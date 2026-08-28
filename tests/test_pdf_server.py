import json
import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from pypdf import PdfWriter
from starlette.testclient import TestClient

from epub_browser.auth import (
    AuthConfig,
    AuthService,
    BootstrapCredentials,
    hash_password,
)
from epub_browser.migration import MigrationManager
from epub_browser.server import create_app
from epub_browser.server_library import (
    PDF_OUTPUT_REVISION,
    PDF_OUTPUT_REVISION_FILE,
    ServerLibraryManager,
)
from epub_browser.state import StateStore


def _login(client, username, password):
    page = client.get("/login")
    nonce = re.search(
        r'<meta name="epub-browser-auth-nonce" content="([^"]+)">', page.text
    )
    if page.status_code != 200 or nonce is None:
        raise RuntimeError("login page did not provide an authentication nonce")
    return client.post(
        "/login",
        json={"username": username, "password": password, "next": "/"},
        headers={
            "X-EPUB-Browser-Auth-Nonce": nonce.group(1),
            "Origin": str(client.base_url).rstrip("/"),
            "Sec-Fetch-Site": "same-origin",
        },
    )


class PDFDocumentDeliveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temporary.name)
        cls.server_dir = cls.root / "server"
        cls.sources = cls.root / "sources"
        cls.sources.mkdir()
        cls.source = cls.sources / "reader.pdf"
        writer = PdfWriter()
        writer.add_blank_page(width=320, height=480)
        with cls.source.open("wb") as output:
            writer.write(output)
        cls.original_bytes = cls.source.read_bytes()
        cls.source_stat = cls.source.stat()
        migration = MigrationManager(
            cls.server_dir,
            None,
            bootstrap=BootstrapCredentials("owner", "secret"),
        )
        result = migration.prepare_data()
        cls.store = StateStore(result.database_path)
        cls.manager = ServerLibraryManager(
            server_dir=cls.server_dir,
            sources=(cls.sources,),
            state_store=cls.store,
            migration_manager=migration,
            max_workers=1,
        )
        cls.record = cls.manager.reconcile().active_books[0]
        cls.cached_document = cls.manager.public_dir.joinpath(
            "book", cls.record.book_id, "pdf", "document.pdf"
        )
        cls.app = create_app(
            cls.manager.public_dir,
            state_store=cls.store,
            auth_service=AuthService(cls.store, AuthConfig.from_values([])),
        )
        cls.owner = TestClient(cls.app)
        if _login(cls.owner, "owner", "secret").status_code != 200:
            raise RuntimeError("owner login failed")
        cls.url = f"/api/books/{cls.record.book_id}/document"
        cls.store.create_user("reader", hash_password("reader-secret"))
        cls.store.set_book_visibility(cls.record.book_id, "restricted")
        cls.reader = TestClient(cls.app)
        if _login(cls.reader, "reader", "reader-secret").status_code != 200:
            raise RuntimeError("reader login failed")

    @classmethod
    def tearDownClass(cls):
        cls.reader.close()
        cls.owner.close()
        cls.manager.shutdown()
        cls.temporary.cleanup()

    def test_authenticated_get_returns_the_cached_pdf(self):
        response = self.owner.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, self.original_bytes)
        self.assertEqual(response.headers["content-type"], "application/pdf")
        self.assertEqual(response.headers["accept-ranges"], "bytes")
        self.assertEqual(
            response.headers["content-length"], str(len(self.original_bytes))
        )
        self.assertEqual(response.headers["x-content-type-options"], "nosniff")
        self.assertEqual(response.headers["cache-control"], "private, no-cache")
        self.assertIn(
            'inline; filename="reader.pdf"',
            response.headers["content-disposition"],
        )
        self.assertNotIn(str(self.root), response.headers["content-disposition"])

    def test_head_has_get_headers_without_a_body(self):
        response = self.owner.head(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"")
        self.assertEqual(
            response.headers["content-length"], str(len(self.original_bytes))
        )
        self.assertEqual(response.headers["accept-ranges"], "bytes")

    def test_closed_and_open_ended_ranges_are_bounded(self):
        cases = (
            ("bytes=10-19", 10, self.original_bytes[10:20], "10-19"),
            (
                "bytes=10-",
                len(self.original_bytes) - 10,
                self.original_bytes[10:],
                f"10-{len(self.original_bytes) - 1}",
            ),
            (
                "bytes=-12",
                12,
                self.original_bytes[-12:],
                f"{len(self.original_bytes) - 12}-{len(self.original_bytes) - 1}",
            ),
            (
                "bytes=0-999999",
                len(self.original_bytes),
                self.original_bytes,
                f"0-{len(self.original_bytes) - 1}",
            ),
        )
        for value, length, expected, normalized in cases:
            with self.subTest(value=value):
                response = self.owner.get(self.url, headers={"Range": value})
                self.assertEqual(response.status_code, 206)
                self.assertEqual(response.content, expected)
                self.assertEqual(response.headers["content-length"], str(length))
                self.assertEqual(
                    response.headers["content-range"],
                    f"bytes {normalized}/{len(self.original_bytes)}",
                )

    def test_head_range_has_partial_headers_without_a_body(self):
        response = self.owner.head(self.url, headers={"Range": "bytes=3-7"})

        self.assertEqual(response.status_code, 206)
        self.assertEqual(response.content, b"")
        self.assertEqual(response.headers["content-length"], "5")
        self.assertEqual(
            response.headers["content-range"],
            f"bytes 3-7/{len(self.original_bytes)}",
        )

    def test_invalid_multiple_and_unsatisfiable_ranges_return_416(self):
        for value in (
            "items=0-1",
            "bytes=",
            "bytes=-0",
            "bytes=20-10",
            f"bytes={len(self.original_bytes)}-",
            "bytes=0-1,4-5",
            "bytes= 0-1",
            "bytes=" + "9" * 10000 + "-",
        ):
            with self.subTest(value=value[:40]):
                response = self.owner.get(self.url, headers={"Range": value})
                self.assertEqual(response.status_code, 416)
                self.assertEqual(response.content, b"")
                self.assertEqual(
                    response.headers["content-range"],
                    f"bytes */{len(self.original_bytes)}",
                )
                self.assertEqual(response.headers["content-length"], "0")

    def test_etag_supports_conditional_get_and_precedes_range(self):
        first = self.owner.get(self.url)
        etag = first.headers["etag"]

        response = self.owner.get(
            self.url,
            headers={"If-None-Match": f'W/{etag}, "other"', "Range": "bytes=0-1"},
        )

        self.assertEqual(response.status_code, 304)
        self.assertEqual(response.content, b"")
        self.assertEqual(response.headers["etag"], etag)
        self.assertNotIn("content-range", response.headers)

    def test_unauthenticated_and_inaccessible_books_are_hidden_before_cache_reads(self):
        anonymous = TestClient(self.app)
        self.addCleanup(anonymous.close)
        self.assertEqual(anonymous.get(self.url).status_code, 401)

        hidden = self.cached_document.with_suffix(".hidden")
        self.cached_document.replace(hidden)
        try:
            denied = self.reader.get(self.url)
        finally:
            hidden.replace(self.cached_document)
        self.assertEqual(denied.status_code, 404)
        self.assertNotIn(str(self.root), denied.text)

    def test_changed_source_and_corrupt_cache_are_refused_without_rewriting_cache(self):
        self.source.write_bytes(self.original_bytes + b"changed")
        try:
            changed = self.owner.get(self.url)
            self.assertEqual(changed.status_code, 409)
            self.assertEqual(self.cached_document.read_bytes(), self.original_bytes)
            self.assertNotIn(str(self.source), changed.text)
        finally:
            self.source.write_bytes(self.original_bytes)
            os.utime(
                self.source,
                ns=(self.source_stat.st_atime_ns, self.source_stat.st_mtime_ns),
            )

        self.cached_document.write_bytes(b"corrupt")
        try:
            corrupt = self.owner.get(self.url)
            self.assertEqual(corrupt.status_code, 409)
            self.assertNotIn(str(self.cached_document), corrupt.text)
        finally:
            self.cached_document.write_bytes(self.original_bytes)

    def test_outdated_revision_and_metadata_schema_are_refused(self):
        book_root = self.cached_document.parent.parent
        revision = book_root / PDF_OUTPUT_REVISION_FILE
        metadata_path = self.cached_document.parent / "metadata.json"
        original_metadata = metadata_path.read_text(encoding="utf-8")

        revision.write_text("outdated\n", encoding="utf-8")
        try:
            self.assertEqual(self.owner.get(self.url).status_code, 409)
        finally:
            revision.write_text(PDF_OUTPUT_REVISION + "\n", encoding="utf-8")

        metadata = json.loads(original_metadata)
        metadata["schema_version"] = -1
        metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
        try:
            self.assertEqual(self.owner.get(self.url).status_code, 409)
        finally:
            metadata_path.write_text(original_metadata, encoding="utf-8")

    def test_delivery_never_uses_path_read_bytes_or_exposes_a_pat_route(self):
        with mock.patch.object(
            Path,
            "read_bytes",
            side_effect=AssertionError("whole-file reads are forbidden"),
        ):
            response = self.owner.get(self.url, headers={"Range": "bytes=0-3"})
        self.assertEqual(response.status_code, 206)
        self.assertEqual(response.content, self.original_bytes[:4])
        self.assertNotEqual(
            self.owner.get(f"/api/v1/books/{self.record.book_id}/document").status_code,
            200,
        )

    def test_non_read_methods_are_rejected_by_the_exact_route(self):
        csrf = self.owner.get("/api/session").json()["csrf_token"]
        response = self.owner.post(
            self.url,
            headers={"X-CSRF-Token": csrf},
            content=b"ignored",
        )

        self.assertEqual(response.status_code, 405)
        self.assertEqual(response.headers["allow"], "GET, HEAD")


class SingleRangeParserTests(unittest.TestCase):
    def test_normalizes_full_suffix_and_open_ended_ranges(self):
        from epub_browser.pdf_delivery import ByteRange, parse_single_range

        self.assertIsNone(parse_single_range(None, 20))
        self.assertEqual(parse_single_range("bytes=3-7", 20), ByteRange(3, 7))
        self.assertEqual(parse_single_range("bytes=15-", 20), ByteRange(15, 19))
        self.assertEqual(parse_single_range("bytes=-50", 20), ByteRange(0, 19))

    def test_rejects_ranges_for_an_empty_document(self):
        from epub_browser.pdf_delivery import RangeNotSatisfiable, parse_single_range

        with self.assertRaises(RangeNotSatisfiable) as caught:
            parse_single_range("bytes=0-0", 0)
        self.assertEqual(caught.exception.size, 0)


if __name__ == "__main__":
    unittest.main()
