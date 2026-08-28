# Locked third-party browser assets

`assets.lock.json` is the reviewable manifest for browser assets copied into
`epub_browser/assets/vendor/` during the build. The initial lock intentionally
contains no production packages; adding one requires its exact upstream
archive, size limits, allowlisted output files, SHA-256 values, and license
files.

Run the offline integrity check with:

```sh
python3 tools/sync_vendor_assets.py verify
```

The verifier never downloads assets. A later build step hydrates the generated
vendor tree from the same lock.
