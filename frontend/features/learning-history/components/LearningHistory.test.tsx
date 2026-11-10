import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, test, vi } from "vitest";

import { LearningHistory } from "./LearningHistory";

const getAnalysisRecordsMock = vi.hoisted(() => vi.fn());

vi.mock("@/lib/api/records", () => ({
  getAnalysisRecords: getAnalysisRecordsMock,
}));

describe("LearningHistory", () => {
  beforeEach(() => {
    getAnalysisRecordsMock.mockReset();
  });

  test("APIが返した順に、日本時間の日付・単元・点数を表示する", async () => {
    getAnalysisRecordsMock.mockResolvedValue({
      items: [
        {
          id: "2",
          // 日本時間では 10/1 の朝
          recorded_at: "2026-09-30T23:30:00Z",
          unit: { code: "division", name: "わり算" },
          score: 40,
          max_score: 50,
        },
        {
          id: "1",
          recorded_at: "2026-09-20T05:00:00Z",
          unit: {
            code: "addition_subtraction_written",
            name: "たし算とひき算の筆算",
          },
          score: 120,
          max_score: 150,
        },
      ],
      limit: 20,
      offset: 0,
      has_more: false,
    });

    render(<LearningHistory />);
    const items = await screen.findAllByRole("listitem");

    expect(items.map((item) => item.textContent)).toEqual([
      "10/1わり算40/50",
      "9/20たし算とひき算の筆算120/150",
    ]);
  });

  test("記録がないときは案内を表示する", async () => {
    getAnalysisRecordsMock.mockResolvedValue({
      items: [],
      limit: 20,
      offset: 0,
      has_more: false,
    });

    render(<LearningHistory />);

    expect(
      await screen.findByText(
        "まだ記録がありません。テストを分析すると、ここに表示されます。",
      ),
    ).toBeTruthy();
  });

  test("取得に失敗したときはエラーを表示する", async () => {
    getAnalysisRecordsMock.mockRejectedValue(new Error("network"));

    render(<LearningHistory />);

    const alert = await screen.findByRole("alert");

    expect(alert.textContent).toBe(
      "学習履歴を読み込めませんでした。時間をおいてもう一度お試しください。",
    );
  });
});
