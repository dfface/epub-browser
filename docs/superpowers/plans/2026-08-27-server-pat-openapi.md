# Server PAT and OpenAPI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add scoped account PATs and a versioned external API for library content and account-owned reading data, with administrator cross-user read access.

**Architecture:** Keep browser Cookie + CSRF APIs unchanged and add a Bearer-only `/api/v1/*` surface. `pat.py` owns token primitives, `public_api.py` owns the external contract, and both reuse `StateStore`, `ServerPageRenderer`, and existing book ACLs.

**Tech Stack:** Python 3.9, SQLite, Starlette, native JavaScript/CSS, unittest, Node test runner, OpenAPI 3.1.

**Spec:** `docs/superpowers/specs/2026-08-27-server-pat-openapi-webhooks-design.md`

## Global Constraints

- PATs authenticate only `/api/v1/*`; browser Cookies authenticate only the existing browser routes.
- Raw PATs are returned once and never persisted; SQLite stores a SHA-256 digest and indexed public ID.
- Supported scopes are exactly `library:read`, `bookshelf:read`, `bookshelf:write`, `progress:read`, `progress:write`, `annotations:read`, `annotations:write`, `reviews:read`, `reviews:write`, and `admin:data:read`.
- External administrator access is read-only and excludes every credential, digest, provider key, and WebHook secret.
- Chapter access performs current book ACL checks before reading Server content cache.
- Python remains compatible with 3.9; do not add a CDN or runtime network dependency.
- All visible copy covers en, zh-CN, zh-TW, ko, and ja.
- Do not raise `SERVER_OUTPUT_REVISION`; SSG must contain no PAT UI or `/api/v1` dependency.

## File Structure

| File | Responsibility |
| --- | --- |
| `epub_browser/pat.py` | PAT format, digest, authentication result, scope validation. |
| `epub_browser/public_api.py` | Bearer middleware helpers, route declarations, handlers, OpenAPI document. |
| `epub_browser/state.py` | v16 PAT tables and token/query persistence. |
| `epub_browser/auth.py` | Password reauthentication and account lifecycle coordination. |
| `epub_browser/server.py` | Internal PAT-management routes and external route mounting. |
| `epub_browser/server_chrome.py` | Server-only Account PAT markup. |
| `epub_browser/assets/auth.js` | PAT list/create/copy/revoke interaction. |
| `epub_browser/assets/account.css` | Responsive PAT controls and states. |
| `epub_browser/assets/i18n.js` | Five-locale PAT and API copy. |
| `tests/test_pat.py` | PAT primitive and scope tests. |
| `tests/test_state.py` | v16 schema, migration, lifecycle, and paginated read APIs. |
| `tests/test_public_api.py` | Bearer boundary, public resources, ACL, and OpenAPI contract. |
| `tests/test_auth_ui.js` | Account PAT interaction tests. |
| `tests/test_generated_reader_surfaces.py` | Dynamic Server and SSG boundary assertions. |
| `tests/test_i18n_coverage.py` | Locale key coverage. |

### Task 1: Add PAT primitives and v16 token persistence

**Files:**
- Create: `epub_browser/pat.py`
- Create: `tests/test_pat.py`
- Modify: `epub_browser/state.py`
- Modify: `tests/test_state.py`

**Interfaces:**
- Produces `PAT_SCOPES`, `PAT_WRITE_REQUIRES`, `PersonalAccessToken`, `IssuedPersonalAccessToken`, `AuthenticatedPAT`, `generate_pat()`, `pat_digest()`, and `normalize_scopes()`.
- Produces `StateStore.create_personal_access_token`, `list_personal_access_tokens`, `authenticate_personal_access_token`, `revoke_personal_access_token`, and `revoke_all_personal_access_tokens`.

- [ ] **Step 1: Write failing primitive and schema tests**

```python
def test_generate_pat_returns_once_visible_high_entropy_secret(self):
    raw, public_id, digest = generate_pat()
    self.assertTrue(raw.startswith("epub_pat_" + public_id + "_"))
    self.assertEqual(pat_digest(raw), digest)
    self.assertNotIn(raw, repr(digest))

def test_v16_pat_schema_and_round_trip(self):
    issued = self.store.create_personal_access_token(
        self.member.user_id, "Reader sync", {"library:read"}, expires_at=None
    )
    self.assertEqual(self.store.authenticate_personal_access_token(issued.raw_token).token_id, issued.token.id)
    self.assertNotIn(issued.raw_token, self.store.raw_personal_access_token_rows())
```

