# Project I18N and Bilingual Interface Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a project-wide `window.EpubBrowserI18n` runtime and migrate every existing browser-facing interface to complete English and Simplified Chinese localization.

**Architecture:** One immutable ES5-compatible browser asset owns locale detection, persistence, dictionaries, formatting, DOM translation, and locale-change events. Generated pages keep readable English fallback text, mark translatable attributes explicitly, and preserve EPUB content language on content containers; dynamic scripts obtain all user-facing copy from the shared runtime. Stable localized manifests and stable server error codes complete the boundary without changing book, shelf, annotation, or progress data.

**Tech Stack:** Python 3.8+, vanilla browser-compatible JavaScript, DOM APIs, `Intl` with deterministic fallbacks, Python `unittest`, Node built-in `node:test`, Starlette, static asset publisher, Service Worker.

**Spec:** `docs/superpowers/specs/2026-08-18-project-i18n-bilingual-interface-design.md`

## Global Constraints

- The only browser global is named exactly `window.EpubBrowserI18n`.
- Supported UI locales are exactly `en` and `zh-CN`; unsupported locales fall back to `en`.
- Locale selection appears only in the library page's `library-breadcrumb` / `library-meta`; book and chapter pages must not add another selector.
- The selector changes the current library page without a reload and persists across pages and sessions.
- Book titles, authors, tags, descriptions, chapter titles, EPUB body content, annotations, usernames, and user-entered CSS remain untranslated user/content data.
- `<html lang>` represents UI locale; book description and chapter content containers retain the EPUB language.
- UI localization covers visible browser copy, dynamic messages, confirmations, placeholders, titles, ARIA labels, dates, numbers, plural forms, page metadata, and PWA metadata.
- CLI help, command-line output, development logs, README, and release documentation stay English.
- Server and `--no-server` static output use the same I18N assets and behavior.
- Existing persisted keys, shelf JSON, annotation records, progress records, hashes, API paths, and stable business identifiers such as `All` and `NoTag` do not change.
- Translation interpolation is text-only; translated strings never become trusted HTML.
- Every task that introduces a `t('namespace.key')` call adds exact `en` and `zh-CN` entries for that key in the same commit; dictionary parity tests must remain green.
- Preserve browser-compatible ES5 syntax in shared assets that currently support Kindle; do not add an npm or Python runtime dependency.

## File Structure

- Create `epub_browser/assets/i18n.js`: UMD-compatible factory, both dictionaries, browser singleton, persistence, formatting, DOM translation, manifest selection, and events.
- Create `epub_browser/assets/manifest.zh-CN.json`: localized PWA metadata; keep `manifest.json` as the English source and compatibility URL.
- Create `tests/test_i18n.js`: runtime behavior and dictionary parity.
- Create `tests/test_i18n_coverage.py`: first-party UI literal guard.
- Modify `epub_browser/asset_publisher.py`: publish English and Chinese manifests at stable URLs and precache them.
- Modify `epub_browser/library.py`: load and initialize I18N, localize the library and shared shelf templates, and render the only locale selector.
- Modify `epub_browser/processor.py`: load I18N on book/chapter pages, separate UI/content language, and localize book, reader, and shared shelf templates.
- Modify `epub_browser/version.py`: localizable shared footer attributes and fallback copy.
- Modify `epub_browser/server.py`: stable error `code` values while retaining compatible English `message` fields.
- Modify first-party UI scripts: `library.js`, `bookshelf.js`, `book.js`, `chapter.js`, `theme.js`, `annotation.js`, `annotation-hub.js`, `version-check.js`, and any visible status in `reading-progress.js`.
- Modify `epub_browser/assets/library.css`: compact breadcrumb locale selector styles.
- Modify existing Python and Node tests alongside the component they cover.

---

### Task 1: Shared I18N Runtime and Dictionary Contract

**Files:**
- Create: `epub_browser/assets/i18n.js`
- Create: `tests/test_i18n.js`

**Interfaces:**
- Consumes: browser-like `root` object with optional `navigator`, `localStorage`, `document`, `CustomEvent`, `Intl`, and timer/event APIs.
- Produces in browsers: `window.EpubBrowserI18n` with `init()`, `t(key, params)`, `getLocale()`, `setLocale(locale)`, `translateDocument(root?)`, `formatDate(value, options?)`, `formatNumber(value, options?)`, and `onLocaleChange(listener)`.
- Produces in Node: `{ createRuntime, dictionaries }` for isolated tests; this Node export is not a browser global.
- `onLocaleChange(listener)` returns an unsubscribe function; `init()` is idempotent; `setLocale()` returns the normalized active locale.

- [ ] **Step 1: Write failing locale, translation, persistence, and parity tests**

```javascript
const test = require('node:test');
const assert = require('node:assert/strict');
const { createRuntime, dictionaries } = require('../epub_browser/assets/i18n.js');

function fakeRoot(language) {
  const values = {};
  return {
    navigator: { languages: [language], language },
    localStorage: {
      getItem: key => Object.prototype.hasOwnProperty.call(values, key) ? values[key] : null,
      setItem: (key, value) => { values[key] = String(value); }
    },
    addEventListener() {}, dispatchEvent() {},
    Intl, console: { warn() {} },
    __values: values
  };
}

test('detects Simplified Chinese regions and falls back unsupported locales to English', () => {
  assert.equal(createRuntime(fakeRoot('zh-SG'), dictionaries).init(), 'zh-CN');
  assert.equal(createRuntime(fakeRoot('fr-FR'), dictionaries).init(), 'en');
});

test('persists an explicit locale and interpolates text parameters', () => {
  const root = fakeRoot('en');
  const i18n = createRuntime(root, dictionaries);
  i18n.init();
  assert.equal(i18n.setLocale('zh-CN'), 'zh-CN');
  assert.equal(root.__values.epub_browser_locale, 'zh-CN');
  assert.equal(i18n.t('common.version', { version: '1.11.1' }), '版本 1.11.1');
});

test('English and Chinese dictionaries have identical non-empty key trees', () => {
  assert.deepEqual(Object.keys(dictionaries.en).sort(), Object.keys(dictionaries['zh-CN']).sort());
  Object.keys(dictionaries.en).forEach(key => {
    assert.notEqual(dictionaries.en[key], '');
    assert.notEqual(dictionaries['zh-CN'][key], '');
  });
});
```

- [ ] **Step 2: Run the runtime tests and verify the missing module failure**

Run: `node --test tests/test_i18n.js`

Expected: FAIL with `Cannot find module '../epub_browser/assets/i18n.js'`.

- [ ] **Step 3: Implement the UMD factory, locale normalization, and idempotent initialization**

