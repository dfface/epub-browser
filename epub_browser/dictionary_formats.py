"""Readers for administrator-installed local dictionary packages.

Dictionary definitions are retained exactly as published. Rendering happens in
an isolated reader surface rather than rewriting a dictionary's markup during
import.
"""

from __future__ import annotations

import base64
import gzip
import html.parser
import json
import posixpath
import re
import struct
import unicodedata
from urllib.parse import unquote
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


class DictionaryFormatError(ValueError):
    """A stable, safe reason why a local dictionary cannot be installed."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class DictionaryEntry:
    headword: str
    normalized_headword: str
    aliases: tuple[str, ...]
    definition_text: str
    definition_format: str = "text"
    media_references: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class ImportedDictionary:
    format: str
    display_name: str
    entries: tuple[DictionaryEntry, ...]


def normalize_lookup(value: str) -> str:
    if not isinstance(value, str):
        raise DictionaryFormatError("invalid_dictionary_text")
    value = unicodedata.normalize("NFC", value)
    value = " ".join(value.split())
    if not value:
        raise DictionaryFormatError("invalid_dictionary_text")
    return value.casefold()


def _canonical_mdict_resource_path(value: str, *, allow_relative: bool = False) -> str | None:
    """Return the safe, case-insensitive MDD key for a local resource."""
    if not isinstance(value, str):
        return None
    value = unquote(value).strip()
    if value.casefold().startswith("file://"):
        value = value[7:]
    elif not allow_relative:
        return None
    elif "://" in value or value.startswith(("/", "#")):
        return None
    value = value.replace("\\", "/").lstrip("/")
    value = posixpath.normpath(value)
    if not value or value in {".", ".."} or value.startswith("../") or "\x00" in value:
        return None
    return value.casefold()


class _MdictMediaExtractor(html.parser.HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.references: list[tuple[str, str]] = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        kind = {"img": "image", "audio": "audio"}.get(tag.casefold())
        source = attributes.get("src")
        if tag.casefold() == "link" and "stylesheet" in attributes.get("rel", "").casefold().split():
            kind = "stylesheet"
            source = attributes.get("href")
            path = _canonical_mdict_resource_path(source, allow_relative=True)
        else:
            path = _canonical_mdict_resource_path(source)
        if not kind:
            return
        if path and (kind, path) not in self.references:
            self.references.append((kind, path))


def mdict_media_references(value: str) -> tuple[tuple[str, str], ...]:
    parser = _MdictMediaExtractor()
    try:
        parser.feed(value)
        parser.close()
    except (html.parser.HTMLParseError, ValueError):
        raise DictionaryFormatError("invalid_dictionary_definition")
    return tuple(parser.references)


_STARDICT_TEXT_TYPES = frozenset("mlgtxyknrwh")
_STARDICT_BINARY_TYPES = frozenset("WPX")
_STARDICT_TYPES = _STARDICT_TEXT_TYPES | _STARDICT_BINARY_TYPES


def _parse_ifo(path: Path) -> dict[str, str]:
    try:
        raw = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError):
        raise DictionaryFormatError("invalid_stardict")
    values = {}
    for line in raw.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    if values.get("StarDict's dict ifo file") is not None:
        # Some writers use the marker as a key; it is still a valid file.
        pass
    sequence = values.get("sametypesequence", "")
    if not values.get("bookname") or any(type_code not in _STARDICT_TYPES for type_code in sequence):
        raise DictionaryFormatError("invalid_stardict")
    return values


def _stardict_data_path(base: Path) -> Path:
    raw = base.with_suffix(".dict")
    compressed = base.with_suffix(".dict.dz")
    if raw.is_file():
        return raw
    if compressed.is_file():
        return compressed
    raise DictionaryFormatError("stardict_data_missing")


def _read_stardict_data(path: Path) -> bytes:
    try:
        return gzip.open(path, "rb").read() if path.suffix == ".dz" else path.read_bytes()
    except (OSError, EOFError):
        raise DictionaryFormatError("invalid_stardict")


def _split_stardict_record(record: bytes, sequence: str) -> tuple[bytes, ...]:
    """Split a StarDict article using its published same-type sequence rules."""
    parts = []
    cursor = 0
    for index, type_code in enumerate(sequence):
        if index == len(sequence) - 1:
            parts.append(record[cursor:])
            break
        if type_code.islower():
            terminator = record.find(b"\0", cursor)
            if terminator < cursor:
                raise DictionaryFormatError("invalid_stardict")
            parts.append(record[cursor:terminator])
            cursor = terminator + 1
        else:
            if cursor + 4 > len(record):
                raise DictionaryFormatError("invalid_stardict")
            length = struct.unpack(">I", record[cursor:cursor + 4])[0]
            cursor += 4
            if cursor + length > len(record):
                raise DictionaryFormatError("invalid_stardict")
            parts.append(record[cursor:cursor + length])
            cursor += length
    return tuple(parts)


def _split_tagged_stardict_record(record: bytes) -> tuple[tuple[str, bytes], ...]:
    """Read a record without ``sametypesequence`` from its type markers."""
    parts: list[tuple[str, bytes]] = []
    cursor = 0
    while cursor < len(record):
        try:
            type_code = chr(record[cursor])
        except (TypeError, ValueError):  # pragma: no cover - bytes guard
            raise DictionaryFormatError("invalid_stardict")
        cursor += 1
        if type_code not in _STARDICT_TYPES:
            raise DictionaryFormatError("invalid_stardict")
        if type_code in _STARDICT_TEXT_TYPES:
            terminator = record.find(b"\0", cursor)
            if terminator < cursor:
                raise DictionaryFormatError("invalid_stardict")
            parts.append((type_code, record[cursor:terminator]))
            cursor = terminator + 1
        else:
            if cursor + 4 > len(record):
                raise DictionaryFormatError("invalid_stardict")
            length = struct.unpack(">I", record[cursor:cursor + 4])[0]
            cursor += 4
            if cursor + length > len(record):
                raise DictionaryFormatError("invalid_stardict")
            parts.append((type_code, record[cursor:cursor + length]))
            cursor += length
    if not parts:
        raise DictionaryFormatError("invalid_stardict")
    return tuple(parts)


def _decode_stardict_text(value: bytes) -> str:
    """Preserve legacy locale text when a StarDict file does not use UTF-8."""
    for encoding in ("utf-8", "gb18030", "latin-1"):
        try:
            return value.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise DictionaryFormatError("invalid_stardict")  # pragma: no cover - latin-1 always decodes


def _serialize_stardict_parts(parts: tuple[tuple[str, bytes], ...]) -> str:
    """Store typed fields without flattening StarDict's original structure."""
    serialized = []
    for type_code, value in parts:
        if type_code in _STARDICT_TEXT_TYPES:
            serialized.append({"type": type_code, "text": _decode_stardict_text(value)})
        else:
            serialized.append({"type": type_code, "data": base64.b64encode(value).decode("ascii")})
    return json.dumps(serialized, ensure_ascii=False, separators=(",", ":"))


