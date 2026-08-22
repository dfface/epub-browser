# Administrator Book Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace eager per-book administration cards with a lightweight, pinyin-searchable, paginated table and one lazy atomic settings editor.

**Architecture:** `StateStore` returns all active book summaries with a bounded set of batch queries and applies a complete settings payload in one transaction. Starlette preserves existing granular endpoints while adding an index, detail GET, and atomic settings PUT. The browser filters/paginates the lightweight index locally with the bundled `pinyin-pro` library and fetches full controls only for one expanded row.

**Tech Stack:** Python 3.9+, SQLite schema v11, Starlette, browser-compatible ES5 JavaScript, bundled `pinyin-pro`, CSS, `unittest`, Node's built-in test runner.

**Spec:** `docs/superpowers/specs/2026-08-23-server-schema-admin-operations-design.md`

## Global Constraints

- Complete the schema v11 and administrator AI jobs plans first.
- Preserve existing `/api/admin/books`, visibility, grants, and `/ai` endpoint behavior.
- Add no Python pinyin dependency and no SQLite JSON1/FTS dependency.
- Initial book management loads only privacy-safe active-book summaries; never return source paths or raw `metadata_json`.
- Search title, authors, EPUB tags, and server tags using literal text plus tone-free full pinyin.
- Render 20 books per page by default and load full editable detail only for the expanded book.
- Visibility, member grants, server tags, and AI profile save atomically or not at all.
- Clearing AI results remains a separately confirmed destructive action.
- Reuse existing administration CSS variables and controls; do not add a UI framework or nested modal.
- Keep English and Simplified Chinese key sets complete.
- Server mode only; SSG contains no administration table or API calls.
- Do not change `.server-content-revision`.

---

### Task 1: Add batched book summaries and atomic settings persistence

**Files:**
- Modify: `tests/test_state.py`
- Modify: `epub_browser/state.py:1930-2350,3065-3305`

**Interfaces:**
- Consumes: existing books, book access, AI tags/profiles, and AI results tables.
- Produces: `StateStore.list_admin_book_summaries() -> tuple[dict, ...]`, `StateStore.get_admin_book_detail(book_id: str) -> dict`, and `StateStore.update_admin_book_settings(book_id: str, *, visibility: str, user_ids: Sequence[str], tag_ids: Sequence[str], profile: str) -> tuple[dict, dict]` returning `(detail, summary)`.

- [ ] **Step 1: Write failing summary-content and bounded-query tests**

Create three active books and one inactive book with authors/EPUB tags, mixed visibility, grants, profiles, server tags, and retained AI results. Assert summaries contain:

```python
{
    "id": book.book_id,
    "title": "算法导论",
    "authors": ["作者甲"],
    "epub_tags": ["算法"],
    "visibility": "restricted",
    "grant_count": 2,
    "ai_profile": "technical",
    "ai_tags": [{"id": tag["id"], "name": "Computer Science"}],
    "ai_result_count": 3,
    "updated_at": book.updated_at,
}
```

Assert the inactive book and `source_path`/`metadata_json` are absent. Wrap `_connect` so each returned connection installs `set_trace_callback(statements.append)`, call `list_admin_book_summaries()`, and assert the number of executed `SELECT` statements is unchanged after adding 50 more books.

- [ ] **Step 2: Write failing atomic update tests**

Call `update_admin_book_settings` with a restricted visibility, two enabled members, two valid tag IDs, and `fiction`; assert all four groups changed. Then call it with one unknown tag and assert visibility, grants, tags, and profile all remain at the prior values.

Add validation cases for disabled/admin grant users, duplicate IDs, unknown book, unsupported visibility, and unsupported profile. Duplicate user/tag IDs normalize by first occurrence without duplicate rows.

- [ ] **Step 3: Run focused StateStore tests and verify failure**

Run: `python3 -m unittest tests.test_state.StateStoreTests.test_admin_book_summaries_are_batched_and_private tests.test_state.StateStoreTests.test_admin_book_settings_update_is_atomic tests.test_state.StateStoreTests.test_invalid_admin_book_settings_roll_back -v`

