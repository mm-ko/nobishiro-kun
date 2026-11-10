# Backend

FastAPIを使った学習トラッキングアプリのBackendです。Pythonは3.13.15を使用します。

## ローカル起動

Backendディレクトリで仮想環境を作成し、依存関係をインストールします。

### WSL（Ubuntu）/ macOS

```bash
cd backend
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

### Windows PowerShell

```powershell
cd backend
py -3.13 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

`py -3.13` が実行できない場合は、以下のコマンドでPythonのバージョンを確認してください。

```powershell
python --version
```

Python 3.13系が使用されている場合は、以下のコマンドでも仮想環境を作成できます。

```powershell
python -m venv .venv
```

Frontendから接続する場合は、環境変数 `FRONTEND_ORIGIN` に許可するOriginを設定します。
例：`FRONTEND_ORIGIN=http://localhost:3000`。未設定の場合、CORSで許可するOriginはありません。

```bash
uvicorn app.main:app --reload
```

起動後、`http://localhost:8000/docs` でSwagger UIを確認できます。

## Docker単体起動

Backend・PostgreSQL・MemcachedをDocker Composeでまとめて起動する手順は、リポジトリルートの
`README.md` を参照してください。ここではBackend単体での起動方法を記載します。
Backendディレクトリをbuild contextとして実行します。

```bash
cd backend
docker build -t nobishiro-backend .
docker run --rm -p 8000:8000 \
  -e FRONTEND_ORIGIN=http://localhost:3000 \
  nobishiro-backend
```

コンテナ起動後、`http://localhost:8000/docs` を開きます。DockerfileではUvicornを
`0.0.0.0:8000` で起動します。

## 環境変数

必要な環境変数名は `.env.example` を参照してください。実値を設定した `.env` はGitへ
コミットせず、Dockerイメージにも含めません。設定値は `app/core/config.py` の
`Settings` から参照します。CORSの許可Originは `FRONTEND_ORIGIN` の1件に限定します。

### ローカルの秘密情報

- Firebaseサービスアカウントキーは `backend/secrets/firebase-service-account.json` に配置します。
- `FIREBASE_CREDENTIALS_PATH` には `secrets/firebase-service-account.json` を設定します。
  相対パスは `.env` や `config.py` の場所ではなく、Backendプロセスの起動時の作業ディレクトリを基準に解決されます。READMEの起動コマンドどおり `backend/` から実行してください。別のディレクトリから起動する場合は、正しい絶対パスを設定します。
- `backend/secrets/` は `.gitignore` と `.dockerignore` で除外しています。サービスアカウントキーをGitに追加したり、Dockerイメージへ含めたりしないでください。キーはパスワードマネージャなど承認済みの安全な方法で受け取り、チャットやリポジトリには貼り付けないでください。
- ローカル環境変数の値を保存する場合は `backend/.env` に置き、共有・コミットしないでください。`.env.example` には変数名だけを記載します。
- 現在の `Settings` はプロセス環境変数を読み込みますが、`.env` ファイルを自動では読み込みません。`.env` に値を保存しただけではアプリへ反映されないため、起動前に各自のシェルやIDEで環境変数として設定してください。
- Docker Composeで起動する場合は、`docker-compose.yml` の `env_file` により `backend/.env` の値がコンテナの環境変数として渡されます。また、`backend/secrets/` はコンテナの `/app/secrets` へ読み取り専用でマウントされます（鍵はDockerイメージに含めません）。

## ディレクトリと責務

