# Reader Performance and Version Proxy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Server reader startup smaller and stable, expose localized web manifests publicly, and route release checks through a fixed same-origin endpoint.

**Architecture:** Server-only release lookup is implemented as a fixed, cached GitHub client and served by a same-origin route; shared footers select that route only in Server mode. Reader templates retain only essential startup code, while feature clients load their own immutable scripts and styles on first use. EPUB conversion enriches image markup before it is cached, so Server caches get a schema revision.

**Tech Stack:** Python 3, Starlette, unittest/TestClient, Node built-in test runner, browser DOM APIs, existing AssetPublisher.

**Spec:** `docs/superpowers/specs/2026-08-25-reader-performance-and-version-proxy-design.md`

## Global Constraints

- Server-only behavior must not appear in SSG output or require `/api/*` from SSG pages.
- The release endpoint accepts no upstream URL from a client and returns no arbitrary upstream payload.
- Keep non-manifest deployed assets protected in Server mode.
- Increase `SERVER_OUTPUT_REVISION` only for cached EPUB image dimensions, with compatible cache validation tests.
- Use the existing hashed asset publisher; dynamic loaders receive generated immutable URLs, never unhashed asset paths.

---

### Task 1: Fixed same-origin version endpoint

**Files:**
- Modify: `epub_browser/version.py`
- Modify: `epub_browser/server.py`
- Modify: `epub_browser/site.py`
- Modify: `epub_browser/processor.py`
- Test: `tests/test_server.py`
- Test: `tests/test_version_check.js`

**Interfaces:**
- Produces `ReleaseLookup.fetch() -> dict | None`, which only reads `LATEST_RELEASE_API_URL`.
- Produces `GET /api/version`, returning the allowed release fields or a non-sensitive 503 response.
- `render_footer(year, release_api_url=LATEST_RELEASE_API_URL)` supplies the URL consumed by `version-check.js`.

- [ ] **Step 1: Write failing Server tests for public same-origin release lookup**

```python
def test_version_endpoint_returns_only_safe_release_fields(self):
    app = create_app(self.public, release_fetcher=lambda: {
        'tag_name': 'v1.2.3', 'html_url': 'https://github.com/dfface/epub-browser/releases/tag/v1.2.3',
        'draft': False, 'prerelease': False, 'body': 'must not escape',
    })
    response = TestClient(app).get('/api/version')
    self.assertEqual(response.status_code, 200)
    self.assertEqual(response.json(), {'tag_name': 'v1.2.3', 'html_url': 'https://github.com/dfface/epub-browser/releases/tag/v1.2.3', 'draft': False, 'prerelease': False})
```

- [ ] **Step 2: Run the new Server test and verify it fails because `/api/version` does not exist**

Run: `python3 -m unittest tests.test_server.<VersionEndpointTests.test_version_endpoint_returns_only_safe_release_fields>`

- [ ] **Step 3: Add a fixed-URL cached release lookup and `/api/version` route**

```python
async def version(request):
    release = await release_lookup.fetch()
    if release is None:
        return response(error_payload('version_unavailable', 'Version information unavailable'), 503)
    return response(release, 200)
```

- [ ] **Step 4: Extend tests for timeout/failure, cache reuse, and fixed upstream scope**

```python
def test_version_endpoint_returns_503_when_fixed_upstream_is_unavailable(self): ...
def test_version_lookup_reuses_a_recent_safe_response(self): ...
def test_version_lookup_has_no_client_supplied_upstream_url(self): ...
```

- [ ] **Step 5: Point Server footers at `/api/version`, preserve SSG GitHub URL, and update client fixtures**

```python
server_footer = render_footer(year, release_api_url='/api/version')
ssg_footer = render_footer(year)
```

- [ ] **Step 6: Run focused Python and Node tests**

Run: `python3 -m unittest tests.test_server.<VersionEndpointTests>` and `node --test tests/test_version_check.js`

### Task 2: Public localized web manifests without widening asset access

**Files:**
- Modify: `epub_browser/server.py`
- Test: `tests/test_server.py`

**Interfaces:**
- Produces `PUBLIC_WEB_MANIFESTS`, a fixed set of stable generated manifest paths.
- Anonymous requests to those paths use `public_files`; package-local login assets continue to use the package asset directory.

