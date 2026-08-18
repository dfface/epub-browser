# EPUB Browser SSG and Server Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the mixed static/server lifecycle with explicit `ssg` and `server` modes, safely migrate existing persistent data, and deliver a verified v2-compatible CLI, runtime, Docker image, and documentation set.

**Architecture:** Keep EPUB parsing and per-book rendering in a shared conversion core. Build SSG output through a transactional snapshot publisher, while Server owns a durable SQLite state store and a separately rebuildable incremental cache under one `server-dir`. A thin legacy adapter maps old invocations into the new configuration objects and never forks execution behavior.

**Tech Stack:** Python 3.8+, argparse, dataclasses, pathlib, SQLite, Starlette, Uvicorn, watchdog, unittest, Node.js built-in test runner.

**Spec:** `docs/superpowers/specs/2026-08-18-ssg-server-mode-architecture-design.md`

## Global Constraints

- The public modes are exactly `ssg` and `server`; `dev` is not a mode.
- Original EPUB files remain external and are never copied into durable Server storage.
- SSG output is a complete publication snapshot and contains no database or Server state.
- Server stores permanent state only under `<server-dir>/data` and derived output only under `<server-dir>/cache`.
- `data/` is never automatically deleted; cache deletion must preserve book IDs and all user data.
- Server book IDs are durable 22-character unpadded base64url UUIDv4 values; migrated legacy hashes remain valid IDs.
- SSG IDs are deterministic 22-character unpadded base64url SHA-256 prefixes.
- SSG defaults to `--base-path /`; Server defaults to `--host 127.0.0.1 --port 8000`.
- Old commands map into the new execution paths and remain supported throughout the new major release.
- Persistent migration is integrity-checked, versioned, idempotent, backed up, and fail-safe.
- A failed SSG build cannot change the previous publication; a failed Server book update cannot replace its previous cache.
- Docker explicitly binds `0.0.0.0`, preserves `/app/EpubBrowserFiles`, and reads source EPUBs from `/app/Library`.
- Full authentication, Server subpath hosting, partial SSG publication, and UI redesign are out of scope.
- Without `--log`, routine conversion, cache, watcher, path, and request diagnostics are silent and cannot disrupt tqdm; only actionable errors, one legacy migration hint, final results, and progress itself remain visible.

## Planned file structure

New focused modules:

- `epub_browser/cli.py`: new subcommand parsing, immutable config objects, and legacy argument translation.
- `epub_browser/urls.py`: base-path validation and public URL construction/rewriting.
- `epub_browser/models.py`: shared immutable book metadata and conversion result types.
- `epub_browser/identity.py`: deterministic SSG IDs, durable Server IDs, and source fingerprints.
- `epub_browser/reporting.py`: tqdm-safe user notices and `--log`-gated operational diagnostics.
- `epub_browser/site.py`: library shell and `book-metadata.json` publication independent of orchestration mode.
- `epub_browser/ssg.py`: complete snapshot staging, validation, activation, and rollback.
- `epub_browser/state.py`: SQLite schema, schema versioning, durable book registry, and existing state APIs.
- `epub_browser/migration.py`: legacy layout/database/JSON migration and migration state.
- `epub_browser/server_library.py`: source discovery, cache reconciliation, per-book conversion, and atomic cache activation.
- `epub_browser/runtime.py`: Server lifecycle, lock, watcher, readiness/degraded state, and Uvicorn startup.

Existing modules retained and narrowed:

- `epub_browser/main.py`: parse config and dispatch to `run_ssg` or `run_server`.
- `epub_browser/processor.py`: shared per-book EPUB conversion implementation.
- `epub_browser/asset_publisher.py`: content-addressed assets parameterized by URL policy.
- `epub_browser/library.py`: compatibility facade during the transition; no Server state ownership.
- `epub_browser/server.py`: Starlette routes and cache policy using explicit public/data paths.
- `epub_browser/watch.py`: filesystem event normalization feeding `ServerLibraryManager`.

---

### Task 1: Introduce the new CLI contract and legacy adapter

**Files:**
- Create: `epub_browser/cli.py`
- Create: `epub_browser/reporting.py`
- Create: `tests/test_cli.py`
- Create: `tests/test_reporting.py`
- Modify: `epub_browser/main.py`

**Interfaces:**
- Produces: `SSGConfig`, `ServerConfig`, `parse_cli(argv: Sequence[str])`, and `format_legacy_migration_hint(config) -> Optional[str]`.
- Produces: `Reporter(log_enabled: bool)` with `detail`, `notice`, `error`, and `result` methods.
- Consumes later: `run_ssg(config: SSGConfig) -> int` and `run_server(config: ServerConfig) -> int`.

- [ ] **Step 1: Write failing tests for new SSG and Server commands**

```python
from pathlib import Path
import unittest

from epub_browser.cli import SSGConfig, ServerConfig, parse_cli


class NewCommandTests(unittest.TestCase):
    def test_ssg_requires_output_and_normalizes_sources(self):
        config = parse_cli(["ssg", "books", "--output-dir", "dist", "--base-path", "/reader/"])
        self.assertIsInstance(config, SSGConfig)
        self.assertEqual(config.sources, (Path("books"),))
        self.assertEqual(config.output_dir, Path("dist"))
        self.assertEqual(config.base_path, "/reader/")

    def test_server_requires_persistent_or_ephemeral_storage(self):
        config = parse_cli(["server", "books", "--server-dir", "state"])
        self.assertIsInstance(config, ServerConfig)
        self.assertEqual(config.server_dir, Path("state"))
        self.assertFalse(config.ephemeral)
        self.assertEqual(config.host, "127.0.0.1")
        self.assertEqual(config.port, 8000)
```

- [ ] **Step 2: Run the new CLI tests and verify the module is missing**

Run: `python -m unittest tests.test_cli.NewCommandTests -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'epub_browser.cli'`.

