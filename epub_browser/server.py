import asyncio
import html
import json
import glob
import os
import sqlite3
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
    StreamingResponse,
)
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from .auth import (
    AuthService,
    Principal,
    SESSION_COOKIE,
    hash_password,
    session_cookie_options,
)
from .state import StateStore
from .library_progress import LibraryProgressBroker

DATABASE_FILENAME = 'epub-browser.db'
LEGACY_DATABASE_FILENAME = 'annotations.db'
PRINCIPAL_SCOPE_KEY = 'epub_browser.principal'
PENDING_IDENTITY_SCOPE_KEY = 'epub_browser.pending_identity'
SESSION_TOKEN_SCOPE_KEY = 'epub_browser.session_token'
SAFE_METHODS = frozenset({'GET', 'HEAD', 'OPTIONS', 'TRACE'})
PUBLIC_AUTH_ENDPOINTS = frozenset({
    '/login',
    '/logout',
    '/api/identity/link',
})
PUBLIC_LOGIN_ASSETS = frozenset({'/assets/auth.js'})


def error_payload(code, message):
    return {'code': code, 'message': message}


def route_is_public_auth_endpoint(path):
    return path in PUBLIC_AUTH_ENDPOINTS or path in PUBLIC_LOGIN_ASSETS


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


def load_legacy_bookshelf(directory, username):
    """Return the newest readable legacy bookshelf JSON record, if any."""
    pattern = os.path.join(directory, 'epub-browser-bookshelf-' + username + '-*.json')
    records = []
    for filename in glob.glob(pattern):
        try:
            version = int(os.path.basename(filename).rsplit('-', 1)[1][:-5])
            with open(filename, encoding='utf-8') as source:
                records.append((version, json.load(source)))
        except (IndexError, ValueError, OSError, json.JSONDecodeError):
            continue
    return max(records, key=lambda record: record[0]) if records else None


