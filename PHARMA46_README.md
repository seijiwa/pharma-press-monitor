# Pharma46 Monitor v2.2 — 46社公式開示監査（段階的導入・配信安全版）

## 現時点のステータス

- **コード・固定46社台帳・テスト・新GitHub Actions・メール実装:** 作成済み。
- **ローカル自動テスト:** 26件合格（既存模擬23件＋段階移行・配信安全3件）（実ネットワークを使わない模擬サイトテスト）。
- **46社本番実サイトでの期間網羅QA:** **未検証。** 模擬テストの成功を本番監査成功と誤認しない。
- **GitHubリポジトリへの適用:** **未反映。** 接続されているGitHubアプリは Contents API への書込を403で拒否した。
- **Gmailでの送信:** **未設定・未送信。** 秘密情報の設定と本番実行が必要。

## 根本的な変更点

旧系は ChatGPT定時4段階(A/B/C/D) + Library間ファイル共有 + 別系統のGitHub 71社監視で構成され、どこか1段が失敗すると監査が成立しませんでした。新系では**GitHub Actionsが唯一の収集・QA・履歴・メール処理の実行環境**です。GitHubの保存結果を後からChatGPTが読み、企業別分析や確認漏れの補完に使います。

- 日本時間02:00を意図した単一の日次ジョブ（GitHubの起動遅延あり）。旧4分割ジョブ・旧71社20分間隔ジョブとは異なります。
- A/B/C各企業の結果を同じ実行プロセスで収集し、1回で固定46社を順序検証。工程DのLibrary欠落は発生しません。
- 現在の実HTTP取得 + Playwright（Ubuntu **24.04固定**）でニュース一覧を試行。`web.open`のクロールキャッシュは使いません。
- 出典URL・HTTP応答・取得日時(JST)・`Date`/`Age`ヘッダー・HTMLのSHA-256・圧縮スナップショットを保存します。
- 公式日付付き一覧を**比較開始以前までページング**できなければ `未確認`。見つからない＝「なし」ではありません。
- 対象記事の公式原文URLを直接取得し、原文の本文・日付も照合します。原文だけ確認できた発表は、会社の一覧QAとは独立して記録します。
- 旧来の `previous_success_jst=null` は勝手に埋めず、初回は実行開始から24時間前の **暫定比較開始** とします。厳格QA成功時だけ成功履歴を更新します。
- 新規と既報のURL台帳を永続化。初回に確認した発表は「初回観測・真の新規未判定」として扱います。
- GmailのSentフォルダーをIMAPで照合し、同日レポートの重複送信を防止。IMAPが不通なら**送信しません**。送信に成功したときだけIDを記録します。
- **未確認は赤信号です。** 1社でも未確認ならQAの最終工程は失敗としてGitHub Actionsを赤表示にしますが、取得済み監査ファイルと暫定メールは保持・送信します。

## ファイル構成

```text
.github/workflows/pharma46.yml   GitHub Actions日次ワークフロー（独立ファイル。旧71社用monitor.ymlは残す）
pharma46/sources.json             固定46社・候補公式URL（到達・網羅は未検証）
pharma46/extract.py             日付付き一覧/原文/ページリンク抽出
pharma46/fetch.py               requests/Chromium、HTTP証拠・キャッシュメタ情報
pharma46/engine.py              46社収集・全ページQA・履歴・46社本文
pharma46/delivery.py            Gmail SMTP+IMAP重複防止
pharma46/cli.py                 監視の単一エントリポイント
requirements-pharma46.txt                固定依存関係
tests_pharma46/                 模擬HTMLの自動QAテスト (計26件)
install_into_repo.sh            既存リポジトリに新コードをコピー（ユーザー操作）
```

旧71社の `run.py`, `validate.py`, `companies.csv`, `docs/` および `.github/workflows/monitor.yml` は新ワークフローから独立して動作するよう残します。過去のデータは監査証跡のため自動削除せず、旧 GitHub Pages の71社RSSは旧monitor.ymlで別途更新されます（実収集の成功は要検証）。過去コードの削除は別途判断してください。

