(function (root, factory) {
  var store = {};
  var api = factory(root, store);
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (root && root.document) root.EpubBrowserI18n = api;
})(typeof window !== 'undefined' ? window : (typeof globalThis !== 'undefined' ? globalThis : this), function (root, messages) {
  'use strict';

  var STORAGE_KEY = 'epub_browser_locale';

  function publicPath(basePath, path) {
    var base = basePath || '/';
    var value = path || '/';
    if (/^(?:[a-z][a-z0-9+.-]*:)?\/\//i.test(value) || /^(?:data|mailto|tel):/i.test(value)) return value;
    if (base.charAt(0) !== '/') base = '/' + base;
    if (base.charAt(base.length - 1) !== '/') base += '/';
    if (base !== '/' && value.indexOf(base) === 0) return value;
    if (value.charAt(0) === '/') return base.replace(/\/$/, '') + value;
    return base + value;
  }

  root.EpubBrowserURL = root.EpubBrowserURL || {};
  root.EpubBrowserURL.publicPath = function (path) {
    return publicPath(root.EpubBrowserBasePath || '/', path);
  };

  function normalizeLocale(value) {
    value = String(value || '').replace('_', '-').toLowerCase();
    if (value === 'zh' || value.indexOf('zh-cn') === 0 || value.indexOf('zh-sg') === 0) return 'zh-CN';
    if (value.indexOf('zh-tw') === 0 || value.indexOf('zh-hk') === 0 || value.indexOf('zh-mo') === 0) return 'zh-TW';
    if (value === 'ko' || value.indexOf('ko-') === 0) return 'ko';
    if (value === 'ja' || value.indexOf('ja-') === 0) return 'ja';
    if (value === 'en' || value.indexOf('en-') === 0) return 'en';
    if (value === 'pt' || value.indexOf('pt-') === 0) return 'pt-BR';
    var base = value.split('-')[0];
    return ['es', 'de', 'fr', 'ru', 'it', 'ar', 'id', 'hi', 'vi', 'th', 'ms'].indexOf(base) >= 0 ? base : '';
  }

  function readCookie() {
    var cookie = '';
    try { cookie = root.document && root.document.cookie; } catch (error) {}
    if (!cookie) return '';
    var match = String(cookie).match(new RegExp('(?:^|;\\s*)' + STORAGE_KEY + '=([^;]*)'));
    if (!match) return '';
    try { return decodeURIComponent(match[1]); } catch (error) { return match[1]; }
  }

  // Build an isolated runtime backed by the given locale map. The shared `store`
  // (passed by the module wrapper) is used for the browser runtime so inline and
  // on-demand packs land together; tests pass their own map.
  function createRuntime(root, messages) {
    var dicts = messages || {};

    var locale = '';
    var initialized = false;
    var loading = {};
    var listeners = [];
    var pageMemoryLocale = '';

    function registerDictionary(code, dict) {
      if (!code || !dict) return;
      if (dicts[code]) {
        Object.keys(dict).forEach(function (key) {
          if (Object.prototype.hasOwnProperty.call(dict, key)) dicts[code][key] = dict[key];
        });
      } else {
        dicts[code] = dict;
      }
    }

    var manifestPromise = null;

    function loadManifest() {
      if (manifestPromise) return manifestPromise;
      var url = publicPath(root.EpubBrowserBasePath || '/', '/assets/i18n-manifest.json');
      if (typeof root.fetch !== 'function') return Promise.resolve(null);
      manifestPromise = root.fetch(url, { credentials: 'same-origin' })
        .then(function (response) {
          if (!response.ok) throw new Error('i18n manifest load failed');
          return response.json();
        })
        .catch(function () { return null; });
      return manifestPromise;
    }

    function loadLocale(code) {
      if (!code || dicts[code] || loading[code]) return loading[code] || Promise.resolve();
      var fallbackUrl = publicPath(
        root.EpubBrowserBasePath || '/',
        '/assets/i18n/' + encodeURIComponent(code) + '.json'
      );
      if (typeof root.fetch !== 'function') return Promise.resolve(null);
      var urlPromise = loadManifest().then(function (manifest) {
        var url = manifest && manifest.locales && manifest.locales[code];
        return url || fallbackUrl;
      }).catch(function () { return fallbackUrl; });
      function fetchJson(url) {
        return root.fetch(url, { credentials: 'same-origin' })
          .then(function (response) {
            if (!response.ok) throw new Error('i18n load failed: ' + code);
            return response.json();
          })
          .then(function (dict) {
            registerDictionary(code, dict);
            return dict;
          });
      }
      loading[code] = urlPromise
        .then(function (url) {
          return fetchJson(url).catch(function (error) {
            if (url === fallbackUrl) throw error;
            return fetchJson(fallbackUrl);
          });
        })
        .then(function (dict) { loading[code] = null; return dict; })
        .catch(function (error) {
          loading[code] = null;
          if (root.console && root.console.warn) root.console.warn(error);
          return null;
        });
      return loading[code];
    }

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
      stored = normalizeLocale(readCookie());
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
      if (initialized) return locale;
      initialized = true;
      var browser = root.navigator && ((root.navigator.languages || [])[0] || root.navigator.language);
      locale = readStoredLocale() || normalizeLocale(browser) || 'en';
      applyLocaleToDocument();
      var pending = [];
      if (!dicts.en) pending.push(loadLocale('en'));
      if (locale !== 'en' && !dicts[locale]) pending.push(loadLocale(locale));
      function reveal() {
        var docEl = root.document && root.document.documentElement;
        if (docEl) {
          docEl.classList.remove('i18n-boot');
          docEl.classList.add('i18n-ready');
        }
      }

      function afterLoad() {
        function finish() {
          translateDocument();
          // Notify locale-change listeners once the initial dictionaries are
          // ready, just like setLocale does. Listeners that render content via
          // t() (rather than data-i18n attributes) otherwise run before the
          // dictionary is loaded and never get a second chance to re-render.
          notifyListeners();
          reveal();
        }
        if (root.document && root.document.readyState === 'loading') {
          root.document.addEventListener('DOMContentLoaded', finish);
        } else {
          finish();
        }
      }
      if (pending.length) Promise.all(pending).then(afterLoad, afterLoad);
      else afterLoad();
      return locale;
    }

    function interpolate(template, params) {
      return String(template).replace(/\{([A-Za-z0-9_]+)\}/g, function (match, key) {
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
      selected = dicts[locale] && dicts[locale][key];
      fallback = dicts.en && dicts.en[key];
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
      nodes = scope.querySelectorAll('[data-i18n], [data-i18n-placeholder], [data-i18n-title], [data-i18n-aria-label], [data-i18n-content], [data-i18n-data-tip]');
      Array.prototype.forEach.call(nodes, function (node) {
        var params = {};
        try {
          params = JSON.parse(node.getAttribute('data-i18n-params') || '{}');
        } catch (error) {}
        try {
          if (node.hasAttribute('data-i18n')) {
            var strongParam = node.getAttribute('data-i18n-strong-param');
            var ownerDocument = node.ownerDocument || root.document;
            if (
              strongParam
              && Object.prototype.hasOwnProperty.call(params, strongParam)
              && ownerDocument
              && ownerDocument.createElement
              && ownerDocument.createTextNode
              && node.appendChild
            ) {
              var marker = '';
              var richParams = {};
              Object.keys(params).forEach(function (key) {
                richParams[key] = key === strongParam ? marker : params[key];
              });
              var translated = t(node.getAttribute('data-i18n'), richParams);
              var parts = translated.split(marker);
              if (parts.length === 2) {
                var emphasis = ownerDocument.createElement('strong');
                emphasis.textContent = String(params[strongParam]);
                node.textContent = '';
                if (parts[0]) node.appendChild(ownerDocument.createTextNode(parts[0]));
                node.appendChild(emphasis);
                if (parts[1]) node.appendChild(ownerDocument.createTextNode(parts[1]));
              } else {
                node.textContent = t(node.getAttribute('data-i18n'), params);
              }
            } else {
              node.textContent = t(node.getAttribute('data-i18n'), params);
            }
          }
          ['placeholder', 'title', 'aria-label', 'content', 'data-tip'].forEach(function (attribute) {
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
      if (root.EpubBrowserDisableManifest) return;
      if (!root.document) return;
      if (root.document.querySelector) link = root.document.querySelector('#epubBrowserManifest');
      if (!link && root.document.createElement && root.document.head) {
        link = root.document.createElement('link');
        link.id = 'epubBrowserManifest';
        link.rel = 'manifest';
        root.document.head.appendChild(link);
      }
      if (link) link.href = root.EpubBrowserURL.publicPath('/assets/manifest.' + locale + '.json');
    }

    function applyLocaleToDocument() {
      var documentRoot = root.document && root.document.documentElement;
      if (documentRoot) {
        documentRoot.lang = locale;
        documentRoot.dir = locale === 'ar' ? 'rtl' : 'ltr';
      }
      updateManifestLink();
    }

    function notifyListeners() {
      listeners.slice().forEach(function (listener) {
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
      function finish() {
        translateDocument();
        notifyListeners();
      }
      if (dicts[locale]) finish();
      else loadLocale(locale).then(finish, finish);
      return locale;
    }

    function onLocaleChange(listener) {
      if (typeof listener !== 'function') return function () {};
      listeners.push(listener);
      return function () {
        var index = listeners.indexOf(listener);
        if (index !== -1) listeners.splice(index, 1);
      };
    }

    return {
      init: init,
      t: t,
      getLocale: function () { return init(); },
      setLocale: setLocale,
      translateDocument: translateDocument,
      formatDate: formatDate,
      formatNumber: formatNumber,
      onLocaleChange: onLocaleChange,
      registerDictionary: registerDictionary,
      loadLocale: loadLocale,
      dictionaries: dicts,
      publicPath: publicPath,
    };
  }

  var defaultApi = createRuntime(root, messages);
  defaultApi.createRuntime = createRuntime;
  return defaultApi;
});
