import json
import math
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
from .book_identity import (
    BOOK_ID_STORAGE_EMBEDDED,
    BOOK_ID_STORAGE_SIDECAR,
    ExternalBookIdentity,
    KnownSourceFingerprint,
    inspect_book_identity,
    resolve_book_identity,
    validate_book_id_storage,
)
from .identity import source_sha256
from .library_progress import LibraryProgressBroker
from .migration import MigrationManager
from .models import BookMetadata, ConvertedBook
from .pdf_processor import PDFMetadata, inspect_pdf, render_pdf_cover
from .processor import (
    EPUBProcessor,
    SERVER_OUTPUT_REVISION,
    SERVER_OUTPUT_REVISION_FILE,
)
from .reporting import Reporter
from .site import LibraryBook, publish_library_shell
from .sidecar_identity import discover_orphan_sidecars, sidecar_path_for
from .source_format import (
    EPUB_FORMAT,
    PDF_EMBEDDED_STORAGE_NOTICE,
    PDF_FORMAT,
    is_supported_source,
    source_format,
)
from .state import BookRecord, StateStore
from .urls import SiteURLs


PDF_OUTPUT_REVISION = "server-pdf-v2"
PDF_OUTPUT_REVISION_FILE = ".server-pdf-revision"
PDF_METADATA_SCHEMA_VERSION = 2


