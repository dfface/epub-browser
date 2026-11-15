import unittest
from types import SimpleNamespace

from epub_browser.book_sort import library_sort, sort_catalog


def record(book_id, created_at="2024-01-01", source_format="epub"):
    return SimpleNamespace(
        book_id=book_id,
        title=book_id.upper(),
        created_at=created_at,
        updated_at=created_at,
        source_format=source_format,
    )


class ShelfFirstSortTests(unittest.TestCase):
    def test_shelf_books_come_first_ordered_by_added_time_desc(self):
        books = [record("a"), record("b"), record("c"), record("d")]
        ordered = sort_catalog(
            books,
            "shelf_first",
            ("d", "c", "b", "a"),
            shelf_added={"b": 200.0, "c": 100.0, "d": 300.0},
        )
        self.assertEqual([book.book_id for book in ordered], ["d", "b", "c", "a"])

    def test_non_shelf_books_follow_manual_order(self):
        books = [record("a"), record("b"), record("c"), record("d")]
        ordered = sort_catalog(
            books,
            "shelf_first",
            ("c", "b"),
            shelf_added={"a": 10.0},
        )
        self.assertEqual([book.book_id for book in ordered], ["a", "d", "c", "b"])

    def test_shelf_first_without_manual_order_uses_id_tiebreak(self):
        books = [record("c"), record("a"), record("b")]
        ordered = sort_catalog(books, "shelf_first", (), shelf_added={"a": 1.0})
        self.assertEqual([book.book_id for book in ordered], ["a", "b", "c"])

    def test_other_sorts_do_not_consume_shelf_data(self):
        books = [record("b"), record("a")]
        ordered = sort_catalog(books, "title_asc", (), shelf_added={"b": 100.0})
        self.assertEqual([book.book_id for book in ordered], ["a", "b"])


class ShelfOrderSortTests(unittest.TestCase):
    def test_shelf_books_follow_the_arrangement_order(self):
        books = [record("a"), record("b"), record("c"), record("d")]
        ordered = sort_catalog(
            books,
            "shelf_order",
            ("d", "c", "b", "a"),
            shelf_order=["c", "a", "d"],
            shelf_added={"a": 300.0, "c": 200.0, "d": 100.0},
        )
        self.assertEqual([book.book_id for book in ordered], ["c", "a", "d", "b"])

    def test_non_shelf_books_follow_manual_order(self):
        books = [record("a"), record("b"), record("c"), record("d")]
        ordered = sort_catalog(
            books,
            "shelf_order",
            ("c", "b"),
            shelf_order=["a"],
        )
        self.assertEqual([book.book_id for book in ordered], ["a", "d", "c", "b"])

    def test_shelf_order_is_an_allowed_library_sort(self):
        self.assertEqual(library_sort("shelf_order"), "shelf_order")


class PdfFirstSortTests(unittest.TestCase):
    def test_pdf_books_come_first_with_newest_books_in_each_group(self):
        books = [
            record("a", "2024-03-01"),
            record("p1", "2024-01-01", "pdf"),
            record("b", "2024-05-01"),
            record("p2", "2024-06-01", "pdf"),
        ]
        ordered = sort_catalog(books, "pdf_first")
        self.assertEqual([book.book_id for book in ordered], ["p2", "p1", "b", "a"])

    def test_pdf_first_uses_title_order_for_equal_timestamps(self):
        books = [
            record("z", "2024-01-01"),
            record("p_b", "2024-01-01", "pdf"),
            record("p_a", "2024-01-01", "pdf"),
        ]
        ordered = sort_catalog(books, "pdf_first")
        self.assertEqual([book.book_id for book in ordered], ["p_a", "p_b", "z"])

    def test_pdf_first_is_an_allowed_library_sort(self):
        self.assertEqual(library_sort("pdf_first"), "pdf_first")


if __name__ == "__main__":
    unittest.main()
