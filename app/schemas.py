import json
from datetime import datetime
from typing import Dict, Optional, Union
from pydantic import BaseModel, ConfigDict, field_validator, Field


# TestResponse and AnswerSubmission remain unchanged
class TestResponse(BaseModel):
    """Response model for test metadata"""
    test_id: str = Field(..., description="Unique identifier for the test")
    status: str = Field(..., description="Test status (e.g., 'active', 'inactive')")
    answers_1_35: Optional[Dict[int, str]] = Field(
        default=None,
        description="Answers for questions 1-35 (keys: question numbers as strings, values: answer letters)"
    )
    answers_36_45: Optional[Dict[str, Union[str, Dict[str, str]]]] = Field(
        default=None,
        description="Answers for questions 36-45 (keys: question parts, values: math expressions or sub-answers)"
    )
    max_grade: int = Field(..., ge=0, description="Maximum possible grade for the test")
    created_at: datetime = Field(..., description="When the test was created")

    model_config = ConfigDict(from_attributes=True)

    @field_validator('answers_1_35', 'answers_36_45', mode='before')
    def convert_answers(cls, value):
        """Convert database answer formats to proper dictionaries"""
        if value is None:
            return None

        # Handle case where answers might be stored as JSON strings
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                # Handle case where answers_1_35 might be a plain string (like 'A'*35)
                if len(value) >= 35:
                    return {str(i + 1): value[i] for i in range(35)}
                return None

        # Convert all dictionary keys to strings
        if isinstance(value, dict):
            return {str(k): v for k, v in value.items()}

        return None


class PartAnswer(BaseModel):
    a: str
    b: str

class CheckAnswersRequest(BaseModel):
    test_id: str
    answers_1_35: Dict[str, str]  # example: {"1": "A", ..., "35": "D"}
    answers_36_45: Dict[str, PartAnswer]  # example: {"36": {"a": "2", "b": "1"}}

class SingleAnswerResult(BaseModel):
    is_correct: bool
    correct_answer: str

class CheckAnswersResponse(BaseModel):
    results_1_35: Dict[str, SingleAnswerResult]
    results_36_45: Dict[str, Dict[str, SingleAnswerResult]]
    total_correct: float
    percentage: float

class MathAnswer(BaseModel):
    a: str
    b: str

class SubmitAnswersRequest(BaseModel):
    test_id: str
    telegram_id: int
    firstname: str
    secondname: str
    thirdname: Optional[str]
    region: str
    answers_1_35: str
    answers_36_45: Dict[str, MathAnswer]
    submission_time: datetime


class TestCreate(BaseModel):
    test_id: str = Field(..., max_length=20)
    answers_1_35: Dict[str, str]
    answers_36_45: Dict[str, Union[str, Dict[str, str]]]
    status: str = "inactive"
    max_grade: int = 93


class TestUpdate(BaseModel):
    answers_1_35: Optional[Dict[str, str]] = None
    answers_36_45: Optional[Dict[str, Union[str, Dict[str, str]]]] = None
    status: Optional[str] = None
    max_grade: Optional[int] = None

