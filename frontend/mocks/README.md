# mocks/（デモ用のサンプルデータ）

画面の開発・確認に使うサンプルデータです。

Stage Aは通常、本物のAPIを呼びます。BEを起動せずにUI-006を確認するときだけ、後述の手順でStage Aのサンプルへ一時的に差し替えます。

- 形はAPI設計書（#8）のレスポンスと同じです。型は `types/api.ts` にあります。
- 画面は `mocks/` を直接読まず、`lib/api/` の関数を通して使います。本物のAPIにつなぐときは、`lib/api/` の関数の中身だけを変えます（#41）。
- 画面で型を使うときは、`@/types/api` から読み込みます（`mocks/` からは読み込みません）。
- すべてダミーです。実在の人物・本物のFirebaseの値・市販のテストは使いません。

## ファイル

| ファイル           | 内容                                                                                       | 使う画面               |
| ------------------ | ------------------------------------------------------------------------------------------ | ---------------------- |
| `mocks/user.ts`    | ログイン中ユーザー                                                                         | UI-001・UI-002         |
| `mocks/stageA.ts`  | 1回目のAI結果（5問・80点）とダミー画像の場所。開発中の確認用に「不明」を含むサンプルもある | UI-003・UI-005・UI-006 |
| `mocks/stageB.ts`  | 2回目のAI分析結果（分析完了時のサンプル）                                                  | UI-007                 |
| `mocks/records.ts` | 履歴・ランキングのサンプル。いまは使っていない（残す・消すはチームで決める。#41）          | なし                   |
| `mocks/usage.ts`   | 利用状況（分析できる／できない）。デモは「分析できる」                                     | UI-002                 |
| `types/api.ts`     | APIのリクエスト・レスポンスの型（モックをやめたあとも使う）                                | 全画面                 |
| `lib/api/*.ts`     | 画面から呼ぶ「取り出す関数」                                                               | 全画面                 |

ダミー画像：`public/mocks/sample-test.png`（アップロード画面で選ぶ用）

## デモの流れ

ログイン → ホーム → アップロード → 分析中 → 確認・修正 → 分析結果 → ホーム（履歴が1件増え、ランキングにも反映される）

履歴・ランキングとも、BEに保存された本物の記録から表示します（`mocks/records.ts` は使っていません）。記録がないときの表示は、記録がまだないユーザーでログインすると確かめられます。

## 不明を含むサンプルに差し替える（開発中の確認用）

デモ用のデータは、5問とも解答・正誤・得点が読み取れています。UI-006で「読み取れなかった」ときの表示や入力チェックを確かめたいときは、`mocks/stageA.ts` の `mockStageAResponseWithUnknown` に差し替えます。

| 変えているところ             | 値          | 画面で確かめること                         |
| ---------------------------- | ----------- | ------------------------------------------ |
| 得点（`read_score`）         | `null`      | 得点欄が空で表示され、入力しないと進めない |
| q2の正誤（`grading`）        | `"unknown"` | 正解／不正解を選ぶまで進めない             |
| q4の解答（`student_answer`） | `null`      | 実際の解答を入力するまで進めない           |

差し替え方：`lib/api/analysis.ts` でサンプルを読み込み、`startStageA` の先頭から一時的に返します。

```ts
import { mockStageAResponseWithUnknown } from "@/mocks/stageA";

const USE_STAGE_A_DEVELOPMENT_SAMPLE = true;

export async function startStageA(
  images: File[],
  options: StartStageAOptions,
): Promise<StageAResponse> {
  // UI-006の確認中だけ追加する
  if (USE_STAGE_A_DEVELOPMENT_SAMPLE) {
    return mockStageAResponseWithUnknown;
  }

  // ここから下の既存のAPI処理は変更しない
}
```

確かめ終わったら、追加したimport・定数・if文を必ず元に戻します。

**差し替えたままコミットしないでください。** Stage Aの本物のAPIを呼ばなくなります。

## 利用状況の表示を確認する

実際の画面では、`lib/api/usage.ts` が `GET /v1/usage` を呼び出し、Backendから返された `blocked_reason` によってホームの表示を切り替えます。

`mocks/usage.ts` の次のモックは、`features/home/components/AnalyzeButton.test.tsx` で表示を確認するために使用します。

| モック                         | `blocked_reason`        | ホームの表示                                                                          |
| ------------------------------ | ----------------------- | ------------------------------------------------------------------------------------- |
| `mockUsageAvailable`（デモ用） | `null`                  | ［テストを分析する］                                                                  |
| `mockUsagePlanRequired`        | `plan_required`         | ［3回目以降は有料です］                                                               |
| `mockUsageMonthlyLimitReached` | `monthly_limit_reached` | 押せないお知らせ「今月の分析回数の上限に達しました。来月1日から、また分析できます。」 |

次のコマンドで、3種類の表示と利用状況を取得できない場合の表示を確認できます。

```powershell
npx vitest run features/home/components/AnalyzeButton.test.tsx
```

実際の画面で表示を確認するときは、`lib/api/usage.ts` をモックへ差し替えず、Backendの利用状況を使用します。

## UI-007の分析結果を確認する

UI-007（分析結果画面）では、分析完了・分析対象外・単元を特定できない場合の表示を確認できます。

現在の `lib/api/analysis.ts` では、`NEXT_PUBLIC_MOCK_RESULT` による分析結果の切り替えには対応していません。

### APIレスポンス処理のテスト

分析対象外・単元を特定できない場合のレスポンス処理は、次のコマンドで確認できます。

```powershell
npx vitest run lib/api/analysis.test.ts
```

### 分析結果画面のテスト

画面の表示テストは、次のコマンドで実行できます。

```powershell
npx vitest run features/test-analysis/components/AnalysisResult.test.tsx
```
