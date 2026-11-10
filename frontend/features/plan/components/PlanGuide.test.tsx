import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, test, vi } from "vitest";

import { PaymentRequestError } from "@/lib/api/payment";
import { PlanGuide } from "./PlanGuide";

const mocks = vi.hoisted(() => ({
  createCheckoutSession: vi.fn(),
  push: vi.fn(),
}));

vi.mock("@/lib/api/payment", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/payment")>();
  return {
    ...actual,
    createCheckoutSession: mocks.createCheckoutSession,
  };
});

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: mocks.push,
  }),
}));

function createCheckoutTab() {
  const replace = vi.fn();
  const close = vi.fn();
  const tab = {
    opener: window,
    location: { replace },
    close,
  } as unknown as Window;
  return { tab, replace, close };
}

describe("PlanGuide", () => {
  beforeEach(() => {
    mocks.createCheckoutSession.mockReset();
    mocks.push.mockReset();
  });

  test("決済の前に、金額と月10回までであることを表示する", () => {
    render(<PlanGuide />);

    expect(screen.getByText("3回目以降は月額300円")).toBeTruthy();
    expect(screen.getByText("月10回まで（無料分を含む）")).toBeTruthy();
  });

  test("Checkoutを作成し、新しいタブをStripeのURLへ移動する", async () => {
    const { tab, replace } = createCheckoutTab();
    const open = vi.spyOn(window, "open").mockReturnValue(tab);
    mocks.createCheckoutSession.mockResolvedValue({
      checkout_url: "https://checkout.stripe.com/c/pay/cs_test_dummy",
    });

    render(<PlanGuide />);
    fireEvent.click(
      screen.getByRole("button", { name: "月額300円で利用する" }),
    );

    await waitFor(() => {
      expect(replace).toHaveBeenCalledWith(
        "https://checkout.stripe.com/c/pay/cs_test_dummy",
      );
    });
    expect(open).toHaveBeenCalledWith("about:blank", "_blank");
    expect(tab.opener).toBeNull();
  });

  test("処理中の連打ではCheckoutを1回だけ作成する", () => {
    const { tab } = createCheckoutTab();
    vi.spyOn(window, "open").mockReturnValue(tab);
    mocks.createCheckoutSession.mockReturnValue(new Promise(() => undefined));

    render(<PlanGuide />);
    const button = screen.getByRole("button", {
      name: "月額300円で利用する",
    });
    fireEvent.click(button);
    fireEvent.click(button);

    expect(mocks.createCheckoutSession).toHaveBeenCalledOnce();
  });

  test("ポップアップがブロックされた場合はAPIを呼ばず案内する", () => {
    vi.spyOn(window, "open").mockReturnValue(null);

    render(<PlanGuide />);
    fireEvent.click(
      screen.getByRole("button", { name: "月額300円で利用する" }),
    );

    expect(mocks.createCheckoutSession).not.toHaveBeenCalled();
    expect(screen.getByRole("alert").textContent).toContain(
      "ポップアップを許可",
    );
  });

  test("Checkout作成に失敗した場合は空タブを閉じて再試行を案内する", async () => {
    const { tab, close } = createCheckoutTab();
    vi.spyOn(window, "open").mockReturnValue(tab);
    mocks.createCheckoutSession.mockRejectedValue(new Error("network error"));

    render(<PlanGuide />);
    fireEvent.click(
      screen.getByRole("button", { name: "月額300円で利用する" }),
    );

    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(close).toHaveBeenCalledOnce();
  });

  test("契約済みの場合は空タブを閉じ、契約確認画面へ進む", async () => {
    const { tab, close } = createCheckoutTab();
    vi.spyOn(window, "open").mockReturnValue(tab);
    mocks.createCheckoutSession.mockRejectedValue(
      new PaymentRequestError("ALREADY_SUBSCRIBED", "already subscribed"),
    );

    render(<PlanGuide />);
    fireEvent.click(
      screen.getByRole("button", { name: "月額300円で利用する" }),
    );

    await waitFor(() => {
      expect(mocks.push).toHaveBeenCalledWith("/plan/result?status=success");
    });
    expect(close).toHaveBeenCalledOnce();
  });
});
