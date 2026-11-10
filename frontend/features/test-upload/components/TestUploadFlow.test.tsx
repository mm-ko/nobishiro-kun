import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, test, vi } from "vitest";

import { AnalysisResultProvider } from "@/features/test-analysis/context/AnalysisResultContext";
import {
  StageARequestError,
  StageBRequestError,
  startStageA,
  submitStageB,
} from "@/lib/api/analysis";
import type { StageAResponse, StageBRequest } from "@/types/api";

import { TestUploadFlow } from "./TestUploadFlow";

const routerMocks = vi.hoisted(() => ({
  push: vi.fn(),
  replace: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => routerMocks,
}));

vi.mock("@/lib/analysisWaiting", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/analysisWaiting")>();

  return {
    ...actual,
    withAnalysisTimeout: (promise: Promise<unknown>) => promise,
  };
});
vi.mock("@/lib/api/analysis", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/analysis")>();

  return {
    ...actual,
    startStageA: vi.fn(),
    submitStageB: vi.fn(),
  };
});
vi.mock("./CropStep", () => ({
  CropStep: ({ onUseOriginal }: { onUseOriginal: () => void }) => (
    <button type="button" onClick={onUseOriginal}>
      元の画像を使う
    </button>
  ),
}));
vi.mock("./ReviewStep", () => ({
  ReviewStep: ({
    onComplete,
  }: {
    onComplete: (request: StageBRequest) => void;
  }) => (
    <button
      type="button"
      onClick={() =>
        onComplete({
          score: 80,
          max_score: 100,
          read_unit_name: "わり算",
          confirmed_questions: [],
        })
      }
    >
      確認完了
    </button>
  ),
}));

const stageAResponse = {
  analysis_request_id: "analysis-1",
  status: "awaiting_confirmation",
  read_score: 80,
  read_unit_name: "わり算",
  questions: [],
  expires_at: "2026-10-27T12:00:00Z",
} satisfies StageAResponse;

function renderFlow() {
  return render(
    <AnalysisResultProvider>
      <TestUploadFlow />
    </AnalysisResultProvider>,
  );
}

function createJpeg(name: string) {
  return new File([new Uint8Array([0xff, 0xd8, 0xff, 0x00])], name, {
    type: "image/jpeg",
  });
}

async function uploadImage(file: File) {
  renderFlow();

  fireEvent.change(screen.getByLabelText("画像を選ぶ"), {
    target: { files: [file] },
  });

  await waitFor(() => {
    expect(screen.getByAltText("テスト画像1")).toBeTruthy();
  });
}

async function proceedToAnalysis() {
  fireEvent.click(screen.getByRole("button", { name: "トリミングへ進む" }));
  fireEvent.click(screen.getByRole("button", { name: "元の画像を使う" }));
}

async function proceedToStageB() {
  await uploadImage(createJpeg("first.jpg"));
  vi.mocked(startStageA).mockResolvedValue(stageAResponse);
  await proceedToAnalysis();
  fireEvent.click(await screen.findByRole("button", { name: "確認完了" }));
}

