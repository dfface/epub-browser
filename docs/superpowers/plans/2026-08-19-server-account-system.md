# Server Account System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Server mode a secure multi-user reading library with local-password accounts, trusted-proxy identities, per-book grants, and a safe upgrade path, while leaving SSG fully static.

**Architecture:** A new `auth.py` owns opaque Cookie sessions, Argon2id password verification, CSRF, setup completion, and proxy-identity resolution. `StateStore` owns users, identities, sessions, scoped user data, and book grants; `server.py` applies setup, authentication, and authorization boundaries before dynamic or static content is served. The Server runtime supports web-first or unattended bootstrap and trusted-proxy configuration, while SSG never creates or consumes this configuration.

**Tech Stack:** Python 3.9+, SQLite, Starlette, Uvicorn, `argon2-cffi`, browser JavaScript, Python `unittest`, Node `node:test`.

**Spec:** `docs/superpowers/specs/2026-08-19-server-account-system-design.md`

## Global Constraints

- Support Python `>=3.9`; do not use Python 3.10-only annotation syntax.
- Server authentication is mandatory; unauthenticated clients must not read pages, books, assets, APIs, SSE, health, or readiness state.
- Never accept `X-Username`, browser local storage, or a client body as Server identity.
- Store only Argon2id password hashes and session-token digests; never log a password, raw token, or bootstrap secret.
- Trust proxy identity headers only from explicitly configured CIDRs and include a configured issuer in the identity key.
- Keep SSG free of account routes, auth API calls, cookies, account controls, and `epub_browser_username` dependencies.
- Existing Server annotations, bookshelves, and progress migrate to one pending administrator ID in a rollback-safe SQLite upgrade; setup completes that same ID.
- Until one administrator is completed, expose only the localized setup surface, its fixed assets, and minimal setup-required health/readiness status; do not publish the library or honor proxy identities.
- Preserve the existing `--log` rule: normal Server operation must not print incidental output that corrupts tqdm progress.
- Every user-facing Server string is present in English and Simplified Chinese catalogs.
- Do not add browser end-to-end tests; user acceptance is manual. Automated coverage is limited to unit, in-process ASGI integration, static, and JavaScript tests.

---

## File structure and interfaces

| File | Responsibility |
| --- | --- |
| `epub_browser/auth.py` | `Principal`, `AuthConfig`, cookie/session/CSRF/password/proxy resolution, login throttling. |
| `epub_browser/state.py` | Schema v2 migration, account/identity/session persistence, `user_id` scoped content, book visibility and grants. |
| `epub_browser/cli.py` | Server-only account/proxy options and `ServerConfig.auth`. |
| `epub_browser/runtime.py` | Optionally resolve unattended secrets, gate library publication on setup, construct `AuthConfig`, pass it to `create_app`. |
| `epub_browser/server.py` | One-time localized setup, authentication middleware, local/proxy login routes, account/admin APIs, scoped existing APIs, protected static book delivery. |
| `epub_browser/site.py` | Server-only login/account/admin markup and no SSG auth controls. |
| `epub_browser/assets/auth.js` | Login, logout, session and CSRF helper, account/admin interactions. |
| `epub_browser/assets/i18n.js` | English/Simplified Chinese strings for auth and administration. |
| `epub_browser/assets/library.js`, `bookshelf.js`, `annotation.js`, `reading-progress.js`, `book.js` | Use Cookie/CSRF authenticated APIs; remove server username identity inputs. |
| `tests/test_auth.py` | Auth service, cookies, CSRF, rate-limits, proxy boundaries. |
| `tests/test_state.py` | Schema migration and account/store operations. |
| `tests/test_server.py` | HTTP login/auth/authorization/static-resource/admin behavior. |
| `tests/test_cli.py`, `tests/test_runtime.py` | Configuration and bootstrap secrets. |
| `tests/test_generated_reader_surfaces.py`, `tests/test_*.js` | Server UI i18n and SSG isolation. |
| `README.md`, `Dockerfile`, `docs/migration-v2.md` | Deployment, secrets, proxy trust boundary, breaking-change migration guidance. |

### Shared interfaces

