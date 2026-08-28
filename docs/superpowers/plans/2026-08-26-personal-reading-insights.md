# Personal Reading Insights Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add private Server-only per-book ratings/reviews and Screen Time-style, chapter-level actual-reading history without changing EPUB content caches or SSG behavior.

**Architecture:** Persist ratings and bounded active-reading sessions in the existing `StateStore` SQLite database. The Server owns identity, book authorization, chapter-label snapshots, validation, and summaries; small Server-only browser modules collect active time, render a private review editor, and render the insights page. Shared EPUB templates receive only narrow Server-mode hooks and keep SSG free of routes, controls, scripts, and assets for this feature.

**Tech Stack:** Python 3 + `sqlite3`/`zoneinfo`, Starlette, existing `StateStore` migration framework, vanilla ES5-style browser modules, Node’s built-in test runner, `unittest`, existing asset publisher and i18n runtime.

**Spec:** `docs/superpowers/specs/2026-08-26-personal-reading-insights-design.md`

## Global Constraints

- The feature applies only when `EpubBrowserMode` is `server`; SSG retains only its existing local progress and annotation capabilities.
- Ratings, reviews, sessions, totals, and history are visible only to their authenticated owner; APIs never accept a `user_id`.
- A rating is an integer from 1 through 5 and review text is trimmed to at most 10,000 Unicode characters.
- Count time only while document visibility, window focus, a selected chapter, and a qualifying reading interaction within 60 seconds all hold.
- Heartbeat cadence is 15 seconds; accept at most 20 active seconds per heartbeat; browser wall-clock timestamps are not authoritative.
- Store timestamps in UTC and present calendar buckets using the caller-supplied IANA timezone.
- Keep book and chapter title snapshots in SQLite session rows; do not write them into `book/<id>/content/`.
- Increase only `DB_SCHEMA_VERSION`; do not change `SERVER_OUTPUT_REVISION`, `.server-content-revision`, cached EPUB JSON, or reconversion logic.
- Add all visible strings to every existing locale and pass the repository’s literal UI sink coverage.
- Use hashed asset-manifest URLs and add all Server-only assets to `SERVER_ONLY_ASSET_PATHS` so SSG never publishes them.

---

## File structure

| File | Responsibility |
| --- | --- |
| `epub_browser/state.py` | Schema v14 migration, private review CRUD, idempotent session recording, timezone-aware summary queries. |
| `epub_browser/server.py` | Book authorization/resolution, request validation, review/session/insights APIs, insights document route. |
| `epub_browser/server_chrome.py` | Render a protected Server-only insights document using current asset manifest and existing account/locale chrome. |
| `epub_browser/processor.py` | Add small Server-only review and reading-session hooks to the shared book/chapter templates. |
| `epub_browser/site.py` | Add Server-only Reading insights navigation to the dynamically rendered library shell. |
| `epub_browser/asset_publisher.py` | Exclude insight/review/session assets from SSG publication. |
| `epub_browser/assets/reading-sessions.js` | Testable active-reading state machine, same-browser tab coordination, bounded retry buffer, and heartbeat client. |
| `epub_browser/assets/book-reviews.js` / `.css` | Private book review editor and owner-star display. |
| `epub_browser/assets/reading-insights.js` / `.css` | Fetch/render period summaries and selectable chronological day sessions. |
| `epub_browser/assets/i18n.js` | Five-locale copy for all new controls, announcements, error states, and headings. |
| `tests/test_state.py` | Schema, migration, CRUD, idempotency, timezone aggregation, and owner isolation tests. |
| `tests/test_server.py` | Auth, CSRF, book access, payload validation, API contract, and protected-page tests. |
| `tests/test_reading_sessions.js` | Active-time state-machine, retry, idempotency payload, unload, and tab-coordination tests. |
| `tests/test_book_reviews.js` | Review UI request/render/delete tests. |
| `tests/test_reading_insights.js` | Insights client period/day selection and safe rendering tests. |
| `tests/test_asset_publisher.py`, `tests/test_ssg.py`, `tests/test_generated_reader_surfaces.py`, `tests/test_i18n_coverage.py`, `tests/test_i18n.js` | Server-only asset, SSG boundary, shared template, and translation regression tests. |

## Task 1: Add schema v14 and private review persistence

**Files:**
- Modify: `epub_browser/state.py: DB_SCHEMA_VERSION, StateStore.initialize, schema helpers, StateStore methods`
- Modify: `tests/test_state.py: StateStoreTests`

**Interfaces:**
- Produces: `StateStore.get_book_review(book_id: str, user_id: str) -> dict | None`
- Produces: `StateStore.upsert_book_review(book_id: str, user_id: str, rating: int, review_text: str) -> dict`
- Produces: `StateStore.delete_book_review(book_id: str, user_id: str) -> None`
- Produces: database schema version `14` with `book_reviews` and `reading_sessions`; Task 2 adds their write/query behavior.

- [ ] **Step 1: Write the failing schema and review persistence tests**

