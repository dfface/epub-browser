# EPUB Browser SSG and Server Mode Architecture

## Status

Approved design for the next architecture revision. This is a breaking change in command structure and on-disk layout, with a compatibility adapter for legacy commands and automatic migration for persistent Server data.

## Context

EPUB Browser currently runs one generation pipeline for both static export and local serving. In both cases it produces a static library root containing `index.html`, `book-metadata.json`, `sw.js`, `assets/`, and `book/`. Server mode then adds `epub-browser.db` to that same directory and serves it with Uvicorn and Starlette.

That layout works well for small personal libraries, but it mixes three classes of files with different lifecycles:

- deployable static output that should be replaced as one complete snapshot;
- permanent user data such as annotations, bookshelves, and reading progress;
- derived conversion caches and temporary files that can be deleted and rebuilt.

The current CLI also describes static generation indirectly through `--no-server`. This hides the fact that static generation and the stateful Server are different product modes, not merely different phases of one command.

## Goals

1. Establish two explicit top-level modes: `ssg` and `server`.
2. Treat SSG output as a complete, deterministic, independently deployable static site.
3. Treat Server output as a rebuildable cache, with permanent state in a separate data directory.
4. Keep original EPUB files outside Server-owned storage and access them read-only.
5. Update Server libraries incrementally, one book at a time, without rebuilding the entire library.
6. Preserve book identity, annotations, bookshelves, and reading progress across content updates and upgrades.
7. Automatically migrate the current Server layout and earlier database formats.
8. Preserve legacy command invocations through a thin compatibility adapter while documenting only the new commands.
9. Make local-only network access the safe default.
10. Update the Dockerfile, README, CLI help, upgrade guide, and release notes as part of the change.
11. Preserve clean command-line progress output: without `--log`, routine diagnostics must not interrupt tqdm progress bars.

## Non-goals

- Implementing full user authentication or authorization.
- Replacing SQLite with another database.
- Redesigning annotation, bookshelf, or reading-progress product behavior.
- Adding Server deployment under an HTTP subpath. Server `root-path` support remains a separate project.
- Adding partial-success SSG builds.
- Copying or importing original EPUB files into Server-managed storage.
- Redesigning the reader UI.

## Product modes

### SSG mode

SSG is a static-site generator. Its output is the final product and can be copied directly to GitHub Pages, Cloudflare Pages, Nginx, Apache, object storage, or another static host.

SSG has no Server database, migration state, synchronization API, or runtime cache metadata. Any browser-local annotations or progress remain browser-local unless the generated site is integrated with a separate service.

### Server mode

Server is a stateful reading service. It owns permanent application data, derived book caches, source monitoring, incremental conversion, HTTP APIs, and runtime health state.

The Server reuses the shared EPUB conversion core, but its generated pages are caches rather than deployment artifacts. Deleting the cache must never delete annotations, bookshelves, reading progress, or the durable mapping between a book and its identifier.

## Architecture

```text
CLI
├── ssg
├── server
└── LegacyCommandAdapter
        │
        ▼
Shared EPUB Conversion Core
├── EPUB parsing
├── metadata and TOC extraction
├── chapter rendering
├── resource copying
└── shared frontend asset publishing
        │
        ├── SSGPublisher
        │   ├── complete library build
        │   ├── base-path URL generation
        │   ├── snapshot validation
        │   └── transactional publication
        │
        └── ServerApplication
            ├── SourceCatalog
            ├── BookCache
            ├── StateStore
            ├── LibraryWatcher
            ├── MigrationManager
            └── HTTP/API
```

### Shared conversion core

The conversion core converts one EPUB into a caller-provided staging directory. It may parse metadata, render pages, copy EPUB resources, and publish shared frontend references, but it must not:

- select the final site or cache directory;
- create or modify the Server database;
- delete a library root;
- decide whether an output is permanent;
- calculate the final Server book identity.

The caller supplies the book ID and URL-generation policy. This permits SSG to use deterministic IDs while Server uses durable IDs stored in SQLite.

### SSGPublisher

`SSGPublisher` owns complete-library discovery, deterministic ordering, parallel conversion, root page generation, static URL generation, snapshot validation, and publication of the final output directory.

