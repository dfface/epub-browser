import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from epub_browser.auth import BootstrapCredentials
from epub_browser.state import DB_SCHEMA_VERSION, StateStore


class StateStoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.database = Path(self.temporary.name, "data", "epub-browser.db")
        self.store = StateStore(self.database)
        self.store.initialize()

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
        with mock.patch.object(
            StateStore,
            "_migrate_bookshelves",
            side_effect=sqlite3.Error("stop"),
        ):
            with self.assertRaises(sqlite3.Error):
                StateStore(self.database).initialize(
                    bootstrap=BootstrapCredentials("admin", "secret")
                )
        self.assertEqual(self._user_version(), 1)

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
            user_id="reader",
        )

        self.store.mark_missing(record.book_id)

        self.assertEqual(self.store.active_books(), ())
        self.assertEqual(
            self.store.get_annotation("annotation", user_id="reader")["book_hash"],
            record.book_id,
        )

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
        store.initialize()
        legacy = store.get_annotation("legacy")

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
            }
        )
        self.assertEqual(store.get_annotation("new")["text"], "New")

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
                ) VALUES ('old', ?, 'book', 3, 'old note', '#fff', '2025', '2025')
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
                "INSERT INTO bookshelves (username, version, data) VALUES (?, 7, '{}')",
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

    def _user_version(self):
        with sqlite3.connect(self.database) as connection:
            return connection.execute("PRAGMA user_version").fetchone()[0]


if __name__ == "__main__":
    unittest.main()
