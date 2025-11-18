import os
import time
from pathlib import Path
from datetime import datetime
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

class EpubFileHandler(FileSystemEventHandler):
    """处理 .epub 文件变化的自定义事件处理器"""

    def __init__(self, library):
        super().__init__()
        self.library = library
    
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
    
    def on_created(self, event):
        if not event.is_directory and event.src_path.endswith('.epub'):
            if os.path.basename(event.src_path).startswith(".") or self.has_hidden_component(event.src_path):
                return
            title = event.src_path
            if event.src_path in self.library.file2hash:
                book_hash = self.library.file2hash[event.src_path]
                if book_hash in self.library.books:
                    book_info = self.library.books[book_hash]
                    title = book_info['title']
            print(f"[{str(datetime.now())}][Create] EPUB file: {title}")
            ok, book_info = self.library.add_book(event.src_path)
            if ok:
                book_hash = book_info['hash']
                self.library.move_book(book_hash)
                self.library.create_library_home()
                print(f"[{str(datetime.now())}]Added book({book_hash}): {book_info['title']}")
    
    def on_modified(self, event):
        if not event.is_directory and event.src_path.endswith('.epub'):
            if os.path.basename(event.src_path).startswith(".") or self.has_hidden_component(event.src_path):
                return
            title = event.src_path
            if event.src_path in self.library.file2hash:
                book_hash = self.library.file2hash[event.src_path]
                if book_hash in self.library.books:
                    book_info = self.library.books[book_hash]
                    title = book_info['title']
            print(f"[{str(datetime.now())}][Modify] EPUB file: {title}")
            ok, book_info = self.library.add_book(event.src_path)
            if ok:
                book_hash = book_info['hash']
                self.library.move_book(book_hash)
                self.library.create_library_home()
                print(f"[{str(datetime.now())}]Updated book({book_hash}): {book_info['title']}")
    
    def on_deleted(self, event):
        if not event.is_directory and event.src_path.endswith('.epub'):
            if os.path.basename(event.src_path).startswith(".") or self.has_hidden_component(event.src_path):
                return
            title = event.src_path
            if event.src_path in self.library.file2hash:
                book_hash = self.library.file2hash[event.src_path]
                if book_hash in self.library.books:
                    book_info = self.library.books[book_hash]
                    title = book_info['title']
            print(f"[{str(datetime.now())}][Delete] EPUB file: {title}")
            if event.src_path in self.library.file2hash:
                book_hash = self.library.file2hash[event.src_path]
                book_info = self.library.books[book_hash]
                self.library.remove_book(book_hash)
                self.library.create_library_home()
                print(f"[{str(datetime.now())}]Deleted book({book_hash}): {book_info['title']}")

    def on_moved(self, event):
        if not event.is_directory and event.src_path.endswith('.epub'):
            title = os.path.basename(event.src_path)
            if event.src_path in self.library.file2hash:
                book_hash = self.library.file2hash[event.src_path]
                if book_hash in self.library.books:
                    book_info = self.library.books[book_hash]
                    title = book_info['title']
            print(f"[{str(datetime.now())}][Move] EPUB file({title}): from {event.src_path} to {event.dest_path}")
            if (not os.path.basename(event.src_path).startswith(".")) and (not self.has_hidden_component(event.src_path)) and (event.src_path in self.library.file2hash):
                book_hash = self.library.file2hash[event.src_path]
                book_info = self.library.books[book_hash]
                self.library.remove_book(book_hash)
                self.library.create_library_home()
                print(f"[{str(datetime.now())}]Deleted book({book_hash}): {book_info['title']}")
        if event.dest_path.endswith('.epub'):
            print(f"[{str(datetime.now())}]Waiting to add book...")
            if (not os.path.basename(event.dest_path).startswith(".")) and (not self.has_hidden_component(event.dest_path)):
                ok, book_info = self.library.add_book(event.dest_path)
                if ok:
                    book_hash = book_info['hash']
                    self.library.move_book(book_hash)
                    self.library.create_library_home()
                    print(f"[{str(datetime.now())}]Added book({book_hash}): {book_info['title']}")

class EPUBWatcher:
    def __init__(self, paths, library):
        self.paths = paths
        self.library = library
    
    def normalize_path(self, path):
        """规范化路径，确保使用绝对路径且没有多余的斜杠"""
        return os.path.abspath(os.path.normpath(path))

    def is_subpath(self, child_path, parent_path):
        """检查一个路径是否是另一个路径的子路径"""
        child = self.normalize_path(child_path)
        parent = self.normalize_path(parent_path)
        
        # 如果两个路径相同，返回 True
        if child == parent:
            return True
        
        # 检查子路径
        try:
            # 使用 commonpath 方法检查路径关系
            common = os.path.commonpath([child, parent])
            return common == parent
        except ValueError:
            # 在不同驱动器上时可能会出错
            return False
        
    def remove_nested_paths(self):
        """移除嵌套路径，只保留最顶层的父目录"""
        # 先规范化所有路径
        normalized_paths = [self.normalize_path(path) for path in self.paths]
        
        # 按路径长度排序（短路径在前）
        sorted_paths = sorted(normalized_paths, key=len)
        
        # 找出所有非嵌套路径
        unique_paths = []
        for path in sorted_paths:
            # 检查当前路径是否已经是某个已选路径的子目录
            is_nested = False
            for parent in unique_paths:
                if self.is_subpath(path, parent):
                    is_nested = True
                    break
            
            # 如果不是嵌套路径，则添加到结果中
            if not is_nested:
                unique_paths.append(path)
        
        return unique_paths

    def has_no_hidden_component(self, path_str):
        """检查路径中间是否有以.开头的隐藏组件"""
        path = Path(path_str).resolve()  # 转换为绝对路径并解析符号链接
        parts = path.parts
        
        # 跳过根目录（如果是绝对路径）和最后一个组件（如果是文件）
        # 只检查路径中间的目录组件
        for part in parts[1:]:  # parts[0] 通常是根目录如 '/' 或 'C:\\'
            if part.startswith('.'):
                return False
        return True

    def get_monitor_path(self):
        # 收集需要监控的文件/目录
        valid_path = []
        for filename in self.paths:
            if os.path.isfile(filename):
                # 如果输入的是文件，则监控其所在目录
                watch_path = os.path.dirname(filename)
                valid_path.append(watch_path)
                continue
            else:
                if os.path.exists(filename):
                    valid_path.append(filename)
                    continue
        # 处理 valid_path 是否有嵌套目录或重复目录
        valid_path = list(set(valid_path))
        valid_path = self.remove_nested_paths()
        valid_path = list(filter(self.has_no_hidden_component, valid_path))
        return valid_path

    def watch(self):
        valid_paths = self.get_monitor_path()
        self.valid_paths = valid_paths
        if len(valid_paths) == 0:
            print("No valid path to monitor.")
            return None
        # 创建观察者和事件处理器
        event_handler = EpubFileHandler(self.library)
        self.observer = Observer()
        for path in valid_paths:
            self.observer.schedule(event_handler, path, recursive=True)
            print(f"Monitoring has been added: {path}")

        # 启动监控
        self.observer.start()
        print(f"Start monitoring changes to EPUB files ...")
        
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            self.observer.stop()
            print("Monitoring has been stopped")
        
        self.observer.join()

        return self.observer