```javascript
(function(root, factory) {
  var exported = factory();
  if (typeof module === 'object' && module.exports) module.exports = exported;
  if (root && root.document) root.EpubBrowserI18n = exported.createRuntime(root, exported.dictionaries);
})(typeof window !== 'undefined' ? window : globalThis, function() {
  'use strict';
  var STORAGE_KEY = 'epub_browser_locale';
  var dictionaries = {
    en: { 'common.version': 'Version {version}' },
    'zh-CN': { 'common.version': '版本 {version}' }
  };

  function normalizeLocale(value) {
    value = String(value || '').replace('_', '-').toLowerCase();
    if (value === 'zh' || value.indexOf('zh-cn') === 0 || value.indexOf('zh-sg') === 0) return 'zh-CN';
    return value === 'en' || value.indexOf('en-') === 0 ? 'en' : '';
  }

  function createRuntime(root, messages) {
    var locale = '', initialized = false, listeners = [];
    function init() {
      if (initialized) return locale;
      initialized = true;
      var stored = '';
      try { stored = normalizeLocale(root.localStorage && root.localStorage.getItem(STORAGE_KEY)); } catch (error) {}
      var browser = root.navigator && ((root.navigator.languages || [])[0] || root.navigator.language);
      locale = stored || normalizeLocale(browser) || 'en';
      return locale;
    }
    return {
      init: init,
      t: t,
      getLocale: function() { return init(); },
      setLocale: setLocale,
      translateDocument: translateDocument,
      formatDate: formatDate,
      formatNumber: formatNumber,
      onLocaleChange: onLocaleChange
    };
  }
  return { createRuntime: createRuntime, dictionaries: dictionaries };
});
```

Implement storage fallback in this order: `localStorage`, `window.epubBrowserCache`, Cookie, page memory. Cookie name is `epub_browser_locale`, path is `/`, and no username or SQLite state participates.

- [ ] **Step 4: Implement translation lookup, parameter interpolation, plurals, formatting, and safe fallbacks**

```javascript
function interpolate(template, params) {
  return String(template).replace(/\{([A-Za-z0-9_]+)\}/g, function(match, key) {
    return params && params[key] !== undefined ? String(params[key]) : match;
  });
}

function t(key, params) {
  var selected = messages[locale] && messages[locale][key];
  var fallback = messages.en && messages.en[key];
  if (selected === undefined) selected = fallback;
  if (selected === undefined) { if (root.console) root.console.warn('Missing i18n key:', key); return key; }
  return interpolate(selected, params || {});
}
```

Represent plural values as `{ one: '...', other: '...' }`; use `Intl.PluralRules(locale)` when present, otherwise `count === 1 ? 'one' : 'other'`. Chinese entries may use one string. `formatDate` and `formatNumber` use the active locale with `Intl`, then the deterministic numeric fallbacks from the spec.

- [ ] **Step 5: Implement explicit DOM attribute translation and isolated locale-change listeners**

```javascript
function translateDocument(scope) {
  scope = scope || root.document;
  if (!scope || !scope.querySelectorAll) return;
  var nodes = scope.querySelectorAll('[data-i18n], [data-i18n-placeholder], [data-i18n-title], [data-i18n-aria-label], [data-i18n-content]');
  Array.prototype.forEach.call(nodes, function(node) {
    var params = {};
    try { params = JSON.parse(node.getAttribute('data-i18n-params') || '{}'); } catch (error) {}
    if (node.hasAttribute('data-i18n')) node.textContent = t(node.getAttribute('data-i18n'), params);
    ['placeholder', 'title', 'aria-label', 'content'].forEach(function(attribute) {
      var key = node.getAttribute('data-i18n-' + attribute);
      if (key) node.setAttribute(attribute, t(key, params));
    });
  });
}
```

`setLocale()` updates `<html lang>`, persists the value, translates the document, updates the manifest link, and invokes each listener inside its own `try/catch`. Add tests for English fallback, missing-English key warnings, plural selection, invalid dates, storage exceptions, unsubscribe behavior, and one listener throwing without blocking the next.

- [ ] **Step 6: Run tests and syntax validation**

Run: `node --test tests/test_i18n.js && node --check epub_browser/assets/i18n.js`

Expected: PASS.

- [ ] **Step 7: Commit the runtime**

```bash
git add epub_browser/assets/i18n.js tests/test_i18n.js
git commit -m "feat: add shared browser i18n runtime"
```

### Task 2: Localized PWA Manifests and Static Publication

**Files:**
- Create: `epub_browser/assets/manifest.zh-CN.json`
- Modify: `epub_browser/assets/manifest.json`
- Modify: `epub_browser/asset_publisher.py`
- Modify: `tests/test_asset_publisher.py`
- Modify: `tests/test_static_asset_delivery.py`
- Modify: `tests/test_server.py`

**Interfaces:**
- Consumes: English source `manifest.json`, Chinese source `manifest.zh-CN.json`, and `PublishedAssets` icon/screenshot URLs.
- Produces: stable `/assets/manifest.json` compatibility alias, `/assets/manifest.en.json`, and `/assets/manifest.zh-CN.json`; all contain rewritten immutable icon/screenshot URLs.
- Produces: Service Worker precache entries for all three stable manifest URLs.

- [ ] **Step 1: Add failing publisher and cache-policy tests**

```python
def test_publish_writes_localized_stable_web_manifests(self):
    with tempfile.TemporaryDirectory() as output:
        AssetPublisher("epub_browser/assets", output).publish()
        english = json.loads(Path(output, "assets", "manifest.en.json").read_text(encoding="utf-8"))
        chinese = json.loads(Path(output, "assets", "manifest.zh-CN.json").read_text(encoding="utf-8"))
        self.assertEqual(english["lang"], "en")
        self.assertEqual(chinese["lang"], "zh-CN")
        self.assertEqual(chinese["description"], "私人 EPUB 阅读器与静态站点生成器")
        self.assertRegex(english["icons"][0]["src"], r"^/assets/immutable/icon-192\.[0-9a-f]{12}\.png$")

def test_localized_manifests_are_mutable_revalidated_assets(self):
    for path in ("/assets/manifest.en.json", "/assets/manifest.zh-CN.json"):
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["cache-control"], "no-cache")
```

Extend the test source fixture to write a Chinese source manifest and assert the generated worker contains all localized stable paths.

- [ ] **Step 2: Run the focused tests and verify failure**

Run: `python -m unittest tests.test_asset_publisher tests.test_static_asset_delivery tests.test_server.ServerCacheTests.test_mutable_assets_and_worker_revalidate -v`

Expected: FAIL because localized output manifests do not exist.

- [ ] **Step 3: Add exact Chinese manifest metadata**

```json
{
  "name": "EPUB Browser",
  "short_name": "EPUB Browser",
  "description": "私人 EPUB 阅读器与静态站点生成器",
  "start_url": "/index.html",
  "display": "standalone",
  "background_color": "#f4f0e6",
  "theme_color": "#244548",
  "orientation": "any",
  "lang": "zh-CN",
  "scope": "/",
  "prefer_related_applications": false
}
```

