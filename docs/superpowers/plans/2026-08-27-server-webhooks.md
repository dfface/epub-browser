# Server WebHooks Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add administrator-managed signed WebHooks with transactional events, durable delivery, retries, history, and manual redelivery.

**Architecture:** Store endpoint subscriptions, immutable events, deliveries, and attempts in SQLite. `webhooks.py` owns allowlisted envelopes, HMAC signing, leased queue claims, HTTP delivery, retry, and cleanup; Server lifecycle and admin routes expose it without blocking originating requests.

**Tech Stack:** Python 3.9, SQLite, Starlette, standard-library HTTP client in a worker thread, native JavaScript/CSS, unittest, Node test runner.

**Spec:** `docs/superpowers/specs/2026-08-27-server-pat-openapi-webhooks-design.md`

## Global Constraints

- WebHooks are Server-only and administrator-managed through Cookie + CSRF APIs; PATs cannot manage them.
- Endpoint URLs may be any administrator-supplied HTTP or HTTPS URL; every other scheme is rejected.
- Review events contain user ID, book ID, action, and timestamps only—never rating or review text.
- Deliveries are at least once, signed over timestamp plus exact body, do not follow redirects, and survive restart.
- Retry every non-2xx/connection/timeout failure for at most eight total attempts with jittered exponential backoff capped at 24 hours.
- Delivery history is retained for 30 days; pending or leased deliveries are never removed by retention.
- All visible copy covers en, zh-CN, zh-TW, ko, and ja; UI targets WCAG 2.2 AA.
- Do not raise `SERVER_OUTPUT_REVISION`; SSG contains no WebHook controls, API URLs, or worker assets.

## File Structure

| File | Responsibility |
| --- | --- |
| `epub_browser/webhooks.py` | Event validation, envelope, signing, transport, worker, retry, cleanup. |
| `epub_browser/state.py` | v16 WebHook schema, outbox transactions, leases, history queries. |
| `epub_browser/server.py` | Admin routes and worker lifespan. |
| `epub_browser/server_library.py` | Book lifecycle and conversion event emission. |
| `epub_browser/server_chrome.py` | Administration WebHooks tab and forms. |
| `epub_browser/assets/auth.js` | Endpoint CRUD, test, rotation, history, redelivery. |
| `epub_browser/assets/account.css` | Responsive endpoint/history layouts and states. |
| `epub_browser/assets/i18n.js` | Five-locale WebHook copy. |
| `tests/test_webhooks.py` | Envelope, signature, worker, retry, leases, retention. |
| `tests/test_state.py` | WebHook schema and transactional outbox. |
| `tests/test_server.py` | Admin authorization and WebHook APIs. |
| `tests/test_server_library.py` | Book and conversion event integration. |
| `tests/test_auth_ui.js` | Administration interaction tests. |

### Task 1: Add v16 WebHook schema and transactional outbox APIs

**Files:**
- Modify: `epub_browser/state.py`
- Modify: `tests/test_state.py`

**Interfaces:**
- Produces `WebhookEndpointRecord`, `WebhookEventRecord`, `WebhookDeliveryRecord`, and `WebhookAttemptRecord`.
- Produces endpoint CRUD/subscription methods, `enqueue_webhook_event`, `claim_webhook_delivery`, `complete_webhook_delivery`, `retry_webhook_delivery`, `fail_webhook_delivery`, `redeliver_webhook_event`, and `cleanup_webhook_history`.

- [ ] **Step 1: Write failing schema, lease, and outbox tests**

```python
def test_review_update_and_event_commit_atomically(self):
    endpoint = self.create_review_endpoint()
    review = self.store.upsert_book_review(self.book.book_id, self.member.user_id, 5, "private")
    event = self.store.list_webhook_events(event_type="review.created")[0]
    self.assertEqual(event.payload["data"], {"user_id": self.member.user_id, "book_id": self.book.book_id})
    self.assertNotIn("private", json.dumps(event.payload))

def test_expired_delivery_lease_can_be_reclaimed(self):
    first = self.store.claim_webhook_delivery("worker-a", now=100, lease_seconds=30)
    self.assertIsNone(self.store.claim_webhook_delivery("worker-b", now=120, lease_seconds=30))
    second = self.store.claim_webhook_delivery("worker-b", now=131, lease_seconds=30)
    self.assertEqual(second.id, first.id)
```

- [ ] **Step 2: Run tests and verify failure**

Run: `python3 -m unittest tests.test_state -v`

