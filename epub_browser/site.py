import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, Sequence, Tuple
from types import SimpleNamespace

import minify_html

from .asset_publisher import PublishedAssets, rewrite_asset_urls
from .server_chrome import (
    SERVER_ACCOUNT_CONTROL,
    SERVER_ACCOUNT_PANEL,
    SERVER_ACCOUNT_STYLESHEET,
    SERVER_AUTH_SCRIPT,
    SERVER_LOCALE_CONTROL,
    SERVER_LOCALE_SCRIPT,
)
from .urls import SiteURLs, rewrite_root_urls
from .version import LATEST_RELEASE_API_URL, render_footer
from .source_format import EPUB_FORMAT


@dataclass(frozen=True)
class LibraryBook:
    book_id: str
    title: str
    authors: Tuple[str, ...]
    tags: Tuple[str, ...]
    cover: Optional[str]
    source_format: str = EPUB_FORMAT


def render_library_shell(
    books: Sequence[LibraryBook],
    assets: PublishedAssets,
    urls: SiteURLs,
    deployment_mode: str,
) -> str:
    """Render the shared library application shell for one deployment mode.

    SSG writes this shell together with its static catalogue.  Server mode
    uses the same shell as a small SPA: the initial document contains no
    catalogue and ``library.js`` fetches the authenticated catalogue at
    runtime.  Keeping this public renderer available to the request handler
    means Server UI/asset updates never depend on a stale ``index.html``.
    """
    self = SimpleNamespace(
        books={
            book.book_id: {
                "title": book.title,
                "authors": book.authors,
                "tags": book.tags,
                "cover": book.cover,
            }
            for book in books
        },
        asset_manifest=assets,
    )
    library_feature_assets = json.dumps({
        "pinyin": assets.url_for("vendor/pinyin-pro/pinyin-pro.min.js"),
        "sortable": assets.url_for("vendor/sortablejs/sortable.min.js"),
        "bookshelf": assets.url_for("bookshelf.js"),
        "annotationHubCss": assets.url_for("annotation-hub.css"),
        "annotation": assets.url_for("annotation.js"),
        "annotationHub": assets.url_for("annotation-hub.js"),
    }, separators=(",", ":"))
    server_progress_stylesheet = ""
    server_progress_panel = ""
    server_progress_script = ""
    server_progress_start = ""
    bookshelf_data_actions = """
            <button class="bookshelf-action-btn" id="exportShelfBtn">
                <i class="fas fa-upload" aria-hidden="true"></i> <span data-i18n="bookshelf.export">Export</span>
            </button>
            <button class="bookshelf-action-btn" id="importShelfBtn">
                <i class="fas fa-download" aria-hidden="true"></i> <span data-i18n="bookshelf.import">Import</span>
            </button>
            <input type="file" id="importShelfFile" accept=".json" style="display: none;">""" if deployment_mode == "ssg" else ""
    install_control = """
            <button type="button" class="app-nav-link" id="pwa-install-btn" style="display: none;">
                <i class="fas fa-download" aria-hidden="true"></i><span data-i18n="library.install">Install</span>
            </button>""" if deployment_mode == "ssg" else ""
    server_account_control = ""
    server_account_panel = ""
    server_account_stylesheet = ""
    server_auth_script = ""
    ai_reading_stylesheet = ""
    ai_reading_navigation = ""
    reading_insights_navigation = ""
    ai_reading_script = ""
    server_client_start = f"""
            if (window.initScriptLibrary) window.initScriptLibrary();
            {server_progress_start}"""
    if deployment_mode == "server":
        library_feature_assets = json.dumps({
            **json.loads(library_feature_assets),
            "readingInsightsCss": assets.url_for("reading-insights.css"),
            "readingInsights": assets.url_for("reading-insights.js"),
        }, separators=(",", ":"))
        reading_insights_navigation = '''<button type="button" class="app-nav-link" data-reading-insights aria-haspopup="dialog"><i class="fas fa-chart-column" aria-hidden="true"></i><span data-i18n="readingInsights.navigation">Reading insights</span></button>'''
        ai_reading_navigation = '''<button type="button" class="app-nav-link" data-ai-reading-hub aria-haspopup="dialog"><i class="fas fa-wand-magic-sparkles" aria-hidden="true"></i><span data-i18n="ai.library">AI readings</span></button>'''
        ai_feature_assets = {
            "aiReadingHubCss": assets.url_for("ai-reading-hub.css"),
            "aiReadingHub": assets.url_for("ai-reading-hub.js"),
            "aiRichTextCss": assets.url_for("ai-rich-text.css"),
            "aiRichText": assets.url_for("ai-rich-text.js"),
            "markdownIt": assets.url_for("vendor/markdown-it/markdown-it.min.js"),
            "katexCss": assets.url_for("vendor/katex/katex.min.css"),
            "katex": assets.url_for("vendor/katex/katex.min.js"),
            "mermaid": assets.url_for("vendor/mermaid/mermaid.min.js"),
        }
        ai_reading_script = (
            '<script>window.EpubBrowserFeatureAssets='
            + json.dumps(ai_feature_assets, separators=(",", ":"))
            + ';</script><script src="/assets/ai-feature-loader.js" defer></script>'
        )
        server_progress_stylesheet = '<link rel="stylesheet" href="/assets/library-progress.css">'
        server_progress_panel = """
    <section id="libraryProgress" class="library-progress" hidden aria-labelledby="libraryProgressTitle">
      <div class="library-progress-heading">
        <div>
          <h2 id="libraryProgressTitle" data-progress-title></h2>
          <p data-progress-summary aria-live="polite"></p>
        </div>
        <button type="button" data-progress-close aria-label="Close" data-i18n-aria-label="library.progress.close" hidden disabled>×</button>
      </div>
      <div class="library-progress-track" data-progress-track><span data-progress-bar></span></div>
      <p class="library-progress-latest" data-progress-latest></p>
      <details data-progress-failures hidden>
        <summary data-i18n="library.progress.failureDetails">Failure details</summary>
        <ul data-progress-failure-list></ul>
      </details>
    </section>"""
        server_progress_script = '<script src="/assets/library-progress.js" defer></script>'
        server_progress_start = 'if (window.EpubLibraryProgress) window.EpubLibraryProgress.start(window);'
        server_account_stylesheet = SERVER_ACCOUNT_STYLESHEET
        server_account_control = SERVER_ACCOUNT_CONTROL
        server_account_panel = SERVER_ACCOUNT_PANEL
        server_auth_script = SERVER_AUTH_SCRIPT
        server_client_start = f"""
            if (!window.EpubBrowserAuth) return;
            window.EpubBrowserAuth.init().then(function(session) {{
                if (!session) return;
                if (window.initScriptLibrary) window.initScriptLibrary();
                {server_progress_start}
            }});"""
    library_html = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="theme-color" content="#244548">
