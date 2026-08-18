# Server Library Progress Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show live, truthful Server-mode library reconciliation progress in the library page while keeping non-interactive CLI output quiet.

**Architecture:** A thread-safe in-memory `LibraryProgressBroker` receives committed lifecycle updates from `ServerLibraryManager` and fans full snapshots into capacity-one asyncio subscriber queues. Starlette exposes those snapshots through one read-only SSE route, while a Server-only frontend controller renders the inline panel and asks the existing library renderer to refresh metadata only after a visible catalog publication.

**Tech Stack:** Python 3.9+, dataclasses, `threading`, `asyncio`, Starlette `StreamingResponse`, browser `EventSource`, ES5-compatible JavaScript, CSS, Python `unittest`, Node `node:test`.

**Spec:** `docs/superpowers/specs/2026-08-18-server-library-progress-design.md`

## Global Constraints

- Do not add Server-mode tqdm output.
- Do not add a retry button or any progress write endpoint.
- Do not persist progress in SQLite or the cache.
- Do not change bookshelf, annotation, reading-progress, migration, database-schema, or book-identity behavior.
- Do not gate `/api/library-events`, `/api/ready`, or state-changing APIs on reconciliation phase after the base shell is available.
- Never expose absolute source, staging, cache, or database paths in SSE snapshots.
- Preserve the current commit-lock, stop, source-stat, watch-coalescing, and legacy-retirement boundaries.
- Do not add or run browser end-to-end tests; verification is limited to focused Python and Node tests.

---

## File structure

- Create `epub_browser/library_progress.py`: immutable snapshot model, public error sanitization, subscriber handoff, and broker state transitions.
- Modify `epub_browser/server_library.py`: report reconciliation lifecycle and visible-catalog publications without moving durable commit boundaries.
- Modify `epub_browser/runtime.py`: construct one shared broker, inject it into manager and app, and apply TTY-aware startup reporting.
- Modify `epub_browser/server.py`: stream broker snapshots from `/api/library-events`.
- Modify `epub_browser/assets/library.js`: make metadata replacement idempotent while preserving search, active tag, saved order, and the open bookshelf DOM.
- Create `epub_browser/assets/library-progress.js`: Server-only SSE/reducer/render controller.
- Create `epub_browser/assets/library-progress.css`: inline panel states, progress bar, responsive layout, and reduced-motion behavior.
- Modify `epub_browser/assets/i18n.js`: English and Simplified Chinese progress copy.
- Modify `epub_browser/site.py`: emit the mount and progress assets only for Server library pages and add stable metadata-count hooks.
- Modify `README.md`: document frontend progress and quiet non-TTY output.
- Create `tests/test_library_progress.py`: broker and sanitization unit coverage.
- Modify `tests/test_server_library.py`: lifecycle, catalog-revision, watch, failure, and cancellation coverage.
- Modify `tests/test_server.py`: SSE headers, initial snapshot, later delivery, and subscriber cleanup coverage.
- Modify `tests/test_runtime.py`: shared-broker wiring and TTY/non-TTY reporter behavior.
- Modify `tests/test_library_metadata.js`: incremental grid replacement and state-preservation coverage.
- Create `tests/test_library_progress.js`: reducer, dismissal, reconnect, refresh-deduplication, and mode-gating coverage.
- Modify `tests/test_site.py`: Server-only mount/assets and SSG absence coverage.

---

### Task 1: In-memory progress broker

**Files:**
- Create: `epub_browser/library_progress.py`
- Create: `tests/test_library_progress.py`

**Interfaces:**
- Produces: `ProgressFailure(filename: str, message: str)`.
- Produces: `LibraryProgressSnapshot.as_dict() -> dict` with every field from the approved schema.
- Produces: `ProgressSubscription.next() -> Awaitable[LibraryProgressSnapshot]` and `ProgressSubscription.close() -> None`.
- Produces: `LibraryProgressBroker.snapshot()`, `subscribe(loop)`, `start_generation(trigger)`, `mark_discovered(total, removed)`, `record_reused(source)`, `conversion_started()`, `record_converted(source)`, `record_failure(source, error, in_flight=False)`, `catalog_published(active_books)`, and `finish(active_books)`.

- [ ] **Step 1: Write broker tests that define the full snapshot contract**

