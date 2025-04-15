from sqlalchemy import Column, Integer, String, DateTime, JSON
from sqlalchemy.sql import func
from app.database import Base


class Test(Base):
    __tablename__ = 'tests'

    # Internal primary key
    id = Column(Integer, primary_key=True, index=True)

    # Public-facing test identifier (e.g., "MATH2023-FINAL")
    test_id = Column(String(20), unique=True, nullable=False)

    # Correct answers for multiple-choice questions (1-35)
    answers_1_35 = Column(
        JSON,
        nullable=False,
        comment="Stores correct answers as {'1': 'A', '2': 'B', ..., '35': 'F'}"
    )

    # Correct answers for math problems (36-45)
    answers_36_45 = Column(
        JSON,
        nullable=False,
        comment="Stores correct answers as {'36a': '42', '36b': '3.14', ...}"
    )

    # Test status - consider using ENUM if limited known values
    status = Column(String(10), default='inactive', nullable=False)

    # Maximum possible grade (default matches common test scales)
    max_grade = Column(Integer, default=93, nullable=False)

    # Automatic timestamp with timezone
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)