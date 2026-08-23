import errno
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import threading
import time
import uuid
import webbrowser
from pathlib import Path
from typing import Callable, Mapping, Optional, Union

import uvicorn

try:
    import fcntl
except ImportError:  # pragma: no cover - exercised on Windows
    fcntl = None

try:
    import msvcrt
except ImportError:  # pragma: no cover - exercised on POSIX
    msvcrt = None

from .auth import AuthConfig, AuthService, BootstrapCredentials
from .cli import ServerConfig
from .library_progress import LibraryProgressBroker
from .migration import MigrationError, MigrationManager
from .reporting import Reporter
from .server import create_app
from .server_library import ReconcileSummary, ServerLibraryManager
from .state import DB_SCHEMA_VERSION, StateStore
from .watch import EPUBWatcher


class RuntimeStatus:
    def __init__(self):
        self._lock = threading.Lock()
        self._state = "starting"
        self._failed_books = 0
        self._queued_tasks = 0
        self._available = False

    def mark_migrating(self):
        self._set("migrating", 0, 0, available=False)

    def mark_setup_required(self):
        self._set("setup_required", 0, 0, available=False)

    def mark_scanning(self):
        self._set("scanning", 0, 0)

    def mark_available(self):
        with self._lock:
            self._available = True

    def mark_ready(self):
        self._set("ready", 0, 0, available=True)

    def mark_degraded(self, failed_books: int, queued_tasks: int = 0):
        self._set("degraded", failed_books, queued_tasks, available=True)

    def _set(
        self,
        state: str,
        failed_books: int,
        queued_tasks: int,
        available: Optional[bool] = None,
    ):
        with self._lock:
            self._state = state
            self._failed_books = max(0, int(failed_books))
            self._queued_tasks = max(0, int(queued_tasks))
            if available is not None:
                self._available = available

    def is_ready(self) -> bool:
        with self._lock:
            return self._available

    def snapshot(self):
        with self._lock:
            return {
                "state": self._state,
                "failed_books": self._failed_books,
                "queued_tasks": self._queued_tasks,
                "database_schema_version": DB_SCHEMA_VERSION,
            }


class ServerLockError(RuntimeError):
    pass


class _DescriptorLockUnavailable(RuntimeError):
    pass


def read_secret_file(path: Optional[Union[Path, str]]) -> Optional[str]:
    if path is None:
        return None
    try:
        secret = Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise ServerLockError(
            "Server administrator password file is unreadable"
        ) from error
    if secret.endswith("\n"):
        secret = secret[:-1]
    if not secret:
        raise ServerLockError("Server administrator password file is empty")
    return secret


def resolve_bootstrap_credentials(
    config: ServerConfig,
    environ: Mapping[str, str],
) -> BootstrapCredentials:
    username = config.auth.admin_username or environ.get(
        "EPUB_BROWSER_ADMIN_USERNAME"
    )
    password_file = config.auth.admin_password_file or environ.get(
        "EPUB_BROWSER_ADMIN_PASSWORD_FILE"
    )
    password = (
        read_secret_file(password_file)
        if password_file
        else environ.get("EPUB_BROWSER_ADMIN_PASSWORD")
    )
    if not username or not password:
        raise ServerLockError(
            "Server administrator credentials are required for first startup"
        )
    return BootstrapCredentials(username, password)


def resolve_optional_bootstrap_credentials(
    config: ServerConfig,
    environ: Mapping[str, str],
) -> Optional[BootstrapCredentials]:
    username = config.auth.admin_username or environ.get(
        "EPUB_BROWSER_ADMIN_USERNAME"
    )
    password_file = config.auth.admin_password_file or environ.get(
        "EPUB_BROWSER_ADMIN_PASSWORD_FILE"
    )
    password = environ.get("EPUB_BROWSER_ADMIN_PASSWORD")
    if not username and not password_file and not password:
        return None
    return resolve_bootstrap_credentials(config, environ)


