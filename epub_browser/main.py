#!/usr/bin/env python3
"""
EPUB to Web Converter
将EPUB文件转换为可在浏览器中阅读的网页格式
支持多本书籍同时转换
"""

import os
import sys
import argparse
import zipfile
import tempfile
import shutil
import webbrowser
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import unquote, urlparse
import xml.etree.ElementTree as ET
import json
import re
import hashlib
from pathlib import Path

class EPUBProcessor:
    """处理EPUB文件的类"""
    
    def __init__(self, epub_path, output_dir=None):
        self.epub_path = epub_path
        self.book_name = Path(epub_path).stem  # 获取文件名（不含扩展名）
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
        self.chapters = []
        self.toc = []  # 存储目录结构
        self.resources_base = "resources"  # 资源文件的基础路径
        
    def extract_epub(self):
        """解压EPUB文件"""
        try:
            with zipfile.ZipFile(self.epub_path, 'r') as zip_ref:
                zip_ref.extractall(self.extract_dir)
            print(f"EPUB file extracted to: {self.extract_dir}")
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
            
            print(f"Parsed NCX table of contents items: {[(t['title'], t['src']) for t in toc]}")
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
                print(f"Found {len(self.toc)} table of contents items from NCX file")
            
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
            
            print(f"Found {len(self.chapters)} chapters")
            print(f"Chapter list: {[(c['title'], c['path']) for c in self.chapters]}")
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
        
        print(f"Chapter title not found: {chapter_path}")
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
        
        print(f"Web interface created at: {self.web_dir}")
        return self.web_dir
    
    def create_index_page(self):
        """创建索引页面"""
        index_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{self.book_title}</title>
    <style>
        body {{
            font-family: Arial, sans-serif;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
            line-height: 1.6;
        }}
        .header {{
            text-align: center;
            margin-bottom: 40px;
            border-bottom: 2px solid #333;
            padding-bottom: 20px;
        }}
        .chapter-list {{
            list-style-type: none;
            padding: 0;
        }}
        .chapter-list li {{
            margin: 5px 0;
            padding: 8px 10px;
            border-left: 3px solid #0066cc;
            background-color: #f9f9f9;
        }}
        .chapter-list a {{
            text-decoration: none;
            color: #333;
            display: block;
        }}
        .chapter-list a:hover {{
            color: #0066cc;
            background-color: #f0f0f0;
        }}
        .toc-level-0 {{ margin-left: 0px; }}
        .toc-level-1 {{ margin-left: 20px; font-size: 0.95em; }}
        .toc-level-2 {{ margin-left: 40px; font-size: 0.9em; }}
        .toc-level-3 {{ margin-left: 60px; font-size: 0.85em; }}
        .back-link {{
            display: inline-block;
            margin-bottom: 20px;
            padding: 5px 10px;
            background-color: #f0f0f0;
            border-radius: 3px;
            text-decoration: none;
            color: #333;
        }}
        .back-link:hover {{
            background-color: #e0e0e0;
        }}
    </style>
</head>
<body>
    <a href="/" class="back-link">← Back to Library</a>
    <div class="header">
        <h1>{self.book_title}</h1>
        <p>EPUB to Web Converter</p>
    </div>
    
    <h2>Table of Contents</h2>
    <ul class="chapter-list">
"""
        
        # 如果有详细的toc信息，使用toc生成目录
        if self.toc:
            # 创建章节路径到索引的映射
            chapter_index_map = {}
            for i, chapter in enumerate(self.chapters):
                chapter_index_map[chapter['path']] = i
            
            print(f"Chapter index mapping: {chapter_index_map}")
            
            # 根据toc生成目录
            for toc_item in self.toc:
                level_class = f"toc-level-{min(toc_item.get('level', 0), 3)}"
                chapter_index = chapter_index_map.get(toc_item['src'])
                
                if chapter_index is not None:
                    index_html += f'        <li class="{level_class}"><a href="chapter_{chapter_index}.html">{toc_item["title"]}</a></li>\n'
                else:
                    print(f"Chapter index not found: {toc_item['src']}")
        else:
            # 回退到简单章节列表
            for i, chapter in enumerate(self.chapters):
                index_html += f'        <li><a href="chapter_{i}.html">{chapter["title"]}</a></li>\n'
        
        index_html += """    </ul>
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
        prev_link = f'<a href="chapter_{chapter_index-1}.html">Previous Chapter</a>' if chapter_index > 0 else ''
        next_link = f'<a href="chapter_{chapter_index+1}.html">Next Chapter</a>' if chapter_index < len(self.chapters) - 1 else ''
        
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{chapter_title} - {self.book_title}</title>
    {style_links}
    <style>
        body {{
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
            line-height: 1.6;
        }}
        .navigation {{
            display: flex;
            justify-content: space-between;
            margin: 20px 0;
            padding: 10px 0;
            border-top: 1px solid #ddd;
            border-bottom: 1px solid #ddd;
        }}
        .content {{
            margin: 20px 0;
        }}
        .chapter-title {{
            text-align: center;
            margin-bottom: 30px;
            padding-bottom: 10px;
            border-bottom: 1px solid #eee;
        }}
        a {{
            color: #0066cc;
            text-decoration: none;
        }}
        a:hover {{
            background-color: #0066cc;
            color: white;
        }}
        img {{
            max-width: 100%;
            height: auto;
        }}
        .back-link {{
            display: inline-block;
            margin-bottom: 20px;
            padding: 5px 10px;
            background-color: #f0f0f0;
            border-radius: 3px;
            text-decoration: none;
            color: #333;
        }}
        .back-link:hover {{
            background-color: #e0e0e0;
        }}
    </style>
