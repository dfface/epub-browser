"""Versioned, Bearer-only API surface for Server deployments."""

from __future__ import annotations

import json
import re
import uuid
from contextlib import nullcontext
from dataclasses import dataclass
from functools import cache
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
from typing import Callable, Optional, Tuple

from starlette.responses import JSONResponse, PlainTextResponse, Response
from starlette.routing import Match, Route

from .dictionary_formats import normalize_lookup
from .i18n_bundles import get_bundle, resolve_request_locale
from .kindle import KINDLE_MEMO_MAX_LENGTH, valid_kindle_memo
from .pat import AuthenticatedPAT, PAT_SCOPES
from .server_concurrency import run_db, run_render
from .server_library import BookCacheUnavailable
from .server_pages import ServerPageError, ServerPageRenderer
from .source_format import PDF_FORMAT
from .vocabulary import MASTERY_STATES, MAX_PAGE_SIZE, MAX_QUERY_LENGTH, PAGE_SIZE, vocabulary_page_options


PUBLIC_API_CONTEXT_KEY = "epub_browser.public_api_context"
_LIST_LIMIT = 24
_MAX_LIST_LIMIT = 100
_MAX_LIST_OFFSET = 2**63 - 1
_PRIVATE_HEADERS = {"Cache-Control": "private, no-store"}
_BEARER_PATTERN = re.compile(r"^Bearer ([^\s,]+)$")


@dataclass(frozen=True)
class PublicAPIContext:
    store: object
    public_dir: Path
    book_cache: Optional[Callable] = None


@dataclass(frozen=True)
class PublicAPIOperation:
    path: str
    methods: Tuple[str, ...]
    required_scope: str
    summary: str
    operation_id: str
    handler: Callable


def public_api_error(code: str, message: str, status: int, *, headers=None):
    response_headers = dict(_PRIVATE_HEADERS)
    response_headers.update(headers or {})
    return JSONResponse(
        {"code": code, "message": message},
        status_code=status,
        headers=response_headers,
    )


def _context(request) -> PublicAPIContext:
    return getattr(request.app.state, PUBLIC_API_CONTEXT_KEY)


async def require_pat(request, scope: str):
    """Authenticate one exact Bearer credential and enforce one operation scope."""
    values = request.headers.getlist("authorization")
    match = _BEARER_PATTERN.fullmatch(values[0]) if len(values) == 1 else None
    authenticated = (
        await run_db(
            _context(request).store.authenticate_personal_access_token,
            match.group(1),
        )
        if match is not None
        else None
    )
    if authenticated is None:
        return public_api_error(
            "invalid_token",
            "A valid personal access token is required",
            401,
            headers={"WWW-Authenticate": 'Bearer realm="epub-browser"'},
        )
    if scope not in authenticated.effective_scopes:
        return public_api_error(
            "insufficient_scope",
            "The personal access token does not grant the required scope",
            403,
            headers={
                "WWW-Authenticate": (
                    'Bearer realm="epub-browser", error="insufficient_scope", '
                    'scope="{}"'.format(scope)
                )
            },
        )
    return authenticated


def _book_payload(store, book):
    metadata = store.managed_book_metadata(book.book_id)
    authors = list(metadata.get("authors") or ())
    return {
        "id": book.book_id,
        "title": metadata.get("title") or "EPUB Book",
        "author": ", ".join(authors),
        "authors": authors,
        "language": metadata.get("language") or "",
        "tags": list(metadata.get("tags") or ()),
        "format": book.source_format,
        "visibility": book.visibility,
        "created_at": book.created_at,
        "updated_at": book.updated_at,
    }


async def _list_books(request, authenticated: AuthenticatedPAT):
    store = _context(request).store
    page = request.state.public_list_page

    def load():
        books = store.visible_books(
            authenticated.principal, source_format=page.filters.get("format"), **page.window
        )
        return [_book_payload(store, book) for book in books[:page.limit]], len(books) > page.limit

    items, has_more = await run_db(load)
    return page.response(items, has_more=has_more)


def _authorized_book_sync(store, authenticated, book_id):
    if not store.can_read_book(
        authenticated.principal.user_id,
        authenticated.principal.role,
        book_id,
    ):
        return None
    return store.book_by_id(book_id)


async def _authorized_book(request, authenticated, book_id):
    return await run_db(
        _authorized_book_sync, _context(request).store, authenticated, book_id
    )


async def _book_detail(request, authenticated: AuthenticatedPAT):
    book = await _authorized_book(
        request, authenticated, request.path_params["book_id"]
    )
    if book is None:
        return public_api_error("book_not_found", "Book not found", 404)
    store = _context(request).store
    payload = await run_db(_book_payload, store, book)
    return JSONResponse(
        {"book": payload},
        headers={"Cache-Control": "private, no-store"},
    )


def _chapter_list(renderer):
    if renderer.source_format == PDF_FORMAT:
        metadata, _processor = renderer._pdf_renderer()
        return [
            {
                "index": index,
                "title": f"Page {page.page_number}",
                "format": PDF_FORMAT,
                "page_number": page.page_number,
            }
            for index, page in enumerate(metadata.pages)
        ]
    metadata = renderer._read_json(renderer.content_dir / "metadata.json")
    chapters = metadata.get("chapters")
    if not isinstance(chapters, list):
        raise ServerPageError("Book content cache is invalid")
    result = []
    for index, chapter in enumerate(chapters):
        if not isinstance(chapter, dict) or not isinstance(chapter.get("title"), str):
            raise ServerPageError("Book content cache is invalid")
        result.append({"index": index, "title": chapter["title"]})
    return result


async def _book_chapters(request, authenticated: AuthenticatedPAT):
    book_id = request.path_params["book_id"]
    book = await _authorized_book(request, authenticated, book_id)
    if book is None:
        return public_api_error("book_not_found", "Book not found", 404)
    store = _context(request).store
    public_dir = _context(request).public_dir

    book_cache = _context(request).book_cache

    def _chapter_items():
        with book_cache(book_id, restore=False) if book_cache else nullcontext():
            return _chapter_list(ServerPageRenderer(
                public_dir,
                book_id,
                source_format=book.source_format,
                metadata_overrides=store.managed_book_metadata(book_id),
            ))

    try:
        items = await run_render(_chapter_items)
    except (ServerPageError, BookCacheUnavailable):
        return public_api_error(
            "book_content_unavailable", "Book content is unavailable", 503
        )
    page = request.state.public_list_page
    return page.response(items[page.offset:page.offset + page.limit + 1])


