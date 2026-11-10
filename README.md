# 製薬会社 公式Press Release Monitor（71社）

71社の**会社公式Press Release / Newsroomページそのもの**を巡回し、新しいリリースURLを検出してWeb一覧とRSSを生成します。SEC、Google News、第三者ニュースサイトを一次検知には使いません。

## 無料で動かす方法（GitHub Free）

### 1. GitHubで新しいPublic repositoryを作る
例: `pharma-press-monitor`。GitHub Freeで完全無料運用する場合はPublicにします。

### 2. このZIPの中身をrepositoryのルートへアップロードする
フォルダ構造を崩さず全ファイルを入れ、`main` branchへCommitします。

### 3. GitHub Actionsの書き込み権限を確認
Repository → **Settings → Actions → General → Workflow permissions** で、workflowがrepositoryへ書き込める設定にします。監視履歴を自動commitするために必要です。

### 4. GitHub Pagesを有効化
Repository → **Settings → Pages → Build and deployment → Source = GitHub Actions** を選択します。

### 5. 初回監視を実行
Repository → **Actions → Monitor official press releases → Run workflow**。
初回は現在掲載されている記事URLを「基準値」として保存するため、過去記事を大量に新着扱いしません。

### 6. もう一度 Run workflow を実行して動作確認
71社すべて成功すればActionは緑になります。1社でも取得失敗すると赤になります。失敗を「更新なし」として隠しません。

### 7. Webサイトを見る
Repository → **Settings → Pages** に公開URLが表示されます。サイト上部に `Coverage: 71/71` と取得失敗数が表示されます。

### 8. NetNewsWireへ登録
Pages URLの末尾に `/feed.xml` を付けたものが全社統合RSSです。
例: `https://USERNAME.github.io/pharma-press-monitor/feed.xml`
これをNetNewsWireの **File → New Web Feed** に登録します。

企業別RSSも `feeds/` 以下に生成されます（例: `feeds/biogen.xml`）。

## 自動巡回
`.github/workflows/monitor.yml` は毎時 **07分、27分、47分**（約20分間隔）に起動します。時刻を00分ちょうどからずらしてGitHub Actionsの混雑リスクを下げています。

## 監視方式
1. まず通常HTTPで公式Newsroomを取得。
2. 内容が薄い/JavaScript依存と判断した場合はPlaywright + Chromiumで実ブラウザ表示。
3. 公式ドメイン内のPress/News/Release/記事らしいURLを抽出。
4. 前回保存したURL集合との差分から新規URLを判定。
5. 新規だけ `docs/feed.xml` とWeb一覧へ追加。
6. 取得失敗、または候補記事数が前回から異常に急減した場合はFAIL。

## 重要な運用上の注意
GitHubの仕様上、Public repositoryで60日間repository activityがない場合、scheduled workflowが自動無効化されることがあります。このmonitorは通常、状態更新をcommitするためactivityが発生しますが、長期間まったくcommitが発生しない場合はActions画面を確認してください。

またGitHub scheduled workflowは厳密なリアルタイム保証ではなく、混雑時に遅延する可能性があります。本システムは「無料で継続監視」を目的に約20分間隔としています。

## Biogen
`companies.csv` にBiogen公式Newsroomを登録済みです。SECではなく、この公式ページを直接巡回します。

## ファイル
- `companies.csv` — 71社と公式Newsroom URL
- `run.py` — 巡回・差分判定・RSS/Web生成
- `.github/workflows/monitor.yml` — 自動巡回
- 監視ワークフロー内で、状態保存後にPagesへ公開します。
- `docs/feed.xml` — 実行後に生成される全社RSS
- `data/status.json` — 71社の取得成否
- `data/events.json` — 検出した新規リリース履歴

## 設置時の修正
監視とPages公開を同じワークフローに統合。HTTPエラー・記事候補ゼロ件はFAIL。初回取得は基準値のみ保存し、RSSはその後に検出した新規URLを配信します。記事候補は汎用抽出であり、全社専用パーサーではありません。サイト構成変更時には確認と調整が必要です。