Expected: FAIL because the three methods do not exist.

- [ ] **Step 4: Implement bounded batch summary loading**

Within one `_connection()` block, execute one active-books query and grouped queries for grants, profiles, tag assignments joined to `ai_tags`, and result counts. Build dictionaries keyed by `book_id`, parse metadata with safe fallbacks, and return rows ordered by `book_id` for deterministic transport.

Do not issue SQL from inside the loop over books. A representative aggregate is:

```sql
SELECT book_id, COUNT(*) AS grant_count
FROM book_access
GROUP BY book_id;
```

Tag rows use `ORDER BY book_id, ai_tags.normalized_name, ai_tags.id`; result counts use `GROUP BY book_id`.

- [ ] **Step 5: Refactor connection-scoped settings helpers**

Add private helpers that receive an existing connection:

```python
def _replace_book_grants(self, connection, book_id: str, user_ids: Sequence[str]) -> tuple[str, ...]:
    ...

def _replace_book_ai_tags(self, connection, book_id: str, tag_ids: Sequence[str]) -> tuple[dict, ...]:
    ...

def _set_book_ai_profile(self, connection, book_id: str, profile: str) -> str:
    ...
```

Make existing public granular methods delegate to these helpers in their own connection so their contracts remain unchanged.

- [ ] **Step 6: Implement detail and atomic update**

`get_admin_book_detail` returns the same privacy-safe metadata as a summary plus complete grant user IDs, assigned tags, effective tags, and profile.

`update_admin_book_settings` performs all validation and writes inside one `BEGIN IMMEDIATE` connection:

```python
connection.execute("BEGIN IMMEDIATE")
book = self._get_book(connection, book_id)
self._validate_visibility(visibility)
self._replace_book_grants(connection, book_id, user_ids)
self._replace_book_ai_tags(connection, book_id, tag_ids)
self._set_book_ai_profile(connection, book_id, profile)
connection.execute(
    "UPDATE books SET visibility=?, updated_at=CURRENT_TIMESTAMP WHERE book_id=?",
    (visibility, book_id),
)
connection.execute("COMMIT")
```

Rely on context-manager rollback for exceptions. Before commit, re-query the one affected book through shared private mappers and return `(refreshed_detail, refreshed_summary)` after commit; do not call the all-books summary method to patch one row.

- [ ] **Step 7: Run book state and legacy endpoint tests**

Run: `python3 -m unittest tests.test_state tests.test_server.AdminAccountTests.test_admin_saves_book_tags_and_ai_profile_independently -v`

Expected: PASS.

- [ ] **Step 8: Commit batched summaries and atomic settings**

```bash
git add epub_browser/state.py tests/test_state.py
git commit -m "feat: optimize administrator book persistence"
```

---

### Task 2: Add lightweight index, detail GET, and atomic settings API

**Files:**
- Modify: `tests/test_server.py`
- Modify: `epub_browser/server.py:580-615,1450-1555,2568-2605`

**Interfaces:**
- Consumes: Task 1 StateStore methods.
- Produces: `GET /api/admin/books/index`, `GET /api/admin/books/{book_id}`, and `PUT /api/admin/books/{book_id}/settings`.

- [ ] **Step 1: Write failing index privacy and authorization tests**

Assert administrator index returns summary counts/tags and excludes source paths/raw metadata. Assert members receive 403. Preserve an explicit assertion that the old `GET /api/admin/books` still returns its existing `{"books": [...]}` full records.

```python
index = self.admin_client.get("/api/admin/books/index")
self.assertEqual(index.status_code, 200)
self.assertEqual(index.json()["books"][0]["grant_count"], 1)
self.assertNotIn("source_path", index.text)
self.assertNotIn("metadata_json", index.text)
self.assertEqual(self.member_client.get("/api/admin/books/index").status_code, 403)
```

