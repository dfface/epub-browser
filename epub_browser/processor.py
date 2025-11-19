import os
import zipfile
import tempfile
import shutil
import xml.etree.ElementTree as ET
import re
import hashlib
import json
import minify_html
from concurrent.futures import ThreadPoolExecutor
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
        self.description = None
        self.cover_info = None
        self.lang = 'en'
        self.chapters = []
        self.toc = []  # 存储目录结构
        self.resources_base = "resources"  # 资源文件的基础路径
    
    def cleanup(self):
        # 诸如 extract 失败
        try:
            if os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir, ignore_errors=True)
        except Exception:
            pass

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

            # 获取描述
            description = tree.find('.//dc:description', ns)
            self.description = description.text if description is not None and description.text else None

            # 获取语言
            lang = root.find('.//dc:language', ns)
            self.lang = lang.text if lang is not None and lang.text else 'en'
                
            # 获取manifest（所有资源）
            manifest = {}
            opf_dir = os.path.dirname(opf_path)
            # 获取封面
            cover_info = self.find_cover_info(tree, ns)
            if cover_info:
                href = cover_info["href"]
                cover_info["full_path"] = os.path.normpath(os.path.join(opf_dir, href)) if href else None
            self.cover_info = cover_info
            # 获取其他资源 xhtml、font、css 等
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
    <link rel="stylesheet" href="/assets/fa.all.min.css">
    <link rel="stylesheet" href="/assets/book.css">
    <link rel="icon" type="image/svg+xml" href="/assets/favion.svg">
"""
        index_html += """
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
    <div class="breadcrumb header" data-id="breadcrumb">
        <a href="/index.html#{self.book_hash}"><i class="fas fa-home"></i><span style="margin-left: 8px;">Home</span></a>
        <span class="breadcrumb-separator">/</span>
        <span class="breadcrumb-current" id="book_home">{self.book_title}</span>
    </div>

    <div class="book-info-card" data-id="book-info-card">
            <div class="book-info-cover">
                <img src="{self.get_book_info()['cover']}" alt="cover">
            </div>
            <div class="book-info-content">
                <h2 class="book-info-title">{self.book_title}</h2>
                <p class="book-info-author">{" & ".join(self.authors) if self.authors else "Unknown"}</p>"""
        if self.description:
            index_html += f""" 
                <div class="book-info-desc">
                    {self.description}
                </div>"""
        index_html += """
                <div class="book-info-tags">"""
        if self.tags:
            for tag in self.tags:
                index_html += f"""<span class="book-tag">{tag}</span>"""        
        index_html += f"""
                </div>
                <div class="css-controls clearReadingProgress">
                    <button class="css-btn primary" id="clearReadingProgressBtn"><i class="fas fa-eraser"></i>Clear reading progress</button>
                </div>
            </div>
        </div>
    
    <div class="toc-container" data-id="toc-container">
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
<div class="reading-controls" data-id="reading-controls">
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
<footer class="footer" data-id="footer">
    <p>EPUB Library &copy; {datetime.now().year} | Powered by <a href="https://github.com/dfface/epub-browser" target="_blank">epub-browser</a></p>
</footer>"""

        index_html += """
<script src="/assets/book.js" defer></script>
<script>
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

// 检查当前的基路径
let path = window.location.pathname;
let basePath = path.split('/book/');
// 获取基路径
basePath = basePath[0] + "/";
// 检查当前的基路径
if (!path.startsWith("/book/")) {
    // 处理所有资源，都要加上基路径
    addBasePath(basePath);
}

