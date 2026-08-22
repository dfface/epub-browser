(function(root) {
  'use strict';
  var sequence = 0;
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
      if (!root.katex || !root.katex.render) return fallback(parent, text, language);
      try { root.katex.render(text, parent, { displayMode: true, throwOnError: true, trust: false, strict: 'error' }); }
      catch (_) { fallback(parent, text, language); }
      return;
    }
    if (language === 'mermaid') {
      if (!safeMermaid(text) || !root.mermaid || !root.mermaid.render) return fallback(parent, text, language);
      var id = 'epub-browser-mermaid-' + (++sequence);
      root.mermaid.initialize({ startOnLoad: false, securityLevel: 'strict', suppressErrorRendering: true });
      root.mermaid.render(id, text).then(function(result) {
        parent.textContent = '';
        // Mermaid generated this SVG in strict mode from a constrained code
        // block.  Model HTML is never assigned to innerHTML anywhere else.
        parent.innerHTML = result.svg;
      }).catch(function() { fallback(parent, text, language); });
      return;
    }
    fallback(parent, text, language);
  }
  root.EpubBrowserAIRich = { render: render };
})(window);
