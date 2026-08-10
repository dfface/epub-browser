# EPUB Browser Performance Architecture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make library startup and continuous reading fast in Docker and static Pages through versioned releases, lazy library loading, chapter streaming, an extensible UI-profile system, and a lean ASGI delivery path.

**Architecture:** `ReleasePublisher` owns staging and atomic current-release publication. `LibrarySnapshot` and `ChapterStream` are browser-facing deep modules with narrow interfaces; `ChapterSource` supplies generated fragments. Docker maps stable URLs through `StaticDelivery`, while the static exporter materializes the same current release at the output root.

**Tech Stack:** Python 3.9+, `uvicorn`, `starlette`, `unittest`, browser-compatible ES5 scripts, `node --test`.

## Global Constraints

- Python runtime floor is exactly `>=3.9`.
- Add only `uvicorn` and `starlette` as runtime dependencies; do not add Nginx/OpenResty or a JS bundler.
- Keep all existing CLI flags, Docker invocation, stable `/book/<hash>/...` URLs, Pages output, Kindle/Silk support, local IndexedDB annotations, and local bookshelf behavior.
- Add `--ui=<profile-id>`, defaulting to the new `reader` profile. `--ui=legacy` must render the existing reader experience while sharing the same conversion release and stable URLs.
- Do not generate or store cover thumbnails.
- Browser scripts use IIFEs plus a `window.EpubBrowser` namespace; do not require native ES modules.
- The shared `I18n` service owns `zh-CN` and `en`; UI profiles contain message keys rather than translated persistence values. Render `zh-CN` without JavaScript, then choose saved preference, browser language, or `zh-CN` in that order.
- Keep at most five chapters in a continuous-reading DOM window.

---

## File structure

- Create: `epub_browser/release.py` — staging, publication, rollback, and static export.
- Create: `epub_browser/webapp.py` — Starlette routes, `StaticDelivery`, and API adapter registration.
- Create: `epub_browser/assets/runtime.js` — namespace, capability detection, module bootstrap.
- Create: `epub_browser/assets/library-snapshot.js` — manifest/snapshot fetch and incremental card rendering.
- Create: `epub_browser/assets/chapter-source.js` — fragment fetch, parse, cache, cancellation.
- Create: `epub_browser/assets/chapter-stream.js` — prefetch, append, trim, and position preservation.
- Create: `epub_browser/assets/reader-navigation.js` — MPA-first same-book progressive navigation and history/focus lifecycle.
- Create: `epub_browser/assets/reader-shell.js` — persistent immersive reader controls and delayed loading feedback.
- Create: `epub_browser/assets/i18n.js` and versioned `epub_browser/assets/locales/` catalogs — locale selection, formatting, and message lookup.
- Create: `tests/test_release.py`, `tests/test_webapp.py` — Python regression seams.
- Create: `tests/js/library-snapshot.test.js`, `tests/js/chapter-stream.test.js` — `node --test` seams.
- Modify: `setup.py`, `Dockerfile`, `epub_browser/main.py`, `epub_browser/library.py`, `epub_browser/watch.py`, `epub_browser/processor.py`, `epub_browser/server.py`, and generated-page assets/templates.

## Task 1: Establish runtime and regression seams

**Files:**
- Modify: `setup.py`
- Create: `tests/__init__.py`
- Create: `tests/test_webapp.py`
- Create: `tests/js/chapter-stream.test.js`

**Interfaces:**
- Produces: `python -m unittest discover -s tests -v` and `node --test tests/js/*.test.js` commands used by every later task.

- [ ] **Step 1: Add a failing static-response test**

```python
# tests/test_webapp.py
class StaticDeliveryTests(unittest.TestCase):
    def test_static_delivery_sets_validators_and_honors_range(self):
        app = create_app(self.release_root)
        response = request(app, "GET", "/book/a/chapter_1.html", {"Range": "bytes=0-3"})
        self.assertEqual(response.status, 206)
        self.assertEqual(response.headers["accept-ranges"], "bytes")
        self.assertIn("etag", response.headers)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m unittest tests.test_webapp.StaticDeliveryTests.test_static_delivery_sets_validators_and_honors_range -v`

Expected: FAIL because `epub_browser.webapp` does not exist.

- [ ] **Step 3: Add a failing UI-profile CLI and generation test**

Add parser/unit coverage that omitted `--ui` resolves to `reader`,
`--ui=legacy` resolves to `legacy`, and an unknown profile is rejected with a
clear argparse error. Add processor/template coverage that the two profiles
produce the same stable chapter URL and release metadata while selecting only
their own template and entry assets.

