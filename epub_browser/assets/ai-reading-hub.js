(function(root) {
  'use strict';
  if (!root || !root.document) return;

  var state = { modal: null, container: null, close: null, back: null, opener: null, scrollY: 0, books: [], bookId: '', contextualBookId: '', language: '', version: 0, chapterIndicators: {}, chapterIndicatorRequests: {} };
  function t(key, params) { var i = root.EpubBrowserI18n; return i && i.t ? i.t(key, params) : key; }
  function path(value) { return root.EpubBrowserURL ? root.EpubBrowserURL.publicPath(value) : value; }
  var supportedLanguages = ['en', 'zh-CN', 'zh-TW', 'ko', 'ja', 'es', 'de', 'fr', 'ru', 'it', 'pt-BR', 'ar', 'id', 'hi', 'vi', 'th', 'ms'];
  function locale() { var value = root.EpubBrowserI18n && root.EpubBrowserI18n.getLocale ? root.EpubBrowserI18n.getLocale() : document.documentElement.lang; return supportedLanguages.indexOf(value) >= 0 ? value : 'en'; }
  function el(tag, className, text) { var node = document.createElement(tag); if (className) node.className = className; if (text !== undefined) node.textContent = text; return node; }
  function clear(node) { while (node.firstChild) node.removeChild(node.firstChild); }
  function request(url, options) {
    if (!root.EpubBrowserAuth || !root.EpubBrowserAuth.fetch) return Promise.reject(new Error('auth'));
    return root.EpubBrowserAuth.fetch(url, options).then(function(response) {
      return response.json().catch(function() { return {}; }).then(function(data) {
        if (!response.ok) throw new Error(data.code || 'request_failed');
        return data;
      });
    });
  }
  function resultCount(book) { return (book.results || []).length; }
  function resultTitle(result) { return result && result.content && result.content.quick && result.content.quick.title || t('ai.chapterRead'); }
  function resultSummary(result) { return result && result.content && result.content.quick && result.content.quick.summary || ''; }
  function chapterLabel(result) {
    var index = Number(result && result.chapter_index);
    if (!Number.isInteger(index) || index < 0) return '';
    var label = t('ai.libraryChapter', { number: index });
    return result.chapter_title ? label + ' · ' + result.chapter_title : label;
  }
  function bookVisual(book) {
    if (book && book.cover) {
      var cover = el('img', 'ai-reading-book-cover');
      cover.src = path(book.cover); cover.alt = '';
      cover.addEventListener('error', function() {
        var fallback = el('span', 'ai-reading-book-icon'); var icon = el('i', 'fas fa-wand-magic-sparkles');
        icon.setAttribute('aria-hidden', 'true'); fallback.appendChild(icon); cover.replaceWith(fallback);
      });
      return cover;
    }
    var icon = el('span', 'ai-reading-book-icon'); icon.appendChild(el('i', 'fas fa-wand-magic-sparkles')); icon.querySelector('i').setAttribute('aria-hidden', 'true'); return icon;
  }
  function resultHref(book, result) {
    if (result.scope === 'chapter' && Number.isInteger(Number(result.chapter_index))) return path('/book/' + encodeURIComponent(book.book_id) + '/chapter_' + Number(result.chapter_index) + '.html?ai_result=' + encodeURIComponent(result.id));
    return path('/book/' + encodeURIComponent(book.book_id) + '/');
  }
  function resultLanguage(result) { return result && supportedLanguages.indexOf(result.language) >= 0 ? result.language : 'en'; }
  function visibleResults(book) { return (book.results || []).filter(function(result) { return !state.language || resultLanguage(result) === state.language; }); }
  function resultTimestamp(result) {
    if (!result || !result.created_at) return 0;
    var raw = String(result.created_at).replace(' ', 'T');
    if (!/(?:Z|[+-]\d{2}:?\d{2})$/i.test(raw)) raw += 'Z';
    var timestamp = Date.parse(raw);
    return isNaN(timestamp) ? 0 : timestamp;
  }
  function resultDate(result) {
    if (!result || !result.created_at) return '';
    var parsed = new Date(resultTimestamp(result));
    if (isNaN(parsed.getTime())) return String(result.created_at);
    try { return new Intl.DateTimeFormat(locale(), { dateStyle: 'medium', timeStyle: 'short' }).format(parsed); } catch (_error) { return String(result.created_at); }
  }
  function resultDetails(result) {
    var fields = [
      t('ai.libraryGeneratedAt') + ': ' + resultDate(result),
      t('ai.libraryLanguage') + ': ' + t('locale.name.' + resultLanguage(result)),
      t('ai.libraryTemplateVersion') + ': v' + Number(result.template_version || 0),
      t('ai.libraryConfigVersion') + ': ' + Number(result.config_revision || 0),
    ];
    return fields.join(' · ');
  }
  function resultGroups(book) {
    var groups = {};
    visibleResults(book).forEach(function(result) {
      var key = result.scope + ':' + (result.scope === 'chapter' ? Number(result.chapter_index) : 'book');
      if (!groups[key]) groups[key] = { key: key, result: result, results: [] };
      groups[key].results.push(result);
    });
    return Object.keys(groups).map(function(key) {
      var group = groups[key];
      group.results.sort(function(left, right) {
        var byDate = resultTimestamp(right) - resultTimestamp(left);
        if (byDate) return byDate;
        return String(right.id || '').localeCompare(String(left.id || ''));
      });
      group.result = group.results[0];
      return group;
    }).sort(function(left, right) {
      if (left.result.scope === 'book') return right.result.scope === 'book' ? 0 : -1;
      if (right.result.scope === 'book') return 1;
      return Number(left.result.chapter_index) - Number(right.result.chapter_index);
    });
  }
  function deleteResult(result) {
    if (!result || !result.id) return Promise.resolve(false);
    var confirm = root.EpubDialog && typeof root.EpubDialog.confirm === 'function'
      ? root.EpubDialog.confirm({
        title: t('ai.libraryDelete'),
        message: t('ai.libraryDeleteConfirm'),
        confirmText: t('ai.libraryDelete'),
        destructive: true
      })
      : Promise.resolve(root.confirm(t('ai.libraryDeleteConfirm')));
    return Promise.resolve(confirm).then(function(confirmed) {
      if (!confirmed) return false;
      return request(path('/api/ai/results/' + encodeURIComponent(result.id)), { method: 'DELETE' }).then(function() {
        if (root.EpubBrowserNotification && root.EpubBrowserNotification.show) root.EpubBrowserNotification.show(t('ai.libraryDeleted'), 'success');
        load();
        return true;
      });
    }).catch(function() {
      if (root.EpubBrowserNotification && root.EpubBrowserNotification.show) root.EpubBrowserNotification.show(t('ai.libraryDeleteFailed'), 'error');
      return false;
    });
  }
  function openBook(book) { state.bookId = book.book_id; state.back.hidden = false; render(); }
  function renderEmpty(title, detail, retry) {
    clear(state.container); var box = el('section', 'ai-reading-hub-state');
    var heading = el('h1', 'ai-reading-hub-title', title); heading.id = 'aiReadingHubTitle'; box.appendChild(heading);
    box.appendChild(el('p', '', detail));
    if (retry) { var button = el('button', 'ai-reading-hub-retry', t('ai.libraryRetry')); button.type = 'button'; button.addEventListener('click', load); box.appendChild(button); }
    state.container.appendChild(box);
  }
  function renderLoading() {
    clear(state.container); state.container.setAttribute('aria-busy', 'true');
    var loader = el('section', 'ai-reading-hub-loading'); loader.setAttribute('role', 'status'); loader.appendChild(el('span', 'ai-reading-hub-spinner')); loader.appendChild(el('p', '', t('ai.libraryLoading'))); state.container.appendChild(loader);
  }
  function renderBookList() {
    clear(state.container); state.container.removeAttribute('aria-busy');
    var heading = el('header', 'ai-reading-hub-heading'); var title = el('h1', 'ai-reading-hub-title', t('ai.libraryTitle')); title.id = 'aiReadingHubTitle'; heading.appendChild(title);
    heading.appendChild(el('p', '', t('ai.libraryDescription'))); state.container.appendChild(heading);
    if (!state.books.length) { renderEmpty(t('ai.libraryEmptyTitle'), t('ai.libraryEmptyDescription')); return; }
    var list = el('div', 'ai-reading-book-list');
    state.books.forEach(function(book) {
      var card = el('button', 'ai-reading-book-card'); card.type = 'button'; card.addEventListener('click', function() { openBook(book); });
      card.appendChild(bookVisual(book));
      var content = el('span', 'ai-reading-book-content'); content.appendChild(el('strong', '', book.title));
      if (book.authors && book.authors.length) content.appendChild(el('span', 'ai-reading-book-author', book.authors.join(' · ')));
      content.appendChild(el('span', 'ai-reading-book-meta', t('ai.libraryResultCount', { count: resultCount(book) })));
      card.appendChild(content); var chevron = el('i', 'fas fa-chevron-right'); chevron.setAttribute('aria-hidden', 'true'); card.appendChild(chevron); list.appendChild(card);
    });
    state.container.appendChild(list);
  }
  function renderBook(book) {
    clear(state.container); state.container.removeAttribute('aria-busy');
    var heading = el('header', 'ai-reading-hub-heading'); var title = el('h1', 'ai-reading-hub-title', book.title); title.id = 'aiReadingHubTitle'; heading.appendChild(title);
    var languageRow = el('label', 'ai-reading-language-filter'); languageRow.appendChild(el('span', '', t('ai.libraryLanguage')));
    var languageOptions = [['', t('ai.libraryAllLanguages')]].concat(supportedLanguages.map(function(language) { return [language, t('locale.name.' + language)]; }));
    var languageSelect = el('select'); languageSelect.setAttribute('aria-label', t('ai.libraryLanguage')); languageOptions.forEach(function(option) { var node = el('option', '', option[1]); node.value = option[0]; node.selected = option[0] === state.language; languageSelect.appendChild(node); }); languageSelect.addEventListener('change', function() { state.language = languageSelect.value; render(); }); languageRow.appendChild(languageSelect); heading.appendChild(languageRow);
    var groups = resultGroups(book), results = visibleResults(book); heading.appendChild(el('p', '', t('ai.libraryResultCount', { count: results.length }))); state.container.appendChild(heading);
    var list = el('div', 'ai-reading-result-list');
    groups.forEach(function(group) {
      var groupNode = el('section', 'ai-reading-result-group');
      var groupHeading = el('h2', 'ai-reading-result-group-title', group.result.scope === 'chapter' ? chapterLabel(group.result) : t('ai.libraryBookGuide'));
      groupNode.appendChild(groupHeading);
      if (group.results.length > 1) groupNode.appendChild(el('p', 'ai-reading-result-group-meta', t('ai.libraryVersionCount', { count: group.results.length })));
      var versions = el('div', 'ai-reading-result-versions');
      group.results.forEach(function(result) {
      var row = el('div', 'ai-reading-result-row');
      var card = el('article', 'ai-reading-result-card');
      var link = el('a', 'ai-reading-result-link'); link.href = resultHref(book, result); link.addEventListener('click', close);
      var actionLabel = result.scope === 'chapter' ? t('ai.libraryOpenChapter') : t('ai.libraryOpenBook');
      link.appendChild(el('h3', '', resultTitle(result))); var summary = resultSummary(result); if (summary) link.appendChild(el('p', '', summary));
      link.appendChild(el('span', 'ai-reading-result-details', resultDetails(result)));
      var action = el('span', 'ai-reading-result-action', actionLabel); action.appendChild(el('i', 'fas fa-arrow-right')); action.querySelector('i').setAttribute('aria-hidden', 'true'); link.appendChild(action); card.appendChild(link); row.appendChild(card);
      if (result.can_delete) {
        var remove = el('button', 'ai-reading-result-delete');
        remove.type = 'button';
        remove.setAttribute('aria-label', t('ai.libraryDelete'));
        remove.setAttribute('title', t('ai.libraryDelete'));
        var removeIcon = el('i', 'fas fa-trash-alt'); removeIcon.setAttribute('aria-hidden', 'true'); remove.appendChild(removeIcon);
        remove.addEventListener('click', function(event) {
          event.preventDefault(); event.stopPropagation();
          if (remove.disabled) return;
          remove.disabled = true; remove.setAttribute('aria-busy', 'true');
          deleteResult(result).then(function(deleted) {
            if (!deleted) { remove.disabled = false; remove.removeAttribute('aria-busy'); }
          });
        });
        row.appendChild(remove);
      }
      versions.appendChild(row);
      });
      groupNode.appendChild(versions); list.appendChild(groupNode);
    });
    if (!results.length) list.appendChild(el('p', 'ai-reading-language-empty', t('ai.libraryLanguageEmpty')));
    state.container.appendChild(list);
  }
  function render() { if (!state.bookId) { renderBookList(); return; } var book = state.books.filter(function(item) { return item.book_id === state.bookId; })[0]; if (book) renderBook(book); else { state.bookId = ''; state.back.hidden = true; renderBookList(); } }
  function translate() { if (!state.modal) return; state.modal.querySelector('.ai-reading-hub-header-label span').textContent = t('ai.library'); state.back.querySelector('span').textContent = t('ai.libraryBack'); state.close.setAttribute('aria-label', t('ai.libraryClose')); if (!state.modal.hidden && state.books) render(); }
  function trapFocus(event) {
    if (event.key === 'Escape') { event.preventDefault(); close(); return; }
    if (event.key !== 'Tab') return;
    var focusable = state.modal.querySelectorAll('button:not([hidden]):not([disabled]), a[href], [tabindex]:not([tabindex="-1"])'); if (!focusable.length) return;
    var first = focusable[0], last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); } else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
  }
  function ensure() {
    if (state.modal) return state.modal;
    var modal = el('div', 'ai-reading-hub-modal'); modal.hidden = true; modal.setAttribute('role', 'dialog'); modal.setAttribute('aria-modal', 'true'); modal.setAttribute('aria-labelledby', 'aiReadingHubTitle');
    modal.innerHTML = '<div class="ai-reading-hub-backdrop" data-ai-reading-hub-close></div><section class="ai-reading-hub-dialog"><header class="ai-reading-hub-header"><button type="button" class="ai-reading-hub-back" hidden><i class="fas fa-arrow-left" aria-hidden="true"></i><span></span></button><span class="ai-reading-hub-header-label"><i class="fas fa-wand-magic-sparkles" aria-hidden="true"></i><span></span></span><button type="button" class="ai-reading-hub-close"><i class="fas fa-times" aria-hidden="true"></i></button></header><main class="ai-reading-hub-container" tabindex="-1" aria-live="polite"></main></section>';
    document.body.appendChild(modal); state.modal = modal; state.container = modal.querySelector('.ai-reading-hub-container'); state.close = modal.querySelector('.ai-reading-hub-close'); state.back = modal.querySelector('.ai-reading-hub-back');
    state.close.addEventListener('click', close); state.back.addEventListener('click', function() { state.bookId = ''; state.back.hidden = true; render(); }); modal.querySelector('[data-ai-reading-hub-close]').addEventListener('click', close); modal.addEventListener('keydown', trapFocus); translate(); return modal;
  }
  // The library itself is already the all-books view, so it has no back link.
  // A book or chapter opens a contextual view and must offer a way back to it.
  function load() { var version = ++state.version; renderLoading(); request(path('/api/ai/library')).then(function(data) { if (version !== state.version) return; state.books = data.books || []; state.bookId = state.contextualBookId || ''; state.back.hidden = !Boolean(state.bookId); render(); }).catch(function() { if (version === state.version) renderEmpty(t('ai.libraryLoadFailed'), t('ai.libraryLoadFailedDetail'), true); }); }
  function open(opener) { if (root.EpubBrowserAIRich && root.EpubBrowserAIRich.loadStyle) root.EpubBrowserAIRich.loadStyle('aiReadingHubCss'); var modal = ensure(); if (modal.hidden) { state.opener = opener || document.activeElement; state.scrollY = root.scrollY || 0; document.body.classList.add('ai-reading-hub-open'); document.body.style.top = '-' + state.scrollY + 'px'; modal.hidden = false; } state.contextualBookId = opener && opener.getAttribute('data-book-id') || ''; state.bookId = state.contextualBookId; state.language = locale(); state.back.hidden = !Boolean(state.bookId); load(); root.setTimeout(function() { state.close.focus(); }, 0); }
  function close() { if (!state.modal || state.modal.hidden) return; state.modal.hidden = true; document.body.classList.remove('ai-reading-hub-open'); document.body.style.top = ''; root.scrollTo(0, state.scrollY); if (state.opener && state.opener.focus) state.opener.focus(); }
  function addChapterBadge(link) {
    var existing = link.querySelector('.ai-reading-chapter-badge');
    if (existing) {
      existing.setAttribute('title', t('ai.library'));
      existing.setAttribute('aria-label', t('ai.library'));
      var existingLabel = existing.querySelector('.ai-reading-chapter-label');
      if (existingLabel) existingLabel.textContent = t('ai.library');
      return;
    }
    var badge = el('span', 'ai-reading-chapter-badge'); badge.setAttribute('title', t('ai.library')); badge.setAttribute('aria-label', t('ai.library')); badge.setAttribute('data-ai-reading-chapter-badge', ''); var icon = el('i', 'fas fa-wand-magic-sparkles'); icon.setAttribute('aria-hidden', 'true'); var label = el('span', 'ai-reading-chapter-label', t('ai.library')); badge.appendChild(icon); badge.appendChild(label);
    // The book page has a title/sync grouping; the chapter drawer only has a
    // plain link.  Keep both layouts native to their own navigation surface.
    var title = link.querySelector('.chapter-title');
    var titleGroup = link.querySelector('.chapter-title-with-sync');
    if (!titleGroup && title) { var outline = link.querySelector('.chapter-outline-labels'); titleGroup = el('span', 'chapter-title-with-sync'); title.parentNode.insertBefore(titleGroup, title); titleGroup.appendChild(title); if (outline) titleGroup.appendChild(outline); }
    var syncTag = titleGroup && titleGroup.querySelector('.chapter-sync-tag');
    if (titleGroup) titleGroup.insertBefore(badge, syncTag || null); else link.appendChild(badge);
  }
  function applyChapterIndicators(container, chapters) {
    if (!container || !chapters) return;
    Array.prototype.forEach.call(container.querySelectorAll('[data-chapter-index]'), function(node) {
      var index = Number(node.getAttribute('data-chapter-index'));
      var link = node.tagName === 'A' ? node : node.querySelector('a[data-chapter-index]');
      if (!link) return;
      var badge = link.querySelector('.ai-reading-chapter-badge');
      if (!chapters[index]) { if (badge) badge.remove(); return; }
      addChapterBadge(link);
    });
  }
  function chapterIndicatorKey(bookId, language) { return JSON.stringify([bookId, language]); }
  function refreshIndicatorContainer(container) {
    var bookId = container && container.getAttribute('data-book-id');
    if (!bookId) return Promise.resolve();
    var language = locale();
    return loadChapterIndicators(bookId, language).then(function(chapters) {
      if (language === locale()) applyChapterIndicators(container, chapters);
      return chapters;
    });
  }
  function refreshChapterIndicators(node) {
    var container = node && node.closest ? node.closest('[data-ai-reading-indicators]') : null;
    if (!container) return;
    refreshIndicatorContainer(container).catch(function() {});
  }
  function loadChapterIndicators(bookId, language) {
    var key = chapterIndicatorKey(bookId, language);
    if (state.chapterIndicators[key]) return Promise.resolve(state.chapterIndicators[key]);
    if (!state.chapterIndicatorRequests[key]) {
      state.chapterIndicatorRequests[key] = request(path('/api/ai/books/' + encodeURIComponent(bookId) + '/results') + '?language=' + encodeURIComponent(language)).then(function(data) {
        var chapters = {};
        (data.results || []).forEach(function(result) {
          if (resultLanguage(result) === language && result.scope === 'chapter' && Number.isInteger(Number(result.chapter_index))) chapters[Number(result.chapter_index)] = true;
        });
        state.chapterIndicators[key] = chapters;
        return chapters;
      }).catch(function(error) {
        delete state.chapterIndicatorRequests[key];
        throw error;
      });
    }
    return state.chapterIndicatorRequests[key];
  }
  function markBookChapters() {
    var containers = document.querySelectorAll('[data-ai-reading-indicators]'); if (!containers.length || !root.EpubBrowserAuth || !root.EpubBrowserAuth.fetch) return;
    Array.prototype.forEach.call(containers, function(container) {
      if (!container.dataset.aiReadingIndicatorsBound) {
        container.dataset.aiReadingIndicatorsBound = 'true';
        // The chapter TOC is filled from toc.json after this script loads.
        // Observe it so badges appear without relying on script timing.
        if (root.MutationObserver) new root.MutationObserver(function() { refreshIndicatorContainer(container).catch(function() {}); }).observe(container, { childList: true, subtree: true });
      }
      refreshIndicatorContainer(container).catch(function() {});
    });
  }
  function handleLocaleChange() { translate(); markBookChapters(); }
  function bind() {
    Array.prototype.forEach.call(document.querySelectorAll('[data-ai-reading-hub]'), function(trigger) { if (trigger.dataset.aiReadingHubBound) return; trigger.dataset.aiReadingHubBound = 'true'; trigger.addEventListener('click', function(event) { event.preventDefault(); open(trigger); }); });
    markBookChapters();
    if (!document.documentElement.dataset.aiReadingHubTocBound) {
      document.documentElement.dataset.aiReadingHubTocBound = 'true';
      document.addEventListener('epub-browser:chapter-toc-loaded', function(event) {
        refreshChapterIndicators(event.detail && event.detail.container);
      });
    }
    var i18n = root.EpubBrowserI18n; if (i18n && i18n.onLocaleChange && !document.documentElement.dataset.aiReadingHubI18nBound) { document.documentElement.dataset.aiReadingHubI18nBound = 'true'; i18n.onLocaleChange(handleLocaleChange); }
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', bind); else bind();
  root.EpubBrowserAIReadingHub = { open: open, close: close, bind: bind, refreshChapterIndicators: refreshChapterIndicators };
})(window);
