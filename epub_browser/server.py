import os
import webbrowser
import socket
import threading
import mimetypes
import json
import glob
import sqlite3
from socketserver import ThreadingMixIn
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse
import errno
from starlette.applications import Starlette
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import FileResponse, JSONResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles
import uvicorn

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


def create_app(base_directory, sync_dir=None, state_store=None):
    """Create the ASGI module used by Uvicorn to serve an EPUB library."""
    global DATABASE_PATH
    base_directory = os.path.abspath(base_directory)
    database = migrate_legacy_database(base_directory)
    store = state_store or StateStore(
        database,
        connection_factory=lambda path: sqlite3.connect(path),
    )
    store.initialize()
    # The legacy HTTPRequestHandler still reads this compatibility pointer.
    # Starlette handlers above use their injected store and remain isolated.
    DATABASE_PATH = os.fspath(store.database_path)

    async def library_index(request):
        index_path = os.path.join(base_directory, 'index.html')
        if not os.path.isfile(index_path):
            return response(error_payload('not_found', 'Library index not found'), 404)
        response = FileResponse(index_path, media_type='text/html')
        response.headers['Cache-Control'] = 'no-cache'
        return response

    async def health(request):
        return JSONResponse({'status': 'ok'}, headers={'Cache-Control': 'no-cache'})

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
        Route('/api/reading-progress/{book_hash}', reading_progress, methods=['GET', 'PUT', 'DELETE']),
        Route('/api/{path:path}', annotations, methods=['GET', 'POST', 'PUT', 'DELETE']),
        Route('/sync', sync, methods=['POST']),
        Mount('/', app=CachedStaticFiles(directory=base_directory, html=False)),
    ]
    return Starlette(routes=routes, exception_handlers={StarletteHTTPException: http_exception})

# Shared server database path
DATABASE_PATH = None

def init_annotation_db(base_dir):
    """Initialize the legacy handler's shared database through StateStore."""
    global DATABASE_PATH
    DATABASE_PATH = migrate_legacy_database(base_dir)
    StateStore(
        DATABASE_PATH,
        connection_factory=lambda path: sqlite3.connect(path),
    ).initialize()
class StoppableThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """可停止的多线程HTTP服务器"""
    daemon_threads = True
    thread_name_prefix = "epub_server_"
    
    def __init__(self, server_address, RequestHandlerClass):
        super().__init__(server_address, RequestHandlerClass)
        self._is_shutting_down = False
    
    def shutdown(self):
        """优雅地关闭服务器"""
        self._is_shutting_down = True
        super().shutdown()
    
    def serve_forever(self, poll_interval=0.5):
        """重写serve_forever以支持优雅关闭"""
        while not self._is_shutting_down:
            try:
                self.handle_request()
            except Exception as e:
                if not self._is_shutting_down:
                    print(f"Server error: {e}")
        self.server_close()


