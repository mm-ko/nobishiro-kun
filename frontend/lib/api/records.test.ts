import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import type {
  AnalysisRecordsResponse,
  UnitRankingsResponse,
} from "@/types/api";

import {
  getAnalysisRecords,
  getUnitRankings,
  RecordsRequestError,
} from "./records";

const firebaseAuthMocks = vi.hoisted(() => ({
  getCurrentFirebaseUser: vi.fn(),
  getIdToken: vi.fn(),
  logoutFromFirebase: vi.fn(),
}));

vi.mock("@/lib/firebase/auth", () => ({
  getCurrentFirebaseUser: firebaseAuthMocks.getCurrentFirebaseUser,
  logoutFromFirebase: firebaseAuthMocks.logoutFromFirebase,
}));

const fetchMock = vi.fn<typeof fetch>();

const validRecordsResponse = {
  items: [
    {
      id: "2",
      recorded_at: "2026-10-01T03:20:00Z",
      unit: { code: "division", name: "わり算" },
      score: 40,
      max_score: 50,
    },
  ],
  limit: 20,
  offset: 0,
  has_more: false,
} satisfies AnalysisRecordsResponse;

const validRankingsResponse = {
  items: [
    {
      rank: 1,
      unit: { code: "division", name: "わり算" },
      average_score_rate: 70,
      record_count: 2,
    },
    {
      rank: 1,
      unit: { code: "multiplication", name: "かけ算" },
      average_score_rate: 70,
      record_count: 1,
    },
  ],
} satisfies UnitRankingsResponse;

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

describe("records API", () => {
  beforeEach(() => {
    fetchMock.mockReset();
    firebaseAuthMocks.getCurrentFirebaseUser.mockReset();
    firebaseAuthMocks.getCurrentFirebaseUser.mockReturnValue({
      getIdToken: firebaseAuthMocks.getIdToken,
    });
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

  test("学習履歴APIから新しい順の20件を取得する", async () => {
    fetchMock.mockResolvedValue(Response.json(validRecordsResponse));

    const response = await getAnalysisRecords();
    const [requestUrl, requestOptions] = getLastRequest();
    const headers = new Headers(requestOptions?.headers);

    expect(response).toEqual(validRecordsResponse);
    // ユーザーはBEが認証から決めるため、user_id は送らない
    expect(requestUrl).toBe(
      "http://localhost:8000/v1/analysis-records?limit=20",
    );
    expect(requestOptions?.method).toBe("GET");
    expect(headers.get("Authorization")).toBe("Bearer firebase-id-token");
  });

  test("記録がないときは空の一覧を返す", async () => {
    const emptyResponse = { ...validRecordsResponse, items: [] };
    fetchMock.mockResolvedValue(Response.json(emptyResponse));

    await expect(getAnalysisRecords()).resolves.toEqual(emptyResponse);
  });

  test("APIエラーのときはエラーコードを持ったエラーにする", async () => {
    fetchMock.mockResolvedValue(
      Response.json({ error: { code: "UNAUTHENTICATED" } }, { status: 401 }),
    );

    const error = await getRejectedError(getAnalysisRecords());

    expect(error).toBeInstanceOf(RecordsRequestError);
    expect((error as RecordsRequestError).code).toBe("UNAUTHENTICATED");
  });

  test("レスポンス形式が不正な場合はエラーにする", async () => {
    fetchMock.mockResolvedValue(
      Response.json({
        ...validRecordsResponse,
        items: [{ ...validRecordsResponse.items[0], unit: null }],
      }),
    );

    const error = await getRejectedError(getAnalysisRecords());

    expect(error).toBeInstanceOf(RecordsRequestError);
    expect((error as RecordsRequestError).code).toBe("INTERNAL_ERROR");
  });

  test("APIの接続先が設定されていない場合は送信しない", async () => {
    vi.stubEnv("NEXT_PUBLIC_API_BASE_URL", "");

    const error = await getRejectedError(getAnalysisRecords());

    expect(error).toBeInstanceOf(RecordsRequestError);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  test("Firebaseユーザーがいない場合は学習履歴APIを呼ばない", async () => {
    firebaseAuthMocks.getCurrentFirebaseUser.mockReturnValue(null);

    const error = await getRejectedError(getAnalysisRecords());

    expect(error).toBeInstanceOf(RecordsRequestError);
    expect((error as RecordsRequestError).code).toBe("UNAUTHENTICATED");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  test("ランキングAPIから取得し、順位を計算し直さずに返す", async () => {
    fetchMock.mockResolvedValue(Response.json(validRankingsResponse));

    const response = await getUnitRankings();
    const [requestUrl, requestOptions] = getLastRequest();
    const headers = new Headers(requestOptions?.headers);

    expect(response).toEqual(validRankingsResponse);
    // ユーザーはBEが認証から決めるため、user_id は送らない
    expect(requestUrl).toBe("http://localhost:8000/v1/rankings/units");
    expect(requestOptions?.method).toBe("GET");
    expect(headers.get("Authorization")).toBe("Bearer firebase-id-token");
  });

  test("ランキングの対象がないときは空の一覧を返す", async () => {
    fetchMock.mockResolvedValue(Response.json({ items: [] }));

    await expect(getUnitRankings()).resolves.toEqual({ items: [] });
  });

  test("ランキングのAPIエラーのときはエラーコードを持ったエラーにする", async () => {
    fetchMock.mockResolvedValue(
      Response.json({ error: { code: "UNAUTHENTICATED" } }, { status: 401 }),
    );

    const error = await getRejectedError(getUnitRankings());

    expect(error).toBeInstanceOf(RecordsRequestError);
    expect((error as RecordsRequestError).code).toBe("UNAUTHENTICATED");
  });

  test("ランキングのレスポンス形式が不正な場合はエラーにする", async () => {
    fetchMock.mockResolvedValue(
      Response.json({
        items: [
          { ...validRankingsResponse.items[0], average_score_rate: "70" },
        ],
      }),
    );

    const error = await getRejectedError(getUnitRankings());

    expect(error).toBeInstanceOf(RecordsRequestError);
    expect((error as RecordsRequestError).code).toBe("INTERNAL_ERROR");
  });

  test("ランキングでもAPIの接続先が設定されていない場合は送信しない", async () => {
    vi.stubEnv("NEXT_PUBLIC_API_BASE_URL", "");

    const error = await getRejectedError(getUnitRankings());

    expect(error).toBeInstanceOf(RecordsRequestError);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  test("Firebaseユーザーがいない場合はランキングAPIを呼ばない", async () => {
    firebaseAuthMocks.getCurrentFirebaseUser.mockReturnValue(null);

    const error = await getRejectedError(getUnitRankings());

    expect(error).toBeInstanceOf(RecordsRequestError);
    expect((error as RecordsRequestError).code).toBe("UNAUTHENTICATED");
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
