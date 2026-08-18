(function(root, factory) {
  var exported = factory();
  if (typeof module === 'object' && module.exports) module.exports = exported;
  if (root && root.document) root.EpubBrowserI18n = exported.createRuntime(root, exported.dictionaries);
})(typeof window !== 'undefined' ? window : (typeof globalThis !== 'undefined' ? globalThis : this), function() {
  'use strict';

  var STORAGE_KEY = 'epub_browser_locale';
  var dictionaries = {
    en: {
      'common.version': 'Version {version}'
    },
    'zh-CN': {
      'common.version': '版本 {version}'
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
