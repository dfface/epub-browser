import json
import contextlib
import io
import os
import tempfile
import threading
import time
import unittest
import zipfile
from pathlib import Path

from starlette.testclient import TestClient

from epub_browser.cli import ServerConfig
from epub_browser.migration import MigrationManager
from epub_browser.processor import EPUBProcessor
from epub_browser.runtime import RuntimeStatus, ServerLock, run_server
from epub_browser.server import create_app
from epub_browser.server_library import ReconcileSummary, ServerLibraryManager
from epub_browser.state import StateStore


class RuntimeStatusTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.public = self.root / "public"
        self.public.mkdir()
        (self.public / "index.html").write_text("library", encoding="utf-8")
        self.store = StateStore(self.root / "data" / "epub-browser.db")
        self.store.initialize()

    def test_ready_rejects_before_base_shell_and_reports_after_ready(self):
        status = RuntimeStatus()
        client = TestClient(create_app(self.public, self.store, status))

        self.assertEqual(client.get("/api/ready").status_code, 503)
        status.mark_ready()

        self.assertEqual(client.get("/api/ready").json()["state"], "ready")

    def test_degraded_health_reports_counts_without_private_paths(self):
        status = RuntimeStatus()
        status.mark_degraded(failed_books=2, queued_tasks=1)
        client = TestClient(create_app(self.public, self.store, status))

        payload = client.get("/api/health").json()

        self.assertEqual(payload["state"], "degraded")
        self.assertEqual(payload["failed_books"], 2)
        self.assertEqual(payload["queued_tasks"], 1)
        self.assertNotIn(str(self.root), json.dumps(payload))

    def test_state_changes_are_rejected_until_ready(self):
        status = RuntimeStatus()
        client = TestClient(create_app(self.public, self.store, status))

        response = client.put(
            "/api/reading-progress/book",
            json={"chapter_index": 1},
        )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["code"], "not_ready")

    def test_scanning_remains_available_after_base_shell_is_ready(self):
        status = RuntimeStatus()
        status.mark_scanning()
        status.mark_available()
        client = TestClient(create_app(self.public, self.store, status))

        self.assertEqual(client.get("/api/ready").status_code, 200)
        self.assertEqual(client.get("/api/ready").json()["state"], "scanning")
        response = client.put(
            "/api/reading-progress/book",
            json={"chapter_index": 1},
        )
        self.assertEqual(response.status_code, 200)


class ServerRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.sources = self.root / "sources"
        self.sources.mkdir()
        self.server_dir = self.root / "server"

    def test_second_lock_for_same_server_directory_returns_status_five(self):
        self.server_dir.mkdir()
        lock = ServerLock(self.server_dir)
        lock.acquire()
        self.addCleanup(lock.release)
        config = ServerConfig(
            sources=(self.sources,),
            server_dir=self.server_dir,
            ephemeral=False,
            no_browser=True,
        )

        status = run_server(config, server_factory=_ReturningServer)

        self.assertEqual(status, 5)

    def test_inactive_lock_metadata_is_reused_without_unlinking(self):
        self.server_dir.mkdir()
        lock_path = self.server_dir / ".server.lock"
        lock_path.write_text('{"pid":999999,"token":"stale"}', encoding="utf-8")
        original_inode = lock_path.stat().st_ino

        lock = ServerLock(self.server_dir)
        lock.acquire()
        lock.release()

        self.assertEqual(lock_path.stat().st_ino, original_inode)
        payload = json.loads(lock_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["pid"], os.getpid())

    def test_persistent_shutdown_keeps_data_and_public_cache(self):
        config = ServerConfig(
            sources=(self.sources,),
            server_dir=self.server_dir,
            ephemeral=False,
            no_browser=True,
        )

        status = run_server(config, server_factory=_ReturningServer)

        self.assertEqual(status, 0)
        self.assertTrue((self.server_dir / "data" / "epub-browser.db").is_file())
        self.assertTrue((self.server_dir / "cache" / "public" / "index.html").is_file())
        self.assertTrue((self.server_dir / ".server.lock").is_file())

    def test_success_without_log_prints_only_server_url(self):
        config = ServerConfig(
            sources=(self.sources,),
            server_dir=self.server_dir,
            ephemeral=False,
            no_browser=True,
        )

        with (
            contextlib.redirect_stdout(io.StringIO()) as stdout,
            contextlib.redirect_stderr(io.StringIO()) as stderr,
        ):
            status = run_server(config, server_factory=_ReturningServer)

        self.assertEqual(status, 0)
        self.assertEqual(
            stdout.getvalue(),
            "Server available at: http://127.0.0.1:8000/\n",
        )
        self.assertEqual(stderr.getvalue(), "")

    def test_keyboard_interrupt_is_a_clean_normal_shutdown(self):
        config = ServerConfig(
            sources=(self.sources,),
            server_dir=self.server_dir,
            ephemeral=False,
            no_browser=True,
        )

        with (
            contextlib.redirect_stdout(io.StringIO()) as stdout,
            contextlib.redirect_stderr(io.StringIO()) as stderr,
        ):
            status = run_server(config, server_factory=_InterruptingServer)

        self.assertEqual(status, 0)
        self.assertEqual(
            stdout.getvalue(),
            "Server available at: http://127.0.0.1:8000/\n",
        )
        self.assertEqual(stderr.getvalue(), "")

    def test_keyboard_interrupt_does_not_wait_for_slow_initial_conversion(self):
        source = self.sources / "slow.epub"
        _write_runtime_epub(source)
        _BlockingProcessor.reset()
        config = ServerConfig(
            sources=(self.sources,),
            server_dir=self.server_dir,
            ephemeral=False,
            no_browser=True,
        )

        started_at = time.monotonic()
        try:
            status = run_server(
                config,
                server_factory=_InterruptWhenConversionStarts,
                library_factory=_blocking_library_factory,
            )
            elapsed = time.monotonic() - started_at
        finally:
            _BlockingProcessor.release.set()
            _BlockingProcessor.cleaned.wait(timeout=5)

        self.assertEqual(status, 0)
        self.assertLess(elapsed, 1.0)

    def test_interrupted_initial_scan_does_not_retire_legacy_public_backup(self):
        source = self.sources / "slow.epub"
        _write_runtime_epub(source)
        migration = MigrationManager(self.server_dir, None)
        result = migration.prepare_data()
        state = json.loads(result.state_path.read_text(encoding="utf-8"))
        state["layout_phase"] = "retired"
        result.state_path.write_text(json.dumps(state), encoding="utf-8")
        legacy_public = self.server_dir / "cache" / "legacy-public"
        legacy_public.mkdir(parents=True)
        (legacy_public / "index.html").write_text("legacy", encoding="utf-8")
        _BlockingProcessor.reset()
        config = ServerConfig(
            sources=(self.sources,),
            server_dir=self.server_dir,
            ephemeral=False,
            no_browser=True,
        )

        try:
            status = run_server(
                config,
                server_factory=_InterruptWhenConversionStarts,
                library_factory=_blocking_library_factory,
            )
        finally:
            _BlockingProcessor.release.set()
            _BlockingProcessor.cleaned.wait(timeout=5)

        final_state = json.loads(result.state_path.read_text(encoding="utf-8"))
        self.assertEqual(status, 0)
        self.assertEqual(final_state["layout_phase"], "retired")
        self.assertTrue((legacy_public / "index.html").is_file())

    def test_bind_failure_does_not_report_availability_or_open_browser(self):
        opened = []
        config = ServerConfig(
            sources=(self.sources,),
            server_dir=self.server_dir,
            ephemeral=False,
            no_browser=False,
        )

        with (
            contextlib.redirect_stdout(io.StringIO()) as stdout,
            contextlib.redirect_stderr(io.StringIO()) as stderr,
        ):
            status = run_server(
                config,
                server_factory=_BindFailingServer,
                browser_opener=opened.append,
            )

        self.assertEqual(status, 5)
        self.assertEqual(stdout.getvalue(), "")
        self.assertEqual(opened, [])
        self.assertIn("failed to bind or start", stderr.getvalue())

    def test_ephemeral_shutdown_removes_only_created_temporary_root(self):
        ephemeral_root = self.root / "ephemeral-runtime"
        config = ServerConfig(
            sources=(self.sources,),
            server_dir=None,
            ephemeral=True,
            no_browser=True,
        )

        status = run_server(
            config,
            server_factory=_ReturningServer,
            ephemeral_root_factory=lambda: ephemeral_root,
        )

        self.assertEqual(status, 0)
        self.assertFalse(ephemeral_root.exists())
        self.assertTrue(self.sources.is_dir())

    def test_legacy_keep_files_preserves_ephemeral_root(self):
        ephemeral_root = self.root / "retained-runtime"
        config = ServerConfig(
            sources=(self.sources,),
            server_dir=None,
            ephemeral=True,
            no_browser=True,
            retain_legacy_temporary_dir=True,
            legacy_invocation=True,
        )

        with contextlib.redirect_stdout(io.StringIO()) as stdout:
            status = run_server(
                config,
                server_factory=_ReturningServer,
                ephemeral_root_factory=lambda: ephemeral_root,
            )

        self.assertEqual(status, 0)
        self.assertTrue((ephemeral_root / "cache" / "public" / "index.html").is_file())
        self.assertIn(f"Server files retained at: {ephemeral_root.resolve()}", stdout.getvalue())

    def test_http_shell_starts_while_initial_reconciliation_runs(self):
        _BlockingLibrary.reset()
        _InspectingServer.reset()
        config = ServerConfig(
            sources=(self.sources,),
            server_dir=self.server_dir,
            ephemeral=False,
            no_browser=True,
        )

        status = run_server(
            config,
            server_factory=_InspectingServer,
            library_factory=_BlockingLibrary,
        )

        self.assertEqual(status, 0)
        self.assertEqual(_InspectingServer.states, ["scanning", "ready"])


