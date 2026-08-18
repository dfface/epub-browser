import json
import os
import queue
import shutil
import tempfile
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Sequence

from .asset_publisher import AssetPublisher, PublishedAssets
from .identity import source_sha256
from .library_progress import LibraryProgressBroker
from .migration import MigrationManager
from .models import BookMetadata, ConvertedBook
from .processor import EPUBProcessor
from .reporting import Reporter
from .site import LibraryBook, publish_library_shell
from .state import BookRecord, StateStore
from .urls import SiteURLs


@dataclass(frozen=True)
class ConversionFailure:
    source: Path
    book_id: Optional[str]
    message: str
    kept_previous_cache: bool


@dataclass(frozen=True)
class ReconcileSummary:
    converted: int
    reused: int
    removed: int
    failures: tuple[ConversionFailure, ...]
    active_books: tuple[BookRecord, ...]
    cancelled: bool = False

    @property
    def failed(self) -> int:
        return len(self.failures)

    @property
    def degraded(self) -> bool:
        return bool(self.failures)


@dataclass(frozen=True)
class _ConversionPlan:
    source: Path
    record: BookRecord
    fingerprint: str
    metadata: BookMetadata
    source_size: int
    source_mtime_ns: int


class _StaleSourceError(RuntimeError):
    pass


class _ConversionCancelled(RuntimeError):
    pass


