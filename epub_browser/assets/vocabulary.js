(function() {
  'use strict';

  const i18n = window.EpubBrowserI18n;
  const triggers = document.querySelectorAll('[data-vocabulary]');
  if (!triggers.length || !i18n) return;

  const t = (key, params) => i18n.t('vocabulary.' + key, params);
  const statuses = ['new', 'learning', 'mastered'];

  function append(parent, tag, className, text) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined) element.textContent = text;
    parent.appendChild(element);
    return element;
  }

  function button(parent, className, text, action) {
    const control = append(parent, 'button', className, text);
    control.type = 'button';
    control.addEventListener('click', event => {
      if (control.getAttribute('aria-disabled') !== 'true') action(event);
    });
    return control;
  }

  function panel(id, className) {
    const dialog = append(document.body, 'dialog', 'vocabulary-dialog ' + className);
    const header = append(dialog, 'header', 'vocabulary-header');
    const title = append(header, 'h2');
    title.id = id;
    dialog.setAttribute('aria-labelledby', id);
    const close = button(header, 'vocabulary-close', '×', () => dialog.close());
    close.autofocus = true;
    const body = append(dialog, 'div', 'vocabulary-body');
    if (className === 'vocabulary-list-dialog') {
      header.classList.add('annotation-hub-modal-header');
      title.classList.add('annotation-hub-header-label');
      const icon = append(title, 'i', 'fas fa-spell-check');
      icon.setAttribute('aria-hidden', 'true');
      close.classList.add('annotation-hub-icon-button');
      body.classList.add('annotation-hub-container');
    }
    const label = className === 'vocabulary-list-dialog' ? append(title, 'span') : title;
    return {dialog, header, title: label, close, body};
  }

  function masteryOptions(select, includeAll) {
    const selected = select.value;
    select.replaceChildren();
    for (const value of includeAll ? ['', ...statuses] : statuses) {
      const option = append(select, 'option', '', value ? t(value) : i18n.t('library.all'));
      option.value = value;
    }
    select.value = selected;
  }

  const list = panel('vocabulary-title', 'vocabulary-list-dialog');
  const listHeading = list.title.closest('h2');
  listHeading.tabIndex = -1;
  const allWords = button(list.header, 'annotation-hub-header-button', undefined, () => {
    openList('');
    listHeading.focus({preventScroll: true});
  });
  allWords.hidden = true;
  list.header.prepend(allWords);
  append(allWords, 'i', 'fas fa-arrow-left').setAttribute('aria-hidden', 'true');
  const allWordsLabel = append(allWords, 'span');
  const detail = panel('vocabulary-word', 'vocabulary-detail-dialog');
  const controls = append(list.body, 'div', 'vocabulary-filters');
  const search = append(controls, 'input');
  search.type = 'search';
  const filter = append(append(controls, 'span', 'dictionary-select-control'), 'select');
  const status = append(list.body, 'p', 'vocabulary-status');
  status.setAttribute('role', 'status');
  const retry = button(list.body, '', '', () => loadPage(view, view.page));
  const grid = append(list.body, 'div', 'vocabulary-grid');
  const pagination = append(list.body, 'nav', 'vocabulary-pagination');
  const previous = button(pagination, '', '', () => loadPage(view, view.page - 1));
  const pageLabel = append(pagination, 'span');
  const next = button(pagination, '', '', () => loadPage(view, view.page + 1));
  let searchTimer;
  let view;
  let selected;

  function api(path, state) {
    const params = new URLSearchParams();
    if (state.bookId) params.set('book_id', state.bookId);
    return '/api/vocabulary' + path + (params.size ? '?' + params : '');
  }

  function chapterUrl(source) {
    const path = '/book/' + encodeURIComponent(source.book_id) + '/chapter_' +
      encodeURIComponent(source.chapter_index) + '.html';
    return window.EpubBrowserURL.publicPath(path);
  }

  function countText(item) {
    return t(item.lookup_count > 1 ? 'repeated' : 'once', {
      count: item.lookup_count.toLocaleString(i18n.getLocale())
    });
  }

  function renderList() {
    if (!view) return;
    const current = document.activeElement?.dataset.wordId;
    list.title.textContent = t(view.bookId ? 'bookTitle' : 'navigation');
    allWords.hidden = !view.bookId;
    allWordsLabel.textContent = t('allWords');
    allWords.setAttribute('aria-label', allWordsLabel.textContent);
    allWords.title = allWordsLabel.textContent;
    list.close.setAttribute('aria-label', t('close'));
    search.placeholder = t('search');
    search.setAttribute('aria-label', t('search'));
    filter.setAttribute('aria-label', t('mastery'));
    masteryOptions(filter, true);
    const busy = view.notice === 'loading';
    const filtered = Boolean(search.value.trim() || filter.value);
    controls.hidden = !view.total && !filtered && !view.ready;
    retry.textContent = t('retry');
    retry.hidden = view.notice !== 'loadError';
    pagination.setAttribute('aria-label', t('pagination'));
    previous.textContent = t('previousPage');
    next.textContent = t('nextPage');
    pagination.hidden = view.totalPages <= 1;
    const format = new Intl.NumberFormat(i18n.getLocale());
    pageLabel.textContent = i18n.t('pdf.pageOf', {
      number: format.format(view.page), total: format.format(view.totalPages)
    });
    previous.setAttribute('aria-disabled', String(busy || view.page <= 1));
    next.setAttribute('aria-disabled', String(busy || view.page >= view.totalPages));
    grid.setAttribute('aria-busy', String(busy));
    grid.inert = busy;
    status.textContent = view.notice ? t(view.notice) :
      !view.words.length ? t(filtered ? 'noMatches' : 'emptyGuide') : pageLabel.textContent;
    status.classList.toggle('sr-only', !view.notice && view.words.length > 0);
    grid.replaceChildren();
    for (const item of view.words) {
      const card = button(grid, 'vocabulary-card', undefined, event => openWord(item, event.currentTarget));
      card.dataset.wordId = item.id;
      card.setAttribute('aria-haspopup', 'dialog');
      append(card, 'strong', 'vocabulary-card-word', item.word).dir = 'auto';
      const meta = append(card, 'span', 'vocabulary-card-meta');
      append(meta, 'span', 'vocabulary-mastery', t(item.mastery)).dataset.mastery = item.mastery;
      append(meta, 'span', item.lookup_count > 1 ? 'vocabulary-repeated' : '', countText(item));
    }
    if (current && !busy) focusCard(current);
  }

  function focusCard(id, index = 0) {
    const cards = Array.from(grid.children);
    const target = cards.find(card => card.dataset.wordId === id) ||
      cards[Math.min(index, cards.length - 1)] || list.close;
    target.focus({preventScroll: true});
  }

  function openWord(item, card) {
    selected = {
      item, view, index: Array.from(grid.children).indexOf(card),
      controller: new AbortController(), notice: '', pending: false
    };
    renderDetail(selected);
    detail.dialog.showModal();
    detail.title.focus();
  }

  function renderDetail(state) {
    const {item} = state;
    detail.title.textContent = item.word;
    detail.title.dir = 'auto';
    detail.title.tabIndex = -1;
    detail.close.setAttribute('aria-label', t('close'));
    detail.body.replaceChildren();
    detail.body.scrollTop = 0;
    detail.dialog.querySelector('.vocabulary-footer')?.remove();

    const meta = append(detail.body, 'p', 'vocabulary-count', countText(item));
    meta.classList.toggle('vocabulary-repeated', item.lookup_count > 1);
    const definitions = append(detail.body, 'section', 'vocabulary-section');
    definitions.setAttribute('aria-label', i18n.t('dictionary.title'));
    const lookup = append(definitions, 'div', 'vocabulary-definitions');
    window.EpubBrowserDictionary.mountLookup(lookup, item.sources[0].book_id, item.word, {
      signal: state.controller.signal,
      review: true
    });

    const sourceSection = append(detail.body, 'details', 'vocabulary-sources-details');
    append(sourceSection, 'summary', '', t('sources'));
    const sources = append(sourceSection, 'ul', 'vocabulary-sources');
    for (const source of item.sources) {
      const location = i18n.t(source.source_format === 'pdf' ? 'pdf.page' : 'reader.chapterNumber', {
        number: source.chapter_index + 1
      });
      const name = state.view.bookId ? location : source.title + ' · ' + location;
      const link = append(append(sources, 'li'), 'a', '', name);
      link.href = chapterUrl(source);
      link.dir = 'auto';
    }

    const dates = new Intl.DateTimeFormat(i18n.getLocale(), {dateStyle: 'medium', timeStyle: 'short'});
    const history = append(sourceSection, 'div', 'vocabulary-history');
    append(history, 'p', '', t('firstSeen', {date: dates.format(new Date(item.first_seen))}));
    if (item.first_seen !== item.last_seen) {
      append(history, 'p', '', t('lastSeen', {date: dates.format(new Date(item.last_seen))}));
    }

    const footer = append(detail.dialog, 'footer', 'vocabulary-footer');
    const feedback = append(footer, 'p', 'vocabulary-status');
    feedback.setAttribute('role', 'status');
    feedback.textContent = state.notice ? t(state.notice) : '';

    const actions = append(footer, 'div', 'vocabulary-detail-actions');
    const label = append(actions, 'label', '', t('mastery'));
    const mastery = append(append(label, 'span', 'dictionary-select-control'), 'select');
    masteryOptions(mastery, false);
    mastery.value = item.mastery;
    mastery.addEventListener('change', () => {
      if (state.pending) {
        mastery.value = state.pendingMastery || item.mastery;
        return;
      }
      update('PATCH', mastery.value);
    });

    const removeKey = state.view.bookId ? 'remove' : 'delete';
    const remove = button(actions, 'vocabulary-danger', t(removeKey), () => {
      if (state.pending) return;
      confirmation.showModal();
      cancel.focus();
    });
    const confirmation = append(footer, 'dialog', 'vocabulary-dialog vocabulary-confirm-dialog');
    const prompt = append(confirmation, 'p', '', t(
      state.view.bookId ? 'confirmRemove' : 'confirmDelete', {word: item.word}
    ));
    prompt.id = 'vocabulary-remove-prompt';
    confirmation.setAttribute('aria-labelledby', prompt.id);
    const confirmActions = append(confirmation, 'div', 'vocabulary-detail-actions');
    const cancel = button(confirmActions, '', i18n.t('dialog.cancel'), () => confirmation.close());
    button(confirmActions, 'vocabulary-danger', t(removeKey), () => {
      confirmation.close();
      update('DELETE');
    });

    async function update(method, nextMastery) {
      if (state.pending) return;
      state.pending = true;
      state.pendingMastery = nextMastery;
      mastery.setAttribute('aria-disabled', 'true');
      remove.setAttribute('aria-disabled', 'true');
      feedback.textContent = t('saving');
      state.notice = 'saving';
      try {
        const options = {method};
        if (nextMastery) {
          options.headers = {'Content-Type': 'application/json'};
          options.body = JSON.stringify({mastery: nextMastery});
        }
        const response = await window.EpubBrowserAuth.fetch(api('/' + encodeURIComponent(item.id), state.view), options);
        if (!response.ok) throw new Error('Vocabulary update failed');
        if (nextMastery) {
          item.mastery = nextMastery;
          state.view.dirty = true;
          state.notice = 'saved';
        } else {
          state.view.words = state.view.words.filter(word => word.id !== item.id);
          state.view.dirty = true;
          if (selected === state) detail.dialog.close();
        }
      } catch (error) {
        state.notice = 'saveError';
      } finally {
        state.pending = false;
        if (selected === state) {
          const currentMastery = detail.dialog.querySelector('.vocabulary-footer select');
          currentMastery.removeAttribute('aria-disabled');
          currentMastery.value = item.mastery;
          detail.dialog.querySelector('.vocabulary-footer .vocabulary-danger').removeAttribute('aria-disabled');
          detail.dialog.querySelector('.vocabulary-footer .vocabulary-status').textContent = t(state.notice);
        } else if (view === state.view && view.dirty) {
          loadPage(view, view.page);
        }
      }
    }
    if (state.pending) {
      mastery.setAttribute('aria-disabled', 'true');
      remove.setAttribute('aria-disabled', 'true');
    }
  }

  async function loadPage(state, page, restoreFocus) {
    state.controller?.abort();
    const changedPage = state.page !== page;
    state.dirty = false;
    state.page = page;
    const controller = new AbortController();
    state.controller = controller;
    state.notice = 'loading';
    renderList();
    const query = search.value.trim();
    const params = new URLSearchParams({page});
    if (state.bookId) params.set('book_id', state.bookId);
    if (query) params.set('q', query);
    if (filter.value) params.set('mastery', filter.value);
    try {
      const response = await window.EpubBrowserAuth.fetch('/api/vocabulary?' + params, {
        signal: controller.signal
      });
      if (!response.ok) throw new Error('Vocabulary load failed');
      const result = await response.json();
      if (controller.signal.aborted) return;
      state.words = result.words;
      state.page = result.page;
      state.total = result.total;
      state.totalPages = result.total_pages;
      state.ready = true;
      state.notice = '';
    } catch (error) {
      if (controller.signal.aborted) return;
      state.notice = 'loadError';
    }
    if (view === state) {
      const pageButton = pagination.contains(document.activeElement);
      renderList();
      if (changedPage && !restoreFocus && !state.notice) {
        list.dialog.scrollTop = 0;
        if (pageButton) focusCard();
      }
      if (restoreFocus) focusCard(restoreFocus.id, restoreFocus.index);
      if (pageButton && pagination.hidden && pagination.contains(document.activeElement)) list.close.focus();
    }
  }

  search.maxLength = 2048;
  search.addEventListener('input', () => {
    clearTimeout(searchTimer);
    view.controller?.abort();
    searchTimer = setTimeout(() => loadPage(view, 1), 220);
  });
  filter.addEventListener('change', () => {
    clearTimeout(searchTimer);
    loadPage(view, 1);
  });
  list.dialog.addEventListener('close', () => {
    clearTimeout(searchTimer);
    view?.controller?.abort();
    view = null;
  });
  detail.dialog.addEventListener('close', () => {
    if (!selected) return;
    const {item, index, controller} = selected;
    selected = null;
    controller.abort();
    if (view.dirty) {
      loadPage(view, view.page, {id: item.id, index});
    } else {
      renderList();
      focusCard(item.id, index);
    }
  });
  i18n.onLocaleChange(() => {
    renderList();
    if (selected) {
      selected.controller.abort();
      selected.controller = new AbortController();
      renderDetail(selected);
      detail.title.focus();
    }
  });
  function openList(bookId) {
    clearTimeout(searchTimer);
    view?.controller?.abort();
    search.value = '';
    filter.value = '';
    list.dialog.scrollTop = 0;
    view = {bookId, words: [], page: 1, total: 0, totalPages: 0};
    loadPage(view, 1);
  }

  triggers.forEach(control => {
    control.addEventListener('click', () => {
      list.dialog.showModal();
      openList(control.dataset.vocabulary);
    });
  });
})();