class _ReturningServer:
    def __init__(self, config):
        self.config = config
        self.should_exit = False
        self.started = True

    def run(self):
        return None


class _InterruptingServer(_ReturningServer):
    def run(self):
        raise KeyboardInterrupt()


class _BindFailingServer(_ReturningServer):
    def __init__(self, config):
        super().__init__(config)
        self.started = False

    def run(self):
        raise SystemExit(1)


class _InterruptWhenConversionStarts(_ReturningServer):
    def run(self):
        if not _BlockingProcessor.started.wait(timeout=5):
            raise RuntimeError("slow conversion did not start")
        raise KeyboardInterrupt()


class _BlockingProcessor(EPUBProcessor):
    started = threading.Event()
    release = threading.Event()
    cleaned = threading.Event()

    @classmethod
    def reset(cls):
        cls.started.clear()
        cls.release.clear()
        cls.cleaned.clear()

    def convert(self):
        self.started.set()
        self.release.wait(timeout=2)
        return super().convert()

    def cleanup(self):
        try:
            super().cleanup()
        finally:
            self.cleaned.set()


def _blocking_library_factory(**kwargs):
    return ServerLibraryManager(
        converter_factory=_BlockingProcessor,
        max_workers=1,
        **kwargs,
    )


class _BlockingLibrary:
    started = threading.Event()
    release = threading.Event()
    completed = threading.Event()

    @classmethod
    def reset(cls):
        cls.started.clear()
        cls.release.clear()
        cls.completed.clear()

    def __init__(self, *, server_dir, **kwargs):
        self.public_dir = Path(server_dir) / "cache" / "public"
        self.on_reconcile_started = None
        self.on_reconciled = None

    def prepare_public_shell(self):
        self.public_dir.mkdir(parents=True, exist_ok=True)
        (self.public_dir / "index.html").write_text("library", encoding="utf-8")

    def reconcile(self):
        if self.on_reconcile_started:
            self.on_reconcile_started()
        self.started.set()
        if not self.release.wait(timeout=5):
            raise RuntimeError("test reconciliation was not released")
        summary = ReconcileSummary(0, 0, 0, (), ())
        if self.on_reconciled:
            self.on_reconciled(summary)
        self.completed.set()
        return summary

    def shutdown(self):
        return None


class _InspectingServer:
    states = []

    @classmethod
    def reset(cls):
        cls.states = []

    def __init__(self, config):
        self.config = config
        self.should_exit = False
        self.started = True

    def run(self):
        self.assert_started()
        client = TestClient(self.config.app)
        self.states.append(client.get("/api/health").json()["state"])
        _BlockingLibrary.release.set()
        if not _BlockingLibrary.completed.wait(timeout=5):
            raise RuntimeError("test reconciliation did not complete")
        self.states.append(client.get("/api/health").json()["state"])

    @staticmethod
    def assert_started():
        if not _BlockingLibrary.started.wait(timeout=5):
            raise RuntimeError("server started before reconciliation worker")


def _write_runtime_epub(path):
    container = """<?xml version="1.0"?>
<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0">
  <rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles>
</container>
"""
    package = """<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="book-id">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="book-id">urn:test:runtime-slow</dc:identifier>
    <dc:title>Slow Book</dc:title><dc:creator>Author</dc:creator><dc:language>en</dc:language>
  </metadata>
  <manifest><item id="chapter" href="chapter.xhtml" media-type="application/xhtml+xml"/></manifest>
  <spine><itemref idref="chapter"/></spine>
</package>
"""
    chapter = """<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml"><body><p>Slow</p></body></html>
"""
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mimetype", "application/epub+zip")
        archive.writestr("META-INF/container.xml", container)
        archive.writestr("OEBPS/content.opf", package)
        archive.writestr("OEBPS/chapter.xhtml", chapter)


if __name__ == "__main__":
    unittest.main()