```python
# epub_browser/auth.py
@dataclass(frozen=True)
class Principal:
    user_id: str
    username: str
    role: str

@dataclass(frozen=True)
class AuthConfig:
    cookie_secure: bool
    session_ttl_seconds: int
    csrf_header_name: str
    trusted_proxy_networks: tuple[ipaddress._BaseNetwork, ...]
    proxy_subject_header: Optional[str]
    proxy_display_name_header: Optional[str]
    proxy_issuer: Optional[str]

    @classmethod
    def from_values(cls, trusted_proxy_cidrs, proxy_subject_header, proxy_issuer,
                    proxy_display_name_header=None, cookie_secure=False): ...

@dataclass(frozen=True)
class ServerAuthOptions:
    admin_username: Optional[str] = None
    admin_password_file: Optional[Path] = None
    trusted_proxy_cidrs: tuple[str, ...] = ()
    proxy_subject_header: Optional[str] = None
    proxy_display_name_header: Optional[str] = None
    proxy_issuer: Optional[str] = None
    cookie_secure: Optional[bool] = None

class AuthService:
    def complete_setup(self, username: str, password: str) -> tuple[str, Principal]: ...
    def authenticate_password(self, username: str, password: str, client_key: str) -> Principal: ...
    def create_session(self, principal: Principal) -> tuple[str, str]: ...
    def principal_from_session(self, raw_token: Optional[str]) -> Optional[Principal]: ...
    def authenticate_proxy(self, client_host: str, headers) -> Optional[ProxyIdentity]: ...
    def issue_csrf_token(self, principal: Principal, raw_session: str) -> str: ...
    def verify_csrf(self, request, principal: Principal) -> bool: ...

# epub_browser/state.py
def bootstrap_admin(self, username: str, password_hash: str) -> Principal: ...
def has_administrator(self) -> bool: ...
def complete_administrator_setup(self, username: str, password_hash: str,
                                 token_digest: str, expires_at, *, now=None) -> Principal: ...
def migrate_user_owned_data(self, administrator_id: str) -> None: ...
def visible_books(self, principal: Principal) -> tuple[BookRecord, ...]: ...
def can_read_book(self, user_id: str, role: str, book_id: str) -> bool: ...
```

### Task 1: Add account configuration and cryptographic primitives

**Files:**
- Create: `epub_browser/auth.py`
- Modify: `setup.py`
- Modify: `epub_browser/cli.py`
- Modify: `tests/test_auth.py`
- Modify: `tests/test_cli.py`

**Consumes:** Existing `ServerConfig` parser pattern in `epub_browser/cli.py`.

**Produces:** `AuthConfig`, `BootstrapCredentials`, `Principal`, proxy-CIDR parsing, cookie option helpers, `hash_password`, `verify_password`, and ServerConfig fields used by Tasks 2–10.

- [ ] **Step 1: Write failing configuration and password tests**

```python
class AuthPrimitiveTests(unittest.TestCase):
    def test_argon2_hash_is_verifiable_but_does_not_contain_password(self):
        encoded = hash_password('correct horse battery staple')
        self.assertNotIn('correct horse battery staple', encoded)
        self.assertTrue(verify_password(encoded, 'correct horse battery staple'))
        self.assertFalse(verify_password(encoded, 'wrong'))

    def test_proxy_config_requires_subject_header_issuer_and_trusted_cidr(self):
        with self.assertRaises(ValueError):
            AuthConfig.from_values(['10.0.0.0/8'], 'X-Remote-User', None)

class CLITests(unittest.TestCase):
    def test_server_parses_auth_proxy_options_without_affecting_ssg(self):
        config = parse_cli(['server', 'library', '--server-dir', 'data',
                            '--trusted-proxy-cidr', '10.0.0.0/8',
                            '--proxy-subject-header', 'X-Remote-User',
                            '--proxy-issuer', 'https://sso.example'])
        self.assertEqual(config.auth.proxy_issuer, 'https://sso.example')
```

- [ ] **Step 2: Run the new tests and verify they fail**

Run: `python3 -m unittest tests.test_auth.AuthPrimitiveTests tests.test_cli.CLITests.test_server_parses_auth_proxy_options_without_affecting_ssg`

Expected: FAIL because `epub_browser.auth` and the Server auth fields do not exist.

- [ ] **Step 3: Add the dependency and minimal value objects**

```python
# setup.py
install_requires = [..., 'argon2-cffi>=23.1,<26.0']

# epub_browser/auth.py
def hash_password(password: str) -> str:
    return PasswordHasher(type=Type.ID).hash(password)

def verify_password(encoded: str, password: str) -> bool:
    try:
        return PasswordHasher(type=Type.ID).verify(encoded, password)
    except (VerifyMismatchError, InvalidHashError, VerificationError):
        return False

@dataclass(frozen=True)
class BootstrapCredentials:
    username: str
    password: str
```

Extend `ServerConfig` with an `auth: ServerAuthOptions` default value. Add the
Server-only CLI options `--admin-username`, `--admin-password-file`,
`--trusted-proxy-cidr` (repeatable), `--proxy-subject-header`,
`--proxy-display-name-header`, `--proxy-issuer`, and `--cookie-secure`.
Validate that all proxy settings are supplied together; reject these options
for `ssg` through argparse rather than silently accepting them.

- [ ] **Step 4: Run focused tests**

Run: `python3 -m unittest tests.test_auth.AuthPrimitiveTests tests.test_cli`

Expected: PASS.

- [ ] **Step 5: Commit the vertical slice**

```bash
git add setup.py epub_browser/auth.py epub_browser/cli.py tests/test_auth.py tests/test_cli.py
git commit -m "feat: add Server authentication configuration"
```

### Task 2: Add transactional account schema and legacy ownership migration

