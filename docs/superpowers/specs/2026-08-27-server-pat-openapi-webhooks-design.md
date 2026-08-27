# Server PAT, OpenAPI, and WebHook Design

**Date:** 2026-08-27

**Status:** Pending written-spec review

## Summary

EPUB Browser Server will add three related Server-only capabilities:

1. account-owned personal access tokens (PATs) with explicit scopes;
2. a versioned, documented external API under `/api/v1/*`;
3. administrator-managed, signed WebHooks with durable delivery and retry.

The existing browser API remains an internal Cookie Session + CSRF surface. The
external API is a separate compatibility boundary that accepts Bearer PATs only.
Both surfaces call the existing state and content services, so the feature does
not introduce a second source of truth.

The work changes the Server SQLite schema and dynamic Server UI. It does not
change the EPUB-derived content cache schema, does not raise
`SERVER_OUTPUT_REVISION`, and does not add any capability or API dependency to
SSG output.

## Goals

- Let each account create, inspect, and revoke scoped PATs from Account
  settings.
- Let external clients read the accessible library and chapter content.
- Let external clients read or write the token owner's bookshelf, progress,
  annotations, and reviews when explicitly scoped.
- Let an administrator PAT read all users' non-secret personal data without
  granting administrator write operations.
- Publish an OpenAPI 3.1 contract and a self-contained documentation page.
- Let administrators configure event subscriptions and inspect reliable,
  signed WebHook delivery from the administration panel.
- Preserve existing authentication, book visibility, user isolation, dynamic
  Server rendering, and SSG boundaries.

## Non-goals

- PAT access to the existing browser-oriented `/api/*` routes.
- External administrator mutations of users, permissions, books, AI settings,
  dictionaries, WebHooks, or other system configuration.
- Raw EPUB downloads or direct publication of files under Server `content/`.
- WebHook delivery of full review ratings or review text.
- Exposure of password hashes, Session or PAT digests, provider credentials,
  WebHook signing secrets, or other authentication material.
- A separate API process, database, or deployment unit.
- An OpenAPI or WebHook surface in SSG builds.

## Architectural boundary

### Existing browser surface

Existing `/api/*` handlers continue to authenticate with the HttpOnly Session
cookie. Unsafe methods continue to require the current CSRF token. Existing
response shapes remain internal UI contracts and are not retroactively declared
stable public APIs.

### External API surface

New external operations live under `/api/v1/*` and accept only:

```http
Authorization: Bearer <personal-access-token>
```

Cookie Sessions do not authenticate `/api/v1/*`, and PATs do not authenticate
the existing browser APIs. This keeps CSRF and Bearer-token behavior separate,
makes the external contract versionable, and prevents an internal route from
becoming public merely because a PAT middleware was added globally.

The implementation is split by responsibility:

- `epub_browser/pat.py`: token generation, parsing, authentication, and scope
  decisions;
- `epub_browser/public_api.py`: versioned routes, request/response schemas, and
  OpenAPI declarations;
- `epub_browser/webhooks.py`: domain events, signatures, delivery worker,
  retries, retention, and redelivery;
- `epub_browser/state.py`: SQLite records, v16 migration, transactional outbox,
  and query methods;
- `epub_browser/server.py`: mounts the new routes and owns Server lifecycle;
- `epub_browser/server_chrome.py` and Server assets: Account PAT and
  Administration WebHook interfaces.

These modules reuse `StateStore`, the existing access checks, dynamic Server
content restoration, and the asset publisher. They do not create another book,
user, or reading-data model.

## Personal access tokens

### Token representation

A token has an identifiable, versioned prefix and a high-entropy secret, for
example:

```text
epub_pat_<public-id>_<random-secret>
```

The public ID permits an indexed lookup. SQLite stores a one-way digest of the
complete raw token and never stores the raw token. Authentication compares the
stored and supplied digests with `hmac.compare_digest`. The complete token is
returned exactly once by the creation response and cannot be recovered later.

