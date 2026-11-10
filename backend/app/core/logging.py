"""Switch log output between development and production (#157)."""

import logging

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
# 送り先のURLや細かい中身を出す依存ライブラリは、開発でも本番でも絞る（ログ設計）。
QUIET_LIBRARY_LOGGERS = (
    "httpx",
    "httpcore",
    "stripe",
    "firebase_admin",
    "google",
    "urllib3",
    "sqlalchemy",
)


def configure_logging(app_env: str) -> None:
    """Set log levels for the environment. Call once when the app starts."""
    is_development = app_env == "development"
    app_level = logging.INFO if is_development else logging.WARNING

    root = logging.getLogger()
    root.setLevel(app_level)
    # Uvicornは自分のログだけに出力先を付けるため、アプリのログの出力先を用意する。
    if not root.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(LOG_FORMAT))
        root.addHandler(handler)

    # 本番では、生のURL・クエリが残るアクセスログを出さない（ログ設計）。
    logging.getLogger("uvicorn.access").setLevel(app_level)
    for name in QUIET_LIBRARY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)
