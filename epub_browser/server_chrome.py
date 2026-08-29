"""Reusable Server-only navigation, account, and administration chrome."""

from datetime import datetime

from .asset_publisher import PublishedAssets
from .locales import LOCALE_NATIVE_NAMES
from .urls import SiteURLs
from .version import render_footer

SERVER_ACCOUNT_STYLESHEET = '<link rel="stylesheet" href="/assets/account.css">'
SERVER_AUTH_SCRIPT = '<script src="/assets/auth.js" defer></script>'
SERVER_LOCALE_SCRIPT = '<script src="/assets/locale-nav.js" defer></script>'

_SERVER_LOCALE_OPTIONS = ''.join(
    '<option value="{code}" data-i18n="locale.name.{code}">{name}</option>'.format(
        code=code,
        name=name,
    )
    for code, name in LOCALE_NATIVE_NAMES.items()
)

SERVER_LOCALE_CONTROL = '''<div class="library-language app-nav-locale">
    <button type="button" class="app-nav-action app-nav-locale-toggle" id="localeToggle" aria-haspopup="menu" aria-expanded="false" aria-label="Language" data-i18n-aria-label="common.language"><i class="fas fa-globe" aria-hidden="true"></i><span class="sr-only" id="localeCurrentLabel" data-i18n="locale.name.en">English</span></button>
    <select class="sr-only" id="localeSelect" tabindex="-1" aria-hidden="true">{}</select>
</div>'''.format(_SERVER_LOCALE_OPTIONS)