```python
def test_v14_creates_private_reviews_and_sessions_tables(self):
    with self.store._connection() as connection:
        self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 14)
        self.assertEqual(
            table_columns(connection, "book_reviews"),
            {"user_id", "book_id", "rating", "review_text", "created_at", "updated_at"},
        )
        self.assertTrue({"reading_sessions", "book_reviews"} <= {
            row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        })

def test_book_review_is_upserted_validated_and_owner_scoped(self):
    self.store.resolve_book("book-1", "source.epub", "fingerprint", {})
    saved = self.store.upsert_book_review("book-1", self.owner.user_id, 5, "  Excellent.  ")
    self.assertEqual(saved["rating"], 5)
    self.assertEqual(saved["review_text"], "Excellent.")
    self.assertEqual(self.store.get_book_review("book-1", self.owner.user_id), saved)
    with self.assertRaises(ValueError):
        self.store.upsert_book_review("book-1", self.owner.user_id, 0, "")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m unittest tests.test_state.StateStoreTests.test_v14_creates_private_reviews_and_sessions_tables tests.test_state.StateStoreTests.test_book_review_is_upserted_validated_and_owner_scoped -v`

Expected: FAIL because schema version 14 and review store methods do not exist.

- [ ] **Step 3: Implement the minimal v14 schema and review methods**

Add `DB_SCHEMA_VERSION = 14`, create both new tables from the latest-schema path, and run `_migrate_schema_v14(connection, version)` after v13 migrations. Give `book_reviews` the exact constraints below and make its update atomic.

```python
connection.execute("""
    CREATE TABLE IF NOT EXISTS book_reviews (
        user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        book_id TEXT NOT NULL REFERENCES books(book_id) ON DELETE CASCADE,
        rating INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5),
        review_text TEXT NOT NULL CHECK(length(review_text) <= 10000),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (user_id, book_id)
    )
""")

def upsert_book_review(self, book_id, user_id, rating, review_text):
    if isinstance(rating, bool) or not isinstance(rating, int) or not 1 <= rating <= 5:
        raise ValueError("rating must be an integer from 1 through 5")
    if not isinstance(review_text, str):
        raise ValueError("review text must be a string")
    review_text = review_text.strip()
    if len(review_text) > 10_000:
        raise ValueError("review text is too long")
    with self._connection() as connection:
        self._require_user(connection, user_id)
        self._require_active_book(connection, book_id)
        connection.execute(
            "INSERT INTO book_reviews (user_id, book_id, rating, review_text) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(user_id, book_id) DO UPDATE SET rating = excluded.rating, "
            "review_text = excluded.review_text, updated_at = CURRENT_TIMESTAMP",
            (user_id, book_id, rating, review_text),
        )
```

Create `reading_sessions` in that same v14 helper so every database reaching version 14 has the complete schema:

```sql
CREATE TABLE IF NOT EXISTS reading_sessions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    book_id TEXT NOT NULL REFERENCES books(book_id) ON DELETE CASCADE,
    chapter_index INTEGER NOT NULL CHECK(chapter_index >= 0),
    book_title_snapshot TEXT NOT NULL CHECK(length(book_title_snapshot) > 0),
    chapter_label_snapshot TEXT NOT NULL CHECK(length(chapter_label_snapshot) > 0),
    started_at REAL NOT NULL,
    ended_at REAL NOT NULL CHECK(ended_at >= started_at),
    active_seconds INTEGER NOT NULL CHECK(active_seconds >= 1),
    client_id TEXT NOT NULL CHECK(length(client_id) BETWEEN 1 AND 128),
    last_client_sequence INTEGER NOT NULL CHECK(last_client_sequence >= 0),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

Use foreign-key cascade for user/book deletion. Add `idx_book_reviews_user_updated` on `(user_id, updated_at DESC, book_id)`, `idx_reading_sessions_user_started` on `(user_id, started_at, id)`, and `idx_reading_sessions_user_book_chapter_started` on `(user_id, book_id, chapter_index, started_at)` through a v14 index helper instead of changing the v11 index contract.

- [ ] **Step 4: Add migration-preservation and delete tests**

```python
def test_v13_upgrade_creates_empty_review_tables_without_losing_progress(self):
    database = Path(self.temporary.name, "v13.db")
    self._create_v13_database_with_progress(database)
    store = StateStore(database)
    store.initialize()
    self.assertEqual(store.get_reading_progress("admin", "legacy-book"), 4)
    self.assertIsNone(store.get_book_review("legacy-book", "admin"))

def test_delete_book_review_cannot_delete_another_users_row(self):
    book = self._active_book("book-1")
    self.store.upsert_book_review(book.book_id, self.owner.user_id, 4, "Mine")
    other = self.store.create_user("other", hash_password("secret"))
    self.store.delete_book_review(book.book_id, other.user_id)
    self.assertEqual(self.store.get_book_review(book.book_id, self.owner.user_id)["rating"], 4)
