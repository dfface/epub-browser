# Library Information and Breadcrumb Density Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the library information card lighter and restore equal, medium-height breadcrumbs across the reader.

**Architecture:** CSS-only changes keep generated markup intact. Library-specific rules reduce the information card; the three page styles share the same breadcrumb padding while retaining its gradient top rule.

**Tech Stack:** CSS, Python `unittest` generated-page checks.

## Global Constraints

- `.library-info` has no gradient pseudo-element.
- `.breadcrumb` keeps its gradient top rule and uses 28px 24px padding on every page.

---

### Task 1: Apply and verify the density correction

**Files:**
- Modify: `epub_browser/assets/library.css`
- Modify: `epub_browser/assets/book.css`
- Modify: `epub_browser/assets/chapter.css`
- Test: `tests/test_generated_reader_surfaces.py`

- [ ] **Step 1: Add the failing style contract test**

```python
def test_breadcrumb_styles_have_shared_medium_padding(self):
    for path in ("library.css", "book.css", "chapter.css"):
        css = Path("epub_browser/assets", path).read_text(encoding="utf-8")
        self.assertIn("padding: 28px 24px", css)
```

- [ ] **Step 2: Run the focused test and verify failure**

Run: `python3 -m unittest tests.test_generated_reader_surfaces.GeneratedReaderSurfaceTests.test_breadcrumb_styles_have_shared_medium_padding -v`

- [ ] **Step 3: Apply the CSS correction**

Set every `.breadcrumb` to `padding: 28px 24px`. Remove `.library-info::before`; set library information padding to `28px 20px`, margin-bottom to `28px`, heading size to `2rem`, and the logo dimensions to 44px.

- [ ] **Step 4: Run all checks**

Run: `python3 -m unittest discover -s tests -v && git diff --check`

- [ ] **Step 5: Commit**

```bash
git add epub_browser/assets/{library,book,chapter}.css tests/test_generated_reader_surfaces.py
git commit -m "style: rebalance library info and breadcrumbs"
```