### ServerApplication

`ServerApplication` owns the long-running lifecycle. It coordinates source discovery, persisted book identities, cache validation, background conversion, source watching, the SQLite state store, migration, health, and HTTP serving.

### LegacyCommandAdapter

The legacy adapter only translates old arguments into a new SSG or Server configuration object. It must not preserve or fork the old execution pipeline.

## CLI contract

### New commands

```bash
epub-browser ssg <source...> \
  --output-dir <dist> \
  [--base-path /]

epub-browser server <source...> \
  (--server-dir <dir> | --ephemeral) \
  [--watch] \
  [--host 127.0.0.1] \
  [--port 8000] \
  [--no-browser] \
  [--log] \
  [--legacy-sync-dir <dir>]
```

Both modes accept one or more EPUB files or directories as sources. Directory discovery continues to recurse while excluding hidden path components.

### SSG options

- `--output-dir` is required and identifies the final static publication directory.
- `--base-path` defaults to `/` and specifies the public URL path at which the site will be hosted.
- `--base-path` is normalized to a leading and trailing slash. Schemes, hosts, query strings, fragments, backslashes, and `..` segments are rejected.
- SSG does not accept Server-only options.

For example, a GitHub Pages project site uses:

```bash
epub-browser ssg ./books \
  --output-dir ./dist \
  --base-path /epub-library/
```

`--output-dir` is a filesystem path. `--base-path` is a public URL path. They are intentionally independent.

### Server options

- Persistent mode requires `--server-dir`.
- Temporary use requires the explicit `--ephemeral` option.
- `--server-dir` and `--ephemeral` are mutually exclusive.
- `--watch`, `--host`, `--port`, `--no-browser`, `--log`, and `--legacy-sync-dir` are Server-only options.
- Server binds to `127.0.0.1` by default. LAN or container access requires an explicit `--host 0.0.0.0` or another bind address.

### Legacy compatibility mapping

If the first argument is `ssg` or `server`, only the new parser is used. Otherwise the legacy adapter applies these mappings:

| Legacy invocation | New equivalent |
| --- | --- |
| `epub-browser <source> --output-dir <dir>` | `epub-browser server <source> --server-dir <dir>` |
| `epub-browser <source> --no-server --output-dir <dir>` | `epub-browser ssg <source> --output-dir <dir>` |
| `epub-browser <source>` | `epub-browser server <source> --ephemeral` |
| `--sync-dir <dir>` | `--legacy-sync-dir <dir>` |
| Server options such as `--watch` and `--port` | Same Server option |

`--keep-files` with a persistent legacy `--output-dir` becomes a no-op because `server-dir` is permanent by definition. The adapter accepts it and explains the new behavior. Legacy temporary mode with `--keep-files` remains compatible for the compatibility period: it prints the generated directory and does not delete it, while recommending an explicit `--server-dir`.

Every legacy invocation prints one concise deprecation message containing its equivalent new command. The old commands remain supported throughout the new major release. Removing them requires a later breaking release.

## SSG directory contract

`output-dir` is fully owned by SSG. A successful publication has this structure:

```text
<output-dir>/
├── index.html
├── book-metadata.json
├── sw.js
├── assets/
│   ├── asset-manifest.json
│   ├── manifest.json
│   └── immutable/
└── book/
    └── <book-id>/
        ├── index.html
        ├── toc.json
        ├── chapter_0.html
        ├── chapter_1.html
        └── resources/
```

SSG does not preserve unrelated files already present in `output-dir`. Documentation and CLI help must state that the directory is replaced as a complete publication.

The build is created in a sibling staging directory named like `.<output-name>.staging-<id>`. After validation, platforms that support direct directory exchange use it. Other platforms use a rollback-capable sequence:

1. rename the current output to a sibling previous directory;
2. rename staging into the final location;
3. restore the previous directory if activation fails;
4. remove the previous directory only after activation succeeds.

The implementation must refuse obviously dangerous publication targets such as a filesystem root, the source directory itself, or a source EPUB path.

## Server directory contract

Original EPUB files remain external:

```text
<source>/
└── *.epub
```

Persistent Server state uses one user-facing directory:

```text
<server-dir>/
├── .server.lock
├── data/
│   ├── epub-browser.db
│   ├── migration-state.json
│   └── backups/
│       └── pre-migration-<timestamp>.db
└── cache/
    ├── catalog.json
    ├── public/
    │   ├── index.html
    │   ├── book-metadata.json
    │   ├── sw.js
    │   ├── assets/
    │   └── book/
    │       └── <book-id>/
    ├── staging/
    │   └── <conversion-job-id>/
    └── legacy-public/
```

`data/` is permanent. EPUB Browser never automatically deletes it. `cache/` is derived and may be deleted in full; Server must reconstruct it from the source EPUBs and the durable book registry. `cache/catalog.json` is an acceleration and diagnostic artifact, not the authority for book identity.

`cache/staging/` is on the same filesystem as `cache/public/`, permitting directory rename when a converted book is activated. Staging directories left by a crash are removed at the next startup.

`server-dir` must not be inside a watched source directory. A source file or directory must not be inside `server-dir`. These constraints prevent recursive monitoring and accidental treatment of managed files as source material.

Ephemeral mode creates the same logical layout under a temporary directory, reports its location, and removes only the directory it created when the process stops normally.

## Book identity and source fingerprints

Server identity and source version are separate concepts.

### Durable Server book ID

Server stores an authoritative book registry in SQLite:

```text
books
├── book_id
├── source_path
├── epub_identifier
├── source_fingerprint
├── source_size
├── source_mtime_ns
├── metadata_json
├── active
├── created_at
└── updated_at
```

`book_id` is permanent and is used in URLs and existing API/database fields named `book_hash`. Those existing names remain compatible even though the value is conceptually a book ID.

New Server books receive `base64url(UUIDv4.bytes)` without padding, producing a 22-character URL-safe durable identifier. Content updates never change it. Path-preserving changes match through the existing registry. A watcher move event transfers the same ID to the destination path. When a file was moved while Server was offline, Server may match a unique EPUB package identifier and content fingerprint. If a match is ambiguous, it creates a new book record rather than guessing and corrupting identity.

During migration, existing book hashes remain the `book_id`. Server computes the legacy TOC-based hash for discovered source EPUBs and correlates it with the old `book-metadata.json` and old `book/<hash>/` directories. Existing annotations or progress whose book cannot be correlated remain in the database and are never deleted.

Deleting a source marks its book record inactive and removes it from the active library index. It does not delete the record, annotations, bookshelves, progress, or durable ID. A source that reappears and can be identified safely reactivates the same record.

### Source fingerprint

The source fingerprint is a SHA-256 content digest and represents the cached version. Size and nanosecond modification time are stored as a fast unchanged check. When either quick attribute changes, Server recomputes the digest. A changed digest queues conversion while leaving the durable ID unchanged.

### Embedded SSG book ID

SSG reads a durable application ID from the primary OPF package metadata. When the
metadata is absent, it generates `base64url(UUIDv4.bytes)` without padding and safely
writes it into the source EPUB as `epub-browser:book-id` before conversion. Metadata,
spine, TOC, source path, and content changes never change this ID.

Writing is atomic and changes only the primary OPF ZIP entry. The publisher validates
the rewritten archive before replacing the source, preserves all non-OPF entries and
container metadata, and refuses to rewrite signed, read-only, hard-linked, or
non-conforming containers. SSG rejects duplicate embedded IDs and identifies all
conflicting input files rather than overwriting one book.

## SSG build flow

```text
discover and stably sort EPUBs
→ parse metadata and derive SSG IDs
→ reject duplicate IDs
→ convert all books into staging
→ publish immutable shared assets
→ generate root metadata and index
→ generate all URLs with the base-path policy
→ validate the complete snapshot
→ transactionally activate output-dir
```

Conversion may run concurrently, but final metadata and generated ordering are deterministic. The same input set, application version, and options must produce equivalent logical output regardless of thread completion order.

Any book conversion failure fails the complete SSG build. The process gathers and reports all book-level failures, retains the previously published output unchanged, and removes only its staging directory. There is no initial `--allow-partial` option.

Snapshot validation includes:

