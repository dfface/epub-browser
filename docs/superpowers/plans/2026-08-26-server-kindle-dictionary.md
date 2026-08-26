# 已废弃：Server Kindle 词典导入与查词 Implementation Plan

**状态：已废弃（2026-08-26）**

本计划不再执行。现行计划见：[本地词典与百科查阅 Implementation Plan](2026-08-26-local-dictionary-and-encyclopedia.md)。

---

以下内容仅保留作决策记录，不作为实施依据。

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 Server 阅读页提供无 DRM Kindle Mobi 7 词典的管理员导入和零留痕查词；选区仅显示复制、高亮、笔记、查词四项。

**Architecture:** StateStore 保存词典目录、语言默认项和可恢复导入任务；词典正文保存在独立只读 SQLite。DictionaryService 负责文件、导入队列、查询；Server 仅处理鉴权与 HTTP。词典资源只发布给 Server 动态章节，SSG 保持本地三项选区动作。

**Tech Stack:** Python 3.9, SQLite, Starlette, 原生 JavaScript/CSS, unittest。

**Spec:** docs/superpowers/specs/2026-08-26-server-kindle-dictionary-design.md

## Global Constraints

- 仅支持无 DRM Mobi 7 .mobi 与实际容器为 Mobi 7 的 .azw；拒绝 AZW3/KF8、KFX、加密或非词典文件。
- 词典发行物按 GPLv3 分发，直接固定依赖 GPL-3.0-only 的 Python `mobi==0.4.1`；不引入 Calibre。
- 不提高 SERVER_OUTPUT_REVISION；不改变 book/<id>/content/ 或要求 EPUB 重转。
- 词典正文只存于 <server-dir>/data/dictionaries/<uuid>.sqlite；不得进入主状态库、EPUB 缓存或 SSG。
- 所有写操作经登录、管理员角色和 CSRF；查词先经书籍 ACL，使用 POST 与 private, no-store，且不保存历史。
- 所有可见文字覆盖 en、zh-CN、zh-TW、ko、ja；SSG 绝不发布词典资产、控件、配置或 API URL。
- UI 服从现有主题 token：WCAG AA 对比度、可见焦点、键盘可达、44px 触摸目标、8px 间距、reduced motion。

## File Structure

| File | Responsibility |
| --- | --- |
| epub_browser/state.py | Schema 14 与字典目录、默认项、任务的事务 API。 |
| epub_browser/kindle_dictionary.py | `mobi.extract()` 适配、恢复 HTML 的受限词典条目抽取与纯文本清洗。 |
| epub_browser/dictionary_service.py | 独立 SQLite 生成、队列、清理及只读 lookup。 |
| epub_browser/server.py | 生命周期和管理员/读者 API。 |
| epub_browser/asset_publisher.py, processor.py | Server-only 资源和章节 runtime config。 |
| epub_browser/server_chrome.py, assets/auth.js | 词典管理界面。 |
| assets/dictionary.js, assets/dictionary.css, assets/annotation.js | 查询浮层和四动作选区菜单。 |
| assets/i18n.js | 五语言文案。 |
| tests/test_state.py, test_kindle_dictionary.py, test_dictionary_service.py, test_server.py, test_dictionary.js, test_annotation.js | 状态、解析、服务、权限和 UI 回归。 |

### Task 1: Add schema 14 and StateStore APIs

**Files:**
- Modify: epub_browser/state.py
- Modify: tests/test_state.py

**Interfaces:**
- Produces DictionaryRecord and DictionaryImportJob dataclasses.
- Produces create_dictionary_import_job, claim_next_dictionary_import_job, complete_dictionary_import_job, fail_dictionary_import_job, create_dictionary, list_dictionaries, set_dictionary_enabled, set_dictionary_default, get_dictionary_default, and delete_dictionary.

- [ ] **Step 1: Write failing schema and invariant tests**

~~~
def test_schema_v14_creates_dictionary_tables_and_indexes(self):
    store = StateStore(self.database_path)
    store.initialize(self.bootstrap)
    with store._connection() as connection:
        self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 14)

def test_disabling_default_dictionary_clears_default(self):
    record = self.create_enabled_dictionary(source_language="en")
    self.store.set_dictionary_default("en", record.id, self.admin.user_id)
    self.store.set_dictionary_enabled(record.id, False)
    self.assertIsNone(self.store.get_dictionary_default("en"))
~~~

- [ ] **Step 2: Run the tests to verify failure**

