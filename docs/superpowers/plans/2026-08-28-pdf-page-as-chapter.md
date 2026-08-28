# PDF Page-as-Chapter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add PDF support in which every PDF page is a canonical EPUB Browser chapter rendered by PDF.js inside the existing reader.

**Architecture:** Source dispatch and PDF metadata processing are format-specific, while Book and chapter pages remain owned by `EPUBProcessor`. A PDF processor hydrates page-shaped chapter metadata; SSG writes and Server dynamically renders `chapter_N.html`. One small browser adapter paints PDF.js canvas/text layers into page placeholders and relies on existing chapter navigation, continuous loading, settings, annotations, dictionary, reading sessions, insights, OpenAPI, and WebHooks.

**Tech Stack:** Python 3.9+, Starlette, SQLite, pypdf, pypdfium2, PDF.js, vanilla JavaScript, CSS, `unittest`, Node test runner, in-app browser E2E.

**Spec:** `docs/superpowers/specs/2026-08-28-pdf-support-design.md`

## Global Constraints

- Work only in `.worktrees/pdf-support` on branch `codex/pdf-support`.
- PDF page N maps to chapter index N-1 and `chapter_{N-1}.html`.
- PDF uses the exact shared chapter template, settings tabs, annotation selection popup, dictionary dialog, annotation center, reading sessions, insights, and chapter progress.
- The TOC always contains every page; embedded outline titles only mark destination pages.
- `reader.html` is never a PDF UI; it may only redirect old links to `chapter_0.html`.
- Server PDF cache contains immutable derived PDF metadata, never current HTML, UI, i18n, permissions, users, annotations, sessions, or asset URLs.
- SSG contains no Session-only code or `/api/*` dependency.
- PDF.js and all vendor files come from the verified local vendor tree.
- The local Little Prince PDF is used for workspace testing but remains untracked.
- Existing EPUB SSG and Server behavior must remain unchanged.

---

### Task 1: Format classification and capability-aware identity

**Files:**
- Create: `epub_browser/source_format.py`
- Modify: `epub_browser/book_identity.py`
- Modify: `epub_browser/sidecar_identity.py`
- Modify: `epub_browser/ssg.py`
- Modify: `epub_browser/watch.py`
- Modify: `epub_browser/cli.py`
- Modify: `tests/test_book_identity.py`
- Modify: `tests/test_ssg.py`
- Modify: `tests/test_watch.py`

**Interfaces:**
- Produces: `EPUB_FORMAT = "epub"`, `PDF_FORMAT = "pdf"`
- Produces: `source_format(path: Path) -> str`
- Produces: `is_supported_source(path: Path) -> bool`
- Changes: identity inspection reads embedded IDs only for EPUB; PDF always uses a sidecar

- [ ] **Step 1: Add failing PDF discovery and identity tests**

```python
def test_pdf_uses_sidecar_when_embedded_storage_is_requested(self):
    pdf = self.directory / "book.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%%EOF\n")
    identity = resolve_book_identity(pdf, BOOK_ID_STORAGE_EMBEDDED)
    self.assertEqual(read_sidecar(identity.sidecar_path).book_id, identity.book_id)

def test_discovery_accepts_epub_and_pdf_case_insensitively(self):
    (self.sources / "one.epub").write_bytes(EPUB_FIXTURE)
    (self.sources / "two.PDF").write_bytes(PDF_FIXTURE)
    self.assertEqual({path.suffix.lower() for path in builder._discover_sources()}, {".epub", ".pdf"})
```

- [ ] **Step 2: Run focused tests**

Run: `python3 -m unittest tests.test_book_identity tests.test_ssg tests.test_watch -v`

Expected: FAIL because discovery and embedded identity assume EPUB.

- [ ] **Step 3: Add format helpers and narrow identity dispatch**

```python
EPUB_FORMAT = "epub"
PDF_FORMAT = "pdf"

def source_format(path: Path) -> str:
    suffix = Path(path).suffix.lower()
    if suffix == ".epub":
        return EPUB_FORMAT
    if suffix == ".pdf":
        return PDF_FORMAT
    raise ValueError(f"Unsupported book format: {suffix or '<none>'}")

def is_supported_source(path: Path) -> bool:
    return Path(path).suffix.lower() in {".epub", ".pdf"}
```

