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
        for root, dirs, files in os.walk(".assets"):
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
    <p>EPUB Library &copy; {datetime.now().year} | <a href="javascript:localStorage.clear(); alert('Done!');">clear localStorage</a> | Powered by <a href="https://github.com/dfface/epub-browser" target="_blank">epub-browser</a></p>
</footer>
"""
        library_html += """<script>
        // 设置 cookie
        function setCookie(key, value) {
            const date = new Date();
            date.setTime(date.getTime() + 3650 * 24 * 60 * 60 * 1000); // 3650天的毫秒数
            const expires = "expires=" + date.toUTCString(); // 转换为 UTC 格式
            document.cookie = `${key}=${value}; ${expires}; path=/;`;
        }

        // 解析指定 key 的 Cookie
        function getCookie(key) {
            // 分割所有 Cookie 为数组
            const cookies = document.cookie.split('; ');
            for (const cookie of cookies) {
                // 分割键和值
                const [cookieKey, cookieValue] = cookie.split('=');
                // 解码并返回匹配的值
                if (cookieKey === key) {
                return decodeURIComponent(cookieValue);
                }
            }
            return null; // 未找到
        }

        function deleteCookie(name) {
            // 设置 Cookie 过期时间为过去（例如：1970年1月1日）
            document.cookie = `${name}=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;`;
        }
        
        document.addEventListener('DOMContentLoaded', function() {
            // 检查当前的基路径
            base_path = window.location.pathname;
            if (base_path !== "/") {
                if (base_path.endsWith("index.html")) {
                    base_path = base_path.replace(/index.html$/, '');
                }
                // 处理所有资源，都要加上基路径
                addBasePath(base_path);
            } else {
            }

            function addBasePath(basePath) {
                // 处理所有链接、图片、脚本和样式表
                const resources = document.querySelectorAll('a[href^="/"], img[src^="/"], script[src^="/"], link[rel="stylesheet"][href^="/"]');
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

            let kindleMode = getCookie("kindle-mode") || "false";
            function isKindleMode() {
                return kindleMode == "true";
            }

            if (isKindleMode()) {
                document.querySelector("#kindleModeValueNot").style.display = 'none';
                document.querySelector("#kindleModeValueYes").style.display = 'inherit';
                document.body.classList.add("kindle-mode");
            } else {
                document.querySelector("#kindleModeValueNot").style.display = 'inherit';
                document.querySelector("#kindleModeValueYes").style.display = 'none';
            }

            // 书籍目录锚点
            const allBookLinks = document.querySelectorAll('.book-card .book-link');
            allBookLinks.forEach(item => {
                let pathParts = item.href.split('/');
                pathParts = pathParts.filter(item => item !== "");
                let book_hash = pathParts[pathParts.length - 2];  // 最后一个是 index.html
                if (!isKindleMode()) {
                    let book_anchor = localStorage.getItem(book_hash) || '';
                    item.href += book_anchor;
                } else {
                    let book_anchor = getCookie(book_hash) || '';
                    item.href += book_anchor;
                }
            });

            // 主题切换
            const themeToggle = document.getElementById('themeToggle');
            const themeIcon = themeToggle.querySelector('i');
            
            // 检查本地存储中的主题设置
            let currentTheme = 'light';
            if (!isKindleMode()) {
                currentTheme = localStorage.getItem('theme');
            } else {
                currentTheme = getCookie('theme');
            }
            
            // 应用保存的主题
            if (currentTheme === 'dark') {
                document.body.classList.add('dark-mode');
                themeIcon.classList.remove('fa-moon');
                themeIcon.classList.add('fa-sun');
            }
            
            // 切换主题
            themeToggle.addEventListener('click', function() {
                document.body.classList.toggle('dark-mode');
                
                if (document.body.classList.contains('dark-mode')) {
                    themeIcon.classList.remove('fa-moon');
                    themeIcon.classList.add('fa-sun');
                    if (!isKindleMode()) {
                        localStorage.setItem('theme', 'dark');
                    } else {
                        setCookie('theme', 'dark');
                    }
                } else {
                    themeIcon.classList.remove('fa-sun');
                    themeIcon.classList.add('fa-moon');
                    if (!isKindleMode()) {
                        localStorage.setItem('theme', 'light');
                    } else {
                        setCookie('theme', 'light');
                    }
                }
            });
            
            // 搜索功能
            const searchBox = document.querySelector('.search-box');
            const bookCards = document.querySelectorAll('.book-card');
            const filterBtns = document.querySelectorAll('.filter-btn');
            const tagCloudItems = document.querySelectorAll('.tag-cloud-item');
            
            // 搜索功能
            searchBox.addEventListener('input', function() {
                const searchTerm = this.value.toLowerCase();
                
                bookCards.forEach(card => {
                    const title = card.querySelector('.book-title').textContent.toLowerCase();
                    const author = card.querySelector('.book-author').textContent.toLowerCase();
                    
                    if (title.includes(searchTerm) || author.includes(searchTerm)) {
                        card.style.display = 'block';
                    } else {
                        card.style.display = 'none';
                    }
                });
            });
            
            // 标签云筛选功能
            tagCloudItems.forEach(tag => {
                tag.addEventListener('click', function() {
                    // 移除所有标签的active类
                    tagCloudItems.forEach(t => t.classList.remove('active'));
                    // 为当前点击的标签添加active类
                    this.classList.add('active');
                    
                    const tagText = this.textContent.trim();
                    
                    if (tagText === 'All') {
                        bookCards.forEach(card => {
                            card.style.display = 'block';
                        });
                    } else {
                        bookCards.forEach(card => {
                            const tags = card.querySelectorAll('.book-tag');
                            let hasTag = false;
                            
                            tags.forEach(t => {
                                if (t.textContent === tagText) {
                                    hasTag = true;
                                }
                            });
                            
                            if (hasTag) {
                                card.style.display = 'block';
                            } else {
                                card.style.display = 'none';
                            }
                        });
                    }
                });
            });
            
            // 书籍标签点击筛选功能
            const bookTags = document.querySelectorAll('.book-tag');
            bookTags.forEach(tag => {
                tag.addEventListener('click', function(e) {
                    e.preventDefault();
                    e.stopPropagation();
                    
                    const tagText = this.textContent;
                    
                    // 移除所有标签云的active类
                    tagCloudItems.forEach(t => t.classList.remove('active'));
                    
                    // 激活对应的标签云项
                    tagCloudItems.forEach(t => {
                        if (t.textContent === tagText) {
                            t.classList.add('active');
                        }
                    });
                    
                    // 筛选书籍
                    bookCards.forEach(card => {
                        const tags = card.querySelectorAll('.book-tag');
                        let hasTag = false;
                        
                        tags.forEach(t => {
                            if (t.textContent === tagText) {
                                hasTag = true;
                            }
                        });
                        
                        if (hasTag) {
                            card.style.display = 'block';
                        } else {
                            card.style.display = 'none';
                        }
                    });
                });
            });

            // 滚动到顶部功能
            const scrollToTopBtn = document.getElementById('scrollToTopBtn');
            
            scrollToTopBtn.addEventListener('click', function() {
                window.scrollTo({
                    top: 0,
                    behavior: 'smooth'
                });
            });
        });
    </script>
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
            shutil.rmtree(os.path.join(self.output_dir, "assets"))
            return
        else:
            # 清理基础目录
            if os.path.exists(self.base_directory):
                shutil.rmtree(self.base_directory)
                print(f"Cleaned up library base directory: {self.base_directory}")
