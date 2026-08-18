import tempfile
import unittest
from pathlib import Path

from epub_browser.identity import (
    derive_ssg_book_id,
    new_server_book_id,
    source_sha256,
)
from epub_browser.models import BookMetadata


class IdentityTests(unittest.TestCase):
    def test_server_id_is_unique_22_character_url_safe_uuid(self):
        first = new_server_book_id()
        second = new_server_book_id()

        self.assertRegex(first, r"^[A-Za-z0-9_-]{22}$")
        self.assertNotEqual(first, second)

    def test_ssg_id_is_deterministic_and_path_independent(self):
        metadata = BookMetadata(
            title=" Example ",
            authors=(" A ",),
            tags=(),
            cover=None,
            language="en",
            epub_identifier=" urn:isbn:1 ",
        )
        spine = ((" Chapter ", "Text/one.xhtml", 0),)

        first = derive_ssg_book_id(metadata, spine)
        second = derive_ssg_book_id(metadata, spine)

        self.assertEqual(first, second)
        self.assertRegex(first, r"^[A-Za-z0-9_-]{22}$")

    def test_ssg_id_changes_when_package_identity_or_spine_changes(self):
        first_metadata = BookMetadata(
            title="Example",
            authors=("A",),
            tags=(),
            cover=None,
            language="en",
            epub_identifier="urn:isbn:1",
        )
        second_metadata = BookMetadata(
            title="Example",
            authors=("A",),
            tags=(),
            cover=None,
            language="en",
            epub_identifier="urn:isbn:2",
        )

        first = derive_ssg_book_id(first_metadata, (("One", "one.xhtml", 0),))
        changed_identifier = derive_ssg_book_id(
            second_metadata, (("One", "one.xhtml", 0),)
        )
        changed_spine = derive_ssg_book_id(
            first_metadata, (("Two", "two.xhtml", 0),)
        )

        self.assertNotEqual(first, changed_identifier)
        self.assertNotEqual(first, changed_spine)

    def test_ssg_id_without_package_identifier_uses_title_and_authors(self):
        first = BookMetadata(
            title="Example",
            authors=("A",),
            tags=("ignored",),
            cover="ignored.png",
            language="en",
            epub_identifier=None,
        )
        second = BookMetadata(
            title="Different",
            authors=("B",),
            tags=("also ignored",),
            cover=None,
            language="fr",
            epub_identifier=None,
        )
        spine = (("One", "one.xhtml", 0),)

        self.assertNotEqual(
            derive_ssg_book_id(first, spine),
            derive_ssg_book_id(second, spine),
        )

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