**Files:**
- Modify: `epub_browser/state.py`
- Modify: `tests/test_state.py`
- Modify: `tests/test_migration.py`

**Consumes:** `Principal` and password hashes from Task 1.

**Produces:** Schema version 2, user/identity/session/access tables, user-owned annotation/bookshelf/progress methods, and `bootstrap_admin` migration entry point used by Task 3.

- [ ] **Step 1: Write failing migration tests using a real v1 SQLite database**

```python
def test_v1_user_content_moves_to_bootstrap_administrator(self):
    self._create_v1_database_with_annotation_bookshelf_and_progress('legacy-name')
    store = StateStore(self.database)
    admin = store.initialize(bootstrap=BootstrapCredentials('admin', 'secret'))
    self.assertEqual(store.list_annotations(user_id=admin.user_id)[0]['text'], 'old note')
    self.assertEqual(store.get_bookshelf(user_id=admin.user_id)[0], 7)
    self.assertEqual(store.get_reading_progress(admin.user_id, 'book'), 3)

def test_migration_rolls_back_if_rekeying_bookshelf_fails(self):
    self._create_v1_database_with_annotation_bookshelf_and_progress('legacy-name')
    with mock.patch.object(StateStore, '_migrate_bookshelves', side_effect=sqlite3.Error('stop')):
        with self.assertRaises(sqlite3.Error):
            StateStore(self.database).initialize(bootstrap=BootstrapCredentials('admin', 'secret'))
    self.assertEqual(self._user_version(), 1)
```

- [ ] **Step 2: Run the migration tests and verify failure**

Run: `python3 -m unittest tests.test_state.StateStoreTests.test_v1_user_content_moves_to_bootstrap_administrator tests.test_state.StateStoreTests.test_migration_rolls_back_if_rekeying_bookshelf_fails`

Expected: FAIL because schema v2 and bootstrap-aware initialization do not exist.

- [ ] **Step 3: Implement schema v2 inside the existing explicit transaction**

```python
DB_SCHEMA_VERSION = 2

def initialize(self, bootstrap: Optional[BootstrapCredentials] = None) -> Optional[Principal]:
    # BEGIN IMMEDIATE; create/migrate schema; require bootstrap only when no admin exists.

def bootstrap_admin(self, username: str, password_hash: str) -> Principal:
    # Insert exactly one enabled admin with a generated immutable user ID.

def migrate_user_owned_data(self, administrator_id: str) -> None:
    # Add/backfill annotations.user_id, rebuild bookshelves and reading_progress
    # with user_id key columns, then create user_id indexes.
```

Use migration-specific temporary table names and reject a pre-existing
temporary table. Preserve `username` as legacy audit data, but change all
runtime queries to select by `user_id`. Add `books.visibility` defaulting to
`authenticated`, and `book_access(book_id, user_id)` with foreign keys and
unique composite primary key. Keep all schema changes and rekeys within the
current `BEGIN IMMEDIATE` / rollback mechanism.

- [ ] **Step 4: Add account and grant operations with tests**

```python
def test_restricted_book_requires_matching_grant(self):
    admin = self.store.create_user('admin', 'hash', role='admin')
    member = self.store.create_user('member', 'hash', role='member')
    self.store.set_book_visibility('book-1', 'restricted')
    self.assertFalse(self.store.can_read_book(member.user_id, member.role, 'book-1'))
    self.store.grant_book_access('book-1', member.user_id)
    self.assertTrue(self.store.can_read_book(member.user_id, member.role, 'book-1'))
```

Implement `create_user`, `get_user_by_username`, `set_password_hash`,
`set_user_enabled`, `list_users`, `set_book_visibility`,
`grant_book_access`, `revoke_book_access`, `visible_books`, and
`can_read_book` with parameterized SQL.

- [ ] **Step 5: Run state and migration suites**

Run: `python3 -m unittest tests.test_state tests.test_migration tests.test_mode_integration`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add epub_browser/state.py tests/test_state.py tests/test_migration.py
git commit -m "feat: migrate Server data to account ownership"
```

### Task 3: Implement session, CSRF, proxy identity, and throttling services

**Files:**
- Modify: `epub_browser/auth.py`
- Modify: `epub_browser/state.py`
- Modify: `tests/test_auth.py`

**Consumes:** User and identity persistence from Task 2.

**Produces:** `AuthService`, `ProxyIdentity`, session-store methods, CSRF verification, and login throttling used by HTTP routes in Task 4.

- [ ] **Step 1: Write failing security tests**

```python
def test_database_stores_digest_not_raw_session_token(self):
    principal = self._principal('alice')
    token, csrf = self.service.create_session(principal)
    self.assertIsNotNone(self.store.principal_from_session(token))
    self.assertNotIn(token, self.store.raw_session_rows())
    self.assertTrue(self.service.verify_csrf_token(principal, token, csrf))

def test_untrusted_client_cannot_assert_proxy_identity(self):
    identity = self.service.authenticate_proxy('203.0.113.8', {'X-Remote-User': 'subject'})
    self.assertIsNone(identity)