Copy the existing icon, screenshot, and category arrays unchanged, but translate screenshot labels to `EPUB Browser 桌面视图` and `EPUB Browser 移动视图`. Keep the English manifest's product name and update its description/screenshot labels only when needed for consistency.

- [ ] **Step 4: Publish all manifest outputs outside immutable assets**

```python
WEB_MANIFEST_SOURCES = {
    "manifest.json": "manifest.json",
    "manifest.en.json": "manifest.json",
    "manifest.zh-CN.json": "manifest.zh-CN.json",
}

def _write_web_manifests(self, published):
    for output_name, source_name in WEB_MANIFEST_SOURCES.items():
        source = self.source_dir / source_name
        manifest = self._rewrite_asset_urls(json.loads(source.read_text(encoding="utf-8")), published)
        target = self.output_dir / "assets" / output_name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
```

Exclude `sw.js`, `manifest.json`, and `manifest.zh-CN.json` from `_copy_immutable_assets()`. Replace `_write_web_manifest()` with `_write_web_manifests()` and append the three stable manifest paths to `precache_urls`.

- [ ] **Step 5: Update server fixtures and run publication tests**

Run: `python -m unittest tests.test_asset_publisher tests.test_static_asset_delivery tests.test_server -v`

Expected: PASS.

- [ ] **Step 6: Commit localized manifest publication**

```bash
git add epub_browser/assets/manifest.json epub_browser/assets/manifest.zh-CN.json epub_browser/asset_publisher.py tests/test_asset_publisher.py tests/test_static_asset_delivery.py tests/test_server.py
git commit -m "feat: publish localized web app manifests"
```

### Task 3: Generated Page Bootstrap and UI/Content Language Separation

**Files:**
- Modify: `epub_browser/library.py`
- Modify: `epub_browser/processor.py`
- Modify: `epub_browser/assets/i18n.js`
- Modify: `tests/test_i18n.js`
- Modify: `tests/test_generated_reader_surfaces.py`

**Interfaces:**
- Consumes: immutable `i18n.js` URL rewritten by `AssetPublisher` and stable localized manifest paths.
- Produces: synchronous `EpubBrowserI18n.init()` before first-party deferred UI scripts on library, book, and chapter pages.
- Produces: UI language on `<html lang>` and EPUB language on book description/chapter article `lang` attributes.

- [ ] **Step 1: Add failing generated-page bootstrap tests**

```python
def test_all_generated_pages_bootstrap_shared_i18n_before_ui_scripts(self):
    for html in (self._library_html(), self._book_html(), self._chapter_html()):
        self.assertRegex(html, r'/assets/immutable/i18n\.[0-9a-f]{12}\.js')
        self.assertIn('window.EpubBrowserI18n.init()', html)
        self.assertLess(html.index('window.EpubBrowserI18n.init()'), html.index('/assets/immutable/theme.'))
        self.assertIn('<noscript><link rel="manifest" href="/assets/manifest.en.json">', html)

def test_chapter_separates_ui_and_epub_content_languages(self):
    html = self._chapter_html()
    self.assertIn('<html lang="en"', html)
    self.assertRegex(html, r'<article[^>]+id="eb-content"[^>]+lang="en"')
```

Add a book fixture with `processor.lang = "fr"` and assert its description and article use `lang="fr"` while the initial document fallback remains `lang="en"`.

- [ ] **Step 2: Run the generated-page tests and verify failure**

Run: `python -m unittest tests.test_generated_reader_surfaces.GeneratedReaderSurfaceTests.test_all_generated_pages_bootstrap_shared_i18n_before_ui_scripts tests.test_generated_reader_surfaces.GeneratedReaderSurfaceTests.test_chapter_separates_ui_and_epub_content_languages -v`

Expected: FAIL because no page loads `i18n.js` and book/chapter `<html>` currently uses EPUB language.

- [ ] **Step 3: Bootstrap I18N synchronously in all page heads**

```html
<script src="/assets/i18n.js"></script>
<script>window.EpubBrowserI18n.init();</script>
<noscript><link rel="manifest" href="/assets/manifest.en.json"></noscript>
```

Remove the old direct `/assets/manifest.json` link. Keep `i18n.js` before `theme.js`, `library.js`, `book.js`, `chapter.js`, `annotation.js`, and other first-party UI scripts. `init()` must set `document.documentElement.lang`, insert one localized manifest link with id `epubBrowserManifest`, then translate on `DOMContentLoaded`.

- [ ] **Step 4: Separate UI fallback language from EPUB language**

```python
# Generated shell fallback:
'<html lang="en">'

# Book description when present:
f'<div class="book-info-desc" lang="{self.lang}">{self.description}</div>'

# Chapter content:
f'<article class="eb-content" id="eb-content" lang="{self.lang}" ...>'
```

Escape the EPUB language attribute using the existing HTML-safe template conventions; normalize an empty EPUB language to `en` during metadata parsing.

- [ ] **Step 5: Test manifest attachment and page bootstrap**

Extend `tests/test_i18n.js` with a fake document head and assert `init()` inserts `/assets/manifest.zh-CN.json` for Chinese, replaces it after `setLocale('en')`, and never creates a second manifest link.

Run: `node --test tests/test_i18n.js && python -m unittest tests.test_generated_reader_surfaces -v`

Expected: PASS.

- [ ] **Step 6: Commit the generated shell integration**

```bash
git add epub_browser/assets/i18n.js epub_browser/library.py epub_browser/processor.py tests/test_i18n.js tests/test_generated_reader_surfaces.py
git commit -m "feat: bootstrap i18n on generated pages"
```

### Task 4: Stable Server Error Codes

**Files:**
- Modify: `epub_browser/server.py`
- Modify: `tests/test_server.py`

**Interfaces:**
- Consumes: existing Starlette and legacy handler status/message behavior.
- Produces error JSON: `{ "code": "stable_snake_case_code", "message": "compatible English message" }` plus existing fields.
- Exact codes: `not_found`, `username_required`, `invalid_json`, `no_sync_data`, `annotation_not_found`, `invalid_chapter_index`, `batch_requires_post`, `database_unavailable`, `reading_progress_not_found`, and `server_error`.

- [ ] **Step 1: Add failing response-code compatibility tests**

```python
def test_browser_api_errors_include_stable_codes_and_compatible_messages(self):
    cases = [
        (self.client.post("/sync", json={}), 400, "username_required"),
        (self.client.put("/api/reading-progress/book", json={"chapter_index": -1}), 400, "invalid_chapter_index"),
        (self.client.get("/api/annotations/item/missing"), 404, "annotation_not_found"),
    ]
    for response, status, code in cases:
        with self.subTest(code=code):
            self.assertEqual(response.status_code, status)
            self.assertEqual(response.json()["code"], code)
            self.assertIsInstance(response.json()["message"], str)
```

Add a malformed JSON request using raw `content=b'{'` and assert `invalid_json`. Keep success payload assertions unchanged.

- [ ] **Step 2: Run server tests and verify missing-code failure**