SERVER_ACCOUNT_CONTROL = '''<button type="button" class="library-meta-action app-nav-action" id="adminMenu" aria-haspopup="dialog" aria-controls="adminPanel" aria-label="Administration" data-i18n-aria-label="admin.menu" hidden>
        <i class="fas fa-user-shield" aria-hidden="true"></i><span data-i18n="admin.menu">Administration</span>
    </button>
    <button type="button" class="library-meta-action app-nav-action" id="accountMenu" aria-haspopup="dialog" aria-controls="accountPanel" aria-label="Account" data-i18n-aria-label="account.menu">
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
<section class="account-card account-card-wide account-oidc-card" id="accountOidcCard" aria-labelledby="accountOidcTitle" hidden>
    <div class="account-section-heading">
        <div><h3 id="accountOidcTitle" data-i18n="account.oidc.title">Connected identity</h3><p class="account-help" data-i18n="account.oidc.description">Connect your account to the configured sign-in provider.</p></div>
    </div>
    <div class="account-oidc-summary">
        <ul class="account-list account-oidc-list" id="accountOidcList"></ul>
        <div class="account-oidc-actions">
            <button type="button" id="accountOidcLink" class="bookshelf-action-btn account-primary-action" data-i18n="account.oidc.link">Connect identity</button>
            <button type="button" id="accountOidcUnlink" class="bookshelf-action-btn account-danger-action" data-i18n="account.oidc.unlink" hidden>Disconnect identity</button>
        </div>
    </div>
    <p id="accountOidcLive" class="account-form-message" role="status" aria-live="polite" aria-atomic="true"></p>
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
<section class="account-card account-card-wide account-pat-card" aria-labelledby="accountPatTitle">
    <div class="account-section-heading">
        <div><h3 id="accountPatTitle" data-i18n="account.pats.title">Personal access tokens</h3><p class="account-help" data-i18n="account.pats.description">Use scoped tokens with the external API.</p></div>
        <a class="account-docs-link" href="/api-docs" target="_blank" rel="noopener"><i class="fas fa-code" aria-hidden="true"></i><span data-i18n="account.pats.docs">Open API docs</span></a>
    </div>
    <form class="account-form account-pat-form" id="patCreateForm">
        <div class="account-pat-form-grid">
            <label><span data-i18n="account.pats.name">Token name</span><input type="text" name="name" maxlength="80" autocomplete="off" required></label>
            <label><span data-i18n="account.currentPassword">Current password</span><input type="password" name="current_password" autocomplete="current-password" required></label>
            <label><span data-i18n="account.pats.expiration">Expiration</span><select name="expires_in_days" aria-describedby="patExpirationHelp"><option value="30" data-i18n="account.pats.days30">30 days</option><option value="90" selected data-i18n="account.pats.days90">90 days</option><option value="180" data-i18n="account.pats.days180">180 days</option><option value="365" data-i18n="account.pats.days365">365 days</option><option value="never" data-i18n="account.pats.never">Never expires</option></select></label>
        </div>
        <fieldset class="account-pat-scopes">
            <legend data-i18n="account.pats.scopes">Permissions</legend>
            <div class="account-pat-scope-group"><strong data-i18n="account.pats.group.library">Library</strong><label><input type="checkbox" name="scopes" value="library:read"> <span data-i18n="account.pats.scope.libraryRead">Read library and chapters</span></label></div>
            <div class="account-pat-scope-group"><strong data-i18n="account.pats.group.bookshelf">Bookshelf</strong><label><input type="checkbox" name="scopes" value="bookshelf:read"> <span data-i18n="account.pats.scope.bookshelfRead">Read bookshelf</span></label><label><input type="checkbox" name="scopes" value="bookshelf:write"> <span data-i18n="account.pats.scope.bookshelfWrite">Update bookshelf</span></label></div>
            <div class="account-pat-scope-group"><strong data-i18n="account.pats.group.progress">Progress</strong><label><input type="checkbox" name="scopes" value="progress:read"> <span data-i18n="account.pats.scope.progressRead">Read progress</span></label><label><input type="checkbox" name="scopes" value="progress:write"> <span data-i18n="account.pats.scope.progressWrite">Update progress</span></label></div>
            <div class="account-pat-scope-group"><strong data-i18n="account.pats.group.annotations">Annotations</strong><label><input type="checkbox" name="scopes" value="annotations:read"> <span data-i18n="account.pats.scope.annotationsRead">Read annotations</span></label><label><input type="checkbox" name="scopes" value="annotations:write"> <span data-i18n="account.pats.scope.annotationsWrite">Update annotations</span></label></div>
            <div class="account-pat-scope-group"><strong data-i18n="account.pats.group.reviews">Reviews</strong><label><input type="checkbox" name="scopes" value="reviews:read"> <span data-i18n="account.pats.scope.reviewsRead">Read reviews</span></label><label><input type="checkbox" name="scopes" value="reviews:write"> <span data-i18n="account.pats.scope.reviewsWrite">Update reviews</span></label></div>
            <div class="account-pat-scope-group" id="patAdminScopeLabel" hidden><strong data-i18n="account.pats.group.administration">Administration</strong><label><input type="checkbox" name="scopes" value="admin:data:read"> <span data-i18n="account.pats.scope.adminDataRead">Read all users' non-secret data</span></label></div>
        </fieldset>
        <div class="account-pat-form-footer"><p class="account-pat-warning" id="patExpirationHelp" data-i18n="account.pats.neverExpiresWarning">Never-expiring tokens remain valid until you revoke them.</p><button type="submit" id="patCreateSubmit" class="bookshelf-action-btn account-primary-action" data-i18n="account.pats.create">Create token</button></div>
    </form>
    <div class="account-pat-secret" id="patSecretRegion" role="status" aria-live="polite" hidden>
        <p data-i18n="account.pats.created">Copy this token now. It will not be shown again.</p>
        <code id="patCreatedSecret"></code>
        <button type="button" id="patCopySecret" class="bookshelf-action-btn" data-i18n="account.pats.copy">Copy token</button>
    </div>
    <div class="account-records-heading"><h4 data-i18n="account.pats.issued">Issued tokens</h4></div>
    <ul class="account-list account-pat-list" id="patList"></ul>
    <p id="patLive" class="sr-only visually-hidden" aria-live="polite" aria-atomic="true"></p>
</section>
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
<section class="account-admin account-admin-console" id="adminConsole" aria-labelledby="adminTitle">
    <p class="account-admin-intro" data-i18n="admin.description">Manage users and access to restricted books.</p>
    <nav class="admin-section-nav" id="adminSectionNav" role="tablist" aria-label="Administration sections" data-i18n-aria-label="admin.sectionNavigation">
        <button type="button" class="admin-section-tab is-active" id="adminSectionOverviewTab" role="tab" aria-selected="true" aria-controls="adminOverviewSection" data-admin-section="overview" data-i18n="admin.overview">Overview</button>
        <button type="button" class="admin-section-tab" id="adminSectionUsersTab" role="tab" aria-selected="false" aria-controls="adminUsersSection" data-admin-section="users" data-i18n="admin.users">Users</button>
        <button type="button" class="admin-section-tab" id="adminSectionOidcTab" role="tab" aria-selected="false" aria-controls="adminOidcSection" data-admin-section="oidc" data-i18n="admin.oidc.title">OIDC login</button>
        <button type="button" class="admin-section-tab" id="adminSectionDictionariesTab" role="tab" aria-selected="false" aria-controls="adminDictionariesSection" data-admin-section="dictionaries" data-i18n="admin.dictionaries">Dictionaries</button>
        <button type="button" class="admin-section-tab" id="adminSectionAiConfigurationTab" role="tab" aria-selected="false" aria-controls="adminAiConfigurationSection" data-admin-section="ai-configuration" data-i18n="admin.ai.configuration">AI configuration</button>
        <button type="button" class="admin-section-tab" id="adminSectionAiPermissionsTab" role="tab" aria-selected="false" aria-controls="adminAiPermissionsSection" data-admin-section="ai-permissions" data-i18n="admin.ai.permissions">AI permissions</button>
        <button type="button" class="admin-section-tab" id="adminSectionAiJobsTab" role="tab" aria-selected="false" aria-controls="adminAiJobsSection" data-admin-section="ai-jobs" data-i18n="admin.ai.jobs.title">AI jobs</button>
        <button type="button" class="admin-section-tab" id="adminSectionTagsTab" role="tab" aria-selected="false" aria-controls="adminTagsSection" data-admin-section="tags" data-i18n="admin.tags">Tag management</button>
        <button type="button" class="admin-section-tab" id="adminSectionBooksTab" role="tab" aria-selected="false" aria-controls="adminBooksSection" data-admin-section="books" data-i18n="admin.books">Book management</button>
        <button type="button" class="admin-section-tab" id="adminSectionWebhooksTab" role="tab" aria-selected="false" aria-controls="adminWebhooksSection" data-admin-section="webhooks" data-i18n="admin.webhooks.title">WebHooks</button>
    </nav>
    <div class="account-admin-grid">
    <section class="account-admin-section account-card-wide admin-overview-section" id="adminOverviewSection" role="tabpanel" aria-labelledby="adminSectionOverviewTab" data-admin-panel="overview">
        <h4 data-i18n="admin.overview">Overview</h4>
        <p class="account-section-copy" data-i18n="admin.overviewDescription">Review the state of your library and jump straight to the area that needs attention.</p>
        <div class="admin-overview-grid">
            <button type="button" class="admin-overview-stat" data-admin-section="users"><span data-i18n="admin.overview.users">Users</span><strong id="adminOverviewUsers">—</strong></button>
            <button type="button" class="admin-overview-stat" data-admin-section="ai-configuration"><span data-i18n="admin.overview.ai">AI reading</span><strong id="adminOverviewAi">—</strong></button>
            <button type="button" class="admin-overview-stat" data-admin-section="tags"><span data-i18n="admin.overview.tags">Tags</span><strong id="adminOverviewTags">—</strong></button>
            <button type="button" class="admin-overview-stat" data-admin-section="books"><span data-i18n="admin.overview.books">Books</span><strong id="adminOverviewBooks">—</strong></button>
        </div>
        <section class="admin-system-limits" id="adminSystemLimits" aria-labelledby="adminSystemLimitsTitle">
            <h5 id="adminSystemLimitsTitle" data-i18n="admin.systemLimits">Administrator operations</h5>
            <p data-i18n="admin.systemLimitsDescription">Dictionary imports, AI execution, and bulk book updates have no built-in capacity, count, or concurrency limit. Actual capacity depends on this server and your AI provider.</p>
        </section>
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
    <section class="account-admin-section account-card-wide admin-oidc-section" id="adminOidcSection" role="tabpanel" aria-labelledby="adminSectionOidcTab" data-admin-panel="oidc" hidden>
        <h4 data-i18n="admin.oidc.title">OIDC login</h4>
        <p class="account-section-copy" data-i18n="admin.oidc.description">Configure one standards-based OpenID Connect provider for Server sign-in and account linking.</p>
        <form class="account-form admin-oidc-form" id="adminOidcForm" novalidate>
            <fieldset class="admin-oidc-group">
                <legend data-i18n="admin.oidc.provider">Provider</legend>
                <label class="admin-oidc-check"><input type="checkbox" name="enabled"><span data-i18n="admin.oidc.enabled">Enable OIDC login</span></label>
                <label for="adminOidcProviderName"><span data-i18n="admin.oidc.providerName">Provider name</span><input id="adminOidcProviderName" name="provider_name" maxlength="80" autocomplete="off" required></label>
                <label for="adminOidcIssuerUrl"><span data-i18n="admin.oidc.issuerUrl">Issuer URL</span><input id="adminOidcIssuerUrl" name="issuer_url" type="url" inputmode="url" autocomplete="off" placeholder="https://auth.example.com" required></label><!-- i18n-allow-literal: URL/protocol value -->
                <label for="adminOidcClientId"><span data-i18n="admin.oidc.clientId">Client ID</span><input id="adminOidcClientId" name="client_id" autocomplete="off" required></label>
                <label for="adminOidcClientSecret"><span data-i18n="admin.oidc.clientSecret">Client secret</span><input id="adminOidcClientSecret" name="client_secret" type="password" autocomplete="new-password" data-i18n-placeholder="admin.oidc.secretPlaceholder" placeholder="Leave blank to keep the configured secret"></label>
                <label class="admin-oidc-check"><input type="checkbox" name="clear_client_secret"><span data-i18n="admin.oidc.clearSecret">Clear stored client secret</span></label>
            </fieldset>
            <fieldset class="admin-oidc-group">
                <legend data-i18n="admin.oidc.callback">Callback and claims</legend>
                <div class="admin-oidc-field"><label for="adminOidcRedirectUri"><span data-i18n="admin.oidc.redirectUri">Redirect URI</span><input id="adminOidcRedirectUri" name="redirect_uri" type="url" inputmode="url" autocomplete="off" required aria-describedby="adminOidcRedirectHelp"></label><p class="account-help" id="adminOidcRedirectHelp" data-i18n="admin.oidc.redirectHelp">Register this exact URI with the provider. Its path must be /auth/oidc/callback.</p><button type="button" class="bookshelf-action-btn account-inline-action" id="adminOidcUseSuggestion" data-i18n="admin.oidc.useSuggestion">Use suggested URI</button></div>
                <div class="admin-oidc-field"><label for="adminOidcScopes"><span data-i18n="admin.oidc.scopes">Scopes</span><input id="adminOidcScopes" name="scopes" autocomplete="off" value="openid profile email" required aria-describedby="adminOidcScopesHelp"></label><p class="account-help" id="adminOidcScopesHelp" data-i18n="admin.oidc.scopesHelp">Separate scopes with spaces. openid is required.</p></div>
                <label for="adminOidcUsernameClaim"><span data-i18n="admin.oidc.usernameClaim">Username claim</span><input id="adminOidcUsernameClaim" name="username_claim" autocomplete="off" value="preferred_username" required></label>
            </fieldset>
            <fieldset class="admin-oidc-group">
                <legend data-i18n="admin.oidc.provisioning">Account policy</legend>
                <label class="admin-oidc-check"><input type="checkbox" name="auto_create_users"><span><strong data-i18n="admin.oidc.autoCreate">Automatically create members</strong><small data-i18n="admin.oidc.autoCreateHelp">Unknown identities receive a member account. Administrator roles are never imported.</small></span></label>
                <label class="admin-oidc-check"><input type="checkbox" name="allow_member_password_login" checked><span><strong data-i18n="admin.oidc.allowMemberPassword">Allow local password login for members</strong><small data-i18n="admin.oidc.adminFallbackHelp">Local administrator password login always remains available.</small></span></label>
            </fieldset>
            <p id="adminOidcMessage" class="account-form-message" role="status" aria-live="polite" aria-atomic="true"></p>
            <button type="submit" class="bookshelf-action-btn account-primary-action" id="adminOidcSubmit" data-i18n="admin.oidc.save">Save OIDC settings</button>
        </form>
    </section>
    <section class="account-admin-section account-card-wide" id="adminDictionariesSection" role="tabpanel" aria-labelledby="adminSectionDictionariesTab" data-admin-panel="dictionaries" hidden>
        <h4 data-i18n="admin.dictionaries">Dictionaries</h4>
        <p class="account-section-copy" data-i18n="admin.dictionariesDescription">Install a local MDict or StarDict dictionary. You can choose it when looking up a word.</p>
        <form class="account-form dictionary-install-form" id="adminDictionaryForm">
            <fieldset class="dictionary-format-chooser"><legend data-i18n="admin.dictionaryFormat">Dictionary format</legend><label class="dictionary-format-option is-selected"><input name="dictionary_format" type="radio" value="mdict" checked><span><strong data-i18n="admin.dictionaryFormatMdictName">MDict</strong><small data-i18n="admin.dictionaryFormatMdict">Upload one ZIP containing the MDict and its local resources.</small></span></label><label class="dictionary-format-option"><input name="dictionary_format" type="radio" value="stardict"><span><strong data-i18n="admin.dictionaryFormatStardictName">StarDict</strong><small data-i18n="admin.dictionaryFormatStardict">Upload one downloaded archive containing the dictionary files.</small></span></label></fieldset>
            <div class="dictionary-upload-fields" data-dictionary-upload="mdict"><label><span data-i18n="admin.dictionaryMdictPackage">MDict package</span><span class="dictionary-file-control"><input class="dictionary-file-input" name="mdict_archive" type="file" accept=".zip,application/zip,application/octet-stream" required aria-describedby="adminDictionaryMdictPackageHelp"><span class="dictionary-file-button" aria-hidden="true" data-i18n="admin.chooseDictionaryFile">Choose file</span><span class="dictionary-file-name" data-dictionary-file-name="mdict_archive" data-i18n="admin.noDictionaryFile">No file selected</span></span><small id="adminDictionaryMdictPackageHelp" data-i18n="admin.dictionaryMdictPackageHelp">ZIP with one MDX and any matching MDD, CSS, image, or audio resources.</small></label></div>
            <div class="dictionary-upload-fields" data-dictionary-upload="stardict" hidden><label><span data-i18n="admin.dictionaryPackage">Dictionary package</span><span class="dictionary-file-control"><input class="dictionary-file-input" name="stardict_archive" type="file" accept=".zip,.tar.gz,.tgz,.tar.bz2,.tbz2,.gz,.bz2,application/zip,application/gzip,application/x-bzip2,application/octet-stream" disabled aria-describedby="adminDictionaryPackageHelp"><span class="dictionary-file-button" aria-hidden="true" data-i18n="admin.chooseDictionaryFile">Choose file</span><span class="dictionary-file-name" data-dictionary-file-name="stardict_archive" data-i18n="admin.noDictionaryFile">No file selected</span></span><small id="adminDictionaryPackageHelp" data-i18n="admin.dictionaryPackageHelp">Choose a ZIP, .tar.gz/.tgz, or .tar.bz2/.tbz2 download containing matching .ifo, .idx, and .dict files.</small></label></div>
            <label><span data-i18n="admin.dictionaryName">Display name (optional)</span><input name="display_name" type="text" autocomplete="off" aria-describedby="adminDictionaryNameHelp"><small id="adminDictionaryNameHelp" data-i18n="admin.dictionaryNameHelp">Pre-filled from the file name. You can change it.</small></label>
            <button type="submit" class="bookshelf-action-btn account-primary-action" id="adminDictionarySubmit" data-i18n="admin.installDictionary">Install dictionary</button>
            <p id="adminDictionaryMessage" class="auth-alert" role="alert" hidden></p>
        </form>
        <p id="adminDictionaryLive" class="sr-only visually-hidden" aria-live="polite" aria-atomic="true"></p>
        <ul class="account-list" id="adminDictionaryList"></ul>
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
                <label><span data-i18n="admin.ai.timeout">Timeout (seconds)</span><input type="number" name="timeout_seconds" required></label>
                <label><span class="admin-ai-field-label"><span data-i18n="admin.ai.modelContextWindow">Model context window (tokens)</span><button type="button" class="admin-ai-help" data-i18n-data-tip="admin.ai.modelContextWindowHelp" data-i18n-aria-label="admin.ai.modelContextWindowHelpLabel" data-tip="The total input and output tokens the selected model supports in one request. EPUB Browser automatically reserves room for the answer and uses the remainder for source text and conversation history." aria-label="Explain model context window"><i class="fas fa-info" aria-hidden="true"></i></button></span><input type="number" name="model_context_window" required></label>
                <label><span class="admin-ai-field-label"><span data-i18n="admin.ai.concurrency">Max concurrency</span><button type="button" class="admin-ai-help" data-i18n-data-tip="admin.ai.concurrencyHelp" data-i18n-aria-label="admin.ai.concurrencyHelpLabel" data-tip="Maximum number of AI requests this server sends at the same time. A lower value is gentler on the provider; a higher value improves throughput but can hit provider limits." aria-label="Explain max concurrency"><i class="fas fa-info" aria-hidden="true"></i></button></span><input type="number" name="max_concurrency" required></label>
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
        <p class="account-section-copy" data-i18n="admin.tagsDescription">Tags imported from books are managed here. Renaming or deleting a tag updates every assigned book.</p>
        <form class="account-form admin-ai-tag-form" id="adminAiTagForm">
            <label><span data-i18n="admin.ai.newTagName">New tag name</span><input type="text" name="name" maxlength="80" required></label>
            <button type="submit" class="bookshelf-action-btn account-primary-action" id="adminAiTagSubmit" data-i18n="admin.ai.addTag">Add tag</button>
        </form>
        <p id="adminAiTagMessage" class="auth-alert admin-ai-tag-message" role="alert" hidden></p>
        <p id="adminAiTagLive" class="sr-only visually-hidden" aria-live="polite" aria-atomic="true"></p>
        <label class="admin-ai-tag-search" id="adminAiTagSearchControl" for="adminAiTagSearch" hidden><span data-i18n="admin.ai.searchTags">Search tags</span><input id="adminAiTagSearch" type="search" autocomplete="off" data-i18n-placeholder="admin.ai.searchPlaceholder" placeholder="Search by tag name"></label>
        <ul class="account-list" id="adminAiTagList" aria-labelledby="adminTagsTitle"></ul>
    </section>
    <section class="account-admin-section account-card-wide admin-webhooks-section" id="adminWebhooksSection" role="tabpanel" aria-labelledby="adminSectionWebhooksTab" data-admin-panel="webhooks" hidden>
        <h4 data-i18n="admin.webhooks.title">WebHooks</h4>
        <p class="account-section-copy" data-i18n="admin.webhooks.description">Send signed event notifications to administrator-managed HTTP endpoints.</p>
        <div class="admin-webhook-workspace"><form class="account-form admin-webhook-form" id="adminWebhookForm">
            <label><span data-i18n="admin.webhooks.name">Name</span><input name="name" maxlength="80" required></label>
            <label><span data-i18n="admin.webhooks.url">Endpoint URL</span><input name="url" type="url" placeholder="https://example.com/webhook" data-i18n-placeholder="admin.webhooks.urlPlaceholder" autocomplete="off" required></label>
            <fieldset class="admin-webhook-events"><legend data-i18n="admin.webhooks.events">Events</legend>
                <div class="admin-webhook-event-group" role="group" aria-labelledby="adminWebhookReviewEvents"><strong id="adminWebhookReviewEvents" data-i18n="admin.webhooks.reviewEvents">Review activity</strong><div class="admin-webhook-event-options"><label><input type="checkbox" name="event_types" value="review.created"><span data-i18n="admin.webhooks.event.reviewCreated">Review created</span></label><label><input type="checkbox" name="event_types" value="review.updated"><span data-i18n="admin.webhooks.event.reviewUpdated">Review updated</span></label><label><input type="checkbox" name="event_types" value="review.deleted"><span data-i18n="admin.webhooks.event.reviewDeleted">Review deleted</span></label></div></div>
                <div class="admin-webhook-event-group" role="group" aria-labelledby="adminWebhookBookEvents"><strong id="adminWebhookBookEvents" data-i18n="admin.webhooks.bookEvents">Book lifecycle</strong><div class="admin-webhook-event-options"><label><input type="checkbox" name="event_types" value="book.created"><span data-i18n="admin.webhooks.event.bookCreated">Book created</span></label><label><input type="checkbox" name="event_types" value="book.updated"><span data-i18n="admin.webhooks.event.bookUpdated">Book updated</span></label><label><input type="checkbox" name="event_types" value="book.removed"><span data-i18n="admin.webhooks.event.bookRemoved">Book removed</span></label><label><input type="checkbox" name="event_types" value="book.conversion.succeeded"><span data-i18n="admin.webhooks.event.conversionSucceeded">Conversion succeeded</span></label><label><input type="checkbox" name="event_types" value="book.conversion.failed"><span data-i18n="admin.webhooks.event.conversionFailed">Conversion failed</span></label></div></div>
            </fieldset>
            <label class="admin-webhook-enabled"><input type="checkbox" name="enabled" checked><span data-i18n="admin.webhooks.enabled">Enabled</span></label>
            <div class="admin-webhook-form-actions"><button type="submit" id="adminWebhookSubmit" class="bookshelf-action-btn account-primary-action" data-i18n="admin.webhooks.create">Add endpoint</button><button type="button" id="adminWebhookCancelEdit" class="bookshelf-action-btn" data-i18n="admin.webhooks.cancelEdit" hidden>Cancel editing</button></div>
        </form>
        <section class="admin-webhook-registry" aria-labelledby="adminWebhookConfiguredTitle"><h5 id="adminWebhookConfiguredTitle" data-i18n="admin.webhooks.configured">Configured endpoints</h5><ul class="account-list admin-webhook-list" id="adminWebhookList"></ul></section></div>
        <div class="account-pat-secret" id="adminWebhookSecretRegion" role="status" aria-live="polite" hidden><p data-i18n="admin.webhooks.secretOnce">Copy the signing secret now. It will not be shown again.</p><code id="adminWebhookSecret"></code><button type="button" id="adminWebhookCopySecret" class="bookshelf-action-btn" data-i18n="admin.webhooks.copySecret">Copy secret</button></div>
        <section class="admin-webhook-history" aria-labelledby="adminWebhookDeliveriesTitle"><h5 id="adminWebhookDeliveriesTitle" data-i18n="admin.webhooks.deliveries">Recent deliveries</h5><ul class="account-list admin-webhook-deliveries" id="adminWebhookDeliveries"></ul></section>
        <p id="adminWebhookLive" class="sr-only visually-hidden" aria-live="polite" aria-atomic="true"></p>
    </section>
    <section class="account-admin-section account-card-wide" id="adminBooksSection" role="tabpanel" aria-labelledby="adminSectionBooksTab" data-admin-panel="books" hidden>
        <h4 id="adminBooksTitle" data-i18n="admin.books">Book management</h4>
        <p class="account-section-copy" data-i18n="admin.booksDescription">Manage book metadata, visibility, member access, tags, AI reading classification, and AI results.</p>
        <div id="adminBookTableSurface" class="admin-books-workspace" hidden>
            <div class="account-form admin-books-controls" role="search" aria-labelledby="adminBooksTitle">
                <label class="admin-book-search-control" for="adminBookSearch"><span data-i18n="admin.books.searchLabel">Search books</span><input id="adminBookSearch" type="search" autocomplete="off" data-i18n-placeholder="admin.books.searchPlaceholder" placeholder="Search by title, author, or tag"></label>
                <label class="admin-book-filter-control" for="adminBookVisibilityFilter"><span data-i18n="admin.books.visibilityFilter">Visibility</span><select id="adminBookVisibilityFilter"><option value="" data-i18n="admin.books.visibility.all">All visibility</option><option value="authenticated" data-i18n="admin.books.visibility.authenticated">All signed-in users</option><option value="restricted" data-i18n="admin.books.visibility.restricted">Restricted</option></select></label>
                <label class="admin-book-filter-control" for="adminBookTagFilter"><span data-i18n="admin.books.tagFilter">Tag</span><select id="adminBookTagFilter"><option value="" data-i18n="admin.books.tag.all">All tags</option></select></label>
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
    <div class="admin-book-editor-modal" id="adminBookEditorModal" role="dialog" aria-modal="true" aria-hidden="true" aria-labelledby="adminBookEditorModalTitle" hidden>
        <div class="admin-book-editor-dialog">
            <div class="admin-book-editor-modal-body" id="adminBookEditorContent"></div>
            <button type="button" class="admin-book-editor-close" id="adminBookEditorClose" aria-label="Close book settings" data-i18n-aria-label="admin.books.closeEditor"><i class="fas fa-times" aria-hidden="true"></i></button>
        </div>
    </div>
</div>'''


