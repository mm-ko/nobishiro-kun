// ② テスト画像（ダミー）と ③ 1回目のAI結果（Stage A・UI-005 → UI-006）
// 形は API設計書 3.3 に合わせている。ストーリーは「5問中1問まちがい＝80点」。
import type { StageAQuestion, StageAResponse } from "@/types/api";

/** デモ用のダミー答案画像（frontend/public/mocks/ に置く。個人情報なし・自作） */
export const mockTestImagePath = "/mocks/sample-test.png";

export const MOCK_ANALYSIS_REQUEST_ID = "d85a0a9f-1234-4a56-8b90-123456789abc";

export const mockStageAResponse: StageAResponse = {
  analysis_request_id: MOCK_ANALYSIS_REQUEST_ID,
  status: "awaiting_confirmation",
  read_score: 80,
  read_unit_name: "あまりのあるわり算",
  questions: [
    {
      question_id: "q1",
      image_index: 1,
      question_number: "1(1)",
      problem_text: "17÷5",
      student_answer: "3あまり3",
      calculation_process: null,
      grading: "incorrect",
    },
    {
      question_id: "q2",
      image_index: 1,
      question_number: "1(2)",
      problem_text: "23÷4",
      student_answer: "5あまり3",
      calculation_process: null,
      grading: "correct",
    },
    {
      question_id: "q3",
      image_index: 1,
      question_number: "2(1)",
      problem_text: "48÷6",
      student_answer: "8",
      calculation_process: null,
      grading: "correct",
    },
    {
      question_id: "q4",
      image_index: 1,
      question_number: "2(2)",
      problem_text: "50÷7",
      student_answer: "7あまり1",
      calculation_process: null,
      grading: "correct",
    },
    {
      question_id: "q5",
      image_index: 1,
      question_number: "3",
      problem_text: "39÷8",
      student_answer: "4あまり7",
      calculation_process: null,
      grading: "correct",
    },
  ],
  expires_at: "2026-12-31T00:00:00Z",
};

/**
 * 開発中の確認用：「読み取れなかった」ケースを含むサンプル（デモでは使わない）。
 * デモ用の mockStageAResponse をもとに、次の3つだけを変えている。
 * - 得点が読み取れなかった（read_score が null）
 * - q2：正誤が読み取れなかった（grading が "unknown"）
 * - q4：解答が読み取れなかった（student_answer が null）
 * 使い方は mocks/README.md の「不明を含むサンプルに差し替える」を参照。
 */
export const mockStageAResponseWithUnknown: StageAResponse = {
  ...mockStageAResponse,
  read_score: null,
  questions: mockStageAResponse.questions.map((question): StageAQuestion => {
    if (question.question_id === "q2") {
      return { ...question, grading: "unknown" };
    }
    if (question.question_id === "q4") {
      return { ...question, student_answer: null };
    }
    return question;
  }),
};
