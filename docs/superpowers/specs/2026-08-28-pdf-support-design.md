# PDF Support Design

**Date:** 2026-08-28

**Status:** Pending written-spec review

## Summary

EPUB Browser will add PDF as a second book format without converting PDF pages
to HTML and without generalizing the existing EPUB processor into a new reader
framework. EPUB continues through `EPUBProcessor` and the current shared EPUB
templates. PDF uses an isolated metadata/conversion path and a PDF.js rendering
adapter, while reusing the current library, identity, permissions, reader
chrome, themes, selection actions, annotations center, and Server services.

The first release supports PDF viewing in SSG and Server. Server additionally
supports synchronized PDF progress, PDF highlights and notes, and the existing
local dictionary and Wikimedia encyclopedia actions. Features that require a
text layer degrade explicitly for scanned or image-only PDFs.

PDF.js is a locally packaged rendering dependency supplied by the locked
third-party asset process described in
`2026-08-28-third-party-web-assets-supply-chain-design.md`. Generated pages do
not load PDF.js or its worker from a CDN.

## Goals

- Discover `.pdf` sources alongside `.epub` sources in SSG, Server, watch mode,
  and legacy command syntax.
- Preserve the current EPUB implementation and user interface.
- Render PDFs in the browser with PDF.js canvas, text, and annotation layers.
- Support outline navigation, text search, page navigation, zoom, rotation,
  print, and download in the first release.
- Support authenticated Server progress, highlights, notes, local dictionary
  lookup, and encyclopedia lookup for PDFs with a usable text layer.
- Keep PDF-derived Server cache data separate from the EPUB `content/` cache
  and its revision.
- Deliver Server PDF bytes through an authenticated, range-capable internal
  endpoint without exposing source paths.
- Extend the new OpenAPI and WebHook contracts additively and preserve their
  existing EPUB behavior.
- Keep the PDF UI visually and behaviorally consistent with the current reader
  rather than redesigning it.

## Non-goals

- Converting PDF pages or text into EPUB-style chapter HTML.
- Refactoring EPUB and PDF into one abstract reader or one content-cache schema.
- OCR, AI reading, AI chat, PDF summarization, or translation in the first PDF
  release.
- Editing PDF content, filling or submitting forms, executing PDF JavaScript,
  or exposing embedded attachments.
- Restoring annotations across a changed PDF by coordinates alone.
- Publishing raw PDF downloads through PAT/OpenAPI endpoints.
- Server APIs, synchronized data, dictionary, encyclopedia, or annotations in
  SSG output.
- Inverting, recoloring, or otherwise modifying rendered PDF page content for a
  reader theme.

## Product capability matrix

| Capability | EPUB SSG | EPUB Server | PDF SSG | PDF Server |
| --- | --- | --- | --- | --- |
| Library and book detail | unchanged | unchanged | adapted | adapted |
| View content | existing HTML | existing HTML | PDF.js | PDF.js |
| Outline and page navigation | unchanged | unchanged | supported | supported |
| Text search | unchanged | unchanged | text-layer PDFs | text-layer PDFs |
| Zoom and rotation | unchanged | unchanged | supported | supported |
| Print and download | unchanged | unchanged | supported | authorized readers |
| Local progress | unchanged | unchanged | supported | supported before sync |
| Synchronized progress | n/a | unchanged | n/a | PDF-specific record |
| Highlight and note | unchanged | unchanged | unavailable | text-layer PDFs |
| Dictionary and encyclopedia | n/a | unchanged | unavailable | text-layer PDFs |
| Annotation center | n/a | unchanged | n/a | combined EPUB/PDF view |
| PDF forms | n/a | n/a | read-only display | read-only display |
| PDF JavaScript/attachments | n/a | n/a | disabled | disabled |
| OCR and AI | n/a | existing EPUB behavior | unavailable | unavailable |

“Unavailable” is a deliberate capability boundary, not a failed button. SSG
must not emit `/api/*` references or Server-only assets, and a scanned PDF must
remain readable even when text-dependent actions cannot be offered.

## Architectural boundary

### EPUB path remains unchanged

