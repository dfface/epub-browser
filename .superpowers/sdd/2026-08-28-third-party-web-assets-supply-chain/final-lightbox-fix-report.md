# Final GLightbox boundary fix report

## Outcome

The project-owned lightbox adapter now keeps untrusted EPUB markup outside
GLightbox's DOM configuration parser. Reader code selects images, but the
adapter passes GLightbox only explicit records shaped as:

```text
{ href: <validated displayed image URL>, type: "image" }
```

It never passes an EPUB image node or selector to GLightbox. Captions are
omitted, so decoded `alt`, titles, descriptions, and other EPUB strings cannot
reach GLightbox's `innerHTML` caption paths.

## Verified threat boundary

The GLightbox 3.3.1 package source was reviewed before implementation:

- `SlideConfigParser.parseConfig` merges DOM `dataset` values, promotes
  `content` to inline content, infers video/inline/AJAX/external types from
  URLs, and derives an image title from `alt`.
- `Slide.setContent` writes title and description through `innerHTML`.
- video slides dynamically load the default remote Plyr CSS and JavaScript.
- the documented safe programmatic boundary is `elements`, updated through
  `setElements`, with explicit index opening through `openAt`.

The EPUB Server sanitizer intentionally preserves arbitrary `data-*`
attributes, and SSG retains broader source markup. This fix therefore enforces
the boundary at the shared reader adapter instead of changing EPUB content
semantics or the Server content-cache schema.

## Implementation

- Builds image-only slide records from `currentSrc`, falling back to `src`.
- Accepts only sanitizer-compatible base64 raster image data URLs or resolved
  HTTP(S)/`file:` URLs inside the current generated book directory. Cross-
  origin and same-origin outside-book sources are not rebound or reloaded.
- Forces `selector: false` and overwrites any supplied `elements` value before
  constructing GLightbox.
- Owns click listeners and maps each current image to `openAt(index)`.
- Reuses one GLightbox instance, detects unchanged binds, updates changed
  galleries with `setElements`, removes listeners from replaced/pruned nodes,
  and exposes idempotent `destroy` cleanup.
- Keeps the `.fancybox__container` compatibility class used by reader
  navigation guards.
- Makes all initial, pagination, AJAX, and continuous-reader call sites select
  `#eb-content img`; EPUB `data-fancybox` no longer affects gallery membership.

This is a shared SSG/Server UI asset change. It does not change
`SERVER_OUTPUT_REVISION` and does not require EPUB reconversion.

## Hostile regression coverage

`tests/test_lightbox_adapter.js` inspects the exact constructor and
`setElements` arguments supplied to GLightbox. Fixtures include decoded hostile
`alt` plus `data-fancybox`, `data-gallery`, `data-glightbox`, `data-href`,
`data-sizes`, `data-srcset`, `data-title`, `data-type`,
`data-video-provider`, `data-description`, `data-alt`,
`data-desc-position`, `data-effect`, `data-width`, `data-height`,
`data-content`, `data-zoomable`, and `data-draggable` values.

The assertions prove that:

- only validated `href` and literal `type: "image"` reach GLightbox;
- hostile values and remote Plyr URLs are absent from adapter arguments;
- `currentSrc` wins and `src` is the fallback;
- cross-origin and outside-book URLs are excluded;
- clicks open the correct explicit index;
- duplicate binds do not stack handlers;
- AJAX/continuous rebinding removes stale handlers and updates indexes;
- destroy is idempotent and a later bind creates a fresh instance; and
- all four reader call sites ignore EPUB lightbox attributes when selecting
  images.

## Strict TDD evidence

Command used for each cycle:

```text
node tests/test_lightbox_adapter.js
```

Observed RED stages before their corresponding production changes:

1. The constructor-argument assertion showed actual
   `selector: "#eb-content img"` instead of explicit image elements.
2. After image-only construction, the click-listener assertion failed `0 !==
   1`, proving index mapping was still absent.
3. After click/rebind support, the destroy assertion failed because the API
   was undefined.
4. The reader-selector assertion showed the two AJAX/continuous call sites
   still used `img:not([data-fancybox])`.
5. The safe-source assertion showed a same-origin URL outside the generated
   book directory still entered the elements array.

Each failure was followed by the smallest production change and a green
focused rerun before proceeding.

## Final verification

All commands were run after the final source-policy change:

```text
node --test tests/*.js
# 275 passed, 0 failed; exit 0

python3 -m unittest tests.test_generated_reader_surfaces tests.test_static_asset_delivery -q
# Ran 148 tests; OK; exit 0

python3 tools/sync_vendor_assets.py verify
# silent success; exit 0

node --check epub_browser/assets/lightbox-adapter.js
node --check epub_browser/assets/chapter.js
git diff --check
# all exit 0
```

The pre-existing untracked `examples/TheLittlePrince.pdf` and
`examples/TheLittlePrince.pdf.epub-browser.json` were not modified or staged.
