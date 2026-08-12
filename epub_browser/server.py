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
from starlette.responses import FileResponse, JSONResponse, PlainTextResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles
import uvicorn


def cache_control_for_path(path):
    """Cache immutable app assets and stable EPUB resources without caching pages."""
    normalized = os.path.normpath(path).replace(os.sep, '/')
    if '/assets/immutable/' in normalized:
        return 'public, max-age=31536000, immutable'
    if '/book/' in normalized and '/resources/' in normalized:
        return 'public, max-age=2592000'
    return 'no-cache'


class CachedStaticFiles(StaticFiles):
    """Static file adapter with one cache policy for browser assets and books."""

    def file_response(self, full_path, stat_result, scope, status_code=200):
        response = super().file_response(full_path, stat_result, scope, status_code)
        response.headers['Cache-Control'] = cache_control_for_path(full_path)
        return response


def create_app(base_directory, sync_dir=None):
    """Create the ASGI module used by Uvicorn to serve an EPUB library."""
    base_directory = os.path.abspath(base_directory)
    init_annotation_db(base_directory)

    async def library_index(request):
        index_path = os.path.join(base_directory, 'index.html')
        if not os.path.isfile(index_path):
            return PlainTextResponse('Library index not found', status_code=404)
        response = FileResponse(index_path, media_type='text/html')
        response.headers['Cache-Control'] = 'no-cache'
        return response

    async def health(request):
        return JSONResponse({'status': 'ok'}, headers={'Cache-Control': 'no-cache'})

    def response(data, status=200):
        return JSONResponse(data, status_code=status, headers={'Cache-Control': 'no-cache'})

    def row_data(row):
        data = dict(row)
        for key, target in [('start_meta', 'startMeta'), ('end_meta', 'endMeta')]:
            data[target] = json.loads(data[key]) if data.get(key) else None
        return data

    async def annotations(request):
        parts = [part for part in request.path_params['path'].split('/') if part]
        if not parts or parts[0] != 'annotations': return response({'message': 'Not found'}, 404)
        username = request.headers.get('X-Username', '').strip()
        conn = sqlite3.connect(os.path.join(base_directory, 'annotations.db'))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        try:
            tail = parts[1:]
            if request.method == 'GET':
                if tail[:1] == ['batch']: return response({'message': 'Batch requires POST'}, 400)
                if tail[:1] == ['item'] and len(tail) == 2:
                    sql, args = ('SELECT * FROM annotations WHERE id = ?', [tail[1]]) if not username else ('SELECT * FROM annotations WHERE id = ? AND username = ?', [tail[1], username])
                    row = cursor.execute(sql, args).fetchone()
                    return response({'data': row_data(row)}, 200) if row else response({'message': 'Annotation not found'}, 404)
                where, args = '', []
                if len(tail) >= 1: where, args = ' WHERE book_hash = ?', [tail[0]]
                if len(tail) == 2:
                    try: args.append(int(tail[1]))
                    except ValueError: return response({'message': 'Invalid chapter index'}, 400)
                    where += ' AND chapter_index = ?'
                if username: where += (' AND ' if where else ' WHERE ') + 'username = ?'; args.append(username)
                rows = cursor.execute('SELECT * FROM annotations' + where + ' ORDER BY created_at DESC', args).fetchall()
                return response({'data': [row_data(row) for row in rows]})
            data = await request.json()
            if request.method == 'POST':
                entries = data.get('annotations', []) if tail == ['batch'] else [data]
                created = failed = 0
                for entry in entries:
                    try:
                        cursor.execute('INSERT OR REPLACE INTO annotations (id,book_hash,chapter_index,text,note,start_meta,end_meta,color,created_at,updated_at,username) VALUES (?,?,?,?,?,?,?,?,?,?,?)', (entry['id'], entry['book_hash'], entry['chapter_index'], entry['text'], entry.get('note',''), json.dumps(entry.get('startMeta')) if entry.get('startMeta') else None, json.dumps(entry.get('endMeta')) if entry.get('endMeta') else None, entry['color'], entry['created_at'], entry['updated_at'], username)); created += 1
                    except Exception: failed += 1
                conn.commit()
                return response({'created': created, 'failed': failed}, 201) if tail == ['batch'] else response({'data': data}, 201)
            if len(tail) != 2 or tail[0] != 'item': return response({'message': 'Not found'}, 404)
            annotation_id = tail[1]; selector, args = ('id = ?', [annotation_id]) if not username else ('id = ? AND username = ?', [annotation_id, username])
            if request.method == 'DELETE': cursor.execute('DELETE FROM annotations WHERE ' + selector, args); conn.commit(); return response({'message': 'Deleted'})
            cursor.execute('UPDATE annotations SET note = ?, color = ?, updated_at = datetime(\'now\') WHERE ' + selector, [data.get('note',''), data.get('color','#FFEB3B')] + args); conn.commit()
            row = cursor.execute('SELECT * FROM annotations WHERE ' + selector, args).fetchone()
            return response({'data': row_data(row)}, 200) if row else response({'message': 'Annotation not found'}, 404)
        finally: conn.close()

    async def sync(request):
        try:
            data = await request.json()
            username, version, shelf = data.get('username', ''), data.get('version', 1), data.get('data')
            if not username: return response({'message': 'Username is required'}, 400)
            directory = sync_dir or base_directory
            pattern = os.path.join(directory, 'epub-browser-bookshelf-' + username + '-*.json')
            records = []
            for filename in glob.glob(pattern):
                try: records.append((int(os.path.basename(filename).rsplit('-', 1)[1][:-5]), filename))
                except (IndexError, ValueError): pass
            if records:
                current_version, current_file = max(records)
                if current_version == version:
                    return response({}, 304)
                if current_version > version:
                    with open(current_file, encoding='utf-8') as source: return response({'message': 'Server has newer or same version', 'version': current_version, 'data': json.load(source)})
            if shelf is None: return response({'message': 'No data provided for update'}, 400)
            new_version = max(version, 1)
            filename = os.path.join(directory, 'epub-browser-bookshelf-' + username + '-' + str(new_version) + '.json')
            with open(filename, 'w', encoding='utf-8') as target: json.dump(shelf, target, ensure_ascii=False, indent=2)
            for _, old_file in records:
                if old_file != filename: os.remove(old_file)
            return response({'message': 'New user created' if not records else 'Data updated', 'version': new_version}, 404 if not records else 201)
        except json.JSONDecodeError: return response({'message': 'Invalid JSON data'}, 400)

    routes = [
        Route('/', library_index),
        Route('/index.html', library_index),
        Route('/api/health', health),
        Route('/api/{path:path}', annotations, methods=['GET', 'POST', 'PUT', 'DELETE']),
        Route('/sync', sync, methods=['POST']),
        Mount('/', app=CachedStaticFiles(directory=base_directory, html=False)),
    ]
    return Starlette(routes=routes)