EPUB discovery, parsing, cleaning, TOC normalization, chapter cache generation,
shared templates, dynamic Server restoration, AI reading, and all existing
tests continue to use the present EPUB modules. PDF support may add a narrow
format dispatch before EPUB processing, but it does not rename, relocate, or
generalize `EPUBProcessor` merely to make the new format appear symmetric.

### PDF path

The proposed responsibility split is:

- `epub_browser/pdf_processor.py`: PDF signature validation, safe metadata
  extraction, generic cover metadata, Server PDF cache writing, SSG document
  copying, and the shared PDF reader-shell renderer;
- `epub_browser/pdf_pages.py`: Server restoration of PDF metadata and dynamic
  invocation of the shared PDF shell renderer;
- `epub_browser/pdf_delivery.py`: authenticated GET/HEAD/Range delivery,
  validators, and source-change checks;
- `epub_browser/assets/pdf-reader.js`: project-owned PDF.js integration,
  rendering scheduler, search, outline, navigation, progress, and selection
  adapter;
- `epub_browser/assets/pdf-reader.css`: PDF-only canvas/text/overlay styles,
  scoped below a PDF reader root and based on existing theme variables;
- state-store additions for PDF progress and annotations.

Exact module names may be refined in the implementation plan, but the
separation of EPUB processing, PDF metadata, PDF page rendering, and PDF byte
delivery is part of this design.

Both SSG and Server call one PDF shell renderer. Deployment mode changes the
document URL and availability of authenticated services, not the page markup
source of truth.

## Source discovery and format classification

Discovery accepts `.epub` and `.pdf` case-insensitively. A candidate PDF must
also begin with a valid PDF header within the allowed leading-byte window;
renaming arbitrary content to `.pdf` is not sufficient.

Every registered book has an explicit `source_format` of `epub` or `pdf`.
Format comes from validated source inspection and is not inferred later from a
title, generated URL, or cache directory. Existing EPUB database rows migrate
to `epub`.

Format-specific conversion errors identify the source without returning file
content, passwords, absolute paths, or parser tracebacks to readers or WebHook
payloads.

## PDF metadata and Server cache

PDF metadata extraction uses a small pure-Python dependency such as `pypdf`.
It is limited to fields needed before the browser opens the document:

- title and authors where safely available;
- page count where available without a password;
- encrypted state;
- whether an outline appears to be available;
- source fingerprint and format.

The first release uses a project-owned generic PDF cover. It does not render a
page during Server conversion merely to produce a thumbnail.

Server writes PDF-derived metadata to:

```text
book/<book_id>/pdf/metadata.json
book/<book_id>/.server-pdf-revision
```

The precise revision-file placement may follow the existing book cache layout,
but it remains named and validated independently from
`.server-content-revision`. PDF conversion writes no `chapter_<n>.json`,
`toc.json`, or EPUB `content/` entry.

The initial logical metadata schema is:

```json
{
  "schema": 1,
  "format": "pdf",
  "title": "Document title",
  "authors": ["Author"],
  "page_count": 64,
  "encrypted": false,
  "has_outline": false,
  "source_fingerprint": {
    "algorithm": "sha256",
    "value": "<64-lowercase-hex>"
  }
}
```

For an encrypted document whose page count or outline cannot be inspected
without a password, those values are `null` rather than guessed. The browser
may learn them after the reader supplies a password, but the password and
decrypted metadata are not written back to disk, logs, SQLite, or WebHooks.

Changing only PDF reader HTML, JavaScript, CSS, i18n, permissions, or dynamic
controls does not raise `.server-pdf-revision` and does not require reconversion.
Only an incompatible PDF-derived metadata schema or meaning raises it.

`SERVER_OUTPUT_REVISION` and the EPUB cache validator do not change for this
feature.

## Document delivery

### SSG

SSG copies the validated source bytes without modification to:

```text
book/<book_id>/document.pdf
```

The PDF reader shell refers to that relative static path. Progress is local
browser state. The page contains no Session assumptions, `/api/*` URLs,
dictionary assets, encyclopedia calls, or synchronized annotation code.

### Server

The dynamic reader shell obtains bytes from an internal Session-only route:

```text
GET|HEAD /api/books/<book_id>/document
```

The route performs, in order:

1. Session authentication;
2. current book visibility and read-permission checks;
3. source-format verification;
4. registered-source stat and fingerprint consistency checks;
5. safe GET, HEAD, or single-range response generation.

Missing and inaccessible books are indistinguishable to unauthorized readers.
The response supports byte ranges required by PDF.js and includes a stable ETag
derived from the registered source fingerprint, `Accept-Ranges: bytes`, an
inline PDF content disposition with a sanitized filename, an explicit PDF
content type, `X-Content-Type-Options: nosniff`, and the existing private cache
policy. Invalid or unsatisfiable ranges return the appropriate bounded error.
Multipart ranges are not required in the first release.

The handler never returns the registered absolute path. If the source changes
after registration, the route refuses to combine bytes with stale metadata and
asks the existing library reconciliation path to refresh the book.

Authorized browser readers can print or download because PDF.js must already
receive the document bytes. Hiding those controls is not treated as a security
boundary. PAT/OpenAPI deliberately does not expose this raw-document route.

## PDF.js integration

PDF.js main and worker modules are locked, packaged locally, and verified as a
version-matched pair. EPUB Browser uses rendering components rather than the
upstream default viewer UI.

The project-owned adapter provides:

- lazy page rendering near the viewport instead of eagerly rendering the whole
  document;
- fixed page aspect-ratio placeholders to avoid layout shift;
- canvas rendering with a selectable text layer when available;
- a separate EPUB Browser annotation overlay above the PDF.js layers;
- outline loading and navigation;
- text search with result count and next/previous navigation;
- page input and previous/next navigation;
- fit-width, fit-page, zoom in, zoom out, and rotation;
- print and download through the already authorized document source;
- explicit progress, retry, password, unsupported, and degraded states.

Page render jobs are cancelled when superseded by navigation, zoom, rotation,
or teardown. Scroll and resize work is throttled. The worker URL comes from the
existing hashed asset publisher rather than a hardcoded path.

The browser opens encrypted PDFs through PDF.js's client-side password flow.
The Server never receives or stores that password. A cancelled or incorrect
password leaves the book registered and presents a recoverable reader state.

PDF forms are not interactive in the first release. PDF scripting is disabled,
and no attachment panel or attachment download action is exposed.

## UI and UX consistency

PDF support does **not** redesign the reader.

The PDF shell reuses the current:

- `app-nav` and application navigation placement;
- `reader-toolbar`, `top-controls`, `chapter-tools`, and `control-btn` patterns;
- reader drawers and drawer backdrop;
- bottom desktop page-navigation and current mobile control patterns;
- settings modal, loading indicator, notifications, skip link, pure-reading
  behavior, and annotation center entry point;
- Font Awesome icon language;
- existing light, dark, sepia, green, blue, pink, and purple theme variables;
- typography, spacing, borders, radii, shadows, focus rings, responsive
  breakpoints, and reduced-motion treatment.

PDF outline uses the existing reader-drawer pattern. PDF search uses the same
drawer/surface language and existing `control-btn` styling. Page number input,
previous/next controls, and mobile navigation occupy the equivalent locations
already used by the EPUB reader. Zoom, fit, and rotation are added as PDF-only
controls using existing button and settings patterns. Print and download are
visible to authorized desktop readers and remain reachable through the same
settings/action treatment on constrained screens.

The PDF canvas and its text/annotation layers are the only genuinely new visual
surface. `pdf-reader.css` is scoped to the PDF root, derives colors from the
current reader variables, and adds no new global font, icon library, navigation
system, or competing design tokens. Reader themes change the surrounding
canvas and chrome; they do not invert the pixels of a PDF page.

The existing annotation selection toolbar is reused without visual redesign,
action reordering, or EPUB CSS changes. UI/UX review for this feature evaluates
consistency, degradation, responsiveness, and accessibility rather than
proposing a new visual direction.

## Accessibility and interaction

Project-owned reader chrome targets WCAG 2.2 AA:

- semantic buttons, toolbar/drawer/dialog labels, and live loading/error
  status;
- visible focus indicators and logical DOM/Tab order matching the current
  reader;