```python
# tests/test_library_progress.py
import asyncio
import unittest
from pathlib import Path

from epub_browser.library_progress import LibraryProgressBroker


class LibraryProgressBrokerTests(unittest.IsolatedAsyncioTestCase):
    async def test_generation_counters_and_terminal_phase(self):
        broker = LibraryProgressBroker()
        broker.start_generation("startup")
        broker.mark_discovered(total=3, removed=1)
        broker.record_reused(Path("/private/library/one.epub"))
        broker.conversion_started()
        broker.record_converted(Path("/private/library/two.epub"))
        broker.record_failure(
            Path("/private/library/broken.epub"),
            "unable to parse /private/staging/package.opf",
        )
        broker.catalog_published(active_books=2)
        snapshot = broker.finish(active_books=2).as_dict()

        self.assertEqual(snapshot["generation"], 1)
        self.assertEqual(snapshot["phase"], "degraded")
        self.assertEqual(snapshot["completed"], 3)
        self.assertEqual(snapshot["converted"], 1)
        self.assertEqual(snapshot["reused"], 1)
        self.assertEqual(snapshot["failed"], 1)
        self.assertEqual(snapshot["removed"], 1)
        self.assertEqual(snapshot["in_flight"], 0)
        self.assertEqual(snapshot["catalog_revision"], 1)
        self.assertEqual(snapshot["failures"][0]["filename"], "broken.epub")
        self.assertNotIn("/private/", str(snapshot))

    async def test_new_generation_retains_catalog_revision_but_resets_batch(self):
        broker = LibraryProgressBroker()
        broker.start_generation("startup")
        broker.mark_discovered(0, 0)
        broker.catalog_published(0)
        broker.finish(0)

        snapshot = broker.start_generation("watch")

        self.assertEqual(snapshot.generation, 2)
        self.assertEqual(snapshot.catalog_revision, 1)
        self.assertEqual(snapshot.completed, 0)
        self.assertEqual(snapshot.failures, ())

    async def test_subscriber_gets_initial_and_only_latest_pending_snapshot(self):
        broker = LibraryProgressBroker()
        loop = asyncio.get_running_loop()
        subscription = broker.subscribe(loop)
        initial = await asyncio.wait_for(subscription.next(), 0.2)
        broker.start_generation("startup")
        broker.mark_discovered(4, 0)
        broker.conversion_started()
        await asyncio.sleep(0)
        latest = await asyncio.wait_for(subscription.next(), 0.2)

        self.assertEqual(initial.phase, "idle")
        self.assertEqual(latest.phase, "processing")
        self.assertEqual(latest.total, 4)
        self.assertEqual(latest.in_flight, 1)
        subscription.close()
        self.assertEqual(broker.subscriber_count, 0)
```

- [ ] **Step 2: Run the broker tests and confirm the module is missing**

Run: `python3 -m unittest tests.test_library_progress -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'epub_browser.library_progress'`.

- [ ] **Step 3: Implement immutable snapshots, sanitization, and event-loop-safe latest-only delivery**

```python
# epub_browser/library_progress.py
import asyncio
import re
import threading
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class ProgressFailure:
    filename: str
    message: str


@dataclass(frozen=True)
class LibraryProgressSnapshot:
    generation: int = 0
    revision: int = 0
    trigger: str = "startup"
    phase: str = "idle"
    total: Optional[int] = None
    completed: int = 0
    converted: int = 0
    reused: int = 0
    failed: int = 0
    removed: int = 0
    in_flight: int = 0
    active_books: int = 0
    catalog_revision: int = 0
    latest_book: Optional[str] = None
    failures: tuple[ProgressFailure, ...] = ()

    def as_dict(self) -> dict:
        return asdict(self)


def safe_progress_message(error) -> str:
    message = str(error).splitlines()[0].strip() or "Unable to process EPUB"
    message = re.sub(
        r"(?:[A-Za-z]:[\\/]|/)[^\s:'\"]+(?:[\\/][^\s:'\"]*)*",
        "source file",
        message,
    )
    return message[:240]


class ProgressSubscription:
    def __init__(self, broker, loop, initial):
        self._broker = broker
        self.loop = loop
        self.queue = asyncio.Queue(maxsize=1)
        self.closed = False
        self._offer(initial)

    def _offer(self, snapshot):
        if self.closed:
            return
        if self.queue.full():
            self.queue.get_nowait()
        self.queue.put_nowait(snapshot)

    def offer_threadsafe(self, snapshot):
        self.loop.call_soon_threadsafe(self._offer, snapshot)

    async def next(self):
        return await self.queue.get()

    def close(self):
        if not self.closed:
            self.closed = True
            self._broker.unsubscribe(self)
```