Run: python3 -m unittest tests.test_state

Expected: FAIL because version 14 and dictionary methods do not exist.

- [ ] **Step 3: Implement the minimal schema and transactional methods**

Define dictionaries, dictionary_defaults and dictionary_import_jobs exactly as in the approved spec. Raise DB_SCHEMA_VERSION to 14; add the v13-to-v14 flow and fresh-db version. Add queue, source-language, and dictionary-id indexes. In one transaction, clear defaults when a dictionary is disabled/deleted, enforce matching source language for defaults, and mark startup-running jobs interrupted.

~~~
def set_dictionary_default(self, source_language: str, dictionary_id: str,
                           updated_by_user_id: str) -> DictionaryRecord:
    """Require an enabled same-language dictionary and upsert its default."""
~~~

- [ ] **Step 4: Run focused regression tests**

Run: python3 -m unittest tests.test_state

Expected: PASS.

- [ ] **Step 5: Commit**

~~~
git add epub_browser/state.py tests/test_state.py
git commit -m "feat: add dictionary state schema"
~~~

### Task 2: Adapt the GPL Mobi extractor to bounded dictionary entries

**Files:**
- Create: epub_browser/kindle_dictionary.py
- Create: tests/test_kindle_dictionary.py

**Interfaces:**
- Produces KindleDictionaryEntry, ImportedKindleDictionary, KindleDictionaryLimits, KindleDictionaryError.
- Produces extract_kindle_dictionary(path, *, limits=KindleDictionaryLimits()).
- Consumed by DictionaryService in Task 3.

- [ ] **Step 1: Write failing extractor-adapter tests**

Mock `mobi.extract()` to return a temporary directory and a recovered dictionary HTML file containing `idx:entry`, `idx:orth` and `idx:iform` markup. Include an extractor exception, a recovered ordinary book, malformed dictionary HTML, zero-entry output and oversized source inputs.

~~~
def test_extracts_headword_inflections_and_plain_definition(self):
    result = extract_kindle_dictionary(self.write_fixture(b"MOBI fixture"))
    self.assertEqual(result.entries[0].headword, "run")
    self.assertEqual(result.entries[0].forms, ("run", "runs", "running"))
    self.assertEqual(result.entries[0].definition_text, "to move quickly")
~~~

- [ ] **Step 2: Run tests to verify failure**

Run: python3 -m unittest tests.test_kindle_dictionary

Expected: FAIL because the module is absent.

- [ ] **Step 3: Implement the `mobi` adapter and HTML sanitizer**

Validate filename, extension, source size and canonical temporary paths before invoking `mobi.extract()`. Convert its known unpacking errors into stable error codes. Parse only recovered `<idx:entry>` blocks, NFC-casefold and collapse whitespace for forms, preserve the human-readable headword, strip all tags/scripts/styles/external URLs with HTMLParser, and enforce entry/form/definition limits while extracting. Always remove the `mobi.extract()` temporary directory in `finally`.

~~~
@dataclass(frozen=True)
class KindleDictionaryLimits:
    max_file_bytes: int = 512 * 1024 * 1024
    max_records: int = 200_000
    max_entries: int = 2_000_000
    max_forms_per_entry: int = 64
    max_definition_bytes: int = 12 * 1024
~~~

- [ ] **Step 4: Verify adapter and syntax**

Run: python3 -m unittest tests.test_kindle_dictionary && python3 -m py_compile epub_browser/kindle_dictionary.py

Expected: PASS.

- [ ] **Step 5: Commit**

~~~
git add epub_browser/kindle_dictionary.py tests/test_kindle_dictionary.py
git commit -m "feat: extract Kindle dictionary entries with mobi"
~~~

### Task 3: Build DictionaryService and isolated dictionary files

**Files:**
- Create: epub_browser/dictionary_service.py
- Create: tests/test_dictionary_service.py

**Interfaces:**
- Consumes Task 1 StateStore methods and Task 2 extractor.
- Produces DictionaryService.start_worker, stop_worker, submit_import, retry_import, lookup, set_enabled, set_default and delete.

- [ ] **Step 1: Write failing service tests**

~~~
async def test_import_builds_separate_sqlite_and_lookup_has_no_state_write(self):
    service = DictionaryService(self.store, self.server_dir, parser=fake_parser)
    job = await service.submit_import(self.admin.user_id, "English.mobi", fixture_bytes)
    await service.run_one_job_for_test()
    result = service.lookup("en", "running")
    self.assertTrue(result.found)
    self.assertEqual(self.store.dictionary_lookup_history_count_for_test(), 0)
