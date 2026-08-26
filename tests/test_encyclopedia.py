import json
import unittest
from unittest import mock

from epub_browser.encyclopedia import WikimediaEncyclopedia


class _Response:
    def __init__(self, payload):
        self.payload = payload
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def read(self, limit): return json.dumps(self.payload).encode("utf-8")


class EncyclopediaTests(unittest.TestCase):
    @mock.patch("epub_browser.encyclopedia.urlopen")
    def test_uses_a_fixed_language_host_and_returns_safe_summary(self, urlopen):
        urlopen.return_value = _Response({
            "title": "Earth", "description": "planet", "extract": "Our world",
            "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/Earth"}},
        })
        result = WikimediaEncyclopedia().lookup("en-US", "Earth")
        self.assertTrue(result.found)
        self.assertEqual(result.title, "Earth")
        self.assertIn("en.wikipedia.org", urlopen.call_args.args[0].full_url)


if __name__ == "__main__":
    unittest.main()
