# Configurable Book ID Storage

## Status

Approved design awaiting final document review. Implementation must not begin until this document is reviewed and an implementation plan is approved.

## Context

EPUB Browser v2.0.4 introduced a stable UUID-derived `book_id` by adding `epub-browser:book-id` metadata to each source EPUB package document. The ID is also the `book_hash` used in generated URLs and retained by annotations, reading progress, and Server state.

Embedding the ID makes it travel with one file, but even a one-element OPF change requires rebuilding the ZIP container. Rebuilding can change compressed bytes and other ZIP-level details even when every logical resource is preserved. It can also invalidate signatures, interact badly with uncommon ZIP features, and produce `--watch` events for EPUB Browser's own write.

The default identity carrier will therefore become a visible adjacent sidecar. Users who prefer a self-contained EPUB may explicitly select embedded storage for the whole command invocation.

## Goals

1. Keep a stable UUID-derived book ID across generation, Server restarts, content updates, and ordinary file moves.
2. Make a visible adjacent sidecar the default storage method without modifying source EPUB bytes.
3. Retain embedded OPF storage as an explicit invocation-wide option.
4. Apply the same option and identity rules to SSG, Server, watch mode, and legacy command syntax.
5. Migrate v2.0.4 embedded IDs to sidecars without generating new IDs or rewriting EPUBs.
6. Use source fingerprints for cache reuse and unambiguous move detection, while keeping identity and content version as separate concepts.
7. Fail clearly on identity conflicts or unsafe writes instead of guessing or silently falling back to a different storage method.
8. Restore repository example EPUBs to their pre-v2.0.4 bytes and carry their published IDs in visible sidecars.

## Non-goals

- Removing an old carrier when the selected storage method changes.
- Automatically resolving two different IDs for the same source.
- Making sidecar files editable configuration files.
- Storing sidecars in Server data, a hidden directory, or a central registry.
- Guaranteeing identity across a copy that omits every identity carrier and cannot be correlated with one unique inactive source.
- Making embedded ZIP rewriting byte-for-byte lossless for all EPUB containers.

## Terminology

- **Book ID**: the durable application identity. New IDs are UUID v4 values encoded as unpadded URL-safe base64, currently 22 characters. Existing valid IDs are retained during migration.
- **`book_hash`**: the existing URL and client-state field name. Its value is exactly the book ID; it is not a digest of the EPUB.
- **Source fingerprint**: the lowercase hexadecimal SHA-256 digest of the current complete EPUB file bytes.
- **Carrier**: a durable place that stores a book ID: the adjacent sidecar or embedded OPF metadata.
- **Exact sidecar**: the sidecar whose path is derived directly from an EPUB path.
- **Orphan sidecar**: an in-scope sidecar whose corresponding EPUB path does not currently exist.

## Command contract

Both explicit modes accept the same option:

```bash
epub-browser ssg <source...> \
  --output-dir <dist> \
  [--book-id-storage sidecar|embedded]

epub-browser server <source...> \
  (--server-dir <dir> | --ephemeral) \
  [--watch] \
  [--book-id-storage sidecar|embedded]
```

The legacy parser accepts the same `--book-id-storage` option. The legacy migration hint includes it only when the non-default `embedded` value was selected.

The option applies to every EPUB discovered by that command. Per-book storage selection is not supported. Its default is `sidecar`.

`SSGConfig` and `ServerConfig` both carry a validated storage value. The process fixes the value at startup; watch mode cannot change it until the process is restarted.

## Visible sidecar contract

The sidecar is adjacent to its EPUB and uses the complete EPUB filename plus `.epub-browser.json`:

```text
1984.epub
1984.epub.epub-browser.json
```

It is deliberately not hidden. Version 1 has this logical schema:

```json
{
  "schema": 1,
  "book_id": "3q2-7w9AR2O3d4wXyZpQ9A",
  "source_fingerprint": {
    "algorithm": "sha256",
    "value": "64-lowercase-hex-characters"
  }
}
```

The writer emits UTF-8 JSON with stable key ordering, readable indentation, and one trailing newline. It adds no timestamps, absolute paths, titles, or other machine-dependent values. Unknown keys in a supported schema are preserved when the fingerprint is refreshed, but EPUB Browser owns the defined fields.