Add locale contract tests: a no-JavaScript generated page has `lang="zh-CN"`
and Chinese product labels; `I18n` chooses saved preference before browser
language and browser language before `zh-CN`; switching from `zh-CN` to `en`
does not alter chapter URLs or local-progress keys; every referenced message
key exists in both catalogs or uses the declared English fallback.

- [ ] **Step 4: Set supported runtime dependencies**

```python
# setup.py
python_requires=">=3.9",
install_requires=["tqdm", "minify_html", "watchdog", "uvicorn", "starlette"],
```

Create an empty `tests/__init__.py`; keep JavaScript tests compatible with Node's built-in test runner and use `require('node:test')`.

- [ ] **Step 5: Add a minimal `create_app` placeholder only sufficient to import**

```python
# epub_browser/webapp.py
def create_app(release_root):
    raise NotImplementedError("StaticDelivery is implemented in Task 6")
```

The test must still fail with `NotImplementedError`, proving it reaches the intended seam.

- [ ] **Step 6: Commit the harness**

```bash
git add setup.py tests epub_browser/webapp.py
git commit -m "test: establish performance architecture seams"
```

## Task 2: Publish immutable release snapshots

**Files:**
- Create: `epub_browser/release.py`
- Modify: `epub_browser/library.py`
- Modify: `epub_browser/watch.py`
- Create: `tests/test_release.py`

**Interfaces:**
- Produces: `ReleasePublisher(output_dir).stage(build)`, `publish(stage)`, `current_root()`, `rollback()`, and `export_static(destination)`.
- Consumes: a callable that writes a complete generated library tree to a supplied staging directory.

- [ ] **Step 1: Write failing publication tests**

```python
def test_publish_switches_current_atomically_and_keeps_previous(self):
    publisher = ReleasePublisher(self.output)
    first = publisher.stage(lambda root: write_file(root, "book/a/chapter_1.html", "old"))
    publisher.publish(first)
    second = publisher.stage(lambda root: write_file(root, "book/a/chapter_1.html", "new"))
    publisher.publish(second)
    self.assertEqual(read_file(publisher.current_root(), "book/a/chapter_1.html"), "new")
    self.assertEqual(read_file(publisher.previous_root(), "book/a/chapter_1.html"), "old")
```

- [ ] **Step 2: Run the publication test to verify it fails**

Run: `python -m unittest tests.test_release.ReleasePublisherTests.test_publish_switches_current_atomically_and_keeps_previous -v`

Expected: FAIL because `ReleasePublisher` does not exist.

- [ ] **Step 3: Implement `ReleasePublisher` with stable-path indirection**

```python
class ReleasePublisher:
    def stage(self, build):
        stage = Path(tempfile.mkdtemp(dir=self.staging_dir, prefix="release-"))
        build(stage)
        return stage

    def publish(self, stage):
        release = self.releases_dir / self.release_id(stage)
        os.replace(stage, release)
        atomic_write_text(self.root / "current.json", json.dumps({"release": release.name}))
        self.cleanup_releases(keep=2)
```

`current.json` is the stable seam: Docker resolves request paths beneath its release, while `export_static` copies the current release tree to the static output root. Do not expose release IDs in browser URLs.

- [ ] **Step 4: Route generation through staging**

Change `EPUBLibrary` to accept a supplied base directory without deciding publication. In `main.py` build the initial library in `ReleasePublisher.stage`; in `watch.py` serialize publication through one lock, build a complete next snapshot, then call `publish`. A failed conversion leaves `current.json` unchanged.

- [ ] **Step 5: Run tests and commit**

Run: `python -m unittest tests.test_release -v`

Expected: PASS for publish, rollback, failed-stage preservation, and `export_static` stable paths.

```bash
git add epub_browser/release.py epub_browser/library.py epub_browser/watch.py epub_browser/main.py tests/test_release.py
git commit -m "feat: publish generated libraries as atomic snapshots"
```

## Task 3: Add LibrarySnapshot and remove eager library work

**Files:**
- Modify: `epub_browser/library.py`
- Create: `epub_browser/assets/runtime.js`
- Create: `epub_browser/assets/library-snapshot.js`
- Modify: `epub_browser/assets/library.js`
- Modify: `epub_browser/assets/library.css`
- Create: `tests/js/library-snapshot.test.js`

