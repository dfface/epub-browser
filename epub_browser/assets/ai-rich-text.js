(function(root) {
  'use strict';
  var sequence = 0;
  var assetLoads = {};
  var markdownParser = null;
  function featureUrl(name) { return root.EpubBrowserFeatureAssets && root.EpubBrowserFeatureAssets[name]; }
  function loadAsset(name, tag, attribute) {
    var url = featureUrl(name);
    if (!url) return Promise.reject(new Error('missing_feature_asset'));
    if (assetLoads[name]) return assetLoads[name];
    assetLoads[name] = new Promise(function(resolve, reject) {
      var node = root.document.createElement(tag);
      node.setAttribute(attribute, url);
      if (tag === 'link') node.setAttribute('rel', 'stylesheet');
      node.setAttribute('data-epub-browser-feature', name);
      node.addEventListener('load', function() { resolve(); });
      node.addEventListener('error', function() { delete assetLoads[name]; reject(new Error('feature_asset_failed')); });
      (root.document.head || root.document.documentElement).appendChild(node);
    });
    return assetLoads[name];
  }
  function loadStyle(name) { return loadAsset(name, 'link', 'href').then(function() { return undefined; }); }
  function loadScript(name) { return loadAsset(name, 'script', 'src'); }
  function waitForStylePaint() {
    if (!root.requestAnimationFrame) return Promise.resolve();
    return new Promise(function(resolve) {
      root.requestAnimationFrame(function() {
        root.requestAnimationFrame(resolve);
      });
    });
  }
  function ensureRenderer(language) {
    if (language === 'math') return Promise.all([loadStyle('aiRichTextCss'), loadStyle('katexCss'), loadScript('katex')]).then(waitForStylePaint);
    if (language === 'mermaid') return Promise.all([loadStyle('aiRichTextCss'), loadScript('mermaid')]).then(waitForStylePaint);
    return Promise.resolve();
  }
  function el(tag, className, text) {
    var node = root.document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }
  function normalizeMarkdown(source) {
    return String(source || '')
      .replace(/\r\n?/g, '\n');
  }
  function getMarkdownParser() {
    if (markdownParser) return markdownParser;
    if (!root.markdownit) return null;
    markdownParser = root.markdownit({
      html: false,
      linkify: false,
      typographer: false,
      breaks: false,
    });
    // AI output must not be able to cause a remote image request. Preserve the
    // useful alt text while dropping the image element itself.
    markdownParser.renderer.rules.image = function(tokens, index) {
      return markdownParser.utils.escapeHtml(tokens[index].content || '');
    };
    markdownParser.renderer.rules.link_open = function(tokens, index, options, env, renderer) {
      var token = tokens[index];
      var href = token.attrGet('href') || '';
      if (/^https?:\/\//i.test(href)) {
        token.attrSet('target', '_blank');
        token.attrSet('rel', 'noopener noreferrer');
      }
      return renderer.renderToken(tokens, index, options);
    };
    return markdownParser;
  }
  function safeMermaid(source) {
    return !/(?:^|\n)\s*(?:click|link)\b|https?:\/\/|<\/?[a-z]/i.test(source);
  }
  function fallback(parent, source, language) {
    parent.textContent = '';
    parent.classList.add('ai-rich-render-error');
    var i18n = root.EpubBrowserI18n;
    var messageKey = language === 'mermaid' ? 'ai.mermaidFallback' : 'ai.mathFallback';
    var note = root.document.createElement('small');
    note.textContent = i18n && i18n.t ? i18n.t(messageKey) : messageKey;
    var pre = root.document.createElement('pre');
    var code = root.document.createElement('code'); code.textContent = source; pre.appendChild(code);
    parent.appendChild(note); parent.appendChild(pre);
  }
  function render(parent, language, source) {
    var text = String(source || '');
    if (language === 'math') {
      if (!root.katex || !root.katex.render) {
        fallback(parent, text, language);
        if (!parent.dataset.aiRichLoading) {
          parent.dataset.aiRichLoading = 'true';
          parent.aiRichRenderPromise = ensureRenderer(language).then(function() {
            delete parent.dataset.aiRichLoading;
            return render(parent, language, text);
          }).catch(function() { delete parent.dataset.aiRichLoading; });
        }
        return parent.aiRichRenderPromise || Promise.resolve();
      }
      try { root.katex.render(text, parent, { displayMode: true, throwOnError: true, trust: false, strict: 'error' }); }
      catch (_) { fallback(parent, text, language); }
      return Promise.resolve();
    }
    if (language === 'mermaid') {
      if (!safeMermaid(text)) { fallback(parent, text, language); return Promise.resolve(); }
      if (!root.mermaid || !root.mermaid.render) {
        fallback(parent, text, language);
        if (!parent.dataset.aiRichLoading) {
          parent.dataset.aiRichLoading = 'true';
          parent.aiRichRenderPromise = ensureRenderer(language).then(function() {
            delete parent.dataset.aiRichLoading;
            return render(parent, language, text);
          }).catch(function() { delete parent.dataset.aiRichLoading; });
        }
        return parent.aiRichRenderPromise || Promise.resolve();
      }
      var id = 'epub-browser-mermaid-' + (++sequence);
      root.mermaid.initialize({ startOnLoad: false, securityLevel: 'strict', suppressErrorRendering: true });
      return root.mermaid.render(id, text).then(function(result) {
        parent.textContent = '';
        // Mermaid generated this SVG in strict mode from a constrained code
        // block. Raw model HTML is never assigned to innerHTML.
        parent.innerHTML = result.svg;
      }).catch(function() { fallback(parent, text, language); });
    }
    fallback(parent, text, language);
    return Promise.resolve();
  }
  function renderMarkdown(parent, source, className) {
    parent.textContent = '';
    var parser = getMarkdownParser();
    if (!parser) {
      parent.appendChild(el('p', '', normalizeMarkdown(source)));
      return;
    }
    // markdown-it escapes source HTML because `html` is disabled. The string
    // assigned here is renderer output, never raw model output.
    parent.innerHTML = parser.render(normalizeMarkdown(source));
    Array.prototype.forEach.call(parent.querySelectorAll('pre > code[class*="language-"]'), function(code) {
      var match = String(code.className || '').match(/(?:^|\s)language-(mermaid|math)(?:\s|$)/i);
      if (!match || !code.parentNode) return;
      var rich = el('div', className || 'ai-rich-markdown-block');
      code.parentNode.parentNode.replaceChild(rich, code.parentNode);
      render(rich, match[1].toLowerCase(), code.textContent || '');
    });
  }
  root.EpubBrowserAIRich = { render: render, renderMarkdown: renderMarkdown, loadStyle: loadStyle, ensureRenderer: ensureRenderer };
})(window);
