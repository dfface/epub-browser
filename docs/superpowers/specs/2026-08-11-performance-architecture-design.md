# EPUB Browser performance architecture design

## Goal

Make Docker and static Pages deployments faster without generating thumbnails,
while preserving stable URLs, CLI behavior, Kindle/Silk support, offline reading,
local annotations, and the current book/shelf features.

## Scope and acceptance criteria

### Library startup

- The library must stop forcing a fresh `book-metadata.json` request with a
  timestamp query parameter.
- A `LibrarySnapshot` module must publish a short manifest plus a versioned,
  immutable library snapshot.
- The library UI must render cards incrementally and each cover must use
  `loading="lazy"` and `decoding="async"`.
- No cover thumbnails will be generated. The UI continues to use EPUB cover
  files, only when they approach the viewport.
- Search, tags, sortable order, local bookshelf data, and existing library URLs
  remain available.

### Continuous reading

- A `ChapterStream` module owns continuous-reading state. Its interface is
  limited to starting the stream, prefetching, appending, trimming, and
  reporting the current chapter.
- A `ChapterSource` adapter supplies chapter data. Production data comes from
  generated chapter fragments; tests use an in-memory adapter.
- The reader begins a next-chapter prefetch after roughly 60--70% progress,
  instead of beginning the request only within 300px of the end.
- At the chapter boundary, the reader inserts prefetched content rather than
  parsing a complete reading page in the foreground.
- The stream retains no more than the current chapter, two preceding chapters,
  and two following chapters. It preserves scroll position and the stable
  chapter URL while trimming distant DOM content.
- Stale prefetches are cancelled when reading direction changes.

### Reader experience and extensible UI profiles

- Presentation is a build-time `UIProfile` boundary, separate from book data,
  release publication, URLs, reader state, annotations, shelves, and sync.
  A profile owns page templates, entry assets, visual tokens, and optional
  presentation-only interaction hooks; it must not own persistence or chapter
  delivery.
- The CLI accepts `--ui=<profile-id>` and defaults to the new Kindle-inspired
  `reader` profile, displayed to users as **Quiet**. `--ui=legacy`, displayed
  as **Classic**, deliberately produces the current interface for conservative
  rollout and Kindle/Silk compatibility. The profile registry is open for
  future distinct designs (including deliberately expressive ones) without
  changing the conversion pipeline.
- Every installed profile emits the same stable chapter URLs and consumes the
  same immutable release data and chapter fragments. Selection is explicit at
  generation time, not a runtime server switch or a separate deployment.
- The default `reader` profile is an MPA-first progressive enhancement: every
  chapter URL opens as a complete page; capable browsers retain a persistent
  Reader App Shell and progressively navigate same-book previous/next and
  table-of-contents links. Native navigation remains the fallback for
  unsupported browsers, failures, cross-book links, and new-tab requests.
- The `reader` visual language is Kindle-inspired and content-first: paper/ink
  light and dark tokens, no remote font dependency, no glass/blur/parallax,
  and only restrained opacity/transform transitions. `prefers-reduced-motion`
  disables the transition.
- The reading measure, line height, responsive gutters, semantic landmarks,
  focus transfer after progressive navigation, keyboard controls, and 44px
  touch targets are part of the `reader` profile contract. Controls may recede
  during reading but remain immediately recoverable.
- Loading feedback is announced politely and appears only after a short delay,
  so fast navigation neither flashes a skeleton nor shifts the reading layout.

### Internationalization

- Internationalization is a shared runtime service, independent from
  `UIProfile`. A profile supplies visual treatment and `data-i18n` keys; the
  locale service supplies text, plural/formatting rules, document language, and
  accessible labels. This lets Quiet, Classic, and future profiles use the same
  languages without duplicating their catalogs.
- First-class locales are `zh-CN` and `en`. The initial document is rendered in
  `zh-CN` to preserve the current Chinese-first experience. When JavaScript is
  available, selection is: saved user preference, compatible browser language,
  then `zh-CN`. Users can switch language in the UI, and the preference is
  retained locally.
- Selection happens wholly in the browser and never changes a chapter URL,
  release, annotation, bookshelf, or reading-progress key. Docker and Pages
  serve exactly the same static output; there is no language-specific site tree
  or server content negotiation.
- All product UI strings, plural forms, date/number formatting, document
  `lang`, control labels, notifications, and ARIA text use stable message keys.
  EPUB titles and source chapter content are never machine-translated. Missing
  translations fall back to `en` and are surfaced by development tests.
