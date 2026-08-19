# Server account system design

## Purpose and scope

EPUB Browser Server currently accepts a client-provided `X-Username` header
and uses that value to partition annotations, reading progress, and bookshelf
data.  It is a display nickname, not an authentication mechanism: any client
can impersonate another name.  This design replaces it with authenticated,
stable accounts for Server mode only.

The first release provides:

- mandatory authentication for every Server page, book resource, and API;
- local password accounts and trusted reverse-proxy / SSO identities;
- one local account associated with zero or more external identities;
- `admin` and `member` roles, user administration, password reset, and
  restricted-book grants;
- transactional migration of existing server user data to the bootstrap
  administrator;
- an SSG mode that remains completely static and has no account dependency.

It does not provide public registration, email delivery, direct OAuth/OIDC
protocol handling, anonymous Server access, organization tenancy, or per-user
uploaded book libraries.  An external identity provider is integrated through
a trusted reverse proxy; that proxy performs the provider-specific protocol.

## Decisions

| Area | Decision |
| --- | --- |
| Account creation | The first Server startup creates an administrator from deployment credentials. Afterwards only administrators create users. |
| Login methods | Local password and trusted-proxy identity methods coexist and can be linked to one account. |
| Unrecognized SSO identity | It may be linked to an existing account only after that account's password is verified; an administrator may also link it. |
| Password recovery | An administrator resets passwords; no SMTP service is included. |
| Library access | All authenticated accounts can read normally visible books. Administrators may restrict an individual book to selected accounts. |
| Existing user data | All legacy annotations, bookshelves, and progress rows become data of the bootstrap administrator. |
| Session lifetime | Browser sessions have a 30-day sliding expiry and may be revoked by the user or an administrator. |

## Components and boundaries

### State store

`StateStore` owns schema creation, migrations, account persistence, book access
grants, and all scoped data queries.  A new schema version adds the following
logical tables:

- `users`: immutable internal ID, case-normalized unique username, role,
  enabled flag, optional Argon2id password hash, timestamps;
- `user_identities`: unique `(issuer, subject)` pairs pointing at `users.id`;
- `sessions`: random token digest, user ID, expiry, last-used time, and
  revocation time;
- `book_access`: `(book_id, user_id)` grants for restricted books;
- a visibility field on `books`, whose default is `authenticated` and whose
  restricted value requires a matching `book_access` record.

Annotations, reading progress, and bookshelves gain `user_id` ownership.
Their legacy `username` values are retained only during compatibility migration
and must not participate in authorization after the migration.

All migration work happens in one SQLite `BEGIN IMMEDIATE` transaction.  The
existing verified database-backup process runs before opening that transaction.
For an existing database, initialization first creates the bootstrap
administrator, then assigns every legacy data row to it and rebuilds any
username-based primary keys or indexes using `user_id`.  A failed migration
rolls back and leaves the backed-up original database available; startup fails
closed.

### Authentication service

A focused authentication service sits between Starlette requests and the state
store.  It has four responsibilities:

1. verify a local username/password against an Argon2id hash;
2. create, rotate, look up, and revoke opaque random session tokens;
3. resolve a proxy assertion to a configured `issuer + subject` identity;
4. expose an authenticated principal (`user_id`, username, role) to handlers.

The browser receives only a random session token in an `HttpOnly`,
`SameSite=Lax` cookie.  The database stores a one-way digest of that token, not
the token itself.  State-changing cookie-authenticated requests require a
CSRF token.  Password and token values never appear in logs, error responses,
or health endpoints.

The application never reads `X-Username`.  A proxy identity is honored only
when both of these are configured: a trusted source address range and an
identity-header definition.  The configured issuer is part of the identity
key, and a proxy-supplied display name is never used as a key.  Requests from
any other peer ignore forwarded identity headers.  This prevents a direct
client from forging an SSO login.

### Authorization service

The authorization layer uses the resolved principal, never browser local
storage or request headers.  It guards:

- index and reader HTML;
- cover images, chapter files, EPUB resources, and downloads;
- catalog, annotations, progress, bookshelf, SSE, and administration APIs;
- book routes addressed directly by a known book ID.

Authentication is required before normal Server content is served.  For a
restricted book, the layer also verifies that the principal is an administrator
or has an explicit grant.  The library metadata endpoint returns only books
the principal can access, so direct URLs cannot bypass the catalog filter.

## User-facing flows

### Bootstrap and local login

On the first persistent Server start, the deployment must provide
`EPUB_BROWSER_ADMIN_USERNAME` and one of
`EPUB_BROWSER_ADMIN_PASSWORD_FILE` (preferred) or
`EPUB_BROWSER_ADMIN_PASSWORD`.  The password file supports a Docker/Kubernetes
secret mount.  If the database has no administrator and these values are
absent or invalid, startup fails with a credential-free configuration error.

