# Configurable Book ID Storage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make visible adjacent sidecars the default stable book-ID carrier while retaining an explicit invocation-wide embedded-OPF mode and preserving existing URLs and Server data.

**Architecture:** Keep low-level embedded ZIP handling in `epub_identity.py`, add a focused sidecar persistence module, and coordinate both carriers through a shared inspect-then-resolve service. SSG supplies no external identity; Server contributes current-path, legacy, or unique inactive-record candidates and continues using SHA-256 as the content-version key.

**Tech Stack:** Python 3.9+, `argparse`, dataclasses, `pathlib`, `zipfile`, SQLite, `unittest`, watchdog, GitHub Actions shell.

**Spec:** `docs/superpowers/specs/2026-08-20-book-id-storage-design.md`

## Global Constraints

- `--book-id-storage sidecar|embedded` applies to every EPUB in one SSG, Server, watch, or legacy invocation.
- The default is exactly `sidecar`; only explicit `embedded` mode may write an EPUB.
- Sidecars are visible and adjacent: `BOOK.epub.epub-browser.json`.
- New IDs remain UUID v4 bytes encoded as 22-character unpadded URL-safe base64; migrated valid IDs remain unchanged.
- `book_id` and URL/client field `book_hash` remain exactly the same value; URL shapes and database schema do not change.
- All carrier, current-path database, legacy, and selected move-candidate IDs must agree; conflicts and duplicate active IDs fail without automatic repair.
- Server cache reuse requires the established source fingerprint to equal the database fingerprint and the cache to remain valid; sidecar fingerprint alone is never reuse evidence.
- Selected storage may be created or refreshed, but non-selected carriers are never deleted or refreshed.
- Sidecar write failure and unsafe embedded write are hard failures; database-only fallback is removed.
- Existing v2.0.4 release/tag history remains unchanged; this work releases as v2.0.5.
- Verification is limited to affected Python modules, example hashes, and the exact GitHub Pages command; do not run an unrelated full product regression suite.

## File Structure

- Create `epub_browser/sidecar_identity.py` for schema validation, safe reads, deterministic atomic writes, adoption, and orphan discovery.
- Create `epub_browser/book_identity.py` for storage constants, carrier inspection, candidate agreement, fingerprint establishment, and selected-carrier persistence.
- Modify `epub_browser/epub_identity.py` to expose generic book-ID validation while preserving its embedded writer.
- Modify `epub_browser/cli.py`, `epub_browser/ssg.py`, `epub_browser/state.py`, `epub_browser/server_library.py`, and `epub_browser/runtime.py` for end-to-end propagation.
- Keep `epub_browser/watch.py` behavior unchanged; extend its tests to lock in `.json` filtering.
- Add focused carrier and example tests; update existing CLI, SSG, State, Server, runtime, watch, and release tests.
- Restore the three tracked example EPUBs and add three visible sidecars.
- Update the GitHub Pages workflow, README, Docker guidance, migration guide, v2.0.5 release notes, and version metadata.

---

### Task 1: Invocation-Wide CLI Storage Choice

