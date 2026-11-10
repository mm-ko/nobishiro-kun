import importlib.util
import unittest
from pathlib import Path

import httpx

spec = importlib.util.spec_from_file_location(
    "verify_stage_a",
    Path(__file__).resolve().parents[2] / "scripts/verify_stage_a.py",
)
script = importlib.util.module_from_spec(spec)
spec.loader.exec_module(script)

SECRET = "SECRET-INPUT-TEXT"


def record(status, **kwargs):
    # 外部へは送らず、作り物の応答をタイマーに渡す。
    timer = script.RequestTimer()
    request = httpx.Request("POST", "https://openrouter.test/chat")
    timer.on_request(request)
    timer.on_response(httpx.Response(status, request=request, **kwargs))
    return timer.summary()


class RequestTimerTests(unittest.TestCase):
    def test_error_shows_code_and_wait_but_never_message(self):
        summary = record(
            429,
            headers={"retry-after": "7"},
            json={
                "error": {
                    "code": 429,
                    "message": SECRET,
                    "metadata": {"provider_name": "Io Net", "raw": SECRET},
                }
            },
        )
        self.assertIn("status=429 code=429 provider=Io Net retry_after=7", summary)
        self.assertNotIn(SECRET, summary)

    def test_unexpected_error_shapes_still_record_status(self):
        for body in (
            [SECRET],
            {"error": SECRET},
            {"error": {"code": "429", "metadata": SECRET}},
            {"error": {"metadata": {"provider_name": f"{SECRET}\n" * 5}}},
        ):
            with self.subTest(body=body):
                summary = record(500, json=body)
                self.assertIn("responses=500(", summary)
                self.assertIn("status=500 code=- provider=-", summary)
                self.assertNotIn(SECRET, summary)

    def test_non_json_error_still_records_status(self):
        summary = record(502, content=SECRET.encode())
        self.assertIn("status=502 code=- provider=-", summary)
        self.assertNotIn(SECRET, summary)

    def test_success_with_unexpected_shape_still_records_time(self):
        for kwargs in ({"json": [SECRET]}, {"content": SECRET.encode()}):
            with self.subTest(kwargs=kwargs):
                summary = record(200, **kwargs)
                self.assertRegex(summary, r"responses=200\(\d+\.\ds,provider=-\)")
                self.assertNotIn(SECRET, summary)

    def test_success_shows_provider_name(self):
        summary = record(200, json={"provider": "Novita"})
        self.assertIn("provider=Novita)", summary)


if __name__ == "__main__":
    unittest.main()
