# PDF Support Design: Page-as-Chapter

**Date:** 2026-08-28

**Status:** Approved in chat; pending written-spec review

## Summary

EPUB Browser will support PDF by treating every PDF page as an EPUB-style
chapter. PDF page 1 maps to `chapter_0.html`, page 2 maps to
`chapter_1.html`, and so on. PDF therefore uses the existing Book page,
chapter template, chapter navigation, TOC, reading modes, progress, reading
sessions, settings, annotation component, selection action popup, dictionary,
encyclopedia, and annotation center instead of presenting a second reader UI.

PDF.js has one narrow responsibility: render a requested PDF page into the
content area of an ordinary EPUB Browser chapter. It does not supply a viewer
shell, navigation bar, settings panel, selection popup, annotation UI, TOC, or
progress model.

SSG writes one `chapter_<index>.html` shell per PDF page. Server stores only
PDF-derived metadata and renders those same chapter shells dynamically. Both
modes keep one copy of the original PDF document. Existing EPUB behavior and
its Server content-cache schema remain unchanged.

## Goals

- Discover `.pdf` alongside `.epub` in SSG, Server, watch mode, and legacy CLI
  syntax.
- Produce PDF chapter pages with the same
  `EPUBProcessor.create_chapter_template` used for EPUB chapters.
- Make every PDF page a real chapter for URLs, TOC, previous/next navigation,
  continuous reading, pagination, progress, reading insights, and annotations.
- Always show every page in the TOC. Attach embedded PDF outline titles to
  their destination pages as markers without replacing page entries.
- Use the existing EPUB settings tabs and exact annotation selection popup.
- Support Highlight, Note, Dictionary, and Encyclopedia through the existing
  components for PDFs with a usable text layer.
- Degrade text-dependent features explicitly for scanned or image-only PDFs.
- Keep PDF-derived Server cache data separate from the EPUB `content/` cache.
- Deliver Server PDF bytes through an authenticated, range-capable route.
- Extend OpenAPI and WebHook contracts additively.
- Package PDF.js through the locked third-party asset process, never a runtime
  CDN.

## Non-goals

- A standalone `reader.html` PDF application or the PDF.js default viewer UI.
- PDF-specific copies of application navigation, settings, chapter toolbar,
  selection popup, annotation settings, annotation center, or insights UI.
- Converting PDF pixels or extracted text into authored EPUB HTML.
- OCR, AI reading, AI chat, summarization, translation, PDF editing, form
  submission, PDF JavaScript, or attachments in the first release.
- Redesigning the current EPUB reader.
- Writing identity metadata into PDF bytes.

## Page-to-chapter model

The mapping is exact:

| PDF concept | EPUB Browser concept |
| --- | --- |
| Page 1 | chapter index 0 / `chapter_0.html` |
| Page N | chapter index N-1 / `chapter_{N-1}.html` |
| Page label | localized chapter title `Page N` |
| Outline destination | marker on the destination page entry |
| Current page | current chapter |
| Page annotation | annotation with `chapter_index=N-1` |
| Continuous PDF reading | existing continuous chapter loading |
| PDF page turning | existing EPUB pagination/turning mode |

Page numbers remain one-based in labels and PDF.js. Chapter indices remain
zero-based in URLs, state, APIs, and SQLite.

## Shared reader architecture

### Canonical chapter URLs

Every page has a canonical URL:

```text
/book/<book_id>/chapter_<page_index>.html
```

Book Read and Continue links point to the appropriate chapter. `reader.html`
is not a rendering surface. If retained for old links, it only redirects to
`chapter_0.html`; no UI or state may depend on it.

### Shared template

PDF pages call `EPUBProcessor.create_chapter_template` with the normal book ID,
chapter index, localized page title, total chapter count, TOC, and deployment
mode. The only PDF-specific content is a render placeholder:

```html
<div class="pdf-page-content" data-pdf-page-number="12"></div>
```

The result keeps the same DOM hierarchy, IDs, navigation, settings modal,
Appearance/Reading/Annotations tabs, annotation hub, progress bar, mobile
controls, accessibility structure, Server controls, and asset order as EPUB.
PDF-specific rotation, fit, print, download, and document search actions use
existing buttons, drawers, dialogs, and settings patterns.

### PDF.js adapter

`pdf-chapter.js` loads the document and renders page placeholders. One adapter
instance renders every `[data-pdf-page-number]` node entering the live reader
DOM. It reserves page aspect ratio, paints canvas and text layers lazily,
cancels superseded jobs, and releases canvases removed by the existing bounded
continuous-chapter window.

