(function(root) {
  'use strict';
  if (!root || root.EpubBrowserMode !== 'server' || !root.document) return;

  var document = root.document;
  var panel;
  var requestContext;

  function t(key, params) {
    var i18n = root.EpubBrowserI18n;
    return i18n && i18n.t ? i18n.t(key, params) : key;
  }

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function action(label, handler, primary) {
    var button = el('button', primary ? 'ai-reading-primary' : 'ai-reading-action', t(label));
    button.type = 'button';
    button.addEventListener('click', handler);
    return button;
  }

  function fetchApi(url, options) {
    if (!root.EpubBrowserAuth || !root.EpubBrowserAuth.fetch) return Promise.reject(new Error('auth'));
    return root.EpubBrowserAuth.fetch(url, options).then(function(response) {
      return response.json().catch(function() { return {}; }).then(function(payload) {
        if (!response.ok) {
          var error = new Error(payload.code || 'ai_generation_failed');
          error.code = payload.code || 'ai_generation_failed';
          throw error;
        }
        return payload;
      });
    });
  }

  function showError(error) {
    var status = panel && panel.querySelector('[data-ai-status]');
    if (status) status.textContent = t('ai.error.' + (error && error.code || 'unknown'));
  }

  function ensurePanel() {
    if (panel) return panel;
    panel = el('section', 'ai-reading-panel');
    panel.setAttribute('role', 'dialog');
    panel.setAttribute('aria-modal', 'true');
    panel.setAttribute('aria-label', t('ai.title'));
    panel.hidden = true;
    document.body.appendChild(panel);
    return panel;
  }

  function openPanel(context) {
    requestContext = context;
    var target = ensurePanel();
    target.textContent = '';
    var header = el('div', 'ai-reading-header');
    header.appendChild(el('h2', '', t(context.scope === 'book' ? 'ai.bookGuide' : 'ai.chapterRead')));
    header.appendChild(action('ai.close', closePanel));
    target.appendChild(header);
    var body = el('div', 'ai-reading-body');
    var status = el('p', 'ai-reading-status', '');
    status.setAttribute('data-ai-status', '');
    body.appendChild(status);
    if (context.scope === 'book') {
      body.appendChild(el('p', 'ai-reading-copy', t('ai.bookModeHelp')));
      var select = el('select', 'ai-reading-mode');
      select.setAttribute('aria-label', t('ai.mode'));
      ['spoiler_free', 'read_so_far', 'full_review'].forEach(function(mode) {
        var option = el('option', '', t('ai.mode.' + mode));
        option.value = mode;
        select.appendChild(option);
      });
      body.appendChild(select);
      body.appendChild(action('ai.generate', function() {
        context.mode = select.value;
        startGeneration(context, false);
      }, true));
    } else {
      startGeneration(context, false);
    }
    target.appendChild(body);
    target.hidden = false;
  }

  function closePanel() {
    if (panel) panel.hidden = true;
  }

  function addResult(result) {
    var body = panel.querySelector('.ai-reading-body');
    body.textContent = '';
    var content = result.content || {};
    var quick = content.quick || {};
    var structure = content.structure || {};
    var deep = content.deep || {};
    body.appendChild(el('h3', 'ai-reading-result-title', quick.title || t('ai.result')));
    body.appendChild(el('p', 'ai-reading-summary', quick.summary || ''));
    addList(body, 'ai.quickPoints', quick.key_points || []);
    body.appendChild(el('h4', '', t('ai.structure')));
    body.appendChild(el('p', '', structure.overview || ''));
    var map = el('div', 'ai-reading-map');
    (structure.nodes || []).forEach(function(node) {
      var item = el('div', 'ai-reading-map-node');
      item.appendChild(el('strong', '', node.label || ''));
      item.appendChild(el('span', '', node.detail || ''));
      map.appendChild(item);
    });
    body.appendChild(map);
    addList(body, 'ai.deepThemes', deep.themes || []);
    addList(body, 'ai.deepQuestions', deep.questions || []);
    addList(body, 'ai.deepApplications', deep.applications || []);
    var evidence = content.evidence || [];
    if (evidence.length) {
      body.appendChild(el('h4', '', t('ai.evidence')));
      evidence.forEach(function(item) {
        var card = el('blockquote', 'ai-reading-evidence');
        card.appendChild(el('p', '', item.quote || ''));
        card.appendChild(el('footer', '', item.reason || ''));
        if (requestContext.scope === 'book' && Number.isInteger(item.chapter_index)) {
          var link = el('a', '', t('ai.openEvidence'));
          link.href = 'chapter_' + item.chapter_index + '.html';
          card.appendChild(link);
        }
        body.appendChild(card);
      });
    }
    var rerun = action('ai.regenerate', function() { startGeneration(requestContext, true); });
    body.appendChild(rerun);
    addFollowup(body, result.id);
  }

  function addList(parent, label, values) {
    if (!values || !values.length) return;
    parent.appendChild(el('h4', '', t(label)));
    var list = el('ul', 'ai-reading-list');
    values.forEach(function(value) { list.appendChild(el('li', '', value)); });
    parent.appendChild(list);
  }

  function addFollowup(parent, resultId) {
    var form = el('form', 'ai-reading-followup');
    var input = el('input', '');
    input.type = 'text';
    input.maxLength = 2000;
    input.placeholder = t('ai.followupPlaceholder');
    input.setAttribute('aria-label', t('ai.followupPlaceholder'));
    form.appendChild(input);
    form.appendChild(action('ai.ask', function() {
      var question = input.value.trim();
      if (!question) return;
      fetchApi('/api/ai/followups', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ result_id: resultId, question: question, language: locale() })
      }).then(function(payload) {
        input.value = '';
        pollFollowup(resultId, payload.followup.id, parent);
      }).catch(showError);
    }, true));
    parent.appendChild(form);
  }

  function pollFollowup(resultId, id, parent) {
    function poll() {
      fetchApi('/api/ai/results/' + encodeURIComponent(resultId) + '/followups').then(function(payload) {
        var found = (payload.followups || []).filter(function(item) { return item.id === id; })[0];
        if (!found || found.status === 'queued' || found.status === 'running') return root.setTimeout(poll, 700);
        if (found.status !== 'complete') throw Object.assign(new Error(found.error_code), { code: found.error_code });
        var answer = el('section', 'ai-reading-answer');
        answer.appendChild(el('h4', '', t('ai.answer')));
        answer.appendChild(el('p', '', found.answer || ''));
        parent.appendChild(answer);
      }).catch(showError);
    }
    poll();
  }

  function pollJob(jobId, context) {
    var status = panel.querySelector('[data-ai-status]');
    function poll() {
      fetchApi('/api/ai/jobs/' + encodeURIComponent(jobId)).then(function(payload) {
        var job = payload.job || {};
        if (job.status === 'queued' || job.status === 'running') {
          status.textContent = t('ai.generating', { current: job.progress_current || 0, total: job.progress_total || 1 });
          return root.setTimeout(poll, 700);
        }
        if (job.status !== 'complete') throw Object.assign(new Error(job.error_code), { code: job.error_code });
        if (!payload.result) throw Object.assign(new Error('ai_result_not_found'), { code: 'ai_result_not_found' });
        addResult(payload.result);
      }).catch(showError);
    }
    poll();
  }

  function startGeneration(context, force) {
    var status = panel.querySelector('[data-ai-status]');
    if (status) status.textContent = t('ai.generating', { current: 0, total: 1 });
    fetchApi('/api/ai/reading', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        scope: context.scope, book_id: context.bookId, chapter_index: context.chapterIndex,
        mode: context.mode || 'chapter', language: locale(), force: Boolean(force)
      })
    }).then(function(payload) {
      if (payload.status === 'complete') return addResult(payload.result);
      pollJob(payload.job.id, context);
    }).catch(showError);
  }

  function locale() {
    var i18n = root.EpubBrowserI18n;
    return i18n && i18n.getLocale ? i18n.getLocale() : 'en';
  }

  function init() {
    var chapter = document.querySelector('[data-ai-reading-chapter]');
    var book = document.querySelector('[data-ai-reading-book]');
    function allowed(status) {
      if (book) refreshEffectiveTags(book.getAttribute('data-book-id'));
      if (!status || !status.authorized) {
        if (chapter) chapter.hidden = true;
        if (book) book.hidden = true;
        return;
      }
      if (chapter) chapter.addEventListener('click', function() {
        openPanel({ scope: 'chapter', bookId: chapter.getAttribute('data-book-id'), chapterIndex: Number(chapter.getAttribute('data-chapter-index')), mode: 'chapter' });
      });
      if (book) book.addEventListener('click', function() {
        openPanel({ scope: 'book', bookId: book.getAttribute('data-book-id'), mode: 'spoiler_free' });
      });
    }
    if (!chapter && !book) return;
    fetchApi('/api/ai/status', { method: 'GET' }).then(allowed).catch(function() {
      if (chapter) chapter.hidden = true;
      if (book) book.hidden = true;
    });
  }

  function refreshEffectiveTags(bookId) {
    var container = document.querySelector('.book-info-tags');
    if (!container) return;
    fetchApi('/api/books/' + encodeURIComponent(bookId) + '/metadata', { method: 'GET' })
      .then(function(payload) {
        container.textContent = '';
        (payload.tags || []).forEach(function(tag) {
          container.appendChild(el('span', 'book-tag', tag));
        });
      }).catch(function() {});
  }

  document.addEventListener('DOMContentLoaded', function() {
    if (!root.EpubBrowserAuth || !root.EpubBrowserAuth.init) return;
    root.EpubBrowserAuth.init().then(function(session) { if (session) init(); });
  });
})(window);
