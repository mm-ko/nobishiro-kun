"""AI analysis service."""

import json
import re

from pydantic import ValidationError

from app.features.ai_analysis.clients.openrouter import OpenRouterClient
from app.features.ai_analysis.prompts.comment import COMMENT_PROMPT
from app.features.ai_analysis.prompts.stage_a import build_stage_a_messages
from app.features.ai_analysis.prompts.stage_b import PATTERN_PROMPT, UNIT_PROMPT
from app.features.ai_analysis.schemas import (
    AnalysisComment,
    AnalysisPattern,
    CauseType,
    Grading,
    StageAExtraction,
    StageAImageExtraction,
    StageAInputImage,
    StageAQuestion,
    StageBInput,
    StageBPatterns,
    StageBResult,
    StageBUnit,
    StageBUnitDecision,
    UnitStatus,
)

# 1回目の検証失敗のあと、同じ画像でやり直す回数。
STAGE_A_VALIDATION_RETRY_COUNT = 1
# JSON・schemaの検証に失敗した段階だけ、同じ入力で1回やり直す。
STAGE_B_VALIDATION_RETRY_COUNT = 1
COMMENT_VALIDATION_RETRY_COUNT = 1
# 同じ画像から、なるべく同じ読み取り結果が返るようにする。
STAGE_A_REQUEST_PARAMETERS: dict[str, object] = {"temperature": 0}


class StageAInvalidResponseError(Exception):
    """Raised when the AI output for Stage A does not match the expected schema."""


class StageAImageUnreadableError(Exception):
    """Raised when no question can be read from any of the images."""


def parse_stage_a_extraction(content: str) -> StageAImageExtraction:
    """Validate the AI output for one image and return it as a schema object."""
    # AIの出力は外部入力として扱う。エラーには、どこがどう不正かだけを残し、
    # 出力そのもの（答案の内容を含む）は入れない。
    # JSONの前後に説明文やコードブロックの記号が付くことがあるため、
    # 最初の「{」から始まるオブジェクト1つを読む。
    start = content.find("{")
    if start == -1:
        raise StageAInvalidResponseError("Stage A output does not contain JSON.")

    # 頼んだ形は、オブジェクト1つ。「[{...}]」のように配列で囲まれた形は、
    # 中身が正しくても受け付けない。
    if content[:start].rstrip().endswith("["):
        raise StageAInvalidResponseError("Stage A output is a JSON array.")

    try:
        extraction_data, end = json.JSONDecoder().raw_decode(content, start)
    except json.JSONDecodeError:
        raise StageAInvalidResponseError("Stage A output is not valid JSON.") from None

    # オブジェクトの後ろに残ってよいのは、説明文とコードブロックの記号だけ。
    # かっこが残っている場合は、壊れたJSONや2つ目のデータとみなす。
    if any(bracket in content[end:] for bracket in "{}[]"):
        raise StageAInvalidResponseError(
            "Stage A output has unexpected JSON after the object."
        )

    try:
        return StageAImageExtraction.model_validate(extraction_data)
    except ValidationError as exc:
        problems = ", ".join(
            f"{'.'.join(str(part) for part in error['loc'])}: {error['type']}"
            for error in exc.errors(include_input=False, include_url=False)
        )
        raise StageAInvalidResponseError(
            f"Stage A output does not match the schema ({problems})."
        ) from None


def run_stage_a(
    images: list[StageAInputImage], client: OpenRouterClient
) -> StageAExtraction:
    """Extract facts from 1-2 images of one test and combine them into one result."""
    # 画像は1枚ずつ送り、問題の識別子はAIに任せずBEで付ける。
    extractions = [_extract_from_image(image, client) for image in images]

    questions: list[StageAQuestion] = []
    for image_index, extraction in enumerate(extractions, start=1):
        for question in extraction.questions:
            # 表裏で同じ問題番号が出ることがあるため、2枚を通した連番にする。
            questions.append(
                StageAQuestion(
                    **question.model_dump(),
                    question_id=f"q{len(questions) + 1}",
                    image_index=image_index,
                )
            )
    if not questions:
        raise StageAImageUnreadableError("No question could be read from the images.")

    return StageAExtraction(
        read_score=_combine_read_score(extractions),
        read_unit_name=_combine_read_unit_name(extractions),
        questions=questions,
    )