Each token record contains:

- stable token ID and public lookup ID;
- owning user ID;
- user-visible name;
- normalized scope set;
- creation and optional expiration timestamps;
- last-used timestamp;
- optional revocation timestamp.

`last_used_at` is updated at a coarse interval rather than on every request so a
busy integration does not turn every read into a SQLite write.

### Scope model

The first version supports:

- `library:read`
- `bookshelf:read`
- `bookshelf:write`
- `progress:read`
- `progress:write`
- `annotations:read`
- `annotations:write`
- `reviews:read`
- `reviews:write`
- `admin:data:read`

A write scope requires its matching read scope. The Account UI automatically
selects the read scope when a write scope is selected, and the Server validates
the same invariant rather than trusting the browser.

Only an administrator may create a token containing `admin:data:read`. The
scope is checked against the owner's current role on every request. Demoting an
administrator therefore removes cross-user access immediately even though the
token record remains. An administrator still needs `library:read` to call the
ordinary library and chapter routes; `admin:data:read` does not silently expand
into unrelated scopes.

### Lifetime and lifecycle

The creation UI offers 30, 90, 180, and 365 days, plus an explicit never-expire
choice. Never-expiring tokens remain visually marked in the token list. Expired
and revoked tokens cannot be restored.

Creating a PAT requires the account's current password in addition to an
authenticated browser Session and valid CSRF token. Listing and revoking the
account's own PATs use the existing browser Session boundary. A PAT cannot list,
create, rotate, or revoke PATs.

Lifecycle rules are:

- disabling a user invalidates and revokes all of the user's PATs;
- an administrator password reset revokes all of the affected user's PATs;
- a user changing their own password keeps existing PATs;
- demotion removes `admin:data:read` capability immediately;
- deleting or revoking one token does not affect browser Sessions or other
  tokens.

Account management routes remain internal browser APIs:

- `GET /api/account/pats`
- `POST /api/account/pats`
- `DELETE /api/account/pats/{token_id}`

List responses expose metadata only. The POST response is the only response
that includes the newly generated raw token.

## External API contract

### Common behavior

All `/api/v1/*` JSON list operations use bounded cursor pagination and stable
ordering. Cursor values are opaque. Invalid cursors, filters, or request bodies
return stable machine-readable error codes.

The common error envelope is versioned and includes at least an error code and
human-readable message. Authentication failures return `401` with an
appropriate `WWW-Authenticate: Bearer` header. Valid PATs lacking a required
scope return `403`. A missing book and a book the principal cannot see both
return `404` so restricted book IDs cannot be probed.

Book visibility is evaluated from the current account and grants on every
request. PAT authentication never substitutes for book authorization.

### Library and chapter operations

The `library:read` scope permits:

- `GET /api/v1/books`
- `GET /api/v1/books/{book_id}`
- `GET /api/v1/books/{book_id}/chapters`
- `GET /api/v1/books/{book_id}/chapters/{chapter_index}`

The books collection returns only books visible to the token owner. Book detail
contains stable book identity and normalized metadata. The chapter collection
returns the normalized table of contents, chapter indices, and titles.

Chapter detail defaults to a JSON representation containing chapter metadata
and the existing sanitized HTML content. `?format=text` returns the cleaned
plain-text representation with an appropriate text content type. The handler
checks visibility before restoring or reading cached content. It uses the
existing Server chapter cache and does not expose cache paths, raw cache JSON,
or the original EPUB file.

### Token-owner operations

The token owner's resources are grouped under `/api/v1/me`:

- `GET` and `PUT /api/v1/me/bookshelf`
- `GET /api/v1/me/progress`
- `GET`, `PUT`, and `DELETE /api/v1/me/progress/{book_id}`
- `GET` and `POST /api/v1/me/annotations`
- `GET`, `PUT`, and `DELETE /api/v1/me/annotations/{annotation_id}`
- `GET /api/v1/me/reviews`
- `GET`, `PUT`, and `DELETE /api/v1/me/reviews/{book_id}`

