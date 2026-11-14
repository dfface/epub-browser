"""Shared reading pages for EPUB and PDF in both deployment modes."""

import html
import json
import os
import posixpath
import urllib.parse
from datetime import datetime
from typing import Optional, TYPE_CHECKING

from .asset_publisher import PublishedAssets, rewrite_asset_urls
from .epub_sanitization import metadata_text, sanitize_html_fragment
from .i18n_bundles import get_bundle, render_i18n_runtime_and_inline
from .kindle import kindle_locale_script, kindle_message, render_kindle_dock
from .locales import normalize_locale
from .models import BookMetadata
from .reporting import Reporter
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
from .source_format import EPUB_FORMAT, PDF_FORMAT
from .urls import SiteURLs, rewrite_root_urls
from .version import render_footer

if TYPE_CHECKING:
    from .pdf_processor import PDFMetadata


_READER_FONT_SIZES_REM = (0.9, 1.1, 1.3, 1.5, 1.7, 1.9, 2.2, 2.5, 2.8, 3.2, 3.6, 4.0)
_DEFAULT_READER_FONT_LEVEL = 3

# Shared by the Server EPUB book dialog and chapter drawer.
_BOOK_SEARCH_BODY = '''
        <form class="book-search-form" id="bookSearchForm" role="search">
            <label class="visually-hidden" for="bookSearchInput" data-i18n="book.search">Search this book</label>
            <input id="bookSearchInput" type="search" autocomplete="off" enterkeyhint="search" maxlength="128" placeholder="Search this book" data-i18n-placeholder="book.searchPlaceholder">
            <button class="book-search-submit" type="submit" aria-label="Search this book" data-i18n-aria-label="book.search"><i class="fas fa-magnifying-glass" aria-hidden="true"></i></button>
        </form>
        <p class="book-search-status" id="bookSearchStatus" role="status"></p>
        <ul class="toc-list book-search-results" id="bookSearchResults"></ul>
        <form class="book-search-pagination" id="bookSearchPagination" hidden>
            <button class="book-search-page-btn" id="bookSearchPrev" type="button" aria-label="Previous page" data-i18n-aria-label="book.searchPrevPage"><i class="fas fa-chevron-left" aria-hidden="true"></i></button>
            <label class="visually-hidden" for="bookSearchPageInput" data-i18n="reader.currentPage">Current page</label>
            <input class="book-search-page-input" id="bookSearchPageInput" type="number" min="1" step="1" required inputmode="numeric" enterkeyhint="go" aria-describedby="bookSearchPageStatus">
            <span class="book-search-page-total" id="bookSearchPageTotal" aria-hidden="true"></span>
            <span class="visually-hidden" id="bookSearchPageStatus" aria-live="polite"></span>
            <button class="book-search-page-btn book-search-page-jump" id="bookSearchPageJump" type="submit" data-i18n="reader.jump">Jump</button>
            <button class="book-search-page-btn" id="bookSearchNext" type="button" aria-label="Next page" data-i18n-aria-label="book.searchNextPage"><i class="fas fa-chevron-right" aria-hidden="true"></i></button>
        </form>
'''

# Kindle minimal reader: a deliberately dependency-free surface for legacy
# Kindle WebKit browsers. All CSS/JS is inlined into the page, preferences and
# reading progress use cookies (no localStorage), and the script stays ES5
# (no let/const, arrow functions, Promise, or template literals). No CSS
# variables, box shadows, or rounded corners. Keep this minimal on purpose:
# it is a fallback, not a second full-featured reader.
_KINDLE_READER_CSS = """\
body{margin:0;padding:0;background-color:#fff!important;color:#111!important;font-family:Georgia,"Times New Roman",serif;font-size:16px;line-height:1.65}
body.sepia{background-color:#f3e9d2!important;color:#3c2f1a!important}
body.dark{background-color:#161616!important;color:#c9c9c9!important}
/* Nested controls share an 8px corner inside 12px panels with a 4px inset. */
.k-surface,#kRecent li:first-child a,#kCatalog a{border-radius:12px}
.k-surface{box-sizing:border-box;border:1px solid #aaa;border-bottom-width:2px;background:#fff}
body.dark .k-surface{background:#161616;border-color:#777}
body.sepia .k-surface{background:#f3e9d2;border-color:#86795e}
.k-control{display:inline-block;box-sizing:border-box;min-height:44px;padding:10px 14px;
  color:inherit;background:transparent;border:1px solid #888;border-radius:8px;text-decoration:none;font:inherit}
.k-dock{position:fixed;z-index:5;bottom:0;left:0;right:0;margin:0 auto;
  max-width:720px;display:table;width:100%;height:58px;table-layout:fixed;padding:3px;border-radius:12px 12px 0 0;
  font:16px/1.3 Arial,sans-serif}
.k-dock>a{display:table-cell;height:49px;vertical-align:middle;text-align:center;color:inherit;
  text-decoration:none;font-size:.85em;word-wrap:break-word;border:1px solid transparent;border-radius:8px}
.k-dock [aria-current]{border-color:currentColor;font-weight:bold}
#kFontSizeValue{display:inline-block;min-width:48px;text-align:center}
.k-control:focus,.k-surface a:focus,.k-surface button:focus{outline:2px solid;outline-offset:2px}
.k-header{padding:10px 16px;border-bottom:1px solid;line-height:1.4;font-family:Arial,sans-serif}
.k-header a,.k-header button{display:inline-block;min-height:24px;padding:9px 0}
.k-header button{float:right;background:none;border:0;color:inherit;font:inherit;text-decoration:underline}
.k-cover{display:block;position:relative;box-sizing:border-box;overflow:hidden;border:1px solid #777;border-radius:3px;text-align:center}
.k-cover img{position:absolute;top:0;right:0;bottom:0;left:0;max-width:100%;max-height:100%;margin:auto}
.k-cover-placeholder:before{content:"";position:absolute;top:0;bottom:0;left:13%;border-left:1px solid #777}
.k-cover-placeholder:after{content:"";position:absolute;top:32%;left:28%;right:16%;height:14%;border-top:1px solid #777;border-bottom:1px solid #777}
.k-reader-header{max-width:680px;margin:0 auto}
.k-reader-settings{display:none;position:fixed;z-index:10}
body.sepia .k-header,body.dark .k-header{border-color:#666}
.k-header a{color:inherit;text-decoration:none;font-weight:bold;font-size:15px}
.k-content{padding:22px 20px 32px;max-width:640px;margin:0 auto;word-wrap:break-word;line-height:1.7}
body.sepia .k-content{color:#3c2f1a!important}
body.dark .k-content{color:#c9c9c9!important}
body[data-k-font="serif"] #kText,body[data-k-font="serif"] #kText *{font-family:Georgia,"Times New Roman",serif!important}
body[data-k-font="sans"] #kText,body[data-k-font="sans"] #kText *{font-family:Arial,sans-serif!important}
.k-content img{max-width:100%;height:auto}
.k-content a{color:inherit;text-decoration:underline}
.k-nav{overflow:hidden;border-top:1px solid #999;padding:12px 14px;max-width:640px;margin:0 auto}
body.sepia .k-nav,body.dark .k-nav{border-color:#666}
.k-nav a{color:inherit;text-decoration:none;padding:10px 14px;border:1px solid;font-family:Arial,sans-serif}
.k-nav .prev{float:left}
.k-nav .next{float:right}
.k-toc{padding:4px 16px 30px;max-width:640px;margin:0 auto}
.k-toc ul{list-style:none;margin:0;padding:0}
.k-toc li{padding:5px 0;line-height:1.45}
.k-toc li[class^="lvl-"] a{padding:9px 0;border-bottom:1px solid #888}
.k-toc li.lvl-1{padding-left:16px}
.k-toc li.lvl-2{padding-left:32px}
.k-toc li.lvl-3{padding-left:48px}
.k-toc a{color:inherit;text-decoration:none;display:block}
.k-toc .sec{color:#666;font-size:14px}
body.dark .k-toc .sec{color:#9a9a9a}
"""

_KINDLE_READER_JS = r"""
function getCookie(key) {
  var cookies = document.cookie.split('; ');
  for (var i = 0; i < cookies.length; i++) {
    var parts = cookies[i].split('=');
    if (parts[0] === key) {
      try { return decodeURIComponent(parts.slice(1).join('=')); } catch (error) { return null; }
    }
  }
  return null;
}
function setCookie(key, value, days) {
  var expires = '';
  if (days) {
    var date = new Date();
    date.setTime(date.getTime() + days * 86400000);
    expires = '; expires=' + date.toUTCString();
  }
  document.cookie = key + '=' + encodeURIComponent(value) + expires + '; path=/; SameSite=Lax';
}
function kHistoryKey() {
  var root = window.location.pathname.replace(/(?:book\/[^/]+\/)?[^/]+$/, '');
  return 'kindle_recent_' + encodeURIComponent(root);
}
function kRememberBook(book) {
  var key = kHistoryKey();
  var saved = (getCookie(key) || '').split(',');
  var recent = [book];
  for (var i = 0; i < saved.length && recent.length < 12; i++) {
    if (saved[i] && recent.indexOf(saved[i]) < 0) recent.push(saved[i]);
  }
  setCookie(key, recent.join(','), 365);
}
var K_THEMES = ['light', 'sepia', 'dark'];
var K_FONT_SIZES = [12, 14, 16, 18, 20, 22, 24, 28, 32, 36, 42, 48];
function kMarkChoice(attribute, value) {
  var choices = document.querySelectorAll('[' + attribute + ']');
  for (var i = 0; i < choices.length; i++) {
    choices[i].setAttribute('aria-pressed', choices[i].getAttribute(attribute) === value ? 'true' : 'false');
  }
}
function applyTheme(theme) {
  if (K_THEMES.indexOf(theme) === -1) theme = 'light';
  document.body.className = theme;
  kMarkChoice('data-k-theme', theme);
}
function kSelectTheme(theme) {
  setCookie('kindle_theme', theme, 365);
  applyTheme(theme);
}
function kApplyFontChoice(choice) {
  if (choice !== 'serif' && choice !== 'sans') choice = 'book';
  document.body.setAttribute('data-k-font', choice);
  kMarkChoice('data-k-font-choice', choice);
}
function kSelectFont(choice) {
  setCookie('kindle_font_family', choice, 365);
  kApplyFontChoice(choice);
  if (window.kReaderRelayout) window.kReaderRelayout();
}
function applyFont(size) {
  var text = document.getElementById('kText');
  if (!text) return;
  var pixels = K_FONT_SIZES[size - 1] || K_FONT_SIZES[2];
  text.style.setProperty('font-size', pixels + 'px', 'important');
  var value = document.getElementById('kFontSizeValue');
  if (value) value.textContent = pixels + ' px';
}
function kTheme() {
  var current = getCookie('kindle_theme') || 'light';
  var index = -1;
  for (var i = 0; i < K_THEMES.length; i++) {
    if (K_THEMES[i] === current) { index = i; break; }
  }
  if (index < 0) { index = 0; }
  var next = K_THEMES[(index + 1) % K_THEMES.length];
  kSelectTheme(next);
}
function kFont(delta) {
  var size = parseInt(getCookie('kindle_font_size') || '3', 10);
  if (isNaN(size)) { size = 3; }
  size = Math.max(1, Math.min(K_FONT_SIZES.length, size + delta));
  setCookie('kindle_font_size', String(size), 365);
  applyFont(size);
  if (window.kReaderRelayout) window.kReaderRelayout();
}
(function () {
  applyTheme(getCookie('kindle_theme') || 'light');
  kApplyFontChoice(getCookie('kindle_font_family'));
  var size = parseInt(getCookie('kindle_font_size') || '3', 10);
  if (isNaN(size)) { size = 3; }
  applyFont(size);
})();
// Keep the reader layout and tap navigation as independent preferences.
function kClickScrollOn() {
  return getCookie('kindle_click_scroll') !== 'off';
}
function kPagedMode() {
  var mode = getCookie('kindle_reading_mode');
  return mode ? mode === 'pages' : kClickScrollOn();
}
function kToggleClickScroll() {
  // Preserve the old layout when moving from the legacy combined setting.
  if (!getCookie('kindle_reading_mode')) {
    setCookie('kindle_reading_mode', kPagedMode() ? 'pages' : 'scroll', 365);
  }
  setCookie('kindle_click_scroll', kClickScrollOn() ? 'off' : 'on', 365);
  kSyncReaderToggles();
}
function kToggleReadingMode() {
  setCookie('kindle_reading_mode', kPagedMode() ? 'scroll' : 'pages', 365);
  kSyncReaderToggles();
  if (window.kReaderRelayout) window.kReaderRelayout();
}
function kSyncReaderToggles() {
  var tap = document.getElementById('kClickScroll');
  var mode = document.getElementById('kReadingMode');
  if (tap) tap.setAttribute('aria-pressed', kClickScrollOn() ? 'true' : 'false');
  if (mode) mode.setAttribute('aria-pressed', kPagedMode() ? 'true' : 'false');
}
function kSettingsOpen() {
  var settings = document.getElementById('kSettings');
  return settings && settings.style.display === 'block';
}
function kToggleSettings() {
  var settings = document.getElementById('kSettings');
  var backdrop = document.getElementById('kSettingsBackdrop');
  var toggle = document.getElementById('kSettingsToggle');
  if (!settings || !backdrop || !toggle) return;
  var open = !kSettingsOpen();
  settings.style.display = backdrop.style.display = open ? 'block' : 'none';
  toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
  if (open) settings.getElementsByTagName('button')[0].focus();
  else toggle.focus();
}
function kIsTurnNode(node) {
  while (node && node !== document.body) {
    var tag = String(node.tagName || '').toUpperCase();
    if (tag === 'A' || tag === 'BUTTON' || tag === 'INPUT' || tag === 'SELECT' || tag === 'TEXTAREA') return true;
    node = node.parentNode;
  }
  return false;
}
function kClickTurn(e) {
  var ev = e || window.event;
  if (!ev) return;
  if (kSettingsOpen() || !kClickScrollOn() || !window.kTurnPage) return;
  var viewport = document.getElementById('kViewport');
  var target = ev.target || ev.srcElement;
  if (!viewport || !target || !viewport.contains(target) || kIsTurnNode(target)) return;
  if (window.getSelection && String(window.getSelection())) return;
  var bounds = viewport.getBoundingClientRect();
  var width = bounds.right - bounds.left;
  if (width <= 0) return;
  var x = ev.clientX - bounds.left;
  if (x < width / 3) window.kTurnPage(-1);
  else if (x > width * 2 / 3) window.kTurnPage(1);
}
(function () {
  kSyncReaderToggles();
  document.onclick = kClickTurn;
})();
"""


_KINDLE_BOOK_CSS = """
.k-book{box-sizing:border-box;max-width:720px;margin:0 auto;padding:14px 14px 76px;font-family:Arial,sans-serif}
.k-book-hero{padding:16px;overflow:hidden;margin-bottom:14px}
.k-book-hero .k-cover{float:left;width:105px;height:146px;margin-right:18px}
.k-book-hero h1{font:700 1.55em/1.25 Georgia,serif;margin:4px 0 6px;word-wrap:break-word}
.k-book-hero p{font-size:.9em;margin:0 0 10px}
.k-book-action{display:inline-block;min-height:24px;padding:10px 16px;background:#111;color:#fff;
  font-size:16px;font-weight:bold;text-decoration:none;border:1px solid #111}
body.dark .k-book-action{background:#eee;color:#111;border-color:#eee}
.k-book h2{font-size:1.05em;margin:0;padding:10px 14px;border-bottom:1px solid #999}
.k-book .k-toc{padding:0 14px 6px;max-width:none}
.k-book .k-toc li{padding-top:0;padding-bottom:0}
.k-book .k-toc li a{padding-top:13px;padding-bottom:13px}
.k-book .k-toc a[aria-current="location"]{box-shadow:inset 3px 0 currentColor;
  padding-left:12px;padding-right:8px;font-weight:bold;background:#e9e9e9}
body.sepia .k-book .k-toc a[aria-current]{background:#e6d8ba}
body.dark .k-book .k-toc a[aria-current]{background:#333}
.k-book .k-toc .sec{padding-top:13px;font-weight:bold}
.k-book .k-toc li:last-child a{border-bottom:0}
@media (max-width:360px){.k-book-hero .k-cover{width:75px;height:104px;margin-right:12px}}
"""


