# OIDC end-to-end test

This fixture proves EPUB Browser's generic OIDC implementation against a real,
pinned Authelia Provider and a real Chromium browser. It uses isolated Compose
volumes, a short-lived test CA, S256 PKCE, and test-only credentials and signing
material. Nothing in this directory is suitable for production.

Run from any directory:

```sh
tests/e2e/oidc/run.sh
```

The test builds the production EPUB Browser image, validates Authelia's real
discovery/token/JWKS behavior, exercises account binding and automatic member
creation, saves screenshots under `artifacts/`, and always removes its containers
and named volumes. On failure it also writes `artifacts/compose.log`.

The fixed loopback ports `18443` and `18444` are used because the exact HTTPS
application and issuer URLs must be identical from Chromium and from the EPUB
Browser container. The runner checks that both ports are free before starting.
Set `EPUB_BROWSER_CHROMIUM` to override
the automatically detected Chromium executable.

Test accounts:

- EPUB Browser administrator: `owner` / `owner-secret`
- Existing local and Authelia member: `reader` / `reader-secret`
- Authelia-only member: `newcomer` / `new-reader-secret`

The committed RSA key, password hashes, client secret hash, and application
secrets are deliberately public test fixtures. Never reuse them.
