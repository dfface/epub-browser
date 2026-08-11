# Versioned Asset Cache Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every generated EPUB Browser release self-updating in normal browsers: documents and the service worker revalidate, while application assets receive immutable content-addressed URLs.

**Architecture:** Generate a deterministic asset manifest from `epub_browser/assets`, publish runtime assets under `/assets/immutable/`, and pass the manifest into every HTML generator. Keep only update entry points (`index.html`, `sw.js`, and `assets/manifest.json`) at stable, revalidated URLs. Render the service worker from the generated manifest and use network-first fetches for mutable book content, eliminating cache-first reads of mutable paths.

**Tech Stack:** Python 3, `unittest`, Starlette static serving, generated static-site files, browser Service Worker Cache API.

## Global Constraints

- Do not require a query-string version or an end-user hard refresh to receive a release.
- Keep generated sites deployable to GitHub Pages and compatible with the bundled ASGI server.
- Do not cache `sw.js`, HTML, or `assets/manifest.json` as immutable resources.
- Do not publish, push, or create a release as part of this work.

---

## Task 1: Add a deterministic asset publisher and its failing contract tests

**Files:**
- Create: `epub_browser/asset_publisher.py`
- Create: `tests/test_asset_publisher.py`

- [ ] **Step 1: Write the failing tests**

```python
class AssetPublisherTests(unittest.TestCase):
    def test_publish_writes_content_addressed_assets_and_a_lookup_manifest(self):
        with tempfile.TemporaryDirectory() as source, tempfile.TemporaryDirectory() as output:
            Path(source, "app.js").write_text("console.log('v1')", encoding="utf-8")
            published = AssetPublisher(source, output).publish()

            self.assertRegex(published.url_for("app.js"), r"^/assets/immutable/app\.[0-9a-f]{12}\.js$")
            self.assertTrue(Path(output, published.url_for("app.js").lstrip("/")).is_file())
            self.assertEqual(json.loads(Path(output, "assets", "asset-manifest.json").read_text()), published.assets)

    def test_publish_changes_only_the_url_for_changed_content(self):
        # publish v1, change one source asset, publish v2; assert its URL changes

    def test_publish_renders_the_stable_service_worker_with_the_release_precache(self):
        # assert /sw.js has a digest-derived cache name and immutable URLs, but no stale source URLs
```

- [ ] **Step 2: Run the focused test to verify it fails**

Run: `/Library/Developer/CommandLineTools/usr/bin/python3 -m unittest tests.test_asset_publisher -v`

Expected: import failure because `epub_browser.asset_publisher` does not exist.

- [ ] **Step 3: Implement the smallest publisher API**

Create `AssetPublisher` with `publish()`, `url_for(logical_name)`, and a serializable `assets` map. It must:

1. walk source assets deterministically;
2. SHA-256 each non-service-worker asset and copy it to `assets/immutable/<stem>.<12-hex><suffix>`;
3. write `assets/asset-manifest.json` containing the logical-to-public URL map;
4. copy a rewritten stable `assets/manifest.json` whose icon URLs use the same map;
5. render source `sw.js` placeholders using a release ID derived from the manifest and the immutable precache URLs.

Use POSIX public paths and make `url_for()` raise `KeyError` for an unknown logical asset so missed template references cannot silently revert to mutable URLs.

- [ ] **Step 4: Run focused publisher tests**

Run: `/Library/Developer/CommandLineTools/usr/bin/python3 -m unittest tests.test_asset_publisher -v`

Expected: PASS.

- [ ] **Step 5: Commit (local only)**

```bash
git add epub_browser/asset_publisher.py tests/test_asset_publisher.py
git commit -m "feat: publish content-addressed web assets"
```

## Task 2: Render generated pages exclusively through the asset manifest

**Files:**
- Modify: `epub_browser/library.py`
- Modify: `epub_browser/processor.py`
- Modify: `tests/test_generated_reader_surfaces.py`

- [ ] **Step 1: Replace stale query-version assertions with failing immutable-URL assertions**

Update the reader-surface test fixture to create one publisher-backed `AssetManifest` and inject it into `EPUBLibrary`/`EPUBProcessor`. Assert each library, book, and chapter page contains `/assets/immutable/` URLs for its browser-owned CSS, JS, logo, and icons, contains no `?v=`, and retains `/assets/manifest.json` as the stable revalidated manifest entry point.

- [ ] **Step 2: Run focused reader-surface tests to verify they fail**

Run: `/Library/Developer/CommandLineTools/usr/bin/python3 -m unittest tests.test_generated_reader_surfaces -v`

Expected: existing HTML still contains mutable `/assets/*.css` paths and `?v=` versions.

- [ ] **Step 3: Pass manifest URLs into all HTML renderers**

Build the source manifest once in `EPUBLibrary.__init__`; pass it to `EPUBProcessor` in `add_book()`. For direct `EPUBProcessor` use, create the same manifest lazily. Add a small HTML helper (for example `asset_url("chapter.js")`) and replace every project-owned `/assets/...` URL in library, book, and chapter templates. Keep `/assets/manifest.json` stable.

