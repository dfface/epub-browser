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
  function waitForStylePaint() {
    if (!root.requestAnimationFrame) return Promise.resolve();
    return new Promise(function(resolve) {
      root.requestAnimationFrame(function() {
        root.requestAnimationFrame(resolve);
      });
    });
  }
  function enable(name) {
    return load('markdownIt').then(function() { return load('aiRichText'); }).then(function() {
      var stylesheet = name === 'aiReadingHub'
        ? 'aiReadingHubCss'
        : name === 'aiCanvas'
          ? 'aiCanvasCss'
          : name === 'aiChat'
            ? 'aiChatCss'
            : '';
      if (!stylesheet) return load(name);
      return root.EpubBrowserAIRich.loadStyle(stylesheet)
        .then(waitForStylePaint)
        .then(function() { return load(name); });
    });
  }
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
  function setFeatureLoading(button, loading) {
    var label = button.querySelector('[data-i18n]');
    var icon = button.querySelector('i');
    var i18n = root.EpubBrowserI18n;
    var messageKey = featureFor(button) === 'aiChat' ? 'ai.chatLoading' : 'ai.libraryLoading';
    if (loading) {
      if (label) { button.dataset.aiFeatureLabel = label.textContent; label.textContent = i18n && i18n.t ? i18n.t(messageKey) : button.dataset.aiFeatureLabel; }
      if (icon) { button.dataset.aiFeatureIcon = icon.className; icon.className = 'fas fa-spinner fa-spin'; }
      button.classList.add('is-loading');
      button.setAttribute('aria-busy', 'true');
      button.setAttribute('aria-disabled', 'true');
      button.disabled = true;
      return;
    }
    if (label) label.textContent = label.getAttribute('data-i18n') && i18n && i18n.t ? i18n.t(label.getAttribute('data-i18n')) : button.dataset.aiFeatureLabel;
    if (icon && button.dataset.aiFeatureIcon) icon.className = button.dataset.aiFeatureIcon;
    button.classList.remove('is-loading');
    button.removeAttribute('aria-busy');
    button.removeAttribute('aria-disabled');
    button.disabled = false;
    delete button.dataset.aiFeatureLabel;
    delete button.dataset.aiFeatureIcon;
  }
  document.addEventListener('click', function(event) {
    var button = buttonFor(event.target);
    if (!button || button.dataset.aiFeatureReady) return;
    var feature = featureFor(button);
    if (!feature) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    setFeatureLoading(button, true);
    enable(feature).then(function() {
      setFeatureLoading(button, false);
      replay(button);
    }).catch(function() { setFeatureLoading(button, false); });
  }, true);
  function loadRequestedResult() {
    if (!root.location || root.location.search.indexOf('ai_result=') < 0) return;
    var button = document.querySelector('[data-ai-learning-canvas]');
    if (!button) return;
    enable('aiCanvas').then(function() { replay(button); }).catch(function() {});
  }
  function loadReadingIndicators() {
    // Chapter badges need result metadata on the book/chapter page, but do not
    // need the hub stylesheet or modal.  Load only this small behavior chunk.
    if (document.querySelector('[data-ai-reading-indicators]')) load('aiReadingHub').catch(function() {});
  }
  function initializeDeferredFeatures() { loadRequestedResult(); loadReadingIndicators(); }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', initializeDeferredFeatures);
  else initializeDeferredFeatures();
})(window);
