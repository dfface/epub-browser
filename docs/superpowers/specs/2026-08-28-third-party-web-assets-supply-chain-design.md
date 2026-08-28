# Third-Party Web Asset Supply Chain Design

**Date:** 2026-08-28

**Status:** Pending written-spec review

## Summary

EPUB Browser currently keeps several third-party JavaScript, CSS, font, and
theme files inside `epub_browser/assets/`. Those files are required at runtime,
but they are not authored as EPUB Browser source and their provenance is not
described by one reproducible contract.

Before PDF support adds PDF.js, the project will introduce a locked, verified
asset supply chain. Git will track a human-reviewable lock manifest, licenses,
notices, and the synchronization tool. Generated vendor files will not be
tracked in the source tree. Release jobs will fetch and verify exact upstream
artifacts before building, while wheels, source distributions, and Docker final
images will remain self-contained and require no runtime network access.

This is a build-time change only. It does not change EPUB processing, Server
content caches, SQLite data, public APIs, or SSG runtime behavior.

## Goals

- Make every third-party browser asset attributable to an exact upstream
  package, version, archive digest, license, and allowlisted output file.
- Keep generated third-party blobs out of Git without making installed wheels,
  source distributions, Docker images, or SSG output depend on a CDN.
- Make developer, CI, PyPI, and Docker builds use the same lock and verifier.
- Reject altered, mutable, incomplete, unexpectedly large, or unsafe archives.
- Preserve current logical runtime behavior while relocating all third-party
  browser files under one generated vendor tree.
- Add PDF.js through this mechanism rather than as a special-case download.
- Support a completely offline wheel build from the published source
  distribution.

## Non-goals

- Downloading assets when EPUB Browser starts, when a reader opens a page, or
  when a user installs an already-built wheel.
- Depending on public CDNs from generated SSG or Server pages.
- Treating `git clone` of a mutable branch or tag as a reproducible source.
- Building upstream JavaScript projects from arbitrary source checkouts when an
  official release or npm package already contains the required distribution.
- Automatically accepting upstream version updates.
- Reformatting, minifying, bundling, or otherwise modifying third-party code in
  ways not described by the lock.

## Repository layout and ownership

Git tracks:

```text
third_party/assets.lock.json
third_party/README.md
THIRD_PARTY_NOTICES.md
tools/sync_vendor_assets.py
```

The synchronization tool generates:

```text
epub_browser/assets/vendor/<package>/<allowlisted-file>
```

`epub_browser/assets/vendor/` is ignored by Git. The ignore rule applies only
to generated vendor content; EPUB Browser-authored JavaScript, CSS, icons, and
templates remain normal tracked source files.

Existing third-party files at the root of `epub_browser/assets/` are migrated
to package-specific vendor directories. The initial audit includes at least:

- KaTeX;
- markdown-it;
- Mermaid;
- pinyin-pro;
- highlight.js and the shipped highlight themes;
- Fancybox;
- SortableJS;
- web-highlighter;
- Font Awesome CSS and fonts;
- PDF.js when PDF support is implemented.

The migration must first classify every candidate as project-authored or
third-party. Ambiguous files stay tracked until provenance is established; the
tool must not guess ownership from a filename.

## Lock manifest

`third_party/assets.lock.json` is deterministic UTF-8 JSON with a top-level
schema version and a package list in stable order. Each package records:

```json
{
  "name": "pdfjs-dist",
  "version": "<exact-version>",
  "source": {
    "kind": "npm-tarball",
    "url": "<immutable-official-url>"
  },
  "archive": {
    "sha256": "<64-lowercase-hex>",
    "max_bytes": 0,
    "max_expanded_bytes": 0
  },
  "license": {
    "spdx": "Apache-2.0",
    "files": ["LICENSE"]
  },
  "files": [
    {
      "source": "package/build/pdf.mjs",
      "target": "pdfjs/pdf.mjs",
      "sha256": "<64-lowercase-hex>"
    }
  ]
}
```

Exact field names may be refined in the implementation plan, but the contract
must retain the following properties:

- the upstream version and URL are exact, not ranges or moving aliases;
- the complete downloaded archive has a SHA-256 digest and size bound;
- extraction is an explicit source-to-target allowlist;
- every installed file has an expected digest;
- all required license files are extracted and verified;
- targets are relative paths below the generated vendor root;
- duplicate package names, duplicate targets, unknown fields in a supported
  schema, and non-canonical paths are rejected rather than silently normalized.

An official release archive or npm registry tarball is preferred. A CDN URL is
acceptable only when it identifies immutable, versioned bytes and those bytes
are independently locked by digest. `git clone`, a branch URL, `latest`, a
semver range, or a URL whose response changes without its identity changing is
not accepted.

## Synchronization command

The project-owned command is:

```bash
python tools/sync_vendor_assets.py fetch
python tools/sync_vendor_assets.py verify
python tools/sync_vendor_assets.py clean
```

### `fetch`

`fetch` downloads each missing archive into a temporary directory, enforces the
compressed-size limit while streaming, verifies the archive SHA-256 before
extraction, and extracts only allowlisted regular files. It writes generated
files atomically and then runs the same checks as `verify`.

An already-correct generated tree requires no network request. A present but
incorrect file is an error unless the user explicitly runs `fetch`, at which
point it is replaced only after the new archive has passed all verification.

### `verify`

