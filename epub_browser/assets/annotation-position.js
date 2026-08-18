(function(root, factory) {
  var positioning = factory();
  if (typeof module === 'object' && module.exports) module.exports = positioning;
  root.EpubAnnotationPosition = positioning;
})(typeof window !== 'undefined' ? window : globalThis, function() {
  var ROOT_INDEX = -2;

  function copyMeta(meta, parentTagName, parentIndex) {
    if (!meta) return null;
    var copy = {};
    Object.keys(meta).forEach(function(key) { copy[key] = meta[key]; });
    copy.parentTagName = parentTagName;
    copy.parentIndex = parentIndex;
    return copy;
  }

  function elementsByTag(root, tagName) {
    if (!root || !tagName || !root.getElementsByTagName) return [];
    return Array.prototype.slice.call(root.getElementsByTagName(tagName));
  }

  function toChapterMeta(meta, contentRoot, chapterSection) {
    if (!meta || !contentRoot || !chapterSection) return meta || null;
    if (meta.parentIndex === ROOT_INDEX) return copyMeta(meta, meta.parentTagName, meta.parentIndex);

    var rootElements = elementsByTag(contentRoot, meta.parentTagName);
    var target = rootElements[meta.parentIndex];
    if (!target || !chapterSection.contains(target)) return null;
    if (target === chapterSection) return copyMeta(meta, chapterSection.tagName, ROOT_INDEX);

    var chapterElements = elementsByTag(chapterSection, meta.parentTagName);
    var chapterIndex = chapterElements.indexOf(target);
    return chapterIndex === -1 ? null : copyMeta(meta, meta.parentTagName, chapterIndex);
  }

  function toRootMeta(meta, contentRoot, chapterSection) {
    if (!meta || !contentRoot || !chapterSection) return meta || null;
    var target;
    var tagName = meta.parentTagName;
    if (meta.parentIndex === ROOT_INDEX) {
      target = chapterSection;
      tagName = chapterSection.tagName;
    } else {
      target = elementsByTag(chapterSection, tagName)[meta.parentIndex];
    }
    if (!target) return null;

    var rootIndex = elementsByTag(contentRoot, tagName).indexOf(target);
    return rootIndex === -1 ? null : copyMeta(meta, tagName, rootIndex);
  }

  function chapterIndexForNodes(nodes, fallbackIndex) {
    for (var i = 0; i < (nodes || []).length; i++) {
      var node = nodes[i];
      var section = node && node.closest ? node.closest('.continuous-chapter') : null;
      if (!section) continue;
      var index = parseInt(section.getAttribute('data-chapter-index'), 10);
      if (!isNaN(index)) return index;
    }
    return fallbackIndex;
  }

  return {
    ROOT_INDEX: ROOT_INDEX,
    chapterIndexForNodes: chapterIndexForNodes,
    toChapterMeta: toChapterMeta,
    toRootMeta: toRootMeta
  };
});
