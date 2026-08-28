# Server SQLite Schema v11 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate Server application data to schema v11 with query-aligned indexes, relational constraints, WAL concurrency settings, and WAL-safe verified backups.

**Architecture:** `StateStore` remains the single owner of schema creation and in-transaction upgrades. Fresh databases create v11 directly; older databases first complete the existing ownership migrations and then rebuild only the affected tables. `MigrationManager` snapshots SQLite through the backup API before `StateStore` changes an authoritative database.

**Tech Stack:** Python 3.9+, standard-library `sqlite3`, `unittest`, threads/events for bounded concurrency tests.

**Spec:** `docs/superpowers/specs/2026-08-23-server-schema-admin-operations-design.md`

## Global Constraints

- Preserve existing Server APIs, authorization behavior, bookshelf document/version semantics, and external `book_hash` field names.
- Do not depend on SQLite JSON1, FTS, generated columns, or non-standard extensions.
- Keep `PRAGMA foreign_keys=ON` on every connection; add `busy_timeout=5000` and WAL-compatible `synchronous=NORMAL`.
- Request WAL once after schema initialization; accept SQLite's returned fallback journal mode.
- Use SQLite's backup API for authoritative and legacy SQLite snapshots so committed WAL pages are included.
- Never silently delete unexpected orphan rows or duplicate active AI cache keys during migration.
- Normalize only a legacy `ai_reading_jobs.result_id` that provably points to a missing result.
- Do not change `.server-content-revision`; this is SQLite application state, not EPUB-derived content.
- SSG must not gain SQLite initialization, Server routes, or `/api/*` dependencies.

---

### Task 1: Add the SQLite connection and journal policy

**Files:**
- Modify: `tests/test_state.py`
- Modify: `epub_browser/state.py:1-145`

**Interfaces:**
- Consumes: existing `StateStore(database_path, connection_factory=sqlite3.connect)` and `StateStore.initialize()`.
- Produces: `StateStore._configure_connection(connection) -> None` and `StateStore._configure_database() -> str` returning SQLite's effective journal mode. This task deliberately leaves `DB_SCHEMA_VERSION` at 10 until every v11 migration helper exists.

- [ ] **Step 1: Write failing PRAGMA policy tests**

Add focused assertions to `StateStoreTests`:

```python
def test_connections_enable_busy_timeout_foreign_keys_and_normal_sync(self):
    with self.store._connection() as connection:
        busy_timeout = connection.execute("PRAGMA busy_timeout").fetchone()[0]
        foreign_keys_enabled = connection.execute("PRAGMA foreign_keys").fetchone()[0]
        synchronous = connection.execute("PRAGMA synchronous").fetchone()[0]
    self.assertEqual(busy_timeout, 5000)
    self.assertEqual(foreign_keys_enabled, 1)
    self.assertEqual(synchronous, 1)

def test_initialize_requests_wal_and_records_sqlite_fallback(self):
    journal_mode = self.store._configure_database()
    self.assertIn(journal_mode.lower(), {"wal", "delete", "memory"})
```

- [ ] **Step 2: Run the focused test and verify the v10 shape fails**

Run: `python3 -m unittest tests.test_state.StateStoreTests.test_connections_enable_busy_timeout_foreign_keys_and_normal_sync tests.test_state.StateStoreTests.test_initialize_requests_wal_and_records_sqlite_fallback -v`

Expected: FAIL because the connection has SQLite's default busy timeout/synchronous policy and `_configure_database` does not exist.

- [ ] **Step 3: Implement per-connection and post-initialize database configuration**

In `epub_browser/state.py`, keep the injected connection factory signature unchanged and configure returned connections rather than adding connect kwargs:

```python
@staticmethod
def _configure_connection(connection) -> None:
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    connection.execute("PRAGMA synchronous = NORMAL")

def _connect(self):
    connection = self._connection_factory(self.database_path)
    self._configure_connection(connection)
    return connection

def _configure_database(self) -> str:
    with self._connection() as connection:
        mode = str(connection.execute("PRAGMA journal_mode = WAL").fetchone()[0])
        connection.execute("PRAGMA optimize")
    return mode
```

