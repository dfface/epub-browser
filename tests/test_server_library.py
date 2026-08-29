import asyncio
import contextlib
import io
import json
import os
import re
import shutil
import tempfile
import threading
import time
import unittest
import zipfile
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
from unittest import mock

from starlette.testclient import TestClient
from pypdf import PdfWriter

from epub_browser.asset_publisher import AssetPublisher
from epub_browser.auth import AuthConfig, AuthService, BootstrapCredentials
from epub_browser.epub_identity import (
    ensure_embedded_book_id,
    read_embedded_book_id,
)
from epub_browser.identity import source_sha256
from epub_browser.library_progress import LibraryProgressBroker
from epub_browser.locales import SUPPORTED_LOCALES
from epub_browser.migration import MigrationManager
from epub_browser.processor import (
    EPUBProcessor,
    SERVER_OUTPUT_REVISION_FILE,
)
from epub_browser.server_library import (
    PDF_OUTPUT_REVISION,
    PDF_OUTPUT_REVISION_FILE,
    library_metadata,
)
from epub_browser.reporting import Reporter
from epub_browser.server import create_app
from epub_browser.server_library import ServerLibraryManager
from epub_browser.server_pages import ServerPageRenderer
from epub_browser.sidecar_identity import read_exact_sidecar, sidecar_path_for
from epub_browser.state import StateStore


