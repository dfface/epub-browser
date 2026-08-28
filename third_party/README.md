# Locked third-party browser assets

`assets.lock.json` is the reviewable manifest for browser assets copied into
`epub_browser/assets/vendor/` during the build. Each package records its exact
immutable npm tarball, archive and expansion limits, allowlisted output files,
SHA-256 values, and license files. The hydrated vendor tree is generated and
must not be committed.

## Developer workflow

A source checkout does not fetch dependencies implicitly. Hydrate the tree
once, verify it offline, run the supply-chain tests, and then build:

```bash
python3 tools/sync_vendor_assets.py fetch
python3 tools/sync_vendor_assets.py verify
python3 -m unittest tests.test_vendor_assets -v
python3 -m build
```

`fetch` is the only synchronization command that uses the network. It accepts
only the immutable HTTPS npm tarballs and files recorded in the lock. It
verifies archive and installed-file SHA-256 values, extraction bounds, and
licenses before atomically installing the allowlisted files. An already valid
tree is reused.

This statement applies to browser vendor assets: the standard isolated
`python3 -m build` command may separately consult a Python package index for
its build requirements.

`verify` is completely offline and fails on missing, extra, altered, linked,
or special files. To remove generated files owned by the current lock, run:

```bash
python3 tools/sync_vendor_assets.py clean
```

`clean` does not remove unknown files and never operates outside the generated
vendor root. Do not add hydrated files to Git; this hygiene check must print no
paths:

```bash
git ls-files epub_browser/assets/vendor
```

## Updating a browser dependency

Review the upstream release and its redistribution license before changing the
lock. Update the exact version, immutable tarball URL, archive digest and size
bounds, source-to-target allowlist, installed-file digests, license files, and
the corresponding entry in `THIRD_PARTY_NOTICES.md`. Then fetch into a clean
tree and run the developer commands above. Never use a mutable branch, tag,
version range, or `latest` URL.

The image lightbox is **GLightbox 3.3.1 (MIT)**. Fancyapps/Fancybox is not a
locked, fetched, or redistributed dependency. The authored
`epub_browser/assets/lightbox-adapter.js` retains a small legacy-shaped
application API while delegating to GLightbox; its compatibility names are not
evidence that Fancyapps code is present.

PDF.js is similarly supplied by the lock. Its main module and worker come from
the same exact `pdfjs-dist` release and are never mixed with a CDN worker.

## Release workflow

Release checkouts explicitly fetch and verify before building. The canonical
local sequence is:

```bash
python3 tools/sync_vendor_assets.py fetch
python3 tools/sync_vendor_assets.py verify
python3 -m unittest tests.test_vendor_assets -v
python3 -m build
```

For a fully network-disabled build, first hydrate the vendor tree and provision
the Python environment while network access is available:

```bash
python3 tools/sync_vendor_assets.py fetch
python3 -m pip install build setuptools wheel
```

After disconnecting, verify the tree and disable both index access and PEP 517
build isolation so the pre-provisioned tools are used:

```bash
python3 tools/sync_vendor_assets.py verify
PIP_NO_INDEX=1 python3 -m build --no-isolation
```

The PyPI workflow builds the direct wheel and sdist separately, verifies their
exact vendor inventories and digests, rebuilds a wheel from the sdist inside a
Docker container with `--network none`, and compares it with the direct wheel.
Provision the builder image while online; the image must already contain the
Python build frontend and backend before the isolated gate starts:

```bash
docker build --tag epub-browser-release-builder:local - <<'DOCKERFILE'
FROM python:3.14-slim
RUN python -m pip install --no-cache-dir build setuptools wheel
DOCKERFILE
```

The artifact gate then fails closed if Docker or the pre-provisioned image is
unavailable. Docker isolation is supported on POSIX hosts and runs with the
calling user's numeric UID:GID so its writable bind mounts do not acquire
root-owned files; a host without POSIX identity APIs fails closed. The optional
rebuilt-wheel evidence directory must be absent or empty. The gate builds in a
fresh private directory and publishes the one verified wheel to that evidence
directory only after verification succeeds:

```bash
python3 tools/verify_release_artifacts.py \
  --wheel dist/direct/*.whl \
  --sdist dist/release/*.tar.gz \
  --rebuilt-wheel-dir dist/rebuilt \
  --network-isolation docker \
  --builder-image epub-browser-release-builder:local
```

GitHub Pages uses a verified wheel. Docker fetches and verifies only in its
builder stage, installs that wheel into the final stage, and does not copy the
sync tool, archive cache, or Git metadata into the runtime image. Wheels,
sdists, Docker images, and SSG output are therefore self-contained; installed
readers never download vendor files or require a runtime CDN.

Package provenance, copyright notices, licenses, and installed-file ownership
are recorded in `THIRD_PARTY_NOTICES.md` at the repository root. The lock is a
fact record, not a substitute for license review.
