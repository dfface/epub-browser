# Library Lighthouse Performance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce authenticated Library-page transfer, rendering, and blocking work identified by the supplied Lighthouse report without changing reader behavior.

**Architecture:** Keep the Library shell and metadata API unchanged. Render cards in small animation-frame batches and let the browser defer offscreen EPUB cover requests; move optional interaction code behind one small loader that consumes content-addressed URLs emitted by the existing asset publisher. Original EPUB cover files remain the only cover representation.

**Tech Stack:** Python 3.9, Starlette, vanilla JavaScript, browser native image loading, Node test runner, unittest.

**Spec:** `/Users/handy/.codex/attachments/de3b3204-4d67-406d-b9bf-18c8fc11de78/pasted-text.txt`

## Global Constraints

- Preserve one shared Library template for SSG and Server deployments.
- Server-only clients must not be published to SSG output.
- Do not generate, transform, or store cover thumbnails; the existing performance architecture forbids them.
- Never expose a protected book resource without Server book visibility checks.
- Keep all user-visible strings in the existing i18n tables.
- Run `git diff --check` and both JavaScript and Python test suites before merge.

## Execution status

- [x] Task 1: Lazy cover loading and asynchronous decoding.
- [x] Task 2: Deferred Library feature loading, including the Server AI Hub entry point.
- [x] Task 3: 24-card animation-frame rendering batches; compact thumbnails are explicitly excluded by the existing performance architecture.
- [x] Task 4: Non-blocking Font Awesome font faces.
- [x] Task 5: Full verification and merge.

---

### Task 1: Lazy, non-blocking Library cover decoding

**Files:**
- Modify: `epub_browser/assets/library.js`
- Test: `tests/test_library_metadata.js`

**Interfaces:**
- Consumes: Library metadata records with `cover` URLs.
- Produces: card `<img>` nodes with native lazy loading and asynchronous decoding.

- [ ] **Step 1: Write the failing test**

```js
test('library cards defer offscreen cover fetches and decode asynchronously', () => {
  const harness = createLibraryHarness([{ books: [sampleBook] }]);
  harness.window.initScriptLibrary();
  const cover = harness.card(sampleBook.hash).querySelector('.book-cover');
  assert.equal(cover.getAttribute('loading'), 'lazy');
  assert.equal(cover.getAttribute('decoding'), 'async');
});
```

- [ ] **Step 2: Run the focused test and verify it fails because these attributes are absent**

Run: `node --test tests/test_library_metadata.js`

- [ ] **Step 3: Implement the smallest card-renderer change**

```js
cover.setAttribute('loading', 'lazy');
cover.setAttribute('decoding', 'async');
```

- [ ] **Step 4: Run the focused test and verify it passes**

Run: `node --test tests/test_library_metadata.js`

- [ ] **Step 5: Commit the independently testable change**

```bash
git add epub_browser/assets/library.js tests/test_library_metadata.js
git commit -m "perf: lazy load library covers"
```

### Task 2: Load Library-only features on interaction

**Files:**
- Create: `epub_browser/assets/library-feature-loader.js`
- Modify: `epub_browser/site.py`
- Modify: `epub_browser/assets/library.js`
- Test: `tests/test_library_feature_loader.js`
- Test: `tests/test_generated_reader_surfaces.py`

**Interfaces:**
- Consumes: `window.EpubBrowserLibraryFeatureAssets`, a map from `pinyin`, `sortable`, `bookshelf`, `annotation`, `annotationHub`, and their styles to immutable URLs.
- Produces: `window.EpubBrowserLibraryFeatures.load(name)` and replayed first-click events once a feature has initialized.

- [ ] **Step 1: Write failing loader tests for one-time script/style injection and first-click replay**

```js
assert.equal(harness.appendedScripts.length, 0);
harness.click(harness.bookshelfButton);
await harness.flush();
assert.deepEqual(harness.appendedScripts, ['/assets/immutable/sortable.hash.js', '/assets/immutable/bookshelf.hash.js']);
assert.equal(harness.replayedClicks, 1);
```

- [ ] **Step 2: Run the focused test and verify the loader module is missing**

Run: `node --test tests/test_library_feature_loader.js`

- [ ] **Step 3: Implement `library-feature-loader.js` and publish its URL map from the shared Library shell**

```js
function loadScript(name) { /* memoized content-addressed script injection */ }
function loadStyle(name) { /* memoized non-render-blocking stylesheet injection */ }
root.EpubBrowserLibraryFeatures = { load: loadFeature };
```

- [ ] **Step 4: Change the Library shell to remove optional `<script>`/`<link>` tags from the critical path**

```python
library_feature_assets = json.dumps({
    'pinyin': assets.url_for('pinyin-pro.min.js'),
    'sortable': assets.url_for('sortable.min.js'),
})
```

- [ ] **Step 5: Make `library.js` request pinyin only for a non-literal search and sortable/bookshelf only after their associated interaction**

