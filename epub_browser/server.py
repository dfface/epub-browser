import asyncio
import base64
import hashlib
from collections import OrderedDict
import html
import ipaddress
import json
import logging
import math
import mimetypes
import os
import posixpath
import re
import secrets
import sqlite3

from .i18n_bundles import get_bundle, i18n_core_immutable_url, render_i18n_bootstrap, resolve_request_locale
import time
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qs, quote, unquote, unquote_to_bytes, urlsplit
from zoneinfo import ZoneInfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from anyio import CancelScope, to_thread
from starlette.applications import Starlette
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.gzip import GZipMiddleware
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
from .ai_reading import (
    AIReadingError,
    AIReadingService,
    ReadingRequest,
    _public_ai_job,
    _public_ai_result,
    validate_reading_request,
)
from .asset_publisher import WEB_MANIFEST_SOURCES, PublishedAssets, rewrite_asset_urls
from .dictionary_service import (
    DictionaryService,
    DictionaryServiceError,
    migrate_legacy_dictionary_directory,
)
from .encyclopedia import EncyclopediaError, WikimediaEncyclopedia
from .prompt_templates import template_for
from .state import (
    APPEARANCE_DEFAULTS,
    APPEARANCE_THEMES,
    SetupAlreadyCompleteError,
    StateStore,
    UserDeletionError,
)
from .library_progress import LibraryProgressBroker
from .locales import LOCALE_NATIVE_NAMES, SUPPORTED_LOCALE_SET, normalize_locale
from .oidc import OIDCConfiguration, OIDCError, OIDCService
from .processor import (
    SERVER_OUTPUT_REVISION,
    SERVER_OUTPUT_REVISION_FILE,
    server_book_public_path_allowed,
)
from .pdf_delivery import (
    ByteRange,
    OwnedPDFFileResponse,
    PDFDeliverySpecification,
    PDFValidationError,
    RangeNotSatisfiable,
    if_none_match_matches,
    inline_pdf_disposition,
    parse_single_range,
    prepare_pdf_delivery_async,
)
from .public_api import (
    PUBLIC_API_CONTEXT_KEY,
    PublicAPIContext,
    bounded_public_json_object,
    openapi_document,
    public_api_operations,
    public_api_routes,
)
from .server_api_docs import render_api_docs
from .vocabulary import MASTERY_STATES, vocabulary_page_options
from .server_concurrency import (
    SetupStateMonitor,
    StatKeyedCache,
    run_db,
    run_io,
    run_render,
)
from .server_library import (
    BookCacheUnavailable,
    PDF_METADATA_SCHEMA_VERSION,
    PDF_OUTPUT_REVISION,
    PDF_OUTPUT_REVISION_FILE,
    library_metadata,
)
from .server_pages import ServerPageError, ServerPageRenderer
from .source_format import EPUB_FORMAT, PDF_FORMAT, is_supported_source
from .kindle import KINDLE_WIDGETS, kindle_timezone_offset, kindle_timezones, valid_kindle_memo
from .kindle_calendar import CALENDAR_REFRESH_SECONDS, calendar_url, load_calendar_events
from .book_sort import library_sort, sort_catalog
from .site import LibraryBook, render_kindle_library_page, render_library_shell
from .urls import SiteURLs
from .version import ReleaseLookup, render_footer
from .webhooks import WEBHOOK_EVENT_TYPES, WebhookService


LOGGER = logging.getLogger(__name__)

DATABASE_FILENAME = 'epub-browser.db'
LEGACY_DATABASE_FILENAME = 'annotations.db'
PRINCIPAL_SCOPE_KEY = 'epub_browser.principal'
SESSION_TOKEN_SCOPE_KEY = 'epub_browser.session_token'
SETUP_NONCE_COOKIE = 'epub_browser_setup_nonce'
AUTH_NONCE_COOKIE = 'epub_browser_auth_nonce'
AUTH_NONCE_HEADER = 'X-EPUB-Browser-Auth-Nonce'
OIDC_BROWSER_COOKIE = 'epub_browser_oidc'
SAFE_METHODS = frozenset({'GET', 'HEAD', 'OPTIONS', 'TRACE'})
ADMIN_AI_JOB_STATUSES = frozenset({
    'queued', 'running', 'complete', 'failed', 'interrupted',
})
ADMIN_AI_JOB_MAX_PAGE = 1_000_000
ADMIN_AI_JOB_MAX_PAGE_SIZE = 100
PUBLIC_UNAUTHENTICATED_ENDPOINTS = frozenset({
    '/setup',
    '/login',
    '/logout',
    '/auth/oidc/start',
    '/auth/oidc/callback',
    '/auth/oidc/associate',
    '/sw.js',
    '/openapi.json',
    '/api-docs',
    '/api/health',
    '/api/ready',
    '/api/version',
})
PUBLIC_SESSION_AWARE_ENDPOINTS = frozenset({
    '/setup',
    '/login',
    '/logout',
    '/auth/oidc/start',
    '/auth/oidc/callback',
    '/auth/oidc/associate',
})
PUBLIC_STATELESS_ENDPOINTS = (
    PUBLIC_UNAUTHENTICATED_ENDPOINTS - PUBLIC_SESSION_AWARE_ENDPOINTS
)
PUBLIC_PRE_SETUP_ENDPOINTS = (
    PUBLIC_STATELESS_ENDPOINTS - frozenset({'/api/health', '/api/ready'})
) | frozenset({'/setup'})
PUBLIC_UNAUTHENTICATED_ASSETS = frozenset({
    '/assets/account.css',
    '/assets/api-docs.css',
    '/assets/api-docs.js',
    '/assets/auth.js',
    '/assets/favicon.png',
    '/assets/i18n/i18n-core.js',
    '/assets/logo-mark-color.png',
    '/assets/theme-bootstrap.js',
    '/assets/theme.css',
    '/assets/version-check.js',
})
PUBLIC_UNAUTHENTICATED_ASSET_NAMES = frozenset(
    path.removeprefix('/assets/') for path in PUBLIC_UNAUTHENTICATED_ASSETS
)
AUTH_NONCE_COOKIE_LIMIT = 8
AUTH_NONCE_VALUE_PATTERN = re.compile(r'[A-Za-z0-9_-]{32,128}')
PUBLIC_WEB_MANIFESTS = frozenset(
    f'/assets/{name}' for name in WEB_MANIFEST_SOURCES
)
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
    'zh-TW': {
        'page_title': '設定 · EPUB Browser',
        'title': '建立超級使用者帳戶',
        'description': '首次存取 Web 介面時，系統會提示你建立一個超級使用者帳戶。',
        'username': '使用者名稱',
        'password': '密碼',
        'password_confirmation': '確認密碼',
        'submit': '建立超級使用者',
        'language': '語言',
        'invalid': '請輸入使用者名稱和密碼。',
        'password_mismatch': '密碼與確認密碼不一致。',
        'username_unavailable': '此使用者名稱無法使用。',
    },
    'ko': {
        'page_title': '설정 · EPUB Browser',
        'title': '슈퍼유저 계정 만들기',
        'description': '웹 인터페이스에 처음 접속하면 슈퍼유저 계정을 만들라는 안내가 표시됩니다.',
        'username': '사용자 이름',
        'password': '비밀번호',
        'password_confirmation': '비밀번호 확인',
        'submit': '슈퍼유저 만들기',
        'language': '언어',
        'invalid': '사용자 이름과 비밀번호를 입력하세요.',
        'password_mismatch': '비밀번호가 서로 일치하지 않습니다.',
        'username_unavailable': '사용할 수 없는 사용자 이름입니다.',
    },
    'ja': {
        'page_title': 'セットアップ · EPUB Browser',
        'title': 'スーパーユーザーアカウントを作成',
        'description': 'Web インターフェースへ初めてアクセスすると、スーパーユーザーアカウントの作成を求められます。',
        'username': 'ユーザー名',
        'password': 'パスワード',
        'password_confirmation': 'パスワードの確認',
        'submit': 'スーパーユーザーを作成',
        'language': '言語',
        'invalid': 'ユーザー名とパスワードを入力してください。',
        'password_mismatch': 'パスワードが一致しません。',
        'username_unavailable': 'このユーザー名は使用できません。',
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
        'login_throttled': 'Too many sign-in attempts. Try again in {minutes} minutes.',
        'language': 'Language',
    },
    'zh-CN': {
        'page_title': '登录 · EPUB Browser',
        'sign_in': '登录',
        'description': '登录后继续进入你的个人书库。',
        'username': '用户名',
        'password': '密码',
        'invalid_credentials': '用户名或密码不正确。',
        'login_throttled': '登录尝试次数过多，请在 {minutes} 分钟后重试。',
        'language': '语言',
    },
    'zh-TW': {
        'page_title': '登入 · EPUB Browser',
        'sign_in': '登入',
        'description': '登入以繼續前往你的個人書庫。',
        'username': '使用者名稱',
        'password': '密碼',
        'invalid_credentials': '使用者名稱或密碼不正確。',
        'login_throttled': '登入嘗試次數過多，請在 {minutes} 分鐘後再試。',
        'language': '語言',
    },
    'ko': {
        'page_title': '로그인 · EPUB Browser',
        'sign_in': '로그인',
        'description': '개인 라이브러리를 계속 이용하려면 로그인하세요.',
        'username': '사용자 이름',
        'password': '비밀번호',
        'invalid_credentials': '사용자 이름 또는 비밀번호가 올바르지 않습니다.',
        'login_throttled': '로그인 시도가 너무 많습니다. {minutes}분 후 다시 시도하세요.',
        'language': '언어',
    },
    'ja': {
        'page_title': 'ログイン · EPUB Browser',
        'sign_in': 'ログイン',
        'description': '個人ライブラリを引き続き利用するにはログインしてください。',
        'username': 'ユーザー名',
        'password': 'パスワード',
        'invalid_credentials': 'ユーザー名またはパスワードが正しくありません。',
        'login_throttled': 'ログイン試行回数が多すぎます。{minutes} 分後にもう一度お試しください。',
        'language': '言語',
    },
}
OIDC_COPY = {
    'en': {
        'error_title': 'Sign-in could not be completed',
        'error_body': 'Return to sign in and try again. If the problem continues, contact your administrator.',
        'back': 'Return to sign in',
        'associate_title': 'Connect your existing account',
        'associate_body': 'Enter your existing EPUB Browser username and password once to connect this identity.',
        'submit': 'Connect and sign in',
    },
    'zh-CN': {
        'error_title': '无法完成登录',
        'error_body': '请返回登录页重试。如果问题持续存在，请联系管理员。',
        'back': '返回登录',
        'associate_title': '绑定现有账户',
        'associate_body': '请输入一次现有 EPUB Browser 用户名和密码，以绑定此身份。',
        'submit': '绑定并登录',
    },
    'zh-TW': {
        'error_title': '無法完成登入',
        'error_body': '請返回登入頁重試。如果問題持續發生，請聯絡管理員。',
        'back': '返回登入',
        'associate_title': '連結現有帳戶',
        'associate_body': '請輸入一次現有 EPUB Browser 使用者名稱和密碼，以連結此身分。',
        'submit': '連結並登入',
    },
    'ko': {
        'error_title': '로그인을 완료할 수 없습니다',
        'error_body': '로그인 화면으로 돌아가 다시 시도하세요. 문제가 계속되면 관리자에게 문의하세요.',
        'back': '로그인으로 돌아가기',
        'associate_title': '기존 계정 연결',
        'associate_body': '이 ID를 연결하려면 기존 EPUB Browser 사용자 이름과 비밀번호를 한 번 입력하세요.',
        'submit': '연결하고 로그인',
    },
    'ja': {
        'error_title': 'ログインを完了できませんでした',
        'error_body': 'ログイン画面に戻って再試行してください。問題が続く場合は管理者に連絡してください。',
        'back': 'ログインに戻る',
        'associate_title': '既存のアカウントを接続',
        'associate_body': 'この ID を接続するため、既存の EPUB Browser のユーザー名とパスワードを一度入力してください。',
        'submit': '接続してログイン',
    },
}

def locale_options(locale):
    return '\n'.join(
        '<option value="{}"{} data-i18n="locale.name.{}">{}</option>'.format(
            code,
            ' selected' if code == locale else '',
            code,
            name,
        )
        for code, name in LOCALE_NATIVE_NAMES.items()
    )

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


def reader_content_security_policy(markup, inline_scripts=False):
    if isinstance(markup, bytes):
        markup = markup.decode('utf-8', errors='replace')
    if inline_scripts:
        # Legacy e-ink Kindles ship a WebKit that does not understand CSP hash
        # sources ('sha256-...'); it then rejects every inline <script>, killing
        # the Kindle minimal UI's i18n, theme and font controls. These pages are
        # a closed, already-sanitized read surface, so allowing inline scripts
        # is safe.
        script_sources = "'self' 'unsafe-inline'"
    else:
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
        "object-src 'none'; frame-src 'none'; "
        "base-uri 'none'; form-action 'self'"
    ).format(script_sources)


def error_payload(code, message):
    return {'code': code, 'message': message}


def _safe_source_filename(raw):
    """Reduce a client-supplied filename to a safe, non-hidden base name.

    Strips any directory components (path separators) and characters that are
    unsafe across common filesystems, but preserves Unicode letters and digits
    so international names (e.g. Chinese or accented) survive intact.  Hidden
    or empty names are refused so uploads can only land in the managed sources
    directory under their bare name.
    """
    if not raw:
        return ""
    name = raw.split("/")[-1].split("\\")[-1]
    # Keep Unicode word characters plus "." and "-" so international names are
    # retained; replace everything else (separators, control characters, the
    # reserved Windows characters, etc.) with an underscore.
    name = re.sub(r"[^\w.-]", "_", name)
    name = re.sub(r"_+", "_", name)
    if not re.search(r"[^\W_]", name) or name.startswith(".") or name in (".", ".."):
        return ""
    if len(name) > 255:
        stem, dot, suffix = name.rpartition(".")
        if dot:
            name = stem[:250] + dot + suffix
        else:
            name = name[:255]
    return name


def _is_valid_book_magic(head, filename):
    """Best-effort content sniff for EPUB (ZIP) and PDF uploads."""
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf":
        return head[:4] == b"%PDF"
    if suffix == ".epub":
        return head[:4] in (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")
    return False


def route_is_public_unauthenticated(path):
    return (
        path in PUBLIC_UNAUTHENTICATED_ENDPOINTS
        or path in PUBLIC_UNAUTHENTICATED_ASSETS
        or path in PUBLIC_WEB_MANIFESTS
        or path == '/assets/i18n-manifest.json'
    )


def normalize_login_locale(value, accept_language=''):
    candidate = value
    if not candidate:
        candidate = str(accept_language or '').split(',', 1)[0].split(';', 1)[0].strip()
    return normalize_locale(candidate, 'en')


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


# Bounds for the "continue reading" rail.  The rail is a short overview, so the
# server never has to serialise a whole reading history for it.
RECENT_READING_DEFAULT_LIMIT = 10
RECENT_READING_MAX_LIMIT = 24


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
        path in {'/', '/index.html', '/kindle', '/kindle/screensaver'}
        or path.endswith('.html')
        or 'text/html' in request.headers.get('accept', '').lower()
    )


def unauthenticated_response(request):
    path = request.url.path
    if (
        path.startswith('/book/')
        and path.endswith('.html')
        and _request_expects_html(request)
    ):
        target = quote(_request_relative_path(request), safe='')
        return RedirectResponse(
            '/login?next=' + target,
            status_code=303,
            headers={'Cache-Control': 'no-store'},
        )
    if path == '/book' or path.startswith('/book/'):
        return JSONResponse(
            error_payload('forbidden', 'Forbidden'),
            status_code=403,
            headers={'Cache-Control': 'no-store'},
        )
    if path == '/sync' or path.startswith('/api/') or path == '/reading-insights':
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
        return 'private, max-age=31536000, immutable'
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


