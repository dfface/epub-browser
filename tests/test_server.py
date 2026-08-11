import os
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
        self.client = TestClient(create_app(self.directory.name))

    def tearDown(self):
        self.directory.cleanup()

    def test_static_cover_is_cacheable_and_validates_with_etag(self):
        response = self.client.get("/assets/cover.webp")

        self.assertEqual(response.status_code, 200)
        self.assertIn("public", response.headers["cache-control"])
        self.assertIn("etag", response.headers)

        cached = self.client.get("/assets/cover.webp", headers={"If-None-Match": response.headers["etag"]})
        self.assertEqual(cached.status_code, 304)

    def test_html_is_revalidated_instead_of_long_lived(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["cache-control"], "no-cache")

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