def _stardict_definition(parts: tuple[tuple[str, bytes], ...]) -> tuple[str, str]:
    """Keep simple text/HTML compatible and retain every other field as typed data."""
    if len(parts) == 1 and parts[0][0] in {"m", "l", "h"}:
        type_code, value = parts[0]
        return _decode_stardict_text(value), "stardict:" + type_code
    return _serialize_stardict_parts(parts), "stardict:parts"


def parse_stardict(ifo_path: Path) -> ImportedDictionary:
    if ifo_path.suffix.casefold() != ".ifo":
        raise DictionaryFormatError("invalid_stardict")
    values = _parse_ifo(ifo_path)
    base = ifo_path.with_suffix("")
    try:
        index = base.with_suffix(".idx").read_bytes()
        data = _read_stardict_data(_stardict_data_path(base))
    except OSError:
        raise DictionaryFormatError("stardict_index_missing")
    sequence = values.get("sametypesequence", "")
    entries: list[DictionaryEntry] = []
    offset = 0
    cursor = 0
    while cursor < len(index):
        terminator = index.find(b"\x00", cursor)
        if terminator < cursor or terminator + 9 > len(index):
            raise DictionaryFormatError("invalid_stardict")
        try:
            headword = index[cursor:terminator].decode("utf-8")
        except UnicodeDecodeError:
            raise DictionaryFormatError("invalid_stardict")
        record_offset, record_length = struct.unpack(">II", index[terminator + 1:terminator + 9])
        cursor = terminator + 9
        if record_offset + record_length > len(data):
            raise DictionaryFormatError("invalid_stardict")
        try:
            record = data[record_offset:record_offset + record_length]
            parts = (
                tuple(zip(sequence, _split_stardict_record(record, sequence)))
                if sequence else _split_tagged_stardict_record(record)
            )
            definition, definition_format = _stardict_definition(parts)
            normalized = normalize_lookup(headword)
            entries.append(DictionaryEntry(
                headword.strip(), normalized, (), definition,
                definition_format,
            ))
        except (UnicodeDecodeError, DictionaryFormatError):
            raise DictionaryFormatError("invalid_stardict")
    aliases_by_index: dict[int, list[str]] = {}
    synonym_path = base.with_suffix(".syn")
    if synonym_path.is_file():
        try:
            synonym_data = synonym_path.read_bytes()
        except OSError:
            raise DictionaryFormatError("invalid_stardict")
        cursor = 0
        while cursor < len(synonym_data):
            terminator = synonym_data.find(b"\x00", cursor)
            if terminator < cursor or terminator + 5 > len(synonym_data):
                raise DictionaryFormatError("invalid_stardict")
            try:
                alias = synonym_data[cursor:terminator].decode("utf-8")
                entry_index = struct.unpack(">I", synonym_data[terminator + 1:terminator + 5])[0]
                aliases_by_index.setdefault(entry_index, []).append(normalize_lookup(alias))
            except UnicodeDecodeError:
                raise DictionaryFormatError("invalid_stardict")
            cursor = terminator + 5
    finalized = []
    for index, entry in enumerate(entries):
        aliases = tuple(alias for alias in aliases_by_index.get(index, ()) if alias != entry.normalized_headword)
        finalized.append(DictionaryEntry(
            entry.headword, entry.normalized_headword, aliases,
            entry.definition_text, entry.definition_format,
        ))
    if not finalized:
        raise DictionaryFormatError("dictionary_has_no_entries")
    return ImportedDictionary("stardict", values["bookname"], tuple(finalized))


