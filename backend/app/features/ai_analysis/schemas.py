"""AI analysis data schemas."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Grading(StrEnum):
    """Teacher's grading as read from the image. The AI never grades by itself."""

    CORRECT = "correct"
    INCORRECT = "incorrect"
    UNKNOWN = "unknown"


def _strip_text(value: object) -> object:
    return value.strip() if isinstance(value, str) else value


def _empty_text_to_none(value: object) -> object:
    stripped_value = _strip_text(value)
    return None if stripped_value == "" else stripped_value


class StageAExtractedQuestion(BaseModel):
    """Facts about one question, as returned by the AI for a single image."""

    # 独自採点やパターン分析など、求めていない項目をAIが返しても、後続へ渡さない。
    model_config = ConfigDict(extra="ignore")

    question_number: str | None
    problem_text: str = Field(min_length=1)
    # 空欄は空文字、読み取れない場合は None。意味が違うため、空文字を None にしない。
    student_answer: str | None
    calculation_process: str | None
    grading: Grading

    @field_validator("question_number", mode="before")
    @classmethod
    def normalize_question_number(cls, value: object) -> object:
        # 「1」のように、数値で返ることがある。
        if isinstance(value, int) and not isinstance(value, bool):
            return str(value)
        return _empty_text_to_none(value)

    @field_validator("problem_text", "student_answer", mode="before")
    @classmethod
    def strip_text(cls, value: object) -> object:
        return _strip_text(value)

    @field_validator("calculation_process", mode="before")
    @classmethod
    def normalize_calculation_process(cls, value: object) -> object:
        return _empty_text_to_none(value)


class StageAImageExtraction(BaseModel):
    """Facts extracted from a single test image by the AI."""

    model_config = ConfigDict(extra="ignore")

    read_score: int | None
    read_unit_name: str | None
    questions: list[StageAExtractedQuestion]

    @field_validator("read_score", mode="before")
    @classmethod
    def normalize_read_score(cls, value: object) -> int | None:
        # 得点は、0以上の整数として確定できる場合だけ使う（API設計 3.3）。
        # 「80点」「4.5」などは推測で直さず、None にして保護者の入力に任せる。
        if isinstance(value, bool):
            return None
        if isinstance(value, float) and value.is_integer():
            value = int(value)
        if isinstance(value, str) and value.strip().isascii():
            stripped_value = value.strip()
            value = int(stripped_value) if stripped_value.isdigit() else None
        if isinstance(value, int) and value >= 0:
            return value
        return None

    @field_validator("read_unit_name", mode="before")
    @classmethod
    def normalize_read_unit_name(cls, value: object) -> object:
        return _empty_text_to_none(value)


class StageAInputImage(BaseModel):
    """One test image to send to Stage A. Kept in memory only, never saved."""

    content: bytes
    media_type: str


class StageAQuestion(StageAExtractedQuestion):
    """Facts about one question, with the identifiers assigned by the backend."""

    question_id: str
    image_index: int


class StageAExtraction(BaseModel):
    """Stage A result for one test, combined from up to two images."""

    read_score: int | None
    read_unit_name: str | None
    questions: list[StageAQuestion]


class UnitStatus(StrEnum):
    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    UNDETERMINED = "undetermined"


class CauseType(StrEnum):
    BLANK = "blank"
    CARELESS_MISTAKE = "careless_mistake"
    POSSIBLE_UNDERSTANDING_GAP = "possible_understanding_gap"
    UNDETERMINED = "undetermined"


class ConfirmedQuestion(StageAExtractedQuestion):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    question_id: str = Field(min_length=1)
    image_index: int = Field(strict=True, ge=1, le=2)
    student_answer: str

    @field_validator("grading")
    @classmethod
    def require_confirmed_grading(cls, value: Grading) -> Grading:
        if value == Grading.UNKNOWN:
            raise ValueError("Grading must be confirmed.")
        return value


class StageBInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    read_unit_name: str | None
    confirmed_questions: list[ConfirmedQuestion] = Field(min_length=1)

    @field_validator("read_unit_name", mode="before")
    @classmethod
    def normalize_unit_name(cls, value: object) -> object:
        return _empty_text_to_none(value)

    @model_validator(mode="after")
    def require_unique_question_ids(self) -> "StageBInput":
        ids = [question.question_id for question in self.confirmed_questions]
        if len(ids) != len(set(ids)):
            raise ValueError("Question IDs must be unique.")
        return self


class StageBUnit(BaseModel):
    id: int = Field(strict=True, gt=0)
    code: str = Field(min_length=1)
    name: str = Field(min_length=1)


class StageBUnitDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    unit_status: UnitStatus
    unit_code: str | None


class StageBPattern(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    pattern: str = Field(min_length=1)
    cause_type: CauseType
    question_ids: list[str] = Field(min_length=1)
    explanation: str = Field(min_length=1)
    evidence: str | None


class StageBPatterns(BaseModel):
    model_config = ConfigDict(extra="forbid")

    patterns: list[StageBPattern]


class AnalysisPattern(BaseModel):
    pattern: str
    cause_type: CauseType
    question_numbers: list[str]
    explanation: str


class StageBResult(BaseModel):
    unit_status: UnitStatus
    unit: StageBUnit | None
    unit_is_estimated: bool
    patterns: list[AnalysisPattern] | None


class AnalysisComment(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    comment_title: str = Field(min_length=1, max_length=60)
    comment_body: str = Field(min_length=150, max_length=800)
