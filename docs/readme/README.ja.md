# EPUB Browser

> **本をウェブサイトに変え、自分だけのライブラリーをつくる。**
>
> EPUB と PDF の書籍を静的ウェブサイトとして公開したり、アカウント、進捗同期、注釈、
> オプションの AI ネイティブ読書を備えたプライベートなセルフホストライブラリーを運用したりできます。

[静的ライブラリーを見る](https://epub-browser-test.yuhan.tech/) · [プライベートライブラリーを試す](#ライブデモ)

**README:** [English](../../README.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | [Español](README.es.md) | [Deutsch](README.de.md) | [Français](README.fr.md) | [Русский](README.ru.md) | [Italiano](README.it.md) | [Português (Brasil)](README.pt-BR.md) | [العربية](README.ar.md) | [Bahasa Indonesia](README.id.md) | [हिन्दी](README.hi.md) | [Tiếng Việt](README.vi.md) | [ไทย](README.th.md) | [Bahasa Melayu](README.ms.md)

<p align="center">
  <img src="https://raw.githubusercontent.com/dfface/epub-browser/main/epub_browser/assets/logo-lockup-color.png" alt="EPUB Browser ロゴ" width="520">
</p>

[![PyPI version](https://img.shields.io/pypi/v/epub-browser)](https://pypi.org/project/epub-browser/)
[![Python versions](https://img.shields.io/pypi/pyversions/epub-browser)](https://pypi.org/project/epub-browser/)
[![License](https://img.shields.io/github/license/dfface/epub-browser)](../../License.txt)

![共通の EPUB Browser リーダーで表示した PDF。元のページ、ナビゲーション、テーマ、読書ツールを利用できる。](https://raw.githubusercontent.com/dfface/epub-browser/main/docs/releases/assets/v2.8.0-pdf-reader.png)

EPUB Browser は、単なる書籍変換ツールではありません。どこにでも公開でき、自分でホストすることもできる、
完全な読書プラットフォームです。EPUB と PDF は、同じライブラリー、書籍ページ、目次、読書モード、
テーマ、進捗管理、注釈ワークフローを共有します。PDF の各ページはリーダーの章となり、
同じ読書画面の中で PDF.js によってローカルにレンダリングされます。別のビューアーは不要で、
実行時 CDN も使用しません。

## 目次

- [プロジェクト概要](#プロジェクト概要)
  - [EPUB Browser を選ぶ理由](#epub-browser-を選ぶ理由)
  - [技術スタック](#技術スタック)
  - [SSG と Server の選択](#ssg-と-server-の選択)
  - [ライブデモ](#ライブデモ)
  - [AI ネイティブ読書（Server のみ）](#ai-ネイティブ読書server-のみ)
  - [Kindle ミニマルモード](#kindle-ミニマルモード)
- [はじめに](#はじめに)
  - [インストール方法の選択](#インストール方法の選択)
  - [クイックスタート](#クイックスタート)
- [書籍形式と読書](#書籍形式と読書)
  - [ソースと安定した書籍 ID](#ソースと安定した書籍-id)
  - [PDF：1 ページを 1 章に](#pdf1-ページを-1-章に)
- [デプロイ](#デプロイ)
  - [SSG](#ssg)
  - [Server](#server)
  - [Docker](#docker)
- [リファレンスと運用](#リファレンスと運用)
  - [コマンドリファレンス](#コマンドリファレンス)
  - [読書データと機能の配置](#読書データと機能の配置)
  - [Server API と WebHooks](#server-api-と-webhooks)
  - [データの安全性とトラブルシューティング](#データの安全性と移行)
- [開発とライセンス](#開発とライセンス)
- [ドキュメントハブ](../README.md)

## プロジェクト概要

### EPUB Browser を選ぶ理由

- **どこにでも公開でき、管理権も手放さない。** 1 つのコマンドで Pages、オブジェクトストレージ、
  Nginx 向けの完全な静的サイトを構築できます。また、アカウント、書籍権限、OIDC を備えた
  永続的な Server を運用することもできます。アプリケーションのアセット、フォント、PDF.js、
  レンダラーはすべてローカルから配信されるため、読書が CDN に依存することはありません。
- **EPUB と PDF に、1 つの本格的なリーダーを。** 両形式はライブラリー、書籍ページ、目次、
  レスポンシブレイアウト、3 つの読書モード、テーマ、全画面表示、進捗管理を共有します。
  PDF の各ページは読書画面内に表示され、別のプレビューアーに切り替えることなく、
  ズーム、テキストレイヤーの選択、注釈を利用できます。
- **書籍だけでなく、必要な箇所も見つけられる。** ライブラリーの検索はメタデータ、タグ、
  ピンインに対応し、並べ替えとページネーションも利用できます。Server 側の EPUB 全文検索は、
  すべての検索結果を章ごとにまとめて返し、ハイライトされた箇所へ移動できます。安定した書籍 ID により、
  再開位置、注釈、履歴が常に同じ書籍に関連付けられます。
- **スクロールするだけでなく、理解を深められる。** Server モードでは、EPUB の章ガイド、
  根拠箇所とつながる解説、マインドマップ、非公開の Ask AI を原文のそばに置けます。
  ハイライト、メモ、辞書、百科事典は EPUB とテキストレイヤーのある PDF の両方で動作し、
  Server の単語リストには各単語の出典と習熟状態が記録されます。
- **読書を、残しておく価値のある履歴に。** 入れ子の本棚、評価、レビュー、注釈のエクスポート、
  アクティビティカレンダー、傾向、書籍ごとの統計、読書時間ランキングが、つながりのある記録を作ります。
  Server は読書データをアカウントごとに非公開で保持し、複数の端末間で同期します。
- **ビューアーではなく、読書サービスを運用できる。** Server モードでは、管理者による Web アップロードや
  監視フォルダーから書籍を追加し、設定可能な LRU 方式のキャッシュ削除でディスク使用量を制限し、
  メンバーと AI の権限を管理し、OpenAPI、PAT、WebHooks で連携できます。Kindle のミニマル読書画面は
  機能が制限された端末にも対応します。Server には、時計、カレンダー、予定、メモ、ポモドーロタイマーを備えた
  個人用 Kindle スクリーンセーバーダッシュボードもあります。

![EPUB 原文のそばに埋め込まれた章ガイドと、非公開の Ask AI ドロワー。](https://raw.githubusercontent.com/dfface/epub-browser/main/docs/readme/assets/ai-native-reading.png)

*AI ネイティブなガイドと非公開の質問は、常に原書に結び付いています。*

![アクティビティカレンダーと読書時間の傾向を表示する、非公開の読書インサイト画面。](https://raw.githubusercontent.com/dfface/epub-browser/main/docs/readme/assets/reading-insights.png)

*読書インサイトは、積極的な読書を、自分だけの理解しやすい履歴に変えます。*

### 技術スタック

EPUB Browser は、あえて小規模なサーバーレンダリングの Web スタックを採用しています。
インストールされるアプリケーションには SPA フレームワークがなく、Node.js ランタイムも不要です。

| レイヤー | 技術 | 役割 |
| --- | --- | --- |
| フロントエンド | セマンティック HTML、CSS、ES モジュールとブラウザー API を使う VanillaJS | SSG と Server で共有する 1 つのレスポンシブ UI |
| CLI と Server | Python 3.9+、Starlette、Uvicorn | 変換コマンド、認証付きページ、API、バックグラウンド処理 |
| データ | SQLite と再構築可能な JSON コンテンツキャッシュ | ユーザー状態と EPUB／PDF の派生コンテンツを分離 |
| 書籍形式 | lxml、pypdf、pypdfium2、PDF.js | 厳密な解析を優先する統一 EPUB 解析・サニタイズ、PDF メタデータ・表紙、ローカルブラウザーレンダリング |
| オフラインとアセット | Service Worker、ハッシュ付き不変アセット、バージョンを固定したサードパーティー依存関係 | 実行時 CDN のない自己完結型配信 |
| 配布 | PyPI、Docker、通常の静的ホスティング | 同じコードベースを SSG または永続的な Server として提供 |
| オプションの AI | OpenAI 互換 API、ローカルでレンダリングされる Markdown、KaTeX、Mermaid | Server モードのみの EPUB 学習レイヤー |

Node.js は、メンテナーがブラウザー側のテストを実行する場合にだけ使用します。
リーダーの本番ランタイムには含まれません。

### SSG と Server の選択

同じソース処理とページテンプレートが、明確に分かれた 2 つのデプロイモードを支えています。
書籍形式ではなく、読書データをどこに置くかで選んでください。

| 機能 | `ssg` | `server` |
| --- | --- | --- |
| EPUB と PDF | 対応 | 対応 |
| 配信方式 | Pages、オブジェクトストレージ、Nginx 向けの静的 HTML／アセットをアトミックに生成 | 置き換え可能なコンテンツキャッシュを基盤とする、動的な認証付きページ |
| アカウントとアクセス制御 | なし | 管理者／メンバーアカウント、制限付き書籍の許可、セッション、CSRF 保護 |
| OIDC シングルサインオン | 含まない | 汎用 Provider、既存アカウントとの連携、オプションのメンバープロビジョニング |
| 進捗、注釈、本棚 | 現在のブラウザーに保存 | 認証済みアカウントごとに SQLite で同期 |
| 評価、レビュー、読書セッション | 出力しない | アカウントごとの非公開記録と読書インサイト |
| ソースの更新 | `ssg` を再実行 | 再起動、再スキャン、または `--watch` を使用 |
| 管理、タグ、OpenAPI、WebHooks | 含まない | 含む |
| AI 読書と Ask AI | 含まない | 設定され、明示的に許可された場合は EPUB で利用可能。PDF では非表示 |
| 実行時データベース | なし | 永続モードでは必須 |
| 最適な用途 | 公開／静的ホスティング、オフラインバンドル、シンプルな個人公開 | プライベートライブラリー、複数端末または複数読者、自動化、アクセス管理 |

通常の静的ファイルが必要な場合は `ssg` を使用してください。アカウント、端末間のデータ、
アクセス制御、ソース変更の自動反映が必要な場合は `server` を使用してください。

### ライブデモ

- **SSG モード**： [epub-browser-test.yuhan.tech](https://epub-browser-test.yuhan.tech/)
- **Server モード**： [epub.yuhan.tech](https://epub.yuhan.tech/) — ユーザー名 `demo`、パスワード `demo` でサインインできます。

### AI ネイティブ読書（Server のみ）

Server モードでは EPUB 書籍に、章ガイド、根拠箇所とつながる解説、マインドマップ、
振り返りの問い、非公開の Ask AI ドロワーを追加できます。読者は原文から離れる必要がありません。
生成結果にも書籍へのアクセス権が適用され、メンバーには明示的な許可が必要です。SSG には、
AI のコントロール、ジョブ、アカウントデータ、プロバイダー設定は一切含まれません。
PDF では、AI 読書と Ask AI を意図的に非表示にしています。

インタラクションモデルの詳細については [AI ネイティブ読書ガイド](../ai-native-reading.md)を、
レンダリングとネットワーク安全性の境界については [ローカルリッチテキストレンダラーの注記](../third-party-ai-renderers.md)を参照してください。

### Kindle ミニマルモード

旧型の e-Ink Kindle（および機能が制限されたその他のブラウザー）では、依存関係のないミニマルな読書画面を利用できます。
`--kindle` で有効にします。

- SSG：`epub-browser ssg --kindle -o output/ SOURCE...`
- Server：`epub-browser server --kindle --server-dir data SOURCE...`

各 EPUB 書籍（PDF 書籍は対象外）に、次の 3 つのページが追加されます。

- ミニマル本棚 `/kindle-library.html`
- 書籍ページ `/book/<id>/kindle.html`
- 章ページ `/book/<id>/kindle_chapter_N.html`

これらのページは e-Ink 向けに調整されています。最小限のマークアップ、CSS のみのテーマ、
ES5 互換スクリプトを採用し、Service Worker とフレームワークは使用しません。JavaScript がなくても読書できます。
テーマ切り替え（Light / Sepia / Dark）、フォントサイズ（A- / A+）、インターフェースのローカライズは、
プレーンな HTML に軽量なインラインスクリプトを重ねて実現しています。

すべてのページに、テーマとフォントのコントロール（ヘッダーと章フッターの両方）、目次ナビゲーション、
前／次の章、保存された進捗から再開する「続きを読む」リンクがあります。

読書進捗はモードによって異なります。

- **SSG：** 進捗は現在のブラウザーの Cookie に保存されます。ローカルのみで、アカウントはありません。
- **Server：** 進捗と読書ハートビートは、サインイン済みアカウントごとに SQLite で同期されます。
  Kindle 画面は読み取りと報告専用です。現在の章を記録してハートビートを報告し、読み取り専用の本棚を表示しますが、
  インサイトやコンテンツ管理は提供しません。

すべての Kindle 画面でアクセス制御が適用されます。公開が制限された書籍の場合、権限のないユーザーには、
ミニマル本棚では書籍が表示されず、書籍ページ、章ページ、進捗 API では 403 が返されます。

対応ブラウザー（UA に `Kindle/`、`Arora/` などを含むもの）は、通常のリーダーからミニマルページへ自動的にリダイレクトされます。
上記の URL に直接アクセスすることもできます。そのため、低スペックな端末や JavaScript が制限された端末でも、
ミニマルモードを代替画面として利用できます。

## はじめに

### インストール方法の選択

EPUB Browser には 2 つのインストール方法があります。どちらも、1 つ以上の `.epub` または `.pdf` ファイル、
入れ子のディレクトリー、Calibre 形式のライブラリーディレクトリーを指定できます。

| インストール方法 | 用途 | ホスト要件 |
| --- | --- | --- |
| PyPI | SSG または Server モード | Python 3.9 以降 |
| Docker | 永続的な Server モード | Docker Engine。Python はイメージに含まれます |

#### PyPI（SSG または Server）

コマンドラインアプリケーションをインストールします。

```bash
pip install epub-browser
```

モード別のコマンドリファレンスを表示します。

```bash
epub-browser --help
epub-browser ssg --help
epub-browser server --help
```

#### Docker（Server）

公開されている [`dfface/epub-browser`](https://hub.docker.com/r/dfface/epub-browser)
イメージは Server モードで動作し、ホストに Python は不要です。

```bash
docker pull dfface/epub-browser:latest
```

現在のリリースを評価する場合は `latest` を使用し、再現可能な本番デプロイでは番号付きリリースタグを固定してください。
必須の書籍・状態マウント、Compose のクイックスタート、初回セットアップ、ネットワークの案内については、
[Docker](#docker)を参照してください。

### クイックスタート

#### 静的サイトを生成する

```bash
epub-browser ssg /path/to/books \
  --output-dir /path/to/dist
```

`dist/` は HTTP で配信してください。ブラウザーのストレージ、モジュール、マニフェスト、Service Worker には HTTP オリジンが必要なため、
生成したページを `file://` で直接開くことはサポートされていません。

URL プレフィックスの下にサイトをホストする場合は、ファイルシステム上の出力先とは別に公開パスを設定します。

```bash
epub-browser ssg /path/to/books \
  --output-dir /path/to/dist \
  --base-path /my-repository/
```

`--base-path` は生成される URL を変更するもので、ファイルの書き込み先を変更するものではありません。
`/my-repository/` を指定すると、リンク、アイコン、マニフェスト、書籍メタデータ、Service Worker のエントリーにはすべてそのプレフィックスが使われ、
ファイル自体は引き続き `dist/` の直下に置かれます。

#### 永続的な Server ライブラリーを実行する

```bash
epub-browser server /path/to/books \
  --server-dir /path/to/epub-browser-state \
  --watch
```

`http://127.0.0.1:8000/` を開きます。初回アクセス時に、EPUB Browser は最初の管理者の作成を求めます。
この初回セットアップが完了するまで、ライブラリーはスキャンも公開もされません。

Docker を選択した場合は、上記の Python コマンドを省略して、
[Docker Compose のクイックスタート](#docker-compose)に進んでください。

## 書籍形式と読書

### ソースと安定した書籍 ID

位置引数 `SOURCE` には、それぞれ EPUB ファイル、PDF ファイル、またはディレクトリーを指定できます。
ディレクトリーは再帰的に検索されます。1 つのコマンドに複数のソースを渡すこともできます。

```bash
epub-browser server book.epub /srv/library /srv/periodicals \
  --server-dir /srv/epub-browser \
  --watch
```

各書籍には安定した `book_id` が割り当てられ、生成される URL とブラウザーデータでは `book_hash` としても公開されます。
CLI 全般のデフォルトは次のとおりです。

```bash
--book-id-storage sidecar
```

sidecar モードでは、ソースの隣に `BOOK.epub.epub-browser.json` や `BOOK.pdf.epub-browser.json` のような識別ファイルを作成し、
ソースのバイト列は変更しません。sidecar には、安定した ID と検証済みの SHA-256 ソースフィンガープリントが保存されます。

ID を EPUB の OPF メタデータまたは PDF の文書情報辞書に格納する場合は、そのコマンドで処理するすべてのソースで embedded モードを使用します。

```bash
--book-id-storage embedded
```

embedded モードでは、変換前に EPUB ZIP を再構築したり、PDF のメタデータ更新を追加したりする場合があります。
PDF を更新できず、ソースが変更されていない場合、EPUB Browser は同じ ID を隣接する sidecar に保存します。
これには、署名付き、暗号化、読み取り専用の PDF も含まれます。ID が一致しない場合、アクティブなソース間で ID が重複している場合、
保存先が無効な場合、必要な保存先に書き込めない場合、EPUB Browser は処理を停止します。

ストレージモードを移行する場合、EPUB Browser は既存の ID を選択した保存先にコピーし、もう一方の有効な保存先も保持します。
v2.0.4 ですでに embedded ID が設定されている場合、その ID は EPUB を書き換えずにデフォルトの sidecar へコピーされます。
SSG と Server はいずれも、メタデータ更新後の PDF ソースをバイト単位で同一のコピーとして配信します。

### PDF：1 ページを 1 章に

PDF は両方のデプロイモードでサポートされています。リーダーは PDF の各ページを通常の EPUB Browser の章として扱うため、
既存の書籍ページ、章ナビゲーション、目次、ページネーション、連続読書、進捗、読書セッション、注釈、
辞書、百科事典が、単一の共有 UI とデータモデルのまま利用できます。

| PDF の概念 | SSG | Server |
| --- | --- | --- |
| ページ 1 の URL | `chapter_0.html` | `/book/<book-id>/chapter_0.html` |
| ページ N の URL | `chapter_{N-1}.html` | `/book/<book-id>/chapter_{N-1}.html` |
| ページラベルと目次 | ローカルで生成。すべてのページを一覧表示 | PDF メタデータキャッシュからレンダリング。すべてのページを一覧表示 |
| 埋め込みアウトライン | 移動先ページの目次エントリーにマーカーを表示 | 同じマーカーを表示し、ページエントリーの削除や並べ替えは行わない |
| スクロールとページネーション／ページめくり | 静的な章ページの枠組みとローカル PDF.js | 動的に生成する共通の章ページの枠組みとローカル PDF.js |
| ハイライト、メモ、辞書、百科事典 | テキストレイヤーがある場合は共有のブラウザーローカルコンポーネント | テキストレイヤーがある場合は共有の認証付きコンポーネント |
| 元の PDF バイト列 | 静的な書籍出力に 1 つの `document.pdf` | キャッシュされた文書を配信する、Session 専用の Range 対応ルート |

表示されるラベルと PDF.js のページ番号は 1 始まりです。URL、状態、API、SQLite の章インデックスは 0 始まりです。
したがって、PDF のページ 1 は常に `chapter_0.html` です。正規化された目次には、すべてのページに `Page N` エントリーが 1 つずつ保持されます。
PDF に埋め込まれたアウトラインのタイトルは、移動先エントリーにアウトラインマーカーとして付加されます。
1 ページに複数のマーカーが付く場合もあります。

SSG は、1 つの `document.pdf` と、ページごとに 1 つの `chapter_<index>.html` の枠組みを書き出します。
SSG の出力には、Session スクリプト、`/api/*` 呼び出し、同期された注釈データ、Server 依存関係は含まれません。
Server は、ソース全体をバイト単位で同一のまま `book/<book-id>/pdf/document.pdf` として保存し、分割も書き換えもしません。
Server は PDF メタデータから同じ章ページの枠組みを動的にレンダリングします。ソースが変更されると PDF キャッシュ
（文書、メタデータ、派生した表紙）を無効化して完全に再生成するため、新旧のページが混在することはありません。

Server の原文書エンドポイントは Session 専用です。
`GET`/`HEAD /api/books/<book-id>/document`。認証、書籍の可視性、PDF 形式、ソース／キャッシュのフィンガープリントを確認したうえで、
`ETag`、`Accept-Ranges`、プライベートキャッシュ、`nosniff`、インライン PDF disposition を備えた、範囲を制限した単一 Range レスポンスをサポートします。
絶対パスは公開せず、PAT 認証では利用できず、PAT／OpenAPI の提供範囲にも含まれません。
SSG にはローカルの `document.pdf` だけがあり、原文書 API はありません。

PDF.js で利用可能なテキストレイヤーを持つ PDF では、既存の選択ポップアップと注釈コンポーネントをそのまま再利用し、
ハイライト、メモ、辞書、百科事典を利用できます。注釈の保存、所有権、エクスポート、一覧、ディープリンクも共有され、
PDF 専用の注釈テーブルや設定 UI はありません。スキャンされた PDF や画像のみの PDF も読書はできますが、
利用可能なテキストレイヤーがない場合、選択に基づくハイライト、メモ、辞書、百科事典、文書検索は明示的に利用不可となります。
ページをまたいだ選択範囲はコピーできますが、注釈や辞書・百科事典の参照操作では、ローカライズされた未対応メッセージが表示されます。
ページ内の選択は引き続き動作します。

PDF.js を別個のビューアー画面として使うわけではありません。ビルドまたは公開の前に、バージョンを固定したサードパーティーアセットを取得し、検証してください。

```bash
python3 tools/sync_vendor_assets.py fetch
python3 tools/sync_vendor_assets.py verify
```

実行時には、アプリケーションがローカルのハッシュ付き PDF.js モジュールとワーカーアセットを配信し、CDN から取得することはありません。
画像ライトボックスにはバージョンを固定した GLightbox を使用します。Fancyapps/Fancybox は、実行時にも再配布にも使用しません。
バージョンを固定したアセットとリリースワークフローについては、[third_party/README.md](../../third_party/README.md)を参照してください。

## デプロイ

### SSG

SSG は、出力先の兄弟ステージングディレクトリーに完全なスナップショットを構築して検証し、その後で出力先を置き換えます。
いずれかの変換が失敗した場合、以前の出力先は変更されません。生成される出力には、Server データベース、移行状態、
アカウントページ、実行時キャッシュメタデータは含まれません。

SSG は、意図的にローカルでアカウントを使わない動作になっています。

- 読書進捗と注釈には、現在のオリジン上のブラウザーストレージを使用します。
- 本棚はローカル JSON のインポートとエクスポートに対応し、クラウド同期操作はありません。
- ログイン、アカウント設定、Server API、ユーザーに依存するコントロールは含まれません。
- 保存先はローカルブラウザーストレージに固定され、設定項目としては表示されません。
- 静的出力には、オフラインでアセットを利用するために必要な Service Worker が含まれます。

必要なアプリケーションの JavaScript、CSS、フォント、アイコンはすべて出力に含まれます。
唯一のオプションのネットワークリクエストについては、[自己完結型の配信とネットワーク動作](#自己完結型の配信とネットワーク動作)を参照してください。

### Server

#### 初期設定、アカウント、権限

新しい永続状態ディレクトリーでは、通常のページは `/setup` にリダイレクトされます。最初の管理者が作成されるまで、
API、イベントストリーム、生成アセット、書籍はセットアップが必要であることを示すレスポンスを返します。
ポートを公開する前に、ループバックまたは信頼できる別のプライベート経路でセットアップを完了してください。
最初にセットアップを正常に送信した人が、管理者アカウントを取得します。

セットアップ後は次のとおりです。

- 公開登録は閉じられ、管理者がユーザーを作成・管理します。
- アカウントには `administrator` または `member` のいずれかのロールがあります。
- 通常の書籍は、すべての認証済みアカウントに表示されます。
- 制限付き書籍は、管理者と明示的に選択されたユーザーだけに表示されます。
- 各ユーザーは、自分の本棚、進捗、注釈、アクティブセッションを所有します。
- ユーザーは自分のパスワードを変更し、セッションを取り消せます。
- 管理者は、ユーザー、ロール、パスワード、セッション、書籍の許可を管理できます。
- セッションには HttpOnly Cookie、CSRF 保護、30 日間のスライディング有効期限を使用します。

#### OIDC シングルサインオンとアカウント連携

Server モードでは、Authelia、Keycloak、Authentik、その他の互換サービスを含む、1 つの汎用 OpenID Connect（OIDC）Provider を利用できます。
**Administration → OIDC login** で、読者に表示する Provider 名、発行者 URL、クライアント ID、クライアントシークレット、
完全一致するリダイレクト URI、スコープ、ユーザー名クレームを入力します。EPUB Browser は、Discovery と S256 PKCE を使う
Authorization Code フローを利用し、署名付き ID トークンを検証します。外部アカウントは `(issuer, sub)` のみで識別し、
メールアドレスとユーザー名クレームは表示・プロビジョニングの手掛かりにすぎず、アカウントの識別には使用しません。

Provider には、スキームとホストを含む次のコールバックを正確に登録してください。

```text
https://reader.example.com/auth/oidc/callback
```

既存ユーザーは、ローカルでサインインして Account settings から Provider を接続できます。
未連携の外部アカウントでサインインした場合は、既存のローカルユーザー名とパスワードを一度だけ求められます。
オプションの自動プロビジョニングでは、パスワードのないメンバーが作成されますが、管理者ロールがインポートされることはありません。
既存ユーザーに先に連携させてください。自動プロビジョニングを早く有効にしすぎると、**重複したローカルアカウント**が作成される可能性があります。
ローカルメンバーのパスワードログインを無効にしても、**ローカル管理者**のパスワードログインは常に利用できます。
この復旧用認証情報は、動作確認を行い、安全に保管してください。Provider のログアウトは実行されず、Provider のアクセス／リフレッシュトークンも保存されません。

Authelia では、その OIDC Provider セクションに confidential client を設定します。以下の抜粋では意図的に偽の値を使用しており、
Authelia に必要な Provider キーとポリシーは設定済みであることを前提としています。強力なランダムなクライアントシークレットのハッシュを
Authelia に保存し、対応する生のシークレットを EPUB Browser に一度だけ入力してください。

```yaml
identity_providers:
  oidc:
    clients:
      - client_id: 'epub-browser'
        client_name: 'EPUB Browser'
        client_secret: '<AUTHELIA_HASH_OF_A_RANDOM_SECRET>'
        public: false
        authorization_policy: 'two_factor'
        require_pkce: true
        pkce_challenge_method: 'S256'
        redirect_uris:
          - 'https://reader.example.com/auth/oidc/callback'
        scopes: ['openid', 'profile', 'email']
        response_types: ['code']
        grant_types: ['authorization_code']
        token_endpoint_auth_method: 'client_secret_basic'
```

EPUB Browser では、発行者に `https://auth.example.com`、クライアント ID に `epub-browser`、スコープに `openid profile email`、
ユーザー名クレームに `preferred_username` を指定します。保存時にライブ Discovery と機能検証が実行され、失敗した場合は以前の設定が有効なままになります。

#### AI 読書の設定と管理

管理者は **Administration** で AI 読書を設定します。このページは、ユーザー管理の直後、書籍管理の前にあります。
OpenAI 互換の Base URL、API キー、モデル、タイムアウト、コンテキスト予算、同時実行数の上限、
デフォルトの 1 日あたりプロバイダー呼び出し上限が、Server の SQLite データベースに保存されます。
AI はメンバーに対して初期状態で無効になっており、管理者がメンバーごとにアクセスを許可する必要があります。
個別の 1 日あたり上限も設定でき、`0` は無制限を意味します。

章の学習レイヤーと書籍全体のレビューは、対象言語ごとに共有されますが、フォローアップの会話はアカウントごとに非公開です。
結果、タスク状態、カスタムタグ、書籍の読書分類、非公開のフォローアップは SQLite に保存されます。
モデル設定を変更した後も、管理者が明示的に再生成するまで、古い結果は利用できます。

読者が AI ガイドを要求したり質問したりすると、選択された EPUB テキストと圧縮された会話コンテキストが、
設定された外部プロバイダーに送信されます。そのコンテンツをプロバイダーへ送信することが読者に許可されている場合以外は、
この機能を有効にしないでください。API キーがブラウザーに返されたり API で公開されたりすることはありません。
Server の状態ディレクトリーも適切に保護してください。

無人での初回起動には、ユーザー名とパスワードファイルを指定します。

```bash
epub-browser server /path/to/books \
  --server-dir /path/to/state \
  --admin-username admin \
  --admin-password-file /run/secrets/epub-browser-admin-password \
  --no-browser
```

パスワードファイルのモードは `0600` にしてください。EPUB Browser は末尾の改行を 1 つ削除し、Argon2id ハッシュを保存します。
シークレットが出力されることはありません。設定が不完全な場合、ファイルが空の場合、ファイルを読み取れない場合は起動が停止します。
セットアップが完了すると、以降の起動ではブートストラップシークレットを読み取りません。

同等の環境変数は `EPUB_BROWSER_ADMIN_USERNAME` と `EPUB_BROWSER_ADMIN_PASSWORD_FILE` です。
`EPUB_BROWSER_ADMIN_PASSWORD` は、パスワードファイルが設定されていない場合にだけ使われる平文のフォールバックです。
CLI のパスワードファイルパスは、環境変数のパスワードソースより優先されます。

#### ブラウザーの起動とログ

デフォルトでは、HTTP リスナーが開始された後に、Server は OS のデフォルトブラウザーを開こうとします。
`--no-browser` は、このローカルでの起動を抑止します。**Web インターフェースやブラウザーからのアクセスを無効にするものではなく**、
ローカルの `webbrowser.open(...)` 呼び出しを抑止するだけです。Docker、systemd、SSH セッション、ヘッドレスマシン、スクリプトで使用してください。

デフォルト（`--log-level error`）では、CLI はエラーのみを出力するため、通常のメッセージや警告でターミナルの進捗表示が妨げられません。
対話型ターミナルでは、バインドされた URL が一度だけ表示されます。非対話型の Docker やサービスとして実行する場合は、通常のメッセージを出力しません。
警告も出力するには `--log-level warning`、運用ログと HTTP アクセスログには `--log-level info`、最も詳細な出力には `--log-level debug` を使用してください。
`--log` は `--log-level info` の互換エイリアスとして残っています。

初回スキャンと watch スキャンは、ターミナルの `tqdm` ではなく Web インターフェースに表示されます。
成功時の概要は自動的に閉じ、失敗時の情報は手動で閉じるまで表示されたままになります。`--watch` を使用している場合、
ソースを修正または置き換えると、手動で再試行しなくても別のスキャンが開始されます。

#### 永続状態と一時状態

永続的な Server モードには `--server-dir` が必要です。使い捨てで実行する場合は、代わりに `--ephemeral` を使用します。

```bash
epub-browser server book.epub --ephemeral
```

一時状態はシャットダウン時に削除されます。実行のたびにデータベースが新しくなるため、無人ブートストラップ認証情報を指定しない限り、
セットアップも毎回繰り返されます。

永続的なレイアウト：

```text
<server-dir>/
├── .server.lock                 # reusable process-lock metadata
├── data/
│   ├── epub-browser.db          # authoritative accounts, books, grants, reading data
│   ├── migration-state.json     # restart-safe migration state
│   └── backups/                 # verified pre-migration database copies
└── cache/
    ├── catalog.json             # generated-cache status
    ├── public/                  # served application and converted books
    └── staging/                 # replaceable conversion work
```

正規のデータは `data/` だけです。`cache/` は削除しても再構築されます。アップグレードやコンテナー置き換えの際にも `data/` を保持してください。
排他性は OS のロックで制御されます。`.server.lock` は正常なシャットダウン後も診断メタデータとして残る場合があります。

永続的な `data/epub-browser.db` はローカルファイルシステムに保存してください。WAL の同時実行では、共有ファイルシステムやネットワークファイルシステムはサポートされていません。
検証済みバックアップは `data/backups/` に残り、コミット済みのすべての WAL データを含みます。

#### LAN とリバースプロキシ

Server はデフォルトで `127.0.0.1:8000` にバインドします。信頼できる LAN で使用する場合：

```bash
epub-browser server /path/to/books \
  --server-dir /path/to/state \
  --watch \
  --host 0.0.0.0 \
  --port 8080 \
  --no-browser
```

組み込み HTTP サーバーを公開インターネットに直接公開しないでください。リバースプロキシで TLS を終端し、
ネットワーク制御を適用し、セキュア Cookie を有効にしてください。

リバースプロキシの背後で、アクティブセッションとログインレート制限に実際のクライアント IP を記録するには、
公開クライアントの範囲ではなく、**Server に直接接続するプロキシのネットワーク**を設定します。

```bash
epub-browser server /path/to/books \
  --server-dir /path/to/state \
  --watch \
  --host 0.0.0.0 \
  --trusted-proxy-cidr 172.32.11.1/32 \
  --trusted-proxy-cidr 10.42.0.0/16 \
  --cookie-secure \
  --no-browser
```

直接接続する各プロキシアドレスまたはネットワークに対して、`--trusted-proxy-cidr` を 1 回ずつ繰り返してください。
これらの CIDR のいずれかに属する直接ピアからのリクエストでのみ `X-Forwarded-For` を信頼し、
それ以外のピアからのリクエストでは、直接接続元のアドレスだけを記録します。Uvicorn の forwarded-address 処理は無効になっているため、
`Forwarded` と `FORWARDED_ALLOW_IPS` によってこの信頼境界を広げることはできません。
ブラウザーが HTTPS 経由でサービスにアクセスする場合にだけ `--cookie-secure` を使用してください。

### Docker

イメージは、次のデフォルトで永続的な Server モードを実行します。

- ソースは `/app/Library`
- 永続状態は `/app/EpubBrowserFiles`
- `--watch`
- `--no-browser`
- `--host 0.0.0.0 --port 80`
- `--book-id-storage embedded`
- `--kindle`

embedded モードでは EPUB または PDF ファイルを更新する場合があるため、ライブラリーは読み書き可能でマウントしてください。
Server 状態も読み書き可能でマウントし、コンテナーを置き換えても保持してください。

```bash
docker run -d \
  --name epub-browser \
  -p 127.0.0.1:8080:80 \
  -v /path/to/books:/app/Library:rw \
  -v /path/to/epub-browser-state:/app/EpubBrowserFiles \
  dfface/epub-browser:latest
```

ポートバインドやプロキシルールを変更する前に、`http://127.0.0.1:8080/setup` にアクセスしてください。

#### Docker Compose

Compose を使用したい場合のため、リポジトリーには [docker-compose.yml](../../docker-compose.yml) が含まれています。
チェックアウトしたディレクトリーで `Library/` を作成し、EPUB または PDF 書籍を置いてから、次を実行します。

```bash
docker compose up -d --build
```

公開されるのは `127.0.0.1:8080` だけで、ソースの EPUB／PDF 書籍は `./Library` に保持され、Server 状態は `./EpubBrowserFiles` に永続化されます。
イメージの暗黙のデフォルトを置き換えずにデプロイ固有のフラグを追加できるよう、Server の `command` はあえてすべてファイル内に記載しています。
`http://127.0.0.1:8080/setup` で一度だけのセットアップを完了してください。リモートアクセスには、このループバックバインドを維持し、
その前段に認証付き TLS リバースプロキシを配置してください。

無人セットアップの場合：

```bash
docker run -d \
  --name epub-browser \
  -p 127.0.0.1:8080:80 \
  -v /path/to/books:/app/Library:rw \
  -v /path/to/epub-browser-state:/app/EpubBrowserFiles \
  -e EPUB_BROWSER_ADMIN_USERNAME=admin \
  -e EPUB_BROWSER_ADMIN_PASSWORD_FILE=/run/secrets/epub-browser-admin-password \
  --mount type=bind,src=/path/to/admin-password,dst=/run/secrets/epub-browser-admin-password,readonly \
  dfface/epub-browser:latest
```

最初の起動に成功した後は、一度だけ使用するシークレットマウントを削除できます。読み取り専用ライブラリーが機能するのは、
すべての EPUB に、一致する有効な ID がすでに埋め込まれている場合だけです。ID を埋め込む際も、既存の sidecar は保持されます。

レガシー本棚 JSON をインポートしている間だけ、`/app/SyncData:ro` をマウントしてください。

```bash
-v /path/to/legacy-sync:/app/SyncData:ro
```

例では公開ポートをループバックにバインドしているため、コンテナーのサービスにはホスト上からしかアクセスできません。リモートアクセスには TLS リバースプロキシを使用し、
実際のコンテナーネットワーク CIDR を設定して、`--cookie-secure` を追加してください。

## リファレンスと運用

### コマンドリファレンス

#### `epub-browser ssg SOURCE [SOURCE ...]`

| オプション | 意味 |
| --- | --- |
| `--output-dir DIR`、`-o DIR` | アトミックな静的スナップショットの必須出力先。 |
| `--base-path PATH` | 公開 URL プレフィックス。デフォルトは `/`。先頭と末尾が `/` である必要があります。 |
| `--book-id-storage sidecar\|embedded` | 選択したすべてのソースに使う安定した ID の保存先。デフォルトは `sidecar`。 |
| `--kindle` | 旧型 e-Ink Kindle 向けに依存関係のないミニマルページを生成し、Kindle WebKit ブラウザーをそこへリダイレクトします。デフォルトはオフ。 |
| `--log` | `--log-level info` の互換エイリアス。 |
| `--log-level debug\|info\|warning\|error` | 運用ログの詳細度。デフォルトは `error` で、通常の変換出力と警告を抑制します。 |

#### `epub-browser server SOURCE [SOURCE ...]`

`--server-dir` と `--ephemeral` のどちらか一方だけを指定する必要があります。

| オプション | 意味 |
| --- | --- |
| `--server-dir DIR` | 永続的な正規データと、置き換え可能なキャッシュのルート。 |
| `--ephemeral` | 使い捨ての状態を使用。`--server-dir` とは相互排他。 |
| `--watch`、`-w` | ソースを監視し、追加、更新、移動、削除を反映します。 |
| `--host ADDRESS` | バインドアドレス。デフォルトは `127.0.0.1`。 |
| `--port PORT`、`-p PORT` | バインドポート。デフォルトは `8000`。 |
| `--no-browser` | ローカルのデフォルトブラウザーを起動しません。Web UI は引き続き利用できます。 |
| `--log` | `--log-level info` の互換エイリアス。 |
| `--log-level debug\|info\|warning\|error` | 運用ログの詳細度。デフォルトは `error`。HTTP アクセスログは `info` と `debug` で有効になります。 |
| `--legacy-sync-dir DIR` | 起動時の移行でレガシー本棚 JSON を読み取ります。 |
| `--book-id-storage sidecar\|embedded` | 選択したすべてのソースに使う安定した ID の保存先。デフォルトは `sidecar`。 |
| `--admin-username NAME` | 無人セットアップ時の初期管理者名。フォールバックは `EPUB_BROWSER_ADMIN_USERNAME`。 |
| `--admin-password-file FILE` | 優先して使用する初期シークレットファイル。ファイルが未設定の場合のフォールバックは `EPUB_BROWSER_ADMIN_PASSWORD_FILE`、その次は `EPUB_BROWSER_ADMIN_PASSWORD`。 |
| `--trusted-proxy-cidr CIDR` | `X-Forwarded-For` からクライアント IP を安全に解析するための、直接接続プロキシの信頼ネットワーク。繰り返し指定できます。 |
| `--cookie-secure` | ブラウザー向け HTTPS 経由の場合にだけセッション Cookie を送信します。 |
| `--kindle` | 旧型 e-Ink Kindle 向けに依存関係のないミニマルページを配信し、Kindle WebKit ブラウザーをそこへリダイレクトします。デフォルトはオフ。 |

#### 旧 v1 構文

旧構文は v2 メジャーライン全体でサポートされます。

| v1 コマンド | v2 への対応 |
| --- | --- |
| `epub-browser BOOKS` | `epub-browser server BOOKS --ephemeral` |
| `epub-browser BOOKS --output-dir STATE` | `epub-browser server BOOKS --server-dir STATE` |
| `epub-browser BOOKS --no-server --output-dir DIST` | `epub-browser ssg BOOKS --output-dir DIST` |
| `--sync-dir DIR` | `server --legacy-sync-dir DIR` |

旧バージョン専用の `--keep-files` は、一時的な Server ディレクトリーを保持します。永続的な Server ディレクトリーは、すでに永続化されています。
`--log` を指定すると、互換アダプターが同等の v2 コマンドを表示します。指定しない場合は静かなままです。

### 読書データと機能の配置

- EPUB／PDF と Calibre ライブラリーの再帰的な検出、メタデータタグ、検索、ピンイン検索
- レスポンシブなライブラリー、書籍詳細、章の読書インターフェース
- スクロール、ページめくり、連続読書、コンテンツ幅の調整、フォント、カスタム CSS、テーマ、集中読書モード
- ハイライト、メモ、注釈の閲覧、入れ子の本棚グループ、タグ、JSON インポート／エクスポート
- 英語、簡体字中国語、繁体字中国語、韓国語、日本語、スペイン語、ドイツ語、フランス語、ロシア語、
  イタリア語、ブラジルポルトガル語、アラビア語、インドネシア語、ヒンディー語、ベトナム語、タイ語、マレー語のインターフェースロケール
- Kindle／Silk ブラウザーに配慮した電子書籍リーダー向けの動作。ブラウザーの機能を多く使う機能は、簡略化される場合があります

| データ | SSG | Server |
| --- | --- | --- |
| 読書進捗 | ブラウザーローカル | 認証済みユーザーの SQLite レコード |
| ハイライトとメモ | ブラウザーローカル | 認証済みユーザーの SQLite レコード |
| 非公開の評価、レビュー、読書セッション履歴 | なし | 認証済みユーザーの SQLite レコード |
| 本棚 | ブラウザーローカル。インポート／エクスポート | 認証済みユーザーのバージョン付きクラウドドキュメント。自動保存 |
| アカウントとセッション | なし | `<server-dir>/data` 以下の SQLite |
| 書籍の許可 | なし | `<server-dir>/data` 以下の SQLite |

Server にはローカル／クラウドストレージのセレクターはありません。認証された読書データは常に Server に保存されます。
詳細な非公開の読書セッション履歴が SSG で出力されることはありません。SSG は Server API にアクセスせず、
常に現在のブラウザーオリジンのローカルストレージを使用します。

### 自己完結型の配信とネットワーク動作

読書に必要なアプリケーションは自己完結しています。必要な JavaScript、CSS、フォント、アイコン、マニフェスト、変換済み EPUB リソースは、
すべてローカルから配信されます。実行時の CDN 依存関係はありません。外部インターネットへの接続を遮断しても、セットアップ、ログイン、
閲覧、読書、注釈、進捗、本棚の利用、管理、ソース変換は妨げられません。

フッターでは、新しい EPUB Browser バージョンを見つけるために、GitHub Releases API へのオプションのリクエストが行われる場合があります。
失敗、ブロック、オフラインの場合は、その更新通知が表示されなくなるだけです。

SSG は静的な Service Worker を公開します。Server では、あるアカウントが別のアカウントのキャッシュされた保護コンテンツを受け取らないよう、
オリジン全体の Service Worker を意図的に無効化し、既存の登録も解除します。

### Server API と WebHooks

Server アカウントでは、Account settings でスコープ付きの個人アクセストークンを作成できます。外部クライアントは、
バージョン付きの `/api/v1/*` API で `Authorization: Bearer <PAT>` を使用します。ブラウザー Cookie ではこれらのルートを認証できません。
API の対象は、アクセス可能な書籍と章コンテンツ、トークン所有者の本棚、進捗、注釈、レビューです。
また、`admin:data:read` を持つ管理者 PAT では、他のユーザーのデータも読み取り専用で参照できます。

OpenAPI 3.1 ドキュメントは `/openapi.json` で利用できます。サインイン済みユーザーは `/api-docs` でローカルリファレンスを閲覧できます。
例：`curl -H 'Authorization: Bearer …' https://reader.example/api/v1/books`。章の詳細はデフォルトでサニタイズ済み HTML を返し、
`?format=text` を指定するとプレーンテキストを返します。

一覧エンドポイントは `items` と `next_cursor` を返します。`limit` のデフォルトは 24、最大は 100 です。
同じフィルターを維持し、`next_cursor` を `cursor` として渡すと次のページを取得できます。null カーソルは最終ページを示します。
たとえば、`/api/v1/me/annotations?book_id=BOOK_ID&chapter_index=0&fields=id,text,note` を使用すると、
1 つの EPUB 章または PDF ページから、選択した注釈フィールドを取得できます。クエリフィルターと対応フィールドは、
OpenAPI ドキュメントに記載されています。

単語リストもデフォルトで同じ一覧形式を使用します。古い `words` レスポンスを使用するクライアントは、
`page=1` または `page_size` を送信してレガシーページネーション形式を選択できます。

管理者は Administration で WebHook エンドポイントを管理します。シークレットは作成時またはローテーション時にだけ表示されます。
配信は署名され、永続化され、2xx 以外のレスポンスでは再試行されます。書籍レビューイベントには ID と操作タイムスタンプが含まれますが、
評価やレビュー本文は一切含まれません。

### データの安全性と移行

永続的な Server インストールをアップグレードする前に、ソースの EPUB／PDF 書籍と `<server-dir>/data` をバックアップしてください。
コンテナーを置き換える場合も、同じ永続状態ボリュームを維持してください。

起動時の移行は自動で、再起動しても安全です。レガシーデータベースを検証してバックアップを作成し、コピーをアップグレードし、
対象となるレガシーの本棚／進捗／注釈データを、作成予定の最初の管理者にインポートします。
成功したチェックポイントの後にだけ、置き換え可能なレガシー公開アーティファクトを廃止します。
通常のリクエストがレガシー同期ディレクトリーをスキャンすることはありません。破損したデータベース、無効なパスワードハッシュ、
曖昧なレガシーデータベース、競合する ID が検出された場合は、推測や上書きを行わず、起動を中止します。

移行後にルートへ残る `epub-browser.db` または `annotations.db` は、機密性の高い復旧用コピーであり、正規のデータベースではありません。
正規のデータベースは `data/epub-browser.db` であり、Server リクエストはルートに残されたファイルを使用しません。復旧用コピーは非公開に保ってください。
正規のデータベースと記録されたバックアップを確認し、v1 へのロールバックが不要になった後で、Server を停止している間にだけ手動で削除してください。
EPUB Browser が自動的に削除することはありません。

レガシールートに `epub-browser.db` と `annotations.db` の両方が存在する場合、起動は停止し、どちらも変更されません。
バックアップ、ロールバック、キャッシュ再構築、競合からの復旧については、[v2 への移行](../migration-v2.md)を参照してください。

### トラブルシューティング

#### コマンドは起動したがブラウザーが開かない

グラフィカルなローカルマシンで実行している場合は `--no-browser` を外すか、表示／バインドされた URL を手動で開いてください。
Docker、systemd、SSH、非対話型セッションでは、自分で URL を開くことが想定されています。

#### CLI の出力が少ない

特に非対話型環境では、`--log` を指定しない限り静かな動作になるのは意図的です。運用ログとアクセスの詳細が必要な場合は `--log` を追加してください。
Server のスキャン進捗は Web インターフェースに表示されます。

#### Docker で安定した ID を書き込めない

イメージはデフォルトで embedded モードを使用します。`/app/Library` を読み書き可能でマウントするか、一致する有効な ID をあらかじめ埋め込んでください。
書き込み可能な sidecar の方が適している場合にだけ、カスタムコマンドで `--book-id-storage sidecar` を使用してください。

#### 生成した SSG サイトのサブパス以下でリンクが切れる

`/reader/` のような正規化された `--base-path` を指定して再生成し、その同じプレフィックスで出力を配信するよう静的ホストを設定してください。

#### アップグレード後に Server が起動しない

最初に記録された移行または検証エラーを読み、データとソースファイルを保持し、[docs/migration-v2.md](https://raw.githubusercontent.com/dfface/epub-browser/main/docs/migration-v2.md)を参照してください。
エラーを回避するために、正規の `data/` ディレクトリーを削除しないでください。

## 開発とライセンス

### コントリビューション

[dfface/epub-browser](https://github.com/dfface/epub-browser) では Issue と Pull Request を歓迎します。
有用な報告には、実行したコマンド、ブラウザー／端末、再現手順、関連ログ、法的に共有可能な場合は EPUB または PDF を含めてください。

#### メンテナー向けのアーキテクチャ規約

コンテンツ処理、ページテンプレート、キャッシュ、権限、アセット、デプロイ動作を変更する前に、
[AGENTS.md](../../AGENTS.md)を読んでください。EPUB／PDF の形式境界、SSG／Server の責任範囲、独立したキャッシュリビジョン、
実行時 i18n の要件、セキュリティチェック、必須の検証が定義されています。*reader chapter*、*reading window*、
*reading stage*、*content cache* などの共有製品用語は、[CONTEXT.md](../../CONTEXT.md)で定義されています。

要点は、リーダー UI を 1 つに保ち、Server 専用データを SSG に含めず、EPUB と PDF の派生キャッシュを SQLite ユーザーデータから分離し、
実行時 CDN 依存関係を決して追加しないことです。共有部分に影響する変更は、該当する場合、
両方の形式と両方のデプロイモードでテストする必要があります。

#### ソースをチェックアウトして開発する

サードパーティーのブラウザーファイルは、プロジェクトソースではなく生成されるビルド入力であるため、
`epub_browser/assets/vendor/` は意図的に Git に含まれていません。開発またはビルドの前に、ロックファイルで指定されたバージョンのアセットを明示的に取得し、
その後オフラインで検証してください。

```bash
python3 tools/sync_vendor_assets.py fetch
python3 tools/sync_vendor_assets.py verify
python3 -m unittest tests.test_vendor_assets -v
python3 -m build
```

上記のうち、ブラウザーのベンダーアセットをダウンロードするのは `fetch` だけです。ロックファイルには、不変の npm tarball、
ファイルダイジェスト、許可リスト、ライセンスが記録されています。`verify`、テスト、アセットを取得済みのチェックアウトで行うビルド、
インストールされたリーダーは、ブラウザーアセットをダウンロードしません。標準の隔離ビルドコマンド `python3 -m build` でも、
ビルド要件のために Python パッケージインデックスを参照する場合があります。完全にネットワークを無効にしてビルドする場合は、
オフラインにする前にベンダーディレクトリーを用意し、`build`、`setuptools`、`wheel` を事前インストールしてから、
`PIP_NO_INDEX=1 python3 -m build --no-isolation` を実行してください。Wheel、ソース配布、Docker イメージ、生成された SSG サイトには、
検証済みファイルが含まれ、実行時 CDN 依存関係はありません。更新、リリース、リポジトリー管理のワークフローについては、
[third_party/README.md](../../third_party/README.md)を参照してください。

### ライセンス

[MIT](../../License.txt)
