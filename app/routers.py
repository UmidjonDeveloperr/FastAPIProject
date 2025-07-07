# app/routers.py
import os
import tempfile
from io import BytesIO

import numpy as np
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from fastapi.openapi.models import Response
from scipy.stats import zscore
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.testing import db
from starlette.background import BackgroundTask

from FastRaschModel import FastRaschModel
from app import crud, schemas, models
from app.crud import ensure_table_exists, insert_user_answers, export_test_results, logger, export_df_results
from app.database import get_db
from app.schemas import CheckAnswersResponse
from app.utils import check_answers
from fastapi.responses import FileResponse

router = APIRouter()

# Root endpoint
@router.get("/")
async def root():
    return {"message": "API is working", "docs": "/docs", "redoc": "/redoc"}

@router.get("/tests/{test_id}", response_model=schemas.TestResponse)
async def get_test(test_id: str, db: AsyncSession = Depends(get_db)):
    db_test = await crud.get_test_by_id(db, test_id)
    if not db_test:
        raise HTTPException(status_code=404, detail="Test not found")
    return db_test

@router.post("/check-answers", response_model=schemas.CheckAnswersResponse)
async def check_all_answers(payload: schemas.CheckAnswersRequest, db: AsyncSession = Depends(get_db)):
    test = await crud.get_test_by_id(db, payload.test_id)
    if not test:
        raise HTTPException(status_code=404, detail="Test not found")

    result = check_answers(
        user_data={
            "answers_1_35": payload.answers_1_35,
            "answers_36_45": payload.answers_36_45,
        },
        correct_data=test
    )
    percentage = round(result["total_correct"] / test.max_grade * 100, 2)
    return CheckAnswersResponse(
        results_1_35=result["results_1_35"],
        results_36_45=result["results_36_45"],
        total_correct=result["total_correct"],
        percentage=percentage
    )

@router.post("/submit-answers")
async def submit_answers(payload: schemas.SubmitAnswersRequest, db: AsyncSession = Depends(get_db)):
    await ensure_table_exists(payload.test_id, db)
    await crud.get_user_telegram_id(payload.test_id, payload.telegram_id, db)


    await insert_user_answers(payload.test_id, payload.dict(), db)
    return {"message": "Answers submitted successfully"}


@router.get("/tests", response_model=list[schemas.TestResponse])
async def get_all_tests(db: AsyncSession = Depends(get_db)):
    return await crud.get_all_tests(db)

@router.post("/insert-test", response_model=schemas.TestResponse)
async def insert_test(test_data: schemas.TestCreate, db: AsyncSession = Depends(get_db)):
    test = models.Test(**test_data.dict())
    return await crud.save_single_test(test, db)

@router.put("/update-test/{test_id}", response_model=schemas.TestResponse)
async def modify_test(
    test_id: str,
    update_data: schemas.TestUpdate,  # Optional: use `dict` if no schema
    db: AsyncSession = Depends(get_db)
):
    test = await crud.update_test(test_id, update_data.dict(exclude_unset=True), db)
    return test


@router.delete("/delete-test/{test_id}", response_model=schemas.TestResponse)
async def delete_test(test_id: str, db: AsyncSession = Depends(get_db)):
    test = await crud.delete_test(test_id, db)
    return test


