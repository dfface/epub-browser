from datetime import datetime
import os
import zipfile
import tempfile
import shutil
import xml.etree.ElementTree as ET
import re
import hashlib

class EPUBProcessor:
    """处理EPUB文件的类"""
    
    def __init__(self, epub_path, output_dir=None):
        self.epub_path = epub_path
        self.book_hash = hashlib.md5(epub_path.encode()).hexdigest()[:8]  # 使用哈希值作为标识
        
        if output_dir:
            # 使用用户指定的输出目录
            self.temp_dir = tempfile.mkdtemp(prefix='epub_', dir=output_dir)
        else:
            # 使用系统临时目录
            self.temp_dir = tempfile.mkdtemp(prefix='epub_')
            
        self.extract_dir = os.path.join(self.temp_dir, 'extracted')
        self.web_dir = os.path.join(self.temp_dir, 'web')
        self.book_title = "EPUB Book"
        self.authors = None
        self.tags = None
        self.cover_info = None
        self.chapters = []
        self.toc = []  # 存储目录结构
        self.resources_base = "resources"  # 资源文件的基础路径
        
    def extract_epub(self):
        """解压EPUB文件"""
        try:
            with zipfile.ZipFile(self.epub_path, 'r') as zip_ref:
                zip_ref.extractall(self.extract_dir)
            # print(f"EPUB file extracted to: {self.extract_dir}")
            return True
        except Exception as e:
            print(f"Failed to extract EPUB file: {e}")
            return False
    
    def parse_container(self):
        """解析container.xml获取内容文件路径"""
        container_path = os.path.join(self.extract_dir, 'META-INF', 'container.xml')
        if not os.path.exists(container_path):
            print("container.xml file not found")
            return None
            
        try:
            tree = ET.parse(container_path)
            root = tree.getroot()
            # 查找rootfile元素
            ns = {'ns': 'urn:oasis:names:tc:opendocument:xmlns:container'}
            rootfile = root.find('.//ns:rootfile', ns)
            if rootfile is not None:
                return rootfile.get('full-path')
        except Exception as e:
            print(f"Failed to parse container.xml: {e}")
            
        return None
    
    def find_cover_info(self, opf_tree, namespaces):
        """
        在 OPF 文件中查找封面信息
        """
        # 方法1: 查找 meta 标签中声明的封面
        cover_id = None
        meta_elements = opf_tree.findall('.//opf:metadata/opf:meta', namespaces)
        for meta in meta_elements:
            if meta.get('name') in ['cover', 'cover-image']:
                cover_id = meta.get('content')
                break
        
        # 方法2: 查找 manifest 中的封面项
        manifest_items = opf_tree.findall('.//opf:manifest/opf:item', namespaces)
        
        # 优先使用 meta 标签中指定的封面
        if cover_id:
            for item in manifest_items:
                if item.get('id') == cover_id:
                    return {
                        'href': item.get('href'),
                        'media-type': item.get('media-type'),
                        'id': item.get('id')
                    }
        
        # 方法3: 通过文件名模式查找
        cover_patterns = ['cover', 'Cover', 'COVER', 'titlepage', 'TitlePage']
        for item in manifest_items:
            media_type = item.get('media-type', '')
            href = item.get('href', '')
            
            # 检查是否是图片文件
            if media_type.startswith('image/'):
                # 检查文件名是否匹配封面模式
                if any(pattern in href for pattern in cover_patterns):
                    return {
                        'href': href,
                        'media-type': media_type,
                        'id': item.get('id')
                    }
        
        # 方法4: 查找第一个图片作为备选
        for item in manifest_items:
            media_type = item.get('media-type', '')
            if media_type.startswith('image/'):
                return {
                    'href': item.get('href'),
                    'media-type': media_type,
                    'id': item.get('id')
                }
        
        return None

    def find_ncx_file(self, opf_path, manifest):
        """查找NCX文件路径"""
        opf_dir = os.path.dirname(opf_path)
        
        # 首先查找OPF中明确指定的toc
        try:
            tree = ET.parse(os.path.join(self.extract_dir, opf_path))
            root = tree.getroot()
            ns = {'opf': 'http://www.idpf.org/2007/opf'}
            
            spine = root.find('.//opf:spine', ns)
            if spine is not None:
                toc_id = spine.get('toc')
                if toc_id and toc_id in manifest:
                    ncx_path = os.path.join(opf_dir, manifest[toc_id]['href'])
                    if os.path.exists(os.path.join(self.extract_dir, ncx_path)):
                        return ncx_path
        except Exception as e:
            print(f"Failed to find toc attribute: {e}")
        
        # 如果没有明确指定，查找media-type为application/x-dtbncx+xml的文件
        for item_id, item in manifest.items():
            if item['media_type'] == 'application/x-dtbncx+xml':
                ncx_path = os.path.join(opf_dir, item['href'])
                if os.path.exists(os.path.join(self.extract_dir, ncx_path)):
                    return ncx_path
        
        # 最后，尝试查找常见的NCX文件名
        common_ncx_names = ['toc.ncx', 'nav.ncx', 'ncx.ncx']
        for name in common_ncx_names:
            ncx_path = os.path.join(opf_dir, name)
            if os.path.exists(os.path.join(self.extract_dir, ncx_path)):
                return ncx_path
        
        return None
    
    def parse_ncx(self, ncx_path):
        """解析NCX文件获取目录结构"""
        ncx_full_path = os.path.join(self.extract_dir, ncx_path)
        if not os.path.exists(ncx_full_path):
            print(f"NCX file not found: {ncx_full_path}")
            return []
            
        try:
            # 读取文件内容并注册命名空间
            with open(ncx_full_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 注册命名空间
            ET.register_namespace('', 'http://www.daisy.org/z3986/2005/ncx/')
            
            tree = ET.parse(ncx_full_path)
            root = tree.getroot()
            
            # 获取书籍标题（这一步应该在 opf 文件解析那里做）
            # doc_title = root.find('.//{http://www.daisy.org/z3986/2005/ncx/}docTitle/{http://www.daisy.org/z3986/2005/ncx/}text')
            # if doc_title is not None and doc_title.text:
            #     self.book_title = doc_title.text
            
            # 解析目录
            nav_map = root.find('.//{http://www.daisy.org/z3986/2005/ncx/}navMap')
            if nav_map is None:
                return []
            
            toc = []
            
            # 递归处理navPoint
            def process_navpoint(navpoint, level=0):
                # 获取导航标签和内容源
                nav_label = navpoint.find('.//{http://www.daisy.org/z3986/2005/ncx/}navLabel/{http://www.daisy.org/z3986/2005/ncx/}text')
                content = navpoint.find('.//{http://www.daisy.org/z3986/2005/ncx/}content')
                
                if nav_label is not None and content is not None:
                    title = nav_label.text
                    src = content.get('src')
                    
                    # 处理可能的锚点
                    if '#' in src:
                        src = src.split('#')[0]
                    
                    if title and src:
                        # 将src路径转换为相对于EPUB根目录的完整路径
                        ncx_dir = os.path.dirname(ncx_path)
                        full_src = os.path.normpath(os.path.join(ncx_dir, src))
                        
                        toc.append({
                            'title': title,
                            'src': full_src,
                            'level': level
                        })
                
                # 处理子navPoint
                child_navpoints = navpoint.findall('{http://www.daisy.org/z3986/2005/ncx/}navPoint')
                for child in child_navpoints:
                    process_navpoint(child, level + 1)
            
            # 处理所有顶级navPoint
            top_navpoints = nav_map.findall('{http://www.daisy.org/z3986/2005/ncx/}navPoint')
            for navpoint in top_navpoints:
                process_navpoint(navpoint, 0)
            
            # print(f"Parsed NCX table of contents items: {[(t['title'], t['src']) for t in toc]}")
            return toc
            
        except Exception as e:
            print(f"Failed to parse NCX file: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def parse_opf(self, opf_path):
        """解析OPF文件获取书籍信息和章节列表"""
        opf_full_path = os.path.join(self.extract_dir, opf_path)
        if not os.path.exists(opf_full_path):
            print(f"OPF file not found: {opf_full_path}")
            return False
            
        try:
            tree = ET.parse(opf_full_path)
            root = tree.getroot()
            
            # 获取命名空间
            ns = {'opf': 'http://www.idpf.org/2007/opf',
                  'dc': 'http://purl.org/dc/elements/1.1/'}
            
            # 获取书名
            title_elem = root.find('.//dc:title', ns)
            if title_elem is not None and title_elem.text:
                self.book_title = title_elem.text
            
            # 获取作者名
            authors = tree.findall('.//dc:creator', ns)
            self.authors = [author.text for author in authors] if authors else None

            # 获取标签
            tags = tree.findall('.//dc:subject', ns)
            self.tags = [tag.text for tag in tags] if tags else None

            # 获取封面
            cover_info = self.find_cover_info(tree, ns)
            self.cover_info = cover_info
                
            # 获取manifest（所有资源）
            manifest = {}
            opf_dir = os.path.dirname(opf_path)
            for item in root.findall('.//opf:item', ns):
                item_id = item.get('id')
                href = item.get('href')
                media_type = item.get('media-type', '')
                # 构建相对于EPUB根目录的完整路径
                full_path = os.path.normpath(os.path.join(opf_dir, href)) if href else None
                manifest[item_id] = {
                    'href': href,
                    'media_type': media_type,
                    'full_path': full_path
                }
            
            # 查找并解析NCX文件
            ncx_path = self.find_ncx_file(opf_path, manifest)
            if ncx_path:
                self.toc = self.parse_ncx(ncx_path)
                # print(f"Found {len(self.toc)} table of contents items from NCX file")
            
            # 获取spine（阅读顺序）
            spine = root.find('.//opf:spine', ns)
            if spine is not None:
                for itemref in spine.findall('opf:itemref', ns):
                    idref = itemref.get('idref')
                    if idref in manifest:
                        item = manifest[idref]
                        # 只处理HTML/XHTML内容
                        if item['media_type'] in ['application/xhtml+xml', 'text/html']:
                            # 尝试从toc中查找对应的标题
                            title = self.find_chapter_title(item['full_path'])
                            
                            self.chapters.append({
                                'id': idref,
                                'path': item['full_path'],
                                'title': title or f"Chapter {len(self.chapters) + 1}"
                            })
            
            # print(f"Found {len(self.chapters)} chapters")
            # print(f"Chapter list: {[(c['title'], c['path']) for c in self.chapters]}")
            return True
            
        except Exception as e:
            print(f"Failed to parse OPF file: {e}")
            return False
    
    def find_chapter_title(self, chapter_path):
        """根据章节路径在toc中查找对应的标题"""
        # 先尝试精确匹配
        for toc_item in self.toc:
            if toc_item['src'] == chapter_path:
                return toc_item['title']
        
        # 如果直接匹配失败，尝试基于文件名匹配
        chapter_filename = os.path.basename(chapter_path)
        for toc_item in self.toc:
            toc_filename = os.path.basename(toc_item['src'])
            if toc_filename == chapter_filename:
                return toc_item['title']
        
        # 尝试规范化路径后再匹配
        normalized_chapter_path = os.path.normpath(chapter_path)
        for toc_item in self.toc:
            normalized_toc_path = os.path.normpath(toc_item['src'])
            if normalized_toc_path == normalized_chapter_path:
                return toc_item['title']
        
        # print(f"Chapter title not found: {chapter_path}")
        return None
    
    def create_web_interface(self):
        """创建网页界面"""
        os.makedirs(self.web_dir, exist_ok=True)
        
        # 创建主页面
        self.create_index_page()
        
        # 创建章节页面
        self.create_chapter_pages()
        
        # 复制资源文件（CSS、图片、字体等）
        self.copy_resources()
        
        # print(f"Web interface created at: {self.web_dir}")
        return self.web_dir
    
    def create_index_page(self):
        """创建章节索引页面"""
        index_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{self.book_title}</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
"""
        index_html += """
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
            font-size: 2.2rem;
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
            position: absolute;
            top: 30px;
            right: 30px;
            background: var(--card-bg);
            border: none;

            width: 50px;
            height: 50px;
            border-radius: 50%;
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

        .reading-controls {
            position: fixed;
            bottom: 30px;
            right: 30px;
            display: flex;
            flex-direction: column;
            gap: 10px;
            z-index: 20;
        }

        .reading-controls .control-btn, .top-controls .control-btn {
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

        .reading-controls .control-btn:hover, .top-controls .control-btn:hover {
            background: var(--secondary);
            transform: scale(1.1);
        }

        .breadcrumb {
            display: flex;
            align-items: center;
            margin-bottom: 30px;
            padding: 15px 20px;
            background: var(--card-bg);
            border-radius: var(--border-radius);
            box-shadow: var(--shadow);
            transition: var(--transition);
        }

        .breadcrumb a {
            text-decoration: none;
            color: var(--text-secondary);
            transition: var(--transition);
            display: flex;
            align-items: center;
        }

        .breadcrumb a:hover {
            color: var(--primary);
        }

        .breadcrumb-separator {
            margin: 0 10px;
            color: var(--text-secondary);
        }

        .breadcrumb-current {
            color: var(--text-color);
            font-weight: 600;
        }

        .book-info {
            display: flex;
            gap: 25px;
            margin-bottom: 30px;
            flex-wrap: wrap;
        }

        .book-cover {
            flex: 0 0 200px;
            height: 280px;
            border-radius: var(--border-radius);
            overflow: hidden;
            box-shadow: var(--shadow);
        }

        .book-cover img {
            width: 100%;
            height: 100%;
            object-fit: cover;
        }

        .book-details {
            flex: 1;
            min-width: 300px;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
        }

        .book-meta {
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            margin-bottom: 20px;
        }

        .book-tag {
            background: var(--border-color);
            color: var(--text-color);
            padding: 6px 12px;
            border-radius: 20px;
            font-size: 0.8rem;
            font-weight: 500;
            transition: var(--transition);
        }

        .book-actions {
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
        }

        .action-btn {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            background: var(--primary);
            color: white;
            padding: 10px 20px;
            border-radius: 50px;
            font-weight: 600;
            text-decoration: none;
            transition: var(--transition);
            border: none;
            cursor: pointer;
        }

        .action-btn:hover {
            background: var(--secondary);
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(67, 97, 238, 0.4);
        }

        .action-btn.secondary {
            background: var(--card-bg);
            color: var(--text-color);
            border: 2px solid var(--border-color);
        }

        .action-btn.secondary:hover {
            background: var(--border-color);
            transform: translateY(-2px);
        }

        .toc-container {
            background: var(--card-bg);
            border-radius: var(--border-radius);
            box-shadow: var(--shadow);
            overflow: hidden;
            transition: var(--transition);
        }

        .toc-header {
            padding: 20px;
            border-bottom: 1px solid var(--border-color);
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .toc-header h2 {
            color: var(--text-color);
            font-size: 1.5rem;
            transition: var(--transition);
        }

        .chapter-count {
            background: var(--primary);
            color: white;
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 0.9rem;
            font-weight: 600;
        }

        .chapter-list {
            list-style-type: none;
            padding: 0;
            max-height: 500px;
            overflow-y: auto;
        }

        .chapter-list li {
            border-bottom: 1px solid var(--border-color);
            transition: var(--transition);
        }

        .chapter-list li:last-child {
            border-bottom: none;
        }

        .chapter-list a {
            text-decoration: none;
            color: var(--text-color);
            display: flex;
            align-items: center;
            padding: 15px 20px;
            transition: var(--transition);
        }

        .chapter-list a:hover {
            background: var(--border-color);
        }

        .chapter-icon {
            margin-right: 12px;
            color: var(--text-secondary);
            font-size: 1.1rem;
            width: 24px;
            text-align: center;
        }

        .chapter-title {
            flex: 1;
        }

        .chapter-page {
            color: var(--text-secondary);
            font-size: 0.9rem;
        }

        .toc-level-0 { margin-left: 0px; }
        .toc-level-1 { margin-left: 25px; font-size: 0.95em; }
        .toc-level-2 { margin-left: 50px; font-size: 0.9em; }
        .toc-level-3 { margin-left: 75px; font-size: 0.85em; }

        .toc-level-1 .chapter-icon { color: var(--success); }
        .toc-level-2 .chapter-icon { color: var(--warning); }
        .toc-level-3 .chapter-icon { color: var(--danger); }

        .footer {
            text-align: center;
            padding: 10px 0;
            color: var(--text-secondary);
            font-size: 0.9rem;
            border-top: 1px solid var(--border-color);
            margin-top: 20px;
            transition: var(--transition);
        }

        @media (max-width: 768px) {
            .header h1 {
                font-size: 1.8rem;
            }
            
            .book-info {
                flex-direction: column;
            }
            
            .book-cover {
                align-self: center;
            }
            
            .book-actions {
                justify-content: center;
            }
        }

        @media (max-width: 480px) {
            .header {
                padding: 30px 15px;
            }
            
            .breadcrumb {
                flex-wrap: wrap;
            }
            
            .breadcrumb-separator {
                margin: 0 5px;
            }
            
            .toc-header {
                flex-direction: column;
                gap: 10px;
                align-items: flex-start;
            }
        }
    </style>
</head>
<body>
"""
        index_html += f"""
<div class="container">
    <div class="breadcrumb header">
        <a href="/"><i class="fas fa-home"></i><span style="margin-left: 8px;">Home</span></a>
        <span class="breadcrumb-separator">/</span>
        <span class="breadcrumb-current">{self.book_title}</span>
    </div>
    
    <div class="toc-container">
        <div class="toc-header">
            <h2>Table of contents</h2>
            <div class="chapter-count">total: {len(self.chapters)}</div>
        </div>
        <ul class="chapter-list">
"""
        
        # 如果有详细的toc信息，使用toc生成目录
        if self.toc:
            # 创建章节路径到索引的映射
            chapter_index_map = {}
            for i, chapter in enumerate(self.chapters):
                chapter_index_map[chapter['path']] = i
            
            # print(f"Chapter index mapping: {chapter_index_map}")
            
            # 根据toc生成目录
            for toc_item in self.toc:
                level_class = f"toc-level-{min(toc_item.get('level', 0), 3)}"
                chapter_index = chapter_index_map.get(toc_item['src'])
                
                if chapter_index is not None:
                    index_html += f'        <li class="{level_class}"><a href="/book/{self.book_hash}/chapter_{chapter_index}.html">{toc_item["title"]}</a></li>\n'
                else:
                    print(f"Chapter index not found: {toc_item['src']}")
        else:
            # 回退到简单章节列表
            for i, chapter in enumerate(self.chapters):
                index_html += f'        <li><a href="/book/{self.book_hash}/chapter_{i}.html">{chapter["title"]}</a></li>\n'
        
        index_html += f"""    </ul>
    </div>
</div>
<div class="theme-toggle" id="themeToggle">
    <i class="fas fa-moon"></i>
</div>
<footer class="footer">
    <p>EPUB Library &copy; {datetime.now().year} | Powered by <a href="https://github.com/dfface/epub-browser" target="_blank">epub-browser</a></p>
</footer>
"""
        index_html += """<script>
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
        
        with open(os.path.join(self.web_dir, 'index.html'), 'w', encoding='utf-8') as f:
            f.write(index_html)
    
    def create_chapter_pages(self):
        """创建章节页面"""
        for i, chapter in enumerate(self.chapters):
            chapter_path = os.path.join(self.extract_dir, chapter['path'])
            
            if os.path.exists(chapter_path):
                try:
                    # 读取章节内容
                    with open(chapter_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    # 处理HTML内容，修复资源链接并提取样式
                    body_content, style_links = self.process_html_content(content, chapter['path'])
                    
                    # 创建章节页面
                    chapter_html = self.create_chapter_template(body_content, style_links, i, chapter['title'])
                    
                    with open(os.path.join(self.web_dir, f'chapter_{i}.html'), 'w', encoding='utf-8') as f:
                        f.write(chapter_html)
                        
                except Exception as e:
                    print(f"Failed to process chapter {chapter['path']}: {e}")
    
    def process_html_content(self, content, chapter_path):
        """处理HTML内容，修复资源链接并提取样式"""
        # 提取head中的样式链接
        style_links = self.extract_style_links(content, chapter_path)
        
        # 提取body内容
        body_content = self.clean_html_content(content)
        
        # 修复body中的图片链接
        body_content = self.fix_image_links(body_content, chapter_path)
        
        # 修复body中的其他资源链接
        body_content = self.fix_other_links(body_content, chapter_path)
        
        return body_content, style_links
    
    def extract_style_links(self, content, chapter_path):
        """从head中提取样式链接"""
        style_links = []
        
        # 匹配head标签
        head_match = re.search(r'<head[^>]*>(.*?)</head>', content, re.DOTALL | re.IGNORECASE)
        if head_match:
            head_content = head_match.group(1)
            
            # 匹配link标签（CSS样式表）
            link_pattern = r'<link[^>]+rel=["\']stylesheet["\'][^>]*>'
            links = re.findall(link_pattern, head_content, re.IGNORECASE)
            
            for link in links:
                # 提取href属性
                href_match = re.search(r'href=["\']([^"\']+)["\']', link)
                if href_match:
                    href = href_match.group(1)
                    # 如果已经是绝对路径，则不处理
                    if href.startswith(('http://', 'https://', '/')):
                        style_links.append(link)
                    else:
                        # 计算相对于EPUB根目录的完整路径
                        chapter_dir = os.path.dirname(chapter_path)
                        full_href = os.path.normpath(os.path.join(chapter_dir, href))
                        
                        # 转换为web资源路径
                        web_href = f"{self.resources_base}/{full_href}"
                        
                        # 替换href属性
                        fixed_link = link.replace(f'href="{href}"', f'href="{web_href}"')
                        style_links.append(fixed_link)
            
            # 匹配style标签
            style_pattern = r'<style[^>]*>.*?</style>'
            styles = re.findall(style_pattern, head_content, re.DOTALL)
            style_links.extend(styles)
        
        return '\n        '.join(style_links)
    
    def clean_html_content(self, content):
        """清理HTML内容"""
        # 提取body内容（如果存在）
        if '<body' in content.lower():
            try:
                # 提取body内容
                start = content.lower().find('<body')
                start = content.find('>', start) + 1
                end = content.lower().find('</body>')
                content = content[start:end]
            except:
                pass
        
        return content
    
    def fix_image_links(self, content, chapter_path):
        """修复图片链接"""
        # 匹配img标签的src属性
        img_pattern = r'<img[^>]+src="([^"]+)"[^>]*>'
        
        def replace_img_link(match):
            src = match.group(1)
            # 如果已经是绝对路径或数据URI，则不处理
            if src.startswith(('http://', 'https://', 'data:', '/')):
                return match.group(0)
            
            # 计算相对于EPUB根目录的完整路径
            chapter_dir = os.path.dirname(chapter_path)
            full_src = os.path.normpath(os.path.join(chapter_dir, src))
            
            # 转换为web资源路径
            web_src = f"{self.resources_base}/{full_src}"
            return match.group(0).replace(f'src="{src}"', f'src="{web_src}"')
        
        return re.sub(img_pattern, replace_img_link, content)
    
    def fix_other_links(self, content, chapter_path):
        """修复其他资源链接"""
        # 匹配其他可能包含资源链接的属性
        link_patterns = [
            (r'url\(\s*[\'"]?([^\'"\)]+)[\'"]?\s*\)', 'url'),  # CSS中的url()
        ]
        
        for pattern, attr_type in link_patterns:
            def replace_other_link(match):
                url = match.group(1)
                # 如果已经是绝对路径或数据URI，则不处理
                if url.startswith(('http://', 'https://', 'data:', '/')):
                    return match.group(0)
                
                # 计算相对于EPUB根目录的完整路径
                chapter_dir = os.path.dirname(chapter_path)
                full_url = os.path.normpath(os.path.join(chapter_dir, url))
                
                # 转换为web资源路径
                web_url = f"{self.resources_base}/{full_url}"
                return match.group(0).replace(url, web_url)
            
            content = re.sub(pattern, replace_other_link, content)
        
        return content
    
    def create_chapter_template(self, content, style_links, chapter_index, chapter_title):
        """创建章节页面模板"""
        prev_link = f'<a href="/book/{self.book_hash}/chapter_{chapter_index-1}.html" alt="previous"> <div class="control-btn"> <i class="fas fa-arrow-left"></i></div></a>' if chapter_index > 0 else ''
        next_link = f'<a href="/book/{self.book_hash}/chapter_{chapter_index+1}.html" alt="next"> <div class="control-btn"> <i class="fas fa-arrow-right"></i></div></a>' if chapter_index < len(self.chapters) - 1 else ''
        prev_link_mobile = f'<a href="/book/{self.book_hash}/chapter_{chapter_index-1}.html" alt="previous"> <div class="control-btn"> <i class="fas fa-arrow-left"></i><span>Previous</span></div></a>' if chapter_index > 0 else ''
        next_link_mobile = f'<a href="/book/{self.book_hash}/chapter_{chapter_index+1}.html" alt="next"> <div class="control-btn"> <i class="fas fa-arrow-right"></i><span>Next</span></div></a>' if chapter_index < len(self.chapters) - 1 else ''
        
        chapter_html =  f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{chapter_title} - {self.book_title}</title>
    {style_links}
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
"""
        chapter_html += """
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
            --content-bg: #ffffff;
            --content-text: #333333;
        }

        .dark-mode {
            /* 深色主题变量 */
            --bg-color: #121212;
            --card-bg: #1e1e1e;
            --text-color: #e9ecef;
            --text-secondary: #a0a0a0;
            --border-color: #2d2d2d;
            --header-bg: #1e1e1e;
            --content-bg: #1e1e1e;
            --content-text: #e9ecef;
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
            padding: 0 20px;
            transition: var(--transition);
            display: flex;
            flex-direction: column;
        }

        .container {
            max-width: 1000px;
            margin: 0 auto;
            flex: 1;
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

        .header-content {
            display: flex;
            justify-content: space-between;
            align-items: center;
            max-width: 1000px;
            margin: 0 auto;
            padding: 0 20px;
        }

        .theme-toggle {
            width: 50px;
            height: 50px;
            border-radius: 50%;

            background: var(--card-bg);
            border: none;

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

        .reading-progress-container {
            width: 100%;
            height: 5px;
            background: var(--border-color);
            position: fixed;
            top: 0;
            left: 0;
            z-index: 101;
        }

        .progress-bar {
            height: 100%;
            background: linear-gradient(to right, var(--primary), var(--success));
            width: 0%;
            transition: width 0.3s ease;
        }

        .toc-floating {
            position: fixed;
            top: 150px;
            right: 30px;
            width: 280px;
            background: var(--card-bg);
            border-radius: var(--border-radius);
            box-shadow: var(--shadow);
            transition: var(--transition);
            max-height: 70vh;
            overflow-y: auto;
            display: none;
            z-index: 88;
        }

        .toc-floating.active {
            display: block;
        }

        .toc-header {
            padding: 15px 20px;
            border-bottom: 1px solid var(--border-color);
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .toc-header h3 {
            color: var(--text-color);
            font-size: 1.1rem;
            transition: var(--transition);
        }

        .toc-close {
            background: none;
            border: none;
            color: var(--text-secondary);
            cursor: pointer;
            font-size: 1.2rem;
            transition: var(--transition);
        }

        .toc-close:hover {
            color: var(--primary);
        }

        .toc-list {
            list-style-type: none;
            padding: 10px 0;
        }

        .toc-item {
            padding: 8px 20px;
            transition: var(--transition);
        }

        .toc-item a {
            text-decoration: none;
            color: var(--text-secondary);
            font-size: 0.9rem;
            display: block;
            transition: var(--transition);
        }

        .toc-item a:hover {
            color: var(--primary);
        }

        .toc-item.active a {
            color: var(--primary);
            font-weight: 600;
        }

        .toc-level-1 { margin-left: 0; }
        .toc-level-2 { margin-left: 15px; font-size: 0.85em; }
        .toc-level-3 { margin-left: 30px; font-size: 0.8em; }

        .breadcrumb {
            display: flex;
            align-items: center;
            margin: 20px 0;
            padding: 15px 20px;
            background: var(--card-bg);
            border-radius: var(--border-radius);
            box-shadow: var(--shadow);
            transition: var(--transition);
        }

        .breadcrumb a {
            text-decoration: none;
            color: var(--text-secondary);
            transition: var(--transition);
            display: flex;
            align-items: center;
        }

        .breadcrumb a:hover {
            color: var(--primary);
        }

        .breadcrumb-separator {
            margin: 0 10px;
            color: var(--text-secondary);
        }

        .breadcrumb-current {
            color: var(--text-color);
            font-weight: 600;
        }

        .chapter-header {
            text-align: center;
            margin-bottom: 30px;
            padding: 20px;
            background: var(--card-bg);
            border-radius: var(--border-radius);
            box-shadow: var(--shadow);
            transition: var(--transition);
        }

        .chapter-title {
            font-size: 1.8rem;
            margin-bottom: 10px;
            color: var(--text-color);
            font-weight: 700;
            transition: var(--transition);
        }

        .book-title {
            font-size: 1.1rem;
            color: var(--text-secondary);
            transition: var(--transition);
        }

        .content-container {
            background: var(--content-bg);
            border-radius: var(--border-radius);
            box-shadow: var(--shadow);
            overflow: hidden;
            margin-bottom: 30px;
            transition: var(--transition);
        }

        .content {
            padding: 40px;
            color: var(--content-text);
            transition: var(--transition);
        }

        .content h2, .content h3, .content h4 {
            margin-top: 2rem;
            margin-bottom: 1rem;
            color: var(--text-color);
            transition: var(--transition);
        }

        .content h2 {
            font-size: 1.5rem;
            border-bottom: 2px solid var(--primary);
            padding-bottom: 0.5rem;
        }

        .content h3 {
            font-size: 1.3rem;
            border-left: 4px solid var(--success);
            padding-left: 1rem;
        }

        .content h4 {
            font-size: 1.1rem;
            border-left: 2px solid var(--warning);
            padding-left: 1rem;
        }

        .content p {
            margin-bottom: 1.2rem;
            line-height: 1.7;
        }

        .content img {
            max-width: 100%;
            height: auto;
            border-radius: 8px;
            box-shadow: 0 4px 15px rgba(0, 0, 0, 0.1);
            margin: 1.5rem 0;
        }

        .content code {
            background: var(--border-color);
            padding: 2px 6px;
            border-radius: 4px;
            font-family: 'Courier New', monospace;
            font-size: 0.9rem;
        }

        .content pre {
            background: var(--border-color);
            padding: 1.5rem;
            border-radius: 8px;
            overflow-x: auto;
            margin: 1.5rem 0;
        }

        .navigation {
            display: flex;
            justify-content: space-between;
            margin: 30px 0;
            padding: 20px;
            background: var(--card-bg);
            border-radius: var(--border-radius);
            box-shadow: var(--shadow);
            transition: var(--transition);
        }

        .navigation a {
            text-decoration: none;
        }

        .navigation .control-btn {
            display: flex;
            align-items: center;
            gap: 10px;
            padding: 12px 20px;
            background: var(--card-bg);
            color: var(--text-color);
            border-radius: 10px;
            text-decoration: none;
            font-weight: 600;
            transition: var(--transition);
            border: none;
            cursor: pointer;
        }

        .nav-btn:hover {
            background: var(--primary);
            color: var(--card-bg);
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(67, 97, 238, 0.4);
        }

        .footer {
            text-align: center;
            padding: 10px 0;
            color: var(--text-secondary);
            font-size: 0.9rem;
            margin-top: 20px;
            background: var(--header-bg);
            transition: var(--transition);
        }

        .top-controls {
            position: fixed;
            top: 30px;
            right: 30px;
            display: flex;
            flex-direction: column;
            gap: 10px;
            z-index: 22;
        }

        .reading-controls {
            position: fixed;
            bottom: 30px;
            right: 30px;
            display: flex;
            flex-direction: column;
            gap: 10px;
            z-index: 20;
        }

        .reading-controls a {
            text-decoration: none;
        }

        .reading-controls .control-btn,.top-controls .control-btn {
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

        .reading-controls .control-btn:hover, .top-controls .control-btn:hover {
            background: var(--secondary);
            transform: scale(1.1);
        }

        .font-controls {
            position: fixed;
            bottom: 150px;
            right: 20px;
            background: var(--card-bg);
            border-radius: var(--border-radius);
            padding: 15px;
            box-shadow: var(--shadow);
            display: none;
            flex-direction: column;
            gap: 10px;
            width: 150px;
            z-index: 88;
        }

        .font-controls.show {
            display: flex;
        }

        .font-size-control {
            display: flex;
            align-items: center;
            justify-content: space-between;
        }

        .font-size-btn {
            width: 35px;
            height: 35px;
            border-radius: 50%;
            background: var(--border-color);
            color: var(--text-color);
            display: flex;
            align-items: center;
            justify-content: center;
            cursor: pointer;
            transition: var(--transition);
            border: none;
        }

        .font-size-btn.active {
            background: var(--primary);
            color: white;
        }

        /* 移动端底部控件 */
        .mobile-controls {
            position: fixed;
            bottom: 0;
            left: 0;
            right: 0;
            background: var(--card-bg);
            box-shadow: 0 -2px 10px rgba(0, 0, 0, 0.1);
            display: none;
            justify-content: space-around;
            padding: 10px 0;
            z-index: 99;
        }

        .mobile-controls .control-btn {
            display: flex;
            flex-direction: column;
            align-items: center;
            background: none;
            border: none;
            color: var(--text-secondary);
            cursor: pointer;
            transition: var(--transition);
            padding: 8px 12px;
            border-radius: 8px;
            min-width: 60px;
        }

        .mobile-controls .control-btn:hover,
        .mobile-controls .control-btn.active {
            color: var(--primary);
            background: var(--border-color);
        }

        .mobile-controls .control-btn i {
            font-size: 1.2rem;
            margin-bottom: 4px;
        }

        .mobile-controls .control-btn span {
            font-size: 0.7rem;
        }

        .mobile-controls a {
            text-decoration: none;
        }

        /* 响应式设计 */

        @media (max-width: 768px) {
            .chapter-title {
                font-size: 1.5rem;
            }
            
            .navigation {
                flex-direction: column;
                gap: 15px;
                display: none;
            }
            
            .nav-btn {
                justify-content: center;
            }

            .top-controls {
                top: 20px;
                right: 20px;
                display: none;
            }
            
            .reading-controls {
                bottom: 20px;
                right: 20px;
                display: none;
            }
            
            .toc-floating {
                width: 90%;
                right: 5%;
                left: 5%;
                top: 20px;
            }

            .mobile-controls {
                display: flex;
            }

            .font-controls {
                bottom: 80px;
            }
        }

        @media (max-width: 480px) {
            .breadcrumb {
                flex-wrap: wrap;
            }
            
            .breadcrumb-separator {
                margin: 0 5px;
            }
            
            .content {
                padding: 20px;
            }
        }
    </style>
</head>
"""
        chapter_html +=f"""
<body>
    <div class="reading-progress-container">
        <div class="progress-bar" id="progressBar"></div>
    </div>

    <div class="top-controls">
        <div class="theme-toggle" id="themeToggle">
            <i class="fas fa-moon"></i>
        </div>

        <a href="/book/{self.book_hash}" alt="bookHome">
            <div class="control-btn">
                <i class="fas fa-book"></i>
            </div>
        </a>

        <div class="control-btn" id="tocToggle">
            <i class="fas fa-list"></i>
        </div>
    </div>

    <div class="toc-floating" id="tocFloating">
        <div class="toc-header">
            <h3>Toc</h3>
            <button class="toc-close" id="tocClose">
                <i class="fas fa-times"></i>
            </button>
        </div>
        <ul class="toc-list" id="tocList">
            <!-- 动态生成的目录将放在这里 -->
        </ul>
    </div>

    <div class="container">
        <div class="breadcrumb header">
            <a href="/" alt="home"><i class="fas fa-home"></i><span style="margin-left:8px;">Home</span></a>
            <span class="breadcrumb-separator">/</span>
            <a href="/book/{self.book_hash}" alt="bookHome">{self.book_title}</a>
            <span class="breadcrumb-separator">/</span>
            <span class="breadcrumb-current">{chapter_title}</span>
        </div>

        <div class="content-container">
            <article class="content" id="content">
            {content}
            </article>
        </div>

        <div class="navigation">
            {prev_link}
            <a href="/" alt="home">
                <div class="control-btn">
                    <i class="fas fa-home"></i>
                </div>
            </a>
            {next_link}
        </div>
    </div>

    <div class="font-controls" id="fontControls">
        <div class="font-size-control">
            <span>Font Size</span>
        </div>
        <div class="font-size-control">
            <div class="font-size-btn font-small" data-size="small">A</div>
            <div class="font-size-btn font-medium active" data-size="medium">A</div>
            <div class="font-size-btn font-large" data-size="large">A</div>
        </div>
    </div>

    <div class="reading-controls">
        <div class="control-btn" id="fontControlBtn">
            <i class="fas fa-font"></i>
        </div>
        <div class="control-btn" id="scrollToTopBtn">
            <i class="fas fa-arrow-up"></i>
        </div>
    </div>

    <!-- 移动端控件 -->
    <div class="mobile-controls">
        <div class="control-btn" id="mobileTocBtn">
            <i class="fas fa-list"></i>
            <span>Toc</span>
        </div>
        <div class="control-btn" id="mobileThemeBtn">
            <i class="fas fa-moon"></i>
            <span>Theme</span>
        </div>
        {prev_link_mobile}
        <a href="/" alt="home">
            <div class="control-btn">
                <i class="fas fa-home"></i>
                <span>Home</span>
            </div>
        </a>
        {next_link_mobile}
        <div class="control-btn" id="mobileFontBtn">
            <i class="fas fa-font"></i>
            <span>Font Size</span>
        </div>
        <div class="control-btn" id="mobileTopBtn">
            <i class="fas fa-arrow-up"></i>
            <span>Top</span>
        </div>
    </div>

    <footer class="footer">
        <p>EPUB Library &copy; {datetime.now().year} | Powered by <a href="https://github.com/dfface/epub-browser" target="_blank">epub-browser</a></p>
    </footer>
"""
        chapter_html += """
<script>
        // 主题切换功能
        document.addEventListener('DOMContentLoaded', function() {
            const themeToggle = document.getElementById('themeToggle');
            const mobileThemeBtn = document.getElementById('mobileThemeBtn');
            const themeIcon = themeToggle.querySelector('i');
            
            // 检查本地存储中的主题设置
            const currentTheme = localStorage.getItem('theme') || 'light';
            
            // 应用保存的主题
            if (currentTheme === 'dark') {
                document.body.classList.add('dark-mode');
                themeIcon.classList.remove('fa-moon');
                themeIcon.classList.add('fa-sun');
                mobileThemeBtn.querySelector('i').classList.remove('fa-moon');
                mobileThemeBtn.querySelector('i').classList.add('fa-sun');
            }
            
            // 切换主题
            function toggleTheme() {
                document.body.classList.toggle('dark-mode');
                
                if (document.body.classList.contains('dark-mode')) {
                    themeIcon.classList.remove('fa-moon');
                    themeIcon.classList.add('fa-sun');
                    mobileThemeBtn.querySelector('i').classList.remove('fa-moon');
                    mobileThemeBtn.querySelector('i').classList.add('fa-sun');
                    localStorage.setItem('theme', 'dark');
                } else {
                    themeIcon.classList.remove('fa-sun');
                    themeIcon.classList.add('fa-moon');
                    mobileThemeBtn.querySelector('i').classList.remove('fa-sun');
                    mobileThemeBtn.querySelector('i').classList.add('fa-moon');
                    localStorage.setItem('theme', 'light');
                }
            }

            // 切换主题 - 桌面端
            themeToggle.addEventListener('click', function() {
                toggleTheme();
            });

            // 切换主题 - 移动端
            mobileThemeBtn.addEventListener('click', function() {
                toggleTheme();
            });
            
            // 阅读进度功能
            const progressBar = document.getElementById('progressBar');
            
            window.addEventListener('scroll', function() {
                const windowHeight = window.innerHeight;
                const documentHeight = document.documentElement.scrollHeight - windowHeight;
                const scrollTop = window.pageYOffset || document.documentElement.scrollTop;
                const progress = (scrollTop / documentHeight) * 100;
                
                progressBar.style.width = progress + '%';
                
                // 更新目录高亮
                updateTocHighlight();
            });
            
            // 目录功能
            const tocToggle = document.getElementById('tocToggle');
            const tocFloating = document.getElementById('tocFloating');
            const mobileTocBtn = document.getElementById('mobileTocBtn');
            const tocClose = document.getElementById('tocClose');
            const tocList = document.getElementById('tocList');
            
            // 生成目录
            generateToc();
            
            // 切换目录显示 - 桌面端
            tocToggle.addEventListener('click', function() {
                tocFloating.classList.toggle('active');
            });
            
            // 切换目录显示 - 移动端
            mobileTocBtn.addEventListener('click', function() {
                tocFloating.classList.toggle('active');
                // 移动端点击后高亮按钮
                mobileTocBtn.classList.toggle('active');
            });
            
            // 关闭目录
            tocClose.addEventListener('click', function() {
                tocFloating.classList.remove('active');
                mobileTocBtn.classList.remove('active');
            });
            
            // 生成目录函数
            function generateToc() {
                const content = document.getElementById('content');
                const headings = content.querySelectorAll('h2, h3, h4');
                
                if (headings.length === 0) {
                    tocList.innerHTML = '<li class="toc-item">no title found</li>';
                    return;
                }
                
                headings.forEach((heading, index) => {
                    // 为每个标题添加ID
                    if (!heading.id) {
                        heading.id = `heading-${index}`;
                    }
                    
                    // 创建目录项
                    const listItem = document.createElement('li');
                    const level = heading.tagName.charAt(1); // h2 -> 2, h3 -> 3, h4 -> 4
                    listItem.className = `toc-item toc-level-${level - 1}`;
                    
                    const link = document.createElement('a');
                    link.href = `#${heading.id}`;
                    link.textContent = heading.textContent;
                    
                    link.addEventListener('click', function(e) {
                        e.preventDefault();
                        
                        // 平滑滚动到标题位置
                        const targetElement = document.getElementById(heading.id);
                        if (targetElement) {
                            const offsetTop = targetElement.offsetTop - 100;
                            window.scrollTo({
                                top: offsetTop,
                                behavior: 'smooth'
                            });
                            
                            // 关闭目录浮窗
                            tocFloating.classList.remove('active');
                            mobileTocBtn.classList.remove('active');
                        }
                    });
                    
                    listItem.appendChild(link);
                    tocList.appendChild(listItem);
                });
            }
            
            // 更新目录高亮
            function updateTocHighlight() {
                const content = document.getElementById('content');
                const headings = content.querySelectorAll('h2, h3, h4');
                const tocItems = document.querySelectorAll('.toc-item');
                
                // 找到当前可见的标题
                let currentHeadingId = '';
                const scrollPosition = window.scrollY + 150; // 偏移量
                
                for (let i = headings.length - 1; i >= 0; i--) {
                    const heading = headings[i];
                    if (heading.offsetTop <= scrollPosition) {
                        currentHeadingId = heading.id;
                        break;
                    }
                }
                
                // 更新目录高亮
                tocItems.forEach(item => {
                    item.classList.remove('active');
                    const link = item.querySelector('a');
                    if (link && link.getAttribute('href') === `#${currentHeadingId}`) {
                        item.classList.add('active');
                    }
                });
            }
            
            // 滚动到顶部功能
            const scrollToTopBtn = document.getElementById('scrollToTopBtn');
            
            scrollToTopBtn.addEventListener('click', function() {
                window.scrollTo({
                    top: 0,
                    behavior: 'smooth'
                });
            });

            // 滚动到顶部功能 - 移动端
            const mobileTopBtn = document.getElementById('mobileTopBtn');
            
            mobileTopBtn.addEventListener('click', function() {
                window.scrollTo({
                    top: 0,
                    behavior: 'smooth'
                });
            });

            
            let lastScrollTop = 0; // 移动端滚动时显示/隐藏底部控件
            const scrollThreshold = 10; // 滚动阈值，避免轻微滚动触
            const mobileControls = document.querySelector('.mobile-controls');
            window.addEventListener('scroll', function() {
                const scrollTop = window.pageYOffset || document.documentElement.scrollTop;

                if (scrollTop > lastScrollTop && scrollTop - lastScrollTop > scrollThreshold) {
                    mobileControls.style.transform = 'translateY(100%)';
                } 
                // 向上滚动超过阈值时显示控件
                else if (scrollTop < lastScrollTop && lastScrollTop - scrollTop > scrollThreshold) {
                    mobileControls.style.transform = 'translateY(0)';
                }

                // 更新上一次滚动位置
                lastScrollTop = scrollTop;
            });

            // 图片点击放大功能
            const contentImages = document.querySelectorAll('img');

            for (let i = 0; i < contentImages.length; i++) {
                let contentImage = contentImages[i];
                contentImage.addEventListener('click', function() {
                    if (this.classList.contains('zoomed')) {
                        this.classList.remove('zoomed');
                        this.style.cursor = 'zoom-in';
                    } else {
                        this.classList.add('zoomed');
                        this.style.cursor = 'zoom-out';
                    }
                });
            }
            
            // 字体控制功能
            const fontControlBtn = document.getElementById('fontControlBtn');
            const mobileFontBtn = document.getElementById('mobileFontBtn');
            const fontControls = document.getElementById('fontControls');
            const fontSizeBtns = document.querySelectorAll('.font-size-btn');
            const content = document.getElementById('content');
            
            fontControlBtn.addEventListener('click', function() {
                fontControls.classList.toggle('show');
            });

            mobileFontBtn.addEventListener('click', function() {
                fontControls.classList.toggle('show');
            });
            
            fontSizeBtns.forEach(btn => {
                btn.addEventListener('click', function() {
                    // 移除所有按钮的active类
                    fontSizeBtns.forEach(b => b.classList.remove('active'));
                    // 为当前点击的按钮添加active类
                    this.classList.add('active');
                    
                    const size = this.getAttribute('data-size');
                    
                    // 移除所有字体大小类
                    content.classList.remove('font-small', 'font-medium', 'font-large');
                    
                    // 添加选中的字体大小类
                    if (size === 'small') {
                        content.classList.add('font-small');
                    } else if (size === 'medium') {
                        content.classList.add('font-medium');
                    } else if (size === 'large') {
                        content.classList.add('font-large');
                    }
                });
            });
            
            // 添加字体大小样式
            const style = document.createElement('style');
            style.textContent = `
                .font-small { font-size: 0.9rem; }
                .font-medium { font-size: 1rem; }
                .font-large { font-size: 1.2rem; }

                img.zoomed {
                    width: 90vw; 
                    max-height: 100vh; 
                    cursor: zoom-out;
                }
            `;
            document.head.appendChild(style);
        });
    </script>
</body>
</html>
"""
        return chapter_html
    
    def copy_resources(self):
        """复制资源文件"""
        # 复制整个提取目录到web目录下的resources文件夹
        resources_dir = os.path.join(self.web_dir, self.resources_base)
        os.makedirs(resources_dir, exist_ok=True)
        
        # 复制整个提取目录
        for root, dirs, files in os.walk(self.extract_dir):
            for file in files:
                src_path = os.path.join(root, file)
                # 计算相对于提取目录的相对路径
                rel_path = os.path.relpath(src_path, self.extract_dir)
                dst_path = os.path.join(resources_dir, rel_path)
                
                # 确保目标目录存在
                os.makedirs(os.path.dirname(dst_path), exist_ok=True)
                shutil.copy2(src_path, dst_path)
        
        # print(f"Resource files copied to: {resources_dir}")
    
    def get_book_info(self):
        """获取书籍信息"""
        cover = ""
        if self.cover_info:
            cover = os.path.normpath(os.path.join(self.resources_base, self.cover_info["href"]))
        return {
            'title': self.book_title,
            'path': self.web_dir,
            'hash': self.book_hash,
            'cover': cover,
            'authors': self.authors,
            'tags': self.tags
        }
    
    def cleanup(self):
        """清理临时文件"""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
            # print(f"Temporary files cleaned up for: {self.book_title}")
