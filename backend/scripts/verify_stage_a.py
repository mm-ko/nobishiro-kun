"""Run Stage A on real images: from backend, python scripts/verify_stage_a.py IMAGE.

Set OPENROUTER_API_KEY and OPENROUTER_MODEL in the process environment yourself.
Pass one or two JPEG/PNG files of one test (front and back). Images are read into
memory only and are never copied, saved or printed.
By default only counts, presence flags and the elapsed time are printed, with the
number of HTTP requests sent to OpenRouter, their status codes and durations.
Use --review to show the validated extraction on the terminal, for images you are
allowed to inspect. Nothing is written to files or logs.
Use --provider SLUG to send the request only to that OpenRouter provider (for
comparing providers). ZDR routing stays enforced; only the candidate set is narrowed.
Credentials, raw model responses and exception messages are never printed.
"""

import argparse
import re
import sys
import time
from collections import Counter
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.features.ai_analysis.clients.openrouter import (  # noqa: E402
    OpenRouterClient,
    OpenRouterError,
)
from app.features.ai_analysis.schemas import (  # noqa: E402
    StageAExtraction,
    StageAInputImage,
)
from app.features.ai_analysis.service import (  # noqa: E402
    StageAImageUnreadableError,
    StageAInvalidResponseError,
    run_stage_a,
)

MAX_IMAGE_COUNT = 2
# 拡張子ではなく、ファイルの先頭の内容で形式を見分ける。
IMAGE_SIGNATURES = {
    b"\xff\xd8\xff": "image/jpeg",
    b"\x89PNG\r\n\x1a\n": "image/png",
}
# 外部から来るProvider名は、名前として想定できる形のときだけ表示する。
PROVIDER_NAME = re.compile(r"[A-Za-z0-9 ._-]{1,40}")


def _as_dict(value: object) -> dict:
    # 応答の形が想定と違っても止まらないよう、辞書以外は空として扱う。
    return value if isinstance(value, dict) else {}


def _json_dict(response: httpx.Response) -> dict:
    try:
        return _as_dict(response.json())
    except ValueError:
        return {}


def _provider_name(value: object) -> str:
    if isinstance(value, str) and PROVIDER_NAME.fullmatch(value):
        return value
    return "-"


def load_image(path: Path) -> StageAInputImage | None:
    content = path.read_bytes()
    for signature, media_type in IMAGE_SIGNATURES.items():
        if content.startswith(signature):
            return StageAInputImage(content=content, media_type=media_type)
    return None


def print_summary(extraction: StageAExtraction, image_count: int) -> None:
    for image_index in range(1, image_count + 1):
        questions = [q for q in extraction.questions if q.image_index == image_index]
        gradings = Counter(q.grading.value for q in questions)
        print(
            f"image {image_index}: questions={len(questions)}"
            f" correct={gradings['correct']} incorrect={gradings['incorrect']}"
            f" unknown={gradings['unknown']}"
            f" blank_answers={sum(q.student_answer == '' for q in questions)}"
            f" unread_answers={sum(q.student_answer is None for q in questions)}"
            f" with_process={sum(q.calculation_process is not None for q in questions)}"
            f" without_number={sum(q.question_number is None for q in questions)}"
        )
    print(
        f"read_score={'yes' if extraction.read_score is not None else 'no'}"
        f" read_unit_name={'yes' if extraction.read_unit_name is not None else 'no'}"
    )


def print_review(extraction: StageAExtraction) -> None:
    print(f"read_score: {extraction.read_score}")
    print(f"read_unit_name: {extraction.read_unit_name}")
    for q in extraction.questions:
        print(f"[{q.question_id}] image={q.image_index} number={q.question_number}")
        print(f"  problem_text: {q.problem_text}")
        print(f"  student_answer: {q.student_answer!r}")
        print(f"  calculation_process: {q.calculation_process}")
        print(f"  grading: {q.grading.value}")