@router.get("/export/{test_id}")
async def export_test_results_endpoint(test_id: str, db: AsyncSession = Depends(get_db)):
    """
    Export test results as an Excel file for a given test ID.
    """
    tmp_path = None
    try:
        # Call the business logic to generate the Excel file
        excel_file, filename = await export_test_results(db, test_id)

        # Create a temporary file that won't be automatically deleted
        tmp_path = f"temp_{filename}"
        with open(tmp_path, "wb") as tmp:
            tmp.write(excel_file.getvalue())

        # Return the file as a response
        response = FileResponse(
            path=tmp_path,
            filename=filename,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )

        response.background = BackgroundTask(lambda: os.unlink(tmp_path) if os.path.exists(tmp_path) else None)

        return response

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error exporting test results: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/rasch-analysis/{test_id}")
async def perform_rasch_analysis(
        test_id: str,
        db: AsyncSession = Depends(get_db)  # Inject database session
):
    """
    Perform Rasch analysis on test results and return Excel file with scores.
    """
    try:
        # Load data with database session
        df = await export_df_results(db, test_id)  # Pass db session

        if df is None or df.empty:
            raise HTTPException(
                status_code=404,
                detail="No data found for this test ID"
            )

        print(f"Data loaded successfully with {len(df)} rows")
        print("Faylda mavjud ustunlar:", df.columns.tolist())

        # Agar ustun nomlari boshqacha bo'lsa, ularni moslashtiring
        required_columns = ['№', 'F.I.O.', 'Duris']
        available_columns = df.columns.tolist()

        # Ustun nomlarini tekshirish va moslashtirish
        if not all(col in available_columns for col in required_columns):
            # Agar standart nomlar topilmasa, birinchi 3 ustundan foydalaning
            if len(df.columns) >= 3:
                df.columns = ['№', 'F.I.O.', 'Duris'] + list(df.columns[3:])
                print("Ustun nomlari avtomatik moslashtirildi")
            else:
                raise ValueError("Faylda kamida 3 ta ustun bo'lishi kerak")

        # Column handling
        if len(df.columns) < 3:
            raise ValueError("File must have at least 3 columns")

        # Auto-detect response columns (assuming they start from column 3)
        response_cols = df.columns[3:]
        print(f"Detected {len(response_cols)} response columns")

        # Convert responses to binary (1 for correct, 0 for incorrect)
        response_data = df[response_cols].applymap(lambda x: 1 if x == 1 else 0)

        # Fit Rasch model with progress tracking
        print("Fitting Rasch model...")
        model = FastRaschModel()
        model.fit(response_data)

        # Calculate scores
        print("Calculating scores...")
        df['Theta'] = model.person_ability
        df['Ball'] = 50 + 10 * zscore(df['Theta'])
        df['Ball'] = np.round(df['Ball'], 2)

        df['Ball'] = df['Ball'] + np.random.uniform(-0.05, 0.05, size=len(df['Ball']))
        df['Ball'] = df['Ball'].round(decimals=2)

        # Determine subject type based on max possible score
        max_possible = len(response_cols)
        subject_type = "1-fan" if max_possible >= 45 else "2-fan"

        # Calculate proportional scores
        theta_min = df['Theta'].min()
        theta_range = df['Theta'].max() - theta_min
        if theta_range > 0:
            df['Prop_Score'] = ((df['Theta'] - theta_min) / theta_range) * (max_possible - 65) + 65
        else:
            df['Prop_Score'] = 65  # Handle case where all abilities are equal

        # Assign grades
        bins = [0, 46, 50, 55, 60, 65, 70, 93]
        labels = ['NC', 'C', 'C+', 'B', 'B+', 'A', 'A+']
        df['Daraja'] = pd.cut(df['Ball'], bins=bins, labels=labels, right=False)

        # Save results
        result_cols = ['№', 'F.I.O.', 'Ball', 'Daraja']
        if '№' not in df.columns:
            result_cols = [col for col in result_cols if col != '№']

        print("Saving results...")
        result_path = f'rasch_{test_id}_natijalar.xlsx'

        df = df.sort_values(by='Ball', ascending=False)
        df['№'] = range(1, len(df) + 1)

        # Create Excel file in memory
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df[result_cols].to_excel(writer, index=False, sheet_name='Natijalar')
        output.seek(0)

        filename = f"rasch_{test_id}_natijalar.xlsx"

        tmp_path = f"temp_{filename}"
        with open(tmp_path, "wb") as tmp:
            tmp.write(output.getvalue())

        # Return the file as a response
        response = FileResponse(
            path=tmp_path,
            filename=filename,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

        # Set a callback to delete the file after the response is sent
        response.background = BackgroundTask(lambda: os.unlink(tmp_path) if os.path.exists(tmp_path) else None)

        return response

    except HTTPException:
        raise  # Re-raise HTTP exceptions
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error processing file: {str(e)}"
        )
