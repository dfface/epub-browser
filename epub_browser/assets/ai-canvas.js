(function(root) {
  'use strict';
  if (!root || root.EpubBrowserMode !== 'server') return;
  var document = root.document;
  var state = { marks: [], paragraphTriggers: [], results: {}, pending: {}, guide: null, reflection: null, popover: null, paragraphPopover: null, mapPopover: null, mapTrigger: null, statusTimer: null, button: null, buttons: [], contextVersion: 0, eventSources: [], initialized: false };
  function t(key, params) { var i = root.EpubBrowserI18n; return i && i.t ? i.t(key, params) : key; }
  function label(key, english, chinese) { var value = t(key); return value === key ? (String(locale()).toLowerCase().indexOf('zh') === 0 ? chinese : english) : value; }
  function el(tag, className, text) { var node = document.createElement(tag); if (className) node.className = className; if (text !== undefined) node.textContent = text; return node; }
  function locale() {
    var value = root.EpubBrowserI18n && root.EpubBrowserI18n.getLocale ? root.EpubBrowserI18n.getLocale() : document.documentElement.lang;
    return String(value || '').toLowerCase().indexOf('zh') === 0 ? 'zh-CN' : 'en';
  }
  function api(url, options) { return root.EpubBrowserAuth.fetch(url, options).then(function(response) { return response.json().catch(function() { return {}; }).then(function(payload) { if (!response.ok) { var error = new Error(payload.code || 'ai_generation_failed'); error.code = payload.code || 'ai_generation_failed'; throw error; } return payload; }); }); }
  function setStatus(button, text, error, transient) {
    var status = document.querySelector('[data-ai-canvas-status]');
    if (!status) { status = el('span', 'ai-canvas-status'); status.setAttribute('data-ai-canvas-status', ''); status.setAttribute('role', 'status'); status.setAttribute('aria-live', 'polite'); document.body.appendChild(status); }
    root.clearTimeout(state.statusTimer); status.textContent = text || ''; status.classList.toggle('ai-canvas-status-error', Boolean(error)); status.classList.toggle('ai-canvas-status-visible', Boolean(text));
    if (transient && text) state.statusTimer = root.setTimeout(function() { status.textContent = ''; status.classList.remove('ai-canvas-status-visible'); }, error ? 7000 : 4200);
  }
  function renderMarkdown(parent, source) {
    parent.textContent = '';
    var code = null, language = '';
    function flushCode() { if (!code) return; var raw = code.join('\n'); if ((language === 'mermaid' || language === 'math') && root.EpubBrowserAIRich) { var rich = el('div', 'ai-canvas-rich-block'); parent.appendChild(rich); root.EpubBrowserAIRich.render(rich, language, raw); } else { var pre = el('pre'); pre.appendChild(el('code', '', raw)); parent.appendChild(pre); } code = null; language = ''; }
    String(source || '').split(/\r?\n/).forEach(function(line) {
      var fence = line.match(/^```\s*([\w-]*)\s*$/i); if (fence) { if (code) flushCode(); else { code = []; language = fence[1].toLowerCase(); } return; }
      if (code) { code.push(line); return; }
      if (!line.trim()) return;
      var title = line.match(/^#{1,3}\s+(.+)$/), item = line.match(/^[-*+]\s+(.+)$/);
      if (title) parent.appendChild(el('h4', '', title[1]));
      else if (item) { var list = parent.lastElementChild && parent.lastElementChild.tagName === 'UL' ? parent.lastElementChild : el('ul'); if (!list.parentNode) parent.appendChild(list); list.appendChild(el('li', '', item[1])); }
      else parent.appendChild(el('p', '', line));
    });
    flushCode();
  }
  function clear() {
    state.marks.forEach(function(mark) { if (!mark.parentNode) return; var parent = mark.parentNode; while (mark.firstChild) parent.insertBefore(mark.firstChild, mark); parent.removeChild(mark); parent.normalize(); });
    state.marks = []; state.paragraphTriggers.forEach(function(trigger) { var block = trigger.parentElement; trigger.remove(); if (block) { block.classList.remove('ai-paragraph-note-anchor'); block.removeAttribute('data-ai-paragraph-note-count'); } }); state.paragraphTriggers = []; state.results = {};
    if (state.guide) state.guide.remove(); if (state.reflection) state.reflection.remove(); if (state.popover) state.popover.remove(); if (state.paragraphPopover) state.paragraphPopover.remove(); if (state.mapPopover) state.mapPopover.remove(); state.guide = state.reflection = state.popover = state.paragraphPopover = state.mapPopover = null;
    setCanvasActive(false);
  }
  function closeEventSources() {
    state.eventSources.forEach(function(source) { source.close(); });
    state.eventSources = [];
  }
  function isCurrentContext(context, contextVersion) {
    var article = currentArticleFor(context);
    return contextVersion === state.contextVersion && article === context.article &&
      Number(article && article.getAttribute('data-chapter-index')) === context.chapterIndex;
  }
  function clearChapter(chapterIndex) {
    var key = String(chapterIndex);
    state.marks = state.marks.filter(function(mark) { if (mark.getAttribute('data-ai-canvas-chapter') !== key) return true; if (!mark.parentNode) return false; var parent = mark.parentNode; while (mark.firstChild) parent.insertBefore(mark.firstChild, mark); parent.removeChild(mark); parent.normalize(); return false; });
    state.paragraphTriggers = state.paragraphTriggers.filter(function(trigger) { if (trigger.getAttribute('data-ai-canvas-chapter') !== key) return true; var block = trigger.parentElement; trigger.remove(); if (block && !block.querySelector('.ai-paragraph-note-trigger')) { block.classList.remove('ai-paragraph-note-anchor'); block.removeAttribute('data-ai-paragraph-note-count'); } return false; });
    Array.prototype.forEach.call(document.querySelectorAll('[data-ai-canvas-chapter="' + key + '"]'), function(node) { node.remove(); });
    if (state.popover) { state.popover.remove(); state.popover = null; }
    if (state.paragraphPopover) removeParagraphPopover();
    if (state.mapPopover) removeMapPopover();
    setCanvasActive(Boolean(document.querySelector('[data-ai-chapter-guide]')));
  }
  function setCanvasActive(active) { state.buttons.forEach(function(button) { button.classList.toggle('is-active', !!active); button.setAttribute('aria-pressed', active ? 'true' : 'false'); }); }
  function diagramFromStructure(structure) {
    if (structure && structure.diagram_mermaid) return structure.diagram_mermaid;
    var nodes = structure && structure.nodes || [], links = structure && structure.links || [];
    if (!nodes.length || !links.length) return '';
    var rootLabel = String(structure.overview || nodes[0].label || '').replace(/[\n()[\]{}]/g, ' ').trim();
    if (!rootLabel) return '';
    var seen = {}; seen[rootLabel] = true;
    var lines = ['mindmap', '  root((' + rootLabel + '))'];
    nodes.slice(0, 9).forEach(function(node) {
      var label = String(node.label || '').replace(/[\n()[\]{}]/g, ' ').trim();
      if (!label || seen[label]) return;
      seen[label] = true; lines.push('    ' + label);
    });
    return lines.length > 2 ? lines.join('\n') : '';
  }
  function createMap(result) {
    var source = diagramFromStructure(result.content && result.content.structure); if (!source || !root.EpubBrowserAIRich) return;
    var map = el('figure', 'ai-native-map'); map.setAttribute('data-ai-native-map', '');
    var canvas = el('div', 'ai-canvas-rich-block'); root.EpubBrowserAIRich.render(canvas, 'mermaid', source); map.appendChild(canvas);
    return map;
  }
  function createNote(annotation, index) {
    var note = el('article', 'ai-native-sticky'); note.id = annotation.id || 'ai-native-note-' + index; note.tabIndex = -1; note.setAttribute('data-ai-note-color', String(index % 4));
    var noteKind = annotation.kind === 'paragraph' ? 'ai.paragraphNote' : 'ai.annotation.' + annotation.kind;
    var head = el('header'); appendKicker(head, t(noteKind), 'fas fa-wand-magic-sparkles'); head.appendChild(el('strong', '', annotation.title)); note.appendChild(head);
    var body = el('div', 'ai-native-note-body'); renderMarkdown(body, annotation.body_markdown || annotation.reason || ''); note.appendChild(body);
    return note;
  }
  function appendKicker(parent, text, iconClass) {
    var kicker = el('span', 'ai-native-note-kicker');
    if (iconClass) kicker.appendChild(el('i', iconClass));
    kicker.appendChild(document.createTextNode(text || ''));
    parent.appendChild(kicker);
    return kicker;
  }
  function positionPanel(panel, trigger) {
    var rect = trigger.getBoundingClientRect(), gap = 12;
    var left = rect.right + gap, top = rect.top - 8;
    if (left + panel.offsetWidth > root.innerWidth - 16 && rect.left >= panel.offsetWidth + gap + 16) left = rect.left - panel.offsetWidth - gap;
    else if (left + panel.offsetWidth > root.innerWidth - 16) left = Math.max(16, root.innerWidth - panel.offsetWidth - 16);
    if (top + panel.offsetHeight > root.innerHeight - 16) top = Math.max(16, root.innerHeight - panel.offsetHeight - 16);
    panel.style.left = left + 'px'; panel.style.top = top + 'px';
  }
  function removeParagraphPopover() { if (state.paragraphPopover) state.paragraphPopover.remove(); state.paragraphPopover = null; }
  function showParagraphPopover(trigger, note) {
    if (state.paragraphPopover && state.paragraphPopover.getAttribute('data-ai-note-id') === note.id) return;
    removeParagraphPopover();
    var panel = el('aside', 'ai-paragraph-popover'); panel.setAttribute('data-ai-note-id', note.id); panel.setAttribute('role', 'dialog'); panel.setAttribute('aria-label', note.title || label('ai.openParagraphNote', 'Paragraph note', '段落笔记'));
    var noteCard = createNote(note, Number(trigger.getAttribute('data-ai-note-color') || 0));
    var close = el('button', 'ai-paragraph-popover-close'); close.type = 'button'; close.setAttribute('aria-label', t('ai.close')); close.appendChild(el('i', 'fas fa-times')); close.addEventListener('click', function(event) { event.preventDefault(); event.stopPropagation(); removeParagraphPopover(); trigger.focus(); });
    noteCard.querySelector('header').appendChild(close); panel.appendChild(noteCard);
    document.body.appendChild(panel); positionPanel(panel, trigger); state.paragraphPopover = panel;
  }
  function normalizeAnchor(value) { return String(value || '').replace(/\u00a0/g, ' ').replace(/\s+/g, ' ').trim(); }
  function findAnchorBlock(article, quote) {
    var needle = normalizeAnchor(quote); if (needle.length < 8) return null;
    var blocks = article.querySelectorAll('p,li,blockquote,dd,dt,figcaption');
    for (var index = 0; index < blocks.length; index++) {
      var block = blocks[index];
      if (block.closest('.ai-chapter-guide,script,style,noscript')) continue;
      var text = normalizeAnchor(block.textContent);
      if (text.indexOf(needle) >= 0) return block;
      // EPUBs often split a source paragraph across inline elements or
      // normalize punctuation differently.  A long distinctive prefix is a
      // safe fallback that keeps the note attached to its actual paragraph.
      var prefix = needle.slice(0, Math.min(96, needle.length));
      if (prefix.length >= 24 && text.indexOf(prefix) >= 0) return block;
    }
    return null;
  }
  function placeParagraphNote(article, note, index, chapterIndex) {
    var block = findAnchorBlock(article, note.anchor_quote); if (!block) return;
    var order = Number(block.getAttribute('data-ai-paragraph-note-count') || 0);
    block.setAttribute('data-ai-paragraph-note-count', String(order + 1)); block.classList.add('ai-paragraph-note-anchor');
    var trigger = el('button', 'ai-paragraph-note-trigger', '!'); trigger.type = 'button'; trigger.setAttribute('data-ai-note-color', String(index % 4)); trigger.setAttribute('data-ai-canvas-chapter', String(chapterIndex)); trigger.setAttribute('aria-label', note.title || label('ai.openParagraphNote', 'Open paragraph note', '查看段落笔记')); trigger.setAttribute('aria-describedby', 'ai-native-note-' + index); trigger.style.top = (6 + order * 30) + 'px';
    function toggle() {
      if (state.paragraphPopover && state.paragraphPopover.getAttribute('data-ai-note-id') === note.id) removeParagraphPopover();
      else showParagraphPopover(trigger, note);
    }
    trigger.addEventListener('click', function(event) { event.preventDefault(); toggle(); });
    trigger.addEventListener('keydown', function(event) { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); toggle(); } else if (event.key === 'Escape') removeParagraphPopover(); });
    block.appendChild(trigger); state.paragraphTriggers.push(trigger);
  }
  function removeMapPopover() { if (state.mapPopover) state.mapPopover.remove(); document.body.classList.remove('ai-map-open'); if (state.mapTrigger) state.mapTrigger.setAttribute('aria-expanded', 'false'); state.mapPopover = null; state.mapTrigger = null; }
  function showMapPopover(trigger, result) {
    if (state.mapPopover) return;
    var map = createMap(result); if (!map) return;
    var modal = el('div', 'ai-guide-map-modal');
    var panel = el('aside', 'ai-guide-map-dialog'); panel.setAttribute('role', 'dialog'); panel.setAttribute('aria-modal', 'true'); panel.setAttribute('aria-label', label('ai.viewMap', 'View mind map', '查看思维导图'));
    var header = el('header', 'ai-guide-map-header'), heading = el('div', 'ai-guide-map-heading'); appendKicker(heading, t('ai.mapKicker'), 'fas fa-diagram-project'); var title = el('h2', '', result.content.quick && result.content.quick.title || t('ai.chapterRead')); title.id = 'ai-guide-map-title'; heading.appendChild(title); panel.setAttribute('aria-labelledby', title.id); header.appendChild(heading);
    var actions = el('div', 'ai-map-popover-actions');
    var fullscreen = el('button', 'ai-map-action'); fullscreen.type = 'button'; fullscreen.setAttribute('aria-label', t('ai.fullscreen')); fullscreen.appendChild(el('i', 'fas fa-expand'));
    fullscreen.addEventListener('click', function() { var active = modal.classList.toggle('is-fullscreen'); fullscreen.setAttribute('aria-label', t(active ? 'ai.exitFullscreen' : 'ai.fullscreen')); fullscreen.querySelector('i').className = active ? 'fas fa-compress' : 'fas fa-expand'; });
    var close = el('button', 'ai-map-action ai-guide-map-close'); close.type = 'button'; close.setAttribute('aria-label', t('ai.close')); close.appendChild(el('i', 'fas fa-times')); close.addEventListener('click', function() { removeMapPopover(); trigger.focus(); });
    actions.appendChild(fullscreen); actions.appendChild(close); header.appendChild(actions); panel.appendChild(header); panel.appendChild(map); modal.appendChild(panel); modal.addEventListener('click', function(event) { if (event.target === modal) { removeMapPopover(); trigger.focus(); } }); document.body.appendChild(modal); document.body.classList.add('ai-map-open'); state.mapPopover = modal; state.mapTrigger = trigger; close.focus();
  }
  function showPopover(mark, annotation) {
    if (state.popover) state.popover.remove();
    var popover = el('aside', 'ai-annotation-popover'); popover.setAttribute('role', 'dialog'); popover.setAttribute('data-ai-canvas-color', mark.getAttribute('data-ai-canvas-color') || '0'); popover.setAttribute('aria-label', annotation.title || t('ai.result'));
    var head = el('header'); appendKicker(head, t('ai.annotation.' + annotation.kind), 'fas fa-wand-magic-sparkles'); head.appendChild(el('strong', '', annotation.title));
    var close = el('button', 'ai-annotation-popover-close'); close.type = 'button'; close.setAttribute('aria-label', t('ai.close')); close.appendChild(el('i', 'fas fa-times')); close.addEventListener('click', function() { popover.remove(); state.popover = null; }); head.appendChild(close); popover.appendChild(head);
    var body = el('div', 'ai-native-note-body'); renderMarkdown(body, annotation.body_markdown || annotation.reason || ''); popover.appendChild(body); document.body.appendChild(popover);
    var rect = mark.getBoundingClientRect(); popover.style.top = Math.min(root.innerHeight - popover.offsetHeight - 16, rect.bottom + 12) + 'px'; popover.style.left = Math.min(root.innerWidth - popover.offsetWidth - 16, Math.max(16, rect.left)) + 'px'; state.popover = popover; close.focus();
  }
  function markQuote(article, annotation, index, chapterIndex) {
    var needle = String(annotation.quote || '').trim(); if (needle.length < 8) return null;
    var walker = document.createTreeWalker(article, root.NodeFilter ? root.NodeFilter.SHOW_TEXT : 4), node;
    while ((node = walker.nextNode())) {
      if (!node.parentElement || node.parentElement.closest('.ai-canvas-mark,.ai-native-map,script,style,noscript')) continue;
      var start = node.nodeValue.indexOf(needle); if (start < 0) continue;
      var range = document.createRange(); range.setStart(node, start); range.setEnd(node, start + needle.length);
      var mark = el('mark', 'ai-canvas-mark'); mark.setAttribute('data-ai-canvas-kind', annotation.kind || 'concept'); mark.setAttribute('data-ai-canvas-color', String(index % 5)); mark.setAttribute('data-ai-canvas-chapter', String(chapterIndex)); mark.tabIndex = 0; mark.setAttribute('role', 'button'); mark.setAttribute('aria-controls', 'ai-native-note-' + index); mark.setAttribute('aria-label', annotation.title || t('ai.result'));
      range.surroundContents(mark);
      function explain() { showPopover(mark, annotation); }
      mark.addEventListener('click', explain); mark.addEventListener('keydown', function(event) { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); explain(); } }); return mark;
    }
    return null;
  }
  function appendReflection(article, result, chapterIndex) {
    var questions = result.content && result.content.deep && result.content.deep.questions || []; if (!questions.length) return;
    var reflection = el('section', 'ai-chapter-reflection'); reflection.setAttribute('data-ai-chapter-reflection', ''); reflection.setAttribute('data-ai-canvas-chapter', String(chapterIndex));
    var head = el('header'); appendKicker(head, label('ai.reflectionKicker', 'AFTER THE CHAPTER', '本章末尾'), 'fas fa-lightbulb'); head.appendChild(el('h2', '', label('ai.reflectionTitle', 'Think further', '深入思考'))); reflection.appendChild(head);
    reflection.appendChild(el('p', 'ai-chapter-reflection-intro', label('ai.reflectionDescription', 'Pause here before moving on.', '读完后，不妨停下来想一想。')));
    var list = el('ol', 'ai-chapter-reflection-list'); questions.slice(0, 3).forEach(function(item) { var entry = el('li', 'ai-reflection-question'); entry.appendChild(el('strong', '', item.question || '')); if (item.why) entry.appendChild(el('p', '', item.why)); list.appendChild(entry); }); reflection.appendChild(list);
    article.appendChild(reflection); state.reflection = reflection;
  }
  function apply(result, article, chapterIndex) {
    article = article || document.querySelector('#eb-content'); chapterIndex = Number(chapterIndex == null ? result.chapter_index : chapterIndex); if (!article || !Number.isInteger(chapterIndex)) return 0;
    clearChapter(chapterIndex); state.results[String(chapterIndex)] = result;
    var guide = el('section', 'ai-chapter-guide'); guide.setAttribute('data-ai-chapter-guide', ''); guide.setAttribute('data-ai-canvas-chapter', String(chapterIndex));
    var guideHead = el('header'); var guideTitle = el('div', 'ai-chapter-guide-title'); appendKicker(guideTitle, t('ai.guideKicker'), 'fas fa-wand-magic-sparkles'); guideTitle.appendChild(el('h2', '', result.content.quick && result.content.quick.title || t('ai.chapterRead'))); guideHead.appendChild(guideTitle);
    if (diagramFromStructure(result.content && result.content.structure)) { var mapLabel = label('ai.viewMap', 'View mind map', '查看思维导图'), mapTrigger = el('button', 'ai-guide-map-trigger'); mapTrigger.type = 'button'; mapTrigger.setAttribute('aria-label', mapLabel); mapTrigger.setAttribute('aria-expanded', 'false'); mapTrigger.appendChild(el('i', 'fas fa-diagram-project')); mapTrigger.appendChild(el('span', '', mapLabel)); function openMap() { showMapPopover(mapTrigger, result); mapTrigger.setAttribute('aria-expanded', 'true'); } mapTrigger.addEventListener('click', function(event) { event.preventDefault(); if (state.mapPopover) { removeMapPopover(); mapTrigger.setAttribute('aria-expanded', 'false'); } else openMap(); }); mapTrigger.addEventListener('keydown', function(event) { if (event.key === 'Escape') { removeMapPopover(); mapTrigger.setAttribute('aria-expanded', 'false'); } }); guideHead.appendChild(mapTrigger); }
    guide.appendChild(guideHead);
    guide.appendChild(el('p', 'ai-chapter-guide-summary', result.content.quick && result.content.quick.summary || ''));
    var points = result.content.quick && result.content.quick.key_points || []; if (points.length) { var list = el('ul', 'ai-chapter-guide-points'); points.slice(0, 4).forEach(function(point) { list.appendChild(el('li', '', point)); }); guide.appendChild(list); }
    article.insertBefore(guide, article.firstChild); state.guide = guide;
    var annotations = result.content && result.content.annotations || [];
    if (!annotations.length) annotations = (result.content && result.content.evidence || []).map(function(item) { return { kind: 'evidence', quote: item.quote, title: t('ai.evidence'), body_markdown: item.reason }; });
    var placed = 0; annotations.forEach(function(item, index) { var mark = markQuote(article, item, index, chapterIndex); if (mark) { state.marks.push(mark); placed += 1; } });
    var paragraphNotes = result.content && result.content.paragraph_notes || [];
    paragraphNotes.forEach(function(item, index) { placeParagraphNote(article, { id: 'ai-native-note-' + chapterIndex + '-' + index, title: item.title, body_markdown: item.summary_markdown, anchor_quote: item.anchor_quote, kind: 'paragraph' }, index, chapterIndex); });
    appendReflection(article, result, chapterIndex);
    setCanvasActive(true);
    return placed;
  }
  function chapterContext(bookId, fallbackIndex) {
    var article = document.querySelector('#eb-content'), index = Number(fallbackIndex), title = article && article.getAttribute('data-chapter-title') || '';
    if (document.body.classList.contains('continuous-scroll-mode') && article) {
      var sections = Array.prototype.slice.call(article.querySelectorAll('.continuous-chapter'));
      if (sections.length) {
        var viewportCenter = root.innerHeight / 2, closest = sections[0], distance = Infinity;
        sections.forEach(function(section) { var rect = section.getBoundingClientRect(), center = (rect.top + rect.bottom) / 2, next = Math.abs(center - viewportCenter); if (next < distance) { distance = next; closest = section; } });
        article = closest; index = Number(closest.getAttribute('data-chapter-index')); title = closest.getAttribute('data-chapter-title') || title;
      }
    }
    return { bookId: bookId, chapterIndex: index, article: article, title: title };
  }
  function currentArticleFor(context) {
    if (!document.body.classList.contains('continuous-scroll-mode')) return context.article;
    return document.querySelector('.continuous-chapter[data-chapter-index="' + context.chapterIndex + '"]') || context.article;
  }
  function contextLabel(context) { return context.title ? t('ai.generatingChapter', { chapter: context.chapterIndex, title: context.title }) : t('ai.generatingChapter', { chapter: context.chapterIndex, title: '' }); }
  function contextScope(context) { return context.title ? t('ai.chapterScope', { chapter: context.chapterIndex, title: context.title }) : t('ai.chapterScopeUntitled', { chapter: context.chapterIndex }); }
  function updateButtonScope(button, context) { var text = t('ai.generateScopeDescription', { scope: contextScope(context) }); button.setAttribute('title', text); button.setAttribute('aria-label', text); }
  function confirmGeneration(context) {
    var message = t('ai.generateScopeDescription', { scope: contextScope(context) });
    if (root.EpubDialog && typeof root.EpubDialog.confirm === 'function') return root.EpubDialog.confirm({ title: t('ai.generateScopeTitle'), message: message, confirmText: t('ai.generateScopeAction') });
    return Promise.resolve(root.confirm(message));
  }
  function watch(button, jobId, context, contextVersion) {
    if (!root.EventSource) return; var source = new root.EventSource('/api/ai/events?job_id=' + encodeURIComponent(jobId));
    state.eventSources.push(source);
    source.addEventListener('job', function(event) { var payload; try { payload = JSON.parse(event.data); } catch (_) { return; } var job = payload.job || {};
      if (!isCurrentContext(context, contextVersion)) { source.close(); return; }
      if (job.status === 'queued' || job.status === 'running') { setStatus(button, contextLabel(context) + ' · ' + t(job.status === 'queued' ? 'ai.queued' : 'ai.generating', { current: job.progress_current || 0, total: job.progress_total || 1 })); return; }
      source.close(); button.disabled = false; delete state.pending[String(context.chapterIndex) + ':' + contextVersion]; if (job.status === 'complete' && payload.result) { var count = apply(payload.result, currentArticleFor(context), context.chapterIndex); setStatus(button, t('ai.canvasApplied', { count: count }), false, true); } else setStatus(button, t('ai.error.' + (job.error_code || 'unknown')), true, true);
    });
  }
  function requestedResultId() { try { return new root.URLSearchParams(root.location.search).get('ai_result'); } catch (_error) { return null; } }
  function load(button, context, contextVersion) {
    var requested = requestedResultId();
    var source = requested
      ? api('/api/ai/results/' + encodeURIComponent(requested), { method: 'GET' }).then(function(payload) { return { results: [payload.result], current_template_version: payload.result && payload.result.template_version }; })
      : api('/api/ai/books/' + encodeURIComponent(context.bookId) + '/results?chapter_index=' + encodeURIComponent(context.chapterIndex) + '&language=' + encodeURIComponent(locale()), { method: 'GET' });
    return source.then(function(payload) {
      if (!isCurrentContext(context, contextVersion)) return null;
      var result = (payload.results || []).filter(function(item) {
        if (!item || item.book_id !== context.bookId || Number(item.chapter_index) !== context.chapterIndex) return false;
        return requested || Number(item.template_version || 0) === Number(payload.current_template_version || 0);
      })[0];
      if (result) apply(result, currentArticleFor(context), context.chapterIndex);
      return result;
    });
  }
  function generate(button, context, contextVersion) { if (!isCurrentContext(context, contextVersion)) return; var key = String(context.chapterIndex) + ':' + contextVersion; if (state.pending[key]) return; state.pending[key] = true; button.disabled = true; setStatus(button, contextLabel(context) + ' · ' + t('ai.queued', { current: 0, total: 1 })); api('/api/ai/reading', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ scope: 'chapter', book_id: context.bookId, chapter_index: context.chapterIndex, mode: 'chapter', language: locale(), force: false }) }).then(function(payload) { if (!isCurrentContext(context, contextVersion)) return; if (payload.status === 'complete') { button.disabled = false; delete state.pending[key]; var count = apply(payload.result, currentArticleFor(context), context.chapterIndex); setStatus(button, t('ai.canvasApplied', { count: count }), false, true); } else watch(button, payload.job.id, context, contextVersion); }).catch(function(error) { if (!isCurrentContext(context, contextVersion)) return; button.disabled = false; delete state.pending[key]; setStatus(button, t('ai.error.' + (error.code || 'unknown')), true, true); }); }
  function refresh(chapterIndex) {
    if (!state.initialized || !state.button || document.body.classList.contains('pagination-mode') || document.body.classList.contains('continuous-scroll-mode')) return Promise.resolve(null);
    state.contextVersion += 1;
    closeEventSources();
    clear();
    state.pending = {};
    state.buttons.forEach(function(button) {
      button.disabled = false;
      button.removeAttribute('aria-disabled');
    });
    var bookId = state.button.getAttribute('data-book-id');
    var context = chapterContext(bookId, Number(chapterIndex));
    state.buttons.forEach(function(button) { updateButtonScope(button, chapterContext(bookId, Number(button.getAttribute('data-chapter-index')))); });
    return load(state.button, context, state.contextVersion).catch(function() { return null; });
  }
  function init() {
    if (state.initialized) return;
    var buttons = Array.prototype.slice.call(document.querySelectorAll('[data-ai-learning-canvas]'));
    if (!buttons.length || !root.EpubBrowserAuth || !root.EpubBrowserAuth.fetch) return;
    state.initialized = true;
    state.buttons = buttons;
    state.button = buttons[0];
    setCanvasActive(false);
    if (document.body.classList.contains('pagination-mode')) {
      buttons.forEach(function(button) { button.disabled = true; button.setAttribute('aria-disabled', 'true'); button.setAttribute('title', t('ai.unavailableInPagination')); });
      return;
    }
    var bookId = state.button.getAttribute('data-book-id');
    var initial = chapterContext(bookId, Number(state.button.getAttribute('data-chapter-index')));
    state.contextVersion += 1;
    load(state.button, initial, state.contextVersion).catch(function() {});
    buttons.forEach(function(button) {
      function currentContext() { return chapterContext(bookId, Number(button.getAttribute('data-chapter-index'))); }
      updateButtonScope(button, currentContext());
      button.addEventListener('mouseenter', function() { updateButtonScope(button, currentContext()); });
      button.addEventListener('focus', function() { updateButtonScope(button, currentContext()); });
      button.addEventListener('click', function() {
        var context = currentContext(), key = String(context.chapterIndex);
        if (document.querySelector('[data-ai-chapter-guide][data-ai-canvas-chapter="' + key + '"]')) {
          clearChapter(context.chapterIndex);
          setStatus(button, t('ai.canvasHidden'), false, true);
          return;
        }
        if (state.results[key]) {
          var count = apply(state.results[key], context.article, context.chapterIndex);
          setStatus(button, t('ai.canvasApplied', { count: count }), false, true);
          return;
        }
        var contextVersion = state.contextVersion;
        load(button, context, contextVersion).then(function(result) {
          if (result || !isCurrentContext(context, contextVersion)) return;
          return confirmGeneration(context).then(function(confirmed) { if (confirmed && isCurrentContext(context, contextVersion)) generate(button, context, contextVersion); });
        }).catch(function() {
          if (!isCurrentContext(context, contextVersion)) return;
          confirmGeneration(context).then(function(confirmed) { if (confirmed && isCurrentContext(context, contextVersion)) generate(button, context, contextVersion); });
        });
      });
    });
    var i18n = root.EpubBrowserI18n;
    if (i18n && i18n.onLocaleChange && !document.documentElement.dataset.aiCanvasI18nBound) {
      document.documentElement.dataset.aiCanvasI18nBound = 'true';
      i18n.onLocaleChange(function() { refresh(Number(state.button.getAttribute('data-chapter-index'))); });
    }
  }
  root.EpubBrowserAICanvas = { refresh: refresh };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})(window);
