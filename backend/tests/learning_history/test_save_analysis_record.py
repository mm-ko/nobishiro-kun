import unittest
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import MagicMock
from uuid import uuid4

from app.db.models import AnalysisRecord, AnalysisUsage
from app.features.learning_history import service as history_service
from app.features.usage import service as usage_service


class SaveAnalysisRecordTests(unittest.TestCase):
    def setUp(self):
        # 本物のDBには接続しない。
        self.session = MagicMock()

    def test_record_is_added_without_commit(self):
        history_service.save_analysis(
            self.session,
            user_id=7,
            unit_id=1,
            analysis_usage_id=11,
            score=100,
            max_score=150,
            score_rate=Decimal("66.67"),
            incorrect_question_numbers=["1:1(1)"],
            analysis_result={"patterns": [{"pattern": "計算の確認"}]},
            comment_title="タイトル",
            comment_body="本文",
            recorded_at=datetime(2026, 10, 31, 15, 1, tzinfo=UTC),
        )

        record = self.session.add.call_args.args[0]
        self.assertIsInstance(record, AnalysisRecord)
        self.assertEqual(
            (record.user_id, record.unit_id, record.analysis_usage_id),
            (7, 1, 11),
        )
        self.assertEqual(
            (record.score, record.max_score, record.score_rate),
            (100, 150, Decimal("66.67")),
        )
        self.assertEqual(record.incorrect_question_numbers, ["1:1(1)"])
        self.assertEqual(
            record.analysis_result, {"patterns": [{"pattern": "計算の確認"}]}
        )
        self.assertEqual(
            (record.comment_title, record.comment_body), ("タイトル", "本文")
        )
        self.assertEqual(record.recorded_at, datetime(2026, 10, 31, 15, 1, tzinfo=UTC))
        self.session.add.assert_called_once_with(record)
        self.session.flush.assert_called_once_with()
        # 利用実績と同じトランザクションで確定するため、commitは呼び出し側に任せる。
        self.session.commit.assert_not_called()

    def test_usage_is_added_without_commit_and_returns_its_id(self):
        analysis_request_id = uuid4()

        def assign_id():
            self.session.add.call_args.args[0].id = 11

        self.session.flush.side_effect = assign_id

        counted_at = datetime(2026, 10, 31, 15, 1, tzinfo=UTC)
        usage_id = usage_service.record_usage(
            self.session, 7, analysis_request_id, counted_at
        )

        usage = self.session.add.call_args.args[0]
        self.assertIsInstance(usage, AnalysisUsage)
        self.assertEqual(
            (usage.user_id, usage.analysis_request_id), (7, analysis_request_id)
        )
        self.assertEqual(usage.counted_at, counted_at)
        self.assertEqual(usage_id, 11)
        self.session.commit.assert_not_called()


if __name__ == "__main__":
    unittest.main()
