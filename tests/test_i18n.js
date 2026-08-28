const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const { createRuntime, dictionaries, publicPath } = require('../epub_browser/assets/i18n.js');

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

test('normalizes all supported browser locale families and falls back unsupported locales to English', () => {
  assert.equal(createRuntime(fakeRoot('zh-SG'), dictionaries).init(), 'zh-CN');
  assert.equal(createRuntime(fakeRoot('zh-TW'), dictionaries).init(), 'zh-TW');
  assert.equal(createRuntime(fakeRoot('zh_HK'), dictionaries).init(), 'zh-TW');
  assert.equal(createRuntime(fakeRoot('zh-MO'), dictionaries).init(), 'zh-TW');
  assert.equal(createRuntime(fakeRoot('ko-KR'), dictionaries).init(), 'ko');
  assert.equal(createRuntime(fakeRoot('ja-JP'), dictionaries).init(), 'ja');
  assert.equal(createRuntime(fakeRoot('en-GB'), dictionaries).init(), 'en');
  assert.equal(createRuntime(fakeRoot('fr-FR'), dictionaries).init(), 'fr');
  assert.equal(createRuntime(fakeRoot('pt-PT'), dictionaries).init(), 'pt-BR');
  assert.equal(createRuntime(fakeRoot('ar-SA'), dictionaries).init(), 'ar');
  assert.equal(createRuntime(fakeRoot('nl-NL'), dictionaries).init(), 'en');
});

test('builds browser URLs from the generated base path', () => {
  assert.equal(publicPath('/project/', '/book/demo/index.html'), '/project/book/demo/index.html');
  assert.equal(publicPath('/project/', '/project/sw.js'), '/project/sw.js');
  assert.equal(publicPath('/', '/sw.js'), '/sw.js');

  const root = fakeRoot('en');
  root.EpubBrowserBasePath = '/project/';
  createRuntime(root, dictionaries);
  assert.equal(root.EpubBrowserURL.publicPath('/assets/manifest.en.json'), '/project/assets/manifest.en.json');
});

test('persists an explicit locale and interpolates text parameters', () => {
  const root = fakeRoot('en');
  const i18n = createRuntime(root, dictionaries);
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
  const i18n = createRuntime(root, dictionaries);
  i18n.setLocale('ar-SA');
  assert.equal(root.document.documentElement.lang, 'ar');
  assert.equal(root.document.documentElement.dir, 'rtl');
  i18n.setLocale('de-DE');
  assert.equal(root.document.documentElement.lang, 'de');
  assert.equal(root.document.documentElement.dir, 'ltr');
});

test('all supported dictionaries have identical non-empty shapes and interpolation tokens', () => {
  const locales = ['en', 'zh-CN', 'zh-TW', 'ko', 'ja', 'es', 'de', 'fr', 'ru', 'it', 'pt-BR', 'ar', 'id', 'hi', 'vi', 'th', 'ms'];
  const placeholders = value => [...String(value).matchAll(/\{([A-Za-z0-9_]+)\}/g)].map(match => match[1]).sort();
  const shape = value => value && typeof value === 'object' ? Object.keys(value).sort() : typeof value;
  locales.slice(1).forEach(locale => {
    assert.deepEqual(Object.keys(dictionaries[locale]).sort(), Object.keys(dictionaries.en).sort());
  });
  Object.keys(dictionaries.en).forEach(key => {
    locales.forEach(locale => {
      const value = dictionaries[locale][key];
      assert.deepEqual(shape(value), shape(dictionaries.en[key]), `${locale}:${key} shape`);
      if (value && typeof value === 'object') {
        Object.keys(dictionaries.en[key]).forEach(category => {
          assert.notEqual(value[category], '', `${locale}:${key}.${category}`);
          assert.deepEqual(placeholders(value[category]), placeholders(dictionaries.en[key][category]), `${locale}:${key}.${category} placeholders`);
        });
      } else {
        assert.notEqual(value, '', `${locale}:${key}`);
        assert.deepEqual(placeholders(value), placeholders(dictionaries.en[key]), `${locale}:${key} placeholders`);
      }
    });
  });
});

