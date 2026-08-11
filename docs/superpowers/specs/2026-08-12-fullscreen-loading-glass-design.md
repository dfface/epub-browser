# Unified Full-Screen Loading Glass Design

## Goal

Make every full-screen loading state in the library, reader, and chapter views use the same neutral frosted-glass treatment. The loading layer is a system status surface, not a theme surface, so its background must not change with the active reading theme.

## Scope

- Apply the shared treatment to `.loading-overlay` in `book.css`, `library.css`, and `chapter.css`.
- Keep the existing theme-aware spinner accent so it remains legible in each theme.
- Keep non-full-screen loading indicators, such as book grids, shelves, groups, and continuous-scroll indicators, unchanged.

## Visual Behavior

- Use one neutral translucent background: `rgba(15, 23, 42, 0.32)`.
- Blur the content behind the overlay with `backdrop-filter: blur(12px) saturate(1.05)` and its WebKit-prefixed counterpart.
- Preserve the existing full-screen positioning, stacking order, and centered spinner.
- Remove theme-specific full-screen overlay background overrides, including the opaque dark-mode layer.
- For browsers that do not support backdrop filtering, the same translucent background remains as a readable fallback.
- Under `prefers-reduced-motion: reduce`, stop the spinner animation.

## Validation

- Automated style checks assert that all three full-screen overlay declarations carry the shared background, blur, and reduced-motion behavior.
- A visual smoke check covers the library, reader, and chapter overlays in light and dark modes; each must reveal blurred underlying content without a white or opaque full-screen flash.

## Non-Goals

- No changes to loading timing, DOM structure, spinner markup, or local loading indicators.
- No changes to theme tokens unrelated to full-screen loading.
