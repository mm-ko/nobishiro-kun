import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import type { UsageResponse } from "@/types/api";

import { getUsage, UsageRequestError } from "./usage";

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

const validUsageResponse = {
  can_analyze: true,
  used_count: 1,
  free_limit: 2,
  blocked_reason: null,
} satisfies UsageResponse;

async function getRejectedError(request: Promise<unknown>): Promise<unknown> {
  return request.then(
    () => {
      throw new Error("リクエストが失敗しませんでした。");
    },
    (error: unknown) => error,
  );
}

function getLastRequest(): Parameters<typeof fetch> {
  const request = fetchMock.mock.calls.at(-1);
  if (!request) {
    throw new Error("fetchが呼ばれていません。");
  }

  return request;
}

describe("usage API", () => {
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

  test("利用状況APIから認証済みユーザーの利用状況を取得する", async () => {
    fetchMock.mockResolvedValue(Response.json(validUsageResponse));

    const response = await getUsage();
    const [requestUrl, requestOptions] = getLastRequest();
    const headers = new Headers(requestOptions?.headers);

    expect(response).toEqual(validUsageResponse);
    expect(requestUrl).toBe("http://localhost:8000/v1/usage");
    expect(requestOptions?.method).toBe("GET");
    expect(headers.get("Authorization")).toBe("Bearer firebase-id-token");
  });

  test.each(["plan_required", "monthly_limit_reached"] as const)(
    "blocked_reason が %s の利用状況をそのまま返す",
    async (blockedReason) => {
      const blockedUsageResponse = {
        ...validUsageResponse,
        can_analyze: false,
        blocked_reason: blockedReason,
      };
      fetchMock.mockResolvedValue(Response.json(blockedUsageResponse));

      await expect(getUsage()).resolves.toEqual(blockedUsageResponse);
    },
  );

  test("APIエラーのときはエラーコードを持ったエラーにする", async () => {
    fetchMock.mockResolvedValue(
      Response.json({ error: { code: "UNAUTHENTICATED" } }, { status: 401 }),
    );

    const error = await getRejectedError(getUsage());

    expect(error).toBeInstanceOf(UsageRequestError);
    expect((error as UsageRequestError).code).toBe("UNAUTHENTICATED");
  });

  test("レスポンス形式が不正な場合はエラーにする", async () => {
    fetchMock.mockResolvedValue(
      Response.json({ ...validUsageResponse, used_count: "1" }),
    );

    const error = await getRejectedError(getUsage());

    expect(error).toBeInstanceOf(UsageRequestError);
    expect((error as UsageRequestError).code).toBe("INTERNAL_ERROR");
  });

  test("APIの接続先が設定されていない場合は送信しない", async () => {
    vi.stubEnv("NEXT_PUBLIC_API_BASE_URL", "");

    const error = await getRejectedError(getUsage());

    expect(error).toBeInstanceOf(UsageRequestError);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  test("Firebaseユーザーがいない場合は利用状況APIを呼ばない", async () => {
    firebaseAuthMocks.getCurrentFirebaseUser.mockReturnValue(null);

    const error = await getRejectedError(getUsage());

    expect(error).toBeInstanceOf(UsageRequestError);
    expect((error as UsageRequestError).code).toBe("UNAUTHENTICATED");
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
