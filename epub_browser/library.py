import os
import tempfile
import minify_html
import shutil
from datetime import datetime

from .processor import EPUBProcessor

class EPUBLibrary:
    """EPUB图书馆类，管理多本书籍"""
    
    def __init__(self, output_dir=None):
        self.books = {}  # 存储所有书籍信息，使用哈希作为键
        self.output_dir = output_dir
        
        # 创建基础目录
        if output_dir is not None:
            if os.path.exists(output_dir):
                # 如果存在 那就存在
                self.base_directory = output_dir
            else:
                try:
                    os.mkdir(output_dir)
                    self.base_directory = output_dir
                except Exception:
                    print(f"output_dir {output_dir} not exists, try to create failed, please check.")
                    return
        else:
            self.base_directory = tempfile.mkdtemp(prefix='epub_library_')

        print(f"Library base directory: {self.base_directory}")
    
    def is_epub_file(self, filename):
        suffix = filename[-5:]
        return suffix == '.epub'
    
    def epub_file_discover(self, filename) -> list:
        filenames = []
        if self.is_epub_file(filename):
            filenames.append(filename)
            return filenames
        if os.path.isdir(filename):
            cur_files = os.listdir(filename)
            for new_filename in cur_files:
                new_path = os.path.join(filename, new_filename)
                cur_names = self.epub_file_discover(new_path)
                filenames.extend(cur_names)
        return filenames   
    
    def add_book(self, epub_path):
        """添加一本书籍到图书馆"""
        try:
            # print(f"Adding book: {epub_path}")
            processor = EPUBProcessor(epub_path, self.base_directory)
            
            # 解压EPUB
            if not processor.extract_epub():
                return False
            
            # 解析容器文件
            opf_path = processor.parse_container()
            if not opf_path:
                print(f"Unable to parse EPUB container file: {epub_path}")
                return False
            
            # 解析OPF文件
            if not processor.parse_opf(opf_path):
                return False

            # 重新生成 hash
            processor.generate_hash()
            
            # 创建网页界面
            web_dir = processor.create_web_interface()
            
            # 存储书籍信息
            book_info = processor.get_book_info()
            self.books[book_info['hash']] = {
                'temp_dir': book_info['temp_dir'],
                'title': book_info['title'],
                'web_dir': web_dir,
                'cover': book_info['cover'],
                'authors': book_info['authors'],
                'tags': book_info['tags'],
                'processor': processor
            }
            
            # print(f"Successfully added book: {book_info['title']} (Hash: {book_info['hash']})")
            return True
            
        except Exception as e:
            print(f"Failed to add book {epub_path}: {e}")
            return False
    
    def add_assets(self):
        # 复制 assets
        assets_path = os.path.join(self.base_directory, "assets")
        for root, dirs, files in os.walk("./assets"):
            for file in files:
                src_path = os.path.join(root, file)
                dst_path = os.path.join(assets_path, file)
                # 确保目标目录存在
                os.makedirs(os.path.dirname(dst_path), exist_ok=True)
                shutil.copy2(src_path, dst_path)
            
    
    def create_library_home(self):
        """图书馆首页"""
        library_html = """<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport"content="width=device-width, initial-scale=1.0"><title>EPUB Library</title>
<link rel="stylesheet"href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.7.2/css/all.min.css">
<link rel="icon" type="image/svg+xml" href="data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCA2NDAgNjQwIj48IS0tIUZvbnQgQXdlc29tZSBGcmVlIHY3LjEuMCBieSBAZm9udGF3ZXNvbWUgLSBodHRwczovL2ZvbnRhd2Vzb21lLmNvbSBMaWNlbnNlIC0gaHR0cHM6Ly9mb250YXdlc29tZS5jb20vbGljZW5zZS9mcmVlIENvcHlyaWdodCAyMDI1IEZvbnRpY29ucywgSW5jLi0tPjxwYXRoIGQ9Ik0zMjAgMjA1LjNMMzIwIDUxNC42TDMyMC41IDUxNC40QzM3NS4xIDQ5MS43IDQzMy43IDQ4MCA0OTIuOCA0ODBMNTEyIDQ4MEw1MTIgMTYwTDQ5Mi44IDE2MEM0NTAuNiAxNjAgNDA4LjcgMTY4LjQgMzY5LjcgMTg0LjZDMzUyLjkgMTkxLjYgMzM2LjMgMTk4LjUgMzIwIDIwNS4zek0yOTQuOSAxMjUuNUwzMjAgMTM2TDM0NS4xIDEyNS41QzM5MS45IDEwNiA0NDIuMSA5NiA0OTIuOCA5Nkw1MjggOTZDNTU0LjUgOTYgNTc2IDExNy41IDU3NiAxNDRMNTc2IDQ5NkM1NzYgNTIyLjUgNTU0LjUgNTQ0IDUyOCA1NDRMNDkyLjggNTQ0QzQ0Mi4xIDU0NCAzOTEuOSA1NTQgMzQ1LjEgNTczLjVMMzMyLjMgNTc4LjhDMzI0LjQgNTgyLjEgMzE1LjYgNTgyLjEgMzA3LjcgNTc4LjhMMjk0LjkgNTczLjVDMjQ4LjEgNTU0IDE5Ny45IDU0NCAxNDcuMiA1NDRMMTEyIDU0NEM4NS41IDU0NCA2NCA1MjIuNSA2NCA0OTZMNjQgMTQ0QzY0IDExNy41IDg1LjUgOTYgMTEyIDk2TDE0Ny4yIDk2QzE5Ny45IDk2IDI0OC4xIDEwNiAyOTQuOSAxMjUuNXoiLz48L3N2Zz4=">
<link rel="stylesheet"href="/assets/library.css">
</head>
<body>
"""
        all_tags = set()
        for book_hash, book_info in self.books.items():
            cur_tags = book_info['tags']
            if cur_tags:
                for cur_tag in cur_tags:
                    all_tags.add(cur_tag)

        library_html += f"""
    <div class="container">
        <header class="header">
            <div class="theme-toggle" id="themeToggle">
                <i class="fas fa-moon"></i>
                <span class="control-name">Theme</span>
            </div>
            <h1><i class="fas fa-book-open"></i> EPUB Library</h1>
            <div class="stats">
                <div class="stat-card">
                    <i class="fas fa-book"></i>
                    <div>
                        <div class="stat-value">{len(self.books)} book(s)</div>
                    </div>
                </div>
                <div class="stat-card">
                    <i class="fas fa-tags"></i>
                    <div>
                        <div class="stat-value">{len(all_tags)} tag(s)</div>
                    </div>
                </div>
                <div class="stat-card" id="kindleMode">
                    <i class="fas fa-mobile"></i>
                    <a id="kindleModeValueYes" style="text-decoration: none; color: var(--text-color);" href="javascript:deleteCookie('kindle-mode'); location.replace(location.pathname);">
                        <div class="stat-value">Kindle Mode</div>
                    </a>
                    <a id="kindleModeValueNot" style="text-decoration: none; color: var(--text-color);" href="javascript:setCookie('kindle-mode', 'true'); location.replace(location.pathname);">
                        <div class="stat-value">Not Kindle</div>
                    </a>
                </div>
            </div>
        </header>
        <div class="controls">
            <div class="search-container">
                <input type="text" class="search-box" placeholder="Search by book title, author, or tag...">
                <i class="fas fa-search search-icon"></i>
            </div>
            <br/>
            <div class="tag-cloud">
                <div class="tag-cloud-item active">All</div>
"""
        for tag in sorted(all_tags):
            library_html += f"""<div class="tag-cloud-item">{tag}</div>"""
        library_html += """
            </div>
        </div>"""

        library_html += """
        <div class="book-grid">
"""
        for book_hash, book_info in self.books.items():
            library_html += f"""
        <div class="book-card">
            <a href="/book/{book_hash}/index.html" class="book-link" id="{book_hash}">
                <img src="/book/{book_hash}/{book_info['cover']}" alt="cover" class="book-cover"/>
                <div class="book-card-content">
                    <h3 class="book-title">{book_info['title']}</h3>
                    <div class="book-author">{" & ".join(book_info['authors']) if book_info['authors'] else ""}</div>
            """
            if book_info['tags']:
                library_html += """<div class="book-tags">"""
                for tag in book_info['tags']:
                    library_html += f"""
                        <span class="book-tag">{tag}</span>
"""
                library_html += """</div>"""
            library_html += """
                </div>
            </a>
        </div>
"""      
        library_html += f"""
    </div>
    <div class="reading-controls">
        <button class="control-btn" id="scrollToTopBtn">
            <i class="fas fa-arrow-up"></i>
            <span class="control-name">Top</span>
        </button>
    </div>
</div>
<footer class="footer">
    <p>EPUB Library &copy; {datetime.now().year} | Powered by <a href="https://github.com/dfface/epub-browser" target="_blank">epub-browser</a></p>
</footer>
"""
        library_html += """
        <script src="/assets/library.js" defer></script>
    </body>
</html>"""
        library_html = minify_html.minify(library_html, minify_css=True, minify_js=True)
        with open(os.path.join(self.base_directory, 'index.html'), 'w', encoding='utf-8') as f:
            f.write(library_html)
    
    def reorganize_files(self):
        """按照 href 的格式组织目录"""
        # 创建 book 目录
        book_path = os.path.join(self.base_directory, "book")
        if os.path.exists(book_path):
            try:
                shutil.rmtree(book_path)
                os.mkdir(book_path)
            except Exception as e:
                print(f"book_path {book_path} exists, try to recreate failed, err: {e}")
        else:
            os.mkdir(book_path)
        # 把所有书籍移动到对应目录
        for book_hash, book_info in self.books.items():
            old_path = book_info['web_dir']
            old_temp_dir = book_info['temp_dir']
            cur_path = os.path.join(book_path, book_hash)
            try:
                shutil.move(old_path, cur_path)
                # 删除原来的 temp_dir 目录
                shutil.rmtree(old_temp_dir)
            except Exception as e:
                print(f"move {old_path} to {cur_path} failed, err: {e}")
    
    def cleanup(self):
        """清理所有文件"""
        if self.output_dir is not None:
            # 用户自己的目录，不要一个全删
            for book_hash, book_info in self.books.items():
                temp_dir = book_info['temp_dir']
                if os.path.exists(temp_dir):
                    shutil.rmtree(temp_dir)
                    print(f"Cleaned up book: {book_info['title']}, path: {temp_dir}")
            os.remove(os.path.join(self.output_dir, "index.html"))
            if os.path.exists(os.path.join(self.output_dir, "assets")):
                shutil.rmtree(os.path.join(self.output_dir, "assets"))
            return
        else:
            # 清理基础目录
            if os.path.exists(self.base_directory):
                shutil.rmtree(self.base_directory)
                print(f"Cleaned up library base directory: {self.base_directory}")
