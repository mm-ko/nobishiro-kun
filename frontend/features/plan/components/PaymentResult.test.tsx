import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import { PaymentResult } from "./PaymentResult";

const mocks = vi.hoisted(() => ({
  getCurrentSubscription: vi.fn(),
  push: vi.fn(),
}));

vi.mock("@/lib/api/payment", () => ({
  getCurrentSubscription: mocks.getCurrentSubscription,
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: mocks.push,
  }),
}));

const activeSubscription = {
  is_subscribed: true,
  status: "active",
  current_period_end: "2026-11-25T00:00:00Z",
};

const noSubscription = {
  is_subscribed: false,
  status: null,
  current_period_end: null,
};

describe("PaymentResult", () => {
  beforeEach(() => {
    mocks.getCurrentSubscription.mockReset();
    mocks.push.mockReset();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  test("契約がactiveと確認できた場合だけ成功を表示する", async () => {
    mocks.getCurrentSubscription.mockResolvedValue(activeSubscription);

    render(<PaymentResult status="success" />);

    expect(
      screen.getByRole("heading", { name: "決済状況を確認しています" }),
    ).toBeTruthy();
    expect(
      await screen.findByRole("heading", { name: "決済が完了しました" }),
    ).toBeTruthy();
    expect(mocks.getCurrentSubscription).toHaveBeenCalledOnce();
  });

  test("Webhookが未反映なら1秒後に契約状態を取り直す", async () => {
    vi.useFakeTimers();
    mocks.getCurrentSubscription
      .mockResolvedValueOnce(noSubscription)
      .mockResolvedValueOnce(activeSubscription);

    render(<PaymentResult status="success" />);
    await act(async () => {
      await Promise.resolve();
    });
    expect(mocks.getCurrentSubscription).toHaveBeenCalledOnce();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });

    expect(mocks.getCurrentSubscription).toHaveBeenCalledTimes(2);
    expect(
      screen.getByRole("heading", { name: "決済が完了しました" }),
    ).toBeTruthy();
  });

  test("10回確認してもactiveでなければ、失敗と断定せず再確認を案内する", async () => {
    vi.useFakeTimers();
    mocks.getCurrentSubscription.mockResolvedValue({
      ...activeSubscription,
      status: "past_due",
    });

    render(<PaymentResult status="success" />);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(9000);
    });

    expect(mocks.getCurrentSubscription).toHaveBeenCalledTimes(10);
    expect(
      screen.getByRole("heading", {
        name: "決済状況を確認できませんでした",
      }),
    ).toBeTruthy();
    expect(screen.queryByText("決済を完了できませんでした")).toBeNull();
  });

  test("再確認すると契約状態を最初から確認し直す", async () => {
    vi.useFakeTimers();
    mocks.getCurrentSubscription.mockResolvedValue(noSubscription);

    render(<PaymentResult status="success" />);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(9000);
    });
    mocks.getCurrentSubscription.mockResolvedValue(activeSubscription);

    fireEvent.click(screen.getByRole("button", { name: "もう一度確認する" }));
    await act(async () => {
      await Promise.resolve();
    });

    expect(
      screen.getByRole("heading", { name: "決済が完了しました" }),
    ).toBeTruthy();
  });

  test("失敗状態では契約APIを呼ばず、プラン画面へ戻れる", () => {
    render(<PaymentResult status="failure" />);
    fireEvent.click(screen.getByRole("button", { name: "再試行する" }));

    expect(mocks.getCurrentSubscription).not.toHaveBeenCalled();
    expect(mocks.push).toHaveBeenCalledWith("/plan");
  });

  test("キャンセル状態では契約APIを呼ばず、プラン画面へ戻れる", () => {
    render(<PaymentResult status="cancel" />);
    fireEvent.click(screen.getByRole("button", { name: "決済へ戻る" }));

    expect(mocks.getCurrentSubscription).not.toHaveBeenCalled();
    expect(mocks.push).toHaveBeenCalledWith("/plan");
  });
});
