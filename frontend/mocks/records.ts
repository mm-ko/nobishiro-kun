// ⑤ 履歴・ランキング（UI-002 ホーム）
// 形は API設計書 3.6・3.7 に合わせている。並び順は recorded_at の新しい順。
// 「分析前」と「分析後」の2通りを用意し、ホーム → 分析 → ホームの流れで履歴が増えて見えるようにする。
import type {
  AnalysisRecordsResponse,
  UnitRankingsResponse,
} from "@/types/api";

const DIVISION = { code: "division", name: "わり算" };
const ADD_SUB = {
  code: "addition_subtraction_written",
  name: "たし算とひき算の筆算",
};

/** 分析前の履歴（3件） */
export const mockRecordsBefore: AnalysisRecordsResponse = {
  items: [
    {
      id: "10",
      recorded_at: "2026-09-26T03:20:00Z",
      unit: DIVISION,
      score: 80,
      max_score: 100,
    },
    {
      id: "9",
      recorded_at: "2026-09-20T05:00:00Z",
      unit: ADD_SUB,
      score: 85,
      max_score: 100,
    },
    {
      id: "8",
      recorded_at: "2026-09-12T04:30:00Z",
      unit: DIVISION,
      score: 60,
      max_score: 100,
    },
  ],
  limit: 20,
  offset: 0,
  has_more: false,
};

/** 分析後の履歴（今回の分析が先頭に追加される） */
export const mockRecordsAfter: AnalysisRecordsResponse = {
  ...mockRecordsBefore,
  items: [
    {
      id: "11",
      recorded_at: "2026-10-05T01:30:00Z",
      unit: DIVISION,
      score: 80,
      max_score: 100,
    },
    ...mockRecordsBefore.items,
  ],
};

/** 分析前のランキング（得点率の平均が低い単元が上位） */
export const mockRankingsBefore: UnitRankingsResponse = {
  items: [
    { rank: 1, unit: DIVISION, average_score_rate: 70.0, record_count: 2 },
    { rank: 2, unit: ADD_SUB, average_score_rate: 85.0, record_count: 1 },
  ],
};

/** 分析後のランキング（わり算：(60+80+80)÷3 ≒ 73.3、3件） */
export const mockRankingsAfter: UnitRankingsResponse = {
  items: [
    { rank: 1, unit: DIVISION, average_score_rate: 73.3, record_count: 3 },
    { rank: 2, unit: ADD_SUB, average_score_rate: 85.0, record_count: 1 },
  ],
};

/**
 * 開発中の確認用：記録が1件もないときのサンプル（デモでは使わない）。
 * 使い方は mocks/README.md の「記録が0件のサンプルに差し替える」を参照。
 */
export const mockRecordsEmpty: AnalysisRecordsResponse = {
  items: [],
  limit: 20,
  offset: 0,
  has_more: false,
};

/** 開発中の確認用：ランキングの対象が1件もないときのサンプル（デモでは使わない） */
export const mockRankingsEmpty: UnitRankingsResponse = {
  items: [],
};
