# Server OIDC Login Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add one administrator-configured generic OIDC Provider with safe existing-account binding, optional member provisioning, local-admin recovery, polished localized UI, and a real Authelia end-to-end test.

**Architecture:** A new `OIDCService` performs discovery, Authorization Code + PKCE, callback validation, and bounded Provider communication. `StateStore` owns settings, one-time transactions, external identities, and atomic provisioning; successful OIDC authentication always becomes the existing opaque EPUB Browser session and `Principal`.

**Tech Stack:** Python 3.9+, Starlette, SQLite, Authlib 1.6.11, HTTPX, vanilla JavaScript/CSS, Node test runner, Docker Compose, Authelia, Playwright container.

**Spec:** `docs/superpowers/specs/2026-08-29-server-oidc-login-design.md`

## Global Constraints

- OIDC exists only in Server mode; SSG must emit no OIDC routes, UI, state, or network dependencies.
- Support one generic configurable Provider; use exact `(issuer, subject)` identity and never bind by username or email.
- Automatically provision only passwordless `member` accounts; no claim may grant `admin`.
- Local administrator password login always remains available.
- Use Authorization Code Flow, S256 PKCE, state, nonce, exact issuer/audience validation, and a browser-binding cookie.
- Do not persist Provider access or refresh tokens and never expose secrets, codes, raw claims, nonce, state, or PKCE material in logs or API responses.
- Constrain Authlib to `Authlib>=1.6.11,<1.7` so Python 3.9 remains supported; add compatible `httpx>=0.27,<1.0`.
- OIDC configuration updates are validated before atomic replacement and take effect without book reconversion.
- All visible text and dynamic DOM must use the existing complete locale catalogue and update in place on locale change.
- UI target is WCAG 2.2 AA: visible labels/focus, 44px controls, loading and error feedback, keyboard access, 200% zoom, 375px reflow, light/dark parity, and reduced-motion support.
- Do not change EPUB or PDF content-cache revisions.

## File responsibility map

- Create `epub_browser/oidc.py`: OIDC records, validation errors, discovery/JWKS client, authorization start, and callback completion.
- Modify `epub_browser/state.py`: schema v20 tables and transactional settings/identity/login-transaction operations.
- Modify `epub_browser/auth.py`: local-login policy hook and local-session creation from an already resolved principal.
- Modify `epub_browser/runtime.py`: construct and close the shared OIDC service.
- Modify `epub_browser/server.py`: public OIDC flow routes and authenticated/admin APIs; no low-level JOSE logic.
- Modify `epub_browser/server_chrome.py`: admin OIDC tab and account identity markup.
- Modify `epub_browser/assets/auth.js`: settings, link/unlink, loading/error state, and locale-reactive behavior.
- Modify `epub_browser/assets/account.css`: responsive form groups, status treatment, and focus/touch states using existing tokens.
- Modify `epub_browser/assets/i18n.js`: complete OIDC copy for every supported locale.
- Modify `setup.py`, `README.md`, `docs/readme/README.zh-CN.md`, and `THIRD_PARTY_NOTICES.md`: dependencies and deployment guidance.
- Create `tests/test_oidc.py`: protocol and network-boundary unit tests.
- Modify `tests/test_state.py`, `tests/test_auth.py`, `tests/test_server.py`, `tests/test_auth_ui.js`, and `tests/test_i18n.js`: state, route, policy, UI, and locale coverage.
- Create `tests/e2e/oidc/`: isolated Authelia, EPUB Browser, and Playwright Docker Compose fixture.

---

### Task 1: Persist OIDC configuration with migration safety

**Files:**
- Modify: `epub_browser/state.py`
- Test: `tests/test_state.py`

**Interfaces:**
- Produces: `OIDCSettingsRecord`, `StateStore.get_oidc_settings()`, and `StateStore.replace_oidc_settings(...)`.
- Preserves: schema initialization and every pre-v20 migration path.

- [ ] **Step 1: Write failing schema and settings tests**

Add tests that assert schema version 20, singleton defaults, write-only client-secret masking, exact scopes/redirect fields, revision increments, and replacement rollback when the supplied mutation raises before commit. Use a legacy v19 fixture and assert all existing account rows remain unchanged.