The login page posts local credentials over the same origin.  A successful
login creates a session and redirects to the originally requested safe path.
Users can change their own password and revoke their own sessions.  An
administrator can create, enable, disable, reset the password of, and revoke
all sessions for a member.  The last enabled administrator cannot be disabled
or demoted.

### Trusted proxy / SSO login and linking

An operator optionally configures trusted proxy CIDRs, the subject header, an
optional display-name header, and a stable issuer string.  When a request from
a trusted proxy has an already-linked `(issuer, subject)`, the application
creates or refreshes that account's local session.

An unknown assertion leads to an association page, not automatic account
creation.  The user can prove ownership of an existing local account by
entering its password, after which the identity is linked and a session is
created.  An administrator can create the mapping or remove it in the account
administration page.  Linking must reject an identity already linked to another
account.

### Library management

The Server header's current nickname-only login UI becomes a real account menu:
current user, account settings, logout, and an Administrator entry for admins.
The administrator page manages accounts, active sessions, restricted-book
membership, and legacy-data migration status.  Existing local username and
manual Sync prompts are removed from Server UI.  Bookshelf synchronization,
annotations, and progress derive their owner from the session automatically.

All new pages, validation messages, and permissions labels use the existing
English and Simplified Chinese i18n catalogues.

## Routes and response semantics

The exact route names may follow existing project naming conventions, but the
public contract contains these operations:

- login, logout, current-session status, CSRF bootstrap, password change;
- proxy identity association with an existing account;
- administrator user CRUD, password reset, account enable/disable, and
  session revocation;
- administrator book visibility and grant management.

Unauthenticated HTML requests redirect to login.  Unauthenticated API and SSE
requests return `401`; unauthorized book/API requests return `403` without
leaking restricted-book metadata.  Session expiry, logout, disablement, and
revocation all invalidate subsequent API requests immediately.  CSRF failure
returns `403` with a structured API error.

## Configuration and deployment

The CLI adds Server-only authentication settings, with environment-variable
counterparts for secret-friendly deployment.  Relevant settings include the
bootstrap username/password source, cookie security/public URL behavior,
trusted-proxy CIDRs, proxy subject/display-name header names, and proxy issuer.
Authentication configuration is rejected for SSG rather than silently ignored.

Docker documentation provides a secure example that mounts the Server data
directory and an administrator-password secret, runs behind TLS, and configures
the reverse-proxy trust boundary.  Documentation explicitly states that merely
setting a forwarding header is insufficient: the Uvicorn port must not be
directly reachable by untrusted clients when proxy authentication is enabled.

## Compatibility

SSG emits no login, account, administration, proxy, session, or authentication
API behavior.  Its annotations and reading progress remain browser-local.

The Server migration is intentionally a breaking security change: it no longer
accepts username identity supplied by JavaScript, local storage, or clients.
Existing browser data is not deleted, but only server-resident data migrates to
the bootstrap administrator.  Existing manual bookshelf sync begins operating
under the authenticated session after users log in.

## Error handling and observability

- Bootstrap misconfiguration, unsupported newer database schema, migration
  failure, and password-hash corruption fail startup closed.
- Repeated login failures receive rate limiting without revealing whether a
  username exists.
- Login and identity-link errors are deliberately generic to callers but have
  safe operational log entries when `--log` is enabled.
- Health and readiness endpoints require authentication too; they expose no
  user, identity, or secret state.
- Disabling an account revokes all its sessions in the same transaction.

## Test strategy

Unit and integration coverage will verify:

1. Argon2id password hashing, token-digest storage, session expiry/rotation,
   logout, CSRF, throttling, and no secret leakage;
2. trusted-proxy source/header/issuer validation, local-account linking,
   duplicate identity rejection, and untrusted header rejection;
3. user/role lifecycle, last-admin protection, password reset, and immediate
   session revocation after disablement;
4. catalog and direct-file authorization for normal and restricted books,
   including covers, resources, reader HTML, APIs, and SSE;
5. transactional migration of annotations, bookshelf rows, progress, and
   existing database backups, with rollback on injected failure;
6. i18n coverage and browser behavior for login/account/admin interfaces;
7. regression checks that SSG produces no account controls, no authentication
   calls, and no dependency on `epub_browser_username`.

## Acceptance criteria

- An unauthenticated request cannot read Server content or impersonate another
  user with `X-Username`.
- A newly bootstrapped administrator can create a member, reset its password,
  restrict a book, grant that member access, and revoke access again.
- A configured trusted SSO identity can be linked to a local account; the same
  asserted identity cannot be attached to two accounts.
- Existing server-resident annotations, bookshelf state, and progress are
  present under the bootstrap administrator after migration.
- A restricted book is inaccessible by catalog omission and direct resource
  URLs to an unauthorized account.
- SSG behavior, output, and local annotation/progress storage remain unchanged.