document.addEventListener('DOMContentLoaded', function() {
// 检查当前的基路径
let path = window.location.pathname;
let basePath = path.split('/book/');
// 获取基路径
basePath = basePath[0] + "/";

// 单独处理 js 资源，无论如何都要重新加载，因为那个脚本不再监听 DOMContentLoaded 事件了
const js_resource = document.querySelector('script[src="/assets/book.js"]');
if (window.initScriptBook) {
    console.log("init")
    window.initScriptBook();
} else {
    const src = js_resource.getAttribute('src');
    newScript = reloadScriptByReplacement(js_resource, basePath.substr(0, basePath.length - 1) + src);
    newScript.onload = () => {
        if (window.initScriptBook) {
            console.log("reinit")
            window.initScriptBook();
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
        # kindle 支持，不能压缩 css 和 js
        index_html = minify_html.minify(index_html, minify_css=False, minify_js=False)
        with open(os.path.join(self.web_dir, 'index.html'), 'w', encoding='utf-8') as f:
            f.write(index_html)
    
    def create_chapter_pages(self):
        """创建章节页面"""
        def create_chapter_page(chapter_path, chapter, i):
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
        
        # 创建并启动线程
        with ThreadPoolExecutor(max_workers=10) as executor:  # 限制最大10个并发线程
            futures = []
            for i, chapter in enumerate(self.chapters):
                chapter_path = os.path.join(self.extract_dir, chapter['path'])
                if os.path.exists(chapter_path):
                    # 使用线程池提交任务
                    future = executor.submit(create_chapter_page, chapter_path, chapter, i)
                    futures.append(future)
                
    
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
        img_pattern1 = r'<img[^>]+src="([^"]+)"[^>]*>'
        img_pattern2 = r'<image[^>]+xlink:href="([^"]+)"[^>]*>'
        
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
            return match.group(0).replace(f'"{src}"', f'"{web_src}"')

        replaced_content = re.sub(img_pattern1, replace_img_link, content)
        replaced_content = re.sub(img_pattern2, replace_img_link, replaced_content)
        return replaced_content
    
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
        prev_href = f'href="/book/{self.book_hash}/chapter_{chapter_index-1}.html"' if chapter_index > 0 else ''
        next_href = f'href="/book/{self.book_hash}/chapter_{chapter_index+1}.html"' if chapter_index < len(self.chapters) - 1 else ''
        prev_chapter = f'Perv chapter' if chapter_index > 0 else 'First chapter'
        next_chapter = f'Next chapter' if chapter_index < len(self.chapters) - 1 else 'Last chapter'
        prev_link = f'<a {prev_href} alt="previous" class="prev-chapter"> <div class="control-btn"> <i class="fas fa-arrow-left"></i><span class="control-name">{prev_chapter}</span></div></a>'
        next_link = f'<a {next_href} alt="next" class="next-chapter"> <div class="control-btn"> <i class="fas fa-arrow-right"></i><span class="control-name">{next_chapter}</span></div></a>'
        prev_link_mobile = f'<a {prev_href} alt="previous"> <div class="control-btn"> <i class="fas fa-arrow-left"></i><span>{prev_chapter.replace(' chapter', '')}</span></div></a>'
        next_link_mobile = f'<a {next_href} alt="next"> <div class="control-btn"> <i class="fas fa-arrow-right"></i><span>{next_chapter.replace(' chapter', '')}</span></div></a>'
        
        chapter_html =  f"""<!DOCTYPE html>
<html lang="{self.lang}">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{chapter_title} - {self.book_title}</title>
    {style_links}
    <link id="code-light" rel="stylesheet" href="/assets/github.min.css">
    <link id="code-dark" rel="stylesheet" disabled href="/assets/github-dark.min.css">
    <link rel="stylesheet" href="/assets/fa.all.min.css">
    <link rel="stylesheet" href="/assets/chapter.css">
    <link rel="icon" type="image/svg+xml" href="/assets/favion.svg">
"""
        chapter_html += """
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
        <div class="breadcrumb header" data-id="breadcrumb">
            <a href="/index.html#{self.book_hash}" alt="home"><i class="fas fa-home"></i><span style="margin-left:8px;">Home</span></a>
            <span class="breadcrumb-separator">/</span>
            <a href="/book/{self.book_hash}/index.html" alt="bookHome" class="a-book-home">{self.book_title}</a>
            <span class="breadcrumb-separator">/</span>
            <span class="breadcrumb-current">{chapter_title}</span>
        </div> 

        <div class="custom-css-panel" data-id="custom-css-panel">
            <div class="panel-header" id="cssPanelToggle">
                <h3><i class="fas fa-paint-brush"></i>Custom CSS</h3>
                <button class="panel-toggle">
                    <i class="fas fa-chevron-down"></i>
                </button>
            </div>
            <div class="panel-content" id="cssPanelContent">
                <div class="css-editor">
                    <textarea id="customCssInput" placeholder="Please input your CSS code... For example: .content{{margin: 50px}}"></textarea>
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

        <div class="content-container" data-id="content-container">
            <article class="content" id="content">
            {content}
            </article>
        </div>

        <div class="navigation" data-id="navigation">
            {prev_link}
            <a href="/index.html#{self.book_hash}" alt="home" id="navigationHomeBtn">
                <div class="control-btn">
                    <i class="fas fa-home"></i>
                    <span class="control-name">Home</span>
                </div>
            </a>

            <div id="paginationInfo" style="display: none;">
                <div class="control-btn" id="prevPage" style="padding-right: 40px;">
                    <i class="fas fa-chevron-left"></i>
                    <span class="control-name">Prev page</span>
                </div>
                <div style="display: flex; flex-direction: row;">
                    <span class="page-indicator">
                        <span id="currentPage" style="display:none;"></span>
                        <input type="number" style="margin-right:2px;" id="pageJumpInput" min="1" max="1" value="1"> / <span id="totalPages">1</span>
                    </span>
                    <div class="control-btn" style="padding-left:10px;" id="goToPage" title="Jump">
                        <i class="fas fa-arrow-right-to-bracket"></i>
                        <span class="control-name">Jump</span>
                    </div>
                </div>
                <div style="display: flex; flex-direction: row;" class="page-height-adjustment">
                    <span>
                        <input type="number" style="margin-right:10px;" id="pageHeightInput" value="1">
                    </span>
                    <div class="control-btn" id="setPageHeight" style="padding: 0;" title="Set page height">
                        <i class="fas fa-ruler-vertical"></i>
                        <span class="control-name">Set page height</span>
                    </div>
                </div>
                <div class="control-btn" id="nextPage" style="padding-left: 40px;">
                    <i class="fas fa-chevron-right"></i>
                    <span class="control-name">Next page</span>
                </div>
            </div>
            {next_link}
        </div>
    </div>

    <div class="font-controls" id="fontControls" data-id="fontControls">
        <div class="font-family-control">
            <span>Font Family</span>
        </div>
        <div class="font-family-selector">
            <select id="fontFamilySelect">
                <option value="system-ui, -apple-system, sans-serif">System default</option>
                <option value="custom">Custom by input</option>
            </select>
        </div>
        <div class="custom-font-input" id="customFontInput" style="display: none;">
            <input type="text" id="customFontFamily" placeholder="Input font name here">
            <small>Tip: Font family applies globally. Ensure it’s installed in the system.</small>
            <button class="css-btn primary" id="applyFontSettings">
                <i class="fas fa-check"></i> Apply
            </button>
        </div>

        <div>
            <span>Font Size</span>
        </div>
        <div class="font-size-control">
            <div class="font-size-btn font-small" data-size="small">A</div>
            <div class="font-size-btn font-medium active" data-size="medium">A</div>
            <div class="font-size-btn font-large" data-size="large">A</div>
        </div>
    </div>

    <div class="reading-controls" data-id="reading-controls">
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
    <div class="mobile-controls" data-id="mobile-controls">
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

    <footer class="footer" data-id="footer">
        <p>EPUB Library &copy; {datetime.now().year} | Powered by <a href="https://github.com/dfface/epub-browser" target="_blank">epub-browser</a></p>
    </footer>
"""
        chapter_html += """
    <script>
    // 检查当前的基路径
    let path = window.location.pathname;
    let basePath = path.split('/book/');
    // 获取基路径
    basePath = basePath[0] + "/";
    // 检查当前的基路径
    if (!path.startsWith("/book/")) {
        // 处理所有资源，都要加上基路径
        addBasePath(basePath);
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
    let path = window.location.pathname;
    let basePath = path.split('/book/');
    // 获取基路径
    basePath = basePath[0] + "/";
    
    // 单独处理 js 资源，无论如何都要重新加载，因为那个脚本不再监听 DOMContentLoaded 事件了
    const js_resource = document.querySelector('script[src="/assets/chapter.js"]');
    if (window.initScriptChapter) {
        window.initScriptChapter();
        console.log("init")
    } else {
        const src = js_resource.getAttribute('src');
        newScript = reloadScriptByReplacement(js_resource, basePath.substr(0, basePath.length - 1) + src);
        newScript.onload = () => {
            if (window.initScriptChapter) {
                console.log("reinit")
                window.initScriptChapter();
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
    <script src="/assets/chapter.js" defer></script>
    <script src="/assets/sortable.min.js"></script>
    <script src="/assets/highlight.min.js"></script>
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
                suffix = file.split(".")[-1]
                if suffix in ("html", "xhtml", "xml", "txt", "opf", "ncx", "mimetype"):
                    # html 不需要了，已经重新生成了
                    continue

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
        cover_path = ""
        if self.cover_info and self.cover_info['full_path']:
            cover_path = os.path.normpath(os.path.join(self.resources_base, self.cover_info["full_path"]))
        return {
            'title': self.book_title,
            'temp_dir': self.temp_dir,
            'path': self.web_dir,
            'hash': self.book_hash,
            'cover': cover_path,
            'authors': self.authors,
            'tags': self.tags,
            'origin_file_path': self.epub_path,
        }
    
    def cleanup(self):
        """清理临时文件"""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
            # print(f"Temporary files cleaned up for: {self.book_title}")