_KINDLE_CHAPTER_CSS = """
.k-reader-header{box-sizing:border-box;padding:0 16px}
.k-reader-header a,.k-reader-header button{display:inline-block;box-sizing:border-box;min-height:44px;
  line-height:1.3;margin:0;padding:12px 0;font:inherit;color:inherit;background:none;border:0}
.k-reader-header button{float:right;font-weight:bold}
.k-reader-header a{float:left;margin-right:14px}
.k-reader-header .k-running-title{display:block;overflow:hidden;white-space:nowrap;text-overflow:ellipsis;padding:12px 0;font-weight:normal}
.k-reader-header,.k-reader-footer,.k-reader-settings{font:15px/1.4 Arial,sans-serif}
.k-reader-footer{text-align:center;overflow:hidden}
.k-reader-footer button{display:none}
#kSettingsBackdrop{display:none;position:fixed;top:0;right:0;bottom:0;left:0;z-index:9;background:transparent}
.k-reader-settings{box-sizing:border-box;left:8px;right:8px;bottom:8px;max-width:540px;max-height:82%;
  margin:0 auto;padding:10px 12px;text-align:left;overflow:auto}
.k-reader-settings a,.k-reader-settings button{display:inline-block;box-sizing:border-box;min-height:44px;
  padding:10px 12px;margin:3px;border:1px solid #888;color:inherit;background:none;font:inherit;text-decoration:none}
.k-settings-heading{overflow:hidden}
.k-settings-heading h2{display:inline-block;margin:12px 3px 6px;font-size:1.05em}
.k-settings-heading button{float:right;min-width:44px;font-size:1.25em;line-height:1}
.k-settings-modes{padding:6px 0}
.k-settings-modes button{font-weight:bold}
.k-settings-modes button[aria-pressed="true"]{color:#fff;background:#111;border-color:#111}
body.dark .k-settings-modes button[aria-pressed="true"]{color:#111;background:#eee;border-color:#eee}
.k-reader-settings .k-settings-links{border-top:1px solid #888;padding-top:6px}
.k-reader-header:after{content:"";display:block;clear:both}
.k-content img{height:auto}
#kViewport{min-height:100px}
body[data-k-reader] .k-reader-header{position:absolute;top:0;left:0;right:0;height:45px;max-width:680px}
body[data-k-reader] #kViewport{position:absolute;top:59px;bottom:61px;left:19px;right:19px;max-width:640px;
  margin:auto;overflow:auto;min-height:0}
body[data-k-reader="pages"] #kViewport{overflow:hidden}
body[data-k-reader="pages"] #kText{margin:0;padding:0;overflow:visible;min-height:0;
  -webkit-column-fill:auto;column-fill:auto}
body[data-k-reader="pages"] #kText img{max-height:calc(100vh - 124px);object-fit:contain}
body[data-k-reader] .k-reader-footer{position:absolute;bottom:0;left:0;right:0;box-sizing:border-box;
  height:48px;max-width:680px;margin:0 auto;border-top:1px solid #888}
body[data-k-reader] .k-reader-footer .k-chapter-links{display:none}
body[data-k-reader] .k-reader-footer button{display:block;box-sizing:border-box;width:18%;height:44px;
  border:0;background:none;color:inherit;font:inherit;font-size:1.45em}
body[data-k-reader] .k-reader-footer button:disabled{opacity:.4}
#kTurnBack{float:left}
#kTurnForward{float:right}
#kReaderPosition{display:inline-block;margin-top:13px}
body[data-k-reader] .k-content{padding:0 0 10px;min-height:85%;box-sizing:border-box}
@media (max-width:360px){body[data-k-reader] #kViewport{left:14px;right:14px}}
"""


_KINDLE_CHAPTER_JS = """
(function () {
  var viewport = document.getElementById('kViewport');
  var text = document.getElementById('kText');
  var previous = document.getElementById('kPrev');
  var next = document.getElementById('kNext');
  var back = document.getElementById('kTurnBack');
  var forward = document.getElementById('kTurnForward');
  var position = document.getElementById('kReaderPosition');
  var chapter = viewport.getAttribute('data-chapter');
  var cookie = 'kindle_pos_' + viewport.getAttribute('data-book');
  var chapterLabel = position.textContent;
  var columnGap = 28;
  var columnsSupported = 'webkitColumnWidth' in text.style || 'columnWidth' in text.style;
  var paged = false;
  var interacted = false;
  var saveTimer;
  var page = 0;
  var pageCount = 1;
  var stride = 1;
  var end = 0;
  function positionRatio() {
    return end ? (paged ? viewport.scrollLeft : viewport.scrollTop) / end : 0;
  }
  function measure() {
    if (paged) {
      stride = viewport.clientWidth + columnGap;
      end = Math.max(0, viewport.scrollWidth - viewport.clientWidth);
      pageCount = Math.round(end / stride) + 1;
    } else {
      var line = parseFloat(window.getComputedStyle(text).lineHeight) || 24;
      stride = Math.max(1, viewport.clientHeight - line);
      end = Math.max(0, viewport.scrollHeight - viewport.clientHeight);
      pageCount = Math.ceil(end / stride) + 1;
    }
  }
  function updatePosition() {
    var offset = paged ? viewport.scrollLeft : viewport.scrollTop;
    page = offset >= end - 1 ? pageCount - 1 : Math.round(offset / stride);
    var label = chapterLabel + ' · ' + (page + 1) + '/' + pageCount;
    if (position.textContent !== label) position.textContent = label;
    back.disabled = !previous && page === 0;
    forward.disabled = !next && page >= pageCount - 1;
  }
  function jump(index) {
    var offset = Math.max(0, Math.min(end, index * stride));
    if (paged) viewport.scrollLeft = offset;
    else viewport.scrollTop = offset;
    updatePosition();
  }
  function save() {
    if (saveTimer) window.clearTimeout(saveTimer);
    setCookie(cookie, chapter + ':' + positionRatio().toFixed(5), 365);
  }
  function turn(dir) {
    if (kSettingsOpen()) return;
    interacted = true;
    if (paged ? page + dir >= 0 && page + dir < pageCount
        : ((dir < 0 && viewport.scrollTop > 0) || (dir > 0 && viewport.scrollTop < end - 1))) {
      if (paged) jump(page + dir);
      else viewport.scrollTop += dir * stride;
      updatePosition();
      save();
      return;
    }
    var link = dir < 0 ? previous : next;
    if (link) {
      save();
      window.location.href = link.href + (dir < 0 ? '#kEnd' : '');
    }
  }
  function layout(ratio) {
    paged = columnsSupported && kPagedMode() && window.getComputedStyle(viewport).direction !== "rtl";
    document.body.setAttribute('data-k-reader', paged ? 'pages' : 'scroll');
    text.style.height = paged ? viewport.clientHeight + 'px' : '';
    text.style.width = paged ? viewport.clientWidth + 'px' : '';
    text.style.webkitColumnWidth = text.style.columnWidth = text.style.width;
    text.style.webkitColumnGap = text.style.columnGap = paged ? columnGap + 'px' : '';
    if (paged && viewport.scrollHeight > viewport.clientHeight + 3) {
      // Tall, indivisible EPUB content remains reachable by regular scrolling.
      paged = false;
      document.body.setAttribute('data-k-reader', 'scroll');
      text.style.height = text.style.width = '';
      text.style.webkitColumnWidth = text.style.columnWidth = '';
      text.style.webkitColumnGap = text.style.columnGap = '';
    }
    measure();
    if (paged) jump(Math.round(ratio * (pageCount - 1)));
    else {
      viewport.scrollTop = ratio * end;
      updatePosition();
    }
  }
  function revealAnchor() {
    var anchor = window.location.hash.slice(1);
    if (!anchor || anchor === 'kEnd' || anchor === 'resume') return;
    try { anchor = decodeURIComponent(anchor); } catch (error) {}
    var target = document.getElementById(anchor);
    if (!target || !viewport.contains(target)) return;
    if (paged) {
      var offset = viewport.scrollLeft + target.getBoundingClientRect().left
        - viewport.getBoundingClientRect().left;
      jump(Math.floor((offset + 1) / stride));
    } else target.scrollIntoView();
  }
  window.kTurnPage = turn;
  window.kReaderRelayout = function () {
    interacted = true;
    layout(positionRatio());
    save();
  };
  var ratio = 0;
  var fragment = window.location.hash;
  if (fragment === '#kEnd') ratio = 1;
  else if (fragment === '#resume') {
    var parts = (getCookie(cookie) || '').split(':');
    if (parts[0] === chapter) ratio = Math.max(0, Math.min(1, Number(parts[1]) || 0));
  }
  layout(ratio);
  revealAnchor();
  window.onhashchange = revealAnchor;
  viewport.onscroll = function () {
    if (!paged) updatePosition();
    if (saveTimer) window.clearTimeout(saveTimer);
    saveTimer = window.setTimeout(save, 300);
  };
  window.onresize = function () { layout(positionRatio()); };
  window.onpagehide = save;
  window.onload = function () {
    layout(interacted ? positionRatio() : ratio);
    if (!interacted) revealAnchor();
  };
  document.onkeydown = function (event) {
    var e = event || window.event;
    if (!e) return;
    if (kSettingsOpen()) {
      if (e.keyCode === 27) kToggleSettings();
      if (e.keyCode === 9) {
        var controls = document.getElementById('kSettings').querySelectorAll('button, a[href]');
        var first = controls[0];
        var last = controls[controls.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          last.focus();
          return false;
        }
        if (!e.shiftKey && document.activeElement === last) {
          first.focus();
          return false;
        }
      }
      return;
    }
    if (kIsTurnNode(e.target || e.srcElement)) return;
    if (e.keyCode === 37 || e.keyCode === 39) {
      turn(e.keyCode === 37 ? -1 : 1);
      if (e.preventDefault) e.preventDefault();
    }
  };
})();
"""


def kindle_cover(url):
    if not url:
        return '<span class="k-cover k-cover-placeholder" aria-hidden="true"></span>'
    return f'<span class="k-cover"><img src="{html.escape(url, quote=True)}" alt=""></span>'


# Kindle minimal-page UI strings, resolved server-side against the book's
# language so legacy e-Ink Kindles never have to load i18n-core.js.  Keys mirror
# the on-page [data-i18n] attributes; "previous"/"next" keep the arrows that
# the template renders inline.
_KINDLE_READER_I18N = {
    "en": {
        "continueReading": "Continue reading",
        "openFullReader": "Open full reader",
        "previous": "\u2039 Prev",
        "next": "Next \u203a",
        "theme": "Theme",
        "tapTurn": "Tap to turn",
    },
    "zh": {
        "continueReading": "继续阅读",
        "openFullReader": "打开完整阅读器",
        "previous": "\u2039 上一章",
        "next": "下一章 \u203a",
        "theme": "主题",
        "tapTurn": "点击翻页",
    },
    "zh-CN": {
        "continueReading": "继续阅读",
        "openFullReader": "打开完整阅读器",
        "previous": "\u2039 上一章",
        "next": "下一章 \u203a",
        "theme": "主题",
        "tapTurn": "点击翻页",
    },
    "zh-TW": {
        "continueReading": "繼續閱讀",
        "openFullReader": "開啟完整閱讀器",
        "previous": "\u2039 上一章",
        "next": "下一章 \u203a",
        "theme": "主題",
        "tapTurn": "點擊翻頁",
    },
    "ja": {
        "continueReading": "続きを読む",
        "openFullReader": "フルリーダーを開く",
        "previous": "\u2039 前へ",
        "next": "次へ \u203a",
        "theme": "テーマ",
        "tapTurn": "タップでめくる",
    },
    "ko": {
        "continueReading": "계속 읽기",
        "openFullReader": "전체 리더 열기",
        "previous": "\u2039 이전",
        "next": "다음 \u203a",
        "theme": "테마",
        "tapTurn": "탭으로 넘기기",
    },
    "es": {
        "continueReading": "Continuar leyendo",
        "openFullReader": "Abrir el lector completo",
        "previous": "\u2039 Anterior",
        "next": "Siguiente \u203a",
        "theme": "Tema",
        "tapTurn": "Tocar para pasar",
    },
    "de": {
        "continueReading": "Weiterlesen",
        "openFullReader": "Vollständigen Reader öffnen",
        "previous": "\u2039 Zurück",
        "next": "Weiter \u203a",
        "theme": "Design",
        "tapTurn": "Tippen zum Blättern",
    },
    "fr": {
        "continueReading": "Reprendre la lecture",
        "openFullReader": "Ouvrir le lecteur complet",
        "previous": "\u2039 Précédent",
        "next": "Suivant \u203a",
        "theme": "Thème",
        "tapTurn": "Toucher pour tourner",
    },
    "ru": {
        "continueReading": "Продолжить чтение",
        "openFullReader": "Открыть полный читатель",
        "previous": "\u2039 Назад",
        "next": "Далее \u203a",
        "theme": "Тема",
        "tapTurn": "Нажмите, чтобы листать",
    },
    "it": {
        "continueReading": "Continua a leggere",
        "openFullReader": "Apri il lettore completo",
        "previous": "\u2039 Precedente",
        "next": "Successivo \u203a",
        "theme": "Tema",
        "tapTurn": "Tocca per girare",
    },
    "pt-BR": {
        "continueReading": "Continuar lendo",
        "openFullReader": "Abrir o leitor completo",
        "previous": "\u2039 Anterior",
        "next": "Próximo \u203a",
        "theme": "Tema",
        "tapTurn": "Toque para virar",
    },
    "ar": {
        "continueReading": "متابعة القراءة",
        "openFullReader": "فتح القارئ الكامل",
        "previous": "\u2039 السابق",
        "next": "التالي \u203a",
        "theme": "السمة",
        "tapTurn": "انقر للتقليب",
    },
    "id": {
        "continueReading": "Lanjutkan membaca",
        "openFullReader": "Buka pembaca lengkap",
        "previous": "\u2039 Sebelumnya",
        "next": "Berikutnya \u203a",
        "theme": "Tema",
        "tapTurn": "Ketuk untuk membalik",
    },
    "hi": {
        "continueReading": "पढ़ना जारी रखें",
        "openFullReader": "पूर्ण रीडर खोलें",
        "previous": "\u2039 पिछला",
        "next": "अगला \u203a",
        "theme": "थीम",
        "tapTurn": "टैप करें",
    },
    "vi": {
        "continueReading": "Đọc tiếp",
        "openFullReader": "Mở trình đọc đầy đủ",
        "previous": "\u2039 Trước",
        "next": "Tiếp \u203a",
        "theme": "Chủ đề",
        "tapTurn": "Chạm để lật",
    },
    "th": {
        "continueReading": "อ่านต่อ",
        "openFullReader": "เปิดโปรแกรมอ่านแบบเต็ม",
        "previous": "\u2039 ก่อนหน้า",
        "next": "ถัดไป \u203a",
        "theme": "ธีม",
        "tapTurn": "แตะเพื่อพลิก",
    },
    "ms": {
        "continueReading": "Teruskan membaca",
        "openFullReader": "Buka pembaca penuh",
        "previous": "\u2039 Sebelum",
        "next": "Seterusnya \u203a",
        "theme": "Tema",
        "tapTurn": "Ketuk untuk membalik",
    },
}