test('all locales present one unified tag vocabulary without AI or EPUB variants', () => {
  const labels = {
    en: 'Tags', 'zh-CN': '标签', 'zh-TW': '標籤', ko: '태그', ja: 'タグ',
    es: 'Etiquetas', de: 'Schlagwörter', fr: 'Étiquettes', ru: 'Метки', it: 'Tag',
    'pt-BR': 'Etiquetas', ar: 'الوسوم', id: 'Tag', hi: 'टैग', vi: 'Thẻ', th: 'แท็ก', ms: 'Tag',
  };
  Object.entries(labels).forEach(([locale, label]) => {
    const messages = dictionaries[locale];
    assert.equal(messages['admin.ai.tags'], label, `${locale}: unified tag label`);
    assert.equal(messages['admin.ai.epubTags'], label, `${locale}: legacy EPUB label`);
    assert.equal(messages['admin.ai.noEpubTags'], messages['admin.ai.noTags'], `${locale}: unified empty state`);
    assert.notEqual(messages['admin.error.invalid_ai_tag'], dictionaries[locale]['admin.error.invalid_ai_access'], `${locale}: tag validation is not AI access copy`);
  });
  assert.equal(dictionaries.en['admin.error.invalid_ai_tag'], 'Enter a valid tag.');
  assert.equal(dictionaries['zh-CN']['admin.error.invalid_ai_tag'], '请输入有效的标签。');
});

test('new locale packs have no unexpected English fallback copy', () => {
  const locales = ['es', 'de', 'fr', 'ru', 'it', 'pt-BR', 'ar', 'id', 'hi', 'vi', 'th', 'ms'];
  const sharedInvariantKeys = new Set([
    'common.brand',
    'reader.pageRange',
    'admin.userSummary',
    'annotations.hexPlaceholder',
    'annotations.authorSeparator',
    'annotations.bylineSeparator',
    'footer.poweredBySuffix',
    'admin.dictionaryFormatMdictName',
    'admin.dictionaryFormatStardictName',
    'admin.webhooks.title',
    'admin.webhooks.urlPlaceholder',
  ]);
  const nativeIdenticalKeys = {
    es: ['theme.sepia', 'admin.books.profile.general', 'admin.ai.profile.general', 'admin.ai.jobs.header.error', 'ai.spoilers', 'book.totalChapters', 'annotations.color', 'readingInsights.duration.minute', 'apiDocs.endpointCount'],
    de: ['common.version', 'theme.sepia', 'settings.optional', 'account.role.admin', 'admin.ai.jobs.statusFilter', 'admin.ai.jobs.header.status', 'account.pats.group.administration', 'admin.webhooks.name', 'apiDocs.format'],
    fr: ['common.version', 'reader.annotations', 'library.annotations', 'admin.menu', 'admin.title', 'admin.books.profile.fiction', 'admin.books.header.action', 'admin.books.pageButton', 'admin.ai.profile.fiction', 'admin.ai.jobs.header.action', 'admin.ai.jobs.pageButton', 'ai.spoilers', 'ai.annotation.concept', 'ai.annotation.question', 'ai.libraryConfigVersion', 'ai.libraryVersionCount', 'ai.conversation', 'book.annotations', 'annotations.tab', 'annotations.hubTitle', 'annotations.annotationCount', 'annotations.shareCount', 'annotations.shareNote', 'annotations.shareFileFallback', 'annotations.noteAction', 'readingInsights.duration.minute', 'account.pats.group.annotations', 'account.pats.group.administration', 'account.pats.expiration', 'apiDocs.format', 'apiDocs.group.annotations'],
    ru: [],
    it: ['reader.home', 'account.menu', 'account.password', 'book.home', 'dictionary.source', 'readingInsights.duration.minute'],
    'pt-BR': ['admin.ai.jobs.statusFilter', 'admin.ai.jobs.header.status', 'ai.spoilers', 'book.totalChapters', 'readingInsights.duration.minute', 'apiDocs.endpointCount'],
    ar: [],
    id: ['theme.sepia', 'theme.lavender', 'account.role.admin', 'admin.ai.model', 'admin.ai.jobs.statusFilter', 'admin.ai.jobs.header.status', 'book.totalChapters', 'apiDocs.format'],
    hi: [],
    vi: [],
    th: [],
    ms: ['theme.sepia', 'theme.lavender', 'admin.ai.model', 'admin.ai.jobs.statusFilter', 'admin.ai.jobs.header.status', 'bookshelf.import', 'readingInsights.duration.minute', 'apiDocs.format'],
  };
  locales.forEach(locale => {
    const allowed = new Set(nativeIdenticalKeys[locale]);
    Object.keys(dictionaries.en).forEach(key => {
      const identical = JSON.stringify(dictionaries[locale][key]) === JSON.stringify(dictionaries.en[key]);
      const intentional = key.startsWith('locale.name.') || sharedInvariantKeys.has(key) || allowed.has(key);
      assert.equal(identical && !intentional, false, `${locale}:${key} unexpectedly falls back to English`);
    });
  });
});