Replace exact `script[src="...?... "]` reinitialization selectors with a semantic `data-eb-asset` selector so code does not depend on an implementation URL. Preserve the base-path rewrite behavior by continuing to emit root-relative URLs.

- [ ] **Step 4: Publish assets during library generation**

Replace `EPUBLibrary.add_assets()`'s direct flat copy with the publisher. Ensure it runs before `create_library_home()` is exposed to callers, and that the publisher output is idempotent for the same source inputs.

- [ ] **Step 5: Run focused reader-surface and publisher tests**

Run: `/Library/Developer/CommandLineTools/usr/bin/python3 -m unittest tests.test_asset_publisher tests.test_generated_reader_surfaces -v`

Expected: PASS.

- [ ] **Step 6: Commit (local only)**

```bash
git add epub_browser/library.py epub_browser/processor.py tests/test_generated_reader_surfaces.py
git commit -m "feat: reference immutable assets from generated pages"
```

## Task 3: Make the service worker update-safe and set server cache headers

**Files:**
- Modify: `epub_browser/assets/sw.js`
- Modify: `epub_browser/server.py`
- Modify: `tests/test_server.py`
- Modify: `tests/test_asset_publisher.py`

- [ ] **Step 1: Write failing cache-policy tests**

Add ASGI requests that assert:

```python
self.assertEqual(response.headers["cache-control"], "public, max-age=31536000, immutable")
# for /assets/immutable/app.<hash>.js
self.assertEqual(response.headers["cache-control"], "no-cache")
# for /sw.js, /assets/manifest.json, and generated HTML
```

Also assert generated `sw.js` uses substituted release/precache placeholders, network-first handling for navigation and mutable requests, and no generic cache-first branch for arbitrary `/assets/` or `/book/` requests.

- [ ] **Step 2: Run focused tests to verify they fail**

Run: `/Library/Developer/CommandLineTools/usr/bin/python3 -m unittest tests.test_server tests.test_asset_publisher -v`

Expected: immutable assets currently receive only one-hour caching and the source worker uses generic cache-first behavior.

- [ ] **Step 3: Implement explicit cache classifications**

Use a path check for `assets/immutable/` in both the Starlette and legacy HTTP response paths. Serve only those content-addressed files as `public, max-age=31536000, immutable`; serve stable update endpoints and documents as `no-cache`.

Change `sw.js` to expose two rendering placeholders: `__EPUB_BROWSER_RELEASE_ID__` and `__EPUB_BROWSER_PRECACHE_URLS__`. Precaches only the immutable app shell and `index.html`; performs network-first with cached fallback for navigations and mutable content; and deletes prior release caches on activation. Keep the existing `CLEAR_CACHE` message capability, but it must repopulate only the new precache list.

- [ ] **Step 4: Run focused server and publisher tests**

Run: `/Library/Developer/CommandLineTools/usr/bin/python3 -m unittest tests.test_server tests.test_asset_publisher -v`

Expected: PASS.

- [ ] **Step 5: Commit (local only)**

```bash
git add epub_browser/assets/sw.js epub_browser/server.py tests/test_server.py tests/test_asset_publisher.py
git commit -m "fix: make browser updates cache-safe"
```

## Task 4: Verify generated static-site behavior and document deployment guarantees

**Files:**
- Modify: `README.md`
- Modify: `docs/releases/v1.10.1.md`
- Create: `tests/test_static_asset_delivery.py`

- [ ] **Step 1: Add a failing end-to-end generated-output test**

Generate an empty library, then assert all HTML-referenced immutable paths exist, `/sw.js` and `/assets/manifest.json` exist at stable paths, and no generated HTML has `?v=` or a direct mutable browser asset URL.

- [ ] **Step 2: Run the test to verify it fails before any needed integration fix**

Run: `/Library/Developer/CommandLineTools/usr/bin/python3 -m unittest tests.test_static_asset_delivery -v`

Expected: FAIL until the generator call order and all template references are complete.

- [ ] **Step 3: Add deployment documentation**

In the README and release notes, explain that deployers should publish the complete generated directory atomically when possible. Explain the automatic browser behavior in plain language: HTML and `sw.js` revalidate; app assets are content-addressed and immutable; users no longer need to use Network-panel cache clearing for normal upgrades. Retain a short troubleshooting note for intermediary proxies/CDNs that override origin headers.

- [ ] **Step 4: Run the full test suite**

Run: `/Library/Developer/CommandLineTools/usr/bin/python3 -m unittest discover -s tests -v`

Expected: PASS. If the local interpreter lacks existing Starlette dependencies, rerun with the repository's available Command Line Tools Python and report that environment fact separately.

- [ ] **Step 5: Inspect the generated output manually**

Run a temporary-library generation command and inspect `index.html`, `sw.js`, `assets/asset-manifest.json`, and `assets/immutable/`. Confirm each referenced filename includes a digest and the service worker release ID changes when a source asset changes.

- [ ] **Step 6: Commit (local only)**

```bash
git add README.md docs/releases/v1.10.1.md tests/test_static_asset_delivery.py
git commit -m "docs: describe cache-safe static deployments"
```
