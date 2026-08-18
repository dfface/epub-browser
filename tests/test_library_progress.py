import asyncio
import unittest
from pathlib import Path

from epub_browser.library_progress import LibraryProgressBroker


class LibraryProgressBrokerTests(unittest.IsolatedAsyncioTestCase):
    async def test_generation_counters_and_terminal_phase(self):
        broker = LibraryProgressBroker()
        broker.start_generation("startup")
        broker.mark_discovered(total=3, removed=1)
        broker.record_reused(Path("/private/library/one.epub"))
        broker.conversion_started()
        broker.record_converted(Path("/private/library/two.epub"))
        broker.record_failure(
            Path("/private/library/broken.epub"),
            "unable to parse /private/staging/package.opf",
        )
        broker.catalog_published(active_books=2)
        snapshot = broker.finish(active_books=2).as_dict()

        self.assertEqual(snapshot["generation"], 1)
        self.assertEqual(snapshot["phase"], "degraded")
        self.assertEqual(snapshot["completed"], 3)
        self.assertEqual(snapshot["converted"], 1)
        self.assertEqual(snapshot["reused"], 1)
        self.assertEqual(snapshot["failed"], 1)
        self.assertEqual(snapshot["removed"], 1)
        self.assertEqual(snapshot["in_flight"], 0)
        self.assertEqual(snapshot["catalog_revision"], 1)
        self.assertEqual(snapshot["failures"][0]["filename"], "broken.epub")
        self.assertNotIn("/private/", str(snapshot))

    async def test_new_generation_retains_catalog_revision_but_resets_batch(self):
        broker = LibraryProgressBroker()
        broker.start_generation("startup")
        broker.mark_discovered(0, 0)
        broker.catalog_published(0)
        broker.finish(0)

        snapshot = broker.start_generation("watch")

        self.assertEqual(snapshot.generation, 2)
        self.assertEqual(snapshot.catalog_revision, 1)
        self.assertEqual(snapshot.completed, 0)
        self.assertEqual(snapshot.failures, ())

    async def test_subscriber_gets_initial_and_only_latest_pending_snapshot(self):
        broker = LibraryProgressBroker()
        loop = asyncio.get_running_loop()
        subscription = broker.subscribe(loop)
        initial = await asyncio.wait_for(subscription.next(), 0.2)
        broker.start_generation("startup")
        broker.mark_discovered(4, 0)
        broker.conversion_started()
        await asyncio.sleep(0)
        latest = await asyncio.wait_for(subscription.next(), 0.2)

        self.assertEqual(initial.phase, "idle")
        self.assertEqual(latest.phase, "processing")
        self.assertEqual(latest.total, 4)
        self.assertEqual(latest.in_flight, 1)
        subscription.close()
        self.assertEqual(broker.subscriber_count, 0)

    async def test_failure_message_sanitizes_windows_unc_paths(self):
        broker = LibraryProgressBroker()
        broker.start_generation("startup")
        broker.mark_discovered(1, 0)
        broker.record_failure(
            Path("/private/library/broken.epub"),
            r"unable to parse \\server\share\staging\package.opf",
        )

        snapshot = broker.snapshot().as_dict()

        self.assertNotIn(r"\\server\share\staging\package.opf", str(snapshot))
        self.assertEqual(snapshot["failures"][0]["message"], "unable to parse source file")
