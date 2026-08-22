# Server schema v11 and administration operations design

Date: 2026-08-23

Status: approved for implementation planning

Scope: Server mode only

## Purpose

EPUB Browser's Server database has grown from annotations and bookshelf sync
into a 20-table application database that also owns accounts, sessions, book
authorization, AI configuration, durable AI queues, cached AI results, and
private conversations. The schema still contains compatibility columns and
indexes from earlier releases, while several newer queue and history queries
do not have indexes matching their filters and ordering.

The administration panel has a related scaling problem. It cannot inspect AI
reading jobs, and book management loads every active book with all editable
controls at once. The latter performs multiple store calls per book and builds
permission, tag, and AI settings controls for the whole library even when an
administrator edits only one book.

This design introduces a compatible database schema v11 and two focused
administration surfaces:

- a paginated AI reading job table with privacy-safe operational metadata and
  audited manual retry;
- a searchable, filterable, paginated book table backed by a lightweight
  summary index and lazy per-book editing.

Existing reader APIs, authorization semantics, external `book_hash` field
names, bookshelf conflict behavior, and EPUB-derived Server content remain
unchanged.

## Decisions

| Area | Decision |
| --- | --- |
| Compatibility | Preserve existing API and user-visible data semantics. Add new administrator routes without removing the old granular routes. |
| Database version | Increment `DB_SCHEMA_VERSION` from 10 to 11 and migrate inside one `BEGIN IMMEDIATE` transaction after a verified backup. |
| SQLite runtime | Use WAL for persistent local databases, `synchronous=NORMAL`, a 5-second busy timeout, foreign keys on every connection, and `PRAGMA optimize` after schema work. |
| AI job scope | Administrators manage shared AI reading generation jobs only. Private follow-up questions and book-chat contents are not exposed. |
| Manual retry | Create a new linked job using the original safe request and current book/model/template state. Never rewrite the failed row back to `queued`. |
| Job pagination | Server-side status filtering and pagination, default 20 rows and maximum 100 rows per page. |
| Book pagination | Load a lightweight active-book index once, apply title/author/tag/pinyin search and filters in the browser, and render 20 rows per page. Load editable details only for the expanded book. |
| Book updates | Add one atomic settings operation for visibility, grants, server tags, and AI profile. Preserve existing individual endpoints. |
| UI implementation | Reuse the existing administration modal, CSS variables, controls, and English/Simplified Chinese i18n system. Do not add a UI framework. |
| Server content cache | Do not change `.server-content-revision`; SQLite application state is outside the EPUB-derived content schema. |

## Goals

- Make queue claiming, annotation history, session history, AI result history,
  and administrator job pagination use query-aligned indexes.
- Enforce single-flight AI generation in SQLite instead of relying only on an
  application transaction convention.
- Remove obsolete ownership columns and indexes without losing legacy data.
- Add missing relational integrity where the relationship is stable and
  unambiguous.
- Improve concurrent read/write behavior for the ASGI server and background AI
  worker.
- Give administrators enough AI job information to diagnose failures and retry
  safe jobs without exposing source text, prompts, provider responses, or
  private conversations.
- Make book administration responsive for libraries with many books, users,
  tags, and AI results.

## Non-goals

- Do not rename the public `book_hash` fields to `book_id` in this release.
- Do not normalize the versioned bookshelf JSON document. It is intentionally
  an atomic ordered document with optimistic conflict semantics.
- Do not merge the three durable AI queues into one generic queue.
- Do not expose or administer the text of AI reading follow-ups or book chat.
- Do not add cancellation, automatic scheduled retry, bulk retry, job deletion,
  or provider log storage.
- Do not depend on SQLite JSON1 or FTS extensions; Python 3.9 installations may
  be linked to different SQLite builds.
- Do not change SSG output or add a Server API dependency to SSG pages.

## Current findings

The current database contains 20 application tables. Review against the actual
queries found these concrete issues:

- the three queued-work claims scan their full job tables and build temporary
  order-by trees;
- annotation, active-session, follow-up-history, and chapter/language AI result
  queries use temporary sorting despite having adjacent indexes;
- `idx_bookshelves_user_id`, `idx_reading_progress_user_id`, and the current
  annotation user index are duplicated by primary-key prefixes or by their
  replacements;