Call `_configure_database()` only after the initialization transaction commits. Do not issue `journal_mode` from inside `BEGIN IMMEDIATE`.

- [ ] **Step 4: Run connection and existing setup tests**

Run: `python3 -m unittest tests.test_state.StateStoreTests.test_connections_enable_busy_timeout_foreign_keys_and_normal_sync tests.test_state.StateStoreTests.test_initialize_requests_wal_and_records_sqlite_fallback tests.test_state.StateStoreTests.test_initialize_creates_versioned_existing_and_books_tables tests.test_state.StateStoreTests.test_initialize_without_bootstrap_creates_one_stable_pending_administrator -v`

Expected: PASS.

- [ ] **Step 5: Commit the connection policy**

```bash
git add epub_browser/state.py tests/test_state.py
git commit -m "feat: configure server SQLite concurrency"
```

---

### Task 2: Rebuild legacy ownership and session tables transactionally

**Files:**
- Modify: `tests/test_state.py`
- Modify: `epub_browser/state.py:650-1060`

**Interfaces:**
- Consumes: the compatibility-first table shapes and existing v1/v2 ownership methods.
- Produces: inactive migration helpers `_v11_rebuild_owned_state(connection) -> None`, `_v11_rebuild_sessions(connection) -> None`, `_create_v11_annotations_table(connection) -> None`, `_create_v11_bookshelves_table(connection) -> None`, `_create_v11_reading_progress_table(connection) -> None`, `_create_v11_sessions_table(connection) -> None`, and `_assert_matching_row_counts(connection, source, target) -> None`. Task 3 wires them into initialization and changes the schema version.

- [ ] **Step 1: Add a reusable v10-shape fixture helper**

In `tests/test_state.py`, add `_downgrade_selected_tables_to_v10(database)` that opens a fresh test database with foreign keys off, rebuilds `annotations`, `bookshelves`, `reading_progress`, and `sessions` to their exact pre-v11 columns, copies existing rows, drops v11-only indexes, and sets `PRAGMA user_version=10`.

Use explicit old definitions, including:

```sql
CREATE TABLE annotations_v10 (
    id TEXT NOT NULL,
    book_hash TEXT NOT NULL,
    chapter_index INTEGER NOT NULL,
    text TEXT NOT NULL,
    note TEXT,
    start_meta TEXT,
    end_meta TEXT,
    color TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    username TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (user_id, id)
);
CREATE TABLE bookshelves_v10 (
    user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    username TEXT NOT NULL DEFAULT '',
    version INTEGER NOT NULL,
    data TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE reading_progress_v10 (
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    username TEXT NOT NULL DEFAULT '',
    book_hash TEXT NOT NULL,
    chapter_index INTEGER NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, book_hash)
);
```

The session v10 fixture uses `TEXT` for its four epoch columns and includes `client_address` and `user_agent`.

- [ ] **Step 2: Write migration preservation and rollback tests**

Create rows containing non-empty annotation color/selector metadata, a versioned ordered bookshelf document, reading progress, and a live session. Downgrade the selected tables, then call both helpers inside an explicit test transaction and assert:

```python
self.assertNotIn("username", table_columns(connection, "annotations"))
self.assertNotIn("username", table_columns(connection, "bookshelves"))
self.assertNotIn("username", table_columns(connection, "reading_progress"))
self.assertEqual(store.get_bookshelf(self.owner.user_id), (7, shelf_payload))
self.assertEqual(store.get_reading_progress(self.owner.user_id, "book-id"), 9)
self.assertEqual(store.list_sessions(self.owner.user_id)[0].expires_at, 200.0)
```

Add a rollback test that begins one transaction, calls `_v11_rebuild_owned_state`, raises `sqlite3.Error("stop-v11")` before the session helper, rolls back, then compares the pre/post table SQL and row tuples from a separate connection.

- [ ] **Step 3: Run migration tests and verify they fail**