Implement `LibraryProgressBroker` with one `threading.Lock`, a subscriber set, and one `_update(**changes)` helper. `_update` must increment `revision`, copy subscribers while holding the lock, release the lock, and then call `subscription.offer_threadsafe(snapshot)`. `start_generation()` validates `trigger in {"startup", "watch"}`, retains `catalog_revision` and `active_books`, and resets all batch counters. `record_converted()` increments `converted` and `completed` and decrements `in_flight` exactly once. `record_failure(..., in_flight=True)` increments `failed` and `completed`, decrements `in_flight` exactly once, stores only `Path(source).name`, and uses `safe_progress_message`. Every transition preserves `completed == converted + reused + failed`; `finish()` sets `complete` when `failed == 0` and `degraded` otherwise.

- [ ] **Step 4: Run broker tests**

Run: `python3 -m unittest tests.test_library_progress -v`

Expected: all broker tests PASS.

- [ ] **Step 5: Commit the broker**

```bash
git add epub_browser/library_progress.py tests/test_library_progress.py
git commit -m "feat: add server library progress broker"
```

---

### Task 2: Reconciliation lifecycle and catalog publication

**Files:**
- Modify: `epub_browser/server_library.py`
- Modify: `tests/test_server_library.py`

**Interfaces:**
- Consumes: every `LibraryProgressBroker` transition from Task 1.
- Produces: `ServerLibraryManager(..., progress_broker: Optional[LibraryProgressBroker] = None)` and public `progress_broker` attribute.
- Produces: `ServerLibraryManager.reconcile(trigger: str = "startup") -> ReconcileSummary`.
- Produces: `_publish_current_state(...) -> tuple[tuple[BookRecord, ...], bool]`, where the boolean is true only when the visible metadata signature changed.

- [ ] **Step 1: Add lifecycle tests around existing fake conversions**

```python
# tests/test_server_library.py
from epub_browser.library_progress import LibraryProgressBroker

def test_reconcile_reports_incremental_progress_and_catalog_publication(self):
    broker = LibraryProgressBroker()
    manager = self.manager(
        converter_factory=self.converter_factory,
        progress_broker=broker,
        max_workers=2,
    )

    summary = manager.reconcile()
    snapshot = broker.snapshot()

    self.assertFalse(summary.cancelled)
    self.assertEqual(snapshot.phase, "complete")
    self.assertEqual(snapshot.total, 2)
    self.assertEqual(snapshot.completed, 2)
    self.assertEqual(snapshot.active_books, 2)
    self.assertGreaterEqual(snapshot.catalog_revision, 1)

def test_watch_reconcile_creates_watch_generation(self):
    broker = LibraryProgressBroker()
    manager = self.manager(progress_broker=broker)
    manager.reconcile()
    manager.reconcile(trigger="watch")

    snapshot = broker.snapshot()
    self.assertEqual(snapshot.generation, 2)
    self.assertEqual(snapshot.trigger, "watch")

def test_cancelled_reconcile_does_not_publish_terminal_success(self):
    broker = LibraryProgressBroker()
    manager = self.manager(progress_broker=broker)
    manager.request_stop()

    summary = manager.reconcile()

    self.assertTrue(summary.cancelled)
    self.assertNotIn(broker.snapshot().phase, {"complete", "degraded"})
```

Extend the existing slow-conversion and partial-failure tests to capture broker snapshots from a subscription. Assert `in_flight > 0` while conversion is blocked, the successful book advances `catalog_revision` before the other conversion finishes, and failure snapshots contain the basename but no temporary-directory prefix.

- [ ] **Step 2: Run the lifecycle tests and confirm constructor/signature failures**

Run: `python3 -m unittest tests.test_server_library -v`

Expected: FAIL because `progress_broker` and `reconcile(trigger=...)` do not exist.

- [ ] **Step 3: Inject the broker without changing commit ownership**

```python
# epub_browser/server_library.py
from .library_progress import LibraryProgressBroker

def __init__(
    self,
    server_dir,
    sources,
    state_store,
    migration_manager=None,
    reporter=None,
    converter_factory=EPUBProcessor,
    max_workers=4,
    progress_broker=None,
):
    self.progress_broker = progress_broker or LibraryProgressBroker()
    self._published_library_signature = None
```

Start the generation only after acquiring `_reconcile_lock` and repeating the stop check, immediately before discovery begins. This makes “generation started” mean a real scan rather than a reconcile waiting behind another scan. After discovery and missing-record marking, call `mark_discovered(len(discovered), removed)`. Call `record_reused(source)` only after `resolve_book` succeeds. Call `record_failure(source, error)` for stat/probe/reuse failures. In `_conversion_outcomes.worker`, call `conversion_started()` after taking a plan and before `_convert_plan(plan)`. In the outcome consumer, call `record_converted(plan.source)` after commit and public publication, or `record_failure(plan.source, error, in_flight=True)` after failure handling and publication.

Use a visible signature that includes the public fields, not timestamps:

