"""Comment validation and orchestration using synthetic data and mocked AI."""

import json
import unittest
from unittest.mock import Mock

from pydantic import ValidationError
from stage_b_cases import UNITS, make_input

from app.features.ai_analysis.clients.openrouter import (
    OpenRouterError,
    OpenRouterTimeoutError,
)
from app.features.ai_analysis.prompts.comment import COMMENT_PROMPT
from app.features.ai_analysis.schemas import (
    AnalysisComment,
    AnalysisPattern,
    StageBResult,
)
from app.features.ai_analysis.service import (
    StageBInvalidResponseError,
    generate_comment,
    run_stage_b,
)

COMMENT = {
    "comment_title": "あまりを一緒に確認してみましょう",
    "comment_body": (
        "テストに取り組んだお子さんも、確認された保護者の方もお疲れさまです。"
        "今回は、わり算のあまりの計算に間違いが見られました。"
        "この答案だけでは理由までは分かりませんので、焦らず振り返ってみましょう。"
        "問1の割る数と商を掛けて、元の数から引く手順を一緒に確認してみませんか。"
        "あまりが割る数より小さいかも確かめてみるとよさそうです。"
        "一度に全部を直そうとせず、一問ずつ、親子のペースで取り組んでいきましょう。"
    ),
}


def completion(value):
    return {
        "choices": [{"message": {"content": json.dumps(value, ensure_ascii=False)}}]
    }


def supported_result(patterns=None):
    return StageBResult(
        unit_status="supported",
        unit=UNITS[0],
        unit_is_estimated=True,
        patterns=[] if patterns is None else patterns,
    )


class CommentTests(unittest.TestCase):
    def test_schema_boundaries_and_whitespace(self):
        for title_length, body_length in ((1, 150), (60, 800)):
            comment = AnalysisComment(
                comment_title=" " + "あ" * title_length + " ",
                comment_body="\n" + "あ" * body_length + "\n",
            )
            self.assertEqual(len(comment.comment_title), title_length)
            self.assertEqual(len(comment.comment_body), body_length)
        for invalid in (
            {"comment_title": " "},
            {"comment_title": "あ" * 61},
            {"comment_body": "あ" * 149},
            {"comment_body": "あ" * 801},
            {"comment_body": None},
            {"comment_title": 42},
            {"extra": "unexpected"},
        ):
            with self.subTest(invalid=invalid), self.assertRaises(ValidationError):
                AnalysisComment.model_validate({**COMMENT, **invalid})
        for missing in ("comment_title", "comment_body"):
            with self.subTest(missing=missing), self.assertRaises(ValidationError):
                AnalysisComment.model_validate(
                    {key: value for key, value in COMMENT.items() if key != missing}
                )

    def test_validated_causes_and_confirmed_facts_reach_comment_generation(self):
        for cause in (
            "blank",
            "careless_mistake",
            "possible_understanding_gap",
            "undetermined",
        ):
            with self.subTest(cause=cause):
                data = make_input(student_answer="" if cause == "blank" else "3あまり3")
                result = supported_result(
                    [
                        AnalysisPattern(
                            pattern="あまりの確認",
                            cause_type=cause,
                            question_numbers=["1:1(1)"],
                            explanation="原因は断定できません。",
                        )
                    ]
                )
                client = Mock()
                client.create_chat_completion.return_value = completion(COMMENT)
                self.assertEqual(
                    generate_comment(data, result, client).model_dump(), COMMENT
                )
                messages = client.create_chat_completion.call_args.args[0]
                self.assertEqual(
                    messages[0], {"role": "system", "content": COMMENT_PROMPT}
                )
                payload = json.loads(messages[1]["content"])
                self.assertEqual(payload["patterns"][0]["cause_type"], cause)
                self.assertEqual(
                    payload["confirmed_questions"],
                    data.model_dump(mode="json")["confirmed_questions"],
                )
                self.assertEqual(
                    set(payload), {"confirmed_questions", "unit", "patterns"}
                )

    def test_all_correct_still_generates_a_comment(self):
        client = Mock()
        client.create_chat_completion.side_effect = [
            completion({"unit_status": "supported", "unit_code": "division"}),
            completion(COMMENT),
        ]
        data = make_input(grading="correct")
        result = run_stage_b(data, UNITS, client)
        generate_comment(data, result, client)
        self.assertEqual(client.create_chat_completion.call_count, 2)
        payload = json.loads(
            client.create_chat_completion.call_args.args[0][1]["content"]
        )
        self.assertEqual(payload["patterns"], [])
        self.assertEqual(payload["confirmed_questions"][0]["grading"], "correct")

    def test_invalid_comment_retries_without_repeating_analysis(self):
        for invalid in (
            {},
            {"choices": []},
            completion({}),
            completion("private output"),
            {"choices": [{"message": {"content": "not-json"}}]},
        ):
            with self.subTest(invalid=invalid):
                client = Mock()
                client.create_chat_completion.side_effect = [
                    invalid,
                    completion(COMMENT),
                ]
                comment = generate_comment(make_input(), supported_result(), client)
                self.assertEqual(comment.model_dump(), COMMENT)
                calls = client.create_chat_completion.call_args_list
                self.assertEqual(len(calls), 2)
                self.assertEqual(calls[0], calls[1])

    def test_two_invalid_comments_fail_without_exposing_output(self):
        client = Mock()
        client.create_chat_completion.return_value = completion(
            {"private output": "secret"}
        )
        with self.assertRaises(StageBInvalidResponseError) as caught:
            generate_comment(make_input(), supported_result(), client)
        self.assertEqual(str(caught.exception), "Invalid comment response.")
        self.assertIsNone(caught.exception.__cause__)
        self.assertEqual(client.create_chat_completion.call_count, 2)

    def test_comment_retry_keeps_successful_unit_and_pattern_results(self):
        client = Mock()
        client.create_chat_completion.side_effect = [
            completion({"unit_status": "supported", "unit_code": "division"}),
            completion({"patterns": []}),
            completion({}),
            completion(COMMENT),
        ]
        data = make_input(student_answer="")
        result = run_stage_b(data, UNITS, client)
        generate_comment(data, result, client)
        calls = client.create_chat_completion.call_args_list
        self.assertEqual(len(calls), 4)
        self.assertEqual(calls[2], calls[3])
        payload = json.loads(calls[2].args[0][1]["content"])
        self.assertEqual(payload["patterns"][0]["cause_type"], "blank")

    def test_transport_errors_are_not_retried(self):
        for error in (OpenRouterError, OpenRouterTimeoutError):
            client = Mock()
            client.create_chat_completion.side_effect = error("private output")
            with self.assertRaises(error):
                generate_comment(make_input(), supported_result(), client)
            client.create_chat_completion.assert_called_once()

    def test_incomplete_or_non_supported_analysis_never_calls_ai(self):
        for result in (
            StageBResult(
                unit_status="unsupported",
                unit=None,
                unit_is_estimated=False,
                patterns=None,
            ),
            StageBResult(
                unit_status="undetermined",
                unit=None,
                unit_is_estimated=False,
                patterns=None,
            ),
            supported_result().model_copy(update={"patterns": None}),
            supported_result().model_copy(update={"unit": None}),
        ):
            client = Mock()
            with self.assertRaises(StageBInvalidResponseError):
                generate_comment(make_input(), result, client)
            client.create_chat_completion.assert_not_called()
