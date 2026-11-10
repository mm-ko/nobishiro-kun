"use client";

import { useState, type FormEvent } from "react";

import { Button } from "@/components/Button";
import { Card } from "@/components/Card";
import { TextField } from "@/components/TextField";
import type {
  Grading,
  StageAQuestion,
  StageAResponse,
  StageBRequest,
} from "@/types/api";

import {
  buildStageBRequest,
  type QuestionReview,
} from "../utils/stageBRequest";

import styles from "./ReviewStep.module.css";

type ReviewStepProps = {
  result: StageAResponse;
  onComplete: (request: StageBRequest) => void | Promise<void>;
  isSubmitting: boolean;
};

function createInitialReviews(
  questions: StageAQuestion[],
): Record<string, QuestionReview> {
  return Object.fromEntries(
    questions.map((question) => [
      question.question_id,
      {
        answerConfirmation:
          question.student_answer === null ? "differs" : "matches",
        correctedAnswer: "",
        isBlankAnswer: false,
        gradingConfirmation:
          question.grading === "unknown" ? "differs" : "matches",
        correctedGrading: null,
      },
    ]),
  );
}

function parseNonNegativeInteger(value: string): number | null {
  if (!/^\d+$/.test(value)) {
    return null;
  }

  const parsedValue = Number(value);
  return Number.isSafeInteger(parsedValue) ? parsedValue : null;
}

function formatAnswer(answer: string | null): string {
  if (answer === null) {
    return "読み取れませんでした";
  }

  if (answer === "") {
    return "空欄";
  }

  return answer;
}

function formatGrading(grading: Grading): string {
  switch (grading) {
    case "correct":
      return "○ 正解";
    case "incorrect":
      return "× 不正解";
    case "unknown":
      return "読み取れませんでした";
  }
}

function getMissingMessages(
  review: QuestionReview | undefined,
  question: StageAQuestion,
  label: string,
): string[] {
  if (!review) {
    return [`${label}の確認が完了していません。`];
  }

  const messages: string[] = [];

  const answerNeedsInput =
    question.student_answer === null || review.answerConfirmation === "differs";

  if (
    answerNeedsInput &&
    !review.isBlankAnswer &&
    review.correctedAnswer.trim().length === 0
  ) {
    messages.push(
      `${label}の実際の解答を入力するか、空欄だったことを選んでください。`,
    );
  }

  const gradingNeedsInput =
    question.grading === "unknown" || review.gradingConfirmation === "differs";

  if (gradingNeedsInput && review.correctedGrading === null) {
    messages.push(`${label}の正解・不正解を選んでください。`);
  }

  return messages;
}