```python
def _library_signature(self, records):
    return tuple(
        (record.book_id, record.metadata_json)
        for record in records
    )

def _publish_current_state(self, failures):
    with self._commit_lock:
        if self._stop_event.is_set():
            return self._valid_active_records(), False
        active_records = self._valid_active_records()
        signature = self._library_signature(active_records)
        visible_changed = signature != self._published_library_signature
        self._refresh_public_shell()
        self._write_catalog(active_records, failures)
        self._published_library_signature = signature
        return active_records, visible_changed
```

After every `_publish_current_state`, call `catalog_published(len(active_records))` only when `visible_changed` is true. Finish a non-cancelled generation with `finish(len(active_records))` immediately before `on_reconciled`. Do not publish `complete` or `degraded` on any `_stopped_summary` return.

In `prepare_public_shell`, compute the initial active-record signature while already holding `_commit_lock`, assign `_published_library_signature`, then call `catalog_published(len(active_records))` after releasing `_commit_lock` when that signature was new. This gives a page-open baseline without reacquiring the non-reentrant commit lock.

For direct delete watch events, acquire `_reconcile_lock` before the existing `_commit_lock` section so deletion cannot overlap a scan generation, then wrap the existing atomic delete publication in a short watch generation:

```python
self.progress_broker.start_generation("watch")
self.progress_broker.mark_discovered(total=0, removed=1)
active_records, visible_changed = self._publish_current_state(())
if visible_changed:
    self.progress_broker.catalog_published(len(active_records))
self.progress_broker.finish(len(active_records))
```

Change `_drain_queued_events()` to call `self.reconcile(trigger="watch")`. Keep `_queued_generations`, `_event_lock`, `_commit_lock`, and all stop checks in their current order.

- [ ] **Step 4: Run broker and manager tests**

Run: `python3 -m unittest tests.test_library_progress tests.test_server_library -v`

Expected: all tests PASS, including the existing shutdown and delete/commit race regressions.

- [ ] **Step 5: Commit lifecycle reporting**

```bash
git add epub_browser/server_library.py tests/test_server_library.py
git commit -m "feat: report server reconciliation progress"
```

---

### Task 3: Server-Sent Events API and runtime wiring

**Files:**
- Modify: `epub_browser/server.py`
- Modify: `epub_browser/runtime.py`
- Modify: `tests/test_server.py`
- Modify: `tests/test_runtime.py`

**Interfaces:**
- Consumes: `LibraryProgressBroker.subscribe(asyncio.get_running_loop())`.
- Produces: `create_app(..., progress_broker: Optional[LibraryProgressBroker] = None)`.
- Produces: `GET /api/library-events` with `event: progress` JSON snapshots, 15-second comment heartbeats, `Cache-Control: no-store`, and `X-Accel-Buffering: no`.

- [ ] **Step 1: Write SSE and shared-instance tests**

```python
# tests/test_server.py
from epub_browser.library_progress import LibraryProgressBroker

def test_library_events_use_sse_headers_and_initial_snapshot(self):
    broker = LibraryProgressBroker()
    broker.start_generation("startup")
    broker.mark_discovered(2, 0)
    app = create_app(self.directory.name, progress_broker=broker)

    with TestClient(app) as client:
        with client.stream("GET", "/api/library-events") as response:
            lines = response.iter_lines()
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers["cache-control"], "no-store")
            self.assertEqual(response.headers["x-accel-buffering"], "no")
            self.assertEqual(next(lines), "event: progress")
            payload = json.loads(next(lines).removeprefix("data: "))
            self.assertEqual(payload["phase"], "processing")
            self.assertEqual(payload["total"], 2)

    self.assertEqual(broker.subscriber_count, 0)
```

Add a second API test that starts a stream, calls `broker.conversion_started()` from a worker thread, and asserts the next event contains `in_flight == 1`. In `tests/test_runtime.py`, make the fake `library_factory` capture `progress_broker` and make the fake `create_app` capture the same instance; assert object identity.

Add this readiness regression in `tests/test_server.py` using a real `RuntimeStatus`: call `status.mark_available()`, then `status.mark_scanning()`, create the app with the broker, and assert `GET /api/ready` returns 200 and `PUT /api/reading-progress/book` still returns 200. This prevents progress phase from becoming an availability gate.

- [ ] **Step 2: Run the focused API/runtime tests and confirm missing arguments/route**

Run: `python3 -m unittest tests.test_server tests.test_runtime -v`

Expected: FAIL because `create_app` and `ServerLibraryManager` are not wired to one broker and `/api/library-events` returns the generic API 404.

- [ ] **Step 3: Implement the async generator and route before the generic API route**

