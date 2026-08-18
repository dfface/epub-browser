import asyncio
import json
import os
import shutil
import tempfile
import threading
import time
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from epub_browser.identity import source_sha256
from epub_browser.library_progress import LibraryProgressBroker
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

    def _manager(self, converter_factory=EPUBProcessor, **kwargs):
        return ServerLibraryManager(
            server_dir=self.server_dir,
            sources=(self.source_dir,),
            state_store=self.store,
            migration_manager=self.migration,
            converter_factory=converter_factory,
            max_workers=2,
            **kwargs,
        )

    @staticmethod
    def _latest_subscription_snapshot(loop, subscription):
        loop.run_until_complete(asyncio.sleep(0))
        latest = None
        while not subscription.queue.empty():
            latest = subscription.queue.get_nowait()
        return latest

    def test_reconcile_reports_incremental_progress_and_catalog_publication(self):
        broker = LibraryProgressBroker()
        second_source = self.source_dir / "second.epub"
        self._write_epub(second_source, "Second")
        manager = self._manager(progress_broker=broker)

        summary = manager.reconcile()
        snapshot = broker.snapshot()

        self.assertFalse(summary.cancelled)
        self.assertEqual(snapshot.phase, "complete")
        self.assertEqual(snapshot.total, 2)
        self.assertEqual(snapshot.completed, 2)
        self.assertEqual(snapshot.active_books, 2)
        self.assertGreaterEqual(snapshot.catalog_revision, 1)
        manager.shutdown()

    def test_watch_reconcile_creates_watch_generation(self):
        broker = LibraryProgressBroker()
        manager = self._manager(progress_broker=broker)
        manager.reconcile()
        manager.reconcile(trigger="watch")

        snapshot = broker.snapshot()
        self.assertEqual(snapshot.generation, 2)
        self.assertEqual(snapshot.trigger, "watch")
        manager.shutdown()

    def test_cancelled_reconcile_does_not_publish_terminal_success(self):
        broker = LibraryProgressBroker()
        manager = self._manager(progress_broker=broker)
        manager.request_stop()

        summary = manager.reconcile()

        self.assertTrue(summary.cancelled)
        self.assertNotIn(broker.snapshot().phase, {"complete", "degraded"})
        manager.shutdown()

    def test_unknown_delete_does_not_start_a_watch_generation(self):
        broker = LibraryProgressBroker()
        manager = self._manager(progress_broker=broker)

        manager.mark_deleted(self.source_dir / "unknown.epub")

        snapshot = broker.snapshot()
        self.assertEqual(snapshot.generation, 0)
        self.assertEqual(snapshot.catalog_revision, 0)
        manager.shutdown()

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

    def test_metadata_only_stat_change_is_recorded_after_one_recheck(self):
        manager = self._manager()
        manager.reconcile()
        stat = self.source.stat()
        os.utime(
            self.source,
            ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000),
        )

        with (
            mock.patch(
                "epub_browser.server_library.source_sha256",
                wraps=source_sha256,
            ) as fingerprint,
            mock.patch.object(
                manager,
                "_probe_metadata",
                wraps=manager._probe_metadata,
            ) as probe,
        ):
            manager.reconcile()
            fingerprint.reset_mock()
            probe.reset_mock()
            manager.reconcile()

        fingerprint.assert_not_called()
        probe.assert_not_called()
        manager.shutdown()

    def test_prepare_public_shell_removes_abandoned_staging_jobs_once(self):
        manager = self._manager()
        abandoned = manager.staging_dir / "abandoned-job"
        abandoned.mkdir(parents=True)
        (abandoned / "partial.txt").write_text("partial", encoding="utf-8")

        manager.prepare_public_shell()

        self.assertFalse(abandoned.exists())
        self.assertTrue(manager.staging_dir.is_dir())
        manager.shutdown()

    def test_interrupted_discovery_does_not_mark_unscanned_books_missing(self):
        manager = self._manager()
        original = manager.reconcile().active_books[0]
        real_walk = os.walk

        def interrupted_walk(*args, **kwargs):
            for item in real_walk(*args, **kwargs):
                manager.request_stop()
                yield item

        with mock.patch(
            "epub_browser.server_library.os.walk",
            side_effect=interrupted_walk,
        ):
            summary = manager.reconcile()

        self.assertEqual([record.book_id for record in summary.active_books], [original.book_id])
        self.assertEqual(self.store.active_books()[0].book_id, original.book_id)
        metadata = json.loads(
            (manager.public_dir / "book-metadata.json").read_text(encoding="utf-8")
        )
        self.assertEqual([book["hash"] for book in metadata], [original.book_id])
        manager.shutdown()

    def test_delete_between_validation_and_commit_cannot_reactivate_book(self):
        manager = self._manager()
        validated = threading.Event()
        release_commit = threading.Event()
        original_validate = manager._validate_converted_book

        def pause_after_validation(converted):
            original_validate(converted)
            validated.set()
            release_commit.wait(timeout=5)

        manager._validate_converted_book = pause_after_validation
        result = []
        reconcile_thread = threading.Thread(
            target=lambda: result.append(manager.reconcile()),
            daemon=True,
        )
        reconcile_thread.start()
        try:
            self.assertTrue(validated.wait(timeout=2))
            self.source.unlink()
            manager.mark_deleted(self.source)
        finally:
            release_commit.set()
            reconcile_thread.join(timeout=5)

        self.assertFalse(reconcile_thread.is_alive())
        self.assertEqual(result[0].active_books, ())
        self.assertEqual(self.store.active_books(), ())
        metadata = json.loads(
            (manager.public_dir / "book-metadata.json").read_text(encoding="utf-8")
        )
        self.assertEqual(metadata, [])
        manager.shutdown()

    def test_delete_during_identical_content_reuse_cannot_reactivate_book(self):
        manager = self._manager()
        manager.reconcile()
        stat = self.source.stat()
        os.utime(
            self.source,
            ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000),
        )
        reuse_checked = threading.Event()
        release_reuse = threading.Event()
        original_cache_valid = manager._cache_valid
        cache_checks = 0

        def pause_after_reuse_check(record):
            nonlocal cache_checks
            valid = original_cache_valid(record)
            cache_checks += 1
            if cache_checks == 2:
                reuse_checked.set()
                release_reuse.wait(timeout=5)
            return valid

        manager._cache_valid = pause_after_reuse_check
        result = []
        reconcile_thread = threading.Thread(
            target=lambda: result.append(manager.reconcile()),
            daemon=True,
        )
        reconcile_thread.start()
        try:
            self.assertTrue(reuse_checked.wait(timeout=2))
            self.source.unlink()
            manager.mark_deleted(self.source)
        finally:
            release_reuse.set()
            reconcile_thread.join(timeout=5)

        self.assertFalse(reconcile_thread.is_alive())
        self.assertEqual(result[0].active_books, ())
        self.assertEqual(self.store.active_books(), ())
        manager.shutdown()

    def test_request_stop_does_not_start_a_final_publication(self):
        class BlockingProcessor(EPUBProcessor):
            started = threading.Event()
            release = threading.Event()
            cleaned = threading.Event()

            def convert(self):
                self.started.set()
                self.release.wait(timeout=5)
                return super().convert()

            def cleanup(self):
                try:
                    super().cleanup()
                finally:
                    self.cleaned.set()

        manager = self._manager(BlockingProcessor)
        manager.migration_manager.record_cache_reconciled = mock.Mock(
            wraps=manager.migration_manager.record_cache_reconciled
        )
        manager.on_reconciled = mock.Mock()
        publications = []
        original_publish = manager._publish_current_state

        def record_publication(failures):
            publications.append(tuple(failures))
            return original_publish(failures)

        manager._publish_current_state = record_publication
        result = []
        reconcile_thread = threading.Thread(
            target=lambda: result.append(manager.reconcile()),
            daemon=True,
        )
        reconcile_thread.start()
        try:
            self.assertTrue(BlockingProcessor.started.wait(timeout=2))
            manager.request_stop()
            reconcile_thread.join(timeout=1)
            self.assertFalse(reconcile_thread.is_alive())
            self.assertEqual(len(publications), 1)
        finally:
            BlockingProcessor.release.set()
            BlockingProcessor.cleaned.wait(timeout=5)

        self.assertEqual(result[0].active_books, ())
        self.assertTrue(result[0].cancelled)
        manager.migration_manager.record_cache_reconciled.assert_not_called()
        manager.on_reconciled.assert_not_called()
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
        broker = LibraryProgressBroker()
        loop = asyncio.new_event_loop()
        self.addCleanup(loop.close)
        asyncio.set_event_loop(loop)
        subscription = broker.subscribe(loop)
        asyncio.set_event_loop(None)
        self.addCleanup(subscription.close)
        manager = self._manager(progress_broker=broker)
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
            def __init__(self, epub_path, *args, **kwargs):
                self.epub_path = epub_path

            def convert(self):
                raise RuntimeError(f"conversion failed {self.epub_path}")

        manager.converter_factory = FailingProcessor
        summary = manager.reconcile()

        self.assertTrue(summary.degraded)
        self.assertEqual(summary.failed, 1)
        self.assertIn("Original", chapter_path.read_text(encoding="utf-8"))
        self.assertEqual(self.store.active_books()[0].book_id, first.book_id)
        snapshot = self._latest_subscription_snapshot(loop, subscription)
        self.assertEqual(snapshot.phase, "degraded")
        self.assertEqual(snapshot.failures[0].filename, self.source.name)
        self.assertNotIn(self.temporary.name, str(snapshot.failures))

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

    def test_successful_books_are_published_while_other_conversions_continue(self):
        slow_source = self.source_dir / "slow.epub"
        self._write_epub(slow_source, "Slow")

        class IncrementalProcessor(EPUBProcessor):
            slow_started = threading.Event()
            release_slow = threading.Event()

            def convert(self):
                if Path(self.epub_path).name == "slow.epub":
                    self.slow_started.set()
                    self.release_slow.wait(timeout=5)
                return super().convert()

        broker = LibraryProgressBroker()
        loop = asyncio.new_event_loop()
        self.addCleanup(loop.close)
        asyncio.set_event_loop(loop)
        subscription = broker.subscribe(loop)
        asyncio.set_event_loop(None)
        self.addCleanup(subscription.close)
        manager = self._manager(IncrementalProcessor, progress_broker=broker)
        result = []
        reconcile_thread = threading.Thread(
            target=lambda: result.append(manager.reconcile()),
            daemon=True,
        )
        reconcile_thread.start()
        try:
            self.assertTrue(IncrementalProcessor.slow_started.wait(timeout=2))
            snapshot = self._latest_subscription_snapshot(loop, subscription)
            self.assertGreater(snapshot.in_flight, 0)
            deadline = time.monotonic() + 2
            published = []
            while time.monotonic() < deadline:
                metadata_path = manager.public_dir / "book-metadata.json"
                if metadata_path.is_file():
                    published = json.loads(metadata_path.read_text(encoding="utf-8"))
                    if published:
                        break
                time.sleep(0.02)

            self.assertEqual(len(published), 1)
            self.assertTrue(reconcile_thread.is_alive())
            snapshot = self._latest_subscription_snapshot(loop, subscription)
            self.assertGreaterEqual(snapshot.catalog_revision, 1)
        finally:
            IncrementalProcessor.release_slow.set()
            reconcile_thread.join(timeout=5)

        self.assertFalse(reconcile_thread.is_alive())
        self.assertEqual(len(result[0].active_books), 2)
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
