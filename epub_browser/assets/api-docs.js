(function(root, factory) {
  var api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else api.autoInit(root);
})(typeof window !== 'undefined' ? window : (typeof globalThis !== 'undefined' ? globalThis : this), function() {
  'use strict';

  function normalizeQuery(value) {
    return String(value || '').trim().toLowerCase();
  }

  function matchesEndpoint(searchable, query) {
    query = normalizeQuery(query);
    return !query || String(searchable || '').toLowerCase().indexOf(query) !== -1;
  }

  function copyText(root, value) {
    var documentObject = root.document;
    if (root.navigator && root.navigator.clipboard && root.navigator.clipboard.writeText) {
      return root.navigator.clipboard.writeText(value);
    }
    return new Promise(function(resolve, reject) {
      var field = documentObject.createElement('textarea');
      field.value = value;
      field.setAttribute('readonly', '');
      field.style.position = 'fixed';
      field.style.opacity = '0';
      documentObject.body.appendChild(field);
      field.select();
      try {
        if (!documentObject.execCommand || !documentObject.execCommand('copy')) throw new Error('copy_failed');
        resolve();
      } catch (error) {
        reject(error);
      } finally {
        documentObject.body.removeChild(field);
      }
    });
  }

  function createAPIDocs(root) {
    var documentObject = root && root.document;
    var i18n = root && root.EpubBrowserI18n;
    var search;
    var endpoints;
    var groups;
    var resultCount;
    var emptyState;
    var groupLinks;
    var copyButton;
    var copyStatus;
    var example;
    if (!documentObject || !i18n) return null;
    i18n.init();
    i18n.translateDocument();
    search = documentObject.getElementById('apiEndpointSearch');
    endpoints = Array.prototype.slice.call(documentObject.querySelectorAll('[data-api-endpoint]'));
    groups = Array.prototype.slice.call(documentObject.querySelectorAll('[data-api-group]'));
    groupLinks = Array.prototype.slice.call(documentObject.querySelectorAll('[data-api-group-link]'));
    resultCount = documentObject.getElementById('apiResultCount');
    emptyState = documentObject.getElementById('apiEmptyState');
    copyButton = documentObject.getElementById('apiCopyExample');
    copyStatus = documentObject.getElementById('apiCopyStatus');
    example = documentObject.getElementById('apiExampleCode');

    function setLocalizedText(node, key, params) {
      if (node) node.textContent = key ? i18n.t(key, params) : '';
    }

    function setPlainText(node, value) {
      if (node) node.textContent = String(value == null ? '' : value);
    }

    function setCopyStatus(key) {
      setLocalizedText(copyStatus, key);
    }

    function filter() {
      var query = normalizeQuery(search && search.value);
      var visible = 0;
      endpoints.forEach(function(endpoint) {
        var matches = matchesEndpoint(endpoint.getAttribute('data-api-search'), query);
        endpoint.hidden = !matches;
        if (matches) visible += 1;
      });
      groups.forEach(function(group) {
        var groupVisible = group.querySelectorAll('[data-api-endpoint]:not([hidden])').length;
        var countNode = group.querySelector('[data-api-group-count]');
        group.setAttribute('data-api-visible-count', String(groupVisible));
        group.hidden = groupVisible === 0;
        setLocalizedText(countNode, 'apiDocs.endpointCount', { count: groupVisible });
      });
      groupLinks.forEach(function(link) {
        var group = documentObject.querySelector('[data-api-group="' + link.getAttribute('data-api-group-link') + '"]');
        var badge = link.querySelector('strong');
        link.hidden = !group || group.hidden;
        if (badge && group) setPlainText(badge, group.getAttribute('data-api-visible-count'));
      });
      if (resultCount) resultCount.textContent = i18n.t('apiDocs.results', { count: visible });
      if (emptyState) emptyState.hidden = visible !== 0;
      return visible;
    }

    if (search) search.addEventListener('input', filter);
    documentObject.addEventListener('keydown', function(event) {
      var target = event.target;
      if (event.key !== '/' || event.metaKey || event.ctrlKey || event.altKey) return;
      if (target && /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName)) return;
      event.preventDefault();
      if (search) search.focus();
    });
    if (copyButton && example) {
      copyButton.addEventListener('click', function() {
        copyButton.disabled = true;
        copyText(root, example.textContent).then(function() {
          setCopyStatus('apiDocs.copied');
        }, function() {
          setCopyStatus('apiDocs.copyFailed');
        }).then(function() {
          copyButton.disabled = false;
        });
      });
    }
    i18n.onLocaleChange(filter);
    filter();
    return { filter: filter };
  }

  function autoInit(root) {
    if (!root || !root.document) return;
    if (root.document.readyState === 'loading') {
      root.document.addEventListener('DOMContentLoaded', function() { createAPIDocs(root); });
    } else {
      createAPIDocs(root);
    }
  }

  return {
    autoInit: autoInit,
    copyText: copyText,
    createAPIDocs: createAPIDocs,
    matchesEndpoint: matchesEndpoint,
    normalizeQuery: normalizeQuery
  };
});
