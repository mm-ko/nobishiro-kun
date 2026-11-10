import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, test, vi } from "vitest";

import { UnitRanking } from "./UnitRanking";

const getUnitRankingsMock = vi.hoisted(() => vi.fn());

vi.mock("@/lib/api/records", () => ({
  getUnitRankings: getUnitRankingsMock,
}));

describe("UnitRanking", () => {
  beforeEach(() => {
    getUnitRankingsMock.mockReset();
  });

  test("APIが返した同順位を計算し直さずに表示する", async () => {
    getUnitRankingsMock.mockResolvedValue({
      items: [
        {
          rank: 1,
          unit: { code: "division", name: "わり算" },
          average_score_rate: 52.5,
          record_count: 2,
        },
        {
          rank: 1,
          unit: { code: "multiplication", name: "かけ算" },
          average_score_rate: 52.5,
          record_count: 2,
        },
        {
          rank: 3,
          unit: { code: "addition", name: "たし算" },
          average_score_rate: 75,
          record_count: 1,
        },
      ],
    });

    render(<UnitRanking />);
    const items = await screen.findAllByRole("listitem");

    expect(items.map((item) => item.textContent)).toEqual([
      "1わり算52.5%",
      "1かけ算52.5%",
      "3たし算75.0%",
    ]);
  });
});
