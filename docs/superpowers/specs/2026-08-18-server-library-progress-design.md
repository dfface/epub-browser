# Server Library Progress Design

**Date:** 2026-08-18
**Status:** Ready for review

## Summary

Server mode will expose library discovery and reconciliation progress in the library web interface instead of rendering a terminal tqdm display. The HTTP shell remains available while the initial scan runs, successful books continue to appear incrementally, and the library page receives live progress through a read-only Server-Sent Events stream.

The progress UI is an inline panel between the library heading and the book grid. It covers both the initial scan and later `--watch` batches. A fully successful batch shows a short success summary and collapses automatically. A batch with any failure remains visible until the user closes it. There is no manual retry API; changing or replacing the EPUB lets the existing watcher start a new reconciliation batch.

## Goals

- Show truthful initial-scan and watch progress in the Server library page.
- Keep the HTTP shell and state-changing APIs available while scanning.
- Publish successful books into the visible library as soon as each commit completes.
- Deliver progress without polling and without allowing slow clients to block conversion.
- Keep Server CLI and container output quiet in non-interactive environments.
- Preserve the existing database, cache, migration, readiness, and shutdown boundaries.

## Non-goals

- Server-mode tqdm output.
- Progress UI in SSG output, book pages, or chapter pages.
- A manual retry button or progress-related write API.
- Persisting progress snapshots to SQLite or the cache.
- Full browser end-to-end tests.
- Changing bookshelf, annotation, reading-progress, or book-identity behavior.

## User experience

### Placement

The panel appears on the Server library page between the library heading and the book grid. It does not appear on reading surfaces and does not float above existing controls.

The same component represents initial startup and watch-triggered batches:

- `discovering`: indeterminate progress and “Scanning library”.
- `processing`: determinate progress, counts, in-flight work, and the most recently completed filename.
- `complete`: green success summary for three seconds, then collapse.
- `degraded`: persistent failure summary with expandable safe details and a close button.
- `disconnected`: retain the last snapshot and show that the browser is reconnecting.

Closing a degraded panel hides only its current generation in the current page lifetime. A later generation opens the panel again. Reloading the page may show the current degraded state again, which favors visibility over durable dismissal state.

### Success and failure

When every discovered book is processed successfully, the panel shows the final total and zero failures for three seconds before collapsing.

When one or more books fail:

- successful books remain published and visible;
- the panel stays open until manually closed;
- failure details contain only the source filename and a safe error message;
- no host absolute path is sent to the browser;
- there is no retry action;
- a subsequent file change or Server restart performs the next normal reconciliation.

### Accessibility and responsive behavior

- Determinate progress uses `role="progressbar"` with `aria-valuemin`, `aria-valuemax`, and `aria-valuenow`.
- Routine state changes use a restrained `aria-live="polite"` summary rather than announcing every counter update.
- A terminal degraded state uses `role="alert"` once.
- Failure details are keyboard operable and collapsible.
- The panel is full-width on narrow screens and never overlaps the existing bottom reading controls.

## CLI output behavior

Server progress belongs to the web interface, not tqdm.

- In an interactive TTY, Server prints the available URL once after Uvicorn has successfully bound.
- In a non-TTY environment such as Docker or systemd, a normal run does not print the internal `127.0.0.1:<container-port>` URL.
- `--log` enables operational startup, bound-address, scan, and watch details through the existing progress-safe Reporter path, including in a non-TTY environment.
- Errors remain visible regardless of `--log` or TTY state.
- SSG keeps its existing terminal tqdm behavior.

## Architecture

### Components

`ServerLibraryManager` remains responsible for source discovery, cache reuse, conversion, durable activation, and incremental public-shell publication. It reports lifecycle changes only after the corresponding state transition or commit is real.

A new `LibraryProgressBroker` owns the in-memory progress snapshot and subscriptions. It provides:

- atomic snapshot updates under a thread lock;
- monotonically increasing generations and revisions;
- full-snapshot publication;
- registration and cleanup of SSE subscribers, with event-loop-safe handoff from reconciliation worker threads;
- latest-only delivery so slow subscribers cannot build an unbounded queue.

The Server API adds one read-only endpoint:

```text
GET /api/library-events
```

The library frontend adds a focused progress controller, published with the normal immutable assets. It owns EventSource connection state, stale-event rejection, panel transitions, dismissal, and metadata refresh requests. Rendering remains separate from transport and state reduction so those behaviors can be tested independently.

### Data flow

```text
ServerLibraryManager
  -> LibraryProgressBroker full snapshot
  -> GET /api/library-events (SSE)
  -> library progress controller
  -> inline progress panel

Successful per-book commit
  -> public book + metadata/catalog publication
  -> catalog_revision advances in progress snapshot
  -> browser refetches book-metadata.json
  -> existing library renderer reapplies search, tag, sort, and shelf state
```

Progress events never carry book metadata. `book-metadata.json` remains the only browser-facing source of library book records.

## Progress snapshot

Every SSE progress event contains a complete snapshot:

```json
{
  "generation": 7,
  "revision": 23,
  "trigger": "startup",
  "phase": "processing",
  "total": 32,
  "completed": 18,
  "converted": 9,
  "reused": 8,
  "failed": 1,
  "removed": 2,
  "in_flight": 4,
  "active_books": 29,
  "catalog_revision": 12,
  "latest_book": "example.epub",
  "failures": [
    {
      "filename": "broken.epub",
      "message": "Unable to parse EPUB package"
    }
  ]
}
```

### Field rules

