"""Bounded primitives for authenticated PDF document delivery."""

import hashlib
import json
import os
import re
import stat
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Optional
from urllib.parse import quote

import anyio
from starlette.requests import ClientDisconnect
from starlette.responses import Response


_RANGE_PATTERN = re.compile(r"bytes=(\d*)-(\d*)")
_MAX_RANGE_DIGITS = 20
_STREAM_CHUNK_SIZE = 64 * 1024
_MAX_REVISION_SIZE = 256
_MAX_METADATA_SIZE = 8 * 1024 * 1024


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


class PDFValidationError(ValueError):
    """A registered source or cached PDF is unsafe or no longer current."""


@dataclass(frozen=True)
class PDFDeliverySpecification:
    source_path: Path
    book_root: Path
    source_size: int
    source_mtime_ns: int
    source_digest: str
    output_revision: str
    metadata_schema_version: int


@dataclass
class ValidatedPDFDocument:
    file_descriptor: Optional[int]
    size: int
    digest: str

    def detach(self) -> int:
        descriptor = self.file_descriptor
        if descriptor is None:
            raise RuntimeError("PDF descriptor ownership was already transferred")
        self.file_descriptor = None
        return descriptor

    def close(self) -> None:
        descriptor = self.file_descriptor
        self.file_descriptor = None
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass


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


def _safe_open_flags() -> int:
    flags = os.O_RDONLY
    for name in ("O_CLOEXEC", "O_NOFOLLOW", "O_NONBLOCK"):
        flags |= getattr(os, name, 0)
    return flags


def _open_descriptor(path: Path) -> int:
    try:
        return os.open(os.fspath(path), _safe_open_flags())
    except OSError as error:
        raise PDFValidationError("PDF file could not be opened safely") from error


def _identity(file_stat) -> tuple:
    return (
        file_stat.st_dev,
        file_stat.st_ino,
        file_stat.st_mode,
        file_stat.st_size,
        file_stat.st_mtime_ns,
        file_stat.st_ctime_ns,
    )


def _path_matches_descriptor(path: Path, descriptor_stat) -> bool:
    try:
        path_stat = os.stat(os.fspath(path), follow_symlinks=False)
    except OSError:
        return False
    return (
        stat.S_ISREG(path_stat.st_mode)
        and path_stat.st_dev == descriptor_stat.st_dev
        and path_stat.st_ino == descriptor_stat.st_ino
    )


def _hash_file_descriptor(descriptor: int, expected_size: int) -> str:
    """Hash exactly the registered length and reject early EOF."""
    digest = hashlib.sha256()
    remaining = expected_size
    os.lseek(descriptor, 0, os.SEEK_SET)
    while remaining:
        chunk = os.read(descriptor, min(_STREAM_CHUNK_SIZE, remaining))
        if not chunk:
            raise PDFValidationError("PDF file ended during validation")
        digest.update(chunk)
        remaining -= len(chunk)
    return digest.hexdigest()


def open_validated_pdf_file(
    path: Path,
    *,
    expected_size: int,
    expected_digest: str,
    expected_mtime_ns: Optional[int] = None,
) -> int:
    """Safely open and validate a regular file, returning the same verified fd."""
    if (
        not isinstance(expected_size, int)
        or isinstance(expected_size, bool)
        or expected_size < 0
        or not isinstance(expected_digest, str)
    ):
        raise PDFValidationError("Invalid expected PDF metadata")
    descriptor = _open_descriptor(Path(path))
    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_size != expected_size
            or (
                expected_mtime_ns is not None
                and before.st_mtime_ns != expected_mtime_ns
            )
            or not _path_matches_descriptor(Path(path), before)
        ):
            raise PDFValidationError("PDF file metadata changed")
        digest = _hash_file_descriptor(descriptor, expected_size)
        after = os.fstat(descriptor)
        if (
            _identity(before) != _identity(after)
            or not _path_matches_descriptor(Path(path), after)
            or digest != expected_digest
        ):
            raise PDFValidationError("PDF file changed during validation")
        os.lseek(descriptor, 0, os.SEEK_SET)
        return descriptor
    except BaseException:
        try:
            os.close(descriptor)
        except OSError:
            pass
        raise


async def open_validated_pdf_file_async(
    path: Path,
    *,
    expected_size: int,
    expected_digest: str,
    expected_mtime_ns: Optional[int] = None,
) -> int:
    operation = partial(
        open_validated_pdf_file,
        path,
        expected_size=expected_size,
        expected_digest=expected_digest,
        expected_mtime_ns=expected_mtime_ns,
    )
    return await anyio.to_thread.run_sync(operation)


def _read_bounded_regular_file(path: Path, maximum_size: int) -> bytes:
    descriptor = _open_descriptor(path)
    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_size < 0
            or before.st_size > maximum_size
            or not _path_matches_descriptor(path, before)
        ):
            raise PDFValidationError("PDF cache metadata is unsafe")
        remaining = before.st_size
        chunks = []
        while remaining:
            chunk = os.read(descriptor, min(_STREAM_CHUNK_SIZE, remaining))
            if not chunk:
                raise PDFValidationError("PDF cache metadata ended early")
            chunks.append(chunk)
            remaining -= len(chunk)
        after = os.fstat(descriptor)
        if (
            _identity(before) != _identity(after)
            or not _path_matches_descriptor(path, after)
        ):
            raise PDFValidationError("PDF cache metadata changed")
        return b"".join(chunks)
    finally:
        try:
            os.close(descriptor)
        except OSError:
            pass