- `ai_reading_jobs.result_id`, `ai_book_chat_turns.book_id`, and
  `ai_book_chat_summaries.book_id` lack foreign keys;
- annotations, bookshelves, and reading progress still retain legacy
  `username` columns whose current writes always store an empty string;
- session epoch values are stored as `TEXT`, forcing `CAST(expires_at AS REAL)`
  and allowing lexical rather than numeric timestamp ordering;
- every SQLite connection enables foreign keys but has no explicit busy
  timeout or journal/concurrency policy;
- the administrator book endpoint performs per-book lookups for grants,
  profiles, and tags, and the browser renders every book's full editor.

## SQLite connection and backup policy

### Per-connection settings

`StateStore._connect()` keeps `PRAGMA foreign_keys=ON` and additionally applies:

- `PRAGMA busy_timeout=5000` so short contention between HTTP requests and the
  AI worker waits instead of immediately raising `database is locked`;
- `PRAGMA synchronous=NORMAL` for WAL connections;
- the existing row factory and normal transaction behavior.

Journal mode is initialized once for a persistent database before normal
request traffic, not renegotiated by every connection. The initializer requests
`PRAGMA journal_mode=WAL`, records the returned mode, and continues with SQLite's
returned fallback mode when WAL is unavailable. WAL is intended for a local
filesystem. Deployment documentation will state that a shared network
filesystem is not a supported database location for concurrent Server use.

`PRAGMA optimize` runs after a successful schema initialization/migration so
SQLite can refresh planner metadata without placing it on every request path.

### WAL-safe backups

The current verified backup copies only the main database file. Once WAL is
enabled, a valid committed state may also exist in `-wal`; a raw file copy can
therefore produce an incomplete backup after an unclean stop.

All database backups and legacy-database snapshots will use SQLite's backup API
into a temporary destination database. The backup operation reads a consistent
snapshot including committed WAL pages. The destination is closed, integrity
checked, digest verified where applicable, and atomically renamed into
`data/backups/`. A failure leaves the authoritative source and schema version
unchanged.

The Server process lock still prevents two EPUB Browser instances from
migrating the same database. SQLite locking remains the authority within the
process and for diagnostic tools that may open the file concurrently.

## Schema v11

### Legacy ownership cleanup

Schema v1/v2 ownership migration continues to run before cleanup. Once all
legacy rows have stable `user_id` ownership, v11 rebuilds these tables without
the obsolete `username` column:

- `annotations`;
- `bookshelves`;
- `reading_progress`.

The rebuild copies every current field and preserves primary keys, timestamps,
colors, selector metadata, bookshelf versions/documents, and progress values.
Annotations and reading progress deliberately do not gain a foreign key from
the externally named `book_hash` column to `books`: older synchronized data may
outlive an active library registration, and retaining that data is existing
behavior.

The bookshelf remains one row per user containing `version`, `data`, and
`updated_at`. Its ordered document and compare-and-swap version are not split
into relational shelf-item rows.

### Sessions

The `sessions` table is rebuilt with `REAL` affinity for `expires_at`,
`last_used_at`, `revoked_at`, and `created_at`. Existing numeric strings are
converted with `CAST(... AS REAL)`. Store methods bind numeric values instead
of stringifying them; API serialization continues returning the same UTC ISO
timestamps.

The existing token digest uniqueness and `users(id) ON DELETE CASCADE` foreign
key remain unchanged.

### AI reading jobs

`ai_reading_jobs` keeps the complete safe replay request in `request_json` but
never stores EPUB text, prompts, provider responses, or secrets. V11 adds:

- `attempt_number INTEGER NOT NULL DEFAULT 1 CHECK(attempt_number >= 1)`;
- `retried_from_job_id TEXT REFERENCES ai_reading_jobs(id) ON DELETE SET NULL`;
- `retry_root_job_id TEXT REFERENCES ai_reading_jobs(id) ON DELETE SET NULL`;
- `retried_by_user_id TEXT REFERENCES users(id) ON DELETE SET NULL`;
- `result_id TEXT REFERENCES ai_reading_results(id) ON DELETE SET NULL`;
- `CHECK(progress_current >= 0 AND progress_total >= 1 AND progress_current <= progress_total)`;
- a consistency check preventing a row from holding both `result_id` and
  `error_code`, and requiring failed rows to have an error code.

