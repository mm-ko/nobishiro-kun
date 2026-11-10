import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import type { User } from "firebase/auth";

import { authenticatedFetch } from "./client";
import { clearInitializedMyUser, initializeMyUser } from "./auth";

vi.mock("./client", () => ({
  authenticatedFetch: vi.fn(),
}));

const authenticatedFetchMock = vi.mocked(authenticatedFetch);
const firebaseUser = { uid: "firebase-user-1" } as User;
const userResponse = {
  id: "app-user-1",
  created_at: "2026-10-20T00:00:00Z",
};

describe("initializeMyUser", () => {
  beforeEach(() => {
    clearInitializedMyUser();
    authenticatedFetchMock.mockReset();
    vi.stubEnv("NEXT_PUBLIC_API_BASE_URL", "http://localhost:8000/");
  });

  afterEach(() => {
    vi.unstubAllEnvs();
  });

  test("PUT /v1/users/meでアプリ内ユーザーを初期登録する", async () => {
    authenticatedFetchMock.mockResolvedValue(
      Response.json(userResponse, { status: 201 }),
    );

    await expect(initializeMyUser(firebaseUser)).resolves.toEqual(userResponse);
    expect(authenticatedFetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/v1/users/me",
      { method: "PUT" },
      firebaseUser,
    );
  });

  test("同一ログイン中の重複初期登録をまとめる", async () => {
    authenticatedFetchMock.mockResolvedValue(Response.json(userResponse));

    await initializeMyUser(firebaseUser);
    await initializeMyUser(firebaseUser);

    expect(authenticatedFetchMock).toHaveBeenCalledOnce();
  });

  test("ログアウト後は同じユーザーでも再度初期登録APIを呼ぶ", async () => {
    authenticatedFetchMock.mockImplementation(async () =>
      Response.json(userResponse),
    );

    await initializeMyUser(firebaseUser);
    clearInitializedMyUser();
    await initializeMyUser(firebaseUser);

    expect(authenticatedFetchMock).toHaveBeenCalledTimes(2);
  });

  test("レスポンス形式が不正な場合はエラーにする", async () => {
    authenticatedFetchMock.mockResolvedValue(
      Response.json({ id: "app-user-1" }),
    );

    await expect(initializeMyUser(firebaseUser)).rejects.toThrow(
      "ユーザー情報の初期登録に失敗しました。",
    );
  });
});
