import unittest
from types import SimpleNamespace

from epub_browser.book_sort import sort_catalog


def record(book_id):
    return SimpleNamespace(
        book_id=book_id,
        title=book_id.upper(),
        created_at="2024-01-01",
        updated_at="2024-01-01",
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


if __name__ == "__main__":
    unittest.main()
