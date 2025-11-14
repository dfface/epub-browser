import os
import zipfile
import tempfile
import shutil
import xml.etree.ElementTree as ET
import re
import hashlib
import json
import minify_html
from datetime import datetime

class EPUBProcessor:
    """处理EPUB文件的类"""
    
    def __init__(self, epub_path, output_dir=None):
        self.epub_path = epub_path
        self.output_dir = output_dir
        self.book_hash = hashlib.md5(epub_path.encode()).hexdigest()[:8]  # 使用哈希值作为标识，后续可能会根据 ncx 更新
        
        if output_dir:
            # 使用用户指定的输出目录
            # 这里一般会始终使用 base_directory，也就是上层已经处理了，可能是 temp dir
            self.temp_dir = os.path.join(output_dir, f'epub_{self.book_hash}')
            if not os.path.exists(self.temp_dir):
                os.mkdir(self.temp_dir)
        else:
            # 使用系统临时目录
            # 本程序永远走不到这里来的，除非作为库被别人调用
            self.temp_dir = tempfile.mkdtemp(prefix='epub_')
            
        self.extract_dir = os.path.join(self.temp_dir, 'extracted')
        self.web_dir = os.path.join(self.temp_dir, 'web')
        self.book_title = "EPUB Book"
        self.authors = None
        self.tags = None
        self.cover_info = None
        self.lang = 'en'
        self.chapters = []
        self.toc = []  # 存储目录结构
        self.resources_base = "resources"  # 资源文件的基础路径
        
    def generate_hash(self):
        """生成书籍 Hash
        一般来说，用路径受到用户传参影响，每次都是绝对路径则都是一样；
        content.opf 可能因修改元数据如标签而更改；
        toc.ncx 一般不会变化，用这个来 Hash 比较合适，而这个解析出来的是 toc 变量；
        """
        if self.toc:
            self.book_hash = hashlib.md5(json.dumps(self.toc).encode()).hexdigest()[:8]
            # 如果重新生成 Hash，需要修改路径
            if self.output_dir:
                new_temp_dir = os.path.join(self.output_dir, f'epub_{self.book_hash}')
                try:
                    if not os.path.exists(new_temp_dir):
                        os.rename(self.temp_dir, new_temp_dir)
                    self.temp_dir = new_temp_dir
                    self.web_dir = os.path.join(self.temp_dir, 'web')
                    self.extract_dir = os.path.join(self.temp_dir, 'extracted')
                except Exception as e:
                    print(f"Modify directory name failed, old: {self.temp_dir}, new: {new_temp_dir}, err: {e}")
        
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

            # 获取语言
            lang = root.find('.//dc:language', ns)
            self.lang = lang.text if lang is not None and lang.text else 'en'

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
        
        # 复制资源文件（CSS、图片、字体等）并删除 extracted 文件夹
        self.copy_resources()
        
        # print(f"Web interface created at: {self.web_dir}")
        return self.web_dir
    
    def create_index_page(self):
        """创建章节索引页面"""
        index_html = f"""<!DOCTYPE html>
<html lang="{self.lang}">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{self.book_title}</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/7.0.1/css/all.min.css">
    <link rel="icon" type="image/svg+xml" href="data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCA2NDAgNjQwIj48IS0tIUZvbnQgQXdlc29tZSBGcmVlIHY3LjEuMCBieSBAZm9udGF3ZXNvbWUgLSBodHRwczovL2ZvbnRhd2Vzb21lLmNvbSBMaWNlbnNlIC0gaHR0cHM6Ly9mb250YXdlc29tZS5jb20vbGljZW5zZS9mcmVlIENvcHlyaWdodCAyMDI1IEZvbnRpY29ucywgSW5jLi0tPjxwYXRoIGQ9Ik0zMjAgMjA1LjNMMzIwIDUxNC42TDMyMC41IDUxNC40QzM3NS4xIDQ5MS43IDQzMy43IDQ4MCA0OTIuOCA0ODBMNTEyIDQ4MEw1MTIgMTYwTDQ5Mi44IDE2MEM0NTAuNiAxNjAgNDA4LjcgMTY4LjQgMzY5LjcgMTg0LjZDMzUyLjkgMTkxLjYgMzM2LjMgMTk4LjUgMzIwIDIwNS4zek0yOTQuOSAxMjUuNUwzMjAgMTM2TDM0NS4xIDEyNS41QzM5MS45IDEwNiA0NDIuMSA5NiA0OTIuOCA5Nkw1MjggOTZDNTU0LjUgOTYgNTc2IDExNy41IDU3NiAxNDRMNTc2IDQ5NkM1NzYgNTIyLjUgNTU0LjUgNTQ0IDUyOCA1NDRMNDkyLjggNTQ0QzQ0Mi4xIDU0NCAzOTEuOSA1NTQgMzQ1LjEgNTczLjVMMzMyLjMgNTc4LjhDMzI0LjQgNTgyLjEgMzE1LjYgNTgyLjEgMzA3LjcgNTc4LjhMMjk0LjkgNTczLjVDMjQ4LjEgNTU0IDE5Ny45IDU0NCAxNDcuMiA1NDRMMTEyIDU0NEM4NS41IDU0NCA2NCA1MjIuNSA2NCA0OTZMNjQgMTQ0QzY0IDExNy41IDg1LjUgOTYgMTEyIDk2TDE0Ny4yIDk2QzE5Ny45IDk2IDI0OC4xIDEwNiAyOTQuOSAxMjUuNXoiLz48L3N2Zz4=">
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
            background: var(--card-bg);
            border: none;

            width: 50px;
            height: 50px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            flex-direction: column;

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
            flex-direction: column;
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

        .chapter-list a:target {
            background: linear-gradient(to right, var(--primary), var(--success));
            color: #e9ecef;
        }

        .chapter-list a:target .chapter-page {
            color: #e9ecef;
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
            transition: var(--transition);
        }

        .book-info-card {
            display: flex;
            background: var(--card-bg);
            border-radius: var(--border-radius);
            box-shadow: var(--shadow);
            padding: 25px;
            margin-bottom: 30px;
            gap: 25px;
            transition: var(--transition);
        }

        .book-info-cover {
            flex: 0 0 150px;
            height: 200px;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 4px 15px rgba(0, 0, 0, 0.1);
        }

        .book-info-cover img {
            width: 100%;
            height: 100%;
            object-fit: cover;
        }

        .book-info-content {
            flex: 1;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
        }

        .book-info-title {
            font-size: 1.5rem;
            color: var(--text-color);
            margin-bottom: 10px;
            font-weight: 700;
            line-height: 1.3;
        }

        .book-info-author {
            font-size: 1rem;
            color: var(--text-secondary);
            margin-bottom: 15px;
        }

        .book-info-tags {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin-bottom: 15px;
        }

        .book-tag {
            background: var(--primary-light);
            color: white;
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 0.8rem;
            font-weight: 500;
            transition: var(--transition);
        }

        .book-tag:hover {
            background: var(--primary);
            transform: translateY(-2px);
            cursor: pointer;
        }

        .control-name {
            font-size: 0.5rem;
        }

        .kindle-mode .header, .kindle-mode .toc-container, 
        .kindle-mode .content-container, .kindle-mode .navigation,
        .kindle-mode .theme-toggle, .kindle-mode .control-btn {
            box-shadow: none;
            border-radius: inherit;
        }

        .kindle-mode .book-info-card, .kindle-mode .footer{
            display: none;
        }

        .kindle-mode .chapter-list {
            max-height: none;
        }

        .kindle-mode .breadcrumb {
            margin: 0;
        }

        .kindle-mode .container {
            padding: 0;
        }

        .kindle-mode .theme-toggle {
            border: 1px solid;
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
<div class="top-controls">
    <div class="theme-toggle" id="themeToggle">
        <i class="fas fa-moon"></i>
        <span class="control-name">Theme</span>
    </div>
</div>
"""
        index_html += f"""
<div class="container">
    <div class="breadcrumb header">
        <a href="/index.html#{self.book_hash}"><i class="fas fa-home"></i><span style="margin-left: 8px;">Home</span></a>
        <span class="breadcrumb-separator">/</span>
        <span class="breadcrumb-current" id="book_home">{self.book_title}</span>
    </div>

    <div class="book-info-card">
            <div class="book-info-cover">
                <img src="{self.get_book_info()['cover']}" alt="cover">
            </div>
            <div class="book-info-content">
                <h2 class="book-info-title">{self.book_title}</h2>
                <p class="book-info-author">{" & ".join(self.authors) if self.authors else "Unknown"}</p>
                    <div class="book-info-tags">"""
        if self.tags:
            for tag in self.tags:
                index_html += f"""<span class="book-tag">{tag}</span>"""        
        index_html += f"""
                </div>
            </div>
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
                    index_html += f'        <li class="{level_class}"><a href="/book/{self.book_hash}/chapter_{chapter_index}.html" id="chapter_{chapter_index}"><span class="chapter-title">{toc_item["title"]}</span><span class="chapter-page">chapter_{chapter_index}.html</span></a></li>\n'
                else:
                    print(f"Chapter index not found: {toc_item['src']}")
        else:
            # 回退到简单章节列表
            for i, chapter in enumerate(self.chapters):
                index_html += f'        <li><a href="/book/{self.book_hash}/chapter_{i}.html">{chapter["title"]}</a></li>\n'
        
        index_html += f"""    </ul>
    </div>
