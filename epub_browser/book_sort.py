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
LIBRARY_SORT_OPTIONS = {"manual": "library.sort.manual", **BOOK_SORT_OPTIONS}


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


def sort_catalog(books, sort, manual_order=()):
    """Order visible book records before applying any page boundary."""
    ordered = list(books)  # The visible-books query supplies the ID tie-break order.
    if sort == "manual":
        if manual_order:
            ranks = {book_id: index for index, book_id in enumerate(manual_order)}
            ordered.sort(key=lambda book: ranks.get(book.book_id, -1))
        return ordered

    ordered.sort(key=lambda book: book.title.casefold(), reverse=sort == "title_desc")
    if sort == "created_desc":
        ordered.sort(key=lambda book: book.created_at, reverse=True)
    elif sort == "updated_desc":
        ordered.sort(key=lambda book: book.updated_at, reverse=True)
    return ordered
