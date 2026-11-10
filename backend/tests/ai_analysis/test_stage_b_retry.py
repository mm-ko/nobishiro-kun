"""Stage B retries malformed responses, without repeating a successful stage."""

import json
import unittest
from unittest.mock import Mock

from stage_b_cases import UNITS, make_input

from app.features.ai_analysis.clients.openrouter import (
    OpenRouterError,
    OpenRouterTimeoutError,
)
from app.features.ai_analysis.prompts.stage_b import PATTERN_PROMPT, UNIT_PROMPT
from app.features.ai_analysis.service import StageBInvalidResponseError, run_stage_b

UNIT = {"unit_status": "supported", "unit_code": "division"}
PATTERNS = {
    "patterns": [
        {
            "pattern": "あまりの計算ミス",
            "cause_type": "undetermined",
            "question_ids": ["q1"],
            "explanation": "あまりの値に誤りが見られます。",
            "evidence": None,
        }
    ]
}


def client_with(*outputs):
    client = Mock()
    client.create_chat_completion.side_effect = [
        value
        if isinstance(value, Exception)
        else {
            "choices": [
                {
                    "message": {
                        "content": value
                        if isinstance(value, str)
                        else json.dumps(value)
                    }
                }
            ]
        }
        for value in outputs
    ]
    return client


class StageBRetryTests(unittest.TestCase):
    def test_unit_recovers_from_json_or_schema_error(self):
        for invalid in ("synthetic-sensitive-output", {"unit_status": "supported"}):
            with self.subTest(invalid=invalid):
                client = client_with(invalid, UNIT, PATTERNS)
                result = run_stage_b(make_input(), UNITS, client)
                self.assertEqual(result.unit.code, "division")
                calls = client.create_chat_completion.call_args_list
                self.assertEqual(len(calls), 3)
                self.assertEqual(calls[0], calls[1])
                self.assertEqual(calls[0].args[0][0]["content"], UNIT_PROMPT)
                self.assertEqual(calls[2].args[0][0]["content"], PATTERN_PROMPT)

    def test_pattern_recovers_without_repeating_unit(self):
        for invalid in (
            "synthetic-sensitive-output",
            {},
            {"patterns": [{"pattern": "誤り"}]},
        ):
            with self.subTest(invalid=invalid):
                client = client_with(UNIT, invalid, PATTERNS)
                result = run_stage_b(make_input(), UNITS, client)
                self.assertEqual(len(result.patterns), 1)
                self.assertEqual(result.patterns[0].pattern, "あまりの計算ミス")
                self.assertEqual(result.patterns[0].question_numbers, ["1:1(1)"])
                calls = client.create_chat_completion.call_args_list
                self.assertEqual(len(calls), 3)
                self.assertEqual(calls[1], calls[2])
                self.assertEqual(calls[0].args[0][0]["content"], UNIT_PROMPT)
                self.assertEqual(calls[1].args[0][0]["content"], PATTERN_PROMPT)

    def test_each_stage_has_its_own_single_retry(self):
        client = client_with({}, UNIT, {}, PATTERNS)
        run_stage_b(make_input(), UNITS, client)
        calls = client.create_chat_completion.call_args_list
        self.assertEqual(len(calls), 4)
        self.assertEqual(calls[0], calls[1])
        self.assertEqual(calls[2], calls[3])

    def test_unit_stops_after_two_invalid_responses(self):
        for invalid, message in (
            ("synthetic-sensitive-output", "Stage B output is not valid JSON."),
            ({}, "Invalid Stage B unit schema."),
        ):
            with self.subTest(invalid=invalid):
                client = client_with(invalid, invalid, UNIT)
                with self.assertRaises(StageBInvalidResponseError) as caught:
                    run_stage_b(make_input(), UNITS, client)
                self.assertEqual(str(caught.exception), message)
                self.assertEqual(client.create_chat_completion.call_count, 2)

    def test_final_pattern_failure_preserves_safe_diagnostics(self):
        value = {"patterns": [{"synthetic-sensitive-output": "private"}]}
        client = client_with(UNIT, "invalid-json", value, PATTERNS)
        with self.assertRaises(StageBInvalidResponseError) as caught:
            run_stage_b(make_input(), UNITS, client)
        self.assertEqual(client.create_chat_completion.call_count, 3)
        self.assertEqual(str(caught.exception), "Invalid Stage B pattern schema.")
        self.assertIn("patterns.0.evidence:missing", caught.exception.validation_issues)
        self.assertIn(
            "patterns.0.extra_field:extra_forbidden", caught.exception.validation_issues
        )
        self.assertNotIn(
            "synthetic-sensitive-output", str(caught.exception.validation_issues)
        )

    def test_transport_errors_are_not_retried_at_either_stage(self):
        for error_type in (OpenRouterError, OpenRouterTimeoutError):
            for prefix in ([], [{}], [UNIT], [UNIT, {}]):
                with self.subTest(error_type=error_type, prefix=prefix):
                    error = error_type("synthetic-sensitive-output")
                    client = client_with(*prefix, error, PATTERNS)
                    with self.assertRaises(error_type) as caught:
                        run_stage_b(make_input(), UNITS, client)
                    self.assertIs(caught.exception, error)
                    self.assertEqual(
                        client.create_chat_completion.call_count, len(prefix) + 1
                    )

    def test_success_and_early_return_do_not_retry(self):
        for grading, decision, outputs, calls in (
            ("incorrect", UNIT, [PATTERNS], 2),
            ("correct", UNIT, [], 1),
            ("incorrect", {"unit_status": "unsupported", "unit_code": None}, [], 1),
        ):
            with self.subTest(grading=grading, decision=decision):
                client = client_with(decision, *outputs)
                run_stage_b(make_input(grading=grading), UNITS, client)
                self.assertEqual(client.create_chat_completion.call_count, calls)
