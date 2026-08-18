import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from .reporting import Reporter


class EpubFileHandler(FileSystemEventHandler):
    """Normalize watchdog events into ServerLibraryManager operations."""

    def __init__(self, manager, reporter=None):
        super().__init__()
        self.manager = manager
        self.reporter = reporter or Reporter(False)
        self._executor = None
        self._pending_tasks_dict = {}
        self._lock = threading.Lock()

    @property
    def executor(self):
        if self._executor is None:
            self._executor = ThreadPoolExecutor(
                max_workers=5,
                thread_name_prefix="epub_watch_events",
            )
        return self._executor

    @property
    def lock(self):
        return self._lock

    @property
    def pending_tasks(self):
        return self._pending_tasks_dict

    def _submit_task(self, task_id, func, *args, **kwargs):
        with self.lock:
            previous = self.pending_tasks.get(task_id)
            if previous is not None:
                previous.cancel()
            future = self.executor.submit(func, *args, **kwargs)
            self.pending_tasks[task_id] = future

        def cleanup(completed_future):
            with self.lock:
                if self.pending_tasks.get(task_id) is completed_future:
                    del self.pending_tasks[task_id]

        future.add_done_callback(cleanup)
        return future

    @staticmethod
    def _is_epub(path):
        return str(path).lower().endswith(".epub")

    @staticmethod
    def _is_hidden(path):
        return Path(path).name.startswith(".")

    def _queue_path(self, path):
        if hasattr(self.manager, "queue_path"):
            return self.manager.queue_path(Path(path))
        # Compatibility for callers still using the old in-memory facade.
        if hasattr(self.manager, "add_book"):
            return self.manager.add_book(os.fspath(path))
        return None

    def _mark_deleted(self, path):
        if hasattr(self.manager, "mark_deleted"):
            return self.manager.mark_deleted(Path(path))
        return None

    def on_created(self, event):
        if event.is_directory or not self._is_epub(event.src_path):
            return
        if self._is_hidden(event.src_path):
            return
        self._submit_task(
            f"queue:{event.src_path}",
            self._queue_path,
            event.src_path,
        )

    def on_modified(self, event):
        self.on_created(event)

    def on_deleted(self, event):
        if event.is_directory or not self._is_epub(event.src_path):
            return
        self._submit_task(
            f"delete:{event.src_path}",
            self._mark_deleted,
            event.src_path,
        )

    def on_moved(self, event):
        if event.is_directory:
            return
        if self._is_epub(event.src_path):
            self._submit_task(
                f"delete:{event.src_path}",
                self._mark_deleted,
                event.src_path,
            )
        if self._is_epub(event.dest_path) and not self._is_hidden(event.dest_path):
            self._submit_task(
                f"queue:{event.dest_path}",
                self._queue_path,
                event.dest_path,
            )

    def shutdown(self):
        if self._executor is not None:
            self._executor.shutdown(wait=True)


class EPUBWatcher:
    def __init__(self, paths, manager, reporter=None):
        self.paths = tuple(paths)
        self.manager = manager
        self.reporter = reporter or Reporter(False)
        self.observer = None

    @staticmethod
    def normalize_path(path):
        return os.path.abspath(os.path.normpath(path))

    @classmethod
    def is_subpath(cls, child_path, parent_path):
        child = cls.normalize_path(child_path)
        parent = cls.normalize_path(parent_path)
        try:
            return os.path.commonpath([child, parent]) == parent
        except ValueError:
            return False

    def remove_nested_paths(self, paths=None):
        normalized = sorted(
            {self.normalize_path(path) for path in (paths or self.paths)},
            key=lambda value: (len(value), value),
        )
        selected = []
        for path in normalized:
            if not any(self.is_subpath(path, parent) for parent in selected):
                selected.append(path)
        return selected

    def get_monitor_path(self):
        candidates = []
        for configured in self.paths:
            path = Path(configured).expanduser()
            if path.is_file():
                candidates.append(path.parent)
            elif path.is_dir():
                candidates.append(path)
        return self.remove_nested_paths(candidates)

    def watch(self, stop_event=None):
        valid_paths = self.get_monitor_path()
        if not valid_paths:
            self.reporter.detail("No valid path to monitor")
            return None
        event_handler = EpubFileHandler(self.manager, reporter=self.reporter)
        self.observer = Observer()
        for path in valid_paths:
            self.observer.schedule(event_handler, path, recursive=True)
            self.reporter.detail(f"Monitoring EPUB source: {path}")
        self.observer.start()
        try:
            while stop_event is None or not stop_event.is_set():
                time.sleep(0.25)
        except KeyboardInterrupt:
            pass
        finally:
            self.observer.stop()
            event_handler.shutdown()
            self.observer.join()
        return self.observer
