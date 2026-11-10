"""Send a synthetic image to OpenRouter with ZDR routing enabled."""

import os
import sys

import httpx

API_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "google/gemma-4-26b-a4b-it"
SYNTHETIC_PNG = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/"
    "lQAAAABJRU5ErkJggg=="
)


def main() -> int:
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        print("FAIL provider=unknown")
        return 1

    try:
        timeout_seconds = float(os.environ.get("OPENROUTER_TIMEOUT_SECONDS", "30"))
        if timeout_seconds <= 0:
            print("FAIL provider=unknown")
            return 1

        image_data_url = f"data:image/png;base64,{SYNTHETIC_PNG}"
        request_body = {
            "model": os.environ.get("OPENROUTER_MODEL", DEFAULT_MODEL),
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Reply with one word: OK."},
                        {"type": "image_url", "image_url": {"url": image_data_url}},
                    ],
                }
            ],
            "max_tokens": 8,
            "provider": {
                "zdr": True,
                "data_collection": "deny",
                "allow_fallbacks": False,
            },
        }

        with httpx.Client(timeout=timeout_seconds) as client:
            response = client.post(
                API_URL,
                headers={"Authorization": f"Bearer {api_key}"},
                json=request_body,
            )

        if not response.is_success:
            print("FAIL provider=unknown")
            return 1

        response_data = response.json()
        provider = response_data.get("provider", "unknown")
        if not isinstance(provider, str) or not provider:
            provider = "unknown"
        print(f"SUCCESS provider={provider}")
        return 0
    except (httpx.HTTPError, ValueError):
        print("FAIL provider=unknown")
        return 1


if __name__ == "__main__":
    sys.exit(main())
