# Chapter AI Multi-Stage Generation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make one chapter AI reading task generate a Feynman explanation and a source-grounded learning layer through multiple provider calls while consuming one member daily reading allowance.

**Architecture:** Keep one durable `ai_reading_jobs` row and one public result. Reserve a chapter-reading allowance once per job, then run source preparation when needed, a core-learning call, and a source-grounding call in sequence before atomically storing the merged normalized result. Preserve `provider_calls` as operational telemetry and add task allowance state separately.

**Tech Stack:** Python 3.12, SQLite, Starlette server APIs/SSE, vanilla JavaScript, CSS custom properties, `unittest`.

**Spec:** `docs/superpowers/specs/2026-08-24-chapter-ai-multistage-design.md`

## Global Constraints

- Keep AI reading Server-only; SSG output must not load AI routes, scripts, or state.
- Do not change `SERVER_OUTPUT_REVISION`; this changes runtime AI data and UI, not EPUB-derived content-cache schema.
- All new reader, progress, and administrator copy requires both English and Simplified Chinese translations.
- Preserve the current exact-source validation for annotations, paragraph notes, and chapter-summary beats.
- A normal chapter runs the core and grounding calls sequentially; automatic provider retries and reader retry of the same failed job never reserve another chapter-reading allowance.
- A forced user regeneration creates a new job and reserves a new allowance; cache hits and administrator retry do not.
- Run `git diff --check` before each task commit and leave unrelated worktree changes untouched.

---

### Task 1: Migrate durable AI task accounting and stage progress

**Files:**
- Modify: `epub_browser/state.py:26-75, 185-250, 470-480, 803-841, 3501-3825`
- Modify: `tests/test_state.py` (or the existing SQLite migration test module that covers schema v11)

**Interfaces:**
- Produces `DB_SCHEMA_VERSION == 12`.
- Produces `ai_usage.reading_tasks INTEGER NOT NULL DEFAULT 0`.
- Produces `ai_reading_jobs.quota_reserved INTEGER NOT NULL DEFAULT 0` and `generation_stage TEXT`.
- Produces `StateStore.reserve_ai_reading_task(job_id: str, principal: Principal, usage_day: str) -> bool`, `StateStore.record_ai_provider_call(principal: Principal, usage_day: str) -> None`, and `StateStore.update_ai_job_progress(job_id: str, progress_current: int, progress_total: int, generation_stage: Optional[str] = None) -> bool`.

- [ ] **Step 1: Write failing migration and idempotency tests**

```python
def test_v12_migration_adds_task_usage_and_job_stage_without_converting_provider_calls(self):
    with sqlite3.connect(self.database) as connection:
        connection.execute(
            "INSERT INTO ai_usage (user_id, usage_day, provider_calls) VALUES (?, '2026-08-24', 7)",
            (self.owner.user_id,),
        )
        connection.execute("PRAGMA user_version = 11")
    store = StateStore(self.database)
    store.initialize()

    with sqlite3.connect(self.database) as connection:
        row = connection.execute("SELECT provider_calls, reading_tasks FROM ai_usage WHERE user_id = ?", (self.owner.user_id,)).fetchone()
        self.assertEqual(row, (7, 0))
        self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 12)

def test_reading_task_reservation_is_idempotent_for_one_job(self):
    member = self.store.create_user("reader", "hash", role="member")
    self.store.set_ai_user_access(member.user_id, enabled=True, daily_limit=2)
    self.store.create_ai_job("task-job", member.user_id, "cache")

    self.assertTrue(self.store.reserve_ai_reading_task("task-job", member, "2026-08-24"))
    self.assertTrue(self.store.reserve_ai_reading_task("task-job", member, "2026-08-24"))
    with self.store._connection() as connection:
        self.assertEqual(connection.execute("SELECT reading_tasks FROM ai_usage WHERE user_id = ?", (member.user_id,)).fetchone()[0], 1)
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `python -m unittest tests.test_state.StateStoreTests.test_v12_migration_adds_task_usage_and_job_stage_without_converting_provider_calls tests.test_state.StateStoreTests.test_reading_task_reservation_is_idempotent_for_one_job`

Expected: FAIL because schema version 12, the new columns, and `reserve_ai_reading_task` do not exist.

- [ ] **Step 3: Implement schema v12 and state methods**

```python
DB_SCHEMA_VERSION = 12

