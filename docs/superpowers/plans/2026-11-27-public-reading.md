# Public Reading Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Deliver #85 anonymous public reading and #86 default visibility without changing private deployments or SSG behavior.

**Architecture:** Extend existing roles and book grants with public visibility. Centralize access decisions for direct checks and filtered queries; apply import defaults only within new-book insertion.

**Tech Stack:** Python, SQLite, Starlette, JavaScript, existing shared HTML renderer and pytest/Node tests.

**Spec:** docs/superpowers/specs/2026-11-27-public-reading-design.md

## Global Constraints

- `allow_anonymous_reading=false`; `default_book_visibility=authenticated`.
- Visibility values: `public`, `authenticated`, `restricted`.
- No generic RBAC, guest accounts, anonymous personal APIs or raw-file API.
- Preserve SSG isolation, EPUB/PDF content-cache revisions and existing grants.
- No commit/push/PR before explicit approval under issue-driven-implement.

## Review Focus

- Existing SQLite foreign keys and grants survive visibility-constraint migration (Task 1).
- Search, metadata and guessed resource URLs cannot reveal private books (Task 2).
- Conditional/Range requests cannot bypass a changed visibility setting (Task 2).
- Anonymous UI cannot silently initialize personal or AI API calls (Task 3).
- Restored or updated stable identities keep permissions after default changes (Task 4).

### Task 1: Persist policy and extend authorization

**Files:** epub_browser/state.py; tests/test_state.py.

**Interfaces:** Extend `get_general_settings() -> dict` and keyword settings in `set_general_settings(...) -> dict`; extend direct `can_read_book` and list authorization to handle absent authenticated identity explicitly. Preserve authenticated caller compatibility.

- [x] Add a behavioral test for defaults through get_general_settings; run pytest tests/test_state.py -q and observe the missing-setting failure.
- [x] Implement settings persistence and migration with strict boolean/visibility validation; rerun the test to pass.
- [x] Add one failing authorization case at a time for anonymous/public/global switch, member/public, restricted grants, administrator and inactive books. Implement matching direct and filtered-query behavior, then rerun tests.
- [x] Add populated legacy migration coverage asserting unchanged IDs, grants and related records through public methods; implement constraint migration and run tests/test_state.py.

### Task 2: Gate anonymous HTTP delivery

**Files:** epub_browser/server.py, epub_browser/pdf_delivery.py, epub_browser/book_search.py; tests/test_server.py, tests/test_pdf_server.py, tests/test_book_search.py.

**Interfaces:** HTTP routes consume Task 1 settings and authorization. Anonymous policy is available only to selected GET/HEAD read handlers; personal, admin, AI and PAT routes preserve authentication requirements.

- [x] Add a failing HTTP test proving default-off behavior and public-only catalog delivery when enabled; implement route-specific middleware and handler support, then pass it.
- [x] Incrementally test search, metadata, cover, TOC, chapter and embedded resources against public and restricted books; update their filtering before returning data.
- [x] Add failing PDF Range/HEAD and conditional-request cases after public-to-restricted changes and global disable; enforce authorization before cache/Range decisions and verify private cache headers.
- [x] Test anonymous denial for personal APIs and AI plus unchanged PAT authentication; run pytest tests/test_server.py tests/test_pdf_server.py tests/test_book_search.py -q.

### Task 3: Admin settings and anonymous reader capabilities

**Files:** epub_browser/server.py, epub_browser/reader_pages.py, epub_browser/server_pages.py, epub_browser/assets/auth.js, relevant reader capability initialization in existing assets, epub_browser/assets/i18n/*.json; tests/test_auth_ui.js, tests/test_server.py, tests/test_i18n_coverage.py and existing reader tests.

**Interfaces:** Admin general settings exposes Task 1 fields. Shared renderers receive an explicit runtime authentication/capability context; SSG retains existing behavior.

- [x] Test admin-only settings updates and invalid values; add settings controls and API validation using existing UI conventions.
- [x] Add failing anonymous markup/JS behavior tests for login entry and disabled personal/AI initialization; implement capability checks in shared components, then pass tests.
- [x] Cover EPUB/PDF chapter, paginated, continuous and Kindle behavior without assuming a fixed initial chapter; verify SSG rendering separately.
- [x] Add localized labels/explanations and runtime locale updates; run existing Node tests and pytest tests/test_i18n_coverage.py -q.

### Task 4: First-import default visibility

**Files:** epub_browser/state.py, epub_browser/server_library.py only if necessary; tests/test_state.py, tests/test_server_library.py, tests/test_pdf_server.py, tests/test_server.py.

**Interfaces:** `resolve_book(...) -> BookRecord` keeps its caller interface; only its insertion branch consumes default_book_visibility from the same transaction.

- [x] Add a failing new-import test asserting configured restricted/public visibility; implement default selection only for a genuinely new record, then pass it.
- [x] Add incremental tests for watched imports and administrator uploads for both formats using their public entry points; verify identical defaults.
- [x] Change the default, update/rescan/rebuild and restore a soft-deleted stable ID; assert original visibility and grants remain, while a new identity gets the new default.
- [x] Run pytest tests/test_state.py tests/test_server_library.py tests/test_server.py tests/test_pdf_server.py -q.

### Task 5: Verification and reviewable environment

- [x] Run scope-relevant SSG/template, permission, search, PDF and JS regression suites plus git diff --check. Record actual results and any pre-existing failures.
- [x] Start SSG from examples and serve it locally; start Server with examples using isolated server data and a different available port.
- [x] Provide URLs, login/setup information, changes and verification results for user review. Keep environments running until review ends.
- [ ] After user review and explicit commit/push/PR approval, stop test servers, commit intended files and create a PR linking Closes #85 and Closes #86 using the pr skill.

Execution note: use the repository’s unittest runner instead of pytest; the approved test seams remain unchanged. Changes remain uncommitted until explicit PR-stage approval. Final validation evidence is recorded in the execution ledger.

Final verification (2026-11-27): 488 Python tests passed across mode integration, SSG, PDF Server, i18n, concurrency, StateStore, Server, library imports, book search and bookmark browser behavior. All 418 JavaScript tests passed. Vendor assets verified offline; git diff --check passed. Initial full discovery encountered runtime test failures, four reproduced on unchanged main due to startup mocks missing search_indexes; those are outside this implementation. Final scoped suites include regressions for all five independent review findings.