The reader requires:

- a JSON object with integer `schema` equal to `1`;
- a syntactically valid existing book ID;
- `source_fingerprint.algorithm` equal to `sha256`;
- a 64-character lowercase hexadecimal fingerprint.

A malformed file, unsupported schema, invalid ID, or invalid fingerprint is an actionable error for that source. EPUB Browser does not repair malformed identity data by guessing.

### Atomic sidecar writes

Sidecars are written through a temporary file in the same directory, flushed and synced, then activated with `os.replace`. The parent directory is synced where the platform supports it. A failed write leaves the previous sidecar intact and removes only EPUB Browser's temporary file.

The EPUB is opened read-only in sidecar mode. Source EPUB symlinks and hard links are not rewritten. The sidecar path is derived from the discovered source path before database canonicalization, so it remains visibly adjacent to the path the user supplied or discovered.

An existing sidecar must be a regular, non-symlink file. A sidecar with multiple hard links is refused rather than silently breaking or updating another path's identity. The implementation does not follow a sidecar symlink.

If a required sidecar is absent and its directory is not writable, or an existing sidecar cannot be safely refreshed, the source fails with a clear error. Server does not replace the carrier with a database-only identity.

## Embedded carrier contract

Embedded mode retains the v2.0.4 OPF metadata name:

```xml
<meta name="epub-browser:book-id" content="..."/>
```

Reading embedded metadata is always read-only. Writing it is allowed only when `--book-id-storage embedded` is selected and the chosen ID is not already embedded.

The existing embedded writer keeps its safety checks for signed, encrypted, unsupported, read-only, symbolic-link, hard-linked, concurrently changed, or otherwise unsafe EPUBs. It preserves entry order and logical non-OPF resources, but it cannot promise identical compressed bytes. A refused embedded write fails the source and does not fall back to sidecar or database-only storage.

## Identity resolution

Identity resolution is a shared service used by SSG and Server. It establishes the current source fingerprint and collects every applicable identity candidate:

1. the exact sidecar ID, if present;
2. the embedded OPF ID, if present;
3. the Server database ID already registered for the same canonical source path, in Server mode;
4. an unambiguous move candidate from an orphan sidecar or inactive Server record, when no exact current-path carrier establishes the move.

Every collected non-empty ID must agree. A mismatch is a conflict and fails that source without changing the EPUB, sidecar, or Server registry. Duplicate active sources with the same ID also fail instead of receiving replacement IDs.

If no candidate supplies an ID, EPUB Browser generates one new UUID-derived ID. It then persists that same ID only to the carrier selected for the invocation. Existing non-selected carriers are read for consistency but are neither deleted nor refreshed.

### Resolution matrix

The table omits Server database candidates; a database ID participates in the same agreement rule.

| Existing carrier state | `sidecar` mode | `embedded` mode |
| --- | --- | --- |
| Neither carrier | Generate one ID and create sidecar | Generate one ID and write OPF |
| Embedded only | Create sidecar with the embedded ID; do not write EPUB | Reuse embedded ID |
| Sidecar only | Reuse sidecar ID and refresh its fingerprint if needed | Write the sidecar ID into OPF; do not alter sidecar |
| Both contain the same ID | Reuse ID; refresh sidecar fingerprint if needed | Reuse ID; do not alter sidecar |
| Carriers disagree | Fail without mutation | Fail without mutation |

If both carriers are absent but Server has an existing ID at the same path, the selected carrier is recreated with the database ID. This covers accidental sidecar deletion without breaking annotations or URLs.

Switching modes never generates a new ID when a valid existing carrier or Server record supplies one. It also never removes the old carrier. A dormant sidecar's stored fingerprint may become stale while embedded mode is active; its ID remains a consistency candidate, and sidecar mode refreshes the fingerprint if selected later.

## Fingerprints, reuse, copies, and moves

Identity and cache reuse are separate decisions.

### Cache reuse

Server reuses a converted cache only when:

1. the source's established current fingerprint equals the database `source_fingerprint` for the resolved book ID; and
2. the converted cache passes its existing validity checks.

