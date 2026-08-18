import json
import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from epub_browser.migration import MigrationManager
from epub_browser.processor import EPUBProcessor
from epub_browser.server_library import ServerLibraryManager
from epub_browser.state import StateStore


class ServerLibraryManagerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.server_dir = self.root / "server"
        self.source_dir = self.root / "sources"
        self.source_dir.mkdir()
        self.source = self.source_dir / "book.epub"
        self._write_epub(self.source, "Original")
        self.migration = MigrationManager(self.server_dir, None)
        result = self.migration.prepare_data()
        self.store = StateStore(result.database_path)

    def _manager(self, converter_factory=EPUBProcessor):
        return ServerLibraryManager(
            server_dir=self.server_dir,
            sources=(self.source_dir,),
            state_store=self.store,
            migration_manager=self.migration,
            converter_factory=converter_factory,
            max_workers=2,
        )

    def test_second_reconcile_reuses_unchanged_book_cache(self):
        converter = mock.Mock(side_effect=EPUBProcessor)
        manager = self._manager(converter)

        first = manager.reconcile()
        converter.reset_mock()
        second = manager.reconcile()

        self.assertEqual(first.converted, 1)
        self.assertEqual(second.reused, 1)
        converter.assert_not_called()
        manager.shutdown()

    def test_generated_cache_bootstraps_server_mode(self):
        manager = self._manager()

        record = manager.reconcile().active_books[0]
        library_html = (manager.public_dir / "index.html").read_text(encoding="utf-8")
        book_html = (
            manager.public_dir / "book" / record.book_id / "index.html"
        ).read_text(encoding="utf-8")
        chapter_html = (
            manager.public_dir / "book" / record.book_id / "chapter_0.html"
        ).read_text(encoding="utf-8")

        for html in (library_html, book_html, chapter_html):
            self.assertRegex(
                html,
                r"window\.EpubBrowserMode=(?:[\"'`])server(?:[\"'`])",
            )
        manager.shutdown()

    def test_cache_deletion_rebuilds_without_changing_book_id(self):
        manager = self._manager()
        original = manager.reconcile().active_books[0]
        shutil.rmtree(self.server_dir / "cache")

        rebuilt = manager.reconcile().active_books[0]

        self.assertEqual(rebuilt.book_id, original.book_id)
        self.assertTrue(
            (
                self.server_dir
                / "cache"
                / "public"
                / "book"
                / original.book_id
                / "index.html"
            ).is_file()
        )
        manager.shutdown()

    def test_failed_update_keeps_previous_cache_and_reports_degraded(self):
        manager = self._manager()
        first = manager.reconcile().active_books[0]
        chapter_path = (
            self.server_dir
            / "cache"
            / "public"
            / "book"
            / first.book_id
            / "chapter_0.html"
        )
        self.assertIn("Original", chapter_path.read_text(encoding="utf-8"))
        self._write_epub(self.source, "Changed")

        class FailingProcessor:
            def __init__(self, *args, **kwargs):
                pass

            def convert(self):
                raise RuntimeError("conversion failed")

        manager.converter_factory = FailingProcessor
        summary = manager.reconcile()

        self.assertTrue(summary.degraded)
        self.assertEqual(summary.failed, 1)
        self.assertIn("Original", chapter_path.read_text(encoding="utf-8"))
        self.assertEqual(self.store.active_books()[0].book_id, first.book_id)

        manager.converter_factory = EPUBProcessor
        retried = manager.reconcile()

        self.assertEqual(retried.converted, 1)
        self.assertFalse(retried.degraded)
        self.assertIn("Changed", chapter_path.read_text(encoding="utf-8"))
        manager.shutdown()

    def test_reconciliation_callbacks_report_each_scan_result(self):
        manager = self._manager()
        events = []
        manager.on_reconcile_started = lambda: events.append("scanning")
        manager.on_reconciled = lambda summary: events.append(
            "degraded" if summary.degraded else "ready"
        )

        manager.reconcile()
        self._write_epub(self.source, "Changed")

        class FailingProcessor:
            def __init__(self, *args, **kwargs):
                pass

            def convert(self):
                raise RuntimeError("conversion failed")

        manager.converter_factory = FailingProcessor
        manager.reconcile()

        self.assertEqual(events, ["scanning", "ready", "scanning", "degraded"])
        manager.shutdown()

    def test_delete_hides_book_but_preserves_data_and_restore_reuses_id(self):
        manager = self._manager()
        record = manager.reconcile().active_books[0]
        self.store.upsert_annotation(
            {
                "id": "saved",
                "book_hash": record.book_id,
                "chapter_index": 0,
                "text": "Text",
                "color": "#fff",
                "created_at": "2026",
                "updated_at": "2026",
            }
        )
        self.source.unlink()

        removed = manager.reconcile()

        metadata = json.loads(
            (self.server_dir / "cache" / "public" / "book-metadata.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(removed.removed, 1)
        self.assertEqual(metadata, [])
        self.assertEqual(self.store.active_books(), ())
        self.assertEqual(
            self.store.get_annotation("saved")["book_hash"],
            record.book_id,
        )

        self._write_epub(self.source, "Original")
        restored = manager.reconcile().active_books[0]

        self.assertEqual(restored.book_id, record.book_id)
        manager.shutdown()

    def test_discovery_ignores_directory_symlink_outside_source_root(self):
        outside = self.root / "outside"
        outside.mkdir()
        outside_book = outside / "outside.epub"
        self._write_epub(outside_book, "Outside")
        self.source.unlink()
        (self.source_dir / "linked").symlink_to(outside, target_is_directory=True)
        manager = self._manager()

        summary = manager.reconcile()

        self.assertEqual(summary.active_books, ())
        manager.shutdown()

    def test_rejects_managed_and_source_directory_nesting(self):
        nested_server = self.source_dir / "server"
        with self.assertRaisesRegex(ValueError, "must not be nested"):
            ServerLibraryManager(
                server_dir=nested_server,
                sources=(self.source_dir,),
                state_store=self.store,
            )

        source_inside_server = self.server_dir / "sources"
        source_inside_server.mkdir(parents=True)
        with self.assertRaisesRegex(ValueError, "must not be nested"):
            ServerLibraryManager(
                server_dir=self.server_dir,
                sources=(source_inside_server,),
                state_store=self.store,
            )

    @staticmethod
    def _write_epub(path, chapter_text):
        container = """<?xml version="1.0"?>
<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0">
  <rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles>
</container>
"""
        package = """<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="book-id">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="book-id">urn:test:server-library</dc:identifier>
    <dc:title>Server Book</dc:title><dc:creator>Author</dc:creator><dc:language>en</dc:language>
  </metadata>
  <manifest><item id="chapter" href="chapter.xhtml" media-type="application/xhtml+xml"/></manifest>
  <spine><itemref idref="chapter"/></spine>
</package>
"""
        chapter = f"""<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml"><head><title>One</title></head>
<body><h1>One</h1><p>{chapter_text}</p></body></html>
"""
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("mimetype", "application/epub+zip")
            archive.writestr("META-INF/container.xml", container)
            archive.writestr("OEBPS/content.opf", package)
            archive.writestr("OEBPS/chapter.xhtml", chapter)


if __name__ == "__main__":
    unittest.main()
