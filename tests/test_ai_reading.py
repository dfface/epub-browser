import asyncio
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from epub_browser.ai_client import AIProviderError, ProviderConfig
from epub_browser.ai_reading import (
    AIReadingError,
    AIReadingService,
    ReadingRequest,
    _ModelTokenBudget,
    _estimate_messages_tokens,
    _estimate_tokens,
    _merge_chapter_layers,
    _normalize_core_result,
    _normalize_result,
    _public_ai_job,
    _split_text_by_token_budget,
    _truncate_tokens,
    extract_chapter_text,
)
from epub_browser.auth import BootstrapCredentials
from epub_browser.prompt_templates import (
    chapter_core_template,
    chapter_grounding_template,
    profile_system_prompt,
    template_for,
)
from epub_browser.state import StateStore


class _FakeClient:
    calls = []

    def __init__(self, config: ProviderConfig):
        self.config = config

    def complete(self, messages, *, max_tokens=None):
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

    def complete(self, messages, *, max_tokens=None):
        type(self).calls.append(messages)
        if len(type(self).calls) <= 3:
            raise AIProviderError("provider_server_error", retryable_without_response=True)
        answer = super().complete(messages, max_tokens=max_tokens)
        type(self).calls.pop()
        return answer


class _RejectedClient(_FakeClient):
    calls = []

    def complete(self, messages, *, max_tokens=None):
        type(self).calls.append(messages)
        raise AIProviderError("provider_request_rejected")


class _ChunkingClient:
    calls = []
    markers = ("FIRST_MARKER", "MIDDLE_A_MARKER", "MIDDLE_B_MARKER", "FINAL_MARKER")

    def __init__(self, config: ProviderConfig):
        self.config = config

    def complete(self, messages, *, max_tokens=None):
        type(self).calls.append({"messages": messages, "max_tokens": max_tokens})
        system = messages[0]["content"]
        user = messages[-1]["content"]
        if "contiguous source part" in system:
            covered = [marker for marker in self.markers if marker in user]
            return json.dumps(
                {"covered_markers": covered, "detail": "part analysis " * 300}
            )
        return json.dumps(
            {
                "quick": {"title": "Complete guide", "summary": "All parts covered", "key_points": []},
                "structure": {"overview": "Whole chapter", "nodes": [], "links": []},
                "deep": {"themes": [], "questions": [], "applications": []},
                "evidence": [],
                "annotations": [
                    {
                        "chapter_index": 0,
                        "kind": "claim",
                        "quote": "FINAL_MARKER",
                        "title": "The conclusion",
                        "body_markdown": "This remains anchored to the full source.",
                    }
                ],
            }
        )


class _EnvelopeClient:
    calls = []

    def __init__(self, config: ProviderConfig):
        self.config = config

    def complete(self, messages, *, max_tokens=None):
        type(self).calls.append({"messages": messages, "max_tokens": max_tokens})
        return "Bounded answer"


class _LearningLayerEnvelopeClient:
    calls = []

    def __init__(self, config: ProviderConfig):
        self.config = config

    def complete(self, messages, *, max_tokens=None):
        type(self).calls.append({"messages": messages, "max_tokens": max_tokens})
        return json.dumps(
            {
                "quick": {
                    "title": "Tiny guide",
                    "summary": "A safe summary.",
                    "key_points": ["One point"],
                },
                "teach": {
                    "explanation": "A plain explanation.",
                    "analogy": "A familiar analogy.",
                    "check_question": "Can you explain it back?",
                },
                "structure": {
                    "overview": "A tiny structure.",
                    "diagram_mermaid": "",
                    "nodes": [{"label": "Idea", "detail": "The central idea."}],
                    "links": [],
                },
                "deep": {
                    "themes": [{"title": "Theme", "analysis": "An analysis."}],
                    "questions": [{"question": "Why?", "why": "For reflection."}],
                    "applications": [{"context": "Practice", "advice": "Apply it."}],
                },
                "evidence": [
                    {
                        "chapter_index": 0,
                        "quote": "Source sentence.",
                        "reason": "It supports the summary.",
                    }
                ],
                "annotations": [],
                "paragraph_notes": [],
            }
        )


class _FailingGroundingClient:
    calls = []

    def __init__(self, config: ProviderConfig):
        self.config = config

    def complete(self, messages, *, max_tokens=None):
        type(self).calls.append({"messages": messages, "max_tokens": max_tokens})
        if len(type(self).calls) == 1:
            return json.dumps({
                "quick": {"title": "Guide", "summary": "Core complete", "key_points": []},
                "teach": {"explanation": "Plain", "analogy": "", "check_question": ""},
                "chapter_summary": {"overview": "", "beats": [], "key_elements": [], "closing": ""},
                "structure": {"overview": "", "diagram_mermaid": "", "nodes": [], "links": []},
                "deep": {"themes": [], "questions": [], "applications": []},
            })
        raise AIProviderError("provider_request_rejected")