def test_failed_password_attempts_are_throttled_without_user_enumeration(self):
    for _ in range(5):
        self.assertIsNone(self.service.authenticate_password('missing', 'bad', 'ip'))
    self.assertTrue(self.service.login_is_throttled('ip'))
```

- [ ] **Step 2: Run the tests and verify failure**

Run: `python3 -m unittest tests.test_auth.SessionAndProxyTests`

Expected: FAIL because session, proxy, CSRF, and throttle interfaces are absent.

- [ ] **Step 3: Implement opaque session and proxy resolution**

```python
class AuthService:
    def create_session(self, principal: Principal) -> tuple[str, str]:
        raw_token = secrets.token_urlsafe(32)
        self.store.create_session(token_digest(raw_token), principal.user_id, self.clock() + self.ttl)
        return raw_token, self.issue_csrf_token(principal, raw_token)

    def authenticate_proxy(self, client_host: str, headers) -> Optional[ProxyIdentity]:
        if not self.config.is_trusted_proxy(client_host):
            return None
        subject = headers.get(self.config.proxy_subject_header)
        return ProxyIdentity(self.config.proxy_issuer, subject, headers.get(self.config.proxy_display_name_header)) if subject else None
```

Use `hmac.compare_digest` for token/CSRF comparison and SHA-256 only for
token-at-rest lookup. Persist expiry, last-used, and revocation time. Rotate or
extend sessions only when valid and within the 30-day sliding policy. Rate-limit
by client address plus normalized username using a bounded in-memory window;
return the same authentication failure result for unknown user and wrong
password. Add `revoke_session`, `revoke_all_sessions`, `principal_from_session`,
and identity CRUD store methods.

- [ ] **Step 4: Run focused security tests**

Run: `python3 -m unittest tests.test_auth`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add epub_browser/auth.py epub_browser/state.py tests/test_auth.py
git commit -m "feat: add secure Server sessions and proxy identities"
```

### Task 4: Protect every Server request and provide local login/logout routes

**Files:**
- Modify: `epub_browser/server.py`
- Modify: `tests/test_server.py`
- Modify: `tests/test_runtime.py`

**Consumes:** `AuthService` and `Principal` from Task 3; user-scoped StateStore methods from Task 2.

**Produces:** request `scope['epub_browser.principal']`, secure cookie handling, `/login`, `/logout`, `/api/session`, and common `require_principal` helpers used by Tasks 5–7.

- [ ] **Step 1: Write failing HTTP boundary tests**

```python
def test_server_redirects_unauthenticated_html_and_rejects_api_static_and_sse(self):
    self.assertEqual(self.client.get('/').status_code, 303)
    self.assertEqual(self.client.get('/api/annotations/book').status_code, 401)
    self.assertEqual(self.client.get('/book/id/chapter_0.html').status_code, 403)
    self.assertEqual(self.client.get('/api/library-events').status_code, 401)

def test_password_login_sets_httponly_session_and_requires_csrf_to_write(self):
    response = self.client.post('/login', data={'username': 'alice', 'password': 'secret'})
    self.assertEqual(response.status_code, 303)
    self.assertIn('HttpOnly', response.headers['set-cookie'])
    self.assertEqual(self.client.post('/api/annotations/book', json=self.annotation).status_code, 403)
```

- [ ] **Step 2: Run the HTTP tests and verify failure**

Run: `python3 -m unittest tests.test_server.ServerAuthBoundaryTests`

Expected: FAIL because unauthenticated content is currently served and login routes do not exist.

- [ ] **Step 3: Add authentication middleware and local session endpoints**

```python
async def auth_middleware(request, call_next):
    principal = auth_service.principal_from_session(request.cookies.get(SESSION_COOKIE))
    request.scope['epub_browser.principal'] = principal
    if route_is_public_auth_endpoint(request.url.path):
        return await call_next(request)
    if principal is None:
        return unauthenticated_response(request)
    return await call_next(request)

def require_principal(request) -> Principal:
    principal = request.scope.get('epub_browser.principal')
    if principal is None:
        raise HTTPException(status_code=401)
    return principal
```

Build the Starlette app with this middleware before the static mount so all
content, including static EPUB resources, passes through it. Permit only the
login/logout/identity-association endpoints and their fixed application assets
to bypass the login check; never permit reader or book paths. Make a GET/HEAD
HTML request redirect to `/login?next=<validated-relative-path>`; return a
structured `401` for JSON/SSE/API paths. Implement GET login form, POST local
login, POST logout, and GET session/CSRF endpoints. On every unsafe method,
require the configured CSRF header before calling a state-changing handler.
Set `Secure` from explicit runtime configuration and always set `HttpOnly` and
`SameSite=Lax`.

- [ ] **Step 4: Run focused server/runtime tests**

