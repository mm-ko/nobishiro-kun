import type {
  CheckoutSessionResponse,
  CurrentSubscriptionResponse,
} from "@/types/api";
import { authenticatedFetch, UnauthenticatedRequestError } from "./client";

export class PaymentRequestError extends Error {
  constructor(
    public readonly code: string,
    message: string,
  ) {
    super(message);
    this.name = "PaymentRequestError";
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isNullableString(value: unknown): value is string | null {
  return value === null || typeof value === "string";
}

function isStripeCheckoutUrl(value: unknown): value is string {
  if (typeof value !== "string") {
    return false;
  }

  try {
    const url = new URL(value);
    return url.protocol === "https:" && url.hostname === "checkout.stripe.com";
  } catch {
    return false;
  }
}

function isCheckoutSessionResponse(
  value: unknown,
): value is CheckoutSessionResponse {
  return isRecord(value) && isStripeCheckoutUrl(value.checkout_url);
}

function isCurrentSubscriptionResponse(
  value: unknown,
): value is CurrentSubscriptionResponse {
  return (
    isRecord(value) &&
    typeof value.is_subscribed === "boolean" &&
    isNullableString(value.status) &&
    isNullableString(value.current_period_end)
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

function getApiBaseUrl(): string {
  const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "");
  if (!apiBaseUrl) {
    throw new PaymentRequestError(
      "INTERNAL_ERROR",
      "APIの接続先が設定されていません。",
    );
  }
  return apiBaseUrl;
}

async function paymentFetch(
  path: string,
  init: RequestInit,
): Promise<Response> {
  try {
    return await authenticatedFetch(`${getApiBaseUrl()}${path}`, init);
  } catch (error) {
    if (error instanceof UnauthenticatedRequestError) {
      throw new PaymentRequestError(
        "UNAUTHENTICATED",
        "Firebaseのログイン情報を確認できませんでした。",
      );
    }
    throw error;
  }
}

export async function createCheckoutSession(): Promise<CheckoutSessionResponse> {
  const response = await paymentFetch("/v1/billing/checkout-sessions", {
    method: "POST",
  });
  const payload: unknown = await response.json().catch(() => null);

  if (!response.ok) {
    throw new PaymentRequestError(
      getApiErrorCode(payload),
      "決済画面の作成に失敗しました。",
    );
  }

  if (!isCheckoutSessionResponse(payload)) {
    throw new PaymentRequestError(
      "INTERNAL_ERROR",
      "決済画面のレスポンス形式が不正です。",
    );
  }

  return payload;
}

export async function getCurrentSubscription(): Promise<CurrentSubscriptionResponse> {
  const response = await paymentFetch("/v1/subscriptions/current", {
    method: "GET",
  });
  const payload: unknown = await response.json().catch(() => null);

  if (!response.ok) {
    throw new PaymentRequestError(
      getApiErrorCode(payload),
      "契約状態の取得に失敗しました。",
    );
  }

  if (!isCurrentSubscriptionResponse(payload)) {
    throw new PaymentRequestError(
      "INTERNAL_ERROR",
      "契約状態のレスポンス形式が不正です。",
    );
  }

  return payload;
}