test('translates the local annotation sharing actions in all five supported locales', () => {
  ['en', 'zh-CN', 'zh-TW', 'ko', 'ja'].forEach(locale => {
    [
      'annotations.shareActions',
      'annotations.copyShare',
      'annotations.exportShare',
      'annotations.annotationActions',
      'annotations.copyAnnotation',
      'annotations.annotationCopied',
      'annotations.annotationCopyFailed',
      'annotations.shareAuthors',
      'annotations.shareCount',
      'annotations.shareNote',
      'annotations.shareCopied',
      'annotations.shareCopyFailed',
      'annotations.shareExported',
      'annotations.shareExportFailed',
      'annotations.shareFileFallback',
    ].forEach(key => assert.notEqual(dictionaries[locale][key], undefined, `${locale}:${key}`));
  });
});

test('localizes private review and reading-insight copy in all five supported locales', () => {
  const keys = [
    'bookReviews.title',
    'bookReviews.rating',
    'bookReviews.ratingValue',
    'bookReviews.ratingRequired',
    'bookReviews.review',
    'bookReviews.reviewHint',
    'bookReviews.save',
    'bookReviews.delete',
    'bookReviews.savedRating',
    'bookReviews.saved',
    'bookReviews.deleted',
    'bookReviews.deleteConfirm',
    'book.readingTime',
    'readingInsights.navigation',
    'readingInsights.description',
    'readingInsights.pageTitle',
    'readingInsights.library',
    'readingInsights.privateKicker',
    'readingInsights.title',
    'readingInsights.intro',
    'readingInsights.periodLabel',
    'readingInsights.period.overview',
    'readingInsights.period.day',
    'readingInsights.period.week',
    'readingInsights.period.month',
    'readingInsights.rangeLabel',
    'readingInsights.previousRange',
    'readingInsights.nextRange',
    'readingInsights.summaryLabel',
    'readingInsights.total',
    'readingInsights.topBook',
    'readingInsights.activity',
    'readingInsights.activityHeatmap',
    'readingInsights.activityRange',
    'readingInsights.activityLess',
    'readingInsights.activityMore',
    'readingInsights.activityScale',
    'readingInsights.trend',
    'readingInsights.trendRange',
    'readingInsights.trend.duration',
    'readingInsights.trend.books',
    'readingInsights.trendTotalDuration',
    'readingInsights.trendTotalBooks',
    'readingInsights.axis.readingTime',
    'readingInsights.axis.books',
    'readingInsights.booksRead',
    'readingInsights.days',
    'readingInsights.selectedDay',
    'readingInsights.empty',
    'readingInsights.emptyDay',
    'readingInsights.loading',
    'readingInsights.loaded',
    'readingInsights.error',
    'readingInsights.unknownBook',
    'readingInsights.unknownChapter',
    'readingInsights.session.start',
    'readingInsights.session.book',
    'readingInsights.session.chapter',
    'readingInsights.session.duration',
    'readingInsights.duration.second',
    'readingInsights.duration.minute',
    'readingInsights.duration.hour',
    'readingSessions.pending',
    'readingSessions.error',
    'readingSessions.discarded',
  ];
  ['en', 'zh-CN', 'zh-TW', 'ko', 'ja'].forEach(locale => {
    keys.forEach(key => assert.ok(dictionaries[locale][key], `${locale}:${key}`));
  });
});

