import os
import shutil
import webbrowser
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse
from library import EPUBLibrary

class EPUBHTTPRequestHandler(SimpleHTTPRequestHandler):
    """自定义HTTP请求处理器"""
    
    def __init__(self, *args, library=None, **kwargs):
        self.library = library
        # 设置服务器根目录为临时目录
        self.base_directory = self.library.base_directory
        super().__init__(*args, directory=self.base_directory, **kwargs)
    
    def do_GET(self):
        """处理GET请求"""
        # 解析请求路径
        parsed_path = urlparse(self.path)
        path = parsed_path.path
        
        # 处理根路径 - 显示图书馆首页
        if path == '/' or path == '/index.html':
            self.send_library_index()
            return
        
        # 处理书籍路径 - 使用哈希值
        if path.startswith('/book/'):
            self.serve_book_content(path)
            return
        
        # 其他请求使用默认处理
        super().do_GET()
    
    def send_library_index(self):
        with open(os.path.join(self.base_directory, "index.html"), 'rb') as f:
            content = f.read()
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.send_header('Content-Length', str(len(content)))
        self.end_headers()
        self.wfile.write(content)
        self.end_headers()
    
    def serve_book_content(self, path):
        """服务书籍内容"""
        # 提取书籍哈希值和请求的文件路径
        path_parts = path.split('/')
        if len(path_parts) < 3:
            self.send_error(404, "Book not found")
            return
        
        book_hash = path_parts[2]
        
        # 检查书籍是否存在
        if book_hash not in self.library.books:
            self.send_error(404, f"Book with hash '{book_hash}' not found")
            return
        
        book_info = self.library.books[book_hash]
        book_web_dir = book_info['web_dir']
        
        # 确定请求的文件
        if len(path_parts) == 3 or path_parts[3] == '':
            # 请求书籍根目录，返回index.html
            file_path = os.path.join(book_web_dir, 'index.html')
        else:
            # 请求特定文件
            relative_path = '/'.join(path_parts[3:])
            file_path = os.path.join(book_web_dir, relative_path)
        
        # 检查文件是否存在
        if not os.path.exists(file_path):
            self.send_error(404, f"File not found: {relative_path}")
            return
        
        # 发送文件
        try:
            with open(file_path, 'rb') as f:
                content = f.read()
            
            # 确定MIME类型
            if file_path.endswith('.html'):
                content_type = 'text/html'
            elif file_path.endswith('.css'):
                content_type = 'text/css'
            elif file_path.endswith('.js'):
                content_type = 'application/javascript'
            elif file_path.endswith('.png'):
                content_type = 'image/png'
            elif file_path.endswith('.jpg') or file_path.endswith('.jpeg'):
                content_type = 'image/jpeg'
            elif file_path.endswith('.gif'):
                content_type = 'image/gif'
            elif file_path.endswith('.svg'):
                content_type = 'image/svg+xml'
            else:
                content_type = 'application/octet-stream'
            
            self.send_response(200)
            self.send_header('Content-type', content_type)
            self.send_header('Content-Length', str(len(content)))
            self.end_headers()
            self.wfile.write(content)
            
        except Exception as e:
            self.send_error(500, f"Error reading file: {str(e)}")
    
    def log_message(self, format, *args):
        """自定义日志格式"""
        print(f"[{self.log_date_time_string()}] {format % args}")


class EPUBServer():
    """
    简单 HTTP 服务器
    """

    def __init__(self, library: EPUBLibrary):
        self.library = library
        self.server = None

    def start_server(self, port=8000, no_browser=False):
        """启动Web服务器"""
        if not self.library.books:
            print("No books available to serve")
            return False
        
        try:
            # 创建自定义请求处理器
            handler = lambda *args, **kwargs: EPUBHTTPRequestHandler(
                *args, library=self.library, **kwargs
            )
            
            # 启动服务器
            server_address = ('', port)
            self.server = HTTPServer(server_address, handler)
            
            print(f"Web server started: http://localhost:{port}")
            print("Available books:")
            for book_hash, book_info in self.library.books.items():
                print(f"  - {book_info['title']}: http://localhost:{port}/book/{book_hash}/")
            print("Press Ctrl+C to stop the server\n")
            
            # 自动打开浏览器
            if not no_browser:
                webbrowser.open(f'http://localhost:{port}')
            
            # 启动服务器
            self.server.serve_forever()
            return True
            
        except Exception as e:
            print(f"Failed to start server: {e}")
            return False
    
    def stop_server(self):
        """停止Web服务器"""
        if self.server:
            self.server.shutdown()
            print("Server stopped")
    
    def cleanup(self):
        """清理所有临时文件"""
        # 清理基础目录
        if os.path.exists(self.library.base_directory):
            shutil.rmtree(self.library.base_directory)
            # print(f"Cleaned up library base directory: {self.base_directory}")
        
        # 清理各本书籍的临时文件
        for book_hash, book_info in self.library.books.items():
            try:
                book_info['processor'].cleanup()
                print(f"Cleaned up temporary files for: {book_info['title']}")
            except Exception as e:
                print(f"Failed to clean up {book_info['title']}: {e}")
