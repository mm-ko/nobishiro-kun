// 利用状況の「取り出す関数」。画面（UI-002 ホーム）はここだけを呼ぶ。
import type { UsageResponse } from "@/types/api";
import { authenticatedFetch, UnauthenticatedRequestError } from "./client";

export class UsageRequestError extends Error {
  constructor(
    public readonly code: string,
    message: string,
  ) {
    super(message);
    this.name = "UsageRequestError";
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isUsageResponse(value: unknown): value is UsageResponse {
  if (!isRecord(value)) {
    return false;
  }

  const isBlockedReasonValid =
    value.blocked_reason === null ||
    value.blocked_reason === "plan_required" ||
    value.blocked_reason === "monthly_limit_reached";

  return (
    typeof value.can_analyze === "boolean" &&
    typeof value.used_count === "number" &&
    Number.isInteger(value.used_count) &&
    value.used_count >= 0 &&
    typeof value.free_limit === "number" &&
    Number.isInteger(value.free_limit) &&
    value.free_limit >= 0 &&
    isBlockedReasonValid
  );
}

function getApiErrorCode(payload: unknown): string {
  if (!isRecord(payload) || !isRecord(payload.error)) {
    return "INTERNAL_ERROR";
  }

  return typeof payload.error.code === "string"
    ? payload.error.code
    : "INTERNAL_ERROR";
}

export async function getUsage(): Promise<UsageResponse> {
  const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "");
  if (!apiBaseUrl) {
    throw new UsageRequestError(
      "INTERNAL_ERROR",
      "APIの接続先が設定されていません。",
    );
  }

  let response: Response;
  try {
    response = await authenticatedFetch(`${apiBaseUrl}/v1/usage`, {
      method: "GET",
    });
  } catch (error) {
    if (error instanceof UnauthenticatedRequestError) {
      throw new UsageRequestError(
        "UNAUTHENTICATED",
        "Firebaseのログイン情報を確認できませんでした。",
      );
    }
    throw error;
  }

  const payload: unknown = await response.json().catch(() => null);

  if (!response.ok) {
    throw new UsageRequestError(
      getApiErrorCode(payload),
      "利用状況のリクエストに失敗しました。",
    );
  }

  if (!isUsageResponse(payload)) {
    throw new UsageRequestError(
      "INTERNAL_ERROR",
      "利用状況のレスポンス形式が不正です。",
    );
  }

  return payload;
}