def prepare_pdf_delivery(
    specification: PDFDeliverySpecification,
) -> ValidatedPDFDocument:
    """Validate source and cache entirely in a worker-safe synchronous call."""
    source_descriptor = open_validated_pdf_file(
        specification.source_path,
        expected_size=specification.source_size,
        expected_digest=specification.source_digest,
        expected_mtime_ns=specification.source_mtime_ns,
    )
    os.close(source_descriptor)
    pdf_root = specification.book_root / "pdf"
    try:
        revision = _read_bounded_regular_file(
            specification.book_root / ".server-pdf-revision",
            _MAX_REVISION_SIZE,
        ).decode("utf-8").strip()
        metadata = json.loads(
            _read_bounded_regular_file(
                pdf_root / "metadata.json", _MAX_METADATA_SIZE
            ).decode("utf-8")
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PDFValidationError("Invalid PDF cache metadata") from error
    if not isinstance(metadata, dict):
        raise PDFValidationError("Invalid PDF cache metadata")
    expected_size = metadata.get("document_size")
    expected_digest = metadata.get("document_sha256")
    if (
        revision != specification.output_revision
        or metadata.get("schema_version") != specification.metadata_schema_version
        or metadata.get("source_format") != "pdf"
        or metadata.get("source_sha256") != specification.source_digest
        or metadata.get("source_size") != specification.source_size
        or metadata.get("source_mtime_ns") != specification.source_mtime_ns
        or expected_size != specification.source_size
        or expected_digest != specification.source_digest
    ):
        raise PDFValidationError("PDF cache requires refresh")
    descriptor = open_validated_pdf_file(
        pdf_root / "document.pdf",
        expected_size=expected_size,
        expected_digest=expected_digest,
    )
    return ValidatedPDFDocument(descriptor, expected_size, expected_digest)


async def prepare_pdf_delivery_async(
    specification: PDFDeliverySpecification,
) -> ValidatedPDFDocument:
    return await anyio.to_thread.run_sync(prepare_pdf_delivery, specification)


def _read_descriptor_chunk(descriptor: int, offset: int, length: int) -> bytes:
    if hasattr(os, "pread"):
        return os.pread(descriptor, length, offset)
    os.lseek(descriptor, offset, os.SEEK_SET)
    return os.read(descriptor, length)


class OwnedPDFFileResponse(Response):
    """ASGI response that closes its owned PDF descriptor on every exit path."""

    media_type = "application/pdf"

    def __init__(
        self,
        file_descriptor: int,
        byte_range: ByteRange,
        *,
        status_code: int,
        headers: dict,
    ):
        self.file_descriptor = file_descriptor
        self.byte_range = byte_range
        super().__init__(
            content=b"",
            status_code=status_code,
            headers=headers,
            media_type=self.media_type,
        )

    async def _stream_response(self, descriptor: int, send) -> None:
        await send({
            "type": "http.response.start",
            "status": self.status_code,
            "headers": self.raw_headers,
        })
        offset = self.byte_range.start
        remaining = self.byte_range.length
        while remaining:
            requested = min(_STREAM_CHUNK_SIZE, remaining)
            chunk = await anyio.to_thread.run_sync(
                _read_descriptor_chunk,
                descriptor,
                offset,
                requested,
            )
            if len(chunk) != requested:
                raise OSError("Validated PDF ended during delivery")
            remaining -= len(chunk)
            offset += len(chunk)
            await send({
                "type": "http.response.body",
                "body": chunk,
                "more_body": remaining > 0,
            })
        if self.byte_range.length == 0:
            await send({
                "type": "http.response.body",
                "body": b"",
                "more_body": False,
            })

    @staticmethod
    async def _listen_for_disconnect(receive) -> None:
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return

    async def _stream_until_disconnect(self, descriptor, receive, send) -> None:
        async with anyio.create_task_group() as task_group:
            async def run_and_cancel(operation, *args):
                try:
                    await operation(*args)
                finally:
                    task_group.cancel_scope.cancel()

            task_group.start_soon(
                run_and_cancel,
                self._stream_response,
                descriptor,
                send,
            )
            task_group.start_soon(
                run_and_cancel,
                self._listen_for_disconnect,
                receive,
            )

    async def __call__(self, scope, receive, send) -> None:
        descriptor = self.file_descriptor
        self.file_descriptor = None
        if descriptor is None:
            raise RuntimeError("PDF response was already consumed")
        try:
            spec_version = tuple(
                map(
                    int,
                    scope.get("asgi", {}).get("spec_version", "2.0").split("."),
                )
            )
            if spec_version >= (2, 4):
                try:
                    await self._stream_response(descriptor, send)
                except OSError as error:
                    raise ClientDisconnect() from error
            else:
                await self._stream_until_disconnect(descriptor, receive, send)
        finally:
            try:
                os.close(descriptor)
            except OSError:
                pass


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
