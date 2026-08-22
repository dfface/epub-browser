# AI Reading Context Budget Implementation Plan

> **For Codex:** Follow this plan task by task with strict red-green-refactor cycles.

**Goal:** Stop truncating chapter source at 48,000 characters, fit every provider request to the configured model context window, preserve complete long-chapter coverage through chunk analysis and synthesis, and survive transient provider 5xx/cooling periods with bounded backoff.

**Architecture:** Keep the full extracted EPUB chapter as the cache and validation source. Derive input/output budgets from `model_context_window`, measure the actual prompt envelope, and either make one generation call or split the chapter on paragraph/token boundaries. Oversized chapters use compact per-chunk analyses followed by one final learning-layer synthesis. Provider calls use an explicit transient retry schedule while authorization and quota are rechecked before every real attempt.

**Tech Stack:** Python 3, `asyncio`, existing dependency-free OpenAI-compatible client, SQLite-backed `StateStore`, `unittest`.

---

### Task 1: Preserve complete chapter extraction

**Files:**
- Modify: `epub_browser/ai_reading.py`
- Test: `tests/test_ai_reading.py`

1. Add a regression test with source text longer than 48,000 characters and assert the final marker remains present.
2. Run the focused test and confirm it fails because `extract_chapter_text` returns a fixed prefix.
3. Remove the fixed default character limit while retaining source parsing and empty-source validation.
4. Run the focused extraction tests and confirm they pass.

### Task 2: Derive provider budgets and split without dropping source

**Files:**
- Modify: `epub_browser/ai_reading.py`
- Test: `tests/test_ai_reading.py`

1. Add table-driven tests proving output and prompt reserves are derived from small and large configured context windows.
2. Add a regression test proving paragraph/token chunks each fit the requested budget and their concatenated content retains the beginning, middle, and ending in order.
3. Implement a context-budget value object/helper and a paragraph-aware token splitter with a hard split fallback for a single oversized paragraph.
4. Run focused helper tests and refactor only after green.

### Task 3: Analyze and synthesize oversized chapters

**Files:**
- Modify: `epub_browser/ai_reading.py`
- Test: `tests/test_ai_reading.py`

1. Add an integration-style service test with a deliberately small context window and a long multi-paragraph chapter.
2. Assert every source marker reaches exactly one chunk-analysis request, every request fits the context budget, the final synthesis sees all chunk analyses, the stored annotations are validated against the original full chapter, and job progress reaches the number of chunk calls plus one.
3. Run the test and confirm the current single-call implementation fails.
4. Implement prompt-envelope measurement, chunk-analysis prompts, compact analysis bounds, final synthesis, and dynamic job progress updates.
5. Keep existing one-call behavior when the complete chapter fits.
6. Run the focused AI reading tests.

### Task 4: Retry transient provider failures across cooling windows

**Files:**
- Modify: `epub_browser/ai_reading.py`
- Test: `tests/test_ai_reading.py`

1. Replace the existing one-retry test with behavior tests for transient failures followed by success and for a non-retryable 4xx-style error.
2. Patch only the real clock wait boundary so tests assert the requested delays without sleeping.
3. Confirm failures against the current 0.6-second single retry.
4. Implement bounded delays of 60, 120, and 240 seconds; before every retry recheck authorization, book visibility, and daily quota.
5. Run focused retry tests and confirm four total attempts at most.

### Task 5: Verify compatibility

**Files:**
- Verify: `epub_browser/ai_reading.py`
- Verify: `tests/test_ai_reading.py`

1. Run `uv run --with-editable . python -W ignore::ResourceWarning -m unittest tests.test_ai_reading tests.test_ai_client tests.test_state`.
2. Run `uv run --with-editable . python -W ignore::ResourceWarning -m unittest discover -s tests`.
3. Run `node --test tests/*.js`.
4. Run `git diff --check` and inspect `git diff --stat` plus the complete diff.
5. Confirm `.server-content-revision` is unchanged because this is Server runtime logic, not content-cache schema.