# Server-only addition to the minimal reader: reading progress is read-write
# on the minimal surface.  The page fetches a CSRF token, loads the saved
# position (mirrored into the cookie so the index can resume it), then records
# the current chapter; heartbeats stay report-only.  The Kindle surface never
# displays insights and never mutates the shelf, and the script stays ES5:
# XMLHttpRequest only, no localStorage/Promise/fetch/classList.
_KINDLE_READER_SERVER_REPORT_JS = """\
(function () {
  var bookHash = %(book_hash)s;
  var chapterIndex = %(chapter_index)s;
  var clientId = 'kindle-' + Math.floor(Math.random() * 1e9).toString(36);
  var sequence = 0;
  var csrfToken = '';
  function kXhr(method, url, body, onDone) {
    try {
      var xhr = new XMLHttpRequest();
      xhr.open(method, url, true);
      if (body || method === 'PUT' || method === 'POST') {
        xhr.setRequestHeader('Content-Type', 'application/json');
        if (csrfToken) {
          xhr.setRequestHeader('X-CSRF-Token', csrfToken);
        }
      }
      xhr.onreadystatechange = function () {
        if (xhr.readyState === 4 && xhr.status === 200 && onDone) {
          onDone(xhr.responseText);
        }
      };
      xhr.send(body);
    } catch (e) {}
  }
  function kReadProgress() {
    kXhr('GET', '/api/reading-progress/' + encodeURIComponent(bookHash), null, function (text) {
      try {
        var progress = JSON.parse(text);
        if (progress && progress.chapter_index !== undefined &&
            progress.chapter_index !== null &&
            progress.chapter_index !== chapterIndex) {
          setCookie(bookHash, 'chapter_' + progress.chapter_index + '.html', 365);
        }
      } catch (e) {}
    });
  }
  function kSync() {
    // Reading progress is read-write: load the saved position, then record
    // the current chapter. Heartbeats below stay report-only.
    kReadProgress();
    kXhr(
      'PUT',
      '/api/reading-progress/' + encodeURIComponent(bookHash),
      '{"chapter_index":' + chapterIndex + '}'
    );
  }
  var lastBeat = new Date().getTime();
  function kHeartbeat() {
    // Report the wall-clock seconds since the last beat (capped like the
    // desktop tracker) so the 15s cadence maps to real reading time.
    var now = new Date().getTime();
    var elapsed = Math.max(1, Math.min(20, Math.round((now - lastBeat) / 1000)));
    lastBeat = now;
    sequence = sequence + 1;
    kXhr(
      'POST',
      '/api/reading-sessions/' + encodeURIComponent(bookHash) + '/heartbeat',
      '{"client_id":"' + clientId + '","client_sequence":' + sequence +
        ',"chapter_index":' + chapterIndex + ',"active_seconds":' + elapsed + '}'
    );
  }
  kXhr('GET', '/api/csrf', null, function (text) {
    try {
      csrfToken = JSON.parse(text).csrf_token || '';
    } catch (e) {}
    kSync();
    kHeartbeat();
  });
  setInterval(kHeartbeat, 15000);
})();
"""

# Server-only addition to the minimal index: resolve "Continue reading" from
# the authenticated reading-progress API (read-only) instead of relying only
# on the local cookie, so progress follows the user across devices. Stays ES5.
_KINDLE_READER_SERVER_RESUME_JS = """\
(function () {
  var bookHash = %(book_hash)s;
  try {
    var xhr = new XMLHttpRequest();
    xhr.open('GET', '/api/reading-progress/' + encodeURIComponent(bookHash), true);
    xhr.onreadystatechange = function () {
      if (xhr.readyState === 4 && xhr.status === 200) {
        try {
          var progress = JSON.parse(xhr.responseText);
          if (progress && !kindleRequestedChapter) kSetResume(progress.chapter_index);
        } catch (e) {}
      }
    };
    xhr.send(null);
  } catch (e) {}
})();
"""


def _kindle_i18n_messages(language, tools=None):
    """Resolve Kindle chrome strings independently of book metadata."""
    language = normalize_locale(language, "en")
    dictionary = _KINDLE_READER_I18N.get(language or "")
    if dictionary is None:
        dictionary = _KINDLE_READER_I18N.get((language or "").split("-")[0])
    if dictionary is None:
        dictionary = _KINDLE_READER_I18N["en"]
    bundle = get_bundle(normalize_locale(language, "en"))
    english = get_bundle("en")
    keys = {
        "library": "library.title",
        "contents": "reader.tableOfContents",
        "settings": "reader.settings",
        "done": "reader.closeSettings",
        "pageMode": "settings.paginationMode",
        "tapTurn": "reader.clickToTurn",
        "startReading": "book.startReading",
        "previousPage": "reader.previousPage",
        "nextPage": "reader.nextPage",
    }
    labels = dict(dictionary, **{name: bundle.get(key) or english[key] for name, key in keys.items()})
    if tools is not None:
        labels.update({key: kindle_message(language, key) for key in ("screensaver", "pomodoro")})
    return labels


def pdf_page_navigation(pages):
    """Build the page-derived chapter and TOC lists shared by PDF renderers.

    Both lists depend only on immutable page metadata, so a Server cache may
    retain them for the lifetime of one published PDF cache generation.
    """
    chapters = [
        {
            "title": f"Page {page.page_number}",
            "path": f"chapter_{page.page_number - 1}.html",
        }
        for page in pages
    ]
    toc = [
        {
            "title": f"Page {page.page_number}",
            "level": 0,
            "kind": "chapter",
            "chapter_index": page.page_number - 1,
            "chapter_file": f"chapter_{page.page_number - 1}.html",
            "page_label": str(page.page_number),
            "outline_labels": list(page.outline_labels),
        }
        for page in pages
    ]
    return chapters, toc


class ReaderPageRenderer:
    """Render shared EPUB and PDF pages from book data and deployment settings."""

    def __init__(
        self, *, book_id, metadata: BookMetadata, chapters, toc, description,
        asset_manifest: PublishedAssets, deployment_mode, urls=None, reporter=None,
        kindle_support=False, ai_reading_enabled=True, pdf_pages=(),
        pdf_encrypted=False, pdf_has_extractable_text=False,
    ):
        if deployment_mode not in {"ssg", "server"}:
            raise ValueError(f"Unsupported deployment mode: {deployment_mode}")
        self.book_hash = str(book_id)
        self.book_title = metadata.title
        self.authors = list(metadata.authors)
        self.tags = list(metadata.tags)
        self.cover_info = {"web_path": metadata.cover} if metadata.cover else None
        self.resources_base = "resources"
        self.lang = metadata.language
        self.epub_identifier = metadata.epub_identifier
        self.source_format = metadata.source_format
        self.chapters = chapters
        self.toc = toc
        self.description = description
        self.asset_manifest = asset_manifest
        self.deployment_mode = deployment_mode
        self.urls = urls or SiteURLs()
        self.reporter = reporter or Reporter(False)
        self.kindle_support = bool(kindle_support)
        self.ai_reading_enabled = ai_reading_enabled
        self._pdf_pages = pdf_pages
        self._pdf_encrypted = pdf_encrypted
        self._pdf_has_extractable_text = pdf_has_extractable_text

    @staticmethod
    def from_pdf_metadata(
        *,
        book_id: str,
        metadata: "PDFMetadata",
        cover_path: Optional[str],
        asset_manifest: PublishedAssets,
        urls: SiteURLs,
        deployment_mode: str,
        navigation=None,
    ) -> "ReaderPageRenderer":
        """Adapt PDF page metadata to the shared reader."""
        if navigation is None:
            chapters, toc = pdf_page_navigation(metadata.pages)
        else:
            chapters, toc = navigation
        return ReaderPageRenderer(
            book_id=book_id,
            metadata=BookMetadata(
                title=metadata.title or "PDF Book", authors=metadata.authors,
                tags=metadata.tags, cover=cover_path, language=metadata.language or "en",
                epub_identifier=None, source_format=PDF_FORMAT,
            ),
            chapters=chapters, toc=toc, description=None,
            asset_manifest=asset_manifest, urls=urls, deployment_mode=deployment_mode,
            pdf_pages=tuple(metadata.pages), pdf_encrypted=bool(metadata.encrypted),
            pdf_has_extractable_text=bool(metadata.has_extractable_text),
        )

    @staticmethod
    def from_server_content_cache(
        *,
        book_id,
        metadata,
        asset_manifest,
        urls=None,
        reporter=None,
        kindle_support=False,
        ai_reading_enabled=True,
    ):
        """Adapt validated cache metadata to the shared reader."""
        if not isinstance(metadata, dict):
            raise ValueError("Server content metadata must be an object")
        title = metadata.get("title")
        chapters = metadata.get("chapters")
        toc = metadata.get("toc")
        if not isinstance(title, str) or not isinstance(chapters, list) or not isinstance(toc, list):
            raise ValueError("Server content metadata is invalid")

        cover_info = metadata.get("cover_info") or {}
        cover = cover_info.get("web_path")
        if not cover and cover_info.get("full_path"):
            cover = os.path.normpath(os.path.join(
                metadata.get("resources_base") or "resources", cover_info["full_path"],
            ))
        return ReaderPageRenderer(
            book_id=book_id,
            metadata=BookMetadata(
                title=title, authors=tuple(metadata.get("authors") or ()),
                tags=tuple(metadata.get("tags") or ()), cover=cover,
                language=metadata.get("language") or "en",
                epub_identifier=metadata.get("epub_identifier"), source_format=EPUB_FORMAT,
            ),
            chapters=chapters, toc=toc, description=metadata.get("description"),
            asset_manifest=asset_manifest, urls=urls, deployment_mode="server",
            reporter=reporter, kindle_support=kindle_support,
            ai_reading_enabled=ai_reading_enabled,
        )

    def _server_ai_feature_assets(self):
        """Expose immutable optional AI assets without putting them on the critical path."""
        if self.deployment_mode != "server":
            return ""
        logical_assets = {
            "aiCanvasCss": "ai-canvas.css",
            "aiCanvas": "ai-canvas.js",
            "aiReadingHubCss": "ai-reading-hub.css",
            "aiReadingHub": "ai-reading-hub.js",
            "aiChatCss": "ai-chat.css",
            "aiChat": "ai-chat.js",
            "aiRichTextCss": "ai-rich-text.css",
            "aiRichText": "ai-rich-text.js",
            "markdownIt": "vendor/markdown-it/markdown-it.min.js",
            "katexCss": "vendor/katex/katex.min.css",
            "katex": "vendor/katex/katex.min.js",
            "mermaid": "vendor/mermaid/mermaid.min.js",
        }
        urls = {
            name: self.asset_manifest.url_for(logical_name)
            for name, logical_name in logical_assets.items()
        }
        return (
            '<script>window.EpubBrowserFeatureAssets='
            + json.dumps(urls, separators=(",", ":"))
            + ';</script>'
        )

    def render_index(self, initial_book_review=None):
        """创建章节索引页面"""
        is_pdf_book = getattr(self, 'source_format', EPUB_FORMAT) == PDF_FORMAT
        book_language = html.escape(self.lang or 'en', quote=True)
        bookshelf_data_actions = """
                <button class="bookshelf-action-btn" id="exportShelfBtn">
                    <i class="fas fa-upload" aria-hidden="true"></i> <span data-i18n="bookshelf.export">Export</span>
                </button>
                <button class="bookshelf-action-btn" id="importShelfBtn">
                    <i class="fas fa-download" aria-hidden="true"></i> <span data-i18n="bookshelf.import">Import</span>
                </button>
                <input type="file" id="importShelfFile" accept=".json" style="display: none;">""" if self.deployment_mode == "ssg" else ""
        safe_book_title = metadata_text(self.book_title)
        book_title_text = html.escape(safe_book_title, quote=False)
        book_title_attribute = html.escape(safe_book_title, quote=True)
        # The minimal reader is opt-in (--kindle); PDF books never have a
        # kindle.html page, so neither case embeds an entry script.
        kindle_entry_script = (
            ""
            if (is_pdf_book or not self.kindle_support)
            else self._kindle_entry_script("kindle.html")
        )
        book_id_attribute = html.escape(str(self.book_hash), quote=True)
        book_id_url = urllib.parse.quote(str(self.book_hash), safe='')
        if self.authors:
            authors_text = " & ".join(
                html.escape(metadata_text(author), quote=False)
                for author in self.authors
            )
            authors_html = f'<p class="book-info-author" lang="{book_language}" dir="auto">{authors_text}</p>'
        else:
            authors_html = '<p class="book-info-author" data-i18n="book.unknownAuthor">Unknown author</p>'
        ai_feature_assets = "" if (is_pdf_book or not self.ai_reading_enabled) else self._server_ai_feature_assets()
        book_feature_assets = json.dumps({
            "bookshelf": self.asset_manifest.url_for("bookshelf.js"),
            "annotationHubCss": self.asset_manifest.url_for("annotation-hub.css"),
            "annotation": self.asset_manifest.url_for("annotation.js"),
            "annotationHub": self.asset_manifest.url_for("annotation-hub.js"),
            "sortable": self.asset_manifest.url_for("vendor/sortablejs/sortable.min.js"),
        }, separators=(",", ":"))
        if self.deployment_mode == "server":
            book_feature_assets = json.dumps({
                **json.loads(book_feature_assets),
                "readingInsightsCss": self.asset_manifest.url_for("reading-insights.css"),
                "readingInsights": self.asset_manifest.url_for("reading-insights.js"),
            }, separators=(",", ":"))
        ai_reading_navigation = (
            f'<button type="button" class="app-nav-link" data-ai-reading-hub '
            f'data-book-id="{book_id_attribute}" aria-haspopup="dialog">'
            '<i class="fas fa-wand-magic-sparkles" aria-hidden="true"></i>'
            '<span data-i18n="ai.library">AI readings</span></button>'
            if self.deployment_mode == "server" and not is_pdf_book and self.ai_reading_enabled else ""
        )
        reading_insights_navigation = (
            f'<button type="button" class="app-nav-link" data-reading-insights data-reading-insights-show-overview data-book-id="{book_id_attribute}" '
            'aria-haspopup="dialog"><i class="fas fa-chart-column" '
            'aria-hidden="true"></i><span data-i18n="readingInsights.navigation">Reading insights</span></button>'
            if self.deployment_mode == "server" else ""
        )
        ai_reading_indicators = (
            f' data-ai-reading-indicators data-book-id="{book_id_attribute}"'
            if self.deployment_mode == "server" and not is_pdf_book and self.ai_reading_enabled else ""
        )
        ai_reading_script = (
            '<script src="/assets/ai-feature-loader.js" defer></script>'
            if self.deployment_mode == "server" and not is_pdf_book and self.ai_reading_enabled else ""
        )
        ai_book_chat_button = (
            f'<button type="button" class="css-btn secondary" data-ai-book-chat '
            f'data-book-id="{book_id_attribute}"><i class="fas fa-comments" aria-hidden="true"></i>'
            '<span data-i18n="ai.askBook">Ask AI</span></button>'
            if self.deployment_mode == "server" and not is_pdf_book and self.ai_reading_enabled else ""
        )
        ai_book_chat_script = ""
        book_review_assets = (
            '<link rel="stylesheet" href="' + self.asset_manifest.url_for("book-reviews.css") + '">'
            '<script src="' + self.asset_manifest.url_for("book-reviews.js") + '" defer></script>'
            if self.deployment_mode == "server" else ""
        )
        book_review_panel = (
            f'<div class="book-review-modal" data-book-review-modal hidden>'
            f'<section class="book-review-dialog" id="book-review-dialog" role="dialog" '
            f'aria-modal="true" aria-label="Write review" data-i18n-aria-label="bookReviews.write" tabindex="-1">'
            f'<section data-book-reviews data-book-id="{book_id_attribute}"></section>'
            f'</section></div>'
            if self.deployment_mode == "server" else ""
        )
        # Book reviews are account-private runtime data.  In Server mode the
        # authenticated request may provide the current user's review so the
        # first paint already reserves its final position.  Never use this in
        # SSG output or persist it in the EPUB-derived content cache.
        initial_review = None
        if self.deployment_mode == "server" and isinstance(initial_book_review, dict):
            initial_rating = initial_book_review.get("rating")
            initial_text = initial_book_review.get("review_text")
            if (
                isinstance(initial_rating, int)
                and not isinstance(initial_rating, bool)
                and 1 <= initial_rating <= 5
                and isinstance(initial_text, str)
            ):
                initial_review = {
                    "rating": initial_rating,
                    "review_text": initial_text,
                }
        if self.deployment_mode != "server":
            book_review_display = ""
            book_review_initial_data = ""
        elif initial_review is None:
            book_review_display = (
                f'<section class="book-review-display" data-book-review-display '
                f'data-book-id="{book_id_attribute}" hidden></section>'
            )
            book_review_initial_data = ""
        else:
            review_rating = initial_review["rating"]
            review_text = initial_review["review_text"]
            review_copy = html.escape(review_text, quote=False)
            review_stars = "★★★★★"[:review_rating]
            review_body = (
                f'<p class="book-review-display-copy is-collapsed">{review_copy}</p>'
                f'<button type="button" class="book-review-expand" data-book-review-expand '
                f'aria-expanded="false"{"" if len(review_text) > 100 else " hidden"} '
                f'data-i18n="bookReviews.showMore">Show more</button>'
                if review_text else ""
            )
            book_review_display = f'''<section class="book-review-display" data-book-review-display data-book-id="{book_id_attribute}">
        <div class="book-review-display-header">
            <h2 data-i18n="bookReviews.title">My review</h2>
            <span class="book-review-display-rating" aria-label="{review_rating}/5">
                <span aria-hidden="true">{review_stars}</span><span class="book-review-display-score">{review_rating}/5</span>
            </span>
        </div>
        {review_body}
    </section>'''
            initial_review_json = json.dumps(initial_review, ensure_ascii=False).replace("<", "\\u003c").replace(
                ">", "\\u003e"
            ).replace("&", "\\u0026")
            book_review_initial_data = (
                '<script type="application/json" data-book-review-initial>'
                + initial_review_json
                + '</script>'
            )
        book_review_trigger = (
            '<button type="button" class="css-btn secondary" data-book-review-toggle '
            'aria-controls="book-review-dialog" aria-expanded="false">'
            '<i class="fas fa-pen" aria-hidden="true"></i>'
            '<span data-i18n="bookReviews.write">Write review</span></button>'
            if self.deployment_mode == "server" else ""
        )
        book_reading_time = (
            '<p class="book-reading-time" data-book-reading-time hidden>'
            '<i class="fas fa-chart-column" aria-hidden="true"></i>'
            '<span data-book-reading-time-label></span></p>'
            if self.deployment_mode == "server" else ""
        )
        book_source_format = (
            '<span class="book-source-format" aria-label="PDF" data-i18n-aria-label="pdf.formatBadge" '
            'data-i18n="pdf.formatBadge">PDF</span>'
            if is_pdf_book else ""
        )
        server_account_stylesheet = SERVER_ACCOUNT_STYLESHEET if self.deployment_mode == "server" else ""
        book_search_stylesheet = ""
        book_search_trigger = ""
        book_search_modal = ""
        book_search_script = ""
        if self.deployment_mode == "server" and not is_pdf_book:
            book_search_stylesheet = '<link rel="stylesheet" href="/assets/book-search.css">'
            book_search_trigger = (
                '<button type="button" class="css-btn secondary" id="bookSearchToggle" '
                'aria-haspopup="dialog" aria-controls="book-search-dialog" aria-expanded="false">'
                '<i class="fas fa-magnifying-glass" aria-hidden="true"></i>'
                '<span data-i18n="book.search">Search this book</span></button>'
            )
            book_search_modal = f'''<div class="book-search-modal" id="bookSearchModal" hidden>
    <section class="book-search-dialog" id="book-search-dialog" role="dialog" aria-modal="true" aria-label="Search this book" data-i18n-aria-label="book.search" tabindex="-1" data-book-search data-book-hash="{book_id_attribute}">
        <div class="book-search-dialog-header">
            <h2 data-i18n="book.search">Search this book</h2>
            <button class="book-search-close" id="bookSearchClose" type="button" aria-label="Close search" data-i18n-aria-label="book.closeSearch"><i class="fas fa-times" aria-hidden="true"></i></button>
        </div>
{_BOOK_SEARCH_BODY}
    </section>
</div>'''
            book_search_script = '<script src="/assets/book-search.js" defer></script>'
        # Locale selection is shared navigation chrome in both SSG and Server.
        server_locale_control = SERVER_LOCALE_CONTROL
        server_account_control = SERVER_ACCOUNT_CONTROL if self.deployment_mode == "server" else ""
        server_account_panel = render_account_panel(self.kindle_support) if self.deployment_mode == "server" else ""
        server_locale_script = SERVER_LOCALE_SCRIPT
        index_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="theme-color" content="#244548">
    <meta name="description" content="{book_title_attribute} - EPUB Browser">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="default">
    <meta name="apple-mobile-web-app-title" content="EPUB Browser">
    <title>{book_title_text}</title>
    {render_i18n_runtime_and_inline(deployment_mode=self.deployment_mode)}
    <script>window.EpubBrowserI18n.init();</script>
    {ai_feature_assets}
    <noscript><link rel="manifest" href="/assets/manifest.en.json"></noscript>
    <link rel="stylesheet" href="/assets/vendor/fontawesome/css/all.min.css">
    <link rel="stylesheet" href="/assets/theme.css">
    <link rel="stylesheet" href="/assets/notification.css">
    <link rel="stylesheet" href="/assets/dialog.css">
    <link rel="stylesheet" href="/assets/book.css?v=13">
    {book_search_stylesheet}
    <link rel="stylesheet" href="/assets/breadcrumb.css?v=3">
    <link rel="stylesheet" href="/assets/loading.css?v=15">
    <link rel="icon" type="image/png" href="/assets/favicon.png">
    <link rel="apple-touch-icon" href="/assets/icon-192.png">
    <link rel="stylesheet" href="/assets/bookshelf.css">
    {server_account_stylesheet}
    {book_review_assets}