```python
# epub_browser/server.py
import asyncio
from starlette.responses import StreamingResponse

def create_app(public_dir, state_store=None, status=None, sync_dir=None, progress_broker=None):
    async def library_events(request):
        if progress_broker is None:
            return response(error_payload("not_found", "Not found"), 404)

        async def events():
            subscription = progress_broker.subscribe(asyncio.get_running_loop())
            try:
                while True:
                    try:
                        snapshot = await asyncio.wait_for(subscription.next(), 15.0)
                    except asyncio.TimeoutError:
                        yield ": heartbeat\n\n"
                    else:
                        payload = json.dumps(snapshot.as_dict(), ensure_ascii=False, separators=(",", ":"))
                        yield "event: progress\ndata: " + payload + "\n\n"
            finally:
                subscription.close()

        return StreamingResponse(
            events(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
        )
```

Register `Route('/api/library-events', library_events)` before `Route('/api/{path:path}', annotations, ...)`. In `runtime.py`, create one `LibraryProgressBroker` before the manager, pass it as `progress_broker=progress_broker` to `library_factory`, and pass the same object to `create_app`. Update test fakes to accept and retain this keyword instead of weakening production injection.

- [ ] **Step 4: Run API, runtime, broker, and manager tests**

Run: `python3 -m unittest tests.test_library_progress tests.test_server_library tests.test_server tests.test_runtime -v`

Expected: all focused Python tests PASS; the stream test exits cleanly and leaves zero subscribers.

- [ ] **Step 5: Commit SSE delivery**

```bash
git add epub_browser/server.py epub_browser/runtime.py tests/test_server.py tests/test_runtime.py
git commit -m "feat: stream server library progress"
```

---

### Task 4: Idempotent incremental library metadata refresh

**Files:**
- Modify: `epub_browser/assets/library.js`
- Modify: `epub_browser/site.py`
- Modify: `tests/test_library_metadata.js`
- Modify: `tests/test_site.py`

**Interfaces:**
- Produces: `window.refreshLibraryMetadata() -> Promise<Array<BookMetadata>>`.
- Produces: stable DOM hooks `#libraryBookCount`, `#libraryTagCount`, and the existing `.book-grid`, `.search-box`, `.tag-cloud`.
- Preserves: current search string, active library tag, saved card/tag order, and any existing bookshelf modal DOM/open state.

- [ ] **Step 1: Extend the Node DOM harness and assert replacement rather than append**

```javascript
// tests/test_library_metadata.js
test('incremental metadata refresh replaces cards and preserves filters', async () => {
  const harness = createLibraryHarness([
    [{ hash: 'one', title: 'One', authors: [], tags: ['A'], url: '/book/one/', cover: null }],
    [
      { hash: 'one', title: 'One', authors: [], tags: ['A'], url: '/book/one/', cover: null },
      { hash: 'two', title: 'Two', authors: [], tags: ['B'], url: '/book/two/', cover: null }
    ]
  ]);
  harness.window.initScriptLibrary();
  harness.searchBox.value = 'two';

  await harness.window.refreshLibraryMetadata();

  assert.deepEqual(harness.cardIds(), ['one', 'two']);
  assert.equal(harness.searchBox.value, 'two');
  assert.equal(harness.card('one').style.display, 'none');
  assert.equal(harness.card('two').style.display, 'block');
  assert.equal(harness.bookshelfModal.classList.contains('active'), true);
});
```

Add a rejection case that starts with one rendered card, returns HTTP 500 for the refresh, and asserts the original card remains. Extend `tests/test_site.py` to assert the two count IDs exist in both modes.

- [ ] **Step 2: Run metadata/site tests and confirm the refresh function is missing**

Run: `node --test tests/test_library_metadata.js && python3 -m unittest tests.test_site -v`

Expected: the Node refresh test FAILS because `window.refreshLibraryMetadata` is undefined.

- [ ] **Step 3: Refactor library rendering around one replace operation and delegated filters**

In `library.js`, change `loadBookMetadata` to accept success and failure callbacks. Add `replaceBookCards(books)` that builds all cards with `createElement`/`textContent`, removes only `.book-card` and `.library-state` children, appends the new cards, rebuilds dynamic tag items, restores saved order, and reapplies filters. Do not replace `.book-grid`, `.controls`, `.bookshelf-modal`, or any modal children.

Use one delegated listener per control, guarded by data attributes:

