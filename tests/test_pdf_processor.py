from contextlib import redirect_stderr
import io
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
from PIL import Image

from epub_browser.pdf_processor import (
    PDFProcessingError,
    inspect_pdf,
    render_pdf_cover,
)


class PDFProcessorTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary_directory.name)

    def tearDown(self):
        self.temporary_directory.cleanup()

    def fixture_pdf(
        self,
        *,
        metadata=None,
        page_sizes=((200, 400),),
        rotations=(),
        outline=(),
        text_pages=(),
        password=None,
    ):
        source = self.directory / "fixture.pdf"
        writer = PdfWriter()
        for width, height in page_sizes:
            writer.add_blank_page(width=width, height=height)
        for page_index, degrees in rotations:
            writer.pages[page_index].rotate(degrees)
        for page_index in text_pages:
            font = DictionaryObject(
                {
                    NameObject("/Type"): NameObject("/Font"),
                    NameObject("/Subtype"): NameObject("/Type1"),
                    NameObject("/BaseFont"): NameObject("/Helvetica"),
                }
            )
            resources = DictionaryObject(
                {
                    NameObject("/Font"): DictionaryObject(
                        {NameObject("/F1"): writer._add_object(font)}
                    )
                }
            )
            content = DecodedStreamObject()
            content.set_data(b"BT /F1 12 Tf 20 30 Td (Readable text) Tj ET")
            writer.pages[page_index][NameObject("/Resources")] = resources
            writer.pages[page_index][NameObject("/Contents")] = writer._add_object(
                content
            )
        outline_parents = {}
        for title, page_number, level in outline:
            parent = outline_parents.get(level - 1) if level else None
            outline_parents[level] = writer.add_outline_item(
                title, page_number - 1, parent=parent
            )
            for nested_level in tuple(outline_parents):
                if nested_level > level:
                    del outline_parents[nested_level]
        if metadata:
            writer.add_metadata(metadata)
        if password is not None:
            writer.encrypt(password)
        with source.open("wb") as stream:
            writer.write(stream)
        return source

    def test_inspect_pdf_returns_document_metadata(self):
        source = self.fixture_pdf(
            metadata={
                "/Title": "Analytical Notes",
                "/Author": "Ada Lovelace; Grace Hopper",
                "/Keywords": "mathematics, computing; history",
                "/Lang": "en-GB",
            }
        )

        metadata = inspect_pdf(source)

        self.assertEqual(metadata.title, "Analytical Notes")
        self.assertEqual(metadata.authors, ("Ada Lovelace", "Grace Hopper"))
        self.assertEqual(metadata.tags, ("mathematics", "computing", "history"))
        self.assertEqual(metadata.language, "en-GB")
        self.assertIsNone(metadata.cover)

    def test_inspect_pdf_returns_rotation_aware_geometry_for_every_page(self):
        source = self.fixture_pdf(
            page_sizes=((200, 400), (500, 300), (72, 144)),
            rotations=((1, 90),),
        )

        metadata = inspect_pdf(source)

        self.assertEqual(
            [
                (page.page_number, page.width, page.height)
                for page in metadata.pages
            ],
            [(1, 200.0, 400.0), (2, 300.0, 500.0), (3, 72.0, 144.0)],
        )

    def test_inspect_pdf_attaches_outline_labels_to_destination_pages(self):
        source = self.fixture_pdf(
            page_sizes=((200, 400), (200, 400), (200, 400)),
            outline=(
                ("Part One", 1, 0),
                ("Opening", 2, 1),
                ("Detail", 2, 2),
                ("Again", 2, 0),
            ),
        )

        metadata = inspect_pdf(source)

        self.assertEqual(metadata.pages[0].outline_labels, ("Part One",))
        self.assertEqual(
            metadata.pages[1].outline_labels, ("Opening", "Detail", "Again")
        )
        self.assertEqual(metadata.pages[2].outline_labels, ())

    def test_inspect_pdf_reports_extractable_text_capability(self):
        blank = inspect_pdf(self.fixture_pdf())
        readable = inspect_pdf(
            self.fixture_pdf(
                page_sizes=((200, 400), (200, 400)),
                text_pages=(1,),
            )
        )

        self.assertFalse(blank.has_extractable_text)
        self.assertTrue(readable.has_extractable_text)

    def test_inspect_pdf_reports_encrypted_documents_without_decrypting_them(self):
        source = self.fixture_pdf(
            metadata={"/Title": "Private title"}, password="secret"
        )

        metadata = inspect_pdf(source)

        self.assertTrue(metadata.encrypted)
        self.assertEqual(metadata.pages, ())
        self.assertFalse(metadata.has_extractable_text)
        self.assertIsNone(metadata.title)

    def test_inspect_pdf_rejects_a_missing_signature_with_a_stable_error(self):
        source = self.directory / "not-a-document.pdf"
        source.write_bytes(b"This is not a PDF")

        with self.assertRaises(PDFProcessingError) as raised:
            inspect_pdf(source)

        self.assertEqual(str(raised.exception), "PDF signature is missing")
        self.assertNotIn(source.name, str(raised.exception))

    def test_inspect_pdf_checks_only_the_bounded_signature_window(self):
        valid_source = self.fixture_pdf()
        source = self.directory / "late-signature.pdf"
        source.write_bytes(b"x" * 1024 + valid_source.read_bytes())

        with self.assertRaises(PDFProcessingError) as raised:
            inspect_pdf(source)

        self.assertEqual(str(raised.exception), "PDF signature is missing")

    def test_inspect_pdf_wraps_parser_failures_without_leaking_the_path(self):
        source = self.directory / "sensitive-customer-name.pdf"
        source.write_bytes(b"%PDF-1.7\ntruncated")

        with redirect_stderr(io.StringIO()):
            with self.assertRaises(PDFProcessingError) as raised:
                inspect_pdf(source)

        self.assertEqual(str(raised.exception), "Unable to inspect PDF")
        self.assertNotIn(source.name, str(raised.exception))
        self.assertIsNone(raised.exception.__cause__)

    def test_render_pdf_cover_writes_a_bounded_first_page_png(self):
        source = self.fixture_pdf(page_sizes=((1200, 1800), (1800, 1200)))
        destination = self.directory / "cover.png"

        result = render_pdf_cover(source, destination)

        self.assertEqual(result, destination)
        with Image.open(destination) as image:
            self.assertEqual(image.format, "PNG")
            self.assertEqual(image.size, (600, 900))

    def test_render_pdf_cover_rejects_a_missing_signature_stably(self):
        source = self.directory / "not-a-document.pdf"
        source.write_bytes(b"not a PDF")
        destination = self.directory / "cover.png"

        with self.assertRaises(PDFProcessingError) as raised:
            render_pdf_cover(source, destination)

        self.assertEqual(str(raised.exception), "PDF signature is missing")
        self.assertFalse(destination.exists())

    def test_render_pdf_cover_returns_none_for_an_encrypted_document(self):
        source = self.fixture_pdf(password="secret")
        destination = self.directory / "cover.png"

        self.assertIsNone(render_pdf_cover(source, destination))
        self.assertFalse(destination.exists())

    def test_render_pdf_cover_rejects_nonpositive_bounds(self):
        source = self.fixture_pdf()

        with self.assertRaises(PDFProcessingError) as raised:
            render_pdf_cover(source, self.directory / "cover.png", max_width=0)

        self.assertEqual(
            str(raised.exception), "PDF cover bounds must be positive"
        )

    def test_render_pdf_cover_wraps_output_failures_without_leaking_the_path(self):
        source = self.fixture_pdf()
        destination = self.directory / "sensitive-customer-name" / "cover.png"

        with self.assertRaises(PDFProcessingError) as raised:
            render_pdf_cover(source, destination)

        self.assertEqual(str(raised.exception), "Unable to render PDF cover")
        self.assertNotIn("sensitive-customer-name", str(raised.exception))
        self.assertIsNone(raised.exception.__cause__)

    def test_package_metadata_declares_compatible_pdf_runtime_ranges(self):
        repository_root = Path(__file__).parents[1]
        egg_base = self.directory / "egg-info"
        egg_base.mkdir()

        subprocess.run(
            [
                sys.executable,
                "setup.py",
                "egg_info",
                "--egg-base",
                str(egg_base),
            ],
            cwd=repository_root,
            check=True,
            capture_output=True,
            text=True,
        )
        requirements_file = next(egg_base.glob("*.egg-info/requires.txt"))
        requirements = set(requirements_file.read_text(encoding="utf-8").splitlines())

        self.assertTrue(
            {
                "pypdf<7.0,>=6.0",
                "pypdfium2<6.0,>=5.0",
                "Pillow<12.0,>=10.0",
            }.issubset(requirements)
        )


if __name__ == "__main__":
    unittest.main()