def sync_bookshelf(
    database_path,
    legacy_directory,
    user_id,
    client_version,
    client_data,
    store=None,
    legacy_username=None,
):
    """Synchronize one bookshelf document and return its response payload and status."""
    active_store = store or StateStore(database_path)
    if store is None:
        active_store.initialize()
    row = active_store.get_bookshelf(user_id)
    if row is None:
        legacy = load_legacy_bookshelf(legacy_directory, legacy_username or '')
        if legacy is not None:
            legacy_version, legacy_data = legacy
            active_store.create_bookshelf(user_id, legacy_version, legacy_data)
            row = (
                legacy_version,
                json.dumps(legacy_data, ensure_ascii=False),
            )

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

    def response(data, status=200, cache_control='no-cache'):
        return JSONResponse(
            data,
            status_code=status,
            headers={'Cache-Control': cache_control},
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

    async def json_object(request):
        try:
            data = await request.json()
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None
        return data if isinstance(data, dict) else None

    def user_data(user):
        return {
            'id': user.user_id,
            'username': user.username,
            'role': user.role,
            'enabled': user.enabled,
        }

    def session_data(record, current_session_id):
        return {
            'id': record.session_id,
            'created_at': record.created_at,
            'last_used_at': record.last_used_at,
            'expires_at': record.expires_at,
            'current': record.session_id == current_session_id,
        }

    def client_key(request):
        return request.client.host if request.client is not None else 'unknown'

    def login_form(next_path='/', error=None, status_code=200):
        safe_next = html.escape(_safe_relative_path(next_path), quote=True)
        error_markup = (
            '<p role="alert">Invalid username or password.</p>' if error else ''
        )
        markup = (
            '<!doctype html><html><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>Sign in · EPUB Browser</title></head><body>'
            '<main><h1>Sign in</h1>'
            + error_markup
            + '<form id="loginForm" method="post" action="/login">'
            '<input type="hidden" name="next" value="'
            + safe_next
            + '"><label>Username <input name="username" autocomplete="username" '
            'required></label><label>Password <input name="password" type="password" '
            'autocomplete="current-password" required></label>'
            '<button type="submit">Sign in</button></form></main></body></html>'
        )
        return HTMLResponse(
            markup,
            status_code=status_code,
            headers={'Cache-Control': 'no-store'},
        )

    async def login(request):
        requested_next = _safe_relative_path(request.query_params.get('next', '/'))
        if request.method == 'GET':
            if request.scope.get(PRINCIPAL_SCOPE_KEY) is not None:
                return RedirectResponse(requested_next, status_code=303)
            return login_form(requested_next)

        try:
            content_type = request.headers.get('content-type', '').split(';', 1)[0]
            if content_type != 'application/x-www-form-urlencoded':
                raise ValueError('Unsupported login form content type')
            body = await request.body()
            if len(body) > 64 * 1024:
                raise ValueError('Login form is too large')
            values = parse_qs(
                body.decode('utf-8'),
                keep_blank_values=True,
                strict_parsing=False,
            )
            form = {
                key: entries[-1] if entries else ''
                for key, entries in values.items()
            }
        except (UnicodeDecodeError, ValueError):
            return login_form(requested_next, error=True, status_code=400)
        next_path = _safe_relative_path(form.get('next') or requested_next)
        client_key = request.client.host if request.client is not None else 'unknown'
        principal = auth_service.authenticate_password(
            form.get('username', ''),
            form.get('password', ''),
            client_key,
        )
        if principal is None:
            return login_form(next_path, error=True, status_code=401)

        raw_session, _ = auth_service.create_session(principal)
        redirect = RedirectResponse(
            next_path,
            status_code=303,
            headers={'Cache-Control': 'no-store'},
        )
        set_session_cookie(redirect, raw_session)
        return redirect

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
        data = await json_object(request)
        if data is None:
            return response(
                error_payload('invalid_json', 'Invalid JSON data'),
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
        raw_session, _ = auth_service.create_session(principal)
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

    async def library_index(request):
        index_path = os.path.join(base_directory, 'index.html')
        if not os.path.isfile(index_path):
            return response(error_payload('not_found', 'Library index not found'), 404)
        response = FileResponse(index_path, media_type='text/html')
        response.headers['Cache-Control'] = 'no-cache'
        return response

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
                return response({'data': rows})

            if request.method == 'DELETE':
                if len(tail) != 2 or tail[0] != 'item':
                    return response(error_payload('not_found', 'Not found'), 404)
                store.delete_annotation(tail[1], user_id=principal.user_id)
                return response({'message': 'Deleted'})
            try:
                data = await request.json()
            except json.JSONDecodeError:
                return response(error_payload('invalid_json', 'Invalid JSON data'), 400)

            if request.method == 'POST':
                entries = data.get('annotations', []) if tail == ['batch'] else [data]
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
                database_path(base_directory), sync_dir or base_directory,
                principal.user_id, version, shelf, store=store,
                legacy_username=principal.username,
            )
            if status == 400:
                return response(error_payload('no_sync_data', payload['message']), status)
            return response(payload, status)
        except json.JSONDecodeError: return response(error_payload('invalid_json', 'Invalid JSON data'), 400)
        except Exception: return response(error_payload('server_error', 'Internal server error'), 500)

    def bookshelf_document(username):
        row = store.get_bookshelf(username)
        if row is None:
            legacy = load_legacy_bookshelf(sync_dir or base_directory, username)
            if legacy is not None:
                version, data = legacy
                store.create_bookshelf(username, version, data)
                return version, data
            return 0, {"items": [], "groups": {}, "order": []}
        version, serialized = row
        return version, json.loads(serialized)

    async def bookshelf(request):
        username = request.headers.get('X-Username', '').strip()
        if not username:
            return response(error_payload('username_required', 'Username is required'), 400)
        try:
            current_version, current_data = bookshelf_document(username)
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
                store.create_bookshelf(username, next_version, proposed_data)
            else:
                store.update_bookshelf(username, next_version, proposed_data)
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
        Route('/login', login, methods=['GET', 'POST']),
        Route('/logout', logout, methods=['POST']),
        Route('/api/identity/link', link_proxy_identity, methods=['POST']),
        Route('/api/session', session, methods=['GET']),
        Route('/api/csrf', csrf, methods=['GET']),
        Route('/api/account/password', change_password, methods=['PUT']),
        Route('/api/account/sessions', list_own_sessions, methods=['GET']),
        Route('/api/account/sessions/{session_id}', revoke_own_session, methods=['DELETE']),
        Route('/api/admin/users', admin_users, methods=['GET', 'POST']),
        Route('/api/admin/users/{username}/password', admin_reset_password, methods=['PUT']),
        Route('/api/admin/users/{username}', admin_user, methods=['PUT']),
        Route('/', library_index),
        Route('/index.html', library_index),
        Route('/api/health', health),
        Route('/api/ready', ready),
        Route('/api/library-events', library_events),
        Route('/api/bookshelf', bookshelf, methods=['GET', 'PUT']),
        Route('/api/reading-progress/{book_hash}', reading_progress, methods=['GET', 'PUT', 'DELETE']),
        Route('/api/{path:path}', annotations, methods=['GET', 'POST', 'PUT', 'DELETE']),
        Route('/sync', sync, methods=['POST']),
        Mount('/', app=CachedStaticFiles(directory=base_directory, html=False)),
    ]
    app = Starlette(
        routes=routes,
        exception_handlers={
            StarletteHTTPException: http_exception,
            Exception: server_error,
        },
    )

    async def auth_middleware(request, call_next):
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
        path = request.url.path
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
            new_proxy_session, _ = auth_service.create_session(principal)
            request.scope[SESSION_TOKEN_SCOPE_KEY] = new_proxy_session
        authorized = await call_next(request)
        if new_proxy_session is not None:
            set_session_cookie(authorized, new_proxy_session)
        authorized.headers['Cache-Control'] = 'private, no-cache'
        return authorized

    app.add_middleware(BaseHTTPMiddleware, dispatch=auth_middleware)
    return app
