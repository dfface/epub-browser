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

from epub_browser.asset_publisher import AssetPublisher
from epub_browser.auth import BootstrapCredentials
from epub_browser.epub_identity import (
    ensure_embedded_book_id,
    read_embedded_book_id,
)
from epub_browser.identity import source_sha256
from epub_browser.library_progress import LibraryProgressBroker
from epub_browser.migration import MigrationManager
from epub_browser.processor import EPUBProcessor
from epub_browser.reporting import Reporter
from epub_browser.server_library import ServerLibraryManager
from epub_browser.sidecar_identity import read_exact_sidecar, sidecar_path_for
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
        self.migration = MigrationManager(
            self.server_dir,
            None,
            bootstrap=BootstrapCredentials("admin", "secret"),
        )
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

    def test_first_reconcile_creates_sidecar_without_modifying_epub(self):
        before = self.source.read_bytes()
        manager = self._manager()
        record = manager.reconcile().active_books[0]
        self.assertEqual(read_exact_sidecar(self.source).book_id, record.book_id)
        self.assertEqual(self.source.read_bytes(), before)
        self.assertIsNone(read_embedded_book_id(self.source))
        manager.shutdown()

    def test_v204_embedded_id_migrates_to_sidecar_without_epub_write(self):
        ensure_embedded_book_id(
            self.source, preferred_book_id="v204_embedded_id"
        )
        before = self.source.read_bytes()
        manager = self._manager()
        record = manager.reconcile().active_books[0]
        self.assertEqual(record.book_id, "v204_embedded_id")
        self.assertEqual(read_exact_sidecar(self.source).book_id, record.book_id)
        self.assertEqual(self.source.read_bytes(), before)
        manager.shutdown()

    def test_content_edit_retains_exact_sidecar_id(self):
        manager = self._manager()
        first = manager.reconcile().active_books[0]
        self._write_epub(self.source, "Changed")
        second = manager.reconcile().active_books[0]
        self.assertEqual(second.book_id, first.book_id)
        self.assertEqual(read_exact_sidecar(self.source).book_id, first.book_id)
        manager.shutdown()

    def test_offline_epub_only_move_adopts_orphan_and_database_id(self):
        manager = self._manager()
        first = manager.reconcile().active_books[0]
        orphan = sidecar_path_for(self.source)
        moved = self.source_dir / "moved.epub"
        self.source.rename(moved)
        second = manager.reconcile().active_books[0]
        self.assertEqual(second.book_id, first.book_id)
        self.assertEqual(Path(second.source_path), moved.resolve())
        self.assertFalse(orphan.exists())
        self.assertEqual(read_exact_sidecar(moved).book_id, first.book_id)
        manager.shutdown()

    def test_epub_only_copy_gets_distinct_id_while_original_is_active(self):
        manager = self._manager()
        first = manager.reconcile().active_books[0]
        copied = self.source_dir / "copied.epub"
        shutil.copy2(self.source, copied)
        summary = manager.reconcile()
        self.assertEqual(len(summary.active_books), 2)
        self.assertEqual(len({record.book_id for record in summary.active_books}), 2)
        self.assertNotEqual(read_exact_sidecar(copied).book_id, first.book_id)
        manager.shutdown()

    def test_explicit_embedded_mode_writes_once_then_reuses(self):
        converter = mock.Mock(side_effect=EPUBProcessor)
        manager = self._manager(converter, book_id_storage="embedded")
        first = manager.reconcile()
        converter.reset_mock()
        second = manager.reconcile()
        self.assertEqual(first.converted, 1)
        self.assertEqual(second.reused, 1)
        self.assertIsNotNone(read_embedded_book_id(self.source))
        self.assertFalse(sidecar_path_for(self.source).exists())
        converter.assert_not_called()
        manager.shutdown()

    def test_epub_and_sidecar_copy_reports_duplicate_active_id(self):
        manager = self._manager()
        first = manager.reconcile().active_books[0]
        copied = self.source_dir / "copied.epub"
        shutil.copy2(self.source, copied)
        shutil.copy2(sidecar_path_for(self.source), sidecar_path_for(copied))
        summary = manager.reconcile()
        self.assertEqual(summary.failed, 1)
        self.assertIn("already used by another source", summary.failures[0].message)
        self.assertEqual(
            [record.book_id for record in summary.active_books],
            [first.book_id],
        )
        manager.shutdown()

    def test_carrier_database_conflict_keeps_previous_cache(self):
        manager = self._manager()
        first = manager.reconcile().active_books[0]
        ensure_embedded_book_id(
            self.source, preferred_book_id="conflicting_id"
        )
        summary = manager.reconcile()
        self.assertTrue(summary.degraded)
        self.assertTrue(summary.failures[0].kept_previous_cache)
        self.assertTrue(
            (manager.public_dir / "book" / first.book_id / "index.html").is_file()
        )
        manager.shutdown()

    def test_sidecar_replace_failure_has_no_database_only_fallback(self):
        manager = self._manager()
        with mock.patch(
            "epub_browser.book_identity.write_sidecar",
            side_effect=OSError("sidecar replace failed"),
        ):
            summary = manager.reconcile()
        self.assertEqual(summary.failed, 1)
        self.assertIn("sidecar replace failed", summary.failures[0].message)
        self.assertEqual(summary.active_books, ())
        self.assertEqual(self.store.active_books(), ())
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

    def test_reconcile_upgrades_unchanged_legacy_generated_output(self):
        manager = self._manager()
        record = manager.reconcile().active_books[0]
        book_dir = manager.public_dir / "book" / record.book_id
        toc = json.loads((book_dir / "toc.json").read_text(encoding="utf-8"))
        generated_pages = [book_dir / "index.html"] + [
            book_dir / item["chapter_file"]
            for item in toc
            if item.get("chapter_file")
        ]
        (book_dir / ".server-output-revision").unlink(missing_ok=True)
        for page in generated_pages:
            page.write_text("<html><body>legacy reader</body></html>", encoding="utf-8")

        upgraded = manager.reconcile()

        self.assertGreater(upgraded.converted, 0)
        self.assertEqual(upgraded.reused, 0)
        for page in generated_pages:
            self.assertRegex(
                page.read_text(encoding="utf-8"),
                r'/assets/immutable/cache-boundary\.[0-9a-f]{12}\.js',
            )
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
        self.assertEqual(metadata, [])
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

    def test_generated_server_shell_contains_no_shared_book_catalog(self):
        manager = self._manager()

        record = manager.reconcile().active_books[0]
        metadata_path = manager.public_dir / "book-metadata.json"
        library_html = (manager.public_dir / "index.html").read_text(
            encoding="utf-8"
        )

        self.assertEqual(json.loads(metadata_path.read_text(encoding="utf-8")), [])
        self.assertNotIn(record.book_id, library_html)
        self.assertNotIn("Server Book", library_html)
        manager.shutdown()

    def test_generated_server_cache_does_not_publish_a_service_worker(self):
        manager = self._manager()
        stale_worker = manager.public_dir / "sw.js"
        stale_worker.parent.mkdir(parents=True, exist_ok=True)
        stale_worker.write_text("stale worker", encoding="utf-8")

        manager.prepare_public_shell()

        self.assertFalse(stale_worker.exists())
        manager.shutdown()

    def test_server_asset_publication_never_invokes_the_worker_writer(self):
        manager = self._manager()

        with mock.patch.object(
            AssetPublisher,
            "_write_service_worker",
            side_effect=AssertionError("Server attempted to write sw.js"),
        ):
            manager.reconcile()

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
            published_books = []
            while time.monotonic() < deadline:
                book_root = manager.public_dir / "book"
                published_books = (
                    [
                        path
                        for path in book_root.iterdir()
                        if (path / "index.html").is_file()
                    ]
                    if book_root.is_dir()
                    else []
                )
                if published_books:
                    break
                time.sleep(0.02)

            self.assertEqual(len(published_books), 1)
            self.assertEqual(
                json.loads(
                    (manager.public_dir / "book-metadata.json").read_text(
                        encoding="utf-8"
                    )
                ),
                [],
            )
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
        administrator = self.store.list_users()[0]
        self.store.upsert_annotation(
            {
                "id": "saved",
                "book_hash": record.book_id,
                "chapter_index": 0,
                "text": "Text",
                "color": "#fff",
                "created_at": "2026",
                "updated_at": "2026",
            },
            user_id=administrator.user_id,
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
            self.store.get_annotation(
                "saved",
                user_id=administrator.user_id,
            )["book_hash"],
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