Rename EPUB-specific sidecar parameters to `source_path`; pass the complete
EPUB/PDF set to orphan detection; skip embedded read/write for PDF and report
one informational message for `--book-id-storage embedded`.

- [ ] **Step 4: Run identity, discovery, CLI, and watch tests**

Run: `python3 -m unittest tests.test_book_identity tests.test_ssg tests.test_watch tests.test_cli -v`

Expected: PASS, including unchanged EPUB embedded identity cases.

- [ ] **Step 5: Commit**

```bash
git add epub_browser/source_format.py epub_browser/book_identity.py epub_browser/sidecar_identity.py epub_browser/ssg.py epub_browser/watch.py epub_browser/cli.py tests
git commit -m "feat: discover PDF sources safely"
```

### Task 2: PDF metadata, outline, and cover extraction

**Files:**
- Create: `epub_browser/pdf_processor.py`
- Modify: `setup.py`
- Create: `tests/test_pdf_processor.py`

**Interfaces:**
- Produces: `PDFOutlineItem(title: str, page_number: int, level: int)`
- Produces: `PDFPageMetadata(page_number: int, width: float, height: float, outline_labels: tuple[str, ...])`
- Produces: `PDFMetadata(title, authors, tags, language, pages, encrypted, has_extractable_text, cover)`
- Produces: `inspect_pdf(source: Path) -> PDFMetadata`
- Produces: `render_pdf_cover(source: Path, destination: Path, max_width=600, max_height=900) -> Optional[Path]`

- [ ] **Step 1: Write deterministic metadata and cover tests**

```python
def test_inspect_pdf_returns_every_page_and_outline_markers(self):
    metadata = inspect_pdf(self.fixture_pdf(pages=3, outline=[("Opening", 2)]))
    self.assertEqual([page.page_number for page in metadata.pages], [1, 2, 3])
    self.assertEqual(metadata.pages[1].outline_labels, ("Opening",))

def test_cover_is_bounded_first_page_png(self):
    target = self.directory / "cover.png"
    self.assertEqual(render_pdf_cover(self.fixture_pdf(pages=1), target), target)
    with Image.open(target) as image:
        self.assertLessEqual(image.width, 600)
        self.assertLessEqual(image.height, 900)
```

- [ ] **Step 2: Run metadata tests**

Run: `python3 -m unittest tests.test_pdf_processor -v`

Expected: FAIL because `epub_browser.pdf_processor` does not exist.

- [ ] **Step 3: Implement bounded inspection and cover rendering**

```python
@dataclass(frozen=True)
class PDFPageMetadata:
    page_number: int
    width: float
    height: float
    outline_labels: tuple[str, ...] = ()

def inspect_pdf(source: Path) -> PDFMetadata:
    if b"%PDF-" not in source.read_bytes()[:1024]:
        raise PDFProcessingError("PDF signature is missing")
    reader = PdfReader(source, strict=False)
    pages = tuple(page_metadata(reader, index) for index in range(len(reader.pages)))
    return metadata_with_outline_markers(reader, pages)
```

Catch parser errors as stable `PDFProcessingError` messages without paths or
tracebacks. Use `pypdfium2` only for a bounded first-page cover. Add pinned
runtime dependencies with project-compatible version ranges.

- [ ] **Step 4: Run PDF processor tests**

Run: `python3 -m unittest tests.test_pdf_processor -v`

Expected: PASS for valid, invalid, encrypted, no-text, outline, dimensions, and cover cases.

- [ ] **Step 5: Commit**

```bash
git add epub_browser/pdf_processor.py setup.py tests/test_pdf_processor.py
git commit -m "feat: inspect PDF metadata and covers"
```

### Task 3: Hydrate the shared Book and chapter templates with PDF pages

**Files:**
- Modify: `epub_browser/processor.py`
- Modify: `epub_browser/assets/i18n.js`
- Modify: `tests/test_generated_reader_surfaces.py`
- Modify: `tests/test_i18n_coverage.py`

