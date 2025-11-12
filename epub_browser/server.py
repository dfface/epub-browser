import os
import shutil
import webbrowser
import threading
import mimetypes
from socketserver import ThreadingMixIn
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse
import errno
from socket import error as socket_error

from .library import EPUBLibrary


class StoppableThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """可停止的多线程HTTP服务器"""
    daemon_threads = True
    thread_name_prefix = "epub_server_"
    
    def __init__(self, server_address, RequestHandlerClass, library):
        super().__init__(server_address, RequestHandlerClass)
        self.library = library
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
    
    def __init__(self, *args, library=None, enableLog, **kwargs):
        self.library = library
        self.enableLog = enableLog
        self.base_directory = self.library.base_directory
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
                self.serve_book_content(path)
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
    
    def serve_book_content(self, path):
        """服务书籍内容"""
        try:
            if getattr(self.server, '_is_shutting_down', False):
                self.send_error(503, "Server is shutting down")
                return
                
            path_parts = path.split('/')
            if len(path_parts) < 3:
                self.send_error(404, "Book not found")
                return
            
            book_hash = path_parts[2]
            
            if book_hash not in self.library.books:
                self.send_error(404, f"Book with hash '{book_hash}' not found")
                return
            
            book_info = self.library.books[book_hash]
            book_web_dir = book_info['web_dir']
            
            if len(path_parts) == 3 or path_parts[3] == '':
                file_path = os.path.join(book_web_dir, 'index.html')
            else:
                relative_path = '/'.join(path_parts[3:])
                file_path = os.path.join(book_web_dir, relative_path)
            
            file_path = os.path.normpath(file_path)
            if not file_path.startswith(os.path.normpath(book_web_dir)):
                self.send_error(403, "Access denied")
                return
            
            if not os.path.exists(file_path):
                self.send_error(404, f"File not found: {relative_path}")
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
            
            if self.should_cache_file(file_path):
                self.send_header('Cache-Control', 'public, max-age=3600')
            else:
                self.send_header('Cache-Control', 'no-cache')
                
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
        cache_extensions = {'.css', '.js', '.png', '.jpg', '.jpeg', '.gif', '.svg', '.woff', '.woff2', '.ttf'}
        return any(file_path.endswith(ext) for ext in cache_extensions)
    
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

    def __init__(self, library: EPUBLibrary, enableLog: bool):
        self.library = library
        self.enableLog = enableLog
        self.server = None
        self._is_running = False
        self._server_thread = None

    def start_server(self, port=8000, no_browser=False, host=''):
        """启动Web服务器"""
        if not self.library.books:
            print("No books available to serve")
            return False
        
        try:
            # 创建自定义请求处理器 - 修复lambda作用域问题
            def create_handler(*args, **kwargs):
                return EPUBHTTPRequestHandler(
                    *args, library=self.library, enableLog=self.enableLog, **kwargs
                )
            
            # 启动可停止的服务器
            server_address = (host, port)
            self.server = StoppableThreadedHTTPServer(server_address, create_handler, self.library)
            
            # 获取实际绑定的地址和端口
            actual_host = host if host else 'localhost'
            actual_port = self.server.server_address[1]
            
            print(f"Web server started: http://{actual_host}:{actual_port}")
            print(f"Available books ({len(self.library.books)}):")
            for book_hash, book_info in self.library.books.items():
                print(f"  - {book_info['title']}: http://{actual_host}:{actual_port}/book/{book_hash}/")
            print("Press Ctrl+C to stop the server\n")
            
            # 自动打开浏览器
            if not no_browser:
                try:
                    webbrowser.open(f'http://{actual_host}:{actual_port}')
                except Exception as e:
                    print(f"Failed to open browser: {e}")
            
            self._is_running = True
            
            # 启动服务器
            self.server.serve_forever()
            return True
            
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
        
        print("Shutting down server...")
        
        # 停止服务器
        if self.server:
            try:
                self.server.shutdown()
                self.server.server_close()
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
    
    def cleanup(self):
        """清理所有临时文件"""
        # 先停止服务器
        if self.is_running():
            self.stop_server()
        
        # 清理基础目录
        if os.path.exists(self.library.base_directory):
            shutil.rmtree(self.library.base_directory)
            print(f"Cleaned up library base directory: {self.library.base_directory}")