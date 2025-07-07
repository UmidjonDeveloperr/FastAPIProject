import json
import logging
from fileinput import filename
from io import BytesIO
from typing import Tuple
import pandas as pd
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.testing import db
from app import models
from sqlalchemy import text
from app.utils import is_expression_equal


async def get_test_by_id(db: AsyncSession, test_id: str):
    result = await db.execute(
        select(models.Test).filter(models.Test.test_id == test_id)
    )
    return result.scalar_one_or_none()

async def ensure_table_exists(test_id: str, db: AsyncSession):
    table_name = f"test_{test_id.lower()}_answers"
    check_sql = f"""
    SELECT EXISTS (
        SELECT FROM information_schema.tables 
        WHERE table_name = '{table_name}'
    )
    """
    result = await db.execute(text(check_sql))
    exists = result.scalar()

    if not exists:
        create_sql = f"""
        CREATE TABLE {table_name} (
            id SERIAL PRIMARY KEY,
            telegram_id BIGINT UNIQUE,
            firstname TEXT,
            secondname TEXT,
            thirdname TEXT,
            region TEXT,
            answers_1_35 TEXT,
            answers_36_45 JSONB,
            submission_time TIMESTAMP
        )
        """
        await db.execute(text(create_sql))
        await db.commit()

async def insert_user_answers(test_id: str, data: dict, db: AsyncSession):
    table_name = f"test_{test_id.lower()}_answers"

    insert_sql = f"""
    INSERT INTO {table_name} (
        telegram_id, firstname, secondname, thirdname,
        region, answers_1_35, answers_36_45, submission_time
    )
    VALUES (
        :telegram_id, :firstname, :secondname, :thirdname,
        :region, :answers_1_35, :answers_36_45, :submission_time
    )
    """

    await db.execute(
        text(insert_sql),
        {
            "telegram_id": data["telegram_id"],
            "firstname": data["firstname"],
            "secondname": data["secondname"],
            "thirdname": data.get("thirdname"),
            "region": data["region"],
            "answers_1_35": data["answers_1_35"],
            "answers_36_45": json.dumps(data["answers_36_45"]),
            "submission_time": data["submission_time"]
        }
    )
    await db.commit()

async def get_user_telegram_id(test_id: str, telegram_id: int, db: AsyncSession):
    table_name = f"test_{test_id.lower()}_answers"
    check_sql_telegram_id = f"""
        SELECT EXISTS (
            SELECT 1 FROM {table_name} WHERE telegram_id = :telegram_id
        )
        """
    result = await db.execute(text(check_sql_telegram_id), {"telegram_id": telegram_id})
    exists = result.scalar()

    if exists:
        raise HTTPException(
            status_code=403,
            detail=f"User telegram id already exists."
        )




async def get_all_tests(db: AsyncSession):
    result = await db.execute(
        select(models.Test)
    )
    return result.scalars().all()


async def save_single_test(test: models.Test, db: AsyncSession):
    db.add(test)
    await db.commit()
    return test

async def update_test(test_id: str, updated_data: dict, db: AsyncSession):
    result = await db.execute(
        select(models.Test).where(models.Test.test_id == test_id)
    )
    test = result.scalar_one_or_none()

    if test:
        # Update only fields that exist in the model
        for key, value in updated_data.items():
            if hasattr(test, key):
                setattr(test, key, value)

        await db.commit()
        await db.refresh(test)

    return test


async def delete_test(test_id: str, db: AsyncSession):
    result = await db.execute(
        select(models.Test).where(models.Test.test_id == test_id)
    )
    test = result.scalar_one_or_none()
    if test:
        await db.delete(test)
        await db.commit()
    return test  # Return deleted object or None




logger = logging.getLogger(__name__)

