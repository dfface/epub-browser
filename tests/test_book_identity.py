import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from epub_browser.book_identity import (
    BookIdentityConflict,
    BookIdentityError,
    ExternalBookIdentity,
    KnownSourceFingerprint,
    inspect_book_identity,
    resolve_book_identity,
)
from epub_browser.epub_identity import read_embedded_book_id
from epub_browser.identity import source_sha256
from epub_browser.sidecar_identity import (
    read_exact_sidecar,
    read_sidecar_file,
    sidecar_path_for,
    write_sidecar,
)


class BookIdentityTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "book.epub"

    def test_default_sidecar_generation_preserves_epub_bytes(self):
        self._write_epub(self.source)
        before = self.source.read_bytes()
        resolved = resolve_book_identity(
            inspect_book_identity(self.source), "sidecar"
        )
        self.assertRegex(resolved.book_id, r"^[A-Za-z0-9_-]{22}$")
        self.assertEqual(self.source.read_bytes(), before)
        self.assertEqual(read_exact_sidecar(self.source).book_id, resolved.book_id)
        self.assertIsNone(read_embedded_book_id(self.source))

    def test_sidecar_mode_migrates_embedded_id_without_rewrite(self):
        self._write_epub(self.source, embedded_book_id="embedded_id")
        before = self.source.read_bytes()
        resolved = resolve_book_identity(
            inspect_book_identity(self.source), "sidecar"
        )
        self.assertEqual(resolved.book_id, "embedded_id")
        self.assertEqual(self.source.read_bytes(), before)
        self.assertEqual(read_exact_sidecar(self.source).book_id, "embedded_id")

    def test_embedded_mode_uses_sidecar_id_without_deleting_sidecar(self):
        self._write_epub(self.source)
        write_sidecar(self.source, "sidecar_id", source_sha256(self.source))
        sidecar_before = sidecar_path_for(self.source).read_bytes()
        resolved = resolve_book_identity(
            inspect_book_identity(self.source), "embedded"
        )
        self.assertEqual(resolved.book_id, "sidecar_id")
        self.assertEqual(read_embedded_book_id(self.source), "sidecar_id")
        self.assertEqual(sidecar_path_for(self.source).read_bytes(), sidecar_before)

    def test_conflicting_carriers_fail_without_mutation(self):
        self._write_epub(self.source, embedded_book_id="embedded_id")
        write_sidecar(self.source, "sidecar_id", source_sha256(self.source))
        epub_before = self.source.read_bytes()
        sidecar_before = sidecar_path_for(self.source).read_bytes()
        with self.assertRaisesRegex(BookIdentityConflict, "embedded_id"):
            resolve_book_identity(inspect_book_identity(self.source), "sidecar")
        self.assertEqual(self.source.read_bytes(), epub_before)
        self.assertEqual(sidecar_path_for(self.source).read_bytes(), sidecar_before)

    def test_content_edit_retains_exact_sidecar_id_and_refreshes_digest(self):
        self._write_epub(self.source)
        first = resolve_book_identity(
            inspect_book_identity(self.source), "sidecar"
        )
        old_digest = read_exact_sidecar(self.source).source_fingerprint
        self._replace_archive_text(
            self.source, "OEBPS/chapter.xhtml", b"unchanged", b"changed"
        )
        second = resolve_book_identity(
            inspect_book_identity(self.source), "sidecar"
        )
        self.assertEqual(second.book_id, first.book_id)
        self.assertNotEqual(
            read_exact_sidecar(self.source).source_fingerprint, old_digest
        )

    def test_one_matching_orphan_is_adopted_after_rename(self):
        self._write_epub(self.source)
        first = resolve_book_identity(
            inspect_book_identity(self.source), "sidecar"
        )
        orphan = sidecar_path_for(self.source)
        moved = self.root / "moved.epub"
        self.source.rename(moved)
        second = resolve_book_identity(
            inspect_book_identity(moved, orphan_sidecars=(orphan,)),
            "sidecar",
        )
        self.assertEqual(second.book_id, first.book_id)
        self.assertFalse(orphan.exists())
        self.assertEqual(read_exact_sidecar(moved).book_id, first.book_id)

    def test_two_matching_orphans_are_ambiguous(self):
        self._write_epub(self.source)
        first = resolve_book_identity(
            inspect_book_identity(self.source), "sidecar"
        )
        first_orphan = sidecar_path_for(self.source)
        second_orphan = self.root / "copy.epub.epub-browser.json"
        shutil.copy2(first_orphan, second_orphan)
        moved = self.root / "moved.epub"
        self.source.rename(moved)
        with self.assertRaisesRegex(BookIdentityError, "Multiple sidecars"):
            resolve_book_identity(
                inspect_book_identity(
                    moved,
                    orphan_sidecars=(first_orphan, second_orphan),
                ),
                "sidecar",
            )
        self.assertEqual(first.book_id, read_sidecar_file(first_orphan).book_id)

    def test_current_database_id_recreates_missing_sidecar(self):
        self._write_epub(self.source)
        resolved = resolve_book_identity(
            inspect_book_identity(self.source),
            "sidecar",
            external_candidates=(
                ExternalBookIdentity("Server database", "database_id", True),
            ),
        )
        self.assertEqual(resolved.book_id, "database_id")
        self.assertEqual(read_exact_sidecar(self.source).book_id, "database_id")

    def test_known_fingerprint_requires_matching_size_and_mtime(self):
        self._write_epub(self.source)
        source_stat = self.source.stat()
        known = KnownSourceFingerprint(
            "a" * 64, source_stat.st_size, source_stat.st_mtime_ns
        )
        with mock.patch("epub_browser.book_identity.source_sha256") as digest:
            inspection = inspect_book_identity(
                self.source, known_fingerprint=known
            )
        digest.assert_not_called()
        self.assertEqual(inspection.source_fingerprint, "a" * 64)

    def test_sidecar_mode_places_identity_beside_source_symlink(self):
        self._write_epub(self.source)
        target_before = self.source.read_bytes()
        linked = self.root / "linked.epub"
        linked.symlink_to(self.source)
        resolved = resolve_book_identity(
            inspect_book_identity(linked), "sidecar"
        )
        self.assertEqual(read_exact_sidecar(linked).book_id, resolved.book_id)
        self.assertTrue((self.root / "linked.epub.epub-browser.json").is_file())
        self.assertEqual(self.source.read_bytes(), target_before)

    def test_current_external_id_conflicts_with_carrier(self):
        self._write_epub(self.source, embedded_book_id="embedded_id")
        inspection = inspect_book_identity(self.source)
        with self.assertRaisesRegex(BookIdentityConflict, "Server database"):
            resolve_book_identity(
                inspection,
                "sidecar",
                external_candidates=(
                    ExternalBookIdentity(
                        "Server database", "database_id", True
                    ),
                ),
            )

    def test_source_change_during_inspection_is_refused(self):
        self._write_epub(self.source)
        real_digest = source_sha256

        def change_then_hash(path):
            self._replace_archive_text(
                path, "OEBPS/chapter.xhtml", b"unchanged", b"changed"
            )
            return real_digest(path)

        with mock.patch(
            "epub_browser.book_identity.source_sha256",
            side_effect=change_then_hash,
        ):
            with self.assertRaisesRegex(BookIdentityError, "source changed"):
                inspect_book_identity(self.source)

    @staticmethod
    def _write_epub(path, embedded_book_id=None):
        container = """<?xml version="1.0"?>
<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0">
  <rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles>
</container>
"""
        embedded = (
            '<meta name="epub-browser:book-id" '
            f'content="{embedded_book_id}"/>'
            if embedded_book_id
            else ""
        )
        package = f"""<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="book-id">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="book-id">urn:test:identity</dc:identifier>
    <dc:title>Identity Book</dc:title><dc:language>en</dc:language>{embedded}
  </metadata>
  <manifest><item id="chapter" href="chapter.xhtml" media-type="application/xhtml+xml"/></manifest>
  <spine><itemref idref="chapter"/></spine>
</package>
"""
        with zipfile.ZipFile(path, "w") as archive:
            mimetype = zipfile.ZipInfo("mimetype")
            mimetype.compress_type = zipfile.ZIP_STORED
            archive.writestr(mimetype, "application/epub+zip")
            archive.writestr("META-INF/container.xml", container)
            archive.writestr("OEBPS/content.opf", package)
            archive.writestr("OEBPS/chapter.xhtml", b"unchanged")

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


if __name__ == "__main__":
    unittest.main()
