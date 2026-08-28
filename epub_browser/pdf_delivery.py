"""Bounded primitives for authenticated PDF document delivery."""

from dataclasses import dataclass
import hashlib
import re
from typing import Optional
from urllib.parse import quote


_RANGE_PATTERN = re.compile(r"bytes=(\d*)-(\d*)")
_MAX_RANGE_DIGITS = 20
_STREAM_CHUNK_SIZE = 64 * 1024


@dataclass(frozen=True)
class ByteRange:
    start: int
    end: int

    @property
    def length(self) -> int:
        return self.end - self.start + 1


class RangeNotSatisfiable(ValueError):
    def __init__(self, size: int):
        super().__init__("Range is not satisfiable")
        self.size = size


def parse_single_range(value: str, size: int) -> Optional[ByteRange]:
    """Normalize one HTTP byte range, or return ``None`` when it is absent."""
    if not isinstance(size, int) or isinstance(size, bool) or size < 0:
        raise ValueError("Document size must be a non-negative integer")
    if value is None:
        return None
    if not isinstance(value, str):
        raise RangeNotSatisfiable(size)
    match = _RANGE_PATTERN.fullmatch(value.strip())
    if match is None:
        raise RangeNotSatisfiable(size)
    start_text, end_text = match.groups()
    if not start_text and not end_text:
        raise RangeNotSatisfiable(size)
    if (
        len(start_text) > _MAX_RANGE_DIGITS
        or len(end_text) > _MAX_RANGE_DIGITS
        or size == 0
    ):
        raise RangeNotSatisfiable(size)

    if not start_text:
        suffix_length = int(end_text)
        if suffix_length <= 0:
            raise RangeNotSatisfiable(size)
        return ByteRange(max(0, size - suffix_length), size - 1)

    start = int(start_text)
    if start >= size:
        raise RangeNotSatisfiable(size)
    if not end_text:
        return ByteRange(start, size - 1)
    end = int(end_text)
    if end < start:
        raise RangeNotSatisfiable(size)
    return ByteRange(start, min(end, size - 1))


def sha256_stream(stream) -> str:
    """Hash an open binary stream without an unbounded read."""
    digest = hashlib.sha256()
    stream.seek(0)
    while True:
        chunk = stream.read(_STREAM_CHUNK_SIZE)
        if not chunk:
            return digest.hexdigest()
        digest.update(chunk)


def iter_file_range(stream, byte_range: ByteRange):
    """Yield exactly one normalized range from an already validated file."""
    remaining = byte_range.length
    stream.seek(byte_range.start)
    try:
        while remaining:
            chunk = stream.read(min(_STREAM_CHUNK_SIZE, remaining))
            if not chunk:
                return
            remaining -= len(chunk)
            yield chunk
    finally:
        stream.close()


def if_none_match_matches(value: str, etag: str) -> bool:
    if not value:
        return False
    expected = etag.removeprefix("W/")
    for candidate in value.split(","):
        candidate = candidate.strip()
        if candidate == "*" or candidate.removeprefix("W/") == expected:
            return True
    return False


def inline_pdf_disposition(source_name: str) -> str:
    """Build a path-free, header-safe inline filename."""
    name = str(source_name or "").replace("\\", "_").replace("/", "_")
    name = "".join(
        character if ord(character) >= 32 and ord(character) != 127 else "_"
        for character in name
    )
    name = name.strip().strip(".") or "document.pdf"
    if not name.casefold().endswith(".pdf"):
        name += ".pdf"
    fallback = "".join(
        character
        if character.isascii()
        and (character.isalnum() or character in " ._-")
        else "_"
        for character in name
    )
    fallback = fallback.replace('"', "_").strip().strip(".") or "document.pdf"
    encoded = quote(name, safe="")
    return f'inline; filename="{fallback}"; filename*=UTF-8\'\'{encoded}'
