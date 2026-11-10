# のびしろくん フロントエンド

Next.js + TypeScript で作るフロントエンドです。

## 必要なもの

- Node.js 22（`.nvmrc` で `22.23.3` に固定しています）
- npm（Node.js に付属しているものを使います）

Node.js のバージョンをそろえるため、バージョン管理ツール **fnm** を使います。
すでに nvm を使っている人は、fnm に切り替えず nvm のままで大丈夫です。
Mac／Linux 版の nvm は `.nvmrc` を読めますが、Windows の nvm-windows は別の製品で、バージョンの指定が必要です（手順は「2. Node.js 22 に切り替える」を参照）。
バージョン管理ツールを複数入れると PATH が競合することがあるため、どちらか1つにしてください。

## 1. fnm の準備（最初の1回だけ）

使っている環境に合わせて、どちらか一方を行ってください。

### Windows（PowerShell で作業する人）

1. fnm をインストールする

   ```powershell
   winget install Schniz.fnm
   ```

2. PowerShell の設定ファイル（プロファイル）を作って開く

   ```powershell
   if (-not (Test-Path $profile)) { New-Item $profile -Force }
   Invoke-Item $profile
   ```

3. 開いたファイルの末尾に次の1行を追加して保存する

   ```powershell
   fnm env --use-on-cd --shell powershell | Out-String | Invoke-Expression
   ```

4. PowerShell を開き直す

PowerShell を開き直したときに「スクリプトの実行が無効」というエラーが出る場合は、Windows の設定で読み込みが制限されています。チームに相談してください。

### Mac／Linux／WSL（それ以外の人）

WSL（Windows 上の Ubuntu など）で作業している人もこちらです。
次の **A か B のどちらか一方** を行ってください。迷ったら A で大丈夫です。

#### A. インストールスクリプトを使う（Mac／Linux／WSL 共通）

1. fnm をインストールする（`curl` と `unzip` が必要です）

   ```bash
   curl -fsSL https://fnm.vercel.app/install | bash
   ```

   シェルの設定ファイル（`~/.zshrc` や `~/.bashrc` など）に、fnm の設定が自動で追加されます。

2. ターミナルを開き直す

#### B. Homebrew を使う（Mac で Homebrew を使っている人）

1. fnm をインストールする

   ```bash
   brew install fnm
   ```

2. `~/.zshrc` の末尾に次の1行を追加して保存する

   ```bash
   eval "$(fnm env --use-on-cd --shell zsh)"
   ```

3. ターミナルを開き直す

## 2. Node.js 22 に切り替える

`frontend/` に移動してから実行します。

```bash
cd frontend
fnm install   # .nvmrc のバージョン（22.23.3）をインストール
fnm use       # .nvmrc のバージョンに切り替え
node -v       # v22.23.3 と表示されればOK
```

nvm を使っている人は、次のとおりです。

- Mac／Linux の nvm（`.nvmrc` を読めるので、バージョンの指定は不要）

  ```bash
  cd frontend
  nvm install
  nvm use
  ```

- Windows の nvm-windows（`.nvmrc` に書かれたバージョンを指定する）

  ```powershell
  cd frontend
  nvm install 22.23.3
  nvm use 22.23.3
  ```

どちらも、最後に `node -v` で `v22.23.3` と表示されればOKです。

## 3. 起動する

```bash
npm ci        # package-lock.json のとおりに依存パッケージをインストール
npm run dev   # 開発サーバーを起動
```

ブラウザで http://localhost:3000 を開くと、画面が表示されます。
