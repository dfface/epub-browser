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

from .asset_publisher import AssetPublisher, PublishedAssets
from .cli import SSGConfig
from .identity import derive_ssg_book_id
from .models import BookMetadata, ConvertedBook
from .processor import EPUBProcessor
from .reporting import Reporter
from .site import LibraryBook, publish_library_shell
from .urls import SiteURLs


class SSGBuildError(RuntimeError):
    pass


@dataclass(frozen=True)
class _PreparedBook:
    source: Path
    book_id: str


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
        prepared = self._prepare_books()
        self._validate_output_target(tuple(book.source for book in prepared))

        self.output_dir.parent.mkdir(parents=True, exist_ok=True)
        staging = Path(
            tempfile.mkdtemp(
                prefix=f".{self.output_dir.name}.staging-",
                dir=self.output_dir.parent,
            )
        )
        try:
            assets_dir = Path(__file__).with_name("assets")
            assets = AssetPublisher(assets_dir, staging, urls=self.urls).publish()
            books = self._convert_all(prepared, staging, assets)
            publish_library_shell(staging, books, assets, self.urls)
            self._validate_snapshot(staging, books, assets)
            self._activate(staging)
            return self.output_dir
        finally:
            if staging.exists():
                shutil.rmtree(staging, ignore_errors=True)

    def _prepare_books(self) -> tuple[_PreparedBook, ...]:
        sources = self._discover_sources()
        failures = []
        prepared = []
        with tempfile.TemporaryDirectory(prefix="epub-browser-ssg-probe-") as directory:
            probe_root = Path(directory)
            for source in sources:
                processor = EPUBProcessor(
                    source,
                    probe_root,
                    PublishedAssets({}),
                    urls=self.urls,
                    reporter=self.reporter,
                )
                try:
                    if not processor.extract_epub():
                        raise ValueError("unable to extract EPUB archive")
                    opf_path = processor.parse_container()
                    if not opf_path:
                        raise ValueError("unable to locate EPUB package")
                    if not processor.parse_opf(opf_path):
                        raise ValueError("unable to parse EPUB package")
                    structure = self._book_structure(processor)
                    book_id = derive_ssg_book_id(processor.get_metadata(), structure)
                    prepared.append(_PreparedBook(source=source, book_id=book_id))
                except Exception as error:
                    failures.append((source, str(error)))
                finally:
                    processor.cleanup()

        if failures:
            raise SSGBuildError(self._format_failures("Unable to inspect EPUB inputs", failures))

        collisions = {}
        for book in prepared:
            collisions.setdefault(book.book_id, []).append(book.source)
        duplicate_groups = {
            book_id: paths
            for book_id, paths in collisions.items()
            if len(paths) > 1
        }
        if duplicate_groups:
            lines = ["Duplicate deterministic SSG book IDs:"]
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
            resolved = source.resolve()
            if resolved.is_file():
                if resolved.suffix.lower() == ".epub":
                    discovered.append(resolved)
                else:
                    failures.append((resolved, "file is not an EPUB"))
                continue
            if not resolved.is_dir():
                failures.append((resolved, "path is not a regular file or directory"))
                continue
            for candidate in resolved.rglob("*"):
                relative = candidate.relative_to(resolved)
                if any(part.startswith(".") for part in relative.parts):
                    continue
                if candidate.is_file() and candidate.suffix.lower() == ".epub":
                    discovered.append(candidate.resolve())

        if failures:
            raise SSGBuildError(self._format_failures("Invalid SSG sources", failures))
        unique = tuple(sorted(set(discovered), key=str))
        if not unique:
            raise SSGBuildError("No EPUB files were discovered")
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
            if source == self.output_dir or source.is_relative_to(self.output_dir):
                raise SSGBuildError(
                    f"Output directory would own an input EPUB: {self.output_dir}"
                )

    @staticmethod
    def _book_structure(processor: EPUBProcessor):
        if processor.toc:
            return tuple(
                (
                    item.get("title") or "",
                    item.get("src") or "",
                    int(item.get("level") or 0),
                )
                for item in processor.toc
            )
        return tuple(
            (chapter.get("title") or "", chapter.get("path") or "", 0)
            for chapter in processor.chapters
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
            )
        finally:
            cleanup = getattr(processor, "cleanup", None)
            if cleanup:
                cleanup()

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
            "assets/manifest.json",
            "assets/manifest.en.json",
            "assets/manifest.zh-CN.json",
            "sw.js",
        )
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

        forbidden_names = {
            "epub-browser.db",
            "annotations.db",
            "migration-state.json",
            "catalog.json",
        }
        for path in staging.rglob("*"):
            if path.name in forbidden_names or "data" in path.relative_to(staging).parts:
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
                self._remove_path(previous)

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
    except SSGBuildError as error:
        active_reporter.error(str(error))
        return 4
    active_reporter.result(f"Files generated in: {output.resolve()}")
    return 0