<meta name="description" content="EPUB Library - A web-based EPUB reader" data-i18n-content="library.description">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="default">
<meta name="apple-mobile-web-app-title" content="EPUB Browser">
<title data-i18n="library.pageTitle">EPUB Library</title>
<script src="/assets/i18n.js"></script>
<script>window.EpubBrowserI18n.init();</script>
<noscript><link rel="manifest" href="/assets/manifest.en.json"></noscript>
<link rel="stylesheet" href="/assets/vendor/fontawesome/css/all.min.css">
<link rel="icon" type="image/png" href="/assets/favicon.png">
<link rel="apple-touch-icon" href="/assets/icon-192.png">
<link rel="stylesheet" href="/assets/theme.css">
<link rel="stylesheet" href="/assets/notification.css">
<link rel="stylesheet" href="/assets/dialog.css">
<link rel="stylesheet" href="/assets/library.css?v=13">
<link rel="stylesheet" href="/assets/breadcrumb.css?v=3">
<link rel="stylesheet" href="/assets/loading.css?v=15">
<link rel="stylesheet" href="/assets/bookshelf.css">
    {ai_reading_stylesheet}
{server_account_stylesheet}
{server_progress_stylesheet}
<script>
// 立即应用主题，避免闪现 —— Kindle 兼容版
function isKindleDevice() {
  // 优先从 window 缓存读取
  if (window.epubBrowserCache && window.epubBrowserCache.kindle_mode !== undefined) {
    return window.epubBrowserCache.kindle_mode === "true";
  }
  // 检测设备
  var ua = navigator.userAgent.toLowerCase();
  var isKindle = ua.indexOf("kindle") !== -1 || ua.indexOf("silk") !== -1;

  if (!window.epubBrowserCache) {
    window.epubBrowserCache = {};
  }
  window.epubBrowserCache.kindle_mode = isKindle ? "true" : "false";
  return isKindle;
}

// 通用 Cookie 方法（只定义一次）
function getCookie(key) {
  var cookies = document.cookie.split("; ");
  for (var i = 0; i < cookies.length; i++) {
    var parts = cookies[i].split("=");
    var cookieKey = parts[0];
    var cookieValue = parts.slice(1).join("=");
    if (cookieKey === key) {
      return decodeURIComponent(cookieValue);
    }
  }
  return null;
}

