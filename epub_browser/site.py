import json
import html
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, Sequence, Tuple
from types import SimpleNamespace

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
from .version import render_footer
from .source_format import EPUB_FORMAT
# The Kindle minimal reader CSS/JS live in processor.py as the single source
# of truth shared by the book-level kindle.html pages and the minimal library
# page below; both surfaces must stay dependency-free and ES5.
from .processor import (
    _KINDLE_READER_CSS,
    _KINDLE_READER_JS,
    metadata_text,
)


@dataclass(frozen=True)
class LibraryBook:
    book_id: str
    title: str
    authors: Tuple[str, ...]
    tags: Tuple[str, ...]
    cover: Optional[str]
    source_format: str = EPUB_FORMAT


def _kindle_book_row(book: LibraryBook, urls: SiteURLs) -> str:
    """One read-only Kindle book row linking into the minimal reader."""
    href = urls.public(f"/book/{book.book_id}/kindle.html")
    title = html.escape(metadata_text(book.title), quote=False)
    authors = " & ".join(
        html.escape(metadata_text(author), quote=False)
        for author in book.authors
    )
    if authors:
        return (
            f'<li><a href="{href}"><span class="k-lib-title">{title}</span>'
            f'<span class="k-lib-authors">{authors}</span></a></li>'
        )
    return f'<li><a href="{href}">{title}</a></li>'


def _kindle_group_html(group, books_by_id, urls: SiteURLs) -> str:
    """Render one bookshelf group as a read-only nested Kindle list.

    The bookshelf document stores each group as ``{"name", "items",
    "groups", "order"}``; nested groups are rendered recursively with plain
    ``ul/li`` markup so legacy Kindle WebKit stays happy.  The surface is
    read-only: group names are static text and only book rows are links.
    """
    if not isinstance(group, dict):
        return ""
    name = html.escape(metadata_text(group.get("name") or ""), quote=False)
    if not name:
        return ""
    items = group.get("items")
    sub_groups = group.get("groups")
    items = items if isinstance(items, list) else []
    sub_groups = sub_groups if isinstance(sub_groups, dict) else {}
    order = group.get("order")
    if not isinstance(order, list):
        order = list(items) + list(sub_groups)
    rows = []
    for entry in order:
        if entry in sub_groups:
            rows.append(_kindle_group_html(sub_groups[entry], books_by_id, urls))
        elif entry in books_by_id:
            rows.append(_kindle_book_row(books_by_id[entry], urls))
    return (
        f'<li class="k-shelf-group"><span class="k-lib-title k-shelf-group-name">'
        f'{name}</span><ul>{"".join(rows)}</ul></li>'
    )


def _kindle_shelf_html(books_by_id, shelf, urls: SiteURLs) -> str:
    """Render the user bookshelf (groups plus loose books) read-only."""
    if not isinstance(shelf, dict):
        return ""
    items = shelf.get("items")
    groups = shelf.get("groups")
    items = items if isinstance(items, list) else []
    groups = groups if isinstance(groups, dict) else {}
    order = shelf.get("order")
    if not isinstance(order, list):
        order = list(items) + list(groups)
    rows = []
    for entry in order:
        if entry in groups:
            rows.append(_kindle_group_html(groups[entry], books_by_id, urls))
        elif entry in books_by_id:
            rows.append(_kindle_book_row(books_by_id[entry], urls))
    return "".join(rows)


