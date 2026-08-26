import io
import struct
import tempfile
import unittest
import zipfile
from pathlib import Path
from urllib.parse import quote
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
        self.assertEqual(response.json(), {
            "default_dictionary_id": self.dictionary.id,
            "dictionaries": [{
            "id": self.dictionary.id, "display_name": "Local", "entry_count": 1,
            }],
        })

    def test_admin_can_change_the_default_dictionary(self):
        base = self.root / "alternate"
        definition = b"to travel quickly"
        index = b"run\0" + struct.pack(">II", 0, len(definition))
        base.with_suffix(".ifo").write_text(
            "StarDict's dict ifo file\nversion=2.4.2\nbookname=Alternate\nwordcount=1\n"
            "idxfilesize=" + str(len(index)) + "\nsametypesequence=m\n", encoding="utf-8"
        )
        base.with_suffix(".idx").write_bytes(index)
        base.with_suffix(".dict").write_bytes(definition)
        alternate = DictionaryService(self.store, self.root).install(
            base.with_suffix(".ifo"), created_by_user_id=self.admin.user_id,
        )

        changed = self.client.put("/api/admin/dictionaries/" + alternate.id + "/default")

        self.assertEqual(changed.status_code, 200)
        self.assertTrue(changed.json()["dictionary"]["is_default"])
        choices = self.client.get("/api/books/book/dictionaries").json()
        self.assertEqual(choices["default_dictionary_id"], alternate.id)
        self.assertEqual(choices["dictionaries"][0]["id"], alternate.id)

        disabled = self.client.put(
            "/api/admin/dictionaries/" + alternate.id, json={"enabled": False},
        )
        self.assertEqual(disabled.status_code, 200)
        choices = self.client.get("/api/books/book/dictionaries").json()
        self.assertEqual(choices["default_dictionary_id"], self.dictionary.id)

    def test_admin_can_rename_a_dictionary(self):
        renamed = self.client.put(
            "/api/admin/dictionaries/" + self.dictionary.id,
            json={"display_name": "Fast English"},
        )

        self.assertEqual(renamed.status_code, 200)
        self.assertEqual(renamed.json()["dictionary"]["display_name"], "Fast English")
        self.assertEqual(
            self.client.get("/api/admin/dictionaries").json()["dictionaries"][0]["display_name"],
            "Fast English",
        )

        invalid = self.client.put(
            "/api/admin/dictionaries/" + self.dictionary.id,
            json={"display_name": "   "},
        )
        self.assertEqual(invalid.status_code, 400)
        self.assertEqual(invalid.json()["code"], "invalid_dictionary_name")

    def test_admin_upload_decodes_a_unicode_filename_as_the_default_name(self):
        definition = b"a different definition"
        index = b"word\0" + struct.pack(">II", 0, len(definition))
        payload = io.BytesIO()
        with zipfile.ZipFile(payload, "w") as archive:
            archive.writestr(
                "inner.ifo",
                "StarDict's dict ifo file\nversion=2.4.2\nbookname=Inner\nwordcount=1\n"
                "idxfilesize=" + str(len(index)) + "\nsametypesequence=m\n",
            )
            archive.writestr("inner.idx", index)
            archive.writestr("inner.dict", definition)

        response = self.client.post(
            "/api/admin/dictionaries", content=payload.getvalue(),
            headers={
                "content-type": "application/zip",
                "x-epub-browser-dictionary-filename": quote("现代汉语词典.zip"),
                "x-epub-browser-dictionary-name": "",
                "x-epub-browser-dictionary-format": "stardict",
            },
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["dictionary"]["display_name"], "现代汉语词典")

    def test_stardict_html_package_assets_are_available_to_the_reader(self):
        definition = b'<link rel="stylesheet" href="styles/entry.css"><img src="images/run.png"><script src="entry.js"></script>'
        index = b"run\0" + struct.pack(">II", 0, len(definition))
        payload = io.BytesIO()
        with zipfile.ZipFile(payload, "w") as archive:
            archive.writestr(
                "package/sample.ifo",
                "StarDict's dict ifo file\nversion=2.4.2\nbookname=HTML\nwordcount=1\n"
                "idxfilesize=" + str(len(index)) + "\nsametypesequence=h\n",
            )
            archive.writestr("package/sample.idx", index)
            archive.writestr("package/sample.dict", definition)
            archive.writestr("package/styles/entry.css", ".entry{color:#123456}")
            archive.writestr("package/images/run.png", b"\x89PNG\r\n\x1a\nimage-data")
            archive.writestr("package/entry.js", "window.packageScript = true;")

        created = self.client.post(
            "/api/admin/dictionaries", content=payload.getvalue(),
            headers={
                "content-type": "application/zip",
                "x-epub-browser-dictionary-filename": "html.zip",
                "x-epub-browser-dictionary-format": "stardict",
            },
        )

        self.assertEqual(created.status_code, 201)
        dictionary_id = created.json()["dictionary"]["id"]
        lookup = self.client.post(
            "/api/books/book/dictionary/lookup", json={"text": "run", "dictionary_id": dictionary_id},
        )
        self.assertEqual(lookup.json()["asset_base_path"], "package")
        self.assertFalse(lookup.json()["allow_scripts"])
        self.assertEqual(lookup.json()["entries"][0]["definition_format"], "stardict:h")
        self.assertEqual(self.client.get(
            "/api/books/book/dictionaries/" + dictionary_id + "/assets/package/styles/entry.css",
        ).status_code, 200)
        self.assertEqual(self.client.get(
            "/api/books/book/dictionaries/" + dictionary_id + "/assets/package/images/run.png",
        ).headers["content-type"], "image/png")
        self.assertEqual(self.client.put(
            "/api/admin/dictionaries/" + dictionary_id, json={"allow_scripts": True},
        ).json()["dictionary"]["allow_scripts"], True)

    def test_admin_can_disable_and_delete_a_dictionary(self):
        disabled = self.client.put(
            "/api/admin/dictionaries/" + self.dictionary.id, json={"enabled": False},
        )
        self.assertEqual(disabled.status_code, 200)
        self.assertFalse(disabled.json()["dictionary"]["enabled"])
        self.assertEqual(self.client.get("/api/books/book/dictionaries").json()["dictionaries"], [])

        deleted = self.client.delete("/api/admin/dictionaries/" + self.dictionary.id)
        self.assertEqual(deleted.status_code, 204)
        self.assertEqual(self.client.get("/api/admin/dictionaries").json()["dictionaries"], [])

    def test_mdict_package_assets_are_acl_protected(self):
        try:
            from mdict_utils.base.writemdict import MDictWriter
        except ImportError:
            self.skipTest("mdict-utils is installed with the server dependency")
        mdx = io.BytesIO()
        MDictWriter(
            {"run": "to move<img src=\"file://\\\\images\\\\run.png\">"},
            title="Media", description="", compression_type=2, version="2.0",
        ).write(mdx)
        mdd = io.BytesIO()
        MDictWriter(
            {"\\\\images\\\\run.png": b"\x89PNG\r\n\x1a\nimage-data"},
            title="Media", description="", compression_type=2, version="2.0", is_mdd=True,
        ).write(mdd)
        package = io.BytesIO()
        with zipfile.ZipFile(package, "w") as archive:
            archive.writestr("media/media.mdx", mdx.getvalue())
            archive.writestr("media/media.mdd", mdd.getvalue())
        created = self.client.post(
            "/api/admin/dictionaries", content=package.getvalue(),
            headers={
                "content-type": "application/zip",
                "x-epub-browser-dictionary-filename": quote("media.zip"),
                "x-epub-browser-dictionary-format": "mdict",
            },
        )
        self.assertEqual(created.status_code, 201)
        dictionary_id = created.json()["dictionary"]["id"]

        lookup = self.client.post(
            "/api/books/book/dictionary/lookup", json={"text": "run", "dictionary_id": dictionary_id},
        )
        self.assertEqual(lookup.json()["asset_base_path"], "media")
        media = self.client.get(
            "/api/books/book/dictionaries/" + dictionary_id + "/assets/media/images/run.png",
        )
        self.assertEqual(media.status_code, 200)
        self.assertEqual(media.headers["content-type"], "image/png")
        self.assertEqual(media.headers["cache-control"], "private, no-store")
        self.assertEqual(media.content, b"\x89PNG\r\n\x1a\nimage-data")
        anonymous = TestClient(self.app)
        self.addCleanup(anonymous.close)
        self.assertEqual(anonymous.get(
            "/api/books/book/dictionaries/" + dictionary_id + "/assets/media/images/run.png",
        ).status_code, 401)

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