- `generation` increments once for each reconciliation that actually starts.
- `revision` increments for every snapshot change within a generation.
- `trigger` is `startup` or `watch`.
- `phase` is `idle`, `discovering`, `processing`, `complete`, or `degraded`.
- `total` is `null` during discovery and becomes the discovered EPUB count afterward.
- `completed = converted + reused + failed`.
- `removed` is separate from `total` and `completed`.
- `in_flight` reflects conversion tasks currently executing; the UI does not claim that one book is the sole current task.
- `latest_book` is the basename of the most recently completed source, never a full path.
- `active_books` is the currently valid published-book count.
- `catalog_revision` starts at zero and advances only after a public catalog/metadata publication that can change the visible grid completes. This includes published additions, reactivated/reused books, and removals.
- `failures` contains filename and safe message pairs for the current generation.

The frontend compares `(generation, revision)` lexicographically and ignores older snapshots.

## Reconciliation lifecycle

1. `reconcile()` starts a new generation and publishes `discovering` before source traversal.
2. Interrupted discovery marks the generation cancelled internally and does not publish a false completed state.
3. Completed discovery publishes `processing` with a known total and removal count.
4. Each cache reuse increments `reused` and `completed` after its database state is resolved. If reuse changes the visible catalog, `catalog_revision` advances only after that public publication finishes.
5. Each conversion increments `in_flight` when execution starts.
6. A successful conversion decrements `in_flight`, increments `converted` and `completed`, and advances `catalog_revision` only after the existing commit and public publication finish.
7. A failed conversion decrements `in_flight`, increments `failed` and `completed`, and appends a sanitized failure.
8. A generation with zero failures publishes `complete`; otherwise it publishes `degraded`.
9. Watch events continue using the existing coalescing and serialized reconciliation flow. A later actual reconciliation receives a new generation.

No progress publication may weaken the existing `_commit_lock`, stop checks, migration retirement rules, or source-stat validation. Progress updates are observers of committed lifecycle changes, not part of the database transaction.

## SSE delivery

`GET /api/library-events` is available only in Server mode as soon as the base HTTP shell is serviceable; an active scan does not gate the endpoint. A connection immediately receives the current full snapshot, then receives subsequent full snapshots as `event: progress` messages.

Each subscriber has an `asyncio.Queue` with capacity one owned by the Server event loop. Broker publications from reconciliation threads enter that loop through `loop.call_soon_threadsafe`; the event-loop callback replaces an older queued snapshot with the latest one when necessary. The scanner never waits for an SSE client and no asyncio queue is mutated directly from a worker thread.

The endpoint:

- sends a comment heartbeat every 15 seconds while idle;
- uses `Cache-Control: no-store`;
- uses `X-Accel-Buffering: no`;
- cleans up the subscriber when the request disconnects;
- does not replay an event history because the initial full snapshot is authoritative.

The EventSource client automatically reconnects. While disconnected during an active generation, the panel retains its last counters and changes its connection label without resetting progress. Reconnecting to a generation that the user already dismissed does not reopen it; a later generation does.

The initial snapshot establishes the page baseline. A page opened after a successful generation is already complete does not flash the three-second success panel. A page that observed that generation while it was active does show the success summary. A degraded initial snapshot remains visible because it requires attention.

## Incremental library refresh

The frontend refetches `book-metadata.json` only when `catalog_revision` increases. Multiple progress snapshots with the same catalog revision do not trigger duplicate metadata requests.

The existing library renderer must preserve the user’s current query, active tag, sort order, and bookshelf view when applying new metadata. A failed metadata refresh leaves the current grid intact and may retry on the next higher catalog revision or page reload.

## Error and privacy handling

- Absolute source paths remain in Server logs only when `--log` is enabled; they are never included in the SSE payload.
- Failure messages use the same sanitized public-error boundary as health and API responses and must not embed staging, cache, database, or source-root paths.
- A progress subscriber failure cannot change Server health, stop scanning, or mark a book failed.
- An SSE disconnect is a browser connectivity state, not a Server degraded state.
- If the Server stops, the existing shutdown sequence wins; no terminal progress event is required after stop is requested.

## Compatibility

- SSG output and behavior are unchanged.
- Legacy v1 CLI mappings remain unchanged.
- Existing `/api/health` and `/api/ready` contracts remain stable.
- Bookshelf, annotations, reading progress, migration, book IDs, and database schema are unchanged.
- The new frontend controller must no-op unless `window.EpubBrowserMode === "server"` and the library progress mount exists.

## Focused verification

No browser end-to-end suite is required for this feature.

### Progress broker tests

- generation and revision monotonicity;
- immediate snapshot for a late subscriber;
- latest-only delivery under backpressure;
- unknown total during discovery;
- filename and error sanitization.

### Server library lifecycle tests

- correct reuse, conversion, failure, removal, and in-flight counters;
- catalog revision only after successful publication;
- per-book progress while other conversions continue;
- a new watch reconciliation creates a new generation;
- cancellation and stop do not publish misleading terminal events;
- partial failure preserves successful incremental publication.

### SSE API tests

- initial snapshot and later progress delivery;
- no-store and no-buffer response headers;
- subscriber cleanup on disconnect;
- one slow subscriber cannot block another or the scanner.

### Frontend unit tests

- stale snapshot rejection;
- three-second successful collapse;
- persistent degraded state and manual dismissal;
- dismissal limited to one generation;
- reconnection display without counter reset;
- catalog revision metadata refresh deduplication;
- preservation of active library filters and sort;
- no EventSource in SSG mode.

### Reporter/runtime tests

- interactive TTY prints the successfully bound URL once;
- non-TTY normal Server output is empty;
- `--log` operational output remains available;
- errors remain visible.
