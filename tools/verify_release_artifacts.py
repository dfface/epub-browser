#!/usr/bin/env python3
"""Verify release artifacts and rebuild an sdist without package indexes."""

import argparse
import hashlib
import os
import re
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from tools.sync_vendor_assets import VendorAssetError, load_lock  # noqa: E402


class ReleaseArtifactError(Exception):
    """A release artifact is incomplete, altered, or unsafe to rebuild."""


DRIVE_LIKE_SEGMENT = re.compile(r"^[A-Za-z]:")


def _canonical_member_name(
    value: str,
    *,
    is_directory: bool,
    directory_trailing_slash: bool,
) -> str:
    """Return one canonical POSIX archive name or reject every path alias."""
    if not isinstance(value, str) or not value or "\x00" in value or "\\" in value:
        raise ReleaseArtifactError("archive contains a non-canonical member name")
    if value.startswith("/"):
        raise ReleaseArtifactError("archive contains a non-canonical member name")
    if is_directory and directory_trailing_slash:
        if not value.endswith("/"):
            raise ReleaseArtifactError("archive contains a non-canonical member name")
        core = value[:-1]
    else:
        if value.endswith("/"):
            raise ReleaseArtifactError("archive contains a non-canonical member name")
        core = value
    parts = core.split("/")
    if (
        not parts
        or any(part in ("", ".", "..") for part in parts)
        or any(DRIVE_LIKE_SEGMENT.match(part) for part in parts)
        or "/".join(parts) != core
    ):
        raise ReleaseArtifactError("archive contains a non-canonical member name")
    return core


def _sha256_stream(stream) -> str:
    digest = hashlib.sha256()
    for chunk in iter(lambda: stream.read(64 * 1024), b""):
        digest.update(chunk)
    return digest.hexdigest()


def _locked_vendor_digests(lock_path: Path):
    lock = load_lock(lock_path)
    expected = {
        item.target: item.sha256
        for package in lock.packages
        for item in package.files
    }
    expected.update(
        {
            item.target: item.sha256
            for package in lock.packages
            for item in package.supplemental_license_files
        }
    )
    return expected


def verify_wheel(wheel_path: Path, lock_path: Path, notices_path: Path) -> None:
    """Verify the exact vendor inventory, digests, and notices in one wheel."""
    expected = _locked_vendor_digests(lock_path)
    expected_names = {
        "epub_browser/assets/vendor/" + relative for relative in expected
    }
    try:
        with zipfile.ZipFile(wheel_path) as archive:
            members = archive.infolist()
            canonical_members = {}
            for member in members:
                raw_name = getattr(member, "orig_filename", member.filename)
                canonical = _canonical_member_name(
                    raw_name,
                    is_directory=member.is_dir(),
                    directory_trailing_slash=True,
                )
                if canonical in canonical_members:
                    raise ReleaseArtifactError(
                        "wheel contains duplicate canonical members"
                    )
                canonical_members[canonical] = member
            names = set(canonical_members)
            actual_names = {
                name
                for name, member in canonical_members.items()
                if not member.is_dir()
                and name.startswith("epub_browser/assets/vendor/")
            }
            if actual_names != expected_names:
                missing = sorted(expected_names - actual_names)
                extra = sorted(actual_names - expected_names)
                raise ReleaseArtifactError(
                    "wheel vendor inventory mismatch; missing={} extra={}".format(
                        missing, extra
                    )
                )
            for relative, expected_digest in expected.items():
                name = "epub_browser/assets/vendor/" + relative
                with archive.open(canonical_members[name]) as member:
                    actual_digest = _sha256_stream(member)
                if actual_digest != expected_digest:
                    raise ReleaseArtifactError(
                        "wheel vendor digest mismatch: {}".format(relative)
                    )
            notice_names = sorted(
                name for name in names if name.endswith("/THIRD_PARTY_NOTICES.md")
            )
            if not notice_names:
                raise ReleaseArtifactError(
                    "wheel is missing THIRD_PARTY_NOTICES.md"
                )
            expected_notice = notices_path.read_bytes()
            for name in notice_names:
                if archive.read(canonical_members[name]) != expected_notice:
                    raise ReleaseArtifactError(
                        "wheel contains altered THIRD_PARTY_NOTICES.md"
                    )
    except (OSError, zipfile.BadZipFile) as error:
        raise ReleaseArtifactError(
            "cannot inspect wheel {}: {}".format(wheel_path, error)
        ) from error


def _safe_sdist_members(archive: tarfile.TarFile):
    members = archive.getmembers()
    canonical_members = {}
    roots = set()
    for member in members:
        canonical = _canonical_member_name(
            member.name,
            is_directory=member.isdir(),
            directory_trailing_slash=False,
        )
        if canonical in canonical_members:
            raise ReleaseArtifactError("sdist contains duplicate canonical members")
        canonical_members[canonical] = member
        roots.add(canonical.split("/", 1)[0])
        if not member.isfile() and not member.isdir():
            raise ReleaseArtifactError("sdist contains a linked or special entry")
    if len(roots) != 1:
        raise ReleaseArtifactError("sdist must contain exactly one top-level directory")
    return members, next(iter(roots))