- [ ] **Step 2: Run tests and verify the intended failure**

Run: `python3 -m unittest tests.test_pat tests.test_state -v`

Expected: FAIL because `epub_browser.pat` and v16 PAT methods do not exist.

- [ ] **Step 3: Implement primitives, schema, and persistence**

```python
PAT_SCOPES = frozenset({
    "library:read", "bookshelf:read", "bookshelf:write",
    "progress:read", "progress:write", "annotations:read",
    "annotations:write", "reviews:read", "reviews:write",
    "admin:data:read",
})
PAT_WRITE_REQUIRES = {
    "bookshelf:write": "bookshelf:read",
    "progress:write": "progress:read",
    "annotations:write": "annotations:read",
    "reviews:write": "reviews:read",
}
```

Raise `DB_SCHEMA_VERSION` to 16. Add `personal_access_tokens` with token ID, unique public ID, unique digest, user FK, name, canonical scope JSON, optional expiration, last use, revocation, and timestamps. Add owner and active-lookup indexes. Integrate `_migrate_schema_v16()` into every initialization path and keep fresh/v15 schemas identical.

- [ ] **Step 4: Run focused tests**

Run: `python3 -m unittest tests.test_pat tests.test_state -v`

Expected: PASS, including v15-to-v16 and fresh schema assertions.

- [ ] **Step 5: Commit**

```bash
git add epub_browser/pat.py epub_browser/state.py tests/test_pat.py tests/test_state.py
git commit -m "feat: add scoped personal access token state"
```

### Task 2: Enforce PAT account lifecycle and internal management APIs

**Files:**
- Modify: `epub_browser/state.py`
- Modify: `epub_browser/server.py`
- Modify: `tests/test_auth.py`
- Modify: `tests/test_server.py`

**Interfaces:**
- Consumes Task 1 PAT methods.
- Produces Cookie + CSRF routes `GET/POST /api/account/pats` and `DELETE /api/account/pats/{token_id}`.

- [ ] **Step 1: Write failing lifecycle and route tests**

```python
def test_admin_reset_revokes_pats_but_self_password_change_keeps_them(self):
    token = self.issue_pat(self.member)
    self.change_own_password(self.member_client)
    self.assertIsNotNone(self.store.authenticate_personal_access_token(token))
    self.admin_reset_password("member")
    self.assertIsNone(self.store.authenticate_personal_access_token(token))

def test_pat_creation_requires_current_password_and_csrf(self):
    denied = self.client.post("/api/account/pats", json=self.pat_payload())
    self.assertEqual(denied.status_code, 403)
    created = self.authenticated_post("/api/account/pats", self.pat_payload(password="secret"))
    self.assertEqual(created.status_code, 201)
    self.assertIn("token", created.json())
```

- [ ] **Step 2: Run tests and verify failure**

Run: `python3 -m unittest tests.test_auth tests.test_server -v`

Expected: FAIL because PAT routes and lifecycle revocation are absent.

- [ ] **Step 3: Implement lifecycle and management handlers**

Validate names as trimmed 1–80 character strings, expirations as 30/90/180/365 days or `null`, and admin scope against the current role. Reauthenticate the current password through `AuthService.authenticate_password`. Return the raw token only from the successful POST. Extend administrator reset and user disable paths to revoke PATs in the same state transaction; leave PATs intact on self password change.

- [ ] **Step 4: Run focused tests**

Run: `python3 -m unittest tests.test_auth tests.test_server -v`

Expected: PASS with existing Session and CSRF regressions unchanged.

- [ ] **Step 5: Commit**

```bash
git add epub_browser/state.py epub_browser/server.py tests/test_auth.py tests/test_server.py
git commit -m "feat: manage account personal access tokens"
```

### Task 3: Build the Account PAT interface and five-locale copy

**Files:**
- Modify: `epub_browser/server_chrome.py`
- Modify: `epub_browser/assets/auth.js`
- Modify: `epub_browser/assets/account.css`
- Modify: `epub_browser/assets/i18n.js`
- Modify: `tests/test_auth_ui.js`
- Modify: `tests/test_generated_reader_surfaces.py`
- Modify: `tests/test_i18n_coverage.py`

**Interfaces:**
- Consumes Task 2 PAT management routes.
- Produces account controls `patList`, `patCreateForm`, `patCreatedSecret`, and `patLive`.