```python
settings = self.store.get_oidc_settings()
self.assertFalse(settings.enabled)
self.assertFalse(settings.client_secret_configured)
self.assertEqual(settings.scopes, ("openid", "profile", "email"))

saved = self.store.replace_oidc_settings(
    enabled=True,
    provider_name="Authelia",
    issuer_url="https://auth.example.test",
    client_id="epub-browser",
    client_secret="new-secret",
    redirect_uri="https://reader.example.test/auth/oidc/callback",
    scopes=("openid", "profile", "email"),
    username_claim="preferred_username",
    auto_create_users=False,
    allow_member_password_login=True,
)
self.assertTrue(saved.client_secret_configured)
self.assertFalse(hasattr(saved, "client_secret"))
```

- [ ] **Step 2: Run the focused tests and verify failure**

Run: `python -m unittest tests.test_state.StateStoreTests.test_oidc_settings_defaults tests.test_state.StateStoreTests.test_v19_migrates_oidc_schema -v`

Expected: failure because schema v20 and the settings API do not exist.

- [ ] **Step 3: Implement schema v20 and immutable public records**

Add `oidc_settings` with the fields and checks from the spec. Keep the stored secret in a private SQL row conversion path and return a frozen public record with only `client_secret_configured`. Normalize scopes to a deterministic tuple containing `openid`; reject empty display name, issuer, client ID, username claim, and invalid booleans.

- [ ] **Step 4: Run state migration and full state tests**

Run: `python -m unittest tests.test_state -v`

Expected: all state tests pass with `DB_SCHEMA_VERSION == 20`.

- [ ] **Step 5: Commit the settings slice**

```bash
git add epub_browser/state.py tests/test_state.py
git commit -m "feat: persist OIDC server settings"
```

### Task 2: Persist one-time transactions and external identities

**Files:**
- Modify: `epub_browser/state.py`
- Test: `tests/test_state.py`

**Interfaces:**
- Produces: `OIDCIdentityRecord`, `OIDCTransactionRecord`, `create_oidc_transaction(...)`, `claim_oidc_transaction(...)`, `stage_oidc_association(...)`, `link_oidc_identity(...)`, `unlink_oidc_identity(...)`, `provision_oidc_member(...)`, and identity list/lookups.
- Consumes: users, sessions, `Principal`, token digests, and configuration revision from Task 1.

- [ ] **Step 1: Write failing transaction and identity tests**

Cover browser-token digest matching, ten-minute expiry, one-time callback claim, configuration-revision mismatch, safe association staging, exact issuer/subject lookup, one identity per user/issuer, duplicate-race rollback, profile snapshot updates, and self-unlink refusal when no alternate login exists.

```python
self.store.link_oidc_identity(
    self.owner.user_id,
    issuer="https://auth.example.test",
    subject="stable-subject",
    username_claim="owner-at-idp",
    display_name="Owner",
    email="owner@example.test",
)
resolved = self.store.principal_for_oidc_identity(
    "https://auth.example.test", "stable-subject"
)
self.assertEqual(resolved, self.owner)
```

- [ ] **Step 2: Run focused tests and verify failure**

Run: `python -m unittest tests.test_state.StateStoreTests.test_oidc_transaction_is_browser_bound_and_single_use tests.test_state.StateStoreTests.test_oidc_provisioning_is_atomic -v`

Expected: failure because transaction and identity tables/methods are absent.

- [ ] **Step 3: Implement transactional persistence**

Create `user_identities` and `oidc_login_transactions` with foreign keys, uniqueness, expiry indexes, bounded snapshot fields, and phase checks. Store only digests for raw state/browser tokens. Make provisioning insert user + identity in one `BEGIN IMMEDIATE` transaction and map uniqueness failures to a focused conflict exception without leaving a user row.

- [ ] **Step 4: Run state and migration tests**

Run: `python -m unittest tests.test_state tests.test_migration -v`

Expected: all tests pass, including legacy migration and concurrent uniqueness cases.

- [ ] **Step 5: Commit identity persistence**

```bash
git add epub_browser/state.py tests/test_state.py
git commit -m "feat: store OIDC identities and login transactions"
```

### Task 3: Build the bounded generic OIDC protocol client

