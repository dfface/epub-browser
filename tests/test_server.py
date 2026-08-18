import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest import mock

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
        with open(os.path.join(self.directory.name, "assets", "manifest.en.json"), "w", encoding="utf-8") as manifest:
            manifest.write("{}")
        with open(os.path.join(self.directory.name, "assets", "manifest.zh-CN.json"), "w", encoding="utf-8") as manifest:
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
                self.assertEqual(response.headers["cache-control"], "no-cache")

    def test_html_is_revalidated_instead_of_long_lived(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["cache-control"], "no-cache")

    def test_starlette_static_errors_return_stable_json_codes(self):
        response = self.client.get("/missing-static-file")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"code": "not_found", "message": "Not Found"})

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
        headers = {"X-Username": "reader"}
        self.client.post("/api/annotations", json=annotation, headers=headers)

        response = self.client.put(
            "/api/annotations/item/misplaced",
            json={
                "chapter_index": 3,
                "startMeta": {"parentTagName": "P", "parentIndex": 0, "textOffset": 1},
                "endMeta": {"parentTagName": "P", "parentIndex": 0, "textOffset": 5},
            },
            headers=headers,
        )

        self.assertEqual(response.status_code, 200)
        repaired = response.json()["data"]
        self.assertEqual(repaired["chapter_index"], 3)
        self.assertEqual(repaired["note"], "keep me")
        self.assertEqual(repaired["startMeta"]["parentIndex"], 0)
        self.assertEqual(self.client.get("/api/annotations/book/1", headers=headers).json()["data"], [])
        self.assertEqual(self.client.get("/api/annotations/book/3", headers=headers).json()["data"][0]["id"], "misplaced")

    def test_browser_api_errors_include_stable_codes_and_compatible_messages(self):
        with TestClient(create_app(self.directory.name), raise_server_exceptions=False) as client:
            with mock.patch("epub_browser.server.sqlite3.connect", side_effect=sqlite3.OperationalError("offline")):
                server_error = client.get("/api/reading-progress/book")

        cases = [
            (self.client.post("/sync", json={}), 400, "username_required"),
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

    def test_reading_progress_isolated_by_username_and_rejects_invalid_chapters(self):
        self.client.put("/api/reading-progress/book", json={"chapter_index": 4})
        named = self.client.put(
            "/api/reading-progress/book",
            json={"chapter_index": 7},
            headers={"X-Username": "reader"},
        )

        self.assertEqual(named.json(), {"chapter_index": 7})
        self.assertEqual(self.client.get("/api/reading-progress/book").json(), {"chapter_index": 4})
        self.assertEqual(
            self.client.get("/api/reading-progress/book", headers={"X-Username": "reader"}).json(),
            {"chapter_index": 7},
        )
        self.assertEqual(
            self.client.put("/api/reading-progress/book", json={"chapter_index": -1}).status_code,
            400,
        )

    def test_two_apps_keep_state_in_their_injected_database(self):
        with tempfile.TemporaryDirectory() as second_directory:
            Path(second_directory, "index.html").write_text(
                "second library",
                encoding="utf-8",
            )
            first_client = TestClient(create_app(self.directory.name))
            second_client = TestClient(create_app(second_directory))

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
        with sqlite3.connect(os.path.join(self.directory.name, "epub-browser.db")) as connection:
            row = connection.execute("SELECT version FROM bookshelves WHERE username = ?", ("reader",)).fetchone()
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

        create_app(legacy_directory.name)

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
            create_app(legacy_directory.name)

        self.assertTrue(os.path.isfile(legacy_path))
        self.assertTrue(os.path.isfile(os.path.join(legacy_directory.name, "epub-browser.db")))
