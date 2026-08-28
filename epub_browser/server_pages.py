"""Dynamic Server-mode reader pages backed by immutable EPUB content cache."""

from __future__ import annotations

import json
from pathlib import Path

from .asset_publisher import PublishedAssets
from .processor import EPUBProcessor
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

    def __init__(self, public_dir, book_id, urls=None, metadata_overrides=None):
        self.public_dir = Path(public_dir)
        self.book_id = str(book_id)
        self.urls = urls or SiteURLs()
        self.metadata_overrides = dict(metadata_overrides or {})
        self.content_dir = self.public_dir / "book" / self.book_id / "content"

    def render_index(self, initial_book_review=None) -> str:
        return self._processor().create_index_page(
            write=False,
            initial_book_review=initial_book_review,
        )

    def render_chapter(self, chapter_index: int) -> str:
        payload = self.chapter_content(chapter_index)
        title = payload["title"]
        content = payload["content"]
        style_links = payload["style_links"]
        return self._processor().create_chapter_template(
            content, style_links, chapter_index, title
        )

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
            )
        except ValueError as error:
            raise ServerPageError("Book content cache is invalid") from error

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