- [ ] **Step 3: Add immutable configuration types and strict subcommand parsers**

```python
@dataclass(frozen=True)
class SSGConfig:
    sources: Tuple[Path, ...]
    output_dir: Path
    base_path: str = "/"
    legacy_invocation: bool = False


@dataclass(frozen=True)
class ServerConfig:
    sources: Tuple[Path, ...]
    server_dir: Optional[Path]
    ephemeral: bool
    watch: bool = False
    host: str = "127.0.0.1"
    port: int = 8000
    no_browser: bool = False
    log: bool = False
    legacy_sync_dir: Optional[Path] = None
    retain_legacy_temporary_dir: bool = False
    legacy_invocation: bool = False
```

Implement separate argparse subparsers. Make `--server-dir` and `--ephemeral` a required mutually exclusive group. Reject Server flags in SSG and SSG flags in Server through argparse rather than ignoring them.

- [ ] **Step 4: Add failing tests for legacy mappings and invalid mixed options**

```python
class LegacyCommandTests(unittest.TestCase):
    def test_old_output_dir_maps_to_persistent_server(self):
        config = parse_cli(["books", "--output-dir", "state", "--watch", "--keep-files"])
        self.assertIsInstance(config, ServerConfig)
        self.assertEqual(config.server_dir, Path("state"))
        self.assertTrue(config.watch)
        self.assertTrue(config.legacy_invocation)

    def test_old_no_server_maps_to_ssg(self):
        config = parse_cli(["books", "--no-server", "--output-dir", "dist"])
        self.assertEqual(config, SSGConfig((Path("books"),), Path("dist"), "/", True))

    def test_old_without_output_maps_to_ephemeral_server(self):
        config = parse_cli(["book.epub"])
        self.assertTrue(config.ephemeral)
        self.assertIsNone(config.server_dir)
```

Use `self.assertRaises(SystemExit)` for `ssg ... --port`, `server ... --base-path`, and a Server invocation with neither storage option.

- [ ] **Step 5: Implement legacy translation and migration hints**

Parse legacy flags with the old names, construct the equivalent new config, and return one concise hint such as:

```text
Legacy command syntax is deprecated; equivalent command: epub-browser server books --server-dir state --watch
```

Map `--sync-dir` to `legacy_sync_dir`. Treat persistent `--keep-files` as a compatibility no-op. Preserve temporary `--keep-files` through `retain_legacy_temporary_dir=True`.

- [ ] **Step 6: Replace `main.py` argument parsing with config dispatch**

Keep temporary adapter functions calling the existing pipeline so this commit remains runnable:

```python
def main(argv=None):
    config = parse_cli(sys.argv[1:] if argv is None else argv)
    hint = format_legacy_migration_hint(config)
    if hint:
        print(hint, file=sys.stderr)
    if isinstance(config, SSGConfig):
        return run_ssg(config)
    return run_server(config)
```

At this task, `run_ssg` and `run_server` must wrap the existing `EPUBLibrary`/`EPUBServer` behavior, and all later code calls them through the typed configs.

- [ ] **Step 7: Add a failing test for quiet and tqdm-safe reporting**

```python
def test_detail_is_silent_without_log_but_errors_remain_visible(self):
    reporter = Reporter(log_enabled=False)
    with redirect_stdout(StringIO()) as stdout, redirect_stderr(StringIO()) as stderr:
        reporter.detail("cache hit")
        reporter.error("conversion failed")
    self.assertEqual(stdout.getvalue(), "")
    self.assertEqual(stderr.getvalue(), "conversion failed\n")
```

Patch `tqdm.tqdm.write` in a second test, call `notice` while `progress_active=True`, and assert the message uses `tqdm.write` rather than built-in `print`.

- [ ] **Step 8: Implement the reporting boundary and route Task 1 output through it**

`detail` emits only when `log_enabled=True`. `notice`, `error`, and `result` are explicit user-facing messages. When `progress_active` is true they call `tqdm.write`; otherwise they write once to the selected standard stream. Pass one Reporter from `main` into mode runners instead of adding new raw `print` calls.

- [ ] **Step 9: Run CLI, reporting, and existing Python tests**

Run: `python -m unittest tests.test_cli tests.test_reporting -v`

Expected: PASS.

Run: `python -m unittest discover -s tests -p 'test_*.py'`

Expected: existing suite PASS.

- [ ] **Step 10: Commit the CLI seam**

```bash
git add epub_browser/cli.py epub_browser/reporting.py epub_browser/main.py tests/test_cli.py tests/test_reporting.py
git commit -m "feat: add ssg and server command modes"
```

### Task 2: Centralize base-path and asset URL generation

**Files:**
- Create: `epub_browser/urls.py`
- Create: `tests/test_urls.py`
- Modify: `epub_browser/asset_publisher.py`
- Modify: `tests/test_asset_publisher.py`
- Modify: `tests/test_static_asset_delivery.py`

**Interfaces:**
- Produces: `normalize_base_path(value: str) -> str`, `SiteURLs`, and `rewrite_root_urls(html: str, urls: SiteURLs) -> str`.
- `AssetPublisher(source_dir, output_dir, urls=SiteURLs("/"))` publishes public URLs while writing beneath `output_dir`.

- [ ] **Step 1: Write failing URL normalization and rewriting tests**

```python
from epub_browser.urls import SiteURLs, normalize_base_path, rewrite_root_urls


class URLTests(unittest.TestCase):
    def test_normalizes_project_path(self):
        self.assertEqual(normalize_base_path("reader"), "/reader/")

    def test_rejects_external_or_traversing_base_path(self):
        for value in ("https://example.com/reader/", "/a/../b/", "/reader/?x=1"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize_base_path(value)

    def test_rewrites_root_url_under_base_path(self):
        html = '<link href="/assets/app.css"><a href="/book/demo/">Read</a>'
        result = rewrite_root_urls(html, SiteURLs("/library/"))
        self.assertIn('href="/library/assets/app.css"', result)
        self.assertIn('href="/library/book/demo/"', result)
```

