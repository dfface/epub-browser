import struct
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from starlette.testclient import TestClient

from epub_browser.auth import AuthConfig, AuthService, BootstrapCredentials
from epub_browser.dictionary_service import DictionaryService
from epub_browser.encyclopedia import EncyclopediaSummary
from epub_browser.server import create_app
from epub_browser.state import StateStore


class DictionaryApiTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        (self.root / "index.html").write_text("library", encoding="utf-8")
        self.store = StateStore(self.root / "epub-browser.db")
        self.admin = self.store.initialize(BootstrapCredentials("admin", "correct horse battery staple"))
        self.book = self.store.resolve_book(
            self.root / "book.epub", None, "fingerprint", {"language": "en"}, preferred_book_id="book"
        )
        self.auth = AuthService(self.store, AuthConfig.from_values([]))
        self.app = create_app(self.root, state_store=self.store, auth_service=self.auth)
        self.client = TestClient(self.app)
        self.addCleanup(self.client.close)
        token, csrf = self.auth.create_session(self.admin)
        self.client.cookies.set("epub_browser_session", token)
        self.client.headers["X-CSRF-Token"] = csrf
        self._install_dictionary()

    def _install_dictionary(self):
        base = self.root / "local"
        definition = b"to move quickly"
        index = b"run\0" + struct.pack(">II", 0, len(definition))
        base.with_suffix(".ifo").write_text(
            "StarDict's dict ifo file\nversion=2.4.2\nbookname=Local\nwordcount=1\nidxfilesize=" + str(len(index)) + "\nsametypesequence=m\n", encoding="utf-8"
        )
        base.with_suffix(".idx").write_bytes(index)
        base.with_suffix(".dict").write_bytes(definition)
        service = DictionaryService(self.store, self.root)
        self.dictionary = service.install(base.with_suffix(".ifo"), created_by_user_id=self.admin.user_id)

    def test_dictionary_lookup_requires_acl_and_never_caches_query(self):
        response = self.client.post(
            "/api/books/book/dictionary/lookup",
            json={"text": "run", "dictionary_id": self.dictionary.id},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["cache-control"], "private, no-store")
        self.assertEqual(response.json()["entries"][0]["definition"], "to move quickly")
        anonymous = TestClient(self.app)
        self.addCleanup(anonymous.close)
        self.assertEqual(anonymous.post(
            "/api/books/book/dictionary/lookup",
            json={"text": "run", "dictionary_id": self.dictionary.id},
        ).status_code, 401)

    def test_dictionary_choices_are_book_acl_protected(self):
        response = self.client.get("/api/books/book/dictionaries")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["cache-control"], "private, no-store")
        self.assertEqual(response.json()["dictionaries"], [{
            "id": self.dictionary.id, "display_name": "Local", "entry_count": 1,
        }])

    @mock.patch("epub_browser.server.WikimediaEncyclopedia.lookup")
    def test_encyclopedia_is_separate_from_local_dictionary(self, lookup):
        lookup.return_value = EncyclopediaSummary(True, "Run", "motion", "An act of running", "https://en.wikipedia.org/wiki/Run")
        response = self.client.post("/api/books/book/encyclopedia/lookup", json={"text": "run"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["cache-control"], "private, no-store")
        self.assertEqual(response.json()["title"], "Run")
        lookup.assert_called_once_with("en", "run")


if __name__ == "__main__":
    unittest.main()
