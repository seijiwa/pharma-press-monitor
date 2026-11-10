# 製薬会社 公式プレスリリース監視（71社）

- [公開サイト](https://seijiwa.github.io/pharma-press-monitor/)
- [NetNewsWire用の統合RSS](https://seijiwa.github.io/pharma-press-monitor/feed.xml)
- [自動実行と取得状況](https://github.com/seijiwa/pharma-press-monitor/actions/workflows/monitor.yml)

GitHub Actionsで毎時07・27・47分に実行し、結果をGitHub Pagesに公開します。予定時刻には遅延することがあります。企業別RSSはサイトの各社カードから開けます。

**登録71社は、正常取得71社を意味しません。** 最新の取得状況は公開サイトとActionsで確認できます。失敗を「更新なし」に置き換えず、全社の公式ページを取得できない実行は赤になります。その場合もサイト・RSS・失敗内容を更新します。

## 新着の扱い

初回は基準値を保存します。その後に増えた記事だけをRSSに配信し、既存記事を大量に新着として配信しません。取得先や抽出方式を変更した会社は、新しい基準値から開始します。検出日時は記事の発表日時とは異なります。

公式サイトのリンクと見出しを取得します。全記事の網羅は未検証です。公式サイト自身が使う公開ニュースデータも利用し、公式RSSしか取得できなかった会社は「公式RSSで補完中」と表示します。SECや第三者ニュースサイトを一次検知には使いません。

## 個別対応

- Amgen、BioMarin、Neurocrine、Novo Nordisk、Samsung Biologics：公式サイトの公開一覧データを取得。
- Akeso、第一三共、Immunome、住友ファーマ：独自の記事URL・PDF形式に対応。
- Innovent、Grifols：記事カード内の実際の見出しを使用。
- Kelun-Biotech：固定記事URLを提供しないカード一覧を見出し・日付で識別。RSSのリンク先は公式ニュース一覧です。
- Alvotech、Kura、Sareptaなど：現行の公式ニュースページを使用。
- Biogen：公式ニュース一覧を優先し、取得できない場合は公式トップページの最新ニュース欄を確認します。

取得拒否（HTTP 403）は回避したことにせず失敗として記録します。取得できない会社は対応が必要です。AvidityはNovartis、ReataはBiogenの公式発表を関連キーワードで確認します。独立企業としてのニュース配信が続いているという意味ではありません。サイトの「取得した記事と確認情報」には抽出例とエラーを掲載します。

## 構成

`companies.csv` に対象71社、`run.py` に取得と差分検出、`validate.py` に設定と動作の検証があります。実行結果を `data/` に保存し、`docs/` に統合RSS・71社別RSS・Webページを生成します。監視・保存・公開は `.github/workflows/monitor.yml` の一つの処理で実施します。
