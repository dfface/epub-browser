"""Versioned, Bearer-only API surface for Server deployments."""

from __future__ import annotations

import json
import re
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