The existing reader loads adjacent `chapter_N.html` documents by XHR. The PDF
adapter observes, or receives one small format-neutral lifecycle event for,
inserted and removed chapter content. The shared loader does not gain PDF
navigation or a second page list. PDF scripting and form submission remain
disabled.

### Reading modes

PDF uses the same `turning` and `continuousScroll` preferences and the same
Settings > Reading controls as EPUB:

- ordinary scrolling displays the current page/chapter;
- continuous scrolling loads adjacent page chapters with the existing chapter
  window;
- pagination/turning uses existing reader and chapter navigation behavior.

There is no PDF-only reading-mode preference. Text-flow settings that cannot
alter PDF pixels remain in the same panel but are disabled or explicitly
unavailable rather than pretending to work. Theme and reader-layout settings
remain active.

## TOC and embedded outline

The normalized TOC always has one base entry per page in page order:

```json
{
  "title": "Page 12",
  "chapter_index": 11,
  "chapter_file": "chapter_11.html",
  "page_label": "12",
  "outline_labels": ["The Desert"]
}
```

`outline_labels` is empty for unmarked pages. Multiple outline items on one
page remain attached in source order. Outline nesting may be secondary visual
metadata, but must not reorder, duplicate, indent away, or remove page entries.
The Book TOC, reader drawer, desktop sidebar, progress restoration, and
annotation links consume this one list.

## Annotation and selection reuse

PDF uses the existing `annotation.js` initialization and exact selection
action popup. There is no PDF selection menu, PDF annotation settings tab, or
PDF-specific reorder/export component.

After PDF.js finishes a text layer, the adapter exposes it beneath the normal
chapter section and refreshes the existing annotation module for that chapter.
In continuous mode, each page is already inside the existing
`.continuous-chapter[data-chapter-index]` container.

PDF uses the existing annotation storage and API with
`chapter_index = page_number - 1`. Highlighter metadata, quote, note, color,
ownership, export, annotation-center listing, and deep links are shared. No
`pdf_annotations` table or parallel annotation API is introduced.

The first release supports selection within one page. Cross-page selection may
retain Copy, while annotation and lookup actions show a localized unsupported
message. A document without a usable text layer remains readable but does not
offer selection-based Highlight, Note, Dictionary, Encyclopedia, or search.
Dictionary and Encyclopedia come from the exact existing selection popup and
reuse `dictionary.js`, ACLs, locale handling, request cancellation, and result
dialog.

## Progress and reading insights

PDF reuses chapter progress and reading sessions:

- local continuation stores `eb_ci_<page_index>`;
- chapter-change events report page index and localized page title;
- Server reading-session heartbeats use the existing chapter contract;
- Reading Insights counts and links PDF pages as chapters;
- annotation links target
  `chapter_<page_index>.html?annotation=<annotation_id>`.

A PDF-only preference may store rotation or fit mode. It must not duplicate
current chapter, continuous-scroll, pagination, or reading-session progress.
No `pdf_reading_progress` table is added in this release.

## Source metadata, cover, and identity

Discovery accepts `.epub` and `.pdf` case-insensitively and validates the PDF
signature. Every book records `source_format`; existing rows migrate to
`epub`.

A bounded parser such as `pypdf` extracts title, authors, page count,
encryption, extractable-text capability, page dimensions, and outline
destinations. The first page is rendered to a bounded cover image so the
shared library and Book page use their normal cover presentation.

Server stores immutable PDF-derived data separately:

```text
book/<book_id>/pdf/metadata.json
book/<book_id>/.server-pdf-revision
```

It contains the page list, dimensions, outline markers, fingerprint, and
capability flags, but no HTML, i18n, UI, permissions, user data, annotations,
sessions, or compiled asset URLs. UI changes need only a Server restart. The
EPUB `.server-content-revision` remains unchanged.

The CLI retains `--book-id-storage sidecar|embedded`. In `sidecar`, both
formats use adjacent sidecars. In `embedded`, EPUB keeps its OPF carrier while
PDF still uses `document.pdf.epub-browser.json` and logs one clear notice that
embedded storage is EPUB-only. PDF bytes are never mutated for identity.

The local `examples/TheLittlePrince.pdf` and sidecar remain in the worktree for
manual and E2E testing. They are not committed or shipped unless redistribution
rights are established. CI uses generated or clearly licensed fixtures.

## SSG and Server delivery

