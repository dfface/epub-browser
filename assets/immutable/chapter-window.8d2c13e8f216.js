(function(root, factory) {
  var ChapterWindow = factory();
  if (typeof module === 'object' && module.exports) module.exports = ChapterWindow;
  root.EpubChapterWindow = ChapterWindow;
})(typeof window !== 'undefined' ? window : globalThis, function() {
  function ChapterWindow(initialIndex, limit) {
    this.limit = limit || 5;
    this.chapterIndices = [initialIndex];
  }

  ChapterWindow.prototype.add = function(index, direction) {
    if (this.chapterIndices.indexOf(index) !== -1) return { evicted: [] };
    this.chapterIndices.push(index);
    this.chapterIndices.sort(function(a, b) { return a - b; });
    var evicted = [];
    while (this.chapterIndices.length > this.limit) {
      var removeAt = direction === 'previous' ? this.chapterIndices.length - 1 : 0;
      evicted.push(this.chapterIndices.splice(removeAt, 1)[0]);
    }
    return { evicted: evicted };
  };

  ChapterWindow.prototype.indices = function() { return this.chapterIndices.slice(); };
  return ChapterWindow;
});