def server_book_output_is_current(
    base_directory,
    book_id,
    source_format=EPUB_FORMAT,
):
    if source_format == PDF_FORMAT:
        revision_file = PDF_OUTPUT_REVISION_FILE
        expected_revision = PDF_OUTPUT_REVISION
    else:
        revision_file = SERVER_OUTPUT_REVISION_FILE
        expected_revision = SERVER_OUTPUT_REVISION
    marker = os.path.join(
        base_directory,
        'book',
        book_id,
        revision_file,
    )
    try:
        with open(marker, encoding='utf-8') as revision_file:
            revision = revision_file.read().strip()
    except OSError:
        return False
    return revision == expected_revision


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
        # ``mimetypes`` does not consistently recognise the JPEG JFIF suffix
        # across platforms, even though EPUB manifests commonly use it.
        if Path(full_path).suffix.casefold() == '.jfif':
            response.headers['Content-Type'] = 'image/jpeg'
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
    oidc_service: Optional[OIDCService] = None,
    release_lookup: Optional[ReleaseLookup] = None,
    log_errors: bool = False,
    server_directory=None,
    kindle: bool = False,
    library_manager=None,
):
    """Create the ASGI module used by Uvicorn to serve an EPUB library."""
    base_directory = os.path.abspath(public_dir)
    if state_store is None or auth_service is None:
        raise RuntimeError('An initialized StateStore and AuthService are required')
    store = state_store
    oidc_service = oidc_service or OIDCService(store)
    runtime_status = status or _CompatibilityRuntimeStatus()
    public_files = CachedStaticFiles(directory=base_directory, html=False)
    release_lookup = release_lookup or ReleaseLookup()
    # Dictionary databases are runtime user data; they must live under the
    # server directory, not inside the published cache tree.  Migrate any
    # databases earlier builds wrote under ``cache/public/data``.
    data_directory = Path(server_directory) if server_directory else Path(base_directory)
    if library_manager is not None:
        upload_sources_dir = Path(library_manager.managed_sources_dir)
    else:
        upload_sources_dir = data_directory / "data" / "sources"
        upload_sources_dir.mkdir(parents=True, exist_ok=True)
    migrate_legacy_dictionary_directory(base_directory, data_directory)
    book_cache = library_manager.book_cache if library_manager is not None else None
    ai_reading = AIReadingService(store, base_directory, book_cache=book_cache)

    async def pin_book_cache(request, book_id, *, read=False, restore=True):
        if library_manager is None:
            return
        with CancelScope(shield=True):
            await to_thread.run_sync(
                lambda: library_manager.acquire_book_cache(book_id, read=read, restore=restore)
            )
            request.scope['epub_browser.book_cache_pin'] = book_id

    class BookCacheLeaseMiddleware:
        """Keep static resources pinned until Starlette finishes streaming them."""

        def __init__(self, app):
            self.app = app

        async def __call__(self, scope, receive, send):
            try:
                await self.app(scope, receive, send)
            finally:
                book_id = scope.pop('epub_browser.book_cache_pin', None)
                if book_id is not None:
                    with CancelScope(shield=True):
                        await to_thread.run_sync(library_manager.release_book_cache, book_id)

    webhook_service = WebhookService(store)
    dictionary_service = DictionaryService(store, data_directory)
    encyclopedia = WikimediaEncyclopedia()
    heartbeat_attempts = {}
    store.requeue_running_ai_jobs()
    store.requeue_running_ai_followups()
    store.requeue_running_ai_book_chat_turns()

    def response(data, status=200, cache_control='no-cache', headers=None):
        response_headers = {'Cache-Control': cache_control}
        if headers:
            response_headers.update(headers)
        return JSONResponse(
            data,
            status_code=status,
            headers=response_headers,
        )

    asset_manifest_path = Path(base_directory, 'assets', 'asset-manifest.json')

    def _load_published_assets():
        manifest = json.loads(asset_manifest_path.read_text(encoding='utf-8'))
        if not isinstance(manifest, dict) or not all(
            isinstance(key, str) and isinstance(value, str)
            for key, value in manifest.items()
        ):
            raise ValueError('Invalid asset manifest')
        return PublishedAssets(manifest)

    asset_manifest_cache = StatKeyedCache(asset_manifest_path, _load_published_assets)
    # One startup probe; afterwards the middleware and the background task keep
    # the cached value fresh without touching SQLite on every request.
    setup_state = SetupStateMonitor(
        store.has_administrator,
        initial_ready=store.has_administrator(),
    )

    def current_published_assets():
        return asset_manifest_cache.get()

    def current_asset_url(logical_name):
        try:
            return current_published_assets().url_for(logical_name)
        except (KeyError, OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
            return '/assets/' + logical_name

    def is_public_unauthenticated_asset(path):
        if path == '/assets/i18n-manifest.json':
            return True
        # i18n locale packs and the runtime loader are non-sensitive UI text and
        # are required for the localized login/setup surface, so they must stay
        # reachable (including before first-run setup) even when the asset
        # publisher has not run yet.
        if path.startswith('/assets/i18n/') or path.startswith('/assets/immutable/i18n/'):
            return True
        if path in PUBLIC_UNAUTHENTICATED_ASSETS:
            return True
        try:
            published = current_published_assets()
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
            return False
        for logical_name in PUBLIC_UNAUTHENTICATED_ASSET_NAMES:
            published_path = published.assets.get(logical_name)
            if (
                isinstance(published_path, str)
                and published_path.startswith('/assets/immutable/')
                and path == published_path
            ):
                return True
        return False

    def heartbeat_rate_limited(user_id, client_id):
        """Permit the normal 15-second cadence and a few transient retries."""
        now = time.monotonic()
        key = (user_id, client_id)
        attempts = [value for value in heartbeat_attempts.get(key, ()) if now - value < 60]
        if len(attempts) >= 12:
            heartbeat_attempts[key] = attempts
            return True
        attempts.append(now)
        heartbeat_attempts[key] = attempts
        return False

    def apply_reader_security_headers(
        target_response, file_path=None, markup=None, inline_scripts=False
    ):
        if markup is None:
            try:
                markup = Path(file_path).read_text(encoding='utf-8')
            except (OSError, UnicodeDecodeError, TypeError):
                return target_response
        target_response.headers[
            'Content-Security-Policy'
        ] = reader_content_security_policy(markup, inline_scripts=inline_scripts)
        target_response.headers['X-Content-Type-Options'] = 'nosniff'
        return target_response

    async def apply_security_headers(
        target_response, file_path=None, markup=None, inline_scripts=False
    ):
        """Apply CSP scanning off the event loop; reading markup may hit disk."""
        return await run_render(
            apply_reader_security_headers,
            target_response,
            file_path=file_path,
            markup=markup,
            inline_scripts=inline_scripts,
        )

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

    def auth_nonce_cookie_values(raw_value):
        if not isinstance(raw_value, str):
            return ()
        return tuple(
            value
            for value in raw_value.split('.')[-AUTH_NONCE_COOKIE_LIMIT:]
            if AUTH_NONCE_VALUE_PATTERN.fullmatch(value)
        )

    def set_auth_nonce_cookie(target_response, nonce, existing_value=None):
        values = [
            value
            for value in auth_nonce_cookie_values(existing_value)
            if not secrets.compare_digest(value, nonce)
        ]
        values.append(nonce)
        target_response.set_cookie(
            AUTH_NONCE_COOKIE,
            '.'.join(values[-AUTH_NONCE_COOKIE_LIMIT:]),
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

    def set_oidc_browser_cookie(target_response, browser_token):
        target_response.set_cookie(
            OIDC_BROWSER_COOKIE,
            browser_token,
            max_age=600,
            path='/auth/oidc',
            secure=auth_service.config.cookie_secure,
            httponly=True,
            samesite='lax',
        )

    def delete_oidc_browser_cookie(target_response):
        target_response.delete_cookie(
            OIDC_BROWSER_COOKIE,
            path='/auth/oidc',
            secure=auth_service.config.cookie_secure,
            httponly=True,
            samesite='lax',
        )

    async def json_object(request):
        try:
            data = await request.json()
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None
        return data if isinstance(data, dict) else None

    async def bounded_unique_json_object(request, maximum_size=None):
        content_type = request.headers.get('content-type', '').split(';', 1)[0]
        if content_type.strip().casefold() != 'application/json':
            return None
        content_length = request.headers.get('content-length')
        if content_length:
            try:
                if int(content_length) < 0 or (
                    maximum_size is not None and int(content_length) > maximum_size
                ):
                    return None
            except ValueError:
                return None
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if maximum_size is not None and len(body) > maximum_size:
                return None

        class DuplicateKeyError(ValueError):
            pass

        def unique_object(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise DuplicateKeyError
                result[key] = value
            return result

        try:
            data = json.loads(
                bytes(body).decode('utf-8'),
                object_pairs_hook=unique_object,
            )
        except (
            UnicodeDecodeError,
            json.JSONDecodeError,
            DuplicateKeyError,
            RecursionError,
        ):
            return None
        return data if isinstance(data, dict) else None

    def oidc_identity_data(user, identity, all_identities, settings):
        password_login = bool(user.password_hash) and (
            user.role == 'admin'
            or not settings.enabled
            or settings.allow_member_password_login
        )
        can_unlink = password_login or len(all_identities) > 1
        return {
            'issuer': identity.issuer,
            'provider_name': (
                settings.provider_name
                if identity.issuer == settings.issuer_url and settings.provider_name
                else identity.issuer
            ),
            'username': identity.username_claim,
            'display_name': identity.display_name,
            'email': identity.email,
            'created_at': identity.created_at,
            'last_login_at': identity.last_login_at,
            'can_unlink': can_unlink,
        }

    def user_oidc_identities(user):
        identities = store.list_oidc_identities(user.user_id)
        settings = store.get_oidc_settings()
        return [
            oidc_identity_data(user, identity, identities, settings)
            for identity in identities
        ]

    def user_data(user):
        payload = {
            'id': user.user_id,
            'username': user.username,
            'role': user.role,
            'enabled': user.enabled,
            'oidc_identities': user_oidc_identities(user),
        }
        if user.role == 'member':
            payload['ai_access'] = store.get_ai_user_access(user.user_id)
        return payload

    def oidc_settings_data(settings):
        return {
            'enabled': settings.enabled,
            'provider_name': settings.provider_name,
            'issuer_url': settings.issuer_url,
            'client_id': settings.client_id,
            'redirect_uri': settings.redirect_uri,
            'scopes': list(settings.scopes),
            'username_claim': settings.username_claim,
            'auto_create_users': settings.auto_create_users,
            'allow_member_password_login': settings.allow_member_password_login,
            'config_revision': settings.config_revision,
            'client_secret_configured': settings.client_secret_configured,
            'updated_at': settings.updated_at,
        }

    def admin_book_data(book):
        metadata = store.managed_book_metadata(book.book_id)
        tags = list(store.book_ai_tags(book.book_id))
        return {
            'id': book.book_id,
            'title': metadata.get('title') or 'EPUB Book',
            'authors': list(metadata.get('authors') or ()),
            'tags': tags,
            'epub_tags': [],
            'visibility': book.visibility,
            'grants': list(store.book_grants(book.book_id)),
            'ai_profile': store.get_book_ai_profile(book.book_id),
            'ai_tags': tags,
            'effective_tags': [tag['name'] for tag in tags],
        }

    def admin_book_summary_data(book):
        payload = dict(book)
        payload['authors'] = list(book['authors'])
        payload['tags'] = [dict(tag) for tag in book['tags']]
        payload['epub_tags'] = list(book['epub_tags'])
        payload['ai_tags'] = [dict(tag) for tag in book['ai_tags']]
        return payload

    def admin_book_detail_data(book):
        payload = admin_book_summary_data(book)
        payload['grants'] = list(book['grants'])
        payload['effective_tags'] = list(book['effective_tags'])
        return payload

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
        return trusted_client_address(request) or 'unknown'

    def trusted_client_address(request):
        """Use forwarded client IPs only when the direct peer is trusted.

        Walk X-Forwarded-For right-to-left so a chain of configured proxies is
        skipped and the first non-proxy address is retained as the client.
        Malformed forwarding data is ignored in favor of the direct peer.
        """
        direct_address = request.client.host if request.client is not None else None
        if (
            not isinstance(direct_address, str)
            or not auth_service.config.is_trusted_proxy(direct_address)
        ):
            return direct_address
        forwarded = request.headers.get('x-forwarded-for')
        if not isinstance(forwarded, str) or not forwarded.strip():
            return direct_address
        candidates = [part.strip() for part in forwarded.split(',')]
        if not candidates or any(not candidate for candidate in candidates):
            return direct_address
        for candidate in reversed(candidates):
            try:
                address = str(ipaddress.ip_address(candidate.strip('[]')))
            except ValueError:
                return direct_address
            if not auth_service.config.is_trusted_proxy(address):
                return address
        return direct_address

    def session_client_metadata(request):
        return {
            'client_address': trusted_client_address(request),
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
        supplied_nonce = request.headers.get(AUTH_NONCE_HEADER)
        if (
            not isinstance(supplied_nonce, str)
            or not supplied_nonce
        ):
            return False
        try:
            return any(
                secrets.compare_digest(cookie_nonce, supplied_nonce)
                for cookie_nonce in auth_nonce_cookie_values(
                    request.cookies.get(AUTH_NONCE_COOKIE)
                )
            )
        except TypeError:
            return False

    def authenticated_login_retry(request):
        return (
            request.method == 'POST'
            and request.url.path == '/login'
            and bool(request.headers.get(AUTH_NONCE_HEADER))
            and valid_same_origin_request_source(request)
        )

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

    def auth_brand_markup():
        return (
            '<div class="auth-brand">'
            '<img class="auth-brand-mark" src="/assets/logo-mark-color.png" '
            'width="32" height="32" '
            'alt="" aria-hidden="true"><span>EPUB Browser</span></div>'
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
        copy = SETUP_COPY.get(locale, SETUP_COPY['en'])
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
        language_options = locale_options(locale)
        footer_markup = render_footer(datetime.now().year, release_api_url='/api/version')
        brand_markup = auth_brand_markup()
        markup = f'''<!doctype html><html lang="{locale}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light dark">
<title data-i18n="account.setupPageTitle">{copy['page_title']}</title>
<link rel="stylesheet" href="/assets/theme.css">
<link rel="stylesheet" href="/assets/account.css">
<script src="/assets/theme-bootstrap.js"></script>
<script>window.EpubBrowserBasePath="/";window.EpubBrowserDisableManifest=true;</script>
{render_i18n_bootstrap(locale, locale if locale_explicit else None, core_url=i18n_core_immutable_url())}
<script src="/assets/version-check.js" defer></script>
</head><body class="auth-page"><main class="auth-shell"><div class="auth-stack"><section class="auth-card setup-card">
<header class="auth-card-header">{brand_markup}
<label class="auth-language setup-language"><span class="auth-language-label" data-i18n="common.language">{copy['language']}</span>
<select id="setupLocaleSelect" aria-label="{copy['language']}" data-i18n-aria-label="common.language">
{language_options}
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
            if await run_db(store.has_administrator):
                setup_state.mark_complete()
                return RedirectResponse(
                    '/' if request.scope.get(PRINCIPAL_SCOPE_KEY) is not None else '/login',
                    status_code=303,
                    headers={'Cache-Control': 'no-store'},
                )
            return await run_render(
                setup_form,
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
        if await run_db(store.has_administrator):
            setup_state.mark_complete()
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
            return await run_render(
                setup_form,
                error='invalid',
                status_code=400,
                locale=submitted_locale,
                locale_explicit=True,
            )
        if password != confirmation:
            return await run_render(
                setup_form,
                error='password_mismatch',
                status_code=400,
                locale=submitted_locale,
                locale_explicit=True,
            )
        try:
            raw_session, _ = await run_db(
                auth_service.complete_setup,
                username,
                password,
                **session_client_metadata(request),
            )
            setup_state.mark_complete()
        except SetupAlreadyCompleteError:
            completed = RedirectResponse(
                '/login',
                status_code=303,
                headers={'Cache-Control': 'no-store'},
            )
            delete_setup_nonce_cookie(completed)
            return completed
        except sqlite3.IntegrityError:
            return await run_render(
                setup_form,
                error='username_unavailable',
                status_code=409,
                locale=submitted_locale,
                locale_explicit=True,
            )
        except ValueError:
            return await run_render(
                setup_form,
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
        existing_auth_nonce_cookie=None,
    ):
        safe_next = html.escape(_safe_relative_path(next_path), quote=True)
        locale = normalize_login_locale(locale)
        nonce = secrets.token_urlsafe(32)
        copy = LOGIN_COPY.get(locale, LOGIN_COPY['en'])
        error_markup = (
            '<p class="auth-alert" id="loginError" role="alert" data-i18n="account.error.invalid_credentials">'
            + copy['invalid_credentials']
            + '</p>'
            if error
            else '<p class="auth-alert" id="loginError" role="alert" data-i18n="account.error.invalid_credentials" hidden>'
            + copy['invalid_credentials']
            + '</p>'
        )
        language_options = locale_options(locale)
        footer_markup = render_footer(datetime.now().year, release_api_url='/api/version')
        brand_markup = auth_brand_markup()
        favicon_url = html.escape(current_asset_url('favicon.png'), quote=True)
        oidc_settings = store.get_oidc_settings()
        oidc_markup = ''
        if oidc_settings.enabled:
            provider_name = html.escape(oidc_settings.provider_name, quote=True)
            provider_params = html.escape(
                json.dumps(
                    {'provider': oidc_settings.provider_name},
                    ensure_ascii=False,
                ),
                quote=True,
            )
            oidc_href = '/auth/oidc/start?next=' + quote(
                _safe_relative_path(next_path),
                safe='',
            )
            oidc_markup = f'''<div class="auth-divider" role="separator"><span data-i18n="account.oidc.or">or</span></div>
<a class="auth-provider-button" id="oidcLoginAction" href="{oidc_href}">
<i class="fas fa-arrow-right-to-bracket" aria-hidden="true"></i>
<span data-i18n="account.oidc.continueWith" data-i18n-params="{provider_params}" data-i18n-strong-param="provider">Continue with <strong>{provider_name}</strong></span>
</a>'''
        markup = f'''<!doctype html><html lang="{locale}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light dark">
<meta name="epub-browser-auth-nonce" content="{nonce}">
<title data-i18n="account.loginPageTitle">{copy['page_title']}</title>
<link rel="icon" type="image/png" href="{favicon_url}">
<link rel="stylesheet" href="/assets/theme.css">
<link rel="stylesheet" href="/assets/account.css">
<script src="/assets/theme-bootstrap.js"></script>
<script>window.EpubBrowserBasePath="/";window.EpubBrowserDisableManifest=true;</script>
{render_i18n_bootstrap(locale, locale if locale_explicit else None, core_url=i18n_core_immutable_url())}
<script src="/assets/version-check.js" defer></script>
</head><body class="auth-page"><main class="auth-shell"><div class="auth-stack"><section class="auth-card login-card">
<header class="auth-card-header">{brand_markup}
<label class="auth-language login-language"><span class="auth-language-label" data-i18n="common.language">{copy['language']}</span>
<select id="loginLocaleSelect" aria-label="{copy['language']}" data-i18n-aria-label="common.language">
{language_options}
</select></label></header>
<div class="auth-intro"><h1 data-i18n="account.signIn">{copy['sign_in']}</h1>
<p class="auth-description" data-i18n="account.loginDescription">{copy['description']}</p></div>
<form class="auth-form" id="loginForm" method="post" action="/login">
<input type="hidden" name="auth_nonce" value="{nonce}">
<input type="hidden" name="next" value="{safe_next}">
<input type="hidden" name="locale" value="{locale}">
{error_markup}
<label class="auth-field"><span data-i18n="account.username">{copy['username']}</span><input name="username" autocomplete="username" required></label>
<label class="auth-field"><span data-i18n="account.password">{copy['password']}</span><input name="password" type="password" autocomplete="current-password" required></label>
<button class="auth-primary-button" type="submit" data-i18n="account.signIn">{copy['sign_in']}</button>
</form>{oidc_markup}</section>{footer_markup}</div></main>
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
var loginSubmit=loginForm&&loginForm.querySelector('button[type="submit"]');
var loginPending=false;
function setLoginBusy(busy){{
loginPending=busy;
if(loginSubmit){{loginSubmit.disabled=busy;loginSubmit.setAttribute('aria-busy',String(busy));}}
}}
function setLoginError(visible,key,params,invalidCredentials){{
if(loginError&&visible&&key){{
loginError.setAttribute('data-i18n',key);
loginError.setAttribute('data-i18n-params',JSON.stringify(params||{{}}));
if(i18n&&i18n.t)loginError.textContent=i18n.t(key,params||{{}});
}}
if(loginError)loginError.hidden=!visible;
if(loginForm)Array.prototype.forEach.call(loginForm.querySelectorAll('input[name="username"],input[name="password"]'),function(field){{
if(visible&&invalidCredentials)field.setAttribute('aria-invalid','true');else field.removeAttribute('aria-invalid');
}});
}}
if(loginForm)loginForm.addEventListener('submit',function(event){{
if(!window.fetch)return; /* legacy Kindle WebKit: plain form POST fallback */
event.preventDefault();
if(loginPending)return;
setLoginBusy(true);
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
if(!response.ok){{
setLoginBusy(false);
var retryAfter=Number(payload.retry_after_seconds||0);
var errorKey=payload.code==='login_throttled'?'account.error.login_throttled':
payload.code==='invalid_credentials'?'account.error.invalid_credentials':
(payload.code==='invalid_auth_request'||payload.code==='csrf_required')?'account.error.csrf_required':'account.error.unknown';
setLoginError(true,errorKey,{{count:Math.max(1,Math.ceil(retryAfter/60))}},payload.code==='invalid_credentials');return;
}}
window.location.assign(payload.redirect||'/');
}});
}}).catch(function(){{setLoginBusy(false);setLoginError(true,'account.error.network');}});
}});
}}());</script></body></html>'''
        page = HTMLResponse(
            markup,
            status_code=status_code,
            headers={'Cache-Control': 'no-store'},
        )
        set_auth_nonce_cookie(page, nonce, existing_auth_nonce_cookie)
        return page

    def oidc_error_page(request, *, status_code=400):
        locale = normalize_login_locale(
            request.query_params.get('lang'),
            request.headers.get('accept-language', ''),
        )
        copy = OIDC_COPY.get(locale, OIDC_COPY['en'])
        markup = f'''<!doctype html><html lang="{locale}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light dark">
<title data-i18n="account.oidc.errorTitle">{html.escape(copy['error_title'])} · EPUB Browser</title>
<link rel="stylesheet" href="/assets/theme.css">
<link rel="stylesheet" href="/assets/account.css">
<script src="/assets/theme-bootstrap.js"></script>
<script>window.EpubBrowserBasePath="/";window.EpubBrowserDisableManifest=true;</script>
{render_i18n_bootstrap(locale, None, core_url=i18n_core_immutable_url())}</head>
<body class="auth-page"><main class="auth-shell"><div class="auth-stack"><section class="auth-card login-card">
<header class="auth-card-header">{auth_brand_markup()}</header>
<div class="auth-intro">
<h1 data-i18n="account.oidc.errorTitle">{html.escape(copy['error_title'])}</h1>
<p class="auth-description" data-i18n="account.oidc.errorBody">{html.escape(copy['error_body'])}</p></div>
<div class="auth-form"><a class="auth-primary-button" href="/login" data-i18n="account.oidc.backToLogin">{html.escape(copy['back'])}</a></div>
</section></div></main></body></html>'''
        return HTMLResponse(
            markup,
            status_code=status_code,
            headers={'Cache-Control': 'no-store'},
        )

    def oidc_association_form(
        request,
        association_token,
        *,
        error=False,
        status_code=200,
    ):
        locale = normalize_login_locale(
            request.query_params.get('lang'),
            request.headers.get('accept-language', ''),
        )
        copy = OIDC_COPY.get(locale, OIDC_COPY['en'])
        login_copy = LOGIN_COPY.get(locale, LOGIN_COPY['en'])
        nonce = secrets.token_urlsafe(32)
        error_markup = (
            '<p class="auth-alert" role="alert" '
            'data-i18n="account.error.invalid_credentials">{}</p>'.format(
                html.escape(login_copy['invalid_credentials'])
            )
            if error else ''
        )
        markup = f'''<!doctype html><html lang="{locale}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light dark">
