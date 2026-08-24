# Chapter AI reading: multi-stage generation

## Goal

A reader starts one chapter AI reading task and consumes one daily AI reading
allowance. The server may make multiple provider calls to improve completeness
and grounding. The feature includes the Feynman-style `teach` section, which
explains the chapter in plain language for a general reader.

## Decisions

- A new, non-cached chapter reading task reserves one user allowance.
- Provider calls within that task, including automatic transient retries, do
  not reserve more user allowances.
- Retrying the same failed task reuses its reservation. An administrator retry
  does not charge the member.
- A reader's explicit **Regenerate** action creates a new task and reserves a
  new allowance.
- Cached results do not reserve an allowance.
- The administrator can still see actual provider-call volume separately from
  reader task consumption.

## Reader flow

```text
Start chapter AI reading (1 allowance)
        |
        +-- source preparation (only for oversized chapters)
        |
        +-- Core learning layer
        |     quick guide + Feynman teach + chapter structure + mind map
        |
        +-- Source-grounded layer
        |     evidence + annotations + paragraph notes
        |
        +-- Validate, merge and atomically publish one result
```

The page retains a previous result while a forced regeneration runs. A failed
stage leaves that prior result visible and gives the task one retry path rather
than publishing a partial learning layer.

## Generation contracts

### Core learning layer

The first final call returns only the fields that require a coherent,
whole-chapter explanation:

- `quick`
- `teach { explanation, analogy, check_question }`
- `chapter_summary`
- `structure`
- `deep`

`teach.explanation` uses two to four short, plain-language paragraphs,
immediately defines unavoidable jargon, makes no claim absent from the source,
and is accompanied by an optional everyday analogy plus one question that asks
the reader to explain the main idea back in their own words.

### Source-grounded layer

The second final call receives the source plus a compact core-layer synopsis.
It returns only `evidence`, `annotations`, and `paragraph_notes`. Existing
exact-anchor validation remains the final gate before publication. For a source
that exceeds the model context, it instead receives the existing ordered
source-part analyses, which retain exact anchor excerpts; validation still uses
the original chapter source.

For oversized chapters, the existing contiguous-source analysis runs first and
its ordered synthesis is supplied to both final calls. The two final calls do
not run concurrently: this preserves the configured provider concurrency cap,
allows the source-grounded layer to use the core synopsis, and makes progress
and failure states deterministic.

The chapter prompt-template version increases because its result contract
changes. This invalidates only AI-result cache selection, not EPUB content
cache; `SERVER_OUTPUT_REVISION` is unchanged.

## Persistence and quota accounting

`ai_usage.provider_calls` remains telemetry for actual provider attempts. A
new task-count field records reader-visible usage. Existing provider-call
counts are not converted to task counts, so deployment does not unfairly block
members whose earlier chapter used multi-call generation.

Each `ai_reading_jobs` row records whether its task allowance is already
reserved, together with its current generation stage. Reserving a task and
incrementing that member's daily task counter occurs in one SQLite transaction.
The reservation is idempotent across worker restarts and retries.

The schema migration also adds a nullable stage field for public job progress.
It is safe for old completed jobs to have no stage. New tasks expose one of:
`preparing_source`, `generating_core`, or `grounding_source`.

## API and UI

The external request remains one `POST /api/ai/reading` request and the result
remains one result object. Public job payloads gain an optional stage value.
Server-rendered chapter pages and the legacy AI drawer both render `teach` only
when a normalized explanation is present.

The chapter canvas uses localized stage-specific live-status text, for example
“Generating plain-language explanation” and “Locating source evidence”. The
administration configuration labels the member limit as **AI reading tasks per
day**, not provider calls.

## Failure and recovery

- A provider failure ends the one visible job with its existing safe error
  code; no partial result is stored.
- Automatic network retries stay inside the already-reserved task.
- A reader retry uses the same job reservation and re-runs the task; it never
  publishes a partial learning layer.
- A settings/template change invalidates a queued task through the existing
  snapshot checks. A new user action then creates a new task reservation.

## Test plan

- Normalization accepts and bounds every `teach` field, with empty defaults.
- Core and source-grounded stage outputs merge into exactly one normalized
  result; invalid anchors are removed.
- A normal chapter performs two final provider calls while consuming one daily
  task allowance and recording two provider calls.
- Oversized chapters retain the existing source-part flow and then perform two
  final stages without exceeding context budgets.
- A transient provider retry, worker restart, and member retry do not increment
  the task allowance twice.
- A forced regeneration consumes a new task allowance; a cache hit consumes
  none.
- API events expose localized stage progress, and both AI surfaces render the
  Feynman section only for chapter results that contain it.
- Migration tests cover existing `ai_usage` and `ai_reading_jobs` rows.