**Files:**
- Create: `epub_browser/oidc.py`
- Modify: `setup.py`
- Modify: `THIRD_PARTY_NOTICES.md`
- Create: `tests/test_oidc.py`

**Interfaces:**
- Produces: `OIDCService`, `OIDCConfiguration`, `OIDCProviderMetadata`, `OIDCStart`, `OIDCCompletion`, `OIDCClaims`, and stable `OIDCError.code` values.
- Consumes: Task 1 settings and Task 2 transaction methods; receives an injectable `httpx.AsyncClient` and clock for tests.

- [ ] **Step 1: Add failing discovery and callback tests**

Use HTTPX mock transports and local signed JWT/JWKS fixtures. Cover exact discovery issuer, required endpoints, HTTPS/loopback rules, response-size and timeout mapping, S256 challenge construction, state/browser binding, nonce, `iss`, `aud`, `azp`, `exp`, `iat`, unknown `kid`, key rotation, Provider error callbacks, and sanitized error strings.

```python
start = await service.begin(
    settings,
    purpose="login",
    next_path="/book/book-1/chapter_1.html",
    expected_user_id=None,
)
self.assertIn("code_challenge_method=S256", start.authorization_url)
self.assertNotIn(start.browser_token, start.authorization_url)
```

- [ ] **Step 2: Run protocol tests and verify failure**

Run: `python -m unittest tests.test_oidc -v`

Expected: import failure because `epub_browser.oidc` does not exist.

- [ ] **Step 3: Add compatible dependencies and protocol implementation**

Add `Authlib>=1.6.11,<1.7` and `httpx>=0.27,<1.0`. Implement metadata caching keyed by issuer + settings revision, bounded JSON fetches, Authorization Code + S256 request generation, token exchange, and Authlib-based ID Token/JWKS validation. Keep all low-level protocol data in `oidc.py`; expose only normalized claims and stable local error codes.

- [ ] **Step 4: Run protocol, packaging, and Python 3.9 compatibility tests**

Run: `python -m unittest tests.test_oidc tests.test_vendor_assets -v`

Run in a Python 3.9 container: `docker run --rm -v "$PWD:/src" -w /src python:3.9-slim sh -c 'pip install -e . && python -m unittest tests.test_oidc -v'`

Expected: protocol tests pass and package installation succeeds on Python 3.9.

- [ ] **Step 5: Commit the protocol client**

```bash
git add epub_browser/oidc.py setup.py THIRD_PARTY_NOTICES.md tests/test_oidc.py
git commit -m "feat: add generic OIDC protocol client"
```

### Task 4: Integrate OIDC login, callback, association, and local-login policy

**Files:**
- Modify: `epub_browser/auth.py`
- Modify: `epub_browser/runtime.py`
- Modify: `epub_browser/server.py`
- Test: `tests/test_auth.py`
- Test: `tests/test_server.py`
- Test: `tests/test_runtime.py`
- Test: `tests/test_mode_integration.py`

**Interfaces:**
- Produces routes `GET /auth/oidc/start`, `GET /auth/oidc/callback`, and `GET|POST /auth/oidc/associate`.
- Produces `AuthService.authenticate_password(..., allow_member=True)` and reuses `AuthService.create_session(...)` for OIDC principals.
- Consumes: `OIDCService` from Task 3 and identity/provisioning operations from Task 2.

- [ ] **Step 1: Write failing server-flow tests**

Test hidden/visible Provider action, safe `next`, start cookie attributes, successful linked callback, automatic member provisioning, required association, association password throttling, disabled account denial, stale revision, callback replay, malformed Provider error, no-store headers, local administrator fallback, blocked member password login, and total SSG absence.

```python
response = client.get("/auth/oidc/start?next=%2Faccount", follow_redirects=False)
self.assertEqual(response.status_code, 307)
self.assertIn("epub_browser_oidc", response.headers["set-cookie"])

session = client.get("/api/session").json()
self.assertEqual(session["user"]["username"], "oidc-reader")
self.assertEqual(session["user"]["role"], "member")
```

- [ ] **Step 2: Run focused server tests and verify failure**

