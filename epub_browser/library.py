import os
import tempfile
import minify_html
import shutil
from pathlib import Path
from datetime import datetime

from .processor import EPUBProcessor

class EPUBLibrary:
    """EPUB图书馆类，管理多本书籍"""
    
    def __init__(self, output_dir=None):
        self.books = {}  # 存储所有书籍信息，使用哈希作为键
        self.file2hash = {} # 原书籍epub的 path -> book_hash
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
    
    def has_hidden_component(self, path_str):
        """检查路径中间是否有以.开头的隐藏组件"""
        path = Path(path_str).resolve()  # 转换为绝对路径并解析符号链接
        parts = path.parts
        
        # 跳过根目录（如果是绝对路径）和最后一个组件（如果是文件）
        # 只检查路径中间的目录组件
        for part in parts[1:]:  # parts[0] 通常是根目录如 '/' 或 'C:\\'
            if part.startswith('.'):
                return True
        return False
    
    def epub_file_discover(self, filename) -> list:
        filenames = []
        if self.is_epub_file(filename):
            filenames.append(filename)
            return filenames
        if os.path.isdir(filename) and (not self.has_hidden_component(filename)):
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
                processor.cleanup()
                return False, None
            
            # 解析容器文件
            opf_path = processor.parse_container()
            if not opf_path:
                print(f"Unable to parse EPUB container file: {epub_path}")
                processor.cleanup()
                return False, None
            
            # 解析OPF文件
            if not processor.parse_opf(opf_path):
                processor.cleanup()
                return False, None

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
                'processor': processor,
                'origin_file_path': book_info['origin_file_path']
            }
            self.file2hash[book_info['origin_file_path']] = book_info['hash']
            
            # print(f"Successfully added book: {book_info['title']} (Hash: {book_info['hash']})")
            return True, book_info
            
        except Exception as e:
            print(f"Failed to add book {epub_path}: {e}")
            return False, None
    
    def add_assets(self):
        # 复制 assets
        BASE_DIR = os.path.dirname(os.path.realpath(__file__))
        ASSETS_DIR = os.path.join(BASE_DIR, 'assets')
        assets_path = os.path.join(self.base_directory, "assets")
        for root, dirs, files in os.walk(ASSETS_DIR):
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
<link rel="stylesheet"href="/assets/fa.all.min.css">
<link rel="icon" type="image/svg+xml" href="/assets/favion.svg">
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
        <header class="header" data-id="header">
            <div class="theme-toggle" id="themeToggle">
                <i class="fas fa-moon"></i>
                <span class="control-name">Theme</span>
            </div>
            <h1 style="display: flex; justify-content: center; align-items: center; text-align:center"> <img src="/assets/favion.svg" style="width:60px; height:60px; margin-right:10px; display: flex"> <span style="display: flex">EPUB Library</span></h1>
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
                    <a id="kindleModeValueYes" style="text-decoration: none; color: var(--text-color);" href="javascript:document.cookie=`kindle-mode=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;`; location.replace(location.pathname);">
                        <div class="stat-value">Kindle Mode</div>
                    </a>
                    <a id="kindleModeValueNot" style="text-decoration: none; color: var(--text-color);" href="javascript:document.cookie=`kindle-mode=true; expires=Fri, 26 Jun 999999999999999 20:10:32 GMT; path=/;'`; location.replace(location.pathname);">
                        <div class="stat-value">Not Kindle</div>
                    </a>
                </div>
            </div>
        </header>
        <div class="controls" data-id="controls">
            <div class="search-container">
                <input type="text" class="search-box" placeholder="Search by book title, author, or tag...">
                <i class="fas fa-search search-icon"></i>
            </div>
            <br/>
            <div class="tag-cloud">
                <div class="tag-cloud-item active" data-id="All">All</div>
"""
        for tag in sorted(all_tags):
            library_html += f"""<div class="tag-cloud-item" data-id="{tag}">{tag}</div>"""
        library_html += """
            </div>
        </div>"""

        library_html += """
        <div class="book-grid" data-id="book-grid">
"""
        for book_hash, book_info in self.books.items():
            library_html += f"""
        <div class="book-card" data-id="{book_hash}">
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
    <div class="reading-controls" data-id="reading-controls">
        <button class="control-btn" id="scrollToTopBtn">
            <i class="fas fa-arrow-up"></i>
            <span class="control-name">Top</span>
        </button>
    </div>
</div>
<footer class="footer" data-id="footer">
    <p>EPUB Library &copy; {datetime.now().year} | Powered by <a href="https://github.com/dfface/epub-browser" target="_blank">epub-browser</a></p>
