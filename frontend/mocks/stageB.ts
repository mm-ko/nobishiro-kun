// ④ 2回目のAI分析結果（Stage B・UI-007）
// API設計書 3.4 に合わせて、completed・unsupported・unit_undetermined の各結果を定義する。
import { MOCK_ANALYSIS_REQUEST_ID } from "./stageA";
import type {
  StageBCompletedResponse,
  StageBUnsupportedResponse,
  StageBUndeterminedResponse,
} from "@/types/api";

export const mockStageBCompletedResponse: StageBCompletedResponse = {
  analysis_request_id: MOCK_ANALYSIS_REQUEST_ID,
  status: "completed",
  unit_status: "supported",
  unit: { id: "1", code: "division", name: "わり算" },
  score: 80,
  max_score: 100,
  score_rate: 80.0,
  incorrect_question_numbers: ["1:1(1)"],
  analysis_result: {
    patterns: [
      {
        pattern: "あまりの計算ミス",
        cause_type: "undetermined",
        question_numbers: ["1:1(1)"],
        explanation: "商は合っていますが、あまりの値に誤りが見られます。",
      },
    ],
  },
  comment_title: "あまりを一緒に確認してみましょう",
  comment_body:
    "テストの確認、お疲れさまです。今回は商を求めるところまでできています。割る数と商を掛け、元の数から引く手順を一緒に確かめてみましょう。",
  message: null,
};

/** UI-007 動作確認用：分析対象外 */
export const mockStageBUnsupportedResponse: StageBUnsupportedResponse = {
  analysis_request_id: MOCK_ANALYSIS_REQUEST_ID,
  status: "unsupported",
  unit_status: "unsupported",
  unit: null,
  score: 80,
  max_score: 100,
  score_rate: 80,
  incorrect_question_numbers: null,
  analysis_result: null,
  comment_title: null,
  comment_body: null,
  message:
    "このテストの単元は分析対象外のため、分析を終了します。利用回数は消費されません。",
};

/** UI-007 動作確認用：単元を特定できない場合 */
export const mockStageBUndeterminedResponse: StageBUndeterminedResponse = {
  analysis_request_id: MOCK_ANALYSIS_REQUEST_ID,
  status: "unit_undetermined",
  unit_status: "undetermined",
  unit: null,
  score: 80,
  max_score: 100,
  score_rate: 80,
  incorrect_question_numbers: null,
  analysis_result: null,
  comment_title: null,
  comment_body: null,
  message:
    "このテストの単元を特定できなかったため、分析を終了します。利用回数は消費されません。",
};