SSG, sidecar creation or refresh, and move correlation compute SHA-256 from the actual EPUB bytes. On Server's unchanged fast path, a previously verified database digest may be treated as current only while canonical path, resolved ID, source size, and nanosecond modification time still match the stored baseline. Any mismatch recomputes SHA-256. The digest remains the content-version comparison; size and time only avoid recalculating it. A sidecar's recorded fingerprint is never sufficient evidence for cache reuse and never overrides the EPUB or Server database state.

When content changes at an exact EPUB/sidecar path, the book ID remains stable, the current digest replaces the sidecar fingerprint in sidecar mode, and Server converts a new cache version. Existing annotations and progress remain attached to the stable ID.

### Move detection

For directory sources, orphan candidates are discovered recursively within the same configured source roots, excluding hidden path components. For an explicitly supplied EPUB, candidates are limited to its parent directory. A sidecar is orphaned only when the EPUB path obtained by removing `.epub-browser.json` does not exist.

If a new EPUB has no exact sidecar, an orphan sidecar is eligible only when its stored SHA-256 equals the new EPUB's actual SHA-256. Exactly one eligible orphan may be adopted. Its ID must also agree with embedded metadata and Server state. After consistency checks, sidecar mode atomically renames it to the new exact sidecar path and refreshes it if necessary.

If zero orphan sidecars match, other valid candidates may still resolve the ID; otherwise a new ID is created. If multiple orphan sidecars match and no exact current-path carrier already establishes identity, resolution fails as ambiguous. EPUB Browser never generates a replacement ID to hide that ambiguity and never chooses by filename similarity, title, author, EPUB identifier alone, or modification time.

Server's inactive-record move correlation continues to require one unique match on EPUB identifier plus actual source fingerprint. A carrier ID, when present, is stronger and must agree with that record.

### Observable copy and move behavior

- Move the EPUB and sidecar together: the exact sidecar retains the ID.
- Rename or move only the EPUB within the discovery scope: one matching orphan sidecar retains the ID.
- Copy only a sidecar-managed EPUB with no embedded ID while the original remains active: the copy receives a new ID and a new selected carrier.
- Copy an EPUB that already carries an embedded ID while the original remains active: the copied carrier produces a duplicate-ID conflict.
- Copy the EPUB and sidecar while the original remains active: the duplicate active ID is reported as a conflict.
- Remove the original and leave one matching orphan sidecar or inactive Server record: the new path is treated as a move, because move and copy cannot otherwise be distinguished.
- Edit EPUB content in place: retain the exact carrier's ID and change only the content fingerprint/version.

## SSG flow

SSG resolves identity for every discovered EPUB before conversion. Sidecar creation or embedded writing may therefore persist even if a later book causes the complete static build to fail; preserving identity across the retry is intentional.

Duplicate resolved IDs fail the whole SSG build with all conflicting source paths listed. The destination snapshot remains transactional and unchanged on failure.

SSG has no database. Its portable identity comes from the selected carrier or migration from the non-selected carrier.

## Server flow

Server resolves the carrier, current source fingerprint, and database record before deciding whether to reuse or convert. Database registration and carrier persistence use one resolved ID; neither may silently override the other.

For an existing source path, a missing selected carrier is recreated from the database ID before reuse or conversion. For a moved source, carrier and unique inactive-record correlation must agree before the database path is updated.

At startup, full reconciliation first knows the complete discovered source set. A database row whose former path is no longer present can participate in move correlation during that same reconciliation even before its `active` flag is committed as false. This preserves identity for offline renames instead of temporarily treating the old missing path as a duplicate active source.

A new sidecar is persisted before conversion begins so a failed conversion retry does not create a new ID. Conversion failure keeps any previously active cache and Server record under the same ID, following existing degraded-mode behavior.

No database schema change is required. The existing `books.book_id`, `source_path`, and `source_fingerprint` columns retain their meanings.

## Watch behavior

The watch handler continues reacting only to `.epub` events. `.epub-browser.json` and temporary sidecar events are ignored, so sidecar creation and fingerprint refresh cannot trigger reconciliation loops.

Manual sidecar-only edits while Server is running are not hot-reloaded. They are evaluated on the next relevant EPUB reconciliation or process restart.

In sidecar mode, EPUB Browser never writes the EPUB, so it creates no self-generated EPUB event.