- [ ] **Step 2: Write failing detail and atomic-update route tests**

Assert GET returns one book detail, unknown/inactive books return 404, invalid payloads return stable 400 codes, members cannot GET/PUT, and a valid PUT changes all groups and returns both `book` detail and `summary` for row patching.

Send the complete payload:

```python
payload = {
    "visibility": "restricted",
    "user_ids": [self.member.user_id],
    "tag_ids": [tag_id],
    "profile": "technical",
}
```

Patch the store update method to raise after a validation seam and assert the API does not expose exception text.

- [ ] **Step 3: Run focused Server tests and verify failure**

Run: `python3 -m unittest tests.test_server.AdminAccountTests.test_admin_book_index_is_lightweight_and_private tests.test_server.AdminAccountTests.test_admin_gets_one_book_detail tests.test_server.AdminAccountTests.test_admin_atomically_updates_complete_book_settings -v`

Expected: FAIL with 404/405 for the new routes.

- [ ] **Step 4: Implement response mapping without filesystem fields**

Use store-returned dictionaries directly after copying mutable lists. Do not pass `BookRecord.source_path` or raw metadata through the mapper. Keep existing `admin_book_data` for `/api/admin/books` compatibility. Unpack the atomic update result as `detail, summary` and respond with `{"book": detail, "summary": summary}`.

- [ ] **Step 5: Implement strict atomic settings payload validation**

Require exactly usable values for `visibility`, `user_ids`, `tag_ids`, and `profile`. Reject booleans/non-strings/non-lists before calling the store. Map `KeyError` to 404 only for the book; unknown users/tags and invalid settings map to `400 invalid_book_settings` without identifying restricted entities.

- [ ] **Step 6: Register routes in non-ambiguous order**

Register static paths before the `{book_id}` route:

```python
Route('/api/admin/books/index', admin_book_index, methods=['GET']),
Route('/api/admin/books/{book_id}/settings', admin_book_settings, methods=['PUT']),
Route('/api/admin/books/{book_id}', admin_book, methods=['GET', 'PUT']),
```

Do not remove the old grants and AI routes.

- [ ] **Step 7: Run administrator and book authorization suites**

Run: `python3 -m unittest tests.test_server.AdminAccountTests tests.test_server.BookAuthorizationTests -v`

Expected: PASS.

- [ ] **Step 8: Commit book administration APIs**

```bash
git add epub_browser/server.py tests/test_server.py
git commit -m "feat: add optimized book administration APIs"
```

---

### Task 3: Replace the eager book list with localized table markup

**Files:**
- Modify: `epub_browser/site.py:223-228`
- Modify: `epub_browser/assets/i18n.js`
- Modify: `tests/test_site.py`
- Modify: `tests/test_generated_reader_surfaces.py`
- Modify: `tests/test_i18n_coverage.py`

**Interfaces:**
- Consumes: existing administration modal and i18n infrastructure.
- Produces: DOM IDs `adminBookSearch`, `adminBookVisibilityFilter`, `adminBookTagFilter`, `adminBookPageSize`, `adminBookRefresh`, `adminBookList`, `adminBookPagination`, and `adminBookLive`.

- [ ] **Step 1: Write failing Server-only markup tests**

Assert the book section includes a labeled search input, visibility/tag/page-size selects, refresh button, semantic table, `<tbody id=adminBookList>`, pagination navigation, and polite live region. Assert SSG output contains none of the management IDs.

- [ ] **Step 2: Add required bilingual key coverage**

Extend `test_account_and_administration_copy_exists_in_both_locales` with every `admin.books.*` key for search/filter placeholders, column labels, manage/save/cancel/clear actions, loading/empty states, grant/result counts, page summary, confirmation, and API error codes.

- [ ] **Step 3: Run markup/i18n tests and verify failure**

Run: `python3 -m unittest tests.test_site tests.test_generated_reader_surfaces tests.test_i18n_coverage -v`

Expected: FAIL because the old book section contains only an unordered list.

