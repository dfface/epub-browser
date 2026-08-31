"""Dynamic Server-mode reader pages backed by immutable content caches."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import quote

from .asset_publisher import PublishedAssets
from .processor import EPUBProcessor
from .pdf_processor import PDFMetadata, PDFPageMetadata
from .source_format import EPUB_FORMAT, PDF_FORMAT
from .urls import SiteURLs


class ServerPageError(ValueError):
    """The derived content cache cannot safely render a reader page."""


class ServerPageRenderer:
    """Render current reader chrome around cached EPUB content.

    The cache intentionally contains only parsed EPUB metadata, sanitized
    chapter fragments, EPUB stylesheet references, and passive resources.
    This object hydrates the existing page renderer with that content and the
    freshly published asset manifest, avoiding a second HTML template system.
    """

    def __init__(
        self,
        public_dir,
        book_id,
        urls=None,
        source_format=EPUB_FORMAT,
        metadata_overrides=None,
        kindle=False,
    ):
        self.public_dir = Path(public_dir)
        self.book_id = str(book_id)
        self.urls = urls or SiteURLs()
        self.source_format = source_format
        self.metadata_overrides = dict(metadata_overrides or {})
        self.kindle = bool(kindle)
        if self.source_format not in {EPUB_FORMAT, PDF_FORMAT}:
            raise ServerPageError("Unsupported book format")
        self.book_dir = self.public_dir / "book" / self.book_id
        self.content_dir = self.public_dir / "book" / self.book_id / "content"
        self.pdf_dir = self.book_dir / "pdf"

    def render_kindle_index(self) -> str:
        """Render the dependency-free minimal reader index (EPUB only)."""
        if self.source_format != EPUB_FORMAT:
            raise ServerPageError("Kindle minimal pages are EPUB-only")
        return self._processor().create_kindle_index_page()

    def render_kindle_chapter(self, chapter_index: int) -> str:
        """Render the dependency-free minimal reader chapter (EPUB only)."""
        if self.source_format != EPUB_FORMAT:
            raise ServerPageError("Kindle minimal pages are EPUB-only")
        payload = self.chapter_content(chapter_index)
        return self._processor().create_kindle_chapter_page(
            payload["content"],
            payload["style_links"],
            chapter_index,
            payload["title"],
        )

    def render_index(self, initial_book_review=None) -> str:
        return self._active_processor().create_index_page(
            write=False,
            initial_book_review=initial_book_review,
        )

    def render_chapter(self, chapter_index: int) -> str:
        if self.source_format == PDF_FORMAT:
            return self.render_pdf_chapter(chapter_index)
        payload = self.chapter_content(chapter_index)
        title = payload["title"]
        content = payload["content"]
        style_links = payload["style_links"]
        return self._processor().create_chapter_template(
            content, style_links, chapter_index, title
        )

    def render_pdf_chapter(self, chapter_index: int) -> str:
        metadata, processor = self._pdf_processor()
        if chapter_index < 0 or chapter_index >= len(metadata.pages):
            raise ServerPageError("Chapter not found")
        document_url = f"/api/books/{quote(self.book_id, safe='')}/document"
        try:
            return processor.create_pdf_chapter_template(chapter_index, document_url)
        except ValueError as error:
            raise ServerPageError("Chapter not found") from error

    def chapter_content(self, chapter_index: int) -> dict:
        """Return one validated cache payload without exposing its disk path."""
        payload = self._read_json(self.content_dir / f"chapter_{chapter_index}.json")
        if payload.get("index") != chapter_index:
            raise ServerPageError("Chapter cache does not match its requested index")
        title = payload.get("title")
        content = payload.get("content")
        style_links = payload.get("style_links")
        if not all(isinstance(value, str) for value in (title, content, style_links)):
            raise ServerPageError("Chapter cache is invalid")
        return {
            "index": chapter_index,
            "title": title,
            "content": content,
            "style_links": style_links,
        }

    def toc_bytes(self) -> bytes:
        if self.source_format == PDF_FORMAT:
            _metadata, processor = self._pdf_processor()
            return json.dumps(
                processor._build_toc_data(),
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
        path = self.content_dir / "toc.json"
        try:
            return path.read_bytes()
        except OSError as error:
            raise ServerPageError("Book table of contents is unavailable") from error

    def _processor(self) -> EPUBProcessor:
        metadata = self._read_json(self.content_dir / "metadata.json")
        for key in ("title", "authors", "tags"):
            if key in self.metadata_overrides:
                metadata[key] = self.metadata_overrides[key]
        # EPUBProcessor already owns the single source of truth for page
        # templates. Hydrating an instance avoids duplicating its large,
        # security-sensitive reader chrome while keeping transient state out
        # of the persistent cache.
        try:
            return EPUBProcessor.from_server_content_cache(
                book_id=self.book_id,
                metadata=metadata,
                asset_manifest=PublishedAssets(self._asset_manifest()),
                urls=self.urls,
                kindle_support=self.kindle,
            )
        except ValueError as error:
            raise ServerPageError("Book content cache is invalid") from error

    def _active_processor(self) -> EPUBProcessor:
        if self.source_format == PDF_FORMAT:
            return self._pdf_processor()[1]
        return self._processor()

    def _pdf_processor(self) -> tuple[PDFMetadata, EPUBProcessor]:
        payload = self._read_json(self.pdf_dir / "metadata.json")
        for key in ("title", "authors", "tags"):
            if key in self.metadata_overrides:
                payload[key] = self.metadata_overrides[key]
        try:
            raw_pages = payload["pages"]
            if payload.get("page_count") != len(raw_pages):
                raise ValueError
            pages = tuple(
                PDFPageMetadata(
                    page_number=page["page_number"],
                    width=page["width"],
                    height=page["height"],
                    outline_labels=tuple(page.get("outline_labels") or ()),
                )
                for page in raw_pages
            )
            if [page.page_number for page in pages] != list(range(1, len(pages) + 1)):
                raise ValueError
            metadata = PDFMetadata(
                title=payload.get("title"),
                authors=tuple(payload.get("authors") or ()),
                tags=tuple(payload.get("tags") or ()),
                language=payload.get("language"),
                pages=pages,
                encrypted=bool(payload["encrypted"]),
                has_extractable_text=bool(payload["has_extractable_text"]),
                cover=None,
            )
            processor = EPUBProcessor.from_pdf_metadata(
                book_id=self.book_id,
                metadata=metadata,
                cover_path=payload.get("cover"),
                asset_manifest=PublishedAssets(self._asset_manifest()),
                urls=self.urls,
                deployment_mode="server",
            )
        except (KeyError, TypeError, ValueError) as error:
            raise ServerPageError("PDF metadata cache is invalid") from error
        return metadata, processor

    def _asset_manifest(self) -> dict[str, str]:
        manifest = self._read_json(self.public_dir / "assets" / "asset-manifest.json")
        if not all(isinstance(key, str) and isinstance(value, str) for key, value in manifest.items()):
            raise ServerPageError("Asset manifest is invalid")
        return manifest

    @staticmethod
    def _read_json(path: Path):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ServerPageError(f"Unreadable Server content cache: {path.name}") from error
        if not isinstance(value, dict):
            raise ServerPageError(f"Invalid Server content cache: {path.name}")
        return value
