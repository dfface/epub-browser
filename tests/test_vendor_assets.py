import copy
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
import warnings
import zipfile
from contextlib import redirect_stdout
from pathlib import Path
from urllib.request import Request

from tools import sync_vendor_assets
from tools import verify_release_artifacts as release_artifacts
from tools.sync_vendor_assets import (
    VendorAssetError,
    clean_assets,
    fetch_assets,
    load_lock,
    verify_assets,
)
from tools.verify_release_artifacts import (
    ReleaseArtifactError,
    verify_release_artifacts,
    verify_sdist,
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

        with self.assertRaisesRegex(VendorAssetError, "final URL"):
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

    def test_all_offline_commands_reject_insecure_or_malformed_source_urls(self):
        """Every lock consumer must share strict HTTPS source validation."""

        def reject_network(*args, **kwargs):
            raise AssertionError("invalid locks must not reach the network")

        operations = (
            ("load", lambda path: load_lock(path)),
            ("verify", lambda path: verify_assets(path, self.vendor_root)),
            ("clean", lambda path: clean_assets(path, self.vendor_root)),
            (
                "fetch",
                lambda path: fetch_assets(
                    path,
                    self.vendor_root,
                    opener=reject_network,
                ),
            ),
        )
        for url in (
            "http://registry.example.test/example.tgz",
            "https://",
            "https://registry.example.test:invalid/example.tgz",
            "https://registry.example.test:/example.tgz",
            "https://user:password@registry.example.test/example.tgz",
            "https://registry.example.test/example.tgz\n",
            "https://registry.example.test\\evil/example.tgz",
            "https://registry.example.test/example\x00.tgz",
            "https://registry.example.test/example\x7f.tgz",
            "https://registry.example.test/example\x80.tgz",
            "https://registry.example.test/example\N{ZERO WIDTH SPACE}.tgz",
            "https://registry.example.test/example\N{EM SPACE}.tgz",
        ):
            lock_path = self.changed_lock(
                self.lock_path,
                "invalid-source-{}.lock.json".format(
                    hashlib.sha256(url.encode("utf-8")).hexdigest()
                ),
                lambda package, value=url: package["source"].update({"url": value}),
            )
            for operation_name, operation in operations:
                with self.subTest(operation=operation_name, url=url):
                    for relative, contents in (
                        ("pkg/LICENSE", b"license"),
                        ("pkg/file.js", b"asset"),
                    ):
                        destination = self.vendor_root / relative
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        destination.write_bytes(contents)
                    with self.assertRaisesRegex(VendorAssetError, "HTTPS URL"):
                        operation(lock_path)
                    self.assertTrue((self.vendor_root / "pkg/LICENSE").is_file())
                    self.assertTrue((self.vendor_root / "pkg/file.js").is_file())

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

        for redirected_url in (
            "http://mirror.example.test/archive.tgz",
            "https://mirror.example.test\\evil/archive.tgz",
            "https://mirror.example.test:/archive.tgz",
            "https://mirror.example.test/archive\x7f.tgz",
            "https://mirror.example.test/archive\N{ZERO WIDTH SPACE}.tgz",
        ):
            with self.subTest(url=redirected_url):
                with self.assertRaisesRegex(VendorAssetError, "redirected"):
                    handler.redirect_request(
                        Request("https://registry.example.test/archive.tgz"),
                        None,
                        302,
                        "Found",
                        {},
                        redirected_url,
                    )

    def test_fetch_rejects_malformed_response_final_urls(self):
        """A downloader response must not bypass strict redirect URL validation."""
        archive = self.tar_archive(
            [("LICENSE", b"license", "file"), ("file.js", b"asset", "file")]
        )
        lock_path = self.lock_for_archive(archive)
        for final_url in (
            "https://mirror.example.test\\evil/archive.tgz",
            "https://mirror.example.test:/archive.tgz",
            "https://mirror.example.test/archive\x80.tgz",
            "https://mirror.example.test/archive\N{ZERO WIDTH SPACE}.tgz",
        ):
            with self.subTest(url=final_url):
                clean_assets(self.lock_path, self.vendor_root)
                with self.assertRaisesRegex(VendorAssetError, "final URL"):
                    fetch_assets(
                        lock_path,
                        self.vendor_root,
                        opener=self.opener(archive, final_url=final_url),
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

    def test_schema_two_records_release_notice_metadata_and_runtime_consumers(self):
        """Every releasable package must identify its project, copyright, and consumers."""
        document = json.loads(self.lock_path.read_text(encoding="utf-8"))
        package = document["packages"][0]
        document["schema"] = 2
        package.update(
            {
                "upstream": "https://example.test/example",
                "copyright": ["Copyright (c) Example Authors"],
                "runtime_files": ["pkg/file.js"],
            }
        )
        self.lock_path.write_text(json.dumps(document), encoding="utf-8")

        lock = load_lock(self.lock_path)

        self.assertEqual(lock.schema, 2)
        self.assertEqual(lock.packages[0].upstream, "https://example.test/example")
        self.assertEqual(
            lock.packages[0].copyright,
            ("Copyright (c) Example Authors",),
        )
        self.assertEqual(lock.packages[0].runtime_files, ("pkg/file.js",))

    def test_schema_one_still_requires_an_archive_license_file(self):
        """Adding supplemental schema-two licenses must not weaken legacy locks."""
        document = json.loads(self.lock_path.read_text(encoding="utf-8"))
        document["packages"][0]["license"]["files"] = []
        self.lock_path.write_text(json.dumps(document), encoding="utf-8")

        with self.assertRaisesRegex(VendorAssetError, "license.files must not be empty"):
            load_lock(self.lock_path)

    def test_schema_two_rejects_unknown_runtime_consumers(self):
        """Notice metadata must not name a runtime file outside the locked inventory."""
        document = json.loads(self.lock_path.read_text(encoding="utf-8"))
        package = document["packages"][0]
        document["schema"] = 2
        package.update(
            {
                "upstream": "https://example.test/example",
                "copyright": ["Copyright (c) Example Authors"],
                "runtime_files": ["pkg/missing.js"],
            }
        )
        self.lock_path.write_text(json.dumps(document), encoding="utf-8")

        with self.assertRaisesRegex(VendorAssetError, "runtime_files.*locked target"):
            load_lock(self.lock_path)

    def test_schema_two_allows_two_versions_but_rejects_duplicate_identities(self):
        """Bundled dependency inventories may legitimately contain two exact versions."""
        document = json.loads(self.lock_path.read_text(encoding="utf-8"))
        first = document["packages"][0]
        document["schema"] = 2
        first.update(
            {
                "upstream": "https://example.test/example",
                "copyright": ["Copyright (c) Example Authors"],
                "runtime_files": ["pkg/file.js"],
            }
        )
        second = json.loads(json.dumps(first))
        second["version"] = "2.0.0"
        second["files"] = [
            {
                "source": "LICENSE",
                "target": "pkg-v2/LICENSE",
                "sha256": hashlib.sha256(b"license").hexdigest(),
            }
        ]
        second["runtime_files"] = ["pkg/file.js"]
        document["packages"].append(second)
        self.lock_path.write_text(json.dumps(document), encoding="utf-8")

        lock = load_lock(self.lock_path)

        self.assertEqual(
            [(package.name, package.version) for package in lock.packages],
            [("example", "1.0.0"), ("example", "2.0.0")],
        )
        document["packages"].append(second)
        self.lock_path.write_text(json.dumps(document), encoding="utf-8")
        with self.assertRaisesRegex(VendorAssetError, "duplicate package"):
            load_lock(self.lock_path)

    def test_schema_two_installs_digest_locked_supplemental_license_text(self):
        """An upstream license omitted from a distribution tarball remains generated and verified."""
        document = json.loads(self.lock_path.read_text(encoding="utf-8"))
        package = document["packages"][0]
        text = "Copyright (c) Upstream Authors\n\nPermission is hereby granted.\n"
        document["schema"] = 2
        package.update(
            {
                "upstream": "https://example.test/example",
                "copyright": ["Copyright (c) Example Authors"],
                "runtime_files": ["pkg/file.js"],
                "supplemental_license_files": [
                    {
                        "target": "pkg/UPSTREAM-LICENSE",
                        "sha256": hashlib.sha256(text.encode()).hexdigest(),
                        "text": text,
                        "upstream": "https://example.test/commit/LICENSE",
                    }
                ],
            }
        )
        self.lock_path.write_text(json.dumps(document), encoding="utf-8")
        clean_assets(self.lock_path, self.vendor_root)
        archive = self.tar_archive(
            [("LICENSE", b"license", "file"), ("file.js", b"asset", "file")]
        )

        fetch_assets(
            self.lock_for_archive(archive),
            self.vendor_root,
            opener=self.opener(archive),
        )

        self.assertEqual(
            (self.vendor_root / "pkg/UPSTREAM-LICENSE").read_text(encoding="utf-8"),
            text,
        )
        verify_assets(self.lock_for_archive(archive), self.vendor_root)

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

    def test_setup_packages_recursive_vendor_assets(self):
        """Dropping the recursive package-data rule would omit nested licenses and fonts."""
        repository_root = Path(__file__).parents[1]
        completed = subprocess.run(
            [sys.executable, "setup.py", "--version"],
            cwd=repository_root,
            text=True,
            capture_output=True,
            check=True,
        )

        self.assertRegex(completed.stdout.strip(), r"^\d+\.\d+\.\d+")
        self.assertIn(
            "assets/vendor/**/*",
            (repository_root / "setup.py").read_text(encoding="utf-8"),
        )

    def test_release_jobs_fetch_and_verify_before_build(self):
        """A release build must fail closed before packaging an incomplete vendor tree."""
        repository_root = Path(__file__).parents[1]
        for relative in (
            ".github/workflows/pypi.yml",
            ".github/workflows/gh-pages.yml",
            "Dockerfile",
        ):
            with self.subTest(path=relative):
                source = (repository_root / relative).read_text(encoding="utf-8")
                fetch = source.index("sync_vendor_assets.py fetch")
                verify = source.index("sync_vendor_assets.py verify")
                build = source.index("python -m build")
                self.assertLess(fetch, verify)
                self.assertLess(verify, build)

    def test_wheel_contains_complete_locked_vendor_inventory_and_notices(self):
        """A wheel must not drop deeply nested fonts, workers, or license notices."""
        repository_root = Path(__file__).parents[1]
        lock = json.loads(
            (repository_root / "third_party/assets.lock.json").read_text(
                encoding="utf-8"
            )
        )
        expected_vendor = {
            "epub_browser/assets/vendor/" + item["target"]
            for package in lock["packages"]
            for field in ("files", "supplemental_license_files")
            for item in package.get(field, [])
        }
        with tempfile.TemporaryDirectory() as directory:
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "build",
                    "--wheel",
                    "--no-isolation",
                    "--outdir",
                    directory,
                ],
                cwd=repository_root,
                text=True,
                capture_output=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            wheel = next(Path(directory).glob("*.whl"))
            with zipfile.ZipFile(wheel) as archive:
                names = set(archive.namelist())

        self.assertEqual(sorted(expected_vendor - names), [])
        self.assertTrue(
            any(name.endswith("/THIRD_PARTY_NOTICES.md") for name in names),
            "wheel is missing THIRD_PARTY_NOTICES.md",
        )

    def test_pypi_release_gate_rebuilds_sdist_before_upload(self):
        """PyPI must gate upload on a network-isolated rebuild and comparison."""
        repository_root = Path(__file__).parents[1]
        source = (repository_root / ".github/workflows/pypi.yml").read_text(
            encoding="utf-8"
        )

        direct = source.index("python -m build --wheel")
        sdist = source.index("python -m build --sdist")
        gate = source.index("verify_release_artifacts.py")
        upload = source.index("twine upload")
        self.assertLess(direct, gate)
        self.assertLess(sdist, gate)
        self.assertLess(gate, upload)
        self.assertIn(
            "docker build --tag epub-browser-release-builder:local", source
        )
        self.assertIn(
            "EPUB_BROWSER_RELEASE_BUILDER_IMAGE=epub-browser-release-builder:local",
            source,
        )
        self.assertIn("--network-isolation docker", source)
        self.assertIn(
            "--builder-image epub-browser-release-builder:local", source
        )

    def test_release_artifact_gate_fails_closed_without_network_isolation(self):
        """An sdist rebuild must never silently fall back to host networking."""
        repository_root = Path(__file__).parents[1]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            direct, sdist = self.build_release_artifacts(repository_root, root)
            completed = subprocess.run(
                [
                    sys.executable,
                    "tools/verify_release_artifacts.py",
                    "--wheel",
                    str(direct),
                    "--sdist",
                    str(sdist),
                ],
                cwd=repository_root,
                text=True,
                capture_output=True,
            )

        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("network isolation is required", completed.stderr)

    def test_release_artifact_gate_accepts_an_injected_isolation_runner(self):
        """Tests and embedding callers may supply an explicit isolation boundary."""
        repository_root = Path(__file__).parents[1]
        lock_path = repository_root / "third_party/assets.lock.json"
        notices_path = repository_root / "THIRD_PARTY_NOTICES.md"
        sync_tool_path = repository_root / "tools/sync_vendor_assets.py"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            direct, sdist = self.build_release_artifacts(repository_root, root)
            with redirect_stdout(io.StringIO()):
                verify_release_artifacts(
                    wheel_path=direct,
                    lock_path=lock_path,
                    notices_path=notices_path,
                    sync_tool_path=sync_tool_path,
                    sdist_path=sdist,
                    isolation_runner=self.local_build_runner,
                )

    def test_release_gate_rejects_preexisting_rebuilt_wheel_evidence(self):
        """A stale valid wheel must never satisfy a no-op sdist rebuild."""
        repository_root = Path(__file__).parents[1]
        lock_path = repository_root / "third_party/assets.lock.json"
        notices_path = repository_root / "THIRD_PARTY_NOTICES.md"
        sync_tool_path = repository_root / "tools/sync_vendor_assets.py"
        runner_called = False

        def no_op_runner(source_root, output_dir):
            nonlocal runner_called
            runner_called = True
            return subprocess.CompletedProcess([], 0, "", "")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            direct, sdist = self.build_release_artifacts(repository_root, root)
            evidence_dir = root / "rebuilt"
            evidence_dir.mkdir()
            stale_wheel = evidence_dir / direct.name
            stale_wheel.write_bytes(direct.read_bytes())

            with redirect_stdout(io.StringIO()):
                with self.assertRaisesRegex(
                    ReleaseArtifactError, "evidence directory must be empty"
                ):
                    verify_release_artifacts(
                        wheel_path=direct,
                        lock_path=lock_path,
                        notices_path=notices_path,
                        sync_tool_path=sync_tool_path,
                        sdist_path=sdist,
                        rebuilt_wheel_dir=evidence_dir,
                        isolation_runner=no_op_runner,
                    )

            self.assertFalse(runner_called)
            self.assertEqual(stale_wheel.read_bytes(), direct.read_bytes())

    def test_release_gate_builds_fresh_then_publishes_verified_evidence(self):
        """Caller evidence paths must receive only a newly built verified wheel."""
        repository_root = Path(__file__).parents[1]
        lock_path = repository_root / "third_party/assets.lock.json"
        notices_path = repository_root / "THIRD_PARTY_NOTICES.md"
        sync_tool_path = repository_root / "tools/sync_vendor_assets.py"
        observed_outputs = []

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            direct, sdist = self.build_release_artifacts(repository_root, root)
            evidence_dir = root / "rebuilt"
            evidence_dir.mkdir()

            def fixture_runner(source_root, output_dir):
                observed_outputs.append(output_dir.resolve())
                self.assertEqual(list(output_dir.iterdir()), [])
                (output_dir / direct.name).write_bytes(direct.read_bytes())
                return subprocess.CompletedProcess([], 0, "", "")

            with redirect_stdout(io.StringIO()):
                verify_release_artifacts(
                    wheel_path=direct,
                    lock_path=lock_path,
                    notices_path=notices_path,
                    sync_tool_path=sync_tool_path,
                    sdist_path=sdist,
                    rebuilt_wheel_dir=evidence_dir,
                    isolation_runner=fixture_runner,
                )

            self.assertEqual(len(observed_outputs), 1)
            self.assertNotEqual(observed_outputs[0], evidence_dir.resolve())
            published = list(evidence_dir.iterdir())
            self.assertEqual([path.name for path in published], [direct.name])
            self.assertEqual(published[0].read_bytes(), direct.read_bytes())

    def test_release_artifact_gate_rejects_an_unavailable_isolation_runtime(self):
        """A missing container runtime must stop the build instead of weakening it."""
        repository_root = Path(__file__).parents[1]
        lock_path = repository_root / "third_party/assets.lock.json"
        notices_path = repository_root / "THIRD_PARTY_NOTICES.md"
        sync_tool_path = repository_root / "tools/sync_vendor_assets.py"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            direct, sdist = self.build_release_artifacts(repository_root, root)
            runner = release_artifacts.DockerNetworkIsolationRunner(
                "fixture-builder:latest",
                docker_executable=str(root / "missing-docker"),
            )
            with redirect_stdout(io.StringIO()):
                with self.assertRaisesRegex(
                    ReleaseArtifactError, "network isolation.*unavailable"
                ):
                    verify_release_artifacts(
                        wheel_path=direct,
                        lock_path=lock_path,
                        notices_path=notices_path,
                        sync_tool_path=sync_tool_path,
                        sdist_path=sdist,
                        isolation_runner=runner,
                    )

    @unittest.skipUnless(
        hasattr(os, "getuid") and hasattr(os, "getgid"),
        "Docker release builds require a POSIX host identity",
    )
    def test_docker_runner_fails_closed_when_the_daemon_is_unavailable(self):
        """A present Docker CLI with an unreachable daemon must not run a build."""
        fake_docker = self.directory / "unavailable-docker"
        run_marker = self.directory / "run-called"
        fake_docker.write_text(
            """#!/usr/bin/env python3
import sys
from pathlib import Path

if sys.argv[1:3] == ["image", "inspect"]:
    raise SystemExit(1)
Path({!r}).write_text("called", encoding="utf-8")
""".format(str(run_marker)),
            encoding="utf-8",
        )
        fake_docker.chmod(0o755)
        runner = release_artifacts.DockerNetworkIsolationRunner(
            "fixture-builder:latest",
            docker_executable=str(fake_docker),
        )

        with self.assertRaisesRegex(
            ReleaseArtifactError, "network isolation is unavailable"
        ):
            runner(self.directory / "source", self.directory / "output")

        self.assertFalse(run_marker.exists())

    def test_release_cli_rejects_option_like_builder_image_before_docker(self):
        """`--builder-image=--help` must not become a Docker option injection."""
        repository_root = Path(__file__).parents[1]
        completed = subprocess.run(
            [
                sys.executable,
                "tools/verify_release_artifacts.py",
                "--wheel",
                str(self.directory / "missing.whl"),
                "--sdist",
                str(self.directory / "missing.tar.gz"),
                "--network-isolation",
                "docker",
                "--builder-image=--help",
            ],
            cwd=repository_root,
            text=True,
            capture_output=True,
        )

        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("invalid Docker builder image reference", completed.stderr)
        self.assertNotIn("cannot inspect wheel", completed.stderr)

    @unittest.skipUnless(
        hasattr(os, "getuid") and hasattr(os, "getgid"),
        "Docker release builds require a POSIX host identity",
    )
    def test_docker_runner_maps_the_host_identity_into_writable_mounts(self):
        """Container builds must not leave root-owned files in host bind mounts."""
        fake_docker = self.directory / "fake-docker"
        argument_log = self.directory / "docker-arguments.json"
        fake_docker.write_text(
            """#!/usr/bin/env python3
import json
import sys
from pathlib import Path

if sys.argv[1:3] == ["image", "inspect"]:
    raise SystemExit(0)
Path({!r}).write_text(json.dumps(sys.argv[1:]), encoding="utf-8")
""".format(str(argument_log)),
            encoding="utf-8",
        )
        fake_docker.chmod(0o755)
        source_root = self.directory / "source"
        output_dir = self.directory / "output"
        source_root.mkdir()
        output_dir.mkdir()
        runner = release_artifacts.DockerNetworkIsolationRunner(
            "fixture-builder:latest",
            docker_executable=str(fake_docker),
        )

        completed = runner(source_root, output_dir)

        self.assertEqual(completed.returncode, 0, completed.stderr)
        arguments = json.loads(argument_log.read_text(encoding="utf-8"))
        self.assertIn("--user", arguments)
        user_index = arguments.index("--user")
        self.assertEqual(
            arguments[user_index + 1], "{}:{}".format(os.getuid(), os.getgid())
        )
        image_index = arguments.index("fixture-builder:latest")
        self.assertLess(user_index, image_index)
        self.assertEqual(arguments[image_index - 1], "--")

    @unittest.skipUnless(
        os.environ.get("EPUB_BROWSER_RELEASE_BUILDER_IMAGE"),
        "set EPUB_BROWSER_RELEASE_BUILDER_IMAGE to run the Docker isolation proof",
    )
    def test_docker_network_isolation_blocks_backend_network_attempts(self):
        """The release container must block socket, urllib, and subprocess access."""
        repository_root = Path(__file__).parents[1]
        lock_path = repository_root / "third_party/assets.lock.json"
        notices_path = repository_root / "THIRD_PARTY_NOTICES.md"
        sync_tool_path = repository_root / "tools/sync_vendor_assets.py"
        network_probe = b'''\
import socket as _probe_socket
import subprocess as _probe_subprocess
import sys as _probe_sys
import urllib.request as _probe_urllib

def _require_blocked(label, operation):
    try:
        operation()
    except Exception:
        return
    raise RuntimeError(label + " unexpectedly reached the network")

_require_blocked(
    "direct socket",
    lambda: _probe_socket.create_connection(("1.1.1.1", 443), timeout=1),
)
_require_blocked(
    "urllib",
    lambda: _probe_urllib.urlopen("https://pypi.org/simple/", timeout=2).read(1),
)
_probe_child = _probe_subprocess.run(
    [
        _probe_sys.executable,
        "-c",
        "import socket; socket.create_connection(('1.1.1.1', 443), timeout=1)",
    ],
    stdout=_probe_subprocess.DEVNULL,
    stderr=_probe_subprocess.DEVNULL,
    timeout=3,
)
if _probe_child.returncode == 0:
    raise RuntimeError("subprocess unexpectedly reached the network")
'''
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            direct, sdist = self.build_release_artifacts(repository_root, root)
            hostile_sdist = root / "network-probe.tar.gz"
            self.rewrite_sdist(
                sdist,
                hostile_sdist,
                change=lambda name, data: network_probe + data
                if name.endswith("/setup.py")
                else data,
            )
            runner = release_artifacts.DockerNetworkIsolationRunner(
                os.environ["EPUB_BROWSER_RELEASE_BUILDER_IMAGE"]
            )
            with redirect_stdout(io.StringIO()):
                verify_release_artifacts(
                    wheel_path=direct,
                    lock_path=lock_path,
                    notices_path=notices_path,
                    sync_tool_path=sync_tool_path,
                    sdist_path=hostile_sdist,
                    isolation_runner=runner,
                )

    def test_release_artifact_gate_rejects_real_artifact_tampering(self):
        """The public gate must reject malformed derivatives of real artifacts."""
        repository_root = Path(__file__).parents[1]
        lock_path = repository_root / "third_party/assets.lock.json"
        notices_path = repository_root / "THIRD_PARTY_NOTICES.md"
        sync_tool_path = repository_root / "tools/sync_vendor_assets.py"
        first_target = load_lock(lock_path).packages[0].files[0].target
        wheel_target = "epub_browser/assets/vendor/" + first_target

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            direct, sdist = self.build_release_artifacts(repository_root, root)

            missing_input = root / "missing-input.tar.gz"
            self.rewrite_sdist(
                sdist,
                missing_input,
                omit=lambda name: name.endswith("/tools/sync_vendor_assets.py"),
            )
            changed_vendor = root / "changed-vendor.tar.gz"
            self.rewrite_sdist(
                sdist,
                changed_vendor,
                change=lambda name, data: b"changed"
                if name.endswith("/epub_browser/assets/vendor/" + first_target)
                else data,
            )
            duplicate_vendor = root / "duplicate-vendor.tar.gz"
            self.rewrite_sdist(
                sdist,
                duplicate_vendor,
                prepend=[("epub_browser/assets/vendor/" + first_target, b"changed")],
            )
            extra_vendor = root / "extra-vendor.tar.gz"
            self.rewrite_sdist(
                sdist,
                extra_vendor,
                append=[("epub_browser/assets/vendor/unlocked.js", b"extra")],
            )
            linked_member = root / "linked-member.tar.gz"
            self.rewrite_sdist(sdist, linked_member, symlink="unsafe-link")
            traversal_member = root / "traversal-member.tar.gz"
            self.rewrite_sdist(
                sdist,
                traversal_member,
                raw_append=[("../escape", b"escape")],
            )
            rebuilt_tamper = root / "rebuilt-tamper.tar.gz"
            mutation = (
                "from pathlib import Path as _ArtifactPath\n"
                "_ArtifactPath('epub_browser/assets/vendor/{}')"
                ".write_bytes(b'rebuilt-tamper')\n".format(first_target)
            ).encode("utf-8")
            self.rewrite_sdist(
                sdist,
                rebuilt_tamper,
                change=lambda name, data: mutation + data
                if name.endswith("/setup.py")
                else data,
            )
            changed_wheel = root / "changed-wheel.whl"
            self.rewrite_wheel_with_changed_file(
                direct, changed_wheel, wheel_target
            )
            duplicate_wheel = root / "duplicate-wheel.whl"
            self.rewrite_wheel_with_changed_duplicate(
                direct, duplicate_wheel, wheel_target
            )

            cases = (
                ("missing required input", direct, missing_input, "missing"),
                ("changed locked vendor byte", direct, changed_vendor, "digest"),
                ("duplicate changed vendor", direct, duplicate_vendor, "duplicate"),
                ("extra vendor file", direct, extra_vendor, "inventory"),
                ("link member", direct, linked_member, "linked|special"),
                (
                    "traversal member",
                    direct,
                    traversal_member,
                    "canonical|unsafe",
                ),
                ("altered direct wheel", changed_wheel, None, "digest"),
                ("duplicate changed wheel", duplicate_wheel, None, "duplicate"),
                ("altered rebuilt wheel", direct, rebuilt_tamper, "digest"),
            )
            for label, wheel, source, message in cases:
                with self.subTest(case=label):
                    with redirect_stdout(io.StringIO()):
                        with self.assertRaisesRegex(ReleaseArtifactError, message):
                            verify_release_artifacts(
                                wheel_path=wheel,
                                lock_path=lock_path,
                                notices_path=notices_path,
                                sync_tool_path=sync_tool_path,
                                sdist_path=source,
                                isolation_runner=self.local_build_runner,
                            )

    def test_release_gate_rejects_noncanonical_real_archive_members(self):
        """Archive path aliases must fail before inventory checks or extraction."""
        repository_root = Path(__file__).parents[1]
        lock_path = repository_root / "third_party/assets.lock.json"
        notices_path = repository_root / "THIRD_PARTY_NOTICES.md"
        sync_tool_path = repository_root / "tools/sync_vendor_assets.py"
        first_target = load_lock(lock_path).packages[0].files[0].target
        canonical = "epub_browser/assets/vendor/" + first_target

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            direct, sdist = self.build_release_artifacts(repository_root, root)
            wheel_aliases = (
                ("double slash", canonical.replace("/assets/", "//assets/")),
                ("dot segment", canonical.replace("/assets/", "/./assets/")),
                ("backslash", canonical.replace("/", "\\")),
                ("drive rooted", "C:/" + canonical),
                ("absolute", "/" + canonical),
            )
            for label, alias in wheel_aliases:
                destination = root / ("wheel-" + label.replace(" ", "-") + ".whl")
                self.rewrite_wheel_with_extra_member(
                    direct, destination, alias, b"alias"
                )
                with self.subTest(archive="wheel", alias=label):
                    with redirect_stdout(io.StringIO()):
                        with self.assertRaisesRegex(
                            ReleaseArtifactError, "canonical"
                        ):
                            verify_release_artifacts(
                                wheel_path=destination,
                                lock_path=lock_path,
                                notices_path=notices_path,
                                sync_tool_path=sync_tool_path,
                            )

            sdist_aliases = (
                ("double slash", [("aliases//double.js", b"alias")], ()),
                ("dot segment", [("aliases/./dot.js", b"alias")], ()),
                ("backslash", [("aliases\\backslash.js", b"alias")], ()),
                ("nested drive", [("C:/escape.js", b"alias")], ()),
                (
                    "normalized collision",
                    [("epub_browser//assets/vendor/" + first_target, b"changed")],
                    (),
                ),
                ("drive rooted", (), [("C:/escape.js", b"alias")]),
                ("absolute", (), [("/escape.js", b"alias")]),
            )
            for label, relative, exact in sdist_aliases:
                destination = root / ("sdist-" + label.replace(" ", "-") + ".tar.gz")
                self.rewrite_sdist(
                    sdist,
                    destination,
                    raw_append=relative,
                    exact_append=exact,
                )
                with self.subTest(archive="sdist", alias=label):
                    with redirect_stdout(io.StringIO()):
                        with self.assertRaisesRegex(
                            ReleaseArtifactError, "canonical"
                        ):
                            verify_release_artifacts(
                                wheel_path=direct,
                                lock_path=lock_path,
                                notices_path=notices_path,
                                sync_tool_path=sync_tool_path,
                                sdist_path=destination,
                            )

    def test_release_gate_rejects_portable_name_collisions_in_real_artifacts(self):
        """Casefold and Unicode aliases must not produce ambiguous release files."""
        repository_root = Path(__file__).parents[1]
        lock_path = repository_root / "third_party/assets.lock.json"
        notices_path = repository_root / "THIRD_PARTY_NOTICES.md"
        sync_tool_path = repository_root / "tools/sync_vendor_assets.py"
        collisions = (
            ("casefold", "portable/Asset.txt", "portable/asset.txt"),
            (
                "unicode",
                "portable/caf\N{LATIN SMALL LETTER E WITH ACUTE}.txt",
                "portable/cafe\N{COMBINING ACUTE ACCENT}.txt",
            ),
        )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            direct, sdist = self.build_release_artifacts(repository_root, root)
            for label, first, second in collisions:
                wheel_intermediate = root / (label + "-first.whl")
                wheel_collision = root / (label + "-collision.whl")
                self.rewrite_wheel_with_extra_member(
                    direct, wheel_intermediate, first, b"first"
                )
                self.rewrite_wheel_with_extra_member(
                    wheel_intermediate, wheel_collision, second, b"second"
                )
                with self.subTest(archive="wheel", collision=label):
                    with redirect_stdout(io.StringIO()):
                        with self.assertRaisesRegex(
                            ReleaseArtifactError, "portable.*collision"
                        ):
                            verify_release_artifacts(
                                wheel_path=wheel_collision,
                                lock_path=lock_path,
                                notices_path=notices_path,
                                sync_tool_path=sync_tool_path,
                            )

                sdist_collision = root / (label + "-collision.tar.gz")
                self.rewrite_sdist(
                    sdist,
                    sdist_collision,
                    raw_append=((first, b"first"), (second, b"second")),
                )
                with self.subTest(archive="sdist", collision=label):
                    with self.assertRaisesRegex(
                        ReleaseArtifactError, "portable.*collision"
                    ):
                        verify_sdist(
                            sdist_collision,
                            lock_path,
                            notices_path,
                            sync_tool_path,
                        )

    def test_docker_final_stage_copies_prefetched_runtime_without_pip(self):
        """The final image must not resolve or download Python dependencies."""
        repository_root = Path(__file__).parents[1]
        source = (repository_root / "Dockerfile").read_text(encoding="utf-8")
        builder, final = source.rsplit("\nFROM ", 1)

        self.assertIn("verify_release_artifacts.py --wheel", builder)
        self.assertIn("--prefix=/runtime", builder)
        self.assertIn("--ignore-installed", builder)
        self.assertIn("COPY --from=builder /runtime/ /usr/local/", final)
        self.assertNotIn("pip install", final)
        self.assertNotIn("sync_vendor_assets.py", final)

    def fixture_lock(self, files, root=None):
        root = root or self.directory / "vendor"
        for target, contents in files.items():
            path = root / target
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(contents)
        return self.write_lock(files=files), root

    def build_release_artifacts(self, repository_root, root):
        outputs = []
        for kind, name, pattern in (
            ("--wheel", "direct", "*.whl"),
            ("--sdist", "source", "*.tar.gz"),
        ):
            output = root / name
            output.mkdir()
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "build",
                    kind,
                    "--no-isolation",
                    "--outdir",
                    str(output),
                ],
                cwd=repository_root,
                text=True,
                capture_output=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            outputs.append(next(output.glob(pattern)))
        return tuple(outputs)

    @staticmethod
    def local_build_runner(source_root, output_dir):
        environment = os.environ.copy()
        environment.update(
            {"PIP_NO_INDEX": "1", "PIP_DISABLE_PIP_VERSION_CHECK": "1"}
        )
        return subprocess.run(
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

    @staticmethod
    def rewrite_sdist(
        source,
        destination,
        omit=lambda name: False,
        change=lambda name, data: data,
        prepend=(),
        append=(),
        raw_append=(),
        exact_append=(),
        symlink=None,
    ):
        with tarfile.open(source, mode="r:gz") as original:
            members = original.getmembers()
            root = members[0].name.split("/", 1)[0]
            with tarfile.open(destination, mode="w:gz") as rewritten:
                for relative, data in prepend:
                    VendorAssetTests.add_tar_bytes(
                        rewritten, root + "/" + relative, data
                    )
                for member in members:
                    if omit(member.name):
                        continue
                    cloned = copy.copy(member)
                    if member.isfile():
                        stream = original.extractfile(member)
                        if stream is None:
                            raise AssertionError("cannot read " + member.name)
                        with stream:
                            data = change(member.name, stream.read())
                        cloned.size = len(data)
                        rewritten.addfile(cloned, io.BytesIO(data))
                    else:
                        rewritten.addfile(cloned)
                for relative, data in append:
                    VendorAssetTests.add_tar_bytes(
                        rewritten, root + "/" + relative, data
                    )
                for name, data in raw_append:
                    VendorAssetTests.add_tar_bytes(rewritten, root + "/" + name, data)
                for name, data in exact_append:
                    VendorAssetTests.add_tar_bytes(rewritten, name, data)
                if symlink is not None:
                    member = tarfile.TarInfo(root + "/" + symlink)
                    member.type = tarfile.SYMTYPE
                    member.linkname = "../outside"
                    rewritten.addfile(member)

    @staticmethod
    def add_tar_bytes(archive, name, data):
        member = tarfile.TarInfo(name)
        member.size = len(data)
        archive.addfile(member, io.BytesIO(data))

    @staticmethod
    def rewrite_wheel_with_changed_duplicate(source, destination, target):
        with zipfile.ZipFile(source) as original, zipfile.ZipFile(
            destination, mode="w"
        ) as rewritten:
            rewritten.writestr(target, b"changed")
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                for member in original.infolist():
                    rewritten.writestr(member, original.read(member.filename))

    @staticmethod
    def rewrite_wheel_with_changed_file(source, destination, target):
        with zipfile.ZipFile(source) as original, zipfile.ZipFile(
            destination, mode="w"
        ) as rewritten:
            for member in original.infolist():
                data = (
                    b"changed"
                    if member.filename == target
                    else original.read(member.filename)
                )
                rewritten.writestr(member, data)

    @staticmethod
    def rewrite_wheel_with_extra_member(source, destination, name, data):
        with zipfile.ZipFile(source) as original, zipfile.ZipFile(
            destination, mode="w"
        ) as rewritten:
            for member in original.infolist():
                rewritten.writestr(member, original.read(member.filename))
            rewritten.writestr(name, data)

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
