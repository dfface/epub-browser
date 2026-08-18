import os
import json
import glob
import sqlite3
from starlette.applications import Starlette
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import FileResponse, JSONResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from .state import StateStore

DATABASE_FILENAME = 'epub-browser.db'
LEGACY_DATABASE_FILENAME = 'annotations.db'


def error_payload(code, message):
    return {'code': code, 'message': message}


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
    username,
    client_version,
    client_data,
    store=None,
):
    """Synchronize one bookshelf document and return its response payload and status."""
    active_store = store or StateStore(database_path)
    if store is None:
        active_store.initialize()
    row = active_store.get_bookshelf(username)
    if row is None:
        legacy = load_legacy_bookshelf(legacy_directory, username)
        if legacy is not None:
            legacy_version, legacy_data = legacy
            active_store.create_bookshelf(username, legacy_version, legacy_data)
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
        active_store.create_bookshelf(username, new_version, client_data)
        return {'message': 'New user created', 'version': new_version}, 404

    active_store.update_bookshelf(username, new_version, client_data)
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


def create_app(public_dir, state_store=None, status=None, sync_dir=None):
    """Create the ASGI module used by Uvicorn to serve an EPUB library."""
    base_directory = os.path.abspath(public_dir)
    if state_store is None:
        database = migrate_legacy_database(base_directory)
        store = StateStore(
            database,
            connection_factory=lambda path: sqlite3.connect(path),
        )
        store.initialize()
    else:
        store = state_store
    runtime_status = status or _CompatibilityRuntimeStatus()

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

    def response(data, status=200):
        return JSONResponse(data, status_code=status, headers={'Cache-Control': 'no-cache'})

    async def http_exception(request, exc):
        code = 'not_found' if exc.status_code == 404 else 'server_error'
        message = exc.detail if isinstance(exc.detail, str) else 'Internal server error'
        return response(error_payload(code, message), exc.status_code)

    def row_data(row):
        data = dict(row)
        for key, target in [('start_meta', 'startMeta'), ('end_meta', 'endMeta')]:
            data[target] = json.loads(data[key]) if data.get(key) else None
        return data

    async def annotations(request):
        parts = [part for part in request.path_params['path'].split('/') if part]
        if not parts or parts[0] != 'annotations':
            return response(error_payload('not_found', 'Not found'), 404)
        username = request.headers.get('X-Username', '').strip()
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
                    row = store.get_annotation(tail[1], username=username)
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
                    username=username,
                )
                return response({'data': rows})

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
                            username=username,
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
            if request.method == 'DELETE':
                store.delete_annotation(annotation_id, username=username)
                return response({'message': 'Deleted'})
            if 'chapter_index' in data and (
                isinstance(data['chapter_index'], bool)
                or not isinstance(data['chapter_index'], int)
                or data['chapter_index'] < 0
            ):
                return response({'message': 'Invalid chapter index'}, 400)
            row = store.update_annotation(
                annotation_id,
                data,
                username=username,
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
        if not runtime_status.is_ready():
            return response(error_payload('not_ready', 'Server is not ready'), 503)
        try:
            data = await request.json()
            username, version, shelf = data.get('username', ''), data.get('version', 1), data.get('data')
            if not username: return response(error_payload('username_required', 'Username is required'), 400)
            payload, status = sync_bookshelf(
                database_path(base_directory), sync_dir or base_directory,
                username, version, shelf, store=store,
            )
            if status == 400:
                return response(error_payload('no_sync_data', payload['message']), status)
            return response(payload, status)
        except json.JSONDecodeError: return response(error_payload('invalid_json', 'Invalid JSON data'), 400)
        except Exception: return response(error_payload('server_error', 'Internal server error'), 500)

    async def reading_progress(request):
        try:
            return await reading_progress_response(request)
        except Exception:
            return response(error_payload('server_error', 'Internal server error'), 500)

    async def reading_progress_response(request):
        book_hash = request.path_params['book_hash']
        username = request.headers.get('X-Username', '')

        if request.method != 'GET' and not runtime_status.is_ready():
            return response(error_payload('not_ready', 'Server is not ready'), 503)

        if request.method == 'GET':
            chapter_index = store.get_reading_progress(username, book_hash)
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
            store.set_reading_progress(username, book_hash, chapter_index)
            return response({'chapter_index': chapter_index})

        store.delete_reading_progress(username, book_hash)
        return response({'message': 'Deleted'})

    routes = [
        Route('/', library_index),
        Route('/index.html', library_index),
        Route('/api/health', health),
        Route('/api/ready', ready),
        Route('/api/reading-progress/{book_hash}', reading_progress, methods=['GET', 'PUT', 'DELETE']),
        Route('/api/{path:path}', annotations, methods=['GET', 'POST', 'PUT', 'DELETE']),
        Route('/sync', sync, methods=['POST']),
        Mount('/', app=CachedStaticFiles(directory=base_directory, html=False)),
    ]
    return Starlette(routes=routes, exception_handlers={StarletteHTTPException: http_exception})
