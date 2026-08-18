import contextlib
import io
import json
import re
import tempfile
import unittest
import zipfile
from pathlib import Path

from epub_browser.cli import SSGConfig
from epub_browser.ssg import SSGBuildError, SSGPublisher, run_ssg


class SSGPublicationTests(unittest.TestCase):
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

    def test_duplicate_deterministic_ids_report_every_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "first.epub"
            second = root / "second.epub"
            output = root / "dist"
            self._write_minimal_epub(first, identifier="urn:test:duplicate")
            self._write_minimal_epub(second, identifier="urn:test:duplicate")

            with self.assertRaises(SSGBuildError) as raised:
                SSGPublisher(
                    SSGConfig((first, second), output),
                    show_progress=False,
                ).build()

            message = str(raised.exception)
            self.assertIn(str(first.resolve()), message)
            self.assertIn(str(second.resolve()), message)
            self.assertFalse(output.exists())

    def test_output_cannot_own_an_input_epub(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            source = output / "book.epub"
            self._write_minimal_epub(source, identifier="urn:test:unsafe-output")

            with self.assertRaisesRegex(SSGBuildError, "Output directory"):
                SSGPublisher(
                    SSGConfig((source,), output),
                    show_progress=False,
                ).build()

            self.assertTrue(source.exists())

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


if __name__ == "__main__":
    unittest.main()
