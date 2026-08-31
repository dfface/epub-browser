"""Local dictionary installation and read-only lookup service."""

from __future__ import annotations

import hashlib
import json
import posixpath
import re
import shutil
import sqlite3
import tarfile
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote

from .dictionary_formats import (
    DictionaryFormatError, ImportedDictionary, normalize_lookup, parse_local_dictionary,
    read_mdict_resources,
)
from .state import DictionaryRecord, StateStore

class DictionaryServiceError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def migrate_legacy_dictionary_directory(public_dir, server_directory):
    """Move dictionary databases that earlier versions wrote inside the cache.

    Older Server builds passed the published directory (``<server-dir>/cache/
    public``) to ``DictionaryService``, so installed dictionaries landed under
    ``cache/public/data/dictionaries``.  Dictionary databases are runtime user
    data and belong under the server directory, outside the cache tree.
    """
    legacy = Path(public_dir) / "data" / "dictionaries"
    target = Path(server_directory) / "data" / "dictionaries"
    if not legacy.is_dir() or legacy.resolve() == target.resolve():
        return
    target.mkdir(parents=True, exist_ok=True)
    for item in sorted(legacy.iterdir()):
        if (
            item.is_file()
            and item.name.endswith(".sqlite")
            and not item.name.startswith(".")
        ):
            destination = target / item.name
            if not destination.exists():
                shutil.move(str(item), str(destination))
    # Remove leftover staging/tmp entries and the now-empty legacy tree.
    for item in list(legacy.iterdir()):
        if item.is_dir():
            shutil.rmtree(item, ignore_errors=True)
        else:
            item.unlink(missing_ok=True)
    try:
        legacy.rmdir()
    except OSError:
        pass


@dataclass(frozen=True)
class DictionaryLookup:
    found: bool
    dictionary: DictionaryRecord | None
    query: str
    entries: tuple[dict, ...]
    asset_base_path: str = ""
    allow_scripts: bool = False