test('provides native locale names and translated AI language labels', () => {
  const nativeNames = {
    en: 'English', 'zh-CN': '简体中文', 'zh-TW': '繁體中文', ko: '한국어', ja: '日本語',
    es: 'Español', de: 'Deutsch', fr: 'Français', ru: 'Русский', it: 'Italiano',
    'pt-BR': 'Português (Brasil)', ar: 'العربية', id: 'Bahasa Indonesia', hi: 'हिन्दी',
    vi: 'Tiếng Việt', th: 'ไทย', ms: 'Bahasa Melayu'
  };
  Object.keys(dictionaries).forEach(locale => {
    Object.entries(nativeNames).forEach(([code, name]) => {
      assert.equal(dictionaries[locale][`locale.name.${code}`], name);
    });
  });
  assert.equal(dictionaries['zh-TW']['ai.title'], 'AI 閱讀');
  assert.equal(dictionaries.ko['account.signIn'], '로그인');
  assert.equal(dictionaries.ja['library.title'], 'ライブラリ');
});

test('new locale packs translate the Library and Book primary surfaces', () => {
  const locales = ['es', 'de', 'fr', 'ru', 'it', 'pt-BR', 'ar', 'id', 'hi', 'vi', 'th', 'ms'];
  const keys = [
    'library.navigation', 'library.bookCount', 'library.tagCount', 'library.shelf',
    'library.searchPlaceholder', 'library.noTag', 'readingInsights.navigation',
    'ai.library', 'book.navigation', 'book.shelf', 'book.startReading',
    'book.addToShelf', 'book.tableOfContents', 'footer.poweredBy'
  ];
  locales.forEach(locale => {
    keys.forEach(key => {
      assert.notDeepEqual(dictionaries[locale][key], dictionaries.en[key], `${locale}:${key}`);
    });
  });
  assert.equal(dictionaries.es['library.shelf'], 'Estantería');
  assert.equal(dictionaries.es['readingInsights.navigation'], 'Estadísticas de lectura');
  assert.equal(dictionaries.ar['library.navigation'], 'التنقل الرئيسي');
});

test('new locale packs translate every Library, Book, Chapter, and API Docs message', () => {
  const locales = ['es', 'de', 'fr', 'ru', 'it', 'pt-BR', 'ar', 'id', 'hi', 'vi', 'th', 'ms'];
  const namespaces = /^(library|book|reader|settings|apiDocs)\./;
  const intentionalInvariants = {
    es: ['reader.pageRange', 'book.totalChapters', 'apiDocs.endpointCount'],
    de: ['reader.pageRange', 'settings.optional', 'apiDocs.format'],
    fr: ['reader.annotations', 'reader.pageRange', 'library.annotations', 'book.annotations', 'apiDocs.format', 'apiDocs.group.annotations'],
    ru: ['reader.pageRange'],
    it: ['reader.home', 'reader.pageRange', 'book.home'],
    'pt-BR': ['reader.pageRange', 'book.totalChapters', 'apiDocs.endpointCount'],
    ar: ['reader.pageRange'],
    id: ['reader.pageRange', 'book.totalChapters', 'apiDocs.format'],
    hi: ['reader.pageRange'],
    vi: ['reader.pageRange'],
    th: ['reader.pageRange'],
    ms: ['reader.pageRange', 'apiDocs.format'],
  };
  locales.forEach(locale => {
    const unchanged = Object.keys(dictionaries.en).filter(key => (
      namespaces.test(key) && dictionaries[locale][key] === dictionaries.en[key]
    ));
    assert.deepEqual(unchanged, intentionalInvariants[locale], `${locale} untranslated page copy`);
  });
});

