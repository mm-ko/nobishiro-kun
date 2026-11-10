import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.db.session import DatabaseConfigurationError
from app.features.health.router import router


class HealthRouterTests(unittest.TestCase):
    def setUp(self):
        engine_patch = patch("app.features.health.repository.get_engine")
        self.get_engine = engine_patch.start()
        self.addCleanup(engine_patch.stop)

        session_patch = patch("app.features.health.repository.Session")
        self.session_class = session_patch.start()
        self.addCleanup(session_patch.stop)
        self.session = self.session_class.return_value.__enter__.return_value

        app = FastAPI()
        app.include_router(router)
        self.client = self.enterContext(TestClient(app))

    def assert_unavailable(self, response):
        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.json(), {"status": "error", "database": "unavailable"}
        )
        self.assertNotIn("internal-db-details", response.text)

    def assert_failure_logged(self, exception_type):
        with self.assertLogs("app.features.health.repository", level="WARNING") as logs:
            self.assert_unavailable(self.client.get("/v1/health"))
        self.assertEqual(
            logs.output,
            [
                "WARNING:app.features.health.repository:"
                f"DB health check failed: {exception_type}"
            ],
        )
        self.assertIsNone(logs.records[0].exc_info)
        self.assertIsNone(logs.records[0].stack_info)

    def test_database_query_success_returns_200(self):
        self.session.execute.return_value.scalar_one.return_value = 1

        response = self.client.get("/v1/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok", "database": "ok"})
        self.session_class.assert_called_once_with(self.get_engine.return_value)
        self.assertEqual(str(self.session.execute.call_args.args[0]), "SELECT 1")
        self.session_class.return_value.__exit__.assert_called_once()

    def test_missing_database_configuration_returns_503(self):
        self.get_engine.side_effect = DatabaseConfigurationError("internal-db-details")

        self.assert_failure_logged("DatabaseConfigurationError")
        self.session_class.assert_not_called()

    def test_connection_failure_returns_503_without_internal_details(self):
        self.session_class.return_value.__enter__.side_effect = OperationalError(
            "SELECT 1", {}, Exception("internal-db-details")
        )

        self.assert_failure_logged("OperationalError")
        self.session.execute.assert_not_called()

    def test_query_failure_returns_503_and_closes_session(self):
        self.session.execute.side_effect = OperationalError(
            "SELECT 1", {}, Exception("internal-db-details")
        )

        self.assert_failure_logged("OperationalError")
        self.session_class.return_value.__exit__.assert_called_once()