class EPUBHTTPRequestHandler(SimpleHTTPRequestHandler):
    """自定义HTTP请求处理器"""
    
    def __init__(self, *args, base_directory, enableLog, sync_dir, **kwargs):
        self.enableLog = enableLog
        self.base_directory = base_directory
        self.sync_dir = sync_dir
        super().__init__(*args, directory=self.base_directory, **kwargs)
    
    def handle_one_request(self):
        """重写handle_one_request以处理连接重置"""
        try:
            return super().handle_one_request()
        except ConnectionResetError:
            # 客户端在读取请求时断开连接，安全忽略
            self.log_message("Client reset connection during request reading")
        except BrokenPipeError:
            # 客户端在写入响应时断开连接，安全忽略
            self.log_message("Client broke pipe during response writing")

    def send_error(self, code, message=None, explain=None):
        message = message or self.responses.get(code, ('Unknown error',))[0]
        error_code = 'not_found' if code == 404 else 'server_error'
        self.send_json_error(code, error_code, message)
        
    def do_GET(self):
        """处理GET请求"""
        try:
            # 检查服务器是否正在关闭
            if getattr(self.server, '_is_shutting_down', False):
                self.send_json_error(503, 'server_error', 'Server is shutting down')
                return
                
            parsed_path = urlparse(self.path)
            path = parsed_path.path

            if path == '/' or path == '/index.html':
                self.send_library_index()
                return
            
            if path.startswith('/book/'):
                self.serve_book(path)
                return
            
            # Annotation API routes
            if path.startswith('/api/'):
                # Health check endpoint (pure health check, no user coupling)
                if path == '/api/health':
                    self.send_json_response(200, {"status": "ok"})
                    return
                
                self.handle_annotation_api('GET', path)
                return
            
            super().do_GET()
            
        except (BrokenPipeError, ConnectionResetError):
            # 客户端断开连接，安全忽略
            pass
        except Exception as e:
            self.log_message(f"Unexpected error in do_GET: {e}")
            try:
                self.send_json_error(500, 'server_error', 'Internal server error')
            except (BrokenPipeError, ConnectionResetError):
                pass
    
    def do_POST(self):
        """处理POST请求"""
        try:
            if getattr(self.server, '_is_shutting_down', False):
                self.send_json_error(503, 'server_error', 'Server is shutting down')
                return
            
            parsed_path = urlparse(self.path)
            path = parsed_path.path
            
            # Annotation API routes
            if path.startswith('/api/'):
                self.handle_annotation_api('POST', path)
                return
            
            if path == '/sync':
                self.handle_sync_request()
                return
            
            self.send_json_error(404, 'not_found', 'Not Found')
            
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as e:
            self.log_message(f"Unexpected error in do_POST: {e}")
            try:
                self.send_json_error(500, 'server_error', 'Internal server error')
            except (BrokenPipeError, ConnectionResetError):
                pass
    
    def do_PUT(self):
        """处理PUT请求"""
        try:
            if getattr(self.server, '_is_shutting_down', False):
                self.send_json_error(503, 'server_error', 'Server is shutting down')
                return
            
            parsed_path = urlparse(self.path)
            path = parsed_path.path
            
            if path.startswith('/api/'):
                self.handle_annotation_api('PUT', path)
                return
            
            self.send_json_error(404, 'not_found', 'Not Found')
            
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as e:
            self.log_message(f"Unexpected error in do_PUT: {e}")
            try:
                self.send_json_error(500, 'server_error', 'Internal server error')
            except (BrokenPipeError, ConnectionResetError):
                pass
    
    def do_DELETE(self):
        """处理DELETE请求"""
        try:
            if getattr(self.server, '_is_shutting_down', False):
                self.send_json_error(503, 'server_error', 'Server is shutting down')
                return
            
            parsed_path = urlparse(self.path)
            path = parsed_path.path
            
            if path.startswith('/api/'):
                self.handle_annotation_api('DELETE', path)
                return
            
            self.send_json_error(404, 'not_found', 'Not Found')
            
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as e:
            self.log_message(f"Unexpected error in do_DELETE: {e}")
            try:
                self.send_json_error(500, 'server_error', 'Internal server error')
            except (BrokenPipeError, ConnectionResetError):
                pass
    
    def handle_sync_request(self):
        """处理书架同步请求"""
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length)
            data = json.loads(body.decode('utf-8'))
            
            username = data.get('username', '')
            client_version = data.get('version', 1)
            client_data = data.get('data')
            
            if not username:
                self.send_json_response(400, error_payload('username_required', 'Username is required'))
                return
            
            payload, status = sync_bookshelf(
                database_path(self.base_directory),
                self.sync_dir or self.base_directory,
                username, client_version, client_data,
            )
            if status == 400:
                self.send_json_response(status, error_payload('no_sync_data', payload['message']))
            else:
                self.send_json_response(status, payload)
            
        except json.JSONDecodeError:
            self.send_json_response(400, error_payload('invalid_json', 'Invalid JSON data'))
        except Exception as e:
            self.log_message(f"Error handling sync request: {e}")
            self.send_json_response(500, error_payload('server_error', 'Internal server error'))
    
    def send_json_response(self, code, data):
        """发送JSON响应"""
        try:
            response = json.dumps(data, ensure_ascii=False).encode('utf-8')
            self.send_response(code)
            self.send_header('Content-type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(response)))
            self.send_header('Cache-Control', 'no-cache')
            self.end_headers()
            self.wfile.write(response)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def send_json_error(self, status, code, message):
        self.send_json_response(status, error_payload(code, message))
    
    def _get_username(self):
        """从请求头中提取用户名"""
        return self.headers.get('X-Username', '').strip()
    
    def handle_annotation_api(self, method, path):
        """Handle annotation API requests"""
        try:
            # Parse path
            # /api/annotations - all annotations
            # /api/annotations/{book_hash} - book annotations
            # /api/annotations/{book_hash}/{chapter_index} - chapter annotations
            # /api/annotations/{id} - single annotation
            # /api/annotations/batch - batch operation
            
            parts = path.split('/')
            # parts = ['', 'api', 'annotations', ...]
            
            if len(parts) < 3 or parts[2] != 'annotations':
                self.send_json_response(404, error_payload('not_found', 'Not found'))
                return
            
            if not DATABASE_PATH:
                self.send_json_response(503, error_payload('database_unavailable', 'Database not initialized'))
                return
            
            conn = sqlite3.connect(DATABASE_PATH)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            try:
                # GET 请求
                if method == 'GET':
                    self._handle_annotation_get(cursor, parts)
                
                # POST 请求
                elif method == 'POST':
                    self._handle_annotation_post(cursor, parts, conn)
                
                # PUT 请求
                elif method == 'PUT':
                    self._handle_annotation_put(cursor, parts, conn)
                
                # DELETE 请求
                elif method == 'DELETE':
                    self._handle_annotation_delete(cursor, parts, conn)
                
            finally:
                conn.close()
                
        except json.JSONDecodeError:
            self.send_json_response(400, error_payload('invalid_json', 'Invalid JSON data'))
        except Exception as e:
            self.log_message(f"Error handling annotation API: {e}")
            self.send_json_response(500, error_payload('server_error', 'Internal server error'))
    
    def _parse_row_meta(self, row_dict):
        """Parse start_meta and end_meta from JSON strings"""
        if row_dict.get('start_meta'):
            try:
                row_dict['startMeta'] = json.loads(row_dict['start_meta'])
            except:
                row_dict['startMeta'] = None
        if row_dict.get('end_meta'):
            try:
                row_dict['endMeta'] = json.loads(row_dict['end_meta'])
            except:
                row_dict['endMeta'] = None
        return row_dict
    
    def _handle_annotation_get(self, cursor, parts):
        """处理标注GET请求"""
        username = self._get_username()
        
        # /api/annotations
        if len(parts) == 3:
            if username:
                cursor.execute('SELECT * FROM annotations WHERE username = ? ORDER BY created_at DESC', (username,))
            else:
                cursor.execute('SELECT * FROM annotations ORDER BY created_at DESC')
            rows = cursor.fetchall()
            data = [self._parse_row_meta(dict(row)) for row in rows]
            self.send_json_response(200, {"data": data})
            return

        # /api/annotations/item/{id}
        if len(parts) == 5 and parts[3] == 'item':
            ann_id = parts[4]
            if username:
                cursor.execute('SELECT * FROM annotations WHERE id = ? AND username = ?', (ann_id, username))
            else:
                cursor.execute('SELECT * FROM annotations WHERE id = ?', (ann_id,))
            row = cursor.fetchone()
            if not row:
                self.send_json_response(404, error_payload('annotation_not_found', 'Annotation not found'))
                return
            self.send_json_response(200, {"data": self._parse_row_meta(dict(row))})
            return

        # /api/annotations/batch
        if len(parts) >= 4 and parts[3] == 'batch':
            self.send_json_response(400, error_payload('batch_requires_post', 'Batch requires POST'))
            return

        # /api/annotations/{book_hash}
        if len(parts) == 4:
            book_hash = parts[3]
            if username:
                cursor.execute('SELECT * FROM annotations WHERE book_hash = ? AND username = ? ORDER BY created_at DESC', (book_hash, username))
            else:
                cursor.execute('SELECT * FROM annotations WHERE book_hash = ? ORDER BY created_at DESC', (book_hash,))
            rows = cursor.fetchall()
            data = [self._parse_row_meta(dict(row)) for row in rows]
            self.send_json_response(200, {"data": data})
            return

        # /api/annotations/{book_hash}/{chapter_index}
        if len(parts) == 5:
            book_hash = parts[3]
            try:
                chapter_index = int(parts[4])
            except ValueError:
                self.send_json_response(400, error_payload('invalid_chapter_index', 'Invalid chapter index'))
                return
            if username:
                cursor.execute('SELECT * FROM annotations WHERE book_hash = ? AND chapter_index = ? AND username = ? ORDER BY created_at DESC', (book_hash, chapter_index, username))
            else:
                cursor.execute('SELECT * FROM annotations WHERE book_hash = ? AND chapter_index = ? ORDER BY created_at DESC', (book_hash, chapter_index))
            rows = cursor.fetchall()
            data = [self._parse_row_meta(dict(row)) for row in rows]
            self.send_json_response(200, {"data": data})
            return

        self.send_json_response(404, error_payload('not_found', 'Not found'))
    
    def _handle_annotation_post(self, cursor, parts, conn):
        """处理标注POST请求"""
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length)
        data = json.loads(body.decode('utf-8'))
        username = self._get_username()

        # /api/annotations/batch
        if len(parts) == 4 and parts[3] == 'batch':
            annotations = data.get('annotations', [])
            created = 0
            failed = 0

            for ann in annotations:
                try:
                    cursor.execute('''
                        INSERT OR REPLACE INTO annotations 
                        (id, book_hash, chapter_index, text, note, start_meta, end_meta, 
                         color, created_at, updated_at, username)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        ann['id'], ann['book_hash'], ann['chapter_index'], ann['text'],
                        ann.get('note', ''),
                        json.dumps(ann['startMeta']) if ann.get('startMeta') else None,
                        json.dumps(ann['endMeta']) if ann.get('endMeta') else None,
                        ann['color'], ann['created_at'], ann['updated_at'],
                        username
                    ))
                    created += 1
                except Exception:
                    failed += 1

            conn.commit()
            self.send_json_response(201, {"created": created, "failed": failed})
            return

        # /api/annotations - 创建单个标注
        if len(parts) == 3:
            cursor.execute('''
                INSERT INTO annotations 
                (id, book_hash, chapter_index, text, note, start_meta, end_meta, 
                 color, created_at, updated_at, username)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                data['id'], data['book_hash'], data['chapter_index'], data['text'],
                data.get('note', ''),
                json.dumps(data['startMeta']) if data.get('startMeta') else None,
                json.dumps(data['endMeta']) if data.get('endMeta') else None,
                data['color'], data['created_at'], data['updated_at'],
                username
            ))
            conn.commit()
            self.send_json_response(201, {"data": data})
            return

        self.send_json_response(404, error_payload('not_found', 'Not found'))
    
    def _handle_annotation_put(self, cursor, parts, conn):
        """处理标注PUT请求"""
        # /api/annotations/item/{id}
        if len(parts) == 5 and parts[3] == 'item':
            ann_id = parts[4]
            username = self._get_username()
            
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length)
            data = json.loads(body.decode('utf-8'))
            
            # 检查是否存在（带用户名过滤）
            if username:
                cursor.execute('SELECT * FROM annotations WHERE id = ? AND username = ?', (ann_id, username))
            else:
                cursor.execute('SELECT * FROM annotations WHERE id = ?', (ann_id,))
            if not cursor.fetchone():
                self.send_json_response(404, error_payload('annotation_not_found', 'Annotation not found'))
                return
            
            # 更新
            import datetime
            updated_at = datetime.datetime.now().isoformat()
            if 'chapter_index' in data and (isinstance(data['chapter_index'], bool) or not isinstance(data['chapter_index'], int) or data['chapter_index'] < 0):
                self.send_json_response(400, {"message": "Invalid chapter index"})
                return

            assignments = []
            values = []
            for field in ('note', 'color', 'chapter_index'):
                if field in data:
                    assignments.append(field + ' = ?')
                    values.append(data[field])
            for field, column in (('startMeta', 'start_meta'), ('endMeta', 'end_meta')):
                if field in data:
                    assignments.append(column + ' = ?')
                    values.append(json.dumps(data[field]) if data[field] else None)
            assignments.append('updated_at = ?')
            values.append(updated_at)
            selector = 'id = ? AND username = ?' if username else 'id = ?'
            selector_values = [ann_id, username] if username else [ann_id]
            cursor.execute(
                'UPDATE annotations SET ' + ', '.join(assignments) + ' WHERE ' + selector,
                values + selector_values,
            )
            
            conn.commit()
            
            if username:
                cursor.execute('SELECT * FROM annotations WHERE id = ? AND username = ?', (ann_id, username))
            else:
                cursor.execute('SELECT * FROM annotations WHERE id = ?', (ann_id,))
            row = cursor.fetchone()
            self.send_json_response(200, {"data": self._parse_row_meta(dict(row))})
            return
        
        self.send_json_response(404, error_payload('not_found', 'Not found'))
    
    def _handle_annotation_delete(self, cursor, parts, conn):
        """处理标注DELETE请求"""
        # /api/annotations/item/{id}
        if len(parts) == 5 and parts[3] == 'item':
            ann_id = parts[4]
            username = self._get_username()
            
            if username:
                cursor.execute('DELETE FROM annotations WHERE id = ? AND username = ?', (ann_id, username))
            else:
                cursor.execute('DELETE FROM annotations WHERE id = ?', (ann_id,))
            conn.commit()
            
            self.send_json_response(200, {"message": "Deleted"})
            return
        
        self.send_json_response(404, error_payload('not_found', 'Not found'))
    
    def send_library_index(self):
        """发送图书馆首页"""
        try:
            index_path = os.path.join(self.base_directory, "index.html")
            if not os.path.exists(index_path):
                self.send_json_error(404, 'not_found', 'Library index not found')
                return
                
            with open(index_path, 'rb') as f:
                content = f.read()
            
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(content)))
            self.send_header('Cache-Control', 'no-cache')
            self.end_headers()
            self.wfile.write(content)
            
        except FileNotFoundError:
            self.send_json_error(404, 'not_found', 'Index page not found')
        except Exception as e:
            self.log_message(f"Error sending library index: {e}")
            self.send_json_error(500, 'server_error', 'Internal server error')
    
    def serve_book(self, path):
        """服务书籍内容"""
        try:
            if path[0] == "/":
                path = path[1:]
            file_path = os.path.join(self.base_directory, path)
            file_path = os.path.normpath(file_path)            

            if not os.path.exists(file_path):
                self.send_json_error(404, 'not_found', f'File not found: {file_path}')
                return
            
            self.send_file_safely(file_path)
        except Exception as e:
            self.log_message(f"Error serving book content: {e}")
            try:
                self.send_json_error(500, 'server_error', 'Internal server error')
            except (BrokenPipeError, ConnectionResetError):
                pass
    
    def send_file_safely(self, file_path):
        """安全地发送文件"""
        try:
            if getattr(self.server, '_is_shutting_down', False):
                self.send_json_error(503, 'server_error', 'Server is shutting down')
                return
                
            file_size = os.path.getsize(file_path)
            content_type, encoding = mimetypes.guess_type(file_path)
            if content_type is None:
                content_type = 'application/octet-stream'
            
            self.send_response(200)
            self.send_header('Content-type', content_type)
            self.send_header('Content-Length', str(file_size))
            
            self.send_header('Cache-Control', cache_control_for_path(file_path))
                
            self.end_headers()
            
            chunk_size = 8192
            with open(file_path, 'rb') as f:
                while True:
                    if getattr(self.server, '_is_shutting_down', False):
                        break
                    chunk = f.read(chunk_size)
                    if not chunk:
                        break
                    try:
                        self.wfile.write(chunk)
                    except (BrokenPipeError, ConnectionResetError):
                        break
            
        except FileNotFoundError:
            self.send_json_error(404, 'not_found', 'File not found')
        except PermissionError:
            self.send_json_error(403, 'server_error', 'Permission denied')
        except Exception as e:
            self.log_message(f"Error reading file {file_path}: {e}")
            self.send_json_error(500, 'server_error', 'Internal server error')
    
    def should_cache_file(self, file_path):
        """判断文件是否应该被缓存"""
        return cache_control_for_path(file_path).endswith('immutable')
    
    def log_message(self, format, *args):
        """自定义日志格式"""
        if not self.enableLog:
            return
        thread_name = threading.current_thread().name
        print(f"[{self.log_date_time_string()}] [{thread_name}] {format % args}")
    