- Locale catalogs are local, versioned release assets. The initial Chinese
  document remains usable without JavaScript; another catalog is fetched only
  when required and then cached with the release. No remote translation or font
  service is introduced.

### Static delivery and release publication

- Runtime Python support changes from `>=3.6` to `>=3.9`.
- Docker delivery uses `uvicorn` with `starlette`; no Nginx/OpenResty is added
  to the image.
- A `StaticDelivery` adapter owns static paths, MIME types, ETag,
  Last-Modified, Range responses, and cache-control. Annotation and sync routes
  remain in a small API module.
- EPUB conversion writes a staging release snapshot. On success, it atomically
  publishes the snapshot while preserving stable URLs such as
  `/book/<hash>/chapter_4.html`.
- One previous release remains available for rollback and is cleaned up later.
- Docker and Pages both consume the same generated output. Pages remains a
  pure static deployment.

### JavaScript and offline behavior

- The browser stays compatible with Kindle/Silk and uses no build step or native
  ES module requirement.
- Traditional script modules have narrow interfaces: shared runtime, library,
  reader, chapter stream, annotations, bookshelf, and sync.
- Static Pages continues to provide IndexedDB annotations and the local
  bookshelf. Server annotation and shelf-sync adapters load only when their
  server capability is available.
- The service worker uses snapshot-versioned caches. It is network-first for
  the release manifest, cache-first for immutable release resources, and
  removes prior snapshot caches after activation.

## Architecture

```text
EPUB watcher
  -> ReleasePublisher
      -> staging snapshot
      -> atomic stable-path publish
          -> manifest + LibrarySnapshot
          -> full chapter pages + chapter fragments

Uvicorn / Starlette
  -> StaticDelivery adapter -> immutable release tree
  -> API module            -> annotations and sync

Browser shared runtime
  -> Library module        -> manifest, LibrarySnapshot, lazy cards
  -> UIProfile entrypoint  -> Reader App Shell -> ReaderNavigation / ChapterStream
                                             -> ChapterSource adapter
  -> I18n module           -> locale catalog, browser/local preference, formatters
  -> Annotation / shelf    -> local storage first; server adapter on demand
```

`ReleasePublisher`, `LibrarySnapshot`, `UIProfile`, `I18n`,
`ReaderNavigation`, `ChapterStream`, and `StaticDelivery` are deep modules.
Their interfaces hide file layout, version selection, presentation and locale
choice, navigation/prefetch state, DOM lifecycle, and HTTP response details.
This gives the performance policies locality and provides leverage across
Docker and Pages.

## Delivery phases

1. Add regression harnesses, then implement `LibrarySnapshot` and lazy card
   rendering.
2. Generate chapter fragments and introduce the default Reader App Shell,
   `ReaderNavigation`, and `ChapterStream`; retain the existing interface as
   the explicit `legacy` UI profile.
3. Publish staging snapshots and replace the hand-written HTTP server with
   Uvicorn/Starlette `StaticDelivery` plus the API module.
4. Split browser scripts, add the shared locale service, and replace the
   service-worker cache policy.

Each phase preserves existing CLI arguments, Docker startup behavior, stable
URLs, and static output. `--ui=reader` becomes the default while
`--ui=legacy` preserves the old generated experience. A later phase may consume
artifacts created earlier, but no phase requires a big-bang migration.

## Verification

- Python `unittest`: snapshot creation, atomic publish/rollback, static cache
  headers, ETag/conditional requests, and Range responses.
- `node --test`: `LibrarySnapshot` consumer behavior and `ChapterStream`
  prefetch, append, trim, cancellation, scroll-position logic, plus
  `ReaderNavigation` history, native fallback, focus behavior, and catalog
  selection/fallback and message-key coverage for `zh-CN` and `en`.
- Browser regression: a cold library with 131 books does not eagerly request
  every cover; continuous reading of short and long books prefetches before the
  visible boundary and retains at most five chapters; `--ui=legacy` still
  renders the current reader markup and `--ui=reader` provides the immersive
  App Shell without breaking direct chapter loads. Language switching changes
  all product controls and accessibility text without changing the current
  chapter URL or local reading state.
- Deployment regression: Docker and Cloudflare Pages serve the same generated
  output; local annotations and bookshelf work on Pages, while server sync
  remains available in Docker.

## Non-goals

- Generate or store cover thumbnails.
- Add Nginx/OpenResty to the Docker image.
- Replace the traditional browser script model with a bundler or native ES
  modules.
- Change public book or chapter URLs.