Run: `python -m unittest tests.test_server.ServerCacheTests.test_browser_api_errors_include_stable_codes_and_compatible_messages -v`

Expected: FAIL with `KeyError: 'code'`.

- [ ] **Step 3: Add one payload helper and migrate Starlette errors**

```python
def error_payload(code, message):
    return {'code': code, 'message': message}

# Example:
return response(error_payload('invalid_chapter_index', 'Invalid chapter index'), 400)
```

Use the exact code list above for every non-2xx response that can be shown by the browser. Preserve all existing status codes and English `message` values. Do not attach `code` to successful create/update/delete messages.

- [ ] **Step 4: Migrate legacy handler errors and stop exposing exception text**

```python
self.send_json_response(500, error_payload('server_error', 'Internal server error'))
```

Continue logging the original exception through `log_message`, but never include `str(e)` in a browser 500 body. Apply the same exact codes to equivalent Starlette and legacy routes.

- [ ] **Step 5: Run complete server tests**

Run: `python -m unittest tests.test_server -v`

Expected: PASS with unchanged success responses and new stable error codes.

- [ ] **Step 6: Commit the API contract**

```bash
git add epub_browser/server.py tests/test_server.py
git commit -m "feat: add stable browser api error codes"
```

### Task 5: Library Breadcrumb Selector and Shared Chrome

**Files:**
- Modify: `epub_browser/assets/i18n.js`
- Modify: `epub_browser/library.py`
- Modify: `epub_browser/assets/library.js`
- Modify: `epub_browser/assets/library.css`
- Modify: `epub_browser/assets/theme.js`
- Modify: `epub_browser/assets/version-check.js`
- Modify: `epub_browser/version.py`
- Modify: `tests/test_i18n.js`
- Modify: `tests/test_version_check.js`
- Modify: `tests/test_generated_reader_surfaces.py`

**Interfaces:**
- Consumes: `EpubBrowserI18n` and stable library data attributes.
- Produces: exactly one `<select id="localeSelect">` in library `library-meta`, values `zh-CN` and `en`, and no selector on book/chapter pages.
- Produces dictionary namespaces: `common.*`, `theme.*`, `library.*`, `footer.*`, `version.*`, and generic `errors.*` mappings.

- [ ] **Step 1: Add failing selector, shared-copy, and live-switch tests**

```python
def test_locale_selector_exists_only_in_library_breadcrumb(self):
    library = self._library_html()
    self.assertEqual(library.count('id="localeSelect"'), 1)
    breadcrumb = library[library.index('class="breadcrumb library-breadcrumb"'):library.index('</nav>')]
    self.assertIn('value="zh-CN"', breadcrumb)
    self.assertIn('value="en"', breadcrumb)
    self.assertNotIn('id="localeSelect"', self._book_html())
    self.assertNotIn('id="localeSelect"', self._chapter_html())
```

In the same generated-page test, assert the emitted library bootstrap assigns `localeSelect.value` from `getLocale()`, binds one `change` listener, and passes `localeSelect.value` to `setLocale()`. Task 1 already behavior-tests persistence, document translation, and locale-change callbacks in isolation.

- [ ] **Step 2: Run focused tests and verify failure**

Run: `node --test tests/test_i18n.js tests/test_version_check.js && python -m unittest tests.test_generated_reader_surfaces.GeneratedReaderSurfaceTests.test_locale_selector_exists_only_in_library_breadcrumb -v`

Expected: FAIL because `localeSelect` and shared localized copy do not exist.

- [ ] **Step 3: Add the compact breadcrumb selector**

```html
<label class="library-language" for="localeSelect">
  <i class="fas fa-globe" aria-hidden="true"></i>
  <span class="sr-only" data-i18n="common.language">Language</span>
  <select id="localeSelect" data-i18n-aria-label="common.language">
    <option value="zh-CN">中文</option>
    <option value="en">English</option>
  </select>
</label>
```

Place it in `library-meta` after Annotations and before Login. Style it from existing breadcrumb colors/borders, preserve a 44px minimum touch target, and let existing narrow-screen `library-meta` wrapping handle overflow. Do not add it to `.top-controls`.

- [ ] **Step 4: Bind the selector and migrate library page copy**

```javascript
var i18n = window.EpubBrowserI18n;
var localeSelect = document.getElementById('localeSelect');
localeSelect.value = i18n.getLocale();
localeSelect.addEventListener('change', function() { i18n.setLocale(localeSelect.value); });
```

Mark Python template text/placeholder/ARIA attributes with `data-i18n-*`. Replace `library.js` and the library inline login/install strings with `i18n.t()` calls. Cover Library, book/tag counts, Annotations, Login, Theme, search placeholder, All, No tag, Top, Shelf, install states, username prompt/saved/cleared, loading, and empty/error states. Leave tag values and book metadata untouched.

- [ ] **Step 5: Migrate shared theme, footer, and update copy**

```javascript
var themes = [
  { id: 'light', nameKey: 'theme.light', icon: 'fa-sun' },
  { id: 'dark', nameKey: 'theme.dark', icon: 'fa-moon' }
];
item.appendChild(document.createTextNode(i18n.t(theme.nameKey)));
```

Use translation keys for footer product copy, `aria-label="Version {version}"`, and `Update available: v{version}`. Keep repository name, year, and version as parameters. Update `tests/test_version_check.js` to inject an I18N stub and assert localized link text.

- [ ] **Step 6: Run library/shared chrome tests**

Run: `node --test tests/test_i18n.js tests/test_version_check.js && node --check epub_browser/assets/library.js && node --check epub_browser/assets/theme.js && python -m unittest tests.test_generated_reader_surfaces -v`

Expected: PASS.

- [ ] **Step 7: Commit the library and shared chrome**

```bash
git add epub_browser/assets/i18n.js epub_browser/library.py epub_browser/assets/library.js epub_browser/assets/library.css epub_browser/assets/theme.js epub_browser/assets/version-check.js epub_browser/version.py tests/test_i18n.js tests/test_version_check.js tests/test_generated_reader_surfaces.py
git commit -m "feat: localize library and shared browser chrome"
```

### Task 6: Bookshelf and Group Management

**Files:**
- Modify: `epub_browser/assets/i18n.js`
- Modify: `epub_browser/library.py`
- Modify: `epub_browser/processor.py`
- Modify: `epub_browser/assets/bookshelf.js`
- Modify: `tests/test_generated_reader_surfaces.py`

**Interfaces:**
- Consumes: stable `data-tag="All"`, shelf JSON, group paths, username, and `EpubBrowserI18n`.
- Produces dictionary namespace `bookshelf.*` and localized shelf/group modals on every page where they exist.
- Locale changes on the library page rerender open shelf/group statistics and empty states without mutating shelf data.

- [ ] **Step 1: Add failing bookshelf coverage tests**

