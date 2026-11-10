"""Synthetic PoC scenarios; no real answers or personal information."""

from app.features.ai_analysis.schemas import StageBInput, StageBUnit

UNITS = [
    StageBUnit(id=1, code="division", name="わり算"),
    StageBUnit(id=2, code="addition_subtraction_written", name="たし算とひき算の筆算"),
]
# name, problem, answer, process, expected status, expected master code
CASES = [
    ("decimal", "4cm5mmをcmで表す", "45cm", None, "unsupported", None),
    ("blank", "17÷5", "", None, "supported", "division"),
    ("blank_grouping", "17÷5", "", None, "supported", "division"),
    (
        "carry",
        "368+457の筆算",
        "715",
        "8+7=15、6+5=11、3+4=7",
        "supported",
        "addition_subtraction_written",
    ),
    ("infer_length", "4cm5mmをcmで表す", "4.5cm", None, "unsupported", None),
    (
        "infer_division",
        "24個を6人に同じ数ずつ分ける",
        "3個",
        None,
        "supported",
        "division",
    ),
    (
        "infer_written",
        "368+457の筆算",
        "715",
        None,
        "supported",
        "addition_subtraction_written",
    ),
    ("unknown", "問題内容が読み取れない", "3", None, "undetermined", None),
    ("fraction", "1/3+1/3", "1/6", None, "unsupported", None),
    (
        "transcription",
        "368+457の筆算",
        "815",
        "8+7=15、6+5+1=12、3+4+1=8",
        "supported",
        "addition_subtraction_written",
    ),
    ("remainder", "17÷5", "3あまり3", None, "supported", "division"),
]


def make_input(case=CASES[-1], **overrides) -> StageBInput:
    question = dict(
        question_id="q1",
        image_index=1,
        question_number="1(1)",
        problem_text=case[1],
        student_answer=case[2],
        calculation_process=case[3],
        grading="incorrect",
    )
    question.update(overrides)
    questions = [question]
    if case[0] == "blank_grouping":
        questions.append({**question, "question_id": "q2", "image_index": 2})
    return StageBInput(read_unit_name=None, confirmed_questions=questions)