- [ ] **Step 2: Verify the URL tests fail**

Run: `python -m unittest tests.test_urls -v`

Expected: FAIL because `epub_browser.urls` does not exist.

- [ ] **Step 3: Implement `SiteURLs` and safe HTML root rewriting**

```python
@dataclass(frozen=True)
class SiteURLs:
    base_path: str = "/"

    def public(self, path: str) -> str:
        relative = path.lstrip("/")
        return posixpath.join(self.base_path, relative)

    def filesystem_relative(self, public_url: str) -> Path:
        prefix = self.base_path
        if not public_url.startswith(prefix):
            raise ValueError(f"URL is outside base path: {public_url}")
        return Path(public_url[len(prefix):])
```

Use an HTML attribute pattern limited to `href`, `src`, and `content` URL values. Do not rewrite protocol-relative or absolute external URLs.

- [ ] **Step 4: Add a failing asset test for non-root publication**

```python
def test_publish_uses_base_path_without_writing_nested_prefix(self):
    with tempfile.TemporaryDirectory() as source, tempfile.TemporaryDirectory() as output:
        Path(source, "app.js").write_text("app", encoding="utf-8")
        published = AssetPublisher(source, output, SiteURLs("/reader/")).publish()
        public_url = published.url_for("app.js")
        self.assertRegex(public_url, r"^/reader/assets/immutable/app\.[0-9a-f]{12}\.js$")
        self.assertTrue(Path(output, "assets", "immutable", public_url.rsplit("/", 1)[1]).is_file())
```

- [ ] **Step 5: Parameterize asset manifest, web manifest, CSS rewriting, and Service Worker URLs**

Keep filesystem targets under `output_dir/assets/...` while emitting base-prefixed public URLs. Ensure Manifest icon URLs, `start_url`, `scope`, Service Worker precache entries, and CSS-local asset URLs all use `SiteURLs.public`.

- [ ] **Step 6: Run focused and generated-surface tests**

Run: `python -m unittest tests.test_urls tests.test_asset_publisher tests.test_static_asset_delivery -v`

Expected: PASS.

- [ ] **Step 7: Commit URL policy support**

```bash
git add epub_browser/urls.py epub_browser/asset_publisher.py tests/test_urls.py tests/test_asset_publisher.py tests/test_static_asset_delivery.py
git commit -m "feat: centralize static site URL generation"
```

### Task 3: Define shared conversion models and stable identity functions

**Files:**
- Create: `epub_browser/models.py`
- Create: `epub_browser/identity.py`
- Create: `tests/test_identity.py`
- Modify: `epub_browser/processor.py`
- Modify: `tests/test_generated_reader_surfaces.py`

**Interfaces:**
- Produces: `BookMetadata`, `ConvertedBook`, `derive_ssg_book_id(metadata, spine_toc)`, `new_server_book_id()`, and `source_sha256(path)`.
- Modifies: `EPUBProcessor(..., book_id: Optional[str] = None, urls: Optional[SiteURLs] = None)` and `EPUBProcessor.convert() -> ConvertedBook`.

- [ ] **Step 1: Write failing identity tests**

```python
from epub_browser.identity import derive_ssg_book_id, new_server_book_id
from epub_browser.models import BookMetadata


class IdentityTests(unittest.TestCase):
    def test_server_id_is_22_character_url_safe_uuid(self):
        value = new_server_book_id()
        self.assertRegex(value, r"^[A-Za-z0-9_-]{22}$")

    def test_ssg_id_is_deterministic_and_path_independent(self):
        metadata = BookMetadata(title="Example", authors=("A",), tags=(), cover=None, language="en", epub_identifier="urn:isbn:1")
        first = derive_ssg_book_id(metadata, (("Chapter", "Text/one.xhtml", 0),))
        second = derive_ssg_book_id(metadata, (("Chapter", "Text/one.xhtml", 0),))
        self.assertEqual(first, second)
        self.assertRegex(first, r"^[A-Za-z0-9_-]{22}$")
```

- [ ] **Step 2: Verify identity tests fail**

Run: `python -m unittest tests.test_identity -v`

Expected: FAIL because the modules do not exist.

- [ ] **Step 3: Add immutable shared data models**

```python
@dataclass(frozen=True)
class BookMetadata:
    title: str
    authors: Tuple[str, ...]
    tags: Tuple[str, ...]
    cover: Optional[str]
    language: str
    epub_identifier: Optional[str]


@dataclass(frozen=True)
class ConvertedBook:
    book_id: str
    source_path: Path
    output_dir: Path
    metadata: BookMetadata
    chapter_count: int
```

- [ ] **Step 4: Implement exact identity and fingerprint algorithms**

Use `uuid.uuid4().bytes`, `base64.urlsafe_b64encode(...).decode().rstrip("=")` for Server IDs. For SSG, JSON-serialize normalized package identifier/title/authors and `(title, src, level)` TOC/spine tuples with sorted keys, SHA-256 the UTF-8 bytes, base64url encode, and take the first 22 characters. Stream source files into SHA-256 in 1 MiB chunks.

- [ ] **Step 5: Write failing processor tests for caller-supplied identity and safe extraction**

Extend the existing generated-reader fixture so constructing `EPUBProcessor(..., book_id="stable_id")`, parsing the EPUB, and converting it yields `ConvertedBook.book_id == "stable_id"` and writes into the caller-provided staging root rather than renaming from a TOC hash.

Create a minimal ZIP with an entry named `../outside.txt`, call `extract_epub()`, assert conversion fails with a path-safety error, and assert no file is written outside `extract_dir`.

- [ ] **Step 6: Refactor `EPUBProcessor` behind `convert()`**