| パス | 責務 |
| --- | --- |
| `app/main.py` | FastAPIアプリ、middleware、共通API routerの登録 |
| `app/core/` | 環境変数などアプリ共通設定、セキュリティ処理 |
| `app/db/` | DB接続・セッション・全テーブルモデルの配置先 |
| `app/api/router.py` | 各featureのrouterを集約 |
| `app/features/auth/` | Firebase認証と認証済みユーザーの依存処理 |
| `app/features/test_analysis/` | 入力検証とStage A／Stage Bのフロー制御 |
| `app/features/ai_analysis/` | AI処理、Stage別prompt、OpenRouter client |
| `app/features/learning_history/` | 学習履歴・ランキングとDBアクセス |
| `app/features/usage/` | 利用回数・レート制限 |
| `app/features/payment/` | Stripe決済と決済状態 |
| `app/shared/` | 複数featureで実際に共有する処理 |
| `tests/` | feature単位のテスト配置先 |

### Feature間の依存

依存は次の向きに限定し、循環参照を作りません。他featureの処理を呼び出す場合は、
原則としてそのfeatureの `service.py` を経由し、`repository.py` は直接呼びません。

```text
test_analysis -> ai_analysis
test_analysis -> usage
test_analysis -> learning_history
usage -> payment
```

認証が必要な各featureのrouterは、共通認証依存として
`app/features/auth/dependencies.py` を利用します。

## 単体テスト（#85・#39）

Python 3.13の仮想環境を有効にし、`backend/` から実行します。

```bash
python -m pip install -r requirements.txt
python -m pytest
```

`pytest` だけでも同じテストを検出します。既存のunittest形式のテストも実行対象です。
feature単位、またはファイル単位で実行する場合はパスを指定します。

```bash
python -m pytest tests/auth
python -m pytest tests/ai_analysis/test_openrouter_client.py
python -m pytest tests/ai_analysis/test_stage_a_extraction.py
```

全件成功すると末尾に `passed` が表示され、終了コードは0になります。
失敗時は失敗したテストと期待値を確認してください。スキップやテスト0件を成功扱いにせず、
PRには実行コマンド・件数・結果を記載します。

### テストの配置・命名とCIの扱い（#39）

テストは `tests/<feature>/` に配置し、フォルダ名を含むパスで対象のfeatureを識別します。
既存テストは改名せず、ファイル名には確認対象や役割が分かる名前を使います。
pytestでのimport衝突を避けるため、別のfeatureでも同名のテストファイルは作りません。
テストファイルを配置したディレクトリの `.gitkeep` は不要なため削除します。

CI（#43）は見送りとし、#39の「ローカルとCIで同じテストを実行できる構成」は対象外とします。
単体テストの共通実行コマンドは `python -m pytest` とし、PR前に手元で実行します。
CIでの実行確認は行っていません。

### 外部サービス・秘密情報

- `.env` や本物の鍵は不要です。テストからenvファイルを読み込みません。
- `tests/conftest.py` が、テストのimport前に接続先・鍵の環境変数を未設定扱いにし、
  開発用固定ユーザーも無効にします。テストプロセスだけの設定で、ファイルは変更しません。
- OpenRouter・Firebase・Stripeはモックを使います。DNS解決、TCP接続、UDP送信を試みると
  テストが失敗します。localhostへの接続も禁止します。
- FastAPIの `TestClient` は実際のHTTPサーバーへ接続せず、メモリ上で処理します。
  Windowsの内部通信に必要な `socketpair` の生成だけは許可します。
- DBのテストはモックまたはメモリ上のSQLiteを使います。psycopgの同期・非同期の接続入口も
  遮断し、SQLAlchemy経由を含め、本物のPostgreSQLへの接続を試みるとテストが失敗します。
- データにはダミー値・架空の答案を使い、本物のキー・個人情報・答案画像を追加しません。
  出力にローカル変数を含める `--showlocals` は使わないでください。
- 実際のAIを呼ぶ精度・回帰確認は #41、機能別の単体テスト整備は #39で扱います。CI設定（#43）は見送りです。

### Dockerでの実行

Docker Desktop等を起動し、同じく `backend/` から実行します。
以下はPowerShellとBashで共通です。既存のDockerfileを使用します。

