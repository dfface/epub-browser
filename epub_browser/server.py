import asyncio
import base64
import hashlib
import html
import json
import os
import posixpath
import re
import secrets
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qs, quote, unquote, urlsplit

from starlette.applications import Starlette
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
    Response,
    StreamingResponse,
)
from starlette.routing import Route
from starlette.staticfiles import StaticFiles

from .auth import (
    AuthService,
    Principal,
    SESSION_COOKIE,
    hash_password,
    session_cookie_options,
)
from .ai_client import validate_provider_base_url
from .ai_reading import AIReadingError, AIReadingService, ReadingRequest
from .state import SetupAlreadyCompleteError, StateStore
from .library_progress import LibraryProgressBroker
from .processor import (
    SERVER_OUTPUT_REVISION,
    SERVER_OUTPUT_REVISION_FILE,
    server_book_public_path_allowed,
)
from .server_library import library_metadata
from .version import render_footer

DATABASE_FILENAME = 'epub-browser.db'
LEGACY_DATABASE_FILENAME = 'annotations.db'
PRINCIPAL_SCOPE_KEY = 'epub_browser.principal'
PENDING_IDENTITY_SCOPE_KEY = 'epub_browser.pending_identity'
SESSION_TOKEN_SCOPE_KEY = 'epub_browser.session_token'
SETUP_NONCE_COOKIE = 'epub_browser_setup_nonce'
AUTH_NONCE_COOKIE = 'epub_browser_auth_nonce'
AUTH_NONCE_HEADER = 'X-EPUB-Browser-Auth-Nonce'
SAFE_METHODS = frozenset({'GET', 'HEAD', 'OPTIONS', 'TRACE'})
PUBLIC_AUTH_ENDPOINTS = frozenset({
    '/setup',
    '/login',
    '/logout',
    '/api/identity/link',
    '/sw.js',
})
PUBLIC_LOGIN_ASSETS = frozenset({
    '/assets/account.css',
    '/assets/auth.js',
    '/assets/i18n.js',
    '/assets/theme-bootstrap.js',
    '/assets/theme.css',
    '/assets/version-check.js',
})
SETUP_COPY = {
    'en': {
        'page_title': 'Set up · EPUB Browser',
        'title': 'Create a superuser account',
        'description': (
            'When you first access the web interface, you will be prompted '
            'to create a superuser account.'
        ),
        'username': 'Username',
        'password': 'Password',
        'password_confirmation': 'Confirm password',
        'submit': 'Create superuser',
        'language': 'Language',
        'invalid': 'Enter a username and password.',
        'password_mismatch': 'Password and confirmation do not match.',
        'username_unavailable': 'Username is unavailable.',
    },
    'zh-CN': {
        'page_title': '设置 · EPUB Browser',
        'title': '创建超级用户账户',
        'description': '首次访问 Web 界面时，系统会提示你创建一个超级用户账户。',
        'username': '用户名',
        'password': '密码',
        'password_confirmation': '确认密码',
        'submit': '创建超级用户',
        'language': '语言',
        'invalid': '请输入用户名和密码。',
        'password_mismatch': '密码与确认密码不一致。',
        'username_unavailable': '用户名不可用。',
    },
}
LOGIN_COPY = {
    'en': {
        'page_title': 'Sign in · EPUB Browser',
        'sign_in': 'Sign in',
        'description': 'Sign in to continue to your personal library.',
        'username': 'Username',
        'password': 'Password',
        'invalid_credentials': 'Invalid username or password.',
        'language': 'Language',
    },
    'zh-CN': {
        'page_title': '登录 · EPUB Browser',
        'sign_in': '登录',
        'description': '登录后继续进入你的个人书库。',
        'username': '用户名',
        'password': '密码',
        'invalid_credentials': '用户名或密码不正确。',
        'language': '语言',
    },
}

SERVICE_WORKER_TOMBSTONE = r"""'use strict';
self.addEventListener('install', function(event) {
    event.waitUntil(self.skipWaiting());
});
self.addEventListener('activate', function(event) {
    event.waitUntil((async function() {
        const names = await caches.keys();
        await Promise.all(names.filter(function(name) {
            return name.indexOf('epub-browser-') === 0;
        }).map(function(name) {
            return caches.delete(name);
        }));
        await self.clients.claim();
        await self.registration.unregister();
        const windows = await self.clients.matchAll({
            type: 'window',
            includeUncontrolled: true
        });
        await Promise.all(windows.map(function(client) {
            return client.navigate(client.url);
        }));
    }()));
});
"""
_INLINE_SCRIPT = re.compile(
    r'<script\b(?![^>]*\bsrc\s*=)[^>]*>(.*?)</script\s*>',
    re.IGNORECASE | re.DOTALL,
)


def reader_content_security_policy(markup):
    if isinstance(markup, bytes):
        markup = markup.decode('utf-8', errors='replace')
    hashes = []
    for script in _INLINE_SCRIPT.findall(str(markup or '')):
        digest = base64.b64encode(
            hashlib.sha256(script.encode('utf-8')).digest()
        ).decode('ascii')
        hashes.append("'sha256-{}'".format(digest))
    script_sources = " ".join(["'self'"] + sorted(set(hashes)))
    return (
        "default-src 'self'; "
        "script-src {}; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: blob:; "
        "font-src 'self' data:; "
        "media-src 'self' data: blob:; "
        "connect-src 'self'; "
        "object-src 'none'; frame-src 'none'; frame-ancestors 'none'; "
        "base-uri 'none'; form-action 'self'"
    ).format(script_sources)


def error_payload(code, message):
    return {'code': code, 'message': message}


def route_is_public_auth_endpoint(path):
    return path in PUBLIC_AUTH_ENDPOINTS or path in PUBLIC_LOGIN_ASSETS


def normalize_login_locale(value, accept_language=''):
    candidate = str(value or '').replace('_', '-').lower()
    if not candidate:
        candidate = str(accept_language or '').split(',', 1)[0].split(';', 1)[0].strip().lower()
    if candidate == 'zh' or candidate.startswith(('zh-cn', 'zh-sg')):
        return 'zh-CN'
    return 'en'


def require_principal(request) -> Principal:
    principal = request.scope.get(PRINCIPAL_SCOPE_KEY)
    if principal is None:
        raise StarletteHTTPException(
            status_code=401,
            detail='Authentication required',
        )
    return principal


def require_admin(request) -> Principal:
    principal = require_principal(request)
    if principal.role != 'admin':
        raise StarletteHTTPException(status_code=403, detail='Forbidden')
    return principal


def _safe_relative_path(value, default='/'):
    if not isinstance(value, str) or not value.startswith('/'):
        return default
    candidate = value
    for _ in range(3):
        if candidate.startswith('//') or '\\' in candidate or any(
            character in candidate for character in ('\r', '\n', '\x00')
        ):
            return default
        decoded = unquote(candidate)
        if decoded == candidate:
            break
        candidate = decoded
    parsed = urlsplit(value)
    if parsed.scheme or parsed.netloc or parsed.fragment:
        return default
    return value


def _request_relative_path(request):
    target = request.url.path
    query = request.scope.get('query_string', b'').decode('utf-8', errors='replace')
    if query:
        target += '?' + query
    return _safe_relative_path(target)


def _request_expects_html(request):
    if request.method not in {'GET', 'HEAD'}:
        return False
    path = request.url.path
    return (
        path in {'/', '/index.html'}
        or path.endswith('.html')
        or 'text/html' in request.headers.get('accept', '').lower()
    )


def unauthenticated_response(request):
    path = request.url.path
    if path == '/book' or path.startswith('/book/'):
        return JSONResponse(
            error_payload('forbidden', 'Forbidden'),
            status_code=403,
            headers={'Cache-Control': 'no-store'},
        )
    if path == '/sync' or path.startswith('/api/'):
        return JSONResponse(
            error_payload('authentication_required', 'Authentication required'),
            status_code=401,
            headers={'Cache-Control': 'no-store'},
        )
    if _request_expects_html(request):
        target = quote(_request_relative_path(request), safe='')
        return RedirectResponse(
            '/login?next=' + target,
            status_code=303,
            headers={'Cache-Control': 'no-store'},
        )
    return JSONResponse(
        error_payload('forbidden', 'Forbidden'),
        status_code=403,
        headers={'Cache-Control': 'no-store'},
    )


def setup_required_response(request):
    path = request.url.path
    if path in {'/api/health', '/api/ready'}:
        return JSONResponse(
            {'status': 'setup_required'},
            status_code=503,
            headers={'Cache-Control': 'no-store'},
        )
    content_path = (
        path == '/book'
        or path.startswith('/book/')
        or path.startswith('/assets/')
        or path == '/book-metadata.json'
        or path == '/sync'
        or path.startswith('/api/')
    )
    if not content_path and (path == '/login' or _request_expects_html(request)):
        return RedirectResponse(
            '/setup',
            status_code=303,
            headers={'Cache-Control': 'no-store'},
        )
    return JSONResponse(
        error_payload('setup_required', 'Administrator setup required'),
        status_code=503,
        headers={'Cache-Control': 'no-store'},
    )


def database_path(base_directory):
    return os.path.join(base_directory, DATABASE_FILENAME)


def migrate_legacy_database(base_directory):
    """Atomically rename the former annotation-only database when needed."""
    target = database_path(base_directory)
    legacy = os.path.join(base_directory, LEGACY_DATABASE_FILENAME)
    if not os.path.exists(target) and os.path.isfile(legacy):
        try:
            os.replace(legacy, target)
        except OSError:
            pass
    return target