**Interfaces:**
- Produces: `/library-manifest.json` with `{version, snapshot}` and immutable `library.<version>.json`.
- Produces: `EpubBrowser.LibrarySnapshot.load(manifestUrl)` and `renderInto(grid, books)`.

- [ ] **Step 1: Write failing snapshot and card tests**

```javascript
test('renders cards in batches and leaves covers lazy', async () => {
  const grid = fakeGrid();
  await LibrarySnapshot.renderInto(grid, [{ hash: 'a', cover: 'cover.jpg', title: 'A', authors: [], tags: [] }]);
  assert.equal(grid.images[0].loading, 'lazy');
  assert.equal(grid.images[0].decoding, 'async');
});
```

- [ ] **Step 2: Run the JavaScript test to verify it fails**

Run: `node --test tests/js/library-snapshot.test.js`

Expected: FAIL because `library-snapshot.js` does not exist.

- [ ] **Step 3: Generate manifest and immutable snapshot**

```python
payload = json.dumps(books_data, ensure_ascii=False, separators=(",", ":")).encode()
version = hashlib.sha256(payload).hexdigest()[:16]
write_json(root / f"library.{version}.json", books_data)
write_json(root / "library-manifest.json", {"version": version, "snapshot": f"/library.{version}.json"})
```

Set `Cache-Control: no-cache` for the manifest and `public, max-age=31536000, immutable` for the snapshot in `StaticDelivery`.

- [ ] **Step 4: Implement incremental rendering without thumbnails**

Use `DocumentFragment` batches of 24 cards scheduled through `requestAnimationFrame`. Create covers with:

```javascript
image.loading = 'lazy';
image.decoding = 'async';
image.className = 'book-cover';
image.src = '/book/' + book.hash + '/' + book.cover;
```

Replace `Date.now()` metadata URLs in `library.js` and `bookshelf.js` with `LibrarySnapshot.load('/library-manifest.json')`. Add a CSS `aspect-ratio: 2 / 3` fallback to `.book-cover`.

- [ ] **Step 5: Run tests and commit**

Run: `node --test tests/js/library-snapshot.test.js && python -m unittest tests.test_release -v`

Expected: PASS; generated output contains both manifest and versioned snapshot.

```bash
git add epub_browser/library.py epub_browser/assets/runtime.js epub_browser/assets/library-snapshot.js epub_browser/assets/library.js epub_browser/assets/library.css epub_browser/assets/bookshelf.js tests/js/library-snapshot.test.js
git commit -m "feat: version library snapshots and lazy-load covers"
```

## Task 4: Generate chapter fragments and a cancellable ChapterSource

**Files:**
- Modify: `epub_browser/processor.py`
- Create: `epub_browser/assets/chapter-source.js`
- Create: `tests/js/chapter-stream.test.js`

**Interfaces:**
- Produces: `book/<hash>/fragments/chapter_<index>.json` with `{index,title,bodyHtml}`.
- Produces: `EpubBrowser.ChapterSource.create(bookHash).fetch(index, signal)` returning a Promise for that object.

- [ ] **Step 1: Write a failing source cancellation test**

