// 分析中の待ち表示（UI-005・UI-006B）の秒数。
// 上限は、本物の読み取りの実測（画像1枚で約40〜60秒）と、Backendの上限（120秒）に合わせた。
// 切り替えの秒数は、処理が長引いたら3つ目を「進行中」のまま待つ仕様のため、3秒・6秒で確定した（#88）。

/** 2つ目・3つ目の文言へ切り替えるまでの時間（待ち表示を出してからのミリ秒） */
export const ANALYSIS_WAITING_STEP_DELAYS_MS = [3000, 6000] as const;

/** 待ち時間の上限（ミリ秒）。超えたら失敗として扱い、エラー表示へ進む */
export const ANALYSIS_TIMEOUT_MS = 120_000;

type AnalysisTimeoutOptions = {
  onTimeout?: () => void;
};

/** 分析の呼び出しに上限をかける。上限までに結果が返らなければ失敗にする */
export function withAnalysisTimeout<T>(
  request: Promise<T>,
  options: AnalysisTimeoutOptions = {},
): Promise<T> {
  return new Promise((resolve, reject) => {
    const timeoutId = setTimeout(() => {
      options.onTimeout?.();
      reject(new Error("分析の待ち時間が上限を超えました。"));
    }, ANALYSIS_TIMEOUT_MS);

    request.then(resolve, reject).finally(() => clearTimeout(timeoutId));
  });
}