Run: `python -m unittest tests.test_server.ServerTests.test_oidc_linked_login_issues_local_session tests.test_auth.AuthTests.test_member_local_login_policy_keeps_admin_fallback -v`

Expected: route/method failures.

- [ ] **Step 3: Wire service lifecycle and public flow routes**

Construct one `OIDCService` in runtime, close its HTTP client during Starlette lifespan shutdown, and pass it to `create_app`. Add narrowly public post-setup routes, bounded form parsing, browser-binding cookie helpers, localized generic protocol pages, and local-session creation. Do not add OIDC branches to SSG templates or static generation.

- [ ] **Step 4: Implement local member password policy**

Allow the existing password verifier to distinguish normal login from association proof. At `/login`, reject a valid member password when settings disable member local login, while administrators and association proof remain valid. Preserve uniform throttling and generic responses.

- [ ] **Step 5: Run authentication and mode suites**

Run: `python -m unittest tests.test_auth tests.test_server tests.test_runtime tests.test_mode_integration -v`

Expected: all tests pass without changing current session/CSRF behavior.

- [ ] **Step 6: Commit the core login flow**

```bash
git add epub_browser/auth.py epub_browser/runtime.py epub_browser/server.py tests/test_auth.py tests/test_server.py tests/test_runtime.py tests/test_mode_integration.py
git commit -m "feat: integrate OIDC server login flows"
```

### Task 5: Add administrator and account identity APIs

**Files:**
- Modify: `epub_browser/server.py`
- Modify: `epub_browser/state.py`
- Test: `tests/test_server.py`
- Test: `tests/test_state.py`

**Interfaces:**
- Produces `GET|PUT /api/admin/oidc/settings`, `POST /api/account/oidc/link`, `DELETE /api/account/oidc/identity`, and identity data in administrator user/account session payloads.
- Consumes: Task 1 atomic settings replacement, Task 2 link/unlink methods, and Task 3 `validate_configuration(...)`.

- [ ] **Step 1: Write failing API contract tests**

Cover admin-only masked reads, CSRF, validate-before-save rollback, secret retain/replace/clear semantics, exact redirect URI validation, settings revision changes, link start for current user only, safe self-unlink, admin identity inspection/removal, and no raw secret/profile-token fields in JSON.

- [ ] **Step 2: Run focused tests and verify failure**

Run: `python -m unittest tests.test_server.ServerTests.test_admin_oidc_settings_are_masked_and_validated tests.test_server.ServerTests.test_account_oidc_unlink_requires_alternate_login -v`

Expected: 404 responses for the new APIs.

- [ ] **Step 3: Implement API orchestration**

Parse strict unique-key JSON, build an `OIDCConfiguration`, call discovery validation before replacing settings, and map stable OIDC errors to sanitized API codes. Return `client_secret_configured`, callback URI helper data, identity summary, and capability flags only. Use existing CSRF and `require_admin`/`require_principal` guards.

- [ ] **Step 4: Run state/server API suites**

Run: `python -m unittest tests.test_state tests.test_server -v`

Expected: all tests pass and existing administration APIs are unchanged.

- [ ] **Step 5: Commit APIs**

```bash
git add epub_browser/server.py epub_browser/state.py tests/test_server.py tests/test_state.py
git commit -m "feat: add OIDC settings and identity APIs"
```

### Task 6: Implement accessible OIDC administration and account UI

**Files:**
- Modify: `epub_browser/server_chrome.py`
- Modify: `epub_browser/server.py`
- Modify: `epub_browser/assets/auth.js`
- Modify: `epub_browser/assets/account.css`
- Modify: `epub_browser/assets/i18n.js`
- Test: `tests/test_auth_ui.js`
- Test: `tests/test_i18n.js`
- Test: `tests/test_i18n_coverage.py`
- Test: `tests/test_server.py`

**Interfaces:**
- Consumes: Task 5 JSON APIs and existing `authenticatedFetch`, notification, dialog, locale-change, tab, and account form helpers.
- Produces: deep-linkable `oidc` admin tab, Provider login action, account identity card, association form, and localized loading/error/success states.

- [ ] **Step 1: Add failing markup and JavaScript tests**

