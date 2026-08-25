"""Reusable Server-only navigation, account, and administration chrome."""

SERVER_ACCOUNT_STYLESHEET = '<link rel="stylesheet" href="/assets/account.css">'
SERVER_AUTH_SCRIPT = '<script src="/assets/auth.js" defer></script>'
SERVER_LOCALE_SCRIPT = '<script src="/assets/locale-nav.js" defer></script>'

SERVER_LOCALE_CONTROL = '''<div class="library-language app-nav-locale">
    <button type="button" class="app-nav-action app-nav-locale-toggle" id="localeToggle" aria-haspopup="menu" aria-expanded="false" aria-label="Language" data-i18n-aria-label="common.language"><i class="fas fa-globe" aria-hidden="true"></i><span class="sr-only" id="localeCurrentLabel" data-i18n="locale.name.en">English</span></button>
    <select class="sr-only" id="localeSelect" tabindex="-1" aria-hidden="true"><option value="en" data-i18n="locale.name.en">English</option><option value="zh-CN" data-i18n="locale.name.zh-CN">简体中文</option><option value="zh-TW" data-i18n="locale.name.zh-TW">繁體中文</option><option value="ko" data-i18n="locale.name.ko">한국어</option><option value="ja" data-i18n="locale.name.ja">日本語</option></select>
</div>'''

SERVER_ACCOUNT_CONTROL = '''<button type="button" class="library-meta-action app-nav-action" id="adminMenu" aria-haspopup="dialog" aria-controls="adminPanel" hidden>
        <i class="fas fa-user-shield" aria-hidden="true"></i><span data-i18n="admin.menu">Administration</span>
    </button>
    <button type="button" class="library-meta-action app-nav-action" id="accountMenu" aria-haspopup="dialog" aria-controls="accountPanel">
        <i class="fas fa-user" aria-hidden="true"></i><span id="accountMenuValue" data-i18n="account.menu">Account</span>
    </button>'''