```javascript
function applyLibraryFilters() {
    var searchTerm = (searchBox.value || '').toLowerCase().trim();
    var activeTag = document.querySelector('.tag-cloud-item.active');
    var tagId = activeTag ? activeTag.getAttribute('data-id') : 'All';
    document.querySelectorAll('.book-card').forEach(function(card) {
        var textMatches = cardMatchesSearch(card, searchTerm);
        var tagMatches = cardMatchesTag(card, tagId);
        card.style.display = textMatches && tagMatches ? 'block' : 'none';
    });
}

window.refreshLibraryMetadata = function() {
    return new Promise(function(resolve, reject) {
        loadBookMetadata(function(books) {
            replaceBookCards(books);
            resolve(books);
        }, reject);
    });
};
```

Update count text and `data-i18n-params` using `t('library.bookCount', {count: books.length})` and the unique tag count. Preserve the selected tag by `data-id`; if it disappeared, activate `All`. Call `restoreOrder(storageKeySortableBook, 'book-grid')` and `restoreOrder(storageKeySortableTag, 'tag-cloud')` after replacement, but do not create another Sortable instance.

In `site.py`, add `id="libraryBookCount"` and `id="libraryTagCount"` to the existing count spans. Do not add progress markup in this task.

- [ ] **Step 4: Run metadata and site tests**

Run: `node --test tests/test_library_metadata.js && python3 -m unittest tests.test_site -v`

Expected: all tests PASS, including adversarial metadata escaping and SSG rendering.

- [ ] **Step 5: Commit incremental metadata refresh**

```bash
git add epub_browser/assets/library.js epub_browser/site.py tests/test_library_metadata.js tests/test_site.py
git commit -m "feat: refresh server library metadata in place"
```

---

### Task 5: Server-only inline progress panel

**Files:**
- Create: `epub_browser/assets/library-progress.js`
- Create: `epub_browser/assets/library-progress.css`
- Create: `tests/test_library_progress.js`
- Modify: `epub_browser/assets/i18n.js`
- Modify: `epub_browser/site.py`
- Modify: `tests/test_site.py`

**Interfaces:**
- Consumes: `window.EpubBrowserMode`, `window.EpubBrowserBasePath`, `window.refreshLibraryMetadata`, browser `EventSource`, and the full snapshot schema.
- Produces: `window.EpubLibraryProgress.start()` for DOM startup.
- Exports under Node: `isNewer(previous, incoming)`, `reduce(state, snapshot)`, and `createController(options)`.

- [ ] **Step 1: Write pure reducer/controller tests with fake timers and EventSource**

```javascript
// tests/test_library_progress.js
const test = require('node:test');
const assert = require('node:assert/strict');
const Progress = require('../epub_browser/assets/library-progress.js');

function snapshot(values) {
  return Object.assign({
    generation: 1, revision: 1, trigger: 'startup', phase: 'processing',
    total: 2, completed: 0, converted: 0, reused: 0, failed: 0,
    removed: 0, in_flight: 1, active_books: 0, catalog_revision: 0,
    latest_book: null, failures: []
  }, values || {});
}

test('rejects stale snapshots and deduplicates catalog refresh', async () => {
  let refreshes = 0;
  const controller = Progress.createController({
    render() {},
    refreshMetadata() { refreshes += 1; return Promise.resolve(); },
    schedule(fn) { fn(); return 1; },
    cancelSchedule() {}
  });
  controller.accept(snapshot({ revision: 2, catalog_revision: 4 }));
  controller.accept(snapshot({ revision: 1, catalog_revision: 3 }));
  controller.accept(snapshot({ revision: 3, catalog_revision: 4 }));
  await Promise.resolve();

  assert.equal(controller.state.snapshot.revision, 3);
  assert.equal(refreshes, 1);
});

test('only an observed successful generation auto-collapses', () => {
  const scheduled = [];
  const controller = Progress.createController({
    render() {}, refreshMetadata() { return Promise.resolve(); },
    schedule(fn, delay) { scheduled.push({ fn, delay }); return scheduled.length; },
    cancelSchedule() {}
  });
  controller.accept(snapshot({ phase: 'processing' }));
  controller.accept(snapshot({ revision: 2, phase: 'complete', completed: 2, converted: 2 }));
  assert.equal(scheduled[0].delay, 3000);
  scheduled[0].fn();
  assert.equal(controller.state.hiddenGeneration, 1);
});

test('degraded dismissal survives reconnect but not the next generation', () => {
  const controller = Progress.createController({
    render() {}, refreshMetadata() { return Promise.resolve(); },
    schedule() { return 1; }, cancelSchedule() {}
  });
  controller.accept(snapshot({ phase: 'degraded', failed: 1 }));
  controller.dismiss();
  controller.disconnected();
  controller.accept(snapshot({ revision: 2, phase: 'degraded', failed: 1 }));
  assert.equal(controller.state.visible, false);
  controller.accept(snapshot({ generation: 2, revision: 1, trigger: 'watch' }));
  assert.equal(controller.state.visible, true);
});
```

