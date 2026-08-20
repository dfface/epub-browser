import asyncio
import contextlib
import io
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

from epub_browser.epub_identity import read_embedded_book_id
from epub_browser.identity import source_sha256
from epub_browser.library_progress import LibraryProgressBroker
from epub_browser.migration import MigrationManager
from epub_browser.processor import EPUBProcessor
from epub_browser.reporting import Reporter
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

    def test_first_reconcile_embeds_the_database_book_id_without_changing_resources(self):
        with zipfile.ZipFile(self.source) as archive:
            chapter_before = archive.read("OEBPS/chapter.xhtml")
        manager = self._manager()

        record = manager.reconcile().active_books[0]

        self.assertEqual(read_embedded_book_id(self.source), record.book_id)
        with zipfile.ZipFile(self.source) as archive:
            self.assertEqual(archive.read("OEBPS/chapter.xhtml"), chapter_before)
            self.assertIsNone(archive.testzip())
            self.assertEqual(archive.infolist()[0].filename, "mimetype")
            self.assertEqual(archive.infolist()[0].compress_type, zipfile.ZIP_STORED)
        manager.shutdown()

    def test_offline_move_and_content_edit_reuse_embedded_book_id(self):
        manager = self._manager()
        original = manager.reconcile().active_books[0]
        moved = self.source_dir / "moved.epub"
        self.source.rename(moved)
        self._replace_archive_text(
            moved,
            "OEBPS/chapter.xhtml",
            b"Original",
            b"Changed after move",
        )

        summary = manager.reconcile()

        self.assertFalse(summary.degraded)
        self.assertEqual([record.book_id for record in summary.active_books], [original.book_id])
        self.assertEqual(Path(summary.active_books[0].source_path), moved.resolve())
        manager.shutdown()

    def test_conflicting_embedded_id_degrades_scan_and_keeps_previous_cache(self):
        manager = self._manager()
        original = manager.reconcile().active_books[0]
        self._replace_archive_text(
            self.source,
            "OEBPS/content.opf",
            original.book_id.encode("ascii"),
            b"A" * 22,
        )

        summary = manager.reconcile()

        self.assertTrue(summary.degraded)
        self.assertEqual(summary.failures[0].book_id, original.book_id)
        self.assertTrue(summary.failures[0].kept_previous_cache)
        self.assertEqual([record.book_id for record in summary.active_books], [original.book_id])
        self.assertTrue(
            (
                manager.public_dir
                / "book"
                / original.book_id
                / "index.html"
            ).is_file()
        )
        manager.shutdown()

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

    def test_reconcile_log_reports_trigger_discovery_and_completion_while_normal_mode_is_silent(self):
        logged_manager = self._manager(reporter=Reporter(True))
        with contextlib.redirect_stderr(io.StringIO()) as stderr:
            logged_manager.reconcile(trigger="watch")
        output = stderr.getvalue()
        self.assertIn("Library reconciliation started: trigger=watch", output)
        self.assertIn("Library discovery complete: trigger=watch, total=1", output)
        self.assertIn("Library reconciliation complete: trigger=watch, total=1", output)
        logged_manager.shutdown()

        quiet_manager = self._manager(reporter=Reporter(False))
        with contextlib.redirect_stderr(io.StringIO()) as stderr:
            quiet_manager.reconcile(trigger="watch")
        self.assertEqual(stderr.getvalue(), "")
        quiet_manager.shutdown()

    def test_degraded_reconcile_and_direct_delete_have_logged_summaries(self):
        class FailingProcessor:
            def __init__(self, *args, **kwargs):
                pass

            def convert(self):
                raise RuntimeError("conversion failed")

        manager = self._manager(FailingProcessor, reporter=Reporter(True))
        with contextlib.redirect_stderr(io.StringIO()) as stderr:
            manager.reconcile()
        self.assertIn("Library reconciliation degraded: trigger=startup", stderr.getvalue())
        self.assertIn("failed=1", stderr.getvalue())
        manager.shutdown()

        self._write_epub(self.source, "Restored")
        manager = self._manager(reporter=Reporter(False))
        manager.reconcile()
        manager.reporter = Reporter(True)
        with contextlib.redirect_stderr(io.StringIO()) as stderr:
            manager.mark_deleted(self.source)
        output = stderr.getvalue()
        self.assertIn("Watch direct-delete batch started:", output)
        self.assertIn("Watch direct-delete batch complete: removed=1", output)
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

    def test_batched_watch_deletions_publish_the_total_removed(self):
        broker = LibraryProgressBroker()
        second_source = self.source_dir / "second.epub"
        self._write_epub(second_source, "Second")
        third_source = self.source_dir / "third.epub"
        self._write_epub(third_source, "Third")
        manager = self._manager(progress_broker=broker)
        manager.reconcile()
        self.source.unlink()
        second_source.unlink()

        first = manager.queue_path(self.source)
        second = manager.queue_path(second_source)
        first.result(timeout=3)
        second.result(timeout=3)

        snapshot = broker.snapshot()
        self.assertEqual(snapshot.trigger, "watch")
        self.assertEqual(snapshot.removed, 2)
        self.assertEqual(snapshot.total, 1)
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

    def test_stop_during_direct_delete_keeps_catalog_and_progress_consistent(self):
        broker = LibraryProgressBroker()
        manager = self._manager(progress_broker=broker)
        manager.reconcile()
        marked_missing = threading.Event()
        release_delete = threading.Event()
        original_mark_missing = self.store.mark_missing

        def pause_after_mark_missing(book_id):
            original_mark_missing(book_id)
            marked_missing.set()
            release_delete.wait(timeout=5)

        self.store.mark_missing = pause_after_mark_missing
        delete_thread = threading.Thread(
            target=lambda: manager.mark_deleted(self.source),
            daemon=True,
        )
        delete_thread.start()
        try:
            self.assertTrue(marked_missing.wait(timeout=2))
            stop_thread = threading.Thread(target=manager.request_stop, daemon=True)
            stop_thread.start()
            deadline = time.monotonic() + 2
            while not manager._stop_event.is_set() and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertTrue(manager._stop_event.is_set())
            release_delete.set()
            delete_thread.join(timeout=5)
            stop_thread.join(timeout=5)
        finally:
            release_delete.set()
            delete_thread.join(timeout=5)

        self.assertFalse(delete_thread.is_alive())
        self.assertEqual(self.store.active_books(), ())
        metadata = json.loads(
            (manager.public_dir / "book-metadata.json").read_text(encoding="utf-8")
        )
        self.assertEqual(metadata, [])
        self.assertNotIn(broker.snapshot().phase, {"complete", "degraded"})
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
        manager.prepare_public_shell()
        baseline_revision = broker.snapshot().catalog_revision
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
            self.assertGreater(snapshot.catalog_revision, baseline_revision)
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

    @staticmethod
    def _replace_archive_text(path, member_name, before, after):
        temporary = path.with_suffix(".rewritten.epub")
        with zipfile.ZipFile(path, "r") as source:
            with zipfile.ZipFile(temporary, "w") as destination:
                destination.comment = source.comment
                for info in source.infolist():
                    data = source.read(info)
                    if info.filename == member_name:
                        data = data.replace(before, after)
                    destination.writestr(info, data)
        temporary.replace(path)


if __name__ == "__main__":
    unittest.main()
