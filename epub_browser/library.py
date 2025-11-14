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
    
    def create_library_home(self):
        """图书馆首页"""
        library_html = """<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport"content="width=device-width, initial-scale=1.0"><title>EPUB Library</title><link rel="stylesheet"href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/7.0.1/css/all.min.css">
<link rel="icon" type="image/svg+xml" href="data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCA2NDAgNjQwIj48IS0tIUZvbnQgQXdlc29tZSBGcmVlIHY3LjEuMCBieSBAZm9udGF3ZXNvbWUgLSBodHRwczovL2ZvbnRhd2Vzb21lLmNvbSBMaWNlbnNlIC0gaHR0cHM6Ly9mb250YXdlc29tZS5jb20vbGljZW5zZS9mcmVlIENvcHlyaWdodCAyMDI1IEZvbnRpY29ucywgSW5jLi0tPjxwYXRoIGQ9Ik0zMjAgMjA1LjNMMzIwIDUxNC42TDMyMC41IDUxNC40QzM3NS4xIDQ5MS43IDQzMy43IDQ4MCA0OTIuOCA0ODBMNTEyIDQ4MEw1MTIgMTYwTDQ5Mi44IDE2MEM0NTAuNiAxNjAgNDA4LjcgMTY4LjQgMzY5LjcgMTg0LjZDMzUyLjkgMTkxLjYgMzM2LjMgMTk4LjUgMzIwIDIwNS4zek0yOTQuOSAxMjUuNUwzMjAgMTM2TDM0NS4xIDEyNS41QzM5MS45IDEwNiA0NDIuMSA5NiA0OTIuOCA5Nkw1MjggOTZDNTU0LjUgOTYgNTc2IDExNy41IDU3NiAxNDRMNTc2IDQ5NkM1NzYgNTIyLjUgNTU0LjUgNTQ0IDUyOCA1NDRMNDkyLjggNTQ0QzQ0Mi4xIDU0NCAzOTEuOSA1NTQgMzQ1LjEgNTczLjVMMzMyLjMgNTc4LjhDMzI0LjQgNTgyLjEgMzE1LjYgNTgyLjEgMzA3LjcgNTc4LjhMMjk0LjkgNTczLjVDMjQ4LjEgNTU0IDE5Ny45IDU0NCAxNDcuMiA1NDRMMTEyIDU0NEM4NS41IDU0NCA2NCA1MjIuNSA2NCA0OTZMNjQgMTQ0QzY0IDExNy41IDg1LjUgOTYgMTEyIDk2TDE0Ny4yIDk2QzE5Ny45IDk2IDI0OC4xIDEwNiAyOTQuOSAxMjUuNXoiLz48L3N2Zz4=">
<style>
        :root {
            --primary: #4361ee;
            --primary-light: #4895ef;
            --secondary: #3f37c9;
            --dark: #1d3557;
            --light: #f8f9fa;
            --gray: #6c757d;
            --gray-light: #e9ecef;
            --success: #4cc9f0;
            --warning: #f8961e;
            --danger: #e63946;
            --border-radius: 12px;
            --shadow: 0 4px 20px rgba(0, 0, 0, 0.08);
            --transition: all 0.3s ease;
            
            /* 浅色主题变量 */
            --bg-color: #f8f9fa;
            --card-bg: #ffffff;
            --text-color: #1d3557;
            --text-secondary: #6c757d;
            --border-color: #e9ecef;
            --header-bg: #ffffff;
        }

        .dark-mode {
            /* 深色主题变量 */
            --bg-color: #121212;
            --card-bg: #1e1e1e;
            --text-color: #e9ecef;
            --text-secondary: #a0a0a0;
            --border-color: #2d2d2d;
            --header-bg: #1e1e1e;
            --shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
        }

        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: "LXGW WenKai", "Helvetica Neue", "Heiti", "Songti", "Kaiti", "Fangsong", "Helvetica", "Arial", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", "WenQuanYi Micro Hei", "Times New Roman", "Courier New", system-ui, -apple-system, sans-serif;
            line-height: 1.6;
            color: var(--text-color);
            background: var(--bg-color);
            min-height: 100vh;
            transition: var(--transition);
            padding: 0 20px;
        }

        /* 字体设置 */
        .content h1, .content h2, .content h3, .content h4, .content h5, .content h6, .content p, .content span, .content a, .content div {
            font-family: "LXGW WenKai", "Helvetica Neue", "Heiti", "Songti", "Kaiti", "Fangsong", "Helvetica", "Arial", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", "WenQuanYi Micro Hei", "Times New Roman", "Courier New", system-ui, -apple-system, sans-serif;
        }

        .container {
            max-width: 1000px;
            margin: 0 auto;
            padding: 20px 0;
        }

        .header {
            text-align: center;
            margin-bottom: 40px;
            padding: 40px 20px;
            background: var(--header-bg);
            border-radius: var(--border-radius);
            box-shadow: var(--shadow);
            position: relative;
            overflow: hidden;
            transition: var(--transition);
        }

        .header::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 4px;
            background: linear-gradient(to right, var(--primary), var(--success));
        }

        .header h1 {
            font-size: 2.5rem;
            margin-bottom: 10px;
            color: var(--text-color);
            font-weight: 700;
            transition: var(--transition);
        }

        .header p {
            font-size: 1.1rem;
            color: var(--text-secondary);
            max-width: 600px;
            margin: 0 auto;
            transition: var(--transition);
        }

        .theme-toggle {
            position: fixed;
            top: 30px;
            right: 30px;
            width: 50px;
            height: 50px;
            border-radius: 50%;

            background: var(--card-bg);
            border: none;
            z-index: 98;

            display: flex;
            align-items: center;
            justify-content: center;
            cursor: pointer;
            flex-direction: column;

            transition: var(--transition);
            box-shadow: var(--shadow);
        }

        .theme-toggle:hover {
            transform: rotate(15deg);
        }

        .theme-toggle i {
            font-size: 1.3rem;
            color: var(--text-color);
            transition: var(--transition);
        }

        .controls {
            display: block;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 30px;
            flex-wrap: wrap;
            gap: 15px;
        }

        .search-container {
            flex: 1;
            min-width: 300px;
            position: relative;
        }

        .search-box {
            width: 100%;
            padding: 15px 50px 15px 20px;
            border: 2px solid var(--border-color);
            border-radius: 50px;
            font-size: 1rem;
            transition: var(--transition);
            background: var(--card-bg);
            color: var(--text-color);
        }

        .search-box:focus {
            outline: none;
            border-color: var(--primary);
            box-shadow: 0 0 0 3px rgba(67, 97, 238, 0.2);
        }

        .search-icon {
            position: absolute;
            right: 20px;
            top: 50%;
            transform: translateY(-50%);
            color: var(--text-secondary);
            font-size: 1.2rem;
            transition: var(--transition);
        }

        .filter-container {
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
        }

        .filter-btn {
            background: var(--card-bg);
            border: 2px solid var(--border-color);
            padding: 10px 20px;
            border-radius: 50px;
            font-size: 0.9rem;
            cursor: pointer;
            transition: var(--transition);
            display: flex;
            align-items: center;
            gap: 8px;
            color: var(--text-color);
        }

        .filter-btn:hover, .filter-btn.active {
            background: var(--primary);
            color: white;
            border-color: var(--primary);
        }

        .stats {
            display: flex;
            flex-wrap: wrap;
            flex-direction: row;
            justify-content: center;
        }

        .stat-card {
            background: var(--card-bg);
            padding: 5px;
            border-radius: var(--border-radius);
            display: flex;
            align-items: center;
            transition: var(--transition);
        }

        .stat-card i {
            font-size: 1.5rem;
            color: var(--primary);
        }

        .book-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
            gap: 25px;
            margin-bottom: 40px;
        }

        .book-card {
            background: var(--card-bg);
            border-radius: var(--border-radius);
            overflow: hidden;
            box-shadow: var(--shadow);
            transition: var(--transition);
            position: relative;
            display: flex;
            flex-direction: column;
        }

        .book-card:hover {
            transform: translateY(-5px);
            box-shadow: 0 10px 25px rgba(0, 0, 0, 0.15);
        }

        .book-cover {
            width: 100%;
            height: 200px;
            object-fit: contain;
            display: block;
            border-bottom: 1px solid transparent;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            padding-bottom: 8px;
        }

        .book-card-content {
            padding: 5px 20px;
            flex-grow: 1;
            display: flex;
            flex-direction: column;
        }

        .book-title {
            font-size: 1.2rem;
            font-weight: 600;
            color: var(--text-color);
            line-height: 1.4;
            display: -webkit-box;
            -webkit-line-clamp: 2;
            -webkit-box-orient: vertical;
            transition: var(--transition);
            width: 100%;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }

        .book-author {
            font-size: 0.9rem;
            color: var(--text-secondary);
            transition: var(--transition);
            width: 100%;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }

        .book-tags {
            position: absolute;
            bottom: 0;
            left: 0;
            right: 0;
            background: linear-gradient(to top, rgba(0,0,0,0.8), transparent);
            padding: 20px 15px 10px;
            transform: translateY(100%);
            opacity: 0;
            transition: all 0.3s ease;
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
        }

        .book-card:hover .book-tags {
            transform: translateY(0);
            opacity: 1;
        }

        .book-tag {
            background: var(--border-color);
            color: var(--text-color);
            padding: 4px 10px;
            border-radius: 20px;
            font-size: 0.75rem;
            font-weight: 500;
            transition: var(--transition);
        }

        .book-tag:hover {
            background: var(--primary);
            color: white;
            cursor: pointer;
        }

        .book-meta {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-top: auto;
            font-size: 0.85rem;
            color: var(--text-secondary);
            transition: var(--transition);
        }

        .book-format {
            background: var(--primary-light);
            color: white;
            padding: 4px 10px;
            border-radius: 20px;
            font-size: 0.75rem;
            font-weight: 500;
        }

        .book-link {
            display: block;
            text-decoration: none;
            color: inherit;
        }

        .reading-controls {
            position: fixed;
            bottom: 30px;
            right: 30px;
            display: flex;
            flex-direction: column;
            gap: 10px;
            z-index: 99;
        }

        .control-name {
            font-size: 0.5rem;
        }

        .control-btn {
            width: 50px;
            height: 50px;
            border-radius: 50%;
            background: var(--primary);
            color: white;
            display: flex;
            align-items: center;
            justify-content: center;
            cursor: pointer;
            transition: var(--transition);
            box-shadow: var(--shadow);
            border: none;
            flex-direction: column;
        }

        .control-btn:hover {
            background: var(--secondary);
            transform: scale(1.1);
        }

        .footer {
            text-align: center;
            padding: 10px 0;
            color: var(--text-secondary);
            font-size: 0.9rem;
            border-top: 1px solid var(--border-color);
            transition: var(--transition);
        }

        .empty-state {
            text-align: center;
            padding: 60px 20px;
            color: var(--text-secondary);
        }

        .empty-state i {
            font-size: 4rem;
            margin-bottom: 20px;
            color: var(--border-color);
        }

        .book-icon {
            width: 100%;
            height: 120px;
            background: linear-gradient(135deg, var(--primary-light), var(--primary));
            display: flex;
            align-items: center;
            justify-content: center;
            color: white;
            font-size: 2.5rem;
        }

        .tag-cloud {
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            margin-bottom: 30px;
            justify-content: center;
        }

        .tag-cloud-item {
            background: var(--card-bg);
            padding: 8px 16px;
            border-radius: 20px;
            font-size: 0.9rem;
            cursor: pointer;
            transition: var(--transition);
            box-shadow: var(--shadow);
            color: var(--text-color);
        }

        .tag-cloud-item:hover, .tag-cloud-item.active {
            background: var(--primary);
            color: white;
        }

        @media (max-width: 768px) {
            .book-grid {
                grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
            }
            
            .header h1 {
                font-size: 2rem;
            }
            
            .stats {
                flex-direction: row;
                align-items: center;
            }
            
            .controls {
                flex-direction: column;
                align-items: stretch;
            }
            
            .search-container {
                min-width: 100%;
            }
        }

        .kindle-mode header, .kindle-mode .tag-cloud-item, .kindle-mode .book-cover, .kindle-mode .book-card, .kindle-mode .theme-toggle, .kindle-mode .control-btn, .kindle-mode .search-box {
            box-shadow: none;
            border-radius: inherit;
        }

        .kindle-mode .container {
            padding: 0;
        }

        .kindle-mode .header {
            margin-bottom: 0;
        }

        .kindle-mode .theme-toggle {
            border: 1px solid;
        }

        @media (max-width: 480px) {
            .book-grid {
                grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
            }
            
            .header {
                padding: 30px 15px;
            }
        }
    </style>
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
            return
        else:
            # 清理基础目录
            if os.path.exists(self.base_directory):
                shutil.rmtree(self.base_directory)
                print(f"Cleaned up library base directory: {self.base_directory}")
