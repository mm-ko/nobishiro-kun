// 履歴・ランキングの「取り出す関数」。画面（UI-002 ホーム）はここだけを呼ぶ。
// 履歴は GET /v1/analysis-records、ランキングは GET /v1/rankings/units を呼ぶ。
import type {
  AnalysisRecordItem,
  AnalysisRecordsResponse,
  UnitRankingItem,
  UnitRankingsResponse,
} from "@/types/api";
import { authenticatedFetch, UnauthenticatedRequestError } from "./client";

// ホームに表示する履歴の件数（新しい順の20件だけを表示し、続きは読み込まない）
const ANALYSIS_RECORDS_LIMIT = 20;

type RecordsRequestOptions = {
  signal?: AbortSignal;
};

export class RecordsRequestError extends Error {
  constructor(
    public readonly code: string,
    message: string,
  ) {
    super(message);
    this.name = "RecordsRequestError";
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isAnalysisRecordItem(value: unknown): value is AnalysisRecordItem {
  if (!isRecord(value)) {
    return false;
  }

  return (
    typeof value.id === "string" &&
    typeof value.recorded_at === "string" &&
    isRecord(value.unit) &&
    typeof value.unit.code === "string" &&
    typeof value.unit.name === "string" &&
    typeof value.score === "number" &&
    typeof value.max_score === "number"
  );
}

function isAnalysisRecordsResponse(
  value: unknown,
): value is AnalysisRecordsResponse {
  if (!isRecord(value)) {
    return false;
  }

  return (
    Array.isArray(value.items) &&
    value.items.every(isAnalysisRecordItem) &&
    typeof value.limit === "number" &&
    typeof value.offset === "number" &&
    typeof value.has_more === "boolean"
  );
}

function isUnitRankingItem(value: unknown): value is UnitRankingItem {
  if (!isRecord(value)) {
    return false;
  }

  return (
    typeof value.rank === "number" &&
    isRecord(value.unit) &&
    typeof value.unit.code === "string" &&
    typeof value.unit.name === "string" &&
    typeof value.average_score_rate === "number" &&
    typeof value.record_count === "number"
  );
}

function isUnitRankingsResponse(value: unknown): value is UnitRankingsResponse {
  if (!isRecord(value)) {
    return false;
  }

  return Array.isArray(value.items) && value.items.every(isUnitRankingItem);
}

function getApiErrorCode(payload: unknown): string {
  if (!isRecord(payload) || !isRecord(payload.error)) {
    return "INTERNAL_ERROR";
  }

  return typeof payload.error.code === "string"
    ? payload.error.code
    : "INTERNAL_ERROR";
}

/** UI-002：ログイン中のユーザーの学習履歴（新しい順）を取得する */
export async function getAnalysisRecords(
  options: RecordsRequestOptions = {},
): Promise<AnalysisRecordsResponse> {
  const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "");
  if (!apiBaseUrl) {
    throw new RecordsRequestError(
      "INTERNAL_ERROR",
      "APIの接続先が設定されていません。",
    );
  }

  let response: Response;
  try {
    response = await authenticatedFetch(
      `${apiBaseUrl}/v1/analysis-records?limit=${ANALYSIS_RECORDS_LIMIT}`,
      {
        method: "GET",
        signal: options.signal,
      },
    );
  } catch (error) {
    if (error instanceof UnauthenticatedRequestError) {
      throw new RecordsRequestError(
        "UNAUTHENTICATED",
        "Firebaseのログイン情報を確認できませんでした。",
      );
    }
    throw error;
  }

  const payload: unknown = await response.json().catch(() => null);

  if (!response.ok) {
    throw new RecordsRequestError(
      getApiErrorCode(payload),
      "学習履歴のリクエストに失敗しました。",
    );
  }

  if (!isAnalysisRecordsResponse(payload)) {
    throw new RecordsRequestError(
      "INTERNAL_ERROR",
      "学習履歴のレスポンス形式が不正です。",
    );
  }

  return payload;
}

/** UI-002：ログイン中のユーザーの苦手単元ランキング（得点率の平均が低い順）を取得する */
export async function getUnitRankings(
  options: RecordsRequestOptions = {},
): Promise<UnitRankingsResponse> {
  const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "");
  if (!apiBaseUrl) {
    throw new RecordsRequestError(
      "INTERNAL_ERROR",
      "APIの接続先が設定されていません。",
    );
  }

  let response: Response;
  try {
    response = await authenticatedFetch(`${apiBaseUrl}/v1/rankings/units`, {
      method: "GET",
      signal: options.signal,
    });
  } catch (error) {
    if (error instanceof UnauthenticatedRequestError) {
      throw new RecordsRequestError(
        "UNAUTHENTICATED",
        "Firebaseのログイン情報を確認できませんでした。",
      );
    }
    throw error;
  }

  const payload: unknown = await response.json().catch(() => null);

  if (!response.ok) {
    throw new RecordsRequestError(
      getApiErrorCode(payload),
      "ランキングのリクエストに失敗しました。",
    );
  }

  if (!isUnitRankingsResponse(payload)) {
    throw new RecordsRequestError(
      "INTERNAL_ERROR",
      "ランキングのレスポンス形式が不正です。",
    );
  }

  return payload;
}
