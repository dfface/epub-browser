(function(root) {
  'use strict';
  var sequence = 0;
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
  function appendInlineMarkdown(parent, source) {
    var text = String(source || '');
    var token = /\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)|\*\*([\s\S]+?)\*\*|__([\s\S]+?)__|`([^`]+)`/g;
    var index = 0;
    text.replace(token, function(match, linkText, href, boldA, boldB, code, offset) {
      if (offset > index) parent.appendChild(root.document.createTextNode(text.slice(index, offset)));
      if (href) {
        var link = el('a', '', linkText); link.href = href; link.target = '_blank'; link.rel = 'noopener noreferrer'; parent.appendChild(link);
      } else if (boldA || boldB) parent.appendChild(el('strong', '', boldA || boldB));
      else parent.appendChild(el('code', '', code));
      index = offset + match.length;
      return match;
    });
    if (index < text.length) parent.appendChild(root.document.createTextNode(text.slice(index)));
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
  function renderMarkdown(parent, source, className) {
    parent.textContent = '';
    var code = null, language = '', paragraph = [], list = null;
    function flushParagraph() {
      if (!paragraph.length) return;
      var block = el('p');
      paragraph.forEach(function(line, index) {
        if (index) block.appendChild(el('br'));
        appendInlineMarkdown(block, line);
      });
      parent.appendChild(block); paragraph = [];
    }
    function flushList() { list = null; }
    function flushCode() {
      if (!code) return;
      var raw = code.join('\n');
      if (language === 'mermaid' || language === 'math') {
        var rich = el('div', className || 'ai-rich-markdown-block'); parent.appendChild(rich); render(rich, language, raw);
      } else {
        var pre = el('pre'), block = el('code', '', raw); pre.appendChild(block); parent.appendChild(pre);
      }
      code = null; language = '';
    }
    normalizeMarkdown(source).split('\n').forEach(function(line) {
      var fence = line.match(/^```\s*([\w-]*)\s*$/i);
      if (fence) { if (code) flushCode(); else { flushParagraph(); flushList(); code = []; language = fence[1].toLowerCase(); } return; }
      if (code) { code.push(line); return; }
      var heading = line.match(/^(#{1,3})\s+(.+)$/), item = line.match(/^[-*+]\s+(.+)$/), quote = line.match(/^>\s?(.+)$/);
      if (heading) { flushParagraph(); flushList(); var title = el(heading[1].length === 1 ? 'h4' : 'h5'); appendInlineMarkdown(title, heading[2]); parent.appendChild(title); }
      else if (item) { flushParagraph(); if (!list) { list = el('ul'); parent.appendChild(list); } var entry = el('li'); appendInlineMarkdown(entry, item[1]); list.appendChild(entry); }
      else if (quote) { flushParagraph(); flushList(); var blockquote = el('blockquote'); appendInlineMarkdown(blockquote, quote[1]); parent.appendChild(blockquote); }
      else if (!line.trim()) { flushParagraph(); flushList(); }
      else { flushList(); paragraph.push(line); }
    });
    flushParagraph(); flushList(); flushCode();
  }
  root.EpubBrowserAIRich = { render: render, renderMarkdown: renderMarkdown };
})(window);
