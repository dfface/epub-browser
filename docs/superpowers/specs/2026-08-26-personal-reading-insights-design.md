# Personal book reviews and reading insights

## Purpose and scope

Add two private, Server-only reading features:

1. A signed-in reader can save one 1–5 star rating and an optional written
   review for each book they can access.
2. A signed-in reader can review their actual reading time in a Screen Time-like
   history: aggregate totals by day, week, and month, then the individual
   time-of-day sessions showing which book and chapter they read and for how
   long.

The first release is strictly personal. Reviews, ratings, sessions, totals, and
history are visible only to their owner. There is no community feed, aggregate
rating, administrator reporting view, moderation, export, or SSG equivalent.

This is runtime application data. It must never enter `book/<id>/content/`,
change the Server EPUB content revision, or require books to be reconverted.

## User experience

### Rating and review

The Server book-detail page shows a private “My rating and review” control. A
reader can select 1–5 stars, optionally enter a review, save, edit, or delete
the record. A review is allowed to be empty so that a reader can leave only a
rating. The library shows the owner’s star rating on its book card, but never
the review text.

### Reading insights

The Server interface exposes a private Reading insights page. Its default view
is the current week, with:

- total actual reading time for the selected range;
- the book with the greatest reading time for that range;
- a selectable daily strip/calendar; and
- a selected day’s chronological session list: start time, book title, chapter
  label, and active duration.

The range can move between day, week, and month. Date grouping and display use
the reader’s current browser IANA time zone. Stored timestamps remain UTC, so a
reader travelling between time zones sees a consistent instant rendered in the
current local time zone.

A session is an uninterrupted interval of active reading of one chapter. Moving
to another chapter closes the old session and starts a new one once the reader
is active again. Historical session rows use a snapshot of the book and chapter
labels so an EPUB update or a changed table of contents does not make old
history misleading.

## Active-reading definition

The browser counts time only while all of the following are true:

1. The document is visible.
2. Its tab/window is focused.
3. The reader has interacted within the prior 60 seconds. Qualifying interaction
   is scroll, page turn, keyboard navigation, or an explicit reader navigation
   action; mouse movement alone does not qualify.
4. A readable chapter is selected.

Visibility loss, window blur, a 60-second inactivity timeout, chapter change,
or reader teardown closes the active interval. A visibility/focus return alone
does not resume it: the next qualifying reading interaction does.

The tracker sends a heartbeat every 15 seconds while active. The server treats
the submitted active duration as a bounded increment (at most 20 seconds per
heartbeat) and records the server receipt time as the authoritative end instant.
It derives an interval start from that receipt time and bounded duration; browser
wall-clock timestamps are not accepted as authority.
On `pagehide` and visibility loss, the browser attempts a final `keepalive`
request. It buffers only a small bounded number of unsent heartbeat increments
in browser storage and retries after connectivity returns. Expired or rejected
increments are discarded rather than retried forever.

Within one browser, a per-tab coordination mechanism ensures only the focused
reading tab contributes time. Simultaneously active sessions from separate
devices are kept as distinct history rows. Range totals merge overlapping
active intervals so concurrent use cannot double-count a reader’s total time.

## Architecture and data ownership

The feature applies only when `EpubBrowserMode` is `server`. SSG templates
retain their existing local progress and annotation features, but they must
not include insight controls, analytics scripts, API routes, or translated text
that implies server data is available.

Server page templates receive only feature flags and current book identity.
They do not receive a precomputed rating, review, session history, locale
strings, permissions, or content-cache data. The authenticated browser requests
the private data from Server APIs after the regular authentication bootstrap.

The `StateStore` is the sole persistence layer. The Server route layer resolves
the public book reference to the canonical Server `book_id`, verifies the
current principal has access, then calls `StateStore`. Browser-provided book IDs,
chapter labels, timestamps, and accumulated totals are never trusted without
validation and bounds.

Book title and chapter label snapshots are allowed in SQLite because they are
historical presentation data for user-owned reading records, not EPUB content
cache schema. Current book and chapter data still comes from the existing
dynamic Server renderer.

## Persistence schema

The next SQLite schema migration adds these tables.

### `book_reviews`

| Column | Meaning |
| --- | --- |
| `user_id` | Owning user; foreign key to `users` |
| `book_id` | Canonical active Server book; foreign key to `books` |
| `rating` | Integer constrained to 1 through 5 |
| `review_text` | Trimmed optional review body, at most 10,000 Unicode characters |
| `created_at`, `updated_at` | UTC instants |

`(user_id, book_id)` is the primary key. Deleting the review removes both the
rating and review. An index by `(user_id, updated_at)` supports a future
personal-library sort without exposing data to other users.

### `reading_sessions`

| Column | Meaning |
| --- | --- |
| `id` | Opaque UUID session ID |
| `user_id`, `book_id` | Owner and canonical book |
| `chapter_index` | Generated reader chapter index |
| `book_title_snapshot`, `chapter_label_snapshot` | History display labels at recording time |
| `started_at`, `ended_at` | UTC bounds of the recorded active interval |
| `active_seconds` | Bounded integer count of actual active time |
| `client_id` | Opaque per-browser/tab identifier for idempotency and recovery |
| `last_client_sequence` | Largest accepted monotonically increasing heartbeat sequence |
| `created_at`, `updated_at` | Audit/update instants |

