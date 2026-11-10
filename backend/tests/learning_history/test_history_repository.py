import unittest
from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, MetaData, String, Table
from sqlmodel import Session, create_engine

from app.features.learning_history.repository import list_analysis_records


class HistoryRepositoryTests(unittest.TestCase):
    def setUp(self):
        # PostgreSQL固有の保存項目を除いた一時テーブルで、取得クエリを実行する。
        self.engine = create_engine("sqlite://")
        self.addCleanup(self.engine.dispose)
        metadata = MetaData()
        units = Table(
            "units",
            metadata,
            Column("id", Integer, primary_key=True),
            Column("code", String),
            Column("name", String),
        )
        records = Table(
            "analysis_records",
            metadata,
            Column("id", Integer, primary_key=True),
            Column("user_id", Integer),
            Column("unit_id", Integer),
            Column("recorded_at", DateTime),
            Column("score", Integer),
            Column("max_score", Integer),
        )
        metadata.create_all(self.engine)
        with self.engine.begin() as connection:
            connection.execute(
                units.insert(),
                [
                    {"id": 1, "code": "division", "name": "わり算"},
                    {"id": 2, "code": "fractions", "name": "分数"},
                ],
            )
            connection.execute(
                records.insert(),
                [
                    {
                        "id": record_id,
                        "user_id": user_id,
                        "unit_id": unit_id,
                        "recorded_at": datetime(2026, 10, day),
                        "score": score,
                        "max_score": 100,
                    }
                    for record_id, user_id, unit_id, day, score in (
                        (1, 7, 1, 18, 80),
                        (2, 7, 2, 20, 0),
                        (3, 7, 1, 20, 100),
                        (4, 8, 2, 21, 50),
                    )
                ],
            )
        self.session = self.enterContext(Session(self.engine))

    def test_returns_only_own_records_in_date_and_id_descending_order(self):
        rows = list_analysis_records(self.session, 7, 20, 0)
        self.assertEqual([row[0] for row in rows], [3, 2, 1])
        self.assertEqual(rows[0][2:], ("division", "わり算", 100, 100))
        self.assertEqual(rows[1][2:], ("fractions", "分数", 0, 100))
        self.assertEqual(
            [row[0] for row in list_analysis_records(self.session, 8, 20, 0)], [4]
        )

    def test_pagination_applies_after_user_filter_and_order(self):
        rows = list_analysis_records(self.session, 7, 1, 1)
        self.assertEqual([row[0] for row in rows], [2])

    def test_returns_empty_for_unknown_user_or_offset_past_last_record(self):
        self.assertEqual(list_analysis_records(self.session, 999, 20, 0), [])
        self.assertEqual(list_analysis_records(self.session, 7, 20, 3), [])


if __name__ == "__main__":
    unittest.main()
