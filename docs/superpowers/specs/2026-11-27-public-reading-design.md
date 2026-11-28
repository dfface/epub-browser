# Server public reading and default book visibility

Approved direction: extend existing admin/member roles and per-book grants; no general-purpose RBAC. Implements GitHub issues #85 and #86, in that order.

## Access policy

Add `public` alongside `authenticated` and `restricted`. Active public books are readable by authenticated members and administrators. Anonymous visitors may read public books only when `allow_anonymous_reading` is true; its default is false. Active authenticated books require login. Restricted books require an explicit user grant or administrator role. Inactive books remain unavailable.

Anonymous is an absent authenticated principal, not a persisted guest user. Anonymous access is read-only and explicitly allowed by route, never by broad path-prefix bypass. Lists, counts, metadata, search, covers, TOCs, chapter pages and book resources must apply the same visibility policy as direct book checks. Invisible books must not be discoverable through details or resources.

PDF delivery retains the same-origin document route and Range support. Apply visibility checks before document access and conditional responses. Do not expose cache files, absolute paths or a new raw-file API. Session-authenticated personal APIs, AI permissions and PAT/OpenAPI authentication remain protected independently of public reading.

## Application settings and import lifecycle

Store `allow_anonymous_reading=false` and `default_book_visibility=authenticated` in SQLite application settings. Admin APIs validate types and supported values. Public may be selected as the default even while anonymous reading is disabled; explain that the global switch still gates anonymous access.

Read the configured default inside the transaction that actually inserts a new book in `StateStore.resolve_book`. Existing-path updates, stable-ID restoration, source moves, rescans and cache rebuilds preserve visibility and grants. Changing the default affects only future first-time imports. Watched directories and administrator uploads share this policy for both EPUB and PDF.

SQLite migration must expand the books visibility CHECK constraint while preserving book IDs, relationships, grants and indexes. Existing installations retain their prior access behavior. Do not bump EPUB/PDF content-cache revisions or include these settings in SSG output.

## Reader and cache behavior

Use shared dynamic templates. Convey anonymous capabilities explicitly and prevent personal/AI API initialization for anonymous pages; offer a localized login path with a safe local return destination. Cover normal chapter, paginated and continuous readers plus Kindle; preserve SSG behavior.

Visibility or configuration changes take effect on subsequent requests, including Range and conditional requests. Dynamic and book-specific protected responses must not receive long-lived shared caching. Globally shared hashed UI assets may retain immutable caching. Content already delivered to a browser cannot be revoked.

## Alternatives

A configurable RBAC system would add custom roles, permission catalogs and assignment UI without a requirement for librarians, reviewers or groups. The chosen existing-role plus resource-grant approach satisfies both issues with a smaller policy surface.

## Verification and delivery

Behavioral seams: StateStore public methods (authorization/settings/identity preservation), HTTP routes (discovery, reading, resources, personal API denial, Range and cache revocation), library import entry points (watched sources/uploads and restoration). Test migration with populated related records. Test both formats and retain SSG isolation. Verify localized dynamic UI and anonymous reader capability handling.

Use an isolated worktree and incremental red-green tests. Present running SSG and Server environments using examples before any commit/push/PR approval. Commit, push and PR creation follow explicit user acceptance and approval.
