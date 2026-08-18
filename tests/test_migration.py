import io
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from epub_browser.cli import ServerConfig
from epub_browser.migration import (
    MigrationConflictError,
    MigrationError,
    MigrationManager,
)
from epub_browser.state import DB_SCHEMA_VERSION


class MigrationManagerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.server_dir = Path(self.temporary.name)

    def test_migrates_root_database_with_backup_and_schema_upgrade(self):
        source = self.server_dir / "epub-browser.db"
        self._create_legacy_database(source)

        result = MigrationManager(self.server_dir, None).prepare_data()

        self.assertEqual(
            result.database_path,
            self.server_dir / "data" / "epub-browser.db",
        )
        self.assertIsNotNone(result.backup_path)
        self.assertTrue(result.backup_path.is_file())
        self.assertFalse(source.exists())
        self.assertTrue(result.state_path.is_file())
        with sqlite3.connect(result.database_path) as connection:
            self.assertEqual(
                connection.execute("PRAGMA user_version").fetchone()[0],
                DB_SCHEMA_VERSION,
            )
            self.assertEqual(
                connection.execute("SELECT text FROM annotations").fetchone()[0],
                "Saved",
            )

    def test_migrates_annotations_database_when_it_is_only_candidate(self):
        source = self.server_dir / "annotations.db"
        self._create_legacy_database(source)

        result = MigrationManager(self.server_dir, None).prepare_data()

        self.assertTrue(result.database_path.is_file())
        self.assertFalse(source.exists())

    def test_conflicting_root_databases_are_left_untouched(self):
        first = self.server_dir / "epub-browser.db"
        second = self.server_dir / "annotations.db"
        self._create_legacy_database(first)
        self._create_legacy_database(second)

        with self.assertRaises(MigrationConflictError) as raised:
            MigrationManager(self.server_dir, None).prepare_data()

        self.assertIn(str(first), str(raised.exception))
        self.assertIn(str(second), str(raised.exception))
        self.assertTrue(first.is_file())
        self.assertTrue(second.is_file())
        self.assertFalse((self.server_dir / "data").exists())

    def test_corrupt_candidate_is_left_untouched(self):
        source = self.server_dir / "epub-browser.db"
        source.write_bytes(b"not sqlite")

        with self.assertRaisesRegex(MigrationError, "integrity"):
            MigrationManager(self.server_dir, None).prepare_data()

        self.assertEqual(source.read_bytes(), b"not sqlite")
        self.assertFalse((self.server_dir / "data").exists())

    def test_prepare_data_is_idempotent(self):
        source = self.server_dir / "epub-browser.db"
        self._create_legacy_database(source)
        manager = MigrationManager(self.server_dir, None)

        first = manager.prepare_data()
        second = manager.prepare_data()

        self.assertEqual(first.database_path, second.database_path)
        self.assertEqual(first.backup_path, second.backup_path)
        self.assertEqual(
            len(list((self.server_dir / "data" / "backups").iterdir())),
            1,
        )
        with sqlite3.connect(second.database_path) as connection:
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM annotations").fetchone()[0],
                1,
            )

    def test_imports_only_the_highest_bookshelf_version_per_user(self):
        source = self.server_dir / "epub-browser.db"
        self._create_legacy_database(source, shelf_version=3)
        legacy_dir = self.server_dir / "legacy-sync"
        legacy_dir.mkdir()
        (self.server_dir / "epub-browser-bookshelf-reader-2.json").write_text(
            '{"items":["old"]}',
            encoding="utf-8",
        )
        (legacy_dir / "epub-browser-bookshelf-reader-5.json").write_text(
            '{"items":["new"]}',
            encoding="utf-8",
        )
        (legacy_dir / "epub-browser-bookshelf-other-4.json").write_text(
            '{"items":["other"]}',
            encoding="utf-8",
        )
        (legacy_dir / "epub-browser-bookshelf-bad-9.json").write_text(
            "[]",
            encoding="utf-8",
        )

        result = MigrationManager(self.server_dir, legacy_dir).prepare_data()

        with sqlite3.connect(result.database_path) as connection:
            reader = connection.execute(
                "SELECT version, data FROM bookshelves WHERE username = 'reader'"
            ).fetchone()
            other = connection.execute(
                "SELECT version, data FROM bookshelves WHERE username = 'other'"
            ).fetchone()
            bad = connection.execute(
                "SELECT version FROM bookshelves WHERE username = 'bad'"
            ).fetchone()
        self.assertEqual(reader, (5, '{"items": ["new"]}'))
        self.assertEqual(other, (4, '{"items": ["other"]}'))
        self.assertIsNone(bad)

    def test_retires_only_known_public_artifacts_in_two_successful_phases(self):
        self._create_legacy_database(self.server_dir / "epub-browser.db")
        for filename in ("index.html", "book-metadata.json", "sw.js"):
            (self.server_dir / filename).write_text(filename, encoding="utf-8")
        (self.server_dir / "assets").mkdir()
        (self.server_dir / "book").mkdir()
        user_file = self.server_dir / "keep-me.txt"
        user_file.write_text("user", encoding="utf-8")
        manager = MigrationManager(self.server_dir, None)
        manager.prepare_data()

        manager.record_cache_reconciled()

        legacy_public = self.server_dir / "cache" / "legacy-public"
        self.assertTrue((legacy_public / "index.html").is_file())
        self.assertFalse((self.server_dir / "index.html").exists())
        self.assertTrue(user_file.is_file())

        manager.finish_legacy_public_retirement()

        self.assertFalse(legacy_public.exists())
        state = json.loads(
            (self.server_dir / "data" / "migration-state.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(state["layout_phase"], "complete")

    def test_runtime_maps_migration_failure_to_exit_status_three(self):
        from epub_browser.runtime import run_server

        config = ServerConfig(
            sources=(self.server_dir / "books",),
            server_dir=self.server_dir,
            ephemeral=False,
        )
        stderr = io.StringIO()
        with mock.patch(
            "epub_browser.runtime.MigrationManager.prepare_data",
            side_effect=MigrationConflictError("choose one database"),
        ), mock.patch("sys.stderr", stderr):
            status = run_server(config)
            message = stderr.getvalue()

        self.assertEqual(status, 3)
        self.assertIn("choose one database", message)

    def test_legacy_identity_correlation_reuses_only_unique_matches(self):
        manager = MigrationManager(self.server_dir, None)
        manager.prepare_data()
        state_path = self.server_dir / "data" / "migration-state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["legacy_book_ids"] = ["legacy-hash"]
        state_path.write_text(json.dumps(state), encoding="utf-8")
        first = self.server_dir / "first.epub"
        second = self.server_dir / "second.epub"

        with mock.patch.object(
            manager,
            "_derive_legacy_book_id",
            return_value="legacy-hash",
        ):
            unique = manager.correlate_legacy_book_ids((first,))
            ambiguous = manager.correlate_legacy_book_ids((first, second))

        self.assertEqual(unique, {first.absolute(): "legacy-hash"})
        self.assertEqual(ambiguous, {})

    @staticmethod
    def _create_legacy_database(path, shelf_version=None):
        with sqlite3.connect(path) as connection:
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
                    id, book_hash, chapter_index, text, color,
                    created_at, updated_at
                ) VALUES ('a', 'book', 0, 'Saved', '#fff', '2026', '2026')
                """
            )
            connection.execute(
                """
                CREATE TABLE bookshelves (
                    username TEXT PRIMARY KEY,
                    version INTEGER NOT NULL,
                    data TEXT NOT NULL
                )
                """
            )
            if shelf_version is not None:
                connection.execute(
                    "INSERT INTO bookshelves VALUES (?, ?, ?)",
                    ("reader", shelf_version, '{"items":["database"]}'),
                )


if __name__ == "__main__":
    unittest.main()