```

- [ ] **Step 5: Run the focused state tests**

Run: `python -m unittest tests.test_state -v`

Expected: PASS, including pre-v14 migration fixtures and all existing state tests.

- [ ] **Step 6: Commit the independently working persistence layer**

```bash
git add epub_browser/state.py tests/test_state.py
git commit -m "feat: persist private book reviews"
```

## Task 2: Record idempotent reading sessions and produce private summaries

**Files:**
- Modify: `epub_browser/state.py: StateStore session and aggregation methods`
- Modify: `tests/test_state.py: StateStoreTests`

**Interfaces:**
- Consumes: Task 1’s schema v14 initializer and owner/book foreign-key rules.
- Produces: `StateStore.record_reading_heartbeat(*, user_id: str, book_id: str, client_id: str, client_sequence: int, chapter_index: int, active_seconds: int, book_title: str, chapter_label: str, received_at: datetime) -> dict`
- Produces: `StateStore.reading_insights(user_id: str, period: str, anchor_date: date, timezone_name: str) -> dict`

- [ ] **Step 1: Write the failing session and aggregation tests**

```python
def test_heartbeat_is_idempotent_and_changes_chapter_session(self):
    first = self.store.record_reading_heartbeat(
        user_id=self.owner.user_id, book_id="book-1", client_id="tab-a",
        client_sequence=1, chapter_index=2, active_seconds=15,
        book_title="Book", chapter_label="Chapter 3", received_at=_utc("2026-08-15T00:00:15Z"),
    )
    duplicate = self.store.record_reading_heartbeat(
        user_id=self.owner.user_id, book_id="book-1", client_id="tab-a",
        client_sequence=1, chapter_index=2, active_seconds=15,
        book_title="Book", chapter_label="Chapter 3", received_at=_utc("2026-08-15T00:00:16Z"),
    )
    changed = self.store.record_reading_heartbeat(
        user_id=self.owner.user_id, book_id="book-1", client_id="tab-a",
        client_sequence=2, chapter_index=3, active_seconds=15,
        book_title="Book", chapter_label="Chapter 4", received_at=_utc("2026-08-15T00:00:30Z"),
    )
    self.assertEqual(first["active_seconds"], 15)
    self.assertEqual(duplicate["active_seconds"], 15)
    self.assertNotEqual(first["id"], changed["id"])

def test_insights_use_callers_timezone_and_merge_overlapping_device_sessions(self):
    # Seed two overlapping UTC sessions that render on the same Asia/Shanghai day.
    result = self.store.reading_insights(self.owner.user_id, "day", date(2026, 8, 15), "Asia/Shanghai")
    self.assertEqual(result["total_active_seconds"], 1800)
    self.assertEqual(result["days"][0]["date"], "2026-08-15")
    self.assertEqual(result["sessions"][0]["chapter_label"], "Chapter 3")