- every book has `index.html`, `toc.json`, and its referenced chapter files;
- `book-metadata.json` agrees with the directories present under `book/`;
- every generated internal asset, cover, manifest, and Service Worker precache reference exists;
- all internal URLs contain the normalized `base-path`;
- output contains no absolute local paths, temporary paths, Server API URLs, database files, migration files, or Server cache metadata.

A shared URL builder generates correct paths during publication. Generated pages must not rely on post-load JavaScript to repair root-relative resource paths.

## Server startup and incremental update flow

Persistent Server startup follows this sequence:

```text
acquire server lock
→ migrate and open state store
→ validate or create shared public shell
→ scan source EPUBs
→ resolve durable book identities
→ reuse valid cached versions
→ queue missing or stale books
→ start HTTP when the base shell is ready
→ reconcile books in the background
→ start watcher when requested
```

An existing valid cache permits fast startup. First startup exposes the base library shell after it is ready, then adds books as successful conversions complete.

For each changed book:

```text
debounce and coalesce source events
→ capture expected source fingerprint
→ convert into a unique staging directory
→ validate the generated book
→ verify source fingerprint is still current
→ atomically replace cache/public/book/<book-id>/
→ transactionally update the books table
→ atomically regenerate library index and metadata
```

Only one conversion job for a given source may commit at a time. If the source changes again during conversion, the stale result is discarded and a new job is queued.

Conversion failure for an existing book leaves its previous cache and database record active and reports degraded status. Failure for a new book leaves it out of the public index until conversion succeeds.

Root HTML and JSON files are written to temporary siblings and renamed into place. Shared project assets remain content-addressed under `assets/immutable/`.

## Automatic migration

Migration runs only for persistent Server mode. Ephemeral mode never imports an old layout automatically.

### Detection

Database candidates are checked in this order:

```text
<server-dir>/data/epub-browser.db
<server-dir>/epub-browser.db
<server-dir>/annotations.db
```

If `data/epub-browser.db` exists, it is authoritative and only normal schema migration applies; legacy root candidates are left untouched and reported as warnings. If the data database does not exist and exactly one legacy candidate exists, that candidate is migrated. If both root-level legacy candidates exist, Server fails safely with explicit paths and recovery instructions, even when one has the newer filename. It never guesses or overwrites one database with another.

### Transactional data migration

```text
acquire migration lock
→ detect layout and schema versions
→ run SQLite integrity_check
→ copy source database to data/backups/
→ create or copy data/epub-browser.db
→ run schema migrations in a transaction
→ import eligible legacy bookshelf JSON
→ validate migrated database
→ record data migration state
```

SQLite `PRAGMA user_version` records schema version. `data/migration-state.json` records filesystem migration phases, source paths, backup path, and completion. Re-running migration is idempotent.

The root-level legacy database remains untouched until the migrated data database passes integrity and schema validation and the migration state is durably recorded. Server then removes the root-level copy only after verifying that the backup has the same digest as the original. The verified backup under `data/backups/` is retained indefinitely unless the user removes it explicitly.

Migration adds the durable `books` registry without renaming compatibility fields used by existing annotation and progress APIs. Existing `annotations`, `bookshelves`, and `reading_progress` rows remain intact.

### Legacy bookshelf JSON

Migration scans both the explicit `--legacy-sync-dir` and the legacy Server root for files named `epub-browser-bookshelf-<username>-<version>.json`. It validates filenames and JSON, selects the highest valid version per user, and imports it only when SQLite does not already contain a newer or equal record. Source JSON files are not deleted.

### Legacy static output

Legacy root artifacts are known generated files only:

- `index.html`;
- `book-metadata.json`;
- `sw.js`;
- `assets/`;
- `book/`.

They are not user data. However, they remain untouched until the new cache is usable. A cache reconciliation is successful only when every discovered active source has either reused a validated cache or completed conversion successfully. After that condition is met, the legacy artifacts move to `cache/legacy-public/`. The next successful startup removes that cache backup. If reconciliation is incomplete, Server may operate in degraded mode but retains the old root artifacts for rollback and records the layout migration as pending.