- [ ] **Step 1: Write failing setup and post-setup anonymous-access tests**

```python
for path in ('/assets/manifest.json', '/assets/manifest.en.json', '/assets/manifest.zh-CN.json', '/assets/manifest.zh-TW.json', '/assets/manifest.ko.json', '/assets/manifest.ja.json'):
    self.assertEqual(anonymous.get(path).status_code, 200)
self.assertEqual(anonymous.get('/assets/reader.js').status_code, 403)
```

- [ ] **Step 2: Run the tests and verify that manifests currently return 403/503**

Run: `python3 -m unittest tests.test_server.<ServerAuthBoundaryTests.test_anonymous_manifests_are_public>`

- [ ] **Step 3: Separate package login assets from generated public web manifests in middleware and file routing**

```python
PUBLIC_WEB_MANIFESTS = frozenset({...})
if '/' + path in PUBLIC_LOGIN_ASSETS:
    return package_asset_response(path)
if '/' + path in PUBLIC_WEB_MANIFESTS:
    return await public_files.get_response(path, request.scope)
```

- [ ] **Step 4: Run focused authorization/cache tests**

Run: `python3 -m unittest tests.test_server.ServerSetupBoundaryTests tests.test_server.ServerAuthBoundaryTests tests.test_server.ServerCacheTests`

### Task 3: Explicit AI loading and deduplicated chapter indicators

**Files:**
- Modify: `epub_browser/assets/ai-canvas.js`
- Modify: `epub_browser/assets/ai-reading-hub.js`
- Test: `tests/test_ai_canvas.js` or add focused cases to the existing AI client test file
- Test: `tests/test_ai_reading_hub.js` or add focused cases to the existing hub test file

**Interfaces:**
- Default `ai-canvas.init()` binds controls but does not call `load()`.
- An `ai_result` query parameter remains an explicit automatic load.
- `chapterIndicatorsFor(bookId) -> Promise<object>` is shared by all indicator containers for that book.

- [ ] **Step 1: Write failing DOM tests for no default AI result request and one request for two indicator containers**

```javascript
assert.equal(fetches.filter(url => url.includes('/results?chapter_index=')).length, 0);
assert.equal(fetches.filter(url => url.endsWith('/results')).length, 1);
```

- [ ] **Step 2: Run the new Node tests and verify the default fetch and duplicate request occur**

Run: `node --test tests/test_ai_canvas.js tests/test_ai_reading_hub.js`

- [ ] **Step 3: Bind AI canvas lazily and cache indicator promises per book**

```javascript
if (requestedResultId()) load(state.button, initial, state.contextVersion);
function chapterIndicatorsFor(bookId) {
  return state.chapterIndicatorRequests[bookId] || (state.chapterIndicatorRequests[bookId] = request(...));
}
```

- [ ] **Step 4: Run focused Node tests**

Run: `node --test tests/test_ai_canvas.js tests/test_ai_reading_hub.js`

### Task 4: Lazy rich-renderer and optional reader feature assets

**Files:**
- Modify: `epub_browser/processor.py`
- Modify: `epub_browser/server_pages.py`
- Modify: `epub_browser/assets/ai-rich-text.js`
- Modify: `epub_browser/assets/ai-canvas.js`
- Modify: `epub_browser/assets/ai-chat.js`
- Modify: `epub_browser/assets/annotation*.js`
- Modify: `epub_browser/assets/bookshelf.js`
- Test: `tests/test_generated_reader_surfaces.py`
- Test: focused Node tests for each lazy loader

**Interfaces:**
- Server reader HTML exposes `window.EpubBrowserFeatureAssets`, mapping the named optional assets to current immutable URLs.
- `EpubBrowserAIRich.ensure(kind) -> Promise<void>` loads each renderer/style once.
- Feature controls load their own optional dependency before opening the corresponding UI.

- [ ] **Step 1: Write failing surface tests asserting Mermaid, KaTeX, Fancybox, highlight, sortable, bookshelf and AI-chat are absent from initial chapter HTML**

```python
self.assertNotIn('vendor/mermaid/mermaid.min.js', chapter_html)
self.assertNotIn('vendor/katex/katex.min.js', chapter_html)
self.assertIn('window.EpubBrowserFeatureAssets', chapter_html)
```

