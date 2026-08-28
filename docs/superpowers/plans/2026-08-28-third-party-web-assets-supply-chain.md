# Third-Party Web Asset Supply Chain Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace tracked third-party browser blobs with a reproducible, locked, verified build-time asset pipeline that also supplies PDF.js.

**Architecture:** A project-owned Python tool validates a canonical lock file, downloads immutable HTTPS archives into temporary storage, extracts only allowlisted regular files, verifies all digests and licenses, and atomically hydrates `epub_browser/assets/vendor/`. Runtime publishing consumes that complete local tree exactly as it consumes authored assets; release workflows fetch and verify before building self-contained artifacts.

**Tech Stack:** Python 3.9+, `urllib.request`, `hashlib`, `tarfile`, `zipfile`, setuptools, GitHub Actions, Docker multi-stage builds, `unittest`.

**Spec:** `docs/superpowers/specs/2026-08-28-third-party-web-assets-supply-chain-design.md`

## Global Constraints

- Source checkouts never contact the network implicitly.
- Runtime readers never load vendor code from a CDN.
- All archive URLs, versions, archive SHA-256 values, output SHA-256 values, size limits, file allowlists, and licenses are locked.
- Generated content is restricted to `epub_browser/assets/vendor/` and is absent from Git but present in wheels, sdists, Docker images, and SSG output.
- `clean` never removes unknown files or any path outside the generated vendor root.
- Existing authored assets and EPUB behavior remain unchanged.

---

### Task 1: Lock schema and offline verifier

**Files:**
- Create: `third_party/assets.lock.json`
- Create: `third_party/README.md`
- Create: `tools/sync_vendor_assets.py`
- Create: `tests/test_vendor_assets.py`

**Interfaces:**
- Produces: `load_lock(path: Path) -> AssetLock`
- Produces: `verify_assets(lock_path: Path, vendor_root: Path) -> None`
- Produces: CLI `python tools/sync_vendor_assets.py verify`

- [ ] **Step 1: Write failing schema and verification tests**

```python
class VendorAssetTests(unittest.TestCase):
    def test_verify_rejects_digest_mismatch(self):
        lock, root = self.fixture_lock(files={"pkg/file.js": b"expected"})
        (root / "pkg/file.js").write_bytes(b"changed")
        with self.assertRaisesRegex(VendorAssetError, "pkg/file.js.*SHA-256"):
            verify_assets(lock, root)

    def test_lock_rejects_duplicate_targets_and_parent_paths(self):
        for target in ("../escape.js", "/absolute.js", "pkg/../../escape.js"):
            with self.subTest(target=target):
                with self.assertRaises(VendorAssetError):
                    load_lock(self.write_lock(targets=[target, target]))
```

- [ ] **Step 2: Run tests and verify the module is missing**

Run: `python3 -m unittest tests.test_vendor_assets -v`

Expected: FAIL because `tools.sync_vendor_assets` does not exist.

- [ ] **Step 3: Implement strict dataclasses, canonical-path checks, and offline verification**

```python
@dataclass(frozen=True)
class LockedFile:
    source: str
    target: str
    sha256: str

def safe_relative(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise VendorAssetError(f"unsafe asset path: {value}")
    return path

def verify_assets(lock_path: Path, vendor_root: Path) -> None:
    lock = load_lock(lock_path)
    expected = {item.target: item.sha256 for package in lock.packages for item in package.files}
    actual = {path.relative_to(vendor_root).as_posix() for path in vendor_root.rglob("*") if path.is_file()}
    if actual != set(expected):
        raise VendorAssetError("generated vendor file set does not match lock")
    for relative, digest in expected.items():
        if sha256_file(vendor_root / relative) != digest:
            raise VendorAssetError(f"{relative} SHA-256 mismatch")
```

- [ ] **Step 4: Run verifier tests**

Run: `python3 -m unittest tests.test_vendor_assets -v`

Expected: PASS for schema, inventory, digest, missing-license, and extra-file tests.

- [ ] **Step 5: Commit**

```bash
git add third_party tools/sync_vendor_assets.py tests/test_vendor_assets.py
git commit -m "build: add locked vendor asset verifier"
```

### Task 2: Safe fetch, extraction, and narrow clean

**Files:**
- Modify: `tools/sync_vendor_assets.py`
- Modify: `tests/test_vendor_assets.py`