Run: `python3 -m unittest tests.test_state.StateStoreTests.test_v11_owned_state_and_session_helpers_preserve_rows tests.test_state.StateStoreTests.test_v11_rebuild_helpers_roll_back_with_the_caller -v`

Expected: FAIL because no v11 rebuild path exists.

- [ ] **Step 4: Implement explicit table rebuild helpers**

Implement each rebuild with this sequence inside the caller's existing transaction:

```python
connection.execute("ALTER TABLE annotations RENAME TO annotations__v11_source")
self._create_v11_annotations_table(connection)
connection.execute(
    "INSERT INTO annotations (id, book_hash, chapter_index, text, note, start_meta, "
    "end_meta, color, created_at, updated_at, user_id) "
    "SELECT id, book_hash, chapter_index, text, note, start_meta, end_meta, color, "
    "created_at, updated_at, user_id FROM annotations__v11_source"
)
self._assert_matching_row_counts(connection, "annotations__v11_source", "annotations")
connection.execute("DROP TABLE annotations__v11_source")
```

Define the shared count assertion explicitly so a partial copy cannot be committed:

```python
@staticmethod
def _assert_matching_row_counts(connection, source: str, target: str) -> None:
    source_count = connection.execute(f'SELECT COUNT(*) FROM "{source}"').fetchone()[0]
    target_count = connection.execute(f'SELECT COUNT(*) FROM "{target}"').fetchone()[0]
    if source_count != target_count:
        raise sqlite3.IntegrityError(
            f"schema v11 row-count mismatch: {source}={source_count}, {target}={target_count}"
        )
```

Call this helper only with hard-coded migration table names, never user-controlled identifiers. Use distinct `__v11_source` names for all four tables. Convert session epochs with `CAST(column AS REAL)` and reject rows where a required epoch is null or cannot round-trip to a finite float. Preserve nullable `revoked_at`.

Do not call these helpers from `initialize()` yet. Task 3 activates them only after AI table rebuilds and final indexes are ready.

- [ ] **Step 5: Run focused ownership/session regression tests**

Run: `python3 -m unittest tests.test_state.StateStoreTests.test_v11_owned_state_and_session_helpers_preserve_rows tests.test_state.StateStoreTests.test_v11_rebuild_helpers_roll_back_with_the_caller tests.test_state.StateStoreTests.test_v1_user_content_moves_to_bootstrap_administrator tests.test_server.AdminAccountTests.test_user_lists_and_revokes_only_owned_sessions -v`

Expected: PASS.

- [ ] **Step 6: Commit the owned-state and session migration helpers**

```bash
git add epub_browser/state.py tests/test_state.py
git commit -m "refactor: prepare server schema v11 table rebuilds"
```

---

### Task 3: Add AI relational constraints and the final index set

**Files:**
- Modify: `tests/test_state.py`
- Modify: `epub_browser/state.py:330-560,900-1060,2380-3065,3280-3505`

**Interfaces:**
- Consumes: Task 2's owned-state/session rebuild helpers.
- Produces: `DB_SCHEMA_VERSION = 11`, `_migrate_schema_v11(connection, source_version) -> None`, `_v11_rebuild_ai_state(connection) -> None`, `_create_v11_indexes(connection) -> None`, latest fresh table factories, and database-enforced active-cache single flight.

- [ ] **Step 1: Write constraint, legacy-pointer, and orphan tests**

Add these local test helpers before the complete fresh-schema contract and integrated migration tests:

```python
def table_columns(connection, table):
    return {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}

def foreign_key_contract(connection, table):
    return {
        (row[3], row[2], row[4], row[6])
        for row in connection.execute(f"PRAGMA foreign_key_list({table})")
    }
```

The fresh test asserts retry columns, removed ownership columns, REAL session epochs, foreign keys, and `user_version=11`. Create a v10-shaped job/result/chat set, then assert after initialization:

```python
job_fks = foreign_key_contract(connection, "ai_reading_jobs")
self.assertIn(("result_id", "ai_reading_results", "id", "SET NULL"), job_fks)
self.assertIn(("book_id", "books", "book_id", "CASCADE"), foreign_key_contract(connection, "ai_book_chat_turns"))
self.assertIn(("book_id", "books", "book_id", "CASCADE"), foreign_key_contract(connection, "ai_book_chat_summaries"))
self.assertIsNone(connection.execute(
    "SELECT result_id FROM ai_reading_jobs WHERE id='completed-with-cleared-result'"
).fetchone()[0])
```

Add separate failures for an orphan chat `book_id`, two queued jobs sharing one cache key, and a reserved table such as `annotations__v11_source` left in the database. Each must roll back and leave `user_version=10`.

- [ ] **Step 2: Run the new tests and verify failure**

Run: `python3 -m unittest tests.test_state.StateStoreTests.test_v11_fresh_database_has_latest_contract tests.test_state.StateStoreTests.test_v10_ai_tables_gain_v11_constraints tests.test_state.StateStoreTests.test_v11_rejects_orphan_chat_book tests.test_state.StateStoreTests.test_v11_rejects_duplicate_active_cache_keys tests.test_state.StateStoreTests.test_v11_rejects_leftover_migration_tables -v`

Expected: FAIL because the version remains 10, v10 tables are not rebuilt, and the active-cache index is not unique/partial.

- [ ] **Step 3: Rebuild AI job and book-chat tables**

Before copying jobs, set only invalid historical result pointers to null in the source table:

```sql
UPDATE ai_reading_jobs__v11_source
SET result_id = NULL
WHERE result_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM ai_reading_results
      WHERE ai_reading_results.id = ai_reading_jobs__v11_source.result_id
  );
```

Validate no duplicate active cache keys and no missing chat books. Copy existing jobs with `attempt_number=1` and all retry columns null. Copy turns/summaries without changing question, answer, status, order, summary, or timestamps. Add `CHECK(progress_current <= progress_total)` and the failed-row/result-error consistency contract from the spec.

Add latest table-creation helpers used by both a fresh database and rebuilds. Set `DB_SCHEMA_VERSION=11` only in this task. Detect a genuinely empty database with `_has_application_tables(connection)` and create latest shapes directly; otherwise create compatible legacy shapes, complete historical v1/v2 migrations, then call `_migrate_schema_v11`. Before rebuilding, reject leftover tables whose names use the reserved `__v11_source` suffix. After rebuilding and indexing, require an empty `PRAGMA foreign_key_check`, set `PRAGMA user_version=11`, and let the caller commit.

At the same activation point, stop applying `str()` when inserting/updating session epochs. Update `SessionRecord` epoch annotations to `float` and `Optional[float]`; keep `server.py` ISO serialization unchanged because it already calls `float(value)`.

- [ ] **Step 4: Replace old indexes with named v11 indexes**

Create the exact query-aligned indexes with stable names:

```sql
CREATE INDEX idx_books_active_book ON books(active, book_id);
CREATE INDEX idx_annotations_user_created ON annotations(user_id, created_at DESC, id);
CREATE INDEX idx_annotations_user_book_created ON annotations(user_id, book_hash, created_at DESC, id);
CREATE INDEX idx_annotations_user_book_chapter_created ON annotations(user_id, book_hash, chapter_index, created_at DESC, id);
CREATE INDEX idx_sessions_user_created ON sessions(user_id, created_at DESC, session_id);
CREATE INDEX idx_ai_jobs_created ON ai_reading_jobs(created_at DESC, id DESC);
CREATE INDEX idx_ai_jobs_status_created ON ai_reading_jobs(status, created_at DESC, id DESC);
CREATE INDEX idx_ai_jobs_queue ON ai_reading_jobs(created_at, id) WHERE status='queued' AND request_json IS NOT NULL;
CREATE UNIQUE INDEX idx_ai_jobs_active_cache ON ai_reading_jobs(cache_key) WHERE status IN ('queued','running');
CREATE INDEX idx_ai_jobs_result ON ai_reading_jobs(result_id) WHERE result_id IS NOT NULL;
CREATE INDEX idx_ai_jobs_retry_root ON ai_reading_jobs(retry_root_job_id, attempt_number);
CREATE INDEX idx_ai_followups_queue ON ai_reading_followups(created_at, id) WHERE status='queued';
CREATE INDEX idx_ai_followups_result_owner_created ON ai_reading_followups(result_id, owner_user_id, created_at);
CREATE INDEX idx_ai_book_chat_queue ON ai_book_chat_turns(created_at) WHERE status='queued';
CREATE INDEX idx_ai_book_chat_owner_book_created ON ai_book_chat_turns(owner_user_id, book_id, created_at, id);
CREATE INDEX idx_ai_book_chat_result ON ai_book_chat_turns(result_id) WHERE result_id IS NOT NULL;
CREATE INDEX idx_ai_results_book_created ON ai_reading_results(book_id, created_at DESC, id DESC);
CREATE INDEX idx_ai_results_chapter_language_created ON ai_reading_results(book_id, chapter_index, language, created_at DESC, id DESC);
CREATE INDEX idx_ai_current_results_result ON ai_reading_current_results(result_id);
CREATE INDEX idx_book_ai_tags_tag ON book_ai_tags(tag_id);
```

