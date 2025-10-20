#!/usr/bin/env python3
"""
EPUB to Web Converter
将EPUB文件转换为可在浏览器中阅读的网页格式
"""

import os
import sys
import argparse
import zipfile
import tempfile
import shutil
import webbrowser
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import unquote
import xml.etree.ElementTree as ET
import json
import re

class EPUBProcessor:
    """处理EPUB文件的类"""
    
    def __init__(self, epub_path):
        self.epub_path = epub_path
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
            print(f"已解压EPUB文件到: {self.extract_dir}")
            return True
        except Exception as e:
            print(f"解压EPUB文件失败: {e}")
            return False
    
    def parse_container(self):
        """解析container.xml获取内容文件路径"""
        container_path = os.path.join(self.extract_dir, 'META-INF', 'container.xml')
        if not os.path.exists(container_path):
            print("未找到container.xml文件")
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
            print(f"解析container.xml失败: {e}")
            
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
            print(f"查找toc属性失败: {e}")
        
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
            print(f"未找到NCX文件: {ncx_full_path}")
            return []
            
        try:
            # 读取文件内容并注册命名空间
            with open(ncx_full_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 注册命名空间
            ET.register_namespace('', 'http://www.daisy.org/z3986/2005/ncx/')
            
            tree = ET.parse(ncx_full_path)
            root = tree.getroot()
            
            # 获取书籍标题
            doc_title = root.find('.//{http://www.daisy.org/z3986/2005/ncx/}docTitle/{http://www.daisy.org/z3986/2005/ncx/}text')
            if doc_title is not None and doc_title.text:
                self.book_title = doc_title.text
            
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
            
            print(f"解析NCX得到目录项: {[(t['title'], t['src']) for t in toc]}")
            return toc
            
        except Exception as e:
            print(f"解析NCX文件失败: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def parse_opf(self, opf_path):
        """解析OPF文件获取书籍信息和章节列表"""
        opf_full_path = os.path.join(self.extract_dir, opf_path)
        if not os.path.exists(opf_full_path):
            print(f"未找到OPF文件: {opf_full_path}")
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
                print(f"从NCX文件中找到 {len(self.toc)} 个目录项")
            
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
            
            print(f"找到 {len(self.chapters)} 个章节")
            print(f"章节列表: {[(c['title'], c['path']) for c in self.chapters]}")
            return True
            
        except Exception as e:
            print(f"解析OPF文件失败: {e}")
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
        
        print(f"未找到章节标题: {chapter_path}")
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
        
        print(f"网页界面已创建在: {self.web_dir}")
    
    def create_index_page(self):
        """创建索引页面"""
        index_html = f"""<!DOCTYPE html>
<html lang="zh-CN">
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
    </style>
</head>
<body>
    <div class="header">
        <h1>{self.book_title}</h1>
        <p>EPUB to Web Converter</p>
    </div>
    
    <h2>目录</h2>
    <ul class="chapter-list">
"""
        
        # 如果有详细的toc信息，使用toc生成目录
        if self.toc:
            # 创建章节路径到索引的映射
            chapter_index_map = {}
            for i, chapter in enumerate(self.chapters):
                chapter_index_map[chapter['path']] = i
            
            print(f"章节索引映射: {chapter_index_map}")
            
            # 根据toc生成目录
            for toc_item in self.toc:
                level_class = f"toc-level-{min(toc_item.get('level', 0), 3)}"
                chapter_index = chapter_index_map.get(toc_item['src'])
                
                if chapter_index is not None:
                    index_html += f'        <li class="{level_class}"><a href="chapter_{chapter_index}.html">{toc_item["title"]}</a></li>\n'
                else:
                    print(f"未找到章节索引: {toc_item['src']}")
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
                    print(f"处理章节 {chapter['path']} 失败: {e}")
    
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
        prev_link = f'<a href="chapter_{chapter_index-1}.html">上一章</a>' if chapter_index > 0 else ''
        next_link = f'<a href="chapter_{chapter_index+1}.html">下一章</a>' if chapter_index < len(self.chapters) - 1 else ''
        
        return f"""<!DOCTYPE html>
<html lang="zh-CN">
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
    </style>
    <link rel="stylesheet" href="https://unpkg.com/@highlightjs/cdn-assets@11.9.0/styles/default.min.css">
    <!-- and it's easy to individually load additional languages -->
    <script src="https://unpkg.com/@highlightjs/cdn-assets@11.9.0/languages/go.min.js"></script>
    <script src="https://unpkg.com/@highlightjs/cdn-assets@11.9.0/languages/python.min.js"></script>
    <script src="https://unpkg.com/@highlightjs/cdn-assets@11.9.0/languages/bash.min.js"></script>
    <script src="https://unpkg.com/@highlightjs/cdn-assets@11.9.0/languages/java.min.js"></script>
    <script src="https://unpkg.com/@highlightjs/cdn-assets@11.9.0/languages/c++.min.js"></script>
    <script src="https://unpkg.com/@highlightjs/cdn-assets@11.9.0/languages/c.min.js"></script>
    <script>hljs.highlightAll();</script>
    <script>
    document.addEventListener('DOMContentLoaded', (event) => {{
        document.querySelectorAll('pre').forEach((el) => {{
            hljs.highlightElement(el);
        }});
    }});
    </script>
</head>
<body>
    <div class="navigation">
        <div>{prev_link}</div>
        <div><a href="index.html">目录</a></div>
        <div>{next_link}</div>
    </div>
    
    <article class="content">
        {content}
    </article>
    
    <div class="navigation">
        <div>{prev_link}</div>
        <div><a href="index.html">目录</a></div>
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
        
        print(f"资源文件已复制到: {resources_dir}")
    
    def cleanup(self):
        """清理临时文件"""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
            print("临时文件已清理")

class EPUBHTTPRequestHandler(SimpleHTTPRequestHandler):
    """自定义HTTP请求处理器"""
    
    def __init__(self, *args, web_dir=None, **kwargs):
        self.web_dir = web_dir
        super().__init__(*args, directory=web_dir, **kwargs)
    
    def log_message(self, format, *args):
        """自定义日志格式"""
        print(f"[{self.log_date_time_string()}] {format % args}")

def main():
    parser = argparse.ArgumentParser(description='EPUB to Web Converter')
    parser.add_argument('filename', help='EPUB文件路径')
    parser.add_argument('--port', '-p', type=int, default=8000, help='Web服务器端口 (默认: 8000)')
    parser.add_argument('--no-browser', action='store_true', help='不自动打开浏览器')
    
    args = parser.parse_args()
    
    if not os.path.exists(args.filename):
        print(f"错误: 文件 '{args.filename}' 不存在")
        sys.exit(1)
    
    # 处理EPUB文件
    processor = EPUBProcessor(args.filename)
    
    try:
        print(f"正在处理EPUB文件: {args.filename}")
        
        # 解压EPUB
        if not processor.extract_epub():
            sys.exit(1)
        
        # 解析容器文件
        opf_path = processor.parse_container()
        if not opf_path:
            print("无法解析EPUB容器文件")
            sys.exit(1)
        
        # 解析OPF文件
        if not processor.parse_opf(opf_path):
            sys.exit(1)
        
        # 创建网页界面
        processor.create_web_interface()
        
        # 启动Web服务器
        os.chdir(processor.web_dir)
        server_address = ('', args.port)
        httpd = HTTPServer(server_address, 
                          lambda *x, **y: EPUBHTTPRequestHandler(*x, web_dir=processor.web_dir, **y))
        
        print(f"Web服务器已启动: http://localhost:{args.port}")
        print(f"书籍标题: {processor.book_title}")
        print("按 Ctrl+C 停止服务器")
        
        # 自动打开浏览器
        if not args.no_browser:
            webbrowser.open(f'http://localhost:{args.port}')
        
        # 启动服务器
        httpd.serve_forever()
        
    except KeyboardInterrupt:
        print("\n正在关闭服务器...")
    except Exception as e:
        print(f"发生错误: {e}")
    finally:
        processor.cleanup()

if __name__ == '__main__':
    main()