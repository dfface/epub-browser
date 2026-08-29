# Task 7 report: PDF.js page rendering lifecycle

## Outcome

- PDF chapter pages load a PDF-only, content-addressed stylesheet and adapter;
  EPUB chapter pages load neither asset.
- The adapter accepts only same-origin hashed PDF.js main/worker URLs, assigns
  the paired worker before loading one shared document task per URL, and makes
  no CDN, CMap, standard-font, ICC, or WASM requests. Optional decoder paths,
  XFA, and error recovery are disabled explicitly.
- Page descriptors paint lazily into DPR-aware canvases and PDF.js 6.2
  selectable `TextLayer` instances. Existing page geometry supports bounded
  zoom, normalized rotation, fit-width/fit-page sizing, and resize rerenders.
- Passwords pass only from the localized browser prompt to PDF.js's
  `onPassword` callback. They are not request parameters, persisted, logged,
  or sent to the application server.
- Loading, error, no-text, and Page N of M states reuse existing localized
  reader copy and accessible status/label semantics.
- Shared chapter replacement, pagination rebuild, continuous append/prepend,
  and bounded-window eviction dispatch format-neutral added/removed events.
  Active render/text jobs and resize observers are cancelled on removal, while
  synchronous page-turn replacements safely reuse the current document task.
- No PDF navigation, settings, annotation popup, or other parallel reader UI
  was added. The Server content revision remains unchanged.

## TDD evidence

RED was observed before implementation for the missing adapter, PDF-only
generated assets, lazy intersection paint, stable resize cancellation, task
reuse across page turning, and fail-closed optional resource configuration.

GREEN verification:

- `node --test tests/test_pdf_chapter.js tests/test_chapter_*.js tests/test_continuous_*.js`
  — 16 tests passed.
- `node --test tests/test_*.js` — 286 tests passed.
- `python3 -m unittest tests.test_generated_reader_surfaces tests.test_i18n_coverage tests.test_asset_publisher tests.test_static_asset_delivery tests.test_vendor_assets -v`
  — 234 tests passed; one opt-in Docker isolation test skipped.
- `node --check epub_browser/assets/pdf-chapter.js` and
  `node --check epub_browser/assets/chapter.js` — passed.
- `git diff --check` — passed.

`AssetPublisher` needed no special-case change: its existing recursive,
content-addressed publication already publishes the new first-party adapter
assets and includes them in static/release inventories.

## Workspace hygiene

`examples/TheLittlePrince.pdf` and
`examples/TheLittlePrince.pdf.epub-browser.json` remain untracked, unstaged,
and unmodified.
