import json
import unittest
from unittest.mock import patch

import httpx

from app.features.ai_analysis.clients.openrouter import (
    MAX_RETRY_COUNT,
    OpenRouterClient,
    OpenRouterClientError,
    OpenRouterProviderUnavailableError,
    OpenRouterRateLimitError,
    OpenRouterServerError,
    OpenRouterTimeoutError,
)


class OpenRouterClientTests(unittest.TestCase):
    def make_client(self, handler):
        http_client = httpx.Client(transport=httpx.MockTransport(handler))
        return OpenRouterClient(
            api_key="test-key",
            model="google/gemma-4-26b-a4b-it",
            timeout_seconds=5,
            http_client=http_client,
        )

    def test_request_always_requires_zdr_and_limits_providers(self):
        request_data = {}

        def handler(request):
            request_data.update(json.loads(request.content))
            return httpx.Response(200, json={"id": "response-id"})

        client = self.make_client(handler)
        try:
            result = client.create_chat_completion(
                [{"role": "user", "content": "hello"}],
                {"provider": {"zdr": False, "only": ["other-provider"]}},
            )
        finally:
            client.close()

        self.assertEqual(result["id"], "response-id")
        self.assertEqual(
            request_data["provider"],
            {
                "zdr": True,
                "data_collection": "deny",
                "only": ["novita", "io-net"],
                "order": ["novita", "io-net"],
                "allow_fallbacks": True,
            },
        )

    def test_non_matching_endpoint_fails_without_retry_or_fallback(self):
        request_count = 0

        def handler(request):
            nonlocal request_count
            request_count += 1
            return httpx.Response(404, json={"error": {"message": "not found"}})

        client = self.make_client(handler)
        try:
            with self.assertRaises(OpenRouterProviderUnavailableError):
                client.create_chat_completion([{"role": "user", "content": "hello"}])
        finally:
            client.close()

        self.assertEqual(request_count, 1)

    def test_timeout_retries_are_bounded_and_converted(self):
        request_count = 0

        def handler(request):
            nonlocal request_count
            request_count += 1
            raise httpx.ReadTimeout("timeout", request=request)

        client = self.make_client(handler)
        try:
            with patch("app.features.ai_analysis.clients.openrouter.time.sleep"):
                with self.assertRaises(OpenRouterTimeoutError):
                    client.create_chat_completion(
                        [{"role": "user", "content": "hello"}]
                    )
        finally:
            client.close()

        self.assertEqual(request_count, MAX_RETRY_COUNT)

    def test_rate_limit_and_server_errors_are_distinct(self):
        for status_code, error_type in (
            (429, OpenRouterRateLimitError),
            (503, OpenRouterServerError),
        ):
            with self.subTest(status_code=status_code):
                request_count = 0

                def handler(request, response_status=status_code):
                    nonlocal request_count
                    request_count += 1
                    return httpx.Response(response_status, json={"error": {}})

                client = self.make_client(handler)
                try:
                    with patch(
                        "app.features.ai_analysis.clients.openrouter.time.sleep"
                    ):
                        with self.assertRaises(error_type):
                            client.create_chat_completion(
                                [{"role": "user", "content": "hello"}]
                            )
                finally:
                    client.close()

                self.assertEqual(request_count, MAX_RETRY_COUNT)

    def test_other_client_errors_are_converted_without_retry(self):
        request_count = 0

        def handler(request):
            nonlocal request_count
            request_count += 1
            return httpx.Response(400, json={"error": {"message": "invalid"}})

        client = self.make_client(handler)
        try:
            with self.assertRaises(OpenRouterClientError):
                client.create_chat_completion([{"role": "user", "content": "hello"}])
        finally:
            client.close()

        self.assertEqual(request_count, 1)

    def test_image_is_encoded_as_an_in_memory_data_uri(self):
        self.assertEqual(
            OpenRouterClient.encode_image(b"image-bytes", "image/png"),
            "data:image/png;base64,aW1hZ2UtYnl0ZXM=",
        )


if __name__ == "__main__":
    unittest.main()
