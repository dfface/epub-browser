# Administrator AI Jobs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a privacy-safe, paginated administrator AI reading job table and audited manual retry that re-evaluates the original request against current settings and content.

**Architecture:** `StateStore` owns pagination SQL and the atomic creation of linked retry attempts. `AIReadingService` owns replay validation, current material/template/cache calculation, authorization, and worker wake-up. `server.py` exposes administrator-only routes, while `auth.js` renders and polls a semantic table without receiving replay JSON or private conversations.

**Tech Stack:** Python 3.9+, Starlette, SQLite schema v11, `asyncio`, browser-compatible ES5 JavaScript, CSS, `unittest`, Node's built-in test runner.

**Spec:** `docs/superpowers/specs/2026-08-23-server-schema-admin-operations-design.md`

## Global Constraints

- Complete `docs/superpowers/plans/2026-08-23-server-sqlite-schema-v11.md` first.
- List and retry only shared `ai_reading_jobs`; do not expose follow-up or book-chat questions/answers.
- Never return `request_json`, EPUB text, prompts, provider configuration/response, exceptions, source paths, or filesystem paths.
- Retry only `failed` or `interrupted` jobs with a valid replay request.
- Preserve the original owner and enforce the owner's current enabled state, book access, AI authorization, and quota.
- Recompute profile, template, material digest, cache key, and progress against current state.
- A retry creates a linked row; it never changes the terminal source row back to `queued`.
- Pagination defaults to 20 and rejects page sizes above 100.
- All visible copy and accessibility labels must exist in English and Simplified Chinese.
- Server mode only; SSG must not contain the administration controls or API calls.
- Do not change `.server-content-revision`.

---

### Task 1: Add safe job pagination and atomic retry lineage to StateStore

**Files:**
- Modify: `tests/test_state.py`
- Modify: `epub_browser/state.py:2360-2670`

**Interfaces:**
- Consumes: schema v11 retry columns and indexes.
- Produces: `StateStore.list_admin_ai_jobs(*, status: Optional[str], page: int, page_size: int) -> tuple[tuple[dict, ...], int]`, `StateStore.get_ai_job_for_retry(job_id: str) -> Optional[dict]`, and `StateStore.create_or_get_admin_retry_ai_job(...) -> tuple[dict, bool]`.

- [ ] **Step 1: Write failing pagination/privacy tests**

Create 25 jobs with distinct creation times and mixed statuses, then assert:

```python
jobs, total = self.store.list_admin_ai_jobs(status="failed", page=2, page_size=5)
self.assertEqual(total, 13)
self.assertEqual(len(jobs), 5)
self.assertEqual([job["created_at"] for job in jobs], sorted(
    (job["created_at"] for job in jobs), reverse=True
))
self.assertTrue(all(job["status"] == "failed" for job in jobs))
self.assertTrue(all("request_json" not in job for job in jobs))
self.assertTrue(all("metadata_json" not in job for job in jobs))
self.assertEqual(jobs[0]["book_title"], "Admin Job Book")
self.assertEqual(jobs[0]["owner_username"], "reader")
```

Use replay payloads containing `scope`, `mode`, `language`, `chapter_index`, and `reading_boundary`; assert only those parsed safe fields appear.

- [ ] **Step 2: Write failing retry-lineage and concurrency tests**

Finish one source job as failed. Call `create_or_get_admin_retry_ai_job` twice with the same recomputed cache key and assert one row is created, the second returns it, the source stays failed, and the new row contains:

```python
{
    "attempt_number": 2,
    "retried_from_job_id": "failed-source",
    "retry_root_job_id": "failed-source",
    "retried_by_user_id": self.owner.user_id,
    "owner_user_id": self.member.user_id,
}
```

After failing attempt 2, retry it and assert attempt 3 retains the same root. Add validation tests for a queued, running, complete, unknown, and malformed-replay source.

- [ ] **Step 3: Run the focused state tests and verify failure**

Run: `python3 -m unittest tests.test_state.StateStoreTests.test_admin_ai_job_pagination_is_safe_and_stable tests.test_state.StateStoreTests.test_admin_retry_creates_one_linked_active_attempt tests.test_state.StateStoreTests.test_admin_retry_attempt_numbers_follow_the_root_lineage -v`

Expected: FAIL because the methods do not exist.

- [ ] **Step 4: Implement safe list mapping**

Validate `status`, `page`, and `page_size` before SQL. Use one count query and one joined page query ordered by `jobs.created_at DESC, jobs.id DESC`. Build separate filtered and unfiltered SQL variants so each can use its matching index:

```sql
SELECT jobs.id, jobs.owner_user_id, users.username AS owner_username,
       jobs.book_id, books.metadata_json AS book_metadata_json,
       jobs.request_json, jobs.profile, jobs.template_id, jobs.template_version,
       jobs.status, jobs.error_code, jobs.result_id,
       jobs.progress_current, jobs.progress_total,
       jobs.attempt_number, jobs.retried_from_job_id,
       jobs.retry_root_job_id, jobs.retried_by_user_id,
       jobs.created_at, jobs.updated_at
FROM ai_reading_jobs AS jobs
JOIN users ON users.id = jobs.owner_user_id
LEFT JOIN books ON books.book_id = jobs.book_id
WHERE jobs.status = :status
ORDER BY jobs.created_at DESC, jobs.id DESC
LIMIT :page_size OFFSET :offset
```

For the unfiltered variant, omit the `WHERE` clause completely so ordering uses `idx_ai_jobs_created`; the filtered variant uses `idx_ai_jobs_status_created`.

Parse metadata and replay JSON inside the store mapper, copy only the six allowed request fields, and omit both raw JSON strings. Set `retryable` only when status is failed/interrupted and replay parsing yields a valid object.

Use this same safe mapper for rows returned by `create_or_get_admin_retry_ai_job`, including the existing-active path. Only `get_ai_job_for_retry` may return `request_json`; a job dictionary returned by the retry service or administrator route must never contain it.

- [ ] **Step 5: Implement the private replay lookup and atomic retry insert**

`get_ai_job_for_retry` returns the complete internal job row, including private `request_json`, only to server-side callers.

Define the retry creator with explicit keyword-only inputs:

```python
def create_or_get_admin_retry_ai_job(
    self, *, source_job_id: str, job_id: str, retried_by_user_id: str,
    owner_user_id: str, book_id: str, cache_key: str, request_payload: dict,
    progress_total: int, profile: str, template_id: str,
    template_version: int, cached_result_id: Optional[str] = None,
) -> tuple[dict, bool]:
    ...
```

Inside `BEGIN IMMEDIATE`, re-read and validate the source status, verify both users/book/result, return an existing queued/running row for `cache_key`, derive root and `MAX(attempt_number)+1`, and insert either:

- `queued`, progress 0, no result; or
- `complete`, progress equal to total, with `cached_result_id`.

Catch only the partial-unique race, re-query the active cache row, and return `(row, False)`; do not suppress unrelated integrity errors.

- [ ] **Step 6: Run all StateStore AI tests**

Run: `python3 -m unittest tests.test_state -v`

Expected: PASS.

- [ ] **Step 7: Commit store pagination and retry lineage**

```bash
git add epub_browser/state.py tests/test_state.py
git commit -m "feat: persist auditable AI job retries"
```

---

### Task 2: Reconstruct and enqueue retries in AIReadingService

**Files:**
- Modify: `tests/test_ai_reading.py`
- Modify: `epub_browser/ai_reading.py:395-710`

**Interfaces:**
- Consumes: Task 1's `get_ai_job_for_retry` and `create_or_get_admin_retry_ai_job`.
- Produces: `AIReadingService.retry_job(administrator: Principal, source_job_id: str) -> dict`.

- [ ] **Step 1: Write failing service retry tests**

Add async tests covering:

```python
retried = await self.service.retry_job(self.owner, "failed-job")
self.assertEqual(retried["status"], "queued")
self.assertEqual(retried["job"]["owner_user_id"], self.member.user_id)
self.assertEqual(retried["job"]["retried_by_user_id"], self.owner.user_id)
self.assertEqual(retried["job"]["attempt_number"], 2)
```

Change the book AI profile after the source failure and assert the new job contains the current profile/template and a cache key different from the old job. In a separate case change only the model configuration revision: assert the content cache key remains compatible but an older-revision cached result is not reused. Add cases for same-revision cached completion with zero provider calls, active-cache joining, disabled owner, revoked book access, disabled AI, invalid replay JSON, and a non-admin caller.

- [ ] **Step 2: Run retry service tests and verify failure**

Run: `python3 -m unittest tests.test_ai_reading.AIReadingServiceTests.test_admin_retry_recomputes_current_job_state tests.test_ai_reading.AIReadingServiceTests.test_admin_retry_uses_current_cache_without_provider_call tests.test_ai_reading.AIReadingServiceTests.test_admin_retry_rejects_disabled_owner_or_revoked_book -v`

Expected: FAIL because `retry_job` does not exist.

- [ ] **Step 3: Implement strict replay decoding**

Add a private helper that accepts only the persisted reading request contract:

```python
def _reading_request_from_job_payload(payload: object) -> ReadingRequest:
    if not isinstance(payload, dict):
        raise AIReadingError("ai_job_not_retryable")
    request = ReadingRequest(
        scope=payload.get("scope"),
        book_id=payload.get("book_id"),
        chapter_index=payload.get("chapter_index"),
        mode=payload.get("mode", "chapter"),
        language=payload.get("language", "en"),
        force=True,
        reading_boundary=payload.get("reading_boundary"),
    )
    _validate_reading_request_fields(request)
    return request
```

Share field validation with normal submission rather than allowing retry-only request shapes.

- [ ] **Step 4: Implement `retry_job` using current state**

Require `administrator.role == "admin"`, load the private source row, resolve `UserRecord`, and explicitly reject disabled owners. Check `store.can_use_ai(owner.principal)` and `store.can_read_book(...)`. Then run the same material/profile/template/cache calculation used by `submit` and call Task 1's atomic retry creator.

Treat a cached result as reusable only when its content key, `config_revision`, `template_id`, and `template_version` match the current request. When its ID is supplied to the store, return the new completed linked job without starting the worker. When an active job is returned, return `shared=True`. When a queued row is created, call `await start_worker()` and `wake_worker()`. Before returning, assert the mapped job has no `request_json` and do not attach the private source row to the result.

Do not reserve quota in this method; `_provider_call` remains the single point that reserves one unit for each real provider attempt.

- [ ] **Step 5: Run all AI reading tests**

Run: `python3 -m unittest tests.test_ai_reading tests.test_ai_client -v`

Expected: PASS, including dynamic context-window chunking and transient backoff tests already present in the worktree.

- [ ] **Step 6: Commit service-level retry**

```bash
git add epub_browser/ai_reading.py tests/test_ai_reading.py
git commit -m "feat: retry failed AI reading jobs safely"
```

---

### Task 3: Expose administrator job list and retry routes

**Files:**
- Modify: `tests/test_server.py`
- Modify: `epub_browser/server.py:560-650,1550-1745,2568-2605`

**Interfaces:**
- Consumes: `StateStore.list_admin_ai_jobs` and `AIReadingService.retry_job`.
- Produces: `GET /api/admin/ai/jobs` and `POST /api/admin/ai/jobs/{job_id}/retry`.

- [ ] **Step 1: Write authorization, pagination, and response-privacy API tests**

In `AdminAccountTests`, create jobs with a replay payload containing a sentinel string such as `PRIVATE_REPLAY_SENTINEL`. Assert:

```python
denied = self.member_client.get("/api/admin/ai/jobs")
listed = self.admin_client.get("/api/admin/ai/jobs?status=failed&page=1&page_size=10")
self.assertEqual(denied.status_code, 403)
self.assertEqual(listed.status_code, 200)
self.assertEqual(listed.json()["pagination"]["page_size"], 10)
self.assertNotIn("PRIVATE_REPLAY_SENTINEL", listed.text)
self.assertNotIn("request_json", listed.text)
```

Add invalid cases for page 0, non-numeric page, page size 101, and unknown status; each returns `400 invalid_ai_job_query`.

- [ ] **Step 2: Write retry route tests**

Patch `AIReadingService.retry_job` with `AsyncMock` to isolate route semantics. Assert administrator POST returns 202 for queued, 200 for cached/active shared completion, members receive 403, missing jobs receive 404, and requests without the current CSRF token receive 403.

- [ ] **Step 3: Run focused Server tests and verify failure**

Run: `python3 -m unittest tests.test_server.AdminAccountTests.test_admin_lists_paginated_ai_jobs_without_private_payload tests.test_server.AdminAccountTests.test_admin_retries_failed_ai_job_with_csrf tests.test_server.AdminAccountTests.test_admin_ai_job_query_validation -v`

Expected: FAIL with route not found.

- [ ] **Step 4: Implement query parsing and safe handlers**

Add a small integer parser that rejects booleans, signs, empty strings, zero, and values over the supplied maximum. The GET handler calls `require_admin`, validates status, calls the store, and returns:

```python
{
    "jobs": list(jobs),
    "pagination": {
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": (total + page_size - 1) // page_size,
    },
}
```

The retry handler calls `require_admin`, awaits `ai_reading.retry_job`, maps stable `AIReadingError` codes to 400/403/404/409/503, and returns 202 only when a new queued job was created.

- [ ] **Step 5: Register static administrator routes before dynamic AI reader routes**

Add:

```python
Route('/api/admin/ai/jobs', admin_ai_jobs, methods=['GET']),
Route('/api/admin/ai/jobs/{job_id}/retry', admin_ai_job_retry, methods=['POST']),
```

