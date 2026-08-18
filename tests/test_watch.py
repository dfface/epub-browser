import threading
import unittest
from pathlib import Path

from watchdog.events import FileCreatedEvent, FileDeletedEvent, FileMovedEvent

from epub_browser.watch import EpubFileHandler


class ImmediateFailureLibrary:
    """A library double that reproduces a fast failed EPUB parse."""

    def __init__(self):
        self.books = {}
        self.file2hash = {}
        self.add_attempted = threading.Event()

    def add_book(self, _path):
        self.add_attempted.set()
        return False, None


class EpubFileHandlerTests(unittest.TestCase):
    def test_manager_receives_normalized_create_delete_and_move_operations(self):
        class Manager:
            def __init__(self):
                self.queued = []
                self.deleted = []

            def queue_path(self, path):
                self.queued.append(Path(path))

            def mark_deleted(self, path):
                self.deleted.append(Path(path))

        manager = Manager()
        handler = EpubFileHandler(manager)

        handler.on_created(FileCreatedEvent("/tmp/created.epub"))
        handler.on_deleted(FileDeletedEvent("/tmp/deleted.epub"))
        handler.on_moved(FileMovedEvent("/tmp/old.epub", "/tmp/new.epub"))
        handler.shutdown()

        self.assertIn(Path("/tmp/created.epub"), manager.queued)
        self.assertIn(Path("/tmp/new.epub"), manager.queued)
        self.assertIn(Path("/tmp/deleted.epub"), manager.deleted)
        self.assertIn(Path("/tmp/old.epub"), manager.deleted)

    def test_fast_task_completion_does_not_deadlock_event_dispatch(self):
        library = ImmediateFailureLibrary()
        handler = EpubFileHandler(library)
        dispatch = threading.Thread(
            target=handler.on_created,
            args=(FileCreatedEvent("/tmp/new.epub"),),
            daemon=True,
        )

        dispatch.start()
        dispatch.join(timeout=1)

        self.assertTrue(library.add_attempted.wait(timeout=1))
        self.assertFalse(dispatch.is_alive(), "watchdog event dispatch deadlocked")
        handler.shutdown()

    def test_older_task_completion_keeps_newer_task_tracked(self):
        handler = EpubFileHandler(ImmediateFailureLibrary())
        first_started = threading.Event()
        second_started = threading.Event()
        release_first = threading.Event()
        release_second = threading.Event()

        def first_task():
            first_started.set()
            release_first.wait(timeout=2)

        def second_task():
            second_started.set()
            release_second.wait(timeout=2)

        first = handler._submit_task("same-path", first_task)
        self.assertTrue(first_started.wait(timeout=1))
        second = handler._submit_task("same-path", second_task)
        self.assertTrue(second_started.wait(timeout=1))

        release_first.set()
        first.result(timeout=1)

        self.assertIs(handler.pending_tasks.get("same-path"), second)
        release_second.set()
        second.result(timeout=1)
        handler.shutdown()


if __name__ == "__main__":
    unittest.main()
