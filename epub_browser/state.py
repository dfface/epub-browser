import dataclasses
import json
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from .auth import BootstrapCredentials, Principal, hash_password
from .identity import new_server_book_id


DB_SCHEMA_VERSION = 2


@dataclass(frozen=True)
class BookRecord:
    book_id: str
    source_path: str
    epub_identifier: Optional[str]
    source_fingerprint: str
    source_size: Optional[int]
    source_mtime_ns: Optional[int]
    metadata_json: str
    visibility: str
    active: bool
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class UserRecord:
    user_id: str
    username: str
    role: str
    enabled: bool
    password_hash: Optional[str]
    created_at: str
    updated_at: str

    @property
    def principal(self) -> Principal:
        return Principal(self.user_id, self.username, self.role)

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


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
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    @contextmanager
    def _connection(self):
        connection = self._connect()
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def initialize(
        self,
        bootstrap: Optional[BootstrapCredentials] = None,
    ) -> Optional[Principal]:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = self._connect()
        connection.isolation_level = None
        administrator = None
        try:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version > DB_SCHEMA_VERSION:
                raise RuntimeError(
                    f"Database uses newer schema version {version}; "
                    f"this version supports {DB_SCHEMA_VERSION}"
                )
            connection.execute("BEGIN IMMEDIATE")
            self._create_compatible_schema(connection)
            administrator = self._administrator(connection)
            if administrator is None and bootstrap is not None:
                administrator = self._bootstrap_admin(
                    connection,
                    bootstrap.username,
                    hash_password(bootstrap.password),
                )
            if version < 2:
                self._migrate_user_owned_data(
                    connection,
                    administrator.user_id if administrator is not None else None,
                )
            self._create_user_owned_indexes(connection)
            connection.execute(f"PRAGMA user_version = {DB_SCHEMA_VERSION}")
            connection.execute("COMMIT")
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()
        return administrator.principal if administrator is not None else None

    def _create_compatible_schema(self, connection) -> None:
        self._migrate_historical_annotations(connection)
        self._create_account_schema(connection)
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS annotations (
                id TEXT PRIMARY KEY,
                username TEXT NOT NULL DEFAULT '',
                user_id TEXT NOT NULL DEFAULT '',
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
            """
            CREATE TABLE IF NOT EXISTS bookshelves (
                user_id TEXT PRIMARY KEY,
                username TEXT NOT NULL DEFAULT '',
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
                user_id TEXT NOT NULL DEFAULT '',
                username TEXT NOT NULL DEFAULT '',
                book_hash TEXT NOT NULL,
                chapter_index INTEGER NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, book_hash)
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
                visibility TEXT NOT NULL DEFAULT 'authenticated'
                    CHECK(visibility IN ('authenticated', 'restricted')),
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
        self._add_column_if_missing(
            connection,
            "books",
            "visibility",
            "TEXT NOT NULL DEFAULT 'authenticated' "
            "CHECK(visibility IN ('authenticated', 'restricted'))",
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS book_access (
                book_id TEXT NOT NULL REFERENCES books(book_id) ON DELETE CASCADE,
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (book_id, user_id)
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_book_access_user_id "
            "ON book_access(user_id)"
        )

    @staticmethod
    def _create_account_schema(connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                username TEXT NOT NULL COLLATE NOCASE UNIQUE,
                role TEXT NOT NULL CHECK(role IN ('admin', 'member')),
                enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0, 1)),
                password_hash TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS user_identities (
                issuer TEXT NOT NULL,
                subject TEXT NOT NULL,
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                display_name TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (issuer, subject)
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_user_identities_user_id "
            "ON user_identities(user_id)"
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                token_digest TEXT NOT NULL UNIQUE,
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                expires_at TEXT NOT NULL,
                last_used_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                revoked_at TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id)"
        )

    def _migrate_historical_annotations(self, connection) -> None:
        table = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'annotations'"
        ).fetchone()
        if table is None:
            return

        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(annotations)").fetchall()
        }
        if {"start_meta", "end_meta"} <= columns:
            return

        legacy_position_columns = {
            "start_xpath",
            "end_xpath",
            "start_offset",
            "end_offset",
        }
        required_columns = {
            "id",
            "book_hash",
            "chapter_index",
            "text",
            "note",
            "color",
            "created_at",
            "updated_at",
        }
        if not legacy_position_columns <= columns or not required_columns <= columns:
            raise RuntimeError(
                "Unsupported historical annotations schema; expected either "
                "start_meta/end_meta or XPath position columns"
            )

        temporary_table = "annotations_v2_migrating"
        if connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (temporary_table,),
        ).fetchone():
            raise RuntimeError(
                f"Temporary annotation migration table already exists: {temporary_table}"
            )
        connection.execute(
            f"""
            CREATE TABLE {temporary_table} (
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
        rows = connection.execute("SELECT * FROM annotations").fetchall()
        for row in rows:
            start_meta = self._legacy_position_meta(
                row["start_xpath"],
                row["start_offset"],
            )
            end_meta = self._legacy_position_meta(
                row["end_xpath"],
                row["end_offset"],
            )
            connection.execute(
                f"""
                INSERT INTO {temporary_table} (
                    id, username, book_hash, chapter_index, text, note,
                    start_meta, end_meta, color, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["id"],
                    row["username"] if "username" in columns else "",
                    row["book_hash"],
                    row["chapter_index"],
                    row["text"],
                    row["note"],
                    start_meta,
                    end_meta,
                    row["color"],
                    row["created_at"],
                    row["updated_at"],
                ),
            )
        connection.execute("DROP TABLE annotations")
        connection.execute(
            f"ALTER TABLE {temporary_table} RENAME TO annotations"
        )

    @staticmethod
    def _legacy_position_meta(xpath, offset) -> Optional[str]:
        if not xpath:
            return None
        return json.dumps(
            {
                "legacyXPath": xpath,
                "legacyOffset": int(offset or 0),
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
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

    def migrate_user_owned_data(
        self,
        administrator_id: str,
    ) -> None:
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._migrate_user_owned_data(connection, administrator_id)

    def _migrate_user_owned_data(
        self,
        connection,
        administrator_id: Optional[str],
    ) -> None:
        if self._add_column_if_missing(
            connection,
            "annotations",
            "user_id",
            "TEXT NOT NULL DEFAULT ''",
        ):
            if administrator_id is None:
                connection.execute(
                    "UPDATE annotations SET user_id = username"
                )
            else:
                connection.execute(
                    "UPDATE annotations SET user_id = ?",
                    (administrator_id,),
                )
        self._migrate_bookshelves(connection, administrator_id)
        self._migrate_reading_progress(connection, administrator_id)

    @staticmethod
    def _create_user_owned_indexes(connection) -> None:
        connection.execute("DROP INDEX IF EXISTS idx_chapter_username")
        connection.execute("DROP INDEX IF EXISTS idx_book_username")
        connection.execute("DROP INDEX IF EXISTS idx_username")
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_annotations_chapter_user_id "
            "ON annotations(book_hash, chapter_index, user_id)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_annotations_book_user_id "
            "ON annotations(book_hash, user_id)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_annotations_user_id "
            "ON annotations(user_id)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_bookshelves_user_id "
            "ON bookshelves(user_id)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_reading_progress_user_id "
            "ON reading_progress(user_id)"
        )

    def _migrate_bookshelves(
        self,
        connection,
        administrator_id: Optional[str],
    ) -> None:
        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(bookshelves)").fetchall()
        }
        if "user_id" in columns:
            return
        temporary_table = "bookshelves_v2_migrating"
        self._reject_migration_table(connection, temporary_table)
        connection.execute(
            f"""
            CREATE TABLE {temporary_table} (
                user_id TEXT PRIMARY KEY,
                username TEXT NOT NULL DEFAULT '',
                version INTEGER NOT NULL,
                data TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        owner = "username" if administrator_id is None else "?"
        values = () if administrator_id is None else (administrator_id,)
        connection.execute(
            f"""
            INSERT INTO {temporary_table} (
                user_id, username, version, data, updated_at
            )
            SELECT {owner}, username, version, data,
                   COALESCE(updated_at, CURRENT_TIMESTAMP)
            FROM bookshelves
            """,
            values,
        )
        connection.execute("DROP TABLE bookshelves")
        connection.execute(
            f"ALTER TABLE {temporary_table} RENAME TO bookshelves"
        )

    def _migrate_reading_progress(
        self,
        connection,
        administrator_id: Optional[str],
    ) -> None:
        columns = {
            row["name"]
            for row in connection.execute(
                "PRAGMA table_info(reading_progress)"
            ).fetchall()
        }
        if "user_id" in columns:
            return
        temporary_table = "reading_progress_v2_migrating"
        self._reject_migration_table(connection, temporary_table)
        connection.execute(
            f"""
            CREATE TABLE {temporary_table} (
                user_id TEXT NOT NULL DEFAULT '',
                username TEXT NOT NULL DEFAULT '',
                book_hash TEXT NOT NULL,
                chapter_index INTEGER NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, book_hash)
            )
            """
        )
        owner = "username" if administrator_id is None else "?"
        values = () if administrator_id is None else (administrator_id,)
        connection.execute(
            f"""
            INSERT INTO {temporary_table} (
                user_id, username, book_hash, chapter_index, updated_at
            )
            SELECT {owner}, username, book_hash, chapter_index,
                   COALESCE(updated_at, CURRENT_TIMESTAMP)
            FROM reading_progress
            """,
            values,
        )
        connection.execute("DROP TABLE reading_progress")
        connection.execute(
            f"ALTER TABLE {temporary_table} RENAME TO reading_progress"
        )

    @staticmethod
    def _reject_migration_table(connection, table: str) -> None:
        if connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table,),
        ).fetchone():
            raise RuntimeError(
                f"Temporary ownership migration table already exists: {table}"
            )

    def bootstrap_admin(self, username: str, password_hash: str) -> Principal:
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            if self._administrator(connection) is not None:
                raise RuntimeError("An administrator already exists")
            return self._bootstrap_admin(
                connection,
                username,
                password_hash,
            ).principal

    def has_administrator(self) -> bool:
        if not self.database_path.is_file():
            return False
        with self._connection() as connection:
            users_table = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'users'"
            ).fetchone()
            if users_table is None:
                return False
            return self._administrator(connection) is not None

    def _bootstrap_admin(
        self,
        connection,
        username: str,
        password_hash: str,
    ) -> UserRecord:
        normalized = self._normalize_username(username)
        user_id = uuid.uuid4().hex
        connection.execute(
            """
            INSERT INTO users (id, username, role, enabled, password_hash)
            VALUES (?, ?, 'admin', 1, ?)
            """,
            (user_id, normalized, password_hash),
        )
        return self._get_user(connection, user_id)

    def _administrator(self, connection) -> Optional[UserRecord]:
        row = connection.execute(
            """
            SELECT id AS user_id, username, role, enabled, password_hash,
                   created_at, updated_at
            FROM users
            WHERE role = 'admin'
            ORDER BY created_at, id
            LIMIT 1
            """
        ).fetchone()
        return self._user_record(row) if row is not None else None

    @staticmethod
    def _normalize_username(username: str) -> str:
        normalized = username.strip().casefold()
        if not normalized:
            raise ValueError("Username must not be empty")
        return normalized

    def create_user(
        self,
        username: str,
        password_hash: Optional[str],
        *,
        role: str = "member",
    ) -> Principal:
        if role not in {"admin", "member"}:
            raise ValueError(f"Unsupported user role: {role}")
        normalized = self._normalize_username(username)
        user_id = uuid.uuid4().hex
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO users (id, username, role, enabled, password_hash)
                VALUES (?, ?, ?, 1, ?)
                """,
                (user_id, normalized, role, password_hash),
            )
            return self._get_user(connection, user_id).principal

    def get_user_by_username(self, username: str) -> Optional[UserRecord]:
        normalized = self._normalize_username(username)
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT id AS user_id, username, role, enabled, password_hash,
                       created_at, updated_at
                FROM users
                WHERE username = ?
                """,
                (normalized,),
            ).fetchone()
        return self._user_record(row) if row is not None else None

    def set_password_hash(self, user_id: str, password_hash: str) -> UserRecord:
        with self._connection() as connection:
            cursor = connection.execute(
                """
                UPDATE users
                SET password_hash = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (password_hash, user_id),
            )
            if cursor.rowcount != 1:
                raise KeyError(f"Unknown user ID: {user_id}")
            return self._get_user(connection, user_id)

    def set_user_enabled(self, user_id: str, enabled: bool) -> UserRecord:
        with self._connection() as connection:
            cursor = connection.execute(
                """
                UPDATE users
                SET enabled = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (int(enabled), user_id),
            )
            if cursor.rowcount != 1:
                raise KeyError(f"Unknown user ID: {user_id}")
            return self._get_user(connection, user_id)

    def list_users(self) -> tuple[UserRecord, ...]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT id AS user_id, username, role, enabled, password_hash,
                       created_at, updated_at
                FROM users
                ORDER BY username, id
                """
            ).fetchall()
        return tuple(self._user_record(row) for row in rows)

    def set_book_visibility(self, book_id: str, visibility: str) -> None:
        if visibility not in {"authenticated", "restricted"}:
            raise ValueError(f"Unsupported book visibility: {visibility}")
        with self._connection() as connection:
            cursor = connection.execute(
                """
                UPDATE books
                SET visibility = ?, updated_at = CURRENT_TIMESTAMP
                WHERE book_id = ?
                """,
                (visibility, book_id),
            )
            if cursor.rowcount != 1:
                raise KeyError(f"Unknown book ID: {book_id}")

    def grant_book_access(self, book_id: str, user_id: str) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO book_access (book_id, user_id)
                VALUES (?, ?)
                ON CONFLICT(book_id, user_id) DO NOTHING
                """,
                (book_id, user_id),
            )

    def revoke_book_access(self, book_id: str, user_id: str) -> None:
        with self._connection() as connection:
            connection.execute(
                "DELETE FROM book_access WHERE book_id = ? AND user_id = ?",
                (book_id, user_id),
            )

    def visible_books(self, principal: Principal) -> tuple[BookRecord, ...]:
        with self._connection() as connection:
            if principal.role == "admin":
                rows = connection.execute(
                    "SELECT * FROM books WHERE active = 1 ORDER BY book_id"
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT books.*
                    FROM books
                    WHERE books.active = 1
                      AND (
                        books.visibility = 'authenticated'
                        OR EXISTS (
                            SELECT 1 FROM book_access
                            WHERE book_access.book_id = books.book_id
                              AND book_access.user_id = ?
                        )
                      )
                    ORDER BY books.book_id
                    """,
                    (principal.user_id,),
                ).fetchall()
        return tuple(self._book_record(row) for row in rows)

    def can_read_book(self, user_id: str, role: str, book_id: str) -> bool:
        with self._connection() as connection:
            book = connection.execute(
                "SELECT visibility FROM books WHERE book_id = ? AND active = 1",
                (book_id,),
            ).fetchone()
            if book is None:
                return False
            if role == "admin" or book["visibility"] == "authenticated":
                return True
            grant = connection.execute(
                """
                SELECT 1 FROM book_access
                WHERE book_id = ? AND user_id = ?
                """,
                (book_id, user_id),
            ).fetchone()
        return grant is not None

    def resolve_book(
        self,
        source_path: Path,
        epub_identifier: Optional[str],
        source_fingerprint: str,
        metadata,
        source_size: Optional[int] = None,
        source_mtime_ns: Optional[int] = None,
        preferred_book_id: Optional[str] = None,
        authoritative_book_id: Optional[str] = None,
    ) -> BookRecord:
        canonical_path = str(Path(source_path).expanduser().resolve())
        identifier = (epub_identifier or "").strip() or None
        authoritative_id = (authoritative_book_id or "").strip() or None
        metadata_json = self._metadata_json(metadata)
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM books WHERE source_path = ?",
                (canonical_path,),
            ).fetchone()
            if row is not None:
                if authoritative_id and row["book_id"] != authoritative_id:
                    raise ValueError(
                        "Book ID conflicts with the book registered "
                        f"for {canonical_path}"
                    )
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

            if authoritative_id:
                identity_row = connection.execute(
                    "SELECT * FROM books WHERE book_id = ?",
                    (authoritative_id,),
                ).fetchone()
                if identity_row is not None:
                    if identity_row["active"]:
                        raise ValueError(
                            "Book ID is already used by another source: "
                            f"{identity_row['source_path']}"
                        )
                    connection.execute(
                        """
                        UPDATE books SET
                            source_path = ?,
                            epub_identifier = COALESCE(?, epub_identifier),
                            source_fingerprint = ?,
                            metadata_json = ?,
                            source_size = ?,
                            source_mtime_ns = ?,
                            active = 1,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE book_id = ?
                        """,
                        (
                            canonical_path,
                            identifier,
                            source_fingerprint,
                            metadata_json,
                            source_size,
                            source_mtime_ns,
                            authoritative_id,
                        ),
                    )
                    return self._get_book(connection, authoritative_id)

            move_matches = self._inactive_move_rows(
                connection,
                identifier,
                source_fingerprint,
            )
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
            if len(move_matches) > 1:
                raise ValueError(
                    "Multiple inactive books match the same EPUB identifier "
                    "and fingerprint"
                )

            book_id = (
                authoritative_id
                or (preferred_book_id or "").strip()
                or new_server_book_id()
            )
            if connection.execute(
                "SELECT 1 FROM books WHERE book_id = ?",
                (book_id,),
            ).fetchone():
                if authoritative_id:
                    raise ValueError(
                        f"Book ID is already registered: {book_id}"
                    )
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

    @staticmethod
    def _inactive_move_rows(connection, identifier, source_fingerprint):
        if not identifier or not source_fingerprint:
            return []
        return connection.execute(
            """
            SELECT * FROM books
            WHERE active = 0
              AND epub_identifier = ?
              AND source_fingerprint = ?
            ORDER BY book_id
            """,
            (identifier, source_fingerprint),
        ).fetchall()

    def inactive_book_matches(
        self,
        epub_identifier: Optional[str],
        source_fingerprint: str,
    ) -> tuple[BookRecord, ...]:
        identifier = (epub_identifier or "").strip() or None
        with self._connection() as connection:
            rows = self._inactive_move_rows(
                connection,
                identifier,
                source_fingerprint,
            )
        return tuple(self._book_record(row) for row in rows)

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

    def get_annotation(self, annotation_id: str, user_id: str = ""):
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM annotations WHERE id = ? AND user_id = ?",
                (annotation_id, user_id),
            ).fetchone()
        return self._annotation_data(row) if row else None

    def list_annotations(
        self,
        book_hash: Optional[str] = None,
        chapter_index: Optional[int] = None,
        user_id: str = "",
    ):
        clauses = []
        values = []
        if book_hash is not None:
            clauses.append("book_hash = ?")
            values.append(book_hash)
        if chapter_index is not None:
            clauses.append("chapter_index = ?")
            values.append(chapter_index)
        clauses.append("user_id = ?")
        values.append(user_id)
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
        user_id: str = "",
        replace_existing: bool = False,
    ) -> None:
        operation = "INSERT OR REPLACE" if replace_existing else "INSERT"
        with self._connection() as connection:
            connection.execute(
                f"""
                {operation} INTO annotations (
                    id, book_hash, chapter_index, text, note, start_meta, end_meta,
                    color, created_at, updated_at, user_id, username
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    user_id,
                    "",
                ),
            )

    def update_annotation(self, annotation_id: str, data, user_id: str = ""):
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
        with self._connection() as connection:
            connection.execute(
                "UPDATE annotations SET "
                + ", ".join(assignments)
                + " WHERE id = ? AND user_id = ?",
                values + [annotation_id, user_id],
            )
        return self.get_annotation(annotation_id, user_id=user_id)

    def delete_annotation(self, annotation_id: str, user_id: str = "") -> None:
        with self._connection() as connection:
            connection.execute(
                "DELETE FROM annotations WHERE id = ? AND user_id = ?",
                (annotation_id, user_id),
            )

    def get_bookshelf(self, user_id: str):
        with self._connection() as connection:
            row = connection.execute(
                "SELECT version, data FROM bookshelves WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        return (row["version"], row["data"]) if row else None

    def create_bookshelf(self, user_id: str, version: int, data) -> None:
        serialized = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False)
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO bookshelves (
                    user_id, username, version, data, updated_at
                ) VALUES (?, '', ?, ?, CURRENT_TIMESTAMP)
                """,
                (user_id, version, serialized),
            )

    def update_bookshelf(self, user_id: str, version: int, data) -> None:
        serialized = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False)
        with self._connection() as connection:
            connection.execute(
                """
                UPDATE bookshelves
                SET version = ?, data = ?, updated_at = CURRENT_TIMESTAMP
                WHERE user_id = ?
                """,
                (version, serialized, user_id),
            )

    def get_reading_progress(self, user_id: str, book_hash: str):
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT chapter_index FROM reading_progress
                WHERE user_id = ? AND book_hash = ?
                """,
                (user_id, book_hash),
            ).fetchone()
        return row["chapter_index"] if row else None

    def set_reading_progress(
        self,
        user_id: str,
        book_hash: str,
        chapter_index: int,
    ) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO reading_progress(
                    user_id, username, book_hash, chapter_index, updated_at
                ) VALUES (?, '', ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(user_id, book_hash) DO UPDATE SET
                    chapter_index = excluded.chapter_index,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (user_id, book_hash, chapter_index),
            )

    def delete_reading_progress(self, user_id: str, book_hash: str) -> None:
        with self._connection() as connection:
            connection.execute(
                "DELETE FROM reading_progress WHERE user_id = ? AND book_hash = ?",
                (user_id, book_hash),
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

    @staticmethod
    def _user_record(row) -> UserRecord:
        values = dict(row)
        values["enabled"] = bool(values["enabled"])
        return UserRecord(**values)

    def _get_user(self, connection, user_id: str) -> UserRecord:
        row = connection.execute(
            """
            SELECT id AS user_id, username, role, enabled, password_hash,
                   created_at, updated_at
            FROM users
            WHERE id = ?
            """,
            (user_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"Unknown user ID: {user_id}")
        return self._user_record(row)

    def _get_book(self, connection, book_id: str) -> BookRecord:
        row = connection.execute(
            "SELECT * FROM books WHERE book_id = ?",
            (book_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"Unknown book ID: {book_id}")
        return self._book_record(row)