class RequestTimer:
    """Records how many requests were sent and how each one ended, never content."""

    def __init__(self) -> None:
        self.started_at: list[float] = []
        self.results: list[str] = []
        self.errors: list[str] = []

    def on_request(self, request: httpx.Request) -> None:
        self.started_at.append(time.monotonic())

    def on_response(self, response: httpx.Response) -> None:
        elapsed = time.monotonic() - self.started_at[-1]
        if response.is_error:
            self.results.append(f"{response.status_code}({elapsed:.1f}s)")
            self.errors.append(self._describe_error(response))
            return
        # 成功した応答は、どのProviderが、全体で何秒かけて返したかだけを記録する。
        response.read()
        total = time.monotonic() - self.started_at[-1]
        provider = _provider_name(_json_dict(response).get("provider"))
        self.results.append(f"{response.status_code}({total:.1f}s,provider={provider})")

    @staticmethod
    def _describe_error(response: httpx.Response) -> str:
        # 自由文のmessageは入力内容を含みうるため表示せず、コードと待ち時間だけを出す。
        response.read()
        error = _as_dict(_json_dict(response).get("error"))
        metadata = _as_dict(error.get("metadata"))
        code = error.get("code")
        headers = response.headers
        return (
            f"status={response.status_code}"
            f" code={code if type(code) is int else '-'}"
            f" provider={_provider_name(metadata.get('provider_name'))}"
            f" retry_after={headers.get('retry-after', '-')}"
            f" limit={headers.get('x-ratelimit-limit', '-')}"
            f" remaining={headers.get('x-ratelimit-remaining', '-')}"
        )

    def summary(self) -> str:
        # 応答がなかった送信は、タイムアウトまたは接続の失敗。
        no_response = len(self.started_at) - len(self.results)
        return (
            f"http_requests={len(self.started_at)}"
            f" responses={','.join(self.results) or '-'}"
            f" no_response={no_response}"
            + "".join(f"\n  error: {error}" for error in self.errors)
        )


class SingleProviderClient(httpx.Client):
    """Narrows the routing to one provider, keeping the ZDR settings of the client."""

    def __init__(self, provider: str, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self._provider = provider

    def post(self, url: str, **kwargs: object) -> httpx.Response:
        # アプリのクライアントが必ず付けるZDRの指定は変えず、送り先だけを絞る。
        body = dict(kwargs.pop("json"))
        body["provider"] = {**body["provider"], "only": [self._provider]}
        return super().post(url, json=body, **kwargs)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("images", nargs="+", type=Path, help="1-2 JPEG/PNG files")
    parser.add_argument(
        "--review", action="store_true", help="Show the validated extraction"
    )
    parser.add_argument("--provider", help="Send only to this provider slug")
    args = parser.parse_args()
    if len(args.images) > MAX_IMAGE_COUNT:
        print(f"FAIL too many images (max {MAX_IMAGE_COUNT})")
        return 1

    images = []
    for position, path in enumerate(args.images, start=1):
        try:
            image = load_image(path)
        except OSError as exc:
            print(f"FAIL image {position} cannot be read error={type(exc).__name__}")
            return 1
        if image is None:
            print(f"FAIL image {position} is not JPEG or PNG")
            return 1
        images.append(image)
        print(f"image {position}: {image.media_type} {len(image.content)} bytes")

    timer = RequestTimer()
    event_hooks = {"request": [timer.on_request], "response": [timer.on_response]}
    if args.provider:
        http_client = SingleProviderClient(args.provider, event_hooks=event_hooks)
        print(f"provider filter: only={args.provider}")
    else:
        http_client = httpx.Client(event_hooks=event_hooks)
    try:
        client = OpenRouterClient(http_client=http_client)
    except OpenRouterError as exc:
        http_client.close()
        print(f"FAIL configuration error={type(exc).__name__}")
        return 1
    started_at = time.monotonic()
    try:
        extraction = run_stage_a(images, client)
    except (
        OpenRouterError,
        StageAInvalidResponseError,
        StageAImageUnreadableError,
    ) as exc:
        elapsed = time.monotonic() - started_at
        print(f"FAIL error={type(exc).__name__} elapsed={elapsed:.1f}s")
        print(timer.summary())
        return 1
    finally:
        client.close()
    elapsed = time.monotonic() - started_at

    print(f"SUCCESS elapsed={elapsed:.1f}s questions={len(extraction.questions)}")
    print(timer.summary())
    print_summary(extraction, len(images))
    if args.review:
        print("--- review (terminal only) ---")
        print_review(extraction)
    return 0


if __name__ == "__main__":
    sys.exit(main())
