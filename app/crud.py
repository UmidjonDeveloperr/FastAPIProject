import json
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app import models
from sqlalchemy import text


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