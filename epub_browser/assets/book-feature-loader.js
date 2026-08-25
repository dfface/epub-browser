(function(root) {
  'use strict';

  var loads = {};
  var features = {
    bookshelf: { scripts: ['sortable', 'bookshelf'] },
    annotations: { styles: ['annotationHubCss'], scripts: ['annotation', 'annotationHub'] },
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

  function loadFeature(name) {
    var feature = features[name];
    var sequence = Promise.resolve();
    if (!feature) return Promise.reject(new Error('unknown_book_feature'));
    (feature.styles || []).forEach(function(style) {
      sequence = sequence.then(function() { return loadAsset(style, 'link', 'href'); });
    });
    (feature.scripts || []).forEach(function(script) {
      sequence = sequence.then(function() { return loadAsset(script, 'script', 'src'); });
    });
    return sequence;
  }

  root.EpubBrowserBookFeatures = { load: loadFeature };
})(window);