Keep `/api/ai/jobs/{job_id}` unchanged for authorized readers.

- [ ] **Step 6: Run administrator and security tests**

Run: `python3 -m unittest tests.test_server.AdminAccountTests tests.test_server.ServerAccountSecurityMatrixTests -v`

Expected: PASS.

- [ ] **Step 7: Commit administrator AI job APIs**

```bash
git add epub_browser/server.py tests/test_server.py
git commit -m "feat: expose administrator AI job operations"
```

---

### Task 4: Add localized semantic job-table markup

**Files:**
- Modify: `epub_browser/site.py:176-202`
- Modify: `epub_browser/assets/i18n.js`
- Modify: `tests/test_site.py`
- Modify: `tests/test_generated_reader_surfaces.py`
- Modify: `tests/test_i18n_coverage.py`

**Interfaces:**
- Consumes: existing administration modal and `window.EpubBrowserI18n`.
- Produces: DOM IDs `adminAiJobsStatus`, `adminAiJobsPageSize`, `adminAiJobsRefresh`, `adminAiJobsBody`, `adminAiJobsPagination`, and `adminAiJobsLive`.

- [ ] **Step 1: Write failing markup and i18n coverage tests**

Assert Server markup contains a `<table>` with `<thead>`, `<tbody id=adminAiJobsBody>`, localized filter labels, pagination container, and `aria-live=polite`; assert SSG markup contains none of these IDs. Extend the required-key set with every `admin.ai.jobs.*` key used by markup/JavaScript.

- [ ] **Step 2: Run markup tests and verify failure**

Run: `python3 -m unittest tests.test_site.SitePublicationTests.test_server_library_shell_bootstraps_server_data_clients tests.test_generated_reader_surfaces tests.test_i18n_coverage.I18nCoverageTests.test_account_and_administration_copy_exists_in_both_locales -v`

Expected: FAIL because the table and translations do not exist.

- [ ] **Step 3: Add the table structure below AI cache controls**

Use static semantic markup whose fallback text has matching `data-i18n` attributes. Include status options for all/queued/running/complete/failed/interrupted, page sizes 10/20/50/100, column headers, refresh, empty/loading row target, pagination target, and a visually hidden live region.

Keep the controls and live output addressable without relying on visual text:

```html
<label for="adminAiJobsStatus" data-i18n="admin.ai.jobs.statusFilter">Status</label>
<select id="adminAiJobsStatus">
  <option value="" data-i18n="admin.ai.jobs.status.all">All</option>
  <option value="failed" data-i18n="admin.ai.jobs.status.failed">Failed</option>
</select>
<button id="adminAiJobsRefresh" type="button" data-i18n="admin.ai.jobs.refresh">Refresh</button>
<div class="account-table-scroll">
  <table class="account-admin-table">
    <thead><!-- all localized column headers --></thead>
    <tbody id="adminAiJobsBody"></tbody>
  </table>
</div>
<nav id="adminAiJobsPagination" aria-label="AI job pages"
     data-i18n-aria-label="admin.ai.jobs.paginationLabel"></nav>
<p id="adminAiJobsLive" class="visually-hidden" aria-live="polite"></p>
```

- [ ] **Step 4: Add exact bilingual translation keys**

Add matching English and Simplified Chinese entries for the section title/description, filters, column names, statuses, progress, unknown book/user, retry action, retry success/conflict, empty/loading states, refresh, page summary, previous/next, and stable API error codes.

- [ ] **Step 5: Run markup and i18n tests**

Run: `python3 -m unittest tests.test_site tests.test_generated_reader_surfaces tests.test_i18n_coverage -v`

Expected: PASS.

- [ ] **Step 6: Commit job-table structure and copy**

```bash
git add epub_browser/site.py epub_browser/assets/i18n.js tests/test_site.py tests/test_generated_reader_surfaces.py tests/test_i18n_coverage.py
git commit -m "feat: add localized AI job administration table"
```

---

### Task 5: Implement table pagination, polling, and retry interaction

**Files:**
- Modify: `epub_browser/assets/auth.js:8-1125`
- Modify: `epub_browser/assets/account.css:529-1185`
- Modify: `tests/test_auth_ui.js`

**Interfaces:**
- Consumes: Task 3 API payloads and Task 4 DOM IDs/i18n keys.
- Produces: `loadAdminAiJobs()`, `retryAdminAiJob(jobId)`, `startAdminAiJobPolling()`, and `stopAdminAiJobPolling()` inside the auth module; exposes `loadAiJobs` and `retryAiJob` on the testable returned object.