test('localizes every navigation behavior choice and its helper copy', () => {
  const keys = [
    'settings.navigationBehavior',
    'settings.navigationBehaviorHelp',
    'settings.navigationBehavior.normal',
    'settings.navigationBehavior.sticky',
    'settings.navigationBehavior.autoHide',
    'settings.keyboardNavigation',
    'settings.arrowKeyNavigation',
    'settings.spaceKeyNavigation',
  ];
  ['en', 'zh-CN', 'zh-TW', 'ko', 'ja'].forEach(locale => {
    keys.forEach(key => assert.ok(dictionaries[locale][key], `${locale}:${key}`));
  });
});

test('localizes AI administration panels and chapter regeneration in all five locales', () => {
  const keys = [
    'admin.ai.configuration',
    'admin.ai.permissions',
    'admin.ai.jobs.header.timeline',
    'ai.regenerateScopeTitle',
    'ai.regenerateScopeDescription',
    'ai.regenerateScopeAction',
  ];
  ['en', 'zh-CN', 'zh-TW', 'ko', 'ja'].forEach(locale => {
    keys.forEach(key => assert.ok(dictionaries[locale][key], `${locale}:${key}`));
  });
});

test('uses Taiwan product language for navigation AI errors and destructive actions', () => {
  const traditional = dictionaries['zh-TW'];
  assert.deepEqual({
    aiJobsPages: traditional['admin.ai.jobs.paginationLabel'],
    aiJobsRefresh: traditional['admin.ai.jobs.refresh'],
    bookChat: traditional['ai.bookChat'],
    backToBook: traditional['ai.backToBook'],
    answer: traditional['ai.answer'],
    config: traditional['ai.libraryConfigVersion'],
    clearProgressError: traditional['book.clearReadingProgressFailed'],
    removeFromShelf: traditional['book.removeFromShelf'],
    libraryLoadError: traditional['library.loadError'],
    countingData: traditional['annotations.countingData'],
    exportData: traditional['annotations.exportData'],
  }, {
    aiJobsPages: 'AI 作業頁面',
    aiJobsRefresh: '重新整理',
    bookChat: '書籍對話',
    backToBook: '返回書籍',
    answer: '後續回答',
    config: '設定',
    clearProgressError: '無法清除閱讀進度。請再試一次。',
    removeFromShelf: '從書架移除',
    libraryLoadError: '無法載入書庫。請重新整理後再試。',
    countingData: '正在計算資料…',
    exportData: '匯出資料',
  });
});

