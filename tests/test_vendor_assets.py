import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tools.sync_vendor_assets import VendorAssetError, load_lock, verify_assets


class VendorAssetTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.directory = Path(self.temporary_directory.name)

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
                        "max_expanded_bytes": 2048,
                    },
                    "license": {"spdx": "MIT", "files": ["LICENSE"]},
                    "files": entries,
                }
            ],
        }
        lock_path = self.directory / "assets.lock.json"
        lock_path.write_text(json.dumps(document), encoding="utf-8")
        return lock_path


if __name__ == "__main__":
    unittest.main()
