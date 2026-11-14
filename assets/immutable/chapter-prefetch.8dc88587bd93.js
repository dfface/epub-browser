(function (root, factory) {
  var api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.EpubChapterPrefetch = api;
})(typeof window !== 'undefined' ? window : globalThis, function () {
  'use strict';

  function defaultSchedule(task) {
    var win = rootWindow();
    var cancelled = false;
    function run() {
      if (!cancelled) task();
    }
    if (win && typeof win.requestIdleCallback === 'function') {
      var handle = win.requestIdleCallback(run, { timeout: 2000 });
      return function () {
        cancelled = true;
        if (typeof win.cancelIdleCallback === 'function') win.cancelIdleCallback(handle);
      };
    }
    var timer = setTimeout(run, 0);
    return function () {
      cancelled = true;
      clearTimeout(timer);
    };
  }

  function rootWindow() {
    return typeof window !== 'undefined' ? window : null;
  }

  function defaultRequest(url, done) {
    var xhr = new XMLHttpRequest();
    xhr.open('GET', url, true);
    xhr.onload = function () {
      if (xhr.status >= 200 && xhr.status < 300) done(xhr.responseText || '');
      else done(null);
    };
    xhr.onerror = function () { done(null); };
    xhr.send();
    return function () { xhr.abort(); };
  }

  function create(options) {
    options = options || {};
    var urlFor = options.urlFor;
    var schedule = options.schedule || defaultSchedule;
    var request = options.request || defaultRequest;
    var planned = null;

    function afterChapterRendered(index, totalChapters) {
      var current = parseInt(index, 10);
      var total = parseInt(totalChapters, 10);
      if (isNaN(current) || isNaN(total)) return;
      var nextIndex = current + 1;
      if (planned && planned.index === current && planned.nextIndex === nextIndex) return;
      if (planned && planned.cancel) planned.cancel();
      if (nextIndex >= total) {
        planned = null;
        return;
      }
      planned = { index: current, nextIndex: nextIndex, html: null, cancel: null };
      var entry = planned;
      entry.cancel = schedule(function () {
        entry.cancel = request(urlFor(nextIndex), function (html) {
          if (planned !== entry) return;
          entry.cancel = null;
          entry.html = html || null;
        });
      });
    }

    function take(index) {
      var target = parseInt(index, 10);
      if (!planned || planned.nextIndex !== target) return null;
      var html = planned.html;
      if (!html && planned.cancel) planned.cancel();
      planned = null;
      return html;
    }

    return { afterChapterRendered: afterChapterRendered, take: take };
  }

  return { create: create };
});