async def  export_test_results(db: AsyncSession, test_id: str) -> Tuple[BytesIO, str]:
    """
    Export test results to an Excel file with 1/0 scoring.
    Returns a tuple of (BytesIO containing the file, filename).
    """
    # Get test correct answers
    test = await get_test_by_id(db, test_id)
    if not test:
        raise ValueError("Test not found")

    correct_answers = test.answers_1_35
    correct_36_45 = test.answers_36_45

    # Get all user answers - note the table name format matches your actual table
    table_name = f"test_{test_id.lower()}_answers"

    # Check if table exists
    exists = await db.execute(
        text("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = :table_name)"),
        {"table_name": table_name}
    )
    if not exists.scalar():
        raise ValueError("No submissions for this test yet")

    # Get all user data
    records = await db.execute(
        text(f"""
            SELECT firstname, secondname, thirdname, region, answers_1_35, answers_36_45
            FROM {table_name}
            ORDER BY secondname, firstname
        """)
    )
    records = records.fetchall()

    # Process data for Excel
    data = []
    count = 1
    for record in records:
        user_answers = (record.answers_1_35 or "").strip()

        # Handle answers_36_45 which is already a dict in your case
        user_math_answers = record.answers_36_45 or {}

        row = {
            '№': count,
            'F.I.O': f"{record.firstname} {record.secondname} {record.thirdname} ({record.region})"
        }
        count += 1

        # Binary for 1–35
        for i in range(len(user_answers)):
            question_num = i + 1
            is_correct = (i < len(correct_answers)) and (user_answers[i].upper() == correct_answers[i].upper())
            row[str(question_num)] = 1 if is_correct else 0

        # Binary for 36–45 (a and b)
        for q in range(36, 46):
            q_str = str(q)
            for part in ['a', 'b']:
                user_latex = user_math_answers.get(q_str, {}).get(part, "")
                correct_expr = correct_36_45.get(q_str, {}).get(part, "")

                if not isinstance(user_latex, str) or not user_latex.strip():
                    result = 0
                else:
                    result = 1 if is_expression_equal(user_latex, correct_expr) else 0

                row[f"{q}{part}"] = result

        data.append(row)

    # Create DataFrame
    df = pd.DataFrame(data)

    # Define column order
    cols = ['№', 'F.I.O'] + [str(i + 1) for i in range(len(correct_answers))] + \
           [f"{q}{part}" for q in range(36, 46) for part in ['a', 'b']]
    df = df[cols]

    # Create Excel file in memory
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Natijalar')

        # Auto-adjust column widths
        worksheet = writer.sheets['Natijalar']
        for i, col in enumerate(df.columns):
            max_len = max(df[col].astype(str).map(len).max(), len(col)) + 2
            worksheet.set_column(i, i, max_len)

    output.seek(0)
    filename = f"test_{test_id}_natijalar.xlsx"
    return output, filename


async def export_df_results(db: AsyncSession, test_id: str) -> Tuple[BytesIO, str]:
    """
    Export test results to an Excel file with 1/0 scoring.
    Returns a tuple of (BytesIO containing the file, filename).
    """
    # Get test correct answers
    test = await get_test_by_id(db, test_id)
    if not test:
        raise ValueError("Test not found")

    correct_answers = test.answers_1_35
    correct_36_45 = test.answers_36_45

    # Get all user answers - note the table name format matches your actual table
    table_name = f"test_{test_id.lower()}_answers"

    # Check if table exists
    exists = await db.execute(
        text("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = :table_name)"),
        {"table_name": table_name}
    )
    if not exists.scalar():
        raise ValueError("No submissions for this test yet")

    # Get all user data
    records = await db.execute(
        text(f"""
            SELECT firstname, secondname, thirdname, region, answers_1_35, answers_36_45
            FROM {table_name}
            ORDER BY secondname, firstname
        """)
    )
    records = records.fetchall()

    # Process data for Excel
    data = []
    count = 1
    for record in records:
        user_answers = (record.answers_1_35 or "").strip()

        # Handle answers_36_45 which is already a dict in your case
        user_math_answers = record.answers_36_45 or {}

        row = {
            '№': count,
            'F.I.O': f"{record.firstname} {record.secondname} {record.thirdname} ({record.region})"
        }
        count += 1

        # Binary for 1–35
        for i in range(len(user_answers)):
            question_num = i + 1
            is_correct = (i < len(correct_answers)) and (user_answers[i].upper() == correct_answers[i].upper())
            row[str(question_num)] = 1 if is_correct else 0

        # Binary for 36–45 (a and b)
        for q in range(36, 46):
            q_str = str(q)
            for part in ['a', 'b']:
                user_latex = user_math_answers.get(q_str, {}).get(part, "")
                correct_expr = correct_36_45.get(q_str, {}).get(part, "")

                if not isinstance(user_latex, str) or not user_latex.strip():
                    result = 0
                else:
                    result = 1 if is_expression_equal(user_latex, correct_expr) else 0

                row[f"{q}{part}"] = result

        data.append(row)

    # Create DataFrame
    df = pd.DataFrame(data)

    # Define column order
    cols = ['№', 'F.I.O'] + [str(i + 1) for i in range(len(correct_answers))] + \
           [f"{q}{part}" for q in range(36, 46) for part in ['a', 'b']]
    df = df[cols]

    return df