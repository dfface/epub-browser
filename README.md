# EPUB Browser

> A personal EPUB reader and static-site generator. Read privately. Publish anywhere.

<p align="center">
  <img src="https://github.com/dfface/epub-browser/blob/aff1def01252481f74c25ebf5b17d142b7db3c5e/epub_browser/assets/logo-lockup-color.png" alt="EPUB Browser logo" width="520">
</p>

[![PyPI version](https://img.shields.io/pypi/v/epub-browser)](https://pypi.org/project/epub-browser/)
[![Python versions](https://img.shields.io/pypi/pyversions/epub-browser)](https://pypi.org/project/epub-browser/)
[![License](https://img.shields.io/github/license/dfface/epub-browser)](License.txt)

EPUB Browser v2 has two explicit product modes:

- `ssg` generates a complete static-site snapshot for Pages, object storage, Nginx, or any other static host.
- `server` runs a stateful reading service with durable SQLite data, an incremental generated cache, optional file watching, and browser APIs.

Choose the mode from what you are deploying—not from whether a build step happens internally.

## Install

```bash
pip install epub-browser
```

Python 3.9 or newer is required.

## SSG: generate a static site

Generate a site for a domain root:

```bash
epub-browser ssg /path/to/books \
  --output-dir /path/to/dist
```

For GitHub Pages or another project subpath, set the public URL prefix explicitly:

```bash
epub-browser ssg /path/to/books \
  --output-dir /path/to/dist \
  --base-path /my-repository/
```

`--base-path` changes generated browser URLs; it does not change the output directory. For example, `--base-path /my-repository/` makes links, manifests, icons, book metadata, and Service Worker entries start with `/my-repository/` while files are still written directly inside `dist/`.

SSG activation is transactional: EPUB Browser builds and validates a sibling staging snapshot, then replaces the destination. A failed conversion leaves the previous output untouched. SSG output contains no Server database, migration state, or runtime cache metadata.

Browser-local bookshelf data remains local unless you use the existing manual Sync action against a compatible endpoint. Static reading progress and annotations stay in browser storage and do not probe EPUB Browser Server APIs.

## Book identity storage

EPUB Browser gives every book a stable `book_id`; this is the same value exposed as `book_hash` in generated URLs and browser data. The default for SSG, Server, `--watch`, and legacy command syntax is:

```bash
--book-id-storage sidecar
```

Sidecar mode stores the identity in a visible file beside the source, for example `BOOK.epub.epub-browser.json`. It preserves the EPUB byte-for-byte. The sidecar also records a verified SHA-256 source fingerprint, which Server combines with database state and cache validation when deciding whether generated content can be reused.

To store the same ID inside OPF metadata instead, opt in for the entire command invocation:

```bash
--book-id-storage embedded
```

Embedded mode may rebuild the EPUB ZIP and is refused for sources that cannot be changed safely. There is no database-only fallback: the selected carrier must already be valid or be writable. EPUB Browser reads both carrier types before writing and stops on disagreeing IDs, duplicate active IDs, or ambiguous move candidates.

When upgrading from v2.0.4, an existing embedded ID is copied to the default sidecar without rewriting the EPUB or deleting its OPF metadata. Switching storage modes likewise creates the selected carrier with the existing ID and leaves the other carrier intact.

## Server: run a persistent reading library

For a private local library:

```bash
epub-browser server /path/to/books \
  --server-dir /path/to/epub-browser-state \
  --watch
```

Server binds to `127.0.0.1` by default. This is the safe default for one machine. To make it reachable on a trusted LAN, opt in explicitly:

```bash
epub-browser server /path/to/books \
  --server-dir /path/to/epub-browser-state \
  --watch \
  --host 0.0.0.0 \
  --port 8080 \
  --no-browser
```

Do not expose the built-in Server directly to the public internet. Put it behind a TLS reverse proxy with authentication and appropriate network controls.

For a disposable session, use `--ephemeral` instead of `--server-dir`:

```bash
epub-browser server book.epub --ephemeral
```

- Initial and watch scans appear in the Server library page; Server mode does not use terminal tqdm.
- Interactive terminals print the bound URL once. Docker/systemd runs stay quiet unless `--log` is enabled.
- A successful scan summary closes automatically; failures remain visible until dismissed. Fixing or replacing the EPUB lets `--watch` start the next scan—there is no manual retry endpoint.

### Server storage contract

```text
<server-dir>/
├── .server.lock                 # reusable process-lock metadata
├── data/
│   ├── epub-browser.db          # durable books, annotations, bookshelf sync, progress
│   ├── migration-state.json     # restart-safe v2 migration state
│   └── backups/                 # verified pre-migration database copies
└── cache/
    ├── catalog.json             # generated-cache status
    ├── public/                  # served HTML, assets, and converted books
    └── staging/                 # replaceable conversion work
```

Only `data/` is authoritative. `cache/` can be deleted: the next start rebuilds it while retaining durable book IDs and user data. `.server.lock` remains as harmless diagnostic metadata after shutdown; an operating-system lock, rather than its recorded PID, controls exclusivity. Public files are never written at the Server root in the v2 layout.

In Server mode, the bookshelf is stored as a versioned cloud document in the Server database and saves automatically after every change. Users must sign in with the existing username setting before using it. SSG mode keeps local bookshelf data and provides Import and Export; it has no Sync action.

## Docker

The image runs persistent Server mode. Mount EPUB input read-write so the default sidecars can be created and refreshed, and mount Server state read-write:

```bash
docker run -d \
  --name epub-browser \
  -p 127.0.0.1:8080:80 \
  -v /path/to/books:/app/Library:rw \
  -v /path/to/epub-browser-state:/app/EpubBrowserFiles \
  epub-browser:2.0.5
```

`/app/EpubBrowserFiles` must be writable and persistent. `/app/Library:rw` permits default sidecar creation and fingerprint refresh. A read-only input mount works only when every selected sidecar or embedded carrier already exists and matches; EPUB Browser no longer falls back to a database-only ID. Using `--book-id-storage embedded` opts into EPUB ZIP rebuilding and may be refused for signed, linked, read-only, or unsupported sources. Mount `/app/SyncData:ro` only when legacy bookshelf JSON needs to be imported:

```bash
-v /path/to/legacy-sync:/app/SyncData:ro
```

The container intentionally binds the process to `0.0.0.0`; control exposure with the published Docker port, firewall, and reverse proxy.

## Legacy v1 command compatibility

v2 accepts the v1 syntax for the full v2 major line and maps it to one of the new modes:

| v1 command shape | v2 equivalent |
| --- | --- |
| `epub-browser BOOKS` | `epub-browser server BOOKS --ephemeral` |
| `epub-browser BOOKS --output-dir STATE` | `epub-browser server BOOKS --server-dir STATE` |
| `epub-browser BOOKS --no-server --output-dir DIST` | `epub-browser ssg BOOKS --output-dir DIST` |
| `--sync-dir DIR` | `server --legacy-sync-dir DIR` |

With `--log`, legacy invocation prints the equivalent v2 command. Without `--log`, the adapter stays quiet. Legacy temporary `--keep-files` is retained; persistent Server directories are already permanent.

See [Migrating to v2](docs/migration-v2.md) for backup, automatic data migration, conflict recovery, and rollback details.

## Useful options

```bash
epub-browser ssg --help
epub-browser server --help
```

| Mode | Option | Purpose |
| --- | --- | --- |
| SSG | `--output-dir`, `-o` | Required static snapshot destination. |
| SSG | `--base-path` | Public URL prefix, default `/`. |
| Server | `--server-dir` | Persistent data and cache root. |
| Server | `--ephemeral` | Disposable Server root; mutually exclusive with `--server-dir`. |
| Server | `--watch`, `-w` | Reconcile source changes automatically. |
| Server | `--host` | Bind address, default `127.0.0.1`. |
| Server | `--port`, `-p` | Bind port, default `8000`. |
| Server | `--legacy-sync-dir` | Read legacy bookshelf JSON during migration. |
| Both | `--book-id-storage sidecar\|embedded` | Select one identity carrier for the entire invocation; default `sidecar`. |
| Both | `--log` | Show operational detail without corrupting progress output. |

## Reading features

- Recursive EPUB and Calibre-library discovery, metadata tags, search, and pinyin search.
- Scrolling, page turning, continuous reading, custom fonts and CSS, themes, and pure reading mode.
- Highlights and notes with browser or Server-backed annotation storage where available.
- Nested bookshelf groups, tags, JSON import/export, and the existing optional manual sync.
- PWA manifests and content-addressed static assets.
- English and Simplified Chinese browser UI.

Kindle/Silk browsers receive an e-reader-friendly mode; browser-heavy features may be reduced.

## Data safety and migration

Persistent Server startup automatically checks for the v1 root database, verifies it, creates a backup, upgrades a copied database, imports eligible legacy bookshelf JSON, and only then removes the migrated root database. Legacy public files are retired in two successful startup phases and are never treated as authoritative data.

If both `epub-browser.db` and `annotations.db` exist at the legacy root, startup stops with a conflict instead of guessing. Corrupt databases are also left untouched. See [docs/migration-v2.md](docs/migration-v2.md).

## Contributing

Issues and pull requests are welcome at [dfface/epub-browser](https://github.com/dfface/epub-browser). A useful report includes the EPUB when it can be shared, the exact command, browser/device, and reproduction steps.

## License

[MIT](License.txt)