`verify` is completely offline. It checks the manifest schema, installed file
set, file digests, license files, and package-specific invariants. Extra files
under a managed package directory fail verification. Missing generated assets
produce one actionable command rather than an import-time Python error.

For PDF.js, verification also requires the main module and worker to come from
the same locked package and version. The application never mixes a CDN worker
with a locally packaged main module.

### `clean`

`clean` removes only paths owned by the current lock under
`epub_browser/assets/vendor/`, plus empty package directories. It refuses a
target outside that exact generated root and does not recursively delete the
asset directory, repository root, user-provided paths, or unknown files.

## Archive and filesystem safety

Before extraction, the tool rejects:

- absolute paths, drive-qualified paths, NUL bytes, and `..` traversal;
- symbolic links, hard links, device files, FIFOs, sockets, and other
  non-regular entries;
- duplicate normalized member paths;
- entries or total expansion beyond the manifest bounds;
- allowlisted members whose actual type or digest differs from the lock;
- targets that traverse or resolve through a symlink outside the vendor root;
- archive formats or compression methods not explicitly supported.

The downloader follows only a small bounded number of HTTPS redirects and
rejects a redirect to a non-HTTPS URL. Network, hash, schema, license, and
filesystem errors name the package and failed stage without dumping response
bodies, credentials, or arbitrary archive content.

## Build and release flow

### Local development

A source checkout does not silently access the network. A developer explicitly
runs `fetch` once, then normal tests and application commands consume the
verified generated tree. Fast tests may use checked-in miniature fixture
archives; tests never contact upstream package servers.

### Wheels

The build pipeline runs `fetch` and `verify` before `python -m build`. Generated
vendor assets and their licenses are included as package data in the wheel.
Installing and running the wheel is offline and does not contain the sync tool
as a runtime requirement.

### Source distributions

The release checkout is hydrated and verified before the source distribution
is created. The sdist includes the verified generated assets, licenses, lock,
notices, and build metadata required to build a wheel without network access.
This is intentional: generated files are absent from Git but present in the
published source artifact.

CI must unpack the sdist in a network-disabled environment, build a wheel, and
compare its required vendor file inventory with the directly built wheel.

### Docker

The Docker builder stage fetches and verifies assets, builds the wheel, and
tests its contents. The final stage receives only the built application and
runtime files. It contains no archive cache, Git metadata, compiler checkout,
or build-time downloader invocation.

### GitHub Pages and PyPI workflows

Release workflows move from direct `python setup.py sdist bdist_wheel` calls to
the standards-based `python -m build` flow. GitHub Pages uses the same hydrated
wheel or verified source tree and emits no CDN URLs. Dependency download
failure stops the build rather than producing a partially functional site.

## Runtime asset publishing

The existing asset publisher remains responsible for immutable hashed runtime
URLs. Relocation into `assets/vendor/<package>/` changes source paths, not the
public caching model. Application templates continue to request logical assets
through the publisher instead of embedding upstream URLs.

SSG output contains every required browser asset. Server restarts immediately
pick up a newly built asset set through the existing publisher and do not
require EPUB reconversion or a `SERVER_OUTPUT_REVISION` increase.

## Licensing and notices

Every locked package must have an identified license compatible with the way it
is redistributed. `THIRD_PARTY_NOTICES.md` lists package name, exact version,
upstream project, source archive, license identifier, copyright notice where
required, and the installed files that use it.

Required upstream license or notice files travel in wheels, sdists, Docker
images, and other release artifacts. A package with a missing, unexpected, or
unreviewed license cannot be fetched into a releasable build merely because its
code hash matches.

The lock records facts; it does not make a legal compatibility decision.
Upgrading or adding a package requires reviewing both the code diff and license
change before updating the lock and notices.

## Migration sequence

1. Inventory current third-party assets, their versions, upstream archives,
   digests, and licenses.
2. Add the lock, notices, sync tool, offline fixtures, and verification tests
   while current files are still tracked.
3. Hydrate a generated vendor tree and update logical application asset paths.
4. Prove SSG and Server behavior against the generated tree.
5. Remove only the audited third-party blobs from Git and add the narrow ignore
   rule.
6. Update wheel, sdist, Docker, PyPI, and GitHub Pages builds.
7. Add PDF.js as a new locked package only after the supply chain gates pass.

The migration should be reviewable package by package. Project-authored assets
must not be moved simply to make the directory structure uniform.

## Verification and acceptance

Automated tests cover:

- lock schema validation and deterministic ordering;
- correct fetch, offline verify, idempotent fetch, and narrow clean behavior;
- archive traversal, link, duplicate-path, compressed-size, expansion-size,
  redirect, unexpected-file, missing-license, and digest failures;
- tampering with an archive and with an installed file;
- application asset publication with no runtime CDN or upstream URL;
- SSG and Server smoke tests with a fully hydrated tree;
- wheel and sdist inventories, including licenses and notices;
- network-disabled sdist-to-wheel construction;
- Docker final-image smoke tests and absence of build caches;
- PDF.js main/worker version and digest agreement;
- a Git check that generated vendor blobs are not tracked.

Release acceptance requires `python -m build`, installation from the produced
wheel, an offline wheel build from the produced sdist, relevant SSG and Server
tests, and `git diff --check`.

## References

- [Python packaging flow](https://packaging.python.org/en/latest/flow/)
- [Python package distribution formats](https://packaging.python.org/en/latest/discussions/package-formats/)
- [PyPA build-tool recommendations](https://packaging.python.org/en/latest/guides/tool-recommendations/)
