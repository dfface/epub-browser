import json
import html
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime
from itertools import groupby
from pathlib import Path
from typing import Optional, Sequence, Tuple
from types import SimpleNamespace
from urllib.parse import urlencode

from .asset_publisher import PublishedAssets, rewrite_asset_urls
from .book_sort import BOOK_SORT_LABEL, LIBRARY_SORT_OPTIONS, book_sort_options, library_sort
from .i18n_bundles import get_bundle, render_i18n_runtime_and_inline
from .kindle import _KINDLE_DASHBOARD_CSS, kindle_locale_script, kindle_message, render_kindle_dashboard_widgets, render_kindle_dock
from .locales import LOCALE_NATIVE_NAMES
from .server_chrome import (
    SERVER_ACCOUNT_CONTROL,
    SERVER_ACCOUNT_STYLESHEET,
    SERVER_AUTH_SCRIPT,
    SERVER_LOCALE_CONTROL,
    SERVER_LOCALE_SCRIPT,
    render_account_panel,
    render_vocabulary_assets,
    render_vocabulary_navigation,
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
    kindle_cover,
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
    chapter_count: Optional[int] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


def _kindle_book_row(book: LibraryBook, urls: SiteURLs, chapter=None) -> str:
    filename = "kindle.html" if chapter is None else f"kindle_chapter_{chapter}.html"
    fragment = "#resume" if chapter is not None else ""
    href = html.escape(urls.public(f"/book/{book.book_id}/{filename}{fragment}"), quote=True)
    title = html.escape(metadata_text(book.title), quote=False)
    authors = " &amp; ".join(
        html.escape(metadata_text(author), quote=False) for author in book.authors
    )
    cover_url = (
        urls.public(book.cover)
        if book.cover and book.cover.startswith(f"/book/{book.book_id}/") else None
    )
    count = f' data-chapters="{book.chapter_count}"' if book.chapter_count is not None else ""
    search = html.escape(" ".join((book.title, *book.authors, *book.tags)), quote=True)
    return (
        f'<li data-book="{html.escape(book.book_id, quote=True)}" data-search="{search}"{count}>'
        f'<a href="{href}">{kindle_cover(cover_url)}'
        f'<span class="k-lib-info"><strong class="k-lib-title">{title}</strong>'
        f'<span class="k-lib-authors">{authors}</span></span></a></li>'
    )


KINDLE_PAGE_SIZE = 12


def _kindle_page_count(total):
    return max(1, (total + KINDLE_PAGE_SIZE - 1) // KINDLE_PAGE_SIZE)


def _kindle_page(entries, requested):
    total = _kindle_page_count(len(entries))
    page = min(max(1, requested), total)
    offset = (page - 1) * KINDLE_PAGE_SIZE
    return entries[offset:offset + KINDLE_PAGE_SIZE], page, total


def _kindle_static_page_name(page):
    return "kindle-library.html" if page == 1 else f"kindle-library-{page}.html"


def _kindle_shelf_entries(shelf, books_by_id, path=()):
    """Yield visible book placements in shelf order with their group paths."""
    if not isinstance(shelf, dict):
        return
    items = shelf.get("items")
    groups = shelf.get("groups")
    items = items if isinstance(items, list) else []
    groups = groups if isinstance(groups, dict) else {}
    order = shelf.get("order")
    if not isinstance(order, list):
        order = list(items) + list(groups)
    for entry in order:
        if not isinstance(entry, str):
            continue
        if entry in groups:
            group = groups[entry]
            if isinstance(group, dict) and group.get("name"):
                yield from _kindle_shelf_entries(
                    group, books_by_id, (*path, (entry, metadata_text(group["name"]))),
                )
        elif entry in books_by_id:
            yield path, books_by_id[entry]


def _kindle_shelf_html(entries, urls: SiteURLs, depth=0) -> str:
    """Rebuild group headings around just the books on this page."""
    chunks = []
    for group, rows in groupby(entries, lambda item: item[0][depth] if len(item[0]) > depth else None):
        if group is None:
            chunks.extend(_kindle_book_row(book, urls) for _, book in rows)
        else:
            children = _kindle_shelf_html(rows, urls, depth + 1)
            chunks.append(
                f'<li class="k-shelf-group"><span class="k-lib-title k-shelf-group-name">'
                f'{html.escape(group[1])}</span><ul>{children}</ul></li>'
            )
    return "".join(chunks)


_KINDLE_LOCAL_CATALOG_JS = r"""
(function () {
  var size = %s;
  var metadata;
  var callbacks = [];
  var recent = document.getElementById('kRecent');
  var catalog = document.getElementById('kCatalog');
  var pager = document.getElementById('kCatalogPager');
  var form = document.getElementById('kBookSearch');
  var input = document.getElementById('kFindBooks');
  var sort = document.getElementById('kBookSort');
  var submittedSort;
  var requestGeneration = 0;
  var originalCatalog = catalog.innerHTML;
  var originalPager = pager.innerHTML;
  var results = [];
  var query = '';
  var resultPage = 1;

  function loadBooks(callback) {
    if (metadata) return callback(metadata);
    callbacks.push(callback);
    if (callbacks.length > 1) return;
    function finish(books) {
      metadata = books;
      var pending = callbacks;
      callbacks = [];
      for (var i = 0; i < pending.length; i++) pending[i](books);
    }
    try {
      var xhr = new XMLHttpRequest();
      xhr.open('GET', 'book-metadata.json', true);
      xhr.onreadystatechange = function () {
        if (xhr.readyState !== 4) return;
        var books = null;
        if (xhr.status === 200 || xhr.status === 0) {
          try { books = JSON.parse(xhr.responseText); } catch (error) {}
        }
        finish(books instanceof Array ? books : null);
      };
      xhr.send(null);
    } catch (error) { finish(null); }
  }

  function element(tag, style, text) {
    var node = document.createElement(tag);
    if (style) node.className = style;
    if (text) node.textContent = text;
    return node;
  }

  function row(book, chapter) {
    var entry = element('li');
    entry.setAttribute('data-book', book.hash);
    var link = element('a');
    var page = chapter === undefined ? 'kindle.html' : 'kindle_chapter_' + chapter + '.html#resume';
    link.href = 'book/' + encodeURIComponent(book.hash) + '/' + page;
    var cover = element('span', 'k-cover' + (book.cover ? '' : ' k-cover-placeholder'));
    if (book.cover) {
      var image = element('img');
      image.src = book.cover;
      image.alt = '';
      cover.appendChild(image);
    }
    cover.setAttribute('aria-hidden', 'true');
    link.appendChild(cover);
    var info = element('span', 'k-lib-info');
    info.appendChild(element('strong', 'k-lib-title', book.title));
    info.appendChild(element('span', 'k-lib-authors', book.authors.join(' & ')));
    link.appendChild(info);
    entry.appendChild(link);
    return entry;
  }

  function renderRecent() {
    var order = (getCookie(kHistoryKey()) || '').split(',');
    var saved = {};
    var cookies = document.cookie.split(';');
    for (var i = 0; i < cookies.length; i++) {
      var parts = cookies[i].match(/^\s*([^=]+)=chapter_([0-9]+)[.]html$/);
      if (parts) saved[':' + parts[1]] = Number(parts[2]);
    }
    var visible = {};
    var pageRows = catalog.querySelectorAll('[data-book]');
    for (var j = 0; j < pageRows.length; j++) {
      var id = pageRows[j].getAttribute('data-book');
      visible[':' + id] = pageRows[j];
    }
    // The full static reader also writes chapter cookies, without the Kindle MRU.
    for (var key in saved) if (saved.hasOwnProperty(key)) order.push(key.slice(1));
    function draw(books) {
      var byId = {};
      for (var i = 0; books && i < books.length; i++) byId[':' + books[i].hash] = books[i];
      recent.innerHTML = '';
      for (var j = 0; j < order.length && recent.children.length < 5; j++) {
        var key = ':' + order[j];
        if (!saved.hasOwnProperty(key)) continue;
        var chapter = saved[key];
        delete saved[key];
        var current = visible[key];
        var book = byId[key];
        if (current) {
          var count = current.getAttribute('data-chapters');
          if (count !== null && chapter >= Number(count)) continue;
          var copy = current.cloneNode(true);
          var link = copy.getElementsByTagName('a')[0];
          link.href = link.href.replace(/kindle[.]html$/, 'kindle_chapter_' + chapter + '.html#resume');
          recent.appendChild(copy);
        } else if (book && book.format === 'epub' &&
                   (typeof book.chapterCount !== 'number' || chapter < book.chapterCount)) {
          recent.appendChild(row(book, chapter));
        }
      }
      document.getElementById('kRecentEmpty').style.display = recent.children.length ? 'none' : '';
      if (window.kShowLibraryPanel) window.kShowLibraryPanel();
    }
    for (var key in saved) {
      if (saved.hasOwnProperty(key) && !visible[key]) {
        loadBooks(draw);
        return;
      }
    }
    draw(null);
  }

  function drawResults() {
    catalog.innerHTML = '';
    pager.innerHTML = '';
    if (!results.length) {
      var empty = element('li');
      empty.setAttribute('data-i18n', 'noResults');
      catalog.appendChild(empty);
      kLocalize(catalog);
      return;
    }
    var total = Math.ceil(results.length / size);
    var offset = (resultPage - 1) * size;
    for (var i = offset; i < Math.min(results.length, offset + size); i++) catalog.appendChild(row(results[i]));
    if (total < 2) return;
    var controls = element('div', 'k-pager');
    function button(step, key, arrow) {
      var control = element('button', 'k-control', arrow);
      control.type = 'button';
      control.setAttribute('data-i18n-aria-label', key);
      control.disabled = resultPage + step < 1 || resultPage + step > total;
      control.onclick = function () {
        resultPage += step;
        drawResults();
        window.scrollTo(0, 0);
      };
      return control;
    }
    var position = element('span', '', resultPage + ' / ' + total);
    position.setAttribute('data-i18n-aria-label', 'pageOf');
    position.setAttribute('data-page', resultPage);
    position.setAttribute('data-total', total);
    controls.appendChild(button(-1, 'previousPage', '‹'));
    controls.appendChild(position);
    controls.appendChild(button(1, 'nextPage', '›'));
    pager.appendChild(controls);
    kLocalize(pager);
  }

  function renderCatalog() {
    var generation = ++requestGeneration;
    if (!query && submittedSort === 'manual' && !window.EpubBrowserBookSort.manualOrder().length) {
      catalog.innerHTML = originalCatalog;
      pager.innerHTML = originalPager;
      kLocalize(catalog);
      kLocalize(pager);
      return;
    }
    loadBooks(function (books) {
      if (generation !== requestGeneration) return;
      if (!books) {
        // File browsers may block XHR. Keep the generated catalogue and pager usable.
        catalog.innerHTML = originalCatalog;
        pager.innerHTML = originalPager;
        var rows = catalog.children;
        for (var i = 0; i < rows.length; i++) {
          var text = rows[i].getAttribute('data-search') || '';
          rows[i].style.display = text.toLowerCase().indexOf(query) >= 0 ? '' : 'none';
        }
        kLocalize(catalog);
        kLocalize(pager);
        return;
      }
      var matches = books.filter(function(book) {
        if (book.format !== 'epub') return false;
        var haystack = [book.title].concat(book.authors, book.tags).join(' ').toLowerCase();
        return haystack.indexOf(query) >= 0;
      });
      results = window.EpubBrowserBookSort.sortBooks(matches, submittedSort, document.documentElement.lang);
      drawResults();
    });
  }

  form.style.display = 'block';
  var preferenceKey = kHistoryKey() + '_sort';
  var savedSort = getCookie(preferenceKey);
  if (savedSort) sort.value = savedSort;
  if (!sort.value) sort.value = 'manual';
  submittedSort = sort.value;
  form.onsubmit = function () {
    query = input.value.replace(/^\s+|\s+$/g, '').toLowerCase();
    submittedSort = sort.value;
    setCookie(preferenceKey, submittedSort, 365);
    resultPage = 1;
    renderCatalog();
    return false;
  };
  if (submittedSort !== 'manual' || window.EpubBrowserBookSort.manualOrder().length) renderCatalog();
  window.kOnLocaleChange(function () {
    if (submittedSort !== 'manual') renderCatalog();
  });
  renderRecent();
  var previousPageShow = window.onpageshow;
  window.onpageshow = function (event) {
    if (previousPageShow) previousPageShow(event);
    if (event && event.persisted) renderRecent();
  };
})();
"""


_KINDLE_LIBRARY_NAV_JS = r"""
(function () {
  var navigation = document.getElementById('kLibraryNav');
  var tabs = navigation.getElementsByTagName('a');
  var recent = document.getElementById('kRecent');
  var current = '';
  function showPanel() {
    var requested = location.hash.slice(1);
    if (requested === 'kContinue' || requested === 'kAllBooks' || requested === 'kBookshelf') current = requested;
    var selected = document.getElementById(current) ? current : (recent.children.length ? 'kContinue' : 'kAllBooks');
    for (var i = 0; i < tabs.length; i++) {
      var panel = document.getElementById(tabs[i].hash.slice(1));
      var active = panel && panel.id === selected;
      if (panel) panel.style.display = active ? 'block' : 'none';
      if (active) tabs[i].setAttribute('aria-current', 'page');
      else tabs[i].removeAttribute('aria-current');
    }
  }
  showPanel();
  window.kShowLibraryPanel = showPanel;
  for (var i = 0; i < tabs.length; i++) {
    tabs[i].onclick = function (event) {
      if (event && (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey)) return;
      if (window.history && history.pushState) {
        if (location.hash !== this.hash) history.pushState(null, '', this.hash);
        showPanel();
        window.scrollTo(0, 0);
        return false;
      }
    };
  }
})();
"""


_KINDLE_DOCK_JS = """
(function () {
  var dock = document.getElementById('kDock');
  var links = dock.getElementsByTagName('a');
  var views = document.querySelectorAll('[data-k-view]');
  var library = document.getElementById('kLibraryView');
  var libraryHash = '';
  function sync() {
    var requested = location.hash.slice(1);
    var inLibrary = requested === 'kContinue' || requested === 'kBookshelf' || requested === 'kAllBooks';
    if (inLibrary) libraryHash = location.hash;
    var target = inLibrary ? library : document.getElementById(requested);
    if (!target || target.getAttribute('data-k-view') === null) {
      target = document.getElementById(dock.getAttribute('data-default'));
    }
    for (var i = 0; i < views.length; i++) views[i].style.display = views[i] === target ? 'block' : 'none';
    for (var j = 0; j < links.length; j++) {
      if (links[j].hash === '#' + target.id) links[j].setAttribute('aria-current', 'page');
      else links[j].removeAttribute('aria-current');
    }
    if (target === library && window.kShowLibraryPanel) window.kShowLibraryPanel();
    if (target.id === 'kDashboardWidgets' && window.kActivateDashboard) window.kActivateDashboard();
    window.scrollTo(0, 0);
  }
  for (var i = 0; i < links.length; i++) {
    links[i].onclick = function (event) {
      if (event && (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey)) return;
      var current = location.hash;
      if (current === '#kContinue' || current === '#kBookshelf' || current === '#kAllBooks') libraryHash = current;
      var hash = this.hash === '#kLibraryView' && libraryHash ? libraryHash : this.hash;
      if (window.history && history.pushState) {
        if (location.hash !== hash) history.pushState(null, '', hash);
        sync();
        return false;
      }
      if (location.hash !== hash) location.hash = hash;
      else sync();
      return false;
    };
  }
  window.onhashchange = sync;
  window.onpopstate = sync;
  sync();
})();
"""


def _kindle_library_locale_script(server_mode):
    keys = (
        "library", "continue", "allBooks", "emptyRecent", "emptyLibrary", "fullLibrary", "theme",
        "search", "noResults", "settings", "fontFamily", "language", "light",
        "sepia", "dark", "bookDefault", "serif", "sans", "pageMode", "tapTurn", "previousPage",
        "nextPage", "pageOf",
    )
    if server_mode:
        keys += (
            "bookshelf", "emptyShelf", "screensaver", "calendar", "memo", "pomodoro", "reset",
            "agenda", "noEvents", "calendarUnavailable", "pomoStart", "pomoPause", "pomoResume",
            "pomoFocus", "pomoBreak", "pomoComplete", "pomoFocusMinutes", "pomoBreakMinutes", "pomoRounds",
        )
    return kindle_locale_script(
        lambda locale: {
            **{key: kindle_message(locale, key) for key in keys},
            **{key: get_bundle(locale).get(key) or get_bundle("en")[key]
               for key in (BOOK_SORT_LABEL, "library.sort.apply", *LIBRARY_SORT_OPTIONS.values())},
        },
        use_initial_locale=server_mode,
    )


def _kindle_pager(page, total, href, copy):
    if total == 1:
        return ""

    def control(target, key, arrow):
        attrs = f'class="k-control" data-i18n-aria-label="{key}" aria-label="{copy(key)}"'
        if target < 1 or target > total:
            return f'<span {attrs} aria-disabled="true">{arrow}</span>'
        return f'<a {attrs} href="{html.escape(href(target), quote=True)}">{arrow}</a>'

    label = copy("pageOf").replace("{number}", str(page)).replace("{total}", str(total))
    return (
        '<div class="k-pager">'
        + control(page - 1, "previousPage", "‹")
        + f'<span data-i18n-aria-label="pageOf" aria-label="{label}" data-page="{page}" '
          f'data-total="{total}">{page} / {total}</span>'
        + control(page + 1, "nextPage", "›")
        + '</div>'
    )


def render_kindle_library_page(
    books: Sequence[LibraryBook],
    urls: SiteURLs,
    shelf=None,
    recent=None,
    locale="en",
    dashboard=None,
    show_dashboard=False,
    catalog_page=1,
    shelf_page=1,
    query="",
    static_catalog_total=None,
    sort="manual",
) -> str:
    """Render the shared Kindle bookshelf with local or account progress."""
    books_by_id = {book.book_id: book for book in books if book.source_format == EPUB_FORMAT}

    def copy(key):
        return html.escape(kindle_message(locale, key))

    server_mode = recent is not None
    sort = library_sort(sort)
    catalogue_books = books_by_id.values()
    if not server_mode and static_catalog_total is None:
        catalogue_books = sorted(catalogue_books, key=lambda book: book.book_id)
    shelf_entries, shelf_page, shelf_total = _kindle_page(
        list(_kindle_shelf_entries(shelf, books_by_id)), shelf_page,
    )
    shelf_html = _kindle_shelf_html(shelf_entries, urls)
    query = query.strip()[:200]
    needle = query.casefold()
    catalog = [
        book for book in catalogue_books
        if not needle or needle in " ".join((book.title, *book.authors, *book.tags)).casefold()
    ]
    if static_catalog_total is None:
        catalog, catalog_page, catalog_total = _kindle_page(catalog, catalog_page)
    else:
        # The static publisher already sliced the sorted EPUB catalogue.
        catalog_total = static_catalog_total
    all_rows = "".join(_kindle_book_row(book, urls) for book in catalog)
    recent_rows = "".join(
        _kindle_book_row(books_by_id[book_id], urls, chapter)
        for book_id, chapter in (recent or ())
        if book_id in books_by_id
    )
    library_url = urls.public("/kindle-library.html")

    def paged_url(section, page):
        if not server_mode:
            return urls.public("/" + _kindle_static_page_name(page)) + "#kAllBooks"
        params = {
            "catalog_page": page if section == "kAllBooks" else catalog_page,
            "shelf_page": page if section == "kBookshelf" else shelf_page,
        }
        if sort != "manual":
            params["sort"] = sort
        if query:
            params["q"] = query
        return library_url + "?" + urlencode(params) + "#" + section

    catalog_pager = _kindle_pager(
        catalog_page, catalog_total, lambda page: paged_url("kAllBooks", page), copy,
    )
    shelf_link = (
        f'<a class="k-control" href="#kBookshelf" data-i18n="bookshelf">{copy("bookshelf")}</a>'
        if server_mode else ""
    )
    empty_shelf = f'<li data-i18n="emptyShelf">{copy("emptyShelf")}</li>'
    shelf_section = (
        f'<section id="kBookshelf" class="k-library-panel" data-i18n-aria-label="bookshelf">'
        f'<ul class="k-shelf-list">{shelf_html or empty_shelf}</ul>'
        + _kindle_pager(shelf_page, shelf_total, lambda page: paged_url("kBookshelf", page), copy)
        + '</section>'
        if server_mode else ""
    )
    language_options = "".join(
        f'<option value="{code}"{" selected" if code == locale else ""}>{html.escape(name)}</option>'
        for code, name in LOCALE_NATIVE_NAMES.items()
    )
    dashboard_html, dashboard_js = (
        render_kindle_dashboard_widgets(dashboard, locale, show_dashboard)
        if dashboard is not None else ("", "")
    )
    default_view = "kDashboardWidgets" if show_dashboard else "kLibraryView"
    if show_dashboard and dashboard["pomodoro"] and not any(dashboard[key] for key in ("clock", "calendar", "memo")):
        default_view = "kPomodoro"
    library_style = ' style="display:none"' if show_dashboard else ""
    no_recent = "" if recent_rows else f'<p id="kRecentEmpty" data-i18n="emptyRecent">{copy("emptyRecent")}</p>'
    empty_key = "noResults" if query else "emptyLibrary"
    empty_library = f'<li data-i18n="{empty_key}">{copy(empty_key)}</li>'
    local_scripts = ""
    if not server_mode:
        sort_script = (Path(__file__).parent / "assets" / "book-sort.js").read_text(encoding="utf-8")
        local_scripts = sort_script + (_KINDLE_LOCAL_CATALOG_JS % KINDLE_PAGE_SIZE)
    sort_label = html.escape(get_bundle(locale).get(BOOK_SORT_LABEL) or get_bundle("en")[BOOK_SORT_LABEL])
    sort_options = book_sort_options(LIBRARY_SORT_OPTIONS, sort, locale)
    dashboard_css = _KINDLE_DASHBOARD_CSS if dashboard is not None else ""
    return f"""<!DOCTYPE html>
<html lang="{locale}">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title data-i18n="library">{copy("library")}</title>
<style>
{_KINDLE_READER_CSS}
.k-library{{box-sizing:border-box;max-width:720px;margin:0 auto;padding:14px 14px 76px;font:16px/1.4 Arial,sans-serif}}
.k-library-head{{overflow:hidden;margin-bottom:10px}}
.k-library-head h1{{margin:4px 0;font:700 1.85em/1.25 Arial,sans-serif;letter-spacing:-.02em}}

.k-library-tabs{{padding:4px;white-space:normal}}
.k-library-tabs a{{display:inline-block;box-sizing:border-box;min-height:44px;padding:11px 12px;
  border-color:transparent;color:inherit;text-decoration:none;font-size:.91em}}
.k-library-tabs a[aria-current]{{background:#111;color:#fff;font-weight:bold}}
body.dark .k-library-tabs a[aria-current]{{background:#eee;color:#111}}
.k-library-panel{{padding:12px 0;min-height:110px}}
.k-library-panel ul{{list-style:none;padding:0;margin:0}}
.k-library-panel a{{display:block;color:inherit;text-decoration:none}}
.k-lib-info,.k-lib-title,.k-lib-authors{{display:block;word-wrap:break-word}}
.k-lib-authors{{font-size:.83em;margin-top:3px;opacity:.85}}
.k-shelf-group-name{{display:block;margin:15px 0 2px;font-weight:bold}}
.k-shelf-list ul{{padding-left:12px;border-left:1px solid #888}}
.k-shelf-list a,#kRecent a{{overflow:hidden;padding:10px 0;min-height:44px;border-bottom:1px solid #888}}
.k-shelf-list .k-cover,#kRecent .k-cover{{float:left;width:42px;height:58px;margin-right:12px}}
#kRecent li:first-child a{{border:1px solid #aaa;border-bottom-width:2px;padding:14px;margin-bottom:6px}}
#kRecent li:first-child .k-cover{{width:75px;height:104px;margin-right:16px}}
#kRecent li:first-child .k-lib-title{{font:700 1.3em/1.3 Georgia,serif}}
#kBookSearch{{margin-bottom:14px}}
.k-catalog-sort{{display:table;width:100%;margin-top:8px}}
.k-catalog-sort label,.k-catalog-sort-action{{display:table-cell;vertical-align:middle}}
.k-catalog-sort label{{width:100%}}
.k-catalog-sort label span{{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0,0,0,0)}}
.k-catalog-sort-action{{padding-left:8px}}
.k-catalog-sort-action button{{white-space:nowrap}}
#kBookSort{{width:100%;max-width:100%;min-height:44px}}
body.dark #kBookSort option{{background:#161616;color:#eee}}
body.sepia #kBookSort option{{background:#f3e9d2;color:#3c2f1a}}
.k-pager{{display:table;width:100%;table-layout:fixed;margin:8px 0;text-align:center}}
.k-pager .k-control{{display:inline-block;width:60px;padding:6px 12px;font-size:1.3em}}
.k-pager>span[data-page]{{display:inline-block;min-width:94px;padding:0 10px}}
.k-pager [aria-disabled="true"],.k-pager button:disabled{{opacity:.4}}
#kFindBooks{{box-sizing:border-box;width:100%;min-height:44px;padding:8px 12px;border:1px solid #888;background:transparent;color:inherit;font:inherit}}
#kFindBooks::placeholder{{color:inherit;opacity:.8}}
#kCatalog li[data-book]{{display:inline-block;vertical-align:top;box-sizing:border-box;width:32%;margin:0 1.3% 8px 0}}
#kCatalog a{{box-sizing:border-box;min-height:174px;padding:9px 8px;border:1px solid #aaa;
  border-bottom-width:2px}}
#kCatalog .k-cover{{width:81px;max-width:100%;height:114px;margin:0 auto 8px}}
#kCatalog .k-lib-title{{display:-webkit-box;-webkit-box-orient:vertical;-webkit-line-clamp:2;
  min-height:2.5em;max-height:2.5em;overflow:hidden;line-height:1.25;font-size:.9em}}
#kCatalog .k-lib-authors{{min-height:1.2em;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
{dashboard_css}
.k-home-settings{{padding:12px 14px}}
.k-home-settings fieldset{{margin:0 0 12px;padding:0;border:0}}
.k-home-settings legend{{font-weight:bold;padding-bottom:5px}}
.k-home-settings button{{margin:2px}}
.k-home-settings button[aria-pressed="true"]{{border-color:currentColor;font-weight:bold;box-shadow:inset 0 0 0 1px currentColor}}
#kLanguage{{max-width:100%;min-width:154px;background:inherit}}
body.dark #kLanguage option{{background:#161616;color:#eee}}
body.sepia #kLanguage option{{background:#f3e9d2;color:#3c2f1a}}

@media (max-width:360px){{
    #kCatalog li[data-book]{{width:48%}}
    .k-library-tabs a{{padding-left:7px;padding-right:7px}}
}}
</style>
</head>
<body class="light">
<div class="k-library">
<main>
<section id="kLibraryView" data-k-view{library_style}>
<header class="k-library-head">
<h1 data-i18n="library">{copy("library")}</h1>
</header>
<nav class="k-library-tabs k-surface" id="kLibraryNav">
<a class="k-control" href="#kContinue" data-i18n="continue">{copy("continue")}</a>
{shelf_link}
<a class="k-control" href="#kAllBooks" data-i18n="allBooks">{copy("allBooks")}</a>
</nav>
<section id="kContinue" class="k-library-panel" data-i18n-aria-label="continue" aria-label="{copy("continue")}">
{no_recent}<ul id="kRecent">{recent_rows}</ul></section>
{shelf_section}
<section id="kAllBooks" class="k-library-panel" data-i18n-aria-label="allBooks" aria-label="{copy("allBooks")}">
<form id="kBookSearch" action="{library_url}#kAllBooks" method="get"{"" if server_mode else ' style="display:none"'}>
  <input type="search" class="k-control" id="kFindBooks" name="q" maxlength="200"
         value="{html.escape(query, quote=True)}" data-i18n-aria-label="search" data-i18n-placeholder="search"
         aria-label="{copy("search")}" placeholder="{copy("search")}">
  <input type="hidden" name="shelf_page" value="{shelf_page}">
  <div class="k-catalog-sort">
    <label for="kBookSort"><span data-i18n="{BOOK_SORT_LABEL}">{sort_label}</span>
      <select id="kBookSort" name="sort" class="k-control">{sort_options}</select>
    </label>
    <div class="k-catalog-sort-action">
      <button class="k-control" type="submit" data-i18n="library.sort.apply">{html.escape(get_bundle(locale).get("library.sort.apply") or get_bundle("en")["library.sort.apply"])}</button>
    </div>
  </div>
</form>
<ul id="kCatalog">{all_rows or empty_library}</ul>
<div id="kCatalogPager">{catalog_pager}</div>
</section>
</section>
{dashboard_html}
<section id="kHomeSettings" class="k-surface k-home-settings" data-k-view style="display:none">
<h1 data-i18n="settings">{copy("settings")}</h1>
<fieldset><legend data-i18n="theme">{copy("theme")}</legend>
<button type="button" class="k-control" data-k-theme="light" onclick="kSelectTheme('light')" data-i18n="light">{copy("light")}</button>
<button type="button" class="k-control" data-k-theme="sepia" onclick="kSelectTheme('sepia')" data-i18n="sepia">{copy("sepia")}</button>
<button type="button" class="k-control" data-k-theme="dark" onclick="kSelectTheme('dark')" data-i18n="dark">{copy("dark")}</button>
</fieldset>
<fieldset><legend data-i18n="fontFamily">{copy("fontFamily")}</legend>
<button type="button" class="k-control" data-k-font-choice="book" onclick="kSelectFont('book')" data-i18n="bookDefault">{copy("bookDefault")}</button>
<button type="button" class="k-control" data-k-font-choice="serif" onclick="kSelectFont('serif')" data-i18n="serif">{copy("serif")}</button>
<button type="button" class="k-control" data-k-font-choice="sans" onclick="kSelectFont('sans')" data-i18n="sans">{copy("sans")}</button>
</fieldset>
<fieldset><legend id="kLanguageLabel" data-i18n="language">{copy("language")}</legend>
<select id="kLanguage" class="k-control" aria-labelledby="kLanguageLabel" onchange="kSetLocale(this.value)">
{language_options}
</select>
</fieldset>
<p><button type="button" class="k-control" id="kReadingMode" onclick="kToggleReadingMode()" data-i18n="pageMode">{copy("pageMode")}</button>
<button type="button" class="k-control" id="kClickScroll" onclick="kToggleClickScroll()" data-i18n="tapTurn">{copy("tapTurn")}</button></p>
<a class="k-control" href="{urls.public('/index.html?full=1')}" data-i18n="fullLibrary">{copy("fullLibrary")}</a>
</section>
</main>
{render_kindle_dock(urls, locale, default_view=default_view, tools=dashboard)}
</div>
<script>
{_KINDLE_READER_JS}
{_kindle_library_locale_script(server_mode)}
{_KINDLE_LIBRARY_NAV_JS}
{local_scripts}
{dashboard_js}
{_KINDLE_DOCK_JS}
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
    ai_reading_enabled: bool = True,
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
    recent_reading_stylesheet = ""
    recent_reading_panel = ""
    recent_reading_script = ""
    recent_reading_start = ""
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
    if kindle and deployment_mode == "server":
        kindle_entry_script = kindle_entry_script.replace("'kindle-library.html'", "'kindle'")
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
        # Reading insights is independent of AI reading and must stay visible in
        # server mode regardless of the AI reading toggle.
        reading_insights_navigation = '''<button type="button" class="app-nav-link" data-reading-insights aria-haspopup="dialog"><i class="fas fa-chart-column" aria-hidden="true"></i><span data-i18n="readingInsights.navigation">Reading insights</span></button>'''
        if ai_reading_enabled:
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
        # The rail is Server-only: it reads per-user reading progress, which
        # never exists in SSG output.  It starts before the catalogue request so
        # the first metadata response can populate it without a second render.
        recent_reading_stylesheet = '<link rel="stylesheet" href="/assets/recent-reading.css">'
        recent_reading_panel = """
    <section id="recentReading" class="recent-reading" hidden aria-labelledby="recentReadingTitle">
      <h2 id="recentReadingTitle" class="recent-reading-title" data-i18n="library.recentReading.title">Continue reading</h2>
      <ul class="recent-reading-rail" data-recent-reading-list></ul>
    </section>"""
        recent_reading_script = '<script src="/assets/recent-reading.js" defer></script>'
        recent_reading_start = 'if (window.EpubRecentReading) window.EpubRecentReading.start(window);'
        server_account_stylesheet = SERVER_ACCOUNT_STYLESHEET
        server_account_control = SERVER_ACCOUNT_CONTROL
        server_account_panel = render_account_panel(kindle)
        server_auth_script = SERVER_AUTH_SCRIPT
        server_client_start = f"""
            if (!window.EpubBrowserAuth) return;
            window.EpubBrowserAuth.init().then(function(session) {{
                if (!session) return;
                {recent_reading_start}
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
{I18N_RUNTIME_BOOTSTRAP}
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
{recent_reading_stylesheet}
<script src="/assets/theme-bootstrap.js"></script>
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
            {render_vocabulary_navigation() if deployment_mode == "server" else ""}
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
{recent_reading_panel}
{server_progress_panel}
    <div class="controls" data-id="controls">
        <div class="library-toolbar">
            <div class="search-container">
                <input type="search" class="search-box" placeholder="Search by book title, author, or tag..."
                    aria-label="Search by book title, author, or tag"
                    data-i18n-placeholder="library.searchPlaceholder" data-i18n-aria-label="library.searchPlaceholder">
                <i class="fas fa-search search-icon" aria-hidden="true"></i>
            </div>
            <div class="library-sort-control">
                <label class="sr-only" for="libraryBookSort" data-i18n="{BOOK_SORT_LABEL}">Sort by</label>
                <i class="fas fa-sort library-sort-icon" aria-hidden="true"></i>
                <select id="libraryBookSort" disabled>{book_sort_options(LIBRARY_SORT_OPTIONS, "manual")}</select>
                <i class="fas fa-chevron-down library-sort-chevron" aria-hidden="true"></i>
            </div>
        </div>
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
    <div class="book-grid" id="libraryBooks" data-id="book-grid" tabindex="-1">
        <div class="book-grid-loading" id="bookGridLoading" data-id="bookGridLoading" role="status" aria-label="Loading library" data-i18n-aria-label="library.loading">
            <div class="loading-spinner"></div>
        </div>
"""
    library_html += f"""
    </div>
    <nav id="libraryPager" class="library-pager" aria-label="Library pages" data-i18n-aria-label="library.pagination" hidden>
        <button id="libraryPreviousPage" type="button" aria-controls="libraryBooks" aria-label="Previous page" data-i18n-aria-label="reader.previousPage"><i class="fas fa-chevron-left" aria-hidden="true"></i></button>
        <span id="libraryPageStatus" role="status" data-i18n="pdf.pageOf"></span>
        <button id="libraryNextPage" type="button" aria-controls="libraryBooks" aria-label="Next page" data-i18n-aria-label="reader.nextPage"><i class="fas fa-chevron-right" aria-hidden="true"></i></button>
        <form id="libraryJumpForm" class="library-jump">
            <input id="libraryJumpInput" type="number" min="1" max="1" step="1" required inputmode="numeric"
                aria-label="Page number" data-i18n-aria-label="reader.currentPage" aria-describedby="libraryPageStatus">
            <button type="submit" aria-controls="libraryBooks" data-i18n="reader.jump">Jump</button>
        </form>
    </nav>
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
{vocabulary_assets}
    <script src="/assets/theme.js" defer></script>
    <script src="/assets/dialog.js" defer></script>
    <script src="/assets/version-check.js" defer></script>
    <script>window.EpubBrowserLibraryFeatureAssets={library_feature_assets};</script>
    <script src="/assets/library-feature-loader.js" defer></script>
    <script src="/assets/book-sort.js" defer></script>
    <script src="/assets/library.js?v=13" defer></script>
{ai_reading_script}
{server_progress_script}
{recent_reading_script}
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
    library_html = library_html.replace("{recent_reading_stylesheet}", recent_reading_stylesheet)
    library_html = library_html.replace("{recent_reading_panel}", recent_reading_panel)
    library_html = library_html.replace("{recent_reading_script}", recent_reading_script)
    library_html = library_html.replace("{recent_reading_start}", recent_reading_start)
    library_html = library_html.replace("{library_feature_assets}", library_feature_assets)
    library_html = library_html.replace("{bookshelf_data_actions}", bookshelf_data_actions)
    library_html = library_html.replace("{server_account_panel}", server_account_panel)
    library_html = library_html.replace("{server_account_stylesheet}", server_account_stylesheet)
    library_html = library_html.replace("{server_auth_script}", server_auth_script)
    library_html = library_html.replace("{server_client_start}", server_client_start)
    library_html = library_html.replace("{ai_reading_stylesheet}", ai_reading_stylesheet)
    library_html = library_html.replace("{ai_reading_navigation}", ai_reading_navigation)
    library_html = library_html.replace(
        "{vocabulary_assets}",
        render_vocabulary_assets(assets) if deployment_mode == "server" else "",
    )
    library_html = library_html.replace("{reading_insights_navigation}", reading_insights_navigation)
    library_html = library_html.replace("{ai_reading_script}", ai_reading_script)
    library_html = library_html.replace("{SERVER_LOCALE_SCRIPT}", SERVER_LOCALE_SCRIPT)
    library_html = library_html.replace(
        "{I18N_RUNTIME_BOOTSTRAP}",
        render_i18n_runtime_and_inline(urls.base_path, deployment_mode=deployment_mode),
    )
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
            "created_at": book.created_at,
            "updated_at": book.updated_at,
        }
        for book in ordered_books
    ]
    html = render_library_shell(ordered_books, assets, urls, deployment_mode, kindle, ai_reading_enabled=False)
    _atomic_write_text(root / "index.html", html)
    if deployment_mode == "ssg" and kindle:
        catalog = tuple(book for book in ordered_books if book.source_format == EPUB_FORMAT)
        total = _kindle_page_count(len(catalog))
        for page in range(1, total + 1):
            offset = (page - 1) * KINDLE_PAGE_SIZE
            _atomic_write_text(
                root / _kindle_static_page_name(page),
                render_kindle_library_page(
                    catalog[offset:offset + KINDLE_PAGE_SIZE], urls,
                    catalog_page=page, static_catalog_total=total,
                ),
            )
        for item, book in zip(metadata, ordered_books):
            if book.source_format == EPUB_FORMAT and book.chapter_count is not None:
                item["chapterCount"] = book.chapter_count
    _atomic_write_text(
        root / "book-metadata.json",
        json.dumps(metadata, ensure_ascii=False, separators=(",", ":")),
    )
