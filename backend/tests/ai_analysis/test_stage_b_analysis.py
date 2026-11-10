import contextlib
import importlib.util
import io
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from pydantic import ValidationError
from stage_b_cases import CASES, UNITS, make_input

from app.features.ai_analysis.clients.openrouter import (
    OpenRouterClient,
    OpenRouterError,
)
from app.features.ai_analysis.schemas import CauseType
from app.features.ai_analysis.service import StageBInvalidResponseError, run_stage_b


def client_for(status="supported", code="division", patterns=None):
    outputs = [
        dict(unit_status=status, unit_code=code),
        dict(patterns=patterns or []),
        dict(patterns=patterns or []),
    ]
    client = Mock(spec=OpenRouterClient)
    client.create_chat_completion.side_effect = [
        {"choices": [{"message": {"content": json.dumps(output)}}]}
        for output in outputs
    ]
    return client


def pattern(cause="undetermined", evidence=None, **overrides):
    value = dict(
        pattern="あまりの計算ミス",
        cause_type=cause,
        question_ids=["q1"],
        explanation="あまりの値に誤りが見られます。",
        evidence=evidence,
    )
    value.update(overrides)
    return value


class StageBTests(unittest.TestCase):
    def test_identical_patterns_group_numbers_in_first_seen_order_without_duplicates(
        self,
    ):
        data = make_input()
        data.confirmed_questions.extend(
            [
                make_input(question_id="q2", image_index=2).confirmed_questions[0],
                make_input(
                    question_id="q3", question_number="1(2)"
                ).confirmed_questions[0],
            ]
        )
        result = run_stage_b(
            data,
            UNITS,
            client_for(
                patterns=[
                    pattern(question_ids=["q2", "q3", "q1", "q2"]),
                    pattern(pattern="商の計算ミス", question_ids=["q2"]),
                    pattern(question_ids=["q1", "q3"]),
                ]
            ),
        )
        self.assertEqual(len(result.patterns), 2)
        self.assertEqual(
            result.patterns[0].question_numbers, ["2:1(1)", "1:1(2)", "1:1(1)"]
        )
        self.assertEqual(result.patterns[0].pattern, "あまりの計算ミス")
        self.assertEqual(result.patterns[0].cause_type, "undetermined")
        self.assertEqual(result.patterns[1].pattern, "商の計算ミス")
        self.assertEqual(result.patterns[1].question_numbers, ["2:1(1)"])

    def test_patterns_with_different_final_fields_remain_separate(self):
        for changes in (
            {"pattern": "商の計算ミス"},
            {"explanation": "商ではなく、あまりの値が異なっています。"},
            {"cause_type": "careless_mistake", "evidence": "3"},
        ):
            with self.subTest(changes=changes):
                data = make_input(calculation_process="商は3")
                data.confirmed_questions.append(
                    make_input(
                        question_id="q2",
                        question_number="1(2)",
                        calculation_process="商は3",
                    ).confirmed_questions[0]
                )
                result = run_stage_b(
                    data,
                    UNITS,
                    client_for(
                        patterns=[pattern(), pattern(question_ids=["q2"], **changes)]
                    ),
                )
                self.assertEqual(len(result.patterns), 2)
                self.assertEqual(result.patterns[0].question_numbers, ["1:1(1)"])
                self.assertEqual(result.patterns[1].question_numbers, ["1:1(2)"])

    def test_grouping_uses_sanitized_patterns_and_explanations(self):
        data = make_input()
        data.confirmed_questions.append(
            make_input(question_id="q2", question_number="1(2)").confirmed_questions[0]
        )
        result = run_stage_b(
            data,
            UNITS,
            client_for(
                patterns=[
                    pattern(pattern="理解不足", explanation="理解できていません。"),
                    pattern(
                        pattern="ケアレスミス",
                        explanation="急いで書いたため数字を写し間違えたようです。",
                        question_ids=["q2"],
                    ),
                ]
            ),
        )
        self.assertEqual(len(result.patterns), 1)
        self.assertEqual(result.patterns[0].pattern, "判定困難")
        self.assertEqual(result.patterns[0].question_numbers, ["1:1(1)", "1:1(2)"])
        self.assertNotIn("急い", result.patterns[0].explanation)

    def test_blank_patterns_are_grouped_with_unknown_number_format_preserved(self):
        data = make_input(student_answer="", question_number=None)
        data.confirmed_questions.append(
            make_input(
                question_id="q2", image_index=2, student_answer="", question_number=None
            ).confirmed_questions[0]
        )
        result = run_stage_b(data, UNITS, client_for())
        self.assertEqual(len(result.patterns), 1)
        self.assertEqual(result.patterns[0].cause_type, "blank")
        self.assertEqual(
            result.patterns[0].question_numbers, ["1:番号不明-q1", "2:番号不明-q2"]
        )

    def test_blank_grouping_verification_requires_one_pattern_with_both_numbers(self):
        spec = importlib.util.spec_from_file_location(
            "verify_stage_b",
            Path(__file__).resolve().parents[2] / "scripts/verify_stage_b.py",
        )
        script = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(script)
        case = next(case for case in CASES if case[0] == "blank_grouping")
        result = run_stage_b(make_input(case), UNITS, client_for())
        variants = [(result.patterns, 0), (None, 1), ([], 1)]
        item = result.patterns[0]
        for changes in (
            {"cause_type": CauseType.UNDETERMINED},
            {"pattern": "あまりの計算ミス"},
            {"question_numbers": ["1:1(1)"]},
            {"question_numbers": ["1:1(1)", "1:1(2)"]},
            {"question_numbers": ["2:1(1)", "1:1(1)"]},
            {"question_numbers": ["1:1(1)", "2:1(1)", "2:1(1)"]},
        ):
            variants.append(([item.model_copy(update=changes)], 1))
        variants.append(
            (
                [
                    item.model_copy(update={"question_numbers": [number]})
                    for number in ("1:1(1)", "2:1(1)")
                ],
                1,
            )
        )
        for patterns, expected in variants:
            for review in (False, True):
                with self.subTest(patterns=patterns, review=review):
                    output = io.StringIO()
                    argv = ["verify_stage_b.py"] + (["--review"] if review else [])
                    with (
                        patch.object(script, "CASES", [case]),
                        patch.object(script, "OpenRouterClient", return_value=Mock()),
                        patch.object(
                            script,
                            "run_stage_b",
                            return_value=result.model_copy(
                                update={"patterns": patterns}
                            ),
                        ),
                        patch.object(sys, "argv", argv),
                        contextlib.redirect_stdout(output),
                    ):
                        self.assertEqual(script.main(), expected)
                    self.assertIn(
                        f"blank_grouping: {'PASS' if expected == 0 else 'FAIL'}",
                        output.getvalue(),
                    )
                    self.assertEqual("review case=" in output.getvalue(), review)

    def test_verification_error_diagnostics_use_only_predefined_labels(self):
        spec = importlib.util.spec_from_file_location(
            "verify_stage_b",
            Path(__file__).resolve().parents[2] / "scripts/verify_stage_b.py",
        )
        script = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(script)
        case = next(case for case in CASES if case[0] == "transcription")
        errors = [
            ("Stage B output is not valid JSON.", "invalid_json"),
            ("Invalid Stage B unit schema.", "invalid_unit_schema"),
            ("Unit status and master code do not match.", "unit_master_mismatch"),
            ("Invalid Stage B pattern schema.", "invalid_pattern_schema"),
            ("Pattern must refer to an incorrect ID.", "invalid_question_reference"),
            ("synthetic-sensitive-output", "unknown_invalid_response"),
        ]
        exceptions = [
            (StageBInvalidResponseError(text), reason) for text, reason in errors
        ]
        for value, expected in (
            (pattern(cause="synthetic-sensitive-output"), "patterns.0.cause_type:enum"),
            (
                {key: value for key, value in pattern().items() if key != "evidence"},
                "patterns.0.evidence:missing",
            ),
            (
                pattern(**{"synthetic-sensitive-output": "private"}),
                "patterns.0.extra_field:extra_forbidden",
            ),
        ):
            with self.assertRaises(StageBInvalidResponseError) as caught:
                run_stage_b(make_input(), UNITS, client_for(patterns=[value]))
            self.assertEqual(caught.exception.validation_issues, (expected,))
            exceptions.append((caught.exception, "invalid_pattern_schema"))
        exceptions.append((OpenRouterError("synthetic-sensitive-output"), None))
        for exc, reason in exceptions:
            for review in (False, True):
                with self.subTest(
                    error=type(exc).__name__, reason=reason, review=review
                ):
                    output = io.StringIO()
                    client = Mock()
                    argv = ["verify_stage_b.py"] + (["--review"] if review else [])
                    with (
                        patch.object(script, "CASES", [case]),
                        patch.object(script, "OpenRouterClient", return_value=client),
                        patch.object(script, "run_stage_b", side_effect=exc) as run,
                        patch.object(sys, "argv", argv),
                        contextlib.redirect_stdout(output),
                    ):
                        self.assertEqual(script.main(), 1)
                    text = output.getvalue()
                    self.assertIn("transcription: FAIL", text)
                    self.assertIn(f"error={type(exc).__name__}", text)
                    if reason is None:
                        self.assertNotIn("reason=", text)
                    else:
                        self.assertIn(f"reason={reason}", text)
                    if (
                        isinstance(exc, StageBInvalidResponseError)
                        and exc.validation_issues
                    ):
                        self.assertIn(
                            f"validation_issues={list(exc.validation_issues)}", text
                        )
                    self.assertNotIn(str(exc), text)
                    self.assertNotIn(case[1], text)
                    self.assertNotIn(case[3], text)
                    run.assert_called_once()
                    client.close.assert_called_once()

    def test_question_number_format_for_analysis_and_blank_answers(self):
        for answer in ("3あまり3", ""):
            for image_index in (1, 2):
                for number, expected in (
                    (None, "番号不明-q3"),
                    ("1(1)", "1(1)"),
                ):
                    with self.subTest(
                        answer=answer, image_index=image_index, number=number
                    ):
                        data = make_input(
                            question_id="q3",
                            image_index=image_index,
                            question_number=number,
                            student_answer=answer,
                        )
                        result = run_stage_b(
                            data,
                            UNITS,
                            client_for(patterns=[pattern(question_ids=["q3"])]),
                        )
                        self.assertEqual(len(result.patterns), 1)
                        self.assertEqual(
                            result.patterns[0].question_numbers,
                            [f"{image_index}:{expected}"],
                        )
                        self.assertEqual(
                            result.patterns[0].cause_type,
                            "blank" if answer == "" else "undetermined",
                        )

    def test_scenarios_preserve_master_and_use_text_only(self):
        for case in CASES:
            with self.subTest(case=case[0]):
                client = client_for(case[4], case[5])
                result = run_stage_b(make_input(case), UNITS, client)
                self.assertEqual(result.unit_status, case[4])
                self.assertEqual(result.unit.code if result.unit else None, case[5])
                self.assertEqual(
                    client.create_chat_completion.call_count,
                    2 if case[4] == "supported" else 1,
                )
                for call in client.create_chat_completion.call_args_list:
                    self.assertTrue(
                        all(isinstance(m["content"], str) for m in call.args[0])
                    )
                if case[0] == "blank":
                    self.assertEqual(result.patterns[0].cause_type, "blank")

    def test_read_unit_name_is_passed_and_not_marked_estimated(self):
        data = make_input()
        data.read_unit_name = "あまりのあるわり算"
        client = client_for(code="addition_subtraction_written", patterns=[pattern()])
        result = run_stage_b(data, UNITS, client)
        self.assertFalse(result.unit_is_estimated)
        self.assertEqual(result.unit.code, "division")
        payload = json.loads(
            client.create_chat_completion.call_args_list[0].args[0][1]["content"]
        )
        self.assertEqual(payload["read_unit_name"], data.read_unit_name)
        self.assertEqual(result.patterns[0].question_numbers, ["1:1(1)"])

    def test_causes_require_quoted_evidence_and_never_assert_understanding(self):
        for cause, evidence, process, expected in [
            ("careless_mistake", "3", None, "undetermined"),
            ("careless_mistake", "3", "商は3", "careless_mistake"),
            ("possible_understanding_gap", None, None, "undetermined"),
            (
                "possible_understanding_gap",
                "3あまり3",
                None,
                "undetermined",
            ),
            (
                "possible_understanding_gap",
                "あまりは割る数より大きくてよい",
                "あまりは割る数より大きくてよい",
                "possible_understanding_gap",
            ),
        ]:
            with self.subTest(cause=cause, evidence=evidence):
                client = client_for(patterns=[pattern(cause, evidence)])
                result = run_stage_b(
                    make_input(calculation_process=process), UNITS, client
                )
                self.assertEqual(result.patterns[0].cause_type, expected)
                if expected != "undetermined":
                    self.assertIn("可能性", result.patterns[0].explanation)

    def test_correct_questions_are_never_analyzed(self):
        client = client_for()
        result = run_stage_b(make_input(grading="correct"), UNITS, client)
        self.assertEqual(result.patterns, [])
        self.assertEqual(client.create_chat_completion.call_count, 1)

    def test_undetermined_explanation_does_not_preserve_cause_assertions(self):
        for text in (
            "理解できていません。",
            "繰り上がりの仕組みを理解できていないようです。",
            "ケアレスミスです。",
            "不注意によるミスの可能性があります。",
            "時間が足りませんでした。",
            "急いで書いたため数字を写し間違えたようです。",
            "慌てて答えを書いたようです。",
            "見直しが足りなかったようです。",
            "勘違いしたようです。",
            "繰り上がりを見落としたようです。",
        ):
            with self.subTest(text=text):
                result = run_stage_b(
                    make_input(),
                    UNITS,
                    client_for(patterns=[pattern(explanation=text)]),
                )
                self.assertNotIn(text, result.patterns[0].explanation)
                self.assertIn("原因は判定困難", result.patterns[0].explanation)
                self.assertEqual(result.patterns[0].pattern, "あまりの計算ミス")

    def test_undetermined_explanation_preserves_specific_error_details(self):
        for text in (
            "商の3は合っていますが、あまりが2ではなく3になっています。",
            "繰り上がりの1が次の位の計算に反映されていません。",
            "あまりが2ではなく3になっています。 原因は判定困難です。",
        ):
            with self.subTest(text=text):
                result = run_stage_b(
                    make_input(),
                    UNITS,
                    client_for(patterns=[pattern(explanation=text)]),
                )
                explanation = result.patterns[0].explanation
                self.assertIn(text, explanation)
                self.assertEqual(explanation.count("原因は判定困難です。"), 1)
                self.assertEqual(result.patterns[0].cause_type, "undetermined")

    def test_written_transcription_can_be_a_possible_careless_mistake(self):
        process = "8+7=15、6+5+1=12、3+4+1=8"
        for title in ("答えの書き写し間違い", "答えの転記ミス"):
            with self.subTest(title=title):
                data = make_input(
                    problem_text="368+457の筆算",
                    student_answer="815",
                    calculation_process=process,
                )
                result = run_stage_b(
                    data,
                    UNITS,
                    client_for(
                        code="addition_subtraction_written",
                        patterns=[pattern("careless_mistake", process, pattern=title)],
                    ),
                )
                self.assertEqual(result.patterns[0].pattern, title)
                self.assertEqual(result.patterns[0].cause_type, "careless_mistake")
                self.assertIn("ケアレスミスの可能性", result.patterns[0].explanation)
                self.assertIn("断定できません", result.patterns[0].explanation)
                self.assertIn(process, result.patterns[0].explanation)
                self.assertIn(
                    "途中式から得られる答えは825", result.patterns[0].explanation
                )
                self.assertIn("確認済みの解答は815", result.patterns[0].explanation)
                self.assertEqual(data.confirmed_questions[0].grading, "incorrect")

    def test_transcription_rejects_incomplete_incorrect_or_matching_work(self):
        correct_process = "8+7=15、6+5+1=12、3+4+1=8"
        for problem, process, answer in (
            ("368+457の筆算", "1", "815"),
            ("368+457の筆算", "8+7=15、6+5=11、3+4=7", "715"),
            ("368+457の筆算", "8+7=14、6+5+1=12、3+4+1=8", "814"),
            ("368+457の筆算", correct_process, "825"),
            ("368+457の筆算", "6+5+1=12、3+4+1=8", "815"),
            ("368+457の筆算", "9+6=15、9+3=12、7+1=8", "815"),
            ("368+457の筆算", correct_process, "なし"),
            ("368-457の筆算", correct_process, "815"),
            ("368+457+1の筆算", correct_process, "815"),
        ):
            with self.subTest(problem=problem, process=process, answer=answer):
                data = make_input(
                    problem_text=problem,
                    student_answer=answer,
                    calculation_process=process,
                )
                result = run_stage_b(
                    data,
                    UNITS,
                    client_for(
                        code="addition_subtraction_written",
                        patterns=[
                            pattern(
                                "careless_mistake",
                                process,
                                pattern="答えの書き写し間違い",
                            )
                        ],
                    ),
                )
                self.assertEqual(result.patterns[0].cause_type, "undetermined")
                self.assertIn("判定困難", result.patterns[0].explanation)
                self.assertEqual(data.confirmed_questions[0].grading, "incorrect")

    def test_verified_transcription_handles_carry_overflow_and_operator_variants(self):
        for problem, process, answer, correct in (
            ("99+1の筆算", "9+1=10、9+0+1=10", "110", 100),
            (
                "368＋457 の筆算",
                "8＋7＝15、6＋5＋1＝12、3＋4＋1＝8",
                "815",
                825,
            ),
        ):
            with self.subTest(problem=problem):
                result = run_stage_b(
                    make_input(
                        problem_text=problem,
                        student_answer=answer,
                        calculation_process=process,
                    ),
                    UNITS,
                    client_for(
                        code="addition_subtraction_written",
                        patterns=[
                            pattern(
                                "careless_mistake", process, pattern="答えの転記ミス"
                            )
                        ],
                    ),
                )
                self.assertEqual(result.patterns[0].cause_type, "careless_mistake")
                self.assertIn(f"答えは{correct}", result.patterns[0].explanation)

    def test_written_transcription_requires_quoted_process_evidence(self):
        process = "8+7=15、6+5+1=12、3+4+1=8"
        for calculation, evidence in (
            (None, process),
            (process, None),
            (process, "8+7=15"),
            (process, "8+7=14"),
            (process, "815"),
        ):
            with self.subTest(calculation=calculation, evidence=evidence):
                result = run_stage_b(
                    make_input(
                        problem_text="368+457の筆算",
                        student_answer="815",
                        calculation_process=calculation,
                    ),
                    UNITS,
                    client_for(
                        code="addition_subtraction_written",
                        patterns=[
                            pattern(
                                "careless_mistake",
                                evidence,
                                pattern="答えの書き写し間違い",
                            )
                        ],
                    ),
                )
                self.assertEqual(result.patterns[0].cause_type, "undetermined")
                self.assertIn("判定困難", result.patterns[0].explanation)

    def test_numeric_evidence_alone_does_not_identify_written_error_cause(self):
        process = "8+7=15、6+5+1=12、3+4+1=8"
        for cause, title in (
            ("careless_mistake", "計算手順の誤り"),
            ("possible_understanding_gap", "答えの書き写し間違い"),
        ):
            with self.subTest(cause=cause, title=title):
                result = run_stage_b(
                    make_input(
                        problem_text="368+457の筆算",
                        student_answer="815",
                        calculation_process=process,
                    ),
                    UNITS,
                    client_for(
                        code="addition_subtraction_written",
                        patterns=[pattern(cause, process, pattern=title)],
                    ),
                )
                self.assertEqual(result.patterns[0].cause_type, "undetermined")
                self.assertIn("判定困難", result.patterns[0].explanation)
                self.assertNotIn("計算誤り", result.patterns[0].explanation)

    def test_pattern_names_do_not_preserve_cause_assessments(self):
        for title in (
            "わり算を理解できていません",
            "理解不足の可能性",
            "ケアレスミスです",
            "うっかりミス",
            "注意力が不足しています",
            "集中できていません",
            "わり算が苦手",
            "知識不足",
            "練習不足",
            "時間不足",
            "時間切れ",
            "時間が足りませんでした",
            "わかっていません",
            "分かりません",
            "分からない",
        ):
            for cause in ("undetermined", "possible_understanding_gap"):
                with self.subTest(title=title, cause=cause):
                    result = run_stage_b(
                        make_input(),
                        UNITS,
                        client_for(patterns=[pattern(cause, pattern=title)]),
                    )
                    self.assertEqual(result.patterns[0].pattern, "判定困難")
                    self.assertEqual(result.patterns[0].cause_type, "undetermined")

    def test_specific_error_patterns_remain_when_cause_is_undetermined(self):
        for name, code, title in (
            ("carry", "addition_subtraction_written", "繰り上がりの反映漏れ"),
            ("carry", "addition_subtraction_written", "繰り上がりの加え忘れ"),
            ("remainder", "division", "あまりの計算ミス"),
        ):
            with self.subTest(title=title):
                case = next(case for case in CASES if case[0] == name)
                result = run_stage_b(
                    make_input(case),
                    UNITS,
                    client_for(code=code, patterns=[pattern(pattern=title)]),
                )
                self.assertEqual(result.patterns[0].pattern, title)
                self.assertEqual(result.patterns[0].cause_type, "undetermined")
                self.assertEqual(result.patterns[0].question_numbers, ["1:1(1)"])

    def test_verification_requires_specific_patterns_and_optional_review(
        self,
    ):
        spec = importlib.util.spec_from_file_location(
            "verify_stage_b",
            Path(__file__).resolve().parents[2] / "scripts/verify_stage_b.py",
        )
        script = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(script)
        for name, code, title, expected in (
            ("carry", "addition_subtraction_written", "判定困難", 1),
            ("carry", "addition_subtraction_written", "繰り上がりの反映漏れ", 0),
            ("remainder", "division", "判定困難", 1),
            ("remainder", "division", "商の計算ミス", 1),
            ("remainder", "division", "あまりの計算ミス", 0),
        ):
            case = next(case for case in CASES if case[0] == name)
            result = run_stage_b(
                make_input(case),
                UNITS,
                client_for(
                    code=code,
                    patterns=[pattern(pattern=title)],
                ),
            )
            for review in (False, True):
                output = io.StringIO()
                argv = ["verify_stage_b.py"] + (["--review"] if review else [])
                with (
                    patch.object(script, "CASES", [case]),
                    patch.object(script, "OpenRouterClient", return_value=Mock()),
                    patch.object(script, "run_stage_b", return_value=result),
                    patch.object(sys, "argv", argv),
                    contextlib.redirect_stdout(output),
                ):
                    self.assertEqual(script.main(), expected)
                self.assertEqual("explanation=" in output.getvalue(), review)

    def test_transcription_verification_requires_pattern_cause_and_safe_explanation(
        self,
    ):
        spec = importlib.util.spec_from_file_location(
            "verify_stage_b",
            Path(__file__).resolve().parents[2] / "scripts/verify_stage_b.py",
        )
        script = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(script)
        case = next(case for case in CASES if case[0] == "transcription")
        result = run_stage_b(
            make_input(case),
            UNITS,
            client_for(
                code=case[5],
                patterns=[
                    pattern("careless_mistake", case[3], pattern="答えの書き写し間違い")
                ],
            ),
        )
        variants = [("valid", result, 0)]
        for changes in (
            {"cause_type": CauseType.UNDETERMINED},
            {"cause_type": CauseType.POSSIBLE_UNDERSTANDING_GAP},
            {"pattern": "判定困難"},
            {"pattern": "繰り上がりの反映漏れ"},
            {"pattern": "書き写し"},
            {"question_numbers": ["1:1(2)"]},
            {"question_numbers": ["1:1(1)", "1:1(2)"]},
            {"explanation": "ケアレスミスです。"},
            {
                "explanation": "ケアレスミスです。ケアレスミスの可能性があります。"
                "原因は断定できません。"
            },
            {"explanation": "原因は断定できません。"},
            {"explanation": "ケアレスミスの可能性があります。"},
        ):
            invalid = result.model_copy(
                update={"patterns": [result.patterns[0].model_copy(update=changes)]}
            )
            variants.append((str(changes), invalid, 1))
        invalid_pattern = result.patterns[0].model_copy(
            update={"cause_type": CauseType.UNDETERMINED}
        )
        for patterns in (None, [], [result.patterns[0], invalid_pattern]):
            variants.append(
                (
                    "invalid patterns",
                    result.model_copy(update={"patterns": patterns}),
                    1,
                )
            )
        variants.append(
            (
                "wrong unit",
                result.model_copy(update={"unit": UNITS[0]}),
                1,
            )
        )
        for name, candidate, expected in variants:
            for review in (False, True):
                with self.subTest(name=name, review=review):
                    output = io.StringIO()
                    argv = ["verify_stage_b.py"] + (["--review"] if review else [])
                    with (
                        patch.object(script, "CASES", [case]),
                        patch.object(script, "OpenRouterClient", return_value=Mock()),
                        patch.object(script, "run_stage_b", return_value=candidate),
                        patch.object(sys, "argv", argv),
                        contextlib.redirect_stdout(output),
                    ):
                        self.assertEqual(script.main(), expected)
                    self.assertIn(
                        f"transcription: {'PASS' if expected == 0 else 'FAIL'}",
                        output.getvalue(),
                    )
                    self.assertEqual(
                        "explanation=" in output.getvalue(),
                        review and bool(candidate.patterns),
                    )

    def test_remainder_answer_alone_cannot_identify_cause(self):
        for cause in ("possible_understanding_gap", "careless_mistake"):
            with self.subTest(cause=cause):
                result = run_stage_b(
                    make_input(),
                    UNITS,
                    client_for(patterns=[pattern(cause, "3あまり3")]),
                )
                self.assertEqual(result.patterns[0].pattern, "あまりの計算ミス")
                self.assertEqual(result.patterns[0].cause_type, "undetermined")
                self.assertIn("区別できません", result.patterns[0].explanation)

    def test_carry_error_does_not_identify_its_cause(self):
        case = next(case for case in CASES if case[0] == "carry")
        for cause in ("possible_understanding_gap", "careless_mistake"):
            for title in ("繰り上がりの反映漏れ", "計算手順の誤り"):
                with self.subTest(cause=cause, title=title):
                    client = client_for(
                        code="addition_subtraction_written",
                        patterns=[pattern(cause, case[3], pattern=title)],
                    )
                    result = run_stage_b(make_input(case), UNITS, client)
                    self.assertEqual(result.patterns[0].pattern, title)
                    self.assertEqual(result.patterns[0].cause_type, "undetermined")
                    self.assertEqual(result.patterns[0].question_numbers, ["1:1(1)"])
                    self.assertIn("区別できません", result.patterns[0].explanation)

    def test_invalid_ai_outputs_fail_without_exposing_content(self):
        for output in (
            {},
            {"choices": []},
            {"choices": [{"message": {"content": "secret"}}]},
            {"choices": [{"message": {"content": "{}"}}]},
        ):
            client = Mock(spec=OpenRouterClient)
            client.create_chat_completion.return_value = output
            with self.assertRaises(StageBInvalidResponseError) as caught:
                run_stage_b(make_input(), UNITS, client)
            self.assertNotIn("secret", str(caught.exception))

    def test_unknown_master_code_and_invalid_pattern_references_fail(self):
        clients = [client_for(code="fraction"), client_for("unsupported", "division")]
        clients += [
            client_for(patterns=[pattern(**change)])
            for change in (
                {"question_ids": ["missing"]},
                {"cause_type": "understanding_gap"},
                {"pattern": " "},
                {"question_ids": []},
            )
        ]
        for client in clients:
            with self.assertRaises(StageBInvalidResponseError):
                run_stage_b(make_input(), UNITS, client)

    def test_nonblank_classified_as_blank_does_not_discard_other_results(self):
        for answer in ("なし", "未記入", "3あまり3"):
            with self.subTest(answer=answer):
                data = make_input(student_answer=answer)
                data.confirmed_questions.append(
                    make_input(
                        question_id="q2", question_number="1(2)"
                    ).confirmed_questions[0]
                )
                client = client_for(
                    patterns=[
                        pattern("blank", pattern="空欄", explanation="解答が空欄です"),
                        pattern(question_ids=["q2"]),
                    ]
                )
                result = run_stage_b(data, UNITS, client)
                self.assertEqual(len(result.patterns), 2)
                self.assertEqual(result.patterns[0].pattern, "判定困難")
                self.assertEqual(result.patterns[0].cause_type, "undetermined")
                self.assertNotIn("空欄", result.patterns[0].explanation)
                self.assertEqual(result.patterns[0].question_numbers, ["1:1(1)"])
                self.assertEqual(result.patterns[1].pattern, "あまりの計算ミス")
                self.assertEqual(result.patterns[1].question_numbers, ["1:1(2)"])
                self.assertEqual(client.create_chat_completion.call_count, 2)
                self.assertEqual(data.confirmed_questions[0].student_answer, answer)

    def test_correct_question_references_are_skipped(self):
        for outputs in (
            [pattern(question_ids=["q2", "q1"])],
            [pattern(question_ids=["q2"]), pattern()],
        ):
            with self.subTest(outputs=outputs):
                data = make_input()
                data.confirmed_questions.append(
                    make_input(
                        question_id="q2", question_number="1(2)", grading="correct"
                    ).confirmed_questions[0]
                )
                client = client_for(patterns=outputs)
                result = run_stage_b(data, UNITS, client)
                self.assertEqual(len(result.patterns), 1)
                self.assertEqual(result.patterns[0].question_numbers, ["1:1(1)"])
                self.assertEqual(result.patterns[0].pattern, "あまりの計算ミス")
                self.assertEqual(client.create_chat_completion.call_count, 2)

    def test_only_correct_references_return_no_patterns(self):
        data = make_input()
        data.confirmed_questions.append(
            make_input(question_id="q2", grading="correct").confirmed_questions[0]
        )
        result = run_stage_b(
            data, UNITS, client_for(patterns=[pattern(question_ids=["q2"])])
        )
        self.assertEqual(result.unit_status, "supported")
        self.assertEqual(result.patterns, [])

    def test_actual_blank_is_still_detected_with_invalid_blank_classification(self):
        data = make_input(student_answer="")
        data.confirmed_questions.append(
            make_input(
                question_id="q2", question_number="1(2)", student_answer="なし"
            ).confirmed_questions[0]
        )
        result = run_stage_b(
            data,
            UNITS,
            client_for(patterns=[pattern("blank", question_ids=["q1", "q2"])]),
        )
        self.assertEqual(len(result.patterns), 2)
        by_number = {p.question_numbers[0]: p for p in result.patterns}
        self.assertEqual(by_number["1:1(1)"].cause_type, "blank")
        self.assertEqual(by_number["1:1(2)"].cause_type, "undetermined")

    def test_unknown_id_still_fails_when_mixed_with_correct_and_incorrect_ids(self):
        data = make_input()
        data.confirmed_questions.append(
            make_input(question_id="q2", grading="correct").confirmed_questions[0]
        )
        with self.assertRaises(StageBInvalidResponseError):
            run_stage_b(
                data,
                UNITS,
                client_for(patterns=[pattern(question_ids=["q2", "q1", "missing"])]),
            )

    def test_unconfirmed_or_image_input_is_rejected(self):
        for change in (
            {"grading": "unknown"},
            {"student_answer": None},
            {"image_index": 3},
            {"image_url": "image"},
            {"question_id": " "},
        ):
            with self.assertRaises(ValidationError):
                make_input(**change)

    def test_duplicate_input_ids_and_missing_pattern_fields_fail(self):
        data = make_input().model_dump()
        data["confirmed_questions"] *= 2
        with self.assertRaises(ValidationError):
            type(make_input()).model_validate(data)
        incomplete = pattern()
        del incomplete["evidence"]
        with self.assertRaises(StageBInvalidResponseError):
            run_stage_b(make_input(), UNITS, client_for(patterns=[incomplete]))

    def test_transport_errors_are_not_reclassified_as_unit_undetermined(self):
        client = Mock(spec=OpenRouterClient)
        client.create_chat_completion.side_effect = OpenRouterError("connection failed")
        with self.assertRaises(OpenRouterError):
            run_stage_b(make_input(), UNITS, client)