- [ ] **Step 4: Add compact semantic table structure**

Replace the `<ul>` with toolbar + overflow container + table. Keep `adminBookList` as the tbody ID so the stable surface name remains recognizable while its semantics change. Add headers for book, visibility/access, AI profile/tags, AI results, updated time, and actions.

All fallback text must carry the matching `data-i18n`, `data-i18n-placeholder`, or `data-i18n-aria-label` attribute.

Use labeled controls and a table body that JavaScript can replace safely:

```html
<label for="adminBookSearch" data-i18n="admin.books.searchLabel">Search books</label>
<input id="adminBookSearch" type="search"
       data-i18n-placeholder="admin.books.searchPlaceholder">
<label for="adminBookVisibilityFilter" data-i18n="admin.books.visibilityFilter">Visibility</label>
<select id="adminBookVisibilityFilter"><!-- localized options --></select>
<div class="account-table-scroll">
  <table class="account-admin-table">
    <thead><!-- six localized column headers --></thead>
    <tbody id="adminBookList"></tbody>
  </table>
</div>
<nav id="adminBookPagination" aria-label="Book pages"
     data-i18n-aria-label="admin.books.paginationLabel"></nav>
<p id="adminBookLive" class="visually-hidden" aria-live="polite"></p>
```

- [ ] **Step 5: Add matching English and Simplified Chinese copy**

Use concise operational language. The destructive confirmation must interpolate the book title through JavaScript rather than embedding it in static HTML.

- [ ] **Step 6: Run markup and locale tests**

Run: `python3 -m unittest tests.test_site tests.test_generated_reader_surfaces tests.test_i18n_coverage -v`

Expected: PASS.

- [ ] **Step 7: Commit book-table structure and copy**

```bash
git add epub_browser/site.py epub_browser/assets/i18n.js tests/test_site.py tests/test_generated_reader_surfaces.py tests/test_i18n_coverage.py
git commit -m "feat: add localized book management table"
```

---

### Task 4: Implement client-side pinyin search, filters, and pagination

**Files:**
- Modify: `epub_browser/assets/auth.js:20-980`
- Modify: `tests/test_auth_ui.js`

**Interfaces:**
- Consumes: `GET /api/admin/books/index`, bundled `root.pinyinPro`, Task 3 DOM IDs.
- Produces: `loadAdminBookIndex()`, `filteredAdminBooks()`, `renderAdminBooks()`, and test-visible `loadBookIndex()`.

- [ ] **Step 1: Write failing lightweight-load and pagination tests**

Update the existing separate-admin-panel test to expect `/api/admin/books/index` rather than `/api/admin/books`. Provide 45 summaries and assert only 20 body rows render initially, next page renders the following 20, and changing page size/search/filter resets the current page to 1.

- [ ] **Step 2: Write failing pinyin and filter tests**

Inject:

```javascript
root.pinyinPro = {
  pinyin(value) {
    return value === '算法导论' ? 'suan fa dao lun' : value;
  },
};
```

Assert `suanfadaolun` matches the Chinese title, literal author/tag searches match case-insensitively, restricted visibility filters correctly, server-tag filter matches tag ID, and clearing filters restores total pages.

- [ ] **Step 3: Run Node tests and verify failure**

Run: `node --test tests/test_auth_ui.js`

Expected: FAIL because `loadAdminData` still fetches/render all full book cards.

- [ ] **Step 4: Implement normalized literal+pinyin search text**

Create a safe helper:

```javascript
function compactSearchText(value) {
  return String(value || '').toLocaleLowerCase().replace(/\s+/g, '');
}

function adminBookSearchText(book) {
  var literal = [book.title].concat(book.authors || [], book.epub_tags || [],
    (book.ai_tags || []).map(function(tag) { return tag.name; })).join(' ');
  var pinyin = '';
  if (root.pinyinPro && typeof root.pinyinPro.pinyin === 'function') {
    pinyin = root.pinyinPro.pinyin(literal, { toneType: 'none' });
  }
  return compactSearchText(literal) + ' ' + compactSearchText(pinyin);
}
```