Run: `python3 -m unittest tests.test_server.ServerAuthBoundaryTests tests.test_runtime`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add epub_browser/server.py tests/test_server.py tests/test_runtime.py
git commit -m "feat: require authenticated Server sessions"
```

### Task 5: Add proxy association, account lifecycle, and administrator APIs

**Files:**
- Modify: `epub_browser/server.py`
- Modify: `epub_browser/state.py`
- Modify: `tests/test_server.py`
- Modify: `tests/test_state.py`

**Consumes:** middleware principal from Task 4, proxy identity resolution from Task 3, account persistence from Task 2.

**Produces:** proxy-account association endpoints, self-service password/session endpoints, and administrator account/session APIs for Task 8 UI.

- [ ] **Step 1: Write failing proxy and administrator tests**

```python
def test_unknown_trusted_proxy_identity_must_prove_existing_password_before_linking(self):
    response = self.proxy_client.get('/')
    self.assertEqual(response.status_code, 303)
    linked = self.proxy_client.post('/api/identity/link', json={'username': 'alice', 'password': 'secret'}, headers=self.csrf)
    self.assertEqual(linked.status_code, 201)
    self.assertEqual(self.proxy_client.get('/api/session').json()['user']['username'], 'alice')

def test_admin_disables_member_and_revokes_all_member_sessions(self):
    response = self.admin_client.put('/api/admin/users/member', json={'enabled': False}, headers=self.admin_csrf)
    self.assertEqual(response.status_code, 200)
    self.assertEqual(self.member_client.get('/api/session').status_code, 401)

def test_last_enabled_admin_cannot_be_disabled(self):
    response = self.admin_client.put('/api/admin/users/admin', json={'enabled': False}, headers=self.admin_csrf)
    self.assertEqual(response.status_code, 409)
```

- [ ] **Step 2: Run tests and verify failure**

Run: `python3 -m unittest tests.test_server.ProxyAssociationTests tests.test_server.AdminAccountTests`

Expected: FAIL because the association and administration routes do not exist.

- [ ] **Step 3: Implement the account lifecycle contract**

```python
Route('/api/identity/link', link_proxy_identity, methods=['POST'])
Route('/api/account/password', change_password, methods=['PUT'])
Route('/api/account/sessions', list_own_sessions, methods=['GET'])
Route('/api/account/sessions/{session_id}', revoke_own_session, methods=['DELETE'])
Route('/api/admin/users', admin_users, methods=['GET', 'POST'])
Route('/api/admin/users/{username}', admin_user, methods=['PUT'])
Route('/api/admin/users/{username}/password', admin_reset_password, methods=['PUT'])
```

Only allow identity linking when the request carries a pending identity from a
trusted proxy and password verification succeeds. Atomically reject identity
duplicates. Restrict every `/api/admin/` handler to `principal.role == 'admin'`.
On disable/password reset/revoke-all, revoke all target sessions in the same
store transaction. Enforce last-enabled-admin protection in the store rather
than only in the route.

- [ ] **Step 4: Run lifecycle tests**

Run: `python3 -m unittest tests.test_server.ProxyAssociationTests tests.test_server.AdminAccountTests tests.test_state.StateStoreTests`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add epub_browser/server.py epub_browser/state.py tests/test_server.py tests/test_state.py
git commit -m "feat: add Server account and identity management"
```

### Task 6: Scope annotations, bookshelf, and reading progress to sessions

**Files:**
- Modify: `epub_browser/server.py`
- Modify: `epub_browser/state.py`
- Modify: `epub_browser/assets/annotation.js`
- Modify: `epub_browser/assets/bookshelf.js`
- Modify: `epub_browser/assets/reading-progress.js`
- Modify: `tests/test_server.py`
- Modify: `tests/test_annotation.js`
- Modify: `tests/test_reading_progress.js`

**Consumes:** `require_principal` from Task 4 and user-ID scoped StateStore methods from Task 2.

**Produces:** all existing personal-data APIs use session ownership and client code sends CSRF instead of usernames.

- [ ] **Step 1: Write failing impersonation and client-request tests**

```python
def test_annotation_header_cannot_impersonate_another_account(self):
    self.login('alice')
    response = self.client.post('/api/annotations/book', json=self.annotation,
                                headers={'X-Username': 'bob', **self.csrf})
    self.assertEqual(response.status_code, 201)
    self.assertEqual(self.store.list_annotations(user_id=self.alice.user_id)[0]['id'], self.annotation['id'])
    self.assertEqual(self.store.list_annotations(user_id=self.bob.user_id), [])
```

```javascript
test('server progress uses Cookie authentication and CSRF, never X-Username', async () => {
  const received = await requestProgressAsServer();
  assert.equal(received.credentials, 'same-origin');
  assert.equal(received.headers['X-Username'], undefined);
  assert.equal(received.headers['X-CSRF-Token'], 'csrf');
});
```

- [ ] **Step 2: Run tests and verify failure**

Run: `python3 -m unittest tests.test_server.SessionOwnershipTests && node --test tests/test_annotation.js tests/test_reading_progress.js`

