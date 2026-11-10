import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, test, vi } from "vitest";

import { RequireAuth } from "./RequireAuth";

const mocks = vi.hoisted(() => ({
  auth: {
    isLoading: true,
    user: null as { id: string; created_at: string } | null,
  },
  replace: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: mocks.replace }),
}));

vi.mock("@/features/auth/context/AuthContext", () => ({
  useAuth: () => mocks.auth,
}));

describe("RequireAuth", () => {
  beforeEach(() => {
    mocks.auth.isLoading = true;
    mocks.auth.user = null;
    mocks.replace.mockReset();
  });

  test("認証状態の復元中はログイン画面へ移動しない", () => {
    render(
      <RequireAuth>
        <p>認証済み画面</p>
      </RequireAuth>,
    );

    expect(screen.queryByText("認証済み画面")).toBeNull();
    expect(mocks.replace).not.toHaveBeenCalled();
  });

  test("未認証が確定した場合はログイン画面へ移動する", async () => {
    mocks.auth.isLoading = false;

    render(
      <RequireAuth>
        <p>認証済み画面</p>
      </RequireAuth>,
    );

    await waitFor(() => expect(mocks.replace).toHaveBeenCalledWith("/login"));
    expect(screen.queryByText("認証済み画面")).toBeNull();
  });

  test("認証済みの場合は子要素を表示する", () => {
    mocks.auth.isLoading = false;
    mocks.auth.user = {
      id: "app-user-1",
      created_at: "2026-10-20T00:00:00Z",
    };

    render(
      <RequireAuth>
        <p>認証済み画面</p>
      </RequireAuth>,
    );

    expect(screen.getByText("認証済み画面")).toBeDefined();
    expect(mocks.replace).not.toHaveBeenCalled();
  });
});
