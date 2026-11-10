import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import {
  createCheckoutSession,
  getCurrentSubscription,
  PaymentRequestError,
} from "./payment";

const firebaseAuthMocks = vi.hoisted(() => ({
  getCurrentFirebaseUser: vi.fn(),
  getIdToken: vi.fn(),
  logoutFromFirebase: vi.fn(),
}));

vi.mock("@/lib/firebase/auth", () => ({
  getCurrentFirebaseUser: firebaseAuthMocks.getCurrentFirebaseUser,
  logoutFromFirebase: firebaseAuthMocks.logoutFromFirebase,
}));

const fetchMock = vi.fn<typeof fetch>();

async function getRejectedError(request: Promise<unknown>): Promise<unknown> {
  return request.then(
    () => {
      throw new Error("リクエストが失敗しませんでした。");
    },
    (error: unknown) => error,
  );
}

describe("payment API", () => {
  beforeEach(() => {
    fetchMock.mockReset();
    firebaseAuthMocks.getCurrentFirebaseUser.mockReset();
    firebaseAuthMocks.getCurrentFirebaseUser.mockReturnValue({
      getIdToken: firebaseAuthMocks.getIdToken,
    });
    firebaseAuthMocks.getIdToken.mockReset();
    firebaseAuthMocks.getIdToken.mockResolvedValue("firebase-id-token");
    firebaseAuthMocks.logoutFromFirebase.mockReset();
    firebaseAuthMocks.logoutFromFirebase.mockResolvedValue(undefined);
    vi.stubEnv("NEXT_PUBLIC_API_BASE_URL", "http://localhost:8000/");
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
  });

  test("認証付きでCheckoutを作成し、StripeのURLを返す", async () => {
    const responseBody = {
      checkout_url: "https://checkout.stripe.com/c/pay/cs_test_dummy",
    };
    fetchMock.mockResolvedValue(Response.json(responseBody, { status: 201 }));

    await expect(createCheckoutSession()).resolves.toEqual(responseBody);

    const [requestUrl, requestOptions] = fetchMock.mock.calls[0];
    const headers = new Headers(requestOptions?.headers);
    expect(requestUrl).toBe(
      "http://localhost:8000/v1/billing/checkout-sessions",
    );
    expect(requestOptions?.method).toBe("POST");
    expect(headers.get("Authorization")).toBe("Bearer firebase-id-token");
  });

  test.each([
    "http://checkout.stripe.com/c/pay/cs_test_dummy",
    "https://example.com/checkout",
    "javascript:alert(1)",
  ])("Stripe Checkout以外のURLを拒否する: %s", async (checkoutUrl) => {
    fetchMock.mockResolvedValue(
      Response.json({ checkout_url: checkoutUrl }, { status: 201 }),
    );

    const error = await getRejectedError(createCheckoutSession());

    expect(error).toBeInstanceOf(PaymentRequestError);
    expect((error as PaymentRequestError).code).toBe("INTERNAL_ERROR");
  });

  test("Backendのエラーコードを保持する", async () => {
    fetchMock.mockResolvedValue(
      Response.json({ error: { code: "ALREADY_SUBSCRIBED" } }, { status: 409 }),
    );

    const error = await getRejectedError(createCheckoutSession());

    expect(error).toBeInstanceOf(PaymentRequestError);
    expect((error as PaymentRequestError).code).toBe("ALREADY_SUBSCRIBED");
  });

  test("現在の契約状態を取得する", async () => {
    const responseBody = {
      is_subscribed: true,
      status: "active",
      current_period_end: "2026-11-25T00:00:00Z",
    };
    fetchMock.mockResolvedValue(Response.json(responseBody));

    await expect(getCurrentSubscription()).resolves.toEqual(responseBody);

    const [requestUrl, requestOptions] = fetchMock.mock.calls[0];
    expect(requestUrl).toBe("http://localhost:8000/v1/subscriptions/current");
    expect(requestOptions?.method).toBe("GET");
  });

  test("Firebaseユーザーがいない場合は決済APIを呼ばない", async () => {
    firebaseAuthMocks.getCurrentFirebaseUser.mockReturnValue(null);

    const error = await getRejectedError(createCheckoutSession());

    expect(error).toBeInstanceOf(PaymentRequestError);
    expect((error as PaymentRequestError).code).toBe("UNAUTHENTICATED");
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