Add optional `book_id` and `SiteURLs`. Preserve legacy `generate_hash()` only when no ID is supplied. Before extracting each ZIP member, resolve its destination and require it to remain under `extract_dir`; reject absolute paths, drive-prefixed paths, and `..` escapes. `convert()` executes safe extraction, container parsing, OPF parsing, ID derivation if needed, page generation, TOC generation, and resource copying, returning `ConvertedBook`. Existing lower-level methods remain usable by focused tests.

- [ ] **Step 7: Apply URL policy during generated book and chapter HTML creation**

Run content-addressed asset rewriting first and `rewrite_root_urls` second. Remove the generated runtime script that tries to repair root-relative resources after page load. Keep Server behavior unchanged with `SiteURLs("/")`.

- [ ] **Step 8: Run conversion and JavaScript surface tests**

Run: `python -m unittest tests.test_identity tests.test_generated_reader_surfaces -v`

Expected: PASS.

Run: `node --test tests/test_*.js`

Expected: PASS.

- [ ] **Step 9: Commit shared conversion identities**

```bash
git add epub_browser/models.py epub_browser/identity.py epub_browser/processor.py tests/test_identity.py tests/test_generated_reader_surfaces.py
git commit -m "refactor: separate book identity from conversion"
```

### Task 4: Extract mode-neutral library shell publication

**Files:**
- Create: `epub_browser/site.py`
- Create: `tests/test_site.py`
- Modify: `epub_browser/library.py`
- Modify: `tests/test_generated_reader_surfaces.py`
- Modify: `tests/test_static_asset_delivery.py`

**Interfaces:**
- Produces: `publish_library_shell(output_dir: Path, books: Sequence[LibraryBook], assets: PublishedAssets, urls: SiteURLs) -> None`.
- Produces: `LibraryBook(book_id, title, authors, tags, cover)`.
- Consumed by: SSG snapshot publication and Server cache metadata refresh.

- [ ] **Step 1: Write failing shell publication tests**

```python
def test_publish_library_shell_writes_sorted_metadata_and_base_paths(self):
    books = [
        LibraryBook("b", "Beta", ("B",), (), "/book/b/resources/cover.jpg"),
        LibraryBook("a", "Alpha", ("A",), ("tag",), None),
    ]
    publish_library_shell(root, books, assets, SiteURLs("/reader/"))
    payload = json.loads((root / "book-metadata.json").read_text(encoding="utf-8"))
    self.assertEqual([item["hash"] for item in payload], ["a", "b"])
    self.assertEqual(payload[1]["cover"], "/reader/book/b/resources/cover.jpg")
```

- [ ] **Step 2: Verify the shell test fails**

Run: `python -m unittest tests.test_site -v`

Expected: FAIL because `epub_browser.site` does not exist.

- [ ] **Step 3: Move library HTML and metadata generation into `site.py`**

Move the existing library template without visual changes. Accept an explicit immutable sequence of `LibraryBook` values, sort by `book_id` for deterministic metadata, apply `rewrite_asset_urls` and `rewrite_root_urls`, minify, and atomically replace `index.html` and `book-metadata.json` through temporary sibling files.

- [ ] **Step 4: Convert `EPUBLibrary` into a compatibility facade**

Keep source discovery and existing `add_book` behavior for compatibility tests, but delegate root publication to `publish_library_shell`. Remove direct Server database or lifecycle assumptions. Pass the active `SiteURLs` and asset manifest explicitly.

- [ ] **Step 5: Run shell, generated-surface, and static-delivery tests**

Run: `python -m unittest tests.test_site tests.test_generated_reader_surfaces tests.test_static_asset_delivery -v`

Expected: PASS with unchanged reader surfaces and no runtime base-path repair script.

- [ ] **Step 6: Commit the shell boundary**

```bash
git add epub_browser/site.py epub_browser/library.py tests/test_site.py tests/test_generated_reader_surfaces.py tests/test_static_asset_delivery.py
git commit -m "refactor: extract library site publication"
```

### Task 5: Implement transactional SSG publication

**Files:**
- Create: `epub_browser/ssg.py`
- Create: `tests/test_ssg.py`
- Modify: `epub_browser/main.py`
- Modify: `epub_browser/library.py`

**Interfaces:**
- Produces: `run_ssg(config: SSGConfig) -> int` and `SSGPublisher.build() -> Path`.
- Consumes: `SiteURLs`, `derive_ssg_book_id`, `EPUBProcessor.convert`, `AssetPublisher`, and `publish_library_shell`.

- [ ] **Step 1: Write a failing test that successful SSG output contains no Server state**

```python
def test_ssg_build_publishes_complete_static_snapshot(self):
    config = SSGConfig((example_epub,), output, "/reader/")
    self.assertEqual(run_ssg(config), 0)
    self.assertTrue((output / "index.html").is_file())
    self.assertTrue((output / "book-metadata.json").is_file())
    self.assertTrue((output / "assets" / "manifest.json").is_file())
    self.assertFalse((output / "epub-browser.db").exists())
    self.assertFalse((output / "data").exists())
```

- [ ] **Step 2: Write a failing rollback test**

Create an existing `output/index.html` containing `old`, inject a converter that raises for one input, assert `SSGBuildError`, and verify the original file still contains `old` and no staging directory remains.

- [ ] **Step 3: Run the SSG tests and verify failure**

Run: `python -m unittest tests.test_ssg -v`

Expected: FAIL because `run_ssg` and `SSGPublisher` do not exist.

- [ ] **Step 4: Implement discovery, deterministic IDs, and duplicate reporting**

Resolve all inputs before changing output. Parse enough metadata/TOC to derive IDs, collect collisions as `{book_id: [source paths]}`, and raise one `SSGBuildError` listing every conflicting group. Sort source work and final books deterministically.

- [ ] **Step 5: Implement sibling staging and rollback-capable activation**