class _BlockingClient:
    calls = []
    started = threading.Event()
    release = threading.Event()

    def __init__(self, config: ProviderConfig):
        self.config = config

    def complete(self, messages, *, max_tokens=None):
        type(self).calls.append({"messages": messages, "max_tokens": max_tokens})
        if len(type(self).calls) == 1:
            type(self).started.set()
            type(self).release.wait(timeout=5)
        return "Provider answer"


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
        await self.service.stop_worker()
        self.temporary.cleanup()

    async def _wait_for_job(self, job_id, owner_user_id=None):
        owner_user_id = owner_user_id or self.member.user_id
        for _ in range(100):
            job = self.store.get_ai_job(job_id, owner_user_id)
            if job["status"] in {"complete", "failed"}:
                return job
            await asyncio.sleep(0.01)
        self.fail("AI generation task did not finish")

    def _provider_calls(self, user_id):
        with self.store._connection() as connection:
            row = connection.execute(
                "SELECT COALESCE(SUM(provider_calls), 0) AS calls "
                "FROM ai_usage WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        return int(row["calls"])

    def _reading_tasks(self, user_id):
        with self.store._connection() as connection:
            row = connection.execute(
                "SELECT COALESCE(SUM(reading_tasks), 0) AS tasks "
                "FROM ai_usage WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        return int(row["tasks"])

    def _create_failed_reading_job(
        self,
        job_id="failed-job",
        *,
        cache_key="failed-cache-key",
        request_payload=None,
        profile="auto",
    ):
        template = template_for("chapter", "chapter")
        replay = request_payload or {
            "scope": "chapter",
            "book_id": self.book.book_id,
            "chapter_index": 0,
            "mode": "chapter",
            "language": "en",
            "reading_boundary": 0,
        }
        self.store.create_ai_job(
            job_id,
            self.member.user_id,
            cache_key,
            book_id=self.book.book_id,
            progress_total=1,
            request_payload=replay,
            profile=profile,
            template_id=template["id"],
            template_version=template["version"],
        )
        self.assertTrue(self.store.start_ai_job(job_id))
        self.assertTrue(
            self.store.finish_ai_job(job_id, error_code="provider_request_rejected")
        )
        return self.store.get_ai_job_for_retry(job_id)

    def _assert_dependency_free_call_fits(
        self, call, context_window=2048, safety_tokens=128
    ):
        self.assertIsInstance(call["max_tokens"], int)
        input_upper_bound = 4 + sum(
            8
            + len(message["role"].encode("utf-8"))
            + len(message["content"].encode("utf-8"))
            for message in call["messages"]
        )
        self.assertLessEqual(
            input_upper_bound + call["max_tokens"] + safety_tokens,
            context_window,
        )

    async def test_chapter_generation_is_cached_and_uses_untrusted_content_boundary(self):
        request = ReadingRequest(
            scope="chapter", book_id=self.book.book_id, chapter_index=0, language="en"
        )
        started = await self.service.submit(self.member, request)
        self.assertEqual(started["status"], "queued")
        completed = await self._wait_for_job(started["job"]["id"])
        self.assertEqual(completed["status"], "complete")
        self.assertIsNotNone(completed["result_id"])
        self.assertEqual(len(_FakeClient.calls), 2)
        for call in _FakeClient.calls:
            self.assertIn("<UNTRUSTED_EPUB_CONTENT>", call[1]["content"])
            self.assertIn("Source sentence.", call[1]["content"])
            self.assertNotIn("ignore()", call[1]["content"])

        cached = await self.service.submit(self.member, request)
        self.assertTrue(cached["cached"])
        self.assertEqual(cached["result"]["content"]["quick"]["summary"], "Useful overview")
        self.assertEqual(len(_FakeClient.calls), 2)

    async def test_admin_retry_recomputes_current_job_state(self):
        replay = {
            "scope": "chapter",
            "book_id": self.book.book_id,
            "chapter_index": 0,
            "mode": "chapter",
            "language": "en",
            "reading_boundary": 0,
            "private_marker": "PRIVATE_REPLAY_SENTINEL",
        }
        source = self._create_failed_reading_job(request_payload=replay)
        self.store.set_book_ai_profile(self.book.book_id, "technical")
        current_template = template_for("chapter", "chapter")

        retried = await self.service.retry_job(self.owner, source["id"])

        self.assertEqual(retried["status"], "queued")
        self.assertFalse(retried["cached"])
        self.assertFalse(retried["shared"])
        self.assertEqual(retried["job"]["owner_user_id"], self.member.user_id)
        self.assertEqual(retried["job"]["retried_by_user_id"], self.owner.user_id)
        self.assertEqual(retried["job"]["attempt_number"], 2)
        self.assertEqual(retried["job"]["profile"], "technical")
        self.assertEqual(retried["job"]["template_id"], current_template["id"])
        self.assertEqual(
            retried["job"]["template_version"], current_template["version"]
        )
        private_retry = self.store.get_ai_job_for_retry(retried["job"]["id"])
        self.assertNotEqual(private_retry["cache_key"], source["cache_key"])
        self.assertNotIn("request_json", retried["job"])
        self.assertEqual(set(retried), {"status", "cached", "shared", "job"})
        self.assertNotIn("PRIVATE_REPLAY_SENTINEL", json.dumps(retried))
        worker = self.service._worker_states[asyncio.get_running_loop()]
        self.assertTrue(worker.wake.is_set())

    async def test_admin_retry_uses_current_cache_without_provider_call(self):
        source = self._create_failed_reading_job()
        request = ReadingRequest(
            scope="chapter", book_id=self.book.book_id, chapter_index=0
        )
        material, _metadata, progress_total, _segments = (
            self.service._material_for_request(self.member, request)
        )
        profile = self.store.get_book_ai_profile(self.book.book_id)
        template = template_for(request.scope, request.mode)
        cache_key = self.service._cache_key(request, material, profile, template)
        settings = self.store._get_ai_provider_settings()
        cached = self.store.store_ai_reading_result(
            cache_key=cache_key,
            book_id=self.book.book_id,
            chapter_index=0,
            scope="chapter",
            mode="chapter",
            profile=profile,
            config_revision=settings["config_revision"],
            content={"quick": {"summary": "cached"}},
            created_by_user_id=self.member.user_id,
            template_id=template["id"],
            template_version=template["version"],
            language="en",
            reading_boundary=0,
        )

        retried = await self.service.retry_job(self.owner, source["id"])

        self.assertEqual(retried["status"], "complete")
        self.assertTrue(retried["cached"])
        self.assertFalse(retried["shared"])
        self.assertEqual(retried["job"]["result_id"], cached["id"])
        self.assertEqual(retried["job"]["progress_current"], progress_total)
        self.assertEqual(retried["job"]["progress_total"], progress_total)
        self.assertEqual(_FakeClient.calls, [])
        self.assertEqual(self._provider_calls(self.member.user_id), 0)
        self.assertEqual(self.service._worker_states, {})

    async def test_admin_retry_downgrades_cached_completion_after_config_race(self):
        source = self._create_failed_reading_job()
        request = ReadingRequest(
            scope="chapter", book_id=self.book.book_id, chapter_index=0
        )
        material, _metadata, _progress_total, _segments = (
            self.service._material_for_request(self.member, request)
        )
        profile = self.store.get_book_ai_profile(self.book.book_id)
        template = template_for(request.scope, request.mode)
        cache_key = self.service._cache_key(request, material, profile, template)
        settings = self.store._get_ai_provider_settings()
        cached = self.store.store_ai_reading_result(
            cache_key=cache_key,
            book_id=self.book.book_id,
            chapter_index=0,
            scope="chapter",
            mode="chapter",
            profile=profile,
            config_revision=settings["config_revision"],
            content={"quick": {"summary": "raced cache"}},
            created_by_user_id=self.member.user_id,
            template_id=template["id"],
            template_version=template["version"],
            language="en",
            reading_boundary=0,
        )
        create_retry = self.store.create_or_get_admin_retry_ai_job

        def change_config_then_create(**kwargs):
            self.store.set_ai_settings(
                enabled=True,
                base_url="https://provider.example/v1",
                api_key=None,
                model="raced-reader-model",
                timeout_seconds=30,
                max_concurrency=2,
                daily_limit=20,
            )
            return create_retry(**kwargs)

        with mock.patch.object(
            self.store,
            "create_or_get_admin_retry_ai_job",
            side_effect=change_config_then_create,
        ):
            retried = await self.service.retry_job(self.owner, source["id"])

        self.assertEqual(retried["status"], "queued")
        self.assertFalse(retried["cached"])
        self.assertIsNone(retried["job"]["result_id"])
        self.assertNotEqual(
            settings["config_revision"],
            self.store._get_ai_provider_settings()["config_revision"],
        )
        self.assertEqual(cached["cache_key"], cache_key)
        self.assertEqual(self._provider_calls(self.member.user_id), 0)

    async def test_admin_retry_refreshes_profile_snapshot_after_transaction_race(self):
        source = self._create_failed_reading_job()
        request = ReadingRequest(
            scope="chapter", book_id=self.book.book_id, chapter_index=0
        )
        material, _metadata, _progress_total, _segments = (
            self.service._material_for_request(self.member, request)
        )
        template = template_for(request.scope, request.mode)
        auto_cache_key = self.service._cache_key(
            request, material, "auto", template
        )
        settings = self.store._get_ai_provider_settings()
        cached = self.store.store_ai_reading_result(
            cache_key=auto_cache_key,
            book_id=self.book.book_id,
            chapter_index=0,
            scope="chapter",
            mode="chapter",
            profile="auto",
            config_revision=settings["config_revision"],
            content={"quick": {"summary": "old auto result"}},
            created_by_user_id=self.member.user_id,
            template_id=template["id"],
            template_version=template["version"],
            language="en",
            reading_boundary=0,
        )
        create_retry = self.store.create_or_get_admin_retry_ai_job
        raced = False

        def change_profile_then_create(**kwargs):
            nonlocal raced
            if not raced:
                raced = True
                self.store.set_book_ai_profile(
                    self.book.book_id, "technical"
                )
            return create_retry(**kwargs)

        with mock.patch.object(
            self.store,
            "create_or_get_admin_retry_ai_job",
            side_effect=change_profile_then_create,
        ):
            retried = await self.service.retry_job(self.owner, source["id"])

        private_retry = self.store.get_ai_job_for_retry(retried["job"]["id"])
        technical_cache_key = auto_cache_key.replace(":auto:", ":technical:", 1)
        self.assertEqual(retried["status"], "queued")
        self.assertFalse(retried["cached"])
        self.assertEqual(retried["job"]["profile"], "technical")
        self.assertEqual(private_retry["cache_key"], technical_cache_key)
        self.assertNotEqual(private_retry["result_id"], cached["id"])
        jobs, total = self.store.list_admin_ai_jobs(
            status=None, page=1, page_size=20
        )
        retry_rows = tuple(
            job for job in jobs if job["retried_from_job_id"] == source["id"]
        )
        self.assertEqual(total, 2)
        self.assertEqual(len(retry_rows), 1)
        self.assertEqual(self._provider_calls(self.member.user_id), 0)

    async def test_admin_retry_reports_conflict_after_bounded_profile_churn(self):
        source = self._create_failed_reading_job()
        create_retry = self.store.create_or_get_admin_retry_ai_job
        selections = iter(("technical", "fiction", "general", "auto"))
        attempts = 0

        def change_profile_then_create(**kwargs):
            nonlocal attempts
            attempts += 1
            self.store.set_book_ai_profile(
                self.book.book_id, next(selections)
            )
            return create_retry(**kwargs)

        with mock.patch.object(
            self.store,
            "create_or_get_admin_retry_ai_job",
            side_effect=change_profile_then_create,
        ):
            with self.assertRaises(AIReadingError) as caught:
                await asyncio.wait_for(
                    self.service.retry_job(self.owner, source["id"]),
                    timeout=1,
                )

        self.assertEqual(caught.exception.code, "ai_job_retry_conflict")
        self.assertEqual(attempts, 3)
        _jobs, total = self.store.list_admin_ai_jobs(
            status=None, page=1, page_size=20
        )
        self.assertEqual(total, 1)
        self.assertEqual(self.service._worker_states, {})

    async def test_admin_retry_rechecks_disabled_owner_inside_retry_transaction(self):
        source = self._create_failed_reading_job()
        create_retry = self.store.create_or_get_admin_retry_ai_job

        def disable_owner_then_create(**kwargs):
            self.store.set_user_enabled(self.member.user_id, False)
            return create_retry(**kwargs)

        with mock.patch.object(
            self.store,
            "create_or_get_admin_retry_ai_job",
            side_effect=disable_owner_then_create,
        ):
            with self.assertRaises(AIReadingError) as caught:
                await self.service.retry_job(self.owner, source["id"])

        self.assertEqual(caught.exception.code, "ai_not_authorized")
        _jobs, total = self.store.list_admin_ai_jobs(
            status=None, page=1, page_size=20
        )
        self.assertEqual(total, 1)

    async def test_admin_retry_rechecks_retrier_role_inside_retry_transaction(self):
        source = self._create_failed_reading_job()
        self.store.create_user("backup-admin", "hash", role="admin")
        create_retry = self.store.create_or_get_admin_retry_ai_job

        def demote_retrier_then_create(**kwargs):
            self.store.update_user(self.owner.user_id, role="member")
            return create_retry(**kwargs)

        with mock.patch.object(
            self.store,
            "create_or_get_admin_retry_ai_job",
            side_effect=demote_retrier_then_create,
        ):
            with self.assertRaises(AIReadingError) as caught:
                await self.service.retry_job(self.owner, source["id"])

        self.assertEqual(caught.exception.code, "ai_not_authorized")
        _jobs, total = self.store.list_admin_ai_jobs(
            status=None, page=1, page_size=20
        )
        self.assertEqual(total, 1)

    async def test_admin_retry_rechecks_revoked_ai_access_inside_retry_transaction(self):
        source = self._create_failed_reading_job()
        create_retry = self.store.create_or_get_admin_retry_ai_job

        def revoke_ai_then_create(**kwargs):
            self.store.set_ai_user_access(
                self.member.user_id, enabled=False, daily_limit=10
            )
            return create_retry(**kwargs)

        with mock.patch.object(
            self.store,
            "create_or_get_admin_retry_ai_job",
            side_effect=revoke_ai_then_create,
        ):
            with self.assertRaises(AIReadingError) as caught:
                await self.service.retry_job(self.owner, source["id"])

        self.assertEqual(caught.exception.code, "ai_not_authorized")
        _jobs, total = self.store.list_admin_ai_jobs(
            status=None, page=1, page_size=20
        )
        self.assertEqual(total, 1)

    async def test_admin_retry_rechecks_revoked_book_inside_retry_transaction(self):
        self.store.set_book_visibility(self.book.book_id, "restricted")
        self.store.grant_book_access(self.book.book_id, self.member.user_id)
        source = self._create_failed_reading_job()
        create_retry = self.store.create_or_get_admin_retry_ai_job

        def revoke_book_then_create(**kwargs):
            self.store.revoke_book_access(
                self.book.book_id, self.member.user_id
            )
            return create_retry(**kwargs)

        with mock.patch.object(
            self.store,
            "create_or_get_admin_retry_ai_job",
            side_effect=revoke_book_then_create,
        ):
            with self.assertRaises(AIReadingError) as caught:
                await self.service.retry_job(self.owner, source["id"])

        self.assertEqual(caught.exception.code, "ai_not_authorized")
        _jobs, total = self.store.list_admin_ai_jobs(
            status=None, page=1, page_size=20
        )
        self.assertEqual(total, 1)

    async def test_admin_retry_rejects_disabled_owner_or_revoked_book(self):
        source = self._create_failed_reading_job()
        self.store.set_user_enabled(self.member.user_id, False)

        with self.assertRaises(AIReadingError) as disabled:
            await self.service.retry_job(self.owner, source["id"])
        self.assertEqual(disabled.exception.code, "ai_not_authorized")

        self.store.set_user_enabled(self.member.user_id, True)
        self.store.set_book_visibility(self.book.book_id, "restricted")
        self.store.grant_book_access(self.book.book_id, self.member.user_id)
        self.store.revoke_book_access(self.book.book_id, self.member.user_id)

        with self.assertRaises(AIReadingError) as revoked:
            await self.service.retry_job(self.owner, source["id"])
        self.assertEqual(revoked.exception.code, "ai_not_authorized")

    async def test_admin_retry_does_not_reuse_a_result_from_an_older_config_revision(self):
        source = self._create_failed_reading_job()
        request = ReadingRequest(
            scope="chapter", book_id=self.book.book_id, chapter_index=0
        )
        material, _metadata, _progress_total, _segments = (
            self.service._material_for_request(self.member, request)
        )
        profile = self.store.get_book_ai_profile(self.book.book_id)
        template = template_for(request.scope, request.mode)
        cache_key = self.service._cache_key(request, material, profile, template)
        old_revision = self.store._get_ai_provider_settings()["config_revision"]
        cached = self.store.store_ai_reading_result(
            cache_key=cache_key,
            book_id=self.book.book_id,
            chapter_index=0,
            scope="chapter",
            mode="chapter",
            profile=profile,
            config_revision=old_revision,
            content={"quick": {"summary": "stale config"}},
            created_by_user_id=self.member.user_id,
            template_id=template["id"],
            template_version=template["version"],
            language="en",
            reading_boundary=0,
        )
        self.store.set_ai_settings(
            enabled=True,
            base_url="https://provider.example/v1",
            api_key=None,
            model="new-reader-model",
            timeout_seconds=30,
            max_concurrency=2,
            daily_limit=20,
        )

        retried = await self.service.retry_job(self.owner, source["id"])

        self.assertEqual(retried["status"], "queued")
        self.assertFalse(retried["cached"])
        private_retry = self.store.get_ai_job_for_retry(retried["job"]["id"])
        self.assertEqual(private_retry["cache_key"], cached["cache_key"])
        self.assertIsNone(private_retry["result_id"])
        self.assertEqual(self._provider_calls(self.member.user_id), 0)

    async def test_admin_retry_joins_current_active_job_without_starting_a_worker(self):
        source = self._create_failed_reading_job()
        request = ReadingRequest(
            scope="chapter", book_id=self.book.book_id, chapter_index=0
        )
        material, _metadata, progress_total, _segments = (
            self.service._material_for_request(self.member, request)
        )
        profile = self.store.get_book_ai_profile(self.book.book_id)
        template = template_for(request.scope, request.mode)
        cache_key = self.service._cache_key(request, material, profile, template)
        self.store.create_ai_job(
            "active-current-job",
            self.member.user_id,
            cache_key,
            book_id=self.book.book_id,
            progress_total=progress_total,
            request_payload={
                "scope": "chapter",
                "book_id": self.book.book_id,
                "chapter_index": 0,
                "mode": "chapter",
                "language": "en",
                "reading_boundary": 0,
            },
            profile=profile,
            template_id=template["id"],
            template_version=template["version"],
        )

        retried = await self.service.retry_job(self.owner, source["id"])

        self.assertEqual(retried["status"], "queued")
        self.assertTrue(retried["shared"])
        self.assertFalse(retried["cached"])
        self.assertEqual(retried["job"]["id"], "active-current-job")
        self.assertNotIn("request_json", retried["job"])
        self.assertEqual(self.service._worker_states, {})

    async def test_admin_retry_rejects_non_admin_invalid_replay_and_disabled_ai(self):
        source = self._create_failed_reading_job()

        with self.assertRaises(AIReadingError) as non_admin:
            await self.service.retry_job(self.member, source["id"])
        self.assertEqual(non_admin.exception.code, "ai_not_authorized")

        with self.store._connection() as connection:
            connection.execute(
                "UPDATE ai_reading_jobs SET request_json = ? WHERE id = ?",
                ('{"scope":"chapter","chapter_index":true}', source["id"]),
            )
        with self.assertRaises(AIReadingError) as malformed:
            await self.service.retry_job(self.owner, source["id"])
        self.assertEqual(malformed.exception.code, "ai_job_not_retryable")

        with self.store._connection() as connection:
            connection.execute(
                "UPDATE ai_reading_jobs SET request_json = ? WHERE id = ?",
                (
                    json.dumps(
                        {
                            "scope": "chapter",
                            "book_id": self.book.book_id,
                            "chapter_index": 0,
                            "mode": "chapter",
                            "language": "en",
                            "reading_boundary": 0,
                        }
                    ),
                    source["id"],
                ),
            )
        self.store.set_ai_settings(
            enabled=False,
            base_url="https://provider.example/v1",
            api_key=None,
            model="reader-model",
            timeout_seconds=30,
            max_concurrency=2,
            daily_limit=20,
        )
        with self.assertRaises(AIReadingError) as disabled:
            await self.service.retry_job(self.owner, source["id"])
        self.assertEqual(disabled.exception.code, "ai_disabled")

    async def test_admin_retry_rejects_missing_nonterminal_and_ai_revoked_sources(self):
        with self.assertRaises(AIReadingError) as missing:
            await self.service.retry_job(self.owner, "missing-job")
        self.assertEqual(missing.exception.code, "ai_job_not_found")

        self._create_failed_reading_job("queued-source")
        with self.store._connection() as connection:
            connection.execute(
                "UPDATE ai_reading_jobs SET status = 'queued', error_code = NULL "
                "WHERE id = 'queued-source'"
            )
        with self.assertRaises(AIReadingError) as nonterminal:
            await self.service.retry_job(self.owner, "queued-source")
        self.assertEqual(nonterminal.exception.code, "ai_job_not_retryable")

        with self.store._connection() as connection:
            connection.execute(
                "UPDATE ai_reading_jobs SET status = 'failed', "
                "error_code = 'provider_request_rejected' WHERE id = 'queued-source'"
            )
        self.store.set_ai_user_access(
            self.member.user_id, enabled=False, daily_limit=10
        )
        with self.assertRaises(AIReadingError) as ai_revoked:
            await self.service.retry_job(self.owner, "queued-source")
        self.assertEqual(ai_revoked.exception.code, "ai_not_authorized")

    async def test_submit_jobs_hide_replay_while_the_worker_can_still_load_it(self):
        request = ReadingRequest(
            scope="chapter", book_id=self.book.book_id, chapter_index=0
        )

        created = await self.service.submit(self.member, request)
        joined = await self.service.submit(self.member, request)

        self.assertNotIn("request_json", created["job"])
        self.assertNotIn("request_json", joined["job"])
        self.assertTrue(joined["shared"])
        private_job = self.store.get_ai_job_for_retry(created["job"]["id"])
        self.assertEqual(
            json.loads(private_job["request_json"]),
            {
                "scope": "chapter",
                "book_id": self.book.book_id,
                "chapter_index": 0,
                "mode": "chapter",
                "language": "en",
                "force": False,
                "reading_boundary": 0,
            },
        )
        completed = await self._wait_for_job(created["job"]["id"])
        self.assertEqual(completed["status"], "complete")

    async def test_submit_and_retry_share_strict_reading_request_validation(self):
        invalid_request = ReadingRequest(
            scope="chapter",
            book_id=self.book.book_id,
            chapter_index=True,
            mode="chapter",
        )
        with self.assertRaises(AIReadingError) as submitted:
            await self.service.submit(self.member, invalid_request)
        self.assertEqual(submitted.exception.code, "invalid_ai_reading_request")

        source = self._create_failed_reading_job()
        with self.store._connection() as connection:
            connection.execute(
                "UPDATE ai_reading_jobs SET request_json = ? WHERE id = ?",
                (
                    json.dumps(
                        {
                            "scope": "chapter",
                            "book_id": self.book.book_id,
                            "chapter_index": True,
                            "mode": "chapter",
                            "language": "en",
                            "reading_boundary": 0,
                        }
                    ),
                    source["id"],
                ),
            )
        with self.assertRaises(AIReadingError) as replayed:
            await self.service.retry_job(self.owner, source["id"])
        self.assertEqual(replayed.exception.code, "ai_job_not_retryable")

    async def test_submit_and_retry_reject_unhashable_reading_fields_stably(self):
        source = self._create_failed_reading_job()
        base = {
            "scope": "book",
            "book_id": self.book.book_id,
            "chapter_index": None,
            "mode": "full_review",
            "language": "en",
            "reading_boundary": None,
        }
        invalid_fields = (
            ("scope", []),
            ("language", {}),
            ("mode", []),
        )

        for field, invalid_value in invalid_fields:
            with self.subTest(path="submit", field=field):
                values = dict(base)
                values[field] = invalid_value
                with self.assertRaises(AIReadingError) as submitted:
                    await self.service.submit(
                        self.member,
                        ReadingRequest(**values),
                    )
                self.assertEqual(
                    submitted.exception.code, "invalid_ai_reading_request"
                )

            with self.subTest(path="retry", field=field):
                replay = dict(base)
                replay[field] = invalid_value
                with self.store._connection() as connection:
                    connection.execute(
                        "UPDATE ai_reading_jobs SET request_json = ? WHERE id = ?",
                        (json.dumps(replay), source["id"]),
                    )
                with self.assertRaises(AIReadingError) as retried:
                    await self.service.retry_job(self.owner, source["id"])
                self.assertEqual(
                    retried.exception.code, "ai_job_not_retryable"
                )

    async def test_tiny_chapter_generation_preserves_the_2048_context_minimum(self):
        self.store.set_ai_settings(
            enabled=True,
            base_url="https://provider.example/v1",
            api_key="secret",
            model="reader-model",
            timeout_seconds=30,
            model_context_window=2048,
            max_concurrency=2,
            daily_limit=100,
        )
        self.store.set_ai_user_access(
            self.member.user_id, enabled=True, daily_limit=100
        )
        _LearningLayerEnvelopeClient.calls = []
        service = AIReadingService(
            self.store, self.root / "public", _LearningLayerEnvelopeClient
        )

        try:
            started = await service.submit(
                self.member,
                ReadingRequest(
                    scope="chapter",
                    book_id=self.book.book_id,
                    chapter_index=0,
                ),
            )
            completed = await self._wait_for_job(started["job"]["id"])
        finally:
            await service.stop_worker()

        self.assertEqual(completed["status"], "complete")
        self.assertEqual(len(_LearningLayerEnvelopeClient.calls), 2)
        for call in _LearningLayerEnvelopeClient.calls:
            self._assert_dependency_free_call_fits(call)
            system_prompt = call["messages"][0]["content"].lower()
            self.assertIn("untrusted", system_prompt)
            self.assertIn("never", system_prompt)
            self.assertIn("<UNTRUSTED_EPUB_CONTENT>", call["messages"][-1]["content"])
        self.assertNotIn(
            "annotations", _LearningLayerEnvelopeClient.calls[0]["messages"][0]["content"]
        )
        self.assertIn(
            "Normalized core synopsis",
            _LearningLayerEnvelopeClient.calls[1]["messages"][-1]["content"],
        )

        result = self.store.get_ai_reading_result(completed["result_id"])
        content = result["content"]
        self.assertEqual(
            set(content),
            {
                "quick", "teach", "structure", "deep", "evidence", "annotations",
                "paragraph_notes", "chapter_summary",
            },
        )
        self.assertEqual(
            set(content["teach"]), {"explanation", "analogy", "check_question"}
        )
        self.assertEqual(
            set(content["chapter_summary"]),
            {"overview", "beats", "key_elements", "closing"},
        )
        self.assertEqual(set(content["quick"]), {"title", "summary", "key_points"})
        self.assertEqual(
            set(content["structure"]),
            {"overview", "diagram_mermaid", "nodes", "links"},
        )
        self.assertEqual(
            set(content["deep"]), {"themes", "questions", "applications"}
        )
        self.assertEqual(
            set(content["deep"]["themes"][0]), {"title", "analysis"}
        )
        self.assertEqual(
            set(content["deep"]["questions"][0]), {"question", "why"}
        )
        self.assertEqual(
            set(content["deep"]["applications"][0]), {"context", "advice"}
        )

    async def test_server_content_cache_is_used_without_generated_reader_html(self):
        legacy_path = self.root / "public" / "book" / self.book.book_id / "chapter_0.html"
        legacy_path.unlink()
        content_dir = legacy_path.parent / "content"
        content_dir.mkdir()
        (content_dir / "chapter_0.json").write_text(
            json.dumps(
                {
                    "index": 0,
                    "title": "Chapter",
                    "content": "<article><p>Cached source sentence.</p></article>",
                    "style_links": "",
                }
            ),
            encoding="utf-8",
        )

        request = ReadingRequest(
            scope="chapter", book_id=self.book.book_id, chapter_index=0, language="en"
        )
        started = await self.service.submit(self.member, request)
        completed = await self._wait_for_job(started["job"]["id"])

        self.assertEqual(completed["status"], "complete")
        self.assertEqual(len(_FakeClient.calls), 2)
        self.assertTrue(all(
            "Cached source sentence." in call[-1]["content"]
            for call in _FakeClient.calls
        ))

    async def test_failed_grounding_does_not_persist_a_partial_core_result(self):
        _FailingGroundingClient.calls = []
        service = AIReadingService(
            self.store, self.root / "public", _FailingGroundingClient
        )

        try:
            started = await service.submit(
                self.member,
                ReadingRequest(
                    scope="chapter", book_id=self.book.book_id, chapter_index=0
                ),
            )
            completed = await self._wait_for_job(started["job"]["id"])
        finally:
            await service.stop_worker()

        self.assertEqual(completed["status"], "failed")
        self.assertEqual(completed["generation_stage"], "grounding_source")
        self.assertEqual(len(_FailingGroundingClient.calls), 2)
        with self.store._connection() as connection:
            stored = connection.execute(
                "SELECT COUNT(*) FROM ai_reading_results WHERE cache_key = ?",
                (completed["cache_key"],),
            ).fetchone()[0]
        self.assertEqual(stored, 0)

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

    async def test_followup_prompt_fits_context_with_large_multilingual_question(self):
        started = await self.service.submit(
            self.member,
            ReadingRequest(scope="chapter", book_id=self.book.book_id, chapter_index=0),
        )
        await self._wait_for_job(started["job"]["id"])
        cached = await self.service.submit(
            self.member,
            ReadingRequest(scope="chapter", book_id=self.book.book_id, chapter_index=0),
        )
        self.store.set_ai_settings(
            enabled=True,
            base_url="https://provider.example/v1",
            api_key="secret",
            model="reader-model",
            timeout_seconds=30,
            model_context_window=2048,
            max_concurrency=2,
            daily_limit=100,
        )
        self.store.set_ai_user_access(
            self.member.user_id, enabled=True, daily_limit=100
        )
        _EnvelopeClient.calls = []
        service = AIReadingService(
            self.store, self.root / "public", _EnvelopeClient
        )

        try:
            followup = await service.follow_up(
                self.member,
                cached["result"]["id"],
                "QUESTION_MARKER " + ("😀问题" * 600),
                "en",
            )
            for _ in range(100):
                entry = self.store.get_ai_followup(
                    followup["id"], self.member.user_id
                )
                if entry and entry["status"] in {"complete", "failed"}:
                    break
                await asyncio.sleep(0.01)
        finally:
            await service.stop_worker()

        self.assertEqual(entry["status"], "complete")
        self.assertEqual(len(_EnvelopeClient.calls), 1)
        self.assertIn(
            "QUESTION_MARKER", _EnvelopeClient.calls[0]["messages"][-1]["content"]
        )
        self._assert_dependency_free_call_fits(_EnvelopeClient.calls[0])

    async def test_book_chat_can_answer_from_a_chapter_without_a_shared_layer(self):
        turn = await self.service.ask_book(
            self.member, book_id=self.book.book_id, chapter_index=0,
            question="What is the key claim?", language="en", context_mode="chapter_source",
        )
        for _ in range(100):
            turns = self.store.list_ai_book_chat_turns(self.book.book_id, self.member.user_id)
            if turns and turns[0]["status"] in {"complete", "failed"}:
                break
            await asyncio.sleep(0.01)
        self.assertEqual(turns[0]["id"], turn["id"])
        self.assertEqual(turns[0]["chapter_index"], 0)
        self.assertEqual(turns[0]["status"], "complete")
        self.assertEqual(self.store.list_ai_book_chat_turns(self.book.book_id, self.owner.user_id), ())

    async def test_book_chat_prompt_fits_context_with_large_source_and_question(self):
        self.store.set_ai_settings(
            enabled=True,
            base_url="https://provider.example/v1",
            api_key="secret",
            model="reader-model",
            timeout_seconds=30,
            model_context_window=2048,
            max_concurrency=2,
            daily_limit=100,
        )
        self.store.set_ai_user_access(
            self.member.user_id, enabled=True, daily_limit=100
        )
        chapter = self.root / "public" / "book" / self.book.book_id / "chapter_0.html"
        chapter.write_text(
            "<article><p>SOURCE_MARKER " + ("😀正文" * 2000) + "</p></article>",
            encoding="utf-8",
        )
        _EnvelopeClient.calls = []
        service = AIReadingService(
            self.store, self.root / "public", _EnvelopeClient
        )

        try:
            turn = await service.ask_book(
                self.member,
                book_id=self.book.book_id,
                chapter_index=0,
                question="QUESTION_MARKER " + ("🤔提问" * 600),
                language="en",
                context_mode="chapter_source",
            )
            for _ in range(100):
                entry = self.store.get_ai_book_chat_turn(
                    turn["id"], self.member.user_id
                )
                if entry and entry["status"] in {"complete", "failed"}:
                    break
                await asyncio.sleep(0.01)
        finally:
            await service.stop_worker()

        self.assertEqual(entry["status"], "complete")
        self.assertEqual(len(_EnvelopeClient.calls), 1)
        prompt = _EnvelopeClient.calls[0]["messages"][-1]["content"]
        self.assertIn("SOURCE_MARKER", prompt)
        self.assertIn("QUESTION_MARKER", prompt)
        self._assert_dependency_free_call_fits(_EnvelopeClient.calls[0])

    async def test_book_chat_sends_this_readers_prior_book_conversation_with_exact_chapter(self):
        first = await self.service.ask_book(
            self.member, book_id=self.book.book_id, chapter_index=0,
            question="What is the key claim?", language="en", context_mode="chapter_source",
        )
        for _ in range(100):
            first_turn = self.store.get_ai_book_chat_turn(first["id"], self.member.user_id)
            if first_turn and first_turn["status"] in {"complete", "failed"}:
                break
            await asyncio.sleep(0.01)
        self.assertEqual(first_turn["status"], "complete")

        second = await self.service.ask_book(
            self.member, book_id=self.book.book_id, chapter_index=0,
            question="How does that evidence support it?", language="en", context_mode="chapter_source",
        )
        for _ in range(100):
            second_turn = self.store.get_ai_book_chat_turn(second["id"], self.member.user_id)
            if second_turn and second_turn["status"] in {"complete", "failed"}:
                break
            await asyncio.sleep(0.01)
        self.assertEqual(second_turn["status"], "complete")
        prompt = _FakeClient.calls[-1][1]["content"]
        self.assertIn("Exact current chapter number: 0", prompt)
        self.assertIn("Private conversation history for this reader in this book", prompt)
        self.assertIn("What is the key claim?", prompt)
        self.assertIn('"chapter_number": 0', prompt)

    async def test_book_chat_preserves_the_stored_chapter_index(self):
        record = self.service._chat_turn_record(
            {"book_context": 0, "chapter_index": 7, "question": "Q", "answer": "A"},
            question_limit=100,
            answer_limit=100,
        )

        self.assertEqual(record["chapter_number"], 7)
        self.assertEqual(record["scope"], "chapter 7")

    async def test_book_overview_chat_uses_compressed_shared_layers_and_private_history(self):
        request = ReadingRequest(scope="chapter", book_id=self.book.book_id, chapter_index=0)
        started = await self.service.submit(self.member, request)
        await self._wait_for_job(started["job"]["id"])
        prior = await self.service.ask_book(
            self.member, book_id=self.book.book_id, chapter_index=0,
            question="What should I retain?", language="en", context_mode="shared_layer",
        )
        for _ in range(100):
            current = self.store.get_ai_book_chat_turn(prior["id"], self.member.user_id)
            if current and current["status"] in {"complete", "failed"}:
                break
            await asyncio.sleep(0.01)

        whole_book = await self.service.ask_book(
            self.member, book_id=self.book.book_id, chapter_index=None,
            question="What connects this book?", language="en", context_mode="book_overview",
        )
        for _ in range(100):
            current = self.store.get_ai_book_chat_turn(whole_book["id"], self.member.user_id)
            if current and current["status"] in {"complete", "failed"}:
                break
            await asyncio.sleep(0.01)
        self.assertEqual(current["status"], "complete")
        self.assertEqual(current["book_context"], 1)
        prompt = _FakeClient.calls[-1][1]["content"]
        self.assertIn("Conversation scope: the whole book", prompt)
        self.assertIn("Compressed shared reading layers", prompt)
        self.assertIn("What should I retain?", prompt)

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

    async def test_force_chapter_submission_creates_and_charges_a_distinct_active_job(self):
        _BlockingClient.calls = []
        _BlockingClient.started = threading.Event()
        _BlockingClient.release = threading.Event()
        normal_service = AIReadingService(
            self.store, self.root / "public", _BlockingClient
        )
        try:
            normal = await normal_service.submit(
                self.member,
                ReadingRequest(
                    scope="chapter", book_id=self.book.book_id, chapter_index=0
                ),
            )
            for _ in range(100):
                if _BlockingClient.started.is_set():
                    break
                await asyncio.sleep(0.01)
            self.assertTrue(_BlockingClient.started.is_set())

            forced = await self.service.submit(
                self.member,
                ReadingRequest(
                    scope="chapter", book_id=self.book.book_id, chapter_index=0,
                    force=True,
                ),
            )

            self.assertFalse(forced["shared"])
            self.assertNotEqual(forced["job"]["id"], normal["job"]["id"])
            _BlockingClient.release.set()
            self.assertEqual(
                (await self._wait_for_job(normal["job"]["id"]))["status"], "complete"
            )
            self.assertEqual(
                (await self._wait_for_job(forced["job"]["id"]))["status"], "complete"
            )
            self.assertEqual(self._reading_tasks(self.member.user_id), 2)
        finally:
            _BlockingClient.release.set()
            await normal_service.stop_worker()

    async def test_background_worker_claims_a_durable_sqlite_job(self):
        request = ReadingRequest(scope="chapter", book_id=self.book.book_id, chapter_index=0)
        material, _metadata, progress_total, _segments = self.service._material_for_request(self.member, request)
        template = template_for(request.scope, request.mode)
        cache_key = self.service._cache_key(
            request, material, self.store.get_book_ai_profile(self.book.book_id), template
        )
        self.store.create_ai_job(
            "durable-worker-job", self.member.user_id, cache_key,
            book_id=self.book.book_id, progress_total=progress_total,
            request_payload={
                "scope": "chapter", "book_id": self.book.book_id,
                "chapter_index": 0, "mode": "chapter", "language": "en",
                "reading_boundary": 0,
            },
            profile="auto", template_id=template["id"], template_version=template["version"],
        )

        await self.service.start_worker()
        self.service.wake_worker()
        completed = await self._wait_for_job("durable-worker-job")

        self.assertEqual(completed["status"], "complete")
        self.assertIsNotNone(completed["result_id"])

    async def test_claimed_chapter_job_uses_a_winning_cache_without_reserving_a_task(self):
        request = ReadingRequest(
            scope="chapter", book_id=self.book.book_id, chapter_index=0
        )
        material, _metadata, progress_total, _segments = self.service._material_for_request(
            self.member, request
        )
        template = template_for(request.scope, request.mode)
        cache_key = self.service._cache_key(request, material, "auto", template)
        self.store.create_ai_job(
            "claimed-cached-job", self.member.user_id, cache_key,
            book_id=self.book.book_id, progress_total=progress_total,
            request_payload={
                "scope": "chapter", "book_id": self.book.book_id,
                "chapter_index": 0, "mode": "chapter", "language": "en",
                "force": False, "reading_boundary": 0,
            },
            profile="auto", template_id=template["id"], template_version=template["version"],
        )
        claimed = self.store.claim_next_ai_reading_job()
        settings = self.store._get_ai_provider_settings()
        cached = self.store.store_ai_reading_result(
            cache_key=cache_key, book_id=self.book.book_id, chapter_index=0,
            scope="chapter", mode="chapter", profile="auto",
            config_revision=settings["config_revision"],
            content={"quick": {"summary": "winning cache"}},
            created_by_user_id=self.member.user_id, template_id=template["id"],
            template_version=template["version"], language="en", reading_boundary=0,
        )

        await self.service._run_queued_job(claimed)

        completed = self.store.get_ai_job("claimed-cached-job", self.member.user_id)
        self.assertEqual(completed["status"], "complete")
        self.assertEqual(completed["result_id"], cached["id"])
        self.assertEqual(_FakeClient.calls, [])
        self.assertEqual(self._reading_tasks(self.member.user_id), 0)

    async def test_durable_job_uses_the_cache_key_for_material_read_by_worker(self):
        """A queued job must not publish updated source under its old digest."""
        request = ReadingRequest(scope="chapter", book_id=self.book.book_id, chapter_index=0)
        material, _metadata, progress_total, _segments = self.service._material_for_request(
            self.member, request
        )
        template = template_for(request.scope, request.mode)
        stale_cache_key = self.service._cache_key(
            request, material, self.store.get_book_ai_profile(self.book.book_id), template
        )
        self.store.create_ai_job(
            "changed-material-worker-job", self.member.user_id, stale_cache_key,
            book_id=self.book.book_id, progress_total=progress_total,
            request_payload={
                "scope": "chapter", "book_id": self.book.book_id,
                "chapter_index": 0, "mode": "chapter", "language": "en",
                "reading_boundary": 0,
            },
            profile="auto", template_id=template["id"], template_version=template["version"],
        )
        chapter = self.root / "public" / "book" / self.book.book_id / "chapter_0.html"
        chapter.write_text(
            "<article><p>Updated Source sentence.</p></article>", encoding="utf-8"
        )
        current_material, _metadata, _total, _segments = self.service._material_for_request(
            self.member, request
        )
        current_cache_key = self.service._cache_key(
            request, current_material, "auto", template
        )
        self.assertNotEqual(current_cache_key, stale_cache_key)

        await self.service.start_worker()
        self.service.wake_worker()
        completed = await self._wait_for_job("changed-material-worker-job")

        result = self.store.get_ai_reading_result(completed["result_id"])
        self.assertEqual(result["cache_key"], current_cache_key)
        self.assertIsNone(self.store.get_current_ai_reading_result(stale_cache_key))
        self.assertEqual(
            self.store.get_current_ai_reading_result(current_cache_key)["id"], result["id"]
        )
        self.assertIn("Updated Source sentence.", _FakeClient.calls[-1][1]["content"])

    async def test_durable_force_job_regenerates_after_cache_and_config_change(self):
        request = ReadingRequest(scope="chapter", book_id=self.book.book_id, chapter_index=0)
        material, _metadata, progress_total, _segments = self.service._material_for_request(
            self.member, request
        )
        template = template_for(request.scope, request.mode)
        cache_key = self.service._cache_key(request, material, "auto", template)
        prior_config_revision = self.store.get_ai_settings()["config_revision"]
        prior = self.store.store_ai_reading_result(
            cache_key=cache_key, book_id=self.book.book_id, chapter_index=0,
            scope="chapter", mode="chapter", profile="auto", config_revision=prior_config_revision,
            content={"quick": {"summary": "old"}}, created_by_user_id=self.member.user_id,
            template_id=template["id"], template_version=template["version"], language="en",
        )
        self.store.create_ai_job(
            "forced-config-change-job", self.member.user_id, cache_key,
            book_id=self.book.book_id, progress_total=progress_total,
            request_payload={
                "scope": "chapter", "book_id": self.book.book_id,
                "chapter_index": 0, "mode": "chapter", "language": "en",
                "reading_boundary": 0,
            },
            profile="auto", template_id=template["id"], template_version=template["version"],
        )
        self.store.set_ai_settings(
            enabled=True, base_url="https://provider.example/v1", api_key="secret",
            model="reader-model-v2", timeout_seconds=30, max_concurrency=2,
            daily_limit=20,
        )
        current_config_revision = self.store.get_ai_settings()["config_revision"]
        self.assertNotEqual(current_config_revision, prior_config_revision)
        _FakeClient.calls = []

        await self.service.start_worker()
        self.service.wake_worker()
        completed = await self._wait_for_job("forced-config-change-job")

        result = self.store.get_ai_reading_result(completed["result_id"])
        self.assertNotEqual(result["id"], prior["id"])
        self.assertEqual(result["config_revision"], current_config_revision)
        self.assertEqual(len(_FakeClient.calls), 2)

    async def test_rekeyed_running_job_joins_later_submission_for_changed_material(self):
        request = ReadingRequest(scope="chapter", book_id=self.book.book_id, chapter_index=0)
        material, _metadata, progress_total, _segments = self.service._material_for_request(
            self.member, request
        )
        template = template_for(request.scope, request.mode)
        stale_cache_key = self.service._cache_key(request, material, "auto", template)
        self.store.create_ai_job(
            "rekeyed-running-job", self.member.user_id, stale_cache_key,
            book_id=self.book.book_id, progress_total=progress_total,
            request_payload={
                "scope": "chapter", "book_id": self.book.book_id,
                "chapter_index": 0, "mode": "chapter", "language": "en",
                "reading_boundary": 0,
            },
            profile="auto", template_id=template["id"], template_version=template["version"],
        )
        claimed = self.store.claim_next_ai_reading_job()
        self.assertEqual(claimed["id"], "rekeyed-running-job")
        chapter = self.root / "public" / "book" / self.book.book_id / "chapter_0.html"
        chapter.write_text(
            "<article><p>Updated Source sentence.</p></article>", encoding="utf-8"
        )
        current_material, _metadata, _total, _segments = self.service._material_for_request(
            self.member, request
        )
        current_cache_key = self.service._cache_key(request, current_material, "auto", template)
        self.assertNotEqual(current_cache_key, stale_cache_key)
        _BlockingClient.calls = []
        _BlockingClient.started = threading.Event()
        _BlockingClient.release = threading.Event()
        service = AIReadingService(self.store, self.root / "public", _BlockingClient)
        running = asyncio.create_task(service._run_queued_job(claimed))
        try:
            for _ in range(100):
                if _BlockingClient.started.is_set():
                    break
                await asyncio.sleep(0.01)
            self.assertTrue(_BlockingClient.started.is_set())

            joined = await service.submit(self.member, request)
            self.assertTrue(joined["shared"])
            self.assertEqual(joined["job"]["id"], "rekeyed-running-job")
            self.assertEqual(
                self.store.get_ai_job("rekeyed-running-job")["cache_key"], current_cache_key
            )
            self.assertEqual(len(_BlockingClient.calls), 1)
        finally:
            _BlockingClient.release.set()
            await running
            await service.stop_worker()

        completed = self.store.get_ai_job("rekeyed-running-job")
        result = self.store.get_ai_reading_result(completed["result_id"])
        self.assertEqual(completed["status"], "complete")
        self.assertEqual(result["cache_key"], current_cache_key)
        self.assertEqual(len(_BlockingClient.calls), 2)

    async def test_running_durable_job_is_requeued_after_a_service_restart(self):
        request = ReadingRequest(scope="chapter", book_id=self.book.book_id, chapter_index=0)
        material, _metadata, progress_total, _segments = self.service._material_for_request(self.member, request)
        template = template_for(request.scope, request.mode)
        cache_key = self.service._cache_key(
            request, material, self.store.get_book_ai_profile(self.book.book_id), template
        )
        self.store.create_ai_job(
            "restartable-worker-job", self.member.user_id, cache_key,
            book_id=self.book.book_id, progress_total=progress_total,
            request_payload={
                "scope": "chapter", "book_id": self.book.book_id,
                "chapter_index": 0, "mode": "chapter", "language": "en",
                "reading_boundary": 0,
            },
            profile="auto", template_id=template["id"], template_version=template["version"],
        )
        self.assertTrue(self.store.start_ai_job("restartable-worker-job"))
        self.assertEqual(self.store.requeue_running_ai_jobs(), 1)

        await self.service.start_worker()
        self.service.wake_worker()
        completed = await self._wait_for_job("restartable-worker-job")

        self.assertEqual(completed["status"], "complete")

    async def test_transient_provider_server_errors_back_off_across_the_cooling_window(self):
        _FlakyClient.calls = []
        delays = []

        async def record_sleep(delay):
            delays.append(delay)

        service = AIReadingService(
            self.store, self.root / "public", _FlakyClient, sleeper=record_sleep
        )
        request = ReadingRequest(scope="chapter", book_id=self.book.book_id, chapter_index=0)

        try:
            started = await service.submit(self.member, request)
            completed = await self._wait_for_job(started["job"]["id"])
        finally:
            await service.stop_worker()

        self.assertEqual(completed["status"], "complete")
        self.assertEqual(len(_FlakyClient.calls), 5)
        self.assertEqual(delays, [60, 120, 240])

    async def test_non_retryable_provider_error_fails_without_waiting_or_retrying(self):
        _RejectedClient.calls = []
        delays = []

        async def record_sleep(delay):
            delays.append(delay)

        service = AIReadingService(
            self.store, self.root / "public", _RejectedClient, sleeper=record_sleep
        )

        try:
            started = await service.submit(
                self.member,
                ReadingRequest(scope="chapter", book_id=self.book.book_id, chapter_index=0),
            )
            completed = await self._wait_for_job(started["job"]["id"])
        finally:
            await service.stop_worker()

        self.assertEqual(completed["status"], "failed")
        self.assertEqual(completed["error_code"], "provider_request_rejected")
        self.assertEqual(len(_RejectedClient.calls), 1)
        self.assertEqual(delays, [])

    async def test_retry_rechecks_that_the_user_is_still_enabled(self):
        _FlakyClient.calls = []
        delays = []

        async def disable_user_during_wait(delay):
            delays.append(delay)
            self.store.set_user_enabled(self.member.user_id, False)

        service = AIReadingService(
            self.store,
            self.root / "public",
            _FlakyClient,
            sleeper=disable_user_during_wait,
        )

        try:
            started = await service.submit(
                self.member,
                ReadingRequest(
                    scope="chapter", book_id=self.book.book_id, chapter_index=0
                ),
            )
            completed = await self._wait_for_job(started["job"]["id"])
        finally:
            await service.stop_worker()

        self.assertEqual(completed["status"], "failed")
        self.assertEqual(completed["error_code"], "ai_not_authorized")
        self.assertEqual(len(_FlakyClient.calls), 1)
        self.assertEqual(delays, [60])

    async def test_retry_uses_fresh_role_after_administrator_is_demoted(self):
        self.store.create_user("backup-admin", "hash", role="admin")
        self.store.set_book_visibility(self.book.book_id, "restricted")
        _FlakyClient.calls = []
        delays = []

        async def demote_administrator_during_wait(delay):
            delays.append(delay)
            self.store.update_user(self.owner.user_id, role="member")

        service = AIReadingService(
            self.store,
            self.root / "public",
            _FlakyClient,
            sleeper=demote_administrator_during_wait,
        )

        try:
            started = await service.submit(
                self.owner,
                ReadingRequest(
                    scope="chapter", book_id=self.book.book_id, chapter_index=0
                ),
            )
            completed = await self._wait_for_job(
                started["job"]["id"], self.owner.user_id
            )
        finally:
            await service.stop_worker()

        self.assertEqual(completed["status"], "failed")
        self.assertEqual(completed["error_code"], "ai_not_authorized")
        self.assertEqual(len(_FlakyClient.calls), 1)
        self.assertEqual(delays, [60])

    async def test_retry_rechecks_restricted_book_access_after_revocation(self):
        self.store.set_book_visibility(self.book.book_id, "restricted")
        self.store.grant_book_access(self.book.book_id, self.member.user_id)
        _FlakyClient.calls = []
        delays = []

        async def revoke_book_during_wait(delay):
            delays.append(delay)
            self.store.revoke_book_access(self.book.book_id, self.member.user_id)

        service = AIReadingService(
            self.store,
            self.root / "public",
            _FlakyClient,
            sleeper=revoke_book_during_wait,
        )

        try:
            started = await service.submit(
                self.member,
                ReadingRequest(
                    scope="chapter", book_id=self.book.book_id, chapter_index=0
                ),
            )
            completed = await self._wait_for_job(started["job"]["id"])
        finally:
            await service.stop_worker()

        self.assertEqual(completed["status"], "failed")
        self.assertEqual(completed["error_code"], "ai_not_authorized")
        self.assertEqual(len(_FlakyClient.calls), 1)
        self.assertEqual(delays, [60])

    async def test_retry_rechecks_member_ai_access_after_revocation(self):
        _FlakyClient.calls = []
        delays = []

        async def revoke_ai_during_wait(delay):
            delays.append(delay)
            self.store.set_ai_user_access(
                self.member.user_id, enabled=False, daily_limit=10
            )

        service = AIReadingService(
            self.store,
            self.root / "public",
            _FlakyClient,
            sleeper=revoke_ai_during_wait,
        )

        try:
            started = await service.submit(
                self.member,
                ReadingRequest(
                    scope="chapter", book_id=self.book.book_id, chapter_index=0
                ),
            )
            completed = await self._wait_for_job(started["job"]["id"])
        finally:
            await service.stop_worker()

        self.assertEqual(completed["status"], "failed")
        self.assertEqual(completed["error_code"], "ai_not_authorized")
        self.assertEqual(len(_FlakyClient.calls), 1)
        self.assertEqual(delays, [60])

    async def test_chapter_task_retries_provider_attempts_without_a_second_allowance(self):
        self.store.set_ai_user_access(
            self.member.user_id, enabled=True, daily_limit=1
        )
        _FlakyClient.calls = []
        delays = []

        async def record_sleep(delay):
            delays.append(delay)

        service = AIReadingService(
            self.store, self.root / "public", _FlakyClient, sleeper=record_sleep
        )

        try:
            started = await service.submit(
                self.member,
                ReadingRequest(
                    scope="chapter", book_id=self.book.book_id, chapter_index=0
                ),
            )
            completed = await self._wait_for_job(started["job"]["id"])
        finally:
            await service.stop_worker()

        self.assertEqual(completed["status"], "complete")
        self.assertEqual(len(_FlakyClient.calls), 5)
        self.assertEqual(delays, [60, 120, 240])
        self.assertEqual(self._provider_calls(self.member.user_id), 5)
        self.assertEqual(self._reading_tasks(self.member.user_id), 1)

    async def test_client_construction_failure_does_not_charge_quota(self):
        def failing_client_factory(_config):
            raise ValueError("invalid client configuration")

        service = AIReadingService(
            self.store, self.root / "public", failing_client_factory
        )
        config = ProviderConfig(
            "https://provider.example/v1", "secret", "reader-model", 30, 1
        )

        with self.assertRaises(ValueError):
            await service._provider_call(
                self.member,
                config,
                [{"role": "user", "content": "Question"}],
                book_id=self.book.book_id,
                max_tokens=32,
            )

        self.assertEqual(self._provider_calls(self.member.user_id), 0)

    async def test_one_chapter_job_can_make_two_provider_calls_with_one_task_allowance(self):
        self.store.create_ai_job(
            "two-call-chapter-job", self.member.user_id, "two-call-cache",
            book_id=self.book.book_id,
        )
        self.assertTrue(self.store.start_ai_job("two-call-chapter-job"))
        config = ProviderConfig(
            "https://provider.example/v1", "secret", "reader-model", 30, 1
        )
        messages = [{"role": "user", "content": "Chapter source"}]

        self.service._reserve_generation_task(
            "two-call-chapter-job",
            self.member,
            ReadingRequest(
                scope="chapter", book_id=self.book.book_id, chapter_index=0
            ),
        )
        await self.service._provider_call(
            self.member, config, messages, book_id=self.book.book_id,
            max_tokens=32, task_scoped=True,
        )
        await self.service._provider_call(
            self.member, config, messages, book_id=self.book.book_id,
            max_tokens=32, task_scoped=True,
        )

        self.assertEqual(self._provider_calls(self.member.user_id), 2)
        self.assertEqual(self._reading_tasks(self.member.user_id), 1)

    async def test_retrying_a_failed_chapter_job_does_not_reserve_a_second_task(self):
        failing_service = AIReadingService(
            self.store, self.root / "public", _RejectedClient
        )
        try:
            started = await failing_service.submit(
                self.member,
                ReadingRequest(
                    scope="chapter", book_id=self.book.book_id, chapter_index=0
                ),
            )
            failed = await self._wait_for_job(started["job"]["id"])
        finally:
            await failing_service.stop_worker()
        self.assertEqual(failed["status"], "failed")

        retried = await self.service.retry_job(self.owner, failed["id"])
        completed = await self._wait_for_job(retried["job"]["id"])

        self.assertEqual(completed["status"], "complete")
        self.assertEqual(self._reading_tasks(self.member.user_id), 1)

    async def test_cancellation_while_waiting_for_concurrency_does_not_charge_quota(self):
        _BlockingClient.calls = []
        _BlockingClient.started = threading.Event()
        _BlockingClient.release = threading.Event()
        service = AIReadingService(
            self.store, self.root / "public", _BlockingClient
        )
        config = ProviderConfig(
            "https://provider.example/v1", "secret", "reader-model", 30, 1
        )
        messages = [{"role": "user", "content": "Question"}]
        first = asyncio.create_task(
            service._provider_call(
                self.member,
                config,
                messages,
                book_id=self.book.book_id,
                max_tokens=32,
            )
        )
        try:
            for _ in range(100):
                if _BlockingClient.started.is_set():
                    break
                await asyncio.sleep(0.01)
            self.assertTrue(_BlockingClient.started.is_set())
            second = asyncio.create_task(
                service._provider_call(
                    self.member,
                    config,
                    messages,
                    book_id=self.book.book_id,
                    max_tokens=32,
                )
            )
            await asyncio.sleep(0.02)
            second.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await second
        finally:
            _BlockingClient.release.set()
            await first

        self.assertEqual(len(_BlockingClient.calls), 1)
        self.assertEqual(self._provider_calls(self.member.user_id), 1)

    async def test_authorization_is_rechecked_after_waiting_for_concurrency(self):
        _BlockingClient.calls = []
        _BlockingClient.started = threading.Event()
        _BlockingClient.release = threading.Event()
        service = AIReadingService(
            self.store, self.root / "public", _BlockingClient
        )
        config = ProviderConfig(
            "https://provider.example/v1", "secret", "reader-model", 30, 1
        )
        messages = [{"role": "user", "content": "Question"}]
        first = asyncio.create_task(
            service._provider_call(
                self.member,
                config,
                messages,
                book_id=self.book.book_id,
                max_tokens=32,
            )
        )
        try:
            for _ in range(100):
                if _BlockingClient.started.is_set():
                    break
                await asyncio.sleep(0.01)
            self.assertTrue(_BlockingClient.started.is_set())
            second = asyncio.create_task(
                service._provider_call(
                    self.member,
                    config,
                    messages,
                    book_id=self.book.book_id,
                    max_tokens=32,
                )
            )
            await asyncio.sleep(0.02)
            self.store.set_ai_user_access(
                self.member.user_id, enabled=False, daily_limit=10
            )
        finally:
            _BlockingClient.release.set()
            await first

        with self.assertRaises(AIReadingError) as caught:
            await second
        self.assertEqual(caught.exception.code, "ai_not_authorized")
        self.assertEqual(len(_BlockingClient.calls), 1)
        self.assertEqual(self._provider_calls(self.member.user_id), 1)

    async def test_oversized_chapter_uses_context_bounded_parts_and_complete_synthesis(self):
        self.store.set_ai_settings(
            enabled=True,
            base_url="https://provider.example/v1",
            api_key="secret",
            model="reader-model",
            timeout_seconds=30,
            model_context_window=8192,
            max_concurrency=2,
            daily_limit=100,
        )
        self.store.set_ai_user_access(self.member.user_id, enabled=True, daily_limit=100)
        chapter = self.root / "public" / "book" / self.book.book_id / "chapter_0.html"
        paragraphs = [
            marker + " " + ("complete source detail " * 180)
            for marker in _ChunkingClient.markers
        ]
        chapter.write_text(
            "<article>" + "".join("<p>" + paragraph + "</p>" for paragraph in paragraphs) + "</article>",
            encoding="utf-8",
        )
        _ChunkingClient.calls = []
        service = AIReadingService(self.store, self.root / "public", _ChunkingClient)

        try:
            started = await service.submit(
                self.member,
                ReadingRequest(scope="chapter", book_id=self.book.book_id, chapter_index=0),
            )
            completed = await self._wait_for_job(started["job"]["id"])
        finally:
            await service.stop_worker()

        self.assertEqual(completed["status"], "complete")
        part_calls = [
            call for call in _ChunkingClient.calls
            if "contiguous source part" in call["messages"][0]["content"]
        ]
        self.assertGreater(len(part_calls), 1)
        self.assertEqual(len(_ChunkingClient.calls), len(part_calls) + 2)
        for marker in _ChunkingClient.markers:
            self.assertEqual(
                sum(marker in call["messages"][-1]["content"] for call in part_calls),
                1,
            )
            self.assertTrue(all(
                marker in call["messages"][-1]["content"]
                for call in _ChunkingClient.calls[-2:]
            ))
        for call in _ChunkingClient.calls:
            estimated_input = _estimate_messages_tokens(
                call["messages"], "reader-model"
            )
            self.assertLessEqual(estimated_input + call["max_tokens"] + 409, 8192)
        self.assertEqual(completed["progress_current"], len(part_calls) + 2)
        self.assertEqual(completed["progress_total"], len(part_calls) + 2)
        result = self.store.get_ai_reading_result(completed["result_id"])
        self.assertEqual(result["content"]["annotations"][0]["quote"], "FINAL_MARKER")

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

    def test_extract_chapter_text_preserves_content_after_48000_characters(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "chapter.html"
            path.write_text(
                "<article><p>" + ("long chapter content " * 2600) + "</p><p>FINAL_MARKER</p></article>",
                encoding="utf-8",
            )

            extracted = extract_chapter_text(path)

            self.assertGreater(len(extracted), 48000)
            self.assertTrue(extracted.endswith("FINAL_MARKER"))


class ModelContextBudgetTests(unittest.TestCase):
    def test_dependency_free_estimator_uses_utf8_byte_upper_bound(self):
        samples = (
            ("plain ASCII", 11),
            ("中文内容", 12),
            ("العربية", 14),
            ("हिन्दी", 18),
            ("😀🤔🧠", 12),
        )

        with mock.patch.dict(sys.modules, {"tiktoken": None}):
            for sample, expected in samples:
                with self.subTest(sample=sample):
                    self.assertEqual(
                        _estimate_tokens(sample, "unknown-model"),
                        expected,
                    )

    def test_optional_tokenizer_cannot_reduce_the_safe_upper_bound(self):
        undercounting_tiktoken = mock.Mock()
        undercounting_tiktoken.encoding_for_model.return_value.encode.return_value = [1]

        with mock.patch.dict(sys.modules, {"tiktoken": undercounting_tiktoken}):
            self.assertEqual(
                _estimate_tokens("😀 arbitrary provider", "unknown-model"),
                len("😀 arbitrary provider".encode("utf-8")),
            )

    def test_truncation_suffix_stays_inside_the_byte_budget(self):
        truncated = _truncate_tokens("abcdefghijklmnopqrstuvwxyz", 10)

        self.assertTrue(truncated.endswith("…"))
        self.assertLessEqual(_estimate_tokens(truncated), 10)

    def test_context_window_controls_output_and_safety_reserves(self):
        cases = (
            (2048, (512, 128)),
            (32768, (6553, 1638)),
            (1050000, (16384, 4096)),
        )

        for context_window, expected in cases:
            with self.subTest(context_window=context_window):
                budget = _ModelTokenBudget.from_context_window(context_window)
                self.assertEqual(
                    (budget.output_tokens, budget.safety_tokens), expected
                )
                self.assertLess(
                    budget.output_tokens + budget.safety_tokens,
                    budget.context_window,
                )

    def test_token_chunks_fit_the_budget_without_dropping_the_middle_or_end(self):
        source = (
            "FIRST paragraph has a short introduction.\n"
            + ("MIDDLE detail and explanation. " * 80)
            + "\nFINAL paragraph closes the chapter."
        )

        chunks = _split_text_by_token_budget(source, 80, "reader-model")

        self.assertGreater(len(chunks), 2)
        self.assertEqual("".join(chunks), source)
        self.assertTrue(all(_estimate_tokens(chunk, "reader-model") <= 80 for chunk in chunks))
        self.assertIn("MIDDLE", "".join(chunks))
        self.assertTrue(chunks[-1].endswith("FINAL paragraph closes the chapter."))

    def test_dependency_free_chunks_bound_emoji_and_non_latin_source(self):
        source = "BEGIN " + ("😀 العربية 日本語 " * 40) + "END"

        with mock.patch.dict(sys.modules, {"tiktoken": None}):
            chunks = _split_text_by_token_budget(source, 96, "unknown-model")

            self.assertGreater(len(chunks), 2)
            self.assertEqual("".join(chunks), source)
            self.assertTrue(
                all(
                    _estimate_tokens(chunk, "unknown-model") <= 96
                    for chunk in chunks
                )
            )

    def test_token_chunks_prefer_paragraph_boundaries_and_hard_split_long_words(self):
        paragraphs = ("甲" * 40) + "\n" + ("乙" * 40)
        paragraph_chunks = _split_text_by_token_budget(
            paragraphs, 130, "reader-model"
        )
        long_word = "FIRST" + ("界" * 180) + "FINAL"
        hard_chunks = _split_text_by_token_budget(long_word, 50, "reader-model")

        self.assertTrue(paragraph_chunks[0].endswith("\n"))
        self.assertEqual("".join(paragraph_chunks), paragraphs)
        self.assertGreater(len(hard_chunks), 2)
        self.assertEqual("".join(hard_chunks), long_word)
        self.assertTrue(
            all(
                _estimate_tokens(chunk, "reader-model") <= 50
                for chunk in hard_chunks
            )
        )


class ResultNormalizationTests(unittest.TestCase):
    def test_public_ai_job_includes_only_safe_stage_progress(self):
        """Readers receive the durable stage, never the private replay payload."""
        public = _public_ai_job({
            "id": "job",
            "request_json": "secret",
            "generation_stage": "generating_core",
        })

        self.assertEqual(public["generation_stage"], "generating_core")
        self.assertNotIn("request_json", public)

    def test_compact_core_synopsis_is_valid_json_and_keeps_beats_at_2048(self):
        core = {
            "quick": {
                "title": "A very long opening guide",
                "summary": "opening context " * 80,
                "key_points": ["context " * 40],
            },
            "teach": {
                "explanation": "plain explanation " * 80,
                "analogy": "familiar analogy " * 40,
                "check_question": "Explain it back in your own words.",
            },
            "chapter_summary": {
                "overview": "A long overview " * 40,
                "beats": [
                    {
                        "label": "Opening",
                        "title": "First claim",
                        "summary": "Introduces the central claim.",
                    },
                    {
                        "label": "Turn",
                        "title": "Counterexample",
                        "summary": "Challenges the first claim.",
                    },
                    {
                        "label": "Closing",
                        "title": "Revised conclusion",
                        "summary": "Resolves the chapter's tension.",
                    },
                ],
                "key_elements": [],
                "closing": "A long closing " * 40,
            },
            "structure": {"overview": "structure " * 80, "nodes": [], "links": []},
            "deep": {"themes": [], "questions": [], "applications": []},
        }

        synopsis = AIReadingService._compact_core_synopsis(
            core, _ModelTokenBudget.from_context_window(2048), "reader-model"
        )
        try:
            parsed = json.loads(synopsis)
        except json.JSONDecodeError as error:
            self.fail("compact core synopsis is not valid JSON: {}".format(error))

        beats = parsed["chapter_summary"]["beats"]
        self.assertEqual(len(beats), 3)
        self.assertEqual(
            [set(beat) for beat in beats],
            [{"title", "summary"}, {"title", "summary"}, {"title", "summary"}],
        )
        self.assertTrue(all(beat["title"] and beat["summary"] for beat in beats))
        self.assertLessEqual(len(synopsis.encode("utf-8")), 2048 // 6)

    def test_core_summary_fallback_does_not_include_rejected_grounding_fields(self):
        core = _normalize_core_result(json.dumps({
            "quick": {"title": "Guide", "key_points": []},
            "teach": {"explanation": "Plain", "analogy": "", "check_question": ""},
            "chapter_summary": {"overview": "", "beats": [], "key_elements": [], "closing": ""},
            "structure": {"overview": "", "diagram_mermaid": "", "nodes": [], "links": []},
            "deep": {"themes": [], "questions": [], "applications": []},
            "evidence": [{
                "chapter_index": 0,
                "quote": "CORE-ONLY-ANCHOR",
                "reason": "Rejected grounding data",
            }],
            "annotations": [{
                "chapter_index": 0,
                "kind": "claim",
                "quote": "CORE-ONLY-ANCHOR",
                "title": "Rejected",
                "body_markdown": "Rejected grounding data",
            }],
        }))

        self.assertEqual(core["quick"]["summary"], "")
        self.assertNotIn("CORE-ONLY-ANCHOR", json.dumps(core, ensure_ascii=False))

    def test_chapter_core_contract_normalizes_feynman_teach_without_anchor_fields(self):
        core = _normalize_core_result(json.dumps({
            "quick": {"title": "Guide", "summary": "Overview", "key_points": []},
            "teach": {
                "explanation": "Plain explanation",
                "analogy": "Daily analogy",
                "check_question": "Explain it back.",
            },
            "chapter_summary": {
                "overview": "A guided account.",
                "beats": [{
                    "label": "Opening",
                    "title": "The claim",
                    "anchor_quote": "Core must not own this source anchor.",
                    "summary": "Introduces the claim.",
                }],
                "key_elements": [],
                "closing": "",
            },
            "structure": {"overview": "", "diagram_mermaid": "", "nodes": [], "links": []},
            "deep": {"themes": [], "questions": [], "applications": []},
            "evidence": [{"chapter_index": 0, "quote": "Unsafe", "reason": "Unsafe"}],
            "annotations": [{"chapter_index": 0, "quote": "Unsafe"}],
        }))

        self.assertEqual(core["teach"]["explanation"], "Plain explanation")
        self.assertEqual(
            set(core), {"quick", "teach", "chapter_summary", "structure", "deep"}
        )
        self.assertNotIn("anchor_quote", core["chapter_summary"]["beats"][0])

    def test_merge_keeps_only_grounded_annotations(self):
        core_layer = {
            "quick": {"title": "Guide", "summary": "Overview", "key_points": []},
            "teach": {"explanation": "Plain", "analogy": "", "check_question": ""},
            "chapter_summary": {"overview": "", "beats": [], "key_elements": [], "closing": ""},
            "structure": {"overview": "", "diagram_mermaid": "", "nodes": [], "links": []},
            "deep": {"themes": [], "questions": [], "applications": []},
            "annotations": [{
                "chapter_index": 0, "kind": "claim", "quote": "Core invention.",
                "title": "Unsafe", "body_markdown": "Must be ignored.",
            }],
        }
        grounding_layer = {
            "evidence": [],
            "annotations": [{
                "chapter_index": 0, "kind": "claim", "quote": "Exact source quote.",
                "title": "Grounded", "body_markdown": "Tied to the source.",
            }],
            "paragraph_notes": [],
        }

        merged = _merge_chapter_layers(core_layer, grounding_layer)
        validated = AIReadingService._validate_learning_layer(
            merged,
            ReadingRequest(scope="chapter", book_id="book", chapter_index=0),
            "Exact source quote.",
        )

        self.assertEqual(validated["annotations"], [grounding_layer["annotations"][0]])

    def test_grounded_evidence_requires_an_exact_source_quote(self):
        content = {
            "quick": {},
            "teach": {},
            "chapter_summary": {},
            "structure": {},
            "deep": {},
            "evidence": [
                {"chapter_index": 10, "quote": "Exact source quote.", "reason": "Support"},
                {"chapter_index": 10, "quote": "Invented quote.", "reason": "Unsafe"},
            ],
            "annotations": [],
            "paragraph_notes": [],
        }

        validated = AIReadingService._validate_learning_layer(
            content,
            ReadingRequest(scope="chapter", book_id="book", chapter_index=21),
            "Exact source quote.",
        )

        self.assertEqual(validated["evidence"], [{
            "chapter_index": 21,
            "quote": "Exact source quote.",
            "reason": "Support",
        }])

    def test_chapter_summary_contract_does_not_change_book_generation(self):
        chapter_template = template_for("chapter", "chapter")
        book_template = template_for("book", "full_review")

        self.assertEqual(chapter_template["version"], 9)
        self.assertIn("chapter_summary", chapter_template["system"])
        self.assertIn("key_elements", chapter_template["system"])
        self.assertEqual(book_template["version"], 5)
        self.assertNotIn("chapter_summary", book_template["system"])

    def test_chapter_templates_separate_learning_from_source_grounding(self):
        core = chapter_core_template()
        grounding = chapter_grounding_template()

        self.assertEqual((core["id"], core["version"]), (grounding["id"], grounding["version"]))
        self.assertIn("teach", core["system"])
        self.assertNotIn("anchor_quote", core["system"])
        self.assertNotIn("annotations", core["system"])
        self.assertIn("anchor_quote", grounding["system"])
        self.assertIn("annotations", grounding["system"])

    def test_chapter_prompt_uses_distinct_profile_guidance(self):
        template = template_for("chapter", "chapter")

        technical = profile_system_prompt(template, "technical")
        fiction = profile_system_prompt(template, "fiction")
        general = profile_system_prompt(template, "general")

        self.assertIn("argument, method", technical)
        self.assertIn("narrative movement", fiction)
        self.assertIn("concepts, facts", general)
        self.assertNotEqual(technical, fiction)

    def test_chapter_prompt_frames_analysis_as_evidence_based_reading_comprehension(self):
        template = template_for("chapter", "chapter")

        prompt = profile_system_prompt(template, "general")

        self.assertIn("reading-comprehension researcher", prompt)
        self.assertIn("textual evidence", prompt)
        self.assertIn("fact, inference, and open question", prompt)

    def test_chapter_summary_keeps_story_beats_and_key_elements_with_exact_source_anchors(self):
        result = _normalize_result(json.dumps({
            "quick": {"summary": "Quick guide"},
            "chapter_summary": {
                "overview": "A complete account of this chapter.",
                "beats": [
                    {
                        "label": "Opening",
                        "title": "The opening claim",
                        "anchor_quote": "The source starts here.",
                        "summary": "It establishes the chapter's subject.",
                    },
                    {
                        "label": "Discarded",
                        "title": "Discarded section",
                        "anchor_quote": "This is absent from the source.",
                        "summary": "It must not be published as navigable detail.",
                    },
                ],
                "key_elements": [
                    {"name": "Memory", "note": "The pressure point of the chapter."},
                    {"name": "The diary", "note": "Turns private doubt into action."},
                ],
                "closing": "The chapter leaves the question open.",
            },
        }))
        request = ReadingRequest(scope="chapter", book_id="book", chapter_index=0)
        validated = AIReadingService._validate_learning_layer(
            result, request, "The source starts here.\nIt continues here."
        )

        self.assertEqual(validated["chapter_summary"], {
            "overview": "A complete account of this chapter.",
            "beats": [{
                "label": "Opening",
                "title": "The opening claim",
                "anchor_quote": "The source starts here.",
                "summary": "It establishes the chapter's subject.",
            }],
            "key_elements": [
                {"name": "Memory", "note": "The pressure point of the chapter."},
                {"name": "The diary", "note": "Turns private doubt into action."},
            ],
            "closing": "The chapter leaves the question open.",
        })

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

    def test_shared_canvas_annotations_are_typed_and_require_exact_source_anchors(self):
        result = _normalize_result(json.dumps({
            "quick": {"summary": "Summary"},
            "annotations": [
                {
                    "chapter_index": 0,
                    "kind": "claim",
                    "quote": "Source sentence.",
                    "title": "Central claim",
                    "body_markdown": "**Why it matters**\n\n```math\na^2+b^2=c^2\n```",
                },
                {
                    "chapter_index": 0,
                    "kind": "claim",
                    "quote": "Not present in the source.",
                    "title": "Must not be placed",
                    "body_markdown": "This has no reliable anchor.",
                },
            ],
        }))
        request = ReadingRequest(scope="chapter", book_id="book", chapter_index=0)
        validated = AIReadingService._validate_learning_layer(
            result, request, "Source sentence.\nRead this carefully."
        )

        self.assertEqual(validated["annotations"], [{
            "chapter_index": 0,
            "kind": "claim",
            "quote": "Source sentence.",
            "title": "Central claim",
            "body_markdown": "**Why it matters**\n\n```math\na^2+b^2=c^2\n```",
        }])

    def test_learning_layer_preserves_a_mermaid_mind_map_for_the_native_canvas(self):
        result = _normalize_result(json.dumps({
            "quick": {"summary": "Summary"},
            "structure": {
                "diagram_mermaid": "mindmap\n  root((Central idea))\n    Cause\n    Effect",
                "nodes": [{"label": "Cause", "detail": "Starts the argument."}],
            },
        }))

        self.assertEqual(
            result["structure"]["diagram_mermaid"],
            "mindmap\n  root((Central idea))\n    Cause\n    Effect",
        )

    def test_learning_layer_discards_legacy_flowcharts_for_the_mind_map_surface(self):
        result = _normalize_result(json.dumps({
            "quick": {"summary": "Summary"},
            "structure": {
                "diagram_mermaid": "flowchart LR\nA[Cause] --> B[Effect]",
                "nodes": [{"label": "Cause", "detail": "Starts the argument."}],
            },
        }))

        self.assertEqual(result["structure"]["diagram_mermaid"], "")

    def test_paragraph_notes_need_exact_source_anchors(self):
        result = _normalize_result(json.dumps({
            "quick": {"summary": "Summary"},
            "paragraph_notes": [
                {"chapter_index": 0, "anchor_quote": "Source sentence.", "title": "Opening move", "summary_markdown": "Frames the problem."},
                {"chapter_index": 0, "anchor_quote": "Not in source", "title": "Discard", "summary_markdown": "Must not be shown."},
            ],
        }))
        request = ReadingRequest(scope="chapter", book_id="book", chapter_index=0)
        validated = AIReadingService._validate_learning_layer(
            result, request, "Source sentence.\nRead this carefully."
        )

        self.assertEqual(validated["paragraph_notes"], [{
            "chapter_index": 0, "anchor_quote": "Source sentence.",
            "title": "Opening move", "summary_markdown": "Frames the problem.",
        }])

    def test_chapter_layer_normalizes_printed_chapter_numbers_to_page_index(self):
        result = _normalize_result(json.dumps({
            "quick": {"summary": "Summary"},
            "annotations": [{
                "chapter_index": 10, "kind": "claim", "quote": "Source sentence.",
                "title": "The actual claim", "body_markdown": "It frames the argument.",
            }],
            "paragraph_notes": [{
                "chapter_index": 10, "anchor_quote": "Read this carefully.",
                "title": "The paragraph's turn", "summary_markdown": "It changes the stakes.",
            }],
        }))
        request = ReadingRequest(scope="chapter", book_id="book", chapter_index=21)
        validated = AIReadingService._validate_learning_layer(
            result, request, "Source sentence.\nRead this carefully."
        )

        self.assertEqual(validated["annotations"][0]["chapter_index"], 21)
        self.assertEqual(validated["paragraph_notes"][0]["chapter_index"], 21)
