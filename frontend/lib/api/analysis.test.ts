import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import type {
  StageAResponse,
  StageBCompletedResponse,
  StageBRequest,
} from "@/types/api";

import {
  getStageAErrorMessage,
  getStageBErrorMessage,
  shouldGoToPlanAfterAnalysisError,
  shouldReturnHomeAfterStageAError,
  shouldReturnHomeAfterStageBError,
  StageARequestError,
  StageBRequestError,
  startStageA,
  submitStageB,
} from "./analysis";

const firebaseAuthMocks = vi.hoisted(() => ({
  getIdToken: vi.fn(),
  logoutFromFirebase: vi.fn(),
}));

vi.mock("@/lib/firebase/auth", () => ({
  getCurrentFirebaseUser: () => ({
    getIdToken: firebaseAuthMocks.getIdToken,
  }),
  logoutFromFirebase: firebaseAuthMocks.logoutFromFirebase,
}));
const fetchMock = vi.fn<typeof fetch>();

const validStageAResponse = {
  analysis_request_id: "analysis-1",
  status: "awaiting_confirmation",
  read_score: 80,
  read_unit_name: "わり算",
  questions: [
    {
      question_id: "question-1",
      image_index: 1,
      question_number: "1",
      problem_text: "12÷3",
      student_answer: "4",
      calculation_process: null,
      grading: "correct",
    },
  ],
  expires_at: "2026-10-15T12:00:00Z",
} satisfies StageAResponse;

const stageBRequest = {
  score: 80,
  max_score: 100,
  read_unit_name: "わり算",
  confirmed_questions: [
    {
      question_id: "question-1",
      image_index: 1,
      question_number: "1",
      problem_text: "12÷3",
      student_answer: "5",
      calculation_process: null,
      grading: "incorrect",
    },
  ],
} satisfies StageBRequest;

const validStageBResponse = {
  analysis_request_id: "analysis-1",
  status: "completed",
  unit_status: "supported",
  unit: { id: "1", code: "division", name: "わり算" },
  score: 80,
  max_score: 100,
  score_rate: 80,
  incorrect_question_numbers: ["1:1"],
  analysis_result: {
    patterns: [
      {
        pattern: "わり算の計算ミス",
        cause_type: "careless_mistake",
        question_numbers: ["1:1"],
        explanation: "商の値に誤りが見られます。",
      },
    ],
  },
  comment_title: "テストの確認、お疲れさまです",
  comment_body:
    "確認できた間違え方を参考に、一緒に問題を振り返ってみましょう。",
  message: null,
} satisfies StageBCompletedResponse;

async function getRejectedError(request: Promise<unknown>): Promise<unknown> {
  return request.then(
    () => {
      throw new Error("リクエストが失敗しませんでした。");
    },
    (error: unknown) => error,
  );
}

function getLastRequest(): Parameters<typeof fetch> {
  const request = fetchMock.mock.calls.at(-1);
  if (!request) {
    throw new Error("fetchが呼ばれていません。");
  }

  return request;
}