# Annotation database path
ANNOTATION_DB_PATH = None

def init_annotation_db(base_dir):
    """Initialize annotation database"""
    global ANNOTATION_DB_PATH
    ANNOTATION_DB_PATH = os.path.join(base_dir, 'annotations.db')
    
    conn = sqlite3.connect(ANNOTATION_DB_PATH)
    cursor = conn.cursor()
    
    # Create annotations table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS annotations (
            id TEXT PRIMARY KEY,
            username TEXT NOT NULL DEFAULT '',
            book_hash TEXT NOT NULL,
            chapter_index INTEGER NOT NULL,
            text TEXT NOT NULL,
            note TEXT,
            start_meta TEXT,
            end_meta TEXT,
            color TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    ''')
    # Create indexes
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_chapter_username ON annotations(book_hash, chapter_index, username)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_book_username ON annotations(book_hash, username)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_username ON annotations(username)')
    
    conn.commit()
    conn.close()

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
        
    def do_GET(self):
        """处理GET请求"""
        try:
            # 检查服务器是否正在关闭
            if getattr(self.server, '_is_shutting_down', False):
                self.send_error(503, "Server is shutting down")
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
                self.send_error(500, "Internal Server Error")
            except (BrokenPipeError, ConnectionResetError):
                pass
    
    def do_POST(self):
        """处理POST请求"""
        try:
            if getattr(self.server, '_is_shutting_down', False):
                self.send_error(503, "Server is shutting down")
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
            
            self.send_error(404, "Not Found")
            
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as e:
            self.log_message(f"Unexpected error in do_POST: {e}")
            try:
                self.send_error(500, "Internal Server Error")
            except (BrokenPipeError, ConnectionResetError):
                pass
    
    def do_PUT(self):
        """处理PUT请求"""
        try:
            if getattr(self.server, '_is_shutting_down', False):
                self.send_error(503, "Server is shutting down")
                return
            
            parsed_path = urlparse(self.path)
            path = parsed_path.path
            
            if path.startswith('/api/'):
                self.handle_annotation_api('PUT', path)
                return
            
            self.send_error(404, "Not Found")
            
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as e:
            self.log_message(f"Unexpected error in do_PUT: {e}")
            try:
                self.send_error(500, "Internal Server Error")
            except (BrokenPipeError, ConnectionResetError):
                pass
    
    def do_DELETE(self):
        """处理DELETE请求"""
        try:
            if getattr(self.server, '_is_shutting_down', False):
                self.send_error(503, "Server is shutting down")
                return
            
            parsed_path = urlparse(self.path)
            path = parsed_path.path
            
            if path.startswith('/api/'):
                self.handle_annotation_api('DELETE', path)
                return
            
            self.send_error(404, "Not Found")
            
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as e:
            self.log_message(f"Unexpected error in do_DELETE: {e}")
            try:
                self.send_error(500, "Internal Server Error")
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
                self.send_json_response(400, {"message": "Username is required"})
                return
            
            if not self.sync_dir:
                self.sync_dir = self.base_directory
            
            pattern = os.path.join(self.sync_dir, f"epub-browser-bookshelf-{username}-*.json")
            existing_files = glob.glob(pattern)
            
            if not existing_files:
                if client_data is None:
                    self.send_json_response(400, {"message": "No data provided for new user"})
                    return
                new_version = client_version if client_version > 0 else 1
                filename = f"epub-browser-bookshelf-{username}-{new_version}.json"
                filepath = os.path.join(self.sync_dir, filename)
                with open(filepath, 'w', encoding='utf-8') as f:
                    json.dump(client_data, f, ensure_ascii=False, indent=2)
                self.send_json_response(404, {"message": "New user created", "version": new_version})
                return
            
            max_version = 0
            max_version_file = None
            for f in existing_files:
                basename = os.path.basename(f)
                try:
                    version = int(basename.split('-')[-1].replace('.json', ''))
                    if version > max_version:
                        max_version = version
                        max_version_file = f
                except ValueError:
                    continue
            
            if max_version >= client_version:
                with open(max_version_file, 'r', encoding='utf-8') as f:
                    server_data = json.load(f)
                self.send_json_response(200, {
                    "message": "Server has newer or same version",
                    "version": max_version,
                    "data": server_data
                })
                return
            
            if client_data is None:
                self.send_json_response(400, {"message": "No data provided for update"})
                return
            
            new_version = client_version
            filename = f"epub-browser-bookshelf-{username}-{new_version}.json"
            filepath = os.path.join(self.sync_dir, filename)
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(client_data, f, ensure_ascii=False, indent=2)
            
            for f in existing_files:
                try:
                    os.remove(f)
                except Exception:
                    pass
            
            self.send_json_response(201, {"message": "Data updated", "version": new_version})
            
        except json.JSONDecodeError:
            self.send_json_response(400, {"message": "Invalid JSON data"})
        except Exception as e:
            self.log_message(f"Error handling sync request: {e}")
            self.send_json_response(500, {"message": f"Server error: {str(e)}"})
    
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
                self.send_json_response(404, {"message": "Not found"})
                return
            
            if not ANNOTATION_DB_PATH:
                self.send_json_response(503, {"message": "Database not initialized"})
                return
            
            conn = sqlite3.connect(ANNOTATION_DB_PATH)
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
                
        except Exception as e:
            self.log_message(f"Error handling annotation API: {e}")
            self.send_json_response(500, {"message": f"Server error: {str(e)}"})
    
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
                self.send_json_response(404, {"message": "Annotation not found"})
                return
            self.send_json_response(200, {"data": self._parse_row_meta(dict(row))})
            return

        # /api/annotations/batch
        if len(parts) >= 4 and parts[3] == 'batch':
            self.send_json_response(400, {"message": "Batch requires POST"})
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
                self.send_json_response(400, {"message": "Invalid chapter index"})
                return
            if username:
                cursor.execute('SELECT * FROM annotations WHERE book_hash = ? AND chapter_index = ? AND username = ? ORDER BY created_at DESC', (book_hash, chapter_index, username))
            else:
                cursor.execute('SELECT * FROM annotations WHERE book_hash = ? AND chapter_index = ? ORDER BY created_at DESC', (book_hash, chapter_index))
            rows = cursor.fetchall()
            data = [self._parse_row_meta(dict(row)) for row in rows]
            self.send_json_response(200, {"data": data})
            return

        self.send_json_response(404, {"message": "Not found"})
    
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

        self.send_json_response(404, {"message": "Not found"})
    
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
                self.send_json_response(404, {"message": "Annotation not found"})
                return
            
            # 更新
            import datetime
            updated_at = datetime.datetime.now().isoformat()
            
            if username:
                cursor.execute('''
                    UPDATE annotations 
                    SET note = ?, color = ?, updated_at = ?
                    WHERE id = ? AND username = ?
                ''', (data.get('note', ''), data.get('color', '#FFEB3B'), updated_at, ann_id, username))
            else:
                cursor.execute('''
                    UPDATE annotations 
                    SET note = ?, color = ?, updated_at = ?
                    WHERE id = ?
                ''', (data.get('note', ''), data.get('color', '#FFEB3B'), updated_at, ann_id))
            
            conn.commit()
            
            if username:
                cursor.execute('SELECT * FROM annotations WHERE id = ? AND username = ?', (ann_id, username))
            else:
                cursor.execute('SELECT * FROM annotations WHERE id = ?', (ann_id,))
            row = cursor.fetchone()
            self.send_json_response(200, {"data": self._parse_row_meta(dict(row))})
            return
        
        self.send_json_response(404, {"message": "Not found"})
    
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
        
        self.send_json_response(404, {"message": "Not found"})
    
    def send_library_index(self):
        """发送图书馆首页"""
        try:
            index_path = os.path.join(self.base_directory, "index.html")
            if not os.path.exists(index_path):
                self.send_error(404, "Library index not found")
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
            self.send_error(404, "Index page not found")
        except Exception as e:
            self.log_message(f"Error sending library index: {e}")
            self.send_error(500, f"Error reading index: {str(e)}")
    
    def serve_book(self, path):
        """服务书籍内容"""
        try:
            if path[0] == "/":
                path = path[1:]
            file_path = os.path.join(self.base_directory, path)
            file_path = os.path.normpath(file_path)            

            if not os.path.exists(file_path):
                self.send_error(404, f"File not found: {file_path}")
                return
            
            self.send_file_safely(file_path)
        except Exception as e:
            self.log_message(f"Error serving book content: {e}")
            try:
                self.send_error(500, f"Error serving content: {str(e)}")
            except (BrokenPipeError, ConnectionResetError):
                pass
    
    def send_file_safely(self, file_path):
        """安全地发送文件"""
        try:
            if getattr(self.server, '_is_shutting_down', False):
                self.send_error(503, "Server is shutting down")
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
            self.send_error(404, "File not found")
        except PermissionError:
            self.send_error(403, "Permission denied")
        except Exception as e:
            self.log_message(f"Error reading file {file_path}: {e}")
            self.send_error(500, f"Error reading file: {str(e)}")
    
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
