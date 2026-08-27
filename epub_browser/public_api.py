"""Versioned, Bearer-only API surface for Server deployments."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Tuple

from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .pat import AuthenticatedPAT, PAT_SCOPES


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
