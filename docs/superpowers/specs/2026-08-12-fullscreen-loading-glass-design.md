# Unified Loading and Navigation Surface Design

## Goals

Make every full-screen loading state in the library, reader, and chapter views use the same neutral frosted-glass treatment. The loading layer is a system status surface, not a theme surface, so its background must not change with the active reading theme.

Make the library, book, and chapter views use the same navigation hierarchy: a breadcrumb bar for location, followed by a page-specific information surface when one is needed.

## Loading Scope

- Apply the shared treatment to `.loading-overlay` in `book.css`, `library.css`, and `chapter.css`.
- Keep the existing theme-aware spinner accent so it remains legible in each theme.
- Keep non-full-screen loading indicators, such as book grids, shelves, groups, and continuous-scroll indicators, unchanged.

## Navigation Scope

- Use one shared breadcrumb presentation on all three top-level views:
  - Library: `Library`
  - Book: `Library / Book title`
  - Chapter: `Library / Book title / Chapter title`
- Remove `eb-header` from existing book and chapter breadcrumbs so the navigation no longer inherits header-card styling.
- Add a separate library information card below the library breadcrumb. It retains the existing logo, title, library statistics, and login entry.
- Express each breadcrumb as a `<nav aria-label="Breadcrumb">`, and mark the current location with `aria-current="page"`.
- Reuse the existing mobile breadcrumb wrapping behavior; no additional navigation interaction is introduced.

## Loading Visual Behavior

- Use one neutral translucent background: `rgba(15, 23, 42, 0.32)`.
- Blur the content behind the overlay with `backdrop-filter: blur(12px) saturate(1.05)` and its WebKit-prefixed counterpart.
- Preserve the existing full-screen positioning, stacking order, and centered spinner.
- Remove theme-specific full-screen overlay background overrides, including the opaque dark-mode layer.
- For browsers that do not support backdrop filtering, the same translucent background remains as a readable fallback.
- Under `prefers-reduced-motion: reduce`, stop the spinner animation.

## Navigation Visual Behavior

- The breadcrumb is a compact, left-aligned navigation surface with the existing card background, border radius, spacing, and responsive wrapping.
- The current item is plain text rather than a link; ancestor items remain links.
- The library information card remains visually prominent but is separate from navigation. Its current title, logo, statistics, and login affordance are retained.
- Book details and chapter controls remain unchanged below their now-neutral breadcrumb.

## Validation

- Automated style checks assert that all three full-screen overlay declarations carry the shared background, blur, and reduced-motion behavior.
- A visual smoke check covers the library, reader, and chapter overlays in light and dark modes; each must reveal blurred underlying content without a white or opaque full-screen flash.
- Generated library, book, and chapter HTML use semantic navigation landmarks and the correct breadcrumb depth.
- A responsive smoke check at the mobile breakpoint confirms breadcrumb items wrap without horizontal overflow.

## Non-Goals

- No changes to loading timing, DOM structure, spinner markup, or local loading indicators.
- No changes to theme tokens unrelated to full-screen loading.
- No changes to the information displayed by the library header, book detail card, or chapter controls.
