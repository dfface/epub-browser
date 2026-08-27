"""Signed, durable WebHook delivery for Server administrators."""

import asyncio
import hashlib
import hmac
import json
import random
import time
import urllib.error
import urllib.request
import uuid


WEBHOOK_EVENT_TYPES = frozenset({
    "book.created", "book.updated", "book.removed",
    "book.conversion.succeeded", "book.conversion.failed",
    "review.created", "review.updated", "review.deleted", "webhook.test",
})


def sign_webhook(secret, timestamp, body):
    key = secret if isinstance(secret, bytes) else str(secret).encode("utf-8")
    message = str(int(timestamp)).encode("ascii") + b"." + body
    return "v1=" + hmac.new(key, message, hashlib.sha256).hexdigest()


def _random_jitter(maximum):
    return random.uniform(0, maximum)


def retry_delay_seconds(attempt_number, *, jitter=_random_jitter):
    base = min(30 * (2 ** max(int(attempt_number) - 1, 0)), 86400)
    return min(86400, base + max(0, jitter(min(base * 0.2, 300))))


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class WebhookTransport:
    def __init__(self, timeout=10):
        self.timeout = timeout
        self._opener = urllib.request.build_opener(_NoRedirect)

    async def post(self, url, body, headers):
        return await asyncio.to_thread(self._post, url, body, headers)

    def _post(self, url, body, headers):
        request = urllib.request.Request(url, data=body, headers=headers, method="POST")
        try:
            with self._opener.open(request, timeout=self.timeout) as response:
                response.read(64 * 1024)
                return int(response.status)
        except urllib.error.HTTPError as error:
            error.read(64 * 1024)
            return int(error.code)


class WebhookService:
    def __init__(self, store, *, transport=None, clock=time.time, jitter=_random_jitter):
        self.store = store
        self.transport = transport or WebhookTransport()
        self.clock = clock
        self.jitter = jitter
        self.worker_id = uuid.uuid4().hex
        self._task = None
        self._stop = None

    async def run_once(self):
        now = self.clock()
        delivery = self.store.claim_webhook_delivery(self.worker_id, now=now)
        if delivery is None:
            return False
        timestamp = int(now)
        body = json.dumps(
            delivery["payload"], ensure_ascii=False, sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "EPUB-Browser-WebHook/1",
            "X-EPUB-Event": delivery["event_type"],
            "X-EPUB-Delivery": delivery["id"],
            "X-EPUB-Timestamp": str(timestamp),
            "X-EPUB-Signature": sign_webhook(delivery["secret"], timestamp, body),
        }
        status_code = None
        error = None
        try:
            status_code = await self.transport.post(delivery["url"], body, headers)
        except Exception as caught:
            error = type(caught).__name__
        attempt = delivery["attempt_count"] + 1
        retry_at = now + retry_delay_seconds(attempt, jitter=self.jitter)
        self.store.finish_webhook_delivery(
            delivery["id"], self.worker_id, status_code=status_code,
            error=error, retry_at=retry_at, now=now,
        )
        return True

    async def _run(self):
        while self._stop is not None and not self._stop.is_set():
            if not await self.run_once():
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=1)
                except asyncio.TimeoutError:
                    pass

    async def start_worker(self):
        if self._task is None:
            self.store.cleanup_webhook_history(now=self.clock(), retention_days=30)
            self._stop = asyncio.Event()
            self._task = asyncio.create_task(self._run())

    async def stop_worker(self):
        if self._task is not None:
            self._stop.set()
            await self._task
            self._task = None
            self._stop = None