Drop superseded named indexes before creating these. Keep `idx_book_access_user_id`, `idx_user_identities_user_id`, and package-identity lookup.

- [ ] **Step 5: Add query-plan regression tests**

Use `EXPLAIN QUERY PLAN` on controlled rows and assert the details mention `idx_ai_jobs_queue`, `idx_ai_followups_queue`, `idx_ai_book_chat_queue`, the correct annotation index, `idx_sessions_user_created`, and `idx_ai_results_chapter_language_created`. Assert queue plans do not contain `SCAN ai_reading_jobs`, `SCAN ai_reading_followups`, or `SCAN ai_book_chat_turns`.

- [ ] **Step 6: Run state and AI queue tests**

Run: `python3 -m unittest tests.test_state tests.test_ai_reading -v`

Expected: PASS with the database enforcing single flight and existing worker order tests unchanged.

- [ ] **Step 7: Commit AI constraints and indexes**

```bash
git add epub_browser/state.py tests/test_state.py
git commit -m "feat: enforce AI queue integrity and indexes"
```

---

### Task 4: Replace raw SQLite copies with consistent backup snapshots

**Files:**
- Modify: `tests/test_migration.py`
- Modify: `epub_browser/migration.py:120-240`

**Interfaces:**
- Consumes: `DB_SCHEMA_VERSION=11` and `StateStore.initialize()`.
- Produces: `MigrationManager._backup_sqlite_atomic(source: Path, destination: Path) -> None` and WAL-consistent backup behavior for both authoritative and root legacy databases.

- [ ] **Step 1: Write a WAL backup regression test**

Create an authoritative v10 test database, switch it to WAL, disable automatic checkpoint, insert/commit a marker while confirming the `-wal` file exists, and run `_backup_authoritative_database`:

```python
with sqlite3.connect(database) as connection:
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA wal_autocheckpoint=0")
    connection.execute("CREATE TABLE wal_marker(value TEXT)")
    connection.execute("INSERT INTO wal_marker VALUES ('committed-in-wal')")
    connection.commit()
    backup = self._manager()._backup_authoritative_database(database)

with sqlite3.connect(backup) as connection:
    self.assertEqual(connection.execute("SELECT value FROM wal_marker").fetchone()[0], "committed-in-wal")
    self.assertEqual(connection.execute("PRAGMA integrity_check").fetchone()[0], "ok")
```

- [ ] **Step 2: Run the test and verify the raw-copy behavior fails**

Run: `python3 -m unittest tests.test_migration.MigrationManagerTests.test_authoritative_backup_includes_committed_wal_pages -v`

Expected: FAIL because the current copy reads only the main database bytes.

- [ ] **Step 3: Implement atomic SQLite backup snapshots**

Use a sibling temporary file and SQLite's backup API:

