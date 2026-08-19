(function(root, factory) {
  var EpubReadingProgress = factory(root);
  if (typeof module === 'object' && module.exports) module.exports = EpubReadingProgress;
  root.EpubReadingProgress = EpubReadingProgress;
})(typeof window !== 'undefined' ? window : globalThis, function(root) {
  function activeChapter(sections, viewportMidpoint) {
    var nearest;
    var nearestDistance = Infinity;
    for (var i = 0; i < sections.length; i++) {
      var section = sections[i];
      if (section.top <= viewportMidpoint && section.bottom >= viewportMidpoint) return section.index;
      var distance = viewportMidpoint < section.top
        ? section.top - viewportMidpoint : viewportMidpoint - section.bottom;
      if (distance < nearestDistance) {
        nearest = section.index;
        nearestDistance = distance;
      }
    }
    return nearest;
  }

  function ChapterReporter(report, delay) {
    this.report = report;
    this.delay = delay || 2000;
    this.pending = undefined;
    this.reported = undefined;
    this.timer = null;
    this.selectionVersion = 0;
    this.selected = undefined;
    this.forcePending = false;
    this.inFlight = null;
    this.pendingKeepalive = false;
  }

  ChapterReporter.prototype.select = function(index) {
    this.selectionVersion++;
    this.selected = index;
    if (this.timer !== null) {
      clearTimeout(this.timer);
      this.timer = null;
    }
    if (index === this.reported && this.inFlight === null) {
        this.pending = undefined;
        this.forcePending = false;
        return;
    }
    this.pending = index;
    this.forcePending = index === this.reported;
    var self = this;
    this.timer = setTimeout(function() {
      self.timer = null;
      self.flush();
    }, this.delay);
  };

  ChapterReporter.prototype.flush = function(keepalive) {
    if (this.timer !== null) {
      clearTimeout(this.timer);
      this.timer = null;
    }
    if (this.inFlight !== null) {
      if (keepalive) this.pendingKeepalive = true;
      return this.inFlight;
    }
    if (this.pending === undefined || (this.pending === this.reported && !this.forcePending)) return Promise.resolve(null);
    var index = this.pending;
    var selectionVersion = this.selectionVersion;
    this.pending = undefined;
    this.forcePending = false;
    var result;
    try {
      result = this.report(index, keepalive);
    } catch (error) {
      result = null;
    }
    var self = this;
    this.inFlight = Promise.resolve(result).then(function(response) {
      if (self.selectionVersion === selectionVersion) {
        if (response) self.reported = index;
        else if (self.pending === undefined) self.pending = index;
      } else {
        self.pending = self.selected;
        self.forcePending = true;
      }
      return response;
    }, function() {
      if (self.selectionVersion === selectionVersion && self.pending === undefined) self.pending = index;
      else if (self.selectionVersion !== selectionVersion) {
        self.pending = self.selected;
        self.forcePending = true;
      }
      return null;
    }).then(function(response) {
      self.inFlight = null;
      if (self.selectionVersion !== selectionVersion && self.pending !== undefined) {
        var nextKeepalive = self.pendingKeepalive;
        self.pendingKeepalive = false;
        self.flush(nextKeepalive);
      }
      return response;
    });
    return this.inFlight;
  };

  function showProgressBar(value) { return value !== 'false'; }
  function progressBarClass(visible) { return visible ? '' : 'is-progress-bar-hidden'; }

  function request(method, url, chapterIndex, keepalive, includeError) {
    if (root.EpubBrowserMode !== 'server') return Promise.resolve(null);
    var options = { method: method };
    if (keepalive) options.keepalive = true;
    if (method === 'PUT') {
      options.headers = {};
      options.headers['Content-Type'] = 'application/json';
      options.body = JSON.stringify({ chapter_index: chapterIndex });
    }
    try {
      if (!root.EpubBrowserAuth || typeof root.EpubBrowserAuth.fetch !== 'function') {
        return Promise.resolve(includeError ? { error: {} } : null);
      }
      return Promise.resolve(root.EpubBrowserAuth.fetch(url, options)).then(function(response) {
        if (!response.ok) {
          if (!includeError) return null;
          return response.json().then(function(payload) {
            return { error: payload && typeof payload === 'object' ? payload : {} };
          }, function() {
            return { error: {} };
          });
        }
        if (response.status === 204) return null;
        return response.json();
      }, function() {
        return includeError ? { error: {} } : null;
      });
    } catch (error) {
      return Promise.resolve(includeError ? { error: {} } : null);
    }
  }

  return {
    activeChapter: activeChapter,
    ChapterReporter: ChapterReporter,
    showProgressBar: showProgressBar,
    progressBarClass: progressBarClass,
    isServerMode: function() { return root.EpubBrowserMode === 'server'; },
    request: request
  };
});