**Interfaces:**
- Produces: `EPUBProcessor.from_pdf_metadata(*, book_id: str, metadata: PDFMetadata, cover_path: Optional[str], asset_manifest: PublishedAssets, urls: SiteURLs, deployment_mode: str) -> EPUBProcessor`
- Produces: `create_pdf_chapter_template(chapter_index: int, document_url: str) -> str`
- Produces: TOC records with `chapter_file`, `chapter_index`, `page_label`, and `outline_labels`

- [ ] **Step 1: Add failing shared-template and complete-TOC tests**

```python
def test_pdf_page_uses_exact_shared_chapter_chrome(self):
    processor = self.pdf_processor(pages=3)
    html = processor.create_pdf_chapter_template(1, "document.pdf")
    for required in ('id="eb-content"', 'id="settingsModal"', 'id="appearance-tab"',
                     'id="reading-tab"', 'annotation.js', 'chapter.js'):
        self.assertIn(required, html)
    self.assertIn('data-pdf-page-number="2"', html)
    self.assertNotIn('pdf-selection-menu', html)

def test_pdf_toc_keeps_all_pages_and_marks_outline(self):
    toc = self.pdf_processor(pages=3, outline=[("Opening", 2)])._build_toc_data()
    self.assertEqual([item["chapter_file"] for item in toc],
                     ["chapter_0.html", "chapter_1.html", "chapter_2.html"])
    self.assertEqual(toc[1]["outline_labels"], ["Opening"])
```

- [ ] **Step 2: Run shared reader tests**

Run: `python3 -m unittest tests.test_generated_reader_surfaces tests.test_i18n_coverage -v`

Expected: FAIL because the processor has no PDF hydration path.

- [ ] **Step 3: Implement page-shaped chapters and a narrow PDF content branch**

```python
processor.chapters = [
    {"title": f"Page {page.page_number}", "path": f"chapter_{page.page_number - 1}.html"}
    for page in metadata.pages
]
processor.toc = [
    {"title": chapter["title"], "chapter_index": index,
     "chapter_file": f"chapter_{index}.html", "page_label": str(index + 1),
     "outline_labels": list(metadata.pages[index].outline_labels)}
    for index, chapter in enumerate(processor.chapters)
]
```

Keep `create_chapter_template` as the only reader shell. Add an optional
`pdf_page` descriptor that inserts a scoped placeholder and PDF assets while
retaining every shared element and script. Do not duplicate the annotation
tab or selection popup.

- [ ] **Step 4: Run shared template, i18n, and EPUB regression tests**

Run: `python3 -m unittest tests.test_generated_reader_surfaces tests.test_i18n_coverage -v`

Expected: PASS for PDF and all existing EPUB cases.

- [ ] **Step 5: Commit**

```bash
git add epub_browser/processor.py epub_browser/assets/i18n.js tests/test_generated_reader_surfaces.py tests/test_i18n_coverage.py
git commit -m "feat: model PDF pages as reader chapters"
```

### Task 4: SSG PDF chapter output

**Files:**
- Modify: `epub_browser/ssg.py`
- Modify: `epub_browser/site.py`
- Modify: `epub_browser/models.py`
- Modify: `tests/test_ssg.py`
- Modify: `tests/test_bookshelf_metadata.js`

**Interfaces:**
- Produces: SSG `index.html`, `toc.json`, `document.pdf`, `cover.png`, and every `chapter_N.html`
- Produces: library metadata `format: "pdf"`

- [ ] **Step 1: Add a failing multi-page SSG acceptance test**

```python
def test_pdf_ssg_writes_one_shared_chapter_per_page(self):
    result = self.build_sources([self.fixture_pdf(pages=3)])
    book = result.book_root
    self.assertTrue((book / "document.pdf").is_file())
    self.assertEqual([path.name for path in sorted(book.glob("chapter_*.html"))],
                     ["chapter_0.html", "chapter_1.html", "chapter_2.html"])
    self.assertFalse((book / "reader.html").is_file())
    self.assertNotIn("/api/", (book / "chapter_0.html").read_text(encoding="utf-8"))
```

- [ ] **Step 2: Run SSG tests**

Run: `python3 -m unittest tests.test_ssg -v`

Expected: FAIL because `_convert_one` always instantiates `EPUBProcessor`.

- [ ] **Step 3: Dispatch PDF conversion and write canonical chapter shells**

