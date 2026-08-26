"""Local dictionary installation and read-only lookup service."""

from __future__ import annotations

import hashlib
import io
import shutil
import sqlite3
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path

from .dictionary_formats import DictionaryFormatError, ImportedDictionary, normalize_lookup, parse_local_dictionary
from .state import DictionaryRecord, StateStore


class DictionaryServiceError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class DictionaryLookup:
    found: bool
    dictionary: DictionaryRecord | None
    query: str
    entries: tuple[dict, ...]


class DictionaryService:
    """Keep local dictionary records outside the EPUB cache and main database."""

    def __init__(self, store: StateStore, server_directory):
        self.store = store
        self.server_directory = Path(server_directory)
        self.dictionary_directory = self.server_directory / "data" / "dictionaries"
        self.dictionary_directory.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _source_digest(source: Path) -> str:
        digest = hashlib.sha256()
        base = source.with_suffix("")
        sources = [source]
        if source.suffix.casefold() == ".ifo":
            sources = [
                candidate for candidate in (
                    base.with_suffix(".ifo"), base.with_suffix(".idx"),
                    base.with_suffix(".dict"), base.with_suffix(".dict.dz"),
                    base.with_suffix(".syn"),
                ) if candidate.is_file()
            ]
        for item in sorted(sources):
            digest.update(item.name.encode("utf-8"))
            with item.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _create_file(path: Path, dictionary: ImportedDictionary, source_language: str, target_language: str, digest: str) -> None:
        temporary = path.with_suffix(".sqlite.tmp")
        try:
            with sqlite3.connect(temporary) as connection:
                connection.execute("PRAGMA journal_mode = OFF")
                connection.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
                connection.execute(
                    "CREATE TABLE entries (id INTEGER PRIMARY KEY, headword TEXT NOT NULL, normalized_headword TEXT NOT NULL, definition_text TEXT NOT NULL)"
                )
                connection.execute(
                    "CREATE TABLE forms (normalized_form TEXT NOT NULL, entry_id INTEGER NOT NULL REFERENCES entries(id) ON DELETE CASCADE, PRIMARY KEY(normalized_form, entry_id))"
                )
                connection.execute("CREATE INDEX idx_dictionary_entries ON entries(normalized_headword, id)")
                connection.execute("CREATE INDEX idx_dictionary_forms ON forms(normalized_form, entry_id)")
                connection.executemany(
                    "INSERT INTO meta(key, value) VALUES (?, ?)",
                    (("format", dictionary.format), ("source_language", source_language),
                     ("target_language", target_language), ("content_sha256", digest)),
                )
                for entry in dictionary.entries:
                    cursor = connection.execute(
                        "INSERT INTO entries(headword, normalized_headword, definition_text) VALUES (?, ?, ?)",
                        (entry.headword, entry.normalized_headword, entry.definition_text),
                    )
                    connection.executemany(
                        "INSERT OR IGNORE INTO forms(normalized_form, entry_id) VALUES (?, ?)",
                        ((entry.normalized_headword, cursor.lastrowid),) + tuple((alias, cursor.lastrowid) for alias in entry.aliases),
                    )
                integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
                if integrity != "ok":
                    raise DictionaryServiceError("dictionary_integrity_failed")
            temporary.replace(path)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise

    def install(
        self,
        source: Path,
        *,
        source_language: str,
        target_language: str,
        created_by_user_id: str,
        display_name: str | None = None,
        attribution: str = "",
    ) -> DictionaryRecord:
        try:
            parsed = parse_local_dictionary(Path(source))
            digest = self._source_digest(Path(source))
        except DictionaryFormatError as error:
            raise DictionaryServiceError(error.code) from error
        dictionary_id = str(uuid.uuid4())
        target = self.dictionary_directory / (dictionary_id + ".sqlite")
        self._create_file(target, parsed, source_language, target_language, digest)
        try:
            return self.store.create_dictionary(
                dictionary_id=dictionary_id,
                display_name=display_name or parsed.display_name,
                source_language=source_language,
                target_language=target_language,
                entry_count=len(parsed.entries),
                content_sha256=digest,
                attribution=attribution,
                created_by_user_id=created_by_user_id,
            )
        except Exception:
            target.unlink(missing_ok=True)
            raise

    def install_archive(
        self,
        archive_bytes: bytes,
        *,
        source_language: str,
        target_language: str,
        created_by_user_id: str,
        display_name: str | None = None,
        attribution: str = "",
    ) -> DictionaryRecord:
        """Install one dictionary from a bounded zip without trusting its paths."""
        if not isinstance(archive_bytes, bytes) or not archive_bytes or len(archive_bytes) > 512 * 1024 * 1024:
            raise DictionaryServiceError("invalid_dictionary_archive")
        staging = self.dictionary_directory / (".import-" + str(uuid.uuid4()))
        staging.mkdir(mode=0o700)
        try:
            try:
                archive = zipfile.ZipFile(io.BytesIO(archive_bytes))
            except zipfile.BadZipFile as error:
                raise DictionaryServiceError("invalid_dictionary_archive") from error
            with archive:
                members = [member for member in archive.infolist() if not member.is_dir()]
                if not members or len(members) > 16 or sum(member.file_size for member in members) > 1024 * 1024 * 1024:
                    raise DictionaryServiceError("invalid_dictionary_archive")
                for member in members:
                    relative = Path(member.filename)
                    if relative.is_absolute() or ".." in relative.parts or member.filename.replace("\\", "/").startswith("/"):
                        raise DictionaryServiceError("invalid_dictionary_archive")
                    if (member.external_attr >> 16) & 0o170000 == 0o120000:
                        raise DictionaryServiceError("invalid_dictionary_archive")
                    target = staging / relative.name
                    with archive.open(member) as source, target.open("xb") as output:
                        shutil.copyfileobj(source, output, 1024 * 1024)
            candidates = [item for item in staging.iterdir() if item.suffix.casefold() in {".ifo", ".mdx"}]
            if len(candidates) != 1:
                raise DictionaryServiceError("invalid_dictionary_archive")
            return self.install(
                candidates[0], source_language=source_language,
                target_language=target_language, created_by_user_id=created_by_user_id,
                display_name=display_name, attribution=attribution,
            )
        finally:
            shutil.rmtree(staging, ignore_errors=True)

    def lookup(self, source_language: str, text: str) -> DictionaryLookup:
        try:
            query = normalize_lookup(text)
        except DictionaryFormatError as error:
            raise DictionaryServiceError("invalid_dictionary_query") from error
        dictionary = self.store.get_dictionary_default(source_language)
        if dictionary is None:
            raise DictionaryServiceError("dictionary_not_configured")
        path = self.dictionary_directory / (dictionary.id + ".sqlite")
        if not path.is_file():
            raise DictionaryServiceError("dictionary_unavailable")
        try:
            connection = sqlite3.connect("file:" + path.as_posix() + "?mode=ro", uri=True)
            connection.row_factory = sqlite3.Row
            try:
                rows = connection.execute(
                    """
                    SELECT entries.headword, entries.definition_text FROM forms
                    JOIN entries ON entries.id = forms.entry_id
                    WHERE forms.normalized_form = ? ORDER BY entries.id LIMIT 3
                    """, (query,)
                ).fetchall()
            finally:
                connection.close()
        except sqlite3.Error as error:
            raise DictionaryServiceError("dictionary_unavailable") from error
        entries = tuple({"headword": row["headword"], "definition": row["definition_text"]} for row in rows)
        return DictionaryLookup(bool(entries), dictionary, query, entries)

    def set_default(self, source_language: str, dictionary_id: str, user_id: str) -> DictionaryRecord:
        return self.store.set_dictionary_default(source_language, dictionary_id, user_id)

    def set_enabled(self, dictionary_id: str, enabled: bool) -> DictionaryRecord:
        return self.store.set_dictionary_enabled(dictionary_id, enabled)

    def delete(self, dictionary_id: str) -> None:
        self.store.delete_dictionary(dictionary_id)
        (self.dictionary_directory / (dictionary_id + ".sqlite")).unlink(missing_ok=True)