def reserve_ai_reading_task(self, job_id: str, principal: Principal, usage_day: str) -> bool:
    with self._connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        job = connection.execute(
            "SELECT owner_user_id, quota_reserved FROM ai_reading_jobs WHERE id = ?", (job_id,)
        ).fetchone()
        if job is None:
            raise KeyError(job_id)
        if job["quota_reserved"]:
            connection.execute("COMMIT")
            return True
        if job["owner_user_id"] != principal.user_id or not self.can_use_ai(principal):
            connection.execute("COMMIT")
            return False
        used = connection.execute(
            "SELECT reading_tasks FROM ai_usage WHERE user_id = ? AND usage_day = ?",
            (principal.user_id, usage_day),
        ).fetchone()
        if self.ai_daily_limit(principal) and used is not None and used["reading_tasks"] >= self.ai_daily_limit(principal):
            connection.execute("COMMIT")
            return False
        connection.execute(
            "INSERT INTO ai_usage (user_id, usage_day, reading_tasks) VALUES (?, ?, 1) "
            "ON CONFLICT(user_id, usage_day) DO UPDATE SET reading_tasks = ai_usage.reading_tasks + 1",
            (principal.user_id, usage_day),
        )
        connection.execute("UPDATE ai_reading_jobs SET quota_reserved = 1 WHERE id = ?", (job_id,))
        connection.execute("COMMIT")
        return True
```

Implement v12 as an additive migration: add the two job columns and `reading_tasks` to existing tables, include them in new-database table definitions and all public/admin job SELECT projections, and set `PRAGMA user_version = 12` only after integrity checks. Existing `provider_calls` values remain unchanged. Extend `update_ai_job_progress` to validate one of `None`, `preparing_source`, `generating_core`, or `grounding_source` and persist it with the numeric progress.

- [ ] **Step 4: Run migration and state tests to verify they pass**

Run: `python -m unittest tests.test_state`

Expected: PASS, including old-schema migration coverage and the new reservation idempotency cases.

- [ ] **Step 5: Commit the durable accounting layer**

```bash
git add epub_browser/state.py tests/test_state.py
git diff --check
git commit -m "feat: track chapter AI task allowances"
```

### Task 2: Separate task allowance reservation from provider-attempt telemetry

**Files:**
- Modify: `epub_browser/ai_reading.py:1015-1075, 700-770, 930-977`
- Modify: `tests/test_ai_reading.py`

**Interfaces:**
- Consumes `StateStore.reserve_ai_reading_task` from Task 1.
- Produces `_provider_call(..., task_scoped: bool = False) -> str` that records actual provider attempts without reserving chapter allowances for task-scoped calls.
- Produces `_reserve_generation_task(job_id: str, principal: Principal, request: ReadingRequest) -> None`.

- [ ] **Step 1: Write failing usage-semantics tests**

```python
async def test_one_chapter_job_can_make_two_provider_calls_with_one_task_allowance(self):
    self.client.responses = [CORE_JSON, GROUNDING_JSON]
    completed = await self._run_chapter_job()

    self.assertEqual(completed["status"], "complete")
    self.assertEqual(self._provider_calls(self.member.user_id), 2)
    self.assertEqual(self._reading_tasks(self.member.user_id), 1)

async def test_retrying_a_failed_chapter_job_does_not_reserve_a_second_task(self):
    self.client.responses = [AIProviderError.retryable("provider_server_error"), CORE_JSON, GROUNDING_JSON]
    failed = await self._run_chapter_job()
    retried = await self.service.retry_job(self.owner, failed["id"])

    await self._wait_for_job(retried["job"]["id"])
    self.assertEqual(self._reading_tasks(self.member.user_id), 1)
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `python -m unittest tests.test_ai_reading.AIReadingServiceTests.test_one_chapter_job_can_make_two_provider_calls_with_one_task_allowance tests.test_ai_reading.AIReadingServiceTests.test_retrying_a_failed_chapter_job_does_not_reserve_a_second_task`

Expected: FAIL because `_provider_call` currently calls `reserve_ai_usage` for every provider attempt.

- [ ] **Step 3: Implement reservation at durable-job start**

```python
def _reserve_generation_task(self, job_id, principal, request):
    if request.scope != "chapter":
        return
    if not self.store.reserve_ai_reading_task(job_id, principal, date.today().isoformat()):
        raise AIReadingError("ai_quota_exhausted")

async def _provider_call(..., task_scoped=False):
    live_principal = self._live_provider_principal(principal.user_id, book_id)
    if task_scoped:
        self.store.record_ai_provider_call(live_principal, date.today().isoformat())
    elif not self.store.reserve_ai_usage(live_principal, date.today().isoformat()):
        raise AIReadingError("ai_quota_exhausted")
    return await asyncio.to_thread(client.complete, messages, max_tokens=max_tokens)
```