Assert tab semantics, `fieldset`/`legend`, associated labels, helper/error IDs, password autocomplete, masked-secret behavior, current-origin callback suggestion, one primary submit, 44px-capable classes, loading disablement, actionable field errors, confirmation before unlink, no `innerHTML` for claims, locale rerender, and no OIDC DOM in SSG output.

- [ ] **Step 2: Run UI tests and verify failure**

Run: `node --test tests/test_auth_ui.js tests/test_i18n.js`

Run: `python -m unittest tests.test_i18n_coverage tests.test_server -v`

Expected: missing OIDC elements and locale keys.

- [ ] **Step 3: Add semantic shared markup**

Add the OIDC top-level admin tab and panel to `server_chrome.py`, an identity region to account settings, and the textual local/OIDC divider plus Provider action to the login renderer. Use visible labels, programmatic descriptions, `role="status"`/`aria-live`, and a destructive unlink region separated from normal actions.

- [ ] **Step 4: Add UI behavior with safe state handling**

Extend the existing admin-section allowlist and URL hash behavior. Load masked settings, preserve blank secret input, validate on blur/submit, disable controls during save, focus the first invalid field, and update status without page reload. Implement link navigation and confirmed unlink using existing CSRF-aware fetch helpers.

- [ ] **Step 5: Add responsive token-based CSS and complete translations**

Use existing semantic colors, focus rings, button/input primitives, and breakpoints. Keep inputs at least 44px tall, stack groups at 375px, prevent horizontal overflow at 200% zoom, provide dark-mode parity, and gate transitions behind reduced-motion. Add all OIDC keys to every object in `i18n.js` and keep runtime DOM on `data-i18n*` or locale subscriptions.

- [ ] **Step 6: Run complete UI and i18n suites**

Run: `node --test tests/test_auth_ui.js tests/test_i18n.js`

Run: `python -m unittest tests.test_i18n_coverage tests.test_server tests.test_generated_reader_surfaces -v`

Expected: all UI, locale, Server, and shared-surface tests pass.

- [ ] **Step 7: Commit UI and i18n**

```bash
git add epub_browser/server_chrome.py epub_browser/server.py epub_browser/assets/auth.js epub_browser/assets/account.css epub_browser/assets/i18n.js tests/test_auth_ui.js tests/test_i18n.js tests/test_i18n_coverage.py tests/test_server.py
git commit -m "feat: add accessible OIDC account interfaces"
```

### Task 7: Document generic Provider and Authelia deployment

**Files:**
- Modify: `README.md`
- Modify: `docs/readme/README.zh-CN.md`
- Test: `tests/test_readme_docs.py`

**Interfaces:**
- Documents: admin configuration fields, exact callback URI, local-admin recovery, binding/provisioning behavior, and Authelia confidential-client/S256 settings.

- [ ] **Step 1: Add failing documentation contract tests**

Assert both primary English and Simplified Chinese docs mention OIDC, the callback path, Authorization Code, S256 PKCE, `(issuer, sub)`, local administrator fallback, and passwordless-member provisioning.

- [ ] **Step 2: Run documentation tests and verify failure**

Run: `python -m unittest tests.test_readme_docs -v`

Expected: failure for missing OIDC deployment sections.

- [ ] **Step 3: Write operator guidance**

Add concise generic OIDC setup and a concrete Authelia client example with clearly fake example values, exact redirect URI, scopes, and recovery warnings. State that the admin UI stores one Provider and that enabling automatic provisioning before existing users bind can create duplicate local accounts.

- [ ] **Step 4: Run documentation tests and commit**

Run: `python -m unittest tests.test_readme_docs -v`

```bash
git add README.md docs/readme/README.zh-CN.md tests/test_readme_docs.py
git commit -m "docs: explain OIDC and Authelia setup"
```

### Task 8: Prove the complete flow against real Authelia

**Files:**
- Create: `tests/e2e/oidc/docker-compose.yml`
- Create: `tests/e2e/oidc/authelia/configuration.yml`
- Create: `tests/e2e/oidc/authelia/users.yml`
- Create: `tests/e2e/oidc/authelia/private.pem`
- Create: `tests/e2e/oidc/fixtures/test.epub`
- Create: `tests/e2e/oidc/run.sh`
- Create: `tests/e2e/oidc/test_oidc.mjs`
- Create: `tests/e2e/oidc/README.md`