var theme = "light";
var isKindle = false;

try {
  // 优先从 window 缓存读取
  var storedTheme = null;
  if (window.epubBrowserCache && window.epubBrowserCache.theme) {
    storedTheme = window.epubBrowserCache.theme;
  } else {
    storedTheme = localStorage.getItem("theme");
    if (storedTheme) {
      if (!window.epubBrowserCache) {
    window.epubBrowserCache = {};
      }
      window.epubBrowserCache.theme = storedTheme;
    }
  }

  if (storedTheme) {
    theme = storedTheme;
  } else if (isKindleDevice()) {
    isKindle = true;
    theme = getCookie("theme") || "light";
  }
} catch (e) {
  // 捕获异常，兼容 Kindle
  if (isKindleDevice()) {
    isKindle = true;
    theme = getCookie("theme") || "light";
  }
}

// 使用 html 元素添加类名
var htmlElement = document.documentElement;
htmlElement.classList.add(theme + "-mode");
if (isKindle) {
  htmlElement.classList.add("kindle-mode");
}
</script>
</head>
<body>
"""
    all_tags = set()
    for book_hash, book_info in self.books.items():
        cur_tags = book_info['tags']
        if cur_tags:
            for cur_tag in cur_tags:
                if isinstance(cur_tag, str) and cur_tag.strip():
                    all_tags.add(cur_tag.strip())

    library_html += f"""
    <header class="app-header">
    <nav class="app-nav app-nav-primary" aria-label="Primary navigation" data-i18n-aria-label="library.navigation">
        <a class="app-nav-brand" href="/" aria-label="EPUB Browser" data-i18n-aria-label="common.brand"><img class="app-nav-brand-mark" src="/assets/logo-mark-color.png" width="32" height="32" alt="" aria-hidden="true"><span data-i18n="common.brand">EPUB Browser</span></a>
        <div class="app-nav-links">
            <button type="button" class="app-nav-link" id="bookshelfBtn" aria-haspopup="dialog" aria-controls="bookshelfModal"><i class="fas fa-bookmark" aria-hidden="true"></i><span data-i18n="library.shelf">Shelf</span></button>
            <button type="button" class="app-nav-link" id="annotationsBtn" data-annotation-hub aria-haspopup="dialog"><i class="fas fa-highlighter" aria-hidden="true"></i><span data-i18n="library.annotations">Annotations</span></button>
            {reading_insights_navigation}
            {ai_reading_navigation}
            {install_control}
        </div>
        <div class="app-nav-actions">
            {SERVER_LOCALE_CONTROL}
            <button type="button" class="theme-toggle app-nav-action app-nav-theme" id="themeToggle" aria-label="Theme" data-i18n-aria-label="library.theme"><i class="fas fa-moon" aria-hidden="true"></i><span class="app-nav-action-label" data-i18n="library.theme">Theme</span></button>
            {server_account_control}
        </div>
    </nav>
    </header>
    <div class="container">
    <section class="library-overview" aria-labelledby="libraryHeading">
        <div>
            <p class="library-overview-kicker" data-i18n="common.brand">EPUB Browser</p>
            <h1 id="libraryHeading" data-i18n="library.title">Library</h1>
        </div>
        <div class="library-summary" aria-label="Library information" data-i18n-aria-label="library.information">
            <span class="library-summary-item"><i class="fas fa-book" aria-hidden="true"></i><span id="libraryBookCount" data-i18n="library.bookCount" data-i18n-params='{{"count": {len(self.books)}}}'>{len(self.books)} book(s)</span></span>
            <span class="library-summary-item"><i class="fas fa-tags" aria-hidden="true"></i><span id="libraryTagCount" data-i18n="library.tagCount" data-i18n-params='{{"count": {len(all_tags)}}}'>{len(all_tags)} tag(s)</span></span>
        </div>
    </section>
{server_progress_panel}
    <div class="controls" data-id="controls">
        <div class="search-container">
            <input type="text" class="search-box" placeholder="Search by book title, author, or tag..." data-i18n-placeholder="library.searchPlaceholder">
            <i class="fas fa-search search-icon"></i>
        </div>
        <br/>
        <div class="tag-cloud">
            <div class="tag-cloud-item active" data-id="All" data-i18n="library.all">All</div>
            <div class="tag-cloud-item" data-id="NoTag" data-i18n="library.noTag">No tag</div>
