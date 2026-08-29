# EPUB Browser

> EPUB と PDF を、プライベートな読書ライブラリーまたは自己完結型の静的サイトで楽しめます。

**README:** [English](../../README.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | [Español](README.es.md) | [Deutsch](README.de.md) | [Français](README.fr.md) | [Русский](README.ru.md) | [Italiano](README.it.md) | [Português (Brasil)](README.pt-BR.md) | [العربية](README.ar.md) | [Bahasa Indonesia](README.id.md) | [हिन्दी](README.hi.md) | [Tiếng Việt](README.vi.md) | [ไทย](README.th.md) | [Bahasa Melayu](README.ms.md)

**インターフェース言語（17 言語）：** 英語、簡体字中国語、繁体字中国語、日本語、韓国語、スペイン語、ドイツ語、フランス語、ロシア語、イタリア語、ブラジルポルトガル語、アラビア語、インドネシア語、ヒンディー語、ベトナム語、タイ語、マレー語。

[![PyPI version](https://img.shields.io/pypi/v/epub-browser)](https://pypi.org/project/epub-browser/)
[![Python versions](https://img.shields.io/pypi/pyversions/epub-browser)](https://pypi.org/project/epub-browser/)
[![License](https://img.shields.io/github/license/dfface/epub-browser)](../../License.txt)

![EPUB Browser の共通リーダーで表示した PDF ページ。](../releases/assets/v2.8.0-pdf-reader.png)

EPUB Browser は `.epub` と `.pdf` を、役割を明確に分けた 2 つのモードで扱います。

| | `ssg` | `server` |
| --- | --- | --- |
| EPUB と PDF | 対応 | 対応 |
| 配置先 | 静的ホスティング、Pages、オブジェクトストレージ、Nginx | 永続的なプライベート読書サービス |
| アカウント | なし | ローカルアカウント |
| 進捗、注釈、本棚 | このブラウザーだけ | SQLite 内のログイン済みアカウントのデータ |
| 原本の更新 | `ssg` を再実行 | サービスを再起動、または `--watch` を使用 |
| 実行時データベース | なし | 必須 |

PDF は第一級の書籍形式です。PDF の 1 ページ目は `chapter_0.html` となり、すべてのページが目次に並び、ローカルの PDF.js によって同じライブラリー、書籍ページ、読書画面、検索、注釈フローで表示されます。PDF で未対応の AI 読書などは明示的に非表示になり、読書中に CDN へ接続しません。

通常の静的ファイルを公開したい場合は `ssg` を、アカウント、端末間のデータ、書籍へのアクセス制御、原本の自動監視が必要な場合は `server` を選びます。

## 概要

### 技術スタック

フロントエンドはセマンティック HTML、CSS、Vanilla JavaScript で構成し、SPA フレームワークは使用しません。CLI と Server は Python 3.9+、Starlette、Uvicorn、SQLite を使い、PDF は pypdf、pypdfium2、PDF.js でローカル処理するため、実行時 CDN は不要です。

### デモ

- **SSG モード**: [epub-browser-test.yuhan.tech](https://epub-browser-test.yuhan.tech/)
- **Server モード**: [epub.yuhan.tech](https://epub.yuhan.tech/) — デモ用のユーザー名とパスワードはいずれも `demo` です。

### AI ネイティブ読書（Server 専用）

AI 読書は、書籍の横に一般的な要約を置く機能ではありません。本文の上に、共同で見直せる学習レイヤーを作成します。章の前の読書ガイド、必要なときだけ開く章の概観、引用箇所につながる解説と段落メモ、語句や珍しい文字の説明、章末のファインマン式のやさしい解説、さらに考えるための問いを、読書の流れの中に残します。

結果は SQLite に保存されるバックグラウンドジョブで生成され、書籍へのアクセス権を持つ読者で共有されます。追加の対話はアカウントごとに非公開です。管理者は OpenAI 互換プロバイダーを設定し、メンバーごとに利用を許可する必要があります。選択された EPUB の本文は設定済みの外部プロバイダーに送られるため、読者がこの処理を許可している場合だけ有効にしてください。SSG 出力には AI 操作、アカウント、ジョブ、プロバイダー設定は含まれません。

## はじめに

### 動作要件とインストール

- Python 3.9 以降
- 1 つ以上の `.epub` または `.pdf` ファイル、書籍を含む入れ子のディレクトリー、または Calibre 形式のライブラリーディレクトリー

PyPI からインストールすると、SSG と Server の両方のモードを利用できます：

```bash
pip install epub-browser

# モード別の完全なコマンドヘルプ
epub-browser --help
epub-browser ssg --help
epub-browser server --help
```

Docker で永続的な Server を実行する場合は、公開イメージを使用します。ホスト側の Python は不要です：

```bash
docker pull dfface/epub-browser:latest
```

### クイックスタート

#### 静的サイトを生成する

```bash
epub-browser ssg /path/to/books \
  --output-dir /path/to/dist
```

`dist/` は HTTP で配信してください。生成したページを `file://` で直接開くことはできません。サブパスに公開する場合は `--base-path /my-repository/` を追加します。このオプションは出力先ではなく、生成される URL を変更します。

#### 永続的な Server ライブラリーを実行する

```bash
epub-browser server /path/to/books \
  --server-dir /path/to/epub-browser-state \
  --watch
```

`http://127.0.0.1:8000/` を開きます。初回アクセス時に最初の管理者を作成します。この一度だけの設定が完了するまで、ライブラリーはスキャンも公開もされません。`--no-browser` はサービスがローカルの既定ブラウザーを自動で開くことだけを止め、Web UI を無効にはしません。

## データと運用

### データ、アカウント、アクセス境界

各書籍には安定した `book_id` があり、URL とブラウザーのデータでは `book_hash` とも表示されます。既定の `--book-id-storage sidecar` は原本の隣に識別ファイルを作成し、原本のバイト列を変更しません。EPUB では `--book-id-storage embedded` を OPF メタデータへ保存できますが、PDF では常に隣接する sidecar へフォールバックします。

Server の `--server-dir` は SQLite、キャッシュ、移行バックアップを含む権威ある状態ディレクトリーです。アカウント、本棚、読書進捗、注釈、AI 結果、ジョブもここに保存されます。管理者はユーザー、ロール、セッション、制限付き書籍の許可を管理し、通常のメンバーは許可された書籍と自分の非公開データだけを利用できます。このディレクトリーとバックアップの権限を適切に保護してください。

使い捨ての試用には次を使用できます。

```bash
epub-browser server book.epub --ephemeral
```

一時状態は終了時に削除されるため、次の起動時には再設定が必要です。本番では常に `--server-dir` を使用してください。

### Docker とリバースプロキシ

コンテナーでは書籍ディレクトリーを読み取り専用でマウントし、`--server-dir` は永続ボリュームにマウントしてください。リバースプロキシのヘッダーは、信頼できるプロキシからのものだけを受け入れる必要があります。公開環境では HTTPS を使用し、デプロイの説明に従って信頼するプロキシとホスト名を設定してください。

Docker Compose の完全な例、CLI 引数、データ移行、LAN／リバースプロキシ、トラブルシューティングは、[英語版の完全な README](../../README.md) または [簡体字中国語版の完全な README](README.zh-CN.md) を参照してください。コマンドラインオプションと 2 つのモードの動作は、すべての言語で同じです。

## 開発とライセンス

### コントリビュートとライセンス

Issue と Pull Request を歓迎します。ライセンスは [License.txt](../../License.txt) を参照してください。