```js
window.EpubBrowserLibraryFeatures.load('pinyin').then(applyLibraryFilters);
```

- [ ] **Step 6: Run targeted JavaScript and generated-surface tests**

Run: `node --test tests/test_library_feature_loader.js tests/test_library_metadata.js && /usr/bin/python3 -m unittest tests.test_generated_reader_surfaces -q`

- [ ] **Step 7: Commit the independently testable change**

```bash
git add epub_browser/assets/library-feature-loader.js epub_browser/assets/library.js epub_browser/site.py tests/test_library_feature_loader.js tests/test_generated_reader_surfaces.py
git commit -m "perf: defer optional library features"
```

### Task 3: Incrementally render a large Library catalog

**Files:**
- Modify: `epub_browser/assets/library.js`
- Test: `tests/test_library_metadata.js`

**Interfaces:**
- Consumes: the existing full Library metadata array.
- Produces: cards in deterministic batches of 24 per animation frame, while preserving filters, tags, persisted card order, and the loading state.

- [ ] **Step 1: Write a failing incremental-rendering test**

```js
const books = Array.from({ length: 25 }, (_, index) => sampleBook('book-' + index));
const harness = createLibraryHarness([{ books }]);
harness.window.initScriptLibrary();
assert.equal(harness.cardIds().length, 0);
harness.flushAnimationFrame();
assert.equal(harness.cardIds().length, 24);
harness.flushAnimationFrame();
assert.equal(harness.cardIds().length, 25);
```

- [ ] **Step 2: Run the focused test and verify all cards currently append synchronously**

Run: `node --test tests/test_library_metadata.js`

- [ ] **Step 3: Implement a requestAnimationFrame batch renderer**

```js
function appendCardsInBatches(bookGrid, cards, done) {
    var offset = 0;
    function appendBatch() {
        cards.slice(offset, offset + 24).forEach(function(card) { bookGrid.appendChild(card); });
        offset += 24;
        if (offset < cards.length) window.requestAnimationFrame(appendBatch);
        else done();
    }
    window.requestAnimationFrame(appendBatch);
}
```

- [ ] **Step 4: Preserve the existing post-render state transition**

```js
appendCardsInBatches(bookGrid, cards, function() {
    hideBookGridLoading();
    window.onBookCardsLoaded && window.onBookCardsLoaded();
});
```

- [ ] **Step 5: Run focused Library metadata tests**

Run: `node --test tests/test_library_metadata.js`

- [ ] **Step 6: Commit the independently testable change**

```bash
git add epub_browser/assets/library.js tests/test_library_metadata.js
git commit -m "perf: render library cards incrementally"
```

### Task 4: Prevent icon font blocking

**Files:**
- Modify: `epub_browser/assets/fa.all.min.css`
- Test: `tests/test_generated_reader_surfaces.py`

**Interfaces:**
- Consumes: existing Font Awesome icon class names.
- Produces: identical icons with `font-display: swap` rather than a blocking font face.

- [ ] **Step 1: Write a failing source-level regression test**

```python
stylesheet = Path('epub_browser/assets/fa.all.min.css').read_text(encoding='utf-8')
self.assertNotIn('font-display:block', stylesheet)
self.assertIn('font-display:swap', stylesheet)
```

- [ ] **Step 2: Run the focused test and verify it fails on the current blocking declarations**

Run: `/usr/bin/python3 -m unittest tests.test_generated_reader_surfaces -q`

- [ ] **Step 3: Mechanically replace the font-face display mode**

```sh
perl -0pi -e 's/font-display:block/font-display:swap/g' epub_browser/assets/fa.all.min.css
```

- [ ] **Step 4: Run the focused test and asset-publisher tests**

Run: `/usr/bin/python3 -m unittest tests.test_generated_reader_surfaces tests.test_asset_publisher -q`

- [ ] **Step 5: Commit the independently testable change**

```bash
git add epub_browser/assets/fa.all.min.css tests/test_generated_reader_surfaces.py
git commit -m "perf: avoid blocking icon fonts"
```

### Task 5: Final verification and integration

**Files:**
- Modify: `docs/superpowers/plans/2026-08-25-library-lighthouse-performance.md`

- [ ] **Step 1: Mark completed plan steps and inspect the final diff**

Run: `git diff --check && git status --short`

- [ ] **Step 2: Run full JavaScript and Python suites with the known working runtimes**

Run: `PATH=/usr/bin:/bin:/usr/sbin:/sbin /Users/handy/.local/state/fnm_multishells/79468_1787637786305/bin/node --test tests/test_*.js && PYTHONASYNCIODEBUG=0 /usr/bin/python3 -m unittest discover -s tests -q`

- [ ] **Step 3: Commit the plan record and merge `codex/library-lighthouse` into `main`**

```bash
git add docs/superpowers/plans/2026-08-25-library-lighthouse-performance.md
git commit -m "docs: record library performance remediation"
git checkout main
git merge --no-ff codex/library-lighthouse
```