```python
def test_bookshelf_templates_localize_labels_without_translating_business_values(self):
    for html in (self._library_html(), self._book_html(), self._chapter_html()):
        self.assertIn('data-i18n="bookshelf.addGroup"', html)
        self.assertIn('data-i18n="bookshelf.sync"', html)
        self.assertRegex(html, r'data-tag=(?:["\'])All(?:["\'])')

def test_bookshelf_script_routes_user_messages_through_i18n(self):
    script = Path('epub_browser/assets/bookshelf.js').read_text(encoding='utf-8')
    self.assertNotRegex(script, r"showNotification\(\s*['\"]")
    self.assertNotRegex(script, r"confirm\(\s*['\"]")
    self.assertIn("i18n.t('bookshelf.currentStats'", script)
```

- [ ] **Step 2: Run focused tests and verify hard-coded-copy failure**

Run: `python -m unittest tests.test_generated_reader_surfaces.GeneratedReaderSurfaceTests.test_bookshelf_templates_localize_labels_without_translating_business_values tests.test_generated_reader_surfaces.GeneratedReaderSurfaceTests.test_bookshelf_script_routes_user_messages_through_i18n -v`

Expected: FAIL on missing data attributes and literal notification/confirmation strings.

- [ ] **Step 3: Migrate the duplicated shelf/group templates**

Add `bookshelf.*` bindings for Bookshelf, Add Group, Sync, Export, Import, All, Rename, Delete Group, Group, close/home labels, loading, footer labels, and input prompts in both Python generators. Keep group names, tag names, book titles, and path segments as unmodified text nodes.

```html
<button class="bookshelf-action-btn" id="addShelfGroupBtn">
  <i class="fas fa-folder-plus" aria-hidden="true"></i>
  <span data-i18n="bookshelf.addGroup">Add Group</span>
</button>
```

- [ ] **Step 4: Migrate bookshelf rendering, statistics, confirmations, and sync states**

```javascript
function tr(key, params) { return window.EpubBrowserI18n.t('bookshelf.' + key, params); }
bookshelfStats.textContent = tr('currentStats', {
  books: bookCount, groups: groupCount, totalBooks: total.books, totalGroups: total.groups
});
if (confirm(tr('confirmDeleteGroup', { name: targetGroup.name }))) { /* existing delete path */ }
```

Cover create/rename/delete prompts, nested-group warning, empty shelf/group states, current/total statistics, import parsing/format results, sync progress and every status branch, and unknown error fallback. Map API `code` values from Task 4 to localized copy; log raw `message` but do not display it as the primary text.

- [ ] **Step 5: Rerender open shelf UI on locale changes**

```javascript
window.EpubBrowserI18n.onLocaleChange(function() {
  if (bookshelfModal && bookshelfModal.classList.contains('active')) renderBookshelf(currentTag);
  if (groupModal && groupModal.classList.contains('active') && currentGroupId) {
    var shelfData = getBookshelf();
    var group = shelfData.groups[currentGroupId];
    for (var i = 0; i < currentGroupPath.length; i++) group = group.groups[currentGroupPath[i]];
    renderGroupContent(group, currentTag);
  }
});
```

Use the module's actual open/visible state conventions instead of changing modal behavior. Reapply the active stable tag after rerender.

- [ ] **Step 6: Run bookshelf and generated-page regression tests**

Run: `node --check epub_browser/assets/bookshelf.js && python -m unittest tests.test_generated_reader_surfaces -v`

Expected: PASS.

- [ ] **Step 7: Commit bookshelf localization**

```bash
git add epub_browser/assets/i18n.js epub_browser/library.py epub_browser/processor.py epub_browser/assets/bookshelf.js tests/test_generated_reader_surfaces.py
git commit -m "feat: localize bookshelf management"
```

### Task 7: Book Home and Reading Progress UI

**Files:**
- Modify: `epub_browser/assets/i18n.js`
- Modify: `epub_browser/processor.py`
- Modify: `epub_browser/assets/book.js`
- Modify: `epub_browser/assets/reading-progress.js` if a visible status remains
- Modify: `tests/test_generated_reader_surfaces.py`
- Modify: `tests/test_reading_progress.js`

**Interfaces:**
- Consumes: original book metadata, TOC titles, reading progress, username, shelf state, API error codes, and I18N runtime.
- Produces dictionary namespace `book.*`; metadata/TOC remains original content.

- [ ] **Step 1: Add failing book-page and dynamic-copy tests**

```python
def test_book_page_localizes_shell_but_marks_metadata_as_content(self):
    with tempfile.TemporaryDirectory() as directory:
        processor = EPUBProcessor('book.epub', directory)
        processor.book_title = 'A Book'
        processor.lang = 'fr'
        processor.description = '<p>Texte original</p>'
        Path(processor.web_dir).mkdir(parents=True)
        processor.create_index_page()
        html = Path(processor.web_dir, 'index.html').read_text(encoding='utf-8')
    self.assertIn('data-i18n="book.startReading"', html)
    self.assertIn('data-i18n="book.tableOfContents"', html)
    self.assertRegex(html, r'class="book-info-desc"[^>]+lang="fr"')
    self.assertIn('A Book', html)
    self.assertIn('Texte original', html)

def test_book_script_has_no_literal_user_notifications_or_confirmations(self):
    script = Path('epub_browser/assets/book.js').read_text(encoding='utf-8')
    self.assertNotRegex(script, r"showNotification\(\s*['\"]")
    self.assertNotRegex(script, r"confirm\(\s*['\"]")
```

- [ ] **Step 2: Run focused tests and verify failure**

Run: `python -m unittest tests.test_generated_reader_surfaces.GeneratedReaderSurfaceTests.test_book_page_localizes_shell_but_marks_metadata_as_content tests.test_generated_reader_surfaces.GeneratedReaderSurfaceTests.test_book_script_has_no_literal_user_notifications_or_confirmations -v`

Expected: FAIL on hard-coded book shell strings.

- [ ] **Step 3: Migrate book template copy and content language boundaries**

Bind Library, Unknown author, Start/Continue reading, more actions, clear progress, Annotations, Add/Remove Shelf, Table of contents, total chapter count, Top, Shelf, Home, and control ARIA labels to `book.*` or `common.*`. Put EPUB `lang` on description and other prose metadata containers; never place `data-i18n` on metadata or TOC titles.

```html
<span id="continueReadingBtnText" data-i18n="book.startReading">Start reading</span>
<h2 data-i18n="book.tableOfContents">Table of contents</h2>
```

- [ ] **Step 4: Migrate dynamic reading progress and shelf state copy**

```javascript
var i18n = window.EpubBrowserI18n;
continueButtonText.textContent = i18n.t(resumeChapter ? 'book.continueReading' : 'book.startReading');
syncTag.textContent = i18n.t('book.cloudSyncUser', { username: username });
```

Cover clear-progress confirmation/success/failure, synced progress badge, start/continue state, add/remove shelf labels and results, group chooser headings/actions, and all empty/error states. Usernames and group/book names are plain-text parameters.

