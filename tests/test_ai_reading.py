import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from epub_browser.ai_client import AIProviderError, ProviderConfig
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


class _FlakyClient(_FakeClient):
    calls = []

    def complete(self, messages):
        type(self).calls.append(messages)
        if len(type(self).calls) == 1:
            raise AIProviderError("provider_server_error", retryable_without_response=True)
        answer = super().complete(messages)
        type(self).calls.pop()
        return answer


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

    async def test_second_opening_joins_the_existing_chapter_job_without_a_provider_call(self):
        request = ReadingRequest(scope="chapter", book_id=self.book.book_id, chapter_index=0)
        material, _metadata, progress_total, _segments = self.service._material_for_request(self.member, request)
        cache_key = self.service._cache_key(
            request, material, self.store.get_book_ai_profile(self.book.book_id)
        )
        self.store.create_ai_job(
            "already-running", self.member.user_id, cache_key,
            book_id=self.book.book_id, progress_total=progress_total,
        )

        joined = await self.service.submit(self.member, request)

        self.assertEqual(joined["status"], "queued")
        self.assertTrue(joined["shared"])
        self.assertEqual(joined["job"]["id"], "already-running")
        self.assertEqual(_FakeClient.calls, [])

    async def test_transient_provider_server_error_retries_once_before_failing_the_job(self):
        _FlakyClient.calls = []
        service = AIReadingService(self.store, self.root / "public", _FlakyClient)
        request = ReadingRequest(scope="chapter", book_id=self.book.book_id, chapter_index=0)

        started = await service.submit(self.member, request)
        completed = await self._wait_for_job(started["job"]["id"])

        self.assertEqual(completed["status"], "complete")
        self.assertEqual(len(_FlakyClient.calls), 2)

    def test_full_book_bridges_keep_provider_inputs_and_final_synthesis_bounded(self):
        long_chapter = "start " + ("middle " * 5000) + "finish"

        bridge_material = self.service._bridge_material(long_chapter)
        groups = self.service._bridge_groups(tuple((index, long_chapter) for index in range(30)))
        synthesis = self.service._bounded_book_bridges(["x" * 5000 for _ in range(20)])

        self.assertLessEqual(len(bridge_material), 12080)
        self.assertTrue(bridge_material.startswith("start "))
        self.assertTrue(bridge_material.endswith("finish"))
        self.assertLess(len(groups), 30)
        self.assertTrue(all(len(material) <= 12080 for _label, material in groups))
        self.assertEqual(", ".join(str(index) for index in range(30)), ", ".join(
            label for label, _material in groups
        ))
        self.assertLessEqual(len(synthesis), 36000)


class ChapterExtractionTests(unittest.TestCase):
    def test_extract_chapter_text_omits_script_and_navigation(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "chapter.html"
            path.write_text("<header>Chrome</header><nav>Menu</nav><p>Hello</p><script>secret</script><style>x</style><p>World</p>")
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
