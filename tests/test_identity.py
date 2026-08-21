import tempfile
import unittest
from pathlib import Path

from epub_browser.identity import (
    new_server_book_id,
    source_sha256,
)


class IdentityTests(unittest.TestCase):
    def test_server_id_is_unique_22_character_url_safe_uuid(self):
        first = new_server_book_id()
        second = new_server_book_id()

        self.assertRegex(first, r"^[A-Za-z0-9_-]{22}$")
        self.assertNotEqual(first, second)

    def test_source_sha256_hashes_file_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory, "book.epub")
            source.write_bytes(b"epub bytes")

            self.assertEqual(
                source_sha256(source),
                "227dae38658f29c3a8494e65302e70b406162c2f581845339dfa19cbfad839d4",
            )


if __name__ == "__main__":
    unittest.main()
