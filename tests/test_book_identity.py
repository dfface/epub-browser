import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from pypdf import PdfReader, PdfWriter
from pypdf.errors import PdfReadError

from epub_browser.book_identity import (
    BOOK_ID_STORAGE_EMBEDDED,
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
    discover_orphan_sidecars,
    read_exact_sidecar,
    read_sidecar_file,
    sidecar_path_for,
    write_sidecar,
)
from epub_browser.source_format import (
    EPUB_FORMAT,
    PDF_FORMAT,
    is_supported_source,
    source_format,
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

    def test_embedded_mode_falls_back_to_sidecar_for_encrypted_pdf(self):
        source = self.root / "encrypted.pdf"
        writer = PdfWriter()
        writer.add_blank_page(200, 300)
        writer.encrypt("protected")
        writer.write(source)
        before = source.read_bytes()

        resolved = resolve_book_identity(inspect_book_identity(source), BOOK_ID_STORAGE_EMBEDDED)
        self.assertEqual(read_exact_sidecar(source).book_id, resolved.book_id)
        self.assertEqual(read_exact_sidecar(source).source_fingerprint, source_sha256(source))
        repeated = resolve_book_identity(inspect_book_identity(source), BOOK_ID_STORAGE_EMBEDDED)
        self.assertEqual(repeated.book_id, resolved.book_id)
        self.assertEqual(source.read_bytes(), before)

    def test_pdf_embed_failure_uses_existing_book_id(self):
        source = self.root / "book.pdf"
        writer = PdfWriter()
        writer.add_blank_page(200, 300)
        writer.write(source)
        before = source.read_bytes()
        with mock.patch(
            "epub_browser.book_identity.embed_pdf_book_id",
            side_effect=PdfReadError("Object not found"),
        ):
            resolved = resolve_book_identity(
                inspect_book_identity(source),
                BOOK_ID_STORAGE_EMBEDDED,
                external_candidates=(ExternalBookIdentity("Server record", "existing_id", True),),
            )
        self.assertEqual(resolved.book_id, "existing_id")
        self.assertEqual(read_exact_sidecar(source).book_id, "existing_id")
        self.assertEqual(source.read_bytes(), before)

    def test_pdf_embed_failure_does_not_write_sidecar_after_source_changes(self):
        source = self.root / "changed.pdf"
        writer = PdfWriter()
        writer.add_blank_page(200, 300)
        writer.write(source)

        def change_source(*_args):
            with source.open("ab") as stream:
                stream.write(b"\n% changed by another process\n")
            raise OSError("source changed")

        with mock.patch("epub_browser.book_identity.embed_pdf_book_id", side_effect=change_source):
            with self.assertRaisesRegex(BookIdentityError, "source changed"):
                resolve_book_identity(inspect_book_identity(source), BOOK_ID_STORAGE_EMBEDDED)
        self.assertFalse(sidecar_path_for(source).exists())

    def test_pdf_embedding_preserves_page_objects_with_nonzero_generation(self):
        source = self.root / "reused-page-object.pdf"
        pdf = bytearray(b"%PDF-1.4\n")
        entries = [b"0000000000 65535 f \n"]
        for number, generation, body in (
            (1, 0, b"<< /Type /Catalog /Pages 2 0 R >>"),
            (2, 0, b"<< /Type /Pages /Count 1 /Kids [4 1 R] >>"),
            (3, 0, b"<< /Title (Reused page object) >>"),
            (4, 1, b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 300] >>"),
        ):
            entries.append(f"{len(pdf):010d} {generation:05d} n \n".encode())
            pdf.extend(f"{number} {generation} obj\n".encode() + body + b"\nendobj\n")
        startxref = len(pdf)
        pdf.extend(b"xref\n0 5\n" + b"".join(entries))
        pdf.extend(b"trailer\n<< /Size 5 /Root 1 0 R /Info 3 0 R >>\n")
        pdf.extend(f"startxref\n{startxref}\n%%EOF\n".encode())
        source.write_bytes(pdf)

        resolved = resolve_book_identity(inspect_book_identity(source), "embedded")

        self.assertTrue(source.read_bytes().startswith(pdf))
        self.assertFalse(sidecar_path_for(source).exists())
        reader = PdfReader(source, strict=True)
        self.assertEqual(reader.metadata.title, "Reused page object")
        self.assertEqual(reader.metadata["/EpubBrowserBookId"], resolved.book_id)
        self.assertEqual(len(reader.pages), 1)
        self.assertEqual(reader.pages[0].indirect_reference.generation, 1)

    def test_explicit_pdf_source_parent_contributes_orphan_sidecars(self):
        source = self.root / "old.PDF"
        writer = PdfWriter()
        writer.add_blank_page(200, 300)
        writer.write(source)
        first = resolve_book_identity(inspect_book_identity(source), "sidecar")
        orphan = sidecar_path_for(source)
        moved = self.root / "moved.pdf"
        source.rename(moved)

        orphan_sidecars = discover_orphan_sidecars((moved,), (moved,))
        second = resolve_book_identity(
            inspect_book_identity(moved, orphan_sidecars=orphan_sidecars), "sidecar"
        )

        self.assertEqual(orphan_sidecars, (orphan,))
        self.assertEqual(second.book_id, first.book_id)
        self.assertFalse(orphan.exists())
        self.assertEqual(read_exact_sidecar(moved).book_id, first.book_id)

    def test_source_format_classifies_supported_suffixes_case_insensitively(self):
        self.assertEqual(source_format(Path("book.EPUB")), EPUB_FORMAT)
        self.assertEqual(source_format(Path("book.PdF")), PDF_FORMAT)
        self.assertTrue(is_supported_source(Path("book.epub")))
        self.assertTrue(is_supported_source(Path("book.PDF")))
        self.assertFalse(is_supported_source(Path("book.txt")))
        with self.assertRaisesRegex(ValueError, "Unsupported book format: <none>"):
            source_format(Path("book"))

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
