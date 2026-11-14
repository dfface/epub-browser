(function(root) {
  'use strict';

  var loads = {};
  var features = {
    pinyin: { scripts: ['pinyin'] },
    sortable: { scripts: ['sortable'] },
    bookshelf: { scripts: ['sortable', 'bookshelf'] },
    annotations: { styles: ['annotationHubCss'], scripts: ['annotation', 'annotationHub'] },
    readingInsights: { styles: ['readingInsightsCss'], scripts: ['readingInsights'] }
  };

  function assetUrl(name) {
    return root.EpubBrowserLibraryFeatureAssets && root.EpubBrowserLibraryFeatureAssets[name];
  }

  function loadAsset(name, tagName, attribute) {
    var source = assetUrl(name);
    if (!source) return Promise.reject(new Error('missing_library_feature_asset'));
    if (loads[name]) return loads[name];
    loads[name] = new Promise(function(resolve, reject) {
      var node = root.document.createElement(tagName);
      node.setAttribute(attribute, source);
      node.setAttribute('data-epub-browser-library-feature', name);
      if (tagName === 'link') node.setAttribute('rel', 'stylesheet');
      node.addEventListener('load', resolve);
      node.addEventListener('error', function() {
        delete loads[name];
        reject(new Error('library_feature_asset_failed'));
      });
      (root.document.head || root.document.documentElement).appendChild(node);
    });
    return loads[name];
  }

  function loadStyle(name) { return loadAsset(name, 'link', 'href'); }
  function loadScript(name) { return loadAsset(name, 'script', 'src'); }

  // A stylesheet's load event can fire just before the browser has applied it.
  // Wait for two frames so a deferred dialog is never inserted unstyled at the
  // bottom of the document.
  function waitForStylePaint() {
    if (!root.requestAnimationFrame) return Promise.resolve();
    return new Promise(function(resolve) {
      root.requestAnimationFrame(function() {
        root.requestAnimationFrame(resolve);
      });
    });
  }

  function loadFeature(name) {
    var feature = features[name];
    var sequence = Promise.resolve();
    if (!feature) return Promise.reject(new Error('unknown_library_feature'));
    (feature.styles || []).forEach(function(style) {
      sequence = sequence.then(function() { return loadStyle(style); });
    });
    if (feature.styles && feature.styles.length) {
      sequence = sequence.then(waitForStylePaint);
    }
    (feature.scripts || []).forEach(function(script) {
      sequence = sequence.then(function() { return loadScript(script); });
    });
    return sequence;
  }

  root.EpubBrowserLibraryFeatures = {
    load: loadFeature
  };
  function bindReadingInsights() {
    Array.prototype.forEach.call(root.document.querySelectorAll('[data-reading-insights]'), function(button) {
      if (button.dataset.readingInsightsLoaderBound) return;
      button.dataset.readingInsightsLoaderBound = 'true';
      button.addEventListener('click', function(event) {
        if (root.EpubReadingInsights && root.EpubReadingInsights.open) return;
        event.preventDefault();
        button.disabled = true;
        button.setAttribute('aria-busy', 'true');
        loadFeature('readingInsights').then(function() {
          button.disabled = false;
          button.removeAttribute('aria-busy');
          if (root.EpubReadingInsights && root.EpubReadingInsights.open) root.EpubReadingInsights.open(button);
        }).catch(function() {
          button.disabled = false;
          button.removeAttribute('aria-busy');
          if (root.EpubBrowserNotification && root.EpubBrowserNotification.show) {
            root.EpubBrowserNotification.show('Unable to open reading insights. Please try again.', 'error');
          }
        });
      });
    });
  }
  if (root.document.readyState === 'loading') root.document.addEventListener('DOMContentLoaded', bindReadingInsights);
  else bindReadingInsights();
})(window);
