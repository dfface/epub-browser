import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from epub_browser.sidecar_identity import (
    SidecarIdentityError,
    discover_orphan_sidecars,
    read_exact_sidecar,
    sidecar_path_for,
    write_sidecar,
)


class SidecarIdentityTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "book.epub"
        self.source.write_bytes(b"original epub bytes")

    def test_write_is_visible_deterministic_and_does_not_modify_epub(self):
        source_before = self.source.read_bytes()
        path = write_sidecar(self.source, "stable_id", "a" * 64)
        first_bytes = path.read_bytes()
        write_sidecar(self.source, "stable_id", "a" * 64)
        self.assertEqual(path, self.root / "book.epub.epub-browser.json")
        self.assertEqual(self.source.read_bytes(), source_before)
        self.assertEqual(path.read_bytes(), first_bytes)
        self.assertTrue(first_bytes.endswith(b"\n"))
        self.assertEqual(read_exact_sidecar(self.source).book_id, "stable_id")

    def test_refresh_preserves_unknown_supported_schema_keys(self):
        path = sidecar_path_for(self.source)
        path.write_text(
            json.dumps(
                {
                    "schema": 1,
                    "book_id": "stable_id",
                    "source_fingerprint": {
                        "algorithm": "sha256",
                        "value": "a" * 64,
                    },
                    "future": {"keep": True},
                }
            ),
            encoding="utf-8",
        )
        write_sidecar(self.source, "stable_id", "b" * 64)
        payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(payload["future"], {"keep": True})
        self.assertEqual(payload["source_fingerprint"]["value"], "b" * 64)

    def test_malformed_sidecar_is_refused(self):
        sidecar_path_for(self.source).write_text(
            '{"schema":2,"book_id":"stable_id"}', encoding="utf-8"
        )
        with self.assertRaisesRegex(SidecarIdentityError, "schema"):
            read_exact_sidecar(self.source)

    def test_failed_replace_preserves_existing_sidecar(self):
        path = write_sidecar(self.source, "stable_id", "a" * 64)
        before = path.read_bytes()
        with mock.patch(
            "epub_browser.sidecar_identity.os.replace",
            side_effect=OSError("replace failed"),
        ):
            with self.assertRaisesRegex(OSError, "replace failed"):
                write_sidecar(self.source, "stable_id", "b" * 64)
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(
            list(self.root.glob(".book.epub.epub-browser.json.*.tmp")), []
        )

    def test_sidecar_symbolic_link_is_refused(self):
        target = self.root / "target.json"
        target.write_text("{}", encoding="utf-8")
        sidecar_path_for(self.source).symlink_to(target)
        with self.assertRaisesRegex(SidecarIdentityError, "symbolic link"):
            read_exact_sidecar(self.source)

    def test_sidecar_with_multiple_hard_links_is_refused(self):
        path = write_sidecar(self.source, "stable_id", "a" * 64)
        os.link(path, self.root / "other.epub-browser.json")
        with self.assertRaisesRegex(SidecarIdentityError, "multiple hard links"):
            read_exact_sidecar(self.source)

    def test_orphan_discovery_excludes_hidden_exact_and_paired_files(self):
        exact = self.root / "exact.epub"
        exact.write_bytes(b"exact")
        write_sidecar(exact, "exact_id", "a" * 64)
        orphan = self.root / "old.epub"
        orphan_sidecar = write_sidecar(orphan, "old_id", "b" * 64)
        paired = self.root / "paired.epub"
        paired.write_bytes(b"paired")
        write_sidecar(paired, "paired_id", "c" * 64)
        hidden = self.root / ".hidden"
        hidden.mkdir()
        write_sidecar(hidden / "hidden.epub", "hidden_id", "d" * 64)

        discovered = discover_orphan_sidecars((self.root,), (exact, paired))

        self.assertEqual(discovered, (orphan_sidecar,))


if __name__ == "__main__":
    unittest.main()
