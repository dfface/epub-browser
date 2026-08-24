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

## Concerns

None. Clipboard fallback support depends on the browser's legacy `document.execCommand('copy')` availability when the modern Clipboard API is unavailable or rejected; failure is explicitly localized and announced.

## Commit

Final commit: `feat: share per-book annotations locally`.
