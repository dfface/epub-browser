(function(root) {
  'use strict';
  if (!root || root.EpubBrowserMode !== 'server') return;
  var document = root.document;
  var loads = {};
  function url(name) { return root.EpubBrowserFeatureAssets && root.EpubBrowserFeatureAssets[name]; }
  function load(name) {
    if (loads[name]) return loads[name];
    var source = url(name);
    if (!source) return Promise.reject(new Error('missing_feature_asset'));
    loads[name] = new Promise(function(resolve, reject) {
      var script = document.createElement('script');
      script.src = source;
      script.setAttribute('data-epub-browser-feature', name);
      script.addEventListener('load', resolve);
      script.addEventListener('error', function() { delete loads[name]; reject(new Error('feature_asset_failed')); });
      (document.head || document.documentElement).appendChild(script);
    });
    return loads[name];
  }
  function enable(name) { return load('aiRichText').then(function() { return load(name); }); }
  function buttonFor(target) {
    if (!target || !target.closest) return null;
    return target.closest('[data-ai-learning-canvas], [data-ai-followup-drawer], [data-ai-book-chat], [data-ai-reading-hub]');
  }
  function featureFor(button) {
    if (button.hasAttribute('data-ai-learning-canvas')) return 'aiCanvas';
    if (button.hasAttribute('data-ai-followup-drawer') || button.hasAttribute('data-ai-book-chat')) return 'aiChat';
    if (button.hasAttribute('data-ai-reading-hub')) return 'aiReadingHub';
    return '';
  }
  function replay(button) {
    button.dataset.aiFeatureReady = 'true';
    button.click();
  }
  document.addEventListener('click', function(event) {
    var button = buttonFor(event.target);
    if (!button || button.dataset.aiFeatureReady) return;
    var feature = featureFor(button);
    if (!feature) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    enable(feature).then(function() { replay(button); }).catch(function() {});
  }, true);
  function loadRequestedResult() {
    if (!root.location || root.location.search.indexOf('ai_result=') < 0) return;
    var button = document.querySelector('[data-ai-learning-canvas]');
    if (!button) return;
    enable('aiCanvas').then(function() { replay(button); }).catch(function() {});
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', loadRequestedResult);
  else loadRequestedResult();
})(window);