def library_metadata(
    records: Sequence[BookRecord], public_dir: Path, state_store: Optional[StateStore] = None,
    owner_user_id: Optional[str] = None,
) -> list[dict]:
    """Build the published, principal-filtered catalog without writing it."""
    public_root = Path(public_dir)
    books = []
    ratings = (
        state_store.book_review_ratings(owner_user_id, [record.book_id for record in records])
        if state_store is not None and owner_user_id is not None else {}
    )
    for record in records:
        book_root = public_root / "book" / record.book_id
        if record.source_format == PDF_FORMAT:
            available = (book_root / "pdf" / "metadata.json").is_file()
        else:
            available = (
                (book_root / "content" / "metadata.json").is_file()
                or (book_root / "index.html").is_file()
            )
        if not available:
            continue
        try:
            metadata = (
                state_store.managed_book_metadata(record.book_id)
                if state_store is not None
                else json.loads(record.metadata_json)
            )
        except (KeyError, json.JSONDecodeError):
            continue
        cover = metadata.get("cover")
        books.append(
            {
                "hash": record.book_id,
                "url": f"/book/{record.book_id}/index.html",
                "title": metadata.get("title") or "EPUB Book",
                "authors": list(metadata.get("authors") or ()),
                "tags": list(metadata.get("tags") or ()),
                "cover": (
                    f"/book/{record.book_id}/{cover.lstrip('/')}"
                    if isinstance(cover, str) and cover
                    else None
                ),
                "rating": ratings.get(record.book_id),
                "format": record.source_format,
            }
        )
    return books


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
    source_format: str
    pdf_metadata: Optional[PDFMetadata] = None
    identity_inspection: object = None


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
        book_id_storage: str = BOOK_ID_STORAGE_SIDECAR,
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
        self.book_id_storage = validate_book_id_storage(book_id_storage)
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
        self._pdf_embedded_storage_notice_reported = False
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
                publish_service_worker=False,
            ).publish()
            (self.public_dir / "sw.js").unlink(missing_ok=True)
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
            if (
                self.book_id_storage == BOOK_ID_STORAGE_EMBEDDED
                and not self._pdf_embedded_storage_notice_reported
                and any(source_format(path) == PDF_FORMAT for path in discovered)
            ):
                self.reporter.notice(PDF_EMBEDDED_STORAGE_NOTICE)
                self._pdf_embedded_storage_notice_reported = True
            discovered_set = {str(path.resolve()) for path in discovered}
            removed = 0
            with self._commit_lock:
                if self._stop_event.is_set():
                    return self._stopped_summary()
                for record in self.state_store.active_books():
                    if record.source_path not in discovered_set:
                        self.state_store.mark_missing(record.book_id)
                        removed += 1

            orphan_sidecars = discover_orphan_sidecars(
                self._source_inputs,
                discovered,
            )

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
            legacy_ids = self._legacy_id_matches(
                tuple(
                    source
                    for source in discovered
                    if source_format(source) == EPUB_FORMAT
                )
            )
            reused_records = []
            plans = []
            failures = []

            for source in discovered:
                if self._stop_event.is_set():
                    break
                existing = self.state_store.book_by_source(source)
                resolved_book_id = existing.book_id if existing else None
                try:
                    format_name = source_format(source)
                    source_stat = source.stat()
                    existing_cache_valid = bool(
                        existing and self._cache_valid(existing)
                    )
                    known_fingerprint = None
                    if (
                        existing
                        and existing_cache_valid
                        and existing.source_size == source_stat.st_size
                        and existing.source_mtime_ns == source_stat.st_mtime_ns
                    ):
                        known_fingerprint = KnownSourceFingerprint(
                            existing.source_fingerprint,
                            source_stat.st_size,
                            source_stat.st_mtime_ns,
                        )

                    inspection = inspect_book_identity(
                        source,
                        known_fingerprint=known_fingerprint,
                        orphan_sidecars=orphan_sidecars,
                    )
                    external_candidates = []
                    legacy_book_id = legacy_ids.get(source)
                    if existing:
                        external_candidates.append(
                            ExternalBookIdentity(
                                "Server database",
                                existing.book_id,
                                True,
                            )
                        )
                    elif legacy_book_id:
                        external_candidates.append(
                            ExternalBookIdentity(
                                "legacy migration",
                                legacy_book_id,
                                True,
                            )
                        )

                    metadata = None
                    pdf_metadata = None
                    if (
                        existing is None
                        and legacy_book_id is None
                        and not inspection.has_current_carrier
                    ):
                        metadata, pdf_metadata = self._probe_metadata(source)
                        inactive_matches = self.state_store.inactive_book_matches(
                            metadata.epub_identifier,
                            inspection.source_fingerprint,
                        )
                        if len(inactive_matches) > 1:
                            raise ValueError(
                                "Multiple inactive books match the same EPUB "
                                "identifier and fingerprint"
                            )
                        if inactive_matches:
                            external_candidates.append(
                                ExternalBookIdentity(
                                    "inactive Server record",
                                    inactive_matches[0].book_id,
                                    False,
                                )
                            )

                    resolved = resolve_book_identity(
                        inspection,
                        self.book_id_storage,
                        external_candidates=external_candidates,
                        persist=format_name == EPUB_FORMAT,
                    )
                    resolved_book_id = resolved.book_id

                    if (
                        existing
                        and existing_cache_valid
                        and existing.book_id == resolved.book_id
                        and existing.source_fingerprint
                        == resolved.source_fingerprint
                        and existing.source_size == resolved.source_size
                        and existing.source_mtime_ns == resolved.source_mtime_ns
                    ):
                        with self._commit_lock:
                            if self._stop_event.is_set():
                                break
                            self._require_source_stat(source, resolved)
                            record = self.state_store.resolve_book(
                                source,
                                existing.epub_identifier,
                                resolved.source_fingerprint,
                                json.loads(existing.metadata_json),
                                source_size=resolved.source_size,
                                source_mtime_ns=resolved.source_mtime_ns,
                                authoritative_book_id=resolved.book_id,
                                source_format=format_name,
                            )
                        reused_records.append(record)
                        self.progress_broker.record_reused(source)
                        continue

                    if self._stop_event.is_set():
                        break
                    if metadata is None:
                        metadata, pdf_metadata = self._probe_metadata(source)
                    if self._stop_event.is_set():
                        break
                    if existing:
                        record = existing
                    else:
                        with self._commit_lock:
                            if self._stop_event.is_set():
                                break
                            self._require_source_stat(source, resolved)
                            record = self.state_store.resolve_book(
                                source,
                                metadata.epub_identifier,
                                resolved.source_fingerprint,
                                metadata,
                                source_size=resolved.source_size,
                                source_mtime_ns=resolved.source_mtime_ns,
                                authoritative_book_id=resolved.book_id,
                                source_format=format_name,
                            )

                    if (
                        record.source_fingerprint == resolved.source_fingerprint
                        and self._cache_valid(record)
                    ):
                        with self._commit_lock:
                            if self._stop_event.is_set():
                                break
                            self._require_source_stat(source, resolved)
                            record = self.state_store.resolve_book(
                                source,
                                metadata.epub_identifier,
                                resolved.source_fingerprint,
                                metadata,
                                source_size=resolved.source_size,
                                source_mtime_ns=resolved.source_mtime_ns,
                                authoritative_book_id=resolved.book_id,
                                source_format=format_name,
                            )
                        reused_records.append(record)
                        self.progress_broker.record_reused(source)
                        continue

                    with self._commit_lock:
                        if self._stop_event.is_set():
                            break
                        self._invalidate_public_output(record)
                    plans.append(
                        _ConversionPlan(
                            source=source,
                            record=record,
                            fingerprint=resolved.source_fingerprint,
                            metadata=metadata,
                            source_size=resolved.source_size,
                            source_mtime_ns=resolved.source_mtime_ns,
                            source_format=format_name,
                            pdf_metadata=pdf_metadata,
                            identity_inspection=inspection,
                        )
                    )
                except Exception as error:
                    kept = bool(existing and self._cache_valid(existing))
                    failures.append(
                        ConversionFailure(
                            source,
                            resolved_book_id,
                            str(error),
                            kept,
                        )
                    )
                    self._mark_missing_if_deleted(source, existing)
                    self.state_store.enqueue_webhook_event(
                        "book.conversion.failed",
                        {
                            "book_id": resolved_book_id,
                            "format": existing.source_format if existing else source_format(source),
                            "source_name": source.name,
                            "error_code": "conversion_failed",
                        },
                    )
                    self.progress_broker.record_failure(source, error)
                    continue

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
                        self.state_store.enqueue_webhook_event(
                            "book.conversion.succeeded",
                            {"book_id": converted.book_id, "format": converted.source_format},
                        )
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
                        self.state_store.enqueue_webhook_event(
                            "book.conversion.failed",
                            {
                                "book_id": plan.record.book_id,
                                "format": plan.source_format,
                                "source_name": plan.source.name,
                                "error_code": "conversion_failed",
                            },
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
        for logical_source, source in zip(self._source_inputs, self.sources):
            if self._stop_event.is_set():
                raise _ConversionCancelled("Server is stopping")
            if source.is_file():
                if is_supported_source(logical_source):
                    discovered.add(logical_source)
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
                    if filename.startswith("."):
                        continue
                    candidate = root_path / filename
                    if not is_supported_source(candidate):
                        continue
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
                    if source.resolve() == canonical and source != canonical:
                        source_aliases.append(canonical)
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

    def _probe_metadata(self, source: Path) -> tuple[BookMetadata, Optional[PDFMetadata]]:
        if source_format(source) == PDF_FORMAT:
            metadata = inspect_pdf(source)
            return BookMetadata(
                title=metadata.title or "PDF Book",
                authors=metadata.authors,
                tags=metadata.tags,
                cover=None,
                language=metadata.language or "en",
                epub_identifier=None,
                source_format=PDF_FORMAT,
            ), metadata
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
                return processor.get_metadata(), None
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
        if plan.source_format == PDF_FORMAT:
            try:
                return self._convert_pdf_plan(plan, job_root)
            finally:
                shutil.rmtree(job_root, ignore_errors=True)
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
                        source_format=EPUB_FORMAT,
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

    def _convert_pdf_plan(self, plan: _ConversionPlan, job_root: Path) -> BookRecord:
        metadata = plan.pdf_metadata or inspect_pdf(plan.source)
        pdf_dir = job_root / "pdf"
        pdf_dir.mkdir(parents=True, exist_ok=True)
        document = pdf_dir / "document.pdf"
        self._atomic_copy(plan.source, document)
        document_digest = source_sha256(document)
        if document_digest != plan.fingerprint:
            raise _StaleSourceError("source changed while conversion was in progress")
        cover_result = render_pdf_cover(plan.source, job_root / "cover.png")
        cover_name = "cover.png" if cover_result is not None else None
        payload = self._pdf_metadata_payload(
            metadata,
            cover_name=cover_name,
            source_size=plan.source_size,
            source_mtime_ns=plan.source_mtime_ns,
            source_digest=plan.fingerprint,
            document_size=document.stat().st_size,
            document_digest=document_digest,
        )
        self._atomic_write_json(pdf_dir / "metadata.json", payload)
        (job_root / PDF_OUTPUT_REVISION_FILE).write_text(
            PDF_OUTPUT_REVISION + "\n", encoding="utf-8"
        )
        converted_metadata = BookMetadata(
            title=metadata.title or "PDF Book",
            authors=metadata.authors,
            tags=metadata.tags,
            cover=cover_name,
            language=metadata.language or "en",
            epub_identifier=None,
            source_format=PDF_FORMAT,
        )
        self._validate_pdf_cache(job_root, plan, converted_metadata)

        with self._commit_lock:
            if self._stop_event.is_set():
                raise _ConversionCancelled("Server is stopping")
            self._require_source_stat(plan.source, plan)
            identity_state = self._capture_pdf_identity_state(plan)
            destination = self.public_dir / "book" / plan.record.book_id
            destination.parent.mkdir(parents=True, exist_ok=True)
            rollback = self.staging_dir / (
                f".rollback-{plan.record.book_id}-{uuid.uuid4().hex}"
            )
            had_previous = destination.exists()
            activated = False
            try:
                persisted = resolve_book_identity(
                    plan.identity_inspection,
                    self.book_id_storage,
                    external_candidates=(ExternalBookIdentity(
                        "prepared Server PDF cache",
                        plan.record.book_id,
                        False,
                    ),),
                )
                if persisted.book_id != plan.record.book_id:
                    raise ValueError("PDF identity changed during conversion")
                if had_previous:
                    os.replace(destination, rollback)
                os.replace(job_root, destination)
                activated = True
                updated = self.state_store.update_book_version(
                    plan.record.book_id,
                    plan.fingerprint,
                    converted_metadata,
                    source_size=plan.source_size,
                    source_mtime_ns=plan.source_mtime_ns,
                    source_format=PDF_FORMAT,
                )
            except Exception:
                if activated and destination.exists():
                    shutil.rmtree(destination, ignore_errors=True)
                if had_previous and rollback.exists():
                    os.replace(rollback, destination)
                self._restore_pdf_identity_state(identity_state)
                raise
            else:
                if rollback.exists():
                    shutil.rmtree(rollback, ignore_errors=True)
                return updated

    def _validate_pdf_cache(
        self,
        directory: Path,
        expected,
        metadata: BookMetadata,
    ) -> None:
        if not self._pdf_cache_valid(directory, expected, metadata):
            raise ValueError("converted PDF has an invalid Server cache")

    @staticmethod
    def _pdf_cache_valid(directory: Path, expected, metadata) -> bool:
        try:
            revision = (directory / PDF_OUTPUT_REVISION_FILE).read_text(
                encoding="utf-8"
            ).strip()
            payload = json.loads(
                (directory / "pdf" / "metadata.json").read_text(encoding="utf-8")
            )
            document = directory / "pdf" / "document.pdf"
            document_stat = document.stat()
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return False
        if revision != PDF_OUTPUT_REVISION or not isinstance(payload, dict):
            return False
        if payload.get("schema_version") != PDF_METADATA_SCHEMA_VERSION:
            return False
        if payload.get("source_format") != PDF_FORMAT:
            return False
        expected_digest = getattr(expected, "fingerprint", None) or getattr(
            expected, "source_fingerprint", None
        )
        expected_size = getattr(expected, "source_size", None)
        expected_mtime_ns = getattr(expected, "source_mtime_ns", None)
        try:
            cached_digest = source_sha256(document)
        except OSError:
            return False
        if (
            payload.get("source_sha256") != expected_digest
            or payload.get("source_size") != expected_size
            or payload.get("source_mtime_ns") != expected_mtime_ns
            or payload.get("document_sha256") != expected_digest
            or payload.get("document_size") != expected_size
            or document_stat.st_size != expected_size
            or cached_digest != expected_digest
        ):
            return False
        if not isinstance(payload.get("title"), str) or not payload["title"].strip():
            return False
        for field in ("authors", "tags"):
            if not isinstance(payload.get(field), list) or not all(
                isinstance(item, str) for item in payload[field]
            ):
                return False
        if payload.get("language") is not None and not isinstance(
            payload.get("language"), str
        ):
            return False
        if not isinstance(payload.get("encrypted"), bool) or not isinstance(
            payload.get("has_extractable_text"), bool
        ):
            return False
        pages = payload.get("pages")
        if not isinstance(pages, list) or payload.get("page_count") != len(pages):
            return False
        for index, page in enumerate(pages, 1):
            if not isinstance(page, dict) or page.get("page_number") != index:
                return False
            dimensions = (page.get("width"), page.get("height"))
            if any(
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or value <= 0
                for value in dimensions
            ):
                return False
            if not isinstance(page.get("outline_labels"), list) or not all(
                isinstance(label, str) for label in page["outline_labels"]
            ):
                return False
        cover = payload.get("cover")
        expected_cover = (
            metadata.cover if isinstance(metadata, BookMetadata)
            else metadata.get("cover")
        )
        if cover != expected_cover:
            return False
        if cover and not (directory / cover).is_file():
            return False
        if (directory / "content").exists():
            return False
        if (directory / "index.html").exists() or any(directory.glob("chapter_*.html")):
            return False
        return True

    @staticmethod
    def _pdf_metadata_payload(
        metadata: PDFMetadata,
        *,
        cover_name: Optional[str],
        source_size: int,
        source_mtime_ns: int,
        source_digest: str,
        document_size: int,
        document_digest: str,
    ) -> dict:
        return {
            "schema_version": PDF_METADATA_SCHEMA_VERSION,
            "source_format": PDF_FORMAT,
            "title": metadata.title,
            "authors": list(metadata.authors),
            "tags": list(metadata.tags),
            "language": metadata.language,
            "pages": [
                {
                    "page_number": page.page_number,
                    "width": page.width,
                    "height": page.height,
                    "outline_labels": list(page.outline_labels),
                }
                for page in metadata.pages
            ],
            "page_count": len(metadata.pages),
            "encrypted": bool(metadata.encrypted),
            "has_extractable_text": bool(metadata.has_extractable_text),
            "cover": cover_name,
            "source_size": source_size,
            "source_mtime_ns": source_mtime_ns,
            "source_sha256": source_digest,
            "document_size": document_size,
            "document_sha256": document_digest,
        }

    @staticmethod
    def _atomic_copy(source: Path, destination: Path) -> None:
        descriptor, temporary_name = tempfile.mkstemp(
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as output, Path(source).open("rb") as input_file:
                shutil.copyfileobj(input_file, output)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)

    @staticmethod
    def _atomic_write_json(destination: Path, payload: dict) -> None:
        descriptor, temporary_name = tempfile.mkstemp(
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            text=True,
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as output:
                json.dump(payload, output, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)

    @staticmethod
    def _capture_pdf_identity_state(plan: _ConversionPlan):
        paths = {sidecar_path_for(plan.source)}
        if plan.identity_inspection is not None:
            paths.update(sidecar.path for sidecar in plan.identity_inspection.matching_orphans)
        return tuple(
            (path, path.read_bytes() if path.exists() or path.is_symlink() else None)
            for path in sorted(paths, key=str)
        )

    @staticmethod
    def _restore_pdf_identity_state(states) -> None:
        for path, contents in states:
            if contents is None:
                path.unlink(missing_ok=True)
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                descriptor, temporary_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
                temporary = Path(temporary_name)
                try:
                    with os.fdopen(descriptor, "wb") as output:
                        output.write(contents)
                        output.flush()
                        os.fsync(output.fileno())
                    os.replace(temporary, path)
                finally:
                    temporary.unlink(missing_ok=True)

    @staticmethod
    def _validate_converted_book(converted: ConvertedBook) -> None:
        directory = Path(converted.output_dir)
        try:
            revision = (directory / SERVER_OUTPUT_REVISION_FILE).read_text(
                encoding="utf-8"
            ).strip()
        except OSError as error:
            raise ValueError(
                "converted book is missing its Server output revision"
            ) from error
        if revision != SERVER_OUTPUT_REVISION:
            raise ValueError("converted book has an outdated Server output revision")
        content_dir = directory / "content"
        for name in ("metadata.json", "toc.json"):
            if not (content_dir / name).is_file():
                raise ValueError(f"converted book is missing {name}")
        try:
            content_metadata = json.loads(
                (content_dir / "metadata.json").read_text(encoding="utf-8")
            )
            chapters = content_metadata["chapters"]
        except (OSError, json.JSONDecodeError, KeyError, TypeError) as error:
            raise ValueError("converted book has invalid content metadata") from error
        if not isinstance(chapters, list):
            raise ValueError("converted book has invalid chapter metadata")
        for index in range(len(chapters)):
            if not (content_dir / f"chapter_{index}.json").is_file():
                raise ValueError(f"converted book is missing chapter_{index}.json")
        if converted.metadata.cover and not (
            directory / converted.metadata.cover
        ).is_file():
            raise ValueError(
                f"converted book is missing cover {converted.metadata.cover}"
            )

    def _cache_valid(self, record: BookRecord) -> bool:
        directory = self.public_dir / "book" / record.book_id
        if record.source_format == PDF_FORMAT:
            try:
                metadata = json.loads(record.metadata_json)
            except (TypeError, json.JSONDecodeError):
                return False
            return self._pdf_cache_valid(directory, record, metadata)
        try:
            revision = (directory / SERVER_OUTPUT_REVISION_FILE).read_text(
                encoding="utf-8"
            ).strip()
        except OSError:
            return False
        if revision != SERVER_OUTPUT_REVISION:
            return False
        content_dir = directory / "content"
        if not (content_dir / "metadata.json").is_file() or not (
            content_dir / "toc.json"
        ).is_file():
            return False
        try:
            content_metadata = json.loads(
                (content_dir / "metadata.json").read_text(encoding="utf-8")
            )
            chapters = content_metadata["chapters"]
            metadata = json.loads(record.metadata_json)
        except (OSError, json.JSONDecodeError, KeyError, TypeError):
            return False
        if not isinstance(chapters, list):
            return False
        for index in range(len(chapters)):
            if not (content_dir / f"chapter_{index}.json").is_file():
                return False
        cover = metadata.get("cover")
        return not cover or (directory / cover).is_file()

    def _invalidate_public_output(self, record: BookRecord) -> None:
        directory = self.public_dir / "book" / record.book_id
        marker = (
            PDF_OUTPUT_REVISION_FILE
            if record.source_format == PDF_FORMAT
            else SERVER_OUTPUT_REVISION_FILE
        )
        (directory / marker).unlink(missing_ok=True)

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
        publish_library_shell(
            self.public_dir,
            (),
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
