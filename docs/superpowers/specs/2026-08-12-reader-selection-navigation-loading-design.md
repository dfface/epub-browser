# Reader Selection, Navigation, and Loading Design

## Goals

- Let readers copy the exact selected text from the annotation selection menu without creating an annotation.
- Make the library, book, and chapter breadcrumbs share the same visual position and accent treatment.
- Remove full-screen loading overlays and show loading only where content changes.

## Selection Copy

- Add a `Copy` action alongside the existing annotation actions in the selection menu.
- Copy only the selected plain text to the clipboard. Do not add book title, chapter information, or a link.
- On success, show a short confirmation. If clipboard access is unavailable, use the existing fallback mechanism where possible and show a failure notification when it cannot copy.
- Copying must not create, edit, or delete annotations.

## Navigation

- Render every breadcrumb inside the same shared navigation container with identical maximum width, horizontal alignment, and vertical spacing.
- Keep the reader content width independent: chapter content may stay narrower than the breadcrumb bar.
- Restore the former `eb-header` visual signature as a thin, gradient top rule on `.breadcrumb`; do not restore the large header-card layout or centered text.
- Preserve semantic `<nav aria-label="Breadcrumb">` markup and `aria-current="page"` on the final breadcrumb item.

## Loading

- Remove the full-screen `#loadingOverlay` markup and its global overlay behavior from library, book, and chapter pages.
- Keep local loading states where their content changes: book-grid loading, bookshelf/group loading, and continuous-scroll chapter loading.
- Add an in-content loading state for dynamic chapter content work. It is positioned within `.eb-content-container`, has the same neutral frosted-glass visual language, and never blocks unrelated page controls or navigation.
- Browser page navigation does not create an artificial loading overlay.

## Validation

- Automated tests cover the copy action's text-only clipboard payload and confirm it does not invoke annotation persistence.
- Generated pages contain no `#loadingOverlay` and retain their local loading indicators.
- Generated library, book, and chapter pages use the same breadcrumb container and semantic breadcrumb markup.
- Visual checks confirm the gradient breadcrumb rule aligns across the three pages and content-level loading does not cover the full viewport.

## Non-Goals

- No changes to annotation storage schema or existing note/highlight behavior.
- No changes to the text or ordering of existing breadcrumbs beyond visual alignment.
- No loading animation for static page navigation.