Create staging with `tempfile.mkdtemp(prefix=f".{output.name}.staging-", dir=output.parent)`. Build everything there. On success, rename the prior output to `.<name>.previous-<id>`, rename staging to output, restore previous on activation failure, and remove previous only after success. Reject filesystem roots, sources, and source EPUB paths as output targets.

- [ ] **Step 6: Implement complete snapshot validation**

Validate book directories, `toc.json` chapter references, metadata agreement, asset manifest targets, Manifest icons, Service Worker precache targets, base-path prefixes, and absence of `epub-browser.db`, `data`, `migration-state.json`, local absolute source paths, and staging paths.

- [ ] **Step 7: Make all-book failure atomic and diagnostic**

Use the existing bounded thread pool, collect each source exception, finish outstanding jobs, then raise one `SSGBuildError` containing every failed source and message. Do not activate partial output.

- [ ] **Step 8: Dispatch SSG configs from `main.py`**

Return exit status `4` for build failures and `0` after successful publication. Print `Files generated in: <absolute output>` only after activation.

- [ ] **Step 9: Run SSG, static asset, and generated surface suites**

Run: `python -m unittest tests.test_ssg tests.test_static_asset_delivery tests.test_generated_reader_surfaces -v`

Expected: PASS.

- [ ] **Step 10: Commit SSG mode**

```bash
git add epub_browser/ssg.py epub_browser/main.py epub_browser/library.py tests/test_ssg.py
git commit -m "feat: publish transactional ssg snapshots"
```

### Task 6: Add the versioned Server state store and durable books registry

**Files:**
- Create: `epub_browser/state.py`
- Create: `tests/test_state.py`
- Modify: `epub_browser/server.py`
- Modify: `tests/test_server.py`

**Interfaces:**
- Produces: `StateStore(database_path: Path)`, `BookRecord`, and `DB_SCHEMA_VERSION`.
- Key methods: `initialize()`, `resolve_book(...)`, `update_book_version(...)`, `mark_missing(...)`, `active_books()`, and existing annotation/bookshelf/progress operations.

- [ ] **Step 1: Write failing schema and durable identity tests**

```python
class StateStoreTests(unittest.TestCase):
    def test_initialize_creates_versioned_existing_and_books_tables(self):
        store = StateStore(path)
        store.initialize()
        with sqlite3.connect(path) as connection:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertEqual(version, DB_SCHEMA_VERSION)
        self.assertTrue({"annotations", "bookshelves", "reading_progress", "books"} <= tables)

    def test_content_update_keeps_book_id(self):
        record = store.resolve_book(source, "epub-id", "fingerprint-a", metadata)
        updated = store.update_book_version(record.book_id, "fingerprint-b", metadata)
        self.assertEqual(updated.book_id, record.book_id)
```

- [ ] **Step 2: Verify state tests fail**

Run: `python -m unittest tests.test_state -v`

Expected: FAIL because `epub_browser.state` does not exist.

- [ ] **Step 3: Implement schema initialization and versioning**

Create all existing tables with their compatible columns and add `books`. Wrap each version transition in `BEGIN IMMEDIATE`, update `PRAGMA user_version` only at commit, reject versions greater than `DB_SCHEMA_VERSION`, and preserve existing `book_hash` API columns.

- [ ] **Step 4: Implement durable registry operations**

`resolve_book` first matches canonical source path. For an unambiguous offline move, match the unique inactive row with the same non-empty EPUB identifier and fingerprint. Otherwise allocate `new_server_book_id()`. `mark_missing` sets `active=0` without cascading deletion. Store metadata as normalized JSON.

- [ ] **Step 5: Move direct SQLite access in Starlette handlers behind `StateStore`**

Keep response payloads and status codes compatible. Inject a `StateStore` into `create_app` instead of relying on module-global `DATABASE_PATH`. Tests must be able to create two isolated apps without cross-test global state.

- [ ] **Step 6: Run state and Server API tests**

Run: `python -m unittest tests.test_state tests.test_server -v`

Expected: PASS.

- [ ] **Step 7: Commit persistent Server state**

```bash
git add epub_browser/state.py epub_browser/server.py tests/test_state.py tests/test_server.py
git commit -m "feat: add durable server book registry"
```

### Task 7: Implement automatic legacy data and layout migration

**Files:**
- Create: `epub_browser/migration.py`
- Create: `tests/test_migration.py`
- Modify: `epub_browser/state.py`
- Create: `epub_browser/runtime.py`

**Interfaces:**
- Produces: `MigrationManager(server_dir: Path, legacy_sync_dir: Optional[Path])` and `MigrationResult`.
- Key methods: `prepare_data() -> MigrationResult`, `record_cache_reconciled()`, and `finish_legacy_public_retirement()`.
- Consumes: `StateStore.initialize()` and legacy ID derivation from `EPUBProcessor` metadata/TOC.

- [ ] **Step 1: Write failing migration tests for current and older layouts**

```python
def test_migrates_root_database_with_backup_and_schema_upgrade(self):
    create_legacy_database(server_dir / "epub-browser.db")
    result = MigrationManager(server_dir, None).prepare_data()
    self.assertEqual(result.database_path, server_dir / "data" / "epub-browser.db")
    self.assertTrue(result.backup_path.is_file())
    self.assertFalse((server_dir / "epub-browser.db").exists())
    self.assertTrue((server_dir / "data" / "migration-state.json").is_file())

def test_migrates_annotations_database_when_it_is_only_candidate(self):
    create_legacy_database(server_dir / "annotations.db")
    result = MigrationManager(server_dir, None).prepare_data()
    self.assertTrue(result.database_path.is_file())
```

- [ ] **Step 2: Add conflict, corruption, and idempotency tests**

Assert migration raises `MigrationConflictError` without modifying files when both root candidates exist. Assert a failed `PRAGMA integrity_check` leaves the source untouched. Run `prepare_data()` twice and assert one backup and unchanged rows.

- [ ] **Step 3: Run migration tests and verify failure**

