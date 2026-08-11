# Unified Reader Surfaces Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the library, book, and chapter pages consistent breadcrumb navigation, unobtrusive reader settings, and one neutral frosted-glass full-screen loading treatment.

**Architecture:** Page generators in `library.py` and `processor.py` own semantic HTML and the placement of reader controls. A new `loading.css` is the single source of truth for all full-screen loading treatment, while page-specific styles retain local layout only. Existing `chapter.js` keeps the Custom CSS persistence logic but no longer expects a standalone collapsible panel.

**Tech Stack:** Python 3, `unittest`, generated HTML, vanilla JavaScript, CSS.

## Global Constraints

- The overlay background is exactly `rgba(15, 23, 42, 0.32)` with `blur(12px) saturate(1.05)`.
- Spinner accents remain theme-aware; only the full-screen overlay becomes neutral.
- Local loading indicators and all Custom CSS persistence/preview behavior remain unchanged.
- Breadcrumbs use `<nav aria-label="Breadcrumb">`; only ancestor locations are links and the final location has `aria-current="page"`.
- Settings remain limited to Font and Reading tabs; Custom CSS appears below continuous-scroll controls under `Reading appearance (advanced)`.

---

### Task 1: Add generated-page regression coverage

**Files:**
- Create: `tests/test_generated_reader_surfaces.py`
- Modify: `epub_browser/library.py:145-476`
- Modify: `epub_browser/processor.py:1088-1644`

**Interfaces:**
- Consumes: `EPUBLibrary.create_library_home()` and `EPUBProcessor.create_chapter_template(content, style_links, chapter_index, chapter_title)`.
- Produces: DOM-level assertions over the generated library and chapter HTML, independent of minified whitespace.

- [ ] **Step 1: Write failing tests for the new generated HTML contract**

```python
import tempfile
import unittest
from pathlib import Path

from epub_browser.library import EPUBLibrary
from epub_browser.processor import EPUBProcessor


class GeneratedReaderSurfaceTests(unittest.TestCase):
    def test_library_has_a_current_location_breadcrumb_before_library_info(self):
        with tempfile.TemporaryDirectory() as directory:
            library = EPUBLibrary(directory)
            library.create_library_home()
            html = Path(directory, "index.html").read_text(encoding="utf-8")

        self.assertIn('<nav class="breadcrumb" aria-label="Breadcrumb">', html)
        self.assertIn('<span class="breadcrumb-current" aria-current="page">Library</span>', html)
        self.assertLess(html.index('aria-label="Breadcrumb"'), html.index('class="library-info"'))

    def test_chapter_puts_custom_css_in_the_reading_settings_tab(self):
        with tempfile.TemporaryDirectory() as directory:
            processor = EPUBProcessor("book.epub", directory)
            processor.book_title = "A Book"
            processor.chapters = [{"title": "One"}]
            html = processor.create_chapter_template("<p>Text</p>", "", 0, "One")

        reading_tab_start = html.index('id="reading-tab"')
        editor_start = html.index('id="customCssInput"')
        self.assertGreater(editor_start, reading_tab_start)
        self.assertIn('Reading appearance (advanced)', html)
        self.assertNotIn('id="cssPanelToggle"', html)
```

- [ ] **Step 2: Run the tests to verify they fail for the missing structures**

Run: `python -m unittest tests.test_generated_reader_surfaces -v`  
Expected: FAIL because the library has no breadcrumb and the CSS editor remains in the standalone panel.

- [ ] **Step 3: Implement only the HTML changes needed by the failing tests**

```html
<nav class="breadcrumb" aria-label="Breadcrumb">
  <span class="breadcrumb-current" aria-current="page">Library</span>
</nav>
<header class="library-info" data-id="header">…</header>
```

```html
<div class="settings-group settings-group-advanced">
  <label class="settings-label">Reading appearance (advanced)</label>
  <textarea id="customCssInput"></textarea>
  <!-- existing Custom CSS action controls -->
</div>
```

