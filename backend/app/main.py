import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import settings
from app.core.logging import configure_logging
from app.shared.exceptions import register_exception_handlers

configure_logging(settings.app_env)

if settings.dev_fixed_user_enabled:
    # オンのまま気づかずに使い続けないよう、起動のたびに知らせる（#110）。
    logging.getLogger(__name__).warning(
        "開発用の固定ユーザーが有効です（DEV_FIXED_USER_ENABLED=true）。"
        "本番ではオンにしないでください。"
    )

app = FastAPI(title="Learning Tracking API")
register_exception_handlers(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin] if settings.frontend_origin else [],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)
