from contextlib import redirect_stderr
import io
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, PropertyMock

from pypdf import PdfReader, PdfWriter
from pypdf.generic import (
    DecodedStreamObject,
    DictionaryObject,
    NameObject,
    RectangleObject,
    TextStringObject,
)
from PIL import Image

from epub_browser.pdf_processor import (
    PDFProcessingError,
    inspect_pdf,
    render_pdf_cover,
)


class BoundedReadSpy:
    def __init__(self, stream):
        self.stream = stream
        self.read_sizes = []

    def read(self, size=-1):
        self.read_sizes.append(size)
        if size is None or size < 0:
            raise AssertionError("PDF inspection attempted an unbounded read")
        return self.stream.read(size)

    def __getattr__(self, name):
        return getattr(self.stream, name)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.stream.close()


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
        box_overrides=(),
        invalid_crop_pages=(),
    ):
        source = self.directory / "fixture.pdf"
        writer = PdfWriter()
        for width, height in page_sizes:
            writer.add_blank_page(width=width, height=height)
        for page_index, degrees in rotations:
            writer.pages[page_index].rotate(degrees)
        for page_index, media_box, crop_box in box_overrides:
            writer.pages[page_index][NameObject("/MediaBox")] = RectangleObject(
                media_box
            )
            writer.pages[page_index][NameObject("/CropBox")] = RectangleObject(
                crop_box
            )
        for page_index in invalid_crop_pages:
            writer.pages[page_index][NameObject("/CropBox")] = TextStringObject(
                "broken"
            )
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

    def corrupt_first_xref_offset(self, source):
        data = source.read_bytes()
        object_match = re.search(rb"(?:^|\n)(1 0 obj\s)", data)
        self.assertIsNotNone(object_match)
        object_offset = object_match.start(1)
        entry = f"{object_offset:010d} 00000 n ".encode("ascii")
        self.assertIn(entry, data)
        source.write_bytes(
            data.replace(
                entry,
                f"{object_offset + 1:010d} 00000 n ".encode("ascii"),
                1,
            )
        )
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

    def test_inspect_pdf_keeps_one_bounded_source_stream_alive(self):
        source = self.fixture_pdf(
            page_sizes=((200, 400), (300, 500)), text_pages=(1,)
        )
        original_path_open = Path.open
        spies = []

        def guarded_path_open(path, *args, **kwargs):
            stream = original_path_open(path, *args, **kwargs)
            if path == source and args and args[0] == "rb":
                spy = BoundedReadSpy(stream)
                spies.append(spy)
                return spy
            return stream

        with patch.object(Path, "open", new=guarded_path_open):
            with patch("builtins.open", side_effect=AssertionError("path reopened")):
                metadata = inspect_pdf(source)

        self.assertEqual(len(metadata.pages), 2)
        self.assertEqual(len(spies), 1)
        self.assertTrue(spies[0].read_sizes)

    def test_inspect_pdf_rejects_unbounded_corrupt_xref_recovery(self):
        source = self.corrupt_first_xref_offset(
            self.fixture_pdf(metadata={"/Title": "Corrupt xref"})
        )
        original_path_open = Path.open
        spies = []

        def guarded_path_open(path, *args, **kwargs):
            stream = original_path_open(path, *args, **kwargs)
            if path == source and args and args[0] == "rb":
                spy = BoundedReadSpy(stream)
                spies.append(spy)
                return spy
            return stream

        with patch.object(Path, "open", new=guarded_path_open):
            with redirect_stderr(io.StringIO()):
                with self.assertRaises(PDFProcessingError) as raised:
                    inspect_pdf(source)

        self.assertEqual(str(raised.exception), "Unable to inspect PDF")
        self.assertIsNone(raised.exception.__cause__)
        self.assertEqual(len(spies), 1)
        self.assertFalse(
            any(size is None or size < 0 for size in spies[0].read_sizes)
        )

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

    def test_inspect_pdf_normalizes_and_clips_page_boxes_before_rotation(self):
        source = self.fixture_pdf(
            page_sizes=((600, 800), (600, 800), (600, 800)),
            rotations=((0, 90),),
            box_overrides=(
                (0, (0, 0, 600, 800), (-100, 100, 700, 500)),
                (1, (600, 800, 0, 0), (500, 700, 100, 200)),
                (2, (0, 0, 600, 800), (700, 900, 900, 1000)),
            ),
        )

        metadata = inspect_pdf(source)

        self.assertEqual(
            [(page.width, page.height) for page in metadata.pages],
            [(400.0, 600.0), (400.0, 500.0), (600.0, 800.0)],
        )

    def test_inspect_pdf_falls_back_to_media_box_for_invalid_crop_box(self):
        source = self.fixture_pdf(
            page_sizes=((600, 800),), invalid_crop_pages=(0,)
        )

        metadata = inspect_pdf(source)

        self.assertEqual(
            (metadata.pages[0].width, metadata.pages[0].height),
            (600.0, 800.0),
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

    def test_inspect_pdf_skips_one_malformed_outline_destination(self):
        source = self.fixture_pdf(
            page_sizes=((200, 400), (200, 400), (200, 400)),
            outline=(
                ("Good", 1, 0),
                ("Malformed", 2, 0),
                ("Later", 3, 0),
            ),
        )
        original_destination_page = PdfReader.get_destination_page_number

        def destination_page(reader, destination):
            if destination.title == "Malformed":
                raise ValueError("broken outline action")
            return original_destination_page(reader, destination)

        with patch.object(
            PdfReader, "get_destination_page_number", new=destination_page
        ):
            metadata = inspect_pdf(source)

        self.assertEqual(metadata.pages[0].outline_labels, ("Good",))
        self.assertEqual(metadata.pages[1].outline_labels, ())
        self.assertEqual(metadata.pages[2].outline_labels, ("Later",))

    def test_inspect_pdf_keeps_pages_when_the_outline_tree_is_malformed(self):
        source = self.fixture_pdf(
            page_sizes=((200, 400), (300, 500)),
            text_pages=(1,),
        )

        with patch.object(
            PdfReader,
            "outline",
            new_callable=PropertyMock,
            side_effect=ValueError("broken outline tree"),
        ):
            metadata = inspect_pdf(source)

        self.assertEqual(len(metadata.pages), 2)
        self.assertEqual(metadata.pages[0].outline_labels, ())
        self.assertEqual(metadata.pages[1].outline_labels, ())
        self.assertTrue(metadata.has_extractable_text)

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
            metadata={"/Title": "Private title"},
            page_sizes=((200, 400), (500, 300)),
            rotations=((1, 90),),
            password="secret",
        )

        metadata = inspect_pdf(source)

        self.assertTrue(metadata.encrypted)
        self.assertEqual(
            [(page.width, page.height) for page in metadata.pages],
            [(200.0, 400.0), (300.0, 500.0)],
        )
        self.assertFalse(metadata.has_extractable_text)
        self.assertIsNone(metadata.title)

    def test_inspect_pdf_uses_an_empty_password_when_it_unlocks_the_document(self):
        source = self.fixture_pdf(
            metadata={"/Title": "Open encryption"},
            page_sizes=((200, 400), (300, 500)),
            text_pages=(1,),
            password="",
        )

        metadata = inspect_pdf(source)

        self.assertTrue(metadata.encrypted)
        self.assertEqual(metadata.title, "Open encryption")
        self.assertEqual(len(metadata.pages), 2)
        self.assertTrue(metadata.has_extractable_text)

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

    def test_render_pdf_cover_preserves_existing_cover_on_encoder_failure(self):
        source = self.fixture_pdf()
        destination = self.directory / "cover.png"
        destination.write_bytes(b"existing-cover")

        def fail_after_partial_write(image, output, *args, **kwargs):
            if hasattr(output, "write"):
                output.write(b"partial")
                output.flush()
            else:
                Path(output).write_bytes(b"partial")
            raise OSError("encoder failed")

        with patch.object(Image.Image, "save", new=fail_after_partial_write):
            with self.assertRaises(PDFProcessingError) as raised:
                render_pdf_cover(source, destination)

        self.assertEqual(str(raised.exception), "Unable to render PDF cover")
        self.assertEqual(destination.read_bytes(), b"existing-cover")
        self.assertEqual(list(self.directory.glob(".cover.png.*.tmp")), [])

    def test_render_pdf_cover_preserves_existing_cover_when_replace_fails(self):
        source = self.fixture_pdf()
        destination = self.directory / "cover.png"
        destination.write_bytes(b"existing-cover")

        with patch(
            "epub_browser.pdf_processor.os.replace",
            side_effect=OSError("replace failed"),
        ):
            with self.assertRaises(PDFProcessingError) as raised:
                render_pdf_cover(source, destination)

        self.assertEqual(str(raised.exception), "Unable to render PDF cover")
        self.assertEqual(destination.read_bytes(), b"existing-cover")
        self.assertEqual(list(self.directory.glob(".cover.png.*.tmp")), [])

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
