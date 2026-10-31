const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { createRuntime, publicPath } = require('../epub_browser/assets/i18n/i18n-core.js');

const SUPPORTED = ['en', 'zh-CN', 'zh-TW', 'ko', 'ja', 'es', 'de', 'fr', 'ru', 'it', 'pt-BR', 'ar', 'id', 'hi', 'vi', 'th', 'ms'];

function loadBundle(code) {
  return JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'epub_browser', 'assets', 'i18n', code + '.json'), 'utf8'));
}

const bundles = {};
SUPPORTED.forEach(code => { bundles[code] = loadBundle(code); });

function fakeRoot(language) {
  const values = {};
  const root = {
    navigator: { languages: [language], language },
    localStorage: {
      getItem: key => Object.prototype.hasOwnProperty.call(values, key) ? values[key] : null,
      setItem: (key, value) => { values[key] = String(value); }
    },
    addEventListener() {}, dispatchEvent() {},
    Intl, console: { warn() {} },
    __values: values
  };
  root.EpubBrowserURL = { publicPath: (p) => publicPath(root.EpubBrowserBasePath || '/', p) };
  return root;
}

test('normalizes all supported browser locale families and falls back unsupported locales to English', () => {
  assert.equal(createRuntime(fakeRoot('zh-SG'), bundles).init(), 'zh-CN');
  assert.equal(createRuntime(fakeRoot('zh-TW'), bundles).init(), 'zh-TW');
  assert.equal(createRuntime(fakeRoot('zh_HK'), bundles).init(), 'zh-TW');
  assert.equal(createRuntime(fakeRoot('zh-MO'), bundles).init(), 'zh-TW');
  assert.equal(createRuntime(fakeRoot('ko-KR'), bundles).init(), 'ko');
  assert.equal(createRuntime(fakeRoot('ja-JP'), bundles).init(), 'ja');
  assert.equal(createRuntime(fakeRoot('en-GB'), bundles).init(), 'en');
  assert.equal(createRuntime(fakeRoot('fr-FR'), bundles).init(), 'fr');
  assert.equal(createRuntime(fakeRoot('pt-PT'), bundles).init(), 'pt-BR');
  assert.equal(createRuntime(fakeRoot('ar-SA'), bundles).init(), 'ar');
  assert.equal(createRuntime(fakeRoot('nl-NL'), bundles).init(), 'en');
});

test('builds browser URLs from the generated base path', () => {
  assert.equal(publicPath('/project/', '/book/demo/index.html'), '/project/book/demo/index.html');
  assert.equal(publicPath('/project/', '/project/sw.js'), '/project/sw.js');
  assert.equal(publicPath('/', '/sw.js'), '/sw.js');

  const root = fakeRoot('en');
  root.EpubBrowserBasePath = '/project/';
  createRuntime(root, bundles);
  assert.equal(root.EpubBrowserURL.publicPath('/assets/manifest.en.json'), '/project/assets/manifest.en.json');
});

test('persists an explicit locale and interpolates text parameters', () => {
  const root = fakeRoot('en');
  const i18n = createRuntime(root, bundles);
  i18n.init();
  assert.equal(i18n.setLocale('zh-CN'), 'zh-CN');
  assert.equal(root.__values.epub_browser_locale, 'zh-CN');
  assert.equal(i18n.t('common.version', { version: '1.11.1' }), '版本 1.11.1');
});

test('applies RTL only for Arabic and restores LTR for other locales', () => {
  const root = fakeRoot('en');
  root.EpubBrowserDisableManifest = true;
  root.document = {
    documentElement: {},
    addEventListener() {},
    querySelectorAll() { return []; }
  };
  const i18n = createRuntime(root, bundles);
  i18n.setLocale('ar-SA');
  assert.equal(root.document.documentElement.lang, 'ar');
  assert.equal(root.document.documentElement.dir, 'rtl');
  i18n.setLocale('de-DE');
  assert.equal(root.document.documentElement.lang, 'de');
  assert.equal(root.document.documentElement.dir, 'ltr');
});

test('all supported dictionaries have identical non-empty shapes and interpolation tokens', () => {
  const placeholders = value => [...String(value).matchAll(/\{([A-Za-z0-9_]+)\}/g)].map(match => match[1]).sort();
  const shape = value => value && typeof value === 'object' ? Object.keys(value).sort() : typeof value;
  SUPPORTED.slice(1).forEach(locale => {
    assert.deepEqual(Object.keys(bundles[locale]).sort(), Object.keys(bundles.en).sort());
  });
  Object.keys(bundles.en).forEach(key => {
    SUPPORTED.forEach(locale => {
      const value = bundles[locale][key];
      assert.deepEqual(shape(value), shape(bundles.en[key]), `${locale}:${key} shape`);
      if (value && typeof value === 'object') {
        Object.keys(bundles.en[key]).forEach(category => {
          assert.notEqual(value[category], '', `${locale}:${key}.${category}`);
          assert.deepEqual(placeholders(value[category]), placeholders(bundles.en[key][category]), `${locale}:${key}.${category} placeholders`);
        });
      } else {
        assert.notEqual(value, '', `${locale}:${key}`);
        assert.deepEqual(placeholders(value), placeholders(bundles.en[key]), `${locale}:${key} placeholders`);
      }
    });
  });
});

