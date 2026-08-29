# EPUB Browser

> 以同一套閱讀體驗閱讀 EPUB 與 PDF：既可建立自包含的靜態網站，也可執行私人閱讀服務。

**README：** [English](../../README.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | [Español](README.es.md) | [Deutsch](README.de.md) | [Français](README.fr.md) | [Русский](README.ru.md) | [Italiano](README.it.md) | [Português (Brasil)](README.pt-BR.md) | [العربية](README.ar.md) | [Bahasa Indonesia](README.id.md) | [हिन्दी](README.hi.md) | [Tiếng Việt](README.vi.md) | [ไทย](README.th.md) | [Bahasa Melayu](README.ms.md)

**介面語言（17 種）：** 英語、簡體中文、繁體中文、日語、韓語、西班牙語、德語、法語、俄語、義大利語、巴西葡萄牙語、阿拉伯語、印尼語、印地語、越南語、泰語及馬來語。

[![PyPI version](https://img.shields.io/pypi/v/epub-browser)](https://pypi.org/project/epub-browser/)
[![Python versions](https://img.shields.io/pypi/pyversions/epub-browser)](https://pypi.org/project/epub-browser/)
[![License](https://img.shields.io/github/license/dfface/epub-browser)](../../License.txt)

![PDF 在 EPUB Browser 共用閱讀器中顯示。](../releases/assets/v2.8.0-pdf-reader.png)

EPUB Browser 同時處理 `.epub` 與 `.pdf`，並提供兩種明確分工的部署模式：

| | `ssg` | `server` |
| --- | --- | --- |
| EPUB 與 PDF | 支援 | 支援 |
| 部署方式 | 靜態主機、Pages、物件儲存、Nginx | 持久化的私人閱讀服務 |
| 帳戶 | 無 | 本機帳戶 |
| 進度、標註、書架 | 僅目前瀏覽器 | SQLite 中已登入帳戶的資料 |
| 更新來源 | 再次執行 `ssg` | 重啟服務或使用 `--watch` |
| 執行期資料庫 | 無 | 必需 |

PDF 是一等書籍格式：第 1 頁對應 `chapter_0.html`，每一頁都會出現在目錄中，並由本機 PDF.js 在相同的 Library、書籍頁、閱讀介面、搜尋與標註流程中顯示。PDF 不支援的 AI 閱讀等功能會明確隱藏，閱讀期間不會存取 CDN。

需要可直接發布的普通靜態檔案時，請選擇 `ssg`；需要帳戶、跨裝置資料、書籍存取控制或自動監看來源時，請選擇 `server`。

## 專案概覽

### 示範站台

- **SSG 模式**：[epub-browser-test.yuhan.tech](https://epub-browser-test.yuhan.tech/)
- **Server 模式**：[epub.yuhan.tech](https://epub.yuhan.tech/) — 示範帳號與密碼皆為 `demo`。

### AI 原生閱讀（僅 Server 模式）

AI 閱讀會在原文上建立共享、可回看的學習層，而不是在書旁附上一份泛泛摘要：章前導讀、按需展開的章節總覽、貼近原文的證據解釋與段落提示、詞語／生僻字說明、章末的費曼式通俗講解，以及延伸思考問題都保持在閱讀流程中。結果以背景工作產生並儲存在 SQLite；有存取該書權限的讀者可共用結果，追問對話則僅屬於自己的帳戶。

AI 是 Server 專屬功能。管理員必須設定 OpenAI 相容供應商並逐一授權成員；選取的 EPUB 文字會傳送到該供應商，請僅在讀者同意此資料處理時啟用。SSG 永遠不含帳戶、AI 控制項、背景工作或供應商設定。

## 開始使用

### 需求與安裝

- Python 3.9 或更新版本
- 一個或多個 `.epub` 或 `.pdf` 檔案、含書籍的巢狀目錄，或 Calibre 風格的書庫目錄

從 PyPI 安裝可使用 SSG 與 Server 兩種模式：

```bash
pip install epub-browser

# 查看各模式的完整參數
epub-browser --help
epub-browser ssg --help
epub-browser server --help
```

若要透過 Docker 執行持久化 Server，請使用已發布的映像；主機不需要安裝 Python：

```bash
docker pull dfface/epub-browser:latest
```

### 快速開始

#### 產生靜態網站

```bash
epub-browser ssg /path/to/books \
  --output-dir /path/to/dist
```

請以 HTTP 提供 `dist/`，不要直接以 `file://` 開啟產生的頁面。若網站位於子路徑，加入 `--base-path /my-repository/`；這會改變產生的 URL，不會改變輸出資料夾。

#### 執行持久化 Server 書庫

```bash
epub-browser server /path/to/books \
  --server-dir /path/to/epub-browser-state \
  --watch
```

開啟 `http://127.0.0.1:8000/`。第一次造訪時建立初始管理員；在完成此一次性設定前，書庫不會被掃描或公開。使用 `--no-browser` 只會停止服務在本機自動開啟瀏覽器，不會關閉網頁介面。

## 資料與維運

### 資料、帳戶與存取邊界

每本書都有穩定的 `book_id`（網址與瀏覽器資料中亦稱 `book_hash`）。預設的 `--book-id-storage sidecar` 會在來源旁寫入身分檔且不改動原始位元組。EPUB 可用 `--book-id-storage embedded` 寫入 OPF 中繼資料；PDF 則一定回退到相鄰 sidecar。

Server 的 `--server-dir` 是權威狀態位置，包含 SQLite、快取與遷移備份。帳戶、書架、閱讀進度、標註、AI 結果與工作都存放在此。管理員可管理帳戶、角色、登入工作階段與受限書籍的授權；一般成員只能使用獲授權的書籍與自己的私人資料。請保護此目錄及其備份的檔案權限。

臨時測試可使用：

```bash
epub-browser server book.epub --ephemeral
```

臨時狀態會在關閉時刪除，因此每次啟動都會重新設定。正式服務請始終使用 `--server-dir`。

### Docker 與反向代理

容器化時，將書籍目錄以唯讀方式掛載，並將 `--server-dir` 掛載到持久化磁碟區。反向代理僅應轉送來自可信任代理的標頭；公開網路部署請使用 HTTPS，並依部署說明設定可信任代理與主機名稱。

完整 Docker Compose、CLI 參數、資料遷移、LAN／反向代理和疑難排解請見[英文完整 README](../../README.md)或[簡體中文完整 README](README.zh-CN.md)；命令列選項與兩種模式的行為在所有語言版本中相同。

## 開發與授權

### 貢獻與授權

歡迎提交 Issue 與 Pull Request。授權條款請見 [License.txt](../../License.txt)。
