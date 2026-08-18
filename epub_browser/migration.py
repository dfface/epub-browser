import hashlib
import json
import os
import re
import shutil
import sqlite3
import tempfile
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .asset_publisher import PublishedAssets
from .processor import EPUBProcessor
from .reporting import Reporter
from .state import StateStore
from .urls import SiteURLs


MIGRATION_STATE_VERSION = 1
BOOKSHELF_PATTERN = re.compile(
    r"^epub-browser-bookshelf-(.+)-(\d+)\.json$"
)
LEGACY_PUBLIC_ARTIFACTS = (
    "index.html",
    "book-metadata.json",
    "sw.js",
    "assets",
    "book",
)


class MigrationError(RuntimeError):
    pass


class MigrationConflictError(MigrationError):
    pass


@dataclass(frozen=True)
class MigrationResult:
    database_path: Path
    state_path: Path
    backup_path: Optional[Path]
    imported_bookshelves: int
    legacy_book_ids: tuple[str, ...]
    warnings: tuple[str, ...] = ()


class MigrationManager:
    def __init__(
        self,
        server_dir: Path,
        legacy_sync_dir: Optional[Path],
    ):
        self.server_dir = Path(server_dir).expanduser().absolute()
        self.legacy_sync_dir = (
            Path(legacy_sync_dir).expanduser().absolute()
            if legacy_sync_dir
            else None
        )
        self.data_dir = self.server_dir / "data"
        self.database_path = self.data_dir / "epub-browser.db"
        self.state_path = self.data_dir / "migration-state.json"
        self.backups_dir = self.data_dir / "backups"
        self.cache_dir = self.server_dir / "cache"

    def prepare_data(self) -> MigrationResult:
        root_candidates = tuple(
            path
            for path in (
                self.server_dir / "epub-browser.db",
                self.server_dir / "annotations.db",
            )
            if path.is_file()
        )
        if not self.database_path.exists() and len(root_candidates) > 1:
            raise MigrationConflictError(
                "Conflicting legacy databases found; move one aside before retrying: "
                + ", ".join(str(path) for path in root_candidates)
            )

        candidate = root_candidates[0] if root_candidates else None
        if not self.database_path.exists() and candidate is not None:
            self._check_integrity(candidate)

        self.data_dir.mkdir(parents=True, exist_ok=True)
        with self._migration_lock():
            return self._prepare_locked(root_candidates)

    def _prepare_locked(self, root_candidates: tuple[Path, ...]) -> MigrationResult:
        warnings = []
        state = self._load_state()
        backup_path = self._state_backup_path(state)

        if self.database_path.is_file():
            self._check_integrity(self.database_path)
            self._initialize_database(self.database_path)
            self._check_integrity(self.database_path)
            if root_candidates:
                warnings.append(
                    "Authoritative data database already exists; legacy root database "
                    "was left untouched: "
                    + ", ".join(str(path) for path in root_candidates)
                )
        else:
            candidate = root_candidates[0] if root_candidates else None
            if candidate is None:
                self._initialize_database(self.database_path)
            else:
                backup_path = self._migrate_candidate(candidate)

        imported = self._import_legacy_bookshelves()
        legacy_book_ids = self._legacy_book_ids()
        if state is None:
            state = {
                "version": MIGRATION_STATE_VERSION,
                "database_status": "complete",
                "database_path": str(self.database_path),
                "source_path": str(root_candidates[0]) if root_candidates and backup_path else None,
                "backup_path": str(backup_path) if backup_path else None,
                "layout_phase": "pending",
                "legacy_book_ids": list(legacy_book_ids),
            }
        else:
            state["version"] = MIGRATION_STATE_VERSION
            state["database_status"] = "complete"
            state["database_path"] = str(self.database_path)
            if backup_path:
                state["backup_path"] = str(backup_path)
            state["legacy_book_ids"] = sorted(
                set(state.get("legacy_book_ids", ())) | set(legacy_book_ids)
            )
            state.setdefault("layout_phase", "pending")
        self._write_state(state)

        for candidate in root_candidates:
            if (
                state.get("source_path") == str(candidate)
                and backup_path
                and candidate.exists()
            ):
                if self._sha256(candidate) != self._sha256(backup_path):
                    raise MigrationError(
                        f"Backup verification failed; legacy database was retained: {candidate}"
                    )
                candidate.unlink()

        return MigrationResult(
            database_path=self.database_path,
            state_path=self.state_path,
            backup_path=backup_path,
            imported_bookshelves=imported,
            legacy_book_ids=tuple(state.get("legacy_book_ids", ())),
            warnings=tuple(warnings),
        )

    def _migrate_candidate(self, candidate: Path) -> Path:
        source_digest = self._sha256(candidate)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        self.backups_dir.mkdir(parents=True, exist_ok=True)
        backup_path = self.backups_dir / (
            f"{candidate.name}.{timestamp}.{source_digest[:12]}.bak"
        )
        self._copy_atomic(candidate, backup_path)

        temporary_database = self.data_dir / (
            f".epub-browser.db.migrating-{uuid.uuid4().hex}"
        )
        try:
            shutil.copy2(candidate, temporary_database)
            self._initialize_database(temporary_database)
            self._check_integrity(temporary_database)
            os.replace(temporary_database, self.database_path)
        finally:
            if temporary_database.exists():
                temporary_database.unlink()
        return backup_path

    @staticmethod
    def _initialize_database(path: Path) -> None:
        try:
            StateStore(path).initialize()
        except (RuntimeError, sqlite3.DatabaseError) as error:
            raise MigrationError(
                f"Database schema migration failed for {path}: {error}"
            ) from error

    def _import_legacy_bookshelves(self) -> int:
        selected = {}
        directories = {self.server_dir}
        if self.legacy_sync_dir:
            directories.add(self.legacy_sync_dir)
        for directory in sorted(directories, key=str):
            if not directory.is_dir():
                continue
            for path in sorted(directory.iterdir(), key=lambda item: item.name):
                match = BOOKSHELF_PATTERN.match(path.name)
                if not match or not path.is_file():
                    continue
                username, version_text = match.groups()
                try:
                    payload = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                if not isinstance(payload, dict):
                    continue
                version = int(version_text)
                existing = selected.get(username)
                if existing is None or version > existing[0]:
                    selected[username] = (version, payload)

        store = StateStore(self.database_path)
        imported = 0
        for username, (version, payload) in sorted(selected.items()):
            current = store.get_bookshelf(username)
            if current is not None and current[0] >= version:
                continue
            if current is None:
                store.create_bookshelf(username, version, payload)
            else:
                store.update_bookshelf(username, version, payload)
            imported += 1
        return imported

    def _legacy_book_ids(self) -> tuple[str, ...]:
        identifiers = set()
        metadata_path = self.server_dir / "book-metadata.json"
        if metadata_path.is_file():
            try:
                payload = json.loads(metadata_path.read_text(encoding="utf-8"))
                if isinstance(payload, list):
                    for item in payload:
                        if isinstance(item, dict) and isinstance(item.get("hash"), str):
                            identifiers.add(item["hash"])
            except (OSError, json.JSONDecodeError):
                pass
        book_root = self.server_dir / "book"
        if book_root.is_dir():
            identifiers.update(path.name for path in book_root.iterdir() if path.is_dir())
        return tuple(sorted(identifiers))

    def correlate_legacy_book_ids(
        self,
        sources,
        source_aliases=None,
    ) -> dict[Path, str]:
        state = self._require_state()
        known_ids = set(state.get("legacy_book_ids", ()))
        aliases = source_aliases or {}
        matches = {}
        for source in sorted(
            (Path(path).expanduser().resolve() for path in sources),
            key=str,
        ):
            candidates = (source, *(aliases.get(source, ())))
            legacy_ids = {
                legacy_id
                for candidate in candidates
                for legacy_id in (self._derive_legacy_book_id(Path(candidate)),)
                if legacy_id in known_ids
            }
            if len(legacy_ids) == 1:
                legacy_id = next(iter(legacy_ids))
                matches.setdefault(legacy_id, []).append(source)
        return {
            paths[0]: legacy_id
            for legacy_id, paths in matches.items()
            if len(paths) == 1
        }

    @staticmethod
    def _derive_legacy_book_id(source: Path) -> Optional[str]:
        with tempfile.TemporaryDirectory(
            prefix="epub-browser-legacy-identity-"
        ) as directory:
            processor = EPUBProcessor(
                source,
                directory,
                PublishedAssets({}),
                urls=SiteURLs(),
                reporter=Reporter(False),
            )
            try:
                if not processor.extract_epub():
                    return None
                opf_path = processor.parse_container()
                if not opf_path or not processor.parse_opf(opf_path):
                    return None
                processor.generate_hash()
                return processor.book_hash
            except Exception:
                return None
            finally:
                processor.cleanup()

    def record_cache_reconciled(self, successful: bool = True) -> None:
        if not successful:
            return
        state = self._require_state()
        if state.get("layout_phase") != "pending":
            return
        legacy_public = self.cache_dir / "legacy-public"
        if legacy_public.exists():
            raise MigrationConflictError(
                f"Legacy public backup already exists: {legacy_public}"
            )
        existing = [
            self.server_dir / name
            for name in LEGACY_PUBLIC_ARTIFACTS
            if (self.server_dir / name).exists()
        ]
        if existing:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            staging = self.cache_dir / f".legacy-public-{uuid.uuid4().hex}"
            staging.mkdir()
            moved = []
            try:
                for source in existing:
                    destination = staging / source.name
                    shutil.move(source, destination)
                    moved.append((source, destination))
                os.replace(staging, legacy_public)
            except Exception:
                for source, destination in reversed(moved):
                    if destination.exists() and not source.exists():
                        shutil.move(destination, source)
                if staging.exists():
                    shutil.rmtree(staging, ignore_errors=True)
                raise
        state["layout_phase"] = "retired"
        self._write_state(state)

    def finish_legacy_public_retirement(self) -> None:
        state = self._require_state()
        if state.get("layout_phase") != "retired":
            return
        legacy_public = self.cache_dir / "legacy-public"
        if legacy_public.exists():
            shutil.rmtree(legacy_public)
        state["layout_phase"] = "complete"
        self._write_state(state)

    def _check_integrity(self, path: Path) -> None:
        try:
            connection = sqlite3.connect(path)
            try:
                result = connection.execute("PRAGMA integrity_check").fetchone()
            finally:
                connection.close()
        except sqlite3.DatabaseError as error:
            raise MigrationError(
                f"SQLite integrity check failed for {path}: {error}"
            ) from error
        if not result or result[0] != "ok":
            raise MigrationError(
                f"SQLite integrity check failed for {path}: "
                f"{result[0] if result else 'no result'}"
            )

    @contextmanager
    def _migration_lock(self):
        lock_path = self.data_dir / ".migration.lock"
        lock_file = lock_path.open("a+")
        try:
            try:
                import fcntl

                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            except ImportError:
                pass
            yield
        finally:
            try:
                import fcntl

                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
            except ImportError:
                pass
            lock_file.close()

    def _load_state(self):
        if not self.state_path.is_file():
            return None
        try:
            state = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise MigrationError(
                f"Migration state is unreadable: {self.state_path}: {error}"
            ) from error
        if not isinstance(state, dict):
            raise MigrationError(f"Migration state must be an object: {self.state_path}")
        return state

    def _require_state(self):
        state = self._load_state()
        if state is None:
            raise MigrationError(
                f"Migration has not prepared Server data: {self.state_path}"
            )
        return state

    @staticmethod
    def _state_backup_path(state) -> Optional[Path]:
        if not state or not state.get("backup_path"):
            return None
        return Path(state["backup_path"])

    def _write_state(self, state) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        contents = json.dumps(
            state,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        ) + "\n"
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=self.data_dir,
            prefix=".migration-state.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary.write(contents)
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_path = Path(temporary.name)
        os.replace(temporary_path, self.state_path)

    @staticmethod
    def _copy_atomic(source: Path, destination: Path) -> None:
        temporary = destination.with_name(
            f".{destination.name}.tmp-{uuid.uuid4().hex}"
        )
        try:
            shutil.copy2(source, temporary)
            with temporary.open("rb") as copied:
                os.fsync(copied.fileno())
            os.replace(temporary, destination)
        finally:
            if temporary.exists():
                temporary.unlink()

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as source:
            while chunk := source.read(1024 * 1024):
                digest.update(chunk)
        return digest.hexdigest()