def render_kindle_library_page(
    books: Sequence[LibraryBook],
    urls: SiteURLs,
    shelf=None,
) -> str:
    """Render the dependency-free Kindle minimal library page.

    One plain row per book linking straight into that book's ``kindle.html``
    minimal reader, reusing the exact inline CSS/JS of the EPUBProcessor
    Kindle pages so legacy Kindle WebKit browsers get one consistent, ES5,
    no-/assets/ surface.  SSG writes this page next to ``index.html``; Server
    mode renders it at request time from the authenticated catalogue.

    ``shelf`` is the optional read-only bookshelf document (``items`` /
    ``groups`` / ``order``).  When present, the user's groups render first as
    plain nested lists, followed by the full book catalogue; group names are
    static text and nothing here mutates the shelf.  SSG passes no shelf
    because bookshelves are per-user Server data.
    """
    books_by_id = {book.book_id: book for book in books}
    shelf_html = (
        _kindle_shelf_html(books_by_id, shelf, urls) if shelf is not None else ""
    )
    all_rows = [
        _kindle_book_row(book, urls)
        for book in sorted(books, key=lambda book: book.book_id)
    ]
    all_list_html = (
        "\n".join(all_rows) if all_rows else '<li class="k-lib-empty">No books</li>'
    )
    if shelf_html:
        shelf_section = f'<p class="sec">Bookshelf</p>\n<ul>\n{shelf_html}\n</ul>'
        all_section = f'<p class="sec">All books</p>\n<ul>\n{all_list_html}\n</ul>'
    else:
        shelf_section = ""
        all_section = f'<ul>\n{all_list_html}\n</ul>'
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Library</title>
<style>
{_KINDLE_READER_CSS}
.k-lib-title{{display:block;font-weight:bold}}
.k-lib-authors{{display:block;color:#666;font-size:14px;font-weight:normal}}
body.dark .k-lib-authors{{color:#9a9a9a}}
.k-lib-empty{{padding:8px 0;color:#666}}
.k-shelf-group-name{{display:block;font-weight:bold;margin:8px 0 2px}}
</style>
</head>
<body class="light">
<header class="k-header">
<a href="index.html?full=1">Library</a>
<div class="k-controls">
    <button type="button" onclick="kTheme()" accesskey="t">Theme</button>
    <button type="button" onclick="kFont(-1)">A-</button>
    <button type="button" onclick="kFont(1)">A+</button>
</div>
</header>
<div class="k-toc">
{shelf_section}
{all_section}
</div>
<p class="k-footer"><a href="index.html?full=1">Open full library</a></p>
<script>
{_KINDLE_READER_JS}
</script>
</body>
</html>
"""


def render_library_shell(
    books: Sequence[LibraryBook],
    assets: PublishedAssets,
    urls: SiteURLs,
    deployment_mode: str,
    kindle: bool = False,
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
    # Legacy Kindle WebKit entry (opt-in via --kindle, SSG and Server): steer
    # real e-Ink Kindles to the dependency-free minimal library instead of the
    # full SPA; Kindle Fire (Silk) and ?full=1 keep the full UI. Runs before
    # the SPA loads. SSG writes kindle-library.html beside the shell; Server
    # renders it at /kindle-library.html.
    kindle_entry_script = """
<script>
(function () {
  var ua = navigator.userAgent.toLowerCase();
  if (ua.indexOf('kindle') === -1) return;
  if (ua.indexOf('silk') !== -1) return;
  if (location.search.indexOf('full=1') !== -1) return;
  location.replace('kindle-library.html');
})();
</script>""" if kindle else ""
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
// 立即应用主题，避免闪现
var theme = "light";

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
  }
} catch (e) {
  // localStorage 不可用时保持默认主题
}

// 使用 html 元素添加类名
var htmlElement = document.documentElement;
htmlElement.classList.add(theme + "-mode");
</script>
{kindle_entry_script}
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
        tag_text = html.escape(metadata_text(tag), quote=False)
        tag_attribute = html.escape(metadata_text(tag), quote=True)
        library_html += f"""<div class="tag-cloud-item" data-id="{tag_attribute}">{tag_text}</div>"""
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
{render_footer(datetime.now().year, release_api_url='/api/version' if deployment_mode == 'server' else '')}
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
    library_html = library_html.replace("{kindle_entry_script}", kindle_entry_script)
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
    # 不压缩 HTML：模板紧凑，实测 minify_html 对这类输出无收益，
    # 且 CSS/JS 压缩可能与 kindle 兼容性冲突，压缩依赖已移除。
    return library_html


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
    kindle: bool = False,
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
    html = render_library_shell(ordered_books, assets, urls, deployment_mode, kindle)
    _atomic_write_text(root / "index.html", html)
    if deployment_mode == "ssg" and kindle:
        _atomic_write_text(
            root / "kindle-library.html",
            render_kindle_library_page(ordered_books, urls),
        )
    _atomic_write_text(
        root / "book-metadata.json",
        json.dumps(metadata, ensure_ascii=False, separators=(",", ":")),
    )