~~~

- [ ] **Step 2: Run tests to verify failure**

Run: python3 -m unittest tests.test_dictionary_service

Expected: FAIL because DictionaryService is absent.

- [ ] **Step 3: Implement secure file and queue lifecycle**

Write raw uploads as data/dictionary-imports/<job>.upload after body-size and file-name validation. Use one asyncio worker plus asyncio.to_thread for parsing. Build <dictionary>.sqlite.tmp with meta, entries and forms, integrity_check it, then atomically rename it to data/dictionaries/<dictionary>.sqlite before completing the state transaction. Open lookup connections with mode=ro, prefer forms before entries, return at most three senses and never write state. On startup mark running jobs interrupted and only remove stale tmp/upload/trash paths that have no catalog record.

- [ ] **Step 4: Run service/state tests**

Run: python3 -m unittest tests.test_dictionary_service tests.test_state

Expected: PASS.

- [ ] **Step 5: Commit**

~~~
git add epub_browser/dictionary_service.py tests/test_dictionary_service.py
git commit -m "feat: add isolated dictionary import service"
~~~

### Task 4: Expose protected API routes and integrate lifespan

**Files:**
- Modify: epub_browser/server.py
- Modify: tests/test_server.py

**Interfaces:**
- Consumes DictionaryService.
- Produces the approved admin dictionary APIs and POST /api/books/<book_id>/dictionary/lookup.

- [ ] **Step 1: Write failing authorization and response tests**

~~~
async def test_lookup_checks_book_acl_before_reading_metadata(self):
    response = await self.client.post(
        f"/api/books/{self.restricted_book_id}/dictionary/lookup",
        json={"text": "running"}, headers=self.member_headers,
    )
    self.assertEqual(response.status_code, 404)

async def test_lookup_is_private_no_store_and_has_no_history(self):
    response = await self.client.post(
        f"/api/books/{self.book_id}/dictionary/lookup",
        json={"text": "running"}, headers=self.reader_headers,
    )
    self.assertEqual(response.headers["cache-control"], "private, no-store")
~~~

- [ ] **Step 2: Run tests to verify failure**

Run: python3 -m unittest tests.test_server.DictionaryApiTests

Expected: FAIL because routes are absent.

- [ ] **Step 3: Add HTTP handlers in the existing Server style**

Register routes before the annotation catch-all. Require require_admin for all /api/admin/dictionaries routes; rely on global CSRF for mutations. Stream the raw upload with a 512 MiB cap; do not unboundedly read request.body. For lookup, require principal, deny inaccessible book before reading metadata, derive language only from protected cached metadata, validate JSON text, call service and send private/no-store response. Start/wake/stop DictionaryService with the AI worker in lifespan.

- [ ] **Step 4: Run server/auth regressions**

Run: python3 -m unittest tests.test_server tests.test_auth

Expected: PASS.

- [ ] **Step 5: Commit**

~~~
git add epub_browser/server.py tests/test_server.py
git commit -m "feat: expose protected dictionary APIs"
~~~

### Task 5: Enforce Server-only asset and cache boundary

**Files:**
- Modify: epub_browser/asset_publisher.py
- Modify: epub_browser/processor.py
- Modify: tests/test_asset_publisher.py
- Modify: tests/test_mode_integration.py

**Interfaces:**
- Produces Server-only manifest names dictionary.js and dictionary.css.
- Produces only Server chapters with data-dictionary-lookup="enabled" and a book-id runtime attribute.

- [ ] **Step 1: Write failing SSG/Server boundary tests**

~~~
def test_ssg_does_not_publish_dictionary_assets_or_api_urls(self):
    assets = EPUBLibrary(output_dir=self.output_dir).asset_manifest.assets
    self.assertNotIn("dictionary.js", assets)
    self.assertNotIn("dictionary.css", assets)

def test_server_chapter_uses_existing_cache_and_exposes_dictionary_config(self):
    html = self.render_server_chapter_from_cached_content(self.book_id, chapter_index=0)
    self.assertIn('data-dictionary-lookup="enabled"', html)
~~~

- [ ] **Step 2: Run tests to verify failure**

Run: python3 -m unittest tests.test_asset_publisher tests.test_mode_integration

Expected: FAIL because assets/config do not exist.

