/* Server-only local dictionary and Wikimedia encyclopedia result dialog. */
(function(root) {
  'use strict';
  var activeController = null;
  var activeDialog = null;
  var outsideClickHandler = null;

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

  // Dictionary definitions are imported as plain text: never interpret source
  // HTML.  This deliberately small Markdown subset retains useful typography
  // (including the numbered senses often written as `1`) without giving a
  // third-party dictionary executable markup or script capabilities.
  function appendInlineMarkdown(parent, source) {
    var text = String(source || '');
    var token = /\*\*([^*\n]+)\*\*|__([^_\n]+)__|`([^`\n]+)`|\*([^*\n]+)\*|_([^_\n]+)_/g;
    var index = 0;
    text.replace(token, function(match, boldA, boldB, code, italicA, italicB, offset) {
      if (offset > index) parent.appendChild(root.document.createTextNode(text.slice(index, offset)));
      if (boldA || boldB) parent.appendChild(element('strong', '', boldA || boldB));
      else if (code) parent.appendChild(element('code', '', code));
      else parent.appendChild(element('em', '', italicA || italicB));
      index = offset + match.length;
      return match;
    });
    if (index < text.length) parent.appendChild(root.document.createTextNode(text.slice(index)));
  }

  function definitionElement(source) {
    var definition = element('p');
    appendInlineMarkdown(definition, source);
    return definition;
  }

  function readJson(response) {
    return response.json().catch(function() { return {}; }).then(function(body) {
      if (!response.ok) throw new Error(body.code || 'unavailable');
      return body;
    });
  }

  function appendMedia(item, entry, bookId) {
    (entry.media || []).forEach(function(media) {
      if (!media || !media.id || (media.kind !== 'image' && media.kind !== 'audio')) return;
      var source = '/api/books/' + encodeURIComponent(bookId) + '/dictionaries/'
        + encodeURIComponent(entry.dictionary_id || '') + '/resources/' + encodeURIComponent(media.id);
      if (media.kind === 'image') {
        var image = element('img', 'dictionary-entry-image');
        image.src = source;
        image.loading = 'lazy';
        image.alt = entry.headword || '';
        item.appendChild(image);
      } else {
        var audio = element('audio', 'dictionary-entry-audio');
        audio.src = source;
        audio.controls = true;
        audio.preload = 'metadata';
        item.appendChild(audio);
      }
    });
  }

  function renderDictionaryResult(content, data, bookId) {
    var result = element('div', 'dictionary-results');
    if (!data.found) {
      result.textContent = t('notFound');
    } else {
      (data.entries || []).forEach(function(entry) {
        var item = element('article', 'dictionary-entry');
        item.appendChild(element('strong', '', entry.headword));
        item.appendChild(definitionElement(entry.definition));
        entry.dictionary_id = data.dictionary && data.dictionary.id;
        appendMedia(item, entry, bookId);
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
        var dictionaryId = choices[0].id;
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
        if (select) select.addEventListener('change', lookup);
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