Database backups are never removed by cache cleanup. Any migration failure leaves the old database and static output intact and exits with the migration error status. Server never accepts state-changing requests against a half-migrated database.

## HTTP and runtime states

Server mounts `cache/public/` for static reading surfaces and uses `data/epub-browser.db` for state APIs.

### Routes

```text
GET  /                                  library index
GET  /book/<book-id>/...                book pages and EPUB resources
GET  /assets/...                        shared frontend assets
GET  /book-metadata.json                active library metadata

GET  /api/health                        process liveness
GET  /api/ready                         database and base-shell readiness
*    /api/annotations/...               annotation API
*    /api/reading-progress/...          reading progress API
POST /sync                              bookshelf synchronization
```

The existing route and payload contracts remain compatible except for the addition of `/api/ready`.

### Runtime state model

```text
starting
→ migrating
→ scanning
→ ready
→ degraded
```

`/api/health` reports process liveness. `/api/ready` fails until migration, database validation, and the base public shell are usable. Once ready, individual book failures change status to degraded without taking the service offline.

Health responses may include runtime state, failed-book count, queued-task count, and database schema version. They must not expose local source paths, annotation contents, usernames, or other private data.

State-changing APIs reject requests before readiness. Normal API and HTML responses remain `no-cache`.

### HTTP cache policy

- `assets/immutable/`: `public, max-age=31536000, immutable`;
- `book/*/resources/`: `public, max-age=2592000`;
- HTML, JSON, Manifest, Service Worker, health endpoints, and APIs: `no-cache`.

### Network and identity boundary

Server defaults to `127.0.0.1`. Docker and intentional LAN use must pass `--host 0.0.0.0` explicitly.

This project does not add full authentication. Existing username semantics remain for data compatibility, but a client-supplied username or header is not a security boundary. Documentation must warn against direct public exposure. A reverse proxy deployed publicly must provide authentication and overwrite any trusted identity header rather than forwarding an arbitrary client value.

## Failure handling and concurrency safety

- A process lock allows only one Server to use a `server-dir` at a time.
- SIGINT and SIGTERM stop new conversion work and allow active database commits to complete.
- Persistent shutdown never deletes `data/` or activated caches.
- Ephemeral shutdown deletes only the temporary directory created for that invocation.
- Cache corruption triggers cache validation and rebuilding, not database deletion.
- Database corruption, migration conflict, or an unsupported newer schema version prevents startup.
- Disk-full and conversion errors leave the previous active book and public metadata in place.
- Generated EPUB extraction paths must remain within the job staging directory. ZIP path traversal is rejected.
- Book IDs, resource paths, and `base-path` values are normalized and cannot create `..` traversal.
- Source symlinks that escape a declared source root are not followed.
- Log output must not include annotation contents, notes, or other private user data.
- Without `--log`, routine conversion details, cache hits, watcher events, directory diagnostics, and request logs are silent. The CLI may still emit actionable errors, the one-time legacy migration hint, final command results, and tqdm progress itself.
- Messages that must be emitted while a tqdm bar is active use a tqdm-compatible writer rather than raw `print`, so progress rendering remains intact.
- With `--log`, verbose operational messages and Uvicorn informational logs are enabled through the same reporting boundary.

Exit statuses are stable:

| Status | Meaning |
| --- | --- |
| `0` | Normal completion or shutdown |
| `2` | CLI usage error |
| `3` | Database or migration error |
| `4` | SSG build failure |
| `5` | Server startup failure, including bind, lock, or permission errors |

## Docker contract

The Docker image uses the new Server command and keeps the existing persistent path so an upgraded container can detect the legacy layout:

```dockerfile
CMD [
  "epub-browser", "server", "/app/Library",
  "--server-dir=/app/EpubBrowserFiles",
  "--legacy-sync-dir=/app/SyncData",
  "--watch",
  "--host=0.0.0.0",
  "--no-browser",
  "--port=80"
]
```

Deployment documentation must mount:

- `/app/Library` read-only for source EPUBs;
- `/app/EpubBrowserFiles` read-write for permanent data and cache;
- `/app/SyncData` read-only when legacy bookshelf JSON migration is needed.

Stopping a container must preserve both `data/` and activated caches. The obsolete `--keep-files` option is not used.

