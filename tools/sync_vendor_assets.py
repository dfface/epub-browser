#!/usr/bin/env python3
"""Validate the locked third-party browser asset inventory without networking."""

import argparse
import gzip
import hashlib
import json
import os
import re
import sys
import tarfile
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Iterable, Tuple
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, build_opener, urlopen


LOCK_SCHEMA = 1
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
DRIVE_PATH_PATTERN = re.compile(r"[A-Za-z]:")


class VendorAssetError(Exception):
    """The lock or installed vendor files do not meet the supply-chain contract."""


class HTTPSOnlyRedirectHandler(HTTPRedirectHandler):
    """Retain urllib's bounded redirect accounting while forbidding downgrades."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urlparse(newurl).scheme != "https":
            raise VendorAssetError("download redirected away from HTTPS")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _https_urlopen(url):
    return build_opener(HTTPSOnlyRedirectHandler()).open(url)


@dataclass(frozen=True)
class LockedFile:
    source: str
    target: str
    sha256: str


@dataclass(frozen=True)
class LockedSource:
    kind: str
    url: str


@dataclass(frozen=True)
class LockedArchive:
    sha256: str
    max_bytes: int
    max_expanded_bytes: int


@dataclass(frozen=True)
class LockedLicense:
    spdx: str
    files: Tuple[str, ...]


@dataclass(frozen=True)
class LockedPackage:
    name: str
    version: str
    source: LockedSource
    archive: LockedArchive
    license: LockedLicense
    files: Tuple[LockedFile, ...]


@dataclass(frozen=True)
class AssetLock:
    schema: int
    packages: Tuple[LockedPackage, ...]


def safe_relative(value: str) -> PurePosixPath:
    """Return a canonical relative POSIX path or reject paths unsafe to install."""
    if not isinstance(value, str) or not value or "\x00" in value or "\\" in value:
        raise VendorAssetError("unsafe asset path: {!r}".format(value))
    if DRIVE_PATH_PATTERN.match(value):
        raise VendorAssetError("unsafe asset path: {!r}".format(value))
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or not path.parts
        or ".." in path.parts
        or path.as_posix() != value
    ):
        raise VendorAssetError("unsafe asset path: {!r}".format(value))
    return path


def _safe_archive_relative(value: str) -> PurePosixPath:
    """Normalize a safe archive member path for duplicate detection."""
    if not isinstance(value, str) or not value or "\x00" in value or "\\" in value:
        raise VendorAssetError("archive contains an unsafe member path")
    if DRIVE_PATH_PATTERN.match(value):
        raise VendorAssetError("archive contains an unsafe member path")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts:
        raise VendorAssetError("archive contains an unsafe member path")
    normalized = path.as_posix()
    if normalized in ("", "."):
        raise VendorAssetError("archive contains an unsafe member path")
    return PurePosixPath(normalized)


class _ExpandedArchiveReader:
    """Read gzip output without allowing decompressed bytes past the lock bound."""

    def __init__(self, source, limit: int, package_name: str):
        self.source = source
        self.remaining = limit
        self.package_name = package_name

    def read(self, size: int) -> bytes:
        chunk = self.source.read(min(size, self.remaining + 1))
        if len(chunk) > self.remaining:
            raise VendorAssetError(
                "{} archive exceeds max_expanded_bytes".format(self.package_name)
            )
        self.remaining -= len(chunk)
        return chunk


def _read_exact(source, size: int, package_name: str, allow_eof: bool = False):
    chunks = []
    remaining = size
    while remaining:
        chunk = source.read(remaining)
        if not chunk:
            if allow_eof and not chunks:
                return None
            raise VendorAssetError(
                "{} archive contains truncated tar data".format(package_name)
            )
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _preflight_tar_archive(archive_path: Path, limit: int, package_name: str) -> None:
    """Bound every raw tar record before tarfile may interpret extensions."""
    compressed_archive = gzip.GzipFile(filename=archive_path, mode="rb")
    with compressed_archive:
        expanded = _ExpandedArchiveReader(compressed_archive, limit, package_name)
        while True:
            header = _read_exact(
                expanded, tarfile.BLOCKSIZE, package_name, allow_eof=True
            )
            if header is None:
                return
            if header == tarfile.NUL * tarfile.BLOCKSIZE:
                continue
            try:
                member = tarfile.TarInfo.frombuf(
                    header, encoding="utf-8", errors="surrogateescape"
                )
            except tarfile.HeaderError as error:
                raise VendorAssetError(
                    "{} archive contains an invalid tar header".format(package_name)
                ) from error
            _safe_archive_relative(member.name)
            if member.size < 0:
                raise VendorAssetError(
                    "{} archive contains an invalid member size".format(package_name)
                )
            padded_size = (
                (member.size + tarfile.BLOCKSIZE - 1) // tarfile.BLOCKSIZE
            ) * tarfile.BLOCKSIZE
            if padded_size > expanded.remaining:
                raise VendorAssetError(
                    "{} archive exceeds max_expanded_bytes".format(package_name)
                )
            if member.type == tarfile.GNUTYPE_SPARSE:
                raise VendorAssetError(
                    "{} archive contains unsupported entry".format(package_name)
                )
            _read_exact(expanded, padded_size, package_name)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as asset_file:
        for chunk in iter(lambda: asset_file.read(64 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_lock(path: Path) -> AssetLock:
    """Load and strictly validate a version-one asset lock manifest."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise VendorAssetError("cannot read asset lock {}: {}".format(path, error)) from error
    return _parse_lock(data)


