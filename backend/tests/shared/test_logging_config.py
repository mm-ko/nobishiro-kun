import logging
import unittest

from app.core.logging import QUIET_LIBRARY_LOGGERS, configure_logging

WATCHED_LOGGERS = ("", "uvicorn.access", *QUIET_LIBRARY_LOGGERS)


class ConfigureLoggingTests(unittest.TestCase):
    def setUp(self):
        # ほかのテストに影響しないよう、変更するログの設定を元に戻す。
        root = logging.getLogger()
        saved_levels = {name: logging.getLogger(name).level for name in WATCHED_LOGGERS}
        saved_handlers = list(root.handlers)

        def restore():
            for name, level in saved_levels.items():
                logging.getLogger(name).setLevel(level)
            root.handlers[:] = saved_handlers

        self.addCleanup(restore)

    def test_development_shows_app_info_and_access_log(self):
        configure_logging("development")

        self.assertEqual(logging.getLogger().level, logging.INFO)
        self.assertTrue(
            logging.getLogger("app.features.usage.service").isEnabledFor(logging.INFO)
        )
        self.assertTrue(logging.getLogger("uvicorn.access").isEnabledFor(logging.INFO))

    def test_production_shows_only_warnings_and_no_access_log(self):
        configure_logging("production")

        self.assertEqual(logging.getLogger().level, logging.WARNING)
        app_logger = logging.getLogger("app.features.usage.service")
        self.assertFalse(app_logger.isEnabledFor(logging.INFO))
        self.assertTrue(app_logger.isEnabledFor(logging.WARNING))
        # 生のURL・クエリが残るアクセスログ（INFO）を出さない。
        self.assertFalse(logging.getLogger("uvicorn.access").isEnabledFor(logging.INFO))

    def test_libraries_show_only_warnings_in_both_environments(self):
        for app_env in ("development", "production"):
            with self.subTest(app_env=app_env):
                configure_logging(app_env)

                for name in QUIET_LIBRARY_LOGGERS:
                    library_logger = logging.getLogger(name)
                    self.assertFalse(library_logger.isEnabledFor(logging.INFO), name)
                    self.assertTrue(library_logger.isEnabledFor(logging.WARNING), name)

    def test_adds_one_output_only_when_none_is_set(self):
        root = logging.getLogger()
        root.handlers[:] = []

        configure_logging("development")
        configure_logging("development")

        self.assertEqual(len(root.handlers), 1)


if __name__ == "__main__":
    unittest.main()