```python
if prepared.source_format == PDF_FORMAT:
    metadata = inspect_pdf(prepared.source)
    processor = EPUBProcessor.from_pdf_metadata(
        book_id=prepared.book_id,
        metadata=metadata,
        cover_path="cover.png" if cover_path else None,
        asset_manifest=assets,
        urls=self.urls,
        deployment_mode="ssg",
    )
    for index in range(len(metadata.pages)):
        (destination / f"chapter_{index}.html").write_text(
            processor.create_pdf_chapter_template(index, document_url), encoding="utf-8")
```

Copy the source once, render the bounded cover, write the shared Book page and
normalized TOC, and validate every referenced chapter file. Preserve the EPUB
converter factory path exactly.

- [ ] **Step 4: Run SSG and bookshelf metadata tests**

Run: `python3 -m unittest tests.test_ssg tests.test_static_asset_delivery -v`

Run: `node --test tests/test_bookshelf_metadata.js`

Expected: PASS with both EPUB and PDF sources.

- [ ] **Step 5: Commit**

```bash
git add epub_browser/ssg.py epub_browser/site.py epub_browser/models.py tests/test_ssg.py tests/test_bookshelf_metadata.js
git commit -m "feat: generate PDF page chapters in SSG"
```

### Task 5: Server PDF metadata cache and dynamic page routes

**Files:**
- Modify: `epub_browser/state.py`
- Modify: `epub_browser/server_library.py`
- Modify: `epub_browser/server_pages.py`
- Modify: `epub_browser/server.py`
- Modify: `tests/test_state.py`
- Modify: `tests/test_server_library.py`
- Modify: `tests/test_server.py`

**Interfaces:**
- Adds: `BookRecord.source_format: str`
- Produces: `.server-pdf-revision` and `pdf/metadata.json`
- Produces: `ServerPageRenderer.render_pdf_chapter(chapter_index: int) -> str`
- Produces: dynamic `/book/{book_id}/chapter_{chapter_index}.html`

- [ ] **Step 1: Add failing migration, cache, and route tests**

```python
def test_existing_book_rows_migrate_to_epub_format(self):
    store = self.open_pre_pdf_database()
    self.assertEqual(store.active_books()[0].source_format, "epub")

def test_pdf_server_cache_contains_metadata_not_html(self):
    record = self.manager.convert_pdf(self.fixture_pdf(pages=2))
    root = self.public_dir / "book" / record.book_id
    self.assertTrue((root / "pdf" / "metadata.json").is_file())
    self.assertFalse((root / "content").exists())
    self.assertFalse((root / "chapter_0.html").exists())
    self.assertEqual(self.client.get(f"/book/{record.book_id}/chapter_1.html").status_code, 200)
```

- [ ] **Step 2: Run Server state/library tests**

Run: `python3 -m unittest tests.test_state tests.test_server_library tests.test_server -v`

Expected: FAIL because records and Server routing are EPUB-only.

- [ ] **Step 3: Add format migration, independent cache validation, and dynamic rendering**

```python
PDF_OUTPUT_REVISION = "1"
PDF_OUTPUT_REVISION_FILE = ".server-pdf-revision"

def render_pdf_chapter(self, chapter_index: int) -> str:
    metadata = self._pdf_metadata()
    if chapter_index < 0 or chapter_index >= len(metadata.pages):
        raise ServerPageError("Chapter not found")
    return self._pdf_processor(metadata).create_pdf_chapter_template(
        chapter_index, f"/api/books/{self.book_id}/document")
```

Route format dispatch happens only after authentication and visibility checks.
PDF cache validity checks PDF revision, metadata schema, page count, cover, and
fingerprint without touching `SERVER_OUTPUT_REVISION`.

- [ ] **Step 4: Run migration, cache, route, and dynamic-UI tests**

Run: `python3 -m unittest tests.test_state tests.test_server_library tests.test_server -v`

Expected: PASS, including restart-render changes without reconversion and unchanged EPUB cache tests.

- [ ] **Step 5: Commit**

```bash
git add epub_browser/state.py epub_browser/server_library.py epub_browser/server_pages.py epub_browser/server.py tests/test_state.py tests/test_server_library.py tests/test_server.py
git commit -m "feat: render PDF chapters from Server metadata"
```

