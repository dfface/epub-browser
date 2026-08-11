# Library Information and Breadcrumb Density Design

## Goal

Reduce the library information card's visual weight while restoring a consistent, comfortably sized breadcrumb surface on library, book, and chapter pages.

## Library Information Card

- Remove the gradient top rule from `.library-info`.
- Reduce vertical padding from 40px to 28px and bottom separation from 40px to 28px.
- Reduce the library logo from 60px to 44px and the title from 2.5rem to 2rem.
- Retain the title, book count, tag count, and login entry.

## Breadcrumbs

- Keep the gradient top rule on `.breadcrumb`.
- Give all three pages the same 28px vertical and 24px horizontal padding.
- Keep shared container width, horizontal alignment, and top spacing unchanged.
- Preserve semantic breadcrumb markup and existing responsive wrapping.

## Validation

- Generated library, book, and chapter pages retain their breadcrumb containers.
- CSS confirms the library card has no pseudo-element top rule while each breadcrumb retains one.
- A generated example site visually shows a lighter library card and equal breadcrumb height across pages.
