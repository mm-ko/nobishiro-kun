import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import { authenticatedFetch, UnauthenticatedRequestError } from "./client";
import {
  getCurrentFirebaseUser,
  logoutFromFirebase,
} from "@/lib/firebase/auth";

vi.mock("@/lib/firebase/auth", () => ({
  getCurrentFirebaseUser: vi.fn(),
  logoutFromFirebase: vi.fn(),
}));

const fetchMock = vi.fn<typeof fetch>();
const getCurrentFirebaseUserMock = vi.mocked(getCurrentFirebaseUser);
const logoutFromFirebaseMock = vi.mocked(logoutFromFirebase);

describe("authenticatedFetch", () => {
  beforeEach(() => {
    fetchMock.mockReset();
    getCurrentFirebaseUserMock.mockReset();
    logoutFromFirebaseMock.mockReset();
    logoutFromFirebaseMock.mockResolvedValue(undefined);
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  test("Firebase IDトークンをAuthorizationヘッダーへ付与する", async () => {
    const getIdToken = vi.fn().mockResolvedValue("firebase-id-token");
    getCurrentFirebaseUserMock.mockReturnValue({ getIdToken } as never);
    fetchMock.mockResolvedValue(new Response(null, { status: 200 }));

    await authenticatedFetch("http://localhost:8000/v1/example", {
      headers: { "X-Request-Id": "request-1" },
    });

    const [, request] = fetchMock.mock.calls[0];
    const headers = new Headers(request?.headers);
    expect(getIdToken).toHaveBeenCalledOnce();
    expect(headers.get("Authorization")).toBe("Bearer firebase-id-token");
    expect(headers.get("X-Request-Id")).toBe("request-1");
  });

  test("Backendが401を返した場合はFirebaseからログアウトする", async () => {
    getCurrentFirebaseUserMock.mockReturnValue({
      getIdToken: vi.fn().mockResolvedValue("expired-token"),
    } as never);
    fetchMock.mockResolvedValue(new Response(null, { status: 401 }));

    const response = await authenticatedFetch(
      "http://localhost:8000/v1/example",
    );

    expect(response.status).toBe(401);
    expect(logoutFromFirebaseMock).toHaveBeenCalledOnce();
  });

  test("Firebaseユーザーがいない場合はBackendを呼ばない", async () => {
    getCurrentFirebaseUserMock.mockReturnValue(null);

    await expect(
      authenticatedFetch("http://localhost:8000/v1/example"),
    ).rejects.toBeInstanceOf(UnauthenticatedRequestError);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