SERVER_ACCOUNT_PANEL = '''
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
<div class="account-panel-loading" id="accountPanelLoading" role="status" aria-live="polite" aria-atomic="true" hidden>
    <span class="account-panel-loading-spinner" aria-hidden="true"></span>
    <span data-i18n="account.loading">Loading account settings…</span>
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
<div class="account-panel-loading" id="adminPanelLoading" role="status" aria-live="polite" aria-atomic="true" hidden>
    <span class="account-panel-loading-spinner" aria-hidden="true"></span>
    <span data-i18n="admin.loading">Loading administration…</span>
</div>
<div class="account-modal-body"><div class="account-layout">
<section class="account-admin account-admin-console" aria-labelledby="adminTitle">
    <p class="account-admin-intro" data-i18n="admin.description">Manage users and access to restricted books.</p>
    <nav class="admin-section-nav" id="adminSectionNav" role="tablist" aria-label="Administration sections" data-i18n-aria-label="admin.sectionNavigation">
        <button type="button" class="admin-section-tab is-active" id="adminSectionOverviewTab" role="tab" aria-selected="true" aria-controls="adminOverviewSection" data-admin-section="overview" data-i18n="admin.overview">Overview</button>
        <button type="button" class="admin-section-tab" id="adminSectionUsersTab" role="tab" aria-selected="false" aria-controls="adminUsersSection" data-admin-section="users" data-i18n="admin.users">Users</button>
        <button type="button" class="admin-section-tab" id="adminSectionAiConfigurationTab" role="tab" aria-selected="false" aria-controls="adminAiConfigurationSection" data-admin-section="ai-configuration" data-i18n="admin.ai.configuration">AI configuration</button>
        <button type="button" class="admin-section-tab" id="adminSectionAiPermissionsTab" role="tab" aria-selected="false" aria-controls="adminAiPermissionsSection" data-admin-section="ai-permissions" data-i18n="admin.ai.permissions">AI permissions</button>
        <button type="button" class="admin-section-tab" id="adminSectionAiJobsTab" role="tab" aria-selected="false" aria-controls="adminAiJobsSection" data-admin-section="ai-jobs" data-i18n="admin.ai.jobs.title">AI jobs</button>
        <button type="button" class="admin-section-tab" id="adminSectionTagsTab" role="tab" aria-selected="false" aria-controls="adminTagsSection" data-admin-section="tags" data-i18n="admin.tags">Tag management</button>
        <button type="button" class="admin-section-tab" id="adminSectionBooksTab" role="tab" aria-selected="false" aria-controls="adminBooksSection" data-admin-section="books" data-i18n="admin.books">Book management</button>
    </nav>
    <div class="account-admin-grid">
    <section class="account-admin-section account-card-wide admin-overview-section" id="adminOverviewSection" role="tabpanel" aria-labelledby="adminSectionOverviewTab" data-admin-panel="overview">
        <h4 data-i18n="admin.overview">Overview</h4>
        <p class="account-section-copy" data-i18n="admin.overviewDescription">Review the state of your library and jump straight to the area that needs attention.</p>
        <div class="admin-overview-grid">
            <button type="button" class="admin-overview-stat" data-admin-section="users"><span data-i18n="admin.overview.users">Users</span><strong id="adminOverviewUsers">—</strong></button>
            <button type="button" class="admin-overview-stat" data-admin-section="ai-configuration"><span data-i18n="admin.overview.ai">AI reading</span><strong id="adminOverviewAi">—</strong></button>
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
    <section class="account-admin-section account-card-wide account-ai-section admin-ai-configuration-panel" id="adminAiConfigurationSection" role="tabpanel" aria-labelledby="adminSectionAiConfigurationTab" data-admin-panel="ai-configuration" hidden>
            <h4 id="adminAiConfigurationTitle" data-i18n="admin.ai.configuration">AI configuration</h4>
            <p class="account-section-copy" data-i18n="admin.ai.description">Configure one OpenAI-compatible model, member access, and cached results. Selected book text is sent to the configured provider.</p>
            <form class="account-form admin-ai-settings-form" id="adminAiSettingsForm">
            <fieldset class="admin-ai-settings-group admin-ai-connection-group">
                <legend data-i18n="admin.ai.connection">Connection and model</legend>
                <label class="admin-ai-enabled"><span data-i18n="admin.ai.enabled">Enable AI reading</span><input type="checkbox" name="enabled"></label>
                <p class="admin-ai-connection-status" id="adminAiConnectionStatus" role="status"></p>
                <label><span data-i18n="admin.ai.baseUrl">Provider base URL</span><input type="url" name="base_url" autocomplete="off" placeholder="https://api.example/v1" required></label><!-- i18n-allow-literal: URL/protocol value -->
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
                <label><span class="admin-ai-field-label"><span data-i18n="admin.ai.dailyLimit">Default daily AI reading task limit</span><button type="button" class="admin-ai-help" data-i18n-data-tip="admin.ai.dailyLimitHelp" data-i18n-aria-label="admin.ai.dailyLimitHelpLabel" data-tip="The default number of AI reading tasks each authorized member may start per day. One chapter reading task may use several backend model calls. Set 0 for no daily limit. Per-member overrides take precedence." aria-label="Explain default daily AI reading task limit"><i class="fas fa-info" aria-hidden="true"></i></button></span><input type="number" name="daily_limit" min="0" required></label>
            </fieldset>
            <fieldset class="admin-ai-settings-group admin-ai-credential-group">
                <legend data-i18n="admin.ai.credentials">Credentials</legend>
                <label class="admin-ai-clear-key"><input type="checkbox" name="clear_api_key"><span data-i18n="admin.ai.clearKey">Clear stored API key</span></label>
            </fieldset>
            <button type="submit" class="bookshelf-action-btn account-primary-action" id="adminAiSettingsSubmit" data-i18n="admin.ai.save">Save AI settings</button>
            </form>
            <p class="account-section-copy admin-ai-key-notice" data-i18n="admin.ai.keyNotice">The API key is stored in this server's SQLite database and is never returned to the browser.</p>
            <div class="admin-ai-cache-actions">
                <h6 data-i18n="admin.ai.cache">AI result cache</h6>
                <button type="button" class="bookshelf-action-btn account-danger-action" id="adminAiClearRevision" data-i18n="admin.ai.clearRevision">Clear results for this configuration</button>
                <button type="button" class="bookshelf-action-btn account-danger-action" id="adminAiClearAll" data-i18n="admin.ai.clearAll">Clear all AI results</button>
            </div>
    </section>
    <section class="account-admin-section account-card-wide account-ai-section admin-ai-permissions-panel" id="adminAiPermissionsSection" role="tabpanel" aria-labelledby="adminSectionAiPermissionsTab" data-admin-panel="ai-permissions" hidden>
            <h4 id="adminAiPermissionsTitle" data-i18n="admin.ai.permissions">AI permissions</h4>
            <ul class="account-list" id="adminAiUserList"></ul>
    </section>
    <section class="account-admin-section account-card-wide account-ai-section admin-ai-jobs" id="adminAiJobsSection" role="tabpanel" aria-labelledby="adminSectionAiJobsTab" data-admin-panel="ai-jobs" hidden>
            <h4 id="adminAiJobsTitle" data-i18n="admin.ai.jobs.title">AI jobs</h4>
            <p class="account-section-copy" data-i18n="admin.ai.jobs.description">Review shared AI reading jobs and retry eligible failures.</p>
            <div class="account-form admin-ai-jobs-controls">
                <label for="adminAiJobsStatus"><span data-i18n="admin.ai.jobs.statusFilter">Status</span><select id="adminAiJobsStatus"><option value="" data-i18n="admin.ai.jobs.status.all">All</option><option value="queued" data-i18n="admin.ai.jobs.status.queued">Queued</option><option value="running" data-i18n="admin.ai.jobs.status.running">Running</option><option value="complete" data-i18n="admin.ai.jobs.status.complete">Complete</option><option value="failed" data-i18n="admin.ai.jobs.status.failed">Failed</option><option value="interrupted" data-i18n="admin.ai.jobs.status.interrupted">Interrupted</option></select></label>
                <label for="adminAiJobsPageSize"><span data-i18n="admin.ai.jobs.pageSize">Jobs per page</span><select id="adminAiJobsPageSize"><option value="10">10</option><option value="20" selected>20</option><option value="50">50</option><option value="100">100</option></select></label>
                <button type="button" class="bookshelf-action-btn" id="adminAiJobsRefresh" data-i18n="admin.ai.jobs.refresh">Refresh</button>
            </div>
            <div class="account-table-scroll admin-ai-jobs-table-scroll">
                <table class="account-admin-table admin-ai-jobs-table">
                    <caption class="sr-only visually-hidden" data-i18n="admin.ai.jobs.tableLabel">AI reading jobs</caption>
                    <thead><tr><th scope="col" data-i18n="admin.ai.jobs.header.status">Status</th><th scope="col" data-i18n="admin.ai.jobs.header.job">Job</th><th scope="col" data-i18n="admin.ai.jobs.header.book">Book</th><th scope="col" data-i18n="admin.ai.jobs.header.progress">Progress</th><th scope="col" data-i18n="admin.ai.jobs.header.timeline">Timeline</th><th scope="col" data-i18n="admin.ai.jobs.header.action">Action</th></tr></thead>
                    <tbody id="adminAiJobsBody"><tr><td colspan="6" data-i18n="admin.ai.jobs.loading">Loading AI jobs…</td></tr></tbody>
                </table>
            </div>
            <nav id="adminAiJobsPagination" aria-label="AI job pages" data-i18n-aria-label="admin.ai.jobs.paginationLabel"></nav>
            <p id="adminAiJobsLive" class="sr-only visually-hidden" aria-live="polite" aria-atomic="true"></p>
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