def _persistent_database_needs_bootstrap(server_dir: Path) -> bool:
    data_database = server_dir / "data" / "epub-browser.db"
    if data_database.is_file():
        probe_path = data_database
    else:
        root_candidates = tuple(
            path
            for path in (
                server_dir / "epub-browser.db",
                server_dir / "annotations.db",
            )
            if path.is_file()
        )
        if len(root_candidates) > 1:
            return False
        if not root_candidates:
            return True
        probe_path = root_candidates[0]
    try:
        with sqlite3.connect(probe_path) as connection:
            schema_version = connection.execute(
                "PRAGMA user_version"
            ).fetchone()[0]
        if schema_version > DB_SCHEMA_VERSION:
            return False
        return not StateStore(probe_path).has_administrator()
    except sqlite3.DatabaseError:
        # MigrationManager owns corruption diagnostics and backup handling.
        return False


class ServerLock:
    def __init__(self, server_dir: Path):
        self.server_dir = Path(server_dir)
        self.path = self.server_dir / ".server.lock"
        self.token = uuid.uuid4().hex
        self._acquired = False
        self._descriptor = None

    def acquire(self) -> None:
        self.server_dir.mkdir(parents=True, exist_ok=True)
        flags = os.O_RDWR | os.O_CREAT
        flags |= getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(self.path, flags, 0o600)
        try:
            self._lock_descriptor(descriptor)
        except _DescriptorLockUnavailable:
            os.close(descriptor)
            payload = self._read_existing_safely()
            pid = payload.get("pid")
            owner = f" by PID {pid}" if isinstance(pid, int) and pid > 0 else ""
            raise ServerLockError(
                f"Server directory is already in use{owner}: {self.server_dir}"
            ) from None

        try:
            os.fchmod(descriptor, 0o600)
            payload = json.dumps(
                {
                    "pid": os.getpid(),
                    "started_at": time.time(),
                    "token": self.token,
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            os.lseek(descriptor, 0, os.SEEK_SET)
            os.ftruncate(descriptor, 0)
            offset = 0
            while offset < len(payload):
                offset += os.write(descriptor, payload[offset:])
            os.fsync(descriptor)
        except Exception:
            self._unlock_descriptor(descriptor)
            os.close(descriptor)
            raise
        self._descriptor = descriptor
        self._acquired = True

    def release(self) -> None:
        if not self._acquired:
            return
        descriptor = self._descriptor
        try:
            if descriptor is not None:
                self._unlock_descriptor(descriptor)
        finally:
            if descriptor is not None:
                os.close(descriptor)
            self._descriptor = None
            self._acquired = False

    def _read_existing_safely(self):
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        if not isinstance(payload, dict):
            return {}
        return payload

    @staticmethod
    def _lock_descriptor(descriptor: int) -> None:
        if fcntl is not None:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise _DescriptorLockUnavailable() from error
            return
        os.lseek(descriptor, 0, os.SEEK_SET)
        if os.fstat(descriptor).st_size == 0:
            os.write(descriptor, b"\0")
            os.fsync(descriptor)
        os.lseek(descriptor, 0, os.SEEK_SET)
        try:  # pragma: no cover - exercised on Windows
            msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
        except OSError as error:  # pragma: no cover - exercised on Windows
            if error.errno in {errno.EACCES, errno.EAGAIN, errno.EDEADLK}:
                raise _DescriptorLockUnavailable() from error
            raise

    @staticmethod
    def _unlock_descriptor(descriptor: int) -> None:
        if fcntl is not None:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            return
        os.lseek(descriptor, 0, os.SEEK_SET)
        msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)  # pragma: no cover


def run_server(
    config: ServerConfig,
    reporter: Optional[Reporter] = None,
    *,
    server_factory: Callable = uvicorn.Server,
    library_factory: Callable = ServerLibraryManager,
    watcher_factory: Callable = EPUBWatcher,
    browser_opener: Callable = webbrowser.open,
    ephemeral_root_factory: Optional[Callable[[], Path]] = None,
) -> int:
    active_reporter = reporter or Reporter(config.log)
    status = RuntimeStatus()
    manager = None
    watcher_thread = None
    initial_reconcile_thread = None
    watcher_stop = threading.Event()
    initial_reconcile_done = threading.Event()
    administrator_observed = threading.Event()
    lock = None
    ephemeral_root = None
    created_ephemeral_root = False
    progress_broker = LibraryProgressBroker()

    try:
        if config.ephemeral:
            if ephemeral_root_factory is None:
                ephemeral_root = Path(
                    tempfile.mkdtemp(prefix="epub-browser-server-")
                )
                created_ephemeral_root = True
            else:
                ephemeral_root = Path(ephemeral_root_factory())
                if ephemeral_root.exists():
                    raise ServerLockError(
                        f"Ephemeral Server root already exists: {ephemeral_root}"
                    )
                ephemeral_root.mkdir(parents=True)
                created_ephemeral_root = True
            server_dir = ephemeral_root
        else:
            if config.server_dir is None:
                raise ServerLockError("Persistent Server mode requires --server-dir")
            server_dir = Path(config.server_dir).expanduser().absolute()

        lock = ServerLock(server_dir)
        lock.acquire()
        migration_manager = None
        initial_layout_phase = None
        auth_config = AuthConfig.from_values(
            config.auth.trusted_proxy_cidrs,
            cookie_secure=bool(config.auth.cookie_secure),
        )

        if config.ephemeral:
            data_path = server_dir / "data" / "epub-browser.db"
            state_store = StateStore(data_path)
            bootstrap = (
                resolve_optional_bootstrap_credentials(config, os.environ)
                if not state_store.has_administrator()
                else None
            )
            state_store.initialize(bootstrap=bootstrap)
        else:
            status.mark_migrating()
            bootstrap = (
                resolve_optional_bootstrap_credentials(config, os.environ)
                if _persistent_database_needs_bootstrap(server_dir)
                else None
            )
            migration_manager = MigrationManager(
                server_dir,
                config.legacy_sync_dir,
                bootstrap=bootstrap,
            )
            migration_result = migration_manager.prepare_data()
            for warning in migration_result.warnings:
                active_reporter.notice(warning)
            state_store = StateStore(migration_result.database_path)
            initial_layout_phase = _migration_layout_phase(
                migration_result.state_path
            )

        manager = library_factory(
            server_dir=server_dir,
            sources=config.sources,
            state_store=state_store,
            migration_manager=migration_manager,
            reporter=active_reporter,
            progress_broker=progress_broker,
            book_id_storage=config.book_id_storage,
        )
        manager.on_reconcile_started = status.mark_scanning
        manager.on_reconciled = lambda summary: _update_runtime_status(
            status,
            summary,
        )
        setup_required = not state_store.has_administrator()
        manager.prepare_public_shell()
        if setup_required:
            status.mark_setup_required()
        else:
            status.mark_scanning()
            status.mark_available()

        def initial_reconcile():
            try:
                while not state_store.has_administrator():
                    if watcher_stop.wait(0.05):
                        return
                administrator_observed.set()
                if setup_required:
                    status.mark_available()
                summary: ReconcileSummary = manager.reconcile()
                if (
                    not summary.cancelled
                    and not summary.degraded
                    and migration_manager
                    and initial_layout_phase == "retired"
                ):
                    migration_manager.finish_legacy_public_retirement()
            except Exception as error:
                status.mark_degraded(1, 0)
                active_reporter.error(
                    f"Initial Server library reconciliation failed: {error}"
                )
            finally:
                initial_reconcile_done.set()

        initial_reconcile_thread = threading.Thread(
            target=initial_reconcile,
            name="EPUBInitialReconcile",
            daemon=True,
        )
        initial_reconcile_thread.start()

        if config.watch:
            def watch_after_initial_reconcile():
                initial_reconcile_done.wait()
                if (
                    watcher_stop.is_set()
                    or not administrator_observed.is_set()
                ):
                    return
                try:
                    watcher = watcher_factory(
                        config.sources,
                        manager,
                        reporter=active_reporter,
                    )
                    watcher.watch(watcher_stop)
                except Exception as error:
                    status.mark_degraded(1, 0)
                    active_reporter.error(f"Server source watcher failed: {error}")

            watcher_thread = threading.Thread(
                target=watch_after_initial_reconcile,
                name="EPUBWatcher",
                daemon=True,
            )
            watcher_thread.start()

        app = create_app(
            manager.public_dir,
            state_store=state_store,
            auth_service=AuthService(state_store, auth_config),
            status=status,
            sync_dir=config.legacy_sync_dir or server_dir,
            progress_broker=progress_broker,
        )
        uvicorn_config = uvicorn.Config(
            app,
            host=config.host,
            port=config.port,
            log_level="info" if config.log else "warning",
            access_log=config.log,
            proxy_headers=False,
        )
        server = server_factory(uvicorn_config)
        local_url = _local_url(config.host, config.port)
        availability_reported = threading.Event()
        availability_lock = threading.Lock()
        startup_monitor_stop = threading.Event()

        def report_availability():
            with availability_lock:
                if availability_reported.is_set():
                    return
                message = f"Server available at: {local_url}"
                if config.log:
                    active_reporter.notice(message)
                elif sys.stdout.isatty():
                    active_reporter.result(message)
                if not config.no_browser:
                    try:
                        browser_opener(local_url)
                    except Exception as error:
                        active_reporter.detail(f"Unable to open browser: {error}")
                availability_reported.set()

        def monitor_startup():
            while not startup_monitor_stop.wait(0.01):
                if getattr(server, "started", False):
                    report_availability()
                    return

        startup_monitor = threading.Thread(
            target=monitor_startup,
            name="UvicornStartupMonitor",
            daemon=True,
        )
        startup_monitor.start()
        try:
            server.run()
        finally:
            if getattr(server, "started", False):
                report_availability()
            startup_monitor_stop.set()
            startup_monitor.join(timeout=1)
        if (
            created_ephemeral_root
            and ephemeral_root is not None
            and config.retain_legacy_temporary_dir
        ):
            active_reporter.result(
                f"Server files retained at: {ephemeral_root.resolve()}"
            )
        return 0
    except MigrationError as error:
        active_reporter.error(f"Server data migration failed: {error}")
        return 3
    except (ServerLockError, PermissionError, OSError, ValueError) as error:
        active_reporter.error(f"Server startup failed: {error}")
        return 5
    except KeyboardInterrupt:
        return 0
    except SystemExit as error:
        if not error.code:
            return 0
        active_reporter.error("Server failed to bind or start")
        return 5
    except Exception as error:
        active_reporter.error(f"Server startup failed: {error}")
        return 5
    finally:
        watcher_stop.set()
        if manager is not None:
            request_stop = getattr(manager, "request_stop", None)
            if request_stop is not None:
                request_stop()
        if initial_reconcile_thread is not None:
            initial_reconcile_thread.join(timeout=1)
        if watcher_thread is not None:
            watcher_thread.join(timeout=5)
        if manager is not None:
            manager.shutdown()
        if lock is not None:
            lock.release()
        if (
            created_ephemeral_root
            and ephemeral_root is not None
            and not config.retain_legacy_temporary_dir
        ):
            shutil.rmtree(ephemeral_root, ignore_errors=True)


def _migration_layout_phase(state_path: Path) -> Optional[str]:
    try:
        payload = json.loads(Path(state_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload.get("layout_phase") if isinstance(payload, dict) else None


def _update_runtime_status(
    status: RuntimeStatus,
    summary: ReconcileSummary,
) -> None:
    if summary.degraded:
        status.mark_degraded(summary.failed, 0)
    else:
        status.mark_ready()


def _local_url(host: str, port: int) -> str:
    display_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    if ":" in display_host and not display_host.startswith("["):
        display_host = f"[{display_host}]"
    return f"http://{display_host}:{port}/"
