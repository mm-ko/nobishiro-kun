import unittest
from decimal import Decimal

from sqlalchemy import Column, Integer, MetaData, Numeric, String, Table
from sqlmodel import Session, create_engine

from app.features.learning_history.repository import list_unit_rankings


class UnitRankingRepositoryTests(unittest.TestCase):
    def setUp(self):
        # PostgreSQL固有の保存項目を除いた一時テーブルで、集計クエリを実行する。
        self.engine = create_engine("sqlite://")
        self.addCleanup(self.engine.dispose)
        metadata = MetaData()
        self.units = Table(
            "units",
            metadata,
            Column("id", Integer, primary_key=True),
            Column("code", String),
            Column("name", String),
        )
        self.records = Table(
            "analysis_records",
            metadata,
            Column("id", Integer, primary_key=True),
            Column("user_id", Integer),
            Column("unit_id", Integer),
            Column("score_rate", Numeric(5, 2)),
        )
        metadata.create_all(self.engine)
        with self.engine.begin() as connection:
            connection.execute(
                self.units.insert(),
                [
                    {"id": 1, "code": "division", "name": "わり算"},
                    {"id": 2, "code": "addition_subtraction_written", "name": "筆算"},
                    {"id": 3, "code": "fractions", "name": "分数"},
                ],
            )
        self.session = self.enterContext(Session(self.engine))

    def add_records(self, *rows: tuple[int, int, str]) -> None:
        with self.engine.begin() as connection:
            connection.execute(
                self.records.insert(),
                [
                    {"user_id": user_id, "unit_id": unit_id, "score_rate": rate}
                    for user_id, unit_id, rate in rows
                ],
            )

    def test_rounded_ties_share_rank_and_next_rank_is_skipped(self):
        # DB設計の例：70.04％と70.03％はどちらも70.0％で1位、83.33％は3位。
        self.add_records((7, 1, "70.04"), (7, 2, "70.03"), (7, 3, "83.33"))

        rows = list_unit_rankings(self.session, 7)

        self.assertEqual(
            [(row[0], row[1]) for row in rows],
            [
                (1, "addition_subtraction_written"),  # 同順位の中は単元コード順
                (1, "division"),
                (3, "fractions"),
            ],
        )
        self.assertEqual(
            [Decimal(str(row[3])) for row in rows],
            [Decimal("70.0"), Decimal("70.0"), Decimal("83.3")],
        )

    def test_average_uses_each_score_rate_even_when_max_scores_differ(self):
        # 40/50点（80％）と90/150点（60％）の平均は70.0％。
        # 得点の合計÷満点の合計（65％）ではない。
        self.add_records((7, 1, "80.00"), (7, 1, "60.00"))

        rows = list_unit_rankings(self.session, 7)

        self.assertEqual(len(rows), 1)
        self.assertEqual(Decimal(str(rows[0][3])), Decimal("70.0"))
        self.assertEqual(rows[0][4], 2)

    def test_only_own_records_are_counted_and_units_without_records_are_excluded(self):
        self.add_records((7, 1, "50.00"), (8, 1, "10.00"), (8, 2, "20.00"))

        rows = list_unit_rankings(self.session, 7)

        self.assertEqual(
            [(row[0], row[1], row[4]) for row in rows], [(1, "division", 1)]
        )
        self.assertEqual(Decimal(str(rows[0][3])), Decimal("50.0"))

    def test_returns_empty_when_user_has_no_records(self):
        self.add_records((8, 1, "10.00"))
        self.assertEqual(list_unit_rankings(self.session, 7), [])


if __name__ == "__main__":
    unittest.main()