Run: `python -m unittest tests.test_migration -v`

Expected: FAIL because `epub_browser.migration` does not exist.

- [ ] **Step 4: Implement explicit database candidate selection**

Treat `data/epub-browser.db` as authoritative. With no data database, accept exactly one of root `epub-browser.db` and root `annotations.db`; reject both. Run integrity check, compute the source digest, copy to a temporary data file, create the timestamped backup, initialize schema, validate, atomically install data DB, write migration state atomically, verify backup digest, then remove the root source.

- [ ] **Step 5: Implement legacy bookshelf JSON import**

Parse names with `^epub-browser-bookshelf-(.+)-(\d+)\.json$`, validate JSON objects, choose the highest version per username across the explicit legacy directory and Server root, and upsert only when SQLite contains an older version. Never delete source JSON.

- [ ] **Step 6: Implement legacy book identity correlation**

Load old `book-metadata.json` hashes and old `book/<hash>/` names. During first source reconciliation, compute the legacy TOC hash for candidate EPUBs. Reuse a legacy hash only for a unique match; leave ambiguous and unmatched database state untouched.

- [ ] **Step 7: Implement legacy public retirement phases**

Keep exact known root artifacts until all active discovered sources have valid new caches. Move them into `cache/legacy-public` after full reconciliation, set the layout phase in migration state, and delete that cache only on the next fully successful startup.

- [ ] **Step 8: Map migration failures to exit status 3**

Create `runtime.py` with a provisional `run_server(config)` wrapper that performs `prepare_data()` before delegating to the existing Server startup. On migration failure, print the actionable path-specific message to stderr and return `3`. Task 9 replaces the remaining legacy startup delegation.

- [ ] **Step 9: Run migration and state tests**

Run: `python -m unittest tests.test_migration tests.test_state -v`

Expected: PASS.

- [ ] **Step 10: Commit automatic migration**

```bash
git add epub_browser/migration.py epub_browser/state.py epub_browser/runtime.py tests/test_migration.py
git commit -m "feat: migrate legacy server data safely"
```

### Task 8: Build the incremental Server library cache

**Files:**
- Create: `epub_browser/server_library.py`
- Create: `tests/test_server_library.py`
- Modify: `epub_browser/watch.py`
- Modify: `epub_browser/processor.py`
- Modify: `epub_browser/site.py`

**Interfaces:**
- Produces: `ServerLibraryManager`, `ReconcileSummary`, and `ConversionFailure`.
- Key methods: `prepare_public_shell()`, `reconcile()`, `queue_path(path)`, `mark_deleted(path)`, `shutdown()`.
- Consumes: `StateStore`, `EPUBProcessor.convert`, `AssetPublisher`, `publish_library_shell`, and `MigrationManager.record_cache_reconciled()`.

- [ ] **Step 1: Write failing cache reuse and cache rebuild tests**

```python
def test_second_reconcile_reuses_unchanged_book_cache(self):
    first = manager.reconcile()
    converter.reset_mock()
    second = manager.reconcile()
    self.assertEqual(first.converted, 1)
    self.assertEqual(second.reused, 1)
    converter.assert_not_called()

def test_cache_deletion_rebuilds_without_changing_book_id(self):
    original = manager.reconcile().active_books[0]
    shutil.rmtree(server_dir / "cache")
    rebuilt = manager.reconcile().active_books[0]
    self.assertEqual(rebuilt.book_id, original.book_id)
```

- [ ] **Step 2: Add failing atomic-update, deletion, and source-boundary tests**

Inject a converter failure after an old cache exists and assert the old chapter remains and the manager reports degraded. Delete the source and assert it disappears from public metadata while annotations and the inactive `books` row remain. Restore the same source and assert its ID returns.

Create a source-directory symlink that points outside the declared source root and assert discovery ignores it. Assert construction fails when `server-dir` is inside a source directory or a source is inside `server-dir`.

- [ ] **Step 3: Run Server library tests and verify failure**

Run: `python -m unittest tests.test_server_library -v`

Expected: FAIL because `epub_browser.server_library` does not exist.

- [ ] **Step 4: Implement source discovery and derived catalog**

Extract hidden-component-aware recursive discovery from `EPUBLibrary` into `server_library.py`. Canonicalize sources, do not follow directory symlinks that escape a declared source root, reject managed/source nesting, and write `cache/catalog.json` atomically from StateStore plus cache validation results. Treat it as derived data only.

- [ ] **Step 5: Implement cache validation and per-book staging**

Store each active book at `cache/public/book/<book-id>`. Validate required index, TOC, chapters, resources referenced by metadata, and recorded fingerprint. Convert in `cache/staging/<job-id>`, verify the source fingerprint has not changed, rename the existing book to a rollback sibling, activate staging, update StateStore, then remove rollback.

- [ ] **Step 6: Implement deterministic public-shell refresh**

Publish shared assets and base shell under `cache/public`. After each successful activation/deactivation batch, read active records from StateStore and atomically rewrite `index.html`, `book-metadata.json`, and derived `catalog.json`.

- [ ] **Step 7: Implement bounded conversion concurrency and per-source coalescing**

Use a bounded `ThreadPoolExecutor`. Maintain one pending/latest fingerprint per canonical source. A second change replaces the pending version; an in-flight stale job cannot commit after the expected fingerprint check fails.

- [ ] **Step 8: Adapt watchdog events to manager operations**

`watch.py` should normalize create, modify, move, and delete events and call `queue_path`, `mark_deleted`, or move-aware registry update. Remove the separate watcher process and copied in-memory `EPUBLibrary` model.

- [ ] **Step 9: Run cache, watcher, generated-surface, and JavaScript tests**

Run: `python -m unittest tests.test_server_library tests.test_watch tests.test_generated_reader_surfaces -v`

Expected: PASS.

Run: `node --test tests/test_*.js`

Expected: PASS.

- [ ] **Step 10: Commit incremental Server caching**

