import os
import tempfile
from datetime import datetime

from .processor import EPUBProcessor

class EPUBLibrary:
    """EPUB图书馆类，管理多本书籍"""
    
    def __init__(self, output_dir=None):
        self.books = {}  # 存储所有书籍信息，使用哈希作为键
        
        # 创建基础目录用于服务器
        if output_dir is not None and os.path.exists(output_dir):
            self.base_directory = output_dir
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
            
            # 创建网页界面
            web_dir = processor.create_web_interface()
            
            # 存储书籍信息
            book_info = processor.get_book_info()
            self.books[book_info['hash']] = {
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
<head><meta charset="UTF-8"><meta name="viewport"content="width=device-width, initial-scale=1.0"><title>EPUB Library</title><link rel="stylesheet"href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
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
            font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
            line-height: 1.6;
            color: var(--text-color);
            background: var(--bg-color);
            min-height: 100vh;
            transition: var(--transition);
            padding: 0 20px;
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
            gap: 20px;
            flex-wrap: wrap;
            flex-direction: row;
            justify-content: center;
        }

        .stat-card {
            background: var(--card-bg);
            padding: 15px 25px;
            border-radius: var(--border-radius);
            display: flex;
            align-items: center;
            gap: 10px;
            transition: var(--transition);
        }

        .stat-card i {
            font-size: 1.5rem;
            color: var(--primary);
        }

        .book-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
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
        }

        .book-card-content {
            padding: 20px;
            flex-grow: 1;
            display: flex;
            flex-direction: column;
        }

        .book-title {
            font-size: 1.2rem;
            font-weight: 600;
            margin-bottom: 8px;
            color: var(--text-color);
            line-height: 1.4;
            display: -webkit-box;
            -webkit-line-clamp: 2;
            -webkit-box-orient: vertical;
            overflow: hidden;
            transition: var(--transition);
        }

        .book-author {
            font-size: 0.9rem;
            color: var(--text-secondary);
            margin-bottom: 15px;
            transition: var(--transition);
        }

        .book-tags {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin-bottom: 15px;
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
            margin-top: 20px;
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
                grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
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

        @media (max-width: 480px) {
            .book-grid {
                grid-template-columns: 1fr;
            }
            
            .header {
                padding: 30px 15px;
            }
        }
    </style>
</head>
<body>
"""
        all_tags = []
        for book_hash, book_info in self.books.items():
            cur_tags = book_info['tags']
            if cur_tags:
                all_tags.extend(cur_tags)

        library_html += f"""
    <div class="container">
        <header class="header">
            <div class="theme-toggle" id="themeToggle">
                <i class="fas fa-moon"></i>
            </div>
            <h1><i class="fas fa-book-open"></i> EPUB Library</h1>
            <div class="stats">
                <div class="stat-card">
                    <i class="fas fa-book"></i>
                    <div>
                        <div class="stat-value">{len(self.books)}</div>
                    </div>
                </div>
                <div class="stat-card">
                    <i class="fas fa-tags"></i>
                    <div>
                        <div class="stat-value">{len(all_tags)}</div>
                    </div>
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
        for tag in all_tags:
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
            <a href="/book/{book_hash}/" class="book-link">
                <img src="/book/{book_hash}/{book_info['cover']}" alt="cover" class="book-cover"/>
                <div class="book-card-content">
                    <h3 class="book-title">{book_info['title']}</h3>
                    <div class="book-author">{" & ".join(book_info['authors']) if book_info['authors'] else ""}</div>
                    <div class="book-tags">
            """
            if book_info['tags']:
                for tag in book_info['tags']:
                    library_html += f"""
                        <span class="book-tag">{tag}</span>
"""
            library_html += """
                    </div>
                </div>
            </a>
        </div>
"""      
        library_html += f"""
    </div>
    <div class="reading-controls">
        <button class="control-btn" id="scrollToTopBtn">
            <i class="fas fa-arrow-up"></i>
        </button>
    </div>
</div>
<footer class="footer">
    <p>EPUB Library &copy; {datetime.now().year} | Powered by <a href="https://github.com/dfface/epub-browser" target="_blank">epub-browser</a></p>
</footer>
"""
        library_html += """<script>
        // 主题切换功能
        document.addEventListener('DOMContentLoaded', function() {
            const themeToggle = document.getElementById('themeToggle');
            const themeIcon = themeToggle.querySelector('i');
            
            // 检查本地存储中的主题设置
            const currentTheme = localStorage.getItem('theme') || 'light';
            
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
                    localStorage.setItem('theme', 'dark');
                } else {
                    themeIcon.classList.remove('fa-sun');
                    themeIcon.classList.add('fa-moon');
                    localStorage.setItem('theme', 'light');
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
        with open(os.path.join(self.base_directory, 'index.html'), 'w', encoding='utf-8') as f:
            f.write(library_html)
