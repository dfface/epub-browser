import tempfile
import unittest
from pathlib import Path

from starlette.testclient import TestClient

from epub_browser.auth import AuthConfig, AuthService, BootstrapCredentials
from epub_browser.pat import PAT_SCOPES
from epub_browser.public_api import openapi_document, public_api_operations
from epub_browser.server import create_app
from epub_browser.state import StateStore

from tests.test_server import _json_login


class PublicAPIBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.public = Path(self.directory.name)
        (self.public / "index.html").write_text("library", encoding="utf-8")
        (self.public / "assets").mkdir()
        self.store = StateStore(self.public / "epub-browser.db")
        self.principal = self.store.initialize(
            bootstrap=BootstrapCredentials("alice", "secret")
        )
        self.store.resolve_book(
            self.public / "book.epub",
            None,
            "book-fingerprint",
            {"title": "Visible Book", "author": "Author"},
            preferred_book_id="book",
        )
        self.auth_service = AuthService(self.store, AuthConfig.from_values([]))
        self.app = create_app(
            self.public,
            state_store=self.store,
            auth_service=self.auth_service,
        )
        self.client = TestClient(self.app, follow_redirects=False)

    def bearer(self, *scopes):
        issued = self.store.create_personal_access_token(
            self.principal.user_id,
            "API test",
            scopes,
            expires_at=None,
        )
        return {"Authorization": "Bearer " + issued.raw_token}

    def test_cookie_cannot_authenticate_v1_and_pat_cannot_authenticate_browser_api(self):
        self.assertEqual(
            _json_login(self, self.client, "alice", "secret").status_code,
            200,
        )
        self.assertEqual(self.client.get("/api/v1/books").status_code, 401)

        pat_only = TestClient(self.app, follow_redirects=False)
        response = pat_only.get(
            "/api/session", headers=self.bearer("library:read")
        )
        self.assertEqual(response.status_code, 401)

    def test_bearer_errors_and_scope_checks_are_machine_readable(self):
        missing = self.client.get("/api/v1/books")
        self.assertEqual(missing.status_code, 401)
        self.assertEqual(missing.json()["code"], "invalid_token")
        self.assertEqual(missing.headers["www-authenticate"], 'Bearer realm="epub-browser"')

        denied = self.client.get(
            "/api/v1/books", headers=self.bearer("bookshelf:read")
        )
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(denied.json()["code"], "insufficient_scope")

    def test_library_read_pat_lists_only_currently_visible_books(self):
        response = self.client.get(
            "/api/v1/books", headers=self.bearer("library:read")
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["items"][0]["id"], "book")
        self.assertEqual(response.headers["cache-control"], "private, no-store")

    def test_openapi_contract_matches_declared_operations_and_scopes(self):
        document = openapi_document()
        self.assertEqual(document["openapi"], "3.1.0")
        self.assertEqual(
            set(document["components"]["securitySchemes"]["PATBearer"]["x-scopes"]),
            PAT_SCOPES,
        )
        for operation in public_api_operations():
            declared = document["paths"][operation.path][operation.methods[0].lower()]
            self.assertEqual(
                declared["security"], [{"PATBearer": [operation.required_scope]}]
            )


if __name__ == "__main__":
    unittest.main()