```javascript
test('aborts a stale fragment request', async () => {
  const source = ChapterSource.create('book', fakeFetch);
  const controller = new AbortController();
  const promise = source.fetch(3, controller.signal);
  controller.abort();
  await assert.rejects(promise, { name: 'AbortError' });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `node --test tests/js/chapter-stream.test.js`

Expected: FAIL because `ChapterSource` does not exist.

- [ ] **Step 3: Emit fragment data next to each full chapter page**

When `EPUBProcessor` renders a chapter, reuse the existing title and body HTML before wrapping it in the full reader document. Write JSON with `ensure_ascii=False`, and escape only through `json.dump`; do not scrape generated full pages to produce fragments.

- [ ] **Step 4: Implement source cache and cancellation**

```javascript
function fetchChapter(index, signal) {
  return fetch(base + '/fragments/chapter_' + index + '.json', { signal: signal })
    .then(function (response) {
      if (!response.ok) throw new Error('Chapter fragment request failed: ' + response.status);
      return response.json();
    });
}
```

Cache successful fragment objects by index only for the active reader session. Do not cache rejected or aborted requests.

- [ ] **Step 5: Run tests and commit**

Run: `node --test tests/js/chapter-stream.test.js`

Expected: PASS for successful fetch, non-200 failure, cache reuse, and abort.

```bash
git add epub_browser/processor.py epub_browser/assets/chapter-source.js tests/js/chapter-stream.test.js
git commit -m "feat: generate lightweight chapter fragments"
```

## Task 5: Build UI profiles, the Reader App Shell, and ChapterStream

**Files:**
- Create: `epub_browser/assets/chapter-stream.js`
- Create: `epub_browser/assets/reader-navigation.js`
- Create: `epub_browser/assets/reader-shell.js`
- Modify: `epub_browser/assets/chapter.js`
- Modify: `epub_browser/processor.py`
- Modify: `epub_browser/assets/chapter.css`
- Modify: `tests/js/chapter-stream.test.js`
- Create: `tests/js/reader-navigation.test.js`

**Interfaces:**
- Produces: `EpubBrowser.ChapterStream.create({content, source, chapterIndex, totalChapters, windowSize})`.
- Interface: `start()`, `onScroll(progress)`, `prefetch(direction)`, `append(fragment)`, `trim()`, `current()` and `destroy()`.
- Produces: `UIProfiles.get(profileId)`, whose profile object selects templates and entry assets only; shared conversion, source, stream, annotations, and bookshelf modules stay outside the profile.
- Produces: `EpubBrowser.ReaderNavigation.create({shell, source, history, location})`, with `start()`, `navigate(url)`, `restore()`, and `destroy()`.

- [ ] **Step 1: Add failing stream-window tests**

```javascript
test('prefetches at 65 percent and retains five chapters', async () => {
  const stream = ChapterStream.create(fakeOptions({ windowSize: 5 }));
  stream.start();
  stream.onScroll({ progress: 0.65, direction: 'next' });
  await flushPromises();
  assert.deepEqual(stream.loadedIndices(), [3, 4, 5, 6, 7]);
  assert.equal(stream.current().index, 5);
});
```

Add profile tests establishing that `reader` is the default, `legacy` selects
the unchanged template/entrypoint, and a future registered profile can select
its own template/assets without branching chapter generation. Add navigation
tests establishing that same-book ordinary clicks use `pushState`, replace the
main reading content and focus it, while modified clicks, failed fetches, and
unsupported capabilities fall back to the native link.

- [ ] **Step 2: Run the test to verify it fails**

Run: `node --test tests/js/chapter-stream.test.js`

Expected: FAIL because `ChapterStream` does not exist.

- [ ] **Step 3: Implement the profile registry and page generation boundary**

Introduce a small Python `UIProfile` registry with `reader` and `legacy`
definitions. Parse and validate `--ui`; pass the chosen definition into
library/chapter rendering. Each profile maps to explicit template and asset
entrypoints. Do not copy EPUB conversion, release publication, URL construction,
annotations, or fragment generation into profile-specific branches.

- [ ] **Step 4: Implement prefetch, append, and trim**

Use one `AbortController` per direction. Begin `prefetch('next')` at progress `>= 0.65`; append only a completed prefetched fragment at the visible end. After each append, remove nodes belonging to indices outside `[current - 2, current + 2]`; when removing nodes above the viewport, subtract their measured height from `window.scrollY` to preserve reading position.

- [ ] **Step 5: Implement the default Reader App Shell and navigation**

For `reader`, keep the shell mounted across same-book chapter navigation. Its
reading surface uses paper/ink tokens, local/system typography, comfortable
line length and gutters, semantic `main`/`article` landmarks, keyboard controls,
44px targets, and a reduced-motion-safe short transition. Show loading feedback
only after a delay and announce it through a polite live region. Intercept only
eligible same-book links; fetch a fragment, update title/progress/history and
focus the reading landmark. The `legacy` entrypoint does not mount this shell.

- [ ] **Step 6: Replace direct page parsing in the reader profile**

Delete the `XMLHttpRequest`, `tempDiv.innerHTML`, full-page title extraction, and duplicated next/previous clone loops. Create `ChapterSource` and `ChapterStream` after the reader content exists. Keep existing URL replacement, Fancybox binding, progress UI, and settings toggle as callbacks supplied to the stream rather than hidden global state.

- [ ] **Step 7: Run tests and commit**

Run: `node --test tests/js/chapter-stream.test.js tests/js/reader-navigation.test.js && python -m unittest discover -s tests -v`

Expected: PASS for profile selection, native-link fallback, history/focus
lifecycle, threshold prefetch, no foreground page parsing, five-chapter
trimming, reverse-direction cancellation, and scroll position preservation.

```bash
git add epub_browser/assets/chapter-stream.js epub_browser/assets/chapter-source.js epub_browser/assets/reader-navigation.js epub_browser/assets/reader-shell.js epub_browser/assets/chapter.js epub_browser/assets/chapter.css epub_browser/processor.py tests/js/chapter-stream.test.js tests/js/reader-navigation.test.js
git commit -m "feat: add reader profile and bounded chapter stream"
```

## Task 6: Implement StaticDelivery and migrate Docker serving

**Files:**
- Modify: `epub_browser/webapp.py`
- Modify: `epub_browser/main.py`
- Modify: `epub_browser/server.py`
- Modify: `Dockerfile`
- Modify: `tests/test_webapp.py`

**Interfaces:**
- Produces: `create_app(release_root, sync_dir)` and `run_server(app, port)`.
- `StaticDelivery` resolves a stable URL against `ReleasePublisher.current_root()` on every request.

- [ ] **Step 1: Add failing cache and API-isolation tests**

```python
def test_manifest_revalidates_but_versioned_snapshot_is_immutable(self):
    manifest = request(self.app, "GET", "/library-manifest.json")
    snapshot = request(self.app, "GET", "/library.abc.json")
    self.assertEqual(manifest.headers["cache-control"], "no-cache")
    self.assertEqual(snapshot.headers["cache-control"], "public, max-age=31536000, immutable")

