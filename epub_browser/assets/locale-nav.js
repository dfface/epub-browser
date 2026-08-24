(function(root) {
  'use strict';

  var SUPPORTED_LOCALES = ['en', 'zh-CN', 'zh-TW', 'ko', 'ja'];

  function init() {
    var documentObject = root.document;
    var i18n = root.EpubBrowserI18n;
    if (!documentObject || !i18n) return;
    var localeSelect = documentObject.getElementById('localeSelect');
    var localeToggle = documentObject.getElementById('localeToggle');
    var localeCurrentLabel = documentObject.getElementById('localeCurrentLabel');
    if (!localeSelect || !localeToggle || !localeCurrentLabel || localeToggle.dataset.localeNavBound === 'true') return;
    localeToggle.dataset.localeNavBound = 'true';

    var localeMenu = documentObject.createElement('div');
    localeMenu.className = 'theme-menu locale-menu';
    localeMenu.setAttribute('role', 'menu');
    localeMenu.style.display = 'none';
    localeMenu.style.position = 'fixed';
    localeMenu.style.zIndex = '10000';
    documentObject.body.appendChild(localeMenu);

    function localeName(locale) {
      return i18n.t('locale.name.' + locale);
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

    function renderLocaleMenu() {
      var current = i18n.getLocale();
      localeMenu.innerHTML = '';
      SUPPORTED_LOCALES.forEach(function(locale) {
        var item = documentObject.createElement('button');
        item.type = 'button';
        item.className = 'theme-menu-item locale-menu-item';
        item.setAttribute('role', 'menuitemradio');
        item.setAttribute('aria-checked', locale === current ? 'true' : 'false');
        var check = documentObject.createElement('i');
        check.className = locale === current ? 'fas fa-check' : 'fas fa-language';
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
    }

    function focusAdjacentItem(direction) {
      var items = localeMenu.querySelectorAll('[role="menuitemradio"]');
      if (!items.length) return;
      var current = Array.prototype.indexOf.call(items, documentObject.activeElement);
      var next = current < 0 ? 0 : (current + direction + items.length) % items.length;
      items[next].focus();
    }

    localeSelect.value = i18n.getLocale();
    localeSelect.addEventListener('change', function() {
      i18n.setLocale(localeSelect.value);
    });
    localeToggle.addEventListener('click', function(event) {
      event.stopPropagation();
      if (localeMenu.style.display === 'none') {
        renderLocaleMenu();
        positionLocaleMenu();
        localeMenu.style.display = 'block';
        localeToggle.setAttribute('aria-expanded', 'true');
        var selected = localeMenu.querySelector('[aria-checked="true"]');
        if (selected) selected.focus();
      } else {
        closeLocaleMenu(false);
      }
    });
    localeMenu.addEventListener('keydown', function(event) {
      if (event.key === 'ArrowDown' || event.key === 'ArrowRight') {
        event.preventDefault();
        focusAdjacentItem(1);
      } else if (event.key === 'ArrowUp' || event.key === 'ArrowLeft') {
        event.preventDefault();
        focusAdjacentItem(-1);
      } else if (event.key === 'Escape') {
        event.preventDefault();
        closeLocaleMenu(true);
      }
    });
    documentObject.addEventListener('click', function(event) {
      if (!localeToggle.contains(event.target) && !localeMenu.contains(event.target)) closeLocaleMenu(false);
    });
    root.addEventListener('resize', function() {
      if (localeMenu.style.display !== 'none') positionLocaleMenu();
    });
    i18n.onLocaleChange(function() {
      localeSelect.value = i18n.getLocale();
      renderLocaleMenu();
    });
    renderLocaleMenu();
  }

  if (root.document) {
    if (root.document.readyState === 'loading') root.document.addEventListener('DOMContentLoaded', init);
    else init();
  }
})(typeof window !== 'undefined' ? window : this);
