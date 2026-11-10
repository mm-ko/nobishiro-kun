import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, test, vi } from "vitest";

import {
  mockUsageAvailable,
  mockUsageMonthlyLimitReached,
  mockUsagePlanRequired,
} from "@/mocks/usage";
import { AnalyzeButton } from "./AnalyzeButton";

const mocks = vi.hoisted(() => ({
  getUsage: vi.fn(),
  push: vi.fn(),
}));

vi.mock("@/lib/api/usage", () => ({
  getUsage: mocks.getUsage,
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: mocks.push,
  }),
}));

const LIMIT_MESSAGE =
  "今月の分析回数の上限に達しました。来月1日から、また分析できます。";

describe("AnalyzeButton", () => {
  beforeEach(() => {
    mocks.getUsage.mockReset();
    mocks.push.mockReset();
  });

  test("blocked_reason が null のときは、分析ボタンだけを出し、押すとアップロードへ進む", async () => {
    mocks.getUsage.mockResolvedValue(mockUsageAvailable);

    render(<AnalyzeButton />);
    fireEvent.click(
      await screen.findByRole("button", { name: "テストを分析する" }),
    );

    expect(screen.getAllByRole("button")).toHaveLength(1);
    expect(screen.queryByText(LIMIT_MESSAGE)).toBeNull();
    expect(mocks.push).toHaveBeenCalledWith("/test-upload");
  });

  test("plan_required のときは、有料案内のボタンだけを出し、押すと有料案内へ進む", async () => {
    mocks.getUsage.mockResolvedValue(mockUsagePlanRequired);

    render(<AnalyzeButton />);
    fireEvent.click(
      await screen.findByRole("button", { name: "3回目以降は有料です" }),
    );

    expect(screen.getAllByRole("button")).toHaveLength(1);
    expect(screen.queryByText(LIMIT_MESSAGE)).toBeNull();
    expect(mocks.push).toHaveBeenCalledWith("/plan");
  });

  test("monthly_limit_reached のときは、押せない上限のお知らせだけを出す", async () => {
    mocks.getUsage.mockResolvedValue(mockUsageMonthlyLimitReached);

    render(<AnalyzeButton />);

    expect(await screen.findByText(LIMIT_MESSAGE)).toBeTruthy();
    expect(screen.queryByRole("button")).toBeNull();
  });

  test("利用状況を取得できないときは、分析ボタンを出す", async () => {
    mocks.getUsage.mockRejectedValue(new Error("network error"));

    render(<AnalyzeButton />);

    expect(
      await screen.findByRole("button", { name: "テストを分析する" }),
    ).toBeTruthy();
  });
});
