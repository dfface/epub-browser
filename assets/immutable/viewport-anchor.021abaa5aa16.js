(function(root, factory) {
  var anchor = factory(root);
  if (typeof module === 'object' && module.exports) module.exports = anchor;
  root.EpubViewportAnchor = anchor;
})(typeof window !== 'undefined' ? window : globalThis, function(root) {
  function anchorScrollDelta(beforeViewportTop, afterViewportTop) {
    return afterViewportTop - beforeViewportTop;
  }

  function intersectsViewport(rect) {
    return rect.bottom > 0 && rect.top < root.innerHeight;
  }

  function isTextBearing(element) {
    return element.tagName === 'IMG' || Boolean((element.textContent || '').trim());
  }

  function capture(container) {
    if (!container) return null;
    var candidates = container.querySelectorAll('p, h1, h2, h3, h4, h5, h6, li, blockquote, pre, td, th, img');
    for (var index = 0; index < candidates.length; index++) {
      var candidate = candidates[index];
      if (isTextBearing(candidate) && intersectsViewport(candidate.getBoundingClientRect())) {
        return { element: candidate, viewportTop: candidate.getBoundingClientRect().top };
      }
    }
    var chapters = container.querySelectorAll('.continuous-chapter');
    for (var chapterIndex = 0; chapterIndex < chapters.length; chapterIndex++) {
      var chapter = chapters[chapterIndex];
      if (intersectsViewport(chapter.getBoundingClientRect())) {
        return { element: chapter, viewportTop: chapter.getBoundingClientRect().top };
      }
    }
    return null;
  }

  function restore(anchor) {
    if (!anchor || !anchor.element || !anchor.element.isConnected) return 0;
    var currentTop = anchor.element.getBoundingClientRect().top;
    var delta = anchorScrollDelta(anchor.viewportTop, currentTop);
    if (delta) root.scrollBy(0, delta);
    return delta;
  }

  function restoreAfterLayout(anchor) {
    if (!anchor) return;
    var schedule = root.requestAnimationFrame || function(callback) { return root.setTimeout(callback, 0); };
    schedule(function() { restore(anchor); });
  }

  function restoreOnImageLoad(anchor, section) {
    if (!anchor || !section) return;
    var images = section.querySelectorAll('img');
    var pending = 0;
    var scheduled = false;

    function restoreOnce() {
      if (scheduled) return;
      scheduled = true;
      var schedule = root.requestAnimationFrame || function(callback) { return root.setTimeout(callback, 0); };
      schedule(function() {
        scheduled = false;
        restore(anchor);
      });
    }

    function finish() {
      pending -= 1;
      restoreOnce();
    }

    for (var index = 0; index < images.length; index++) {
      if (images[index].complete) continue;
      pending += 1;
      images[index].addEventListener('load', finish, { once: true });
      images[index].addEventListener('error', finish, { once: true });
    }
    if (pending) restoreOnce();
  }

  return {
    anchorScrollDelta: anchorScrollDelta,
    capture: capture,
    restore: restore,
    restoreAfterLayout: restoreAfterLayout,
    restoreOnImageLoad: restoreOnImageLoad,
  };
});
