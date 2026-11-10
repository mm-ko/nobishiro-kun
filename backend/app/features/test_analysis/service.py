"""Test analysis flow service."""

from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from io import BytesIO
from uuid import UUID, uuid4

from fastapi import UploadFile, status
from PIL import Image
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from app.core.config import settings
from app.features.ai_analysis import service as ai_analysis_service
from app.features.ai_analysis.clients.openrouter import (
    OpenRouterClient,
    OpenRouterError,
    OpenRouterTimeoutError,
)
from app.features.ai_analysis.schemas import (
    StageAInputImage,
    StageBInput,
    StageBUnit,
    UnitStatus,
)
from app.features.learning_history import service as history_service
from app.features.test_analysis import repository as test_analysis_repository
from app.features.test_analysis.schemas import (
    StageAQuestionResponse,
    StageAResponse,
    StageBAnalysisResult,
    StageBRequest,
    StageBResponse,
    StageBUnitResponse,
)
from app.features.usage import service as usage_service
from app.shared.exceptions import AppError

# 拡張子やContent-Typeは送る側が自由に付けられるため、中身の先頭で判定する。
IMAGE_SIGNATURES = {
    b"\xff\xd8\xff": "image/jpeg",
    b"\x89PNG\r\n\x1a\n": "image/png",
}
# Pillowに読ませる形式。ほかの形式として読める画像は、受け付けない。
READABLE_IMAGE_FORMATS = ("JPEG", "PNG")
# 仮の値。BEはまだ分析処理IDを保存しておらず、期限のチェックもしていない。
# 保持期限は #27 で決める。
ANALYSIS_REQUEST_LIFETIME = timedelta(hours=1)


def run_stage_a(
    session: Session, user_id: int, images: list[UploadFile]
) -> StageAResponse:
    """Validate the uploaded images and extract the facts of one test."""
    # 画像はこの関数の中のメモリだけで扱い、保存もログへの出力もしない。
    input_images = _validate_images(images)

    usage_service.check_remaining_usage(session, user_id)
    # 読み取りの間（数十秒）DBの接続を持ち続けないよう、読むだけの処理を終える。
    session.rollback()
    usage_service.check_rate_limit(user_id, usage_service.RateLimitTarget.STAGE_A)

    client = OpenRouterClient()
    try:
        extraction = ai_analysis_service.run_stage_a(input_images, client)
    except ai_analysis_service.StageAImageUnreadableError as exc:
        raise _image_unreadable_error() from exc
    except ai_analysis_service.StageAInvalidResponseError as exc:
        raise AppError(
            status.HTTP_502_BAD_GATEWAY,
            "AI_RESPONSE_INVALID",
            "読み取りに失敗しました。もう一度お試しください。",
        ) from exc
    except OpenRouterTimeoutError as exc:
        raise AppError(
            status.HTTP_504_GATEWAY_TIMEOUT,
            "ANALYSIS_TIMEOUT",
            "読み取りに時間がかかっています。時間をおいて、もう一度お試しください。",
        ) from exc
    except OpenRouterError as exc:
        raise AppError(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "AI_SERVICE_UNAVAILABLE",
            "ただいま読み取りを利用できません。時間をおいて、もう一度お試しください。",
        ) from exc
    finally:
        client.close()

    return StageAResponse(
        analysis_request_id=uuid4(),
        status="awaiting_confirmation",
        read_score=extraction.read_score,
        read_unit_name=extraction.read_unit_name,
        questions=[
            StageAQuestionResponse(**question.model_dump())
            for question in extraction.questions
        ],
        expires_at=datetime.now(UTC) + ANALYSIS_REQUEST_LIFETIME,
    )