Call `_reserve_generation_task` after a worker has claimed a non-cached chapter job and before its first provider attempt. Preserve cache-race handling so a job that resolves to a current cached result does not reserve. Preserve the existing per-call quota behavior for non-chapter follow-up/chat requests until that surface receives its own task-accounting design.

- [ ] **Step 4: Run the focused service tests to verify they pass**

Run: `python -m unittest tests.test_ai_reading.AIReadingServiceTests`

Expected: PASS; provider attempt counts may rise for a multi-stage chapter, while member chapter allowance remains one.

- [ ] **Step 5: Commit quota semantics**

```bash
git add epub_browser/ai_reading.py tests/test_ai_reading.py
git diff --check
git commit -m "feat: charge chapter AI by task"
```

### Task 3: Split chapter generation into core and source-grounded contracts

**Files:**
- Modify: `epub_browser/prompt_templates/chapter-reading-layer.json`
- Modify: `epub_browser/prompt_templates.py`
- Modify: `epub_browser/ai_reading.py:24-45, 256-455, 1120-1360, 1456-1645`
- Modify: `tests/test_ai_reading.py`

**Interfaces:**
- Produces `chapter_core_template()` and `chapter_grounding_template()` explicit prompt builders.
- Produces `_normalize_core_result(raw: str) -> dict`, `_normalize_grounding_result(raw: str) -> dict`, and `_merge_chapter_layers(core: dict, grounding: dict) -> dict`.
- Produces persisted `content` with exactly `quick`, `teach`, `chapter_summary`, `structure`, `deep`, `evidence`, `annotations`, and `paragraph_notes`.

- [ ] **Step 1: Write failing contract and merge tests**

```python
def test_chapter_core_contract_normalizes_feynman_teach_without_anchor_fields(self):
    core = _normalize_core_result(json.dumps({
        "quick": {"title": "Guide", "summary": "Overview", "key_points": []},
        "teach": {"explanation": "Plain explanation", "analogy": "Daily analogy", "check_question": "Explain it back."},
        "chapter_summary": {"overview": "", "beats": [], "key_elements": [], "closing": ""},
        "structure": {"overview": "", "diagram_mermaid": "", "nodes": [], "links": []},
        "deep": {"themes": [], "questions": [], "applications": []},
    }))
    self.assertEqual(core["teach"]["explanation"], "Plain explanation")

def test_merge_keeps_only_grounded_annotations(self):
    merged = _merge_chapter_layers(CORE_LAYER, GROUNDING_LAYER)
    validated = AIReadingService._validate_learning_layer(merged, CHAPTER_REQUEST, "Exact source quote.")
    self.assertEqual(validated["annotations"], [GROUNDING_LAYER["annotations"][0]])
```

- [ ] **Step 2: Run the contract tests to verify they fail**

Run: `python -m unittest tests.test_ai_reading.ResultNormalizationTests.test_chapter_core_contract_normalizes_feynman_teach_without_anchor_fields tests.test_ai_reading.ResultNormalizationTests.test_merge_keeps_only_grounded_annotations`

Expected: FAIL because generation currently has one prompt and one all-fields normalizer.

- [ ] **Step 3: Implement two sequential final calls**

```python
core_raw = await self._provider_call(
    principal, config, core_messages(material), book_id=request.book_id,
    max_tokens=budget.output_tokens,
)
core = _normalize_core_result(core_raw)
grounding_material = self._grounding_material(material, core, budget, config.model)
grounding_raw = await self._provider_call(
    principal, config, grounding_messages(grounding_material), book_id=request.book_id,
    max_tokens=budget.output_tokens,
)
content = self._validate_learning_layer(
    _merge_chapter_layers(core, _normalize_grounding_result(grounding_raw)),
    request, source_material,
)
```

Version the chapter templates together so cached version-7/8 results are not selected as if they contained the multi-stage contract. Keep full-book generation on its existing one-layer contract. Reuse `_analyze_oversized_source`; when it is needed, pass its ordered analysis representation to both stage builders and include the compact normalized core synopsis only in the grounding-stage user message. Set `generation_stage` to `preparing_source`, `generating_core`, and `grounding_source` at each durable progress update. Store a result only after both stages and validation succeed.

- [ ] **Step 4: Run generation, budget, and validation tests to verify they pass**

Run: `python -m unittest tests.test_ai_reading.ResultNormalizationTests tests.test_ai_reading.AIReadingServiceTests.test_tiny_chapter_generation_preserves_the_2048_context_minimum tests.test_ai_reading.AIReadingServiceTests.test_server_content_cache_is_used_without_generated_reader_html`