def test_api_route_does_not_fall_through_to_static_tree(self):
    response = request(self.app, "GET", "/api/health")
    self.assertEqual(response.status, 200)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m unittest tests.test_webapp -v`

Expected: FAIL because `create_app` is still a placeholder.

- [ ] **Step 3: Build Starlette routes around `StaticDelivery`**

```python
routes = [
    Route('/api/health', health),
    Route('/api/{path:path}', annotation_api),
    Route('/sync', sync_endpoint, methods=['POST']),
    Mount('/', app=StaticDelivery(release_resolver)),
]
return Starlette(routes=routes)
```

Use `FileResponse` for static files. Select cache headers by path: manifest `no-cache`; versioned snapshots, fragments, and fingerprinted assets immutable; full stable chapter pages `no-cache` with validators.

- [ ] **Step 4: Start the ASGI application from the existing CLI**

Replace the `EPUBServer` child process target with `uvicorn.run(create_app(...), host='0.0.0.0', port=port)`. Preserve `--no-browser`, `--log`, `--watch`, `--sync-dir`, `--output-dir`, port behavior, and graceful SIGTERM handling. Remove only the now-unused custom static paths from `server.py`; keep database and sync logic behind the API module.

- [ ] **Step 5: Verify Docker and commit**

Run: `python -m unittest tests.test_webapp tests.test_release -v`

Run: `docker build -t epub-browser-perf-test . && docker run --rm -p 18080:80 -v "$PWD/examples:/app/Library:ro" epub-browser-perf-test`

Expected: health endpoint returns 200; a chapter has ETag; a range request returns 206; existing Docker CLI command still starts.

```bash
git add epub_browser/webapp.py epub_browser/main.py epub_browser/server.py Dockerfile tests/test_webapp.py
git commit -m "feat: serve releases through ASGI static delivery"
```

## Task 7: Split page scripts, add I18n, and version offline caches

**Files:**
- Modify: `epub_browser/library.py`
- Modify: `epub_browser/processor.py`
- Modify: `epub_browser/assets/sw.js`
- Modify: `epub_browser/assets/annotation.js`
- Modify: `epub_browser/assets/bookshelf.js`
- Create: `epub_browser/assets/annotation-server.js`
- Create: `epub_browser/assets/i18n.js`
- Create: `epub_browser/assets/locales/zh-CN.js`
- Create: `epub_browser/assets/locales/en.js`
- Create: `tests/js/runtime.test.js`
- Create: `tests/js/i18n.test.js`

**Interfaces:**
- Produces: `EpubBrowser.Runtime.load(name)` and feature modules registered through `EpubBrowser.Runtime.register(name, factory)`.
- Produces: `AnnotationServerAdapter.create(baseUrl)` only after server capability succeeds.
- Produces: `EpubBrowser.I18n.create({defaultLocale, storage, navigator, loadCatalog})`, with `t()`, `format()`, `setLocale()`, and `applyDocument()`; all identifiers used for URLs and persisted state remain unlocalized.

- [ ] **Step 1: Write failing module-loader and cache-policy tests**

```javascript
test('loads a registered feature once', function () {
  Runtime.register('reader', function () { return { start: function () {} }; });
  assert.equal(Runtime.load('reader'), Runtime.load('reader'));
});
```

Add a service-worker fixture test that asserts release cache names include the manifest version and that only the active cache remains after activation.

Add `i18n.test.js` cases for locale precedence, English fallback, catalog-key
parity, `Intl` formatting fallback on constrained browsers, DOM/ARIA updates,
and preservation of the current URL and progress key when the locale changes.

- [ ] **Step 2: Run tests to verify they fail**

Run: `node --test tests/js/runtime.test.js`

Expected: FAIL because `runtime.js` does not exist.

- [ ] **Step 3: Move code behind traditional module interfaces and add I18n**

Load only shared runtime plus the page feature required by the generated template. Library pages load library, theme, and bookshelf; chapter pages load reader, chapter source/stream, and annotation core. Move remote annotation calls from `annotation.js` into `annotation-server.js`; retain IndexedDB behavior in annotation core.

Make generated templates have Chinese product labels and `lang="zh-CN"` before
scripts run. Replace every user-facing product literal with stable message keys
in the `zh-CN` and `en` catalogs, including controls, errors, notifications,
and ARIA labels. On bootstrap, select local preference, then a compatible
browser language, then Chinese; load only the required versioned catalog,
update `document.documentElement.lang`, and persist explicit user changes. Do
not translate EPUB content or use localized strings as CSS selectors, URLs, or
storage keys.

- [ ] **Step 4: Replace the Service Worker policy**

Fetch `library-manifest.json` network-first. Namespace caches as `epub-browser-<release-version>`. Cache immutable snapshots, fragments, assets, locale catalogs, and covers cache-first; leave API and sync uncached. On activate, delete every cache namespace except the active release namespace.

- [ ] **Step 5: Run full regression and commit**

Run: `node --test tests/js/*.test.js && python -m unittest discover -s tests -v`

Expected: PASS; a static deployment still opens local annotations and bookshelf without `/api` or `/sync`, and switching `zh-CN`/`en` leaves its URL and local reading state unchanged.

```bash
git add epub_browser/library.py epub_browser/processor.py epub_browser/assets tests/js/runtime.test.js tests/js/i18n.test.js
git commit -m "refactor: add i18n and version offline caches"
```

## Task 8: Measure complete user flows and update documentation

**Files:**
- Modify: `README.md`
- Modify: `Dockerfile`
- Modify: `docs/superpowers/specs/2026-08-11-performance-architecture-design.md`

**Interfaces:**
- Consumes: all preceding release and browser interfaces.
- Produces: reproducible performance commands and documented migration behavior.

- [ ] **Step 1: Add browser-flow assertions before documentation changes**

Record repeatable checks: initial library has lazy cover attributes; no more than five `.chapter-separator`/chapter groups survive continuous reading; static Pages uses local annotations without a server adapter.

- [ ] **Step 2: Run the browser-flow checks against generated fixtures**

Run: `node --test tests/js/*.test.js && python -m unittest discover -s tests -v`

Expected: PASS before changing user documentation.

- [ ] **Step 3: Document the exact deployment model**

Explain the Python 3.9 floor, no-added-proxy Docker image, release publication behavior, rollback retention, stable URLs, cache update behavior, and how to clear a stale service-worker cache.

- [ ] **Step 4: Rebuild and smoke test both outputs**

Run: `epub-browser examples --no-server --output-dir /tmp/epub-browser-static --keep-files`

Run: `find /tmp/epub-browser-static -maxdepth 2 -name 'library-manifest.json' -o -name 'current.json'`

Expected: static export contains the root library entry and stable `book/` paths; no runtime server files are required by Pages.

- [ ] **Step 5: Commit the release-ready documentation**

```bash
git add README.md Dockerfile docs/superpowers/specs/2026-08-11-performance-architecture-design.md
git commit -m "docs: describe snapshot delivery and cache behavior"
```

## Self-review

- Spec coverage: Tasks 2--3 implement LibrarySnapshot, lazy covers, and stable publication; Tasks 4--5 implement fragments, prefetch, cancellation, and five-chapter trimming; Task 6 implements Uvicorn/Starlette static delivery; Task 7 implements traditional browser module split, local Pages behavior, and versioned offline cache; Task 8 verifies Docker and Pages behavior.
- Placeholder scan: no unfinished markers or unnamed interfaces remain.
- Type consistency: `ReleasePublisher`, `LibrarySnapshot`, `ChapterSource`, `ChapterStream`, `StaticDelivery`, and `Runtime` interfaces are introduced before later tasks consume them.
