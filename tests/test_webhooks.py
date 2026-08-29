import hashlib
import hmac
import json
import tempfile
import unittest
from pathlib import Path

from starlette.testclient import TestClient

from epub_browser.auth import AuthConfig, AuthService
from epub_browser.auth import BootstrapCredentials
from epub_browser.server import create_app
from epub_browser.state import StateStore
from epub_browser.webhooks import WEBHOOK_EVENT_TYPES, WebhookService, retry_delay_seconds, sign_webhook
from tests.test_server import _json_login


class FakeTransport:
    def __init__(self, status=204):
        self.status = status
        self.calls = []

    async def post(self, url, body, headers):
        self.calls.append((url, body, headers))
        return self.status


class WebhookTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addAsyncCleanup(self._cleanup)
        self.store = StateStore(Path(self.directory.name) / "state.db")
        self.store.initialize(BootstrapCredentials("admin", "secret"))

    async def _cleanup(self):
        self.directory.cleanup()

    def test_signature_covers_timestamp_period_and_exact_body(self):
        signature = sign_webhook(b"secret", 1700000000, b'{"ok":true}')
        expected = hmac.new(
            b"secret", b'1700000000.{"ok":true}', hashlib.sha256
        ).hexdigest()
        self.assertEqual(signature, "v1=" + expected)

    def test_retry_schedule_is_exponential_and_bounded(self):
        self.assertEqual(retry_delay_seconds(1, jitter=lambda _: 0), 30)
        self.assertEqual(retry_delay_seconds(8, jitter=lambda _: 0), 3840)
        self.assertLessEqual(retry_delay_seconds(30, jitter=lambda _: 0), 86400)

    async def test_delivery_is_signed_and_non_2xx_is_retried(self):
        endpoint = self.store.create_webhook_endpoint(
            "Receiver", "https://example.test/hook", {"webhook.test"}
        )
        self.store.enqueue_webhook_event("webhook.test", {"endpoint_id": endpoint["webhook"]["id"]}, now=100)
        transport = FakeTransport(status=302)
        service = WebhookService(
            self.store, transport=transport, clock=lambda: 100, jitter=lambda _: 0
        )

        self.assertTrue(await service.run_once())

        delivery = self.store.list_webhook_deliveries()[0]
        self.assertEqual(delivery["status"], "retrying")
        self.assertEqual(delivery["attempt_count"], 1)
        _url, body, headers = transport.calls[0]
        self.assertEqual(json.loads(body)["type"], "webhook.test")
        self.assertTrue(headers["X-EPUB-Signature"].startswith("v1="))
        self.assertEqual(set(WEBHOOK_EVENT_TYPES) >= {"review.created", "webhook.test"}, True)

    async def test_expired_delivery_lease_is_reclaimed_after_worker_restart(self):
        endpoint = self.store.create_webhook_endpoint(
            "Receiver", "https://example.test/hook", {"webhook.test"}
        )
        self.store.enqueue_webhook_test(endpoint["webhook"]["id"], now=100)
        first = self.store.claim_webhook_delivery("worker-a", now=100, lease_seconds=30)
        self.assertIsNotNone(first)
        self.assertIsNone(
            self.store.claim_webhook_delivery("worker-b", now=120, lease_seconds=30)
        )
        reclaimed = self.store.claim_webhook_delivery(
            "worker-b", now=131, lease_seconds=30
        )
        self.assertEqual(reclaimed["id"], first["id"])

    async def test_cleanup_preserves_pending_deliveries(self):
        endpoint = self.store.create_webhook_endpoint(
            "Receiver", "https://example.test/hook", {"webhook.test"}
        )
        self.store.enqueue_webhook_test(endpoint["webhook"]["id"], now=100)
        self.assertEqual(self.store.cleanup_webhook_history(now=10_000_000, retention_days=30), 0)
        self.assertEqual(len(self.store.list_webhook_deliveries()), 1)

    async def test_book_webhook_payloads_add_the_source_format(self):
        record = self.store.resolve_book(
            Path(self.directory.name) / "document.pdf",
            None,
            "pdf-fingerprint",
            {"title": "PDF"},
            preferred_book_id="pdf",
            source_format="pdf",
        )

        created = self.store.list_webhook_events(event_type="book.created")[0]
        self.assertEqual(created["data"], {"book_id": record.book_id, "format": "pdf"})

        self.store.update_book_version(
            record.book_id, "pdf-fingerprint-2", {"title": "PDF 2"},
            source_format="pdf",
        )
        updated = self.store.list_webhook_events(event_type="book.updated")[0]
        self.assertEqual(updated["data"], {"book_id": record.book_id, "format": "pdf"})

        self.store.mark_missing(record.book_id)
        removed = self.store.list_webhook_events(event_type="book.removed")[0]
        self.assertEqual(removed["data"], {"book_id": record.book_id, "format": "pdf"})


class WebhookAdminAPITests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        public = Path(self.directory.name)
        (public / "index.html").write_text("library", encoding="utf-8")
        (public / "assets").mkdir()
        self.store = StateStore(public / "state.db")
        self.store.initialize(BootstrapCredentials("admin", "secret"))
        auth = AuthService(self.store, AuthConfig.from_values([]))
        self.client = TestClient(create_app(public, state_store=self.store, auth_service=auth))
        _json_login(self, self.client, "admin", "secret")
        self.client.headers["X-CSRF-Token"] = self.client.get("/api/session").json()["csrf_token"]

    def test_secret_is_returned_only_on_create_and_rotation(self):
        created = self.client.post("/api/admin/webhooks", json={
            "name": "Automation", "url": "https://example.test/hook",
            "event_types": ["review.created"], "enabled": True,
        })
        self.assertEqual(created.status_code, 201, created.text)
        self.assertIn("secret", created.json())
        webhook_id = created.json()["webhook"]["id"]

        listing = self.client.get("/api/admin/webhooks")
        self.assertNotIn("secret", listing.text)
        rotated = self.client.post(
            "/api/admin/webhooks/{}/rotate-secret".format(webhook_id), json={}
        )
        self.assertEqual(rotated.status_code, 200)
        self.assertIn("secret", rotated.json())

    def test_webhook_mutations_require_csrf_and_validate_url(self):
        self.client.headers.pop("X-CSRF-Token")
        denied = self.client.post("/api/admin/webhooks", json={})
        self.assertEqual(denied.status_code, 403)
        self.client.headers["X-CSRF-Token"] = self.client.get("/api/session").json()["csrf_token"]
        invalid = self.client.post("/api/admin/webhooks", json={
            "name": "Bad", "url": "file:///etc/passwd",
            "event_types": ["review.created"], "enabled": True,
        })
        self.assertEqual(invalid.status_code, 400)


if __name__ == "__main__":
    unittest.main()
