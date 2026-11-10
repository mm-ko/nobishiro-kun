import { afterEach, describe, expect, test, vi } from "vitest";

import { ANALYSIS_TIMEOUT_MS, withAnalysisTimeout } from "./analysisWaiting";

describe("withAnalysisTimeout", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  test("待ち時間の上限を超えたら通信の中断処理を呼ぶ", async () => {
    vi.useFakeTimers();
    const onTimeout = vi.fn();
    const result = withAnalysisTimeout(new Promise(() => undefined), {
      onTimeout,
    });
    const rejection =
      expect(result).rejects.toThrow("分析の待ち時間が上限を超えました。");

    await vi.advanceTimersByTimeAsync(ANALYSIS_TIMEOUT_MS);

    await rejection;
    expect(onTimeout).toHaveBeenCalledOnce();
  });
});
