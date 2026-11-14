(function(root, factory) {
  var buffer = factory();
  if (typeof module === 'object' && module.exports) module.exports = buffer;
  root.EpubContinuousBuffer = buffer;
})(typeof window !== 'undefined' ? window : globalThis, function() {
  function needsMoreContinuousContent(scrollHeight, scrollY, viewportHeight) {
    return scrollHeight - (scrollY + viewportHeight) < viewportHeight * 2;
  }

  return { needsMoreContinuousContent: needsMoreContinuousContent };
});
