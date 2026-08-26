# Task 7 report: localization, boundaries, and release verification

## Implemented

- Added complete five-locale copy for private reviews, reading insights,
  session fields, duration fallbacks, and deferred reading-session persistence
  feedback.
- Added the three first-party feature clients to literal-sink coverage and
  taught the coverage checker how the reading-insights client's scoped
  translation helper receives its key.
- Added an SSG integration assertion that rejects all five authenticated-only
  feature assets and all review/session/insight routes from the static output.
- Added a Server restart integration test that converts once, verifies private
  review/session APIs and the insights page, restarts without conversion, and
  proves the EPUB-derived `content/` file set and bytes never change.
- Documented that private ratings, reviews, and detailed reading-session
  history are authenticated SQLite data and never appear in SSG output.
- Repaired the two approved baseline i18n sink false positives by reading the
  existing `data-i18n` binding through `dataset`.

## Review repair

- Reading-session heartbeats now announce a localized queued-persistence
  warning once per unsaved streak and a localized error after three consecutive
  failed sends. Successful persistence clears the streak, so routine heartbeats
  and automatic retries do not spam notifications. The notifications use the
  existing shared UI, which provides polite or assertive live semantics.
- The reading-insights fallback formatter now obtains second/minute/hour unit
  labels from the active locale when `Intl.DurationFormat` is unavailable.
  The non-English regression test covers this browser path.

## Verification

```text
$ python3 -m unittest tests.test_state tests.test_server tests.test_ssg \
    tests.test_mode_integration tests.test_asset_publisher \
    tests.test_generated_reader_surfaces tests.test_i18n_coverage -q
passed

$ node --test tests/test_reading_sessions.js tests/test_book_reviews.js \
    tests/test_reading_insights.js tests/test_i18n.js \
    tests/test_reading_progress.js tests/test_book_bookshelf.js
passed

$ python3 -m unittest tests.test_i18n_coverage tests.test_generated_reader_surfaces -q
Ran 143 tests ... OK

$ git diff --check
exit 0
```

## UI-skill application

- Applied `ui-ux-pro-max`: reused the existing notification surface and visual
  language, kept feedback concise, and avoided additional controls or motion.
- Applied `UI/UX Design Review`: retry feedback is text-based, localized,
  keyboard/screen-reader compatible through the existing live notification
  component, and rate-limited to prevent disruptive repeated announcements.