"""
    for tag in sorted(t for t in all_tags if isinstance(t, str) and t.strip()):
        library_html += f"""<div class="tag-cloud-item" data-id="{tag}">{tag}</div>"""
    library_html += """
        </div>
        <button type="button" class="tag-cloud-toggle" id="tagCloudToggle" hidden aria-expanded="false" data-i18n="library.showMoreTags">Show more</button>
    </div>"""

    library_html += """
    <div class="book-grid" data-id="book-grid">
        <div class="book-grid-loading" id="bookGridLoading" data-id="bookGridLoading" role="status" aria-label="Loading library" data-i18n-aria-label="library.loading">
            <div class="loading-spinner"></div>
        </div>
"""
    library_html += f"""
    </div>
    <div class="reading-controls" data-id="reading-controls">
    <button class="control-btn" id="scrollToTopBtn" type="button" aria-label="Top" data-i18n-aria-label="library.top">
        <i class="fas fa-arrow-up"></i>
        <span class="control-name" data-i18n="library.top">Top</span>
    </button>
    </div>
</div>

<!-- 书架弹窗 -->
<div class="bookshelf-modal" id="bookshelfModal" role="dialog" aria-modal="true" aria-labelledby="bookshelfModalTitle">
    <div class="bookshelf-content" tabindex="-1">
    <div class="bookshelf-header">
        <div class="bookshelf-header-left">
            <button class="bookshelf-action-btn" id="addShelfGroupBtn">
                <i class="fas fa-folder-plus" aria-hidden="true"></i> <span data-i18n="bookshelf.addGroup">Add Group</span>
            </button>
            <button class="bookshelf-action-btn" id="addShelfBookBtn">
                <i class="fas fa-plus" aria-hidden="true"></i> <span data-i18n="bookshelf.addBook">Add Book</span>
            </button>
{bookshelf_data_actions}
        </div>
        <h2 class="bookshelf-title" id="bookshelfModalTitle"><i class="fas fa-home" aria-hidden="true"></i> <span data-i18n="bookshelf.title">Bookshelf</span></h2>
        <div class="bookshelf-header-right">
            <button class="bookshelf-close-btn" id="bookshelfCloseBtn" aria-label="Close" data-i18n-aria-label="bookshelf.close">
                <i class="fas fa-times"></i>
            </button>
        </div>
    </div>
    <div class="bookshelf-loading" id="bookshelfLoading" role="status" aria-label="Loading bookshelf" data-i18n-aria-label="bookshelf.loading">
        <div class="loading-spinner"></div>
    </div>
    <div class="bookshelf-body" id="bookshelfBody">
    </div>
    <div class="bookshelf-footer" id="bookshelfFooter">
        <span id="bookshelfStats"></span>
    </div>
    </div>
</div>

<!-- 分组弹窗 -->
<div class="bookshelf-modal" id="groupModal" role="dialog" aria-modal="true" aria-labelledby="groupModalTitle">
    <div class="bookshelf-content" tabindex="-1">
    <div class="bookshelf-header">
        <div class="bookshelf-header-left">
            <button class="bookshelf-action-btn" id="addGroupSubGroupBtn">
                <i class="fas fa-folder-plus" aria-hidden="true"></i> <span data-i18n="bookshelf.addGroup">Add Group</span>
            </button>
            <button class="bookshelf-action-btn" id="addGroupBookBtn">
                <i class="fas fa-plus" aria-hidden="true"></i> <span data-i18n="bookshelf.addBook">Add Book</span>
            </button>
            <button class="bookshelf-action-btn" id="renameGroupBtn">
                <i class="fas fa-edit" aria-hidden="true"></i> <span data-i18n="bookshelf.rename">Rename</span>
            </button>
            <button class="bookshelf-action-btn bookshelf-delete-btn" id="deleteGroupBtn">
                <i class="fas fa-trash" aria-hidden="true"></i> <span data-i18n="bookshelf.deleteGroup">Delete Group</span>
            </button>
        </div>
        <h2 class="bookshelf-title" id="groupModalTitle" data-i18n="bookshelf.group">Group</h2>
        <div class="bookshelf-header-right">
            <button class="bookshelf-close-btn" id="groupCloseBtn" aria-label="Back to bookshelf" data-i18n-aria-label="bookshelf.home">
                <i class="fas fa-home"></i>
            </button>
            <button class="bookshelf-close-btn" id="groupCloseAllBtn" aria-label="Close" data-i18n-aria-label="bookshelf.close">
                <i class="fas fa-times"></i>
            </button>
        </div>
    </div>
    <div class="bookshelf-loading" id="groupLoading" role="status" aria-label="Loading bookshelf" data-i18n-aria-label="bookshelf.loading">
        <div class="loading-spinner"></div>
    </div>
    <div class="bookshelf-body" id="groupBody">
    </div>
    <div class="bookshelf-footer" id="groupFooter">
        <span id="groupStats"></span>
    </div>
    </div>