Completed jobs may have a null `result_id` after an administrator clears the
referenced cached result, so the schema does not incorrectly require every
historical completed row to retain a result forever.

Manual retries preserve the original `owner_user_id`. `retried_by_user_id`
records the administrator who requested the new attempt. The original row
remains terminal and unchanged. A first retry stores the source job ID as
`retry_root_job_id`; later retries carry that root forward. The next attempt
number is selected as the maximum existing attempt in that root lineage plus
one inside the same immediate transaction.

### Additional foreign keys

The following missing relationships become explicit:

- `ai_book_chat_turns.book_id -> books(book_id) ON DELETE CASCADE`;
- `ai_book_chat_summaries.book_id -> books(book_id) ON DELETE CASCADE`;
- `ai_reading_jobs.result_id -> ai_reading_results(id) ON DELETE SET NULL`.

Books are normally retained and marked inactive rather than physically
deleted. Before the rebuilt tables replace their originals, migration checks
all referenced IDs. Unexpected orphan rows abort and roll back migration with a
clear startup error; they are never silently deleted. The verified backup is
retained for diagnosis.

One legacy case is expected rather than corrupt: before v11, clearing cached AI
results could leave a completed job's unconstrained `result_id` pointing at a
deleted result. Migration converts only those proven-missing result pointers to
null before adding the foreign key, preserving the completed job history. It
does not delete the job or invent a replacement result. Orphaned book/user/chat
relationships and duplicate active cache keys remain migration errors because
there is no equally unambiguous repair.

### Index changes

The final index set follows real filters and stable orderings:

| Query family | Index |
| --- | --- |
| Active books | `books(active, book_id)` replacing the single-column active index |
| Annotations by user | `annotations(user_id, created_at DESC, id)` |
| Annotations by book | `annotations(user_id, book_hash, created_at DESC, id)` |
| Annotations by chapter | `annotations(user_id, book_hash, chapter_index, created_at DESC, id)` |
| Session history | `sessions(user_id, created_at DESC, session_id)` |
| Default admin job page | `ai_reading_jobs(created_at DESC, id DESC)` |
| Status-filtered admin job page | `ai_reading_jobs(status, created_at DESC, id DESC)` |
| Reading queue | partial `ai_reading_jobs(created_at, id) WHERE status='queued' AND request_json IS NOT NULL` |
| Reading single-flight | unique partial `ai_reading_jobs(cache_key) WHERE status IN ('queued','running')` |
| Job result cleanup | partial `ai_reading_jobs(result_id) WHERE result_id IS NOT NULL` |
| Job retry lineage | `ai_reading_jobs(retry_root_job_id, attempt_number)` |
| Follow-up queue | partial `ai_reading_followups(created_at, id) WHERE status='queued'` |
| Follow-up history | `ai_reading_followups(result_id, owner_user_id, created_at)` with the implicit rowid suffix |
| Book-chat queue | partial `ai_book_chat_turns(created_at) WHERE status='queued'`; SQLite's implicit rowid suffix preserves insertion order ties |
| Book-chat history | `ai_book_chat_turns(owner_user_id, book_id, created_at, id)` |
| Book-chat result cleanup | partial `ai_book_chat_turns(result_id) WHERE result_id IS NOT NULL` |
| AI results by book | `ai_reading_results(book_id, created_at DESC, id DESC)` |
| AI results by chapter/language | `ai_reading_results(book_id, chapter_index, language, created_at DESC, id DESC)` |
| Current-result cleanup | `ai_reading_current_results(result_id)` |
| Tag deletion | `book_ai_tags(tag_id)` |

Reading and follow-up queue claims retain their existing `(created_at, id)`
ordering. Follow-up reader history and the book-chat queue retain
`(created_at, rowid)` because `CURRENT_TIMESTAMP` is only second-granular and
rowid represents the real send order for records inserted in the same second.
SQLite rowid-table secondary indexes carry rowid as their implicit final key,
so those indexes can satisfy the ordering without changing conversation
semantics. Book-chat reader history already uses `(created_at, id)` and keeps
that contract.