- [ ] **Step 1: Write failing fetch/pagination/retry tests**

Use the existing `rootWithFetch` harness with stub controls. Assert opening the admin panel requests `/api/admin/ai/jobs?page=1&page_size=20`, changing status resets page to 1, next-page requests page 2, and retry sends:

```javascript
assert.deepEqual(calls.at(-1), {
  url: '/api/admin/ai/jobs/failed%2Fjob/retry',
  method: 'POST',
  csrf: 'admin-csrf',
});
```

Assert a pending retry disables only that row's button and a completed retry reloads the current filtered page.

- [ ] **Step 2: Write failing polling lifecycle tests**

Inject `root.setInterval` and `root.clearInterval` fakes. Assert one interval starts when the admin panel opens, no duplicate starts on repeated loads, it stops on close, stops while `document.hidden` is true, and restarts on visibility change only if the panel remains active.

- [ ] **Step 3: Run Node tests and verify failure**

Run: `node --test tests/test_auth_ui.js`

Expected: FAIL because job-table state and helpers do not exist.

- [ ] **Step 4: Implement isolated job-table state and rendering**

Add module state:

```javascript
var aiJobsState = { status: '', page: 1, pageSize: 20, totalPages: 0, loading: false };
var aiJobsPollTimer = null;
```

Build rows with `createElement` and `textContent` only. Format timestamps through a local safe formatter, render translated status/error codes, use a native `<progress max>` element, and never assign API text through `innerHTML`.

Clamp the current page to `Math.max(1, totalPages)` after responses. If the requested page is now above the last page, update state and issue exactly one follow-up request for the clamped page rather than rendering an empty stale page. Preserve filters during retry/refresh and guard stale responses with a monotonically increasing request generation.

- [ ] **Step 5: Implement visible-only polling**

Use a 10-second interval. Start only when the admin panel has class `active` and `document.hidden !== true`; stop on close and visibility hide. The interval calls `loadAdminAiJobs()` only when no previous job request is pending.

- [ ] **Step 6: Add responsive table styles**

Use existing account CSS variables. Add an overflow container, compact sticky header, status pills, right-aligned progress/action cells, 44px minimum interactive targets, focus-visible outlines, and narrow-screen minimum table width. Respect the existing reduced-motion block.

Keep the responsive behavior table-native:

```css
.account-table-scroll { overflow-x: auto; }
.account-admin-table { width: 100%; border-collapse: collapse; }
.account-admin-table thead th { position: sticky; top: 0; }
.account-admin-table button { min-height: 44px; }
@media (max-width: 720px) {
  .account-admin-table { min-width: 56rem; }
}
```

- [ ] **Step 7: Run JS syntax and UI tests**

Run: `node --check epub_browser/assets/auth.js`

Run: `node --test tests/test_auth_ui.js tests/test_i18n.js`

Expected: PASS without interval handles keeping Node alive.

- [ ] **Step 8: Commit job-table behavior and styles**

```bash
git add epub_browser/assets/auth.js epub_browser/assets/account.css tests/test_auth_ui.js
git commit -m "feat: manage AI jobs from the admin panel"
```

---

### Task 6: Verify AI job administration end to end

**Files:**
- Verify: `epub_browser/state.py`
- Verify: `epub_browser/ai_reading.py`
- Verify: `epub_browser/server.py`
- Verify: `epub_browser/site.py`
- Verify: `epub_browser/assets/auth.js`
- Verify: `epub_browser/assets/account.css`

**Interfaces:**
- Consumes: Tasks 1-5.
- Produces: a verified administrator job workflow ready for book-management work.

- [ ] **Step 1: Run focused Python suites**

Run: `python3 -m unittest tests.test_state tests.test_ai_reading tests.test_server.AdminAccountTests tests.test_site tests.test_generated_reader_surfaces tests.test_i18n_coverage -v`

Expected: PASS.

- [ ] **Step 2: Run focused Node suites**

Run: `node --test tests/test_auth_ui.js tests/test_i18n.js`

Expected: PASS.

- [ ] **Step 3: Run complete regression suites**

Run: `python3 -W ignore::ResourceWarning -m unittest discover -s tests -p 'test_*.py'`

Run: `node --test tests/*.js`

Run: `git diff --check`

Expected: all tests pass; `.server-content-revision` remains unchanged.

- [ ] **Step 4: Commit any verification-only fixture corrections**

If verification required fixture-only corrections, commit only those verified files:

```bash
git add tests
git commit -m "test: complete AI job administration coverage"
```

If no correction was required, leave the working tree unchanged and record the passing commands in the handoff.