</div>
{server_account_panel}
{render_footer(datetime.now().year, release_api_url='/api/version' if deployment_mode == 'server' else LATEST_RELEASE_API_URL)}
"""
    library_html += """
    <script src="/assets/cache-boundary.js" defer></script>
    <script src="/assets/notification.js" defer></script>
{server_auth_script}
    <script src="/assets/theme.js" defer></script>
    <script src="/assets/dialog.js" defer></script>
    <script src="/assets/version-check.js" defer></script>
    <script>window.EpubBrowserLibraryFeatureAssets={library_feature_assets};</script>
    <script src="/assets/library-feature-loader.js" defer></script>
    <script src="/assets/library.js?v=13" defer></script>
{ai_reading_script}
{server_progress_script}
    {SERVER_LOCALE_SCRIPT}
    <script>
    document.addEventListener('DOMContentLoaded', function() {
        function startLibraryClients() {
            {server_client_start}
        }
        if (window.EpubBrowserMode === 'server') {
            if (window.EpubBrowserCacheBoundary) {
                window.EpubBrowserCacheBoundary.start(startLibraryClients);
            }
        } else {
            startLibraryClients();
        }
    });
    </script>
    </body>
</html>"""
    library_html = library_html.replace("{server_progress_stylesheet}", server_progress_stylesheet)
    library_html = library_html.replace("{server_progress_panel}", server_progress_panel)
    library_html = library_html.replace("{server_progress_script}", server_progress_script)
    library_html = library_html.replace("{server_progress_start}", server_progress_start)
    library_html = library_html.replace("{library_feature_assets}", library_feature_assets)
    library_html = library_html.replace("{bookshelf_data_actions}", bookshelf_data_actions)
    library_html = library_html.replace("{server_account_panel}", server_account_panel)
    library_html = library_html.replace("{server_account_stylesheet}", server_account_stylesheet)
    library_html = library_html.replace("{server_auth_script}", server_auth_script)
    library_html = library_html.replace("{server_client_start}", server_client_start)
    library_html = library_html.replace("{ai_reading_stylesheet}", ai_reading_stylesheet)
    library_html = library_html.replace("{ai_reading_navigation}", ai_reading_navigation)
    library_html = library_html.replace("{reading_insights_navigation}", reading_insights_navigation)
    library_html = library_html.replace("{ai_reading_script}", ai_reading_script)
    library_html = library_html.replace("{SERVER_LOCALE_SCRIPT}", SERVER_LOCALE_SCRIPT)
    library_html = rewrite_asset_urls(library_html, self.asset_manifest)
    library_html = rewrite_root_urls(library_html, urls)
    library_html = library_html.replace(
        '<script>window.EpubBrowserI18n.init();</script>',
        f'<script>window.EpubBrowserBasePath={json.dumps(urls.base_path)};'
        f'window.EpubBrowserMode={json.dumps(deployment_mode)}</script>'
        '<script>window.EpubBrowserI18n.init();</script>',
        1,
    )
    return minify_html.minify(library_html, minify_css=True, minify_js=True)


def _atomic_write_text(path: Path, contents: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as temporary:
        temporary.write(contents)
        temporary.flush()
        os.fsync(temporary.fileno())
        temporary_path = Path(temporary.name)
    os.replace(temporary_path, path)


def publish_library_shell(
    output_dir: Path,
    books: Sequence[LibraryBook],
    assets: PublishedAssets,
    urls: SiteURLs,
    deployment_mode: str = "ssg",
) -> None:
    if deployment_mode not in {"ssg", "server"}:
        raise ValueError(f"Unsupported deployment mode: {deployment_mode}")
    root = Path(output_dir)
    ordered_books = tuple(sorted(books, key=lambda book: book.book_id))
    metadata = [
        {
            "hash": book.book_id,
            "url": urls.public(f"/book/{book.book_id}/index.html"),
            "title": book.title,
            "authors": list(book.authors),
            "tags": list(book.tags),
            "cover": urls.public(book.cover) if book.cover else None,
            "format": book.source_format,
        }
        for book in ordered_books
    ]
    html = render_library_shell(ordered_books, assets, urls, deployment_mode)
    _atomic_write_text(root / "index.html", html)
    _atomic_write_text(
        root / "book-metadata.json",
        json.dumps(metadata, ensure_ascii=False, separators=(",", ":")),
    )
