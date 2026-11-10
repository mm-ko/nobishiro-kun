"""Synchronous OpenRouter client with mandatory ZDR routing."""

import base64
import time

import httpx

from app.core.config import settings

OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
MAX_RETRY_COUNT = 3
DEFAULT_TIMEOUT_SECONDS = 30
ZDR_PROVIDER_ORDER = ["novita", "io-net"]


class OpenRouterError(Exception):
    """Base class for OpenRouter request failures."""


class OpenRouterConfigurationError(OpenRouterError):
    """Raised when required OpenRouter configuration is missing or invalid."""


class OpenRouterTimeoutError(OpenRouterError):
    """Raised when the OpenRouter request times out."""


class OpenRouterRateLimitError(OpenRouterError):
    """Raised when OpenRouter continues to rate-limit the request."""


class OpenRouterProviderUnavailableError(OpenRouterError):
    """Raised when no endpoint can satisfy the required routing constraints."""


class OpenRouterClientError(OpenRouterError):
    """Raised for other OpenRouter 4xx responses."""


class OpenRouterServerError(OpenRouterError):
    """Raised when OpenRouter returns a 5xx response."""


class OpenRouterConnectionError(OpenRouterError):
    """Raised when the request cannot reach OpenRouter."""


class OpenRouterClient:
    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        timeout_seconds: float | None = None,
        http_client: httpx.Client | None = None,
    ) -> None:
        resolved_api_key = (
            api_key if api_key is not None else settings.openrouter_api_key
        )
        resolved_model = model if model is not None else settings.openrouter_model
        resolved_timeout = (
            timeout_seconds
            if timeout_seconds is not None
            else settings.openrouter_timeout_seconds
        )

        if not resolved_api_key:
            raise OpenRouterConfigurationError("OpenRouter API key is not configured")
        if not resolved_model:
            raise OpenRouterConfigurationError("OpenRouter model is not configured")
        if resolved_timeout is None:
            resolved_timeout = DEFAULT_TIMEOUT_SECONDS
        if resolved_timeout <= 0:
            raise OpenRouterConfigurationError("OpenRouter timeout must be positive")

        self._api_key = resolved_api_key
        self._model = resolved_model
        self._timeout_seconds = resolved_timeout
        self._http_client = http_client or httpx.Client()

    def create_chat_completion(
        self,
        messages: list[dict[str, object]],
        parameters: dict[str, object] | None = None,
    ) -> dict[str, object]:
        request_body = dict(parameters or {})
        request_body.update(
            {
                "model": self._model,
                "messages": messages,
                "provider": {
                    "zdr": True,
                    "data_collection": "deny",
                    "only": ZDR_PROVIDER_ORDER,
                    "order": ZDR_PROVIDER_ORDER,
                    "allow_fallbacks": True,
                },
            }
        )
        headers = {"Authorization": f"Bearer {self._api_key}"}

        for attempt in range(MAX_RETRY_COUNT):
            try:
                response = self._http_client.post(
                    OPENROUTER_API_URL,
                    headers=headers,
                    json=request_body,
                    timeout=self._timeout_seconds,
                )
            except httpx.TimeoutException as exc:
                if attempt + 1 < MAX_RETRY_COUNT:
                    time.sleep(0.25 * (2**attempt))
                    continue
                raise OpenRouterTimeoutError("OpenRouter request timed out") from exc
            except httpx.TransportError as exc:
                raise OpenRouterConnectionError(
                    "Could not connect to OpenRouter"
                ) from exc

            if response.status_code == 429:
                if attempt + 1 < MAX_RETRY_COUNT:
                    time.sleep(0.25 * (2**attempt))
                    continue
                raise OpenRouterRateLimitError("OpenRouter rate limit exceeded")
            if response.status_code >= 500:
                if attempt + 1 < MAX_RETRY_COUNT:
                    time.sleep(0.25 * (2**attempt))
                    continue
                raise OpenRouterServerError("OpenRouter server error")
            if response.status_code == 404:
                raise OpenRouterProviderUnavailableError(
                    "No endpoint is available for the required routing constraints"
                )
            if 400 <= response.status_code < 500:
                raise OpenRouterClientError(
                    f"OpenRouter request failed with status {response.status_code}"
                )
            if response.is_error:
                raise OpenRouterError("OpenRouter returned an unexpected response")

            result = response.json()
            if not isinstance(result, dict):
                raise OpenRouterError("OpenRouter returned an invalid response")
            return result

        raise OpenRouterError("OpenRouter request failed")

    @staticmethod
    def encode_image(image_bytes: bytes, media_type: str) -> str:
        encoded_image = base64.b64encode(image_bytes).decode("ascii")
        return f"data:{media_type};base64,{encoded_image}"

    def close(self) -> None:
        self._http_client.close()
