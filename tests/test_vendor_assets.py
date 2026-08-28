import gzip
import hashlib
import io
import json
import os
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from urllib.request import Request

from tools import sync_vendor_assets
from tools.sync_vendor_assets import (
    VendorAssetError,
    clean_assets,
    fetch_assets,
    load_lock,
    verify_assets,
)


class VendorAssetTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.directory = Path(self.temporary_directory.name)
        self.lock_path, self.vendor_root = self.fixture_lock(
            {"pkg/LICENSE": b"license", "pkg/file.js": b"asset"}
        )

    def test_fetch_rejects_traversal_and_links(self):
        """Unsafe or linked archive entries must never reach the vendor tree."""
        clean_assets(self.lock_path, self.vendor_root)
        for member in ("../escape.js", "/escape.js", "package/link"):
            with self.subTest(member=member):
                archive = self.tar_archive(
                    [
                        ("LICENSE", b"license", "file"),
                        ("file.js", b"asset", "file"),
                        (
                            member,
                            b"payload",
                            "symlink" if member.endswith("link") else "file",
                        ),
                    ]
                )
                with self.assertRaisesRegex(VendorAssetError, "unsafe|unsupported"):
                    fetch_assets(
                        self.lock_for_archive(archive),
                        self.vendor_root,
                        opener=self.opener(archive),
                    )

    def test_clean_removes_only_locked_files(self):
        """Cleaning must preserve content that is not owned by the current lock."""
        unknown = self.vendor_root / "manual.txt"
        unknown.write_text("keep", encoding="utf-8")

        clean_assets(self.lock_path, self.vendor_root)

        self.assertTrue(unknown.is_file())
        self.assertFalse((self.vendor_root / "pkg/LICENSE").exists())
        self.assertFalse((self.vendor_root / "pkg/file.js").exists())

    def test_fetch_installs_only_allowlisted_files_and_verifies(self):
        """A valid archive must hydrate the exact locked tree, ignoring other regular files."""
        clean_assets(self.lock_path, self.vendor_root)
        archive = self.tar_archive(
            [
                ("LICENSE", b"license", "file"),
                ("file.js", b"asset", "file"),
                ("not-installed.txt", b"upstream extra", "file"),
            ]
        )

        fetch_assets(
            self.lock_for_archive(archive),
            self.vendor_root,
            opener=self.opener(archive),
        )

        verify_assets(self.lock_path, self.vendor_root)
        self.assertFalse((self.vendor_root / "not-installed.txt").exists())

    def test_fetch_is_offline_when_the_locked_tree_is_already_correct(self):
        """Removing the early verification would make an idempotent fetch contact upstream."""
        def reject_network(*args, **kwargs):
            raise AssertionError("network must not be used")

        fetch_assets(self.lock_path, self.vendor_root, opener=reject_network)

    def test_fetch_rejects_total_expansion_beyond_the_locked_limit(self):
        """Ignoring uninstalled members in the expansion total would permit archive bombs."""
        clean_assets(self.lock_path, self.vendor_root)
        archive = self.tar_archive(
            [
                ("LICENSE", b"license", "file"),
                ("file.js", b"asset", "file"),
                ("large-ignored.bin", b"x" * 4096, "file"),
            ]
        )
        lock_path = self.lock_for_archive(archive, max_expanded_bytes=4096)

        with self.assertRaisesRegex(VendorAssetError, "max_expanded_bytes"):
            fetch_assets(lock_path, self.vendor_root, opener=self.opener(archive))

    def test_fetch_rejects_oversized_member_from_header_without_reading_body(self):
        """The expansion guard must fire before streaming an oversized member body."""
        clean_assets(self.lock_path, self.vendor_root)
        info = tarfile.TarInfo("oversized.bin")
        info.size = 1 << 30
        archive = gzip.compress(info.tobuf(format=tarfile.USTAR_FORMAT))

        with self.assertRaisesRegex(VendorAssetError, "max_expanded_bytes"):
            fetch_assets(
                self.lock_for_archive(archive, max_expanded_bytes=2048),
                self.vendor_root,
                opener=self.opener(archive),
            )

    def test_fetch_preflights_oversized_extension_headers_before_their_bodies(self):
        """PAX and GNU extension payloads must be bounded before tarfile sees them."""
        clean_assets(self.lock_path, self.vendor_root)
        for extension_type in (
            tarfile.XHDTYPE,
            tarfile.XGLTYPE,
            tarfile.GNUTYPE_LONGNAME,
            tarfile.GNUTYPE_SPARSE,
        ):
            with self.subTest(extension_type=extension_type):
                info = tarfile.TarInfo("extension")
                info.type = extension_type
                info.size = 1 << 30
                archive = gzip.compress(info.tobuf(format=tarfile.USTAR_FORMAT))

                with self.assertRaisesRegex(VendorAssetError, "max_expanded_bytes"):
                    fetch_assets(
                        self.lock_for_archive(archive, max_expanded_bytes=2048),
                        self.vendor_root,
                        opener=self.opener(archive),
                    )

    def test_fetch_supports_bounded_pax_and_gnu_long_name_records(self):
        """Safe extension metadata in ordinary npm-style tarballs must remain usable."""
        long_name = "nested/" + "a" * 120 + ".txt"
        for archive_format in (tarfile.PAX_FORMAT, tarfile.GNU_FORMAT):
            with self.subTest(archive_format=archive_format):
                clean_assets(self.lock_path, self.vendor_root)
                archive = self.tar_archive(
                    [
                        ("LICENSE", b"license", "file"),
                        ("file.js", b"asset", "file"),
                        (long_name, b"ignored", "file"),
                    ],
                    archive_format=archive_format,
                )

                fetch_assets(
                    self.lock_for_archive(archive),
                    self.vendor_root,
                    opener=self.opener(archive),
                )
                verify_assets(self.lock_path, self.vendor_root)

    def test_fetch_rejects_duplicate_normalized_archive_members(self):
        """Two archive entries must not compete for one normalized source path."""
        clean_assets(self.lock_path, self.vendor_root)
        archive = self.tar_archive(
            [
                ("LICENSE", b"license", "file"),
                ("file.js", b"asset", "file"),
                ("./file.js", b"asset", "file"),
            ]
        )

        with self.assertRaisesRegex(VendorAssetError, "duplicate"):
            fetch_assets(
                self.lock_for_archive(archive),
                self.vendor_root,
                opener=self.opener(archive),
            )

    def test_fetch_rejects_compressed_archive_over_the_locked_limit(self):
        """The response stream must stop once its compressed-byte budget is exhausted."""
        clean_assets(self.lock_path, self.vendor_root)
        archive = self.tar_archive(
            [("LICENSE", b"license", "file"), ("file.js", b"asset", "file")]
        )

        with self.assertRaisesRegex(VendorAssetError, "max_bytes"):
            fetch_assets(
                self.lock_for_archive(archive, max_bytes=len(archive) - 1),
                self.vendor_root,
                opener=self.opener(archive),
            )

    def test_fetch_rejects_archive_file_and_missing_license_failures(self):
        """No archive may install unless its container, files, and license all match."""
        clean_assets(self.lock_path, self.vendor_root)
        valid_archive = self.tar_archive(
            [("LICENSE", b"license", "file"), ("file.js", b"asset", "file")]
        )
        wrong_archive_lock = self.lock_for_archive(valid_archive)
        document = json.loads(wrong_archive_lock.read_text(encoding="utf-8"))
        document["packages"][0]["archive"]["sha256"] = "f" * 64
        wrong_archive_lock.write_text(json.dumps(document), encoding="utf-8")
        with self.assertRaisesRegex(VendorAssetError, "archive SHA-256"):
            fetch_assets(wrong_archive_lock, self.vendor_root, opener=self.opener(valid_archive))

        changed_file_archive = self.tar_archive(
            [("LICENSE", b"license", "file"), ("file.js", b"changed", "file")]
        )
        with self.assertRaisesRegex(VendorAssetError, "file.js SHA-256"):
            fetch_assets(
                self.lock_for_archive(changed_file_archive),
                self.vendor_root,
                opener=self.opener(changed_file_archive),
            )

        missing_license_archive = self.tar_archive([("file.js", b"asset", "file")])
        with self.assertRaisesRegex(VendorAssetError, "missing.*LICENSE"):
            fetch_assets(
                self.lock_for_archive(missing_license_archive),
                self.vendor_root,
                opener=self.opener(missing_license_archive),
            )

    def test_fetch_rejects_insecure_sources_redirects_and_unknown_archive_kinds(self):
        """Only HTTPS npm tarballs whose final URL stays HTTPS are fetchable."""
        clean_assets(self.lock_path, self.vendor_root)
        archive = self.tar_archive(
            [("LICENSE", b"license", "file"), ("file.js", b"asset", "file")]
        )

        insecure_lock = self.changed_lock(
            self.lock_for_archive(archive),
            "insecure.lock.json",
            lambda package: package["source"].update(
                {"url": "http://registry.example.test/example.tgz"}
            ),
        )
        with self.assertRaisesRegex(VendorAssetError, "HTTPS"):
            fetch_assets(insecure_lock, self.vendor_root, opener=self.opener(archive))

        with self.assertRaisesRegex(VendorAssetError, "redirected"):
            fetch_assets(
                self.lock_for_archive(archive),
                self.vendor_root,
                opener=self.opener(archive, final_url="http://mirror.example.test/file.tgz"),
            )

        unknown_kind_lock = self.changed_lock(
            self.lock_for_archive(archive),
            "unknown-kind.lock.json",
            lambda package: package["source"].update({"kind": "release-zip"}),
        )
        with self.assertRaisesRegex(VendorAssetError, "unsupported archive kind"):
            fetch_assets(unknown_kind_lock, self.vendor_root, opener=self.opener(archive))

    def test_fetch_validates_source_contract_before_idempotent_return(self):
        """A correct local tree must not hide an insecure or unsupported lock source."""
        insecure_lock = self.changed_lock(
            self.lock_path,
            "installed-insecure.lock.json",
            lambda package: package["source"].update(
                {"url": "http://registry.example.test/example.tgz"}
            ),
        )
        with self.assertRaisesRegex(VendorAssetError, "HTTPS"):
            fetch_assets(insecure_lock, self.vendor_root, opener=self.opener(b""))

        unknown_kind_lock = self.changed_lock(
            self.lock_path,
            "installed-unknown-kind.lock.json",
            lambda package: package["source"].update({"kind": "release-zip"}),
        )
        with self.assertRaisesRegex(VendorAssetError, "unsupported archive kind"):
            fetch_assets(unknown_kind_lock, self.vendor_root, opener=self.opener(b""))

    def test_load_lock_rejects_unsupported_archive_kind(self):
        """Unsupported archive formats must be invalid in the shared lock contract."""
        lock_path = self.changed_lock(
            self.lock_path,
            "load-unknown-kind.lock.json",
            lambda package: package["source"].update({"kind": "release-zip"}),
        )

        with self.assertRaisesRegex(VendorAssetError, "unsupported archive kind"):
            load_lock(lock_path)

    def test_verify_rejects_unsupported_archive_kind(self):
        """Offline verification must not bless an installed tree from an unknown format."""
        lock_path = self.changed_lock(
            self.lock_path,
            "verify-unknown-kind.lock.json",
            lambda package: package["source"].update({"kind": "release-zip"}),
        )

        with self.assertRaisesRegex(VendorAssetError, "unsupported archive kind"):
            verify_assets(lock_path, self.vendor_root)

    def test_clean_rejects_unsupported_archive_kind_without_removing_files(self):
        """Clean must validate the common lock before unlinking any managed target."""
        lock_path = self.changed_lock(
            self.lock_path,
            "clean-unknown-kind.lock.json",
            lambda package: package["source"].update({"kind": "release-zip"}),
        )

        with self.assertRaisesRegex(VendorAssetError, "unsupported archive kind"):
            clean_assets(lock_path, self.vendor_root)

        self.assertEqual((self.vendor_root / "pkg/LICENSE").read_bytes(), b"license")
        self.assertEqual((self.vendor_root / "pkg/file.js").read_bytes(), b"asset")

    def test_redirect_handler_rejects_an_intermediate_https_downgrade(self):
        """Every redirect hop must remain HTTPS even when a later final URL is secure."""
        handler = sync_vendor_assets.HTTPSOnlyRedirectHandler()

        with self.assertRaisesRegex(VendorAssetError, "redirected"):
            handler.redirect_request(
                Request("https://registry.example.test/archive.tgz"),
                None,
                302,
                "Found",
                {},
                "http://mirror.example.test/archive.tgz",
            )

    def test_fetch_rejects_hardlinks_devices_and_fifos(self):
        """No special tar entry type may be accepted as an installable artifact."""
        clean_assets(self.lock_path, self.vendor_root)
        for kind in ("hardlink", "device", "fifo"):
            with self.subTest(kind=kind):
                archive = self.tar_archive([("special", b"", kind)])
                with self.assertRaisesRegex(VendorAssetError, "unsupported entry"):
                    fetch_assets(
                        self.lock_for_archive(archive),
                        self.vendor_root,
                        opener=self.opener(archive),
                    )

    def test_fetch_rejects_unknown_existing_content_before_installing(self):
        """A failed exact-inventory check must leave every existing locked file unchanged."""
        unknown = self.vendor_root / "manual.txt"
        unknown.write_text("keep", encoding="utf-8")
        old_license = (self.vendor_root / "pkg/LICENSE").read_bytes()
        old_asset = (self.vendor_root / "pkg/file.js").read_bytes()
        new_files = {"pkg/LICENSE": b"new license", "pkg/file.js": b"new asset"}
        self.write_lock(files=new_files)
        archive = self.tar_archive(
            [("LICENSE", b"new license", "file"), ("file.js", b"new asset", "file")]
        )

        with self.assertRaisesRegex(VendorAssetError, "unexpected|file set"):
            fetch_assets(
                self.lock_for_archive(archive),
                self.vendor_root,
                opener=self.opener(archive),
            )

        self.assertEqual((self.vendor_root / "pkg/LICENSE").read_bytes(), old_license)
        self.assertEqual((self.vendor_root / "pkg/file.js").read_bytes(), old_asset)
        self.assertEqual(unknown.read_text(encoding="utf-8"), "keep")

    def test_fetch_and_clean_refuse_symlinked_target_parents(self):
        """Managed operations must not follow a directory symlink outside the vendor root."""
        clean_assets(self.lock_path, self.vendor_root)
        outside = self.directory / "outside"
        outside.mkdir()
        outside_license = outside / "LICENSE"
        outside_asset = outside / "file.js"
        outside_license.write_bytes(b"outside license")
        outside_asset.write_bytes(b"outside asset")
        (self.vendor_root / "pkg").symlink_to(outside, target_is_directory=True)
        archive = self.tar_archive(
            [("LICENSE", b"license", "file"), ("file.js", b"asset", "file")]
        )

        with self.assertRaisesRegex(VendorAssetError, "symbolic link"):
            fetch_assets(
                self.lock_for_archive(archive),
                self.vendor_root,
                opener=self.opener(archive),
            )
        self.assertEqual(outside_license.read_bytes(), b"outside license")
        self.assertEqual(outside_asset.read_bytes(), b"outside asset")

        with self.assertRaisesRegex(VendorAssetError, "symbolic link"):
            clean_assets(self.lock_path, self.vendor_root)
        self.assertEqual(outside_license.read_bytes(), b"outside license")
        self.assertEqual(outside_asset.read_bytes(), b"outside asset")

    def test_clean_refuses_a_directory_at_a_locked_file_path(self):
        """Clean must report and preserve an unknown directory masquerading as a locked file."""
        (self.vendor_root / "pkg/LICENSE").unlink()
        (self.vendor_root / "pkg/LICENSE").mkdir()

        with self.assertRaisesRegex(VendorAssetError, "clean failed"):
            clean_assets(self.lock_path, self.vendor_root)

        self.assertTrue((self.vendor_root / "pkg/LICENSE").is_dir())

    def test_load_lock_returns_typed_packages_for_a_valid_manifest(self):
        """Removing a required package field must make this manifest invalid."""
        lock_path, _ = self.fixture_lock({"pkg/LICENSE": b"license", "pkg/file.js": b"asset"})

        lock = load_lock(lock_path)

        self.assertEqual(lock.schema, 1)
        self.assertEqual(lock.packages[0].name, "example")
        self.assertEqual(lock.packages[0].files[1].target, "pkg/file.js")

    def test_lock_rejects_unknown_fields_and_duplicate_package_names(self):
        """Accepting unrecognized fields or duplicate packages could hide a bad lock edit."""
        lock_path, _ = self.fixture_lock({"pkg/LICENSE": b"license", "pkg/file.js": b"asset"})
        document = json.loads(lock_path.read_text(encoding="utf-8"))
        document["unexpected"] = True
        lock_path.write_text(json.dumps(document), encoding="utf-8")
        with self.assertRaisesRegex(VendorAssetError, "unknown"):
            load_lock(lock_path)

        document.pop("unexpected")
        document["packages"].append(document["packages"][0])
        lock_path.write_text(json.dumps(document), encoding="utf-8")
        with self.assertRaisesRegex(VendorAssetError, "duplicate package"):
            load_lock(lock_path)

    def test_lock_rejects_duplicate_targets_and_parent_paths(self):
        """Dropping canonical-path validation would let a lock overwrite files outside the root."""
        lock_path, _ = self.fixture_lock({"pkg/LICENSE": b"license", "pkg/file.js": b"asset"})
        document = json.loads(lock_path.read_text(encoding="utf-8"))
        document["packages"][0]["files"].append(document["packages"][0]["files"][1])
        lock_path.write_text(json.dumps(document), encoding="utf-8")
        with self.assertRaisesRegex(VendorAssetError, "duplicate"):
            load_lock(lock_path)

        for target in ("../escape.js", "/absolute.js", "pkg/../../escape.js", "pkg/./file.js"):
            with self.subTest(target=target):
                lock_path = self.write_lock(targets=[target, target])
                with self.assertRaises(VendorAssetError):
                    load_lock(lock_path)

    def test_verify_rejects_digest_mismatch(self):
        """A changed installed browser asset must not verify against its locked digest."""
        lock_path, root = self.fixture_lock({"pkg/LICENSE": b"license", "pkg/file.js": b"expected"})
        (root / "pkg/file.js").write_bytes(b"changed")

        with self.assertRaisesRegex(VendorAssetError, "pkg/file.js.*SHA-256"):
            verify_assets(lock_path, root)

    def test_verify_rejects_missing_required_license_file(self):
        """A release missing its locked license must not pass despite intact code files."""
        lock_path, root = self.fixture_lock({"pkg/LICENSE": b"license", "pkg/file.js": b"asset"})
        (root / "pkg/LICENSE").unlink()

        with self.assertRaisesRegex(VendorAssetError, "file set"):
            verify_assets(lock_path, root)

    def test_verify_rejects_extra_generated_file(self):
        """An unreviewed file under the managed root must make offline verification fail."""
        lock_path, root = self.fixture_lock({"pkg/LICENSE": b"license", "pkg/file.js": b"asset"})
        (root / "pkg/extra.js").write_bytes(b"unreviewed")

        with self.assertRaisesRegex(VendorAssetError, "file set"):
            verify_assets(lock_path, root)

    def test_verify_rejects_dangling_and_directory_symlinks_without_following_them(self):
        """A symlink must not hide unexpected content outside the managed tree."""
        lock_path, root = self.fixture_lock({"pkg/LICENSE": b"license", "pkg/file.js": b"asset"})
        (root / "pkg/dangling").symlink_to(root / "outside")

        with self.assertRaisesRegex(VendorAssetError, "symbolic link"):
            verify_assets(lock_path, root)

        (root / "pkg/dangling").unlink()
        outside = self.directory / "outside"
        outside.mkdir()
        (outside / "unlocked.js").write_bytes(b"not managed")
        (root / "pkg/linked-directory").symlink_to(outside, target_is_directory=True)

        with self.assertRaisesRegex(VendorAssetError, "symbolic link"):
            verify_assets(lock_path, root)

    @unittest.skipUnless(hasattr(os, "mkfifo"), "platform does not support FIFOs")
    def test_verify_rejects_special_files(self):
        """A FIFO must not be silently omitted from the managed inventory."""
        lock_path, root = self.fixture_lock({"pkg/LICENSE": b"license", "pkg/file.js": b"asset"})
        os.mkfifo(root / "pkg/pipe")

        with self.assertRaisesRegex(VendorAssetError, "unsupported entry"):
            verify_assets(lock_path, root)

    def test_verify_rejects_unowned_empty_directories(self):
        """Only directories needed to contain locked files may exist in the vendor root."""
        lock_path, root = self.fixture_lock({"pkg/LICENSE": b"license", "pkg/file.js": b"asset"})
        (root / "unowned").mkdir()

        with self.assertRaisesRegex(VendorAssetError, "unexpected directory"):
            verify_assets(lock_path, root)

    def test_verify_command_accepts_explicit_lock_and_vendor_root(self):
        """The CLI must verify the same caller-supplied fixture as the Python API."""
        root = self.directory / "vendor"
        lock_path, root = self.fixture_lock(
            {"pkg/LICENSE": b"license", "pkg/file.js": b"asset"}, root=root
        )
        completed = subprocess.run(
            [sys.executable, "tools/sync_vendor_assets.py", "verify", "--lock", str(lock_path), "--vendor-root", str(root)],
            cwd=Path(__file__).parents[1],
            capture_output=True,
            text=True,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_fetch_and_clean_commands_accept_explicit_lock_and_vendor_root(self):
        """The CLI must expose both mutating APIs with caller-supplied paths."""
        repository_root = Path(__file__).parents[1]
        clean = subprocess.run(
            [
                sys.executable,
                "tools/sync_vendor_assets.py",
                "clean",
                "--lock",
                str(self.lock_path),
                "--vendor-root",
                str(self.vendor_root),
            ],
            cwd=repository_root,
            capture_output=True,
            text=True,
        )
        self.assertEqual(clean.returncode, 0, clean.stderr)
        self.assertFalse((self.vendor_root / "pkg/file.js").exists())

        empty_lock = self.directory / "empty.lock.json"
        empty_lock.write_text('{"schema": 1, "packages": []}', encoding="utf-8")
        fetch = subprocess.run(
            [
                sys.executable,
                "tools/sync_vendor_assets.py",
                "fetch",
                "--lock",
                str(empty_lock),
                "--vendor-root",
                str(self.directory / "empty-vendor"),
            ],
            cwd=repository_root,
            capture_output=True,
            text=True,
        )
        self.assertEqual(fetch.returncode, 0, fetch.stderr)

    def fixture_lock(self, files, root=None):
        root = root or self.directory / "vendor"
        for target, contents in files.items():
            path = root / target
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(contents)
        return self.write_lock(files=files), root

    def write_lock(self, files=None, targets=None):
        files = files or {target: b"asset" for target in targets}
        entries = [
            {
                "source": target.removeprefix("pkg/"),
                "target": target,
                "sha256": hashlib.sha256(contents).hexdigest(),
            }
            for target, contents in sorted(files.items())
        ]
        document = {
            "schema": 1,
            "packages": [
                {
                    "name": "example",
                    "version": "1.0.0",
                    "source": {"kind": "npm-tarball", "url": "https://registry.example.test/example-1.0.0.tgz"},
                    "archive": {
                        "sha256": "0" * 64,
                        "max_bytes": 1024,
                        "max_expanded_bytes": 32 * 1024,
                    },
                    "license": {"spdx": "MIT", "files": ["LICENSE"]},
                    "files": entries,
                }
            ],
        }
        lock_path = self.directory / "assets.lock.json"
        lock_path.write_text(json.dumps(document), encoding="utf-8")
        return lock_path

    def lock_for_archive(self, archive, max_expanded_bytes=None, max_bytes=None):
        document = json.loads(self.lock_path.read_text(encoding="utf-8"))
        document["packages"][0]["archive"]["sha256"] = hashlib.sha256(archive).hexdigest()
        document["packages"][0]["archive"]["max_bytes"] = (
            len(archive) + 1 if max_bytes is None else max_bytes
        )
        if max_expanded_bytes is not None:
            document["packages"][0]["archive"]["max_expanded_bytes"] = max_expanded_bytes
        lock_path = self.directory / "archive.lock.json"
        lock_path.write_text(json.dumps(document), encoding="utf-8")
        return lock_path

    def changed_lock(self, source, name, change):
        document = json.loads(source.read_text(encoding="utf-8"))
        change(document["packages"][0])
        destination = self.directory / name
        destination.write_text(json.dumps(document), encoding="utf-8")
        return destination

    @staticmethod
    def tar_fixture(member, contents, symlink=False):
        return VendorAssetTests.tar_archive(
            [(member, contents, "symlink" if symlink else "file")]
        )

    @staticmethod
    def tar_archive(entries, archive_format=tarfile.PAX_FORMAT):
        archive = io.BytesIO()
        with tarfile.open(
            fileobj=archive, mode="w:gz", format=archive_format
        ) as tar:
            for member, contents, kind in entries:
                info = tarfile.TarInfo(member)
                if kind == "symlink":
                    info.type = tarfile.SYMTYPE
                    info.linkname = "../outside"
                    tar.addfile(info)
                elif kind == "hardlink":
                    info.type = tarfile.LNKTYPE
                    info.linkname = "LICENSE"
                    tar.addfile(info)
                elif kind == "device":
                    info.type = tarfile.CHRTYPE
                    tar.addfile(info)
                elif kind == "fifo":
                    info.type = tarfile.FIFOTYPE
                    tar.addfile(info)
                else:
                    info.size = len(contents)
                    tar.addfile(info, io.BytesIO(contents))
        return archive.getvalue()

    @staticmethod
    def opener(contents, final_url="https://registry.example.test/example-1.0.0.tgz"):
        class Response(io.BytesIO):
            def geturl(self):
                return final_url

        return lambda *args, **kwargs: Response(contents)


if __name__ == "__main__":
    unittest.main()