## Documentation and release communication

The implementation is incomplete until these surfaces agree with the new architecture:

- README opening and quick start explain the SSG/Server product distinction.
- Separate SSG deployment and Server operation sections document their directory contracts.
- CLI `--help`, `ssg --help`, and `server --help` list only applicable options.
- Static deployment examples cover `/`, GitHub Pages project paths, and `--base-path`.
- Server examples cover local-only, LAN, Docker, and reverse-proxy safety.
- An upgrade guide documents legacy command mapping, automatic migration, backups, rollback, and conflict recovery.
- Release notes mark the command and layout changes prominently as a breaking architecture revision despite the compatibility adapter.
- Dockerfile and container examples use the new Server command and explicit bind address.

New documentation uses only `ssg` and `server`. Legacy syntax appears only in the migration section.

## Testing strategy

### Unit tests

- new CLI parsing and all legacy mappings;
- invalid cross-mode option rejection;
- `base-path` normalization and URL generation;
- embedded SSG ID generation, safe source rewriting, and collision reporting;
- durable Server ID and fingerprint separation;
- database schema version transitions;
- legacy database detection and conflict handling;
- legacy bookshelf JSON validation and version selection;
- cache manifest validation;
- archive extraction and output path safety.

### Integration tests

- migrate the current root `epub-browser.db` layout into `data/`;
- migrate the older `annotations.db` layout;
- recover safely from migration interruption;
- refuse conflicting legacy databases without modification;
- import legacy bookshelf JSON without overwriting newer database data;
- reuse valid Server caches across restart;
- rebuild cache after full cache deletion while retaining book IDs and annotations;
- update one EPUB without rebuilding unrelated books;
- preserve an old cached book when its update fails;
- remove and restore a source while retaining its durable ID;
- leave existing SSG output unchanged after a failed build;
- validate non-root `base-path` HTML, Manifest, and Service Worker references;
- prevent simultaneous Server use of one `server-dir`.

### End-to-end migration test

```text
run the current version
→ create annotations, bookshelf state, and reading progress
→ upgrade and start through the legacy command
→ verify automatic data and identity migration
→ restart with the new server command
→ verify all state, book URLs, and cache reuse
```

### Docker smoke test

- mount source EPUBs read-only;
- persist `/app/EpubBrowserFiles`;
- migrate an old data volume;
- verify the container binds on port 80 through explicit `--host=0.0.0.0`;
- stop and restart the container;
- verify database state and cache remain available.

## Delivery sequence

1. Introduce mode-neutral conversion and URL-generation seams while retaining behavior.
2. Add the new CLI configuration model and legacy adapter.
3. Implement SSG snapshot publication and base-path validation.
4. Add the Server directory model, durable books registry, cache manager, and incremental conversion.
5. Implement versioned, idempotent migration with backups and legacy identity correlation.
6. Move HTTP serving to `cache/public/`, add readiness state, and change the safe bind default.
7. Update Docker, README, CLI help, migration guide, and release notes.
8. Run migration, SSG, Server restart, and Docker end-to-end tests.

Each step must keep one execution path per mode. Compatibility code may translate inputs but may not call retained legacy orchestration.

## Acceptance criteria

- `epub-browser ssg` creates a complete static site with no Server state.
- `epub-browser server` stores durable state only under `server-dir/data` and derived output only under `server-dir/cache`.
- Original EPUBs remain external and are never copied into durable Server storage.
- Clearing Server cache preserves IDs, annotations, bookshelves, and progress.
- Updating one EPUB does not rebuild unrelated books or change its Server book ID.
- A failed book update leaves its old cached version available.
- A failed SSG build leaves the old publication unchanged.
- Non-root SSG deployments work without runtime DOM URL repair.
- Current and older database layouts migrate automatically with integrity checks and backups.
- Legacy commands enter the new implementation through a documented compatibility adapter.
- Server listens only on localhost unless the user explicitly requests another host.
- Running without `--log` does not interleave routine diagnostic output with tqdm progress bars.
- Docker upgrades retain persistent data and use the new command syntax.
- README, help output, upgrade documentation, Dockerfile, and release notes describe the same behavior.
