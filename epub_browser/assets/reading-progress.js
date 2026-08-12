(function(root, factory) {
  var EpubReadingProgress = factory();
  if (typeof module === 'object' && module.exports) module.exports = EpubReadingProgress;
  root.EpubReadingProgress = EpubReadingProgress;
})(typeof window !== 'undefined' ? window : globalThis, function() {
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
  }

  ChapterReporter.prototype.select = function(index) {
    this.selectionVersion++;
    if (this.timer !== null) {
      clearTimeout(this.timer);
      this.timer = null;
    }
    if (index === this.reported) {
      this.pending = undefined;
      return;
    }
    this.pending = index;
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
    if (this.pending === undefined || this.pending === this.reported) return Promise.resolve(null);
    var index = this.pending;
    var selectionVersion = this.selectionVersion;
    this.pending = undefined;
    var result;
    try {
      result = this.report(index, keepalive);
    } catch (error) {
      result = null;
    }
    var self = this;
    return Promise.resolve(result).then(function(response) {
      if (response) self.reported = index;
      else if (self.selectionVersion === selectionVersion && self.pending === undefined) self.pending = index;
      return response;
    }, function() {
      if (self.selectionVersion === selectionVersion && self.pending === undefined) self.pending = index;
      return null;
    });
  };

  function showProgressBar(value) { return value !== 'false'; }
  function progressBarClass(visible) { return visible ? '' : 'is-progress-bar-hidden'; }

  function request(method, url, chapterIndex, keepalive) {
    var options = { method: method };
    if (keepalive) options.keepalive = true;
    if (method === 'PUT') {
      options.headers = { 'Content-Type': 'application/json' };
      options.body = JSON.stringify({ chapter_index: chapterIndex });
    }
    try {
      return Promise.resolve(fetch(url, options)).then(function(response) {
        if (!response.ok || response.status === 204) return null;
        return response.json();
      }, function() {
        return null;
      });
    } catch (error) {
      return Promise.resolve(null);
    }
  }

  return {
    activeChapter: activeChapter,
    ChapterReporter: ChapterReporter,
    showProgressBar: showProgressBar,
    progressBarClass: progressBarClass,
    request: request
  };
});