def render_reading_insights_document(assets: PublishedAssets, urls: SiteURLs) -> str:
    """Render the private reading-insights shell without embedding user data."""
    insights_css = assets.url_for('reading-insights.css')
    insights_script = assets.url_for('reading-insights.js')
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="theme-color" content="#244548">
<meta name="description" content="Private reading insights" data-i18n-content="readingInsights.description">
<title data-i18n="readingInsights.pageTitle">Reading insights · EPUB Browser</title>
<script src="/assets/i18n.js"></script>
<script>window.EpubBrowserBasePath={urls.base_path!r};window.EpubBrowserMode="server";window.EpubBrowserI18n.init();</script>
<link rel="stylesheet" href="/assets/vendor/fontawesome/css/all.min.css">
<link rel="icon" type="image/png" href="/assets/favicon.png">
<link rel="stylesheet" href="/assets/theme.css">
<link rel="stylesheet" href="/assets/notification.css">
<link rel="stylesheet" href="/assets/dialog.css">
<link rel="stylesheet" href="/assets/library.css?v=13">
<link rel="stylesheet" href="/assets/breadcrumb.css?v=3">
<link rel="stylesheet" href="/assets/loading.css?v=15">
{SERVER_ACCOUNT_STYLESHEET}
<link rel="stylesheet" href="{insights_css}">
<script>try{{var epubBrowserTheme=localStorage.getItem("theme")||"light";document.documentElement.classList.add(epubBrowserTheme+"-mode");}}catch(error){{document.documentElement.classList.add("light-mode");}}</script>
</head>
<body>
<header class="app-header">
  <nav class="app-nav app-nav-primary" aria-label="Primary navigation" data-i18n-aria-label="library.navigation">
    <a class="app-nav-brand" href="/" aria-label="EPUB Browser" data-i18n-aria-label="common.brand"><img class="app-nav-brand-mark" src="/assets/logo-mark-color.png" width="32" height="32" alt="" aria-hidden="true"><span data-i18n="common.brand">EPUB Browser</span></a>
    <div class="app-nav-links">
      <a class="app-nav-link" href="/" data-i18n="readingInsights.library">Library</a>
      <a class="app-nav-link is-active" href="/reading-insights" aria-current="page" data-i18n="readingInsights.navigation">Reading insights</a>
    </div>
    <div class="app-nav-actions">
      {SERVER_LOCALE_CONTROL}
      <button type="button" class="theme-toggle app-nav-action app-nav-theme" id="themeToggle" aria-label="Theme" data-i18n-aria-label="library.theme"><i class="fas fa-moon" aria-hidden="true"></i><span class="app-nav-action-label" data-i18n="library.theme">Theme</span></button>
      {SERVER_ACCOUNT_CONTROL}
    </div>
  </nav>
