#!/usr/bin/env python3
"""Validate the locked third-party browser asset inventory without networking."""

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Iterable, Tuple


LOCK_SCHEMA = 1
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
DRIVE_PATH_PATTERN = re.compile(r"[A-Za-z]:")


class VendorAssetError(Exception):
    """The lock or installed vendor files do not meet the supply-chain contract."""


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
    actual = {
        path.relative_to(vendor_root).as_posix()
        for path in vendor_root.rglob("*")
        if path.is_file()
    }
    if actual != set(expected):
        raise VendorAssetError("generated vendor file set does not match lock")
    for relative, digest in expected.items():
        candidate = vendor_root / safe_relative(relative)
        if candidate.is_symlink() or sha256_file(candidate) != digest:
            raise VendorAssetError("{} SHA-256 mismatch".format(relative))


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
    return LockedSource(_require_text(data["kind"], label + ".kind"), _require_text(data["url"], label + ".url"))


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
    verify = subcommands.add_parser("verify", help="verify the local vendor tree without networking")
    repository_root = Path(__file__).resolve().parents[1]
    verify.add_argument("--lock", type=Path, default=repository_root / "third_party" / "assets.lock.json")
    verify.add_argument("--vendor-root", type=Path, default=repository_root / "epub_browser" / "assets" / "vendor")
    arguments = parser.parse_args(argv)
    try:
        verify_assets(arguments.lock, arguments.vendor_root)
    except VendorAssetError as error:
        parser.exit(1, "vendor asset verification failed: {}\n".format(error))
    return 0


if __name__ == "__main__":
    sys.exit(main())