- [ ] **Step 4: Run the tests to verify the generated HTML contract passes**

Run: `python -m unittest tests.test_generated_reader_surfaces -v`  
Expected: PASS.

- [ ] **Step 5: Commit the tested structural change**

```bash
git add tests/test_generated_reader_surfaces.py epub_browser/library.py epub_browser/processor.py
git commit -m "feat: unify reader navigation and settings"
```

### Task 2: Consolidate full-screen loading styling

**Files:**
- Create: `epub_browser/assets/loading.css`
- Modify: `epub_browser/library.py:157-164`
- Modify: `epub_browser/processor.py:1097-1195`
- Modify: `epub_browser/assets/book.css:773-823`
- Modify: `epub_browser/assets/chapter.css:1500-1550`
- Modify: `epub_browser/assets/library.css:701-751`
- Modify: `epub_browser/assets/theme.css:363-1546`

**Interfaces:**
- Consumes: existing `.loading-overlay` and `.loading-spinner` markup on each generated page.
- Produces: one linked `loading.css` asset that controls overlay layout, backdrop treatment, spinner motion, and reduced-motion fallback.

- [ ] **Step 1: Extend the failing generated-page tests with the shared asset contract**

```python
def test_library_and_chapter_link_the_shared_loading_stylesheet(self):
    self.assertIn('href="/assets/loading.css"', library_html)
    self.assertIn('href="/assets/loading.css"', chapter_html)
```

- [ ] **Step 2: Run the focused tests to verify the shared asset is not linked yet**

Run: `python -m unittest tests.test_generated_reader_surfaces.GeneratedReaderSurfaceTests.test_library_and_chapter_link_the_shared_loading_stylesheet -v`  
Expected: FAIL because `loading.css` is not linked.

- [ ] **Step 3: Add the shared asset and remove duplicate page-level full-screen styles**

```css
.loading-overlay {
    position: fixed;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 9999;
    background: rgba(15, 23, 42, 0.32);
    -webkit-backdrop-filter: blur(12px) saturate(1.05);
    backdrop-filter: blur(12px) saturate(1.05);
}

@media (prefers-reduced-motion: reduce) {
    .loading-spinner { animation: none; }
}
```

Delete the three local `.loading-overlay`, `.loading-spinner`, dark-mode overlay, and Kindle spinner blocks after moving their shared spinner rules into `loading.css`. Remove or neutralize theme-level overlay background overrides so no theme can replace the shared neutral glass.

- [ ] **Step 4: Run focused generated-page tests and perform the CSS smoke checks**

Run: `python -m unittest tests.test_generated_reader_surfaces -v`  
Expected: PASS.

Run: `rg -n "loading-overlay" epub_browser/assets/{book,chapter,library}.css epub_browser/assets/loading.css`  
Expected: only `loading.css` defines the full-screen overlay.

- [ ] **Step 5: Commit the loading consolidation**

```bash
git add epub_browser/assets/loading.css epub_browser/assets/{book,chapter,library}.css epub_browser/assets/theme.css epub_browser/library.py epub_browser/processor.py tests/test_generated_reader_surfaces.py
git commit -m "feat: unify loading glass treatment"
```

### Task 3: Apply shared navigation and settings presentation

**Files:**
- Modify: `epub_browser/assets/library.css:32-67, 434-496, 752-756`
- Modify: `epub_browser/assets/book.css:190-221, 868-870`
- Modify: `epub_browser/assets/chapter.css:203-234, 618-624, 820-839, 1322-1489, 1494-1496`
- Modify: `epub_browser/assets/chapter.js:824-826, 1121-1144`

**Interfaces:**
- Consumes: semantic breadcrumb markup, `.library-info`, and the Custom CSS controls emitted by Task 1.
- Produces: a compact shared breadcrumb, a distinct library information card, and an advanced Custom CSS group that continues to use `customCssFunc()`.

