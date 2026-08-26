/* Server-only local dictionary and Wikimedia encyclopedia result dialog. */
(function(root) {
  'use strict';
  var activeController = null;
  var activeDialog = null;
  var outsideClickHandler = null;
  var preferredDictionaryStorageKey = 'epub-browser.dictionary-preference';

  function t(key) {
    var i18n = root.EpubBrowserI18n;
    return i18n && i18n.t ? i18n.t('dictionary.' + key) : key;
  }

  function close() {
    if (activeController) activeController.abort();
    activeController = null;
    if (outsideClickHandler) root.document.removeEventListener('click', outsideClickHandler);
    outsideClickHandler = null;
    if (activeDialog) activeDialog.remove();
    activeDialog = null;
  }

  function closeWhenClickedOutside(dialog) {
    root.setTimeout(function() {
      if (activeDialog !== dialog) return;
      outsideClickHandler = function(event) {
        if (!dialog.contains(event.target)) close();
      };
      root.document.addEventListener('click', outsideClickHandler);
    }, 0);
  }

  function element(tag, className, text) {
    var item = root.document.createElement(tag);
    if (className) item.className = className;
    if (text !== undefined && text !== null) item.textContent = text;
    return item;
  }

  function dictionaryOrigin() {
    var origin = root.location && typeof root.location.origin === 'string' ? root.location.origin : '';
    return /^https?:\/\//i.test(origin) ? origin : '';
  }

  function dictionaryAssetBaseUrl(bookId, dictionaryId, assetBasePath) {
    var encodedPath = String(assetBasePath || '').split('/').filter(Boolean).map(function(part) {
      return encodeURIComponent(part);
    }).join('/');
    return dictionaryOrigin() + '/api/books/' + encodeURIComponent(bookId) + '/dictionaries/'
      + encodeURIComponent(dictionaryId || '') + '/assets/' + (encodedPath ? encodedPath + '/' : '');
  }

  function dictionaryAssetUrl(bookId, dictionaryId, assetBasePath, reference) {
    return dictionaryAssetBaseUrl(bookId, dictionaryId, assetBasePath)
      + reference.split('/').map(function(part) { return encodeURIComponent(part); }).join('/');
  }

  function canonicalPackageResourceReference(value, allowRelative) {
    if (typeof value !== 'string') return null;
    try { value = decodeURIComponent(value).trim(); } catch (error) { return null; }
    if (/^(?:file|sound):\/\//i.test(value)) value = value.replace(/^[a-z]+:\/\//i, '');
    else if (!allowRelative || /^[a-z][a-z0-9+.-]*:/i.test(value) || /^[/#]/.test(value)) return null;
    value = value.split(/[?#]/, 1)[0];
    value = value.replace(/\\/g, '/').replace(/^\/+/, '');
    var parts = [];
    value.split('/').forEach(function(part) {
      if (!part || part === '.') return;
      if (part === '..') { parts.pop(); return; }
      parts.push(part);
    });
    return parts.length ? parts.join('/').toLowerCase() : null;
  }

  function resolveDictionaryPackageResources(source, entry, bookId, assetBasePath) {
    return source.replace(/\b(src|href)\s*=\s*(["'])(.*?)\2/gi, function(attribute, name, quote, value) {
      var reference = canonicalPackageResourceReference(value, true);
      var replacement = reference && dictionaryAssetUrl(bookId, entry.dictionary_id, assetBasePath, reference);
      return replacement ? name + '=' + quote + replacement + quote : attribute;
    });
  }

  function escapeHtml(value) {
    return String(value || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function stardictResourceUrl(bookId, dictionaryId, assetBasePath, reference) {
    var safeReference = canonicalPackageResourceReference(reference, true);
    return safeReference
      ? dictionaryAssetUrl(bookId, dictionaryId, assetBasePath, 'res/' + safeReference)
      : null;
  }

  function renderStarDictResourceList(value, entry, bookId, assetBasePath) {
    return String(value || '').split(/\r?\n/).map(function(line) {
      var separator = line.indexOf(':');
      if (separator < 1) return '';
      var kind = line.slice(0, separator).toLowerCase();
      var url = stardictResourceUrl(bookId, entry.dictionary_id, assetBasePath, line.slice(separator + 1));
      if (!url) return '';
      if (kind === 'img') return '<img src="' + escapeHtml(url) + '" alt="">';
      if (kind === 'snd') return '<audio controls src="' + escapeHtml(url) + '"></audio>';
      if (kind === 'vdo') return '<video controls src="' + escapeHtml(url) + '"></video>';
      return '<a href="' + escapeHtml(url) + '" download>' + escapeHtml(line.slice(separator + 1)) + '</a>';
    }).join('');
  }

  function renderXdxfResourceReferences(source, entry, bookId, assetBasePath) {
    return source.replace(/<rref\b([^>]*)>([\s\S]*?)<\/rref>/gi, function(original, attributes, reference) {
      var type = /\btype\s*=\s*(["'])(.*?)\1/i.exec(attributes || '');
      var url = stardictResourceUrl(bookId, entry.dictionary_id, assetBasePath, reference);
      if (!url) return original;
      var kind = type && type[2].toLowerCase();
      if (kind === 'image') return '<img src="' + escapeHtml(url) + '" alt="">';
      if (kind === 'sound') return '<audio controls src="' + escapeHtml(url) + '"></audio>';
      if (kind === 'video') return '<video controls src="' + escapeHtml(url) + '"></video>';
      return '<a href="' + escapeHtml(url) + '" download>' + escapeHtml(reference) + '</a>';
    });
  }

  function renderStarDictParts(source, entry, bookId, assetBasePath) {
    var parts;
    try { parts = JSON.parse(source); } catch (error) { return '<pre>' + escapeHtml(source) + '</pre>'; }
    if (!Array.isArray(parts)) return '<pre>' + escapeHtml(source) + '</pre>';
    return parts.map(function(part) {
      if (!part || typeof part.type !== 'string') return '';
      var type = part.type;
      var text = typeof part.text === 'string' ? part.text : '';
      if (type === 'h') return resolveDictionaryPackageResources(text, entry, bookId, assetBasePath);
      if (type === 'g' || type === 'k') return resolveDictionaryPackageResources(text, entry, bookId, assetBasePath);
      if (type === 'x') return renderXdxfResourceReferences(
        resolveDictionaryPackageResources(text, entry, bookId, assetBasePath), entry, bookId, assetBasePath
      );
      if (type === 'r') return renderStarDictResourceList(text, entry, bookId, assetBasePath);
      if (type === 't' || type === 'y') return '<div class="stardict-phonetic">' + escapeHtml(text) + '</div>';
      if (type === 'W') return '<audio controls src="data:audio/wav;base64,' + escapeHtml(part.data) + '"></audio>';
      if (type === 'P') return '<img src="data:image/*;base64,' + escapeHtml(part.data) + '" alt="">';
      if (type === 'X') return '<a download href="data:application/octet-stream;base64,' + escapeHtml(part.data) + '">attachment</a>';
      return '<pre>' + escapeHtml(text) + '</pre>';
    }).join('');
  }

  function definitionElement(entry, bookId, assetBasePath, allowScripts) {
    var definition = element('iframe', 'dictionary-entry-document');
    var source = String(entry.definition || '');
    var format = String(entry.definition_format || '');
    var isPackagedHtml = format === 'mdict' || format === 'stardict:h';
    var isStarDictParts = format === 'stardict:parts';
    var isPlainText = /^stardict:[ml]+$/.test(format)
      || (format === 'mdict' && !/<[A-Za-z!/][^>]*>/.test(source));
    if (isPackagedHtml) source = resolveDictionaryPackageResources(source, entry, bookId, assetBasePath);
    if (isStarDictParts) source = renderStarDictParts(source, entry, bookId, assetBasePath);
    var origin = dictionaryOrigin() || "'self'";
    var scriptSource = allowScripts && (isPackagedHtml || isStarDictParts) ? origin + " 'unsafe-inline'" : "'none'";
    definition.sandbox = allowScripts && (isPackagedHtml || isStarDictParts)
      ? 'allow-same-origin allow-scripts' : 'allow-same-origin';
    definition.referrerPolicy = 'no-referrer';
    definition.setAttribute('title', entry.headword || '');
    definition.srcdoc = '<!doctype html><meta http-equiv="Content-Security-Policy" '
      + 'content="default-src \'none\'; base-uri ' + origin + '; connect-src \'none\'; form-action \'none\'; '
      + 'frame-src \'none\'; object-src \'none\'; script-src ' + scriptSource + '; style-src ' + origin + ' \'unsafe-inline\'; '
      + 'img-src ' + origin + ' data:; media-src ' + origin + ' data:; font-src ' + origin + ' data:">'
      + '<style>body{margin:0;color:inherit;font:14px/1.62 system-ui,sans-serif;overflow-wrap:anywhere}'
      + 'pre{margin:0;white-space:pre-wrap;font:inherit}img{max-width:100%;height:auto}'
      + 'table{max-width:100%;border-collapse:collapse}td{vertical-align:top}</style>'
      + (isPlainText ? '<pre>' + source.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;') + '</pre>' : source);
    return definition;
  }

  function readJson(response) {
    return response.json().catch(function() { return {}; }).then(function(body) {
      if (!response.ok) throw new Error(body.code || 'unavailable');
      return body;
    });
  }

  function readPreferredDictionary() {
    try { return root.localStorage.getItem(preferredDictionaryStorageKey); } catch (error) { return null; }
  }

  function savePreferredDictionary(dictionaryId) {
    try { root.localStorage.setItem(preferredDictionaryStorageKey, dictionaryId); } catch (error) { /* Optional preference. */ }
  }

  function dictionaryChoiceId(choices, defaultDictionaryId) {
    var preferredId = readPreferredDictionary();
    if (preferredId && choices.some(function(choice) { return choice.id === preferredId; })) {
      return preferredId;
    }
    if (defaultDictionaryId && choices.some(function(choice) { return choice.id === defaultDictionaryId; })) {
      return defaultDictionaryId;
    }
    return choices[0].id;
  }

  function renderDictionaryResult(content, data, bookId) {
    var result = element('div', 'dictionary-results');
    if (!data.found) {
      result.textContent = t('notFound');
    } else {
      (data.entries || []).forEach(function(entry) {
        var item = element('article', 'dictionary-entry');
        item.appendChild(element('strong', '', entry.headword));
        entry.dictionary_id = data.dictionary && data.dictionary.id;
        item.appendChild(definitionElement(entry, bookId, data.asset_base_path, Boolean(data.allow_scripts)));
        result.appendChild(item);
      });
    }
    var previous = content.querySelector('.dictionary-results');
    if (previous) previous.remove();
    content.appendChild(result);
    if (content.parentNode) positionDialog(content.parentNode, content.parentNode._epubAnchor);
  }

  function positionDialog(dialog, anchor) {
    var margin = 12;
    var width = dialog.offsetWidth || 400;
    var height = dialog.offsetHeight || 260;
    var hasAnchor = anchor && typeof anchor.left === 'number';
    var left = hasAnchor ? anchor.left + ((anchor.width || 0) - width) / 2 : (root.innerWidth - width) / 2;
    var top = hasAnchor ? anchor.bottom + margin : (root.innerHeight - height) / 2;
    left = Math.max(margin, Math.min(left, root.innerWidth - width - margin));
    if (hasAnchor && top + height > root.innerHeight - margin) top = anchor.top - height - margin;
    top = Math.max(margin, Math.min(top, root.innerHeight - height - margin));
    dialog.style.left = Math.round(left) + 'px';
    dialog.style.top = Math.round(top) + 'px';
  }

  function show(kind, text, anchor) {
    close();
    var dialog = element('section', 'dictionary-dialog');
    dialog.setAttribute('role', 'dialog');
    dialog.setAttribute('aria-live', 'polite');
    dialog.setAttribute('aria-label', t(kind === 'dictionary' ? 'title' : 'encyclopediaTitle'));
    var header = element('header', 'dictionary-dialog-header');
    header.appendChild(element('strong', '', t(kind === 'dictionary' ? 'title' : 'encyclopediaTitle')));
    var button = element('button', 'dictionary-dialog-close', '×');
    button.type = 'button'; button.setAttribute('aria-label', t('close'));
    button.addEventListener('click', close); header.appendChild(button);
    dialog.appendChild(header);
    var content = element('div', 'dictionary-dialog-content', t('loading'));
    dialog.appendChild(content);
    root.document.body.appendChild(dialog);
    dialog._epubAnchor = anchor;
    positionDialog(dialog, anchor);
    activeDialog = dialog;
    closeWhenClickedOutside(dialog);
    button.focus();

    var article = root.document.getElementById('eb-content');
    var bookId = article && article.getAttribute('data-book-hash');
    if (!bookId || !root.EpubBrowserAuth || !root.EpubBrowserAuth.fetch) {
      content.textContent = t('unavailable'); positionDialog(dialog, dialog._epubAnchor); return;
    }
    if (kind === 'dictionary') {
      activeController = new AbortController();
      root.EpubBrowserAuth.fetch('/api/books/' + encodeURIComponent(bookId) + '/dictionaries', {
        signal: activeController.signal
      }).then(readJson).then(function(data) {
        if (activeDialog !== dialog) return;
        var choices = data.dictionaries || [];
        content.textContent = '';
        if (!choices.length) { content.textContent = t('notConfigured'); positionDialog(dialog, dialog._epubAnchor); return; }
        var dictionaryId = dictionaryChoiceId(choices, data.default_dictionary_id);
        var select = null;
        if (choices.length > 1) {
          var picker = element('div', 'dictionary-picker');
          picker.appendChild(element('span', '', t('choose')));
          select = element('select', 'dictionary-picker-select');
          select.setAttribute('aria-label', t('choose'));
          choices.forEach(function(choice) {
            var option = element('option', '', choice.display_name);
            option.value = choice.id;
            select.appendChild(option);
          });
          select.value = dictionaryId;
          picker.appendChild(select);
          content.appendChild(picker);
          positionDialog(dialog, dialog._epubAnchor);
        }
        function lookup() {
          if (activeController) activeController.abort();
          activeController = new AbortController();
          root.EpubBrowserAuth.fetch('/api/books/' + encodeURIComponent(bookId) + '/dictionary/lookup', {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({text: text, dictionary_id: select ? select.value : dictionaryId}), signal: activeController.signal
          }).then(readJson).then(function(result) {
            if (activeDialog === dialog) renderDictionaryResult(content, result, bookId);
          }).catch(function(error) {
            if (error.name !== 'AbortError' && activeDialog === dialog) {
              renderDictionaryResult(content, {found: false}, bookId);
            }
          });
        }
        if (select) select.addEventListener('change', function() {
          savePreferredDictionary(select.value);
          lookup();
        });
        lookup();
      }).catch(function(error) {
        if (error.name !== 'AbortError' && activeDialog === dialog) {
          content.textContent = t('unavailable'); positionDialog(dialog, dialog._epubAnchor);
        }
      });
      return;
    }

    activeController = new AbortController();
    root.EpubBrowserAuth.fetch('/api/books/' + encodeURIComponent(bookId) + '/' + kind + '/lookup', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({text: text}), signal: activeController.signal
    }).then(function(response) {
      return readJson(response);
    }).then(function(data) {
      if (activeDialog !== dialog) return;
      content.textContent = '';
      if (!data.found) { content.textContent = t('notFound'); positionDialog(dialog, dialog._epubAnchor); return; }
      if (kind !== 'dictionary') {
        content.appendChild(element('strong', '', data.title || text));
        if (data.description) content.appendChild(element('p', 'dictionary-source', data.description));
        if (data.extract) content.appendChild(element('p', '', data.extract));
        if (data.source_url) {
          var link = element('a', 'dictionary-source-link', t('source'));
          link.href = data.source_url; link.target = '_blank'; link.rel = 'noopener noreferrer';
          content.appendChild(link);
        }
        content.appendChild(element('small', 'dictionary-attribution', data.attribution || 'Wikipedia · CC BY-SA 4.0'));
      }
      positionDialog(dialog, dialog._epubAnchor);
    }).catch(function(error) {
      if (error.name === 'AbortError' || activeDialog !== dialog) return;
      content.textContent = t('unavailable');
      positionDialog(dialog, dialog._epubAnchor);
    });
  }

  root.document.addEventListener('keydown', function(event) { if (event.key === 'Escape') close(); });
  root.EpubBrowserDictionary = { open: show, close: close };
})(window);