SQLite does not automatically index foreign-key child columns. The result and
tag indexes above specifically cover existing destructive paths: clearing AI
results must not scan jobs, current pointers, follow-ups, or book-chat turns,
and deleting a server tag must not scan all book-tag assignments. Foreign keys
whose parents have no hard-delete operation do not receive write-amplifying
indexes solely for a hypothetical deletion path.

V11 drops superseded indexes, including the redundant bookshelf and progress
user indexes and old annotation/job indexes. Primary-key and unique indexes
remain SQLite-managed. `book_access(user_id)` remains because member-oriented
visibility queries cannot use the `(book_id, user_id)` primary key in reverse.

## Migration sequence and failure handling

For an authoritative database below schema v11, `MigrationManager` performs:

1. open and integrity-check the source, including any WAL state;
2. create and verify a consistent SQLite backup;
3. open the authoritative database and begin `BEGIN IMMEDIATE`;
4. create the latest compatible base schema;
5. complete historical ownership/primary-key migrations in their existing
   version order;
6. validate source rows needed by rebuilt tables, including numeric session
   timestamps, new foreign-key targets, and unique active cache keys; normalize
   only the documented legacy missing-result pointers to null;
7. rebuild selected tables under unique temporary names, copy rows, compare
   source/destination row counts, replace originals, and create final indexes;
8. run `PRAGMA foreign_key_check`, set `PRAGMA user_version=11`, and commit;
9. request WAL mode and run `PRAGMA optimize` outside the migration transaction;
10. reopen and integrity-check the migrated database.

Any validation, copy, constraint, row-count, or foreign-key failure rolls the
transaction back. Temporary migration tables are not accepted on the next
startup. A fresh database creates the v11 shapes directly and does not perform
unnecessary table rebuilds. A database with a schema version newer than 11
continues to fail closed.

## Administrator AI job management

### API

`GET /api/admin/ai/jobs` accepts:

- `page`, a positive integer, default `1`;
- `page_size`, one of a bounded positive range, default `20`, maximum `100`;
- optional `status` in `queued`, `running`, `complete`, `failed`, or
  `interrupted`.

The response contains `jobs` plus `pagination` (`page`, `page_size`, `total`,
`total_pages`). Each row may include only:

- job ID and attempt/retry linkage;
- safe owner username/ID;
- book ID and display title;
- scope, mode, language, chapter index, and reading boundary parsed server-side
  from the small replay document;
- profile/template identifiers;
- status, safe error code, progress, result ID, and timestamps;
- whether the row is currently retryable.

It never returns `request_json`, EPUB text, prompts, provider base URL/key,
provider response bodies, exception messages, filesystem paths, follow-up
questions, or book-chat messages.

`POST /api/admin/ai/jobs/{job_id}/retry` requires administrator authentication
and the existing CSRF protection. Only `failed` and `interrupted` reading jobs
with a valid replay request are eligible.

### Retry flow

The retry handler delegates to `AIReadingService`; it does not mutate queue
rows directly:

1. load and validate the terminal source job;
2. resolve its original owner and re-check that the account is enabled, AI
   authorized, and allowed to read the active book;
3. reconstruct `ReadingRequest` from the private replay document;
4. extract the current allowed material and choose the current profile,
   template, model configuration revision, and model context window;
5. recompute the cache key and progress total;
6. inside an immediate transaction, reject/join an existing active job for the
   same cache key or create a new job with `attempt_number + 1`,
   `retried_from_job_id`, `retry_root_job_id`, and `retried_by_user_id`;
7. if a current cached result already satisfies the recomputed key, complete
   the new linked job without a provider call; otherwise wake the durable
   worker and return the queued job.

The retry continues to execute as the original owner. It does not bypass book
authorization, AI authorization, or provider-call quota accounting. A changed
template, model configuration, book version, or reading boundary therefore
produces the correct new cache identity instead of replaying an obsolete cache
key.

Simultaneous clicks are safe: the partial unique cache index is authoritative,
and the losing request returns the already-active job rather than creating a
second provider call. Stable error codes distinguish missing, non-retryable,
unauthorized, stale/unavailable source, active-conflict, and globally disabled
AI cases.