In embedded mode, the initial OPF write can produce one filesystem event. The resolver recomputes the post-write stat and fingerprint before committing its baseline. When the queued event is reconciled, the ID is already embedded and the actual fingerprint/database/cache checks prevent another write or conversion loop. A harmless extra reconciliation is permitted; repeated source updates are not.

## Migration from v2.0.4

Default sidecar mode reads any v2.0.4 embedded ID once and creates the exact sidecar with the same ID and current source fingerprint. It does not remove the OPF metadata and does not rewrite the EPUB. Existing Server database IDs must agree and remain unchanged.

If embedded metadata and the Server registry disagree, startup or SSG inspection fails with both sources of identity named. There is no automatic winner.

Repositories and libraries that never ran v2.0.4 simply receive a new sidecar ID on first use. Read-only libraries must have valid sidecars prepared in advance; the former Server database-only fallback is intentionally removed.

## Repository examples and CI

The three tracked example EPUBs are restored byte-for-byte from the commit immediately before embedded identity was introduced. The two successfully embedded v2.0.4 IDs are retained. The non-standard `1984` EPUB was never rewritten successfully, so its existing v2.0.3 TOC-derived public ID is retained instead. Those three existing public IDs are written to these tracked visible files:

```text
examples/Mao Ze Dong Xuan Ji - Mao Ze Dong.epub.epub-browser.json
examples/TheEconomist.2026.02.14 - Kovid Goyal.epub.epub-browser.json
examples/Yi Jiu Ba Si - Qiao Zhi _Ao Wei Er.epub.epub-browser.json
```

This keeps existing generated URLs stable while restoring the original EPUB ZIP layout, including the legacy `mimetype` placement in the affected file.

The GitHub Pages workflow continues using the legacy command as a compatibility check. Because the default is sidecar and all example sidecars exist, the workflow reads the EPUBs without mutating them. Verification records EPUB hashes before and after the command and requires them to match.

## Errors and diagnostics

Errors name the source path and the conflicting or unsafe identity locations without dumping EPUB content. Important failure classes are:

- malformed, unsupported, symlinked, or multiply linked sidecar;
- sidecar directory not writable when creation or refresh is required;
- embedded, sidecar, and/or database ID disagreement;
- duplicate active book ID across multiple sources;
- ambiguous orphan sidecar or inactive-record matches when no stronger candidate exists;
- unsafe or concurrently changed embedded write;
- source changes while fingerprinting or identity persistence is in progress.

Before replacing a sidecar or EPUB, the implementation rechecks the source stat captured before hashing. If the source changed, it discards temporary output and retries through the normal reconciliation path rather than binding an ID to uncertain bytes.

## Documentation and release

This is released as v2.0.5. The existing v2.0.4 tag and release history remain unchanged.

The README, CLI help, Docker examples, migration guidance, version metadata, and `docs/releases/v2.0.5.md` explain:

- sidecar is the default and does not alter EPUB bytes;
- the exact visible filename and JSON purpose;
- `--book-id-storage embedded` explicitly opts into source rewriting and its limitations;
- the option applies to the whole command;
- read-only libraries require pre-existing valid carriers;
- `book_id` and URL `book_hash` are the same value;
- changing storage modes preserves IDs and leaves old carriers in place.

## Verification scope

Implementation verification is focused rather than a full product regression run:

- sidecar schema parsing, deterministic atomic writing, and malformed-file refusal;
- identity resolution matrix, migration, conflict, duplicate, copy, content-update, and unique/ambiguous move cases;
- actual fingerprint controls Server cache reuse;
- both explicit commands and legacy parsing propagate the invocation-wide option;
- watch ignores sidecar events and embedded mode does not loop;
- source EPUB hashes remain unchanged in default sidecar mode;
- explicit embedded mode retains its existing safe-write/refusal behavior;
- repository example EPUB hashes match their pre-v2.0.4 versions;
- the exact GitHub Pages legacy command completes against the restored examples without changing them;
- release metadata and documentation consistently report v2.0.5.

## Implementation boundary

The approved implementation may refactor the current `epub_identity` module into shared resolver, sidecar, and embedded responsibilities; update CLI/config, SSG, Server reconciliation, watcher tests, examples, documentation, and release metadata; and remove the current Server database-only write-refusal fallback.

It must not redesign generated URL shapes, database tables, annotation/progress storage, reader UI, or unrelated publication behavior.