def _extract_from_image(
    image: StageAInputImage, client: OpenRouterClient
) -> StageAImageExtraction:
    image_data_url = OpenRouterClient.encode_image(image.content, image.media_type)
    messages = build_stage_a_messages(image_data_url)

    # 形式の崩れは、同じ画像でもやり直せば直ることがあるため、上限まで再試行する。
    # OpenRouterの通信エラーは、クライアントの中で再試行済みのため、
    # ここでは再試行しない。
    for attempt in range(STAGE_A_VALIDATION_RETRY_COUNT + 1):
        response = client.create_chat_completion(messages, STAGE_A_REQUEST_PARAMETERS)
        try:
            return parse_stage_a_extraction(_get_message_content(response))
        except StageAInvalidResponseError:
            if attempt == STAGE_A_VALIDATION_RETRY_COUNT:
                raise

    raise StageAInvalidResponseError("Stage A output could not be validated.")


def _get_message_content(response: dict[str, object]) -> str:
    choices = response.get("choices")
    if isinstance(choices, list) and choices and isinstance(choices[0], dict):
        message = choices[0].get("message")
        if isinstance(message, dict) and isinstance(message.get("content"), str):
            return message["content"]
    raise StageAInvalidResponseError("Stage A response does not contain any content.")


def _combine_read_score(extractions: list[StageAImageExtraction]) -> int | None:
    # 得点は用紙に1つだけのはず。2枚とも読めた場合は、どちらが正しいか
    # 決められないため使わず、保護者の入力に任せる。
    read_scores = [
        extraction.read_score
        for extraction in extractions
        if extraction.read_score is not None
    ]
    return read_scores[0] if len(read_scores) == 1 else None


def _combine_read_unit_name(extractions: list[StageAImageExtraction]) -> str | None:
    # 表裏で同じ単元名なら使う。違う場合は、まとめテストや別のテストの可能性が
    # あるため使わず、Stage Bの単元判定に任せる。
    read_unit_names = {
        extraction.read_unit_name
        for extraction in extractions
        if extraction.read_unit_name is not None
    }
    return read_unit_names.pop() if len(read_unit_names) == 1 else None


class StageBInvalidResponseError(Exception):
    """Invalid AI output; messages never contain answers or raw model output."""

    validation_issues: tuple[str, ...] = ()


CAUSE_ASSESSMENT_WORDS = (
    "理解",
    "ケアレス",
    "うっかり",
    "注意",
    "集中",
    "苦手",
    "知識不足",
    "練習不足",
    "時間不足",
    "時間切れ",
    "時間が足り",
    "わかってい",
    "分かってい",
    "わかりません",
    "分かりません",
    "わからない",
    "分からない",
    "急い",
    "慌て",
    "見直し",
    "勘違い",
    "見落とし",
)