```bash
git add epub_browser/server_library.py epub_browser/watch.py epub_browser/processor.py epub_browser/site.py tests/test_server_library.py tests/test_watch.py
git commit -m "feat: add incremental server book cache"
```

### Task 9: Integrate Server runtime, health states, locks, and safe networking

**Files:**
- Modify: `epub_browser/runtime.py`
- Create: `tests/test_runtime.py`
- Modify: `epub_browser/server.py`
- Modify: `epub_browser/main.py`
- Modify: `tests/test_server.py`
- Modify: `tests/test_watch.py`

**Interfaces:**
- Produces: `run_server(config: ServerConfig) -> int`, `RuntimeStatus`, and `create_app(public_dir: Path, state_store: StateStore, status: RuntimeStatus)`.
- Consumes: `MigrationManager`, `ServerLibraryManager`, watchdog observer, and Uvicorn.

- [ ] **Step 1: Write failing readiness and degraded-health tests**

```python
def test_ready_rejects_before_base_shell_and_reports_after_ready(self):
    status = RuntimeStatus()
    client = TestClient(create_app(public_dir, store, status))
    self.assertEqual(client.get("/api/ready").status_code, 503)
    status.mark_ready()
    self.assertEqual(client.get("/api/ready").json()["state"], "ready")

def test_degraded_health_reports_counts_without_paths(self):
    status.mark_degraded(failed_books=2, queued_tasks=1)
    payload = client.get("/api/health").json()
    self.assertEqual(payload["failed_books"], 2)
    self.assertNotIn(str(source_root), json.dumps(payload))
```

- [ ] **Step 2: Add failing lock and persistent shutdown tests**

Start one runtime lock, assert a second runtime for the same `server-dir` returns status `5`. Stop a persistent runtime and assert `data/epub-browser.db` and `cache/public` remain. Stop ephemeral runtime and assert only its created temporary root is removed.

- [ ] **Step 3: Run runtime tests and verify failure**

Run: `python -m unittest tests.test_runtime -v`

Expected: FAIL because runtime status and lock behavior are absent.

- [ ] **Step 4: Implement runtime state and process locking**

Model `starting`, `migrating`, `scanning`, `ready`, and `degraded` under a thread lock. Create `.server.lock` exclusively with PID and start time, detect stale locks safely, and always release the lock in `finally` without deleting data/cache.

- [ ] **Step 5: Refactor Starlette creation around explicit dependencies**

Mount `CachedStaticFiles(directory=public_dir)`. Add `/api/health` and `/api/ready` before the static mount. Reject state-changing requests with 503 until ready. Remove module-global database state and unreachable legacy HTTP-server code after equivalent tests cover Starlette/Uvicorn behavior.

- [ ] **Step 6: Run migration, cache, watcher, and Uvicorn in one Server process**

Prepare migration and the base public shell, perform quick cache reconciliation, then construct Uvicorn. Start watchdog in the same process only with `--watch`. A stop event closes the observer, drains StateStore commits, shuts down conversion workers, and requests Uvicorn exit.

- [ ] **Step 7: Implement safe bind and browser behavior**

Use `config.host` exactly, defaulting through CLI to `127.0.0.1`. Print the actual local URL. Open a browser only when `--no-browser` is absent. Do not perform an external DNS socket connection to discover a LAN address.

- [ ] **Step 8: Map stable exit statuses**

Return `2` for parser errors through argparse, `3` for migration/database errors, `4` from SSG failures, and `5` for bind, lock, permission, or runtime startup failures. Normal shutdown returns `0`.

- [ ] **Step 9: Run Server runtime and API suites**

Run: `python -m unittest tests.test_runtime tests.test_server tests.test_server_library tests.test_watch -v`

Expected: PASS.

- [ ] **Step 10: Commit Server runtime integration**

```bash
git add epub_browser/runtime.py epub_browser/server.py epub_browser/main.py tests/test_runtime.py tests/test_server.py tests/test_watch.py
git commit -m "feat: run stateful server from isolated storage"
```

### Task 10: Verify end-to-end legacy upgrades and mode isolation

**Files:**
- Create: `tests/test_mode_integration.py`
- Modify: `tests/test_migration.py`
- Modify: `tests/test_ssg.py`
- Modify: `tests/test_server_library.py`
- Modify: `tests/test_static_asset_delivery.py`

**Interfaces:**
- Validates all public interfaces from Tasks 1-9 together.

- [ ] **Step 1: Add a complete legacy-upgrade integration fixture**

Build a current-layout root with `epub-browser.db`, `book-metadata.json`, `book/<legacy-hash>`, `assets`, and legacy bookshelf JSON. Insert one annotation, bookshelf record, and reading-progress row. Start the new runtime through a legacy `parse_cli` invocation and stop after reconciliation.

- [ ] **Step 2: Assert migration and identity preservation**

Verify the annotation and progress still reference the same legacy ID, the book registry uses it, the new cache URL is `/book/<legacy-id>/`, the old DB has a verified backup, and restart with `server --server-dir` reuses cache without conversion.

- [ ] **Step 3: Add SSG/Server isolation assertions**

Build SSG and Server from the same EPUB. Assert SSG has no database/data/cache markers, Server has no public files at its root, deleting Server cache leaves StateStore rows, and rebuilding restores the durable Server ID.

- [ ] **Step 4: Add quiet CLI output assertions**

Run SSG through its real CLI runner with `--log` absent and a captured stdout/stderr. Assert routine strings such as `Library base directory`, per-book processing lines, cache hits, and watcher events are absent while the final result and progress output remain. Repeat with `--log` and assert operational detail is emitted through `Reporter`.

- [ ] **Step 5: Add non-root static-host link verification**

Parse every generated HTML `href`/`src`, Manifest icon/start/scope entry, metadata cover, and Service Worker precache URL. Assert internal URLs begin `/project/`, map to an existing output file after removing the prefix, and contain no runtime repair script.

