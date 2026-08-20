import copy
import os
import re
import shutil
import stat
import tempfile
import urllib.parse
import zipfile
from pathlib import Path, PurePosixPath
from typing import Optional
from xml.etree import ElementTree as ET
from xml.parsers import expat

from .identity import new_server_book_id


CONTAINER_NAMESPACE = "urn:oasis:names:tc:opendocument:xmlns:container"
OPF_NAMESPACE = "http://www.idpf.org/2007/opf"
BOOK_ID_META_NAME = "epub-browser:book-id"
_SAFE_BOOK_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


class EPUBIdentityWriteRefused(RuntimeError):
    """The EPUB can be read, but changing it would be unsafe."""


def read_embedded_book_id(epub_path: Path) -> Optional[str]:
    """Read epub-browser's durable identity from the primary package document."""
    path = Path(epub_path)
    with zipfile.ZipFile(path, "r") as archive:
        package_info = _package_document_info(archive)
        package_bytes = archive.read(package_info)
    return _book_id_from_package(package_bytes)


def ensure_embedded_book_id(
    epub_path: Path,
    preferred_book_id: Optional[str] = None,
) -> str:
    """Return an existing identity or safely add one to an unsigned EPUB."""
    path = Path(epub_path)
    preferred = _validated_book_id(preferred_book_id) if preferred_book_id else None
    existing = read_embedded_book_id(path)
    if existing:
        if preferred and preferred != existing:
            raise ValueError(
                f"EPUB book ID {existing!r} conflicts with preferred ID {preferred!r}"
            )
        return existing

    if path.is_symlink():
        raise EPUBIdentityWriteRefused("refusing to replace a symbolic-link EPUB")
    source_stat = path.stat()
    if not stat.S_IMODE(source_stat.st_mode) & 0o222:
        raise EPUBIdentityWriteRefused("EPUB source is read-only")
    if source_stat.st_nlink > 1:
        raise EPUBIdentityWriteRefused("EPUB source has multiple hard links")

    book_id = preferred or new_server_book_id()
    with zipfile.ZipFile(path, "r") as archive:
        infos = archive.infolist()
        _validate_container_for_rewrite(archive, infos)
        if any(info.filename == "META-INF/signatures.xml" for info in infos):
            raise EPUBIdentityWriteRefused("signed EPUB cannot be modified safely")
        package_info = _package_document_info(archive)
        package_bytes = archive.read(package_info)
        current = _book_id_from_package(package_bytes)
        if current:
            if preferred and preferred != current:
                raise ValueError(
                    f"EPUB book ID {current!r} conflicts with preferred ID "
                    f"{preferred!r}"
                )
            return current
        updated_package = _inject_book_id(package_bytes, book_id)

    _replace_package_atomically(
        path,
        package_info.filename,
        updated_package,
        source_stat,
    )
    return book_id


def _package_document_info(archive: zipfile.ZipFile) -> zipfile.ZipInfo:
    infos = archive.infolist()
    names = [info.filename for info in infos]
    if len(names) != len(set(names)):
        raise ValueError("EPUB contains duplicate ZIP entry names")
    by_name = {info.filename: info for info in infos}
    try:
        container_bytes = archive.read("META-INF/container.xml")
    except KeyError as error:
        raise ValueError("EPUB is missing META-INF/container.xml") from error
    try:
        container = ET.fromstring(container_bytes)
    except ET.ParseError as error:
        raise ValueError("EPUB container.xml is not valid XML") from error
    rootfile = container.find(f".//{{{CONTAINER_NAMESPACE}}}rootfile")
    if rootfile is None:
        raise ValueError("EPUB container does not identify a package document")
    package_path = _safe_archive_path(rootfile.get("full-path"))
    try:
        return by_name[package_path]
    except KeyError as error:
        raise ValueError(f"EPUB package document is missing: {package_path}") from error


def _safe_archive_path(value: Optional[str]) -> str:
    if not value:
        raise ValueError("EPUB package path is empty")
    decoded = urllib.parse.unquote(value)
    path = PurePosixPath(decoded)
    if (
        not decoded
        or "\x00" in decoded
        or "\\" in decoded
        or path.is_absolute()
        or ".." in path.parts
    ):
        raise ValueError(f"Unsafe EPUB package path: {value}")
    return path.as_posix()


def _book_id_from_package(package_bytes: bytes) -> Optional[str]:
    try:
        root = ET.fromstring(package_bytes)
    except ET.ParseError as error:
        raise ValueError("EPUB package document is not valid XML") from error
    metadata = root.find(f"{{{OPF_NAMESPACE}}}metadata")
    if metadata is None:
        raise ValueError("EPUB package document has no metadata element")
    values = []
    for element in metadata.findall(f"{{{OPF_NAMESPACE}}}meta"):
        value = None
        if element.get("name") == BOOK_ID_META_NAME:
            value = element.get("content")
        elif element.get("property") == BOOK_ID_META_NAME:
            value = element.text
        if value is not None and value.strip():
            values.append(_validated_book_id(value.strip()))
    unique = set(values)
    if len(unique) > 1:
        raise ValueError("EPUB contains conflicting embedded book IDs")
    return values[0] if values else None


def _validated_book_id(value: str) -> str:
    if not _SAFE_BOOK_ID.fullmatch(value):
        raise ValueError(f"Invalid embedded EPUB book ID: {value!r}")
    return value