- [ ] **Step 3: Implement narrow asset/template branch**

Add both logical assets to SERVER_ONLY_ASSET_PATHS. Add a processor helper parallel to server AI asset handling which emits hashed URLs and minimal runtime attributes only when deployment_mode == "server". Do not serialize any dictionary data into EPUB content caches or change SERVER_OUTPUT_REVISION.

- [ ] **Step 4: Run rendering boundary tests**

Run: python3 -m unittest tests.test_asset_publisher tests.test_mode_integration tests.test_generated_reader_surfaces

Expected: PASS.

- [ ] **Step 5: Commit**

~~~
git add epub_browser/asset_publisher.py epub_browser/processor.py tests/test_asset_publisher.py tests/test_mode_integration.py
git commit -m "feat: isolate dictionary assets to server"
~~~

### Task 6: Implement accessible lookup popover and localize it

**Files:**
- Create: epub_browser/assets/dictionary.js
- Create: epub_browser/assets/dictionary.css
- Modify: epub_browser/assets/i18n.js
- Create: tests/test_dictionary.js
- Modify: tests/test_i18n.js
- Modify: tests/test_i18n_coverage.py

**Interfaces:**
- Produces window.EpubBrowserDictionary.lookup(selectionText, anchorRect) and close().
- Consumed by Task 7.

- [ ] **Step 1: Write failing client, abort and i18n tests**

~~~
test("lookup aborts earlier request and writes definitions as text", async () => {
  const first = dictionary.lookup("run", rect);
  const second = dictionary.lookup("running", rect);
  await second;
  assert.equal(fetch.mock.calls[0][1].signal.aborted, true);
  assert.equal(definition.textContent, "to move quickly");
});

test("all dictionary translations exist", () => {
  assert.deepEqual(missingTranslations("dictionary."), []);
});
~~~

- [ ] **Step 2: Run tests to verify failure**

Run: node --test tests/test_dictionary.js tests/test_i18n.js && python3 -m unittest tests.test_i18n_coverage

Expected: FAIL because assets and keys are absent.

- [ ] **Step 3: Implement the non-modal result surface**

Create elements with document.createElement and textContent only. POST JSON text using the existing CSRF helper and an AbortController. Render localized loading, not-found, unconfigured, unavailable and retryable-network messages; no raw server HTML. Use labelled role=dialog, a visible 44px close button, Escape/click-away close, aria-live=polite, focus return and viewport clamping. CSS must use existing color tokens, visible focus, >=8px action spacing, touch-action: manipulation and a reduced-motion rule.

- [ ] **Step 4: Run JS/i18n tests**

Run: node --test tests/test_dictionary.js tests/test_i18n.js && python3 -m unittest tests.test_i18n_coverage

Expected: PASS.

- [ ] **Step 5: Commit**

~~~
git add epub_browser/assets/dictionary.js epub_browser/assets/dictionary.css epub_browser/assets/i18n.js tests/test_dictionary.js tests/test_i18n.js tests/test_i18n_coverage.py
git commit -m "feat: add accessible dictionary lookup popover"
~~~

### Task 7: Replace automatic annotation creation with four action choices

**Files:**
- Modify: epub_browser/assets/annotation.js
- Modify: tests/test_annotation.js

**Interfaces:**
- Consumes EpubBrowserDictionary only when the Server marker is present.
- Produces showSelectionActionMenu, copySelection, createHighlight, openNoteEditor and lookupSelection.

- [ ] **Step 1: Write failing mutually-exclusive action tests**

~~~
test("copy clears the draft without persistence", async () => {
  await selectTextAndClick("copy");
  assert.equal(storage.createAnnotation.mock.calls.length, 0);
  assert.ok(highlighter.remove.mock.calls.length);
});

test("lookup removes the draft and never creates an annotation", async () => {
  await selectTextAndClick("lookup");
  assert.equal(storage.createAnnotation.mock.calls.length, 0);
  assert.equal(dictionary.lookup.mock.calls.length, 1);
});
~~~

- [ ] **Step 2: Run tests to verify failure**

Run: node --test tests/test_annotation.js

Expected: FAIL because the reader currently opens its combined annotation dialog.

- [ ] **Step 3: Refactor selection behavior without changing annotation persistence format**