**Files:**
- Create: `epub_browser/book_identity.py`
- Modify: `epub_browser/cli.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Produces: `BOOK_ID_STORAGE_SIDECAR`, `BOOK_ID_STORAGE_EMBEDDED`, `BOOK_ID_STORAGE_CHOICES`, and `validate_book_id_storage(value: str) -> str`.
- Produces: `SSGConfig.book_id_storage: str` and `ServerConfig.book_id_storage: str`, both defaulting to `sidecar`.

- [ ] **Step 1: Add failing CLI tests**

Add to `NewCommandTests`:

```python
    def test_book_id_storage_defaults_to_sidecar_in_both_modes(self):
        ssg = parse_cli(["ssg", "books", "--output-dir", "dist"])
        server = parse_cli(["server", "books", "--server-dir", "state"])
        self.assertEqual(ssg.book_id_storage, "sidecar")
        self.assertEqual(server.book_id_storage, "sidecar")

    def test_book_id_storage_is_invocation_wide_in_both_modes(self):
        ssg = parse_cli(
            ["ssg", "one.epub", "two.epub", "--output-dir", "dist",
             "--book-id-storage", "embedded"]
        )
        server = parse_cli(
            ["server", "books", "--server-dir", "state",
             "--book-id-storage", "embedded"]
        )
        self.assertEqual(ssg.book_id_storage, "embedded")
        self.assertEqual(server.book_id_storage, "embedded")

    def test_invalid_book_id_storage_is_rejected(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            parse_cli(
                ["ssg", "books", "--output-dir", "dist",
                 "--book-id-storage", "database"]
            )
```

Add to `LegacyCommandTests`:

```python
    def test_legacy_book_id_storage_maps_to_the_new_command(self):
        config = parse_cli(
            ["books", "--output-dir", "state",
             "--book-id-storage", "embedded"]
        )
        self.assertEqual(config.book_id_storage, "embedded")
        self.assertEqual(
            format_legacy_migration_hint(config),
            "Legacy command syntax is deprecated; equivalent command: "
            "epub-browser server books --server-dir state "
            "--book-id-storage embedded",
        )
```

- [ ] **Step 2: Verify the tests fail**

Run: `python3 -m unittest tests.test_cli -v`

Expected: FAIL because configs and parsers do not expose `book_id_storage`.

- [ ] **Step 3: Define constants and validation**

Create `epub_browser/book_identity.py`:

```python
BOOK_ID_STORAGE_SIDECAR = "sidecar"
BOOK_ID_STORAGE_EMBEDDED = "embedded"
BOOK_ID_STORAGE_CHOICES = (
    BOOK_ID_STORAGE_SIDECAR,
    BOOK_ID_STORAGE_EMBEDDED,
)


def validate_book_id_storage(value: str) -> str:
    if value not in BOOK_ID_STORAGE_CHOICES:
        choices = ", ".join(BOOK_ID_STORAGE_CHOICES)
        raise ValueError(f"Book ID storage must be one of: {choices}")
    return value
```

- [ ] **Step 4: Propagate the CLI value**

In `cli.py`, add this helper to both subparsers and the legacy parser:

```python
def _add_book_id_storage(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--book-id-storage",
        choices=BOOK_ID_STORAGE_CHOICES,
        default=BOOK_ID_STORAGE_SIDECAR,
        help="Store stable IDs in visible sidecars (default) or EPUB OPF metadata",
    )
```

Append `book_id_storage: str = BOOK_ID_STORAGE_SIDECAR` to both dataclasses, set it in all four config construction branches, and append the non-default value to legacy hints:

```python
    if config.book_id_storage != BOOK_ID_STORAGE_SIDECAR:
        command.extend(["--book-id-storage", config.book_id_storage])
```

- [ ] **Step 5: Run focused tests and commit**

Run: `python3 -m unittest tests.test_cli -v`

Expected: PASS.

```bash
git add epub_browser/book_identity.py epub_browser/cli.py tests/test_cli.py
git commit -m "feat: add book ID storage option"
```

---

### Task 2: Safe Visible Sidecar Persistence

**Files:**
- Create: `epub_browser/sidecar_identity.py`
- Modify: `epub_browser/epub_identity.py`
- Create: `tests/test_sidecar_identity.py`
- Modify: `tests/test_epub_identity.py`

**Interfaces:**
- Produces: `validate_book_id(value: str) -> str` from `epub_identity.py`.
- Produces: `SidecarIdentity`, `validate_source_fingerprint`, `sidecar_path_for`, `read_sidecar_file`, `read_exact_sidecar`, `write_sidecar`, `adopt_sidecar`, and `discover_orphan_sidecars`.

- [ ] **Step 1: Write failing sidecar tests**

Create `tests/test_sidecar_identity.py` with these imports, fixture, and core cases:

```python
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from epub_browser.sidecar_identity import (
    SidecarIdentityError,
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
            json.dumps({
                "schema": 1,
                "book_id": "stable_id",
                "source_fingerprint": {
                    "algorithm": "sha256", "value": "a" * 64,
                },
                "future": {"keep": True},
            }),
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
        self.assertEqual(list(self.root.glob(".book.epub.epub-browser.json.*.tmp")), [])
```

Add these link-safety cases:

```python
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
```

- [ ] **Step 2: Verify import failure**

Run: `python3 -m unittest tests.test_sidecar_identity -v`

Expected: FAIL because `sidecar_identity.py` does not exist.

- [ ] **Step 3: Expose carrier-neutral ID validation**

Rename `_validated_book_id` in `epub_identity.py` and update all internal callers:

```python
def validate_book_id(value: str) -> str:
    if not _SAFE_BOOK_ID.fullmatch(value):
        raise ValueError(f"Invalid EPUB Browser book ID: {value!r}")
    return value
```

Import `os` in `tests/test_epub_identity.py`. Add one direct invalid `/` assertion plus these existing safety-contract tests; do not loosen embedded write behavior:

```python
    def test_embedded_mode_refuses_source_symlink(self):
        self._write_epub(self.source)
        linked = self.root / "linked.epub"
        linked.symlink_to(self.source)
        with self.assertRaisesRegex(EPUBIdentityWriteRefused, "symbolic-link"):
            ensure_embedded_book_id(linked, preferred_book_id="safe_id")

    def test_embedded_mode_refuses_source_hard_link(self):
        self._write_epub(self.source)
        linked = self.root / "linked.epub"
        os.link(self.source, linked)
        with self.assertRaisesRegex(EPUBIdentityWriteRefused, "hard links"):
            ensure_embedded_book_id(linked, preferred_book_id="safe_id")
```

- [ ] **Step 4: Implement strict reads and the public data type**

Create the following API:

```python
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


def sidecar_path_for(epub_path: Path) -> Path:
    source = Path(epub_path)
    return source.with_name(source.name + SIDECAR_SUFFIX)


def read_exact_sidecar(epub_path: Path) -> Optional[SidecarIdentity]:
    path = sidecar_path_for(epub_path)
    if not path.exists() and not path.is_symlink():
        return None
    return read_sidecar_file(path)


def validate_source_fingerprint(value: str) -> str:
    if not _SHA256.fullmatch(value):
        raise SidecarIdentityError(
            f"Invalid SHA-256 source fingerprint: {value!r}"
        )
    return value
```

`read_sidecar_file` uses `lstat`, rejects non-regular files, symlinks, and `st_nlink > 1`, parses UTF-8 JSON, requires `type(schema) is int and schema == 1`, validates the ID and exact nested SHA-256 fields, and wraps failures as `SidecarIdentityError` naming the path.

- [ ] **Step 5: Implement deterministic atomic write and adoption**

Build output by preserving unknown supported-schema keys and replacing owned fields:

```python
payload = dict(existing.document) if existing is not None else {}
payload.update({
    "schema": 1,
    "book_id": validate_book_id(book_id),
    "source_fingerprint": {
        "algorithm": "sha256",
        "value": validate_source_fingerprint(source_fingerprint),
    },
})
serialized = (
    json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
).encode("utf-8")
```

Return without a write when bytes already match. Otherwise use adjacent `mkstemp`, flush/fsync, `os.replace`, best-effort parent-directory fsync, and temporary cleanup in `finally`.

`adopt_sidecar(orphan, epub_path)` re-reads and validates the orphan, refuses an existing destination, then atomically moves it to `sidecar_path_for(epub_path)`. A subsequent `write_sidecar` refreshes formatting/fingerprint.

- [ ] **Step 6: Implement scoped orphan discovery**

Add:

```python
def discover_orphan_sidecars(
    configured_sources: Sequence[Path],
    discovered_epubs: Sequence[Path],
) -> tuple[Path, ...]:
```

Explicit EPUB inputs scan only their parent; directory inputs use `os.walk(configured_root, followlinks=False)` and prune hidden or symlinked directories. Collect visible `*.epub.epub-browser.json`, exclude exact current sidecars, and require the paired EPUB path not to exist. Return unique paths sorted by string. Add:

```python
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
```

Import `discover_orphan_sidecars` in the test module.

- [ ] **Step 7: Run tests and commit**

Run: `python3 -m unittest tests.test_sidecar_identity tests.test_epub_identity -v`

Expected: PASS, including existing embedded container-preservation cases.

```bash
git add epub_browser/epub_identity.py epub_browser/sidecar_identity.py tests/test_epub_identity.py tests/test_sidecar_identity.py
git commit -m "feat: add safe visible identity sidecars"
```

---

### Task 3: Shared Carrier Inspection and Resolution

**Files:**
- Modify: `epub_browser/book_identity.py`
- Create: `tests/test_book_identity.py`

**Interfaces:**
- Consumes: Task 2 sidecar APIs, embedded APIs, `new_server_book_id`, and `source_sha256`.
- Produces: `KnownSourceFingerprint`, `ExternalBookIdentity`, `BookIdentityInspection`, `ResolvedBookIdentity`, `inspect_book_identity`, `resolve_book_identity`, `BookIdentityError`, and `BookIdentityConflict`.

- [ ] **Step 1: Write failing resolver matrix tests**

Create `tests/test_book_identity.py` with the valid minimal EPUB helper from `test_epub_identity.py`, `_replace_archive_text` from `test_ssg.py`, and these imports/core tests:

```python
import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from epub_browser.book_identity import (
    BookIdentityConflict,
    BookIdentityError,
    ExternalBookIdentity,
    KnownSourceFingerprint,
    inspect_book_identity,
    resolve_book_identity,
)
from epub_browser.epub_identity import read_embedded_book_id
from epub_browser.identity import source_sha256
from epub_browser.sidecar_identity import (
    read_exact_sidecar,
    read_sidecar_file,
    sidecar_path_for,
    write_sidecar,
)


    def test_default_sidecar_generation_preserves_epub_bytes(self):
        self._write_epub(self.source)
        before = self.source.read_bytes()
        resolved = resolve_book_identity(
            inspect_book_identity(self.source), "sidecar"
        )
        self.assertRegex(resolved.book_id, r"^[A-Za-z0-9_-]{22}$")
        self.assertEqual(self.source.read_bytes(), before)
        self.assertEqual(read_exact_sidecar(self.source).book_id, resolved.book_id)
        self.assertIsNone(read_embedded_book_id(self.source))

    def test_sidecar_mode_migrates_embedded_id_without_rewrite(self):
        self._write_epub(self.source, embedded_book_id="embedded_id")
        before = self.source.read_bytes()
        resolved = resolve_book_identity(
            inspect_book_identity(self.source), "sidecar"
        )
        self.assertEqual(resolved.book_id, "embedded_id")
        self.assertEqual(self.source.read_bytes(), before)
        self.assertEqual(read_exact_sidecar(self.source).book_id, "embedded_id")

    def test_embedded_mode_uses_sidecar_id_without_deleting_sidecar(self):
        self._write_epub(self.source)
        write_sidecar(self.source, "sidecar_id", source_sha256(self.source))
        sidecar_before = sidecar_path_for(self.source).read_bytes()
        resolved = resolve_book_identity(
            inspect_book_identity(self.source), "embedded"
        )
        self.assertEqual(resolved.book_id, "sidecar_id")
        self.assertEqual(read_embedded_book_id(self.source), "sidecar_id")
        self.assertEqual(sidecar_path_for(self.source).read_bytes(), sidecar_before)

    def test_conflicting_carriers_fail_without_mutation(self):
        self._write_epub(self.source, embedded_book_id="embedded_id")
        write_sidecar(self.source, "sidecar_id", source_sha256(self.source))
        epub_before = self.source.read_bytes()
        sidecar_before = sidecar_path_for(self.source).read_bytes()
        with self.assertRaisesRegex(BookIdentityConflict, "embedded_id"):
            resolve_book_identity(inspect_book_identity(self.source), "sidecar")
        self.assertEqual(self.source.read_bytes(), epub_before)
        self.assertEqual(sidecar_path_for(self.source).read_bytes(), sidecar_before)
```

Add these resolver cases, using `_replace_archive_text` from the fixture helper for the content edit:

```python
    def test_content_edit_retains_exact_sidecar_id_and_refreshes_digest(self):
        self._write_epub(self.source)
        first = resolve_book_identity(
            inspect_book_identity(self.source), "sidecar"
        )
        old_digest = read_exact_sidecar(self.source).source_fingerprint
        self._replace_archive_text(
            self.source, "OEBPS/chapter.xhtml", b"unchanged", b"changed"
        )
        second = resolve_book_identity(
            inspect_book_identity(self.source), "sidecar"
        )
        self.assertEqual(second.book_id, first.book_id)
        self.assertNotEqual(
            read_exact_sidecar(self.source).source_fingerprint, old_digest
        )

    def test_one_matching_orphan_is_adopted_after_rename(self):
        self._write_epub(self.source)
        first = resolve_book_identity(
            inspect_book_identity(self.source), "sidecar"
        )
        orphan = sidecar_path_for(self.source)
        moved = self.root / "moved.epub"
        self.source.rename(moved)
        second = resolve_book_identity(
            inspect_book_identity(moved, orphan_sidecars=(orphan,)),
            "sidecar",
        )
        self.assertEqual(second.book_id, first.book_id)
        self.assertFalse(orphan.exists())
        self.assertEqual(read_exact_sidecar(moved).book_id, first.book_id)

    def test_two_matching_orphans_are_ambiguous(self):
        self._write_epub(self.source)
        first = resolve_book_identity(
            inspect_book_identity(self.source), "sidecar"
        )
        first_orphan = sidecar_path_for(self.source)
        second_orphan = self.root / "copy.epub.epub-browser.json"
        shutil.copy2(first_orphan, second_orphan)
        moved = self.root / "moved.epub"
        self.source.rename(moved)
        with self.assertRaisesRegex(BookIdentityError, "Multiple sidecars"):
            resolve_book_identity(
                inspect_book_identity(
                    moved,
                    orphan_sidecars=(first_orphan, second_orphan),
                ),
                "sidecar",
            )
        self.assertEqual(first.book_id, read_sidecar_file(first_orphan).book_id)

    def test_current_database_id_recreates_missing_sidecar(self):
        self._write_epub(self.source)
        resolved = resolve_book_identity(
            inspect_book_identity(self.source),
            "sidecar",
            external_candidates=(
                ExternalBookIdentity("Server database", "database_id", True),
            ),
        )
        self.assertEqual(resolved.book_id, "database_id")
        self.assertEqual(read_exact_sidecar(self.source).book_id, "database_id")

    def test_known_fingerprint_requires_matching_size_and_mtime(self):
        self._write_epub(self.source)
        stat = self.source.stat()
        known = KnownSourceFingerprint("a" * 64, stat.st_size, stat.st_mtime_ns)
        with mock.patch("epub_browser.book_identity.source_sha256") as digest:
            inspection = inspect_book_identity(
                self.source, known_fingerprint=known
            )
        digest.assert_not_called()
        self.assertEqual(inspection.source_fingerprint, "a" * 64)

    def test_sidecar_mode_places_identity_beside_source_symlink(self):
        self._write_epub(self.source)
        target_before = self.source.read_bytes()
        linked = self.root / "linked.epub"
        linked.symlink_to(self.source)
        resolved = resolve_book_identity(
            inspect_book_identity(linked), "sidecar"
        )
        self.assertEqual(
            read_exact_sidecar(linked).book_id, resolved.book_id
        )
        self.assertTrue(
            (self.root / "linked.epub.epub-browser.json").is_file()
        )
        self.assertEqual(self.source.read_bytes(), target_before)
```

Add these final consistency cases:

```python
    def test_current_external_id_conflicts_with_carrier(self):
        self._write_epub(self.source, embedded_book_id="embedded_id")
        inspection = inspect_book_identity(self.source)
        with self.assertRaisesRegex(BookIdentityConflict, "Server database"):
            resolve_book_identity(
                inspection,
                "sidecar",
                external_candidates=(
                    ExternalBookIdentity(
                        "Server database", "database_id", True
                    ),
                ),
            )

    def test_source_change_during_inspection_is_refused(self):
        self._write_epub(self.source)
        real_digest = source_sha256

        def change_then_hash(path):
            self._replace_archive_text(
                path, "OEBPS/chapter.xhtml", b"unchanged", b"changed"
            )
            return real_digest(path)

        with mock.patch(
            "epub_browser.book_identity.source_sha256",
            side_effect=change_then_hash,
        ):
            with self.assertRaisesRegex(BookIdentityError, "source changed"):
                inspect_book_identity(self.source)
```

- [ ] **Step 2: Verify the resolver tests fail**

Run: `python3 -m unittest tests.test_book_identity -v`

Expected: FAIL because the APIs are absent.

- [ ] **Step 3: Define immutable inputs and outputs**

Extend `book_identity.py`:

```python
class BookIdentityError(RuntimeError):
    pass


class BookIdentityConflict(BookIdentityError):
    pass


@dataclass(frozen=True)
class KnownSourceFingerprint:
    value: str
    source_size: int
    source_mtime_ns: int


@dataclass(frozen=True)
class ExternalBookIdentity:
    origin: str
    book_id: str
    current_path: bool


@dataclass(frozen=True)
class BookIdentityInspection:
    source: Path
    source_fingerprint: str
    source_size: int
    source_mtime_ns: int
    source_snapshot: tuple[int, int, int, int]
    embedded_book_id: Optional[str]
    exact_sidecar: Optional[SidecarIdentity]
    matching_orphans: tuple[SidecarIdentity, ...]

    @property
    def has_current_carrier(self) -> bool:
        return self.exact_sidecar is not None or self.embedded_book_id is not None


@dataclass(frozen=True)
class ResolvedBookIdentity:
    book_id: str
    source_fingerprint: str
    source_size: int
    source_mtime_ns: int
```

- [ ] **Step 4: Implement read-only inspection**

Add:

```python
def inspect_book_identity(
    source: Path,
    *,
    known_fingerprint: Optional[KnownSourceFingerprint] = None,
    orphan_sidecars: Sequence[Path] = (),
) -> BookIdentityInspection:
```

Capture `(st_dev, st_ino, st_size, st_mtime_ns)`. Reuse a known digest only when size and mtime exactly match; otherwise hash actual bytes. Read exact and embedded carriers, load existing orphan sidecars whose stored digest matches, sort them, and recheck the source snapshot. A mismatch raises `BookIdentityError("source changed while its identity was inspected")`.

- [ ] **Step 5: Resolve all candidates before mutation**

Add:

```python
def resolve_book_identity(
    inspection: BookIdentityInspection,
    storage: str,
    *,
    external_candidates: Sequence[ExternalBookIdentity] = (),
) -> ResolvedBookIdentity:
```

Validate storage and candidate IDs. Current-path candidates are exact sidecar, embedded metadata, and external candidates with `current_path=True`. If any exist, ignore orphan and move-only candidates. Otherwise include move-only candidates, fail if more than one matching orphan exists, and include the one orphan when present. Require all included IDs to agree before any write; list every origin/value in `BookIdentityConflict`. Generate one UUID-derived ID only when the set is empty.

- [ ] **Step 6: Persist only the selected carrier**

Recheck the snapshot. Sidecar mode adopts the selected orphan when used, calls `write_sidecar`, and confirms EPUB stat identity is unchanged. Embedded mode calls `ensure_embedded_book_id(inspection.source, preferred_book_id=book_id)` only if missing, never touches sidecar, then returns the post-write SHA-256/stat. Existing embedded IDs cause no rewrite.

- [ ] **Step 7: Run tests and commit**

Run: `python3 -m unittest tests.test_book_identity tests.test_sidecar_identity tests.test_epub_identity -v`

Expected: PASS.

```bash
git add epub_browser/book_identity.py tests/test_book_identity.py
git commit -m "feat: resolve book IDs across portable carriers"
```

---

### Task 4: SSG Uses the Shared Resolver

**Files:**
- Modify: `epub_browser/ssg.py`
- Modify: `tests/test_ssg.py`

**Interfaces:**
- Consumes: `inspect_book_identity`, `resolve_book_identity`, and `discover_orphan_sidecars`.
- Produces: default byte-preserving SSG identity behavior and explicit embedded behavior.

- [ ] **Step 1: Replace embedded-default expectations with sidecar-default tests**

Update the first identity test to read the ID from `read_exact_sidecar`, retain it after package content changes, and assert the sidecar fingerprint changes. Add:

```python
    def test_default_ssg_creates_sidecar_without_modifying_epub(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "book.epub"
            output = root / "dist"
            self._write_minimal_epub(source, identifier="urn:test:sidecar")
            before = source.read_bytes()
            SSGPublisher(
                SSGConfig((source,), output), show_progress=False
            ).build()
            sidecar = read_exact_sidecar(source)
            metadata = json.loads(
                (output / "book-metadata.json").read_text(encoding="utf-8")
            )
            self.assertIsNotNone(sidecar)
            self.assertEqual(metadata[0]["hash"], sidecar.book_id)
            self.assertEqual(source.read_bytes(), before)
            self.assertIsNone(read_embedded_book_id(source))

    def test_explicit_embedded_ssg_writes_opf_and_no_sidecar(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "book.epub"
            output = root / "dist"
            self._write_minimal_epub(source, identifier="urn:test:embedded")
            SSGPublisher(
                SSGConfig((source,), output, book_id_storage="embedded"),
                show_progress=False,
            ).build()
            self.assertIsNotNone(read_embedded_book_id(source))
            self.assertFalse(sidecar_path_for(source).exists())
```

Change the duplicate-ID test to copy both EPUB and sidecar:

```python
            SSGPublisher(
                SSGConfig((first,), seed_output), show_progress=False
            ).build()
            shutil.copy2(first, second)
            shutil.copy2(sidecar_path_for(first), sidecar_path_for(second))

            with self.assertRaises(SSGBuildError) as raised:
                SSGPublisher(
                    SSGConfig((first, second), output), show_progress=False
                ).build()
            self.assertIn(str(first.resolve()), str(raised.exception))
            self.assertIn(str(second.resolve()), str(raised.exception))
```

Add a copy-only test that omits the sidecar copy, builds both sources, reads `book-metadata.json`, and asserts `len({book["hash"] for book in metadata}) == 2` while `read_embedded_book_id(first)` and `read_embedded_book_id(second)` are both `None`.

In the existing failed-build test, assert `read_exact_sidecar(source)` is not `None` after conversion failure, proving identity persists for retry while the old destination snapshot remains unchanged.

- [ ] **Step 2: Verify old behavior fails**

Run: `python3 -m unittest tests.test_ssg -v`

Expected: FAIL because SSG still always embeds.

- [ ] **Step 3: Preserve logical explicit source paths**

Use `Path(configured_source).expanduser().absolute()` for an explicit file in `_discover_sources` so its sidecar stays beside the visible path. Continue resolving directory roots for traversal/boundary checks and keep hidden path filtering unchanged.

- [ ] **Step 4: Resolve identities before conversion**

In `build`:

```python
orphan_sidecars = discover_orphan_sidecars(self.config.sources, sources)
prepared = self._prepare_books(sources, orphan_sidecars)
```

Change `_prepare_books` to accept the orphan list and replace embedded-only resolution with:

```python
inspection = inspect_book_identity(
    source, orphan_sidecars=orphan_sidecars
)
identity = resolve_book_identity(
    inspection, self.config.book_id_storage
)
book_id = identity.book_id
```

Keep the EPUB parser probe after resolution. Rename the collision heading to `Duplicate SSG book IDs:`.

- [ ] **Step 5: Run tests and commit**

Run: `python3 -m unittest tests.test_ssg tests.test_book_identity -v`

Expected: PASS, including source-byte equality in default mode.

```bash
git add epub_browser/ssg.py tests/test_ssg.py
git commit -m "feat: use sidecar identities in SSG"
```

---

### Task 5: Carrier-Neutral Server Registry Correlation

**Files:**
- Modify: `epub_browser/state.py`
- Modify: `tests/test_state.py`

**Interfaces:**
- Produces: `StateStore.inactive_book_matches(epub_identifier, source_fingerprint) -> tuple[BookRecord, ...]`.
- Produces: ambiguity errors while an authoritative carrier ID can still select its exact inactive row.
- Keeps: database schema and `PRAGMA user_version` unchanged.

- [ ] **Step 1: Require ambiguity failure in tests**

Replace the ambiguous-new-ID test with:

```python
    def test_ambiguous_inactive_move_is_refused(self):
        first = self.store.resolve_book(
            Path(self.temporary.name, "first.epub"),
            "urn:test:ambiguous", "same-content", {"title": "Book"},
        )
        second = self.store.resolve_book(
            Path(self.temporary.name, "second.epub"),
            "urn:test:ambiguous", "same-content", {"title": "Book"},
        )
        self.store.mark_missing(first.book_id)
        self.store.mark_missing(second.book_id)
        matches = self.store.inactive_book_matches(
            "urn:test:ambiguous", "same-content"
        )
        self.assertEqual(
            {record.book_id for record in matches},
            {first.book_id, second.book_id},
        )
        with self.assertRaisesRegex(ValueError, "Multiple inactive"):
            self.store.resolve_book(
                Path(self.temporary.name, "moved.epub"),
                "urn:test:ambiguous", "same-content", {"title": "Book"},
            )
```

Add the authoritative-carrier counterpart:

```python
    def test_authoritative_id_selects_exact_inactive_row_despite_ambiguity(self):
        first = self.store.resolve_book(
            Path(self.temporary.name, "first.epub"),
            "urn:test:ambiguous", "same-content", {"title": "Book"},
        )
        second = self.store.resolve_book(
            Path(self.temporary.name, "second.epub"),
            "urn:test:ambiguous", "same-content", {"title": "Book"},
        )
        self.store.mark_missing(first.book_id)
        self.store.mark_missing(second.book_id)
        moved = self.store.resolve_book(
            Path(self.temporary.name, "moved.epub"),
            "urn:test:ambiguous", "same-content", {"title": "Book"},
            authoritative_book_id=first.book_id,
        )
        self.assertEqual(moved.book_id, first.book_id)
        self.assertTrue(moved.active)
```

- [ ] **Step 2: Verify failure**

Run: `python3 -m unittest tests.test_state -v`

Expected: FAIL because the public query is absent and ambiguity allocates a new ID.

- [ ] **Step 3: Add one reusable inactive-match query**

Add:

```python
    @staticmethod
    def _inactive_move_rows(connection, identifier, source_fingerprint):
        if not identifier or not source_fingerprint:
            return []
        return connection.execute(
            """
            SELECT * FROM books
            WHERE active = 0
              AND epub_identifier = ?
              AND source_fingerprint = ?
            ORDER BY book_id
            """,
            (identifier, source_fingerprint),
        ).fetchall()

    def inactive_book_matches(self, epub_identifier, source_fingerprint):
        identifier = (epub_identifier or "").strip() or None
        with self._connection() as connection:
            rows = self._inactive_move_rows(
                connection, identifier, source_fingerprint
            )
        return tuple(self._book_record(row) for row in rows)
```

Use the helper inside `resolve_book`; preserve the unique match and raise `ValueError("Multiple inactive books match the same EPUB identifier and fingerprint")` for multiple rows when no authoritative ID already handled the request.

- [ ] **Step 4: Make errors carrier-neutral, test, and commit**

Replace `Embedded EPUB book ID` wording in `resolve_book` with `Portable book ID` or `Book ID`, preserving source paths and IDs.

Run: `python3 -m unittest tests.test_state -v`

Expected: PASS with unchanged database schema version.

```bash
git add epub_browser/state.py tests/test_state.py
git commit -m "fix: reject ambiguous server identity moves"
```

---

### Task 6: Server Reconciliation, Runtime, and Watch Integration

**Files:**
- Modify: `epub_browser/server_library.py`
- Modify: `epub_browser/runtime.py`
- Modify: `tests/test_server_library.py`
- Modify: `tests/test_runtime.py`
- Modify: `tests/test_watch.py`

**Interfaces:**
- Consumes: Tasks 1-5 resolver, sidecar discovery, and inactive-match query.
- Produces: a new keyword argument `book_id_storage: str = "sidecar"` on `ServerLibraryManager.__init__`, plus runtime propagation.
- Removes: `_ensure_source_identity` and database-only fallback.

- [ ] **Step 1: Rewrite Server identity tests around sidecars**

Change the first Server test to:

```python
    def test_first_reconcile_creates_sidecar_without_modifying_epub(self):
        before = self.source.read_bytes()
        manager = self._manager()
        record = manager.reconcile().active_books[0]
        self.assertEqual(read_exact_sidecar(self.source).book_id, record.book_id)
        self.assertEqual(self.source.read_bytes(), before)
        self.assertIsNone(read_embedded_book_id(self.source))
        manager.shutdown()
```

Add the following named cases with these exact operations/assertions:

```python
    def test_v204_embedded_id_migrates_to_sidecar_without_epub_write(self):
        ensure_embedded_book_id(
            self.source, preferred_book_id="v204_embedded_id"
        )
        before = self.source.read_bytes()
        manager = self._manager()
        record = manager.reconcile().active_books[0]
        self.assertEqual(record.book_id, "v204_embedded_id")
        self.assertEqual(read_exact_sidecar(self.source).book_id, record.book_id)
        self.assertEqual(self.source.read_bytes(), before)
        manager.shutdown()

    def test_content_edit_retains_exact_sidecar_id(self):
        manager = self._manager()
        first = manager.reconcile().active_books[0]
        self._write_epub(self.source, "Changed")
        second = manager.reconcile().active_books[0]
        self.assertEqual(second.book_id, first.book_id)
        self.assertEqual(read_exact_sidecar(self.source).book_id, first.book_id)
        manager.shutdown()

    def test_offline_epub_only_move_adopts_orphan_and_database_id(self):
        manager = self._manager()
        first = manager.reconcile().active_books[0]
        orphan = sidecar_path_for(self.source)
        moved = self.source_dir / "moved.epub"
        self.source.rename(moved)
        second = manager.reconcile().active_books[0]
        self.assertEqual(second.book_id, first.book_id)
        self.assertEqual(Path(second.source_path), moved.resolve())
        self.assertFalse(orphan.exists())
        self.assertEqual(read_exact_sidecar(moved).book_id, first.book_id)
        manager.shutdown()

    def test_epub_only_copy_gets_distinct_id_while_original_is_active(self):
        manager = self._manager()
        first = manager.reconcile().active_books[0]
        copied = self.source_dir / "copied.epub"
        shutil.copy2(self.source, copied)
        summary = manager.reconcile()
        self.assertEqual(len(summary.active_books), 2)
        self.assertEqual(len({record.book_id for record in summary.active_books}), 2)
        self.assertNotEqual(read_exact_sidecar(copied).book_id, first.book_id)
        manager.shutdown()

    def test_explicit_embedded_mode_writes_once_then_reuses(self):
        converter = mock.Mock(side_effect=EPUBProcessor)
        manager = self._manager(
            converter, book_id_storage="embedded"
        )
        first = manager.reconcile()
        converter.reset_mock()
        second = manager.reconcile()
        self.assertEqual(first.converted, 1)
        self.assertEqual(second.reused, 1)
        self.assertIsNotNone(read_embedded_book_id(self.source))
        self.assertFalse(sidecar_path_for(self.source).exists())
        converter.assert_not_called()
        manager.shutdown()
```

Add the remaining failure cases exactly:

```python
    def test_epub_and_sidecar_copy_reports_duplicate_active_id(self):
        manager = self._manager()
        first = manager.reconcile().active_books[0]
        copied = self.source_dir / "copied.epub"
        shutil.copy2(self.source, copied)
        shutil.copy2(sidecar_path_for(self.source), sidecar_path_for(copied))
        summary = manager.reconcile()
        self.assertEqual(summary.failed, 1)
        self.assertIn("already used by another source", summary.failures[0].message)
        self.assertEqual(
            [record.book_id for record in summary.active_books],
            [first.book_id],
        )
        manager.shutdown()

    def test_carrier_database_conflict_keeps_previous_cache(self):
        manager = self._manager()
        first = manager.reconcile().active_books[0]
        ensure_embedded_book_id(
            self.source, preferred_book_id="conflicting_id"
        )
        summary = manager.reconcile()
        self.assertTrue(summary.degraded)
        self.assertTrue(summary.failures[0].kept_previous_cache)
        self.assertTrue(
            (manager.public_dir / "book" / first.book_id / "index.html").is_file()
        )
        manager.shutdown()

    def test_sidecar_replace_failure_has_no_database_only_fallback(self):
        manager = self._manager()
        with mock.patch(
            "epub_browser.sidecar_identity.os.replace",
            side_effect=OSError("sidecar replace failed"),
        ):
            summary = manager.reconcile()
        self.assertEqual(summary.failed, 1)
        self.assertIn("sidecar replace failed", summary.failures[0].message)
        self.assertEqual(summary.active_books, ())
        self.assertEqual(self.store.active_books(), ())
        manager.shutdown()
```

- [ ] **Step 2: Add watcher and runtime propagation tests**

Add to `tests/test_watch.py`:

```python
    def test_sidecar_events_do_not_queue_reconciliation(self):
        class Manager:
            def __init__(self):
                self.queued = []

            def queue_path(self, path):
                self.queued.append(Path(path))

        manager = Manager()
        handler = EpubFileHandler(manager)
        handler.on_created(
            FileCreatedEvent("/tmp/book.epub.epub-browser.json")
        )
        handler.on_created(FileCreatedEvent("/tmp/.book.epub.sidecar.tmp"))
        handler.shutdown()
        self.assertEqual(manager.queued, [])
```

Add this runtime case using the existing `_ReturningServer` pattern:

```python
    def test_runtime_passes_book_id_storage_to_library_manager(self):
        captured = {}
        config = ServerConfig(
            sources=(self.sources,),
            server_dir=self.server_dir,
            ephemeral=False,
            no_browser=True,
            book_id_storage="embedded",
        )

        class Library:
            def __init__(self, *, server_dir, book_id_storage, **kwargs):
                captured["book_id_storage"] = book_id_storage
                self.public_dir = Path(server_dir) / "cache" / "public"
                self.on_reconcile_started = None
                self.on_reconciled = None

            def prepare_public_shell(self):
                self.public_dir.mkdir(parents=True, exist_ok=True)
                (self.public_dir / "index.html").write_text(
                    "library", encoding="utf-8"
                )

            def reconcile(self):
                return ReconcileSummary(0, 0, 0, (), ())

            def request_stop(self):
                return None

            def shutdown(self):
                return None

        status = run_server(
            config,
            server_factory=_ReturningServer,
            library_factory=Library,
        )
        self.assertEqual(status, 0)
        self.assertEqual(captured["book_id_storage"], "embedded")
```

- [ ] **Step 3: Verify integration failures**

Run: `python3 -m unittest tests.test_server_library tests.test_watch tests.test_runtime -v`

Expected: identity and propagation cases FAIL while unrelated cases remain green.

- [ ] **Step 4: Add manager storage and logical path handling**

Add `book_id_storage=BOOK_ID_STORAGE_SIDECAR` to `ServerLibraryManager.__init__`, validate it, and store it. Keep `_source_inputs` as expanded absolute logical paths and `self.sources` as canonical paths for nesting checks.

For an explicit file, `_discover_sources` returns its logical absolute path. Directory walks keep canonical-root boundaries. Build `discovered_set` from `str(path.resolve())` so canonical database rows are not marked missing due to an explicit symlink.

After discovery/missing marking, calculate:

```python
orphan_sidecars = discover_orphan_sidecars(
    self._source_inputs, discovered
)
```

- [ ] **Step 5: Replace embedded-only identity resolution**

Delete the `EPUBIdentityWriteRefused` catch and `new_server_book_id` fallback. For each source:

1. Create `KnownSourceFingerprint` only when an existing row's size/mtime match and its cache is valid; otherwise inspection hashes actual bytes.
2. Inspect exact, embedded, and matching orphan carriers.
3. Existing same-path row becomes `ExternalBookIdentity("Server database", id, current_path=True)`.
4. With no row, a correlated legacy ID becomes `ExternalBookIdentity("legacy migration", id, current_path=True)`.
5. With neither and no current carrier, probe metadata and query `inactive_book_matches`. Multiple matches fail; one becomes `ExternalBookIdentity("inactive Server record", id, current_path=False)`.
6. Resolve using `self.book_id_storage`, then pass `authoritative_book_id=resolved.book_id` to `StateStore.resolve_book` together with the probed metadata and resolved fingerprint/stat values.

On the unchanged fast path, reuse only when post-persistence fingerprint, size, and mtime still equal the database baseline and cache is valid. An initial embedded write falls through to conversion using its post-write values; sidecar creation can reuse unchanged cached content.

Conversion plans use the resolved fingerprint/size/mtime. Keep `_convert_plan`'s final actual SHA-256 and stat checks unchanged.

- [ ] **Step 6: Pass runtime configuration**

Add to the manager constructor in `run_server`:

```python
            book_id_storage=config.book_id_storage,
```

The watcher needs no storage argument because the process-wide manager owns it.

- [ ] **Step 7: Run focused integrations and commit**

Run: `python3 -m unittest tests.test_server_library tests.test_state tests.test_watch tests.test_runtime tests.test_mode_integration -v`

Expected: PASS, including progress, cancellation, cache rollback, migration, and boundaries.

```bash
git add epub_browser/server_library.py epub_browser/runtime.py tests/test_server_library.py tests/test_runtime.py tests/test_watch.py tests/test_mode_integration.py
git commit -m "feat: use configurable identities in Server mode"
```

---

### Task 7: Restore Example EPUBs and Protect CI Inputs

**Files:**
- Restore: `examples/Mao Ze Dong Xuan Ji - Mao Ze Dong.epub`
- Restore: `examples/TheEconomist.2026.02.14 - Kovid Goyal.epub`
- Restore: `examples/Yi Jiu Ba Si - Qiao Zhi _Ao Wei Er.epub`
- Create: the adjacent `.epub-browser.json` file for each EPUB above
- Create: `tests/test_examples_identity.py`
- Modify: `.github/workflows/gh-pages.yml`

**Interfaces:**
- Consumes: sidecar schema and default SSG behavior.
- Produces: pre-v2.0.4 EPUB bytes, stable existing public IDs, and CI mutation detection.

- [ ] **Step 1: Add a failing exact fixture regression**

Create `tests/test_examples_identity.py`:

```python
import unittest
from pathlib import Path

from epub_browser.epub_identity import read_embedded_book_id
from epub_browser.identity import source_sha256
from epub_browser.sidecar_identity import read_exact_sidecar


class ExampleIdentityTests(unittest.TestCase):
    EXPECTED = {
        "Mao Ze Dong Xuan Ji - Mao Ze Dong.epub": (
            "6QrgU-nfQSm_M6lmKAuBRg",
            "ee41f0b9a38ca691490e4e0e957cf40b4eaaa86c490c7b0417d33e1a77d8b50e",
        ),
        "TheEconomist.2026.02.14 - Kovid Goyal.epub": (
            "HxcyeSrJTySgmFoJMnyKFw",
            "764459af1ffb78720e1efdbd619139c39daf4f9af82426c62f97c7cdcf3dfc13",
        ),
        "Yi Jiu Ba Si - Qiao Zhi _Ao Wei Er.epub": (
            "W5t_bkH64u-0GwfxFrnEew",
            "e39771bfc05df91a23e9d86a86a319ea57e7c0f94f49b1220f1587f180685192",
        ),
    }

    def test_examples_keep_original_bytes_and_visible_public_ids(self):
        root = Path("examples")
        for filename, (book_id, fingerprint) in self.EXPECTED.items():
            with self.subTest(filename=filename):
                source = root / filename
                sidecar = read_exact_sidecar(source)
                self.assertEqual(source_sha256(source), fingerprint)
                self.assertEqual(sidecar.book_id, book_id)
                self.assertEqual(sidecar.source_fingerprint, fingerprint)
                self.assertIsNone(read_embedded_book_id(source))
```

- [ ] **Step 2: Verify it fails**

Run: `python3 -m unittest tests.test_examples_identity -v`

Expected: FAIL because sidecars are absent and two EPUB hashes still contain embedded metadata.

- [ ] **Step 3: Restore only the approved binary targets**

```bash
git restore --source=9a5a94b -- "examples/Mao Ze Dong Xuan Ji - Mao Ze Dong.epub" "examples/TheEconomist.2026.02.14 - Kovid Goyal.epub" "examples/Yi Jiu Ba Si - Qiao Zhi _Ao Wei Er.epub"
```

Do not restore the directory recursively or touch another user file.

- [ ] **Step 4: Add exact visible sidecars**

Use Task 2's deterministic JSON shape with these pairs:

```text
Mao Ze Dong Xuan Ji - Mao Ze Dong.epub
6QrgU-nfQSm_M6lmKAuBRg
ee41f0b9a38ca691490e4e0e957cf40b4eaaa86c490c7b0417d33e1a77d8b50e

TheEconomist.2026.02.14 - Kovid Goyal.epub
HxcyeSrJTySgmFoJMnyKFw
764459af1ffb78720e1efdbd619139c39daf4f9af82426c62f97c7cdcf3dfc13

Yi Jiu Ba Si - Qiao Zhi _Ao Wei Er.epub
W5t_bkH64u-0GwfxFrnEew
e39771bfc05df91a23e9d86a86a319ea57e7c0f94f49b1220f1587f180685192
```

Each file contains only `book_id`, `schema: 1`, and the nested SHA-256 object, formatted as `write_sidecar` emits it.

- [ ] **Step 5: Guard GitHub Pages inputs**

Keep the existing empty-directory check and legacy command, wrapping it with:

```bash
find examples -maxdepth 1 -type f -name '*.epub' -print0 \
  | sort -z \
  | xargs -0 sha256sum > /tmp/epub-browser-inputs-before.sha256
epub-browser ./examples --no-server --output-dir ./test --keep-files
find examples -maxdepth 1 -type f -name '*.epub' -print0 \
  | sort -z \
  | xargs -0 sha256sum > /tmp/epub-browser-inputs-after.sha256
diff -u /tmp/epub-browser-inputs-before.sha256 /tmp/epub-browser-inputs-after.sha256
```

- [ ] **Step 6: Verify fixtures and the exact command**

Run: `python3 -m unittest tests.test_examples_identity -v`

Then record `sha256sum examples/*.epub`, run `epub-browser ./examples --no-server --output-dir "$(mktemp -d)/test" --keep-files`, and record hashes again.

Expected: test and generation PASS; all before/after hashes are identical.

- [ ] **Step 7: Commit examples and CI**

```bash
git add \
  "examples/Mao Ze Dong Xuan Ji - Mao Ze Dong.epub" \
  "examples/Mao Ze Dong Xuan Ji - Mao Ze Dong.epub.epub-browser.json" \
  "examples/TheEconomist.2026.02.14 - Kovid Goyal.epub" \
  "examples/TheEconomist.2026.02.14 - Kovid Goyal.epub.epub-browser.json" \
  "examples/Yi Jiu Ba Si - Qiao Zhi _Ao Wei Er.epub" \
  "examples/Yi Jiu Ba Si - Qiao Zhi _Ao Wei Er.epub.epub-browser.json" \
  tests/test_examples_identity.py \
  .github/workflows/gh-pages.yml
git commit -m "fix: preserve example EPUBs with sidecar IDs"
```

---

### Task 8: v2.0.5 Documentation and Release Metadata

**Files:**
- Modify: `README.md`
- Modify: `Dockerfile`
- Modify: `docs/migration-v2.md`
- Create: `docs/releases/v2.0.5.md`
- Modify: `epub_browser/version.py`
- Modify: `tests/test_mode_integration.py`

**Interfaces:**
- Consumes: completed behavior and exact CLI names.
- Produces: consistent v2.0.5 guidance without moving or editing v2.0.4 history.

- [ ] **Step 1: Change the release expectation first**

In `tests/test_mode_integration.py`:

```python
        self.assertIn(
            'VERSION = "2.0.5"',
            Path("epub_browser/version.py").read_text(),
        )
```

Run: `python3 -m unittest tests.test_mode_integration.ModeIntegrationTests.test_release_metadata_is_consistent -v`

Expected: FAIL while version remains `2.0.4`.

- [ ] **Step 2: Document the portable identity contract**

Add a README `Book identity storage` section that states these exact facts:

```text
Default: --book-id-storage sidecar
Visible file: BOOK.epub.epub-browser.json
Alternative: --book-id-storage embedded
Scope: one value for the entire command invocation
Identity: book_id is the same value as URL/client book_hash
Reuse: Server compares verified source fingerprint plus cache validity
Migration: v2.0.4 embedded IDs copy to sidecars without rewriting EPUBs
Conflict: disagreeing carriers or duplicate active IDs stop that source
```

Add `--book-id-storage` to the `Both` option table. Update Docker guidance: `/app/Library:rw` permits default sidecar creation/refresh; read-only works only when every selected carrier already exists and matches. Explain that `embedded` opts into ZIP rebuilding and may be refused.

Add the same migration/rollback facts to `docs/migration-v2.md`. Update the Dockerfile comment so it no longer recommends read-only input unconditionally.

- [ ] **Step 3: Write bilingual v2.0.5 release notes**

Create `docs/releases/v2.0.5.md`, dated `2026-08-20`, with Chinese and English sections covering:

- visible sidecars as default;
- the invocation-wide option in SSG, Server, watch, and legacy syntax;
- byte-preserving default and explicit embedded risk;
- v2.0.4 migration without deleting embedded metadata;
- fingerprint-based reuse/move recognition;
- conflict, duplicate, and ambiguity errors;
- restored example bytes and CI mutation guard;
- no database migration and unchanged URL `book_hash`.

Do not edit `docs/releases/v2.0.4.md`.

- [ ] **Step 4: Bump version and Docker image example**

Set `VERSION = "2.0.5"` and change the README example image from `epub-browser:2.0.4` to `epub-browser:2.0.5`.

- [ ] **Step 5: Verify and commit release materials**

Run: `python3 -m unittest tests.test_mode_integration.ModeIntegrationTests.test_release_metadata_is_consistent tests.test_cli -v`

Expected: PASS.

```bash
git add README.md Dockerfile docs/migration-v2.md docs/releases/v2.0.5.md epub_browser/version.py tests/test_mode_integration.py
git commit -m "chore: release v2.0.5"
```

---

### Task 9: Focused Verification and Final Consistency Gate

**Files:**
- Verify only; modify task-owned files only if a focused check exposes a defect.

**Interfaces:**
- Consumes: complete implementation.
- Produces: evidence that approved behavior works and default mode preserves EPUB bytes.

- [ ] **Step 1: Prepare imports only when needed**

Run `python3 -m pip install -e .` only if the current interpreter cannot import declared dependencies (`uvicorn`, `watchdog`, `starlette`, `tqdm`, `minify_html`).

- [ ] **Step 2: Run only affected test modules**

```bash
python3 -m unittest \
  tests.test_cli \
  tests.test_epub_identity \
  tests.test_sidecar_identity \
  tests.test_book_identity \
  tests.test_ssg \
  tests.test_state \
  tests.test_server_library \
  tests.test_watch \
  tests.test_runtime \
  tests.test_mode_integration \
  tests.test_examples_identity \
  -v
```

Expected: PASS. Do not expand to unrelated Python or JavaScript suites.

- [ ] **Step 3: Reproduce GitHub Pages without input mutation**

Record hashes, run:

```bash
epub-browser ./examples --no-server --output-dir "$(mktemp -d)/test" --keep-files
```

Record hashes again. Expected exit code is `0`, and hashes remain:

```text
ee41f0b9a38ca691490e4e0e957cf40b4eaaa86c490c7b0417d33e1a77d8b50e
764459af1ffb78720e1efdbd619139c39daf4f9af82426c62f97c7cdcf3dfc13
e39771bfc05df91a23e9d86a86a319ea57e7c0f94f49b1220f1587f180685192
```

- [ ] **Step 4: Run static consistency checks**

```bash
python3 -m compileall -q epub_browser tests
git diff --check
rg -n "2\.0\.4|database-only|always.*embed|Mount EPUB input read-write so EPUB Browser can embed" README.md Dockerfile docs/migration-v2.md docs/releases/v2.0.5.md epub_browser
git status --short
```

Expected: compile/diff pass; search contains no stale current-behavior guidance; status is clean after intentional commits.

- [ ] **Step 5: Commit only focused verification fixes when required**

If a check required correction, stage only affected task-owned paths and commit:

```bash
git commit -m "fix: finalize sidecar identity release"
```

If no correction was needed, do not create an empty commit.
