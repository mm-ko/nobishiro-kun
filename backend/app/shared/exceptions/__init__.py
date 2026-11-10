"""Common error responses shared by all features (API設計 4章)."""

import logging
from uuid import uuid4

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

VALIDATION_ERROR_CODE = "VALIDATION_ERROR"
INTERNAL_ERROR_CODE = "INTERNAL_ERROR"

logger = logging.getLogger(__name__)


class AppError(Exception):
    """An error returned to the client in the common error format."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: list[dict[str, str]] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(code)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or []
        self.headers = headers


def register_exception_handlers(app: FastAPI) -> None:
    """Return every error in the common format, including validation errors."""
    app.add_exception_handler(AppError, _handle_app_error)
    app.add_exception_handler(RequestValidationError, _handle_validation_error)
    app.add_exception_handler(Exception, _handle_unexpected_error)


def _error_response(
    request: Request,
    status_code: int,
    code: str,
    message: str,
    details: list[dict[str, str]],
    headers: dict[str, str] | None = None,
    error_type: str | None = None,
) -> JSONResponse:
    # HTTPリクエストの追跡用。分析処理IDとは区別する（API設計 4章）。
    request_id = f"req-{uuid4().hex}"
    _log_error(request, request_id, status_code, code, error_type)
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {"code": code, "message": message, "details": details},
            "request_id": request_id,
        },
        headers=headers,
    )


def _log_error(
    request: Request,
    request_id: str,
    status_code: int,
    code: str,
    error_type: str | None,
) -> None:
    # 応答と同じ request_id を残し、報告されたIDからログを探せるようにする。
    # 入力値・トークン・クエリ・例外のメッセージは残さない（答案の内容や
    # 秘密情報が入ることがあるため）。パスと、例外の種類の名前だけを残す。
    log = logger.error if status_code >= 500 else logger.warning
    log(
        "request_id=%s method=%s path=%s status=%d code=%s error_type=%s",
        request_id,
        request.method,
        request.url.path,
        status_code,
        code,
        error_type or "-",
    )


def _handle_app_error(request: Request, exc: AppError) -> JSONResponse:
    return _error_response(
        request, exc.status_code, exc.code, exc.message, exc.details, exc.headers
    )


def _handle_validation_error(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    # 入力値（答案の内容を含むことがある）は返さず、どの項目かだけを返す。
    details = [
        {
            "field": ".".join(str(part) for part in error["loc"][1:])
            or str(error["loc"][0]),
            "reason": "必須の項目です。"
            if error["type"] == "missing"
            else "形式または値が正しくありません。",
        }
        for error in exc.errors()
    ]
    return _error_response(
        request,
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        VALIDATION_ERROR_CODE,
        "入力内容を確認してください。",
        details,
    )


def _handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    # スタックトレースや例外の内容は返さない（API設計 4章）。
    return _error_response(
        request,
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        INTERNAL_ERROR_CODE,
        "時間をおいて、もう一度お試しください。",
        [],
        error_type=type(exc).__name__,
    )