def verify_sdist(
    sdist_path: Path,
    lock_path: Path,
    notices_path: Path,
    sync_tool_path: Path,
) -> str:
    """Verify the complete offline-build input inventory in one sdist."""
    expected = _locked_vendor_digests(lock_path)
    try:
        with tarfile.open(sdist_path, mode="r:gz") as archive:
            members, root = _safe_sdist_members(archive)
            regular = {member.name: member for member in members if member.isfile()}
            prefix = root + "/"
            expected_vendor = {
                prefix + "epub_browser/assets/vendor/" + relative
                for relative in expected
            }
            actual_vendor = {
                name
                for name in regular
                if name.startswith(prefix + "epub_browser/assets/vendor/")
            }
            if actual_vendor != expected_vendor:
                missing = sorted(expected_vendor - actual_vendor)
                extra = sorted(actual_vendor - expected_vendor)
                raise ReleaseArtifactError(
                    "sdist vendor inventory mismatch; missing={} extra={}".format(
                        missing, extra
                    )
                )
            for relative, expected_digest in expected.items():
                name = prefix + "epub_browser/assets/vendor/" + relative
                stream = archive.extractfile(regular[name])
                if stream is None:
                    raise ReleaseArtifactError("cannot read sdist member " + name)
                with stream:
                    actual_digest = _sha256_stream(stream)
                if actual_digest != expected_digest:
                    raise ReleaseArtifactError(
                        "sdist vendor digest mismatch: {}".format(relative)
                    )
            required = {
                prefix + "third_party/assets.lock.json": lock_path.read_bytes(),
                prefix + "THIRD_PARTY_NOTICES.md": notices_path.read_bytes(),
                prefix + "tools/sync_vendor_assets.py": sync_tool_path.read_bytes(),
            }
            for name, expected_bytes in required.items():
                member = regular.get(name)
                if member is None:
                    raise ReleaseArtifactError("sdist is missing " + name[len(prefix):])
                stream = archive.extractfile(member)
                if stream is None:
                    raise ReleaseArtifactError("cannot read sdist member " + name)
                with stream:
                    actual_bytes = stream.read()
                if actual_bytes != expected_bytes:
                    raise ReleaseArtifactError(
                        "sdist contains altered " + name[len(prefix):]
                    )
            return root
    except (OSError, tarfile.TarError) as error:
        raise ReleaseArtifactError(
            "cannot inspect sdist {}: {}".format(sdist_path, error)
        ) from error


def _extract_verified_sdist(sdist_path: Path, destination: Path) -> Path:
    with tarfile.open(sdist_path, mode="r:gz") as archive:
        members, root = _safe_sdist_members(archive)
        archive.extractall(destination, members=members)
    return destination / root


def verify_release_artifacts(
    wheel_path: Path,
    lock_path: Path,
    notices_path: Path,
    sync_tool_path: Path,
    sdist_path=None,
    rebuilt_wheel_dir=None,
) -> None:
    """Verify a direct wheel and optionally rebuild and compare an sdist."""
    verify_wheel(wheel_path, lock_path, notices_path)
    print("direct wheel verified: {}".format(wheel_path))
    if sdist_path is None:
        return
    verify_sdist(sdist_path, lock_path, notices_path, sync_tool_path)
    with tempfile.TemporaryDirectory(prefix="epub-browser-sdist-") as directory:
        temporary_root = Path(directory)
        source_root = _extract_verified_sdist(sdist_path, temporary_root / "source")
        if rebuilt_wheel_dir is None:
            output_dir = temporary_root / "wheel"
        else:
            output_dir = rebuilt_wheel_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        environment = os.environ.copy()
        environment.update(
            {
                "PIP_NO_INDEX": "1",
                "PIP_DISABLE_PIP_VERSION_CHECK": "1",
            }
        )
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "build",
                "--wheel",
                "--no-isolation",
                "--outdir",
                str(output_dir),
            ],
            cwd=source_root,
            env=environment,
            text=True,
            capture_output=True,
        )
        if completed.returncode != 0:
            raise ReleaseArtifactError(
                "offline sdist wheel build failed:\n{}".format(completed.stderr)
            )
        rebuilt = sorted(output_dir.glob("*.whl"))
        if len(rebuilt) != 1:
            raise ReleaseArtifactError("offline sdist build did not produce one wheel")
        verify_wheel(rebuilt[0], lock_path, notices_path)
        print("offline sdist wheel verified: {}".format(rebuilt[0]))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--sdist", type=Path)
    parser.add_argument("--rebuilt-wheel-dir", type=Path)
    parser.add_argument(
        "--lock",
        type=Path,
        default=REPOSITORY_ROOT / "third_party" / "assets.lock.json",
    )
    parser.add_argument(
        "--notices",
        type=Path,
        default=REPOSITORY_ROOT / "THIRD_PARTY_NOTICES.md",
    )
    parser.add_argument(
        "--sync-tool",
        type=Path,
        default=REPOSITORY_ROOT / "tools" / "sync_vendor_assets.py",
    )
    arguments = parser.parse_args(argv)
    try:
        verify_release_artifacts(
            wheel_path=arguments.wheel,
            lock_path=arguments.lock,
            notices_path=arguments.notices,
            sync_tool_path=arguments.sync_tool,
            sdist_path=arguments.sdist,
            rebuilt_wheel_dir=arguments.rebuilt_wheel_dir,
        )
    except (OSError, ReleaseArtifactError, VendorAssetError) as error:
        parser.exit(1, "release artifact verification failed: {}\n".format(error))
    return 0


if __name__ == "__main__":
    sys.exit(main())