test('OIDC provider actions are complete natural sentences in every locale', () => {
  const expected = {
    en: 'Continue with Company SSO',
    'zh-CN': '使用 Company SSO 继续',
    'zh-TW': '使用 Company SSO 繼續',
    ko: 'Company SSO로 계속',
    ja: 'Company SSO で続行',
    es: 'Continuar con Company SSO',
    de: 'Mit Company SSO fortfahren',
    fr: 'Continuer avec Company SSO',
    ru: 'Продолжить с помощью Company SSO',
    it: 'Continua con Company SSO',
    'pt-BR': 'Continuar com Company SSO',
    ar: 'المتابعة باستخدام Company SSO',
    id: 'Lanjutkan dengan Company SSO',
    hi: 'Company SSO से जारी रखें',
    vi: 'Tiếp tục với Company SSO',
    th: 'ดำเนินการต่อด้วย Company SSO',
    ms: 'Teruskan dengan Company SSO',
  };
  Object.entries(expected).forEach(([locale, label]) => {
    const i18n = createRuntime(fakeRoot(locale), bundles);
    i18n.init();
    assert.equal(i18n.t('account.oidc.continueWith', { provider: 'Company SSO' }), label, locale);
  });
});

test('rich i18n parameters preserve locale word order and use safe strong text nodes', () => {
  const attributes = {
    'data-i18n': 'account.oidc.continueWith',
    'data-i18n-params': JSON.stringify({ provider: '<Company SSO>' }),
    'data-i18n-strong-param': 'provider',
  };
  const children = [];
  const document = {
    documentElement: {},
    createTextNode(value) { return { nodeType: 3, textContent: String(value) }; },
    createElement(tagName) {
      return { tagName: String(tagName).toUpperCase(), textContent: '' };
    },
    querySelectorAll() { return [node]; },
  };
  const node = {
    ownerDocument: document,
    getAttribute(name) { return attributes[name] || null; },
    hasAttribute(name) { return Object.prototype.hasOwnProperty.call(attributes, name); },
    appendChild(child) { children.push(child); return child; },
  };
  Object.defineProperty(node, 'textContent', {
    get() { return children.map(child => child.textContent).join(''); },
    set(value) {
      children.length = 0;
      if (value) children.push(document.createTextNode(value));
    },
  });
  const root = fakeRoot('zh-CN');
  root.EpubBrowserDisableManifest = true;
  root.document = document;
  const i18n = createRuntime(root, bundles);

  i18n.setLocale('zh-CN');

  assert.equal(node.textContent, '使用 <Company SSO> 继续');
  assert.deepEqual(children.map(child => child.tagName || '#text'), [
    '#text', 'STRONG', '#text'
  ]);
  assert.equal(children[1].textContent, '<Company SSO>');
});

test('user deletion warnings are complete in every supported locale', () => {
  const locales = SUPPORTED;
  const keys = [
    'admin.dangerZone', 'admin.deleteUser', 'admin.deleteUserHelp',
    'admin.deleteUserSimpleConfirm', 'admin.deleteUserImpactConfirm',
    'admin.deleteUserConfirmationLabel', 'admin.userDeleted',
    'admin.userDeleteData.authentication', 'admin.userDeleteData.library',
    'admin.userDeleteData.ai', 'admin.userDeleteData.dictionary_history',
    'admin.userDeleteRetained.dictionary_attribution',
    'admin.userDeleteRetained.ai_retry_attribution',
    'admin.error.user_deletion_confirmation_required',
    'admin.error.self_deletion_forbidden',
  ];
  locales.forEach(locale => keys.forEach(key => {
    assert.equal(typeof bundles[locale][key], 'string', `${locale}:${key}`);
    assert.notEqual(bundles[locale][key], '', `${locale}:${key}`);
  }));
  assert.equal(
    bundles['zh-CN']['admin.deleteUserConfirmationLabel'],
    '输入 {username} 以确认'
  );
  assert.match(
    bundles['zh-CN']['admin.userDeleteRetained.dictionary_attribution'],
    /保留并转交/
  );
});

test('initializes locale document direction before any fetch resolves', () => {
  const root = fakeRoot('ar');
  root.EpubBrowserDisableManifest = true;
  root.document = { documentElement: {}, addEventListener() {}, querySelectorAll() { return []; } };
  const i18n = createRuntime(root, bundles);
  i18n.init();
  assert.equal(i18n.getLocale(), 'ar');
  assert.equal(root.document.documentElement.dir, 'rtl');
});