</div>
<div class="reading-controls">
    <a href="/index.html#{self.book_hash}" alt="Home">
        <div class="control-btn">
            <i class="fas fa-home"></i>
            <span class="control-name">Home</span>
        </div>
    </a>
    <div class="control-btn" id="scrollToTopBtn">
        <i class="fas fa-arrow-up"></i>
        <span class="control-name">Top</span>
    </div>
</div>
<footer class="footer">
    <p>EPUB Library &copy; {datetime.now().year} | Powered by <a href="https://github.com/dfface/epub-browser" target="_blank">epub-browser</a></p>
</footer>
"""
        index_html += f"""<script>
    document.addEventListener('DOMContentLoaded', function() {{
        const book_hash = "{self.book_hash}";"""
        index_html += """
        const path = window.location.pathname;  // 获取当前URL路径
        let pathParts = path.split('/');
        pathParts = pathParts.filter(item => item !== "");

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

        let kindleMode = getCookie("kindle-mode") || "false";

        function isKindleMode() {
            return kindleMode == "true";
        }

        if (isKindleMode()) {
            document.body.classList.add("kindle-mode");
        }
        
        // 检查当前的基路径
        if (!path.startsWith("/book/")) {
            // 获取基路径
            let basePath = path.split('/book/');
            basePath = basePath[0] + "/";
            // 处理所有资源，都要加上基路径
            addBasePath(basePath);
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

        // 书籍目录锚点删除
        const anchor = window.location.hash;
        if (!isKindleMode()) {
            if (anchor === '' || !anchor.startsWith('#chapter_')) {
                localStorage.removeItem(book_hash);  // 此时 lastPart 就是 book_hash
            }
        } else {
            if (anchor === '' || !anchor.startsWith('#chapter_')) {
                deleteCookie(book_hash);  // 此时 lastPart 就是 book_hash
            }
        }
        
        // 主题切换功能
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
        # kindle 支持，不能压缩 css 和 js
        index_html = minify_html.minify(index_html, minify_css=False, minify_js=False)
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
        prev_link = f'<a href="/book/{self.book_hash}/chapter_{chapter_index-1}.html" alt="previous"> <div class="control-btn"> <i class="fas fa-arrow-left"></i><span class="control-name">Prev chapter</span></div></a>' if chapter_index > 0 else ''
        next_link = f'<a href="/book/{self.book_hash}/chapter_{chapter_index+1}.html" alt="next"> <div class="control-btn"> <i class="fas fa-arrow-right"></i><span class="control-name">Next chapter</span></div></a>' if chapter_index < len(self.chapters) - 1 else ''
        prev_link_mobile = f'<a href="/book/{self.book_hash}/chapter_{chapter_index-1}.html" alt="previous"> <div class="control-btn"> <i class="fas fa-arrow-left"></i><span>Prev</span></div></a>' if chapter_index > 0 else ''
        next_link_mobile = f'<a href="/book/{self.book_hash}/chapter_{chapter_index+1}.html" alt="next"> <div class="control-btn"> <i class="fas fa-arrow-right"></i><span>Next</span></div></a>' if chapter_index < len(self.chapters) - 1 else ''
        
        chapter_html =  f"""<!DOCTYPE html>
<html lang="{self.lang}">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{chapter_title} - {self.book_title}</title>
    {style_links}
    <link id="code-light" rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.11.1/styles/github.min.css">
    <link id="code-dark" rel="stylesheet" disabled href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.11.1/styles/github-dark.min.css">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/7.0.1/css/all.min.css">
    <link rel="icon" type="image/svg+xml" href="data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCA2NDAgNjQwIj48IS0tIUZvbnQgQXdlc29tZSBGcmVlIHY3LjEuMCBieSBAZm9udGF3ZXNvbWUgLSBodHRwczovL2ZvbnRhd2Vzb21lLmNvbSBMaWNlbnNlIC0gaHR0cHM6Ly9mb250YXdlc29tZS5jb20vbGljZW5zZS9mcmVlIENvcHlyaWdodCAyMDI1IEZvbnRpY29ucywgSW5jLi0tPjxwYXRoIGQ9Ik0zMjAgMjA1LjNMMzIwIDUxNC42TDMyMC41IDUxNC40QzM3NS4xIDQ5MS43IDQzMy43IDQ4MCA0OTIuOCA0ODBMNTEyIDQ4MEw1MTIgMTYwTDQ5Mi44IDE2MEM0NTAuNiAxNjAgNDA4LjcgMTY4LjQgMzY5LjcgMTg0LjZDMzUyLjkgMTkxLjYgMzM2LjMgMTk4LjUgMzIwIDIwNS4zek0yOTQuOSAxMjUuNUwzMjAgMTM2TDM0NS4xIDEyNS41QzM5MS45IDEwNiA0NDIuMSA5NiA0OTIuOCA5Nkw1MjggOTZDNTU0LjUgOTYgNTc2IDExNy41IDU3NiAxNDRMNTc2IDQ5NkM1NzYgNTIyLjUgNTU0LjUgNTQ0IDUyOCA1NDRMNDkyLjggNTQ0QzQ0Mi4xIDU0NCAzOTEuOSA1NTQgMzQ1LjEgNTczLjVMMzMyLjMgNTc4LjhDMzI0LjQgNTgyLjEgMzE1LjYgNTgyLjEgMzA3LjcgNTc4LjhMMjk0LjkgNTczLjVDMjQ4LjEgNTU0IDE5Ny45IDU0NCAxNDcuMiA1NDRMMTEyIDU0NEM4NS41IDU0NCA2NCA1MjIuNSA2NCA0OTZMNjQgMTQ0QzY0IDExNy41IDg1LjUgOTYgMTEyIDk2TDE0Ny4yIDk2QzE5Ny45IDk2IDI0OC4xIDEwNiAyOTQuOSAxMjUuNXoiLz48L3N2Zz4=">
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
            min-width: 1000px;
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

        #bookHomeFloating {
            width: 30%;
            height: 100%;
            bottom: 80px;
            top: 80px;
            overflow: hidden;
        }

        #bookHomeIframe {
            width: 100%;
            height: 100%;
            border: none;
            display: flex;
        }

        .iframe-container {
            width: 100%;
            height: 100%;
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
            display: none;
            flex-direction: column;  /* 垂直方向排列 */
            z-index: 88;
        }

        .toc-floating.active {
            display: flex;
        }

        .toc-header {
            padding: 15px 20px;
            border-bottom: 1px solid var(--border-color);
            display: flex;
            flex-shrink: 0; /* 头部不收缩 */ 
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
            flex: 1; /* 内容区域占据剩余空间 */
            overflow-y: auto;
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
            text-indent: 0px;
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
            border-left: 4px solid var(--primary);
            padding-left: 1rem;
        }

        .content h4 {
            font-size: 1.1rem;
            border-left: 2px solid var(--primary);
            padding-left: 1rem;
        }

        .content p {
            margin-bottom: 0.8rem;
            line-height: 1.7;
        }

        .content img {
            max-width: 100%;
            height: auto;
            border-radius: 8px;
            box-shadow: 0 4px 15px rgba(0, 0, 0, 0.1);
            margin: 0;
            object-fit: contain;
        }

        .content .table-wrapper {
            width: 100%;
            overflow-x: auto;
        }

        .content table {
            margin: 0px;
            border-color: var(--text-color);
        }

        .content table tr, .content table td, .content table th {
            border-color: var(--text-color);
        }

        .content table tr {
            margin: 0px;
            color: inherit;
            background-color: inherit;
        }

        .content table th {
            background-color: inherit;
            font-weight: 600;
            color: inherit;
        }
        
        .content table td {
            color: inherit;
        }
        
        .content table tr:hover {
            background-color: var(--bg-color);
        }

        .content pre code {
            padding: 10px 10px;
            border-radius: 4px;
            font-family: 'Courier New', monospace;
            font-size: 0.9rem;
            height: auto;
            width: 100%;
        }

        .content pre {
            background: var(--border-color);
            border-radius: 8px;
            overflow-x: auto;
            margin: 0px;
            padding: 10px;
            font-family: 'Courier New', monospace;
            font-size: 0.9rem;
            display: flex;
            white-space: pre;
        }

        .content blockquote {
            color: inherit;
            position: relative;
            overflow: hidden;
        }

        .content ul, .content ol {
            padding: 0;
        }
        
        .content ul li, .content ol li {
            border-radius: inherit;
            box-shadow: none;
            transition: all 0.3s ease;
        }

        .content ul li:before {
            margin-right: 0.5rem;
        }

        .content ol li:before {
            margin-right: 0.5rem;
        }

        .navigation {
            display: flex;
            justify-content: space-between;
            margin: 30px 0 0 0;
            padding: 20px;
            background: var(--card-bg);
            border-radius: var(--border-radius);
            box-shadow: var(--shadow);
            transition: var(--transition);
        }

        .navigation a {
            text-decoration: none;
            line-height: 1;
        }

        .navigation .control-btn {
            display: flex;
            align-items: center;
            gap: 10px;
            padding: 0 20px;
            background: var(--card-bg);
            color: var(--text-color);
            border-radius: 10px;
            text-decoration: none;
            font-weight: 600;
            transition: var(--transition);
            border: none;
            cursor: pointer;
            flex-direction: column;
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
            flex-direction: column;
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
            border-radius: 8px;
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


        .custom-css-panel {
            background: var(--card-bg);
            border-radius: var(--border-radius);
            box-shadow: var(--shadow);
            margin-bottom: 30px;
            overflow: hidden;
            transition: var(--transition);
        }

        .panel-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 15px 20px;
            background: var(--primary);
            color: white;
            cursor: pointer;
        }

        .panel-header h3 {
            margin: 0;
            font-size: 1.1rem;
            display: flex;
            align-items: center;
            gap: 10px;
        }

        .panel-toggle {
            background: none;
            border: none;
            color: white;
            cursor: pointer;
            transition: var(--transition);
            padding: 5px;
        }

        .panel-toggle:hover {
            transform: scale(1.1);
        }

        .panel-content {
            padding: 0;
            max-height: 0;
            overflow: hidden;
            transition: max-height 0.3s ease;
        }

        .panel-content.expanded {
            max-height: 500px;
            padding: 20px;
        }

        .css-editor {
            display: flex;
            flex-direction: column;
            gap: 15px;
        }

        #customCssInput {
            width: 100%;
            height: 200px;
            padding: 15px;
            border: 1px solid var(--border-color);
            border-radius: 8px;
            font-family: 'Courier New', monospace;
            font-size: 0.9rem;
            resize: vertical;
            background: var(--bg-color);
            color: var(--text-color);
            transition: var(--transition);
        }

        #customCssInput:focus {
            outline: none;
            border-color: var(--primary);
            box-shadow: 0 0 0 2px rgba(67, 97, 238, 0.2);
        }

        .css-controls {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 10px;
        }

        .css-btn {
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 8px;
            padding: 10px 15px;
            border-radius: 6px;
            font-weight: 600;
            cursor: pointer;
            transition: var(--transition);
            border: none;
            font-size: 0.9rem;
            text-align: center;
            white-space: nowrap;
        }

        .css-btn.primary {
            background: var(--primary);
            color: white;
        }

        .css-btn.primary:hover {
            background: var(--secondary);
            transform: translateY(-2px);
        }

        .css-btn.secondary {
            background: var(--card-bg);
            color: var(--text-color);
            border: 1px solid var(--border-color);
        }

        .css-btn.secondary:hover {
            background: var(--border-color);
            transform: translateY(-2px);
        }

        /* 通知样式 */
        .custom-css-notification {
            position: fixed;
            top: 20px;
            right: 20px;
            padding: 12px 20px;
            border-radius: 6px;
            color: white;
            font-weight: 600;
            z-index: 1000;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
            transition: all 0.3s ease;
        }

        .custom-css-notification.success {
            background: var(--success);
        }

        .custom-css-notification.info {
            background: var(--primary);
        }

        .custom-css-notification.warning {
            background: #f8961e;
        }

        .custom-css-notification.fade-out {
            opacity: 0;
            transform: translateY(-10px);
        }

        .css-info {
            padding: 10px 15px;
            background: var(--border-color);
            border-radius: 6px;
            font-size: 0.85rem;
            color: var(--text-secondary);
        }

        .css-info p {
            margin: 0;
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .css-info i {
            color: var(--primary);
        }

        .control-name {
            font-size: 0.5rem;
        }

        /* 翻页控制面板 */
        .pagination-controls {
            position: fixed;
            bottom: 20px;
            left: 50%;
            transform: translateX(-50%);
            display: flex;
            align-items: center;
            gap: 40px;
            background: var(--card-bg);
            border-radius: 50px;
            box-shadow: var(--shadow);
            padding: 10px 20px;
            z-index: 77;
            transition: var(--transition);
        }

        .pagination-btn {
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 8px 16px;
            background: var(--primary);
            color: white;
            border: none;
            border-radius: 25px;
            cursor: pointer;
            transition: var(--transition);
            font-weight: 600;
        }

        .pagination-btn:hover {
            background: var(--secondary);
            transform: translateY(-2px);
        }

        .pagination-info {
            display: flex;
            align-items: center;
            gap: 15px;
        }

        .page-indicator {
            font-weight: 600;
            color: var(--text-color);
            min-width: 60px;
            text-align: center;
        }

        .page-nav {
            display: flex;
            gap: 10px;
        }

        .page-nav-btn {
            height: 40px;
            border-radius: 10%;
            padding: 5px 10px;
            background: var(--border-color);
            color: var(--text-color);
            border: none;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: var(--transition);
            flex-direction: column;
        }

        .page-nav-btn:hover {
            background: var(--primary);
            color: white;
            transform: scale(1.1);
        }

        .page-nav-btn:disabled {
            opacity: 0.5;
            cursor: not-allowed;
            transform: none;
        }

        .page-nav-btn:disabled:hover {
            background: var(--border-color);
            color: var(--text-color);
        }

        /* 页面跳转输入框 */
        .page-jump {
            display: flex;
            align-items: center;
            gap: 5px;
            margin: 0 5px;
        }

        #pageJumpInput {
            width: 50px;
            height: 36px;
            text-align: center;
            border: 1px solid var(--border-color);
            border-radius: 6px;
            background: var(--bg-color);
            color: var(--text-color);
            font-weight: 600;
        }

        #pageJumpInput:focus {
            outline: none;
            border-color: var(--primary);
        }

        /* 翻页模式样式 */
        .pagination-mode .content-container {
            overflow: hidden;
            height: calc(100vh - 60px);
            position: relative;
        }

        .pagination-mode .content {
            display: flex;
            flex-direction: column;
            height: 100%;
            position: relative;
        }

        .pagination-page {
            height: 100%;
            width: 100%;
            overflow-y: auto;
            box-sizing: border-box;
            position: absolute;
            top: 0;
            left: 0;
            opacity: 0;
            transform: translateX(100%);
            transition: opacity 0.3s ease, transform 0.4s ease;
        }

        .pagination-page.active {
            opacity: 1;
            transform: translateX(0);
            position: relative;
        }

        .pagination-page.prev {
            transform: translateX(-100%);
        }

        /* 隐藏滚动条 */
        .pagination-mode ::-webkit-scrollbar {
            display: none;
        }

        .pagination-mode {
            -ms-overflow-style: none;
            scrollbar-width: none;
        }

        .kindle-mode .header, .kindle-mode .toc-container, 
        .kindle-mode .content-container, .kindle-mode .navigation,
        .kindle-mode .theme-toggle, .kindle-mode .control-btn, .kindle-mode .pagination-controls {
            box-shadow: none;
            border-radius: inherit;
        }

        .kindle-mode .pagination-controls {
            border: 1px solid;
        }

        .kindle-mode .footer {
            display: none;
        }

        .kindle-mode .breadcrumb {
            margin: 0;
        }

        .kindle-mode .pagination-page {
            transition: none;
        }

        .kindle-mode .theme-toggle {
            border: 1px solid;
        }

        /* 响应式设计 */
        @media (max-width: 1079px) {
            .container {
                max-width: 100%;
                min-width: 70%;
            }
        }

        @media (max-width: 768px) {
            .container {
                max-width: 100%;
                min-width: 80%;
            }

            .chapter-title {
                font-size: 1.5rem;
            }
            
            .navigation {
                gap: 10px;
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
                bottom: 90px;
                max-height: 100vh;
            }

            #bookHomeFloating {
                right: 5%;
                left: 5%;
                top: 20px;
                bottom: 90px;
                width: auto;
                height: auto;
            }

            .mobile-controls {
                display: flex;
            }

            .font-controls {
                bottom: 80px;
            }

            .css-controls {
                grid-template-columns: 1fr 1fr;
            }
            
            .css-btn {
                justify-content: center;
            }

            .pagination-controls {
                bottom: 70px; /* 避免与移动端底部控件重叠 */
                max-width: 80%;
            }
            
            .pagination-info {
                justify-content: space-between;
            }

            .page-nav-btn {
                width: 65px;
            }

            .pagination-page {
                transition: none;
            }
        }

        @media (max-width: 480px) {
            .container {
                max-width: 100%;
                min-width: 80%;
            }

            .breadcrumb {
                flex-wrap: wrap;
            }
            
            .breadcrumb-separator {
                margin: 0 5px;
            }
            
            .content {
                padding: 20px;
            }

            .css-controls {
                grid-template-columns: 1fr;
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
            <span class="control-name">Theme</span>
        </div>

        <div class="control-btn" id="togglePagination">
            <i class="fas fa-book-open"></i>
            <span class="control-name">Turning</span>
        </div>

        <div class="control-btn" id="bookHomeToggle">
            <i class="fas fa-book"></i>
            <span class="control-name">Book</span>
        </div>

        <div class="control-btn" id="tocToggle">
            <i class="fas fa-list"></i>
            <span class="control-name">Toc</span>
        </div>
    </div>

    <div class="toc-floating" id="bookHomeFloating">
        <div class="toc-header">
            <h3>Toc</h3>
            <button class="toc-close" id="bookHomeClose">
                <i class="fas fa-times"></i>
            </button>
        </div>
        <div class="iframe-container">
            <iframe id="bookHomeIframe" src="/book/{self.book_hash}/index.html" title="BookHome" sandbox="allow-same-origin allow-scripts allow-forms"></iframe>
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
            <a href="/index.html#{self.book_hash}" alt="home"><i class="fas fa-home"></i><span style="margin-left:8px;">Home</span></a>
            <span class="breadcrumb-separator">/</span>
            <a href="/book/{self.book_hash}/index.html" alt="bookHome" class="a-book-home">{self.book_title}</a>
            <span class="breadcrumb-separator">/</span>
            <span class="breadcrumb-current">{chapter_title}</span>
        </div> 

        <div class="custom-css-panel">
            <div class="panel-header" id="cssPanelToggle">
                <h3><i class="fas fa-paint-brush"></i>Custom CSS</h3>
                <button class="panel-toggle">
                    <i class="fas fa-chevron-down"></i>
                </button>
            </div>
            <div class="panel-content" id="cssPanelContent">
                <div class="css-editor">
                    <textarea id="customCssInput" placeholder="Please input your CSS code..."></textarea>
                    <div class="css-controls">
                        <button class="css-btn primary" id="saveCssBtn">
                            <i class="fas fa-save"></i> Save
                        </button>
                        <button class="css-btn primary" id="saveAsDefaultBtn">
                            <i class="fas fa-star"></i> Save as default
                        </button>
                        <button class="css-btn secondary" id="resetCssBtn">
                            <i class="fas fa-undo"></i> Reset
                        </button>
                        <button class="css-btn secondary" id="loadDefaultBtn">
                            <i class="fas fa-download"></i> Load default
                        </button>
                        <button class="css-btn secondary" id="previewCssBtn">
                            <i class="fas fa-eye"></i> Preview
                        </button>
                    </div>
                    <div class="css-info">
                        <p><i class="fas fa-info-circle"></i> Tip: The default style will be applied to all books unless a custom style is set for specific books.</p>
                    </div>
                </div>
            </div>
        </div>

        <div class="content-container">
            
            <div class="pagination-info pagination-controls" id="paginationInfo" style="display: none;">
                <span class="page-indicator">
                    <span id="currentPage">1</span> / <span id="totalPages">1</span>
                </span>
                <div class="page-nav">
                    <div class="page-jump">
                        <input type="number" id="pageJumpInput" min="1" max="1" value="1">
                        <div class="page-nav-btn" id="goToPage" title="Jump">
                            <i class="fas fa-arrow-right-to-bracket"></i>
                            <span class="control-name">Go to</span>
                        </div>
                    </div>
                    <div class="page-nav-btn" id="prevPage">
                        <i class="fas fa-chevron-left"></i>
                        <span class="control-name">Prev page</span>
                    </div>
                    <div class="page-nav-btn" id="nextPage">
                        <i class="fas fa-chevron-right"></i>
                        <span class="control-name">Next page</span>
                    </div>
                </div>
            </div>
            <article class="content" id="content">
            {content}
            </article>
        </div>

        <div class="navigation">
            {prev_link}
            <a href="/index.html#{self.book_hash}" alt="home">
                <div class="control-btn">
                    <i class="fas fa-home"></i>
                    <span class="control-name">Home</span>
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
        <a href="/index.html#{self.book_hash}" alt="Home">
            <div class="control-btn">
                <i class="fas fa-home"></i>
                <span class="control-name">Home</span>
            </div>
        </a>
        <div class="control-btn" id="fontControlBtn">
            <i class="fas fa-font"></i>
            <span class="control-name">Font</span>
        </div>
        <div class="control-btn" id="scrollToTopBtn">
            <i class="fas fa-arrow-up"></i>
            <span class="control-name">Up</span>
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
        <div class="control-btn" id="mobileTogglePagination">
            <i class="fas fa-book-open"></i>
            <span class="control-name">Turning</span>
        </div>
        {prev_link_mobile}
        <a href="/index.html#{self.book_hash}" alt="Home">
            <div class="control-btn">
                <i class="fas fa-home"></i>
                <span>Home</span>
            </div>
        </a>
        {next_link_mobile}
        <div class="control-btn" id="mobileBookHomeBtn">
            <i class="fas fa-book"></i>
            <span>Book</span>
        </div>
        <div class="control-btn" id="mobileFontBtn">
            <i class="fas fa-font"></i>
            <span>Font</span>
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
        chapter_html += f"""
    <script>
    document.addEventListener('DOMContentLoaded', function() {{
        const book_hash = "{self.book_hash}";
"""
        chapter_html += f"""
            const path = window.location.pathname;  // 获取当前URL路径
            let pathParts = path.split('/');
            pathParts = pathParts.filter(item => item !== "");

            // 翻页功能
            const togglePaginationBtn = document.getElementById('togglePagination');
            const mobileTogglePaginationBtn  = document.getElementById('mobileTogglePagination');
            const paginationInfo = document.getElementById('paginationInfo');
            const currentPageEl = document.getElementById('currentPage');
            const totalPagesEl = document.getElementById('totalPages');
            const prevPageBtn = document.getElementById('prevPage');
            const nextPageBtn = document.getElementById('nextPage');
            const contentContainer = document.querySelector('.content-container');
            const content = document.getElementById('content');
            const pageJumpInput = document.getElementById('pageJumpInput');
            const goToPageBtn = document.getElementById('goToPage');
            const progressFill = document.getElementById('progressBar');

            // 生成存储键名
            function getStorageKey(mode) {{
                // 书籍ID和章节ID
                const bookId = "{self.book_hash}";
                const chapterId = {chapter_index}"""
        chapter_html += """                                
                return `book_${bookId}_chapter_${chapterId}_${mode}_position`;
            }

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

            function isKindleMode() {
                let kindleMode = getCookie("kindle-mode") || "false";
                return kindleMode == "true";
            }

            if (isKindleMode()) {
                document.querySelector(".custom-css-panel").style.display = "none";
                document.body.classList.add("kindle-mode");
            }
            
            // 翻页状态变量
            let isPaginationMode = false;
            let currentPage = 0;
            let totalPages = 0;
            let pages = [];

            // 检查本地存储中的主题设置
            if (!isKindleMode()) {
                let currentPaginationMode = localStorage.getItem('turning') || "false";
                isPaginationMode = currentPaginationMode == "true"
            } else {
                let currentPaginationMode =  getCookie('turning') || "false";
                isPaginationMode = currentPaginationMode == "true"
            }

            if (isPaginationMode) {
                // 一开始就是翻页
                enablePaginationMode();
                togglePaginationBtn.innerHTML = '<i class="fas fa-scroll"></i><span class="control-name">Scrolling</span>';
                // 隐藏 tocFloatingBtn
                let tocToggleBtn = document.getElementById('tocToggle');
                if (tocToggleBtn) {
                    tocToggleBtn.style.display = 'none';
                }
                // 隐藏 mobileTocBtn
                let mobileTocBtn = document.getElementById('mobileTocBtn');
                if (mobileTocBtn) {
                    mobileTocBtn.style.display = 'none';
                }
            }

            loadReadingProgress();  // 刚进去是 scroll，也需要恢复下进度
            
            // 切换翻页模式
            togglePaginationBtn.addEventListener('click', function() {
                isPaginationMode = !isPaginationMode;
                if (isPaginationMode) {
                    enablePaginationMode();
                    togglePaginationBtn.innerHTML = '<i class="fas fa-scroll"></i><span class="control-name">Scrolling</span>';
                    // 隐藏 tocFloatingBtn
                    let tocToggleBtn = document.getElementById('tocToggle');
                    if (tocToggleBtn) {
                        tocToggleBtn.style.display = 'none';
                    }
                } else {
                    disablePaginationMode();
                    togglePaginationBtn.innerHTML = '<i class="fas fa-book-open"></i><span class="control-name">Turning</span>';
                }
            });
            mobileTogglePaginationBtn.addEventListener('click', function() {
                isPaginationMode = !isPaginationMode;
                
                if (isPaginationMode) {
                    enablePaginationMode();
                    togglePaginationBtn.innerHTML = '<i class="fas fa-scroll"></i><span class="control-name">Scrolling</span>';
                    // 隐藏 mobileTocBtn
                    let mobileTocBtn = document.getElementById('mobileTocBtn');
                    if (mobileTocBtn) {
                        mobileTocBtn.style.display = 'none';
                    }
                } else {
                    disablePaginationMode();
                    togglePaginationBtn.innerHTML = '<i class="fas fa-book-open"></i><span class="control-name">Turning</span>';
                }
            });
            
            // 启用翻页模式
            function enablePaginationMode() {
                if (!isKindleMode()) {
                    localStorage.setItem('turning', 'true');
                } else {
                    setCookie('turning', 'true');
                }
                
                // 添加翻页模式类
                document.body.classList.add('pagination-mode');
                contentContainer.classList.add('pagination-mode');            
                
                // 关闭页面的不必要元素
                toggleHideUnnecessary(true);
                
                // 显示翻页信息
                paginationInfo.style.display = 'flex';
                
                // 分割内容为页面
                createPages();

                // 尝试加载保存的阅读进度
                loadReadingProgress();
                
                // 更新导航按钮状态
                updateNavButtons();
                
                // 添加键盘事件监听
                document.addEventListener('keydown', handleKeyDown);

                if (isKindleMode()) {
                    showNotification(`Page turning mode enabled`, 'info');
                }
            }

            // 关闭页面的不必要元素
            function toggleHideUnnecessary(hide) {
                let customCssPanel = document.querySelector(".custom-css-panel");
                let breadcrumb = document.querySelector(".breadcrumb");
                let footer = document.querySelector("footer");
                if (hide) {
                    customCssPanel.style.display = 'none';
                    breadcrumb.style.display = 'none';
                    footer.style.display = 'none';
                } else {
                    customCssPanel.style.display = 'inherit';
                    breadcrumb.style.display = 'inherit';
                    footer.style.display = 'inherit';
                }
            }
            
            // 禁用翻页模式
            function disablePaginationMode() {
                if (!isKindleMode()) {
                    localStorage.removeItem('turning');
                } else {
                    deleteCookie('turning');
                }
                // 恢复原始内容
                restoreOriginalContent();
               
            }
            
            // 创建页面
            function createPages() {
                // 保存原始内容
                const originalContent = content.innerHTML;
                
                // 获取容器高度
                const contentHeight = content.clientHeight - 150; // 减去内边距
                
                // 分割内容为页面
                let currentPageContent = '';
                let currentHeight = 0;
                const elements = Array.from(content.children || []);
                
                // 如果没有子元素，直接使用文本内容
                if (elements.length === 0) {
                    pages = [originalContent];
                    totalPages = 1;
                } else {
                    // 遍历所有子元素
                    elements.forEach(element => {
                        const elementHeight = element.offsetHeight;
                        
                        // 如果当前页面高度加上新元素高度超过容器高度，创建新页面
                        if (currentHeight + elementHeight > contentHeight && currentHeight > 0) {
                            pages.push(currentPageContent);
                            currentPageContent = '';
                            currentHeight = 0;
                        }
                        
                        // 添加元素到当前页面
                        currentPageContent += element.outerHTML;
                        currentHeight += elementHeight;
                    });
                    
                    // 添加最后一页
                    if (currentPageContent) {
                        pages.push(currentPageContent);
                    }
                    
                    totalPages = pages.length;
                }

                pageJumpInput.setAttribute('max', totalPages);

                // 清空内容容器
                content.innerHTML = '';
                
                // 创建页面元素
                pages.forEach((pageContent, index) => {
                    const pageElement = document.createElement('div');
                    pageElement.className = 'pagination-page';
                    pageElement.innerHTML = pageContent;
                    content.appendChild(pageElement);
                });
            }
            
            // 显示指定页面
            function showPage(pageIndex) {
                // 隐藏所有页面
                document.querySelectorAll('.pagination-page').forEach(page => {
                    page.classList.remove('active', 'prev');
                });
                
                // 显示当前页面
                const currentPageElement = document.querySelectorAll('.pagination-page')[pageIndex];
                if (currentPageElement) {
                    currentPageElement.classList.add('active');
                }
                
                // 更新当前页面索引
                currentPage = pageIndex;
                currentPageEl.textContent = currentPage + 1;
                totalPagesEl.textContent = totalPages;
                
                // 更新跳转输入框
                pageJumpInput.value = currentPage + 1;
                
                // 更新进度指示器
                updateProgressIndicator();

                // 更新导航按钮状态
                updateNavButtons();

                // 保存阅读进度
                saveReadingProgress();

                // 更新目录锚点
                updateTocHighlight();
            }
            
            // 更新导航按钮状态
            function updateNavButtons() {
                prevPageBtn.disabled = currentPage === 0;
                nextPageBtn.disabled = currentPage === totalPages - 1;
            }

            // 更新进度指示器
            function updateProgressIndicator() {
                const progress = ((currentPage + 1) / totalPages) * 100;
                progressFill.style.width = `${progress}%`;
            }
            
            // 恢复原始内容
            function restoreOriginalContent() {
                // 这里需要重新加载原始内容
                // 在实际应用中，您可能需要保存原始内容或重新获取
                // 这里我们简单重新加载页面
                if (isKindleMode() || confirm('Are you sure you want to exit the page-turning mode?')) {
                    location.reload();
                } else {
                    // 如果用户取消，重新启用翻页模式
                    // 什么也不干
                }
            }

            // 保存阅读进度
            function saveReadingProgress() {
                if (isPaginationMode && !isKindleMode()) {
                    // 翻页模式
                    let storageKey = getStorageKey("turning");
                    localStorage.setItem(storageKey, currentPage.toString());
                }
            }

            // 加载阅读进度
            function loadReadingProgress() {
                if (isKindleMode()) {
                    if (isPaginationMode) {
                        showPage(0);
                    }
                    return
                }

                if (isPaginationMode) {
                    // 翻页模式
                    let storageKey = getStorageKey("turning");
                    let savedPage = localStorage.getItem(storageKey);
                
                    if (savedPage !== null) {
                        const pageIndex = parseInt(savedPage, 10);
                        if (pageIndex >= 0 && pageIndex < totalPages) {
                            showPage(pageIndex);
                            
                            // 显示加载进度提示
                            showNotification(`Reading progress loaded: Page ${pageIndex + 1}`, 'info');
                        }
                    } else {
                        showPage(0);
                    }
                } else {
                    // 滚动模式
                    let storageKey = getStorageKey("scroll");
                    let savedPos = localStorage.getItem(storageKey);
                    let windowHeight = window.innerHeight;
                    window.scrollTo({
                        top: parseInt(savedPos),
                        behavior: 'smooth'
                    });
                    // 显示加载进度提示
                    showNotification(`Reading progress loaded: Scroll position ${Math.round( savedPos / (document.documentElement.scrollHeight - windowHeight) * 100 )}%`, 'info');
                }
            }
            
            // 键盘事件处理
            function handleKeyDown(e) {
                if (!isPaginationMode || isKindleMode()) return;
                
                switch(e.key) {
                    case 'ArrowLeft':
                        if (currentPage > 0) {
                            showPage(currentPage - 1);
                        }
                        break;
                    case 'ArrowRight':
                        if (currentPage < totalPages - 1) {
                            showPage(currentPage + 1);
                        }
                        break;
                }
            }

            // 跳转到指定页面
            goToPageBtn.addEventListener('click', function() {
                const pageNum = parseInt(pageJumpInput.value, 10);
                if (pageNum >= 1 && pageNum <= totalPages) {
                    showPage(pageNum - 1);
                } else {
                    showNotification(`Please enter a valid page number (1-${totalPages})`, 'warning');
                    pageJumpInput.value = currentPage + 1;
                }
            });
            
            // 跳转输入框回车事件
            pageJumpInput.addEventListener('keypress', function(e) {
                if (e.key === 'Enter') {
                    goToPageBtn.click();
                }
            });

            // 上一页按钮事件
            prevPageBtn.addEventListener('click', function() {
                if (currentPage > 0) {
                    showPage(currentPage - 1);
                } else {
                    showNotification(`Reached the start of this chapter.`, 'warning');
                }
            });
            
            // 下一页按钮事件
            nextPageBtn.addEventListener('click', function() {
                if (currentPage < totalPages - 1) {
                    showPage(currentPage + 1);
                } else {
                    showNotification(`All pages of this chapter read. Click for the next chapter.`, 'warning');
                }
            });

            // 检查当前的基路径
            if (!path.startsWith("/book/")) {
                // 获取基路径
                let basePath = path.split('/book/');
                basePath = basePath[0] + "/";
                // 处理所有资源，都要加上基路径
                addBasePath(basePath);
            }

            function addBasePath(basePath) {
                // 处理所有链接、图片、脚本和样式表
                const resources = document.querySelectorAll('iframe[src^="/"], a[href^="/"], img[src^="/"], script[src^="/"], link[rel="stylesheet"][href^="/"]');
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

            // 自定义 css
            customCssFunc();

            function customCssFunc() {
                if (isKindleMode()) {
                    return;
                }
                // 自定义CSS功能
                const cssPanelToggle = document.getElementById('cssPanelToggle');
                const cssPanelContent = document.getElementById('cssPanelContent');
                const customCssInput = document.getElementById('customCssInput');
                const saveCssBtn = document.getElementById('saveCssBtn');
                const saveAsDefaultBtn = document.getElementById('saveAsDefaultBtn');
                const resetCssBtn = document.getElementById('resetCssBtn');
                const previewCssBtn = document.getElementById('previewCssBtn');
                const loadDefaultBtn = document.getElementById('loadDefaultBtn');
                const storageKey = `custom_css_${book_hash}`;
                const defaultStorageKey = `custom_css_default`;
                // 切换面板展开/收起
                cssPanelToggle.addEventListener('click', function() {
                    cssPanelContent.classList.toggle('expanded');
                    const icon = cssPanelToggle.querySelector('i');
                    if (cssPanelContent.classList.contains('expanded')) {
                        icon.classList.remove('fa-chevron-down');
                        icon.classList.add('fa-chevron-up');
                    } else {
                        icon.classList.remove('fa-chevron-up');
                        icon.classList.add('fa-chevron-down');
                    }
                });
                // 加载保存的自定义CSS
                function loadCustomCss() {
                    // 首先尝试加载特定书籍的CSS
                    const savedCss = localStorage.getItem(storageKey);
                    if (savedCss) {
                        customCssInput.value = savedCss;
                        applyCustomCss(savedCss);
                        return;
                    }
                    
                    // 如果没有特定书籍的CSS，尝试加载默认CSS
                    const defaultCss = localStorage.getItem(defaultStorageKey);
                    if (defaultCss) {
                        customCssInput.value = defaultCss;
                        applyCustomCss(defaultCss);
                    }
                }
                // 应用自定义CSS到页面
                function applyCustomCss(css) {
                    // 移除之前添加的自定义样式
                    const existingStyle = document.getElementById('custom-user-css');
                    if (existingStyle) {
                        existingStyle.remove();
                    }
                    
                    if (css.trim()) {
                        // 创建新的style元素并添加到head
                        const styleElement = document.createElement('style');
                        styleElement.id = 'custom-user-css';
                        styleElement.textContent = css;
                        document.head.appendChild(styleElement);
                    }
                }
                // 保存自定义CSS
                saveCssBtn.addEventListener('click', function() {
                    const css = customCssInput.value;
                    localStorage.setItem(storageKey, css);
                    applyCustomCss(css);
                    
                    // 显示保存成功提示
                    showNotification('Saved for current book!', 'success');
                });
                // 保存为默认样式
                saveAsDefaultBtn.addEventListener('click', function() {
                    const css = customCssInput.value;
                    if (confirm('Are you sure to save as the default style? This will affect all books that do not have a custom style.')) {
                        localStorage.setItem(defaultStorageKey, css);
                        showNotification('Saved as a default style!', 'success');
                    }
                });
                // 加载默认样式
                loadDefaultBtn.addEventListener('click', function() {
                    const defaultCss = localStorage.getItem(defaultStorageKey);
                    if (!defaultCss) {
                        showNotification('Default style not found!', 'warning');
                        return;
                    }
                    
                    if (confirm('Are you sure to load the default style? This will replace the current CSS code.')) {
                        customCssInput.value = defaultCss;
                        applyCustomCss(defaultCss);
                        showNotification('The default style has been loaded!', 'success');
                    }
                });
                // 重置自定义CSS
                resetCssBtn.addEventListener('click', function() {
                    if (confirm('Are you sure to reset? This will clear the custom CSS code for this book.')) {
                        customCssInput.value = '';
                        localStorage.removeItem(storageKey);
                        applyCustomCss('');
                        
                        // 重置后尝试加载默认样式
                        const defaultCss = localStorage.getItem(defaultStorageKey);
                        if (defaultCss) {
                            customCssInput.value = defaultCss;
                            applyCustomCss(defaultCss);
                        }
                        
                        showNotification('The custom style for this book has been reset!', 'info');
                    }
                });
                // 预览自定义CSS
                previewCssBtn.addEventListener('click', function() {
                    const css = customCssInput.value;
                    applyCustomCss(css);
                    showNotification('Applied!', 'info');
                });

                // 初始化 - 加载保存的CSS
                loadCustomCss();
            }
            
            // 显示通知
            function showNotification(message, type) {
                // 移除现有通知
                const existingNotification = document.querySelector('.custom-css-notification');
                if (existingNotification) {
                    existingNotification.remove();
                }
                // 创建新通知
                const notification = document.createElement('div');
                notification.className = `custom-css-notification ${type}`;
                notification.textContent = message;
                
                // 添加到页面
                document.body.appendChild(notification);
                
                // 自动移除
                setTimeout(() => {
                    notification.classList.add('fade-out');
                    setTimeout(() => {
                        if (notification.parentNode) {
                            notification.parentNode.removeChild(notification);
                        }
                    }, 300);
                }, 3000);
            }
            
            
            // iframe 处理
            let iframe = document.getElementById('bookHomeIframe');
            iframe.addEventListener('load', function() {
                loadBookHomeToc();
                iframeAddEvent();
            });
            function loadBookHomeToc() {
                try {
                    const iframeDoc = iframe.contentDocument || iframe.contentWindow.document;
                    // 使用 iframeDoc 进行操作
                    let bookHomeToc = iframeDoc.querySelector('.chapter-list');
                    let iframeBody = iframeDoc.querySelector('body');
                    let iframeFooter = iframeDoc.querySelector('footer');
                    let iframeContainer = iframeDoc.querySelector('.container');
                    let topControls = iframeDoc.querySelector('.top-controls');
                    let readingControls = iframeDoc.querySelector('.reading-controls');
                    let breadcrumb = iframeDoc.querySelector('.breadcrumb');
                    let bookInfoCard = iframeDoc.querySelector('.book-info-card');
                    let tocHeader = iframeDoc.querySelector('.toc-header'); 

                    topControls.style.display = 'none';
                    breadcrumb.style.display = 'none';
                    bookInfoCard.style.display = 'none';
                    iframeFooter.style.display = 'none';
                    tocHeader.style.display = 'none';
                    readingControls.style.display = 'none';
                    bookHomeToc.style.width = "100%";
                    bookHomeToc.style.maxHeight = "100%";
                    iframeBody.style.padding = 0;
                    iframeContainer.style.padding = 0;
                    iframeContainer.style.margin = 0; 
                } catch (e) {
                    console.log('Can not reach iframe:', e.message);
                }
            }

            function iframeAddEvent() {
                try {
                    const iframeDoc = iframe.contentDocument || iframe.contentWindow.document;
                    // 使用 iframeDoc 进行操作
                    let allLinks = iframeDoc.querySelectorAll('a');
                    allLinks.forEach( link => {
                        link.addEventListener('click', function(event) {
                        // 阻止默认行为（在iframe中打开） 
                        event.preventDefault(); 
                        // 获取链接URL 
                        var href = this.getAttribute('href'); 
                        // 在父页面中打开链接 
                        window.location.href = href; 
                        return false; 
                        });
                    });

                    // 书籍目录锚点滚动
                    mobileBookHomeBtn.addEventListener('click', function(){
                        scrollBookHomeToc();
                    });
                    bookHomeToggle.addEventListener('click', function(){
                        scrollBookHomeToc();
                    });

                    function scrollBookHomeToc() {
                        if (anchor != '') { // 后面有 var anchor 的声明和取值
                            targetEl =  iframeDoc.getElementById(anchor.substr(1));
                            if (targetEl) {
                                var rect = targetEl.getBoundingClientRect();
                                // 滚动到元素位置
                                iframe.contentWindow.scrollTo({
                                    top: rect.top + iframe.contentWindow.pageYOffset,
                                    behavior: 'smooth'
                                });
                            }
                        }
                    }
                } catch (e) {
                    console.log('Can not reach iframe:', e.message);
                }
            }
            
            // 代码高亮
            if (!isKindleMode()) {
                hljs.highlightAll();
            }
            
            function switchCodeTheme(isDark) {
                const lightTheme = document.querySelector('link[href*="highlight.js"][id*="light"]');
                const darkTheme = document.querySelector('link[href*="highlight.js"][id*="dark"]');
                
                if (lightTheme && darkTheme) {
                    if (isDark) {
                    lightTheme.disabled = true;
                    darkTheme.disabled = false;
                    } else {
                    lightTheme.disabled = false;
                    darkTheme.disabled = true;
                    }
                }
            }
            

            // 包裹所有表格
            function wrapAllTables() {
                // 获取页面中所有table元素
                const tables = document.querySelectorAll('table');
                let wrappedCount = 0;
                
                // 遍历每个表格
                tables.forEach((table, index) => {
                    // 如果表格已经被包裹，跳过
                    if (table.parentElement && table.parentElement.classList.contains('table-wrapper')) {
                        return;
                    }
                    
                    // 创建包裹div
                    const wrapper = document.createElement('div');
                    wrapper.className = 'table-wrapper';
                    
                    // 将表格插入到包裹div中
                    table.parentNode.insertBefore(wrapper, table);
                    wrapper.appendChild(table);
                    
                    wrappedCount++;
                });
                
                return wrappedCount;
            }
            wrapAllTables();

            // 书籍目录锚点更新
            const lastPart = pathParts[pathParts.length - 1];
            var anchor = '';
            if (lastPart.startsWith('chapter_') && lastPart.endsWith('.html')) {
                anchor = "#" + lastPart.replace('.html', '');
            }
            if (anchor !== '') {
                let bookHomes = document.querySelectorAll('.a-book-home');
                bookHomes.forEach(item => {
                    item.href += anchor;
                });
                if (!isKindleMode()) {
                    localStorage.setItem(book_hash, anchor);
                } else {
                    setCookie(book_hash, anchor);
                }   
                
                let bookHomeIframe = document.querySelector('#bookHomeIframe');
                bookHomeIframe.src += anchor;
            }

            // 主题切换功能
            const themeToggle = document.getElementById('themeToggle');
            const mobileThemeBtn = document.getElementById('mobileThemeBtn');
            const themeIcon = themeToggle.querySelector('i');
            
            // 检查本地存储中的主题设置
            let currentTheme =  'light';
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
                mobileThemeBtn.querySelector('i').classList.remove('fa-moon');
                mobileThemeBtn.querySelector('i').classList.add('fa-sun');
                switchCodeTheme(true);
            }
            
            // 切换主题
            function toggleTheme() {
                document.body.classList.toggle('dark-mode');
                
                if (document.body.classList.contains('dark-mode')) {
                    themeIcon.classList.remove('fa-moon');
                    themeIcon.classList.add('fa-sun');
                    mobileThemeBtn.querySelector('i').classList.remove('fa-moon');
                    mobileThemeBtn.querySelector('i').classList.add('fa-sun');
                    if (!isKindleMode()) {
                        localStorage.setItem('theme', 'dark');
                    } else {
                        setCookie('theme', 'dark');
                    }
                    switchCodeTheme(true);
                } else {
                    themeIcon.classList.remove('fa-sun');
                    themeIcon.classList.add('fa-moon');
                    mobileThemeBtn.querySelector('i').classList.remove('fa-sun');
                    mobileThemeBtn.querySelector('i').classList.add('fa-moon');
                    if (!isKindleMode()) {
                        localStorage.setItem('theme', 'light');
                    } else {
                        setCookie('theme', 'light');
                    }
                    switchCodeTheme(false);
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
                
                if (!document.body.classList.contains('pagination-mode')) {
                    // 滚动模式进度条
                    progressBar.style.width = progress + '%';
                }

                if (!isKindleMode()) {
                    if (!document.body.classList.contains('pagination-mode')) {
                        // 保存阅读进度
                        let curStorageKey = getStorageKey("scroll");
                        localStorage.setItem(curStorageKey, window.scrollY + 20);  // 加一点偏移
                    }
                }
                
                // 更新目录高亮
                updateTocHighlight();
            });
            
            // 目录功能
            const tocToggle = document.getElementById('tocToggle');
            const bookHomeToggle = document.getElementById('bookHomeToggle');
            const tocFloating = document.getElementById('tocFloating');
            const bookHomeFloating = document.getElementById('bookHomeFloating');
            const mobileTocBtn = document.getElementById('mobileTocBtn');
            const mobileBookHomeBtn = document.getElementById('mobileBookHomeBtn');
            const tocClose = document.getElementById('tocClose');
            const bookHomeClose = document.getElementById('bookHomeClose');
            const tocList = document.getElementById('tocList');
            
            // 生成目录
            generateToc();
            
            // 切换目录显示 - 桌面端
            function tocFloatingScrolling() {
                // 滚动到正确的位置
                const activeLi = document.querySelector('.toc-list li.active');
                const tocList = document.getElementById('tocList');
                if (activeLi) {
                    // 计算 activeLi 相对于 ul 的顶部偏移量
                    const offsetTop = activeLi.offsetTop;
                    tocList.scrollTop = offsetTop - 20;  // 加点偏移
                }
            }
            tocToggle.addEventListener('click', function() {
                tocFloating.classList.toggle('active');
                tocFloatingScrolling();
            });
            bookHomeToggle.addEventListener('click', function() {
                bookHomeFloating.classList.toggle('active');
                loadBookHomeToc();
            });
            
            // 切换目录显示 - 移动端
            mobileTocBtn.addEventListener('click', function() {
                tocFloating.classList.toggle('active');
                tocFloatingScrolling();
                // 移动端点击后高亮按钮
                mobileTocBtn.classList.toggle('active');
            });
            mobileBookHomeBtn.addEventListener('click', function() {
                bookHomeFloating.classList.toggle('active');
                // 移动端点击后高亮按钮
                mobileBookHomeBtn.classList.toggle('active');
                loadBookHomeToc();
            });
            
            // 关闭目录
            tocClose.addEventListener('click', function() {
                tocFloating.classList.remove('active');
                mobileTocBtn.classList.remove('active');
            });
            bookHomeClose.addEventListener('click', function() {
                bookHomeFloating.classList.remove('active');
                mobileBookHomeBtn.classList.remove('active');
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

                // 滚动到对应位置
                tocFloatingScrolling();
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
            const scrollThreshold = 1; // 滚动阈值，避免轻微滚动触
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

                    // 关闭窗口
                    fontControls.classList.toggle('show');
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
    <script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.11.1/highlight.min.js"></script>
</body>
</html>
"""
        # kindle 支持，不能压缩 css 和 js
        chapter_html = minify_html.minify(chapter_html, minify_css=False, minify_js=False)
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
        
        # 删除原来的 extracted，以后都不用了
        if os.path.exists(self.extract_dir):
            try:
                shutil.rmtree(self.extract_dir)
            except Exception:
                pass

        # print(f"Resource files copied to: {resources_dir}")
    
    def get_book_info(self):
        """获取书籍信息"""
        cover = ""
        if self.cover_info:
            cover = os.path.normpath(os.path.join(self.resources_base, self.cover_info["href"]))
        return {
            'title': self.book_title,
            'temp_dir': self.temp_dir,
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