export function ReviewStep({
  result,
  onComplete,
  isSubmitting,
}: ReviewStepProps) {
  const [score, setScore] = useState(
    result.read_score === null ? "" : String(result.read_score),
  );
  const [maxScore, setMaxScore] = useState("");
  const [reviews, setReviews] = useState(() =>
    createInitialReviews(result.questions),
  );
  const [formError, setFormError] = useState<string | null>(null);

  const scoreValue = parseNonNegativeInteger(score);
  const maxScoreValue = parseNonNegativeInteger(maxScore);

  const scoreError =
    score.length > 0 && scoreValue === null
      ? "得点は0以上の整数で入力してください。"
      : scoreValue !== null &&
          maxScoreValue !== null &&
          scoreValue > maxScoreValue
        ? "得点は満点以下で入力してください。"
        : undefined;

  const maxScoreError =
    maxScore.length > 0 && (maxScoreValue === null || maxScoreValue < 1)
      ? "満点は1以上の整数で入力してください。"
      : undefined;

  const scoreMessages: string[] = [];

  if (scoreValue === null) {
    scoreMessages.push("得点を入力してください。");
  }

  if (maxScoreValue === null || maxScoreValue < 1) {
    scoreMessages.push("満点を入力してください。");
  }

  if (
    scoreValue !== null &&
    maxScoreValue !== null &&
    maxScoreValue >= 1 &&
    scoreValue > maxScoreValue
  ) {
    scoreMessages.push("得点は満点以下にしてください。");
  }

  const questionMessages = result.questions.flatMap((question, index) =>
    getMissingMessages(
      reviews[question.question_id],
      question,
      `${question.image_index}:${question.question_number ?? index + 1}`,
    ),
  );

  const missingMessages = [...scoreMessages, ...questionMessages];

  const canSubmit = result.questions.length > 0 && missingMessages.length === 0;

  const updateReview = (
    questionId: string,
    update: Partial<QuestionReview>,
  ) => {
    setReviews((currentReviews) => ({
      ...currentReviews,
      [questionId]: {
        ...currentReviews[questionId],
        ...update,
      },
    }));

    setFormError(null);
  };

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    if (!canSubmit || scoreValue === null || maxScoreValue === null) {
      setFormError(
        "すべての問題の確認と、得点・配点の入力を完了してください。",
      );
      return;
    }

    const request = buildStageBRequest(
      result,
      scoreValue,
      maxScoreValue,
      reviews,
    );

    void Promise.resolve(onComplete(request)).catch(() => {
      // 送信エラーの表示は親コンポーネントの UI-006B に任せる。
    });
  };

  return (
    <form className={styles.form} onSubmit={handleSubmit} noValidate>
      <header className={styles.header}>
        <p className={styles.eyebrow}>AI読み取り結果</p>
        <h1>AIの読み取りを確認</h1>
        <p>テストと見比べて、違うところだけ押してください。</p>
      </header>

      <Card title="テストの点数">
        <p className={styles.cardDescription}>
          得点はAIの読み取り値を表示しています。満点とあわせて確認してください。
        </p>

        <div className={styles.scoreFields}>
          <TextField
            id="score"
            disabled={isSubmitting}
            label="得点"
            type="number"
            inputMode="numeric"
            min={0}
            step={1}
            value={score}
            error={scoreError}
            onChange={(event) => {
              setScore(event.target.value);
              setFormError(null);
            }}
          />

          <TextField
            id="max-score"
            label="満点"
            type="number"
            inputMode="numeric"
            min={1}
            step={1}
            value={maxScore}
            error={maxScoreError}
            disabled={isSubmitting}
            onChange={(event) => {
              setMaxScore(event.target.value);
              setFormError(null);
            }}
          />
        </div>
      </Card>

      <div className={styles.questionList}>
        {result.questions.map((question, index) => {
          const review = reviews[question.question_id];

          if (!review) {
            return null;
          }

          const answerUnreadable = question.student_answer === null;
          const gradingUnreadable = question.grading === "unknown";

          const answerNeedsCorrection =
            answerUnreadable || review.answerConfirmation === "differs";

          const gradingNeedsCorrection =
            gradingUnreadable || review.gradingConfirmation === "differs";

          return (
            <Card
              key={question.question_id}
              title={`${question.image_index}:${question.question_number ?? index + 1}`}
            >
              {question.problem_text && (
                <p className={styles.problemText}>{question.problem_text}</p>
              )}

              <div className={styles.readingBlock}>
                <p className={styles.readingLabel}>読み取った解答</p>
                <p className={styles.readingValue}>
                  {formatAnswer(question.student_answer)}
                </p>
              </div>

              {answerUnreadable ? (
                <p className={styles.guidance}>
                  解答が読み取れませんでした。実際の解答を入力するか、空欄だったことを選んでください。
                </p>
              ) : (
                <fieldset className={styles.fieldset}>
                  <legend>解答内容は合っていますか？</legend>

                  <div className={styles.choiceGrid}>
                    <button
                      className={styles.choiceButton}
                      type="button"
                      disabled={isSubmitting}
                      aria-pressed={review.answerConfirmation === "matches"}
                      onClick={() =>
                        updateReview(question.question_id, {
                          answerConfirmation: "matches",
                          correctedAnswer: "",
                          isBlankAnswer: false,
                        })
                      }
                    >
                      ○ 合っている
                    </button>

                    <button
                      className={styles.choiceButton}
                      type="button"
                      disabled={isSubmitting}
                      aria-pressed={review.answerConfirmation === "differs"}
                      onClick={() =>
                        updateReview(question.question_id, {
                          answerConfirmation: "differs",
                        })
                      }
                    >
                      × 違う
                    </button>
                  </div>
                </fieldset>
              )}

              {answerNeedsCorrection && (
                <div className={styles.answerCorrection}>
                  <TextField
                    id={`corrected-answer-${index}`}
                    disabled={isSubmitting || review.isBlankAnswer}
                    label="子どもが実際に書いた解答"
                    value={review.correctedAnswer}
                    error={
                      !review.isBlankAnswer &&
                      review.correctedAnswer.trim().length === 0
                        ? "実際の解答を入力するか、空欄だったことを選んでください。"
                        : undefined
                    }
                    onChange={(event) =>
                      updateReview(question.question_id, {
                        correctedAnswer: event.target.value,
                        isBlankAnswer: false,
                      })
                    }
                  />

                  <button
                    className={styles.choiceButton}
                    type="button"
                    disabled={isSubmitting}
                    aria-pressed={review.isBlankAnswer}
                    onClick={() =>
                      updateReview(question.question_id, {
                        correctedAnswer: "",
                        isBlankAnswer: !review.isBlankAnswer,
                      })
                    }
                  >
                    実際は空欄だった
                  </button>
                </div>
              )}

              <div className={styles.readingBlock}>
                <p className={styles.readingLabel}>読み取った正誤</p>
                <p className={styles.readingValue}>
                  {formatGrading(question.grading)}
                </p>
              </div>

              {gradingUnreadable ? (
                <p className={styles.guidance}>
                  正誤が読み取れませんでした。正解か不正解かを選んでください。
                </p>
              ) : (
                <fieldset className={styles.fieldset}>
                  <legend>正誤は合っていますか？</legend>

                  <div className={styles.choiceGrid}>
                    <button
                      className={styles.choiceButton}
                      type="button"
                      disabled={isSubmitting}
                      aria-pressed={review.gradingConfirmation === "matches"}
                      onClick={() =>
                        updateReview(question.question_id, {
                          gradingConfirmation: "matches",
                          correctedGrading: null,
                        })
                      }
                    >
                      ○ 合っている
                    </button>

                    <button
                      className={styles.choiceButton}
                      type="button"
                      disabled={isSubmitting}

                      aria-pressed={review.gradingConfirmation === "differs"}
                      onClick={() =>
                        updateReview(question.question_id, {
                          gradingConfirmation: "differs",
                        })
                      }
                    >
                      × 違う
                    </button>
                  </div>
                </fieldset>
              )}

              {gradingNeedsCorrection && (
                <fieldset className={styles.fieldset}>
                  <legend>実際の正誤を選んでください</legend>

                  <div className={styles.choiceGrid}>
                    <button
                      className={styles.choiceButton}
                      type="button"
                      disabled={isSubmitting}
                      aria-pressed={review.correctedGrading === "correct"}
                      onClick={() =>
                        updateReview(question.question_id, {
                          correctedGrading: "correct",
                        })
                      }
                    >
                      ○ 正解
                    </button>

                    <button
                      className={styles.choiceButton}
                      type="button"
                      disabled={isSubmitting}
                      aria-pressed={review.correctedGrading === "incorrect"}
                      onClick={() =>
                        updateReview(question.question_id, {
                          correctedGrading: "incorrect",
                        })
                      }
                    >
                      × 不正解
                    </button>
                  </div>

                  {review.correctedGrading === null && (
                    <p className={styles.fieldError}>
                      正解か不正解を選択してください。
                    </p>
                  )}
                </fieldset>
              )}
            </Card>
          );
        })}
      </div>

      {formError && (
        <p className={styles.formError} role="alert">
          {formError}
        </p>
      )}

      {!canSubmit && missingMessages.length > 0 && (
        <div className={styles.completionHint} aria-live="polite">
          <p>先へ進むために、次をご確認ください。</p>
          <ul>
            {missingMessages.map((message) => (
              <li key={message}>{message}</li>
            ))}
          </ul>
        </div>
      )}

      <Button type="submit" disabled={!canSubmit || isSubmitting}>
        {isSubmitting ? "送信中..." : "確認完了して分析する"}
      </Button>
    </form>
  );
}