- the existing skip link leading to the PDF document region;
- minimum 44-by-44-pixel touch targets through existing controls;
- Escape dismissal and focus restoration for drawers and dialogs;
- operation at 375 CSS pixels, landscape phone width, and 200%/400% browser
  zoom without losing controls;
- `prefers-reduced-motion` support and no decorative continuous animation;
- PageUp/PageDown and current-reader navigation behavior while the PDF document
  region is active;
- `Ctrl/Cmd+F` opening PDF text search without creating an unescapable keyboard
  trap.

Each rendered page has an accessible page label such as “Page 3 of 64”. PDF.js
text and structure layers are used where available. EPUB Browser cannot create
semantic headings, reading order, alternative text, or searchable text that is
absent from the source PDF. A scanned or untagged PDF therefore remains a
document-source accessibility limitation, not a reason to make the reader
controls inaccessible.

## Progress model

Existing EPUB progress data and APIs remain intact. Server adds a PDF-specific
table:

```text
pdf_reading_progress(
  user_id,
  book_id,
  page_number,
  page_offset,
  scale_mode,
  rotation,
  updated_at
)
```

`page_number` is one-based at API and UI boundaries. `page_offset` is a bounded
normalized position within the page and permits a stable return location in
continuous-scroll mode. `scale_mode` stores a stable symbolic value such as
`fit-width`, `fit-page`, or `custom`; an implementation may store a separate
bounded custom scale when needed. Rotation is normalized to 0, 90, 180, or 270.

The browser writes local progress first and synchronizes with the same
debounced, last-write-aware behavior used by the existing reader. A Server
response is validated against current page count before restoration.

## PDF annotation model

Existing EPUB `annotations` rows and highlighter metadata do not change. Server
adds:

```text
pdf_annotations(
  id,
  user_id,
  book_id,
  page_number,
  quote,
  prefix,
  suffix,
  rects_json,
  note,
  color,
  source_fingerprint,
  created_at,
  updated_at
)
```

Each rectangle is normalized to the unrotated PDF page coordinate space, so
zoom, device pixel ratio, and reader rotation do not rewrite stored annotation
coordinates. A multiline same-page selection stores multiple rectangles.
Initial highlight/note creation is limited to one page.

`quote`, bounded `prefix`, and bounded `suffix` provide readable context and a
future recovery aid. `source_fingerprint` binds the geometry to the exact PDF
bytes. If the registered source fingerprint changes, annotations are not
painted at their former coordinates. They remain visible in the annotation
center as detached records with an explicit status until a later recovery flow
is designed.

The annotation overlay is separate from the PDF.js text layer. Re-rendering a
page, changing zoom, rotating, or replacing a canvas rebuilds overlay geometry
from normalized records without mutating PDF.js internals.

The annotation center merges EPUB and PDF records at the service/presentation
layer. A PDF entry links back to the existing book reader with a project-owned
fragment:

```text
/book/<book_id>/index.html#page=37&annotation=<annotation_id>
```

It shows page location rather than fabricating an EPUB chapter.

## Selection, dictionary, and encyclopedia

The current selection action component remains:

```text
Copy / Highlight / Note / Dictionary / Encyclopedia
```

EPUB continues to supply the existing highlighter source. The PDF adapter
supplies selected text, page number, normalized rectangles, quote context, and
an on-screen anchor rectangle to the same presenter.

For a same-page selection in Server mode, all five actions are available. The
dictionary and encyclopedia actions reuse `dictionary.js`, its result dialog,
the existing authenticated routes, book ACL checks, language inference, i18n,
request cancellation, and security policy. No PDF-specific dictionary or
encyclopedia backend is added.

For SSG, the selection component exposes only actions supported without Server
state or `/api/*`; PDF annotations, dictionary, and encyclopedia remain absent.
For a cross-page PDF selection, Copy remains available while the other actions
are rejected with a short localized explanation instead of storing unstable
geometry. For a PDF without a usable text layer, selection, text search,
highlight, note, dictionary, and encyclopedia are unavailable with one clear
localized capability message.

## Book ID storage

The CLI keeps the existing option and values:

```text
--book-id-storage sidecar|embedded
```

There is no PDF-specific option and no runtime fallback:

- `sidecar`: EPUB and PDF identities use adjacent sidecars;
- `embedded`: EPUB uses the current OPF carrier, while PDF still uses an
  adjacent sidecar and startup emits one clear informational notice explaining
  that embedded storage applies only to EPUB.

The PDF sidecar path is:

```text
document.pdf.epub-browser.json
```

It uses the existing schema-1 `book_id` and SHA-256 source fingerprint contract
without a redundant format field. EPUB Browser never writes XMP, document-info,
incremental updates, or other metadata into the PDF.

The identity implementation becomes capability-aware:

- `sidecar_path_for(source_path)` replaces EPUB-specific path naming;
- source inspection reports `source_format`;
- embedded carrier read/write is called only for EPUB;
- orphan sidecar discovery receives the complete discovered EPUB/PDF source
  set;
- duplicate ID, copy, move, rename, read-only directory, symlink, hard-link,
  fingerprint, and malformed-sidecar rules apply equally to PDFs.

A read-only PDF source requires a valid pre-existing sidecar. CLI help and the
legacy migration hint explain the EPUB-only scope of `embedded` without adding
a new configuration value.

The repository sample `examples/TheLittlePrince.pdf` may be used locally for
manual and end-to-end validation. It has SHA-256
`7b904879f98250ff5981ae53e238dda5d321df2b177327a64a8a9a785dd0d584`,
64 pages, no encryption, no form, and no PDF JavaScript. Because the provided
file has no redistribution license metadata, it is not included in commits or
release artifacts unless its redistribution rights are established. CI uses
small generated or clearly licensed PDF fixtures.

## OpenAPI compatibility

The Server PAT/OpenAPI feature remains Server-only. PDF support modifies its
stable contract additively:

- book list and detail responses gain `format: "epub" | "pdf"`;
- legacy EPUB items explicitly report `epub` rather than relying on a default
  title such as “EPUB Book”;
- requesting chapters or chapter content for a PDF returns
  `409 unsupported_book_format` and never invents one chapter per page;
- the internal raw-document route is not mounted under `/api/v1` and cannot be
  reached with a PAT;
- progress response/request schemas become a discriminated EPUB/PDF union while
  retaining every existing EPUB field and accepted request shape;
- annotation schemas become a discriminated EPUB/PDF union; EPUB retains
  `chapter_index`, `startMeta`, and `endMeta`, while PDF uses page, quote context,
  rectangles, and source fingerprint;
- token-owner and administrator reads include both formats and preserve
  ownership, visibility, pagination, and scope checks.

Representative PDF progress JSON is:

```json
{
  "book_id": "<book-id>",
  "format": "pdf",
  "location": {
    "page_number": 37,
    "page_offset": 0.25,
    "scale_mode": "fit-width",
    "rotation": 0
  },
  "updated_at": "<timestamp>"
}
```

OpenAPI 3.1 declares the discriminator and both schemas explicitly. Contract
tests prove that existing EPUB clients continue to work and that PDF-only
fields cannot be submitted for an EPUB book or vice versa.

## WebHook compatibility

Existing WebHook event names remain stable:

- `book.created`, `book.updated`, and `book.deleted` cover either format;
- `book.conversion.started`, `book.conversion.succeeded`, and
  `book.conversion.failed` cover EPUB conversion or PDF metadata indexing.

Allowlisted book and conversion payloads gain `format`. The event envelope
remains version 1. Existing `X-EPUB-*` signature and delivery headers remain for
compatibility even when the subject is a PDF; renaming them would be a separate
protocol version.

PDF failure events contain a stable error code and safe summary. They never
contain source bytes, passwords, selected text, absolute paths, parser
tracebacks, or decrypted metadata. SSG emits no WebHooks.

## Security and privacy

- Every Server HTML, document, progress, annotation, dictionary, encyclopedia,
  print, and download path checks current Session authentication and book
  visibility before reading protected data.
- Browser-supplied page count, book format, source fingerprint, owner, and file
  path are not trusted.
- PDF byte delivery is internal, range-bounded, path-hidden, and unavailable to
  PATs.
- PDF passwords exist only in the PDF.js client flow.
- Annotation quote context is private user data and follows existing ownership,
  API scope, administration, export, and deletion boundaries.