Each operation requires its resource's explicit read or write scope. Existing
validation, ownership checks, book visibility, field limits, and conflict
semantics are reused. A token can never choose another owner through a query or
request-body field.

### Administrator read operations

`admin:data:read` grants read-only access to all users' non-secret personal
application data. It covers:

- users and public account metadata;
- bookshelves;
- reading progress;
- annotations;
- ratings and full review text;
- reading-session history and computed reading insights;
- AI conversations and AI reading results.

Resources are grouped under `/api/v1/admin/users`:

- `GET /api/v1/admin/users`
- `GET /api/v1/admin/users/{user_id}/bookshelf`
- `GET /api/v1/admin/users/{user_id}/progress`
- `GET /api/v1/admin/users/{user_id}/annotations`
- `GET /api/v1/admin/users/{user_id}/reviews`
- `GET /api/v1/admin/users/{user_id}/reading-sessions`
- `GET /api/v1/admin/users/{user_id}/reading-insights`
- `GET /api/v1/admin/users/{user_id}/ai-conversations`
- `GET /api/v1/admin/users/{user_id}/ai-results`

Collections are paginated and accept only documented filters. These routes do
not expose password hashes, Session records or digests, PAT records or digests,
AI provider keys, WebHook signing secrets, or other credentials. They also do
not expose administrator mutations. System settings, job administration,
WebHook delivery administration, and permission mutation can be added later
under distinct scopes rather than expanding `admin:data:read`.

### OpenAPI publication

The canonical OpenAPI 3.1 document is available at `/openapi.json` after Server
setup. It contains no account or library data. A self-contained documentation
page is available at `/api-docs`; its scripts and styles are published locally,
with no CDN dependency. If the page offers an authorization field, the value is
kept in memory only and is never written to local storage, session storage, or
the URL.

Route metadata, request and response schemas, error schemas, and scope
requirements come from the same explicit Python declarations used to register
the external routes. Contract tests reject documented operations without a
route, routes without a documented operation, method mismatches, and scope
mismatches.

## WebHook configuration

Only a current administrator using a browser Session and CSRF token can manage
WebHooks. PATs cannot manage WebHooks in the first version.

The Administration panel gains a WebHooks section that supports:

- listing endpoints and their state;
- creating and editing an endpoint name and URL;
- enabling, disabling, and deleting an endpoint;
- choosing event subscriptions;
- creating or rotating a signing secret;
- sending a `webhook.test` event;
- viewing delivery and attempt history;
- manually redelivering a terminal or successful event.

Endpoint URLs may use any administrator-supplied HTTP or HTTPS address,
including loopback, private, link-local, and public destinations. Other URI
schemes are rejected. The UI warns that a destination can access services on
the Server's private network. Delivery still enforces connection and read
timeouts, response-size bounds, and a concurrency limit so one endpoint cannot
occupy the worker indefinitely.

Disabling an endpoint pauses its pending deliveries without discarding them.
Re-enabling resumes eligible deliveries. Deleting an endpoint cancels pending
delivery, prevents redelivery, erases its active signing secret, and retains
non-secret delivery history until normal retention cleanup.

## WebHook events

The first version defines:

- `book.created`
- `book.updated`
- `book.removed`
- `book.conversion.succeeded`
- `book.conversion.failed`
- `review.created`
- `review.updated`
- `review.deleted`
- `webhook.test`

Book events are emitted from authoritative reconciliation and conversion state
transitions, not from UI handlers. Review events are emitted from the same
transaction that creates, updates, or deletes the review.

Payloads are constructed from an explicit allowlist. Book payloads may contain
the book ID, normalized display metadata, and a reason code. Conversion-failure
payloads may contain a non-sensitive source display name and public error code,
but not an absolute source path, traceback, or file content. Review payloads
contain only the event action, user ID, book ID, and timestamps. They never
contain the rating or review body. An administrator integration can use its
`admin:data:read` PAT to retrieve the current full review after receiving the
event.