<title data-i18n="account.oidc.associateTitle">{html.escape(copy['associate_title'])} · EPUB Browser</title>
<link rel="stylesheet" href="/assets/theme.css">
<link rel="stylesheet" href="/assets/account.css">
<script src="/assets/theme-bootstrap.js"></script>
<script>window.EpubBrowserBasePath="/";window.EpubBrowserDisableManifest=true;</script>
{render_i18n_bootstrap(locale, None, core_url=i18n_core_immutable_url())}</head>
<body class="auth-page"><main class="auth-shell"><div class="auth-stack"><section class="auth-card login-card">
<header class="auth-card-header">{auth_brand_markup()}</header>
<div class="auth-intro">
<h1 data-i18n="account.oidc.associateTitle">{html.escape(copy['associate_title'])}</h1>
<p class="auth-description" data-i18n="account.oidc.associateBody">{html.escape(copy['associate_body'])}</p></div>
<form class="auth-form" id="associationForm" method="post" action="/auth/oidc/associate">
<input type="hidden" name="token" value="{html.escape(association_token, quote=True)}">
<input type="hidden" name="auth_nonce" value="{html.escape(nonce, quote=True)}">
<label class="auth-field"><span data-i18n="account.username">{html.escape(login_copy['username'])}</span>
<input name="username" autocomplete="username" required maxlength="255"></label>
<label class="auth-field"><span data-i18n="account.password">{html.escape(login_copy['password'])}</span>
<input name="password" type="password" autocomplete="current-password" required maxlength="4096"></label>
{error_markup}<button class="auth-primary-button" type="submit" data-i18n="account.oidc.associateSubmit">{html.escape(copy['submit'])}</button>
</form></section></div></main></body></html>'''
        page = HTMLResponse(
            markup,
            status_code=status_code,
            headers={'Cache-Control': 'no-store'},
        )
        set_auth_nonce_cookie(
            page,
            nonce,
            request.cookies.get(AUTH_NONCE_COOKIE),
        )
        return page

    def oidc_settings():
        settings = store._get_oidc_provider_settings()
        if not settings.get('enabled'):
            raise OIDCError('configuration_invalid')
        return settings

    async def complete_local_session(request, principal, next_path):
        current_principal = request.scope.get(PRINCIPAL_SCOPE_KEY)
        current_session = request_session_token(request)
        metadata = session_client_metadata(request)
        if current_principal is not None and current_session:
            raw_session, _ = await run_db(
                auth_service.replace_session,
                principal,
                current_session,
                **metadata,
            )
        else:
            raw_session, _ = await run_db(
                auth_service.create_session,
                principal,
                **metadata,
            )
        completed = RedirectResponse(
            next_path,
            status_code=303,
            headers={'Cache-Control': 'no-store'},
        )
        set_session_cookie(completed, raw_session)
        delete_oidc_browser_cookie(completed)
        delete_auth_nonce_cookie(completed)
        return completed

    async def oidc_start(request):
        try:
            settings = await run_db(oidc_settings)
        except OIDCError:
            return oidc_error_page(request, status_code=404)
        next_path = _safe_relative_path(request.query_params.get('next', '/'))
        purpose = request.query_params.get('purpose', 'login')
        current_principal = request.scope.get(PRINCIPAL_SCOPE_KEY)
        if purpose == 'link':
            if current_principal is None:
                return oidc_error_page(request, status_code=401)
            expected_user_id = current_principal.user_id
        elif purpose == 'login':
            expected_user_id = None
        else:
            return oidc_error_page(request, status_code=400)
        try:
            started = await oidc_service.begin(
                settings,
                purpose=purpose,
                next_path=next_path,
                expected_user_id=expected_user_id,
            )
        except OIDCError as error:
            status_code = 502 if error.code == 'provider_unavailable' else 400
            return oidc_error_page(request, status_code=status_code)
        redirect = RedirectResponse(
            started.authorization_url,
            status_code=307,
            headers={'Cache-Control': 'no-store'},
        )
        set_oidc_browser_cookie(redirect, started.browser_token)
        return redirect

    async def oidc_callback(request):
        values = {
            name: request.query_params.get(name)
            for name in ('state', 'code', 'error', 'error_description')
        }
        if (
            not isinstance(values['state'], str)
            or not values['state']
            or any(isinstance(value, str) and len(value) > 8192 for value in values.values())
        ):
            failed = oidc_error_page(request, status_code=400)
            delete_oidc_browser_cookie(failed)
            return failed
        try:
            settings = await run_db(oidc_settings)
            completion = await oidc_service.complete(
                settings,
                state=values['state'],
                browser_token=request.cookies.get(OIDC_BROWSER_COOKIE, ''),
                code=values['code'],
                error=values['error'],
                error_description=values['error_description'],
            )
        except OIDCError as error:
            status_code = 502 if error.code == 'provider_unavailable' else 400
            failed = oidc_error_page(request, status_code=status_code)
            delete_oidc_browser_cookie(failed)
            return failed

        claims = completion.claims
        transaction = completion.transaction
        current_principal = request.scope.get(PRINCIPAL_SCOPE_KEY)
        try:
            if transaction.purpose == 'link':
                if (
                    current_principal is None
                    or current_principal.user_id != transaction.expected_user_id
                ):
                    raise RuntimeError('OIDC link session changed')
                await run_db(
                    store.link_oidc_identity,
                    current_principal.user_id,
                    issuer=claims.issuer,
                    subject=claims.subject,
                    username_claim=claims.username,
                    display_name=claims.display_name,
                    email=claims.email,
                )
                principal = current_principal
            else:
                principal = await run_db(
                    store.principal_for_oidc_identity,
                    claims.issuer,
                    claims.subject,
                )
                if principal is not None:
                    await run_db(
                        store.link_oidc_identity,
                        principal.user_id,
                        issuer=claims.issuer,
                        subject=claims.subject,
                        username_claim=claims.username,
                        display_name=claims.display_name,
                        email=claims.email,
                    )
                elif settings['auto_create_users']:
                    principal = await run_db(
                        store.provision_oidc_member,
                        issuer=claims.issuer,
                        subject=claims.subject,
                        username_base=claims.username,
                        username_claim=claims.username,
                        display_name=claims.display_name,
                        email=claims.email,
                    )
                else:
                    association_token = secrets.token_urlsafe(32)
                    await run_db(
                        store.stage_oidc_association,
                        association_token=association_token,
                        browser_token=request.cookies.get(OIDC_BROWSER_COOKIE, ''),
                        issuer=claims.issuer,
                        subject=claims.subject,
                        username_claim=claims.username,
                        display_name=claims.display_name,
                        email=claims.email,
                        next_path=transaction.next_path,
                        config_revision=settings['config_revision'],
                        expires_at=time.time() + 600,
                    )
                    return RedirectResponse(
                        '/auth/oidc/associate?token=' + quote(association_token, safe=''),
                        status_code=303,
                        headers={'Cache-Control': 'no-store'},
                    )
        except (RuntimeError, ValueError, sqlite3.IntegrityError):
            failed = oidc_error_page(request, status_code=403)
            delete_oidc_browser_cookie(failed)
            return failed
        return await complete_local_session(request, principal, transaction.next_path)

    async def oidc_associate(request):
        try:
            settings = await run_db(oidc_settings)
        except OIDCError:
            return oidc_error_page(request, status_code=404)
        browser_token = request.cookies.get(OIDC_BROWSER_COOKIE, '')
        if request.method == 'GET':
            association_token = request.query_params.get('token', '')
            transaction = await run_db(
                store.get_oidc_association,
                association_token,
                browser_token,
                settings['config_revision'],
            )
            if transaction is None:
                return oidc_error_page(request, status_code=400)
            return oidc_association_form(request, association_token)
        try:
            data = await form_data(request, maximum_size=16 * 1024)
        except (ValueError, UnicodeDecodeError):
            return oidc_error_page(request, status_code=400)
        association_token = data.get('token', '')
        supplied_nonce = data.get('auth_nonce', '')
        if (
            not valid_same_origin_request_source(request)
            or not supplied_nonce
            or not any(
                secrets.compare_digest(supplied_nonce, cookie_nonce)
                for cookie_nonce in auth_nonce_cookie_values(
                    request.cookies.get(AUTH_NONCE_COOKIE)
                )
            )
        ):
            return oidc_error_page(request, status_code=403)
        transaction = await run_db(
            store.get_oidc_association,
            association_token,
            browser_token,
            settings['config_revision'],
        )
        if transaction is None:
            return oidc_error_page(request, status_code=400)
        client_key = request.client.host if request.client is not None else 'unknown'

        def _authenticate_association():
            authenticated = auth_service.authenticate_password(
                data.get('username', ''),
                data.get('password', ''),
                client_key,
                allow_member=True,
            )
            if authenticated is None:
                return None, 429 if auth_service.login_retry_after_seconds(
                    client_key, data.get('username', '')
                ) else 401
            return authenticated, 0

        principal, status_code = await run_db(_authenticate_association)
        if principal is None:
            return oidc_association_form(
                request,
                association_token,
                error=True,
                status_code=status_code,
            )
        try:
            identity = await run_db(
                store.complete_oidc_association,
                association_token,
                browser_token,
                settings['config_revision'],
                principal.user_id,
            )
        except (RuntimeError, ValueError, sqlite3.IntegrityError):
            return oidc_error_page(request, status_code=409)
        if identity is None:
            return oidc_error_page(request, status_code=400)
        return await complete_local_session(request, principal, transaction.next_path)

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
            return await run_render(
                login_form,
                requested_next,
                locale=requested_locale,
                locale_explicit=locale_explicit,
                existing_auth_nonce_cookie=request.cookies.get(AUTH_NONCE_COOKIE),
            )
        current_principal = request.scope.get(PRINCIPAL_SCOPE_KEY)
        if current_principal is not None and authenticated_login_retry(request):
            data, parse_error = await bounded_public_json_object(request)
            if parse_error is not None:
                return public_json_error(parse_error)
            return response(
                {'redirect': _safe_relative_path(data.get('next') or requested_next)},
                cache_control='no-store',
            )
        if current_principal is None and not valid_anonymous_auth_request(request):
            # No-JavaScript fallback for legacy e-Ink Kindle WebKit: the form
            # posts application/x-www-form-urlencoded and proves the auth
            # nonce from the cookie through a hidden field, exactly like the
            # OIDC association form.
            try:
                form = await form_data(request, maximum_size=16 * 1024)
            except (UnicodeDecodeError, ValueError):
                return invalid_auth_request()
            supplied_nonce = form.get('auth_nonce', '')
            if (
                not supplied_nonce
                or not valid_same_origin_request_source(request)
                or not any(
                    secrets.compare_digest(supplied_nonce, cookie_nonce)
                    for cookie_nonce in auth_nonce_cookie_values(
                        request.cookies.get(AUTH_NONCE_COOKIE)
                    )
                )
            ):
                return invalid_auth_request()
            data = dict(form)
        else:
            data, parse_error = await bounded_public_json_object(request)
            if parse_error is not None:
                return public_json_error(parse_error)
        next_path = _safe_relative_path(data.get('next') or requested_next)
        client_key = request.client.host if request.client is not None else 'unknown'
        current_session = request_session_token(request)
        metadata = session_client_metadata(request)

        def _authenticate_login():
            settings = store.get_oidc_settings()
            authenticated = auth_service.authenticate_password(
                data.get('username', ''),
                data.get('password', ''),
                client_key,
                allow_member=(
                    not settings.enabled
                    or settings.allow_member_password_login
                ),
            )
            if authenticated is None:
                return None, auth_service.login_retry_after_seconds(
                    client_key,
                    data.get('username', ''),
                ), None
            if current_principal is not None and current_session:
                session, _ = auth_service.replace_session(
                    authenticated,
                    current_session,
                    **metadata,
                )
            else:
                session, _ = auth_service.create_session(
                    authenticated,
                    **metadata,
                )
            return authenticated, 0, session

        principal, retry_after_seconds, raw_session = await run_db(_authenticate_login)
        if principal is None:
            if retry_after_seconds:
                locale = normalize_login_locale(data.get('locale') or requested_locale)
                minutes = max(1, math.ceil(retry_after_seconds / 60))
                payload = error_payload(
                    'login_throttled',
                    LOGIN_COPY.get(locale, LOGIN_COPY['en'])['login_throttled'].format(minutes=minutes),
                )
                payload['retry_after_seconds'] = retry_after_seconds
                throttled = response(payload, 429, cache_control='no-store')
                throttled.headers['Retry-After'] = str(retry_after_seconds)
                return throttled
            return response(
                error_payload(
                    'invalid_credentials',
                    'Invalid username or password',
                ),
                401,
                cache_control='no-store',
            )

        logged_in = response(
            {'redirect': next_path},
            cache_control='no-store',
        )
        set_session_cookie(logged_in, raw_session)
        delete_auth_nonce_cookie(logged_in)
        return logged_in

    async def logout(request):
        await run_db(auth_service.revoke_session, request.cookies.get(SESSION_COOKIE))
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

        def _session_state():
            user = store.get_user(principal.user_id)
            settings = store.get_oidc_settings()
            identities = user_oidc_identities(user)
            return settings, identities

        oidc_settings, oidc_identities = await run_db(_session_state)
        return response(
            {
                'user': {
                    'id': principal.user_id,
                    'username': principal.username,
                    'role': principal.role,
                    'oidc_identities': oidc_identities,
                },
                'csrf_token': auth_service.issue_csrf_token(
                    principal,
                    raw_session,
                ),
                'oidc': {
                    'enabled': oidc_settings.enabled,
                    'provider_name': (
                        oidc_settings.provider_name if oidc_settings.enabled else ''
                    ),
                    'linked': any(
                        identity['issuer'] == oidc_settings.issuer_url
                        for identity in oidc_identities
                    ) if oidc_settings.enabled else False,
                },
            },
            cache_control='no-store',
        )

    async def account_appearance(request):
        principal = require_principal(request)
        if request.method == 'GET':
            settings = await run_db(store.get_account_appearance, principal.user_id)
        else:
            try:
                changes = await request.json()
            except (UnicodeDecodeError, json.JSONDecodeError):
                changes = None
            if (
                not isinstance(changes, dict)
                or not changes
                or not changes.keys() <= APPEARANCE_DEFAULTS.keys()
                or ('automatic' in changes and type(changes['automatic']) is not bool)
                or any(
                    not isinstance(value, str) or value not in APPEARANCE_THEMES
                    for key, value in changes.items() if key != 'automatic'
                )
            ):
                locale = resolve_request_locale(request)
                return response(
                    error_payload('invalid_appearance', get_bundle(locale)['theme.invalid']),
                    400, cache_control='private, no-store',
                )
            settings = await run_db(store.update_account_appearance, principal.user_id, changes)
        return response(settings, cache_control='private, no-store')

    async def account_reader_page(markup, principal):
        preferences = await run_db(store.get_account_appearance, principal.user_id)
        # Values are restricted to the theme identifiers and a boolean.
        bootstrap = '<script>window.EpubBrowserAppearance=' + json.dumps(preferences) + ';</script>'
        markup = markup.replace('<head>', '<head>\n' + bootstrap, 1)
        target = HTMLResponse(markup, headers={'Cache-Control': 'private, no-store'})
        return await apply_security_headers(target, markup=markup)

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

        def _change_password():
            authenticated = auth_service.authenticate_password(
                principal.username,
                current_password,
                client_key(request),
            )
            if authenticated is None or authenticated.user_id != principal.user_id:
                return False
            store.set_password_hash_and_revoke_sessions(
                principal.user_id,
                hash_password(new_password),
            )
            return True

        if not await run_db(_change_password):
            return response(
                error_payload('invalid_credentials', 'Invalid username or password'),
                401,
            )
        changed = response({'message': 'Password changed'})
        delete_session_cookie(changed)
        return changed

    async def list_own_sessions(request):
        principal = require_principal(request)

        def _list_sessions():
            current_session_id = store.session_id_from_token(
                request_session_token(request),
                user_id=principal.user_id,
            )
            return current_session_id, store.list_sessions(
                principal.user_id,
                active_only=True,
            )

        current_session_id, sessions = await run_db(_list_sessions)
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

        def _revoke_session():
            current_session_id = store.session_id_from_token(
                request_session_token(request),
                user_id=principal.user_id,
            )
            return current_session_id, store.revoke_user_session(
                principal.user_id,
                session_id,
            )

        current_session_id, revoked_ok = await run_db(_revoke_session)
        if not revoked_ok:
            return response(error_payload('not_found', 'Session not found'), 404)
        revoked = response({'message': 'Session revoked'})
        if session_id == current_session_id:
            delete_session_cookie(revoked)
        return revoked

    def personal_access_token_data(record):
        def iso_timestamp(value):
            if value is None:
                return None
            return datetime.fromtimestamp(
                float(value), timezone.utc
            ).isoformat().replace('+00:00', 'Z')

        return {
            'id': record.token_id,
            'name': record.name,
            'scopes': list(record.scopes),
            'created_at': iso_timestamp(record.created_at),
            'expires_at': iso_timestamp(record.expires_at),
            'last_used_at': iso_timestamp(record.last_used_at),
        }

    async def own_personal_access_tokens(request):
        principal = require_principal(request)
        if request.method == 'GET':
            tokens = await run_db(
                store.list_personal_access_tokens,
                principal.user_id,
            )
            return response({
                'personal_access_tokens': [
                    personal_access_token_data(record)
                    for record in tokens
                ]
            })
        data = await json_object(request)
        if data is None:
            return response(error_payload('invalid_json', 'Invalid JSON data'), 400)
        name = data.get('name')
        current_password = data.get('current_password')
        scopes = data.get('scopes')
        expires_in_days = data.get('expires_in_days')
        if (
            not isinstance(name, str)
            or not isinstance(current_password, str)
            or not isinstance(scopes, list)
            or expires_in_days not in (None, 30, 90, 180, 365)
        ):
            return response(
                error_payload('invalid_personal_access_token', 'Invalid personal access token'),
                400,
            )
        expires_at = (
            None
            if expires_in_days is None
            else time.time() + expires_in_days * 24 * 60 * 60
        )

        def _issue_token():
            authenticated = auth_service.authenticate_password(
                principal.username,
                current_password,
                client_key(request),
            )
            if authenticated is None or authenticated.user_id != principal.user_id:
                return 'invalid_credentials', None
            if 'admin:data:read' in scopes and principal.role != 'admin':
                return 'forbidden', None
            try:
                return 'ok', store.create_personal_access_token(
                    principal.user_id,
                    name,
                    scopes,
                    expires_at=expires_at,
                )
            except ValueError:
                return 'invalid_token', None

        outcome, issued = await run_db(_issue_token)
        if outcome == 'invalid_credentials':
            return response(
                error_payload('invalid_credentials', 'Invalid username or password'),
                401,
            )
        if outcome == 'forbidden':
            return response(error_payload('forbidden', 'Forbidden'), 403)
        if outcome == 'invalid_token':
            return response(
                error_payload('invalid_personal_access_token', 'Invalid personal access token'),
                400,
            )
        return response({
            'personal_access_token': personal_access_token_data(issued.token),
            'token': issued.raw_token,
        }, 201, cache_control='no-store')

    async def revoke_own_personal_access_token(request):
        principal = require_principal(request)
        if not await run_db(
            store.revoke_personal_access_token,
            principal.user_id,
            request.path_params['token_id'],
        ):
            return response(error_payload('not_found', 'Personal access token not found'), 404)
        return Response(status_code=204)

    async def admin_oidc_settings(request):
        require_admin(request)
        if request.method == 'GET':
            settings = await run_db(store.get_oidc_settings)
            suggestion = str(request.base_url).rstrip('/') + '/auth/oidc/callback'
            return response(
                {
                    'settings': oidc_settings_data(settings),
                    'callback_path': '/auth/oidc/callback',
                    'suggested_redirect_uri': suggestion,
                },
                cache_control='private, no-store',
            )
        data = await bounded_unique_json_object(request, maximum_size=16 * 1024)
        required = {
            'enabled',
            'provider_name',
            'issuer_url',
            'client_id',
            'redirect_uri',
            'scopes',
            'username_claim',
            'auto_create_users',
            'allow_member_password_login',
        }
        optional = {'client_secret', 'clear_client_secret'}
        if data is None or not required.issubset(data) or not set(data) <= required | optional:
            return response(
                error_payload('invalid_oidc_settings', 'Invalid OIDC settings'),
                400,
                'private, no-store',
            )
        clear_secret = data.get('clear_client_secret', False)
        supplied_secret = data.get('client_secret') if 'client_secret' in data else None
        scopes = data.get('scopes')
        if (
            not isinstance(data.get('enabled'), bool)
            or not isinstance(data.get('provider_name'), str)
            or not isinstance(data.get('issuer_url'), str)
            or not isinstance(data.get('client_id'), str)
            or not isinstance(data.get('redirect_uri'), str)
            or not isinstance(scopes, list)
            or not scopes
            or any(not isinstance(scope, str) or not scope.strip() for scope in scopes)
            or not isinstance(data.get('username_claim'), str)
            or not isinstance(data.get('auto_create_users'), bool)
            or not isinstance(data.get('allow_member_password_login'), bool)
            or not isinstance(clear_secret, bool)
            or (
                'client_secret' in data
                and supplied_secret is not None
                and not isinstance(supplied_secret, str)
            )
            or (supplied_secret is None and 'client_secret' in data and not clear_secret)
            or (clear_secret and isinstance(supplied_secret, str))
        ):
            return response(
                error_payload('invalid_oidc_settings', 'Invalid OIDC settings'),
                400,
                'private, no-store',
            )
        current = await run_db(store._get_oidc_provider_settings)
        candidate_secret = (
            ''
            if clear_secret
            else supplied_secret
            if isinstance(supplied_secret, str)
            else current['client_secret']
        )
        candidate_values = {
            **data,
            'enabled': True,
            'client_secret': candidate_secret,
            'config_revision': int(current['config_revision']) + 1,
        }
        try:
            candidate = None
            if any(
                str(data.get(name, '')).strip()
                for name in ('issuer_url', 'redirect_uri', 'client_id', 'provider_name')
            ):
                candidate = OIDCConfiguration.from_settings(candidate_values)
            if data['enabled']:
                if not candidate_secret or candidate is None:
                    raise OIDCError('configuration_invalid')
                await oidc_service.validate_configuration(candidate)
            saved = await run_db(
                store.replace_oidc_settings,
                enabled=data['enabled'],
                provider_name=data['provider_name'],
                issuer_url=data['issuer_url'],
                client_id=data['client_id'],
                client_secret=(
                    supplied_secret if isinstance(supplied_secret, str) else None
                ),
                redirect_uri=data['redirect_uri'],
                scopes=scopes,
                username_claim=data['username_claim'],
                auto_create_users=data['auto_create_users'],
                allow_member_password_login=data['allow_member_password_login'],
                clear_client_secret=clear_secret,
            )
        except OIDCError as error:
            return response(
                error_payload('oidc_' + error.code, 'OIDC settings could not be validated'),
                400,
                'private, no-store',
            )
        except (ValueError, sqlite3.IntegrityError):
            return response(
                error_payload('invalid_oidc_settings', 'Invalid OIDC settings'),
                400,
                'private, no-store',
            )
        return response(
            {'settings': oidc_settings_data(saved)},
            cache_control='private, no-store',
        )

    async def account_oidc_link(request):
        principal = require_principal(request)
        data = await bounded_unique_json_object(request, maximum_size=2048)
        if data is None or not set(data) <= {'next'}:
            return response(error_payload('invalid_oidc_link', 'Invalid OIDC link request'), 400)
        next_path = _safe_relative_path(data.get('next', '/account'), '/account')

        def _oidc_link_state():
            return (
                store.get_oidc_settings(),
                store.list_oidc_identities(principal.user_id),
            )

        settings, identities = await run_db(_oidc_link_state)
        if not settings.enabled:
            return response(error_payload('oidc_disabled', 'OIDC is disabled'), 409)
        if any(
            identity.issuer == settings.issuer_url
            for identity in identities
        ):
            return response(error_payload('oidc_already_linked', 'OIDC identity is already linked'), 409)
        target = (
            '/auth/oidc/start?purpose=link&next='
            + quote(next_path, safe='')
        )
        return response({'redirect': target}, cache_control='private, no-store')

    def selected_identity_issuer(user_id, settings, requested_issuer=None):
        identities = store.list_oidc_identities(user_id)
        if requested_issuer:
            return next(
                (item.issuer for item in identities if item.issuer == requested_issuer),
                None,
            )
        current = next(
            (item.issuer for item in identities if item.issuer == settings.issuer_url),
            None,
        )
        if current is not None:
            return current
        return identities[0].issuer if len(identities) == 1 else None

    async def account_oidc_identity(request):
        principal = require_principal(request)
        requested_issuer = request.query_params.get('issuer')

        def _unlink_identity():
            settings = store.get_oidc_settings()
            issuer = selected_identity_issuer(
                principal.user_id,
                settings,
                requested_issuer,
            )
            if issuer is None:
                return 'not_found'
            try:
                removed = store.unlink_oidc_identity(
                    principal.user_id,
                    issuer,
                    allow_member_password_login=(
                        not settings.enabled or settings.allow_member_password_login
                    ),
                )
            except RuntimeError:
                return 'last_login_method'
            return 'ok' if removed else 'not_found'

        outcome = await run_db(_unlink_identity)
        if outcome == 'last_login_method':
            return response(
                error_payload('oidc_last_login_method', 'Cannot remove the only login method'),
                409,
            )
        if outcome == 'not_found':
            return response(error_payload('oidc_identity_not_found', 'OIDC identity not found'), 404)
        return Response(status_code=204)

    async def admin_user_oidc_identity(request):
        require_admin(request)
        username = request.path_params['username']
        requested_issuer = request.query_params.get('issuer')

        def _unlink_identity():
            try:
                user = store.get_user_by_username(username)
            except ValueError:
                user = None
            if user is None:
                return 'user_not_found'
            settings = store.get_oidc_settings()
            issuer = selected_identity_issuer(
                user.user_id,
                settings,
                requested_issuer,
            )
            if issuer is None:
                return 'identity_not_found'
            removed = store.unlink_oidc_identity(
                user.user_id,
                issuer,
                allow_member_password_login=True,
                force=True,
            )
            return 'ok' if removed else 'identity_not_found'

        outcome = await run_db(_unlink_identity)
        if outcome == 'user_not_found':
            return response(error_payload('not_found', 'User not found'), 404)
        if outcome != 'ok':
            return response(error_payload('oidc_identity_not_found', 'OIDC identity not found'), 404)
        return Response(status_code=204)

    async def admin_users(request):
        require_admin(request)
        if request.method == 'GET':
            users = await run_db(store.list_users)
            return response({'users': [user_data(user) for user in users]})
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
        def _create_user():
            return store.create_user(
                username,
                hash_password(password),
                role=role,
            )

        try:
            created = await run_db(_create_user)
        except (ValueError, sqlite3.IntegrityError):
            return response(
                error_payload('username_unavailable', 'Username is unavailable'),
                409,
            )
        setup_state.request_revalidate()
        refreshed = await run_db(store.get_user_by_username, created.username)
        return response(
            {'user': user_data(refreshed)},
            201,
        )

    async def admin_user_deletion_impact(request):
        principal = require_admin(request)
        username = request.path_params['username']

        def _deletion_impact():
            try:
                target = store.get_user_by_username(username)
            except ValueError:
                return 'not_found', None, None
            if target.user_id == principal.user_id:
                return 'self', None, None
            return 'ok', target, store.user_deletion_impact(target.user_id)

        outcome, user, impact = await run_db(_deletion_impact)
        if outcome == 'not_found':
            return response(error_payload('not_found', 'User not found'), 404)
        if outcome == 'self':
            return response(
                error_payload(
                    'self_deletion_forbidden',
                    'The current administrator cannot delete their own account',
                ),
                409,
            )
        return response({'impact': impact})

    async def admin_user(request):
        principal = require_admin(request)
        username = request.path_params['username']

        def _get_user():
            try:
                return store.get_user_by_username(username)
            except ValueError:
                return None

        user = await run_db(_get_user)
        if user is None:
            return response(error_payload('not_found', 'User not found'), 404)
        data = await json_object(request)
        if data is None:
            return response(error_payload('invalid_json', 'Invalid JSON data'), 400)
        if request.method == 'DELETE':
            confirmation = data.get('confirmation')
            if confirmation is not None and not isinstance(confirmation, str):
                return response(
                    error_payload('invalid_user', 'Invalid user data'), 400
                )
            try:
                await run_db(
                    store.delete_user,
                    user.user_id,
                    replacement_user_id=principal.user_id,
                    confirmation=confirmation,
                )
            except UserDeletionError as error:
                payload = error_payload(error.code, str(error))
                if error.impact is not None:
                    payload['impact'] = error.impact
                return response(payload, 409)
            setup_state.request_revalidate()
            return Response(status_code=204)
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
            updated = await run_db(
                store.update_user,
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
        setup_state.request_revalidate()
        return response({'user': user_data(updated)})

    async def admin_reset_password(request):
        require_admin(request)
        username = request.path_params['username']

        def _get_user():
            try:
                return store.get_user_by_username(username)
            except ValueError:
                return None

        user = await run_db(_get_user)
        if user is None:
            return response(error_payload('not_found', 'User not found'), 404)
        data = await json_object(request)
        password = data.get('password') if data is not None else None
        if not isinstance(password, str) or not password:
            return response(
                error_payload('invalid_password', 'Invalid password'),
                400,
            )

        def _reset_password():
            return store.set_password_hash_and_revoke_sessions(
                user.user_id,
                hash_password(password),
                revoke_personal_access_tokens=True,
            )

        updated = await run_db(_reset_password)
        return response({'user': user_data(updated)})

    async def admin_books(request):
        require_admin(request)
        books = await run_db(store.active_books)
        return response({'books': [admin_book_data(book) for book in books]})

    async def admin_books_upload(request):
        require_admin(request)
        if not runtime_status.is_ready():
            return response(error_payload("not_ready", "Server is not ready"), 503)
        raw_name = unquote(request.headers.get("x-epub-browser-source-filename", ""))
        filename = _safe_source_filename(raw_name)
        if not filename:
            return response(
                error_payload("invalid_source_filename", "Invalid source filename"), 400
            )
        if not is_supported_source(Path(filename)):
            return response(
                error_payload("unsupported_source", "Only EPUB and PDF files are supported"), 400
            )
        target = upload_sources_dir / filename
        if target.exists():
            return response(
                error_payload("book_source_exists", "A book source with this name already exists"), 409
            )
        def _read_upload_head(path):
            with path.open('rb') as probe:
                return probe.read(5)

        temp = upload_sources_dir / (".upload-" + secrets.token_urlsafe(24))
        output = None
        try:
            output = await run_io(temp.open, 'xb')
            buffer = bytearray()
            async for chunk in request.stream():
                buffer.extend(chunk)
                if len(buffer) >= 1024 * 1024:
                    payload = bytes(buffer)
                    buffer.clear()
                    await run_io(output.write, payload)
            if buffer:
                await run_io(output.write, bytes(buffer))
            await run_io(output.close)
            output = None
            head = await run_io(_read_upload_head, temp)
            if not _is_valid_book_magic(head, filename):
                return response(
                    error_payload("unsupported_source", "The uploaded file is not a valid EPUB or PDF"), 400
                )
            await run_io(os.replace, temp, target)
        except OSError:
            return response(
                error_payload("source_upload_failed", "Failed to store the uploaded file"), 400
            )
        finally:
            if output is not None:
                try:
                    await run_io(output.close)
                except OSError:
                    pass
            await run_io(temp.unlink, missing_ok=True)
        if library_manager is not None:
            library_manager.queue_path(target)
        return response({"filename": filename}, 201)

    async def admin_book_index(request):
        require_admin(request)
        summaries = await run_db(store.list_admin_book_summaries)
        return response({
            'books': [admin_book_summary_data(book) for book in summaries]
        })

    async def admin_bulk_books(request):
        require_admin(request)
        data = await bounded_unique_json_object(request)
        if data is None or set(data) not in ({'operation', 'book_ids'}, {'operation', 'book_ids', 'user_ids'}):
            return response(error_payload('invalid_bulk_book_update', 'Invalid bulk book update'), 400)
        operation = data.get('operation')
        book_ids = data.get('book_ids')
        user_ids = data.get('user_ids')
        if (
            operation not in {'restrict', 'grant'}
            or not isinstance(book_ids, list)
            or not book_ids
            or any(not isinstance(book_id, str) or not book_id for book_id in book_ids)
            or len(set(book_ids)) != len(book_ids)
            or (operation == 'restrict' and user_ids is not None)
            or (operation == 'grant' and (
                not isinstance(user_ids, list)
                or not user_ids
                or any(not isinstance(user_id, str) or not user_id for user_id in user_ids)
                or len(set(user_ids)) != len(user_ids)
            ))
        ):
            return response(error_payload('invalid_bulk_book_update', 'Invalid bulk book update'), 400)
        def _bulk_update():
            if operation == 'restrict':
                return store.bulk_set_book_visibility(book_ids, 'restricted')
            return store.bulk_grant_book_access(book_ids, user_ids)

        try:
            updated_book_ids = await run_db(_bulk_update)
        except (KeyError, ValueError):
            return response(error_payload('invalid_bulk_book_update', 'Invalid bulk book update'), 400)
        return response({'operation': operation, 'updated_count': len(updated_book_ids)})

    async def admin_book(request):
        require_admin(request)
        book_id = request.path_params['book_id']
        if request.method in {'GET', 'HEAD'}:
            try:
                book = await run_db(store.get_admin_book_detail, book_id)
            except KeyError:
                return response(error_payload('not_found', 'Book not found'), 404)
            return response({'book': admin_book_detail_data(book)})
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
            book = await run_db(store.set_book_visibility, book_id, visibility)
        except KeyError:
            return response(error_payload('not_found', 'Book not found'), 404)
        return response({'book': admin_book_data(book)})

    async def admin_book_settings(request):
        require_admin(request)
        book_id = request.path_params['book_id']
        data = await bounded_unique_json_object(request)
        legacy_required = {'visibility', 'user_ids', 'tag_ids', 'profile'}
        managed_required = legacy_required | {'title', 'authors'}
        if data is None or frozenset(data) not in {
            frozenset(legacy_required), frozenset(managed_required)
        }:
            return response(
                error_payload(
                    'invalid_book_settings',
                    'Invalid book settings',
                ),
                400,
            )
        visibility = data['visibility']
        user_ids = data['user_ids']
        tag_ids = data['tag_ids']
        profile = data['profile']
        title = data.get('title')
        authors = data.get('authors')
        if (
            not isinstance(visibility, str)
            or visibility not in {'authenticated', 'restricted'}
            or not isinstance(user_ids, list)
            or any(
                not isinstance(user_id, str) or not user_id
                for user_id in user_ids
            )
            or not isinstance(tag_ids, list)
            or any(
                not isinstance(tag_id, str) or not tag_id
                for tag_id in tag_ids
            )
            or not isinstance(profile, str)
            or profile not in {'auto', 'technical', 'fiction', 'general'}
            or ('title' in data and (
                not isinstance(title, str)
                or not title.strip()
                or len(title.strip()) > 500
                or not isinstance(authors, list)
                or len(authors) > 100
                or any(
                    not isinstance(author, str)
                    or not author.strip()
                    or len(author.strip()) > 500
                    for author in authors
                )
            ))
        ):
            return response(
                error_payload(
                    'invalid_book_settings',
                    'Invalid book settings',
                ),
                400,
            )
        try:
            await run_db(store.get_admin_book_detail, book_id)
        except KeyError:
            return response(error_payload('not_found', 'Book not found'), 404)
        settings = {
            'visibility': visibility,
            'user_ids': user_ids,
            'tag_ids': tag_ids,
            'profile': profile,
        }
        if 'title' in data:
            settings.update({'title': title, 'authors': authors})
        try:
            book, summary = await run_db(
                store.update_admin_book_settings, book_id, **settings
            )
        except (KeyError, ValueError):
            return response(
                error_payload(
                    'invalid_book_settings',
                    'Invalid book settings',
                ),
                400,
            )
        return response({
            'book': admin_book_detail_data(book),
            'summary': admin_book_summary_data(summary),
        })

    def admin_book_raw_tail(request):
        prefix = b'/api/admin/books/'
        raw_path = request.scope.get('raw_path')
        if isinstance(raw_path, bytes):
            raw_path = raw_path.split(b'?', 1)[0]
            if raw_path.startswith(prefix):
                return raw_path[len(prefix):], True
        book_path = request.path_params.get('book_path', '')
        return str(book_path).encode('utf-8'), False

    def decode_admin_book_path(value, encoded):
        if encoded:
            value = unquote_to_bytes(value)
        return value.decode('utf-8', errors='replace')

    async def admin_book_request(request):
        raw_tail, encoded = admin_book_raw_tail(request)
        method = request.method

        async def dispatch(handler, **path_params):
            request.scope['path_params'] = path_params
            return await handler(request)

        if method == 'PUT' and raw_tail.endswith(b'/settings'):
            book_id = decode_admin_book_path(raw_tail[:-len(b'/settings')], encoded)
            return await dispatch(admin_book_settings, book_id=book_id)
        if method in {'GET', 'HEAD', 'PUT'} and raw_tail.endswith(b'/ai'):
            book_id = decode_admin_book_path(raw_tail[:-len(b'/ai')], encoded)
            return await dispatch(admin_book_ai, book_id=book_id)
        grant_marker = b'/grants/'
        if method in {'PUT', 'DELETE'} and grant_marker in raw_tail:
            raw_book_id, raw_user_id = raw_tail.rsplit(grant_marker, 1)
            if raw_user_id and b'/' not in raw_user_id:
                return await dispatch(
                    admin_book_grant,
                    book_id=decode_admin_book_path(raw_book_id, encoded),
                    user_id=decode_admin_book_path(raw_user_id, encoded),
                )
        if method == 'PUT' and raw_tail.endswith(b'/grants'):
            book_id = decode_admin_book_path(raw_tail[:-len(b'/grants')], encoded)
            return await dispatch(admin_book_grants, book_id=book_id)
        if method in {'GET', 'HEAD', 'PUT'}:
            return await dispatch(
                admin_book,
                book_id=decode_admin_book_path(raw_tail, encoded),
            )
        raise StarletteHTTPException(status_code=405, detail='Method not allowed')

    async def admin_book_grant(request):
        require_admin(request)
        book_id = request.path_params['book_id']
        user_id = request.path_params['user_id']
        try:
            await run_db(store.get_book, book_id)
        except KeyError:
            return response(error_payload('not_found', 'Book not found'), 404)
        try:
            user = await run_db(store.get_user, user_id)
        except (KeyError, ValueError):
            return response(error_payload('not_found', 'User not found'), 404)
        if not user.enabled:
            return response(
                error_payload('user_disabled', 'User is disabled'),
                400,
            )
        if request.method == 'PUT':
            await run_db(store.grant_book_access, book_id, user_id)
            granted = True
        else:
            await run_db(store.revoke_book_access, book_id, user_id)
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
            grants = await run_db(store.replace_book_grants, book_id, user_ids)
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
            settings = await run_db(store.get_ai_settings)
            return response({'settings': settings})
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
        current_settings = await run_db(store.get_ai_settings)
        model_context_window = data.get(
            'model_context_window',
            data.get('chat_context_tokens', current_settings['model_context_window']),
        )
        if (
            not isinstance(data['enabled'], bool)
            or not isinstance(data['base_url'], str)
            or not isinstance(data['model'], str)
            or (api_key is not None and not isinstance(api_key, str))
            or not isinstance(clear_api_key, bool)
            or isinstance(data['timeout_seconds'], bool)
            or not isinstance(data['timeout_seconds'], int)
            or isinstance(model_context_window, bool)
            or not isinstance(model_context_window, int)
            or isinstance(data['max_concurrency'], bool)
            or not isinstance(data['max_concurrency'], int)
            or isinstance(data['daily_limit'], bool)
            or not isinstance(data['daily_limit'], int)
        ):
            return response(error_payload('invalid_ai_settings', 'Invalid AI settings'), 400)
        try:
            if data['enabled']:
                validate_provider_base_url(data['base_url'])
            settings = await run_db(
                store.set_ai_settings,
                enabled=data['enabled'],
                base_url=data['base_url'],
                api_key=api_key,
                model=data['model'],
                timeout_seconds=data['timeout_seconds'],
                model_context_window=model_context_window,
                max_concurrency=data['max_concurrency'],
                daily_limit=data['daily_limit'],
                clear_api_key=clear_api_key,
            )
        except ValueError:
            return response(error_payload('invalid_ai_settings', 'Invalid AI settings'), 400)
        return response({'settings': settings})

    def general_settings_response(settings):
        # Preserve exact values when the browser cannot represent them as numbers.
        if settings['book_cache_limit'] > 2**53 - 1:
            settings['book_cache_limit'] = str(settings['book_cache_limit'])
        return response({'settings': settings})

    async def admin_general_settings(request):
        require_admin(request)
        if request.method == 'GET':
            settings = await run_db(store.get_general_settings)
            return general_settings_response(settings)
        data = await json_object(request)
        if data is None:
            return response(error_payload('invalid_json', 'Invalid JSON data'), 400)
        changes = {
            key: data[key]
            for key in ('recent_reading_limit', 'reading_insights_rank_limit', 'book_cache_limit')
            if key in data
        }
        try:
            if not changes or any(value is None for value in changes.values()):
                raise ValueError
            cache_limit = changes.get('book_cache_limit')
            if isinstance(cache_limit, str) and re.fullmatch(r'[0-9]+', cache_limit):
                changes['book_cache_limit'] = int(cache_limit)
            settings = await run_db(store.set_general_settings, **changes)
        except ValueError:
            return response(
                error_payload('invalid_general_settings', 'Invalid general settings'),
                400,
            )
        if library_manager is not None and 'book_cache_limit' in changes:
            await run_io(library_manager.trim_book_cache)
        return general_settings_response(settings)

    async def admin_ai_user_access(request):
        require_admin(request)
        user_id = request.path_params['user_id']

        def _get_user():
            try:
                return store.get_user(user_id)
            except (KeyError, ValueError):
                return None

        user = await run_db(_get_user)
        if user is None:
            return response(error_payload('not_found', 'User not found'), 404)
        if request.method == 'GET':
            access = await run_db(store.get_ai_user_access, user_id)
            return response({'access': access})
        data = await json_object(request)
        limit = data.get('daily_limit') if isinstance(data, dict) else None
        if (
            not isinstance(data, dict)
            or not isinstance(data.get('enabled'), bool)
            or (
                'daily_limit' in data
                and limit is not None
                and (isinstance(limit, bool) or not isinstance(limit, int) or limit < 0)
            )
        ):
            return response(error_payload('invalid_ai_access', 'Invalid AI access'), 400)
        try:
            await run_db(
                store.set_ai_user_access,
                user_id,
                enabled=data['enabled'],
                daily_limit=limit if 'daily_limit' in data else None,
            )
        except ValueError:
            return response(error_payload('invalid_ai_access', 'Invalid AI access'), 400)
        access = await run_db(store.get_ai_user_access, user_id)
        return response({'access': access})

    async def admin_ai_tags(request):
        require_admin(request)
        if request.method == 'GET':
            tags = await run_db(store.list_ai_tags)
            return response({'tags': list(tags)})
        data = await json_object(request)
        name = data.get('name') if isinstance(data, dict) else None
        if not isinstance(name, str):
            return response(error_payload('invalid_ai_tag', 'Invalid tag'), 400)
        try:
            tag = await run_db(store.create_ai_tag, name)
        except ValueError:
            return response(error_payload('invalid_ai_tag', 'Invalid tag'), 400)
        return response({'tag': tag}, 201)

    async def admin_ai_tag(request):
        require_admin(request)
        tag_id = request.path_params['tag_id']
        if request.method == 'DELETE':
            if not await run_db(store.delete_ai_tag, tag_id):
                return response(error_payload('not_found', 'Tag not found'), 404)
            return response({'message': 'Tag deleted'})
        data = await json_object(request)
        name = data.get('name') if isinstance(data, dict) else None
        if not isinstance(name, str):
            return response(error_payload('invalid_ai_tag', 'Invalid tag'), 400)
        try:
            tag = await run_db(store.rename_ai_tag, tag_id, name)
        except KeyError:
            return response(error_payload('not_found', 'Tag not found'), 404)
        except ValueError:
            return response(error_payload('invalid_ai_tag', 'Invalid tag'), 400)
        return response({'tag': tag})

    async def admin_book_ai(request):
        require_admin(request)
        book_id = request.path_params['book_id']
        try:
            await run_db(store.get_book, book_id)
        except KeyError:
            return response(error_payload('not_found', 'Book not found'), 404)
        if request.method in {'GET', 'HEAD'}:
            def _book_ai_state():
                return (
                    store.get_book_ai_profile(book_id),
                    store.book_ai_tags(book_id),
                    store.effective_book_tags(book_id),
                )

            profile, tags, effective_tags = await run_db(_book_ai_state)
            return response({
                'profile': profile,
                'tags': list(tags),
                'effective_tags': list(effective_tags),
            })
        data = await json_object(request)
        if data is None:
            return response(error_payload('invalid_book_ai', 'Invalid book AI settings'), 400)
        has_profile = 'profile' in data
        has_tag_ids = 'tag_ids' in data
        if not has_profile and not has_tag_ids:
            return response(error_payload('invalid_book_ai', 'Invalid book AI settings'), 400)
        profile = data.get('profile') if has_profile else None
        tag_ids = data.get('tag_ids') if has_tag_ids else None
        if (
            (has_profile and profile not in {'auto', 'technical', 'fiction', 'general'})
            or (has_tag_ids and (
                not isinstance(tag_ids, list)
                or any(not isinstance(tag_id, str) or not tag_id for tag_id in tag_ids)
            ))
        ):
            return response(error_payload('invalid_book_ai', 'Invalid book AI settings'), 400)
        try:
            current_profile, current_tags = await run_db(
                store.update_book_ai_settings,
                book_id,
                profile=profile if has_profile else None,
                tag_ids=tag_ids if has_tag_ids else None,
            )
        except (ValueError, KeyError):
            return response(error_payload('invalid_book_ai', 'Invalid book AI settings'), 400)
        return response({
            'profile': current_profile,
            'tags': list(current_tags),
            'effective_tags': [tag['name'] for tag in current_tags],
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
        if book_id is not None and await run_db(store.book_by_id, book_id) is None:
            return response(error_payload('not_found', 'Book not found'), 404)
        deleted = await run_db(
            store.clear_ai_reading_results,
            book_id=book_id,
            config_revision=revision,
        )
        return response({'deleted': deleted})

    def admin_ai_job_query(request):
        query = request.query_params
        if any(len(query.getlist(name)) != 1 for name in (
            'page', 'page_size', 'status'
        ) if name in query):
            raise ValueError('Repeated AI job query parameter')
        if any(name not in {'page', 'page_size', 'status'} for name in query):
            raise ValueError('Unknown AI job query parameter')

        def positive_integer(name, default, maximum):
            value = query.get(name)
            if value is None:
                return default
            if (
                isinstance(value, bool)
                or not isinstance(value, str)
                or not value
                or not value.isascii()
                or not value.isdecimal()
            ):
                raise ValueError('Invalid AI job query integer')
            parsed = int(value)
            if parsed < 1 or parsed > maximum:
                raise ValueError('AI job query integer is out of bounds')
            return parsed

        status = query.get('status')
        if status is not None and status not in ADMIN_AI_JOB_STATUSES:
            raise ValueError('Invalid AI job status')
        return (
            status,
            positive_integer('page', 1, ADMIN_AI_JOB_MAX_PAGE),
            positive_integer('page_size', 20, ADMIN_AI_JOB_MAX_PAGE_SIZE),
        )

    async def admin_ai_jobs(request):
        require_admin(request)
        try:
            status, page, page_size = admin_ai_job_query(request)
            jobs, total = await run_db(
                store.list_admin_ai_jobs,
                status=status,
                page=page,
                page_size=page_size,
            )
        except ValueError:
            return response(
                error_payload('invalid_ai_job_query', 'Invalid AI job query'), 400
            )
        return response({
            'jobs': list(jobs),
            'pagination': {
                'page': page,
                'page_size': page_size,
                'total': total,
                'total_pages': (total + page_size - 1) // page_size,
            },
        })

    def admin_ai_job_retry_error_response(error):
        status = {
            'ai_not_authorized': 403,
            'ai_job_not_found': 404,
            'book_not_found': 404,
            'chapter_not_found': 404,
            'ai_job_retry_conflict': 409,
            'ai_disabled': 503,
            'source_unavailable': 503,
            'no_reading_material': 503,
            'ai_template_unavailable': 503,
        }.get(error.code, 400)
        return response(
            error_payload(error.code, 'AI job retry failed'), status
        )

    async def admin_ai_job_retry(request):
        principal = require_admin(request)
        job_id = request.path_params['job_id']
        if not job_id:
            return response(error_payload('ai_job_not_found', 'AI job not found'), 404)
        try:
            result = await ai_reading.retry_job(principal, job_id)
        except AIReadingError as error:
            return admin_ai_job_retry_error_response(error)
        status = 202 if (
            result.get('status') == 'queued' and not result.get('shared')
        ) else 200
        return response(result, status)

    def ai_error_response(error):
        status = {
            'ai_disabled': 503,
            'ai_not_authorized': 403,
            'ai_quota_exhausted': 429,
            'book_not_found': 404,
            'chapter_not_found': 404,
            'ai_result_not_found': 404,
            'ai_reading_required': 409,
        }.get(error.code, 400)
        return response(error_payload(error.code, 'AI reading request failed'), status)

    async def ai_status(request):
        principal = require_principal(request)

        def _ai_status():
            settings = store.get_ai_settings()
            authorized = settings['enabled'] and store.can_use_ai(principal)
            return settings, authorized, (
                store.ai_daily_limit(principal) if authorized else None
            )

        settings, authorized, daily_limit = await run_db(_ai_status)
        return response({
            'enabled': settings['enabled'],
            'authorized': authorized,
            'daily_limit': daily_limit,
        })

    async def book_effective_metadata(request):
        principal = require_principal(request)
        book_id = request.path_params['book_id']

        def _effective_metadata():
            if not store.can_read_book(
                principal.user_id, principal.role, book_id
            ):
                return None
            metadata = store.managed_book_metadata(book_id)
            return {
                'title': metadata['title'],
                'authors': list(metadata['authors']),
                'tags': list(metadata['tags']),
                'ai_profile': store.get_book_ai_profile(book_id),
            }

        metadata = await run_db(_effective_metadata)
        if metadata is None:
            return response(error_payload('forbidden', 'Forbidden'), 403)
        return response(metadata)

    def book_language(book_id):
        book = store.book_by_id(book_id)
        if book is None:
            raise ValueError("book_not_found")
        try:
            metadata = json.loads(book.metadata_json)
        except json.JSONDecodeError:
            metadata = {}
        language = metadata.get("language")
        return language if isinstance(language, str) and language.strip() else "en"

    async def dictionary_lookup(request):
        principal = require_principal(request)
        book_id = request.path_params["book_id"]
        if await run_db(book_access_denied, principal, book_id):
            return forbidden_book_response()
        data, error = await bounded_public_json_object(request, maximum_size=2048)
        if error or not isinstance(data.get("text"), str) or not isinstance(data.get("dictionary_id"), str):
            return response(error_payload("invalid_dictionary_query", "Invalid dictionary query"), 400, "private, no-store")
        chapter_index = data.get("chapter_index")
        lookup_id = data.get("lookup_id")
        track = "chapter_index" in data or "lookup_id" in data
        if track and (
            type(chapter_index) is not int or chapter_index < 0
            or not isinstance(lookup_id, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", lookup_id)
        ):
            return response(error_payload("invalid_dictionary_query", "Invalid dictionary query"), 400, "private, no-store")
        try:
            result = await run_io(
                dictionary_service.lookup, data["dictionary_id"], data["text"]
            )
        except DictionaryServiceError as error:
            status = 404 if error.code == "dictionary_unavailable" else 400
            return response(error_payload(error.code, "Dictionary lookup failed"), status, "private, no-store")
        except ValueError:
            return response(error_payload("not_found", "Not Found"), 404, "private, no-store")
        recorded = None
        if track:
            recorded = False
            try:
                await run_db(authorized_chapter_snapshot, book_id, chapter_index)
                recorded = await run_db(
                    store.record_vocabulary_lookup, principal, book_id, chapter_index,
                    lookup_id, " ".join(data["text"].split()), result.query,
                )
            except (ValueError, ServerPageError, sqlite3.Error):
                # A recording failure must not suppress a valid dictionary result.
                pass
        return response({
            "found": result.found,
            **({"vocabulary_recorded": recorded} if track else {}),
            "query": result.query,
            "asset_base_path": result.asset_base_path,
            "allow_scripts": result.allow_scripts,
            "dictionary": {
                "id": result.dictionary.id,
                "display_name": result.dictionary.display_name,
            },
            "entries": list(result.entries),
        }, cache_control="private, no-store")

    async def vocabulary(request):
        principal = require_principal(request)
        book_id = request.query_params.get("book_id")
        cache_control = "private, no-store"
        if book_id is not None and await run_db(book_access_denied, principal, book_id):
            return response(error_payload("forbidden", "Forbidden"), 403, cache_control)
        if request.method in ("GET", "HEAD"):
            try:
                options = vocabulary_page_options(request.query_params)
            except ValueError:
                return response(error_payload("invalid_vocabulary_query", "Invalid vocabulary query"), 400, cache_control)
            result = await run_db(store.list_vocabulary, principal, book_id, **options)
            return response(result, cache_control=cache_control)
        mastery = None
        if request.method == "PATCH":
            data, error = await bounded_public_json_object(request, maximum_size=1024)
            if error or data.get("mastery") not in MASTERY_STATES:
                return response(error_payload("invalid_vocabulary_mastery", "Invalid mastery state"), 400, cache_control)
            mastery = data["mastery"]
        changed = await run_db(
            store.change_vocabulary, principal, request.path_params["word_id"],
            book_id=book_id, mastery=mastery,
        )
        if not changed:
            return response(error_payload("not_found", "Not found"), 404, cache_control)
        if request.method == "DELETE":
            return Response(status_code=204, headers={"Cache-Control": cache_control})
        return response({"mastery": mastery}, cache_control=cache_control)

    async def dictionary_choices(request):
        principal = require_principal(request)
        book_id = request.path_params["book_id"]
        if await run_db(book_access_denied, principal, book_id):
            return forbidden_book_response()

        def _dictionary_choices():
            available = list(dictionary_service.list_available())
            default = dictionary_service.store.get_global_dictionary_default()
            default_dictionary_id = default.id if default and any(
                record.id == default.id for record in available
            ) else None
            if default_dictionary_id:
                available.sort(
                    key=lambda record: record.id != default_dictionary_id
                )
            return default_dictionary_id, [
                {
                    "id": record.id,
                    "display_name": record.display_name,
                    "entry_count": record.entry_count,
                }
                for record in available
            ]

        default_dictionary_id, dictionaries = await run_io(_dictionary_choices)
        return response({
            "default_dictionary_id": default_dictionary_id,
            "dictionaries": dictionaries,
        }, cache_control="private, no-store")

    async def dictionary_media(request):
        principal = require_principal(request)
        book_id = request.path_params["book_id"]
        if await run_db(book_access_denied, principal, book_id):
            return forbidden_book_response()
        try:
            media = await run_io(
                dictionary_service.get_media,
                request.path_params["dictionary_id"],
                request.path_params["media_id"],
            )
        except DictionaryServiceError:
            return response(error_payload("not_found", "Not Found"), 404, "private, no-store")
        return Response(
            media["content"], media_type=media["content_type"],
            headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
        )

    async def dictionary_asset(request):
        principal = require_principal(request)
        book_id = request.path_params["book_id"]
        if await run_db(book_access_denied, principal, book_id):
            return forbidden_book_response()
        try:
            asset = await run_io(
                dictionary_service.get_asset,
                request.path_params["dictionary_id"],
                request.path_params["asset_path"],
            )
        except DictionaryServiceError:
            return response(error_payload("not_found", "Not Found"), 404, "private, no-store")
        return Response(
            asset["content"], media_type=asset["content_type"],
            headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
        )

    async def encyclopedia_lookup(request):
        principal = require_principal(request)
        book_id = request.path_params["book_id"]
        if await run_db(book_access_denied, principal, book_id):
            return forbidden_book_response()
        data, error = await bounded_public_json_object(request, maximum_size=2048)
        if error or not isinstance(data.get("text"), str):
            return response(error_payload("invalid_encyclopedia_query", "Invalid encyclopedia query"), 400, "private, no-store")
        try:
            language = await run_db(book_language, book_id)
            result = await asyncio.to_thread(encyclopedia.lookup, language, data["text"])
        except EncyclopediaError as error:
            status = 429 if error.code == "encyclopedia_rate_limited" else 400
            return response(error_payload(error.code, "Encyclopedia lookup failed"), status, "private, no-store")
        except ValueError:
            return response(error_payload("not_found", "Not Found"), 404, "private, no-store")
        return response({
            "found": result.found,
            "title": result.title,
            "description": result.description,
            "extract": result.extract,
            "source_url": result.source_url,
            "attribution": result.attribution,
        }, cache_control="private, no-store")

    def dictionary_record_data(record, default_dictionary_id=None):
        return {
            "id": record.id, "display_name": record.display_name,
            "entry_count": record.entry_count, "attribution": record.attribution,
            "enabled": record.enabled,
            "allow_scripts": dictionary_service.allows_scripts(record.id),
            "is_default": record.id == default_dictionary_id,
        }

    async def admin_dictionaries(request):
        principal = require_admin(request)
        if request.method == "GET":
            def _list_dictionaries():
                default = dictionary_service.store.get_global_dictionary_default()
                default_id = default.id if default else None
                return default_id, [
                    dictionary_record_data(item, default_id)
                    for item in dictionary_service.store.list_dictionaries()
                ]

            default_dictionary_id, dictionaries = await run_io(_list_dictionaries)
            return response({
                "default_dictionary_id": default_dictionary_id,
                "dictionaries": dictionaries,
            })
        if not runtime_status.is_ready():
            return response(error_payload("not_ready", "Server is not ready"), 503)
        filename = unquote(request.headers.get("x-epub-browser-dictionary-filename", ""))
        display_name = unquote(request.headers.get("x-epub-browser-dictionary-name", ""))
        dictionary_format = request.headers.get("x-epub-browser-dictionary-format", "")
        upload = dictionary_service.dictionary_directory / (".upload-" + secrets.token_urlsafe(24))
        output = None
        try:
            output = await run_io(upload.open, "xb")
            buffer = bytearray()
            async for chunk in request.stream():
                buffer.extend(chunk)
                if len(buffer) >= 1024 * 1024:
                    payload = bytes(buffer)
                    buffer.clear()
                    await run_io(output.write, payload)
            if buffer:
                await run_io(output.write, bytes(buffer))
            await run_io(output.close)
            output = None
            if dictionary_format == "mdict":
                record = await run_io(
                    dictionary_service.install_mdict_package_file,
                    upload, filename,
                    created_by_user_id=principal.user_id,
                    display_name=display_name,
                )
            elif dictionary_format == "stardict":
                record = await run_io(
                    dictionary_service.install_stardict_package_file,
                    upload, filename,
                    created_by_user_id=principal.user_id,
                    display_name=display_name,
                )
            else:
                raise DictionaryServiceError("unsupported_dictionary_format")
        except (DictionaryServiceError, OSError, ValueError) as error:
            code = error.code if isinstance(error, DictionaryServiceError) else "invalid_dictionary_archive"
            return response(error_payload(code, "Dictionary installation failed"), 400)
        finally:
            if output is not None:
                try:
                    await run_io(output.close)
                except OSError:
                    pass
            await run_io(upload.unlink, missing_ok=True)
        default = await run_io(dictionary_service.store.get_global_dictionary_default)
        return response({"dictionary": dictionary_record_data(
            record, default.id if default else None,
        )}, 201)

    async def admin_dictionary_default(request):
        principal = require_admin(request)
        dictionary_id = request.path_params["dictionary_id"]
        try:
            record = await run_db(
                dictionary_service.store.set_global_dictionary_default,
                dictionary_id,
                principal.user_id,
            )
        except KeyError:
            return response(error_payload("not_found", "Not Found"), 404)
        return response({"dictionary": dictionary_record_data(record, record.id)})

    async def admin_dictionary(request):
        require_admin(request)
        dictionary_id = request.path_params["dictionary_id"]
        if request.method == "DELETE":
            try:
                await run_io(dictionary_service.delete, dictionary_id)
            except KeyError:
                return response(error_payload("not_found", "Not Found"), 404)
            return Response(status_code=204, headers={"Cache-Control": "no-cache"})
        data, error = await bounded_public_json_object(request)
        if error:
            return response(error_payload("invalid_dictionary_update", "Invalid dictionary update"), 400)
        if "display_name" in data:
            if not isinstance(data["display_name"], str):
                return response(error_payload("invalid_dictionary_name", "Invalid dictionary name"), 400)
            def _rename_dictionary():
                record = dictionary_service.rename(dictionary_id, data["display_name"])
                default = dictionary_service.store.get_global_dictionary_default()
                return dictionary_record_data(record, default.id if default else None)

            try:
                payload = await run_io(_rename_dictionary)
            except KeyError:
                return response(error_payload("not_found", "Not Found"), 404)
            except ValueError:
                return response(error_payload("invalid_dictionary_name", "Invalid dictionary name"), 400)
            return response({"dictionary": payload})
        if "allow_scripts" in data:
            if not isinstance(data["allow_scripts"], bool):
                return response(error_payload("invalid_dictionary_update", "Invalid dictionary update"), 400)

            def _set_dictionary_scripts():
                record = dictionary_service.set_script_execution_enabled(
                    dictionary_id, data["allow_scripts"],
                )
                default = dictionary_service.store.get_global_dictionary_default()
                return dictionary_record_data(record, default.id if default else None)

            try:
                payload = await run_io(_set_dictionary_scripts)
            except KeyError:
                return response(error_payload("not_found", "Not Found"), 404)
            except DictionaryServiceError:
                return response(error_payload("dictionary_unavailable", "Dictionary unavailable"), 400)
            return response({"dictionary": payload})
        if not isinstance(data.get("enabled"), bool):
            return response(error_payload("invalid_dictionary_update", "Invalid dictionary update"), 400)

        def _set_dictionary_enabled():
            record = dictionary_service.set_enabled(dictionary_id, data["enabled"])
            return dictionary_record_data(record)

        try:
            payload = await run_io(_set_dictionary_enabled)
        except KeyError:
            return response(error_payload("not_found", "Not Found"), 404)
        return response({"dictionary": payload})

    async def admin_dictionary_resources(request):
        require_admin(request)
        if not runtime_status.is_ready():
            return response(error_payload("not_ready", "Server is not ready"), 503)
        filename = unquote(request.headers.get("x-epub-browser-dictionary-filename", ""))
        upload = dictionary_service.dictionary_directory / (".resource-upload-" + secrets.token_urlsafe(24) + ".mdd")
        output = None
        try:
            output = await run_io(upload.open, "xb")
            buffer = bytearray()
            async for chunk in request.stream():
                buffer.extend(chunk)
                if len(buffer) >= 1024 * 1024:
                    payload = bytes(buffer)
                    buffer.clear()
                    await run_io(output.write, payload)
            if buffer:
                await run_io(output.write, bytes(buffer))
            await run_io(output.close)
            output = None
            await run_io(
                dictionary_service.attach_mdict_resources_file,
                request.path_params["dictionary_id"],
                upload,
                filename,
            )
        except (DictionaryServiceError, OSError, ValueError) as error:
            code = error.code if isinstance(error, DictionaryServiceError) else "invalid_mdict_resource"
            return response(error_payload(code, "Dictionary resource installation failed"), 400)
        finally:
            if output is not None:
                try:
                    await run_io(output.close)
                except OSError:
                    pass
            await run_io(upload.unlink, missing_ok=True)
        return Response(status_code=204, headers={"Cache-Control": "no-cache"})

    async def ai_reading_request(request):
        principal = require_principal(request)
        data, error = await bounded_public_json_object(request)
        if error:
            return response(error_payload(error, 'Invalid AI reading request'), 400)
        reading_request = ReadingRequest(
            scope=data.get('scope'),
            book_id=data.get('book_id'),
            chapter_index=data.get('chapter_index'),
            mode=data.get('mode', 'chapter'),
            language=data.get('language', 'en'),
            force=data.get('force', False),
            reading_boundary=data.get('reading_boundary'),
        )
        try:
            validate_reading_request(reading_request)
        except AIReadingError:
            return response(error_payload('invalid_ai_reading_request', 'Invalid AI reading request'), 400)
        if not await run_db(
            store.can_read_book,
            principal.user_id,
            principal.role,
            reading_request.book_id,
        ):
            return response(error_payload('forbidden', 'Forbidden'), 403)
        try:
            result = await ai_reading.submit(principal, reading_request)
        except AIReadingError as error:
            return ai_error_response(error)
        return response(result, 200 if result['status'] == 'complete' else 202)

    async def ai_job(request):
        principal = require_principal(request)
        job_id = request.path_params['job_id']

        def _job_state():
            job = store.get_ai_job(job_id)
            if job is None:
                return 'not_found', None, None
            if job.get('book_id'):
                if not store.can_read_book(
                    principal.user_id, principal.role, job['book_id']
                ):
                    return 'forbidden', None, None
            elif job['owner_user_id'] != principal.user_id:
                # Rows created before the shared-job migration lack the book
                # reference required for authorization, keep them owner-only.
                return 'not_found', None, None
            result = (
                store.get_ai_reading_result(job['result_id'])
                if job.get('result_id') else None
            )
            if result is not None and not store.can_read_book(
                principal.user_id, principal.role, result['book_id']
            ):
                return 'forbidden', None, None
            return 'ok', job, result

        outcome, job, result = await run_db(_job_state)
        if outcome == 'not_found':
            return response(error_payload('not_found', 'AI job not found'), 404)
        if outcome == 'forbidden':
            return response(error_payload('forbidden', 'Forbidden'), 403)
        return response({
            'job': _public_ai_job(job),
            'result': _public_ai_result(result),
        })

    def ai_reading_chapter_titles(book_id):
        chapter_titles = {}
        try:
            book_output = Path(base_directory, 'book', book_id)
            toc_path = book_output / 'content' / 'toc.json'
            if not toc_path.is_file():
                # Compatibility with pre-content-cache Server outputs.
                toc_path = book_output / 'toc.json'
            toc_items = json.loads(toc_path.read_text(encoding='utf-8'))
            if isinstance(toc_items, list):
                for toc_item in toc_items:
                    if not isinstance(toc_item, dict):
                        continue
                    chapter_index = toc_item.get('chapter_index')
                    chapter_title = toc_item.get('title')
                    if isinstance(chapter_index, int) and isinstance(chapter_title, str):
                        chapter_titles[chapter_index] = chapter_title
        except (OSError, TypeError, ValueError):
            # The generated TOC is an optional presentation enhancement.
            # AI results remain readable when a book is being regenerated.
            pass
        return chapter_titles

    async def ai_book_results(request):
        principal = require_principal(request)
        book_id = request.path_params['book_id']
        if not await run_db(
            store.can_read_book, principal.user_id, principal.role, book_id
        ):
            return response(error_payload('forbidden', 'Forbidden'), 403)
        chapter_index_raw = request.query_params.get('chapter_index')
        language = request.query_params.get('language')
        if language is not None and language not in SUPPORTED_LOCALE_SET:
            return response(error_payload('invalid_ai_reading_request', 'Invalid AI reading request'), 400)
        view = request.query_params.get('view')
        if view == 'indicators':
            results = await run_db(
                store.list_ai_reading_result_indicators,
                book_id, language=language,
            )
            return response({'results': list(results)})
        if view == 'summary':
            chapter_titles = await run_io(ai_reading_chapter_titles, book_id)
            summaries = await run_db(
                store.list_ai_reading_library_summaries, book_id
            )
            results = []
            for result in summaries:
                item = dict(result)
                item['can_delete'] = (
                    principal.role == 'admin'
                    or item.get('created_by_user_id') == principal.user_id
                )
                item.pop('created_by_user_id', None)
                chapter_index = item.get('chapter_index')
                if isinstance(chapter_index, int) and chapter_index in chapter_titles:
                    item['chapter_title'] = chapter_titles[chapter_index]
                results.append(item)
            return response({'results': results})
        if view is not None:
            return response(error_payload('invalid_ai_reading_request', 'Invalid AI reading request'), 400)
        chapter_index = None
        if chapter_index_raw is not None:
            try:
                chapter_index = int(chapter_index_raw)
            except ValueError:
                return response(error_payload('invalid_chapter_index', 'Invalid chapter index'), 400)
            if chapter_index < 0:
                return response(error_payload('invalid_chapter_index', 'Invalid chapter index'), 400)
        results = await run_db(
            store.list_ai_reading_results,
            book_id, chapter_index=chapter_index, language=language,
        )
        return response({
            'results': list(results),
            # Clients use this to avoid treating an older result schema as
            # the active reading layer while retaining it in the history hub.
            'current_template_version': template_for('chapter', 'chapter')['version'],
        })

    async def ai_reading_library(request):
        """Return every readable book's retained shared AI layers, never private chats."""
        principal = require_principal(request)
        view = request.query_params.get('view')
        if (
            view not in {None, 'summary'}
            or request.query_params.get('book_id') is not None
        ):
            return response(
                error_payload('invalid_ai_reading_request', 'Invalid AI reading request'),
                400,
            )
        def _library_payload():
            visible_books = list(store.visible_books(principal))
            result_counts = (
                store.ai_reading_result_counts()
                if view == 'summary'
                else {}
            )
            books = []
            for book in visible_books:
                # A shared layer belongs to the book rather than to the user who
                # generated it.  Retain historic results here too: a newer model
                # configuration must not make an earlier, still-useful reading
                # disappear from the user's AI-reading library.
                result_count = result_counts.get(book.book_id, 0)
                if view == 'summary':
                    results = None
                else:
                    results = list(store.list_ai_reading_results(book.book_id))
                    result_count = len(results)
                if not result_count:
                    continue
                metadata = store.managed_book_metadata(book.book_id)
                chapter_titles = (
                    ai_reading_chapter_titles(book.book_id)
                    if results is not None
                    else {}
                )
                enriched_results = []
                for result in results or ():
                    enriched_result = dict(result)
                    enriched_result['can_delete'] = (
                        principal.role == 'admin'
                        or result.get('created_by_user_id') == principal.user_id
                    )
                    # The UI only needs a permission bit.  Do not disclose which
                    # member generated another reader's shared learning layer.
                    enriched_result.pop('created_by_user_id', None)
                    chapter_index = enriched_result.get('chapter_index')
                    if isinstance(chapter_index, int) and chapter_index in chapter_titles:
                        enriched_result['chapter_title'] = chapter_titles[chapter_index]
                    enriched_results.append(enriched_result)
                cover = metadata.get('cover')
                book_payload = {
                    'book_id': book.book_id,
                    'title': str(metadata.get('title') or book.book_id),
                    'authors': list(metadata.get('authors') or []),
                    'cover': (
                        f"/book/{book.book_id}/{cover.lstrip('/')}"
                        if isinstance(cover, str) and cover.strip() else None
                    ),
                }
                if results is None:
                    book_payload['result_count'] = result_count
                else:
                    book_payload['results'] = enriched_results
                books.append(book_payload)
            return books

        return response({'books': await run_io(_library_payload)})

    async def ai_result(request):
        principal = require_principal(request)

        def _result_state():
            result = store.get_ai_reading_result(
                request.path_params['result_id']
            )
            if result is None:
                return 'not_found', None
            if not store.can_read_book(
                principal.user_id, principal.role, result['book_id']
            ):
                return 'forbidden', None
            if request.method == 'DELETE':
                # Shared learning layers remain readable by every authorized
                # reader, but their lifecycle is controlled by administrators
                # or by the member who generated the specific retained version.
                if (
                    principal.role != 'admin'
                    and result['created_by_user_id'] != principal.user_id
                ):
                    return 'forbidden', None
                store.delete_ai_reading_result(result['id'])
                return 'deleted', result
            return 'ok', result

        outcome, result = await run_db(_result_state)
        if outcome == 'not_found':
            return response(error_payload('not_found', 'AI result not found'), 404)
        if outcome == 'forbidden':
            return response(error_payload('forbidden', 'Forbidden'), 403)
        if outcome == 'deleted':
            return response({'deleted': result['id']})
        return response({'result': result})

    async def ai_events(request):
        """Push AI task state for a reader's open assistant panel.

        The model clients are intentionally request/response based, so this
        stream reports durable SQLite state changes rather than pretending to
        stream provider tokens.  A reconnect therefore resumes accurately
        after the panel is closed or the page is refreshed.
        """
        principal = require_principal(request)
        job_id = request.query_params.get('job_id')
        followup_id = request.query_params.get('followup_id')
        chat_id = request.query_params.get('chat_id')
        if sum(bool(value) for value in (job_id, followup_id, chat_id)) != 1:
            return response(error_payload('invalid_ai_event_request', 'Invalid AI event request'), 400)

        if job_id:
            def _job_access():
                job = store.get_ai_job(job_id)
                if job is None:
                    return 'not_found'
                if job.get('book_id'):
                    if not store.can_read_book(
                        principal.user_id, principal.role, job['book_id']
                    ):
                        return 'forbidden'
                    return 'ok'
                return 'ok' if job['owner_user_id'] == principal.user_id else 'forbidden'

            access = await run_db(_job_access)
            if access == 'not_found':
                return response(error_payload('not_found', 'AI job not found'), 404)
            if access == 'forbidden':
                return response(error_payload('forbidden', 'Forbidden'), 403)

            def snapshot():
                current = store.get_ai_job(job_id)
                if current is None:
                    return None
                result = store.get_ai_reading_result(current['result_id']) if current.get('result_id') else None
                return {
                    'job': _public_ai_job(current),
                    'result': _public_ai_result(result),
                }

            event_name = 'job'
            terminal = lambda payload: payload is None or payload['job']['status'] not in {'queued', 'running'}
        elif followup_id:
            def _followup_access():
                followup = store.get_ai_followup(followup_id, principal.user_id)
                if followup is None:
                    return 'followup_not_found'
                result = store.get_ai_reading_result(followup['result_id'])
                if result is None:
                    return 'result_not_found'
                if not store.can_read_book(
                    principal.user_id, principal.role, result['book_id']
                ):
                    return 'forbidden'
                return 'ok'

            access = await run_db(_followup_access)
            if access == 'followup_not_found':
                return response(error_payload('not_found', 'AI follow-up not found'), 404)
            if access == 'result_not_found':
                return response(error_payload('not_found', 'AI result not found'), 404)
            if access == 'forbidden':
                return response(error_payload('forbidden', 'Forbidden'), 403)

            def snapshot():
                current = store.get_ai_followup(followup_id, principal.user_id)
                return {'followup': current} if current is not None else None

            event_name = 'followup'
            terminal = lambda payload: payload is None or payload['followup']['status'] not in {'queued', 'running'}
        else:
            def _chat_access():
                turn = store.get_ai_book_chat_turn(chat_id, principal.user_id)
                if turn is None:
                    return 'not_found'
                if not store.can_read_book(
                    principal.user_id, principal.role, turn['book_id']
                ):
                    return 'forbidden'
                return 'ok'

            access = await run_db(_chat_access)
            if access == 'not_found':
                return response(error_payload('not_found', 'AI chat turn not found'), 404)
            if access == 'forbidden':
                return response(error_payload('forbidden', 'Forbidden'), 403)

            def snapshot():
                current = store.get_ai_book_chat_turn(chat_id, principal.user_id)
                return {'chat': current} if current is not None else None

            event_name = 'chat'
            terminal = lambda payload: payload is None or payload['chat']['status'] not in {'queued', 'running'}

        async def events():
            previous = None
            while True:
                payload = await run_db(snapshot)
                serialized = json.dumps(payload, ensure_ascii=False, separators=(',', ':'))
                if serialized != previous:
                    yield 'event: ' + event_name + '\ndata: ' + serialized + '\n\n'
                    previous = serialized
                if terminal(payload):
                    return
                await asyncio.sleep(0.5)

        return StreamingResponse(
            events(),
            media_type='text/event-stream',
            headers={
                'Cache-Control': 'no-store',
                'X-Accel-Buffering': 'no',
            },
        )

    async def ai_followups(request):
        principal = require_principal(request)
        if request.method == 'GET':
            result_id = request.path_params['result_id']

            def _list_followups():
                result = store.get_ai_reading_result(result_id)
                if result is None:
                    return 'not_found', None
                if not store.can_read_book(
                    principal.user_id, principal.role, result['book_id']
                ):
                    return 'forbidden', None
                return 'ok', list(
                    store.list_ai_followups(result_id, principal.user_id)
                )

            outcome, followups = await run_db(_list_followups)
            if outcome == 'not_found':
                return response(error_payload('not_found', 'AI result not found'), 404)
            if outcome == 'forbidden':
                return response(error_payload('forbidden', 'Forbidden'), 403)
            return response({'followups': followups})
        data, error = await bounded_public_json_object(request)
        if error:
            return response(error_payload(error, 'Invalid AI follow-up'), 400)
        result_id = data.get('result_id')
        question = data.get('question')
        language = data.get('language', 'en')
        if not isinstance(result_id, str) or not isinstance(question, str) or language not in SUPPORTED_LOCALE_SET:
            return response(error_payload('invalid_ai_followup', 'Invalid AI follow-up'), 400)
        def _followup_result():
            result = store.get_ai_reading_result(result_id)
            if result is None:
                return 'not_found'
            if not store.can_read_book(
                principal.user_id, principal.role, result['book_id']
            ):
                return 'forbidden'
            return 'ok'

        outcome = await run_db(_followup_result)
        if outcome == 'not_found':
            return response(error_payload('not_found', 'AI result not found'), 404)
        if outcome == 'forbidden':
            return response(error_payload('forbidden', 'Forbidden'), 403)
        try:
            followup = await ai_reading.follow_up(principal, result_id, question, language)
        except AIReadingError as error:
            return ai_error_response(error)
        return response({'followup': followup}, 202)

    async def ai_book_chat(request):
        principal = require_principal(request)
        book_id = request.path_params['book_id']
        if not await run_db(
            store.can_read_book, principal.user_id, principal.role, book_id
        ):
            return response(error_payload('forbidden', 'Forbidden'), 403)
        if request.method == 'GET':
            turns = await run_db(
                store.list_ai_book_chat_turns, book_id, principal.user_id
            )
            return response({'turns': list(turns)})
        data, error = await bounded_public_json_object(request)
        if error:
            return response(error_payload(error, 'Invalid AI chat'), 400)
        chapter_index = data.get('chapter_index')
        question = data.get('question')
        language = data.get('language', 'en')
        context_mode = data.get('context_mode', 'chapter_source')
        book_context = context_mode == 'book_overview'
        if (
            (not book_context and (isinstance(chapter_index, bool) or not isinstance(chapter_index, int)))
            or (book_context and chapter_index not in {None, ''})
            or not isinstance(question, str) or language not in SUPPORTED_LOCALE_SET
            or context_mode not in {'shared_layer', 'chapter_source', 'book_overview'}
        ):
            return response(error_payload('invalid_ai_chat', 'Invalid AI chat'), 400)
        try:
            turn = await ai_reading.ask_book(
                principal, book_id=book_id, chapter_index=None if book_context else chapter_index,
                question=question, language=language, context_mode=context_mode,
            )
        except AIReadingError as error:
            return ai_error_response(error)
        return response({'chat': turn}, 202)

    def sort_visible_catalog(principal, records, sort):
        return sort_catalog(
            records, sort, store.library_order(principal.user_id) if sort == "manual" else (),
        )

    async def filtered_library_metadata(request):
        principal = require_principal(request)
        sort = library_sort(request.query_params.get("sort"))

        def _library_metadata():
            records = sort_visible_catalog(principal, store.visible_books(principal), sort)
            return library_metadata(records, base_directory, state_store=store, owner_user_id=principal.user_id)

        return response(await run_db(_library_metadata))

    async def save_library_order(request):
        principal = require_principal(request)
        payload, error = await bounded_public_json_object(request, maximum_size=2 * 1024 * 1024)
        ids = payload.get("ids") if payload is not None else None
        if error or not isinstance(ids, list) or any(not isinstance(book_id, str) for book_id in ids):
            return response(error_payload('invalid_json', 'Invalid JSON data'), 400)

        def save():
            visible = {record.book_id for record in store.visible_books(principal)}
            order = tuple(dict.fromkeys(book_id for book_id in ids if book_id in visible))
            store.save_library_order(principal.user_id, order, import_legacy=payload.get("legacy") is True)

        await run_db(save)
        return Response(status_code=204)

    async def library_index(request):
        # Server's library is an authenticated SPA shell.  Render it from the
        # current asset manifest so a UI or i18n deployment is visible after a
        # restart without regenerating every EPUB or a checked-in index.html.
        # Keep the static fallback for partially initialized/legacy installs
        # where no manifest has been published yet.
        try:
            ai_settings = await run_db(store.get_ai_settings)
            markup = await run_render(
                render_library_shell,
                (), current_published_assets(), SiteURLs(),
                deployment_mode='server', kindle=kindle,
                ai_reading_enabled=ai_settings["enabled"],
            )
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
            markup = None
        if markup is not None:
            return await account_reader_page(markup, require_principal(request))

        index_path = os.path.join(base_directory, 'index.html')
        if not os.path.isfile(index_path):
            return response(error_payload('not_found', 'Library index not found'), 404)
        response = FileResponse(index_path, media_type='text/html')
        response.headers['Cache-Control'] = 'no-cache'
        return await apply_security_headers(response, index_path)

    def kindle_library_books(principal, sort):
        """Project visible book records onto the read-only minimal shelf."""
        books = []
        records = [record for record in store.visible_books(principal) if record.source_format == EPUB_FORMAT]
        for record in sort_visible_catalog(principal, records, sort):
            try:
                metadata = json.loads(record.metadata_json)
            except (TypeError, json.JSONDecodeError):
                metadata = {}
            if not isinstance(metadata, dict):
                metadata = {}
            try:
                authors = tuple(json.loads(record.authors_json))
            except (TypeError, json.JSONDecodeError):
                authors = ()
            tags = metadata.get("tags")
            books.append(
                LibraryBook(
                    book_id=record.book_id,
                    title=record.title,
                    authors=authors,
                    tags=tuple(tags) if isinstance(tags, (list, tuple)) else (),
                    cover=(f"/book/{record.book_id}/{metadata['cover']}"
                           if metadata.get("cover") else None),
                    source_format=record.source_format,
                )
            )
        return books

    async def kindle_library_page(request, *, show_dashboard=False):
        principal = require_principal(request)

        def page_number(key):
            value = request.query_params.get(key, "")
            return int(value) if re.fullmatch(r"[0-9]{1,9}", value) else 1

        sort = library_sort(request.query_params.get("sort"))

        def load_shelf():
            books = kindle_library_books(principal, sort)
            visible = {book.book_id for book in books}
            limit = store.get_general_settings()["recent_reading_limit"]
            recent = []
            for row in store.list_reading_progress(principal.user_id):
                book_id = row["book_id"]
                chapter = row["chapter_index"]
                if book_id not in visible:
                    continue
                cache = Path(base_directory) / "book" / book_id / "content"
                if not (cache / f"chapter_{chapter}.json").is_file() and not (
                    library_manager is not None and library_manager.book_cache_is_cold(book_id)
                ):
                    continue
                recent.append((book_id, chapter))
                if len(recent) == limit:
                    break
            row = store.get_bookshelf(principal.user_id)
            try:
                shelf = json.loads(row[1]) if row is not None else None
            except (TypeError, json.JSONDecodeError):
                shelf = None
            return books, shelf, recent, store.get_kindle_screensaver(principal.user_id)

        books, shelf, recent, dashboard = await run_db(load_shelf)
        markup = await run_render(
            render_kindle_library_page, books, SiteURLs(), shelf=shelf, recent=recent,
            locale=resolve_request_locale(request), dashboard=dashboard, show_dashboard=show_dashboard,
            catalog_page=page_number("catalog_page"), shelf_page=page_number("shelf_page"),
            query=request.query_params.get("q", ""), sort=sort,
        )
        target = HTMLResponse(markup, headers={'Cache-Control': 'private, no-store'})
        return await apply_security_headers(target, markup=markup, inline_scripts=True)

    async def kindle_entry(request):
        principal = require_principal(request)
        settings = await run_db(store.get_kindle_screensaver, principal.user_id)
        target = '/kindle/screensaver' if settings['default'] else '/kindle-library.html'
        return RedirectResponse(target, status_code=303, headers={'Cache-Control': 'private, no-store'})

    async def kindle_screensaver(request):
        return await kindle_library_page(request, show_dashboard=True)

    async def kindle_screensaver_memo(request):
        principal = require_principal(request)
        settings = await run_db(store.get_kindle_screensaver, principal.user_id)
        return response({'memo': settings['text'] if settings['memo'] else ''},
                        cache_control='private, no-store')

    async def kindle_screensaver_timezone(request):
        principal = require_principal(request)
        settings = await run_db(store.get_kindle_screensaver, principal.user_id)
        return response(
            {"offset": kindle_timezone_offset(settings["timezone"])},
            cache_control="private, no-store",
        )

    async def kindle_screensaver_calendar(request):
        principal = require_principal(request)
        settings = await run_db(store.get_kindle_screensaver, principal.user_id)
        urls = settings["calendar_urls"] if settings["calendar"] else []
        window = int(time.monotonic() // CALENDAR_REFRESH_SECONDS)
        zone_name = settings["timezone"]
        zone = ZoneInfo(zone_name) if zone_name else None
        feeds = await asyncio.gather(*(
            run_io(load_calendar_events, principal.user_id, url, window, zone_name)
            for url in urls
        ))
        events = {}
        failures = 0
        for feed in feeds:
            if feed is None:
                failures += 1
                continue
            for event in feed:
                key = (event.get("start", ""), event.get("end", ""), event["title"])
                if zone:
                    event = dict(event)
                    for field in ("start", "end"):
                        value = event.get(field, "")
                        if "T" in value:
                            timestamp = datetime.fromisoformat(value)
                            if timestamp.tzinfo is not None:
                                event[field] = timestamp.astimezone(zone).isoformat()
                events[key] = event
        return response(
            {"events": [events[key] for key in sorted(events)[:500]],
             "unavailable": bool(feeds) and failures == len(feeds),
             "partial": 0 < failures < len(feeds),
             **({"localized": True} if zone else {})},
            cache_control="private, no-store",
        )

    async def kindle_screensaver_preferences(request):
        principal = require_principal(request)
        if request.method == 'PUT':
            try:
                data = await request.json()
            except (UnicodeDecodeError, json.JSONDecodeError):
                data = None
            locale = resolve_request_locale(request)

            def invalid(code):
                message = get_bundle(locale)['account.error.' + code]
                return response(error_payload(code, message), 400, cache_control='private, no-store')

            if (
                not isinstance(data, dict)
                or any(type(data.get(key)) is not bool for key in KINDLE_WIDGETS)
                or ("pomodoro" in data and type(data["pomodoro"]) is not bool)
                or ("memo_text" in data and not valid_kindle_memo(data["memo_text"]))
            ):
                return invalid("invalid_kindle_preferences")
            if "timezone" in data:
                zone = data["timezone"]
                if not isinstance(zone, str) or (zone and zone not in kindle_timezones()):
                    return invalid("invalid_kindle_timezone")
            if "calendar_urls" in data or "calendar_url" in data:
                urls = data.get("calendar_urls", [data.get("calendar_url")])
                try:
                    if not isinstance(urls, list) or len(urls) > 8:
                        raise ValueError("Invalid calendar list")
                    data["calendar_urls"] = list(dict.fromkeys(
                        url for value in urls if (url := calendar_url(value))
                    ))
                except ValueError:
                    return invalid("invalid_kindle_calendar_url")
            await run_db(store.set_kindle_screensaver_preferences, principal.user_id, data)
        settings = await run_db(store.get_kindle_screensaver, principal.user_id)
        return response(
            {**{key: settings[key] for key in KINDLE_WIDGETS},
             "memo_text": settings["text"], "calendar_url": settings["calendar_url"],
             "calendar_urls": settings["calendar_urls"],
             "pomodoro": settings["pomodoro"], "timezone": settings["timezone"],
             **({"timezones": kindle_timezones()} if request.method == "GET" else {})},
            cache_control='private, no-store',
        )

    async def openapi_schema(request):
        result = response(openapi_document(), cache_control='public, max-age=300')
        # A weak validator also applies to the gzip representation.
        etag = 'W/"' + hashlib.sha256(result.body).hexdigest() + '"'
        result.headers['ETag'] = etag
        if if_none_match_matches(request.headers.get('if-none-match'), etag):
            return Response(status_code=304, headers={
                'ETag': etag, 'Cache-Control': result.headers['Cache-Control'],
            })
        return result

    async def api_docs(request):
        locale = resolve_request_locale(request)

        def _render_docs():
            docs = render_api_docs(public_api_operations(), openapi_document(), locale=locale)
            try:
                return rewrite_asset_urls(docs, current_published_assets())
            except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
                return docs

        markup = await run_render(_render_docs)
        target = HTMLResponse(markup, headers={
            'Cache-Control': 'public, max-age=300',
            'Vary': 'Accept-Language, Cookie',
        })
        return await apply_security_headers(target, markup=markup)

    async def reading_insights_page(request):
        """Keep legacy links safe now that insights lives in the shared modal hub."""
        require_principal(request)
        return RedirectResponse('/', status_code=303, headers={'Cache-Control': 'no-store'})

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

    async def pdf_document(request):
        principal = require_principal(request)
        if request.method not in {'GET', 'HEAD'}:
            return Response(
                status_code=405,
                headers={
                    'Allow': 'GET, HEAD',
                    'Cache-Control': 'private, no-cache',
                    'Content-Length': '0',
                },
            )
        book_id = request.path_params['book_id']
        if not await run_db(
            store.can_read_book, principal.user_id, principal.role, book_id
        ):
            return response(error_payload('not_found', 'Not Found'), 404)
        book = await run_db(store.book_by_id, book_id)
        if book is None or book.source_format != PDF_FORMAT:
            return response(error_payload('not_found', 'Not Found'), 404)

        try:
            await pin_book_cache(request, book_id, read=True)
        except BookCacheUnavailable:
            return response(error_payload('pdf_cache_stale', 'PDF cache requires refresh'), 409)

        if (
            not isinstance(book.source_size, int)
            or isinstance(book.source_size, bool)
            or not isinstance(book.source_mtime_ns, int)
            or isinstance(book.source_mtime_ns, bool)
        ):
            return response(
                error_payload('pdf_cache_stale', 'PDF cache requires refresh'),
                409,
            )
        source = Path(book.source_path)
        try:
            validated = await prepare_pdf_delivery_async(
                PDFDeliverySpecification(
                    source_path=source,
                    book_root=Path(base_directory, 'book', book_id),
                    source_size=book.source_size,
                    source_mtime_ns=book.source_mtime_ns,
                    source_digest=book.source_fingerprint,
                    output_revision=PDF_OUTPUT_REVISION,
                    metadata_schema_version=PDF_METADATA_SCHEMA_VERSION,
                )
            )
        except PDFValidationError:
            return response(
                error_payload('pdf_cache_stale', 'PDF cache requires refresh'),
                409,
            )

        expected_size = validated.size
        etag = f'"{validated.digest}"'
        headers = {
            'Accept-Ranges': 'bytes',
            'Cache-Control': 'private, no-cache',
            'Content-Disposition': inline_pdf_disposition(source.name),
            'ETag': etag,
            'X-Content-Type-Options': 'nosniff',
        }
        range_header = request.headers.get('range')
        # A PDF.js range fetch needs the selected bytes even when the browser
        # adds a cache validator for the same document. Returning 304 here
        # leaves the worker without the requested chunk and can produce a
        # successfully "rendered" but empty canvas. Full-document requests
        # still use ordinary ETag revalidation.
        if range_header is None and if_none_match_matches(
            request.headers.get('if-none-match'), etag
        ):
            validated.close()
            return Response(status_code=304, headers=headers)
        try:
            requested_range = parse_single_range(
                range_header, expected_size
            )
        except RangeNotSatisfiable:
            validated.close()
            headers.update({
                'Content-Range': f'bytes */{expected_size}',
                'Content-Length': '0',
            })
            return Response(status_code=416, headers=headers)

        selected = requested_range or ByteRange(0, expected_size - 1)
        status_code = 206 if requested_range is not None else 200
        headers['Content-Length'] = str(selected.length if expected_size else 0)
        if requested_range is not None:
            headers['Content-Range'] = (
                f'bytes {selected.start}-{selected.end}/{expected_size}'
            )
        if request.method == 'HEAD' or expected_size == 0:
            validated.close()
            return Response(
                status_code=status_code,
                media_type='application/pdf',
                headers=headers,
            )
        descriptor = validated.detach()
        try:
            return OwnedPDFFileResponse(
                descriptor,
                selected,
                status_code=status_code,
                headers=headers,
            )
        except BaseException:
            os.close(descriptor)
            raise

    async def book_preparation_page(request, book, kindle_page):
        locale = resolve_request_locale(request)
        english = get_bundle('en')
        bundle = get_bundle(locale)

        def label(key):
            return html.escape(bundle.get(key) or english[key])

        def query_link(**params):
            return '?' + html.escape(request.url.include_query_params(**params).query, quote=True)

        fallback = query_link(open='1')
        start_url = query_link(prepare='start')
        status_url = query_link(prepare='status')
        shelf = '/kindle-library.html' if kindle_page else '/'
        markup = f'''<!doctype html><html lang="{locale}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light dark">
