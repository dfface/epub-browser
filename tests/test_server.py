import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest

from starlette.testclient import TestClient

from epub_browser.server import create_app


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
        with open(os.path.join(self.directory.name, "sw.js"), "w", encoding="utf-8") as worker:
            worker.write("self.addEventListener('fetch', () => {})")
        os.makedirs(os.path.join(self.directory.name, "book", "demo", "resources"))
        with open(os.path.join(self.directory.name, "book", "demo", "index.html"), "w", encoding="utf-8") as book_index:
            book_index.write("book")
        with open(os.path.join(self.directory.name, "book", "demo", "chapter_0.html"), "w", encoding="utf-8") as chapter:
            chapter.write("chapter")
        with open(os.path.join(self.directory.name, "book", "demo", "resources", "cover.webp"), "wb") as cover:
            cover.write(b"cover")
        self.client = TestClient(create_app(self.directory.name))

    def tearDown(self):
        self.directory.cleanup()

    def test_immutable_assets_are_long_lived_and_validate_with_etag(self):
        response = self.client.get("/assets/immutable/app.0123456789ab.js")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["cache-control"], "public, max-age=31536000, immutable")
        self.assertIn("etag", response.headers)

        cached = self.client.get("/assets/immutable/app.0123456789ab.js", headers={"If-None-Match": response.headers["etag"]})
        self.assertEqual(cached.status_code, 304)

    def test_mutable_assets_and_worker_revalidate(self):
        for path in ("/assets/cover.webp", "/assets/manifest.json", "/sw.js"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.headers["cache-control"], "no-cache")

    def test_html_is_revalidated_instead_of_long_lived(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["cache-control"], "no-cache")

    def test_book_resources_are_cached_while_book_pages_revalidate(self):
        book_page = self.client.get("/book/demo/index.html")
        chapter_page = self.client.get("/book/demo/chapter_0.html")
        cover = self.client.get("/book/demo/resources/cover.webp")

        self.assertEqual(book_page.headers["cache-control"], "no-cache")
        self.assertEqual(chapter_page.headers["cache-control"], "no-cache")
        self.assertEqual(cover.headers["cache-control"], "public, max-age=2592000")

    def test_annotation_routes_preserve_create_and_read_behavior(self):
        annotation = {"id": "a1", "book_hash": "book", "chapter_index": 1, "text": "note", "color": "#fff", "created_at": "2026-01-01", "updated_at": "2026-01-01"}
        created = self.client.post("/api/annotations", json=annotation, headers={"X-Username": "reader"})
        fetched = self.client.get("/api/annotations/book/1", headers={"X-Username": "reader"})

        self.assertEqual(created.status_code, 201)
        self.assertEqual(fetched.json()["data"][0]["id"], "a1")

    def test_sync_route_preserves_new_shelf_response(self):
        response = self.client.post("/sync", json={"username": "reader", "version": 1, "data": {"items": []}})

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["version"], 1)

    def test_sync_returns_not_modified_when_versions_match(self):
        payload = {"username": "reader", "version": 1, "data": {"items": []}}
        self.client.post("/sync", json=payload)

        response = self.client.post("/sync", json=payload)

        self.assertEqual(response.status_code, 304)

    def test_sync_persists_the_shelf_in_sqlite(self):
        payload = {"username": "reader", "version": 2, "data": {"items": ["book-a"], "groups": {}}}

        response = self.client.post("/sync", json=payload)

        self.assertEqual(response.status_code, 404)
        with sqlite3.connect(os.path.join(self.directory.name, "annotations.db")) as connection:
            row = connection.execute(
                "SELECT version, data FROM bookshelves WHERE username = ?", ("reader",)
            ).fetchone()
        self.assertEqual(row, (2, json.dumps(payload["data"], ensure_ascii=False)))

    def test_sync_returns_the_sqlite_shelf_to_an_older_client(self):
        self.client.post("/sync", json={"username": "reader", "version": 3, "data": {"items": ["server"], "groups": {}}})

        response = self.client.post("/sync", json={"username": "reader", "version": 2, "data": {"items": ["client"], "groups": {}}})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"message": "Server has newer or same version", "version": 3, "data": {"items": ["server"], "groups": {}}})

    def test_sync_imports_the_highest_version_legacy_shelf_once(self):
        Path(self.directory.name, "epub-browser-bookshelf-reader-2.json").write_text('{"items":["old"],"groups":{}}', encoding="utf-8")
        Path(self.directory.name, "epub-browser-bookshelf-reader-4.json").write_text('{"items":["new"],"groups":{}}', encoding="utf-8")

        response = self.client.post("/sync", json={"username": "reader", "version": 1, "data": {"items": [], "groups": {}}})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["version"], 4)
        self.assertEqual(response.json()["data"]["items"], ["new"])
        with sqlite3.connect(os.path.join(self.directory.name, "annotations.db")) as connection:
            row = connection.execute("SELECT version FROM bookshelves WHERE username = ?", ("reader",)).fetchone()
        self.assertEqual(row, (4,))
