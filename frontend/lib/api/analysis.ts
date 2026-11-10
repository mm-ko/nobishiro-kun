// 分析（Stage A・Stage B）の「取り出す関数」。画面はここだけを呼ぶ。
import type {
  AnalysisPattern,
  StageAQuestion,
  StageAResponse,
  StageBCompletedResponse,
  StageBRequest,
  StageBResultResponse,
  StageBUnsupportedResponse,
  StageBUndeterminedResponse,
} from "@/types/api";
import { authenticatedFetch, UnauthenticatedRequestError } from "./client";

type StartStageAOptions = {
  idempotencyKey: string;
  signal?: AbortSignal;
};

type SubmitStageBOptions = {
  idempotencyKey: string;
  signal?: AbortSignal;
};

export class StageARequestError extends Error {
  constructor(
    public readonly code: string,
    message: string,
  ) {
    super(message);
    this.name = "StageARequestError";
  }
}

export class StageBRequestError extends Error {
  constructor(
    public readonly code: string,
    message: string,
  ) {
    super(message);
    this.name = "StageBRequestError";
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isNullableString(value: unknown): value is string | null {
  return value === null || typeof value === "string";
}

function isStageAQuestion(value: unknown): value is StageAQuestion {
  if (!isRecord(value)) {
    return false;
  }

  return (
    typeof value.question_id === "string" &&
    (value.image_index === 1 || value.image_index === 2) &&
    isNullableString(value.question_number) &&
    typeof value.problem_text === "string" &&
    isNullableString(value.student_answer) &&
    isNullableString(value.calculation_process) &&
    (value.grading === "correct" ||
      value.grading === "incorrect" ||
      value.grading === "unknown")
  );
}

function isStageAResponse(value: unknown): value is StageAResponse {
  if (!isRecord(value)) {
    return false;
  }

  return (
    typeof value.analysis_request_id === "string" &&
    value.status === "awaiting_confirmation" &&
    (value.read_score === null ||
      (typeof value.read_score === "number" &&
        Number.isInteger(value.read_score) &&
        value.read_score >= 0)) &&
    isNullableString(value.read_unit_name) &&
    Array.isArray(value.questions) &&
    value.questions.every(isStageAQuestion) &&
    typeof value.expires_at === "string"
  );
}

function isAnalysisPattern(value: unknown): value is AnalysisPattern {
  if (!isRecord(value)) {
    return false;
  }

  return (
    typeof value.pattern === "string" &&
    (value.cause_type === "blank" ||
      value.cause_type === "careless_mistake" ||
      value.cause_type === "possible_understanding_gap" ||
      value.cause_type === "undetermined") &&
    Array.isArray(value.question_numbers) &&
    value.question_numbers.every((number) => typeof number === "string") &&
    typeof value.explanation === "string"
  );
}

function isStageBCompletedResponse(
  value: unknown,
): value is StageBCompletedResponse {
  if (!isRecord(value)) {
    return false;
  }

  return (
    typeof value.analysis_request_id === "string" &&
    value.status === "completed" &&
    value.unit_status === "supported" &&
    isRecord(value.unit) &&
    typeof value.unit.id === "string" &&
    typeof value.unit.code === "string" &&
    typeof value.unit.name === "string" &&
    typeof value.score === "number" &&
    typeof value.max_score === "number" &&
    typeof value.score_rate === "number" &&
    Array.isArray(value.incorrect_question_numbers) &&
    value.incorrect_question_numbers.every(
      (number) => typeof number === "string",
    ) &&
    isRecord(value.analysis_result) &&
    Array.isArray(value.analysis_result.patterns) &&
    value.analysis_result.patterns.every(isAnalysisPattern) &&
    typeof value.comment_title === "string" &&
    typeof value.comment_body === "string" &&
    isNullableString(value.message)
  );
}

/** 対象外・判定困難のレスポンス（API設計書 3.4 の状態ごとの表）か */
function isStageBUnitUnavailableResponse(
  value: unknown,
): value is StageBUnsupportedResponse | StageBUndeterminedResponse {
  if (!isRecord(value)) {
    return false;
  }

  return (
    typeof value.analysis_request_id === "string" &&
    ((value.status === "unsupported" && value.unit_status === "unsupported") ||
      (value.status === "unit_undetermined" &&
        value.unit_status === "undetermined")) &&
    value.unit === null &&
    typeof value.score === "number" &&
    typeof value.max_score === "number" &&
    typeof value.score_rate === "number" &&
    value.incorrect_question_numbers === null &&
    value.analysis_result === null &&
    value.comment_title === null &&
    value.comment_body === null &&
    isNullableString(value.message)
  );
}

// 画面設計書 UI-005・UI-006B。ホームの上限の案内（UI-002）と同じ文
const MONTHLY_LIMIT_REACHED_MESSAGE =
  "今月の分析回数の上限に達しました。来月1日から、また分析できます。";

function getApiErrorCode(payload: unknown): string {
  if (!isRecord(payload) || !isRecord(payload.error)) {
    return "INTERNAL_ERROR";
  }

  return typeof payload.error.code === "string"
    ? payload.error.code
    : "INTERNAL_ERROR";
}

export function getStageAErrorMessage(error: unknown): string {
  if (!(error instanceof StageARequestError)) {
    return "分析に失敗しました。時間をおいてもう一度お試しください。";
  }

  switch (error.code) {
    case "IMAGE_TOO_LARGE":
      return "画像の容量が上限を超えています。画像を選び直してください。";
    case "UNSUPPORTED_IMAGE_TYPE":
      return "対応していない画像形式です。JPEG、JPG、PNGを選択してください。";
    case "VALIDATION_ERROR":
      return "画像の枚数や内容を確認してください。";
    case "IMAGE_UNREADABLE":
      return "画像を読み取れませんでした。明るい場所で撮り直してください。";
    case "RATE_LIMIT_EXCEEDED":
      return "現在、一時的に分析を利用できません。少し時間をおいてから、もう一度お試しください。";
    case "MONTHLY_LIMIT_REACHED":
      return MONTHLY_LIMIT_REACHED_MESSAGE;
    case "UNAUTHENTICATED":
      return "ログインの有効期限が切れています。もう一度ログインしてください。";
    case "AI_RESPONSE_INVALID":
    case "AI_SERVICE_UNAVAILABLE":
    case "ANALYSIS_TIMEOUT":
      return "AIによる分析に失敗しました。時間をおいてもう一度お試しください。";
    default:
      return "分析に失敗しました。時間をおいてもう一度お試しください。";
  }
}

/** やり直しても分析できないエラーか。画面では［ホームへ戻る］だけを出す */
export function shouldReturnHomeAfterStageAError(error: unknown): boolean {
  return (
    error instanceof StageARequestError &&
    error.code === "MONTHLY_LIMIT_REACHED"
  );
}

/** UI-005：「分析する」を押したあと。画像をStage A APIへ送信する */
export async function startStageA(
  images: File[],
  options: StartStageAOptions,
): Promise<StageAResponse> {
  const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "");
  if (!apiBaseUrl) {
    throw new StageARequestError(
      "INTERNAL_ERROR",
      "APIの接続先が設定されていません。",
    );
  }

  const formData = new FormData();
  images.forEach((image) => formData.append("images", image));

  const headers = new Headers({
    "Idempotency-Key": options.idempotencyKey,
  });

  let response: Response;
  try {
    response = await authenticatedFetch(`${apiBaseUrl}/v1/analyses`, {
      method: "POST",
      headers,
      body: formData,
      signal: options.signal,
    });
  } catch (error) {
    if (error instanceof UnauthenticatedRequestError) {
      throw new StageARequestError(
        "UNAUTHENTICATED",
        "Firebaseのログイン情報を確認できませんでした。",
      );
    }
    throw error;
  }

  const payload: unknown = await response.json().catch(() => null);

  if (!response.ok) {
    throw new StageARequestError(
      getApiErrorCode(payload),
      "Stage Aのリクエストに失敗しました。",
    );
  }

  if (!isStageAResponse(payload)) {
    throw new StageARequestError(
      "AI_RESPONSE_INVALID",
      "Stage Aのレスポンス形式が不正です。",
    );
  }

  return payload;
}

export function getStageBErrorMessage(error: unknown): string {
  if (!(error instanceof StageBRequestError)) {
    return "通信状況をご確認のうえ、もう一度お試しください。";
  }

  switch (error.code) {
    // 対象外・判定困難は、API設計書の message と同じ文を画面側に固定で持つ（画面設計書 UI-007）
    case "unsupported":
      return "このテストの単元は分析対象外のため、分析を終了します。利用回数は消費されません。";
    case "unit_undetermined":
      return "このテストの単元を特定できなかったため、分析を終了します。利用回数は消費されません。";
    case "VALIDATION_ERROR":
      return "確認内容に誤りがあります。確認画面へ戻って、得点や正誤を確認してください。";
    case "ANALYSIS_NOT_FOUND":
    case "ANALYSIS_EXPIRED":
    case "ANALYSIS_STATE_CONFLICT":
      return "分析を続けられませんでした。お手数ですが、ホームへ戻り、テスト画像のアップロードからやり直してください。";
    case "RATE_LIMIT_EXCEEDED":
      return "現在、一時的に分析を利用できません。少し時間をおいてから、もう一度お試しください。";
    case "MONTHLY_LIMIT_REACHED":
      return MONTHLY_LIMIT_REACHED_MESSAGE;
    case "UNAUTHENTICATED":
      return "ログインの有効期限が切れています。もう一度ログインしてください。";
    case "AI_RESPONSE_INVALID":
    case "AI_SERVICE_UNAVAILABLE":
    case "ANALYSIS_TIMEOUT":
      return "AIによる分析に失敗しました。時間をおいてもう一度お試しください。";
    default:
      return "通信状況をご確認のうえ、もう一度お試しください。";
  }
}

/** 再試行・確認画面へ戻っても続けられないエラーか。画面では［ホームへ戻る］だけを出す */
export function shouldReturnHomeAfterStageBError(error: unknown): boolean {
  if (!(error instanceof StageBRequestError)) {
    return false;
  }

  return (
    error.code === "unsupported" ||
    error.code === "unit_undetermined" ||
    error.code === "ANALYSIS_NOT_FOUND" ||
    error.code === "ANALYSIS_EXPIRED" ||
    error.code === "ANALYSIS_STATE_CONFLICT" ||
    error.code === "MONTHLY_LIMIT_REACHED"
  );
}

/** 契約が必要なエラーか（Stage A・Stage B 共通）。画面ではエラーを出さず、有料案内（UI-008）へ移動する */
export function shouldGoToPlanAfterAnalysisError(error: unknown): boolean {
  return (
    (error instanceof StageARequestError ||
      error instanceof StageBRequestError) &&
    error.code === "PLAN_REQUIRED"
  );
}

/** UI-006 の「確認完了」を押したあと。確認済みデータをStage B APIへ送信する */
export async function submitStageB(
  analysisRequestId: string,
  request: StageBRequest,
  options: SubmitStageBOptions,
): Promise<StageBResultResponse> {
  const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "");
  if (!apiBaseUrl) {
    throw new StageBRequestError(
      "INTERNAL_ERROR",
      "APIの接続先が設定されていません。",
    );
  }

  const headers = new Headers({
    "Content-Type": "application/json",
    "Idempotency-Key": options.idempotencyKey,
  });

  let response: Response;
  try {
    response = await authenticatedFetch(
      `${apiBaseUrl}/v1/analyses/${encodeURIComponent(analysisRequestId)}/result`,
      {
        method: "POST",
        headers,
        body: JSON.stringify(request),
        signal: options.signal,
      },
    );
  } catch (error) {
    if (error instanceof UnauthenticatedRequestError) {
      throw new StageBRequestError(
        "UNAUTHENTICATED",
        "Firebaseのログイン情報を確認できませんでした。",
      );
    }
    throw error;
  }

  const payload: unknown = await response.json().catch(() => null);

  if (!response.ok) {
    throw new StageBRequestError(
      getApiErrorCode(payload),
      "Stage Bのリクエストに失敗しました。",
    );
  }

  // 対象外・判定困難の結果は、結果画面に渡す。
  if (isStageBUnitUnavailableResponse(payload)) {
    return payload;
  }

  if (!isStageBCompletedResponse(payload)) {
    throw new StageBRequestError(
      "AI_RESPONSE_INVALID",
      "Stage Bのレスポンス形式が不正です。",
    );
  }

  return payload;
}
