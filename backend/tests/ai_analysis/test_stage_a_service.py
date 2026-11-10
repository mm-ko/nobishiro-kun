import json
import unittest

from app.features.ai_analysis.clients.openrouter import OpenRouterTimeoutError
from app.features.ai_analysis.prompts.stage_a import STAGE_A_PROMPT
from app.features.ai_analysis.schemas import StageAInputImage
from app.features.ai_analysis.service import (
    StageAImageUnreadableError,
    StageAInvalidResponseError,
    run_stage_a,
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


def make_response(questions=None, **overrides):
    output = {
        "read_score": None,
        "read_unit_name": None,
        "questions": [make_question()] if questions is None else questions,
    }
    output.update(overrides)
    content = json.dumps(output, ensure_ascii=False)
    return {"choices": [{"message": {"content": content}}]}


def make_image(content=b"image-1"):
    return StageAInputImage(content=content, media_type="image/png")


class FakeOpenRouterClient:
    """Returns the prepared responses in order instead of calling OpenRouter."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.requests = []

    def create_chat_completion(self, messages, parameters=None):
        self.requests.append({"messages": messages, "parameters": parameters})
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class RunStageATests(unittest.TestCase):
    def test_one_image_returns_questions_with_backend_ids(self):
        client = FakeOpenRouterClient(
            [make_response(read_score=80, read_unit_name="あまりのあるわり算")]
        )

        extraction = run_stage_a([make_image()], client)

        self.assertEqual(extraction.read_score, 80)
        self.assertEqual(extraction.read_unit_name, "あまりのあるわり算")
        self.assertEqual(len(extraction.questions), 1)
        question = extraction.questions[0]
        self.assertEqual(question.question_id, "q1")
        self.assertEqual(question.image_index, 1)
        self.assertEqual(question.question_number, "1(1)")
        self.assertEqual(question.student_answer, "3あまり3")

    def test_two_images_are_combined_with_serial_question_ids(self):
        # 表裏で同じ問題番号が出ても、question_id は重ならない。
        client = FakeOpenRouterClient(
            [
                make_response([make_question(), make_question(question_number="1(2)")]),
                make_response([make_question()]),
            ]
        )

        extraction = run_stage_a([make_image(), make_image(b"image-2")], client)

        self.assertEqual(
            [(q.question_id, q.image_index) for q in extraction.questions],
            [("q1", 1), ("q2", 1), ("q3", 2)],
        )
        self.assertEqual(len(client.requests), 2)

    def test_each_image_is_sent_in_its_own_request(self):
        client = FakeOpenRouterClient([make_response(), make_response()])

        run_stage_a([make_image(b"front"), make_image(b"back")], client)

        image_urls = []
        for request in client.requests:
            content = request["messages"][0]["content"]
            self.assertEqual(content[0], {"type": "text", "text": STAGE_A_PROMPT})
            image_urls.append(content[1]["image_url"]["url"])
            self.assertEqual(request["parameters"], {"temperature": 0})
        # b"front" と b"back" を base64 にした値。
        self.assertEqual(
            image_urls,
            ["data:image/png;base64,ZnJvbnQ=", "data:image/png;base64,YmFjaw=="],
        )

    def test_invalid_output_is_retried_once(self):
        client = FakeOpenRouterClient(
            [
                {"choices": [{"message": {"content": "読み取れませんでした"}}]},
                make_response(),
            ]
        )

        extraction = run_stage_a([make_image()], client)

        self.assertEqual(len(extraction.questions), 1)
        self.assertEqual(len(client.requests), 2)

    def test_invalid_output_twice_raises_error(self):
        client = FakeOpenRouterClient(
            [
                {"choices": [{"message": {"content": "読み取れませんでした"}}]},
                {"choices": [{"message": {"content": "[]"}}]},
            ]
        )

        with self.assertRaises(StageAInvalidResponseError):
            run_stage_a([make_image()], client)
        self.assertEqual(len(client.requests), 2)

    def test_response_without_content_is_retried(self):
        client = FakeOpenRouterClient(
            [{"choices": [{"message": {"content": None}}]}, make_response()]
        )

        extraction = run_stage_a([make_image()], client)

        self.assertEqual(len(extraction.questions), 1)
        self.assertEqual(len(client.requests), 2)

    def test_retry_is_counted_for_each_image(self):
        # 1枚目のやり直しが、2枚目のやり直しの回数を減らさない。
        invalid_response = {"choices": []}
        client = FakeOpenRouterClient(
            [invalid_response, make_response(), invalid_response, make_response()]
        )

        extraction = run_stage_a([make_image(), make_image(b"image-2")], client)

        self.assertEqual(len(extraction.questions), 2)
        self.assertEqual(len(client.requests), 4)

    def test_no_questions_in_any_image_raises_unreadable_error(self):
        client = FakeOpenRouterClient(
            [make_response([], read_score=80), make_response([])]
        )

        with self.assertRaises(StageAImageUnreadableError):
            run_stage_a([make_image(), make_image(b"image-2")], client)

    def test_openrouter_error_is_not_retried(self):
        client = FakeOpenRouterClient(
            [OpenRouterTimeoutError("OpenRouter request timed out"), make_response()]
        )

        with self.assertRaises(OpenRouterTimeoutError):
            run_stage_a([make_image()], client)
        self.assertEqual(len(client.requests), 1)

    def test_different_unit_names_become_none(self):
        client = FakeOpenRouterClient(
            [
                make_response(read_unit_name="わり算"),
                make_response(read_unit_name="ひっ算"),
            ]
        )

        extraction = run_stage_a([make_image(), make_image(b"image-2")], client)

        self.assertIsNone(extraction.read_unit_name)

    def test_score_read_from_only_one_image_is_used(self):
        client = FakeOpenRouterClient(
            [
                make_response(read_score=2),
                make_response(read_score=None),
            ]
        )

        extraction = run_stage_a([make_image(), make_image(b"image-2")], client)

        self.assertEqual(extraction.read_score, 2)


if __name__ == "__main__":
    unittest.main()
