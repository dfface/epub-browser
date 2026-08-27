(function(root) {
  'use strict';
  if (!root || root.EpubBrowserMode !== 'server') return;
  var document = root.document;
  var overlay, panel, conversation, questionNav, thread, composer, input, send, previousFocus;
  var context = null, eventSources = {};
  var activeQuestionFrame = 0;
  function t(key, params) { var i = root.EpubBrowserI18n; return i && i.t ? i.t(key, params) : key; }
  function localised(key, en, _zh, params) { var value = t(key, params); return value === key ? en : value; }
  function locale() { var value = root.EpubBrowserI18n && root.EpubBrowserI18n.getLocale ? root.EpubBrowserI18n.getLocale() : document.documentElement.lang; return ['en', 'zh-CN', 'zh-TW', 'ko', 'ja', 'es', 'de', 'fr', 'ru', 'it', 'pt-BR', 'ar', 'id', 'hi', 'vi', 'th', 'ms'].indexOf(value) >= 0 ? value : 'en'; }
  function el(tag, className, text) { var node = document.createElement(tag); if (className) node.className = className; if (text !== undefined) node.textContent = text; return node; }
  function fetchApi(url, options) { return root.EpubBrowserAuth.fetch(url, options).then(function(response) { return response.json().catch(function() { return {}; }).then(function(payload) { if (!response.ok) { var error = new Error(payload.code || 'ai_generation_failed'); error.code = payload.code || 'ai_generation_failed'; throw error; } return payload; }); }); }
  function chapterContext(button) {
    var article = document.querySelector('#eb-content');
    var index = Number(button.getAttribute('data-chapter-index'));
    var title = article && article.getAttribute('data-chapter-title') || '';
    if (document.body.classList.contains('continuous-scroll-mode')) {
      var sections = Array.prototype.slice.call(document.querySelectorAll('.continuous-chapter[data-chapter-index]'));
      var best = null, distance = Infinity;
      sections.forEach(function(section) { var distanceHere = Math.abs(section.getBoundingClientRect().top - root.innerHeight * .28); if (distanceHere < distance) { best = section; distance = distanceHere; } });
      if (best) { index = Number(best.getAttribute('data-chapter-index')); title = best.getAttribute('data-chapter-title') || title; }
    }
    return { bookId: button.getAttribute('data-book-id'), chapterIndex: index, chapterTitle: title || '' };
  }
  function chapterScope(value) {
    if (!value || value.bookContext) return t('ai.chatWholeBook');
    var title = String(value.chapterTitle || '').trim();
    return title ? t('ai.chapterScope', { chapter: value.chapterIndex, title: title }) : t('ai.chapterScopeUntitled', { chapter: value.chapterIndex });
  }
  function drawerScope(value) {
    if (!value || value.bookContext) return t('ai.chatBookScope');
    return t('ai.chatScope', { scope: chapterScope(value) });
  }
  function updateTriggerScope(button, value) {
    var text = t('ai.askScope', { scope: chapterScope(value) });
    button.setAttribute('title', text);
    button.setAttribute('aria-label', text);
  }
  function appendInline(parent, value) {
    String(value || '').split(/(\*\*[^*]+\*\*|__[^_]+__|`[^`]+`|\[[^\]]+\]\((?:https?:\/\/|mailto:|\/)[^)]+\)|\*[^*\n]+\*|_[^_\n]+_)/g).forEach(function(part) {
      if (!part) return;
      if (/^(\*\*.*\*\*|__.*__)$/.test(part)) parent.appendChild(el('strong', '', part.slice(2, -2)));
      else if (/^\*.*\*$/.test(part) || /^_.*_$/.test(part)) parent.appendChild(el('em', '', part.slice(1, -1)));
      else if (/^`.*`$/.test(part)) parent.appendChild(el('code', '', part.slice(1, -1)));
      else {
        var link = part.match(/^\[([^\]]+)\]\(([^)]+)\)$/);
        if (!link) { parent.appendChild(document.createTextNode(part)); return; }
        var anchor = el('a', '', link[1]); anchor.href = link[2];
        if (/^https?:\/\//i.test(link[2])) { anchor.target = '_blank'; anchor.rel = 'noopener noreferrer'; }
        parent.appendChild(anchor);
      }
    });
  }
  function renderMarkdown(parent, source) {
    parent.textContent = ''; var lines = String(source || '').replace(/\r\n?/g, '\n').split('\n'), paragraph = [], list, code, language = '';
    function flushParagraph() { if (!paragraph.length) return; var p = el('p'); paragraph.forEach(function(line, index) { if (index) p.appendChild(el('br')); appendInline(p, line); }); parent.appendChild(p); paragraph = []; }
    function flushList() { list = null; }
    function flushCode() { var raw = code.join('\n'); if ((language === 'mermaid' || language === 'math') && root.EpubBrowserAIRich) { var rich = el('div', 'ai-chat-rich-block'); root.EpubBrowserAIRich.render(rich, language, raw); parent.appendChild(rich); } else { var pre = el('pre'); pre.appendChild(el('code', '', raw)); parent.appendChild(pre); } code = null; language = ''; }
    lines.forEach(function(line) { var fence = line.match(/^```\s*([\w-]*)\s*$/); if (fence) { flushParagraph(); flushList(); if (code) flushCode(); else { code = []; language = String(fence[1] || '').toLowerCase(); } return; } if (code) { code.push(line); return; }
      var heading = line.match(/^(#{1,3})\s+(.+)$/), item = line.match(/^\s*([-*+]|\d+\.)\s+(.+)$/), quote = line.match(/^>\s?(.*)$/);
      if (heading) { flushParagraph(); flushList(); var h = el(heading[1].length === 1 ? 'h3' : 'h4'); appendInline(h, heading[2]); parent.appendChild(h); }
      else if (item) { flushParagraph(); var ordered = /\d+\./.test(item[1]); if (!list || list.tagName !== (ordered ? 'OL' : 'UL')) { list = el(ordered ? 'ol' : 'ul'); parent.appendChild(list); } var li = el('li'); appendInline(li, item[2]); list.appendChild(li); }
      else if (quote) { flushParagraph(); flushList(); var block = el('blockquote'); appendInline(block, quote[1]); parent.appendChild(block); }
      else if (!line.trim()) { flushParagraph(); flushList(); } else { flushList(); paragraph.push(line); }
    });
    if (code) flushCode(); flushParagraph();
  }
  function threadIsNearBottom() { return !thread || thread.scrollHeight - thread.scrollTop - thread.clientHeight < 80; }
  function scrollThread() { if (thread) root.requestAnimationFrame(function() { thread.scrollTop = thread.scrollHeight; }); }
  function statusText(turn) { if (turn.status === 'queued') return t('ai.queued', { current: 0, total: 1 }); if (turn.status === 'running') return t('ai.generating', { current: 0, total: 1 }); return t('ai.error.' + (turn.error_code || 'unknown')); }
  function chapterLabel(turn) { if (turn && Number(turn.book_context)) return t('ai.chatWholeBook'); return localised('ai.chatChapter', 'Chapter ' + Number(turn.chapter_index), '第 ' + Number(turn.chapter_index) + ' 章', { number: Number(turn.chapter_index) }); }
  function turnScopeLabel(turn) {
    var turnUsesBook = Boolean(turn && Number(turn.book_context));
    if (!context) return chapterLabel(turn);
    if (context.bookContext) return turnUsesBook ? '' : chapterLabel(turn);
    if (turnUsesBook) return t('ai.chatWholeBook');
    return Number(turn.chapter_index) === Number(context.chapterIndex) ? '' : chapterLabel(turn);
  }
  function findTurn(id) { return thread && thread.querySelector('[data-ai-chat-id="' + id + '"]'); }
  function questionJumpLabel(number, question) {
    var value = t('ai.chatQuestionJump', { number: number, question: question });
    return value === 'ai.chatQuestionJump' ? 'Question ' + number + ': ' + question : value;
  }
  function updateActiveQuestion() {
    activeQuestionFrame = 0;
    if (!thread || !questionNav || questionNav.hidden) return;
    var turns = Array.prototype.slice.call(thread.querySelectorAll('.ai-chat-turn'));
    if (!turns.length) return;
    var threadTop = thread.getBoundingClientRect().top, active = turns[0];
    turns.forEach(function(turn) {
      if (turn.getBoundingClientRect().top <= threadTop + 28) active = turn;
    });
    var activeId = active.getAttribute('data-ai-chat-id');
    var activeMarker = null;
    Array.prototype.slice.call(questionNav.querySelectorAll('.ai-chat-question-marker')).forEach(function(marker) {
      var current = marker.getAttribute('data-ai-chat-target') === activeId;
      marker.classList.toggle('is-active', current);
      if (current) { marker.setAttribute('aria-current', 'true'); activeMarker = marker; } else marker.removeAttribute('aria-current');
    });
    if (activeMarker) {
      var navRect = questionNav.getBoundingClientRect(), markerRect = activeMarker.getBoundingClientRect();
      if (markerRect.top < navRect.top) questionNav.scrollTop -= navRect.top - markerRect.top;
      else if (markerRect.bottom > navRect.bottom) questionNav.scrollTop += markerRect.bottom - navRect.bottom;
    }
  }
  function scheduleActiveQuestion() {
    if (activeQuestionFrame) return;
    activeQuestionFrame = root.requestAnimationFrame(updateActiveQuestion);
  }
  function syncQuestionNavigator() {
    if (!questionNav || !thread) return;
    var turns = Array.prototype.slice.call(thread.querySelectorAll('.ai-chat-turn'));
    questionNav.textContent = '';
    questionNav.hidden = turns.length < 2;
    conversation.classList.toggle('ai-chat-conversation-has-nav', turns.length >= 2);
    turns.forEach(function(turn, index) {
      var id = turn.getAttribute('data-ai-chat-id'), questionNode = turn.querySelector('.ai-chat-message-user p');
      var question = questionNode ? questionNode.textContent.trim() : '';
      var marker = el('button', 'ai-chat-question-marker'); marker.type = 'button';
      marker.setAttribute('data-ai-chat-target', id); marker.setAttribute('aria-label', questionJumpLabel(index + 1, question)); marker.title = question;
      marker.appendChild(el('span', 'ai-chat-question-tick'));
      marker.addEventListener('click', function() {
        var target = findTurn(id); if (!target) return;
        var top = thread.scrollTop + target.getBoundingClientRect().top - thread.getBoundingClientRect().top;
        var reduced = root.matchMedia && root.matchMedia('(prefers-reduced-motion: reduce)').matches;
        thread.scrollTo({ top: top, behavior: reduced ? 'auto' : 'smooth' });
      });
      questionNav.appendChild(marker);
    });
    scheduleActiveQuestion();
  }
  function renderTurn(turn) {
    if (!turn || !turn.id || !thread) return;
    var empty = thread.querySelector('[data-ai-chat-empty]'); if (empty && empty.parentNode) empty.parentNode.removeChild(empty);
    var node = el('article', 'ai-chat-turn'); node.setAttribute('data-ai-chat-id', turn.id);
    var question = el('section', 'ai-chat-message ai-chat-message-user');
    var label = el('span', 'ai-chat-message-label', t('ai.you')), turnScope = turnScopeLabel(turn); if (turnScope) label.appendChild(el('span', 'ai-chat-chapter-pill', turnScope)); question.appendChild(label); question.appendChild(el('p', '', turn.question || '')); node.appendChild(question);
    var answer = el('section', 'ai-chat-message ai-chat-message-assistant'); answer.appendChild(el('span', 'ai-chat-message-label', t('ai.assistant')));
    if (turn.status === 'complete') { var markdown = el('div', 'ai-chat-markdown'); renderMarkdown(markdown, turn.answer || ''); answer.appendChild(markdown); }
    else answer.appendChild(el('p', 'ai-chat-pending', statusText(turn)));
    node.appendChild(answer); var existing = findTurn(turn.id), shouldScroll = !existing || threadIsNearBottom(); if (existing) thread.replaceChild(node, existing); else thread.appendChild(node); syncQuestionNavigator(); if (shouldScroll) scrollThread();
  }
  function error(message) { var note = thread.querySelector('[data-ai-chat-error]'); if (!note) { note = el('p', 'ai-chat-error'); note.setAttribute('data-ai-chat-error', ''); note.setAttribute('role', 'alert'); thread.prepend(note); } note.textContent = message; }
  function renderEmptyState() {
    var empty = el('section', 'ai-chat-empty'); empty.setAttribute('data-ai-chat-empty', '');
    empty.appendChild(el('p', '', t('ai.chatReadyPrompt')));
    var suggestions = el('div', 'ai-chat-suggestions'); suggestions.appendChild(el('span', 'ai-chat-suggestions-title', t('ai.chatSuggestions')));
    ['ai.chatSuggestionExplain', 'ai.chatSuggestionChallenge', 'ai.chatSuggestionConnect', 'ai.chatSuggestionSummarize', 'ai.chatSuggestionNotice'].forEach(function(key) {
      var suggestion = el('button', 'ai-chat-suggestion', t(key)); suggestion.type = 'button';
      suggestion.addEventListener('click', function() { input.value = suggestion.textContent; input.focus(); });
      suggestions.appendChild(suggestion);
    });
    empty.appendChild(suggestions); thread.appendChild(empty);
  }
  function loadTurns() {
    thread.textContent = ''; questionNav.textContent = ''; questionNav.hidden = true; conversation.classList.remove('ai-chat-conversation-has-nav'); thread.appendChild(el('p', 'ai-chat-loading', t('ai.chatLoading')));
    return fetchApi('/api/ai/books/' + encodeURIComponent(context.bookId) + '/chat').then(function(payload) {
      thread.textContent = ''; var turns = payload.turns || [];
      if (!turns.length) renderEmptyState();
      turns.forEach(function(turn) { renderTurn(turn); if (turn.status === 'queued' || turn.status === 'running') streamTurn(turn.id); }); scrollThread();
    }).catch(function() { thread.textContent = ''; error(t('ai.chatError')); });
  }
  function pollTurn(id, attempts) { attempts = attempts || 0; root.setTimeout(function() { fetchApi('/api/ai/books/' + encodeURIComponent(context.bookId) + '/chat').then(function(payload) { var found = (payload.turns || []).filter(function(item) { return item.id === id; })[0]; if (!found) throw Object.assign(new Error('not_found'), { code: 'not_found' }); renderTurn(found); if (found.status === 'queued' || found.status === 'running') pollTurn(id); }).catch(function(err) { if (attempts < 3) pollTurn(id, attempts + 1); else error(t('ai.error.' + (err.code || 'unknown'))); }); }, 700); }
  function streamTurn(id) {
    if (!root.EventSource) { pollTurn(id); return; }
    if (eventSources[id]) return;
    var source = new root.EventSource('/api/ai/events?chat_id=' + encodeURIComponent(id)); eventSources[id] = source;
    source.addEventListener('chat', function(event) { var payload; try { payload = JSON.parse(event.data); } catch (_) { return; } if (!payload.chat) return; renderTurn(payload.chat); if (payload.chat.status !== 'queued' && payload.chat.status !== 'running') { source.close(); delete eventSources[id]; } });
    source.onerror = function() { if (eventSources[id] !== source) return; source.close(); delete eventSources[id]; pollTurn(id); };
  }
  function submitQuestion(question, contextMode) {
    send.disabled = true;
    var payload = { question: question, language: locale(), context_mode: context && context.bookContext ? 'book_overview' : contextMode };
    if (!context || !context.bookContext) payload.chapter_index = context.chapterIndex;
    return fetchApi('/api/ai/books/' + encodeURIComponent(context.bookId) + '/chat', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) }).then(function(payload) { input.value = ''; renderTurn(payload.chat); streamTurn(payload.chat.id); }).catch(function(err) { if (err.code === 'ai_reading_required') showNoLayerChoice(question); else error(t('ai.error.' + (err.code || 'unknown'))); }).finally(function() { send.disabled = false; input.focus(); });
  }
  function showNoLayerChoice(question) {
    var prompt = el('section', 'ai-chat-empty ai-chat-context-choice'); prompt.appendChild(el('h3', '', localised('ai.chatNoReadingTitle', 'No shared reading yet', '本章尚未生成共享阅读层'))); prompt.appendChild(el('p', '', localised('ai.chatNoReadingDescription', 'Generate the shared reading layer first, or ask directly from the chapter text.', '你可以先生成共享阅读层，或直接基于本章原文提问。')));
    var generate = el('button', 'ai-chat-suggestion', localised('ai.chatGenerateFirst', 'Generate shared reading', '生成共享阅读层')); generate.type = 'button'; generate.addEventListener('click', function() { var canvas = document.querySelector('[data-ai-learning-canvas]'); if (canvas) canvas.click(); }); prompt.appendChild(generate);
    var direct = el('button', 'ai-chat-suggestion', localised('ai.chatAskSource', 'Ask from chapter text', '直接阅读原文并提问')); direct.type = 'button'; direct.addEventListener('click', function() { prompt.remove(); submitQuestion(question, 'chapter_source'); }); prompt.appendChild(direct);
    thread.appendChild(prompt); scrollThread();
  }
  function setFullscreen(next) { document.body.classList.toggle('ai-chat-fullscreen', next); var button = panel.querySelector('[data-ai-chat-fullscreen]'); button.setAttribute('aria-label', t(next ? 'ai.exitFullscreen' : 'ai.fullscreen')); button.querySelector('i').className = next ? 'fas fa-compress' : 'fas fa-expand'; }
  function close() { if (!overlay || overlay.hidden) return; overlay.hidden = true; document.body.classList.remove('ai-chat-open'); setFullscreen(false); if (previousFocus && previousFocus.focus) previousFocus.focus(); }
  function ensure() {
    if (overlay) return; overlay = el('div', 'ai-chat-overlay'); overlay.hidden = true; panel = el('aside', 'ai-chat-panel'); panel.setAttribute('role', 'complementary'); panel.setAttribute('aria-label', t('ai.chatDrawerTitle'));
    var header = el('header', 'ai-chat-header'), titles = el('div', 'ai-chat-heading'); titles.appendChild(el('h2', '', t('ai.chatDrawerTitle'))); var meta = el('div', 'ai-chat-meta'), privacy = el('span', 'ai-chat-private-badge', t('ai.chatDrawerEyebrow')); privacy.title = t('ai.chatDrawerDescription'); privacy.setAttribute('aria-label', t('ai.chatDrawerDescription')); var scope = el('span', 'ai-chat-scope'); scope.setAttribute('data-ai-chat-scope', ''); meta.appendChild(privacy); meta.appendChild(scope); titles.appendChild(meta); header.appendChild(titles);
    var actions = el('div', 'ai-chat-header-actions'), full = el('button', 'ai-chat-icon-button'); full.type = 'button'; full.setAttribute('data-ai-chat-fullscreen', ''); full.setAttribute('aria-label', t('ai.fullscreen')); full.appendChild(el('i', 'fas fa-expand')); full.addEventListener('click', function() { setFullscreen(!document.body.classList.contains('ai-chat-fullscreen')); }); var closer = el('button', 'ai-chat-icon-button'); closer.type = 'button'; closer.setAttribute('data-ai-chat-close', ''); closer.setAttribute('aria-label', t('ai.close')); closer.appendChild(el('i', 'fas fa-times')); closer.addEventListener('click', close); actions.appendChild(full); actions.appendChild(closer); header.appendChild(actions); panel.appendChild(header);
    var body = el('div', 'ai-chat-body'); conversation = el('div', 'ai-chat-conversation'); questionNav = el('nav', 'ai-chat-question-nav'); questionNav.hidden = true; questionNav.setAttribute('aria-label', t('ai.chatQuestionNavigation')); thread = el('div', 'ai-chat-thread'); thread.setAttribute('aria-live', 'polite'); thread.addEventListener('scroll', scheduleActiveQuestion, { passive: true }); conversation.appendChild(questionNav); conversation.appendChild(thread); body.appendChild(conversation); panel.appendChild(body);
    composer = el('form', 'ai-chat-composer'); var composerMain = el('div', 'ai-chat-compose-main'); input = el('textarea'); input.maxLength = 2000; input.rows = 1; input.placeholder = t('ai.followupPlaceholder'); input.setAttribute('aria-label', t('ai.followupPlaceholder')); composerMain.appendChild(input); send = el('button', 'ai-chat-send', t('ai.ask')); send.type = 'submit'; composer.appendChild(composerMain); composer.appendChild(send); input.addEventListener('keydown', function(event) { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); composer.requestSubmit(); } }); composer.addEventListener('submit', function(event) { event.preventDefault(); var question = input.value.trim(); if (question && context) submitQuestion(question, 'shared_layer'); }); panel.appendChild(composer); overlay.appendChild(panel); document.body.appendChild(overlay); document.addEventListener('keydown', function(event) { if (event.key === 'Escape' && !overlay.hidden) close(); });
  }
  function availability() { return fetchApi('/api/ai/status').then(function(status) { if (!status.enabled) throw Object.assign(new Error('ai_disabled'), { code: 'ai_disabled' }); if (!status.authorized) throw Object.assign(new Error('ai_not_authorized'), { code: 'ai_not_authorized' }); }); }
  function open(nextContext, button) { availability().then(function() { if (root.EpubBrowserAIRich && root.EpubBrowserAIRich.loadStyle) root.EpubBrowserAIRich.loadStyle('aiChatCss'); context = nextContext; if (!context.bookContext && !Number.isInteger(context.chapterIndex)) throw Object.assign(new Error('invalid_chapter_index'), { code: 'invalid_chapter_index' }); ensure(); previousFocus = button; var scope = panel.querySelector('[data-ai-chat-scope]'), scopeLabel = drawerScope(context); if (scope) { scope.textContent = chapterScope(context); scope.title = scopeLabel; scope.setAttribute('aria-label', scopeLabel); } overlay.hidden = false; document.body.classList.add('ai-chat-open'); panel.querySelector('[data-ai-chat-close]').focus(); loadTurns(); }).catch(function(err) { if (root.EpubBrowserNotification && root.EpubBrowserNotification.show) root.EpubBrowserNotification.show(t('ai.error.' + (err.code || 'unknown')), 'error'); }); }
  function init() { var buttons = document.querySelectorAll('[data-ai-followup-drawer]'), bookButtons = document.querySelectorAll('[data-ai-book-chat]'); if ((!buttons.length && !bookButtons.length) || !root.EpubBrowserAuth || !root.EpubBrowserAuth.fetch) return; buttons.forEach(function(button) { function currentContext() { return chapterContext(button); } if (document.body.classList.contains('pagination-mode')) { button.disabled = true; button.setAttribute('aria-disabled', 'true'); button.title = t('ai.unavailableInPagination'); return; } updateTriggerScope(button, currentContext()); button.addEventListener('mouseenter', function() { updateTriggerScope(button, currentContext()); }); button.addEventListener('focus', function() { updateTriggerScope(button, currentContext()); }); button.addEventListener('click', function() { open(currentContext(), button); }); }); bookButtons.forEach(function(button) { var bookContext = { bookId: button.getAttribute('data-book-id'), chapterIndex: null, bookContext: true }; updateTriggerScope(button, bookContext); button.addEventListener('click', function() { open(bookContext, button); }); }); }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})(window);
