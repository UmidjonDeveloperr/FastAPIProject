# app/routers.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app import crud, schemas
from app.crud import ensure_table_exists, insert_user_answers
from app.database import get_db
from app.schemas import CheckAnswersResponse
from app.utils import check_answers

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