</head>
<body>
    <a href="index.html" class="back-link">← Back to Table of Contents</a>
    <div class="navigation">
        <div>{prev_link}</div>
        <div><a href="index.html">Table of Contents</a></div>
        <div>{next_link}</div>
    </div>
    
    <article class="content">
        {content}
    </article>
    
    <div class="navigation">
        <div>{prev_link}</div>
        <div><a href="index.html">Table of Contents</a></div>
        <div>{next_link}</div>
    </div>
</body>
</html>"""
    
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
        
        print(f"Resource files copied to: {resources_dir}")
    
    def get_book_info(self):
        """获取书籍信息"""
        return {
            'title': self.book_title,
            'path': self.web_dir,
            'name': self.book_name,
            'hash': self.book_hash
        }
    
    def cleanup(self):
        """清理临时文件"""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
            print(f"Temporary files cleaned up for: {self.book_title}")

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
        """发送图书馆首页"""
        library_html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>EPUB Library</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
            line-height: 1.6;
        }
        .header {
            text-align: center;
            margin-bottom: 40px;
            border-bottom: 2px solid #333;
            padding-bottom: 20px;
        }
        .book-list {
            list-style-type: none;
            padding: 0;
        }
        .book-list li {
            margin: 10px 0;
            padding: 15px;
            border: 1px solid #ddd;
            border-radius: 5px;
            background-color: #f9f9f9;
        }
        .book-list a {
            text-decoration: none;
            color: #333;
            display: block;
        }
        .book-list a:hover {
            background-color: #f0f0f0;
        }
        .book-title {
            font-size: 1.2em;
            font-weight: bold;
        }
        .book-file {
            font-size: 0.9em;
            color: #666;
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>EPUB Library</h1>
        <p>All converted EPUB books</p>
    </div>
    
    <h2>Available Books</h2>
    <ul class="book-list">
"""
        
        for book_hash, book_info in self.library.books.items():
            library_html += f"""
        <li>
            <a href="/book/{book_hash}/">
                <div class="book-title">{book_info['title']}</div>
                <div class="book-file">File: {book_info['web_dir']}</div>
            </a>
        </li>"""
        
        library_html += """
    </ul>
</body>
</html>"""
        
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.send_header('Content-Length', str(len(library_html.encode('utf-8'))))
        self.end_headers()
        self.wfile.write(library_html.encode('utf-8'))
    
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

class EPUBLibrary:
    """EPUB图书馆类，管理多本书籍"""
    
    def __init__(self, output_dir=None):
        self.output_dir = output_dir
        self.books = {}  # 存储所有书籍信息，使用哈希作为键
        self.server = None
        
        # 创建基础目录用于服务器
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
            print(f"Adding book: {epub_path}")
            processor = EPUBProcessor(epub_path, self.output_dir)
            
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
                'name': book_info['name'],
                'processor': processor
            }
            
            print(f"Successfully added book: {book_info['title']} (Hash: {book_info['hash']})")
            return True
            
        except Exception as e:
            print(f"Failed to add book {epub_path}: {e}")
            return False
    
    def start_server(self, port=8000, no_browser=False):
        """启动Web服务器"""
        if not self.books:
            print("No books available to serve")
            return False
        
        try:
            # 创建自定义请求处理器
            handler = lambda *args, **kwargs: EPUBHTTPRequestHandler(
                *args, library=self, **kwargs
            )
            
            # 启动服务器
            server_address = ('', port)
            self.server = HTTPServer(server_address, handler)
            
            print(f"Web server started: http://localhost:{port}")
            print("Available books:")
            for book_hash, book_info in self.books.items():
                print(f"  - {book_info['title']}: http://localhost:{port}/book/{book_hash}/")
            print("Press Ctrl+C to stop the server")
            
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
        if os.path.exists(self.base_directory):
            shutil.rmtree(self.base_directory)
            print(f"Cleaned up library base directory: {self.base_directory}")
        
        # 清理各本书籍的临时文件
        for book_hash, book_info in self.books.items():
            try:
                book_info['processor'].cleanup()
                print(f"Cleaned up temporary files for: {book_info['title']}")
            except Exception as e:
                print(f"Failed to clean up {book_info['title']}: {e}")

def main():
    parser = argparse.ArgumentParser(description='EPUB to Web Converter - Multi-book Support')
    parser.add_argument('filename', nargs='+', help='EPUB file path(s)')
    parser.add_argument('--port', '-p', type=int, default=8000, help='Web server port (default: 8000)')
    parser.add_argument('--no-browser', action='store_true', help='Do not automatically open browser')
    parser.add_argument('--output-dir', '-o', help='Output directory for converted books')
    parser.add_argument('--keep-files', action='store_true', help='Keep converted files after server stops')
    
    args = parser.parse_args()
    
    # 检查文件是否存在
    for filename in args.filename:
        if not os.path.exists(filename):
            print(f"Error: File '{filename}' does not exist")
            sys.exit(1)
    
    # 创建图书馆
    library = EPUBLibrary(args.output_dir)
    
    try:
        # 添加所有书籍
        success_count = 0
        # 收集真实的 epub file
        real_epub_files = []
        for filename in args.filename:
            files = library.epub_file_discover(filename)
            real_epub_files.extend(files)
        for filename in real_epub_files:
            if library.add_book(filename):
                success_count += 1
        
        if success_count == 0:
            print("No books were successfully processed")
            sys.exit(1)
        
        print(f"Successfully processed {success_count} out of {len(args.filename)} books")
        
        # 启动服务器
        library.start_server(args.port, args.no_browser)
        
    except KeyboardInterrupt:
        print("\nShutting down server...")
    except Exception as e:
        print(f"Error occurred: {e}")
    finally:
        library.stop_server()
        if not args.keep_files:
            library.cleanup()

if __name__ == '__main__':
    main()