Each heartbeat upserts the currently open session only if its user, client,
book, and chapter context remain compatible; a changed chapter opens a new row.
The write path is idempotent: each tab uses a session-scoped, monotonically
increasing integer heartbeat sequence; the store accepts a sequence only when
it exceeds `last_client_sequence`, so retries do not add time twice.
Indexes support owner-range queries and owner-book-chapter queries:
`(user_id, started_at, id)` and `(user_id, book_id, chapter_index, started_at)`.

Sessions and reviews remain until their owner, the owning user, or the book is
deleted under the existing data-deletion rules. No periodic deletion or
cross-user aggregation occurs in v1.

## API contract

All APIs require an authenticated session, use the existing CSRF-aware request
wrapper for mutations, and return the project’s existing localized-safe API
error shape. Every route resolves and authorizes the target book before it
reads or writes any user-owned row.

| Route | Operation | Result |
| --- | --- | --- |
| `GET /api/book-reviews/{book}` | Get caller’s review | Rating/review or `null` |
| `PUT /api/book-reviews/{book}` | Upsert caller’s review | Validated saved record |
| `DELETE /api/book-reviews/{book}` | Delete caller’s review | `204` |
| `POST /api/reading-sessions/{book}/heartbeat` | Record one validated active increment | Current session summary |
| `GET /api/reading-insights` | Query caller’s range summary and sessions | Totals, daily buckets, chronological sessions |

The exact public `book` path format must follow the existing server book routes;
it is mapped server-side to canonical `book_id`. Mutation payloads are narrow:
reviews contain rating and review text; heartbeats contain client ID, client
sequence, chapter index, and bounded active increment. The server gets the book
and chapter display snapshots from the authorized rendered book; the browser
never supplies those labels. The insights query accepts exactly `period`
(`day`, `week`, or `month`), an ISO anchor date, and an IANA time zone; it never
accepts a `user_id` or arbitrary start/end timestamps.

Missing, inactive, or unauthorized books return the same non-enumerating error
semantics used by current book APIs. Invalid rating, review length, chapter,
timezone, request ID, or time increment fails validation without a partial
write. A transient network failure is non-blocking for reading; client retry
is best effort and the UI does not claim unsaved time has been recorded.

## Rendering and i18n

The rating control belongs in the shared book-detail template behind a narrow
`deployment_mode == "server"` branch. Its supporting JavaScript is published
as a hashed Server asset and loaded only in Server output.

The Reading insights page and its navigation are Server routes/pages protected
by authentication. They can reuse the project’s page chrome, asset publisher,
and i18n loader, but must not duplicate EPUB content templates. Every visible
label, validation message, empty state, range label, date/relative-time phrase,
and accessibility name is added to all supported locales and covered by the
existing i18n coverage checks.

## Migration and compatibility

Increase `DB_SCHEMA_VERSION` and add a restart-safe SQLite migration that
creates the new tables, constraints, and indexes. Existing databases retain all
current user, progress, annotation, bookshelf, and AI data untouched. New
tables begin empty, and no legacy data is inferred as reading time or ratings.

Do not change `SERVER_OUTPUT_REVISION`, `.server-content-revision`, content
cache validation, EPUB conversion output, or Server cache rebuild behavior.
Deploying the new assets and restarting the Server is sufficient for existing
converted books to show the feature.

## Security and privacy

- The database, API, and UI isolate every row by the authenticated user ID.
- Authorization is checked before loading book state and before recording a
  session; browser assertions of identity, access, duration, and title are not
  authority.
- Reading-session request rate, size, duration, and buffered retry count are
  bounded to avoid accidental runaway writes and abuse.
- Session data is personal reading history. It is excluded from administrative
  book summaries, library metadata, AI jobs, logs, exports, and SSG output.
- Existing CSRF protections and response security headers apply to all new
  mutations and pages.

## Verification

Automated coverage must include:

1. Schema creation, upgrade from the current schema, constraints, indexes, and
   preservation of pre-existing data.
2. State-store CRUD and ownership isolation for reviews and sessions.
3. Server route authentication, CSRF, visibility/grant checks, validation,
   non-enumerating denied-book behavior, and no cross-user reads or writes.
4. Session aggregation across daily/week/month time-zone boundaries, sessions
   spanning midnight, and overlap de-duplication.
5. Browser tracker transitions for activity, focus, visibility, idle timeout,
   chapter changes, retry idempotency, page teardown, and same-browser tab
   coordination.
6. Rating and insights UI rendering, accessible controls, and all-locales i18n
   coverage.
7. SSG and Server integration: SSG contains no new APIs/scripts/controls, while
   Server renders new pages against existing `content/` cache without an EPUB
   reconversion.

Before merge, run the relevant Python and JavaScript tests plus `git diff
--check`.
