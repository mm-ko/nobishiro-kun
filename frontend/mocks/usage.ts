// ⑥ 利用状況（UI-002 ホーム）
// ホームは blocked_reason で、分析ボタン・有料案内ボタン・月の上限のお知らせを切り替える。
// デモでは「分析できる」を使う。ほかの表示を確かめるときだけ差し替える（README参照）。
import type { UsageResponse } from "@/types/api";

/** 分析できる（無料枠が残っている、または有料会員） */
export const mockUsageAvailable: UsageResponse = {
  can_analyze: true,
  used_count: 1,
  free_limit: 2,
  blocked_reason: null,
};

/** 分析できない（無料枠を使い切り、有料会員でもない） */
export const mockUsagePlanRequired: UsageResponse = {
  can_analyze: false,
  used_count: 2,
  free_limit: 2,
  blocked_reason: "plan_required",
};

/** 分析できない（今月の上限の10回に達した。契約の有無は問わない） */
export const mockUsageMonthlyLimitReached: UsageResponse = {
  can_analyze: false,
  used_count: 10,
  free_limit: 2,
  blocked_reason: "monthly_limit_reached",
};