</footer>
"""
        library_html += """
        <script src="/assets/library.js" defer></script>
        <script>
        let base_path = window.location.pathname;
        if (base_path.endsWith("index.html")) {
            base_path = base_path.replace(/index.html$/, '');
        }
        if (base_path !== "/") {
            // 处理所有资源，都要加上基路径
            addBasePath(base_path);
        }

        function addBasePath(basePath) {
            // 处理所有链接、图片和样式表
            const resources = document.querySelectorAll('a[href^="/"], script[src^="/"], img[src^="/"], link[href^="/"]');
            resources.forEach(resource => {
                const src = resource.getAttribute('src');
                const href = resource.getAttribute('href');
                if (src && !src.startsWith('http') && !src.startsWith('//') && !src.startsWith(basePath)) {
                    resource.setAttribute('src', basePath.substr(0, basePath.length - 1) + src);
                }
                if (href && !href.startsWith('http') && !href.startsWith('//') && !href.startsWith(basePath)) {
                    resource.setAttribute('href', basePath.substr(0, basePath.length - 1) + href);
                }
            });
        }


        document.addEventListener('DOMContentLoaded', function() {
        // 检查当前的基路径
        let base_path = window.location.pathname;
        if (base_path.endsWith("index.html")) {
            base_path = base_path.replace(/index.html$/, '');
        }
        // 单独处理 js 资源，无论如何都要重新加载，因为那个脚本不再监听 DOMContentLoaded 事件了
        js_resource = document.querySelector('script[src="/assets/library.js"]');
        if (window.initScriptLibrary) {
            window.initScriptLibrary();
            console.log("init")
            return;
        } else {
            const src = js_resource.getAttribute('src');
            newScript = reloadScriptByReplacement(js_resource, base_path.substr(0, base_path.length - 1) + src);
            newScript.onload = () => {
                if (window.initScriptLibrary) {
                    console.log("reinit")
                    window.initScriptLibrary();
                }
            };
        }
        

        function reloadScriptByReplacement(scriptElement, newSrc) {
            const newScript = document.createElement('script');
            newScript.src = newSrc;
            
            // 复制原script的所有属性（除了src）
            Array.from(scriptElement.attributes).forEach(attr => {
                if (attr.name !== 'src') {
                    newScript.setAttribute(attr.name, attr.value);
                }
            });
            scriptElement.parentNode.replaceChild(newScript, scriptElement);
            return newScript;
        }
        });
        </script>
        <script src="/assets/sortable.min.js"></script>
    </body>
</html>"""
        library_html = minify_html.minify(library_html, minify_css=True, minify_js=True)
        with open(os.path.join(self.base_directory, 'index.html'), 'w', encoding='utf-8') as f:
            f.write(library_html)
    
    def move_book(self, book_hash):
        """按 href 的格式组织目录"""
        book_path = os.path.join(self.base_directory, "book")
        book_info = self.books[book_hash]
        if not book_info:
            print(f"move {book_hash} failed, err: not exists such book info")
        old_path = book_info['web_dir']
        old_temp_dir = book_info['temp_dir']
        cur_path = os.path.join(book_path, book_hash)
        try:
            shutil.rmtree(cur_path, ignore_errors=True) # 删掉原来的文件，避免进入子目录
        except Exception as e:
            pass
        try:
            shutil.move(old_path, cur_path)
        except Exception as e:
            print(f"move {old_path} to {cur_path} failed, err: {e}")
        try:
            # 删除原来的 temp_dir 目录
            shutil.rmtree(old_temp_dir)
        except Exception as e:
            pass

    def remove_book(self, book_hash):
        book_path = os.path.join(self.base_directory, "book")
        cur_path = os.path.join(book_path, book_hash)
        if os.path.exists(cur_path):
            try:
                shutil.rmtree(cur_path)
                self.books.pop(book_hash)
            except Exception as e:
                print(f"remove {cur_path} failed, err: {e}")

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
                    shutil.rmtree(temp_dir, ignore_errors=True)
                    print(f"Cleaned up book: {book_info['title']}, path: {temp_dir}")
                middle_dir = os.path.join(self.output_dir,f"epub_{book_hash}") # 可能存在的中间文件
                if os.path.exists(middle_dir):
                    shutil.rmtree(middle_dir, ignore_errors=True)
                    print(f"Cleaned up book: {book_info['title']}, path: {middle_dir}")
            if os.path.exists(os.path.join(self.output_dir, "index.html")):
                os.remove(os.path.join(self.output_dir, "index.html"))
            if os.path.exists(os.path.join(self.output_dir, "assets")):
                shutil.rmtree(os.path.join(self.output_dir, "assets"), ignore_errors=True)
            if os.path.exists(os.path.join(self.output_dir, "book")):
                shutil.rmtree(os.path.join(self.output_dir, "book"), ignore_errors=True)
            print(f"Cleaned up files inside library base directory: {self.base_directory}")
            return
        else:
            # 清理基础目录
            if os.path.exists(self.base_directory):
                shutil.rmtree(self.base_directory, ignore_errors=True)
                print(f"Cleaned up library base directory: {self.base_directory}")
