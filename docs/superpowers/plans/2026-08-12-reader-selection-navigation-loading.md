# Reader Selection, Navigation, and Loading Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add text-only copying to the annotation menu, align breadcrumb surfaces, and replace global loading overlays with content-level feedback.

**Architecture:** `annotation.js` owns copying selected source text and its feedback. Generated page templates own navigation and local loading markup; `chapter.js` toggles only the content container's loading state. CSS provides a shared breadcrumb surface and contained loading overlay.

**Tech Stack:** Python 3 `unittest`, vanilla JavaScript, CSS, Clipboard API.

## Global Constraints

- Copy only selected plain text and never create or mutate an annotation.
- Breadcrumbs stay semantic and retain `aria-current="page"`.
- No page includes `#loadingOverlay`; loading covers only changing content.

---

### Task 1: Add selection-copy behavior

**Files:**
- Modify: `epub_browser/assets/annotation.js:1003-1090`
- Modify: `epub_browser/assets/annotation.css`
- Test: `tests/test_generated_reader_surfaces.py`

- [ ] **Step 1: Add a failing contract test for the generated annotation asset**

```python
def test_annotation_asset_exposes_text_only_copy_action(self):
    script = Path("epub_browser/assets/annotation.js").read_text(encoding="utf-8")
    self.assertIn('annotation-btn-copy', script)
    self.assertIn('navigator.clipboard.writeText(text)', script)
```

- [ ] **Step 2: Run the focused test and verify failure**

Run: `python3 -m unittest tests.test_generated_reader_surfaces.GeneratedReaderSurfaceTests.test_annotation_asset_exposes_text_only_copy_action -v`

- [ ] **Step 3: Implement the Copy button and clipboard fallback**

```javascript
function copySelectedText(text) {
  return navigator.clipboard && navigator.clipboard.writeText
    ? navigator.clipboard.writeText(text)
    : Promise.reject(new Error('Clipboard unavailable'));
}
```

Add `<button class="annotation-btn annotation-btn-copy">Copy</button>` beside Cancel and Add. Its handler copies `source.text`, reports success or failure, and leaves `pendingDraft` and storage untouched.

- [ ] **Step 4: Run test and JavaScript syntax check**

Run: `python3 -m unittest tests.test_generated_reader_surfaces -v && node --check epub_browser/assets/annotation.js`

- [ ] **Step 5: Commit**

```bash
git add epub_browser/assets/annotation.js epub_browser/assets/annotation.css tests/test_generated_reader_surfaces.py
git commit -m "feat: copy selected annotation text"
```

### Task 2: Align breadcrumb surfaces and remove global loading markup

**Files:**
- Modify: `epub_browser/library.py`, `epub_browser/processor.py`
- Modify: `epub_browser/assets/{library,book,chapter,loading}.css`
- Modify: `epub_browser/assets/{library,book,chapter}.js`
- Modify: `epub_browser/assets/sw.js`
- Test: `tests/test_generated_reader_surfaces.py`

- [ ] **Step 1: Add failing generated-page tests**

```python
def test_generated_pages_have_no_fullscreen_loading_overlay(self):
    for html in (library_html, book_html, chapter_html):
        self.assertNotIn('id="loadingOverlay"', html)
```

- [ ] **Step 2: Run the test and verify failure**

Run: `python3 -m unittest tests.test_generated_reader_surfaces -v`

- [ ] **Step 3: Implement contained surfaces**

Remove `#loadingOverlay` markup and obsolete hide functions. Add a `.breadcrumb-container` around each breadcrumb and apply the shared max width, margin, and gradient top rule. Add `.content-loading` inside chapter `.eb-content-container`; update `showLoading()` and `hideLoading()` to toggle it.

- [ ] **Step 4: Verify generated output and complete tests**

Run: `python3 -m unittest discover -s tests -v && python3 -m compileall -q epub_browser && node --check epub_browser/assets/chapter.js && git diff --check`

- [ ] **Step 5: Commit**

```bash
git add epub_browser/library.py epub_browser/processor.py epub_browser/assets tests/test_generated_reader_surfaces.py
git commit -m "feat: align reader navigation and loading"
```

### Task 3: Generate an acceptance preview

**Files:**
- No tracked file changes expected.

- [ ] **Step 1: Generate the example EPUB site**

Run: `python3 -m epub_browser.main 'examples/Yi Jiu Ba Si - Qiao Zhi _Ao Wei Er.epub' --output-dir <temporary-directory> --no-server --no-browser --keep-files`

- [ ] **Step 2: Inspect output and publish local preview**

Verify library, book, and chapter HTML omit `loadingOverlay`; check the chapter contains `.content-loading`, Copy, and aligned breadcrumb wrappers. Serve the output with `python3 -m http.server`.

- [ ] **Step 3: Run final checks**

Run: `python3 -m unittest discover -s tests -v && python3 -m compileall -q epub_browser && node --check epub_browser/assets/{annotation,chapter}.js && git diff --check`
