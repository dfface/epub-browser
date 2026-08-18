import json
import os
import shutil
import tempfile
import threading
import time
import uuid
import webbrowser
from pathlib import Path
from typing import Callable, Optional

import uvicorn

from .cli import ServerConfig
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

    def mark_migrating(self):
        self._set("migrating", 0, 0)

    def mark_scanning(self):
        self._set("scanning", 0, 0)

    def mark_ready(self):
        self._set("ready", 0, 0)

    def mark_degraded(self, failed_books: int, queued_tasks: int = 0):
        self._set("degraded", failed_books, queued_tasks)

    def _set(self, state: str, failed_books: int, queued_tasks: int):
        with self._lock:
            self._state = state
            self._failed_books = max(0, int(failed_books))
            self._queued_tasks = max(0, int(queued_tasks))

    def is_ready(self) -> bool:
        with self._lock:
            return self._state in {"ready", "degraded"}

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


class ServerLock:
    def __init__(self, server_dir: Path):
        self.server_dir = Path(server_dir)
        self.path = self.server_dir / ".server.lock"
        self.token = uuid.uuid4().hex
        self._acquired = False

    def acquire(self) -> None:
        self.server_dir.mkdir(parents=True, exist_ok=True)
        for _ in range(2):
            try:
                descriptor = os.open(
                    self.path,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                    0o600,
                )
            except FileExistsError:
                payload = self._read_existing()
                pid = payload.get("pid")
                if not isinstance(pid, int) or pid <= 0:
                    raise ServerLockError(
                        f"Server lock is unreadable; inspect and remove it if stale: {self.path}"
                    )
                if self._pid_is_alive(pid):
                    raise ServerLockError(
                        f"Server directory is already in use by PID {pid}: {self.server_dir}"
                    )
                try:
                    self.path.unlink()
                except FileNotFoundError:
                    pass
                continue
            try:
                payload = json.dumps(
                    {
                        "pid": os.getpid(),
                        "started_at": time.time(),
                        "token": self.token,
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
                os.write(descriptor, payload)
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            self._acquired = True
            return
        raise ServerLockError(f"Unable to acquire Server lock: {self.path}")

    def release(self) -> None:
        if not self._acquired:
            return
        try:
            payload = self._read_existing()
            if payload.get("token") == self.token:
                self.path.unlink(missing_ok=True)
        finally:
            self._acquired = False

    def _read_existing(self):
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ServerLockError(f"Unable to read Server lock {self.path}: {error}") from error
        if not isinstance(payload, dict):
            raise ServerLockError(f"Invalid Server lock payload: {self.path}")
        return payload

    @staticmethod
    def _pid_is_alive(pid: int) -> bool:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True


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
    watcher_stop = threading.Event()
    lock = None
    ephemeral_root = None
    created_ephemeral_root = False

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

        if config.ephemeral:
            data_path = server_dir / "data" / "epub-browser.db"
            state_store = StateStore(data_path)
            state_store.initialize()
        else:
            status.mark_migrating()
            migration_manager = MigrationManager(
                server_dir,
                config.legacy_sync_dir,
            )
            migration_result = migration_manager.prepare_data()
            for warning in migration_result.warnings:
                active_reporter.notice(warning)
            state_store = StateStore(migration_result.database_path)
            initial_layout_phase = _migration_layout_phase(
                migration_result.state_path
            )

        status.mark_scanning()
        manager = library_factory(
            server_dir=server_dir,
            sources=config.sources,
            state_store=state_store,
            migration_manager=migration_manager,
            reporter=active_reporter,
        )
        manager.prepare_public_shell()
        summary: ReconcileSummary = manager.reconcile()
        if summary.degraded:
            status.mark_degraded(summary.failed, 0)
        else:
            status.mark_ready()
            if migration_manager and initial_layout_phase == "retired":
                migration_manager.finish_legacy_public_retirement()

        if config.watch:
            watcher = watcher_factory(
                config.sources,
                manager,
                reporter=active_reporter,
            )
            watcher_thread = threading.Thread(
                target=watcher.watch,
                args=(watcher_stop,),
                name="EPUBWatcher",
                daemon=True,
            )
            watcher_thread.start()

        app = create_app(
            manager.public_dir,
            state_store=state_store,
            status=status,
            sync_dir=config.legacy_sync_dir or server_dir,
        )
        uvicorn_config = uvicorn.Config(
            app,
            host=config.host,
            port=config.port,
            log_level="info" if config.log else "warning",
            access_log=config.log,
        )
        server = server_factory(uvicorn_config)
        local_url = _local_url(config.host, config.port)
        active_reporter.result(f"Server available at: {local_url}")
        if not config.no_browser:
            try:
                browser_opener(local_url)
            except Exception as error:
                active_reporter.detail(f"Unable to open browser: {error}")
        server.run()
        return 0
    except MigrationError as error:
        active_reporter.error(f"Server data migration failed: {error}")
        return 3
    except (ServerLockError, PermissionError, OSError, ValueError) as error:
        active_reporter.error(f"Server startup failed: {error}")
        return 5
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


def _local_url(host: str, port: int) -> str:
    display_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    if ":" in display_host and not display_host.startswith("["):
        display_host = f"[{display_host}]"
    return f"http://{display_host}:{port}/"