Expected: PASS; the 2048-token fallback still fits, complete output contains `teach`, and a failed grounding stage leaves no partial result.

- [ ] **Step 5: Commit multi-stage generation**

```bash
git add epub_browser/ai_reading.py epub_browser/prompt_templates.py epub_browser/prompt_templates/chapter-reading-layer.json tests/test_ai_reading.py
git diff --check
git commit -m "feat: split chapter AI generation into learning stages"
```

### Task 4: Render the Feynman learning section on both chapter AI surfaces

**Files:**
- Modify: `epub_browser/assets/ai-canvas.js:300-335`
- Modify: `epub_browser/assets/ai-canvas.css`
- Modify: `epub_browser/assets/ai-reading.js:311-390`
- Modify: `epub_browser/assets/ai-reading.css`
- Modify: `epub_browser/assets/i18n.js`
- Modify: `tests/test_generated_reader_surfaces.py`
- Modify: `tests/test_i18n_coverage.py`

**Interfaces:**
- Consumes normalized `content.teach { explanation, analogy, check_question }` from Task 3.
- Produces `[data-ai-chapter-teach]` in the chapter canvas and `.ai-reading-teach` in the legacy drawer only when `teach.explanation` is non-empty.

- [ ] **Step 1: Write failing reader-surface tests**

```python
def test_chapter_ai_surfaces_render_feynman_teach_only_for_a_chapter_explanation(self):
    canvas = Path("epub_browser/assets/ai-canvas.js").read_text(encoding="utf-8")
    drawer = Path("epub_browser/assets/ai-reading.js").read_text(encoding="utf-8")

    self.assertIn("data-ai-chapter-teach", canvas)
    self.assertIn("teach.explanation", canvas)
    self.assertIn("content.teach", drawer)
    self.assertIn("ai.teachCheck", canvas)
```

Add translation coverage for `ai.teachKicker`, `ai.teachTitle`, `ai.teachAnalogy`, `ai.teachCheck`, and a rendering fixture that omits `teach.explanation` to verify the section is absent rather than empty.

- [ ] **Step 2: Run the new surface tests to verify they fail**

Run: `python -m unittest tests.test_generated_reader_surfaces.GeneratedReaderSurfaceTests.test_chapter_ai_surfaces_render_feynman_teach_only_for_a_chapter_explanation tests.test_i18n_coverage.I18nCoverageTests`

Expected: FAIL because neither AI surface has a Feynman section or all localized labels.

- [ ] **Step 3: Implement the accessible learning section**

```javascript
function appendTeach(article, result, chapterIndex) {
  var teach = result.content && result.content.teach || {};
  if (!teach.explanation) return;
  var section = el('section', 'ai-chapter-teach');
  section.setAttribute('data-ai-chapter-teach', '');
  section.setAttribute('data-ai-canvas-chapter', String(chapterIndex));
  // Render title, explanation, optional analogy, and optional self-check
  // with textContent-only nodes; insert after the opening guide.
}
```

Keep the explanation in the Server-only canvas and legacy drawer, exclude `.ai-chapter-teach` from source-anchor matching, and let `clearChapter` remove it using the existing `data-ai-canvas-chapter` cleanup. Use theme tokens, a visible semantic heading, 16px-or-larger explanatory text, and a 44px minimum target only where an interactive control exists (the section itself is non-interactive). Add both locale entries.

- [ ] **Step 4: Run reader surface and i18n tests to verify they pass**

Run: `python -m unittest tests.test_generated_reader_surfaces tests.test_i18n_coverage`

Expected: PASS; SSG remains free of AI assets and both Server AI surfaces handle populated and empty teach data safely.

- [ ] **Step 5: Commit reader rendering**

```bash
git add epub_browser/assets/ai-canvas.js epub_browser/assets/ai-canvas.css epub_browser/assets/ai-reading.js epub_browser/assets/ai-reading.css epub_browser/assets/i18n.js tests/test_generated_reader_surfaces.py tests/test_i18n_coverage.py
git diff --check
git commit -m "feat: add Feynman chapter explanations"
```

### Task 5: Expose stage progress and task-based member-limit copy

**Files:**
- Modify: `epub_browser/ai_reading.py:525-535`
- Modify: `epub_browser/server.py:1900-1985`
- Modify: `epub_browser/assets/ai-canvas.js:14-18, 350-380`
- Modify: `epub_browser/assets/ai-reading.js` (job-event status rendering)
- Modify: `epub_browser/site.py:199-208`
- Modify: `epub_browser/assets/i18n.js`
- Modify: `tests/test_ai_reading.py`
- Modify: `tests/test_generated_reader_surfaces.py`
- Modify: `tests/test_site.py`
- Modify: `tests/test_i18n_coverage.py`