Add tests for an initial `complete` snapshot staying quiet, an initial `degraded` snapshot remaining visible, reconnect retaining counters, safe failure rendering through `textContent`, and `start()` doing nothing when mode is `ssg` or the mount is absent.

- [ ] **Step 2: Run the frontend progress tests and confirm the module is missing**

Run: `node --test tests/test_library_progress.js`

Expected: FAIL because `library-progress.js` does not exist.

- [ ] **Step 3: Implement the UMD reducer, EventSource transport, and accessible renderer**

```javascript
// epub_browser/assets/library-progress.js
(function(root, factory) {
  var exported = factory();
  if (typeof module === 'object' && module.exports) module.exports = exported;
  if (root && root.document) root.EpubLibraryProgress = exported;
})(typeof window !== 'undefined' ? window : globalThis, function() {
  'use strict';

  function isNewer(previous, incoming) {
    return !previous || incoming.generation > previous.generation ||
      (incoming.generation === previous.generation && incoming.revision > previous.revision);
  }

  function eventUrl(root) {
    var base = root.EpubBrowserBasePath || '/';
    return base + 'api/library-events';
  }

  function start(root) {
    var mount = root.document.getElementById('libraryProgress');
    if (root.EpubBrowserMode !== 'server' || !mount || !root.EventSource) return null;
    var controller = createController(createDomOptions(root, mount));
    var source = new root.EventSource(eventUrl(root));
    source.addEventListener('progress', function(event) {
      controller.accept(JSON.parse(event.data));
    });
    source.onerror = function() { controller.disconnected(); };
    mount.querySelector('[data-progress-close]').addEventListener('click', function() {
      controller.dismiss();
    });
    return { controller: controller, source: source };
  }

  return { isNewer: isNewer, reduce: reduce, createController: createController, start: start };
});
```

`createController.accept` must establish the first snapshot as a baseline, ignore stale pairs, refresh metadata only on a strictly higher `catalog_revision`, remember generations observed in `discovering`/`processing`, and schedule a 3000 ms dismissal only when such a generation becomes `complete`. `degraded` must remain visible until `dismiss()`. `disconnected()` changes only connection state. DOM rendering must use `textContent`; determinate processing sets `role="progressbar"` and `aria-valuemin/max/now`, discovery removes `aria-valuenow`, routine summaries use `aria-live="polite"`, and transition into degraded applies `role="alert"` once.

- [ ] **Step 4: Add Server-only markup, styles, assets, and translations**

In `site.py`, build three strings when `deployment_mode == "server"`: a stylesheet link, a panel immediately inside `.container` before `.controls`, and a deferred script. The mount must contain stable hooks instead of dynamic HTML injection:

```html
<section id="libraryProgress" class="library-progress" hidden aria-labelledby="libraryProgressTitle">
  <div class="library-progress-heading">
    <div>
      <h2 id="libraryProgressTitle" data-progress-title></h2>
      <p data-progress-summary aria-live="polite"></p>
    </div>
    <button type="button" data-progress-close aria-label="Close" data-i18n-aria-label="library.progress.close">×</button>
  </div>
  <div class="library-progress-track" data-progress-track><span data-progress-bar></span></div>
  <p class="library-progress-latest" data-progress-latest></p>
  <details data-progress-failures hidden>
    <summary data-i18n="library.progress.failureDetails">Failure details</summary>
    <ul data-progress-failure-list></ul>
  </details>
</section>
```

Add English and `zh-CN` keys for `scanning`, `processing`, `complete`, `degraded`, `reconnecting`, `summary`, `latest`, `failureDetails`, and `close` under `library.progress.*`. Add `library-progress.css` using existing theme tokens, a full-width card, indeterminate animation, determinate width transition, green complete state, warning degraded state, `@media (max-width: 700px)`, and `@media (prefers-reduced-motion: reduce)`.

At DOMContentLoaded, call `window.EpubLibraryProgress.start(window)` after `initScriptLibrary()`. SSG HTML must contain neither the mount nor progress CSS/JS links.

- [ ] **Step 5: Run frontend, site, metadata, and i18n tests**

Run: `node --test tests/test_library_progress.js tests/test_library_metadata.js && python3 -m unittest tests.test_site tests.test_i18n_coverage -v`

Expected: all tests PASS; Node tests use fakes and do not launch a browser.

- [ ] **Step 6: Commit the progress panel**

