"""Tests for the server-only full-book search index and API."""

import json
import os
import tempfile
import unittest
from pathlib import Path

from starlette.testclient import TestClient

from epub_browser.auth import AuthConfig, AuthService
from epub_browser.book_search import (
    BookSearchIndexStore,
    SearchGeneration,
    build_book_search_index,
    extract_search_text,
    normalize_search_query,
    query_book_search_index,
)
from epub_browser.processor import SERVER_OUTPUT_REVISION, SERVER_OUTPUT_REVISION_FILE
from epub_browser.server import create_app
from epub_browser.source_format import PDF_FORMAT
from epub_browser.state import BootstrapCredentials, StateStore
from tests.test_server import _json_login


class _Renderer:
    def __init__(self, chapters):
        self.chapters = chapters

    def chapter_count(self):
        return len(self.chapters)

    def chapter_content(self, index):
        title, content = self.chapters[index]
        return {"index": index, "title": title, "content": content, "style_links": ""}


class TextExtractionTests(unittest.TestCase):
    def test_extracts_visible_text_and_collapses_block_whitespace(self):
        markup = (
            "<p>Hello <b>world</b></p><p>  next  </p>"
            "<script>bad()</script><p>x<br>y</p>"
        )

        self.assertEqual(extract_search_text(markup), "Hello world next x y")

    def test_query_is_literal_and_whitespace_normalized(self):
        self.assertEqual(normalize_search_query("  Hello \n world "), "Hello world")
        self.assertIsNone(normalize_search_query(""))
        self.assertIsNone(normalize_search_query("x" * 129))
        self.assertIsNone(normalize_search_query("bad\x00query"))
        self.assertIsNone(normalize_search_query(["not", "a", "string"]))


class IndexQueryTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "index.sqlite3"
        self.generation = SearchGeneration("rev", "fp", 1, 2)
        self.renderer = _Renderer([
            ("Intro", "<p>Hello <b>world</b></p><p>😀甲乙&amp;字 甲乙</p>"),
            ("Second", "<div>HELLO <span>world</span></div><p>Straße</p>"),
            ("Empty", "<p> </p>"),
        ])
        build_book_search_index(self.path, self.renderer, self.generation)

    def test_literal_hits_use_original_utf16_offsets(self):
        payload = query_book_search_index(self.path, "甲乙")

        self.assertEqual(payload["total"], 2)
        self.assertEqual(payload["page"], 1)
        first, second = payload["results"]
        self.assertEqual((first["start_offset"], first["end_offset"]), (14, 16))
        self.assertEqual(first["before"], "Hello world 😀")
        self.assertEqual(first["match"], "甲乙")
        self.assertEqual(first["after"], "&字 甲乙")
        self.assertEqual((second["start_offset"], second["end_offset"]), (19, 21))

    def test_casefold_matching_and_fts_fallback_agree(self):
        with_fts = query_book_search_index(self.path, "STRASSE")
        without_fts = query_book_search_index(self.path, "STRASSE", use_fts=False)

        self.assertEqual(with_fts, without_fts)
        self.assertEqual(with_fts["results"][0]["match"], "Straße")

    def test_missing_index_meta_is_not_a_generation_match(self):
        from epub_browser.book_search import index_matches_generation

        self.assertTrue(index_matches_generation(self.path, self.generation))
        self.assertFalse(
            index_matches_generation(
                self.path, SearchGeneration("other", "fp", 1, 2)
            )
        )

    def test_pages_through_every_result(self):
        renderer = _Renderer([("Many", "<p>" + ("x " * 60) + "</p>")])
        build_book_search_index(self.path, renderer, self.generation)

        first = query_book_search_index(self.path, "x")
        second = query_book_search_index(self.path, "x", page=2)

        self.assertEqual(first["total"], 60)
        self.assertEqual(first["page_size"], 50)
        self.assertEqual(len(first["results"]), 50)
        self.assertEqual(second["page"], 2)
        self.assertEqual(len(second["results"]), 10)
        offsets = [hit["start_offset"] for hit in first["results"] + second["results"]]
        self.assertEqual(len(offsets), 60)
        self.assertEqual(offsets, sorted(offsets))

    def test_snippet_context_cuts_at_word_boundaries(self):
        prefix = "alpha " * 7
        suffix = " omega" * 10
        renderer = _Renderer([("Words", f"<p>{prefix}target{suffix}</p>")])
        build_book_search_index(self.path, renderer, self.generation)

        hit = query_book_search_index(self.path, "target")["results"][0]

        self.assertTrue(hit["before"].endswith("alpha "))
        self.assertEqual(hit["before"].split()[0], "alpha")
        self.assertTrue(hit["after"].endswith("omega"))


class BookSearchIndexStoreTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name) / "search"

    def test_lru_trim_removes_least_recently_used_indexes(self):
        store = BookSearchIndexStore(self.root, limit=lambda: 1)
        generation = SearchGeneration("rev", "fp", 1, 2)
        store.search(
            "alpha", "hello", generation, _Renderer([("A", "<p>hello</p>")])
        )
        first = store.path_for("alpha")
        os.utime(first, ns=(1, 1))

        store.search(
            "beta", "hello", generation, _Renderer([("B", "<p>hello</p>")])
        )

        self.assertFalse(first.exists())
        self.assertTrue(store.path_for("beta").exists())

    def test_generation_change_rebuilds_stale_index(self):
        store = BookSearchIndexStore(self.root, limit=lambda: 5)
        old = SearchGeneration("rev", "fp", 1, 2)
        new = SearchGeneration("rev2", "fp", 3, 4)
        store.search("alpha", "old", old, _Renderer([("A", "<p>old text</p>")]))

        payload = store.search(
            "alpha", "new", new, _Renderer([("A", "<p>new text</p>")])
        )

        self.assertEqual(payload["results"][0]["match"], "new")


class _BookSearchApiBase(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.public = Path(self.directory.name) / "public"
        self.public.mkdir()
        (self.public / "assets").mkdir()
        self.store = StateStore(Path(self.directory.name) / "state.db")
        self.store.initialize(bootstrap=BootstrapCredentials("alice", "secret"))
        self.store.resolve_book(
            self.public / "book.epub",
            None,
            "book-fingerprint",
            {"title": "Book"},
            preferred_book_id="book",
        )
        self._write_book("book", "<p>Hello <b>world</b></p>")
        self.auth = AuthService(self.store, AuthConfig.from_values([]))
        self.app = create_app(
            self.public,
            state_store=self.store,
            auth_service=self.auth,
        )
        self.client = TestClient(self.app, follow_redirects=False)

    def _write_book(self, book_id, content):
        directory = self.public / "book" / book_id
        content_dir = directory / "content"
        content_dir.mkdir(parents=True)
        (directory / SERVER_OUTPUT_REVISION_FILE).write_text(
            str(SERVER_OUTPUT_REVISION), encoding="utf-8"
        )
        (content_dir / "metadata.json").write_text(
            json.dumps({"chapters": [{"title": "One", "href": "chapter_0.html"}]}),
            encoding="utf-8",
        )
        (content_dir / "chapter_0.json").write_text(
            json.dumps({
                "index": 0,
                "title": "One",
                "content": content,
                "style_links": "",
            }),
            encoding="utf-8",
        )

    def _login(self):
        response = _json_login(self, self.client, "alice", "secret")
        self.assertEqual(response.status_code, 200)


class BookSearchApiTests(_BookSearchApiBase):
    def test_requires_authentication(self):
        response = self.client.get("/api/books/book/search?q=hello")

        self.assertEqual(response.status_code, 401)

    def test_rejects_malformed_queries(self):
        self._login()

        missing = self.client.get("/api/books/book/search")
        duplicated = self.client.get("/api/books/book/search?q=a&q=b")
        empty = self.client.get("/api/books/book/search?q=%20%20")
        too_long = self.client.get("/api/books/book/search?q=" + "x" * 129)

        for response in (missing, duplicated, empty, too_long):
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.json()["code"], "invalid_book_search_query")
            self.assertEqual(response.headers["cache-control"], "private, no-store")

    def test_returns_uncached_results_for_an_authorized_reader(self):
        self._login()

        response = self.client.get("/api/books/book/search?q=world")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["cache-control"], "private, no-store")
        payload = response.json()
        self.assertEqual(payload["total"], 1)
        self.assertEqual(payload["page"], 1)
        self.assertEqual(payload["page_size"], 50)
        self.assertEqual(payload["results"][0]["match"], "world")
        self.assertEqual(payload["results"][0]["chapter_title"], "One")

    def test_paginates_and_rejects_invalid_pages(self):
        self._login()

        page = self.client.get("/api/books/book/search?q=world&page=2")

        self.assertEqual(page.status_code, 200)
        self.assertEqual(page.json()["page"], 2)
        self.assertEqual(page.json()["results"], [])

        for value in ("0", "-1", "abc", "1.5"):
            invalid = self.client.get(f"/api/books/book/search?q=world&page={value}")
            self.assertEqual(invalid.status_code, 400)
            self.assertEqual(invalid.json()["code"], "invalid_book_search_page")

    def test_hides_pdf_books(self):
        self.store.resolve_book(
            self.public / "document.pdf",
            None,
            "pdf-fingerprint",
            {"title": "PDF"},
            preferred_book_id="pdfbook",
            source_format=PDF_FORMAT,
        )
        self._login()

        response = self.client.get("/api/books/pdfbook/search?q=hello")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["code"], "not_found")


class BookSearchCacheSettingsTests(unittest.TestCase):
    def test_general_settings_include_search_index_cache_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            store = StateStore(Path(directory) / "state.db")
            store.initialize(bootstrap=BootstrapCredentials("alice", "secret"))

            self.assertEqual(store.get_general_settings()["search_index_cache_limit"], 20)
            updated = store.set_general_settings(search_index_cache_limit=5)
            self.assertEqual(updated["search_index_cache_limit"], 5)
            with self.assertRaises(ValueError):
                store.set_general_settings(search_index_cache_limit=0)
