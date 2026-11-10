import json
import unittest

from app.features.ai_analysis.schemas import Grading
from app.features.ai_analysis.service import (
    StageAInvalidResponseError,
    parse_stage_a_extraction,
)


def make_question(**overrides):
    question = {
        "question_number": "1(1)",
        "problem_text": "17÷5",
        "student_answer": "3あまり3",
        "calculation_process": None,
        "grading": "incorrect",
    }
    question.update(overrides)
    return question


def make_output(questions=None, **overrides):
    output = {
        "read_score": 80,
        "read_unit_name": "あまりのあるわり算",
        "questions": [make_question()] if questions is None else questions,
    }
    output.update(overrides)
    return json.dumps(output, ensure_ascii=False)


class ParseStageAExtractionTests(unittest.TestCase):
    def test_valid_output_is_returned_as_schema(self):
        extraction = parse_stage_a_extraction(make_output())

        self.assertEqual(extraction.read_score, 80)
        self.assertEqual(extraction.read_unit_name, "あまりのあるわり算")
        self.assertEqual(len(extraction.questions), 1)
        question = extraction.questions[0]
        self.assertEqual(question.question_number, "1(1)")
        self.assertEqual(question.problem_text, "17÷5")
        self.assertEqual(question.student_answer, "3あまり3")
        self.assertIsNone(question.calculation_process)
        self.assertEqual(question.grading, Grading.INCORRECT)

    def test_json_inside_code_block_is_accepted(self):
        content = f"読み取り結果です。\n```json\n{make_output()}\n```"

        extraction = parse_stage_a_extraction(content)

        self.assertEqual(len(extraction.questions), 1)

    def test_blank_answer_and_unreadable_answer_are_kept_distinct(self):
        content = make_output(
            [
                make_question(student_answer=""),
                make_question(student_answer=None),
            ]
        )

        extraction = parse_stage_a_extraction(content)

        self.assertEqual(extraction.questions[0].student_answer, "")
        self.assertIsNone(extraction.questions[1].student_answer)

    def test_empty_optional_text_becomes_none(self):
        content = make_output(
            [make_question(question_number=" ", calculation_process="")],
            read_unit_name="",
        )

        extraction = parse_stage_a_extraction(content)

        self.assertIsNone(extraction.read_unit_name)
        self.assertIsNone(extraction.questions[0].question_number)
        self.assertIsNone(extraction.questions[0].calculation_process)

    def test_numeric_question_number_becomes_text(self):
        extraction = parse_stage_a_extraction(
            make_output([make_question(question_number=3)])
        )

        self.assertEqual(extraction.questions[0].question_number, "3")

    def test_score_that_is_not_a_non_negative_integer_becomes_none(self):
        for read_score in (None, "80点", 4.5, -5, True, "", [80]):
            with self.subTest(read_score=read_score):
                extraction = parse_stage_a_extraction(
                    make_output(read_score=read_score)
                )

                self.assertIsNone(extraction.read_score)

    def test_score_written_as_integer_text_or_float_is_accepted(self):
        for read_score in ("80", 80.0, 0):
            with self.subTest(read_score=read_score):
                extraction = parse_stage_a_extraction(
                    make_output(read_score=read_score)
                )

                self.assertEqual(extraction.read_score, int(read_score))

    def test_grading_and_pattern_analysis_fields_are_dropped(self):
        content = make_output(
            [make_question(is_correct_by_ai=False, mistake_pattern="あまりのミス")],
            unit_estimation="わり算",
        )

        extraction = parse_stage_a_extraction(content)

        dumped = extraction.model_dump()
        self.assertNotIn("unit_estimation", dumped)
        self.assertNotIn("is_correct_by_ai", dumped["questions"][0])
        self.assertNotIn("mistake_pattern", dumped["questions"][0])

    def test_image_without_questions_is_valid(self):
        extraction = parse_stage_a_extraction(make_output([]))

        self.assertEqual(extraction.questions, [])

    def test_output_without_json_raises_error(self):
        with self.assertRaises(StageAInvalidResponseError):
            parse_stage_a_extraction("画像を読み取れませんでした。")

    def test_broken_json_raises_error(self):
        with self.assertRaises(StageAInvalidResponseError):
            parse_stage_a_extraction('{"read_score": 80, "questions": [')

    def test_valid_output_wrapped_in_array_raises_error(self):
        with self.assertRaises(StageAInvalidResponseError):
            parse_stage_a_extraction(f"[{make_output()}]")

    def test_array_without_closing_bracket_raises_error(self):
        with self.assertRaises(StageAInvalidResponseError):
            parse_stage_a_extraction(f"[{make_output()}")

    def test_array_inside_code_block_raises_error(self):
        with self.assertRaises(StageAInvalidResponseError):
            parse_stage_a_extraction(f"```json\n[\n{make_output()}\n]\n```")

    def test_extra_closing_bracket_after_object_raises_error(self):
        with self.assertRaises(StageAInvalidResponseError):
            parse_stage_a_extraction(f"{make_output()}]")

    def test_second_object_after_object_raises_error(self):
        with self.assertRaises(StageAInvalidResponseError):
            parse_stage_a_extraction(f"{make_output()}\n{make_output()}")

    def test_explanation_after_json_is_accepted(self):
        content = f"読み取り結果です。\n{make_output()}\n以上です。"

        extraction = parse_stage_a_extraction(content)

        self.assertEqual(len(extraction.questions), 1)

    def test_missing_required_field_raises_error(self):
        output = json.loads(make_output())
        del output["questions"][0]["grading"]

        with self.assertRaises(StageAInvalidResponseError):
            parse_stage_a_extraction(json.dumps(output))

    def test_unknown_grading_value_raises_error(self):
        with self.assertRaises(StageAInvalidResponseError):
            parse_stage_a_extraction(make_output([make_question(grading="○")]))

    def test_all_supported_grading_values_are_accepted(self):
        for grading in ("correct", "incorrect", "unknown"):
            with self.subTest(grading=grading):
                extraction = parse_stage_a_extraction(
                    make_output([make_question(grading=grading)])
                )
                self.assertEqual(extraction.questions[0].grading, grading)

    def test_null_score_and_answer_are_accepted(self):
        extraction = parse_stage_a_extraction(
            make_output([make_question(student_answer=None)], read_score=None)
        )

        self.assertIsNone(extraction.read_score)
        self.assertIsNone(extraction.questions[0].student_answer)

    def test_missing_fields_in_image_or_question_raise_error(self):
        for location in ("image", "question"):
            original = json.loads(make_output())
            fields = original if location == "image" else original["questions"][0]
            for field in fields:
                with self.subTest(location=location, field=field):
                    output = json.loads(make_output())
                    target = output if location == "image" else output["questions"][0]
                    del target[field]
                    with self.assertRaises(StageAInvalidResponseError):
                        parse_stage_a_extraction(json.dumps(output))

    def test_invalid_question_field_types_raise_error(self):
        for field, value in (
            ("problem_text", 123),
            ("student_answer", ["3"]),
            ("calculation_process", {}),
            ("question_number", True),
            ("grading", None),
            ("grading", 1),
        ):
            with (
                self.subTest(field=field),
                self.assertRaises(StageAInvalidResponseError),
            ):
                parse_stage_a_extraction(make_output([make_question(**{field: value})]))

    def test_empty_problem_text_raises_error(self):
        with self.assertRaises(StageAInvalidResponseError):
            parse_stage_a_extraction(make_output([make_question(problem_text="  ")]))

    def test_error_message_does_not_include_ai_output(self):
        content = make_output(
            [make_question(student_answer="ひみつの解答", grading="まちがい")]
        )

        with self.assertRaises(StageAInvalidResponseError) as context:
            parse_stage_a_extraction(content)

        self.assertNotIn("ひみつの解答", str(context.exception))
        self.assertNotIn("まちがい", str(context.exception))
        self.assertIn("questions.0.grading", str(context.exception))
        self.assertIsNone(context.exception.__cause__)


if __name__ == "__main__":
    unittest.main()
