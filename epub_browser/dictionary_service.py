"""Local dictionary installation and read-only lookup service."""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import tarfile
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path

from .dictionary_formats import (
    DictionaryFormatError, ImportedDictionary, normalize_lookup, parse_local_dictionary,
    read_mdict_resources,
)
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
        self._discard_legacy_dictionary_cache()
        self.store.ensure_global_dictionary_default()

    def _discard_legacy_dictionary_cache(self) -> None:
        """Remove imports created before definitions were retained verbatim."""
        for record in self.store.list_dictionaries():
            path = self.dictionary_directory / (record.id + ".sqlite")
            try:
                with sqlite3.connect(path) as connection:
                    row = connection.execute(
                        "SELECT value FROM meta WHERE key = 'definition_rendering_revision'"
                    ).fetchone()
            except sqlite3.Error:
                row = None
            if row and row[0] == "3":
                continue
            self.store.delete_dictionary(record.id)
            path.unlink(missing_ok=True)

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
    def _create_file(path: Path, dictionary: ImportedDictionary, digest: str) -> None:
        temporary = path.with_suffix(".sqlite.tmp")
        try:
            with sqlite3.connect(temporary) as connection:
                connection.execute("PRAGMA journal_mode = OFF")
                connection.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
                connection.execute(
                    "CREATE TABLE entries (id INTEGER PRIMARY KEY, headword TEXT NOT NULL, normalized_headword TEXT NOT NULL, definition_text TEXT NOT NULL, definition_format TEXT NOT NULL, media_json TEXT NOT NULL DEFAULT '[]')"
                )
                connection.execute(
                    "CREATE TABLE forms (normalized_form TEXT NOT NULL, entry_id INTEGER NOT NULL REFERENCES entries(id) ON DELETE CASCADE, PRIMARY KEY(normalized_form, entry_id))"
                )
                connection.execute("CREATE INDEX idx_dictionary_entries ON entries(normalized_headword, id)")
                connection.execute("CREATE INDEX idx_dictionary_forms ON forms(normalized_form, entry_id)")
                connection.execute(
                    "CREATE TABLE resources (id TEXT PRIMARY KEY, content_type TEXT NOT NULL, content BLOB NOT NULL)"
                )
                connection.executemany(
                    "INSERT INTO meta(key, value) VALUES (?, ?)",
                    (("format", dictionary.format), ("content_sha256", digest), ("definition_rendering_revision", "3")),
                )
                for entry in dictionary.entries:
                    cursor = connection.execute(
                        "INSERT INTO entries(headword, normalized_headword, definition_text, definition_format, media_json) VALUES (?, ?, ?, ?, ?)",
                        (
                            entry.headword, entry.normalized_headword, entry.definition_text,
                            entry.definition_format,
                            json.dumps([
                                {"kind": kind, "reference": reference}
                                for kind, reference in entry.media_references
                            ], separators=(",", ":")),
                        ),
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
        self._create_file(target, parsed, digest)
        try:
            record = self.store.create_dictionary(
                dictionary_id=dictionary_id,
                display_name=display_name or parsed.display_name,
                # These fields are retained only to read databases created by
                # earlier versions. Dictionary availability is not language-bound.
                source_language="und",
                target_language="und",
                entry_count=len(parsed.entries),
                content_sha256=digest,
                attribution=attribution,
                created_by_user_id=created_by_user_id,
            )
            self.store.ensure_global_dictionary_default()
            return record
        except Exception:
            target.unlink(missing_ok=True)
            raise

    def install_archive(
        self,
        archive_bytes: bytes,
        *,
        created_by_user_id: str,
        display_name: str | None = None,
        attribution: str = "",
    ) -> DictionaryRecord:
        """Install one dictionary from a bounded zip without trusting its paths."""
        return self.install_upload(
            archive_bytes, "dictionary.zip", created_by_user_id=created_by_user_id,
            display_name=display_name, attribution=attribution,
            _use_upload_name_as_default=False,
        )

    def install_upload(
        self,
        upload_bytes: bytes,
        filename: str,
        *,
        created_by_user_id: str,
        display_name: str | None = None,
        attribution: str = "",
        _use_upload_name_as_default: bool = True,
    ) -> DictionaryRecord:
        """Install a dictionary received by an in-memory caller, such as a test."""
        if not isinstance(upload_bytes, bytes) or not upload_bytes:
            raise DictionaryServiceError("invalid_dictionary_archive")
        upload = self.dictionary_directory / (".upload-" + str(uuid.uuid4()))
        try:
            upload.write_bytes(upload_bytes)
            return self.install_upload_file(
                upload, filename, created_by_user_id=created_by_user_id,
                display_name=display_name, attribution=attribution,
                _use_upload_name_as_default=_use_upload_name_as_default,
            )
        finally:
            upload.unlink(missing_ok=True)

    def install_upload_file(
        self,
        upload_path: Path,
        filename: str,
        *,
        created_by_user_id: str,
        display_name: str | None = None,
        attribution: str = "",
        _use_upload_name_as_default: bool = True,
    ) -> DictionaryRecord:
        """Install a direct MDX or a StarDict archive already streamed to disk."""
        upload_path = Path(upload_path)
        if not upload_path.is_file() or upload_path.stat().st_size <= 0:
            raise DictionaryServiceError("invalid_dictionary_archive")
        upload_name = Path(filename).name if isinstance(filename, str) else ""
        upload_name_folded = upload_name.casefold()
        upload_suffix = next((suffix for suffix in (
            ".tar.bz2", ".tar.gz", ".tbz2", ".tgz", ".mdx", ".zip",
        ) if upload_name_folded.endswith(suffix)), "")
        if not upload_suffix:
            raise DictionaryServiceError("unsupported_dictionary_format")
        is_mdx = upload_suffix == ".mdx"
        is_zip = upload_suffix == ".zip"
        staging = self.dictionary_directory / (".import-" + str(uuid.uuid4()))
        staging.mkdir(mode=0o700)
        try:
            if is_mdx:
                source = staging / "dictionary.mdx"
                shutil.copyfile(upload_path, source)
            elif is_zip:
                try:
                    archive = zipfile.ZipFile(upload_path)
                except zipfile.BadZipFile as error:
                    raise DictionaryServiceError("invalid_dictionary_archive") from error
                with archive:
                    members = [member for member in archive.infolist() if not member.is_dir()]
                    if not members:
                        raise DictionaryServiceError("invalid_dictionary_archive")
                    for member in members:
                        relative = Path(member.filename)
                        if relative.is_absolute() or ".." in relative.parts or member.filename.replace("\\", "/").startswith("/"):
                            raise DictionaryServiceError("invalid_dictionary_archive")
                        if (member.external_attr >> 16) & 0o170000 == 0o120000:
                            raise DictionaryServiceError("invalid_dictionary_archive")
                        target = staging / relative.name
                        with archive.open(member) as source_stream, target.open("xb") as output:
                            shutil.copyfileobj(source_stream, output, 1024 * 1024)
            else:
                try:
                    archive = tarfile.open(upload_path, mode="r:*")
                except (tarfile.TarError, OSError, EOFError) as error:
                    raise DictionaryServiceError("invalid_dictionary_archive") from error
                with archive:
                    members = [member for member in archive.getmembers() if member.isfile()]
                    if not members:
                        raise DictionaryServiceError("invalid_dictionary_archive")
                    for member in members:
                        relative = Path(member.name)
                        if relative.is_absolute() or ".." in relative.parts or member.name.replace("\\", "/").startswith("/"):
                            raise DictionaryServiceError("invalid_dictionary_archive")
                        source_stream = archive.extractfile(member)
                        if source_stream is None:
                            raise DictionaryServiceError("invalid_dictionary_archive")
                        target = staging / relative.name
                        with source_stream, target.open("xb") as output:
                            shutil.copyfileobj(source_stream, output, 1024 * 1024)
            if not is_mdx:
                candidates = [item for item in staging.iterdir() if item.suffix.casefold() in {".ifo", ".mdx"}]
                if len(candidates) != 1:
                    raise DictionaryServiceError("invalid_dictionary_archive")
                source = candidates[0]
            requested_name = display_name.strip() if isinstance(display_name, str) else ""
            fallback_name = upload_name[:-len(upload_suffix)] if _use_upload_name_as_default and upload_name else None
            return self.install(source, created_by_user_id=created_by_user_id,
                                display_name=requested_name or fallback_name,
                                attribution=attribution)
        finally:
            shutil.rmtree(staging, ignore_errors=True)

    @staticmethod
    def _media_content_type(kind: str, content: bytes) -> str | None:
        if kind == "image":
            if content.startswith(b"\x89PNG\r\n\x1a\n"):
                return "image/png"
            if content.startswith(b"\xff\xd8\xff"):
                return "image/jpeg"
            if content.startswith((b"GIF87a", b"GIF89a")):
                return "image/gif"
            if len(content) >= 12 and content.startswith(b"RIFF") and content[8:12] == b"WEBP":
                return "image/webp"
        if kind == "audio":
            if content.startswith(b"ID3") or content.startswith((b"\xff\xfb", b"\xff\xf3", b"\xff\xf2")):
                return "audio/mpeg"
            if len(content) >= 12 and content.startswith(b"RIFF") and content[8:12] == b"WAVE":
                return "audio/wav"
            if content.startswith(b"OggS"):
                return "audio/ogg"
        if kind == "stylesheet":
            try:
                content.decode("utf-8")
            except UnicodeDecodeError:
                return None
            return "text/css; charset=utf-8"
        return None

    def attach_mdict_resources(self, dictionary_id: str, upload_bytes: bytes, filename: str) -> None:
        """Attach MDD media received by an in-memory caller, such as a test."""
        if not isinstance(upload_bytes, bytes) or not upload_bytes:
            raise DictionaryServiceError("invalid_mdict_resource")
        upload = self.dictionary_directory / (".resource-upload-" + str(uuid.uuid4()) + ".mdd")
        try:
            upload.write_bytes(upload_bytes)
            self.attach_mdict_resources_file(dictionary_id, upload, filename)
        finally:
            upload.unlink(missing_ok=True)

    def attach_mdict_resources_file(self, dictionary_id: str, upload_path: Path, filename: str) -> None:
        """Attach supported MDD media that has already been streamed to disk."""
        upload_path = Path(upload_path)
        if not upload_path.is_file() or upload_path.stat().st_size <= 0:
            raise DictionaryServiceError("invalid_mdict_resource")
        if Path(filename).suffix.casefold() != ".mdd":
            raise DictionaryServiceError("invalid_mdict_resource")
        dictionary = self.store.get_dictionary(dictionary_id)
        if dictionary is None:
            raise DictionaryServiceError("dictionary_unavailable")
        path = self.dictionary_directory / (dictionary.id + ".sqlite")
        if not path.is_file():
            raise DictionaryServiceError("dictionary_unavailable")
        try:
            with sqlite3.connect(path) as connection:
                format_row = connection.execute("SELECT value FROM meta WHERE key = 'format'").fetchone()
                if format_row is None or format_row[0] != "mdict":
                    raise DictionaryServiceError("invalid_mdict_resource")
                rows = connection.execute("SELECT id, media_json FROM entries WHERE media_json != '[]'").fetchall()
                entry_media = {
                    row[0]: json.loads(row[1]) for row in rows
                }
        except (sqlite3.Error, json.JSONDecodeError) as error:
            raise DictionaryServiceError("dictionary_unavailable") from error
        references = {
            item["reference"] for media in entry_media.values() for item in media
            if isinstance(item, dict) and isinstance(item.get("reference"), str)
        }
        if not references:
            raise DictionaryServiceError("mdict_resources_not_found")
        try:
            resources = read_mdict_resources(upload_path, references)
        except DictionaryFormatError as error:
            raise DictionaryServiceError(error.code) from error

        replacements: dict[str, tuple[str, str]] = {}
        for entry in entry_media.values():
            for item in entry:
                if not isinstance(item, dict):
                    continue
                reference, kind = item.get("reference"), item.get("kind")
                content = resources.get(reference)
                content_type = self._media_content_type(kind, content) if isinstance(kind, str) and content else None
                if not content_type:
                    continue
                resource_id = hashlib.sha256(content).hexdigest()
                replacements[reference] = (resource_id, content_type)
        if not replacements:
            raise DictionaryServiceError("unsupported_mdict_resource")
        try:
            with sqlite3.connect(path) as connection:
                for reference, (resource_id, content_type) in replacements.items():
                    connection.execute(
                        "INSERT OR IGNORE INTO resources(id, content_type, content) VALUES (?, ?, ?)",
                        (resource_id, content_type, resources[reference]),
                    )
                for entry_id, media in entry_media.items():
                    attached = [
                        {
                            "kind": item["kind"], "reference": item["reference"],
                            "id": replacements[item["reference"]][0],
                        }
                        for item in media
                        if isinstance(item, dict) and item.get("reference") in replacements
                    ]
                    connection.execute(
                        "UPDATE entries SET media_json = ? WHERE id = ?",
                        (json.dumps(attached, separators=(",", ":")), entry_id),
                    )
        except sqlite3.Error as error:
            raise DictionaryServiceError("dictionary_unavailable") from error

    def get_media(self, dictionary_id: str, media_id: str) -> dict:
        if not isinstance(media_id, str) or len(media_id) != 64 or any(char not in "0123456789abcdef" for char in media_id):
            raise DictionaryServiceError("dictionary_media_unavailable")
        dictionary = self.store.get_dictionary(dictionary_id)
        path = self.dictionary_directory / (dictionary_id + ".sqlite") if dictionary else None
        if dictionary is None or not dictionary.enabled or not path.is_file():
            raise DictionaryServiceError("dictionary_media_unavailable")
        try:
            with sqlite3.connect("file:" + path.as_posix() + "?mode=ro", uri=True) as connection:
                row = connection.execute(
                    "SELECT content_type, content FROM resources WHERE id = ?", (media_id,)
                ).fetchone()
        except sqlite3.Error as error:
            raise DictionaryServiceError("dictionary_media_unavailable") from error
        if row is None:
            raise DictionaryServiceError("dictionary_media_unavailable")
        return {"content_type": row[0], "content": bytes(row[1])}

    def list_available(self) -> tuple[DictionaryRecord, ...]:
        return self.store.list_enabled_dictionaries()

    def lookup(self, dictionary_id: str, text: str) -> DictionaryLookup:
        try:
            query = normalize_lookup(text)
        except DictionaryFormatError as error:
            raise DictionaryServiceError("invalid_dictionary_query") from error
        if not isinstance(dictionary_id, str) or not dictionary_id:
            raise DictionaryServiceError("invalid_dictionary_selection")
        dictionary = self.store.get_dictionary(dictionary_id)
        if dictionary is None or not dictionary.enabled:
            raise DictionaryServiceError("dictionary_unavailable")
        path = self.dictionary_directory / (dictionary.id + ".sqlite")
        if not path.is_file():
            raise DictionaryServiceError("dictionary_unavailable")
        try:
            connection = sqlite3.connect("file:" + path.as_posix() + "?mode=ro", uri=True)
            connection.row_factory = sqlite3.Row
            try:
                columns = {
                    row[1] for row in connection.execute("PRAGMA table_info(entries)").fetchall()
                }
                media_column = "entries.media_json" if "media_json" in columns else "'[]' AS media_json"
                format_column = "entries.definition_format" if "definition_format" in columns else "'text' AS definition_format"
                rows = connection.execute(
                    """SELECT entries.headword, entries.definition_text, %s, %s FROM forms
                    JOIN entries ON entries.id = forms.entry_id
                    WHERE forms.normalized_form = ? ORDER BY entries.id LIMIT 3
                    """ % (format_column, media_column), (query,)
                ).fetchall()
            finally:
                connection.close()
        except sqlite3.Error as error:
            raise DictionaryServiceError("dictionary_unavailable") from error
        entries = tuple({
            "headword": row["headword"], "definition": row["definition_text"],
            "definition_format": row["definition_format"],
            "media": [item for item in json.loads(row["media_json"])
                      if isinstance(item, dict) and item.get("id") and item.get("reference")],
        } for row in rows)
        return DictionaryLookup(bool(entries), dictionary, query, entries)

    def set_enabled(self, dictionary_id: str, enabled: bool) -> DictionaryRecord:
        record = self.store.set_dictionary_enabled(dictionary_id, enabled)
        if not enabled:
            self.store.ensure_global_dictionary_default()
        return record

    def rename(self, dictionary_id: str, display_name: str) -> DictionaryRecord:
        return self.store.rename_dictionary(dictionary_id, display_name)

    def delete(self, dictionary_id: str) -> None:
        self.store.delete_dictionary(dictionary_id)
        (self.dictionary_directory / (dictionary_id + ".sqlite")).unlink(missing_ok=True)
        self.store.ensure_global_dictionary_default()
