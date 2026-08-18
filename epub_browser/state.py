import dataclasses
import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from .identity import new_server_book_id


DB_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class BookRecord:
    book_id: str
    source_path: str
    epub_identifier: Optional[str]
    source_fingerprint: str
    source_size: Optional[int]
    source_mtime_ns: Optional[int]
    metadata_json: str
    active: bool
    created_at: str
    updated_at: str


class StateStore:
    def __init__(
        self,
        database_path: Path,
        connection_factory: Callable = sqlite3.connect,
    ):
        self.database_path = Path(database_path)
        self._connection_factory = connection_factory

    def _connect(self):
        connection = self._connection_factory(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    @contextmanager
    def _connection(self):
        connection = self._connect()
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = self._connect()
        connection.isolation_level = None
        try:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version > DB_SCHEMA_VERSION:
                raise RuntimeError(
                    f"Database uses newer schema version {version}; "
                    f"this version supports {DB_SCHEMA_VERSION}"
                )
            connection.execute("BEGIN IMMEDIATE")
            self._create_compatible_schema(connection)
            connection.execute(f"PRAGMA user_version = {DB_SCHEMA_VERSION}")
            connection.execute("COMMIT")
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def _create_compatible_schema(self, connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS annotations (
                id TEXT PRIMARY KEY,
                username TEXT NOT NULL DEFAULT '',
                book_hash TEXT NOT NULL,
                chapter_index INTEGER NOT NULL,
                text TEXT NOT NULL,
                note TEXT,
                start_meta TEXT,
                end_meta TEXT,
                color TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        self._add_column_if_missing(
            connection,
            "annotations",
            "username",
            "TEXT NOT NULL DEFAULT ''",
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_chapter_username "
            "ON annotations(book_hash, chapter_index, username)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_book_username "
            "ON annotations(book_hash, username)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_username ON annotations(username)"
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS bookshelves (
                username TEXT PRIMARY KEY,
                version INTEGER NOT NULL,
                data TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        if self._add_column_if_missing(
            connection,
            "bookshelves",
            "updated_at",
            "TEXT",
        ):
            connection.execute(
                "UPDATE bookshelves SET updated_at = CURRENT_TIMESTAMP "
                "WHERE updated_at IS NULL"
            )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS reading_progress (
                username TEXT NOT NULL DEFAULT '',
                book_hash TEXT NOT NULL,
                chapter_index INTEGER NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (username, book_hash)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS books (
                book_id TEXT PRIMARY KEY,
                source_path TEXT NOT NULL UNIQUE,
                epub_identifier TEXT,
                source_fingerprint TEXT NOT NULL,
                source_size INTEGER,
                source_mtime_ns INTEGER,
                metadata_json TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0, 1)),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_books_active ON books(active)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_books_package_identity "
            "ON books(epub_identifier, source_fingerprint, active)"
        )

    @staticmethod
    def _add_column_if_missing(
        connection,
        table: str,
        column: str,
        definition: str,
    ) -> bool:
        columns = {
            row["name"]
            for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
        }
        if column in columns:
            return False
        connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
        return True

    def resolve_book(
        self,
        source_path: Path,
        epub_identifier: Optional[str],
        source_fingerprint: str,
        metadata,
        source_size: Optional[int] = None,
        source_mtime_ns: Optional[int] = None,
        preferred_book_id: Optional[str] = None,
    ) -> BookRecord:
        canonical_path = str(Path(source_path).expanduser().resolve())
        identifier = (epub_identifier or "").strip() or None
        metadata_json = self._metadata_json(metadata)
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM books WHERE source_path = ?",
                (canonical_path,),
            ).fetchone()
            if row is not None:
                connection.execute(
                    """
                    UPDATE books SET
                        active = 1,
                        epub_identifier = COALESCE(?, epub_identifier),
                        source_size = COALESCE(?, source_size),
                        source_mtime_ns = COALESCE(?, source_mtime_ns),
                        updated_at = CURRENT_TIMESTAMP
                    WHERE book_id = ?
                    """,
                    (
                        identifier,
                        source_size,
                        source_mtime_ns,
                        row["book_id"],
                    ),
                )
                return self._get_book(connection, row["book_id"])

            move_matches = []
            if identifier and source_fingerprint:
                move_matches = connection.execute(
                    """
                    SELECT * FROM books
                    WHERE active = 0
                      AND epub_identifier = ?
                      AND source_fingerprint = ?
                    """,
                    (identifier, source_fingerprint),
                ).fetchall()
            if len(move_matches) == 1:
                book_id = move_matches[0]["book_id"]
                connection.execute(
                    """
                    UPDATE books SET
                        source_path = ?,
                        metadata_json = ?,
                        source_size = ?,
                        source_mtime_ns = ?,
                        active = 1,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE book_id = ?
                    """,
                    (
                        canonical_path,
                        metadata_json,
                        source_size,
                        source_mtime_ns,
                        book_id,
                    ),
                )
                return self._get_book(connection, book_id)

            book_id = (preferred_book_id or "").strip() or new_server_book_id()
            if connection.execute(
                "SELECT 1 FROM books WHERE book_id = ?",
                (book_id,),
            ).fetchone():
                book_id = new_server_book_id()
            connection.execute(
                """
                INSERT INTO books (
                    book_id, source_path, epub_identifier, source_fingerprint,
                    source_size, source_mtime_ns, metadata_json, active
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 1)
                """,
                (
                    book_id,
                    canonical_path,
                    identifier,
                    source_fingerprint,
                    source_size,
                    source_mtime_ns,
                    metadata_json,
                ),
            )
            return self._get_book(connection, book_id)

    def update_book_version(
        self,
        book_id: str,
        source_fingerprint: str,
        metadata,
        source_size: Optional[int] = None,
        source_mtime_ns: Optional[int] = None,
        epub_identifier: Optional[str] = None,
    ) -> BookRecord:
        metadata_json = self._metadata_json(metadata)
        with self._connection() as connection:
            cursor = connection.execute(
                """
                UPDATE books SET
                    source_fingerprint = ?,
                    metadata_json = ?,
                    source_size = ?,
                    source_mtime_ns = ?,
                    epub_identifier = COALESCE(?, epub_identifier),
                    active = 1,
                    updated_at = CURRENT_TIMESTAMP
                WHERE book_id = ?
                """,
                (
                    source_fingerprint,
                    metadata_json,
                    source_size,
                    source_mtime_ns,
                    (epub_identifier or "").strip() or None,
                    book_id,
                ),
            )
            if cursor.rowcount != 1:
                raise KeyError(f"Unknown book ID: {book_id}")
            return self._get_book(connection, book_id)

    def mark_missing(self, book_id: str) -> None:
        with self._connection() as connection:
            connection.execute(
                "UPDATE books SET active = 0, updated_at = CURRENT_TIMESTAMP "
                "WHERE book_id = ?",
                (book_id,),
            )

    def active_books(self) -> tuple[BookRecord, ...]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM books WHERE active = 1 ORDER BY book_id"
            ).fetchall()
        return tuple(self._book_record(row) for row in rows)

    def book_by_source(self, source_path: Path) -> Optional[BookRecord]:
        canonical_path = str(Path(source_path).expanduser().resolve())
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM books WHERE source_path = ?",
                (canonical_path,),
            ).fetchone()
        return self._book_record(row) if row else None

    def get_annotation(self, annotation_id: str, username: str = ""):
        with self._connection() as connection:
            if username:
                row = connection.execute(
                    "SELECT * FROM annotations WHERE id = ? AND username = ?",
                    (annotation_id, username),
                ).fetchone()
            else:
                row = connection.execute(
                    "SELECT * FROM annotations WHERE id = ?",
                    (annotation_id,),
                ).fetchone()
        return self._annotation_data(row) if row else None

    def list_annotations(
        self,
        book_hash: Optional[str] = None,
        chapter_index: Optional[int] = None,
        username: str = "",
    ):
        clauses = []
        values = []
        if book_hash is not None:
            clauses.append("book_hash = ?")
            values.append(book_hash)
        if chapter_index is not None:
            clauses.append("chapter_index = ?")
            values.append(chapter_index)
        if username:
            clauses.append("username = ?")
            values.append(username)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM annotations" + where + " ORDER BY created_at DESC",
                values,
            ).fetchall()
        return [self._annotation_data(row) for row in rows]

    def upsert_annotation(
        self,
        annotation,
        username: str = "",
        replace_existing: bool = False,
    ) -> None:
        operation = "INSERT OR REPLACE" if replace_existing else "INSERT"
        with self._connection() as connection:
            connection.execute(
                f"""
                {operation} INTO annotations (
                    id, book_hash, chapter_index, text, note, start_meta, end_meta,
                    color, created_at, updated_at, username
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    annotation["id"],
                    annotation["book_hash"],
                    annotation["chapter_index"],
                    annotation["text"],
                    annotation.get("note", ""),
                    self._optional_json(annotation.get("startMeta")),
                    self._optional_json(annotation.get("endMeta")),
                    annotation["color"],
                    annotation["created_at"],
                    annotation["updated_at"],
                    username,
                ),
            )

    def update_annotation(self, annotation_id: str, data, username: str = ""):
        assignments = []
        values = []
        for field in ("note", "color", "chapter_index"):
            if field in data:
                assignments.append(field + " = ?")
                values.append(data[field])
        for field, column in (("startMeta", "start_meta"), ("endMeta", "end_meta")):
            if field in data:
                assignments.append(column + " = ?")
                values.append(self._optional_json(data[field]))
        assignments.append("updated_at = CURRENT_TIMESTAMP")
        selector = "id = ? AND username = ?" if username else "id = ?"
        selector_values = [annotation_id, username] if username else [annotation_id]
        with self._connection() as connection:
            connection.execute(
                "UPDATE annotations SET "
                + ", ".join(assignments)
                + " WHERE "
                + selector,
                values + selector_values,
            )
        return self.get_annotation(annotation_id, username=username)

    def delete_annotation(self, annotation_id: str, username: str = "") -> None:
        selector = "id = ? AND username = ?" if username else "id = ?"
        values = (annotation_id, username) if username else (annotation_id,)
        with self._connection() as connection:
            connection.execute(
                "DELETE FROM annotations WHERE " + selector,
                values,
            )

    def get_bookshelf(self, username: str):
        with self._connection() as connection:
            row = connection.execute(
                "SELECT version, data FROM bookshelves WHERE username = ?",
                (username,),
            ).fetchone()
        return (row["version"], row["data"]) if row else None

    def create_bookshelf(self, username: str, version: int, data) -> None:
        serialized = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False)
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO bookshelves (username, version, data, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                """,
                (username, version, serialized),
            )

    def update_bookshelf(self, username: str, version: int, data) -> None:
        serialized = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False)
        with self._connection() as connection:
            connection.execute(
                """
                UPDATE bookshelves
                SET version = ?, data = ?, updated_at = CURRENT_TIMESTAMP
                WHERE username = ?
                """,
                (version, serialized, username),
            )

    def get_reading_progress(self, username: str, book_hash: str):
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT chapter_index FROM reading_progress
                WHERE username = ? AND book_hash = ?
                """,
                (username, book_hash),
            ).fetchone()
        return row["chapter_index"] if row else None

    def set_reading_progress(
        self,
        username: str,
        book_hash: str,
        chapter_index: int,
    ) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO reading_progress(username, book_hash, chapter_index, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(username, book_hash) DO UPDATE SET
                    chapter_index = excluded.chapter_index,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (username, book_hash, chapter_index),
            )

    def delete_reading_progress(self, username: str, book_hash: str) -> None:
        with self._connection() as connection:
            connection.execute(
                "DELETE FROM reading_progress WHERE username = ? AND book_hash = ?",
                (username, book_hash),
            )

    @staticmethod
    def _metadata_json(metadata) -> str:
        if dataclasses.is_dataclass(metadata):
            metadata = dataclasses.asdict(metadata)
        return json.dumps(
            metadata,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    @staticmethod
    def _optional_json(value):
        return json.dumps(value, ensure_ascii=False) if value else None

    @staticmethod
    def _annotation_data(row):
        data = dict(row)
        data["startMeta"] = json.loads(data["start_meta"]) if data.get("start_meta") else None
        data["endMeta"] = json.loads(data["end_meta"]) if data.get("end_meta") else None
        return data

    @staticmethod
    def _book_record(row) -> BookRecord:
        values = dict(row)
        values["active"] = bool(values["active"])
        return BookRecord(**values)

    def _get_book(self, connection, book_id: str) -> BookRecord:
        row = connection.execute(
            "SELECT * FROM books WHERE book_id = ?",
            (book_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"Unknown book ID: {book_id}")
        return self._book_record(row)