- [ ] **Step 1: Write failing generated-surface and interaction tests**

```javascript
test('PAT creation shows the secret once and never stores it', async () => {
  const ui = buildAuthUI({patCreateResponse: {token: 'epub_pat_public_secret'}});
  await ui.submitPAT();
  assert.equal(ui.secret.textContent, 'epub_pat_public_secret');
  assert.equal(ui.localStorageWrites.length, 0);
  ui.closeAccountPanel();
  assert.equal(ui.secret.textContent, '');
});
```

Add Python surface assertions that Server markup contains PAT controls while SSG markup contains neither PAT controls nor `/api/account/pats`.

- [ ] **Step 2: Run tests and verify failure**

Run: `node --test tests/test_auth_ui.js && python3 -m unittest tests.test_generated_reader_surfaces tests.test_i18n_coverage -v`

Expected: FAIL on missing controls and translation keys.

- [ ] **Step 3: Implement accessible responsive PAT UI**

Use labelled fields, a checkbox group for scopes, a native expiration select including never, inline help for `admin:data:read`, an explicit copy button, status text with `aria-live`, visible keyboard focus, 44px minimum targets, disabled/loading states, and a confirmation before revocation. Clear the raw secret on panel close and on the next creation attempt.

- [ ] **Step 4: Run UI and locale tests**

Run: `node --test tests/test_auth_ui.js && python3 -m unittest tests.test_generated_reader_surfaces tests.test_i18n_coverage -v`

Expected: PASS in all five locale dictionaries and both deployment modes.

- [ ] **Step 5: Commit**

```bash
git add epub_browser/server_chrome.py epub_browser/assets/auth.js epub_browser/assets/account.css epub_browser/assets/i18n.js tests/test_auth_ui.js tests/test_generated_reader_surfaces.py tests/test_i18n_coverage.py
git commit -m "feat: add PAT account interface"
```

### Task 4: Add Bearer-only public API infrastructure and contract declarations

**Files:**
- Create: `epub_browser/public_api.py`
- Create: `tests/test_public_api.py`
- Modify: `epub_browser/server.py`

**Interfaces:**
- Produces `PublicAPIOperation`, `public_api_routes(context)`, `openapi_document()`, `require_pat(request, scope)`, `cursor_page()`, and `public_api_error()`.
- Consumes Task 1 token authentication.

- [ ] **Step 1: Write failing authentication-boundary and contract tests**

```python
def test_cookie_cannot_authenticate_v1_and_pat_cannot_authenticate_browser_api(self):
    self.assertEqual(self.cookie_client.get("/api/v1/books").status_code, 401)
    self.assertEqual(self.client.get("/api/session", headers=self.bearer()).status_code, 401)

def test_every_v1_route_has_one_openapi_operation_with_matching_scope(self):
    operations = operation_index(openapi_document())
    for route in public_api_routes(self.context):
        self.assertEqual(operations[(route.path, route.methods)], route.required_scope)
```

- [ ] **Step 2: Run tests and verify failure**

Run: `python3 -m unittest tests.test_public_api -v`

Expected: FAIL because the public API module is absent.

- [ ] **Step 3: Implement the route declaration and Bearer boundary**

Parse exactly one Bearer credential, reject Cookie-only requests, authenticate through the indexed public ID and digest, enforce account enabled/role/expiry/revocation/scope, and update `last_used_at` at most once per five minutes. Register v1 routes ahead of the browser catch-all. Keep the common 401/403/404/validation envelope and bounded opaque cursor helpers in this module.

- [ ] **Step 4: Run infrastructure tests**

Run: `python3 -m unittest tests.test_public_api tests.test_server -v`

Expected: PASS without changing existing browser authentication behavior.

- [ ] **Step 5: Commit**

```bash
git add epub_browser/public_api.py epub_browser/server.py tests/test_public_api.py
git commit -m "feat: add versioned Bearer API boundary"
```

### Task 5: Publish library, TOC, HTML, and text chapter operations

**Files:**
- Modify: `epub_browser/public_api.py`
- Modify: `epub_browser/server_pages.py`
- Modify: `tests/test_public_api.py`

**Interfaces:**
- Produces the four `library:read` operations defined in the spec.
- Adds `ServerPageRenderer.chapter_content(chapter_index) -> dict` without exposing cache paths.

- [ ] **Step 1: Write failing catalog and chapter ACL tests**