class EPUBServer:
    """
    增强的EPUB服务器
    """

    def __init__(self, base_directory, book_count, enableLog: bool, sync_dir=None):
        self.base_directory = base_directory
        self.book_count = book_count
        self.enableLog = enableLog
        self.sync_dir = sync_dir or os.getcwd()
        self.server = None
        self._is_running = False
        self._server_thread = None
    
    def get_local_ip(self):
        """获取本机局域网IP地址（最可靠的方法）"""
        try:
            # 创建一个UDP socket，连接到公共DNS服务器
            # 这不会真正发送数据，只是用来确定路由路径
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))  # Google DNS
            local_ip = s.getsockname()[0]
            s.close()
            return local_ip
        except Exception as e:
            print(f"Get local IP failed: {e}")
            return ""

    def start_server(self, port=8000, no_browser=False,stop_event=None, host=''):
        """启动Web服务器"""
        if self.book_count <= 0:
            print("No books available to serve")
            return False
        
        # Initialize annotation database
        init_annotation_db(self.base_directory)

        bind_host = host or '0.0.0.0'
        display_host = host or 'localhost'
        self.server = uvicorn.Server(uvicorn.Config(create_app(self.base_directory, self.sync_dir), host=bind_host, port=port, log_level='info' if self.enableLog else 'warning'))
        if stop_event is not None:
            threading.Thread(target=lambda: (stop_event.wait(), setattr(self.server, 'should_exit', True)), daemon=True).start()
        print(f"Available books count: {self.book_count}")
        print(f"Web server started: \n\thttp://{display_host}:{port}/")
        if not no_browser: webbrowser.open(f'http://{display_host}:{port}/')
        self._is_running = True
        try:
            self.server.run()
            return True
        finally:
            self._is_running = False
        
        try:
            # 创建自定义请求处理器 - 修复lambda作用域问题
            def create_handler(*args, **kwargs):
                return EPUBHTTPRequestHandler(
                    *args, base_directory=self.base_directory, enableLog=self.enableLog, sync_dir=self.sync_dir, **kwargs
                )
            
            # 启动可停止的服务器
            server_address = (host, port)
            self.server = StoppableThreadedHTTPServer(server_address, create_handler)
            
            # 获取实际绑定的地址和端口
            actual_host1 = host if host else 'localhost'
            actual_host2 = self.get_local_ip() if host == '' else ''
            actual_port = self.server.server_address[1]
            
            print(f"Available books count: {self.book_count}")
            print(f"Web server started: \n\thttp://{actual_host1}:{actual_port}/")
            if actual_host2 != '':
                print(f"\thttp://{actual_host2}:{actual_port}/")
            # for book_hash, book_info in self.library.books.items():
            #     print(f"  - {book_info['title']}: http://{actual_host}:{actual_port}/book/{book_hash}/")
            print("Press Ctrl+C to stop the server\n")
            
            # 自动打开浏览器
            if not no_browser:
                try:
                    webbrowser.open(f'http://{actual_host1}:{actual_port}/')
                except Exception as e:
                    print(f"Failed to open browser: {e}")
            
            # 如果提供了stop_event，则启动一个线程来监视这个事件
            # if stop_event is not None:
            #     def watch_stop_event():
            #         stop_event.wait()
            #         # 简化
            #         self._is_running = False
            #     stop_monitor_thread = threading.Thread(target=watch_stop_event, daemon=True)
            #     stop_monitor_thread.start()
            
            self._is_running = True
            
            # 启动服务器
            while not self.server._is_shutting_down:
                if stop_event is not None and stop_event.is_set():
                    break
                try:
                    self.server.handle_request()
                except Exception as e:
                    if not self.server._is_shutting_down:
                        print(f"Server error: {e}")
            self.server.server_close()
            return True
        except KeyboardInterrupt:
            pass
        except PermissionError:
            print(f"Permission denied: cannot start server on port {port}")
            print("Try using a different port (e.g., 8080, 9000)")
            return False
        except OSError as e:
            if e.errno == errno.EADDRINUSE:
                print(f"Port {port} is already in use")
                print("Try using a different port (e.g., 8080, 9000)")
            else:
                print(f"Failed to start server: {e}")
            return False
        except Exception as e:
            print(f"Failed to start server: {e}")
            return False
        finally:
            self._is_running = False

    def stop_server(self):
        """停止Web服务器 - 修复版本"""
        if not self.is_running():
            print("Server is not running")
            return
        
        # 停止服务器
        if self.server:
            try:
                self.server.should_exit = True
                print("Server socket closed")
            except Exception as e:
                print(f"Error during server shutdown: {e}")
        
        # 等待服务器线程结束
        if self._server_thread and self._server_thread.is_alive():
            self._server_thread.join(timeout=5.0)  # 等待最多5秒
            if self._server_thread.is_alive():
                print("Warning: Server thread did not terminate gracefully")
        
        self._is_running = False
        self.server = None
        self._server_thread = None
        print("Server stopped completely")

    def is_running(self):
        """检查服务器是否正在运行"""
        return self._is_running