```bash
git add epub_browser/assets/library-progress.js epub_browser/assets/library-progress.css epub_browser/assets/i18n.js epub_browser/site.py tests/test_library_progress.js tests/test_site.py
git commit -m "feat: show server scan progress in library"
```

---

### Task 6: Quiet Server startup output and documentation

**Files:**
- Modify: `epub_browser/runtime.py`
- Modify: `tests/test_runtime.py`
- Modify: `README.md`

**Interfaces:**
- Produces: one URL announcement after successful bind when stdout is a TTY.
- Produces: no URL on stdout/stderr for a normal non-TTY run.
- Produces: one bound-address notice through `Reporter.notice` when `--log` is enabled, including in non-TTY environments.
- Preserves: browser opening, bind-failure behavior, error reporting, and retained-ephemeral-directory output.

- [ ] **Step 1: Replace unconditional-output expectations with TTY/log cases**

```python
# tests/test_runtime.py
def test_non_tty_server_does_not_print_internal_url(self):
    reporter = Reporter(False)
    with mock.patch("epub_browser.runtime.sys.stdout.isatty", return_value=False):
        with contextlib.redirect_stdout(io.StringIO()) as stdout:
            self.run_with_started_server(reporter=reporter)
    self.assertEqual(stdout.getvalue(), "")

def test_tty_server_prints_bound_url_once(self):
    reporter = Reporter(False)
    with mock.patch("epub_browser.runtime.sys.stdout.isatty", return_value=True):
        with contextlib.redirect_stdout(io.StringIO()) as stdout:
            self.run_with_started_server(reporter=reporter)
    self.assertEqual(
        stdout.getvalue(),
        "Server available at: http://127.0.0.1:8000/\n",
    )

def test_log_mode_reports_bound_url_to_stderr_in_non_tty(self):
    reporter = Reporter(True)
    with mock.patch("epub_browser.runtime.sys.stdout.isatty", return_value=False):
        with contextlib.redirect_stderr(io.StringIO()) as stderr:
            self.run_with_started_server(reporter=reporter)
    self.assertIn("Server available at: http://127.0.0.1:8000/", stderr.getvalue())
```

Retain the existing bind-failure assertion that neither reports availability nor opens a browser.

- [ ] **Step 2: Run runtime tests and confirm non-TTY currently prints**

Run: `python3 -m unittest tests.test_runtime -v`

Expected: the non-TTY test FAILS with the current unconditional `Reporter.result` call.

- [ ] **Step 3: Gate only the successful-bind announcement**

```python
# epub_browser/runtime.py
import sys

def report_availability():
    with availability_lock:
        if availability_reported.is_set():
            return
        message = f"Server available at: {local_url}"
        if config.log:
            active_reporter.notice(message)
        elif sys.stdout.isatty():
            active_reporter.result(message)
        if not config.no_browser:
            try:
                browser_opener(local_url)
            except Exception as error:
                active_reporter.detail(f"Unable to open browser: {error}")
        availability_reported.set()
```

Do not change `Reporter.error`, SSG tqdm, Uvicorn log-level selection, or retained-directory output.

- [ ] **Step 4: Document the observable behavior**

Update the Server section of `README.md` with these exact points:

```markdown
- Initial and watch scans appear in the Server library page; Server mode does not use terminal tqdm.
- Interactive terminals print the bound URL once. Docker/systemd runs stay quiet unless `--log` is enabled.
- A successful scan summary closes automatically; failures remain visible until dismissed. Fixing or replacing the EPUB lets `--watch` start the next scan—there is no manual retry endpoint.
```

- [ ] **Step 5: Run all focused non-E2E verification**

Run: `python3 -m unittest discover -s tests -p 'test_*.py'`

Expected: all Python tests PASS.

Run: `node --test tests/*.js`

Expected: all Node unit tests PASS.

Run: `git diff --check`

Expected: no whitespace errors.

- [ ] **Step 6: Commit output behavior and docs**

```bash
git add epub_browser/runtime.py tests/test_runtime.py README.md
git commit -m "fix: keep non-interactive server output quiet"
```

---

## Completion criteria

- Server library pages show initial and watch progress without terminal tqdm.
- Successful books appear as their catalog publications complete.
- A fully successful observed generation collapses after three seconds; a degraded generation waits for manual dismissal.
- No retry endpoint or button exists.
- The SSE stream cannot block reconciliation and cleans up disconnected subscribers.
- `/api/ready` and write APIs remain available while scanning after base-shell readiness.
- Non-TTY Server runs are silent unless `--log` is enabled; failures remain visible.
- SSG output, bookshelf behavior, book IDs, database schema, migration, and shutdown behavior remain unchanged.
- Python and Node unit/API tests pass; no browser E2E suite is added or run.