class DictionaryService:
    """Keep local dictionary records outside the EPUB cache and main database."""

    def __init__(self, store: StateStore, server_directory):
        self.store = store
        self.server_directory = Path(server_directory)
        self.dictionary_directory = self.server_directory / "data" / "dictionaries"
        self.dictionary_directory.mkdir(parents=True, exist_ok=True)
        self.store.ensure_global_dictionary_default()

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
                connection.execute(
                    "CREATE TABLE assets (path TEXT PRIMARY KEY, content_type TEXT NOT NULL, content BLOB NOT NULL)"
                )
                connection.executemany(
                    "INSERT INTO meta(key, value) VALUES (?, ?)",
                    (("format", dictionary.format), ("content_sha256", digest),
                     ("asset_base_path", ""), ("allow_scripts", "0"),
                     ("definition_rendering_revision", "4")),
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
        """Install a direct MDX or a package archive already streamed to disk.

        This legacy entry point remains useful to in-process callers.  Archive
        imports retain their directory layout so a dictionary's HTML can refer
        to the presentation resources shipped alongside its data files.
        """
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
                self._extract_zip_package(upload_path, staging)
            else:
                self._extract_tar_package(upload_path, staging)
            if not is_mdx:
                candidates = [item for item in staging.rglob("*") if item.is_file() and item.suffix.casefold() in {".ifo", ".mdx"}]
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
    def _safe_package_path(value: str) -> str | None:
        if not isinstance(value, str):
            return None
        value = unquote(value).replace("\\", "/")
        if not value or value.startswith("/") or "\x00" in value:
            return None
        normalized = posixpath.normpath(value).lstrip("/")
        if normalized in {"", ".", ".."} or normalized.startswith("../"):
            return None
        return normalized.casefold()

    @classmethod
    def _extract_zip_package(cls, upload_path: Path, staging: Path) -> None:
        try:
            archive = zipfile.ZipFile(upload_path)
        except zipfile.BadZipFile as error:
            raise DictionaryServiceError("invalid_dictionary_archive") from error
        try:
            with archive:
                members = [member for member in archive.infolist() if not member.is_dir()]
                if not members:
                    raise DictionaryServiceError("invalid_dictionary_archive")
                seen_paths: set[str] = set()
                for member in members:
                    relative = cls._safe_package_path(member.filename)
                    if (
                        relative is None
                        or relative in seen_paths
                        or (member.external_attr >> 16) & 0o170000 == 0o120000
                    ):
                        raise DictionaryServiceError("invalid_dictionary_archive")
                    # Finder adds ``__MACOSX/._*`` sidecars when a ZIP is
                    # created in macOS.  They are metadata, not a second MDX
                    # or MDD, and must not affect package validation.
                    parts = relative.split("/")
                    if parts[0] == "__macosx" or parts[-1].startswith("._"):
                        continue
                    seen_paths.add(relative)
                    target = staging / relative
                    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                    try:
                        with archive.open(member) as source_stream, target.open("xb") as output:
                            shutil.copyfileobj(source_stream, output, 1024 * 1024)
                    except FileExistsError as error:
                        raise DictionaryServiceError("invalid_dictionary_archive") from error
        except OSError as error:
            raise DictionaryServiceError("invalid_dictionary_archive") from error

    @classmethod
    def _extract_tar_package(cls, upload_path: Path, staging: Path) -> None:
        """Safely unpack a StarDict tarball while retaining package paths."""
        try:
            archive = tarfile.open(upload_path, mode="r:*")
        except (tarfile.TarError, OSError, EOFError) as error:
            raise DictionaryServiceError("invalid_dictionary_archive") from error
        try:
            with archive:
                members = [member for member in archive.getmembers() if member.isfile()]
                if not members:
                    raise DictionaryServiceError("invalid_dictionary_archive")
                seen_paths: set[str] = set()
                for member in members:
                    relative = cls._safe_package_path(member.name)
                    if relative is None or relative in seen_paths:
                        raise DictionaryServiceError("invalid_dictionary_archive")
                    parts = relative.split("/")
                    if parts[0] == "__macosx" or parts[-1].startswith("._"):
                        continue
                    seen_paths.add(relative)
                    source_stream = archive.extractfile(member)
                    if source_stream is None:
                        raise DictionaryServiceError("invalid_dictionary_archive")
                    target = staging / relative
                    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                    try:
                        with source_stream, target.open("xb") as output:
                            shutil.copyfileobj(source_stream, output, 1024 * 1024)
                    except FileExistsError as error:
                        raise DictionaryServiceError("invalid_dictionary_archive") from error
        except OSError as error:
            raise DictionaryServiceError("invalid_dictionary_archive") from error

    @staticmethod
    def _asset_content_type(path: str, content: bytes) -> tuple[str, bytes] | None:
        suffix = Path(path).suffix.casefold()
        if suffix in {".css", ".js", ".mjs"}:
            for encoding in ("utf-8", "gb18030"):
                try:
                    content_type = "text/css; charset=utf-8" if suffix == ".css" else "text/javascript; charset=utf-8"
                    return content_type, content.decode(encoding).encode("utf-8")
                except UnicodeDecodeError:
                    continue
            return None
        if suffix in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}:
            if suffix == ".svg":
                try:
                    return "image/svg+xml", content.decode("utf-8").encode("utf-8")
                except UnicodeDecodeError:
                    return None
            kind = "image"
        elif suffix in {".mp3", ".wav", ".ogg"}:
            kind = "audio"
        elif suffix in {".mp4", ".webm", ".ogv", ".avi"}:
            video_types = {
                ".mp4": "video/mp4", ".webm": "video/webm", ".ogv": "video/ogg", ".avi": "video/x-msvideo",
            }
            return video_types[suffix], content
        elif suffix in {".woff", ".woff2", ".ttf", ".otf"}:
            font_types = {
                ".woff": "font/woff",
                ".woff2": "font/woff2",
                ".ttf": "font/ttf",
                ".otf": "font/otf",
            }
            return font_types[suffix], content
        elif suffix == ".pdf":
            return "application/pdf", content
        elif suffix in {".bin", ".dat"}:
            return "application/octet-stream", content
        else:
            return None
        content_type = DictionaryService._media_content_type(kind, content)
        return (content_type, content) if content_type else None

    @staticmethod
    def _join_asset_path(base: str, reference: str) -> str | None:
        candidate = posixpath.join(base, reference) if base else reference
        return DictionaryService._safe_package_path(candidate)

    def _set_asset_base_path(self, dictionary_id: str, asset_base_path: str) -> None:
        path = self.dictionary_directory / (dictionary_id + ".sqlite")
        try:
            with sqlite3.connect(path) as connection:
                connection.execute(
                    "UPDATE meta SET value = ? WHERE key = 'asset_base_path'", (asset_base_path,),
                )
        except sqlite3.Error as error:
            raise DictionaryServiceError("dictionary_unavailable") from error

    def _store_package_assets(self, dictionary_id: str, staging: Path, source: Path) -> None:
        path = self.dictionary_directory / (dictionary_id + ".sqlite")
        asset_rows = []
        for item in staging.rglob("*"):
            if not item.is_file() or item == source or item.suffix.casefold() == ".mdd":
                continue
            relative = item.relative_to(staging).as_posix()
            resource = self._asset_content_type(relative, item.read_bytes())
            if resource:
                asset_rows.append((relative, resource[0], resource[1]))
        try:
            with sqlite3.connect(path) as connection:
                connection.executemany(
                    "INSERT OR REPLACE INTO assets(path, content_type, content) VALUES (?, ?, ?)", asset_rows,
                )
        except sqlite3.Error as error:
            raise DictionaryServiceError("dictionary_unavailable") from error

    @classmethod
    def _package_css_mdict_references(cls, staging: Path) -> set[str]:
        """Find MDD paths referenced from packaged stylesheets.

        MDict's ``file://`` URLs are rooted at the MDX package, not at the
        stylesheet's own directory.  They must therefore be unpacked from the
        MDD even if no entry body happens to reference them directly.
        """
        references: set[str] = set()
        pattern = re.compile(r"url\(\s*(['\"]?)file://([^'\")\s]+)\1\s*\)", re.IGNORECASE)
        for item in staging.rglob("*.css"):
            try:
                raw = item.read_bytes()
            except OSError:
                continue
            for encoding in ("utf-8", "gb18030"):
                try:
                    stylesheet = raw.decode(encoding)
                    break
                except UnicodeDecodeError:
                    stylesheet = None
            if stylesheet is None:
                continue
            for match in pattern.finditer(stylesheet):
                reference = cls._safe_package_path(match.group(2))
                if reference:
                    references.add(reference)
        return references

    def install_mdict_package_file(
        self, upload_path: Path, filename: str, *, created_by_user_id: str,
        display_name: str | None = None, attribution: str = "",
    ) -> DictionaryRecord:
        """Install one ZIP containing an MDX and its local presentation assets."""
        upload_path = Path(upload_path)
        if not upload_path.is_file() or upload_path.stat().st_size <= 0:
            raise DictionaryServiceError("invalid_dictionary_archive")
        if Path(filename).suffix.casefold() != ".zip":
            raise DictionaryServiceError("unsupported_dictionary_format")
        staging = self.dictionary_directory / (".mdict-package-" + str(uuid.uuid4()))
        staging.mkdir(mode=0o700)
        try:
            self._extract_zip_package(upload_path, staging)
            sources = [item for item in staging.rglob("*") if item.is_file() and item.suffix.casefold() == ".mdx"]
            if len(sources) != 1:
                raise DictionaryServiceError("invalid_dictionary_archive")
            source = sources[0]
            requested_name = display_name.strip() if isinstance(display_name, str) else ""
            fallback_name = Path(filename).stem
            record = self.install(
                source, created_by_user_id=created_by_user_id,
                display_name=requested_name or fallback_name, attribution=attribution,
            )
            asset_base_path = source.relative_to(staging).parent.as_posix()
            asset_base_path = "" if asset_base_path == "." else asset_base_path
            self._set_asset_base_path(record.id, asset_base_path)
            self._store_package_assets(record.id, staging, source)
            mdd_candidates = [
                item for item in source.parent.iterdir()
                if item.is_file() and item.suffix.casefold() == ".mdd"
                and item.stem.casefold() == source.stem.casefold()
            ]
            if len(mdd_candidates) > 1:
                raise DictionaryServiceError("invalid_dictionary_archive")
            if mdd_candidates:
                self.attach_mdict_resources_file(
                    record.id, mdd_candidates[0], mdd_candidates[0].name,
                    extra_references=self._package_css_mdict_references(staging),
                    allow_missing_references=True,
                )
            return record
        except Exception:
            if "record" in locals():
                self.delete(record.id)
            raise
        finally:
            shutil.rmtree(staging, ignore_errors=True)

    def install_stardict_package_file(
        self, upload_path: Path, filename: str, *, created_by_user_id: str,
        display_name: str | None = None, attribution: str = "",
    ) -> DictionaryRecord:
        """Install a StarDict archive and retain its local presentation files."""
        upload_path = Path(upload_path)
        if not upload_path.is_file() or upload_path.stat().st_size <= 0:
            raise DictionaryServiceError("invalid_dictionary_archive")
        archive_name = Path(filename).name if isinstance(filename, str) else ""
        archive_name_folded = archive_name.casefold()
        suffix = next((item for item in (".tar.bz2", ".tar.gz", ".tbz2", ".tgz", ".zip")
                       if archive_name_folded.endswith(item)), "")
        if not suffix:
            raise DictionaryServiceError("unsupported_dictionary_format")
        staging = self.dictionary_directory / (".stardict-package-" + str(uuid.uuid4()))
        staging.mkdir(mode=0o700)
        try:
            if suffix == ".zip":
                self._extract_zip_package(upload_path, staging)
            else:
                self._extract_tar_package(upload_path, staging)
            sources = [item for item in staging.rglob("*") if item.is_file() and item.suffix.casefold() == ".ifo"]
            if len(sources) != 1:
                raise DictionaryServiceError("invalid_dictionary_archive")
            source = sources[0]
            base = source.with_suffix("")
            if not base.with_suffix(".idx").is_file() or not (
                base.with_suffix(".dict").is_file() or base.with_suffix(".dict.dz").is_file()
            ):
                raise DictionaryServiceError("invalid_dictionary_archive")
            requested_name = display_name.strip() if isinstance(display_name, str) else ""
            fallback_name = archive_name[:-len(suffix)] if archive_name else ""
            record = self.install(
                source, created_by_user_id=created_by_user_id,
                display_name=requested_name or fallback_name, attribution=attribution,
            )
            asset_base_path = source.relative_to(staging).parent.as_posix()
            asset_base_path = "" if asset_base_path == "." else asset_base_path
            self._set_asset_base_path(record.id, asset_base_path)
            self._store_package_assets(record.id, staging, source)
            return record
        except Exception:
            if "record" in locals():
                self.delete(record.id)
            raise
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

    def attach_mdict_resources_file(
        self, dictionary_id: str, upload_path: Path, filename: str, *,
        extra_references: set[str] | None = None,
        allow_missing_references: bool = False,
    ) -> None:
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
                base_row = connection.execute(
                    "SELECT value FROM meta WHERE key = 'asset_base_path'"
                ).fetchone()
                asset_base_path = base_row[0] if base_row else ""
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
        references.update(
            reference for reference in (extra_references or set())
            if isinstance(reference, str) and self._safe_package_path(reference)
        )
        if not references:
            raise DictionaryServiceError("mdict_resources_not_found")
        try:
            resources = read_mdict_resources(upload_path, references)
        except DictionaryFormatError as error:
            if allow_missing_references and error.code == "mdict_resources_not_found":
                return
            raise DictionaryServiceError(error.code) from error

        declared_kinds = {
            item["reference"]: item.get("kind")
            for media in entry_media.values() for item in media
            if isinstance(item, dict) and isinstance(item.get("reference"), str)
        }
        replacements: dict[str, tuple[str, str]] = {}
        for reference, content in resources.items():
            kind = declared_kinds.get(reference)
            content_type = self._media_content_type(kind, content) if isinstance(kind, str) else None
            if not content_type:
                content_type = self._media_content_type("image", content)
            if not content_type:
                content_type = self._media_content_type("audio", content)
            if content_type:
                replacements[reference] = (hashlib.sha256(content).hexdigest(), content_type)
        if not replacements:
            raise DictionaryServiceError("unsupported_mdict_resource")
        try:
            with sqlite3.connect(path) as connection:
                for reference, (resource_id, content_type) in replacements.items():
                    connection.execute(
                        "INSERT OR IGNORE INTO resources(id, content_type, content) VALUES (?, ?, ?)",
                        (resource_id, content_type, resources[reference]),
                    )
                    asset_path = self._join_asset_path(asset_base_path, reference)
                    if asset_path:
                        connection.execute(
                            "INSERT OR REPLACE INTO assets(path, content_type, content) VALUES (?, ?, ?)",
                            (asset_path, content_type, resources[reference]),
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

    def get_asset(self, dictionary_id: str, asset_path: str) -> dict:
        asset_path = self._safe_package_path(asset_path)
        dictionary = self.store.get_dictionary(dictionary_id)
        path = self.dictionary_directory / (dictionary_id + ".sqlite") if dictionary else None
        if asset_path is None or dictionary is None or not dictionary.enabled or not path.is_file():
            raise DictionaryServiceError("dictionary_media_unavailable")
        try:
            with sqlite3.connect("file:" + path.as_posix() + "?mode=ro", uri=True) as connection:
                row = connection.execute(
                    "SELECT content_type, content FROM assets WHERE path = ?", (asset_path,)
                ).fetchone()
                base_row = connection.execute(
                    "SELECT value FROM meta WHERE key = 'asset_base_path'"
                ).fetchone()
        except sqlite3.Error as error:
            raise DictionaryServiceError("dictionary_media_unavailable") from error
        if row is None:
            raise DictionaryServiceError("dictionary_media_unavailable")
        content_type, content = row[0], bytes(row[1])
        if content_type.startswith("text/css"):
            asset_base_path = base_row[0] if base_row else ""
            stylesheet_directory = posixpath.dirname(asset_path)
            try:
                stylesheet = content.decode("utf-8")
            except UnicodeDecodeError as error:
                raise DictionaryServiceError("dictionary_media_unavailable") from error

            def rewrite_package_url(match: re.Match[str]) -> str:
                quote, reference = match.group(1), self._safe_package_path(match.group(2))
                target = self._join_asset_path(asset_base_path, reference) if reference else None
                if target is None:
                    return match.group(0)
                relative = posixpath.relpath(target, stylesheet_directory or ".")
                return "url(" + quote + relative + quote + ")"

            content = re.sub(
                r"url\(\s*(['\"]?)(?:file|sound)://([^'\")\s]+)\1\s*\)", rewrite_package_url,
                stylesheet, flags=re.IGNORECASE,
            ).encode("utf-8")
        return {"content_type": content_type, "content": content}

    def allows_scripts(self, dictionary_id: str) -> bool:
        dictionary = self.store.get_dictionary(dictionary_id)
        path = self.dictionary_directory / (dictionary_id + ".sqlite") if dictionary else None
        if dictionary is None or not path.is_file():
            return False
        try:
            with sqlite3.connect("file:" + path.as_posix() + "?mode=ro", uri=True) as connection:
                row = connection.execute(
                    "SELECT value FROM meta WHERE key = 'allow_scripts'"
                ).fetchone()
        except sqlite3.Error:
            return False
        return bool(row and row[0] == "1")

    def set_script_execution_enabled(self, dictionary_id: str, enabled: bool) -> DictionaryRecord:
        if not isinstance(enabled, bool):
            raise ValueError("Dictionary script flag must be a boolean")
        dictionary = self.store.get_dictionary(dictionary_id)
        path = self.dictionary_directory / (dictionary_id + ".sqlite") if dictionary else None
        if dictionary is None or not path.is_file():
            raise KeyError(dictionary_id)
        try:
            with sqlite3.connect(path) as connection:
                connection.execute(
                    "INSERT INTO meta(key, value) VALUES ('allow_scripts', ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    ("1" if enabled else "0",),
                )
        except sqlite3.Error as error:
            raise DictionaryServiceError("dictionary_unavailable") from error
        return dictionary

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
                asset_base_row = connection.execute(
                    "SELECT value FROM meta WHERE key = 'asset_base_path'"
                ).fetchone()
                script_row = connection.execute(
                    "SELECT value FROM meta WHERE key = 'allow_scripts'"
                ).fetchone()
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
        return DictionaryLookup(
            bool(entries), dictionary, query, entries,
            asset_base_row[0] if asset_base_row else "",
            bool(script_row and script_row[0] == "1"),
        )

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