<title data-i18n="admin.bookPreparation.title">{label('admin.bookPreparation.title')} · EPUB Browser</title>
<link rel="stylesheet" href="{current_asset_url('theme.css')}">
<link rel="stylesheet" href="{current_asset_url('account.css')}">
<script src="{current_asset_url('theme-bootstrap.js')}"></script>
{render_i18n_bootstrap(locale, None, core_url=i18n_core_immutable_url())}
</head><body class="auth-page"><main class="auth-shell">
<div class="auth-stack"><section class="auth-card book-prepare-card" aria-labelledby="bookPrepareTitle">
<h1 id="bookPrepareTitle" data-i18n="admin.bookPreparation.title">{label('admin.bookPreparation.title')}</h1>
<p class="book-prepare-name">{html.escape(book.title)}</p>
<div class="book-prepare-status" role="status" aria-live="polite" aria-atomic="true">
<p id="bookPrepareStatus" tabindex="-1" data-start="{start_url}" data-status="{status_url}" data-i18n="admin.bookPreparation.queued">{label('admin.bookPreparation.queued')}</p>
</div>
<progress id="bookPrepareProgress" aria-labelledby="bookPrepareStatus" hidden></progress>
<div class="book-prepare-actions">
<a class="book-prepare-back" href="{shelf}" data-i18n="library.title">{label('library.title')}</a>
<button id="bookPrepareRetry" class="auth-primary-button" type="button" hidden
 data-i18n="admin.ai.jobs.retry">{label('admin.ai.jobs.retry')}</button>