"""
        index_html += """
    <script src="/assets/theme-bootstrap.js"></script>
{kindle_entry_script}
</head>
<body>
"""
        index_html += f"""
<header class="app-header">
    <nav class="app-nav" aria-label="Book navigation" data-i18n-aria-label="book.navigation">
        <a class="app-nav-brand" href="/" aria-label="EPUB Browser" data-i18n-aria-label="common.brand"><img class="app-nav-brand-mark" src="/assets/logo-mark-color.png" width="32" height="32" alt=""><span data-i18n="common.brand">EPUB Browser</span></a>
        <div class="app-nav-links">
            <button type="button" class="app-nav-link" id="bookshelfBtn" aria-haspopup="dialog" aria-controls="bookshelfModal"><i class="fas fa-bookmark" aria-hidden="true"></i><span data-i18n="book.shelf">Shelf</span></button>
            <button type="button" class="app-nav-link" id="bookAnnotationsBtn" data-annotation-hub data-book-hash="{book_id_attribute}" aria-haspopup="dialog"><i class="fas fa-highlighter" aria-hidden="true"></i><span data-i18n="book.annotations">Annotations</span></button>
            {render_vocabulary_navigation(self.book_hash) if self.deployment_mode == "server" else ""}
            {reading_insights_navigation}
            {ai_reading_navigation}
        </div>
        <div class="app-nav-actions">
            {server_locale_control}
            <button class="theme-toggle app-nav-action app-nav-theme" id="themeToggle" type="button" aria-label="Theme" data-i18n-aria-label="book.theme"><i class="fas fa-moon" aria-hidden="true"></i><span class="app-nav-action-label" data-i18n="book.theme">Theme</span></button>
            {server_account_control}
        </div>
    </nav>
</header>
<div class="container">
    <div class="book-info-card" data-id="book-info-card">
            <div class="book-info-cover-wrap">
                <div class="book-info-cover">
                    <img src="{html.escape(self.get_metadata().cover or '', quote=True)}" alt="">
                </div>
                {book_reading_time}
                {book_source_format}
            </div>
            <div class="book-info-content">
                <h2 class="book-info-title" lang="{book_language}" dir="auto">{book_title_text}</h2>
                {authors_html}"""
        if self.description:
            description = sanitize_html_fragment(self.description)
            index_html += f"""
                <div class="book-info-desc" lang="{book_language}" dir="auto">
                    {description}
                </div>"""
        index_html += f"""
                <div class="book-info-tags" lang="{book_language}" dir="auto">"""
        if self.tags:
            for tag in self.tags:
                tag_text = html.escape(metadata_text(tag), quote=False)
                index_html += """<span class="book-tag">{}</span>""".format(tag_text)
        index_html += f"""
                </div>
                <div class="css-controls clearReadingProgress">
                    <div class="continue-reading-control" id="continueReadingControl">
                        <a class="css-btn primary" id="continueReadingBtn" href="#" aria-label="Start reading" data-i18n-aria-label="book.startReading"><i class="fas fa-book-open"></i><span id="continueReadingBtnText" data-i18n="book.startReading">Start reading</span></a>
                        <button type="button" class="continue-reading-menu-toggle" id="continueReadingMenuToggle" aria-label="More reading actions" data-i18n-aria-label="book.moreReadingActions" aria-expanded="false" aria-controls="clearReadingProgressMenu" hidden><i class="fas fa-chevron-down" aria-hidden="true"></i></button>
                        <div class="continue-reading-menu" id="clearReadingProgressMenu" hidden>
                            <button type="button" class="continue-reading-menu-item" id="clearReadingProgressBtn" aria-label="Clear reading progress" data-i18n-aria-label="book.clearReadingProgress" hidden><i class="fas fa-eraser" aria-hidden="true"></i><span data-i18n="book.clear">Clear</span></button>
                        </div>
                    </div>
                    {ai_book_chat_button}
                    <button class="css-btn secondary" id="toggleShelfBtn"><i class="fas fa-bookmark"></i><span id="toggleShelfBtnText" data-i18n="book.addToShelf">Add to Shelf</span></button>
                    {book_search_trigger}
                    {book_review_trigger}
                </div>
            </div>
    </div>
    {book_review_display}
    {book_review_initial_data}
    {book_review_panel}
    {book_search_modal}
    <div class="toc-container" data-id="toc-container"{ai_reading_indicators}>
        <div class="toc-header">
            <h2 data-i18n="book.tableOfContents">Table of contents</h2>
            <div class="chapter-count" data-i18n="book.totalChapters" data-i18n-params='{{"count": {len(self.chapters)}}}'>Total: {len(self.chapters)}</div>
        </div>
        <ul class="chapter-list">
"""

        # OPF spine owns public chapter indexes.  EPUB navigation only
        # contributes titles, anchors and non-navigable grouping nodes.
        for toc_item in self._build_toc_data():
            level_class = f"toc-level-{min(toc_item.get('level', 0), 3)}"
            toc_title = html.escape(
                metadata_text(toc_item.get("title")), quote=False
            )
            toc_title_attributes = f' lang="{book_language}" dir="auto"'
            if getattr(self, 'source_format', EPUB_FORMAT) == PDF_FORMAT and toc_item.get('page_label'):
                page_params = html.escape(
                    json.dumps(
                        {'number': toc_item['page_label']},
                        separators=(',', ':'),
                    ),
                    quote=True,
                )
                toc_title_attributes += (
                    f' data-i18n="pdf.page" data-i18n-params="{page_params}"'
                )
            outline_labels_html = ""
            if getattr(self, 'source_format', EPUB_FORMAT) == PDF_FORMAT and toc_item.get('outline_labels'):
                outline_labels = " · ".join(
                    html.escape(metadata_text(label), quote=False)
                    for label in toc_item['outline_labels']
                )
                outline_labels_html = (
                    f'<span class="chapter-outline-labels" lang="{book_language}" '
                    f'dir="auto">{outline_labels}</span>'
                )
            if toc_item.get('kind') == 'section':
                index_html += f'        <li class="{level_class} toc-section"><span class="chapter-section-title" lang="{book_language}" dir="auto">{toc_title}</span></li>\n'
                continue

            chapter_index = toc_item['chapter_index']
            chapter_anchor = toc_item.get('anchor')
            chapter_title_group = (
                f'<span class="chapter-title-with-sync"><span class="chapter-title"'
                f'{toc_title_attributes}>{toc_title}</span>{outline_labels_html}</span>'
            )
            if chapter_anchor is not None:
                safe_anchor = urllib.parse.quote(str(chapter_anchor), safe='')
                index_html += f'        <li class="{level_class}"><a class="chapter-link" href="/book/{book_id_url}/chapter_{chapter_index}.html#{safe_anchor}" id="eb_ci_{chapter_index}#{safe_anchor}" data-chapter-index="{chapter_index}">{chapter_title_group}<span class="chapter-page">chapter_{chapter_index}.html</span></a></li>\n'
            else:
                index_html += f'        <li class="{level_class}"><a class="chapter-link" href="/book/{book_id_url}/chapter_{chapter_index}.html" id="eb_ci_{chapter_index}" data-chapter-index="{chapter_index}">{chapter_title_group}<span class="chapter-page">chapter_{chapter_index}.html</span></a></li>\n'

        index_html += f"""    </ul>
    </div>
</div>
<div class="reading-controls" data-id="reading-controls">
    <button class="control-btn" id="scrollToTopBtn" type="button" aria-label="Top" data-i18n-aria-label="book.top">
        <i class="fas fa-arrow-up"></i>
        <span class="control-name" data-i18n="book.top">Top</span>
    </button>
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
{render_footer(datetime.now().year, release_api_url='/api/version' if self.deployment_mode == 'server' else '')}"""

        cache_boundary_script = (
            '<script src="/assets/cache-boundary.js" defer></script>'
            if self.deployment_mode == "server"
            else ""
        )
        auth_script = (
            SERVER_AUTH_SCRIPT
            if self.deployment_mode == "server"
            else ""
        )
        startup = (
            """function startBookClients() {
    if (!window.EpubBrowserAuth) return;
        window.EpubBrowserAuth.init().then(function(session) {
            if (!session) return;
            if (window.initScriptBook) window.initScriptBook();
            var reviewRoot = document.querySelector('[data-book-reviews]');
            if (reviewRoot && window.EpubBookReviews) {
                window.EpubBookReviews.mount(
                    reviewRoot,
                    reviewRoot.getAttribute('data-book-id'),
                    document.querySelector('[data-book-review-display]')
                );
            }
        });
}
if (window.EpubBrowserCacheBoundary) {
    window.EpubBrowserCacheBoundary.start(startBookClients);
}"""
            if self.deployment_mode == "server"
            else "if (window.initScriptBook) window.initScriptBook();"
        )
        index_html += f"""
{cache_boundary_script}
<script src="/assets/notification.js" defer></script>
{auth_script}
{server_locale_script}
<script src="/assets/theme.js" defer></script>
<script src="/assets/dialog.js" defer></script>
<script src="/assets/version-check.js" defer></script>
<script src="/assets/reading-progress.js" defer></script>
<script src="/assets/reader-layout.js" defer></script>
<script>window.EpubBrowserBookFeatureAssets={book_feature_assets};</script>
<script src="/assets/book-feature-loader.js" defer></script>
<script src="/assets/book.js?v=13" defer></script>
{book_search_script}
{ai_reading_script}
{render_vocabulary_assets(self.asset_manifest) if self.deployment_mode == "server" else ""}
{ai_book_chat_script}
<script>
document.addEventListener('DOMContentLoaded', function() {{
    {startup}
}});
</script>
</body>
</html>"""
        index_html = rewrite_asset_urls(index_html, self.asset_manifest)
        index_html = self._inject_deployment_mode(index_html)
        index_html = rewrite_root_urls(index_html, self.urls)
        # 不再压缩 HTML：模板本身紧凑，实测 minify_html 对这类输出无收益
        # （CSS/JS 因 kindle 兼容不能压），且章节页曾因压缩丢失标签而禁用
        index_html = index_html.replace("{kindle_entry_script}", kindle_entry_script)
        return index_html

    def _build_chapter_index_maps(self):
        """构建章节路径到索引的映射（支持多种路径格式）

        Returns:
            tuple: (chapter_index_map, chapter_filename_map)
        """
        chapter_index_map = {}
        chapter_filename_map = {}
        for i, chapter in enumerate(self.chapters):
            # 原始路径
            chapter_index_map[chapter['path']] = i
            # 规范化路径（去除 ./ 前缀）
            normalized_path = chapter['path'].lstrip('./').lstrip('/')
            chapter_index_map[normalized_path] = i
            # 文件名匹配
            chapter_filename = posixpath.basename(chapter['path'])
            chapter_filename_map[chapter_filename] = i
        return chapter_index_map, chapter_filename_map

    def _find_chapter_index(self, toc_src, chapter_index_map, chapter_filename_map):
        """根据toc_src查找章节索引

        Args:
            toc_src: 目录项的src路径
            chapter_index_map: 章节路径到索引的映射
            chapter_filename_map: 章节文件名到索引的映射

        Returns:
            int or None: 章节索引，未找到则返回None
        """
        # 1. 直接匹配
        if toc_src in chapter_index_map:
            return chapter_index_map[toc_src]
        # 2. 规范化路径匹配（去除 ./ 前缀）
        elif toc_src.lstrip('./').lstrip('/') in chapter_index_map:
            return chapter_index_map[toc_src.lstrip('./').lstrip('/')]
        # 3. URL解码后匹配（处理%20等编码字符）
        elif urllib.parse.unquote(toc_src) in chapter_index_map:
            return chapter_index_map[urllib.parse.unquote(toc_src)]
        elif urllib.parse.unquote(toc_src).lstrip('./').lstrip('/') in chapter_index_map:
            return chapter_index_map[urllib.parse.unquote(toc_src).lstrip('./').lstrip('/')]
        # 4. 文件名匹配
        elif posixpath.basename(toc_src) in chapter_filename_map:
            return chapter_filename_map[posixpath.basename(toc_src)]
        # 5. URL解码后的文件名匹配
        elif posixpath.basename(urllib.parse.unquote(toc_src)) in chapter_filename_map:
            return chapter_filename_map[posixpath.basename(urllib.parse.unquote(toc_src))]
        return None

    def _build_toc_data(self):
        """Return the EPUB-derived table of contents for either publisher."""
        if getattr(self, 'source_format', EPUB_FORMAT) == PDF_FORMAT:
            return [dict(item) for item in self.toc]

        toc_data = []

        def title_key(value):
            return " ".join(metadata_text(value).split()).casefold()

        def chapter_record(title, level, chapter_index, anchor=None):
            record = {
                'title': title,
                'level': level,
                'kind': 'chapter',
                'chapter_index': chapter_index,
                'chapter_file': f'chapter_{chapter_index}.html',
            }
            if anchor is not None:
                record['anchor'] = anchor
            return record

        # 如果有详细的toc信息，使用toc生成目录
        if self.toc:
            chapter_index_map, chapter_filename_map = self._build_chapter_index_maps()
            section_indexes_by_title = {}
            for index, chapter in enumerate(self.chapters):
                if chapter.get('is_section_index'):
                    section_indexes_by_title.setdefault(
                        title_key(chapter['title']), []
                    ).append(index)

            used_section_indexes = set()
            represented_indexes = set()

            # 根据toc生成目录
            for order, toc_item in enumerate(self.toc):
                if toc_item.get('kind') == 'section' and not toc_item.get('src'):
                    toc_data.append({
                        'title': toc_item['title'],
                        'level': toc_item.get('level', 0),
                        'kind': 'section',
                    })
                    continue
                toc_src = toc_item['src']
                target_index = self._find_chapter_index(
                    toc_src, chapter_index_map, chapter_filename_map
                )
                if toc_item.get('kind', 'chapter') == 'section':
                    # A repeated NCX target is normally only a grouping node.
                    # However, if OPF has a separate linear section-index page
                    # with the same label, that page is a real chapter and
                    # must own its own chapter_N slot.
                    candidates = section_indexes_by_title.get(
                        title_key(toc_item['title']), []
                    )
                    section_index = next(
                        (
                            candidate for candidate in candidates
                            if candidate not in used_section_indexes
                            and (target_index is None or candidate < target_index)
                        ),
                        None,
                    )
                    if section_index is not None:
                        used_section_indexes.add(section_index)
                        represented_indexes.add(section_index)
                        toc_data.append(chapter_record(
                            toc_item['title'],
                            toc_item.get('level', 0),
                            section_index,
                        ))
                    else:
                        # Keep genuinely structural groups, but never let one
                        # claim an OPF chapter index belonging to its child.
                        toc_data.append({
                            'title': toc_item['title'],
                            'level': toc_item.get('level', 0),
                            'kind': 'section',
                        })
                    continue
                chapter_anchor = toc_item.get('anchor', None)
                if target_index is not None:
                    represented_indexes.add(target_index)
                    toc_data.append(chapter_record(
                        toc_item['title'], toc_item.get('level', 0),
                        target_index, chapter_anchor,
                    ))
                else:
                    self.reporter.detail(
                        f"Chapter index not found for toc item: "
                        f"{toc_item['title']} (src: {toc_src})"
                    )

        else:
            # 回退到简单章节列表
            for i, chapter in enumerate(self.chapters):
                toc_data.append(chapter_record(chapter['title'], 0, i))

        return toc_data

    def _kindle_entry_script(self, target_url):
        """Legacy Kindle WebKit entry script (SSG and Server, opt-in).

        Real e-Ink Kindles (UA contains ``kindle`` but not Silk) are sent to
        the dependency-free minimal page; Kindle Fire (Silk) and ``?full=1``
        keep the full reader, which must never be a redirect loop.  Server
        renders the minimal pages at request time from the same templates.
        PDF books have no minimal pages and must not use this.  The minimal
        pages themselves are opt-in via ``kindle_support``.
        """
        if not self.kindle_support:
            return ""
        return f"""
