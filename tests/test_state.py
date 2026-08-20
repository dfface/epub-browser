import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from epub_browser.auth import BootstrapCredentials, hash_password, token_digest
from epub_browser.state import DB_SCHEMA_VERSION, StateStore


class StateStoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.database = Path(self.temporary.name, "data", "epub-browser.db")
        self.store = StateStore(self.database)
        self.owner = self.store.initialize(
            bootstrap=BootstrapCredentials("owner", "secret")
        )

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
            self.assertEqual(
                connection.execute(
                    "SELECT username FROM bookshelves WHERE user_id = ?",
                    (admin.user_id,),
                ).fetchone()[0],
                "alpha",
            )

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
            self.assertEqual(
                connection.execute(
                    """
                    SELECT username FROM reading_progress
                    WHERE user_id = ? AND book_hash = 'book'
                    """,
                    (admin.user_id,),
                ).fetchone()[0],
                "alpha",
            )

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
        self.assertIn("username", columns)
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


if __name__ == "__main__":
    unittest.main()
