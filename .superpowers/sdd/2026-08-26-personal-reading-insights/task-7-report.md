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

## Final review repair

- The authenticated library metadata projection now obtains visible-book
  ratings with one owner-scoped query. Server cards show only an accessible
  private star rating; review text remains absent, and the SSG catalog remains
  unchanged.
- Insight responses now contain local-day display segments for sessions that
  cross midnight and enumerate every local date in the selected range,
  including days with zero active time.
- Pending heartbeat payloads expire after five minutes and retry only network,
  5xx, or 429 failures. Permanent 4xx failures are removed so they cannot
  block later reading time and receive localized non-retry feedback.
- Visibility loss performs a final keepalive flush. Keyboard activity is
  limited to reader navigation keys outside editable controls, while chapter
  navigation refreshes active-reader state.
- The heartbeat endpoint applies a per-user/client one-minute rate bound before
  cache rendering and SQLite writes. Invalid chapter indexes and overflowing
  valid ISO dates return 400; unavailable content still returns 503.
- Insight day buttons and the selected-day heading use locale date formatting
  rather than raw ISO date strings.

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

Final focused verification:

```text
$ node --test tests/test_reading_sessions.js tests/test_reading_insights.js \
    tests/test_i18n.js tests/test_library_metadata.js
69 passed

$ python3 -m pytest tests/test_state.py::StateStoreTests::test_insights_split_session_at_local_midnight_without_losing_seconds \
    tests/test_server.py::ReadingInsightsAPITests::test_library_metadata_projects_only_the_current_users_rating \
    tests/test_server.py::ReadingInsightsAPITests::test_reading_heartbeat_rate_limits_a_single_client_before_recording_more_work \
    tests/test_server.py::ReadingInsightsAPITests::test_review_heartbeat_and_insights_validate_public_input -vv
4 passed

$ python3 -m pytest tests/test_i18n_coverage.py tests/test_generated_reader_surfaces.py -q
143 passed

$ git diff --check
exit 0
```

## UI-skill application

- Applied `ui-ux-pro-max`: reused the existing notification surface and visual
  language, kept feedback concise, and avoided additional controls or motion.
- Applied `UI/UX Design Review`: retry feedback is text-based, localized,
  keyboard/screen-reader compatible through the existing live notification
  component, and rate-limited to prevent disruptive repeated announcements.