Expected: FAIL because the WebHook schema and queue methods do not exist.

- [ ] **Step 3: Implement tables, indexes, and transactional methods**

Extend the shared v16 migration with endpoint, subscription, event, delivery, and attempt tables. Make `_create_compatible_schema()` create missing v16 WebHook tables even when `PRAGMA user_version` is already 16, and test a PAT-only intermediate v16 database so executing the two plans sequentially is restart-safe. Use soft deletion for endpoint history, erase the active secret on deletion, index due deliveries by status/next-attempt/lease, and claim with `BEGIN IMMEDIATE`. Store canonical immutable payload JSON. Insert subscribed deliveries in the same transaction as each event.

- [ ] **Step 4: Run StateStore tests**

Run: `python3 -m unittest tests.test_state -v`

Expected: PASS for fresh/v15 migration, queue order, leases, disable/resume, deletion, redelivery, and retention.

- [ ] **Step 5: Commit**

```bash
git add epub_browser/state.py tests/test_state.py
git commit -m "feat: add durable webhook outbox state"
```

### Task 2: Implement event envelopes, HMAC signatures, and delivery worker

**Files:**
- Create: `epub_browser/webhooks.py`
- Create: `tests/test_webhooks.py`

**Interfaces:**
- Produces `WEBHOOK_EVENT_TYPES`, `WebhookService`, `WebhookTransport`, `sign_webhook`, and `retry_delay_seconds`.
- `WebhookService.start_worker()` and `stop_worker()` integrate with Server lifespan in Task 4.

- [ ] **Step 1: Write failing signing, redirect, retry, and recovery tests**

```python
def test_signature_covers_timestamp_period_and_exact_body(self):
    signature = sign_webhook(b"secret", 1700000000, b'{"ok":true}')
    expected = hmac.new(b"secret", b'1700000000.{"ok":true}', hashlib.sha256).hexdigest()
    self.assertEqual(signature, "v1=" + expected)

async def test_worker_retries_every_non_2xx_and_stops_after_eight(self):
    transport = FakeTransport(status=302)
    service = WebhookService(self.store, transport=transport, clock=self.clock, jitter=lambda _: 0)
    await service.run_until_idle_for_test()
    self.assertEqual(self.store.get_delivery(self.delivery.id).status, "retrying")
```

- [ ] **Step 2: Run tests and verify failure**

Run: `python3 -m unittest tests.test_webhooks -v`

Expected: FAIL because `epub_browser.webhooks` is absent.

- [ ] **Step 3: Implement bounded transport and leased worker**

Use the standard library to POST from `asyncio.to_thread`, disable redirect handling, apply connect/read timeout, cap the consumed response body, and cap concurrent deliveries. Send the specified `X-EPUB-*` headers. Attempt immediately, then schedule jittered exponential delays capped at 86,400 seconds. Mark attempt eight terminal. Requeue expired leases on startup and run 30-day cleanup without touching pending/leased rows.

- [ ] **Step 4: Run worker tests**

Run: `python3 -m unittest tests.test_webhooks -v`

Expected: PASS for 2xx, 3xx, 4xx, 5xx, timeout, connection error, eight attempts, signatures, rotation, leases, restart, response bounds, and cleanup.

- [ ] **Step 5: Commit**

```bash
git add epub_browser/webhooks.py tests/test_webhooks.py
git commit -m "feat: deliver signed webhooks with retry"
```

### Task 3: Emit review, book, and conversion events from authoritative transitions

**Files:**
- Modify: `epub_browser/state.py`
- Modify: `epub_browser/server_library.py`
- Modify: `tests/test_state.py`
- Modify: `tests/test_server_library.py`

**Interfaces:**
- Consumes Task 1 outbox API.
- Emits the eight domain event types in the approved spec; `webhook.test` remains explicit admin behavior.

- [ ] **Step 1: Write failing privacy and transition-semantic tests**

```python
def test_review_events_never_include_rating_or_body(self):
    self.store.upsert_book_review(self.book.book_id, self.member.user_id, 4, "secret review")
    payload = self.store.list_webhook_events()[0].payload
    self.assertEqual(set(payload["data"]), {"user_id", "book_id"})
    self.assertNotIn("secret review", json.dumps(payload))
    self.assertNotIn("4", json.dumps(payload["data"]))

def test_failed_conversion_uses_display_name_and_public_error_only(self):
    self.library.fail_conversion(Path("/private/library/Book.epub"), RuntimeError("trace detail"))
    payload = self.latest_event("book.conversion.failed").payload
    self.assertEqual(payload["data"]["source_name"], "Book.epub")
    self.assertNotIn("/private/library", json.dumps(payload))
```