### Task 6: Authenticated range delivery

**Files:**
- Create: `epub_browser/pdf_delivery.py`
- Modify: `epub_browser/server.py`
- Create: `tests/test_pdf_server.py`

**Interfaces:**
- Produces: `parse_single_range(value: str, size: int) -> Optional[ByteRange]`
- Produces: Session-only `GET|HEAD /api/books/{book_id}/document`

- [ ] **Step 1: Add failing GET, HEAD, Range, ACL, and changed-source tests**

```python
def test_document_supports_single_range(self):
    response = self.client.get(self.url, headers={"Range": "bytes=10-19"})
    self.assertEqual(response.status_code, 206)
    self.assertEqual(response.headers["content-range"], f"bytes 10-19/{self.size}")
    self.assertEqual(len(response.content), 10)

def test_document_hides_inaccessible_and_changed_sources(self):
    self.assertEqual(self.other_user.get(self.url).status_code, 404)
    self.source.write_bytes(self.source.read_bytes() + b"changed")
    self.assertEqual(self.owner.get(self.url).status_code, 409)
```

- [ ] **Step 2: Run delivery tests**

Run: `python3 -m unittest tests.test_pdf_server -v`

Expected: FAIL because the document route is absent.

- [ ] **Step 3: Implement safe bounded delivery**

```python
@dataclass(frozen=True)
class ByteRange:
    start: int
    end: int

def parse_single_range(value: str, size: int) -> Optional[ByteRange]:
    match = re.fullmatch(r"bytes=(\d*)-(\d*)", value.strip())
    if not match:
        raise RangeNotSatisfiable(size)
    return normalize_range(match.group(1), match.group(2), size)
```

Check Session, visibility, format, current stat/fingerprint, GET/HEAD, one
range, conditional ETag, sanitized inline filename, `Accept-Ranges`, private
cache policy, and `nosniff`. Never expose the source path or mount under
`/api/v1`.

- [ ] **Step 4: Run PDF delivery and Server security tests**

Run: `python3 -m unittest tests.test_pdf_server tests.test_server -v`

Expected: PASS for full, suffix, open-ended, invalid, and unsatisfiable ranges.

- [ ] **Step 5: Commit**

```bash
git add epub_browser/pdf_delivery.py epub_browser/server.py tests/test_pdf_server.py
git commit -m "feat: deliver authorized PDF byte ranges"
```

### Task 7: PDF.js page rendering lifecycle

**Files:**
- Create: `epub_browser/assets/pdf-chapter.js`
- Create: `epub_browser/assets/pdf-chapter.css`
- Modify: `epub_browser/assets/chapter.js`
- Modify: `epub_browser/asset_publisher.py`
- Create: `tests/test_pdf_chapter.js`
- Modify: `tests/test_generated_reader_surfaces.py`

**Interfaces:**
- Consumes: `window.EpubPDFConfig` with document URL and verified PDF.js module/worker URLs
- Produces: `window.EpubPDFChapter.renderWithin(root)` and `disposeWithin(root)`
- Produces: format-neutral DOM events `epub-browser:chapter-content-added` and `epub-browser:chapter-content-removed`

- [ ] **Step 1: Write failing adapter lifecycle tests**

```javascript
test('renders initial and continuously inserted page placeholders once', async () => {
  const harness = createHarness({pages: 3});
  await harness.adapter.renderWithin(harness.document);
  harness.insertChapter(1);
  await harness.flush();
  assert.deepEqual(harness.renderedPages, [1, 2]);
});

test('disposes render jobs and canvases when a chapter leaves the window', async () => {
  const harness = createHarness({pages: 2});
  await harness.adapter.renderWithin(harness.document);
  harness.removeChapter(0);
  assert.equal(harness.cancelCount, 1);
});
```

- [ ] **Step 2: Run adapter tests**

Run: `node --test tests/test_pdf_chapter.js`

Expected: FAIL because the adapter does not exist.

- [ ] **Step 3: Implement scoped rendering and narrow lifecycle events**

