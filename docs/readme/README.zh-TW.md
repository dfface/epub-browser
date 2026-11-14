# EPUB Browser

> **把書變成網站，打造自己的書庫。**
>
> 把 EPUB 和 PDF 書籍發布成靜態網站，也可以自行架設私人書庫，
> 支援帳號、進度同步、標註和可選的 AI 原生閱讀。

[瀏覽靜態書庫](https://epub-browser-test.yuhan.tech/) · [體驗私人書庫](#線上示範)

**README：** [English](../../README.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | [Español](README.es.md) | [Deutsch](README.de.md) | [Français](README.fr.md) | [Русский](README.ru.md) | [Italiano](README.it.md) | [Português (Brasil)](README.pt-BR.md) | [العربية](README.ar.md) | [Bahasa Indonesia](README.id.md) | [हिन्दी](README.hi.md) | [Tiếng Việt](README.vi.md) | [ไทย](README.th.md) | [Bahasa Melayu](README.ms.md)

<p align="center">
  <img src="https://raw.githubusercontent.com/dfface/epub-browser/main/epub_browser/assets/logo-lockup-color.png" alt="EPUB Browser 標誌" width="520">
</p>

[![PyPI version](https://img.shields.io/pypi/v/epub-browser)](https://pypi.org/project/epub-browser/)
[![Python versions](https://img.shields.io/pypi/pyversions/epub-browser)](https://pypi.org/project/epub-browser/)
[![License](https://img.shields.io/github/license/dfface/epub-browser)](../../License.txt)

![PDF 在 EPUB Browser 共用閱讀器中呈現，保留原始頁面、導覽、主題與閱讀工具。](../releases/assets/v2.8.0-pdf-reader.png)

EPUB Browser 不只是書籍轉換工具，更是一套可以發布到任何地方、也能自行託管的
完整閱讀平台。EPUB 與 PDF 共用書庫、書籍頁、目錄、閱讀模式、主題、閱讀進度和
標註流程。PDF 的每一頁都會對應閱讀器中的一個章節，由本機 PDF.js 在同一個閱讀
介面呈現 - 不需要獨立檢視器，也不依賴執行期 CDN。

## 目錄

- [專案概覽](#專案概覽)
  - [為什麼選擇 EPUB Browser](#為什麼選擇-epub-browser)
  - [技術棧](#技術棧)
  - [選擇 SSG 或 Server](#選擇-ssg-或-server)
  - [線上示範](#線上示範)
  - [AI 原生閱讀（僅 Server 模式）](#ai-原生閱讀僅-server-模式)
  - [Kindle 極簡模式](#kindle-極簡模式)
- [開始使用](#開始使用)
  - [選擇安裝方式](#選擇安裝方式)
  - [快速開始](#快速開始)
- [格式與閱讀體驗](#格式與閱讀體驗)
  - [來源與穩定的書籍 ID](#來源與穩定的書籍-id)
  - [PDF：一頁就是一個章節](#pdf一頁就是一個章節)
- [部署](#部署)
  - [SSG](#ssg)
  - [Server](#server)
  - [Docker](#docker)
- [參考與維運](#參考與維運)
  - [命令參考](#命令參考)
  - [閱讀資料與功能歸屬](#閱讀資料與功能歸屬)
  - [Server API 與 WebHooks](#server-api-與-webhooks)
  - [資料安全與疑難排解](#資料安全與遷移)
- [開發與授權](#開發與授權)
- [文件中心](../README.md)

## 專案概覽

### 為什麼選擇 EPUB Browser

- **發布到哪裡，都由你掌控。** 只要一個指令，就能為 Pages、物件儲存或 Nginx 產生
  完整靜態網站，也可以執行持久化 Server，使用帳號、書籍權限和 OIDC。應用程式資源、
  字型、PDF.js 和呈現器全部由本機提供，閱讀不必依賴 CDN。
- **EPUB 和 PDF，用的是同一套閱讀器。** 兩種格式共用書庫、書籍頁、目錄、回應式
  版面、三種閱讀模式、主題、全螢幕和閱讀進度。PDF 的每一頁都顯示在閱讀區中，支援縮放、
  文字層選取與標註，不必另外使用一套預覽工具。
- **既能找到那本書，也能找到那段話。** 書庫搜尋涵蓋中繼資料、標籤和拼音，並提供排序
  與分頁。Server 的 EPUB 全書搜尋會按章節分組傳回完整結果，可直接跳至反白顯示的原文
  段落。穩定的書籍 ID 讓續讀位置、標註和閱讀歷史始終與同一本書對應。
- **不只讀過，還要讀懂。** Server 模式下，EPUB 章節導讀、附證據連結的解說、心智圖
  和私人 Ask AI 都留在原文旁。反白、筆記、字典和百科適用於 EPUB 與具有文字層的
  PDF；Server 生字本還會記錄每個單字的出處與掌握狀態。
- **把閱讀累積成值得保留的記錄。** 巢狀書架、評分、書評、標註匯出、活動日曆、趨勢、
  單書統計和閱讀時間排行共同構成一份相互關聯的記錄。Server 會依帳號私密保存閱讀資料，
  並跨裝置同步。
- **提供的是閱讀服務，不只是檢視器。** Server 模式下，管理員可透過 Web 上傳書籍，
  也可使用監看目錄；透過可設定的 LRU 快取淘汰機制限制磁碟用量，管理成員與 AI 權限，
  還可透過 OpenAPI、PAT 和 WebHooks 整合。Kindle 極簡閱讀支援能力受限的裝置；Server
  也提供個人 Kindle 螢幕保護儀表板，內含時鐘、日曆、行程、備忘錄和番茄鐘。

![貼著 EPUB 原文產生的章節導讀，以及私人 Ask AI 抽屜。](assets/ai-native-reading.png)

*AI 原生導讀與私人提問始終對應原書內容。*

![私人閱讀洞察檢視，包含活動日曆和閱讀時間趨勢。](assets/reading-insights.png)

*閱讀洞察把主動閱讀變成一份容易理解、只屬於自己的歷史記錄。*

### 技術棧

EPUB Browser 刻意採用精簡的伺服器端呈現 Web 技術棧。安裝後的應用程式不使用 SPA
框架，也不需要 Node.js 執行環境：

| 層次 | 技術 | 職責 |
| --- | --- | --- |
| 前端 | 語意化 HTML、CSS、以 ES modules 和瀏覽器 API 為基礎的 VanillaJS | SSG 與 Server 共用同一套回應式介面 |
| CLI 與 Server | Python 3.9+、Starlette、Uvicorn | 轉換命令、需驗證身分的頁面、API 與背景工作 |
| 資料 | SQLite 與可重建的 JSON 內容快取 | 使用者狀態與 EPUB/PDF 衍生內容彼此分離 |
| 書籍格式 | lxml、pypdf、pypdfium2、PDF.js | 統一採嚴格解析優先的 EPUB 解析/清理、PDF 中繼資料/封面和瀏覽器本機呈現 |
| 離線與資源 | Service Worker、附雜湊值的不可變資源、鎖定版本的第三方相依套件 | 不依賴執行期 CDN 的自包含交付 |
| 發布 | PyPI、Docker、一般靜態託管 | 同一份程式碼可產生 SSG，也可執行持久化 Server |
| 可選 AI | OpenAI 相容 API，以及在本機呈現的 Markdown、KaTeX、Mermaid | 僅限 Server 模式的 EPUB 學習層 |

Node.js 只供維護者執行瀏覽器端測試，不屬於讀者端的正式執行環境。

### 選擇 SSG 或 Server

同一套來源處理與頁面範本支撐兩種明確的部署模式。選擇依據是閱讀資料要存放在哪裡，
而不是書籍格式：

| 能力 | `ssg` | `server` |
| --- | --- | --- |
| EPUB 與 PDF | 支援 | 支援 |
| 交付方式 | 以原子方式產生靜態 HTML/資源，可部署至 Pages、物件儲存或 Nginx | 動態傳回已驗證身分的頁面，背後使用可替換的內容快取 |
| 帳號與存取控制 | 無 | 管理員/成員帳號、受限書籍授權、Session 與 CSRF 防護 |
| OIDC 單一登入 | 不包含 | 通用 Provider、現有帳號連結與可選的成員帳號自動建立 |
| 進度、標註、書架 | 儲存在目前瀏覽器 | 依已登入帳號同步至 SQLite |
| 評分、書評、閱讀時段 | 不產生 | 各帳號私密保存，並提供閱讀洞察 |
| 來源更新 | 再次執行 `ssg` | 重新啟動、重新掃描或使用 `--watch` |
| 管理後台、標籤、OpenAPI、WebHooks | 不包含 | 包含 |
| AI 閱讀與 Ask AI | 不包含 | 完成設定並明確授權後可用於 EPUB；PDF 中隱藏 |
| 執行期資料庫 | 無 | 持久化模式必需 |
| 適用情境 | 公開/靜態託管、離線套件、簡單的個人發布 | 私人書庫、多裝置或多人閱讀、自動化與存取管理 |

如果產物必須是一般靜態檔案，請使用 `ssg`；如果讀者需要帳號、跨裝置資料、存取控制或自動處理來源異動，請使用 `server`。

### 線上示範

- **SSG 模式**：[epub-browser-test.yuhan.tech](https://epub-browser-test.yuhan.tech/)
- **Server 模式**：[epub.yuhan.tech](https://epub.yuhan.tech/) - 使用者名稱 `demo`，密碼 `demo`。

### AI 原生閱讀（僅 Server 模式）

對於 EPUB 書籍，Server 模式可提供章節導讀、附證據連結的解說、心智圖、反思問題
和私人 Ask AI 抽屜，同時不讓讀者離開原文。結果仍受書籍權限限制，成員必須獲得明確
授權；SSG 不包含任何 AI 控制項、工作、帳號資料或 Provider 設定。PDF 則明確隱藏
AI 閱讀與 Ask AI。

完整互動模型請見 [AI 原生閱讀指南](../ai-native-reading.md)，呈現與網路安全邊界請見
[本機富文字呈現器說明](../third-party-ai-renderers.md)。

### Kindle 極簡模式

舊款 e-Ink Kindle（以及任何功能受限的瀏覽器）都能使用一套零相依的極簡閱讀介面。透過
`--kindle` 啟用：

- SSG：`epub-browser ssg --kindle -o output/ SOURCE...`
- Server：`epub-browser server --kindle --server-dir data SOURCE...`

每本 EPUB 書籍（不含 PDF）都會增加三個頁面：

- 極簡書架 `/kindle-library.html`
- 書籍頁 `/book/<id>/kindle.html`
- 章節頁 `/book/<id>/kindle_chapter_N.html`

這些頁面針對 e-Ink 調校：極簡標記、純 CSS 主題、相容 ES5 的指令碼、無 Service
Worker、無框架。即使完全不執行 JavaScript 也能閱讀；主題切換（淺色 / 米黃 / 深色）、
字級調整（A- / A+）與介面本地化，都是以純 HTML 為基礎，再疊加輕量內嵌指令碼。

每個頁面都提供主題與字級控制項（頁首以及章節頁尾各一組）、目錄導覽、上一章/下一章，
以及從已儲存進度恢復的“繼續閱讀”連結。

閱讀進度會因模式而異：

- **SSG：** 進度儲存在目前瀏覽器的 Cookie 中 - 僅限本機，不需帳號。
- **Server：** 進度與閱讀心跳會依已登入帳號同步至 SQLite。Kindle 介面只負責讀取和回報：
  記錄目前章節、回報心跳並呈現唯讀書架，絕不提供閱讀洞察或內容管理。

所有 Kindle 介面都會執行存取控制。對於可見性受限的書籍，未授權使用者在極簡書架中
看不到該書，存取書籍頁、章節頁和進度 API 時會收到 403。

支援的瀏覽器（UA 包含 `Kindle/`、`Arora/` 等）會從完整閱讀器自動重新導向至極簡頁面；
上述 URL 也可直接開啟。因此，效能較低或 JavaScript 功能受限的裝置也能透過極簡模式正常閱讀。

## 開始使用

### 選擇安裝方式

EPUB Browser 提供兩種安裝方式。兩者都接受一或多個 `.epub` 或 `.pdf` 檔案、
巢狀目錄，或 Calibre 風格的書庫目錄。

| 安裝方式 | 適用情境 | 主機需求 |
| --- | --- | --- |
| PyPI | SSG 或 Server 模式 | Python 3.9 或更新版本 |
| Docker | 持久化 Server 模式 | Docker Engine；映像已包含 Python |

#### PyPI（SSG 或 Server）

安裝命令列應用程式：

```bash
pip install epub-browser
```

查看各模式的命令參考：

```bash
epub-browser --help
epub-browser ssg --help
epub-browser server --help
```

#### Docker（Server）

已發布的 [`dfface/epub-browser`](https://hub.docker.com/r/dfface/epub-browser)
映像會執行 Server 模式，主機不需安裝 Python：

```bash
docker pull dfface/epub-browser:latest
```

評估目前版本可使用 `latest`；正式環境若要可重複部署，請固定使用特定版本編號的標籤。
必要的書籍與狀態掛載、Compose 快速開始、首次設定和網路指引請見 [Docker](#docker)。

### 快速開始

#### 產生靜態網站

```bash
epub-browser ssg /path/to/books \
  --output-dir /path/to/dist
```

請透過 HTTP 提供 `dist/`。不支援透過 `file://` 直接開啟產生的頁面，因為瀏覽器儲存空間、模組、資訊清單和 Service Worker 都需要 HTTP 來源。

如果網站託管在 URL 前綴之下，請將公開路徑與檔案系統目的地分開設定：

```bash
epub-browser ssg /path/to/books \
  --output-dir /path/to/dist \
  --base-path /my-repository/
```

`--base-path` 會改變產生的 URL，不會改變檔案寫入位置。設為 `/my-repository/` 後，連結、圖示、資訊清單、書籍中繼資料和 Service Worker 項目都會使用此前綴，檔案仍直接寫入 `dist/`。

#### 執行持久化 Server 書庫

```bash
epub-browser server /path/to/books \
  --server-dir /path/to/epub-browser-state \
  --watch
```

開啟 `http://127.0.0.1:8000/`。首次造訪時，EPUB Browser 會引導你建立初始管理員。完成這項一次性設定之前，系統不會掃描或公開書庫。

如果選擇 Docker，請略過上述 Python 命令，繼續查看
[Docker Compose 快速開始](#docker-compose)。

## 格式與閱讀體驗

### 來源與穩定的書籍 ID

每個位置參數 `SOURCE` 都可以是 EPUB 檔案、PDF 檔案或目錄；目錄會以遞迴方式搜尋。
同一個指令可以傳入多個來源：

```bash
epub-browser server book.epub /srv/library /srv/periodicals \
  --server-dir /srv/epub-browser \
  --watch
```

每本書會獲得穩定的 `book_id`，在產生的 URL 和瀏覽器資料中也稱為 `book_hash`。一般 CLI 預設為：

```bash
--book-id-storage sidecar
```

Sidecar 模式會在來源旁寫入可見的身分檔，例如 `BOOK.epub.epub-browser.json` 或 `BOOK.pdf.epub-browser.json`，不會改變來源位元組。Sidecar 包含穩定 ID 和經過驗證的 SHA-256 來源指紋。

若要把 ID 寫入 EPUB OPF 中繼資料或 PDF 文件資訊字典，請為整次命令選擇 embedded 儲存方式：

```bash
--book-id-storage embedded
```

Embedded 模式可能在轉換前重建 EPUB ZIP，或追加 PDF 中繼資料更新。如果 PDF 無法更新且來源未改變，EPUB Browser 會把同一個 ID 儲存到相鄰的 sidecar；已簽署、加密和唯讀 PDF 也適用。當 ID 不一致、使用中的來源有重複 ID、載體無效，或必要載體無法寫入時，EPUB Browser 會停止。

切換儲存方式時，EPUB Browser 會把現有 ID 複製到所選載體，並保留另一個有效載體。v2.0.4 中已有的嵌入式 ID 會複製到預設 sidecar，不會重寫 EPUB。無論是否更新中繼資料，SSG 與 Server 都會交付 PDF 來源逐位元組一致的副本。

### PDF：一頁就是一個章節

兩種部署模式都支援 PDF。閱讀器把 PDF 的每一頁視為一般的 EPUB Browser 章節，
因此現有的書籍頁、章節導覽、目錄、分頁、連續閱讀、進度、閱讀時段、標註、字典和
百科會繼續共用同一套 UI 與資料模型：

| PDF 概念 | SSG | Server |
| --- | --- | --- |
| 第 1 頁 URL | `chapter_0.html` | `/book/<book-id>/chapter_0.html` |
| 第 N 頁 URL | `chapter_{N-1}.html` | `/book/<book-id>/chapter_{N-1}.html` |
| 頁碼標籤和目錄 | 在本機產生；列出每一頁 | 從 PDF 中繼資料快取呈現；列出每一頁 |
| 內嵌大綱 | 在目標頁的目錄項目顯示大綱標記 | 同樣顯示大綱標記，不會刪除或重排頁面項目 |
| 捲動與分頁/翻頁 | 靜態章節頁面框架和本機 PDF.js | 動態共用章節頁面框架和本機 PDF.js |
| 反白、筆記、字典、百科 | 有文字層時使用共用的瀏覽器本機元件 | 有文字層時使用共用且需驗證身分的元件 |
| 原始 PDF 位元組 | 靜態書籍產物中只有一個 `document.pdf` | 僅限 Session 存取、支援 Range 的快取文件路由 |

可見標籤和 PDF.js 中的頁碼從 1 開始；URL、狀態、API 和 SQLite 中的章節索引從 0
開始。因此 PDF 第 1 頁始終是 `chapter_0.html`。正規化目錄會為每一頁保留一個 `Page N`
項目；PDF 內嵌大綱的標題會作為大綱標記附加到目標項目，同一頁有多個
大綱標記時也都會保留。

SSG 會寫出一個 `document.pdf`，並為每頁寫出一個 `chapter_<index>.html` 頁面框架。
SSG 產物不含 Session 指令碼、`/api/*` 呼叫、同步標註資料或 Server 相依項目。Server
會把完整且逐位元組一致的來源儲存為 `book/<book-id>/pdf/document.pdf`，絕不拆頁或重寫；
相同的章節頁面框架由 Server 根據 PDF 中繼資料動態呈現。來源改變時，PDF 快取（文件、
中繼資料和衍生封面）會失效並完整更新，不會混用新舊頁面。

Server 的原始文件端點僅接受 Session：
`GET`/`HEAD /api/books/<book-id>/document`。它會檢查身分驗證、書籍可見性、PDF 格式和
來源/快取指紋，再支援範圍受限的單一 Range 回應，並設定 `ETag`、`Accept-Ranges`、
private 快取、`nosniff` 和 inline PDF disposition。端點不會公開絕對路徑，不接受 PAT
驗證，也不列入 PAT/OpenAPI 介面範圍。SSG 只有本機 `document.pdf`，沒有原始文件 API。

具有可用 PDF.js 文字層的 PDF 會原樣沿用現有的文字選取彈出選單與標註元件，提供反白、
筆記、字典和百科。標註儲存、擁有者、匯出、列表和深層連結繼續共用；不會新增 PDF 專用
標註資料表或設定 UI。掃描版或純圖片 PDF 仍可閱讀，但沒有可用文字層時，以選取範圍為基礎的
反白、筆記、字典、百科和文件搜尋會明確標示為無法使用。跨頁選取的內容仍可複製，但標註和
查詢動作會顯示已本地化的不支援訊息；單頁內的選取功能則繼續正常運作。

PDF.js 不是第二套檢視器外殼。建置或發布前，請先補齊並驗證鎖定版本的第三方資源：

```bash
python3 tools/sync_vendor_assets.py fetch
python3 tools/sync_vendor_assets.py verify
```

接著，應用程式會在執行期提供本機附雜湊值的 PDF.js 模組和 Worker 資源，絕不從
CDN 取得。圖片燈箱使用鎖定版本的 GLightbox 相依套件；Fancyapps/Fancybox 不是
執行期相依套件，也不會隨專案重新散布。鎖定資源與發布流程請見
[third_party/README.md](../../third_party/README.md)。

## 部署

### SSG

SSG 會先在相鄰的 staging 目錄建置完整快照並驗證，然後替換目標目錄。任何轉換失敗時，原有目標目錄保持不變。產生的結果不包含 Server 資料庫、遷移狀態、帳號頁面或執行期快取中繼資料。

SSG 刻意保持本機化且不包含帳號體系：

- 閱讀進度和標註使用目前來源的瀏覽器儲存空間。
- 書架支援本機 JSON 匯入和匯出，沒有雲端同步動作。
- 不包含登入、帳號設定、Server API 或依使用者身分而異的控制項。
- 儲存位置固定為瀏覽器本機，不會顯示為設定選項。
- 靜態產物包含讓資源可離線使用所需的 Service Worker。

應用程式所需的全部 JavaScript、CSS、字型、圖示都會包含在產物中。唯一的可選網路請求請見 [自包含與網路行為](#自包含與網路行為)。

### Server

#### 首次設定、帳號與權限

使用全新的持久化狀態目錄時，一般頁面會重新導向至 `/setup`。建立初始管理員之前，API、事件串流、產生的資源和書籍都會傳回需要設定的回應。開放連接埠前，請透過 loopback 或其他可信任的私人路徑完成設定：第一個成功提交設定的人會取得管理員帳號。

設定完成後：

- 不開放公開註冊，使用者由管理員建立和管理。
- 帳號角色為 `administrator` 或 `member`。
- 一般書籍對所有已驗證身分的帳號可見。
- 受限書籍只對管理員和明確選取的使用者可見。
- 每位使用者各自擁有書架、進度、標註和使用中的工作階段。
- 使用者可以變更自己的密碼，也可以撤銷自己的工作階段。
- 管理員可以管理使用者、角色、密碼、工作階段和書籍授權。
- 工作階段使用 HttpOnly Cookie、CSRF 防護和 30 天滑動有效期。

#### OIDC 單一登入與帳號連結

Server 模式可接入一個通用 OpenID Connect（OIDC）Provider，包括 Authelia、
Keycloak、Authentik 和其他相容服務。在 **管理後台 → OIDC 登入** 中，填寫向讀者顯示的
Provider 名稱、Issuer URL、用戶端 ID、用戶端密鑰、完全一致的重新導向 URI、Scopes
和使用者名稱 Claim。EPUB Browser 使用 Discovery 和採用 S256 PKCE 的 Authorization
Code 流程，驗證已簽署的 ID Token，並且只以 `(issuer, sub)` 識別外部帳號；電子郵件和
使用者名稱 Claim 只是顯示或建立帳號時的參考資訊，絕不作為帳號的身分識別依據。

請在 Provider 中註冊這個完全一致的回呼網址，包含通訊協定和主機名稱：

```text
https://reader.example.com/auth/oidc/callback
```

現有使用者可先以本機帳號登入，再從“帳號設定”連結 Provider。如果外部身分尚未關聯
本機帳號，系統會要求使用者輸入一次現有本機帳號的使用者名稱和密碼。可選的自動建立功能
會產生沒有密碼的成員帳號，絕不會匯入管理員角色。請先讓現有使用者完成連結：過早啟用
自動建立可能產生**重複的本機帳號**。即使停用本機成員密碼登入，**本機管理員**密碼登入
仍始終可用。請確認這組復原憑證可用，並妥善保護。系統不會執行 Provider 登出，也不會
儲存 Provider 的 access/refresh token。

Authelia 需要在其 OIDC Provider 區段設定 confidential client。下列片段使用刻意
虛構的值，並假設 Authelia 必要的 Provider 金鑰和原則已設定完成。請在 Authelia 中
儲存高強度隨機用戶端密鑰的雜湊值，然後只在 EPUB Browser 輸入一次對應的原始密鑰：

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

在 EPUB Browser 中使用 Issuer `https://auth.example.com`、用戶端 ID `epub-browser`、
Scopes `openid profile email` 和使用者名稱 Claim `preferred_username`。儲存時會即時
執行 Discovery 與能力驗證；失敗時，先前的設定仍然有效。

#### 設定與管理 AI 閱讀

管理員在 **管理後台** 設定 AI 閱讀，該頁面緊接使用者管理，位於書籍管理之前。頁面會把
OpenAI 相容 Base URL、API Key、模型、逾時、脈絡預算、並行上限和預設每日
Provider 呼叫額度儲存到 Server 的 SQLite 資料庫。AI 預設對成員關閉；管理員必須逐一
授予成員存取權，並可設定個人每日額度（`0` 表示無限制）。

章節學習層與整書點評會依適用語言共用，後續對話則由各帳號私有。結果、工作狀態、
自訂標籤、書籍閱讀分類和私人追問都儲存在 SQLite。模型設定改變後，舊結果仍然可用，
直到管理員明確重新產生。

當讀者要求 AI 導讀或提出問題時，選取的 EPUB 正文和壓縮後的對話脈絡會傳送給已設定的
外部 Provider。除非讀者已獲准把這些內容傳送給該 Provider，否則請勿啟用此功能。
API Key 絕不會傳回瀏覽器，也不會透過 API 公開；請據此妥善保護 Server 狀態目錄。

無人值守的首次啟動可提供使用者名稱和密碼檔：

```bash
epub-browser server /path/to/books \
  --server-dir /path/to/state \
  --admin-username admin \
  --admin-password-file /run/secrets/epub-browser-admin-password \
  --no-browser
```

密碼檔權限應為 `0600`。EPUB Browser 會移除一個結尾換行字元、儲存 Argon2id 雜湊值，且絕不印出密鑰。設定不完整、檔案為空或無法讀取時，啟動會停止。首次設定完成後，後續啟動不會再讀取這份引導密鑰。

對應的環境變數為 `EPUB_BROWSER_ADMIN_USERNAME` 和 `EPUB_BROWSER_ADMIN_PASSWORD_FILE`。只有未設定密碼檔時，`EPUB_BROWSER_ADMIN_PASSWORD` 才作為明文後備。CLI 的密碼檔路徑優先於環境變數中的密碼來源。

#### 瀏覽器啟動與記錄

預設情況下，Server 會在 HTTP 接聽器啟動後，嘗試開啟作業系統的預設瀏覽器。`--no-browser` 會阻止這項本機啟動動作，**不會關閉 Web 介面，也不會禁止瀏覽器存取**；它只會抑制本機的 `webbrowser.open(...)` 呼叫。Docker、systemd、SSH 工作階段、無顯示介面的主機和指令碼都應使用此選項。

預設使用 `--log-level error`，CLI 只會輸出錯誤，避免例行訊息或警告打斷終端機進度顯示。互動式終端機會印出一次繫結 URL；以非互動方式執行 Docker 或服務時，則不輸出例行訊息。使用 `--log-level warning` 可包含警告，使用 `--log-level info` 可啟用維運記錄和 HTTP 存取記錄，使用 `--log-level debug` 可取得最詳細的資訊。`--log` 保留為 `--log-level info` 的相容別名。

首次掃描和監看掃描的進度會顯示在 Web 介面，而不是終端機 `tqdm`。成功摘要會自動關閉；失敗資訊會保留到手動關閉為止。使用 `--watch` 時，修正或替換來源就會啟動另一次掃描，不需手動重試。

#### 持久化與暫時狀態

持久化 Server 模式必須使用 `--server-dir`。一次性執行可改用 `--ephemeral`：

```bash
epub-browser server book.epub --ephemeral
```

暫時狀態會在關閉時刪除。由於每次執行的資料庫都是全新的，除非提供無人值守的引導憑證，否則也要重複完成設定。

持久化目錄配置：

```text
<server-dir>/
├── .server.lock                 # 可重複使用的處理程序鎖定中繼資料
├── data/
│   ├── epub-browser.db          # 權威帳號、書籍、授權和閱讀資料
│   ├── migration-state.json     # 可安全重新啟動的遷移狀態
│   └── backups/                 # 已驗證的遷移前資料庫副本
└── cache/
    ├── catalog.json             # 產生快取的狀態
    ├── public/                  # 對外提供的應用程式和轉換後書籍
    └── staging/                 # 可替換的轉換工作目錄
```

只有 `data/` 是權威資料；`cache/` 可以刪除，之後會重建。升級和替換容器時必須保留 `data/`。處理程序獨佔由作業系統鎖定機制控制，正常關閉後可能留下的 `.server.lock` 只是診斷中繼資料。

持久化的 `data/epub-browser.db` 必須位於本機檔案系統；共用或網路檔案系統不支援 WAL 並行。已驗證的備份保存在 `data/backups/`，其中包含所有已提交的 WAL 資料。

#### 區域網路與反向代理

Server 預設繫結 `127.0.0.1:8000`。若要在可信任的區域網路中使用：

```bash
epub-browser server /path/to/books \
  --server-dir /path/to/state \
  --watch \
  --host 0.0.0.0 \
  --port 8080 \
  --no-browser
```

請勿把內建 HTTP Server 直接公開到網際網路。請在反向代理終止 TLS、實施網路存取控制，並啟用安全 Cookie。

若要讓使用中的工作階段和登入速率限制在反向代理後方記錄真實用戶端 IP，請設定**與 Server 直接連線的代理網段**（不是公開用戶端網段）：

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

每個直接連線的代理位址或網段都要重複傳入一次 `--trusted-proxy-cidr`。只有直接對等端位於上述任一 CIDR 的請求，Server 才會採用其 `X-Forwarded-For`；其他對等端只記錄直接位址。Uvicorn 的轉送位址處理已停用，因此 `Forwarded` 和 `FORWARDED_ALLOW_IPS` 都不能擴大這個信任邊界。只有瀏覽器透過 HTTPS 存取服務時，才使用 `--cookie-secure`。

### Docker

映像以持久化 Server 模式執行，預設參數如下：

- `/app/Library` 作為書籍來源
- `/app/EpubBrowserFiles` 作為持久化狀態
- `--watch`
- `--no-browser`
- `--host 0.0.0.0 --port 80`
- `--book-id-storage embedded`
- `--kindle`

嵌入式身分可能更新 EPUB 或 PDF 檔案，因此書庫應以可讀寫方式掛載。Server 狀態也必須以可讀寫方式掛載，並在替換容器時保留：

```bash
docker run -d \
  --name epub-browser \
  -p 127.0.0.1:8080:80 \
  -v /path/to/books:/app/Library:rw \
  -v /path/to/epub-browser-state:/app/EpubBrowserFiles \
  dfface/epub-browser:latest
```

變更連接埠繫結或代理規則之前，請先造訪 `http://127.0.0.1:8080/setup`。

#### Docker Compose

儲存庫提供 [docker-compose.yml](../../docker-compose.yml)，供偏好 Compose 的使用者使用。在原始碼工作目錄中建立 `Library/`，把 EPUB 或 PDF 書籍放進去，然後執行：

```bash
docker compose up -d --build
```

它只發布 `127.0.0.1:8080`，來源 EPUB/PDF 書籍保存在 `./Library`，Server 狀態持久化到 `./EpubBrowserFiles`。檔案中刻意完整列出 Server `command`，因此可以直接新增部署專用參數，不必替換映像的隱含預設值。請造訪 `http://127.0.0.1:8080/setup` 完成一次性設定。遠端存取時，應保留 loopback 繫結，並在前方部署具身分驗證的 TLS 反向代理。

無人值守設定：

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

首次成功啟動後，可以移除一次性密鑰掛載。只有每本 EPUB 都已包含有效且相符的嵌入式 ID 時，書庫才能以唯讀方式掛載。把 ID 嵌入書籍時，現有 sidecar 會保留。

只有匯入舊版書架 JSON 時才掛載 `/app/SyncData:ro`：

```bash
-v /path/to/legacy-sync:/app/SyncData:ro
```

範例將發布連接埠繫結到 loopback，使容器服務只能從主機本機存取。遠端存取時，請使用 TLS 反向代理，設定其實際容器網路 CIDR，並加入 `--cookie-secure`。

## 參考與維運

### 命令參考

#### `epub-browser ssg SOURCE [SOURCE ...]`

| 參數 | 意義 |
| --- | --- |
| `--output-dir DIR`, `-o DIR` | 必填；原子式靜態快照的目的目錄。 |
| `--base-path PATH` | 公開 URL 前綴，預設 `/`；必須以 `/` 開頭和結尾。 |
| `--book-id-storage sidecar\|embedded` | 每個所選來源的穩定身分載體，預設 `sidecar`。 |
| `--kindle` | 為舊式 e-Ink Kindle 產生零相依極簡頁面，並把 Kindle WebKit 瀏覽器重新導向至這些頁面；預設關閉。 |
| `--log` | `--log-level info` 的相容別名。 |
| `--log-level debug\|info\|warning\|error` | 維運記錄的詳細程度；預設 `error`，不輸出例行轉換訊息和警告。 |

#### `epub-browser server SOURCE [SOURCE ...]`

`--server-dir` 與 `--ephemeral` 必須且只能選擇一個。

| 參數 | 意義 |
| --- | --- |
| `--server-dir DIR` | 持久化權威資料與可替換快取的根目錄。 |
| `--ephemeral` | 使用一次性狀態；與 `--server-dir` 互斥。 |
| `--watch`, `-w` | 監看來源，並同步處理新增、更新、移動和刪除。 |
| `--host ADDRESS` | 繫結位址，預設 `127.0.0.1`。 |
| `--port PORT`, `-p PORT` | 繫結連接埠，預設 `8000`。 |
| `--no-browser` | 不啟動本機預設瀏覽器；Web 介面仍可存取。 |
| `--log` | `--log-level info` 的相容別名。 |
| `--log-level debug\|info\|warning\|error` | 維運記錄的詳細程度；預設 `error`。`info` 和 `debug` 會啟用 HTTP 存取記錄。 |
| `--legacy-sync-dir DIR` | 啟動遷移時讀取舊版書架 JSON。 |
| `--book-id-storage sidecar\|embedded` | 每個所選來源的穩定身分載體，預設 `sidecar`。 |
| `--admin-username NAME` | 無人值守設定所用的初始管理員名稱；後備為 `EPUB_BROWSER_ADMIN_USERNAME`。 |
| `--admin-password-file FILE` | 優先使用的初始密鑰檔；後備為 `EPUB_BROWSER_ADMIN_PASSWORD_FILE`，未設定檔案時再使用 `EPUB_BROWSER_ADMIN_PASSWORD`。 |
| `--trusted-proxy-cidr CIDR` | 可重複指定的直接代理網路信任邊界，用於安全剖析 `X-Forwarded-For` 中的用戶端 IP。 |
| `--cookie-secure` | 僅透過瀏覽器端 HTTPS 傳送工作階段 Cookie。 |
| `--kindle` | 為舊式 e-Ink Kindle 提供零相依極簡頁面，並把 Kindle WebKit 瀏覽器重新導向至這些頁面；預設關閉。 |

#### 舊版 v1 語法

整個 v2 主要版本週期都支援舊版語法：

| v1 命令 | v2 對應 |
| --- | --- |
| `epub-browser BOOKS` | `epub-browser server BOOKS --ephemeral` |
| `epub-browser BOOKS --output-dir STATE` | `epub-browser server BOOKS --server-dir STATE` |
| `epub-browser BOOKS --no-server --output-dir DIST` | `epub-browser ssg BOOKS --output-dir DIST` |
| `--sync-dir DIR` | `server --legacy-sync-dir DIR` |

舊版專用 `--keep-files` 會保留暫時 Server 目錄；持久化 Server 目錄本來就會永久保留。指定 `--log` 時，相容轉接器會印出等價的 v2 命令，否則保持安靜。

### 閱讀資料與功能歸屬

- 遞迴探索 EPUB/PDF 和 Calibre 書庫、中繼資料標籤、搜尋與拼音搜尋
- 回應式書庫、書籍詳情和章節閱讀介面
- 捲動、翻頁、連續閱讀、可調內容寬度、字型、自訂 CSS、主題和純粹閱讀模式
- 反白、筆記、標註瀏覽、巢狀書架群組、標籤和 JSON 匯入/匯出
- 介面支援英文、簡體中文、繁體中文、韓文、日文、西班牙文、德文、法文、俄文、
  義大利文、巴西葡萄牙文、阿拉伯文、印尼文、印地文、越南文、泰文和馬來文
- 適合 Kindle/Silk 瀏覽器的電子閱讀器行為；需要較多瀏覽器功能支援的功能可能會簡化

| 資料 | SSG | Server |
| --- | --- | --- |
| 閱讀進度 | 瀏覽器本機 | 已驗證身分的使用者的 SQLite 記錄 |
| 反白與筆記 | 瀏覽器本機 | 已驗證身分的使用者的 SQLite 記錄 |
| 私人評分、書評與閱讀時段歷史 | 不存在 | 已驗證身分的使用者的 SQLite 記錄 |
| 書架 | 瀏覽器本機；匯入/匯出 | 已驗證身分的使用者的版本化雲端文件；自動儲存 |
| 帳號與工作階段 | 不存在 | `<server-dir>/data` 下的 SQLite |
| 書籍授權 | 不存在 | `<server-dir>/data` 下的 SQLite |

Server 不提供“本機/雲端”儲存選擇器：已驗證身分的閱讀資料始終儲存在 Server。詳細的私人閱讀時段歷史絕不會輸出到 SSG。SSG 從不探測 Server API，始終使用目前瀏覽器來源的本機儲存空間。

### 自包含與網路行為

應用程式的閱讀功能是自包含的：所需 JavaScript、CSS、字型、圖示、資訊清單和轉換後的 EPUB 資源全部由本機提供，沒有 CDN 執行期相依項目。封鎖網際網路對外存取不會妨礙首次設定、登入、瀏覽、閱讀、標註、進度、書架使用、後台管理或來源轉換。

頁尾可能向 GitHub Releases API 發出一個可選請求，檢查是否有新版 EPUB Browser。請求失敗、被封鎖或離線使用只會隱藏更新提示。

SSG 會發布靜態 Service Worker。Server 會刻意停用並清除整個來源範圍的 Service Worker，避免某個帳號收到另一個帳號快取過的受保護內容。

### Server API 與 WebHooks

Server 帳號可在“帳號設定”中建立具範圍限制的個人存取權杖。外部用戶端透過 `Authorization: Bearer <PAT>` 使用版本化的 `/api/v1/*` API；瀏覽器 Cookie 無法驗證這些路由。API 涵蓋可見書籍與章節內容、權杖擁有者的書架、進度、標註和書評；具 `admin:data:read` 的管理員 PAT 還能唯讀存取跨使用者資料。

OpenAPI 3.1 文件位於 `/openapi.json`，已登入使用者可在 `/api-docs` 瀏覽本機 API 參考。例如：`curl -H 'Authorization: Bearer …' https://reader.example/api/v1/books`。章節詳情預設傳回已清理的 HTML，加入 `?format=text` 可傳回純文字。

列表端點會傳回 `items` 和 `next_cursor`。`limit` 預設為 24，最大為 100。保持篩選條件不變，把 `next_cursor` 作為 `cursor` 傳入即可取得下一頁。游標為 null 時表示最後一頁。例如，使用 `/api/v1/me/annotations?book_id=BOOK_ID&chapter_index=0&fields=id,text,note` 可取得一個 EPUB 章節或 PDF 頁面中指定的標註欄位。查詢篩選條件和支援的欄位列於 OpenAPI 文件。

生字表預設使用相同的列表格式。仍使用舊版 `words` 回應的用戶端可傳入 `page=1` 或 `page_size`，選擇舊版分頁格式。

管理員可在“管理後台”管理 WebHook 端點。密鑰只會在建立或輪換時顯示；投遞會簽署、持久化，並在收到非 2xx 回應時重試。書評事件包含 ID 和動作時間戳記，絕不包含評分或書評正文。

### 資料安全與遷移

升級持久化 Server 安裝前，請備份來源 EPUB/PDF 書籍和 `<server-dir>/data`。替換容器時，必須保留同一個持久化狀態磁碟區。

啟動遷移會自動執行，且可安全重新啟動。它會驗證舊版資料庫、建立備份、升級副本、把符合條件的舊版書架/進度/標註資料匯入待建立的初始管理員帳號，並只在成功檢查點之後淘汰可替換的舊版公開產物。一般請求絕不會掃描舊版同步目錄。遇到資料庫損毀、密碼雜湊無效、舊版資料庫狀態不明確或 ID 衝突時，啟動都會直接停止，不會嘗試猜測或覆寫。

遷移後根目錄的 `epub-browser.db` 或 `annotations.db` 會保留為敏感的非權威復原副本；`data/epub-browser.db` 才是權威資料庫，Server 請求不會使用保留的根目錄檔案。請讓復原副本保持私密。只有在 Server 已停止、權威資料庫與記錄的備份均已驗證，且不再需要回復至 v1 時，才可手動刪除；EPUB Browser 絕不會自動刪除它。

如果舊版根目錄同時包含 `epub-browser.db` 和 `annotations.db`，啟動會停止，且原檔案保持不變。備份、回復、快取重建和衝突復原請見 [遷移至 v2](../migration-v2.md)。

### 疑難排解

#### 命令已啟動，但沒有開啟瀏覽器

在有圖形介面的本機執行時可移除 `--no-browser`，也可以手動開啟印出的/繫結的 URL。在 Docker、systemd、SSH 和非互動工作階段中，自行開啟 URL 是預期行為。

#### CLI 看起來沒有輸出

未使用 `--log` 時保持安靜是刻意設計，在非互動環境中尤其如此。加入 `--log` 可查看維運和存取詳情。Server 掃描進度會顯示在 Web 介面中。

#### Docker 無法寫入穩定 ID

映像預設使用嵌入式身分。請以可讀寫方式掛載 `/app/Library`，或預先嵌入有效且相符的 ID。只有更適合使用可寫入 sidecar 載體時，才透過自訂命令改用 `--book-id-storage sidecar`。

#### 產生的 SSG 網站在子路徑下出現失效連結

使用正規化的 `--base-path`（例如 `/reader/`）重新產生，並設定靜態主機在相同前綴下提供產物。

#### 升級後 Server 拒絕啟動

查看第一則遷移或驗證錯誤記錄，保留資料和來源檔案，並參閱 [docs/migration-v2.md](https://raw.githubusercontent.com/dfface/epub-browser/main/docs/migration-v2.md)。請勿刪除權威 `data/` 目錄來繞過錯誤。

## 開發與授權

### 參與貢獻

歡迎在 [dfface/epub-browser](https://github.com/dfface/epub-browser) 提交 Issue 和 Pull Request。有用的問題回報應包含實際執行的命令、瀏覽器/裝置、重現步驟、相關記錄，以及在可合法分享時附上的 EPUB 或 PDF。

#### 維護者的架構約定

修改內容處理、頁面範本、快取、權限、資源或部署行為之前，請先閱讀
[AGENTS.md](../../AGENTS.md)。其中定義了 EPUB/PDF 格式邊界、SSG/Server 職責、
獨立快取修訂、執行期 i18n 要求、安全檢查和必要驗證。*reader chapter*、
*reading window*、*reading stage*、*content cache* 等共用產品術語請見
[CONTEXT.md](../../CONTEXT.md)。

簡要原則是：只維護一套閱讀器 UI；Server 專屬資料不能進入 SSG；EPUB 和 PDF 衍生快取
必須與 SQLite 使用者資料分離；絕不能新增執行期 CDN 相依項目。影響共用介面的改動，
應在適用範圍內同時以兩種格式和兩種部署模式測試。

#### 從原始碼工作目錄開發

第三方瀏覽器檔案是產生的建置輸入，不是專案原始碼，因此 Git 儲存庫刻意不收錄
`epub_browser/assets/vendor/`。開發或建置前，必須明確補齊鎖定版本的資源，再離線驗證：

```bash
python3 tools/sync_vendor_assets.py fetch
python3 tools/sync_vendor_assets.py verify
python3 -m unittest tests.test_vendor_assets -v
python3 -m build
```

上述命令只有 `fetch` 會下載瀏覽器第三方資源。鎖定檔記錄不可變的 npm tarball、
檔案摘要、允許清單和授權條款；`verify`、測試、在已補齊資源的原始碼工作目錄中建置，
以及安裝後的閱讀器都不會下載瀏覽器資源。標準的隔離建置命令 `python3 -m build` 仍可能
存取 Python 套件索引以取得建置需求。若要在完全停用網路的環境建置，請在離線前補齊
第三方資源目錄並預先安裝 `build`、`setuptools` 和 `wheel`，然後執行
`PIP_NO_INDEX=1 python3 -m build --no-isolation`。wheel、原始碼發行套件、Docker 映像和
產生的 SSG 網站都包含已驗證檔案，沒有執行期 CDN 相依項目。更新、發布和儲存庫維護
流程請見 [third_party/README.md](../../third_party/README.md)。

### 授權

[MIT](../../License.txt)