- [ ] **Step 5: Update exact-English assertions and progress tests**

Replace tests that require English literals inside `book.js` with assertions for translation keys and behavior. Keep `reading-progress.js` request payload tests unchanged; inject a translation stub only if that module displays a visible status.

Run: `node --test tests/test_reading_progress.js && node --check epub_browser/assets/book.js && python -m unittest tests.test_generated_reader_surfaces -v`

Expected: PASS.

- [ ] **Step 6: Commit the book surface**

```bash
git add epub_browser/assets/i18n.js epub_browser/processor.py epub_browser/assets/book.js epub_browser/assets/reading-progress.js tests/test_generated_reader_surfaces.py tests/test_reading_progress.js
git commit -m "feat: localize book home and progress ui"
```

### Task 8: Reader Template, Settings, and Accessible Labels

**Files:**
- Modify: `epub_browser/assets/i18n.js`
- Modify: `epub_browser/processor.py`
- Modify: `tests/test_generated_reader_surfaces.py`

**Interfaces:**
- Consumes: chapter title/body, EPUB language, navigation links, and I18N attribute conventions.
- Produces dictionary namespaces `reader.*` and `settings.*` for all static desktop/mobile reader chrome.

- [ ] **Step 1: Add failing reader-template localization tests**

```python
def test_reader_template_marks_static_ui_and_preserves_chapter_content(self):
    html = self._chapter_html()
    for key in ('reader.tableOfContents', 'reader.previous', 'reader.next',
                'settings.appearance', 'settings.readingMode', 'settings.customStyles'):
        self.assertIn('data-i18n="' + key + '"', html)
    article = html[html.index('<article'):html.index('</article>')]
    self.assertIn('<p>Text</p>', article)
    self.assertNotIn('data-i18n', article)

def test_reader_mobile_controls_use_translatable_accessible_labels(self):
    html = self._chapter_html()
    self.assertIn('data-i18n="reader.theme"', html)
    self.assertIn('data-i18n-aria-label="reader.openBookHome"', html)
```

- [ ] **Step 2: Run focused tests and verify failure**

Run: `python -m unittest tests.test_generated_reader_surfaces.GeneratedReaderSurfaceTests.test_reader_template_marks_static_ui_and_preserves_chapter_content tests.test_generated_reader_surfaces.GeneratedReaderSurfaceTests.test_reader_mobile_controls_use_translatable_accessible_labels -v`

Expected: FAIL because reader controls have no I18N attributes.

- [ ] **Step 3: Migrate navigation, TOC, progress, and desktop/mobile controls**

Apply keys to Library, book home, chapter breadcrumb shell, TOC, previous/next, page controls, current/total page labels, loading overlay, Top, Settings, Shelf, Home, Book, Theme, Turning/Scrolling, close buttons, and all `title`/`aria-label` attributes. Keep chapter/book titles and page numbers as content/parameters.

```html
<span class="control-name" data-i18n="common.settings">Settings</span>
<button id="bookHomeClose" data-i18n-aria-label="reader.closeBookHome" aria-label="Close book home">...</button>
```

- [ ] **Step 4: Migrate the settings modal**

Bind Appearance, Reading, font family, font size, reading mode, progress-bar toggle, continuous scroll, explanatory tip, Custom styles, Optional, CSS description/placeholder, Save, Save as default, Reset, Load default, Preview, and the default-style tip. Preserve the literal CSS example inside the translated placeholder in both languages.

```html
<textarea id="customCssInput"
  data-i18n-placeholder="settings.customCssPlaceholder"
  placeholder="Please input your CSS code..."></textarea>
```

- [ ] **Step 5: Run generated reader tests**

Run: `python -m unittest tests.test_generated_reader_surfaces -v && python -m compileall -q epub_browser`

Expected: PASS.

- [ ] **Step 6: Commit static reader localization**

```bash
git add epub_browser/assets/i18n.js epub_browser/processor.py tests/test_generated_reader_surfaces.py
git commit -m "feat: localize reader templates and settings"
```

### Task 9: Reader Dynamic States and Continuous Navigation

**Files:**
- Modify: `epub_browser/assets/i18n.js`
- Modify: `epub_browser/assets/chapter.js`
- Modify: `tests/test_generated_reader_surfaces.py`
- Modify: `tests/test_continuous_buffer.js`
- Modify: `tests/test_chapter_window.js`

**Interfaces:**
- Consumes: `reader.*` / `settings.*` keys, current page/chapter numbers, chapter titles, progress percentages, and unchanged reader navigation modules.
- Produces: no literal user-facing English in `chapter.js`; content titles remain untouched parameters.

- [ ] **Step 1: Add failing dynamic reader-copy guard tests**

```python
def test_chapter_script_routes_notifications_and_confirmations_through_i18n(self):
    script = Path('epub_browser/assets/chapter.js').read_text(encoding='utf-8')
    self.assertNotRegex(script, r"showNotification\(\s*['\"]")
    self.assertNotRegex(script, r"confirm\(\s*['\"]")
    self.assertIn("i18n.t('reader.loadingNextChapter'", script)
    self.assertIn("i18n.t('settings.saved'", script)
```

- [ ] **Step 2: Run the guard and verify failure**

Run: `python -m unittest tests.test_generated_reader_surfaces.GeneratedReaderSurfaceTests.test_chapter_script_routes_notifications_and_confirmations_through_i18n -v`

Expected: FAIL on existing literal notifications and confirmations.

- [ ] **Step 3: Migrate paging, navigation, and progress messages**

```javascript
var i18n = window.EpubBrowserI18n;
showNotification(i18n.t('reader.progressLoadedPage', { page: pi + 1 }), 'info');
showNotification(i18n.t('reader.progressLoadedPercent', { percent: pct }), 'info');
```

Cover Scrolling/Turning labels, mode enabled/exit confirmation, page ranges, valid-number warning, first/last chapter, previous/next boundary, page-only actions, progress loaded, and annotation deep-link failures.

- [ ] **Step 4: Migrate pure mode and settings feedback**

Use `settings.*` keys for pure mode on/off, reloaded, click-page state, saved/default saved/no default/load/reset/preview states, and every confirmation. Preserve user CSS and numeric parameters as plain text.

- [ ] **Step 5: Migrate TOC and continuous-scroll states**

```javascript
loader.innerHTML = '<span class="chapter-loading-label"></span><span class="loading-dot"></span><span class="loading-dot"></span><span class="loading-dot"></span>';
loader.querySelector('.chapter-loading-label').textContent = i18n.t('reader.loadingNextChapter');
separator.innerHTML = '<div class="chapter-sep-title"></div><div class="chapter-sep-index"></div>';
separator.querySelector('.chapter-sep-title').textContent = chapterTitle || i18n.t('reader.chapterNumber', { number: nextIdx + 1 });
separator.querySelector('.chapter-sep-index').textContent = i18n.t('reader.chapterNumber', { number: nextIdx + 1 });
```