describe("TestUploadFlow", () => {
  beforeEach(() => {
    routerMocks.push.mockClear();
    routerMocks.replace.mockClear();
  });

  test("画像を追加して削除すると、選択画像がなくなる", async () => {
    await uploadImage(createJpeg("first.jpg"));

    expect(screen.getByText("選んだ画像 1/2")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "削除" }));

    expect(screen.getByText("選んだ画像 0/2")).toBeTruthy();
    expect(screen.getByText("ここに並びます")).toBeTruthy();
  });

  test("画像を差し替えると、差し替え後のファイルを分析APIへ渡す", async () => {
    const original = createJpeg("original.jpg");
    const replacement = createJpeg("replacement.jpg");

    await uploadImage(original);

    fireEvent.change(screen.getByLabelText("差し替え"), {
      target: { files: [replacement] },
    });

    await waitFor(() => {
      expect(screen.getByAltText("テスト画像1")).toBeTruthy();
    });

    vi.mocked(startStageA).mockReturnValue(new Promise(() => {}));

    await proceedToAnalysis();

    await waitFor(() => {
      expect(startStageA).toHaveBeenCalledWith(
        [replacement],
        expect.objectContaining({
          idempotencyKey: expect.any(String),
          signal: expect.any(AbortSignal),
        }),
      );
    });
  });

  test("分析開始時にStage A APIを呼び出してローディングを表示する", async () => {
    await uploadImage(createJpeg("first.jpg"));

    vi.mocked(startStageA).mockReturnValue(new Promise(() => {}));

    await proceedToAnalysis();

    expect(startStageA).toHaveBeenCalledOnce();
    expect(screen.getByText("内容を確認しています")).toBeTruthy();
  });

  test("Stage A APIが失敗するとエラー画面を表示する", async () => {
    await uploadImage(createJpeg("first.jpg"));

    vi.mocked(startStageA).mockRejectedValue(new Error("通信エラー"));

    await proceedToAnalysis();

    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(
      screen.getByText(
        "分析に失敗しました。時間をおいてもう一度お試しください。",
      ),
    ).toBeTruthy();
    expect(screen.getByRole("button", { name: "もう一度試す" })).toBeTruthy();
  });

  test("429相当のエラーでは一時的な利用制限メッセージを表示する", async () => {
    await uploadImage(createJpeg("first.jpg"));

    vi.mocked(startStageA).mockRejectedValue(
      new StageARequestError(
        "RATE_LIMIT_EXCEEDED",
        "リクエストが制限されました。",
      ),
    );

    await proceedToAnalysis();

    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(
      screen.getByText(
        "現在、一時的に分析を利用できません。少し時間をおいてから、もう一度お試しください。",
      ),
    ).toBeTruthy();
  });

  test("Stage Aで月の上限に達していたら、上限の案内と［ホームへ戻る］だけを表示する", async () => {
    await uploadImage(createJpeg("first.jpg"));

    vi.mocked(startStageA).mockRejectedValue(
      new StageARequestError(
        "MONTHLY_LIMIT_REACHED",
        "Stage Aのリクエストに失敗しました。",
      ),
    );

    await proceedToAnalysis();

    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(
      screen.getByText(
        "今月の分析回数の上限に達しました。来月1日から、また分析できます。",
      ),
    ).toBeTruthy();
    expect(screen.queryByRole("button", { name: "もう一度試す" })).toBeNull();
    expect(
      screen.queryByRole("button", { name: "トリミングへ戻る" }),
    ).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "ホームへ戻る" }));

    expect(routerMocks.push).toHaveBeenCalledWith("/home");
  });

  test("Stage AでPLAN_REQUIREDが返ったら、エラーを出さずに有料案内へ移動する", async () => {
    await uploadImage(createJpeg("first.jpg"));

    vi.mocked(startStageA).mockRejectedValue(
      new StageARequestError(
        "PLAN_REQUIRED",
        "Stage Aのリクエストに失敗しました。",
      ),
    );

    await proceedToAnalysis();

    await waitFor(() => {
      expect(routerMocks.replace).toHaveBeenCalledWith("/plan");
    });
    expect(screen.queryByRole("alert")).toBeNull();
  });

  test("Stage Bで月の上限に達していたら、上限の案内と［ホームへ戻る］だけを表示する", async () => {
    vi.mocked(submitStageB).mockRejectedValue(
      new StageBRequestError(
        "MONTHLY_LIMIT_REACHED",
        "Stage Bのリクエストに失敗しました。",
      ),
    );

    await proceedToStageB();

    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(
      screen.getByText(
        "今月の分析回数の上限に達しました。来月1日から、また分析できます。",
      ),
    ).toBeTruthy();
    expect(screen.queryByRole("button", { name: "もう一度試す" })).toBeNull();
    expect(screen.queryByRole("button", { name: "確認画面へ戻る" })).toBeNull();
    expect(screen.getByRole("button", { name: "ホームへ戻る" })).toBeTruthy();
  });

  test("Stage BでPLAN_REQUIREDが返ったら、エラーを出さずに有料案内へ移動する", async () => {
    vi.mocked(submitStageB).mockRejectedValue(
      new StageBRequestError(
        "PLAN_REQUIRED",
        "Stage Bのリクエストに失敗しました。",
      ),
    );

    await proceedToStageB();

    await waitFor(() => {
      expect(routerMocks.replace).toHaveBeenCalledWith("/plan");
    });
    expect(screen.queryByRole("alert")).toBeNull();
  });

  test("画像を追加して分析を開始してもlocalStorageやsessionStorageへ保存しない", async () => {
    const localStorageSpy = vi.spyOn(Storage.prototype, "setItem");

    await uploadImage(createJpeg("first.jpg"));

    expect(localStorageSpy).not.toHaveBeenCalled();

    vi.mocked(startStageA).mockReturnValue(new Promise(() => {}));

    await proceedToAnalysis();

    expect(localStorageSpy).not.toHaveBeenCalled();
  });
});
