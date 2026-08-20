import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

try:
    from epub_browser.epub_identity import (
        EPUBIdentityWriteRefused,
        ensure_embedded_book_id,
        read_embedded_book_id,
    )
except ImportError:
    EPUBIdentityWriteRefused = None
    ensure_embedded_book_id = None
    read_embedded_book_id = None


class EPUBIdentityTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "book.epub"

    def test_embedding_changes_only_opf_and_preserves_epub_container_contract(self):
        self._write_epub(self.source)
        before = self._archive_snapshot(self.source)

        self._require_api()
        book_id = ensure_embedded_book_id(
            self.source,
            preferred_book_id="legacy_book_id",
        )

        self.assertEqual(book_id, "legacy_book_id")
        self.assertEqual(read_embedded_book_id(self.source), "legacy_book_id")
        after = self._archive_snapshot(self.source)
        self.assertEqual(after["order"], before["order"])
        self.assertEqual(after["comment"], before["comment"])
        self.assertEqual(after["metadata"], before["metadata"])
        self.assertEqual(
            {name: data for name, data in after["contents"].items() if name != "OEBPS/content.opf"},
            {name: data for name, data in before["contents"].items() if name != "OEBPS/content.opf"},
        )
        self.assertNotEqual(
            after["contents"]["OEBPS/content.opf"],
            before["contents"]["OEBPS/content.opf"],
        )
        with zipfile.ZipFile(self.source) as archive:
            first = archive.infolist()[0]
            self.assertEqual(first.filename, "mimetype")
            self.assertEqual(first.compress_type, zipfile.ZIP_STORED)
            self.assertEqual(first.extra, b"")
            self.assertIsNone(archive.testzip())

    def test_embedding_is_idempotent_and_does_not_rewrite_existing_identity(self):
        self._write_epub(self.source)
        self._require_api()
        first = ensure_embedded_book_id(
            self.source,
            preferred_book_id="stable_book_id",
        )
        once = self.source.read_bytes()

        second = ensure_embedded_book_id(self.source)

        self.assertEqual(first, "stable_book_id")
        self.assertEqual(second, "stable_book_id")
        self.assertEqual(self.source.read_bytes(), once)

    def test_embedding_repairs_mimetype_packaging_without_changing_resources(self):
        self._write_epub(
            self.source,
            mimetype_first=False,
            mimetype_compressed=True,
        )
        before = self._archive_snapshot(self.source)

        self._require_api()
        book_id = ensure_embedded_book_id(
            self.source,
            preferred_book_id="stable_book_id",
        )

        after = self._archive_snapshot(self.source)
        self.assertEqual(book_id, "stable_book_id")
        self.assertEqual(before["order"][0], "META-INF/container.xml")
        self.assertEqual(
            after["order"],
            ["mimetype", *[name for name in before["order"] if name != "mimetype"]],
        )
        self.assertEqual(after["comment"], before["comment"])
        self.assertEqual(after["metadata"]["mimetype"][0], zipfile.ZIP_STORED)
        self.assertEqual(after["metadata"]["mimetype"][3], b"")
        self.assertEqual(
            {
                name: metadata
                for name, metadata in after["metadata"].items()
                if name != "mimetype"
            },
            {
                name: metadata
                for name, metadata in before["metadata"].items()
                if name != "mimetype"
            },
        )
        self.assertEqual(
            {
                name: data
                for name, data in after["contents"].items()
                if name != "OEBPS/content.opf"
            },
            {
                name: data
                for name, data in before["contents"].items()
                if name != "OEBPS/content.opf"
            },
        )

    def test_new_identity_is_url_safe_uuid_value(self):
        self._write_epub(self.source)
        self._require_api()

        book_id = ensure_embedded_book_id(self.source)

        self.assertRegex(book_id, r"^[A-Za-z0-9_-]{22}$")
        self.assertEqual(read_embedded_book_id(self.source), book_id)

    def test_signed_epub_is_not_modified(self):
        self._write_epub(self.source, signed=True)
        before = self.source.read_bytes()
        self._require_api()

        with self.assertRaisesRegex(EPUBIdentityWriteRefused, "signed"):
            ensure_embedded_book_id(self.source, preferred_book_id="safe_id")

        self.assertEqual(self.source.read_bytes(), before)

    def test_failed_atomic_replace_leaves_original_epub_unchanged(self):
        self._write_epub(self.source)
        before = self.source.read_bytes()
        self._require_api()

        with mock.patch(
            "epub_browser.epub_identity.os.replace",
            side_effect=OSError("replace failed"),
        ):
            with self.assertRaisesRegex(OSError, "replace failed"):
                ensure_embedded_book_id(
                    self.source,
                    preferred_book_id="safe_id",
                )

        self.assertEqual(self.source.read_bytes(), before)
        self.assertEqual(list(self.root.glob(".book.epub.*.tmp")), [])

    def test_reads_epub3_property_metadata_without_rewriting(self):
        self._write_epub(
            self.source,
            package_version="3.0",
            embedded_meta=(
                '<meta property="epub-browser:book-id">property_id</meta>'
            ),
        )
        before = self.source.read_bytes()
        self._require_api()

        self.assertEqual(read_embedded_book_id(self.source), "property_id")
        self.assertEqual(ensure_embedded_book_id(self.source), "property_id")
        self.assertEqual(self.source.read_bytes(), before)

    def test_identity_appearing_during_write_is_not_overwritten(self):
        self._write_epub(
            self.source,
            embedded_meta=(
                '<meta name="epub-browser:book-id" content="concurrent_id"/>'
            ),
        )
        before = self.source.read_bytes()
        self._require_api()
        real_read = read_embedded_book_id
        calls = 0

        def miss_the_first_read(path):
            nonlocal calls
            calls += 1
            if calls == 1:
                return None
            return real_read(path)

        with mock.patch(
            "epub_browser.epub_identity.read_embedded_book_id",
            side_effect=miss_the_first_read,
        ):
            with self.assertRaisesRegex(ValueError, "conflicts"):
                ensure_embedded_book_id(
                    self.source,
                    preferred_book_id="preferred_id",
                )

        self.assertEqual(self.source.read_bytes(), before)

    def _require_api(self):
        if ensure_embedded_book_id is None:
            self.fail("embedded EPUB identity API is not implemented")

    @staticmethod
    def _archive_snapshot(path):
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            return {
                "order": [info.filename for info in infos],
                "comment": archive.comment,
                "metadata": {
                    info.filename: (
                        info.compress_type,
                        info.date_time,
                        info.comment,
                        info.extra,
                        info.external_attr,
                        info.internal_attr,
                        info.create_system,
                        info.create_version,
                        info.extract_version,
                        info.flag_bits,
                        info.volume,
                    )
                    for info in infos
                },
                "contents": {
                    info.filename: archive.read(info)
                    for info in infos
                },
            }

    @staticmethod
    def _write_epub(
        path,
        *,
        signed=False,
        package_version="2.0",
        embedded_meta="",
        mimetype_first=True,
        mimetype_compressed=False,
    ):
        container = """<?xml version="1.0"?>
<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0">
  <rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles>
</container>
"""
        package = f"""<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="{package_version}" unique-identifier="book-id">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="book-id">urn:test:identity</dc:identifier>
    <dc:title>Identity Book</dc:title><dc:language>en</dc:language>
    {embedded_meta}
  </metadata>
  <manifest><item id="chapter" href="chapter.xhtml" media-type="application/xhtml+xml"/></manifest>
  <spine><itemref idref="chapter"/></spine>
</package>
"""
        chapter = b"<html xmlns='http://www.w3.org/1999/xhtml'><body>unchanged</body></html>"
        with zipfile.ZipFile(path, "w") as archive:
            mimetype = zipfile.ZipInfo("mimetype", (2020, 1, 2, 3, 4, 6))
            mimetype.compress_type = (
                zipfile.ZIP_DEFLATED
                if mimetype_compressed
                else zipfile.ZIP_STORED
            )
            if mimetype_compressed:
                mimetype.extra = b"\x55\x54\x05\x00\x01\x00\x00\x00\x00"
            if mimetype_first:
                archive.writestr(mimetype, "application/epub+zip")
            archive.writestr(
                "META-INF/container.xml",
                container,
                compress_type=zipfile.ZIP_DEFLATED,
            )
            if not mimetype_first:
                archive.writestr(mimetype, "application/epub+zip")
            opf = zipfile.ZipInfo("OEBPS/content.opf", (2021, 2, 3, 4, 5, 6))
            opf.compress_type = zipfile.ZIP_DEFLATED
            opf.external_attr = 0o100640 << 16
            archive.writestr(opf, package)
            archive.writestr(
                "OEBPS/chapter.xhtml",
                chapter,
                compress_type=zipfile.ZIP_DEFLATED,
            )
            if signed:
                archive.writestr(
                    "META-INF/signatures.xml",
                    b"<signatures/>",
                    compress_type=zipfile.ZIP_DEFLATED,
                )
            archive.comment = b"preserve-this-comment"


if __name__ == "__main__":
    unittest.main()
