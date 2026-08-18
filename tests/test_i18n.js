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

test('provides the library and shared-chrome copy used by the first bilingual surface', () => {
  [
    'common.language', 'common.version', 'theme.light', 'theme.dark',
    'library.title', 'library.bookCount', 'library.searchPlaceholder',
    'library.usernamePrompt', 'library.install', 'footer.product',
    'footer.poweredBy', 'version.updateAvailable', 'errors.generic'
  ].forEach(key => {
    assert.ok(dictionaries.en[key]);
    assert.ok(dictionaries['zh-CN'][key]);
  });
});

test('falls back to English messages and warns when no language contains a key', () => {
  const warnings = [];
  const root = fakeRoot('zh-CN');
  root.console.warn = (...args) => warnings.push(args);
  const i18n = createRuntime(root, {
    en: { onlyEnglish: 'English fallback' },
    'zh-CN': {}
  });

  assert.equal(i18n.t('onlyEnglish'), 'English fallback');
  assert.equal(i18n.t('missing.key'), 'missing.key');
  assert.deepEqual(warnings, [['Missing i18n key:', 'missing.key']]);
});

test('selects plural variants using count and accepts a single Chinese plural message', () => {
  const messages = {
    en: { count: { one: '{count} book', other: '{count} books' } },
    'zh-CN': { count: '共 {count} 本书' }
  };
  const english = createRuntime(fakeRoot('en'), messages);
  const chinese = createRuntime(fakeRoot('zh-CN'), messages);

  assert.equal(english.t('count', { count: 1 }), '1 book');
  assert.equal(english.t('count', { count: 2 }), '2 books');
  assert.equal(chinese.t('count', { count: 2 }), '共 2 本书');
});

test('uses deterministic format fallbacks and returns an empty string for invalid dates', () => {
  const root = fakeRoot('en');
  root.Intl = {};
  const i18n = createRuntime(root, dictionaries);

  assert.equal(i18n.formatNumber(12345.6), '12345.6');
  assert.equal(i18n.formatDate('2026-08-18T09:02:03Z'), '2026-08-18');
  assert.equal(i18n.formatDate('not a date'), '');
});

test('continues locale selection and persistence when local storage throws', () => {
  const root = fakeRoot('zh-CN');
  root.localStorage = {
    getItem() { throw new Error('disabled'); },
    setItem() { throw new Error('disabled'); }
  };
  const i18n = createRuntime(root, dictionaries);

  assert.equal(i18n.init(), 'zh-CN');
  assert.equal(i18n.setLocale('en'), 'en');
});

test('uses cache and cookie storage fallbacks in order when local storage is unavailable', () => {
  const fromCache = fakeRoot('en');
  fromCache.localStorage = { getItem() { throw new Error('disabled'); } };
  fromCache.epubBrowserCache = { epub_browser_locale: 'zh-CN' };
  fromCache.document = { cookie: 'epub_browser_locale=en' };
  const fromCookie = fakeRoot('en');
  fromCookie.localStorage = { getItem() { throw new Error('disabled'); }, setItem() { throw new Error('disabled'); } };
  fromCookie.document = { cookie: 'epub_browser_locale=zh-CN' };

  assert.equal(createRuntime(fromCache, dictionaries).init(), 'zh-CN');
  assert.equal(createRuntime(fromCookie, dictionaries).init(), 'zh-CN');
  createRuntime(fromCookie, dictionaries).setLocale('en');
  assert.equal(fromCookie.document.cookie, 'epub_browser_locale=en; path=/');
});

test('ignores cookie access exceptions while determining the browser locale', () => {
  const root = fakeRoot('en');
  root.localStorage = { getItem() { throw new Error('disabled'); } };
  root.document = {};
  Object.defineProperty(root.document, 'cookie', { get() { throw new Error('cookies disabled'); } });

  assert.equal(createRuntime(root, dictionaries).init(), 'en');
});

test('removes unsubscribed listeners and isolates listener failures', () => {
  const root = fakeRoot('en');
  const warnings = [];
  const calls = [];
  root.console.warn = (...args) => warnings.push(args);
  const i18n = createRuntime(root, dictionaries);
  const unsubscribe = i18n.onLocaleChange(() => calls.push('removed'));
  i18n.onLocaleChange(() => { throw new Error('listener failure'); });
  i18n.onLocaleChange(locale => calls.push(locale));

  unsubscribe();
  i18n.setLocale('zh-CN');

  assert.deepEqual(calls, ['zh-CN']);
  assert.equal(warnings.length, 1);
});

test('translates explicit DOM attributes and maintains one localized manifest link', () => {
  const node = {
    attributes: {
      'data-i18n': 'common.version',
      'data-i18n-params': '{"version":"1.11.1"}',
      'data-i18n-title': 'common.version'
    },
    hasAttribute(name) { return Object.prototype.hasOwnProperty.call(this.attributes, name); },
    getAttribute(name) { return this.attributes[name] || null; },
    setAttribute(name, value) { this.attributes[name] = value; }
  };
  const head = {
    appendChild(node) { this.appended.push(node); },
    appended: []
  };
  const root = fakeRoot('zh-CN');
  root.document = {
    documentElement: { lang: '' },
    head,
    createElement() { return { id: '', href: '', rel: '' }; },
    querySelectorAll() { return [node]; },
    querySelector(selector) {
      if (selector === '#epubBrowserManifest') return head.appended[0] || null;
      return null;
    }
  };
  const i18n = createRuntime(root, dictionaries);

  i18n.init();

  assert.equal(root.document.documentElement.lang, 'zh-CN');
  assert.equal(head.appended.length, 1);
  assert.equal(head.appended[0].id, 'epubBrowserManifest');
  assert.equal(head.appended[0].href, '/assets/manifest.zh-CN.json');
  i18n.setLocale('en');
  assert.equal(node.textContent, 'Version 1.11.1');
  assert.equal(node.attributes.title, 'Version 1.11.1');
  assert.equal(head.appended.length, 1);
  assert.equal(head.appended[0].href, '/assets/manifest.en.json');
});

test('uses empty parameters when a DOM translation node has invalid parameter JSON', () => {
  const node = {
    attributes: { 'data-i18n': 'common.version', 'data-i18n-params': '{not json}' },
    hasAttribute(name) { return Object.prototype.hasOwnProperty.call(this.attributes, name); },
    getAttribute(name) { return this.attributes[name] || null; },
    setAttribute(name, value) { this.attributes[name] = value; }
  };
  const root = fakeRoot('en');
  root.document = { querySelectorAll() { return [node]; } };

  createRuntime(root, dictionaries).translateDocument();

  assert.equal(node.textContent, 'Version {version}');
});