Expected: FAIL because handlers and browser scripts still use `X-Username` and body `username`.

- [ ] **Step 3: Rewire every personal-data API to the principal**

```python
principal = require_principal(request)
store.upsert_annotation(data, user_id=principal.user_id)
payload, status = sync_bookshelf(..., user_id=principal.user_id, store=store)
chapter_index = store.get_reading_progress(principal.user_id, book_hash)
```

Delete username extraction from the annotation, sync, and reading-progress
handlers. For the legacy JSON bookshelf input, ignore any supplied `username`;
do not echo it in responses. Update browser modules to use a shared
`EpubBrowserAuth.fetch` wrapper with `credentials: 'same-origin'` and its CSRF
header. Keep SSG paths on local IndexedDB/local storage and make them avoid the
wrapper entirely.

- [ ] **Step 4: Run focused suites**

Run: `python3 -m unittest tests.test_server.SessionOwnershipTests tests.test_state && node --test tests/test_annotation.js tests/test_reading_progress.js tests/test_bookshelf.js`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add epub_browser/server.py epub_browser/state.py epub_browser/assets/annotation.js epub_browser/assets/bookshelf.js epub_browser/assets/reading-progress.js tests/test_server.py tests/test_state.py tests/test_annotation.js tests/test_reading_progress.js tests/test_bookshelf.js
git commit -m "feat: scope Server reading data to authenticated accounts"
```

### Task 7: Enforce restricted-book visibility in catalog and direct resources

**Files:**
- Modify: `epub_browser/server.py`
- Modify: `epub_browser/server_library.py`
- Modify: `epub_browser/state.py`
- Modify: `tests/test_server.py`
- Modify: `tests/test_server_library.py`

**Consumes:** `visible_books` and `can_read_book` from Task 2, authenticated principal from Task 4.

**Produces:** account-filtered metadata, protected reader/assets, and book grant administration primitives used by Task 8.

- [ ] **Step 1: Write failing catalog and direct-route authorization tests**

```python
def test_member_cannot_discover_or_open_restricted_book_by_direct_resource_url(self):
    self.store.set_book_visibility('restricted-id', 'restricted')
    response = self.member_client.get('/api/library-metadata')
    self.assertNotIn('restricted-id', {book['hash'] for book in response.json()})
    self.assertEqual(self.member_client.get('/book/restricted-id/chapter_0.html').status_code, 403)
    self.assertEqual(self.member_client.get('/book/restricted-id/resources/image.jpg').status_code, 403)

def test_grant_allows_member_catalog_and_reader_access(self):
    self.store.grant_book_access('restricted-id', self.member.user_id)
    self.assertEqual(self.member_client.get('/book/restricted-id/chapter_0.html').status_code, 200)
```

- [ ] **Step 2: Run tests and verify failure**

Run: `python3 -m unittest tests.test_server.BookAuthorizationTests`

Expected: FAIL because the static mount and catalog expose every generated book.

- [ ] **Step 3: Replace unrestricted book serving with an authorization-aware route**

```python
async def protected_public_file(request):
    principal = require_principal(request)
    book_id = extract_book_id_from_public_path(request.path_params['path'])
    if book_id and not store.can_read_book(principal.user_id, principal.role, book_id):
        return response(error_payload('forbidden', 'Forbidden'), 403)
    return cached_file_response(base_directory, request.path_params['path'])
```

Serve public files through a path-normalizing route rather than a bypassing
static mount. Preserve immutable/cache headers only after authorization and
prevent path traversal. Filter any library metadata generated or refreshed for
the requesting principal; never write a user-specific filtered catalog to the
shared public directory. Add administrator routes to set visibility and modify
grants, with validation that `book_id` exists and user ID is enabled.

- [ ] **Step 4: Run authorization and library suites**

Run: `python3 -m unittest tests.test_server.BookAuthorizationTests tests.test_server_library`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add epub_browser/server.py epub_browser/server_library.py epub_browser/state.py tests/test_server.py tests/test_server_library.py
git commit -m "feat: enforce Server book visibility grants"
```

### Task 8: Build the localized Server account and administration interfaces

**Files:**
- Create: `epub_browser/assets/auth.js`
- Modify: `epub_browser/site.py`
- Modify: `epub_browser/assets/i18n.js`
- Modify: `epub_browser/assets/library.js`
- Modify: `epub_browser/assets/bookshelf.js`
- Modify: `epub_browser/assets/annotation.js`
- Modify: `epub_browser/assets/reading-progress.js`
- Modify: `tests/test_generated_reader_surfaces.py`
- Modify: `tests/test_i18n_coverage.py`
- Create: `tests/test_auth_ui.js`

**Consumes:** routes and JSON contracts from Tasks 4–7.

**Produces:** Server-only login/account/admin controls and the shared browser `EpubBrowserAuth` API.

- [ ] **Step 1: Write failing rendered-surface and JavaScript tests**