```python
def test_chapter_supports_sanitized_html_and_plain_text(self):
    html = self.get_v1("/api/v1/books/book-1/chapters/0", scope="library:read")
    text = self.get_v1("/api/v1/books/book-1/chapters/0?format=text", scope="library:read")
    self.assertEqual(html.status_code, 200)
    self.assertIn("<p>", html.json()["content_html"])
    self.assertEqual(text.headers["content-type"].split(";")[0], "text/plain")

def test_restricted_chapter_is_404_before_cache_read(self):
    with mock.patch.object(ServerPageRenderer, "chapter_content") as read:
        response = self.member_get("/api/v1/books/restricted/chapters/0")
    self.assertEqual(response.status_code, 404)
    read.assert_not_called()
```

- [ ] **Step 2: Run tests and verify failure**

Run: `python3 -m unittest tests.test_public_api.PublicLibraryAPITests -v`

Expected: FAIL on missing handlers.

- [ ] **Step 3: Implement catalog and chapter handlers**

Reuse active-book metadata and `store.can_read_book`. Return normalized metadata and TOC only after authorization. Restore cached chapter JSON through `ServerPageRenderer`, return sanitized HTML in JSON by default, and use the same text extraction used by Server AI/content helpers for `format=text`. Reject every other format with a documented validation error.

- [ ] **Step 4: Run catalog tests**

Run: `python3 -m unittest tests.test_public_api.PublicLibraryAPITests tests.test_server_library -v`

Expected: PASS for ordinary, restricted, missing, malformed-cache, HTML, and text paths.

- [ ] **Step 5: Commit**

```bash
git add epub_browser/public_api.py epub_browser/server_pages.py tests/test_public_api.py
git commit -m "feat: expose authorized library and chapter API"
```

### Task 6: Add scoped token-owner reading-data operations

**Files:**
- Modify: `epub_browser/state.py`
- Modify: `epub_browser/public_api.py`
- Modify: `tests/test_state.py`
- Modify: `tests/test_public_api.py`

**Interfaces:**
- Produces `/api/v1/me` bookshelf, progress, annotation, and review operations.
- Adds bounded, cursor-paginated StateStore list methods with explicit `user_id`.

- [ ] **Step 1: Write failing scope and ownership tests**

```python
def test_annotations_write_cannot_choose_another_owner(self):
    payload = self.annotation_payload(user_id=self.other.user_id)
    created = self.post_v1("/api/v1/me/annotations", payload, scopes={"annotations:read", "annotations:write"})
    self.assertEqual(created.status_code, 201)
    self.assertEqual(self.store.get_annotation(created.json()["annotation"]["id"], self.member.user_id)["text"], payload["text"])
    self.assertIsNone(self.store.get_annotation(created.json()["annotation"]["id"], self.other.user_id))

def test_write_scope_without_read_scope_is_rejected_at_creation(self):
    response = self.create_pat(scopes={"reviews:write"})
    self.assertEqual(response.status_code, 400)
```

- [ ] **Step 2: Run tests and verify failure**

Run: `python3 -m unittest tests.test_public_api.PublicPersonalDataAPITests tests.test_state -v`

Expected: FAIL on missing v1 handlers and paginated state queries.

- [ ] **Step 3: Implement personal operations**

Reuse existing bookshelf optimistic versioning, annotation field validation, progress chapter bounds, and review limits. Ignore or reject owner fields in request bodies; ownership always comes from the PAT principal. Apply the book ACL to every book-bound operation and use private, no-store responses.

- [ ] **Step 4: Run personal-data tests**

Run: `python3 -m unittest tests.test_public_api.PublicPersonalDataAPITests tests.test_state tests.test_server -v`

Expected: PASS with browser routes unchanged.

- [ ] **Step 5: Commit**

```bash
git add epub_browser/state.py epub_browser/public_api.py tests/test_state.py tests/test_public_api.py
git commit -m "feat: expose scoped personal reading APIs"
```

### Task 7: Add administrator cross-user read operations

**Files:**
- Modify: `epub_browser/state.py`
- Modify: `epub_browser/public_api.py`
- Modify: `tests/test_state.py`
- Modify: `tests/test_public_api.py`

**Interfaces:**
- Produces the nine `/api/v1/admin/users*` read-only operations in the spec.
- Adds paginated user-owned reads for sessions, insights, AI conversations, and AI results.

- [ ] **Step 1: Write failing role, secret-exclusion, and read-only tests**