def _validate_images(images: list[UploadFile]) -> list[StageAInputImage]:
    # 枚数と全体の量は、受信の段階（upload.py）で制限済み。
    # 容量は、中身を読み出す前に、受け取った大きさだけで確かめる。
    sizes = [image.size or 0 for image in images]
    if (
        any(size > settings.image_max_bytes for size in sizes)
        or sum(sizes) > settings.image_total_max_bytes
    ):
        raise AppError(
            status.HTTP_413_CONTENT_TOO_LARGE,
            "IMAGE_TOO_LARGE",
            "画像の容量が大きすぎます。容量を小さくしてお試しください。",
        )

    input_images = []
    for image in images:
        content = image.file.read()
        media_type = _detect_media_type(content)
        if media_type is None:
            raise AppError(
                status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                "UNSUPPORTED_IMAGE_TYPE",
                "JPEGまたはPNGの画像を送信してください。",
            )
        if not _is_readable_image(content):
            # 先頭だけが画像の形をした、壊れたデータをAIへ送らない。
            raise _image_unreadable_error()
        input_images.append(StageAInputImage(content=content, media_type=media_type))
    return input_images


def _detect_media_type(content: bytes) -> str | None:
    for signature, media_type in IMAGE_SIGNATURES.items():
        if content.startswith(signature):
            return media_type
    return None


def _is_readable_image(content: bytes) -> bool:
    try:
        with Image.open(BytesIO(content), formats=READABLE_IMAGE_FORMATS) as image:
            # 途中で切れた画像は、最後まで読み込んで初めて分かる。
            image.load()
    except (OSError, SyntaxError, ValueError, Image.DecompressionBombError):
        return False
    return True


def _image_unreadable_error() -> AppError:
    return AppError(
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        "IMAGE_UNREADABLE",
        "画像から問題を読み取れませんでした。撮り直してお試しください。",
    )