### Job table UI

The AI section gains a semantic table with:

- status filter, refresh control, page-size control, numbered pagination, and
  previous/next actions;
- status, short job ID/attempt, book, requester, scope/chapter, progress,
  sanitized error, created/updated time, and action columns;
- a retry button only for eligible failed/interrupted jobs;
- an empty state, loading state, localized errors, and an `aria-live` update
  after retry.

The table polls at a low frequency only while the administration panel is open
and the document is visible. Polling stops when the panel closes or the page is
hidden. A retry refreshes the current page and preserves filters; pagination is
clamped if the last row on a page disappears from the selected status.

On narrow screens the table remains semantically a table inside a horizontal
overflow container. Controls have visible labels, keyboard focus, and adequate
touch targets. All copy and status/error labels exist in both supported
locales.

## Optimized book management

### Problems addressed

The current `/api/admin/books` response builds full editable data for every
active book. For each book it independently loads grants, AI profile, server
tags, and effective tags. The browser then creates all member checkboxes, tag
checkboxes, selects, and buttons for every book and calls `loadAdminData()`
after most changes, re-fetching unrelated users, settings, identities, and
tags.

### Lightweight index

A new `GET /api/admin/books/index` route returns a privacy-safe lightweight
summary for every active book:

- ID, title, authors, EPUB tags, visibility, and updated time;
- grant count;
- AI profile and assigned server-tag IDs/names;
- AI result count.

The store fetches active books once and performs batched/grouped queries for
grants, profiles, tag assignments, and result counts. It does not call a store
method per book and does not require SQLite JSON1; metadata JSON is parsed in
Python with the same safe title/author fallbacks used elsewhere.

This compact index is intentionally client-searchable so the existing bundled
`pinyin-pro` library can match Chinese titles and authors without adding a
Python pinyin dependency or storing derived romanization in SQLite.

### Table, search, and pagination

Book management becomes a semantic table with 20 rows per page. The toolbar
supports:

- title, author, EPUB tag, and server-tag search;
- full Chinese text and tone-free pinyin matching through the existing
  `pinyin-pro` asset;
- visibility filtering (`all`, `authenticated`, `restricted`);
- server-tag filtering;
- page-size, numbered page, previous/next, and manual refresh controls.

Matching, stable locale-aware title sorting, and pagination run over the
lightweight index. Only rows for the current page are rendered. A row shows
book/author, visibility, grant count, AI profile, tags, AI result count, update
time, and a Manage action.

### Lazy editor and atomic save

`GET /api/admin/books/{book_id}` is added to the existing book route and returns
the full editable detail for one active book. Clicking Manage expands one
full-width detail row beneath the selected book and closes any other expanded
editor. The editor is fetched only when opened and groups controls into:

- visibility and member access;
- server tags;
- AI reading profile;
- scoped AI result clearing.

`PUT /api/admin/books/{book_id}/settings` accepts one complete settings object:

    {
      "visibility": "restricted",
      "user_ids": ["..."],
      "tag_ids": ["..."],
      "profile": "technical"
    }

The state store validates the book, all users, all tags, the visibility value,
and profile before changing anything. It then applies visibility, replaces
grants, replaces tag assignments, and updates the profile in one immediate
transaction. Any validation or database failure rolls back the entire update.
The response returns refreshed detail and summary data so the browser patches
only the current row and does not reload the rest of the administration panel.

Existing visibility, grant, and `/ai` endpoints remain available and retain
their behavior for compatibility. Shared internal transaction helpers prevent
the new atomic operation from nesting separate connections.

Clearing AI results remains a separate destructive operation. The UI names the
book in a confirmation step, disables the action while pending, reports the
deleted count, and refreshes only that book's result count.

The editor and table use existing account-panel CSS variables and controls. On
mobile, the table has controlled horizontal overflow and the expanded editor
becomes a single-column layout. It does not open a modal inside the existing
administration modal.

## Authorization, privacy, and mode boundaries

All new routes call `require_admin` before reading book/job state. State-changing
operations remain protected by the existing same-origin/CSRF middleware. The
server derives retry ownership, book access, and editable entities from
database records rather than trusting display values sent by the browser.