Every payload uses a versioned envelope:

```json
{
  "id": "evt_0123456789abcdef",
  "type": "review.updated",
  "version": "1",
  "created_at": "2026-08-27T00:00:00Z",
  "data": {
    "user_id": "0123456789abcdef",
    "book_id": "book_0123456789abcdef"
  }
}
```

The event ID is stable across automatic retries and manual redelivery so a
consumer can implement idempotency.

## Signing and delivery

Each endpoint has an independent 256-bit random signing secret. The Server must
retain that secret in a form usable for signing; it is protected by the same
filesystem and SQLite access boundary as other Server credentials and is never
returned by list operations or the external API. The raw secret is displayed in
the UI only immediately after endpoint creation or rotation. Rotation replaces
the active secret immediately, and all later attempts, including retries of an
older event, use the new secret.

The delivery request includes:

- `Content-Type: application/json`
- `User-Agent: EPUB-Browser-WebHook/<version>`
- `X-EPUB-Event: <event-type>`
- `X-EPUB-Delivery: <delivery-id>`
- `X-EPUB-Timestamp: <unix-seconds>`
- `X-EPUB-Signature: v1=<hex-hmac-sha256>`

The signature is HMAC-SHA256 over the ASCII timestamp, a period, and the exact
raw request body. Receivers can reject stale timestamps and compare signatures
in constant time. Redirects are not followed; a 3xx response is a failed
attempt, and the administrator should configure the final destination URL.

Event and delivery records use a SQLite transactional outbox. Where the domain
change is stored in SQLite, the change and event insertion occur in the same
transaction. Once committed, delivery is at least once. A conversion failure
that has no successful domain mutation records its failure event in a dedicated
transaction before the failure is considered reported.

The lifespan-owned worker claims deliveries with a lease so another worker or a
restart can recover abandoned work. The first attempt is immediate. Connection
errors, timeouts, and every non-2xx response retry with exponential backoff and
jitter, capped at 24 hours, for at most eight total attempts. A successful 2xx
marks the delivery complete. Exhausted deliveries become terminal failures and
remain available for administrator redelivery.

Each attempt records timing, the HTTP status when available, and a bounded,
text-safe response or error summary. It never records request Authorization
headers, signing secrets, or an unbounded remote response. Successful, failed,
and attempt records are retained for 30 days. Pending or leased deliveries are
not removed by retention cleanup.

WebHook delivery never waits in the originating HTTP response path. Failure of
a remote endpoint cannot roll back a committed user operation. Failure to
persist an event that is required to be transactional does prevent the paired
domain transaction from committing, preserving the outbox guarantee.

## SQLite schema and migration

`DB_SCHEMA_VERSION` increases from 15 to 16. The migration is automatic,
transactional, restart-safe, and creates:

- `personal_access_tokens`;
- `webhook_endpoints`;
- `webhook_subscriptions`;
- `webhook_events`;
- `webhook_deliveries`;
- `webhook_delivery_attempts`;
- lookup, owner, queue, lease, and retention indexes required by the access
  paths above.

Foreign keys bind PATs to users and WebHook configuration to its creating
administrator while preserving the history behavior described above. Scope and
event names are validated at the service boundary and stored in normalized
rows or canonical JSON only where normalization does not improve lookup.

The migration updates `PRAGMA user_version` only after all schema and integrity
checks pass. Fresh-database creation and v15 migration produce the same v16
schema. No EPUB-derived fields are added, so `.server-content-revision` remains
unchanged and existing converted books render immediately after deployment.

## Dynamic UI and internationalization

The PAT UI is added to `SERVER_ACCOUNT_PANEL`, and the WebHook UI is added to
the existing Server administration chrome. Scripts are served by the asset
publisher with hashed immutable URLs. The dynamic Server page shell therefore
receives the feature after restart without EPUB reconversion.

