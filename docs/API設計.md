# API 設計

本書は、PRD Ver.1.37、DB設計書、および機能要件をもとにしたMVP向けのAPI設計案とする。

Stage A・Stage BのJSON形式、エンドポイント名、ページング方式は本書での提案とし、FE・BE担当のレビュー後に確定する。利用制限・決済関連はIssue #10の決定内容を反映する。

> APIの詳細はOpenAPI形式で定義し、`backend/openapi.yaml`で管理する。
> 本ドキュメントは概要・代表例・運用ルールを示す。
> 本書の作成だけでは、OpenAPIスキーマファイルの作成完了とはしない。

(2026/10/04更新：Issue #10の決定事項を反映)
共通・分析・履歴APIのOpenAPIスキーマは、Issue #8で合意した範囲から順次作成する。
利用制限・決済関連のOpenAPIスキーマには、本書に反映したIssue #10の決定内容を反映する。

（2026/10/25更新：Issue #23・#25・#37・#38の合意と、マージ済み[PR #145](https://github.com/ms-engineer-bc26-05/Section9_team-a/pull/145)のWebhook仕様を反映）
（2026/10/28更新：マージ済みPR #147・#150・#153の確定実装を照合）
Webhookの基本処理はPR #145、決済API・二重契約対策は[PR #147](https://github.com/ms-engineer-bc26-05/Section9_team-a/pull/147)、レート制限は[PR #150](https://github.com/ms-engineer-bc26-05/Section9_team-a/pull/150)で実装済み。利用状況API・無料枠・月間上限は[PR #153](https://github.com/ms-engineer-bc26-05/Section9_team-a/pull/153)と照合済み。決済画面との連携・Webhook反映待ちの再取得はIssue #38の実装仕様を反映する。

分析結果の保存・利用回数の加算は、Stage Bが正常に返ったサーバー側の時点でBEが確定する。FEの表示完了通知APIは設けない。
保存・加算済みの結果が画面へ届かなかった場合は、同じ分析処理IDで結果を再取得できるようにする。

## 1. 設計方針

### 基本方針

| 項目               | 方針                                                                         |
| ------------------ | ---------------------------------------------------------------------------- |
| スタイル           | RESTを基本とするHTTP API                                                     |
| バージョニング     | `/v1`をURLの先頭に付与する                                                   |
| データ形式         | 原則としてJSON。画像アップロードは`multipart/form-data`                      |
| JSONの命名         | `snake_case`                                                                 |
| 認証               | Firebase IDトークンをBearerトークンとして送信する                            |
| 日時               | UTCのISO 8601形式で返す。画面では日本時間に変換する                          |
| 月間利用回数の集計 | 日本時間（Asia/Tokyo）の暦月を基準とする。日時の保存・API表現はUTCを維持する |
| DBのbigint ID      | JavaScriptでの精度問題を避けるため、JSONでは文字列として扱う                 |
| 分析処理ID         | BEがUUIDとして発行する                                                       |
| 得点・満点         | 必須・整数。満点は0より大きく、得点は0以上かつ満点以下                       |
| 得点率             | BEで算出し、小数第2位まで保存する                                            |
| 履歴詳細           | 過去の履歴詳細表示はPhase2。通信失敗時の同じ分析処理IDによる結果再取得はMVPで対応する |
| 編集・削除         | 履歴編集・削除、アカウント削除APIはMVP対象外                                 |

### 認証・ユーザー識別

- 新規登録・ログイン・ログアウトは、FEからFirebase Authenticationを利用する。
- BE独自のメールアドレス・パスワード認証APIは設けない。
- 認証が必要なAPIには、以下のヘッダーを付ける。

```http
Authorization: Bearer <Firebase ID token>
```

- BEでトークンを検証し、Firebase UIDからアプリ内ユーザーを特定する。
- リクエスト本文の`user_id`によって操作対象のユーザーを指定させない。
- 分析処理IDの所有者は、BEで認証済みユーザーと照合する。
- 初回ログイン後、FEはユーザー初期化APIを呼び出す。

### 分析フロー

1. FEで画像を選択し、必要に応じてトリミングする。
2. FEがStage A APIへ画像を送信する。
3. BEがStage A実行前に残り回数・契約状態を確認する。無料枠（月2回）を使い切り、有効な月額プランがない場合は`403 PLAN_REQUIRED`を返す。分析を開始できる場合は、Memcachedのレート制限を適用し、分析処理IDを発行して画像から事実データを抽出する。
4. FEで保護者が解答内容・正誤を確認・修正する。得点は読み取り値を初期表示して確認・修正し、読み取れなければ入力する。満点は保護者が入力する。
5. FEがStage B APIへ確認済みデータ・得点・満点を送信する。
6. BEが単元を判定する。
   - 対象外・判定困難の場合は、判定結果を返して終了する。FEはその旨を表示した後、ホームへ戻す。利用回数は加算せず、分析記録も保存しない。
   - 対象単元の場合は、パターン分析・コメント生成を行う。
7. Stage Bが正常に返ったサーバー側の時点で、BEが所有者・分析成功・未カウントであることを確認し、利用実績と分析記録を同一トランザクションで確定してから結果を返す。
8. FEは結果を表示し、履歴・ランキング・利用回数を再取得する。保存・加算済みの結果が画面へ届かなかった場合は、同じ分析処理IDで結果を再取得する。

利用回数は分析結果が得られた場合に1回とする。
HTTP 200であっても、対象外・判定困難の場合は加算対象としない。

FEからの通知がなくてもBEで保存・加算を確定する。画面への結果到達・表示完了は加算条件にしない。
Stage Aだけを繰り返す利用は、正式な利用回数への加算ではなくMemcachedのレート制限で抑える。

### APIの応答方式

MVPでは、Stage A・Stage Bともに、処理結果を同じHTTPリクエストへの応答として返す同期方式を初期案とする。

実測時間がインフラのタイムアウトに収まらない場合は、非同期方式へ変更し、状態取得API等を追加する。タイムアウト値は検証後に確定する。

### 分析中データの保持方針

Stage Aの抽出結果は、FEが確認画面での表示・修正用に保持する。
Stage Bでは、FEが分析に必要な問題文・計算過程等と、保護者による確認済みの解答・正誤を送信する。
BEは、Stage Bの入力を構成するためにStage Aの抽出結果を参照する方式にはしない。

FEの未保存の途中データの保持先はアプリ内のメモリとする案とし、ページ再読み込み・画面離脱後の途中データ復元はMVP対象外とする。
未保存の途中データを失った場合は再アップロードを案内する。保存済み結果の再取得とは区別し、保存・加算済みの場合は同じ分析処理IDで結果を再取得する。

| 対象データ                             | 保持・管理する側                                                                                               | 方針                                              |
| -------------------------------------- | -------------------------------------------------------------------------------------------------------------- | ------------------------------------------------- |
| Stage Aの抽出結果・確認中の入力        | FE                                                                                                             | 確認画面で保持し、Stage Bへ必要なデータを送信する |
| 分析処理ID・所有者・処理状態・有効期限 | BE側の管理領域                                                                                                 | 所有者確認、状態遷移、期限管理に使用する          |
| 冪等キー・入力照合情報・再送用の応答   | BE側の管理領域                                                                                                 | 重複実行の防止と、通信失敗時の再送に使用する      |
| Stage Bの生成結果                      | BE（正常完了時にPostgreSQLへ保存） | 未保存の途中データと保存済み結果を区別し、画面に届かなかった保存済み結果は同じ分析処理IDで再取得する |

BEサーバーのプロセスメモリだけに依存する保持方式は採用しない。
BE側の管理領域の保存先・保持期限・削除方法・障害時の扱いは、
Issue #27で#28の処理を見据えて確定する。

Stage Aの応答を冪等性のためにBE側で一時保持する場合、
その目的は再送への応答であり、Stage Bへのデータ引き継ぎとは区別する。
この保持範囲は#5・規約と整合させる。

画像・抽出データは必要な期間のみ保持し、不要になった時点で削除する。

## 2. エンドポイント一覧

### 共通・分析・履歴

| メソッド | パス                                        | 概要                                                                                                                                                                    | 認証 |
| -------- | ------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---- |
| GET | `/v1/health` | PostgreSQLで`SELECT 1`を実行し、BackendからのDB接続を確認する | 不要 |
| PUT      | `/v1/users/me`                              | 認証済みユーザーの初期登録。登録済みなら既存情報を返す                                                                                                                  | 必要 |
| GET      | `/v1/users/me`                              | 自分のアプリ内ユーザー情報を取得する                                                                                                                                    | 必要 |
| GET      | `/v1/units`                                 | 対応単元の一覧を取得する                                                                                                                                                | 必要 |
| POST | `/v1/analyses` | Stage A実行前に残り回数・契約状態をチェックし、レート制限を適用して事実抽出を実行する | 必要 |
| POST | `/v1/analyses/{analysis_request_id}/result` | Stage Bを実行し、正常完了時に同一トランザクションで保存・加算して結果を返す | 必要 |
| 未確定 | 未確定（同じ`analysis_request_id`を指定） | 保存・加算済みの分析結果を再取得する。メソッド・パスはFE・BEレビューで確定する | 必要 |
| GET      | `/v1/analysis-records`                      | 自分の学習履歴一覧を取得する                                                                                                                                            | 必要 |
| GET      | `/v1/rankings/units`                        | 自分の苦手単元ランキングを取得する                                                                                                                                      | 必要 |

#### DB接続確認API

`GET /v1/health`はDB接続のみを確認し、テーブル・初期データの存在確認は行わない。

| 結果 | HTTPステータス | レスポンス |
| --- | --- | --- |
| 接続成功 | 200 | `{"status":"ok","database":"ok"}` |
| 接続不可・設定未指定・URL形式不正 | 503 | `{"status":"error","database":"unavailable"}` |

接続先や例外の詳細はレスポンスに含めない。

### 利用制限・決済

処理方針はIssue #10および#23・#25・#37・#38の合意に従う。Webhookの基本処理と二重契約対策は第3.10節、利用状況・契約状態APIは第3.8・3.9節、Checkout作成APIは第3.11節に記載する。

| メソッド | パス                            | 概要                                           | 認証                                 |
| -------- | ------------------------------- | ---------------------------------------------- | ------------------------------------ |
| GET      | `/v1/usage`                     | 現在の利用回数・分析可能かどうかを取得する     | 必要                                 |
| GET      | `/v1/subscriptions/current`     | 現在の契約・利用権の状態を取得する             | 必要                                 |
| POST     | `/v1/billing/checkout-sessions` | Stripe Checkoutを新しいタブで開くための情報を作成する             | 必要                                 |
| POST     | `/v1/webhooks/stripe`           | Stripeからの通知を受け取り、契約情報を反映する | Firebase認証不要・Stripe署名検証必須 |

月額プランは月額300円の1種類のみとし、プラン選択は行わない。Checkoutの対象プラン・金額はBEで固定し、FEからプラン選択情報を受け取らない。
月額プランは、Stripeのサブスクリプションのイベントで有効なサブスクリプションを追跡し、ステータスが`active`であることをBEが確認して判定する。
有料プランは月10回まで（無料の2回を含む）とする。日本時間の暦月で集計し、上限に達した場合は契約の有無にかかわらず分析できない。解約関連APIの有無・操作の詳細は別途確定する。

| 項目 | 方針 |
| --- | --- |
| 決済方式 | Stripe Checkoutを新しいタブで開く |
| 成功 | `invoice.updated`で`paid`が`true`、`status`が`paid`になる |
| 失敗 | `invoice.updated`で`paid`が`false`、`status`が`open`のまま。あわせて`invoice.payment_failed`が送られる |
| キャンセル | UI-008（有料案内）の［今回はやめる］でUI-002（ホーム）へ戻る |

請求書の支払状態とサブスクリプションの契約状態は区別する。月額プラン判定はサブスクリプションの`active`を確認する。
UI-008の［今回はやめる］はホームへ直接戻る。［決済へ進む］では、ポップアップブロックを避けるため空の新規タブを先に開いてから、認証付きで`POST /v1/billing/checkout-sessions`を呼ぶ。応答の`checkout_url`が`https`かつホスト名が`checkout.stripe.com`の場合だけ、その新規タブを移動させる。APIエラー・不正なURL・新規タブを開けない場合はUI-008に留まり、再試行できる日本語の案内を表示する。`409 ALREADY_SUBSCRIBED`の場合は新しいCheckoutを開かず、UI-009の成功確認状態へ進む。

Stripeの成功時URLは`/plan/result?status=success`、キャンセル時URLは`/plan/result?status=cancel`とする。UI-009は1画面とし、成功・失敗・キャンセルを同じ画面内の表示状態として扱う。ただし、戻り先URLやタブの状態だけで決済結果を確定しない。`status=success`では`GET /v1/subscriptions/current`を直ちに実行し、`is_subscribed: true`となるまで1秒間隔・最大10回取得する。確認できた場合だけ成功を表示し、確認できないまま上限に達した場合は失敗と断定せず「決済状況を確認できませんでした」と再試行ボタンを表示する。ホームへ戻るとUI-002が`GET /v1/usage`を取得し、利用可否を更新する。`status=cancel`はキャンセル表示、`status=failure`は失敗表示に使用し、不正な`status`はUI-008へ戻す。Stripe上のカード拒否は通常Checkout内に留まるため、`failure`は画面状態の確認と将来の失敗URL連携に備えて保持する。

## 3. リクエスト / レスポンス例

### 3.1 ユーザー初期登録

```http
PUT /v1/users/me
Authorization: Bearer <Firebase ID token>
```

リクエスト本文は不要とする。Firebase UIDは検証済みトークンから取得する。

初回登録時は`201 Created`、登録済みの場合は`200 OK`を返す。

```json
{
  "id": "1",
  "created_at": "2026-09-26T03:00:00Z"
}
```

`GET /v1/users/me`も同じ形式を返す。

### 3.2 対応単元一覧

```http
GET /v1/units
Authorization: Bearer <Firebase ID token>
```

```json
{
  "items": [
    {
      "id": "1",
      "code": "division",
      "name": "わり算"
    },
    {
      "id": "2",
      "code": "addition_subtraction_written",
      "name": "たし算とひき算の筆算"
    }
  ]
}
```

### 3.3 Stage A：画像からの事実抽出

```http
POST /v1/analyses
Authorization: Bearer <Firebase ID token>
Idempotency-Key: <同じ操作の再試行では同じUUID>
Content-Type: multipart/form-data; boundary=...
```

| フィールド | 型           | 必須 | 内容                 |
| ---------- | ------------ | ---- | -------------------- |
| images     | ファイル配列 | 必須 | 1〜2枚。JPEG/JPG/PNG |

- 1回のリクエストは1つの単元テストを表す。
- トリミングはFEで行い、加工済み画像を送る。
- 拡張子だけでなく、画像の実データも検証する。
- 1枚あたり・合計の画像容量上限は、Issue #27で技術検証し、FE・BE双方の制限値として確定する。

成功レスポンス：`201 Created`

```json
{
  "analysis_request_id": "d85a0a9f-1234-4a56-8b90-123456789abc",
  "status": "awaiting_confirmation",
  "read_score": 80,
  "read_unit_name": "あまりのあるわり算",
  "questions": [
    {
      "question_id": "q1",
      "image_index": 1,
      "question_number": "1(1)",
      "problem_text": "17÷5",
      "student_answer": "3あまり3",
      "calculation_process": null,
      "grading": "incorrect"
    }
  ],
  "expires_at": "2026-09-26T04:00:00Z"
}
```

※ `expires_at`の時刻は例であり、保持時間を1時間と確定するものではない。

| 項目                | 内容                                                                                                   |
| ------------------- | ------------------------------------------------------------------------------------------------------ |
| status              | Stage A完了時は`awaiting_confirmation`                                                                 |
| read_score          | テスト全体の読み取った得点。キーは必須、読み取れない場合は`null`。非負の整数として確定できる場合に返す |
| question_id         | BEが割り当てる問題識別子。確認・修正時も維持する                                                       |
| image_index         | 送信した画像の順番。1または2                                                                           |
| question_number     | 用紙上の問題番号。読み取れない場合は`null`                                                             |
| problem_text        | 読み取った問題内容                                                                                     |
| student_answer      | 子どもの解答。空欄は空文字、読み取り不明は`null`                                                       |
| calculation_process | 計算過程。取得できなければ`null`                                                                       |
| grading             | `correct`／`incorrect`／`unknown`                                                                      |
| read_unit_name      | 読み取れた単元名。不明なら`null`                                                                       |
| expires_at          | 分析処理IDを使ってStage Bを開始できる期限。FEの保持データを自動削除する時刻ではない                    |

Stage Aでは事実抽出のみを行い、間違え方のパターン分析は行わない。
正誤は先生の採点情報を読み取り、AIによる独自の採点は行わない。
採点情報を判断できない場合は、`grading: unknown`を返す。

Stage Aではテスト全体の得点を読み取り、`read_score`として返す。
トリミング等で点数が写っていない場合や、得点を特定できない場合は、推測せず`null`を返す。
点数が読み取れないことだけを理由にStage Aをエラーにはしない。

FEは読み取った得点を得点欄に初期表示し、保護者が確認・修正する。
読み取れない場合は保護者が入力する。満点は保護者が入力する。

保存・得点率計算には、Stage Bで受け取った確認済みの得点・満点を使用する。
BEは入力値を検証して得点率を計算する。

### 3.4 Stage B：確認済みデータの分析

```http
POST /v1/analyses/d85a0a9f-1234-4a56-8b90-123456789abc/result
Authorization: Bearer <Firebase ID token>
Idempotency-Key: <同じ操作の再試行では同じUUID>
Content-Type: application/json

{
  "score": 80,
  "max_score": 100,
  "read_unit_name": "あまりのあるわり算",
  "confirmed_questions": [
    {
      "question_id": "q1",
      "image_index": 1,
      "question_number": "1(1)",
      "problem_text": "17÷5",
      "student_answer": "3あまり3",
      "calculation_process": null,
      "grading": "incorrect"
    }
  ]
}
```

| 項目                | 必須 | NULL | 内容                                       |
| ------------------- | ---- | ---- | ------------------------------------------ |
| read_unit_name      | 必須 | 可   | Stage Aで読み取った単元名                  |
| image_index         | 必須 | 不可 | 画像の順番。1または2                       |
| question_number     | 必須 | 可   | 用紙上の問題番号                           |
| problem_text        | 必須 | 不可 | 分析に必要な問題内容                       |
| calculation_process | 必須 | 可   | 読み取れた計算過程。取得できなければ`null` |

- 得点・満点は必須・整数とする。
- 問題ごとの任意メモは採用せず、Stage Bの入力項目に含めない。
- FEは、Stage Aで受け取った全問題について、分析に必要な情報と確認済み解答・正誤を送信する。
- 問題文・計算過程・画像番号・問題番号・読み取った単元名は、FEが保持するStage Aの値を送信する。
- BEは分析処理IDの所有者・有効期限・処理状態を確認する。
- BEは必須項目、型、値の範囲、問題IDの重複等を検証する。
- BEはStage Aの抽出結果との全項目照合は行わないため、元の抽出結果に対する問題の欠落や内容変更を完全には検出できない。
- FEから受け取ったデータも入力検証を行い、単元判定・分析・得点率計算はBE側で実行する。
- `grading`が`unknown`のままの場合はStage Bへ進めない案とする。
- 読み取り漏れや修正不能な問題の扱いは、確認画面の仕様と合わせて確定する。
- Stage Bは、分析処理IDごとに1つの確定結果を持つ。
- 同じ分析処理IDでStage Bが実行中の場合は、別の冪等キーでも重複実行せず、`409 ANALYSIS_IN_PROGRESS`を返す。
- Stage B完了後に新しいキーで再実行を要求された場合は、`409 ANALYSIS_STATE_CONFLICT`を返す。
- 元のキーによる再送は確定済みの結果を返し、再実行・再保存・再加算しない。保存済み結果は同じ分析処理IDで再取得できる。
- Stage B完了後の解答修正・再分析は、MVP対象外とする案とする。
- Stage Bが正常に返ったサーバー側の時点で、必要な分析結果・コメントを検証し、利用実績1件と分析記録1件を同一トランザクションで作成する。片方の保存に失敗した場合は両方をロールバックする。
- `analysis_usage_id`で両者を紐づけ、`incorrect_question_numbers`は確認済みの正誤からBEで確定する。
- DBへの保存・加算が確定した後に`completed`の成功レスポンスを返す。対象外・判定困難の場合はどちらも保存しない。

成功レスポンス：`200 OK`

```json
{
  "analysis_request_id": "d85a0a9f-1234-4a56-8b90-123456789abc",
  "status": "completed",
  "unit_status": "supported",
  "unit": {
    "id": "1",
    "code": "division",
    "name": "わり算"
  },
  "score": 80,
  "max_score": 100,
  "score_rate": 80.0,
  "incorrect_question_numbers": ["1:1(1)"],
  "analysis_result": {
    "patterns": [
      {
        "pattern": "あまりの計算ミス",
        "cause_type": "undetermined",
        "question_numbers": ["1:1(1)"],
        "explanation": "商は合っていますが、あまりの値に誤りが見られます。"
      }
    ]
  },
  "comment_title": "あまりを一緒に確認してみましょう",
  "comment_body": "テストの確認、お疲れさまです。今回は商を求めるところまでできています。割る数と商を掛け、元の数から引く手順を一緒に確かめてみましょう。",
  "message": null
}
```

- JSONの数値は末尾のゼロを保証しない。画面上の小数桁数は表示処理で整える。
- 保存用の問題番号は、BEで「画像番号:用紙上の問題番号」に整形する

#### パターン分析の形式案

- `patterns`は0件以上の配列とする。
- 全問正解の場合は`incorrect_question_numbers`と`patterns`を空配列にする。
- 原因が分からない場合も、確認できる誤りの説明は返せる。
- `cause_type`は以下を候補とする。

| 値                         | 意味                         |
| -------------------------- | ---------------------------- |
| blank                      | 空欄                         |
| careless_mistake           | ケアレスミスの可能性         |
| possible_understanding_gap | 理解不足の可能性。断定しない |
| undetermined               | 原因を判断できない           |

各パターンの対象問題番号は、確認済みの誤答一覧に含まれることをBEで検証する。

#### 状態ごとのレスポンス

いずれの状態も、判定処理が正常に終了した場合はHTTP `200 OK`を返す。
ただし、利用回数の加算対象は`completed`のみとする。

| status | unit_status | 画面動作 | 利用回数 | 分析記録 |
| --- | --- | --- | --- | --- |
| completed | supported | 分析結果・コメントを表示 | BEで1回加算済み | BEで保存済み |
| unit_undetermined | undetermined | 判定困難の旨を表示後、ホームへ戻る | 加算しない | 保存しない |
| unsupported | unsupported | 対象外の旨を表示後、ホームへ戻る | 加算しない | 保存しない |

対象外・判定困難の場合はパターン分析・コメント生成を行わず終了する。
対象単元のStage B正常完了時に、BEが同一トランザクションで保存・加算を確定する。

| 項目                        | キー必須 | completed            | unit_undetermined   | unsupported    |
| --------------------------- | -------- | -------------------- | ------------------- | -------------- |
| analysis_request_id         | 必須     | UUID文字列           | UUID文字列          | UUID文字列     |
| status                      | 必須     | `completed`          | `unit_undetermined` | `unsupported`  |
| unit_status                 | 必須     | `supported`          | `undetermined`      | `unsupported`  |
| unit                        | 必須     | 単元オブジェクト     | `null`              | `null`         |
| score                       | 必須     | 確認済み得点         | 確認済み得点        | 確認済み得点   |
| max_score                   | 必須     | 確認済み満点         | 確認済み満点        | 確認済み満点   |
| score_rate                  | 必須     | BE計算値             | BE計算値            | BE計算値       |
| incorrect_question_numbers  | 必須     | 配列                 | `null`              | `null`         |
| analysis_result             | 必須     | 分析結果オブジェクト | `null`              | `null`         |
| comment_title               | 必須     | 文字列               | `null`              | `null`         |
| comment_body                | 必須     | 文字列               | `null`              | `null`         |
| message                     | 必須     | `null`               | 判定困難の案内文    | 対象外の案内文 |

対象外・判定困難の場合も、判定処理が正常に終了していれば`200 OK`を返す。
分析結果・コメントは`null`とする。

FEは判定結果の案内のみを表示し、分析結果画面には進まずホームへ戻す。
レスポンスに含まれる得点・満点・得点率は表示・永続保存に使用しない。
利用回数は加算せず、分析記録も保存しない。

`incorrect_question_numbers`の`null`は、誤答一覧を結果として返さないことを示し、全問正解を表す空配列とは区別する。

対象外の場合：

```json
{
  "analysis_request_id": "d85a0a9f-1234-4a56-8b90-123456789abc",
  "status": "unsupported",
  "unit_status": "unsupported",
  "unit": null,
  "score": 80,
  "max_score": 100,
  "score_rate": 80.0,
  "incorrect_question_numbers": null,
  "analysis_result": null,
  "comment_title": null,
  "comment_body": null,
  "message": "このテストの単元は分析対象外のため、分析を終了します。利用回数は消費されません。"
}
```

判定困難の場合：

```json
{
  "analysis_request_id": "d85a0a9f-1234-4a56-8b90-123456789abc",
  "status": "unit_undetermined",
  "unit_status": "undetermined",
  "unit": null,
  "score": 80,
  "max_score": 100,
  "score_rate": 80.0,
  "incorrect_question_numbers": null,
  "analysis_result": null,
  "comment_title": null,
  "comment_body": null,
  "message": "このテストの単元を特定できなかったため、分析を終了します。利用回数は消費されません。"
}
```

### 3.5 保存済み分析結果の再取得

保存・加算された結果が画面へ届かなかった場合、FEは同じ`analysis_request_id`を指定して結果を再取得する。FEの表示完了通知APIは設けない。
再取得APIのHTTPメソッド・パス・未保存時の応答形式は、FE・BEレビューで確定する。

- BEは認証済みユーザーと分析処理IDの所有者を照合する。
- 認証済みユーザーのIDと`analysis_usages.analysis_request_id`で利用実績を確認し、`analysis_records.analysis_usage_id`で対応する保存済み結果を取得する。
- 保存済みの場合は一時データの有無・保持期限にかかわらず、永続DBから第3.4節の正常完了結果を返す。AI分析の再実行・再保存・再加算は行わない。
- 保存済み結果の再取得を、Phase2の過去の履歴詳細表示とは区別する。
- 未保存の場合の処理状態確認・通信再試行は第5章に従う。必要な一時データが期限切れの場合は`410 ANALYSIS_EXPIRED`を返す。
- 対象外・判定困難は分析記録・利用実績を保存しない。判定結果の再送用の一時保持は、第5章とIssue #27の保持方針に従う。

### 3.6 学習履歴一覧

```http
GET /v1/analysis-records?limit=20&offset=0
Authorization: Bearer <Firebase ID token>
```

ページングは`limit`・`offset`方式を案とする。

| パラメータ | デフォルト | 制約   |
| ---------- | ---------- | ------ |
| limit      | 20         | 1〜100 |
| offset     | 0          | 0以上  |

並び順は`recorded_at DESC, id DESC`を案とする。

```json
{
  "items": [
    {
      "id": "10",
      "recorded_at": "2026-09-26T03:20:00Z",
      "unit": {
        "code": "division",
        "name": "わり算"
      },
      "score": 80,
      "max_score": 100
    }
  ],
  "limit": 20,
  "offset": 0,
  "has_more": false
}
```

データがない場合は`items: []`を返す。過去の分析結果・AIコメントは一覧レスポンスに含めない。

### 3.7 苦手単元ランキング

```http
GET /v1/rankings/units
Authorization: Bearer <Firebase ID token>
```

```json
{
  "items": [
    {
      "rank": 1,
      "unit": {
        "code": "division",
        "name": "わり算"
      },
      "average_score_rate": 70.0,
      "record_count": 2
    },
    {
      "rank": 2,
      "unit": {
        "code": "addition_subtraction_written",
        "name": "たし算とひき算の筆算"
      },
      "average_score_rate": 85.0,
      "record_count": 1
    }
  ]
}
```

- 対象ユーザーの全期間の記録を集計する。
- 単元ごとの保存済み得点率の平均を算出する。
- 平均を小数第1位へ四捨五入した値で順位を決める。
- 低い値を上位とし、同率は同順位とする。
- 順位は「1位・1位・3位」方式とする。
- 同順位内の表示順は単元コード順を案とする。
- 記録のない単元は含めない。対象記録がなければ`items: []`を返す。

### 3.8 利用状況

認証済みユーザーの当月の利用回数と、利用回数・契約状態に基づく分析可否を取得する。
`blocked_reason`の追加と判定の優先順位は、Issue #23・#37の合意事項とし、PR #153の実装と照合済み。

```http
GET /v1/usage
Authorization: Bearer <Firebase ID token>
```

リクエスト本文は不要とする。

成功レスポンス：`200 OK`

```json
{
  "can_analyze": true,
  "used_count": 1,
  "free_limit": 2,
  "blocked_reason": null
}
```

| 項目 | 型 | 内容 |
| --- | --- | --- |
| can_analyze | boolean | 当月の上限未満で、無料枠が残っている、または有効な月額プランがある場合はtrue |
| used_count | integer | 当月の利用回数。0以上。有料プランでの利用も含む |
| free_limit | integer | 月間の無料利用上限。MVPでは2 |
| blocked_reason | string / null | `plan_required`・`monthly_limit_reached`・`null`。分析不可の理由。分析できる場合はnull |

判定は次の優先順位とする。月間上限は設定値とし、MVPでは10回（無料分を含む）とする。

| 優先順位 | 条件 | can_analyze | blocked_reason | UI-002の表示 |
| --- | --- | --- | --- | --- |
| 1 | 当月10回以上。契約の有無は問わない | false | `monthly_limit_reached` | 押せない上限の案内。UI-008へ進ませない |
| 2 | 当月10回未満で、無料枠を使い切り、有効な月額プランがない | false | `plan_required` | ［3回目以降は有料です］ |
| 3 | 当月10回未満で、無料枠が残っている、または有効な月額プランがある | true | `null` | ［テストを分析する］ |

月の途中で解約し、当月10回以上利用している場合も`monthly_limit_reached`を優先する。再契約すれば当月の分析を再開できるような有料案内を出さない。

- 当月の集計期間は、日本時間（Asia/Tokyo）の暦月とする。集計・加算のルールは第5章に従う。
- 分析可否はBEで判定し、FEでは利用回数から独自に計算しない。
- UI-002では、`blocked_reason`に応じて分析ボタン・有料案内ボタン・上限の案内を切り替え、同時に表示しない。文言は画面設計書のUI-002に従う。
- 無料枠・月間上限を使い切った場合も、このAPIは`200 OK`で`can_analyze: false`と該当する`blocked_reason`を返す。
- この応答は取得時点の利用可否を示す。Stage A実行前にもBEで利用回数・契約状態を確認する。

### 3.9 現在の契約状態

```http
GET /v1/subscriptions/current
Authorization: Bearer <Firebase ID token>
```

認証済みユーザーの契約状態を返す。`is_subscribed`は契約の`status`が`active`のときだけ`true`とし、その他の状態・契約なしは`false`とする。分析可否はこの値だけで決めず、無料枠・月間上限を反映した`GET /v1/usage`を使用する。

リクエスト本文は不要。成功時は契約の有無にかかわらず`200 OK`を返す。

契約がない場合：

```json
{
  "is_subscribed": false,
  "status": null,
  "current_period_end": null
}
```

| 項目 | 型 | 内容 |
| --- | --- | --- |
| is_subscribed | boolean | `status`が`active`の場合のみtrue。その他の状態・契約なしはfalse |
| status | string / null | 保存されたStripe契約の状態。契約がない場合はnull |
| current_period_end | string / null | 契約期間の終了日時。UTCのISO 8601形式。契約なし・期間未確定時はnull |

- 契約が存在しても`active`以外であれば`is_subscribed: false`とし、契約なしと区別するため`status`には保存された状態を返す。
- 本人の契約のうち`active`を優先し、なければいちばん新しい契約を返す。同じ優先度では`created_at`降順、同日時なら`id`降順で選ぶ（PR #147）。更新日時順では選ばない。
- 利用状況APIと合わせて取得・表示する。決済から戻った際の再取得は第2章のフローに従う。
- #23から使用するBE内部の判定`payment.service.has_active_subscription(session, user_id)`は、本人の契約に`active`が1件でもあれば`true`を返す。画面用APIも`active`を優先し、解約済みの新しい契約だけを見て未契約と表示しない。

### 3.10 Stripe Webhook（基本処理：PR #145、二重契約対策：PR #147）

```http
POST /v1/webhooks/stripe
Content-Type: application/json
Stripe-Signature: <Stripeの署名ヘッダー>
```

Firebase認証は不要。受信した本文をJSONへ変換する前のバイト列で、`STRIPE_WEBHOOK_SECRET`を使ってStripeの署名を検証する。

正常応答：`200 OK`

```json
{
  "received": true
}
```

| 条件 | 処理・応答 |
| --- | --- |
| 署名がない・不正・署名後に本文が変更された | `400 INVALID_WEBHOOK_SIGNATURE`。契約を更新しない |
| Webhook署名検証の設定がない | `503 PAYMENT_SERVICE_UNAVAILABLE` |
| `customer.subscription.created`・`customer.subscription.updated`・`customer.subscription.deleted` | Stripeから最新の契約状態を取得して保存する |
| 対象外のイベント（請求書イベント等） | 契約を更新せず`200 OK` |
| 処理済みのイベントID | 二重処理せず`200 OK` |
| Stripeからの最新状態取得に必要な設定がない・取得に失敗した | ロールバックして`503 PAYMENT_SERVICE_UNAVAILABLE`。Stripeによる再送を受け付ける |
| 重複と判定した契約の自動解約に必要な設定がない・解約に失敗した | ロールバックして`503 PAYMENT_SERVICE_UNAVAILABLE`。処理済みイベントとして記録せず、Stripeの再送で再試行する（PR #147） |
| 最新の契約にアプリの`metadata.user_id`がない・数値として読めない | 警告を記録し、契約は保存せずイベントの処理記録のみ保存して`200 OK` |

- 契約IDごとにPostgreSQLの`pg_advisory_xact_lock`を取り、最新状態の取得から保存・コミットまでを1件ずつ処理する。行が未作成の新規契約にも適用する。
- イベント本文の古い状態をそのまま保存せず、ロック取得後にStripeから取得した最新状態を保存する。
- `stripe_webhook_events.event_id`のUNIQUE制約で重複を防ぎ、イベントの処理記録と契約の追加・更新を同一トランザクションで確定する。
- アプリのユーザーとの紐付けは契約の`metadata.user_id`を使用する。Checkout作成時に`subscription_data.metadata.user_id`へ認証済みユーザーのIDを設定する（PR #147）。
- PR #147の二重契約対策では、ユーザーごとのロックの中で、DBで`active`となっている本人の別契約をStripeから取り直す。Stripe上でも`active`の契約がある場合のみ、今回通知を処理する`active`契約をStripeで自動解約し、解約後の状態を保存する。別契約がStripe上では終了済み等の場合はDBを最新状態にそろえ、今回の契約は残す。確認に失敗した場合はロールバックして`503 PAYMENT_SERVICE_UNAVAILABLE`を返し、未確認のまま自動解約しない。
- DBに保存済みの状態が`canceled`・`incomplete_expired`の契約は、後から来た古い状態で更新しない。`active`・`past_due`など、終了前の状態同士の競合による順序のずれはMVPでは許容する（PR #147）。
- 自動解約はテストモードでの対応とし、返金処理は含まない（PR #147）。
- 同じStripe契約は更新し、既存行の`user_id`は上書きしない。再加入等で契約IDが変わる場合は別の行を追加する。
- 単一プランの契約期間は先頭の明細（`items.data[0]`）から取得する。期間が取得できない場合はNULLとする。
- WebhookのAPIバージョンはSDKと合わせる。PR #145のSDKでは`2026-08-26.dahlia`を使用し、不一致時は警告を記録する。
- エラーの本文は第4章の共通形式を使用する。処理記録のテーブル定義はDB設計書を参照する。

### 3.11 Checkout作成（PR #147）

```http
POST /v1/billing/checkout-sessions
Authorization: Bearer <Firebase ID token>
```

認証済みユーザーの月額プラン契約用Checkoutを作成する。リクエスト本文は不要。`Idempotency-Key`は使用しない。

成功レスポンス：`201 Created`

```json
{
  "checkout_url": "https://checkout.stripe.com/..."
}
```

| 項目 | 型 | 内容 |
| --- | --- | --- |
| checkout_url | string | FEが新しいタブで開くStripe CheckoutのURL |

- `mode`は`subscription`、価格は`STRIPE_PRICE_ID`、数量は1にBEで固定する。成功・キャンセル時の戻り先は`STRIPE_SUCCESS_URL`・`STRIPE_CANCEL_URL`を使用する。価格・数量・戻り先をFEから受け取って変更しない。
- `client_reference_id`と`subscription_data.metadata.user_id`には、認証済みのアプリ内ユーザーIDを文字列で設定する。ユーザーIDをFEから指定させない。
- ユーザーごとのトランザクションロックを取得してから、契約中かどうかの確認・本人の開いているCheckoutの失効・新しいCheckoutの作成を順に行う。成功時はStripeの最新状態にそろえたDB更新をコミットし、失敗時はロールバックしてロックを解放する。
- DBで`active`となっている本人の契約をStripeから取り直し、Stripe上でも`active`の場合は`409 ALREADY_SUBSCRIBED`を返す。Stripe上ではすでに解約済み等の場合はDBを最新状態にそろえてCheckout作成へ進む。確認できない場合は`503 PAYMENT_SERVICE_UNAVAILABLE`を返す。
- 既存の開いているCheckoutは、Stripe上の`status: open`のセッションから`client_reference_id`で本人のものを識別して失効させる。新しいCheckoutを作ると、以前の未払いのタブは使えなくなる。Checkoutの作成だけでは新しい契約をDBへ登録せず、新規契約はWebhookで反映する。既存契約をStripeで再確認した際の状態更新は、Checkout作成成功時にコミットする。
- Stripeの設定が足りない、既存Checkoutの失効・新規作成に失敗した、またはURLを取得できない場合は`503 PAYMENT_SERVICE_UNAVAILABLE`を返す。
- 新しいCheckoutの作成と、同じキーへの同じ応答を保証する冪等性は区別する。再送時に同じ`checkout_url`を返す保証はなく、開いている本人のCheckoutを失効させて作り直す。
- FEは`checkout_url`が`https://checkout.stripe.com`配下であることを確認し、新しいタブで開く。`status=success`の戻り先では`GET /v1/subscriptions/current`を直ちに実行し、1秒間隔・最大10回まで再取得する。`is_subscribed: true`を確認した場合だけ成功表示にする。
- 決済から戻った際の契約状態・利用状況の再取得は第2章に従う。テストモードのデモ手順は、PR #147の`backend/README.md`「月額プランの決済」とルート`README.md`を参照する。

## 4. エラーレスポンス

### 共通フォーマット

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "入力内容を確認してください。",
    "details": [
      {
        "field": "max_score",
        "reason": "満点は1以上の整数で入力してください。"
      }
    ]
  },
  "request_id": "req-example"
}
```

- `request_id`はHTTPリクエスト追跡用で、分析処理IDとは区別する。
- `details`は補足がない場合、空配列とする。
- FEは`message`の文言ではなく、`code`で処理を分岐する。
- スタックトレース、APIキー、答案の全文等をエラーに含めない。

### エラー一覧案

| HTTP | code                    | 内容                                                |
| ---- | ----------------------- | --------------------------------------------------- |
| 401  | UNAUTHENTICATED         | 認証情報がない・無効・期限切れ                      |
| 404  | USER_NOT_INITIALIZED    | アプリ内ユーザーが未登録                            |
| 404  | ANALYSIS_NOT_FOUND      | 分析処理が存在しない、または本人の処理ではない      |
| 409  | ANALYSIS_STATE_CONFLICT | 確認前・分析未完了等、現在の状態では操作できない    |
| 409  | ALREADY_SUBSCRIBED      | 本人にactiveの契約があるため、新しいCheckoutを作成しない |
| 409  | IDEMPOTENCY_CONFLICT    | 同じ冪等キーで異なる内容を送信した                  |
| 409  | ANALYSIS_IN_PROGRESS    | 同じ処理が実行中                                    |
| 410  | ANALYSIS_EXPIRED        | 分析中データの保持期限が切れている                  |
| 413  | IMAGE_TOO_LARGE         | 画像容量上限を超えた                                |
| 415  | UNSUPPORTED_IMAGE_TYPE  | 対応していない画像形式                              |
| 422  | VALIDATION_ERROR        | 枚数・得点・満点・確認データ等が不正                |
| 422  | IMAGE_UNREADABLE        | 画像の内容を十分に読み取れない                      |
| 403  | PLAN_REQUIRED           | Stage A実行前のチェックで無料枠を使い切り、有効な月額プランがない |
| 403  | MONTHLY_LIMIT_REACHED   | Stage A実行前のチェックで月間上限に達した。契約の有無にかかわらずPLAN_REQUIREDより優先 |
| 400  | INVALID_WEBHOOK_SIGNATURE | Stripe Webhookの署名がない・不正、または本文が不正 |
| 503  | PAYMENT_SERVICE_UNAVAILABLE | Stripeの必要な設定がない・接続できない等により、Checkoutの失効・作成、契約状態の取得、重複契約の自動解約に失敗した |
| 429  | RATE_LIMIT_EXCEEDED     | 短時間のアクセス制限を超えた                        |
| 502  | AI_RESPONSE_INVALID     | AI出力が期待する形式を満たさない                    |
| 503  | AI_SERVICE_UNAVAILABLE  | AIサービスが利用できない                            |
| 504  | ANALYSIS_TIMEOUT        | 分析処理がタイムアウトした                          |
| 500  | INTERNAL_ERROR          | アプリ内部の予期しないエラー                        |

入力検証エラーも共通形式に統一する。

Stage Bの判定結果が`completed`・`unsupported`・`unit_undetermined`のいずれの場合も、処理自体が正常に完了していればHTTP `200 OK`を返す。入力不備・通信障害・AI出力形式不正等は、別途エラーレスポンスとして返す。

## 5. レート制限・冪等性

### 月間利用回数の集計

無料枠の月間利用回数は、日本時間（Asia/Tokyo）の暦月で集計する。
集計範囲は、当月1日00:00:00以上、翌月1日00:00:00未満とする。

BEは集計範囲の境界をUTCへ変換し、`analysis_usages.counted_at`で集計する。
日時のDB保存・API表現はUTCを維持する。

利用実績を削除して回数をリセットするのではなく、
月が変わった時点で新しい集計期間を使用する。

### レート制限

- PR #150の仕様として、Stage A（読み取り）とStage B（分析）の両方に、認証済みユーザーごとに適用する。両者は別々のカウンターで数え、それぞれ1分3回までとする。回数は#10の暫定値を引き継ぎ、計測結果を踏まえて見直す。
- Memcachedで短時間のアクセス回数を管理する。Stage Aだけを繰り返す利用も制限の対象とする。
- キーは`ユーザーID:対象:UTCの分単位の時刻（YYYYMMDDHHmm）`とする。対象はStage Aが`analysis_a`、Stage Bが`analysis_b`。形式例：`7:analysis_a:202610251430`・`7:analysis_b:202610251430`（ユーザーIDは例）。
- キーの有効期限は120秒とする。制限の区切りはUTCの「分」で、次の分では新しいキーを使う。120秒は古いカウンターを消す期限であり、利用者を120秒待たせる意味ではない。
- 同じ分・同じユーザー・同じ対象の4回目以降は、AIを呼ばず`429 RATE_LIMIT_EXCEEDED`を返す。`Retry-After`には、次の分までの秒数（`60 - 現在の秒`、1〜60）を返す。
- Stage Bは保存済みの分析処理IDかどうかの確認後、AIを呼ぶ前にカウントする。Stage AとStage Bを各1回実行する通常のフローは、各カウンターを1回ずつ消費する。
- Memcachedに接続できない場合は、レート制限をせずに処理を通す。DBの月間利用回数・契約状態のチェックは維持する。
- 「Memcachedに接続できず、レート制限をせずに通した」旨を警告ログに記録し、ログから停止に気づけるようにする。ユーザーの個人情報やユーザーID・キーの値はログに記録しない。
- Memcachedのレート制限と、DBの月間利用回数は別に扱う。
- カウンターの初期化は`add(..., noreply=False)`で応答を待ってから`incr`する。`incr`でカウンターを取得できなかった場合も、接続失敗時と同様に制限せず通し、警告ログを残す（PR #150）。
- 同時実行数そのものの上限は、本制限とは別に確定する。
- 保存済み結果の再取得時のレート制限は、AI分析を実行する場合と区別して別途確定する。

### POSTの冪等性

| API          | 方針                                                                          |
| ------------ | ----------------------------------------------------------------------------- |
| Stage A      | `Idempotency-Key`を必須とし、同じ画像送信の再試行で分析処理を重複作成しない   |
| Stage B      | `Idempotency-Key`を必須とし、同じ確認済みデータの再送でAI分析を重複実行しない |
| 決済開始 | `Idempotency-Key`は使わない。ユーザーごとのロックの中で開いている本人のCheckoutを失効させてから新規作成する。active契約があれば409（第3.11節、PR #147） |
| Stripe通知 | `stripe_webhook_events.event_id`のUNIQUE制約で同じ通知を二重処理しない。契約IDごとのロックと最新状態の再取得で、異なる通知の同時処理による古い状態の上書きを防ぐ（PR #145） |

- 以下の冪等キー・409応答のルールは分析APIを対象とする。Stripe通知は第3.10節、決済開始APIは第3.11節の仕様に従う。
- 冪等キーはユーザー・操作単位で管理する。
- 同じキー・同じ内容なら、処理を重複実行せず保持済みの結果を返す。
- 同じキーで内容が異なる場合は`409 IDEMPOTENCY_CONFLICT`を返す。
- 処理中の場合は`409 ANALYSIS_IN_PROGRESS`を返し、再試行までの秒数を`Retry-After`ヘッダーで示す。
- FEは`Retry-After`で指定された時間を待ち、同じURL・リクエスト内容・`Idempotency-Key`で再送する。
- 通信タイムアウトだけでは分析失敗とみなさない。同じリクエストの再送により、BE側の処理状態を確認する。
- BEは処理中なら409、完了済みなら保持済みの応答を返す。状態確認のための再送では、分析を重複実行しない。
- 対象外・判定困難の判定結果も、元のキーによる再送時には保持済みの応答を返す。
- BEで処理失敗が確定している場合は、その失敗に対応するエラーを返す。
- 保存済み結果は一時データの期限にかかわらず返す。未保存で必要な一時データが期限切れの場合は`410 ANALYSIS_EXPIRED`を返す。
- 再試行間隔・最大待機時間は、#27・#28での性能検証を踏まえ、FE・BEで確定する。
- 冪等キー・入力照合情報・応答の保持先と期間は、BE設計で確定する。
- 結果再送のための一時保持と、画像・抽出データの削除方針を整合させる。
- 処理期限切れ後に同じ分析処理を暗黙に再実行しない。
- FEは操作開始時に冪等キーを生成し、通信エラー等による同じ操作の再試行では同じキーを使用する。
- Stage AとStage Bでは別のキーを使用する。

### DBでの二重加算防止

- `analysis_usages.analysis_request_id`のUNIQUE制約を使用する。
- `analysis_records.analysis_usage_id`のUNIQUE制約を使用する。
- 利用実績と分析記録の所有者が一致することをBEで確認する。
- 利用実績と分析記録は、必ず同一トランザクションでセットとして確定する。
- UNIQUE制約による二重登録防止と、BEの保存処理によるセット作成を組み合わせる。
- PR #153では、ユーザーごとの利用実績保存ロック取得後に保存済みの分析処理IDを再確認し、無料枠・月間上限を数え直してから保存する。同じ分析処理IDが保存済みの場合は上限エラーより`409 ANALYSIS_STATE_CONFLICT`を優先し、再保存・再加算しない。

### 未確定事項・担当間の確認

| 項目                        | 確認内容                                                                                                               |
| --------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| AIの入出力                  | 本書のJSON形式、原因分類、全問正解時の分析結果を検討する                                                               |
| 確認画面                    | 正誤不明・問題の読み取り漏れ・修正不能時の操作を確定する                                                               |
| 問題番号                    | 表裏での重複、番号不明時の保存表記を確定する                                                                           |
| 冪等性                      | キー・応答の保持方式と期間、失敗確定後に新しいキーで再試行を許可する条件を確定する                                     |
| 性能（検証後決定）          | 画像容量上限は#27で検証する。同期処理の待ち時間・タイムアウト・再試行間隔は#27・#28の検証結果を踏まえて確定する        |
| 履歴                        | ページング方式・並び順をFE担当と合意する                                                                               |
| 利用制限・課金 | Checkout・二重契約対策・active優先の現在契約取得はPR #147と、無料枠・月間上限の判定と保存時の同時実行対策はPR #153と照合済み。画面との連携・Webhook反映待ちの再取得はIssue #38で確定。通常の解約操作は別途確認する |
| 結果再取得 | HTTPメソッド・パス、未保存時の応答、FEでの分析処理IDの保持・復元方法を確定する |
| レート制限 | Stage A・B別カウンター、UTCの分単位キー、期限120秒、Retry-After、カウンター初期化はPR #150と照合済み。同時実行数の上限と、暫定1分3回の数値の見直しは別途確認する |
| OpenAPI | 共通・分析・履歴は#8で作成し、利用制限・決済関連には本書の#10決定事項を反映する |

### レビューで確定する仕様

#### AIの入出力

- Stage A・Stage BのJSON形式は、第3章の形式を採用する案とする。
- 全問正解の場合、`incorrect_question_numbers`と`analysis_result.patterns`は空配列とする。
- 全問正解の場合も、今回の結果に応じたコメントのタイトル・本文を返す。
- Stage Bの確認済み解答は文字列とし、空欄は空文字で表す。読み取り不明を示す`null`は、保護者の確認・修正後には許可しない。
- 必須項目・NULL可否・原因分類は、OpenAPIで明示して担当者間で確認する。
- AIが指定形式や分類で安定して返せるかを#27・#28で検証する。

#### 確認画面

- 正誤が不明な問題は、保護者が「正解／不正解」を選択する。
- FEは読み取った得点を得点欄に初期表示し、保護者が確認・修正する。読み取れない場合は保護者が入力する。満点は保護者が入力する。
- 解答内容の読み取りに誤りがある場合は、保護者が子どもの実際の解答を入力する。
- 問題の追加・削除、問題文・計算過程の編集はMVP対象外とする。
- 確認画面での修正では補えず、分析に必要な情報が不足している場合は、再撮影・再アップロードを案内する。
- 計算過程が読み取れないことだけを理由に、再アップロードを必須としない。計算過程を必要とする原因判定は無理に行わない。
- 読み取り不備の検出方法、分析を続行できる条件、APIでの返却方法は、Issue #27で#28の必要情報と整合させて設計・検証する。

#### 問題番号

- `question_id`は分析処理内で一意とし、確認・修正から分析まで維持する。
- 保存用の問題番号は、BEで「画像番号:用紙上の問題番号」に整形する。
- 例：画像1の問1(2)は`1:1(2)`とする。
- 用紙上の問題番号が不明な場合は、`1:番号不明-q3`のように仮識別子であることを明示する。
- 番号のみが不明でも、分析に必要な問題内容・解答・正誤が確認できていれば分析可能とする。
- 同じ表記の番号が同一画像内に複数ある場合は、`question_id`を付けて区別する。
- `incorrect_question_numbers`と、分析結果内の`question_numbers`には同じ保存用表記を使用する。
- 画像が1枚の場合も、保存用の問題番号には`1:`を付与する。
- Stage Aの`question_number`は用紙上の表記を保持し、画像番号は`image_index`として別に返す。

##### 寄り添い型コメント（Issue #29レビュー反映）

- コメントは、検証済みのStage B分析結果と確認済みテキストを用い、単元判定・パターン分析とは別のAI呼び出しで生成する。既存のZDR対応OpenRouterクライアントを使用する。
- AI出力の`comment_title`と`comment_body`は必須の文字列とし、前後の空白を除去して以下を検証する。
  - `comment_title`：1〜60文字
  - `comment_body`：150〜800文字
- 満点時のレスポンスの`comment_title`は「今回のテストは満点でした」に固定する。
  - 合意した条件：`score == max_score`かつ、`confirmed_questions`に`grading == "incorrect"`の問題が存在しないこと。
  - 現在の実装は`score == max_score`のみで判定する。不正解0問の条件追加は、Issue #29のPRマージ後に別PRで対応する。
  - `comment_body`は通常どおり生成・検証する。固定タイトルを返す場合も、本文の生成失敗を成功扱いにしない。
- コメントのJSON形式・schema検証に失敗した場合は、同じ入力でコメント生成のみ1回再試行する。
- 再試行後も検証に失敗した場合は、`502 AI_RESPONSE_INVALID`を返す。`completed`は返さず、保存・利用回数加算へ進まない。
- 通信障害等は既存のOpenRouterクライアントの再試行方針に従う。コメント生成側で追加の通信再試行は行わない。
  - タイムアウト：`504 ANALYSIS_TIMEOUT`
  - その他のOpenRouter接続エラー：`503 AI_SERVICE_UNAVAILABLE`
- 単元が対象外または単元判定困難の場合は、コメント生成を行わず、`comment_title`と`comment_body`を`null`とする。
- 原因が`undetermined`でも、対象単元の分析結果としてコメントを生成する。原因の候補を新たに補わず、確認できた事実と具体的な確認方法を伝える。

#### 履歴一覧

- 並び順は`recorded_at DESC, id DESC`とする。
- ページングは`limit`・`offset`方式とする。
- `limit`は既定値20、最小1、最大100とする。
- `offset`は既定値0、最小0とする。
- 対象データがない場合は`items: []`、`has_more: false`を返す。

#### 冪等性・再試行

> 「分析失敗確定後に、新しいキーで再試行を許可する条件」は追加提案とする。
> 通信タイムアウト時・処理中の再送方法は、第5章「POSTの冪等性」に従う。

- 同じ操作の通信再試行では、同じ冪等キーを使用する。
- 入力内容を変更する場合は、新しい冪等キーを使用する。
- 入力検証エラーでは分析を開始せず、修正後の送信を許可する。
- 同じ分析処理が実行中の場合は、キーが異なっても重複実行しない。
- Stage B成功後の内容変更・再分析はMVP対象外とする。
- 分析失敗が確定し、処理が停止しており、必要な一時データが有効な場合は、新しいキーによる再試行を許可する案とする。
- 通信タイムアウトだけでは分析失敗とみなさず、BE側の処理状態を確認する。
- 未保存で必要な一時データが期限切れの場合は、再アップロードを案内する。保存済み結果は同じ分析処理IDで再取得する。
- 保存・加算が既に確定済みの場合は、一時データの期限にかかわらず、確定済みの結果を返し、再保存・再加算しない。
