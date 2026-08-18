import unittest

from epub_browser.urls import SiteURLs, normalize_base_path, rewrite_root_urls


class URLTests(unittest.TestCase):
    def test_normalizes_project_path(self):
        self.assertEqual(normalize_base_path("reader"), "/reader/")
        self.assertEqual(normalize_base_path("/reader"), "/reader/")
        self.assertEqual(normalize_base_path("/"), "/")

    def test_rejects_external_or_traversing_base_path(self):
        for value in (
            "https://example.com/reader/",
            "//example.com/reader/",
            "/a/../b/",
            "/reader/?x=1",
            "/reader/#top",
            "\\reader\\",
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize_base_path(value)

    def test_builds_public_and_filesystem_paths(self):
        urls = SiteURLs("/library/")

        self.assertEqual(urls.public("/assets/app.css"), "/library/assets/app.css")
        self.assertEqual(
            urls.filesystem_relative("/library/assets/app.css").as_posix(),
            "assets/app.css",
        )

    def test_rejects_public_url_outside_base_path(self):
        with self.assertRaises(ValueError):
            SiteURLs("/library/").filesystem_relative("/assets/app.css")

    def test_rewrites_internal_root_attributes_under_base_path(self):
        html = (
            '<link href="/assets/app.css">'
            '<a href="/book/demo/">Read</a>'
            '<meta content="/assets/icon.png">'
            '<a href="https://example.com/">External</a>'
        )

        result = rewrite_root_urls(html, SiteURLs("/library/"))

        self.assertIn('href="/library/assets/app.css"', result)
        self.assertIn('href="/library/book/demo/"', result)
        self.assertIn('content="/library/assets/icon.png"', result)
        self.assertIn('href="https://example.com/"', result)

    def test_rewriting_is_idempotent(self):
        html = '<script src="/library/assets/app.js"></script>'

        once = rewrite_root_urls(html, SiteURLs("/library/"))
        twice = rewrite_root_urls(once, SiteURLs("/library/"))

        self.assertEqual(twice, html)


if __name__ == "__main__":
    unittest.main()