```python
def _backup_sqlite_atomic(self, source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.tmp")
    try:
        with sqlite3.connect(source) as source_connection:
            with sqlite3.connect(temporary) as target_connection:
                source_connection.backup(target_connection)
        self._check_integrity(temporary)
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            temporary.unlink()
```

For digest-named backups, snapshot to a temporary database first, hash the closed snapshot, derive the final name from that digest, and atomically rename it. Replace `_copy_atomic` only for SQLite database snapshots; keep ordinary atomic file copy helpers for non-database state if still used.

- [ ] **Step 4: Update failure and idempotency tests**

Patch `_backup_sqlite_atomic` rather than `_copy_atomic` in the existing backup-failure test. Assert no temporary snapshot remains after failure, the authoritative bytes/user version are unchanged, and reopening a current v11 database creates no extra backup.

- [ ] **Step 5: Run all migration tests**

Run: `python3 -m unittest tests.test_migration -v`

Expected: PASS.

- [ ] **Step 6: Commit WAL-safe backups**

```bash
git add epub_browser/migration.py tests/test_migration.py
git commit -m "fix: make server database backups WAL safe"
```

---

### Task 5: Verify concurrency, documentation, and the complete schema migration

**Files:**
- Modify: `tests/test_state.py`
- Modify: `README.md`
- Modify: `docs/readme/README.zh-CN.md`
- Verify: `epub_browser/state.py`
- Verify: `epub_browser/migration.py`

**Interfaces:**
- Consumes: all v11 schema and backup interfaces from Tasks 1-4.
- Produces: verified single-instance concurrency behavior and deployment guidance for local SQLite storage.

- [ ] **Step 1: Add bounded contention tests**

Use two real connections and a thread/event pair. Hold `BEGIN IMMEDIATE` on the first connection, start a `StateStore` write on the second, assert it has not failed before releasing the first transaction, then commit and assert the second completes. In a separate WAL test, hold an uncommitted writer update and assert another connection can still read the last committed value.

Use bounded events and joins rather than timing the whole test:

```python
writer_started = threading.Event()
writer_finished = threading.Event()
writer_error = []

def contend():
    writer_started.set()
    try:
        store.update_reading_progress(owner_id, "book-id", 4)
    except Exception as exc:  # asserted below, never swallowed
        writer_error.append(exc)
    finally:
        writer_finished.set()

thread = threading.Thread(target=contend, daemon=True)
thread.start()
self.assertTrue(writer_started.wait(1.0))
self.assertFalse(writer_finished.wait(0.1))
first_connection.commit()
self.assertTrue(writer_finished.wait(2.0))
thread.join(1.0)
self.assertEqual(writer_error, [])
```

- [ ] **Step 2: Run contention tests**

Run: `python3 -m unittest tests.test_state.StateStoreTests.test_busy_timeout_allows_short_writer_contention tests.test_state.StateStoreTests.test_wal_reader_sees_committed_snapshot_during_write -v`

Expected: PASS without sleeps longer than one second or leaked threads/connections.

- [ ] **Step 3: Document the database filesystem constraint**

Add matching English and Simplified Chinese Server deployment notes: the persistent `data/epub-browser.db` should live on a local filesystem; shared/network filesystems are unsupported for WAL concurrency; backups remain under `data/backups/` and include committed WAL data.

- [ ] **Step 4: Run focused Server data suites**

Run: `python3 -m unittest tests.test_state tests.test_migration tests.test_auth tests.test_server.AdminAccountTests tests.test_ai_reading -v`

Expected: PASS.

- [ ] **Step 5: Run complete regression verification**

Run: `python3 -W ignore::ResourceWarning -m unittest discover -s tests -p 'test_*.py'`

Run: `node --test tests/*.js`

Run: `git diff --check`

Confirm: `.server-content-revision` is byte-for-byte unchanged and SSG tests make no SQLite/API request.

- [ ] **Step 6: Commit documentation and final schema verification**

```bash
git add tests/test_state.py README.md docs/readme/README.zh-CN.md
git commit -m "docs: document server SQLite concurrency"
```
