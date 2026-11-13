"""Server-only full-book search over the immutable EPUB content cache.

The index is a derived artifact: it never enters ``content/`` and can always be
rebuilt from ``metadata.json`` and ``chapter_<n>.json``.  Queries are literal
case-insensitive substring matches; offsets address the *original* chapter text
so the browser can validate a result against the rendered DOM before using it.
"""

from __future__ import annotations

import os
import re
import sqlite3
import tempfile
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from .epub_parsing import EPUBParseError, local_name, parse_xhtml_fragment
from .epub_sanitization import sanitize_html_fragment

INDEX_VERSION = "epub-book-search-v1"
SEARCH_PAGE_SIZE = 50
MAX_QUERY_CODEPOINTS = 128
SNIPPET_CONTEXT = 40

_BLOCK_TAGS = frozenset({
    "address", "article", "aside", "blockquote", "body", "caption", "dd",
    "details", "div", "dl", "dt", "figcaption", "figure", "footer", "form",
    "h1", "h2", "h3", "h4", "h5", "h6", "header", "hr", "html", "li", "main",
    "nav", "ol", "p", "pre", "section", "summary", "table", "tbody", "td",
    "tfoot", "th", "thead", "tr", "ul",
})
_SKIP_TAGS = frozenset({"script", "style", "template", "svg"})
_ASCII_WHITESPACE = re.compile(r"[ \t\r\n\f]+")
_BOOK_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}")


class BookSearchUnavailable(RuntimeError):
    """Search is temporarily unavailable for this book."""


class SearchGenerationChanged(RuntimeError):
    """The published content cache changed while a search was running."""


@dataclass(frozen=True)
class SearchGeneration:
    """Identity of one published EPUB content cache."""

    content_revision: str
    source_fingerprint: str
    content_device: int
    content_inode: int


def normalize_search_query(value) -> Optional[str]:
    """Return the literal query, or ``None`` when it must be rejected."""
    if not isinstance(value, str) or "\x00" in value:
        return None
    query = _ASCII_WHITESPACE.sub(" ", value).strip(" ")
    if not query or len(query) > MAX_QUERY_CODEPOINTS:
        return None
    return query


def extract_search_text(markup) -> str:
    """Extract inert, whitespace-normalized text from chapter markup."""
    sanitized = sanitize_html_fragment(markup)
    if not sanitized.strip():
        return ""
    try:
        nodes = parse_xhtml_fragment(sanitized)
    except EPUBParseError:
        return _ASCII_WHITESPACE.sub(" ", sanitized).strip(" ")
    parts: list[str] = []
    for node in nodes:
        _collect_text(node, parts)
    return _ASCII_WHITESPACE.sub(" ", "".join(parts)).strip(" ")


def _collect_text(node, parts: list[str]) -> None:
    if isinstance(node, str):
        parts.append(node)
        return
    if not isinstance(node.tag, str):
        return
    name = local_name(node.tag).casefold()
    if name in _SKIP_TAGS:
        if node.tail:
            parts.append(node.tail)
        return
    block = name in _BLOCK_TAGS
    if block or name in {"br", "hr"}:
        parts.append(" ")
    if node.text:
        parts.append(node.text)
    for child in node:
        _collect_text(child, parts)
    if block:
        parts.append(" ")
    if node.tail:
        parts.append(node.tail)


def _generation_header(generation: SearchGeneration) -> dict[str, str]:
    return {
        "content_revision": generation.content_revision,
        "source_fingerprint": generation.source_fingerprint,
        "content_device": str(generation.content_device),
        "content_inode": str(generation.content_inode),
    }


