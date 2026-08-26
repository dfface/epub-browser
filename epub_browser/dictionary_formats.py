"""Bounded readers for administrator-installed local dictionary packages.

Dictionary definition HTML is untrusted third-party input and is never
rendered by the reader application. Plain-text Markdown markers are retained
for the reader's small, safe inline renderer (for example, `` `1` `` senses).
"""

from __future__ import annotations

import gzip
import html.parser
import re
import struct
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


MAX_ENTRIES = 500_000
MAX_HEADWORD_LENGTH = 256
MAX_DEFINITION_BYTES = 16 * 1024


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
    if not value or len(value) > MAX_HEADWORD_LENGTH:
        raise DictionaryFormatError("invalid_dictionary_text")
    return value.casefold()


class _PlainTextExtractor(html.parser.HTMLParser):
    _BLOCK_TAGS = frozenset({"p", "div", "br", "li", "dt", "dd", "tr", "h1", "h2", "h3", "h4"})

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._ignored_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "iframe", "object"}:
            self._ignored_depth += 1
        elif self._ignored_depth == 0 and tag.casefold() in self._BLOCK_TAGS:
            self._parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style", "iframe", "object"} and self._ignored_depth:
            self._ignored_depth -= 1
        elif self._ignored_depth == 0 and tag.casefold() in self._BLOCK_TAGS:
            self._parts.append("\n")

    def handle_data(self, data):
        if self._ignored_depth == 0:
            self._parts.append(data)

    def text(self) -> str:
        return "\n".join(
            part.strip() for part in "".join(self._parts).splitlines() if part.strip()
        )


def clean_definition(value: str) -> str:
    if not isinstance(value, str):
        raise DictionaryFormatError("invalid_dictionary_definition")
    parser = _PlainTextExtractor()
    try:
        parser.feed(value)
        parser.close()
    except (html.parser.HTMLParseError, ValueError):
        raise DictionaryFormatError("invalid_dictionary_definition")
    text = unicodedata.normalize("NFC", parser.text())
    if not text:
        raise DictionaryFormatError("empty_dictionary_definition")
    if len(text.encode("utf-8")) > MAX_DEFINITION_BYTES:
        text = text.encode("utf-8")[:MAX_DEFINITION_BYTES].decode("utf-8", "ignore").rstrip()
    return text


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
    if not values.get("bookname") or values.get("sametypesequence", "m")[:1] not in {"m", "l", "g", "h", "x"}:
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
            definition = data[record_offset:record_offset + record_length].decode("utf-8")
            normalized = normalize_lookup(headword)
            entries.append(DictionaryEntry(headword.strip(), normalized, (), clean_definition(definition)))
        except UnicodeDecodeError:
            raise DictionaryFormatError("invalid_stardict")
        if len(entries) > MAX_ENTRIES:
            raise DictionaryFormatError("dictionary_too_large")
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
        finalized.append(DictionaryEntry(entry.headword, entry.normalized_headword, aliases, entry.definition_text))
    if not finalized:
        raise DictionaryFormatError("dictionary_has_no_entries")
    return ImportedDictionary("stardict", values["bookname"], tuple(finalized))


def parse_mdict(mdx_path: Path) -> ImportedDictionary:
    """Read unencrypted MDX through the MIT-licensed mdict-utils package."""
    if mdx_path.suffix.casefold() != ".mdx":
        raise DictionaryFormatError("invalid_mdict")
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

    def decode_mdict_text(value: bytes, declared_encoding: str) -> str:
        # Some older dictionaries declare GBK/GB18030 but store entries in
        # UTF-8.  Prefer UTF-8 because it is unambiguous for these files, then
        # honor the declared encoding for genuine legacy dictionaries.
        encodings = ("utf-8", declared_encoding, "gb18030")
        for encoding in dict.fromkeys(item for item in encodings if item):
            try:
                return value.decode(encoding)
            except UnicodeDecodeError:
                continue
        raise UnicodeDecodeError("mdict", value, 0, len(value), "unsupported entry encoding")

    try:
        reader = readmdict.MDX(str(mdx_path), "", False, None)
        header = reader.header
        name = header.get(b"Title", header.get(b"title", mdx_path.stem.encode("utf-8")))
        display_name = decode_mdict_text(name, reader._encoding).strip() or mdx_path.stem
        entries = []
        for key, value in reader.items():
            headword = decode_mdict_text(key, reader._encoding)
            definition = decode_mdict_text(value, reader._encoding)
            entries.append(DictionaryEntry(headword.strip(), normalize_lookup(headword), (), clean_definition(definition)))
            if len(entries) > MAX_ENTRIES:
                raise DictionaryFormatError("dictionary_too_large")
    except DictionaryFormatError:
        raise
    except (OSError, UnicodeDecodeError, ValueError, AssertionError, EOFError) as error:
        raise DictionaryFormatError("invalid_mdict") from error
    if not entries:
        raise DictionaryFormatError("dictionary_has_no_entries")
    return ImportedDictionary("mdict", display_name, tuple(entries))


def parse_local_dictionary(path: Path) -> ImportedDictionary:
    path = Path(path)
    suffix = path.suffix.casefold()
    if suffix == ".ifo":
        return parse_stardict(path)
    if suffix == ".mdx":
        return parse_mdict(path)
    raise DictionaryFormatError("unsupported_dictionary_format")
