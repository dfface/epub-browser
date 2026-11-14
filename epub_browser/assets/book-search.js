(function (root) {
  'use strict';

  var HASH_PREFIX = '#eb-search=';
  var STORAGE_PREFIX = 'eb-book-search:';
  var state = {
    controller: null,
    requestId: 0,
    initialized: false,
    query: '',
    page: 1,
    pages: 1,
    renderedQuery: '',
    renderedPage: 0,
    closeOverlay: null
  };

  function t(key, params) {
    var i18n = root.EpubBrowserI18n;
    return i18n && typeof i18n.t === 'function' ? i18n.t(key, params) : key;
  }

  function publicPath(path) {
    return root.EpubBrowserURL && typeof root.EpubBrowserURL.publicPath === 'function'
      ? root.EpubBrowserURL.publicPath(path)
      : path;
  }

  function parseHash(hash) {
    if (typeof hash !== 'string' || hash.indexOf(HASH_PREFIX) !== 0) return null;
    var parts = hash.substring(HASH_PREFIX.length).split(',');
    if (parts.length !== 3) return null;
    if (!/^[0-9]+$/.test(parts[0]) || !/^[0-9]+$/.test(parts[1])) return null;
    var start = Number(parts[0]);
    var end = Number(parts[1]);
    if (!Number.isSafeInteger(start) || !Number.isSafeInteger(end) || end <= start) {
      return null;
    }
    var match;
    try {
      match = decodeURIComponent(parts[2]);
    } catch (error) {
      return null;
    }
    if (!match) return null;
    return { start: start, end: end, match: match };
  }

  function hitHash(hit) {
    return HASH_PREFIX + String(hit.start) + ',' + String(hit.end) + ',' +
      encodeURIComponent(hit.match);
  }

  function rangeForHit(rootNode, hit) {
    if (!rootNode || !hit) return null;
    var showText = root.NodeFilter.SHOW_TEXT;
    var accept = root.NodeFilter.FILTER_ACCEPT;
    var reject = root.NodeFilter.FILTER_REJECT;
    var walker = root.document.createTreeWalker(rootNode, showText, {
      acceptNode: function (node) {
        var parent = node.parentElement;
        if (!parent || parent.closest('script,style,template,noscript')) return reject;
        return accept;
      }
    });
    var offset = 0;
    var startNode = null;
    var endNode = null;
    var startOffset = 0;
    var endOffset = 0;
    while (walker.nextNode()) {
      var value = walker.currentNode.nodeValue || '';
      var next = offset + value.length;
      if (startNode === null && hit.start >= offset && hit.start < next) {
        startNode = walker.currentNode;
        startOffset = hit.start - offset;
      }
      if (hit.end >= offset && hit.end <= next) {
        endNode = walker.currentNode;
        endOffset = hit.end - offset;
      }
      if (startNode && endNode) break;
      offset = next;
    }
    if (!startNode || !endNode) return null;
    var range = root.document.createRange();
    range.setStart(startNode, startOffset);
    range.setEnd(endNode, endOffset);
    if (range.toString() !== hit.match) return null;
    return range;
  }

  // The index stores offsets into the *normalized* chapter text (ASCII
  // whitespace collapsed, block elements separated by a space).  The rendered
  // DOM keeps the original indentation/newlines, so raw offsets rarely line up.
  // Rebuild the same normalized stream in the browser, keeping a map back to
  // DOM positions, and fall back to locating by match + surrounding context.
  var BLOCK_TAGS = {
    address: 1, article: 1, aside: 1, blockquote: 1, body: 1, caption: 1,
    dd: 1, details: 1, div: 1, dl: 1, dt: 1, figcaption: 1, figure: 1,
    footer: 1, form: 1, h1: 1, h2: 1, h3: 1, h4: 1, h5: 1, h6: 1,
    header: 1, hr: 1, html: 1, li: 1, main: 1, nav: 1, ol: 1, p: 1,
    pre: 1, section: 1, summary: 1, table: 1, tbody: 1, td: 1, tfoot: 1,
    th: 1, thead: 1, tr: 1, ul: 1
  };
  var SKIP_TAGS = { script: 1, style: 1, template: 1, svg: 1 };

  function normalizedText(rootNode) {
    var chars = [];
    var map = [];
    function boundary() {
      if (!chars.length || chars[chars.length - 1] === ' ') return;
      chars.push(' ');
      map.push(map.length ? map[map.length - 1] : null);
    }
    function walk(node) {
      if (!node) return;
      if (node.nodeType === 3) {
        var value = node.nodeValue || '';
        for (var i = 0; i < value.length; i++) {
          var code = value.charCodeAt(i);
          if (code === 32 || code === 9 || code === 10 || code === 13 || code === 12) {
            if (chars.length && chars[chars.length - 1] !== ' ') {
              chars.push(' ');
              map.push({ node: node, offset: i, end: i + 1 });
            }
            continue;
          }
          chars.push(value.charAt(i));
          map.push({ node: node, offset: i, end: i + 1 });
        }
        return;
      }
      if (node.nodeType !== 1) return;
      var name = String(node.localName || node.nodeName || '').toLowerCase();
      if (SKIP_TAGS[name]) return;
      var block = BLOCK_TAGS[name] === 1;
      if (block) boundary();
      for (var child = node.firstChild; child; child = child.nextSibling) walk(child);
      if (block) boundary();
    }
    walk(rootNode);
    while (chars.length && chars[chars.length - 1] === ' ') {
      chars.pop();
      map.pop();
    }
    return { text: chars.join(''), map: map };
  }

  function contextScore(text, index, hit) {
    var score = 0;
    var before = String(hit.before || '');
    var after = String(hit.after || '');
    var i = 0;
    while (
      i < before.length && index - 1 - i >= 0 &&
      text.charAt(index - 1 - i) === before.charAt(before.length - 1 - i)
    ) {
      i += 1;
    }
    score += i;
    var end = index + hit.match.length;
    var j = 0;
    while (j < after.length && end + j < text.length && text.charAt(end + j) === after.charAt(j)) {
      j += 1;
    }
    return score + j;
  }

  function rangeForNormalizedIndex(built, start, length) {
    var map = built.map;
    var first = start;
    while (first < start + length && !map[first]) first += 1;
    var last = start + length - 1;
    while (last >= start && !map[last]) last -= 1;
    if (first > last || first >= map.length || last >= map.length) return null;
    var begin = map[first];
    var finish = map[last];
    if (!begin || !finish) return null;
    var range = root.document.createRange();
    range.setStart(begin.node, begin.offset);
    range.setEnd(finish.node, finish.end);
    return range;
  }

  function rangeForText(rootNode, hit) {
    if (!rootNode || !hit || !hit.match) return null;
    var built = normalizedText(rootNode);
    var text = built.text;
    if (!text) return null;
    if (text.substr(hit.start, hit.match.length) === hit.match) {
      return rangeForNormalizedIndex(built, hit.start, hit.match.length);
    }
    var best = -1;
    var bestScore = -1;
    var index = text.indexOf(hit.match);
    while (index !== -1) {
      var score = contextScore(text, index, hit);
      if (score > bestScore) {
        bestScore = score;
        best = index;
      }
      index = text.indexOf(hit.match, index + 1);
    }
    return best < 0 ? null : rangeForNormalizedIndex(built, best, hit.match.length);
  }

  function highlightRange(range) {
    if (!root.CSS || !root.CSS.highlights || typeof root.Highlight !== 'function') return;
    try {
      root.CSS.highlights.set('book-search', new root.Highlight(range));
    } catch (error) {
      // Highlighting is progressive enhancement; navigation already succeeded.
    }
  }

  function scrollRangeIntoView(range) {
    var rect = range.getBoundingClientRect();
    var viewport = typeof root.innerHeight === 'number' && root.innerHeight > 0
      ? root.innerHeight
      : 0;
    if (rect && (rect.top || rect.height || rect.width)) {
      var delta = viewport ? Math.round(viewport / 3) : 80;
      root.scrollTo(0, Math.max(0, rect.top + (root.pageYOffset || 0) - delta));
      return;
    }
    var target = range.startContainer;
    if (target && target.nodeType === 1 && target.scrollIntoView) {
      target.scrollIntoView({ behavior: 'auto', block: 'center' });
    } else if (target && target.parentElement && target.parentElement.scrollIntoView) {
      target.parentElement.scrollIntoView({ behavior: 'auto', block: 'center' });
    }
  }

  function locate(rootNode, hit, options) {
    var range = rangeForHit(rootNode, hit) || rangeForText(rootNode, hit);
    if (!range) return false;
    options = options || {};
    if (options.pagination && options.pageWidth > 0 && options.container) {
      var rect = range.getBoundingClientRect();
      var containerRect = options.container.getBoundingClientRect();
      var left = options.container.scrollLeft + rect.left - containerRect.left;
      var page = Math.floor(Math.max(0, left) / options.pageWidth);
      if (typeof options.showPage === 'function') options.showPage(page);
    } else {
      scrollRangeIntoView(range);
    }
    highlightRange(range);
    return true;
  }

  root.EpubBookSearch = {
    hashPrefix: HASH_PREFIX,
    parseHash: parseHash,
    hitHash: hitHash,
    rangeForHit: rangeForHit,
    rangeForText: rangeForText,
    normalizedText: normalizedText,
    locate: locate
  };

  function setStatus(statusEl, key, params) {
    if (!statusEl) return;
    if (!key) {
      statusEl.textContent = '';
      statusEl.removeAttribute('data-i18n');
      statusEl.removeAttribute('data-i18n-params');
      return;
    }
    statusEl.textContent = t(key, params);
    statusEl.setAttribute('data-i18n', key);
    if (params) statusEl.setAttribute('data-i18n-params', JSON.stringify(params));
    else statusEl.removeAttribute('data-i18n-params');
  }

  function clearResults(list) {
    while (list.firstChild) list.removeChild(list.firstChild);
  }

  function renderResults(list, statusEl, payload) {
    clearResults(list);
    var results = payload && Array.isArray(payload.results) ? payload.results : [];
    var total = payload && Number.isFinite(payload.total) ? payload.total : results.length;
    var pageSize = payload && payload.page_size > 0 ? payload.page_size : 1;
    var pages = Math.max(1, Math.ceil(total / pageSize));
    var requested = Math.max(1, payload && payload.page ? payload.page : 1);
    if (total > 0 && requested > pages) {
      // A persisted page can disappear when the index is rebuilt; snap to the
      // last page instead of showing an empty "page out of range" state.
      search(state.query, pages);
      return;
    }
    state.page = Math.min(requested, pages);
    state.pages = pages;
    state.renderedQuery = state.query;
    state.renderedPage = state.page;
    var pagination = root.document.getElementById('bookSearchPagination');
    var pageInput = root.document.getElementById('bookSearchPageInput');
    var pageTotal = root.document.getElementById('bookSearchPageTotal');
    if (pageInput) {
      pageInput.value = state.page;
      pageInput.max = pages;
    }
    if (pageTotal) pageTotal.textContent = '/ ' + pages;
    setStatus(root.document.getElementById('bookSearchPageStatus'),
      'book.searchPageStatus', { page: state.page, pages: pages });
    if (pagination) {
      if (pages <= 1 && pagination.contains(root.document.activeElement)) {
        root.document.getElementById('bookSearchInput').focus();
      }
      pagination.hidden = pages <= 1;
    }
    var previous = root.document.getElementById('bookSearchPrev');
    var next = root.document.getElementById('bookSearchNext');
    if (previous) previous.disabled = state.page <= 1;
    if (next) next.disabled = state.page >= pages;
    var focused = root.document.activeElement;
    if (pageInput && focused && focused.disabled && (focused === previous || focused === next)) {
      pageInput.focus();
    }
    if (!results.length) {
      setStatus(statusEl, total ? 'book.searchPageOutOfRange' : 'book.searchNoResults');
      return;
    }
    setStatus(statusEl, 'book.searchResultCount', { count: total });
    list.scrollTop = 0;
    var lastChapter = null;
    results.forEach(function (hit) {
      var chapterIndex = Number(hit.chapter_index);
      if (chapterIndex !== lastChapter) {
        lastChapter = chapterIndex;
        var header = root.document.createElement('li');
        header.className = 'book-search-chapter';
        var chapterTitle = String(hit.chapter_title || '').trim();
        if (!chapterTitle || /^[\s\-–—·•.…]+$/.test(chapterTitle)) {
          // Untitled sections often carry a placeholder dash; a numbered label
          // still tells readers which chapter a hit belongs to.
          setStatus(header, 'reader.chapterNumber', {
            number: chapterIndex + 1
          });
        } else {
          header.textContent = chapterTitle;
        }
        list.appendChild(header);
      }
      var item = root.document.createElement('li');
      item.className = 'book-search-result';
      var link = root.document.createElement('a');
      link.className = 'book-search-result-link';
      link.href = publicPath(
        '/book/' + encodeURIComponent(bookId()) + '/chapter_' + chapterIndex + '.html' +
        hitHash({ start: Number(hit.start_offset), end: Number(hit.end_offset), match: hit.match })
      );
      var snippet = root.document.createElement('span');
      snippet.className = 'book-search-result-snippet';
      snippet.appendChild(root.document.createTextNode(String(hit.before || '')));
      var mark = root.document.createElement('mark');
      mark.textContent = String(hit.match || '');
      snippet.appendChild(mark);
      snippet.appendChild(root.document.createTextNode(String(hit.after || '')));
      link.appendChild(snippet);
      link.addEventListener('click', function (event) {
        var href = link.getAttribute('href');
        if (!href) return;
        event.preventDefault();
        // Hide the search surface first: the destination chapter is about to
        // take over, and on same-chapter jumps the drawer would cover the hit.
        if (typeof state.closeOverlay === 'function') state.closeOverlay();
        // Reader chapters cancel this event and navigate in place; the book
        // landing page has no reader, so follow the URL normally.
        var navigate = new root.CustomEvent('epub-browser:book-search-navigate', {
          detail: { href: href },
          cancelable: true
        });
        var handled = !root.dispatchEvent(navigate);
        if (!handled) root.location.assign(href);
      });
      item.appendChild(link);
      list.appendChild(item);
    });
  }

  function bookId() {
    var content = root.document.getElementById('eb-content');
    var hash = content ? content.getAttribute('data-book-hash') : '';
    if (!hash) {
      var scope = root.document.querySelector('[data-book-search][data-book-hash]');
      hash = scope ? scope.getAttribute('data-book-hash') : '';
    }
    return hash || '';
  }

  // Search is a repeated activity: readers jump to a hit, read, then come back
  // for the next one. Keep the last query and result page per book for the
  // lifetime of the tab so reopening the drawer/dialog resumes that search.
  function storageKey() {
    var id = bookId();
    return id ? STORAGE_PREFIX + id : '';
  }

  function readStoredSearch() {
    try {
      var key = storageKey();
      var raw = key && root.sessionStorage ? root.sessionStorage.getItem(key) : '';
      if (!raw) return null;
      var parsed = JSON.parse(raw);
      if (!parsed || typeof parsed.q !== 'string') return null;
      var query = String(parsed.q).replace(/[ \t\r\n\f]+/g, ' ').replace(/^ | $/g, '');
      if (!query) return null;
      return {
        query: query.slice(0, 128),
        page: Math.max(1, parseInt(parsed.p, 10) || 1)
      };
    } catch (error) {
      return null;
    }
  }

  function storeSearch(query, page) {
    try {
      var key = storageKey();
      if (!key || !root.sessionStorage) return;
      if (!query) {
        root.sessionStorage.removeItem(key);
        return;
      }
      root.sessionStorage.setItem(key, JSON.stringify({
        q: query,
        p: Math.max(1, parseInt(page, 10) || 1)
      }));
    } catch (error) {
      // Storage can be unavailable (private mode); persistence is optional.
    }
  }

  function focusInput(input) {
    input.focus();
    var value = String(input.value || '');
    if (!value) {
      input.select();
      return;
    }
    try {
      input.setSelectionRange(value.length, value.length);
    } catch (error) {
      input.select();
    }
  }

  function renderHint(list) {
    if (!list) return;
    var item = root.document.createElement('li');
    item.className = 'book-search-empty';
    var text = root.document.createElement('p');
    setStatus(text, 'book.searchHint');
    item.appendChild(text);
    list.appendChild(item);
  }

  function ensureSearch() {
    if (!state.query) return;
    if (state.renderedQuery === state.query && state.renderedPage === state.page) return;
    search(state.query, state.page);
  }

  function search(query, page) {
    var form = root.document.getElementById('bookSearchForm');
    var input = root.document.getElementById('bookSearchInput');
    var statusEl = root.document.getElementById('bookSearchStatus');
    var list = root.document.getElementById('bookSearchResults');
    if (!form || !input || !list) return Promise.resolve();
    var value = String(query || '').replace(/[ \t\r\n\f]+/g, ' ').replace(/^ | $/g, '');
    if (state.controller) state.controller.abort();
    state.requestId += 1;
    var requestId = state.requestId;
    var pagination = root.document.getElementById('bookSearchPagination');
    if (!value) {
      state.controller = null;
      form.removeAttribute('aria-busy');
      state.query = '';
      state.page = 1;
      state.pages = 1;
      state.renderedQuery = '';
      state.renderedPage = 0;
      storeSearch('', 1);
      clearResults(list);
      setStatus(statusEl, '');
      renderHint(list);
      if (pagination) pagination.hidden = true;
      return Promise.resolve();
    }
    var pageNumber = Math.max(1, parseInt(page, 10) || 1);
    state.query = value;
    state.page = pageNumber;
    storeSearch(value, pageNumber);
    state.controller = typeof root.AbortController === 'function' ? new root.AbortController() : null;
    form.setAttribute('aria-busy', 'true');
    clearResults(list);
    setStatus(statusEl, 'book.searching');
    if (pagination && value !== state.renderedQuery) pagination.hidden = true;
    // These results are cleared while loading. A failed request must be
    // retried on reopen even if it requested the last rendered page.
    state.renderedQuery = '';
    var url = publicPath(
      '/api/books/' + encodeURIComponent(bookId()) + '/search?q=' + encodeURIComponent(value) +
      '&page=' + pageNumber
    );
    var options = { credentials: 'same-origin', headers: { Accept: 'application/json' } };
    if (state.controller) options.signal = state.controller.signal;
    return root.fetch(url, options).then(function (response) {
      if (requestId !== state.requestId) return null;
      if (!response.ok) {
        setStatus(statusEl, response.status === 503 ? 'book.searchUnavailable' : 'book.searchFailed');
        return null;
      }
      return response.json();
    }).then(function (payload) {
      if (payload && requestId === state.requestId) renderResults(list, statusEl, payload);
    }).catch(function (error) {
      if (error && error.name === 'AbortError') return;
      if (requestId === state.requestId) setStatus(statusEl, 'book.searchFailed');
    }).then(function () {
      if (requestId !== state.requestId) return;
      form.removeAttribute('aria-busy');
      state.controller = null;
      if (!state.renderedQuery && pagination && !pagination.hidden) {
        if (pagination.contains(root.document.activeElement)) input.focus();
        pagination.hidden = true;
      }
    });
  }

  function trapFocus(event, dialog) {
    var focusable = Array.from(dialog.querySelectorAll(
      'a[href], button:not([disabled]), input:not([disabled]), [tabindex]:not([tabindex="-1"])'
    )).filter(function (element) { return !element.closest('[hidden]'); });
    if (!focusable.length) return;
    var first = focusable[0];
    var last = focusable[focusable.length - 1];
    if (event.shiftKey && root.document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && root.document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  function isSearchShortcut(event) {
    return Boolean(event) && !event.defaultPrevented && !event.altKey && !event.shiftKey &&
      Boolean(event.ctrlKey || event.metaKey) && String(event.key || '').toLowerCase() === 'k';
  }

  function initModal(modal, input) {
    var toggle = root.document.getElementById('bookSearchToggle');
    var close = root.document.getElementById('bookSearchClose');
    var dialog = root.document.getElementById('book-search-dialog') || modal;
    var opener = null;
    function closeModal() {
      if (modal.hidden) return;
      modal.hidden = true;
      if (toggle) toggle.setAttribute('aria-expanded', 'false');
      var restore = opener;
      opener = null;
      if (restore && typeof restore.focus === 'function') restore.focus();
    }
    function openModal() {
      if (!modal.hidden) {
        focusInput(input);
        ensureSearch();
        return;
      }
      opener = root.document.activeElement || toggle;
      modal.hidden = false;
      if (toggle) toggle.setAttribute('aria-expanded', 'true');
      focusInput(input);
      ensureSearch();
    }
    state.openOverlay = openModal;
    state.closeOverlay = closeModal;
    if (toggle) toggle.addEventListener('click', openModal);
    if (close) close.addEventListener('click', closeModal);
    modal.addEventListener('click', function (event) {
      if (event.target === modal) closeModal();
    });
    root.document.addEventListener('keydown', function (event) {
      if (modal.hidden) return;
      if (event.key === 'Escape' || event.key === 'Esc') {
        event.preventDefault();
        closeModal();
      } else if (event.key === 'Tab') {
        trapFocus(event, dialog);
      }
    });
  }

  function init() {
    if (state.initialized) return;
    var form = root.document.getElementById('bookSearchForm');
    var input = root.document.getElementById('bookSearchInput');
    if (!form || !input) return;
    var modal = root.document.getElementById('bookSearchModal');
    var panel = root.document.getElementById('bookSearchDrawer');
    var toggle = root.document.getElementById('bookSearchToggle');
    var mobileToggle = root.document.getElementById('mobileBookSearchToggle');
    var close = root.document.getElementById('bookSearchClose');
    var drawerMode = Boolean(panel && toggle) && !modal;
    if (drawerMode && !root.EpubReaderDrawers) {
      root.addEventListener('epub-browser:reader-drawers-ready', init, { once: true });
      return;
    }
    state.initialized = true;
    var storedSearch = readStoredSearch();
    if (storedSearch) {
      input.value = storedSearch.query;
      state.query = storedSearch.query;
      state.page = storedSearch.page;
    } else {
      renderHint(root.document.getElementById('bookSearchResults'));
    }
    if (drawerMode) {
      var drawer = root.EpubReaderDrawers.register({
        panel: panel,
        toggle: toggle,
        mobileToggle: mobileToggle,
        afterOpen: function () {
          focusInput(input);
          ensureSearch();
        }
      });
      if (drawer) {
        toggle.addEventListener('click', function () { drawer.open(toggle); });
        if (mobileToggle) {
          mobileToggle.addEventListener('click', function () { drawer.open(mobileToggle); });
        }
      }
      state.openOverlay = function () {
        if (!drawer) return;
        if (panel.classList.contains('active')) {
          focusInput(input);
          ensureSearch();
          return;
        }
        drawer.open(toggle);
        // The reader drawer focuses its close button on the next frame, so
        // focus the query field afterwards to keep the shortcut usable.
        root.requestAnimationFrame(function () {
          focusInput(input);
          ensureSearch();
        });
      };
      state.closeOverlay = function () {
        root.EpubReaderDrawers.close(true);
      };
      if (close) {
        close.addEventListener('click', function () {
          root.EpubReaderDrawers.close(true);
        });
      }
    } else if (modal) {
      initModal(modal, input);
    }
    root.document.addEventListener('keydown', function (event) {
      if (!isSearchShortcut(event) || typeof state.openOverlay !== 'function') return;
      event.preventDefault();
      state.openOverlay();
    });
    var previous = root.document.getElementById('bookSearchPrev');
    var next = root.document.getElementById('bookSearchNext');
    var pagination = root.document.getElementById('bookSearchPagination');
    var pageInput = root.document.getElementById('bookSearchPageInput');
    if (pagination && pageInput) {
      pagination.addEventListener('submit', function (event) {
        event.preventDefault();
        if (form.hasAttribute('aria-busy')) return;
        var page = pageInput.valueAsNumber;
        if (!Number.isSafeInteger(page) || page < 1 || page > state.pages) return;
        if (page !== state.page) search(state.query, page);
      });
    }
    if (previous) {
      previous.addEventListener('click', function () {
        if (!form.hasAttribute('aria-busy') && state.page > 1) search(state.query, state.page - 1);
      });
    }
    if (next) {
      next.addEventListener('click', function () {
        if (!form.hasAttribute('aria-busy') && state.page < state.pages) search(state.query, state.page + 1);
      });
    }
    form.addEventListener('submit', function (event) {
      event.preventDefault();
      search(input.value);
    });
  }

  if (root.document.readyState === 'loading') {
    root.document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})(window);