```bash
docker build -t nobishiro-backend-test .
docker run --rm --network none -v "${PWD}/tests:/app/tests:ro" -v "${PWD}/scripts:/app/scripts:ro" -v "${PWD}/pytest.ini:/app/pytest.ini:ro" --entrypoint python nobishiro-backend-test -m pytest -p no:cacheprovider
```

イメージにはアプリと依存だけを含め、テスト・検証スクリプト・pytest設定は読み取り専用で
渡します。通常のDockerイメージにテストファイルをコピーする変更はありません。
コンテナはネットワークを切断し、envファイルや鍵のマウントは行いません。
Docker Composeは使用しないため、DB・Memcachedの起動やマイグレーションも不要です。

## レート制限（Memcached）（#24）

読み取り（`POST /v1/analyses`）と分析（`POST /v1/analyses/{analysis_request_id}/result`）は、AI を呼ぶため、短時間の連続実行を Memcached で抑えます（#10 の決定）。

| 項目 | 内容 |
| --- | --- |
| 上限 | 1ユーザーにつき、それぞれ1分で3回まで（暫定値。#30 の計測結果で見直す） |
| 数え方 | 読み取りと分析は別々に数える。キーは `ユーザーID:analysis_a（またはanalysis_b）:分単位の時刻（UTC）`。期限は120秒 |
| 超えたとき | `429 RATE_LIMIT_EXCEEDED` と、次の「分」までの秒数を `Retry-After` で返す。AI は呼ばない |
| Memcached に接続できないとき | 制限せずに通し、「Memcachedに接続できず、レート制限をせずに通しました。」とログに残す（ユーザーやキーの値は残さない）。接続・応答は0.5秒で打ち切る |

- Memcached の接続先は `MEMCACHED_HOST`・`MEMCACHED_PORT`（Docker Compose では `memcached:11211`）。
- 月の利用回数（課金の判定）は DB で数え、Memcached とは別に扱います（#23）。

## Ruff

Ruffの設定は `ruff.toml` に集約しています。Backendディレクトリで実行します。

```bash
python -m ruff check .
python -m ruff format --check .
```

ルートの `.vscode/settings.json` ではPythonファイルに限ってRuffをFormatterに指定し、
保存時の整形を有効にしています。VS CodeでBackendを開発する場合は、Ruff拡張機能
（`charliermarsh.ruff`）をインストールしてください。この設定はFrontendのFormatterには
適用されません。

## 月額プランの決済（Stripe・テストモード）（#25）

月額300円の1プランを、Stripe Checkout で契約します。**テストモードだけで使い、実際の請求はしません。**

| API | 内容 |
| --- | --- |
| `POST /v1/billing/checkout-sessions` | Checkout のURLを返す（201）。価格・数量・戻り先は BE で固定し、FE からは受け取らない。契約中なら `409 ALREADY_SUBSCRIBED`（DB で `active` の契約を Stripe でも確かめ、Stripe ではすでに解約済みなら DB をそろえて作る） |
| `GET /v1/subscriptions/current` | 使える契約（`active` を優先し、なければいちばん新しい契約）の状態を返す。`is_subscribed` は Stripe の状態が `active` のときだけ `true`。契約がなければ `false`・`null`・`null` |
| `POST /v1/webhooks/stripe` | Stripe からの通知。署名を検証し、契約の状態を `subscriptions` に保存する（Firebase の認証は通さない） |

Stripe の設定が足りない、または Stripe に接続できない場合は `503 PAYMENT_SERVICE_UNAVAILABLE` を返します。

### デモの準備

1. `backend/.env` に次を設定します（値は Issue・PR・チャットに貼らない）。
   - `STRIPE_SECRET_KEY`：テスト用の秘密キー（`sk_test_` で始まる）
   - `STRIPE_PRICE_ID`：月額300円の価格ID（`price_` で始まる）
   - `STRIPE_SUCCESS_URL`：例 `http://localhost:3000/plan/result?status=success`
   - `STRIPE_CANCEL_URL`：例 `http://localhost:3000/plan/result?status=cancel`
   - `STRIPE_WEBHOOK_SECRET`：下の手順3で表示される値（`whsec_` で始まる）
