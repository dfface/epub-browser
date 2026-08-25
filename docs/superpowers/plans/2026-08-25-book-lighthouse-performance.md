# Book Lighthouse Performance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce Book-page critical-path CSS, JavaScript, and image bytes identified by the supplied Lighthouse report without changing Server/SSG behavior.

**Architecture:** Keep the shared Book template in `EPUBProcessor`, but publish a small content-addressed feature loader and resource URL map. The Book shell loads the interaction loader only; bookshelf, annotations, and drag ordering load only after their first related interaction. The current Book template already uses the 32×32 `favicon.png` for its navigation mark; EPUB covers remain unmodified source assets.

**Tech Stack:** Python 3.9, vanilla JavaScript, asset publisher, Node test runner, unittest.

**Spec:** `/Users/handy/.codex/attachments/eb4b533a-f969-40c0-82ae-04bf135a7ee0/pasted-text.txt`

## Global Constraints

- Preserve one shared Book template for SSG and Server outputs.
- Do not generate, transform, or store EPUB cover thumbnails.
- Server-only assets and AI clients must never enter SSG output.
- Do not alter the Server content-cache revision: this is UI and asset loading only.
- Keep all user-visible copy in the existing i18n tables.
- Run JavaScript and Python full suites, plus `git diff --check`, before merging to `main`.

## Execution status

- [x] Task 1: Publish and test the Book feature loader.
- [x] Task 2: Defer Book shelf, annotation, and drag assets.
- [x] Task 3: Verify the navigation logo is already right-sized.
- [x] Task 4: Assert Book AI rich-text assets are not eager.
- [ ] Task 5: Full verification and merge.

---

### Task 1: Book feature asset loader

**Files:**
- Create: `epub_browser/assets/book-feature-loader.js`
- Modify: `tests/test_book_feature_loader.js`

**Interfaces:**
- Consumes: `window.EpubBrowserBookFeatureAssets`, mapping logical names to immutable URLs.
- Produces: `window.EpubBrowserBookFeatures.load(name)`, which memoizes feature style/script requests and respects dependency order.

- [ ] **Step 1: Write a failing loader test**

```js
await Promise.all([
  harness.window.EpubBrowserBookFeatures.load('bookshelf'),
  harness.window.EpubBrowserBookFeatures.load('bookshelf'),
]);
assert.deepEqual(harness.appendedUrls(), [
  '/assets/immutable/bookshelf.css',
  '/assets/immutable/sortable.js',
  '/assets/immutable/bookshelf.js',
]);
```

- [ ] **Step 2: Run the focused test and confirm it fails because the module is missing**

Run: `node --test tests/test_book_feature_loader.js`

- [ ] **Step 3: Implement the loader**

```js
var features = {
  bookshelf: { styles: ['bookshelfCss'], scripts: ['sortable', 'bookshelf'] },
  annotations: { styles: ['annotationHubCss'], scripts: ['annotation', 'annotationHub'] },
  sortable: { scripts: ['sortable'] }
};
```

- [ ] **Step 4: Run the focused test and confirm it passes**

Run: `node --test tests/test_book_feature_loader.js`

### Task 2: Defer optional Book interactions

**Files:**
- Modify: `epub_browser/processor.py`
- Modify: `epub_browser/assets/book.js`
- Modify: `tests/test_generated_reader_surfaces.py`

**Interfaces:**
- Consumes: `EpubBrowserBookFeatures.load(name)`.
- Produces: a Book HTML shell without eager bookshelf, annotation, or Sortable CSS/JS; first clicks are replayed after initialization.

- [ ] **Step 1: Write a failing Book surface test**

```python
self.assertIn('window.EpubBrowserBookFeatureAssets=', book_html)
self.assertRegex(book_html, r'book-feature-loader\.[0-9a-f]{12}\.js')
self.assertNotRegex(book_html, r'<script\b[^>]+/(?:bookshelf|annotation|annotation-hub|sortable)\.[0-9a-f]{12}\.js')
```

- [ ] **Step 2: Run the focused test and confirm it fails on eager asset tags**

Run: `/usr/bin/python3 -m unittest tests.test_generated_reader_surfaces.GeneratedReaderSurfaceTests.test_book_optional_interactions_are_deferred -q`

- [ ] **Step 3: Publish the Book asset map and loader script from the shared template**

```python
book_feature_assets = json.dumps({
    'bookshelfCss': self.asset_manifest.url_for('bookshelf.css'),
    'bookshelf': self.asset_manifest.url_for('bookshelf.js'),
    'annotation': self.asset_manifest.url_for('annotation.js'),
    'annotationHub': self.asset_manifest.url_for('annotation-hub.js'),
    'annotationHubCss': self.asset_manifest.url_for('annotation-hub.css'),
    'sortable': self.asset_manifest.url_for('sortable.min.js'),
})
```

- [ ] **Step 4: Replace startup polling and eager `Sortable.create` with first-interaction loading**

```js
button.addEventListener('click', function(event) {
  if (button.dataset.bookFeatureReady) return;
  event.preventDefault();
  loadBookFeature('bookshelf').then(function() {
    window.initBookShelf();
    button.dataset.bookFeatureReady = 'true';
    button.click();
  });
});
```

- [ ] **Step 5: Run the focused Python and Node tests**

Run: `node --test tests/test_book_feature_loader.js && /usr/bin/python3 -m unittest tests.test_generated_reader_surfaces -q`

### Task 3: Verify the navigation logo is already right-sized

The supplied Lighthouse trace references a historical `logo-mark-color` request. The current shared Book template already emits the immutable 32×32 `favicon.png` navigation mark, so this item requires no code or asset change. EPUB covers remain unmodified.

### Task 4: Protect AI lazy loading

**Files:**
- Modify: `tests/test_generated_reader_surfaces.py`

**Interfaces:**
- Consumes: the Server Book HTML.
- Produces: a regression assertion that Mermaid and KaTeX appear only in the feature URL map, never as eager script tags.

- [ ] **Step 1: Write the failing regression assertion**

```python
self.assertNotRegex(book_html, r'<script\b[^>]+vendor/(?:mermaid|katex)/')
self.assertIn('window.EpubBrowserFeatureAssets=', book_html)
```

- [ ] **Step 2: Run the targeted test, then preserve the existing lazy loader behavior**

Run: `/usr/bin/python3 -m unittest tests.test_generated_reader_surfaces.GeneratedReaderSurfaceTests.test_book_ai_assets_stay_off_critical_path -q`

### Task 5: Full verification and merge

**Files:**
- Modify: `docs/superpowers/plans/2026-08-25-book-lighthouse-performance.md`

- [x] **Step 1: Mark completed tasks, inspect status, and check whitespace**

Run: `git diff --check && git status --short`

- [x] **Step 2: Run the full suites**

Run: `node --test tests/test_*.js && /usr/bin/python3 -m unittest discover -s tests -q`

- [ ] **Step 3: Commit and merge into `main`**

```bash
git add epub_browser tests docs/superpowers/plans/2026-08-25-book-lighthouse-performance.md
git commit -m "perf: defer book page optional features"
git checkout main
git merge --no-ff codex/book-lighthouse
```