**Interfaces:**
- Produces: `fetch_assets(lock_path: Path, vendor_root: Path, opener=urlopen) -> None`
- Produces: `clean_assets(lock_path: Path, vendor_root: Path) -> None`
- Produces: CLI subcommands `fetch`, `verify`, `clean`

- [ ] **Step 1: Add failing archive-safety tests using in-memory fixtures**

```python
def test_fetch_rejects_traversal_and_links(self):
    for member in ("../escape.js", "/escape.js", "package/link"):
        with self.subTest(member=member):
            archive = self.tar_fixture(member, b"payload", symlink=member.endswith("link"))
            with self.assertRaises(VendorAssetError):
                fetch_assets(self.lock_for_archive(archive), self.vendor_root, opener=self.opener(archive))

def test_clean_removes_only_locked_files(self):
    unknown = self.vendor_root / "manual.txt"
    unknown.write_text("keep", encoding="utf-8")
    clean_assets(self.lock_path, self.vendor_root)
    self.assertTrue(unknown.is_file())
```

- [ ] **Step 2: Run the focused safety tests**

Run: `python3 -m unittest tests.test_vendor_assets.VendorAssetTests.test_fetch_rejects_traversal_and_links tests.test_vendor_assets.VendorAssetTests.test_clean_removes_only_locked_files -v`

Expected: FAIL because fetch and clean are not implemented.

- [ ] **Step 3: Implement bounded HTTPS download, allowlisted extraction, atomic install, and clean**

```python
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

def clean_assets(lock_path: Path, vendor_root: Path) -> None:
    for package in load_lock(lock_path).packages:
        for item in package.files:
            (vendor_root / safe_relative(item.target)).unlink(missing_ok=True)
```

Reject non-HTTPS URLs, redirects to non-HTTPS, absolute/traversal paths,
duplicate normalized members, symlinks, hardlinks, devices, expansion beyond
`max_expanded_bytes`, archive/file digest mismatch, and missing licenses.

- [ ] **Step 4: Run all offline supply-chain tests**

Run: `python3 -m unittest tests.test_vendor_assets -v`

Expected: PASS without network access.

- [ ] **Step 5: Commit**

```bash
git add tools/sync_vendor_assets.py tests/test_vendor_assets.py
git commit -m "build: fetch vendor assets safely"
```

### Task 3: Lock and migrate the existing vendor inventory

**Files:**
- Modify: `third_party/assets.lock.json`
- Create: `THIRD_PARTY_NOTICES.md`
- Modify: `.gitignore`
- Modify: `epub_browser/asset_publisher.py`
- Modify: `epub_browser/processor.py`
- Modify: `epub_browser/site.py`
- Modify: `tests/test_asset_publisher.py`
- Modify: `tests/test_generated_reader_surfaces.py`
- Modify: `tests/test_static_asset_delivery.py`
- Delete: tracked third-party blobs after hydrated replacements pass tests

**Interfaces:**
- Consumes: verified files below `epub_browser/assets/vendor/<package>/`
- Produces: logical asset paths shaped as `vendor/<package>/<file>`

- [ ] **Step 1: Add failing provenance and publication assertions**

```python
def test_every_generated_vendor_file_is_locked_and_untracked(self):
    locked = locked_targets(Path("third_party/assets.lock.json"))
    tracked = subprocess.check_output(["git", "ls-files", "epub_browser/assets/vendor"], text=True).splitlines()
    self.assertEqual(tracked, [])
    self.assertIn("pdfjs/build/pdf.mjs", locked)

def test_reader_uses_versioned_vendor_paths(self):
    html = self._chapter_html()
    self.assertRegex(html, r"/assets/immutable/vendor/fontawesome/.+\.css")
    self.assertNotIn("fancybox.min.js", html)
```

- [ ] **Step 2: Run asset and generated-surface tests**

Run: `python3 -m unittest tests.test_asset_publisher tests.test_static_asset_delivery tests.test_generated_reader_surfaces -v`

Expected: FAIL while templates and tracked files use legacy paths.

- [ ] **Step 3: Populate exact locks and migrate runtime references**

Lock and hydrate Font Awesome, highlight.js, KaTeX, markdown-it, Mermaid,
pinyin-pro, SortableJS, web-highlighter, Fancybox, and PDF.js. Record exact
upstream URL, version, archive digest, byte
limits, installed file digests, SPDX identifier, and license file for each.
Update template and publisher logical paths to `vendor/<package>/<file>`; keep a
small authored lightbox adapter only if the new upstream API differs.