**Interfaces:**
- Produces: `tests/e2e/oidc/run.sh`, a self-cleaning deterministic Docker E2E entry point.
- Consumes: the production Dockerfile, public admin/account flows from Tasks 4–6, Authelia OIDC discovery, and Playwright Chromium.

- [ ] **Step 1: Create the isolated Compose fixture and first failing smoke test**

Use test-only hostnames on one Compose network, Authelia file authentication, a confidential EPUB Browser client requiring S256, a fixed test signing key clearly labeled non-production, temporary named volumes, health checks, and a Playwright service. The first assertion loads discovery and fails until EPUB Browser is configured.

- [ ] **Step 2: Run Compose and verify the expected initial failure**

Run: `tests/e2e/oidc/run.sh`

Expected: containers become healthy and the browser test reports that the OIDC login action is absent before administrator configuration.

- [ ] **Step 3: Implement the end-to-end browser journey**

Drive unattended local-admin bootstrap, sign in locally, save the OIDC settings in the real admin tab, log out, authenticate at Authelia, bind an existing member with password proof, verify the library session, unlink safeguard, then enable auto-create and authenticate a second Authelia user. Disable member local login and prove local admin still succeeds while member password login is rejected.

- [ ] **Step 4: Add negative callback checks and automatic cleanup**

Verify tampered state, missing browser cookie, replayed callback, and disabled OIDC return safe localized recovery. Make `run.sh` always collect service logs on failure and run `docker compose down -v --remove-orphans` from a trap without deleting any non-fixture paths.

- [ ] **Step 5: Run the real E2E twice**

Run: `tests/e2e/oidc/run.sh && tests/e2e/oidc/run.sh`

Expected: both clean-room runs pass, proving fixture idempotence and no dependence on retained containers or volumes.

- [ ] **Step 6: Commit the E2E fixture**

```bash
git add tests/e2e/oidc
git commit -m "test: verify OIDC login with Authelia"
```

### Task 9: Run full verification and UI/UX Design Review

**Files:**
- Modify if findings require fixes: `epub_browser/server_chrome.py`
- Modify if findings require fixes: `epub_browser/assets/auth.js`
- Modify if findings require fixes: `epub_browser/assets/account.css`
- Modify if findings require fixes: `epub_browser/assets/i18n.js`
- Modify corresponding tests for every corrected finding.

**Interfaces:**
- Produces: a clean branch with complete automated evidence and no unresolved Critical/High/Medium UI review findings.

- [ ] **Step 1: Run all Python and JavaScript tests**

Run: `python -m unittest discover -s tests -v`

Run: `for file in tests/*.js; do node --test "$file" || exit 1; done`

Expected: every suite passes.

- [ ] **Step 2: Run packaging, release, and whitespace checks**

Run: `python tools/sync_vendor_assets.py verify`

Run: `python tools/verify_release_artifacts.py --source-tree .`

Run: `git diff --check`

Expected: all commands exit zero and no OIDC secret/token appears in `git grep` or captured logs.

- [ ] **Step 3: Capture review artifacts**

Use the real Docker environment to capture login, association, account identity, and admin OIDC screens at 1440px and 375px in light and dark themes. Also test keyboard-only traversal, 200% browser zoom, and reduced motion.

- [ ] **Step 4: Apply the `UI/UX Design Review` framework**

Review WCAG 2.2 AA accessibility, visual hierarchy, form clarity, interaction states, responsive behavior, dark-mode contrast, microcopy, loading/error recovery, and destructive-action safety. Record severity and concrete evidence. Fix every Critical, High, and Medium finding and add a regression assertion for each code change.

- [ ] **Step 5: Re-run focused review tests and real E2E**

Run the affected Python/Node tests, then: `tests/e2e/oidc/run.sh`

Expected: corrected UI passes automated suites and the complete real Provider journey.

- [ ] **Step 6: Commit review fixes and final verification record**

```bash
git add epub_browser tests README.md docs THIRD_PARTY_NOTICES.md setup.py
git commit -m "fix: address OIDC UI and verification review"
```

Run: `git status --short`

Expected: no uncommitted files in the OIDC worktree.