- [ ] **Step 2: Run tests and verify failure**

Run: `python3 -m unittest tests.test_state tests.test_server_library -v`

Expected: FAIL because transitions do not emit domain events.

- [ ] **Step 3: Integrate allowlisted event emission**

Determine create/update/delete review action from the pre-transaction row. Emit book created/updated/removed at committed reconciliation changes. Emit conversion succeeded after durable publication and conversion failed through a dedicated event transaction with source basename and stable public error code only. Avoid emitting from HTTP or JavaScript handlers.

- [ ] **Step 4: Run transition tests**

Run: `python3 -m unittest tests.test_state tests.test_server_library tests.test_server -v`

Expected: PASS with exactly one immutable event per authoritative transition and no private review text or source path.

- [ ] **Step 5: Commit**

```bash
git add epub_browser/state.py epub_browser/server_library.py tests/test_state.py tests/test_server_library.py
git commit -m "feat: emit book and review webhook events"
```

### Task 4: Add administrator WebHook APIs and lifecycle integration

**Files:**
- Modify: `epub_browser/server.py`
- Modify: `tests/test_server.py`

**Interfaces:**
- Produces `GET/POST /api/admin/webhooks`, `GET/PUT/DELETE /api/admin/webhooks/{id}`, `POST /test`, `POST /rotate-secret`, delivery history, and redelivery routes.
- Starts and stops Task 2 `WebhookService` in the Starlette lifespan.

- [ ] **Step 1: Write failing authorization, secret, and route tests**

```python
def test_member_and_pat_cannot_manage_webhooks(self):
    self.assertEqual(self.member_client.get("/api/admin/webhooks").status_code, 403)
    self.assertEqual(self.client.get("/api/admin/webhooks", headers=self.admin_bearer()).status_code, 401)

def test_secret_is_returned_only_on_create_and_rotation(self):
    created = self.admin_post("/api/admin/webhooks", self.endpoint_payload()).json()
    self.assertIn("secret", created)
    self.assertNotIn("secret", self.admin_get("/api/admin/webhooks").text)
    self.assertIn("secret", self.admin_post("/api/admin/webhooks/{}/rotate-secret".format(created["webhook"]["id"]), {}).json())
```

- [ ] **Step 2: Run tests and verify failure**

Run: `python3 -m unittest tests.test_server.ServerWebhookTests -v`

Expected: FAIL on missing routes.

- [ ] **Step 3: Implement bounded admin APIs and lifespan worker**

Validate name, HTTP/HTTPS URL, enabled state, and exact event-name subscriptions. Return the secret only from create/rotation. Paginate deliveries and attempts, truncate response summaries, send `webhook.test` independent of subscriptions, and redeliver by event ID while preserving the event. Apply current admin role and CSRF before reading any WebHook state.

- [ ] **Step 4: Run server tests**

Run: `python3 -m unittest tests.test_server.ServerWebhookTests tests.test_webhooks -v`

Expected: PASS for administrator, member, anonymous, PAT, CSRF, malformed URL, secret redaction, lifecycle, and worker shutdown.

- [ ] **Step 5: Commit**

```bash
git add epub_browser/server.py tests/test_server.py
git commit -m "feat: add webhook administration APIs"
```

### Task 5: Build the WebHooks administration interface and five-locale copy

**Files:**
- Modify: `epub_browser/server_chrome.py`
- Modify: `epub_browser/assets/auth.js`
- Modify: `epub_browser/assets/account.css`
- Modify: `epub_browser/assets/i18n.js`
- Modify: `tests/test_auth_ui.js`
- Modify: `tests/test_generated_reader_surfaces.py`
- Modify: `tests/test_i18n_coverage.py`

**Interfaces:**
- Consumes Task 4 admin routes.
- Adds the `webhooks` admin tab, endpoint editor, one-time secret notice, event checklist, delivery filters, attempts disclosure, and live status region.

- [ ] **Step 1: Write failing UI flow and accessibility tests**

