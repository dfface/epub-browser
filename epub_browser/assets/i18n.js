(function(root, factory) {
  var exported = factory();
  if (typeof module === 'object' && module.exports) module.exports = exported;
  if (root && root.document) root.EpubBrowserI18n = exported.createRuntime(root, exported.dictionaries);
})(typeof window !== 'undefined' ? window : (typeof globalThis !== 'undefined' ? globalThis : this), function() {
  'use strict';

  var STORAGE_KEY = 'epub_browser_locale';
  var dictionaries = {
    en: {
      'common.language': 'Language',
      'common.version': 'Version {version}',
      'theme.light': 'Light',
      'theme.dark': 'Dark',
      'theme.sepia': 'Sepia',
      'theme.forest': 'Forest',
      'theme.ocean': 'Ocean',
      'theme.peach': 'Peach',
      'theme.lavender': 'Lavender',
      'library.title': 'Library',
      'library.pageTitle': 'EPUB Library',
      'library.description': 'EPUB Library - A web-based EPUB reader',
      'library.information': 'Library information',
      'library.bookCount': { one: '{count} book', other: '{count} books' },
      'library.tagCount': { one: '{count} tag', other: '{count} tags' },
      'library.annotations': 'Annotations',
      'library.login': 'Login',
      'library.theme': 'Theme',
      'library.searchPlaceholder': 'Search by book title, author, or tag...',
      'library.all': 'All',
      'library.noTag': 'No tag',
      'library.top': 'Top',
      'library.shelf': 'Shelf',
      'library.cover': 'Cover',
      'library.usernamePrompt': 'Please enter your username:',
      'library.usernameSaved': 'Username saved: {username}',
      'library.usernameCleared': 'Username cleared',
      'library.install': 'Install',
      'library.installing': 'Installing app...',
      'library.installSucceeded': 'App installed successfully!',
      'library.installCancelled': 'Install cancelled',
      'library.loading': 'Loading library',
      'library.empty': 'No books in your library yet.',
      'library.loadError': 'Unable to load your library. Please refresh and try again.',
      'footer.product': 'EPUB Library',
      'footer.poweredBy': 'Powered by',
      'version.updateAvailable': 'Update available: v{version}',
      'errors.generic': 'Something went wrong.',
      'errors.network': 'A network error occurred.'
    },
    'zh-CN': {
      'common.language': '语言',
      'common.version': '版本 {version}',
      'theme.light': '浅色',
      'theme.dark': '深色',
      'theme.sepia': '棕褐色',
      'theme.forest': '森林',
      'theme.ocean': '海洋',
      'theme.peach': '蜜桃',
      'theme.lavender': '薰衣草',
      'library.title': '书库',
      'library.pageTitle': 'EPUB 书库',
      'library.description': 'EPUB 书库 - 基于网页的 EPUB 阅读器',
      'library.information': '书库信息',
      'library.bookCount': '共 {count} 本书',
      'library.tagCount': '共 {count} 个标签',
      'library.annotations': '标注',
      'library.login': '登录',
      'library.theme': '主题',
      'library.searchPlaceholder': '按书名、作者或标签搜索…',
      'library.all': '全部',
      'library.noTag': '无标签',
      'library.top': '顶部',
      'library.shelf': '书架',
      'library.cover': '封面',
      'library.usernamePrompt': '请输入你的用户名：',
      'library.usernameSaved': '用户名已保存：{username}',
      'library.usernameCleared': '用户名已清除',
      'library.install': '安装',
      'library.installing': '正在安装应用…',
      'library.installSucceeded': '应用安装成功！',
      'library.installCancelled': '已取消安装',
      'library.loading': '正在加载书库',
      'library.empty': '书库中还没有书籍。',
      'library.loadError': '无法加载书库，请刷新后重试。',
      'footer.product': 'EPUB 书库',
      'footer.poweredBy': '由以下项目驱动',
      'version.updateAvailable': '有可用更新：v{version}',
      'errors.generic': '发生了错误。',
      'errors.network': '发生网络错误。'
    }
  };

  function normalizeLocale(value) {
    value = String(value || '').replace('_', '-').toLowerCase();
    if (value === 'zh' || value.indexOf('zh-cn') === 0 || value.indexOf('zh-sg') === 0) return 'zh-CN';
    return value === 'en' || value.indexOf('en-') === 0 ? 'en' : '';
  }

  function readCookie(root) {
    var cookie = '';
    var match;
    try { cookie = root.document && root.document.cookie; } catch (error) {}
    if (!cookie) return '';
    match = String(cookie).match(new RegExp('(?:^|;\\s*)' + STORAGE_KEY + '=([^;]*)'));
    if (!match) return '';
    try { return decodeURIComponent(match[1]); } catch (error) { return match[1]; }
  }

  function createRuntime(root, messages) {
    var locale = '';
    var initialized = false;
    var listeners = [];
    var pageMemoryLocale = '';

    function readStoredLocale() {
      var stored = '';
      try {
        stored = root.localStorage && root.localStorage.getItem(STORAGE_KEY);
      } catch (error) {}
      stored = normalizeLocale(stored);
      if (stored) return stored;

      try {
        stored = root.epubBrowserCache && root.epubBrowserCache[STORAGE_KEY];
      } catch (error2) {}
      stored = normalizeLocale(stored);
      if (stored) return stored;

      stored = normalizeLocale(readCookie(root));
      if (stored) return stored;
      return normalizeLocale(pageMemoryLocale);
    }

    function persistLocale(value) {
      var localStorageWorked = false;
      pageMemoryLocale = value;
      try {
        if (root.localStorage) {
          root.localStorage.setItem(STORAGE_KEY, value);
          localStorageWorked = true;
        }
      } catch (error) {}

      try {
        if (root.epubBrowserCache) root.epubBrowserCache[STORAGE_KEY] = value;
        if (root.epubBrowserCache) return;
      } catch (error2) {}

      if (localStorageWorked) return;
      try {
        if (root.document) root.document.cookie = STORAGE_KEY + '=' + encodeURIComponent(value) + '; path=/';
      } catch (error3) {}
    }

    function init() {
      var browser;
      if (initialized) return locale;
      initialized = true;
      browser = root.navigator && ((root.navigator.languages || [])[0] || root.navigator.language);
      locale = readStoredLocale() || normalizeLocale(browser) || 'en';
      applyLocaleToDocument();
      if (root.document && root.document.addEventListener) {
        root.document.addEventListener('DOMContentLoaded', function() {
          translateDocument();
        });
      }
      return locale;
    }

    function interpolate(template, params) {
      return String(template).replace(/\{([A-Za-z0-9_]+)\}/g, function(match, key) {
        return params && params[key] !== undefined ? String(params[key]) : match;
      });
    }

    function selectPlural(message, params) {
      var category = 'other';
      var count = params && params.count;
      if (typeof message === 'string') return message;
      if (!message || typeof message !== 'object') return message;
      try {
        if (root.Intl && root.Intl.PluralRules) category = new root.Intl.PluralRules(locale).select(count);
        else category = Number(count) === 1 ? 'one' : 'other';
      } catch (error) {
        category = Number(count) === 1 ? 'one' : 'other';
      }
      return message[category] !== undefined ? message[category] : message.other;
    }

    function t(key, params) {
      var selected;
      var fallback;
      init();
      selected = messages[locale] && messages[locale][key];
      fallback = messages.en && messages.en[key];
      if (selected === undefined) selected = fallback;
      selected = selectPlural(selected, params || {});
      if (selected === undefined) {
        if (root.console && root.console.warn) root.console.warn('Missing i18n key:', key);
        return key;
      }
      return interpolate(selected, params || {});
    }

    function formatDate(value, options) {
      var date = value instanceof Date ? value : new Date(value);
      function pad(number) { return number < 10 ? '0' + number : String(number); }
      init();
      if (isNaN(date.getTime())) return '';
      try {
        if (root.Intl && root.Intl.DateTimeFormat) return new root.Intl.DateTimeFormat(locale, options).format(date);
      } catch (error) {}
      return date.getUTCFullYear() + '-' + pad(date.getUTCMonth() + 1) + '-' + pad(date.getUTCDate());
    }

    function formatNumber(value, options) {
      init();
      try {
        if (root.Intl && root.Intl.NumberFormat) return new root.Intl.NumberFormat(locale, options).format(value);
      } catch (error) {}
      return String(value);
    }

    function translateDocument(scope) {
      var nodes;
      scope = scope || root.document;
      if (!scope || !scope.querySelectorAll) return;
      nodes = scope.querySelectorAll('[data-i18n], [data-i18n-placeholder], [data-i18n-title], [data-i18n-aria-label], [data-i18n-content]');
      Array.prototype.forEach.call(nodes, function(node) {
        var params = {};
        try {
          params = JSON.parse(node.getAttribute('data-i18n-params') || '{}');
        } catch (error) {}
        try {
          if (node.hasAttribute('data-i18n')) node.textContent = t(node.getAttribute('data-i18n'), params);
          ['placeholder', 'title', 'aria-label', 'content'].forEach(function(attribute) {
            var key = node.getAttribute('data-i18n-' + attribute);
            if (key) node.setAttribute(attribute, t(key, params));
          });
        } catch (error) {
          if (root.console && root.console.warn) root.console.warn('Unable to translate i18n node:', error);
        }
      });
    }

    function updateManifestLink() {
      var link;
      if (!root.document) return;
      if (root.document.querySelector) link = root.document.querySelector('#epubBrowserManifest');
      if (!link && root.document.createElement && root.document.head) {
        link = root.document.createElement('link');
        link.id = 'epubBrowserManifest';
        link.rel = 'manifest';
        root.document.head.appendChild(link);
      }
      if (link) link.href = '/assets/manifest.' + locale + '.json';
    }

    function applyLocaleToDocument() {
      var documentRoot = root.document && root.document.documentElement;
      if (documentRoot) documentRoot.lang = locale;
      updateManifestLink();
    }

    function notifyListeners() {
      listeners.slice().forEach(function(listener) {
        try {
          listener(locale);
        } catch (error) {
          if (root.console && root.console.warn) root.console.warn('I18n localechange listener failed:', error);
        }
      });
      try {
        if (root.dispatchEvent && root.CustomEvent) {
          root.dispatchEvent(new root.CustomEvent('localechange', { detail: { locale: locale } }));
        }
      } catch (error2) {}
    }

    function setLocale(value) {
      init();
      locale = normalizeLocale(value) || 'en';
      persistLocale(locale);
      applyLocaleToDocument();
      translateDocument();
      notifyListeners();
      return locale;
    }

    function onLocaleChange(listener) {
      if (typeof listener !== 'function') return function() {};
      listeners.push(listener);
      return function() {
        var index = listeners.indexOf(listener);
        if (index !== -1) listeners.splice(index, 1);
      };
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
