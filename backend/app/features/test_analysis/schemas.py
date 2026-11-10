"""Test analysis request and response schemas."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.features.ai_analysis.schemas import (
    AnalysisPattern,
    Grading,
    StageBInput,
    UnitStatus,
)


class StageAQuestionResponse(BaseModel):
    """Facts about one question read from the images (API設計 3.3)."""

    question_id: str
    image_index: int
    question_number: str | None
    problem_text: str
    # 空欄は空文字、読み取れない場合は None。
    student_answer: str | None
    calculation_process: str | None
    grading: Grading


class StageAResponse(BaseModel):
    """Response body of POST /v1/analyses (API設計 3.3)."""

    analysis_request_id: UUID
    status: Literal["awaiting_confirmation"]
    read_score: int | None
    read_unit_name: str | None
    questions: list[StageAQuestionResponse]
    expires_at: datetime


class StageBRequest(StageBInput):
    score: int = Field(strict=True, ge=0)
    max_score: int = Field(strict=True, ge=1)

    @model_validator(mode="after")
    def validate_score(self) -> "StageBRequest":
        if self.score > self.max_score:
            raise ValueError("Score must not exceed max_score.")
        return self


class StageBUnitResponse(BaseModel):
    id: str
    code: str
    name: str


class StageBAnalysisResult(BaseModel):
    patterns: list[AnalysisPattern]


class StageBResponse(BaseModel):
    analysis_request_id: UUID
    status: Literal["completed", "unsupported", "unit_undetermined"]
    unit_status: UnitStatus
    unit: StageBUnitResponse | None
    score: int
    max_score: int
    score_rate: float
    incorrect_question_numbers: list[str] | None
    analysis_result: StageBAnalysisResult | None
    comment_title: str | None
    comment_body: str | None
    message: str | None