def cache_control_for_path(path):
    """Cache immutable app assets and stable EPUB resources without caching pages."""
    normalized = os.path.normpath(path).replace(os.sep, '/')
    if '/assets/immutable/' in normalized:
        return 'public, max-age=31536000, immutable'
    if '/book/' in normalized and '/resources/' in normalized:
        return 'public, max-age=2592000'
    return 'no-cache'


def normalize_public_path(path):
    """Return one traversal-safe POSIX path for authorization and file lookup."""
    if not isinstance(path, str):
        raise ValueError('Invalid public path')
    candidate = path.lstrip('/')
    for _ in range(3):
        decoded = unquote(candidate)
        if decoded == candidate:
            break
        candidate = decoded
    if '\\' in candidate or '\x00' in candidate:
        raise ValueError('Invalid public path')
    parts = candidate.split('/')
    if any(part in {'.', '..'} for part in parts):
        raise ValueError('Invalid public path')
    normalized = posixpath.normpath(candidate)
    if normalized == '.':
        return ''
    if normalized == '..' or normalized.startswith('../'):
        raise ValueError('Invalid public path')
    return normalized


def extract_book_id_from_public_path(path):
    parts = path.split('/')
    if len(parts) >= 2 and parts[0] == 'book' and parts[1]:
        return parts[1]
    return None


def server_book_output_is_current(base_directory, book_id):
    marker = os.path.join(
        base_directory,
        'book',
        book_id,
        SERVER_OUTPUT_REVISION_FILE,
    )
    try:
        with open(marker, encoding='utf-8') as revision_file:
            revision = revision_file.read().strip()
    except OSError:
        return False
    return revision == SERVER_OUTPUT_REVISION


def sync_bookshelf(
    database_path,
    user_id,
    client_version,
    client_data,
    store=None,
):
    """Synchronize one bookshelf document and return its response payload and status."""
    active_store = store or StateStore(database_path)
    if store is None:
        active_store.initialize()
    row = active_store.get_bookshelf(user_id)

    if row is not None:
        stored_version, stored_data = row
        if stored_version == client_version:
            return {}, 304
        if stored_version > client_version:
            return {
                'message': 'Server has newer or same version',
                'version': stored_version,
                'data': json.loads(stored_data),
            }, 200

    if client_data is None:
        return {'message': 'No data provided for update'}, 400

    new_version = max(client_version, 1)
    if row is None:
        active_store.create_bookshelf(user_id, new_version, client_data)
        return {'message': 'New user created', 'version': new_version}, 404

    active_store.update_bookshelf(user_id, new_version, client_data)
    return {'message': 'Data updated', 'version': new_version}, 201


class CachedStaticFiles(StaticFiles):
    """Static file adapter with one cache policy for browser assets and books."""

    def file_response(self, full_path, stat_result, scope, status_code=200):
        response = super().file_response(full_path, stat_result, scope, status_code)
        response.headers['Cache-Control'] = cache_control_for_path(full_path)
        return response


class _CompatibilityRuntimeStatus:
    def is_ready(self):
        return True

    def snapshot(self):
        return {
            'state': 'ready',
            'failed_books': 0,
            'queued_tasks': 0,
        }


