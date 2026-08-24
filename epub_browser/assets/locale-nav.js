(function(root, factory) {
  var api = factory();
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  } else {
    root.EpubLocaleNavigation = api;
    api.autoInit(root);
  }
})(typeof self !== 'undefined' ? self : this, function() {
  'use strict';

  var SUPPORTED_LOCALES = ['en', 'zh-CN', 'zh-TW', 'ko', 'ja'];

  function createLocaleNavigation(root) {
    var documentObject = root && root.document;
    var i18n = root && root.EpubBrowserI18n;
    if (!documentObject || !i18n) return null;
    var localeSelect = documentObject.getElementById('localeSelect');
    var localeToggle = documentObject.getElementById('localeToggle');
    var localeCurrentLabel = documentObject.getElementById('localeCurrentLabel');
    if (!localeSelect || !localeToggle || !localeCurrentLabel || localeToggle.dataset.localeNavBound === 'true') return null;
    localeToggle.dataset.localeNavBound = 'true';

    var localeMenu = documentObject.createElement('div');
    localeMenu.className = 'theme-menu locale-menu';
    localeMenu.setAttribute('id', 'localeMenu');
    localeMenu.setAttribute('role', 'menu');
    localeToggle.setAttribute('aria-controls', 'localeMenu');
    localeMenu.style.display = 'none';
    localeMenu.style.position = 'fixed';
    localeMenu.style.zIndex = '10000';
    documentObject.body.appendChild(localeMenu);
    var renderingLocaleMenu = false;

    function localeName(locale) {
      return i18n.t('locale.name.' + locale);
    }

    function menuIsOpen() {
      return localeMenu.style.display !== 'none';
    }

    function positionLocaleMenu() {
      var rect = localeToggle.getBoundingClientRect();
      localeMenu.style.top = (rect.bottom + 8) + 'px';
      localeMenu.style.right = (root.innerWidth - rect.right) + 'px';
    }

    function closeLocaleMenu(restoreFocus) {
      localeMenu.style.display = 'none';
      localeToggle.setAttribute('aria-expanded', 'false');
      if (restoreFocus) localeToggle.focus();
    }

    function menuItems() {
      return localeMenu.querySelectorAll('[role="menuitemradio"]');
    }

    function focusMenuItem(item) {
      Array.prototype.forEach.call(menuItems(), function(candidate) {
        candidate.tabIndex = candidate === item ? 0 : -1;
      });
      if (item) item.focus();
    }

    function renderLocaleMenu() {
      var current = i18n.getLocale();
      var restoreMenuFocus = menuIsOpen() && localeMenu.contains(documentObject.activeElement);
      renderingLocaleMenu = true;
      try {
        localeMenu.innerHTML = '';
      } finally {
        renderingLocaleMenu = false;
      }
      var selectedItem = null;
      SUPPORTED_LOCALES.forEach(function(locale) {
        var selected = locale === current;
        var item = documentObject.createElement('button');
        item.type = 'button';
        item.className = 'theme-menu-item locale-menu-item';
        item.setAttribute('role', 'menuitemradio');
        item.setAttribute('data-locale', locale);
        item.setAttribute('aria-checked', selected ? 'true' : 'false');
        item.tabIndex = selected ? 0 : -1;
        if (selected) selectedItem = item;
        var check = documentObject.createElement('i');
        check.className = selected ? 'fas fa-check' : 'fas fa-language';
        check.setAttribute('aria-hidden', 'true');
        item.appendChild(check);
        item.appendChild(documentObject.createTextNode(localeName(locale)));
        item.addEventListener('click', function() {
          localeSelect.value = locale;
          i18n.setLocale(locale);
          closeLocaleMenu(true);
        });
        localeMenu.appendChild(item);
      });
      localeCurrentLabel.textContent = localeName(current);
      localeMenu.setAttribute('aria-label', i18n.t('common.language'));
      if (restoreMenuFocus && selectedItem) focusMenuItem(selectedItem);
      return selectedItem;
    }

    function focusAdjacentItem(direction) {
      var items = menuItems();
      if (!items.length) return;
      var current = Array.prototype.indexOf.call(items, documentObject.activeElement);
      var next = current < 0 ? 0 : (current + direction + items.length) % items.length;
      focusMenuItem(items[next]);
    }

    function openLocaleMenu() {
      var selected = renderLocaleMenu();
      positionLocaleMenu();
      localeMenu.style.display = 'block';
      localeToggle.setAttribute('aria-expanded', 'true');
      if (selected) focusMenuItem(selected);
    }

    localeSelect.value = i18n.getLocale();
    localeSelect.addEventListener('change', function() {
      i18n.setLocale(localeSelect.value);
    });
    localeToggle.addEventListener('click', function(event) {
      event.stopPropagation();
      if (menuIsOpen()) closeLocaleMenu(false);
      else openLocaleMenu();
    });
    localeMenu.addEventListener('keydown', function(event) {
      if (event.key === 'ArrowDown' || event.key === 'ArrowRight') {
        event.preventDefault();
        focusAdjacentItem(1);
      } else if (event.key === 'ArrowUp' || event.key === 'ArrowLeft') {
        event.preventDefault();
        focusAdjacentItem(-1);
      } else if (event.key === 'Enter' || event.key === ' ') {
        if (localeMenu.contains(documentObject.activeElement)) {
          event.preventDefault();
          documentObject.activeElement.click();
        }
      } else if (event.key === 'Escape') {
        event.preventDefault();
        closeLocaleMenu(true);
      }
    });
    localeMenu.addEventListener('focusout', function(event) {
      if (renderingLocaleMenu) return;
      if (!localeMenu.contains(event.relatedTarget) && event.relatedTarget !== localeToggle) {
        closeLocaleMenu(false);
      }
    });
    documentObject.addEventListener('click', function(event) {
      if (!localeToggle.contains(event.target) && !localeMenu.contains(event.target)) closeLocaleMenu(false);
    });
    root.addEventListener('resize', function() {
      if (menuIsOpen()) positionLocaleMenu();
    });
    i18n.onLocaleChange(function() {
      localeSelect.value = i18n.getLocale();
      renderLocaleMenu();
    });
    renderLocaleMenu();
    return { close: closeLocaleMenu, menu: localeMenu, open: openLocaleMenu };
  }

  function autoInit(root) {
    if (!root || !root.document) return;
    if (root.document.readyState === 'loading') {
      root.document.addEventListener('DOMContentLoaded', function() {
        createLocaleNavigation(root);
      });
    } else {
      createLocaleNavigation(root);
    }
  }

  return {
    SUPPORTED_LOCALES: SUPPORTED_LOCALES,
    autoInit: autoInit,
    createLocaleNavigation: createLocaleNavigation
  };
});
