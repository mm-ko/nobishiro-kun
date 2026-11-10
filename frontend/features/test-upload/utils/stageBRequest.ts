import type { Grading, StageAResponse, StageBRequest } from "@/types/api";

export type QuestionReview = {
  answerConfirmation: "matches" | "differs";
  correctedAnswer: string;
  isBlankAnswer: boolean;
  gradingConfirmation: "matches" | "differs";
  correctedGrading: Exclude<Grading, "unknown"> | null;
};

export function buildStageBRequest(
  result: StageAResponse,
  score: number,
  maxScore: number,
  reviews: Record<string, QuestionReview>,
): StageBRequest {
  return {
    score,
    max_score: maxScore,
    read_unit_name: result.read_unit_name,
    confirmed_questions: result.questions.map((question) => {
      const review = reviews[question.question_id];

      if (!review) {
        throw new Error("問題の確認結果がありません。");
      }

      const studentAnswer =
        question.student_answer === null ||
        review.answerConfirmation === "differs"
          ? review.isBlankAnswer
            ? ""
            : review.correctedAnswer.trim()
          : question.student_answer;

      const grading =
        question.grading === "unknown" ||
        review.gradingConfirmation === "differs"
          ? review.correctedGrading
          : question.grading;

      if (grading === null) {
        throw new Error("正誤が確定していません。");
      }

      return {
        question_id: question.question_id,
        image_index: question.image_index,
        question_number: question.question_number,
        problem_text: question.problem_text,
        student_answer: studentAnswer,
        calculation_process: question.calculation_process,
        grading,
      };
    }),
  };
}
