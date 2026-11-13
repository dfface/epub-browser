import asyncio
import os
import tempfile
import threading
import unittest
from pathlib import Path

from epub_browser.server_concurrency import SetupStateMonitor, StatKeyedCache, run_db


class DatabaseCancellationTests(unittest.IsolatedAsyncioTestCase):
    async def test_cancellation_waits_for_an_in_flight_database_call(self):
        loop = asyncio.get_running_loop()
        started = asyncio.Event()
        release = threading.Event()

        def write():
            loop.call_soon_threadsafe(started.set)
            release.wait(timeout=5)

        task = asyncio.create_task(run_db(write))
        await asyncio.wait_for(started.wait(), timeout=5)
        try:
            task.cancel()
            await asyncio.sleep(0)
            self.assertFalse(task.done())
        finally:
            release.set()
            with self.assertRaises(asyncio.CancelledError):
                await task


class StatKeyedCacheTests(unittest.TestCase):
    def test_unchanged_file_is_served_from_memory(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, 'manifest.json')
            path.write_text('{"a": "1"}', encoding='utf-8')
            loads = []

            def load():
                loads.append(True)
                return path.read_text(encoding='utf-8')

            cache = StatKeyedCache(path, load)
            self.assertEqual(cache.get(), '{"a": "1"}')
            self.assertEqual(cache.get(), '{"a": "1"}')
            self.assertEqual(len(loads), 1)

    def test_rewritten_file_is_reloaded_on_next_request(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, 'manifest.json')
            path.write_text('{"a": "1"}', encoding='utf-8')
            cache = StatKeyedCache(path, lambda: path.read_text(encoding='utf-8'))
            self.assertEqual(cache.get(), '{"a": "1"}')

            path.write_text('{"a": "2"}', encoding='utf-8')
            stat_result = os.stat(path)
            os.utime(
                path,
                ns=(stat_result.st_atime_ns, stat_result.st_mtime_ns + 1_000_000),
            )

            self.assertEqual(cache.get(), '{"a": "2"}')

    def test_missing_file_keeps_the_original_exception(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, 'missing.json')
            cache = StatKeyedCache(path, lambda: path.read_text(encoding='utf-8'))
            with self.assertRaises(OSError):
                cache.get()


class SetupStateMonitorTests(unittest.IsolatedAsyncioTestCase):
    async def test_ready_state_never_probes_per_request(self):
        probes = []

        def probe():
            probes.append(True)
            return True

        monitor = SetupStateMonitor(probe, initial_ready=True)
        self.assertFalse(await monitor.setup_required())
        self.assertFalse(await monitor.setup_required())
        self.assertEqual(probes, [])

    async def test_pending_setup_probes_off_loop_and_recovers(self):
        state = {'ready': False}

        def probe():
            return state['ready']

        monitor = SetupStateMonitor(probe, initial_ready=False)
        self.assertTrue(await monitor.setup_required())

        state['ready'] = True
        await asyncio.sleep(0.15)
        self.assertFalse(await monitor.setup_required())
        self.assertFalse(await monitor.setup_required())

    async def test_mark_complete_closes_the_window_immediately(self):
        monitor = SetupStateMonitor(lambda: False, initial_ready=False)
        self.assertTrue(await monitor.setup_required())
        monitor.mark_complete()
        self.assertFalse(await monitor.setup_required())

    async def test_revalidate_picks_up_admin_removal(self):
        state = {'ready': True}

        def probe():
            return state['ready']

        monitor = SetupStateMonitor(probe, initial_ready=True)
        self.assertFalse(await monitor.setup_required())

        state['ready'] = False
        monitor.request_revalidate()
        self.assertTrue(await monitor.setup_required())