SSG copies the source once to `book/<book_id>/document.pdf`, writes
`index.html`, `toc.json`, and every `chapter_<index>.html`. SSG reader pages
contain no Session scripts, `/api/*`, synchronized annotation, dictionary, or
encyclopedia dependencies.

Server dynamically renders Book, TOC, and chapter pages from the PDF metadata
cache. It delivers bytes through:

```text
GET|HEAD /api/books/<book_id>/document
```

The route checks Session authentication, book visibility, format, and source
fingerprint before bounded single-range responses. It provides ETag,
`Accept-Ranges`, private caching, `nosniff`, inline PDF disposition, and no
absolute path. It is not exposed to PATs.

## OpenAPI and WebHooks

Book list/detail responses add `format: "epub" | "pdf"`. PDF chapter APIs do
not return `409`: pages are chapters, so chapter lists and metadata use the
existing zero-based chapter contract. APIs that return authored chapter text
must report an explicitly supported PDF-derived representation rather than
claiming canvas pixels are EPUB HTML. EPUB shapes remain unchanged.

Progress, reading sessions, and annotations retain their chapter-based
contracts. Rotation/fit preferences do not enter those APIs. OpenAPI documents
PDF page-as-chapter semantics and proves existing clients remain compatible.
The raw-document route remains unavailable to PATs.

Existing WebHook event names, envelope, and `X-EPUB-*` headers remain stable.
Book and conversion payloads add `format`; conversion means EPUB conversion or
PDF metadata indexing. Failures never include bytes, passwords, selected text,
absolute paths, or tracebacks. SSG emits no WebHooks.

## Third-party assets

PDF.js and existing third-party browser dependencies use the approved locked
process in `2026-08-28-third-party-web-assets-supply-chain-design.md`. Git
tracks the lock, licenses, notices, and sync tool; generated vendor blobs are
hydrated and verified for Docker, wheel, sdist, and GitHub Pages builds.
Installed/runtime applications never fetch them from a CDN.

## Accessibility and degradation

The shared template retains semantic controls, focus order, skip link,
keyboard behavior, reduced motion, touch targets, breakpoints, and loading and
error surfaces. Every PDF page has an accessible label such as “Page 12 of
64”. PDF.js text/structure layers are used where available; the application
does not invent missing reading order, headings, alt text, or searchable text.

Encrypted PDFs use PDF.js's client-side password flow. Passwords are never
sent, logged, stored, cached, or included in WebHooks. Scanned, untagged,
encrypted, invalid, and changed-source states preserve safe reading and explain
unavailable capabilities.

## Implementation boundaries

The implementation may add source dispatch, PDF metadata/cover/cache handling,
processor hydration with page-shaped chapters, SSG chapter generation, Server
dynamic chapter rendering and range delivery, a scoped PDF render adapter,
narrow format-neutral reader lifecycle hooks, OpenAPI/WebHook format fields,
and locked build assets.

It must not fork the chapter template, annotation UI, settings tabs, selection
presenter, dictionary dialog, annotation center, reading sessions, or chapter
progress state.

## Verification and acceptance

Automated coverage includes:

- PDF validation, metadata, cover, dimensions, outline, encryption, and no-text
  degradation;
- every page becoming canonical `chapter_N.html` in SSG and Server;
- complete page TOC with sparse and multiple outline markers;
- Book Read/Continue, previous/next, sidebar, progress, sessions, insights,
  annotations, and OpenAPI using chapter indices;
- exact shared settings and annotation components, with no PDF-specific
  selection or annotation settings UI;
- continuous insertion rendering new placeholders and releasing removed
  canvases;
- ordinary scroll, continuous scroll, and turning retaining existing meaning;
- shared Highlight, Note, Dictionary, Encyclopedia, and degradation paths;
- Server GET/HEAD/Range, ACL, ETag, changed-source refusal, and PAT exclusion;
- identity, watch mode, WebHooks, release artifacts, and unchanged EPUB SSG and
  Server behavior.

Browser E2E uses the local Little Prince PDF when available and compares a real
EPUB reference at desktop, mobile, landscape, keyboard-only, and zoomed sizes.
It verifies Book page, navigation, TOC, settings, selection popup, annotation
export/listing, insights, loading/errors, and every reading mode—not only the
PDF canvas.

Before implementation, `ui-ux-pro-max` validates consistency and degradation
without redesign. After implementation and E2E, `UI/UX Design Review` reviews
the rendered result. Critical and High findings are fixed and affected tests
rerun. Final verification includes relevant complete Python/JavaScript suites,
release asset checks, and `git diff --check`.
