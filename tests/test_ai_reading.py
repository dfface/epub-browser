import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from epub_browser.ai_client import ProviderConfig
from epub_browser.ai_reading import (
    AIReadingService,
    ReadingRequest,
    _normalize_result,
    extract_chapter_text,
)
from epub_browser.auth import BootstrapCredentials
from epub_browser.state import StateStore


class _FakeClient:
    calls = []

    def __init__(self, config: ProviderConfig):
        self.config = config

    def complete(self, messages):
        type(self).calls.append(messages)
        return json.dumps(
            {
                "quick": {"title": "Guide", "summary": "Useful overview", "key_points": ["One"]},
                "structure": {"overview": "A → B", "nodes": [{"label": "A", "detail": "Start"}], "links": []},
                "deep": {"themes": ["Theme"], "questions": ["Why?"], "applications": []},
                "evidence": [{"chapter_index": 0, "quote": "Source sentence", "reason": "Support"}],
            }
        )


class AIReadingServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.store = StateStore(self.root / "data.sqlite")
        self.owner = self.store.initialize(BootstrapCredentials("owner", "password"))
        self.member = self.store.create_user("reader", "hash", role="member")
        self.store.set_ai_settings(
            enabled=True,
            base_url="https://provider.example/v1",
            api_key="secret",
            model="reader-model",
            timeout_seconds=30,
            max_concurrency=2,
            daily_limit=20,
        )
        self.store.set_ai_user_access(self.member.user_id, enabled=True, daily_limit=10)
        self.book = self.store.resolve_book(
            self.root / "book.epub", "urn:test:reading", "fingerprint", {"title": "Book"}
        )
        chapter = self.root / "public" / "book" / self.book.book_id / "chapter_0.html"
        chapter.parent.mkdir(parents=True)
        chapter.write_text(
            "<html><body><nav>Ignore navigation</nav><article><p>Source sentence.</p><p>Read this carefully.</p><script>ignore()</script></article></body></html>",
            encoding="utf-8",
        )
        _FakeClient.calls = []
        self.service = AIReadingService(self.store, self.root / "public", _FakeClient)

    async def asyncTearDown(self):
        self.temporary.cleanup()

    async def _wait_for_job(self, job_id):
        for _ in range(100):
            job = self.store.get_ai_job(job_id, self.member.user_id)
            if job["status"] in {"complete", "failed"}:
                return job
            await asyncio.sleep(0.01)
        self.fail("AI generation task did not finish")

    async def test_chapter_generation_is_cached_and_uses_untrusted_content_boundary(self):
        request = ReadingRequest(
            scope="chapter", book_id=self.book.book_id, chapter_index=0, language="en"
        )
        started = await self.service.submit(self.member, request)
        self.assertEqual(started["status"], "queued")
        completed = await self._wait_for_job(started["job"]["id"])
        self.assertEqual(completed["status"], "complete")
        self.assertIsNotNone(completed["result_id"])
        self.assertEqual(len(_FakeClient.calls), 1)
        self.assertIn("<UNTRUSTED_EPUB_CONTENT>", _FakeClient.calls[0][1]["content"])
        self.assertIn("Source sentence.", _FakeClient.calls[0][1]["content"])
        self.assertNotIn("ignore()", _FakeClient.calls[0][1]["content"])

        cached = await self.service.submit(self.member, request)
        self.assertTrue(cached["cached"])
        self.assertEqual(cached["result"]["content"]["quick"]["summary"], "Useful overview")
        self.assertEqual(len(_FakeClient.calls), 1)

    async def test_followups_are_private_and_charged_to_the_owner(self):
        request = ReadingRequest(scope="chapter", book_id=self.book.book_id, chapter_index=0)
        started = await self.service.submit(self.member, request)
        await self._wait_for_job(started["job"]["id"])
        cached = await self.service.submit(self.member, request)
        followup = await self.service.follow_up(
            self.member, cached["result"]["id"], "What should I remember?", "en"
        )
        for _ in range(100):
            entries = self.store.list_ai_followups(cached["result"]["id"], self.member.user_id)
            if entries and entries[0]["status"] in {"complete", "failed"}:
                break
            await asyncio.sleep(0.01)
        self.assertEqual(entries[0]["status"], "complete")
        self.assertEqual(self.store.list_ai_followups(cached["result"]["id"], self.owner.user_id), ())


class ChapterExtractionTests(unittest.TestCase):
    def test_extract_chapter_text_omits_script_and_navigation(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "chapter.html"
            path.write_text("<p>Hello</p><script>secret</script><style>x</style><p>World</p>")
            self.assertEqual(extract_chapter_text(path), "Hello\nWorld")


class ResultNormalizationTests(unittest.TestCase):
    def test_deep_report_items_remain_structured_instead_of_becoming_json_text(self):
        result = _normalize_result(json.dumps({
            "quick": {"summary": "Summary"},
            "deep": {
                "themes": [{"theme": "Trade-off", "analysis": "Safety and autonomy are balanced."}],
                "questions": [{"question": "Who decides?", "why": "It exposes the decision boundary."}],
                "applications": [{"context": "School policy", "advice": "Pair limits with support."}],
            },
        }))

        self.assertEqual(result["deep"]["themes"], [{
            "title": "Trade-off", "analysis": "Safety and autonomy are balanced.",
        }])
        self.assertEqual(result["deep"]["questions"], [{
            "question": "Who decides?", "why": "It exposes the decision boundary.",
        }])
        self.assertEqual(result["deep"]["applications"], [{
            "context": "School policy", "advice": "Pair limits with support.",
        }])
