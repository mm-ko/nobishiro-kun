# のびしろくん

> **テストを撮ると、子どもの伸びしろが見える。**

先生が採点した小学生のテストを AI で分析し、保護者に「子どものつまずき」と「家庭でできるサポートのヒント」を届ける Web アプリです。
AI が採点し直すサービスではなく、忙しい保護者が子どもの学習に関わるきっかけをつくる、学習サポートのためのアプリです。

Team-A（Section9）の卒業制作です。

## 目次

- [アプリの概要](#アプリの概要)
- [主な機能と使い方](#主な機能と使い方)
- [使用技術](#使用技術)
- [課題の要件との対応](#課題の要件との対応)
- [実装の状況](#実装の状況)
- [ドキュメント](#ドキュメント)
- [チーム](#チーム)
- [Docker Composeによる開発環境](#docker-composeによる開発環境)（起動手順）

## アプリの概要

| 項目 | 内容 |
| --- | --- |
| 対象 | 小学3年生の算数の単元テスト（先生が採点済みで、子どもが解き直す前のもの） |
| 対応単元（MVP） | わり算（あまりのあるわり算を含む）、たし算とひき算の筆算。今後、精度を確かめながら順次広げる |
| 利用者 | 共働きなどで忙しい保護者 |
| 料金（想定） | 月2回まで無料、3回目以降は月額300円（無料分を含めて月10回まで）。卒業制作で検討するための仮の料金 |

### 大事にしている設計

- **AI の読み違いを、分析に直結させない**：AI がテストから読み取った「答え」と「正解・不正解」を、保護者が確認・修正してから、確認済みのデータだけで間違え方を分析します（読み取り → 保護者の確認・修正 → 分析）。
- **根拠が足りない原因は断定しない**：「理解不足」「うっかり」などと決めつけず、「この答案だけでは分からない」ことを伝えたうえで、一緒に確認する方法を提案します。
- **テスト画像を保存しない**：画像はメモリの上だけで扱い、ディスク・DB には書きません。外部の AI も、データを保持しない接続先（ZDR）だけに送ります。

## 主な機能と使い方

1. **テストを撮る**：採点済みのテストを撮影してアップロード（表と裏の2枚まで）。名前などは、必要に応じて保護者が切り取れます。
2. **読み取り内容を確認**：AI が読み取った答えと正解・不正解を、保護者がタップで確認し、違うところだけ直します。得点と満点も入力します。
3. **つまずきとヒントを見る**：間違え方の分析と、家庭でのサポートのヒント（寄り添いコメント）を確認します。
4. **ホームで振り返る**：学習履歴と、得点率の平均が低い順の苦手単元ランキングを確認できます。

対象外の単元や、単元を特定できないテストは、その旨を表示して分析を終えます（記録・利用回数に含めません）。

## 使用技術

| 分類 | 技術 |
| --- | --- |
| Frontend | Next.js、TypeScript |
| Backend | FastAPI（Python）、SQLModel |
| DB | PostgreSQL |
| キャッシュ | Memcached（短時間の連続実行の制限） |
| 認証 | Firebase Authentication（メールアドレス＋パスワード） |
| AI | Gemma 4 26B A4B（OpenRouter 経由、ZDR 対応の接続先のみ） |
| 決済 | Stripe（テストモード） |
| 開発環境 | Docker Compose（Backend・PostgreSQL・Memcached） |
| テスト | pytest（Backend）、Vitest＋React Testing Library（Frontend） |

選定の理由は [技術選定](docs/技術選定.md) を参照してください。

## 課題の要件との対応

| 要件 | 対応 |
| --- | --- |
| Docker | Backend・PostgreSQL・Memcached を Docker Compose で起動（下の起動手順） |
| キャッシュサーバー | Memcached で、読み取り・分析の短時間の連続実行を1ユーザー1分3回までに制限。正式な月の利用回数は DB で数える |
| 決済 | Stripe Checkout で月額プランを契約。Webhook の署名を検証し、契約状態を DB に保存 |
| LLM | Gemma 4 26B A4B を OpenRouter 経由で利用。読み取りと分析を分け、間に保護者の確認を挟む |
| 単体テスト | Backend は pytest、Frontend は Vitest。実行方法は [テスト設計書](docs/テスト設計書.md) |
| ログの出し分け・セキュリティ | [ログ設計](docs/ログ設計.md)、[セキュリティ設計](docs/セキュリティ設計.md) |
| デプロイ（ADVANCED） | **見送り**。下記の理由を参照 |

### デプロイ（AWS）を見送った理由

デプロイは任意（ADVANCED）の要件のため、必須要件と、アプリの核となる「読み取り → 保護者の確認 → 分析」の完成と安定を優先しました。
公開環境で動かすには、Stripe の Webhook を受ける公開 URL、Firebase の承認済みドメインの追加、本番用の秘密情報の管理、ログの設定などの追加作業が必要で、実装期間（実質約3週間）の中では、品質を保ったまま対応しきれないと判断しました（Issue #16）。

## 実装の状況

2026/10/25 時点。提出前に更新します。

| 機能 | 状況 |
| --- | --- |
| 画像のアップロード・トリミング | 実装済み |
| 読み取り（Stage A）・保護者の確認・分析（Stage B）・寄り添いコメント | 実装済み（本物の AI で画面から通ることを確認） |
| 学習履歴・苦手単元ランキング | 実装済み |
| 認証 | Backend のトークン検証は実装済み。Frontend のログインを本物につなぐ作業は進行中（#99） |
| 決済（Stripe） | Backend の Checkout・Webhook・有料判定とFrontendの決済画面を接続済み（#25、#38）。成功画面はWebhook反映後の有効な契約を確認して表示 |
| 短時間の連続実行の制限（Memcached） | 実装済み（#24、レビュー中） |
| 月の利用回数・無料枠・月10回の上限 | 作業中（#23）。画面の表示は #37 |

### Stripe決済の画面デモ

1. [Backend READMEの「月額プランの決済」](backend/README.md#月額プランの決済)に従い、StripeテストモードとWebhook転送を準備する。
2. アプリへログインし、無料枠を使い切って有料案内を開く（画面確認だけなら`/plan`へ直接移動してもよい）。
3. ［月額300円で利用する］を押す。新しいタブでStripe Checkoutが開くので、Backend READMEに記載したテストカードを使用する。
4. 支払い後は`/plan/result?status=success`へ戻り、契約状態が反映されるまで待つ。成功表示後に［ホームへ戻る］を押すと、利用状況が更新され、月10回まで分析できる。
5. Stripe Checkoutで戻る操作を行うと`/plan/result?status=cancel`にキャンセル表示が出る。カード拒否は通常Stripe Checkout内にエラー表示される。

失敗状態の画面だけを確認する場合は`/plan/result?status=failure`を開く。不正な`status`は`/plan`へ戻る。カード番号・秘密情報はアプリの画面やログへ記録しない。

AI の読み取りには誤りがあるため（例：先生の × を ○ と読む）、保護者の確認・修正を必須にしています。計測の結果は [OpenRouter 再検証・計測結果](docs/OpenRouter再検証・計測結果.md) を参照してください。

## ドキュメント

| ドキュメント | 内容 |
| --- | --- |
| [PRD](docs/PRD_Ver.1.37.md) | 企画・MVP の範囲・決定事項 |
| [機能要件](docs/機能要件_Ver.1.11.md) | 機能と画面の一覧 |
| [画面設計書](docs/画面設計書_Ver.1.06.md) | 画面遷移図・ワイヤーフレーム |
| [API設計](docs/API設計.md) | API の一覧と、リクエスト・レスポンスの形 |
| [DB設計](docs/DB設計.md) | ER 図・テーブル定義 |
| [アーキテクチャ設計](docs/アーキテクチャ設計.md) | 全体の構成 |
| [技術選定](docs/技術選定.md) | 技術の選定理由・処理の流れ |
| [セキュリティ設計](docs/セキュリティ設計.md)・[ログ設計](docs/ログ設計.md) | 対策と、ログに出す・出さない情報 |
| [テスト設計書](docs/テスト設計書.md) | テストの方針と実行方法 |
| [運用・性能・可用性設計](docs/運用・性能・可用性設計.md) | 簡易版 |
| [OpenRouter 再検証・計測結果](docs/OpenRouter再検証・計測結果.md) | 処理時間・AI の費用の計測 |
| [GitHub運用書](docs/GitHub運用書.md) | ブランチ・Issue・PR の進め方 |
| [Backend の README](backend/README.md) | Backend のテスト・Ruff・決済のデモ手順など |

## チーム

| 名前 | 担当 |
| --- | --- |
| もも | Frontend：FE 進行・デザイン |
| みかこ | Frontend：画面設計・撮影〜確認画面・API 接続 |
| さとう | Frontend：画面設計・認証画面・結果画面 |
| みなみ | Backend：BE 進行・API/DB 設計・AI 分析 |
| ようこ | Backend：企画・全体統括・AI 読み取り |


## Docker Composeによる開発環境

Backend・PostgreSQL・MemcachedをDocker Composeで起動します。
FrontendはDockerに含めず、各自のPC上で別途起動します。

### 前提条件

- Docker Desktopがインストールされ、起動していること
- リポジトリを取得済みであること
- コマンドはリポジトリルートで実行すること

本手順のコマンド例は、Windowsのコマンドプロンプト（cmd）を使用します。
Mac・Linux・WSL（bash・zsh）で書き方が変わるコマンドは、その箇所に併記します。

### サービス構成

| サービス  | 内容                                            | 接続先                        |
| --------- | ----------------------------------------------- | ----------------------------- |
| backend   | 既存の`backend/Dockerfile`からビルドするFastAPI | PCから`http://localhost:8000` |
| db        | PostgreSQL：`postgres:18.6-bookworm`            | Backendから`db:5432`          |
| memcached | Memcached：`memcached:1.6.45`                   | Backendから`memcached:11211`  |

PostgreSQLとMemcachedのポートはPC側へ公開しません。
PostgreSQLのデータは名前付きvolumeに保存します。

### 1. 環境変数の準備

以下のサンプルをコピーして、各自の環境ファイルを作成します。
既存のファイルがある場合は上書きせず、必要な項目を確認してください。

| コピー元                | 作成先                | 用途                         |
| ----------------------- | --------------------- | ---------------------------- |
| `.env.example`          | `.env`                | PostgreSQLコンテナの初期設定 |
| `backend/.env.example`  | `backend/.env`        | Backendアプリの設定          |
| `frontend/.env.example` | `frontend/.env.local` | Frontendアプリの設定         |

`.env`には実値が含まれるため、Gitへコミットしないでください。

#### ルートの`.env`

次の3項目を各自で設定します。

| 変数                | 内容                 |
| ------------------- | -------------------- |
| `POSTGRES_DB`       | 開発用DB名           |
| `POSTGRES_USER`     | 開発用DBのユーザー名 |
| `POSTGRES_PASSWORD` | 開発用DBのパスワード |

これらは、空のデータ領域にDBを初期作成するときの設定です。
初期作成後に`.env`を書き換えるだけでは、既存DBの名前・ユーザー・パスワードは変更されません。

#### Backendの`.env`

Memcachedの接続先は以下とします。

```dotenv
MEMCACHED_HOST=memcached
MEMCACHED_PORT=11211
```

この2項目はComposeの`environment`でも指定しており、Compose側の値が優先されます。

Frontendを`http://localhost:3000`で起動する場合は、以下を設定します。
別のOriginで起動する場合は、その値に合わせてください。

```dotenv
FRONTEND_ORIGIN=http://localhost:3000
```

`DATABASE_URL`は、次の形式で各自が設定します。実値は共有・コミットしません。

```text
postgresql+psycopg://<user>:<password>@db:5432/<database>
```

`<user>`・`<password>`・`<database>`には、ルートの`.env`に設定した値を書き写します。

| ルートの`.env`      | `DATABASE_URL`の中の場所 |
| ------------------- | ------------------------ |
| `POSTGRES_USER`     | `<user>`                 |
| `POSTGRES_PASSWORD` | `<password>`             |
| `POSTGRES_DB`       | `<database>`             |

たとえば、ルートの`.env`が次の場合は、

```dotenv
POSTGRES_DB=nobishiro_dev
POSTGRES_USER=nobishiro
POSTGRES_PASSWORD=example-password
```

`backend/.env`には次のように設定します（`<`・`>`は残しません）。

```dotenv
DATABASE_URL=postgresql+psycopg://nobishiro:example-password@db:5432/nobishiro_dev
```

この値は説明用の例です。そのまま使わず、各自の`.env`の値に置き換えてください。

URLのユーザー名・パスワードに予約文字が含まれる場合は、URLエンコードしてください。
Composeのサービス名は`db`です。`localhost`や`postgres`は使用しません。
設定値はComposeの`env_file`から環境変数として渡され、Backendの`Settings`が読み込みます。
`DATABASE_URL`が空でもBackendは起動できますが、DB接続確認APIは503を返します。

OpenRouter・Stripeの実値は、起動・接続確認だけであれば使用しません。

#### FrontendのFirebase設定

本物のFirebaseログインを使うには、各自のPCに`frontend/.env.local`が必要です。
リポジトリルートで、既存ファイルを上書きしないよう確認してから作成します。

Windows（コマンドプロンプト）：

```cmd
copy frontend\.env.example frontend\.env.local
```

Mac・Linux・WSL：

```bash
cp frontend/.env.example frontend/.env.local
```

`frontend/.env.local`には、`NEXT_PUBLIC_API_BASE_URL`と
`NEXT_PUBLIC_FIREBASE_`で始まる項目を設定します。
ローカルのBackendへ接続する場合、`NEXT_PUBLIC_API_BASE_URL`は
`http://localhost:8000`です。
Firebaseの各値は、[Firebase Console](https://console.firebase.google.com/)の
「プロジェクトの設定」→「全般」→「マイアプリ」→対象のWebアプリ→
「SDK の設定と構成」の`Config`で確認できます。
詳しくは[Firebase公式のWebアプリ設定手順](https://firebase.google.com/docs/web/setup)を参照してください。

Firebase Consoleを参照できない場合は、Firebase管理担当者へ安全な方法で確認してください。
実際の設定値をREADME、Issue、PR、チャット、生成AIへ貼り付けないでください。
`frontend/.env.local`もGitへコミットしません。

Frontendだけでなく、Backendにも次の「Firebaseのサービスアカウントキー」の設定が必要です。
また、この設定を行うタイミングで、後述の「開発用の固定ユーザー（Issue #110）」の
OFF手順も実施してください。

#### Firebaseのサービスアカウントキー

Composeは、`backend/secrets/`をBackendコンテナの`/app/secrets`へ読み取り専用でマウントします。
鍵はDockerイメージに含めず、各自が配置したファイルをコンテナから参照します。

Firebaseを使う場合は、鍵を`backend/secrets/firebase-service-account.json`に配置し、
`backend/.env`に以下を設定します。

```dotenv
FIREBASE_CREDENTIALS_PATH=secrets/firebase-service-account.json
```

`backend/secrets/`はGitの対象外です。鍵をコミットしないでください。
鍵を配置していなくてもBackendの起動確認はできますが、本物のFirebaseログインとの結合確認はできません。
Firebase Admin SDKの初期化処理はBackend側で実装済みです。

#### 開発用の固定ユーザー（Issue #110）

Frontendのログインがモックだった期間にAPIを試すための設定です。
オンにすると、トークンなしの呼び出しを、決まった1人のユーザー（`firebase_uid`が`dev-fixed-user`）として扱います。
誰が呼んでも同じ1人として扱われるため、**本番ではオンにしないでください。**

`backend/.env`に以下を設定し、Backendのコンテナを作り直します。

```dotenv
APP_ENV=development
DEV_FIXED_USER_ENABLED=true
```

```cmd
docker compose up -d backend
```

`docker compose restart`では`.env`の変更が反映されません。

- `APP_ENV`の初期値は`production`です。`APP_ENV=development`以外で`DEV_FIXED_USER_ENABLED=true`にすると、Backendは起動しません。
- トークンを付けた呼び出しは、今までどおり検証します。無効なトークンは、固定ユーザーに切り替えず401を返します。
- 固定ユーザーの`users`の行は、最初の呼び出しで自動的に追加されます。事前に、下の「共通テーブルの初回作成と単元マスタ投入」でテーブルを作成しておいてください。
- オンのあいだは、起動時のログに「開発用の固定ユーザーが有効です」と表示されます。

```cmd
docker compose logs backend
```

本物のFirebaseログインを使う#99以降の結合確認では、以下のOFF手順を実施してから動作確認します。

OFFにするとき（本物のFirebaseログイン #99 の接続後）は、次の順に確認します。

1. `backend/.env`から`DEV_FIXED_USER_ENABLED`を消す（または`false`にする）
2. `docker compose up -d backend`でコンテナを作り直す
3. 起動時のログに「開発用の固定ユーザーが有効です」が出ていないことを確かめる
4. トークンなしで`POST /v1/analyses`を呼び、401になることを確かめる
5. 本物のFirebaseログインから、Stage A → 確認 → Stage B まで通ることを確かめる（#41）

OFFにしても、固定ユーザーの`users`の行はDBに残ります。消す必要がある場合は、Backend担当に相談してください。

### 2. Composeの設定検証

```cmd
docker compose config --quiet
```

何も表示されず正常終了すれば、設定検証は成功です。
エラーが出た場合は、環境ファイルの配置や必須項目を確認してください。

`--quiet`を付け、展開された設定値の一覧を出力しないようにします。

#### イメージ取得に失敗した場合の確認方法

`docker compose config --quiet`では、イメージタグの存在までは確認しません。
指定したタグの存在は、以下で確認できます。

```cmd
docker manifest inspect postgres:18.6-bookworm
docker manifest inspect memcached:1.6.45
```

エラーなくマニフェストのJSONが表示されれば、指定したタグが存在し、そのメタデータを取得できることを確認できます。イメージ本体の取得・起動確認は、`docker compose up --build -d`で行います。

### 3. 起動

```cmd
docker compose up --build -d
```

初回はイメージの取得とBackendのビルドに時間がかかります。

Backendのコードや`requirements.txt`を変更した場合は、同じコマンドでビルドし直します。
ソースコードはイメージにコピーしているため、変更は自動では反映されません。

### 4. 起動確認

```cmd
docker compose ps
```

次の状態になっていることを確認します。

| サービス  | 期待する状態 |
| --------- | ------------ |
| backend   | Up           |
| db        | Up・healthy  |
| memcached | Up           |

ブラウザで以下を開き、Swagger UIが表示されることを確認します。

http://localhost:8000/docs

### 5. BackendからMemcachedへの接続確認

Backendコンテナで、次のコマンドを1行のまま実行します（cmd・bash共通）。

```cmd
docker compose exec backend python -c "import os; from pymemcache.client.base import Client; c = Client((os.environ['MEMCACHED_HOST'], int(os.environ['MEMCACHED_PORT'])), connect_timeout=5, timeout=5); c.set('issue14:connection-check', b'ok', expire=60, noreply=False); print(c.get('issue14:connection-check')); c.close()"
```

`b'ok'`と表示されれば、保存・取得に成功しています。
確認用データは60秒で期限切れになります。

### 6. BackendからPostgreSQLへの接続確認

ブラウザまたはSwagger UIから`GET http://localhost:8000/v1/health`を実行します。
認証は不要です。Frontendからも同じAPIを呼び出せます。

BackendはSQLModelのSessionを使い、PostgreSQLで`SELECT 1`を実行します。

| 結果 | HTTPステータス | JSON |
| --- | --- | --- |
| 接続成功 | 200 | `{"status":"ok","database":"ok"}` |
| 接続不可・設定未指定・URL形式不正 | 503 | `{"status":"error","database":"unavailable"}` |

このAPIは接続のみを確認します。テーブル・初期データの存在確認は行いません。
接続先や例外の詳細は応答に含めません。

#### 共通テーブルの初回作成と単元マスタ投入

以下は、自分のローカル開発DBに対して人が実行します。
既存DBに今回のテーブルがなければ、DBを初期化せずに追加できます。
Alembic管理外の同名テーブルがある場合は、初期化や`stamp`をせず担当者へ相談してください。

```cmd
docker compose exec backend python -m alembic upgrade head
docker compose exec backend python -m app.db.seed
```

`users`・`units`・`analysis_usages`・`analysis_records`を作成します。
`analysis_usages`は分析記録の外部キー参照先であり、利用回数の加算処理は別Issueです。
単元は`division`（わり算）と`addition_subtraction_written`（たし算とひき算の筆算）の2件です。
わり算には、あまりのあるわり算を含みます。

単元投入は同じ`code`がある場合は追加せず、既存行を更新しません。
不足している単元だけ追加するため、再投入にも同じコマンドを使用します。
既存行の名前が指定と異なる場合は自動修正せず、担当者へ相談してください。

通常の停止・再起動ではvolumeにデータが残るため、これらのコマンドは毎回実行しません。
Backend起動時にマイグレーションや単元投入を自動実行することはありません。

適用済みリビジョンと単元データを確認します（cmd・bash共通）。

```cmd
docker compose exec backend python -m alembic current
docker compose exec backend python -c "from sqlmodel import Session, select; from app.db.models import Unit; from app.db.session import get_engine; s = Session(get_engine()); print([(u.code, u.name) for u in s.exec(select(Unit).order_by(Unit.code)).all()]); s.close()"
```

`0001_common_tables (head)`と、上記2単元が表示されることを確認してください。

#### 共通モデルの追加・変更

1. `backend/app/db/models/`のモデルを変更し、追加モデルは`__init__.py`で読み込みます。
2. DB設計書も合わせて更新します。
3. Backendを再ビルドし、開発DBを参照してマイグレーション案を生成します。

```cmd
docker compose up --build -d
docker compose exec backend python -m alembic revision --autogenerate -m "describe_schema_change"
docker compose cp backend:/app/alembic/versions/. backend/alembic/versions/
```

コードはvolume共有していないため、生成したファイルをホストへコピーしてGitで管理します。
生成結果は必ずレビューしてください。自動生成だけでは全変更の正しさを保証しません。
削除・データ損失を伴う変更は、実行前に担当者と相談してください。
共有・適用済みのマイグレーションは書き換えず、新しいリビジョンを追加します。
レビュー後、再ビルドして、人が対象DBへ適用します。

```cmd
docker compose up --build -d
docker compose exec backend python -m alembic upgrade head
```

### 7. PostgreSQLのデータ保持確認

環境を初めて構築したときに、volumeでデータが保持されることを確認する手順です。
通常の開発では実行不要です。

<details>
<summary>データ保持確認と、確認用テーブルの後片付けの手順</summary>

開発DBに確認用テーブルを作成します。
アプリ用テーブルやマイグレーションは使用しません。

データ保持の確認後、確認用テーブル`issue14_persistence_check`は手動で削除してください。接続先がローカルの開発DBであることを確認し、アプリ用テーブルやvolumeは削除しないでください。

DBの操作画面を開きます。コマンドは、使用するシェルに合わせてください。
bash・zshでcmd用のコマンドを実行すると、`$POSTGRES_USER`がPC側で空に展開され、`role "root" does not exist`で失敗します。

Windowsのコマンドプロンプト（cmd）：

```cmd
docker compose exec db sh -c "psql -U \"$POSTGRES_USER\" -d \"$POSTGRES_DB\""
```

Mac・Linux・WSL（bash・zsh）：

```bash
docker compose exec db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
```

DBの操作画面で、以下を実行します。

```sql
CREATE TABLE issue14_persistence_check (
    id integer PRIMARY KEY,
    note text NOT NULL
);

INSERT INTO issue14_persistence_check (id, note)
VALUES (1, 'volume-check');

SELECT * FROM issue14_persistence_check;
```

`1 | volume-check`が表示されることを確認します。

再確認時にテーブルが既に存在する場合は、作成・挿入を繰り返さず、
`SELECT`で既存の確認用データを確認してください。

次でDBの操作画面を終了します。

```text
\q
```

コンテナを停止し、再作成します。`-v`は付けません。

```cmd
docker compose down
docker compose up -d
docker compose ps
```

`db`が`healthy`になったら、再びDBの操作画面を開きます。

Windowsのコマンドプロンプト（cmd）：

```cmd
docker compose exec db sh -c "psql -U \"$POSTGRES_USER\" -d \"$POSTGRES_DB\""
```

Mac・Linux・WSL（bash・zsh）：

```bash
docker compose exec db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
```

```sql
SELECT * FROM issue14_persistence_check;
```

再び`1 | volume-check`が表示されれば、
コンテナの停止・再作成後もデータが保持されています。

```text
\q
```

#### 確認用テーブルの後片付け

データ保持の確認後、各自のローカル開発DBから確認用テーブルを削除します。

リポジトリルートで実行し、DBの操作画面を開きます。

Windowsのコマンドプロンプト（cmd）：

```cmd
docker compose exec db sh -c "psql -U \"$POSTGRES_USER\" -d \"$POSTGRES_DB\""
```

Mac・Linux・WSL（bash・zsh）：

```bash
docker compose exec db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
```

ここからはpsqlの操作画面（`DB名=#`）で入力します。まず接続先を確認します。

```text
\conninfo
```

対象が自分のローカル開発DBであることを確認し、確認用テーブルだけを削除します。

```sql
DROP TABLE IF EXISTS public.issue14_persistence_check;
```

削除を確認します。

```sql
SELECT to_regclass('public.issue14_persistence_check') IS NULL AS removed;
```

`removed`が`t`なら削除完了です。次で終了します。

```text
\q
```

アプリ用テーブルやvolumeは削除しません。
この後片付けに`docker compose down -v`は使用しないでください。

</details>

### 8. 通常の停止・再起動

停止する場合：

```cmd
docker compose down
```

再び起動する場合：

```cmd
docker compose up -d
```

通常の`down`では、PostgreSQLの名前付きvolumeは削除されません。

### 9. 開発DBを初期化する場合

> 以下はPostgreSQLのvolumeを削除する操作です。
> アプリのデータや確認用テーブルを含む、開発DBのデータが失われます。
> 通常の停止には使用しないでください。

対象の開発DBを削除してよいことを確認したうえで、人が実行します。

```cmd
docker compose down -v
docker compose up -d
```

再起動時は、ルートの`.env`に設定された値でDBが初期作成されます。
アプリ用テーブルと単元マスタは、このREADMEの「共通テーブルの初回作成と単元マスタ投入」の
2コマンドで再作成・再投入します。通常のセットアップやスキーマ変更のために
volumeを削除する必要はありません。

### チームでの再現確認

- [ ] Backend担当2人が、この手順で3サービスを起動できる
- [ ] Swagger UIが表示される
- [ ] BackendからPostgreSQLへ接続できる
- [ ] BackendからMemcachedへ保存・取得できる
- [ ] 通常の停止・再作成後もPostgreSQLのデータが保持される
- [ ] 実値入りの環境ファイルがGit管理されていない
- [ ] Frontend担当へ起動方法とBackendの接続先を共有した

## フロントエンドのテスト

フロントエンドのテスト・静的解析・フォーマット確認は、`frontend` ディレクトリで実行します。

```bash
cd frontend
npm test
npm run lint
npm run format:check
```

- `npm test`：Vitestによる単体テストを実行します。
- `npm run lint`：ESLintによるコードチェックを実行します。
- `npm run format:check`：Prettierによるフォーマット確認を実行します。
