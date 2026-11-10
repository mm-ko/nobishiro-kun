import { beforeEach, describe, expect, test, vi } from "vitest";

import PlanResultPage from "./page";

const mocks = vi.hoisted(() => ({
  redirect: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  redirect: mocks.redirect,
}));

vi.mock("@/features/auth/components/RequireAuth", () => ({
  RequireAuth: ({ children }: { children: React.ReactNode }) => children,
}));

describe("PlanResultPage", () => {
  beforeEach(() => {
    mocks.redirect.mockReset();
    mocks.redirect.mockImplementation(() => {
      throw new Error("NEXT_REDIRECT");
    });
  });

  test("不正な決済ステータスは有料案内へリダイレクトする", async () => {
    const page = PlanResultPage({
      searchParams: Promise.resolve({ status: "unexpected" }),
    } as never);

    await expect(page).rejects.toThrow("NEXT_REDIRECT");
    expect(mocks.redirect).toHaveBeenCalledWith("/plan");
  });
});
