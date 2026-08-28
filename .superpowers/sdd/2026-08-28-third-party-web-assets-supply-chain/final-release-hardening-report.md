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
  network boundary. On POSIX hosts it also supplies `--user <uid>:<gid>` so
  writable bind mounts do not receive root-owned files; non-POSIX hosts fail
  closed.
- Docker image references are validated against a strict ASCII image-reference
  grammar before any subprocess runs. Option-like values such as
  `--builder-image=--help` are rejected, and supported Docker commands also use
  `--` before the validated image reference.
- Rebuilt wheels are always created in a fresh tool-owned temporary directory.
  A caller-requested evidence directory must be absent or empty, and receives
  the sole newly created wheel only after its inventory and digests verify.
  Existing evidence is preserved and rejected rather than reused or replaced.
- The PyPI job provisions `build`, `setuptools`, and `wheel` in a builder image
  while networking is available. It then runs a hostile `setup.py` fixture
  which attempts networking through a direct socket, `urllib`, and a Python
  subprocess before using the same image for the real release gate.
- Lock parsing, fetch, redirect handling, and response-final URL handling now
  route through the common strict HTTPS validator. Load, offline verify, clean,
  and fetch reject HTTP, malformed authorities, backslashes, credential-bearing
  URLs, ASCII/DEL/C1 controls, Unicode format characters, and Unicode whitespace
  before filesystem changes or archive installation.
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
5. The real Docker-runner command fixture failed until the host UID:GID and
   validated-image `--` separator were present.
6. The literal `--builder-image=--help` CLI reproduction reached artifact
   inspection before strict image-reference validation was added.
7. A no-op isolation runner incorrectly passed by reusing a valid wheel already
   present in the requested output directory. A second regression proved the
   runner received the caller directory rather than a fresh private directory;
   both passed after separating build output from post-verification evidence.
8. Common lock-consumer, redirect-handler, and response-final URL fixtures
   accepted malformed HTTPS-looking strings before all three boundaries reused
   the strengthened validator.

## Verification evidence

- `python3 -m unittest tests.test_vendor_assets -v`: 56 tests, OK, one expected
  local Docker-proof skip.
- `python3 -m unittest tests.test_vendor_assets tests.test_static_asset_delivery -v`:
  58 tests, OK, one expected local Docker-proof skip.
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
executes the real runner against a fixture Docker CLI to verify UID:GID and
argument placement, separately proves that a present CLI with an unavailable
daemon fails before `docker run`, and uses an injected build runner only for
portable local artifact tests.

The pre-existing untracked example PDF and JSON sidecar were not modified or
staged.