```python
def test_server_includes_real_account_controls_but_ssg_includes_none(self):
    self.assertIn('id="loginForm"', self._server_html())
    self.assertIn('id="accountMenu"', self._server_html())
    self.assertNotIn('loginForm', self._ssg_html())
    self.assertNotIn('accountMenu', self._ssg_html())
```

```javascript
test('auth wrapper attaches CSRF and redirects only after a 401 response', async () => {
  const result = await authFetch('/api/account/sessions', { method: 'DELETE' });
  assert.equal(result.options.headers['X-CSRF-Token'], 'token');
  assert.equal(location.pathname, '/login');
});
```

- [ ] **Step 2: Run tests and verify failure**

Run: `python3 -m unittest tests.test_generated_reader_surfaces.GeneratedReaderSurfaceTests.test_server_includes_real_account_controls_but_ssg_includes_none && node --test tests/test_auth_ui.js`

Expected: FAIL because these surfaces and module do not exist.

- [ ] **Step 3: Render only Server account UI and implement client behavior**

```javascript
window.EpubBrowserAuth = {
  fetch: function(url, options) {
    return fetch(url, withCsrfAndSameOriginCredentials(options)).then(handleUnauthorized);
  },
  session: function() { return this.fetch('/api/session'); },
  logout: function() { return this.fetch('/logout', {method: 'POST'}); }
};
```

Generate login, account settings, and administrator surfaces only when
`deployment_mode == 'server'`. Give every control an i18n key in both locales,
including error, restricted-book, association, password-reset, and session
revocation messages. Remove the old username prompt and Sync identity UI in
Server mode. Preserve existing SSG no-login/no-sync behavior and make UI code
return before any auth initialization in SSG.

- [ ] **Step 4: Run UI and localization tests**

Run: `python3 -m unittest tests.test_generated_reader_surfaces tests.test_i18n_coverage && node --test tests/test_auth_ui.js tests/test_annotation.js tests/test_reading_progress.js`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add epub_browser/site.py epub_browser/assets/auth.js epub_browser/assets/i18n.js epub_browser/assets/library.js epub_browser/assets/bookshelf.js epub_browser/assets/annotation.js epub_browser/assets/reading-progress.js tests/test_generated_reader_surfaces.py tests/test_i18n_coverage.py tests/test_auth_ui.js
git commit -m "feat: add localized Server account controls"
```

### Task 9: Add one-time setup, optional unattended bootstrap, and secure deployment guidance

**Files:**
- Modify: `epub_browser/runtime.py`
- Modify: `epub_browser/state.py`
- Modify: `epub_browser/auth.py`
- Modify: `epub_browser/server.py`
- Modify: `epub_browser/assets/i18n.js`
- Modify: `Dockerfile`
- Modify: `README.md`
- Modify: `docs/migration-v2.md`
- Modify: `docs/superpowers/specs/2026-08-19-server-account-system-design.md`
- Modify: `tests/test_runtime.py`
- Modify: `tests/test_state.py`
- Modify: `tests/test_auth.py`
- Modify: `tests/test_server.py`
- Modify: `tests/test_migration.py`

**Consumes:** `BootstrapCredentials`, `AuthConfig`, and `create_app(..., auth_service=...)` from Tasks 1–4.

**Produces:** a deployment-ready web-first setup boundary, optional fail-closed
unattended bootstrap, stable legacy-data ownership, and complete secure
deployment documentation.

- [ ] **Step 1: Write failing pending-administrator and atomic setup tests**

```python
def test_legacy_data_moves_to_pending_administrator_then_setup_keeps_id(self):
    pending = store.initialize()
    assert not store.has_administrator()
    completed = store.initialize(BootstrapCredentials('owner', 'secret'))
    assert completed.user_id == pending.user_id

def test_setup_activation_and_initial_session_are_one_transaction(self):
    # Inject a duplicate session digest and verify activation rolls back too.
