(function(root) {
  'use strict';

  var loads = {};
  var features = {
    pinyin: { scripts: ['pinyin'] },
    sortable: { scripts: ['sortable'] },
    bookshelf: { scripts: ['sortable', 'bookshelf'] },
    annotations: { styles: ['annotationHubCss'], scripts: ['annotation', 'annotationHub'] }
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
})(window);
