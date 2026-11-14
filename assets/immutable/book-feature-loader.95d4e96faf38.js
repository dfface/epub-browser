(function(root) {
  'use strict';

  var loads = {};
  var features = {
    bookshelf: { scripts: ['sortable', 'bookshelf'] },
    annotations: { styles: ['annotationHubCss'], scripts: ['annotation', 'annotationHub'] },
    readingInsights: { styles: ['readingInsightsCss'], scripts: ['readingInsights'] },
    sortable: { scripts: ['sortable'] }
  };

  function assetUrl(name) {
    return root.EpubBrowserBookFeatureAssets && root.EpubBrowserBookFeatureAssets[name];
  }

  function loadAsset(name, tagName, attribute) {
    var source = assetUrl(name);
    if (!source) return Promise.reject(new Error('missing_book_feature_asset'));
    if (loads[name]) return loads[name];
    loads[name] = new Promise(function(resolve, reject) {
      var node = root.document.createElement(tagName);
      node.setAttribute(attribute, source);
      node.setAttribute('data-epub-browser-book-feature', name);
      if (tagName === 'link') node.setAttribute('rel', 'stylesheet');
      node.addEventListener('load', resolve);
      node.addEventListener('error', function() {
        delete loads[name];
        reject(new Error('book_feature_asset_failed'));
      });
      (root.document.head || root.document.documentElement).appendChild(node);
    });
    return loads[name];
  }

  // Do not initialize a deferred dialog until its stylesheet has had a chance
  // to paint; otherwise its markup can briefly render at document bottom.
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
    if (!feature) return Promise.reject(new Error('unknown_book_feature'));
    (feature.styles || []).forEach(function(style) {
      sequence = sequence.then(function() { return loadAsset(style, 'link', 'href'); });
    });
    if (feature.styles && feature.styles.length) {
      sequence = sequence.then(waitForStylePaint);
    }
    (feature.scripts || []).forEach(function(script) {
      sequence = sequence.then(function() { return loadAsset(script, 'script', 'src'); });
    });
    return sequence;
  }

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

  root.EpubBrowserBookFeatures = { load: loadFeature };
  if (root.document.readyState === 'loading') root.document.addEventListener('DOMContentLoaded', bindReadingInsights);
  else bindReadingInsights();
})(window);
