# Issue #21 实现方案 · Server EPUB 书内搜索

**需求** [Add per-book full-text search in Server mode](https://github.com/dfface/epub-browser/issues/21)

**目标** 在标准 EPUB 章节阅读器中搜索当前整本书的正文。每条结果显示章节和命中片段，并可在当前阅读模式下定位到具体命中。

**交接** 按下面四项任务顺序实现。以实施时最新的 `origin/main` 为基线，在独立 worktree 工作。本文核对的是 `462c327e` 和当前分支的阅读器代码。若按最新主线实施时导航或资源加载已有改动，以对应入口的现有行为为准。

## 范围与设计决定

- 首版支持 **Server 模式的标准 EPUB 章节页**，含桌面及移动端。PDF 已有 PDF.js 书内搜索，继续使用现有入口。EPUB SSG、书库、书籍首页、Kindle 极简页、跨书搜索、PAT/OpenAPI 均在本次范围之外。
- 在第一次获得授权的有效查询时，为这本书构建可丢弃的 `search.sqlite3`。数据来自已清洗的 `content/metadata.json` 和 `chapter_N.json`。索引存于 `cache/public/book/<id>/search.sqlite3`，通过 Server 现有书籍路径白名单保持私有，与该书缓存一起替换和淘汰。运行时状态库无需迁移。
- 索引记录自己的版本，并校验 EPUB 内容修订标记和书源指纹。旧缓存可直接建索引。保留当前 `SERVER_OUTPUT_REVISION`，避免为启用搜索重转已有书籍。
- 首版按字面子串匹配，支持中文短词和含空格的短语。以章节顺序、章内出现顺序返回最多 50 个非重叠命中。查询采用 Unicode 大小写折叠，保留重音和标点。首版界面提示结果截断，让读者用更具体的词继续查找。

## 任务 1 · 搜索文本与单书索引

**文件** 新增 `epub_browser/book_search.py`、`tests/test_book_search.py`。复用 `ServerPageRenderer.chapter_content()` 的校验，并在 `server_pages.py` 暴露读取 EPUB 缓存章节数的小入口，直接读取 `metadata.json` 的 `chapters` 列表长度。搜索无需加载渲染资源清单。

- [ ] 先写测试固定文本协议。用正文 `<p>😀甲<em>乙</em>&amp;字</p><p>甲乙</p>` 搜索 `甲乙`，应返回两个命中，UTF-16 区间分别是 `[2, 4)`、`[7, 9)`。再覆盖空白折叠、HTML 实体、空章节、链接与代码正文、`Straße` 对 `STRASSE`、单字/双字中文，以及引号、百分号、星号和 `OR` 的字面查询。
- [ ] 实现 `extract_search_text(markup: str) -> str`。先复用 `sanitize_html_fragment`，与 Server 阅读页使用同一清洗结果，再用 `epub_parsing.py` 的片段解析器按正文树顺序取文本。处理包装层、顶层文本和元素尾文本。Python 提取器和任务 3 的 DOM 提取器遵守下面同一份协议，用相同 fixture 校验。
- [ ] 实现 `build_book_search_index(path: Path, renderer: ServerPageRenderer, generation: SearchGeneration) -> None` 和 `query_book_search_index(path: Path, query: str) -> dict`。定义 `SearchGeneration`，含磁盘内容修订、书源指纹、内容目录设备号和 inode。数据库存索引版本、内容修订、书源指纹、章节编号、标题、原始搜索文本和折叠文本。编号以缓存的零起点 spine 顺序为准。每个章节保存一行，逐章写入，空正文允许跳过。
- [ ] 三个及以上 Unicode 码点的折叠查询，优先用 FTS5 的 `trigram case_sensitive 1` 在折叠文本上筛选章节。用绑定参数传递完整双引号短语，内部双引号加倍。按章节顺序流式读取候选，再从折叠文本取精确命中。构建时探测当前 SQLite 是否支持 FTS5 trigram。缺少该能力时，用同一个章节表扫描。折叠后的一字、二字查询也扫描单书章节表，保持同一匹配规则。只将缺失 FTS5 或 tokenizer 的错误视为能力降级。
- [ ] 折叠文本用 Python `casefold()`。查到候选章节后，以原文逐码点折叠建立边界映射，只返回能映射到完整原文字符的命中。偏移转换成 UTF-16 码元。扫描到第 51 个有效命中即可停止并设置 `truncated`。每条片段取命中和前后最多各 40 个原文码点。
- [ ] 跑 `python -m unittest tests.test_book_search`。覆盖可用 FTS 与强制无 FTS 两条路径，确保给定查询返回相同结果，截断顺序稳定。验证创建索引前的旧章节缓存就能使用，无需调用转换器。

### Python 与浏览器的文本协议

1. 从章节正文根节点遍历文本。跳过 `script`、`style`、`template`、`svg` 的整个子树。浏览器额外跳过自身生成的章节分隔条和加载提示。保留普通链接、代码、行内格式和标注包装内的原文。
2. 在 `address article aside blockquote dd details div dl dt figcaption figure footer h1 h2 h3 h4 h5 h6 header hr li main nav ol p pre section summary table tbody td tfoot th thead tr ul` 元素边界以及 `br` 处插入分隔空白。行内元素不插入分隔。将连续 ASCII HTML 空白（空格、Tab、CR、LF、FF）折叠成一个普通空格，去掉首尾的这种空白。保留 NBSP。浏览器同时记录折叠前后的节点边界，以便把命中转为 `Range`。
3. 例如上面的 fixture 生成 `😀甲乙&字 甲乙`。正文偏移均为零起点的 UTF-16 半开区间。索引中的折叠文本只用于查询，结果中的 `match` 始终是对应的原文。跨块或跨行内节点的命中沿用同一规则。

[SQLite FTS5 trigram 文档](https://www.sqlite.org/fts5.html#the_trigram_tokenizer)

## 任务 2 · 缓存代次与 Session API

**文件** `epub_browser/book_search.py`、`epub_browser/server_library.py`、`epub_browser/server.py`、`tests/test_server_library.py`，在 `tests/test_server.py` 加 API 测试。

- [ ] 先写用例证明旧书源、新书源和内容修订变化会得到对应结果。再写一个用同步事件控制的测试，在索引构建读完一部分章节时发布新版，断言请求只会返回完整新版或可重试错误，且新版目录内没有旧索引。另测两个并发首查、构建中途失败、缓存淘汰后恢复，以及索引损坏后重建。
- [ ] 在 `ServerLibraryManager` 加窄接口，让搜索在现有 `_commit_lock` 下取得或确认已发布代次。使用内容目录的文件系统身份（设备号、inode）、当前书源指纹及磁盘修订标记。短暂持锁完成取代次、最终比较与替换；释放锁后读取章节、构建和查询。以 `book_cache(book_id, read=True)` 包住整个同步搜索操作，复用冷缓存恢复和缓存租约。租约防淘汰，代次校验处理 watch 转换时的整目录替换。
- [ ] 为同一本书的搜索构建做进程内串行化。重新检查后仍需建索引时，在同一缓存文件系统的 `staging/` 写唯一临时库。提交并关闭 SQLite 后，在 `_commit_lock` 内确认仍是原代次，再用 `os.replace` 发布。将索引头中的版本/指纹/修订与当前代次比较。读章节、打开索引、发布或查询失败时先检查代次。发生切换就丢弃本次全部中间产物并重试一次，仍变化则返回 503。查询结果出工作线程前再检查代次。损坏索引在当前代次下尝试重建一次。为现有无 library manager 的 `create_app` 用法提供同一索引服务的直接读取路径，以传入的书籍缓存根为准。
- [ ] 注册 `GET /api/books/{book_id}/search?q=...`。沿用 `pdf_document` 的 Session/可见性顺序，先 `require_principal`，再 `store.can_read_book`，再取 EPUB 书籍记录。无 Session 走中间件，受限且无授权、已删除、未知或 PDF 书籍统一返回 404。通过权限后校验 `q`，只接受一个参数，按文本协议折叠首尾及内部 ASCII 空白，接受 1–128 个 Unicode 码点，拒绝 NUL。无效值返回 400 和 `invalid_book_search_query`。
- [ ] 用现有 `run_io` 执行整个同步服务，包括租约的 acquire/release。客户端取消时，由工作线程完成清理和释放租约。内容缺失、索引暂不可用或持续换代时返回 503 和 `book_search_unavailable`。准备返回结果前再检查当前可见性，权限已收回则返回 404。路由响应使用 `Cache-Control: private, no-store`，错误正文使用现有错误结构与本地化入口。保持书籍文件白名单，不注册公开索引文件或 PAT 路由。
- [ ] 测试无登录、仅有 PAT、未获授权成员、被授权成员、普通可见书成员及管理员。未授权路径应在尝试恢复书籍缓存或创建索引前返回。用两本含同一短语的书断言只得到目标书章节，并验证 Session 下也无法通过静态文件 URL 下载索引。
- [ ] 跑 `python -m unittest tests.test_book_search tests.test_server tests.test_server_library tests.test_server_concurrency`。

成功响应示例，空结果返回相同结构和空数组。命中前后文本分开传递，客户端可直接用文本节点渲染。

```json
{
  "results": [
    {
      "chapter_index": 0,
      "chapter_title": "第一章",
      "start_offset": 2,
      "end_offset": 4,
      "before": "😀",
      "match": "甲乙",
      "after": "&字 甲乙"
    }
  ],
  "truncated": false
}
```

## 任务 3 · 阅读器入口与结果定位

**文件** `epub_browser/reader_pages.py`、`epub_browser/assets/chapter.js`、新增 `epub_browser/assets/book-search.js`、`epub_browser/asset_publisher.py`、`epub_browser/assets/i18n/*.json`、必要时 `epub_browser/assets/chapter.css`。测试用 `tests/test_generated_reader_surfaces.py` 和新增 `tests/test_book_search.js`。

- [ ] 在 `create_chapter_template()` 中以 `deployment_mode == "server" and pdf_page is None` 渲染桌面/移动搜索按钮与抽屉。沿用 PDF 搜索的抽屉结构与样式约定，复用 `EpubReaderDrawers.register()` 处理开关、遮罩和焦点。若需要抽取样式，共用规则放在章节样式中。用现有哈希资源加载方式引入 `book-search.js`，加入 `SERVER_ONLY_ASSET_PATHS`。
- [ ] 脚本从章节根节点取当前 book ID，经 `EpubBrowserURL.publicPath` 生成同源 API 和章节链接。表单提交触发查询，提供查询中、无结果、失败、结果截断状态。关闭抽屉或发起新查询时取消旧请求并用请求序号忽略迟到响应。用 `textContent`、文本节点和 `mark` 渲染标题、片段与命中。所有状态和按钮文案覆盖受支持语言，运行时用 `data-i18n*` 或 `onLocaleChange` 更新。
- [ ] 结果使用普通链接 `chapter_<n>.html#eb-search=<start>,<end>,<encodeURIComponent(match)>`。跨章走正常浏览器导航，同章监听 `hashchange`，并支持复制链接、直接打开和返回/前进。首版无需让局部章节预取处理搜索链接。现有 `popstate` 监听遇到当前章节的搜索片段时跳过局部导航，由搜索定位逻辑处理，避免连续滚动的章节跳转再把命中滚出视口。对片段做严格解码及整数、长度、区间校验，且仅由已启用搜索的章节页消费。
- [ ] `book-search.js` 暴露 `rangeForHit(root, hit)`。按文本协议把 `start_offset`、`end_offset` 映射为 DOM `Range`，校验相同偏移处的规范化原文等于 `match`。遇到旧结果、无可见矩形或异常片段时保留当前章节并给出本地化状态，不猜测另一个重复命中。
- [ ] 在 `chapter.js` 复用已有布局就绪点执行定位。普通滚动在章节样式和初次布局应用后根据 Range 的首个可见矩形定位。连续滚动限定到目标 `.continuous-chapter[data-chapter-index]`，等待该根插入后定位。横向翻页在 `createPages()` 的 `calculateTotalPages()` 完成后，以 Range 矩形相对阅读容器的横向位置和当前 `scrollLeft` 算页号，交给 `showPage()`。初次加载时，在安排阅读进度恢复前识别格式合法的搜索片段，由搜索定位优先处理，避免延迟恢复覆盖定位。搜索命中可用 CSS Highlight API 临时标示，缺少该 API 时仍定位；切章或换命中时清除标示。保持持久标注及现有 TOC hash 行为。
- [ ] 增加前端测试，覆盖重复词定位到第二个、内联标签、emoji 偏移、跨段空白、恶意片段只作文本、快速查询时旧响应不会覆盖，以及抽屉打开时切换语言。生成页面测试验证 Server EPUB 有入口，EPUB SSG 与 Kindle 没有入口或专用脚本，Server/SSG PDF 原搜索均可渲染。

## 任务 4 · 交付验证

- [ ] 跑 `python -m unittest tests.test_book_search tests.test_server tests.test_server_library tests.test_mode_integration tests.test_ssg tests.test_pdf_server tests.test_i18n_coverage tests.test_generated_reader_surfaces`、`node --test tests/*.js` 和 `git diff --check`。
- [ ] 用 `examples` 分别启动 Server 和 SSG 验证环境，目录使用临时路径。Server 以 `epub-browser server examples --port 8000 --server-dir <临时目录> --watch` 启动，SSG 用 `epub-browser ssg examples --output-dir <临时目录>` 生成后通过静态 HTTP 服务打开。用含重复中文词和英文短语的 EPUB 检查同章及跨章跳转。三种阅读模式都点击第二个重复命中，确认实际进入第二处而非第一处或章首。刷新复制的链接，确认原阅读进度不会覆盖定位。检查移动端、PDF 现有搜索和打开抽屉后切语言。
- [ ] 在 Server 读一本升级前已有内容缓存的 EPUB，首次搜索应生成单书索引。替换书源并保留稳定 ID，等待 watch 转换完成后验证旧词消失、新词出现。确认书库和 SSG 输出中没有搜索数据库。
- [ ] 交接时附改动范围、验证结果、Server/SSG URL 及测试账户的进入方式。PR 按项目 Issue 流程取得明确授权后再创建，并使用 `Closes #21` 关联。
