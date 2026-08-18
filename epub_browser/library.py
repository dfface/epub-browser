import os
import tempfile
import shutil
from pathlib import Path

from .asset_publisher import AssetPublisher
from .processor import EPUBProcessor
from .reporting import Reporter
from .site import LibraryBook, publish_library_shell
from .urls import SiteURLs

class EPUBLibrary:
    """EPUB图书馆类，管理多本书籍"""
    
    def __init__(self, output_dir=None, urls=None, reporter=None):
        self.books = {}  # 存储所有书籍信息，使用哈希作为键
        self.file2hash = {} # 原书籍epub的 path -> book_hash
        self.output_dir = output_dir
        self.urls = urls or SiteURLs()
        self.reporter = reporter or Reporter(False)
        
        # 创建基础目录
        if output_dir is not None:
            Path(output_dir).mkdir(parents=True, exist_ok=True)
            self.base_directory = os.fspath(output_dir)
        else:
            self.base_directory = tempfile.mkdtemp(prefix='epub_library_')

        assets_dir = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'assets')
        self.asset_manifest = AssetPublisher(
            assets_dir,
            self.base_directory,
            urls=self.urls,
        ).publish()
        self.reporter.detail(f"Library base directory: {self.base_directory}")
    
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
            processor = EPUBProcessor(
                epub_path,
                self.base_directory,
                self.asset_manifest,
                urls=self.urls,
                reporter=self.reporter,
            )
            
            # 解压EPUB
            if not processor.extract_epub():
                processor.cleanup()
                return False, None
            
            # 解析容器文件
            opf_path = processor.parse_container()
            if not opf_path:
                self.reporter.detail(f"Unable to parse EPUB container file: {epub_path}")
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
            
            # 如果同一路径之前已有旧记录，先清理旧记录
            # （用于处理覆盖同名 EPUB 文件的情况，旧 hash 与新 hash 不同）
            origin_path = book_info['origin_file_path']
            if origin_path in self.file2hash:
                old_hash = self.file2hash[origin_path]
                new_hash = book_info['hash']
                if old_hash != new_hash and old_hash in self.books:
                    self.reporter.detail(
                        f"[Add] Replacing old version: "
                        f"{self.books[old_hash]['title']} (hash: {old_hash})"
                    )
                    self.remove_book(old_hash)
            
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
            self.file2hash[origin_path] = book_info['hash']
            
            # print(f"Successfully added book: {book_info['title']} (Hash: {book_info['hash']})")
            return True, book_info
            
        except Exception as e:
            self.reporter.detail(f"Failed to add book {epub_path}: {e}")
            return False, None
    
    def add_assets(self):
        """Publish immutable app assets and stable update entry points."""
        assets_dir = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'assets')
        self.asset_manifest = AssetPublisher(
            assets_dir,
            self.base_directory,
            urls=self.urls,
        ).publish()
            
    
    def create_library_home(self):
        """Publish the shared library shell and deterministic metadata."""
        books = tuple(
            LibraryBook(
                book_id=book_hash,
                title=book_info['title'],
                authors=tuple(book_info.get('authors') or ()),
                tags=tuple(book_info.get('tags') or ()),
                cover=(
                    f"/book/{book_hash}/{book_info['cover']}"
                    if book_info.get('cover')
                    else None
                ),
            )
            for book_hash, book_info in self.books.items()
        )
        publish_library_shell(
            Path(self.base_directory),
            books,
            self.asset_manifest,
            self.urls,
        )

    def generate_book_metadata(self):
        self.create_library_home()
    
    def move_book(self, book_hash):
        """按 href 的格式组织目录"""
        book_path = os.path.join(self.base_directory, "book")
        book_info = self.books[book_hash]
        if not book_info:
            self.reporter.detail(
                f"move {book_hash} failed, err: not exists such book info"
            )
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
            self.reporter.detail(f"move {old_path} to {cur_path} failed, err: {e}")
        try:
            # 删除原来的 temp_dir 目录
            shutil.rmtree(old_temp_dir)
        except Exception as e:
            pass

    def remove_book(self, book_hash):
        book_path = os.path.join(self.base_directory, "book")
        cur_path = os.path.join(book_path, book_hash)
        
        # Clean up file2hash mapping
        if book_hash in self.books:
            origin_path = self.books[book_hash].get('origin_file_path')
            if origin_path and origin_path in self.file2hash:
                del self.file2hash[origin_path]
        
        if os.path.exists(cur_path):
            try:
                shutil.rmtree(cur_path)
            except Exception as e:
                self.reporter.detail(f"remove {cur_path} failed, err: {e}")
        
        self.books.pop(book_hash, None)

    def reorganize_files(self):
        """按照 href 的格式组织目录"""
        # 创建 book 目录
        book_path = os.path.join(self.base_directory, "book")
        if os.path.exists(book_path):
            try:
                shutil.rmtree(book_path)
                os.mkdir(book_path)
            except Exception as e:
                self.reporter.detail(
                    f"book_path {book_path} exists, try to recreate failed, err: {e}"
                )
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
                self.reporter.detail(
                    f"move {old_path} to {cur_path} failed, err: {e}"
                )
    
    def cleanup(self):
        """清理所有文件"""
        if self.output_dir is not None:
            # 用户自己的目录，不要一个全删
            for book_hash, book_info in self.books.items():
                temp_dir = book_info['temp_dir']
                if os.path.exists(temp_dir):
                    shutil.rmtree(temp_dir, ignore_errors=True)
                    self.reporter.detail(
                        f"Cleaned up book: {book_info['title']}, path: {temp_dir}"
                    )
                middle_dir = os.path.join(self.output_dir,f"epub_{book_hash}") # 可能存在的中间文件
                if os.path.exists(middle_dir):
                    shutil.rmtree(middle_dir, ignore_errors=True)
                    self.reporter.detail(
                        f"Cleaned up book: {book_info['title']}, path: {middle_dir}"
                    )
            if os.path.exists(os.path.join(self.output_dir, "index.html")):
                os.remove(os.path.join(self.output_dir, "index.html"))
            if os.path.exists(os.path.join(self.output_dir, "sw.js")):
                os.remove(os.path.join(self.output_dir, "sw.js"))
            if os.path.exists(os.path.join(self.output_dir, "assets")):
                shutil.rmtree(os.path.join(self.output_dir, "assets"), ignore_errors=True)
            if os.path.exists(os.path.join(self.output_dir, "book")):
                shutil.rmtree(os.path.join(self.output_dir, "book"), ignore_errors=True)
            self.reporter.detail(
                f"Cleaned up files inside library base directory: {self.base_directory}"
            )
            return
        else:
            # 清理基础目录
            if os.path.exists(self.base_directory):
                shutil.rmtree(self.base_directory, ignore_errors=True)
                self.reporter.detail(
                    f"Cleaned up library base directory: {self.base_directory}"
                )