```

- [ ] **Step 2: Implement pending identity and atomic setup completion**

Create exactly one disabled, passwordless pending administrator when no
completed administrator exists. It has a generated stable user ID and does not
make `has_administrator()` true. Assign all legacy annotations, bookshelf rows,
and progress to it. Web and unattended setup update its username, Argon2id
password hash, enabled flag, and pending marker in place. Web setup inserts the
initial session digest in the same `BEGIN IMMEDIATE` transaction so concurrent
claims have exactly one winner.

- [ ] **Step 3: Write and implement the in-process setup-only HTTP boundary**

Add a localized English/Simplified Chinese `GET /setup` page with username,
password, confirmation, and locale fields, plus `POST /setup`. Before setup is
complete:

- normal HTML redirects to `/setup`;
- APIs, SSE, book resources, and generated static assets return `503` with a
  setup-required error and no content;
- health/readiness return only `{"status":"setup_required"}`;
- only the fixed setup/login JavaScript and i18n assets are public;
- trusted-proxy headers are not evaluated and cannot claim setup.

Validate submitted username/password/confirmation without returning or logging
the password. Protect the claim with a high-entropy hidden nonce and matching
short-lived `HttpOnly`, `SameSite=Strict` cookie, checked with
`compare_digest`. Validate Origin against Host and reject non-same-origin
`Sec-Fetch-Site` values with the same generic response regardless of setup
state. Clear the setup cookie after success or setup-complete. A successful
claim creates the session cookie and redirects to the library; losing
concurrent claims redirect through login. GET and HEAD render setup (HEAD has no
body) instead of entering form parsing.

- [ ] **Step 4: Make runtime web-first while retaining unattended setup**

When no credential source is configured, initialize the pending administrator
and start setup-only mode normally. Keep the public shell inaccessible, do not
scan EPUBs, and do not start the watcher until `has_administrator()` becomes true. If any unattended
credential source is configured, require a complete valid username/password
pair and fail closed otherwise. Prefer the password file, remove exactly one
trailing newline, never report its contents, and complete a pending row in
place. Completed restarts do not read any configured secret. Construct the real
`AuthConfig`/`AuthService` with trusted-proxy and secure-cookie options. Disable
Uvicorn proxy-header processing so trusted-proxy CIDRs always evaluate the
direct socket peer, never a forwarded client address. Start the watcher only
after an explicit successful administrator observation; a polling error must
not be treated like completed setup.

Before changing an existing authoritative `data/epub-browser.db` from an older
supported schema, run its integrity check and create a digest- and
integrity-verified backup under `data/backups/` using the migration naming
convention. Stop before schema mutation on any backup failure, preserve a
restorable prior-schema copy, and avoid repeated backups on current-schema
restarts.

- [ ] **Step 5: Update deployment and migration guidance**

Prefer web setup for interactive README, Docker, and migration examples. Warn
that the first visitor can claim setup: keep the port private until completion,
or mount a secret for unattended deployment. Retain persistent data volume,
`--watch`, TLS termination, secure-cookie, and direct-proxy CIDR/header boundary
instructions.

- [ ] **Step 6: Run focused and full verification**

Run: `python3 -m unittest tests.test_state tests.test_auth tests.test_server tests.test_runtime tests.test_migration tests.test_cli tests.test_mode_integration`

Run: `python3 -m unittest discover -s tests -p 'test_*.py'`

Run: `node --test tests/test_*.js`

Expected: PASS, with no browser E2E.

- [ ] **Step 7: Commit**

```bash
git add epub_browser/state.py epub_browser/auth.py epub_browser/server.py epub_browser/runtime.py epub_browser/assets/i18n.js tests/test_state.py tests/test_auth.py tests/test_server.py tests/test_runtime.py tests/test_migration.py Dockerfile README.md docs/migration-v2.md docs/superpowers/specs/2026-08-19-server-account-system-design.md docs/superpowers/plans/2026-08-19-server-account-system.md
git commit -m "feat: add one-time Server administrator setup"
```

### Task 10: Run the security regression matrix and release checks

**Files:**
- Modify: `tests/test_server.py`
- Test: full `tests/` Python and Node suites.

**Consumes:** All preceding tasks.

**Produces:** a verified account-system branch with no SSG or existing Server lifecycle regressions.

- [ ] **Step 1: Add one in-process ASGI security matrix test**

```python
def test_member_lifecycle_from_login_to_restricted_book_revocation(self):
    self.login_admin()
    self.create_member('reader', 'initial-password')
    self.restrict_book('restricted-id')
    self.assertEqual(self.login_member('reader', 'initial-password').get('/book/restricted-id/chapter_0.html').status_code, 403)
    self.grant_book('restricted-id', 'reader')
    self.assertEqual(self.member.get('/book/restricted-id/chapter_0.html').status_code, 200)
    self.disable_user('reader')
    self.assertEqual(self.member.get('/api/session').status_code, 401)
```

- [ ] **Step 2: Run the matrix test and verify it passes**

Run: `python3 -m unittest tests.test_server.ServerAccountSecurityMatrixTests`

Expected: PASS.

- [ ] **Step 3: Run Python, JavaScript, static, and whitespace checks**

Run: `python3 -m unittest discover -s tests -p 'test_*.py'`

Run: `node --test tests/test_*.js`

Run: `python3 -m compileall -q epub_browser`

Run: `git diff --check main~10..HEAD`

Expected: every command exits 0.

- [ ] **Step 4: Review auth-specific negative cases before commit**

```text
Verify with explicit tests that: an X-Username header cannot change ownership;
an untrusted forwarded header cannot log in; a disabled user cannot use an old
cookie; an unauthorized direct cover/resource URL is 403; SSG output includes
no login/account control; and logs/errors do not contain bootstrap password or
raw session tokens.
```

- [ ] **Step 5: Commit the matrix test or narrowly-scoped fixes**

```bash
git add tests/test_server.py
git commit -m "test: cover Server account security lifecycle"
```

Do not combine unrelated formatting changes with this final commit.