```

- [ ] **Step 2: Run the session tests to verify they fail**

Run: `python -m unittest tests.test_state.StateStoreTests.test_heartbeat_is_idempotent_and_changes_chapter_session tests.test_state.StateStoreTests.test_insights_use_callers_timezone_and_merge_overlapping_device_sessions -v`

Expected: FAIL because neither session API exists.

- [ ] **Step 3: Implement the idempotent append/update path over Task 1’s session table**

In one immediate transaction, select the latest row for `(user_id, client_id)`. Reject a heartbeat whose `client_sequence` is not greater than the row’s `last_client_sequence`. Extend that row only when its book and chapter match and its `ended_at` is within 20 seconds of the receipt time; otherwise insert a UUID row with `started_at = received_at - active_seconds`. For an accepted extension, set `ended_at = received_at`, add the bounded increment to the stored `active_seconds`, and update `last_client_sequence`/`updated_at`.

```python
def record_reading_heartbeat(self, *, user_id, book_id, client_id,
                             client_sequence, chapter_index, active_seconds,
                             book_title, chapter_label, received_at):
    if not isinstance(active_seconds, int) or isinstance(active_seconds, bool) or not 1 <= active_seconds <= 20:
        raise ValueError("active seconds must be an integer from 1 through 20")
    with self._connection() as connection:
        self._require_user(connection, user_id)
        self._require_active_book(connection, book_id)
        previous = connection.execute(
            "SELECT * FROM reading_sessions WHERE user_id = ? AND client_id = ? "
            "ORDER BY ended_at DESC, id DESC LIMIT 1", (user_id, client_id)
        ).fetchone()
        if previous is not None and client_sequence <= previous["last_client_sequence"]:
            return self._reading_session_data(previous)
        compatible = previous is not None and previous["book_id"] == book_id and previous["chapter_index"] == chapter_index and received_at.timestamp() - previous["ended_at"] <= 20
        if compatible:
            connection.execute("UPDATE reading_sessions SET ended_at = ?, active_seconds = active_seconds + ?, last_client_sequence = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (received_at.timestamp(), active_seconds, client_sequence, previous["id"]))
            return self._reading_session_data(connection.execute("SELECT * FROM reading_sessions WHERE id = ?", (previous["id"],)).fetchone())
        session_id = str(uuid.uuid4())
        connection.execute("INSERT INTO reading_sessions (id, user_id, book_id, chapter_index, book_title_snapshot, chapter_label_snapshot, started_at, ended_at, active_seconds, client_id, last_client_sequence) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (session_id, user_id, book_id, chapter_index, book_title, chapter_label, received_at.timestamp() - active_seconds, received_at.timestamp(), active_seconds, client_id, client_sequence))
        return self._reading_session_data(connection.execute("SELECT * FROM reading_sessions WHERE id = ?", (session_id,)).fetchone())
```

- [ ] **Step 4: Implement deterministic insight aggregation**

Use `datetime`, `timezone`, and `zoneinfo.ZoneInfo`; reject unknown zones with `ValueError`. Translate the period/anchor into inclusive local-day bounds, convert those bounds to UTC epochs, fetch only that owner’s overlapping rows, clip each session to the selected range, and return:

```python
{
    "period": "week",
    "anchor_date": "2026-08-15",
    "timezone": "Asia/Shanghai",
    "total_active_seconds": 11880,
    "top_book": {"book_id": "book-1", "title": "Book", "active_seconds": 8760},
    "days": [{"date": "2026-08-12", "active_seconds": 1080}],
    "sessions": [{"id": "session-7f03", "started_at": "2026-08-15T08:18:00Z", "active_seconds": 1860,
                  "book_id": "book-1", "book_title": "Book", "chapter_index": 5,
                  "chapter_label": "Chapter 6"}],
}
```

For the range total, merge overlapping `[started_at, ended_at]` intervals before measuring wall-clock time; cap each merged span’s contribution by the sum of the sessions’ active seconds so a sparse heartbeat gap cannot inflate time. Attribute per-book and per-day totals by clipping the same intervals at book and local-day bounds, distributing a session’s active seconds proportionally by clipped wall time with deterministic integer rounding whose pieces sum to the original active seconds.

- [ ] **Step 5: Add boundary tests and run the state suite**

```python
def test_insights_split_session_at_local_midnight_without_losing_seconds(self):
    result = self.store.reading_insights(self.owner.user_id, "week", date(2026, 8, 16), "Asia/Shanghai")
    self.assertEqual(sum(day["active_seconds"] for day in result["days"]), 20)

def test_heartbeat_rejects_invalid_owner_book_sequence_and_increment(self):
    values = {
        "user_id": self.owner.user_id, "book_id": "book-1", "client_id": "tab-a",
        "client_sequence": 1, "chapter_index": 0, "active_seconds": 15,
        "book_title": "Book", "chapter_label": "Chapter 1",
        "received_at": _utc("2026-08-15T00:00:15Z"),
    }
    with self.assertRaises(ValueError):
        self.store.record_reading_heartbeat(**(values | {"client_sequence": -1}))
    with self.assertRaises(ValueError):
        self.store.record_reading_heartbeat(**(values | {"active_seconds": 21}))
```

Run: `python -m unittest tests.test_state -v`

Expected: PASS, including DST/timezone, midnight, idempotency, isolation, and migration coverage.

- [ ] **Step 6: Commit session storage and summary logic**

```bash
git add epub_browser/state.py tests/test_state.py
git commit -m "feat: record private reading sessions"
```

## Task 3: Expose authorized review, heartbeat, and insights Server APIs

**Files:**
- Modify: `epub_browser/server.py: validation helpers, route handlers, routes list`
- Modify: `tests/test_server.py: authenticated Server API tests`

**Interfaces:**
- Consumes: Task 1 review methods and Task 2 session methods.
- Produces: `GET|PUT|DELETE /api/book-reviews/{book_id}`, `POST /api/reading-sessions/{book_id}/heartbeat`, and `GET /api/reading-insights`.

- [ ] **Step 1: Write the failing API tests**

```python
def test_book_review_api_is_private_and_requires_book_access(self):
    saved = self.client.put("/api/book-reviews/book", json={"rating": 5, "review_text": "Excellent"})
    self.assertEqual(saved.status_code, 200)
    self.assertEqual(saved.json()["review"]["rating"], 5)
    self.assertEqual(self.client.get("/api/book-reviews/book").json()["review"]["review_text"], "Excellent")
    self.assertEqual(self.client.delete("/api/book-reviews/book").status_code, 204)

def test_reading_heartbeat_requires_csrf_and_is_idempotent(self):
    payload = {"client_id": "tab-a", "client_sequence": 1, "chapter_index": 0, "active_seconds": 15}
    first = self.client.post("/api/reading-sessions/book/heartbeat", json=payload)
    again = self.client.post("/api/reading-sessions/book/heartbeat", json=payload)
    self.assertEqual(first.status_code, 200)
    self.assertEqual(again.json()["session"]["active_seconds"], 15)
```

- [ ] **Step 2: Run the API tests to verify they fail**

Run: `python -m unittest tests.test_server.ServerTests.test_book_review_api_is_private_and_requires_book_access tests.test_server.ServerTests.test_reading_heartbeat_requires_csrf_and_is_idempotent -v`

Expected: FAIL with route `404`.

- [ ] **Step 3: Add route helpers and handlers with the existing authorization order**

Create a local helper that obtains `principal = require_principal(request)`, verifies `store.can_read_book(principal.user_id, principal.role, book_id)`, and returns `forbidden_book_response()` before touching any review/session row. Use `bounded_public_json_object` for mutations, reuse the existing CSRF middleware/auth wrapper, and map invalid fields to stable 400 codes:

```python
async def reading_session_heartbeat(request):
    principal = require_principal(request)
    book_id = request.path_params["book_id"]
    if not store.can_read_book(principal.user_id, principal.role, book_id):
        return forbidden_book_response()
    data, error = await bounded_public_json_object(request, maximum_size=4096)
    if error:
        return response(error_payload(error, "Invalid reading session"), 400)
    client_id = data.get("client_id")
    client_sequence = data.get("client_sequence")
    chapter_index = data.get("chapter_index")
    active_seconds = data.get("active_seconds")
    if (not isinstance(client_id, str) or not 1 <= len(client_id) <= 128 or
            isinstance(client_sequence, bool) or not isinstance(client_sequence, int) or client_sequence < 0 or
            isinstance(chapter_index, bool) or not isinstance(chapter_index, int) or chapter_index < 0 or
            isinstance(active_seconds, bool) or not isinstance(active_seconds, int) or not 1 <= active_seconds <= 20):
        return response(error_payload("invalid_reading_session", "Invalid reading session"), 400)
    book_title, chapter_label = authorized_chapter_snapshot(book_id, chapter_index)
    session = store.record_reading_heartbeat(
        user_id=principal.user_id, book_id=book_id, client_id=client_id,
        client_sequence=client_sequence, chapter_index=chapter_index,
        active_seconds=active_seconds, book_title=book_title,
        chapter_label=chapter_label, received_at=datetime.now(timezone.utc),
    )
    return response({"session": session})
```

Define `authorized_chapter_snapshot(book_id, chapter_index)` beside this handler: it loads `ServerPageRenderer(base_directory, book_id)`, validates the requested cached chapter using `render_chapter(chapter_index)`, and returns Server-derived `metadata.json` title plus that chapter’s cached title. Implement `GET` review as `{ "review": null | record }`, `PUT` as `{ "review": record }`, and delete as `Response(status_code=204)`. The insights handler accepts only `period in {"day", "week", "month"}`, an ISO `anchor`, and a valid IANA `timezone`; it calls `store.reading_insights(principal.user_id, period, anchor_date, timezone_name)` and returns `{ "insights": insight_data }`.

Add the explicit routes before `Route('/api/{path:path}', annotations, methods=['GET', 'POST', 'PUT', 'DELETE'])` so they cannot be consumed by the annotation fallback.

- [ ] **Step 4: Add security and validation tests**

```python
def test_review_and_session_routes_do_not_expose_restricted_books(self):
    restricted = self._restrict_book_to_other_member("book")
    self.assertEqual(self.client.get(f"/api/book-reviews/{restricted}").status_code, 403)
    self.assertEqual(self.client.post(f"/api/reading-sessions/{restricted}/heartbeat", json={}).status_code, 403)

def test_insights_reject_invalid_period_anchor_and_timezone(self):
    for query in ("period=year&anchor=2026-08-15&timezone=UTC", "period=week&anchor=nope&timezone=UTC", "period=week&anchor=2026-08-15&timezone=Bad/Zone"):
        self.assertEqual(self.client.get("/api/reading-insights?" + query).status_code, 400)
```

Test an unauthenticated client (401), a second authenticated user (no review/session leakage), malformed JSON/content type, invalid review length/rating, not-ready mutations (503), and a valid chapter label resolved from a cached Server book.

- [ ] **Step 5: Run the Server test module**

Run: `python -m unittest tests.test_server -v`

Expected: PASS, including current reading-progress and annotation routes.

- [ ] **Step 6: Commit the protected API surface**

```bash
git add epub_browser/server.py tests/test_server.py
git commit -m "feat: expose private reading insights APIs"
```

## Task 4: Build and test the active-reading browser tracker

**Files:**
- Create: `epub_browser/assets/reading-sessions.js`
- Create: `tests/test_reading_sessions.js`

**Interfaces:**
- Consumes: `window.EpubBrowserMode`, `window.EpubBrowserAuth.fetch`, active book/chapter data attributes, and Task 3’s heartbeat route.
- Produces: `window.EpubReadingSessions.createTracker(options)` with `recordInteraction()`, `setChapter(chapterIndex, chapterLabel)`, `setVisible(isVisible)`, `setFocused(isFocused)`, `flush(keepalive)`, and `destroy()`.

- [ ] **Step 1: Write the failing Node tests for the pure state machine**

```javascript
test('counts only active, visible, focused reading after a qualifying interaction', () => {
  let clock = 0;
  const sent = [];
  const tracker = Sessions.createTracker({ now: () => clock, send: item => sent.push(item), idleMs: 60000, heartbeatMs: 15000 });
  tracker.setChapter(2, 'Chapter 3');
  tracker.recordInteraction();
  clock += 15000;
  tracker.flush();
  assert.deepEqual(sent[0], { chapter_index: 2, active_seconds: 15, client_sequence: 1 });
  tracker.setVisible(false);
  clock += 15000;
  tracker.flush();
  assert.equal(sent.length, 1);
});

test('idle timeout, chapter change, and retried sequence never double count', async () => {
  let clock = 0;
  const sent = [];
  const tracker = Sessions.createTracker({ now: () => clock, send: item => { sent.push(item); return Promise.reject(new Error('offline')); }, idleMs: 60000, heartbeatMs: 15000 });
  tracker.setChapter(2, 'Chapter 3'); tracker.recordInteraction(); clock = 15000;
  await tracker.flush();
  clock = 76000; tracker.flush();
  tracker.setChapter(3, 'Chapter 4'); tracker.recordInteraction(); clock = 91000;
  await tracker.flush();
  assert.deepEqual(sent.map(item => item.client_sequence), [1, 1, 2]);
  assert.equal(sent[2].chapter_index, 3);
});
```

- [ ] **Step 2: Run the tracker tests to verify they fail**

Run: `node --test tests/test_reading_sessions.js`

Expected: FAIL because `reading-sessions.js` does not exist.

- [ ] **Step 3: Implement the isolated state machine and transport adapter**

Use the project’s UMD-style browser wrapper. Keep timing calculations in injected `now()` and `schedule()` dependencies so Node tests do not need a real DOM. Track visibility, focus, latest qualifying interaction, selected chapter, accumulated unsent seconds, monotonically increasing sequence, and one in-flight request. Start only when `EpubBrowserMode === 'server'` and auth fetch exists.

```javascript
function isActive(state, now) {
  return state.visible && state.focused && state.chapterIndex !== null &&
    state.lastInteraction !== null && now - state.lastInteraction < state.idleMs;
}

function heartbeatPayload(state, seconds) {
  return {
    client_id: state.clientId,
    client_sequence: state.nextSequence,
    chapter_index: state.chapterIndex,
    active_seconds: Math.min(20, seconds)
  };
}
```

Listen for `scroll`, reader page-turn events, keyboard navigation, `visibilitychange`, `focus`, `blur`, `pagehide`, and dynamic chapter navigation events. Store at most four unacknowledged payloads in `sessionStorage`; remove a payload only after a successful response. Use `BroadcastChannel('epub-reading-sessions')` when available and a `storage` event fallback to announce the active tab; only the most recently focused tab emits heartbeats. `flush(true)` sends the current bounded increment with `keepalive: true` and never blocks navigation.

- [ ] **Step 4: Add browser-state regression tests**

```javascript
test('only the elected focused tab emits a heartbeat', () => {
  const channel = createFakeChannel();
  const first = Sessions.createTracker({ channel, clientId: 'tab-a', now: () => 0, send() {} });
  const second = Sessions.createTracker({ channel, clientId: 'tab-b', now: () => 0, send() {} });
  first.setFocused(true); second.setFocused(true);
  assert.equal(first.isLeader(), false);
  assert.equal(second.isLeader(), true);
});
```

Cover focus/visibility resume requiring new interaction, `pagehide` keepalive, 20-second caps, offline queue cap, retry sequence preservation, and cleanup of timers/listeners/channel.

- [ ] **Step 5: Run the tracker tests**

Run: `node --test tests/test_reading_sessions.js`

Expected: PASS.

- [ ] **Step 6: Commit the tracker**

```bash
git add epub_browser/assets/reading-sessions.js tests/test_reading_sessions.js
git commit -m "feat: track active reading sessions in browser"
```

## Task 5: Add the private book rating/review UI and reader hooks

**Files:**
- Create: `epub_browser/assets/book-reviews.js`
- Create: `epub_browser/assets/book-reviews.css`
- Create: `tests/test_book_reviews.js`
- Modify: `epub_browser/processor.py: create_index_page, create_chapter_template`
- Modify: `epub_browser/asset_publisher.py: SERVER_ONLY_ASSET_PATHS`
- Modify: `tests/test_generated_reader_surfaces.py`
- Modify: `tests/test_asset_publisher.py`

**Interfaces:**
- Consumes: Task 3 review API; Task 4 tracker; existing `EpubBrowserAuth.fetch`, notification, i18n, and dynamic Server book identity.
- Produces: `window.EpubBookReviews.mount(root, bookId)` and a Server-only review panel on a book detail page; `window.EpubReadingSessions.createTracker(options)` mounted on Server chapter pages.

- [ ] **Step 1: Write failing template and UI tests**

```python
def test_server_book_home_contains_review_hook_but_ssg_book_home_does_not(self):
    self.assertIn('data-book-reviews', self.server_index)
    self.assertIn('/assets/book-reviews.js', self.server_index)
    self.assertNotIn('data-book-reviews', self.ssg_index)

def test_server_chapter_contains_reading_session_context_but_ssg_does_not(self):
    self.assertIn('data-reading-session', self.server_chapter)
    self.assertNotIn('reading-sessions.js', self.ssg_chapter)
```

```javascript
test('review editor loads, saves, and deletes only the current book review', async () => {
  const client = loadReviewClient({ review: { rating: 4, review_text: 'Useful' } });
  await client.mount('book-id');
  assert.equal(client.rating.value, '4');
  await client.save(5, 'Excellent');
  assert.deepEqual(client.requests.at(-1).body, { rating: 5, review_text: 'Excellent' });
});
```

- [ ] **Step 2: Run the failing tests**

Run: `python -m unittest tests.test_generated_reader_surfaces -v && node --test tests/test_book_reviews.js`

Expected: FAIL because no hooks or review module exist.

- [ ] **Step 3: Add Server-only template hooks and assets**

In `create_index_page`, render a `<section data-book-reviews data-book-id="…">` after the existing book metadata/controls only when `deployment_mode == 'server'`. Pass `book-reviews.css` and `book-reviews.js` through the current asset manifest, not a version query. In `create_chapter_template`, add only when Server mode:

```html
<meta data-reading-session
      data-book-id="{book_id_attribute}"
      data-chapter-index="{chapter_index}"
      data-chapter-label="{chapter_title_attribute}">
<script src="/assets/reading-sessions.js" defer></script>
```

Mount the tracker after authentication/cache-boundary initialization and feed it chapter changes from both normal links and continuous-reader events. Do not add review controls to chapter pages. Mark the four new CSS/JS files as `SERVER_ONLY_ASSET_PATHS`; extend publisher tests to prove they are absent from SSG manifests and immutable output.

- [ ] **Step 4: Implement the review module with safe DOM APIs**

Render rating stars as radio inputs, a labelled textarea with `maxlength="10000"`, save/delete controls, a live region, and an owner-only star summary. Build all dynamic UI using `createElement` and `textContent`; do not use `innerHTML` for review values. Use `EpubBrowserAuth.fetch` with the exact review API, disable mutation controls during a request, surface only translated generic error text, and restore saved fields after a failed write.

- [ ] **Step 5: Run focused UI, asset, and template tests**

Run: `node --test tests/test_book_reviews.js && python -m unittest tests.test_generated_reader_surfaces tests.test_asset_publisher -v`

Expected: PASS; SSG snapshots contain neither review/session asset nor `data-*` feature hook.

- [ ] **Step 6: Commit review UI and reader integration hooks**

```bash
git add epub_browser/assets/book-reviews.js epub_browser/assets/book-reviews.css epub_browser/processor.py epub_browser/asset_publisher.py tests/test_book_reviews.js tests/test_generated_reader_surfaces.py tests/test_asset_publisher.py
git commit -m "feat: add private book review controls"
```

## Task 6: Render the protected reading-insights page and client

**Files:**
- Create: `epub_browser/assets/reading-insights.js`
- Create: `epub_browser/assets/reading-insights.css`
- Create: `tests/test_reading_insights.js`
- Modify: `epub_browser/server_chrome.py: render_reading_insights_document`
- Modify: `epub_browser/server.py: GET /reading-insights route`
- Modify: `epub_browser/site.py: Server-only library navigation`
- Modify: `epub_browser/asset_publisher.py: SERVER_ONLY_ASSET_PATHS`
- Modify: `tests/test_server.py`, `tests/test_generated_reader_surfaces.py`, `tests/test_asset_publisher.py`

**Interfaces:**
- Consumes: Task 3 `GET /api/reading-insights` and published asset manifest.
- Produces: an authenticated HTML page at `/reading-insights` and `window.EpubReadingInsights.mount(root)`.

- [ ] **Step 1: Write failing page and client tests**

```python
def test_reading_insights_document_requires_login_and_uses_current_asset_manifest(self):
    anonymous = TestClient(self.app)
    self.addCleanup(anonymous.close)
    self.assertEqual(anonymous.get('/reading-insights').status_code, 401)
    page = self.client.get('/reading-insights')
    self.assertEqual(page.status_code, 200)
    self.assertIn('data-reading-insights', page.text)
    self.assertRegex(page.text, r'/assets/immutable/reading-insights\.[0-9a-f]{12}\.js')
```

```javascript
test('selecting a day fetches and safely renders chronological sessions', async () => {
  const page = loadInsightsClient();
  await page.mount();
  page.selectDay('2026-08-15');
  assert.equal(page.sessionRows[0].textContent, '08:18 Book Chapter 6 31 min');
});
```

- [ ] **Step 2: Run the page and client tests to verify they fail**

Run: `python -m unittest tests.test_server.ServerTests.test_reading_insights_document_requires_login_and_uses_current_asset_manifest -v && node --test tests/test_reading_insights.js`

Expected: FAIL with `404` and missing client module.

- [ ] **Step 3: Implement document rendering and routing**

Add `render_reading_insights_document(assets: PublishedAssets, urls: SiteURLs) -> str` in `server_chrome.py`. It must include the existing i18n/auth/theme/locale/account chrome, links to `assets.url_for('reading-insights.css')` and `assets.url_for('reading-insights.js')`, a `<main data-reading-insights>` root, accessible period buttons, a selected-day heading/live region, and no user data in the HTML response. In `server.py`, load the current manifest using the same validated manifest pattern as `library_index`, wrap the markup in `HTMLResponse(markup, headers={'Cache-Control': 'no-cache'})`, call `apply_reader_security_headers`, and register `Route('/reading-insights', reading_insights_page, methods=['GET'])` before the catch-all file route.

Add a Server-only `<a class="app-nav-link" href="/reading-insights" data-i18n="readingInsights.navigation">Reading insights</a>` beside the existing library navigation; do not insert it in SSG rendering.

- [ ] **Step 4: Implement client rendering and accessibility**

On mount, derive `Intl.DateTimeFormat().resolvedOptions().timeZone`, fetch the default week with the current ISO local date, and fetch only on a new period/anchor selection. Render total, top book, day buttons, and selected-day session list with `textContent`. Use `aria-pressed` for the selected period/day, `aria-live="polite"` for asynchronous summary changes, translated loading/empty/error text, and `Intl.DateTimeFormat`/`Intl.DurationFormat` fallback helpers for locale-aware values. Do not log or retain response data outside the private page lifetime.

- [ ] **Step 5: Run focused page, client, and boundary tests**

Run: `node --test tests/test_reading_insights.js && python -m unittest tests.test_server tests.test_generated_reader_surfaces tests.test_asset_publisher -v`

Expected: PASS; anonymous requests are rejected, authenticated requests receive no-cache page chrome, and SSG output has no insights link/assets.

- [ ] **Step 6: Commit the reading-insights page**

```bash
git add epub_browser/server_chrome.py epub_browser/server.py epub_browser/site.py epub_browser/asset_publisher.py epub_browser/assets/reading-insights.js epub_browser/assets/reading-insights.css tests/test_reading_insights.js tests/test_server.py tests/test_generated_reader_surfaces.py tests/test_asset_publisher.py
git commit -m "feat: add private reading insights page"
```

## Task 7: Complete translations, SSG boundaries, and full verification

**Files:**
- Modify: `epub_browser/assets/i18n.js: all five locale dictionaries`
- Modify: `tests/test_i18n_coverage.py: FIRST_PARTY and namespace mapping`
- Modify: `tests/test_i18n.js: translation contract assertions`
- Modify: `tests/test_ssg.py`, `tests/test_mode_integration.py`, `README.md`, `docs/readme/README.zh-CN.md`

**Interfaces:**
- Consumes: all feature hooks/assets/routes from Tasks 1–6.
- Produces: complete localized copy, documented Server-only data placement, and release-level regression evidence.

- [ ] **Step 1: Write the failing localization and SSG-boundary tests**

```python
def test_server_only_reading_insight_assets_are_never_emitted_by_ssg(self):
    manifest = self._ssg_manifest()
    for logical_name in ('book-reviews.js', 'book-reviews.css', 'reading-sessions.js', 'reading-insights.js', 'reading-insights.css'):
        self.assertNotIn(logical_name, manifest)
```

```javascript
test('translates every personal reading insights key in all locales', () => {
  ['en', 'zh-CN', 'zh-TW', 'ko', 'ja'].forEach(locale => {
    ['readingInsights.navigation', 'readingInsights.title', 'bookReview.heading', 'bookReview.save'].forEach(key => {
      assert.notEqual(dictionaries[locale][key], undefined, `${locale}:${key}`);
    });
  });
});
```

- [ ] **Step 2: Run the new boundary tests to verify they fail**

Run: `python -m unittest tests.test_ssg tests.test_i18n_coverage -v && node --test tests/test_i18n.js`

Expected: FAIL until all assets/keys are registered and exclusions are complete.

- [ ] **Step 3: Add complete five-locale copy and literal-sink coverage**

Add the same key shape to `en`, `zh-CN`, `zh-TW`, `ko`, and `ja` for: review heading/help/rating label/textarea/save/delete/deleted/saved/error; insights navigation/title/range names/total/top book/no sessions/loading/error; daily session start/book/chapter/duration; and tracker persistence/error announcements. Add `book-reviews.js`, `reading-sessions.js`, and `reading-insights.js` to `FIRST_PARTY`; map the two UI modules to their `bookReview.` and `readingInsights.` namespaces. Keep error codes internal and translate only user-facing messages.

Update the English and Simplified Chinese READMEs’ Server data-placement table to list “private ratings/reviews and reading-session history” as authenticated SQLite data, and state that detailed session history is never emitted by SSG.

- [ ] **Step 4: Add complete mode-integration checks**

Extend Server integration coverage to convert a book once, restart the app with the same cache, and assert that the new book review/session routes and `/reading-insights` page work without reconversion. Assert that `content/metadata.json`, `toc.json`, and chapter cache file sets remain unchanged by the feature. Extend the SSG run assertion to reject `/api/book-reviews`, `/api/reading-sessions`, `/api/reading-insights`, `/reading-insights`, and all five Server-only asset names.

- [ ] **Step 5: Run the full relevant test and quality gate**

Run:

```bash
python -m unittest tests.test_state tests.test_server tests.test_ssg tests.test_mode_integration tests.test_asset_publisher tests.test_generated_reader_surfaces tests.test_i18n_coverage -v
node --test tests/test_reading_sessions.js tests/test_book_reviews.js tests/test_reading_insights.js tests/test_i18n.js tests/test_reading_progress.js tests/test_book_bookshelf.js
git diff --check
```

Expected: every command exits 0; fresh Server conversion writes only `content/` EPUB-derived files, restart exposes the new UI/assets, and SSG has no Server feature artifacts.

- [ ] **Step 6: Commit localization, docs, and final regression coverage**

```bash
git add epub_browser/assets/i18n.js tests/test_i18n_coverage.py tests/test_i18n.js tests/test_ssg.py tests/test_mode_integration.py README.md docs/readme/README.zh-CN.md
git commit -m "docs: document private reading insights"
```