def run_stage_b(
    session: Session,
    user_id: int,
    analysis_request_id: UUID,
    request: StageBRequest,
) -> StageBResponse:
    # 保存済みの分析で、AIを呼び直して費用をかけない。保存済みの結果を返す
    # 再送への対応は、Idempotency-Keyの保持方式を決めてから行う。
    if usage_service.is_analysis_counted(session, analysis_request_id):
        raise _analysis_already_saved_error()
    # Stage Aを通らずに直接呼べるため、ここでも確かめ、上限に達していればAIを
    # 呼ばない。保存済みの分析の再送は、上限に達していても上の409にする（#23）。
    usage_service.check_remaining_usage(session, user_id)
    # Stage BもAIを複数回呼ぶため、短時間の連続実行を抑える（#24）。
    usage_service.check_rate_limit(user_id, usage_service.RateLimitTarget.STAGE_B)
    units = [
        StageBUnit(id=unit.id, code=unit.code, name=unit.name)
        for unit in test_analysis_repository.list_units(session)
    ]
    data = StageBInput(
        read_unit_name=request.read_unit_name,
        confirmed_questions=request.confirmed_questions,
    )
    client = None
    try:
        client = OpenRouterClient()
        result = ai_analysis_service.run_stage_b(data, units, client)
        comment = (
            ai_analysis_service.generate_comment(data, result, client)
            if result.unit_status == UnitStatus.SUPPORTED
            else None
        )
    except ai_analysis_service.StageBInvalidResponseError as exc:
        raise AppError(
            502, "AI_RESPONSE_INVALID", "分析に失敗しました。もう一度お試しください。"
        ) from exc
    except OpenRouterTimeoutError as exc:
        raise AppError(
            504,
            "ANALYSIS_TIMEOUT",
            "分析に時間がかかっています。もう一度お試しください。",
        ) from exc
    except OpenRouterError as exc:
        raise AppError(
            503, "AI_SERVICE_UNAVAILABLE", "ただいま分析を利用できません。"
        ) from exc
    finally:
        if client is not None:
            client.close()
    # 得点率は、小数第3位を四捨五入した値で保存・表示する（DB設計 5章）。
    score_rate = (Decimal(request.score) * 100 / Decimal(request.max_score)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    response = StageBResponse(
        analysis_request_id=analysis_request_id,
        status="unsupported"
        if result.unit_status == UnitStatus.UNSUPPORTED
        else "unit_undetermined",
        unit_status=result.unit_status,
        unit=None,
        score=request.score,
        max_score=request.max_score,
        score_rate=float(score_rate),
        incorrect_question_numbers=None,
        analysis_result=None,
        comment_title=None,
        comment_body=None,
        message=(
            "このテストの単元は分析対象外のため、分析を終了します。"
            "利用回数は消費されません。"
        )
        if result.unit_status == UnitStatus.UNSUPPORTED
        else (
            "このテストの単元を特定できなかったため、分析を終了します。"
            "利用回数は消費されません。"
        ),
    )
    if result.unit_status != UnitStatus.SUPPORTED:
        return response
    if result.unit is None or result.patterns is None or comment is None:
        raise AppError(502, "AI_RESPONSE_INVALID", "分析結果を確認できませんでした。")
    response.status = "completed"
    response.unit = StageBUnitResponse(
        **result.unit.model_dump(exclude={"id"}), id=str(result.unit.id)
    )
    response.incorrect_question_numbers = [
        f"{q.image_index}:{q.question_number or f'番号不明-{q.question_id}'}"
        for q in data.confirmed_questions
        if q.grading == "incorrect"
    ]
    response.analysis_result = StageBAnalysisResult(patterns=result.patterns)
    response.comment_title = (
        "今回のテストは満点でした"
        if request.score == request.max_score
        and not response.incorrect_question_numbers
        else comment.comment_title
    )
    response.comment_body = comment.comment_body
    response.message = None
    _save_completed_analysis(
        session, user_id, analysis_request_id, result.unit.id, score_rate, response
    )
    return response


def _save_completed_analysis(
    session: Session,
    user_id: int,
    analysis_request_id: UUID,
    unit_id: int,
    score_rate: Decimal,
    response: StageBResponse,
) -> None:
    # 利用実績と分析記録は、同じトランザクションで両方保存するか、両方保存しない
    # （DB設計 5章）。保存できてから completed を返す。
    # DBのnow()はトランザクション開始（AI呼び出し前）の時刻になり、月をまたぐと
    # 前月の利用として数えてしまうため、保存する時点のUTC時刻を両方に入れる。
    saved_at = datetime.now(UTC)
    try:
        # 分析の間に、別の端末の保存で上限に達していれば保存しない（#23）。
        usage_service.lock_usage(session, user_id)
        # 同じ分析IDの同時送信で先に保存された場合は、上限の403ではなく409にする。
        if usage_service.is_analysis_counted(session, analysis_request_id):
            raise _analysis_already_saved_error()
        usage_service.check_remaining_usage(session, user_id, saved_at)
        usage_id = usage_service.record_usage(
            session, user_id, analysis_request_id, saved_at
        )
        history_service.save_analysis(
            session,
            user_id=user_id,
            unit_id=unit_id,
            analysis_usage_id=usage_id,
            score=response.score,
            max_score=response.max_score,
            score_rate=score_rate,
            incorrect_question_numbers=response.incorrect_question_numbers or [],
            analysis_result=response.analysis_result.model_dump(mode="json"),
            comment_title=response.comment_title,
            comment_body=response.comment_body,
            recorded_at=saved_at,
        )
        session.commit()
    except AppError:
        # 先に保存されていた・上限に達したため、利用実績も分析記録も保存しない。
        session.rollback()
        raise
    except IntegrityError:
        session.rollback()
        # 同じ分析処理IDの同時送信で、先に保存された場合だけ409にする。
        if usage_service.is_analysis_counted(session, analysis_request_id):
            raise _analysis_already_saved_error() from None
        raise


def _analysis_already_saved_error() -> AppError:
    return AppError(
        status.HTTP_409_CONFLICT,
        "ANALYSIS_STATE_CONFLICT",
        "この分析はすでに完了しています。",
    )
