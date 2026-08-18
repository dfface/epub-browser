import json
import contextlib
import io
import os
import tempfile
import threading
import unittest
from pathlib import Path

from starlette.testclient import TestClient

from epub_browser.cli import ServerConfig
from epub_browser.runtime import RuntimeStatus, ServerLock, run_server
from epub_browser.server import create_app
from epub_browser.server_library import ReconcileSummary
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

    def run(self):
        return None


class _InterruptingServer(_ReturningServer):
    def run(self):
        raise KeyboardInterrupt()


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


if __name__ == "__main__":
    unittest.main()