def create_app(
    public_dir,
    state_store=None,
    status=None,
    sync_dir=None,
    progress_broker: Optional[LibraryProgressBroker] = None,
    library_event_heartbeat_seconds: float = 15.0,
    auth_service: Optional[AuthService] = None,
):
    """Create the ASGI module used by Uvicorn to serve an EPUB library."""
    base_directory = os.path.abspath(public_dir)
    if state_store is None or auth_service is None:
        raise RuntimeError('An initialized StateStore and AuthService are required')
    store = state_store
    runtime_status = status or _CompatibilityRuntimeStatus()
    public_files = CachedStaticFiles(directory=base_directory, html=False)
    ai_reading = AIReadingService(store, base_directory)
    store.mark_incomplete_ai_jobs_interrupted()

    def response(data, status=200, cache_control='no-cache'):
        return JSONResponse(
            data,
            status_code=status,
            headers={'Cache-Control': cache_control},
        )

    def apply_reader_security_headers(target_response, file_path):
        try:
            markup = Path(file_path).read_text(encoding='utf-8')
        except (OSError, UnicodeDecodeError):
            return target_response
        target_response.headers[
            'Content-Security-Policy'
        ] = reader_content_security_policy(markup)
        target_response.headers['X-Content-Type-Options'] = 'nosniff'
        return target_response

    def request_session_token(request):
        return request.scope.get(
            SESSION_TOKEN_SCOPE_KEY,
            request.cookies.get(SESSION_COOKIE),
        )

    def set_session_cookie(target_response, raw_session):
        target_response.set_cookie(
            SESSION_COOKIE,
            raw_session,
            max_age=auth_service.config.session_ttl_seconds,
            **session_cookie_options(auth_service.config),
        )

    def delete_session_cookie(target_response):
        cookie_options = session_cookie_options(auth_service.config)
        target_response.delete_cookie(
            SESSION_COOKIE,
            path=cookie_options['path'],
            secure=cookie_options['secure'],
            httponly=cookie_options['httponly'],
            samesite=cookie_options['samesite'],
        )

    def set_setup_nonce_cookie(target_response, nonce):
        target_response.set_cookie(
            SETUP_NONCE_COOKIE,
            nonce,
            max_age=600,
            path='/setup',
            secure=auth_service.config.cookie_secure,
            httponly=True,
            samesite='strict',
        )

    def delete_setup_nonce_cookie(target_response):
        target_response.delete_cookie(
            SETUP_NONCE_COOKIE,
            path='/setup',
            secure=auth_service.config.cookie_secure,
            httponly=True,
            samesite='strict',
        )

    def set_auth_nonce_cookie(target_response, nonce):
        target_response.set_cookie(
            AUTH_NONCE_COOKIE,
            nonce,
            max_age=600,
            path='/',
            secure=auth_service.config.cookie_secure,
            httponly=True,
            samesite='strict',
        )

    def delete_auth_nonce_cookie(target_response):
        target_response.delete_cookie(
            AUTH_NONCE_COOKIE,
            path='/',
            secure=auth_service.config.cookie_secure,
            httponly=True,
            samesite='strict',
        )

    async def json_object(request):
        try:
            data = await request.json()
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None
        return data if isinstance(data, dict) else None

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

    def user_data(user):
        payload = {
            'id': user.user_id,
            'username': user.username,
            'role': user.role,
            'enabled': user.enabled,
        }
        if user.role == 'member':
            payload['ai_access'] = store.get_ai_user_access(user.user_id)
        return payload

    def admin_book_data(book):
        try:
            metadata = json.loads(book.metadata_json)
        except json.JSONDecodeError:
            metadata = {}
        return {
            'id': book.book_id,
            'title': metadata.get('title') or 'EPUB Book',
            'epub_tags': list(metadata.get('tags') or ()),
            'visibility': book.visibility,
            'grants': list(store.book_grants(book.book_id)),
            'ai_profile': store.get_book_ai_profile(book.book_id),
            'ai_tags': list(store.book_ai_tags(book.book_id)),
            'effective_tags': list(store.effective_book_tags(book.book_id)),
        }

    def admin_identity_data(identity):
        user = store.get_user(identity.user_id)
        return {
            'issuer': identity.issuer,
            'subject': identity.subject,
            'user_id': identity.user_id,
            'username': user.username,
            'display_name': identity.display_name,
        }

    def session_data(record, current_session_id):
        def iso_timestamp(value):
            try:
                return datetime.fromtimestamp(
                    float(value),
                    timezone.utc,
                ).isoformat().replace('+00:00', 'Z')
            except (TypeError, ValueError, OverflowError):
                return value

        return {
            'id': record.session_id,
            'created_at': iso_timestamp(record.created_at),
            'last_used_at': iso_timestamp(record.last_used_at),
            'expires_at': iso_timestamp(record.expires_at),
            'client_address': record.client_address,
            'user_agent': record.user_agent,
            'current': record.session_id == current_session_id,
        }

    def client_key(request):
        return request.client.host if request.client is not None else 'unknown'

    def session_client_metadata(request):
        return {
            'client_address': (
                request.client.host if request.client is not None else None
            ),
            'user_agent': request.headers.get('user-agent'),
        }

    async def form_data(request, maximum_size=64 * 1024):
        content_type = request.headers.get('content-type', '').split(';', 1)[0]
        if content_type != 'application/x-www-form-urlencoded':
            raise ValueError('Unsupported form content type')
        body = await request.body()
        if len(body) > maximum_size:
            raise ValueError('Form is too large')
        values = parse_qs(
            body.decode('utf-8'),
            keep_blank_values=True,
            strict_parsing=False,
        )
        return {
            key: entries[-1] if entries else ''
            for key, entries in values.items()
        }

    def valid_same_origin_request_source(request):
        fetch_site = request.headers.get('sec-fetch-site')
        if fetch_site and fetch_site.strip().lower() != 'same-origin':
            return False
        host = request.headers.get('host', '').strip()
        if not host or any(character.isspace() for character in host) or ',' in host:
            return False
        origin = request.headers.get('origin')
        if not origin:
            return True
        try:
            parsed_origin = urlsplit(origin)
            parsed_host = urlsplit('//' + host)
            if (
                parsed_origin.scheme not in {'http', 'https'}
                or parsed_origin.username is not None
                or parsed_origin.password is not None
                or parsed_origin.query
                or parsed_origin.fragment
                or parsed_origin.path not in {'', '/'}
                or parsed_origin.hostname is None
                or parsed_host.hostname is None
            ):
                return False
            default_port = 443 if parsed_origin.scheme == 'https' else 80
            origin_port = parsed_origin.port or default_port
            host_port = parsed_host.port or default_port
        except ValueError:
            return False
        return (
            parsed_origin.hostname.casefold() == parsed_host.hostname.casefold()
            and origin_port == host_port
        )

    def valid_anonymous_auth_request(request):
        if not valid_same_origin_request_source(request):
            return False
        cookie_nonce = request.cookies.get(AUTH_NONCE_COOKIE)
        supplied_nonce = request.headers.get(AUTH_NONCE_HEADER)
        if (
            not isinstance(cookie_nonce, str)
            or not isinstance(supplied_nonce, str)
            or not cookie_nonce
            or not supplied_nonce
        ):
            return False
        try:
            return secrets.compare_digest(cookie_nonce, supplied_nonce)
        except TypeError:
            return False

    def invalid_setup_request():
        return response(
            error_payload('invalid_setup_request', 'Invalid setup request'),
            403,
            cache_control='no-store',
        )

    def invalid_auth_request():
        return response(
            error_payload('invalid_auth_request', 'Invalid authentication request'),
            403,
            cache_control='no-store',
        )

    def public_json_error(error):
        if error == 'unsupported_media_type':
            return response(
                error_payload(
                    'unsupported_media_type',
                    'Content-Type must be application/json',
                ),
                415,
                cache_control='no-store',
            )
        if error == 'body_too_large':
            return response(
                error_payload('body_too_large', 'Request body is too large'),
                413,
                cache_control='no-store',
            )
        return response(
            error_payload('invalid_json', 'Invalid JSON data'),
            400,
            cache_control='no-store',
        )

    def setup_form(
        error=None,
        status_code=200,
        locale='en',
        locale_explicit=False,
    ):
        locale = normalize_login_locale(locale)
        nonce = secrets.token_urlsafe(32)
        copy = SETUP_COPY[locale]
        error_key = {
            'invalid': 'account.error.invalidSetup',
            'password_mismatch': 'account.error.passwordMismatch',
            'username_unavailable': 'account.error.username_unavailable',
        }.get(error)
        error_markup = (
            '<p class="auth-alert" role="alert" data-i18n="{}">{}</p>'.format(
                error_key,
                copy[error],
            )
            if error_key is not None
            else ''
        )
        en_selected = ' selected' if locale == 'en' else ''
        zh_selected = ' selected' if locale == 'zh-CN' else ''
        footer_markup = render_footer(datetime.now().year)
        markup = f'''<!doctype html><html lang="{locale}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light dark">
<title data-i18n="account.setupPageTitle">{copy['page_title']}</title>
<link rel="stylesheet" href="/assets/theme.css">
<link rel="stylesheet" href="/assets/account.css">
<script src="/assets/theme-bootstrap.js"></script>
<script>window.EpubBrowserBasePath="/";window.EpubBrowserDisableManifest=true;</script>
<script src="/assets/i18n.js"></script>
<script src="/assets/version-check.js" defer></script>
<script>window.EpubBrowserI18n.init();{'window.EpubBrowserI18n.setLocale(' + json.dumps(locale) + ');' if locale_explicit else ''}</script>
</head><body class="auth-page"><main class="auth-shell"><div class="auth-stack"><section class="auth-card setup-card">
<header class="auth-card-header"><div class="auth-brand"><span class="auth-brand-mark" aria-hidden="true">📖</span><span>EPUB Browser</span></div>
<label class="auth-language setup-language"><span class="auth-language-label" data-i18n="common.language">{copy['language']}</span>
<select id="setupLocaleSelect" aria-label="{copy['language']}" data-i18n-aria-label="common.language">
<option value="en"{en_selected} data-i18n="common.english">English</option>
<option value="zh-CN"{zh_selected} data-i18n="common.chinese">中文</option>
</select></label></header>
<div class="auth-intro"><h1 data-i18n="account.setupTitle">{copy['title']}</h1>
<p class="auth-description" data-i18n="account.setupDescription">{copy['description']}</p></div>
<form class="auth-form" id="setupForm" method="post" action="/setup">
<input type="hidden" name="setup_nonce" value="{nonce}">
<input type="hidden" name="locale" value="{locale}">
{error_markup}
<label class="auth-field"><span data-i18n="account.username">{copy['username']}</span><input name="username" autocomplete="username" required></label>
<label class="auth-field"><span data-i18n="account.password">{copy['password']}</span><input name="password" type="password" autocomplete="new-password" required></label>
<label class="auth-field"><span data-i18n="account.confirmPassword">{copy['password_confirmation']}</span><input name="password_confirmation" type="password" autocomplete="new-password" required></label>
<button class="auth-primary-button" type="submit" data-i18n="account.createSuperuser">{copy['submit']}</button>
</form></section>{footer_markup}</div></main>
<script>(function() {{
var i18n=window.EpubBrowserI18n;
var localeSelect=document.getElementById('setupLocaleSelect');
var localeField=document.querySelector('input[name="locale"]');
if(i18n&&localeSelect){{
localeSelect.value=i18n.getLocale();
localeSelect.addEventListener('change',function(){{
i18n.setLocale(localeSelect.value);
if(localeField)localeField.value=localeSelect.value;
}});
}}
}}());</script></body></html>'''
        page = HTMLResponse(
            markup,
            status_code=status_code,
            headers={'Cache-Control': 'no-store'},
        )
        set_setup_nonce_cookie(page, nonce)
        return page

    async def setup(request):
        requested_locale = normalize_login_locale(
            request.query_params.get('lang'),
            request.headers.get('accept-language', ''),
        )
        locale_explicit = 'lang' in request.query_params
        if request.method in {'GET', 'HEAD'}:
            if store.has_administrator():
                return RedirectResponse(
                    '/' if request.scope.get(PRINCIPAL_SCOPE_KEY) is not None else '/login',
                    status_code=303,
                    headers={'Cache-Control': 'no-store'},
                )
            return setup_form(
                locale=requested_locale,
                locale_explicit=locale_explicit,
            )
        if not valid_same_origin_request_source(request):
            return invalid_setup_request()
        try:
            form = await form_data(request)
        except (UnicodeDecodeError, ValueError):
            return invalid_setup_request()
        cookie_nonce = request.cookies.get(SETUP_NONCE_COOKIE)
        submitted_nonce = form.get('setup_nonce')
        if (
            not isinstance(cookie_nonce, str)
            or not isinstance(submitted_nonce, str)
            or not cookie_nonce
            or not submitted_nonce
            or not secrets.compare_digest(cookie_nonce, submitted_nonce)
        ):
            return invalid_setup_request()
        if store.has_administrator():
            completed = RedirectResponse(
                '/login',
                status_code=303,
                headers={'Cache-Control': 'no-store'},
            )
            delete_setup_nonce_cookie(completed)
            return completed
        submitted_locale = normalize_login_locale(
            form.get('locale') or requested_locale
        )
        username = form.get('username')
        password = form.get('password')
        confirmation = form.get('password_confirmation')
        if (
            not isinstance(username, str)
            or not username.strip()
            or not isinstance(password, str)
            or not password
            or not isinstance(confirmation, str)
        ):
            return setup_form(
                error='invalid',
                status_code=400,
                locale=submitted_locale,
                locale_explicit=True,
            )
        if password != confirmation:
            return setup_form(
                error='password_mismatch',
                status_code=400,
                locale=submitted_locale,
                locale_explicit=True,
            )
        try:
            raw_session, _ = auth_service.complete_setup(
                username,
                password,
                **session_client_metadata(request),
            )
        except SetupAlreadyCompleteError:
            completed = RedirectResponse(
                '/login',
                status_code=303,
                headers={'Cache-Control': 'no-store'},
            )
            delete_setup_nonce_cookie(completed)
            return completed
        except sqlite3.IntegrityError:
            return setup_form(
                error='username_unavailable',
                status_code=409,
                locale=submitted_locale,
                locale_explicit=True,
            )
        except ValueError:
            return setup_form(
                error='invalid',
                status_code=400,
                locale=submitted_locale,
                locale_explicit=True,
            )
        redirect = RedirectResponse(
            '/',
            status_code=303,
            headers={'Cache-Control': 'no-store'},
        )
        set_session_cookie(redirect, raw_session)
        delete_setup_nonce_cookie(redirect)
        return redirect

    def login_form(
        next_path='/',
        error=None,
        status_code=200,
        locale='en',
        locale_explicit=False,
    ):
        safe_next = html.escape(_safe_relative_path(next_path), quote=True)
        locale = normalize_login_locale(locale)
        nonce = secrets.token_urlsafe(32)
        copy = LOGIN_COPY[locale]
        error_markup = (
            '<p class="auth-alert" id="loginError" role="alert" data-i18n="account.error.invalid_credentials">'
            + copy['invalid_credentials']
            + '</p>'
            if error
            else '<p class="auth-alert" id="loginError" role="alert" data-i18n="account.error.invalid_credentials" hidden>'
            + copy['invalid_credentials']
            + '</p>'
        )
        en_selected = ' selected' if locale == 'en' else ''
        zh_selected = ' selected' if locale == 'zh-CN' else ''
        footer_markup = render_footer(datetime.now().year)
        markup = f'''<!doctype html><html lang="{locale}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light dark">
<meta name="epub-browser-auth-nonce" content="{nonce}">
<title data-i18n="account.loginPageTitle">{copy['page_title']}</title>
<link rel="stylesheet" href="/assets/theme.css">
<link rel="stylesheet" href="/assets/account.css">
<script src="/assets/theme-bootstrap.js"></script>
<script>window.EpubBrowserBasePath="/";window.EpubBrowserDisableManifest=true;</script>
<script src="/assets/i18n.js"></script>
<script src="/assets/version-check.js" defer></script>
<script>window.EpubBrowserI18n.init();{'window.EpubBrowserI18n.setLocale(' + json.dumps(locale) + ');' if locale_explicit else ''}</script>
</head><body class="auth-page"><main class="auth-shell"><div class="auth-stack"><section class="auth-card login-card">
<header class="auth-card-header"><div class="auth-brand"><span class="auth-brand-mark" aria-hidden="true">📖</span><span>EPUB Browser</span></div>
<label class="auth-language login-language"><span class="auth-language-label" data-i18n="common.language">{copy['language']}</span>
<select id="loginLocaleSelect" aria-label="{copy['language']}" data-i18n-aria-label="common.language">
<option value="en"{en_selected} data-i18n="common.english">English</option>
<option value="zh-CN"{zh_selected} data-i18n="common.chinese">中文</option>
</select></label></header>
<div class="auth-intro"><h1 data-i18n="account.signIn">{copy['sign_in']}</h1>
<p class="auth-description" data-i18n="account.loginDescription">{copy['description']}</p></div>
<form class="auth-form" id="loginForm" method="post" action="/login">
<input type="hidden" name="next" value="{safe_next}">
<input type="hidden" name="locale" value="{locale}">
{error_markup}
<label class="auth-field"><span data-i18n="account.username">{copy['username']}</span><input name="username" autocomplete="username" required></label>
<label class="auth-field"><span data-i18n="account.password">{copy['password']}</span><input name="password" type="password" autocomplete="current-password" required></label>
<button class="auth-primary-button" type="submit" data-i18n="account.signIn">{copy['sign_in']}</button>
</form></section>{footer_markup}</div></main>
<script>(function() {{
var i18n=window.EpubBrowserI18n;
var localeSelect=document.getElementById('loginLocaleSelect');
var localeField=document.querySelector('input[name="locale"]');
if(i18n&&localeSelect){{
localeSelect.value=i18n.getLocale();
localeSelect.addEventListener('change',function(){{
i18n.setLocale(localeSelect.value);
if(localeField)localeField.value=localeSelect.value;
}});
}}
var loginForm=document.getElementById('loginForm');
var loginError=document.getElementById('loginError');
function setLoginError(visible){{
if(loginError)loginError.hidden=!visible;
if(loginForm)Array.prototype.forEach.call(loginForm.querySelectorAll('input[name="username"],input[name="password"]'),function(field){{
if(visible)field.setAttribute('aria-invalid','true');else field.removeAttribute('aria-invalid');
}});
}}
if(loginForm)loginForm.addEventListener('submit',function(event){{
event.preventDefault();
setLoginError(false);
var username=loginForm.elements.username.value;
var password=loginForm.elements.password.value;
var next=loginForm.elements.next.value;
var locale=loginForm.elements.locale.value;
fetch('/login',{{
method:'POST',credentials:'same-origin',
headers:{{'Content-Type':'application/json','{AUTH_NONCE_HEADER}':'{nonce}'}},
body:JSON.stringify({{username:username,password:password,next:next,locale:locale}})
}}).then(function(response){{
return response.json().catch(function(){{return {{}};}}).then(function(payload){{
if(!response.ok){{setLoginError(true);return;}}
window.location.assign(payload.redirect||'/');
}});
}}).catch(function(){{setLoginError(true);}});
}});
}}());</script></body></html>'''
        page = HTMLResponse(
            markup,
            status_code=status_code,
            headers={'Cache-Control': 'no-store'},
        )
        set_auth_nonce_cookie(page, nonce)
        return page

    async def login(request):
        requested_next = _safe_relative_path(request.query_params.get('next', '/'))
        requested_locale = normalize_login_locale(
            request.query_params.get('lang'),
            request.headers.get('accept-language', ''),
        )
        locale_explicit = 'lang' in request.query_params
        if request.method == 'GET':
            if request.scope.get(PRINCIPAL_SCOPE_KEY) is not None:
                return RedirectResponse(requested_next, status_code=303)
            return login_form(
                requested_next,
                locale=requested_locale,
                locale_explicit=locale_explicit,
            )
        current_principal = request.scope.get(PRINCIPAL_SCOPE_KEY)
        if current_principal is None and not valid_anonymous_auth_request(request):
            return invalid_auth_request()
        data, parse_error = await bounded_public_json_object(request)
        if parse_error is not None:
            return public_json_error(parse_error)
        next_path = _safe_relative_path(data.get('next') or requested_next)
        client_key = request.client.host if request.client is not None else 'unknown'
        principal = auth_service.authenticate_password(
            data.get('username', ''),
            data.get('password', ''),
            client_key,
        )
        if principal is None:
            return response(
                error_payload(
                    'invalid_credentials',
                    'Invalid username or password',
                ),
                401,
                cache_control='no-store',
            )

        current_session = request_session_token(request)
        if current_principal is not None and current_session:
            raw_session, _ = auth_service.replace_session(
                principal,
                current_session,
                **session_client_metadata(request),
            )
        else:
            raw_session, _ = auth_service.create_session(
                principal,
                **session_client_metadata(request),
            )
        logged_in = response(
            {'redirect': next_path},
            cache_control='no-store',
        )
        set_session_cookie(logged_in, raw_session)
        delete_auth_nonce_cookie(logged_in)
        return logged_in

    async def logout(request):
        auth_service.revoke_session(request.cookies.get(SESSION_COOKIE))
        redirect = RedirectResponse(
            '/login',
            status_code=303,
            headers={'Cache-Control': 'no-store'},
        )
        delete_session_cookie(redirect)
        return redirect

    async def session(request):
        principal = require_principal(request)
        raw_session = request_session_token(request)
        return response(
            {
                'user': {
                    'id': principal.user_id,
                    'username': principal.username,
                    'role': principal.role,
                },
                'csrf_token': auth_service.issue_csrf_token(
                    principal,
                    raw_session,
                ),
                'authentication': {
                    'proxy_enabled': bool(
                        auth_service.config.trusted_proxy_networks
                    ),
                    'pending_proxy_identity': request.scope.get(
                        PENDING_IDENTITY_SCOPE_KEY
                    ) is not None,
                },
            },
            cache_control='no-store',
        )

    async def csrf(request):
        principal = require_principal(request)
        return response(
            {
                'csrf_token': auth_service.issue_csrf_token(
                    principal,
                    request_session_token(request),
                )
            },
            cache_control='no-store',
        )

    async def link_proxy_identity(request):
        current_principal = request.scope.get(PRINCIPAL_SCOPE_KEY)
        if current_principal is None and not valid_anonymous_auth_request(request):
            return invalid_auth_request()
        data, parse_error = await bounded_public_json_object(request)
        if parse_error is not None:
            return public_json_error(parse_error)
        pending_identity = request.scope.get(PENDING_IDENTITY_SCOPE_KEY)
        if pending_identity is None:
            return response(
                error_payload(
                    'proxy_identity_required',
                    'An unrecognized trusted proxy identity is required',
                ),
                400,
                cache_control='no-store',
            )
        username = data.get('username')
        password = data.get('password')
        if not isinstance(username, str) or not isinstance(password, str):
            return response(
                error_payload('invalid_credentials', 'Invalid username or password'),
                401,
                cache_control='no-store',
            )
        principal = auth_service.authenticate_password(
            username,
            password,
            client_key(request),
        )
        if principal is None:
            return response(
                error_payload('invalid_credentials', 'Invalid username or password'),
                401,
                cache_control='no-store',
            )
        try:
            identity = store.create_identity(
                pending_identity.issuer,
                pending_identity.subject,
                principal.user_id,
                pending_identity.display_name,
            )
        except sqlite3.IntegrityError:
            return response(
                error_payload(
                    'identity_already_linked',
                    'External identity is already linked',
                ),
                409,
                cache_control='no-store',
            )
        current_session = request_session_token(request)
        if current_principal is not None and current_session:
            raw_session, _ = auth_service.replace_session(
                principal,
                current_session,
                **session_client_metadata(request),
            )
        else:
            raw_session, _ = auth_service.create_session(
                principal,
                **session_client_metadata(request),
            )
        linked = response(
            {
                'user': {
                    'id': principal.user_id,
                    'username': principal.username,
                    'role': principal.role,
                },
                'identity': {
                    'issuer': identity.issuer,
                    'subject': identity.subject,
                    'display_name': identity.display_name,
                },
            },
            201,
            cache_control='no-store',
        )
        set_session_cookie(linked, raw_session)
        delete_auth_nonce_cookie(linked)
        return linked

    async def change_password(request):
        principal = require_principal(request)
        data = await json_object(request)
        if data is None:
            return response(error_payload('invalid_json', 'Invalid JSON data'), 400)
        current_password = data.get('current_password')
        new_password = data.get('new_password', data.get('password'))
        if (
            not isinstance(current_password, str)
            or not isinstance(new_password, str)
            or not new_password
        ):
            return response(
                error_payload('invalid_password', 'Invalid password'),
                400,
            )
        authenticated = auth_service.authenticate_password(
            principal.username,
            current_password,
            client_key(request),
        )
        if authenticated is None or authenticated.user_id != principal.user_id:
            return response(
                error_payload('invalid_credentials', 'Invalid username or password'),
                401,
            )
        store.set_password_hash_and_revoke_sessions(
            principal.user_id,
            hash_password(new_password),
        )
        changed = response({'message': 'Password changed'})
        delete_session_cookie(changed)
        return changed

    async def list_own_sessions(request):
        principal = require_principal(request)
        current_session_id = store.session_id_from_token(
            request_session_token(request),
            user_id=principal.user_id,
        )
        sessions = store.list_sessions(
            principal.user_id,
            active_only=True,
        )
        return response(
            {
                'sessions': [
                    session_data(record, current_session_id)
                    for record in sessions
                ]
            }
        )

    async def revoke_own_session(request):
        principal = require_principal(request)
        session_id = request.path_params['session_id']
        current_session_id = store.session_id_from_token(
            request_session_token(request),
            user_id=principal.user_id,
        )
        if not store.revoke_user_session(principal.user_id, session_id):
            return response(error_payload('not_found', 'Session not found'), 404)
        revoked = response({'message': 'Session revoked'})
        if session_id == current_session_id:
            delete_session_cookie(revoked)
        return revoked

    async def admin_users(request):
        require_admin(request)
        if request.method == 'GET':
            return response(
                {'users': [user_data(user) for user in store.list_users()]}
            )
        data = await json_object(request)
        if data is None:
            return response(error_payload('invalid_json', 'Invalid JSON data'), 400)
        username = data.get('username')
        password = data.get('password')
        role = data.get('role', 'member')
        if (
            not isinstance(username, str)
            or not username.strip()
            or not isinstance(password, str)
            or not password
            or role not in {'admin', 'member'}
        ):
            return response(
                error_payload('invalid_user', 'Invalid user data'),
                400,
            )
        try:
            principal = store.create_user(
                username,
                hash_password(password),
                role=role,
            )
        except (ValueError, sqlite3.IntegrityError):
            return response(
                error_payload('username_unavailable', 'Username is unavailable'),
                409,
            )
        return response(
            {'user': user_data(store.get_user_by_username(principal.username))},
            201,
        )

    async def admin_user(request):
        require_admin(request)
        username = request.path_params['username']
        try:
            user = store.get_user_by_username(username)
        except ValueError:
            user = None
        if user is None:
            return response(error_payload('not_found', 'User not found'), 404)
        data = await json_object(request)
        if data is None:
            return response(error_payload('invalid_json', 'Invalid JSON data'), 400)
        supported = {'enabled', 'role', 'revoke_sessions'}
        if not supported.intersection(data):
            return response(error_payload('invalid_user', 'Invalid user data'), 400)
        enabled = data.get('enabled')
        role = data.get('role')
        revoke_sessions = data.get('revoke_sessions', False)
        if (
            ('enabled' in data and not isinstance(enabled, bool))
            or ('role' in data and role not in {'admin', 'member'})
            or not isinstance(revoke_sessions, bool)
        ):
            return response(error_payload('invalid_user', 'Invalid user data'), 400)
        try:
            updated = store.update_user(
                user.user_id,
                enabled=enabled if 'enabled' in data else None,
                role=role if 'role' in data else None,
                revoke_sessions=revoke_sessions,
            )
        except RuntimeError:
            return response(
                error_payload(
                    'last_enabled_admin',
                    'The last enabled administrator cannot be disabled or demoted',
                ),
                409,
            )
        return response({'user': user_data(updated)})

    async def admin_reset_password(request):
        require_admin(request)
        username = request.path_params['username']
        try:
            user = store.get_user_by_username(username)
        except ValueError:
            user = None
        if user is None:
            return response(error_payload('not_found', 'User not found'), 404)
        data = await json_object(request)
        password = data.get('password') if data is not None else None
        if not isinstance(password, str) or not password:
            return response(
                error_payload('invalid_password', 'Invalid password'),
                400,
            )
        updated = store.set_password_hash_and_revoke_sessions(
            user.user_id,
            hash_password(password),
        )
        return response({'user': user_data(updated)})

    async def admin_identities(request):
        require_admin(request)
        if request.method == 'GET':
            return response(
                {
                    'identities': [
                        admin_identity_data(identity)
                        for identity in store.list_all_identities()
                    ]
                }
            )
        data = await json_object(request)
        if data is None:
            return response(error_payload('invalid_json', 'Invalid JSON data'), 400)
        issuer = data.get('issuer')
        subject = data.get('subject')
        if isinstance(issuer, str):
            issuer = issuer.strip()
        if isinstance(subject, str):
            subject = subject.strip()
        if request.method == 'DELETE':
            if not isinstance(issuer, str) or not isinstance(subject, str):
                return response(
                    error_payload('invalid_identity', 'Invalid identity data'),
                    400,
                )
            try:
                deleted = store.delete_identity(issuer, subject)
            except ValueError:
                deleted = False
            if not deleted:
                return response(error_payload('not_found', 'Identity not found'), 404)
            return response({'message': 'Identity deleted'})

        user_id = data.get('user_id')
        display_name = data.get('display_name')
        if (
            not isinstance(issuer, str)
            or not issuer.strip()
            or not isinstance(subject, str)
            or not subject.strip()
            or not isinstance(user_id, str)
            or not user_id
            or (display_name is not None and not isinstance(display_name, str))
        ):
            return response(
                error_payload('invalid_identity', 'Invalid identity data'),
                400,
            )
        try:
            identity = store.create_identity(
                issuer,
                subject,
                user_id,
                display_name.strip() if display_name else None,
            )
        except KeyError:
            return response(error_payload('not_found', 'User not found'), 404)
        except ValueError:
            return response(
                error_payload('invalid_identity', 'Invalid identity data'),
                400,
            )
        except sqlite3.IntegrityError:
            return response(
                error_payload(
                    'identity_already_linked',
                    'External identity is already linked',
                ),
                409,
            )
        return response({'identity': admin_identity_data(identity)}, 201)

    async def admin_books(request):
        require_admin(request)
        return response(
            {'books': [admin_book_data(book) for book in store.active_books()]}
        )

    async def admin_book(request):
        require_admin(request)
        book_id = request.path_params['book_id']
        data = await json_object(request)
        if data is None:
            return response(error_payload('invalid_json', 'Invalid JSON data'), 400)
        visibility = data.get('visibility')
        if visibility not in {'authenticated', 'restricted'}:
            return response(
                error_payload('invalid_visibility', 'Invalid book visibility'),
                400,
            )
        try:
            book = store.set_book_visibility(book_id, visibility)
        except KeyError:
            return response(error_payload('not_found', 'Book not found'), 404)
        return response({'book': admin_book_data(book)})

    async def admin_book_grant(request):
        require_admin(request)
        book_id = request.path_params['book_id']
        user_id = request.path_params['user_id']
        try:
            store.get_book(book_id)
        except KeyError:
            return response(error_payload('not_found', 'Book not found'), 404)
        try:
            user = store.get_user(user_id)
        except (KeyError, ValueError):
            return response(error_payload('not_found', 'User not found'), 404)
        if not user.enabled:
            return response(
                error_payload('user_disabled', 'User is disabled'),
                400,
            )
        if request.method == 'PUT':
            store.grant_book_access(book_id, user_id)
            granted = True
        else:
            store.revoke_book_access(book_id, user_id)
            granted = False
        return response(
            {
                'grant': {
                    'book_id': book_id,
                    'user_id': user_id,
                    'granted': granted,
                }
            }
        )

    async def admin_book_grants(request):
        require_admin(request)
        book_id = request.path_params['book_id']
        data = await json_object(request)
        user_ids = data.get('user_ids') if data is not None else None
        if (
            not isinstance(user_ids, list)
            or any(
                not isinstance(user_id, str) or not user_id
                for user_id in user_ids
            )
        ):
            return response(
                error_payload('invalid_user', 'Invalid book grant users'),
                400,
            )
        try:
            grants = store.replace_book_grants(book_id, user_ids)
        except KeyError:
            return response(
                error_payload('not_found', 'Book or user not found'),
                404,
            )
        except ValueError:
            return response(
                error_payload('invalid_user', 'Invalid book grant users'),
                400,
            )
        return response(
            {
                'grants': {
                    'book_id': book_id,
                    'user_ids': list(grants),
                }
            }
        )

    async def admin_ai_settings(request):
        require_admin(request)
        if request.method == 'GET':
            return response({'settings': store.get_ai_settings()})
        data = await json_object(request)
        if data is None:
            return response(error_payload('invalid_json', 'Invalid JSON data'), 400)
        required = {
            'enabled', 'base_url', 'model', 'timeout_seconds',
            'max_concurrency', 'daily_limit',
        }
        if not required.issubset(data):
            return response(error_payload('invalid_ai_settings', 'Invalid AI settings'), 400)
        api_key = data.get('api_key') if 'api_key' in data else None
        clear_api_key = data.get('clear_api_key', False)
        if (
            not isinstance(data['enabled'], bool)
            or not isinstance(data['base_url'], str)
            or not isinstance(data['model'], str)
            or (api_key is not None and not isinstance(api_key, str))
            or not isinstance(clear_api_key, bool)
            or isinstance(data['timeout_seconds'], bool)
            or not isinstance(data['timeout_seconds'], int)
            or isinstance(data['max_concurrency'], bool)
            or not isinstance(data['max_concurrency'], int)
            or isinstance(data['daily_limit'], bool)
            or not isinstance(data['daily_limit'], int)
        ):
            return response(error_payload('invalid_ai_settings', 'Invalid AI settings'), 400)
        try:
            if data['enabled']:
                validate_provider_base_url(data['base_url'])
            settings = store.set_ai_settings(
                enabled=data['enabled'],
                base_url=data['base_url'],
                api_key=api_key,
                model=data['model'],
                timeout_seconds=data['timeout_seconds'],
                max_concurrency=data['max_concurrency'],
                daily_limit=data['daily_limit'],
                clear_api_key=clear_api_key,
            )
        except ValueError:
            return response(error_payload('invalid_ai_settings', 'Invalid AI settings'), 400)
        return response({'settings': settings})

    async def admin_ai_user_access(request):
        require_admin(request)
        user_id = request.path_params['user_id']
        try:
            user = store.get_user(user_id)
        except (KeyError, ValueError):
            user = None
        if user is None:
            return response(error_payload('not_found', 'User not found'), 404)
        if request.method == 'GET':
            return response({'access': store.get_ai_user_access(user_id)})
        data = await json_object(request)
        limit = data.get('daily_limit') if isinstance(data, dict) else None
        if (
            not isinstance(data, dict)
            or not isinstance(data.get('enabled'), bool)
            or (
                'daily_limit' in data
                and (isinstance(limit, bool) or not isinstance(limit, int) or limit < 0)
            )
        ):
            return response(error_payload('invalid_ai_access', 'Invalid AI access'), 400)
        try:
            store.set_ai_user_access(
                user_id,
                enabled=data['enabled'],
                daily_limit=limit if 'daily_limit' in data else None,
            )
        except ValueError:
            return response(error_payload('invalid_ai_access', 'Invalid AI access'), 400)
        return response({'access': store.get_ai_user_access(user_id)})

    async def admin_ai_tags(request):
        require_admin(request)
        if request.method == 'GET':
            return response({'tags': list(store.list_ai_tags())})
        data = await json_object(request)
        name = data.get('name') if isinstance(data, dict) else None
        if not isinstance(name, str):
            return response(error_payload('invalid_ai_tag', 'Invalid AI tag'), 400)
        try:
            tag = store.create_ai_tag(name)
        except ValueError:
            return response(error_payload('invalid_ai_tag', 'Invalid AI tag'), 400)
        return response({'tag': tag}, 201)

    async def admin_ai_tag(request):
        require_admin(request)
        tag_id = request.path_params['tag_id']
        if request.method == 'DELETE':
            if not store.delete_ai_tag(tag_id):
                return response(error_payload('not_found', 'AI tag not found'), 404)
            return response({'message': 'AI tag deleted'})
        data = await json_object(request)
        name = data.get('name') if isinstance(data, dict) else None
        if not isinstance(name, str):
            return response(error_payload('invalid_ai_tag', 'Invalid AI tag'), 400)
        try:
            tag = store.rename_ai_tag(tag_id, name)
        except KeyError:
            return response(error_payload('not_found', 'AI tag not found'), 404)
        except ValueError:
            return response(error_payload('invalid_ai_tag', 'Invalid AI tag'), 400)
        return response({'tag': tag})

    async def admin_book_ai(request):
        require_admin(request)
        book_id = request.path_params['book_id']
        try:
            store.get_book(book_id)
        except KeyError:
            return response(error_payload('not_found', 'Book not found'), 404)
        if request.method == 'GET':
            return response({
                'profile': store.get_book_ai_profile(book_id),
                'tags': list(store.book_ai_tags(book_id)),
                'effective_tags': list(store.effective_book_tags(book_id)),
            })
        data = await json_object(request)
        if data is None or not {'profile', 'tag_ids'}.issubset(data):
            return response(error_payload('invalid_book_ai', 'Invalid book AI settings'), 400)
        profile = data['profile']
        tag_ids = data['tag_ids']
        if (
            profile not in {'auto', 'technical', 'fiction', 'general'}
            or not isinstance(tag_ids, list)
            or any(not isinstance(tag_id, str) or not tag_id for tag_id in tag_ids)
        ):
            return response(error_payload('invalid_book_ai', 'Invalid book AI settings'), 400)
        try:
            store.set_book_ai_profile(book_id, profile)
            tags = store.replace_book_ai_tags(book_id, tag_ids)
        except (ValueError, KeyError):
            return response(error_payload('invalid_book_ai', 'Invalid book AI settings'), 400)
        return response({
            'profile': store.get_book_ai_profile(book_id),
            'tags': list(tags),
            'effective_tags': list(store.effective_book_tags(book_id)),
        })

    async def admin_ai_results(request):
        require_admin(request)
        data = await json_object(request)
        if data is None:
            data = {}
        book_id = data.get('book_id')
        revision = data.get('config_revision')
        if (
            (book_id is not None and not isinstance(book_id, str))
            or (revision is not None and (isinstance(revision, bool) or not isinstance(revision, int)))
        ):
            return response(error_payload('invalid_ai_cache_scope', 'Invalid AI cache scope'), 400)
        if book_id is not None and store.book_by_id(book_id) is None:
            return response(error_payload('not_found', 'Book not found'), 404)
        return response({
            'deleted': store.clear_ai_reading_results(
                book_id=book_id, config_revision=revision
            )
        })

    def ai_error_response(error):
        status = {
            'ai_disabled': 503,
            'ai_not_authorized': 403,
            'ai_quota_exhausted': 429,
            'book_not_found': 404,
            'chapter_not_found': 404,
            'ai_result_not_found': 404,
        }.get(error.code, 400)
        return response(error_payload(error.code, 'AI reading request failed'), status)

    async def ai_status(request):
        principal = require_principal(request)
        settings = store.get_ai_settings()
        return response({
            'enabled': settings['enabled'],
            'authorized': settings['enabled'] and store.can_use_ai(principal),
            'daily_limit': store.ai_daily_limit(principal) if store.can_use_ai(principal) else None,
        })

    async def book_effective_metadata(request):
        principal = require_principal(request)
        book_id = request.path_params['book_id']
        if not store.can_read_book(principal.user_id, principal.role, book_id):
            return response(error_payload('forbidden', 'Forbidden'), 403)
        return response({
            'tags': list(store.effective_book_tags(book_id)),
            'ai_profile': store.get_book_ai_profile(book_id),
        })

    async def ai_reading_request(request):
        principal = require_principal(request)
        data, error = await bounded_public_json_object(request)
        if error:
            return response(error_payload(error, 'Invalid AI reading request'), 400)
        scope = data.get('scope')
        book_id = data.get('book_id')
        chapter_index = data.get('chapter_index')
        mode = data.get('mode', 'chapter')
        language = data.get('language', 'en')
        force = data.get('force', False)
        if (
            scope not in {'book', 'chapter'}
            or not isinstance(book_id, str)
            or not book_id
            or (scope == 'chapter' and (isinstance(chapter_index, bool) or not isinstance(chapter_index, int)))
            or (scope == 'book' and chapter_index is not None)
            or (scope == 'chapter' and mode != 'chapter')
            or (scope == 'book' and mode not in {'spoiler_free', 'read_so_far', 'full_review'})
            or language not in {'en', 'zh-CN'}
            or not isinstance(force, bool)
        ):
            return response(error_payload('invalid_ai_reading_request', 'Invalid AI reading request'), 400)
        if not store.can_read_book(principal.user_id, principal.role, book_id):
            return response(error_payload('forbidden', 'Forbidden'), 403)
        try:
            result = await ai_reading.submit(
                principal,
                ReadingRequest(scope, book_id, chapter_index, mode, language, force),
            )
        except AIReadingError as error:
            return ai_error_response(error)
        return response(result, 200 if result['status'] == 'complete' else 202)

    async def ai_job(request):
        principal = require_principal(request)
        job = store.get_ai_job(request.path_params['job_id'], principal.user_id)
        if job is None:
            return response(error_payload('not_found', 'AI job not found'), 404)
        result = (
            store.get_ai_reading_result(job['result_id'])
            if job.get('result_id') else None
        )
        if result is not None and not store.can_read_book(
            principal.user_id, principal.role, result['book_id']
        ):
            return response(error_payload('forbidden', 'Forbidden'), 403)
        return response({'job': job, 'result': result})

    async def ai_followups(request):
        principal = require_principal(request)
        if request.method == 'GET':
            result_id = request.path_params['result_id']
            result = store.get_ai_reading_result(result_id)
            if result is None:
                return response(error_payload('not_found', 'AI result not found'), 404)
            if not store.can_read_book(principal.user_id, principal.role, result['book_id']):
                return response(error_payload('forbidden', 'Forbidden'), 403)
            return response({'followups': list(store.list_ai_followups(result_id, principal.user_id))})
        data, error = await bounded_public_json_object(request)
        if error:
            return response(error_payload(error, 'Invalid AI follow-up'), 400)
        result_id = data.get('result_id')
        question = data.get('question')
        language = data.get('language', 'en')
        if not isinstance(result_id, str) or not isinstance(question, str) or language not in {'en', 'zh-CN'}:
            return response(error_payload('invalid_ai_followup', 'Invalid AI follow-up'), 400)
        result = store.get_ai_reading_result(result_id)
        if result is None:
            return response(error_payload('not_found', 'AI result not found'), 404)
        if not store.can_read_book(principal.user_id, principal.role, result['book_id']):
            return response(error_payload('forbidden', 'Forbidden'), 403)
        try:
            followup = await ai_reading.follow_up(principal, result_id, question, language)
        except AIReadingError as error:
            return ai_error_response(error)
        return response({'followup': followup}, 202)

    async def filtered_library_metadata(request):
        principal = require_principal(request)
        return response(
            library_metadata(
                store.visible_books(principal), base_directory, state_store=store
            )
        )

    async def library_index(request):
        index_path = os.path.join(base_directory, 'index.html')
        if not os.path.isfile(index_path):
            return response(error_payload('not_found', 'Library index not found'), 404)
        response = FileResponse(index_path, media_type='text/html')
        response.headers['Cache-Control'] = 'no-cache'
        return apply_reader_security_headers(response, index_path)

    async def service_worker_tombstone(request):
        return Response(
            SERVICE_WORKER_TOMBSTONE,
            media_type='text/javascript',
            headers={
                'Cache-Control': 'no-store, no-cache, must-revalidate',
                'Service-Worker-Allowed': '/',
                'X-Content-Type-Options': 'nosniff',
            },
        )

    async def protected_public_file(request):
        try:
            path = normalize_public_path(request.path_params['path'])
        except ValueError:
            return response(error_payload('not_found', 'Not Found'), 404)
        if '/' + path in PUBLIC_LOGIN_ASSETS:
            return FileResponse(
                os.path.join(os.path.dirname(__file__), path),
                media_type='text/css' if path.endswith('.css') else 'text/javascript',
                headers={'Cache-Control': 'no-cache'},
            )
        principal = require_principal(request)
        book_id = extract_book_id_from_public_path(path)
        book_relative_path = None
        if book_id:
            if not store.can_read_book(
                principal.user_id,
                principal.role,
                book_id,
            ):
                return response(error_payload('forbidden', 'Forbidden'), 403)
            if not server_book_output_is_current(base_directory, book_id):
                return response(error_payload('not_found', 'Not Found'), 404)
            book_relative_path = '/'.join(path.split('/')[2:])
            if not server_book_public_path_allowed(book_relative_path):
                return response(error_payload('not_found', 'Not Found'), 404)
        static_response = await public_files.get_response(path, request.scope)
        if book_relative_path and re.fullmatch(
            r'(?:index|chapter_[0-9]+)\.html',
            book_relative_path,
            re.IGNORECASE,
        ):
            apply_reader_security_headers(
                static_response,
                getattr(
                    static_response,
                    'path',
                    os.path.join(base_directory, *path.split('/')),
                ),
            )
        return static_response

    async def health(request):
        payload = {'status': 'ok'}
        payload.update(runtime_status.snapshot())
        return JSONResponse(payload, headers={'Cache-Control': 'no-cache'})

    async def ready(request):
        payload = runtime_status.snapshot()
        return JSONResponse(
            payload,
            status_code=200 if runtime_status.is_ready() else 503,
            headers={'Cache-Control': 'no-cache'},
        )

    async def library_events(request):
        if progress_broker is None:
            return response(error_payload('not_found', 'Not found'), 404)

        async def events():
            subscription = progress_broker.subscribe(asyncio.get_running_loop())
            try:
                while True:
                    try:
                        snapshot = await asyncio.wait_for(
                            subscription.next(),
                            library_event_heartbeat_seconds,
                        )
                    except asyncio.TimeoutError:
                        yield ': heartbeat\n\n'
                    else:
                        payload = json.dumps(
                            snapshot.as_dict(),
                            ensure_ascii=False,
                            separators=(',', ':'),
                        )
                        yield 'event: progress\ndata: ' + payload + '\n\n'
            finally:
                subscription.close()

        return StreamingResponse(
            events(),
            media_type='text/event-stream',
            headers={
                'Cache-Control': 'no-store',
                'X-Accel-Buffering': 'no',
            },
        )

    async def http_exception(request, exc):
        codes = {
            401: 'authentication_required',
            403: 'forbidden',
            404: 'not_found',
        }
        code = codes.get(exc.status_code, 'server_error')
        message = exc.detail if isinstance(exc.detail, str) else 'Internal server error'
        return response(error_payload(code, message), exc.status_code)

    async def server_error(request, exc):
        cache_control = (
            'private, no-cache'
            if request.scope.get(PRINCIPAL_SCOPE_KEY) is not None
            else 'no-store'
        )
        return response(
            error_payload('server_error', 'Internal server error'),
            500,
            cache_control=cache_control,
        )

    def row_data(row):
        data = dict(row)
        for key, target in [('start_meta', 'startMeta'), ('end_meta', 'endMeta')]:
            data[target] = json.loads(data[key]) if data.get(key) else None
        return data

    def book_access_denied(principal, book_id):
        return (
            not isinstance(book_id, str)
            or not book_id
            or not store.can_read_book(
                principal.user_id,
                principal.role,
                book_id,
            )
        )

    def forbidden_book_response():
        return response(error_payload('forbidden', 'Forbidden'), 403)

    async def annotations(request):
        principal = require_principal(request)
        parts = [part for part in request.path_params['path'].split('/') if part]
        if not parts or parts[0] != 'annotations':
            return response(error_payload('not_found', 'Not found'), 404)
        tail = parts[1:]
        if request.method != 'GET' and not runtime_status.is_ready():
            return response(error_payload('not_ready', 'Server is not ready'), 503)
        try:
            if request.method == 'GET':
                if tail[:1] == ['batch']:
                    return response(
                        error_payload('batch_requires_post', 'Batch requires POST'),
                        400,
                    )
                if tail[:1] == ['item'] and len(tail) == 2:
                    row = store.get_annotation(tail[1], user_id=principal.user_id)
                    if row and book_access_denied(principal, row.get('book_hash')):
                        return forbidden_book_response()
                    return (
                        response({'data': row}, 200)
                        if row
                        else response(
                            error_payload(
                                'annotation_not_found',
                                'Annotation not found',
                            ),
                            404,
                        )
                    )
                if len(tail) > 2:
                    return response(error_payload('not_found', 'Not found'), 404)
                if tail and book_access_denied(principal, tail[0]):
                    return forbidden_book_response()
                chapter_index = None
                if len(tail) == 2:
                    try:
                        chapter_index = int(tail[1])
                    except ValueError:
                        return response(
                            error_payload(
                                'invalid_chapter_index',
                                'Invalid chapter index',
                            ),
                            400,
                        )
                rows = store.list_annotations(
                    book_hash=tail[0] if tail else None,
                    chapter_index=chapter_index,
                    user_id=principal.user_id,
                )
                if not tail:
                    rows = [
                        row for row in rows
                        if not book_access_denied(
                            principal,
                            row.get('book_hash'),
                        )
                    ]
                return response({'data': rows})

            if request.method == 'DELETE':
                if len(tail) != 2 or tail[0] != 'item':
                    return response(error_payload('not_found', 'Not found'), 404)
                row = store.get_annotation(tail[1], user_id=principal.user_id)
                if row and book_access_denied(principal, row.get('book_hash')):
                    return forbidden_book_response()
                store.delete_annotation(tail[1], user_id=principal.user_id)
                return response({'message': 'Deleted'})
            try:
                data = await request.json()
            except json.JSONDecodeError:
                return response(error_payload('invalid_json', 'Invalid JSON data'), 400)

            if request.method == 'POST':
                entries = data.get('annotations', []) if tail == ['batch'] else [data]
                if not isinstance(entries, list) or any(
                    not isinstance(entry, dict) for entry in entries
                ):
                    return response(error_payload('invalid_json', 'Invalid JSON data'), 400)
                path_book_id = (
                    tail[0]
                    if tail and tail[0] not in {'batch', 'item'}
                    else None
                )
                if path_book_id and book_access_denied(principal, path_book_id):
                    return forbidden_book_response()
                for entry in entries:
                    entry_book_id = entry.get('book_hash')
                    stored = None
                    if entry.get('id'):
                        stored = store.get_annotation(
                            entry['id'],
                            user_id=principal.user_id,
                        )
                    if stored and book_access_denied(
                        principal,
                        stored.get('book_hash'),
                    ):
                        return forbidden_book_response()
                    if stored and stored.get('book_hash') != entry_book_id:
                        return response(
                            error_payload(
                                'annotation_book_mismatch',
                                'Annotation cannot move between books',
                            ),
                            409,
                        )
                    if (
                        (path_book_id and entry_book_id != path_book_id)
                        or book_access_denied(principal, entry_book_id)
                    ):
                        return forbidden_book_response()
                created = failed = 0
                for entry in entries:
                    try:
                        store.upsert_annotation(
                            entry,
                            user_id=principal.user_id,
                            replace_existing=tail == ['batch'],
                        )
                        created += 1
                    except Exception:
                        failed += 1
                if tail == ['batch']:
                    return response({'created': created, 'failed': failed}, 201)
                if failed:
                    raise RuntimeError('annotation insert failed')
                return response({'data': data}, 201)

            if len(tail) != 2 or tail[0] != 'item':
                return response(error_payload('not_found', 'Not found'), 404)
            annotation_id = tail[1]
            stored = store.get_annotation(
                annotation_id,
                user_id=principal.user_id,
            )
            if stored and book_access_denied(
                principal,
                stored.get('book_hash'),
            ):
                return forbidden_book_response()
            if 'chapter_index' in data and (
                isinstance(data['chapter_index'], bool)
                or not isinstance(data['chapter_index'], int)
                or data['chapter_index'] < 0
            ):
                return response({'message': 'Invalid chapter index'}, 400)
            row = store.update_annotation(
                annotation_id,
                data,
                user_id=principal.user_id,
            )
            return (
                response({'data': row}, 200)
                if row
                else response(
                    error_payload(
                        'annotation_not_found',
                        'Annotation not found',
                    ),
                    404,
                )
            )
        except Exception:
            return response(error_payload('server_error', 'Internal server error'), 500)

    async def sync(request):
        principal = require_principal(request)
        if not runtime_status.is_ready():
            return response(error_payload('not_ready', 'Server is not ready'), 503)
        try:
            data = await request.json()
            version, shelf = data.get('version', 1), data.get('data')
            payload, status = sync_bookshelf(
                database_path(base_directory), principal.user_id,
                version, shelf, store=store,
            )
            if status == 400:
                return response(error_payload('no_sync_data', payload['message']), status)
            return response(payload, status)
        except json.JSONDecodeError: return response(error_payload('invalid_json', 'Invalid JSON data'), 400)
        except Exception: return response(error_payload('server_error', 'Internal server error'), 500)

    def bookshelf_document(user_id):
        row = store.get_bookshelf(user_id)
        if row is None:
            return 0, {"items": [], "groups": {}, "order": []}
        version, serialized = row
        return version, json.loads(serialized)

    async def bookshelf(request):
        principal = require_principal(request)
        user_id = principal.user_id
        try:
            current_version, current_data = bookshelf_document(user_id)
            if request.method == 'GET':
                return response({'version': current_version, 'data': current_data})
            if not runtime_status.is_ready():
                return response(error_payload('not_ready', 'Server is not ready'), 503)
            payload = await request.json()
            proposed_data = payload.get('data') if isinstance(payload, dict) else None
            proposed_version = payload.get('version') if isinstance(payload, dict) else None
            if not isinstance(proposed_data, dict) or not isinstance(proposed_version, int):
                return response(error_payload('no_sync_data', 'A bookshelf document and version are required'), 400)
            if proposed_version != current_version:
                return response(
                    {
                        'code': 'bookshelf_conflict',
                        'message': 'Bookshelf changed on the server',
                        'version': current_version,
                        'data': current_data,
                    },
                    409,
                )
            next_version = current_version + 1
            if current_version == 0:
                store.create_bookshelf(user_id, next_version, proposed_data)
            else:
                store.update_bookshelf(user_id, next_version, proposed_data)
            return response({'version': next_version, 'data': proposed_data})
        except json.JSONDecodeError:
            return response(error_payload('invalid_json', 'Invalid JSON data'), 400)
        except Exception:
            return response(error_payload('server_error', 'Internal server error'), 500)

    async def reading_progress(request):
        try:
            return await reading_progress_response(request)
        except Exception:
            return response(error_payload('server_error', 'Internal server error'), 500)

    async def reading_progress_response(request):
        principal = require_principal(request)
        book_hash = request.path_params['book_hash']

        if book_access_denied(principal, book_hash):
            return forbidden_book_response()

        if request.method != 'GET' and not runtime_status.is_ready():
            return response(error_payload('not_ready', 'Server is not ready'), 503)

        if request.method == 'GET':
            chapter_index = store.get_reading_progress(principal.user_id, book_hash)
            return (
                response({'chapter_index': chapter_index})
                if chapter_index is not None
                else response(
                    error_payload(
                        'reading_progress_not_found',
                        'Reading progress not found',
                    ),
                    404,
                )
            )

        if request.method == 'PUT':
            try:
                data = await request.json()
            except json.JSONDecodeError:
                return response(error_payload('invalid_json', 'Invalid JSON data'), 400)
            chapter_index = data.get('chapter_index') if isinstance(data, dict) else None
            if isinstance(chapter_index, bool) or not isinstance(chapter_index, int) or chapter_index < 0:
                return response(error_payload('invalid_chapter_index', 'Invalid chapter index'), 400)
            store.set_reading_progress(principal.user_id, book_hash, chapter_index)
            return response({'chapter_index': chapter_index})

        store.delete_reading_progress(principal.user_id, book_hash)
        return response({'message': 'Deleted'})

    routes = [
        Route('/setup', setup, methods=['GET', 'POST']),
        Route('/login', login, methods=['GET', 'POST']),
        Route('/logout', logout, methods=['POST']),
        Route('/sw.js', service_worker_tombstone, methods=['GET']),
        Route('/api/identity/link', link_proxy_identity, methods=['POST']),
        Route('/api/session', session, methods=['GET']),
        Route('/api/csrf', csrf, methods=['GET']),
        Route('/api/account/password', change_password, methods=['PUT']),
        Route('/api/account/sessions', list_own_sessions, methods=['GET']),
        Route('/api/account/sessions/{session_id}', revoke_own_session, methods=['DELETE']),
        Route('/api/admin/users', admin_users, methods=['GET', 'POST']),
        Route('/api/admin/users/{username}/password', admin_reset_password, methods=['PUT']),
        Route('/api/admin/users/{username}', admin_user, methods=['PUT']),
        Route(
            '/api/admin/identities',
            admin_identities,
            methods=['GET', 'POST', 'DELETE'],
        ),
        Route('/api/admin/books', admin_books, methods=['GET']),
        Route('/api/admin/books/{book_id}', admin_book, methods=['PUT']),
        Route('/api/admin/ai/settings', admin_ai_settings, methods=['GET', 'PUT']),
        Route('/api/admin/ai/users/{user_id}', admin_ai_user_access, methods=['GET', 'PUT']),
        Route('/api/admin/ai/tags', admin_ai_tags, methods=['GET', 'POST']),
        Route('/api/admin/ai/tags/{tag_id}', admin_ai_tag, methods=['PUT', 'DELETE']),
        Route('/api/admin/books/{book_id}/ai', admin_book_ai, methods=['GET', 'PUT']),
        Route('/api/admin/ai/results', admin_ai_results, methods=['DELETE']),
        Route(
            '/api/admin/books/{book_id}/grants',
            admin_book_grants,
            methods=['PUT'],
        ),
        Route(
            '/api/admin/books/{book_id}/grants/{user_id}',
            admin_book_grant,
            methods=['PUT', 'DELETE'],
        ),
        Route('/', library_index),
        Route('/index.html', library_index),
        Route('/book-metadata.json', filtered_library_metadata, methods=['GET']),
        Route('/api/health', health),
        Route('/api/ready', ready),
        Route('/api/library-events', library_events),
        Route('/api/bookshelf', bookshelf, methods=['GET', 'PUT']),
        Route('/api/library-metadata', filtered_library_metadata, methods=['GET']),
        Route('/api/reading-progress/{book_hash}', reading_progress, methods=['GET', 'PUT', 'DELETE']),
        Route('/api/ai/status', ai_status, methods=['GET']),
        Route('/api/books/{book_id}/metadata', book_effective_metadata, methods=['GET']),
        Route('/api/ai/reading', ai_reading_request, methods=['POST']),
        Route('/api/ai/jobs/{job_id}', ai_job, methods=['GET']),
        Route('/api/ai/followups', ai_followups, methods=['POST']),
        Route('/api/ai/results/{result_id}/followups', ai_followups, methods=['GET']),
        Route('/api/{path:path}', annotations, methods=['GET', 'POST', 'PUT', 'DELETE']),
        Route('/sync', sync, methods=['POST']),
        Route('/{path:path}', protected_public_file, methods=['GET']),
    ]
    app = Starlette(
        routes=routes,
        exception_handlers={
            StarletteHTTPException: http_exception,
            Exception: server_error,
        },
    )

    async def auth_middleware(request, call_next):
        path = request.url.path
        if not store.has_administrator():
            if path in {'/setup', '/sw.js'} or path in PUBLIC_LOGIN_ASSETS:
                return await call_next(request)
            return setup_required_response(request)
        if path == '/sw.js':
            return await call_next(request)
        raw_session = request.cookies.get(SESSION_COOKIE)
        session_principal = auth_service.principal_from_session(raw_session)
        host = request.client.host if request.client is not None else ''
        proxy_identity = auth_service.authenticate_proxy(host, request.headers)
        proxy_principal = None
        if proxy_identity is not None:
            proxy_principal = store.principal_from_identity(
                proxy_identity.issuer,
                proxy_identity.subject,
            )
        principal = proxy_principal or session_principal
        pending_identity = (
            proxy_identity
            if proxy_identity is not None and proxy_principal is None
            else None
        )
        if proxy_principal is not None and proxy_principal != session_principal:
            raw_session = None
        request.scope[PRINCIPAL_SCOPE_KEY] = principal
        request.scope[PENDING_IDENTITY_SCOPE_KEY] = pending_identity
        request.scope[SESSION_TOKEN_SCOPE_KEY] = raw_session
        is_public_auth = route_is_public_auth_endpoint(path)
        if principal is None:
            if is_public_auth:
                return await call_next(request)
            return unauthenticated_response(request)
        if request.method not in SAFE_METHODS:
            if not auth_service.verify_csrf(request, principal):
                denied = response(
                    error_payload('csrf_required', 'Valid CSRF token required'),
                    403,
                    cache_control='no-store',
                )
                denied.headers['Cache-Control'] = 'private, no-cache'
                return denied
        new_proxy_session = None
        if raw_session is None:
            new_proxy_session, _ = auth_service.create_session(
                principal,
                **session_client_metadata(request),
            )
            request.scope[SESSION_TOKEN_SCOPE_KEY] = new_proxy_session
        authorized = await call_next(request)
        if new_proxy_session is not None:
            set_session_cookie(authorized, new_proxy_session)
        authorized.headers['Cache-Control'] = 'private, no-cache'
        return authorized

    app.add_middleware(BaseHTTPMiddleware, dispatch=auth_middleware)
    return app