<script>
(function () {{
  var ua = navigator.userAgent.toLowerCase();
  if (ua.indexOf('kindle') === -1) return;
  if (ua.indexOf('silk') !== -1) return;
  if (location.search.indexOf('full=1') !== -1) return;
  location.replace('{target_url}');
}})();
</script>"""

    def create_kindle_index_page(self, toc_data=None, *, locale=None, tools=None):
        """Kindle 极简目录页模板。"""
        book_language = html.escape(self.lang or 'en', quote=True)
        kindle_labels = _kindle_i18n_messages(locale)
        safe_book_title = metadata_text(self.book_title)
        book_title_text = html.escape(safe_book_title, quote=False)
        book_hash_js = json.dumps(str(self.book_hash))
        authors_html = ""
        if self.authors:
            authors_text = " & ".join(
                html.escape(metadata_text(author), quote=False)
                for author in self.authors
            )
            authors_html = f'<p>{authors_text}</p>'
        if toc_data is None:
            toc_data = self._build_toc_data()
        toc_items = []
        for item in toc_data:
            if item.get('kind') == 'chapter':
                level = int(item.get('level') or 0)
                if level > 3:
                    level = 3
                chapter_file = f"kindle_chapter_{item.get('chapter_index')}.html"
                title = html.escape(
                    metadata_text(item.get('title', '')), quote=False
                )
                toc_items.append(
                    f'<li class="lvl-{level}"><a href="{chapter_file}" '
                    f'data-k-toc-chapter="{int(item["chapter_index"])}">{title}</a></li>'
                )
            else:
                title = html.escape(
                    metadata_text(item.get('title', '')), quote=False
                )
                toc_items.append(f'<li class="sec">{title}</li>')
        toc_html = "\n".join(toc_items)
        resume_script = f"""
