# Locked third-party browser assets

`assets.lock.json` is the reviewable manifest for browser assets copied into
`epub_browser/assets/vendor/` during the build. Each package records its exact
immutable npm tarball, archive and expansion limits, allowlisted output files,
SHA-256 values, and license files. The hydrated vendor tree is generated and
must not be committed.

Hydrate the tree with:

```sh
python3 tools/sync_vendor_assets.py fetch
```

Run the offline integrity check with:

```sh
python3 tools/sync_vendor_assets.py verify
```

The verifier never downloads assets. Use `clean` to remove only files owned by
the current lock. Package and license details are summarized in
`THIRD_PARTY_NOTICES.md` at the repository root.
