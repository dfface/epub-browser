"""Store an EPUB Browser ID in the PDF document information dictionary."""

from __future__ import annotations

import os
import shutil
import stat
import tempfile
from pathlib import Path
from typing import BinaryIO

from pypdf import PdfReader
from pypdf.generic import (
    DictionaryObject,
    IndirectObject,
    NameObject,
    NullObject,
    NumberObject,
    TextStringObject,
)

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

            with tempfile.NamedTemporaryFile(
                mode="w+b", dir=path.parent, prefix=f".{path.name}.", delete=False,
            ) as output:
                temporary = Path(output.name)
                _write_metadata_update(reader, source, output, book_id)
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


def _write_metadata_update(
    reader: PdfReader, source: BinaryIO, output: BinaryIO, book_id: str
) -> None:
    # pypdf's incremental writer clones the page tree, where references with
    # nonzero generations can fail to resolve. This revision adds only /Info.
    previous_xref = reader._startxref
    if reader._get_xref_issues(source, previous_xref):
        raise ValueError("cannot embed a book ID in a PDF with a broken cross-reference pointer")

    info = reader.metadata
    if info is None:
        info = DictionaryObject()
    info[NameObject(PDF_BOOK_ID_KEY)] = TextStringObject(book_id)

    info_number = 1 + max(
        reader.trailer.get("/Size", 0) - 1,
        max((number for entries in reader.xref.values() for number in entries), default=0),
        max((number for entries in reader.xref_free_entry.values() for number in entries), default=0),
        max(reader.xref_objStm, default=0),
        max((number for _, number in reader.resolved_objects), default=0),
    )
    trailer = DictionaryObject({
        NameObject("/Size"): NumberObject(info_number + 1),
        NameObject("/Root"): reader.trailer.raw_get("/Root"),
        NameObject("/Info"): IndirectObject(info_number, 0, reader),
        NameObject("/Prev"): NumberObject(previous_xref),
    })
    if "/ID" in reader.trailer:
        trailer[NameObject("/ID")] = reader.trailer.raw_get("/ID")

    source.seek(0)
    shutil.copyfileobj(source, output)
    output.write(b"\n")
    info_offset = output.tell()
    if info_offset >= 10**10:
        raise ValueError("PDF is too large for an embedded book ID cross-reference table")
    output.write(f"{info_number} 0 obj\n".encode("ascii"))
    info.write_to_stream(output)
    output.write(b"\nendobj\n")
    xref_offset = output.tell()
    output.write(f"xref\n{info_number} 1\n{info_offset:010d} 00000 n \ntrailer\n".encode("ascii"))
    trailer.write_to_stream(output)
    output.write(f"\nstartxref\n{xref_offset}\n%%EOF\n".encode("ascii"))


def _snapshot(source_stat: os.stat_result) -> tuple[int, int, int, int]:
    return source_stat.st_dev, source_stat.st_ino, source_stat.st_size, source_stat.st_mtime_ns
