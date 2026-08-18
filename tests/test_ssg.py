import contextlib
import io
import json
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

    @staticmethod
    def _write_minimal_epub(path, identifier):
        container = """<?xml version="1.0"?>
<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0">
  <rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles>
</container>
"""
        package = f"""<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="book-id">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="book-id">{identifier}</dc:identifier>
    <dc:title>SSG Book</dc:title><dc:creator>Author</dc:creator><dc:language>en</dc:language>
  </metadata>
  <manifest><item id="chapter" href="chapter.xhtml" media-type="application/xhtml+xml"/></manifest>
  <spine><itemref idref="chapter"/></spine>
</package>
"""
        chapter = """<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml"><head><title>One</title></head>
<body><h1>One</h1><p>Text</p></body></html>
"""
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("mimetype", "application/epub+zip")
            archive.writestr("META-INF/container.xml", container)
            archive.writestr("OEBPS/content.opf", package)
            archive.writestr("OEBPS/chapter.xhtml", chapter)


if __name__ == "__main__":
    unittest.main()
