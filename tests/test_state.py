import json
import re
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from epub_browser.auth import BootstrapCredentials, hash_password, token_digest
from epub_browser.state import DB_SCHEMA_VERSION, StateStore


def table_columns(connection, table):
    return {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}


def foreign_key_contract(connection, table):
    return {
        (row[3], row[2], row[4], row[6])
        for row in connection.execute(f"PRAGMA foreign_key_list({table})")
    }


def index_contract(connection, index_name):
    table, sql = connection.execute(
        "SELECT tbl_name, sql FROM sqlite_master "
        "WHERE type = 'index' AND name = ?",
        (index_name,),
    ).fetchone()
    escaped_table = table.replace('"', '""')
    index_row = next(
        row
        for row in connection.execute(f'PRAGMA index_list("{escaped_table}")')
        if row[1] == index_name
    )
    escaped_index = index_name.replace('"', '""')
    columns = tuple(
        (row[2], bool(row[3]))
        for row in connection.execute(f'PRAGMA index_xinfo("{escaped_index}")')
        if row[5]
    )
    predicate_match = re.search(r"\bWHERE\b(.*)$", sql or "", re.IGNORECASE | re.DOTALL)
    predicate = (
        re.sub(r"\s+", " ", predicate_match.group(1).strip())
        if predicate_match
        else None
    )
    return table, bool(index_row[2]), bool(index_row[4]), columns, predicate


class StateStoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.database = Path(self.temporary.name, "data", "epub-browser.db")
        self.store = StateStore(self.database)
        self.owner = self.store.initialize(
            bootstrap=BootstrapCredentials("owner", "secret")
        )

    def test_connections_enable_busy_timeout_foreign_keys_and_normal_sync(self):
        with self.store._connection() as connection:
            busy_timeout = connection.execute("PRAGMA busy_timeout").fetchone()[0]
            foreign_keys_enabled = connection.execute(
                "PRAGMA foreign_keys"
            ).fetchone()[0]
            synchronous = connection.execute("PRAGMA synchronous").fetchone()[0]
        self.assertEqual(busy_timeout, 5000)
        self.assertEqual(foreign_keys_enabled, 1)
        self.assertEqual(synchronous, 1)

    def test_initialize_requests_wal_and_records_sqlite_fallback(self):
        journal_mode = self.store._configure_database()
        self.assertIn(journal_mode.lower(), {"wal", "delete", "memory"})

    def test_busy_timeout_allows_short_writer_contention(self):
        first_connection = self.store._connect()
        writer_started = threading.Event()
        writer_finished = threading.Event()
        writer_error = []

        def contend():
            writer_started.set()
            try:
                self.store.set_reading_progress(self.owner.user_id, "book-id", 4)
            except Exception as exc:
                writer_error.append(exc)
            finally:
                writer_finished.set()

        thread = threading.Thread(target=contend, daemon=True)
        try:
            first_connection.execute("BEGIN IMMEDIATE")
            thread.start()
            self.assertTrue(writer_started.wait(1.0))
            self.assertFalse(writer_finished.wait(0.1))
            first_connection.commit()
            self.assertTrue(writer_finished.wait(2.0))
            thread.join(1.0)
            self.assertFalse(thread.is_alive())
            self.assertEqual(writer_error, [])
            self.assertEqual(
                self.store.get_reading_progress(self.owner.user_id, "book-id"), 4
            )
        finally:
            if first_connection.in_transaction:
                first_connection.rollback()
            first_connection.close()
            if thread.is_alive():
                self.assertTrue(writer_finished.wait(2.0))
                thread.join(1.0)
                self.assertFalse(thread.is_alive())

    def test_wal_reader_sees_committed_snapshot_during_write(self):
        self.store.set_reading_progress(self.owner.user_id, "book-id", 3)
        writer = self.store._connect()
        reader = self.store._connect()
        try:
            journal_mode = writer.execute("PRAGMA journal_mode").fetchone()[0]
            self.assertEqual(journal_mode.lower(), "wal")
            writer.execute("BEGIN IMMEDIATE")
            writer.execute(
                "UPDATE reading_progress SET chapter_index = 4 "
                "WHERE user_id = ? AND book_hash = ?",
                (self.owner.user_id, "book-id"),
            )

            chapter_index = reader.execute(
                "SELECT chapter_index FROM reading_progress "
                "WHERE user_id = ? AND book_hash = ?",
                (self.owner.user_id, "book-id"),
            ).fetchone()[0]

            self.assertEqual(chapter_index, 3)
        finally:
            if writer.in_transaction:
                writer.rollback()
            writer.close()
            reader.close()

    def test_initialize_creates_versioned_existing_and_books_tables(self):
        with sqlite3.connect(self.database) as connection:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }

        self.assertEqual(version, DB_SCHEMA_VERSION)
        self.assertTrue(
            {"annotations", "bookshelves", "reading_progress", "books"} <= tables
        )

    def test_initialize_adds_session_client_metadata_to_existing_account_database(self):
        database = Path(self.temporary.name, "legacy-session.db")
        password_hash = hash_password("secret")
        with sqlite3.connect(database) as connection:
            connection.executescript(
                """
                CREATE TABLE users (
                    id TEXT PRIMARY KEY,
                    username TEXT NOT NULL COLLATE NOCASE UNIQUE,
                    role TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    password_hash TEXT,
                    setup_pending INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE sessions (
                    session_id TEXT PRIMARY KEY,
                    token_digest TEXT NOT NULL UNIQUE,
                    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    expires_at TEXT NOT NULL,
                    last_used_at TEXT NOT NULL,
                    revoked_at TEXT,
                    created_at TEXT NOT NULL
                );
                PRAGMA user_version = 4;
                """
            )
            connection.execute(
                "INSERT INTO users (id, username, role, password_hash) "
                "VALUES ('admin', 'admin', 'admin', ?)",
                (password_hash,),
            )
            connection.execute(
                "INSERT INTO sessions VALUES (?, ?, ?, ?, ?, NULL, ?)",
                ("old-session", "1" * 64, "admin", "200", "100", "100"),
            )

        store = StateStore(database)
        store.initialize()

        record = store.list_sessions("admin")[0]
        self.assertIsNone(record.client_address)
        self.assertIsNone(record.user_agent)
        with sqlite3.connect(database) as connection:
            columns = {
                row[1] for row in connection.execute("PRAGMA table_info(sessions)")
            }
        self.assertTrue({"client_address", "user_agent"} <= columns)

    def test_v1_user_content_moves_to_bootstrap_administrator(self):
        self._create_v1_database_with_annotation_bookshelf_and_progress(
            "legacy-name"
        )
        store = StateStore(self.database)
        admin = store.initialize(
            bootstrap=BootstrapCredentials("admin", "secret")
        )
        self.assertEqual(
            store.list_annotations(user_id=admin.user_id)[0]["text"],
            "old note",
        )
        self.assertEqual(store.get_bookshelf(user_id=admin.user_id)[0], 7)
        self.assertEqual(store.get_reading_progress(admin.user_id, "book"), 3)

    def test_migration_rolls_back_if_rekeying_bookshelf_fails(self):
        self._create_v1_database_with_annotation_bookshelf_and_progress(
            "legacy-name"
        )
        before = self._database_snapshot()
        with mock.patch.object(
            StateStore,
            "_migrate_bookshelves",
            side_effect=sqlite3.Error("stop"),
        ):
            with self.assertRaises(sqlite3.Error):
                StateStore(self.database).initialize(
                    bootstrap=BootstrapCredentials("admin", "secret")
                )
        self.assertEqual(self._database_snapshot(), before)

    def test_initialize_without_bootstrap_migrates_v1_data_to_pending_administrator(self):
        self._create_v1_database_with_annotation_bookshelf_and_progress(
            "legacy-name"
        )
        store = StateStore(self.database)

        pending = store.initialize()

        user = store.get_user(pending.user_id)
        self.assertFalse(store.has_administrator())
        self.assertFalse(user.enabled)
        self.assertIsNone(user.password_hash)
        self.assertEqual(
            store.list_annotations(user_id=pending.user_id)[0]["text"],
            "old note",
        )
        self.assertEqual(store.get_bookshelf(pending.user_id)[0], 7)
        self.assertEqual(store.get_reading_progress(pending.user_id, "book"), 3)

    def test_initialize_without_bootstrap_creates_one_stable_pending_administrator(self):
        database = Path(self.temporary.name, "fresh", "state.db")
        store = StateStore(database)

        first = store.initialize()
        second = store.initialize()

        self.assertEqual(second.user_id, first.user_id)
        self.assertEqual(len(store.list_users()), 1)
        self.assertFalse(store.has_administrator())

    def test_unattended_bootstrap_completes_pending_administrator_in_place(self):
        database = Path(self.temporary.name, "pending", "state.db")
        store = StateStore(database)
        pending = store.initialize()

        completed = store.initialize(BootstrapCredentials("Owner", "secret"))

        user = store.get_user(completed.user_id)
        self.assertEqual(completed.user_id, pending.user_id)
        self.assertEqual(user.username, "owner")
        self.assertTrue(user.enabled)
        self.assertTrue(store.has_administrator())
        self.assertEqual(len(store.list_users()), 1)

    def test_setup_activation_and_session_insert_roll_back_together(self):
        database = Path(self.temporary.name, "atomic", "state.db")
        store = StateStore(database)
        pending = store.initialize()
        raw_token = "setup-session-token"
        digest = token_digest(raw_token)
        store.create_session(digest, pending.user_id, 200, now=100)

        with self.assertRaises(sqlite3.IntegrityError):
            store.complete_administrator_setup(
                "owner",
                hash_password("secret"),
                digest,
                300,
                now=100,
            )

        user = store.get_user(pending.user_id)
        self.assertFalse(user.enabled)
        self.assertIsNone(user.password_hash)
        self.assertFalse(store.has_administrator())

    def test_initialize_without_bootstrap_reuses_existing_administrator(self):
        self.assertEqual(self.store.initialize(), self.owner)

    def test_restart_fails_closed_when_any_local_password_hash_is_corrupt(self):
        member = self.store.create_user("member", hash_password("member-secret"))
        with sqlite3.connect(self.database) as connection:
            connection.execute(
                "UPDATE users SET password_hash = ? WHERE id = ?",
                ("not-an-argon2-hash", member.user_id),
            )

        with self.assertRaisesRegex(RuntimeError, "password hash"):
            StateStore(self.database).initialize()

        self.assertEqual(
            self.store.get_user_by_username("owner").password_hash,
            self.store.get_user(self.owner.user_id).password_hash,
        )

    def test_restart_rejects_structurally_invalid_argon2id_encodings(self):
        malformed_hashes = (
            "$argon2id$v=19$m=65536,t=3,p=4$bad$bad",
            "$argon2id$v=19$m=65536,t=3,p=4$$",
            "$argon2id$v=19$m=65536,t=3,p=4$c2FsdA$",
            "$argon2id$v=19$m=65536,t=3,p=4$$ZGlnZXN0",
        )
        for encoded in malformed_hashes:
            with self.subTest(encoded=encoded), tempfile.TemporaryDirectory() as directory:
                database = Path(directory, "state.db")
                store = StateStore(database)
                administrator = store.initialize(
                    bootstrap=BootstrapCredentials("owner", "secret")
                )
                with sqlite3.connect(database) as connection:
                    connection.execute(
                        "UPDATE users SET password_hash = ? WHERE id = ?",
                        (encoded, administrator.user_id),
                    )

                with self.assertRaisesRegex(RuntimeError, "password hash"):
                    StateStore(database).initialize()

    def test_v1_colliding_bookshelves_keep_highest_version_newest_deterministically(self):
        self._create_v1_database_with_annotation_bookshelf_and_progress("zeta")
        with sqlite3.connect(self.database) as connection:
            connection.execute(
                """
                UPDATE bookshelves
                SET version = 6, data = '{"owner":"zeta"}',
                    updated_at = '2027-01-01'
                WHERE username = 'zeta'
                """
            )
            connection.executemany(
                """
                INSERT INTO bookshelves (
                    username, version, data, updated_at
                ) VALUES (?, ?, ?, ?)
                """,
                (
                    ("beta", 7, '{"owner":"beta"}', "2026-01-01"),
                    ("alpha", 7, '{"owner":"alpha"}', "2026-01-01"),
                ),
            )

        store = StateStore(self.database)
        admin = store.initialize(BootstrapCredentials("admin", "secret"))

        self.assertEqual(
            store.get_bookshelf(admin.user_id),
            (7, '{"owner":"alpha"}'),
        )
        with sqlite3.connect(self.database) as connection:
            self.assertNotIn("username", table_columns(connection, "bookshelves"))

    def test_v1_colliding_progress_keeps_newest_with_deterministic_tie_break(self):
        self._create_v1_database_with_annotation_bookshelf_and_progress("zeta")
        with sqlite3.connect(self.database) as connection:
            connection.execute(
                """
                UPDATE reading_progress
                SET chapter_index = 3, updated_at = '2025-01-01'
                WHERE username = 'zeta' AND book_hash = 'book'
                """
            )
            connection.executemany(
                """
                INSERT INTO reading_progress (
                    username, book_hash, chapter_index, updated_at
                ) VALUES (?, ?, ?, ?)
                """,
                (
                    ("beta", "book", 8, "2026-01-01"),
                    ("alpha", "book", 4, "2026-01-01"),
                    ("beta", "other-book", 9, "2024-01-01"),
                ),
            )

        store = StateStore(self.database)
        admin = store.initialize(BootstrapCredentials("admin", "secret"))

        self.assertEqual(store.get_reading_progress(admin.user_id, "book"), 4)
        self.assertEqual(
            store.get_reading_progress(admin.user_id, "other-book"),
            9,
        )
        with sqlite3.connect(self.database) as connection:
            self.assertNotIn("username", table_columns(connection, "reading_progress"))

    def test_content_update_keeps_book_id(self):
        source = Path(self.temporary.name, "books", "one.epub")
        metadata = {"title": "One", "authors": ["A"]}

        record = self.store.resolve_book(
            source,
            "epub-id",
            "fingerprint-a",
            metadata,
            source_size=10,
            source_mtime_ns=20,
        )
        updated = self.store.update_book_version(
            record.book_id,
            "fingerprint-b",
            {"title": "Updated", "authors": ["A"]},
            source_size=11,
            source_mtime_ns=21,
        )

        self.assertEqual(updated.book_id, record.book_id)
        self.assertEqual(updated.source_fingerprint, "fingerprint-b")
        self.assertEqual(json.loads(updated.metadata_json)["title"], "Updated")

    def test_restricted_book_requires_matching_grant(self):
        self.store.resolve_book(
            Path(self.temporary.name, "book.epub"),
            None,
            "fingerprint",
            {"title": "Book"},
            preferred_book_id="book-1",
        )
        admin = self.store.create_user("admin", "hash", role="admin")
        member = self.store.create_user("member", "hash", role="member")
        self.store.set_book_visibility("book-1", "restricted")
        self.assertFalse(
            self.store.can_read_book(member.user_id, member.role, "book-1")
        )
        self.store.grant_book_access("book-1", member.user_id)
        self.assertTrue(
            self.store.can_read_book(member.user_id, member.role, "book-1")
        )

    def test_replace_book_grants_is_atomic_and_member_only(self):
        self.store.resolve_book(
            Path(self.temporary.name, "batch.epub"),
            None,
            "batch-fingerprint",
            {"title": "Batch"},
            preferred_book_id="batch-book",
        )
        first = self.store.create_user("first", "hash", role="member")
        second = self.store.create_user("second", "hash", role="member")
        disabled = self.store.create_user("disabled", "hash", role="member")
        self.store.set_user_enabled(disabled.user_id, False)

        grants = self.store.replace_book_grants(
            "batch-book",
            [second.user_id, first.user_id, second.user_id],
        )

        self.assertEqual(grants, tuple(sorted((first.user_id, second.user_id))))
        self.assertEqual(self.store.book_grants("batch-book"), grants)
        with self.assertRaises(ValueError):
            self.store.replace_book_grants(
                "batch-book",
                [first.user_id, disabled.user_id],
            )
        self.assertEqual(self.store.book_grants("batch-book"), grants)
        with self.assertRaises(ValueError):
            self.store.replace_book_grants(
                "batch-book",
                [self.owner.user_id],
            )
        self.assertEqual(self.store.book_grants("batch-book"), grants)

    def test_new_book_can_preserve_a_correlated_legacy_identity(self):
        record = self.store.resolve_book(
            Path(self.temporary.name, "legacy.epub"),
            "urn:test:legacy",
            "fingerprint",
            {"title": "Legacy"},
            preferred_book_id="legacy-toc-hash",
        )

        self.assertEqual(record.book_id, "legacy-toc-hash")

    def test_unique_inactive_identifier_and_fingerprint_match_preserves_move_identity(self):
        original = Path(self.temporary.name, "old", "book.epub")
        moved = Path(self.temporary.name, "new", "book.epub")
        record = self.store.resolve_book(
            original,
            "urn:test:move",
            "same-content",
            {"title": "Book"},
        )
        self.store.mark_missing(record.book_id)

        resolved = self.store.resolve_book(
            moved,
            "urn:test:move",
            "same-content",
            {"title": "Book"},
        )

        self.assertEqual(resolved.book_id, record.book_id)
        self.assertEqual(resolved.source_path, str(moved.resolve()))
        self.assertTrue(resolved.active)

    def test_ambiguous_inactive_move_is_refused(self):
        first = self.store.resolve_book(
            Path(self.temporary.name, "first.epub"),
            "urn:test:ambiguous",
            "same-content",
            {"title": "Book"},
        )
        second = self.store.resolve_book(
            Path(self.temporary.name, "second.epub"),
            "urn:test:ambiguous",
            "same-content",
            {"title": "Book"},
        )
        self.store.mark_missing(first.book_id)
        self.store.mark_missing(second.book_id)
        matches = self.store.inactive_book_matches(
            "urn:test:ambiguous",
            "same-content",
        )
        self.assertEqual(
            {record.book_id for record in matches},
            {first.book_id, second.book_id},
        )
        with self.assertRaisesRegex(ValueError, "Multiple inactive"):
            self.store.resolve_book(
                Path(self.temporary.name, "moved.epub"),
                "urn:test:ambiguous",
                "same-content",
                {"title": "Book"},
            )

    def test_authoritative_id_selects_exact_inactive_row_despite_ambiguity(self):
        first = self.store.resolve_book(
            Path(self.temporary.name, "first.epub"),
            "urn:test:ambiguous",
            "same-content",
            {"title": "Book"},
        )
        second = self.store.resolve_book(
            Path(self.temporary.name, "second.epub"),
            "urn:test:ambiguous",
            "same-content",
            {"title": "Book"},
        )
        self.store.mark_missing(first.book_id)
        self.store.mark_missing(second.book_id)
        moved = self.store.resolve_book(
            Path(self.temporary.name, "moved.epub"),
            "urn:test:ambiguous",
            "same-content",
            {"title": "Book"},
            authoritative_book_id=first.book_id,
        )
        self.assertEqual(moved.book_id, first.book_id)
        self.assertTrue(moved.active)

    def test_mark_missing_does_not_delete_user_data(self):
        record = self.store.resolve_book(
            Path(self.temporary.name, "book.epub"),
            "urn:test:data",
            "fingerprint",
            {"title": "Book"},
        )
        self.store.upsert_annotation(
            {
                "id": "annotation",
                "book_hash": record.book_id,
                "chapter_index": 0,
                "text": "Text",
                "note": "Note",
                "color": "#fff",
                "created_at": "2026-01-01",
                "updated_at": "2026-01-01",
            },
            user_id=self.owner.user_id,
        )

        self.store.mark_missing(record.book_id)

        self.assertEqual(self.store.active_books(), ())
        self.assertEqual(
            self.store.get_annotation(
                "annotation",
                user_id=self.owner.user_id,
            )["book_hash"],
            record.book_id,
        )

    def test_annotations_require_an_existing_nonempty_owner(self):
        annotation = {
            "id": "owned",
            "book_hash": "book",
            "chapter_index": 0,
            "text": "Text",
            "color": "#fff",
            "created_at": "2026",
            "updated_at": "2026",
        }

        with self.assertRaises(TypeError):
            self.store.upsert_annotation(annotation)
        with self.assertRaises(ValueError):
            self.store.upsert_annotation(annotation, user_id="")
        with self.assertRaises(KeyError):
            self.store.upsert_annotation(annotation, user_id="missing")

        with sqlite3.connect(self.database) as connection:
            user_id = next(
                row
                for row in connection.execute("PRAGMA table_info(annotations)")
                if row[1] == "user_id"
            )
            foreign_keys = connection.execute(
                "PRAGMA foreign_key_list(annotations)"
            ).fetchall()
        self.assertEqual(user_id[3], 1)
        self.assertIsNone(user_id[4])
        self.assertIn("users", {row[2] for row in foreign_keys})

    def test_v2_annotation_ids_are_rekeyed_per_owner_without_data_loss(self):
        member = self.store.create_user("member", hash_password("member-secret"))
        with sqlite3.connect(self.database) as connection:
            connection.execute("DROP TABLE annotations")
            connection.execute(
                """
                CREATE TABLE annotations (
                    id TEXT PRIMARY KEY,
                    username TEXT NOT NULL DEFAULT '',
                    user_id TEXT NOT NULL CHECK(length(user_id) > 0)
                        REFERENCES users(id) ON DELETE CASCADE,
                    book_hash TEXT NOT NULL,
                    chapter_index INTEGER NOT NULL,
                    text TEXT NOT NULL,
                    note TEXT,
                    start_meta TEXT,
                    end_meta TEXT,
                    color TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                INSERT INTO annotations (
                    id, user_id, book_hash, chapter_index, text, color,
                    created_at, updated_at
                ) VALUES ('shared', ?, 'book', 1, 'owner note', '#fff',
                          '2026', '2026')
                """,
                (self.owner.user_id,),
            )
            connection.execute("PRAGMA user_version = 2")

        migrated = StateStore(self.database)
        migrated.initialize()
        migrated.upsert_annotation(
            {
                "id": "shared",
                "book_hash": "book",
                "chapter_index": 2,
                "text": "member note",
                "color": "#000",
                "created_at": "2027",
                "updated_at": "2027",
            },
            user_id=member.user_id,
            replace_existing=True,
        )

        owner_saved = migrated.get_annotation(
            "shared",
            user_id=self.owner.user_id,
        )
        member_saved = migrated.get_annotation("shared", user_id=member.user_id)
        self.assertIsNotNone(owner_saved)
        self.assertEqual(owner_saved["text"], "owner note")
        self.assertIsNotNone(member_saved)
        self.assertEqual(member_saved["text"], "member note")

    def test_initialize_rejects_a_database_from_a_newer_schema(self):
        future = Path(self.temporary.name, "future.db")
        with sqlite3.connect(future) as connection:
            connection.execute(f"PRAGMA user_version = {DB_SCHEMA_VERSION + 1}")

        with self.assertRaisesRegex(RuntimeError, "newer schema"):
            StateStore(future).initialize()

    def test_v11_fresh_database_has_latest_contract(self):
        database = Path(self.temporary.name, "fresh-v11.db")
        StateStore(database).initialize(
            bootstrap=BootstrapCredentials("fresh-owner", "secret")
        )
        StateStore(database).initialize()

        with sqlite3.connect(database) as connection:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 11)
            self.assertFalse(
                {"username"} & table_columns(connection, "annotations")
            )
            self.assertFalse(
                {"username"} & table_columns(connection, "bookshelves")
            )
            self.assertFalse(
                {"username"} & table_columns(connection, "reading_progress")
            )
            self.assertTrue(
                {
                    "attempt_number",
                    "retried_from_job_id",
                    "retry_root_job_id",
                    "retried_by_user_id",
                }
                <= table_columns(connection, "ai_reading_jobs")
            )
            job_columns = {
                row[1]: (row[2], bool(row[3]), row[4])
                for row in connection.execute("PRAGMA table_info(ai_reading_jobs)")
            }
            self.assertEqual(
                {
                    name: job_columns[name]
                    for name in (
                        "attempt_number",
                        "retried_from_job_id",
                        "retry_root_job_id",
                        "retried_by_user_id",
                    )
                },
                {
                    "attempt_number": ("INTEGER", True, "1"),
                    "retried_from_job_id": ("TEXT", False, None),
                    "retry_root_job_id": ("TEXT", False, None),
                    "retried_by_user_id": ("TEXT", False, None),
                },
            )
            session_types = {
                row[1]: row[2]
                for row in connection.execute("PRAGMA table_info(sessions)")
            }
            self.assertEqual(
                {
                    name: session_types[name]
                    for name in ("expires_at", "last_used_at", "revoked_at", "created_at")
                },
                {
                    "expires_at": "REAL",
                    "last_used_at": "REAL",
                    "revoked_at": "REAL",
                    "created_at": "REAL",
                },
            )
            job_fks = foreign_key_contract(connection, "ai_reading_jobs")
            self.assertIn(("result_id", "ai_reading_results", "id", "SET NULL"), job_fks)
            self.assertIn(("retried_from_job_id", "ai_reading_jobs", "id", "SET NULL"), job_fks)
            self.assertIn(("retry_root_job_id", "ai_reading_jobs", "id", "SET NULL"), job_fks)
            self.assertIn(("retried_by_user_id", "users", "id", "SET NULL"), job_fks)
            self.assertIn(
                ("book_id", "books", "book_id", "CASCADE"),
                foreign_key_contract(connection, "ai_book_chat_turns"),
            )
            self.assertIn(
                ("book_id", "books", "book_id", "CASCADE"),
                foreign_key_contract(connection, "ai_book_chat_summaries"),
            )
            expected_indexes = {
                "idx_books_active_book": (
                    "books", False, False, (("active", False), ("book_id", False)), None,
                ),
                "idx_annotations_user_created": (
                    "annotations", False, False,
                    (("user_id", False), ("created_at", True), ("id", False)), None,
                ),
                "idx_annotations_user_book_created": (
                    "annotations", False, False,
                    (("user_id", False), ("book_hash", False),
                     ("created_at", True), ("id", False)), None,
                ),
                "idx_annotations_user_book_chapter_created": (
                    "annotations", False, False,
                    (("user_id", False), ("book_hash", False),
                     ("chapter_index", False), ("created_at", True),
                     ("id", False)), None,
                ),
                "idx_sessions_user_created": (
                    "sessions", False, False,
                    (("user_id", False), ("created_at", True),
                     ("session_id", False)), None,
                ),
                "idx_ai_jobs_created": (
                    "ai_reading_jobs", False, False,
                    (("created_at", True), ("id", True)), None,
                ),
                "idx_ai_jobs_status_created": (
                    "ai_reading_jobs", False, False,
                    (("status", False), ("created_at", True), ("id", True)), None,
                ),
                "idx_ai_jobs_queue": (
                    "ai_reading_jobs", False, True,
                    (("created_at", False), ("id", False)),
                    "status='queued' AND request_json IS NOT NULL",
                ),
                "idx_ai_jobs_active_cache": (
                    "ai_reading_jobs", True, True, (("cache_key", False),),
                    "status IN ('queued','running')",
                ),
                "idx_ai_jobs_result": (
                    "ai_reading_jobs", False, True, (("result_id", False),),
                    "result_id IS NOT NULL",
                ),
                "idx_ai_jobs_retry_root": (
                    "ai_reading_jobs", False, False,
                    (("retry_root_job_id", False), ("attempt_number", False)), None,
                ),
                "idx_ai_followups_queue": (
                    "ai_reading_followups", False, True,
                    (("created_at", False), ("id", False)), "status='queued'",
                ),
                "idx_ai_followups_result_owner_created": (
                    "ai_reading_followups", False, False,
                    (("result_id", False), ("owner_user_id", False),
                     ("created_at", False)), None,
                ),
                "idx_ai_book_chat_queue": (
                    "ai_book_chat_turns", False, True, (("created_at", False),),
                    "status='queued'",
                ),
                "idx_ai_book_chat_owner_book_created": (
                    "ai_book_chat_turns", False, False,
                    (("owner_user_id", False), ("book_id", False),
                     ("created_at", False), ("id", False)), None,
                ),
                "idx_ai_book_chat_result": (
                    "ai_book_chat_turns", False, True, (("result_id", False),),
                    "result_id IS NOT NULL",
                ),
                "idx_ai_results_book_created": (
                    "ai_reading_results", False, False,
                    (("book_id", False), ("created_at", True), ("id", True)), None,
                ),
                "idx_ai_results_chapter_language_created": (
                    "ai_reading_results", False, False,
                    (("book_id", False), ("chapter_index", False),
                     ("language", False), ("created_at", True), ("id", True)), None,
                ),
                "idx_ai_current_results_result": (
                    "ai_reading_current_results", False, False,
                    (("result_id", False),), None,
                ),
                "idx_book_ai_tags_tag": (
                    "book_ai_tags", False, False, (("tag_id", False),), None,
                ),
            }
            self.assertEqual(
                {
                    name: index_contract(connection, name)
                    for name in expected_indexes
                },
                expected_indexes,
            )
            connection.execute(
                "INSERT INTO ai_reading_jobs "
                "(id, owner_user_id, cache_key, status) "
                "VALUES ('default-attempt', ?, 'default-attempt', 'queued')",
                (connection.execute("SELECT id FROM users LIMIT 1").fetchone()[0],),
            )
            self.assertEqual(
                connection.execute(
                    "SELECT attempt_number FROM ai_reading_jobs "
                    "WHERE id = 'default-attempt'"
                ).fetchone()[0],
                1,
            )
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "INSERT INTO ai_reading_jobs "
                    "(id, owner_user_id, cache_key, status, attempt_number) "
                    "VALUES ('bad-attempt', ?, 'bad-attempt', 'queued', 0)",
                    (connection.execute("SELECT id FROM users LIMIT 1").fetchone()[0],),
                )
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "INSERT INTO ai_reading_jobs "
                    "(id, owner_user_id, cache_key, status, progress_current, progress_total) "
                    "VALUES ('bad-progress', ?, 'bad-progress', 'queued', 2, 1)",
                    (connection.execute("SELECT id FROM users LIMIT 1").fetchone()[0],),
                )
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "INSERT INTO ai_reading_jobs "
                    "(id, owner_user_id, cache_key, status) "
                    "VALUES ('failed-without-error', ?, 'failed-without-error', 'failed')",
                    (connection.execute("SELECT id FROM users LIMIT 1").fetchone()[0],),
                )

    def test_v11_restart_does_not_create_or_drop_superseded_indexes(self):
        statements = []

        def connect(path):
            connection = sqlite3.connect(path)
            connection.set_trace_callback(statements.append)
            return connection

        with sqlite3.connect(self.database) as connection:
            before = dict(
                connection.execute(
                    "SELECT name, rootpage FROM sqlite_master "
                    "WHERE type = 'index' AND name LIKE 'idx_%'"
                )
            )

        StateStore(self.database, connection_factory=connect).initialize()

        superseded = {
            "idx_books_active",
            "idx_annotations_chapter_user_id",
            "idx_annotations_book_user_id",
            "idx_annotations_user_id",
            "idx_bookshelves_user_id",
            "idx_reading_progress_user_id",
            "idx_sessions_user_id",
            "idx_ai_reading_jobs_owner",
            "idx_ai_reading_jobs_active_cache",
            "idx_ai_reading_results_book",
            "idx_ai_reading_followups_owner",
            "idx_ai_book_chat_turns_owner_book",
        }
        index_ddl = tuple(
            statement
            for statement in statements
            if re.match(r"\s*(?:CREATE|DROP)\s+(?:UNIQUE\s+)?INDEX\b", statement, re.I)
        )
        for index_name in superseded:
            self.assertFalse(
                any(
                    re.search(
                        rf"(?<![A-Za-z0-9_]){re.escape(index_name)}"
                        r"(?![A-Za-z0-9_])",
                        statement,
                    )
                    for statement in index_ddl
                ),
                index_ddl,
            )
        with sqlite3.connect(self.database) as connection:
            after = dict(
                connection.execute(
                    "SELECT name, rootpage FROM sqlite_master "
                    "WHERE type = 'index' AND name LIKE 'idx_%'"
                )
            )
        self.assertEqual(after, before)

    def test_v11_restart_repairs_colliding_active_cache_index(self):
        with sqlite3.connect(self.database) as connection:
            connection.execute("DROP INDEX idx_ai_jobs_active_cache")
            connection.execute(
                "CREATE INDEX idx_ai_jobs_active_cache "
                "ON ai_reading_jobs(status, cache_key) WHERE status = 'queued'"
            )

        StateStore(self.database).initialize()

        with sqlite3.connect(self.database) as connection:
            self.assertEqual(
                index_contract(connection, "idx_ai_jobs_active_cache"),
                (
                    "ai_reading_jobs",
                    True,
                    True,
                    (("cache_key", False),),
                    "status IN ('queued','running')",
                ),
            )
            connection.execute(
                "INSERT INTO ai_reading_jobs "
                "(id, owner_user_id, cache_key, status) "
                "VALUES ('collision-one', ?, 'collision-key', 'queued')",
                (self.owner.user_id,),
            )
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "INSERT INTO ai_reading_jobs "
                    "(id, owner_user_id, cache_key, status) "
                    "VALUES ('collision-two', ?, 'collision-key', 'running')",
                    (self.owner.user_id,),
                )

    def test_v11_restart_fails_closed_if_colliding_index_hides_duplicates(self):
        with sqlite3.connect(self.database) as connection:
            connection.execute("DROP INDEX idx_ai_jobs_active_cache")
            connection.execute(
                "CREATE INDEX idx_ai_jobs_active_cache "
                "ON ai_reading_jobs(status, cache_key) WHERE status = 'queued'"
            )
            connection.executemany(
                "INSERT INTO ai_reading_jobs "
                "(id, owner_user_id, cache_key, status) VALUES (?, ?, 'duplicate', ?)",
                (
                    ("duplicate-one", self.owner.user_id, "queued"),
                    ("duplicate-two", self.owner.user_id, "running"),
                ),
            )

        with self.assertRaises(sqlite3.IntegrityError):
            StateStore(self.database).initialize()

        with sqlite3.connect(self.database) as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM ai_reading_jobs WHERE cache_key = 'duplicate'"
                ).fetchone()[0],
                2,
            )
            self.assertEqual(
                index_contract(connection, "idx_ai_jobs_active_cache"),
                (
                    "ai_reading_jobs",
                    False,
                    True,
                    (("status", False), ("cache_key", False)),
                    "status = 'queued'",
                ),
            )

    def test_v10_ai_tables_gain_v11_constraints(self):
        self._downgrade_selected_tables_to_v10(self.database)
        self._downgrade_ai_tables_to_v10(self.database)
        with sqlite3.connect(self.database) as connection:
            connection.execute(
                "INSERT INTO books (book_id, source_path, source_fingerprint, metadata_json) "
                "VALUES ('book-v10', '/book-v10.epub', 'fingerprint', '{}')"
            )
            connection.execute(
                "INSERT INTO ai_reading_results "
                "(id, cache_key, book_id, scope, mode, profile, config_revision, "
                "content_json, created_by_user_id) "
                "VALUES ('result-v10', 'result-key', 'book-v10', 'book', "
                "'full_review', 'general', 0, '{}', ?)",
                (self.owner.user_id,),
            )
            connection.execute(
                "INSERT INTO ai_reading_jobs "
                "(id, owner_user_id, book_id, cache_key, request_json, profile, "
                "template_id, template_version, status, result_id, progress_current, "
                "progress_total, created_at, updated_at) VALUES "
                "('completed-with-result', ?, 'book-v10', 'job-key-1', '{}', 'general', "
                "'reading-layer', 3, 'complete', 'result-v10', 1, 1, '2026-01', '2026-02'), "
                "('completed-with-cleared-result', ?, 'book-v10', 'job-key-2', '{}', "
                "'general', 'reading-layer', 3, 'complete', 'missing-result', 1, 1, "
                "'2026-03', '2026-04')",
                (self.owner.user_id, self.owner.user_id),
            )
            connection.execute(
                "INSERT INTO ai_book_chat_turns "
                "(id, book_id, chapter_index, result_id, context_mode, book_context, "
                "owner_user_id, question, language, answer, status, created_at, updated_at) "
                "VALUES ('turn-v10', 'book-v10', 4, 'result-v10', 'shared_layer', 1, ?, "
                "'Original question?', 'en', 'Original answer.', 'complete', "
                "'2026-05', '2026-06')",
                (self.owner.user_id,),
            )
            connection.execute(
                "INSERT INTO ai_book_chat_summaries "
                "(book_id, owner_user_id, language, covered_turn_count, summary_text, updated_at) "
                "VALUES ('book-v10', ?, 'en', 1, 'Original summary.', '2026-07')",
                (self.owner.user_id,),
            )

        StateStore(self.database).initialize()

        with sqlite3.connect(self.database) as connection:
            job_fks = foreign_key_contract(connection, "ai_reading_jobs")
            self.assertIn(("result_id", "ai_reading_results", "id", "SET NULL"), job_fks)
            self.assertIn(
                ("book_id", "books", "book_id", "CASCADE"),
                foreign_key_contract(connection, "ai_book_chat_turns"),
            )
            self.assertIn(
                ("book_id", "books", "book_id", "CASCADE"),
                foreign_key_contract(connection, "ai_book_chat_summaries"),
            )
            self.assertIsNone(
                connection.execute(
                    "SELECT result_id FROM ai_reading_jobs "
                    "WHERE id='completed-with-cleared-result'"
                ).fetchone()[0]
            )
            self.assertEqual(
                connection.execute(
                    "SELECT result_id, attempt_number, retried_from_job_id, "
                    "retry_root_job_id, retried_by_user_id, created_at, updated_at "
                    "FROM ai_reading_jobs WHERE id='completed-with-result'"
                ).fetchone(),
                ("result-v10", 1, None, None, None, "2026-01", "2026-02"),
            )
            self.assertEqual(
                connection.execute(
                    "SELECT question, answer, status, created_at, updated_at "
                    "FROM ai_book_chat_turns WHERE id='turn-v10'"
                ).fetchone(),
                ("Original question?", "Original answer.", "complete", "2026-05", "2026-06"),
            )
            self.assertEqual(
                connection.execute(
                    "SELECT covered_turn_count, summary_text, updated_at "
                    "FROM ai_book_chat_summaries WHERE book_id='book-v10'"
                ).fetchone(),
                (1, "Original summary.", "2026-07"),
            )
            self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 11)

    def test_concurrent_initializer_rereads_user_version_after_lock(self):
        self._downgrade_selected_tables_to_v10(self.database)
        self._downgrade_ai_tables_to_v10(self.database)
        with sqlite3.connect(self.database) as connection:
            connection.executemany(
                "INSERT INTO ai_reading_jobs "
                "(id, owner_user_id, cache_key, request_json, status) "
                "VALUES (?, ?, ?, '{}', 'complete')",
                (
                    ("retry-root", self.owner.user_id, "retry-root-key"),
                    ("attempt-two", self.owner.user_id, "attempt-two-key"),
                ),
            )

        migration_ready = threading.Event()
        release_migration = threading.Event()
        second_begin_attempted = threading.Event()
        errors = []

        class BlockingMigrator(StateStore):
            def _migrate_schema_v11(inner_self, connection, source_version):
                super()._migrate_schema_v11(connection, source_version)
                connection.execute(
                    "UPDATE ai_reading_jobs SET attempt_number = 2, "
                    "retried_from_job_id = 'retry-root', "
                    "retry_root_job_id = 'retry-root', retried_by_user_id = ? "
                    "WHERE id = 'attempt-two'",
                    (self.owner.user_id,),
                )
                migration_ready.set()
                if not release_migration.wait(5):
                    raise RuntimeError("timed out waiting to commit schema v11")

        class BeginObservedConnection(sqlite3.Connection):
            def execute(inner_self, statement, parameters=()):
                if statement.strip().upper() == "BEGIN IMMEDIATE":
                    second_begin_attempted.set()
                return super().execute(statement, parameters)

        def initialize(store):
            try:
                store.initialize()
            except BaseException as error:
                errors.append(error)

        first = threading.Thread(target=initialize, args=(BlockingMigrator(self.database),))
        second = threading.Thread(
            target=initialize,
            args=(
                StateStore(
                    self.database,
                    connection_factory=lambda path: sqlite3.connect(
                        path,
                        factory=BeginObservedConnection,
                    ),
                ),
            ),
        )
        first.start()
        self.assertTrue(migration_ready.wait(5))
        second.start()
        self.assertTrue(second_begin_attempted.wait(5))
        release_migration.set()
        first.join(5)
        second.join(5)
        self.assertFalse(first.is_alive())
        self.assertFalse(second.is_alive())
        self.assertEqual(errors, [])

        with sqlite3.connect(self.database) as connection:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 11)
            self.assertEqual(
                connection.execute(
                    "SELECT attempt_number, retried_from_job_id, retry_root_job_id, "
                    "retried_by_user_id FROM ai_reading_jobs WHERE id = 'attempt-two'"
                ).fetchone(),
                (2, "retry-root", "retry-root", self.owner.user_id),
            )

    def test_v11_rejects_orphan_chat_book(self):
        self._downgrade_ai_tables_to_v10(self.database)
        with sqlite3.connect(self.database) as connection:
            connection.execute(
                "INSERT INTO ai_book_chat_turns "
                "(id, book_id, chapter_index, context_mode, owner_user_id, question, status) "
                "VALUES ('orphan-turn', 'missing-book', 0, 'chapter_source', ?, 'Why?', 'queued')",
                (self.owner.user_id,),
            )

        with self.assertRaises(sqlite3.IntegrityError):
            StateStore(self.database).initialize()

        with sqlite3.connect(self.database) as connection:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 10)
            self.assertEqual(
                connection.execute(
                    "SELECT book_id FROM ai_book_chat_turns WHERE id='orphan-turn'"
                ).fetchone()[0],
                "missing-book",
            )

    def test_v11_rejects_duplicate_active_cache_keys(self):
        self._downgrade_ai_tables_to_v10(self.database)
        with sqlite3.connect(self.database) as connection:
            connection.executemany(
                "INSERT INTO ai_reading_jobs "
                "(id, owner_user_id, cache_key, request_json, status) VALUES (?, ?, 'same', '{}', ?)",
                (
                    ("queued-one", self.owner.user_id, "queued"),
                    ("queued-two", self.owner.user_id, "queued"),
                ),
            )

        with self.assertRaises(sqlite3.IntegrityError):
            StateStore(self.database).initialize()

        with sqlite3.connect(self.database) as connection:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 10)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM ai_reading_jobs").fetchone()[0], 2)

    def test_v11_rejects_leftover_migration_tables(self):
        with sqlite3.connect(self.database) as connection:
            connection.execute("CREATE TABLE annotations__v11_source (id TEXT)")
            connection.execute("PRAGMA user_version = 10")

        with self.assertRaises(sqlite3.IntegrityError):
            StateStore(self.database).initialize()

        with sqlite3.connect(self.database) as connection:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 10)
            self.assertIsNotNone(
                connection.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' "
                    "AND name='annotations__v11_source'"
                ).fetchone()
            )

    def test_v11_query_plans_use_final_indexes(self):
        with sqlite3.connect(self.database) as connection:
            connection.execute(
                "INSERT INTO books (book_id, source_path, source_fingerprint, metadata_json) "
                "VALUES ('plan-book', '/plan.epub', 'plan-fingerprint', '{}')"
            )
            connection.execute(
                "INSERT INTO ai_reading_results "
                "(id, cache_key, book_id, chapter_index, scope, mode, profile, language, "
                "config_revision, content_json, created_by_user_id) "
                "VALUES ('plan-result', 'plan-result-key', 'plan-book', 1, 'chapter', "
                "'chapter', 'general', 'en', 0, '{}', ?)",
                (self.owner.user_id,),
            )
            connection.executemany(
                "INSERT INTO ai_reading_jobs "
                "(id, owner_user_id, cache_key, request_json, status) VALUES (?, ?, ?, '{}', 'complete')",
                (
                    (f"complete-job-{number}", self.owner.user_id, f"complete-key-{number}")
                    for number in range(200)
                ),
            )
            connection.executemany(
                "INSERT INTO ai_reading_jobs "
                "(id, owner_user_id, cache_key, request_json, status) "
                "VALUES (?, ?, ?, NULL, 'queued')",
                (
                    (f"empty-job-{number}", self.owner.user_id, f"empty-key-{number}")
                    for number in range(200)
                ),
            )
            connection.execute(
                "INSERT INTO ai_reading_jobs "
                "(id, owner_user_id, cache_key, request_json, status) "
                "VALUES ('queued-job', ?, 'queued-key', '{}', 'queued')",
                (self.owner.user_id,),
            )
            connection.executemany(
                "INSERT INTO ai_reading_followups "
                "(id, result_id, owner_user_id, question, status) "
                "VALUES (?, 'plan-result', ?, 'Question?', 'complete')",
                ((f"complete-followup-{number}", self.owner.user_id) for number in range(200)),
            )
            connection.execute(
                "INSERT INTO ai_reading_followups "
                "(id, result_id, owner_user_id, question, status) "
                "VALUES ('queued-followup', 'plan-result', ?, 'Question?', 'queued')",
                (self.owner.user_id,),
            )
            connection.executemany(
                "INSERT INTO ai_book_chat_turns "
                "(id, book_id, chapter_index, context_mode, owner_user_id, question, status) "
                "VALUES (?, 'plan-book', 1, 'chapter_source', ?, 'Question?', 'complete')",
                ((f"complete-chat-{number}", self.owner.user_id) for number in range(200)),
            )
            connection.execute(
                "INSERT INTO ai_book_chat_turns "
                "(id, book_id, chapter_index, context_mode, owner_user_id, question, status) "
                "VALUES ('queued-chat', 'plan-book', 1, 'chapter_source', ?, 'Question?', 'queued')",
                (self.owner.user_id,),
            )
            connection.execute("ANALYZE")
            plans = {
                "jobs": connection.execute(
                    "EXPLAIN QUERY PLAN SELECT * FROM ai_reading_jobs "
                    "INDEXED BY idx_ai_jobs_queue "
                    "WHERE status = 'queued' AND request_json IS NOT NULL "
                    "ORDER BY created_at ASC, id ASC LIMIT 1"
                ).fetchall(),
                "followups": connection.execute(
                    "EXPLAIN QUERY PLAN SELECT * FROM ai_reading_followups "
                    "WHERE status = 'queued' "
                    "ORDER BY created_at ASC, id ASC LIMIT 1"
                ).fetchall(),
                "chat": connection.execute(
                    "EXPLAIN QUERY PLAN SELECT * FROM ai_book_chat_turns "
                    "WHERE status = 'queued' "
                    "ORDER BY created_at ASC, rowid ASC LIMIT 1"
                ).fetchall(),
                "annotations": connection.execute(
                    "EXPLAIN QUERY PLAN SELECT * FROM annotations "
                    "WHERE user_id=? AND book_hash=? AND chapter_index=? "
                    "ORDER BY created_at DESC, id",
                    (self.owner.user_id, "book", 1),
                ).fetchall(),
                "sessions": connection.execute(
                    "EXPLAIN QUERY PLAN SELECT * FROM sessions WHERE user_id=? "
                    "ORDER BY created_at DESC, session_id",
                    (self.owner.user_id,),
                ).fetchall(),
                "results": connection.execute(
                    "EXPLAIN QUERY PLAN SELECT * FROM ai_reading_results "
                    "WHERE book_id=? AND chapter_index=? AND language=? "
                    "ORDER BY created_at DESC, id DESC",
                    ("book", 1, "en"),
                ).fetchall(),
            }
        plan_details = {
            name: tuple(row[3] for row in rows) for name, rows in plans.items()
        }
        queue_indexes = {
            "jobs": ("idx_ai_jobs_queue",),
            "followups": ("idx_ai_followups_queue",),
            "chat": ("idx_ai_book_chat_queue",),
        }
        queue_tables = {
            "jobs": "ai_reading_jobs",
            "followups": "ai_reading_followups",
            "chat": "ai_book_chat_turns",
        }
        for name, expected_indexes in queue_indexes.items():
            details = plan_details[name]
            self.assertTrue(
                any(index in detail for index in expected_indexes for detail in details),
                details,
            )
            self.assertFalse(
                any(
                    detail.startswith(f"SCAN {queue_tables[name]}")
                    and "USING INDEX" not in detail
                    and "USING COVERING INDEX" not in detail
                    for detail in details
                ),
                details,
            )
            self.assertFalse(any("USE TEMP B-TREE" in detail for detail in details), details)
        details = {
            name: " ".join(rows) for name, rows in plan_details.items()
        }
        self.assertIn("idx_annotations_user_book_chapter_created", details["annotations"])
        self.assertIn("idx_sessions_user_created", details["sessions"])
        self.assertIn("idx_ai_results_chapter_language_created", details["results"])

    def test_initialize_rebuilds_historical_xpath_annotation_schema(self):
        historical = Path(self.temporary.name, "historical.db")
        with sqlite3.connect(historical) as connection:
            connection.execute(
                """
                CREATE TABLE annotations (
                    id TEXT PRIMARY KEY,
                    book_hash TEXT NOT NULL,
                    chapter_index INTEGER NOT NULL,
                    text TEXT NOT NULL,
                    note TEXT,
                    start_xpath TEXT NOT NULL,
                    end_xpath TEXT NOT NULL,
                    start_offset INTEGER NOT NULL,
                    end_offset INTEGER NOT NULL,
                    color TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                INSERT INTO annotations VALUES (
                    'legacy', 'book', 2, 'Saved text', 'note',
                    '/p[1]/text()[1]', '/p[1]/text()[1]', 3, 8,
                    '#ffee00', '2025-01-01', '2025-01-02'
                )
                """
            )

        store = StateStore(historical)
        admin = store.initialize(BootstrapCredentials("admin", "secret"))
        legacy = store.get_annotation("legacy", user_id=admin.user_id)

        self.assertEqual(
            legacy["startMeta"],
            {"legacyXPath": "/p[1]/text()[1]", "legacyOffset": 3},
        )
        self.assertEqual(
            legacy["endMeta"],
            {"legacyXPath": "/p[1]/text()[1]", "legacyOffset": 8},
        )
        with sqlite3.connect(historical) as connection:
            columns = {
                row[1]
                for row in connection.execute("PRAGMA table_info(annotations)")
            }
        self.assertIn("start_meta", columns)
        self.assertIn("end_meta", columns)
        self.assertNotIn("username", columns)
        self.assertNotIn("start_xpath", columns)

        store.upsert_annotation(
            {
                "id": "new",
                "book_hash": "book",
                "chapter_index": 2,
                "text": "New",
                "color": "#fff",
                "created_at": "2026",
                "updated_at": "2026",
                "startMeta": {"parentTagName": "P", "parentIndex": 0, "textOffset": 0},
                "endMeta": {"parentTagName": "P", "parentIndex": 0, "textOffset": 3},
            },
            user_id=admin.user_id,
        )
        self.assertEqual(
            store.get_annotation("new", user_id=admin.user_id)["text"],
            "New",
        )

    def test_last_enabled_administrator_is_protected_in_the_store(self):
        with self.assertRaisesRegex(RuntimeError, "last enabled administrator"):
            self.store.set_user_enabled(self.owner.user_id, False)
        with self.assertRaisesRegex(RuntimeError, "last enabled administrator"):
            self.store.update_user(self.owner.user_id, role="member")

        self.assertTrue(self.store.get_user_by_username("owner").enabled)
        self.assertEqual(self.store.get_user_by_username("owner").role, "admin")

    def test_disabling_an_account_and_revoking_its_sessions_are_atomic(self):
        member = self.store.create_user("member", "old-hash")
        self.store.create_session("a" * 64, member.user_id, 200, now=100)
        with sqlite3.connect(self.database) as connection:
            connection.execute(
                """
                CREATE TRIGGER block_disable_session_revoke
                BEFORE UPDATE OF revoked_at ON sessions
                BEGIN
                    SELECT RAISE(ABORT, 'blocked');
                END
                """
            )

        with self.assertRaises(sqlite3.IntegrityError):
            self.store.set_user_enabled(member.user_id, False)

        self.assertTrue(self.store.get_user_by_username("member").enabled)
        with sqlite3.connect(self.database) as connection:
            self.assertIsNone(
                connection.execute(
                    "SELECT revoked_at FROM sessions WHERE user_id = ?",
                    (member.user_id,),
                ).fetchone()[0]
            )

    def test_password_reset_and_session_revocation_are_atomic(self):
        member = self.store.create_user("member", "old-hash")
        self.store.create_session("b" * 64, member.user_id, 200, now=100)
        with sqlite3.connect(self.database) as connection:
            connection.execute(
                """
                CREATE TRIGGER block_password_session_revoke
                BEFORE UPDATE OF revoked_at ON sessions
                BEGIN
                    SELECT RAISE(ABORT, 'blocked');
                END
                """
            )

        with self.assertRaises(sqlite3.IntegrityError):
            self.store.set_password_hash_and_revoke_sessions(
                member.user_id,
                "new-hash",
            )

        self.assertEqual(
            self.store.get_user_by_username("member").password_hash,
            "old-hash",
        )
        with sqlite3.connect(self.database) as connection:
            self.assertIsNone(
                connection.execute(
                    "SELECT revoked_at FROM sessions WHERE user_id = ?",
                    (member.user_id,),
                ).fetchone()[0]
            )

    def test_store_lists_and_revokes_only_sessions_owned_by_the_user(self):
        member = self.store.create_user("member", "hash")
        owner_session = self.store.create_session(
            "c" * 64,
            self.owner.user_id,
            200,
            now=100,
        )
        member_session = self.store.create_session(
            "d" * 64,
            member.user_id,
            200,
            now=100,
            client_address="192.0.2.10",
            user_agent="Example Browser",
        )

        member_records = self.store.list_sessions(member.user_id)
        self.assertEqual(
            {session.session_id for session in member_records},
            {member_session},
        )
        self.assertEqual(member_records[0].client_address, "192.0.2.10")
        self.assertEqual(member_records[0].user_agent, "Example Browser")
        self.assertFalse(
            self.store.revoke_user_session(member.user_id, owner_session)
        )
        self.assertTrue(
            self.store.revoke_user_session(member.user_id, member_session)
        )

    def test_v11_owned_state_and_session_helpers_preserve_rows(self):
        shelf_payload = json.dumps(
            {"books": ["book-a", "book-b"], "layout": "ordered"}
        )
        self.store.upsert_annotation(
            {
                "id": "annotation-id",
                "book_hash": "book-id",
                "chapter_index": 9,
                "text": "Selected text",
                "note": "A preserved note",
                "color": "#f3c",
                "created_at": "2026-08-23T00:00:00Z",
                "updated_at": "2026-08-23T00:00:00Z",
                "startMeta": {"parentTagName": "P", "textOffset": 4},
                "endMeta": {"parentTagName": "P", "textOffset": 17},
            },
            user_id=self.owner.user_id,
        )
        self.store.create_bookshelf(self.owner.user_id, 7, shelf_payload)
        self.store.set_reading_progress(self.owner.user_id, "book-id", 9)
        live_session_id = self.store.create_session(
            "a" * 64,
            self.owner.user_id,
            200,
            now=100,
            client_address="192.0.2.10",
            user_agent="Live Browser",
        )
        revoked_session_id = self.store.create_session(
            "b" * 64,
            self.owner.user_id,
            300,
            now=110,
            client_address="2001:db8::1",
            user_agent="Revoked Browser",
        )
        self._downgrade_selected_tables_to_v10(self.database)
        with sqlite3.connect(self.database) as connection:
            connection.execute(
                "UPDATE bookshelves SET updated_at = '2026-08-23T01:02:03Z'"
            )
            connection.execute(
                "UPDATE reading_progress SET updated_at = '2026-08-23T04:05:06Z'"
            )
            connection.execute(
                "UPDATE sessions SET expires_at = '200.5', last_used_at = '125.25', "
                "created_at = '100.125' WHERE session_id = ?",
                (live_session_id,),
            )
            connection.execute(
                "UPDATE sessions SET expires_at = '300.5', last_used_at = '150.25', "
                "revoked_at = '175.75', created_at = '110.125' "
                "WHERE session_id = ?",
                (revoked_session_id,),
            )

        with sqlite3.connect(self.database) as connection:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("BEGIN")
            self.store._v11_rebuild_owned_state(connection)
            self.store._v11_rebuild_sessions(connection)
            connection.execute("COMMIT")

            self.assertNotIn(
                "username",
                {row[1] for row in connection.execute("PRAGMA table_info(annotations)")},
            )
            self.assertNotIn(
                "username",
                {row[1] for row in connection.execute("PRAGMA table_info(bookshelves)")},
            )
            self.assertNotIn(
                "username",
                {
                    row[1]
                    for row in connection.execute("PRAGMA table_info(reading_progress)")
                },
            )
            sessions = {
                row[0]: row[1:]
                for row in connection.execute(
                    "SELECT session_id, token_digest, expires_at, last_used_at, "
                    "revoked_at, created_at, client_address, user_agent, "
                    "typeof(expires_at), typeof(last_used_at), typeof(revoked_at), "
                    "typeof(created_at) FROM sessions"
                )
            }
            self.assertEqual(
                sessions[live_session_id],
                (
                    "a" * 64,
                    200.5,
                    125.25,
                    None,
                    100.125,
                    "192.0.2.10",
                    "Live Browser",
                    "real",
                    "real",
                    "null",
                    "real",
                ),
            )
            self.assertEqual(
                sessions[revoked_session_id],
                (
                    "b" * 64,
                    300.5,
                    150.25,
                    175.75,
                    110.125,
                    "2001:db8::1",
                    "Revoked Browser",
                    "real",
                    "real",
                    "real",
                    "real",
                ),
            )

        annotation = self.store.get_annotation(
            "annotation-id", user_id=self.owner.user_id
        )
        self.assertEqual(annotation["color"], "#f3c")
        self.assertEqual(annotation["note"], "A preserved note")
        self.assertEqual(annotation["startMeta"]["textOffset"], 4)
        self.assertEqual(annotation["endMeta"]["textOffset"], 17)
        self.assertEqual(annotation["created_at"], "2026-08-23T00:00:00Z")
        self.assertEqual(annotation["updated_at"], "2026-08-23T00:00:00Z")
        self.assertEqual(self.store.get_bookshelf(self.owner.user_id), (7, shelf_payload))
        self.assertEqual(
            self.store.get_reading_progress(self.owner.user_id, "book-id"), 9
        )
        with sqlite3.connect(self.database) as connection:
            self.assertEqual(
                connection.execute("SELECT updated_at FROM bookshelves").fetchone()[0],
                "2026-08-23T01:02:03Z",
            )
            self.assertEqual(
                connection.execute("SELECT updated_at FROM reading_progress").fetchone()[0],
                "2026-08-23T04:05:06Z",
            )
        self.assertEqual(
            {
                session.session_id: session
                for session in self.store.list_sessions(self.owner.user_id)
            }[live_session_id].expires_at,
            200.5,
        )

    def test_v11_owned_state_factory_preserves_legacy_nullable_color_and_contract(self):
        self.store.upsert_annotation(
            {
                "id": "annotation-id",
                "book_hash": "book-id",
                "chapter_index": 9,
                "text": "Selected text",
                "color": "#f3c",
                "created_at": "2026-08-23T00:00:00Z",
                "updated_at": "2026-08-23T00:00:00Z",
            },
            user_id=self.owner.user_id,
        )
        self._downgrade_selected_tables_to_v10(self.database)
        with sqlite3.connect(self.database) as connection:
            connection.execute("UPDATE annotations SET color = NULL")
            connection.commit()
            connection.execute("BEGIN")
            self.store._v11_rebuild_owned_state(connection)
            connection.execute("COMMIT")

            annotation_columns = {
                row[1]: row for row in connection.execute("PRAGMA table_info(annotations)")
            }
            bookshelf_columns = {
                row[1]: row for row in connection.execute("PRAGMA table_info(bookshelves)")
            }
            self.assertEqual(annotation_columns["color"][3], 0)
            self.assertEqual(bookshelf_columns["user_id"][3], 0)
            self.assertNotIn(
                "CHECK(length(user_id)",
                connection.execute(
                    "SELECT sql FROM sqlite_master WHERE type = 'table' "
                    "AND name = 'annotations'"
                ).fetchone()[0],
            )
            self.assertNotIn(
                "CHECK(length(user_id)",
                connection.execute(
                    "SELECT sql FROM sqlite_master WHERE type = 'table' "
                    "AND name = 'bookshelves'"
                ).fetchone()[0],
            )
            self.assertNotIn(
                "CHECK(length(user_id)",
                connection.execute(
                    "SELECT sql FROM sqlite_master WHERE type = 'table' "
                    "AND name = 'reading_progress'"
                ).fetchone()[0],
            )
            self.assertIsNone(
                connection.execute(
                    "SELECT color FROM annotations WHERE id = 'annotation-id'"
                ).fetchone()[0]
            )

    def test_v11_rebuild_helpers_roll_back_with_the_caller(self):
        self.store.upsert_annotation(
            {
                "id": "annotation-id",
                "book_hash": "book-id",
                "chapter_index": 9,
                "text": "Selected text",
                "color": "#f3c",
                "created_at": "2026-08-23T00:00:00Z",
                "updated_at": "2026-08-23T00:00:00Z",
            },
            user_id=self.owner.user_id,
        )
        self.store.create_bookshelf(self.owner.user_id, 7, "{}")
        self.store.set_reading_progress(self.owner.user_id, "book-id", 9)
        self.store.create_session("a" * 64, self.owner.user_id, 200, now=100)
        self._downgrade_selected_tables_to_v10(self.database)
        before = self._selected_table_snapshot()

        connection = sqlite3.connect(self.database)
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("BEGIN")
            with self.assertRaisesRegex(sqlite3.Error, "stop-v11"):
                self.store._v11_rebuild_owned_state(connection)
                self.store._v11_rebuild_sessions(connection)
                raise sqlite3.Error("stop-v11")
            connection.execute("ROLLBACK")
        finally:
            connection.close()

        self.assertEqual(self._selected_table_snapshot(), before)

    def test_v11_session_rebuild_rejects_invalid_or_non_finite_epochs(self):
        session_id = self.store.create_session(
            "a" * 64, self.owner.user_id, 200, now=100
        )
        self._downgrade_selected_tables_to_v10(self.database)

        for column, epoch in (
            ("expires_at", "not-an-epoch"),
            ("last_used_at", "NaN"),
            ("revoked_at", "-Infinity"),
            ("created_at", "1e999"),
        ):
            with self.subTest(column=column, epoch=epoch):
                with sqlite3.connect(self.database) as connection:
                    connection.execute(
                        "UPDATE sessions SET expires_at = '200', last_used_at = '100', "
                        "revoked_at = NULL, created_at = '100' WHERE session_id = ?",
                        (session_id,),
                    )
                    connection.execute(
                        f"UPDATE sessions SET {column} = ? WHERE session_id = ?",
                        (epoch, session_id),
                    )
                before = self._selected_table_snapshot()

                connection = sqlite3.connect(self.database)
                try:
                    connection.execute("BEGIN")
                    with self.assertRaisesRegex(sqlite3.IntegrityError, column):
                        self.store._v11_rebuild_sessions(connection)
                    connection.execute("ROLLBACK")
                finally:
                    connection.close()

                self.assertEqual(self._selected_table_snapshot(), before)

    def test_session_replacement_rolls_back_if_new_token_cannot_be_inserted(self):
        raw_current = "current-session-token"
        current_digest = token_digest(raw_current)
        duplicate_digest = "f" * 64
        self.store.create_session(
            current_digest,
            self.owner.user_id,
            200,
            now=100,
        )
        self.store.create_session(
            duplicate_digest,
            self.owner.user_id,
            200,
            now=100,
        )

        with self.assertRaises(sqlite3.IntegrityError):
            self.store.replace_session(
                raw_current,
                duplicate_digest,
                self.owner.user_id,
                300,
                now=100,
            )

        self.assertEqual(
            self.store.principal_from_session(raw_current, now=100),
            self.owner,
        )

    def test_second_enabled_admin_allows_first_to_be_disabled_and_revokes_sessions(self):
        self.store.create_user("second-admin", "hash", role="admin")
        self.store.create_session("e" * 64, self.owner.user_id, 200, now=100)

        disabled = self.store.set_user_enabled(self.owner.user_id, False)

        self.assertFalse(disabled.enabled)
        with sqlite3.connect(self.database) as connection:
            self.assertIsNotNone(
                connection.execute(
                    "SELECT revoked_at FROM sessions WHERE user_id = ?",
                    (self.owner.user_id,),
                ).fetchone()[0]
            )

    def test_ai_administration_defaults_to_disabled_members_and_keeps_keys_private(self):
        member = self.store.create_user("reader", "hash", role="member")

        settings = self.store.get_ai_settings()

        self.assertEqual(
            settings,
            {
                "enabled": False,
                "base_url": "",
                "model": "",
                "timeout_seconds": 60,
                "model_context_window": 32768,
                "max_concurrency": 2,
                "daily_limit": 20,
                "config_revision": 0,
                "api_key_configured": False,
            },
        )
        self.assertTrue(self.store.can_use_ai(self.owner))
        self.assertFalse(self.store.can_use_ai(member))

        self.store.set_ai_settings(
            enabled=True,
            base_url="https://provider.example/v1",
            api_key="secret-key",
            model="reader-model",
            timeout_seconds=45,
            max_concurrency=3,
            daily_limit=30,
        )
        self.store.set_ai_user_access(member.user_id, enabled=True, daily_limit=5)

        public = self.store.get_ai_settings()
        self.assertTrue(public["enabled"])
        self.assertTrue(public["api_key_configured"])
        self.assertNotIn("api_key", public)
        self.assertEqual(public["config_revision"], 1)
        self.assertTrue(self.store.can_use_ai(member))
        self.assertEqual(self.store.ai_daily_limit(member), 5)

    def test_administrator_tags_merge_with_epub_tags_and_ai_profile_is_independent(self):
        book = self.store.resolve_book(
            Path(self.temporary.name, "book.epub"),
            "urn:test:tags",
            "fingerprint",
            {"title": "Book", "tags": ["History", "DDD"]},
        )

        tag = self.store.create_ai_tag(" history ")
        custom = self.store.create_ai_tag("Domain driven design")
        self.store.replace_book_ai_tags(book.book_id, [tag["id"], custom["id"]])
        self.store.set_book_ai_profile(book.book_id, "fiction")

        self.assertEqual(
            self.store.effective_book_tags(book.book_id),
            ("DDD", "Domain driven design", "History"),
        )
        self.assertEqual(
            tuple(item["name"] for item in self.store.book_ai_tags(book.book_id)),
            ("Domain driven design", "history"),
        )
        self.assertEqual(self.store.get_book_ai_profile(book.book_id), "fiction")
        self.store.delete_ai_tag(tag["id"])
        self.assertEqual(
            self.store.effective_book_tags(book.book_id),
            ("DDD", "Domain driven design", "History"),
        )

    def test_ai_usage_is_atomic_and_incomplete_jobs_are_marked_interrupted(self):
        member = self.store.create_user("reader", "hash", role="member")
        self.store.set_ai_user_access(member.user_id, enabled=True, daily_limit=2)

        self.assertTrue(self.store.reserve_ai_usage(member, "2026-08-21"))
        self.assertTrue(self.store.reserve_ai_usage(member, "2026-08-21"))
        self.assertFalse(self.store.reserve_ai_usage(member, "2026-08-21"))
        self.assertTrue(self.store.reserve_ai_usage(member, "2026-08-22"))

        self.store.create_ai_job("job-running", member.user_id, "cache-key")
        self.store.start_ai_job("job-running")
        self.store.mark_incomplete_ai_jobs_interrupted()

        self.assertEqual(
            self.store.get_ai_job("job-running", member.user_id)["status"],
            "interrupted",
        )

    def test_ai_generation_jobs_single_flight_by_cache_key(self):
        book = self.store.resolve_book(
            Path(self.temporary.name, "single-flight.epub"),
            "urn:test:single-flight", "fingerprint", {"title": "Book"},
        )
        first, created_first = self.store.create_or_get_active_ai_job(
            "job-first", self.owner.user_id, book.book_id, "same-request", progress_total=3,
        )
        second, created_second = self.store.create_or_get_active_ai_job(
            "job-second", self.owner.user_id, book.book_id, "same-request", progress_total=3,
        )

        self.assertTrue(created_first)
        self.assertFalse(created_second)
        self.assertEqual(first["id"], "job-first")
        self.assertEqual(second["id"], "job-first")
        self.assertEqual(second["book_id"], book.book_id)

    def test_admin_ai_job_pagination_is_safe_and_stable(self):
        member = self.store.create_user("reader", "hash", role="member")
        book = self.store.resolve_book(
            Path(self.temporary.name, "admin-job-book.epub"),
            "urn:test:admin-job-book", "fingerprint", {"title": "Admin Job Book"},
        )
        replay = {
            "book_id": book.book_id,
            "scope": "chapter",
            "mode": "chapter",
            "language": "zh-CN",
            "chapter_index": 4,
            "reading_boundary": 4,
            "private_note": "PRIVATE_REPLAY_SENTINEL",
        }
        for index in range(25):
            job_id = f"admin-page-{index:02d}"
            self.store.create_ai_job(
                job_id,
                member.user_id,
                f"admin-page-cache-{index}",
                book_id=book.book_id,
                request_payload=replay,
                profile="general",
                template_id="reading",
                template_version=1,
            )
            self.assertTrue(self.store.start_ai_job(job_id))
            if index % 2 == 0:
                self.assertTrue(self.store.finish_ai_job(job_id, error_code="provider_failed"))
            else:
                self.assertTrue(self.store.finish_ai_job(job_id))
            with self.store._connection() as connection:
                connection.execute(
                    "UPDATE ai_reading_jobs SET created_at = ? WHERE id = ?",
                    (f"2026-08-23 00:00:{index:02d}", job_id),
                )

        jobs, total = self.store.list_admin_ai_jobs(
            status="failed", page=2, page_size=5
        )

        self.assertEqual(total, 13)
        self.assertEqual(len(jobs), 5)
        self.assertEqual(
            [job["created_at"] for job in jobs],
            sorted((job["created_at"] for job in jobs), reverse=True),
        )
        self.assertTrue(all(job["status"] == "failed" for job in jobs))
        self.assertTrue(all("request_json" not in job for job in jobs))
        self.assertTrue(all("metadata_json" not in job for job in jobs))
        self.assertTrue(all("cache_key" not in job for job in jobs))
        self.assertEqual(jobs[0]["book_title"], "Admin Job Book")
        self.assertEqual(jobs[0]["owner_username"], "reader")
        self.assertEqual(
            {
                key: jobs[0][key]
                for key in ("scope", "mode", "language", "chapter_index", "reading_boundary")
            },
            {
                "scope": "chapter",
                "mode": "chapter",
                "language": "zh-CN",
                "chapter_index": 4,
                "reading_boundary": 4,
            },
        )
        self.assertNotIn("private_note", jobs[0])
        self.assertTrue(jobs[0]["retryable"])

    def test_admin_retry_creates_one_linked_active_attempt(self):
        member = self.store.create_user("reader", "hash", role="member")
        book = self.store.resolve_book(
            Path(self.temporary.name, "retry-book.epub"),
            "urn:test:retry-book", "fingerprint", {"title": "Retry Book"},
        )
        request = {
            "book_id": book.book_id,
            "scope": "chapter",
            "mode": "chapter",
            "language": "en",
            "chapter_index": 2,
            "reading_boundary": 2,
        }
        self.store.create_ai_job(
            "failed-source", member.user_id, "failed-cache", book_id=book.book_id,
            request_payload=request, profile="general", template_id="reading",
            template_version=1, progress_total=3,
        )
        self.assertTrue(self.store.start_ai_job("failed-source"))
        self.assertTrue(
            self.store.finish_ai_job("failed-source", error_code="provider_failed")
        )

        first, created_first = self.store.create_or_get_admin_retry_ai_job(
            source_job_id="failed-source", job_id="retry-attempt-2",
            retried_by_user_id=self.owner.user_id, owner_user_id=member.user_id,
            book_id=book.book_id, cache_key="recomputed-cache", request_payload=request,
            progress_total=4, profile="technical", template_id="current-template",
            template_version=2,
        )
        second, created_second = self.store.create_or_get_admin_retry_ai_job(
            source_job_id="failed-source", job_id="ignored-retry-id",
            retried_by_user_id=self.owner.user_id, owner_user_id=member.user_id,
            book_id=book.book_id, cache_key="recomputed-cache", request_payload=request,
            progress_total=4, profile="technical", template_id="current-template",
            template_version=2,
        )

        self.assertTrue(created_first)
        self.assertFalse(created_second)
        self.assertEqual(first["id"], "retry-attempt-2")
        self.assertEqual(second["id"], "retry-attempt-2")
        self.assertNotIn("request_json", first)
        self.assertEqual(
            {
                key: first[key]
                for key in (
                    "attempt_number", "retried_from_job_id", "retry_root_job_id",
                    "retried_by_user_id", "owner_user_id",
                )
            },
            {
                "attempt_number": 2,
                "retried_from_job_id": "failed-source",
                "retry_root_job_id": "failed-source",
                "retried_by_user_id": self.owner.user_id,
                "owner_user_id": member.user_id,
            },
        )
        self.assertEqual(
            self.store.get_ai_job_for_retry("failed-source")["status"], "failed"
        )
        self.assertIn(
            "request_json", self.store.get_ai_job_for_retry("failed-source")
        )

    def test_admin_retry_attempt_numbers_follow_the_root_lineage(self):
        member = self.store.create_user("reader", "hash", role="member")
        book = self.store.resolve_book(
            Path(self.temporary.name, "retry-lineage.epub"),
            "urn:test:retry-lineage", "fingerprint", {"title": "Retry Book"},
        )
        request = {
            "book_id": book.book_id,
            "scope": "chapter",
            "mode": "chapter",
            "language": "en",
            "chapter_index": 2,
            "reading_boundary": 2,
        }
        self.store.create_ai_job(
            "lineage-source", member.user_id, "lineage-source-cache",
            book_id=book.book_id, request_payload=request, progress_total=2,
        )
        self.assertTrue(self.store.start_ai_job("lineage-source"))
        self.assertTrue(
            self.store.finish_ai_job("lineage-source", error_code="provider_failed")
        )
        attempt_two, created_two = self.store.create_or_get_admin_retry_ai_job(
            source_job_id="lineage-source", job_id="lineage-attempt-2",
            retried_by_user_id=self.owner.user_id, owner_user_id=member.user_id,
            book_id=book.book_id, cache_key="lineage-cache-2", request_payload=request,
            progress_total=2, profile="general", template_id="reading",
            template_version=1,
        )
        self.assertTrue(created_two)
        self.assertTrue(self.store.start_ai_job(attempt_two["id"]))
        self.assertTrue(
            self.store.finish_ai_job(attempt_two["id"], error_code="provider_failed")
        )

        attempt_three, created_three = self.store.create_or_get_admin_retry_ai_job(
            source_job_id=attempt_two["id"], job_id="lineage-attempt-3",
            retried_by_user_id=self.owner.user_id, owner_user_id=member.user_id,
            book_id=book.book_id, cache_key="lineage-cache-3", request_payload=request,
            progress_total=2, profile="general", template_id="reading",
            template_version=1,
        )

        self.assertTrue(created_three)
        self.assertEqual(attempt_three["attempt_number"], 3)
        self.assertEqual(attempt_three["retried_from_job_id"], "lineage-attempt-2")
        self.assertEqual(attempt_three["retry_root_job_id"], "lineage-source")

    def test_admin_retry_rejects_nonterminal_unknown_and_malformed_sources(self):
        member = self.store.create_user("reader", "hash", role="member")
        book = self.store.resolve_book(
            Path(self.temporary.name, "retry-validation.epub"),
            "urn:test:retry-validation", "fingerprint", {"title": "Retry Book"},
        )
        request = {
            "book_id": book.book_id,
            "scope": "chapter",
            "mode": "chapter",
            "language": "en",
            "chapter_index": 2,
            "reading_boundary": 2,
        }

        def retry(source_job_id):
            return self.store.create_or_get_admin_retry_ai_job(
                source_job_id=source_job_id, job_id=f"retry-{source_job_id}",
                retried_by_user_id=self.owner.user_id, owner_user_id=member.user_id,
                book_id=book.book_id, cache_key=f"retry-cache-{source_job_id}",
                request_payload=request, progress_total=2, profile="general",
                template_id="reading", template_version=1,
            )

        self.store.create_ai_job(
            "queued-source", member.user_id, "queued-cache", book_id=book.book_id,
            request_payload=request,
        )
        self.store.create_ai_job(
            "running-source", member.user_id, "running-cache", book_id=book.book_id,
            request_payload=request,
        )
        self.assertTrue(self.store.start_ai_job("running-source"))
        self.store.create_ai_job(
            "complete-source", member.user_id, "complete-cache", book_id=book.book_id,
            request_payload=request,
        )
        self.assertTrue(self.store.start_ai_job("complete-source"))
        self.assertTrue(self.store.finish_ai_job("complete-source"))
        self.store.create_ai_job(
            "malformed-source", member.user_id, "malformed-cache", book_id=book.book_id,
        )
        self.assertTrue(self.store.start_ai_job("malformed-source"))
        self.assertTrue(
            self.store.finish_ai_job("malformed-source", error_code="provider_failed")
        )

        for source_job_id in (
            "queued-source", "running-source", "complete-source", "malformed-source",
        ):
            with self.subTest(source_job_id=source_job_id):
                with self.assertRaises(ValueError):
                    retry(source_job_id)
        with self.assertRaises(KeyError):
            retry("unknown-source")

    def test_running_private_followup_is_requeued_with_its_language(self):
        member = self.store.create_user("reader", "hash", role="member")
        book = self.store.resolve_book(
            Path(self.temporary.name, "followup.epub"),
            "urn:test:followup", "fingerprint", {"title": "Book"},
        )
        result = self.store.store_ai_reading_result(
            cache_key="followup-cache", book_id=book.book_id, chapter_index=0,
            scope="chapter", mode="chapter", profile="general", config_revision=1,
            content={"quick": {"summary": "Summary"}}, created_by_user_id=self.owner.user_id,
        )
        followup = self.store.create_ai_followup(
            result_id=result["id"], owner_user_id=member.user_id,
            question="What matters?", language="zh-CN",
        )
        self.assertTrue(self.store.start_ai_followup(followup["id"], member.user_id))
        self.assertEqual(self.store.requeue_running_ai_followups(), 1)
        claimed = self.store.claim_next_ai_followup()

        self.assertEqual(claimed["id"], followup["id"])
        self.assertEqual(claimed["language"], "zh-CN")

    def test_book_chat_is_private_ordered_and_keeps_the_generated_chapter(self):
        member = self.store.create_user("book-chat-reader", "hash", role="member")
        book = self.store.resolve_book(
            Path(self.temporary.name, "book-chat.epub"),
            "urn:test:book-chat", "fingerprint", {"title": "Book"},
        )
        first = self.store.create_ai_book_chat_turn(
            book_id=book.book_id, chapter_index=7, owner_user_id=member.user_id,
            question="What changed here?", language="en", context_mode="chapter_source",
        )
        second = self.store.create_ai_book_chat_turn(
            book_id=book.book_id, chapter_index=9, owner_user_id=member.user_id,
            question="How does this connect?", language="zh-CN", context_mode="chapter_source",
        )
        claimed = self.store.claim_next_ai_book_chat_turn()
        self.assertIn(claimed["id"], {first["id"], second["id"]})
        self.assertTrue(self.store.finish_ai_book_chat_turn(claimed["id"], member.user_id, answer="It changes."))
        self.assertEqual(
            {item["chapter_index"] for item in self.store.list_ai_book_chat_turns(book.book_id, member.user_id)},
            {7, 9},
        )
        self.assertEqual(self.store.list_ai_book_chat_turns(book.book_id, self.owner.user_id), ())
        next_turn = self.store.claim_next_ai_book_chat_turn()
        self.assertNotEqual(next_turn["id"], claimed["id"])
        self.assertEqual(self.store.requeue_running_ai_book_chat_turns(), 1)
        self.assertEqual(self.store.claim_next_ai_book_chat_turn()["language"], "zh-CN")

    def test_ai_settings_keep_an_existing_key_until_an_admin_clears_it(self):
        self.store.set_ai_settings(
            enabled=True,
            base_url="https://provider.example/v1",
            api_key="secret-key",
            model="reader-model",
            timeout_seconds=60,
            max_concurrency=2,
            daily_limit=20,
        )
        self.store.set_ai_settings(
            enabled=False,
            base_url="",
            api_key=None,
            model="",
            timeout_seconds=60,
            max_concurrency=2,
            daily_limit=20,
        )
        self.assertTrue(self.store.get_ai_settings()["api_key_configured"])
        self.store.set_ai_settings(
            enabled=False,
            base_url="",
            api_key=None,
            model="",
            timeout_seconds=60,
            max_concurrency=2,
            daily_limit=20,
            clear_api_key=True,
        )
        self.assertFalse(self.store.get_ai_settings()["api_key_configured"])
        with self.assertRaisesRegex(ValueError, "required when enabled"):
            self.store.set_ai_settings(
                enabled=True,
                base_url="https://provider.example/v1",
                api_key=None,
                model="reader-model",
                timeout_seconds=60,
                max_concurrency=2,
                daily_limit=20,
            )

    def test_ai_timeout_allows_a_one_hour_provider_request(self):
        self.store.set_ai_settings(
            enabled=True,
            base_url="https://provider.example/v1",
            api_key="secret-key",
            model="reader-model",
            timeout_seconds=3600,
            max_concurrency=2,
            daily_limit=20,
        )

        self.assertEqual(self.store.get_ai_settings()["timeout_seconds"], 3600)
        with self.assertRaisesRegex(ValueError, "timeout"):
            self.store.set_ai_settings(
                enabled=False,
                base_url="",
                api_key=None,
                model="",
                timeout_seconds=3601,
                max_concurrency=2,
                daily_limit=20,
            )

    def test_ai_timeout_constraint_migrates_an_existing_database(self):
        database = Path(self.temporary.name, "legacy-ai-settings.db")
        with sqlite3.connect(database) as connection:
            connection.executescript(
                """
                CREATE TABLE ai_settings (
                    singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
                    enabled INTEGER NOT NULL DEFAULT 0 CHECK(enabled IN (0, 1)),
                    base_url TEXT NOT NULL DEFAULT '',
                    api_key TEXT NOT NULL DEFAULT '',
                    model TEXT NOT NULL DEFAULT '',
                    timeout_seconds INTEGER NOT NULL DEFAULT 60
                        CHECK(timeout_seconds BETWEEN 5 AND 180),
                    max_concurrency INTEGER NOT NULL DEFAULT 2
                        CHECK(max_concurrency BETWEEN 1 AND 4),
                    daily_limit INTEGER NOT NULL DEFAULT 20 CHECK(daily_limit >= 0),
                    config_revision INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                INSERT INTO ai_settings (singleton, timeout_seconds) VALUES (1, 180);
                PRAGMA user_version = 6;
                """
            )

        migrated = StateStore(database)
        migrated.initialize(bootstrap=BootstrapCredentials("owner", "secret"))
        migrated.set_ai_settings(
            enabled=False, base_url="", api_key=None, model="", timeout_seconds=3600,
            max_concurrency=2, daily_limit=20,
        )

        self.assertEqual(migrated.get_ai_settings()["timeout_seconds"], 3600)

    def test_ai_results_keep_history_and_followups_are_private_to_owner(self):
        member = self.store.create_user("reader", "hash", role="member")
        book = self.store.resolve_book(
            Path(self.temporary.name, "book.epub"),
            "urn:test:results",
            "fingerprint",
            {"title": "Book"},
        )
        first = self.store.store_ai_reading_result(
            cache_key="book:1",
            book_id=book.book_id,
            chapter_index=None,
            scope="book",
            mode="read_so_far",
            profile="technical",
            config_revision=1,
            content={"quick": "First result"},
            created_by_user_id=self.owner.user_id,
        )
        second = self.store.store_ai_reading_result(
            cache_key="book:1",
            book_id=book.book_id,
            chapter_index=None,
            scope="book",
            mode="spoiler_free",
            profile="technical",
            config_revision=2,
            content={"quick": "Regenerated result"},
            created_by_user_id=self.owner.user_id,
            template_id="reading-layer",
            template_version=1,
            language="zh-CN",
            reading_boundary=4,
        )
        self.assertEqual(
            self.store.get_current_ai_reading_result("book:1")["id"], second["id"]
        )
        self.assertEqual(self.store.get_ai_reading_result(first["id"])["content"]["quick"], "First result")
        self.assertEqual(second["language"], "zh-CN")
        self.assertEqual(second["reading_boundary"], 4)
        self.assertEqual(second["template_id"], "reading-layer")
        self.assertEqual(second["template_version"], 1)

        followup = self.store.create_ai_followup(
            result_id=second["id"], owner_user_id=member.user_id, question="Why?"
        )
        self.assertTrue(self.store.start_ai_followup(followup["id"], member.user_id))
        self.assertTrue(
            self.store.finish_ai_followup(
                followup["id"], member.user_id, answer="Because of the evidence."
            )
        )
        self.assertEqual(len(self.store.list_ai_followups(second["id"], member.user_id)), 1)
        self.assertEqual(self.store.list_ai_followups(second["id"], self.owner.user_id), ())
        self.assertEqual(
            self.store.get_ai_followup(followup["id"], member.user_id)["question"],
            "Why?",
        )
        self.assertIsNone(self.store.get_ai_followup(followup["id"], self.owner.user_id))

    def _create_v1_database_with_annotation_bookshelf_and_progress(
        self,
        username,
    ):
        self.database.unlink()
        with sqlite3.connect(self.database) as connection:
            connection.execute("PRAGMA user_version = 1")
            connection.execute(
                """
                CREATE TABLE annotations (
                    id TEXT PRIMARY KEY,
                    username TEXT NOT NULL DEFAULT '',
                    book_hash TEXT NOT NULL,
                    chapter_index INTEGER NOT NULL,
                    text TEXT NOT NULL,
                    note TEXT,
                    start_meta TEXT,
                    end_meta TEXT,
                    color TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                INSERT INTO annotations (
                    id, username, book_hash, chapter_index, text, color,
                    created_at, updated_at
                ) VALUES (
                    'old', ?, 'book', 3, 'old note', '#fff',
                    '2025', '2025-01-01'
                )
                """,
                (username,),
            )
            connection.execute(
                """
                CREATE TABLE bookshelves (
                    username TEXT PRIMARY KEY,
                    version INTEGER NOT NULL,
                    data TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            connection.execute(
                """
                INSERT INTO bookshelves (username, version, data, updated_at)
                VALUES (?, 7, '{}', '2025-01-01')
                """,
                (username,),
            )
            connection.execute(
                """
                CREATE TABLE reading_progress (
                    username TEXT NOT NULL DEFAULT '',
                    book_hash TEXT NOT NULL,
                    chapter_index INTEGER NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (username, book_hash)
                )
                """
            )
            connection.execute(
                """
                INSERT INTO reading_progress (username, book_hash, chapter_index)
                VALUES (?, 'book', 3)
                """,
                (username,),
            )

    def _database_snapshot(self):
        with sqlite3.connect(self.database) as connection:
            return (
                connection.execute("PRAGMA user_version").fetchone()[0],
                tuple(connection.iterdump()),
            )

    def _downgrade_selected_tables_to_v10(self, database):
        with sqlite3.connect(database) as connection:
            connection.execute("PRAGMA foreign_keys = OFF")
            for index in (
                "idx_annotations_user_created",
                "idx_annotations_user_book_created",
                "idx_annotations_user_book_chapter_created",
                "idx_sessions_user_created",
            ):
                connection.execute(f"DROP INDEX IF EXISTS {index}")
            connection.executescript(
                """
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
                CREATE TABLE sessions_v10 (
                    session_id TEXT PRIMARY KEY,
                    token_digest TEXT NOT NULL UNIQUE,
                    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    expires_at TEXT NOT NULL,
                    last_used_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    revoked_at TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    client_address TEXT,
                    user_agent TEXT
                );
                """
            )
            connection.execute(
                "INSERT INTO annotations_v10 "
                "SELECT id, book_hash, chapter_index, text, note, start_meta, "
                "end_meta, color, created_at, updated_at, user_id, '' "
                "FROM annotations"
            )
            connection.execute(
                "INSERT INTO bookshelves_v10 "
                "SELECT user_id, '', version, data, updated_at FROM bookshelves"
            )
            connection.execute(
                "INSERT INTO reading_progress_v10 "
                "SELECT user_id, '', book_hash, chapter_index, updated_at "
                "FROM reading_progress"
            )
            connection.execute(
                "INSERT INTO sessions_v10 "
                "SELECT session_id, token_digest, user_id, expires_at, last_used_at, "
                "revoked_at, created_at, client_address, user_agent FROM sessions"
            )
            for table in (
                "annotations",
                "bookshelves",
                "reading_progress",
                "sessions",
            ):
                connection.execute(f"DROP TABLE {table}")
                connection.execute(f"ALTER TABLE {table}_v10 RENAME TO {table}")
            connection.execute("PRAGMA user_version = 10")

    def _downgrade_ai_tables_to_v10(self, database):
        with sqlite3.connect(database) as connection:
            connection.execute("PRAGMA foreign_keys = OFF")
            connection.executescript(
                """
                DROP TABLE ai_reading_jobs;
                DROP TABLE ai_book_chat_turns;
                DROP TABLE ai_book_chat_summaries;
                CREATE TABLE ai_reading_jobs (
                    id TEXT PRIMARY KEY,
                    owner_user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    book_id TEXT REFERENCES books(book_id) ON DELETE CASCADE,
                    cache_key TEXT NOT NULL,
                    request_json TEXT,
                    profile TEXT,
                    template_id TEXT,
                    template_version INTEGER,
                    status TEXT NOT NULL CHECK(status IN (
                        'queued', 'running', 'complete', 'failed', 'interrupted'
                    )),
                    error_code TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    result_id TEXT,
                    progress_current INTEGER NOT NULL DEFAULT 0
                        CHECK(progress_current >= 0),
                    progress_total INTEGER NOT NULL DEFAULT 1
                        CHECK(progress_total >= 1)
                );
                CREATE TABLE ai_book_chat_turns (
                    id TEXT PRIMARY KEY,
                    book_id TEXT NOT NULL,
                    chapter_index INTEGER NOT NULL CHECK(chapter_index >= 0),
                    result_id TEXT REFERENCES ai_reading_results(id) ON DELETE SET NULL,
                    context_mode TEXT NOT NULL CHECK(context_mode IN (
                        'shared_layer', 'chapter_source'
                    )),
                    book_context INTEGER NOT NULL DEFAULT 0 CHECK(book_context IN (0, 1)),
                    owner_user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    question TEXT NOT NULL,
                    language TEXT NOT NULL DEFAULT 'en' CHECK(language IN ('en', 'zh-CN')),
                    answer TEXT,
                    status TEXT NOT NULL CHECK(status IN (
                        'queued', 'running', 'complete', 'failed', 'interrupted'
                    )),
                    error_code TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE ai_book_chat_summaries (
                    book_id TEXT NOT NULL,
                    owner_user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    language TEXT NOT NULL CHECK(language IN ('en', 'zh-CN')),
                    covered_turn_count INTEGER NOT NULL DEFAULT 0
                        CHECK(covered_turn_count >= 0),
                    summary_text TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (book_id, owner_user_id, language)
                );
                PRAGMA user_version = 10;
                """
            )

    def _selected_table_snapshot(self):
        tables = ("annotations", "bookshelves", "reading_progress", "sessions")
        with sqlite3.connect(self.database) as connection:
            return tuple(
                (
                    table,
                    connection.execute(
                        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?",
                        (table,),
                    ).fetchone()[0],
                    tuple(connection.execute(f"SELECT * FROM {table}").fetchall()),
                )
                for table in tables
            )


if __name__ == "__main__":
    unittest.main()