def verify_assets(lock_path: Path, vendor_root: Path) -> None:
    """Verify the exact managed vendor file inventory without network access."""
    lock = load_lock(lock_path)
    expected = {
        item.target: item.sha256
        for package in lock.packages
        for item in package.files
    }
    if vendor_root.is_symlink():
        raise VendorAssetError("vendor root must not be a symbolic link")
    expected_directories = _expected_directories(expected)
    actual = set()
    for relative, kind in _vendor_entries(vendor_root):
        if kind == "directory":
            if relative not in expected_directories:
                raise VendorAssetError("unexpected directory in vendor root: {}".format(relative))
        else:
            actual.add(relative)
    if actual != set(expected):
        raise VendorAssetError("generated vendor file set does not match lock")
    for relative, digest in expected.items():
        candidate = vendor_root / safe_relative(relative)
        if candidate.is_symlink() or sha256_file(candidate) != digest:
            raise VendorAssetError("{} SHA-256 mismatch".format(relative))


def copy_bounded(response, destination: Path, limit: int) -> str:
    digest = hashlib.sha256()
    total = 0
    with destination.open("wb") as output:
        while True:
            chunk = response.read(64 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > limit:
                raise VendorAssetError("archive exceeds max_bytes")
            digest.update(chunk)
            output.write(chunk)
    return digest.hexdigest()


def fetch_assets(lock_path: Path, vendor_root: Path, opener=urlopen) -> None:
    """Fetch, validate, and atomically install the locked vendor files."""
    lock = load_lock(lock_path)
    for package in lock.packages:
        if urlparse(package.source.url).scheme != "https":
            raise VendorAssetError("{} download requires HTTPS".format(package.name))
    if vendor_root.is_symlink():
        raise VendorAssetError("vendor root must not be a symbolic link")
    try:
        verify_assets(lock_path, vendor_root)
        return
    except VendorAssetError:
        pass
    _validate_existing_install_tree(lock, vendor_root)
    if not vendor_root.parent.is_dir():
        raise VendorAssetError("vendor root parent must be an existing directory")

    with tempfile.TemporaryDirectory(
        prefix=".vendor-assets-", dir=vendor_root.parent
    ) as temporary_directory:
        staging_root = Path(temporary_directory) / "staging"
        staging_root.mkdir()
        open_url = _https_urlopen if opener is urlopen else opener
        for package_index, package in enumerate(lock.packages):
            archive_path = Path(temporary_directory) / "archive-{}".format(package_index)
            try:
                with open_url(package.source.url) as response:
                    final_url = response.geturl()
                    if urlparse(final_url).scheme != "https":
                        raise VendorAssetError(
                            "{} download redirected away from HTTPS".format(package.name)
                        )
                    digest = copy_bounded(response, archive_path, package.archive.max_bytes)
            except VendorAssetError:
                raise
            except Exception as error:
                raise VendorAssetError(
                    "{} download failed".format(package.name)
                ) from error
            if digest != package.archive.sha256:
                raise VendorAssetError("{} archive SHA-256 mismatch".format(package.name))
            try:
                _preflight_tar_archive(
                    archive_path,
                    package.archive.max_expanded_bytes,
                    package.name,
                )
                extracted = set()
                compressed_archive = gzip.GzipFile(filename=archive_path, mode="rb")
                with compressed_archive, tarfile.open(
                    fileobj=compressed_archive,
                    mode="r|",
                    bufsize=tarfile.BLOCKSIZE,
                ) as archive:
                    allowlist = {item.source: item for item in package.files}
                    seen_members = set()
                    expanded_bytes = 0
                    for member in archive:
                        relative = _safe_archive_relative(member.name).as_posix()
                        if relative in seen_members:
                            raise VendorAssetError(
                                "{} archive contains duplicate normalized members".format(
                                    package.name
                                )
                            )
                        seen_members.add(relative)
                        if not member.isfile() and not member.isdir():
                            raise VendorAssetError(
                                "{} archive contains unsupported entry".format(package.name)
                            )
                        if member.size < 0:
                            raise VendorAssetError(
                                "{} archive contains an invalid member size".format(
                                    package.name
                                )
                            )
                        expanded_bytes += member.size
                        if expanded_bytes > package.archive.max_expanded_bytes:
                            raise VendorAssetError(
                                "{} archive exceeds max_expanded_bytes".format(
                                    package.name
                                )
                            )
                        item = allowlist.get(relative)
                        if item is None or member.isdir():
                            continue
                        source = archive.extractfile(member)
                        if source is None:
                            raise VendorAssetError(
                                "{} cannot read archive member {}".format(
                                    package.name, relative
                                )
                            )
                        destination = staging_root / safe_relative(item.target)
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        with source:
                            file_digest = copy_bounded(
                                source, destination, package.archive.max_expanded_bytes
                            )
                        if file_digest != item.sha256:
                            raise VendorAssetError(
                                "{} {} SHA-256 mismatch".format(package.name, relative)
                            )
                        extracted.add(relative)
                missing = set(allowlist).difference(extracted)
                if missing:
                    raise VendorAssetError(
                        "{} archive is missing locked files: {}".format(
                            package.name, ", ".join(sorted(missing))
                        )
                    )
            except (tarfile.TarError, OSError, EOFError) as error:
                raise VendorAssetError(
                    "{} archive extraction failed".format(package.name)
                ) from error

        for package in lock.packages:
            for item in package.files:
                relative = safe_relative(item.target)
                _assert_safe_managed_parent(vendor_root, relative)
                target = vendor_root / relative
                try:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    os.replace(staging_root / relative, target)
                except OSError as error:
                    raise VendorAssetError(
                        "{} install failed for {}".format(package.name, item.target)
                    ) from error
        verify_assets(lock_path, vendor_root)


def clean_assets(lock_path: Path, vendor_root: Path) -> None:
    """Remove only files owned by the current lock and now-empty parents."""
    lock = load_lock(lock_path)
    for package in lock.packages:
        for item in package.files:
            relative = safe_relative(item.target)
            _assert_safe_managed_parent(vendor_root, relative)
            try:
                (vendor_root / relative).unlink(missing_ok=True)
            except OSError as error:
                raise VendorAssetError(
                    "{} clean failed for {}".format(package.name, item.target)
                ) from error
    expected = {
        item.target: item.sha256
        for package in lock.packages
        for item in package.files
    }
    for directory in sorted(
        _expected_directories(expected),
        key=lambda value: len(PurePosixPath(value).parts),
        reverse=True,
    ):
        try:
            (vendor_root / safe_relative(directory)).rmdir()
        except (FileNotFoundError, OSError):
            pass


def _expected_directories(expected: Dict[str, str]) -> set:
    directories = set()
    for target in expected:
        parent = safe_relative(target).parent
        while parent != PurePosixPath("."):
            directories.add(parent.as_posix())
            parent = parent.parent
    return directories


def _validate_existing_install_tree(lock: AssetLock, vendor_root: Path) -> None:
    """Allow missing or incorrect managed files, but reject all unowned entries."""
    expected = {
        item.target: item.sha256
        for package in lock.packages
        for item in package.files
    }
    expected_directories = _expected_directories(expected)
    for relative, kind in _vendor_entries(vendor_root):
        if kind == "directory":
            if relative not in expected_directories:
                raise VendorAssetError(
                    "unexpected directory in vendor root: {}".format(relative)
                )
        elif relative not in expected:
            raise VendorAssetError("unexpected file in vendor root: {}".format(relative))


def _assert_safe_managed_parent(vendor_root: Path, relative: PurePosixPath) -> None:
    if vendor_root.is_symlink():
        raise VendorAssetError("vendor root must not be a symbolic link")
    if vendor_root.exists() and not vendor_root.is_dir():
        raise VendorAssetError("vendor root must be a directory")
    parent = vendor_root
    for part in relative.parent.parts:
        parent = parent / part
        if parent.is_symlink():
            raise VendorAssetError("symbolic link in managed target path")
        if parent.exists() and not parent.is_dir():
            raise VendorAssetError("managed target parent must be a directory")


def _vendor_entries(vendor_root: Path) -> Iterable[Tuple[str, str]]:
    """Yield regular files and directories, refusing links and special entries."""
    if not vendor_root.exists():
        return
    if not vendor_root.is_dir():
        raise VendorAssetError("vendor root must be a directory")

    def walk(directory: Path) -> Iterable[Tuple[str, str]]:
        with os.scandir(directory) as entries:
            for entry in entries:
                path = Path(entry.path)
                relative = path.relative_to(vendor_root).as_posix()
                if entry.is_symlink():
                    raise VendorAssetError("symbolic link in vendor root: {}".format(relative))
                if entry.is_dir(follow_symlinks=False):
                    yield relative, "directory"
                    yield from walk(path)
                elif entry.is_file(follow_symlinks=False):
                    yield relative, "file"
                else:
                    raise VendorAssetError("unsupported entry in vendor root: {}".format(relative))

    yield from walk(vendor_root)


def _unique_object(pairs: Iterable[Tuple[str, Any]]) -> Dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise VendorAssetError("duplicate JSON field: {}".format(key))
        result[key] = value
    return result


def _parse_lock(data: Any) -> AssetLock:
    _require_object(data, "lock")
    _require_keys(data, {"schema", "packages"}, "lock")
    schema = _require_integer(data["schema"], "lock.schema")
    if schema != LOCK_SCHEMA:
        raise VendorAssetError("unsupported asset lock schema: {}".format(schema))
    packages_data = _require_list(data["packages"], "lock.packages")
    packages = tuple(_parse_package(item, index) for index, item in enumerate(packages_data))
    names = [package.name for package in packages]
    if len(names) != len(set(names)):
        raise VendorAssetError("duplicate package name in asset lock")
    if names != sorted(names):
        raise VendorAssetError("packages must be in stable name order")
    targets = [item.target for package in packages for item in package.files]
    if len(targets) != len(set(targets)):
        raise VendorAssetError("duplicate target in asset lock")
    return AssetLock(schema=schema, packages=packages)


def _parse_package(data: Any, index: int) -> LockedPackage:
    label = "lock.packages[{}]".format(index)
    _require_object(data, label)
    _require_keys(data, {"name", "version", "source", "archive", "license", "files"}, label)
    name = _require_text(data["name"], label + ".name")
    version = _require_text(data["version"], label + ".version")
    source = _parse_source(data["source"], label + ".source")
    archive = _parse_archive(data["archive"], label + ".archive")
    license_data = _parse_license(data["license"], label + ".license")
    file_data = _require_list(data["files"], label + ".files")
    if not file_data:
        raise VendorAssetError(label + ".files must not be empty")
    files = tuple(_parse_file(item, label + ".files[{}]".format(file_index)) for file_index, item in enumerate(file_data))
    sources = [item.source for item in files]
    targets = [item.target for item in files]
    if len(sources) != len(set(sources)):
        raise VendorAssetError(label + " contains duplicate source files")
    if len(targets) != len(set(targets)):
        raise VendorAssetError(label + " contains duplicate targets")
    if targets != sorted(targets):
        raise VendorAssetError(label + ".files must be in stable target order")
    missing_licenses = set(license_data.files).difference(sources)
    if missing_licenses:
        raise VendorAssetError(label + " does not install required license files")
    return LockedPackage(name, version, source, archive, license_data, files)


def _parse_source(data: Any, label: str) -> LockedSource:
    _require_object(data, label)
    _require_keys(data, {"kind", "url"}, label)
    kind = _require_text(data["kind"], label + ".kind")
    if kind != "npm-tarball":
        raise VendorAssetError(
            "{} uses unsupported archive kind: {}".format(label, kind)
        )
    return LockedSource(kind, _require_text(data["url"], label + ".url"))


def _parse_archive(data: Any, label: str) -> LockedArchive:
    _require_object(data, label)
    _require_keys(data, {"sha256", "max_bytes", "max_expanded_bytes"}, label)
    return LockedArchive(
        _require_sha256(data["sha256"], label + ".sha256"),
        _require_positive_integer(data["max_bytes"], label + ".max_bytes"),
        _require_positive_integer(data["max_expanded_bytes"], label + ".max_expanded_bytes"),
    )


def _parse_license(data: Any, label: str) -> LockedLicense:
    _require_object(data, label)
    _require_keys(data, {"spdx", "files"}, label)
    files = tuple(
        safe_relative(_require_text(value, label + ".files[{}]".format(index))).as_posix()
        for index, value in enumerate(_require_list(data["files"], label + ".files"))
    )
    if not files:
        raise VendorAssetError(label + ".files must not be empty")
    if len(files) != len(set(files)):
        raise VendorAssetError(label + ".files contains duplicates")
    return LockedLicense(_require_text(data["spdx"], label + ".spdx"), files)


def _parse_file(data: Any, label: str) -> LockedFile:
    _require_object(data, label)
    _require_keys(data, {"source", "target", "sha256"}, label)
    return LockedFile(
        safe_relative(_require_text(data["source"], label + ".source")).as_posix(),
        safe_relative(_require_text(data["target"], label + ".target")).as_posix(),
        _require_sha256(data["sha256"], label + ".sha256"),
    )


def _require_keys(data: Dict[str, Any], expected: set, label: str) -> None:
    unknown = set(data).difference(expected)
    missing = expected.difference(data)
    if unknown:
        raise VendorAssetError(label + " contains unknown fields: " + ", ".join(sorted(unknown)))
    if missing:
        raise VendorAssetError(label + " is missing fields: " + ", ".join(sorted(missing)))


def _require_object(value: Any, label: str) -> None:
    if not isinstance(value, dict):
        raise VendorAssetError(label + " must be an object")


def _require_list(value: Any, label: str) -> list:
    if not isinstance(value, list):
        raise VendorAssetError(label + " must be a list")
    return value


def _require_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise VendorAssetError(label + " must be a non-empty string")
    return value


def _require_integer(value: Any, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise VendorAssetError(label + " must be an integer")
    return value


def _require_positive_integer(value: Any, label: str) -> int:
    value = _require_integer(value, label)
    if value <= 0:
        raise VendorAssetError(label + " must be positive")
    return value


def _require_sha256(value: Any, label: str) -> str:
    value = _require_text(value, label)
    if not SHA256_PATTERN.fullmatch(value):
        raise VendorAssetError(label + " must be a lowercase SHA-256 digest")
    return value


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)
    repository_root = Path(__file__).resolve().parents[1]
    commands = {
        "fetch": subcommands.add_parser("fetch", help="fetch and install locked vendor assets"),
        "verify": subcommands.add_parser(
            "verify", help="verify the local vendor tree without networking"
        ),
        "clean": subcommands.add_parser("clean", help="remove locked vendor assets"),
    }
    for command in commands.values():
        command.add_argument(
            "--lock",
            type=Path,
            default=repository_root / "third_party" / "assets.lock.json",
        )
        command.add_argument(
            "--vendor-root",
            type=Path,
            default=repository_root / "epub_browser" / "assets" / "vendor",
        )
    arguments = parser.parse_args(argv)
    try:
        if arguments.command == "fetch":
            fetch_assets(arguments.lock, arguments.vendor_root)
        elif arguments.command == "verify":
            verify_assets(arguments.lock, arguments.vendor_root)
        else:
            clean_assets(arguments.lock, arguments.vendor_root)
    except VendorAssetError as error:
        parser.exit(1, "vendor asset {} failed: {}\n".format(arguments.command, error))
    return 0


if __name__ == "__main__":
    sys.exit(main())
