(function(root) {
  'use strict';
  if (!root || root.EpubBrowserMode !== 'server' || !root.document) return;

  var document = root.document;
  var panel;
  var overlay;
  var requestContext;
  var activeRun = 0;
  var focusReturn;
  var evidenceMarks = [];
  var evidenceResultId;
  var insightPopover;

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
    if (!status && panel) {
      status = el('p', 'ai-reading-status ai-reading-status-error');
      status.setAttribute('data-ai-status', '');
      status.setAttribute('role', 'alert');
      panel.querySelector('.ai-reading-body').prepend(status);
    }
    if (status) status.textContent = t('ai.error.' + (error && error.code || 'unknown'));
  }

  function ensurePanel() {
    if (panel) return panel;
    overlay = el('div', 'ai-reading-overlay');
    overlay.hidden = true;
    panel = el('section', 'ai-reading-panel');
    panel.setAttribute('role', 'dialog');
    panel.setAttribute('aria-modal', 'false');
    panel.setAttribute('aria-label', t('ai.title'));
    panel.tabIndex = -1;
    overlay.appendChild(panel);
    overlay.addEventListener('click', function(event) {
      if (event.target === overlay) closePanel();
    });
    document.addEventListener('keydown', function(event) {
      if (event.key === 'Escape') {
        if (insightPopover) {
          closeInsightPopover();
        } else if (overlay && !overlay.hidden) {
          closePanel();
        }
      }
    });
    document.body.appendChild(overlay);
    return panel;
  }

  function closeButton() {
    var button = el('button', 'ai-reading-close');
    button.type = 'button';
    button.setAttribute('aria-label', t('ai.close'));
    button.setAttribute('title', t('ai.close'));
    var icon = el('i', 'fas fa-times');
    icon.setAttribute('aria-hidden', 'true');
    button.appendChild(icon);
    button.addEventListener('click', closePanel);
    return button;
  }

  function addProgress(body) {
    var progress = el('div', 'ai-reading-progress');
    var status = el('p', 'ai-reading-status', '');
    var meter = el('progress', 'ai-reading-progress-meter');
    status.setAttribute('data-ai-status', '');
    status.setAttribute('role', 'status');
    status.setAttribute('aria-live', 'polite');
    meter.max = 1;
    meter.value = 0;
    meter.setAttribute('aria-label', t('ai.progress'));
    progress.appendChild(status);
    progress.appendChild(meter);
    body.appendChild(progress);
    return { root: progress, status: status, meter: meter };
  }

  function setProgress(progress, status, current, total) {
    if (!progress) return;
    var safeTotal = Math.max(1, Number(total) || 1);
    var safeCurrent = Math.min(safeTotal, Math.max(0, Number(current) || 0));
    var key = status === 'queued' ? 'ai.queued' : 'ai.generating';
    var message = t(key, { current: safeCurrent, total: safeTotal });
    progress.root.hidden = false;
    progress.status.textContent = message;
    progress.meter.max = safeTotal;
    progress.meter.value = safeCurrent;
    progress.meter.setAttribute('aria-valuetext', message);
  }

  function openPanel(context, trigger) {
    activeRun += 1;
    requestContext = context;
    focusReturn = trigger || document.activeElement;
    var target = ensurePanel();
    target.textContent = '';
    var header = el('div', 'ai-reading-header');
    var title = el('h2', '', t(context.scope === 'book' ? 'ai.bookGuide' : 'ai.chapterRead'));
    title.id = 'aiReadingTitle';
    target.setAttribute('aria-labelledby', title.id);
    header.appendChild(title);
    var close = closeButton();
    header.appendChild(close);
    target.appendChild(header);
    var body = el('div', 'ai-reading-body');
    context.progress = addProgress(body);
    // Chapter reading begins immediately, so its progress container must be
    // attached before startGeneration can look it up again.
    target.appendChild(body);
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
      var generate = action('ai.generate', function() {
        context.mode = select.value;
        startGeneration(context, false);
      }, true);
      context.generateButton = generate;
      body.appendChild(generate);
    } else {
      startGeneration(context, false);
    }
    overlay.hidden = false;
    document.body.classList.add('ai-reading-open');
    close.focus();
  }

  function closePanel() {
    activeRun += 1;
    if (overlay) overlay.hidden = true;
    document.body.classList.remove('ai-reading-open');
    if (focusReturn && typeof focusReturn.focus === 'function') focusReturn.focus();
  }

  function addResult(result) {
    if (evidenceMarks.length && evidenceResultId !== result.id) clearEvidenceMarks();
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
    addInsightCards(body, 'ai.deepThemes', deep.themes || [], ['title', 'theme'], ['analysis', 'explanation']);
    addInsightCards(body, 'ai.deepQuestions', deep.questions || [], ['question'], ['why', 'context', 'reflection']);
    addInsightCards(body, 'ai.deepApplications', deep.applications || [], ['context', 'scenario'], ['advice', 'application', 'suggestion']);
    var evidence = content.evidence || [];
    if (evidence.length) {
      body.appendChild(el('h4', '', t('ai.evidence')));
      if (requestContext.scope === 'chapter') addEvidenceHighlightControl(body, evidence, result.id);
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

  function addEvidenceHighlightControl(parent, evidence, resultId) {
    var control = action('ai.showEvidenceHighlights', function() {
      if (evidenceMarks.length && evidenceResultId === resultId) {
        clearEvidenceMarks();
        control.textContent = t('ai.showEvidenceHighlights', { count: evidence.length });
        return;
      }
      var found = showEvidenceMarks(evidence);
      if (!found) {
        showEvidenceNotice(parent, 'ai.noEvidenceHighlights');
        return;
      }
      evidenceResultId = resultId;
      control.textContent = t('ai.hideEvidenceHighlights', { count: found });
    });
    control.classList.add('ai-reading-evidence-toggle');
    control.textContent = evidenceMarks.length && evidenceResultId === resultId
      ? t('ai.hideEvidenceHighlights', { count: evidenceMarks.length })
      : t('ai.showEvidenceHighlights', { count: evidence.length });
    parent.appendChild(control);
  }

  function showEvidenceNotice(parent, key) {
    var notice = parent.querySelector('[data-ai-evidence-notice]');
    if (!notice) {
      notice = el('p', 'ai-reading-status');
      notice.setAttribute('data-ai-evidence-notice', '');
      notice.setAttribute('role', 'status');
      parent.appendChild(notice);
    }
    notice.textContent = t(key);
  }

  function showEvidenceMarks(evidence) {
    var article = document.querySelector('#eb-content');
    if (!article) return 0;
    evidence.forEach(function(item, index) {
      var mark = markEvidenceQuote(article, item && item.quote, item && item.reason, index);
      if (mark) evidenceMarks.push(mark);
    });
    if (evidenceMarks.length) {
      var reduceMotion = root.matchMedia && root.matchMedia('(prefers-reduced-motion: reduce)').matches;
      evidenceMarks[0].scrollIntoView({ block: 'center', behavior: reduceMotion ? 'auto' : 'smooth' });
    }
    return evidenceMarks.length;
  }

  function markEvidenceQuote(article, quote, reason, index) {
    var needle = String(quote || '').trim();
    if (needle.length < 8) return null;
    var walker = document.createTreeWalker(article, root.NodeFilter ? root.NodeFilter.SHOW_TEXT : 4);
    var node;
    while ((node = walker.nextNode())) {
      if (!node.parentElement || node.parentElement.closest('.ai-evidence-mark, script, style, noscript')) continue;
      var start = node.nodeValue.indexOf(needle);
      if (start < 0) continue;
      var range = document.createRange();
      range.setStart(node, start);
      range.setEnd(node, start + needle.length);
      var mark = el('mark', 'ai-evidence-mark');
      mark.setAttribute('data-ai-evidence-color', String(index % 4));
      mark.setAttribute('data-ai-evidence-reason', String(reason || ''));
      mark.tabIndex = 0;
      mark.setAttribute('role', 'button');
      mark.setAttribute('aria-label', t('ai.evidenceInsight', { reason: reason || '' }));
      range.surroundContents(mark);
      mark.addEventListener('click', function() { showInsightPopover(mark); });
      mark.addEventListener('keydown', function(event) {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          showInsightPopover(mark);
        }
      });
      return mark;
    }
    return null;
  }

  function clearEvidenceMarks() {
    closeInsightPopover();
    evidenceMarks.forEach(function(mark) {
      if (!mark || !mark.parentNode) return;
      var parent = mark.parentNode;
      while (mark.firstChild) parent.insertBefore(mark.firstChild, mark);
      parent.removeChild(mark);
      parent.normalize();
    });
    evidenceMarks = [];
    evidenceResultId = undefined;
  }

  function showInsightPopover(mark) {
    closeInsightPopover();
    var popover = el('section', 'ai-evidence-popover');
    popover.setAttribute('role', 'dialog');
    popover.setAttribute('aria-label', t('ai.evidence'));
    var header = el('div', 'ai-evidence-popover-header');
    header.appendChild(el('strong', '', t('ai.evidenceInsightLabel')));
    var close = el('button', 'ai-evidence-popover-close');
    close.type = 'button';
    close.setAttribute('aria-label', t('ai.close'));
    close.appendChild(el('i', 'fas fa-times'));
    close.addEventListener('click', closeInsightPopover);
    header.appendChild(close);
    popover.appendChild(header);
    popover.appendChild(el('p', '', mark.getAttribute('data-ai-evidence-reason') || t('ai.evidence')));
    document.body.appendChild(popover);
    var rect = mark.getBoundingClientRect();
    popover.style.top = Math.min(root.innerHeight - popover.offsetHeight - 12, rect.bottom + 8) + 'px';
    popover.style.left = Math.min(root.innerWidth - popover.offsetWidth - 12, Math.max(12, rect.left)) + 'px';
    insightPopover = popover;
    close.focus();
  }

  function closeInsightPopover() {
    if (!insightPopover) return;
    insightPopover.remove();
    insightPopover = null;
  }

  function addList(parent, label, values) {
    if (!values || !values.length) return;
    parent.appendChild(el('h4', '', t(label)));
    var list = el('ul', 'ai-reading-list');
    values.forEach(function(value) { list.appendChild(el('li', '', value)); });
    parent.appendChild(list);
  }

  function addInsightCards(parent, label, values, titleKeys, detailKeys) {
    if (!values || !values.length) return;
    parent.appendChild(el('h4', '', t(label)));
    var group = el('div', 'ai-reading-insight-list');
    values.forEach(function(value) {
      var item = normaliseInsight(value, titleKeys, detailKeys);
      if (!item.title && !item.detail) return;
      var card = el('article', 'ai-reading-insight');
      if (item.title) card.appendChild(el('strong', '', item.title));
      if (item.detail) card.appendChild(el('p', '', item.detail));
      group.appendChild(card);
    });
    if (group.childNodes.length) parent.appendChild(group);
  }

  function normaliseInsight(value, titleKeys, detailKeys) {
    var item = value;
    if (typeof value === 'string') item = parseLegacyObject(value, titleKeys.concat(detailKeys));
    if (!item || typeof item !== 'object' || Array.isArray(item)) {
      return { title: '', detail: String(value || '').trim() };
    }
    return {
      title: firstInsightValue(item, titleKeys),
      detail: firstInsightValue(item, detailKeys)
    };
  }

  function firstInsightValue(item, keys) {
    for (var index = 0; index < keys.length; index += 1) {
      var value = item[keys[index]];
      if (typeof value === 'string' && value.trim()) return value.trim();
    }
    return '';
  }

  function parseLegacyObject(value, keys) {
    try {
      var parsed = JSON.parse(value);
      if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) return parsed;
    } catch (ignore) {
      // AI results created before the typed report contract used Python-style
      // dictionary strings. Extract only the known display fields; never eval.
    }
    var source = String(value || '').trim();
    if (source.charAt(0) !== '{') return null;
    var parsedLegacy = {};
    keys.forEach(function(key) {
      var escaped = key.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
      var expression = new RegExp("['\\\"]" + escaped + "['\\\"]\\s*:\\s*['\\\"]([\\s\\S]*?)['\\\"](?=\\s*,\\s*['\\\"][A-Za-z_]+['\\\"]\\s*:|\\s*}\\s*$)");
      var match = source.match(expression);
      if (match && match[1]) parsedLegacy[key] = match[1].replace(/\\\\(['\\\"])/g, '$1').trim();
    });
    return Object.keys(parsedLegacy).length ? parsedLegacy : null;
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

  function pollJob(jobId, context, run) {
    function poll() {
      if (run !== activeRun || !overlay || overlay.hidden) return;
      fetchApi('/api/ai/jobs/' + encodeURIComponent(jobId)).then(function(payload) {
        if (run !== activeRun || overlay.hidden) return;
        var job = payload.job || {};
        if (job.status === 'queued' || job.status === 'running') {
          setProgress(
            context.progress,
            job.status,
            job.progress_current || 0,
            job.progress_total || 1
          );
          return root.setTimeout(poll, 700);
        }
        if (job.status !== 'complete') throw Object.assign(new Error(job.error_code), { code: job.error_code });
        if (!payload.result) throw Object.assign(new Error('ai_result_not_found'), { code: 'ai_result_not_found' });
        if (context.generateButton) context.generateButton.disabled = false;
        addResult(payload.result);
      }).catch(function(error) {
        if (run === activeRun) {
          if (context.generateButton) context.generateButton.disabled = false;
          showError(error);
        }
      });
    }
    poll();
  }

  function startGeneration(context, force) {
    var run = activeRun;
    if (!context.progress || !panel.contains(context.progress.root)) {
      var body = panel.querySelector('.ai-reading-body');
      body.textContent = '';
      context.progress = addProgress(body);
    }
    if (context.generateButton) context.generateButton.disabled = true;
    setProgress(context.progress, 'queued', 0, 1);
    fetchApi('/api/ai/reading', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        scope: context.scope, book_id: context.bookId, chapter_index: context.chapterIndex,
        mode: context.mode || 'chapter', language: locale(), force: Boolean(force)
      })
    }).then(function(payload) {
      if (run !== activeRun || !overlay || overlay.hidden) return;
      if (payload.status === 'complete') return addResult(payload.result);
      if (payload.job) {
        setProgress(
          context.progress,
          payload.job.status,
          payload.job.progress_current || 0,
          payload.job.progress_total || 1
        );
      }
      pollJob(payload.job.id, context, run);
    }).catch(function(error) {
      if (run === activeRun) {
        if (context.generateButton) context.generateButton.disabled = false;
        showError(error);
      }
    });
  }

  function locale() {
    var i18n = root.EpubBrowserI18n;
    return i18n && i18n.getLocale ? i18n.getLocale() : 'en';
  }

  function bindControl(control, context) {
    if (!control || control.getAttribute('data-ai-reading-bound') === 'true') return;
    control.setAttribute('data-ai-reading-bound', 'true');
    control.addEventListener('click', function() {
      // The server is the authority for AI access.  Never make the trigger
      // disappear because an optional status probe fails in the browser.
      openPanel(context(), control);
    });
  }

  function init() {
    var chapter = document.querySelector('[data-ai-reading-chapter]');
    var book = document.querySelector('[data-ai-reading-book]');
    if (!chapter && !book) return;

    bindControl(chapter, function() {
      return {
        scope: 'chapter',
        bookId: chapter.getAttribute('data-book-id'),
        chapterIndex: Number(chapter.getAttribute('data-chapter-index')),
        mode: 'chapter'
      };
    });
    bindControl(book, function() {
      return {
        scope: 'book',
        bookId: book.getAttribute('data-book-id'),
        mode: 'spoiler_free'
      };
    });
    if (book) refreshEffectiveTags(book.getAttribute('data-book-id'));
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
    init();
    root.EpubBrowserAuth.init();
  });
})(window);