Cache this derived text on an internal view model, not in API data or SQLite.

- [ ] **Step 5: Implement stable filtering, sorting, and page rendering**

Maintain:

```javascript
var adminBooksState = {
  books: [], query: '', visibility: '', tagId: '', page: 1,
  pageSize: 20, expandedBookId: null, requestGeneration: 0
};
```

Filter in memory, sort by localized title with book ID as tie-breaker, calculate total pages, clamp page, and render only `slice(start, start + pageSize)`. Build all cells with `textContent`; display counts and translated badges without `innerHTML`.

- [ ] **Step 6: Refresh only the index request**

Change `loadAdminData()` to load users, book index, AI settings, and tags in parallel. The book refresh button calls only `loadAdminBookIndex()`. Locale changes re-render the retained state instead of refetching all administrator resources.

- [ ] **Step 7: Run JS syntax and search/pagination tests**

Run: `node --check epub_browser/assets/auth.js`

Run: `node --test tests/test_auth_ui.js tests/test_bookshelf_metadata.js`

Expected: PASS and existing bookshelf pinyin coverage remains green.

- [ ] **Step 8: Commit pinyin search and pagination**

```bash
git add epub_browser/assets/auth.js tests/test_auth_ui.js
git commit -m "feat: paginate and search administrator books"
```

---

### Task 5: Add one lazy editor with atomic save and scoped result clearing

**Files:**
- Modify: `epub_browser/assets/auth.js:630-920,980-1130`
- Modify: `epub_browser/assets/account.css:893-1185`
- Modify: `tests/test_auth_ui.js`

**Interfaces:**
- Consumes: Task 2 detail/settings APIs and Task 4 table state.
- Produces: `openAdminBookEditor(bookId)`, `saveAdminBookSettings(bookId, payload)`, `clearAdminBookResults(bookId, title)`, and test-visible `openBookEditor`/`saveBookSettings` methods.

- [ ] **Step 1: Write failing lazy-detail and single-editor tests**

Click Manage for a row and assert one `GET /api/admin/books/{id}` occurs and one detail `<tr>` is inserted immediately after its summary row. Assert the Manage button has `aria-expanded="true"` and `aria-controls` pointing at the editor. Click another row and assert the first editor is removed/closed. Reopen an already loaded row and assert the cached detail is reused until the index refreshes. Closing with Cancel returns focus to the triggering Manage button.

- [ ] **Step 2: Write failing atomic-save and row-patch tests**

Set visibility, member checkboxes, tag checkboxes, and profile in the editor. Assert one request is sent:

```javascript
assert.equal(call.url, '/api/admin/books/book%2Fid/settings');
assert.equal(call.options.method, 'PUT');
assert.deepEqual(JSON.parse(call.options.body), {
  visibility: 'restricted',
  user_ids: ['member-1', 'member-2'],
  tag_ids: ['tag-1'],
  profile: 'technical',
});
```

Assert success replaces only the matching summary in `adminBooksState.books`, preserves search/filter/page, and does not request users, AI settings, tags, or the whole book index.

- [ ] **Step 3: Write failing destructive-confirmation tests**

Stub `root.confirm`. Assert cancel sends no request. Assert confirmation text contains the book title, confirmation sends the existing `DELETE /api/admin/ai/results` body `{"book_id": id}`, displays the deleted count, and patches only `ai_result_count` for that summary.

- [ ] **Step 4: Run Node tests and verify failure**

Run: `node --test tests/test_auth_ui.js`

Expected: FAIL because the old implementation eagerly builds editors and saves each settings group separately.

- [ ] **Step 5: Implement the expandable detail row**

Render access, grants, tags, profile, save/cancel, and clear-results controls inside a `<tr><td colspan="6">`. Use one active editor ID, retain unsaved controls only while open, and mark the row busy during GET/PUT/DELETE. Do not open another modal.