The AI job API reveals only operational metadata needed by administrators.
Private follow-ups and book-chat rows remain owner-only through their existing
APIs. Book administration does not return source paths or raw metadata JSON.

These routes and controls exist only in Server mode. SSG output contains no
administrator markup, job table, SQLite state, login dependency, or `/api/*`
request. No EPUB-derived cache file changes shape, so existing Server book
content renders after deployment without reconversion.

## Error handling and observability

- Invalid pagination and filters return localized stable `400` error codes.
- Unknown jobs/books return `404` without leaking private data.
- Non-retryable or already-active job attempts return stable conflict codes and
  the safe active job when applicable.
- Migration and backup failures fail startup closed and retain the verified
  backup and authoritative original.
- UI actions disable their initiating control while pending and cannot submit
  duplicate retries or saves from repeated clicks.
- Provider exceptions remain represented only by existing sanitized error
  codes; no new raw provider logging is introduced.

## Test strategy

### Database and migration

- Fresh initialization creates exact v11 columns, constraints, foreign keys,
  and indexes and sets `user_version=11`.
- A representative v10 database migrates without losing rows or changing
  annotations, bookshelf documents/versions, progress, sessions, books, AI
  results, jobs, follow-ups, or chat history.
- Numeric session conversion preserves authentication and API timestamps.
- Injected table-copy, row-count, constraint, orphan, and foreign-key failures
  roll back fully.
- WAL-backed committed data appears in the verified SQLite backup.
- Reopening a v11 database is idempotent and creates no new migration backup.
- Controlled query plans use the intended queue, annotation, session, result,
  and pagination indexes; tests avoid depending on unstable planner wording
  beyond scan/index behavior.
- Concurrent writers wait within the busy timeout, while readers remain usable
  during WAL writes.

### AI job administration

- Anonymous and member callers cannot list or retry jobs; administrator GET is
  read-only and POST requires valid CSRF.
- Pagination, status filtering, stable ordering, totals, and maximum page size
  are validated.
- Responses exclude replay JSON, prompts, source text, provider configuration,
  private questions, filesystem paths, and raw errors.
- Failed/interrupted jobs create linked attempts; queued/running/complete or
  malformed legacy jobs cannot be retried.
- Retry uses current configuration/template/material, preserves original owner,
  records the administrator, respects permissions/quota, and wakes the worker.
- Concurrent retry calls create at most one active job per cache key.
- Cached retry completion does not call the provider.
- Browser tests cover filtering, pagination, polling lifecycle, retry states,
  localization, and narrow-screen table structure.

### Book administration

- The lightweight index returns all active summaries with correct batch-derived
  counts/tags and performs a bounded number of SQL queries independent of book
  count.
- Members cannot read details or update settings.
- Full detail is fetched only when a row expands.
- Atomic settings update either changes all four settings groups or none.
- Existing granular administrator endpoints retain their behavior.
- Search matches title, author, tags, Chinese text, and tone-free full pinyin
  through the existing matcher.
- Filtering, sorting, pagination, row patching, result clearing confirmation,
  locale changes, keyboard behavior, and mobile overflow are covered.

### Regression

- Python tests cover StateStore, migration, authorization, Server APIs, AI
  worker lifecycle, and content/cache boundaries.
- Node tests cover administration UI and i18n key parity.
- Full Python and Node suites pass, followed by `git diff --check`.
- `.server-content-revision` remains unchanged.

## Acceptance criteria

- A v10 production database starts through a verified, rollback-safe v11
  migration and retains all valid application data.
- Queue claims no longer full-scan their tables, and duplicate active AI reading
  jobs for one cache key are rejected by SQLite.
- Normal Server request and AI worker contention does not immediately fail with
  `database is locked` under expected single-instance load.
- Administrators can inspect paginated AI reading jobs, understand sanitized
  failures, and safely retry eligible jobs while preserving the original
  attempt.
- Administrators cannot see private follow-up/book-chat contents through the
  new surface.
- Book management remains responsive with a large library, supports pinyin
  search and filters, renders only one page, and loads only one editor on
  demand.
- A book settings save is atomic and updates only the affected UI row.
- Existing Server and SSG behavior, API compatibility, bookshelf conflict
  semantics, book field names, and EPUB content caches remain intact.