```javascript
async function renderWithin(rootNode) {
  const nodes = rootNode.querySelectorAll('[data-pdf-page-number]:not([data-pdf-rendered])');
  for (const node of nodes) {
    node.setAttribute('data-pdf-rendered', 'pending');
    await renderPage(node, Number(node.dataset.pdfPageNumber));
  }
}

window.addEventListener('epub-browser:chapter-content-added', event => {
  renderWithin(event.detail.root);
});
window.addEventListener('epub-browser:chapter-content-removed', event => {
  disposeWithin(event.detail.root);
});
```

Use PDF.js canvas and text-layer APIs, IntersectionObserver-based lazy paint,
device-pixel-ratio backing size, bounded retained pages, render cancellation,
ResizeObserver rerender, client-only password callback, and scoped CSS based on
existing variables. Shared `chapter.js` only dispatches lifecycle events where
it inserts and removes chapter containers.

- [ ] **Step 4: Run adapter and shared reader JavaScript tests**

Run: `node --test tests/test_pdf_chapter.js tests/test_chapter_*.js tests/test_continuous_*.js`

Expected: PASS, with no changes to EPUB navigation semantics.

- [ ] **Step 5: Commit**

```bash
git add epub_browser/assets/pdf-chapter.js epub_browser/assets/pdf-chapter.css epub_browser/assets/chapter.js epub_browser/asset_publisher.py tests/test_pdf_chapter.js tests/test_generated_reader_surfaces.py
git commit -m "feat: render PDF pages inside reader chapters"
```

### Task 8: PDF actions inside the shared reader chrome

**Files:**
- Modify: `epub_browser/processor.py`
- Modify: `epub_browser/assets/pdf-chapter.js`
- Modify: `epub_browser/assets/pdf-chapter.css`
- Modify: `epub_browser/assets/i18n.js`
- Modify: `tests/test_pdf_chapter.js`
- Modify: `tests/test_generated_reader_surfaces.py`

**Interfaces:**
- Produces: PDF search drawer using existing reader drawer classes
- Produces: fit-width, fit-page, zoom, rotation, print, and download actions using existing `control-btn` patterns
- Stores: PDF-only rotation and fit preferences without duplicating chapter or reading-mode progress

- [ ] **Step 1: Add failing action and search tests**

```javascript
test('search resolves results to canonical PDF chapter URLs', async () => {
  const harness = createHarness({pageTexts: ['alpha', 'beta alpha']});
  const results = await harness.adapter.search('alpha');
  assert.deepEqual(results.map(item => item.href), ['chapter_0.html', 'chapter_1.html']);
});

test('rotation and fit preferences do not mutate reading mode keys', async () => {
  const harness = createHarness({pages: 1});
  await harness.rotate();
  await harness.fitWidth();
  assert.equal(harness.storage.getItem('turning'), null);
  assert.equal(harness.storage.getItem('continuousScroll'), null);
});
```

- [ ] **Step 2: Run PDF action tests**

Run: `node --test tests/test_pdf_chapter.js`

Expected: FAIL because search and PDF actions are absent.

- [ ] **Step 3: Add narrow controls without changing shared settings structure**

Insert PDF-only controls through optional slots already owned by the chapter
template. Search each page with PDF.js text extraction and link results to
canonical `chapter_N.html`; cancel stale searches. Implement bounded zoom,
fit-width, fit-page, normalized 0/90/180/270 rotation, iframe-based print, and
authorized document download. Use existing drawers, buttons, focus restoration,
Escape handling, i18n, touch sizes, and reduced motion.

- [ ] **Step 4: Run action, i18n, and generated-surface tests**

Run: `node --test tests/test_pdf_chapter.js`

Run: `python3 -m unittest tests.test_generated_reader_surfaces tests.test_i18n_coverage -v`

Expected: PASS; Appearance/Reading/Annotations tabs are unchanged and PDF
actions do not appear on EPUB chapters.

- [ ] **Step 5: Commit**

```bash
git add epub_browser/processor.py epub_browser/assets/pdf-chapter.js epub_browser/assets/pdf-chapter.css epub_browser/assets/i18n.js tests/test_pdf_chapter.js tests/test_generated_reader_surfaces.py
git commit -m "feat: add PDF chapter actions"
```

### Task 9: Shared annotations, lookup actions, and degradation

