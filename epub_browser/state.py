import dataclasses
import hmac
import json
import math
import re
import sqlite3
import time
import unicodedata
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional, Sequence

from .auth import (
    BootstrapCredentials,
    Principal,
    hash_password,
    token_digest,
    validate_password_hash,
)
from .identity import new_server_book_id


DB_SCHEMA_VERSION = 11

_PUBLIC_AI_READING_JOB_ERROR_CODES = frozenset({
    "ai_disabled",
    "ai_not_authorized",
    "ai_quota_exhausted",
    "ai_job_not_retryable",
    "book_not_found",
    "chapter_not_found",
    "source_unavailable",
    "no_reading_material",
    "ai_template_unavailable",
    "provider_connection_failed",
    "provider_rate_limited",
    "provider_request_rejected",
    "provider_server_error",
    "provider_invalid_response",
    "ai_generation_failed",
})

_V11_INDEX_CONTRACTS = (
    ("idx_books_active_book", "books", False,
     (("active", False), ("book_id", False)), None),
    ("idx_annotations_user_created", "annotations", False,
     (("user_id", False), ("created_at", True), ("id", False)), None),
    ("idx_annotations_user_book_created", "annotations", False,
     (("user_id", False), ("book_hash", False), ("created_at", True),
      ("id", False)), None),
    ("idx_annotations_user_book_chapter_created", "annotations", False,
     (("user_id", False), ("book_hash", False), ("chapter_index", False),
      ("created_at", True), ("id", False)), None),
    ("idx_sessions_user_created", "sessions", False,
     (("user_id", False), ("created_at", True), ("session_id", False)), None),
    ("idx_ai_jobs_created", "ai_reading_jobs", False,
     (("created_at", True), ("id", True)), None),
    ("idx_ai_jobs_status_created", "ai_reading_jobs", False,
     (("status", False), ("created_at", True), ("id", True)), None),
    ("idx_ai_jobs_queue", "ai_reading_jobs", False,
     (("created_at", False), ("id", False)),
     "status='queued' AND request_json IS NOT NULL"),
    ("idx_ai_jobs_active_cache", "ai_reading_jobs", True,
     (("cache_key", False),), "status IN ('queued','running')"),
    ("idx_ai_jobs_result", "ai_reading_jobs", False,
     (("result_id", False),), "result_id IS NOT NULL"),
    ("idx_ai_jobs_retry_root", "ai_reading_jobs", False,
     (("retry_root_job_id", False), ("attempt_number", False)), None),
    ("idx_ai_followups_queue", "ai_reading_followups", False,
     (("created_at", False), ("id", False)), "status='queued'"),
    ("idx_ai_followups_result_owner_created", "ai_reading_followups", False,
     (("result_id", False), ("owner_user_id", False), ("created_at", False)),
     None),
    ("idx_ai_book_chat_queue", "ai_book_chat_turns", False,
     (("created_at", False),), "status='queued'"),
    ("idx_ai_book_chat_owner_book_created", "ai_book_chat_turns", False,
     (("owner_user_id", False), ("book_id", False), ("created_at", False),
      ("id", False)), None),
    ("idx_ai_book_chat_result", "ai_book_chat_turns", False,
     (("result_id", False),), "result_id IS NOT NULL"),
    ("idx_ai_results_book_created", "ai_reading_results", False,
     (("book_id", False), ("created_at", True), ("id", True)), None),
    ("idx_ai_results_chapter_language_created", "ai_reading_results", False,
     (("book_id", False), ("chapter_index", False), ("language", False),
      ("created_at", True), ("id", True)), None),
    ("idx_ai_current_results_result", "ai_reading_current_results", False,
     (("result_id", False),), None),
    ("idx_book_ai_tags_tag", "book_ai_tags", False,
     (("tag_id", False),), None),
)


class SetupAlreadyCompleteError(RuntimeError):
    pass


class _AIRetrySnapshotChanged(RuntimeError):
    """Signal that retry preparation no longer matches transactional state."""


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