class _ElementIdCollector(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.ids = []

    def handle_starttag(self, _tag, attrs):
        for name, value in attrs:
            if name == "id" and value is not None:
                self.ids.append(value)

    handle_startendtag = handle_starttag


def _json_login(client, username, password):
    page = client.get("/login")
    match = re.search(
        r'<meta name="epub-browser-auth-nonce" content="([^"]+)">',
        page.text,
    )
    if page.status_code != 200 or match is None:
        raise RuntimeError("login page did not provide an authentication nonce")
    return client.post(
        "/login",
        json={"username": username, "password": password, "next": "/"},
        headers={
            "X-EPUB-Browser-Auth-Nonce": match.group(1),
            "Origin": str(client.base_url).rstrip("/"),
            "Sec-Fetch-Site": "same-origin",
        },
    )


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
    def _write_pdf(path, *, title="Server PDF", pages=2):
        writer = PdfWriter()
        for _ in range(pages):
            writer.add_blank_page(width=320, height=480)
        writer.add_metadata({"/Title": title, "/Author": "PDF Author"})
        with Path(path).open("wb") as output:
            writer.write(output)

    @staticmethod
    def _latest_subscription_snapshot(loop, subscription):
        deadline = time.monotonic() + 1
        latest = None
        while time.monotonic() < deadline:
            loop.run_until_complete(asyncio.sleep(0))
            while not subscription.queue.empty():
                latest = subscription.queue.get_nowait()
            if latest is not None:
                return latest
            time.sleep(0.01)
        return latest

    def test_first_reconcile_creates_sidecar_without_modifying_epub(self):
        before = self.source.read_bytes()
        manager = self._manager()
        record = manager.reconcile().active_books[0]
        self.assertEqual(read_exact_sidecar(self.source).book_id, record.book_id)
        self.assertEqual(self.source.read_bytes(), before)
        self.assertIsNone(read_embedded_book_id(self.source))
        manager.shutdown()

    def test_pdf_server_cache_is_byte_identical_metadata_only_and_dynamic(self):
        self.source.unlink()
        pdf_source = self.source_dir / "document.pdf"
        self._write_pdf(pdf_source, pages=2)
        original = pdf_source.read_bytes()
        manager = self._manager()

        summary = manager.reconcile()

        self.assertEqual(summary.failed, 0)
        self.assertEqual(summary.converted, 1)
        record = summary.active_books[0]
        self.assertEqual(record.source_format, "pdf")
        book_root = manager.public_dir / "book" / record.book_id
        self.assertEqual((book_root / "pdf" / "document.pdf").read_bytes(), original)
        cache_metadata = json.loads(
            (book_root / "pdf" / "metadata.json").read_text(encoding="utf-8")
        )
        self.assertEqual(cache_metadata["title"], "Server PDF")
        self.assertEqual(cache_metadata["page_count"], 2)
        self.assertEqual(cache_metadata["source_sha256"], source_sha256(pdf_source))
        self.assertEqual(cache_metadata["document_sha256"], source_sha256(pdf_source))
        self.assertEqual(
            (book_root / PDF_OUTPUT_REVISION_FILE).read_text(encoding="utf-8").strip(),
            PDF_OUTPUT_REVISION,
        )
        self.assertFalse((book_root / "content").exists())
        self.assertFalse((book_root / "index.html").exists())
        self.assertFalse((book_root / "chapter_0.html").exists())
        self.assertNotIn("password", json.dumps(cache_metadata).casefold())
        library_entry = library_metadata((record,), manager.public_dir)[0]
        self.assertEqual(library_entry["format"], "pdf")

        app = create_app(
            manager.public_dir,
            state_store=self.store,
            auth_service=AuthService(self.store, AuthConfig.from_values([])),
        )
        client = TestClient(app)
        self.addCleanup(client.close)
        self.assertEqual(_json_login(client, "admin", "secret").status_code, 200)
        index = client.get(f"/book/{record.book_id}/index.html")
        toc = client.get(f"/book/{record.book_id}/toc.json")
        chapter = client.get(f"/book/{record.book_id}/chapter_1.html")
        cover = client.get(f"/book/{record.book_id}/cover.png")
        self.assertEqual(index.status_code, 200)
        self.assertEqual(toc.status_code, 200)
        self.assertEqual(chapter.status_code, 200)
        self.assertEqual(cover.status_code, 200)
        self.assertEqual(cover.headers["content-type"], "image/png")
        self.assertEqual([item["chapter_index"] for item in toc.json()], [0, 1])
        self.assertIn('"documentUrl":"/api/books/', chapter.text)
        self.assertIn('data-pdf-page-number="2"', chapter.text)
        self.assertNotIn(str(pdf_source), chapter.text)
        manager.shutdown()

    def test_pdf_server_cache_persists_filename_title_fallback(self):
        self.source.unlink()
        pdf_source = self.source_dir / "Original filename.pdf"
        self._write_pdf(pdf_source, title="   ", pages=1)
        manager = self._manager()

        record = manager.reconcile().active_books[0]
        payload = json.loads(
            (manager.public_dir / "book" / record.book_id / "pdf" / "metadata.json")
            .read_text(encoding="utf-8")
        )

        self.assertEqual(payload["title"], "Original filename")
        self.assertEqual(json.loads(record.metadata_json)["title"], "Original filename")
        manager.shutdown()

    def test_pdf_cache_corruption_and_changed_source_rebuild_the_whole_cache(self):
        self.source.unlink()
        pdf_source = self.source_dir / "document.pdf"
        self._write_pdf(pdf_source, title="First", pages=1)
        manager = self._manager()
        first = manager.reconcile().active_books[0]
        book_root = manager.public_dir / "book" / first.book_id
        cached_document = book_root / "pdf" / "document.pdf"
        cached_document.write_bytes(b"corrupt")

        rebuilt = manager.reconcile()

        self.assertEqual(rebuilt.converted, 1)
        self.assertEqual(cached_document.read_bytes(), pdf_source.read_bytes())
        first_cache_metadata = (book_root / "pdf" / "metadata.json").read_bytes()
        self._write_pdf(pdf_source, title="Second", pages=2)

        changed = manager.reconcile()

        self.assertEqual(changed.converted, 1)
        self.assertEqual(changed.active_books[0].book_id, first.book_id)
        self.assertNotEqual(
            (book_root / "pdf" / "metadata.json").read_bytes(),
            first_cache_metadata,
        )
        self.assertEqual(cached_document.read_bytes(), pdf_source.read_bytes())
        manager.shutdown()

    def test_pdf_dynamic_pages_pick_up_template_changes_without_reconversion(self):
        self.source.unlink()
        pdf_source = self.source_dir / "document.pdf"
        self._write_pdf(pdf_source, pages=1)
        manager = self._manager()
        record = manager.reconcile().active_books[0]
        with mock.patch.object(
            EPUBProcessor,
            "create_pdf_chapter_template",
            return_value="<html>fresh-pdf-ui</html>",
        ):
            rendered = ServerPageRenderer(
                manager.public_dir, record.book_id
            ).render_pdf_chapter(0)

        self.assertEqual(rendered, "<html>fresh-pdf-ui</html>")
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
            (
                manager.public_dir
                / "book"
                / first.book_id
                / "content"
                / "metadata.json"
            ).is_file()
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
        (book_dir / SERVER_OUTPUT_REVISION_FILE).unlink(missing_ok=True)

        upgraded = manager.reconcile()

        self.assertGreater(upgraded.converted, 0)
        self.assertEqual(upgraded.reused, 0)
        self.assertTrue((book_dir / "content" / "metadata.json").is_file())
        self.assertFalse((book_dir / "index.html").exists())
        manager.shutdown()

    def test_direct_reader_is_denied_while_legacy_output_reconverts(self):
        class BlockingProcessor(EPUBProcessor):
            started = threading.Event()
            release = threading.Event()

            def convert(self):
                self.started.set()
                self.release.wait(timeout=5)
                return super().convert()

        manager = self._manager()
        record = manager.reconcile().active_books[0]
        book_dir = manager.public_dir / "book" / record.book_id
        (book_dir / SERVER_OUTPUT_REVISION_FILE).write_text(
            "legacy\n",
            encoding="utf-8",
        )
        manager.converter_factory = BlockingProcessor
        auth_config = AuthConfig.from_values([])
        app = create_app(
            manager.public_dir,
            state_store=self.store,
            auth_service=AuthService(self.store, auth_config),
        )
        client = TestClient(app)
        self.addCleanup(client.close)
        login = _json_login(client, "admin", "secret")
        self.assertEqual(login.status_code, 200)
        results = []
        reconcile_thread = threading.Thread(
            target=lambda: results.append(manager.reconcile()),
            daemon=True,
        )
        reconcile_thread.start()
        try:
            self.assertTrue(BlockingProcessor.started.wait(timeout=2))
            for name in ("index.html", "chapter_0.html"):
                with self.subTest(state="stale", name=name):
                    stale = client.get(f"/book/{record.book_id}/{name}")
                    self.assertEqual(stale.status_code, 404)
        finally:
            BlockingProcessor.release.set()
            reconcile_thread.join(timeout=5)

        self.assertFalse(reconcile_thread.is_alive())
        self.assertEqual(results[0].converted, 1)
        for name in ("index.html", "chapter_0.html"):
            with self.subTest(state="current", name=name):
                current = client.get(f"/book/{record.book_id}/{name}")
                self.assertEqual(current.status_code, 200)
                self.assertIn("cache-boundary.", current.text)
        manager.shutdown()

    def test_changed_source_output_is_denied_during_reconversion(self):
        class BlockingProcessor(EPUBProcessor):
            started = threading.Event()
            release = threading.Event()

            def convert(self):
                self.started.set()
                self.release.wait(timeout=5)
                return super().convert()

        self._write_epub(self.source, "Original", include_cover=True)
        manager = self._manager()
        record = manager.reconcile().active_books[0]
        metadata = json.loads(record.metadata_json)
        paths = (
            "index.html",
            "chapter_0.html",
            metadata["cover"],
        )
        auth_config = AuthConfig.from_values([])
        app = create_app(
            manager.public_dir,
            state_store=self.store,
            auth_service=AuthService(self.store, auth_config),
        )
        client = TestClient(app)
        self.addCleanup(client.close)
        login = _json_login(client, "admin", "secret")
        self.assertEqual(login.status_code, 200)
        self._write_epub(self.source, "Changed", include_cover=True)
        manager.converter_factory = BlockingProcessor
        results = []
        reconcile_thread = threading.Thread(
            target=lambda: results.append(manager.reconcile()),
            daemon=True,
        )
        reconcile_thread.start()
        try:
            self.assertTrue(BlockingProcessor.started.wait(timeout=2))
            for path in paths:
                with self.subTest(state="converting", path=path):
                    response = client.get(f"/book/{record.book_id}/{path}")
                    self.assertEqual(response.status_code, 404)
        finally:
            BlockingProcessor.release.set()
            reconcile_thread.join(timeout=5)

        self.assertFalse(reconcile_thread.is_alive())
        self.assertEqual(results[0].converted, 1)
        for path in paths:
            with self.subTest(state="current", path=path):
                response = client.get(f"/book/{record.book_id}/{path}")
                self.assertEqual(response.status_code, 200)
        self.assertIn(
            "Changed",
            client.get(f"/book/{record.book_id}/chapter_0.html").text,
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
        renderer = ServerPageRenderer(manager.public_dir, record.book_id)
        book_html = renderer.render_index()
        chapter_html = renderer.render_chapter(0)

        for html in (library_html, book_html, chapter_html):
            self.assertRegex(
                html,
                r"window\.EpubBrowserMode=(?:[\"'`])server(?:[\"'`])",
            )
        manager.shutdown()

    def test_dynamic_reader_pages_reuse_server_locale_and_account_chrome(self):
        manager = self._manager()
        record = manager.reconcile().active_books[0]
        renderer = ServerPageRenderer(manager.public_dir, record.book_id)

        for markup in (renderer.render_index(), renderer.render_chapter(0)):
            id_collector = _ElementIdCollector()
            id_collector.feed(markup)
            duplicates = sorted(
                element_id
                for element_id, count in Counter(id_collector.ids).items()
                if count > 1
            )
            self.assertEqual(duplicates, [], f"duplicate generated element IDs: {duplicates}")
            for control_id in (
                'localeToggle', 'localeSelect', 'localeCurrentLabel',
                'accountMenu', 'accountPanel', 'accountPasswordForm',
                'adminMenu', 'adminPanel', 'adminClose',
            ):
                self.assertRegex(markup, rf'\bid=(?:["\'])?{control_id}(?:["\' >])')
            for locale in SUPPORTED_LOCALES:
                self.assertRegex(markup, rf'\bvalue=(?:["\'])?{re.escape(locale)}(?:["\' >])')
            self.assertRegex(markup, r'<button\b(?=[^>]*id=(?:["\'])?adminMenu)(?=[^>]*hidden)')
            self.assertRegex(markup, r'/assets/immutable/account\.[0-9a-f]{12}\.css')
            self.assertRegex(markup, r'/assets/immutable/auth\.[0-9a-f]{12}\.js')
            self.assertRegex(markup, r'/assets/immutable/locale-nav\.[0-9a-f]{12}\.js')

        manager.shutdown()

    def test_server_reader_pages_are_rendered_from_content_cache(self):
        manager = self._manager()
        record = manager.reconcile().active_books[0]
        book_dir = manager.public_dir / "book" / record.book_id
        self.assertTrue((book_dir / "content" / "metadata.json").is_file())
        self.assertFalse((book_dir / "index.html").exists())
        self.assertFalse((book_dir / "chapter_0.html").exists())

        auth_config = AuthConfig.from_values([])
        app = create_app(
            manager.public_dir,
            state_store=self.store,
            auth_service=AuthService(self.store, auth_config),
        )
        client = TestClient(app)
        self.addCleanup(client.close)
        self.assertEqual(_json_login(client, "admin", "secret").status_code, 200)

        index = client.get(f"/book/{record.book_id}/index.html")
        chapter = client.get(f"/book/{record.book_id}/chapter_0.html")
        toc = client.get(f"/book/{record.book_id}/toc.json")
        self.assertEqual(index.status_code, 200)
        self.assertEqual(chapter.status_code, 200)
        self.assertEqual(toc.status_code, 200)
        self.assertIn("window.EpubBrowserMode=\"server\"", index.text)
        self.assertIn("window.EpubBrowserMode=\"server\"", chapter.text)
        self.assertEqual(toc.json()[0]["chapter_index"], 0)
        self.assertIn("content-security-policy", chapter.headers)
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

    def test_server_library_index_is_rendered_from_the_current_spa_shell(self):
        manager = self._manager()
        manager.reconcile()
        # A Server deployment must not need a regenerated root index just to
        # serve its current UI and hashed assets.
        (manager.public_dir / "index.html").unlink()

        auth_config = AuthConfig.from_values([])
        app = create_app(
            manager.public_dir,
            state_store=self.store,
            auth_service=AuthService(self.store, auth_config),
        )
        client = TestClient(app)
        self.addCleanup(client.close)
        self.assertEqual(_json_login(client, "admin", "secret").status_code, 200)

        index = client.get("/")

        self.assertEqual(index.status_code, 200)
        self.assertIn('window.EpubBrowserMode="server"', index.text)
        self.assertIn('window.initScriptLibrary', index.text)
        self.assertIn('data-id=book-grid', index.text)
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
        content_dir = (
            self.server_dir
            / "cache"
            / "public"
            / "book"
            / original.book_id
            / "content"
        )
        self.assertTrue((content_dir / "metadata.json").is_file())
        self.assertFalse((content_dir.parent / "index.html").exists())
        manager.shutdown()

    def test_failed_source_update_keeps_stale_output_denied_and_reports_degraded(self):
        broker = LibraryProgressBroker()
        loop = asyncio.new_event_loop()
        self.addCleanup(loop.close)
        asyncio.set_event_loop(loop)
        subscription = broker.subscribe(loop)
        asyncio.set_event_loop(None)
        self.addCleanup(subscription.close)
        manager = self._manager(progress_broker=broker)
        first = manager.reconcile().active_books[0]
        succeeded = self.store.list_webhook_events(
            event_type="book.conversion.succeeded"
        )
        self.assertEqual(
            succeeded[0]["data"],
            {"book_id": first.book_id, "format": "epub"},
        )
        chapter_path = (
            self.server_dir
            / "cache"
            / "public"
            / "book"
            / first.book_id
            / "content"
            / "chapter_0.json"
        )
        self.assertIn("Original", chapter_path.read_text(encoding="utf-8"))
        auth_config = AuthConfig.from_values([])
        app = create_app(
            manager.public_dir,
            state_store=self.store,
            auth_service=AuthService(self.store, auth_config),
        )
        client = TestClient(app)
        self.addCleanup(client.close)
        login = _json_login(client, "admin", "secret")
        self.assertEqual(login.status_code, 200)
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
        self.assertFalse(summary.failures[0].kept_previous_cache)
        self.assertIn("Original", chapter_path.read_text(encoding="utf-8"))
        self.assertIn(
            client.get(f"/book/{first.book_id}/chapter_0.html").status_code,
            (403, 404),
        )
        snapshot = self._latest_subscription_snapshot(loop, subscription)
        self.assertEqual(snapshot.phase, "degraded")
        self.assertEqual(snapshot.failures[0].filename, self.source.name)
        self.assertNotIn(self.temporary.name, str(snapshot.failures))
        failed = self.store.list_webhook_events(
            event_type="book.conversion.failed"
        )[0]
        self.assertEqual(failed["data"]["source_name"], self.source.name)
        self.assertEqual(failed["data"]["error_code"], "conversion_failed")
        self.assertEqual(failed["data"]["format"], "epub")
        self.assertNotIn(str(self.source.parent), json.dumps(failed))

        manager.converter_factory = EPUBProcessor
        retried = manager.reconcile()

        self.assertEqual(retried.converted, 1)
        self.assertFalse(retried.degraded)
        self.assertIn("Changed", chapter_path.read_text(encoding="utf-8"))
        self.assertEqual(
            client.get(f"/book/{first.book_id}/chapter_0.html").status_code,
            200,
        )
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
                        if (path / "content" / "metadata.json").is_file()
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
        self.assertTrue(
            any(
                event["data"]["book_id"] == record.book_id
                for event in self.store.list_webhook_events(
                    event_type="book.removed"
                )
            )
        )
        created_before_restore = len(
            self.store.list_webhook_events(event_type="book.created")
        )
        updated_before_restore = len(
            self.store.list_webhook_events(event_type="book.updated")
        )

        self._write_epub(self.source, "Original")
        restored = manager.reconcile().active_books[0]

        self.assertEqual(restored.book_id, record.book_id)
        self.assertEqual(
            len(self.store.list_webhook_events(event_type="book.created")),
            created_before_restore,
        )
        restored_events = self.store.list_webhook_events(
            event_type="book.updated"
        )
        self.assertEqual(len(restored_events), updated_before_restore + 1)
        self.assertEqual(restored_events[0]["data"]["book_id"], record.book_id)
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

    def test_pdf_reconcile_discovers_directory_and_explicit_sources_without_identity_mutation(self):
        self.source.unlink()
        directory_pdf = self.source_dir / "directory.PDF"
        self._write_pdf(directory_pdf, title="Directory PDF", pages=1)
        explicit_dir = self.root / "explicit"
        explicit_dir.mkdir()
        explicit_pdf = explicit_dir / "explicit.pdf"
        self._write_pdf(explicit_pdf, title="Explicit PDF", pages=2)
        before = {
            directory_pdf: directory_pdf.read_bytes(),
            explicit_pdf: explicit_pdf.read_bytes(),
        }
        manager = ServerLibraryManager(
            server_dir=self.server_dir,
            sources=(self.source_dir, explicit_pdf),
            state_store=self.store,
            migration_manager=self.migration,
            reporter=Reporter(True),
            book_id_storage="embedded",
        )

        with contextlib.redirect_stderr(io.StringIO()) as stderr:
            first = manager.reconcile()
            second = manager.reconcile(trigger="watch")

        self.assertEqual(first.failed, 0)
        self.assertEqual(first.converted, 2)
        self.assertEqual(second.failed, 0)
        self.assertEqual(second.reused, 2)
        self.assertEqual(len(first.active_books), 2)
        self.assertEqual(len(second.active_books), 2)
        for source, original in before.items():
            self.assertEqual(source.read_bytes(), original)
            self.assertTrue(sidecar_path_for(source).is_file())
            record = self.store.book_by_source(source)
            self.assertEqual(record.source_format, "pdf")
            self.assertEqual(
                (
                    manager.public_dir
                    / "book"
                    / record.book_id
                    / "pdf"
                    / "document.pdf"
                ).read_bytes(),
                original,
            )
        output = stderr.getvalue()
        self.assertEqual(output.count("Embedded book ID storage is EPUB-only"), 1)
        self.assertIn("PDF identities use adjacent sidecars", output)
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
    def _write_epub(path, chapter_text, include_cover=False):
        container = """<?xml version="1.0"?>
<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0">
  <rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles>
</container>
"""
        cover_meta = '<meta name="cover" content="cover" />' if include_cover else ""
        cover_item = (
            '<item id="cover" href="cover.jpg" media-type="image/jpeg" />'
            if include_cover
            else ""
        )
        package = f"""<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="book-id">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="book-id">urn:test:server-library</dc:identifier>
    <dc:title>Server Book</dc:title><dc:creator>Author</dc:creator><dc:language>en</dc:language>
    {cover_meta}
  </metadata>
  <manifest><item id="chapter" href="chapter.xhtml" media-type="application/xhtml+xml"/>{cover_item}</manifest>
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
            if include_cover:
                archive.writestr("OEBPS/cover.jpg", b"cover")

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