**Files:**
- Modify: `epub_browser/assets/pdf-chapter.js`
- Modify: `epub_browser/assets/annotation.js`
- Modify: `epub_browser/assets/dictionary.js`
- Modify: `epub_browser/processor.py`
- Create: `tests/test_pdf_annotation_adapter.js`
- Modify: `tests/test_annotation.js`
- Modify: `tests/test_generated_reader_surfaces.py`

**Interfaces:**
- Consumes: existing `AnnotationModule.init({bookHash, chapterIndex})` and refresh APIs
- Consumes: existing `EpubBrowserDictionary.open(kind, text, anchor)`
- Produces: stable page text-layer DOM under the normal chapter section

- [ ] **Step 1: Add failing exact-component and same-page selection tests**

```javascript
test('PDF selection uses the shared annotation popup and chapter index', async () => {
  const harness = pdfAnnotationHarness({pageNumber: 3});
  await harness.renderTextLayer('The little prince');
  harness.select('little prince');
  assert.equal(harness.document.querySelectorAll('.annotation-selection-menu').length, 1);
  assert.equal(harness.document.querySelectorAll('.pdf-selection-menu').length, 0);
  await harness.click('dictionary');
  assert.deepEqual(harness.dictionaryCall.kind, 'dictionary');
  assert.equal(harness.annotationContext.chapterIndex, 2);
});
```

- [ ] **Step 2: Run annotation adapter tests**

Run: `node --test tests/test_pdf_annotation_adapter.js tests/test_annotation.js`

Expected: FAIL until the PDF text layer is registered with the shared annotation module.

- [ ] **Step 3: Register rendered text layers with existing components**

After text-layer completion, dispatch one page-ready event containing the
normal chapter root and call the existing annotation refresh path. Add only
format-neutral readiness support to `annotation.js`; do not add a second popup,
settings tab, color list, exporter, or API. Make cross-page/no-text cases return
a localized capability message before Highlight, Note, Dictionary, or
Encyclopedia executes.

- [ ] **Step 4: Run annotation, dictionary, and generated-page tests**

Run: `node --test tests/test_pdf_annotation_adapter.js tests/test_annotation.js`

Run: `python3 -m unittest tests.test_generated_reader_surfaces tests.test_server -v`

Expected: PASS and the generated PDF chapter contains the exact shared scripts and controls.

- [ ] **Step 5: Commit**

```bash
git add epub_browser/assets/pdf-chapter.js epub_browser/assets/annotation.js epub_browser/assets/dictionary.js epub_browser/processor.py tests
git commit -m "feat: reuse reader annotations for PDF pages"
```

### Task 10: Public API, OpenAPI, and WebHook format compatibility

**Files:**
- Modify: `epub_browser/public_api.py`
- Modify: `epub_browser/state.py`
- Modify: `epub_browser/server_library.py`
- Modify: `tests/test_public_api.py`
- Modify: `tests/test_webhooks.py`

**Interfaces:**
- Produces: book payload field `format`
- Produces: PDF chapter detail `{index, title, format: "pdf", page_number, content_type: "application/pdf-page", content_html: null, text: <extracted-or-empty>}`
- Preserves: existing progress, reading-session, and annotation chapter-index contracts

- [ ] **Step 1: Add failing PDF contract tests and EPUB snapshots**

```python
def test_pdf_chapters_are_page_chapters_in_public_api(self):
    response = self.pat.get(f"/api/v1/books/{self.pdf_id}/chapters/1")
    self.assertEqual(response.status_code, 200)
    self.assertEqual(response.json()["chapter"], {
        "index": 1, "title": "Page 2", "format": "pdf", "page_number": 2,
        "content_type": "application/pdf-page", "content_html": None, "text": ""
    })

def test_raw_pdf_document_is_not_a_pat_operation(self):
    self.assertNotIn("/api/books/{book_id}/document", self.openapi["paths"])
```

- [ ] **Step 2: Run API, OpenAPI, and WebHook tests**

Run: `python3 -m unittest tests.test_public_api tests.test_webhooks -v`

Expected: FAIL because books lack format and PDF chapter metadata.

- [ ] **Step 3: Add additive format fields and PDF chapter representation**