```python
def test_admin_data_scope_reads_full_review_but_never_credentials(self):
    response = self.admin_get("/api/v1/admin/users/{}/reviews".format(self.member.user_id))
    self.assertEqual(response.json()["items"][0]["review_text"], "private notes")
    serialized = json.dumps(response.json())
    self.assertNotIn("password_hash", serialized)
    self.assertNotIn("token_digest", serialized)

def test_admin_namespace_registers_get_only(self):
    self.assertEqual(self.admin_put("/api/v1/admin/users/{}/reviews".format(self.member.user_id), {}).status_code, 405)
```

- [ ] **Step 2: Run tests and verify failure**

Run: `python3 -m unittest tests.test_public_api.PublicAdminDataAPITests -v`

Expected: FAIL on missing admin read handlers.

- [ ] **Step 3: Implement paginated administrator reads**

Require both a current administrator role and `admin:data:read`. Serialize explicit allowlisted fields for users, bookshelf, progress, annotations, full reviews, reading sessions/insights, AI conversations, and results. Never return raw provider requests containing credentials or any authentication table fields.

- [ ] **Step 4: Run administrator API tests**

Run: `python3 -m unittest tests.test_public_api.PublicAdminDataAPITests tests.test_ai_reading tests.test_state -v`

Expected: PASS for admin, demoted admin, member, disabled account, pagination, and secret exclusion.

- [ ] **Step 5: Commit**

```bash
git add epub_browser/state.py epub_browser/public_api.py tests/test_state.py tests/test_public_api.py
git commit -m "feat: add administrator data read API"
```

### Task 8: Publish self-contained OpenAPI docs and verify mode boundaries

**Files:**
- Modify: `epub_browser/public_api.py`
- Modify: `epub_browser/server.py`
- Modify: `epub_browser/asset_publisher.py`
- Create: `epub_browser/assets/api-docs.js`
- Create: `epub_browser/assets/api-docs.css`
- Modify: `tests/test_public_api.py`
- Modify: `tests/test_static_asset_delivery.py`
- Modify: `tests/test_mode_integration.py`
- Modify: `README.md`
- Modify: `docs/readme/README.zh-CN.md`

**Interfaces:**
- Produces `/openapi.json` and `/api-docs` after setup.

- [ ] **Step 1: Write failing schema, documentation, and SSG tests**

```python
def test_openapi_is_31_and_documents_all_security_scopes(self):
    document = self.client.get("/openapi.json").json()
    self.assertEqual(document["openapi"], "3.1.0")
    self.assertEqual(set(document["components"]["securitySchemes"]["PATBearer"]["x-scopes"]), PAT_SCOPES)

def test_ssg_never_contains_external_api_runtime(self):
    output = self.render_ssg()
    self.assertNotIn("/api/v1", output)
    self.assertNotIn("personal access token", output.lower())
```

- [ ] **Step 2: Run tests and verify failure**

Run: `python3 -m unittest tests.test_public_api tests.test_static_asset_delivery tests.test_mode_integration -v`

Expected: FAIL on missing schema and local documentation assets.

- [ ] **Step 3: Implement OpenAPI document and local docs page**

Generate the document from `PublicAPIOperation` declarations. Allow `/openapi.json` without authentication only after initial setup because it contains no account or library data; keep `/api-docs` behind the normal browser Session. Render a local, searchable operation list with request/response schemas, scope badges, and an in-memory-only Bearer field; never persist the token or include it in a URL. Document setup, curl examples, scope selection, chapter formats, pagination, and administrator read boundaries in both READMEs.

- [ ] **Step 4: Run complete PAT/OpenAPI verification**

Run: `python3 -m unittest tests.test_pat tests.test_auth tests.test_state tests.test_public_api tests.test_server tests.test_server_library tests.test_generated_reader_surfaces tests.test_i18n_coverage tests.test_static_asset_delivery tests.test_mode_integration -v`

Run: `node --test tests/test_auth_ui.js`

Run: `python3 -m compileall -q epub_browser && git diff --check`

Expected: all commands PASS.

- [ ] **Step 5: Commit**

```bash
git add epub_browser/public_api.py epub_browser/server.py epub_browser/asset_publisher.py epub_browser/assets/api-docs.js epub_browser/assets/api-docs.css tests/test_public_api.py tests/test_static_asset_delivery.py tests/test_mode_integration.py README.md docs/readme/README.zh-CN.md
git commit -m "docs: publish self-contained OpenAPI reference"
```
