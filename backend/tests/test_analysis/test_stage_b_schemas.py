import unittest

from pydantic import ValidationError

from app.features.test_analysis.schemas import StageBRequest


class StageBRequestTests(unittest.TestCase):
    def setUp(self):
        self.question = dict(
            question_id="q1",
            image_index=1,
            question_number=None,
            problem_text="17÷5",
            student_answer="",
            calculation_process=None,
            grading="incorrect",
        )
        self.body = dict(
            score=0,
            max_score=100,
            read_unit_name=None,
            confirmed_questions=[self.question],
        )

    def test_score_boundaries_and_blank_answer_are_accepted(self):
        for score in (0, 100):
            request = StageBRequest.model_validate(self.body | dict(score=score))
            self.assertEqual(request.score, score)
            self.assertEqual(request.confirmed_questions[0].student_answer, "")

    def test_invalid_scores_extra_fields_and_duplicate_questions_are_rejected(self):
        for update in [
            dict(score=-1),
            dict(score=101),
            dict(max_score=0),
            dict(score="80"),
            dict(score=True),
            dict(max_score=1.5),
            dict(images=[]),
            dict(memo="test"),
            dict(user_id=8),
            dict(confirmed_questions=[]),
            dict(confirmed_questions=[self.question, self.question]),
        ]:
            with self.subTest(update=update), self.assertRaises(ValidationError):
                StageBRequest.model_validate(self.body | update)

    def test_unconfirmed_questions_and_images_are_rejected(self):
        for update in [
            dict(grading="unknown"),
            dict(student_answer=None),
            dict(image_index=3),
            dict(images=[]),
            dict(problem_text=""),
            dict(question_id=""),
        ]:
            with self.subTest(update=update), self.assertRaises(ValidationError):
                StageBRequest.model_validate(
                    self.body | dict(confirmed_questions=[self.question | update])
                )

    def test_required_fields_cannot_be_omitted(self):
        for key in self.body:
            with self.subTest(key=key), self.assertRaises(ValidationError):
                StageBRequest.model_validate(
                    {k: v for k, v in self.body.items() if k != key}
                )