2. 契約を保存するテーブル（`subscriptions`・`stripe_webhook_events`）を作ります（初回だけ）。

   ```bash
   docker compose exec backend python -m alembic upgrade head
   ```

   成功しても何も表示されません（エラーが出なければ成功）。
   `docker compose exec backend python -m alembic current` で `0002_payment_tables` と出れば反映済みです。

3. 別のターミナルで [Stripe CLI](https://docs.stripe.com/stripe-cli) を使い、Stripe からの通知を手元の Backend へ転送します。

   ```bash
   stripe login
   stripe listen --events customer.subscription.created,customer.subscription.updated,customer.subscription.deleted --forward-to localhost:8000/v1/webhooks/stripe
   ```

   `stripe login` では、`backend/.env` のキーと同じサンドボックスを選びます（違うサンドボックスの通知は届きません）。
   `stripe listen` は、転送する通知の種類（`--events`）の指定が必要です。アプリが扱う契約の3つの通知だけを指定します。
   最初に表示される `whsec_...` を `STRIPE_WEBHOOK_SECRET` に設定し、`docker compose up -d backend` で Backend を作り直します。デモのあいだは `stripe listen` を止めません。

### テスト用カード

カード番号のほかは、有効期限に未来の日付、セキュリティコードに任意の3桁を入れます。

| 結果 | カード番号 |
| --- | --- |
| 成功 | `4242 4242 4242 4242` |
| 失敗（カードが拒否される） | `4000 0000 0000 0002` |

### 状態の流れ（#10）

- **成功**：Checkout で支払う → Stripe から `customer.subscription.created` が届く → `subscriptions` に `active` で保存 → `GET /v1/subscriptions/current` が `is_subscribed: true` になる
- **失敗**：Checkout の画面でエラーになり、契約は作られない。契約後の更新で支払いに失敗した場合は、Stripe 側で状態が変わり（`past_due` など）、通知で反映される
- **キャンセル**：Checkout から戻ると `STRIPE_CANCEL_URL` へ移動する。何も保存しない
- 通知はアプリへ戻るより遅れて届くことがあるため、画面側は戻ったあとに契約状態を取り直す（#38）

### 注意

- Stripe SDK（`stripe==15.6.1`）は API バージョン `2026-08-26.dahlia` に固定されています。通知の API バージョンが異なる場合は、ログに警告が出ます。警告が出たら、Stripe の管理画面で API バージョンを確認してください。
- 同じ契約の通知は、契約IDごとのロックで1件ずつ処理し、毎回 Stripe から最新の状態を取り直して保存します。処理済みの通知は `stripe_webhook_events` に記録し、二重に処理しません。
- アプリの Checkout 以外で作った契約（`metadata.user_id` がないもの）は保存しません。
- 新しい Checkout を作るときは、同じ人がまだ開いている Checkout を失効させます（ユーザーごとのロックで1件ずつ処理）。2つのタブで別々に支払って、契約が2つできるのを防ぐためです。開いている Checkout は Stripe 側でユーザーごとに絞り込めないため、開いているもの全体から探します（MVPの利用者数が前提）。
- それでも、支払った直後で通知が届く前の数秒の間に、もう一度 Checkout を作って支払うと、契約が2つできることがあります。その場合は、Webhook で同じ人の2つ目の `active` の契約を見つけた時点で、もう一方の契約が Stripe 上でも今 `active` かを確かめ、`active` なら後から来たほうを Stripe ですぐに解約し、`canceled` として保存します（先の契約は残す）。もう一方が Stripe ではすでに解約済み（解約の通知が遅れているだけ）なら、新しい契約は解約せず、もう一方を DB でも最新の状態にそろえます。テストモードのため返金はしません。本番で使う場合は返金も必要です。
- `GET /v1/subscriptions/current` は、`active` の契約があればそれを、なければいちばん新しい契約を返します（解約した2つ目のほうが新しくても、使える契約を返すため）。
- 解約済み（`canceled`・`incomplete_expired`）として保存した契約は、あとから古い状態（`active` など）で上書きしません。Stripe ではこれらの状態から戻ることがないためで、Webhook と Checkout が同時に動いた場合に、解約済みの契約が有料に戻るのを防ぎます。
- 月の利用回数の上限（月10回）と、有料かどうかによる分析可否の判定は #23 で行います。

## 今回の構築範囲

### Stage B入口の暫定実装（#19）

`POST /v1/analyses/{analysis_request_id}/result` は認証済みの確認済みテキスト・整数の得点と満点を受け付けます。
画像・任意メモ・未確認の正誤は受け付けません。単元判定とパターン分析は既存のStage Bを使用します。
単元はDBの `units` から読みます（事前にルートREADMEの単元マスタ投入が必要です）。
コメントは検証済みのStage B分析後に、同じZDR対応クライアントで別途生成します（#29）。タイトルは1〜60文字、本文は150〜800文字で検証し、形式不正時はコメント生成のみ1回再試行します。対象外・単元判定困難では生成せず、全問正解では今回の取り組みをねぎらいます。
コメントの構成・表現はプロンプトで指示しており、schemaで意味まで保証するものではありません。実モデルによる代表ケースの文面確認と、追加呼び出しの処理時間・料金の検証（#30）は別途必要です。
対象単元で正常に完了した場合だけ、利用実績（`analysis_usages`）と分析記録（`analysis_records`）を同じトランザクションで保存し、保存できてから `completed` を返します（#20）。
対象外・判定困難・AIやコメント生成の失敗では、どちらも保存しません。
保存済みの分析処理IDで呼ばれた場合は、AIを呼ばずに `409 ANALYSIS_STATE_CONFLICT` を返します。保存済みの結果を返す再送への対応は未実装です。
残り回数・契約状態のチェックは #23 で行います。分析IDの所有者・有効期限は未検証で、UUID形式のみを検証します。

各featureのファイルは後続実装用の雛形です。DB接続・モデル実装は#18、画像アップロード
と `python-multipart` は#19、Docker Compose全体構成は#14、pytestの導入・最初のテストは#85、
機能別の不足テスト追加は#39
で対応します。この段階ではPostgreSQLやMemcachedへの接続、認証・決済・AI処理は実装
していません。

#### コメント生成の確認状況と残事項（Issue #29）

- コメント生成テスト8件、分析API関連テスト29件、変更対象のRuff・整形チェックの成功を確認した。
- 架空の答案5ケース（あまりの誤り、繰り上がりの反映漏れ、書き写し間違い、空欄、全問正解）で生成文を確認した。あまり・繰り上がりの2ケースのタイトルと本文は、Issue #29に掲載している。
  - 生成例：https://github.com/ms-engineer-bc26-05/Section9_team-a/issues/29#issuecomment-6247055653
  - 最終確認は各ケース1回であり、すべての出力の正確性を保証するものではない。
  - 保存した検証結果にはモデルIDを含めていないため、その結果だけでは使用モデルを確認できない。
- レビュアーは、原因不明の架空ケースで3回生成し、新しい原因の候補を書かずに説明できることを確認した。
- レビュアーによるデモ用答案の確認では、Stage B全体（単元判定・パターン分析・コメント生成）の所要時間は4回の実行で7〜10秒だった。
- 同確認では、コメント内の計算誤りや、子どもができていた部分への助言も発生した。schemaだけでは防げないため、文面の確認を継続する。
- パターン分析にも誤りが確認されており、コメントのずれに影響する。#28の後続Issueで対応する方針。
- 入力得点と満点が一致し、確認済みの不正解の問題が0問の場合のみ、タイトルを「今回のテストは満点でした」に固定する。不正解の問題がある場合は、生成されたタイトルを使用する。
- 処理時間・料金の継続検証は#30で行う。