## GitHubへの適用（手元のPC / GitHub Desktop等）

1. 本ZIPを解凍し、**既存の** `seijiwa/pharma-press-monitor` をローカルにクローンします。リポジトリに移動して `git switch -c pharma46-v2.2-staged` を先に実行し、移行専用ブランチを作成します。
2. 以下を実行します（既存71社の監視ファイルを消さず、独立した新コードをコピーします）。

```bash
cd /path/to/pharma-monitor-rebuild
bash install_into_repo.sh /path/to/pharma-press-monitor
```

3. `cd /path/to/pharma-press-monitor` として `git diff --stat` / `git diff -- .github/workflows/pharma46.yml` を確認します。
4. 移行専用ブランチ上で、`git add .github/workflows/pharma46.yml .github/workflows/monitor.yml pharma46 requirements-pharma46.txt tests_pharma46 .gitignore PHARMA46_README.md` → `git commit -m 'Staged Pharma46 v2.2 rebuild'` → `git push -u origin pharma46-v2.2-staged` でアップロードします。GitHubで**PRを確認してから**mainへマージしてください。
5. mainへマージ後、GitHubのActions画面で `Pharma46 - dated official news audit (v2.2 staged cutover)` → `Run workflow` → **send_email=false** で初回試験します。
6. Actionsのアーティファクト `pharma46-evidence-...` と `data/pharma_monitor_YYYY-MM-DD_audit.json` を確認します。`period_verified<46` なら赤表示は仕様通りです。

### GitHubメールの事前設定

GitHub → repository → Settings → Secrets and variables → Actions に以下を設定してください。

|種類|名前|値|
|---|---|---|
|Repository secret|`PHARMA_MAIL_USER`|Gmail送信元アドレス|
|Repository secret|`PHARMA_MAIL_APP_PASSWORD`|Gmailアプリパスワード（通常のログインパスワードは入れない）|
|Repository variable|`PHARMA_REPORT_TO`|`(your report recipient; set in repository variables)`|

Googleのアカウント設定・組織ポリシーによってはアプリパスワードが使えません。その場合は別の送信方式への置換が必要です。パスワードをChatGPTに貼り付けないでください。

**v2.2では、新コードをGitHubへマージしただけでは定時メールは送信されません。** 送信テストはActionsの手動実行で明示的に `send_email=true` と選んだ場合だけ可能です。IMAPで同一ID送信済み照合をしますが、旧ChatGPT方式のメールはID形式が異なり重複を防げないため、旧自動タスクを同時稼働させたまま本番配信テストをしないでください。

本番サイト46社の実査・QA・メール送信を確認し、旧ChatGPT自動タスクを停止した後、Repository variable `PHARMA_ENABLE_DELIVERY=true` を設定してください。これで初めて**定時**メール配信を有効化します。未設定またはfalseなら定時実行は収集と保存だけです。GitHubのスケジュールは開始時刻の厳密な保証がないため、05:30必着を保証するものではありません。

## 追加で必要な実地検証（**まだ未完了**）

候補URLは過去台帳由来であり、全46社の現行公式日付付き記事一覧として本番稼働確認したものではありません。まず本番ジョブの初回実行後、以下を必ず実施してください。

1. 46社別の `official_listing_url` が正しいサイトか、企業と証拠URLのドメインが一致するか。
2. `listing_page_urls_checked` に比較開始より古い記事までの**全ページ**が揃っているか。JavaScript「Load more」は十分に検証できていないため、未確認扱いになります。
3. CAPR、JAZZ、LLYの旧Webキャッシュ問題が、新HTTP・代替公式URL・既知公開日アンカーとの比較で改善されるか。
4. 6990 HK が Sichuan Kelun-Biotech であり、Antengeneではないことを再確認。
5. PDFのみ・モーダルのみ・日付を構造化しない公式サイトは個別アダプターが必要。該当企業は**現状では「未確認」**となります。
6. GitHub Actionsの実運用ログでChromiumの導入、46社の直接取得、3バッチ JSON、統合JSON、メール送信IDを確認する。

