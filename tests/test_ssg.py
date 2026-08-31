import contextlib
import io
import json
import re
import shutil
import tempfile
import unittest
import zipfile
from html.parser import HTMLParser
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from pypdf import PdfWriter

from epub_browser.cli import SSGConfig
from epub_browser.epub_identity import read_embedded_book_id
from epub_browser.reporting import Reporter
from epub_browser.sidecar_identity import read_exact_sidecar, sidecar_path_for
from epub_browser.ssg import SSGBuildError, SSGPublisher, run_ssg


class SSGPublicationTests(unittest.TestCase):
    def test_discovery_accepts_epub_and_pdf_case_insensitively(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sources = root / "books"
            sources.mkdir()
            self._write_minimal_epub(
                sources / "one.EPUB", identifier="urn:test:discovery"
            )
            (sources / "two.PDF").write_bytes(b"%PDF-1.4\n%%EOF\n")
            (sources / "ignored.txt").write_text("ignored", encoding="utf-8")
            publisher = SSGPublisher(
                SSGConfig((sources,), root / "dist"), show_progress=False
            )

            discovered = publisher._discover_sources()

            self.assertEqual(
                {path.name for path in discovered}, {"one.EPUB", "two.PDF"}
            )

    def test_embedded_storage_reports_pdf_sidecar_fallback_once(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "one.pdf"
            second = root / "two.PDF"
            first.write_bytes(b"%PDF-1.4\none\n%%EOF\n")
            second.write_bytes(b"%PDF-1.4\ntwo\n%%EOF\n")
            publisher = SSGPublisher(
                SSGConfig(
                    (first, second),
                    root / "dist",
                    log=True,
                    book_id_storage="embedded",
                ),
                reporter=Reporter(True),
                show_progress=False,
            )

            with contextlib.redirect_stderr(io.StringIO()) as stderr:
                publisher._discover_sources()

            output = stderr.getvalue()
            self.assertEqual(output.count("Embedded book ID storage is EPUB-only"), 1)
            self.assertIn("PDF identities use adjacent sidecars", output)

    def test_pdf_ssg_writes_one_shared_chapter_per_page(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "book.PDF"
            output = root / "dist"
            self._write_pdf(source, pages=3)
            before = source.read_bytes()

            SSGPublisher(
                SSGConfig((source,), output, "/reader/", book_id_storage="embedded"),
                show_progress=False,
            ).build()

            metadata = json.loads(
                (output / "book-metadata.json").read_text(encoding="utf-8")
            )
            book_id = metadata[0]["hash"]
            book = output / "book" / book_id
            toc = json.loads((book / "toc.json").read_text(encoding="utf-8"))
            chapter_names = sorted(path.name for path in book.glob("chapter_*.html"))
            chapter_html = (book / "chapter_0.html").read_text(encoding="utf-8")
            index_html = (book / "index.html").read_text(encoding="utf-8")

            self.assertEqual(source.read_bytes(), before)
            self.assertEqual((book / "document.pdf").read_bytes(), before)
            self.assertEqual(
                chapter_names,
                ["chapter_0.html", "chapter_1.html", "chapter_2.html"],
            )
            self.assertEqual(
                [item["chapter_file"] for item in toc],
                ["chapter_0.html", "chapter_1.html", "chapter_2.html"],
            )
            self.assertEqual([item["chapter_index"] for item in toc], [0, 1, 2])
            self.assertFalse((book / "reader.html").exists())
            self.assertTrue((book / "cover.png").is_file())
            with Image.open(book / "cover.png") as image:
                self.assertLessEqual(image.width, 600)
                self.assertLessEqual(image.height, 900)
            self.assertIn('href="/reader/book/{}/chapter_0.html"'.format(book_id), index_html)
            self.assertIn('"documentUrl":"/reader/book/{}/document.pdf"'.format(book_id), chapter_html)
            self.assertNotIn("/api/", chapter_html)
            self.assertNotIn("reading-sessions.js", chapter_html)
            self.assertEqual(metadata[0]["format"], "pdf")
            self.assertEqual(metadata[0]["cover"], "/reader/book/{}/cover.png".format(book_id))
            sidecar = read_exact_sidecar(source)
            self.assertIsNotNone(sidecar)
            self.assertEqual(sidecar.book_id, book_id)

    def test_failed_pdf_output_does_not_persist_identity_or_partial_book(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "book.pdf"
            output = root / "dist"
            self._write_pdf(source, pages=2)
            before = source.read_bytes()

            with patch(
                "epub_browser.ssg.render_pdf_cover",
                side_effect=RuntimeError("cover exploded"),
            ):
                with self.assertRaisesRegex(SSGBuildError, "cover exploded"):
                    SSGPublisher(
                        SSGConfig((source,), output), show_progress=False
                    ).build()

            self.assertEqual(source.read_bytes(), before)
            self.assertFalse(sidecar_path_for(source).exists())
            self.assertFalse(output.exists())
            self.assertEqual(list(root.glob(".dist.staging-*")), [])

    def test_failed_pdf_activation_removes_a_new_identity_sidecar(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "book.pdf"
            output = root / "dist"
            self._write_pdf(source, pages=1)
            publisher = SSGPublisher(
                SSGConfig((source,), output), show_progress=False
            )

            with patch.object(
                publisher, "_activate", side_effect=RuntimeError("activation exploded")
            ):
                with self.assertRaisesRegex(RuntimeError, "activation exploded"):
                    publisher.build()

            self.assertFalse(sidecar_path_for(source).exists())
            self.assertFalse(output.exists())

    def test_failed_pdf_activation_restores_an_adopted_orphan_sidecar(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old_source = root / "old.pdf"
            source = root / "renamed.pdf"
            output = root / "dist"
            self._write_pdf(old_source, pages=1)
            SSGPublisher(
                SSGConfig((old_source,), root / "seed"), show_progress=False
            ).build()
            orphan = sidecar_path_for(old_source)
            orphan_bytes = orphan.read_bytes()
            old_source.rename(source)
            publisher = SSGPublisher(
                SSGConfig((source,), output), show_progress=False
            )

            with patch.object(
                publisher, "_activate", side_effect=RuntimeError("activation exploded")
            ):
                with self.assertRaisesRegex(RuntimeError, "activation exploded"):
                    publisher.build()

            self.assertEqual(orphan.read_bytes(), orphan_bytes)
            self.assertFalse(sidecar_path_for(source).exists())
            self.assertFalse(output.exists())

    def test_failed_pdf_activation_restores_an_existing_sidecar_exactly(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "book.pdf"
            output = root / "dist"
            self._write_pdf(source, pages=1)
            SSGPublisher(
                SSGConfig((source,), output), show_progress=False
            ).build()
            original_output = (output / "index.html").read_bytes()
            sidecar = sidecar_path_for(source)
            original_sidecar = sidecar.read_bytes()
            self._write_pdf(source, pages=2)
            publisher = SSGPublisher(
                SSGConfig((source,), output), show_progress=False
            )

            with patch.object(
                publisher, "_activate", side_effect=RuntimeError("activation exploded")
            ):
                with self.assertRaisesRegex(RuntimeError, "activation exploded"):
                    publisher.build()

            self.assertEqual(sidecar.read_bytes(), original_sidecar)
            self.assertEqual((output / "index.html").read_bytes(), original_output)

    def test_post_commit_cleanup_failure_keeps_new_output_and_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "book.pdf"
            output = root / "dist"
            self._write_pdf(source, pages=1)
            SSGPublisher(
                SSGConfig((source,), output), show_progress=False
            ).build()
            original_sidecar = read_exact_sidecar(source)
            self._write_pdf(source, pages=2)
            publisher = SSGPublisher(
                SSGConfig((source,), output), show_progress=False
            )

            with patch.object(
                publisher,
                "_remove_path",
                side_effect=OSError("previous cleanup exploded"),
            ):
                self.assertEqual(publisher.build(), output.resolve())

            updated_sidecar = read_exact_sidecar(source)
            toc = json.loads(
                next((output / "book").iterdir()).joinpath("toc.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(len(toc), 2)
            self.assertNotEqual(
                updated_sidecar.source_fingerprint,
                original_sidecar.source_fingerprint,
            )
            self.assertEqual(len(list(root.glob(".dist.previous-*"))), 1)

            SSGPublisher(
                SSGConfig((source,), output), show_progress=False
            ).build()

            self.assertEqual(list(root.glob(".dist.previous-*")), [])
            self.assertEqual(read_exact_sidecar(source), updated_sidecar)

    def test_pdf_ssg_escapes_hostile_document_metadata_in_shared_pages(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "hostile.pdf"
            output = root / "dist"
            title = 'Title </title><script data-pdf-attack="title">boom</script>'
            author = 'Author <img src=x onerror="pdfAttack()">'
            tag = 'Tag <svg onload="pdfAttack()">'
            self._write_pdf(
                source,
                pages=1,
                metadata={
                    "/Title": title,
                    "/Author": author,
                    "/Keywords": tag,
                },
            )

            SSGPublisher(
                SSGConfig((source,), output), show_progress=False
            ).build()

            metadata = json.loads(
                (output / "book-metadata.json").read_text(encoding="utf-8")
            )
            book = output / "book" / metadata[0]["hash"]
            for page_name in ("index.html", "chapter_0.html"):
                page = (book / page_name).read_text(encoding="utf-8")
                probe = _HTMLSafetyProbe()
                probe.feed(page)
                self.assertEqual(probe.attack_elements, [], page_name)
                self.assertNotIn("onerror=", page.lower(), page_name)
                self.assertNotIn("onload=", page.lower(), page_name)
                self.assertIn("Title boom", probe.text, page_name)
            library_page = (output / "index.html").read_text(encoding="utf-8")
            library_probe = _HTMLSafetyProbe()
            library_probe.feed(library_page)
            self.assertEqual(library_probe.attack_elements, [])
            self.assertNotIn("onload=", library_page.lower())
            self.assertIn("Tag", library_probe.text)
            index_probe = _HTMLSafetyProbe()
            index_probe.feed((book / "index.html").read_text(encoding="utf-8"))
            self.assertIn("Author", index_probe.text)
            self.assertIn("Tag", index_probe.text)

    def test_sidecar_id_survives_package_metadata_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "book.epub"
            output = root / "dist"
            self._write_minimal_epub(source, identifier="urn:test:before")
            publisher = SSGPublisher(
                SSGConfig((source,), output),
                show_progress=False,
            )

            publisher.build()
            first_sidecar = read_exact_sidecar(source)
            first_id = first_sidecar.book_id
            first_metadata = json.loads(
                (output / "book-metadata.json").read_text(encoding="utf-8")
            )
            self._replace_archive_text(
                source,
                "OEBPS/content.opf",
                b"urn:test:before",
                b"urn:test:after-identifier-changed",
            )
            publisher.build()
            second_metadata = json.loads(
                (output / "book-metadata.json").read_text(encoding="utf-8")
            )

            self.assertRegex(first_id, r"^[A-Za-z0-9_-]{22}$")
            self.assertEqual(first_metadata[0]["hash"], first_id)
            self.assertEqual(second_metadata[0]["hash"], first_id)
            self.assertEqual(read_exact_sidecar(source).book_id, first_id)
            self.assertNotEqual(
                read_exact_sidecar(source).source_fingerprint,
                first_sidecar.source_fingerprint,
            )
            self.assertIsNone(read_embedded_book_id(source))

    def test_default_ssg_creates_sidecar_without_modifying_epub(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "book.epub"
            output = root / "dist"
            self._write_minimal_epub(source, identifier="urn:test:sidecar")
            before = source.read_bytes()

            SSGPublisher(
                SSGConfig((source,), output), show_progress=False
            ).build()

            sidecar = read_exact_sidecar(source)
            metadata = json.loads(
                (output / "book-metadata.json").read_text(encoding="utf-8")
            )
            self.assertIsNotNone(sidecar)
            self.assertEqual(metadata[0]["hash"], sidecar.book_id)
            self.assertEqual(source.read_bytes(), before)
            self.assertIsNone(read_embedded_book_id(source))

    def test_explicit_embedded_ssg_writes_opf_and_no_sidecar(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "book.epub"
            output = root / "dist"
            self._write_minimal_epub(source, identifier="urn:test:embedded")

            SSGPublisher(
                SSGConfig((source,), output, book_id_storage="embedded"),
                show_progress=False,
            ).build()

            self.assertIsNotNone(read_embedded_book_id(source))
            self.assertFalse(sidecar_path_for(source).exists())

    def test_ssg_build_publishes_complete_static_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "book.epub"
            output = root / "dist"
            self._write_minimal_epub(source, identifier="urn:test:ssg")
            config = SSGConfig((source,), output, "/reader/")
            stdout = io.StringIO()

            with contextlib.redirect_stdout(stdout):
                status = run_ssg(config)

            metadata = json.loads(
                (output / "book-metadata.json").read_text(encoding="utf-8")
            )
            book_id = metadata[0]["hash"]

            self.assertEqual(status, 0)
            self.assertTrue((output / "index.html").is_file())
            self.assertTrue((output / "assets" / "manifest.json").is_file())
            self.assertTrue((output / "book" / book_id / "index.html").is_file())
            self.assertTrue((output / "book" / book_id / "toc.json").is_file())
            self.assertFalse((output / "epub-browser.db").exists())
            self.assertFalse((output / "data").exists())
            self.assertIn(str(output.resolve()), stdout.getvalue())
            self.assertTrue(metadata[0]["url"].startswith("/reader/book/"))
            self.assertEqual(metadata[0]["format"], "epub")
            self.assertTrue(metadata[0]["cover"] is None or metadata[0]["cover"].startswith("/reader/"))
            self.assertNotIn(
                str(source.resolve()),
                (output / "index.html").read_text(encoding="utf-8"),
            )
            self.assertIn(
                'window.EpubBrowserMode="ssg"',
                (output / "book" / book_id / "chapter_0.html").read_text(
                    encoding="utf-8"
                ),
            )
            for page in (
                output / "index.html",
                output / "book" / book_id / "index.html",
                output / "book" / book_id / "chapter_0.html",
            ):
                self.assertRegex(
                    page.read_text(encoding="utf-8"),
                    r"window\.EpubBrowserBasePath=(?:[\"'`])/reader/(?:[\"'`])",
                )

    def test_server_only_personal_reading_insight_assets_are_never_emitted_by_ssg(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "book.epub"
            output = root / "dist"
            self._write_minimal_epub(source, identifier="urn:test:personal-reading-insights")

            SSGPublisher(
                SSGConfig((source,), output), show_progress=False
            ).build()

            manifest = json.loads(
                (output / "assets" / "asset-manifest.json").read_text(encoding="utf-8")
            )
            server_only = (
                "book-reviews.js",
                "book-reviews.css",
                "reading-sessions.js",
                "reading-insights.js",
                "reading-insights.css",
            )
            for logical_name in server_only:
                self.assertNotIn(logical_name, manifest)

            output_text = "\n".join(
                path.read_text(encoding="utf-8", errors="ignore")
                for path in output.rglob("*.html")
            )
            for forbidden in (
                "/api/book-reviews",
                "/api/reading-sessions",
                "/api/reading-insights",
                "/reading-insights",
                *server_only,
            ):
                self.assertNotIn(forbidden, output_text)

    def test_non_root_snapshot_has_only_resolvable_base_path_urls(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "book.epub"
            output = root / "dist"
            self._write_minimal_epub(source, identifier="urn:test:base-path")

            SSGPublisher(
                SSGConfig((source,), output, "/project/"),
                show_progress=False,
            ).build()

            root_urls = []
            for page in output.rglob("*.html"):
                html = page.read_text(encoding="utf-8")
                self.assertNotIn("function addBasePath", html)
                for match in re.finditer(
                    r"(?:href|src)=(?:\"([^\"]+)\"|'([^']+)'|([^\s>]+))",
                    html,
                ):
                    url = next(value for value in match.groups() if value is not None)
                    if url.startswith("/") and not url.startswith("//"):
                        root_urls.append(url)

            metadata = json.loads(
                (output / "book-metadata.json").read_text(encoding="utf-8")
            )
            for book in metadata:
                root_urls.extend(
                    value for value in (book.get("url"), book.get("cover")) if value
                )
            for manifest_name in (
                "manifest.json",
                "manifest.en.json",
                "manifest.zh-CN.json",
                "manifest.zh-TW.json",
                "manifest.ko.json",
                "manifest.ja.json",
            ):
                manifest = json.loads(
                    (output / "assets" / manifest_name).read_text(encoding="utf-8")
                )
                root_urls.extend(
                    [manifest["start_url"], manifest["scope"]]
                    + [icon["src"] for icon in manifest["icons"]]
                )

            self.assertTrue(root_urls)
            for url in root_urls:
                self.assertTrue(url.startswith("/project/"), url)
                path = url.split("?", 1)[0].split("#", 1)[0].removeprefix(
                    "/project/"
                )
                target = output / path
                if not path or url.split("?", 1)[0].endswith("/"):
                    target = target / "index.html"
                self.assertTrue(target.is_file(), url)

            worker = (output / "sw.js").read_text(encoding="utf-8")
            self.assertNotIn('"/assets/', worker)
            self.assertNotIn('"/index.html"', worker)
            self.assertIn('"/project/index.html"', worker)

    def test_failed_build_preserves_previous_snapshot_and_removes_staging(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "book.epub"
            output = root / "dist"
            output.mkdir()
            (output / "index.html").write_text("old", encoding="utf-8")
            self._write_minimal_epub(source, identifier="urn:test:failure")

            class FailingProcessor:
                def __init__(self, *args, **kwargs):
                    pass

                def convert(self):
                    raise RuntimeError("conversion exploded")

            publisher = SSGPublisher(
                SSGConfig((source,), output),
                converter_factory=FailingProcessor,
                show_progress=False,
            )

            with self.assertRaisesRegex(SSGBuildError, "conversion exploded"):
                publisher.build()

            self.assertEqual(
                (output / "index.html").read_text(encoding="utf-8"),
                "old",
            )
            self.assertEqual(list(root.glob(".dist.staging-*")), [])
            self.assertEqual(list(root.glob(".dist.previous-*")), [])
            self.assertIsNotNone(read_exact_sidecar(source))

    def test_copied_sidecar_ids_report_every_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "first.epub"
            second = root / "second.epub"
            seed_output = root / "seed-dist"
            output = root / "collision-dist"
            self._write_minimal_epub(first, identifier="urn:test:duplicate")
            SSGPublisher(
                SSGConfig((first,), seed_output),
                show_progress=False,
            ).build()
            shutil.copy2(first, second)
            shutil.copy2(sidecar_path_for(first), sidecar_path_for(second))

            with self.assertRaises(SSGBuildError) as raised:
                SSGPublisher(
                    SSGConfig((first, second), output),
                    show_progress=False,
                ).build()

            message = str(raised.exception)
            self.assertIn(str(first.absolute()), message)
            self.assertIn(str(second.absolute()), message)
            self.assertFalse(output.exists())

    def test_copying_only_epub_allocates_a_distinct_sidecar_id(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "first.epub"
            second = root / "second.epub"
            seed_output = root / "seed-dist"
            output = root / "copy-dist"
            self._write_minimal_epub(first, identifier="urn:test:copy")
            SSGPublisher(
                SSGConfig((first,), seed_output), show_progress=False
            ).build()
            shutil.copy2(first, second)

            SSGPublisher(
                SSGConfig((first, second), output), show_progress=False
            ).build()

            metadata = json.loads(
                (output / "book-metadata.json").read_text(encoding="utf-8")
            )
            self.assertEqual(len({book["hash"] for book in metadata}), 2)
            self.assertIsNone(read_embedded_book_id(first))
            self.assertIsNone(read_embedded_book_id(second))

    def test_output_cannot_own_an_input_epub(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            source = output / "book.epub"
            self._write_minimal_epub(source, identifier="urn:test:unsafe-output")

            with self.assertRaisesRegex(SSGBuildError, "Output directory"):
                before = source.read_bytes()
                SSGPublisher(
                    SSGConfig((source,), output),
                    show_progress=False,
                ).build()

            self.assertTrue(source.exists())
            self.assertEqual(source.read_bytes(), before)

    def test_epub_resource_directory_named_data_is_not_server_state(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "book.epub"
            output = root / "dist"
            self._write_minimal_epub(
                source,
                identifier="urn:test:data-resource",
                resource_path="data/p.png",
            )

            SSGPublisher(
                SSGConfig((source,), output),
                show_progress=False,
            ).build()

            metadata = json.loads(
                (output / "book-metadata.json").read_text(encoding="utf-8")
            )
            book_id = metadata[0]["hash"]
            self.assertTrue(
                (
                    output
                    / "book"
                    / book_id
                    / "resources"
                    / "OEBPS"
                    / "data"
                    / "p.png"
                ).is_file()
            )

    def test_kindle_minimal_reader_pages_are_generated_for_epub(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "book.epub"
            output = root / "dist"
            self._write_minimal_epub(source, identifier="urn:test:kindle")
            SSGPublisher(
                SSGConfig((source,), output, kindle=True),
                show_progress=False,
            ).build()

            metadata = json.loads(
                (output / "book-metadata.json").read_text(encoding="utf-8")
            )
            book = output / "book" / metadata[0]["hash"]

            index = (book / "kindle.html").read_text(encoding="utf-8")
            self.assertIn("SSG Book", index)
            self.assertIn('href="kindle_chapter_0.html"', index)
            self.assertIn('id="kResume"', index)
            self.assertIn("Continue reading", index)

            chapter = (book / "kindle_chapter_0.html").read_text(encoding="utf-8")
            self.assertIn("<h1>One</h1>", chapter)
            self.assertIn("Text", chapter)
            self.assertIn('href="kindle.html"', chapter)
            # First (and only) chapter has neither a prev nor a next link.
            self.assertNotIn('class="prev"', chapter)
            self.assertNotIn('class="next"', chapter)
            # Self-contained: no /assets/ references in the reader page.
            self.assertNotIn("/assets/", chapter)
            # ES5 only and no localStorage: these tokens must never appear.
            for banned in (
                "=>", "const ", "let ", "Promise", "classList", "localStorage",
            ):
                self.assertNotIn(banned, chapter)

            # Library level: the minimal library page and the legacy-Kindle
            # redirect from the full library shell.
            minimal_library = (output / "kindle-library.html").read_text(encoding="utf-8")
            self.assertIn("Library", minimal_library)
            self.assertIn(
                f'href="/book/{book.name}/kindle.html"', minimal_library
            )
            self.assertNotIn("/assets/", minimal_library)
            library_index = (output / "index.html").read_text(encoding="utf-8")
            self.assertIn("location.replace('kindle-library.html')", library_index)
            self.assertIn("kindle-library.html", library_index)

            # Book home and chapter pages carry the legacy-Kindle redirect to
            # their minimal siblings, and the minimal pages escape the loop.
            book_index = (book / "index.html").read_text(encoding="utf-8")
            self.assertIn("location.replace('kindle.html')", book_index)
            full_chapter = (book / "chapter_0.html").read_text(encoding="utf-8")
            self.assertIn(
                "location.replace('kindle_chapter_0.html')", full_chapter
            )
            self.assertIn('href="index.html?full=1"', index)
            self.assertIn("Open full reader", index)

    def test_kindle_minimal_reader_pages_are_not_generated_for_pdf(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "book.pdf"
            output = root / "dist"
            self._write_pdf(source, pages=2)
            SSGPublisher(
                SSGConfig((source,), output),
                show_progress=False,
            ).build()

            metadata = json.loads(
                (output / "book-metadata.json").read_text(encoding="utf-8")
            )
            book = output / "book" / metadata[0]["hash"]
            self.assertFalse((book / "kindle.html").exists())
            self.assertEqual(list(book.glob("kindle_chapter_*.html")), [])
            # PDF pages must not redirect anywhere: there is no minimal page.
            book_index = (book / "index.html").read_text(encoding="utf-8")
            self.assertNotIn("location.replace('kindle.html')", book_index)
            chapter = (book / "chapter_0.html").read_text(encoding="utf-8")
            self.assertNotIn("kindle_chapter", chapter)

    def test_kindle_pages_are_opt_in(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "book.epub"
            output = root / "dist"
            self._write_minimal_epub(source, identifier="urn:test:no-kindle")
            SSGPublisher(
                SSGConfig((source,), output),
                show_progress=False,
            ).build()

            metadata = json.loads(
                (output / "book-metadata.json").read_text(encoding="utf-8")
            )
            book = output / "book" / metadata[0]["hash"]

            # Without --kindle no minimal pages exist and nothing redirects.
            self.assertFalse((output / "kindle-library.html").exists())
            self.assertFalse((book / "kindle.html").exists())
            self.assertEqual(list(book.glob("kindle_chapter_*.html")), [])
            library_index = (output / "index.html").read_text(encoding="utf-8")
            self.assertNotIn("kindle-library.html", library_index)
            book_index = (book / "index.html").read_text(encoding="utf-8")
            self.assertNotIn("location.replace('kindle.html')", book_index)
            chapter = (book / "chapter_0.html").read_text(encoding="utf-8")
            self.assertNotIn("kindle_chapter", chapter)

    def test_operational_filesystem_failure_returns_stable_status(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "book.epub"
            blocker = root / "not-a-directory"
            blocker.write_text("file", encoding="utf-8")
            self._write_minimal_epub(source, identifier="urn:test:io-error")
            stderr = io.StringIO()

            with contextlib.redirect_stderr(stderr):
                status = run_ssg(SSGConfig((source,), blocker / "dist"))

            self.assertEqual(status, 4)
            self.assertIn("not-a-directory", stderr.getvalue())

    @staticmethod
    def _write_minimal_epub(path, identifier, resource_path=None):
        container = """<?xml version="1.0"?>
<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0">
  <rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles>
</container>
"""
        resource_manifest = (
            f'<item id="image" href="{resource_path}" media-type="image/png"/>'
            if resource_path
            else ""
        )
        package = f"""<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="book-id">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="book-id">{identifier}</dc:identifier>
    <dc:title>SSG Book</dc:title><dc:creator>Author</dc:creator><dc:language>en</dc:language>
  </metadata>
  <manifest><item id="chapter" href="chapter.xhtml" media-type="application/xhtml+xml"/>{resource_manifest}</manifest>
  <spine><itemref idref="chapter"/></spine>
</package>
"""
        resource_html = f'<img src="{resource_path}" alt="">' if resource_path else ""
        chapter = f"""<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml"><head><title>One</title></head>
<body><h1>One</h1><p>Text</p>{resource_html}</body></html>
"""
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("mimetype", "application/epub+zip")
            archive.writestr("META-INF/container.xml", container)
            archive.writestr("OEBPS/content.opf", package)
            archive.writestr("OEBPS/chapter.xhtml", chapter)
            if resource_path:
                archive.writestr("OEBPS/" + resource_path, b"png")

    @staticmethod
    def _replace_archive_text(path, member_name, before, after):
        temporary = path.with_suffix(".rewritten.epub")
        with zipfile.ZipFile(path, "r") as source:
            with zipfile.ZipFile(temporary, "w") as destination:
                destination.comment = source.comment
                for info in source.infolist():
                    data = source.read(info)
                    if info.filename == member_name:
                        data = data.replace(before, after)
                    destination.writestr(info, data)
        temporary.replace(path)

    @staticmethod
    def _write_pdf(path, pages, metadata=None):
        writer = PdfWriter()
        for page_number in range(pages):
            writer.add_blank_page(width=200 + page_number, height=400 + page_number)
        writer.add_metadata(
            metadata or {"/Title": "SSG PDF", "/Author": "PDF Author"}
        )
        with Path(path).open("wb") as stream:
            writer.write(stream)


class _HTMLSafetyProbe(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.attack_elements = []
        self.text_parts = []

    @property
    def text(self):
        return "".join(self.text_parts)

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if (
            attributes.get("data-pdf-attack") is not None
            or "onerror" in attributes
            or "onload" in attributes
        ):
            self.attack_elements.append((tag, attributes))

    def handle_data(self, data):
        self.text_parts.append(data)


if __name__ == "__main__":
    unittest.main()
