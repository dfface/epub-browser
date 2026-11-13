import json
import tempfile
import unittest
from pathlib import Path

from starlette.testclient import TestClient

from epub_browser.auth import AuthConfig, AuthService, BootstrapCredentials, hash_password
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
        content = self.public / "book" / "book" / "content"
        content.mkdir(parents=True)
        (content / "metadata.json").write_text(
            json.dumps({
                "title": "Visible Book",
                "author": "Author",
                "chapters": [{"title": "Opening", "path": "chapter_0.html"}],
            }),
            encoding="utf-8",
        )
        (content / "toc.json").write_text(
            json.dumps([{"title": "Opening", "href": "chapter_0.html"}]),
            encoding="utf-8",
        )
        (content / "chapter_0.json").write_text(
            json.dumps({
                "index": 0,
                "title": "Opening",
                "content": "<h1>Opening</h1><p>Hello <strong>reader</strong>.</p>",
                "style_links": "",
            }),
            encoding="utf-8",
        )
        self.store.resolve_book(
            self.public / "document.pdf",
            None,
            "pdf-fingerprint",
            {"title": "Visible PDF", "author": "PDF Author"},
            preferred_book_id="pdf",
            source_format="pdf",
        )
        pdf = self.public / "book" / "pdf" / "pdf"
        pdf.mkdir(parents=True)
        (pdf / "metadata.json").write_text(
            json.dumps({
                "title": "Visible PDF",
                "authors": ["PDF Author"],
                "tags": [],
                "language": "en",
                "pages": [
                    {"page_number": 1, "width": 612, "height": 792,
                     "outline_labels": []},
                    {"page_number": 2, "width": 612, "height": 792,
                     "outline_labels": []},
                ],
                "page_count": 2,
                "encrypted": False,
                "has_extractable_text": False,
                "cover": None,
            }),
            encoding="utf-8",
        )
        (self.public / "assets" / "asset-manifest.json").write_text(
            "{}", encoding="utf-8"
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
        self.assertIsNotNone(
            self.store.authenticate_personal_access_token(issued.raw_token)
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
        item = response.json()["items"][0]
        self.assertEqual(item["id"], "book")
        self.assertEqual(item["author"], "Author")
        self.assertEqual(item["authors"], ["Author"])
        self.assertEqual(item["format"], "epub")
        self.assertEqual(response.headers["cache-control"], "private, no-store")

        tag = self.store.create_ai_tag("Managed tag")
        self.store.update_admin_book_settings(
            "book",
            title="Managed API title",
            authors=["First managed author", "Second managed author"],
            visibility="authenticated",
            user_ids=[],
            tag_ids=[tag["id"]],
            profile="auto",
        )
        managed = self.client.get(
            "/api/v1/books/book", headers=self.bearer("library:read")
        ).json()["book"]
        self.assertEqual(managed["title"], "Managed API title")
        self.assertEqual(
            managed["authors"],
            ["First managed author", "Second managed author"],
        )
        self.assertEqual(
            managed["author"],
            "First managed author, Second managed author",
        )
        self.assertEqual(managed["tags"], ["Managed tag"])

    def test_vocabulary_pages_and_token_permissions(self):
        path = "/api/v1/me/vocabulary"
        for index, word in enumerate(("Run", "Runner", "Walk")):
            self.store.record_vocabulary_lookup(
                self.principal, "book", 0, str(index), word, word.casefold()
            )
        self.store.record_vocabulary_lookup(self.principal, "pdf", 0, "pdf", "Run", "run")
        read = self.bearer("vocabulary:read")
        write = self.bearer("vocabulary:read", "vocabulary:write")
        first = self.client.get(path, params={"limit": 1}, headers=read).json()
        self.assertEqual(len(first["items"]), 1)
        second = self.client.get(path, params={"limit": 1, "cursor": first["next_cursor"]}, headers=read).json()
        self.assertNotEqual(first["items"][0]["id"], second["items"][0]["id"])
        self.assertEqual(self.client.get(path, params={"limit": 1, "page": 1}, headers=read).status_code, 400)
        self.assertEqual(self.client.get(path).status_code, 401)
        self.assertEqual(self.client.get(path, headers=self.bearer("library:read")).status_code, 403)
        page = self.client.get(path, params={"q": "RUN", "page_size": 1}, headers=read).json()
        self.assertEqual((page["page"], page["total"], page["total_pages"]), (1, 2, 2))
        self.assertEqual(page["words"][0]["word"], "Run")
        self.assertEqual(page["words"][0]["lookup_count"], 2)
        second = self.client.get(path, params={
            "q": "run", "page_size": 1, "page": 2, "book_id": "book"
        }, headers=read).json()
        self.assertEqual(second["words"][0]["word"], "Run")
        self.assertEqual(second["words"][0]["lookup_count"], 1)
        self.assertEqual(self.client.get(path, params={"page_size": 101}, headers=read).status_code, 400)
        word_path = path + "/" + page["words"][0]["id"]
        self.assertEqual(self.client.patch(word_path, json={"mastery": "learning"}, headers=read).status_code, 403)
        self.assertEqual(self.client.patch(word_path, json={"mastery": "learning"}, headers=write).status_code, 200)
        result = self.client.get(path, params={"mastery": "learning", "page": 1}, headers=read).json()
        self.assertEqual([word["word"] for word in result["words"]], ["Run"])
        other = self.store.create_user("other", None)
        token = self.store.create_personal_access_token(other.user_id, "Other", ("vocabulary:read", "vocabulary:write"), expires_at=None)
        other_headers = {"Authorization": "Bearer " + token.raw_token}
        self.assertEqual(self.client.get(path, headers=other_headers).json(),
                         {"items": [], "next_cursor": None})
        self.assertEqual(self.client.delete(word_path, headers=other_headers).status_code, 404)
        self.assertEqual(self.client.delete(word_path, params={"book_id": "book"}, headers=write).status_code, 204)
        self.assertEqual(self.client.get(path, params={"book_id": "book", "q": "run", "page": 1}, headers=read).json()["total"], 1)
        self.assertEqual(self.client.delete(word_path, headers=write).status_code, 204)
        lookup = {"word": "Run", "book_id": "pdf", "chapter_index": 1, "lookup_id": "retry"}
        self.assertEqual(self.client.post(path, json=lookup, headers=read).status_code, 403)
        for _ in range(2):
            self.assertEqual(self.client.post(path, json=lookup, headers=write).status_code, 204)
        entry = self.client.get(path, params={"book_id": "pdf"}, headers=read).json()["items"][0]
        self.assertEqual((entry["lookup_count"], entry["sources"][0]["chapter_index"]), (1, 1))
        self.assertEqual(self.client.post(path, json={**lookup, "chapter_index": 2}, headers=write).status_code, 400)
        operation = openapi_document()["paths"][path]["get"]
        self.assertEqual({p["name"] for p in operation["parameters"]},
                         {"book_id", "q", "mastery", "page", "page_size", "limit", "cursor"})

    def test_openapi_contract_matches_declared_operations_and_scopes(self):
        document = openapi_document()
        self.assertEqual(document["openapi"], "3.1.0")
        self.assertEqual(
            set(document["components"]["securitySchemes"]["PATBearer"]["x-scopes"]),
            PAT_SCOPES,
        )
        book_schema = document["components"]["schemas"]["Book"]
        self.assertEqual(book_schema["properties"]["authors"]["type"], "array")
        self.assertEqual(book_schema["properties"]["tags"]["type"], "array")
        self.assertTrue(book_schema["properties"]["author"]["deprecated"])
        self.assertEqual(
            document["paths"]["/api/v1/books"]["get"]["responses"]["200"]
            ["content"]["application/json"]["schema"]["$ref"],
            "#/components/schemas/BookList",
        )
        for operation in public_api_operations():
            declared = document["paths"][operation.path][operation.methods[0].lower()]
            self.assertEqual(
                declared["security"], [{"PATBearer": [operation.required_scope]}]
            )

        served = self.client.get("/openapi.json")
        self.assertEqual(served.status_code, 200)
        self.assertEqual(served.json()["openapi"], "3.1.0")
        cached = self.client.get("/openapi.json", headers={"If-None-Match": served.headers["etag"]})
        self.assertEqual(cached.status_code, 304)
        self.assertEqual(cached.content, b"")
        self.assertEqual(self.client.get("/api-docs").status_code, 200)
        self.assertNotIn("/api/books/{book_id}/document", document["paths"])
        self.assertEqual(
            document["components"]["schemas"]["Book"]["properties"]["format"],
            {"enum": ["epub", "pdf"]},
        )

    def test_all_list_operations_expose_the_same_pagination(self):
        headers = self.bearer(
            "library:read", "progress:read", "annotations:read", "reviews:read",
            "vocabulary:read", "admin:data:read",
        )
        document = openapi_document()
        self.store.set_reading_progress(self.principal.user_id, "book", 0)
        self.store.upsert_book_review("book", self.principal.user_id, 5, "Review")
        for path, methods in document["paths"].items():
            get = methods.get("get", {})
            if not get.get("operationId", "").startswith("list"):
                continue
            with self.subTest(path=path):
                parameters = {parameter["name"]: parameter for parameter in get["parameters"]}
                self.assertEqual(parameters["limit"]["schema"]["maximum"], 100)
                self.assertIn("cursor", parameters)
                url = path.format(book_id="pdf", user_id=self.principal.user_id)
                response = self.client.get(url, params={"limit": 1}, headers=headers)
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(set(response.json()), {"items", "next_cursor"})
                self.assertLessEqual(len(response.json()["items"]), 1)
                invalid = self.client.get(url, params={"limit": 101}, headers=headers)
                self.assertEqual(invalid.status_code, 400)
                self.assertEqual(invalid.json()["code"], "invalid_list_query")

        books = self.client.get("/api/v1/books", params={"format": "pdf"}, headers=headers)
        self.assertEqual([book["id"] for book in books.json()["items"]], ["pdf"])
        chapters = self.client.get(
            "/api/v1/books/pdf/chapters", params={"limit": 1, "cursor": "1"}, headers=headers
        ).json()
        self.assertEqual(chapters["items"][0]["index"], 1)
        self.assertIsNone(chapters["next_cursor"])

    def test_api_docs_are_grouped_searchable_and_public(self):
        page = self.client.get("/api-docs")

        self.assertEqual(page.status_code, 200, page.text)
        self.assertEqual(
            page.text.count("data-api-endpoint data-api-search="),
            len(public_api_operations()),
        )
        self.assertIn('id="apiEndpointSearch"', page.text)
        self.assertIn('data-i18n="apiDocs.operation.listBooks"', page.text)
        self.assertIn('data-i18n="apiDocs.exampleListBooks"', page.text)
        self.assertIn('<code dir="ltr">/api/v1</code>', page.text)
        self.assertIn('id="api-group-library"', page.text)
        self.assertIn('id="api-group-admin"', page.text)
        self.assertIn('href="/assets/api-docs.css"', page.text)
        self.assertIn('src="/assets/api-docs.js"', page.text)
        self.assertIn('src="/assets/logo-mark-color.png"', page.text)
        self.assertIn("default-src 'self'", page.headers["content-security-policy"])
        self.assertEqual(page.headers["cache-control"], "public, max-age=300")

    def test_api_docs_show_request_examples_and_parameter_constraints(self):
        page = self.client.get("/api-docs", headers={"Accept-Language": "zh-CN"})
        self.assertEqual(page.status_code, 200)
        self.assertEqual(page.text.count('data-api-endpoint-details'), len(public_api_operations()))
        self.assertIn('data-i18n="apiDocs.param.cursor"', page.text)
        self.assertIn("默认值 24", page.text)
        self.assertIn("1–100", page.text)
        self.assertIn('book_id=BOOK_ID&amp;chapter_index=0', page.text)
        self.assertIn('data-api-copy="api-example-listMyAnnotations"', page.text)
        self.assertIn('--data', page.text)
        self.assertIn('&quot;chapter_index&quot;:0', page.text)

    def test_api_docs_use_the_library_brand_asset_from_the_current_release(self):
        logo_url = "/assets/immutable/logo-mark-color.release.png"
        (self.public / "assets" / "asset-manifest.json").write_text(
            json.dumps({"logo-mark-color.png": logo_url}),
            encoding="utf-8",
        )
        self.assertEqual(
            _json_login(self, self.client, "alice", "secret").status_code,
            200,
        )

        page = self.client.get("/api-docs")

        self.assertEqual(page.status_code, 200, page.text)
        self.assertIn(f'src="{logo_url}"', page.text)
        self.assertNotIn('src="/assets/logo-mark-color.png"', page.text)

    def test_book_detail_toc_and_chapter_content_are_available(self):
        headers = self.bearer("library:read")
        detail = self.client.get("/api/v1/books/book", headers=headers)
        chapters = self.client.get(
            "/api/v1/books/book/chapters", headers=headers
        )
        chapter = self.client.get(
            "/api/v1/books/book/chapters/0", headers=headers
        )

        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["book"]["title"], "Visible Book")
        self.assertEqual(detail.json()["book"]["format"], "epub")
        self.assertEqual(chapters.status_code, 200)
        self.assertEqual(chapters.json()["items"][0]["index"], 0)
        self.assertEqual(chapter.status_code, 200)
        self.assertIn("<strong>reader</strong>", chapter.json()["content_html"])

    def test_pdf_chapters_are_page_chapters_in_public_api(self):
        headers = self.bearer("library:read")
        chapters = self.client.get("/api/v1/books/pdf/chapters", headers=headers)
        response = self.client.get("/api/v1/books/pdf/chapters/1", headers=headers)

        self.assertEqual(chapters.status_code, 200, chapters.text)
        self.assertEqual(chapters.json()["items"], [
            {"index": 0, "title": "Page 1", "format": "pdf", "page_number": 1},
            {"index": 1, "title": "Page 2", "format": "pdf", "page_number": 2},
        ])
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["chapter"], {
            "index": 1,
            "title": "Page 2",
            "format": "pdf",
            "page_number": 2,
            "content_type": "application/pdf-page",
            "content_html": None,
            "text": "",
        })

    def test_raw_pdf_document_is_not_a_pat_operation(self):
        self.assertNotIn("/api/books/{book_id}/document", openapi_document()["paths"])

    def test_chapter_supports_plain_text_and_rejects_unknown_formats(self):
        headers = self.bearer("library:read")
        text = self.client.get(
            "/api/v1/books/book/chapters/0?format=text", headers=headers
        )
        invalid = self.client.get(
            "/api/v1/books/book/chapters/0?format=epub", headers=headers
        )

        self.assertEqual(text.status_code, 200, text.text)
        self.assertEqual(text.headers["content-type"].split(";", 1)[0], "text/plain")
        self.assertEqual(text.text, "Opening\nHello reader.")
        self.assertEqual(invalid.status_code, 400)
        self.assertEqual(invalid.json()["code"], "invalid_format")

    def test_missing_book_is_404_before_content_cache_is_read(self):
        response = self.client.get(
            "/api/v1/books/not-visible/chapters/0",
            headers=self.bearer("library:read"),
        )
        self.assertEqual(response.status_code, 404, response.text)
        self.assertEqual(response.json()["code"], "book_not_found")

    def test_personal_bookshelf_and_progress_require_independent_scopes(self):
        shelf_read = self.bearer("bookshelf:read")
        self.assertEqual(
            self.client.get("/api/v1/me/bookshelf", headers=shelf_read).status_code,
            200,
        )
        denied = self.client.put(
            "/api/v1/me/bookshelf",
            headers=shelf_read,
            json={"version": 0, "data": {"items": ["book"], "groups": {}, "order": []}},
        )
        self.assertEqual(denied.status_code, 403)

        shelf_write = self.bearer("bookshelf:read", "bookshelf:write")
        updated = self.client.put(
            "/api/v1/me/bookshelf",
            headers=shelf_write,
            json={"version": 0, "data": {"items": ["book"], "groups": {}, "order": []}},
        )
        self.assertEqual(updated.status_code, 200, updated.text)
        self.assertEqual(updated.json()["version"], 1)

        progress = self.client.put(
            "/api/v1/me/progress/book",
            headers=self.bearer("progress:read", "progress:write"),
            json={"chapter_index": 0},
        )
        self.assertEqual(progress.status_code, 200, progress.text)
        listing = self.client.get(
            "/api/v1/me/progress", headers=self.bearer("progress:read")
        )
        self.assertEqual(listing.json()["items"][0]["book_id"], "book")

    def test_annotation_pages_filter_by_visible_book_and_chapter(self):
        member = self.store.create_user("reader", None)
        token = self.store.create_personal_access_token(
            member.user_id, "Reader", ("annotations:read",), expires_at=None
        )
        headers = {"Authorization": "Bearer " + token.raw_token}
        path = "/api/v1/me/annotations"
        for identifier, book_id, chapter in (
            ("a", "book", 0), ("b", "book", 0), ("c", "book", 1), ("d", "pdf", 0),
        ):
            self.store.upsert_annotation({
                "id": identifier, "book_hash": book_id, "chapter_index": chapter,
                "text": "Selected", "note": "", "color": "#ffff00",
                "created_at": "2026-08-27T00:00:00Z", "updated_at": "2026-08-27T00:00:00Z",
            }, member.user_id)
        self.store.update_admin_book_settings(
            "pdf", visibility="restricted", user_ids=[], tag_ids=[], profile="auto"
        )

        query = {"book_id": "book", "chapter_index": 0, "limit": 1, "fields": "id"}
        first = self.client.get(path, params=query, headers=headers).json()
        self.assertEqual(first["items"], [{"id": "a"}])
        second = self.client.get(
            path, params={**query, "cursor": first["next_cursor"]}, headers=headers
        ).json()
        self.assertEqual(second, {"items": [{"id": "b"}], "next_cursor": None})
        visible = self.client.get(path, params={"chapter_index": 0}, headers=headers).json()
        self.assertEqual([row["id"] for row in visible["items"]], ["a", "b"])
        for params in ({"limit": 101}, {"cursor": "-1"}, {"chapter_index": -1}, {"fields": "bogus"}):
            response = self.client.get(path, params=params, headers=headers)
            self.assertEqual(response.status_code, 400, response.text)
            self.assertEqual(response.json()["code"], "invalid_list_query")

    def test_annotation_list_defaults_to_a_bounded_page(self):
        for index in range(25):
            self.store.upsert_annotation({
                "id": str(index), "book_hash": "book", "chapter_index": 0,
                "text": "Selected", "note": "", "color": "#ffff00",
                "created_at": "2026-08-27T00:00:00Z", "updated_at": "2026-08-27T00:00:00Z",
            }, self.principal.user_id)
        path = "/api/v1/me/annotations"
        headers = self.bearer("annotations:read")
        first = self.client.get(path, headers=headers).json()
        self.assertEqual(len(first["items"]), 24)
        last = self.client.get(path, params={"cursor": first["next_cursor"]}, headers=headers).json()
        self.assertEqual(len(last["items"]), 1)
        self.assertIsNone(last["next_cursor"])

    def test_annotation_owner_comes_only_from_authenticated_pat(self):
        payload = {
            "id": "external-note",
            "user_id": "someone-else",
            "book_hash": "book",
            "chapter_index": 0,
            "text": "Selected text",
            "note": "My note",
            "color": "#ffff00",
            "created_at": "2026-08-27T00:00:00Z",
            "updated_at": "2026-08-27T00:00:00Z",
        }
        response = self.client.post(
            "/api/v1/me/annotations",
            headers=self.bearer("annotations:read", "annotations:write"),
            json=payload,
        )
        self.assertEqual(response.status_code, 201, response.text)
        stored = self.store.get_annotation(
            "external-note", user_id=self.principal.user_id
        )
        self.assertEqual(stored["note"], "My note")
        self.assertEqual(response.json()["annotation"]["user_id"], self.principal.user_id)

    def test_review_round_trip_includes_user_book_review(self):
        headers = self.bearer("reviews:read", "reviews:write")
        updated = self.client.put(
            "/api/v1/me/reviews/book",
            headers=headers,
            json={"rating": 5, "review_text": "A careful private review."},
        )
        self.assertEqual(updated.status_code, 200, updated.text)
        listing = self.client.get("/api/v1/me/reviews", headers=headers)
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.json()["items"][0]["review_text"], "A careful private review.")

    def test_admin_data_scope_reads_cross_user_reviews_without_credentials(self):
        member = self.store.create_user("bob", hash_password("member-secret"))
        self.store.upsert_book_review(
            "book", member.user_id, 4, "Member's full review text"
        )
        headers = self.bearer("admin:data:read")

        users = self.client.get("/api/v1/admin/users", headers=headers)
        reviews = self.client.get(
            "/api/v1/admin/users/{}/reviews".format(member.user_id),
            headers=headers,
        )

        self.assertEqual(users.status_code, 200, users.text)
        self.assertEqual(reviews.status_code, 200, reviews.text)
        self.assertEqual(reviews.json()["items"][0]["review_text"], "Member's full review text")
        serialized = json.dumps({"users": users.json(), "reviews": reviews.json()})
        self.assertNotIn("password_hash", serialized)
        self.assertNotIn("token_digest", serialized)

    def test_admin_data_namespace_is_read_only_and_requires_current_admin_role(self):
        headers = self.bearer("admin:data:read")
        self.assertEqual(
            self.client.put("/api/v1/admin/users", headers=headers, json={}).status_code,
            405,
        )
        member = self.store.create_user("bob", hash_password("member-secret"))
        member_token = self.store.create_personal_access_token(
            member.user_id, "invalid admin scope", {"admin:data:read"}, expires_at=None
        )
        denied = self.client.get(
            "/api/v1/admin/users",
            headers={"Authorization": "Bearer " + member_token.raw_token},
        )
        self.assertEqual(denied.status_code, 403)

    def test_admin_data_endpoints_cover_all_approved_user_owned_resources(self):
        member = self.store.create_user("bob", hash_password("member-secret"))
        headers = self.bearer("admin:data:read")
        resources = (
            "bookshelf",
            "progress",
            "annotations",
            "reviews",
            "reading-sessions",
            "reading-insights",
            "ai-conversations",
            "ai-results",
        )
        for resource in resources:
            with self.subTest(resource=resource):
                response = self.client.get(
                    "/api/v1/admin/users/{}/{}".format(member.user_id, resource),
                    headers=headers,
                )
                self.assertEqual(response.status_code, 200, response.text)


if __name__ == "__main__":
    unittest.main()