Have handleHighlightCreate establish exactly one removable draft and a role=toolbar. Copy uses Utils.copyText then clears draft. Highlight immediately persists default-color/empty-note source. Note creates a textarea editor and persists only after explicit Save; Cancel, Escape and close remove draft. Lookup removes draft before delegating selected text and anchor rectangle. Omit lookup completely when there is no Server marker/module. Preserve current post-save color editing and add i18n labels/keyboard activation.

- [ ] **Step 4: Run reader interaction regressions**

Run: node --test tests/test_annotation.js tests/test_annotation_position.js tests/test_reader_layout.js

Expected: PASS.

- [ ] **Step 5: Commit**

~~~
git add epub_browser/assets/annotation.js tests/test_annotation.js
git commit -m "feat: simplify selection actions and add lookup"
~~~

### Task 8: Add administrator dictionary management UI

**Files:**
- Modify: epub_browser/server_chrome.py
- Modify: epub_browser/assets/auth.js
- Modify: epub_browser/assets/i18n.js
- Modify: tests/test_auth_ui.js
- Modify: tests/test_i18n.js

**Interfaces:**
- Consumes Task 4 admin APIs.
- Produces an admin-only dictionaries tab with upload, job status, catalog/default controls, enable state and delete confirmation.

- [ ] **Step 1: Write failing management UI tests**

~~~
test("upload disables submit and announces a failed job", async () => {
  await selectFile("English.mobi");
  await click("dictionary-upload-submit");
  assert.equal(submit.disabled, true);
  await resolveUpload({status: "failed", error_code: "dictionary_drm"});
  assert.equal(status.getAttribute("role"), "status");
});

test("delete requires confirmation and defaults list only enabled same-language dictionaries", () => {
  // Render list with one disabled and one enabled English dictionary.
});
~~~

- [ ] **Step 2: Run tests to verify failure**

Run: node --test tests/test_auth_ui.js tests/test_i18n.js

Expected: FAIL because the dictionaries tab is absent.

- [ ] **Step 3: Implement progressive, semantic controls**

Add role=tab and matching role=tabpanel with label-associated file input, format helper and submit button. Upload raw body with sanitized filename header; disable only submit while pending, poll boundedly only while tab is active, and expose failures with aria-live=polite plus Retry for failed/interrupted jobs. Render catalog as responsive list; offer default picker only for enabled same-source dictionaries. Use native explicit confirmation containing name before deletion; never render server paths/traces.

- [ ] **Step 4: Run UI/integration tests**

Run: node --test tests/test_auth_ui.js tests/test_i18n.js && python3 -m unittest tests.test_server tests.test_i18n_coverage

Expected: PASS.

- [ ] **Step 5: Commit**

~~~
git add epub_browser/server_chrome.py epub_browser/assets/auth.js epub_browser/assets/i18n.js tests/test_auth_ui.js tests/test_i18n.js
git commit -m "feat: add dictionary administration UI"
~~~

### Task 9: Final boundary and UI/UX review

**Files:**
- Modify only verified defects found by review.
- Test: tests/test_server_cache_boundary.js, tests/test_static_asset_delivery.py, full suite.

- [ ] **Step 1: Add final no-reconversion and no-SSG-leak tests**

~~~
def test_dictionary_ui_does_not_change_content_cache_revision(self):
    cached = self.render_server_chapter_from_cached_content(self.book_id, chapter_index=0)
    self.assertIn("data-dictionary-lookup", cached)
    self.assertEqual(SERVER_OUTPUT_REVISION, 1)

test("SSG selection menu has no lookup action or dictionary API URL", () => {
  assert.deepEqual(selectionActionsForSsg(), ["copy", "highlight", "note"]);
});
~~~

- [ ] **Step 2: Run the boundary tests**

Run: python3 -m unittest tests.test_mode_integration tests.test_static_asset_delivery tests.test_server && node --test tests/test_annotation.js tests/test_dictionary.js

Expected: PASS.

- [ ] **Step 3: Review the running UI and fix only recorded findings**

Review desktop and 375px reader/admin screens against WCAG 2.2 AA: tab order, focus return, Esc, 200% zoom reflow, 44px targets, loading/disabled/error states, light/dark contrast, hover independence and reduced motion. Use axe/Lighthouse where available; record severity, WCAG criterion, evidence and concrete change for each finding.

- [ ] **Step 4: Run final validation**

Run: python3 -m unittest discover -s tests && git diff --check

Expected: PASS with no whitespace errors.

- [ ] **Step 5: Commit final verification fixes**

~~~
git add epub_browser tests docs
git commit -m "test: verify dictionary reader integration"
~~~
