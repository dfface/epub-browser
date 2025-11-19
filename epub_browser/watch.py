import os
import time
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from datetime import datetime
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

class EpubFileHandler(FileSystemEventHandler):
    """处理 .epub 文件变化的自定义事件处理器"""

    def __init__(self, library):
        super().__init__()
        self.library = library
        # 延迟初始化线程池，避免序列化问题
        self._executor = None
        self._pending_tasks = {}
        self._lock = None
        self._library_lock = None
    
    @property
    def executor(self):
        """延迟初始化线程池执行器"""
        if self._executor is None:
            self._executor = ThreadPoolExecutor(max_workers=5)
        return self._executor
    
    @property
    def lock(self):
        """延迟初始化锁"""
        if self._lock is None:
            self._lock = threading.Lock()
        return self._lock

    @property
    def library_lock(self):
        """延迟初始化锁"""
        if self._library_lock is None:
            self._library_lock = threading.Lock()
        return self._library_lock
    
    @property
    def pending_tasks(self):
        """延迟初始化待处理任务字典"""
        if not hasattr(self, '_pending_tasks_dict'):
            self._pending_tasks_dict = {}
        return self._pending_tasks_dict
    
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
    
    def _submit_task(self, task_id, func, *args, **kwargs):
        """提交任务到线程池并跟踪状态"""
        with self.lock:
            if task_id in self.pending_tasks:
                # 如果相同任务已经在执行，取消它
                self.pending_tasks[task_id].cancel()
            
            future = self.executor.submit(func, *args, **kwargs)
            self.pending_tasks[task_id] = future
            
            # 添加回调来清理完成的任务
            def cleanup(f):
                with self.lock:
                    if task_id in self.pending_tasks:
                        del self.pending_tasks[task_id]
            
            future.add_done_callback(cleanup)
            return future
    
    def _handle_created(self, src_path):
        """处理文件创建的后台任务"""
        with self.library_lock:
            try:
                print(f"[{str(datetime.now())}][Create] Processing EPUB file: {src_path}")
                ok, book_info = self.library.add_book(src_path)
                if ok:
                    book_hash = book_info['hash']
                    self.library.move_book(book_hash)
                    self.library.create_library_home()
                    print(f"[{str(datetime.now())}][Create] Added book({book_hash}): {book_info['title']}")
            except Exception as e:
                print(f"[{str(datetime.now())}][Create] Error processing {src_path}: {e}")
    
    def on_created(self, event):
        if not event.is_directory and event.src_path.endswith('.epub'):
            # if os.path.basename(event.src_path).startswith(".") or self.has_hidden_component(event.src_path):
            #     return
            src_path = event.src_path
            print(f"[{str(datetime.now())}][Create] EPUB file detected: {src_path}")
            if (os.path.basename(src_path).startswith(".")) or (self.has_hidden_component(src_path)):
                print(f"[{str(datetime.now())}][Create] Hidden file will not be processed: {src_path}")
                return
            # 提交到线程池执行
            task_id = f"create_{src_path}"
            self._submit_task(task_id, self._handle_created, src_path)
    
    def _handle_modified(self, src_path):
        """处理文件修改的后台任务"""
        with self.library_lock:
            try:
                print(f"[{str(datetime.now())}][Modify] Processing EPUB file: {src_path}")
                ok, book_info = self.library.add_book(src_path)
                if ok:
                    book_hash = book_info['hash']
                    self.library.move_book(book_hash)
                    self.library.create_library_home()
                    print(f"[{str(datetime.now())}][Modify] Updated book({book_hash}): {book_info['title']}")
            except Exception as e:
                print(f"[{str(datetime.now())}][Modify] Error processing {src_path}: {e}")
    
    def on_modified(self, event):
        if not event.is_directory and event.src_path.endswith('.epub'):
            # if os.path.basename(event.src_path).startswith(".") or self.has_hidden_component(event.src_path):
            #     return
            src_path = event.src_path
            print(f"[{str(datetime.now())}][Modify] EPUB file detected: {src_path}")
            if (os.path.basename(src_path).startswith(".")) or (self.has_hidden_component(src_path)):
                print(f"[{str(datetime.now())}][Modify] Hidden file will not be processed: {src_path}")
                return
            # 提交到线程池执行
            task_id = f"modify_{src_path}"
            self._submit_task(task_id, self._handle_modified, src_path)
    
    def _handle_deleted(self, src_path, book_hash, book_info):
        """处理文件删除的后台任务"""
        with self.library_lock:
            try:
                print(f"[{str(datetime.now())}][Delete] Processing deletion: {src_path}")
                self.library.remove_book(book_hash)
                self.library.create_library_home()
                print(f"[{str(datetime.now())}][Delete] Deleted book({book_hash}): {book_info['title']}")
            except Exception as e:
                print(f"[{str(datetime.now())}][Delete] Error processing {src_path}: {e}")
    
    def on_deleted(self, event):
        if not event.is_directory and event.src_path.endswith('.epub'):
            # if os.path.basename(event.src_path).startswith(".") or self.has_hidden_component(event.src_path):
            #     return
            print(f"[{str(datetime.now())}][Delete] EPUB file detected: {event.src_path}")
            if event.src_path in self.library.file2hash:
                book_hash = self.library.file2hash[event.src_path]
                if book_hash in self.library.books:
                    book_info = self.library.books[book_hash]
                    # 提交到线程池执行
                    task_id = f"delete_{event.src_path}"
                    self._submit_task(task_id, self._handle_deleted, event.src_path, book_hash, book_info)
    
    def _handle_move_source(self, src_path, book_hash, book_info):
        """处理移动操作源文件的后台任务"""
        with self.library_lock:
            try:
                print(f"[{str(datetime.now())}][Move] Processing source deletion: {src_path}")
                self.library.remove_book(book_hash)
                self.library.create_library_home()
                print(f"[{str(datetime.now())}][Move] Deleted book({book_hash}): {book_info['title']}")
            except Exception as e:
                print(f"[{str(datetime.now())}][Move] Error processing source {src_path}: {e}")
    
    def _handle_move_destination(self, dest_path):
        """处理移动操作目标文件的后台任务"""
        try:
            print(f"[{str(datetime.now())}][Move] Wait for 3 seconds to allow the file to stabilize before adding it: {dest_path}")
            time.sleep(3)  # 等待文件稳定
            print(f"[{str(datetime.now())}][Move] Processing destination addition: {dest_path}")
            with self.library_lock:
                ok, book_info = self.library.add_book(dest_path)
                if ok:
                    book_hash = book_info['hash']
                    self.library.move_book(book_hash)
                    self.library.create_library_home()
                    print(f"[{str(datetime.now())}][Move] Added book({book_hash}): {book_info['title']}")
        except Exception as e:
            print(f"[{str(datetime.now())}][Move] Error processing destination {dest_path}: {e}")
    
    def on_moved(self, event):
        if not event.is_directory and event.src_path.endswith('.epub'):
            print(f"[{str(datetime.now())}][Move] EPUB file detected: from {event.src_path} to {event.dest_path}")
            # 处理源文件删除（如果存在）
            if event.src_path in self.library.file2hash:
                book_hash = self.library.file2hash[event.src_path]
                if book_hash in self.library.books:
                    book_info = self.library.books[book_hash]
                    # 提交源文件处理到线程池
                    task_id = f"move_src_{event.src_path}"
                    self._submit_task(task_id, self._handle_move_source, event.src_path, book_hash, book_info)
            
            # 处理目标文件添加
            if event.dest_path.endswith('.epub'):
                if (not os.path.basename(event.dest_path).startswith(".")) and (not self.has_hidden_component(event.dest_path)):
                    dest_path = event.dest_path
                    if (os.path.basename(dest_path).startswith(".")) or (self.has_hidden_component(dest_path)):
                        print(f"[{str(datetime.now())}][Move] Hidden file will not be processed: {dest_path}")
                        return
                    # 提交目标文件处理到线程池
                    task_id = f"move_dest_{dest_path}"
                    self._submit_task(task_id, self._handle_move_destination, dest_path)
    
    def shutdown(self):
        """关闭线程池"""
        if self._executor is not None:
            self._executor.shutdown(wait=True)


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

    def watch(self, stop_event=None):
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
                if stop_event is not None and stop_event.is_set():
                    break
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        finally:
            self.observer.stop()
            print("Monitoring has been stopped")
            # 关闭线程池
            event_handler.shutdown()
        
        self.observer.join()

        return self.observer