**Interfaces:**
- Consumes `generation_stage` from Task 1.
- Produces public job payload field `generation_stage: str | None`.
- Produces localized keys `ai.stage.preparingSource`, `ai.stage.generatingCore`, `ai.stage.groundingSource`.

- [ ] **Step 1: Write failing public-payload and UI-copy tests**

```python
def test_public_ai_job_includes_only_safe_stage_progress(self):
    public = _public_ai_job({"id": "job", "request_json": "secret", "generation_stage": "generating_core"})
    self.assertEqual(public["generation_stage"], "generating_core")
    self.assertNotIn("request_json", public)

def test_member_daily_limit_describes_chapter_reading_tasks(self):
    html = render_library_shell(...)
    self.assertIn('data-i18n="admin.ai.dailyLimit"', html)
    self.assertIn("AI reading tasks each authorized member may start per day", i18n_english)
```

- [ ] **Step 2: Run the public-payload and UI-copy tests to verify they fail**

Run: `python -m unittest tests.test_ai_reading.ResultNormalizationTests.test_public_ai_job_includes_only_safe_stage_progress tests.test_site.SitePublicationTests tests.test_i18n_coverage.I18nCoverageTests`

Expected: FAIL because stage-specific labels and task-based help copy do not exist.

- [ ] **Step 3: Implement public stage status and localized presentation**

```javascript
function generationStatus(job, context) {
  var stageKey = job.generation_stage && {
    preparing_source: 'ai.stage.preparingSource',
    generating_core: 'ai.stage.generatingCore',
    grounding_source: 'ai.stage.groundingSource'
  }[job.generation_stage];
  return stageKey ? t(stageKey) : contextLabel(context);
}
```

Use this label in canvas and drawer event handlers while retaining the numeric `current/total` progress for assistive status text. Include `generation_stage` in server SSE/public-job serialization but never expose request JSON. Update administrator copy and help text so the configured daily limit says **AI reading tasks**, clarifying that one chapter reading task may use several backend model calls.

- [ ] **Step 4: Run UI/API regression tests to verify they pass**

Run: `python -m unittest tests.test_site tests.test_i18n_coverage tests.test_generated_reader_surfaces tests.test_ai_reading`

Expected: PASS; user-visible progress is localized, no private job data leaks, and the member-limit wording matches accounting behavior.

- [ ] **Step 5: Commit stage progress UI**

```bash
git add epub_browser/ai_reading.py epub_browser/server.py epub_browser/assets/ai-canvas.js epub_browser/assets/ai-reading.js epub_browser/site.py epub_browser/assets/i18n.js tests/test_ai_reading.py tests/test_generated_reader_surfaces.py tests/test_site.py tests/test_i18n_coverage.py
git diff --check
git commit -m "feat: show chapter AI generation stages"
```

### Task 6: Run full migration, Server/SSG, and regression verification

**Files:**
- Modify only if verification identifies a concrete defect in a preceding task.
- Test: `tests/test_ai_reading.py`, `tests/test_state.py`, `tests/test_generated_reader_surfaces.py`, `tests/test_i18n_coverage.py`, `tests/test_site.py`

**Interfaces:**
- Consumes all previous task interfaces.
- Produces a verified Server-only multi-stage chapter AI reading flow with unchanged SSG output boundaries.

- [ ] **Step 1: Run the complete focused regression suite**

Run: `python -m unittest tests.test_state tests.test_ai_reading tests.test_generated_reader_surfaces tests.test_i18n_coverage tests.test_site`

Expected: PASS with no migrations skipped and no unexpected warnings.

- [ ] **Step 2: Run static and asset checks**

Run:

```bash
python -m py_compile epub_browser/state.py epub_browser/ai_reading.py epub_browser/server.py
node --check epub_browser/assets/ai-canvas.js
node --check epub_browser/assets/ai-reading.js
node --check epub_browser/assets/i18n.js
git diff --check
```

Expected: every command exits 0.

- [ ] **Step 3: Perform Server/SSG boundary checks**

Run: `python -m unittest tests.test_generated_reader_surfaces.GeneratedReaderSurfaceTests.test_ai_reading_controls_use_the_native_canvas_without_extra_book_pages`

Expected: PASS; Server chapter output includes AI canvas assets, while generated SSG output contains neither AI controls nor `/api/ai` references.
