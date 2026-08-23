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
    ai_reading_script = ""
    server_client_start = f"""
            if (window.initScriptLibrary) window.initScriptLibrary();
            {server_progress_start}"""
    if deployment_mode == "server":
        ai_reading_stylesheet = '<link rel="stylesheet" href="/assets/ai-reading-hub.css">'
        ai_reading_navigation = '''<button type="button" class="app-nav-link" data-ai-reading-hub aria-haspopup="dialog"><i class="fas fa-wand-magic-sparkles" aria-hidden="true"></i><span data-i18n="ai.library">AI readings</span></button>'''
        ai_reading_script = '<script src="/assets/ai-reading-hub.js" defer></script>'
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
            <p class="account-admin-intro" data-i18n="admin.description">Manage users and access to restricted books.</p>
            <nav class="admin-section-nav" id="adminSectionNav" role="tablist" aria-label="Administration sections" data-i18n-aria-label="admin.sectionNavigation">
                <button type="button" class="admin-section-tab is-active" id="adminSectionOverviewTab" role="tab" aria-selected="true" aria-controls="adminOverviewSection" data-admin-section="overview" data-i18n="admin.overview">Overview</button>
                <button type="button" class="admin-section-tab" id="adminSectionUsersTab" role="tab" aria-selected="false" aria-controls="adminUsersSection" data-admin-section="users" data-i18n="admin.users">Users</button>
                <button type="button" class="admin-section-tab" id="adminSectionAiTab" role="tab" aria-selected="false" aria-controls="adminAiSection" data-admin-section="ai" data-i18n="admin.ai.title">AI reading</button>
                <button type="button" class="admin-section-tab" id="adminSectionTagsTab" role="tab" aria-selected="false" aria-controls="adminTagsSection" data-admin-section="tags" data-i18n="admin.tags">Tag management</button>
                <button type="button" class="admin-section-tab" id="adminSectionBooksTab" role="tab" aria-selected="false" aria-controls="adminBooksSection" data-admin-section="books" data-i18n="admin.books">Book management</button>
            </nav>
            <div class="account-admin-grid">
            <section class="account-admin-section account-card-wide admin-overview-section" id="adminOverviewSection" role="tabpanel" aria-labelledby="adminSectionOverviewTab" data-admin-panel="overview">
                <h4 data-i18n="admin.overview">Overview</h4>
                <p class="account-section-copy" data-i18n="admin.overviewDescription">Review the state of your library and jump straight to the area that needs attention.</p>
                <div class="admin-overview-grid">
                    <button type="button" class="admin-overview-stat" data-admin-section="users"><span data-i18n="admin.overview.users">Users</span><strong id="adminOverviewUsers">—</strong></button>
                    <button type="button" class="admin-overview-stat" data-admin-section="ai"><span data-i18n="admin.overview.ai">AI reading</span><strong id="adminOverviewAi">—</strong></button>
                    <button type="button" class="admin-overview-stat" data-admin-section="tags"><span data-i18n="admin.overview.tags">Server tags</span><strong id="adminOverviewTags">—</strong></button>
                    <button type="button" class="admin-overview-stat" data-admin-section="books"><span data-i18n="admin.overview.books">Books</span><strong id="adminOverviewBooks">—</strong></button>
                </div>
                <p id="adminOverviewLive" class="sr-only visually-hidden" aria-live="polite" aria-atomic="true"></p>
            </section>
            <section class="account-admin-section account-card-wide account-users-section" id="adminUsersSection" role="tabpanel" aria-labelledby="adminSectionUsersTab" data-admin-panel="users" hidden>
                <h4 id="adminUsersTitle" data-i18n="admin.users">Users</h4>
                <p class="account-section-copy" data-i18n="admin.usersDescription">Create local accounts and manage their access, role, password, and sessions.</p>
                <form class="account-form account-create-user-form" id="adminUserForm">
                    <label><span data-i18n="account.username">Username</span><input type="text" name="username" autocomplete="off" required></label>
                    <label><span data-i18n="account.password">Password</span><input type="password" name="password" autocomplete="new-password" required></label>
                    <label><span data-i18n="admin.role">Role</span><select name="role"><option value="member" data-i18n="account.role.member">Member</option><option value="admin" data-i18n="account.role.admin">Administrator</option></select></label>
                    <button type="submit" class="bookshelf-action-btn account-primary-action" id="adminUserSubmit" data-i18n="admin.createUser">Create user</button>
                </form>
                <ul class="account-list" id="adminUserList"></ul>
            </section>
            <section class="account-admin-section account-card-wide account-ai-section" id="adminAiSection" role="tabpanel" aria-labelledby="adminSectionAiTab" data-admin-panel="ai" hidden>
                <h4 id="adminAiTitle" data-i18n="admin.ai.title">AI reading</h4>
                <p class="account-section-copy" data-i18n="admin.ai.description">Configure one OpenAI-compatible model, member access, and cached results. Selected book text is sent to the configured provider.</p>
                <form class="account-form admin-ai-settings-form" id="adminAiSettingsForm">
                    <fieldset class="admin-ai-settings-group admin-ai-connection-group">
                        <legend data-i18n="admin.ai.connection">Connection and model</legend>
                        <label class="admin-ai-enabled"><span data-i18n="admin.ai.enabled">Enable AI reading</span><input type="checkbox" name="enabled"></label>
                        <p class="admin-ai-connection-status" id="adminAiConnectionStatus" role="status"></p>
                        <label><span data-i18n="admin.ai.baseUrl">Provider base URL</span><input type="url" name="base_url" autocomplete="off" placeholder="https://api.example/v1" required></label>
                        <label><span data-i18n="admin.ai.apiKey">API key</span><input type="password" name="api_key" autocomplete="new-password" data-i18n-placeholder="admin.ai.apiKeyPlaceholder" placeholder="Leave blank to keep the configured key"></label>
                        <label><span data-i18n="admin.ai.model">Model</span><input type="text" name="model" autocomplete="off" required></label>
                    </fieldset>
                    <fieldset class="admin-ai-settings-group admin-ai-execution-group">
                        <legend data-i18n="admin.ai.execution">Execution and limits</legend>
                        <label><span data-i18n="admin.ai.timeout">Timeout (seconds)</span><input type="number" name="timeout_seconds" min="5" max="3600" required></label>
                        <label><span class="admin-ai-field-label"><span data-i18n="admin.ai.modelContextWindow">Model context window (tokens)</span><button type="button" class="admin-ai-help" data-i18n-data-tip="admin.ai.modelContextWindowHelp" data-i18n-aria-label="admin.ai.modelContextWindowHelpLabel" data-tip="The total input and output tokens the selected model supports in one request. EPUB Browser automatically reserves room for the answer and uses the remainder for source text and conversation history." aria-label="Explain model context window"><i class="fas fa-info" aria-hidden="true"></i></button></span><input type="number" name="model_context_window" min="2048" max="100000000" required></label>
                        <label><span class="admin-ai-field-label"><span data-i18n="admin.ai.concurrency">Max concurrency</span><button type="button" class="admin-ai-help" data-i18n-data-tip="admin.ai.concurrencyHelp" data-i18n-aria-label="admin.ai.concurrencyHelpLabel" data-tip="Maximum number of AI requests this server sends at the same time. A lower value is gentler on the provider; a higher value improves throughput but can hit provider limits." aria-label="Explain max concurrency"><i class="fas fa-info" aria-hidden="true"></i></button></span><input type="number" name="max_concurrency" min="1" max="4" required></label>
                    </fieldset>
                    <fieldset class="admin-ai-settings-group admin-ai-member-defaults-group">
                        <legend data-i18n="admin.ai.memberDefaults">Member defaults</legend>
                        <label><span class="admin-ai-field-label"><span data-i18n="admin.ai.dailyLimit">Default daily limit</span><button type="button" class="admin-ai-help" data-i18n-data-tip="admin.ai.dailyLimitHelp" data-i18n-aria-label="admin.ai.dailyLimitHelpLabel" data-tip="Default number of AI requests each authorized member may start per day. Set 0 for no daily limit. Per-member overrides take precedence." aria-label="Explain default daily limit"><i class="fas fa-info" aria-hidden="true"></i></button></span><input type="number" name="daily_limit" min="0" required></label>
                    </fieldset>
                    <fieldset class="admin-ai-settings-group admin-ai-credential-group">
                        <legend data-i18n="admin.ai.credentials">Credentials</legend>
                        <label class="admin-ai-clear-key"><input type="checkbox" name="clear_api_key"><span data-i18n="admin.ai.clearKey">Clear stored API key</span></label>
                    </fieldset>
                    <button type="submit" class="bookshelf-action-btn account-primary-action" id="adminAiSettingsSubmit" data-i18n="admin.ai.save">Save AI settings</button>
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
                <section class="admin-ai-subsection admin-ai-jobs" aria-labelledby="adminAiJobsTitle">
                    <h5 id="adminAiJobsTitle" data-i18n="admin.ai.jobs.title">AI jobs</h5>
                    <p class="account-section-copy" data-i18n="admin.ai.jobs.description">Review shared AI reading jobs and retry eligible failures.</p>
                    <div class="account-form admin-ai-jobs-controls">
                        <label for="adminAiJobsStatus"><span data-i18n="admin.ai.jobs.statusFilter">Status</span><select id="adminAiJobsStatus"><option value="" data-i18n="admin.ai.jobs.status.all">All</option><option value="queued" data-i18n="admin.ai.jobs.status.queued">Queued</option><option value="running" data-i18n="admin.ai.jobs.status.running">Running</option><option value="complete" data-i18n="admin.ai.jobs.status.complete">Complete</option><option value="failed" data-i18n="admin.ai.jobs.status.failed">Failed</option><option value="interrupted" data-i18n="admin.ai.jobs.status.interrupted">Interrupted</option></select></label>
                        <label for="adminAiJobsPageSize"><span data-i18n="admin.ai.jobs.pageSize">Jobs per page</span><select id="adminAiJobsPageSize"><option value="10">10</option><option value="20" selected>20</option><option value="50">50</option><option value="100">100</option></select></label>
                        <button type="button" class="bookshelf-action-btn" id="adminAiJobsRefresh" data-i18n="admin.ai.jobs.refresh">Refresh</button>
                    </div>
                    <div class="account-table-scroll admin-ai-jobs-table-scroll">
                        <table class="account-admin-table admin-ai-jobs-table">
                            <caption class="sr-only visually-hidden" data-i18n="admin.ai.jobs.tableLabel">AI reading jobs</caption>
                            <thead><tr><th scope="col" data-i18n="admin.ai.jobs.header.status">Status</th><th scope="col" data-i18n="admin.ai.jobs.header.job">Job</th><th scope="col" data-i18n="admin.ai.jobs.header.book">Book</th><th scope="col" data-i18n="admin.ai.jobs.header.requester">Requester</th><th scope="col" data-i18n="admin.ai.jobs.header.scope">Scope</th><th scope="col" data-i18n="admin.ai.jobs.header.progress">Progress</th><th scope="col" data-i18n="admin.ai.jobs.header.error">Error</th><th scope="col" data-i18n="admin.ai.jobs.header.created">Created</th><th scope="col" data-i18n="admin.ai.jobs.header.updated">Updated</th><th scope="col" data-i18n="admin.ai.jobs.header.action">Action</th></tr></thead>
                            <tbody id="adminAiJobsBody"><tr><td colspan="10" data-i18n="admin.ai.jobs.loading">Loading AI jobs…</td></tr></tbody>
                        </table>
                    </div>
                    <nav id="adminAiJobsPagination" aria-label="AI job pages" data-i18n-aria-label="admin.ai.jobs.paginationLabel"></nav>
                    <p id="adminAiJobsLive" class="sr-only visually-hidden" aria-live="polite" aria-atomic="true"></p>
                </section>
            </section>
            <section class="account-admin-section account-card-wide account-tags-section" id="adminTagsSection" role="tabpanel" aria-labelledby="adminSectionTagsTab" data-admin-panel="tags" hidden>
                <h4 id="adminTagsTitle" data-i18n="admin.tags">Tag management</h4>
                <p class="account-section-copy" data-i18n="admin.tagsDescription">Create server-managed tags and assign them to books. They complement read-only EPUB tags.</p>
                <form class="account-form admin-ai-tag-form" id="adminAiTagForm">
                    <label><span data-i18n="admin.ai.tagName">Tag name</span><input type="text" name="name" maxlength="80" required></label>
                    <button type="submit" class="bookshelf-action-btn account-primary-action" id="adminAiTagSubmit" data-i18n="admin.ai.addTag">Add tag</button>
                </form>
                <ul class="account-list" id="adminAiTagList"></ul>
            </section>
            <section class="account-admin-section account-card-wide" id="adminBooksSection" role="tabpanel" aria-labelledby="adminSectionBooksTab" data-admin-panel="books" hidden>
                <h4 id="adminBooksTitle" data-i18n="admin.books">Book management</h4>
                <p class="account-section-copy" data-i18n="admin.booksDescription">Manage visibility, member access, server tags, AI reading classification, and AI results for each book.</p>
                <div id="adminBookTableSurface" class="admin-books-workspace" hidden>
                    <div class="account-form admin-books-controls" role="search" aria-labelledby="adminBooksTitle">
                        <label class="admin-book-search-control" for="adminBookSearch"><span data-i18n="admin.books.searchLabel">Search books</span><input id="adminBookSearch" type="search" autocomplete="off" data-i18n-placeholder="admin.books.searchPlaceholder" placeholder="Search by title, author, or tag"></label>
                        <label class="admin-book-filter-control" for="adminBookVisibilityFilter"><span data-i18n="admin.books.visibilityFilter">Visibility</span><select id="adminBookVisibilityFilter"><option value="" data-i18n="admin.books.visibility.all">All visibility</option><option value="authenticated" data-i18n="admin.books.visibility.authenticated">All signed-in users</option><option value="restricted" data-i18n="admin.books.visibility.restricted">Restricted</option></select></label>
                        <label class="admin-book-filter-control" for="adminBookTagFilter"><span data-i18n="admin.books.tagFilter">Server tag</span><select id="adminBookTagFilter"><option value="" data-i18n="admin.books.tag.all">All server tags</option></select></label>
                        <label class="admin-book-sort-control" for="adminBookSort"><span data-i18n="admin.books.sortLabel">Sort by</span><select id="adminBookSort"><option value="title_asc" data-i18n="admin.books.sort.titleAsc">Title (A–Z)</option><option value="title_desc" data-i18n="admin.books.sort.titleDesc">Title (Z–A)</option><option value="created_desc" data-i18n="admin.books.sort.createdDesc">Recently added</option><option value="updated_desc" data-i18n="admin.books.sort.updatedDesc">Recently updated</option></select></label>
                        <label class="admin-book-page-size-control" for="adminBookPageSize"><span data-i18n="admin.books.pageSize">Books per page</span><select id="adminBookPageSize"><option value="10">10</option><option value="20" selected>20</option><option value="50">50</option><option value="100">100</option></select></label>
                        <button type="button" class="bookshelf-action-btn account-inline-action admin-book-clear-filters" id="adminBookClearFilters" data-i18n="admin.books.clearFilters">Clear filters</button>
                        <button type="button" class="bookshelf-action-btn account-inline-action admin-book-refresh" id="adminBookRefresh" data-i18n="admin.books.refresh">Refresh</button>
                    </div>
                    <section class="admin-book-bulk-actions" id="adminBookBulkActions" aria-labelledby="adminBookBulkTitle" hidden>
                        <div class="admin-book-bulk-summary"><h5 id="adminBookBulkTitle" data-i18n="admin.books.bulk.title">Bulk actions</h5><p id="adminBookSelectionCount" aria-live="polite" aria-atomic="true"></p><button type="button" class="bookshelf-action-btn account-inline-action" id="adminBookClearSelection" data-i18n="admin.books.bulk.clearSelection">Clear selection</button></div>
                        <div class="admin-book-bulk-controls">
                            <button type="button" class="bookshelf-action-btn account-danger-action" id="adminBookBulkRestrict" data-i18n="admin.books.bulk.restrict">Set selected to restricted</button>
                            <fieldset class="admin-book-bulk-members" id="adminBookBulkGrantFieldset"><legend data-i18n="admin.books.bulk.grantMembers">Grant members access</legend><p class="account-section-copy" data-i18n="admin.books.bulk.grantHelp">Adds access without removing existing grants.</p><div id="adminBookBulkMembers" class="account-book-grant-options"></div></fieldset>
                            <button type="button" class="bookshelf-action-btn account-primary-action" id="adminBookBulkGrant" data-i18n="admin.books.bulk.grant">Grant access</button>
                        </div>
                    </section>
                    <div class="account-table-scroll admin-books-table-scroll">
                        <table class="account-admin-table">
                            <caption class="sr-only visually-hidden" data-i18n="admin.books.tableLabel">Books</caption>
                            <thead><tr><th scope="col" class="admin-book-select-column"><input type="checkbox" id="adminBookSelectPage" data-i18n-aria-label="admin.books.bulk.selectPage" aria-label="Select visible books"></th><th scope="col" data-i18n="admin.books.header.book">Book</th><th scope="col" data-i18n="admin.books.header.access">Visibility and access</th><th scope="col" data-i18n="admin.books.header.profile">AI profile and tags</th><th scope="col" data-i18n="admin.books.header.results">AI results</th><th scope="col" data-i18n="admin.books.header.updated">Updated</th><th scope="col" data-i18n="admin.books.header.action">Actions</th></tr></thead>
                            <tbody id="adminBookList"><tr><td colspan="7" data-i18n="admin.books.loading">Loading books…</td></tr></tbody>
                        </table>
                    </div>
                    <nav id="adminBookPagination" aria-label="Book pages" data-i18n-aria-label="admin.books.paginationLabel"></nav>
                    <p id="adminBookLive" class="sr-only visually-hidden" aria-live="polite" aria-atomic="true"></p>
                </div>
                <ul class="account-list" id="adminBookLegacyList"></ul>
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
        <a class="app-nav-brand" href="/" aria-label="EPUB Browser" data-i18n-aria-label="common.brand"><img class="app-nav-brand-mark" src="/assets/logo-mark-color.png" alt="" aria-hidden="true"><span data-i18n="common.brand">EPUB Browser</span></a>
        <div class="app-nav-links">
            <button type="button" class="app-nav-link" id="bookshelfBtn" aria-haspopup="dialog" aria-controls="bookshelfModal"><i class="fas fa-bookmark" aria-hidden="true"></i><span data-i18n="library.shelf">Shelf</span></button>
            <button type="button" class="app-nav-link" id="annotationsBtn" data-annotation-hub aria-haspopup="dialog"><i class="fas fa-highlighter" aria-hidden="true"></i><span data-i18n="library.annotations">Annotations</span></button>
            {ai_reading_navigation}
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
{ai_reading_script}
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
    library_html = library_html.replace("{ai_reading_stylesheet}", ai_reading_stylesheet)
    library_html = library_html.replace("{ai_reading_navigation}", ai_reading_navigation)
    library_html = library_html.replace("{ai_reading_script}", ai_reading_script)
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
    html = render_library_shell(ordered_books, assets, urls, deployment_mode)
    _atomic_write_text(root / "index.html", html)
    _atomic_write_text(
        root / "book-metadata.json",
        json.dumps(metadata, ensure_ascii=False, separators=(",", ":")),
    )
