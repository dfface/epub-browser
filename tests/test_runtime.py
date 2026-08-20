import json
import contextlib
import io
import os
import re
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock
import zipfile
from pathlib import Path

from starlette.testclient import TestClient

from epub_browser.auth import (
    AuthConfig,
    AuthService,
    BootstrapCredentials,
    ServerAuthOptions,
    verify_password,
)
from epub_browser.cli import ServerConfig
from epub_browser.library_progress import LibraryProgressBroker
from epub_browser.migration import MigrationManager
from epub_browser.processor import EPUBProcessor
from epub_browser.reporting import Reporter
from epub_browser.runtime import (
    RuntimeStatus,
    ServerLock,
    resolve_bootstrap_credentials,
    run_server,
)
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
        self.store.initialize(bootstrap=BootstrapCredentials("owner", "secret"))
        self.auth_config = AuthConfig.from_values([], None, None)
        self.auth_service = AuthService(self.store, self.auth_config)

    def _client(self, status):
        client = TestClient(
            create_app(
                self.public,
                self.store,
                auth_service=self.auth_service,
                status=status,
            )
        )
        self.addCleanup(client.close)
        login = client.post(
            "/login",
            data={"username": "owner", "password": "secret"},
            follow_redirects=False,
        )
        self.assertEqual(login.status_code, 303)
        session = client.get("/api/session")
        self.assertEqual(session.status_code, 200)
        client.headers[self.auth_config.csrf_header_name] = session.json()[
            "csrf_token"
        ]
        return client

    def test_ready_rejects_before_base_shell_and_reports_after_ready(self):
        status = RuntimeStatus()
        client = self._client(status)

        self.assertEqual(client.get("/api/ready").status_code, 503)
        status.mark_ready()

        self.assertEqual(client.get("/api/ready").json()["state"], "ready")

    def test_degraded_health_reports_counts_without_private_paths(self):
        status = RuntimeStatus()
        status.mark_degraded(failed_books=2, queued_tasks=1)
        client = self._client(status)

        payload = client.get("/api/health").json()

        self.assertEqual(payload["state"], "degraded")
        self.assertEqual(payload["failed_books"], 2)
        self.assertEqual(payload["queued_tasks"], 1)
        self.assertNotIn(str(self.root), json.dumps(payload))

    def test_state_changes_are_rejected_until_ready(self):
        status = RuntimeStatus()
        client = self._client(status)

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
        client = self._client(status)

        self.assertEqual(client.get("/api/ready").status_code, 200)
        self.assertEqual(client.get("/api/ready").json()["state"], "scanning")
        response = client.put(
            "/api/reading-progress/book",
            json={"chapter_index": 1},
        )
        self.assertEqual(response.status_code, 200)


class ServerBootstrapTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.sources = self.root / "sources"
        self.sources.mkdir()
        self.server_dir = self.root / "server"
        self.password_file = self.root / "admin-password"

    def _config(self, auth=ServerAuthOptions()):
        return ServerConfig(
            sources=(self.sources,),
            server_dir=self.server_dir,
            ephemeral=False,
            no_browser=True,
            auth=auth,
        )

    def test_first_persistent_start_without_credentials_enters_setup_mode_silently(self):
        with (
            mock.patch.dict(os.environ, {}, clear=True),
            contextlib.redirect_stdout(io.StringIO()) as stdout,
            contextlib.redirect_stderr(io.StringIO()) as stderr,
        ):
            result = run_server(self._config(), server_factory=_ReturningServer)

        store = StateStore(self.server_dir / "data" / "epub-browser.db")
        users = store.list_users()
        self.assertEqual(result, 0)
        self.assertFalse(store.has_administrator())
        self.assertEqual(len(users), 1)
        self.assertFalse(users[0].enabled)
        self.assertEqual(stdout.getvalue(), "")
        self.assertEqual(stderr.getvalue(), "")

    def test_partial_unattended_credentials_fail_closed_without_printing_secret(self):
        with (
            mock.patch.dict(
                os.environ,
                {"EPUB_BROWSER_ADMIN_PASSWORD": "secret-value"},
                clear=True,
            ),
            contextlib.redirect_stderr(io.StringIO()) as stderr,
        ):
            result = run_server(self._config(), server_factory=_ReturningServer)

        self.assertEqual(result, 5)
        self.assertIn("administrator credentials are required", stderr.getvalue())
        self.assertNotIn("secret-value", stderr.getvalue())

    def test_library_publication_waits_until_web_setup_completes(self):
        prepared = threading.Event()
        reconciled = threading.Event()
        responses = {}

        class SetupLibrary:
            def __init__(library, *, server_dir, **kwargs):
                library.public_dir = Path(server_dir) / "cache" / "public"
                library.on_reconcile_started = None
                library.on_reconciled = None

            def prepare_public_shell(library):
                library.public_dir.mkdir(parents=True, exist_ok=True)
                (library.public_dir / "index.html").write_text(
                    "private library",
                    encoding="utf-8",
                )
                prepared.set()

            def reconcile(library):
                if library.on_reconcile_started:
                    library.on_reconcile_started()
                summary = ReconcileSummary(0, 0, 0, (), ())
                if library.on_reconciled:
                    library.on_reconciled(summary)
                reconciled.set()
                return summary

            def request_stop(library):
                return None

            def shutdown(library):
                return None

        class SetupServer(_ReturningServer):
            def run(server):
                with TestClient(server.config.app, follow_redirects=False) as client:
                    responses["before"] = client.get("/")
                    if not prepared.is_set() or reconciled.is_set():
                        raise RuntimeError("setup boundary did not defer library scan")
                    setup_page = client.get("/setup")
                    nonce = re.search(
                        r'name="setup_nonce" value="([^"]+)"',
                        setup_page.text,
                    ).group(1)
                    responses["setup"] = client.post(
                        "/setup",
                        data={
                            "setup_nonce": nonce,
                            "username": "owner",
                            "password": "web-secret",
                            "password_confirmation": "web-secret",
                        },
                    )
                    responses["after"] = client.get("/")
                    if not reconciled.wait(timeout=5):
                        raise RuntimeError("library was not reconciled after setup")

        with mock.patch.dict(os.environ, {}, clear=True):
            result = run_server(
                self._config(),
                server_factory=SetupServer,
                library_factory=SetupLibrary,
            )

        self.assertEqual(result, 0)
        self.assertEqual(responses["before"].status_code, 303)
        self.assertEqual(responses["before"].headers["location"], "/setup")
        self.assertEqual(responses["setup"].status_code, 303)
        self.assertEqual(responses["after"].text, "private library")

    def test_forwarded_allow_ips_cannot_rewrite_the_proxy_trust_peer(self):
        observed = {}
        config = self._config(
            ServerAuthOptions(
                trusted_proxy_cidrs=("10.0.0.0/8",),
                proxy_subject_header="X-Remote-User",
                proxy_issuer="https://sso.example",
            )
        )

        class PeerInspectingServer(_ReturningServer):
            def run(server):
                observed["proxy_headers"] = server.config.proxy_headers
                server.config.load()
                with TestClient(
                    server.config.loaded_app,
                    client=("203.0.113.9", 4321),
                    follow_redirects=False,
                ) as client:
                    login = client.post(
                        "/login",
                        data={"username": "owner", "password": "secret"},
                    )
                    session = client.get("/api/session").json()
                    response = client.post(
                        "/api/identity/link",
                        json={"username": "owner", "password": "secret"},
                        headers={
                            "X-Forwarded-For": "10.1.2.3",
                            "X-Remote-User": "spoofed-subject",
                            "X-CSRF-Token": session["csrf_token"],
                        },
                    )
                    observed["login"] = login.status_code
                    observed["link"] = response.status_code
                    observed["code"] = response.json().get("code")

        with mock.patch.dict(
            os.environ,
            {
                "EPUB_BROWSER_ADMIN_USERNAME": "owner",
                "EPUB_BROWSER_ADMIN_PASSWORD": "secret",
                "FORWARDED_ALLOW_IPS": "*",
            },
            clear=True,
        ):
            result = run_server(config, server_factory=PeerInspectingServer)

        self.assertEqual(result, 0)
        self.assertFalse(observed["proxy_headers"])
        self.assertEqual(observed["login"], 303)
        self.assertEqual(observed["link"], 400)
        self.assertEqual(observed["code"], "proxy_identity_required")

    def test_empty_password_file_environment_setting_uses_plaintext_fallback(self):
        credentials = resolve_bootstrap_credentials(
            self._config(),
            {
                "EPUB_BROWSER_ADMIN_USERNAME": "admin",
                "EPUB_BROWSER_ADMIN_PASSWORD_FILE": "",
                "EPUB_BROWSER_ADMIN_PASSWORD": "environment-secret",
            },
        )

        self.assertEqual(credentials.username, "admin")
        self.assertEqual(credentials.password, "environment-secret")

    def test_runtime_reads_password_file_once_and_bootstraps_admin(self):
        self.password_file.write_text("secret-value\n", encoding="utf-8")
        config = self._config(
            ServerAuthOptions(
                admin_username="admin",
                admin_password_file=self.password_file,
            )
        )

        with mock.patch.dict(os.environ, {}, clear=True):
            result = run_server(config, server_factory=_ReturningServer)

        administrator = StateStore(
            self.server_dir / "data" / "epub-browser.db"
        ).get_user_by_username("admin")
        self.assertEqual(result, 0)
        self.assertTrue(administrator.is_admin)
        self.assertTrue(verify_password(administrator.password_hash, "secret-value"))

    def test_password_file_removes_exactly_one_trailing_newline_and_wins_over_env(self):
        self.password_file.write_text("file-secret\n\n", encoding="utf-8")
        config = self._config(
            ServerAuthOptions(
                admin_username="admin",
                admin_password_file=self.password_file,
            )
        )

        with mock.patch.dict(
            os.environ,
            {"EPUB_BROWSER_ADMIN_PASSWORD": "environment-secret"},
            clear=True,
        ):
            result = run_server(config, server_factory=_ReturningServer)

        administrator = StateStore(
            self.server_dir / "data" / "epub-browser.db"
        ).get_user_by_username("admin")
        self.assertEqual(result, 0)
        self.assertTrue(verify_password(administrator.password_hash, "file-secret\n"))
        self.assertFalse(verify_password(administrator.password_hash, "file-secret"))
        self.assertFalse(
            verify_password(administrator.password_hash, "environment-secret")
        )

    def test_empty_or_unreadable_password_file_fails_closed(self):
        for password_path in (self.password_file, self.root):
            with self.subTest(password_path=password_path):
                self.password_file.write_text("", encoding="utf-8")
                config = self._config(
                    ServerAuthOptions(
                        admin_username="admin",
                        admin_password_file=password_path,
                    )
                )
                with (
                    mock.patch.dict(
                        os.environ,
                        {"EPUB_BROWSER_ADMIN_PASSWORD": "fallback-secret"},
                        clear=True,
                    ),
                    contextlib.redirect_stderr(io.StringIO()) as stderr,
                ):
                    result = run_server(config, server_factory=_ReturningServer)

                self.assertEqual(result, 5)
                self.assertFalse(
                    (self.server_dir / "data" / "epub-browser.db").is_file()
                )
                self.assertNotIn("fallback-secret", stderr.getvalue())

    def test_restart_does_not_read_or_require_bootstrap_secret(self):
        config = self._config(
            ServerAuthOptions(
                admin_username="admin",
                admin_password_file=self.root / "removed-password-file",
            )
        )
        first_environment = {
            "EPUB_BROWSER_ADMIN_USERNAME": "admin",
            "EPUB_BROWSER_ADMIN_PASSWORD": "first-start-secret",
        }
        environment_config = self._config()
        with mock.patch.dict(os.environ, first_environment, clear=True):
            first = run_server(
                environment_config,
                server_factory=_ReturningServer,
            )

        with mock.patch.dict(os.environ, {}, clear=True):
            second = run_server(config, server_factory=_ReturningServer)

        self.assertEqual(first, 0)
        self.assertEqual(second, 0)

    def test_runtime_passes_proxy_and_cookie_configuration_to_auth_service(self):
        self.password_file.write_text("secret-value\n", encoding="utf-8")
        config = self._config(
            ServerAuthOptions(
                admin_username="admin",
                admin_password_file=self.password_file,
                trusted_proxy_cidrs=("10.0.0.0/8",),
                proxy_subject_header="X-Remote-User",
                proxy_display_name_header="X-Remote-Name",
                proxy_issuer="https://sso.example",
                cookie_secure=True,
            )
        )
        captured = {}
        real_create_app = create_app

        def capture_create_app(*args, auth_service, **kwargs):
            captured["auth_service"] = auth_service
            return real_create_app(
                *args,
                auth_service=auth_service,
                **kwargs,
            )

        with (
            mock.patch.dict(os.environ, {}, clear=True),
            mock.patch(
                "epub_browser.runtime.create_app",
                side_effect=capture_create_app,
            ),
        ):
            result = run_server(config, server_factory=_ReturningServer)

        auth_service = captured["auth_service"]
        self.assertEqual(result, 0)
        self.assertIsInstance(auth_service, AuthService)
        self.assertTrue(auth_service.config.cookie_secure)
        self.assertTrue(auth_service.config.is_trusted_proxy("10.2.3.4"))
        self.assertEqual(
            auth_service.config.proxy_subject_header,
            "X-Remote-User",
        )
        self.assertEqual(auth_service.config.proxy_issuer, "https://sso.example")


class ServerRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.sources = self.root / "sources"
        self.sources.mkdir()
        self.server_dir = self.root / "server"
        self.bootstrap = BootstrapCredentials("owner", "secret")
        self.runtime_environment = mock.patch.dict(
            os.environ,
            {
                "EPUB_BROWSER_ADMIN_USERNAME": self.bootstrap.username,
                "EPUB_BROWSER_ADMIN_PASSWORD": self.bootstrap.password,
            },
            clear=True,
        )
        self.runtime_environment.start()
        self.addCleanup(self.runtime_environment.stop)

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

    def test_non_tty_server_does_not_print_internal_url(self):
        config = ServerConfig(
            sources=(self.sources,),
            server_dir=self.server_dir,
            ephemeral=False,
            no_browser=True,
        )

        with (
            contextlib.redirect_stdout(io.StringIO()) as stdout,
            contextlib.redirect_stderr(io.StringIO()) as stderr,
            mock.patch.object(sys.stdout, "isatty", return_value=False),
        ):
            status = run_server(config, server_factory=_ReturningServer)

        self.assertEqual(status, 0)
        self.assertEqual(stdout.getvalue(), "")
        self.assertEqual(stderr.getvalue(), "")

    def test_tty_server_prints_bound_url_once(self):
        config = ServerConfig(
            sources=(self.sources,),
            server_dir=self.server_dir,
            ephemeral=False,
            no_browser=True,
        )

        with (
            contextlib.redirect_stdout(io.StringIO()) as stdout,
            contextlib.redirect_stderr(io.StringIO()) as stderr,
            mock.patch.object(sys.stdout, "isatty", return_value=True),
        ):
            status = run_server(config, server_factory=_ReturningServer)

        self.assertEqual(status, 0)
        self.assertEqual(
            stdout.getvalue(),
            "Server available at: http://127.0.0.1:8000/\n",
        )
        self.assertEqual(stderr.getvalue(), "")

    def test_log_mode_reports_bound_url_to_stderr_in_non_tty(self):
        config = ServerConfig(
            sources=(self.sources,),
            server_dir=self.server_dir,
            ephemeral=False,
            no_browser=True,
            log=True,
        )

        with (
            contextlib.redirect_stdout(io.StringIO()) as stdout,
            contextlib.redirect_stderr(io.StringIO()) as stderr,
            mock.patch.object(sys.stdout, "isatty", return_value=False),
        ):
            status = run_server(
                config,
                reporter=Reporter(True),
                server_factory=_ReturningServer,
            )

        self.assertEqual(status, 0)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("Server available at: http://127.0.0.1:8000/", stderr.getvalue())

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
        self.assertEqual(stdout.getvalue(), "")
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

    def test_setup_watcher_does_not_start_when_admin_probe_fails(self):
        poll_failed = threading.Event()
        watcher_started = threading.Event()
        probe_count = 0

        def has_administrator(_store):
            nonlocal probe_count
            probe_count += 1
            if probe_count == 1:
                return False
            poll_failed.set()
            raise sqlite3.OperationalError("admin probe failed")

        class HoldingServer(_ReturningServer):
            def run(server):
                if not poll_failed.wait(timeout=5):
                    raise RuntimeError("admin probe did not run")
                watcher_started.wait(timeout=0.2)

        def watcher_factory(*args, **kwargs):
            watcher_started.set()
            return mock.Mock()

        config = ServerConfig(
            sources=(self.sources,),
            server_dir=self.server_dir,
            ephemeral=False,
            no_browser=True,
            watch=True,
        )
        with (
            mock.patch.object(
                StateStore,
                "has_administrator",
                new=has_administrator,
            ),
            contextlib.redirect_stderr(io.StringIO()),
        ):
            status = run_server(
                config,
                server_factory=HoldingServer,
                watcher_factory=watcher_factory,
            )

        self.assertEqual(status, 0)
        self.assertFalse(watcher_started.is_set())

    def test_interrupted_initial_scan_does_not_retire_legacy_public_backup(self):
        source = self.sources / "slow.epub"
        _write_runtime_epub(source)
        migration = MigrationManager(
            self.server_dir,
            None,
            bootstrap=self.bootstrap,
        )
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

    def test_runtime_shares_progress_broker_between_library_and_app(self):
        captured = {}
        config = ServerConfig(
            sources=(self.sources,),
            server_dir=self.server_dir,
            ephemeral=False,
            no_browser=True,
        )

        class Library:
            def __init__(self, *, server_dir, progress_broker, **kwargs):
                captured["library_broker"] = progress_broker
                self.public_dir = Path(server_dir) / "cache" / "public"
                self.on_reconcile_started = None
                self.on_reconciled = None

            def prepare_public_shell(self):
                self.public_dir.mkdir(parents=True, exist_ok=True)
                (self.public_dir / "index.html").write_text("library", encoding="utf-8")

            def reconcile(self):
                return ReconcileSummary(0, 0, 0, (), ())

            def request_stop(self):
                return None

            def shutdown(self):
                return None

        def fake_create_app(*args, progress_broker, auth_service, **kwargs):
            captured["app_broker"] = progress_broker
            captured["auth_service"] = auth_service
            return create_app(
                *args,
                auth_service=auth_service,
                **kwargs,
            )

        with mock.patch("epub_browser.runtime.create_app", side_effect=fake_create_app):
            status = run_server(
                config,
                server_factory=_ReturningServer,
                library_factory=Library,
            )

        self.assertEqual(status, 0)
        self.assertIsInstance(captured["library_broker"], LibraryProgressBroker)
        self.assertIs(captured["library_broker"], captured["app_broker"])
        self.assertIsInstance(captured["auth_service"], AuthService)

    def test_runtime_passes_book_id_storage_to_library_manager(self):
        captured = {}
        config = ServerConfig(
            sources=(self.sources,),
            server_dir=self.server_dir,
            ephemeral=False,
            no_browser=True,
            book_id_storage="embedded",
        )

        class Library:
            def __init__(self, *, server_dir, book_id_storage, **kwargs):
                captured["book_id_storage"] = book_id_storage
                self.public_dir = Path(server_dir) / "cache" / "public"
                self.on_reconcile_started = None
                self.on_reconciled = None

            def prepare_public_shell(self):
                self.public_dir.mkdir(parents=True, exist_ok=True)
                (self.public_dir / "index.html").write_text(
                    "library", encoding="utf-8"
                )

            def reconcile(self):
                return ReconcileSummary(0, 0, 0, (), ())

            def request_stop(self):
                return None

            def shutdown(self):
                return None

        status = run_server(
            config,
            server_factory=_ReturningServer,
            library_factory=Library,
        )
        self.assertEqual(status, 0)
        self.assertEqual(captured["book_id_storage"], "embedded")


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
        login = client.post(
            "/login",
            data={"username": "owner", "password": "secret"},
            follow_redirects=False,
        )
        if login.status_code != 303:
            raise RuntimeError("runtime HTTP fixture could not authenticate")
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