- [ ] **Step 6: Run the complete Python and JavaScript suites**

Run: `python -m unittest discover -s tests -p 'test_*.py'`

Expected: PASS.

Run: `node --test tests/test_*.js`

Expected: PASS.

- [ ] **Step 7: Commit integration coverage**

```bash
git add tests/test_mode_integration.py tests/test_migration.py tests/test_ssg.py tests/test_server_library.py tests/test_static_asset_delivery.py
git commit -m "test: cover ssg and server upgrade flows"
```

### Task 11: Update Docker, README, release documentation, and version

**Files:**
- Modify: `Dockerfile`
- Modify: `README.md`
- Modify: `epub_browser/version.py`
- Create: `docs/releases/v2.0.0.md`
- Create: `docs/migration-v2.md`
- Modify: `setup.py` only if CLI package data or entry point behavior requires it

**Interfaces:**
- Documents and packages the public behavior verified by Tasks 1-10.

- [ ] **Step 1: Add a documentation consistency test**

In `tests/test_mode_integration.py`, read Dockerfile and README and assert Docker uses `epub-browser server`, `--server-dir=/app/EpubBrowserFiles`, `--host=0.0.0.0`, and does not use `--keep-files`; assert README contains both `epub-browser ssg` and `epub-browser server` examples.

- [ ] **Step 2: Update Dockerfile for persistent Server mode**

Use this command shape:

```dockerfile
CMD ["epub-browser", "server", "/app/Library", "--server-dir=/app/EpubBrowserFiles", "--legacy-sync-dir=/app/SyncData", "--watch", "--host=0.0.0.0", "--no-browser", "--port=80"]
```

Document `/app/Library` as read-only input and `/app/EpubBrowserFiles` as the required read-write persistent volume. Keep `/app/SyncData` only for legacy import.

- [ ] **Step 3: Rewrite README around the two product modes**

Lead with a mode choice. Include SSG root and GitHub Pages `--base-path` examples, persistent local Server and explicit LAN examples, storage trees, backup behavior, cache deletion safety, Docker volumes, localhost security default, and the warning against direct public exposure without proxy authentication.

- [ ] **Step 4: Write the v2 migration guide**

Document exact old-to-new command mappings, first-start migration sequence, backup paths, database conflict messages, rollback by restoring `data/backups/pre-migration-*.db`, legacy JSON import, and the fact that legacy syntax is supported for the entire v2 major line.

- [ ] **Step 5: Add bilingual v2.0.0 release notes and bump version**

Mark the command and directory architecture as breaking, explain the compatibility adapter and automatic migration, show the Docker change, and list safe upgrade steps before feature summaries. Set `VERSION = "2.0.0"`.

- [ ] **Step 6: Run documentation tests and package smoke checks**

Run: `python -m unittest tests.test_mode_integration -v`

Expected: PASS.

Run: `python -m epub_browser.main --help`

Expected: help names `ssg` and `server`.

Run: `python -m epub_browser.main ssg --help && python -m epub_browser.main server --help`

Expected: each mode lists only its applicable options.

- [ ] **Step 7: Commit release-facing changes**

```bash
git add Dockerfile README.md epub_browser/version.py docs/releases/v2.0.0.md docs/migration-v2.md tests/test_mode_integration.py setup.py
git commit -m "docs: publish ssg and server v2 migration guide"
```

### Task 12: Final verification and merge-readiness review

**Files:**
- Modify only files required to fix failures found by this task.
- Review: all files changed from `main...HEAD`.

**Interfaces:**
- Produces a clean, tested branch ready to merge into `main`.

- [ ] **Step 1: Run Python syntax and import verification**

Run: `python -m compileall -q epub_browser tests`

Expected: exit status 0.

- [ ] **Step 2: Run the complete automated suites**

Run: `python -m unittest discover -s tests -p 'test_*.py'`

Expected: PASS.

Run: `node --test tests/test_*.js`

Expected: PASS.

- [ ] **Step 3: Build and inspect a real SSG example**

Run:

```bash
ssg_check_dir="$(mktemp -d)"
python -m epub_browser.main ssg examples/Yi\ Jiu\ Ba\ Si\ -\ Qiao\ Zhi\ _Ao\ Wei\ Er.epub --output-dir "$ssg_check_dir/site" --base-path /demo/
test -f "$ssg_check_dir/site/index.html"
test -f "$ssg_check_dir/site/book-metadata.json"
test ! -e "$ssg_check_dir/site/epub-browser.db"
```

Expected: command and assertions succeed. Remove only the printed `mktemp` directory after recording results.

- [ ] **Step 4: Run a persistent Server smoke test without opening a browser**

Start Server on `127.0.0.1` with a temporary `--server-dir`, poll `/api/ready`, verify the database is under `data/`, public files are under `cache/public/`, stop it with SIGTERM, and verify both remain. Restart and assert the same book ID is returned without a conversion log entry.

- [ ] **Step 5: Run a legacy migration smoke test**

Create a disposable current-layout directory through the compatibility test fixture, invoke the legacy command, verify backup/data/cache placement and API state, then restart through the new Server command.

- [ ] **Step 6: Review diff quality and repository cleanliness**

Run: `git diff --check main...HEAD`

Expected: no whitespace errors.

Run: `git status --short`

Expected: no uncommitted files.

Review every changed file for accidental source paths, dead legacy orchestration, duplicated CLI logic, data deletion, debug output, or credentials.

- [ ] **Step 7: Commit any verification fixes**

If verification required changes, commit only those fixes:

```bash
git add -u
git commit -m "fix: address ssg server verification findings"
```

If no changes were required, do not create an empty commit.

- [ ] **Step 8: Record merge readiness**

Capture the final commit list, test commands and results, migration smoke result, SSG smoke result, and any known non-blocking limitations. Confirm the branch has no required work remaining before marking the persistent goal complete.