class _PlainTextExtractor(HTMLParser):
    _BLOCKS = frozenset({"p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "li", "br"})
    _IGNORED = frozenset({"script", "style"})

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.ignored_depth = 0

    def handle_starttag(self, tag, attrs):
        del attrs
        if tag in self._IGNORED:
            self.ignored_depth += 1
        elif not self.ignored_depth and tag in self._BLOCKS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self._IGNORED and self.ignored_depth:
            self.ignored_depth -= 1
        elif not self.ignored_depth and tag in self._BLOCKS:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.ignored_depth:
            self.parts.append(data)

    def text(self):
        value = re.sub(r"[ \t\r\f\v]+", " ", "".join(self.parts))
        return re.sub(r"\n\s*\n+", "\n", value).strip()


async def _chapter_detail(request, authenticated: AuthenticatedPAT):
    book_id = request.path_params["book_id"]
    book = await _authorized_book(request, authenticated, book_id)
    if book is None:
        return public_api_error("book_not_found", "Book not found", 404)
    values = request.query_params.getlist("format")
    output_format = values[0] if len(values) == 1 else "html" if not values else None
    if output_format not in {"html", "text"}:
        return public_api_error("invalid_format", "Format must be html or text", 400)
    try:
        chapter_index = int(request.path_params["chapter_index"])
        if chapter_index < 0 or str(chapter_index) != request.path_params["chapter_index"]:
            raise ValueError
    except (TypeError, ValueError):
        return public_api_error("chapter_not_found", "Chapter not found", 404)
    store = _context(request).store
    public_dir = _context(request).public_dir

    book_cache = _context(request).book_cache

    def _load_chapter():
        with book_cache(book_id, read=True, restore=book.source_format != PDF_FORMAT) if book_cache else nullcontext():
            renderer = ServerPageRenderer(
                public_dir,
                book_id,
                source_format=book.source_format,
                metadata_overrides=store.managed_book_metadata(book_id),
            )
            chapters = _chapter_list(renderer)
            if chapter_index >= len(chapters):
                return "chapter_not_found", None, None
            if renderer.source_format == PDF_FORMAT:
                return "pdf", chapters[chapter_index], None
            return "html", None, renderer.chapter_content(chapter_index)

    try:
        outcome, chapter_meta, chapter = await run_render(_load_chapter)
    except (ServerPageError, BookCacheUnavailable):
        return public_api_error(
            "book_content_unavailable", "Book content is unavailable", 503
        )
    if outcome == "chapter_not_found":
        return public_api_error("chapter_not_found", "Chapter not found", 404)
    if outcome == "pdf":
        if output_format == "text":
            return PlainTextResponse(
                "", headers={"Cache-Control": "private, no-store"}
            )
        return JSONResponse(
            {"chapter": {
                **chapter_meta,
                "content_type": "application/pdf-page",
                "content_html": None,
                "text": "",
            }},
            headers={"Cache-Control": "private, no-store"},
        )
    if output_format == "text":
        def _extract_text():
            extractor = _PlainTextExtractor()
            extractor.feed(chapter["content"])
            extractor.close()
            return extractor.text()

        return PlainTextResponse(
            await run_render(_extract_text),
            headers={"Cache-Control": "private, no-store"},
        )
    return JSONResponse(
        {
            "index": chapter["index"],
            "title": chapter["title"],
            "content_html": chapter["content"],
        },
        headers={"Cache-Control": "private, no-store"},
    )


async def bounded_public_json_object(request, maximum_size=64 * 1024):
    content_type = request.headers.get('content-type', '').split(';', 1)[0]
    if content_type.strip().casefold() != 'application/json':
        return None, 'unsupported_media_type'
    content_length = request.headers.get('content-length')
    if content_length:
        try:
            if int(content_length) < 0:
                return None, 'invalid_json'
            if int(content_length) > maximum_size:
                return None, 'body_too_large'
        except ValueError:
            return None, 'invalid_json'
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > maximum_size:
            return None, 'body_too_large'
    try:
        data = json.loads(bytes(body).decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None, 'invalid_json'
    if not isinstance(data, dict):
        return None, 'invalid_json'
    return data, None

async def _json_object(request):
    try:
        value = await request.json()
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _bookshelf_document(store, user_id):
    row = store.get_bookshelf(user_id)
    if row is None:
        return 0, {"items": [], "groups": {}, "order": []}
    version, serialized = row
    try:
        data = json.loads(serialized) if isinstance(serialized, str) else serialized
    except json.JSONDecodeError:
        raise ValueError("Invalid bookshelf document")
    if not isinstance(data, dict):
        raise ValueError("Invalid bookshelf document")
    return version, data


async def _get_bookshelf(request, authenticated):
    version, data = await run_db(
        _bookshelf_document,
        _context(request).store,
        authenticated.principal.user_id,
    )
    return JSONResponse(
        {"version": version, "data": data},
        headers={"Cache-Control": "private, no-store"},
    )


async def _put_bookshelf(request, authenticated):
    data = await _json_object(request)
    version = data.get("version") if data else None
    document = data.get("data") if data else None
    if isinstance(version, bool) or not isinstance(version, int) or version < 0 or not isinstance(document, dict):
        return public_api_error("invalid_bookshelf", "Invalid bookshelf document", 400)
    store = _context(request).store
    user_id = authenticated.principal.user_id
    current_version, current_data = await run_db(
        _bookshelf_document, store, user_id
    )
    if version != current_version:
        return JSONResponse({
            "code": "bookshelf_conflict",
            "message": "Bookshelf changed on the server",
            "version": current_version,
            "data": current_data,
        }, status_code=409, headers=_PRIVATE_HEADERS)
    next_version = version + 1
    if version == 0:
        await run_db(store.create_bookshelf, user_id, next_version, document)
    else:
        await run_db(store.update_bookshelf, user_id, next_version, document)
    return JSONResponse(
        {"version": next_version, "data": document},
        headers={"Cache-Control": "private, no-store"},
    )


async def _list_progress(request, authenticated):
    principal = authenticated.principal
    page = request.state.public_list_page
    items = await run_db(
        _context(request).store.list_reading_progress,
        principal.user_id, visible_to=principal, **page.filters, **page.window,
    )
    return page.response(items)


async def _progress_item(request, authenticated):
    store = _context(request).store
    book_id = request.path_params["book_id"]
    book = await _authorized_book(request, authenticated, book_id)
    if book is None:
        return public_api_error("book_not_found", "Book not found", 404)
    user_id = authenticated.principal.user_id
    if request.method in ("GET", "HEAD"):
        chapter_index = await run_db(
            store.get_reading_progress, user_id, book_id
        )
        if chapter_index is None:
            return public_api_error("progress_not_found", "Reading progress not found", 404)
        return JSONResponse(
            {"book_id": book_id, "chapter_index": chapter_index},
            headers={"Cache-Control": "private, no-store"},
        )
    if request.method == "DELETE":
        await run_db(store.delete_reading_progress, user_id, book_id)
        return Response(status_code=204, headers={"Cache-Control": "private, no-store"})
    data = await _json_object(request)
    chapter_index = data.get("chapter_index") if data else None
    if isinstance(chapter_index, bool) or not isinstance(chapter_index, int) or chapter_index < 0:
        return public_api_error("invalid_chapter_index", "Invalid chapter index", 400)
    public_dir = _context(request).public_dir

    book_cache = _context(request).book_cache

    def _chapters():
        with book_cache(book_id, restore=False) if book_cache else nullcontext():
            return _chapter_list(ServerPageRenderer(
                public_dir,
                book_id,
                source_format=book.source_format,
                metadata_overrides=store.managed_book_metadata(book_id),
            ))

    try:
        chapters = await run_render(_chapters)
    except (ServerPageError, BookCacheUnavailable):
        return public_api_error("book_content_unavailable", "Book content is unavailable", 503)
    if chapter_index >= len(chapters):
        return public_api_error("invalid_chapter_index", "Invalid chapter index", 400)
    await run_db(store.set_reading_progress, user_id, book_id, chapter_index)
    return JSONResponse(
        {"book_id": book_id, "chapter_index": chapter_index},
        headers={"Cache-Control": "private, no-store"},
    )


async def _list_annotations(request, authenticated):
    principal = authenticated.principal
    page = request.state.public_list_page
    items = await run_db(
        _context(request).store.list_annotations,
        book_hash=page.filters.get("book_id"), chapter_index=page.filters.get("chapter_index"),
        user_id=principal.user_id, visible_to=principal, **page.window,
    )
    return page.response(items)


def _valid_annotation(data):
    return (
        isinstance(data, dict)
        and isinstance(data.get("book_hash"), str)
        and data.get("book_hash")
        and not isinstance(data.get("chapter_index"), bool)
        and isinstance(data.get("chapter_index"), int)
        and data.get("chapter_index") >= 0
        and isinstance(data.get("text"), str)
        and 1 <= len(data.get("text")) <= 100_000
        and isinstance(data.get("note", ""), str)
        and len(data.get("note", "")) <= 100_000
        and isinstance(data.get("color"), str)
        and 1 <= len(data.get("color")) <= 64
    )


async def _create_annotation(request, authenticated):
    data = await _json_object(request)
    if not _valid_annotation(data):
        return public_api_error("invalid_annotation", "Invalid annotation", 400)
    book_id = data["book_hash"]
    if await _authorized_book(request, authenticated, book_id) is None:
        return public_api_error("book_not_found", "Book not found", 404)
    annotation = {
        "id": data.get("id") if isinstance(data.get("id"), str) and 1 <= len(data["id"]) <= 128 else uuid.uuid4().hex,
        "book_hash": book_id,
        "chapter_index": data["chapter_index"],
        "text": data["text"],
        "note": data.get("note", ""),
        "startMeta": data.get("startMeta"),
        "endMeta": data.get("endMeta"),
        "color": data["color"],
        "created_at": data.get("created_at") or "",
        "updated_at": data.get("updated_at") or "",
    }
    store = _context(request).store

    try:
        await run_db(
            store.upsert_annotation,
            annotation,
            authenticated.principal.user_id,
        )
    except Exception:
        return public_api_error("annotation_conflict", "Annotation already exists", 409)
    stored = await run_db(
        store.get_annotation,
        annotation["id"],
        authenticated.principal.user_id,
    )
    return JSONResponse(
        {"annotation": stored},
        status_code=201,
        headers={"Cache-Control": "private, no-store"},
    )


async def _annotation_item(request, authenticated):
    store = _context(request).store
    user_id = authenticated.principal.user_id
    annotation_id = request.path_params["annotation_id"]
    stored = await run_db(store.get_annotation, annotation_id, user_id)
    if stored is None or await _authorized_book(
        request, authenticated, stored["book_hash"]
    ) is None:
        return public_api_error("annotation_not_found", "Annotation not found", 404)
    if request.method in ("GET", "HEAD"):
        return JSONResponse({"annotation": stored}, headers={"Cache-Control": "private, no-store"})
    if request.method == "DELETE":
        await run_db(store.delete_annotation, annotation_id, user_id)
        return Response(status_code=204, headers={"Cache-Control": "private, no-store"})
    data = await _json_object(request)
    allowed = {key: data[key] for key in ("note", "color", "chapter_index", "startMeta", "endMeta") if data and key in data}
    if not allowed or ("chapter_index" in allowed and (isinstance(allowed["chapter_index"], bool) or not isinstance(allowed["chapter_index"], int) or allowed["chapter_index"] < 0)):
        return public_api_error("invalid_annotation", "Invalid annotation", 400)
    updated = await run_db(
        store.update_annotation, annotation_id, allowed, user_id
    )
    return JSONResponse({"annotation": updated}, headers={"Cache-Control": "private, no-store"})


async def _list_reviews(request, authenticated):
    principal = authenticated.principal
    page = request.state.public_list_page
    items = await run_db(
        _context(request).store.list_book_reviews,
        principal.user_id, visible_to=principal, **page.filters, **page.window,
    )
    return page.response(items)


async def _review_item(request, authenticated):
    store = _context(request).store
    book_id = request.path_params["book_id"]
    if await _authorized_book(request, authenticated, book_id) is None:
        return public_api_error("book_not_found", "Book not found", 404)
    user_id = authenticated.principal.user_id
    if request.method in ("GET", "HEAD"):
        review = await run_db(store.get_book_review, book_id, user_id)
        if review is None:
            return public_api_error("review_not_found", "Review not found", 404)
        return JSONResponse({"review": review}, headers={"Cache-Control": "private, no-store"})
    if request.method == "DELETE":
        await run_db(store.delete_book_review, book_id, user_id)
        return Response(status_code=204, headers={"Cache-Control": "private, no-store"})
    data = await _json_object(request)
    rating = data.get("rating") if data else None
    review_text = data.get("review_text") if data else None
    if isinstance(rating, bool) or not isinstance(rating, int) or not 1 <= rating <= 5 or not isinstance(review_text, str) or len(review_text.strip()) > 10_000:
        return public_api_error("invalid_review", "Invalid review", 400)
    review = await run_db(
        store.upsert_book_review, book_id, user_id, rating, review_text
    )
    return JSONResponse({"review": review}, headers={"Cache-Control": "private, no-store"})


def _admin_user(store, user_id):
    try:
        return store.get_user(user_id)
    except KeyError:
        return None


def _user_payload(user):
    return {
        "id": user.user_id,
        "username": user.username,
        "role": user.role,
        "enabled": user.enabled,
        "created_at": user.created_at,
        "updated_at": user.updated_at,
    }


async def _admin_users(request, authenticated):
    page = request.state.public_list_page
    users = await run_db(_context(request).store.list_users, **page.window)
    return page.response([_user_payload(user) for user in users])


def _admin_user_list(method):
    async def handler(request, authenticated):
        store = _context(request).store
        user_id = request.path_params["user_id"]
        page = request.state.public_list_page

        def load():
            if _admin_user(store, user_id) is None:
                return None
            filters = page.filters
            if method == "list_annotations":
                return store.list_annotations(
                    user_id=user_id, book_hash=filters.get("book_id"),
                    chapter_index=filters.get("chapter_index"), **page.window,
                )
            return getattr(store, method)(user_id, **filters, **page.window)

        items = await run_db(load)
        if items is None:
            return public_api_error("user_not_found", "User not found", 404)
        return page.response(items)

    return handler


async def _admin_bookshelf(request, authenticated):
    del authenticated
    store = _context(request).store
    user_id = request.path_params["user_id"]

    def _load():
        if _admin_user(store, user_id) is None:
            return None
        return _bookshelf_document(store, user_id)

    result = await run_db(_load)
    if result is None:
        return public_api_error("user_not_found", "User not found", 404)
    version, data = result
    return JSONResponse({"version": version, "data": data}, headers={"Cache-Control": "private, no-store"})


async def _admin_reading_insights(request, authenticated):
    del authenticated
    store = _context(request).store
    user_id = request.path_params["user_id"]
    period = request.query_params.get("period", "overview")
    anchor_value = request.query_params.get("anchor", date.today().isoformat())
    timezone_name = request.query_params.get("timezone", "UTC")

    def _load():
        if _admin_user(store, user_id) is None:
            return None
        anchor = date.fromisoformat(anchor_value)
        return store.reading_insights(
            user_id, period, anchor, timezone_name, maximum_rank_limit=_MAX_LIST_LIMIT
        )

    try:
        insights = await run_db(_load)
    except (TypeError, ValueError, OverflowError):
        return public_api_error("invalid_reading_insights", "Invalid reading insights query", 400)
    if insights is None:
        return public_api_error("user_not_found", "User not found", 404)
    return JSONResponse({"insights": insights}, headers={"Cache-Control": "private, no-store"})


async def _kindle_memo(request, authenticated):
    store = _context(request).store
    user_id = authenticated.principal.user_id
    if request.method in ("GET", "HEAD"):
        settings = await run_db(store.get_kindle_screensaver, user_id)
        memo = settings["text"]
    else:
        data = await _json_object(request)
        memo = data.get("memo") if isinstance(data, dict) else None
        if not valid_kindle_memo(memo):
            message = get_bundle(resolve_request_locale(request))["apiDocs.error.invalidKindleMemo"]
            return public_api_error("invalid_memo", message.format(limit=KINDLE_MEMO_MAX_LENGTH), 400)
        await run_db(store.set_kindle_memo, user_id, memo)
    return JSONResponse({"memo": memo}, headers={"Cache-Control": "private, no-store"})


async def _vocabulary(request, authenticated):
    context = _context(request)
    store = context.store
    principal = authenticated.principal
    book_id = request.query_params.get("book_id")
    headers = {"Cache-Control": "private, no-store"}
    if book_id is not None and await _authorized_book(request, authenticated, book_id) is None:
        return public_api_error("book_not_found", "Book not found", 404)
    if request.method in ("GET", "HEAD"):
        try:
            page = request.state.public_list_page
            options = vocabulary_page_options(request.query_params)
            legacy = "page" in request.query_params or "page_size" in request.query_params
            if legacy and ("cursor" in request.query_params or "limit" in request.query_params):
                raise ValueError
            if not legacy:
                options.update(page_size=page.limit, offset=page.offset)
        except ValueError:
            return public_api_error("invalid_vocabulary_query", "Invalid vocabulary query", 400)
        result = await run_db(store.list_vocabulary, principal, book_id, **options)
        if legacy:
            return JSONResponse(result, headers=headers)
        return page.response(
            result["words"], has_more=page.offset + page.limit < result["total"]
        )

    if request.method == "POST":
        data, error = await bounded_public_json_object(request, maximum_size=16 * 1024)
        if error:
            return public_api_error("invalid_vocabulary_lookup", "Invalid vocabulary lookup", 400)
        book_id = data.get("book_id")
        chapter = data.get("chapter_index")
        lookup_id = data.get("lookup_id")
        word = data.get("word")
        if (
            not isinstance(book_id, str) or not book_id or type(chapter) is not int or chapter < 0
            or not isinstance(lookup_id, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", lookup_id)
            or not isinstance(word, str) or not word.strip() or len(word) > MAX_QUERY_LENGTH
        ):
            return public_api_error("invalid_vocabulary_lookup", "Invalid vocabulary lookup", 400)
        book = await _authorized_book(request, authenticated, book_id)
        if book is None:
            return public_api_error("book_not_found", "Book not found", 404)

        def chapter_exists():
            renderer = ServerPageRenderer(context.public_dir, book_id, source_format=book.source_format)
            return chapter < len(_chapter_list(renderer))

        try:
            exists = await run_render(chapter_exists)
        except ServerPageError:
            return public_api_error("book_content_unavailable", "Book content is unavailable", 503)
        if not exists:
            return public_api_error("invalid_vocabulary_lookup", "Invalid vocabulary lookup", 400)
        recorded = await run_db(
            store.record_vocabulary_lookup, principal, book_id, chapter,
            lookup_id, " ".join(word.split()), normalize_lookup(word),
        )
        if not recorded:
            return public_api_error("book_not_found", "Book not found", 404)
        return Response(status_code=204, headers=headers)

    mastery = None
    if request.method == "PATCH":
        data, error = await bounded_public_json_object(request, maximum_size=1024)
        if error or data.get("mastery") not in MASTERY_STATES:
            return public_api_error("invalid_vocabulary_mastery", "Invalid mastery state", 400)
        mastery = data["mastery"]
    changed = await run_db(
        store.change_vocabulary, principal, request.path_params["word_id"],
        book_id=book_id, mastery=mastery,
    )
    if not changed:
        return public_api_error("not_found", "Word not found", 404)
    if mastery is None:
        return Response(status_code=204, headers=headers)
    return JSONResponse({"mastery": mastery}, headers=headers)


def public_api_operations():
    return (
        PublicAPIOperation(
            path="/api/v1/books",
            methods=("GET",),
            required_scope="library:read",
            summary="List books visible to the token owner",
            operation_id="listBooks",
            handler=_list_books,
        ),
        PublicAPIOperation(
            path="/api/v1/books/{book_id}",
            methods=("GET",),
            required_scope="library:read",
            summary="Get one visible book",
            operation_id="getBook",
            handler=_book_detail,
        ),
        PublicAPIOperation(
            path="/api/v1/books/{book_id}/chapters",
            methods=("GET",),
            required_scope="library:read",
            summary="List a visible book's chapters",
            operation_id="listBookChapters",
            handler=_book_chapters,
        ),
        PublicAPIOperation(
            path="/api/v1/books/{book_id}/chapters/{chapter_index}",
            methods=("GET",),
            required_scope="library:read",
            summary="Read sanitized chapter content",
            operation_id="getBookChapter",
            handler=_chapter_detail,
        ),
        PublicAPIOperation("/api/v1/me/bookshelf", ("GET",), "bookshelf:read", "Get the token owner's bookshelf", "getMyBookshelf", _get_bookshelf),
        PublicAPIOperation("/api/v1/me/bookshelf", ("PUT",), "bookshelf:write", "Replace the token owner's bookshelf", "putMyBookshelf", _put_bookshelf),
        PublicAPIOperation("/api/v1/me/progress", ("GET",), "progress:read", "List the token owner's reading progress", "listMyProgress", _list_progress),
        PublicAPIOperation("/api/v1/me/progress/{book_id}", ("GET",), "progress:read", "Get reading progress for one book", "getMyProgress", _progress_item),
        PublicAPIOperation("/api/v1/me/progress/{book_id}", ("PUT",), "progress:write", "Update reading progress for one book", "putMyProgress", _progress_item),
        PublicAPIOperation("/api/v1/me/progress/{book_id}", ("DELETE",), "progress:write", "Delete reading progress for one book", "deleteMyProgress", _progress_item),
        PublicAPIOperation("/api/v1/me/annotations", ("GET",), "annotations:read", "List the token owner's annotations", "listMyAnnotations", _list_annotations),
        PublicAPIOperation("/api/v1/me/annotations", ("POST",), "annotations:write", "Create an annotation", "createMyAnnotation", _create_annotation),
        PublicAPIOperation("/api/v1/me/annotations/{annotation_id}", ("GET",), "annotations:read", "Get an annotation", "getMyAnnotation", _annotation_item),
        PublicAPIOperation("/api/v1/me/annotations/{annotation_id}", ("PUT",), "annotations:write", "Update an annotation", "putMyAnnotation", _annotation_item),
        PublicAPIOperation("/api/v1/me/annotations/{annotation_id}", ("DELETE",), "annotations:write", "Delete an annotation", "deleteMyAnnotation", _annotation_item),
        PublicAPIOperation("/api/v1/me/reviews", ("GET",), "reviews:read", "List the token owner's reviews", "listMyReviews", _list_reviews),
        PublicAPIOperation("/api/v1/me/reviews/{book_id}", ("GET",), "reviews:read", "Get a review", "getMyReview", _review_item),
        PublicAPIOperation("/api/v1/me/reviews/{book_id}", ("PUT",), "reviews:write", "Create or replace a review", "putMyReview", _review_item),
        PublicAPIOperation("/api/v1/me/reviews/{book_id}", ("DELETE",), "reviews:write", "Delete a review", "deleteMyReview", _review_item),
        PublicAPIOperation("/api/v1/me/vocabulary", ("GET",), "vocabulary:read", "List your vocabulary", "listMyVocabulary", _vocabulary),
        PublicAPIOperation("/api/v1/me/vocabulary", ("POST",), "vocabulary:write", "Record a vocabulary lookup", "recordMyVocabularyLookup", _vocabulary),
        PublicAPIOperation("/api/v1/me/vocabulary/{word_id}", ("PATCH",), "vocabulary:write", "Update a word's mastery", "patchMyVocabulary", _vocabulary),
        PublicAPIOperation("/api/v1/me/vocabulary/{word_id}", ("DELETE",), "vocabulary:write", "Delete a word or its lookups in one book", "deleteMyVocabulary", _vocabulary),
        PublicAPIOperation("/api/v1/me/kindle-memo", ("GET",), "kindle-memo:read", "Read the token owner's Kindle memo", "getMyKindleMemo", _kindle_memo),
        PublicAPIOperation("/api/v1/me/kindle-memo", ("PUT",), "kindle-memo:write", "Replace the token owner's Kindle memo", "putMyKindleMemo", _kindle_memo),
        PublicAPIOperation("/api/v1/admin/users", ("GET",), "admin:data:read", "List public account metadata", "listAdminUsers", _admin_users),
        PublicAPIOperation("/api/v1/admin/users/{user_id}/bookshelf", ("GET",), "admin:data:read", "Read a user's bookshelf", "getAdminUserBookshelf", _admin_bookshelf),
        PublicAPIOperation("/api/v1/admin/users/{user_id}/progress", ("GET",), "admin:data:read", "Read a user's progress", "listAdminUserProgress", _admin_user_list("list_reading_progress")),
        PublicAPIOperation("/api/v1/admin/users/{user_id}/annotations", ("GET",), "admin:data:read", "Read a user's annotations", "listAdminUserAnnotations", _admin_user_list("list_annotations")),
        PublicAPIOperation("/api/v1/admin/users/{user_id}/reviews", ("GET",), "admin:data:read", "Read a user's reviews", "listAdminUserReviews", _admin_user_list("list_book_reviews")),
        PublicAPIOperation("/api/v1/admin/users/{user_id}/reading-sessions", ("GET",), "admin:data:read", "Read a user's reading sessions", "listAdminUserReadingSessions", _admin_user_list("list_reading_sessions_for_user")),
        PublicAPIOperation("/api/v1/admin/users/{user_id}/reading-insights", ("GET",), "admin:data:read", "Read a user's reading insights", "getAdminUserReadingInsights", _admin_reading_insights),
        PublicAPIOperation("/api/v1/admin/users/{user_id}/ai-conversations", ("GET",), "admin:data:read", "Read a user's AI conversations", "listAdminUserAIConversations", _admin_user_list("list_ai_book_chat_turns_for_user")),
        PublicAPIOperation("/api/v1/admin/users/{user_id}/ai-results", ("GET",), "admin:data:read", "Read a user's AI results", "listAdminUserAIResults", _admin_user_list("list_ai_reading_results_for_user")),
    )


# List item schemas also define which fields callers can select.
_LISTS = {
    "listBooks": ("Book", ("format",), False),
    "listBookChapters": ("ChapterListItem", (), False),
    "listMyProgress": ("Progress", ("book_id",), False),
    "listMyAnnotations": ("Annotation", ("book_id", "chapter_index"), True),
    "listMyReviews": ("Review", ("book_id",), True),
    "listMyVocabulary": ("VocabularyWord", (), False),
    "listAdminUsers": ("User", (), False),
    "listAdminUserProgress": ("Progress", ("book_id",), False),
    "listAdminUserAnnotations": ("Annotation", ("book_id", "chapter_index"), True),
    "listAdminUserReviews": ("Review", ("book_id",), True),
    "listAdminUserReadingSessions": ("ReadingSession", ("book_id", "chapter_index"), False),
    "listAdminUserAIConversations": ("AIConversation", ("book_id", "chapter_index"), True),
    "listAdminUserAIResults": ("AIResult", ("book_id", "chapter_index"), True),
}


def _query_value(params, name):
    values = params.getlist(name)
    if len(values) > 1 or (values and not values[0].strip()):
        raise ValueError
    return values[0] if values else None


def _query_integer(value, minimum, maximum):
    if not re.fullmatch(r"[0-9]{1,19}", value):
        raise ValueError
    parsed = int(value)
    if not minimum <= parsed <= maximum:
        raise ValueError
    return parsed


@dataclass(frozen=True)
class _ListPage:
    limit: int
    offset: int
    filters: dict
    fields: tuple[str, ...]

    @classmethod
    def parse(cls, params, operation_id):
        item_schema, supported_filters, sparse = _LISTS[operation_id]
        limit = _query_integer(_query_value(params, "limit") or str(_LIST_LIMIT), 1, _MAX_LIST_LIMIT)
        offset = _query_integer(_query_value(params, "cursor") or "0", 0, _MAX_LIST_OFFSET)
        filters = {}
        for name in supported_filters:
            value = _query_value(params, name)
            if value is not None:
                if name == "chapter_index":
                    value = _query_integer(value, 0, _MAX_LIST_OFFSET)
                if name == "format" and value not in {"epub", "pdf"}:
                    raise ValueError
                filters[name] = value
        fields = _query_value(params, "fields")
        selected = tuple(fields.split(",")) if fields else ()
        if selected and (not sparse or not set(selected) <= _resource_properties()[item_schema].keys()):
            raise ValueError
        return cls(limit, offset, filters, selected)

    @property
    def window(self):
        return {"limit": self.limit + 1, "offset": self.offset}

    def response(self, items, *, has_more=None):
        if has_more is None:
            has_more = len(items) > self.limit
        items = items[:self.limit]
        if self.fields:
            items = [{name: item[name] for name in self.fields if name in item} for item in items]
        next_cursor = str(self.offset + self.limit) if has_more else None
        return JSONResponse({"items": items, "next_cursor": next_cursor}, headers=_PRIVATE_HEADERS)


def _endpoint(operation: PublicAPIOperation):
    async def endpoint(request):
        authenticated = await require_pat(request, operation.required_scope)
        if isinstance(authenticated, Response):
            return authenticated
        if operation.operation_id in _LISTS:
            try:
                request.state.public_list_page = _ListPage.parse(request.query_params, operation.operation_id)
            except ValueError:
                message = get_bundle(resolve_request_locale(request))["apiDocs.error.invalidListQuery"]
                return public_api_error("invalid_list_query", message, 400)
        return await operation.handler(request, authenticated)

    endpoint.__name__ = operation.operation_id
    return endpoint


def public_api_routes(context: Optional[PublicAPIContext] = None):
    del context  # Context is attached to app.state so handlers stay reusable.
    routes = [
        Route(operation.path, _endpoint(operation), methods=operation.methods)
        for operation in public_api_operations()
    ]
    routes.append(Route(
        "/api/v1/{path:path}",
        _public_api_fallback,
        methods=("GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"),
    ))
    return routes


async def _public_api_fallback(request):
    all_methods = ("GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS")
    for operation in public_api_operations():
        probe = Route(operation.path, _endpoint(operation), methods=all_methods)
        match, _scope = probe.matches(request.scope)
        if match is Match.FULL:
            return public_api_error(
                "method_not_allowed", "Method not allowed", 405,
                headers={"Allow": ", ".join(operation.methods)},
            )
    return public_api_error("not_found", "API resource not found", 404)


_STRING = {"type": "string"}
_INTEGER = {"type": "integer"}
_NONNEGATIVE = {"type": "integer", "minimum": 0}
_NULLABLE_STRING = {"type": ["string", "null"]}
_BOOK_FORMAT = {"enum": ["epub", "pdf"]}


def _object(properties, required=None):
    return {
        "type": "object",
        "required": list(properties) if required is None else required,
        "properties": properties,
    }


@cache
def _resource_properties():
    timestamped = {"created_at": _STRING, "updated_at": _STRING}
    chapter = {"book_id": _STRING, "chapter_index": _NONNEGATIVE}
    return {
        "Progress": {"user_id": _STRING, **chapter, "updated_at": _STRING},
        "Annotation": {
            "id": _STRING, "user_id": _STRING, "book_hash": _STRING,
            "chapter_index": _NONNEGATIVE, "text": _STRING, "note": _NULLABLE_STRING,
            "color": _NULLABLE_STRING, "start_meta": _NULLABLE_STRING, "end_meta": _NULLABLE_STRING,
            "startMeta": {}, "endMeta": {}, **timestamped,
        },
        "Review": {
            "user_id": _STRING, "book_id": _STRING,
            "rating": {"type": "integer", "minimum": 1, "maximum": 5},
            "review_text": _STRING, **timestamped,
        },
        "User": {
            "id": _STRING, "username": _STRING, "role": {"enum": ["admin", "member"]},
            "enabled": {"type": "boolean"}, **timestamped,
        },
        "ReadingSession": {
            "id": _STRING, "user_id": _STRING, **chapter,
            "book_title": _STRING, "chapter_label": _STRING, "started_at": _STRING,
            "ended_at": _STRING, "active_seconds": _NONNEGATIVE, "client_id": _STRING,
            "last_client_sequence": _NONNEGATIVE,
        },
        "AIConversation": {
            "id": _STRING, **chapter, "result_id": _NULLABLE_STRING,
            "context_mode": {"enum": ["shared_layer", "chapter_source"]},
            "book_context": {"enum": [0, 1]}, "owner_user_id": _STRING,
            "question": _STRING, "language": _STRING, "answer": _NULLABLE_STRING,
            "status": {"enum": ["queued", "running", "complete", "failed", "interrupted"]},
            "error_code": _NULLABLE_STRING, **timestamped,
        },
        "AIResult": {
            "id": _STRING, "cache_key": _STRING, "book_id": _STRING,
            "chapter_index": {"type": ["integer", "null"]}, "scope": {"enum": ["book", "chapter"]},
            "mode": _STRING, "profile": _STRING, "language": _STRING,
            "reading_boundary": {"type": ["integer", "null"]},
            "config_revision": _NONNEGATIVE, "template_id": _STRING,
            "template_version": _NONNEGATIVE, "content": {},
            "created_by_user_id": _STRING, "created_at": _STRING,
        },
    }


def _ref(name):
    return {"$ref": "#/components/schemas/" + name}


def _json_content(schema):
    return {"application/json": {"schema": schema}}


def _array(schema, maximum=None):
    result = {"type": "array", "items": schema}
    if maximum is not None:
        result["maxItems"] = maximum
    return result


def _query_parameter(name, schema, description):
    return {"name": name, "in": "query", "schema": schema, "description": description}


def _list_contract(operation_id):
    item_name, filters, sparse = _LISTS[operation_id]
    parameters = [
        _query_parameter("limit", {
            "type": "integer", "minimum": 1, "maximum": _MAX_LIST_LIMIT, "default": _LIST_LIMIT,
        }, "Maximum number of items to return."),
        _query_parameter("cursor", {
            "type": "string", "pattern": "^[0-9]{1,19}$",
        }, "Pass next_cursor from the previous page with the same filters. The cursor is an "
           "decimal offset from 0 to 9223372036854775807 in the current ordering. "
           "Concurrent edits can shift results."),
    ]
    filter_parameters = {
        "format": _query_parameter("format", _BOOK_FORMAT, "Filter by source format."),
        "book_id": _query_parameter("book_id", {"type": "string", "minLength": 1}, "Filter by book ID."),
        "chapter_index": _query_parameter(
            "chapter_index", {**_NONNEGATIVE, "maximum": _MAX_LIST_OFFSET},
            "Filter by zero-based chapter index or PDF page index.",
        ),
    }
    parameters.extend(filter_parameters[name] for name in filters)
    item = _ref(item_name)
    if sparse:
        properties = _resource_properties()[item_name]
        parameters.append({
            **_query_parameter(
                "fields", {"type": "string"},
                "Comma-separated item fields to return. Allowed: " + ", ".join(properties) + ".",
            ),
            "x-allowed-fields": list(properties),
        })
        item = _object(properties, required=[])
    schema = _object({
        "items": _array(item, _MAX_LIST_LIMIT),
        "next_cursor": {**_NULLABLE_STRING, "description": "Cursor for the next page, or null at the end."},
    })
    return parameters, schema


def openapi_document():
    schemas = {
        "Book": {
            "type": "object",
            "required": [
                "id", "title", "author", "authors", "language", "tags", "format",
                "visibility", "created_at", "updated_at",
            ],
            "properties": {
                "id": {"type": "string"},
                "title": {"type": "string"},
                "author": {
                    "type": "string",
                    "deprecated": True,
                    "description": "Compatibility string formed by joining authors with a comma.",
                },
                "authors": {"type": "array", "items": {"type": "string"}},
                "language": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}},
                "format": {"enum": ["epub", "pdf"]},
                "visibility": {"type": "string"},
                "created_at": {"type": "string"},
                "updated_at": {"type": "string"},
            },
        },
        "BookDetail": {
            "type": "object",
            "required": ["book"],
            "properties": {
                "book": {"$ref": "#/components/schemas/Book"},
            },
        },
        "ChapterListItem": {
            "type": "object",
            "required": ["index", "title"],
            "properties": {
                "index": {"type": "integer", "minimum": 0},
                "title": {"type": "string"},
                "format": {"enum": ["epub", "pdf"]},
                "page_number": {"type": "integer", "minimum": 1},
            },
            "allOf": [{
                "if": {"properties": {"format": {"const": "pdf"}}, "required": ["format"]},
                "then": {"required": ["page_number"]},
            }],
        },
        "Chapter": {
            "type": "object",
            "required": ["index", "title"],
            "properties": {
                "index": {"type": "integer", "minimum": 0},
                "title": {"type": "string"},
                "format": {"enum": ["epub", "pdf"]},
                "page_number": {"type": "integer", "minimum": 1},
                "content_type": {"type": "string"},
                "content_html": {"type": ["string", "null"]},
                "text": {"type": "string"},
            },
            "allOf": [{
                "if": {"properties": {"format": {"const": "pdf"}}, "required": ["format"]},
                "then": {
                    "required": [
                        "page_number", "content_type", "content_html", "text",
                    ],
                    "properties": {
                        "content_type": {"const": "application/pdf-page"},
                        "content_html": {"type": "null"},
                    },
                },
            }],
        },
    }
    schemas.update({name: _object(fields) for name, fields in _resource_properties().items()})
    schemas["Annotation"]["properties"] = {
        **schemas["Annotation"]["properties"],
        "username": {"type": "string", "deprecated": True},
    }
    schemas["VocabularyWord"] = _vocabulary_schema()
    schemas["Error"] = _object({"code": _STRING, "message": _STRING})
    schemas["Bookshelf"] = _object({"version": _NONNEGATIVE, "data": {"type": "object"}})
    schemas["BookshelfConflict"] = {
        "allOf": [_ref("Error"), _ref("Bookshelf")],
    }
    ranked_book = _object({"book_id": _STRING, "title": _STRING, "active_seconds": _NONNEGATIVE})
    day = {"date": {"type": "string", "format": "date"}, "active_seconds": _NONNEGATIVE}
    insight_fields = {
        "period": {"enum": ["overview", "day", "week", "month"]},
        "timezone": _STRING,
        "total_active_seconds": _NONNEGATIVE,
        "top_book": {"anyOf": [ranked_book, {"type": "null"}]},
        "books": _array(ranked_book, _MAX_LIST_LIMIT),
        "books_read_count": _NONNEGATIVE,
        "trend": _object({
            "granularity": {"enum": ["hour", "day", "month"]},
            "start_date": day["date"], "end_date": day["date"],
            "points": _array(_object({
                "bucket": _STRING, "active_seconds": _NONNEGATIVE, "book_count": _NONNEGATIVE,
            }), 31),
        }),
    }
    schemas["ReadingInsights"] = _object({
        **insight_fields,
        "activity": _object({"days": _array(_object({**day, "book_count": _NONNEGATIVE}), 366)}),
        "days": _array(_object(day), 31),
    }, required=list(insight_fields))
    paths = {}
    for operation in public_api_operations():
        path_item = paths.setdefault(operation.path, {})
        operation_id = operation.operation_id
        parameters = [
            {"name": name, "in": "path", "required": True,
             "schema": _NONNEGATIVE if name == "chapter_index" else _STRING}
            for name in re.findall(r"{(\w+)}", operation.path)
        ]
        responses = {
            "200": {"description": "Successful response"},
            "401": {"description": "Missing or invalid token"},
            "403": {"description": "Insufficient scope"},
            "503": {"description": "Administrator setup required"},
        }
        if operation_id in _LISTS:
            query, schema = _list_contract(operation_id)
            parameters.extend(query)
            if operation_id == "listBooks":
                schemas["BookList"] = schema
                schema = _ref("BookList")
            responses["200"]["content"] = _json_content(schema)
            responses["400"] = {"description": "Invalid list query"}
        if "{" in operation.path:
            responses["404"] = {"description": "Resource unavailable"}
        path_item[operation.methods[0].lower()] = {
            "operationId": operation_id,
            "summary": operation.summary,
            "security": [{"PATBearer": [operation.required_scope]}],
            "responses": responses,
            **({"parameters": parameters} if parameters else {}),
        }

    _describe_resource_operations(paths)
    for path in paths.values():
        for operation in path.values():
            for status, response in operation["responses"].items():
                if int(status) >= 400:
                    response.setdefault("content", _json_content(_ref("Error")))
                if status in {"401", "403"}:
                    response["headers"] = {"WWW-Authenticate": {"schema": _STRING}}

    return {
        "openapi": "3.1.0",
        "info": {"title": "EPUB Browser API", "version": "1.2.0"},
        "paths": paths,
        "components": {
            "securitySchemes": {
                "PATBearer": {
                    "type": "http", "scheme": "bearer", "bearerFormat": "EPUB Browser PAT",
                    "x-scopes": sorted(PAT_SCOPES),
                }
            },
            "schemas": schemas,
        },
    }


def _describe_resource_operations(paths):
    operations = {
        op["operationId"]: op for path in paths.values() for op in path.values()
    }

    def describe(name, schema=None, *, body=None, status="200", errors=(), query=()):
        op = operations[name]
        responses = op["responses"]
        success = responses.pop("200")
        responses[status] = success
        if schema is not None:
            success["content"] = _json_content(schema)
        if body is not None:
            op["requestBody"] = {"required": True, "content": _json_content(body)}
        responses.update({code: {"description": description} for code, description in errors})
        if query:
            op.setdefault("parameters", []).extend(query)

    unavailable = ("503", "Administrator setup is required or book content is unavailable")
    missing_book = ("404", "Book is unavailable")
    invalid = ("400", "Invalid request")
    describe("getBook", _ref("BookDetail"))
    operations["listBookChapters"]["responses"]["503"] = {"description": unavailable[1]}
    describe("getBookChapter", {"oneOf": [
        {"allOf": [_ref("Chapter"), {"required": ["content_html"], "properties": {"content_html": _STRING}}]},
        _object({"chapter": {"allOf": [
            _ref("Chapter"), {"required": ["format"], "properties": {"format": {"const": "pdf"}}},
        ]}}),
    ]}, errors=(invalid, unavailable), query=(
        _query_parameter("format", {"enum": ["html", "text"], "default": "html"},
                         "Return JSON with sanitized chapter HTML or a plain text response. PDF text is empty."),
    ))
    operations["getBookChapter"]["responses"]["200"]["content"]["text/plain"] = {"schema": _STRING}

    for name in ("getMyBookshelf", "getAdminUserBookshelf"):
        describe(name, _ref("Bookshelf"))
    describe("putMyBookshelf", _ref("Bookshelf"), body=_ref("Bookshelf"),
             errors=(invalid, ("409", "Bookshelf changed on the server")))
    operations["putMyBookshelf"]["responses"]["409"]["content"] = _json_content(_ref("BookshelfConflict"))
    progress = _object({"book_id": _STRING, "chapter_index": _NONNEGATIVE})
    describe("getMyProgress", progress)
    describe("putMyProgress", progress, body=_object({"chapter_index": _NONNEGATIVE}),
             errors=(invalid, unavailable))
    describe("deleteMyProgress", status="204")

    annotation = _object({"annotation": _ref("Annotation")})
    annotation_update = {
        "note": _NULLABLE_STRING,
        "color": _NULLABLE_STRING,
        "chapter_index": _NONNEGATIVE, "startMeta": {}, "endMeta": {},
    }
    annotation_create = _object({
        **annotation_update,
        "note": {"type": "string", "maxLength": 100000},
        "color": {"type": "string", "minLength": 1, "maxLength": 64},
        "id": {"type": "string", "description": "Omit to generate an ID. Accepted length is 1–128."},
        "book_hash": {"type": "string", "minLength": 1},
        "text": {"type": "string", "minLength": 1, "maxLength": 100000},
        "created_at": _STRING, "updated_at": _STRING,
    }, required=["book_hash", "chapter_index", "text", "color"])
    describe("createMyAnnotation", annotation, body=annotation_create, status="201",
             errors=(invalid, missing_book, ("409", "Annotation conflict")))
    describe("getMyAnnotation", annotation)
    describe("putMyAnnotation", annotation, body={
        **_object(annotation_update, required=[]),
        "anyOf": [{"required": [field]} for field in annotation_update],
    }, errors=(invalid,))
    describe("deleteMyAnnotation", status="204")
    review = _object({"review": _ref("Review")})
    describe("getMyReview", review)
    describe("putMyReview", review, body=_object({
        "rating": {"type": "integer", "minimum": 1, "maximum": 5},
        "review_text": {"type": "string", "description": "Up to 10,000 characters after trimming."},
    }), errors=(invalid,))
    describe("deleteMyReview", status="204")

    describe("getAdminUserReadingInsights", _object({"insights": _ref("ReadingInsights")}),
             errors=(invalid,), query=(
        _query_parameter("period", {"enum": ["overview", "day", "week", "month"], "default": "overview"},
                         "Report period containing the anchor date."),
        _query_parameter("anchor", {"type": "string", "format": "date"}, "Defaults to the server's current date."),
        _query_parameter("timezone", {"type": "string", "default": "UTC"}, "IANA time zone for the report."),
    ))
    memo = _object({"memo": {"type": "string", "maxLength": KINDLE_MEMO_MAX_LENGTH}})
    describe("getMyKindleMemo", memo)
    describe("putMyKindleMemo", memo, body=memo, errors=(invalid,))
    _describe_vocabulary(operations, describe, invalid, missing_book, unavailable)


def _vocabulary_schema():
    source = _object({
        "book_id": _STRING, "title": _STRING, "source_format": _BOOK_FORMAT,
        "chapter_index": _NONNEGATIVE,
    })
    return _object({
        "id": _STRING, "word": _STRING,
        "mastery": {"enum": list(MASTERY_STATES)},
        "lookup_count": {"type": "integer", "minimum": 1},
        "first_seen": {"type": "string", "format": "date-time"},
        "last_seen": {"type": "string", "format": "date-time"},
        "sources": _array(source),
    })


def _describe_vocabulary(operations, describe, invalid, missing_book, unavailable):
    book = _query_parameter("book_id", _STRING, "Limit the operation to this visible book.")
    mastery = {"enum": list(MASTERY_STATES)}
    legacy_page = {"type": "integer", "minimum": 1, "maximum": 2**31 - 1, "default": 1}
    legacy_size = {"type": "integer", "minimum": 1, "maximum": MAX_PAGE_SIZE, "default": PAGE_SIZE}
    describe("listMyVocabulary", errors=(invalid, missing_book), query=(
        book,
        _query_parameter("q", {"type": "string", "maxLength": MAX_QUERY_LENGTH}, "Filter by word."),
        _query_parameter("mastery", mastery, "Filter by mastery state."),
        {**_query_parameter("page", legacy_page, "Legacy page number. Use without cursor or limit."), "deprecated": True},
        {**_query_parameter("page_size", legacy_size, "Legacy page size. Use without cursor or limit."), "deprecated": True},
    ))
    response = operations["listMyVocabulary"]["responses"]["200"]["content"]["application/json"]
    response["schema"] = {"oneOf": [
        response["schema"],
        _object({
            "words": _array(_ref("VocabularyWord"), MAX_PAGE_SIZE),
            "page": {"type": "integer", "minimum": 1, "description": "Clamped to the last page."},
            "page_size": legacy_size, "total": _NONNEGATIVE, "total_pages": _NONNEGATIVE,
        }),
    ]}
    describe("recordMyVocabularyLookup", body=_object({
        "book_id": _STRING, "chapter_index": _NONNEGATIVE,
        "word": {"type": "string", "minLength": 1, "maxLength": MAX_QUERY_LENGTH},
        "lookup_id": {"type": "string", "pattern": "^[a-zA-Z0-9_-]{1,64}$",
                      "description": "Reuse for retries of the same lookup."},
    }), status="204", errors=(invalid, missing_book, unavailable), query=(book,))
    missing_word = ("404", "Book or word is unavailable to the token owner")
    mastery_object = _object({"mastery": mastery})
    describe("patchMyVocabulary", mastery_object, body=mastery_object,
             errors=(invalid, missing_word), query=(book,))
    describe("deleteMyVocabulary", status="204", errors=(missing_word,), query=(book,))
