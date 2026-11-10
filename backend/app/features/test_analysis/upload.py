"""Limits how much of an image upload is received, before it is validated."""

from collections.abc import AsyncGenerator, Callable, Coroutine
from typing import Any

from fastapi import Request, Response, status
from fastapi.routing import APIRoute
from starlette.datastructures import FormData
from starlette.exceptions import HTTPException
from starlette.formparsers import MultiPartException, MultiPartParser
from starlette.requests import AwaitableOrContextManager

from app.core.config import settings
from app.shared.exceptions import VALIDATION_ERROR_CODE, AppError

MAX_IMAGE_COUNT = 2
# 画像の合計に上乗せして受け取ってよい、multipartの区切りとヘッダーの分。
MULTIPART_OVERHEAD_BYTES = 64 * 1024

# Starletteは、このサイズを超えたアップロードを一時ファイルへ書き出す（既定は1MB）。
# 受け取る量は下の LimitedUploadRoute で止めるため、ここまでは届かない。
# テスト画像をディスクに残さないよう、受け取る分はメモリだけで扱う。
MultiPartParser.spool_max_size = (
    settings.image_total_max_bytes + MULTIPART_OVERHEAD_BYTES + 1
)


def _max_body_bytes() -> int:
    return settings.image_total_max_bytes + MULTIPART_OVERHEAD_BYTES


class _LimitedUploadRequest(Request):
    """Stops receiving the body once it exceeds the accepted upload size."""

    is_too_large = False

    async def stream(self) -> AsyncGenerator[bytes]:
        received_bytes = 0
        async for chunk in super().stream():
            received_bytes += len(chunk)
            if received_bytes > _max_body_bytes():
                # Content-Lengthがない・実際より小さい送信でも、上限で読むのをやめる。
                # この例外にすると、Starletteが受け取り途中のファイルを閉じる。
                self.is_too_large = True
                raise MultiPartException("Upload is too large.")
            yield chunk

    def form(self, **kwargs: Any) -> AwaitableOrContextManager[FormData]:
        # 上限より多いファイルは、中身を受け取る前に解析をやめる。
        return super().form(max_files=MAX_IMAGE_COUNT)


class LimitedUploadRoute(APIRoute):
    """Rejects oversized or excessive uploads while the request is being received.

    FastAPI reads the whole upload before the endpoint runs, so limits checked in
    the service alone would be applied only after everything has been received.
    """

    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        original_handler = super().get_route_handler()

        async def limited_handler(request: Request) -> Response:
            content_length = request.headers.get("content-length", "")
            if content_length.isdigit() and int(content_length) > _max_body_bytes():
                # 申告された大きさが上限を超えていれば、中身を読まずに断る。
                raise _too_large_error()

            limited_request = _LimitedUploadRequest(request.scope, request.receive)
            try:
                return await original_handler(limited_request)
            except HTTPException as exc:
                if limited_request.is_too_large:
                    raise _too_large_error() from exc
                if exc.status_code == status.HTTP_400_BAD_REQUEST:
                    # 枚数の超過など、multipartとして受け取れなかった場合。
                    raise AppError(
                        status.HTTP_422_UNPROCESSABLE_CONTENT,
                        VALIDATION_ERROR_CODE,
                        "入力内容を確認してください。",
                        [
                            {
                                "field": "images",
                                "reason": "画像は1〜2枚で送信してください。",
                            }
                        ],
                    ) from exc
                raise

        return limited_handler


def _too_large_error() -> AppError:
    return AppError(
        status.HTTP_413_CONTENT_TOO_LARGE,
        "IMAGE_TOO_LARGE",
        "画像の容量が大きすぎます。容量を小さくしてお試しください。",
    )