Cover TOC load failure/no title, loading next/previous chapter, generated chapter fallback, continuous-scroll prerequisites, enable/disable reload notices, and tooltip copy. Do not inject chapter titles with `innerHTML`.

- [ ] **Step 6: Run reader JavaScript and integration tests**

Run: `node --check epub_browser/assets/chapter.js && node --test tests/test_continuous_buffer.js tests/test_chapter_window.js && python -m unittest tests.test_generated_reader_surfaces -v`

Expected: PASS with navigation behavior unchanged.

- [ ] **Step 7: Commit dynamic reader localization**

```bash
git add epub_browser/assets/i18n.js epub_browser/assets/chapter.js tests/test_generated_reader_surfaces.py tests/test_continuous_buffer.js tests/test_chapter_window.js
git commit -m "feat: localize reader dynamic states"
```

### Task 10: Annotation Editor, Storage, and Migration UI

**Files:**
- Modify: `epub_browser/assets/i18n.js`
- Modify: `epub_browser/assets/annotation.js`
- Modify: `tests/test_generated_reader_surfaces.py`

**Interfaces:**
- Consumes: annotation text/note/color/time, storage availability, username, API codes, and `EpubBrowserI18n`.
- Produces dictionary namespace `annotations.*`; annotation/user content is always inserted as text or escaped with the existing helper.

- [ ] **Step 1: Add failing annotation localization guards**

```python
def test_annotation_editor_routes_user_copy_through_i18n(self):
    script = Path('epub_browser/assets/annotation.js').read_text(encoding='utf-8')
    self.assertNotRegex(script, r"Utils\.showNotification\(\s*['\"]")
    self.assertNotRegex(script, r"confirm\(\s*['\"]")
    self.assertIn("i18n.t('annotations.noteOptional'", script)
    self.assertIn("i18n.t('annotations.storageLocationChanged'", script)
```

- [ ] **Step 2: Run the guard and verify failure**

Run: `python -m unittest tests.test_generated_reader_surfaces.GeneratedReaderSurfaceTests.test_annotation_editor_routes_user_copy_through_i18n -v`

Expected: FAIL on hard-coded annotation UI copy.

- [ ] **Step 3: Migrate compact/detail annotation dialogs**

Localize Note optional, Add description, Created, Updated, Add, Save, Cancel, Copy, Delete, color actions, annotation-not-found, copied/unable-to-copy, load/add/update/delete failures, and delete confirmation. Keep selected text and notes escaped as today.

```javascript
function tr(key, params) { return window.EpubBrowserI18n.t('annotations.' + key, params); }
textarea.setAttribute('placeholder', tr('noteOptional'));
if (confirm(tr('confirmDelete'))) { self.deleteAnnotation(annotation.id); }
```

- [ ] **Step 4: Migrate settings and storage availability states**

Localize the Annotation settings tab, enabled toggle, local/cloud storage labels, cloud-unavailable warning, username/shared-mode prompt, connection checking/connected/disconnected states, and per-user/shared explanations. Usernames remain parameters.

- [ ] **Step 5: Migrate colors, storage migration, and export states**

Localize add/delete color, hex validation labels, migration dialog/buttons/progress/counts, storage-changed result, export counts, and export failures. Use I18N number/plural formatting for annotation counts.

- [ ] **Step 6: Run annotation regressions and syntax validation**

Run: `node --check epub_browser/assets/annotation.js && python -m unittest tests.test_generated_reader_surfaces -v`

Expected: PASS, including existing highlight restoration and silent-success behavior tests.

- [ ] **Step 7: Commit annotation editor localization**

```bash
git add epub_browser/assets/i18n.js epub_browser/assets/annotation.js tests/test_generated_reader_surfaces.py
git commit -m "feat: localize annotation workflows"
```

### Task 11: Annotation Center and Locale-Aware Dates

**Files:**
- Modify: `epub_browser/assets/i18n.js`
- Modify: `epub_browser/assets/annotation-hub.js`
- Modify: `tests/test_annotation_hub.js`
- Modify: `tests/test_generated_reader_surfaces.py`

**Interfaces:**
- Consumes: `annotations.*`, active locale formatter, original annotation/book/chapter content, and AnnotationStorage.
- Produces: locale-aware annotation-center dates/counts and live rerender after a library-page locale change.

- [ ] **Step 1: Add failing localized helper tests**

```javascript
test('uses shared i18n for chapter fallback, counts, and timestamps', () => {
  const original = global.EpubBrowserI18n;
  global.EpubBrowserI18n = {
    t: (key, params) => key === 'annotations.chapterNumber' ? `章节 ${params.number}` : `${params.count} 条标注`,
    formatDate: () => '2026/08/18 09:02:03',
    onLocaleChange: () => () => {}
  };
  assert.equal(Hub.groupByChapter([{ chapter_index: 1 }], [])[0].title, '章节 2');
  assert.equal(Hub.formatTimestamp('2026-08-18T01:02:03Z'), '2026/08/18 09:02:03');
  global.EpubBrowserI18n = original;
});
```

Add a generated-surface guard that `annotation-hub.js` contains no literal modal state headings or error paragraphs.

- [ ] **Step 2: Run hub tests and verify failure**

Run: `node --test tests/test_annotation_hub.js && python -m unittest tests.test_generated_reader_surfaces.GeneratedReaderSurfaceTests.test_annotation_hub_routes_state_copy_through_i18n -v`

Expected: FAIL because helpers currently construct English copy and numeric timestamps directly.

- [ ] **Step 3: Route helper output and modal chrome through I18N**

```javascript
function i18n() { return root.EpubBrowserI18n; }
function tr(key, params) { return i18n().t('annotations.' + key, params); }
function formatTimestamp(time) { return time ? i18n().formatDate(time, { dateStyle: 'short', timeStyle: 'medium' }) : ''; }
```

Localize All annotated books, Annotations, close/back ARIA labels, loading, empty collection/book states, retry, load failure, annotation counts, byline punctuation, and chapter-number fallback. Book titles, authors, chapter titles, annotation text, and notes remain original content.

- [ ] **Step 4: Rerender the open center on locale changes**

Store the last resolved TOC as `modalState.data.toc` before rendering a book. Add `translateChrome()` and `renderCurrentView()` with these exact responsibilities, then subscribe once during bind. When the modal is open, rerender from `modalState.data`; retain current book scope, opener, scroll lock, focus target, and load version. When closed, update only static modal chrome.

