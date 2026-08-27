"""Versioned, Bearer-only API surface for Server deployments."""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Callable, Optional, Tuple

from starlette.responses import JSONResponse, PlainTextResponse, Response
from starlette.routing import Route

from .pat import AuthenticatedPAT, PAT_SCOPES
from .server_pages import ServerPageError, ServerPageRenderer


PUBLIC_API_CONTEXT_KEY = "epub_browser.public_api_context"
_BEARER_PATTERN = re.compile(r"^Bearer ([^\s,]+)$")


@dataclass(frozen=True)
class PublicAPIContext:
    store: object
    public_dir: Path


@dataclass(frozen=True)
class PublicAPIOperation:
    path: str
    methods: Tuple[str, ...]
    required_scope: str
    summary: str
    operation_id: str
    handler: Callable


def public_api_error(code: str, message: str, status: int, *, headers=None):
    response_headers = {"Cache-Control": "private, no-store"}
    response_headers.update(headers or {})
    return JSONResponse(
        {"code": code, "message": message},
        status_code=status,
        headers=response_headers,
    )


def _context(request) -> PublicAPIContext:
    return getattr(request.app.state, PUBLIC_API_CONTEXT_KEY)


def require_pat(request, scope: str):
    """Authenticate one exact Bearer credential and enforce one operation scope."""
    values = request.headers.getlist("authorization")
    match = _BEARER_PATTERN.fullmatch(values[0]) if len(values) == 1 else None
    authenticated = (
        _context(request).store.authenticate_personal_access_token(match.group(1))
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


def _book_payload(book):
    try:
        metadata = json.loads(book.metadata_json)
    except (TypeError, json.JSONDecodeError):
        metadata = {}
    return {
        "id": book.book_id,
        "title": metadata.get("title") or "EPUB Book",
        "author": metadata.get("author") or metadata.get("creator") or "",
        "language": metadata.get("language") or "",
        "tags": list(metadata.get("tags") or ()),
        "visibility": book.visibility,
        "created_at": book.created_at,
        "updated_at": book.updated_at,
    }


async def _list_books(request, authenticated: AuthenticatedPAT):
    books = _context(request).store.visible_books(authenticated.principal)
    return JSONResponse(
        {"items": [_book_payload(book) for book in books], "next_cursor": None},
        headers={"Cache-Control": "private, no-store"},
    )


def _authorized_book(request, authenticated, book_id):
    context = _context(request)
    if not context.store.can_read_book(
        authenticated.principal.user_id,
        authenticated.principal.role,
        book_id,
    ):
        return None
    return context.store.book_by_id(book_id)


async def _book_detail(request, authenticated: AuthenticatedPAT):
    book = _authorized_book(
        request, authenticated, request.path_params["book_id"]
    )
    if book is None:
        return public_api_error("book_not_found", "Book not found", 404)
    return JSONResponse(
        {"book": _book_payload(book)},
        headers={"Cache-Control": "private, no-store"},
    )


def _chapter_list(renderer):
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
    if _authorized_book(request, authenticated, book_id) is None:
        return public_api_error("book_not_found", "Book not found", 404)
    try:
        items = _chapter_list(ServerPageRenderer(_context(request).public_dir, book_id))
    except ServerPageError:
        return public_api_error(
            "book_content_unavailable", "Book content is unavailable", 503
        )
    return JSONResponse(
        {"items": items, "next_cursor": None},
        headers={"Cache-Control": "private, no-store"},
    )


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
    if _authorized_book(request, authenticated, book_id) is None:
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
    try:
        renderer = ServerPageRenderer(_context(request).public_dir, book_id)
        if chapter_index >= len(_chapter_list(renderer)):
            return public_api_error("chapter_not_found", "Chapter not found", 404)
        chapter = renderer.chapter_content(chapter_index)
    except ServerPageError:
        return public_api_error(
            "book_content_unavailable", "Book content is unavailable", 503
        )
    if output_format == "text":
        extractor = _PlainTextExtractor()
        extractor.feed(chapter["content"])
        extractor.close()
        return PlainTextResponse(
            extractor.text(), headers={"Cache-Control": "private, no-store"}
        )
    return JSONResponse(
        {
            "index": chapter["index"],
            "title": chapter["title"],
            "content_html": chapter["content"],
        },
        headers={"Cache-Control": "private, no-store"},
    )


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
    version, data = _bookshelf_document(
        _context(request).store, authenticated.principal.user_id
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
    current_version, current_data = _bookshelf_document(
        store, authenticated.principal.user_id
    )
    if version != current_version:
        response = public_api_error(
            "bookshelf_conflict", "Bookshelf changed on the server", 409
        )
        response.body = json.dumps({
            "code": "bookshelf_conflict",
            "message": "Bookshelf changed on the server",
            "version": current_version,
            "data": current_data,
        }, separators=(",", ":")).encode("utf-8")
        response.headers["content-length"] = str(len(response.body))
        return response
    next_version = version + 1
    if version == 0:
        store.create_bookshelf(authenticated.principal.user_id, next_version, document)
    else:
        store.update_bookshelf(authenticated.principal.user_id, next_version, document)
    return JSONResponse(
        {"version": next_version, "data": document},
        headers={"Cache-Control": "private, no-store"},
    )


def _visible_items(store, authenticated, items, book_key="book_id"):
    return [
        item for item in items
        if store.can_read_book(
            authenticated.principal.user_id,
            authenticated.principal.role,
            item.get(book_key),
        )
    ]


async def _list_progress(request, authenticated):
    store = _context(request).store
    items = _visible_items(
        store,
        authenticated,
        store.list_reading_progress(authenticated.principal.user_id),
    )
    return JSONResponse(
        {"items": items, "next_cursor": None},
        headers={"Cache-Control": "private, no-store"},
    )


async def _progress_item(request, authenticated):
    store = _context(request).store
    book_id = request.path_params["book_id"]
    if _authorized_book(request, authenticated, book_id) is None:
        return public_api_error("book_not_found", "Book not found", 404)
    user_id = authenticated.principal.user_id
    if request.method == "GET":
        chapter_index = store.get_reading_progress(user_id, book_id)
        if chapter_index is None:
            return public_api_error("progress_not_found", "Reading progress not found", 404)
        return JSONResponse(
            {"book_id": book_id, "chapter_index": chapter_index},
            headers={"Cache-Control": "private, no-store"},
        )
    if request.method == "DELETE":
        store.delete_reading_progress(user_id, book_id)
        return Response(status_code=204, headers={"Cache-Control": "private, no-store"})
    data = await _json_object(request)
    chapter_index = data.get("chapter_index") if data else None
    if isinstance(chapter_index, bool) or not isinstance(chapter_index, int) or chapter_index < 0:
        return public_api_error("invalid_chapter_index", "Invalid chapter index", 400)
    try:
        chapters = _chapter_list(ServerPageRenderer(_context(request).public_dir, book_id))
    except ServerPageError:
        return public_api_error("book_content_unavailable", "Book content is unavailable", 503)
    if chapter_index >= len(chapters):
        return public_api_error("invalid_chapter_index", "Invalid chapter index", 400)
    store.set_reading_progress(user_id, book_id, chapter_index)
    return JSONResponse(
        {"book_id": book_id, "chapter_index": chapter_index},
        headers={"Cache-Control": "private, no-store"},
    )


async def _list_annotations(request, authenticated):
    store = _context(request).store
    items = _visible_items(
        store,
        authenticated,
        store.list_annotations(user_id=authenticated.principal.user_id),
        book_key="book_hash",
    )
    return JSONResponse(
        {"items": items, "next_cursor": None},
        headers={"Cache-Control": "private, no-store"},
    )


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
    if _authorized_book(request, authenticated, book_id) is None:
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
        store.upsert_annotation(annotation, authenticated.principal.user_id)
    except Exception:
        return public_api_error("annotation_conflict", "Annotation already exists", 409)
    stored = store.get_annotation(annotation["id"], authenticated.principal.user_id)
    return JSONResponse(
        {"annotation": stored},
        status_code=201,
        headers={"Cache-Control": "private, no-store"},
    )


async def _annotation_item(request, authenticated):
    store = _context(request).store
    user_id = authenticated.principal.user_id
    annotation_id = request.path_params["annotation_id"]
    stored = store.get_annotation(annotation_id, user_id)
    if stored is None or _authorized_book(request, authenticated, stored["book_hash"]) is None:
        return public_api_error("annotation_not_found", "Annotation not found", 404)
    if request.method == "GET":
        return JSONResponse({"annotation": stored}, headers={"Cache-Control": "private, no-store"})
    if request.method == "DELETE":
        store.delete_annotation(annotation_id, user_id)
        return Response(status_code=204, headers={"Cache-Control": "private, no-store"})
    data = await _json_object(request)
    allowed = {key: data[key] for key in ("note", "color", "chapter_index", "startMeta", "endMeta") if data and key in data}
    if not allowed or ("chapter_index" in allowed and (isinstance(allowed["chapter_index"], bool) or not isinstance(allowed["chapter_index"], int) or allowed["chapter_index"] < 0)):
        return public_api_error("invalid_annotation", "Invalid annotation", 400)
    updated = store.update_annotation(annotation_id, allowed, user_id)
    return JSONResponse({"annotation": updated}, headers={"Cache-Control": "private, no-store"})


async def _list_reviews(request, authenticated):
    store = _context(request).store
    items = _visible_items(
        store,
        authenticated,
        store.list_book_reviews(authenticated.principal.user_id),
    )
    return JSONResponse({"items": items, "next_cursor": None}, headers={"Cache-Control": "private, no-store"})


async def _review_item(request, authenticated):
    store = _context(request).store
    book_id = request.path_params["book_id"]
    if _authorized_book(request, authenticated, book_id) is None:
        return public_api_error("book_not_found", "Book not found", 404)
    user_id = authenticated.principal.user_id
    if request.method == "GET":
        review = store.get_book_review(book_id, user_id)
        if review is None:
            return public_api_error("review_not_found", "Review not found", 404)
        return JSONResponse({"review": review}, headers={"Cache-Control": "private, no-store"})
    if request.method == "DELETE":
        store.delete_book_review(book_id, user_id)
        return Response(status_code=204, headers={"Cache-Control": "private, no-store"})
    data = await _json_object(request)
    rating = data.get("rating") if data else None
    review_text = data.get("review_text") if data else None
    if isinstance(rating, bool) or not isinstance(rating, int) or not 1 <= rating <= 5 or not isinstance(review_text, str) or len(review_text.strip()) > 10_000:
        return public_api_error("invalid_review", "Invalid review", 400)
    review = store.upsert_book_review(book_id, user_id, rating, review_text)
    return JSONResponse({"review": review}, headers={"Cache-Control": "private, no-store"})


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
    )


def _endpoint(operation: PublicAPIOperation):
    async def endpoint(request):
        authenticated = require_pat(request, operation.required_scope)
        if isinstance(authenticated, Response):
            return authenticated
        return await operation.handler(request, authenticated)

    endpoint.__name__ = operation.operation_id
    return endpoint


def public_api_routes(context: Optional[PublicAPIContext] = None):
    del context  # Context is attached to app.state so handlers stay reusable.
    return [
        Route(operation.path, _endpoint(operation), methods=operation.methods)
        for operation in public_api_operations()
    ]


def openapi_document():
    paths = {}
    for operation in public_api_operations():
        path_item = paths.setdefault(operation.path, {})
        for method in operation.methods:
            path_item[method.lower()] = {
                "operationId": operation.operation_id,
                "summary": operation.summary,
                "security": [{"PATBearer": [operation.required_scope]}],
                "responses": {
                    "200": {"description": "Successful response"},
                    "401": {"description": "Missing or invalid token"},
                    "403": {"description": "Insufficient scope"},
                },
            }
    return {
        "openapi": "3.1.0",
        "info": {"title": "EPUB Browser API", "version": "1.0.0"},
        "paths": paths,
        "components": {
            "securitySchemes": {
                "PATBearer": {
                    "type": "http",
                    "scheme": "bearer",
                    "bearerFormat": "EPUB Browser PAT",
                    "x-scopes": sorted(PAT_SCOPES),
                }
            }
        },
    }
