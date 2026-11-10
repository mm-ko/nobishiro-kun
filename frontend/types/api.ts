// API設計書（#8）のレスポンスの形に合わせた型。
// キー名はAPI設計書どおり snake_case のまま（本物のAPIにつなぐときに変換が要らないようにする）。

export type Grading = "correct" | "incorrect" | "unknown";

export type Unit = { id: string; code: string; name: string };

/** ユーザー初期登録・取得（3.1） */
export type UserResponse = { id: string; created_at: string };

/** Stage A：画像からの事実抽出（3.3） */
export type StageAQuestion = {
  question_id: string;
  image_index: 1 | 2;
  question_number: string | null; // 用紙上の問題番号（例："1(1)"）
  problem_text: string;
  student_answer: string | null; // 空欄は空文字、読み取り不明は null
  calculation_process: string | null;
  grading: Grading;
};

export type StageAResponse = {
  analysis_request_id: string;
  status: "awaiting_confirmation";
  read_score: number | null; // 読み取れない場合は null
  read_unit_name: string | null;
  questions: StageAQuestion[];
  expires_at: string;
};

/** Stage B：確認済みデータの分析（3.4）リクエスト */
export type ConfirmedQuestion = {
  question_id: string;
  image_index: 1 | 2;
  question_number: string | null;
  problem_text: string;
  student_answer: string; // 確認後は空欄を空文字で表す（null は許可されない）
  calculation_process: string | null;
  grading: "correct" | "incorrect"; // unknown のままでは送れない
};

export type StageBRequest = {
  score: number;
  max_score: number;
  read_unit_name: string | null;
  confirmed_questions: ConfirmedQuestion[];
};

/** Stage B：分析結果（3.4）。デモは completed のみ */
export type AnalysisPattern = {
  pattern: string;
  cause_type:
    | "blank"
    | "careless_mistake"
    | "possible_understanding_gap"
    | "undetermined";
  question_numbers: string[]; // 保存用表記「画像番号:問題番号」（例："1:1(1)"）
  explanation: string;
};

export type StageBCompletedResponse = {
  analysis_request_id: string;
  status: "completed";
  unit_status: "supported";
  unit: Unit;
  score: number;
  max_score: number;
  score_rate: number;
  incorrect_question_numbers: string[];
  analysis_result: { patterns: AnalysisPattern[] };
  comment_title: string;
  comment_body: string;
  message: string | null;
};

/** Stage B：分析対象外のレスポンス */
export type StageBUnsupportedResponse = {
  analysis_request_id: string;
  status: "unsupported";
  unit_status: "unsupported";
  unit: null;
  score: number;
  max_score: number;
  score_rate: number;
  incorrect_question_numbers: null;
  analysis_result: null;
  comment_title: null;
  comment_body: null;
  message: string | null;
};

/** Stage B：単元を特定できない場合のレスポンス */
export type StageBUndeterminedResponse = {
  analysis_request_id: string;
  status: "unit_undetermined";
  unit_status: "undetermined";
  unit: null;
  score: number;
  max_score: number;
  score_rate: number;
  incorrect_question_numbers: null;
  analysis_result: null;
  comment_title: null;
  comment_body: null;
  message: string | null;
};

/** Stage B：結果画面で扱う3種類のレスポンス */
export type StageBResultResponse =
  | StageBCompletedResponse
  | StageBUnsupportedResponse
  | StageBUndeterminedResponse;

/** 学習履歴一覧（3.6） */
export type AnalysisRecordItem = {
  id: string;
  recorded_at: string; // UTC。画面で日本時間に変換する
  unit: { code: string; name: string };
  score: number;
  max_score: number;
};

export type AnalysisRecordsResponse = {
  items: AnalysisRecordItem[];
  limit: number;
  offset: number;
  has_more: boolean;
};

/** 苦手単元ランキング（3.7） */
export type UnitRankingItem = {
  rank: number;
  unit: { code: string; name: string };
  average_score_rate: number;
  record_count: number;
};

export type UnitRankingsResponse = { items: UnitRankingItem[] };

/** 分析できない理由（GET /v1/usage の blocked_reason）。分析できるときは null */
export type UsageBlockedReason = "plan_required" | "monthly_limit_reached";

/** 利用状況（GET /v1/usage）。分析できるかは BE が判定する。FE は blocked_reason で表示を切り替える */
export type UsageResponse = {
  can_analyze: boolean;
  used_count: number;
  free_limit: number;
  blocked_reason: UsageBlockedReason | null;
};

/** Stripe Checkout作成（POST /v1/billing/checkout-sessions） */
export type CheckoutSessionResponse = {
  checkout_url: string;
};

/** 現在の契約状態（GET /v1/subscriptions/current） */
export type CurrentSubscriptionResponse = {
  is_subscribed: boolean;
  status: string | null;
  current_period_end: string | null;
};
