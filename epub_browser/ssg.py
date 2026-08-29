import json
import os
import re
import shutil
import sys
import tempfile
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable, Optional, Sequence

from tqdm import tqdm

from .asset_publisher import (
    AssetPublisher,
    PublishedAssets,
    SERVER_ONLY_ASSET_PATHS,
    SERVER_ONLY_ASSET_PREFIXES,
    WEB_MANIFEST_SOURCES,
)
from .book_identity import (
    BOOK_ID_STORAGE_EMBEDDED,
    ExternalBookIdentity,
    BookIdentityInspection,
    inspect_book_identity,
    resolve_book_identity,
)
from .cli import SSGConfig
from .models import ConvertedBook
from .identity import source_sha256
from .pdf_processor import PDFMetadata, inspect_pdf, render_pdf_cover
from .processor import EPUBProcessor
from .reporting import Reporter
from .site import LibraryBook, publish_library_shell
from .sidecar_identity import (
    discover_orphan_sidecars,
    sidecar_path_for,
)
from .source_format import (
    PDF_EMBEDDED_STORAGE_NOTICE,
    EPUB_FORMAT,
    PDF_FORMAT,
    is_supported_source,
    source_format,
)
from .urls import SiteURLs


class SSGBuildError(RuntimeError):
    pass


@dataclass(frozen=True)
class _PreparedBook:
    source: Path
    book_id: str
    source_format: str
    source_fingerprint: str
    pdf_metadata: Optional[PDFMetadata] = None
    identity_inspection: Optional[BookIdentityInspection] = None


@dataclass(frozen=True)
class _SidecarState:
    path: Path
    contents: Optional[bytes]