<a id="bookPrepareOpen" class="auth-primary-button" href="{fallback}"
 data-i18n="admin.bookPreparation.open">{label('admin.bookPreparation.open')}</a>
</div></section></div></main>
<script>
(function () {{
    var status = document.getElementById('bookPrepareStatus');
    var progress = document.getElementById('bookPrepareProgress');
    var retry = document.getElementById('bookPrepareRetry');
    var i18n = window.EpubBrowserI18n;
    var timer;
    var attempt = 0;
    var prepareUrl = status.getAttribute('data-start');
    var statusUrl = status.getAttribute('data-status');

    function update(key) {{
        if (status.getAttribute('data-i18n') === key) return;
        status.setAttribute('data-i18n', key);
        status.textContent = i18n.t(key);
    }}

    function get(url, complete) {{
        var xhr = new XMLHttpRequest();
        xhr.open('GET', url);
        xhr.onreadystatechange = function () {{
            if (xhr.readyState === 4) complete(xhr);
        }};
        xhr.send();
    }}

    function prepare() {{
        var current = ++attempt;
        var pending = true;
        if (document.activeElement === retry) status.focus();
        retry.hidden = true;
        progress.hidden = false;
        update('admin.bookPreparation.queued');

        function poll() {{
            get(statusUrl, function (xhr) {{
                if (!pending || current !== attempt) return;
                if (xhr.status === 200 && xhr.responseText === 'running') {{
                    update('admin.bookPreparation.running');
                }}
                timer = window.setTimeout(poll, 650);
            }});
        }}

        get(prepareUrl, function (xhr) {{
            pending = false;
            window.clearTimeout(timer);
            if (xhr.status === 204) {{
                window.location.reload();
                return;
            }}
            progress.hidden = true;
            retry.hidden = false;
            update('admin.bookPreparation.failed');
        }});
        poll();
    }}

    retry.addEventListener('click', prepare);
    prepare();
    document.getElementById('bookPrepareOpen').hidden = true;
}}());
</script></body></html>'''
        page = HTMLResponse(markup, headers={'Cache-Control': 'private, no-store'})
        return await apply_security_headers(page, markup=markup, inline_scripts=kindle_page)

    async def protected_public_file(request):
        try:
            path = normalize_public_path(request.path_params['path'])
        except ValueError:
            return response(error_payload('not_found', 'Not Found'), 404)
        if path == 'assets/i18n-manifest.json' or '/' + path == '/assets/i18n-manifest.json':
            from .i18n_bundles import build_i18n_manifest

            return JSONResponse(
                await run_io(build_i18n_manifest),
                headers={'Cache-Control': 'no-cache'},
            )
        if path.startswith('assets/i18n/') or path.startswith('assets/immutable/i18n/'):
            from .i18n_bundles import read_i18n_asset

            result = await run_io(read_i18n_asset, path)
            if result is None:
                return response(error_payload('not_found', 'Not Found'), 404)
            content, media_type = result
            return Response(
                content,
                media_type=media_type,
                headers={'Cache-Control': 'public, max-age=31536000, immutable'},
            )
        if '/' + path in PUBLIC_UNAUTHENTICATED_ASSETS:
            return FileResponse(
                os.path.join(os.path.dirname(__file__), path),
                media_type=mimetypes.guess_type(path)[0] or 'application/octet-stream',
                headers={'Cache-Control': 'no-cache'},
            )
        if is_public_unauthenticated_asset('/' + path):
            return await public_files.get_response(path, request.scope)
        if '/' + path in PUBLIC_WEB_MANIFESTS:
            return await public_files.get_response(path, request.scope)
        principal = require_principal(request)
        book_id = extract_book_id_from_public_path(path)
        book_relative_path = None
        if book_id:
            if not await run_db(
                store.can_read_book,
                principal.user_id,
                principal.role,
                book_id,
            ):
                return response(error_payload('forbidden', 'Forbidden'), 403)
            book = await run_db(store.book_by_id, book_id)
            if book is None:
                return response(error_payload('not_found', 'Not Found'), 404)
            book_relative_path = '/'.join(path.split('/')[2:])

            def _recorded_cover():
                try:
                    return json.loads(book.metadata_json).get('cover')
                except (TypeError, json.JSONDecodeError):
                    return None

            recorded_cover = await run_db(_recorded_cover)
            pdf_cover_allowed = (
                book.source_format == PDF_FORMAT
                and isinstance(recorded_cover, str)
                and recorded_cover == book_relative_path
                and recorded_cover == 'cover.png'
            )
            kindle_page_allowed = (
                kindle
                and book.source_format == EPUB_FORMAT
                and re.fullmatch(
                    r'kindle(?:\.html|_chapter_[0-9]+\.html)',
                    book_relative_path,
                    re.IGNORECASE,
                )
            )
            if not (
                server_book_public_path_allowed(book_relative_path)
                or pdf_cover_allowed
                or kindle_page_allowed
            ):
                return response(error_payload('not_found', 'Not Found'), 404)
            reader_page = book_relative_path.lower().endswith('.html')
            is_cover = recorded_cover == book_relative_path
            keep_cold = is_cover or book_relative_path == 'toc.json'
            prepare_action = request.query_params.get('prepare')
            if reader_page and library_manager is not None and prepare_action == 'status':
                running = await run_io(library_manager.book_cache_is_restoring, book_id)
                return Response(
                    'running' if running else 'queued',
                    media_type='text/plain',
                    headers={'Cache-Control': 'private, no-store'},
                )
            if reader_page and library_manager is not None and prepare_action == 'start':
                try:
                    await pin_book_cache(request, book_id, read=True)
                except BookCacheUnavailable:
                    return response(error_payload('book_content_unavailable', 'Book content is unavailable'), 503)
                return Response(status_code=204, headers={'Cache-Control': 'private, no-store'})
            if (
                reader_page and library_manager is not None
                and request.query_params.get('open') != '1'
                and (
                    request.headers.get('sec-fetch-mode') == 'navigate'
                    or (not request.headers.get('sec-fetch-mode')
                        and 'text/html' in request.headers.get('accept', ''))
                )
                and await run_io(library_manager.book_cache_is_cold, book_id)
            ):
                return await book_preparation_page(request, book, kindle_page_allowed)
            try:
                await pin_book_cache(request, book_id, read=reader_page, restore=not keep_cold)
            except BookCacheUnavailable:
                return response(error_payload('book_content_unavailable', 'Book content is unavailable'), 503)
            cold_metadata = (
                keep_cold and library_manager is not None
                and await run_io(library_manager.book_cache_is_cold, book_id)
            )
            if not cold_metadata and not await run_io(
                server_book_output_is_current, base_directory, book_id, book.source_format,
            ):
                return response(error_payload('not_found', 'Not Found'), 404)
            if not reader_page and book_relative_path != 'toc.json':
                return await public_files.get_response(path, request.scope)
            ai_settings = await run_db(store.get_ai_settings)
            ai_reading_enabled = bool(ai_settings.get("enabled"))

            def _renderer_metadata():
                return store.managed_book_metadata(book_id)

            renderer = ServerPageRenderer(
                base_directory,
                book_id,
                source_format=book.source_format,
                metadata_overrides=await run_db(_renderer_metadata),
                kindle=kindle,
                ai_reading_enabled=ai_reading_enabled,
            )
            # Retain a narrow compatibility path for manually-created test
            # fixtures and legacy caches that still have an accepted marker.
            # Fresh Server conversions always carry content/metadata.json and
            # therefore take the dynamic path below.
            def _has_dynamic_cache():
                return (
                    Path(
                        base_directory, 'book', book_id, 'pdf', 'metadata.json'
                    ).is_file()
                    if book.source_format == PDF_FORMAT
                    else Path(
                        base_directory, 'book', book_id, 'content', 'metadata.json'
                    ).is_file()
                )

            has_dynamic_cache = await run_io(_has_dynamic_cache)
            if has_dynamic_cache:
                try:
                    if book_relative_path == 'index.html':
                        review = await run_db(
                            store.get_book_review,
                            book_id,
                            principal.user_id,
                        )
                        markup = await run_render(
                            renderer.render_index,
                            initial_book_review=review,
                        )
                        return await account_reader_page(markup, principal)
                    chapter_match = re.fullmatch(
                        r'chapter_([0-9]+)\.html',
                        book_relative_path,
                        re.IGNORECASE,
                    )
                    if chapter_match:
                        markup = await run_render(
                            renderer.render_chapter,
                            int(chapter_match.group(1)),
                        )
                        return await account_reader_page(markup, principal)
                    if kindle_page_allowed:
                        if book_relative_path == 'kindle.html':
                            dashboard = await run_db(store.get_kindle_screensaver, principal.user_id)
                            tools = {"pomodoro": dashboard["pomodoro"]}
                            markup = await run_render(
                                renderer.render_kindle_index, locale=resolve_request_locale(request), tools=tools,
                            )
                            dynamic_response = HTMLResponse(
                                markup,
                                headers={'Cache-Control': 'private, no-cache'},
                            )
                            return await apply_security_headers(
                                dynamic_response,
                                markup=markup,
                                inline_scripts=True,
                            )
                        kindle_chapter_match = re.fullmatch(
                            r'kindle_chapter_([0-9]+)\.html',
                            book_relative_path,
                            re.IGNORECASE,
                        )
                        if kindle_chapter_match:
                            markup = await run_render(
                                renderer.render_kindle_chapter,
                                int(kindle_chapter_match.group(1)),
                                locale=resolve_request_locale(request),
                            )
                            dynamic_response = HTMLResponse(
                                markup,
                                headers={'Cache-Control': 'private, no-cache'},
                            )
                            return await apply_security_headers(
                                dynamic_response,
                                markup=markup,
                                inline_scripts=True,
                            )
                    if book_relative_path == 'toc.json':
                        return Response(
                            await run_render(renderer.toc_bytes),
                            media_type='application/json',
                            headers={'Cache-Control': 'no-cache'},
                        )
                except ServerPageError:
                    return response(error_payload('not_found', 'Not Found'), 404)
        static_response = await public_files.get_response(path, request.scope)
        if book_relative_path and re.fullmatch(
            r'(?:index|chapter_[0-9]+)\.html',
            book_relative_path,
            re.IGNORECASE,
        ):
            await apply_security_headers(
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

    async def version_status(request):
        release = await asyncio.to_thread(release_lookup.fetch)
        if release is None:
            # Version checks are explicitly optional. A blocked/offline release
            # lookup must not surface as a failed application resource in the
            # browser console; the client already treats an empty response as
            # "no update information available".
            return Response(status_code=204, headers={'Cache-Control': 'no-store'})
        return response(release, cache_control='no-cache')

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
        request_id = secrets.token_hex(8)
        if log_errors:
            LOGGER.error(
                "Unhandled server error id=%s method=%s path=%s",
                request_id,
                request.method,
                request.url.path,
                exc_info=(type(exc), exc, exc.__traceback__),
            )
        cache_control = (
            'private, no-cache'
            if request.scope.get(PRINCIPAL_SCOPE_KEY) is not None
            else 'no-store'
        )
        return response(
            error_payload('server_error', 'Internal server error'),
            500,
            cache_control=cache_control,
            headers={'X-Request-ID': request_id},
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
                view = request.query_params.get('view')
                if view is not None:
                    if view != 'summary' or tail:
                        return response(
                            error_payload(
                                'invalid_annotation_view',
                                'Invalid annotation view',
                            ),
                            400,
                        )
                    def _annotation_summaries():
                        return [
                            row for row in store.list_annotation_summaries(
                                user_id=principal.user_id,
                            )
                            if not book_access_denied(
                                principal, row.get('book_hash')
                            )
                        ]

                    return response({'data': await run_db(_annotation_summaries)})
                if tail[:1] == ['batch']:
                    return response(
                        error_payload('batch_requires_post', 'Batch requires POST'),
                        400,
                    )
                if tail[:1] == ['item'] and len(tail) == 2:
                    def _get_annotation_item():
                        row = store.get_annotation(
                            tail[1], user_id=principal.user_id
                        )
                        forbidden = bool(
                            row and book_access_denied(principal, row.get('book_hash'))
                        )
                        return row, forbidden

                    row, forbidden = await run_db(_get_annotation_item)
                    if forbidden:
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
                if tail and await run_db(book_access_denied, principal, tail[0]):
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

                def _list_annotations():
                    rows = store.list_annotations(
                        book_hash=tail[0] if tail else None,
                        chapter_index=chapter_index,
                        user_id=principal.user_id,
                    )
                    if tail:
                        return rows
                    return [
                        row for row in rows
                        if not book_access_denied(
                            principal,
                            row.get('book_hash'),
                        )
                    ]

                return response({'data': await run_db(_list_annotations)})

            if request.method == 'DELETE':
                if len(tail) != 2 or tail[0] != 'item':
                    return response(error_payload('not_found', 'Not found'), 404)
                def _delete_annotation():
                    row = store.get_annotation(
                        tail[1], user_id=principal.user_id
                    )
                    if row and book_access_denied(principal, row.get('book_hash')):
                        return 'forbidden'
                    store.delete_annotation(tail[1], user_id=principal.user_id)
                    return 'deleted'

                if await run_db(_delete_annotation) == 'forbidden':
                    return forbidden_book_response()
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
                def _apply_annotations():
                    if path_book_id and book_access_denied(principal, path_book_id):
                        return 'forbidden', 0, 0
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
                            return 'forbidden', 0, 0
                        if stored and stored.get('book_hash') != entry_book_id:
                            return 'mismatch', 0, 0
                        if (
                            (path_book_id and entry_book_id != path_book_id)
                            or book_access_denied(principal, entry_book_id)
                        ):
                            return 'forbidden', 0, 0
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
                    return 'ok', created, failed

                outcome, created, failed = await run_db(_apply_annotations)
                if outcome == 'forbidden':
                    return forbidden_book_response()
                if outcome == 'mismatch':
                    return response(
                        error_payload(
                            'annotation_book_mismatch',
                            'Annotation cannot move between books',
                        ),
                        409,
                    )
                if tail == ['batch']:
                    return response({'created': created, 'failed': failed}, 201)
                if failed:
                    raise RuntimeError('annotation insert failed')
                return response({'data': data}, 201)

            if len(tail) != 2 or tail[0] != 'item':
                return response(error_payload('not_found', 'Not found'), 404)
            annotation_id = tail[1]

            def _update_annotation():
                stored = store.get_annotation(
                    annotation_id,
                    user_id=principal.user_id,
                )
                if stored and book_access_denied(
                    principal,
                    stored.get('book_hash'),
                ):
                    return 'forbidden', None
                if 'chapter_index' in data and (
                    isinstance(data['chapter_index'], bool)
                    or not isinstance(data['chapter_index'], int)
                    or data['chapter_index'] < 0
                ):
                    return 'invalid', None
                return 'ok', store.update_annotation(
                    annotation_id,
                    data,
                    user_id=principal.user_id,
                )

            outcome, row = await run_db(_update_annotation)
            if outcome == 'forbidden':
                return forbidden_book_response()
            if outcome == 'invalid':
                return response({'message': 'Invalid chapter index'}, 400)
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
            payload, status = await run_db(
                sync_bookshelf,
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

    def bookshelf_contains(book_hash, shelf):
        if not isinstance(shelf, dict):
            return False
        if book_hash in shelf.get("items", []):
            return True
        return any(
            bookshelf_contains(book_hash, group)
            for group in (shelf.get("groups") or {}).values()
        )

    async def bookshelf_membership(request):
        principal = require_principal(request)
        try:
            _version, shelf = await run_db(bookshelf_document, principal.user_id)
            return response({"in_shelf": bookshelf_contains(request.path_params["book_hash"], shelf)})
        except Exception:
            return response(error_payload('server_error', 'Internal server error'), 500)

    async def bookshelf(request):
        principal = require_principal(request)
        user_id = principal.user_id
        try:
            current_version, current_data = await run_db(bookshelf_document, user_id)
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
                await run_db(
                    store.create_bookshelf, user_id, next_version, proposed_data
                )
            else:
                await run_db(
                    store.update_bookshelf, user_id, next_version, proposed_data
                )
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

        if await run_db(book_access_denied, principal, book_hash):
            return forbidden_book_response()

        if request.method != 'GET' and not runtime_status.is_ready():
            return response(error_payload('not_ready', 'Server is not ready'), 503)

        if request.method == 'GET':
            chapter_index = await run_db(
                store.get_reading_progress, principal.user_id, book_hash
            )
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
            await run_db(
                store.set_reading_progress,
                principal.user_id,
                book_hash,
                chapter_index,
            )
            return response({'chapter_index': chapter_index})

        await run_db(store.delete_reading_progress, principal.user_id, book_hash)
        return response({'message': 'Deleted'})

    def recent_reading_limit(request):
        default_limit = store.get_general_settings().get(
            'recent_reading_limit', RECENT_READING_DEFAULT_LIMIT
        )
        raw = request.query_params.get('limit')
        if raw is None or raw == '':
            return default_limit
        try:
            requested = int(raw)
        except (TypeError, ValueError):
            return default_limit
        if requested < 1:
            return default_limit
        return min(requested, RECENT_READING_MAX_LIMIT)

    async def recent_reading(request):
        try:
            return await recent_reading_response(request)
        except StarletteHTTPException:
            # Authentication failures must keep their own status code instead
            # of collapsing into a generic 500.
            raise
        except Exception:
            return response(error_payload('server_error', 'Internal server error'), 500)

    async def recent_reading_response(request):
        """List the caller's most recently updated reading progress.

        Reading progress is runtime user data, never part of the EPUB or PDF
        content cache.  Stored rows can outlive their book: a book may have
        been removed, soft-deleted, or restricted after the row was written.
        Every row is therefore re-checked against the current visibility rules
        before it leaves the server, so the caller only ever learns about
        books it can already open.
        """
        principal = require_principal(request)

        def _recent_items():
            items = []
            for row in store.list_reading_progress(
                principal.user_id, limit=recent_reading_limit(request)
            ):
                book_id = row.get('book_id')
                if book_access_denied(principal, book_id):
                    continue
                items.append(
                    {
                        'book_id': book_id,
                        'chapter_index': row.get('chapter_index'),
                        'updated_at': row.get('updated_at'),
                    }
                )
            return items

        return response(
            {'items': await run_db(_recent_items)},
            cache_control='private, no-store',
        )

    chapter_snapshot_cache: OrderedDict = OrderedDict()
    chapter_snapshot_cache_ttl_seconds = 60.0
    chapter_snapshot_cache_max_entries = 1024

    def load_authorized_chapter_snapshot(book_id, chapter_index):
        """Return cache-derived labels only after the caller has book access.

        A lightweight projection: only book title and chapter label are read,
        never the rendered chapter markup.
        """
        book = store.book_by_id(book_id)
        if book is None:
            raise ServerPageError('Book content cache is invalid')
        renderer = ServerPageRenderer(
            base_directory,
            book_id,
            source_format=book.source_format,
            metadata_overrides=store.managed_book_metadata(book_id),
        )
        if book.source_format == PDF_FORMAT:
            _metadata, processor = renderer._pdf_renderer()
            if chapter_index >= len(processor.chapters):
                raise ValueError('chapter index is outside the book')
            chapter_label = processor.chapters[chapter_index].get('title')
            if (
                not isinstance(processor.book_title, str)
                or not processor.book_title.strip()
                or not isinstance(chapter_label, str)
                or not chapter_label.strip()
            ):
                raise ServerPageError('PDF metadata cache is invalid')
            return processor.book_title, chapter_label
        metadata = renderer._read_json(renderer.content_dir / 'metadata.json')
        if not isinstance(metadata, dict):
            raise ServerPageError('Book content cache is invalid')
        chapters = metadata.get('chapters')
        if not isinstance(chapters, list):
            raise ServerPageError('Book content cache is invalid')
        if not all(
            isinstance(chapter, dict)
            and isinstance(chapter.get('title'), str)
            and chapter['title'].strip()
            and isinstance(chapter.get('path'), str)
            and chapter['path'].strip()
            for chapter in chapters
        ):
            raise ServerPageError('Book content cache is invalid')
        if chapter_index >= len(chapters):
            raise ValueError('chapter index is outside the book')
        # metadata.chapters[index].title and chapter_<n>.json's title are the
        # same EPUB-derived value; no full render or chapter read is needed.
        book_title = store.managed_book_metadata(book_id).get('title')
        chapter_label = chapters[chapter_index]['title']
        if (
            not isinstance(book_title, str) or not book_title.strip()
            or not isinstance(chapter_label, str) or not chapter_label.strip()
        ):
            raise ServerPageError('Book content cache is invalid')
        return book_title, chapter_label

    def authorized_chapter_snapshot(book_id, chapter_index):
        """Return cache-derived labels, rate limited by an LRU with TTL."""
        key = (book_id, chapter_index)
        now = time.monotonic()
        cached = chapter_snapshot_cache.get(key)
        if cached is not None and now - cached[2] < chapter_snapshot_cache_ttl_seconds:
            chapter_snapshot_cache.move_to_end(key)
            return cached[0], cached[1]
        labels = load_authorized_chapter_snapshot(book_id, chapter_index)
        chapter_snapshot_cache[key] = (labels[0], labels[1], now)
        chapter_snapshot_cache.move_to_end(key)
        if len(chapter_snapshot_cache) > chapter_snapshot_cache_max_entries:
            chapter_snapshot_cache.popitem(last=False)
        return labels

    async def book_review(request):
        principal = require_principal(request)
        book_id = request.path_params['book_id']
        if not await run_db(
            store.can_read_book, principal.user_id, principal.role, book_id
        ):
            return forbidden_book_response()
        if request.method == 'GET':
            return response({
                'review': await run_db(
                    store.get_book_review, book_id, principal.user_id
                ),
            })
        if request.method == 'DELETE':
            if not runtime_status.is_ready():
                return response(error_payload('not_ready', 'Server is not ready'), 503)
            await run_db(store.delete_book_review, book_id, principal.user_id)
            return Response(status_code=204)

        if not runtime_status.is_ready():
            return response(error_payload('not_ready', 'Server is not ready'), 503)
        data, error = await bounded_public_json_object(request, maximum_size=4096)
        if error:
            return response(error_payload(error, 'Invalid book review'), 400)
        rating = data.get('rating')
        review_text = data.get('review_text')
        if (
            isinstance(rating, bool) or not isinstance(rating, int)
            or not 1 <= rating <= 5
            or not isinstance(review_text, str) or len(review_text.strip()) > 10_000
        ):
            return response(
                error_payload('invalid_book_review', 'Invalid book review'), 400
            )
        review = await run_db(
            store.upsert_book_review,
            book_id, principal.user_id, rating, review_text,
        )
        return response({'review': review})

    async def reading_session_heartbeat(request):
        principal = require_principal(request)
        book_id = request.path_params['book_id']
        if not await run_db(
            store.can_read_book, principal.user_id, principal.role, book_id
        ):
            return forbidden_book_response()
        if not runtime_status.is_ready():
            return response(error_payload('not_ready', 'Server is not ready'), 503)
        data, error = await bounded_public_json_object(request, maximum_size=4096)
        if error:
            return response(error_payload(error, 'Invalid reading session'), 400)
        client_id = data.get('client_id')
        client_sequence = data.get('client_sequence')
        chapter_index = data.get('chapter_index')
        active_seconds = data.get('active_seconds')
        if (
            not isinstance(client_id, str) or not 1 <= len(client_id) <= 128
            or isinstance(client_sequence, bool)
            or not isinstance(client_sequence, int) or client_sequence < 0
            or isinstance(chapter_index, bool)
            or not isinstance(chapter_index, int) or chapter_index < 0
            or isinstance(active_seconds, bool)
            or not isinstance(active_seconds, int) or not 1 <= active_seconds <= 20
        ):
            return response(
                error_payload('invalid_reading_session', 'Invalid reading session'),
                400,
            )
        if heartbeat_rate_limited(principal.user_id, client_id):
            return response(
                error_payload('reading_session_rate_limited', 'Reading session rate limited'),
                429,
            )
        try:
            book_title, chapter_label = await run_db(
                authorized_chapter_snapshot, book_id, chapter_index
            )
        except ServerPageError:
            return response(
                error_payload(
                    'reading_source_unavailable',
                    'Reading source is unavailable',
                ),
                503,
            )
        except ValueError:
            return response(
                error_payload('invalid_reading_session', 'Invalid reading session'),
                400,
            )
        session = await run_db(
            store.record_reading_heartbeat,
            user_id=principal.user_id,
            book_id=book_id,
            client_id=client_id,
            client_sequence=client_sequence,
            chapter_index=chapter_index,
            active_seconds=active_seconds,
            book_title=book_title,
            chapter_label=chapter_label,
            received_at=datetime.now(timezone.utc),
        )
        return response({'session': session})

    async def reading_session_summary(request):
        principal = require_principal(request)
        book_id = request.path_params['book_id']
        if not await run_db(
            store.can_read_book, principal.user_id, principal.role, book_id
        ):
            return forbidden_book_response()
        try:
            active_seconds = await run_db(
                store.reading_time_for_book, principal.user_id, book_id
            )
        except KeyError:
            return forbidden_book_response()
        return response({'active_seconds': active_seconds})

    async def reading_insights(request):
        principal = require_principal(request)
        query = parse_qs(request.url.query, keep_blank_values=True)
        if set(query) - {'period', 'anchor', 'timezone'}:
            return response(
                error_payload('invalid_reading_insights', 'Invalid reading insights'),
                400,
            )
        values = {
            key: query.get(key)
            for key in ('period', 'anchor', 'timezone')
        }
        if any(value is None or len(value) != 1 for value in values.values()):
            return response(
                error_payload('invalid_reading_insights', 'Invalid reading insights'),
                400,
            )
        period, anchor, timezone_name = (
            values['period'][0], values['anchor'][0], values['timezone'][0]
        )
        if period not in {'overview', 'day', 'week', 'month'} or not re.fullmatch(
            r'\d{4}-\d{2}-\d{2}', anchor
        ):
            return response(
                error_payload('invalid_reading_insights', 'Invalid reading insights'),
                400,
            )
        try:
            anchor_date = date.fromisoformat(anchor)
            ZoneInfo(timezone_name)
        except (TypeError, ValueError, ZoneInfoNotFoundError):
            return response(
                error_payload('invalid_reading_insights', 'Invalid reading insights'),
                400,
            )
        try:
            insights = await run_db(
                store.reading_insights,
                principal.user_id, period, anchor_date, timezone_name,
            )
        except (OverflowError, ValueError):
            return response(
                error_payload('invalid_reading_insights', 'Invalid reading insights'),
                400,
            )
        return response({'insights': insights})

    async def reading_insight_sessions(request):
        principal = require_principal(request)
        query = parse_qs(request.url.query, keep_blank_values=True)
        try:
            if set(query) - {'date', 'timezone', 'page'} or any(len(value) != 1 for value in query.values()):
                raise ValueError
            selected_date = query['date'][0]
            page = query.get('page', ['1'])[0]
            if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', selected_date) or not re.fullmatch(r'[1-9][0-9]{0,8}', page):
                raise ValueError
            result = await run_db(
                store.reading_insight_sessions,
                principal.user_id, date.fromisoformat(selected_date), query['timezone'][0], int(page),
            )
        except (KeyError, ValueError, OverflowError):
            return response(error_payload('invalid_reading_insights', 'Invalid reading insights'), 400)
        return response(result)

    async def book_reading_insights(request):
        principal = require_principal(request)
        book_id = request.path_params['book_id']
        if not await run_db(store.can_read_book, principal.user_id, principal.role, book_id):
            return forbidden_book_response()
        try:
            result = await run_db(store.book_reading_insights, principal.user_id, book_id)
        except KeyError:
            return forbidden_book_response()
        return response({'insights': result})

    def valid_webhook_configuration(data):
        if not isinstance(data, dict):
            return None
        name = data.get('name')
        url = data.get('url')
        event_types = data.get('event_types')
        enabled = data.get('enabled', True)
        parsed = urlsplit(url) if isinstance(url, str) else None
        if (
            not isinstance(name, str) or not 1 <= len(name.strip()) <= 80
            or parsed is None or parsed.scheme not in {'http', 'https'} or not parsed.netloc
            or not isinstance(event_types, list) or not event_types
            or any(not isinstance(item, str) for item in event_types)
            or not set(event_types) <= WEBHOOK_EVENT_TYPES
            or not isinstance(enabled, bool)
        ):
            return None
        return name.strip(), url, tuple(sorted(set(event_types))), enabled

    async def admin_webhooks(request):
        require_admin(request)
        if request.method == 'GET':
            items = await run_db(store.list_webhook_endpoints)
            return response({'items': items}, cache_control='private, no-store')
        data, error = await bounded_public_json_object(request, maximum_size=16 * 1024)
        configuration = valid_webhook_configuration(data) if not error else None
        if configuration is None:
            return response(error_payload('invalid_webhook', 'Invalid WebHook configuration'), 400, 'private, no-store')
        created = await run_db(
            store.create_webhook_endpoint,
            *configuration[:3],
            enabled=configuration[3],
        )
        return response(created, 201, 'private, no-store')

    async def admin_webhook(request):
        require_admin(request)
        endpoint_id = request.path_params['webhook_id']
        if request.method == 'GET':
            endpoint = await run_db(store.get_webhook_endpoint, endpoint_id)
            return response({'webhook': endpoint}, cache_control='private, no-store') if endpoint else response(error_payload('webhook_not_found', 'WebHook not found'), 404, 'private, no-store')
        if request.method == 'DELETE':
            deleted = await run_db(store.delete_webhook_endpoint, endpoint_id)
            return Response(status_code=204) if deleted else response(error_payload('webhook_not_found', 'WebHook not found'), 404, 'private, no-store')
        data, error = await bounded_public_json_object(request, maximum_size=16 * 1024)
        configuration = valid_webhook_configuration(data) if not error else None
        if configuration is None:
            return response(error_payload('invalid_webhook', 'Invalid WebHook configuration'), 400, 'private, no-store')
        endpoint = await run_db(
            store.update_webhook_endpoint,
            endpoint_id,
            name=configuration[0],
            url=configuration[1],
            event_types=configuration[2],
            enabled=configuration[3],
        )
        return response({'webhook': endpoint}, cache_control='private, no-store') if endpoint else response(error_payload('webhook_not_found', 'WebHook not found'), 404, 'private, no-store')

    async def admin_webhook_test(request):
        require_admin(request)
        try:
            queued = await run_db(
                store.enqueue_webhook_test, request.path_params['webhook_id']
            )
        except KeyError:
            return response(error_payload('webhook_not_found', 'WebHook not found'), 404, 'private, no-store')
        return response(queued, 202, 'private, no-store')

    async def admin_webhook_rotate(request):
        require_admin(request)
        secret = await run_db(
            store.rotate_webhook_secret, request.path_params['webhook_id']
        )
        return response({'secret': secret}, cache_control='private, no-store') if secret else response(error_payload('webhook_not_found', 'WebHook not found'), 404, 'private, no-store')

    async def admin_webhook_deliveries(request):
        require_admin(request)
        items = await run_db(store.list_webhook_deliveries)
        return response({'items': items}, cache_control='private, no-store')

    async def admin_webhook_redeliver(request):
        require_admin(request)
        data, error = await bounded_public_json_object(request, maximum_size=2048)
        endpoint_id = data.get('endpoint_id') if not error else None
        if not isinstance(endpoint_id, str):
            return response(error_payload('invalid_webhook_redelivery', 'Invalid WebHook redelivery'), 400, 'private, no-store')
        try:
            delivery_id = await run_db(
                store.redeliver_webhook_event,
                request.path_params['event_id'],
                endpoint_id,
            )
        except sqlite3.IntegrityError:
            return response(error_payload('webhook_event_not_found', 'WebHook event not found'), 404, 'private, no-store')
        return response({'delivery_id': delivery_id}, 202, 'private, no-store')

    public_api_context = PublicAPIContext(store=store, public_dir=Path(base_directory), book_cache=book_cache)
    routes = [
        Route('/setup', setup, methods=['GET', 'POST']),
        Route('/login', login, methods=['GET', 'POST']),
        Route('/logout', logout, methods=['POST']),
        Route('/auth/oidc/start', oidc_start, methods=['GET']),
        Route('/auth/oidc/callback', oidc_callback, methods=['GET']),
        Route('/auth/oidc/associate', oidc_associate, methods=['GET', 'POST']),
        Route('/sw.js', service_worker_tombstone, methods=['GET']),
        Route('/api/session', session, methods=['GET']),
        Route('/api/csrf', csrf, methods=['GET']),
        Route('/api/account/appearance', account_appearance, methods=['GET', 'PUT']),
        Route('/api/account/password', change_password, methods=['PUT']),
        Route('/api/account/sessions', list_own_sessions, methods=['GET']),
        Route('/api/account/sessions/{session_id}', revoke_own_session, methods=['DELETE']),
        Route('/api/account/pats', own_personal_access_tokens, methods=['GET', 'POST']),
        Route('/api/account/pats/{token_id}', revoke_own_personal_access_token, methods=['DELETE']),
        Route('/api/account/oidc/link', account_oidc_link, methods=['POST']),
        Route('/api/account/oidc/identity', account_oidc_identity, methods=['DELETE']),
        Route('/api/admin/oidc/settings', admin_oidc_settings, methods=['GET', 'PUT']),
        Route('/api/admin/users', admin_users, methods=['GET', 'POST']),
        Route(
            '/api/admin/users/{username}/deletion-impact',
            admin_user_deletion_impact,
            methods=['GET'],
        ),
        Route('/api/admin/users/{username}/password', admin_reset_password, methods=['PUT']),
        Route(
            '/api/admin/users/{username}/oidc/identity',
            admin_user_oidc_identity,
            methods=['DELETE'],
        ),
        Route('/api/admin/users/{username}', admin_user, methods=['PUT', 'DELETE']),
        Route('/api/admin/books', admin_books, methods=['GET']),
        Route('/api/admin/books/upload', admin_books_upload, methods=['POST']),
        Route('/api/admin/books/index', admin_book_index, methods=['GET']),
        Route('/api/admin/books/bulk', admin_bulk_books, methods=['POST']),
        Route(
            '/api/admin/books/{book_path:path}',
            admin_book_request,
            methods=['GET', 'PUT', 'DELETE'],
        ),
        Route('/api/admin/ai/settings', admin_ai_settings, methods=['GET', 'PUT']),
        Route('/api/admin/general-settings', admin_general_settings, methods=['GET', 'PUT']),
        Route('/api/admin/ai/users/{user_id}', admin_ai_user_access, methods=['GET', 'PUT']),
        Route('/api/admin/ai/tags', admin_ai_tags, methods=['GET', 'POST']),
        Route('/api/admin/ai/tags/{tag_id}', admin_ai_tag, methods=['PUT', 'DELETE']),
        Route('/api/admin/ai/results', admin_ai_results, methods=['DELETE']),
        Route('/api/admin/ai/jobs', admin_ai_jobs, methods=['GET']),
        Route('/api/admin/ai/jobs/{job_id:path}/retry', admin_ai_job_retry, methods=['POST']),
        Route('/api/admin/dictionaries', admin_dictionaries, methods=['GET', 'POST']),
        Route('/api/admin/dictionaries/{dictionary_id}/resources', admin_dictionary_resources, methods=['POST']),
        Route('/api/admin/dictionaries/{dictionary_id}/default', admin_dictionary_default, methods=['PUT']),
        Route('/api/admin/dictionaries/{dictionary_id}', admin_dictionary, methods=['PUT', 'DELETE']),
        Route('/api/admin/webhooks', admin_webhooks, methods=['GET', 'POST']),
        Route('/api/admin/webhooks/deliveries', admin_webhook_deliveries, methods=['GET']),
        Route('/api/admin/webhooks/events/{event_id}/redeliver', admin_webhook_redeliver, methods=['POST']),
        Route('/api/admin/webhooks/{webhook_id}/test', admin_webhook_test, methods=['POST']),
        Route('/api/admin/webhooks/{webhook_id}/rotate-secret', admin_webhook_rotate, methods=['POST']),
        Route('/api/admin/webhooks/{webhook_id}', admin_webhook, methods=['GET', 'PUT', 'DELETE']),
        Route('/api/books/{book_id}/dictionaries', dictionary_choices, methods=['GET']),
        Route(
            '/api/books/{book_id}/document',
            pdf_document,
            methods=[
                'GET', 'HEAD', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS', 'TRACE',
            ],
        ),
        *public_api_routes(public_api_context),
        Route('/', library_index),
        Route('/index.html', library_index),
        *(
            [
                Route('/kindle', kindle_entry),
                Route('/kindle/screensaver', kindle_screensaver),
                Route('/api/kindle/screensaver/memo', kindle_screensaver_memo),
                Route('/api/kindle/screensaver/timezone', kindle_screensaver_timezone),
                Route('/api/kindle/screensaver/calendar', kindle_screensaver_calendar),
                Route('/api/account/kindle-screensaver', kindle_screensaver_preferences, methods=['GET', 'PUT']),
                Route(
                    '/kindle-library.html',
                    kindle_library_page,
                    methods=['GET'],
                )
            ]
            if kindle
            else []
        ),
        Route('/reading-insights', reading_insights_page, methods=['GET']),
        Route('/book-metadata.json', filtered_library_metadata, methods=['GET']),
        Route('/openapi.json', openapi_schema, methods=['GET']),
        Route('/api-docs', api_docs, methods=['GET']),
        Route('/api/health', health),
        Route('/api/ready', ready),
        Route('/api/version', version_status),
        Route('/api/library-events', library_events),
        Route('/api/bookshelf/{book_hash}/membership', bookshelf_membership, methods=['GET']),
        Route('/api/bookshelf', bookshelf, methods=['GET', 'PUT']),
        Route('/api/library-metadata', filtered_library_metadata, methods=['GET']),
        Route('/api/library-order', save_library_order, methods=['PUT']),
        Route('/api/reading-progress/{book_hash}', reading_progress, methods=['GET', 'PUT', 'DELETE']),
        Route('/api/reading-progress', recent_reading, methods=['GET']),
        Route('/api/book-reviews/{book_id}', book_review, methods=['GET', 'PUT', 'DELETE']),
        Route('/api/reading-sessions/{book_id}/summary', reading_session_summary, methods=['GET']),
        Route('/api/reading-sessions/{book_id}/heartbeat', reading_session_heartbeat, methods=['POST']),
        Route('/api/reading-insights', reading_insights, methods=['GET']),
        Route('/api/reading-insights/sessions', reading_insight_sessions, methods=['GET']),
        Route('/api/books/{book_id}/insights', book_reading_insights, methods=['GET']),
        Route('/api/ai/status', ai_status, methods=['GET']),
        Route('/api/books/{book_id}/metadata', book_effective_metadata, methods=['GET']),
        Route('/api/vocabulary', vocabulary, methods=['GET']),
        Route('/api/vocabulary/{word_id}', vocabulary, methods=['PATCH', 'DELETE']),
        Route('/api/books/{book_id}/dictionary/lookup', dictionary_lookup, methods=['POST']),
        Route('/api/books/{book_id}/dictionaries/{dictionary_id}/assets/{asset_path:path}', dictionary_asset, methods=['GET']),
        Route('/api/books/{book_id}/dictionaries/{dictionary_id}/resources/{media_id}', dictionary_media, methods=['GET']),
        Route('/api/books/{book_id}/encyclopedia/lookup', encyclopedia_lookup, methods=['POST']),
        Route('/api/ai/reading', ai_reading_request, methods=['POST']),
        Route('/api/ai/library', ai_reading_library, methods=['GET']),
        Route('/api/ai/books/{book_id}/results', ai_book_results, methods=['GET']),
        Route('/api/ai/books/{book_id}/chat', ai_book_chat, methods=['GET', 'POST']),
        Route('/api/ai/jobs/{job_id}', ai_job, methods=['GET']),
        Route('/api/ai/results/{result_id}', ai_result, methods=['GET', 'DELETE']),
        Route('/api/ai/events', ai_events, methods=['GET']),
        Route('/api/ai/followups', ai_followups, methods=['POST']),
        Route('/api/ai/results/{result_id}/followups', ai_followups, methods=['GET']),
        Route('/api/{path:path}', annotations, methods=['GET', 'POST', 'PUT', 'DELETE']),
        Route('/sync', sync, methods=['POST']),
        Route('/{path:path}', protected_public_file, methods=['GET']),
    ]
    @asynccontextmanager
    async def ai_worker_lifespan(application):
        """Keep the AI worker lifecycle aligned with the ASGI application."""
        setup_monitor_task = asyncio.create_task(setup_state.run())
        try:
            await ai_reading.start_worker()
            await webhook_service.start_worker()
            ai_reading.wake_worker()
            yield
        finally:
            setup_monitor_task.cancel()
            try:
                await setup_monitor_task
            except asyncio.CancelledError:
                pass
            await webhook_service.stop_worker()
            await ai_reading.stop_worker()
            await oidc_service.aclose()

    app = Starlette(
        routes=routes,
        exception_handlers={
            StarletteHTTPException: http_exception,
            Exception: server_error,
        },
        lifespan=ai_worker_lifespan,
    )
    setattr(app.state, PUBLIC_API_CONTEXT_KEY, public_api_context)

    async def auth_middleware(request, call_next):
        path = request.url.path
        if await setup_state.setup_required():
            if (
                path in PUBLIC_PRE_SETUP_ENDPOINTS
                or is_public_unauthenticated_asset(path)
                or path in PUBLIC_WEB_MANIFESTS
            ):
                return await call_next(request)
            return setup_required_response(request)
        if (
            path in PUBLIC_STATELESS_ENDPOINTS
            or is_public_unauthenticated_asset(path)
            or path in PUBLIC_WEB_MANIFESTS
        ):
            return await call_next(request)
        if path.startswith('/api/v1/'):
            authorized = await call_next(request)
            authorized.headers['Cache-Control'] = 'private, no-store'
            return authorized
        raw_session = request.cookies.get(SESSION_COOKIE)
        # Session validation touches SQLite; keep it off the ASGI loop so a
        # burst of asset requests cannot serialize on one write transaction.
        session_principal = await asyncio.to_thread(
            auth_service.principal_from_session, raw_session
        )
        principal = session_principal
        request.scope[PRINCIPAL_SCOPE_KEY] = principal
        request.scope[SESSION_TOKEN_SCOPE_KEY] = raw_session
        if principal is None:
            if (
                route_is_public_unauthenticated(path)
                or is_public_unauthenticated_asset(path)
            ):
                return await call_next(request)
            return unauthenticated_response(request)
        if (
            request.method not in SAFE_METHODS
            and not authenticated_login_retry(request)
        ):
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
            new_proxy_session, _ = await run_db(
                auth_service.create_session,
                principal,
                **session_client_metadata(request),
            )
            request.scope[SESSION_TOKEN_SCOPE_KEY] = new_proxy_session
        authorized = await call_next(request)
        if new_proxy_session is not None:
            set_session_cookie(authorized, new_proxy_session)
        if path.startswith('/auth/oidc/'):
            authorized.headers['Cache-Control'] = 'no-store'
            return authorized
        if path.startswith('/assets/immutable/'):
            # Content-addressed assets are immutable; authentication must not
            # downgrade the long-lived cache policy set by the static file
            # adapter, or browsers would revalidate every asset on each load.
            return authorized
        # Lookup text is sensitive reading data.  Its handlers deliberately
        # request no-store; preserve that stronger policy instead of replacing
        # it with the authenticated page default.
        if authorized.headers.get('Cache-Control') != 'private, no-store':
            authorized.headers['Cache-Control'] = 'private, no-cache'
        return authorized

    app.add_middleware(
        GZipMiddleware,
        minimum_size=500,
        compresslevel=6,
    )
    app.add_middleware(BaseHTTPMiddleware, dispatch=auth_middleware)

    if library_manager is not None:
        app.add_middleware(BookCacheLeaseMiddleware)

    return app