def build_book_search_index(path, renderer, generation: SearchGeneration) -> None:
    """Atomically rebuild one book index from validated content-cache chapters."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    chapter_count = renderer.chapter_count()
    chapter_payloads = []
    for index in range(chapter_count):
        payload = renderer.chapter_content(index)
        chapter_payloads.append(
            (index, payload["title"], extract_search_text(payload["content"]))
        )
    temporary = path.with_name(f"{path.name}.tmp-{os.getpid()}-{threading.get_ident()}")
    temporary.unlink(missing_ok=True)
    try:
        connection = sqlite3.connect(str(temporary))
        try:
            connection.execute(
                "CREATE TABLE chapters ("
                "chapter_index INTEGER PRIMARY KEY,"
                "title TEXT NOT NULL,"
                "text TEXT NOT NULL,"
                "folded TEXT NOT NULL"
                ")"
            )
            connection.execute(
                "CREATE TABLE index_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
            )
            fts_available = _create_fts_table(connection)
            meta = {
                "index_version": INDEX_VERSION,
                "chapter_count": str(chapter_count),
                "fts": "1" if fts_available else "0",
                **_generation_header(generation),
            }
            connection.executemany(
                "INSERT INTO index_meta (key, value) VALUES (?, ?)", meta.items()
            )
            for index, title, text in chapter_payloads:
                folded = text.casefold()
                connection.execute(
                    "INSERT INTO chapters (chapter_index, title, text, folded) "
                    "VALUES (?, ?, ?, ?)",
                    (index, title, text, folded),
                )
                if fts_available:
                    connection.execute(
                        "INSERT INTO chapters_fts (rowid, folded) VALUES (?, ?)",
                        (index, folded),
                    )
            connection.commit()
        finally:
            connection.close()
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _create_fts_table(connection: sqlite3.Connection) -> bool:
    try:
        connection.execute(
            "CREATE VIRTUAL TABLE chapters_fts USING fts5("
            "folded, content='chapters', content_rowid='chapter_index',"
            "tokenize='trigram case_sensitive 1'"
            ")"
        )
    except sqlite3.OperationalError:
        return False
    return True


def read_index_meta(path) -> Optional[dict[str, str]]:
    """Return index metadata, or ``None`` when the file is missing/unreadable."""
    try:
        connection = sqlite3.connect(
            f"file:{Path(path).as_posix()}?mode=ro", uri=True, timeout=5
        )
    except sqlite3.Error:
        return None
    try:
        rows = connection.execute("SELECT key, value FROM index_meta").fetchall()
    except sqlite3.Error:
        return None
    finally:
        connection.close()
    return {str(key): str(value) for key, value in rows}


def index_matches_generation(path, generation: SearchGeneration) -> bool:
    meta = read_index_meta(path)
    if not meta or meta.get("index_version") != INDEX_VERSION:
        return False
    return all(
        meta.get(key) == value for key, value in _generation_header(generation).items()
    )


def _fts_phrase(folded_query: str) -> str:
    return '"' + folded_query.replace('"', '""') + '"'


def _candidate_chapters(connection, folded_query: str) -> Optional[list[int]]:
    """Return matching chapter rowids through trigram FTS, or ``None``."""
    if len(folded_query) < 3:
        return None
    try:
        rows = connection.execute(
            "SELECT rowid FROM chapters_fts WHERE chapters_fts MATCH ?",
            (_fts_phrase(folded_query),),
        ).fetchall()
    except sqlite3.Error:
        return None
    return sorted(int(row[0]) for row in rows)


def query_book_search_index(
    path, query: str, *, page: int = 1, use_fts: Optional[bool] = None
) -> dict:
    """Return one page of literal hits in reading order plus the total count."""
    start_at = max(0, (max(1, page) - 1) * SEARCH_PAGE_SIZE)
    stop_at = start_at + SEARCH_PAGE_SIZE
    connection = sqlite3.connect(
        f"file:{Path(path).as_posix()}?mode=ro", uri=True, timeout=5
    )
    try:
        meta = dict(connection.execute("SELECT key, value FROM index_meta").fetchall())
        folded_query = query.casefold()
        candidates = None
        if use_fts is not False and meta.get("fts") == "1":
            candidates = _candidate_chapters(connection, folded_query)
            if candidates is not None and not candidates:
                return _search_page([], 0, page)
        if candidates is None:
            rows = connection.execute(
                "SELECT chapter_index, title, text FROM chapters ORDER BY chapter_index"
            )
        else:
            placeholders = ",".join("?" for _ in candidates)
            rows = connection.execute(
                "SELECT chapter_index, title, text FROM chapters "
                f"WHERE chapter_index IN ({placeholders}) ORDER BY chapter_index",
                candidates,
            )
        results = []
        total = 0
        for chapter_index, title, text in rows:
            utf16, _ = _utf16_offsets(text)
            for start, end in _chapter_hits(text, folded_query):
                if start_at <= total < stop_at:
                    results.append({
                        "chapter_index": int(chapter_index),
                        "chapter_title": title,
                        "start_offset": utf16[start],
                        "end_offset": utf16[end],
                        "before": _trimmed_before(text, start),
                        "match": text[start:end],
                        "after": _trimmed_after(text, end),
                    })
                total += 1
        return _search_page(results, total, page)
    finally:
        connection.close()


def _search_page(results: list[dict], total: int, page: int) -> dict:
    return {
        "results": results,
        "page": max(1, page),
        "page_size": SEARCH_PAGE_SIZE,
        "total": total,
    }


def _trimmed_before(text: str, start: int) -> str:
    begin = max(0, start - SNIPPET_CONTEXT)
    snippet = text[begin:start]
    if begin == 0 or not snippet:
        return snippet
    # Drop a leading partial word so snippets do not open mid-word. Only
    # space-separated (ASCII) scripts are trimmed; CJK excerpts stay intact.
    previous, head = text[begin - 1], snippet[0]
    if previous.isascii() and previous.isalnum() and head.isascii() and head.isalnum():
        space = snippet.find(" ")
        if space != -1:
            snippet = snippet[space + 1:]
    return snippet


def _trimmed_after(text: str, end: int) -> str:
    limit = min(len(text), end + SNIPPET_CONTEXT)
    snippet = text[end:limit]
    if limit == len(text) or not snippet:
        return snippet
    following, tail = text[limit], snippet[-1]
    if tail.isascii() and tail.isalnum() and following.isascii() and following.isalnum():
        space = snippet.rfind(" ")
        if space != -1:
            snippet = snippet[:space]
    return snippet


def _chapter_hits(text: str, folded_query: str):
    """Yield original-text ``(start, end)`` codepoint ranges for casefolded hits."""
    if not folded_query:
        return
    folded = text.casefold()
    if folded_query not in folded:
        return
    boundaries: dict[int, int] = {0: 0}
    position = 0
    for index, character in enumerate(text):
        position += len(character.casefold())
        boundaries[position] = index + 1
    search_from = 0
    while True:
        found = folded.find(folded_query, search_from)
        if found < 0:
            return
        end = found + len(folded_query)
        start_index = boundaries.get(found)
        end_index = boundaries.get(end)
        if start_index is not None and end_index is not None and end_index > start_index:
            yield start_index, end_index
            search_from = end
        else:
            search_from = found + 1


def _utf16_offsets(text: str) -> tuple[list[int], int]:
    offsets = [0] * (len(text) + 1)
    position = 0
    for index, character in enumerate(text):
        offsets[index] = position
        position += 2 if ord(character) > 0xFFFF else 1
    offsets[len(text)] = position
    return offsets, position


class BookSearchIndexStore:
    """Disk-backed LRU cache of per-book search indexes."""

    def __init__(self, root, limit: Callable[[], int]):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._limit = limit
        self._lock = threading.Lock()
        self._book_locks: dict[str, threading.Lock] = {}
        self._readers: dict[str, int] = {}
        self._needs_trim = False

    def path_for(self, book_id: str) -> Path:
        if not _BOOK_ID_PATTERN.fullmatch(book_id):
            raise BookSearchUnavailable("Book is unavailable")
        return self.root / f"{book_id}.sqlite3"

    @contextmanager
    def lease(self, book_id: str):
        with self._lock:
            self._readers[book_id] = self._readers.get(book_id, 0) + 1
        try:
            yield
        finally:
            with self._lock:
                remaining = self._readers.get(book_id, 0) - 1
                if remaining > 0:
                    self._readers[book_id] = remaining
                else:
                    self._readers.pop(book_id, None)
                trim = self._needs_trim
            if trim:
                self.trim()

    def is_current(self, book_id: str, generation: SearchGeneration) -> bool:
        """Return whether a usable index already matches this cache generation."""
        try:
            return index_matches_generation(self.path_for(book_id), generation)
        except BookSearchUnavailable:
            return False

    def search(self, book_id, query, generation, renderer, page=1) -> dict:
        path = self.path_for(book_id)
        with self.lease(book_id):
            with self._book_lock(book_id):
                if not index_matches_generation(path, generation):
                    if renderer is None:
                        raise BookSearchUnavailable("Book content is not cached")
                    build_book_search_index(path, renderer, generation)
                try:
                    result = query_book_search_index(path, query, page=page)
                except sqlite3.DatabaseError:
                    if renderer is None:
                        raise BookSearchUnavailable("Book search index is unavailable")
                    build_book_search_index(path, renderer, generation)
                    result = query_book_search_index(path, query, page=page)
                try:
                    os.utime(path, None)
                except OSError:
                    pass
            self.trim()
            return result

    def _book_lock(self, book_id: str) -> threading.Lock:
        with self._lock:
            lock = self._book_locks.get(book_id)
            if lock is None:
                lock = threading.Lock()
                self._book_locks[book_id] = lock
            return lock

    def trim(self) -> None:
        with self._lock:
            limit = max(1, int(self._limit()))
            candidates = []
            for path in self.root.glob("*.sqlite3"):
                try:
                    candidates.append((path.stat().st_mtime_ns, path))
                except OSError:
                    continue
            candidates.sort(reverse=True)
            self._needs_trim = False
            for _, path in candidates[limit:]:
                book_id = path.name[: -len(".sqlite3")]
                if self._readers.get(book_id):
                    self._needs_trim = True
                    continue
                try:
                    path.unlink()
                except OSError:
                    self._needs_trim = True


class BookSearchService:
    """Search one book through the current published cache generation."""

    def __init__(self, public_dir, store, *, library_manager=None, index_store=None):
        self.public_dir = Path(public_dir)
        self.store = store
        self.library_manager = library_manager
        if index_store is not None:
            self.indexes = index_store
        elif library_manager is not None:
            self.indexes = library_manager.search_indexes
        else:
            root = Path(tempfile.gettempdir()) / "epub-browser-search"
            digest = str(abs(hash(str(self.public_dir.resolve()))))
            self.indexes = BookSearchIndexStore(
                root / digest,
                limit=lambda: self.store.get_general_settings()[
                    "search_index_cache_limit"
                ],
            )

    def search(self, book_id: str, query: str, page: int = 1) -> dict:
        if self.library_manager is None:
            return self._search_published_directory(book_id, query, page)
        from .server_library import BookCacheUnavailable

        restore = False
        for attempt in range(2):
            try:
                with self.library_manager.book_cache(
                    book_id, read=True, restore=restore
                ):
                    generation = self.library_manager.search_generation(book_id)
                    if generation is None:
                        raise BookSearchUnavailable("Book search is unavailable")
                    if not restore and not self.indexes.is_current(book_id, generation):
                        restore = True
                        continue
                    result = self.indexes.search(
                        book_id, query, generation, self._renderer(book_id), page
                    )
                    if self.library_manager.search_generation(book_id) != generation:
                        if attempt == 0:
                            restore = False
                            continue
                        raise SearchGenerationChanged()
                    return result
            except BookCacheUnavailable as error:
                raise BookSearchUnavailable("Book search is unavailable") from error
        raise BookSearchUnavailable("Book search is unavailable")

    def _search_published_directory(self, book_id: str, query: str, page: int = 1) -> dict:
        for attempt in range(2):
            generation = self._directory_generation(book_id)
            if generation is None:
                raise BookSearchUnavailable("Book search is unavailable")
            result = self.indexes.search(
                book_id, query, generation, self._renderer(book_id), page
            )
            if self._directory_generation(book_id) != generation:
                if attempt == 0:
                    continue
                raise SearchGenerationChanged()
            return result
        raise BookSearchUnavailable("Book search is unavailable")

    def _directory_generation(self, book_id: str) -> Optional[SearchGeneration]:
        from .processor import SERVER_OUTPUT_REVISION_FILE

        directory = self.public_dir / "book" / book_id
        content = directory / "content"
        try:
            stat_result = os.stat(content)
            revision = (directory / SERVER_OUTPUT_REVISION_FILE).read_text(
                encoding="utf-8"
            ).strip()
            metadata = os.stat(content / "metadata.json")
        except OSError:
            return None
        return SearchGeneration(
            content_revision=revision,
            source_fingerprint=f"{metadata.st_size}:{metadata.st_mtime_ns}",
            content_device=stat_result.st_dev,
            content_inode=stat_result.st_ino,
        )

    def _renderer(self, book_id: str):
        from .server_pages import ServerPageRenderer

        return ServerPageRenderer(self.public_dir, book_id)
