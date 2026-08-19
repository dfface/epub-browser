import contextlib
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from epub_browser.asset_publisher import AssetPublisher
from epub_browser.library import EPUBLibrary
from epub_browser.site import LibraryBook, publish_library_shell
from epub_browser.urls import SiteURLs


class SitePublicationTests(unittest.TestCase):
    def test_publish_library_shell_writes_sorted_metadata_and_base_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            urls = SiteURLs("/reader/")
            assets = AssetPublisher(
                Path("epub_browser/assets"),
                root,
                urls=urls,
            ).publish()
            books = [
                LibraryBook(
                    "b",
                    "Beta",
                    ("B",),
                    (),
                    "/book/b/resources/cover.jpg",
                ),
                LibraryBook("a", "Alpha", ("A",), ("tag",), None),
            ]

            publish_library_shell(root, books, assets, urls)

            payload = json.loads(
                (root / "book-metadata.json").read_text(encoding="utf-8")
            )
            html = (root / "index.html").read_text(encoding="utf-8")

        self.assertEqual([item["hash"] for item in payload], ["a", "b"])
        self.assertEqual(payload[1]["cover"], "/reader/book/b/resources/cover.jpg")
        self.assertRegex(html, r"/reader/assets/immutable/library\.[0-9a-f]{12}\.js")
        self.assertNotIn("function addBasePath", html)
        self.assertIn("window.initScriptLibrary()", html)
        self.assertIn('id=libraryBookCount', html)
        self.assertIn('id=libraryTagCount', html)
        self.assertRegex(
            html,
            r"window\.EpubBrowserBasePath=(?:[\"'`])/reader/(?:[\"'`])",
        )
        self.assertRegex(html, r"window\.EpubBrowserMode=(?:[\"'`])ssg(?:[\"'`])")

    def test_server_library_shell_bootstraps_server_data_clients(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            assets = AssetPublisher(Path("epub_browser/assets"), root).publish()

            publish_library_shell(
                root,
                (),
                assets,
                SiteURLs(),
                deployment_mode="server",
            )

            html = (root / "index.html").read_text(encoding="utf-8")

        self.assertRegex(html, r"window\.EpubBrowserMode=(?:[\"'`])server(?:[\"'`])")
        self.assertIn('id=libraryBookCount', html)
        self.assertIn('id=libraryTagCount', html)
        self.assertIn('id=libraryProgress', html)
        self.assertIn('library-progress', html)
        self.assertIn('data-progress-close', html)
        self.assertRegex(html, r'data-progress-close[^>]*disabled')
        self.assertRegex(html, r'data-progress-close[^>]*hidden')
        self.assertIn('window.EpubLibraryProgress.start(window)', html)
        self.assertIn(
            'window.EpubBrowserCacheBoundary.start(startLibraryClients)',
            html,
        )
        self.assertIn('id=accountMenu', html)
        self.assertIn('id=accountPanel', html)
        self.assertNotIn('id=loginCard', html)
        self.assertNotIn('id=exportShelfBtn', html)
        self.assertNotIn('id=importShelfBtn', html)
        self.assertNotIn('id=syncShelfBtn', html)
        self.assertRegex(html, r'/assets/immutable/auth\.[0-9a-f]{12}\.js')

    def test_static_library_shell_omits_server_progress_panel_assets(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            assets = AssetPublisher(Path("epub_browser/assets"), root).publish()
            publish_library_shell(root, (), assets, SiteURLs())
            html = (root / "index.html").read_text(encoding="utf-8")

        self.assertNotIn('id=libraryProgress', html)
        self.assertNotIn('library-progress', html)
        self.assertNotIn('id=loginCard', html)
        self.assertIn('id=exportShelfBtn', html)
        self.assertIn('id=importShelfBtn', html)
        self.assertNotIn('id=syncShelfBtn', html)

    def test_publish_library_shell_atomically_replaces_both_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            assets = AssetPublisher(Path("epub_browser/assets"), root).publish()
            (root / "index.html").write_text("old", encoding="utf-8")
            (root / "book-metadata.json").write_text("old", encoding="utf-8")

            publish_library_shell(root, (), assets, SiteURLs())

            self.assertNotEqual((root / "index.html").read_text(encoding="utf-8"), "old")
            self.assertEqual(
                json.loads((root / "book-metadata.json").read_text(encoding="utf-8")),
                [],
            )
            self.assertEqual(list(root.glob("*.tmp")), [])

    def test_compatibility_library_is_quiet_by_default(self):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with tempfile.TemporaryDirectory() as directory:
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                EPUBLibrary(directory)

        self.assertEqual(stdout.getvalue(), "")
        self.assertEqual(stderr.getvalue(), "")

    def test_failed_compatibility_conversion_is_quiet_without_log(self):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "invalid.epub"
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr("mimetype", "application/epub+zip")
            library = EPUBLibrary(root / "output")

            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                converted, _ = library.add_book(str(source))

        self.assertFalse(converted)
        self.assertEqual(stdout.getvalue(), "")
        self.assertEqual(stderr.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
