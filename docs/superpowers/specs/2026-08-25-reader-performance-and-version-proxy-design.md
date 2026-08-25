# Reader Performance and Version Proxy Design

## Goal

Remove the reader page's avoidable first-load work and layout instability,
make web manifests readable without a session, and replace the browser's
blocked cross-origin GitHub version check with a narrow same-origin endpoint.

## Constraints

- Preserve the SSG/Server boundary: the version proxy, authenticated AI data,
  and feature loaders are Server-only; SSG must not depend on `/api/*`.
- Keep all non-manifest deployed assets protected in Server mode unless they
  are already required by the setup/login experience.
- Do not raise `SERVER_OUTPUT_REVISION` for UI, JavaScript, CSS, or proxy
  changes. Raising it is required only for the EPUB image-dimension cache
  change.
- The version endpoint must never proxy a client-provided URL.

## Version check

The Server application exposes `GET /api/version`. It retrieves only
`https://api.github.com/repos/dfface/epub-browser/releases/latest`, with a
bounded timeout and a six-hour in-process cache. Concurrent cache misses share
one request. It returns only the release fields needed by the existing client
(`tag_name`, `html_url`, `draft`, and `prerelease`) and reports upstream
unavailability as a same-origin error response without leaking upstream body
contents.

Server-rendered footers point `data-release-api` to `/api/version`; SSG
footers retain the GitHub URL because an SSG deployment has no proxy. The
browser keeps its local six-hour cache. This avoids changing the restrictive
reader CSP and avoids granting browser pages general cross-origin access.

## Public web manifests

Web manifest JSON files in the deployed `assets/` directory are a distinct
public-resource class. `manifest.json` and every configured locale manifest
are served from the generated public directory before authentication. The
existing package-local setup/login CSS and JavaScript allowlist remains
separate, so no deployed file is accidentally read from the Python package.
All other application assets remain session-protected.

## Reader startup and feature loading

The default chapter navigation no longer fetches a prior AI result or injects
an AI chapter guide into the beginning of the reader content. A reader asks for
AI explicitly; an `?ai_result=` deep link remains an explicit request and
loads its result. This preserves the initial reading layout and keeps an
asynchronously added guide from becoming LCP or shifting all text below it.

Mermaid and KaTeX are loaded once, only when a rendered AI response contains a
diagram or mathematical block. Their styles load together with the first use.
Reader chrome supplies the immutable URLs through the already-rendered asset
manifest, so dynamic loaders never need unhashed `/assets/*` paths. AI chat,
annotation/lightbox/highlighting, bookshelf/sorting, and their styles follow
the same first-use loading pattern; small event-binding code may remain in the
initial reader bundle.

The AI-reading hub caches its in-flight and resolved chapter-indicator request
per book. The book chapter drawer and the chapter TOC subscribe to that one
request rather than issue identical result-list requests.

## Images, fonts, and scrolling

The header uses a small WebP logo suited to its rendered size. Font Awesome is
replaced by a reader-specific subset with `font-display: swap`.

During EPUB conversion, images without numeric dimensions are enriched with
their intrinsic width and height when their packaged resource can be read.
Those attributes become part of the cleaned chapter content cache, so the
Server content revision and cache validation are updated. Unknown/external
images retain their existing markup.

Chapter scroll handlers are scheduled through one `requestAnimationFrame`
cycle that completes geometry reads before class/style writes. This eliminates
the reader's avoidable layout-thrashing path without changing user-facing
scroll behavior.

## Testing and verification

Tests cover proxy URL scope, caching/error behavior, anonymous manifest access,
protected non-manifest assets, Server/SSG footer URLs, explicit-only AI result
loading, single AI indicator request per book, lazy feature loading, image
dimension enrichment, and scroll scheduling. Every behavior change follows a
red-green test cycle. Final verification includes focused unit tests, relevant
Server and SSG suites, JavaScript tests, `git diff --check`, and a clean-browser
Lighthouse rerun.
