import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";

import type { StageAResponse } from "@/types/api";

import { ReviewStep } from "./ReviewStep";

const stageAResult: StageAResponse = {
  analysis_request_id: "analysis-1",
  status: "awaiting_confirmation",
  read_score: 8,
  read_unit_name: "わり算",
  expires_at: "2026-10-12T00:00:00Z",
  questions: [
    {
      question_id: "q1",
      image_index: 1,
      question_number: "1",
      problem_text: "12÷3",
      student_answer: "4",
      calculation_process: null,
      grading: "correct",
    },
  ],
};

function renderReviewStep() {
  const onComplete = vi.fn();
  render(
    <ReviewStep
      result={stageAResult}
      onComplete={onComplete}
      isSubmitting={false}
    />,
  );

  fireEvent.change(screen.getByLabelText("満点"), {
    target: { value: "10" },
  });

  return onComplete;
}

describe("ReviewStep", () => {
  test("解答だけを修正して、読み取った正誤はそのまま送信できる", () => {
    const onComplete = renderReviewStep();
    const answerConfirmation = screen.getByRole("group", {
      name: "解答内容は合っていますか？",
    });

    fireEvent.click(
      within(answerConfirmation).getByRole("button", { name: "× 違う" }),
    );
    fireEvent.change(screen.getByLabelText("子どもが実際に書いた解答"), {
      target: { value: "5" },
    });

    const gradingConfirmation = screen.getByRole("group", {
      name: "正誤は合っていますか？",
    });
    expect(
      within(gradingConfirmation)
        .getByRole("button", { name: "○ 合っている" })
        .getAttribute("aria-pressed"),
    ).toBe("true");

    fireEvent.click(
      screen.getByRole("button", { name: "確認完了して分析する" }),
    );

    expect(onComplete).toHaveBeenCalledOnce();
    expect(onComplete).toHaveBeenCalledWith({
      score: 8,
      max_score: 10,
      read_unit_name: "わり算",
      confirmed_questions: [
        expect.objectContaining({
          question_id: "q1",
          student_answer: "5",
          grading: "correct",
        }),
      ],
    });
  });

  test("正誤だけを修正して、読み取った解答はそのまま送信できる", () => {
    const onComplete = renderReviewStep();
    const gradingConfirmation = screen.getByRole("group", {
      name: "正誤は合っていますか？",
    });

    fireEvent.click(
      within(gradingConfirmation).getByRole("button", { name: "× 違う" }),
    );
    fireEvent.click(
      within(
        screen.getByRole("group", {
          name: "実際の正誤を選んでください",
        }),
      ).getByRole("button", { name: "× 不正解" }),
    );
    fireEvent.click(
      screen.getByRole("button", { name: "確認完了して分析する" }),
    );

    expect(onComplete).toHaveBeenCalledOnce();
    expect(onComplete).toHaveBeenCalledWith({
      score: 8,
      max_score: 10,
      read_unit_name: "わり算",
      confirmed_questions: [
        expect.objectContaining({
          question_id: "q1",
          student_answer: "4",
          grading: "incorrect",
        }),
      ],
    });
  });

  test("得点と満点が有効な整数の範囲になるまで送信できない", () => {
    render(
      <ReviewStep
        result={stageAResult}
        onComplete={vi.fn()}
        isSubmitting={false}
      />,
    );
    const score = screen.getByLabelText("得点");
    const maxScore = screen.getByLabelText("満点");
    const submit = screen.getByRole("button", {
      name: "確認完了して分析する",
    }) as HTMLButtonElement;

    fireEvent.change(maxScore, { target: { value: "0" } });
    expect(
      screen.getByText("満点は1以上の整数で入力してください。"),
    ).toBeDefined();
    expect(submit.disabled).toBe(true);

    fireEvent.change(maxScore, { target: { value: "10" } });
    fireEvent.change(score, { target: { value: "-1" } });
    expect(
      screen.getByText("得点は0以上の整数で入力してください。"),
    ).toBeDefined();
    expect(submit.disabled).toBe(true);

    fireEvent.change(score, { target: { value: "11" } });
    expect(
      screen.getByText("得点は満点以下で入力してください。"),
    ).toBeDefined();
    expect(submit.disabled).toBe(true);

    fireEvent.change(score, { target: { value: "8" } });
    expect(submit.disabled).toBe(false);
  });
});