def _mdict_reader_runtime():
    """Load mdict-utils and activate its bundled MIT LZO implementation."""
    try:
        from mdict_utils.base import lzo as bundled_lzo
        from mdict_utils.base import readmdict
    except ImportError as error:  # pragma: no cover - packaging failure guard
        raise DictionaryFormatError("mdict_reader_unavailable") from error

    # mdict-utils ships a MIT-licensed pure-Python LZO decoder, but its reader
    # only uses it when a separately installed ``lzo`` module is present.  MDX
    # 1.x files commonly use LZO, so adapt the bundled decoder to the reader's
    # tiny ``lzo.decompress(header + payload)`` interface.  This avoids adding
    # the GPL-licensed python-lzo dependency to this MIT project.
    if readmdict.lzo is None:
        class _BundledLzoAdapter:
            @staticmethod
            def decompress(payload: bytes) -> bytes:
                if len(payload) < 5 or payload[0] != 0xF0:
                    raise ValueError("invalid_lzo_payload")
                decompressed_size = struct.unpack(">I", payload[1:5])[0]
                return bundled_lzo.decompress(
                    payload[5:], initSize=decompressed_size, blockSize=decompressed_size,
                )

        readmdict.lzo = _BundledLzoAdapter

    return readmdict


def _decode_mdict_text(value: bytes, declared_encoding: str) -> str:
    # Some older dictionaries declare GBK/GB18030 but store entries in UTF-8.
    # Prefer UTF-8 because it is unambiguous for these files, then honor the
    # declared encoding for genuine legacy dictionaries.
    encodings = ("utf-8", declared_encoding, "gb18030")
    for encoding in dict.fromkeys(item for item in encodings if item):
        try:
            return value.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise UnicodeDecodeError("mdict", value, 0, len(value), "unsupported entry encoding")


def parse_mdict(mdx_path: Path) -> ImportedDictionary:
    """Read unencrypted MDX through the MIT-licensed mdict-utils package."""
    if mdx_path.suffix.casefold() != ".mdx":
        raise DictionaryFormatError("invalid_mdict")
    readmdict = _mdict_reader_runtime()

    try:
        # MDict's StyleSheet is part of its article format. Let mdict-utils
        # expand the inline style markers before storing the source unchanged.
        reader = readmdict.MDX(str(mdx_path), "", True, None)
        header = reader.header
        name = header.get(b"Title", header.get(b"title", mdx_path.stem.encode("utf-8")))
        display_name = _decode_mdict_text(name, reader._encoding).strip() or mdx_path.stem
        entries = []
        for key, value in reader.items():
            headword = _decode_mdict_text(key, reader._encoding)
            definition = _decode_mdict_text(value, reader._encoding)
            media_references = mdict_media_references(definition)
            entries.append(DictionaryEntry(
                headword.strip(), normalize_lookup(headword), (),
                definition, "mdict", media_references,
            ))
    except DictionaryFormatError:
        raise
    except (OSError, UnicodeDecodeError, ValueError, AssertionError, EOFError) as error:
        raise DictionaryFormatError("invalid_mdict") from error
    if not entries:
        raise DictionaryFormatError("dictionary_has_no_entries")
    return ImportedDictionary("mdict", display_name, tuple(entries))


def read_mdict_resources(mdd_path: Path, references: set[str]) -> dict[str, bytes]:
    """Read only MDD resources referenced by dictionary entries."""
    if mdd_path.suffix.casefold() != ".mdd":
        raise DictionaryFormatError("invalid_mdict_resource")
    if not references:
        return {}
    readmdict = _mdict_reader_runtime()
    found: dict[str, bytes] = {}
    try:
        reader = readmdict.MDD(str(mdd_path), None)
        for key, value in reader.items():
            path = _canonical_mdict_resource_path("file://" + _decode_mdict_text(key, reader._encoding))
            if path not in references or path in found:
                continue
            if not isinstance(value, bytes):
                raise DictionaryFormatError("invalid_mdict_resource")
            found[path] = value
    except DictionaryFormatError:
        raise
    except (OSError, UnicodeDecodeError, ValueError, AssertionError, EOFError) as error:
        raise DictionaryFormatError("invalid_mdict_resource") from error
    if not found:
        raise DictionaryFormatError("mdict_resources_not_found")
    return found


def parse_local_dictionary(path: Path) -> ImportedDictionary:
    path = Path(path)
    suffix = path.suffix.casefold()
    if suffix == ".ifo":
        return parse_stardict(path)
    if suffix == ".mdx":
        return parse_mdict(path)
    raise DictionaryFormatError("unsupported_dictionary_format")