describe("analysis API", () => {
  beforeEach(() => {
    fetchMock.mockReset();
    firebaseAuthMocks.getIdToken.mockReset();
    firebaseAuthMocks.getIdToken.mockResolvedValue("firebase-id-token");
    firebaseAuthMocks.logoutFromFirebase.mockReset();
    firebaseAuthMocks.logoutFromFirebase.mockResolvedValue(undefined);
    vi.stubEnv("NEXT_PUBLIC_API_BASE_URL", "http://localhost:8000/");
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
  });

  test("Stage A APIへ画像とIdempotency-Keyを送信する", async () => {
    fetchMock.mockResolvedValue(
      Response.json(validStageAResponse, { status: 201 }),
    );

    const image = new File(["image-data"], "test.png", {
      type: "image/png",
    });
    const response = await startStageA([image], {
      idempotencyKey: "request-key-1",
    });
    const [requestUrl, requestOptions] = getLastRequest();
    const headers = new Headers(requestOptions?.headers);
    const body = requestOptions?.body;

    expect(response).toEqual(validStageAResponse);
    expect(requestUrl).toBe("http://localhost:8000/v1/analyses");
    expect(requestOptions?.method).toBe("POST");
    expect(headers.get("Idempotency-Key")).toBe("request-key-1");
    expect(headers.get("Authorization")).toBe("Bearer firebase-id-token");
    expect(body).toBeInstanceOf(FormData);
    expect((body as FormData).getAll("images")).toEqual([image]);
  });

  test("APIエラーコードを画面表示用メッセージへ変換する", async () => {
    fetchMock.mockResolvedValue(
      Response.json({ error: { code: "IMAGE_TOO_LARGE" } }, { status: 413 }),
    );

    const error = await getRejectedError(
      startStageA([new File(["image-data"], "test.png")], {
        idempotencyKey: "request-key-2",
      }),
    );

    expect(error).toBeInstanceOf(StageARequestError);
    expect((error as StageARequestError).code).toBe("IMAGE_TOO_LARGE");
    expect(getStageAErrorMessage(error)).toBe(
      "画像の容量が上限を超えています。画像を選び直してください。",
    );
  });

  test("レート制限時は合意した再試行メッセージを返す", () => {
    const error = new StageARequestError(
      "RATE_LIMIT_EXCEEDED",
      "Stage Aのリクエストに失敗しました。",
    );

    expect(getStageAErrorMessage(error)).toBe(
      "現在、一時的に分析を利用できません。少し時間をおいてから、もう一度お試しください。",
    );
  });

  test("Stage Aで月の上限に達していたら、上限の案内を返し、ホームへ戻るだけにする", async () => {
    fetchMock.mockResolvedValue(
      Response.json(
        { error: { code: "MONTHLY_LIMIT_REACHED" } },
        { status: 403 },
      ),
    );

    const error = await getRejectedError(
      startStageA([new File(["image-data"], "test.png")], {
        idempotencyKey: "request-key-4",
      }),
    );

    expect(error).toBeInstanceOf(StageARequestError);
    expect((error as StageARequestError).code).toBe("MONTHLY_LIMIT_REACHED");
    expect(getStageAErrorMessage(error)).toBe(
      "今月の分析回数の上限に達しました。来月1日から、また分析できます。",
    );
    expect(shouldReturnHomeAfterStageAError(error)).toBe(true);
    expect(shouldGoToPlanAfterAnalysisError(error)).toBe(false);
  });

  test("再試行できるStage Aのエラーは、ホームへ戻るだけにしない", () => {
    for (const code of [
      "RATE_LIMIT_EXCEEDED",
      "IMAGE_UNREADABLE",
      "INTERNAL_ERROR",
    ]) {
      expect(
        shouldReturnHomeAfterStageAError(
          new StageARequestError(code, "Stage Aのリクエストに失敗しました。"),
        ),
      ).toBe(false);
    }

    expect(shouldReturnHomeAfterStageAError(new Error("通信エラー"))).toBe(
      false,
    );
  });

  test("Stage A・Stage BのPLAN_REQUIREDは、有料案内へ移動する", () => {
    expect(
      shouldGoToPlanAfterAnalysisError(
        new StageARequestError(
          "PLAN_REQUIRED",
          "Stage Aのリクエストに失敗しました。",
        ),
      ),
    ).toBe(true);
    expect(
      shouldGoToPlanAfterAnalysisError(
        new StageBRequestError(
          "PLAN_REQUIRED",
          "Stage Bのリクエストに失敗しました。",
        ),
      ),
    ).toBe(true);
  });

  test("PLAN_REQUIRED以外のエラーでは、有料案内へ移動しない", () => {
    for (const error of [
      new StageARequestError(
        "RATE_LIMIT_EXCEEDED",
        "Stage Aのリクエストに失敗しました。",
      ),
      new StageBRequestError(
        "MONTHLY_LIMIT_REACHED",
        "Stage Bのリクエストに失敗しました。",
      ),
      new Error("通信エラー"),
    ]) {
      expect(shouldGoToPlanAfterAnalysisError(error)).toBe(false);
    }
  });

  test("Stage Aレスポンス形式が不正な場合はエラーにする", async () => {
    fetchMock.mockResolvedValue(
      Response.json({
        ...validStageAResponse,
        questions: [
          { ...validStageAResponse.questions[0], problem_text: null },
        ],
      }),
    );

    const error = await getRejectedError(
      startStageA([new File(["image-data"], "test.png")], {
        idempotencyKey: "request-key-3",
      }),
    );

    expect(error).toBeInstanceOf(StageARequestError);
    expect((error as StageARequestError).code).toBe("AI_RESPONSE_INVALID");
  });

  test("Stage B APIへ確認済みデータとIdempotency-Keyを送信する", async () => {
    fetchMock.mockResolvedValue(Response.json(validStageBResponse));

    const response = await submitStageB("analysis-1", stageBRequest, {
      idempotencyKey: "stage-b-key-1",
    });
    const [requestUrl, requestOptions] = getLastRequest();
    const headers = new Headers(requestOptions?.headers);

    expect(response).toEqual(validStageBResponse);
    expect(requestUrl).toBe(
      "http://localhost:8000/v1/analyses/analysis-1/result",
    );
    expect(requestOptions?.method).toBe("POST");
    expect(headers.get("Idempotency-Key")).toBe("stage-b-key-1");
    expect(headers.get("Content-Type")).toBe("application/json");
    expect(headers.get("Authorization")).toBe("Bearer firebase-id-token");
    expect(JSON.parse(String(requestOptions?.body))).toEqual(stageBRequest);
  });

  test("Stage BのAPIエラーコードを画面表示用メッセージへ変換する", async () => {
    fetchMock.mockResolvedValue(
      Response.json({ error: { code: "VALIDATION_ERROR" } }, { status: 422 }),
    );

    const error = await getRejectedError(
      submitStageB("analysis-1", stageBRequest, {
        idempotencyKey: "stage-b-key-2",
      }),
    );

    expect(error).toBeInstanceOf(StageBRequestError);
    expect((error as StageBRequestError).code).toBe("VALIDATION_ERROR");
    expect(getStageBErrorMessage(error)).toBe(
      "確認内容に誤りがあります。確認画面へ戻って、得点や正誤を確認してください。",
    );
  });

  test("Stage Bの分析処理が続けられないエラーは、ホームからのやり直しを案内する", () => {
    for (const code of [
      "ANALYSIS_NOT_FOUND",
      "ANALYSIS_EXPIRED",
      "ANALYSIS_STATE_CONFLICT",
    ]) {
      const error = new StageBRequestError(
        code,
        "Stage Bのリクエストに失敗しました。",
      );

      expect(getStageBErrorMessage(error)).toBe(
        "分析を続けられませんでした。お手数ですが、ホームへ戻り、テスト画像のアップロードからやり直してください。",
      );
      expect(shouldReturnHomeAfterStageBError(error)).toBe(true);
    }
  });

  test("Stage Bで月の上限に達していたら、上限の案内を返し、ホームへ戻るだけにする", async () => {
    fetchMock.mockResolvedValue(
      Response.json(
        { error: { code: "MONTHLY_LIMIT_REACHED" } },
        { status: 403 },
      ),
    );

    const error = await getRejectedError(
      submitStageB("analysis-1", stageBRequest, {
        idempotencyKey: "stage-b-key-6",
      }),
    );

    expect(error).toBeInstanceOf(StageBRequestError);
    expect((error as StageBRequestError).code).toBe("MONTHLY_LIMIT_REACHED");
    expect(getStageBErrorMessage(error)).toBe(
      "今月の分析回数の上限に達しました。来月1日から、また分析できます。",
    );
    expect(shouldReturnHomeAfterStageBError(error)).toBe(true);
  });

  test("再試行できるStage Bのエラーは、ホームへ戻るだけにしない", () => {
    for (const code of [
      "VALIDATION_ERROR",
      "ANALYSIS_TIMEOUT",
      "INTERNAL_ERROR",
    ]) {
      expect(
        shouldReturnHomeAfterStageBError(
          new StageBRequestError(code, "Stage Bのリクエストに失敗しました。"),
        ),
      ).toBe(false);
    }

    expect(shouldReturnHomeAfterStageBError(new Error("通信エラー"))).toBe(
      false,
    );
  });

  test("Stage Bの対象外・判定困難は、画面側で固定の案内文を返す", async () => {
    const cases = [
      {
        status: "unsupported",
        unitStatus: "unsupported",
      },
      {
        status: "unit_undetermined",
        unitStatus: "undetermined",
      },
    ] as const;

    for (const testCase of cases) {
      fetchMock.mockResolvedValueOnce(
        Response.json({
          ...validStageBResponse,
          status: testCase.status,
          unit_status: testCase.unitStatus,
          unit: null,
          incorrect_question_numbers: null,
          analysis_result: null,
          comment_title: null,
          comment_body: null,
          message: "BEから返る案内文",
        }),
      );

      const result = await submitStageB("analysis-1", stageBRequest, {
        idempotencyKey: "stage-b-key-3",
      });

      expect(result.status).toBe(testCase.status);
      expect(result.unit_status).toBe(testCase.unitStatus);
      expect(result.unit).toBeNull();
      expect(result.analysis_result).toBeNull();
    }
  });

  test("Stage Bレスポンス形式が不正な場合はエラーにする", async () => {
    fetchMock.mockResolvedValue(
      Response.json({ ...validStageBResponse, comment_body: null }),
    );

    const error = await getRejectedError(
      submitStageB("analysis-1", stageBRequest, {
        idempotencyKey: "stage-b-key-4",
      }),
    );

    expect(error).toBeInstanceOf(StageBRequestError);
    expect((error as StageBRequestError).code).toBe("AI_RESPONSE_INVALID");
  });

  test("Stage Bの対象外レスポンスで必要な項目が欠けている場合はエラーにする", async () => {
    fetchMock.mockResolvedValue(
      Response.json({
        analysis_request_id: "analysis-1",
        status: "unsupported",
        unit_status: "unsupported",
      }),
    );

    const error = await getRejectedError(
      submitStageB("analysis-1", stageBRequest, {
        idempotencyKey: "stage-b-key-5",
      }),
    );

    expect(error).toBeInstanceOf(StageBRequestError);
    expect((error as StageBRequestError).code).toBe("AI_RESPONSE_INVALID");
    expect(shouldReturnHomeAfterStageBError(error)).toBe(false);
  });
});
