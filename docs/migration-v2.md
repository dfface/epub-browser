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
| `--book-id-storage sidecar\|embedded` | invocation-wide identity carrier; default `sidecar` |

The v1 `--output-dir` had two meanings. v2 removes that ambiguity: SSG output is a deployable snapshot, while Server storage contains durable data plus a replaceable cache.

## Automatic first-start migration

Migration runs only for persistent Server mode. Given an existing v1 directory:

```bash
epub-browser server /path/to/books \
  --server-dir /path/to/existing-v1-directory \
  --legacy-sync-dir /path/to/legacy-sync \
  --admin-username admin \
  --admin-password-file /path/to/admin-password \
  --watch
```

The first v2 start needs administrator credentials because all legacy
annotations, bookshelf rows, and reading progress are assigned to that account
inside the same rollback-safe schema upgrade. Prefer a mode-`0600` secret file.
The environment equivalents are `EPUB_BROWSER_ADMIN_USERNAME` and
`EPUB_BROWSER_ADMIN_PASSWORD_FILE`; `EPUB_BROWSER_ADMIN_PASSWORD` is a less
private fallback only when no file is configured. A configured empty or
unreadable file fails closed and does not fall back to plaintext environment
content. After an administrator exists, retries and ordinary restarts no longer
read or require any bootstrap secret.

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

Starting with v2.0.5, the default identity carrier is the visible adjacent file `BOOK.epub.epub-browser.json`. Its `book_id` is the same value used as URL/client `book_hash`, and the EPUB itself is not rewritten. `--book-id-storage embedded` instead stores that ID in OPF metadata for the whole invocation and may rebuild the EPUB ZIP.

Both carriers are checked before mutation. Conflicting IDs, duplicate active copies, or ambiguous inactive/move candidates stop that source instead of guessing. Server only reuses generated content when the established source fingerprint agrees with its database record and the cache remains valid; a sidecar fingerprint alone is not reuse evidence.

Existing v2.0.4 OPF IDs migrate without an EPUB write: v2.0.5 creates a same-ID sidecar and leaves the embedded metadata intact. Switching in either direction creates the selected carrier but never removes or refreshes the non-selected carrier. No SQLite schema migration is required for this change.

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

Visible sidecars do not alter the EPUB and can be retained during rollback. v2.0.4 does not understand sidecar-only identities; before rolling back an SSG deployment that must keep identical public URLs, run v2.0.5 once with `--book-id-storage embedded` so the same ID is also present in OPF metadata. EPUBs that already carried a v2.0.4 embedded ID need no identity conversion.

For a v2 retry instead of a downgrade, keep `data/epub-browser.db` and rerun the same `server --server-dir` command. Generated cache files may be removed without touching `data/`.

## Docker migration

The v2 image expects:

- `/app/Library`: EPUB input, read-write for default sidecar creation or refresh;
- `/app/EpubBrowserFiles`: required read-write persistent Server directory;
- `/app/SyncData`: optional read-only legacy JSON import directory.
- `/run/secrets/epub-browser-admin-password`: recommended read-only first-start password file.

The container command now uses `epub-browser server` and listens on `0.0.0.0` inside the container. A read-only Library mount works only when every selected identity carrier already exists and matches the source; there is no database-only fallback. `--book-id-storage embedded` may rebuild the EPUB and is refused when doing so would be unsafe. Bind the host port to `127.0.0.1` unless a protected LAN or authenticated TLS reverse proxy is intended.

For example:

```bash
docker run -d \
  -p 127.0.0.1:8080:80 \
  -e EPUB_BROWSER_ADMIN_USERNAME=admin \
  -e EPUB_BROWSER_ADMIN_PASSWORD_FILE=/run/secrets/epub-browser-admin-password \
  --mount type=bind,src=/path/to/admin-password,dst=/run/secrets/epub-browser-admin-password,readonly \
  -v /path/to/books:/app/Library:rw \
  -v /path/to/existing-v1-directory:/app/EpubBrowserFiles \
  epub-browser:2.0.5
```

The container command uses `epub-browser server --watch`, listens on `0.0.0.0`
inside the container, and retains authoritative data only through the mounted
`/app/EpubBrowserFiles` volume. Bind the host port to `127.0.0.1` unless a TLS
reverse proxy is intended. When a proxy supplies identity headers, enable
`--cookie-secure`, trust only the direct proxy network with
`--trusted-proxy-cidr`, configure the subject header and issuer together, and
make the proxy strip client-supplied copies of those headers. A public client
network is never an appropriate trusted-proxy CIDR.