def _verified_transcription_answer(
    problem: str, answer: str, process: str | None, evidence: str | None
) -> int | None:
    """Verify complete addition columns for cause evidence, without changing grading."""
    if not evidence or evidence not in (process or ""):
        return None
    problem = re.sub(r"\s+", "", problem).replace("＋", "+")
    answer = answer.strip()
    addition = re.fullmatch(r"([0-9]{1,6})\+([0-9]{1,6})(?:の筆算)?", problem)
    if addition is None or re.fullmatch(r"[0-9]{1,7}", answer) is None:
        return None
    left, right = map(int, addition.groups())
    text = re.sub(r"\s+", "", evidence).replace("＋", "+").replace("＝", "=")
    columns = re.split(r"[、,;；]", text)
    if len(columns) != max(len(str(left)), len(str(right))):
        return None
    carry, reconstructed = 0, 0
    for index, column in enumerate(columns):
        equation = re.fullmatch(r"([0-9](?:\+[0-9]){1,2})=([0-9]{1,2})", column)
        if equation is None:
            return None
        operands = list(map(int, equation[1].split("+")))
        expected = [left // 10**index % 10, right // 10**index % 10]
        if carry:
            expected.append(carry)
        total = int(equation[2])
        if sorted(operands) != sorted(expected) or sum(operands) != total:
            return None
        reconstructed += total % 10 * 10**index
        carry = total // 10
    reconstructed += carry * 10 ** len(columns)
    correct_answer = left + right
    if reconstructed != correct_answer or int(answer) == correct_answer:
        return None
    return correct_answer


def _stage_b_json(client: OpenRouterClient, prompt: str, data: str) -> object:
    response = client.create_chat_completion(
        [{"role": "system", "content": prompt}, {"role": "user", "content": data}],
        {"temperature": 0},
    )
    try:
        content = response["choices"][0]["message"]["content"]
        # コードフェンスのみ許容し、欠損や余分なJSONを推測で補わない。
        content = content.strip()
        if content.startswith("```json") and content.endswith("```"):
            content = content[7:-3].strip()
        return json.loads(content)
    except (KeyError, IndexError, TypeError, AttributeError, ValueError):
        raise StageBInvalidResponseError("Stage B output is not valid JSON.") from None


def _validated_stage_b_response[Response: (StageBUnitDecision, StageBPatterns)](
    client: OpenRouterClient, prompt: str, data: str, schema: type[Response]
) -> Response:
    retries_left = STAGE_B_VALIDATION_RETRY_COUNT
    while True:
        try:
            return schema.model_validate(_stage_b_json(client, prompt, data))
        except ValidationError as exc:
            kind = "unit" if schema is StageBUnitDecision else "pattern"
            error = StageBInvalidResponseError(f"Invalid Stage B {kind} schema.")
            if schema is StageBPatterns:
                fields = {
                    "patterns",
                    "pattern",
                    "cause_type",
                    "question_ids",
                    "explanation",
                    "evidence",
                }
                issues = []
                for issue in exc.errors(
                    include_input=False, include_context=False, include_url=False
                ):
                    path = ".".join(
                        str(part)
                        if isinstance(part, int) or part in fields
                        else "extra_field"
                        for part in issue["loc"]
                    )
                    issues.append(f"{path or 'patterns'}:{issue['type']}")
                error.validation_issues = tuple(sorted(set(issues)))
        except StageBInvalidResponseError as exc:
            error = exc
        # 通信エラーはここで捕捉せず、クライアント側の再試行結果をそのまま返す。
        if retries_left == 0:
            raise error from None
        retries_left -= 1


def generate_comment(
    data: StageBInput, result: StageBResult, client: OpenRouterClient
) -> AnalysisComment:
    """Generate a comment without repeating the validated pattern analysis."""
    if (
        result.unit_status != UnitStatus.SUPPORTED
        or result.unit is None
        or result.patterns is None
    ):
        raise StageBInvalidResponseError("Comment requires a supported analysis.")
    payload = json.dumps(
        {
            "confirmed_questions": [
                question.model_dump(mode="json")
                for question in data.confirmed_questions
            ],
            "unit": result.unit.model_dump(mode="json", exclude={"id"}),
            "patterns": [
                pattern.model_dump(mode="json") for pattern in result.patterns
            ],
        },
        ensure_ascii=False,
    )
    for attempt in range(COMMENT_VALIDATION_RETRY_COUNT + 1):
        try:
            return AnalysisComment.model_validate(
                _stage_b_json(client, COMMENT_PROMPT, payload)
            )
        except (ValidationError, StageBInvalidResponseError):
            # 検証エラーに答案や生成文を含めず、コメントだけを再試行する。
            if attempt == COMMENT_VALIDATION_RETRY_COUNT:
                raise StageBInvalidResponseError("Invalid comment response.") from None
    raise StageBInvalidResponseError("Comment could not be validated.")


def run_stage_b(
    data: StageBInput, units: list[StageBUnit], client: OpenRouterClient
) -> StageBResult:
    """Analyze text; the caller owns DB access, persistence and client lifetime."""
    supported_codes = {"division", "addition_subtraction_written"}
    master = {unit.code: unit for unit in units if unit.code in supported_codes}
    if len(master) != len(units) or not master:
        raise ValueError("Provide unique MVP unit master entries.")
    payload = data.model_dump(mode="json")
    payload["units"] = [unit.model_dump() for unit in units]
    encoded = json.dumps(payload, ensure_ascii=False)
    decision = _validated_stage_b_response(
        client, UNIT_PROMPT, encoded, StageBUnitDecision
    )
    names = {unit.name: unit.code for unit in units}
    names["あまりのあるわり算"] = "division"
    named_code = names.get(data.read_unit_name)
    # 明確に名寄せできる読み取り済み単元名を、AIの問題内容からの推定で上書きしない。
    if named_code is not None:
        decision = StageBUnitDecision(
            unit_status=UnitStatus.SUPPORTED, unit_code=named_code
        )
    unit = master.get(decision.unit_code)
    if (decision.unit_status == UnitStatus.SUPPORTED and unit is None) or (
        decision.unit_status != UnitStatus.SUPPORTED and decision.unit_code is not None
    ):
        raise StageBInvalidResponseError("Unit status and master code do not match.")
    result = StageBResult(
        unit_status=decision.unit_status,
        unit=unit,
        unit_is_estimated=unit is not None and data.read_unit_name is None,
        patterns=None,
    )
    if unit is None:
        return result
    incorrect = {
        q.question_id: q
        for q in data.confirmed_questions
        if q.grading == Grading.INCORRECT
    }
    result.patterns = []
    if not incorrect:
        return result
    payload["unit"] = unit.model_dump()
    analysis = _validated_stage_b_response(
        client, PATTERN_PROMPT, json.dumps(payload, ensure_ascii=False), StageBPatterns
    )
    correct_ids = {
        q.question_id for q in data.confirmed_questions if q.grading == Grading.CORRECT
    }
    for pattern in analysis.patterns:
        for question_id in dict.fromkeys(pattern.question_ids):
            question = incorrect.get(question_id)
            if question is None:
                if question_id in correct_ids:
                    continue
                raise StageBInvalidResponseError(
                    "Pattern must refer to an incorrect ID."
                )
            # 空欄はAIの分類によらず検出する。過程がない原因推測も採用しない。
            if question.student_answer == "":
                continue
            cause = pattern.cause_type
            explanation = pattern.explanation
            pattern_name = pattern.pattern
            if cause == CauseType.BLANK:
                # 非空欄を空欄とするAIの分類は採用せず、この問題だけ判定困難にする。
                cause = CauseType.UNDETERMINED
                pattern_name = "判定困難"
                explanation = (
                    "確認済みの採点では、この問題は誤答です。"
                    "この答案だけでは原因を判断できません。原因は判定困難です。"
                )
            if cause == CauseType.UNDETERMINED:
                # 原因評価のない誤りの説明は残し、原因を判断できないことを明示する。
                if any(word in explanation for word in CAUSE_ASSESSMENT_WORDS):
                    explanation = (
                        "確認済みの採点では、この問題は誤答です。"
                        "この答案だけでは原因を判断できません。原因は判定困難です。"
                    )
                elif "原因は判定困難です。" not in explanation:
                    explanation = f"{explanation} 原因は判定困難です。"
            if cause in (
                CauseType.CARELESS_MISTAKE,
                CauseType.POSSIBLE_UNDERSTANDING_GAP,
            ):
                facts = [question.calculation_process or ""]
                if cause == CauseType.POSSIBLE_UNDERSTANDING_GAP:
                    facts.extend([question.problem_text, question.student_answer])
                # AIの命名や引用だけではなく、筆算の全桁と解答の不一致を検証する。
                verified_answer = None
                transcription = cause == CauseType.CARELESS_MISTAKE and any(
                    word in pattern.pattern
                    for word in ("書き写", "書写", "転記", "写し間違")
                )
                if transcription and unit.code == "addition_subtraction_written":
                    verified_answer = _verified_transcription_answer(
                        question.problem_text,
                        question.student_answer,
                        question.calculation_process,
                        pattern.evidence,
                    )
                # 誤った途中式や繰り上がりの反映漏れだけでは原因を区別できない。
                error_only = verified_answer is None and (
                    transcription
                    or (
                        unit.code == "addition_subtraction_written"
                        and (
                            cause == CauseType.CARELESS_MISTAKE
                            or re.fullmatch(
                                r"[\d\s+＋\-−×*÷/＝=、,.;:()（）]+",
                                pattern.evidence or "",
                            )
                            is not None
                            or any(
                                word in pattern.pattern + (pattern.evidence or "")
                                for word in ("繰り上が", "繰上", "くり上が", "くりあが")
                            )
                        )
                    )
                )
                if error_only:
                    cause = CauseType.UNDETERMINED
                    explanation = (
                        "途中式の記述だけでは、理解不足かうっかりミスかを"
                        "区別できません。原因は判定困難です。"
                    )
                elif verified_answer is not None:
                    explanation = (
                        f"途中式から得られる答えは{verified_answer}ですが、"
                        f"確認済みの解答は{question.student_answer}です。"
                        "書き写し間違いによるケアレスミスの可能性があります。"
                        f"確認した記述: {pattern.evidence}。原因は断定できません。"
                    )
                elif (
                    unit.code == "division"
                    and not question.calculation_process
                    and pattern.evidence
                    and pattern.evidence in question.student_answer
                ):
                    cause = CauseType.UNDETERMINED
                    explanation = (
                        "解答の記述だけでは、理解不足かうっかりミスかを"
                        "区別できません。原因は判定困難です。"
                    )
                elif not pattern.evidence or not any(
                    pattern.evidence in fact for fact in facts
                ):
                    cause = CauseType.UNDETERMINED
                    explanation = (
                        "確認済みデータに原因の根拠が不足しており、判定困難です。"
                    )
                else:
                    label = (
                        "ケアレスミス"
                        if cause == CauseType.CARELESS_MISTAKE
                        else "理解不足"
                    )
                    explanation = (
                        f"{label}の可能性があります。確認した記述: {pattern.evidence}。"
                        "原因は断定できません。"
                    )
            number = question.question_number or f"番号不明-{question.question_id}"
            # 原因評価を誤りの型として表示しない。原因不明だけでは置換しない。
            if any(word in pattern_name for word in CAUSE_ASSESSMENT_WORDS):
                pattern_name = "判定困難"
            result.patterns.append(
                AnalysisPattern(
                    pattern=pattern_name,
                    cause_type=cause,
                    question_numbers=[f"{question.image_index}:{number}"],
                    explanation=explanation,
                )
            )
    for question in incorrect.values():
        if question.student_answer == "":
            number = question.question_number or f"番号不明-{question.question_id}"
            result.patterns.append(
                AnalysisPattern(
                    pattern="判定困難",
                    cause_type=CauseType.BLANK,
                    question_numbers=[f"{question.image_index}:{number}"],
                    explanation="確認済みの解答が空欄です。理由は断定できません。",
                )
            )
    grouped: dict[tuple[str, CauseType, str], AnalysisPattern] = {}
    for item in result.patterns:
        key = (item.pattern, item.cause_type, item.explanation)
        if key not in grouped:
            grouped[key] = item.model_copy(update={"question_numbers": []})
        for number in item.question_numbers:
            if number not in grouped[key].question_numbers:
                grouped[key].question_numbers.append(number)
    result.patterns = list(grouped.values())
    return result