**重要:** 静的QAテスト26件合格は、公式46社の実データを収集できた証明ではありません。これを監視完成や「なし46社」と報告しないでください。

## 開発テスト

```bash
python -m pip install -r requirements-pharma46.txt pytest
python -m pytest tests_pharma46 -q
# Playwrightの本番ブラウザー確認
python -m playwright install chromium
# 実サイトの監査を実施（メールなし）
python -m pharma46.cli
```

## 判定規則

- `あり`: 日付付き公式一覧が対象範囲を網羅し、該当する新着の**全記事**で公式原文・公開日・本文を検証できた場合のみ。
- `なし`: 同じ一覧が対象範囲を網羅し、新着候補が0件の場合のみ。
- `未確認`: 収集失敗、JSのみ、キャッシュ疑い、ページング未到達、原文未確認、比較開始未到達など。
- `STALE_CACHE`: HTTP `Age`が48時間以上、HTTP `Date`が2日以上古いなど、明確な証拠がある場合。
- `STALE_CACHE_SUSPECTED_*`: 独立した候補公式一覧・過去の一次公開日アンカーより古い一覧しか得られない場合。実サイトの404とは別区分。
- 会社の `未確認` とは独立して `primary_releases[]` に、確認できた原文を残します。

## 制限

- HTMLの日付抽出は汎用パーサーです。ドメイン別CSS・API・RSS・HKEX・韓国DART/KRXの専用実装はまだありません。候補リストは「本人確認済み公式ソースの候補」であり、**取得成功も期間網羅も未検証**です。
- キャッシュ疑いの完全検知はできません。`Date`/`Age`が正常に見える古いHTMLなどは独立した新しい発表のアンカーがないと見逃すことがあります。
- 同日同一メールについてIMAP+ローカル送信台帳で重複を抑止しますが、ネットワーク断や送信直後のIMAP反映遅延があれば絶対的な exactly-once は保証できません。
- このシステムからChatGPT Libraryへの自動アップロードはしません。唯一の正本はGitHubの監査JSONとActions evidence artifactであり、ChatGPTはGitHub接続で閲覧できます。

## v2.1 (2026-11-25) 改修

前版の13件テストから23件、v2.2で計26件に増強しました。古い固定記事・ニュースの掲載順序・過去に確認済み原文との鮮度対比・同一日付の時刻曖昧性・原文タイトル一致・CJK日付を重点検査します。詳細は `IMPROVEMENTS_2026-11-25.md` を参照。

## v2.2 段階的移行の安全確認（2026-11-25）

1. GitHub connectorの実測書込みは `403 Resource not accessible by integration` であり、このZIPはGitHubに**未導入**です。ローカルの模擬テスト結果を本番稼働とは記しません。
2. 旧監視タスクを維持したまま新コードをマージしても、`PHARMA_ENABLE_DELIVERY` が未設定なら**定時メールは送信されません**。
3. 初回はActions `send_email=false` で公式46社取得とQAの証拠を点検します。これは収集・保存までの試験です。
4. 本番移行後に旧4段階タスクを停止し、必要なGmail secretを設定してから `PHARMA_ENABLE_DELIVERY=true` にします。
5. GitHub Actionsの結果が一部未確認で赤表示になるのは仕様です。メール送信や保存が正しく実行されたかは別の指標で確認します。
6. 2026/11/25の追加テストはステージングメール初期値、CIの設定構造、46社固定順序、誤った成功判定防止を検査します。

## 既存71社と新46社の同居（v2.2の重要な変更）

旧 `.github/workflows/monitor.yml`、`requirements.txt`、`run.py`、`companies.csv`、`docs/` は保持します。インストーラーが既存ワークフローの `runs-on: ubuntu-latest` だけを `runs-on: ubuntu-24.04` に修正し、Playwright導入エラーの原因を回避します（71社の実収集の成功は別途検証）。新46社監視は `.github/workflows/pharma46.yml` と `requirements-pharma46.txt`、`pharma46/sources.json`、`tests_pharma46/` に分離します。既存71社の依存パッケージやサイト公開は変更しません。