All visible copy, validation messages, server-returned public error messages,
status text, warnings, and accessible labels are added to every currently
supported locale: English, Simplified Chinese, Traditional Chinese, Korean,
and Japanese. The SSG template path emits none of the Server panels, scripts,
routes, account data, or feature copy.

## Error and recovery behavior

- Invalid, malformed, expired, revoked, or disabled-owner PATs return the same
  authentication failure shape and do not reveal which check failed.
- Scope failures identify the required public scope without exposing protected
  resource existence.
- Pagination and validation failures are deterministic and documented.
- External API responses use private/no-store cache policy for personal data
  and chapter content; the OpenAPI schema and local documentation assets may use
  deployment-appropriate cache headers.
- A worker crash releases work through lease expiry; restart resumes queued and
  retryable deliveries.
- Manual redelivery preserves the event ID and creates a fresh delivery run and
  attempt history.
- Endpoint disablement is reversible; endpoint deletion is not.

## Verification strategy

### State and migration

- Initialize a fresh v16 database and migrate a representative v15 fixture.
- Verify migration rollback and restart behavior.
- Verify foreign keys, indexes, retention queries, delivery leases, and queue
  claims.
- Verify raw PAT values never appear in SQLite, logs, list APIs, or generated
  pages.

### PAT and authorization

- Test entropy, parsing, indexed lookup, digest comparison, expiration,
  revocation, and throttled `last_used_at` writes.
- Test every scope independently and test the write-implies-read invariant.
- Test user disablement, administrator reset, self password change, role
  demotion, and never-expiring tokens.
- Test that browser cookies cannot authenticate `/api/v1/*` and PATs cannot
  authenticate browser or PAT-management routes.

### External API

- Test user isolation for bookshelf, progress, annotations, and reviews.
- Test administrator cross-user reads and absence of administrator writes.
- Test authenticated and restricted book visibility for catalog, TOC, HTML
  chapter content, and plain text.
- Test cursor pagination, stable ordering, field validation, content types,
  cache policy, and error envelopes.
- Contract-test every OpenAPI operation against its registered method, path,
  schema, response, and scope.

### WebHooks

- Test event allowlists and prove review events contain no rating or body.
- Test exact raw-body signatures, timestamp headers, secret rotation, and
  stable event IDs.
- Test success, timeout, connection error, 3xx, 4xx, and 5xx behavior with a
  fake transport and deterministic clock.
- Test retry backoff, eight-attempt exhaustion, leases, concurrent workers,
  restart recovery, disable/resume, deletion, retention, and manual redelivery.
- Test transactional event creation with review and book state changes.
- Test arbitrary HTTP/HTTPS targets while rejecting non-HTTP schemes and
  enforcing response and concurrency limits.

### UI, modes, and regression

- Test one-time secret rendering, scope selection, token state labels, WebHook
  forms, history, keyboard behavior, and accessible status announcements.
- Extend i18n coverage for all five locales.
- Verify dynamic Library, Book, and Chapter Server pages include the current
  Server-only assets after restart.
- Verify SSG output contains no PAT, OpenAPI, WebHook, Bearer-auth, or
  `/api/v1` dependency.
- Run the Server, StateStore, generated-surface, i18n, asset, SSG, and mode
  integration suites affected by the change, followed by `git diff --check`.

## Delivery order

Implementation should proceed in dependency order:

1. v16 schema, PAT primitives, lifecycle, and Account UI;
2. external API declarations, authorization, resource handlers, and OpenAPI
   publication;
3. WebHook schema, domain-event outbox, worker, signatures, and retry;
4. Administration UI, delivery inspection, i18n, documentation, and complete
   cross-mode verification.

This order does not split the compatibility contract: all three capabilities
ship only after the complete security, migration, and SSG boundary tests pass.