```javascript
function translateChrome() {
  if (!modalState.modal) return;
  modalState.back.querySelector('span').textContent = tr('allAnnotatedBooks');
  modalState.modal.querySelector('.annotation-hub-header-label').textContent = tr('title');
  modalState.closeButton.setAttribute('aria-label', tr('close'));
}

function renderCurrentView() {
  if (!modalState.data) return;
  if (!modalState.bookHash) {
    renderBookCards(aggregateBooks(modalState.data.annotations, modalState.data.metadata));
    return;
  }
  renderBookAnnotations(
    modalState.bookHash,
    modalState.data.annotations.filter(function(annotation) { return annotation.book_hash === modalState.bookHash; }),
    modalState.data.metadata,
    modalState.data.toc || []
  );
}

i18n().onLocaleChange(function() {
  if (!modalState.modal) return;
  translateChrome();
  if (!modalState.modal.hidden && modalState.data) renderCurrentView();
});
```

- [ ] **Step 5: Run annotation center and generated-surface tests**

Run: `node --test tests/test_annotation_hub.js && node --check epub_browser/assets/annotation-hub.js && python -m unittest tests.test_generated_reader_surfaces -v`

Expected: PASS.

- [ ] **Step 6: Commit annotation center localization**

```bash
git add epub_browser/assets/i18n.js epub_browser/assets/annotation-hub.js tests/test_annotation_hub.js tests/test_generated_reader_surfaces.py
git commit -m "feat: localize annotation center"
```

### Task 12: Hard-Coded UI Guard and Full Verification

**Files:**
- Create: `tests/test_i18n_coverage.py`
- Modify when reported by the guard: `epub_browser/library.py`
- Modify when reported by the guard: `epub_browser/processor.py`
- Modify when reported by the guard: `epub_browser/version.py`
- Modify when reported by the guard: `epub_browser/assets/library.js`
- Modify when reported by the guard: `epub_browser/assets/bookshelf.js`
- Modify when reported by the guard: `epub_browser/assets/book.js`
- Modify when reported by the guard: `epub_browser/assets/chapter.js`
- Modify when reported by the guard: `epub_browser/assets/theme.js`
- Modify when reported by the guard: `epub_browser/assets/annotation.js`
- Modify when reported by the guard: `epub_browser/assets/annotation-hub.js`
- Modify when reported by the guard: `epub_browser/assets/reading-progress.js`
- Modify when reported by the guard: `epub_browser/assets/version-check.js`
- Modify: `tests/test_generated_reader_surfaces.py` only to replace obsolete exact-English implementation assertions with locale-key or behavior assertions.

**Interfaces:**
- Consumes: completed dictionaries and all first-party templates/scripts.
- Produces: a focused guard preventing new literal English in notification/confirmation/prompt/placeholder/ARIA/visible-text sinks.

- [ ] **Step 1: Write the hard-coded UI sink guard**

```python
import re
import unittest
from pathlib import Path

FIRST_PARTY = [
    Path('epub_browser/library.py'), Path('epub_browser/processor.py'), Path('epub_browser/version.py'),
    *[Path('epub_browser/assets', name) for name in (
        'library.js', 'bookshelf.js', 'book.js', 'chapter.js', 'theme.js',
        'annotation.js', 'annotation-hub.js', 'reading-progress.js', 'version-check.js'
    )]
]
FORBIDDEN = [
    re.compile(r"(?:showNotification|confirm|alert|prompt)\(\s*['\"][A-Za-z]"),
    re.compile(r"\.(?:textContent|placeholder|title)\s*=\s*['\"][A-Za-z]"),
    re.compile(r"(?:placeholder|aria-label|title)=['\"][A-Za-z][^'{]*['\"]"),
]

class I18nCoverageTests(unittest.TestCase):
    def test_first_party_ui_sinks_do_not_embed_english_copy(self):
        failures = []
        for path in FIRST_PARTY:
            for number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
                if 'i18n-allow-literal' in line:
                    continue
                if any(pattern.search(line) for pattern in FORBIDDEN):
                    failures.append(f'{path}:{number}: {line.strip()}')
        self.assertEqual(failures, [], '\n' + '\n'.join(failures))
```

Only use `i18n-allow-literal` for product names, URL/protocol values, CSS/HTML syntax, developer logs, and stable data identifiers. The comment must include one of these reasons on the same line.

- [ ] **Step 2: Run the guard and inspect every reported first-party sink**

Run: `python -m unittest tests.test_i18n_coverage -v`

Expected: FAIL if any migrated component still embeds user-facing English; every failure reports exact file and line.

- [ ] **Step 3: Resolve each sink with one of three explicit transformations**

```javascript
// User message:
showNotification(i18n.t('errors.network'), 'error');

// Dynamic text node:
node.textContent = i18n.t('reader.loadingNextChapter');

// Stable non-UI value with documented exception:
var filterId = 'All'; // i18n-allow-literal: stable data identifier
```

For Python fallback HTML, retain readable English only when the element also has the matching `data-i18n-*` attribute; extend the guard to recognize that same-tag binding instead of blanket-allowing the file.

- [ ] **Step 4: Run dictionary parity, syntax, generated-page, server, and module suites**

Run:

```bash
node --test tests/test_i18n.js tests/test_version_check.js tests/test_reading_progress.js tests/test_annotation_hub.js tests/test_continuous_buffer.js tests/test_chapter_window.js tests/test_viewport_anchor.js
node --check epub_browser/assets/i18n.js
node --check epub_browser/assets/library.js
node --check epub_browser/assets/bookshelf.js
node --check epub_browser/assets/book.js
node --check epub_browser/assets/chapter.js
node --check epub_browser/assets/theme.js
node --check epub_browser/assets/annotation.js
node --check epub_browser/assets/annotation-hub.js
python -m unittest discover -s tests -v
python -m compileall -q epub_browser
git diff --check
```

Expected: every command exits 0.

- [ ] **Step 5: Hand off browser acceptance to the user**

Do not run E2E tests or agent-operated browser smoke tests. The user will manually accept the server and static deployment paths, including locale selection and persistence, original EPUB content language, localized manifests, bookshelf, annotations, reader settings, navigation modes, and storage fallback. Automated coverage remains limited to the unit, integration, generated-page, syntax, compilation, and diff checks in Step 4.

- [ ] **Step 6: Commit the guard and final compatibility fixes**

```bash
git add tests/test_i18n_coverage.py tests/test_generated_reader_surfaces.py \
  epub_browser/library.py epub_browser/processor.py epub_browser/version.py \
  epub_browser/assets/i18n.js epub_browser/assets/library.js epub_browser/assets/bookshelf.js \
  epub_browser/assets/book.js epub_browser/assets/chapter.js epub_browser/assets/theme.js \
  epub_browser/assets/annotation.js epub_browser/assets/annotation-hub.js \
  epub_browser/assets/reading-progress.js epub_browser/assets/version-check.js
git commit -m "test: enforce complete browser ui localization"
```

## Completion Gate

Before declaring the I18N sub-project complete, verify all twelve task commits are present and the commands in Task 12 Step 4 pass from a clean checkout. Hand browser acceptance to the user; the selector-placement requirement is covered by generated-page tests. Then proceed to the separately approved design cycle for the AI server foundation; do not begin AI implementation under this plan.
