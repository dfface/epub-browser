# EPUB Browser

EPUB Browser turns EPUB and PDF books into one locally served reading library.
It has two deployment modes—SSG and Server—but one reader interface. The
reading experience must remain responsive on long EPUBs, large PDFs, and large
local libraries.

## Product constraints

- EPUB chapters and PDF pages share the Library, Book, TOC, Chapter, settings,
  annotation, search, progress, and reading-insight surfaces. PDF is not a
  separate viewer shell.
- A PDF page is a reader chapter: visible page 1 maps to `chapter_0.html`.
  Embedded PDF outlines annotate the page-number TOC; they never replace it.
- SSG contains no accounts, SQLite, `/api/*`, AI controls, or protected data.
  Server-only features must be authenticated and permission checked.
- Server caches format-derived content only. EPUB `content/` and PDF `pdf/`
  cache schemas evolve independently; UI and asset changes do not force book
  reconversion.
- PDF.js and every browser dependency are hydrated at build time from the
  locked vendor manifest. Reading must not require a runtime CDN.
- Runtime-created interface elements must use `data-i18n*` bindings or a locale
  change subscription so switching language never requires a refresh.

## Language

**Book source**:
An input `.epub` or `.pdf` file discovered directly or recursively from a
configured source directory.
_Avoid_: EPUB input when the statement also applies to PDF

**Reader chapter**:
The unit addressed by `chapter_<n>.html`. It is a logical EPUB chapter for an
EPUB book and exactly one page for a PDF book.
_Avoid_: PDF page shell, fake EPUB chapter

**Reading window**:
The bounded set of fully rendered reader chapters around the reader's current
location in continuous scroll mode. Chapters outside the reading window retain
stable geometry until needed again.
_Avoid_: loaded chapter list, infinite scroll cache

**Reading stage**:
The bounded chapter canvas that owns PDF positioning, zoom overflow, loading
state, page gaps, and theme background. Oversized PDF content scrolls inside
the stage instead of escaping into the page layout.
_Avoid_: PDF container when referring to the whole reader viewport

**Content cache**:
Replaceable, format-derived Server data used to render pages. EPUB uses
`content/`; PDF uses `pdf/document.pdf` plus `pdf/metadata.json`. It never owns
accounts, annotations, permissions, translated UI copy, or compiled asset URLs.
_Avoid_: database, public output directory

**Book cover**:
The representative image of a book shown consistently in Library, bookshelf,
and Book surfaces. PDF covers are derived from the first page when possible.
_Avoid_: thumbnail, preview image

**Deployment mode**:
Either `ssg`, which emits a self-contained static snapshot, or `server`, which
dynamically serves authenticated pages and synchronized data.
_Avoid_: EPUB mode; EPUB and PDF are source formats, not deployment modes
