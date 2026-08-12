# Server Bookshelf SQLite Design

## Goal

Store synchronized bookshelves in the server's SQLite database, alongside annotations, while preserving the browser's local bookshelf cache and the current sync payload.

## Scope

- In server mode, SQLite becomes the authoritative durable copy of each user's bookshelf.
- The browser continues to use `localStorage` for immediate rendering and offline use.
- `POST /sync` retains its current `username`, `version`, and `data` payload shape.
- A bookshelf remains one JSON document rather than being decomposed into tables, because nested groups, ordering, and arbitrary client state are already represented by that document.

## Data Model

Create a `bookshelves` table in the existing `annotations.db` database:

```sql
CREATE TABLE IF NOT EXISTS bookshelves (
    username TEXT PRIMARY KEY,
    version INTEGER NOT NULL,
    data TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
)
```

`data` contains the complete bookshelf JSON sent by the browser. A single row is isolated by `username` and can be read or updated atomically.

## Synchronization Semantics

- No existing row: store the submitted data at the submitted positive version (or version `1`) and return the existing new-user response shape.
- Submitted version equals the stored version: return `304`, as today.
- Submitted version is behind the stored version: return the stored `version` and `data`, as today.
- Submitted version is newer: atomically replace the stored JSON and version, then return success.
- Invalid JSON request bodies remain `400` responses.

The client protocol and optimistic-version conflict behavior therefore remain unchanged.

## Migration and Compatibility

- On a sync request with no SQLite row, the server checks for the legacy `epub-browser-bookshelf-<username>-<version>.json` files in `sync_dir` (or the library directory).
- If a legacy record exists, import the highest-version file into SQLite before applying the request's normal version comparison.
- Do not delete legacy JSON files during the initial migration release. They remain a recoverable backup and are no longer created or updated.
- `sync_dir` remains accepted for legacy import compatibility; new bookshelf state is always written to the SQLite database in the served library directory.

## Security Boundary

The existing username field is an identifier, not authentication. Moving to SQLite does not change that: deployments exposed to untrusted users still require real authentication and server-side identity binding before user data can be considered private.

## Validation

- Server tests prove storing, reading, stale-version responses, and equal-version `304` behavior through `/sync`.
- A migration test proves the highest-version legacy JSON shelf imports on first request and is returned through the unchanged response format.
- Annotation tests continue to pass, demonstrating both features share one database without breaking each other.
