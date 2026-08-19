import asyncio
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from unittest import mock

from starlette.testclient import TestClient

from epub_browser.auth import (
    AuthConfig,
    AuthService,
    BootstrapCredentials,
    hash_password,
)
from epub_browser.library_progress import LibraryProgressBroker
from epub_browser.processor import SERVER_OUTPUT_REVISION, SERVER_OUTPUT_REVISION_FILE
from epub_browser.runtime import RuntimeStatus
from epub_browser.server import create_app, migrate_legacy_database
from epub_browser.state import StateStore


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
        self.assertEqual(self.client.get("/api/health").status_code, 401)
        self.assertEqual(
            self.client.get(
                "/api/health",
                headers={"Accept": "text/html"},
            ).status_code,
            401,
        )
        self.assertEqual(self.client.get("/api/ready").status_code, 401)

    def test_password_login_sets_session_and_requires_csrf_to_write(self):
        response = self.client.post(
            "/login?next=%2Fbook%2Fid%2Fchapter_0.html",
            data={"username": "alice", "password": "secret"},
        )

        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/book/id/chapter_0.html")
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

    def test_login_next_is_relative_and_logout_revokes_the_session(self):
        login_page = self.client.get("/login?next=https%3A%2F%2Fevil.example")
        self.assertEqual(login_page.status_code, 200)
        self.assertIn('id="loginForm"', login_page.text)
        encoded_backslash = self.client.get(
            "/login?next=%2F%255C%255Cevil.example"
        )
        self.assertIn('name="next" value="/"', encoded_backslash.text)

        logged_in = self.client.post(
            "/login?next=https%3A%2F%2Fevil.example",
            data={"username": "alice", "password": "secret"},
        )
        self.assertEqual(logged_in.headers["location"], "/")
        csrf = self.client.get("/api/session").json()["csrf_token"]

        self.assertEqual(self.client.post("/logout").status_code, 403)
        logout = self.client.post(
            "/logout",
            headers={self.auth_config.csrf_header_name: csrf},
        )
        self.assertEqual(logout.status_code, 303)
        self.assertEqual(logout.headers["location"], "/login")
        self.assertEqual(self.client.get("/api/session").status_code, 401)

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

        response = secure_client.post(
            "/login",
            data={"username": "alice", "password": "secret"},
        )

        self.assertEqual(response.status_code, 303)
        self.assertIn("Secure", response.headers["set-cookie"])
        self.assertEqual(secure_client.get("/api/session").status_code, 200)

    def test_authenticated_login_requires_csrf_before_replacing_the_session(self):
        first_login = self.client.post(
            "/login",
            data={"username": "alice", "password": "secret"},
        )
        self.assertEqual(first_login.status_code, 303)
        original_session = self.client.cookies.get("epub_browser_session")
        csrf = self.client.get("/api/session").json()["csrf_token"]

        denied = self.client.post(
            "/login",
            data={"username": "alice", "password": "secret"},
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
            data={"username": "alice", "password": "secret"},
            headers={self.auth_config.csrf_header_name: csrf},
        )

        self.assertEqual(replaced.status_code, 303)
        self.assertNotEqual(
            self.client.cookies.get("epub_browser_session"),
            original_session,
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
            client.post(
                "/login",
                data={"username": "alice", "password": "secret"},
            ).status_code,
            303,
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

        rejected = self.proxy_client.post(
            "/api/identity/link",
            json={"username": "alice", "password": "wrong"},
        )
        self.assertEqual(rejected.status_code, 401)
        self.assertIsNone(
            self.store.get_identity("https://sso.example", "subject-alice")
        )

        linked = self.proxy_client.post(
            "/api/identity/link",
            json={"username": "alice", "password": "secret"},
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

    def test_link_requires_an_unrecognized_assertion_from_a_trusted_peer(self):
        untrusted = TestClient(
            self.app,
            client=("203.0.113.8", 50000),
            headers={"X-Remote-User": "forged-subject"},
        )
        self.addCleanup(untrusted.close)

        response = untrusted.post(
            "/api/identity/link",
            json={"username": "alice", "password": "secret"},
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
        login = client.post(
            "/login",
            data={"username": username, "password": password},
        )
        self.assertEqual(login.status_code, 303)
        session = client.get("/api/session")
        self.assertEqual(session.status_code, 200)
        client.headers["X-CSRF-Token"] = session.json()["csrf_token"]
        return client

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
        config = AuthConfig.from_values([], None, None)
        self.app = create_app(
            public,
            state_store=self.store,
            auth_service=AuthService(self.store, config),
        )
        self.client = TestClient(self.app)
        self.addCleanup(self.client.close)
        login = self.client.post(
            "/login",
            data={"username": "alice", "password": "alice-secret"},
            follow_redirects=False,
        )
        self.assertEqual(login.status_code, 303)
        session = self.client.get("/api/session")
        self.assertEqual(session.status_code, 200)
        self.csrf = {"X-CSRF-Token": session.json()["csrf_token"]}
        self.bob_client = TestClient(self.app)
        self.addCleanup(self.bob_client.close)
        bob_login = self.bob_client.post(
            "/login",
            data={"username": "bob", "password": "bob-secret"},
            follow_redirects=False,
        )
        self.assertEqual(bob_login.status_code, 303)
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
        login = client.post(
            "/login",
            data={"username": username, "password": password},
            follow_redirects=False,
        )
        self.assertEqual(login.status_code, 303)
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
        login = client.post(
            "/login",
            data={"username": "alice", "password": "secret"},
            follow_redirects=False,
        )
        self.assertEqual(login.status_code, 303)
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
            "/sw.js",
        ):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.headers["cache-control"], "private, no-cache")

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
            bob.post(
                "/login",
                data={"username": "bob", "password": "secret"},
                follow_redirects=False,
            ).status_code,
            303,
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
                404,
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
        headers = {"X-Username": "reader"}

        initial = self.client.get("/api/bookshelf", headers=headers)
        self.assertEqual(initial.status_code, 200)
        self.assertEqual(initial.json(), {"version": 0, "data": {"items": [], "groups": {}, "order": []}})

        created = self.client.put(
            "/api/bookshelf",
            headers=headers,
            json={"version": 0, "data": {"items": ["book-a"], "groups": {}, "order": ["book-a"]}},
        )
        self.assertEqual(created.status_code, 200)
        self.assertEqual(created.json()["version"], 1)

        loaded = self.client.get("/api/bookshelf", headers=headers)
        self.assertEqual(loaded.json(), created.json())

    def test_server_bookshelf_requires_a_logged_in_username(self):
        read = self.client.get("/api/bookshelf")
        write = self.client.put(
            "/api/bookshelf",
            json={"version": 0, "data": {"items": [], "groups": {}, "order": []}},
        )

        self.assertEqual(read.status_code, 400)
        self.assertEqual(write.status_code, 400)
        self.assertEqual(read.json()["code"], "username_required")
        self.assertEqual(write.json()["code"], "username_required")

    def test_server_bookshelf_rejects_stale_automatic_saves_without_overwriting_data(self):
        headers = {"X-Username": "reader"}
        self.client.put(
            "/api/bookshelf",
            headers=headers,
            json={"version": 0, "data": {"items": ["server"], "groups": {}, "order": ["server"]}},
        )

        conflict = self.client.put(
            "/api/bookshelf",
            headers=headers,
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

    def test_sync_imports_the_highest_version_legacy_shelf_once(self):
        Path(self.directory.name, "epub-browser-bookshelf-alice-2.json").write_text('{"items":["old"],"groups":{}}', encoding="utf-8")
        Path(self.directory.name, "epub-browser-bookshelf-alice-4.json").write_text('{"items":["new"],"groups":{}}', encoding="utf-8")

        response = self.client.post("/sync", json={"username": "reader", "version": 1, "data": {"items": [], "groups": {}}})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["version"], 4)
        self.assertEqual(response.json()["data"]["items"], ["new"])
        with sqlite3.connect(os.path.join(self.directory.name, "epub-browser.db")) as connection:
            row = connection.execute(
                "SELECT version FROM bookshelves WHERE user_id = ?",
                (self.store.get_user_by_username("alice").user_id,),
            ).fetchone()
        self.assertEqual(row, (4,))

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
            bookshelf = connection.execute("SELECT username, version, data FROM bookshelves").fetchone()
        self.assertEqual(annotation, ("annotation-1", "Saved note"))
        self.assertEqual(bookshelf, ("reader", 3, '{\"items\":[\"book-a\"]}'))

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