class SSGPublisher:
    def __init__(
        self,
        config: SSGConfig,
        reporter: Optional[Reporter] = None,
        converter_factory: Callable = EPUBProcessor,
        show_progress: Optional[bool] = None,
    ):
        if config.output_dir is None:
            raise SSGBuildError("SSG output directory is required")
        self.config = config
        self.output_dir = Path(config.output_dir).expanduser().resolve()
        self.urls = SiteURLs(config.base_path)
        self.reporter = reporter or Reporter(config.log)
        self.converter_factory = converter_factory
        self.show_progress = sys.stderr.isatty() if show_progress is None else show_progress

    def build(self) -> Path:
        sources = self._discover_sources()
        self._validate_output_target(sources)
        orphan_sidecars = discover_orphan_sidecars(self.config.sources, sources)
        prepared = self._prepare_books(sources, orphan_sidecars)

        self.output_dir.parent.mkdir(parents=True, exist_ok=True)
        staging = Path(
            tempfile.mkdtemp(
                prefix=f".{self.output_dir.name}.staging-",
                dir=self.output_dir.parent,
            )
        )
        try:
            assets_dir = Path(__file__).with_name("assets")
            assets = AssetPublisher(
                assets_dir,
                staging,
                urls=self.urls,
                excluded_paths=SERVER_ONLY_ASSET_PATHS,
                excluded_prefixes=SERVER_ONLY_ASSET_PREFIXES,
            ).publish()
            books = self._convert_all(prepared, staging, assets)
            publish_library_shell(staging, books, assets, self.urls)
            self._validate_snapshot(staging, books, assets)
            identity_state = self._capture_pdf_identity_state(prepared)
            try:
                self._persist_pdf_identities(prepared)
                self._activate(staging)
            except Exception:
                self._restore_pdf_identity_state(identity_state)
                raise
            return self.output_dir
        finally:
            if staging.exists():
                shutil.rmtree(staging, ignore_errors=True)

    def _prepare_books(
        self,
        sources: Sequence[Path],
        orphan_sidecars: Sequence[Path],
    ) -> tuple[_PreparedBook, ...]:
        failures = []
        prepared = []
        with tempfile.TemporaryDirectory(prefix="epub-browser-ssg-probe-") as directory:
            probe_root = Path(directory)
            for source in sources:
                processor = None
                try:
                    format_name = source_format(source)
                    pdf_metadata = inspect_pdf(source) if format_name == PDF_FORMAT else None
                    inspection = inspect_book_identity(
                        source,
                        orphan_sidecars=orphan_sidecars,
                    )
                    identity = resolve_book_identity(
                        inspection,
                        self.config.book_id_storage,
                        persist=format_name != PDF_FORMAT,
                    )
                    book_id = identity.book_id
                    if format_name == EPUB_FORMAT:
                        processor = EPUBProcessor(
                            source,
                            probe_root,
                            PublishedAssets({}),
                            urls=self.urls,
                            reporter=self.reporter,
                        )
                        if not processor.extract_epub():
                            raise ValueError("unable to extract EPUB archive")
                        opf_path = processor.parse_container()
                        if not opf_path:
                            raise ValueError("unable to locate EPUB package")
                        if not processor.parse_opf(opf_path):
                            raise ValueError("unable to parse EPUB package")
                    prepared.append(_PreparedBook(
                        source=source,
                        book_id=book_id,
                        source_format=format_name,
                        source_fingerprint=identity.source_fingerprint,
                        pdf_metadata=pdf_metadata,
                        identity_inspection=(
                            inspection if format_name == PDF_FORMAT else None
                        ),
                    ))
                except Exception as error:
                    failures.append((source, str(error)))
                finally:
                    if processor is not None:
                        processor.cleanup()

        if failures:
            raise SSGBuildError(
                self._format_failures("Unable to prepare book inputs", failures)
            )

        collisions = {}
        for book in prepared:
            collisions.setdefault(book.book_id, []).append(book.source)
        duplicate_groups = {
            book_id: paths
            for book_id, paths in collisions.items()
            if len(paths) > 1
        }
        if duplicate_groups:
            lines = ["Duplicate SSG book IDs:"]
            for book_id in sorted(duplicate_groups):
                lines.append(f"  {book_id}:")
                lines.extend(
                    f"    - {path}" for path in sorted(duplicate_groups[book_id])
                )
            raise SSGBuildError("\n".join(lines))
        return tuple(sorted(prepared, key=lambda book: (book.book_id, str(book.source))))

    def _discover_sources(self) -> tuple[Path, ...]:
        discovered = []
        failures = []
        for configured_source in self.config.sources:
            source = Path(configured_source).expanduser()
            if not source.exists():
                failures.append((source, "path does not exist"))
                continue
            absolute = source.absolute()
            if absolute.is_file():
                if is_supported_source(absolute):
                    discovered.append(absolute)
                else:
                    failures.append((absolute, "file is not an EPUB or PDF"))
                continue
            resolved = source.resolve()
            if not resolved.is_dir():
                failures.append((resolved, "path is not a regular file or directory"))
                continue
            for candidate in resolved.rglob("*"):
                relative = candidate.relative_to(resolved)
                if any(part.startswith(".") for part in relative.parts):
                    continue
                if candidate.is_file() and is_supported_source(candidate):
                    discovered.append(candidate.resolve())

        if failures:
            raise SSGBuildError(
                self._format_failures("Invalid SSG sources", failures)
            )
        unique = tuple(sorted(set(discovered), key=str))
        if not unique:
            raise SSGBuildError("No EPUB or PDF files were discovered")
        if (
            self.config.book_id_storage == BOOK_ID_STORAGE_EMBEDDED
            and any(source_format(path) == PDF_FORMAT for path in unique)
        ):
            self.reporter.notice(PDF_EMBEDDED_STORAGE_NOTICE)
        return unique

    def _validate_output_target(self, sources: Sequence[Path]) -> None:
        configured_output = Path(self.config.output_dir).expanduser()
        if configured_output.is_symlink():
            raise SSGBuildError("Output directory cannot be a symbolic link")
        if self.output_dir == Path(self.output_dir.anchor):
            raise SSGBuildError("Output directory cannot be a filesystem root")
        for configured_source in self.config.sources:
            source = Path(configured_source).expanduser().resolve()
            if self.output_dir == source:
                raise SSGBuildError(
                    f"Output directory cannot be an input source: {self.output_dir}"
                )
        for source in sources:
            resolved_source = source.resolve()
            if (
                resolved_source == self.output_dir
                or resolved_source.is_relative_to(self.output_dir)
            ):
                raise SSGBuildError(
                    f"Output directory would own an input EPUB: {self.output_dir}"
                )

    def _convert_all(
        self,
        prepared: Sequence[_PreparedBook],
        staging: Path,
        assets: PublishedAssets,
    ) -> tuple[LibraryBook, ...]:
        failures = []
        converted_books = []
        progress = tqdm(
            total=len(prepared),
            desc="Processing books",
            disable=not self.show_progress,
        )
        self.reporter.progress_active = self.show_progress
        try:
            with ThreadPoolExecutor(max_workers=min(10, len(prepared))) as executor:
                futures = {
                    executor.submit(
                        self._convert_one,
                        book,
                        staging,
                        assets,
                    ): book
                    for book in prepared
                }
                for future in as_completed(futures):
                    book = futures[future]
                    try:
                        converted_books.append(future.result())
                    except Exception as error:
                        failures.append((book.source, str(error)))
                    finally:
                        progress.update(1)
        finally:
            progress.close()
            self.reporter.progress_active = False

        if failures:
            raise SSGBuildError(self._format_failures("SSG conversion failed", failures))
        return tuple(sorted(converted_books, key=lambda book: book.book_id))

    def _convert_one(
        self,
        prepared: _PreparedBook,
        staging: Path,
        assets: PublishedAssets,
    ) -> LibraryBook:
        if prepared.source_format == PDF_FORMAT:
            return self._convert_pdf(prepared, staging, assets)
        self.reporter.detail(f"Converting EPUB: {prepared.source}")
        processor = self.converter_factory(
            prepared.source,
            staging,
            assets,
            book_id=prepared.book_id,
            urls=self.urls,
            reporter=self.reporter,
        )
        try:
            converted: ConvertedBook = processor.convert()
            destination = staging / "book" / prepared.book_id
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(os.fspath(converted.output_dir), destination)
            cover = (
                f"/book/{prepared.book_id}/{converted.metadata.cover}"
                if converted.metadata.cover
                else None
            )
            return LibraryBook(
                book_id=prepared.book_id,
                title=converted.metadata.title,
                authors=converted.metadata.authors,
                tags=converted.metadata.tags,
                cover=cover,
                source_format=converted.metadata.source_format,
            )
        finally:
            cleanup = getattr(processor, "cleanup", None)
            if cleanup:
                cleanup()

    def _convert_pdf(
        self,
        prepared: _PreparedBook,
        staging: Path,
        assets: PublishedAssets,
    ) -> LibraryBook:
        self.reporter.detail(f"Converting PDF: {prepared.source}")
        metadata = prepared.pdf_metadata
        if metadata is None:
            raise SSGBuildError("PDF metadata was not prepared")
        destination = staging / "book" / prepared.book_id
        destination.parent.mkdir(parents=True, exist_ok=True)
        working = Path(tempfile.mkdtemp(
            prefix=f".{prepared.book_id}.pdf-",
            dir=destination.parent,
        ))
        try:
            document = working / "document.pdf"
            self._atomic_copy(prepared.source, document)
            if source_sha256(document) != prepared.source_fingerprint:
                raise SSGBuildError("PDF source changed during conversion")

            cover_result = render_pdf_cover(prepared.source, working / "cover.png")
            cover_name = "cover.png" if cover_result is not None else None
            processor = EPUBProcessor.from_pdf_metadata(
                book_id=prepared.book_id,
                metadata=metadata,
                cover_path=cover_name,
                asset_manifest=assets,
                urls=self.urls,
                deployment_mode="ssg",
            )
            self._atomic_write_text(working / "index.html", processor.create_index_page(write=False))
            toc = processor._build_toc_data()
            self._atomic_write_text(
                working / "toc.json",
                json.dumps(toc, ensure_ascii=False, separators=(",", ":")),
            )
            document_url = self.urls.public(
                f"/book/{prepared.book_id}/document.pdf"
            )
            for chapter_index in range(len(metadata.pages)):
                self._atomic_write_text(
                    working / f"chapter_{chapter_index}.html",
                    processor.create_pdf_chapter_template(
                        chapter_index, document_url
                    ),
                )
            self._validate_pdf_book(working, toc, len(metadata.pages))
            os.replace(working, destination)
            working = None
            book_metadata = processor.get_metadata()
            return LibraryBook(
                book_id=prepared.book_id,
                title=book_metadata.title,
                authors=book_metadata.authors,
                tags=book_metadata.tags,
                cover=(
                    f"/book/{prepared.book_id}/{book_metadata.cover}"
                    if book_metadata.cover else None
                ),
                source_format=PDF_FORMAT,
            )
        finally:
            if working is not None and working.exists():
                shutil.rmtree(working, ignore_errors=True)

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
            if temporary.exists():
                temporary.unlink()

    @staticmethod
    def _atomic_write_text(destination: Path, contents: str) -> None:
        descriptor, temporary_name = tempfile.mkstemp(
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            text=True,
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as output:
                output.write(contents)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, destination)
        finally:
            if temporary.exists():
                temporary.unlink()

    @staticmethod
    def _validate_pdf_book(directory: Path, toc, page_count: int) -> None:
        expected = [f"chapter_{index}.html" for index in range(page_count)]
        if [item.get("chapter_file") for item in toc] != expected:
            raise SSGBuildError("PDF table of contents is incomplete")
        if [item.get("chapter_index") for item in toc] != list(range(page_count)):
            raise SSGBuildError("PDF table of contents has invalid chapter indexes")
        actual = sorted(path.name for path in directory.glob("chapter_*.html"))
        if actual != sorted(expected):
            raise SSGBuildError("PDF chapter output is incomplete")
        for name in ("index.html", "toc.json", "document.pdf", *expected):
            if not (directory / name).is_file():
                raise SSGBuildError(f"PDF output is missing {name}")

    def _persist_pdf_identities(self, prepared: Sequence[_PreparedBook]) -> None:
        for book in prepared:
            if book.source_format != PDF_FORMAT:
                continue
            inspection = book.identity_inspection
            if inspection is None:
                raise SSGBuildError("PDF identity was not prepared")
            resolved = resolve_book_identity(
                inspection,
                self.config.book_id_storage,
                external_candidates=(ExternalBookIdentity(
                    origin="prepared SSG output",
                    book_id=book.book_id,
                    current_path=False,
                ),),
            )
            if resolved.book_id != book.book_id:
                raise SSGBuildError("PDF identity changed during conversion")

    @staticmethod
    def _capture_pdf_identity_state(
        prepared: Sequence[_PreparedBook],
    ) -> tuple[_SidecarState, ...]:
        paths = set()
        for book in prepared:
            if book.source_format != PDF_FORMAT:
                continue
            paths.add(sidecar_path_for(book.source))
            if book.identity_inspection is not None:
                paths.update(
                    sidecar.path
                    for sidecar in book.identity_inspection.matching_orphans
                )
        return tuple(
            _SidecarState(
                path=path,
                contents=(
                    path.read_bytes()
                    if path.exists() or path.is_symlink()
                    else None
                ),
            )
            for path in sorted(paths, key=str)
        )

    def _restore_pdf_identity_state(
        self,
        states: Sequence[_SidecarState],
    ) -> None:
        for state in states:
            if state.contents is None and (state.path.exists() or state.path.is_symlink()):
                state.path.unlink()
        for state in states:
            if state.contents is not None:
                self._atomic_write_bytes(state.path, state.contents)

    @staticmethod
    def _atomic_write_bytes(destination: Path, contents: bytes) -> None:
        descriptor, temporary_name = tempfile.mkstemp(
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as output:
                output.write(contents)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, destination)
        finally:
            if temporary.exists():
                temporary.unlink()

    def _validate_snapshot(
        self,
        staging: Path,
        books: Sequence[LibraryBook],
        assets: PublishedAssets,
    ) -> None:
        required_root_files = (
            "index.html",
            "book-metadata.json",
            "assets/asset-manifest.json",
            "sw.js",
        ) + tuple(f"assets/{name}" for name in WEB_MANIFEST_SOURCES)
        for relative in required_root_files:
            if not (staging / relative).is_file():
                raise SSGBuildError(f"Incomplete SSG snapshot: missing {relative}")

        metadata = json.loads(
            (staging / "book-metadata.json").read_text(encoding="utf-8")
        )
        expected_ids = [book.book_id for book in books]
        if [item.get("hash") for item in metadata] != expected_ids:
            raise SSGBuildError("SSG metadata does not agree with converted books")
        book_root = staging / "book"
        actual_ids = sorted(path.name for path in book_root.iterdir() if path.is_dir())
        if actual_ids != expected_ids:
            raise SSGBuildError("SSG book directories do not agree with metadata")

        for book in books:
            directory = book_root / book.book_id
            for name in ("index.html", "toc.json"):
                if not (directory / name).is_file():
                    raise SSGBuildError(
                        f"Incomplete SSG book {book.book_id}: missing {name}"
                    )
            toc = json.loads((directory / "toc.json").read_text(encoding="utf-8"))
            for item in toc:
                chapter = item.get("chapter_file")
                if chapter and not (directory / chapter).is_file():
                    raise SSGBuildError(
                        f"Incomplete SSG book {book.book_id}: missing {chapter}"
                    )

        for public_url in assets.assets.values():
            if self.urls.base_path != "/" and not public_url.startswith(self.urls.base_path):
                raise SSGBuildError(f"Asset URL is outside base path: {public_url}")
            if not (staging / self.urls.filesystem_relative(public_url)).is_file():
                raise SSGBuildError(f"Asset manifest target is missing: {public_url}")

        for item in metadata:
            for key in ("url", "cover"):
                public_url = item.get(key)
                if not public_url:
                    continue
                if self.urls.base_path != "/" and not public_url.startswith(self.urls.base_path):
                    raise SSGBuildError(
                        f"Book metadata URL is outside base path: {public_url}"
                    )
                if not (staging / self.urls.filesystem_relative(public_url)).is_file():
                    raise SSGBuildError(f"Book metadata target is missing: {public_url}")

        forbidden_root_names = {
            "epub-browser.db",
            "annotations.db",
            "migration-state.json",
            "catalog.json",
            "data",
            "cache",
        }
        for path in staging.rglob("*"):
            relative = path.relative_to(staging)
            if relative.parts and relative.parts[0] in forbidden_root_names:
                raise SSGBuildError(f"Server state leaked into SSG snapshot: {path}")

        forbidden_text = (
            str(staging),
            *(str(path) for path in self._prepare_source_paths_for_validation()),
        )
        for path in staging.rglob("*"):
            if path.suffix.lower() not in {".html", ".json", ".js", ".css"}:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            leaked = next((value for value in forbidden_text if value and value in text), None)
            if leaked:
                raise SSGBuildError(f"Local filesystem path leaked into {path}: {leaked}")

        root_url = re.compile(r"(?:href|src|content)\s*=\s*['\"]/(?!/)")
        if self.urls.base_path != "/":
            for path in staging.rglob("*.html"):
                text = path.read_text(encoding="utf-8")
                if root_url.search(text.replace(self.urls.base_path, "")):
                    raise SSGBuildError(f"Root-relative URL escaped base path in {path}")

    def _prepare_source_paths_for_validation(self) -> tuple[Path, ...]:
        paths = []
        for source in self.config.sources:
            path = Path(source).expanduser()
            if path.exists():
                paths.append(path.resolve())
        return tuple(paths)

    def _activate(self, staging: Path) -> None:
        self._cleanup_previous_snapshots()
        previous = self.output_dir.parent / (
            f".{self.output_dir.name}.previous-{uuid.uuid4().hex}"
        )
        had_previous = self.output_dir.exists()
        if had_previous:
            os.replace(self.output_dir, previous)
        try:
            os.replace(staging, self.output_dir)
        except Exception:
            if had_previous and previous.exists():
                if self.output_dir.exists():
                    self._remove_path(self.output_dir)
                os.replace(previous, self.output_dir)
            raise
        else:
            if previous.exists():
                try:
                    self._remove_path(previous)
                except OSError as error:
                    # The staging rename above is the publication commit
                    # boundary. Cleanup cannot turn a committed snapshot into
                    # a failure that rolls its identity back.
                    self.reporter.detail(
                        f"Deferred previous SSG snapshot cleanup: {error}"
                    )

    def _cleanup_previous_snapshots(self) -> None:
        pattern = f".{self.output_dir.name}.previous-*"
        for previous in sorted(self.output_dir.parent.glob(pattern), key=str):
            try:
                self._remove_path(previous)
            except OSError as error:
                self.reporter.detail(
                    f"Unable to clean previous SSG snapshot yet: {error}"
                )

    @staticmethod
    def _remove_path(path: Path) -> None:
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        else:
            path.unlink()

    @staticmethod
    def _format_failures(title: str, failures) -> str:
        lines = [title + ":"]
        for source, message in sorted(failures, key=lambda item: str(item[0])):
            lines.append(f"  - {source}: {message}")
        return "\n".join(lines)


def run_ssg(config: SSGConfig, reporter: Optional[Reporter] = None) -> int:
    active_reporter = reporter or Reporter(config.log)
    active_config = config
    if config.output_dir is None:
        temporary_output = Path(tempfile.mkdtemp(prefix="epub-browser-ssg-"))
        active_config = replace(config, output_dir=temporary_output)
    try:
        output = SSGPublisher(active_config, reporter=active_reporter).build()
    except (SSGBuildError, OSError) as error:
        active_reporter.error(str(error))
        return 4
    active_reporter.result(f"Files generated in: {output.resolve()}")
    return 0
