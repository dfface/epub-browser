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

- Builds image-only slide records from raw sanitized `img.getAttribute('src')`.
  It deliberately ignores attacker-influenced `document.baseURI`, `currentSrc`,
  and the resolved `src` DOM property, resolving the raw value against trusted
  `window.location.href` instead.
- Accepts only sanitizer-compatible base64 raster image data URLs or resolved
  HTTP(S)/`file:` URLs under the exact generated page-directory segments and
  its literal `resources` child. Cross-origin and same-origin outside-book
  sources are not rebound or reloaded. For `file:` pages, the resolved image
  host must exactly equal the generated page host, preventing remote file/UNC
  authorities from passing path-only containment.
- Rejects raw or repeatedly decoded slash, backslash, dot-segment, malformed
  percent-encoding, excessive decoding, and duplicate-separator aliases before
  URL resolution. Containment compares path segments rather than string
  prefixes.
- Forces `selector: false` and overwrites any supplied `elements` value before
  constructing GLightbox.
- Owns click listeners and maps each current image to `openAt(index)`.
- Reuses one GLightbox instance, detects unchanged binds, updates changed
  galleries with `setElements`, removes listeners from replaced/pruned nodes,
  and exposes idempotent `destroy` cleanup. While the overlay is open, gallery
  replacement is deferred until one task after GLightbox's `close` event so
  the vendor cannot reset the active slide to zero. A click arriving during
  that transition is queued by image identity and resolved against the new
  indexes.
- An open destroy requests one close, waits until the vendor close callback has
  fully returned, then destroys. A bind arriving during that close is queued
  and creates the replacement instance only after the old instance is gone.
- Keeps the `.fancybox__container` compatibility class used by reader
  navigation guards.
- Makes all initial, pagination, AJAX, and continuous-reader call sites select
  `#eb-content img`; EPUB `data-fancybox` no longer affects gallery membership.
  Direct continuous-window replacement and backward prepend/prune now rebind
  explicitly, matching the existing forward append path.

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
- malicious `document.baseURI`, `currentSrc`, and resolved `src` cannot replace
  the raw generated resource URL;
- cross-origin, outside-book, `%2F`, `%5C`, `%2E` dot-segment,
  double-encoded, and duplicate-separator aliases are excluded;
- local relative and absolute `file:` resources remain accepted, remote file
  authorities are excluded, invalid credential/port file forms fail closed,
  and the test records the platform parser's canonical empty-host treatment
  of `file://localhost`;
- clicks open the correct explicit index;
- duplicate binds do not stack handlers;
- AJAX/continuous rebinding removes stale handlers and updates indexes without
  resetting an open overlay;
- close-time clicks wait for the new index map;
- destroy is idempotent, never destroys an open/closing instance, and a later
  bind cannot overlap the old instance; and
- all six reader call sites ignore EPUB lightbox attributes when selecting
  images, including direct continuous replacement and backward prepend/prune.

## Actual locked-bundle browser proof

`tests/test_lightbox_browser.js` is a dependency-free Chromium/CDP integration
harness. It auto-detects a system Chromium or Playwright Chromium headless
shell (or accepts `EPUB_BROWSER_CHROMIUM`), serves the actual locked
`glightbox.min.js`, project adapter, stylesheet, and controlled image fixtures,
and captures `Network.requestWillBeSent` events.

The real page contains a malicious `<base>`, decoded hostile captions, every
mode-switching attribute needed to trigger video/inline/external behavior, and
no CSP. The scenario opens index 1, appends and binds while open, verifies no
jump, closes and opens the appended image, prunes/reindexes, then destroys and
rebinds during the asynchronous close. It asserts one modal, only image slides,
no iframe/video/hostile markup, no XSS flags, exact generated-book image URLs,
and no request to `evil.invalid`, `cdn.plyr.io`, or any non-fixture origin.

Concrete command and result on this machine:

```text
node --test tests/test_lightbox_browser.js
# 1 passed, 0 failed; actual locked GLightbox 3.3.1; Chromium headless; exit 0
```

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
6. The review correction showed malicious `document.baseURI`/`currentSrc`
   producing `evil.example` slide URLs instead of the raw generated sources.
7. Table cases showed encoded slash/backslash/dot and double-encoded aliases,
   followed by a separate duplicate-separator RED, entering the gallery.
8. Reader call-site assertions showed direct continuous replacement and
   backward prepend/prune lacked rebinding.
9. The realistic lifecycle fake showed `setElements` resetting open index 1 to
   zero, then showed destroy running before asynchronous close completion.
10. A close-callback timing assertion showed gallery replacement happening
    before GLightbox returned from its close event.
11. The first real Chromium close-time run timed out opening the appended
    image, exposing the narrow click-before-deferred-index-update race; the
    focused queued-image test failed before the adapter correction.
12. The file-page constructor assertion showed
    `file://evil.invalid/local/book/resources/remote.png` entering the exact
    GLightbox `elements` array before the file-host equality check.

Each failure was followed by the smallest production change and a green
focused rerun before proceeding.

## Final verification

The complete suite was run after the preceding lifecycle and source-policy
hardening:

```text
node --test tests/*.js
# 276 passed, 0 failed; includes real Chromium/CDP bundle test; exit 0

python3 -m unittest tests.test_generated_reader_surfaces tests.test_static_asset_delivery -q
# Ran 148 tests; OK; exit 0

python3 tools/sync_vendor_assets.py verify
# silent success; exit 0

node --check epub_browser/assets/lightbox-adapter.js
node --check epub_browser/assets/chapter.js
node --check tests/test_lightbox_browser.js
git diff --check
# all exit 0
```

After the final exact file-host correction, the focused adapter regression,
actual locked-bundle Chromium harness, syntax check, vendor verification, and
diff check were rerun:

```text
node tests/test_lightbox_adapter.js
# lightbox adapter tests passed; exit 0

node --test tests/test_lightbox_browser.js
# 1 passed, 0 failed; exit 0

node --check epub_browser/assets/lightbox-adapter.js
node --check tests/test_lightbox_adapter.js
python3 tools/sync_vendor_assets.py verify
git diff --check
# all exit 0
```

The pre-existing untracked `examples/TheLittlePrince.pdf` and
`examples/TheLittlePrince.pdf.epub-browser.json` were not modified or staged.
