from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class SettingsConfigurationError(RuntimeError):
    """The settings are combined in a way that must not start the app."""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_ignore_empty=True)

    # 書き忘れても安全な側で動くよう、初期値は本番扱いにする。
    app_env: Literal["development", "production"] = "production"
    dev_fixed_user_enabled: bool = False
    database_url: str | None = None
    firebase_project_id: str | None = None
    firebase_credentials_path: str | None = None
    frontend_origin: str | None = None
    openrouter_api_key: str | None = None
    openrouter_model: str | None = None
    openrouter_timeout_seconds: int | None = None
    image_max_bytes: int = 10 * 1024 * 1024
    image_total_max_bytes: int = 20 * 1024 * 1024
    monthly_analysis_limit: int = 10
    memcached_host: str | None = None
    memcached_port: int | None = None
    stripe_secret_key: str | None = None
    stripe_webhook_secret: str | None = None
    stripe_price_id: str | None = None
    stripe_success_url: str | None = None
    stripe_cancel_url: str | None = None

    @model_validator(mode="after")
    def forbid_dev_fixed_user_outside_development(self) -> "Settings":
        # トークンなしの呼び出しを通す設定のため、本番で誤ってオンにしたら起動させない。
        # ValueError にすると、エラー表示に他の設定値（DBのパスワードなど）が
        # 一部含まれるため、メッセージだけを出す別の例外にする。
        if self.dev_fixed_user_enabled and self.app_env != "development":
            raise SettingsConfigurationError(
                "DEV_FIXED_USER_ENABLED can be true only when APP_ENV=development."
            )
        return self


settings = Settings()
