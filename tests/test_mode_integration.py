import contextlib
import io
import json
import shutil
import sqlite3
import tempfile
import time
import unittest
import warnings
import zipfile
from pathlib import Path
from unittest import mock

from starlette.testclient import TestClient

from epub_browser.cli import SSGConfig, parse_cli
from epub_browser.migration import MigrationManager
from epub_browser.processor import EPUBProcessor
from epub_browser.runtime import run_server
from epub_browser.server_library import ServerLibraryManager
from epub_browser.ssg import run_ssg
from epub_browser.state import StateStore


class ModeIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.sources = self.root / "sources"
        self.sources.mkdir()
        self.source = self.sources / "book.epub"
        self._write_epub(self.source)

    def test_legacy_runtime_upgrade_preserves_identity_and_all_user_data(self):
        server_dir = self.root / "legacy-server"
        server_dir.mkdir()
        legacy_id = MigrationManager._derive_legacy_book_id(self.source)
        self.assertIsNotNone(legacy_id)
        legacy_database = server_dir / "epub-browser.db"
        legacy_store = StateStore(legacy_database)
        legacy_store.initialize()
        legacy_store.upsert_annotation(
            {
                "id": "saved-note",
                "book_hash": legacy_id,
                "chapter_index": 0,
                "text": "Preserved annotation",
                "color": "#fff",
                "created_at": "2026",
                "updated_at": "2026",
            }
        )
        legacy_store.create_bookshelf(
            "reader",
            2,
            {"items": [legacy_id], "groups": {}},
        )
        legacy_store.set_reading_progress("reader", legacy_id, 0)
        (server_dir / "epub-browser-bookshelf-reader-5.json").write_text(
            json.dumps({"items": [legacy_id], "groups": {}, "order": [legacy_id]}),
            encoding="utf-8",
        )
        (server_dir / "index.html").write_text("legacy library", encoding="utf-8")
        (server_dir / "book-metadata.json").write_text(
            json.dumps([{"hash": legacy_id, "title": "Legacy Book"}]),
            encoding="utf-8",
        )
        (server_dir / "sw.js").write_text("legacy worker", encoding="utf-8")
        (server_dir / "assets").mkdir()
        (server_dir / "book" / legacy_id).mkdir(parents=True)
        (server_dir / "book" / legacy_id / "index.html").write_text(
            "legacy book",
            encoding="utf-8",
        )

        converter = mock.Mock(side_effect=EPUBProcessor)

        def library_factory(**kwargs):
            return ServerLibraryManager(
                converter_factory=converter,
                max_workers=1,
                **kwargs,
            )

        legacy_config = parse_cli(
            [
                str(self.sources),
                "--output-dir",
                str(server_dir),
                "--no-browser",
            ]
        )
        with (
            warnings.catch_warnings(),
            contextlib.redirect_stdout(io.StringIO()),
            contextlib.redirect_stderr(io.StringIO()) as stderr,
        ):
            warnings.simplefilter("ignore", ResourceWarning)
            first_status = run_server(
                legacy_config,
                server_factory=_ReturningServer,
                library_factory=library_factory,
            )

        self.assertEqual(first_status, 0)
        self.assertEqual(stderr.getvalue(), "")
        self.assertEqual(converter.call_count, 1)
        database_path = server_dir / "data" / "epub-browser.db"
        migrated = StateStore(database_path)
        record = migrated.active_books()[0]
        self.assertEqual(record.book_id, legacy_id)
        self.assertEqual(migrated.get_annotation("saved-note")["book_hash"], legacy_id)
        self.assertEqual(migrated.get_reading_progress("reader", legacy_id), 0)
        shelf_version, shelf_data = migrated.get_bookshelf("reader")
        self.assertEqual(shelf_version, 5)
        self.assertEqual(json.loads(shelf_data)["items"], [legacy_id])
        self.assertTrue(
            (server_dir / "cache" / "public" / "book" / legacy_id / "index.html").is_file()
        )
        migration_state = json.loads(
            (server_dir / "data" / "migration-state.json").read_text(encoding="utf-8")
        )
        self.assertTrue(Path(migration_state["backup_path"]).is_file())
        self.assertFalse(legacy_database.exists())
        self.assertTrue((server_dir / "cache" / "legacy-public" / "index.html").is_file())

        converter.reset_mock()
        explicit_config = parse_cli(
            [
                "server",
                str(self.sources),
                "--server-dir",
                str(server_dir),
                "--no-browser",
            ]
        )
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            second_status = run_server(
                explicit_config,
                server_factory=_ReturningServer,
                library_factory=library_factory,
            )

        self.assertEqual(second_status, 0)
        converter.assert_not_called()
        self.assertFalse((server_dir / "cache" / "legacy-public").exists())
        completed_state = json.loads(
            (server_dir / "data" / "migration-state.json").read_text(encoding="utf-8")
        )
        self.assertEqual(completed_state["layout_phase"], "complete")

    def test_ssg_and_server_keep_deployment_artifacts_isolated(self):
        ssg_output = self.root / "dist"
        server_dir = self.root / "server"
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(run_ssg(SSGConfig((self.source,), ssg_output)), 0)
            self.assertEqual(
                run_server(
                    parse_cli(
                        [
                            "server",
                            str(self.source),
                            "--server-dir",
                            str(server_dir),
                            "--no-browser",
                        ]
                    ),
                    server_factory=_ReturningServer,
                ),
                0,
            )

        for forbidden in ("data", "cache", "epub-browser.db", "migration-state.json"):
            self.assertFalse((ssg_output / forbidden).exists())
        for public_artifact in ("index.html", "book-metadata.json", "assets", "book", "sw.js"):
            self.assertFalse((server_dir / public_artifact).exists())
        self.assertTrue((server_dir / "data" / "epub-browser.db").is_file())
        self.assertTrue((server_dir / "cache" / "public" / "index.html").is_file())

        store = StateStore(server_dir / "data" / "epub-browser.db")
        book_id = store.active_books()[0].book_id
        store.upsert_annotation(
            {
                "id": "durable",
                "book_hash": book_id,
                "chapter_index": 0,
                "text": "Keep after cache deletion",
                "color": "#fff",
                "created_at": "2026",
                "updated_at": "2026",
            }
        )
        shutil.rmtree(server_dir / "cache")
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            status = run_server(
                parse_cli(
                    [
                        "server",
                        str(self.source),
                        "--server-dir",
                        str(server_dir),
                        "--no-browser",
                    ]
                ),
                server_factory=_ReturningServer,
            )

        self.assertEqual(status, 0)
        self.assertEqual(store.active_books()[0].book_id, book_id)
        self.assertEqual(store.get_annotation("durable")["book_hash"], book_id)
        self.assertTrue(
            (server_dir / "cache" / "public" / "book" / book_id / "index.html").is_file()
        )

    def test_ssg_cli_output_is_quiet_without_log_and_detailed_with_log(self):
        quiet_output = self.root / "quiet"
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            status = run_ssg(SSGConfig((self.source,), quiet_output))

        self.assertEqual(status, 0)
        self.assertEqual(stderr.getvalue(), "")
        self.assertEqual(
            stdout.getvalue(),
            f"Files generated in: {quiet_output.resolve()}\n",
        )

        logged_output = self.root / "logged"
        with (
            contextlib.redirect_stdout(io.StringIO()),
            contextlib.redirect_stderr(io.StringIO()) as logged_stderr,
        ):
            logged_status = run_ssg(
                SSGConfig((self.source,), logged_output, log=True)
            )

        self.assertEqual(logged_status, 0)
        self.assertIn(str(self.source.resolve()), logged_stderr.getvalue())

    def test_v2_documentation_matches_the_public_mode_contract(self):
        dockerfile = Path("Dockerfile").read_text(encoding="utf-8")
        readme = Path("README.md").read_text(encoding="utf-8")
        migration = Path("docs/migration-v2.md")
        release = Path("docs/releases/v2.0.0.md")

        self.assertIn('"server"', dockerfile)
        self.assertIn('"--server-dir=/app/EpubBrowserFiles"', dockerfile)
        self.assertIn('"--host=0.0.0.0"', dockerfile)
        self.assertNotIn("--keep-files", dockerfile)
        self.assertIn("epub-browser ssg", readme)
        self.assertIn("epub-browser server", readme)
        self.assertIn("--base-path", readme)
        self.assertIn("127.0.0.1", readme)
        self.assertIn("reverse proxy", readme.lower())
        self.assertTrue(migration.is_file())
        self.assertTrue(release.is_file())
        self.assertIn('VERSION = "2.0.2"', Path("epub_browser/version.py").read_text())

    @staticmethod
    def _write_epub(path):
        container = """<?xml version="1.0"?>
<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0">
  <rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles>
</container>
"""
        package = """<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="book-id">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="book-id">urn:test:mode-integration</dc:identifier>
    <dc:title>Integration Book</dc:title><dc:creator>Author</dc:creator><dc:language>en</dc:language>
  </metadata>
  <manifest><item id="chapter" href="chapter.xhtml" media-type="application/xhtml+xml"/></manifest>
  <spine><itemref idref="chapter"/></spine>
</package>
"""
        chapter = """<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml"><head><title>One</title></head>
<body><h1>One</h1><p>Integration text</p></body></html>
"""
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("mimetype", "application/epub+zip")
            archive.writestr("META-INF/container.xml", container)
            archive.writestr("OEBPS/content.opf", package)
            archive.writestr("OEBPS/chapter.xhtml", chapter)


class _ReturningServer:
    def __init__(self, config):
        self.config = config
        self.started = True

    def run(self):
        client = TestClient(self.config.app)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if client.get("/api/health").json()["state"] in {"ready", "degraded"}:
                return None
            time.sleep(0.01)
        raise RuntimeError("initial Server reconciliation did not finish")


if __name__ == "__main__":
    unittest.main()