- [ ] **Step 4: Verify the migrated tree and reader assets**

Run: `python3 tools/sync_vendor_assets.py verify`

Run: `python3 -m unittest tests.test_asset_publisher tests.test_static_asset_delivery tests.test_generated_reader_surfaces -v`

Expected: all commands PASS and `git ls-files epub_browser/assets/vendor` prints nothing.

- [ ] **Step 5: Commit**

```bash
git add .gitignore THIRD_PARTY_NOTICES.md third_party epub_browser tests
git commit -m "build: migrate browser dependencies to locked assets"
```

### Task 4: Self-contained packaging and release jobs

**Files:**
- Modify: `setup.py`
- Modify: `MANIFEST.in`
- Modify: `.dockerignore`
- Modify: `Dockerfile`
- Modify: `.github/workflows/pypi.yml`
- Modify: `.github/workflows/gh-pages.yml`
- Modify: `tests/test_vendor_assets.py`

**Interfaces:**
- Consumes: `python tools/sync_vendor_assets.py fetch|verify`
- Produces: wheels, sdists, Docker final image, and Pages output containing verified vendor files

- [ ] **Step 1: Add failing package-inventory tests**

```python
def test_setup_packages_recursive_vendor_assets(self):
    completed = subprocess.run([sys.executable, "setup.py", "--version"], text=True, capture_output=True, check=True)
    self.assertRegex(completed.stdout.strip(), r"^\d+\.\d+\.\d+")
    self.assertIn("assets/vendor/**/*", Path("setup.py").read_text(encoding="utf-8"))

def test_release_jobs_fetch_and_verify_before_build(self):
    for path in (Path(".github/workflows/pypi.yml"), Path(".github/workflows/gh-pages.yml"), Path("Dockerfile")):
        source = path.read_text(encoding="utf-8")
        self.assertLess(source.index("sync_vendor_assets.py fetch"), source.index("python -m build"))
```

- [ ] **Step 2: Run packaging tests**

Run: `python3 -m unittest tests.test_vendor_assets -v`

Expected: FAIL because build metadata and workflows do not hydrate the locked tree.

- [ ] **Step 3: Update package data and build pipelines**

Use recursive package data for `assets/vendor/**/*`; include generated assets,
lock, notices, and licenses in sdist; run `fetch` then `verify` before
`python -m build`; build the Docker wheel in a hydrated builder stage and copy
only installed runtime files to the final stage.

- [ ] **Step 4: Build and inspect artifacts**

Run: `python3 tools/sync_vendor_assets.py verify`

Run: `python3 -m build`

Unpack the produced sdist into a temporary directory and run
`PIP_NO_INDEX=1 python3 -m build --wheel --no-isolation` there.

Run: `python3 -m unittest tests.test_vendor_assets tests.test_static_asset_delivery -v`

Expected: PASS without network access; direct wheel and sdist-built wheel
inventories contain all locked files and license notices. Inspect the Docker
final stage to confirm that it contains no archive cache, Git metadata, or
vendor downloader invocation.

- [ ] **Step 5: Commit**

```bash
git add setup.py MANIFEST.in .dockerignore Dockerfile .github/workflows tests/test_vendor_assets.py
git commit -m "build: package verified browser dependencies"
```

### Task 5: Supply-chain regression gate

**Files:**
- Modify: `README.md`
- Modify: `README.zh-CN.md`
- Modify: `third_party/README.md`

**Interfaces:**
- Produces: documented developer and release commands

- [ ] **Step 1: Document exact local and release commands**

```text
python3 tools/sync_vendor_assets.py fetch
python3 tools/sync_vendor_assets.py verify
python3 -m unittest tests.test_vendor_assets -v
python3 -m build
```

- [ ] **Step 2: Run the complete Python baseline before PDF code**

Run: `python3 -m unittest discover -s tests -p 'test_*.py'`

Expected: all baseline Python tests PASS.

- [ ] **Step 3: Run the complete JavaScript baseline**

Run: `node --test tests/test_*.js`

Expected: all baseline JavaScript tests PASS.

- [ ] **Step 4: Check repository hygiene**

Run: `git ls-files epub_browser/assets/vendor`

Expected: no output.

Run: `git diff --check`

Expected: no output.

- [ ] **Step 5: Commit documentation**

```bash
git add README.md README.zh-CN.md third_party/README.md
git commit -m "docs: explain locked browser asset workflow"
```