function kSetResume(chapter) {{
  if (typeof chapter !== 'number' || chapter < 0 || chapter >= {len(self.chapters)}
      || chapter !== Math.floor(chapter)) return;
  var resume = document.getElementById('kResume');
  if (!resume) return;
  resume.href = 'kindle_chapter_' + chapter + '.html#resume';
  document.getElementById('kStartLabel').style.display = 'none';
  document.getElementById('kResumeLabel').style.display = 'inline';
  var entries = document.querySelectorAll('[data-k-toc-chapter]');
  var current;
  for (var i = 0; i < entries.length; i++) {{
    var index = Number(entries[i].getAttribute('data-k-toc-chapter'));
    if (index === chapter && !current) {{
      current = entries[i];
      current.setAttribute('aria-current', 'location');
    }} else entries[i].removeAttribute('aria-current');
  }}
}}
var kindleRequestedChapter = location.hash.match(/^#chapter-([0-9]+)$/);
if (kindleRequestedChapter) {{
  kSetResume(Number(kindleRequestedChapter[1]));
  var kindleCurrent = document.querySelector('.k-toc [aria-current]');
  if (kindleCurrent && kindleCurrent.getBoundingClientRect().bottom > window.innerHeight - 58) {{
    kindleCurrent.scrollIntoView();
  }}
}}
"""
        if self.deployment_mode != "server":
            resume_script += f"""
var kindleSavedChapter = (getCookie({book_hash_js}) || '').match(/^chapter_([0-9]+)[.]html$/);
if (!kindleRequestedChapter && kindleSavedChapter) kSetResume(Number(kindleSavedChapter[1]));
"""
        kindle_server_resume_script = ""
        if self.deployment_mode == "server":
            kindle_server_resume_script = _KINDLE_READER_SERVER_RESUME_JS % {
                "book_hash": json.dumps(str(self.book_hash)),
            }
        cover = self.get_metadata().cover
        cover_html = kindle_cover(cover)
        action = (
            '<a id="kResume" class="k-control k-book-action" href="kindle_chapter_0.html" accesskey="c">'
            f'<span id="kStartLabel" data-i18n="startReading">{html.escape(kindle_labels["startReading"])}</span>'
            f'<span id="kResumeLabel" style="display:none" data-i18n="continueReading">'
            f'{html.escape(kindle_labels["continueReading"])}</span></a>'
            if self.chapters else ""
        )
        return f"""<!DOCTYPE html>
<html lang="{locale or 'en'}">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{book_title_text}</title>
<style>
{_KINDLE_READER_CSS}
{_KINDLE_BOOK_CSS}
</style>
</head>
<body class="light">
<main class="k-book">
<div class="k-book-hero k-surface" lang="{book_language}">
    {cover_html}
    <h1>{book_title_text}</h1>
    {authors_html}
    <div lang="{locale or 'en'}" data-k-ui-language>{action}</div>
</div>
<section class="k-surface">
    <h2 data-i18n="contents">{html.escape(kindle_labels["contents"])}</h2>
    <div class="k-toc" lang="{book_language}"><ul>{toc_html}</ul></div>
</section>
</main>
{render_kindle_dock(self.urls, locale or "en", tools=tools)}
<script>
{_KINDLE_READER_JS}
{kindle_locale_script(lambda code: _kindle_i18n_messages(code, tools), use_initial_locale=locale is not None)}
{resume_script}
{kindle_server_resume_script}</script>
</body>
</html>
"""

    def create_kindle_chapter_page(
        self, body_content, style_links, chapter_index, chapter_title, *, locale=None
    ):
        """Kindle 极简章节阅读页模板。"""
        book_language = html.escape(self.lang or 'en', quote=True)
        kindle_labels = _kindle_i18n_messages(locale)
        safe_book_title = metadata_text(self.book_title)
        safe_chapter_title = metadata_text(chapter_title)
        book_title_text = html.escape(safe_book_title, quote=False)
        chapter_title_text = html.escape(safe_chapter_title, quote=False)
        book_hash_js = json.dumps(str(self.book_hash))
        prev_link = ""
        next_link = ""
        if chapter_index > 0:
            prev_link = (
                f'<a id="kPrev" class="prev" href="kindle_chapter_{chapter_index - 1}.html" '
                'accesskey="p" data-i18n="previous">\u2039 Prev</a>'
            )
        if chapter_index < len(self.chapters) - 1:
            next_link = (
                f'<a id="kNext" class="next" href="kindle_chapter_{chapter_index + 1}.html" '
                'accesskey="n" data-i18n="next">Next \u203a</a>'
            )
        progress_script = (
            f"setCookie({book_hash_js}, 'chapter_{chapter_index}.html', 365);\n"
        )
        if self.deployment_mode != "server":
            progress_script += f"kRememberBook({book_hash_js});\n"
        # Server mode keeps the Kindle surface read-write for progress
        # (load the saved position, then record the current chapter) while
        # heartbeats stay report-only; the page never displays insights or
        # touches the shelf.  SSG stays fully local (cookies only).
        kindle_server_report_script = ""
        if self.deployment_mode == "server":
            kindle_server_report_script = _KINDLE_READER_SERVER_REPORT_JS % {
                "book_hash": json.dumps(str(self.book_hash)),
                "chapter_index": json.dumps(chapter_index),
            }
        return f"""<!DOCTYPE html>
<html lang="{locale or 'en'}">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="format-detection" content="telephone=no">
<title>{chapter_title_text} - {book_title_text}</title>
<style>
{_KINDLE_READER_CSS}
{_KINDLE_CHAPTER_CSS}
</style>
{style_links}
</head>
<body class="light">
<header class="k-header k-reader-header">
    <a href="kindle.html#chapter-{chapter_index}" data-i18n="contents">{html.escape(kindle_labels["contents"])}</a>
    <button type="button" id="kSettingsToggle" onclick="kToggleSettings()" aria-controls="kSettings"
            aria-expanded="false" data-i18n-aria-label="settings" aria-label="{html.escape(kindle_labels["settings"])}">Aa</button><!-- i18n-allow-literal: stable data identifier -->
    <span class="k-running-title" lang="{book_language}">{chapter_title_text or book_title_text}</span>
</header>
<main id="kViewport" data-book="{html.escape(str(self.book_hash), quote=True)}" data-chapter="{chapter_index}">
    <div class="k-content" id="kText" lang="{book_language}">
        {body_content}
    </div>
</main>
<footer class="k-reader-footer" id="kEnd">
    <nav class="k-nav k-chapter-links">{prev_link}{next_link}</nav>
    <button type="button" id="kTurnBack" onclick="kTurnPage(-1)" data-i18n-aria-label="previousPage" aria-label="{html.escape(kindle_labels["previousPage"])}">‹</button>
    <button type="button" id="kTurnForward" onclick="kTurnPage(1)" data-i18n-aria-label="nextPage" aria-label="{html.escape(kindle_labels["nextPage"])}">›</button>
    <span id="kReaderPosition">{chapter_index + 1}/{len(self.chapters)}</span>
</footer>
<div id="kSettingsBackdrop" onclick="kToggleSettings()" aria-hidden="true"></div>
<div class="k-reader-settings k-surface" id="kSettings" role="dialog" aria-modal="true" aria-labelledby="kSettingsTitle">
    <div class="k-settings-heading">
        <h2 id="kSettingsTitle" data-i18n="settings">{html.escape(kindle_labels["settings"])}</h2>
        <button class="k-control" type="button" onclick="kToggleSettings()" data-i18n-aria-label="done" aria-label="{html.escape(kindle_labels["done"])}">×</button>
    </div>
    <div class="k-settings-appearance">
        <button class="k-control" type="button" onclick="kTheme()" accesskey="t" data-i18n="theme">Theme</button>
        <button class="k-control" type="button" onclick="kFont(-1)" data-i18n="decreaseFont">A-</button>
        <output id="kFontSizeValue"></output>
        <button class="k-control" type="button" onclick="kFont(1)" data-i18n="increaseFont">A+</button>
    </div>
    <div class="k-settings-modes">
        <button class="k-control" type="button" id="kReadingMode" onclick="kToggleReadingMode()" aria-pressed="true"
                data-i18n="pageMode">{html.escape(kindle_labels["pageMode"])}</button>
        <button class="k-control" type="button" id="kClickScroll" onclick="kToggleClickScroll()" aria-pressed="true"
                data-i18n="tapTurn">{html.escape(kindle_labels["tapTurn"])}</button>
    </div>
    <div class="k-settings-links">
        {prev_link.replace('id="kPrev" class="prev"', 'class="k-control"')}
        {next_link.replace('id="kNext" class="next"', 'class="k-control"')}
    </div>
</div>
<script>
{_KINDLE_READER_JS}
{kindle_locale_script(_kindle_i18n_messages, use_initial_locale=locale is not None)}
{_KINDLE_CHAPTER_JS}
{kindle_server_report_script}{progress_script}</script>
</body>
</html>
"""

    def create_pdf_chapter_template(self, chapter_index: int, document_url: str) -> str:
        """Render one PDF page through the canonical chapter template."""
        try:
            page = self._pdf_pages[chapter_index]
            chapter = self.chapters[chapter_index]
        except (AttributeError, IndexError):
            raise ValueError(f"PDF chapter index is out of range: {chapter_index}") from None
        return self.create_chapter_template(
            "",
            "",
            chapter_index,
            chapter["title"],
            pdf_page={
                "document_url": document_url,
                "page_number": page.page_number,
                "width": page.width,
                "height": page.height,
                "encrypted": self._pdf_encrypted,
                "has_extractable_text": self._pdf_has_extractable_text,
            },
        )

    def create_chapter_template(
        self,
        content,
        style_links,
        chapter_index,
        chapter_title,
        pdf_page=None,
    ):
        """创建章节页面模板"""
        if self.deployment_mode == "server":
            content = sanitize_html_fragment(content)
        book_id_url = urllib.parse.quote(str(self.book_hash), safe='')
        book_id_attribute = html.escape(str(self.book_hash), quote=True)
        safe_book_title = metadata_text(self.book_title)
        safe_chapter_title = metadata_text(chapter_title)
        book_title_text = html.escape(safe_book_title, quote=False)
        book_title_attribute = html.escape(safe_book_title, quote=True)
        chapter_title_text = html.escape(safe_chapter_title, quote=False)
        chapter_title_attribute = html.escape(safe_chapter_title, quote=True)
        pdf_config_script = ""
        pdf_stylesheet = ""
        pdf_chapter_script = ""
        pdf_reader_controls = ""
        pdf_mobile_controls = ""
        pdf_search_drawer = ""
        page_width_control_attribute = ""
        page_width_slider_attributes = 'min="1" max="4" value="3" step="1"'
        page_width_value_control = ""
        # The minimal reader is opt-in (--kindle); PDF pages never have a
        # kindle_chapter_N.html page, so neither case embeds an entry script.
        kindle_entry_script = (
            ""
            if (pdf_page is not None or not self.kindle_support)
            else self._kindle_entry_script(f"kindle_chapter_{chapter_index}.html")
        )
        page_width_scale = '''
                            <span data-i18n="settings.pageWidthNarrow">Narrow</span>
                            <span data-i18n="settings.pageWidthComfortable">Comfortable</span>
                            <span data-i18n="settings.pageWidthWide">Wide</span>
                            <span data-i18n="settings.pageWidthExtraWide">Extra wide</span>'''
        if pdf_page is not None:
            page_number = int(pdf_page["page_number"])
            total_pages = len(self.chapters)
            page_params = html.escape(
                json.dumps(
                    {"number": page_number, "total": total_pages},
                    separators=(",", ":"),
                ),
                quote=True,
            )
            content = (
                '<div class="pdf-page-content"'
                f' data-pdf-page-number="{page_number}"'
                f' data-pdf-page-width="{html.escape(str(pdf_page["width"]), quote=True)}"'
                f' data-pdf-page-height="{html.escape(str(pdf_page["height"]), quote=True)}"'
                f' data-pdf-encrypted="{str(bool(pdf_page["encrypted"])).lower()}"'
                f' data-pdf-has-extractable-text="{str(bool(pdf_page["has_extractable_text"])).lower()}"'
                ' data-pdf-loading-message-key="pdf.loadingPage"'
                ' data-pdf-text-unavailable-message-key="pdf.textUnavailable"'
                ' data-pdf-password-required-message-key="pdf.passwordRequired"'
                f' aria-label="Page {page_number} of {total_pages}"'
                ' data-i18n-aria-label="pdf.pageOf"'
                f' data-i18n-params="{page_params}"></div>'
            )
            pdf_config = json.dumps(
                {
                    "documentUrl": str(pdf_page["document_url"]),
                    "pdfjsModuleUrl": self.asset_manifest.url_for(
                        "vendor/pdfjs/build/pdf.mjs"
                    ),
                    "pdfjsWorkerUrl": self.asset_manifest.url_for(
                        "vendor/pdfjs/build/pdf.worker.mjs"
                    ),
                    "encrypted": bool(self._pdf_encrypted),
                    "hasExtractableText": bool(self._pdf_has_extractable_text),
                },
                separators=(",", ":"),
            )
            pdf_config = (
                pdf_config.replace("&", "\\u0026")
                .replace("<", "\\u003c")
                .replace(">", "\\u003e")
            )
            pdf_config_script = f"<script>window.EpubPDFConfig={pdf_config};</script>"
            pdf_stylesheet = (
                '<link rel="stylesheet" href="'
                + self.asset_manifest.url_for("pdf-chapter.css")
                + '">'
            )
            pdf_chapter_script = (
                '<script src="'
                + self.asset_manifest.url_for("pdf-chapter.js")
                + '" defer></script>'
            )
            pdf_reader_controls = '''
            <span class="pdf-chapter-actions" data-pdf-actions>
                <button class="control-btn" id="pdfSearchToggle" type="button" aria-label="Search PDF" data-i18n-aria-label="pdf.search" aria-controls="pdfSearchDrawer" aria-expanded="false"><i class="fas fa-magnifying-glass" aria-hidden="true"></i><span class="control-name" data-i18n="pdf.search">Search PDF</span></button>
                <button class="control-btn" id="pdfZoomOut" type="button" aria-label="Zoom out" data-i18n-aria-label="pdf.zoomOut"><i class="fas fa-magnifying-glass-minus" aria-hidden="true"></i><span class="control-name" data-i18n="pdf.zoomOut">Zoom out</span></button>
                <button class="control-btn" id="pdfZoomIn" type="button" aria-label="Zoom in" data-i18n-aria-label="pdf.zoomIn"><i class="fas fa-magnifying-glass-plus" aria-hidden="true"></i><span class="control-name" data-i18n="pdf.zoomIn">Zoom in</span></button>
                <button class="control-btn" id="pdfFitWidth" type="button" aria-label="Fit width" data-i18n-aria-label="pdf.fitWidth" aria-pressed="false"><i class="fas fa-arrows-left-right" aria-hidden="true"></i><span class="control-name" data-i18n="pdf.fitWidth">Fit width</span></button>
                <button class="control-btn" id="pdfFitPage" type="button" aria-label="Fit page" data-i18n-aria-label="pdf.fitPage" aria-pressed="false"><i class="fas fa-maximize" aria-hidden="true"></i><span class="control-name" data-i18n="pdf.fitPage">Fit page</span></button>
                <button class="control-btn" id="pdfRotate" type="button" aria-label="Rotate page" data-i18n-aria-label="pdf.rotate"><i class="fas fa-rotate-right" aria-hidden="true"></i><span class="control-name" data-i18n="pdf.rotate">Rotate page</span></button>
            </span>'''
            pdf_mobile_controls = '''
        <button class="control-btn" id="mobilePdfSearchToggle" type="button" aria-label="Search PDF" title="Search PDF" data-i18n-aria-label="pdf.search" data-i18n-title="pdf.search" aria-controls="pdfSearchDrawer" aria-expanded="false"><i class="fas fa-magnifying-glass" aria-hidden="true"></i><span data-i18n="pdf.search">Search PDF</span></button>
        <button class="control-btn" id="mobilePdfZoomOut" type="button" aria-label="Zoom out" title="Zoom out" data-i18n-aria-label="pdf.zoomOut" data-i18n-title="pdf.zoomOut"><i class="fas fa-magnifying-glass-minus" aria-hidden="true"></i><span data-i18n="pdf.zoomOut">Zoom out</span></button>
        <button class="control-btn" id="mobilePdfZoomIn" type="button" aria-label="Zoom in" title="Zoom in" data-i18n-aria-label="pdf.zoomIn" data-i18n-title="pdf.zoomIn"><i class="fas fa-magnifying-glass-plus" aria-hidden="true"></i><span data-i18n="pdf.zoomIn">Zoom in</span></button>
        <button class="control-btn" id="mobilePdfFitWidth" type="button" aria-label="Fit width" title="Fit width" data-i18n-aria-label="pdf.fitWidth" data-i18n-title="pdf.fitWidth" aria-pressed="false"><i class="fas fa-arrows-left-right" aria-hidden="true"></i><span data-i18n="pdf.fitWidth">Fit width</span></button>
        <button class="control-btn" id="mobilePdfFitPage" type="button" aria-label="Fit page" title="Fit page" data-i18n-aria-label="pdf.fitPage" data-i18n-title="pdf.fitPage" aria-pressed="false"><i class="fas fa-maximize" aria-hidden="true"></i><span data-i18n="pdf.fitPage">Fit page</span></button>
        <button class="control-btn" id="mobilePdfRotate" type="button" aria-label="Rotate page" title="Rotate page" data-i18n-aria-label="pdf.rotate" data-i18n-title="pdf.rotate"><i class="fas fa-rotate-right" aria-hidden="true"></i><span data-i18n="pdf.rotate">Rotate page</span></button>'''
            pdf_search_drawer = '''
    <nav class="toc-floating reader-drawer pdf-search-drawer" id="pdfSearchDrawer" aria-label="Search PDF" data-i18n-aria-label="pdf.search" aria-hidden="true">
        <div class="toc-header">
            <h3 data-i18n="pdf.search">Search PDF</h3>
            <button class="toc-close" id="pdfSearchClose" type="button" aria-label="Close PDF search" data-i18n-aria-label="pdf.closeSearch"><i class="fas fa-times" aria-hidden="true"></i></button>
        </div>
        <form class="pdf-search-form" id="pdfSearchForm" role="search">
            <label class="visually-hidden" for="pdfSearchInput" data-i18n="pdf.search">Search PDF</label>
            <input id="pdfSearchInput" type="search" autocomplete="off" placeholder="Search PDF" data-i18n-placeholder="pdf.searchPlaceholder">
            <button class="control-btn" type="submit" aria-label="Search PDF" data-i18n-aria-label="pdf.search"><i class="fas fa-magnifying-glass" aria-hidden="true"></i></button>
        </form>
        <ul class="toc-list pdf-search-results" id="pdfSearchResults" aria-live="polite"></ul>
    </nav>'''
            page_width_control_attribute = " data-pdf-zoom-control"
            page_width_slider_attributes = 'min="25" max="400" value="100" step="1"'
            page_width_value_control = '''
                        <label class="pdf-zoom-value" for="pageWidthValue">
                            <input id="pageWidthValue" type="number" min="25" max="400" value="100" step="1" aria-label="Page width" data-i18n-aria-label="settings.pageWidth">
                            <span aria-hidden="true">%</span>
                        </label>'''
            page_width_scale = '''
                            <span>25%</span>
                            <span>100%</span>
                            <span>200%</span>
                            <span>400%</span>'''
        font_size_control = ""
        if pdf_page is None:
            sizes = len(_READER_FONT_SIZES_REM)
            font_sizes = ",".join(f"{size:g}" for size in _READER_FONT_SIZES_REM)
            scale_marks = "".join(
                '<span class="scale-mark major"></span>'
                if level in (1, _DEFAULT_READER_FONT_LEVEL, sizes)
                else '<span class="scale-mark"></span>'
                for level in range(1, sizes + 1)
            )
            font_size_control = f'''
                <div class="settings-group">
                    <label class="settings-label" for="fontSizeSlider" data-i18n="settings.fontSize">Font size</label>
                    <div class="font-size-control">
                        <input type="range" id="fontSizeSlider" min="1" max="{sizes}" value="{_DEFAULT_READER_FONT_LEVEL}" step="1" data-sizes-rem="{font_sizes}">
                        <div class="font-size-scale" aria-hidden="true">{scale_marks}</div>
                    </div>
                </div>'''
        ai_chapter_button = (
            '<button class="control-btn" type="button" aria-label="AI reading" '
            'data-i18n-aria-label="ai.chapterRead" data-ai-learning-canvas aria-pressed="false" '
            f'data-book-id="{book_id_attribute}" data-chapter-index="{chapter_index}">'
            '<i class="fas fa-wand-magic-sparkles" aria-hidden="true"></i>'
            '<span class="control-name" data-i18n="ai.chapterRead">AI reading</span></button>'
            if self.deployment_mode == "server" and pdf_page is None and self.ai_reading_enabled
            else ""
        )
        ai_followup_button = (
            '<button class="control-btn" type="button" aria-label="Ask AI" '
            'data-i18n-aria-label="ai.askChapter" data-ai-followup-drawer '
            f'data-book-id="{book_id_attribute}" data-chapter-index="{chapter_index}">'
            '<i class="fas fa-comments" aria-hidden="true"></i>'
            '<span class="control-name" data-i18n="ai.askChapter">Ask AI</span></button>'
            if self.deployment_mode == "server" and pdf_page is None and self.ai_reading_enabled
            else ""
        )
        ai_feature_assets = (
            self._server_ai_feature_assets()
            if pdf_page is None and self.ai_reading_enabled else ""
        )
        ai_reading_navigation = (
            f'<button type="button" class="app-nav-link" data-ai-reading-hub '
            f'data-book-id="{book_id_attribute}" aria-haspopup="dialog">'
            '<i class="fas fa-wand-magic-sparkles" aria-hidden="true"></i>'
            '<span data-i18n="ai.library">AI readings</span></button>'
            if self.deployment_mode == "server" and pdf_page is None and self.ai_reading_enabled else ""
        )
        reading_insights_navigation = (
            f'<button type="button" class="app-nav-link" data-reading-insights data-book-id="{book_id_attribute}" '
            'aria-haspopup="dialog"><i class="fas fa-chart-column" '
            'aria-hidden="true"></i><span data-i18n="readingInsights.navigation">Reading insights</span></button>'
            if self.deployment_mode == "server" else ""
        )
        ai_reading_indicators = (
            f' data-ai-reading-indicators data-book-id="{book_id_attribute}"'
            if self.deployment_mode == "server" and pdf_page is None and self.ai_reading_enabled else ""
        )
        mobile_ai_reading_button = (
            '<button class="control-btn" id="mobileAIReadingBtn" type="button" '
            'data-ai-learning-canvas aria-pressed="false" '
            f'data-book-id="{book_id_attribute}" data-chapter-index="{chapter_index}" '
            'aria-label="AI reading" title="AI reading" '
            'data-i18n-aria-label="ai.chapterRead" data-i18n-title="ai.chapterRead">'
            '<i class="fas fa-wand-magic-sparkles"></i>'
            '<span data-i18n="ai.chapterRead">AI reading</span></button>'
            if self.deployment_mode == "server" and pdf_page is None and self.ai_reading_enabled else ""
        )
        mobile_ai_followup_button = (
            '<button class="control-btn" id="mobileAIChatBtn" type="button" '
            'data-ai-followup-drawer '
            f'data-book-id="{book_id_attribute}" data-chapter-index="{chapter_index}" '
            'aria-label="Ask AI" title="Ask AI" '
            'data-i18n-aria-label="ai.askChapter" data-i18n-title="ai.askChapter">'
            '<i class="fas fa-comments" aria-hidden="true"></i>'
            '<span data-i18n="ai.askChapter">Ask AI</span></button>'
            if self.deployment_mode == "server" and pdf_page is None and self.ai_reading_enabled else ""
        )
        ai_chapter_scripts = (
            '<script src="/assets/ai-feature-loader.js" defer></script>'
            if self.deployment_mode == "server" and pdf_page is None and self.ai_reading_enabled else ""
        )
        dictionary_assets = (
            '<link rel="stylesheet" href="/assets/dictionary.css">\n'
            '<script src="/assets/dictionary.js" defer></script>'
            if self.deployment_mode == "server" else ""
        )
        book_search_controls = ""
        book_search_mobile_controls = ""
        book_search_drawer = ""
        book_search_script = ""
        book_search_stylesheet = ""
        if self.deployment_mode == "server" and pdf_page is None:
            book_search_stylesheet = '<link rel="stylesheet" href="/assets/book-search.css">'
            book_search_controls = '''
            <button class="control-btn" id="bookSearchToggle" type="button" aria-label="Search this book" data-i18n-aria-label="book.search" aria-controls="bookSearchDrawer" aria-expanded="false"><i class="fas fa-magnifying-glass" aria-hidden="true"></i><span class="control-name" data-i18n="book.search">Search this book</span></button>'''
            book_search_mobile_controls = '''
        <button class="control-btn" id="mobileBookSearchToggle" type="button" aria-label="Search this book" title="Search this book" data-i18n-aria-label="book.search" data-i18n-title="book.search" aria-controls="bookSearchDrawer" aria-expanded="false"><i class="fas fa-magnifying-glass" aria-hidden="true"></i><span data-i18n="book.search">Search this book</span></button>'''
            book_search_drawer = f'''
    <nav class="toc-floating reader-drawer book-search-drawer" id="bookSearchDrawer" aria-label="Search this book" data-i18n-aria-label="book.search" aria-hidden="true">
        <div class="toc-header">
            <h3 data-i18n="book.search">Search this book</h3>
            <button class="toc-close" id="bookSearchClose" type="button" aria-label="Close search" data-i18n-aria-label="book.closeSearch"><i class="fas fa-times" aria-hidden="true"></i></button>
        </div>
{_BOOK_SEARCH_BODY}
    </nav>'''
            book_search_script = '<script src="/assets/book-search.js" defer></script>'
        reading_session_context = (
            f'<meta data-reading-session data-book-id="{book_id_attribute}" '
            f'data-chapter-index="{chapter_index}" data-chapter-label="{chapter_title_attribute}">'
            if self.deployment_mode == "server" else ""
        )
        reading_session_script = (
            '<script src="' + self.asset_manifest.url_for("reading-sessions.js") + '" defer></script>'
            if self.deployment_mode == "server" else ""
        )
        server_account_stylesheet = SERVER_ACCOUNT_STYLESHEET if self.deployment_mode == "server" else ""
        # Locale selection is shared navigation chrome in both SSG and Server.
        server_locale_control = SERVER_LOCALE_CONTROL
        server_account_control = SERVER_ACCOUNT_CONTROL if self.deployment_mode == "server" else ""
        server_account_panel = render_account_panel(self.kindle_support) if self.deployment_mode == "server" else ""
        server_locale_script = SERVER_LOCALE_SCRIPT
        prev_href = f'href="/book/{book_id_url}/chapter_{chapter_index-1}.html"' if chapter_index > 0 else ''
        next_href = f'href="/book/{book_id_url}/chapter_{chapter_index+1}.html"' if chapter_index < len(self.chapters) - 1 else ''
        prev_link = f'<a {prev_href} id="readerPreviousChapter" class="control-btn prev-chapter" aria-label="Previous chapter" data-i18n-aria-label="reader.previous" aria-disabled="{"false" if prev_href else "true"}"><i class="fas fa-arrow-left" aria-hidden="true"></i><span class="control-name" data-i18n="reader.previous">Previous chapter</span></a>'
        next_link = f'<a {next_href} id="readerNextChapter" class="control-btn next-chapter" aria-label="Next chapter" data-i18n-aria-label="reader.next" aria-disabled="{"false" if next_href else "true"}"><i class="fas fa-arrow-right" aria-hidden="true"></i><span class="control-name" data-i18n="reader.next">Next chapter</span></a>'
        prev_link_mobile = f'<a {prev_href} aria-label="Previous chapter" title="Previous chapter" data-i18n-aria-label="reader.previous" data-i18n-title="reader.previous"> <div class="control-btn" aria-label="Previous chapter" data-i18n-aria-label="reader.previous"> <i class="fas fa-arrow-left"></i><span data-i18n="reader.previous">Previous chapter</span></div></a>'
        next_link_mobile = f'<a {next_href} aria-label="Next chapter" title="Next chapter" data-i18n-aria-label="reader.next" data-i18n-title="reader.next"> <div class="control-btn" aria-label="Next chapter" data-i18n-aria-label="reader.next"> <i class="fas fa-arrow-right"></i><span data-i18n="reader.next">Next chapter</span></div></a>'
        bookshelf_data_actions = """
                    <button class="bookshelf-action-btn" id="exportShelfBtn">
                        <i class="fas fa-upload" aria-hidden="true"></i> <span data-i18n="bookshelf.export">Export</span>
                    </button>
                    <button class="bookshelf-action-btn" id="importShelfBtn">
                        <i class="fas fa-download" aria-hidden="true"></i> <span data-i18n="bookshelf.import">Import</span>
                    </button>
                    <input type="file" id="importShelfFile" accept=".json" style="display: none;">""" if self.deployment_mode == "ssg" else ""

        highlight_assets = ""
        if pdf_page is None:
            highlight_assets = " " + " ".join(
                f'data-highlight-{key}="{html.escape(self.asset_manifest.url_for(path), quote=True)}"'
                for key, path in (
                    ("script", "vendor/highlight/highlight.min.js"),
                    ("light", "vendor/highlight/github.min.css"),
                    ("dark", "vendor/highlight/github-dark.min.css"),
                )
            )

        chapter_html =  f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="theme-color" content="#244548">
    <meta name="description" content="{chapter_title_attribute} - {book_title_attribute} - EPUB Browser">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="default">
    <meta name="apple-mobile-web-app-title" content="EPUB Browser">
    <title>{chapter_title_text} - {book_title_text}</title>
    {reading_session_context}
    {render_i18n_runtime_and_inline(deployment_mode=self.deployment_mode)}
    <script>window.EpubBrowserI18n.init();</script>
    {pdf_config_script}
    {ai_feature_assets}
    <noscript><link rel="manifest" href="/assets/manifest.en.json"></noscript>
    {style_links}
    <link rel="stylesheet" href="/assets/vendor/fontawesome/css/all.min.css">
    <link rel="stylesheet" href="/assets/theme.css">
    <link rel="stylesheet" href="/assets/notification.css">
    <link rel="stylesheet" href="/assets/dialog.css">
    <link rel="stylesheet" href="/assets/chapter.css?v=18">
    {book_search_stylesheet}
    {pdf_stylesheet}
    <link rel="stylesheet" href="/assets/breadcrumb.css?v=3">
    <link rel="stylesheet" href="/assets/loading.css?v=15">
    <link rel="stylesheet" href="/assets/annotation.css">
    <link rel="stylesheet" href="/assets/annotation-hub.css">
    {server_account_stylesheet}
    <link rel="stylesheet" href="/assets/vendor/glightbox/glightbox.min.css">
    <link rel="icon" type="image/png" href="/assets/favicon.png">
    <link rel="apple-touch-icon" href="/assets/icon-192.png">
    <link rel="stylesheet" href="/assets/bookshelf.css">
"""
        chapter_html += """
    <script src="/assets/theme-bootstrap.js"></script>
{kindle_entry_script}
</head>
"""
        chapter_html +=f"""
<body{(' class="pdf-source"' if pdf_page is not None else '')}>

    <a class="skip-link" href="#eb-content" data-i18n="reader.skipToContent">Skip to reading content</a>

    <div class="reading-progress-container">
        <div class="progress-bar" id="progressBar"></div>
    </div>

    <nav class="toc-floating reader-drawer" id="bookHomeFloating" aria-label="Book chapters" data-i18n-aria-label="reader.bookChapters" aria-hidden="true"{ai_reading_indicators}>
        <div class="toc-header">
            <h3 data-i18n="reader.bookChapters">Chapters</h3>
            <div class="toc-header-actions">
                <button class="toc-current-chapter" id="bookHomeLocateCurrent" type="button" aria-label="Locate current chapter" data-i18n-aria-label="reader.locateCurrentChapter">
                    <i class="fas fa-crosshairs" aria-hidden="true"></i>
                </button>
                <a class="toc-book-home" href="index.html" aria-label="Open book home" data-i18n-aria-label="reader.openBookHome">
                    <i class="fas fa-book" aria-hidden="true"></i><span data-i18n="reader.openBookHome">Open book home</span>
                </a>
                <button class="toc-close" id="bookHomeClose" type="button" aria-label="Close book home" data-i18n-aria-label="reader.closeBookHome">
                    <i class="fas fa-times" aria-hidden="true"></i>
                </button>
            </div>
        </div>
        <ul class="toc-list" id="bookHomeTocList">
            <!-- 动态生成的书籍目录将放在这里 -->
        </ul>
    </nav>

    <nav class="toc-floating reader-drawer" id="tocFloating" aria-label="This chapter contents" data-i18n-aria-label="reader.thisChapterContents" aria-hidden="true"{ai_reading_indicators}>
        <div class="toc-header">
            <h3 data-i18n="reader.thisChapterContents">This chapter</h3>
            <div class="toc-header-actions">
                <button class="toc-current-chapter" id="tocLocateCurrent" type="button" aria-label="Locate current section" data-i18n-aria-label="reader.locateCurrentSection">
                    <i class="fas fa-crosshairs" aria-hidden="true"></i>
                </button>
                <button class="toc-close" id="tocClose" aria-label="Close table of contents" data-i18n-aria-label="reader.closeTableOfContents">
                    <i class="fas fa-times"></i>
                </button>
            </div>
        </div>
        <ul class="toc-list" id="tocList">
            <!-- 动态生成的目录将放在这里 -->
        </ul>
    </nav>
    {pdf_search_drawer}
    {book_search_drawer}

    <div class="reader-drawer-backdrop" id="readerDrawerBackdrop" aria-hidden="true"></div>

    <header class="chapter-top-bar app-header">
        <nav class="app-nav" aria-label="Reading navigation" data-i18n-aria-label="reader.navigation">
            <a class="app-nav-brand" href="/" aria-label="EPUB Browser" data-i18n-aria-label="common.brand"><img class="app-nav-brand-mark" src="/assets/logo-mark-color.png" width="32" height="32" alt=""><span data-i18n="common.brand">EPUB Browser</span></a>
            <div class="app-nav-links">
                <button type="button" class="app-nav-link" id="bookshelfBtn" aria-haspopup="dialog" aria-controls="bookshelfModal"><i class="fas fa-bookmark" aria-hidden="true"></i><span data-i18n="reader.shelf">Shelf</span></button>
                <button type="button" class="app-nav-link" id="chapterAnnotationsBtn" data-annotation-hub data-book-hash="{book_id_attribute}" aria-haspopup="dialog"><i class="fas fa-highlighter" aria-hidden="true"></i><span data-i18n="reader.annotations">Annotations</span></button>
                {render_vocabulary_navigation(self.book_hash) if self.deployment_mode == "server" else ""}
                {reading_insights_navigation}
                {ai_reading_navigation}
            </div>
            <div class="app-nav-actions">
                {server_locale_control}
                <button class="theme-toggle app-nav-action app-nav-theme" id="themeToggle" type="button" aria-label="Theme" data-i18n-aria-label="reader.theme"><i class="fas fa-moon" aria-hidden="true"></i><span class="app-nav-action-label" data-i18n="reader.theme">Theme</span></button>
                {server_account_control}
            </div>
        </nav>
    </header>
    <div class="container">
        <div class="reader-toolbar top-controls chapter-tools" role="toolbar" aria-label="Reading tools" data-i18n-aria-label="reader.navigation">
            <button class="control-btn" id="bookHomeToggle" type="button" aria-label="Open book chapters" data-i18n-aria-label="reader.openBookChapters" aria-controls="bookHomeFloating" aria-expanded="false"><i class="fas fa-book"></i><span class="control-name" data-i18n="reader.bookChapters">Chapters</span></button>
            <button class="control-btn" id="tocToggle" type="button" aria-label="This chapter contents" data-i18n-aria-label="reader.thisChapterContents" aria-controls="tocFloating" aria-expanded="false"><i class="fas fa-list"></i><span class="control-name" data-i18n="reader.thisChapterContents">This chapter</span></button>
            <button class="control-btn" id="settingsControlBtn" type="button" aria-label="Settings" data-i18n-aria-label="reader.settings" aria-controls="settingsModal" aria-expanded="false"><i class="fas fa-cog"></i><span class="control-name" data-i18n="reader.settings">Settings</span></button>
            <div class="pagination-toolbar-controls" id="paginationInfo" role="group" aria-label="Page navigation" data-i18n-aria-label="reader.navigation">
                {prev_link}
                <button class="control-btn" id="prevPage" type="button" aria-label="Previous page" data-i18n-aria-label="reader.previousPage" data-pagination-toolbar-control hidden><i class="fas fa-chevron-left" aria-hidden="true"></i><span class="control-name" data-i18n="reader.previousPage">Previous page</span></button>
                <button class="control-btn" id="reloadPages" type="button" aria-label="Reload pages" data-i18n-aria-label="reader.reloadPages" data-pagination-toolbar-control hidden><i class="fas fa-rotate-right" aria-hidden="true"></i><span class="control-name" data-i18n="reader.reloadPages">Reload pages</span></button>
                <button class="control-btn" id="nextPage" type="button" aria-label="Next page" data-i18n-aria-label="reader.nextPage" data-pagination-toolbar-control hidden><i class="fas fa-chevron-right" aria-hidden="true"></i><span class="control-name" data-i18n="reader.nextPage">Next page</span></button>
                {next_link}
                <span class="pagination-page-status" id="currentPage" aria-live="polite">1</span>
                <span class="pagination-page-status" id="totalPages" aria-label="Total pages" data-i18n-aria-label="reader.totalPages">1</span>
                <button class="control-btn" id="pageJumpToggle" type="button" aria-label="Jump" data-i18n-aria-label="reader.jump" aria-controls="paginationPageJumpPopover" aria-expanded="false" data-pagination-toolbar-control hidden><i class="fas fa-arrow-right-to-bracket" aria-hidden="true"></i><span class="control-name" data-i18n="reader.jump">Jump</span></button>
                <section class="pagination-page-jump-popover" id="paginationPageJumpPopover" role="dialog" aria-modal="false" aria-labelledby="paginationPageJumpTitle" aria-describedby="paginationPageJumpRange" aria-hidden="true" hidden>
                    <strong class="pagination-page-jump-title" id="paginationPageJumpTitle" data-i18n="reader.jump">Jump</strong>
                    <p class="pagination-page-jump-range" id="paginationPageJumpRange"></p>
                    <label class="pagination-page-jump-label" for="pageJumpInput" data-i18n="reader.currentPage">Current page</label>
                    <div class="pagination-page-jump-form">
                        <input type="number" id="pageJumpInput" min="1" max="1" value="1" inputmode="numeric" aria-label="Current page" data-i18n-aria-label="reader.currentPage">
                        <button class="pagination-jump-submit" id="goToPage" type="button" aria-label="Jump" data-i18n-aria-label="reader.jump"><i class="fas fa-arrow-right-to-bracket" aria-hidden="true"></i></button>
                    </div>
                </section>
            </div>
            {pdf_reader_controls}
            {book_search_controls}
            {ai_chapter_button}
            {ai_followup_button}
        </div>
        <div class="eb-content-container" id="eb-content-container" data-id="eb-content-container">
            <div class="content-loading is-visible" id="contentLoading" aria-live="polite" aria-label="Loading content" data-i18n-aria-label="reader.loadingContent">
                <div class="loading-spinner"></div>
            </div>
            <article class="eb-content" id="eb-content" lang="{html.escape(self.lang or 'en', quote=True)}" dir="auto" data-eb-styles data-chapter-index="{chapter_index}" data-chapter-title="{chapter_title_attribute}" data-book-hash="{book_id_attribute}" data-total-chapters="{len(self.chapters)}"{highlight_assets}>
            {content}
            </article>
        </div>

    </div>

    <div class="settings-overlay" id="settingsOverlay" data-id="settingsOverlay" aria-hidden="true"></div>
    <div class="settings-modal" id="settingsModal" data-id="settingsModal" role="dialog" aria-modal="true" aria-hidden="true" aria-labelledby="settingsModalTitle">
        <div class="settings-header">
            <h2 class="settings-header-title" id="settingsModalTitle">
                <i class="fas fa-cog" aria-hidden="true"></i>
                <span data-i18n="reader.settings">Settings</span>
            </h2>
            <button class="settings-close-btn" id="settingsCloseBtn" type="button" aria-label="Close settings" data-i18n-aria-label="reader.closeSettings">
                <i class="fas fa-times"></i>
            </button>
        </div>
        <div class="settings-tabs">
            <button class="settings-tab active" data-tab="font">
                <i class="fas fa-font"></i>
                <span data-i18n="settings.appearance">Appearance</span>
            </button>
            <button class="settings-tab" data-tab="reading">
                <i class="fas fa-book-reader"></i>
                <span data-i18n="settings.reading">Reading</span>
            </button>
        </div>
        <div class="settings-content">
            <div class="settings-tab-panel active" id="font-tab">
                <div class="settings-group">
                    <label class="settings-label" data-i18n="settings.fontFamily">Font family</label>
        <div class="font-family-selector">
            <select id="fontFamilySelect">
                <option value="ebook-default" selected data-i18n="settings.bookDefault">Book default</option>
                <option value="system-ui, -apple-system, sans-serif" data-i18n="settings.systemDefault">System default</option>
                <option value="custom" data-i18n="settings.customByInput">Custom by input</option>
            </select>
        </div>
        <div class="custom-font-input" id="customFontInput" style="display: none;">
            <input type="text" id="customFontFamily" placeholder="Input font name here" data-i18n-placeholder="settings.customFontPlaceholder">
            <small data-i18n="settings.customFontTip">Tip: Font family applies globally. Ensure it’s installed in the system.</small>
            <button class="css-btn primary" id="applyFontSettings">
                <i class="fas fa-check"></i> <span data-i18n="settings.apply">Apply</span>
            </button>
        </div>
                </div>
                {font_size_control}
                <div class="settings-group">
                    <div class="settings-label-row">
                        <label class="settings-label" for="pageWidthSlider" data-i18n="settings.pageWidth">Page width</label>
                        {page_width_value_control}
                    </div>
                    <div class="page-width-control"{page_width_control_attribute}>
                        <input type="range" id="pageWidthSlider" {page_width_slider_attributes} aria-label="Page width" data-i18n-aria-label="settings.pageWidth">
                        <div class="page-width-scale" aria-hidden="true">
                            {page_width_scale}
                        </div>
                    </div>
                </div>
                <div class="settings-group settings-group-custom-css">
                    <div class="settings-section-heading">
                        <span class="settings-section-title" data-i18n="settings.customStyles">Custom styles</span>
                        <span class="settings-section-optional" data-i18n="settings.optional">Optional</span>
                    </div>
                    <p class="settings-section-description" data-i18n="settings.customStylesDescription">Use CSS to fine-tune this book’s typography and layout.</p>
                    <div class="css-editor">
                        <textarea id="customCssInput" placeholder="Please input your CSS code... For example: #eb-content-container{{background: inherit; box-shadow:inherit;}} #eb-content{{margin: 50px; width: auto}} #eb-content p {{margin-bottom: 0.8rem; line-height: 1.7;}}" data-i18n-placeholder="settings.customCssPlaceholder"></textarea>
                        <div class="css-controls">
                            <button class="css-btn primary" id="saveCssBtn">
                                <i class="fas fa-save"></i> <span data-i18n="settings.save">Save</span>
                            </button>
                            <button class="css-btn primary" id="saveAsDefaultBtn">
                                <i class="fas fa-star"></i> <span data-i18n="settings.saveAsDefault">Save as default</span>
                            </button>
                            <button class="css-btn secondary" id="resetCssBtn">
                                <i class="fas fa-undo"></i> <span data-i18n="settings.reset">Reset</span>
                            </button>
                            <button class="css-btn secondary" id="loadDefaultBtn">
                                <i class="fas fa-download"></i> <span data-i18n="settings.loadDefault">Load default</span>
                            </button>
                            <button class="css-btn secondary" id="previewCssBtn">
                                <i class="fas fa-eye"></i> <span data-i18n="settings.preview">Preview</span>
                            </button>
                        </div>
                        <div class="css-info">
                            <p><i class="fas fa-info-circle"></i> <span data-i18n="settings.defaultStyleTip">Tip: The default style will be applied to all books unless a custom style is set for specific books.</span></p>
                        </div>
                    </div>
                </div>
            </div>
            <div class="settings-tab-panel" id="reading-tab">
                <div class="settings-group">
                    <label class="settings-label" data-i18n="settings.readingMode">Reading mode</label>
                    <label class="settings-switch">
                        <input type="checkbox" id="showReadingProgressBarToggle" checked>
                        <span class="switch-slider"></span>
                        <span class="switch-text" data-i18n="settings.showReadingProgressBar">Show reading progress bar</span>
                    </label>
                    <label class="settings-switch">
                        <input type="checkbox" id="paginationModeToggle">
                        <span class="switch-slider"></span>
                        <span class="switch-text" data-i18n="settings.paginationMode">Use page-turning mode</span>
                    </label>
                    <div class="settings-option-with-tip">
                        <label class="settings-switch">
                            <input type="checkbox" id="clickPageToggle" disabled aria-disabled="true">
                            <span class="switch-slider"></span>
                            <span class="switch-text" data-i18n="reader.clickToTurn">Click to turn page</span>
                        </label>
                        <button type="button" class="settings-info-tip" data-settings-tip data-tip="In page-turning mode, click or tap the left and right sides to turn pages. On mobile, tap the center to show or hide the reading controls. Selecting text, dragging, and long-pressing will not trigger these actions." data-i18n-data-tip="settings.clickPageHelp" aria-label="In page-turning mode, click or tap the left and right sides to turn pages. On mobile, tap the center to show or hide the reading controls. Selecting text, dragging, and long-pressing will not trigger these actions." data-i18n-aria-label="settings.clickPageHelp">
                            <i class="fas fa-info-circle" aria-hidden="true"></i>
                        </button>
                    </div>
                    <label class="settings-switch pagination-incompatible-setting">
                        <input type="checkbox" id="continuousScrollToggle">
                        <span class="switch-slider"></span>
                        <span class="switch-text" data-i18n="settings.continuousScroll">Enable continuous scroll</span>
                        <span class="continuous-scroll-tip" id="continuousScrollTip" tabindex="0" data-settings-tip data-tip="Automatically loads the next chapter when scrolling past the end. Note: scroll progress save/restore is disabled. Tip: press Space for a similar seamless reading experience when this is off." data-i18n-data-tip="settings.continuousScrollTip" aria-label="Automatically loads the next chapter when scrolling past the end. Note: scroll progress save/restore is disabled. Tip: press Space for a similar seamless reading experience when this is off." data-i18n-aria-label="settings.continuousScrollTip">
                            <i class="fas fa-info-circle" aria-hidden="true"></i>
                        </span>
                    </label>
                </div>
                <fieldset class="settings-group desktop-layout-settings">
                    <legend class="settings-section-title" data-i18n="settings.desktopLayout">Desktop layout</legend>
                    <div class="desktop-layout-options">
                        <label class="settings-switch desktop-layout-option desktop-setting-only">
                            <input type="checkbox" id="desktopChapterSidebarToggle">
                            <span class="switch-slider"></span>
                            <span class="switch-text" data-i18n="settings.desktopChapterSidebar">Show chapter sidebar</span>
                        </label>
                        <div class="desktop-layout-option settings-option-with-tip desktop-setting-only">
                            <label class="settings-switch">
                                <input type="checkbox" id="autoHideDesktopChapterSidebarToggle" disabled aria-disabled="true">
                                <span class="switch-slider"></span>
                                <span class="switch-text" data-i18n="settings.autoHideDesktopChapterSidebar">Auto-hide chapter sidebar</span>
                            </label>
                            <button type="button" class="settings-info-tip" data-settings-tip data-tip="Move the pointer to the left edge, or use Tab, to show the chapter sidebar." data-i18n-data-tip="settings.autoHideDesktopChapterSidebarHelp" aria-label="Move the pointer to the left edge, or use Tab, to show the chapter sidebar." data-i18n-aria-label="settings.autoHideDesktopChapterSidebarHelp">
                                <i class="fas fa-info-circle" aria-hidden="true"></i>
                            </button>
                        </div>
                        <div class="desktop-layout-option settings-option-with-tip">
                            <label class="settings-switch">
                                <input type="checkbox" id="autoHideDesktopToolbarToggle">
                                <span class="switch-slider"></span>
                                <span class="switch-text" data-i18n="settings.autoHideDesktopToolbar">Auto-hide reading toolbar</span>
                            </label>
                            <button type="button" class="settings-info-tip" data-settings-tip data-tip="Move the pointer to the right edge, or use Tab, to show the toolbar." data-i18n-data-tip="settings.autoHideDesktopToolbarHelp" aria-label="Move the pointer to the right edge, or use Tab, to show the toolbar." data-i18n-aria-label="settings.autoHideDesktopToolbarHelp">
                                <i class="fas fa-info-circle" aria-hidden="true"></i>
                            </button>
                        </div>
                    </div>
                </fieldset>
                <fieldset class="settings-group keyboard-navigation-settings">
                    <legend class="settings-section-title" data-i18n="settings.keyboardNavigation">Keyboard navigation</legend>
                    <div class="keyboard-navigation-options">
                        <label class="settings-switch keyboard-navigation-option">
                            <input type="checkbox" id="arrowKeyNavigationToggle" checked>
                            <span class="switch-slider"></span>
                            <span class="switch-text" data-i18n="settings.arrowKeyNavigation">Use Left and Right Arrow keys to navigate</span>
                        </label>
                        <label class="settings-switch keyboard-navigation-option">
                            <input type="checkbox" id="spaceKeyNavigationToggle" checked>
                            <span class="switch-slider"></span>
                            <span class="switch-text" data-i18n="settings.spaceKeyNavigation">Use Space for the next page or chapter</span>
                        </label>
                    </div>
                </fieldset>
                <fieldset class="settings-group navigation-behavior-settings pagination-incompatible-setting" aria-describedby="navigationBehaviorHelp">
                    <legend class="settings-section-title" data-i18n="settings.navigationBehavior">Navigation bar behavior</legend>
                    <p class="settings-section-description" id="navigationBehaviorHelp" data-i18n="settings.navigationBehaviorHelp">Choose when the top navigation stays visible while you read.</p>
                    <div class="navigation-behavior-options">
                        <label class="navigation-behavior-option"><input type="radio" name="navigationBehavior" value="normal" checked><span data-i18n="settings.navigationBehavior.normal">Normal scroll</span></label>
                        <label class="navigation-behavior-option"><input type="radio" name="navigationBehavior" value="sticky"><span data-i18n="settings.navigationBehavior.sticky">Always sticky</span></label>
                        <label class="navigation-behavior-option"><input type="radio" name="navigationBehavior" value="auto-hide"><span data-i18n="settings.navigationBehavior.autoHide">Hide down, show up</span></label>
                    </div>
                </fieldset>
            </div>
        </div>
    </div>

    <div class="reading-controls" data-id="reading-controls">
        <button class="control-btn" id="scrollToTopBtn" type="button" aria-label="Top" data-i18n-aria-label="reader.top">
            <i class="fas fa-arrow-up"></i>
            <span class="control-name" data-i18n="reader.top">Top</span>
        </button>
        <a class="control-btn" id="bookHomeShortcut" href="index.html" aria-label="Open book home" data-i18n-aria-label="reader.openBookHome" title="Open book home" data-i18n-title="reader.openBookHome">
            <i class="fas fa-book-open"></i>
            <span class="control-name" data-i18n="reader.openBookHome">Book home</span>
        </a>
    </div>

    <!-- 移动端控件 -->
    <div class="mobile-controls" data-id="mobile-controls">
        <button class="control-btn" id="mobileTocBtn" type="button" aria-label="This chapter contents" title="This chapter contents" data-i18n-aria-label="reader.thisChapterContents" data-i18n-title="reader.thisChapterContents" aria-controls="tocFloating" aria-expanded="false">
            <i class="fas fa-list"></i>
            <span data-i18n="reader.thisChapterContents">This chapter</span>
        </button>
        <button class="control-btn" id="mobileBookHomeBtn" type="button" aria-label="Open book chapters" title="Open book chapters" data-i18n-aria-label="reader.openBookChapters" data-i18n-title="reader.openBookChapters">
            <i class="fas fa-book"></i>
            <span data-i18n="reader.bookChapters">Chapters</span>
        </button>
        {pdf_mobile_controls}
        {book_search_mobile_controls}
        {mobile_ai_reading_button}
        {mobile_ai_followup_button}
        {prev_link_mobile}
        <a href="/" aria-label="Home" title="Home" data-i18n-aria-label="reader.home" data-i18n-title="reader.home">
            <div class="control-btn" aria-label="Home" data-i18n-aria-label="reader.home">
                <i class="fas fa-home"></i>
                <span data-i18n="reader.home">Home</span>
            </div>
        </a>
        {next_link_mobile}
        <button class="control-btn" id="mobilePageJumpBtn" type="button" aria-label="Jump" title="Jump" data-i18n-aria-label="reader.jump" data-i18n-title="reader.jump">
            <i class="fas fa-arrow-right-to-bracket" aria-hidden="true"></i>
            <span data-i18n="reader.jump">Jump</span>
        </button>
        <button class="control-btn" id="mobileSettingsBtn" type="button" aria-label="Settings" title="Settings" data-i18n-aria-label="reader.settings" data-i18n-title="reader.settings" aria-controls="settingsModal" aria-expanded="false">
            <i class="fas fa-cog"></i>
            <span data-i18n="reader.settings">Settings</span>
        </button>
        <a class="control-btn" id="mobileBookHomeShortcut" href="index.html" aria-label="Open book home" title="Open book home" data-i18n-aria-label="reader.openBookHome" data-i18n-title="reader.openBookHome">
            <i class="fas fa-book-open"></i>
            <span data-i18n="reader.openBookHome">Book home</span>
        </a>
        <button class="control-btn" id="mobileTopBtn" type="button" aria-label="Top" title="Top" data-i18n-aria-label="reader.top" data-i18n-title="reader.top">
            <i class="fas fa-arrow-up"></i>
            <span data-i18n="reader.top">Top</span>
        </button>
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
    {render_footer(datetime.now().year, release_api_url='/api/version' if self.deployment_mode == 'server' else '')}
"""
        cache_boundary_script = (
            '<script src="/assets/cache-boundary.js" defer></script>'
            if self.deployment_mode == "server"
            else ""
        )
        reading_insights_assets = (
            '<link rel="stylesheet" href="' + self.asset_manifest.url_for('reading-insights.css') + '">'
            '<script src="' + self.asset_manifest.url_for('reading-insights.js') + '" defer></script>'
            if self.deployment_mode == "server" else ""
        )
        auth_script = (
            SERVER_AUTH_SCRIPT
            if self.deployment_mode == "server"
            else ""
        )
        startup = (
            """function startChapterClients() {
        if (!window.EpubBrowserAuth) return;
        window.EpubBrowserAuth.init().then(function(session) {
            if (!session) return;
            if (window.initScriptChapter) window.initScriptChapter();
            if (window.EpubReadingSessions) window.EpubReadingSessions.start();
        });
    }
    if (window.EpubBrowserCacheBoundary) {
        window.EpubBrowserCacheBoundary.start(startChapterClients);
    }"""
            if self.deployment_mode == "server"
            else "if (window.initScriptChapter) window.initScriptChapter();"
        )
        chapter_html += f"""
    {cache_boundary_script}
    <script src="/assets/notification.js" defer></script>
    {auth_script}
    {server_locale_script}
    <script src="/assets/theme.js" defer></script>
    <script src="/assets/dialog.js" defer></script>
    <script src="/assets/version-check.js" defer></script>
    <script src="/assets/vendor/glightbox/glightbox.min.js" defer></script>
    <script src="/assets/lightbox-adapter.js" defer></script>
    <script src="/assets/vendor/web-highlighter/web-highlighter.min.js" defer></script>
    <script src="/assets/chapter-prefetch.js" defer></script>
    <script src="/assets/chapter-window.js" defer></script>
    <script src="/assets/viewport-anchor.js" defer></script>
    <script src="/assets/continuous-buffer.js" defer></script>
    <script src="/assets/reading-progress.js" defer></script>
    <script src="/assets/reader-layout.js" defer></script>
    {pdf_chapter_script}
    {book_search_script}
    <script src="/assets/chapter.js?v=18" defer></script>
    <script src="/assets/annotation-position.js" defer></script>
    <script src="/assets/annotation.js" defer></script>
    <script src="/assets/annotation-hub.js" defer></script>
    <script src="/assets/vendor/sortablejs/sortable.min.js" defer></script>
    {dictionary_assets}
    {render_vocabulary_assets(self.asset_manifest, include_dictionary=False) if self.deployment_mode == "server" else ""}
    <script src="/assets/bookshelf.js" defer></script>
    {reading_insights_assets}
    {reading_session_script}
    {ai_chapter_scripts}
    <script>
    document.addEventListener('DOMContentLoaded', function() {{
        {startup}
    }});
    </script>
</body>
</html>
"""
        chapter_html = rewrite_asset_urls(chapter_html, self.asset_manifest)
        chapter_html = self._inject_deployment_mode(chapter_html)
        chapter_html = rewrite_root_urls(chapter_html, self.urls)
        # The Kindle entry script sits in the plain-string head block of the
        # template, so it needs a placeholder substitution.
        chapter_html = chapter_html.replace("{kindle_entry_script}", kindle_entry_script)
        # kindle 支持，不能压缩 css 和 js
        # 部分 xhtml 书籍压缩之后会丢失标签，说明压缩算法可能存在问题
        # chapter_html = minify_html.minify(chapter_html, minify_css=False, minify_js=False)
        return chapter_html

    def _inject_deployment_mode(self, page_html):
        marker = '<script>window.EpubBrowserI18n.init();</script>'
        bootstrap = (
            '<script>window.EpubBrowserBasePath='
            + json.dumps(self.urls.base_path)
            + ';window.EpubBrowserMode='
            + json.dumps(self.deployment_mode)
            + '</script>'
            + marker
        )
        return page_html.replace(marker, bootstrap, 1)

    def get_metadata(self):
        """Return immutable metadata shared by SSG and Server publishers."""
        cover_path = None
        if self.cover_info and self.cover_info.get('web_path'):
            cover_path = self.cover_info['web_path']
        elif self.cover_info and self.cover_info.get('full_path'):
            cover_path = os.path.normpath(
                os.path.join(self.resources_base, self.cover_info['full_path'])
            )
        return BookMetadata(
            title=self.book_title,
            authors=tuple(self.authors or ()),
            tags=tuple(self.tags or ()),
            cover=cover_path,
            language=self.lang or 'en',
            epub_identifier=self.epub_identifier,
            source_format=self.source_format,
        )