</header>
<main class="reading-insights-page" data-reading-insights tabindex="-1" aria-busy="true" aria-labelledby="readingInsightsTitle">
  <section class="reading-insights-heading">
    <p class="reading-insights-kicker" data-i18n="readingInsights.privateKicker">Private to your account</p>
    <h1 id="readingInsightsTitle" data-i18n="readingInsights.title">Reading insights</h1>
    <p data-i18n="readingInsights.intro">See when you actively read and where your time went.</p>
  </section>
  <section class="reading-insights-periods" aria-label="Reading period" data-i18n-aria-label="readingInsights.periodLabel">
    <button type="button" data-reading-insights-period="day" aria-pressed="false" data-i18n="readingInsights.period.day">Day</button>
    <button type="button" data-reading-insights-period="week" aria-pressed="true" data-i18n="readingInsights.period.week">Week</button>
    <button type="button" data-reading-insights-period="month" aria-pressed="false" data-i18n="readingInsights.period.month">Month</button>
  </section>
  <nav class="reading-insights-range" aria-label="Reading range" data-i18n-aria-label="readingInsights.rangeLabel">
    <button type="button" data-reading-insights-previous aria-label="Previous range" data-i18n-aria-label="readingInsights.previousRange" data-i18n="readingInsights.previousRange">Previous range</button>
    <p class="reading-insights-range-label" data-reading-insights-range-label aria-live="polite" aria-atomic="true">—</p>
    <button type="button" data-reading-insights-next aria-label="Next range" data-i18n-aria-label="readingInsights.nextRange" data-i18n="readingInsights.nextRange">Next range</button>
  </nav>
  <p class="reading-insights-live" data-reading-insights-live role="status" aria-live="polite" aria-atomic="true" data-i18n="readingInsights.loading">Loading reading insights…</p>
  <section class="reading-insights-summary" aria-label="Reading summary" data-i18n-aria-label="readingInsights.summaryLabel">
    <article class="reading-insights-summary-card"><p data-i18n="readingInsights.total">Active reading</p><strong data-reading-insights-total>—</strong></article>
    <article class="reading-insights-summary-card"><p data-i18n="readingInsights.topBook">Top book</p><strong data-reading-insights-top-book>—</strong></article>
  </section>
  <section class="reading-insights-days" aria-labelledby="readingInsightsDaysTitle"><h2 id="readingInsightsDaysTitle" data-i18n="readingInsights.days">Days</h2><div class="reading-insights-day-list" data-reading-insights-days></div></section>
  <section class="reading-insights-sessions" aria-labelledby="readingInsightsSelectedDay"><h2 id="readingInsightsSelectedDay" data-reading-insights-selected-day data-i18n="readingInsights.selectedDay">Selected day</h2><ol data-reading-insights-sessions></ol></section>
</main>
{SERVER_ACCOUNT_PANEL}
{render_footer(datetime.now().year, release_api_url='/api/version')}
<script src="/assets/cache-boundary.js" defer></script>
<script src="/assets/notification.js" defer></script>
{SERVER_AUTH_SCRIPT}
<script src="/assets/theme.js" defer></script>
<script src="/assets/dialog.js" defer></script>
<script src="/assets/version-check.js" defer></script>
{SERVER_LOCALE_SCRIPT}
<script src="{insights_script}" defer></script>
<script>document.addEventListener("DOMContentLoaded",function(){{function start(){{if(!window.EpubBrowserAuth||!window.EpubReadingInsights)return;window.EpubBrowserAuth.init().then(function(session){{if(session)window.EpubReadingInsights.mount(document.querySelector("[data-reading-insights]"));}});}}if(window.EpubBrowserCacheBoundary)window.EpubBrowserCacheBoundary.start(start);else start();}});</script>
</body>
</html>'''
