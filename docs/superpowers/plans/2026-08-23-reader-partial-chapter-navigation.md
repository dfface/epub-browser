# Reader partial chapter navigation implementation plan

> **For the implementation agent:** follow the repository's test-first workflow. Do not change the Server EPUB content-cache revision: this is a reader-shell behavior change.

**Goal:** In normal scrolling reading (not pagination and not continuous scroll), move between chapters by fetching the target chapter page and replacing only `#eb-content`, rather than loading a new document.

**Architecture:** Add a small normal-scroll navigation path in `chapter.js`. It reuses the existing same-origin chapter response format, parses it in a detached element, adopts only the incoming `#eb-content` children and EPUB-derived attributes, then refreshes the chapter-local UI. The browser URL/history remains correct through `pushState` and a guarded `popstate` rehydration. Continuous scrolling and pagination retain their existing behavior.

## Task 1: Replace normal-scroll chapter content without reloading the reader shell

**Files:**
- Modify: `epub_browser/assets/chapter.js`
- Modify: `tests/test_generated_reader_surfaces.py`

1. Write RED source-contract tests for a named normal-scroll navigation helper, DOM-only replacement of `#eb-content`, chapter URL/history handling, and the exclusions for pagination/continuous modes.
2. Add the helper so ordinary previous/next actions and Book TOC chapter links invoke it only in normal scrolling mode. It must fetch same-origin chapter HTML, reject failed/malformed responses without replacing current content, update title/current chapter state/progress/book TOC/chapter-local TOC, move focus or scroll to the requested anchor/top, and rebind content-specific decoration (image/table wrappers, syntax highlighting, Fancybox, annotations).
3. Add one guarded `popstate` listener so browser Back/Forward rehydrates the chapter body without creating another history entry. Preserve hash-only navigation.
4. Keep pagination's full-navigation behavior and continuous scrolling's buffering behavior untouched. Avoid `innerHTML` for the live reader body and do not add a Server-only API dependency.
5. Run the focused Python test file and relevant Node tests. Commit as `feat: swap normal scrolling chapters in place`.

## Task 2: Review and verification

1. Review the Task 1 diff against the goal, especially rapid navigation / stale XHR responses, failed requests, history direction, annotation chapter identity, local heading TOC replacement, and SSG compatibility.
2. Run `python -m unittest tests.test_generated_reader_surfaces` and the relevant Node tests; run `git diff --check`.
3. If Task 1 needs changes, add targeted regression tests and one correction commit. Report the final commit(s), test commands, and residual limitations.