@dataclass(frozen=True)
class UserIdentityRecord:
    issuer: str
    subject: str
    user_id: str
    display_name: Optional[str]
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class SessionRecord:
    session_id: str
    user_id: str
    expires_at: float
    last_used_at: float
    revoked_at: Optional[float]
    created_at: float
    client_address: Optional[str]
    user_agent: Optional[str]


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
        self._configure_connection(connection)
        return connection

    @staticmethod
    def _configure_connection(connection) -> None:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        connection.execute("PRAGMA synchronous = NORMAL")

    def _configure_database(self) -> str:
        with self._connection() as connection:
            mode = str(
                connection.execute("PRAGMA journal_mode = WAL").fetchone()[0]
            )
            connection.execute("PRAGMA optimize")
        return mode

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
            connection.execute("BEGIN IMMEDIATE")
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version > DB_SCHEMA_VERSION:
                raise RuntimeError(
                    f"Database uses newer schema version {version}; "
                    f"this version supports {DB_SCHEMA_VERSION}"
                )
            empty_database = not self._has_application_tables(connection)
            self._create_compatible_schema(
                connection,
                latest=empty_database or version >= 11,
            )
            administrator = self._administrator(connection)
            if administrator is None:
                administrator = (
                    self._create_pending_administrator(connection)
                    if bootstrap is None
                    else self._bootstrap_admin(
                        connection,
                        bootstrap.username,
                        hash_password(bootstrap.password),
                    )
                )
            elif (
                bootstrap is not None
                and self._administrator_is_pending(
                    connection,
                    administrator.user_id,
                )
            ):
                administrator = self._complete_pending_administrator(
                    connection,
                    administrator.user_id,
                    bootstrap.username,
                    hash_password(bootstrap.password),
                )
            if version < 2:
                self._migrate_user_owned_data(
                    connection,
                    administrator.user_id if administrator is not None else None,
                )
            if version < 3:
                self._migrate_annotation_primary_key(connection)
            self._validate_password_hashes(connection)
            if empty_database:
                self._create_v11_indexes(connection)
                self._require_foreign_key_integrity(connection)
                connection.execute("PRAGMA user_version = 11")
            elif version < 11:
                self._migrate_schema_v11(connection, version)
            else:
                self._create_v11_indexes(connection)
                self._require_foreign_key_integrity(connection)
            connection.execute("COMMIT")
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()
        self._configure_database()
        return administrator.principal if administrator is not None else None

    @staticmethod
    def _has_application_tables(connection) -> bool:
        return connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' "
            "AND name NOT LIKE 'sqlite_%' LIMIT 1"
        ).fetchone() is not None

    def _create_compatible_schema(self, connection, *, latest: bool = False) -> None:
        self._migrate_historical_annotations(connection)
        self._create_account_schema(connection, latest=latest)
        self._add_column_if_missing(
            connection,
            "users",
            "setup_pending",
            "INTEGER NOT NULL DEFAULT 0 CHECK(setup_pending IN (0, 1))",
        )
        if latest:
            self._create_v11_annotations_table(connection)
        else:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS annotations (
                id TEXT NOT NULL,
                username TEXT NOT NULL DEFAULT '',
                user_id TEXT NOT NULL CHECK(length(user_id) > 0)
                    REFERENCES users(id) ON DELETE CASCADE,
                book_hash TEXT NOT NULL,
                chapter_index INTEGER NOT NULL,
                text TEXT NOT NULL,
                note TEXT,
                start_meta TEXT,
                end_meta TEXT,
                color TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (user_id, id)
            )
                """
            )
            self._add_column_if_missing(
                connection,
                "annotations",
                "username",
                "TEXT NOT NULL DEFAULT ''",
            )
        if latest:
            self._create_v11_bookshelves_table(connection)
        else:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS bookshelves (
                user_id TEXT NOT NULL PRIMARY KEY CHECK(length(user_id) > 0)
                    REFERENCES users(id) ON DELETE CASCADE,
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
        if latest:
            self._create_v11_reading_progress_table(connection)
        else:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS reading_progress (
                user_id TEXT NOT NULL CHECK(length(user_id) > 0)
                    REFERENCES users(id) ON DELETE CASCADE,
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
        if not latest:
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
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_settings (
                singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
                enabled INTEGER NOT NULL DEFAULT 0 CHECK(enabled IN (0, 1)),
                base_url TEXT NOT NULL DEFAULT '',
                api_key TEXT NOT NULL DEFAULT '',
                model TEXT NOT NULL DEFAULT '',
                timeout_seconds INTEGER NOT NULL DEFAULT 60
                    CHECK(timeout_seconds BETWEEN 5 AND 3600),
                model_context_window INTEGER NOT NULL DEFAULT 32768
                    CHECK(model_context_window BETWEEN 2048 AND 100000000),
                max_concurrency INTEGER NOT NULL DEFAULT 2
                    CHECK(max_concurrency BETWEEN 1 AND 4),
                daily_limit INTEGER NOT NULL DEFAULT 20
                    CHECK(daily_limit >= 0),
                config_revision INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            "INSERT INTO ai_settings (singleton) VALUES (1) "
            "ON CONFLICT(singleton) DO NOTHING"
        )
        added_context_window = self._add_column_if_missing(
            connection, "ai_settings", "model_context_window",
            "INTEGER NOT NULL DEFAULT 32768 CHECK(model_context_window BETWEEN 2048 AND 100000000)",
        )
        if added_context_window:
            columns = {row["name"] for row in connection.execute("PRAGMA table_info(ai_settings)")}
            if "chat_context_tokens" in columns:
                connection.execute(
                    "UPDATE ai_settings SET model_context_window = chat_context_tokens"
                )
        self._migrate_ai_settings_constraints(connection)
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_user_access (
                user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                enabled INTEGER NOT NULL DEFAULT 0 CHECK(enabled IN (0, 1)),
                daily_limit INTEGER CHECK(daily_limit IS NULL OR daily_limit >= 0),
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_tags (
                id TEXT PRIMARY KEY,
                normalized_name TEXT NOT NULL COLLATE NOCASE UNIQUE,
                name TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS book_ai_tags (
                book_id TEXT NOT NULL REFERENCES books(book_id) ON DELETE CASCADE,
                tag_id TEXT NOT NULL REFERENCES ai_tags(id) ON DELETE CASCADE,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (book_id, tag_id)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS book_ai_profiles (
                book_id TEXT PRIMARY KEY REFERENCES books(book_id) ON DELETE CASCADE,
                profile TEXT NOT NULL DEFAULT 'auto'
                    CHECK(profile IN ('auto', 'technical', 'fiction', 'general')),
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_usage (
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                usage_day TEXT NOT NULL,
                provider_calls INTEGER NOT NULL DEFAULT 0
                    CHECK(provider_calls >= 0),
                PRIMARY KEY (user_id, usage_day)
            )
            """
        )
        if latest:
            self._create_v11_ai_reading_jobs_table(connection)
        else:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS ai_reading_jobs (
                id TEXT PRIMARY KEY,
                owner_user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                book_id TEXT REFERENCES books(book_id) ON DELETE CASCADE,
                cache_key TEXT NOT NULL,
                request_json TEXT,
                profile TEXT,
                template_id TEXT,
                template_version INTEGER,
                status TEXT NOT NULL CHECK(status IN (
                    'queued', 'running', 'complete', 'failed', 'interrupted'
                )),
                error_code TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
                """
            )
        if not latest:
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_ai_reading_jobs_owner "
                "ON ai_reading_jobs(owner_user_id, created_at DESC)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_ai_reading_jobs_active_cache "
                "ON ai_reading_jobs(cache_key, status)"
            )
        if not latest:
            self._add_column_if_missing(
                connection,
                "ai_reading_jobs",
                "book_id",
                "TEXT REFERENCES books(book_id) ON DELETE CASCADE",
            )
            self._add_column_if_missing(
                connection,
                "ai_reading_jobs",
                "result_id",
                "TEXT",
            )
            self._add_column_if_missing(
                connection,
                "ai_reading_jobs",
                "progress_current",
                "INTEGER NOT NULL DEFAULT 0 CHECK(progress_current >= 0)",
            )
            self._add_column_if_missing(
                connection,
                "ai_reading_jobs",
                "progress_total",
                "INTEGER NOT NULL DEFAULT 1 CHECK(progress_total >= 1)",
            )
            self._add_column_if_missing(connection, "ai_reading_jobs", "request_json", "TEXT")
            self._add_column_if_missing(connection, "ai_reading_jobs", "profile", "TEXT")
            self._add_column_if_missing(connection, "ai_reading_jobs", "template_id", "TEXT")
            self._add_column_if_missing(connection, "ai_reading_jobs", "template_version", "INTEGER")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_reading_results (
                id TEXT PRIMARY KEY,
                cache_key TEXT NOT NULL,
                book_id TEXT NOT NULL REFERENCES books(book_id) ON DELETE CASCADE,
                chapter_index INTEGER,
                scope TEXT NOT NULL CHECK(scope IN ('book', 'chapter')),
                mode TEXT NOT NULL CHECK(mode IN (
                    'spoiler_free', 'read_so_far', 'full_review', 'chapter'
                )),
                profile TEXT NOT NULL CHECK(profile IN (
                    'auto', 'technical', 'fiction', 'general'
                )),
                language TEXT NOT NULL DEFAULT 'en' CHECK(language IN ('en', 'zh-CN')),
                reading_boundary INTEGER,
                config_revision INTEGER NOT NULL CHECK(config_revision >= 0),
                template_id TEXT NOT NULL DEFAULT 'legacy',
                template_version INTEGER NOT NULL DEFAULT 0 CHECK(template_version >= 0),
                content_json TEXT NOT NULL,
                created_by_user_id TEXT NOT NULL
                    REFERENCES users(id) ON DELETE CASCADE,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        if not latest:
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_ai_reading_results_book "
                "ON ai_reading_results(book_id, created_at DESC)"
            )
        self._add_column_if_missing(
            connection, "ai_reading_results", "template_id", "TEXT NOT NULL DEFAULT 'legacy'"
        )
        self._add_column_if_missing(
            connection, "ai_reading_results", "template_version",
            "INTEGER NOT NULL DEFAULT 0 CHECK(template_version >= 0)",
        )
        self._add_column_if_missing(
            connection, "ai_reading_results", "language",
            "TEXT NOT NULL DEFAULT 'en' CHECK(language IN ('en', 'zh-CN'))",
        )
        self._add_column_if_missing(
            connection, "ai_reading_results", "reading_boundary", "INTEGER",
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_reading_current_results (
                cache_key TEXT PRIMARY KEY,
                result_id TEXT NOT NULL REFERENCES ai_reading_results(id)
                    ON DELETE CASCADE,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_reading_followups (
                id TEXT PRIMARY KEY,
                result_id TEXT NOT NULL REFERENCES ai_reading_results(id)
                    ON DELETE CASCADE,
                owner_user_id TEXT NOT NULL REFERENCES users(id)
                    ON DELETE CASCADE,
                question TEXT NOT NULL,
                language TEXT NOT NULL DEFAULT 'en' CHECK(language IN ('en', 'zh-CN')),
                answer TEXT,
                status TEXT NOT NULL CHECK(status IN (
                    'queued', 'running', 'complete', 'failed', 'interrupted'
                )),
                error_code TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        if not latest:
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_ai_reading_followups_owner "
                "ON ai_reading_followups(owner_user_id, created_at ASC)"
            )
        self._add_column_if_missing(
            connection, "ai_reading_followups", "language",
            "TEXT NOT NULL DEFAULT 'en' CHECK(language IN ('en', 'zh-CN'))",
        )
        # A book conversation deliberately lives separately from the legacy
        # result-bound follow-ups.  A reader may ask from a chapter's source
        # before a shared reading layer exists, while the whole conversation
        # still needs to remain ordered and resumable for that reader.
        if latest:
            self._create_v11_ai_book_chat_turns_table(connection)
        else:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS ai_book_chat_turns (
                id TEXT PRIMARY KEY,
                book_id TEXT NOT NULL,
                chapter_index INTEGER NOT NULL CHECK(chapter_index >= 0),
                result_id TEXT REFERENCES ai_reading_results(id) ON DELETE SET NULL,
                context_mode TEXT NOT NULL CHECK(context_mode IN (
                    'shared_layer', 'chapter_source'
                )),
                book_context INTEGER NOT NULL DEFAULT 0 CHECK(book_context IN (0, 1)),
                owner_user_id TEXT NOT NULL REFERENCES users(id)
                    ON DELETE CASCADE,
                question TEXT NOT NULL,
                language TEXT NOT NULL DEFAULT 'en' CHECK(language IN ('en', 'zh-CN')),
                answer TEXT,
                status TEXT NOT NULL CHECK(status IN (
                    'queued', 'running', 'complete', 'failed', 'interrupted'
                )),
                error_code TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
                """
            )
        if not latest:
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_ai_book_chat_turns_owner_book "
                "ON ai_book_chat_turns(owner_user_id, book_id, created_at ASC, id ASC)"
            )
        self._add_column_if_missing(
            connection, "ai_book_chat_turns", "book_context",
            "INTEGER NOT NULL DEFAULT 0 CHECK(book_context IN (0, 1))",
        )
        if latest:
            self._create_v11_ai_book_chat_summaries_table(connection)
        else:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS ai_book_chat_summaries (
                book_id TEXT NOT NULL,
                owner_user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                language TEXT NOT NULL CHECK(language IN ('en', 'zh-CN')),
                covered_turn_count INTEGER NOT NULL DEFAULT 0 CHECK(covered_turn_count >= 0),
                summary_text TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (book_id, owner_user_id, language)
            )
                """
            )

    @staticmethod
    def _create_account_schema(connection, *, latest: bool = False) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                username TEXT NOT NULL COLLATE NOCASE UNIQUE,
                role TEXT NOT NULL CHECK(role IN ('admin', 'member')),
                enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0, 1)),
                password_hash TEXT,
                setup_pending INTEGER NOT NULL DEFAULT 0
                    CHECK(setup_pending IN (0, 1)),
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
        if latest:
            StateStore._create_v11_sessions_table(connection)
        else:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                token_digest TEXT NOT NULL UNIQUE,
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                expires_at TEXT NOT NULL,
                last_used_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                revoked_at TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                client_address TEXT,
                user_agent TEXT
            )
                """
            )
        StateStore._add_column_if_missing(
            connection,
            "sessions",
            "client_address",
            "TEXT",
        )
        StateStore._add_column_if_missing(
            connection,
            "sessions",
            "user_agent",
            "TEXT",
        )
        if not latest:
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id)"
            )

    @staticmethod
    def _create_v11_annotations_table(connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS annotations (
                id TEXT NOT NULL,
                book_hash TEXT NOT NULL,
                chapter_index INTEGER NOT NULL,
                text TEXT NOT NULL,
                note TEXT,
                start_meta TEXT,
                end_meta TEXT,
                color TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                PRIMARY KEY (user_id, id)
            )
            """
        )

    @staticmethod
    def _create_v11_bookshelves_table(connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS bookshelves (
                user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                version INTEGER NOT NULL,
                data TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

    @staticmethod
    def _create_v11_reading_progress_table(connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS reading_progress (
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                book_hash TEXT NOT NULL,
                chapter_index INTEGER NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, book_hash)
            )
            """
        )

    @staticmethod
    def _create_v11_sessions_table(connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                token_digest TEXT NOT NULL UNIQUE,
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                expires_at REAL NOT NULL,
                last_used_at REAL NOT NULL,
                revoked_at REAL,
                created_at REAL NOT NULL,
                client_address TEXT,
                user_agent TEXT
            )
            """
        )

    @staticmethod
    def _create_v11_ai_reading_jobs_table(connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_reading_jobs (
                id TEXT PRIMARY KEY,
                owner_user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                book_id TEXT REFERENCES books(book_id) ON DELETE CASCADE,
                cache_key TEXT NOT NULL,
                request_json TEXT,
                profile TEXT,
                template_id TEXT,
                template_version INTEGER,
                status TEXT NOT NULL CHECK(status IN (
                    'queued', 'running', 'complete', 'failed', 'interrupted'
                )),
                error_code TEXT,
                result_id TEXT REFERENCES ai_reading_results(id) ON DELETE SET NULL,
                progress_current INTEGER NOT NULL DEFAULT 0,
                progress_total INTEGER NOT NULL DEFAULT 1,
                attempt_number INTEGER NOT NULL DEFAULT 1 CHECK(attempt_number >= 1),
                retried_from_job_id TEXT REFERENCES ai_reading_jobs(id) ON DELETE SET NULL,
                retry_root_job_id TEXT REFERENCES ai_reading_jobs(id) ON DELETE SET NULL,
                retried_by_user_id TEXT REFERENCES users(id) ON DELETE SET NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                CHECK(
                    progress_current >= 0
                    AND progress_total >= 1
                    AND progress_current <= progress_total
                ),
                CHECK(
                    NOT (result_id IS NOT NULL AND error_code IS NOT NULL)
                    AND (status != 'failed' OR error_code IS NOT NULL)
                )
            )
            """
        )

    @staticmethod
    def _create_v11_ai_book_chat_turns_table(connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_book_chat_turns (
                id TEXT PRIMARY KEY,
                book_id TEXT NOT NULL REFERENCES books(book_id) ON DELETE CASCADE,
                chapter_index INTEGER NOT NULL CHECK(chapter_index >= 0),
                result_id TEXT REFERENCES ai_reading_results(id) ON DELETE SET NULL,
                context_mode TEXT NOT NULL CHECK(context_mode IN (
                    'shared_layer', 'chapter_source'
                )),
                book_context INTEGER NOT NULL DEFAULT 0 CHECK(book_context IN (0, 1)),
                owner_user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                question TEXT NOT NULL,
                language TEXT NOT NULL DEFAULT 'en' CHECK(language IN ('en', 'zh-CN')),
                answer TEXT,
                status TEXT NOT NULL CHECK(status IN (
                    'queued', 'running', 'complete', 'failed', 'interrupted'
                )),
                error_code TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

    @staticmethod
    def _create_v11_ai_book_chat_summaries_table(connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_book_chat_summaries (
                book_id TEXT NOT NULL REFERENCES books(book_id) ON DELETE CASCADE,
                owner_user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                language TEXT NOT NULL CHECK(language IN ('en', 'zh-CN')),
                covered_turn_count INTEGER NOT NULL DEFAULT 0
                    CHECK(covered_turn_count >= 0),
                summary_text TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (book_id, owner_user_id, language)
            )
            """
        )

    @staticmethod
    def _assert_matching_row_counts(connection, source: str, target: str) -> None:
        source_count = connection.execute(
            f'SELECT COUNT(*) FROM "{source}"'
        ).fetchone()[0]
        target_count = connection.execute(
            f'SELECT COUNT(*) FROM "{target}"'
        ).fetchone()[0]
        if source_count != target_count:
            raise sqlite3.IntegrityError(
                f"schema v11 row-count mismatch: {source}={source_count}, "
                f"{target}={target_count}"
            )

    def _v11_rebuild_owned_state(self, connection) -> None:
        connection.execute("ALTER TABLE annotations RENAME TO annotations__v11_source")
        self._create_v11_annotations_table(connection)
        connection.execute(
            "INSERT INTO annotations (id, book_hash, chapter_index, text, note, "
            "start_meta, end_meta, color, created_at, updated_at, user_id) "
            "SELECT id, book_hash, chapter_index, text, note, start_meta, end_meta, "
            "color, created_at, updated_at, user_id FROM annotations__v11_source"
        )
        self._assert_matching_row_counts(
            connection, "annotations__v11_source", "annotations"
        )
        connection.execute("DROP TABLE annotations__v11_source")

        connection.execute("ALTER TABLE bookshelves RENAME TO bookshelves__v11_source")
        self._create_v11_bookshelves_table(connection)
        connection.execute(
            "INSERT INTO bookshelves (user_id, version, data, updated_at) "
            "SELECT user_id, version, data, updated_at "
            "FROM bookshelves__v11_source"
        )
        self._assert_matching_row_counts(
            connection, "bookshelves__v11_source", "bookshelves"
        )
        connection.execute("DROP TABLE bookshelves__v11_source")

        connection.execute(
            "ALTER TABLE reading_progress RENAME TO reading_progress__v11_source"
        )
        self._create_v11_reading_progress_table(connection)
        connection.execute(
            "INSERT INTO reading_progress (user_id, book_hash, chapter_index, "
            "updated_at) SELECT user_id, book_hash, chapter_index, updated_at "
            "FROM reading_progress__v11_source"
        )
        self._assert_matching_row_counts(
            connection, "reading_progress__v11_source", "reading_progress"
        )
        connection.execute("DROP TABLE reading_progress__v11_source")

    def _v11_rebuild_sessions(self, connection) -> None:
        connection.execute("ALTER TABLE sessions RENAME TO sessions__v11_source")
        self._validate_v11_session_epochs(connection)
        self._create_v11_sessions_table(connection)
        connection.execute(
            "INSERT INTO sessions (session_id, token_digest, user_id, expires_at, "
            "last_used_at, revoked_at, created_at, client_address, user_agent) "
            "SELECT session_id, token_digest, user_id, CAST(expires_at AS REAL), "
            "CAST(last_used_at AS REAL), CAST(revoked_at AS REAL), "
            "CAST(created_at AS REAL), client_address, user_agent "
            "FROM sessions__v11_source"
        )
        self._assert_matching_row_counts(
            connection, "sessions__v11_source", "sessions"
        )
        connection.execute("DROP TABLE sessions__v11_source")

    @staticmethod
    def _validate_v11_session_epochs(connection) -> None:
        rows = connection.execute(
            "SELECT session_id, expires_at, last_used_at, revoked_at, created_at "
            "FROM sessions__v11_source"
        ).fetchall()
        for row in rows:
            for column, value, nullable in zip(
                ("expires_at", "last_used_at", "revoked_at", "created_at"),
                row[1:],
                (False, False, True, False),
            ):
                if value is None and nullable:
                    continue
                if value is None:
                    raise sqlite3.IntegrityError(
                        f"schema v11 invalid session {column}: {row[0]}"
                    )
                try:
                    epoch = float(value)
                except (TypeError, ValueError) as error:
                    raise sqlite3.IntegrityError(
                        f"schema v11 invalid session {column}: {row[0]}"
                    ) from error
                cast_epoch = connection.execute(
                    "SELECT CAST(? AS REAL)", (value,)
                ).fetchone()[0]
                if (
                    not math.isfinite(epoch)
                    or not math.isfinite(float(cast_epoch))
                    or epoch != float(cast_epoch)
                ):
                    raise sqlite3.IntegrityError(
                        f"schema v11 invalid session {column}: {row[0]}"
                    )

    def _migrate_schema_v11(self, connection, source_version) -> None:
        if source_version >= 11:
            return
        self._reject_v11_source_tables(connection)
        self._v11_rebuild_owned_state(connection)
        self._v11_rebuild_sessions(connection)
        self._v11_rebuild_ai_state(connection)
        self._create_v11_indexes(connection)
        self._require_foreign_key_integrity(connection)
        connection.execute("PRAGMA user_version = 11")

    @staticmethod
    def _reject_v11_source_tables(connection) -> None:
        row = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' "
            "AND name GLOB '*__v11_source' ORDER BY name LIMIT 1"
        ).fetchone()
        if row is not None:
            raise sqlite3.IntegrityError(
                f"schema v11 reserved migration table exists: {row[0]}"
            )

    def _v11_rebuild_ai_state(self, connection) -> None:
        duplicate = connection.execute(
            "SELECT cache_key FROM ai_reading_jobs "
            "WHERE status IN ('queued', 'running') "
            "GROUP BY cache_key HAVING COUNT(*) > 1 LIMIT 1"
        ).fetchone()
        if duplicate is not None:
            raise sqlite3.IntegrityError(
                f"schema v11 duplicate active AI cache key: {duplicate[0]}"
            )
        orphan_turn = connection.execute(
            "SELECT ai_book_chat_turns.id FROM ai_book_chat_turns "
            "LEFT JOIN books ON books.book_id = ai_book_chat_turns.book_id "
            "WHERE books.book_id IS NULL LIMIT 1"
        ).fetchone()
        if orphan_turn is not None:
            raise sqlite3.IntegrityError(
                f"schema v11 orphan AI book chat turn: {orphan_turn[0]}"
            )
        orphan_summary = connection.execute(
            "SELECT ai_book_chat_summaries.book_id FROM ai_book_chat_summaries "
            "LEFT JOIN books ON books.book_id = ai_book_chat_summaries.book_id "
            "WHERE books.book_id IS NULL LIMIT 1"
        ).fetchone()
        if orphan_summary is not None:
            raise sqlite3.IntegrityError(
                f"schema v11 orphan AI book chat summary: {orphan_summary[0]}"
            )

        connection.execute(
            "ALTER TABLE ai_reading_jobs RENAME TO ai_reading_jobs__v11_source"
        )
        connection.execute(
            "UPDATE ai_reading_jobs__v11_source SET result_id = NULL "
            "WHERE result_id IS NOT NULL AND NOT EXISTS ("
            "SELECT 1 FROM ai_reading_results "
            "WHERE ai_reading_results.id = ai_reading_jobs__v11_source.result_id)"
        )
        self._create_v11_ai_reading_jobs_table(connection)
        connection.execute(
            "INSERT INTO ai_reading_jobs (id, owner_user_id, book_id, cache_key, "
            "request_json, profile, template_id, template_version, status, error_code, "
            "result_id, progress_current, progress_total, attempt_number, "
            "retried_from_job_id, retry_root_job_id, retried_by_user_id, created_at, "
            "updated_at) SELECT id, owner_user_id, book_id, cache_key, request_json, "
            "profile, template_id, template_version, status, error_code, result_id, "
            "progress_current, progress_total, 1, NULL, NULL, NULL, created_at, updated_at "
            "FROM ai_reading_jobs__v11_source"
        )
        self._assert_matching_row_counts(
            connection, "ai_reading_jobs__v11_source", "ai_reading_jobs"
        )
        connection.execute("DROP TABLE ai_reading_jobs__v11_source")

        connection.execute(
            "ALTER TABLE ai_book_chat_turns RENAME TO ai_book_chat_turns__v11_source"
        )
        self._create_v11_ai_book_chat_turns_table(connection)
        connection.execute(
            "INSERT INTO ai_book_chat_turns (id, book_id, chapter_index, result_id, "
            "context_mode, book_context, owner_user_id, question, language, answer, "
            "status, error_code, created_at, updated_at) SELECT id, book_id, "
            "chapter_index, result_id, context_mode, book_context, owner_user_id, "
            "question, language, answer, status, error_code, created_at, updated_at "
            "FROM ai_book_chat_turns__v11_source"
        )
        self._assert_matching_row_counts(
            connection, "ai_book_chat_turns__v11_source", "ai_book_chat_turns"
        )
        connection.execute("DROP TABLE ai_book_chat_turns__v11_source")

        connection.execute(
            "ALTER TABLE ai_book_chat_summaries "
            "RENAME TO ai_book_chat_summaries__v11_source"
        )
        self._create_v11_ai_book_chat_summaries_table(connection)
        connection.execute(
            "INSERT INTO ai_book_chat_summaries (book_id, owner_user_id, language, "
            "covered_turn_count, summary_text, updated_at) SELECT book_id, owner_user_id, "
            "language, covered_turn_count, summary_text, updated_at "
            "FROM ai_book_chat_summaries__v11_source"
        )
        self._assert_matching_row_counts(
            connection,
            "ai_book_chat_summaries__v11_source",
            "ai_book_chat_summaries",
        )
        connection.execute("DROP TABLE ai_book_chat_summaries__v11_source")

    @staticmethod
    def _require_foreign_key_integrity(connection) -> None:
        violations = connection.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            table, rowid, parent, foreign_key_id = violations[0]
            raise sqlite3.IntegrityError(
                "schema v11 foreign key violation: "
                f"{table} row {rowid} -> {parent} ({foreign_key_id})"
            )

    @staticmethod
    def _quote_identifier(identifier: str) -> str:
        return '"' + identifier.replace('"', '""') + '"'

    @staticmethod
    def _normalize_index_predicate(predicate: Optional[str]) -> Optional[str]:
        if predicate is None:
            return None
        return re.sub(r"\s+", " ", predicate.strip())

    @staticmethod
    def _index_contract(connection, index_name: str):
        row = connection.execute(
            "SELECT tbl_name, sql FROM sqlite_master "
            "WHERE type = 'index' AND name = ?",
            (index_name,),
        ).fetchone()
        if row is None:
            return None
        table, sql = row
        quoted_table = StateStore._quote_identifier(table)
        index_row = next(
            (
                listed
                for listed in connection.execute(f"PRAGMA index_list({quoted_table})")
                if listed[1] == index_name
            ),
            None,
        )
        if index_row is None:
            raise sqlite3.IntegrityError(
                f"schema v11 index metadata missing: {index_name}"
            )
        quoted_index = StateStore._quote_identifier(index_name)
        columns = tuple(
            (listed[2], bool(listed[3]))
            for listed in connection.execute(f"PRAGMA index_xinfo({quoted_index})")
            if listed[5]
        )
        predicate_match = re.search(
            r"\bWHERE\b(.*)$",
            sql or "",
            re.IGNORECASE | re.DOTALL,
        )
        predicate = StateStore._normalize_index_predicate(
            predicate_match.group(1) if predicate_match else None
        )
        return table, bool(index_row[2]), bool(index_row[4]), columns, predicate

    @staticmethod
    def _index_key_collations(connection, index_name: str):
        quoted_index = StateStore._quote_identifier(index_name)
        return tuple(
            str(listed[4]).upper()
            for listed in connection.execute(f"PRAGMA index_xinfo({quoted_index})")
            if listed[5]
        )

    @staticmethod
    def _create_v11_indexes(connection) -> None:
        existing_indexes = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index'"
            )
        }
        for index in (
            "idx_books_active",
            "idx_annotations_chapter_user_id",
            "idx_annotations_book_user_id",
            "idx_annotations_user_id",
            "idx_bookshelves_user_id",
            "idx_reading_progress_user_id",
            "idx_sessions_user_id",
            "idx_ai_reading_jobs_owner",
            "idx_ai_reading_jobs_active_cache",
            "idx_ai_reading_results_book",
            "idx_ai_reading_followups_owner",
            "idx_ai_book_chat_turns_owner_book",
        ):
            if index in existing_indexes:
                connection.execute(
                    f"DROP INDEX {StateStore._quote_identifier(index)}"
                )
        for name, table, unique, columns, predicate in _V11_INDEX_CONTRACTS:
            expected = (
                table,
                unique,
                predicate is not None,
                columns,
                StateStore._normalize_index_predicate(predicate),
            )
            actual = StateStore._index_contract(connection, name)
            expected_collations = ("BINARY",) * len(columns)
            if (
                actual == expected
                and StateStore._index_key_collations(connection, name)
                == expected_collations
            ):
                continue
            if actual is not None:
                connection.execute(
                    f"DROP INDEX {StateStore._quote_identifier(name)}"
                )
            column_sql = ", ".join(
                StateStore._quote_identifier(column) + (" DESC" if descending else "")
                for column, descending in columns
            )
            statement = (
                "CREATE "
                + ("UNIQUE " if unique else "")
                + f"INDEX {StateStore._quote_identifier(name)} "
                + f"ON {StateStore._quote_identifier(table)}({column_sql})"
            )
            if predicate is not None:
                statement += f" WHERE {predicate}"
            connection.execute(statement)
            if (
                StateStore._index_contract(connection, name) != expected
                or StateStore._index_key_collations(connection, name)
                != expected_collations
            ):
                raise sqlite3.IntegrityError(
                    f"schema v11 index contract mismatch: {name}"
                )

    @staticmethod
    def _validate_password_hashes(connection) -> None:
        rows = connection.execute(
            "SELECT password_hash FROM users WHERE password_hash IS NOT NULL"
        ).fetchall()
        try:
            for row in rows:
                validate_password_hash(row["password_hash"])
        except ValueError as error:
            raise RuntimeError(
                "Authoritative account store contains an invalid password hash"
            ) from error

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

    def _migrate_ai_settings_constraints(self, connection) -> None:
        """Expand immutable SQLite AI-settings constraints without losing settings."""
        definition = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'ai_settings'"
        ).fetchone()["sql"]
        if (
            "BETWEEN 5 AND 3600" in definition
            and "model_context_window INTEGER NOT NULL" in definition
            and "BETWEEN 2048 AND 100000000" in definition
            and "chat_context_tokens" not in definition
        ):
            return
        temporary_table = "ai_settings_constraints_migration"
        self._reject_migration_table(connection, temporary_table)
        connection.execute(
            f"""
            CREATE TABLE {temporary_table} (
                singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
                enabled INTEGER NOT NULL DEFAULT 0 CHECK(enabled IN (0, 1)),
                base_url TEXT NOT NULL DEFAULT '',
                api_key TEXT NOT NULL DEFAULT '',
                model TEXT NOT NULL DEFAULT '',
                timeout_seconds INTEGER NOT NULL DEFAULT 60
                    CHECK(timeout_seconds BETWEEN 5 AND 3600),
                model_context_window INTEGER NOT NULL DEFAULT 32768
                    CHECK(model_context_window BETWEEN 2048 AND 100000000),
                max_concurrency INTEGER NOT NULL DEFAULT 2
                    CHECK(max_concurrency BETWEEN 1 AND 4),
                daily_limit INTEGER NOT NULL DEFAULT 20
                    CHECK(daily_limit >= 0),
                config_revision INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            f"""
            INSERT INTO {temporary_table} (
                singleton, enabled, base_url, api_key, model, timeout_seconds,
                model_context_window, max_concurrency, daily_limit, config_revision, updated_at
            )
            SELECT singleton, enabled, base_url, api_key, model, timeout_seconds,
                   model_context_window, max_concurrency, daily_limit, config_revision, updated_at
            FROM ai_settings
            """
        )
        connection.execute("DROP TABLE ai_settings")
        connection.execute(f"ALTER TABLE {temporary_table} RENAME TO ai_settings")

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
        administrator_id: str,
    ) -> None:
        self._get_user(connection, administrator_id)
        self._migrate_annotations(connection, administrator_id)
        self._migrate_bookshelves(connection, administrator_id)
        self._migrate_reading_progress(connection, administrator_id)

    def _migrate_annotations(self, connection, administrator_id: str) -> None:
        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(annotations)").fetchall()
        }
        if "user_id" in columns:
            return
        temporary_table = "annotations_ownership_v2_migrating"
        self._reject_migration_table(connection, temporary_table)
        connection.execute(
            f"""
            CREATE TABLE {temporary_table} (
                id TEXT NOT NULL,
                username TEXT NOT NULL DEFAULT '',
                user_id TEXT NOT NULL CHECK(length(user_id) > 0)
                    REFERENCES users(id) ON DELETE CASCADE,
                book_hash TEXT NOT NULL,
                chapter_index INTEGER NOT NULL,
                text TEXT NOT NULL,
                note TEXT,
                start_meta TEXT,
                end_meta TEXT,
                color TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (user_id, id)
            )
            """
        )
        connection.execute(
            f"""
            INSERT INTO {temporary_table} (
                id, username, user_id, book_hash, chapter_index, text, note,
                start_meta, end_meta, color, created_at, updated_at
            )
            SELECT id, username, ?, book_hash, chapter_index, text, note,
                   start_meta, end_meta, color, created_at, updated_at
            FROM annotations
            """,
            (administrator_id,),
        )
        connection.execute("DROP TABLE annotations")
        connection.execute(
            f"ALTER TABLE {temporary_table} RENAME TO annotations"
        )

    def _migrate_annotation_primary_key(self, connection) -> None:
        columns = connection.execute("PRAGMA table_info(annotations)").fetchall()
        primary_key = tuple(
            row["name"]
            for row in sorted(columns, key=lambda row: row["pk"])
            if row["pk"]
        )
        if primary_key == ("user_id", "id"):
            return
        temporary_table = "annotations_owner_key_v3_migrating"
        self._reject_migration_table(connection, temporary_table)
        connection.execute(
            f"""
            CREATE TABLE {temporary_table} (
                id TEXT NOT NULL,
                username TEXT NOT NULL DEFAULT '',
                user_id TEXT NOT NULL CHECK(length(user_id) > 0)
                    REFERENCES users(id) ON DELETE CASCADE,
                book_hash TEXT NOT NULL,
                chapter_index INTEGER NOT NULL,
                text TEXT NOT NULL,
                note TEXT,
                start_meta TEXT,
                end_meta TEXT,
                color TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (user_id, id)
            )
            """
        )
        connection.execute(
            f"""
            INSERT INTO {temporary_table} (
                id, username, user_id, book_hash, chapter_index, text, note,
                start_meta, end_meta, color, created_at, updated_at
            )
            SELECT id, username, user_id, book_hash, chapter_index, text, note,
                   start_meta, end_meta, color, created_at, updated_at
            FROM annotations
            """
        )
        connection.execute("DROP TABLE annotations")
        connection.execute(
            f"ALTER TABLE {temporary_table} RENAME TO annotations"
        )

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
        administrator_id: str,
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
                user_id TEXT NOT NULL PRIMARY KEY CHECK(length(user_id) > 0)
                    REFERENCES users(id) ON DELETE CASCADE,
                username TEXT NOT NULL DEFAULT '',
                version INTEGER NOT NULL,
                data TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            f"""
            INSERT INTO {temporary_table} (
                user_id, username, version, data, updated_at
            )
            SELECT ?, username, version, data,
                   COALESCE(updated_at, CURRENT_TIMESTAMP)
            FROM bookshelves
            ORDER BY version DESC, updated_at DESC, username ASC
            LIMIT 1
            """,
            (administrator_id,),
        )
        connection.execute("DROP TABLE bookshelves")
        connection.execute(
            f"ALTER TABLE {temporary_table} RENAME TO bookshelves"
        )

    def _migrate_reading_progress(
        self,
        connection,
        administrator_id: str,
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
                user_id TEXT NOT NULL CHECK(length(user_id) > 0)
                    REFERENCES users(id) ON DELETE CASCADE,
                username TEXT NOT NULL DEFAULT '',
                book_hash TEXT NOT NULL,
                chapter_index INTEGER NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, book_hash)
            )
            """
        )
        connection.execute(
            f"""
            INSERT INTO {temporary_table} (
                user_id, username, book_hash, chapter_index, updated_at
            )
            SELECT ?, current.username, current.book_hash,
                   current.chapter_index,
                   COALESCE(current.updated_at, CURRENT_TIMESTAMP)
            FROM reading_progress AS current
            WHERE NOT EXISTS (
                SELECT 1
                FROM reading_progress AS preferred
                WHERE preferred.book_hash = current.book_hash
                  AND (
                    preferred.updated_at > current.updated_at
                    OR (
                        preferred.updated_at = current.updated_at
                        AND preferred.username < current.username
                    )
                  )
            )
            """,
            (administrator_id,),
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
            administrator = self._administrator(connection)
            if administrator is None:
                return self._bootstrap_admin(
                    connection,
                    username,
                    password_hash,
                ).principal
            if not self._administrator_is_pending(
                connection,
                administrator.user_id,
            ):
                raise RuntimeError("An administrator already exists")
            return self._complete_pending_administrator(
                connection,
                administrator.user_id,
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
            columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(users)").fetchall()
            }
            pending_clause = (
                " AND setup_pending = 0"
                if "setup_pending" in columns
                else ""
            )
            return connection.execute(
                "SELECT 1 FROM users WHERE role = 'admin'"
                + pending_clause
                + " LIMIT 1"
            ).fetchone() is not None

    def complete_administrator_setup(
        self,
        username: str,
        password_hash: str,
        token_digest_value: str,
        expires_at,
        *,
        now=None,
        client_address=None,
        user_agent=None,
    ) -> Principal:
        normalized = self._normalize_username(username)
        if not isinstance(password_hash, str) or not password_hash:
            raise ValueError("Password hash must not be empty")
        self._validate_session_digest(token_digest_value)
        created_at = self._timestamp(now)
        expiry = self._timestamp(expires_at)
        if expiry <= created_at:
            raise ValueError("Session expiry must be in the future")
        session_id = uuid.uuid4().hex
        client_address, user_agent = self._session_client_metadata(
            client_address,
            user_agent,
        )
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            pending = connection.execute(
                """
                SELECT id FROM users
                WHERE role = 'admin' AND setup_pending = 1
                ORDER BY created_at, id
                """
            ).fetchall()
            if not pending:
                raise SetupAlreadyCompleteError("Administrator setup is complete")
            if len(pending) != 1:
                raise RuntimeError("Invalid pending administrator state")
            user_id = pending[0]["id"]
            connection.execute(
                """
                UPDATE users
                SET username = ?, enabled = 1, password_hash = ?,
                    setup_pending = 0, updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND setup_pending = 1
                """,
                (normalized, password_hash, user_id),
            )
            connection.execute(
                """
                INSERT INTO sessions (
                    session_id, token_digest, user_id, expires_at,
                    last_used_at, revoked_at, created_at,
                    client_address, user_agent
                ) VALUES (?, ?, ?, ?, ?, NULL, ?, ?, ?)
                """,
                (
                    session_id,
                    token_digest_value,
                    user_id,
                    expiry,
                    created_at,
                    created_at,
                    client_address,
                    user_agent,
                ),
            )
            return self._get_user(connection, user_id).principal

    @staticmethod
    def _validate_session_digest(token_digest_value: str) -> None:
        if (
            not isinstance(token_digest_value, str)
            or len(token_digest_value) != 64
            or any(
                character not in "0123456789abcdef"
                for character in token_digest_value
            )
        ):
            raise ValueError(
                "Session token digest must be a SHA-256 hexadecimal digest"
            )

    @staticmethod
    def _session_client_metadata(client_address, user_agent):
        address = (
            client_address.strip()[:128]
            if isinstance(client_address, str) and client_address.strip()
            else None
        )
        agent = (
            user_agent.strip()[:512]
            if isinstance(user_agent, str) and user_agent.strip()
            else None
        )
        return address, agent

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

    def _create_pending_administrator(self, connection) -> UserRecord:
        user_id = uuid.uuid4().hex
        connection.execute(
            """
            INSERT INTO users (
                id, username, role, enabled, password_hash, setup_pending
            ) VALUES (?, ?, 'admin', 0, NULL, 1)
            """,
            (user_id, "__epub_browser_setup_" + user_id),
        )
        return self._get_user(connection, user_id)

    def _complete_pending_administrator(
        self,
        connection,
        user_id: str,
        username: str,
        password_hash: str,
    ) -> UserRecord:
        normalized = self._normalize_username(username)
        connection.execute(
            """
            UPDATE users
            SET username = ?, enabled = 1, password_hash = ?,
                setup_pending = 0, updated_at = CURRENT_TIMESTAMP
            WHERE id = ? AND role = 'admin' AND setup_pending = 1
            """,
            (normalized, password_hash, user_id),
        )
        return self._get_user(connection, user_id)

    @staticmethod
    def _administrator_is_pending(connection, user_id: str) -> bool:
        return connection.execute(
            """
            SELECT 1 FROM users
            WHERE id = ? AND role = 'admin' AND setup_pending = 1
            """,
            (user_id,),
        ).fetchone() is not None

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

    @staticmethod
    def _require_user(connection, user_id: str) -> None:
        if not isinstance(user_id, str) or not user_id.strip():
            raise ValueError("User ID must not be empty")
        if connection.execute(
            "SELECT 1 FROM users WHERE id = ?",
            (user_id,),
        ).fetchone() is None:
            raise KeyError(f"Unknown user ID: {user_id}")

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
        return self.update_user(user_id, enabled=enabled)

    def update_user(
        self,
        user_id: str,
        *,
        enabled: Optional[bool] = None,
        role: Optional[str] = None,
        revoke_sessions: bool = False,
    ) -> UserRecord:
        if enabled is not None and not isinstance(enabled, bool):
            raise ValueError("Enabled must be a boolean")
        if role is not None and role not in {"admin", "member"}:
            raise ValueError(f"Unsupported user role: {role}")
        if not isinstance(revoke_sessions, bool):
            raise ValueError("Revoke sessions must be a boolean")
        timestamp = str(self._timestamp())
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            user = self._get_user(connection, user_id)
            next_enabled = user.enabled if enabled is None else enabled
            next_role = user.role if role is None else role
            if (
                user.enabled
                and user.role == "admin"
                and (not next_enabled or next_role != "admin")
            ):
                other_enabled_admin = connection.execute(
                    """
                    SELECT 1 FROM users
                    WHERE id != ? AND role = 'admin' AND enabled = 1
                    LIMIT 1
                    """,
                    (user_id,),
                ).fetchone()
                if other_enabled_admin is None:
                    raise RuntimeError(
                        "The last enabled administrator cannot be disabled or demoted"
                    )
            connection.execute(
                """
                UPDATE users
                SET enabled = ?, role = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (int(next_enabled), next_role, user_id),
            )
            if (enabled is False) or revoke_sessions:
                connection.execute(
                    """
                    UPDATE sessions SET revoked_at = ?
                    WHERE user_id = ? AND revoked_at IS NULL
                    """,
                    (timestamp, user_id),
                )
            return self._get_user(connection, user_id)

    def set_password_hash_and_revoke_sessions(
        self,
        user_id: str,
        password_hash: str,
    ) -> UserRecord:
        timestamp = str(self._timestamp())
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._require_user(connection, user_id)
            connection.execute(
                """
                UPDATE users
                SET password_hash = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (password_hash, user_id),
            )
            connection.execute(
                """
                UPDATE sessions SET revoked_at = ?
                WHERE user_id = ? AND revoked_at IS NULL
                """,
                (timestamp, user_id),
            )
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

    @staticmethod
    def _timestamp(value=None) -> float:
        if value is None:
            return time.time()
        if isinstance(value, datetime):
            return value.timestamp()
        return float(value)

    @staticmethod
    def _require_identity_key(issuer: str, subject: str) -> None:
        if not isinstance(issuer, str) or not issuer.strip():
            raise ValueError("Identity issuer must not be empty")
        if not isinstance(subject, str) or not subject.strip():
            raise ValueError("Identity subject must not be empty")

    @staticmethod
    def _identity_record(row) -> UserIdentityRecord:
        return UserIdentityRecord(
            issuer=row["issuer"],
            subject=row["subject"],
            user_id=row["user_id"],
            display_name=row["display_name"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def create_identity(
        self,
        issuer: str,
        subject: str,
        user_id: str,
        display_name: Optional[str] = None,
    ) -> UserIdentityRecord:
        self._require_identity_key(issuer, subject)
        with self._connection() as connection:
            self._require_user(connection, user_id)
            connection.execute(
                """
                INSERT INTO user_identities (issuer, subject, user_id, display_name)
                VALUES (?, ?, ?, ?)
                """,
                (issuer, subject, user_id, display_name),
            )
            row = connection.execute(
                "SELECT * FROM user_identities WHERE issuer = ? AND subject = ?",
                (issuer, subject),
            ).fetchone()
        return self._identity_record(row)

    def get_identity(
        self,
        issuer: str,
        subject: str,
    ) -> Optional[UserIdentityRecord]:
        self._require_identity_key(issuer, subject)
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM user_identities WHERE issuer = ? AND subject = ?",
                (issuer, subject),
            ).fetchone()
        return self._identity_record(row) if row is not None else None

    def update_identity(
        self,
        issuer: str,
        subject: str,
        *,
        display_name: Optional[str],
    ) -> UserIdentityRecord:
        self._require_identity_key(issuer, subject)
        with self._connection() as connection:
            cursor = connection.execute(
                """
                UPDATE user_identities
                SET display_name = ?, updated_at = CURRENT_TIMESTAMP
                WHERE issuer = ? AND subject = ?
                """,
                (display_name, issuer, subject),
            )
            if cursor.rowcount != 1:
                raise KeyError("Unknown external identity")
            row = connection.execute(
                "SELECT * FROM user_identities WHERE issuer = ? AND subject = ?",
                (issuer, subject),
            ).fetchone()
        return self._identity_record(row)

    def delete_identity(self, issuer: str, subject: str) -> bool:
        self._require_identity_key(issuer, subject)
        with self._connection() as connection:
            cursor = connection.execute(
                "DELETE FROM user_identities WHERE issuer = ? AND subject = ?",
                (issuer, subject),
            )
        return cursor.rowcount == 1

    def list_identities(self, user_id: str) -> tuple[UserIdentityRecord, ...]:
        with self._connection() as connection:
            self._require_user(connection, user_id)
            rows = connection.execute(
                """
                SELECT * FROM user_identities
                WHERE user_id = ?
                ORDER BY issuer, subject
                """,
                (user_id,),
            ).fetchall()
        return tuple(self._identity_record(row) for row in rows)

    def list_all_identities(self) -> tuple[UserIdentityRecord, ...]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT * FROM user_identities
                ORDER BY issuer, subject, user_id
                """
            ).fetchall()
        return tuple(self._identity_record(row) for row in rows)

    def principal_from_identity(
        self,
        issuer: str,
        subject: str,
    ) -> Optional[Principal]:
        self._require_identity_key(issuer, subject)
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT users.id AS user_id, users.username, users.role
                FROM user_identities
                JOIN users ON users.id = user_identities.user_id
                WHERE user_identities.issuer = ?
                  AND user_identities.subject = ?
                  AND users.enabled = 1
                """,
                (issuer, subject),
            ).fetchone()
        if row is None:
            return None
        return Principal(row["user_id"], row["username"], row["role"])

    def create_session(
        self,
        token_digest_value: str,
        user_id: str,
        expires_at,
        *,
        now=None,
        client_address=None,
        user_agent=None,
    ) -> str:
        self._validate_session_digest(token_digest_value)
        created_at = self._timestamp(now)
        expiry = self._timestamp(expires_at)
        if expiry <= created_at:
            raise ValueError("Session expiry must be in the future")
        session_id = uuid.uuid4().hex
        client_address, user_agent = self._session_client_metadata(
            client_address,
            user_agent,
        )
        with self._connection() as connection:
            self._require_user(connection, user_id)
            connection.execute(
                """
                INSERT INTO sessions (
                    session_id, token_digest, user_id, expires_at,
                    last_used_at, revoked_at, created_at,
                    client_address, user_agent
                ) VALUES (?, ?, ?, ?, ?, NULL, ?, ?, ?)
                """,
                (
                    session_id,
                    token_digest_value,
                    user_id,
                    expiry,
                    created_at,
                    created_at,
                    client_address,
                    user_agent,
                ),
            )
        return session_id

    def replace_session(
        self,
        replaced_raw_token: str,
        token_digest_value: str,
        user_id: str,
        expires_at,
        *,
        now=None,
        client_address=None,
        user_agent=None,
    ) -> str:
        """Insert a new session and revoke the current token in one transaction."""
        if not isinstance(replaced_raw_token, str) or not replaced_raw_token:
            raise ValueError("Replaced session token must not be empty")
        self._validate_session_digest(token_digest_value)
        created_at = self._timestamp(now)
        expiry = self._timestamp(expires_at)
        if expiry <= created_at:
            raise ValueError("Session expiry must be in the future")
        replaced_digest = token_digest(replaced_raw_token)
        session_id = uuid.uuid4().hex
        client_address, user_agent = self._session_client_metadata(
            client_address,
            user_agent,
        )
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._require_user(connection, user_id)
            current = connection.execute(
                """
                SELECT token_digest, expires_at, revoked_at
                FROM sessions WHERE token_digest = ?
                """,
                (replaced_digest,),
            ).fetchone()
            if (
                current is None
                or not hmac.compare_digest(
                    current["token_digest"],
                    replaced_digest,
                )
                or current["revoked_at"] is not None
                or float(current["expires_at"]) <= created_at
            ):
                raise ValueError("Current session is not replaceable")
            connection.execute(
                """
                UPDATE sessions SET revoked_at = ?
                WHERE token_digest = ? AND revoked_at IS NULL
                """,
                (created_at, replaced_digest),
            )
            connection.execute(
                """
                INSERT INTO sessions (
                    session_id, token_digest, user_id, expires_at,
                    last_used_at, revoked_at, created_at,
                    client_address, user_agent
                ) VALUES (?, ?, ?, ?, ?, NULL, ?, ?, ?)
                """,
                (
                    session_id,
                    token_digest_value,
                    user_id,
                    expiry,
                    created_at,
                    created_at,
                    client_address,
                    user_agent,
                ),
            )
        return session_id

    def principal_from_session(
        self,
        raw_token: Optional[str],
        *,
        now=None,
        ttl_seconds: int = 30 * 24 * 60 * 60,
    ) -> Optional[Principal]:
        if not isinstance(raw_token, str) or not raw_token:
            return None
        if ttl_seconds <= 0:
            raise ValueError("Session TTL must be positive")
        digest = token_digest(raw_token)
        used_at = self._timestamp(now)
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT sessions.token_digest, sessions.expires_at,
                       sessions.revoked_at, users.id AS user_id,
                       users.username, users.role, users.enabled
                FROM sessions
                JOIN users ON users.id = sessions.user_id
                WHERE sessions.token_digest = ?
                """,
                (digest,),
            ).fetchone()
            if row is None or not hmac.compare_digest(row["token_digest"], digest):
                return None
            if (
                row["revoked_at"] is not None
                or not bool(row["enabled"])
                or float(row["expires_at"]) <= used_at
            ):
                return None
            connection.execute(
                """
                UPDATE sessions
                SET expires_at = ?, last_used_at = ?
                WHERE token_digest = ?
                  AND revoked_at IS NULL
                """,
                (used_at + ttl_seconds, used_at, digest),
            )
        return Principal(row["user_id"], row["username"], row["role"])

    def revoke_session(self, session_id: str, *, revoked_at=None) -> bool:
        if not isinstance(session_id, str) or not session_id:
            return False
        timestamp = self._timestamp(revoked_at)
        with self._connection() as connection:
            cursor = connection.execute(
                """
                UPDATE sessions SET revoked_at = ?
                WHERE session_id = ? AND revoked_at IS NULL
                """,
                (timestamp, session_id),
            )
        return cursor.rowcount == 1

    def revoke_session_by_token(
        self,
        raw_token: Optional[str],
        *,
        revoked_at=None,
    ) -> bool:
        if not isinstance(raw_token, str) or not raw_token:
            return False
        digest = token_digest(raw_token)
        timestamp = self._timestamp(revoked_at)
        with self._connection() as connection:
            row = connection.execute(
                "SELECT token_digest FROM sessions WHERE token_digest = ?",
                (digest,),
            ).fetchone()
            if row is None or not hmac.compare_digest(row["token_digest"], digest):
                return False
            cursor = connection.execute(
                """
                UPDATE sessions SET revoked_at = ?
                WHERE token_digest = ? AND revoked_at IS NULL
                """,
                (timestamp, digest),
            )
        return cursor.rowcount == 1

    def revoke_all_sessions(self, user_id: str, *, revoked_at=None) -> int:
        timestamp = self._timestamp(revoked_at)
        with self._connection() as connection:
            self._require_user(connection, user_id)
            cursor = connection.execute(
                """
                UPDATE sessions SET revoked_at = ?
                WHERE user_id = ? AND revoked_at IS NULL
                """,
                (timestamp, user_id),
            )
        return cursor.rowcount

    @staticmethod
    def _session_record(row) -> SessionRecord:
        return SessionRecord(
            session_id=row["session_id"],
            user_id=row["user_id"],
            expires_at=row["expires_at"],
            last_used_at=row["last_used_at"],
            revoked_at=row["revoked_at"],
            created_at=row["created_at"],
            client_address=row["client_address"],
            user_agent=row["user_agent"],
        )

    def list_sessions(
        self,
        user_id: str,
        *,
        active_only: bool = False,
        now=None,
    ) -> tuple[SessionRecord, ...]:
        with self._connection() as connection:
            self._require_user(connection, user_id)
            conditions = ["user_id = ?"]
            parameters = [user_id]
            if active_only:
                conditions.extend(["revoked_at IS NULL", "expires_at > ?"])
                parameters.append(self._timestamp(now))
            rows = connection.execute(
                """
                SELECT session_id, user_id, expires_at, last_used_at,
                       revoked_at, created_at, client_address, user_agent
                FROM sessions
                WHERE """
                + " AND ".join(conditions)
                + " ORDER BY created_at DESC, session_id",
                tuple(parameters),
            ).fetchall()
        return tuple(self._session_record(row) for row in rows)

    def session_id_from_token(
        self,
        raw_token: Optional[str],
        *,
        user_id: Optional[str] = None,
    ) -> Optional[str]:
        if not isinstance(raw_token, str) or not raw_token:
            return None
        digest = token_digest(raw_token)
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT session_id, token_digest, user_id
                FROM sessions
                WHERE token_digest = ?
                """,
                (digest,),
            ).fetchone()
        if row is None or not hmac.compare_digest(row["token_digest"], digest):
            return None
        if user_id is not None and row["user_id"] != user_id:
            return None
        return row["session_id"]

    def revoke_user_session(
        self,
        user_id: str,
        session_id: str,
        *,
        revoked_at=None,
    ) -> bool:
        if not isinstance(session_id, str) or not session_id:
            return False
        timestamp = self._timestamp(revoked_at)
        with self._connection() as connection:
            self._require_user(connection, user_id)
            cursor = connection.execute(
                """
                UPDATE sessions SET revoked_at = ?
                WHERE session_id = ? AND user_id = ? AND revoked_at IS NULL
                """,
                (timestamp, session_id, user_id),
            )
        return cursor.rowcount == 1

    def raw_session_rows(self) -> tuple[str, ...]:
        """Expose persisted scalar values for security inspection tests."""
        with self._connection() as connection:
            rows = connection.execute("SELECT * FROM sessions").fetchall()
        return tuple(
            str(value)
            for row in rows
            for value in row
            if value is not None
        )

    def get_user(self, user_id: str) -> UserRecord:
        with self._connection() as connection:
            return self._get_user(connection, user_id)

    def get_book(self, book_id: str) -> BookRecord:
        with self._connection() as connection:
            return self._get_book(connection, book_id)

    @staticmethod
    def _validate_book_visibility(visibility: str) -> None:
        if visibility not in {"authenticated", "restricted"}:
            raise ValueError(f"Unsupported book visibility: {visibility}")

    def set_book_visibility(self, book_id: str, visibility: str) -> BookRecord:
        self._validate_book_visibility(visibility)
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
            return self._get_book(connection, book_id)

    @staticmethod
    def _normalized_bulk_book_ids(book_ids: Sequence[str]) -> tuple[str, ...]:
        normalized = tuple(dict.fromkeys(book_ids))
        if not normalized or len(normalized) != len(book_ids):
            raise ValueError("Bulk book IDs must be unique and non-empty")
        return normalized

    def _require_active_bulk_books(self, connection, book_ids: Sequence[str]) -> None:
        placeholders = ", ".join("?" for _ in book_ids)
        rows = connection.execute(
            "SELECT book_id FROM books WHERE active = 1 AND book_id IN (" + placeholders + ")",
            tuple(book_ids),
        ).fetchall()
        if len(rows) != len(book_ids):
            raise KeyError("One or more active books were not found")

    def bulk_set_book_visibility(
        self,
        book_ids: Sequence[str],
        visibility: str,
    ) -> tuple[str, ...]:
        """Atomically update visibility for a bounded set of active books."""
        self._validate_book_visibility(visibility)
        normalized_book_ids = self._normalized_bulk_book_ids(book_ids)
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._require_active_bulk_books(connection, normalized_book_ids)
            placeholders = ", ".join("?" for _ in normalized_book_ids)
            connection.execute(
                "UPDATE books SET visibility = ?, updated_at = CURRENT_TIMESTAMP "
                "WHERE active = 1 AND book_id IN (" + placeholders + ")",
                (visibility, *normalized_book_ids),
            )
            connection.execute("COMMIT")
        return normalized_book_ids

    def bulk_grant_book_access(
        self,
        book_ids: Sequence[str],
        user_ids: Sequence[str],
    ) -> tuple[str, ...]:
        """Atomically add member grants without replacing existing book access."""
        normalized_book_ids = self._normalized_bulk_book_ids(book_ids)
        normalized_user_ids = tuple(dict.fromkeys(user_ids))
        if not normalized_user_ids or len(normalized_user_ids) != len(user_ids):
            raise ValueError("Bulk grant user IDs must be unique and non-empty")
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._require_active_bulk_books(connection, normalized_book_ids)
            for user_id in normalized_user_ids:
                user = self._get_user(connection, user_id)
                if not user.enabled or user.role != "member":
                    raise ValueError("Bulk book access can only be granted to enabled members")
            connection.executemany(
                "INSERT INTO book_access (book_id, user_id) VALUES (?, ?) "
                "ON CONFLICT(book_id, user_id) DO NOTHING",
                (
                    (book_id, user_id)
                    for book_id in normalized_book_ids
                    for user_id in normalized_user_ids
                ),
            )
            connection.execute("COMMIT")
        return normalized_book_ids

    def grant_book_access(self, book_id: str, user_id: str) -> None:
        with self._connection() as connection:
            self._get_book(connection, book_id)
            user = self._get_user(connection, user_id)
            if not user.enabled:
                raise ValueError("Book access cannot be granted to a disabled user")
            connection.execute(
                """
                INSERT INTO book_access (book_id, user_id)
                VALUES (?, ?)
                ON CONFLICT(book_id, user_id) DO NOTHING
                """,
                (book_id, user_id),
            )

    def book_grants(self, book_id: str) -> tuple[str, ...]:
        with self._connection() as connection:
            self._get_book(connection, book_id)
            rows = connection.execute(
                "SELECT user_id FROM book_access WHERE book_id = ? "
                "ORDER BY user_id",
                (book_id,),
            ).fetchall()
        return tuple(row["user_id"] for row in rows)

    def replace_book_grants(
        self,
        book_id: str,
        user_ids: Sequence[str],
    ) -> tuple[str, ...]:
        """Atomically replace a book's explicit member grants."""
        with self._connection() as connection:
            return self._replace_book_grants(connection, book_id, user_ids)

    def _replace_book_grants(
        self,
        connection,
        book_id: str,
        user_ids: Sequence[str],
    ) -> tuple[str, ...]:
        normalized_user_ids = tuple(dict.fromkeys(user_ids))
        self._get_book(connection, book_id)
        for user_id in normalized_user_ids:
            user = self._get_user(connection, user_id)
            if not user.enabled:
                raise ValueError(
                    "Book access cannot be granted to a disabled user"
                )
            if user.role != "member":
                raise ValueError(
                    "Explicit book access can only be granted to members"
                )
        connection.execute(
            "DELETE FROM book_access WHERE book_id = ?",
            (book_id,),
        )
        connection.executemany(
            "INSERT INTO book_access (book_id, user_id) VALUES (?, ?)",
            ((book_id, user_id) for user_id in normalized_user_ids),
        )
        return tuple(sorted(normalized_user_ids))

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

    def get_ai_settings(self) -> dict:
        """Return the public administrator configuration without its API key."""
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT enabled, base_url, model, timeout_seconds, model_context_window, max_concurrency,
                       daily_limit, config_revision, api_key
                FROM ai_settings WHERE singleton = 1
                """
            ).fetchone()
        return {
            "enabled": bool(row["enabled"]),
            "base_url": row["base_url"],
            "model": row["model"],
            "timeout_seconds": row["timeout_seconds"],
            "model_context_window": row["model_context_window"],
            "max_concurrency": row["max_concurrency"],
            "daily_limit": row["daily_limit"],
            "config_revision": row["config_revision"],
            "api_key_configured": bool(row["api_key"]),
        }

    def _get_ai_provider_settings(self) -> dict:
        """Return the private Provider snapshot for server-side use only."""
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT enabled, base_url, api_key, model, timeout_seconds, model_context_window,
                       max_concurrency, daily_limit, config_revision
                FROM ai_settings WHERE singleton = 1
                """
            ).fetchone()
        return dict(row)

    def set_ai_settings(
        self,
        *,
        enabled: bool,
        base_url: str,
        api_key: Optional[str],
        model: str,
        timeout_seconds: int,
        max_concurrency: int,
        daily_limit: int,
        model_context_window: int = 32768,
        clear_api_key: bool = False,
    ) -> dict:
        if not isinstance(base_url, str) or (
            api_key is not None and not isinstance(api_key, str)
        ):
            raise ValueError("AI settings must be strings")
        if not isinstance(model, str):
            raise ValueError("AI model must be text")
        if not 5 <= int(timeout_seconds) <= 3600:
            raise ValueError("AI timeout is out of range")
        if not 2048 <= int(model_context_window) <= 100000000:
            raise ValueError("AI model context window is out of range")
        if not 1 <= int(max_concurrency) <= 4:
            raise ValueError("AI concurrency is out of range")
        if int(daily_limit) < 0:
            raise ValueError("AI daily limit is out of range")
        with self._connection() as connection:
            current = connection.execute(
                "SELECT api_key FROM ai_settings WHERE singleton = 1"
            ).fetchone()
            stored_key = "" if clear_api_key else (
                current["api_key"] if api_key is None else api_key
            )
            if enabled and (
                not base_url.strip() or not model.strip() or not stored_key
            ):
                raise ValueError(
                    "AI base URL, API key, and model are required when enabled"
                )
            connection.execute(
                """
                UPDATE ai_settings
                SET enabled = ?, base_url = ?, api_key = ?, model = ?,
                    timeout_seconds = ?, model_context_window = ?, max_concurrency = ?, daily_limit = ?,
                    config_revision = config_revision + 1,
                    updated_at = CURRENT_TIMESTAMP
                WHERE singleton = 1
                """,
                (
                    int(bool(enabled)),
                    base_url.strip(),
                    stored_key,
                    model.strip(),
                    int(timeout_seconds),
                    int(model_context_window),
                    int(max_concurrency),
                    int(daily_limit),
                ),
            )
        return self.get_ai_settings()

    def set_ai_user_access(
        self,
        user_id: str,
        *,
        enabled: bool,
        daily_limit: Optional[int] = None,
    ) -> None:
        if daily_limit is not None and int(daily_limit) < 0:
            raise ValueError("AI daily limit is out of range")
        with self._connection() as connection:
            user = self._get_user(connection, user_id)
            if user.role != "member":
                raise ValueError("AI member access can only be set for members")
            connection.execute(
                """
                INSERT INTO ai_user_access (user_id, enabled, daily_limit)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    enabled = excluded.enabled,
                    daily_limit = excluded.daily_limit,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (user_id, int(bool(enabled)), daily_limit),
            )

    def get_ai_user_access(self, user_id: str) -> dict:
        with self._connection() as connection:
            user = self._get_user(connection, user_id)
            if user.role == "admin":
                return {"enabled": True, "daily_limit": 0}
            row = connection.execute(
                "SELECT enabled, daily_limit FROM ai_user_access WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        return {
            "enabled": bool(row["enabled"]) if row is not None else False,
            "daily_limit": row["daily_limit"] if row is not None else None,
        }

    def list_ai_user_access(self) -> dict[str, dict]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT user_id, enabled, daily_limit FROM ai_user_access"
            ).fetchall()
        return {
            row["user_id"]: {
                "enabled": bool(row["enabled"]),
                "daily_limit": row["daily_limit"],
            }
            for row in rows
        }

    def can_use_ai(self, principal: Principal) -> bool:
        if principal.role == "admin":
            return True
        with self._connection() as connection:
            row = connection.execute(
                "SELECT enabled FROM ai_user_access WHERE user_id = ?",
                (principal.user_id,),
            ).fetchone()
        return row is not None and bool(row["enabled"])

    def ai_daily_limit(self, principal: Principal) -> int:
        if principal.role == "admin":
            return 0
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT COALESCE(ai_user_access.daily_limit, ai_settings.daily_limit)
                       AS daily_limit
                FROM ai_settings
                LEFT JOIN ai_user_access
                  ON ai_user_access.user_id = ?
                WHERE ai_settings.singleton = 1
                """,
                (principal.user_id,),
            ).fetchone()
        return int(row["daily_limit"])

    @staticmethod
    def _normalize_ai_tag(name: str) -> tuple[str, str]:
        if not isinstance(name, str):
            raise ValueError("AI tag must be text")
        display = unicodedata.normalize("NFKC", name).strip()
        if not display or len(display) > 80:
            raise ValueError("AI tag must contain 1 to 80 characters")
        return display.casefold(), display

    def create_ai_tag(self, name: str) -> dict:
        normalized, display = self._normalize_ai_tag(name)
        with self._connection() as connection:
            row = connection.execute(
                "SELECT id, normalized_name, name FROM ai_tags WHERE normalized_name = ?",
                (normalized,),
            ).fetchone()
            if row is None:
                tag_id = uuid.uuid4().hex
                connection.execute(
                    "INSERT INTO ai_tags (id, normalized_name, name) VALUES (?, ?, ?)",
                    (tag_id, normalized, display),
                )
                row = connection.execute(
                    "SELECT id, normalized_name, name FROM ai_tags WHERE id = ?",
                    (tag_id,),
                ).fetchone()
        return {"id": row["id"], "normalized_name": row["normalized_name"], "name": row["name"]}

    def list_ai_tags(self) -> tuple[dict, ...]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT ai_tags.id, ai_tags.normalized_name, ai_tags.name,
                       COUNT(books.book_id) AS book_count
                FROM ai_tags
                LEFT JOIN book_ai_tags ON book_ai_tags.tag_id = ai_tags.id
                LEFT JOIN books ON books.book_id = book_ai_tags.book_id AND books.active = 1
                GROUP BY ai_tags.id, ai_tags.normalized_name, ai_tags.name
                ORDER BY ai_tags.normalized_name, ai_tags.id
                """
            ).fetchall()
        return tuple(
            {
                "id": row["id"],
                "normalized_name": row["normalized_name"],
                "name": row["name"],
                "book_count": int(row["book_count"]),
            }
            for row in rows
        )

    def rename_ai_tag(self, tag_id: str, name: str) -> dict:
        normalized, display = self._normalize_ai_tag(name)
        with self._connection() as connection:
            try:
                cursor = connection.execute(
                    """
                    UPDATE ai_tags SET normalized_name = ?, name = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (normalized, display, tag_id),
                )
            except sqlite3.IntegrityError as error:
                raise ValueError("AI tag already exists") from error
            if cursor.rowcount != 1:
                raise KeyError("Unknown AI tag")
            row = connection.execute(
                "SELECT id, normalized_name, name FROM ai_tags WHERE id = ?",
                (tag_id,),
            ).fetchone()
        return {"id": row["id"], "normalized_name": row["normalized_name"], "name": row["name"]}

    def delete_ai_tag(self, tag_id: str) -> bool:
        with self._connection() as connection:
            cursor = connection.execute("DELETE FROM ai_tags WHERE id = ?", (tag_id,))
        return cursor.rowcount == 1

    def book_ai_tags(self, book_id: str) -> tuple[dict, ...]:
        with self._connection() as connection:
            return self._book_ai_tags(connection, book_id)

    def _book_ai_tags(self, connection, book_id: str) -> tuple[dict, ...]:
        self._get_book(connection, book_id)
        rows = connection.execute(
            """
            SELECT ai_tags.id, ai_tags.normalized_name, ai_tags.name
            FROM book_ai_tags JOIN ai_tags ON ai_tags.id = book_ai_tags.tag_id
            WHERE book_ai_tags.book_id = ?
            ORDER BY ai_tags.normalized_name, ai_tags.id
            """,
            (book_id,),
        ).fetchall()
        return tuple(
            {"id": row["id"], "normalized_name": row["normalized_name"], "name": row["name"]}
            for row in rows
        )

    def replace_book_ai_tags(self, book_id: str, tag_ids: Sequence[str]) -> tuple[dict, ...]:
        with self._connection() as connection:
            return self._replace_book_ai_tags(connection, book_id, tag_ids)

    def _replace_book_ai_tags(
        self,
        connection,
        book_id: str,
        tag_ids: Sequence[str],
    ) -> tuple[dict, ...]:
        unique_ids = tuple(dict.fromkeys(tag_ids))
        self._get_book(connection, book_id)
        for tag_id in unique_ids:
            if connection.execute(
                "SELECT 1 FROM ai_tags WHERE id = ?", (tag_id,)
            ).fetchone() is None:
                raise KeyError("Unknown AI tag")
        connection.execute("DELETE FROM book_ai_tags WHERE book_id = ?", (book_id,))
        connection.executemany(
            "INSERT INTO book_ai_tags (book_id, tag_id) VALUES (?, ?)",
            ((book_id, tag_id) for tag_id in unique_ids),
        )
        return self._book_ai_tags(connection, book_id)

    def effective_book_tags(self, book_id: str) -> tuple[str, ...]:
        with self._connection() as connection:
            book = self._get_book(connection, book_id)
        metadata = json.loads(book.metadata_json)
        merged = {}
        for name in tuple(metadata.get("tags") or ()) + tuple(
            item["name"] for item in self.book_ai_tags(book_id)
        ):
            try:
                normalized, display = self._normalize_ai_tag(name)
            except ValueError:
                continue
            merged.setdefault(normalized, display)
        return tuple(sorted(merged.values(), key=str.casefold))

    def set_book_ai_profile(self, book_id: str, profile: str) -> None:
        with self._connection() as connection:
            self._set_book_ai_profile(connection, book_id, profile)

    def _set_book_ai_profile(
        self,
        connection,
        book_id: str,
        profile: str,
    ) -> str:
        if profile not in {"auto", "technical", "fiction", "general"}:
            raise ValueError("Unsupported AI profile")
        self._get_book(connection, book_id)
        connection.execute(
            """
            INSERT INTO book_ai_profiles (book_id, profile)
            VALUES (?, ?)
            ON CONFLICT(book_id) DO UPDATE SET
                profile = excluded.profile,
                updated_at = CURRENT_TIMESTAMP
            """,
            (book_id, profile),
        )
        return profile

    def get_book_ai_profile(self, book_id: str) -> str:
        with self._connection() as connection:
            self._get_book(connection, book_id)
            row = connection.execute(
                "SELECT profile FROM book_ai_profiles WHERE book_id = ?",
                (book_id,),
            ).fetchone()
        return row["profile"] if row is not None else "auto"

    @staticmethod
    def _admin_book_metadata(metadata_json: str) -> tuple[str, list[str], list[str]]:
        try:
            metadata = json.loads(metadata_json)
        except (TypeError, ValueError):
            metadata = {}
        if not isinstance(metadata, dict):
            metadata = {}
        title = metadata.get("title")
        if not isinstance(title, str) or not title.strip():
            title = "EPUB Book"
        authors = metadata.get("authors")
        if not isinstance(authors, list):
            authors = []
        epub_tags = metadata.get("tags")
        if not isinstance(epub_tags, list):
            epub_tags = []
        return (
            title,
            [author for author in authors if isinstance(author, str)],
            [tag for tag in epub_tags if isinstance(tag, str)],
        )

    @classmethod
    def _admin_book_summary_mapping(
        cls,
        book_row,
        *,
        grant_count: int = 0,
        profile: str = "auto",
        tags: Sequence[dict] = (),
        result_count: int = 0,
    ) -> dict:
        title, authors, epub_tags = cls._admin_book_metadata(
            book_row["metadata_json"]
        )
        return {
            "id": book_row["book_id"],
            "title": title,
            "authors": authors,
            "epub_tags": epub_tags,
            "visibility": book_row["visibility"],
            "grant_count": int(grant_count),
            "ai_profile": profile,
            "ai_tags": [
                {"id": tag["id"], "name": tag["name"]}
                for tag in tags
            ],
            "ai_result_count": int(result_count),
            "updated_at": book_row["updated_at"],
        }

    def list_admin_book_summaries(self) -> tuple[dict, ...]:
        """Return privacy-safe active-book summaries using bounded queries."""
        with self._connection() as connection:
            books = connection.execute(
                """
                SELECT book_id, metadata_json, visibility, updated_at
                FROM books
                WHERE active = 1
                ORDER BY book_id
                """
            ).fetchall()
            grant_counts = {
                row["book_id"]: row["grant_count"]
                for row in connection.execute(
                    """
                    SELECT book_access.book_id, COUNT(*) AS grant_count
                    FROM book_access
                    JOIN books ON books.book_id = book_access.book_id
                    WHERE books.active = 1
                    GROUP BY book_access.book_id
                    """
                ).fetchall()
            }
            profiles = {
                row["book_id"]: row["profile"]
                for row in connection.execute(
                    """
                    SELECT book_ai_profiles.book_id, book_ai_profiles.profile
                    FROM book_ai_profiles
                    JOIN books ON books.book_id = book_ai_profiles.book_id
                    WHERE books.active = 1
                    """
                ).fetchall()
            }
            tags_by_book = {}
            for row in connection.execute(
                """
                SELECT book_ai_tags.book_id, ai_tags.id, ai_tags.name
                FROM book_ai_tags
                JOIN ai_tags ON ai_tags.id = book_ai_tags.tag_id
                JOIN books ON books.book_id = book_ai_tags.book_id
                WHERE books.active = 1
                ORDER BY book_ai_tags.book_id, ai_tags.normalized_name, ai_tags.id
                """
            ).fetchall():
                tags_by_book.setdefault(row["book_id"], []).append(
                    {"id": row["id"], "name": row["name"]}
                )
            result_counts = {
                row["book_id"]: row["result_count"]
                for row in connection.execute(
                    """
                    SELECT ai_reading_results.book_id, COUNT(*) AS result_count
                    FROM ai_reading_results
                    JOIN books ON books.book_id = ai_reading_results.book_id
                    WHERE books.active = 1
                    GROUP BY ai_reading_results.book_id
                    """
                ).fetchall()
            }
        return tuple(
            self._admin_book_summary_mapping(
                book,
                grant_count=grant_counts.get(book["book_id"], 0),
                profile=profiles.get(book["book_id"], "auto"),
                tags=tags_by_book.get(book["book_id"], ()),
                result_count=result_counts.get(book["book_id"], 0),
            )
            for book in books
        )

    @staticmethod
    def _active_admin_book_row(connection, book_id: str):
        row = connection.execute(
            """
            SELECT book_id, metadata_json, visibility, updated_at
            FROM books
            WHERE book_id = ? AND active = 1
            """,
            (book_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"Unknown active book ID: {book_id}")
        return row

    @classmethod
    def _effective_admin_book_tags(
        cls,
        epub_tags: Sequence[str],
        ai_tags: Sequence[dict],
    ) -> tuple[str, ...]:
        merged = {}
        for name in tuple(epub_tags) + tuple(tag["name"] for tag in ai_tags):
            try:
                normalized, display = cls._normalize_ai_tag(name)
            except ValueError:
                continue
            merged.setdefault(normalized, display)
        return tuple(sorted(merged.values(), key=str.casefold))

    def _admin_book_detail(self, connection, book_row) -> dict:
        book_id = book_row["book_id"]
        grants = tuple(
            row["user_id"]
            for row in connection.execute(
                "SELECT user_id FROM book_access WHERE book_id = ? ORDER BY user_id",
                (book_id,),
            ).fetchall()
        )
        profile_row = connection.execute(
            "SELECT profile FROM book_ai_profiles WHERE book_id = ?",
            (book_id,),
        ).fetchone()
        tags = tuple(
            {"id": row["id"], "name": row["name"]}
            for row in connection.execute(
                """
                SELECT ai_tags.id, ai_tags.name
                FROM book_ai_tags
                JOIN ai_tags ON ai_tags.id = book_ai_tags.tag_id
                WHERE book_ai_tags.book_id = ?
                ORDER BY ai_tags.normalized_name, ai_tags.id
                """,
                (book_id,),
            ).fetchall()
        )
        result_count = connection.execute(
            "SELECT COUNT(*) AS result_count FROM ai_reading_results WHERE book_id = ?",
            (book_id,),
        ).fetchone()["result_count"]
        summary = self._admin_book_summary_mapping(
            book_row,
            grant_count=len(grants),
            profile=(profile_row["profile"] if profile_row is not None else "auto"),
            tags=tags,
            result_count=result_count,
        )
        detail = dict(summary)
        detail["grants"] = grants
        detail["ai_tags"] = tags
        detail["effective_tags"] = self._effective_admin_book_tags(
            detail["epub_tags"], tags
        )
        return detail

    @staticmethod
    def _admin_book_summary_from_detail(detail: dict) -> dict:
        return {
            "id": detail["id"],
            "title": detail["title"],
            "authors": list(detail["authors"]),
            "epub_tags": list(detail["epub_tags"]),
            "visibility": detail["visibility"],
            "grant_count": len(detail["grants"]),
            "ai_profile": detail["ai_profile"],
            "ai_tags": [dict(tag) for tag in detail["ai_tags"]],
            "ai_result_count": detail["ai_result_count"],
            "updated_at": detail["updated_at"],
        }

    def get_admin_book_detail(self, book_id: str) -> dict:
        with self._connection() as connection:
            book_row = self._active_admin_book_row(connection, book_id)
            return self._admin_book_detail(connection, book_row)

    def update_admin_book_settings(
        self,
        book_id: str,
        *,
        visibility: str,
        user_ids: Sequence[str],
        tag_ids: Sequence[str],
        profile: str,
    ) -> tuple[dict, dict]:
        """Atomically replace every editable administrator book setting."""
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._active_admin_book_row(connection, book_id)
            self._validate_book_visibility(visibility)
            self._replace_book_grants(connection, book_id, user_ids)
            self._replace_book_ai_tags(connection, book_id, tag_ids)
            self._set_book_ai_profile(connection, book_id, profile)
            connection.execute(
                """
                UPDATE books
                SET visibility = ?, updated_at = CURRENT_TIMESTAMP
                WHERE book_id = ? AND active = 1
                """,
                (visibility, book_id),
            )
            book_row = self._active_admin_book_row(connection, book_id)
            detail = self._admin_book_detail(connection, book_row)
            summary = self._admin_book_summary_from_detail(detail)
            connection.execute("COMMIT")
        return detail, summary

    def reserve_ai_usage(self, principal: Principal, usage_day: str) -> bool:
        """Atomically reserve one billable Provider attempt for a calendar day."""
        if principal.role == "admin":
            return True
        if not self.can_use_ai(principal):
            return False
        limit = self.ai_daily_limit(principal)
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT provider_calls FROM ai_usage WHERE user_id = ? AND usage_day = ?",
                (principal.user_id, usage_day),
            ).fetchone()
            used = int(row["provider_calls"]) if row is not None else 0
            if limit and used >= limit:
                connection.execute("COMMIT")
                return False
            connection.execute(
                """
                INSERT INTO ai_usage (user_id, usage_day, provider_calls)
                VALUES (?, ?, 1)
                ON CONFLICT(user_id, usage_day) DO UPDATE SET
                    provider_calls = ai_usage.provider_calls + 1
                """,
                (principal.user_id, usage_day),
            )
            connection.execute("COMMIT")
        return True

    @staticmethod
    def _json_object(value) -> Optional[dict]:
        if not isinstance(value, str):
            return None
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            return None
        return parsed if isinstance(parsed, dict) else None

    @classmethod
    def _admin_ai_job_mapping(cls, row) -> dict:
        """Return the narrow, public-safe projection for an AI reading job."""
        values = dict(row)
        replay = cls._json_object(values.pop("request_json", None))
        metadata = cls._json_object(values.pop("book_metadata_json", None))
        values["book_title"] = (
            metadata.get("title")
            if metadata is not None and isinstance(metadata.get("title"), str)
            else None
        )
        public_fields = (
            "scope", "mode", "language", "chapter_index", "reading_boundary",
        )
        valid_replay = False
        if replay is not None and all(
            field in replay for field in public_fields + ("book_id",)
        ):
            from .ai_reading import AIReadingError, reading_request_from_job_payload

            try:
                request = reading_request_from_job_payload(replay)
            except AIReadingError:
                pass
            else:
                if request.book_id == values["book_id"]:
                    valid_replay = True
                    for field in public_fields:
                        values[field] = getattr(request, field)
        if not valid_replay:
            for field in public_fields:
                values[field] = None
        error_code = values.get("error_code")
        values["error_code"] = (
            error_code
            if isinstance(error_code, str)
            and error_code in _PUBLIC_AI_READING_JOB_ERROR_CODES
            else None
        )
        values["retryable"] = (
            values["status"] in {"failed", "interrupted"} and valid_replay
        )
        return values

    @staticmethod
    def _admin_ai_job_select() -> str:
        return """
            SELECT jobs.id, jobs.owner_user_id, users.username AS owner_username,
                   jobs.book_id, books.metadata_json AS book_metadata_json,
                   jobs.request_json, jobs.profile, jobs.template_id, jobs.template_version,
                   jobs.status, jobs.error_code, jobs.result_id,
                   jobs.progress_current, jobs.progress_total,
                   jobs.attempt_number, jobs.retried_from_job_id,
                   jobs.retry_root_job_id, jobs.retried_by_user_id,
                   jobs.created_at, jobs.updated_at
            FROM ai_reading_jobs AS jobs
            JOIN users ON users.id = jobs.owner_user_id
            LEFT JOIN books ON books.book_id = jobs.book_id
        """

    def _get_admin_ai_job(self, connection, job_id: str) -> Optional[dict]:
        row = connection.execute(
            self._admin_ai_job_select() + " WHERE jobs.id = ?", (job_id,)
        ).fetchone()
        return self._admin_ai_job_mapping(row) if row is not None else None

    def list_admin_ai_jobs(
        self, *, status: Optional[str], page: int, page_size: int
    ) -> tuple[tuple[dict, ...], int]:
        """Return one privacy-safe administrator page of shared reading jobs."""
        if status is not None and status not in {
            "queued", "running", "complete", "failed", "interrupted",
        }:
            raise ValueError("AI job status filter is invalid")
        if isinstance(page, bool) or not isinstance(page, int) or page < 1:
            raise ValueError("AI job page is invalid")
        if (
            isinstance(page_size, bool)
            or not isinstance(page_size, int)
            or page_size < 1
            or page_size > 100
        ):
            raise ValueError("AI job page size is invalid")
        offset = (page - 1) * page_size
        with self._connection() as connection:
            if status is None:
                total = connection.execute(
                    "SELECT COUNT(*) FROM ai_reading_jobs"
                ).fetchone()[0]
                statement = (
                    self._admin_ai_job_select()
                    + " ORDER BY jobs.created_at DESC, jobs.id DESC "
                    "LIMIT ? OFFSET ?"
                )
                parameters = (page_size, offset)
            else:
                total = connection.execute(
                    "SELECT COUNT(*) FROM ai_reading_jobs WHERE status = ?", (status,)
                ).fetchone()[0]
                statement = (
                    self._admin_ai_job_select()
                    + " WHERE jobs.status = ? "
                    "ORDER BY jobs.created_at DESC, jobs.id DESC LIMIT ? OFFSET ?"
                )
                parameters = (status, page_size, offset)
            if offset >= total:
                return (), int(total)
            rows = connection.execute(statement, parameters).fetchall()
        return tuple(self._admin_ai_job_mapping(row) for row in rows), int(total)

    def get_ai_job_for_retry(self, job_id: str) -> Optional[dict]:
        """Load the private persisted replay row for server-side retry handling only."""
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM ai_reading_jobs WHERE id = ?", (job_id,)
            ).fetchone()
        return dict(row) if row is not None else None

    def create_or_get_admin_retry_ai_job(
        self, *, source_job_id: str, job_id: str, retried_by_user_id: str,
        owner_user_id: str, book_id: str, cache_key: str, request_payload: dict,
        progress_total: int, profile: str, book_profile_selection: str,
        config_revision: int, template_id: str, template_version: int,
        cached_result_id: Optional[str] = None,
    ) -> tuple[dict, bool]:
        """Atomically persist one safe, auditable retry attempt or join its flight."""
        if not isinstance(request_payload, dict):
            raise ValueError("AI retry request payload is invalid")
        if (
            isinstance(progress_total, bool)
            or not isinstance(progress_total, int)
            or progress_total < 1
        ):
            raise ValueError("AI job progress total must be positive")
        if (
            isinstance(config_revision, bool)
            or not isinstance(config_revision, int)
            or config_revision < 0
        ):
            raise ValueError("AI configuration revision is invalid")
        if (
            not isinstance(book_profile_selection, str)
            or book_profile_selection
            not in {"auto", "technical", "fiction", "general"}
        ):
            raise ValueError("AI book profile selection is invalid")
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            source = connection.execute(
                "SELECT * FROM ai_reading_jobs WHERE id = ?", (source_job_id,)
            ).fetchone()
            if source is None:
                raise KeyError(f"Unknown AI job ID: {source_job_id}")
            source_values = dict(source)
            if source_values["status"] not in {"failed", "interrupted"}:
                raise ValueError("AI job is not retryable")
            if self._json_object(source_values["request_json"]) is None:
                raise ValueError("AI job replay payload is invalid")
            if source_values["owner_user_id"] != owner_user_id:
                raise ValueError("AI retry owner does not match source job")
            if source_values["book_id"] != book_id:
                raise ValueError("AI retry book does not match source job")
            owner = self._get_user(connection, owner_user_id)
            retrier = self._get_user(connection, retried_by_user_id)
            book = self._get_book(connection, book_id)
            settings = connection.execute(
                "SELECT enabled, config_revision FROM ai_settings WHERE singleton = 1"
            ).fetchone()
            if not bool(settings["enabled"]):
                raise PermissionError("ai_disabled")
            if not retrier.enabled or retrier.role != "admin":
                raise PermissionError("ai_not_authorized")
            if not owner.enabled:
                raise PermissionError("ai_not_authorized")
            if owner.role != "admin":
                ai_access = connection.execute(
                    "SELECT enabled FROM ai_user_access WHERE user_id = ?",
                    (owner_user_id,),
                ).fetchone()
                if ai_access is None or not bool(ai_access["enabled"]):
                    raise PermissionError("ai_not_authorized")
            if not book.active:
                raise PermissionError("ai_not_authorized")
            if owner.role != "admin" and book.visibility != "authenticated":
                book_access = connection.execute(
                    "SELECT 1 FROM book_access WHERE book_id = ? AND user_id = ?",
                    (book_id, owner_user_id),
                ).fetchone()
                if book_access is None:
                    raise PermissionError("ai_not_authorized")
            profile_row = connection.execute(
                "SELECT profile FROM book_ai_profiles WHERE book_id = ?",
                (book_id,),
            ).fetchone()
            current_profile_selection = (
                profile_row["profile"] if profile_row is not None else "auto"
            )
            if current_profile_selection != book_profile_selection:
                raise _AIRetrySnapshotChanged
            if config_revision != int(settings["config_revision"]):
                cached_result_id = None
            if cached_result_id is not None:
                cached_result = connection.execute(
                    """
                    SELECT 1
                    FROM ai_reading_current_results AS current_results
                    JOIN ai_reading_results AS results
                      ON results.id = current_results.result_id
                    WHERE current_results.cache_key = ?
                      AND current_results.result_id = ?
                      AND results.id = ?
                      AND results.cache_key = ?
                      AND results.book_id = ?
                      AND results.config_revision = ?
                      AND results.template_id = ?
                      AND results.template_version = ?
                    """,
                    (
                        cache_key, cached_result_id, cached_result_id, cache_key,
                        book_id, config_revision, template_id, template_version,
                    ),
                ).fetchone()
                if cached_result is None:
                    cached_result_id = None

            existing = connection.execute(
                """
                SELECT id FROM ai_reading_jobs
                WHERE cache_key = ? AND status IN ('queued', 'running')
                ORDER BY created_at DESC, id DESC LIMIT 1
                """,
                (cache_key,),
            ).fetchone()
            if existing is not None:
                job = self._get_admin_ai_job(connection, existing["id"])
                connection.execute("COMMIT")
                return job, False

            retry_root_job_id = source_values["retry_root_job_id"] or source_job_id
            root_attempt = connection.execute(
                "SELECT attempt_number FROM ai_reading_jobs WHERE id = ?",
                (retry_root_job_id,),
            ).fetchone()
            if root_attempt is None:
                raise ValueError("AI retry root is unavailable")
            highest_retry = connection.execute(
                "SELECT MAX(attempt_number) FROM ai_reading_jobs "
                "WHERE retry_root_job_id = ?",
                (retry_root_job_id,),
            ).fetchone()[0]
            attempt_number = (
                max(int(root_attempt["attempt_number"]), highest_retry or 0) + 1
            )
            status = "complete" if cached_result_id is not None else "queued"
            progress_current = progress_total if cached_result_id is not None else 0
            try:
                connection.execute(
                    """
                    INSERT INTO ai_reading_jobs (
                        id, owner_user_id, book_id, cache_key, request_json, profile,
                        template_id, template_version, status, result_id,
                        progress_current, progress_total, attempt_number,
                        retried_from_job_id, retry_root_job_id, retried_by_user_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        job_id, owner_user_id, book_id, cache_key,
                        json.dumps(request_payload, ensure_ascii=False, separators=(",", ":")),
                        profile, template_id, template_version, status, cached_result_id,
                        progress_current, progress_total, attempt_number, source_job_id,
                        retry_root_job_id, retried_by_user_id,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                if "UNIQUE constraint failed: ai_reading_jobs.cache_key" not in str(exc):
                    raise
                existing = connection.execute(
                    """
                    SELECT id FROM ai_reading_jobs
                    WHERE cache_key = ? AND status IN ('queued', 'running')
                    ORDER BY created_at DESC, id DESC LIMIT 1
                    """,
                    (cache_key,),
                ).fetchone()
                if existing is None:
                    raise
                job = self._get_admin_ai_job(connection, existing["id"])
                connection.execute("COMMIT")
                return job, False
            job = self._get_admin_ai_job(connection, job_id)
            connection.execute("COMMIT")
        return job, True

    def create_ai_job(
        self,
        job_id: str,
        owner_user_id: str,
        cache_key: str,
        *,
        book_id: Optional[str] = None,
        result_id: Optional[str] = None,
        progress_total: int = 1,
        request_payload: Optional[dict] = None,
        profile: Optional[str] = None,
        template_id: Optional[str] = None,
        template_version: Optional[int] = None,
    ) -> None:
        if int(progress_total) < 1:
            raise ValueError("AI job progress total must be positive")
        with self._connection() as connection:
            self._require_user(connection, owner_user_id)
            if book_id is not None:
                self._get_book(connection, book_id)
            connection.execute(
                """
                INSERT INTO ai_reading_jobs (
                    id, owner_user_id, book_id, cache_key, request_json, profile,
                    template_id, template_version, result_id, status, progress_total
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'queued', ?)
                """,
                (
                    job_id, owner_user_id, book_id, cache_key,
                    json.dumps(request_payload, ensure_ascii=False, separators=(",", ":")) if request_payload else None,
                    profile, template_id, template_version, result_id, int(progress_total),
                ),
            )

    def create_or_get_active_ai_job(
        self,
        job_id: str,
        owner_user_id: str,
        book_id: str,
        cache_key: str,
        *,
        progress_total: int = 1,
        request_payload: Optional[dict] = None,
        profile: Optional[str] = None,
        template_id: Optional[str] = None,
        template_version: Optional[int] = None,
    ) -> tuple[dict, bool]:
        """Atomically join an in-flight shared generation or create one.

        The immediate SQLite transaction is a global single-flight lock. It
        deliberately excludes the independent follow-up task table.
        """
        if int(progress_total) < 1:
            raise ValueError("AI job progress total must be positive")
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._require_user(connection, owner_user_id)
            self._get_book(connection, book_id)
            existing = connection.execute(
                """
                SELECT id, owner_user_id, book_id, cache_key, request_json, profile,
                       template_id, template_version, status, error_code, result_id,
                       progress_current, progress_total, created_at, updated_at
                FROM ai_reading_jobs
                WHERE cache_key = ? AND status IN ('queued', 'running')
                ORDER BY created_at DESC, id DESC LIMIT 1
                """,
                (cache_key,),
            ).fetchone()
            if existing is not None:
                connection.execute("COMMIT")
                return dict(existing), False
            connection.execute(
                """
                INSERT INTO ai_reading_jobs (
                    id, owner_user_id, book_id, cache_key, request_json, profile,
                    template_id, template_version, status, progress_total
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'queued', ?)
                """,
                (
                    job_id, owner_user_id, book_id, cache_key,
                    json.dumps(request_payload, ensure_ascii=False, separators=(",", ":")) if request_payload else None,
                    profile, template_id, template_version, int(progress_total),
                ),
            )
            created = connection.execute(
                """
                SELECT id, owner_user_id, book_id, cache_key, request_json, profile,
                       template_id, template_version, status, error_code, result_id,
                       progress_current, progress_total, created_at, updated_at
                FROM ai_reading_jobs WHERE id = ?
                """,
                (job_id,),
            ).fetchone()
            connection.execute("COMMIT")
        return dict(created), True

    def start_ai_job(self, job_id: str) -> bool:
        with self._connection() as connection:
            cursor = connection.execute(
                """
                UPDATE ai_reading_jobs SET status = 'running',
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND status = 'queued'
                """,
                (job_id,),
            )
        return cursor.rowcount == 1

    def rekey_running_ai_job(self, job_id: str, cache_key: str) -> bool:
        """Atomically move a leased job onto the cache identity it executes.

        The partial unique index keeps the worker's new identity single-flight
        with all queued and running jobs. A conflict means another active job
        already owns that exact execution identity, so the caller must not
        issue a duplicate provider request.
        """
        if not isinstance(cache_key, str) or not cache_key:
            raise ValueError("AI job cache key must not be empty")
        try:
            with self._connection() as connection:
                cursor = connection.execute(
                    """
                    UPDATE ai_reading_jobs SET cache_key = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ? AND status = 'running'
                    """,
                    (cache_key, job_id),
                )
        except sqlite3.IntegrityError as error:
            if "ai_reading_jobs.cache_key" in str(error):
                return False
            raise
        return cursor.rowcount == 1

    def mark_incomplete_ai_jobs_interrupted(self) -> int:
        with self._connection() as connection:
            cursor = connection.execute(
                """
                UPDATE ai_reading_jobs SET status = 'interrupted',
                    updated_at = CURRENT_TIMESTAMP
                WHERE status IN ('queued', 'running')
                """
            )
        return cursor.rowcount

    def requeue_running_ai_jobs(self) -> int:
        """Recover durable work after a process restart instead of losing it."""
        with self._connection() as connection:
            cursor = connection.execute(
                """
                UPDATE ai_reading_jobs SET status = 'queued', updated_at = CURRENT_TIMESTAMP
                WHERE status = 'running' AND request_json IS NOT NULL
                """
            )
        return cursor.rowcount

    def requeue_running_ai_followups(self) -> int:
        """Recover private chat turns after a process restart."""
        with self._connection() as connection:
            cursor = connection.execute(
                """
                UPDATE ai_reading_followups SET status = 'queued', updated_at = CURRENT_TIMESTAMP
                WHERE status = 'running'
                """
            )
        return cursor.rowcount

    def requeue_running_ai_book_chat_turns(self) -> int:
        """Recover book-scoped private conversations after a restart."""
        with self._connection() as connection:
            cursor = connection.execute(
                """
                UPDATE ai_book_chat_turns SET status = 'queued', updated_at = CURRENT_TIMESTAMP
                WHERE status = 'running'
                """
            )
        return cursor.rowcount

    def claim_next_ai_reading_job(self) -> Optional[dict]:
        """Atomically lease one persisted queued task to this worker."""
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT * FROM ai_reading_jobs INDEXED BY idx_ai_jobs_queue
                WHERE status = 'queued' AND request_json IS NOT NULL
                ORDER BY created_at ASC, id ASC LIMIT 1
                """
            ).fetchone()
            if row is None:
                connection.execute("COMMIT")
                return None
            cursor = connection.execute(
                """
                UPDATE ai_reading_jobs SET status = 'running', updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND status = 'queued'
                """,
                (row["id"],),
            )
            if cursor.rowcount != 1:
                connection.execute("COMMIT")
                return None
            claimed = connection.execute(
                "SELECT * FROM ai_reading_jobs WHERE id = ?", (row["id"],)
            ).fetchone()
            connection.execute("COMMIT")
        return dict(claimed)

    def claim_next_ai_followup(self) -> Optional[dict]:
        """Atomically lease one private chat turn to the background worker."""
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT * FROM ai_reading_followups
                WHERE status = 'queued'
                ORDER BY created_at ASC, id ASC LIMIT 1
                """
            ).fetchone()
            if row is None:
                connection.execute("COMMIT")
                return None
            cursor = connection.execute(
                """
                UPDATE ai_reading_followups SET status = 'running', updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND status = 'queued'
                """,
                (row["id"],),
            )
            if cursor.rowcount != 1:
                connection.execute("COMMIT")
                return None
            claimed = connection.execute(
                "SELECT * FROM ai_reading_followups WHERE id = ?", (row["id"],)
            ).fetchone()
            connection.execute("COMMIT")
        return dict(claimed)

    def claim_next_ai_book_chat_turn(self) -> Optional[dict]:
        """Atomically lease the next book-scoped private question."""
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT * FROM ai_book_chat_turns WHERE status = 'queued'
                -- CURRENT_TIMESTAMP is second-granular in SQLite. Rowid keeps
                -- questions submitted within one second in true send order.
                ORDER BY created_at ASC, rowid ASC LIMIT 1
                """
            ).fetchone()
            if row is None:
                connection.execute("COMMIT")
                return None
            cursor = connection.execute(
                """
                UPDATE ai_book_chat_turns SET status = 'running', updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND status = 'queued'
                """,
                (row['id'],),
            )
            if cursor.rowcount != 1:
                connection.execute("COMMIT")
                return None
            claimed = connection.execute(
                "SELECT * FROM ai_book_chat_turns WHERE id = ?", (row['id'],)
            ).fetchone()
            connection.execute("COMMIT")
        return dict(claimed)

    def update_ai_job_progress(
        self, job_id: str, progress_current: int, progress_total: int
    ) -> bool:
        if int(progress_current) < 0 or int(progress_total) < 1:
            raise ValueError("AI job progress is invalid")
        if int(progress_current) > int(progress_total):
            raise ValueError("AI job progress exceeds its total")
        with self._connection() as connection:
            cursor = connection.execute(
                """
                UPDATE ai_reading_jobs SET progress_current = ?, progress_total = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND status = 'running'
                """,
                (int(progress_current), int(progress_total), job_id),
            )
        return cursor.rowcount == 1

    def finish_ai_job(
        self,
        job_id: str,
        *,
        result_id: Optional[str] = None,
        error_code: Optional[str] = None,
    ) -> bool:
        if result_id is not None and error_code is not None:
            raise ValueError("AI job cannot have both a result and an error")
        status = "failed" if error_code else "complete"
        with self._connection() as connection:
            cursor = connection.execute(
                """
                UPDATE ai_reading_jobs SET status = ?, result_id = ?, error_code = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND status = 'running'
                """,
                (status, result_id, error_code, job_id),
            )
        return cursor.rowcount == 1

    def get_ai_job(
        self, job_id: str, owner_user_id: Optional[str] = None
    ) -> Optional[dict]:
        with self._connection() as connection:
            statement = """
                SELECT id, owner_user_id, book_id, cache_key, status, error_code,
                       result_id, progress_current, progress_total, created_at, updated_at
                FROM ai_reading_jobs
                WHERE id = ?
                """
            parameters = (job_id,)
            if owner_user_id is not None:
                statement += " AND owner_user_id = ?"
                parameters += (owner_user_id,)
            row = connection.execute(statement, parameters).fetchone()
        return dict(row) if row is not None else None

    def store_ai_reading_result(
        self,
        *,
        cache_key: str,
        book_id: str,
        chapter_index: Optional[int],
        scope: str,
        mode: str,
        profile: str,
        config_revision: int,
        content: dict,
        created_by_user_id: str,
        template_id: str = "legacy",
        template_version: int = 0,
        language: str = "en",
        reading_boundary: Optional[int] = None,
    ) -> dict:
        if scope not in {"book", "chapter"}:
            raise ValueError("Unsupported AI reading scope")
        if mode not in {"spoiler_free", "read_so_far", "full_review", "chapter"}:
            raise ValueError("Unsupported AI reading mode")
        if profile not in {"auto", "technical", "fiction", "general"}:
            raise ValueError("Unsupported AI profile")
        if not isinstance(content, dict):
            raise ValueError("AI reading result must be an object")
        if not isinstance(template_id, str) or not template_id or len(template_id) > 100:
            raise ValueError("AI reading template id is invalid")
        if isinstance(template_version, bool) or not isinstance(template_version, int) or template_version < 0:
            raise ValueError("AI reading template version is invalid")
        if language not in {"en", "zh-CN"}:
            raise ValueError("AI reading language is invalid")
        if isinstance(reading_boundary, bool) or (
            reading_boundary is not None and (
                not isinstance(reading_boundary, int) or reading_boundary < 0
            )
        ):
            raise ValueError("AI reading boundary is invalid")
        if scope == "chapter" and chapter_index is None:
            raise ValueError("Chapter AI reading results need a chapter index")
        if scope == "book" and chapter_index is not None:
            raise ValueError("Book AI reading results cannot have a chapter index")
        result_id = uuid.uuid4().hex
        encoded_content = json.dumps(content, ensure_ascii=False, separators=(",", ":"))
        with self._connection() as connection:
            self._get_book(connection, book_id)
            self._require_user(connection, created_by_user_id)
            connection.execute(
                """
                INSERT INTO ai_reading_results (
                    id, cache_key, book_id, chapter_index, scope, mode, profile,
                    language, reading_boundary, config_revision, template_id, template_version,
                    content_json, created_by_user_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    result_id,
                    cache_key,
                    book_id,
                    chapter_index,
                    scope,
                    mode,
                    profile,
                    language,
                    reading_boundary,
                    int(config_revision),
                    template_id,
                    template_version,
                    encoded_content,
                    created_by_user_id,
                ),
            )
            connection.execute(
                """
                INSERT INTO ai_reading_current_results (cache_key, result_id)
                VALUES (?, ?)
                ON CONFLICT(cache_key) DO UPDATE SET
                    result_id = excluded.result_id,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (cache_key, result_id),
            )
            row = connection.execute(
                "SELECT * FROM ai_reading_results WHERE id = ?", (result_id,)
            ).fetchone()
        return self._ai_result_record(row)

    @staticmethod
    def _ai_result_record(row) -> dict:
        item = dict(row)
        item["content"] = json.loads(item.pop("content_json"))
        return item

    def get_current_ai_reading_result(self, cache_key: str) -> Optional[dict]:
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT ai_reading_results.*
                FROM ai_reading_current_results
                JOIN ai_reading_results
                  ON ai_reading_results.id = ai_reading_current_results.result_id
                WHERE ai_reading_current_results.cache_key = ?
                """,
                (cache_key,),
            ).fetchone()
        return self._ai_result_record(row) if row is not None else None

    def get_ai_reading_result(self, result_id: str) -> Optional[dict]:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM ai_reading_results WHERE id = ?", (result_id,)
            ).fetchone()
        return self._ai_result_record(row) if row is not None else None

    def list_ai_reading_results(
        self,
        book_id: str,
        *,
        chapter_index: Optional[int] = None,
        language: Optional[str] = None,
    ) -> tuple[dict, ...]:
        """List shared learning layers for a readable book, newest first."""
        clauses = ["book_id = ?"]
        parameters: list[object] = [book_id]
        if chapter_index is not None:
            clauses.append("chapter_index = ?")
            parameters.append(chapter_index)
        if language is not None:
            clauses.append("language = ?")
            parameters.append(language)
        statement = (
            "SELECT * FROM ai_reading_results WHERE " + " AND ".join(clauses)
            + " ORDER BY created_at DESC, id DESC"
        )
        with self._connection() as connection:
            rows = connection.execute(statement, tuple(parameters)).fetchall()
        return tuple(self._ai_result_record(row) for row in rows)

    def list_current_ai_reading_results(self, book_id: str) -> tuple[dict, ...]:
        """Return one current shared learning layer for each cache key of a book."""
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT ai_reading_results.*
                FROM ai_reading_current_results
                JOIN ai_reading_results
                  ON ai_reading_results.id = ai_reading_current_results.result_id
                WHERE ai_reading_results.book_id = ?
                ORDER BY ai_reading_results.created_at DESC, ai_reading_results.id DESC
                """,
                (book_id,),
            ).fetchall()
        return tuple(self._ai_result_record(row) for row in rows)

    def clear_ai_reading_results(
        self, *, book_id: Optional[str] = None, config_revision: Optional[int] = None
    ) -> int:
        clauses = []
        params = []
        if book_id is not None:
            clauses.append("book_id = ?")
            params.append(book_id)
        if config_revision is not None:
            clauses.append("config_revision = ?")
            params.append(int(config_revision))
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        with self._connection() as connection:
            cursor = connection.execute(
                "DELETE FROM ai_reading_results" + where, tuple(params)
            )
        return cursor.rowcount

    def delete_ai_reading_result(self, result_id: str) -> bool:
        """Delete one retained shared result and let its SQLite relations clean up."""
        with self._connection() as connection:
            cursor = connection.execute(
                "DELETE FROM ai_reading_results WHERE id = ?", (result_id,)
            )
        return cursor.rowcount == 1

    def create_ai_followup(
        self, *, result_id: str, owner_user_id: str, question: str, language: str = "en"
    ) -> dict:
        if not isinstance(question, str) or not question.strip() or len(question) > 2000:
            raise ValueError("AI follow-up must contain 1 to 2000 characters")
        if language not in {"en", "zh-CN"}:
            raise ValueError("AI follow-up language is invalid")
        followup_id = uuid.uuid4().hex
        with self._connection() as connection:
            self._require_user(connection, owner_user_id)
            if connection.execute(
                "SELECT 1 FROM ai_reading_results WHERE id = ?", (result_id,)
            ).fetchone() is None:
                raise KeyError("Unknown AI reading result")
            connection.execute(
                """
                INSERT INTO ai_reading_followups (
                    id, result_id, owner_user_id, question, language, status
                ) VALUES (?, ?, ?, ?, ?, 'queued')
                """,
                (followup_id, result_id, owner_user_id, question.strip(), language),
            )
            row = connection.execute(
                "SELECT * FROM ai_reading_followups WHERE id = ?", (followup_id,)
            ).fetchone()
        return dict(row)

    def start_ai_followup(self, followup_id: str, owner_user_id: str) -> bool:
        with self._connection() as connection:
            cursor = connection.execute(
                """
                UPDATE ai_reading_followups SET status = 'running',
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND owner_user_id = ? AND status = 'queued'
                """,
                (followup_id, owner_user_id),
            )
        return cursor.rowcount == 1

    def finish_ai_followup(
        self,
        followup_id: str,
        owner_user_id: str,
        *,
        answer: Optional[str] = None,
        error_code: Optional[str] = None,
    ) -> bool:
        if (answer is None) == (error_code is None):
            raise ValueError("AI follow-up needs exactly one answer or error code")
        with self._connection() as connection:
            cursor = connection.execute(
                """
                UPDATE ai_reading_followups SET status = ?, answer = ?, error_code = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND owner_user_id = ? AND status = 'running'
                """,
                (
                    "complete" if answer is not None else "failed",
                    answer,
                    error_code,
                    followup_id,
                    owner_user_id,
                ),
            )
        return cursor.rowcount == 1

    def list_ai_followups(self, result_id: str, owner_user_id: str) -> tuple[dict, ...]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT id, result_id, owner_user_id, question, language, answer, status,
                       error_code, created_at, updated_at
                FROM ai_reading_followups
                WHERE result_id = ? AND owner_user_id = ?
                -- Preserve the reader's actual question-and-answer order even
                -- when multiple turns share the same timestamp second.
                ORDER BY created_at ASC, rowid ASC
                """,
                (result_id, owner_user_id),
            ).fetchall()
        return tuple(dict(row) for row in rows)

    def get_ai_followup(
        self, followup_id: str, owner_user_id: str
    ) -> Optional[dict]:
        """Return one user's persisted AI conversation turn."""
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT id, result_id, owner_user_id, question, language, answer, status,
                       error_code, created_at, updated_at
                FROM ai_reading_followups
                WHERE id = ? AND owner_user_id = ?
                """,
                (followup_id, owner_user_id),
            ).fetchone()
        return dict(row) if row is not None else None

    def create_ai_book_chat_turn(
        self, *, book_id: str, chapter_index: int, owner_user_id: str,
        question: str, language: str = 'en', context_mode: str = 'chapter_source',
        result_id: Optional[str] = None, book_context: bool = False,
    ) -> dict:
        if not isinstance(question, str) or not question.strip() or len(question) > 2000:
            raise ValueError('AI chat must contain 1 to 2000 characters')
        if not isinstance(chapter_index, int) or chapter_index < 0:
            raise ValueError('AI chat chapter is invalid')
        if language not in {'en', 'zh-CN'}:
            raise ValueError('AI chat language is invalid')
        if context_mode not in {'shared_layer', 'chapter_source'}:
            raise ValueError('AI chat context is invalid')
        turn_id = uuid.uuid4().hex
        with self._connection() as connection:
            self._require_user(connection, owner_user_id)
            if result_id is not None and connection.execute(
                'SELECT 1 FROM ai_reading_results WHERE id = ? AND book_id = ?',
                (result_id, book_id),
            ).fetchone() is None:
                raise KeyError('Unknown AI reading result')
            connection.execute(
                """
                INSERT INTO ai_book_chat_turns (
                    id, book_id, chapter_index, result_id, context_mode,
                    book_context, owner_user_id, question, language, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'queued')
                """,
                (turn_id, book_id, chapter_index, result_id, context_mode,
                 1 if book_context else 0, owner_user_id, question.strip(), language),
            )
            row = connection.execute(
                'SELECT * FROM ai_book_chat_turns WHERE id = ?', (turn_id,)
            ).fetchone()
        return dict(row)

    def finish_ai_book_chat_turn(
        self, turn_id: str, owner_user_id: str, *, answer: Optional[str] = None,
        error_code: Optional[str] = None,
    ) -> bool:
        if (answer is None) == (error_code is None):
            raise ValueError('AI chat needs exactly one answer or error code')
        with self._connection() as connection:
            cursor = connection.execute(
                """
                UPDATE ai_book_chat_turns SET status = ?, answer = ?, error_code = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND owner_user_id = ? AND status = 'running'
                """,
                ('complete' if answer is not None else 'failed', answer, error_code,
                 turn_id, owner_user_id),
            )
        return cursor.rowcount == 1

    def list_ai_book_chat_turns(self, book_id: str, owner_user_id: str) -> tuple[dict, ...]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT id, book_id, chapter_index, result_id, context_mode, book_context,
                       owner_user_id, question, language, answer, status, error_code,
                       created_at, updated_at
                FROM ai_book_chat_turns
                WHERE book_id = ? AND owner_user_id = ?
                ORDER BY created_at ASC, id ASC
                """, (book_id, owner_user_id),
            ).fetchall()
        return tuple(dict(row) for row in rows)

    def get_ai_book_chat_summary(
        self, book_id: str, owner_user_id: str, language: str,
    ) -> Optional[dict]:
        if language not in {'en', 'zh-CN'}:
            raise ValueError('AI chat language is invalid')
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT book_id, owner_user_id, language, covered_turn_count,
                       summary_text, updated_at
                FROM ai_book_chat_summaries
                WHERE book_id = ? AND owner_user_id = ? AND language = ?
                """,
                (book_id, owner_user_id, language),
            ).fetchone()
        return dict(row) if row is not None else None

    def upsert_ai_book_chat_summary(
        self, *, book_id: str, owner_user_id: str, language: str,
        covered_turn_count: int, summary_text: str,
    ) -> None:
        if language not in {'en', 'zh-CN'} or covered_turn_count < 0:
            raise ValueError('AI chat summary is invalid')
        if not isinstance(summary_text, str) or len(summary_text) > 24000:
            raise ValueError('AI chat summary is invalid')
        with self._connection() as connection:
            self._require_user(connection, owner_user_id)
            connection.execute(
                """
                INSERT INTO ai_book_chat_summaries (
                    book_id, owner_user_id, language, covered_turn_count, summary_text
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(book_id, owner_user_id, language) DO UPDATE SET
                    covered_turn_count = excluded.covered_turn_count,
                    summary_text = excluded.summary_text,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (book_id, owner_user_id, language, covered_turn_count, summary_text),
            )

    def get_ai_book_chat_turn(self, turn_id: str, owner_user_id: str) -> Optional[dict]:
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT id, book_id, chapter_index, result_id, context_mode, book_context,
                       owner_user_id, question, language, answer, status, error_code,
                       created_at, updated_at
                FROM ai_book_chat_turns
                WHERE id = ? AND owner_user_id = ?
                """, (turn_id, owner_user_id),
            ).fetchone()
        return dict(row) if row is not None else None

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

    def book_by_id(self, book_id: str) -> Optional[BookRecord]:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM books WHERE book_id = ? AND active = 1", (book_id,)
            ).fetchone()
        return self._book_record(row) if row else None

    def book_by_source(self, source_path: Path) -> Optional[BookRecord]:
        canonical_path = str(Path(source_path).expanduser().resolve())
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM books WHERE source_path = ?",
                (canonical_path,),
            ).fetchone()
        return self._book_record(row) if row else None

    def get_annotation(self, annotation_id: str, user_id: str):
        with self._connection() as connection:
            self._require_user(connection, user_id)
            row = connection.execute(
                "SELECT * FROM annotations WHERE id = ? AND user_id = ?",
                (annotation_id, user_id),
            ).fetchone()
        return self._annotation_data(row) if row else None

    def list_annotations(
        self,
        book_hash: Optional[str] = None,
        chapter_index: Optional[int] = None,
        *,
        user_id: str,
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
            self._require_user(connection, user_id)
            rows = connection.execute(
                "SELECT * FROM annotations" + where + " ORDER BY created_at DESC",
                values,
            ).fetchall()
        return [self._annotation_data(row) for row in rows]

    def upsert_annotation(
        self,
        annotation,
        user_id: str,
        replace_existing: bool = False,
    ) -> None:
        conflict = (
            """
                ON CONFLICT(user_id, id) DO UPDATE SET
                    book_hash = excluded.book_hash,
                    chapter_index = excluded.chapter_index,
                    text = excluded.text,
                    note = excluded.note,
                    start_meta = excluded.start_meta,
                    end_meta = excluded.end_meta,
                    color = excluded.color,
                    created_at = excluded.created_at,
                    updated_at = excluded.updated_at
                WHERE annotations.book_hash = excluded.book_hash
            """
            if replace_existing
            else ""
        )
        with self._connection() as connection:
            self._require_user(connection, user_id)
            cursor = connection.execute(
                f"""
                INSERT INTO annotations (
                    id, book_hash, chapter_index, text, note, start_meta, end_meta,
                    color, created_at, updated_at, user_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                {conflict}
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
                ),
            )
            if replace_existing and cursor.rowcount != 1:
                raise ValueError("Annotation IDs cannot move between books")

    def update_annotation(self, annotation_id: str, data, user_id: str):
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
            self._require_user(connection, user_id)
            connection.execute(
                "UPDATE annotations SET "
                + ", ".join(assignments)
                + " WHERE id = ? AND user_id = ?",
                values + [annotation_id, user_id],
            )
        return self.get_annotation(annotation_id, user_id=user_id)

    def delete_annotation(self, annotation_id: str, user_id: str) -> None:
        with self._connection() as connection:
            self._require_user(connection, user_id)
            connection.execute(
                "DELETE FROM annotations WHERE id = ? AND user_id = ?",
                (annotation_id, user_id),
            )

    def get_bookshelf(self, user_id: str):
        with self._connection() as connection:
            self._require_user(connection, user_id)
            row = connection.execute(
                "SELECT version, data FROM bookshelves WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        return (row["version"], row["data"]) if row else None

    def create_bookshelf(self, user_id: str, version: int, data) -> None:
        serialized = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False)
        with self._connection() as connection:
            self._require_user(connection, user_id)
            connection.execute(
                """
                INSERT INTO bookshelves (
                    user_id, version, data, updated_at
                ) VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                """,
                (user_id, version, serialized),
            )

    def update_bookshelf(self, user_id: str, version: int, data) -> None:
        serialized = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False)
        with self._connection() as connection:
            self._require_user(connection, user_id)
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
            self._require_user(connection, user_id)
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
            self._require_user(connection, user_id)
            connection.execute(
                """
                INSERT INTO reading_progress(
                    user_id, book_hash, chapter_index, updated_at
                ) VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(user_id, book_hash) DO UPDATE SET
                    chapter_index = excluded.chapter_index,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (user_id, book_hash, chapter_index),
            )

    def delete_reading_progress(self, user_id: str, book_hash: str) -> None:
        with self._connection() as connection:
            self._require_user(connection, user_id)
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
