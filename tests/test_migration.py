import io
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from epub_browser.auth import BootstrapCredentials
from epub_browser.cli import ServerConfig
from epub_browser.migration import (
    MigrationConflictError,
    MigrationError,
    MigrationManager,
)
from epub_browser.state import DB_SCHEMA_VERSION, StateStore


class MigrationManagerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.server_dir = Path(self.temporary.name)
        self.bootstrap = BootstrapCredentials("admin", "secret")

    def test_migrates_root_database_with_backup_and_schema_upgrade(self):
        source = self.server_dir / "epub-browser.db"
        self._create_legacy_database(source)

        result = self._manager().prepare_data()

        self.assertEqual(
            result.database_path,
            self.server_dir / "data" / "epub-browser.db",
        )
        self.assertIsNotNone(result.backup_path)
        self.assertTrue(result.backup_path.is_file())
        self.assertTrue(source.exists())
        self.assertEqual(
            result.warnings,
            (f"Legacy root database was retained after migration: {source}",),
        )
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

        result = self._manager().prepare_data()

        self.assertTrue(result.database_path.is_file())
        self.assertTrue(source.exists())

    def test_migrates_root_database_with_committed_wal_pages(self):
        source = self.server_dir / "epub-browser.db"
        self._create_legacy_database(source)

        with sqlite3.connect(source) as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA wal_autocheckpoint=0")
            connection.execute(
                """
                INSERT INTO annotations (
                    id, book_hash, chapter_index, text, color,
                    created_at, updated_at
                ) VALUES ('wal', 'book', 0, 'Committed in WAL', '#fff', '2026', '2026')
                """
            )
            connection.commit()
            self.assertTrue(source.with_name(f"{source.name}-wal").exists())
            result = self._manager().prepare_data()

        with sqlite3.connect(result.backup_path) as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT text FROM annotations WHERE id = 'wal'"
                ).fetchone()[0],
                "Committed in WAL",
            )
            self.assertEqual(
                connection.execute("PRAGMA integrity_check").fetchone()[0],
                "ok",
            )
        with sqlite3.connect(result.database_path) as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT text FROM annotations WHERE id = 'wal'"
                ).fetchone()[0],
                "Committed in WAL",
            )

    def test_root_database_changed_after_backup_is_retained(self):
        source = self.server_dir / "epub-browser.db"
        self._create_legacy_database(source)
        manager = self._manager()
        backup_sqlite_digest = manager._backup_sqlite_digest

        def backup_then_write(path):
            backup = backup_sqlite_digest(path)
            with sqlite3.connect(source) as connection:
                connection.execute(
                    """
                    INSERT INTO annotations (
                        id, book_hash, chapter_index, text, color,
                        created_at, updated_at
                    ) VALUES ('post-backup', 'book', 0, 'Retained source', '#fff', '2026', '2026')
                    """
                )
            return backup

        with mock.patch.object(
            manager,
            "_backup_sqlite_digest",
            side_effect=backup_then_write,
        ):
            result = manager.prepare_data()

        self.assertTrue(source.exists())
        with sqlite3.connect(source) as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT text FROM annotations WHERE id = 'post-backup'"
                ).fetchone()[0],
                "Retained source",
            )
        with sqlite3.connect(result.database_path) as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT text FROM annotations WHERE id = 'a'"
                ).fetchone()[0],
                "Saved",
            )
            self.assertIsNone(
                connection.execute(
                    "SELECT text FROM annotations WHERE id = 'post-backup'"
                ).fetchone()
            )

    def test_migrates_real_xpath_annotation_schema_without_losing_positions(self):
        source = self.server_dir / "annotations.db"
        self._create_xpath_annotation_database(source)

        result = self._manager().prepare_data()
        migrated = StateStore(result.database_path)
        administrator = migrated.get_user_by_username("admin")
        annotation = migrated.get_annotation(
            "legacy",
            user_id=administrator.user_id,
        )

        self.assertEqual(annotation["text"], "Saved from v1")
        self.assertEqual(
            annotation["startMeta"],
            {"legacyXPath": "/p[1]/text()[1]", "legacyOffset": 2},
        )
        self.assertEqual(
            annotation["endMeta"],
            {"legacyXPath": "/p[1]/text()[1]", "legacyOffset": 7},
        )
        with sqlite3.connect(result.backup_path) as connection:
            backup_columns = {
                row[1]
                for row in connection.execute("PRAGMA table_info(annotations)")
            }
        self.assertIn("start_xpath", backup_columns)

    def test_legacy_data_uses_pending_administrator_until_setup_completes(self):
        source = self.server_dir / "annotations.db"
        self._create_legacy_database(source, shelf_version=3)

        result = MigrationManager(self.server_dir, None).prepare_data()
        store = StateStore(result.database_path)
        pending = store.list_users()
        self.assertEqual(len(pending), 1)
        self.assertFalse(store.has_administrator())
        pending_id = pending[0].user_id
        with sqlite3.connect(result.database_path) as connection:
            annotation_owner = connection.execute(
                "SELECT user_id FROM annotations WHERE id = 'a'"
            ).fetchone()[0]
            shelf_owner = connection.execute(
                "SELECT user_id FROM bookshelves"
            ).fetchone()[0]

        MigrationManager(
            self.server_dir,
            None,
            bootstrap=BootstrapCredentials("chosen-owner", "secret"),
        ).prepare_data()
        administrator = StateStore(result.database_path).get_user_by_username(
            "chosen-owner"
        )

        self.assertEqual(annotation_owner, pending_id)
        self.assertEqual(shelf_owner, pending_id)
        self.assertEqual(administrator.user_id, pending_id)
        self.assertTrue(administrator.enabled)

    def test_conflicting_root_databases_are_left_untouched(self):
        first = self.server_dir / "epub-browser.db"
        second = self.server_dir / "annotations.db"
        self._create_legacy_database(first)
        self._create_legacy_database(second)

        with self.assertRaises(MigrationConflictError) as raised:
            self._manager().prepare_data()

        self.assertIn(str(first), str(raised.exception))
        self.assertIn(str(second), str(raised.exception))
        self.assertTrue(first.is_file())
        self.assertTrue(second.is_file())
        self.assertFalse((self.server_dir / "data").exists())

    def test_corrupt_candidate_is_left_untouched(self):
        source = self.server_dir / "epub-browser.db"
        source.write_bytes(b"not sqlite")

        with self.assertRaisesRegex(MigrationError, "integrity"):
            self._manager().prepare_data()

        self.assertEqual(source.read_bytes(), b"not sqlite")
        self.assertFalse((self.server_dir / "data").exists())

    def test_prepare_data_is_idempotent(self):
        source = self.server_dir / "epub-browser.db"
        self._create_legacy_database(source)
        manager = self._manager()

        first = manager.prepare_data()
        second = manager.prepare_data()

        self.assertEqual(first.database_path, second.database_path)
        self.assertEqual(first.backup_path, second.backup_path)
        self.assertTrue(source.exists())
        self.assertEqual(
            first.warnings,
            (f"Legacy root database was retained after migration: {source}",),
        )
        self.assertEqual(
            second.warnings,
            (
                "Authoritative data database already exists; legacy root database "
                f"was left untouched: {source}",
            ),
        )
        self.assertEqual(
            len(list((self.server_dir / "data" / "backups").iterdir())),
            1,
        )
        with sqlite3.connect(second.database_path) as connection:
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM annotations").fetchone()[0],
                1,
            )

    def test_prior_authoritative_schema_is_backed_up_before_in_place_upgrade(self):
        database = self.server_dir / "data" / "epub-browser.db"
        store = StateStore(database)
        administrator = store.initialize(bootstrap=self.bootstrap)
        with sqlite3.connect(database) as connection:
            connection.execute(f"PRAGMA user_version = {DB_SCHEMA_VERSION - 1}")

        manager = self._manager()
        first = manager.prepare_data()
        backup_count = len(tuple((self.server_dir / "data" / "backups").iterdir()))
        second = manager.prepare_data()

        self.assertIsNotNone(first.backup_path)
        self.assertTrue(first.backup_path.is_file())
        self.assertEqual(second.backup_path, first.backup_path)
        self.assertEqual(
            len(tuple((self.server_dir / "data" / "backups").iterdir())),
            backup_count,
        )
        with sqlite3.connect(database) as connection:
            self.assertEqual(
                connection.execute("PRAGMA user_version").fetchone()[0],
                DB_SCHEMA_VERSION,
            )

        restored = self.server_dir / "restored.db"
        restored.write_bytes(first.backup_path.read_bytes())
        with sqlite3.connect(restored) as connection:
            self.assertEqual(
                connection.execute("PRAGMA user_version").fetchone()[0],
                DB_SCHEMA_VERSION - 1,
            )
            self.assertEqual(
                connection.execute(
                    "SELECT id FROM users WHERE username = 'admin'"
                ).fetchone()[0],
                administrator.user_id,
            )

    def test_authoritative_backup_includes_committed_wal_pages(self):
        database = self.server_dir / "data" / "epub-browser.db"
        database.parent.mkdir()

        with sqlite3.connect(database) as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA wal_autocheckpoint=0")
            connection.execute(f"PRAGMA user_version = {DB_SCHEMA_VERSION - 1}")
            connection.execute("CREATE TABLE wal_marker(value TEXT)")
            connection.execute("INSERT INTO wal_marker VALUES ('committed-in-wal')")
            connection.commit()
            self.assertTrue(database.with_name(f"{database.name}-wal").exists())
            backup = self._manager()._backup_authoritative_database(database)

        with sqlite3.connect(backup) as connection:
            self.assertEqual(
                connection.execute("SELECT value FROM wal_marker").fetchone()[0],
                "committed-in-wal",
            )
            self.assertEqual(
                connection.execute("PRAGMA integrity_check").fetchone()[0],
                "ok",
            )

    def test_authoritative_upgrade_backup_failure_leaves_database_unchanged(self):
        database = self.server_dir / "data" / "epub-browser.db"
        StateStore(database).initialize(bootstrap=self.bootstrap)
        with sqlite3.connect(database) as connection:
            connection.execute(f"PRAGMA user_version = {DB_SCHEMA_VERSION - 1}")
        original = database.read_bytes()
        manager = self._manager()
        check_integrity = manager._check_integrity

        def reject_snapshot(path):
            if path == database:
                return check_integrity(path)
            raise MigrationError("snapshot integrity failed")

        with (
            mock.patch.object(
                manager,
                "_check_integrity",
                side_effect=reject_snapshot,
            ),
            self.assertRaisesRegex(MigrationError, "snapshot integrity"),
        ):
            manager.prepare_data()

        self.assertEqual(database.read_bytes(), original)
        backups_dir = self.server_dir / "data" / "backups"
        self.assertFalse(any(backups_dir.glob(".*.tmp")))
        with sqlite3.connect(database) as connection:
            self.assertEqual(
                connection.execute("PRAGMA user_version").fetchone()[0],
                DB_SCHEMA_VERSION - 1,
            )

    def test_imports_only_highest_legacy_bookshelf_for_administrator(self):
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

        result = self._manager(legacy_dir).prepare_data()

        store = StateStore(result.database_path)
        administrator = store.get_user_by_username("admin")
        with sqlite3.connect(result.database_path) as connection:
            administrator_shelf = connection.execute(
                """
                SELECT version, data FROM bookshelves
                WHERE user_id = ?
                """,
                (administrator.user_id,),
            ).fetchone()
            bad = connection.execute(
                "SELECT COUNT(*) FROM bookshelves WHERE user_id != ?",
                (administrator.user_id,),
            ).fetchone()
        self.assertEqual(administrator_shelf, (5, '{"items": ["new"]}'))
        self.assertEqual(bad, (0,))

    def test_retires_only_known_public_artifacts_in_two_successful_phases(self):
        self._create_legacy_database(self.server_dir / "epub-browser.db")
        for filename in ("index.html", "book-metadata.json", "sw.js"):
            (self.server_dir / filename).write_text(filename, encoding="utf-8")
        (self.server_dir / "assets").mkdir()
        (self.server_dir / "book").mkdir()
        user_file = self.server_dir / "keep-me.txt"
        user_file.write_text("user", encoding="utf-8")
        manager = self._manager()
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

        self._manager().prepare_data()
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

    def test_runtime_maps_newer_database_schema_to_exit_status_three(self):
        from epub_browser.runtime import run_server

        database = self.server_dir / "data" / "epub-browser.db"
        database.parent.mkdir()
        with sqlite3.connect(database) as connection:
            connection.execute(f"PRAGMA user_version = {DB_SCHEMA_VERSION + 1}")
        config = ServerConfig(
            sources=(self.server_dir / "books",),
            server_dir=self.server_dir,
            ephemeral=False,
        )
        stderr = io.StringIO()

        with mock.patch("sys.stderr", stderr):
            status = run_server(config)

        self.assertEqual(status, 3)
        self.assertIn("newer schema", stderr.getvalue())

    def test_legacy_identity_correlation_reuses_only_unique_matches(self):
        manager = self._manager()
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

        self.assertEqual(unique, {first.resolve(): "legacy-hash"})
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

    def _manager(self, legacy_sync_dir=None):
        return MigrationManager(
            self.server_dir,
            legacy_sync_dir,
            bootstrap=self.bootstrap,
        )

    @staticmethod
    def _create_xpath_annotation_database(path):
        with sqlite3.connect(path) as connection:
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
                    'legacy', 'book', 1, 'Saved from v1', 'note',
                    '/p[1]/text()[1]', '/p[1]/text()[1]', 2, 7,
                    '#ffee00', '2025-01-01', '2025-01-02'
                )
                """
            )


if __name__ == "__main__":
    unittest.main()
