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
from .urls import SiteURLs, rewrite_root_urls
from .version import render_footer


@dataclass(frozen=True)
class LibraryBook:
    book_id: str
    title: str
    authors: Tuple[str, ...]
    tags: Tuple[str, ...]
    cover: Optional[str]


def _render_library_html(
    books: Sequence[LibraryBook],
    assets: PublishedAssets,
    urls: SiteURLs,
    deployment_mode: str,
) -> str:
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
    server_client_start = f"""
            if (window.initScriptLibrary) window.initScriptLibrary();
            {server_progress_start}"""
    if deployment_mode == "server":
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
        server_account_stylesheet = '<link rel="stylesheet" href="/assets/account.css">'
        server_account_control = '''<button type="button" class="library-meta-action app-nav-action" id="adminMenu" aria-haspopup="dialog" aria-controls="adminPanel" hidden>
                <i class="fas fa-user-shield" aria-hidden="true"></i><span data-i18n="admin.menu">Administration</span>
            </button>
            <button type="button" class="library-meta-action app-nav-action" id="accountMenu" aria-haspopup="dialog" aria-controls="accountPanel">
                <i class="fas fa-user" aria-hidden="true"></i><span id="accountMenuValue" data-i18n="account.menu">Account</span>
            </button>'''
        server_account_panel = '''
<div class="bookshelf-modal account-modal" id="accountPanel" role="dialog" aria-modal="true" aria-hidden="true" aria-labelledby="accountTitle">
    <div class="bookshelf-content account-content">
        <div class="bookshelf-header">
            <div class="bookshelf-header-left">
                <button type="button" class="bookshelf-action-btn account-danger-action" id="accountLogout"><i class="fas fa-sign-out-alt" aria-hidden="true"></i> <span data-i18n="account.logout">Sign out</span></button>
            </div>
            <h2 class="bookshelf-title" id="accountTitle" data-i18n="account.title">Account settings</h2>
            <div class="bookshelf-header-right">
                <button type="button" class="bookshelf-close-btn" id="accountClose" aria-label="Close account settings" data-i18n-aria-label="account.close"><i class="fas fa-times" aria-hidden="true"></i></button>
            </div>
        </div>
        <div class="account-modal-body"><div class="account-layout">
        <section class="account-card account-profile-card" aria-labelledby="accountProfileTitle">
            <h3 id="accountProfileTitle" data-i18n="account.profile">Profile</h3>
            <p id="accountIdentity"></p>
        </section>
        <div class="account-grid">
        <section class="account-card" aria-labelledby="accountPasswordTitle">
            <h3 id="accountPasswordTitle" data-i18n="account.changePassword">Change password</h3>
            <form class="account-form" id="accountPasswordForm">
                <label><span data-i18n="account.currentPassword">Current password</span><input type="password" name="current_password" autocomplete="current-password" required></label>
                <label><span data-i18n="account.newPassword">New password</span><input type="password" name="new_password" autocomplete="new-password" required></label>
                <button type="submit" class="bookshelf-action-btn account-primary-action" data-i18n="account.savePassword">Save password</button>
            </form>
        </section>
        <section class="account-card" aria-labelledby="accountSessionsTitle">
            <h3 id="accountSessionsTitle" data-i18n="account.sessions">Active sessions</h3>
            <ul class="account-list" id="sessionList"></ul>
        </section>
        <details class="account-card account-card-wide account-details" id="associationCard" hidden>
            <summary data-i18n="account.associationTitle">Associate a proxy identity</summary>
            <div class="account-details-body"><p data-i18n="account.associationDescription">If your trusted proxy identity is not recognized, prove which local account it belongs to.</p>
            <p class="account-section-copy" data-i18n="account.associationOidcHelp">EPUB Browser does not connect to OIDC directly. Open it through the configured OIDC-aware trusted proxy first; this form then links that external identity to an existing local account.</p>
            <form class="account-form" id="associationForm">
                <label><span data-i18n="account.username">Username</span><input type="text" name="username" autocomplete="username" required></label>
                <label><span data-i18n="account.password">Password</span><input type="password" name="password" autocomplete="current-password" required></label>
                <button type="submit" class="bookshelf-action-btn account-primary-action" data-i18n="account.associate">Associate identity</button>
            </form></div>
        </details>
        </div>
        </div></div>
    </div>
</div>
<div class="bookshelf-modal account-modal admin-modal" id="adminPanel" role="dialog" aria-modal="true" aria-hidden="true" aria-labelledby="adminTitle" hidden>
    <div class="bookshelf-content account-content">
        <div class="bookshelf-header">
            <div class="bookshelf-header-left"></div>
            <h2 class="bookshelf-title" id="adminTitle"><i class="fas fa-user-shield" aria-hidden="true"></i><span data-i18n="admin.title">Administration</span></h2>
            <div class="bookshelf-header-right">
                <button type="button" class="bookshelf-close-btn" id="adminClose" aria-label="Close administration" data-i18n-aria-label="admin.close"><i class="fas fa-times" aria-hidden="true"></i></button>
            </div>
        </div>
        <div class="account-modal-body"><div class="account-layout">
        <section class="account-admin account-admin-console" aria-labelledby="adminTitle">
            <p class="account-admin-intro" data-i18n="admin.description">Manage users, external identities, and access to restricted books.</p>
            <div class="account-admin-grid">
            <section class="account-admin-section account-card-wide account-users-section" aria-labelledby="adminUsersTitle">
                <h4 id="adminUsersTitle" data-i18n="admin.users">Users</h4>
                <p class="account-section-copy" data-i18n="admin.usersDescription">Create local accounts and manage their access, role, password, and sessions.</p>
                <form class="account-form account-create-user-form" id="adminUserForm">
                    <label><span data-i18n="account.username">Username</span><input type="text" name="username" autocomplete="off" required></label>
                    <label><span data-i18n="account.password">Password</span><input type="password" name="password" autocomplete="new-password" required></label>
                    <label><span data-i18n="admin.role">Role</span><select name="role"><option value="member" data-i18n="account.role.member">Member</option><option value="admin" data-i18n="account.role.admin">Administrator</option></select></label>
                    <button type="submit" class="bookshelf-action-btn account-primary-action" data-i18n="admin.createUser">Create user</button>
                </form>
                <ul class="account-list" id="adminUserList"></ul>
            </section>
            <section class="account-admin-section account-card-wide account-ai-section" aria-labelledby="adminAiTitle">
                <h4 id="adminAiTitle" data-i18n="admin.ai.title">AI reading</h4>
                <p class="account-section-copy" data-i18n="admin.ai.description">Configure one OpenAI-compatible model, member access, and cached results. Selected book text is sent to the configured provider.</p>
                <form class="account-form admin-ai-settings-form" id="adminAiSettingsForm">
                    <label class="admin-ai-enabled"><span data-i18n="admin.ai.enabled">Enable AI reading</span><input type="checkbox" name="enabled"></label>
                    <label><span data-i18n="admin.ai.baseUrl">Provider base URL</span><input type="url" name="base_url" autocomplete="off" placeholder="https://api.example/v1" required></label>
                    <label><span data-i18n="admin.ai.apiKey">API key</span><input type="password" name="api_key" autocomplete="new-password" data-i18n-placeholder="admin.ai.apiKeyPlaceholder" placeholder="Leave blank to keep the configured key"></label>
                    <label><span data-i18n="admin.ai.model">Model</span><input type="text" name="model" autocomplete="off" required></label>
                    <label><span data-i18n="admin.ai.timeout">Timeout (seconds)</span><input type="number" name="timeout_seconds" min="5" max="3600" required></label>
                    <label><span data-i18n="admin.ai.concurrency">Max concurrency</span><input type="number" name="max_concurrency" min="1" max="4" required></label>
                    <label><span data-i18n="admin.ai.dailyLimit">Default daily limit</span><input type="number" name="daily_limit" min="0" required></label>
                    <label class="admin-ai-clear-key"><input type="checkbox" name="clear_api_key"><span data-i18n="admin.ai.clearKey">Clear stored API key</span></label>
                    <button type="submit" class="bookshelf-action-btn account-primary-action" data-i18n="admin.ai.save">Save AI settings</button>
                </form>
                <p class="account-section-copy admin-ai-key-notice" data-i18n="admin.ai.keyNotice">The API key is stored in this server's SQLite database and is never returned to the browser.</p>
                <div class="admin-ai-subsection">
                    <h5 data-i18n="admin.ai.memberAccess">Member AI access</h5>
                    <ul class="account-list" id="adminAiUserList"></ul>
                </div>
                <div class="admin-ai-subsection admin-ai-cache-actions">
                    <h5 data-i18n="admin.ai.cache">AI result cache</h5>
                    <button type="button" class="bookshelf-action-btn account-danger-action" id="adminAiClearRevision" data-i18n="admin.ai.clearRevision">Clear results for this configuration</button>
                    <button type="button" class="bookshelf-action-btn account-danger-action" id="adminAiClearAll" data-i18n="admin.ai.clearAll">Clear all AI results</button>
                </div>
            </section>
            <section class="account-admin-section account-card-wide account-tags-section" aria-labelledby="adminTagsTitle">
                <h4 id="adminTagsTitle" data-i18n="admin.tags">Tag management</h4>
                <p class="account-section-copy" data-i18n="admin.tagsDescription">Create server-managed tags and assign them to books. They complement read-only EPUB tags.</p>
                <form class="account-form admin-ai-tag-form" id="adminAiTagForm">
                    <label><span data-i18n="admin.ai.tagName">Tag name</span><input type="text" name="name" maxlength="80" required></label>
                    <button type="submit" class="bookshelf-action-btn account-primary-action" data-i18n="admin.ai.addTag">Add tag</button>
                </form>
                <ul class="account-list" id="adminAiTagList"></ul>
            </section>
            <section class="account-admin-section account-card-wide" id="adminIdentitiesSection" aria-labelledby="adminIdentitiesTitle" hidden>
                <h4 id="adminIdentitiesTitle" data-i18n="admin.identities">Proxy identities</h4>
                <p class="account-section-copy" data-i18n="admin.identityHelp">For OIDC, let a trusted reverse proxy complete the protocol and pass a stable subject. Issuer must match --proxy-issuer; subject must match the configured subject header.</p>
                <form class="account-form" id="adminIdentityForm">
                    <label><span data-i18n="admin.identityIssuer">Issuer</span><input type="text" name="issuer" autocomplete="off" required></label>
                    <label><span data-i18n="admin.identitySubject">Subject</span><input type="text" name="subject" autocomplete="off" required></label>
                    <label><span data-i18n="admin.identityDisplayName">Display name</span><input type="text" name="display_name" autocomplete="off"></label>
                    <label><span data-i18n="admin.identityUser">Local user</span><select id="adminIdentityUser" name="user_id" required></select></label>
                    <button type="submit" class="bookshelf-action-btn account-primary-action" data-i18n="admin.createIdentity">Create identity</button>
                </form>
                <ul class="account-list" id="adminIdentityList"></ul>
            </section>
            <section class="account-admin-section account-card-wide" aria-labelledby="adminBooksTitle">
                <h4 id="adminBooksTitle" data-i18n="admin.books">Book management</h4>
                <p class="account-section-copy" data-i18n="admin.booksDescription">Manage visibility, member access, server tags, AI reading classification, and AI results for each book.</p>
                <ul class="account-list" id="adminBookList"></ul>
            </section>
            </div>
        </section>
        </div></div>
    </div>
</div>'''
        server_auth_script = '<script src="/assets/auth.js" defer></script>'
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
<link rel="stylesheet" href="/assets/fa.all.min.css">
<link rel="icon" type="image/png" href="/assets/favicon.png">
<link rel="apple-touch-icon" href="/assets/icon-192.png">
<link rel="stylesheet" href="/assets/theme.css">
<link rel="stylesheet" href="/assets/notification.css">
<link rel="stylesheet" href="/assets/dialog.css">
<link rel="stylesheet" href="/assets/library.css?v=13">
<link rel="stylesheet" href="/assets/breadcrumb.css?v=2">
<link rel="stylesheet" href="/assets/loading.css?v=15">
    <link rel="stylesheet" href="/assets/bookshelf.css">
    <link rel="stylesheet" href="/assets/annotation-hub.css">
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
        <a class="app-nav-brand" href="/" aria-label="EPUB Browser" data-i18n-aria-label="common.brand"><img class="app-nav-brand-mark" src="/assets/logo-mark-color.png" alt="" aria-hidden="true"><span data-i18n="common.brand">EPUB Browser</span></a>
        <div class="app-nav-links">
            <button type="button" class="app-nav-link" id="bookshelfBtn" aria-haspopup="dialog" aria-controls="bookshelfModal"><i class="fas fa-bookmark" aria-hidden="true"></i><span data-i18n="library.shelf">Shelf</span></button>
            <button type="button" class="app-nav-link" id="annotationsBtn" data-annotation-hub aria-haspopup="dialog"><i class="fas fa-highlighter" aria-hidden="true"></i><span data-i18n="library.annotations">Annotations</span></button>
            {install_control}
        </div>
        <div class="app-nav-actions">
            <div class="library-language app-nav-locale">
                <button type="button" class="app-nav-action app-nav-locale-toggle" id="localeToggle" aria-haspopup="menu" aria-expanded="false" aria-label="Language" data-i18n-aria-label="common.language"><i class="fas fa-globe" aria-hidden="true"></i><span class="sr-only" id="localeCurrentLabel">中文</span></button>
                <select class="sr-only" id="localeSelect" tabindex="-1" aria-hidden="true"><option value="zh-CN" data-i18n="common.chinese">中文</option><option value="en" data-i18n="common.english">English</option></select>
            </div>
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
{render_footer(datetime.now().year)}
"""
    library_html += """
    <script src="/assets/cache-boundary.js" defer></script>
    <script src="/assets/notification.js" defer></script>
{server_auth_script}
    <script src="/assets/theme.js" defer></script>
    <script src="/assets/dialog.js" defer></script>
    <script src="/assets/version-check.js" defer></script>
    <script src="/assets/pinyin-pro.min.js" defer></script>
    <script src="/assets/library.js?v=13" defer></script>
    <script src="/assets/sortable.min.js" defer></script>
    <script src="/assets/bookshelf.js" defer></script>
    <script src="/assets/annotation.js" defer></script>
    <script src="/assets/annotation-hub.js" defer></script>
{server_progress_script}
    <script>
    document.addEventListener('DOMContentLoaded', function() {
        var i18n = window.EpubBrowserI18n;
        var localeSelect = document.getElementById('localeSelect');
        var localeToggle = document.getElementById('localeToggle');
        var localeCurrentLabel = document.getElementById('localeCurrentLabel');
        if (i18n && localeSelect && localeToggle && localeCurrentLabel) {
            var localeMenu = document.createElement('div');
            localeMenu.className = 'theme-menu locale-menu';
            localeMenu.setAttribute('role', 'menu');
            localeMenu.setAttribute('aria-label', i18n.t('common.language'));
            localeMenu.style.display = 'none';
            localeMenu.style.position = 'fixed';
            localeMenu.style.zIndex = '10000';
            document.body.appendChild(localeMenu);

            function localeName(locale) {
                return i18n.t(locale === 'zh-CN' ? 'common.chinese' : 'common.english');
            }

            function positionLocaleMenu() {
                var rect = localeToggle.getBoundingClientRect();
                localeMenu.style.top = (rect.bottom + 8) + 'px';
                localeMenu.style.right = (window.innerWidth - rect.right) + 'px';
            }

            function closeLocaleMenu() {
                localeMenu.style.display = 'none';
                localeToggle.setAttribute('aria-expanded', 'false');
            }

            function renderLocaleMenu() {
                var current = i18n.getLocale();
                localeMenu.innerHTML = '';
                ['zh-CN', 'en'].forEach(function(locale) {
                    var item = document.createElement('button');
                    item.type = 'button';
                    item.className = 'theme-menu-item locale-menu-item';
                    item.setAttribute('role', 'menuitemradio');
                    item.setAttribute('aria-checked', locale === current ? 'true' : 'false');
                    var check = document.createElement('i');
                    check.className = locale === current ? 'fas fa-check' : 'fas fa-language';
                    check.setAttribute('aria-hidden', 'true');
                    item.appendChild(check);
                    item.appendChild(document.createTextNode(localeName(locale)));
                    item.addEventListener('click', function() {
                        localeSelect.value = locale;
                        i18n.setLocale(locale);
                        closeLocaleMenu();
                        localeToggle.focus();
                    });
                    localeMenu.appendChild(item);
                });
                localeCurrentLabel.textContent = localeName(current);
                localeMenu.setAttribute('aria-label', i18n.t('common.language'));
            }

            localeSelect.value = i18n.getLocale();
            localeSelect.addEventListener('change', function() {
                i18n.setLocale(localeSelect.value);
            });
            localeToggle.addEventListener('click', function(event) {
                event.stopPropagation();
                if (localeMenu.style.display === 'none') {
                    renderLocaleMenu();
                    positionLocaleMenu();
                    localeMenu.style.display = 'block';
                    localeToggle.setAttribute('aria-expanded', 'true');
                    var selected = localeMenu.querySelector('[aria-checked="true"]');
                    if (selected) selected.focus();
                } else {
                    closeLocaleMenu();
                }
            });
            document.addEventListener('click', function(event) {
                if (!localeToggle.contains(event.target) && !localeMenu.contains(event.target)) closeLocaleMenu();
            });
            document.addEventListener('keydown', function(event) {
                if (event.key === 'Escape' && localeMenu.style.display !== 'none') {
                    closeLocaleMenu();
                    localeToggle.focus();
                }
            });
            window.addEventListener('resize', function() {
                if (localeMenu.style.display !== 'none') positionLocaleMenu();
            });
            i18n.onLocaleChange(function() {
                localeSelect.value = i18n.getLocale();
                renderLocaleMenu();
            });
            renderLocaleMenu();
        }
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
    library_html = library_html.replace("{bookshelf_data_actions}", bookshelf_data_actions)
    library_html = library_html.replace("{server_account_panel}", server_account_panel)
    library_html = library_html.replace("{server_account_stylesheet}", server_account_stylesheet)
    library_html = library_html.replace("{server_auth_script}", server_auth_script)
    library_html = library_html.replace("{server_client_start}", server_client_start)
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
        }
        for book in ordered_books
    ]
    html = _render_library_html(ordered_books, assets, urls, deployment_mode)
    _atomic_write_text(root / "index.html", html)
    _atomic_write_text(
        root / "book-metadata.json",
        json.dumps(metadata, ensure_ascii=False, separators=(",", ":")),
    )