def _inject_book_id(package_bytes: bytes, book_id: str) -> bytes:
    if _book_id_from_package(package_bytes):
        return package_bytes

    parser = expat.ParserCreate()
    depth = 0
    metadata_name = None
    insertion_index = None
    declared_encoding = None

    def xml_decl(_version, encoding, _standalone):
        nonlocal declared_encoding
        declared_encoding = encoding

    def start_element(name, _attributes):
        nonlocal depth, metadata_name
        depth += 1
        if depth == 2 and name.rsplit(":", 1)[-1] == "metadata":
            metadata_name = name

    def end_element(name):
        nonlocal depth, insertion_index
        if depth == 2 and metadata_name == name:
            insertion_index = parser.CurrentByteIndex
        depth -= 1

    parser.XmlDeclHandler = xml_decl
    parser.StartElementHandler = start_element
    parser.EndElementHandler = end_element
    try:
        parser.Parse(package_bytes, True)
    except expat.ExpatError as error:
        raise ValueError("EPUB package document is not valid XML") from error
    if metadata_name is None or insertion_index is None:
        raise ValueError("EPUB package document has no writable metadata element")

    prefix = metadata_name.rsplit(":", 1)[0] + ":" if ":" in metadata_name else ""
    fragment = (
        f'<{prefix}meta name="{BOOK_ID_META_NAME}" content="{book_id}"/>'
    )
    encoded_fragment = fragment.encode(
        _package_encoding(package_bytes, declared_encoding)
    )
    return (
        package_bytes[:insertion_index]
        + encoded_fragment
        + package_bytes[insertion_index:]
    )


def _package_encoding(package_bytes: bytes, declared: Optional[str]) -> str:
    if package_bytes.startswith(b"\xff\xfe"):
        return "utf-16-le"
    if package_bytes.startswith(b"\xfe\xff"):
        return "utf-16-be"
    normalized = (declared or "utf-8").lower().replace("_", "-")
    if normalized == "utf-16":
        raise EPUBIdentityWriteRefused(
            "UTF-16 EPUB package has no byte-order mark; refusing to rewrite"
        )
    return normalized


def _validate_container_for_rewrite(
    archive: zipfile.ZipFile,
    infos: list[zipfile.ZipInfo],
) -> None:
    mimetype = next(
        (info for info in infos if info.filename == "mimetype"),
        None,
    )
    if mimetype is None:
        raise EPUBIdentityWriteRefused("EPUB has no mimetype entry")
    if archive.read(mimetype) != b"application/epub+zip":
        raise EPUBIdentityWriteRefused("EPUB mimetype content is invalid")
    for info in infos:
        if info.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}:
            raise EPUBIdentityWriteRefused(
                f"unsupported EPUB compression for {info.filename}"
            )
        if info.flag_bits & 0x1:
            raise EPUBIdentityWriteRefused(
                f"encrypted ZIP entry cannot be rewritten safely: {info.filename}"
            )


def _replace_package_atomically(
    source_path: Path,
    package_name: str,
    package_bytes: bytes,
    original_stat,
) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{source_path.name}.",
        suffix=".tmp",
        dir=source_path.parent,
    )
    os.close(descriptor)
    temporary_path = Path(temporary_name)
    try:
        with zipfile.ZipFile(source_path, "r") as source:
            source_infos = source.infolist()
            with zipfile.ZipFile(temporary_path, "w", allowZip64=True) as destination:
                destination.comment = source.comment
                for info in source_infos:
                    copied_info = copy.copy(info)
                    if info.filename == package_name:
                        destination.writestr(copied_info, package_bytes)
                        continue
                    with source.open(info, "r") as reader:
                        with destination.open(
                            copied_info,
                            "w",
                            force_zip64=info.file_size >= zipfile.ZIP64_LIMIT,
                        ) as writer:
                            shutil.copyfileobj(reader, writer, length=1024 * 1024)

        shutil.copystat(source_path, temporary_path)
        os.utime(temporary_path, None)
        _validate_rewritten_archive(
            source_path,
            temporary_path,
            package_name,
            source_infos,
            _book_id_from_package(package_bytes),
        )
        with temporary_path.open("rb") as rewritten:
            os.fsync(rewritten.fileno())

        current_stat = source_path.stat()
        original_identity = (
            original_stat.st_dev,
            original_stat.st_ino,
            original_stat.st_size,
            original_stat.st_mtime_ns,
        )
        current_identity = (
            current_stat.st_dev,
            current_stat.st_ino,
            current_stat.st_size,
            current_stat.st_mtime_ns,
        )
        if current_identity != original_identity:
            raise RuntimeError("EPUB source changed while its book ID was being written")
        os.replace(temporary_path, source_path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _validate_rewritten_archive(
    source_path: Path,
    rewritten_path: Path,
    package_name: str,
    source_infos: list[zipfile.ZipInfo],
    expected_book_id: str,
) -> None:
    with zipfile.ZipFile(source_path, "r") as source:
        source_comment = source.comment
        expected_unchanged = {
            info.filename: (info.CRC, info.file_size)
            for info in source_infos
            if info.filename != package_name
        }
    with zipfile.ZipFile(rewritten_path, "r") as rewritten:
        rewritten_infos = rewritten.infolist()
        if [info.filename for info in rewritten_infos] != [
            info.filename for info in source_infos
        ]:
            raise RuntimeError("rewritten EPUB changed ZIP entry order")
        if rewritten.comment != source_comment:
            raise RuntimeError("rewritten EPUB changed its ZIP comment")
        _validate_container_for_rewrite(rewritten, rewritten_infos)
        if rewritten.testzip() is not None:
            raise RuntimeError("rewritten EPUB failed its CRC check")
        actual_unchanged = {
            info.filename: (info.CRC, info.file_size)
            for info in rewritten_infos
            if info.filename != package_name
        }
        if actual_unchanged != expected_unchanged:
            raise RuntimeError("rewritten EPUB changed a non-package resource")
    if read_embedded_book_id(rewritten_path) != expected_book_id:
        raise RuntimeError("rewritten EPUB did not retain its embedded book ID")