class ServerLibraryManager:
    _EVENT_DEBOUNCE_SECONDS = 0.1

    def __init__(
        self,
        server_dir: Path,
        sources: Sequence[Path],
        state_store: StateStore,
        migration_manager: Optional[MigrationManager] = None,
        reporter: Optional[Reporter] = None,
        converter_factory: Callable = EPUBProcessor,
        max_workers: int = 4,
        progress_broker: Optional[LibraryProgressBroker] = None,
    ):
        self.server_dir = Path(server_dir).expanduser().resolve()
        self._source_inputs = tuple(
            Path(source).expanduser().absolute() for source in sources
        )
        self.sources = tuple(path.resolve() for path in self._source_inputs)
        self.state_store = state_store
        self.migration_manager = migration_manager
        self.reporter = reporter or Reporter(False)
        self.converter_factory = converter_factory
        self.max_workers = max(1, max_workers)
        self.progress_broker = progress_broker or LibraryProgressBroker()
        self.urls = SiteURLs()
        self.cache_dir = self.server_dir / "cache"
        self.public_dir = self.cache_dir / "public"
        self.staging_dir = self.cache_dir / "staging"
        self.catalog_path = self.cache_dir / "catalog.json"
        self._assets = None
        self._published_library_signature = None
        self._staging_prepared = False
        self._reconcile_lock = threading.Lock()
        self._commit_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._event_lock = threading.Lock()
        self._event_executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="epub_server_events",
        )
        self._queued_generations = {}
        self._event_future = None
        self.on_reconcile_started = None
        self.on_reconciled = None
        self._validate_source_boundaries()

    def _validate_source_boundaries(self) -> None:
        for source in self.sources:
            managed_inside_source = self.server_dir == source or self.server_dir.is_relative_to(source)
            source_inside_managed = source == self.server_dir or source.is_relative_to(self.server_dir)
            if managed_inside_source or source_inside_managed:
                raise ValueError(
                    "Server directory and EPUB sources must not be nested: "
                    f"server={self.server_dir}, source={source}"
                )

    def prepare_public_shell(self) -> Path:
        visible_changed = False
        active_records = ()
        with self._commit_lock:
            if self._stop_event.is_set():
                return self.public_dir
            if not self._staging_prepared:
                shutil.rmtree(self.staging_dir, ignore_errors=True)
                self.staging_dir.mkdir(parents=True, exist_ok=True)
                self._staging_prepared = True
            self.public_dir.mkdir(parents=True, exist_ok=True)
            assets_dir = Path(__file__).with_name("assets")
            self._assets = AssetPublisher(
                assets_dir,
                self.public_dir,
                urls=self.urls,
            ).publish()
            self._refresh_public_shell()
            active_records = self._valid_active_records()
            signature = self._library_signature(active_records)
            visible_changed = signature != self._published_library_signature
            self._published_library_signature = signature
        if visible_changed:
            self.progress_broker.catalog_published(len(active_records))
        return self.public_dir

    def reconcile(self, trigger: str = "startup") -> ReconcileSummary:
        with self._commit_lock:
            if self._stop_event.is_set():
                return self._stopped_summary()
            self._notify_callback(self.on_reconcile_started)
        with self._reconcile_lock:
            if self._stop_event.is_set():
                return self._stopped_summary()
            self.progress_broker.start_generation(trigger)
            self.reporter.detail(
                f"Library reconciliation started: trigger={trigger}"
            )
            try:
                discovered = self._discover_sources()
            except _ConversionCancelled:
                return self._stopped_summary()
            if self._stop_event.is_set():
                return self._stopped_summary()
            discovered_set = {str(path) for path in discovered}
            removed = 0
            with self._commit_lock:
                if self._stop_event.is_set():
                    return self._stopped_summary()
                for record in self.state_store.active_books():
                    if record.source_path not in discovered_set:
                        self.state_store.mark_missing(record.book_id)
                        removed += 1

            self.progress_broker.mark_discovered(len(discovered), removed)
            self.reporter.detail(
                "Library discovery complete: "
                f"trigger={trigger}, total={len(discovered)}, removed={removed}"
            )

            if self._stop_event.is_set():
                return self._stopped_summary(removed=removed)

            self.prepare_public_shell()
            if self._stop_event.is_set():
                return self._stopped_summary(removed=removed)
            legacy_ids = self._legacy_id_matches(discovered)
            reused_records = []
            plans = []
            failures = []

            for source in discovered:
                if self._stop_event.is_set():
                    break
                existing = self.state_store.book_by_source(source)
                try:
                    stat = source.stat()
                except OSError as error:
                    failures.append(
                        ConversionFailure(source, None, str(error), False)
                    )
                    self._mark_missing_if_deleted(source, existing)
                    self.progress_broker.record_failure(source, error)
                    continue

                if (
                    existing
                    and existing.source_size == stat.st_size
                    and existing.source_mtime_ns == stat.st_mtime_ns
                    and self._cache_valid(existing)
                ):
                    try:
                        with self._commit_lock:
                            if self._stop_event.is_set():
                                break
                            self._require_source_stat(source, stat)
                            record = self.state_store.resolve_book(
                                source,
                                existing.epub_identifier,
                                existing.source_fingerprint,
                                json.loads(existing.metadata_json),
                                source_size=stat.st_size,
                                source_mtime_ns=stat.st_mtime_ns,
                            )
                    except (OSError, _StaleSourceError) as error:
                        failures.append(
                            ConversionFailure(source, existing.book_id, str(error), True)
                        )
                        self._mark_missing_if_deleted(source, existing)
                        self.progress_broker.record_failure(source, error)
                        continue
                    reused_records.append(record)
                    self.progress_broker.record_reused(source)
                    continue

                try:
                    fingerprint = source_sha256(source)
                    if self._stop_event.is_set():
                        break
                    metadata = self._probe_metadata(source)
                    if self._stop_event.is_set():
                        break
                    with self._commit_lock:
                        if self._stop_event.is_set():
                            break
                        self._require_source_stat(source, stat)
                        if existing:
                            record = existing
                        else:
                            record = self.state_store.resolve_book(
                                source,
                                metadata.epub_identifier,
                                fingerprint,
                                metadata,
                                source_size=stat.st_size,
                                source_mtime_ns=stat.st_mtime_ns,
                                preferred_book_id=legacy_ids.get(source),
                            )
                except Exception as error:
                    kept = bool(existing and self._cache_valid(existing))
                    failures.append(
                        ConversionFailure(
                            source,
                            existing.book_id if existing else None,
                            str(error),
                            kept,
                        )
                    )
                    self._mark_missing_if_deleted(source, existing)
                    self.progress_broker.record_failure(source, error)
                    continue

                if (
                    record.source_fingerprint == fingerprint
                    and self._cache_valid(record)
                ):
                    try:
                        with self._commit_lock:
                            if self._stop_event.is_set():
                                break
                            self._require_source_stat(source, stat)
                            record = self.state_store.resolve_book(
                                source,
                                metadata.epub_identifier,
                                fingerprint,
                                metadata,
                                source_size=stat.st_size,
                                source_mtime_ns=stat.st_mtime_ns,
                            )
                    except (OSError, _StaleSourceError) as error:
                        failures.append(
                            ConversionFailure(
                                source,
                                record.book_id,
                                str(error),
                                True,
                            )
                        )
                        self._mark_missing_if_deleted(source, record)
                        self.progress_broker.record_failure(source, error)
                        continue
                    reused_records.append(record)
                    self.progress_broker.record_reused(source)
                    continue
                plans.append(
                    _ConversionPlan(
                        source=source,
                        record=record,
                        fingerprint=fingerprint,
                        metadata=metadata,
                        source_size=stat.st_size,
                        source_mtime_ns=stat.st_mtime_ns,
                    )
                )

            if self._stop_event.is_set():
                return self._stopped_summary(
                    reused=len(reused_records),
                    removed=removed,
                    failures=failures,
                )

            converted_records = []
            active_records, visible_changed = self._publish_current_state(failures)
            if visible_changed:
                self.progress_broker.catalog_published(len(active_records))
            if plans:
                for plan, converted, error in self._conversion_outcomes(plans):
                    if self._stop_event.is_set():
                        return self._stopped_summary(
                            converted=len(converted_records),
                            reused=len(reused_records),
                            removed=removed,
                            failures=failures,
                        )
                    if error is None:
                        converted_records.append(converted)
                    elif not isinstance(error, _ConversionCancelled):
                        kept = self._cache_valid(plan.record)
                        if not kept:
                            with self._commit_lock:
                                if self._stop_event.is_set():
                                    return self._stopped_summary(
                                        converted=len(converted_records),
                                        reused=len(reused_records),
                                        removed=removed,
                                        failures=failures,
                                    )
                                self.state_store.mark_missing(plan.record.book_id)
                        failures.append(
                            ConversionFailure(
                                plan.source,
                                plan.record.book_id,
                                str(error),
                                kept,
                            )
                        )
                        self.reporter.detail(
                            f"Failed to convert {plan.source}: {error}"
                        )
                    if self._stop_event.is_set():
                        return self._stopped_summary(
                            converted=len(converted_records),
                            reused=len(reused_records),
                            removed=removed,
                            failures=failures,
                        )
                    active_records, visible_changed = self._publish_current_state(failures)
                    if visible_changed:
                        self.progress_broker.catalog_published(len(active_records))
                    if error is None:
                        self.progress_broker.record_converted(plan.source)
                    elif not isinstance(error, _ConversionCancelled):
                        self.progress_broker.record_failure(
                            plan.source,
                            error,
                            in_flight=True,
                        )

            if self._stop_event.is_set():
                return self._stopped_summary(
                    converted=len(converted_records),
                    reused=len(reused_records),
                    removed=removed,
                    failures=failures,
                )
            active_records, visible_changed = self._publish_current_state(failures)
            if visible_changed:
                self.progress_broker.catalog_published(len(active_records))
            summary = ReconcileSummary(
                converted=len(converted_records),
                reused=len(reused_records),
                removed=removed,
                failures=tuple(
                    sorted(failures, key=lambda failure: str(failure.source))
                ),
                active_books=active_records,
            )
            with self._commit_lock:
                if self._stop_event.is_set():
                    return self._stopped_summary(
                        converted=len(converted_records),
                        reused=len(reused_records),
                        removed=removed,
                        failures=failures,
                    )
                if self.migration_manager:
                    self.migration_manager.record_cache_reconciled(
                        successful=not failures
                        and len(active_records) == len(discovered)
                    )
                self.progress_broker.finish(len(active_records))
                outcome = "degraded" if summary.degraded else "complete"
                self.reporter.detail(
                    "Library reconciliation "
                    f"{outcome}: trigger={trigger}, total={len(discovered)}, "
                    f"converted={summary.converted}, reused={summary.reused}, "
                    f"failed={summary.failed}, removed={summary.removed}, "
                    f"active={len(summary.active_books)}"
                )
                self._notify_callback(self.on_reconciled, summary)
            return summary

    def _stopped_summary(
        self,
        *,
        converted: int = 0,
        reused: int = 0,
        removed: int = 0,
        failures: Sequence[ConversionFailure] = (),
    ) -> ReconcileSummary:
        return ReconcileSummary(
            converted=converted,
            reused=reused,
            removed=removed,
            failures=tuple(
                sorted(failures, key=lambda failure: str(failure.source))
            ),
            active_books=self._valid_active_records(),
            cancelled=True,
        )

    def _conversion_outcomes(self, plans):
        pending = queue.Queue()
        completed = queue.Queue()
        for plan in plans:
            pending.put(plan)

        def worker():
            while not self._stop_event.is_set():
                try:
                    plan = pending.get_nowait()
                except queue.Empty:
                    return
                if self._stop_event.is_set():
                    return
                try:
                    self.progress_broker.conversion_started()
                    converted = self._convert_plan(plan)
                except BaseException as error:
                    completed.put((plan, None, error))
                else:
                    completed.put((plan, converted, None))

        workers = [
            threading.Thread(
                target=worker,
                name=f"epub_server_convert_{index}",
                daemon=True,
            )
            for index in range(min(self.max_workers, len(plans)))
        ]
        for thread in workers:
            thread.start()

        remaining = len(plans)
        while remaining and not self._stop_event.is_set():
            try:
                outcome = completed.get(timeout=0.05)
            except queue.Empty:
                continue
            remaining -= 1
            yield outcome

        if not self._stop_event.is_set():
            for thread in workers:
                thread.join()

    def _notify_callback(self, callback, *args) -> None:
        if callback is None:
            return
        try:
            callback(*args)
        except Exception as error:
            self.reporter.detail(f"Server reconciliation callback failed: {error}")

    @staticmethod
    def _require_source_stat(source: Path, expected) -> None:
        current = source.stat()
        expected_size = (
            expected.st_size
            if hasattr(expected, "st_size")
            else expected.source_size
        )
        expected_mtime_ns = (
            expected.st_mtime_ns
            if hasattr(expected, "st_mtime_ns")
            else expected.source_mtime_ns
        )
        if (
            current.st_size != expected_size
            or current.st_mtime_ns != expected_mtime_ns
        ):
            raise _StaleSourceError("source changed while conversion was in progress")

    def _discover_sources(self) -> tuple[Path, ...]:
        discovered = set()
        for source in self.sources:
            if self._stop_event.is_set():
                raise _ConversionCancelled("Server is stopping")
            if source.is_file():
                if source.suffix.lower() == ".epub":
                    discovered.add(source)
                continue
            if not source.is_dir():
                continue
            for root, directories, files in os.walk(source, followlinks=False):
                if self._stop_event.is_set():
                    raise _ConversionCancelled("Server is stopping")
                root_path = Path(root)
                directories[:] = [
                    name
                    for name in directories
                    if not name.startswith(".")
                    and not (root_path / name).is_symlink()
                ]
                for filename in files:
                    if filename.startswith(".") or not filename.lower().endswith(".epub"):
                        continue
                    candidate = root_path / filename
                    try:
                        resolved = candidate.resolve()
                    except OSError:
                        continue
                    if not resolved.is_relative_to(source):
                        continue
                    if resolved.is_file():
                        discovered.add(resolved)
        if self._stop_event.is_set():
            raise _ConversionCancelled("Server is stopping")
        return tuple(sorted(discovered, key=str))

    def _legacy_id_matches(self, discovered: Sequence[Path]) -> dict[Path, str]:
        if not self.migration_manager:
            return {}
        unresolved = [
            source
            for source in discovered
            if self.state_store.book_by_source(source) is None
        ]
        if not unresolved:
            return {}
        return self.migration_manager.correlate_legacy_book_ids(
            unresolved,
            self._legacy_source_aliases(unresolved),
        )

    def _legacy_source_aliases(self, discovered: Sequence[Path]):
        aliases = {}
        for source in discovered:
            source_aliases = []
            for original, canonical in zip(self._source_inputs, self.sources):
                if canonical.is_file():
                    if source == canonical and original != canonical:
                        source_aliases.append(original)
                    continue
                try:
                    relative = source.relative_to(canonical)
                except ValueError:
                    continue
                alias = original / relative
                if alias != source:
                    source_aliases.append(alias)
            if source_aliases:
                aliases[source] = tuple(source_aliases)
        return aliases

    def _probe_metadata(self, source: Path) -> BookMetadata:
        with tempfile.TemporaryDirectory(
            prefix="epub-browser-server-probe-",
            dir=self.staging_dir if self.staging_dir.is_dir() else None,
        ) as directory:
            processor = EPUBProcessor(
                source,
                directory,
                PublishedAssets({}),
                urls=self.urls,
                reporter=self.reporter,
            )
            try:
                if not processor.extract_epub():
                    raise ValueError("unable to extract EPUB archive")
                opf_path = processor.parse_container()
                if not opf_path or not processor.parse_opf(opf_path):
                    raise ValueError("unable to parse EPUB package")
                return processor.get_metadata()
            finally:
                processor.cleanup()

    def _convert_plan(self, plan: _ConversionPlan) -> BookRecord:
        if self._stop_event.is_set():
            raise _ConversionCancelled("Server is stopping")
        self.staging_dir.mkdir(parents=True, exist_ok=True)
        job_root = Path(
            tempfile.mkdtemp(
                prefix=f"{plan.record.book_id}-",
                dir=self.staging_dir,
            )
        )
        processor = self.converter_factory(
            plan.source,
            job_root,
            self._assets,
            book_id=plan.record.book_id,
            urls=self.urls,
            reporter=self.reporter,
            deployment_mode="server",
        )
        try:
            converted: ConvertedBook = processor.convert()
            if self._stop_event.is_set():
                raise _ConversionCancelled("Server is stopping")
            if source_sha256(plan.source) != plan.fingerprint:
                raise _StaleSourceError(
                    "source changed while conversion was in progress"
                )
            self._validate_converted_book(converted)
            with self._commit_lock:
                if self._stop_event.is_set():
                    raise _ConversionCancelled("Server is stopping")
                self._require_source_stat(plan.source, plan)
                destination = self.public_dir / "book" / plan.record.book_id
                destination.parent.mkdir(parents=True, exist_ok=True)
                rollback = self.staging_dir / (
                    f".rollback-{plan.record.book_id}-{uuid.uuid4().hex}"
                )
                had_previous = destination.exists()
                if had_previous:
                    os.replace(destination, rollback)
                try:
                    os.replace(converted.output_dir, destination)
                    updated = self.state_store.update_book_version(
                        plan.record.book_id,
                        plan.fingerprint,
                        converted.metadata,
                        source_size=plan.source_size,
                        source_mtime_ns=plan.source_mtime_ns,
                        epub_identifier=converted.metadata.epub_identifier,
                    )
                except Exception:
                    if destination.exists():
                        shutil.rmtree(destination, ignore_errors=True)
                    if had_previous and rollback.exists():
                        os.replace(rollback, destination)
                    raise
                else:
                    if rollback.exists():
                        shutil.rmtree(rollback, ignore_errors=True)
                    return updated
        finally:
            cleanup = getattr(processor, "cleanup", None)
            if cleanup:
                cleanup()
            shutil.rmtree(job_root, ignore_errors=True)

    @staticmethod
    def _validate_converted_book(converted: ConvertedBook) -> None:
        directory = Path(converted.output_dir)
        for name in ("index.html", "toc.json"):
            if not (directory / name).is_file():
                raise ValueError(f"converted book is missing {name}")
        toc = json.loads((directory / "toc.json").read_text(encoding="utf-8"))
        for item in toc:
            chapter = item.get("chapter_file")
            if chapter and not (directory / chapter).is_file():
                raise ValueError(f"converted book is missing {chapter}")
        if converted.metadata.cover and not (
            directory / converted.metadata.cover
        ).is_file():
            raise ValueError(
                f"converted book is missing cover {converted.metadata.cover}"
            )

    def _cache_valid(self, record: BookRecord) -> bool:
        directory = self.public_dir / "book" / record.book_id
        if not (directory / "index.html").is_file() or not (
            directory / "toc.json"
        ).is_file():
            return False
        try:
            toc = json.loads((directory / "toc.json").read_text(encoding="utf-8"))
            metadata = json.loads(record.metadata_json)
        except (OSError, json.JSONDecodeError):
            return False
        for item in toc:
            chapter = item.get("chapter_file")
            if chapter and not (directory / chapter).is_file():
                return False
        cover = metadata.get("cover")
        return not cover or (directory / cover).is_file()

    def _valid_active_records(self) -> tuple[BookRecord, ...]:
        return tuple(
            record
            for record in self.state_store.active_books()
            if self._cache_valid(record)
        )

    def _mark_missing_if_deleted(
        self,
        source: Path,
        record: Optional[BookRecord],
    ) -> None:
        if record is None or source.exists():
            return
        with self._commit_lock:
            if not self._stop_event.is_set():
                self.state_store.mark_missing(record.book_id)

    def _refresh_public_shell(self) -> None:
        if self._assets is None:
            return
        books = []
        for record in self._valid_active_records():
            try:
                metadata = json.loads(record.metadata_json)
            except json.JSONDecodeError:
                continue
            cover = metadata.get("cover")
            books.append(
                LibraryBook(
                    book_id=record.book_id,
                    title=metadata.get("title") or "EPUB Book",
                    authors=tuple(metadata.get("authors") or ()),
                    tags=tuple(metadata.get("tags") or ()),
                    cover=(
                        f"/book/{record.book_id}/{cover}"
                        if cover
                        else None
                    ),
                )
            )
        publish_library_shell(
            self.public_dir,
            tuple(books),
            self._assets,
            self.urls,
            deployment_mode="server",
        )

    def _write_catalog(
        self,
        active_records: Sequence[BookRecord],
        failures: Sequence[ConversionFailure],
    ) -> None:
        payload = {
            "schema_version": 1,
            "books": [
                {
                    "book_id": record.book_id,
                    "source_fingerprint": record.source_fingerprint,
                    "source_size": record.source_size,
                    "source_mtime_ns": record.source_mtime_ns,
                }
                for record in active_records
            ],
            "degraded": bool(failures),
            "failed_count": len(failures),
        }
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=self.cache_dir,
            prefix=".catalog.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            json.dump(
                payload,
                temporary,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_path = Path(temporary.name)
        os.replace(temporary_path, self.catalog_path)

    def _publish_current_state(
        self,
        failures: Sequence[ConversionFailure],
    ) -> tuple[tuple[BookRecord, ...], bool]:
        with self._commit_lock:
            return self._publish_current_state_locked(failures)

    def _publish_current_state_locked(
        self,
        failures: Sequence[ConversionFailure],
        *,
        allow_stopped: bool = False,
    ) -> tuple[tuple[BookRecord, ...], bool]:
        if self._stop_event.is_set() and not allow_stopped:
            return self._valid_active_records(), False
        active_records = self._valid_active_records()
        signature = self._library_signature(active_records)
        visible_changed = signature != self._published_library_signature
        self._refresh_public_shell()
        self._write_catalog(active_records, failures)
        self._published_library_signature = signature
        return active_records, visible_changed

    @staticmethod
    def _library_signature(records: Sequence[BookRecord]):
        return tuple(
            (record.book_id, record.metadata_json)
            for record in records
        )

    def queue_path(self, path: Path):
        if self._stop_event.is_set():
            return None
        canonical = Path(path).expanduser().resolve()
        with self._event_lock:
            self._queued_generations[canonical] = (
                self._queued_generations.get(canonical, 0) + 1
            )
            if self._event_future is None or self._event_future.done():
                self._event_future = self._event_executor.submit(
                    self._drain_queued_events
                )
            return self._event_future

    def _drain_queued_events(self):
        while True:
            if self._stop_event.wait(self._EVENT_DEBOUNCE_SECONDS):
                return
            with self._event_lock:
                snapshot = dict(self._queued_generations)
            if not snapshot:
                return
            self.reconcile(trigger="watch")
            with self._event_lock:
                for path, generation in snapshot.items():
                    if self._queued_generations.get(path) == generation:
                        self._queued_generations.pop(path, None)
                if not self._queued_generations:
                    return

    def mark_deleted(self, path: Path) -> None:
        if self._stop_event.is_set():
            return
        with self._reconcile_lock:
            with self._commit_lock:
                if self._stop_event.is_set():
                    return
                record = self.state_store.book_by_source(Path(path))
                if not record or not record.active:
                    return
            if self._assets is None:
                self.prepare_public_shell()
            with self._commit_lock:
                if self._stop_event.is_set():
                    return
                record = self.state_store.book_by_source(Path(path))
                if not record or not record.active:
                    return
                self.reporter.detail(
                    f"Watch direct-delete batch started: source={Path(path)}"
                )
                self.progress_broker.start_generation("watch")
                self.progress_broker.mark_discovered(total=0, removed=1)
                self.state_store.mark_missing(record.book_id)
                active_records, visible_changed = self._publish_current_state_locked(
                    (),
                    allow_stopped=True,
                )
                if visible_changed:
                    self.progress_broker.catalog_published(len(active_records))
                if not self._stop_event.is_set():
                    self.progress_broker.finish(len(active_records))
                    self.reporter.detail(
                        "Watch direct-delete batch complete: "
                        f"removed=1, active={len(active_records)}"
                    )

    def request_stop(self) -> None:
        self._stop_event.set()
        with self._event_lock:
            self._queued_generations.clear()
        with self._commit_lock:
            pass

    def shutdown(self) -> None:
        self.request_stop()
        self._event_executor.shutdown(wait=True, cancel_futures=True)