Return `format` from book list/detail and WebHook book/conversion payloads. Let
chapter list/detail dispatch through `ServerPageRenderer` format metadata;
return the exact PDF representation above. Keep EPUB payload fields and
annotation/progress inputs byte-for-byte compatible. Document the new enum and
PDF chapter fields in OpenAPI 3.1; keep raw bytes Session-only.

- [ ] **Step 4: Run full contract suites**

Run: `python3 -m unittest tests.test_public_api tests.test_webhooks -v`

Expected: PASS for existing EPUB fixtures and new PDF fixtures.

- [ ] **Step 5: Commit**

```bash
git add epub_browser/public_api.py epub_browser/state.py epub_browser/server_library.py tests/test_public_api.py tests/test_webhooks.py
git commit -m "feat: expose PDF page chapters in public contracts"
```

### Task 11: Documentation and repository example policy

**Files:**
- Modify: `README.md`
- Modify: `README.zh-CN.md`
- Modify: `.gitignore`
- Create or modify: generated PDF fixtures under `tests/fixtures/` only when redistribution is clear
- Create: `tests/test_readme_docs.py`

**Interfaces:**
- Documents: PDF support, page-as-chapter URLs, degradation, identity behavior, and build asset prerequisite

- [ ] **Step 1: Add documentation assertions**

```python
def test_readmes_document_pdf_chapter_mapping(self):
    for path in (Path("README.md"), Path("README.zh-CN.md")):
        text = path.read_text(encoding="utf-8")
        self.assertIn("chapter_0.html", text)
        self.assertIn("PDF", text)
```

- [ ] **Step 2: Run documentation tests**

Run: `python3 -m unittest tests.test_readme_docs -v`

Expected: FAIL until both readmes describe PDF support.

- [ ] **Step 3: Document capabilities and keep the local PDF untracked**

Document SSG/Server matrix, `--book-id-storage embedded` fallback, page-as-
chapter semantics, no-text degradation, PDF.js hydration command, and Server
range security. Add a narrow ignore entry for the provided local PDF only if
the repository does not intend to distribute it; keep generated licensed test
fixtures small and deterministic.

- [ ] **Step 4: Run documentation and identity tests**

Run: `python3 -m unittest tests.test_readme_docs tests.test_book_identity -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add README.md README.zh-CN.md .gitignore tests
git commit -m "docs: explain PDF page chapter support"
```

### Task 12: End-to-end UI/UX validation and full regression gate

**Files:**
- Modify only files required by verified Critical/High review findings
- Update matching automated tests with every fix

**Interfaces:**
- Consumes: local `examples/TheLittlePrince.pdf`
- Produces: verified SSG and Server reading experiences consistent with the EPUB reference

- [ ] **Step 1: Build fresh SSG and Server outputs from the worktree**

Run: `python3 tools/sync_vendor_assets.py verify`

Run the project SSG command with the local PDF and one EPUB fixture, then run
the Server command with an isolated temporary state directory. Confirm the PDF
Book page has a first-page cover and 64 canonical page chapters.

- [ ] **Step 2: Execute browser E2E against PDF and EPUB reference pages**

Verify desktop, 375px portrait, landscape phone, keyboard-only, 200% zoom, and
400% zoom for Book page, nav, complete page TOC, outline markers, settings
Appearance/Reading/Annotations tabs, exact selection popup, Highlight, Note,
Dictionary, Encyclopedia, annotation center, Reading Insights, ordinary
scroll, continuous scroll, turning, previous/next, progress restore, search,
rotation, print, download, loading, encrypted, no-text, and error states.

- [ ] **Step 3: Run `UI/UX Design Review` and fix Critical/High findings**

Use the actual rendered SSG and Server pages. For each fix, add or update the
smallest automated reproduction before changing code, rerun it, and repeat the
affected browser flow. Do not redesign the existing EPUB interface.

- [ ] **Step 4: Run complete verification**

Run: `python3 -m unittest discover -s tests -p 'test_*.py'`

Run: `node --test tests/test_*.js`

Run: `python3 tools/sync_vendor_assets.py verify`

Run: `python3 -m build`

Run: `git diff --check`

Expected: every command PASS with no warnings attributed to the change.

- [ ] **Step 5: Commit final review fixes**

```bash
git add epub_browser tests README.md README.zh-CN.md
git commit -m "fix: complete PDF reader UX review"
```
