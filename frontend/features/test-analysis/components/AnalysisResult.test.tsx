import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { AnalysisResult } from "./AnalysisResult";

afterEach(() => {
  cleanup();
});

const mocks = vi.hoisted(() => ({
  push: vi.fn(),
  replace: vi.fn(),
  logout: vi.fn(),
  clearAnalysisResult: vi.fn(),
  analysisResult: null as unknown,
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: mocks.push,
    replace: mocks.replace,
  }),
}));

vi.mock("@/features/auth/context/AuthContext", () => ({
  useAuth: () => ({
    logout: mocks.logout,
  }),
}));

vi.mock("@/features/test-analysis/context/AnalysisResultContext", () => ({
  useAnalysisResult: () => ({
    analysisResult: mocks.analysisResult,
    clearAnalysisResult: mocks.clearAnalysisResult,
    setAnalysisResult: vi.fn(),
  }),
}));

const completedResult = {
  analysis_request_id: "analysis-1",
  status: "completed",
  unit_status: "supported",
  unit: { id: "unit-1", code: "math-01", name: "わり算" },
  score: 8,
  max_score: 10,
  score_rate: 0.8,
  incorrect_question_numbers: ["1:2"],
  analysis_result: { patterns: [] },
  comment_title: "あと少し！",
  comment_body: "計算の確認を続けていきましょう。",
  message: null,
};

describe("AnalysisResult", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.analysisResult = null;
  });

  it("completed の分析結果を表示する", () => {
    mocks.analysisResult = completedResult;

    render(<AnalysisResult homeHref="/home" />);

    expect(screen.getByText("あと少し！")).toBeTruthy();
    expect(screen.getByText("計算の確認を続けていきましょう。")).toBeTruthy();
  });

  it("AIコメントをタイトル＋労いの1文と、残りの文に分けて表示する", () => {
    const commentBody =
      "テストの確認、お疲れさまです。今回は商を求めるところまでできています。17−5×3=2として、あまりを一緒に確かめてみてください。";
    mocks.analysisResult = {
      ...completedResult,
      comment_title: "あまりを一緒に確認してみましょう",
      comment_body: commentBody,
    };

    render(<AnalysisResult homeHref="/home" />);

    expect(
      screen.getByRole("heading", {
        level: 2,
        name: "あまりを一緒に確認してみましょう",
      }),
    ).toBeTruthy();
    expect(screen.getByText("テストの確認、お疲れさまです。")).toBeTruthy();
    expect(
      screen.getByText("今回は商を求めるところまでできています。"),
    ).toBeTruthy();
    expect(
      screen.getByText("として、あまりを一緒に確かめてみてください。", {
        exact: false,
      }).textContent,
    ).toBe("17−5×3=2として、あまりを一緒に確かめてみてください。");
    expect(screen.getByText("17−5×3=2").tagName).toBe("STRONG");

    const shownText = screen
      .getAllByRole("paragraph")
      .map((paragraph) => paragraph.textContent)
      .join("");
    expect(shownText).toBe(commentBody);
  });

  it.each([
    ["completed", completedResult],
    [
      "unsupported",
      { ...completedResult, status: "unsupported", comment_body: null },
    ],
    [
      "unit_undetermined",
      { ...completedResult, status: "unit_undetermined", comment_body: null },
    ],
    ["結果がない", null],
  ])("%s のときも「分析結果」の見出しを表示する", (_, analysisResult) => {
    mocks.analysisResult = analysisResult;

    render(<AnalysisResult homeHref="/home" />);

    expect(
      screen.getByRole("heading", { level: 1, name: "分析結果" }),
    ).toBeTruthy();
  });

  it("unsupported の表示を行う", () => {
    mocks.analysisResult = {
      analysis_request_id: "analysis-2",
      status: "unsupported",
      unit_status: "unsupported",
      unit: null,
      score: 0,
      max_score: 10,
      score_rate: 0,
      incorrect_question_numbers: null,
      analysis_result: null,
      comment_title: null,
      comment_body: null,
      message: null,
    };

    render(<AnalysisResult homeHref="/home" />);

    expect(screen.getByText("分析対象外")).toBeTruthy();
    expect(screen.getByText("利用回数は消費されません。")).toBeTruthy();
  });

  it("unit_undetermined の表示を行う", () => {
    mocks.analysisResult = {
      analysis_request_id: "analysis-3",
      status: "unit_undetermined",
      unit_status: "undetermined",
      unit: null,
      score: 0,
      max_score: 10,
      score_rate: 0,
      incorrect_question_numbers: null,
      analysis_result: null,
      comment_title: null,
      comment_body: null,
      message: null,
    };

    render(<AnalysisResult homeHref="/home" />);

    expect(screen.getByText("単元を特定できませんでした")).toBeTruthy();
  });

  it("分析結果が null の場合に案内を表示する", () => {
    render(<AnalysisResult homeHref="/home" />);

    expect(screen.getByText("分析結果を表示できません")).toBeTruthy();
    expect(screen.getByRole("button", { name: "ホームへ戻る" })).toBeTruthy();
  });

  it("ホームへ戻ると分析結果をクリアしてホームへ遷移する", () => {
    mocks.analysisResult = completedResult;

    render(<AnalysisResult homeHref="/home" />);

    fireEvent.click(screen.getByRole("button", { name: "ホームへ戻る" }));

    expect(mocks.clearAnalysisResult).toHaveBeenCalledOnce();
    expect(mocks.push).toHaveBeenCalledWith("/home");
  });

  it("ログアウト完了後に分析結果をクリアしてログイン画面へ置き換える", async () => {
    mocks.analysisResult = completedResult;
    let resolveLogout!: () => void;
    mocks.logout.mockImplementationOnce(
      () =>
        new Promise<void>((resolve) => {
          resolveLogout = resolve;
        }),
    );

    render(<AnalysisResult homeHref="/home" />);

    fireEvent.click(screen.getByRole("button", { name: "ログアウト" }));

    expect(mocks.clearAnalysisResult).not.toHaveBeenCalled();
    expect(mocks.replace).not.toHaveBeenCalled();

    resolveLogout();
    await waitFor(() => expect(mocks.replace).toHaveBeenCalledWith("/login"));
    expect(mocks.clearAnalysisResult).toHaveBeenCalledOnce();
    expect(mocks.logout).toHaveBeenCalledOnce();
    expect(mocks.push).not.toHaveBeenCalledWith("/login");
  });

  it("ログアウトに失敗した場合は分析結果画面に留まる", async () => {
    mocks.analysisResult = completedResult;
    mocks.logout.mockRejectedValueOnce(new Error("logout failed"));

    render(<AnalysisResult homeHref="/home" />);

    fireEvent.click(screen.getByRole("button", { name: "ログアウト" }));

    await waitFor(() => expect(mocks.logout).toHaveBeenCalledOnce());
    expect(mocks.clearAnalysisResult).not.toHaveBeenCalled();
    expect(mocks.replace).not.toHaveBeenCalled();
  });
});