test('provides exact bilingual administrator AI job scope and language labels', () => {
  assert.deepEqual({
    book: dictionaries.en['admin.ai.jobs.scope.book'],
    chapter: dictionaries.en['admin.ai.jobs.scope.chapter'],
    en: dictionaries.en['admin.ai.jobs.language.en'],
    zhCN: dictionaries.en['admin.ai.jobs.language.zh-CN'],
  }, {
    book: 'Whole book',
    chapter: 'Chapter',
    en: 'English',
    zhCN: 'Simplified Chinese',
  });
  assert.deepEqual({
    book: dictionaries['zh-CN']['admin.ai.jobs.scope.book'],
    chapter: dictionaries['zh-CN']['admin.ai.jobs.scope.chapter'],
    en: dictionaries['zh-CN']['admin.ai.jobs.language.en'],
    zhCN: dictionaries['zh-CN']['admin.ai.jobs.language.zh-CN'],
  }, {
    book: '全书',
    chapter: '章节',
    en: '英语',
    zhCN: '简体中文',
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

test('normalizes aliases from persisted storage before selecting a dictionary and manifest', () => {
  const root = fakeRoot('en');
  root.__values.epub_browser_locale = 'zh-HK';
  root.document = {
    documentElement: { lang: '' },
    head: { appendChild(node) { this.node = node; } },
    createElement() { return {}; },
    querySelector() { return this.head.node || null; },
    querySelectorAll() { return []; },
  };
  const i18n = createRuntime(root, dictionaries);

  assert.equal(i18n.init(), 'zh-TW');
  assert.equal(root.document.documentElement.lang, 'zh-TW');
  assert.equal(root.document.head.node.href, '/assets/manifest.zh-TW.json');
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
  root.EpubBrowserBasePath = '/reader/';
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
  assert.equal(head.appended[0].href, '/reader/assets/manifest.zh-CN.json');
  i18n.setLocale('en');
  assert.equal(node.textContent, 'Version 1.11.1');
  assert.equal(node.attributes.title, 'Version 1.11.1');
  assert.equal(head.appended.length, 1);
  assert.equal(head.appended[0].href, '/reader/assets/manifest.en.json');
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

test('rerenders an open theme menu after the locale changes', () => {
  let locale = 'en';
  let localeChangeListener;

  function element() {
    const result = {
      style: {}, children: [], listeners: {}, attributes: {}, className: '',
      appendChild(child) { this.children.push(child); return child; },
      addEventListener(type, listener) { this.listeners[type] = listener; },
      setAttribute(name, value) { this.attributes[name] = String(value); },
      getAttribute(name) { return this.attributes[name] || null; },
      focus() {},
      querySelector(selector) { return selector === 'i' ? { className: '' } : null; },
      contains() { return false; },
      getBoundingClientRect() { return { bottom: 10, right: 10 }; },
    };
    Object.defineProperty(result, 'innerHTML', {
      get() { return this._innerHTML || ''; },
      set(value) { this._innerHTML = value; this.children = []; },
    });
    return result;
  }

  const themeToggle = element();
  const body = element();
  const document = {
    cookie: '', body,
    documentElement: { classList: { add() {}, remove() {} } },
    getElementById(id) { return id === 'themeToggle' ? themeToggle : null; },
    createElement: element,
    createTextNode(textContent) { return { textContent }; },
    querySelector() { return null; },
    addEventListener() {},
  };
  const window = {
    document, navigator: { userAgent: '' }, innerWidth: 1024,
    localStorage: { getItem() { return null; }, setItem() {} },
    getComputedStyle() { return { display: 'none' }; },
    addEventListener() {},
    EpubBrowserI18n: {
      t(key) { return locale + ':' + key; },
      onLocaleChange(listener) { localeChangeListener = listener; },
    },
  };
  const source = fs.readFileSync('epub_browser/assets/theme.js', 'utf8');

  vm.runInNewContext(source, { window, document, navigator: window.navigator, localStorage: window.localStorage, Date, decodeURIComponent });
  window.initTheme();
  themeToggle.listeners.click({ stopPropagation() {} });

  assert.equal(body.children[0].children[0].children[0].textContent, 'en:theme.light');
  locale = 'zh-CN';
  localeChangeListener();
  assert.equal(body.children[0].children[0].children[0].textContent, 'zh-CN:theme.light');
  assert.equal(body.children[0].style.display, 'block');
});

test('theme picker exposes native choices and the active theme', () => {
  function element(tagName) {
    const result = {
      tagName, style: {}, children: [], listeners: {}, attributes: {}, className: '', focusCount: 0,
      appendChild(child) { this.children.push(child); return child; },
      addEventListener(type, listener) { this.listeners[type] = listener; },
      setAttribute(name, value) { this.attributes[name] = String(value); },
      getAttribute(name) { return this.attributes[name] || null; },
      focus() { this.focusCount += 1; },
      querySelector(selector) { return selector === 'i' ? { className: '' } : null; },
      contains() { return false; },
      getBoundingClientRect() { return { bottom: 10, right: 10 }; },
    };
    Object.defineProperty(result, 'innerHTML', {
      get() { return this._innerHTML || ''; },
      set(value) { this._innerHTML = value; this.children = []; },
    });
    return result;
  }

  const themeToggle = element('button');
  const body = element('body');
  const document = {
    cookie: '', body, listeners: {},
    documentElement: { classList: { add() {}, remove() {} } },
    getElementById(id) { return id === 'themeToggle' ? themeToggle : null; },
    createElement: element,
    createTextNode(textContent) { return { textContent }; },
    querySelector() { return null; },
    addEventListener(type, listener) { this.listeners[type] = listener; },
  };
  const window = {
    document, navigator: { userAgent: '' }, innerWidth: 1024,
    localStorage: { getItem() { return 'forest'; }, setItem() {} },
    getComputedStyle() { return { display: 'none' }; },
    addEventListener() {},
    EpubBrowserI18n: { t(key) { return key; }, onLocaleChange() {} },
  };

  vm.runInNewContext(fs.readFileSync('epub_browser/assets/theme.js', 'utf8'), {
    window, document, navigator: window.navigator, localStorage: window.localStorage, Date, decodeURIComponent,
  });
  window.initTheme();
  themeToggle.listeners.click({ stopPropagation() {} });

  const menu = body.children[0];
  const activeChoice = menu.children[3];
  assert.equal(menu.getAttribute('role'), 'menu');
  assert.equal(themeToggle.getAttribute('aria-expanded'), 'true');
  assert.equal(activeChoice.tagName, 'button');
  assert.equal(activeChoice.getAttribute('role'), 'menuitemradio');
  assert.equal(activeChoice.getAttribute('aria-checked'), 'true');
});

test('theme picker closes on Escape and restores focus to its toggle', () => {
  function element(tagName) {
    const result = {
      tagName, style: {}, children: [], listeners: {}, attributes: {}, className: '', focusCount: 0,
      appendChild(child) { this.children.push(child); return child; },
      addEventListener(type, listener) { this.listeners[type] = listener; },
      setAttribute(name, value) { this.attributes[name] = String(value); },
      getAttribute(name) { return this.attributes[name] || null; },
      focus() { this.focusCount += 1; },
      querySelector(selector) { return selector === 'i' ? { className: '' } : null; },
      contains() { return false; },
      getBoundingClientRect() { return { bottom: 10, right: 10 }; },
    };
    Object.defineProperty(result, 'innerHTML', {
      get() { return this._innerHTML || ''; },
      set(value) { this._innerHTML = value; this.children = []; },
    });
    return result;
  }

  const themeToggle = element('button');
  const body = element('body');
  const document = {
    cookie: '', body, listeners: {},
    documentElement: { classList: { add() {}, remove() {} } },
    getElementById(id) { return id === 'themeToggle' ? themeToggle : null; },
    createElement: element,
    createTextNode(textContent) { return { textContent }; },
    querySelector() { return null; },
    addEventListener(type, listener) { this.listeners[type] = listener; },
  };
  const window = {
    document, navigator: { userAgent: '' }, innerWidth: 1024,
    localStorage: { getItem() { return 'light'; }, setItem() {} },
    getComputedStyle() { return { display: 'none' }; },
    addEventListener() {},
    EpubBrowserI18n: { t(key) { return key; }, onLocaleChange() {} },
  };

  vm.runInNewContext(fs.readFileSync('epub_browser/assets/theme.js', 'utf8'), {
    window, document, navigator: window.navigator, localStorage: window.localStorage, Date, decodeURIComponent,
  });
  window.initTheme();
  themeToggle.listeners.click({ stopPropagation() {} });
  (document.listeners.keydown || (() => {}))({ key: 'Escape' });

  assert.equal(body.children[0].style.display, 'none');
  assert.equal(themeToggle.getAttribute('aria-expanded'), 'false');
  assert.equal(themeToggle.focusCount, 1);
});

test('theme picker closes before another navigation control stops click propagation', () => {
  function element(tagName) {
    const result = {
      tagName, style: {}, children: [], listeners: {}, attributes: {}, className: '',
      appendChild(child) { this.children.push(child); return child; },
      addEventListener(type, listener) { this.listeners[type] = listener; },
      setAttribute(name, value) { this.attributes[name] = String(value); },
      getAttribute(name) { return this.attributes[name] || null; },
      focus() {},
      querySelector(selector) { return selector === 'i' ? { className: '' } : null; },
      contains() { return false; },
      getBoundingClientRect() { return { bottom: 10, right: 10 }; },
    };
    Object.defineProperty(result, 'innerHTML', {
      get() { return this._innerHTML || ''; },
      set(value) { this._innerHTML = value; this.children = []; },
    });
    return result;
  }

  const themeToggle = element('button');
  const localeToggle = element('button');
  const body = element('body');
  const document = {
    cookie: '', body, listeners: { capture: {}, bubble: {} },
    documentElement: { classList: { add() {}, remove() {} } },
    getElementById(id) { return id === 'themeToggle' ? themeToggle : null; },
    createElement: element,
    createTextNode(textContent) { return { textContent }; },
    querySelector() { return null; },
    addEventListener(type, listener, capture) {
      this.listeners[capture ? 'capture' : 'bubble'][type] = listener;
    },
  };
  const window = {
    document, navigator: { userAgent: '' }, innerWidth: 1024,
    localStorage: { getItem() { return 'light'; }, setItem() {} },
    getComputedStyle() { return { display: 'none' }; },
    addEventListener() {},
    EpubBrowserI18n: { t(key) { return key; }, onLocaleChange() {} },
  };

  vm.runInNewContext(fs.readFileSync('epub_browser/assets/theme.js', 'utf8'), {
    window, document, navigator: window.navigator, localStorage: window.localStorage, Date, decodeURIComponent,
  });
  window.initTheme();
  themeToggle.listeners.click({ stopPropagation() {} });
  (document.listeners.capture.click || function() {})({ target: localeToggle });

  assert.equal(body.children[0].style.display, 'none');
  assert.equal(themeToggle.getAttribute('aria-expanded'), 'false');
});

test('theme picker moves focus between choices with arrow keys', () => {
  function element(tagName) {
    const result = {
      tagName, style: {}, children: [], listeners: {}, attributes: {}, className: '', focusCount: 0,
      appendChild(child) { this.children.push(child); return child; },
      addEventListener(type, listener) { this.listeners[type] = listener; },
      setAttribute(name, value) { this.attributes[name] = String(value); },
      getAttribute(name) { return this.attributes[name] || null; },
      focus() { this.focusCount += 1; },
      querySelector(selector) { return selector === 'i' ? { className: '' } : null; },
      contains() { return false; },
      getBoundingClientRect() { return { bottom: 10, right: 10 }; },
    };
    Object.defineProperty(result, 'innerHTML', {
      get() { return this._innerHTML || ''; },
      set(value) { this._innerHTML = value; this.children = []; },
    });
    return result;
  }

  const themeToggle = element('button');
  const body = element('body');
  const document = {
    cookie: '', body, listeners: {},
    documentElement: { classList: { add() {}, remove() {} } },
    getElementById(id) { return id === 'themeToggle' ? themeToggle : null; },
    createElement: element,
    createTextNode(textContent) { return { textContent }; },
    querySelector() { return null; },
    addEventListener(type, listener) { this.listeners[type] = listener; },
  };
  const window = {
    document, navigator: { userAgent: '' }, innerWidth: 1024,
    localStorage: { getItem() { return 'forest'; }, setItem() {} },
    getComputedStyle() { return { display: 'none' }; },
    addEventListener() {},
    EpubBrowserI18n: { t(key) { return key; }, onLocaleChange() {} },
  };

  vm.runInNewContext(fs.readFileSync('epub_browser/assets/theme.js', 'utf8'), {
    window, document, navigator: window.navigator, localStorage: window.localStorage, Date, decodeURIComponent,
  });
  window.initTheme();
  themeToggle.listeners.click({ stopPropagation() {} });
  document.listeners.keydown({ key: 'ArrowDown', preventDefault() {} });

  assert.equal(body.children[0].children[4].focusCount, 1);
});
