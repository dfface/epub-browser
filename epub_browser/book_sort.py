"""Sort choices shared by book management and both library interfaces."""

from html import escape

from .i18n_bundles import get_bundle


BOOK_SORT_LABEL = "library.sort.label"
BOOK_SORT_OPTIONS = {
    "title_asc": "library.sort.titleAsc",
    "title_desc": "library.sort.titleDesc",
    "created_desc": "library.sort.createdDesc",
    "updated_desc": "library.sort.updatedDesc",
}
LIBRARY_SORT_OPTIONS = {
    "manual": "library.sort.manual",
    "shelf_first": "library.sort.shelfFirst",
    "shelf_order": "library.sort.shelfOrder",
    "pdf_first": "library.sort.pdfFirst",
    **BOOK_SORT_OPTIONS,
}


def library_sort(value):
    return value if value in LIBRARY_SORT_OPTIONS else "manual"


def book_sort_options(options, selected, locale="en"):
    bundle = get_bundle(locale)
    english = get_bundle("en")
    return "".join(
        f'<option value="{value}" data-i18n="{key}"'
        f'{" selected" if value == selected else ""}>{escape(bundle.get(key) or english[key])}</option>'
        for value, key in options.items()
    )


def sort_catalog(books, sort, manual_order=(), shelf_added=None, shelf_order=None):
    """Order visible book records before applying any page boundary."""
    ordered = list(books)  # The visible-books query supplies the ID tie-break order.
    if sort == "manual":
        if manual_order:
            ranks = {book_id: index for index, book_id in enumerate(manual_order)}
            ordered.sort(key=lambda book: ranks.get(book.book_id, -1))
        return ordered
    if sort == "pdf_first":
        # Group PDFs ahead of EPUBs, newest first inside each group. Three
        # stable passes keep the title collation as the final tie-break.
        ordered.sort(key=lambda book: book.title.casefold())
        ordered.sort(key=lambda book: book.created_at, reverse=True)
        ordered.sort(
            key=lambda book: 0
            if getattr(book, "source_format", "epub") == "pdf"
            else 1
        )
        return ordered
    if sort == "shelf_first":
        added = shelf_added or {}
        ranks = {book_id: index for index, book_id in enumerate(manual_order)}

        def shelf_key(book):
            timestamp = added.get(book.book_id)
            rank = ranks.get(book.book_id, -1)
            if timestamp is None:
                return (1, rank, 0.0, book.book_id)
            return (0, -timestamp, rank, book.book_id)

        ordered.sort(key=shelf_key)
        return ordered
    if sort == "shelf_order":
        # Follow the shelf arrangement itself: the same depth-first order the
        # shelf page draws, so grouped books stay where the reader put them.
        shelf_ranks = {
            book_id: index for index, book_id in enumerate(shelf_order or ())
        }
        manual_ranks = {
            book_id: index for index, book_id in enumerate(manual_order)
        }

        def arrangement_key(book):
            rank = shelf_ranks.get(book.book_id)
            if rank is not None:
                return (0, rank, book.book_id)
            return (1, manual_ranks.get(book.book_id, -1), book.book_id)

        ordered.sort(key=arrangement_key)
        return ordered

    ordered.sort(key=lambda book: book.title.casefold(), reverse=sort == "title_desc")
    if sort == "created_desc":
        ordered.sort(key=lambda book: book.created_at, reverse=True)
    elif sort == "updated_desc":
        ordered.sort(key=lambda book: book.updated_at, reverse=True)
    return ordered
