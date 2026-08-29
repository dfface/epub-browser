import json
import os
import re
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

from .epub_identity import validate_book_id
from .source_format import is_supported_source


SIDECAR_SUFFIX = ".epub-browser.json"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class SidecarIdentityError(RuntimeError):
    pass


@dataclass(frozen=True)
class SidecarIdentity:
    path: Path
    book_id: str
    source_fingerprint: str
    document: dict


def sidecar_path_for(source_path: Path) -> Path:
    source = Path(source_path)
    return source.with_name(source.name + SIDECAR_SUFFIX)


def read_exact_sidecar(source_path: Path) -> Optional[SidecarIdentity]:
    path = sidecar_path_for(source_path)
    if not path.exists() and not path.is_symlink():
        return None
    return read_sidecar_file(path)


def validate_source_fingerprint(value: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise SidecarIdentityError(
            f"Invalid SHA-256 source fingerprint: {value!r}"
        )
    return value


def read_sidecar_file(path: Path) -> SidecarIdentity:
    sidecar_path = Path(path)
    try:
        source_stat = sidecar_path.lstat()
        if stat.S_ISLNK(source_stat.st_mode):
            raise SidecarIdentityError("symbolic link sidecars are not allowed")
        if not stat.S_ISREG(source_stat.st_mode):
            raise SidecarIdentityError("sidecar is not a regular file")
        if source_stat.st_nlink > 1:
            raise SidecarIdentityError("sidecar has multiple hard links")

        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(sidecar_path, flags)
        try:
            opened_stat = os.fstat(descriptor)
            if not stat.S_ISREG(opened_stat.st_mode):
                raise SidecarIdentityError("sidecar is not a regular file")
            if opened_stat.st_nlink > 1:
                raise SidecarIdentityError("sidecar has multiple hard links")
            if (opened_stat.st_dev, opened_stat.st_ino) != (
                source_stat.st_dev,
                source_stat.st_ino,
            ):
                raise SidecarIdentityError("sidecar changed while being read")
            with os.fdopen(descriptor, "rb", closefd=False) as sidecar:
                raw = sidecar.read()
        finally:
            os.close(descriptor)

        try:
            document = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise SidecarIdentityError(f"invalid UTF-8 JSON: {error}") from error
        if not isinstance(document, dict):
            raise SidecarIdentityError("sidecar document must be a JSON object")
        if type(document.get("schema")) is not int or document["schema"] != 1:
            raise SidecarIdentityError("unsupported sidecar schema")
        try:
            book_id = validate_book_id(document.get("book_id"))
        except (TypeError, ValueError) as error:
            raise SidecarIdentityError(str(error)) from error
        fingerprint = document.get("source_fingerprint")
        if not isinstance(fingerprint, dict):
            raise SidecarIdentityError("source_fingerprint must be an object")
        if fingerprint.get("algorithm") != "sha256":
            raise SidecarIdentityError(
                "source_fingerprint algorithm must be sha256"
            )
        source_fingerprint = validate_source_fingerprint(fingerprint.get("value"))
    except SidecarIdentityError as error:
        raise SidecarIdentityError(f"Invalid sidecar {sidecar_path}: {error}") from error
    except OSError as error:
        raise SidecarIdentityError(f"Unable to read sidecar {sidecar_path}: {error}") from error

    return SidecarIdentity(
        path=sidecar_path,
        book_id=book_id,
        source_fingerprint=source_fingerprint,
        document=document,
    )


def write_sidecar(
    source_path: Path,
    book_id: str,
    source_fingerprint: str,
) -> Path:
    path = sidecar_path_for(source_path)
    existing = read_exact_sidecar(source_path)
    payload = dict(existing.document) if existing is not None else {}
    payload.update(
        {
            "schema": 1,
            "book_id": validate_book_id(book_id),
            "source_fingerprint": {
                "algorithm": "sha256",
                "value": validate_source_fingerprint(source_fingerprint),
            },
        }
    )
    serialized = (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    if existing is not None and path.read_bytes() == serialized:
        return path

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as temporary:
            temporary.write(serialized)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_path, path)
        _fsync_directory(path.parent)
    finally:
        temporary_path.unlink(missing_ok=True)
    return path


def adopt_sidecar(orphan: SidecarIdentity, source_path: Path) -> Path:
    current = read_sidecar_file(orphan.path)
    if (
        current.book_id != orphan.book_id
        or current.source_fingerprint != orphan.source_fingerprint
    ):
        raise SidecarIdentityError(
            f"Orphan sidecar changed before adoption: {orphan.path}"
        )
    destination = sidecar_path_for(source_path)
    if destination.exists() or destination.is_symlink():
        raise SidecarIdentityError(
            f"Cannot adopt sidecar because destination exists: {destination}"
        )
    os.replace(current.path, destination)
    _fsync_directory(current.path.parent)
    if destination.parent != current.path.parent:
        _fsync_directory(destination.parent)
    return destination


def discover_orphan_sidecars(
    configured_sources: Sequence[Path],
    discovered_sources: Sequence[Path],
) -> tuple[Path, ...]:
    exact_sidecars = {
        _absolute(sidecar_path_for(source)) for source in discovered_sources
    }
    candidates = set()
    for configured in configured_sources:
        source = Path(configured)
        if is_supported_source(source):
            _collect_sidecars(source.parent, candidates)
            continue
        if not source.is_dir():
            continue
        for root, directories, files in os.walk(source, followlinks=False):
            root_path = Path(root)
            directories[:] = [
                name
                for name in directories
                if not name.startswith(".")
                and not (root_path / name).is_symlink()
            ]
            for name in files:
                if not name.startswith(".") and name.endswith(SIDECAR_SUFFIX):
                    candidates.add(root_path / name)

    orphans = []
    for candidate in candidates:
        absolute = _absolute(candidate)
        paired = Path(str(candidate)[: -len(SIDECAR_SUFFIX)])
        if absolute in exact_sidecars or paired.exists() or paired.is_symlink():
            continue
        orphans.append(candidate)
    return tuple(sorted(set(orphans), key=str))


def _collect_sidecars(directory: Path, output: set) -> None:
    if not directory.is_dir():
        return
    for child in directory.iterdir():
        if (
            not child.name.startswith(".")
            and child.name.endswith(SIDECAR_SUFFIX)
        ):
            output.add(child)


def _absolute(path: Path) -> Path:
    return Path(os.path.abspath(path))


def _fsync_directory(directory: Path) -> None:
    if not hasattr(os, "O_DIRECTORY"):
        return
    descriptor = None
    try:
        descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        if descriptor is not None:
            os.close(descriptor)