- [ ] **Step 1: Write a failing test for the complete chapter breadcrumb contract**

```python
def test_chapter_has_a_three_level_semantic_breadcrumb(self):
    self.assertIn('<nav class="breadcrumb" aria-label="Breadcrumb">', chapter_html)
    self.assertIn('>Library</span>', chapter_html)
    self.assertIn('aria-current="page">One</span>', chapter_html)
    self.assertNotIn('breadcrumb eb-header', chapter_html)
```

- [ ] **Step 2: Run it to verify the breadcrumb is still header-styled**

Run: `python -m unittest tests.test_generated_reader_surfaces.GeneratedReaderSurfaceTests.test_chapter_has_a_three_level_semantic_breadcrumb -v`  
Expected: FAIL because `breadcrumb eb-header` remains in generated chapter HTML.

- [ ] **Step 3: Implement the visual and interaction changes**

```css
/* Library information only; navigation uses .breadcrumb everywhere. */
.library-info { /* existing .eb-header card rules */ }

.settings-group-advanced {
    border-top: 1px solid var(--border);
    padding-top: 20px;
}
```

Update `customCssFunc()` to use the existing input and action controls directly; remove its standalone-panel toggle lookup and click handler. Keep its storage keys and all action handlers unchanged. Ensure the key handler continues to ignore `#customCssInput` when the editor has focus.

- [ ] **Step 4: Run the complete regression suite and static syntax checks**

Run: `python -m unittest discover -s tests -v`  
Expected: PASS.

Run: `python -m compileall -q epub_browser`  
Expected: exit 0.

- [ ] **Step 5: Commit the presentation and interaction polish**

```bash
git add epub_browser/assets/library.css epub_browser/assets/book.css epub_browser/assets/chapter.css epub_browser/assets/chapter.js epub_browser/library.py epub_browser/processor.py tests/test_generated_reader_surfaces.py
git commit -m "feat: streamline reader settings surface"
```

### Task 4: Perform end-to-end manual acceptance

**Files:**
- Modify: `docs/superpowers/specs/2026-08-12-fullscreen-loading-glass-design.md` only if acceptance reveals a spec mismatch.

**Interfaces:**
- Consumes: generated site from the updated library and all previous automated checks.
- Produces: a manual acceptance result covering desktop and mobile reader states.

- [ ] **Step 1: Generate a library containing at least one EPUB and open it in a browser**

Run: `epub-browser <fixture-or-local-epub-path> --output <temporary-output-directory>`  
Expected: library, book, and chapter pages are generated.

- [ ] **Step 2: Verify desktop visual behavior**

Check: library shows `Library` breadcrumb followed by a distinct library information card; book and chapter pages show `Library / Book` and `Library / Book / Chapter`; neither breadcrumb has the large header-card treatment.

Check: each full-screen Loading state shows the same neutral blurred backdrop in light and dark themes; no opaque white or black flash occurs.

Check: opening Settings → Reading shows continuous-scroll first and `Reading appearance (advanced)` with the Custom CSS editor below it; preview, save, reset, and default actions work as before.

- [ ] **Step 3: Verify mobile and accessibility behavior**

Check at a 375px viewport: breadcrumbs wrap without horizontal overflow, the mobile settings entry exposes the same Reading tab and Custom CSS editor, and the bottom controls do not cover the settings modal.

Check with keyboard: Tab reaches the Reading tab and Custom CSS controls; while the editor is focused, space and arrow keys edit text rather than turning pages.

- [ ] **Step 4: Run final automation evidence**

Run: `python -m unittest discover -s tests -v && python -m compileall -q epub_browser && git diff --check`  
Expected: all tests pass, compilation succeeds, and no whitespace errors are reported.

- [ ] **Step 5: Commit only if acceptance documentation changes**

```bash
git add docs/superpowers/specs/2026-08-12-fullscreen-loading-glass-design.md
git commit -m "docs: record reader surface acceptance"
```
