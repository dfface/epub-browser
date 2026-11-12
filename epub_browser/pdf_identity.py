"""Store an EPUB Browser ID in the PDF document information dictionary."""

import os
import stat
import tempfile
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from pypdf.generic import NullObject

from .epub_identity import validate_book_id


PDF_BOOK_ID_KEY = "/EpubBrowserBookId"


def _read_book_id(reader: PdfReader) -> str | None:
    if reader.is_encrypted:
        return None
    metadata = reader.metadata
    if metadata is None or PDF_BOOK_ID_KEY not in metadata:
        return None
    return validate_book_id(metadata[PDF_BOOK_ID_KEY])


def read_pdf_book_id(path: Path) -> str | None:
    with path.open("rb") as source:
        return _read_book_id(PdfReader(source))


def embed_pdf_book_id(path: Path, book_id: str, expected_snapshot: tuple) -> str:
    """Append an incremental metadata update and replace the source atomically."""
    book_id = validate_book_id(book_id)
    if path.is_symlink():
        raise ValueError("refusing to replace a symbolic-link PDF")

    temporary = None
    try:
        with path.open("rb") as source:
            source_stat = os.fstat(source.fileno())
            if _snapshot(source_stat) != expected_snapshot:
                raise ValueError("PDF changed before its embedded ID could be written")
            reader = PdfReader(source)
            existing = _read_book_id(reader)
            if existing is not None:
                return existing
            if not stat.S_IMODE(source_stat.st_mode) & 0o222:
                raise ValueError("PDF source is read-only")
            if source_stat.st_nlink > 1:
                raise ValueError("PDF source has multiple hard links")
            if reader.is_encrypted:
                raise ValueError("cannot embed a book ID in an encrypted PDF")
            if "/Perms" in reader.root_object or any(
                field.get("/FT") == "/Sig"
                and field.get("/V") is not None
                and not isinstance(field["/V"], NullObject)
                for field in (reader.get_fields() or {}).values()
            ):
                raise ValueError("cannot embed a book ID in a signed PDF")

            writer = PdfWriter(reader, incremental=True)
            writer.add_metadata({PDF_BOOK_ID_KEY: book_id})
            with tempfile.NamedTemporaryFile(
                mode="w+b", dir=path.parent, prefix=f".{path.name}.", delete=False,
            ) as output:
                temporary = Path(output.name)
                writer.write(output)
                os.fchmod(output.fileno(), stat.S_IMODE(source_stat.st_mode))
                output.flush()
                os.fsync(output.fileno())
        if read_pdf_book_id(temporary) != book_id:
            raise ValueError("could not verify the embedded PDF book ID")
        if path.is_symlink() or _snapshot(path.stat()) != expected_snapshot:
            raise ValueError("PDF changed while its embedded ID was being written")
        os.replace(temporary, path)
        return book_id
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _snapshot(source_stat: os.stat_result) -> tuple[int, int, int, int]:
    return source_stat.st_dev, source_stat.st_ino, source_stat.st_size, source_stat.st_mtime_ns