- PDF scripts, form submission, launch actions, and attachments are disabled.
- SSG pages remain static and independent of login, SQLite, or `/api/*`.

## Implementation sequence

1. Complete and verify the third-party asset supply chain.
2. Add locked PDF.js assets and a generated/clearly licensed PDF test corpus.
3. Generalize source discovery and book identity dispatch without changing EPUB
   carrier behavior.
4. Add PDF metadata cache and SSG output.
5. Add authenticated Server document delivery and dynamic PDF pages.
6. Implement the project-owned PDF.js adapter using the current reader UI.
7. Add PDF progress, annotation storage, overlays, and annotation-center merge.
8. Adapt the shared selection actions, including dictionary and encyclopedia.
9. Add OpenAPI and WebHook format contracts.
10. Complete browser E2E, accessibility, and UI/UX review gates.

## Verification and acceptance

### Automated unit and integration tests

- PDF header/type validation, metadata, encrypted metadata degradation, generic
  cover, cache revision, atomic output, and source fingerprint changes;
- SSG output contains `document.pdf`, local assets, and no `/api/*` dependency;
- Server reader HTML is dynamic and reflects UI/asset/i18n changes without PDF
  re-indexing;
- GET, HEAD, valid ranges, invalid ranges, ETag, conditional requests, ACL,
  missing/inaccessible equivalence, and changed-source refusal;
- sidecar and embedded CLI behavior for EPUB/PDF, moves, copies, orphans,
  duplicates, read-only inputs, and watch events;
- PDF progress and annotation ownership, geometry validation, fingerprint
  detachment, migration, and admin reads;
- dictionary/encyclopedia reuse and scanned/cross-page/SSG degradation;
- OpenAPI discriminated schemas, PDF chapter 409 responses, and absence of raw
  PDF PAT routes;
- WebHook payload format, unchanged event names/envelope/headers, and failure
  redaction;
- unchanged EPUB SSG, Server, conversion, cache, AI, progress, annotations,
  dictionary, and OpenAPI behavior.

### Browser end-to-end tests

Tests run against real SSG and Server pages in supported desktop and mobile
browser sizes. They cover:

- first page load and range-backed progressive rendering;
- outline, search, page input, previous/next, fit, zoom, rotation, print, and
  download;
- reload and cross-device Server progress restoration;
- same-page selection, Copy, Highlight, Note, Dictionary, Encyclopedia, and
  annotation-center deep link;
- cross-page and no-text-layer degradation;
- encrypted password success, failure, cancellation, and non-persistence;
- light/dark/current themes without altering PDF pixels;
- 375px portrait, phone landscape, tablet, desktop, 200%/400% browser zoom,
  keyboard-only operation, and reduced motion.

The local `examples/TheLittlePrince.pdf` is used for manual and workspace E2E
testing when present. CI uses redistributable deterministic fixtures so release
artifacts do not depend on that local file.

### UI/UX gates

Before implementation, `ui-ux-pro-max` is used only to validate consistency,
accessibility, touch sizing, loading feedback, focus, stacking, and responsive
behavior. It must not create a new visual direction or replace current reader
patterns.

After implementation and E2E testing, the `UI/UX Design Review` skill reviews
actual rendered artifacts and interactions for:

- consistency with the existing EPUB reader;
- WCAG 2.2 A/AA issues, keyboard traps, focus management, semantic labels, and
  contrast;
- desktop/mobile/landscape reflow and touch targets;
- loading, error, password, empty-outline, no-result, and degraded states;
- selection menu, drawers, settings, annotation overlays, and annotation-center
  behavior.

Critical and High findings are fixed and the affected automated and browser
tests are rerun before the feature is considered complete. Final verification
also includes relevant SSG and Server suites and `git diff --check`.

## References

- [PDF.js website integration](https://github.com/mozilla/pdf.js/wiki/Setup-pdf.js-in-a-website)
- [PDF.js distribution file structure](https://github.com/mozilla/pdf.js/blob/master/docs/contents/getting_started/index.md?plain=1)
- [PDF.js viewport and rendering examples](https://github.com/mozilla/pdf.js/blob/master/docs/contents/examples/index.md)
- [pypdf documentation](https://pypdf.readthedocs.io/)
