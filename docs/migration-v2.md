# Migrating EPUB Browser v1 to v2

EPUB Browser v2 separates static-site generation (`ssg`) from the stateful reading service (`server`). The legacy v1 command syntax remains accepted throughout the v2 major line, but new deployments should use an explicit mode.

## Command mapping

| v1 | v2 |
| --- | --- |
| `epub-browser BOOKS` | `epub-browser server BOOKS --ephemeral` |
| `epub-browser BOOKS --output-dir STATE` | `epub-browser server BOOKS --server-dir STATE` |
| `epub-browser BOOKS --output-dir DIST --no-server` | `epub-browser ssg BOOKS --output-dir DIST` |
| `--sync-dir DIR` | `server --legacy-sync-dir DIR` |
| temporary `--keep-files` | retained by the compatibility adapter |

The v1 `--output-dir` had two meanings. v2 removes that ambiguity: SSG output is a deployable snapshot, while Server storage contains durable data plus a replaceable cache.

## Automatic first-start migration

Migration runs only for persistent Server mode. Given an existing v1 directory:

```bash
epub-browser server /path/to/books \
  --server-dir /path/to/existing-v1-directory \
  --legacy-sync-dir /path/to/legacy-sync
```

Startup performs these steps:

1. Acquire the Server and migration locks.
2. Reject ambiguous root databases or an unreadable/corrupt SQLite file.
3. Copy the v1 root `epub-browser.db` or `annotations.db` to a verified backup under `data/backups/`.
4. Upgrade a temporary copy and atomically activate it as `data/epub-browser.db`.
5. Preserve annotations, bookshelf rows, reading progress, and legacy book IDs.
6. Import the highest valid `epub-browser-bookshelf-<username>-<version>.json` per user when it is newer than SQLite. JSON source files are not deleted.
7. Reconcile every EPUB into `cache/public/`.
8. After a complete reconciliation, move old root `index.html`, `book-metadata.json`, `sw.js`, `assets/`, and `book/` into `cache/legacy-public/`.
9. Remove `cache/legacy-public/` only after the next successful startup.

Migration progress is recorded in `data/migration-state.json`, so an interrupted start can be retried safely.

Backups use a name such as:

```text
data/backups/epub-browser.db.20260818T120000Z.0123456789ab.bak
```

The backup is verified before the v1 root database is removed.

## Book identity and user data

During migration, v1 hashes found in `book-metadata.json` and `book/<hash>/` are correlated with discovered EPUBs. Both the user-supplied source spelling and its canonical path are considered, which preserves path-derived IDs across symlink and macOS `/var` path aliases when the match is unique.

Deleting a source marks its book inactive but does not delete its durable registry row, annotations, bookshelf records, or reading progress. Deleting `cache/` is safe; a later start regenerates it with the same Server book IDs.

The bookshelf product behavior is unchanged: it remains browser-local until the user invokes the existing manual Sync action. A database with no bookshelf row is therefore normal before the first Sync.

## Conflict and corruption handling

If both of these files exist at the v1 root, migration stops and names both paths:

```text
epub-browser.db
annotations.db
```

Move the non-authoritative file aside and retry. EPUB Browser never chooses one automatically.

If SQLite integrity checks fail, the source file is left in place. Repair or restore it before retrying. If `data/epub-browser.db` already exists, it is authoritative; any later-discovered root database is left untouched and reported with `--log`.

## Rollback

Stop EPUB Browser before copying database files.

To return to v1 after a successful v2 migration:

1. Preserve the entire v2 Server directory as an additional backup.
2. Select the matching verified `.bak` file under `data/backups/`.
3. Copy it back to the v1 root as `epub-browser.db` (or `annotations.db` if that was the original name).
4. Run the previous v1 package against that root.

Example:

```bash
cp -a /path/to/server-dir /path/to/server-dir.v2-backup
cp /path/to/server-dir/data/backups/epub-browser.db.TIMESTAMP.DIGEST.bak \
  /path/to/server-dir/epub-browser.db
```

If multiple backups exist, choose the timestamp and digest recorded in `data/migration-state.json` rather than using a wildcard blindly.

For a v2 retry instead of a downgrade, keep `data/epub-browser.db` and rerun the same `server --server-dir` command. Generated cache files may be removed without touching `data/`.

## Docker migration

The v2 image expects:

- `/app/Library`: EPUB input, preferably read-only;
- `/app/EpubBrowserFiles`: required read-write persistent Server directory;
- `/app/SyncData`: optional read-only legacy JSON import directory.

The container command now uses `epub-browser server` and listens on `0.0.0.0` inside the container. Bind the host port to `127.0.0.1` unless a protected LAN or authenticated TLS reverse proxy is intended.
