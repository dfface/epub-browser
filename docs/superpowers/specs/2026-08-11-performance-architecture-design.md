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
  -> Reader module         -> ChapterStream -> ChapterSource adapter
  -> Annotation / shelf    -> local storage first; server adapter on demand
```

`ReleasePublisher`, `LibrarySnapshot`, `ChapterStream`, and `StaticDelivery`
are deep modules. Their interfaces hide file layout, version selection,
prefetch state, DOM lifecycle, and HTTP response details. This gives the
performance policies locality and provides leverage across Docker and Pages.

## Delivery phases

1. Add regression harnesses, then implement `LibrarySnapshot` and lazy card
   rendering.
2. Generate chapter fragments and introduce `ChapterStream` behind the current
   reader UI.
3. Publish staging snapshots and replace the hand-written HTTP server with
   Uvicorn/Starlette `StaticDelivery` plus the API module.
4. Split browser scripts and replace the service-worker cache policy.

Each phase preserves existing CLI arguments, Docker startup behavior, stable
URLs, and static output. A later phase may consume artifacts created earlier,
but no phase requires a big-bang migration.

## Verification

- Python `unittest`: snapshot creation, atomic publish/rollback, static cache
  headers, ETag/conditional requests, and Range responses.
- `node --test`: `LibrarySnapshot` consumer behavior and `ChapterStream`
  prefetch, append, trim, cancellation, and scroll-position logic.
- Browser regression: a cold library with 131 books does not eagerly request
  every cover; continuous reading of short and long books prefetches before the
  visible boundary and retains at most five chapters.
- Deployment regression: Docker and Cloudflare Pages serve the same generated
  output; local annotations and bookshelf work on Pages, while server sync
  remains available in Docker.

## Non-goals

- Generate or store cover thumbnails.
- Add Nginx/OpenResty to the Docker image.
- Replace the traditional browser script model with a bundler or native ES
  modules.
- Change public book or chapter URLs.