Only enabled members appear as grant options. Disable the grant fieldset when visibility is not `restricted`, but keep the selected values so toggling back does not lose the administrator's pending selection.

- [ ] **Step 6: Implement atomic save and targeted state patching**

Build the complete payload from editor controls and call the settings endpoint. On success replace the matching summary by ID, cache returned detail, re-run filtering/pagination, and restore the editor beneath the same book if it remains on the current page.

Use a per-editor generation token so a late response from a previously closed row cannot overwrite the current editor.

- [ ] **Step 7: Implement scoped result confirmation**

First extend `clearAiResults(scope, reload)` so `reload === false` returns the parsed response without calling `loadAdminData()`. Translate a template such as `admin.books.clearResultsConfirm`, replace `{title}` with the plain book title, call `root.confirm`, and use `clearAiResults({book_id: bookId}, false)` so the action does not reload unrelated administrator data.

Make the no-reload contract explicit in the shared helper:

```javascript
return response.json().then(function(payload) {
  showStatus('admin.ai.cacheCleared', 'success');
  return reload === false ? payload : loadAdminData();
});
```

- [ ] **Step 8: Replace eager-card CSS with responsive table/editor CSS**

Remove selectors used only by the old full-card renderer. Add a horizontally scrollable table wrapper, compact badges/counts, sticky header, 44px Manage button, full-width editor row, two-column editor groups above 860px, and one-column groups below 860px. Keep focus-visible styling and reduced-motion behavior.

```css
.admin-book-editor-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); }
.admin-book-editor-row > td { padding: 1rem; }
.admin-book-manage { min-height: 44px; }
@media (max-width: 860px) {
  .admin-book-editor-grid { grid-template-columns: minmax(0, 1fr); }
}
```

- [ ] **Step 9: Run UI tests and syntax checks**

Run: `node --check epub_browser/assets/auth.js`

Run: `node --test tests/test_auth_ui.js tests/test_i18n.js tests/test_bookshelf_metadata.js`

Expected: PASS.

- [ ] **Step 10: Commit lazy editing and atomic save UI**

```bash
git add epub_browser/assets/auth.js epub_browser/assets/account.css tests/test_auth_ui.js
git commit -m "feat: edit administrator book settings on demand"
```

---

### Task 6: Verify book management and full Server/SSG compatibility

**Files:**
- Verify: `epub_browser/state.py`
- Verify: `epub_browser/server.py`
- Verify: `epub_browser/site.py`
- Verify: `epub_browser/assets/auth.js`
- Verify: `epub_browser/assets/account.css`

**Interfaces:**
- Consumes: Tasks 1-5 and both prerequisite plans.
- Produces: fully verified optimized administration surfaces.

- [ ] **Step 1: Run focused Python suites**

Run: `python3 -m unittest tests.test_state tests.test_server.AdminAccountTests tests.test_server.BookAuthorizationTests tests.test_site tests.test_generated_reader_surfaces tests.test_i18n_coverage -v`

Expected: PASS.

- [ ] **Step 2: Run focused Node suites**

Run: `node --test tests/test_auth_ui.js tests/test_i18n.js tests/test_bookshelf_metadata.js`

Expected: PASS.

- [ ] **Step 3: Run complete Python and Node suites**

Run: `python3 -W ignore::ResourceWarning -m unittest discover -s tests -p 'test_*.py'`

Run: `node --test tests/*.js`

Run: `git diff --check`

Expected: all suites pass.

- [ ] **Step 4: Inspect cache and API boundaries**

Confirm `.server-content-revision` is unchanged, SSG-generated HTML contains none of the administrator table IDs, no new SSG JavaScript calls `/api/admin/*`, and the existing `/api/admin/books` response tests remain green.

- [ ] **Step 5: Commit verification-only fixture corrections if present**

If verification required test-fixture corrections, commit only those verified files:

```bash
git add tests
git commit -m "test: complete administrator book coverage"
```

If no correction was required, leave the working tree unchanged and record the passing commands in the final handoff.
