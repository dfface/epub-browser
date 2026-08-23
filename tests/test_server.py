import asyncio
import base64
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import sqlite3
import tempfile
import threading
import unittest
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote
from unittest import mock

from starlette.testclient import TestClient

from epub_browser.auth import (
    AuthConfig,
    AuthService,
    BootstrapCredentials,
    hash_password,
)
from epub_browser.ai_reading import AIReadingError, AIReadingService
from epub_browser.library_progress import LibraryProgressBroker
from epub_browser.processor import SERVER_OUTPUT_REVISION, SERVER_OUTPUT_REVISION_FILE
from epub_browser.runtime import RuntimeStatus
from epub_browser.server import create_app, migrate_legacy_database
from epub_browser.state import StateStore


def _anonymous_auth_nonce(testcase, client, path="/login"):
    page = client.get(path)
    testcase.assertEqual(page.status_code, 200)
    match = re.search(
        r'<meta name="epub-browser-auth-nonce" content="([^"]+)">',
        page.text,
    )
    testcase.assertIsNotNone(match)
    testcase.assertIn("epub_browser_auth_nonce=", page.headers["set-cookie"])
    testcase.assertIn("SameSite=strict", page.headers["set-cookie"])
    return match.group(1)


def _json_login(testcase, client, username, password, *, next_path="/"):
    nonce = _anonymous_auth_nonce(
        testcase,
        client,
        "/login?next=" + quote(next_path, safe=""),
    )
    return client.post(
        "/login",
        json={"username": username, "password": password, "next": next_path},
        headers={
            "X-EPUB-Browser-Auth-Nonce": nonce,
            "Origin": str(client.base_url).rstrip("/"),
            "Sec-Fetch-Site": "same-origin",
        },
    )


def _first_sse_chunk(app, path, session_token):
    """Read one SSE frame, then explicitly simulate a browser disconnect."""
    async def collect():
        headers = {}
        chunks = asyncio.Queue()
        response_started = asyncio.Event()
        disconnected = asyncio.Event()
        request_path, _, query_string = path.partition("?")

        async def receive():
            await disconnected.wait()
            return {"type": "http.disconnect"}

        async def send(message):
            if message["type"] == "http.response.start":
                headers["status"] = message["status"]
                headers.update({
                    name.decode().lower(): value.decode()
                    for name, value in message["headers"]
                })
                response_started.set()
            elif message["type"] == "http.response.body" and message.get("body"):
                await chunks.put(message["body"].decode())

        task = asyncio.create_task(app(
            {
                "type": "http",
                "asgi": {"version": "3.0"},
                "http_version": "1.1",
                "method": "GET",
                "scheme": "http",
                "path": request_path,
                "raw_path": request_path.encode(),
                "query_string": query_string.encode(),
                "headers": [(b"cookie", ("epub_browser_session=" + session_token).encode())],
                "client": ("testclient", 50000),
                "server": ("testserver", 80),
            },
            receive,
            send,
        ))
        await asyncio.wait_for(response_started.wait(), 1)
        chunk = await asyncio.wait_for(chunks.get(), 1)
        disconnected.set()
        await asyncio.wait_for(task, 1)
        return headers, chunk

    return asyncio.run(collect())


@contextmanager
def _assert_no_error_logs(testcase, logger_name):
    logger = logging.getLogger(logger_name)
    original_level = logger.level
    original_handlers = logger.handlers[:]
    original_propagate = logger.propagate
    records = []

    class ErrorCapture(logging.Handler):
        def emit(self, record):
            records.append(record)

    handler = ErrorCapture(level=logging.ERROR)
    logger.addHandler(handler)
    logger.setLevel(logging.ERROR)
    try:
        yield
    finally:
        logger.handlers[:] = original_handlers
        logger.setLevel(original_level)
        logger.propagate = original_propagate

    if records:
        testcase.fail(
            "unexpected ERROR-or-higher logs from {}: {}".format(
                logger_name,
                "; ".join(record.getMessage() for record in records),
            ),
        )


class LoggingAssertionCompatibilityTests(unittest.TestCase):
    def test_error_logs_are_captured_and_logger_state_is_restored(self):
        logger = logging.getLogger("asyncio")
        original_level = logger.level
        original_handlers = logger.handlers[:]
        original_propagate = logger.propagate
        logger.setLevel(logging.CRITICAL)
        configured_handlers = [logging.NullHandler()]
        logger.handlers[:] = configured_handlers
        logger.propagate = False

        try:
            with self.assertRaisesRegex(
                AssertionError,
                "unexpected ERROR-or-higher logs from asyncio: captured error",
            ):
                with _assert_no_error_logs(self, "asyncio"):
                    logger.error("captured error")
            self.assertEqual(logger.level, logging.CRITICAL)
            self.assertEqual(logger.handlers, configured_handlers)
            self.assertFalse(logger.propagate)
        finally:
            logger.handlers[:] = original_handlers
            logger.setLevel(original_level)
            logger.propagate = original_propagate


class ServerSetupBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.public = Path(self.directory.name) / "public"
        self.public.mkdir()
        (self.public / "index.html").write_text(
            "private library content",
            encoding="utf-8",
        )
        (self.public / "assets").mkdir()
        (self.public / "assets" / "reader.js").write_text(
            "private reader asset",
            encoding="utf-8",
        )
        (self.public / "assets" / "auth.js").write_text(
            "generated auth asset",
            encoding="utf-8",
        )
        (self.public / "book" / "id").mkdir(parents=True)
        (self.public / "book" / "id" / "index.html").write_text(
            "private book",
            encoding="utf-8",
        )
        self.store = StateStore(Path(self.directory.name) / "state.db")
        self.pending = self.store.initialize()
        self.auth_config = AuthConfig.from_values([], None, None)
        self.app = create_app(
            self.public,
            state_store=self.store,
            auth_service=AuthService(self.store, self.auth_config),
        )
        self.client = TestClient(self.app, follow_redirects=False)
        self.addCleanup(self.client.close)

    def _setup_nonce(self, client=None, path="/setup"):
        active_client = client or self.client
        response = active_client.get(path)
        match = re.search(r'name="setup_nonce" value="([^"]+)"', response.text)
        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(match)
        return match.group(1)

    def test_pending_setup_exposes_only_setup_fixed_assets_and_minimal_status(self):
        english = self.client.get("/setup?lang=en")
        chinese = self.client.get("/setup?lang=zh-CN")

        self.assertEqual(english.status_code, 200)
        self.assertEqual(chinese.status_code, 200)
        self.assertIn(
            "When you first access the web interface, you will be prompted "
            "to create a superuser account.",
            english.text,
        )
        self.assertIn("首次访问 Web 界面时，系统会提示你创建一个超级用户账户。", chinese.text)
        self.assertIn('id="setupForm"', english.text)
        self.assertIn('class="auth-page"', english.text)
        self.assertIn('class="auth-card setup-card"', english.text)
        self.assertIn('href="/assets/account.css"', english.text)
        self.assertIn('href="/assets/theme.css"', english.text)
        self.assertIn('src="/assets/theme-bootstrap.js"', english.text)
        self.assertIn('src="/assets/version-check.js"', english.text)
        self.assertIn('data-id="eb-footer"', english.text)
        self.assertIn('data-i18n="footer.product"', english.text)
        self.assertIn('href="https://github.com/dfface/epub-browser"', english.text)
        self.assertNotIn('<style>', english.text)
        self.assertIn('name="password_confirmation"', english.text)
        self.assertIn('name="setup_nonce"', english.text)
        nonce = re.search(
            r'name="setup_nonce" value="([^"]+)"',
            english.text,
        ).group(1)
        self.assertGreaterEqual(len(nonce), 32)
        self.assertIn('id="setupLocaleSelect"', english.text)
        setup_cookie = english.headers["set-cookie"]
        self.assertIn("epub_browser_setup_nonce=", setup_cookie)
        self.assertIn("HttpOnly", setup_cookie)
        self.assertIn("Path=/setup", setup_cookie)
        self.assertIn("SameSite=strict", setup_cookie)
        account_styles = self.client.get('/assets/account.css')
        self.assertEqual(account_styles.status_code, 200)
        self.assertIn('text/css', account_styles.headers['content-type'])
        self.assertIn('.auth-card', account_styles.text)
        self.assertIn('.account-layout', account_styles.text)

        for path in ("/", "/index.html", "/login", "/reader.html"):
            with self.subTest(path=path):
                response = self.client.get(path, headers={"Accept": "text/html"})
                self.assertEqual(response.status_code, 303)
                self.assertEqual(response.headers["location"], "/setup")

        for path in (
            "/api/annotations/book",
            "/api/library-events",
            "/book/id/index.html",
            "/assets/reader.js",
        ):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 503)
                self.assertEqual(response.json()["code"], "setup_required")
                self.assertNotIn("private", response.text)

        fixed_auth = self.client.get("/assets/auth.js")
        self.assertEqual(fixed_auth.status_code, 200)
        self.assertNotIn("generated auth asset", fixed_auth.text)
        self.assertEqual(self.client.get("/assets/i18n.js").status_code, 200)
        self.assertEqual(self.client.get("/assets/theme.css").status_code, 200)
        self.assertEqual(
            self.client.get("/assets/theme-bootstrap.js").status_code,
            200,
        )
        self.assertEqual(self.client.get("/assets/version-check.js").status_code, 200)
        tombstone = self.client.get("/sw.js")
        self.assertEqual(tombstone.status_code, 200)
        self.assertIn("self.registration.unregister()", tombstone.text)
        self.assertIn("no-store", tombstone.headers["cache-control"])
        for path in ("/api/health", "/api/ready"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 503)
                self.assertEqual(response.json(), {"status": "setup_required"})

    def test_setup_head_matches_get_status_and_has_no_body(self):
        response = self.client.head("/setup")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"")
        self.assertIn("epub_browser_setup_nonce=", response.headers["set-cookie"])

    def test_setup_submission_activates_pending_admin_and_enters_library(self):
        nonce = self._setup_nonce()
        response = self.client.post(
            "/setup",
            data={
                "setup_nonce": nonce,
                "username": "Owner",
                "password": "setup-secret",
                "password_confirmation": "setup-secret",
                "locale": "en",
            },
            headers={
                "Origin": "http://testserver",
                "Sec-Fetch-Site": "same-origin",
            },
        )

        user = self.store.get_user_by_username("owner")
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/")
        self.assertIn("epub_browser_session=", response.headers["set-cookie"])
        self.assertNotIn("epub_browser_setup_nonce", self.client.cookies)
        self.assertNotIn("setup-secret", response.text)
        self.assertEqual(user.user_id, self.pending.user_id)
        self.assertTrue(user.enabled)
        self.assertTrue(self.store.has_administrator())
        self.assertEqual(self.client.get("/").text, "private library content")

    def test_setup_rejects_invalid_form_without_echoing_password(self):
        nonce = self._setup_nonce(path="/setup?lang=zh-CN")
        response = self.client.post(
            "/setup",
            data={
                "setup_nonce": nonce,
                "username": "Owner",
                "password": "do-not-echo-this",
                "password_confirmation": "different",
                "locale": "zh-CN",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('<html lang="zh-CN">', response.text)
        self.assertIn("密码与确认密码不一致。", response.text)
        self.assertNotIn("do-not-echo-this", response.text)
        self.assertFalse(self.store.has_administrator())

    def test_setup_rejects_cross_origin_form_even_with_valid_nonce(self):
        for headers in (
            {
                "Origin": "https://attacker.example",
                "Sec-Fetch-Site": "same-origin",
            },
            {
                "Origin": "http://testserver",
                "Sec-Fetch-Site": "cross-site",
            },
        ):
            with self.subTest(headers=headers):
                nonce = self._setup_nonce()
                response = self.client.post(
                    "/setup",
                    data={
                        "setup_nonce": nonce,
                        "username": "owner",
                        "password": "secret",
                        "password_confirmation": "secret",
                    },
                    headers=headers,
                )
                self.assertEqual(response.status_code, 403)
                self.assertEqual(
                    response.json()["code"],
                    "invalid_setup_request",
                )
        self.assertFalse(self.store.has_administrator())

    def test_cross_origin_rejection_does_not_reveal_setup_completion(self):
        nonce = self._setup_nonce()
        payload = {
            "setup_nonce": nonce,
            "username": "owner",
            "password": "secret",
            "password_confirmation": "secret",
        }
        hostile_headers = {
            "Origin": "https://attacker.example",
            "Sec-Fetch-Site": "cross-site",
        }
        before = self.client.post(
            "/setup",
            data=payload,
            headers=hostile_headers,
        )
        completed = self.client.post("/setup", data=payload)
        with TestClient(self.app, follow_redirects=False) as anonymous:
            after = anonymous.post(
                "/setup",
                data=payload,
                headers=hostile_headers,
            )

        self.assertEqual(completed.status_code, 303)
        self.assertEqual(before.status_code, after.status_code)
        self.assertEqual(before.json(), after.json())

    def test_setup_rejects_missing_or_mismatched_nonce(self):
        valid_nonce = self._setup_nonce()
        for nonce in (None, valid_nonce + "wrong"):
            with self.subTest(nonce=nonce):
                data = {
                    "username": "owner",
                    "password": "secret",
                    "password_confirmation": "secret",
                }
                if nonce is not None:
                    data["setup_nonce"] = nonce
                response = self.client.post("/setup", data=data)
                self.assertEqual(response.status_code, 403)
                self.assertEqual(
                    response.json()["code"],
                    "invalid_setup_request",
                )
        self.assertFalse(self.store.has_administrator())

    def test_concurrent_setup_submissions_allow_exactly_one_claim(self):
        barrier = threading.Barrier(2)

        def submit(username):
            with TestClient(self.app, follow_redirects=False) as client:
                nonce = self._setup_nonce(client)
                barrier.wait(timeout=5)
                response = client.post(
                    "/setup",
                    data={
                        "setup_nonce": nonce,
                        "username": username,
                        "password": "secret-" + username,
                        "password_confirmation": "secret-" + username,
                    },
                )
                return response.status_code, response.headers.get("location")

        # Each TestClient owns an event loop. Starting the second lifespan must
        # not replace the first worker's asyncio.Event and leave an unhandled
        # cross-loop task failure behind during shutdown.
        with _assert_no_error_logs(self, "asyncio"):
            with ThreadPoolExecutor(max_workers=2) as executor:
                results = tuple(executor.map(submit, ("first", "second")))

        self.assertEqual(sorted(results), [(303, "/"), (303, "/login")])
        users = self.store.list_users()
        self.assertEqual(len(users), 1)
        self.assertEqual(users[0].user_id, self.pending.user_id)
        self.assertTrue(users[0].enabled)
        with sqlite3.connect(self.store.database_path) as connection:
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM sessions").fetchone()[0],
                1,
            )

    def test_trusted_proxy_identity_cannot_claim_pending_setup(self):
        proxy_config = AuthConfig.from_values(
            ["10.0.0.0/8"],
            "X-Remote-User",
            "https://sso.example",
        )
        app = create_app(
            self.public,
            state_store=self.store,
            auth_service=AuthService(self.store, proxy_config),
        )
        with TestClient(
            app,
            client=("10.1.2.3", 4321),
            follow_redirects=False,
        ) as client:
            response = client.get(
                "/",
                headers={"X-Remote-User": "attacker"},
            )

        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/setup")
        self.assertNotIn("set-cookie", response.headers)
        self.assertFalse(self.store.has_administrator())


class ServerAuthBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        public = Path(self.directory.name)
        (public / "index.html").write_text("library", encoding="utf-8")
        (public / "assets").mkdir()
        (public / "assets" / "reader.js").write_text(
            "console.log('reader')",
            encoding="utf-8",
        )
        (public / "assets" / "auth.js").write_text(
            "console.log('login')",
            encoding="utf-8",
        )
        (public / "book" / "id").mkdir(parents=True)
        (public / "book" / "id" / "chapter_0.html").write_text(
            "chapter",
            encoding="utf-8",
        )
        self.store = StateStore(public / "epub-browser.db")
        self.principal = self.store.initialize(
            bootstrap=BootstrapCredentials("alice", "secret")
        )
        self.store.resolve_book(
            public / "book.epub",
            None,
            "book-fingerprint",
            {"title": "Book"},
            preferred_book_id="book",
        )
        self.auth_config = AuthConfig.from_values([], None, None)
        self.auth_service = AuthService(self.store, self.auth_config)
        self.app = create_app(
            public,
            state_store=self.store,
            auth_service=self.auth_service,
        )
        self.client = TestClient(self.app, follow_redirects=False)
        self.annotation = {
            "id": "a1",
            "book_hash": "book",
            "chapter_index": 1,
            "text": "note",
            "color": "#fff",
            "created_at": "2026-01-01",
            "updated_at": "2026-01-01",
        }

    def test_server_redirects_unauthenticated_html_and_rejects_api_static_and_sse(self):
        index = self.client.get("/?language=zh-CN")

        self.assertEqual(index.status_code, 303)
        self.assertEqual(index.headers["location"], "/login?next=%2F%3Flanguage%3Dzh-CN")
        api = self.client.get("/api/annotations/book")
        self.assertEqual(api.status_code, 401)
        self.assertEqual(
            api.json(),
            {"code": "authentication_required", "message": "Authentication required"},
        )
        self.assertEqual(self.client.get("/book/id/chapter_0.html").status_code, 403)
        self.assertEqual(self.client.get("/assets/reader.js").status_code, 403)
        self.assertEqual(self.client.get("/assets/auth.js").status_code, 200)
        self.assertEqual(self.client.get("/api/library-events").status_code, 401)

    def test_health_and_readiness_are_public_after_setup(self):
        health = self.client.get(
            "/api/health",
            headers={"Accept": "text/html"},
        )
        ready = self.client.get("/api/ready")

        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.json()["status"], "ok")
        self.assertEqual(health.json()["state"], "ready")
        self.assertEqual(health.headers["cache-control"], "no-cache")
        self.assertEqual(ready.status_code, 200)
        self.assertEqual(ready.json()["state"], "ready")
        self.assertEqual(ready.headers["cache-control"], "no-cache")

    def test_password_login_sets_session_and_requires_csrf_to_write(self):
        response = _json_login(
            self,
            self.client,
            "alice",
            "secret",
            next_path="/book/id/chapter_0.html",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["redirect"], "/book/id/chapter_0.html")
        cookie = response.headers["set-cookie"]
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=lax", cookie)
        session = self.client.get("/api/session")
        self.assertEqual(session.status_code, 200)
        self.assertEqual(session.headers["cache-control"], "private, no-cache")
        self.assertEqual(session.json()["user"]["username"], "alice")
        self.assertEqual(session.json()["user"]["id"], self.principal.user_id)
        self.assertEqual(
            self.client.post("/api/annotations/book", json=self.annotation).status_code,
            403,
        )
        csrf = session.json()["csrf_token"]
        csrf_response = self.client.get("/api/csrf")
        self.assertEqual(csrf_response.json(), {"csrf_token": csrf})
        self.assertEqual(
            csrf_response.headers["cache-control"],
            "private, no-cache",
        )
        created = self.client.post(
            "/api/annotations/book",
            json=self.annotation,
            headers={self.auth_config.csrf_header_name: csrf},
        )
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.headers["cache-control"], "private, no-cache")
        self.assertEqual(
            self.store.list_annotations(user_id=self.principal.user_id)[0]["id"],
            "a1",
        )

    def test_anonymous_login_requires_json_same_origin_source_and_strict_nonce(self):
        nonce = _anonymous_auth_nonce(self, self.client)
        valid_payload = {
            "username": "alice",
            "password": "secret",
            "next": "/book/id/chapter_0.html",
        }

        form = self.client.post(
            "/login",
            data={"username": "alice", "password": "secret"},
            headers={"X-EPUB-Browser-Auth-Nonce": nonce},
        )
        cross_site = self.client.post(
            "/login",
            json=valid_payload,
            headers={
                "X-EPUB-Browser-Auth-Nonce": nonce,
                "Origin": "https://attacker.example",
                "Sec-Fetch-Site": "cross-site",
            },
        )
        missing_nonce = self.client.post(
            "/login",
            json=valid_payload,
            headers={
                "Origin": "http://testserver",
                "Sec-Fetch-Site": "same-origin",
            },
        )
        oversized = self.client.post(
            "/login",
            content=json.dumps({**valid_payload, "padding": "x" * (64 * 1024)}),
            headers={
                "Content-Type": "application/json",
                "X-EPUB-Browser-Auth-Nonce": nonce,
                "Origin": "http://testserver",
                "Sec-Fetch-Site": "same-origin",
            },
        )

        self.assertEqual(form.status_code, 415)
        self.assertEqual(cross_site.status_code, 403)
        self.assertEqual(cross_site.json()["code"], "invalid_auth_request")
        self.assertEqual(missing_nonce.status_code, 403)
        self.assertEqual(missing_nonce.json()["code"], "invalid_auth_request")
        self.assertEqual(oversized.status_code, 413)
        self.assertEqual(self.client.get("/api/session").status_code, 401)

        logged_in = self.client.post(
            "/login",
            json=valid_payload,
            headers={
                "X-EPUB-Browser-Auth-Nonce": nonce,
                "Origin": "http://testserver",
                "Sec-Fetch-Site": "same-origin",
            },
        )
        self.assertEqual(logged_in.status_code, 200)
        self.assertEqual(logged_in.json()["redirect"], "/book/id/chapter_0.html")
        self.assertEqual(self.client.get("/api/session").status_code, 200)

    def test_login_next_is_relative_and_logout_revokes_the_session(self):
        login_page = self.client.get("/login?next=https%3A%2F%2Fevil.example")
        self.assertEqual(login_page.status_code, 200)
        self.assertIn('id="loginForm"', login_page.text)
        encoded_backslash = self.client.get(
            "/login?next=%2F%255C%255Cevil.example"
        )
        self.assertIn('name="next" value="/"', encoded_backslash.text)

        logged_in = _json_login(self, self.client, "alice", "secret")
        self.assertEqual(logged_in.status_code, 200)
        self.assertEqual(logged_in.json()["redirect"], "/")
        csrf = self.client.get("/api/session").json()["csrf_token"]

        self.assertEqual(self.client.post("/logout").status_code, 403)
        logout = self.client.post(
            "/logout",
            headers={self.auth_config.csrf_header_name: csrf},
        )
        self.assertEqual(logout.status_code, 303)
        self.assertEqual(logout.headers["location"], "/login")
        self.assertEqual(self.client.get("/api/session").status_code, 401)

    def test_public_login_is_a_localized_surface_in_english_and_chinese(self):
        english = self.client.get('/login?lang=en&next=%2Fbook%2Fid%2Fchapter_0.html')
        chinese = self.client.get('/login?lang=zh-CN&next=%2Fbook%2Fid%2Fchapter_0.html')

        self.assertEqual(english.status_code, 200)
        self.assertEqual(chinese.status_code, 200)
        self.assertIn('<html lang="en">', english.text)
        self.assertIn('<html lang="zh-CN">', chinese.text)
        self.assertIn('<h1 data-i18n="account.signIn">Sign in</h1>', english.text)
        self.assertIn('<h1 data-i18n="account.signIn">登录</h1>', chinese.text)
        self.assertIn('id="loginForm"', english.text)
        self.assertIn('class="auth-page"', english.text)
        self.assertIn('class="auth-card login-card"', english.text)
        self.assertIn('href="/assets/account.css"', english.text)
        self.assertIn('href="/assets/theme.css"', english.text)
        self.assertIn('src="/assets/theme-bootstrap.js"', english.text)
        self.assertIn('src="/assets/version-check.js"', english.text)
        self.assertIn('data-id="eb-footer"', english.text)
        self.assertIn('data-current-version=', english.text)
        self.assertIn('data-i18n="footer.poweredBy"', english.text)
        self.assertIn('data-i18n="account.loginDescription"', english.text)
        self.assertNotIn('<style>', english.text)
        self.assertNotIn('id="associationForm"', english.text)
        self.assertIn('id="loginLocaleSelect"', english.text)
        self.assertIn('<option value="en" selected', english.text)
        self.assertIn('<option value="zh-CN" selected', chinese.text)
        self.assertIn('data-i18n="account.username">Username', english.text)
        self.assertIn('data-i18n="account.username">用户名', chinese.text)
        self.assertIn('src="/assets/i18n.js"', english.text)
        self.assertIn('window.EpubBrowserI18n.init()', english.text)
        self.assertIn('i18n.setLocale(localeSelect.value)', english.text)
        self.assertGreater(
            english.text.index('id="loginError"'),
            english.text.index('id="loginForm"'),
        )
        self.assertIn("setLoginError(true)", english.text)
        self.assertIn(
            'name="next" value="/book/id/chapter_0.html"',
            chinese.text,
        )
        self.assertEqual(self.client.get('/assets/i18n.js').status_code, 200)
        stylesheet = self.client.get('/assets/account.css')
        self.assertEqual(stylesheet.status_code, 200)
        self.assertIn('text/css', stylesheet.headers['content-type'])

    def test_cookie_secure_flag_follows_explicit_auth_configuration(self):
        secure_config = AuthConfig.from_values(
            [],
            None,
            None,
            cookie_secure=True,
        )
        secure_app = create_app(
            self.directory.name,
            state_store=self.store,
            auth_service=AuthService(self.store, secure_config),
        )
        secure_client = TestClient(
            secure_app,
            base_url="https://testserver",
            follow_redirects=False,
        )
        self.addCleanup(secure_client.close)

        response = _json_login(self, secure_client, "alice", "secret")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Secure", response.headers["set-cookie"])
        self.assertEqual(secure_client.get("/api/session").status_code, 200)

    def test_authenticated_login_requires_csrf_before_replacing_the_session(self):
        first_login = _json_login(self, self.client, "alice", "secret")
        self.assertEqual(first_login.status_code, 200)
        original_session = self.client.cookies.get("epub_browser_session")
        csrf = self.client.get("/api/session").json()["csrf_token"]

        denied = self.client.post(
            "/login",
            json={"username": "alice", "password": "secret", "next": "/"},
        )

        self.assertEqual(denied.status_code, 403)
        self.assertEqual(denied.json()["code"], "csrf_required")
        self.assertEqual(denied.headers["cache-control"], "private, no-cache")
        self.assertEqual(
            self.client.cookies.get("epub_browser_session"),
            original_session,
        )

        replaced = self.client.post(
            "/login",
            json={"username": "alice", "password": "secret", "next": "/"},
            headers={self.auth_config.csrf_header_name: csrf},
        )

        self.assertEqual(replaced.status_code, 200)
        self.assertNotEqual(
            self.client.cookies.get("epub_browser_session"),
            original_session,
        )

        with TestClient(self.app, follow_redirects=False) as replaced_client:
            replaced_client.cookies.set("epub_browser_session", original_session)
            self.assertEqual(
                replaced_client.get("/api/session").status_code,
                401,
            )

    def test_authenticated_unhandled_error_is_private_and_generic(self):
        class FailingRuntimeStatus:
            def is_ready(self):
                return True

            def snapshot(self):
                raise RuntimeError("sensitive runtime detail")

        failing_app = create_app(
            self.directory.name,
            state_store=self.store,
            auth_service=self.auth_service,
            status=FailingRuntimeStatus(),
        )
        client = TestClient(
            failing_app,
            follow_redirects=False,
            raise_server_exceptions=False,
        )
        self.addCleanup(client.close)
        self.assertEqual(
            _json_login(self, client, "alice", "secret").status_code,
            200,
        )

        failed = client.get("/api/health")

        self.assertEqual(failed.status_code, 500)
        self.assertEqual(
            failed.headers.get("cache-control"),
            "private, no-cache",
        )
        self.assertEqual(
            failed.json(),
            {"code": "server_error", "message": "Internal server error"},
        )
        self.assertNotIn("sensitive runtime detail", failed.text)


class ProxyAssociationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        public = Path(self.directory.name)
        (public / "index.html").write_text("library", encoding="utf-8")
        self.store = StateStore(public / "epub-browser.db")
        self.alice = self.store.initialize(
            bootstrap=BootstrapCredentials("alice", "secret")
        )
        config = AuthConfig.from_values(
            ["10.0.0.0/8"],
            "X-Remote-User",
            "https://sso.example",
            "X-Remote-Name",
        )
        self.app = create_app(
            public,
            state_store=self.store,
            auth_service=AuthService(self.store, config),
        )
        self.proxy_client = TestClient(
            self.app,
            client=("10.1.2.3", 50000),
            headers={
                "X-Remote-User": "subject-alice",
                "X-Remote-Name": "Alice Example",
            },
            follow_redirects=False,
        )
        self.addCleanup(self.proxy_client.close)

    def test_unknown_trusted_proxy_identity_must_prove_existing_password_before_linking(self):
        response = self.proxy_client.get("/")
        self.assertEqual(response.status_code, 303)

        nonce = _anonymous_auth_nonce(self, self.proxy_client)
        source_headers = {
            "X-EPUB-Browser-Auth-Nonce": nonce,
            "Origin": "http://testserver",
            "Sec-Fetch-Site": "same-origin",
        }

        rejected = self.proxy_client.post(
            "/api/identity/link",
            json={"username": "alice", "password": "wrong"},
            headers=source_headers,
        )
        self.assertEqual(rejected.status_code, 401)
        self.assertIsNone(
            self.store.get_identity("https://sso.example", "subject-alice")
        )

        linked = self.proxy_client.post(
            "/api/identity/link",
            json={"username": "alice", "password": "secret"},
            headers=source_headers,
        )

        self.assertEqual(linked.status_code, 201)
        self.assertEqual(
            self.store.get_identity(
                "https://sso.example",
                "subject-alice",
            ).user_id,
            self.alice.user_id,
        )
        self.assertEqual(
            self.proxy_client.get("/api/session").json()["user"]["username"],
            "alice",
        )

    def test_anonymous_proxy_link_rejects_cross_site_missing_nonce_and_non_json(self):
        nonce = _anonymous_auth_nonce(self, self.proxy_client)
        payload = {"username": "alice", "password": "secret"}

        non_json = self.proxy_client.post(
            "/api/identity/link",
            data=payload,
            headers={"X-EPUB-Browser-Auth-Nonce": nonce},
        )
        cross_site = self.proxy_client.post(
            "/api/identity/link",
            json=payload,
            headers={
                "X-EPUB-Browser-Auth-Nonce": nonce,
                "Origin": "https://attacker.example",
                "Sec-Fetch-Site": "cross-site",
            },
        )
        missing_nonce = self.proxy_client.post(
            "/api/identity/link",
            json=payload,
            headers={
                "Origin": "http://testserver",
                "Sec-Fetch-Site": "same-origin",
            },
        )

        self.assertEqual(non_json.status_code, 415)
        self.assertEqual(cross_site.status_code, 403)
        self.assertEqual(cross_site.json()["code"], "invalid_auth_request")
        self.assertEqual(missing_nonce.status_code, 403)
        self.assertIsNone(
            self.store.get_identity("https://sso.example", "subject-alice")
        )

    def test_link_requires_an_unrecognized_assertion_from_a_trusted_peer(self):
        untrusted = TestClient(
            self.app,
            client=("203.0.113.8", 50000),
            headers={"X-Remote-User": "forged-subject"},
        )
        self.addCleanup(untrusted.close)

        nonce = _anonymous_auth_nonce(self, untrusted)
        response = untrusted.post(
            "/api/identity/link",
            json={"username": "alice", "password": "secret"},
            headers={
                "X-EPUB-Browser-Auth-Nonce": nonce,
                "Origin": "http://testserver",
                "Sec-Fetch-Site": "same-origin",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertIsNone(
            self.store.get_identity("https://sso.example", "forged-subject")
        )

    def test_linked_trusted_proxy_identity_creates_a_local_session(self):
        self.store.create_identity(
            "https://sso.example",
            "subject-alice",
            self.alice.user_id,
            "Alice Example",
        )

        response = self.proxy_client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("epub_browser_session=", response.headers["set-cookie"])
        self.assertEqual(
            self.proxy_client.get("/api/session").json()["user"]["username"],
            "alice",
        )


class AdminAccountTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        public = Path(self.directory.name)
        (public / "index.html").write_text("library", encoding="utf-8")
        self.store = StateStore(public / "epub-browser.db")
        self.admin = self.store.initialize(
            bootstrap=BootstrapCredentials("admin", "admin-secret")
        )
        self.member = self.store.create_user(
            "member",
            hash_password("member-secret"),
        )
        config = AuthConfig.from_values([], None, None)
        self.app = create_app(
            public,
            state_store=self.store,
            auth_service=AuthService(self.store, config),
        )
        self.admin_client = self._login("admin", "admin-secret")
        self.member_client = self._login("member", "member-secret")

    def _login(self, username, password):
        client = TestClient(self.app, follow_redirects=False)
        self.addCleanup(client.close)
        login = _json_login(self, client, username, password)
        self.assertEqual(login.status_code, 200)
        session = client.get("/api/session")
        self.assertEqual(session.status_code, 200)
        client.headers["X-CSRF-Token"] = session.json()["csrf_token"]
        return client

    def _create_failed_ai_job(self, job_id="failed-admin-job"):
        book = self.store.resolve_book(
            Path(self.directory.name) / (job_id + ".epub"),
            "urn:test:" + job_id,
            "fingerprint-" + job_id,
            {"title": "Administrative AI Job"},
        )
        self.store.create_ai_job(
            job_id,
            self.member.user_id,
            "cache-" + job_id,
            book_id=book.book_id,
            request_payload={
                "scope": "chapter",
                "book_id": book.book_id,
                "chapter_index": 0,
                "mode": "chapter",
                "language": "en",
                "reading_boundary": 0,
                "provider_base_url": "https://provider.example/private",
                "source_path": "/private/epub/source.epub",
                "private_note": "PRIVATE_REPLAY_SENTINEL",
            },
        )
        self.assertTrue(self.store.start_ai_job(job_id))
        self.assertTrue(
            self.store.finish_ai_job(job_id, error_code="ai_generation_failed")
        )
        return book, job_id

    def test_admin_lists_paginated_ai_jobs_without_private_payload(self):
        book, _job_id = self._create_failed_ai_job()
        anonymous = TestClient(self.app, follow_redirects=False)
        self.addCleanup(anonymous.close)

        anonymous_denied = anonymous.get("/api/admin/ai/jobs")
        denied = self.member_client.get("/api/admin/ai/jobs")
        listed = self.admin_client.get(
            "/api/admin/ai/jobs?status=failed&page=1&page_size=10"
        )
        empty = self.admin_client.get(
            "/api/admin/ai/jobs?status=queued&page=1&page_size=10"
        )

        self.assertEqual(anonymous_denied.status_code, 401)
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(
            listed.json()["pagination"],
            {"page": 1, "page_size": 10, "total": 1, "total_pages": 1},
        )
        self.assertEqual(listed.json()["jobs"][0]["book_id"], book.book_id)
        self.assertEqual(listed.json()["jobs"][0]["scope"], "chapter")
        self.assertNotIn("PRIVATE_REPLAY_SENTINEL", listed.text)
        self.assertNotIn("request_json", listed.text)
        self.assertNotIn("provider_base_url", listed.text)
        self.assertNotIn("/private/epub/source.epub", listed.text)
        self.assertEqual(empty.status_code, 200)
        self.assertEqual(empty.json()["jobs"], [])
        self.assertEqual(empty.json()["pagination"]["total_pages"], 0)

    def test_admin_ai_job_api_sanitizes_malformed_allowlisted_values(self):
        _book, job_id = self._create_failed_ai_job("malformed-admin-api")
        sentinel = "PRIVATE_ADMIN_API_SENTINEL"
        with self.store._connection() as connection:
            connection.execute(
                "UPDATE ai_reading_jobs SET request_json = ?, error_code = ? WHERE id = ?",
                (
                    json.dumps({
                        "scope": [sentinel],
                        "book_id": _book.book_id,
                        "chapter_index": {"exception": sentinel},
                        "mode": {"source_path": "/private/" + sentinel},
                        "language": {"api_key": sentinel},
                        "reading_boundary": "/private/" + sentinel,
                    }),
                    "chapter_not_found:/private/" + sentinel,
                    job_id,
                ),
            )

        response = self.admin_client.get("/api/admin/ai/jobs?status=failed")

        self.assertEqual(response.status_code, 200)
        self.assertNotIn(sentinel, response.text)
        job = response.json()["jobs"][0]
        self.assertFalse(job["retryable"])
        self.assertIsNone(job["error_code"])
        for field in ("scope", "mode", "language", "chapter_index", "reading_boundary"):
            self.assertIsNone(job[field])

    def test_admin_ai_job_query_validation(self):
        invalid_queries = (
            "page=0",
            "page=%2B1",
            "page=-1",
            "page=true",
            "page=",
            "page=one",
            "page=999999999999999999999999999999999999999999",
            "page_size=0",
            "page_size=101",
            "page_size=true",
            "page_size=",
            "status=",
            "status=unknown",
        )

        for query in invalid_queries:
            with self.subTest(query=query):
                response = self.admin_client.get("/api/admin/ai/jobs?" + query)
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json()["code"], "invalid_ai_job_query")

    def test_admin_retries_failed_ai_job_with_csrf(self):
        _book, source_job_id = self._create_failed_ai_job("failed job")
        retry_url = "/api/admin/ai/jobs/" + quote(source_job_id, safe="") + "/retry"
        queued = {
            "status": "queued",
            "cached": False,
            "shared": False,
            "job": {"id": "new-job", "status": "queued"},
        }
        cached = {
            "status": "complete",
            "cached": True,
            "shared": False,
            "job": {"id": "cached-job", "status": "complete"},
        }
        shared = {
            "status": "queued",
            "cached": False,
            "shared": True,
            "job": {"id": "active-job", "status": "queued"},
        }
        completed = {
            "status": "complete",
            "cached": False,
            "shared": False,
            "job": {"id": "completed-job", "status": "complete"},
        }

        with mock.patch(
            "epub_browser.server.AIReadingService.retry_job",
            new_callable=mock.AsyncMock,
            return_value=queued,
        ) as retry_job:
            response = self.admin_client.post(retry_url)
            self.assertEqual(response.status_code, 202)
            self.assertEqual(response.json(), queued)
            retry_job.assert_awaited_once_with(self.admin, source_job_id)

        for result in (cached, shared, completed):
            with self.subTest(result=result):
                with mock.patch(
                    "epub_browser.server.AIReadingService.retry_job",
                    new_callable=mock.AsyncMock,
                    return_value=result,
                ):
                    response = self.admin_client.post(retry_url)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json(), result)

        with mock.patch(
            "epub_browser.server.AIReadingService.retry_job",
            new_callable=mock.AsyncMock,
        ) as retry_job:
            member_denied = self.member_client.post(retry_url)
            self.assertEqual(member_denied.status_code, 403)
            retry_job.assert_not_awaited()

            csrf_token = self.admin_client.headers.pop("X-CSRF-Token")
            try:
                csrf_denied = self.admin_client.post(retry_url)
            finally:
                self.admin_client.headers["X-CSRF-Token"] = csrf_token
            self.assertEqual(csrf_denied.status_code, 403)
            self.assertEqual(csrf_denied.json()["code"], "csrf_required")
            retry_job.assert_not_awaited()

        error_statuses = {
            "ai_job_not_retryable": 400,
            "ai_not_authorized": 403,
            "ai_job_not_found": 404,
            "book_not_found": 404,
            "chapter_not_found": 404,
            "ai_job_retry_conflict": 409,
            "ai_disabled": 503,
            "source_unavailable": 503,
            "ai_template_unavailable": 503,
        }
        for code, expected_status in error_statuses.items():
            with self.subTest(code=code):
                with mock.patch(
                    "epub_browser.server.AIReadingService.retry_job",
                    new_callable=mock.AsyncMock,
                    side_effect=AIReadingError(code),
                ):
                    response = self.admin_client.post(retry_url)
                self.assertEqual(response.status_code, expected_status)
                self.assertEqual(response.json()["code"], code)

    def test_admin_retry_route_preserves_encoded_slash_job_ids(self):
        queued = {
            "status": "queued",
            "cached": False,
            "shared": False,
            "job": {"id": "new-job", "status": "queued"},
        }
        with mock.patch(
            "epub_browser.server.AIReadingService.retry_job",
            new_callable=mock.AsyncMock,
            return_value=queued,
        ) as retry_job:
            slash = self.admin_client.post(
                "/api/admin/ai/jobs/failed%2Fjob/retry"
            )
            multiple_slashes = self.admin_client.post(
                "/api/admin/ai/jobs/failed%2F%2Fjob/retry"
            )
            empty = self.admin_client.post("/api/admin/ai/jobs//retry")

        self.assertEqual(slash.status_code, 202)
        self.assertEqual(multiple_slashes.status_code, 202)
        self.assertEqual(empty.status_code, 404)
        retry_job.assert_has_awaits([
            mock.call(self.admin, "failed/job"),
            mock.call(self.admin, "failed//job"),
        ])
        self.assertEqual(retry_job.await_count, 2)
        self.assertEqual(self.admin_client.get("/api/admin/ai/jobs").status_code, 200)

    def test_admin_disables_member_and_revokes_all_member_sessions(self):
        second_member_client = self._login("member", "member-secret")

        response = self.admin_client.put(
            "/api/admin/users/member",
            json={"enabled": False},
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["user"]["enabled"])
        self.assertEqual(self.member_client.get("/api/session").status_code, 401)
        self.assertEqual(
            second_member_client.get("/api/session").status_code,
            401,
        )

    def test_last_enabled_admin_cannot_be_disabled_or_demoted(self):
        disabled = self.admin_client.put(
            "/api/admin/users/admin",
            json={"enabled": False},
        )
        demoted = self.admin_client.put(
            "/api/admin/users/admin",
            json={"role": "member"},
        )

        self.assertEqual(disabled.status_code, 409)
        self.assertEqual(demoted.status_code, 409)
        self.assertTrue(self.store.get_user_by_username("admin").enabled)
        self.assertEqual(self.store.get_user_by_username("admin").role, "admin")

    def test_member_cannot_call_administrator_routes(self):
        for method, path, body in (
            ("get", "/api/admin/users", None),
            (
                "post",
                "/api/admin/users",
                {"username": "other", "password": "secret"},
            ),
            ("put", "/api/admin/users/member", {"enabled": False}),
            (
                "put",
                "/api/admin/users/member/password",
                {"password": "new-secret"},
            ),
        ):
            with self.subTest(method=method, path=path):
                if body is None:
                    response = getattr(self.member_client, method)(path)
                else:
                    response = getattr(self.member_client, method)(path, json=body)
                self.assertEqual(response.status_code, 403)

    def test_admin_manages_private_ai_configuration_and_member_access(self):
        initial = self.admin_client.get("/api/admin/ai/settings")
        saved = self.admin_client.put(
            "/api/admin/ai/settings",
            json={
                "enabled": True,
                "base_url": "https://provider.example/v1",
                "api_key": "never-return-this",
                "model": "reader-model",
                "timeout_seconds": 30,
                "max_concurrency": 2,
                "daily_limit": 7,
            },
        )
        granted = self.admin_client.put(
            "/api/admin/ai/users/" + self.member.user_id,
            json={"enabled": True, "daily_limit": 3},
        )
        member_status = self.member_client.get("/api/ai/status")

        self.assertFalse(initial.json()["settings"]["enabled"])
        self.assertEqual(saved.status_code, 200)
        self.assertNotIn("api_key", saved.json()["settings"])
        self.assertTrue(saved.json()["settings"]["api_key_configured"])
        self.assertEqual(granted.json()["access"], {"enabled": True, "daily_limit": 3})
        self.assertEqual(member_status.json(), {"enabled": True, "authorized": True, "daily_limit": 3})
        self.assertEqual(
            self.member_client.get("/api/admin/ai/settings").status_code,
            403,
        )

    def test_ai_reading_library_lists_retained_shared_results_for_visible_books(self):
        visible = self.store.resolve_book(
            Path(self.directory.name) / "visible.epub", "urn:test:visible", "visible-fingerprint",
            {"title": "Visible book", "authors": ["A Reader"], "cover": "resources/cover.jpg"},
        )
        restricted = self.store.resolve_book(
            Path(self.directory.name) / "restricted.epub", "urn:test:restricted", "restricted-fingerprint",
            {"title": "Restricted book", "authors": ["Private Author"]},
        )
        self.store.set_book_visibility(restricted.book_id, "restricted")
        visible_output = Path(self.directory.name) / "book" / visible.book_id
        content_output = visible_output / "content"
        content_output.mkdir(parents=True)
        (content_output / "toc.json").write_text(
            json.dumps([{"chapter_index": 0, "title": "Opening chapter"}]),
            encoding="utf-8",
        )
        for book, key in ((visible, "visible-layer"), (restricted, "restricted-layer")):
            self.store.store_ai_reading_result(
                cache_key=key, book_id=book.book_id, chapter_index=0, scope="chapter",
                mode="chapter", profile="auto", config_revision=1,
                content={"quick": {"title": "Chapter guide", "summary": "A shared guide"}},
                created_by_user_id=self.admin.user_id, template_id="chapter-learning-layer",
                template_version=5, language="en",
            )
        # The older result deliberately shares a cache key with the current
        # result. It remains a usable shared reading and must not vanish from
        # the AI-reading library merely because it is no longer the cache head.
        self.store.store_ai_reading_result(
            cache_key="visible-layer", book_id=visible.book_id, chapter_index=0,
            scope="chapter", mode="chapter", profile="auto", config_revision=0,
            content={"quick": {"title": "Earlier guide", "summary": "Still useful"}},
            created_by_user_id=self.admin.user_id, template_id="legacy",
            template_version=0, language="en",
        )

        member = self.member_client.get("/api/ai/library")
        admin = self.admin_client.get("/api/ai/library")

        self.assertEqual(member.status_code, 200)
        self.assertEqual([book["book_id"] for book in member.json()["books"]], [visible.book_id])
        self.assertEqual(len(member.json()["books"][0]["results"]), 2)
        self.assertTrue(all(result["chapter_index"] == 0 for result in member.json()["books"][0]["results"]))
        self.assertTrue(all(result["chapter_title"] == "Opening chapter" for result in member.json()["books"][0]["results"]))
        self.assertEqual(member.json()["books"][0]["cover"], f"/book/{visible.book_id}/resources/cover.jpg")
        self.assertEqual(
            {book["book_id"] for book in admin.json()["books"]},
            {visible.book_id, restricted.book_id},
        )

    def test_ai_reading_result_deletion_is_admin_or_generator_only(self):
        book = self.store.resolve_book(
            Path(self.directory.name) / "deletable.epub", "urn:test:deletable", "deletable",
            {"title": "Deletable"},
        )
        admin_result = self.store.store_ai_reading_result(
            cache_key="admin-layer", book_id=book.book_id, chapter_index=0,
            scope="chapter", mode="chapter", profile="auto", config_revision=1,
            content={"quick": {"title": "Admin"}}, created_by_user_id=self.admin.user_id,
        )
        member_result = self.store.store_ai_reading_result(
            cache_key="member-layer", book_id=book.book_id, chapter_index=1,
            scope="chapter", mode="chapter", profile="auto", config_revision=1,
            content={"quick": {"title": "Member"}}, created_by_user_id=self.member.user_id,
        )

        denied = self.member_client.delete("/api/ai/results/" + admin_result["id"])
        deleted_own = self.member_client.delete("/api/ai/results/" + member_result["id"])
        deleted_other = self.admin_client.delete("/api/ai/results/" + admin_result["id"])

        self.assertEqual(denied.status_code, 403)
        self.assertEqual(deleted_own.json(), {"deleted": member_result["id"]})
        self.assertEqual(deleted_other.json(), {"deleted": admin_result["id"]})

    def test_authorized_member_can_poll_a_shared_ai_generation_job(self):
        book = self.store.resolve_book(
            Path(self.directory.name) / "shared-job.epub",
            "urn:test:shared-job", "shared-job-fingerprint", {"title": "Book"},
        )
        self.store.create_ai_job(
            "shared-generation", self.admin.user_id, "chapter:shared", book_id=book.book_id,
        )

        response = self.member_client.get("/api/ai/jobs/shared-generation")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["job"]["book_id"], book.book_id)

    def test_ai_job_events_emit_durable_terminal_state_with_sse_headers(self):
        book = self.store.resolve_book(
            Path(self.directory.name) / "shared-events.epub",
            "urn:test:shared-events", "shared-events-fingerprint", {"title": "Book"},
        )
        self.store.create_ai_job(
            "shared-events", self.admin.user_id, "chapter:events", book_id=book.book_id,
        )
        self.assertTrue(self.store.start_ai_job("shared-events"))
        self.store.finish_ai_job("shared-events", error_code="provider_connection_failed")

        headers, chunk = _first_sse_chunk(
            self.app,
            "/api/ai/events?job_id=shared-events",
            self.member_client.cookies.get("epub_browser_session"),
        )

        self.assertEqual(headers["status"], 200)
        self.assertEqual(headers["content-type"], "text/event-stream; charset=utf-8")
        self.assertEqual(headers["cache-control"], "private, no-cache")
        self.assertEqual(headers["x-accel-buffering"], "no")
        self.assertIn("event: job", chunk)
        payload = json.loads(chunk.split("data: ", 1)[1])
        self.assertEqual(payload["job"]["status"], "failed")
        self.assertEqual(payload["job"]["error_code"], "provider_connection_failed")

    def test_admin_book_index_is_lightweight_and_private(self):
        source = Path(self.directory.name) / "private-library-source.epub"
        book = self.store.resolve_book(
            source,
            "urn:test:admin-index",
            "admin-index-fingerprint",
            {
                "title": "Indexed book",
                "authors": ["Index Author"],
                "tags": ["EPUB Tag"],
                "private_metadata": "PRIVATE_METADATA_SENTINEL",
            },
            preferred_book_id="admin-index-book",
        )
        tag = self.store.create_ai_tag("Assigned Tag")
        self.store.set_book_visibility(book.book_id, "restricted")
        self.store.grant_book_access(book.book_id, self.member.user_id)
        self.store.replace_book_ai_tags(book.book_id, [tag["id"]])
        self.store.set_book_ai_profile(book.book_id, "technical")

        index = self.admin_client.get("/api/admin/books/index")
        member_denied = self.member_client.get("/api/admin/books/index")
        legacy = self.admin_client.get("/api/admin/books")

        self.assertEqual(index.status_code, 200)
        indexed = next(
            item for item in index.json()["books"] if item["id"] == book.book_id
        )
        self.assertEqual(indexed["title"], "Indexed book")
        self.assertEqual(indexed["authors"], ["Index Author"])
        self.assertEqual(indexed["epub_tags"], ["EPUB Tag"])
        self.assertEqual(indexed["grant_count"], 1)
        self.assertEqual(indexed["ai_profile"], "technical")
        self.assertEqual(indexed["ai_tags"], [{"id": tag["id"], "name": "Assigned Tag"}])
        self.assertNotIn("source_path", index.text)
        self.assertNotIn("metadata_json", index.text)
        self.assertNotIn(str(source), index.text)
        self.assertNotIn("PRIVATE_METADATA_SENTINEL", index.text)
        self.assertEqual(member_denied.status_code, 403)
        self.assertEqual(set(legacy.json()), {"books"})
        legacy_book = next(
            item for item in legacy.json()["books"] if item["id"] == book.book_id
        )
        self.assertEqual(legacy_book["grants"], [self.member.user_id])

    def test_admin_gets_one_book_detail(self):
        source = Path(self.directory.name) / "private-detail-source.epub"
        book = self.store.resolve_book(
            source,
            "urn:test:admin-detail",
            "admin-detail-fingerprint",
            {
                "title": "Detailed book",
                "authors": ["Detail Author"],
                "tags": ["Original Tag"],
                "private_metadata": "PRIVATE_DETAIL_SENTINEL",
            },
            preferred_book_id="admin-detail-book",
        )
        inactive = self.store.resolve_book(
            Path(self.directory.name) / "inactive-detail.epub",
            "urn:test:inactive-detail",
            "inactive-detail-fingerprint",
            {"title": "Inactive private title"},
            preferred_book_id="inactive-detail-book",
        )
        self.store.mark_missing(inactive.book_id)
        tag = self.store.create_ai_tag("Detailed Tag")
        self.store.grant_book_access(book.book_id, self.member.user_id)
        self.store.replace_book_ai_tags(book.book_id, [tag["id"]])
        self.store.set_book_ai_profile(book.book_id, "fiction")

        detail = self.admin_client.get("/api/admin/books/" + book.book_id)
        missing = self.admin_client.get("/api/admin/books/missing-detail-book")
        inactive_response = self.admin_client.get(
            "/api/admin/books/" + inactive.book_id
        )
        member_denied = self.member_client.get(
            "/api/admin/books/" + book.book_id
        )

        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["book"]["id"], book.book_id)
        self.assertEqual(detail.json()["book"]["grants"], [self.member.user_id])
        self.assertEqual(detail.json()["book"]["ai_profile"], "fiction")
        self.assertEqual(
            detail.json()["book"]["ai_tags"],
            [{"id": tag["id"], "name": "Detailed Tag"}],
        )
        self.assertEqual(
            detail.json()["book"]["effective_tags"],
            ["Detailed Tag", "Original Tag"],
        )
        self.assertNotIn("source_path", detail.text)
        self.assertNotIn("metadata_json", detail.text)
        self.assertNotIn(str(source), detail.text)
        self.assertNotIn("PRIVATE_DETAIL_SENTINEL", detail.text)
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(inactive_response.status_code, 404)
        self.assertNotIn("Inactive private title", inactive_response.text)
        self.assertEqual(member_denied.status_code, 403)

    def test_admin_atomically_updates_complete_book_settings(self):
        book = self.store.resolve_book(
            Path(self.directory.name) / "atomic-settings.epub",
            "urn:test:atomic-settings",
            "atomic-settings-fingerprint",
            {"title": "Atomic settings", "authors": [], "tags": ["EPUB"]},
            preferred_book_id="atomic-settings-book",
        )
        inactive = self.store.resolve_book(
            Path(self.directory.name) / "inactive-settings.epub",
            "urn:test:inactive-settings",
            "inactive-settings-fingerprint",
            {"title": "Inactive settings"},
            preferred_book_id="inactive-settings-book",
        )
        self.store.mark_missing(inactive.book_id)
        tag = self.store.create_ai_tag("Technical")
        payload = {
            "visibility": "restricted",
            "user_ids": [self.member.user_id],
            "tag_ids": [tag["id"]],
            "profile": "technical",
        }

        saved = self.admin_client.put(
            "/api/admin/books/" + book.book_id + "/settings",
            json=payload,
        )

        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.json()["book"]["id"], book.book_id)
        self.assertEqual(saved.json()["book"]["visibility"], "restricted")
        self.assertEqual(saved.json()["book"]["grants"], [self.member.user_id])
        self.assertEqual(saved.json()["book"]["ai_profile"], "technical")
        self.assertEqual(saved.json()["summary"]["grant_count"], 1)
        self.assertEqual(saved.json()["summary"]["ai_profile"], "technical")
        self.assertEqual(
            saved.json()["summary"]["ai_tags"],
            [{"id": tag["id"], "name": "Technical"}],
        )

        invalid_payloads = (
            {key: value for key, value in payload.items() if key != "profile"},
            {**payload, "unexpected": True},
            {**payload, "visibility": True},
            {**payload, "visibility": "secret"},
            {**payload, "user_ids": "not-a-list"},
            {**payload, "user_ids": [True]},
            {**payload, "tag_ids": {}},
            {**payload, "tag_ids": [False]},
            {**payload, "profile": True},
            {**payload, "profile": "unsupported"},
            {**payload, "user_ids": ["unknown-private-user"]},
            {**payload, "tag_ids": ["unknown-private-tag"]},
        )
        for invalid_payload in invalid_payloads:
            with self.subTest(payload=invalid_payload):
                rejected = self.admin_client.put(
                    "/api/admin/books/" + book.book_id + "/settings",
                    json=invalid_payload,
                )
                self.assertEqual(rejected.status_code, 400)
                self.assertEqual(rejected.json()["code"], "invalid_book_settings")
                self.assertNotIn("unknown-private", rejected.text)

        unknown_book = self.admin_client.put(
            "/api/admin/books/missing-settings-book/settings",
            json=payload,
        )
        inactive_book = self.admin_client.put(
            "/api/admin/books/" + inactive.book_id + "/settings",
            json=payload,
        )
        member_denied = self.member_client.put(
            "/api/admin/books/" + book.book_id + "/settings",
            json=payload,
        )
        csrf_token = self.admin_client.headers.pop("X-CSRF-Token")
        try:
            csrf_denied = self.admin_client.put(
                "/api/admin/books/" + book.book_id + "/settings",
                json=payload,
            )
        finally:
            self.admin_client.headers["X-CSRF-Token"] = csrf_token

        self.assertEqual(unknown_book.status_code, 404)
        self.assertEqual(inactive_book.status_code, 404)
        self.assertEqual(member_denied.status_code, 403)
        self.assertEqual(csrf_denied.status_code, 403)
        self.assertEqual(csrf_denied.json()["code"], "csrf_required")

        with mock.patch.object(
            self.store,
            "update_admin_book_settings",
            side_effect=KeyError("PRIVATE_RESTRICTED_ENTITY_SENTINEL"),
        ):
            hidden_failure = self.admin_client.put(
                "/api/admin/books/" + book.book_id + "/settings",
                json=payload,
            )
        self.assertEqual(hidden_failure.status_code, 400)
        self.assertEqual(hidden_failure.json()["code"], "invalid_book_settings")
        self.assertNotIn("PRIVATE_RESTRICTED_ENTITY_SENTINEL", hidden_failure.text)

    def test_admin_book_routes_preserve_encoded_slash_ids_and_specific_suffixes(self):
        book = self.store.resolve_book(
            Path(self.directory.name) / "slash-id.epub",
            "urn:test:slash-id",
            "slash-id-fingerprint",
            {"title": "Slash ID", "authors": [], "tags": []},
            preferred_book_id="book/id",
        )
        payload = {
            "visibility": "restricted",
            "user_ids": [],
            "tag_ids": [],
            "profile": "general",
        }

        detail = self.admin_client.get("/api/admin/books/book%2Fid")
        settings = self.admin_client.put(
            "/api/admin/books/book%2Fid/settings",
            json=payload,
        )
        ai = self.admin_client.get("/api/admin/books/book%2Fid/ai")
        grants = self.admin_client.put(
            "/api/admin/books/book%2Fid/grants",
            json={"user_ids": []},
        )
        index = self.admin_client.get("/api/admin/books/index")
        collection = self.admin_client.get("/api/admin/books")
        empty_detail = self.admin_client.get("/api/admin/books/")
        empty_settings = self.admin_client.put(
            "/api/admin/books//settings",
            json=payload,
        )

        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["book"]["id"], book.book_id)
        self.assertEqual(settings.status_code, 200)
        self.assertEqual(settings.json()["book"]["id"], "book/id")
        self.assertEqual(ai.status_code, 200)
        self.assertEqual(ai.json()["profile"], "general")
        self.assertEqual(grants.status_code, 200)
        self.assertEqual(grants.json()["grants"]["book_id"], "book/id")
        self.assertEqual(index.status_code, 200)
        self.assertEqual(collection.status_code, 200)
        self.assertIn("book/id", {item["id"] for item in index.json()["books"]})
        self.assertIn("book/id", {item["id"] for item in collection.json()["books"]})
        self.assertEqual(empty_detail.status_code, 404)
        self.assertEqual(empty_settings.status_code, 404)

    def test_admin_book_raw_paths_disambiguate_encoded_reserved_suffix_ids(self):
        book_ids = (
            "tail",
            "tail/ai",
            "tail/settings",
            "tail/grants",
            "tail//ai",
            "literal%2Fai",
        )
        for index, book_id in enumerate(book_ids):
            self.store.resolve_book(
                Path(self.directory.name) / ("reserved-suffix-" + str(index) + ".epub"),
                "urn:test:reserved-suffix:" + str(index),
                "reserved-suffix-fingerprint-" + str(index),
                {"title": "Reserved suffix " + book_id, "authors": [], "tags": []},
                preferred_book_id=book_id,
            )
        tag = self.store.create_ai_tag("Reserved suffix tag")
        complete_settings = {
            "visibility": "restricted",
            "user_ids": [self.member.user_id],
            "tag_ids": [tag["id"]],
            "profile": "technical",
        }

        with mock.patch.object(
            self.store,
            "get_admin_book_detail",
            wraps=self.store.get_admin_book_detail,
        ) as get_detail, mock.patch.object(
            self.store,
            "set_book_visibility",
            wraps=self.store.set_book_visibility,
        ) as set_visibility, mock.patch.object(
            self.store,
            "update_admin_book_settings",
            wraps=self.store.update_admin_book_settings,
        ) as update_settings:
            encoded_details = {
                book_id: self.admin_client.get(
                    "/api/admin/books/" + quote(book_id, safe="")
                )
                for book_id in (
                    "tail/ai",
                    "tail/settings",
                    "tail/grants",
                    "tail//ai",
                    "literal%2Fai",
                )
            }
            encoded_legacy_settings = self.admin_client.put(
                "/api/admin/books/" + quote("tail/settings", safe=""),
                json={"visibility": "restricted"},
            )
            encoded_legacy_grants = self.admin_client.put(
                "/api/admin/books/" + quote("tail/grants", safe=""),
                json={"visibility": "restricted"},
            )
            encoded_atomic = self.admin_client.put(
                "/api/admin/books/" + quote("tail/ai", safe="") + "/settings",
                json=complete_settings,
            )

        for book_id, detail in encoded_details.items():
            with self.subTest(book_id=book_id):
                self.assertEqual(detail.status_code, 200)
                self.assertIn("book", detail.json())
                self.assertEqual(detail.json()["book"]["id"], book_id)
        self.assertEqual(encoded_legacy_settings.status_code, 200)
        self.assertEqual(encoded_legacy_settings.json()["book"]["id"], "tail/settings")
        self.assertEqual(encoded_legacy_grants.status_code, 200)
        self.assertEqual(encoded_legacy_grants.json()["book"]["id"], "tail/grants")
        self.assertEqual(encoded_atomic.status_code, 200)
        self.assertEqual(encoded_atomic.json()["book"]["id"], "tail/ai")
        for book_id in encoded_details:
            self.assertIn(mock.call(book_id), get_detail.call_args_list)
        set_visibility.assert_has_calls([
            mock.call("tail/settings", "restricted"),
            mock.call("tail/grants", "restricted"),
        ])
        self.assertIn(mock.call(
            "tail/ai",
            visibility="restricted",
            user_ids=[self.member.user_id],
            tag_ids=[tag["id"]],
            profile="technical",
        ), update_settings.call_args_list)

        literal_ai = self.admin_client.get("/api/admin/books/tail/ai")
        literal_grants = self.admin_client.put(
            "/api/admin/books/tail/grants",
            json={"user_ids": [self.member.user_id]},
        )
        literal_settings = self.admin_client.put(
            "/api/admin/books/tail/settings",
            json=complete_settings,
        )
        member_denied = self.member_client.get(
            "/api/admin/books/" + quote("tail/ai", safe="")
        )
        csrf_token = self.admin_client.headers.pop("X-CSRF-Token")
        try:
            csrf_denied = self.admin_client.put(
                "/api/admin/books/" + quote("tail/settings", safe=""),
                json={"visibility": "authenticated"},
            )
        finally:
            self.admin_client.headers["X-CSRF-Token"] = csrf_token

        self.assertEqual(literal_ai.status_code, 200)
        self.assertEqual(literal_ai.json()["profile"], "auto")
        self.assertEqual(literal_grants.status_code, 200)
        self.assertEqual(literal_grants.json()["grants"]["book_id"], "tail")
        self.assertEqual(literal_settings.status_code, 200)
        self.assertEqual(literal_settings.json()["book"]["id"], "tail")
        self.assertEqual(member_denied.status_code, 403)
        self.assertEqual(csrf_denied.status_code, 403)
        self.assertEqual(csrf_denied.json()["code"], "csrf_required")
        self.assertEqual(self.admin_client.get("/api/admin/books/index").status_code, 200)
        self.assertEqual(self.admin_client.get("/api/admin/books").status_code, 200)
        self.assertEqual(self.admin_client.get("/api/admin/books/").status_code, 404)
        self.assertEqual(
            self.admin_client.put(
                "/api/admin/books//settings",
                json=complete_settings,
            ).status_code,
            404,
        )

    def test_admin_book_settings_rejects_duplicate_top_level_keys_before_update(self):
        book = self.store.resolve_book(
            Path(self.directory.name) / "duplicate-settings-key.epub",
            "urn:test:duplicate-settings-key",
            "duplicate-settings-key-fingerprint",
            {"title": "Duplicate settings key", "authors": [], "tags": []},
            preferred_book_id="duplicate-settings-key",
        )
        tag = self.store.create_ai_tag("Duplicate key tag")
        payload = {
            "visibility": "restricted",
            "user_ids": [self.member.user_id],
            "tag_ids": [tag["id"]],
            "profile": "technical",
        }
        duplicate_body = json.dumps(payload)[:-1] + ',"profile":"fiction"}'
        before = self.store.get_admin_book_detail(book.book_id)

        with mock.patch.object(
            self.store,
            "update_admin_book_settings",
            wraps=self.store.update_admin_book_settings,
        ) as update_settings, mock.patch.object(
            self.store,
            "get_admin_book_detail",
            wraps=self.store.get_admin_book_detail,
        ) as get_detail:
            rejected = self.admin_client.put(
                "/api/admin/books/" + book.book_id + "/settings",
                content=duplicate_body,
                headers={"Content-Type": "application/json"},
            )

        self.assertEqual(rejected.status_code, 400)
        self.assertEqual(rejected.json()["code"], "invalid_book_settings")
        update_settings.assert_not_called()
        get_detail.assert_not_called()
        self.assertEqual(self.store.get_admin_book_detail(book.book_id), before)

    def test_admin_book_settings_body_is_bounded_and_duplicate_ids_are_normalized(self):
        book = self.store.resolve_book(
            Path(self.directory.name) / "bounded-settings.epub",
            "urn:test:bounded-settings",
            "bounded-settings-fingerprint",
            {"title": "Bounded settings", "authors": [], "tags": []},
            preferred_book_id="bounded-settings-book",
        )
        tag = self.store.create_ai_tag("Bounded settings tag")
        payload = {
            "visibility": "restricted",
            "user_ids": [self.member.user_id],
            "tag_ids": [tag["id"]],
            "profile": "general",
        }
        oversized_body = json.dumps(payload) + (" " * (64 * 1024))

        with mock.patch.object(
            self.store,
            "update_admin_book_settings",
            wraps=self.store.update_admin_book_settings,
        ) as update_settings, mock.patch.object(
            self.store,
            "get_admin_book_detail",
            wraps=self.store.get_admin_book_detail,
        ) as get_detail:
            oversized = self.admin_client.put(
                "/api/admin/books/" + book.book_id + "/settings",
                content=oversized_body,
                headers={"Content-Type": "application/json"},
            )
        self.assertEqual(oversized.status_code, 400)
        self.assertEqual(oversized.json()["code"], "invalid_book_settings")
        update_settings.assert_not_called()
        get_detail.assert_not_called()

        normalized = self.admin_client.put(
            "/api/admin/books/" + book.book_id + "/settings",
            json={
                **payload,
                "user_ids": [self.member.user_id, self.member.user_id],
                "tag_ids": [tag["id"], tag["id"]],
            },
        )
        self.assertEqual(normalized.status_code, 200)
        self.assertEqual(normalized.json()["book"]["grants"], [self.member.user_id])
        self.assertEqual(
            normalized.json()["book"]["ai_tags"],
            [{"id": tag["id"], "name": "Bounded settings tag"}],
        )

    def test_admin_saves_book_tags_and_ai_profile_independently(self):
        book = self.store.resolve_book(
            Path(self.directory.name) / "book.epub",
            None,
            "book-fingerprint",
            {"title": "Book", "authors": [], "tags": [], "cover": None},
            preferred_book_id="book-id",
        )
        tag = self.admin_client.post("/api/admin/ai/tags", json={"name": "History"})
        profile = self.admin_client.put(
            "/api/admin/books/" + book.book_id + "/ai",
            json={"profile": "fiction"},
        )
        tags = self.admin_client.put(
            "/api/admin/books/" + book.book_id + "/ai",
            json={"tag_ids": [tag.json()["tag"]["id"]]},
        )
        effective_metadata = self.member_client.get(
            "/api/books/" + book.book_id + "/metadata"
        )

        self.assertEqual(profile.status_code, 200)
        self.assertEqual(profile.json()["profile"], "fiction")
        self.assertEqual(tags.status_code, 200)
        self.assertEqual(tags.json()["profile"], "fiction")
        self.assertEqual(tags.json()["tags"], [tag.json()["tag"]])
        self.assertEqual(effective_metadata.status_code, 200)
        self.assertEqual(effective_metadata.json()["tags"], ["History"])
        self.assertEqual(
            self.admin_client.put(
                "/api/admin/books/" + book.book_id + "/ai", json={}
            ).status_code,
            400,
        )

    def test_admin_creates_lists_and_resets_a_member_password(self):
        created = self.admin_client.post(
            "/api/admin/users",
            json={
                "username": "reader",
                "password": "initial-secret",
                "role": "member",
            },
        )
        listed = self.admin_client.get("/api/admin/users")
        reader = self._login("reader", "initial-secret")

        reset = self.admin_client.put(
            "/api/admin/users/reader/password",
            json={"password": "replacement-secret"},
        )

        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.json()["user"]["username"], "reader")
        self.assertIn(
            "reader",
            {user["username"] for user in listed.json()["users"]},
        )
        self.assertEqual(reset.status_code, 200)
        self.assertEqual(reader.get("/api/session").status_code, 401)
        self._login("reader", "replacement-secret")

    def test_admin_can_revoke_all_sessions_without_disabling_the_account(self):
        response = self.admin_client.put(
            "/api/admin/users/member",
            json={"revoke_sessions": True},
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["user"]["enabled"])
        self.assertEqual(self.member_client.get("/api/session").status_code, 401)
        self._login("member", "member-secret")

    def test_admin_manages_proxy_identity_mappings_but_members_cannot(self):
        initial = self.admin_client.get("/api/admin/identities")
        created = self.admin_client.post(
            "/api/admin/identities",
            json={
                "issuer": "https://sso.example",
                "subject": "member-subject",
                "user_id": self.member.user_id,
                "display_name": "Member Example",
            },
        )
        duplicate = self.admin_client.post(
            "/api/admin/identities",
            json={
                "issuer": "https://sso.example",
                "subject": "member-subject",
                "user_id": self.admin.user_id,
            },
        )
        listed = self.admin_client.get("/api/admin/identities")
        member_denied = self.member_client.get("/api/admin/identities")
        deleted = self.admin_client.request(
            "DELETE",
            "/api/admin/identities",
            json={
                "issuer": "https://sso.example",
                "subject": "member-subject",
            },
        )

        self.assertEqual(initial.json(), {"identities": []})
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.json()["identity"]["username"], "member")
        self.assertEqual(duplicate.status_code, 409)
        self.assertEqual(duplicate.json()["code"], "identity_already_linked")
        self.assertEqual(len(listed.json()["identities"]), 1)
        self.assertEqual(member_denied.status_code, 403)
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(
            self.store.principal_from_identity(
                "https://sso.example",
                "member-subject",
            ),
            None,
        )

    def test_user_changes_password_and_all_existing_sessions_are_revoked(self):
        second_admin_client = self._login("admin", "admin-secret")

        wrong = self.admin_client.put(
            "/api/account/password",
            json={
                "current_password": "wrong",
                "new_password": "replacement-secret",
            },
        )
        changed = self.admin_client.put(
            "/api/account/password",
            json={
                "current_password": "admin-secret",
                "new_password": "replacement-secret",
            },
        )

        self.assertEqual(wrong.status_code, 401)
        self.assertEqual(changed.status_code, 200)
        self.assertEqual(self.admin_client.get("/api/session").status_code, 401)
        self.assertEqual(
            second_admin_client.get("/api/session").status_code,
            401,
        )
        self._login("admin", "replacement-secret")

    def test_user_lists_and_revokes_only_owned_sessions(self):
        second_admin_client = self._login("admin", "admin-secret")
        sessions = self.admin_client.get("/api/account/sessions")
        member_sessions = self.member_client.get("/api/account/sessions")

        self.assertEqual(sessions.status_code, 200)
        self.assertEqual(member_sessions.status_code, 200)
        current = next(
            session for session in sessions.json()["sessions"]
            if session["current"]
        )
        self.assertTrue(current["client_address"])
        self.assertTrue(current["user_agent"])
        self.assertIn("T", current["created_at"])
        self.assertIn("T", current["last_used_at"])
        self.assertIn("T", current["expires_at"])
        self.assertEqual(
            self.admin_client.get("/api/session").json()["authentication"],
            {"proxy_enabled": False, "pending_proxy_identity": False},
        )
        member_session = member_sessions.json()["sessions"][0]

        denied = self.admin_client.delete(
            "/api/account/sessions/" + member_session["id"]
        )
        other_admin_session = next(
            session for session in sessions.json()["sessions"]
            if not session["current"]
        )
        revoked = self.admin_client.delete(
            "/api/account/sessions/" + other_admin_session["id"]
        )

        self.assertEqual(denied.status_code, 404)
        self.assertEqual(revoked.status_code, 200)
        self.assertEqual(
            second_admin_client.get("/api/session").status_code,
            401,
        )
        self.assertEqual(self.member_client.get("/api/session").status_code, 200)


class SessionOwnershipTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        public = Path(self.directory.name)
        (public / "index.html").write_text("library", encoding="utf-8")
        self.store = StateStore(public / "epub-browser.db")
        self.alice = self.store.initialize(
            bootstrap=BootstrapCredentials("alice", "alice-secret")
        )
        self.bob = self.store.create_user("bob", hash_password("bob-secret"))
        self.store.resolve_book(
            public / "book.epub",
            None,
            "book-fingerprint",
            {"title": "Book"},
            preferred_book_id="book",
        )
        config = AuthConfig.from_values([], None, None)
        self.app = create_app(
            public,
            state_store=self.store,
            auth_service=AuthService(self.store, config),
        )
        self.client = TestClient(self.app)
        self.addCleanup(self.client.close)
        login = _json_login(self, self.client, "alice", "alice-secret")
        self.assertEqual(login.status_code, 200)
        session = self.client.get("/api/session")
        self.assertEqual(session.status_code, 200)
        self.csrf = {"X-CSRF-Token": session.json()["csrf_token"]}
        self.bob_client = TestClient(self.app)
        self.addCleanup(self.bob_client.close)
        bob_login = _json_login(self, self.bob_client, "bob", "bob-secret")
        self.assertEqual(bob_login.status_code, 200)
        bob_session = self.bob_client.get("/api/session")
        self.assertEqual(bob_session.status_code, 200)
        self.bob_csrf = {"X-CSRF-Token": bob_session.json()["csrf_token"]}
        self.annotation = {
            "id": "alice-note",
            "book_hash": "book",
            "chapter_index": 1,
            "text": "note",
            "color": "#fff",
            "created_at": "2026-01-01",
            "updated_at": "2026-01-01",
        }

    def test_annotation_header_cannot_impersonate_another_account(self):
        response = self.client.post(
            "/api/annotations/book",
            json=self.annotation,
            headers={"X-Username": "bob", **self.csrf},
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            self.store.list_annotations(user_id=self.alice.user_id)[0]["id"],
            self.annotation["id"],
        )
        self.assertEqual(
            self.store.list_annotations(user_id=self.bob.user_id),
            [],
        )

    def test_batch_annotation_id_collision_cannot_replace_another_accounts_row(self):
        bob_annotation = {
            **self.annotation,
            "id": "shared-client-id",
            "text": "Bob's note",
        }
        alice_annotation = {
            **self.annotation,
            "id": "shared-client-id",
            "text": "Alice's note",
        }

        bob_created = self.bob_client.post(
            "/api/annotations/batch",
            json={"annotations": [bob_annotation]},
            headers=self.bob_csrf,
        )
        alice_created = self.client.post(
            "/api/annotations/batch",
            json={"annotations": [alice_annotation]},
            headers=self.csrf,
        )

        self.assertEqual(bob_created.status_code, 201)
        self.assertEqual(bob_created.json(), {"created": 1, "failed": 0})
        self.assertEqual(alice_created.status_code, 201)
        self.assertEqual(alice_created.json(), {"created": 1, "failed": 0})
        bob_saved = self.bob_client.get(
            "/api/annotations/item/shared-client-id"
        )
        alice_saved = self.client.get(
            "/api/annotations/item/shared-client-id"
        )
        self.assertEqual(bob_saved.status_code, 200)
        self.assertEqual(bob_saved.json()["data"]["text"], "Bob's note")
        self.assertEqual(alice_saved.status_code, 200)
        self.assertEqual(alice_saved.json()["data"]["text"], "Alice's note")

    def test_bookshelf_body_username_cannot_select_another_account(self):
        response = self.client.post(
            "/sync",
            json={
                "username": "bob",
                "version": 2,
                "data": {"items": ["alice-book"], "groups": {}},
            },
            headers=self.csrf,
        )

        self.assertEqual(response.status_code, 404)
        self.assertNotIn("username", response.json())
        self.assertIsNotNone(self.store.get_bookshelf(self.alice.user_id))
        self.assertIsNone(self.store.get_bookshelf(self.bob.user_id))

    def test_reading_progress_header_cannot_impersonate_another_account(self):
        response = self.client.put(
            "/api/reading-progress/book",
            json={"chapter_index": 4},
            headers={"X-Username": "bob", **self.csrf},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            self.store.get_reading_progress(self.alice.user_id, "book"),
            4,
        )
        self.assertIsNone(
            self.store.get_reading_progress(self.bob.user_id, "book")
        )


class ServerAccountSecurityMatrixTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        public = Path(self.directory.name)
        (public / "index.html").write_text("library", encoding="utf-8")
        book_dir = public / "book" / "restricted-id"
        book_dir.mkdir(parents=True)
        (book_dir / SERVER_OUTPUT_REVISION_FILE).write_text(
            SERVER_OUTPUT_REVISION + "\n",
            encoding="utf-8",
        )
        (book_dir / "chapter_0.html").write_text("chapter", encoding="utf-8")

        self.store = StateStore(public / "epub-browser.db")
        self.store.initialize(BootstrapCredentials("admin", "admin-password"))
        self.store.resolve_book(
            public / "restricted.epub",
            None,
            "restricted-fingerprint",
            {
                "title": "Restricted book",
                "authors": [],
                "tags": [],
                "cover": None,
            },
            preferred_book_id="restricted-id",
        )
        self.auth_config = AuthConfig.from_values([], None, None)
        self.app = create_app(
            public,
            state_store=self.store,
            auth_service=AuthService(self.store, self.auth_config),
        )
        self.admin = None
        self.member = None
        self.member_ids = {}

    def _login(self, username, password):
        client = TestClient(self.app, follow_redirects=False)
        self.addCleanup(client.close)
        login = _json_login(self, client, username, password)
        self.assertEqual(login.status_code, 200)
        session = client.get("/api/session")
        self.assertEqual(session.status_code, 200)
        client.headers[self.auth_config.csrf_header_name] = session.json()[
            "csrf_token"
        ]
        return client

    def login_admin(self):
        self.admin = self._login("admin", "admin-password")
        return self.admin

    def create_member(self, username, password):
        response = self.admin.post(
            "/api/admin/users",
            json={
                "username": username,
                "password": password,
                "role": "member",
            },
        )
        self.assertEqual(response.status_code, 201)
        self.member_ids[username] = response.json()["user"]["id"]

    def restrict_book(self, book_id):
        response = self.admin.put(
            "/api/admin/books/" + book_id,
            json={"visibility": "restricted"},
        )
        self.assertEqual(response.status_code, 200)

    def login_member(self, username, password):
        self.member = self._login(username, password)
        return self.member

    def grant_book(self, book_id, username):
        response = self.admin.put(
            "/api/admin/books/{}/grants/{}".format(
                book_id,
                self.member_ids[username],
            ),
        )
        self.assertEqual(response.status_code, 200)

    def disable_user(self, username):
        response = self.admin.put(
            "/api/admin/users/" + username,
            json={"enabled": False},
        )
        self.assertEqual(response.status_code, 200)

    def test_member_lifecycle_from_login_to_restricted_book_revocation(self):
        self.login_admin()
        self.create_member("reader", "initial-password")
        self.restrict_book("restricted-id")
        self.assertEqual(
            self.login_member("reader", "initial-password").get(
                "/book/restricted-id/chapter_0.html"
            ).status_code,
            403,
        )
        self.grant_book("restricted-id", "reader")
        self.assertEqual(
            self.member.get(
                "/book/restricted-id/chapter_0.html"
            ).status_code,
            200,
        )
        raw_session = self.member.cookies.get("epub_browser_session")
        self.disable_user("reader")
        denied = self.member.get("/api/session")
        self.assertEqual(denied.status_code, 401)
        self.assertNotIn("initial-password", denied.text)
        self.assertNotIn(raw_session, denied.text)


class BookAuthorizationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        public = Path(self.directory.name)
        (public / "index.html").write_text("library", encoding="utf-8")
        books = [
            {
                "hash": "open-id",
                "url": "/book/open-id/index.html",
                "title": "Open book",
                "authors": ["Open author"],
                "tags": [],
                "cover": "/book/open-id/resources/image.jpg",
            },
            {
                "hash": "restricted-id",
                "url": "/book/restricted-id/index.html",
                "title": "Restricted book",
                "authors": ["Restricted author"],
                "tags": ["private"],
                "cover": "/book/restricted-id/resources/image.jpg",
            },
        ]
        (public / "book-metadata.json").write_text(
            json.dumps(books),
            encoding="utf-8",
        )
        for book_id in ("open-id", "restricted-id"):
            book_dir = public / "book" / book_id
            (book_dir / "resources").mkdir(parents=True)
            (book_dir / SERVER_OUTPUT_REVISION_FILE).write_text(
                SERVER_OUTPUT_REVISION + "\n",
                encoding="utf-8",
            )
            (book_dir / "index.html").write_text("reader", encoding="utf-8")
            (book_dir / "chapter_0.html").write_text("chapter", encoding="utf-8")
            (book_dir / "toc.json").write_text("[]", encoding="utf-8")
            (book_dir / "resources" / "image.jpg").write_bytes(b"image")

        self.store = StateStore(public / "epub-browser.db")
        self.admin = self.store.initialize(
            BootstrapCredentials("admin", "admin-secret")
        )
        self.member = self.store.create_user(
            "member",
            hash_password("member-secret"),
        )
        self.disabled_member = self.store.create_user(
            "disabled",
            hash_password("disabled-secret"),
        )
        self.store.set_user_enabled(self.disabled_member.user_id, False)
        self.store.resolve_book(
            public / "open.epub",
            None,
            "open-fingerprint",
            {
                "title": "Open book",
                "authors": ["Open author"],
                "tags": [],
                "cover": "resources/image.jpg",
            },
            preferred_book_id="open-id",
        )
        self.store.resolve_book(
            public / "restricted.epub",
            None,
            "restricted-fingerprint",
            {
                "title": "Restricted book",
                "authors": ["Restricted author"],
                "tags": ["private"],
                "cover": "resources/image.jpg",
            },
            preferred_book_id="restricted-id",
        )
        self.store.set_book_visibility("restricted-id", "restricted")
        self.auth_config = AuthConfig.from_values([], None, None)
        self.app = create_app(
            public,
            state_store=self.store,
            auth_service=AuthService(self.store, self.auth_config),
        )
        self.admin_client = self._login("admin", "admin-secret")
        self.member_client = self._login("member", "member-secret")

    def _login(self, username, password):
        client = TestClient(self.app)
        self.addCleanup(client.close)
        login = _json_login(self, client, username, password)
        self.assertEqual(login.status_code, 200)
        session = client.get("/api/session")
        self.assertEqual(session.status_code, 200)
        client.headers[self.auth_config.csrf_header_name] = session.json()[
            "csrf_token"
        ]
        return client

    def test_member_cannot_discover_or_open_restricted_book_by_direct_resource_url(self):
        metadata = self.member_client.get("/api/library-metadata")
        legacy_metadata = self.member_client.get("/book-metadata.json")

        self.assertEqual(metadata.status_code, 200)
        self.assertEqual(
            {book["hash"] for book in metadata.json()},
            {"open-id"},
        )
        self.assertEqual(legacy_metadata.json(), metadata.json())
        for path in (
            "/book/restricted-id/index.html",
            "/book/restricted-id/chapter_0.html",
            "/book/restricted-id/toc.json",
            "/book/restricted-id/resources/image.jpg",
        ):
            with self.subTest(path=path):
                denied = self.member_client.get(path)
                self.assertEqual(denied.status_code, 403)
                self.assertEqual(
                    denied.json(),
                    {"code": "forbidden", "message": "Forbidden"},
                )

    def test_grant_allows_member_catalog_and_reader_access(self):
        self.store.grant_book_access("restricted-id", self.member.user_id)

        metadata = self.member_client.get("/api/library-metadata")

        self.assertEqual(metadata.status_code, 200)
        self.assertEqual(
            {book["hash"] for book in metadata.json()},
            {"open-id", "restricted-id"},
        )
        self.assertEqual(
            self.member_client.get(
                "/book/restricted-id/chapter_0.html"
            ).status_code,
            200,
        )
        self.assertEqual(
            self.member_client.get(
                "/book/restricted-id/resources/image.jpg"
            ).status_code,
            200,
        )

    def test_ai_reading_route_rejects_unhashable_and_invalid_field_shapes(self):
        valid = {
            "scope": "chapter",
            "book_id": "open-id",
            "chapter_index": 0,
            "mode": "chapter",
            "language": "en",
            "force": False,
            "reading_boundary": None,
        }
        invalid_fields = (
            ("scope", []),
            ("book_id", []),
            ("language", {}),
            ("mode", []),
            ("chapter_index", True),
            ("force", 1),
            ("reading_boundary", True),
            ("reading_boundary", []),
            ("reading_boundary", -1),
        )

        with mock.patch.object(
            self.store, "can_read_book", wraps=self.store.can_read_book
        ) as can_read_book:
            for field, value in invalid_fields:
                with self.subTest(field=field, value=value):
                    payload = dict(valid)
                    payload[field] = value
                    response = self.member_client.post("/api/ai/reading", json=payload)
                    self.assertEqual(response.status_code, 400)
                    self.assertEqual(
                        response.json()["code"], "invalid_ai_reading_request"
                    )
            can_read_book.assert_not_called()

    def test_ai_reading_route_forwards_valid_reading_boundary(self):
        result = {"status": "queued", "cached": False, "job": {"id": "job"}}
        with mock.patch(
            "epub_browser.server.AIReadingService.submit",
            new_callable=mock.AsyncMock,
            return_value=result,
        ) as submit:
            response = self.member_client.post(
                "/api/ai/reading",
                json={
                    "scope": "book",
                    "book_id": "open-id",
                    "chapter_index": None,
                    "mode": "read_so_far",
                    "language": "en",
                    "force": False,
                    "reading_boundary": 0,
                },
            )

        self.assertEqual(response.status_code, 202)
        request = submit.await_args.args[1]
        self.assertEqual(request.book_id, "open-id")
        self.assertEqual(request.reading_boundary, 0)

    def test_administrator_can_list_restrict_grant_and_revoke_books(self):
        listing = self.admin_client.get("/api/admin/books")

        self.assertEqual(listing.status_code, 200)
        restricted = next(
            book
            for book in listing.json()["books"]
            if book["id"] == "restricted-id"
        )
        self.assertEqual(restricted["visibility"], "restricted")
        self.assertEqual(restricted["grants"], [])

        made_public = self.admin_client.put(
            "/api/admin/books/restricted-id",
            json={"visibility": "authenticated"},
        )
        self.assertEqual(made_public.status_code, 200)
        self.assertEqual(made_public.json()["book"]["visibility"], "authenticated")
        self.assertEqual(
            self.member_client.get(
                "/book/restricted-id/chapter_0.html"
            ).status_code,
            200,
        )

        self.admin_client.put(
            "/api/admin/books/restricted-id",
            json={"visibility": "restricted"},
        )
        granted = self.admin_client.put(
            f"/api/admin/books/restricted-id/grants/{self.member.user_id}",
        )
        self.assertEqual(granted.status_code, 200)
        self.assertTrue(granted.json()["grant"]["granted"])
        self.assertEqual(
            self.member_client.get(
                "/book/restricted-id/chapter_0.html"
            ).status_code,
            200,
        )

        revoked = self.admin_client.delete(
            f"/api/admin/books/restricted-id/grants/{self.member.user_id}",
        )
        self.assertEqual(revoked.status_code, 200)
        self.assertFalse(revoked.json()["grant"]["granted"])
        self.assertEqual(
            self.member_client.get(
                "/book/restricted-id/chapter_0.html"
            ).status_code,
            403,
        )

    def test_administrator_atomically_replaces_multiple_book_grants(self):
        second = self.store.create_user(
            "second-member",
            hash_password("second-secret"),
        )

        saved = self.admin_client.put(
            "/api/admin/books/restricted-id/grants",
            json={"user_ids": [self.member.user_id, second.user_id]},
        )

        self.assertEqual(saved.status_code, 200)
        self.assertEqual(
            saved.json()["grants"]["user_ids"],
            sorted((self.member.user_id, second.user_id)),
        )
        self.assertEqual(
            self.store.book_grants("restricted-id"),
            tuple(sorted((self.member.user_id, second.user_id))),
        )

        rejected = self.admin_client.put(
            "/api/admin/books/restricted-id/grants",
            json={"user_ids": [self.member.user_id, self.disabled_member.user_id]},
        )
        self.assertEqual(rejected.status_code, 400)
        self.assertEqual(
            self.store.book_grants("restricted-id"),
            tuple(sorted((self.member.user_id, second.user_id))),
        )

        cleared = self.admin_client.put(
            "/api/admin/books/restricted-id/grants",
            json={"user_ids": []},
        )
        self.assertEqual(cleared.status_code, 200)
        self.assertEqual(self.store.book_grants("restricted-id"), ())

    def test_book_administration_validates_role_book_visibility_and_enabled_user(self):
        member_denied = self.member_client.put(
            "/api/admin/books/restricted-id",
            json={"visibility": "authenticated"},
        )
        invalid_visibility = self.admin_client.put(
            "/api/admin/books/restricted-id",
            json={"visibility": "secret"},
        )
        unknown_book = self.admin_client.put(
            "/api/admin/books/missing",
            json={"visibility": "restricted"},
        )
        unknown_user = self.admin_client.put(
            "/api/admin/books/restricted-id/grants/missing",
        )
        disabled_user = self.admin_client.put(
            f"/api/admin/books/restricted-id/grants/{self.disabled_member.user_id}",
        )

        self.assertEqual(member_denied.status_code, 403)
        self.assertEqual(invalid_visibility.status_code, 400)
        self.assertEqual(unknown_book.status_code, 404)
        self.assertEqual(unknown_user.status_code, 404)
        self.assertEqual(disabled_user.status_code, 400)

    def test_revoked_book_access_blocks_every_annotation_and_progress_api_shape(self):
        self.store.grant_book_access("restricted-id", self.member.user_id)
        annotation = {
            "id": "restricted-note",
            "book_hash": "restricted-id",
            "chapter_index": 0,
            "text": "private note",
            "color": "#fff",
            "created_at": "2026-01-01",
            "updated_at": "2026-01-01",
        }
        batch_annotation = {**annotation, "id": "restricted-batch-note"}
        self.assertEqual(
            self.member_client.post(
                "/api/annotations/restricted-id",
                json=annotation,
            ).status_code,
            201,
        )
        self.assertEqual(
            self.member_client.post(
                "/api/annotations/batch",
                json={"annotations": [batch_annotation]},
            ).status_code,
            201,
        )
        self.assertEqual(
            self.member_client.put(
                "/api/reading-progress/restricted-id",
                json={"chapter_index": 0},
            ).status_code,
            200,
        )

        self.store.revoke_book_access("restricted-id", self.member.user_id)

        cross_book_overwrite = self.member_client.post(
            "/api/annotations/batch",
            json={
                "annotations": [
                    {
                        **annotation,
                        "book_hash": "open-id",
                        "text": "must not overwrite revoked data",
                    }
                ]
            },
        )
        self.assertEqual(cross_book_overwrite.status_code, 403)
        self.assertEqual(cross_book_overwrite.json()["code"], "forbidden")
        stored_after_cross_book_attempt = self.store.get_annotation(
            "restricted-note",
            user_id=self.member.user_id,
        )
        self.assertEqual(stored_after_cross_book_attempt["book_hash"], "restricted-id")
        self.assertEqual(stored_after_cross_book_attempt["text"], "private note")

        global_annotations = self.member_client.get("/api/annotations")
        self.assertEqual(global_annotations.status_code, 200)
        self.assertEqual(global_annotations.json()["data"], [])
        requests = (
            self.member_client.get("/api/annotations/restricted-id"),
            self.member_client.get("/api/annotations/item/restricted-note"),
            self.member_client.post(
                "/api/annotations/restricted-id",
                json={**annotation, "id": "new-single"},
            ),
            self.member_client.post(
                "/api/annotations/batch",
                json={"annotations": [{**annotation, "id": "new-batch"}]},
            ),
            self.member_client.put(
                "/api/annotations/item/restricted-note",
                json={"note": "changed"},
            ),
            self.member_client.delete(
                "/api/annotations/item/restricted-note"
            ),
            self.member_client.get("/api/reading-progress/restricted-id"),
            self.member_client.put(
                "/api/reading-progress/restricted-id",
                json={"chapter_index": 1},
            ),
            self.member_client.delete(
                "/api/reading-progress/restricted-id"
            ),
        )
        for denied in requests:
            with self.subTest(response=denied):
                self.assertEqual(denied.status_code, 403)
                self.assertEqual(denied.json()["code"], "forbidden")

        self.assertEqual(
            self.store.get_annotation(
                "restricted-note",
                user_id=self.member.user_id,
            )["note"],
            "",
        )
        self.assertEqual(
            self.store.get_reading_progress(
                self.member.user_id,
                "restricted-id",
            ),
            0,
        )

    def test_untracked_book_directory_and_traversal_attempt_are_not_served(self):
        untracked = Path(self.directory.name) / "book" / "untracked"
        untracked.mkdir()
        (untracked / "chapter_0.html").write_text("secret", encoding="utf-8")

        self.assertEqual(
            self.member_client.get(
                "/book/untracked/chapter_0.html"
            ).status_code,
            403,
        )
        self.assertEqual(
            self.member_client.get(
                "/book/open-id/%252e%252e/restricted-id/chapter_0.html"
            ).status_code,
            404,
        )


class ServerCacheTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        with open(os.path.join(self.directory.name, "index.html"), "w", encoding="utf-8") as index:
            index.write("library")
        os.makedirs(os.path.join(self.directory.name, "assets"))
        with open(os.path.join(self.directory.name, "assets", "cover.webp"), "wb") as cover:
            cover.write(b"cover")
        os.makedirs(os.path.join(self.directory.name, "assets", "immutable"))
        with open(os.path.join(self.directory.name, "assets", "immutable", "app.0123456789ab.js"), "w", encoding="utf-8") as app:
            app.write("console.log('app')")
        with open(os.path.join(self.directory.name, "assets", "manifest.json"), "w", encoding="utf-8") as manifest:
            manifest.write("{}")
        with open(os.path.join(self.directory.name, "assets", "manifest.en.json"), "w", encoding="utf-8") as manifest:
            manifest.write("{}")
        with open(os.path.join(self.directory.name, "assets", "manifest.zh-CN.json"), "w", encoding="utf-8") as manifest:
            manifest.write("{}")
        with open(os.path.join(self.directory.name, "sw.js"), "w", encoding="utf-8") as worker:
            worker.write("self.addEventListener('fetch', () => {})")
        os.makedirs(os.path.join(self.directory.name, "book", "demo", "resources"))
        with open(
            os.path.join(
                self.directory.name,
                "book",
                "demo",
                SERVER_OUTPUT_REVISION_FILE,
            ),
            "w",
            encoding="utf-8",
        ) as revision:
            revision.write(SERVER_OUTPUT_REVISION + "\n")
        with open(os.path.join(self.directory.name, "book", "demo", "index.html"), "w", encoding="utf-8") as book_index:
            book_index.write("book")
        with open(os.path.join(self.directory.name, "book", "demo", "chapter_0.html"), "w", encoding="utf-8") as chapter:
            chapter.write("chapter")
        with open(os.path.join(self.directory.name, "book", "demo", "resources", "cover.webp"), "wb") as cover:
            cover.write(b"cover")
        self.app, self.store, self.auth_service = self._authenticated_app(
            self.directory.name
        )
        self.store.resolve_book(
            Path(self.directory.name) / "demo.epub",
            None,
            "demo-fingerprint",
            {"title": "Demo", "cover": "resources/cover.webp"},
            preferred_book_id="demo",
        )
        self.store.resolve_book(
            Path(self.directory.name) / "book.epub",
            None,
            "book-fingerprint",
            {"title": "Book"},
            preferred_book_id="book",
        )
        self.store.resolve_book(
            Path(self.directory.name) / "shared-book.epub",
            None,
            "shared-book-fingerprint",
            {"title": "Shared book"},
            preferred_book_id="shared-book",
        )
        self.client = self._authenticated_client(self.app)

    def tearDown(self):
        self.directory.cleanup()

    def _authenticated_app(self, directory, **kwargs):
        store = kwargs.pop("state_store", None)
        if store is None:
            store = StateStore(Path(directory) / "epub-browser.db")
            store.initialize(bootstrap=BootstrapCredentials("alice", "secret"))
        config = AuthConfig.from_values([], None, None)
        auth_service = AuthService(store, config)
        app = create_app(
            directory,
            state_store=store,
            auth_service=auth_service,
            **kwargs,
        )
        return app, store, auth_service

    def _authenticated_client(self, app):
        client = TestClient(app)
        login = _json_login(self, client, "alice", "secret")
        self.assertEqual(login.status_code, 200)
        session = client.get("/api/session")
        self.assertEqual(session.status_code, 200)
        client.headers["X-CSRF-Token"] = session.json()["csrf_token"]
        return client

    def _library_event_chunks(self, app, after_initial=None):
        async def collect():
            headers = {}
            chunks = asyncio.Queue()
            response_started = asyncio.Event()
            disconnected = asyncio.Event()

            async def receive():
                await disconnected.wait()
                return {"type": "http.disconnect"}

            async def send(message):
                if message["type"] == "http.response.start":
                    headers["status"] = message["status"]
                    headers.update(
                        {
                            name.decode().lower(): value.decode()
                            for name, value in message["headers"]
                        }
                    )
                    response_started.set()
                elif message["type"] == "http.response.body" and message.get("body"):
                    await chunks.put(message["body"].decode())

            task = asyncio.create_task(
                app(
                    {
                        "type": "http",
                        "asgi": {"version": "3.0"},
                        "http_version": "1.1",
                        "method": "GET",
                        "scheme": "http",
                        "path": "/api/library-events",
                        "raw_path": b"/api/library-events",
                        "query_string": b"",
                        "headers": [
                            (
                                b"cookie",
                                (
                                    "epub_browser_session="
                                    + self.client.cookies.get("epub_browser_session")
                                ).encode(),
                            )
                        ],
                        "client": ("testclient", 50000),
                        "server": ("testserver", 80),
                    },
                    receive,
                    send,
                )
            )
            await asyncio.wait_for(response_started.wait(), 1)
            first = await asyncio.wait_for(chunks.get(), 1)
            second = None
            if after_initial is not None:
                after_initial()
                second = await asyncio.wait_for(chunks.get(), 1)
            disconnected.set()
            await asyncio.wait_for(task, 1)
            return headers, first, second

        return asyncio.run(collect())

    def test_authenticated_immutable_assets_revalidate_in_a_private_cache(self):
        response = self.client.get("/assets/immutable/app.0123456789ab.js")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["cache-control"], "private, no-cache")
        self.assertNotIn("public", response.headers["cache-control"])
        self.assertIn("etag", response.headers)

        cached = self.client.get("/assets/immutable/app.0123456789ab.js", headers={"If-None-Match": response.headers["etag"]})
        self.assertEqual(cached.status_code, 304)
        self.assertEqual(cached.headers["cache-control"], "private, no-cache")

    def test_mutable_assets_and_worker_revalidate(self):
        for path in (
            "/assets/cover.webp",
            "/assets/manifest.json",
            "/assets/manifest.en.json",
            "/assets/manifest.zh-CN.json",
        ):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.headers["cache-control"], "private, no-cache")

    def test_server_serves_a_public_no_cache_service_worker_tombstone(self):
        with TestClient(self.app, follow_redirects=False) as anonymous:
            response = anonymous.get("/sw.js")

        self.assertEqual(response.status_code, 200)
        self.assertIn("no-store", response.headers["cache-control"])
        self.assertEqual(response.headers["service-worker-allowed"], "/")
        self.assertNotIn("self.addEventListener('fetch', () => {})", response.text)
        self.assertIn("self.skipWaiting()", response.text)
        self.assertIn("self.clients.claim()", response.text)
        self.assertIn("name.indexOf('epub-browser-') === 0", response.text)
        self.assertIn("self.registration.unregister()", response.text)
        self.assertIn("client.navigate(client.url)", response.text)
        self.assertNotIn("caches.delete(name)", response.text.split("epub-browser-")[0])

    def test_server_reader_html_uses_hash_based_restrictive_csp(self):
        script = "window.generatedReaderBootstrap=true;"
        Path(
            self.directory.name,
            "book",
            "demo",
            "chapter_0.html",
        ).write_text(f"<script>{script}</script><p>chapter</p>", encoding="utf-8")

        response = self.client.get("/book/demo/chapter_0.html")
        policy = response.headers["content-security-policy"]
        expected_hash = base64.b64encode(
            hashlib.sha256(script.encode("utf-8")).digest()
        ).decode("ascii")
        script_directive = next(
            directive
            for directive in policy.split(";")
            if directive.strip().startswith("script-src")
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("default-src 'self'", policy)
        self.assertIn("object-src 'none'", policy)
        self.assertIn("frame-ancestors 'none'", policy)
        self.assertIn("'sha256-{}'".format(expected_hash), script_directive)
        self.assertNotIn("'unsafe-inline'", script_directive)

    def test_server_never_serves_active_documents_from_book_resources(self):
        payload = Path(
            self.directory.name,
            "book",
            "demo",
            "resources",
            "payload.htm",
        )
        payload.write_text(
            '<script id="payload">fetch("/api/session")</script>',
            encoding="utf-8",
        )

        response = self.client.get("/book/demo/resources/payload.htm")

        self.assertEqual(response.status_code, 404)
        self.assertNotIn("content-security-policy", response.headers)
        self.assertNotIn("payload", response.text)

    def test_html_is_revalidated_instead_of_long_lived(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["cache-control"], "private, no-cache")

    def test_starlette_static_errors_return_stable_json_codes(self):
        response = self.client.get("/missing-static-file")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"code": "not_found", "message": "Not Found"})

    def test_authenticated_book_resources_are_private_and_unauthenticated_are_denied(self):
        book_page = self.client.get("/book/demo/index.html")
        chapter_page = self.client.get("/book/demo/chapter_0.html")
        cover = self.client.get("/book/demo/resources/cover.webp")

        for response in (book_page, chapter_page, cover):
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers["cache-control"], "private, no-cache")
            self.assertNotIn("public", response.headers["cache-control"])

        unauthenticated = TestClient(self.app)
        self.addCleanup(unauthenticated.close)
        denied = unauthenticated.get("/book/demo/resources/cover.webp")
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(denied.headers["cache-control"], "no-store")

    def test_annotation_routes_preserve_create_and_read_behavior(self):
        annotation = {"id": "a1", "book_hash": "book", "chapter_index": 1, "text": "note", "color": "#fff", "created_at": "2026-01-01", "updated_at": "2026-01-01"}
        created = self.client.post("/api/annotations", json=annotation)
        fetched = self.client.get("/api/annotations/book/1")

        self.assertEqual(created.status_code, 201)
        self.assertEqual(fetched.json()["data"][0]["id"], "a1")

    def test_annotation_delete_accepts_an_empty_json_request_body(self):
        annotation = {
            "id": "delete-me",
            "book_hash": "book",
            "chapter_index": 1,
            "text": "note",
            "color": "#fff",
            "created_at": "2026-01-01",
            "updated_at": "2026-01-01",
        }
        self.assertEqual(self.client.post("/api/annotations", json=annotation).status_code, 201)

        deleted = self.client.request(
            "DELETE",
            "/api/annotations/item/delete-me",
            content=b"",
            headers={"Content-Type": "application/json"},
        )

        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(deleted.json(), {"message": "Deleted"})
        self.assertEqual(self.client.get("/api/annotations/item/delete-me").status_code, 404)

    def test_annotation_position_repair_can_move_a_cloud_annotation_to_its_real_chapter(self):
        annotation = {
            "id": "misplaced",
            "book_hash": "book",
            "chapter_index": 1,
            "text": "note",
            "note": "keep me",
            "color": "#fff",
            "startMeta": {"parentTagName": "P", "parentIndex": 8, "textOffset": 1},
            "endMeta": {"parentTagName": "P", "parentIndex": 8, "textOffset": 5},
            "created_at": "2026-01-01",
            "updated_at": "2026-01-01",
        }
        self.client.post("/api/annotations", json=annotation)

        response = self.client.put(
            "/api/annotations/item/misplaced",
            json={
                "chapter_index": 3,
                "startMeta": {"parentTagName": "P", "parentIndex": 0, "textOffset": 1},
                "endMeta": {"parentTagName": "P", "parentIndex": 0, "textOffset": 5},
            },
        )

        self.assertEqual(response.status_code, 200)
        repaired = response.json()["data"]
        self.assertEqual(repaired["chapter_index"], 3)
        self.assertEqual(repaired["note"], "keep me")
        self.assertEqual(repaired["startMeta"]["parentIndex"], 0)
        self.assertEqual(self.client.get("/api/annotations/book/1").json()["data"], [])
        self.assertEqual(self.client.get("/api/annotations/book/3").json()["data"][0]["id"], "misplaced")

    def test_browser_api_errors_include_stable_codes_and_compatible_messages(self):
        with mock.patch.object(
            self.store,
            "get_reading_progress",
            side_effect=sqlite3.OperationalError("offline"),
        ):
            server_error = self.client.get("/api/reading-progress/book")

        cases = [
            (self.client.post("/sync", json={}), 400, "no_sync_data"),
            (self.client.put("/api/reading-progress/book", json={"chapter_index": -1}), 400, "invalid_chapter_index"),
            (self.client.get("/api/annotations/item/missing"), 404, "annotation_not_found"),
            (self.client.post("/sync", content=b"{", headers={"Content-Type": "application/json"}), 400, "invalid_json"),
            (server_error, 500, "server_error"),
        ]
        for response, status, code in cases:
            with self.subTest(code=code):
                self.assertEqual(response.status_code, status)
                self.assertEqual(response.json()["code"], code)
                self.assertIsInstance(response.json()["message"], str)

    def test_sync_route_preserves_new_shelf_response(self):
        response = self.client.post("/sync", json={"username": "reader", "version": 1, "data": {"items": []}})

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["version"], 1)

    def test_sync_returns_not_modified_when_versions_match(self):
        payload = {"username": "reader", "version": 1, "data": {"items": []}}
        self.client.post("/sync", json=payload)

        response = self.client.post("/sync", json=payload)

        self.assertEqual(response.status_code, 304)

    def test_reading_progress_defaults_to_shared_reader_and_can_be_cleared(self):
        self.assertEqual(self.client.get("/api/reading-progress/book").status_code, 404)

        saved = self.client.put("/api/reading-progress/book", json={"chapter_index": 4})

        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.json(), {"chapter_index": 4})
        self.assertEqual(self.client.get("/api/reading-progress/book").json(), {"chapter_index": 4})
        self.assertEqual(self.client.delete("/api/reading-progress/book").status_code, 200)
        self.assertEqual(self.client.get("/api/reading-progress/book").status_code, 404)

    def test_reading_progress_isolated_by_session_and_rejects_invalid_chapters(self):
        self.client.put("/api/reading-progress/book", json={"chapter_index": 4})
        self.store.create_user("bob", hash_password("secret"))
        bob = TestClient(self.app)
        self.addCleanup(bob.close)
        self.assertEqual(
            _json_login(self, bob, "bob", "secret").status_code,
            200,
        )
        bob.headers["X-CSRF-Token"] = bob.get("/api/session").json()["csrf_token"]
        named = bob.put(
            "/api/reading-progress/book",
            json={"chapter_index": 7},
        )

        self.assertEqual(named.json(), {"chapter_index": 7})
        self.assertEqual(self.client.get("/api/reading-progress/book").json(), {"chapter_index": 4})
        self.assertEqual(
            bob.get("/api/reading-progress/book").json(),
            {"chapter_index": 7},
        )
        self.assertEqual(
            self.client.put("/api/reading-progress/book", json={"chapter_index": -1}).status_code,
            400,
        )

    def test_library_events_streams_initial_progress_snapshot_with_sse_headers(self):
        broker = LibraryProgressBroker()
        broker.start_generation("startup")
        broker.mark_discovered(2, 0)
        app, _, _ = self._authenticated_app(
            self.directory.name,
            state_store=self.store,
            progress_broker=broker,
        )

        headers, chunk, _ = self._library_event_chunks(app)
        lines = chunk.splitlines()
        self.assertEqual(headers["status"], 200)
        self.assertEqual(headers["cache-control"], "private, no-cache")
        self.assertEqual(headers["x-accel-buffering"], "no")
        self.assertEqual(lines[0], "event: progress")
        payload = json.loads(lines[1].removeprefix("data: "))
        self.assertEqual(payload["phase"], "processing")
        self.assertEqual(payload["total"], 2)

        self.assertEqual(broker.subscriber_count, 0)

    def test_library_events_receive_worker_thread_updates(self):
        broker = LibraryProgressBroker()
        app, _, _ = self._authenticated_app(
            self.directory.name,
            state_store=self.store,
            progress_broker=broker,
        )

        worker = threading.Thread(target=broker.conversion_started)

        def start_worker():
            worker.start()
            worker.join(timeout=1)

        _, _, chunk = self._library_event_chunks(app, after_initial=start_worker)
        self.assertFalse(worker.is_alive())
        lines = chunk.splitlines()
        self.assertEqual(lines[0], "event: progress")
        payload = json.loads(lines[1].removeprefix("data: "))
        self.assertEqual(payload["in_flight"], 1)

    def test_library_events_emit_heartbeat_without_waiting_for_production_timeout(self):
        broker = LibraryProgressBroker()
        app, _, _ = self._authenticated_app(
            self.directory.name,
            state_store=self.store,
            progress_broker=broker,
            library_event_heartbeat_seconds=0.01,
        )

        _, _, heartbeat = self._library_event_chunks(app, after_initial=lambda: None)

        self.assertEqual(heartbeat, ": heartbeat\n\n")

    def test_scanning_progress_does_not_block_ready_or_reading_progress(self):
        status = RuntimeStatus()
        status.mark_available()
        status.mark_scanning()
        broker = LibraryProgressBroker()
        app, _, _ = self._authenticated_app(
            self.directory.name,
            state_store=self.store,
            status=status,
            progress_broker=broker,
        )
        client = self._authenticated_client(app)
        self.addCleanup(client.close)

        self.assertEqual(client.get("/api/ready").status_code, 200)
        self.assertEqual(
            client.put(
                "/api/reading-progress/book",
                json={"chapter_index": 1},
            ).status_code,
            200,
        )

    def test_two_apps_keep_state_in_their_injected_database(self):
        with tempfile.TemporaryDirectory() as second_directory:
            Path(second_directory, "index.html").write_text(
                "second library",
                encoding="utf-8",
            )
            first_client = self.client
            second_app, _, _ = self._authenticated_app(second_directory)
            second_client = self._authenticated_client(second_app)
            self.addCleanup(second_client.close)

            first_client.put(
                "/api/reading-progress/shared-book",
                json={"chapter_index": 2},
            )

            self.assertEqual(
                first_client.get("/api/reading-progress/shared-book").json(),
                {"chapter_index": 2},
            )
            self.assertEqual(
                second_client.get("/api/reading-progress/shared-book").status_code,
                403,
            )

    def test_sync_persists_the_shelf_in_sqlite(self):
        payload = {"username": "reader", "version": 2, "data": {"items": ["book-a"], "groups": {}}}

        response = self.client.post("/sync", json=payload)

        self.assertEqual(response.status_code, 404)
        with sqlite3.connect(os.path.join(self.directory.name, "epub-browser.db")) as connection:
            row = connection.execute(
                "SELECT version, data FROM bookshelves WHERE user_id = ?",
                (self.store.get_user_by_username("alice").user_id,),
            ).fetchone()
        self.assertEqual(row, (2, json.dumps(payload["data"], ensure_ascii=False)))

    def test_server_bookshelf_is_read_and_written_with_a_versioned_document(self):
        initial = self.client.get("/api/bookshelf")
        self.assertEqual(initial.status_code, 200)
        self.assertEqual(initial.json(), {"version": 0, "data": {"items": [], "groups": {}, "order": []}})

        created = self.client.put(
            "/api/bookshelf",
            json={"version": 0, "data": {"items": ["book-a"], "groups": {}, "order": ["book-a"]}},
        )
        self.assertEqual(created.status_code, 200)
        self.assertEqual(created.json()["version"], 1)

        loaded = self.client.get("/api/bookshelf")
        self.assertEqual(loaded.json(), created.json())

    def test_server_bookshelf_ignores_spoofed_username_and_uses_principal(self):
        created = self.client.put(
            "/api/bookshelf",
            headers={"X-Username": "someone-else"},
            json={"version": 0, "data": {"items": [], "groups": {}, "order": []}},
        )

        self.assertEqual(created.status_code, 200)
        self.assertIsNotNone(
            self.store.get_bookshelf(self.store.get_user_by_username("alice").user_id)
        )

    def test_server_bookshelf_rejects_stale_automatic_saves_without_overwriting_data(self):
        self.client.put(
            "/api/bookshelf",
            json={"version": 0, "data": {"items": ["server"], "groups": {}, "order": ["server"]}},
        )

        conflict = self.client.put(
            "/api/bookshelf",
            json={"version": 0, "data": {"items": ["client"], "groups": {}, "order": ["client"]}},
        )

        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(conflict.json()["code"], "bookshelf_conflict")
        self.assertEqual(conflict.json()["data"]["items"], ["server"])

    def test_sync_returns_the_sqlite_shelf_to_an_older_client(self):
        self.client.post("/sync", json={"username": "reader", "version": 3, "data": {"items": ["server"], "groups": {}}})

        response = self.client.post("/sync", json={"username": "reader", "version": 2, "data": {"items": ["client"], "groups": {}}})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"message": "Server has newer or same version", "version": 3, "data": {"items": ["server"], "groups": {}}})

    def test_sync_never_imports_username_selected_legacy_shelf_files(self):
        Path(self.directory.name, "epub-browser-bookshelf-alice-2.json").write_text('{"items":["old"],"groups":{}}', encoding="utf-8")
        Path(self.directory.name, "epub-browser-bookshelf-alice-4.json").write_text('{"items":["new"],"groups":{}}', encoding="utf-8")

        response = self.client.post("/sync", json={"username": "reader", "version": 1, "data": {"items": [], "groups": {}}})

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["version"], 1)
        with sqlite3.connect(os.path.join(self.directory.name, "epub-browser.db")) as connection:
            row = connection.execute(
                "SELECT version, data FROM bookshelves WHERE user_id = ?",
                (self.store.get_user_by_username("alice").user_id,),
            ).fetchone()
        self.assertEqual(
            row,
            (1, json.dumps({"items": [], "groups": {}}, ensure_ascii=False)),
        )

    def test_startup_renames_the_legacy_annotation_database_without_losing_data(self):
        legacy_directory = tempfile.TemporaryDirectory()
        self.addCleanup(legacy_directory.cleanup)
        legacy_path = os.path.join(legacy_directory.name, "annotations.db")
        with sqlite3.connect(legacy_path) as connection:
            connection.execute("""
                CREATE TABLE annotations (
                    id TEXT PRIMARY KEY, username TEXT NOT NULL DEFAULT '', book_hash TEXT NOT NULL,
                    chapter_index INTEGER NOT NULL, text TEXT NOT NULL, note TEXT, start_meta TEXT,
                    end_meta TEXT, color TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                )
            """)
            connection.execute(
                "INSERT INTO annotations (id, book_hash, chapter_index, text, color, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("annotation-1", "book-a", 1, "Saved note", "#fff", "2026-08-12", "2026-08-12"),
            )
            connection.execute("CREATE TABLE bookshelves (username TEXT PRIMARY KEY, version INTEGER NOT NULL, data TEXT NOT NULL)")
            connection.execute("INSERT INTO bookshelves (username, version, data) VALUES (?, ?, ?)", ("reader", 3, '{\"items\":[\"book-a\"]}'))

        migrated = migrate_legacy_database(legacy_directory.name)
        StateStore(migrated).initialize(
            bootstrap=BootstrapCredentials("alice", "secret")
        )

        database_path = os.path.join(legacy_directory.name, "epub-browser.db")
        self.assertTrue(os.path.isfile(database_path))
        self.assertFalse(os.path.exists(legacy_path))
        with sqlite3.connect(database_path) as connection:
            annotation = connection.execute("SELECT id, text FROM annotations").fetchone()
            bookshelf = connection.execute("SELECT version, data FROM bookshelves").fetchone()
        self.assertEqual(annotation, ("annotation-1", "Saved note"))
        self.assertEqual(bookshelf, (3, '{\"items\":[\"book-a\"]}'))

    def test_startup_uses_a_new_database_when_legacy_rename_fails(self):
        legacy_directory = tempfile.TemporaryDirectory()
        self.addCleanup(legacy_directory.cleanup)
        legacy_path = os.path.join(legacy_directory.name, "annotations.db")
        legacy_connection = sqlite3.connect(legacy_path)
        legacy_connection.close()

        with mock.patch("epub_browser.server.os.replace", side_effect=OSError("disk error")):
            database = migrate_legacy_database(legacy_directory.name)
        StateStore(database).initialize(
            bootstrap=BootstrapCredentials("alice", "secret")
        )

        self.assertTrue(os.path.isfile(legacy_path))
        self.assertTrue(os.path.isfile(os.path.join(legacy_directory.name, "epub-browser.db")))