- [ ] **Step 2: Run the surface test and verify existing templates eagerly include these assets**

Run: `python3 -m unittest tests.test_generated_reader_surfaces.GeneratedReaderSurfaceTests.<test_name>`

- [ ] **Step 3: Render immutable optional-asset URLs into Server reader chrome and add one-shot script/style loaders**

```javascript
function ensureAsset(name, kind) {
  if (loaded[name]) return loaded[name];
  loaded[name] = appendAsset(window.EpubBrowserFeatureAssets[name], kind);
  return loaded[name];
}
```

- [ ] **Step 4: Move optional feature initialization behind first interaction while preserving deep-link AI behavior**

- [ ] **Step 5: Run focused surface and Node tests**

Run: `python3 -m unittest tests.test_generated_reader_surfaces` and `node --test tests/test_ai_*.js tests/test_annotation*.js tests/test_bookshelf.js`

### Task 5: Compact image/font delivery and EPUB image dimensions

**Files:**
- Create: `epub_browser/assets/logo-mark-color.webp`
- Modify: `epub_browser/processor.py`
- Modify: `epub_browser/assets/fa.all.min.css` or replace it with a generated reader icon subset
- Modify: `epub_browser/asset_publisher.py` only if a reader icon subset needs an explicit source mapping
- Test: `tests/test_generated_reader_surfaces.py`
- Test: `tests/test_generated_reader_surfaces.py`
- Test: `tests/test_asset_publisher.py`

**Interfaces:**
- Generated reader nav uses `logo-mark-color.webp` and it resolves through `PublishedAssets`.
- Cached server chapter HTML contains intrinsic `width`/`height` where local EPUB image bytes provide dimensions.

- [ ] **Step 1: Write failing tests for WebP header logo and preserved/injected image dimensions**

```python
self.assertRegex(chapter_html, r'logo-mark-color\.[0-9a-f]{12}\.webp')
self.assertIn('<img src="resources/picture.jpg" width="640" height="480">', cleaned)
```

- [ ] **Step 2: Run tests and verify the current PNG and dimension-less image output fail them**

Run: `python3 -m unittest tests.test_generated_reader_surfaces`

- [ ] **Step 3: Generate a display-sized WebP logo, switch reader templates, and supply an icon subset with `font-display: swap`**

```text
sips -Z 64 epub_browser/assets/logo-mark-color.png --out epub_browser/assets/logo-mark-color.webp
```

- [ ] **Step 4: Enrich EPUB-local image dimensions during conversion, update cache schema validation, and bump the Server content revision**

```python
SERVER_OUTPUT_REVISION = "server-content-v9"
# For a local image with no numeric dimensions, serialize its decoded width and
# height while preserving existing valid author-supplied dimensions.
```

- [ ] **Step 5: Run processor, asset publisher, SSG, and Server cache tests**

Run: `python3 -m unittest tests.test_processor tests.test_asset_publisher tests.test_ssg tests.test_server_library`

### Task 6: Scroll-frame scheduling and final regression verification

**Files:**
- Modify: `epub_browser/assets/chapter.js`
- Test: `tests/test_chapter_window.js` or a focused new `tests/test_chapter_scroll.js`

**Interfaces:**
- A single scheduled frame owns reader scroll-update work.
- Existing scroll controls, top-button visibility, navigation behavior, and TOC highlighting retain their observable behavior.

- [ ] **Step 1: Write a failing test that dispatches many scroll events and asserts one pending frame/update cycle**

```javascript
for (let index = 0; index < 5; index += 1) root.dispatchScroll();
assert.equal(frames.length, 1);
frames.shift()();
assert.equal(updateCalls, 1);
```

- [ ] **Step 2: Run the Node test and verify current direct handlers fail**

Run: `node --test tests/test_chapter_scroll.js`

- [ ] **Step 3: Schedule unified scroll reads and writes through `requestAnimationFrame`**

- [ ] **Step 4: Run the full relevant suite and inspect the final diff**

Run: `python3 -m unittest discover -s tests`, `node --test tests/*.js`, and `git diff --check`

- [ ] **Step 5: Run Lighthouse in an incognito/extension-free profile against an authenticated default chapter URL and record the before/after metrics**

- [ ] **Step 6: Commit each independently verified task, then merge the feature branch into `main`**
