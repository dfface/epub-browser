(function(root, factory) {
  var exported = factory();
  if (typeof module === 'object' && module.exports) module.exports = exported;
  if (root && root.document) root.EpubRecentReading = exported;
})(typeof window !== 'undefined' ? window : (typeof globalThis !== 'undefined' ? globalThis : this), function() {
  'use strict';

  var MOUNT_ID = 'recentReading';
  var MINUTE = 60 * 1000;
  var HOUR = 60 * MINUTE;
  var DAY = 24 * HOUR;

  var active = null;

  function translate(context, key, params) {
    var i18n = context && context.EpubBrowserI18n;
    if (i18n && typeof i18n.t === 'function') return i18n.t(key, params || {});
    return key;
  }

  // SQLite writes CURRENT_TIMESTAMP as "YYYY-MM-DD HH:MM:SS" in UTC.  Without
  // an explicit zone suffix the browser would read it as local time, so the
  // value is normalised before it is parsed.
  function parseTimestamp(value) {
    if (typeof value !== 'string' || !value) return null;
    var normalized = value.trim().replace(' ', 'T');
    if (!/(?:[Zz]|[+-]\d{2}:?\d{2})$/.test(normalized)) normalized += 'Z';
    var parsed = new Date(normalized);
    return isNaN(parsed.getTime()) ? null : parsed;
  }

  function relativeTime(context, value, now) {
    var parsed = parseTimestamp(value);
    if (!parsed) return '';
    var reference = now instanceof Date
      ? now.getTime()
      : (typeof now === 'number' && isFinite(now) ? now : Date.now());
    var delta = reference - parsed.getTime();
    // Clock skew between the server and this browser must never produce
    // "in 3 hours"; anything below a minute reads as "just now".
    if (delta < MINUTE) return translate(context, 'library.recentReading.justNow');
    if (delta < HOUR) {
      return translate(context, 'library.recentReading.minutesAgo', {
        count: Math.floor(delta / MINUTE)
      });
    }
    if (delta < DAY) {
      return translate(context, 'library.recentReading.hoursAgo', {
        count: Math.floor(delta / HOUR)
      });
    }
    var days = Math.floor(delta / DAY);
    if (days < 30) return translate(context, 'library.recentReading.daysAgo', { count: days });
    return translate(context, 'library.recentReading.monthsAgo', {
      count: Math.max(1, Math.round(days / 30))
    });
  }

  function positionLabel(context, item, format) {
    var index = item && item.chapter_index;
    if (typeof index !== 'number' || !isFinite(index) || index < 0) return '';
    var number = index + 1;
    return format === 'pdf'
      ? translate(context, 'library.recentReading.page', { index: number })
      : translate(context, 'library.recentReading.chapter', { index: number });
  }

  // Chapter URLs are derived from the catalogue entry instead of being rebuilt
  // from the book id, so the rail follows whatever root the catalogue uses.
  function chapterUrl(bookUrl, chapterIndex) {
    if (typeof bookUrl !== 'string' || !bookUrl) return '';
    if (typeof chapterIndex !== 'number' || !isFinite(chapterIndex) || chapterIndex < 0) {
      return bookUrl;
    }
    var slash = bookUrl.lastIndexOf('/');
    if (slash === -1) return bookUrl;
    return bookUrl.slice(0, slash + 1) + 'chapter_' + chapterIndex + '.html';
  }

  function joinRecentReading(books, items) {
    var byHash = {};
    (books || []).forEach(function(book) {
      if (book && typeof book.hash === 'string') byHash[book.hash] = book;
    });
    var seen = {};
    var merged = [];
    (items || []).forEach(function(item) {
      var book = item && byHash[item.book_id];
      // Entries whose book is absent from the catalogue are skipped: the book
      // was removed, or it is no longer visible to this account.
      if (!book || seen[item.book_id]) return;
      seen[item.book_id] = true;
      merged.push({ book: book, item: item });
    });
    return merged;
  }

  function createEntry(context, entry) {
    var document = context.document;
    var book = entry.book;
    var item = entry.item;

    var listItem = document.createElement('li');
    listItem.className = 'recent-reading-item';

    var link = document.createElement('a');
    link.className = 'recent-reading-link';
    link.setAttribute('href', chapterUrl(book.url, item.chapter_index));

    var coverFrame = document.createElement('span');
    coverFrame.className = 'recent-reading-cover' + (book.cover ? '' : ' recent-reading-cover--empty');
    if (book.cover) {
      var cover = document.createElement('img');
      cover.className = 'recent-reading-cover-image';
      cover.setAttribute('src', book.cover);
      cover.setAttribute('alt', '');
      cover.setAttribute('aria-hidden', 'true');
      cover.setAttribute('loading', 'lazy');
      cover.setAttribute('decoding', 'async');
      coverFrame.appendChild(cover);
    } else {
      var fallbackIcon = document.createElement('i');
      fallbackIcon.className = 'fas fa-book';
      fallbackIcon.setAttribute('aria-hidden', 'true');
      coverFrame.appendChild(fallbackIcon);
    }

    var body = document.createElement('span');
    body.className = 'recent-reading-body';

    var title = document.createElement('span');
    title.className = 'recent-reading-book';
    title.setAttribute('dir', 'auto');
    title.textContent = book.title || '';
    title.title = book.title || '';

    var positionText = positionLabel(context, item, book.format);
    var timeText = relativeTime(context, item.updated_at);
    var metaText = '';
    if (positionText && timeText) {
      metaText = positionText + ' · ' + timeText;
    } else if (positionText) {
      metaText = positionText;
    } else if (timeText) {
      metaText = timeText;
    }

    var meta = document.createElement('span');
    meta.className = 'recent-reading-meta';
    meta.setAttribute('dir', 'auto');
    meta.textContent = metaText;
    meta.title = metaText;

    body.appendChild(title);
    if (meta.textContent) body.appendChild(meta);

    var labelParts = [translate(context, 'library.recentReading.title')];
    if (book.title) labelParts.push(book.title);
    if (metaText) labelParts.push(metaText);
    link.setAttribute('aria-label', labelParts.join(' — '));

    link.appendChild(coverFrame);
    link.appendChild(body);
    listItem.appendChild(link);
    return listItem;
  }

  function renderRail(context, mount, list, state) {
    if (!list) return;
    var entries = joinRecentReading(state.books, state.items);
    // The rail only exists once both sides of the join have arrived, and it
    // disappears instead of showing an empty state.
    mount.hidden = state.items === null || entries.length === 0;
    while (list.firstChild) list.removeChild(list.firstChild);
    entries.forEach(function(entry) {
      list.appendChild(createEntry(context, entry));
    });
  }

  function createDomOptions(context, mount) {
    var list = mount.querySelector('[data-recent-reading-list]');
    return {
      render: function(state) {
        renderRail(context, mount, list, state);
      }
    };
  }

  function createController(options) {
    options = options || {};
    var controller = {
      state: { books: [], items: null },
      setBooks: setBooks,
      setItems: setItems,
      render: render
    };

    function setBooks(books) {
      controller.state.books = Array.isArray(books) ? books : [];
      render();
    }

    function setItems(items) {
      controller.state.items = Array.isArray(items) ? items : null;
      render();
    }

    function render() {
      if (options.render) options.render(controller.state);
    }

    return controller;
  }

  function loadRecentReading(context, controller) {
    var auth = context.EpubBrowserAuth;
    if (!auth || typeof auth.fetch !== 'function') return Promise.resolve(null);
    var url = (context.EpubBrowserBasePath || '/') + 'api/reading-progress';
    return Promise.resolve(auth.fetch(url, { method: 'GET' }))
      .then(function(response) {
        if (!response || !response.ok) return [];
        return response.json().then(function(payload) {
          return payload && Array.isArray(payload.items) ? payload.items : [];
        }, function() {
          return [];
        });
      }, function() {
        return [];
      })
      .then(function(items) {
        controller.setItems(items);
        return items;
      });
  }

  function start(context) {
    var root = context || (typeof window !== 'undefined' ? window : null);
    if (!root || !root.document || root.EpubBrowserMode !== 'server') return null;
    var mount = root.document.getElementById(MOUNT_ID);
    if (!mount) return null;

    var controller = createController(createDomOptions(root, mount));
    active = controller;
    if (root.EpubBrowserI18n && root.EpubBrowserI18n.onLocaleChange) {
      root.EpubBrowserI18n.onLocaleChange(function() { controller.render(); });
    }
    loadRecentReading(root, controller);
    return { controller: controller };
  }

  function updateBooks(books) {
    if (active) active.setBooks(books);
  }

  return {
    start: start,
    updateBooks: updateBooks,
    createController: createController,
    parseTimestamp: parseTimestamp,
    relativeTime: relativeTime,
    positionLabel: positionLabel,
    chapterUrl: chapterUrl,
    joinRecentReading: joinRecentReading
  };
});
