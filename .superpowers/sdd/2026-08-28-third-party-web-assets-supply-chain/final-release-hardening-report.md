# Final release hardening report

Date: 2026-08-28

## Scope

This change closes the final vendor-review Important and Minor release issues
without changing runtime EPUB/Server behavior or the Server content-cache
schema.

## Changes

- Sdist-to-wheel verification now requires an explicit isolation runner. The
  public CLI fails closed when no isolation mode is supplied, when Docker is
  unavailable, or when the requested pre-provisioned image is absent.
- The supported release runner invokes `docker run --network none` and mounts
  only the already-verified extracted sdist and the wheel output directory.
  `PIP_NO_INDEX` remains enabled as defense in depth, but is no longer the
  network boundary.
- The PyPI job provisions `build`, `setuptools`, and `wheel` in a builder image
  while networking is available. It then runs a hostile `setup.py` fixture
  which attempts networking through a direct socket, `urllib`, and a Python
  subprocess before using the same image for the real release gate.
- Lock parsing now routes source URLs through the common strict HTTPS
  validator. Consequently load, offline verify, and clean all reject HTTP,
  missing-host, invalid-port, credential-bearing, and control/whitespace URLs
  before filesystem changes.
- Wheel and sdist member validation now rejects collisions after NFC Unicode
  normalization plus `casefold()`, covering portable case-insensitive
  filesystems in addition to exact canonical-name duplicates.
- `third_party/README.md` documents the new pre-provisioned Docker builder and
  mandatory release-gate flags.

## Strict TDD evidence

Each production behavior was preceded by a focused failing test:

1. The common source-URL test failed for load, verify, and clean before
   `_parse_source` called the strict HTTPS validator; it passed after the
   shared validation change.
2. Real derived wheel and sdist fixtures containing casefold and canonically
   equivalent Unicode names passed incorrectly before portable collision
   checks; all four cases were rejected after the change.
3. The public artifact CLI rebuilt an sdist successfully on the networked host
   before isolation became mandatory; it now exits nonzero with `network
   isolation is required`.
4. The PyPI workflow test failed until the pre-provisioned image, hostile
   backend proof, and Docker isolation arguments were wired into the release
   job.

## Verification evidence

- `python3 -m unittest tests.test_vendor_assets -v`: 50 tests, OK, one expected
  local Docker-proof skip.
- `python3 -m unittest tests.test_vendor_assets tests.test_static_asset_delivery -v`:
  52 tests, OK, one expected local Docker-proof skip.
- `python3 -m py_compile tools/sync_vendor_assets.py
  tools/verify_release_artifacts.py tests/test_vendor_assets.py`: exit 0.
- `python3 tools/sync_vendor_assets.py verify`: exit 0.
- `python3 -m build --wheel --sdist --no-isolation`: built both fresh artifacts.
- `python3 tools/verify_release_artifacts.py --wheel <fresh-wheel>`: direct
  wheel verified.
- Calling the artifact verifier with the fresh wheel and sdist but without an
  isolation mode: exited nonzero with `network isolation is required for an
  sdist rebuild`, proving the public interface does not fall back locally.
- `git ls-files epub_browser/assets/vendor`: no tracked generated vendor files.
- `git diff --check`: exit 0.

## Platform residual

The local host is macOS and its Docker CLI cannot reach a Docker daemon, so the
real container network-namespace proof cannot run locally. This is an expected
fail-closed condition and the suite reports one explicit skip. The PyPI job on
GitHub-hosted Ubuntu provisions the builder image and makes the hostile
socket/`urllib`/subprocess isolation test mandatory before artifact upload; the
release gate itself then uses that same `--network none` runner. Unit coverage
also verifies that an absent runtime/image fails closed and uses an injected
runner only for portable local artifact tests.

The pre-existing untracked example PDF and JSON sidecar were not modified or
staged.