```javascript
test('webhook editor preserves fields on validation error and clears one-time secret on close', async () => {
  const ui = buildAdminUI({createWebhookError: {code: 'invalid_webhook_url'}});
  ui.name.value = 'Automation';
  ui.url.value = 'ftp://invalid';
  await ui.submitWebhook();
  assert.equal(ui.name.value, 'Automation');
  assert.equal(ui.url.getAttribute('aria-invalid'), 'true');
  ui.showSecret('generated-secret');
  ui.closeAdminPanel();
  assert.equal(ui.secret.textContent, '');
});
```

Add generated HTML assertions for tab/tabpanel relationships, labelled URL and event controls, live regions, and absence from SSG.

- [ ] **Step 2: Run tests and verify failure**

Run: `node --test tests/test_auth_ui.js && python3 -m unittest tests.test_generated_reader_surfaces tests.test_i18n_coverage -v`

Expected: FAIL on missing WebHook UI and locale keys.

- [ ] **Step 3: Implement responsive, accessible administration UI**

Use a concise endpoint list with status text and primary actions, a labelled editor, inline URL warning, grouped event checkboxes, explicit enable state, copy/rotate confirmation, test action, filterable delivery history, and expandable attempt details. Preserve entered values on errors, disable duplicate submissions, announce async results, keep logical focus on open/close, provide visible focus, and maintain 44px targets and 320px reflow.

- [ ] **Step 4: Run UI and locale tests**

Run: `node --test tests/test_auth_ui.js && python3 -m unittest tests.test_generated_reader_surfaces tests.test_i18n_coverage -v`

Expected: PASS for keyboard behavior, statuses, destructive confirmation, five locales, and SSG isolation.

- [ ] **Step 5: Commit**

```bash
git add epub_browser/server_chrome.py epub_browser/assets/auth.js epub_browser/assets/account.css epub_browser/assets/i18n.js tests/test_auth_ui.js tests/test_generated_reader_surfaces.py tests/test_i18n_coverage.py
git commit -m "feat: add webhook administration interface"
```

### Task 6: Run the required UI/UX design review, fix findings, and verify release readiness

**Files:**
- Modify as findings require: `epub_browser/server_chrome.py`, `epub_browser/assets/auth.js`, `epub_browser/assets/account.css`, `epub_browser/assets/i18n.js`
- Modify: relevant UI and generated-surface tests
- Modify: `README.md`
- Modify: `README.zh-CN.md`

**Interfaces:**
- Consumes the completed PAT and WebHook interfaces.
- Produces WCAG 2.2 AA-reviewed UI and a manual acceptance checklist.

- [ ] **Step 1: Review the rendered interfaces with the named UI/UX Design Review skill**

Inspect desktop, 768px, and 320px layouts; light/dark themes; 200% zoom; empty/loading/error/success/disabled states; keyboard-only focus order; modal focus restoration; labels, headings, ARIA, live regions; touch targets; microcopy; and destructive confirmations. Record findings by Critical/High/Medium/Low with WCAG references.

- [ ] **Step 2: Add failing regression tests for every Critical/High finding**

```javascript
test('one-time PAT and webhook secrets receive focus and an assertive accessible announcement', async () => {
  const ui = buildSecretResultUI();
  ui.revealSecret('secret');
  assert.equal(ui.secretRegion.getAttribute('role'), 'status');
  assert.equal(ui.document.activeElement, ui.copyButton);
});
```

Replace or extend this exact regression with each observed high-priority finding before changing production code.

- [ ] **Step 3: Implement the reviewed fixes and re-run focused UI checks**

Run: `node --test tests/test_auth_ui.js && python3 -m unittest tests.test_generated_reader_surfaces tests.test_i18n_coverage tests.test_theme_accessibility -v`

Expected: PASS and no unresolved Critical or High review finding.

- [ ] **Step 4: Run full automated verification**

Run: `python3 -m unittest discover -s tests -p 'test_*.py' -v`

Run: `for test_file in tests/test_*.js; do node --test "$test_file" || exit 1; done`

Run: `python3 -m compileall -q epub_browser && git diff --check`

Expected: all commands PASS.

- [ ] **Step 5: Document manual browser acceptance and commit**

Update both READMEs with PAT examples, scope meanings, chapter formats, WebHook signature verification, retry behavior, review privacy, and operator warnings. Hand off manual acceptance for PAT creation/copy/revoke, curl calls, restricted chapters, admin cross-user reads, WebHook create/test/receive/retry/rotate, responsive layout, dark mode, keyboard navigation, and screen-reader announcements.

```bash
git add epub_browser tests README.md README.zh-CN.md
git commit -m "feat: finish PAT OpenAPI and webhook experience"
```
