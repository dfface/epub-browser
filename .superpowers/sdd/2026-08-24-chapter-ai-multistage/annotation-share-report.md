# Annotation sharing report

## Scope

Implemented local-only sharing actions in the per-book annotation summary. The global annotated-books overview is unchanged, and the implementation makes no API or third-party requests beyond the annotation hub's existing metadata and TOC loading.

## TDD evidence

### RED

Added focused share-summary, action visibility/labels, clipboard, fallback/failure, download cleanup/filename tests in `tests/test_annotation_hub.js`, then ran:

```text
node --test tests/test_annotation_hub.js
```

Result: 10 passed, 6 failed as expected. Each failure was an expected missing public behavior (`Hub.buildShareSummary`, `Hub.createShareActions`, `Hub.copyShareText`, or `Hub.shareFilename` was not a function).

Added five-locale sharing-key coverage in `tests/test_i18n.js`, then ran:

```text
node --test tests/test_i18n.js
```

Result: 19 passed, 1 failed as expected: `en:annotations.shareActions` was undefined.

### GREEN

Implemented the smallest shared client-side behavior to satisfy the new tests, then ran:

```text
node --test tests/test_annotation_hub.js tests/test_i18n.js
node --check epub_browser/assets/annotation-hub.js
node --check epub_browser/assets/i18n.js
```

Result: 36 passed, 0 failed; both JavaScript syntax checks passed.

## Implementation

- `epub_browser/assets/annotation-hub.js`
  - Deterministic plain-text summary from current in-memory annotations and TOC.
  - Book title, optional authors, localized count, displayed chapter ordering, quoted highlights, and supplied notes; no timestamps.
  - Per-book-only copy/export action group, with labels, accessible names, icons, and standard localized notifications.
  - Clipboard API first; a selection-based plain-text fallback is used if necessary.
  - UTF-8 Blob download with a deterministic safe `.txt` filename and immediate object-URL revocation.
- `epub_browser/assets/annotation-hub.css`
  - Wrapping subordinate action row, 44px minimum targets, and visible keyboard focus.
- `epub_browser/assets/i18n.js`
  - Added complete English, Simplified Chinese, Traditional Chinese, Korean, and Japanese sharing labels/status/fallback copy.
- `tests/test_annotation_hub.js`, `tests/test_i18n.js`
  - Focused behavior and five-locale coverage.

## Verification

```text
for test_file in tests/test_*.js; do node --test "$test_file" || exit $?; done
```

Result: all Node test files passed.

```text
python3 -m unittest discover -s tests -q
```

Result: passed (environment emitted existing asyncio/websocket deprecation diagnostics and expected temporary-server notices only).

```text
python3 -m unittest tests.test_generated_reader_surfaces tests.test_i18n_coverage -v
```

Result: 110 passed, 0 failed.

```text
git diff --check
```

Result: passed.

## Self-review

- Confirmed the action group is created only for a specific book with annotations; the global view never invokes it.
- Confirmed summary generation uses `textContent`/plain strings only, performs no HTML injection, and does not add timestamps.
- Confirmed Blob download is client-only and independent of `/api`, so it works for both SSG and Server pages.
- Confirmed all five runtime dictionaries have identical shape and interpolation-token parity.
- No Server content-cache schema or revision changed because this is UI/runtime data only.

## Review follow-up: synchronous copy failures

The post-implementation review found that synchronous throws from `navigator.clipboard.writeText` and the legacy `document.execCommand('copy')` fallback could escape before the Copy action attached its localized error handler.

### RED

Added two focused behavioral tests in `tests/test_annotation_hub.js`, then ran:

```text
node --test tests/test_annotation_hub.js
```

Result: 16 passed, 2 failed as expected. The new tests showed synchronous `clipboard denied` and `legacy denied` errors escaping `Hub.copyShareText` rather than producing rejecting promises and the existing localized notification.

### GREEN

Made both branches promise-based, contained every fallback exception as a failed copy result, and reran:

```text
node --test tests/test_annotation_hub.js tests/test_i18n.js
node --check epub_browser/assets/annotation-hub.js
for test_file in tests/test_*.js; do node --test "$test_file" || exit $?; done
python3 -m unittest tests.test_generated_reader_surfaces tests.test_i18n_coverage -v
git diff --check
```

Result: focused share/i18n tests 38 passed; all Node test files passed; generated-surface/i18n guards 110 passed; syntax and diff checks passed.

The tests verify both thrown browser APIs return rejecting promises and, through the actual Copy action handler, emit the localized `shareCopyFailed` error notification without throwing from the click handler.

## Final review follow-up: export object-URL lifecycle

The final review found that the object URL could remain allocated if anchor setup failed after allocation, or if anchor cleanup itself threw.

### RED

Added focused fault-injection tests for anchor creation failure, append failure, cleanup failure, and an unavailable `URL.revokeObjectURL`, then ran:

```text
node --test tests/test_annotation_hub.js
```

Result: 18 passed, 4 failed as expected. The created `blob:private` URLs were not revoked after creation/append errors; a removal failure escaped and suppressed revocation; a missing revoker still allocated a URL.

### GREEN

Required both object-URL capabilities before allocation, started the outer cleanup scope immediately after allocation, and independently guarded anchor removal and revocation. Then ran:

```text
node --test tests/test_annotation_hub.js tests/test_i18n.js
node --check epub_browser/assets/annotation-hub.js
node --check epub_browser/assets/i18n.js
for test_file in tests/test_*.js; do node --test "$test_file" || exit $?; done
git diff --check
```

Result: focused annotation/i18n tests 42 passed; all Node test files passed; syntax and diff checks passed.

The fault-injection tests prove each post-allocation creation, append, and removal error revokes the created URL exactly once. They also prove a missing revoker fails before allocation and the export action emits its localized failure notification.

## Concerns

Clipboard fallback support depends on the browser's legacy `document.execCommand('copy')` availability when the modern Clipboard API is unavailable or rejected; unavailable, rejected, and synchronous-throw failures are now explicitly localized and announced.

## Commit

Final commit: `feat: share per-book annotations locally`.
