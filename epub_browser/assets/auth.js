(function(root, factory) {
  var exported = factory();
  if (typeof module === 'object' && module.exports) module.exports = exported;
  if (root && root.document) root.EpubBrowserAuth = exported.create(root);
})(typeof window !== 'undefined' ? window : (typeof globalThis !== 'undefined' ? globalThis : this), function() {
  'use strict';

  function create(root) {
    var sessionState = null;
    var sessionRequest = null;
    var redirecting = false;
    var initialized = false;
    var users = [];
    var books = [];
    var identities = [];
    var aiSettings = null;
    var aiTags = [];
    var aiJobsState = {
      status: '',
      page: 1,
      pageSize: 20,
      totalPages: 0,
      total: 0,
      loading: false
    };
    var aiJobsRows = [];
    var aiJobsPollTimer = null;
    var aiJobsRequestGeneration = 0;
    var aiJobsPendingRequests = 0;
    var aiJobsRetrying = {};
    var aiJobsRetryRequests = {};
    var aiProfileTranslationKeys = {
      auto: 'admin.ai.profile.auto',
      technical: 'admin.ai.profile.technical',
      fiction: 'admin.ai.profile.fiction',
      general: 'admin.ai.profile.general'
    };

    function i18n() {
      return root.EpubBrowserI18n;
    }

    function t(key, params) {
      var runtime = i18n();
      return runtime && runtime.t ? runtime.t(key, params) : key;
    }

    function copyHeaders(source) {
      var copied = {};
      if (!source) return copied;
      if (typeof source.forEach === 'function') {
        source.forEach(function(value, key) { copied[key] = value; });
        return copied;
      }
      Object.keys(source).forEach(function(key) { copied[key] = source[key]; });
      return copied;
    }

    function requestOptions(options, csrfToken, url) {
      var prepared = {};
      var original = options || {};
      Object.keys(original).forEach(function(key) {
        if (key !== 'headers') prepared[key] = original[key];
      });
      prepared.credentials = 'same-origin';
      prepared.headers = copyHeaders(original.headers);
      if (csrfToken && isUnsafe(prepared.method) && isSameOrigin(url)) {
        prepared.headers['X-CSRF-Token'] = csrfToken;
      }
      return prepared;
    }

    function isUnsafe(method) {
      var normalized = String(method || 'GET').toUpperCase();
      return ['GET', 'HEAD', 'OPTIONS', 'TRACE'].indexOf(normalized) === -1;
    }

    function isSameOrigin(url) {
      var value = String(url || '');
      var origin = root.location && root.location.origin;
      if (value.charAt(0) === '/' && value.charAt(1) !== '/') return true;
      if (!/^[a-z][a-z0-9+.-]*:/i.test(value) && value.indexOf('//') !== 0) return true;
      if (!origin) return false;
      try {
        return new URL(value, origin).origin === origin;
      } catch (error) {
        return false;
      }
    }

    function loginTarget() {
      var location = root.location || {};
      var current = String(location.pathname || '/') + String(location.search || '') + String(location.hash || '');
      if (current.indexOf('/login') === 0) return '/login';
      return '/login?next=' + encodeURIComponent(current);
    }

    function redirectToLogin() {
      if (redirecting) return;
      redirecting = true;
      if (root.location && typeof root.location.assign === 'function') {
        root.location.assign(loginTarget());
      } else if (root.location) {
        root.location.href = loginTarget();
      }
    }

    function handleUnauthorized(response) {
      if (!response || response.status !== 401 || typeof response.clone !== 'function') {
        return response;
      }
      return readJson(response.clone()).then(function(payload) {
        if (payload && payload.code === 'authentication_required') redirectToLogin();
        return response;
      });
    }

    function rawFetch(url, options) {
      return Promise.resolve(root.fetch(url, requestOptions(options, null, url)));
    }

    function readJson(response) {
      if (!response || typeof response.json !== 'function') return Promise.resolve({});
      return Promise.resolve(response.json()).catch(function() { return {}; });
    }

    function csrfRequired(response) {
      if (!response || response.status !== 403 || typeof response.clone !== 'function') {
        return Promise.resolve(false);
      }
      return readJson(response.clone()).then(function(payload) {
        return Boolean(payload && payload.code === 'csrf_required');
      });
    }

    function setSession(payload) {
      sessionState = payload && payload.user ? payload : null;
      return sessionState;
    }

    function loadSession(force) {
      if (root.EpubBrowserMode !== 'server') return Promise.resolve(null);
      if (!force && sessionState) return Promise.resolve(sessionState);
      if (!force && sessionRequest) return sessionRequest;
      sessionRequest = rawFetch('/api/session', { method: 'GET' })
        .then(handleUnauthorized)
        .then(function(response) {
          if (!response || !response.ok) return null;
          return readJson(response).then(setSession);
        })
        .finally(function() { sessionRequest = null; });
      return sessionRequest;
    }

    function authenticatedFetch(url, options) {
      if (root.EpubBrowserMode !== 'server') return Promise.resolve(null);
      var unsafe = isUnsafe(options && options.method);
      var sameOrigin = isSameOrigin(url);
      var needsSession = unsafe && sameOrigin && !(sessionState && sessionState.csrf_token);
      var ready = needsSession ? loadSession(false) : Promise.resolve(sessionState);
      function send() {
        var csrfToken = sessionState && sessionState.csrf_token;
        return Promise.resolve(root.fetch(url, requestOptions(options, csrfToken, url)))
          .then(handleUnauthorized);
      }
      return ready.then(send).then(function(response) {
        if (!unsafe || !sameOrigin) return response;
        return csrfRequired(response).then(function(needsRefresh) {
          if (!needsRefresh) return response;
          return loadSession(true).then(function(session) {
            if (!session || !session.csrf_token) return response;
            return send();
          });
        });
      });
    }

    function logout() {
      return authenticatedFetch('/logout', { method: 'POST' }).then(function(response) {
        sessionState = null;
        if (response && response.status !== 401) redirectToLogin();
        return response;
      });
    }

    function pageAuthenticationNonce() {
      if (!root.document || !root.document.querySelector) return '';
      var meta = root.document.querySelector('meta[name="epub-browser-auth-nonce"]');
      return meta && meta.content ? meta.content : '';
    }

    function associate(credentials) {
      var options = {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(credentials || {})
      };
      var csrfToken = sessionState && sessionState.csrf_token;
      if (!csrfToken) {
        options.headers['X-EPUB-Browser-Auth-Nonce'] = pageAuthenticationNonce();
      }
      return Promise.resolve(root.fetch(
        '/api/identity/link',
        requestOptions(options, csrfToken, '/api/identity/link')
      ));
    }

    function element(id) {
      return root.document && root.document.getElementById
        ? root.document.getElementById(id)
        : null;
    }

    function formValue(form, name) {
      var field = form && form.elements && form.elements[name];
      return field ? field.value : '';
    }

    function clearPasswordFields(form) {
      if (!form || !form.querySelectorAll) return;
      Array.prototype.forEach.call(form.querySelectorAll('input[type="password"]'), function(field) {
        field.value = '';
      });
    }

    function messageKey(scope, code) {
      var known = scope === 'admin' ? {
        invalid_user: true,
        username_unavailable: true,
        invalid_password: true,
        last_enabled_admin: true,
        not_found: true,
        invalid_visibility: true,
        invalid_identity: true,
        identity_already_linked: true,
        user_disabled: true,
        forbidden: true,
        csrf_required: true,
        network: true
      } : {
        authentication_required: true,
        csrf_required: true,
        forbidden: true,
        invalid_credentials: true,
        invalid_password: true,
        proxy_identity_required: true,
        identity_already_linked: true,
        not_found: true,
        network: true
      };
      return scope + '.error.' + (known[code] ? code : 'unknown');
    }

    function showStatus(key, type, params) {
      var notification = root.EpubBrowserNotification;
      if (notification && typeof notification.show === 'function') {
        notification.show(t(key, params), type || 'info');
        return;
      }
      var status = element('accountStatus');
      if (!status) return;
      status.textContent = t(key, params);
      status.className = 'account-status ' + (type || 'info');
      status.hidden = false;
    }

    function showResponseError(response, scope) {
      return readJson(response).then(function(payload) {
        showStatus(messageKey(scope, payload && payload.code), 'error');
        return payload;
      });
    }

    function createTextElement(tag, className, key, params) {
      var node = root.document.createElement(tag);
      if (className) node.className = className;
      if (key) {
        node.setAttribute('data-i18n', key);
        if (params) node.setAttribute('data-i18n-params', JSON.stringify(params));
        node.textContent = t(key, params);
      }
      return node;
    }

    function actionButton(key, action, variant) {
      var className = 'bookshelf-action-btn account-inline-action';
      if (variant === 'danger') className += ' account-danger-action';
      var button = createTextElement('button', className, key);
      button.type = 'button';
      button.addEventListener('click', action);
      return button;
    }

    function formatDate(value) {
      var runtime = i18n();
      return runtime && runtime.formatDate
        ? runtime.formatDate(value, { dateStyle: 'medium', timeStyle: 'short' })
        : String(value || '');
    }

    function safeAiJobDate(value) {
      if (typeof value !== 'string' && typeof value !== 'number') {
        return t('admin.ai.jobs.unknownValue');
      }
      var parsed = new Date(value);
      if (!isFinite(parsed.getTime())) return t('admin.ai.jobs.unknownValue');
      try {
        return formatDate(parsed.toISOString());
      } catch (error) {
        return t('admin.ai.jobs.unknownValue');
      }
    }

    function safeNonNegativeInteger(value, fallback) {
      if (value === null || value === '' || typeof value === 'boolean') return fallback;
      var number = Number(value);
      return isFinite(number) && number >= 0 && Math.floor(number) === number
        ? number
        : fallback;
    }

    function hasOwn(mapping, key) {
      return Object.prototype.hasOwnProperty.call(mapping, key);
    }

    function aiJobStatusKey(status) {
      var known = {
        queued: true,
        running: true,
        complete: true,
        failed: true,
        interrupted: true
      };
      return hasOwn(known, status)
        ? 'admin.ai.jobs.status.' + status
        : 'admin.ai.jobs.unknownValue';
    }

    function aiJobStoredErrorKey(code) {
      var known = {
        ai_disabled: true,
        ai_not_authorized: true,
        ai_quota_exhausted: true,
        provider_connection_failed: true,
        provider_rate_limited: true,
        provider_request_rejected: true,
        provider_server_error: true,
        provider_invalid_response: true,
        ai_result_not_found: true,
        ai_reading_required: true,
        invalid_ai_chat: true,
        ai_generation_failed: true
      };
      if (!code) return '';
      return hasOwn(known, code)
        ? 'ai.error.' + code
        : 'admin.ai.jobs.error.unknown';
    }

    function aiJobActionErrorKey(code) {
      var known = {
        invalid_ai_job_query: true,
        ai_job_not_found: true,
        ai_job_not_retryable: true,
        ai_job_retry_conflict: true,
        ai_disabled: true,
        ai_not_authorized: true,
        ai_owner_disabled: true,
        book_not_found: true,
        chapter_not_found: true,
        ai_reading_required: true,
        ai_template_unavailable: true,
        source_unavailable: true,
        no_reading_material: true
      };
      return hasOwn(known, code)
        ? 'admin.ai.jobs.error.' + code
        : 'admin.ai.jobs.error.unknown';
    }

    function renderAiJobsMessage(key) {
      var body = element('adminAiJobsBody');
      if (!body || !root.document || !root.document.createElement) return;
      body.textContent = '';
      var row = root.document.createElement('tr');
      var cell = createTextElement('td', 'admin-ai-jobs-message', key);
      cell.colSpan = 10;
      cell.setAttribute('colspan', '10');
      row.appendChild(cell);
      body.appendChild(row);
    }

    function aiJobCell(row, className) {
      var cell = root.document.createElement('td');
      if (className) cell.className = className;
      row.appendChild(cell);
      return cell;
    }

    function aiJobDisplayId(job) {
      var value = typeof job.id === 'string' && job.id ? job.id.slice(0, 12) : '';
      var attempt = safeNonNegativeInteger(job.attempt_number, 1) || 1;
      return (value || t('admin.ai.jobs.unknownValue')) + ' · #' + attempt;
    }

    function aiJobScopeLabel(job) {
      var scopeKeys = {
        book: 'admin.ai.jobs.scope.book',
        chapter: 'admin.ai.jobs.scope.chapter'
      };
      var languageKeys = {
        en: 'admin.ai.jobs.language.en',
        'zh-CN': 'admin.ai.jobs.language.zh-CN'
      };
      var knownScope = hasOwn(scopeKeys, job.scope);
      var details = [knownScope
        ? t(scopeKeys[job.scope])
        : t('admin.ai.jobs.unknownValue')];
      var chapter = safeNonNegativeInteger(job.chapter_index, null);
      if (knownScope && job.scope === 'chapter' && chapter !== null) details.push('#' + chapter);
      details.push(hasOwn(languageKeys, job.language)
        ? t(languageKeys[job.language])
        : t('admin.ai.jobs.unknownValue'));
      return details.join(' · ');
    }

    function renderAiJobProgress(cell, job) {
      var total = Math.max(1, safeNonNegativeInteger(job.progress_total, 1));
      var current = Math.min(total, safeNonNegativeInteger(job.progress_current, 0));
      var label = t('admin.ai.jobs.progress', { current: current, total: total });
      var progress = root.document.createElement('progress');
      var text = root.document.createElement('span');
      progress.max = total;
      progress.value = current;
      progress.setAttribute('max', String(total));
      progress.setAttribute('value', String(current));
      progress.setAttribute('aria-label', t('admin.ai.jobs.progressLabel', {
        current: current,
        total: total
      }));
      progress.textContent = label;
      text.className = 'admin-ai-job-progress-text';
      text.textContent = label;
      cell.appendChild(progress);
      cell.appendChild(text);
    }

    function renderAdminAiJobs() {
      var body = element('adminAiJobsBody');
      if (!body || !root.document || !root.document.createElement) return;
      body.textContent = '';
      if (!aiJobsRows.length) {
        renderAiJobsMessage('admin.ai.jobs.empty');
        renderAdminAiJobsPagination();
        return;
      }
      aiJobsRows.forEach(function(job) {
        var row = root.document.createElement('tr');
        var statusCell = aiJobCell(row, 'admin-ai-job-status-cell');
        var status = root.document.createElement('span');
        var bookTitle = typeof job.book_title === 'string' ? job.book_title : '';
        var ownerUsername = typeof job.owner_username === 'string' ? job.owner_username : '';
        var normalizedStatus = ['queued', 'running', 'complete', 'failed', 'interrupted']
          .indexOf(job.status) !== -1 ? job.status : 'unknown';
        status.className = 'admin-ai-job-status is-' + normalizedStatus;
        status.textContent = t(aiJobStatusKey(job.status));
        statusCell.appendChild(status);

        aiJobCell(row, 'admin-ai-job-id').textContent = aiJobDisplayId(job);
        aiJobCell(row, 'admin-ai-job-book').textContent = bookTitle || t('admin.ai.jobs.unknownBook');
        aiJobCell(row, 'admin-ai-job-user').textContent = ownerUsername || t('admin.ai.jobs.unknownUser');
        aiJobCell(row, 'admin-ai-job-scope').textContent = aiJobScopeLabel(job);
        renderAiJobProgress(aiJobCell(row, 'admin-ai-job-progress'), job);

        var errorCell = aiJobCell(row, 'admin-ai-job-error');
        var errorKey = aiJobStoredErrorKey(job.error_code);
        errorCell.textContent = errorKey ? t(errorKey) : '';
        aiJobCell(row, 'admin-ai-job-time').textContent = safeAiJobDate(job.created_at);
        aiJobCell(row, 'admin-ai-job-time').textContent = safeAiJobDate(job.updated_at);

        var actionCell = aiJobCell(row, 'admin-ai-job-action');
        if (job.retryable === true && typeof job.id === 'string' && job.id) {
          var retrying = Boolean(aiJobsRetrying[job.id]);
          var retry = createTextElement(
            'button',
            'bookshelf-action-btn account-inline-action admin-ai-job-retry',
            retrying ? 'admin.ai.jobs.retrying' : 'admin.ai.jobs.retry'
          );
          retry.type = 'button';
          retry.disabled = retrying;
          retry.addEventListener('click', function() { retryAdminAiJob(job.id); });
          actionCell.appendChild(retry);
        }
        body.appendChild(row);
      });
      renderAdminAiJobsPagination();
    }

    function aiJobPageButton(page, currentPage) {
      var button = createTextElement(
        'button',
        'bookshelf-action-btn admin-ai-jobs-page',
        'admin.ai.jobs.pageButton',
        { page: page }
      );
      button.type = 'button';
      button.disabled = page === currentPage;
      if (page === currentPage) button.setAttribute('aria-current', 'page');
      button.addEventListener('click', function() {
        if (page === aiJobsState.page) return;
        aiJobsState.page = page;
        loadAdminAiJobs();
      });
      return button;
    }

    function renderAdminAiJobsPagination() {
      var pagination = element('adminAiJobsPagination');
      if (!pagination || !root.document || !root.document.createElement) return;
      pagination.textContent = '';
      var totalPages = Math.max(1, aiJobsState.totalPages);
      var currentPage = Math.min(totalPages, Math.max(1, aiJobsState.page));
      var summary = createTextElement(
        'span', 'admin-ai-jobs-page-summary', 'admin.ai.jobs.pageSummary', {
          page: currentPage,
          totalPages: totalPages,
          total: aiJobsState.total
        }
      );
      var previous = createTextElement(
        'button', 'bookshelf-action-btn admin-ai-jobs-page', 'admin.ai.jobs.previousPage'
      );
      previous.type = 'button';
      previous.disabled = currentPage <= 1;
      previous.addEventListener('click', function() {
        if (aiJobsState.page <= 1) return;
        aiJobsState.page -= 1;
        loadAdminAiJobs();
      });
      pagination.appendChild(summary);
      pagination.appendChild(previous);

      var pages = {};
      [1, currentPage - 2, currentPage - 1, currentPage, currentPage + 1,
        currentPage + 2, totalPages].forEach(function(page) {
        if (page >= 1 && page <= totalPages) pages[page] = true;
      });
      Object.keys(pages).map(Number).sort(function(left, right) {
        return left - right;
      }).forEach(function(page) {
        pagination.appendChild(aiJobPageButton(page, currentPage));
      });

      var next = createTextElement(
        'button', 'bookshelf-action-btn admin-ai-jobs-page', 'admin.ai.jobs.nextPage'
      );
      next.type = 'button';
      next.disabled = currentPage >= totalPages || aiJobsState.totalPages === 0;
      next.addEventListener('click', function() {
        if (aiJobsState.page >= aiJobsState.totalPages) return;
        aiJobsState.page += 1;
        loadAdminAiJobs();
      });
      pagination.appendChild(next);
    }

    function aiJobsRequestUrl(page, pageSize, status) {
      var url = '/api/admin/ai/jobs?page=' + page + '&page_size=' + pageSize;
      if (status) url += '&status=' + encodeURIComponent(status);
      return url;
    }

    function finishAiJobsRequest(generation, result) {
      aiJobsPendingRequests = Math.max(0, aiJobsPendingRequests - 1);
      aiJobsState.loading = aiJobsPendingRequests > 0;
      return result;
    }

    function loadAdminAiJobs(allowClampFollowup) {
      if (!sessionState || !sessionState.user || sessionState.user.role !== 'admin') {
        return Promise.resolve(null);
      }
      var requestedPage = aiJobsState.page;
      var requestedPageSize = aiJobsState.pageSize;
      var requestedStatus = aiJobsState.status;
      var generation = ++aiJobsRequestGeneration;
      aiJobsPendingRequests += 1;
      aiJobsState.loading = true;
      if (!aiJobsRows.length) renderAiJobsMessage('admin.ai.jobs.loading');
      return authenticatedFetch(aiJobsRequestUrl(
        requestedPage, requestedPageSize, requestedStatus
      )).then(function(response) {
        if (generation !== aiJobsRequestGeneration) return null;
        if (!response || !response.ok) {
          renderAiJobsMessage('admin.ai.jobs.loadError');
          return null;
        }
        return readJson(response).then(function(payload) {
          if (generation !== aiJobsRequestGeneration) return null;
          var pagination = payload && payload.pagination && typeof payload.pagination === 'object'
            ? payload.pagination
            : {};
          var totalPages = safeNonNegativeInteger(pagination.total_pages, 0);
          var maxPage = Math.max(1, totalPages);
          aiJobsState.totalPages = totalPages;
          aiJobsState.total = safeNonNegativeInteger(pagination.total, 0);
          if (requestedPage > maxPage) {
            aiJobsState.page = maxPage;
            if (allowClampFollowup !== false) return loadAdminAiJobs(false);
          }
          aiJobsRows = payload && Array.isArray(payload.jobs) ? payload.jobs : [];
          renderAdminAiJobs();
          return payload;
        });
      }).catch(function() {
        if (generation === aiJobsRequestGeneration) {
          renderAiJobsMessage('admin.ai.jobs.loadError');
        }
        return null;
      }).then(function(result) {
        return finishAiJobsRequest(generation, result);
      }, function(error) {
        finishAiJobsRequest(generation, null);
        throw error;
      });
    }

    function setAiJobsLive(key) {
      var live = element('adminAiJobsLive');
      if (live) live.textContent = t(key);
    }

    function retryAdminAiJob(jobId) {
      if (typeof jobId !== 'string' || !jobId) return Promise.resolve(null);
      if (aiJobsRetryRequests[jobId]) return aiJobsRetryRequests[jobId];
      aiJobsRetrying[jobId] = true;
      renderAdminAiJobs();
      var request = authenticatedFetch(
        '/api/admin/ai/jobs/' + encodeURIComponent(jobId) + '/retry',
        { method: 'POST' }
      ).then(function(response) {
        if (!response || !response.ok) {
          return readJson(response).then(function(payload) {
            var code = payload && payload.code;
            setAiJobsLive(code === 'ai_job_retry_conflict'
              ? 'admin.ai.jobs.retryConflict'
              : aiJobActionErrorKey(code));
            return null;
          });
        }
        return readJson(response).then(function(payload) {
          setAiJobsLive(payload && payload.status === 'complete'
            ? 'admin.ai.jobs.retryComplete'
            : 'admin.ai.jobs.retryQueued');
          return loadAdminAiJobs().then(function() { return payload; });
        });
      }).catch(function() {
        setAiJobsLive('admin.ai.jobs.error.unknown');
        return null;
      });
      aiJobsRetryRequests[jobId] = request.then(function(result) {
        delete aiJobsRetrying[jobId];
        delete aiJobsRetryRequests[jobId];
        renderAdminAiJobs();
        return result;
      }, function(error) {
        delete aiJobsRetrying[jobId];
        delete aiJobsRetryRequests[jobId];
        renderAdminAiJobs();
        throw error;
      });
      return aiJobsRetryRequests[jobId];
    }

    function adminPanelIsActive() {
      var panel = element('adminPanel');
      if (!panel || panel.hidden) return false;
      return Boolean(panel.classList && typeof panel.classList.contains === 'function'
        ? panel.classList.contains('active')
        : panel.active);
    }

    function startAdminAiJobPolling() {
      if (aiJobsPollTimer !== null) return;
      if (!adminPanelIsActive() || (root.document && root.document.hidden === true)) return;
      if (typeof root.setInterval !== 'function') return;
      aiJobsPollTimer = root.setInterval(function() {
        if (
          !aiJobsState.loading
          && adminPanelIsActive()
          && !(root.document && root.document.hidden === true)
        ) {
          loadAdminAiJobs();
        }
      }, 10000);
      if (aiJobsPollTimer && typeof aiJobsPollTimer.unref === 'function') {
        aiJobsPollTimer.unref();
      }
    }

    function stopAdminAiJobPolling() {
      if (aiJobsPollTimer === null) return;
      if (typeof root.clearInterval === 'function') root.clearInterval(aiJobsPollTimer);
      aiJobsPollTimer = null;
    }

    function handleAiJobsVisibilityChange() {
      if (root.document && root.document.hidden === true) {
        stopAdminAiJobPolling();
        return;
      }
      if (adminPanelIsActive()) startAdminAiJobPolling();
    }

    function roleLabel(role) {
      if (role === 'admin') return t('account.role.admin');
      return t('account.role.member');
    }

    function visibilityLabel(visibility) {
      if (visibility === 'restricted') return t('admin.visibility.restricted');
      return t('admin.visibility.authenticated');
    }

    function enabledLabel(enabled) {
      if (enabled) return t('admin.enabled');
      return t('admin.disabled');
    }

    function renderIdentity() {
      var identity = element('accountIdentity');
      var menuValue = element('accountMenuValue');
      if (!sessionState || !sessionState.user) return;
      if (identity) identity.textContent = t('account.signedInAs', {
        username: sessionState.user.username,
        role: roleLabel(sessionState.user.role)
      });
      if (menuValue) menuValue.textContent = sessionState.user.username;
      var adminPanel = element('adminPanel');
      var adminMenu = element('adminMenu');
      if (adminPanel) adminPanel.hidden = sessionState.user.role !== 'admin';
      if (adminMenu) adminMenu.hidden = sessionState.user.role !== 'admin';
      var authentication = sessionState.authentication || {};
      var proxyEnabled = authentication.proxy_enabled === true;
      var pendingProxyIdentity = authentication.pending_proxy_identity === true;
      var associationCard = element('associationCard');
      var adminIdentities = element('adminIdentitiesSection');
      if (associationCard) {
        associationCard.hidden = !proxyEnabled || !pendingProxyIdentity;
      }
      if (adminIdentities) {
        adminIdentities.hidden = !proxyEnabled || sessionState.user.role !== 'admin';
      }
    }

    function describeSessionDevice(userAgent) {
      var agent = String(userAgent || '');
      var browser = '';
      var platform = '';
      if (/Edg\//.test(agent)) browser = 'Edge';
      else if (/Firefox\//.test(agent)) browser = 'Firefox';
      else if (/Chrome\//.test(agent) || /CriOS\//.test(agent)) browser = 'Chrome';
      else if (/Safari\//.test(agent)) browser = 'Safari';
      if (/Android/.test(agent)) platform = 'Android';
      else if (/iPhone|iPad|iPod/.test(agent)) platform = 'iOS';
      else if (/Macintosh|Mac OS X/.test(agent)) platform = 'macOS';
      else if (/Windows/.test(agent)) platform = 'Windows';
      else if (/Linux/.test(agent)) platform = 'Linux';
      if (browser && platform) return browser + ' · ' + platform;
      if (browser || platform) return browser || platform;
      return agent ? agent.slice(0, 80) : t('account.unknownDevice');
    }

    function renderSessions(records) {
      var list = element('sessionList');
      if (!list) return;
      list.textContent = '';
      (records || []).forEach(function(record) {
        var item = root.document.createElement('li');
        item.className = 'account-list-item account-session-item';
        var label = root.document.createElement('span');
        var device = root.document.createElement('strong');
        var address = root.document.createElement('span');
        var times = createTextElement('span', 'account-session-times', 'account.sessionTimes', {
          created: formatDate(record.created_at),
          lastUsed: formatDate(record.last_used_at),
          expires: formatDate(record.expires_at)
        });
        label.className = 'account-session-label';
        device.className = 'account-session-device';
        device.textContent = describeSessionDevice(record.user_agent);
        if (record.user_agent) device.title = record.user_agent;
        address.className = 'account-session-address';
        address.textContent = record.client_address || t('account.unknownAddress');
        label.appendChild(device);
        label.appendChild(address);
        label.appendChild(times);
        item.appendChild(label);
        if (record.current) {
          item.appendChild(createTextElement('strong', 'account-current-session', 'account.currentSession'));
        } else {
          item.appendChild(actionButton('account.revokeSession', function() {
            authenticatedFetch('/api/account/sessions/' + encodeURIComponent(record.id), {
              method: 'DELETE'
            }).then(function(response) {
              if (!response.ok) return showResponseError(response, 'account');
              showStatus('account.sessionRevoked', 'success');
              return loadSessions();
            }).catch(function() {
              showStatus('account.error.network', 'error');
            });
          }, 'danger'));
        }
        list.appendChild(item);
      });
      if (!(records || []).length) list.appendChild(createTextElement('li', 'account-empty', 'account.noSessions'));
    }

    function loadSessions() {
      return authenticatedFetch('/api/account/sessions').then(function(response) {
        if (!response.ok) return showResponseError(response, 'account');
        return readJson(response).then(function(payload) { renderSessions(payload.sessions); });
      }).catch(function() { showStatus('account.error.network', 'error'); });
    }

    function updateUser(username, payload) {
      return authenticatedFetch('/api/admin/users/' + encodeURIComponent(username), {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      }).then(function(response) {
        if (!response.ok) return showResponseError(response, 'admin');
        showStatus('admin.userUpdated', 'success');
        return loadAdminData();
      }).catch(function() { showStatus('admin.error.network', 'error'); });
    }

    function renderUsers() {
      var list = element('adminUserList');
      if (!list) return;
      list.textContent = '';
      users.forEach(function(user) {
        var item = root.document.createElement('li');
        var overview = root.document.createElement('div');
        var profile = root.document.createElement('div');
        var avatar = root.document.createElement('span');
        var identity = root.document.createElement('div');
        var username = root.document.createElement('strong');
        var badges = root.document.createElement('div');
        var role = root.document.createElement('span');
        var status = root.document.createElement('span');
        var details = root.document.createElement('details');
        var detailsSummary = createTextElement('summary', 'account-user-manage', 'admin.manageUser');
        var detailsBody = root.document.createElement('div');
        var accountActions = root.document.createElement('section');
        var accountActionButtons = root.document.createElement('div');
        var securityActions = root.document.createElement('section');
        var passwordControls = root.document.createElement('div');
        var password = root.document.createElement('input');
        item.className = 'account-list-item account-user-item';
        overview.className = 'account-user-overview';
        profile.className = 'account-user-profile';
        avatar.className = 'account-user-avatar';
        avatar.textContent = String(user.username || '?').charAt(0).toUpperCase();
        avatar.setAttribute('aria-hidden', 'true');
        identity.className = 'account-user-identity';
        username.className = 'account-user-name';
        username.textContent = user.username;
        badges.className = 'account-user-badges';
        role.className = 'account-user-badge account-user-role';
        role.textContent = roleLabel(user.role);
        status.className = 'account-user-badge account-user-status ' +
          (user.enabled ? 'is-enabled' : 'is-disabled');
        status.textContent = enabledLabel(user.enabled);
        badges.appendChild(role);
        badges.appendChild(status);
        identity.appendChild(username);
        identity.appendChild(badges);
        profile.appendChild(avatar);
        profile.appendChild(identity);
        overview.appendChild(profile);
        item.appendChild(overview);

        details.className = 'account-user-details';
        detailsBody.className = 'account-user-details-body';
        accountActions.className = 'account-user-action-group';
        accountActionButtons.className = 'account-user-action-buttons';
        accountActions.appendChild(createTextElement(
          'h5', 'account-user-action-title', 'admin.accountAccess'
        ));
        accountActionButtons.appendChild(actionButton(user.enabled ? 'admin.disableUser' : 'admin.enableUser', function() {
          updateUser(user.username, { enabled: !user.enabled });
        }, user.enabled ? 'danger' : undefined));
        accountActionButtons.appendChild(actionButton(user.role === 'admin' ? 'admin.makeMember' : 'admin.makeAdmin', function() {
          updateUser(user.username, { role: user.role === 'admin' ? 'member' : 'admin' });
        }));
        accountActions.appendChild(accountActionButtons);

        securityActions.className = 'account-user-action-group';
        securityActions.appendChild(createTextElement(
          'h5', 'account-user-action-title', 'admin.security'
        ));
        password.type = 'password';
        password.autocomplete = 'new-password';
        password.placeholder = t('admin.newPassword');
        password.className = 'account-inline-input';
        password.setAttribute('data-i18n-placeholder', 'admin.newPassword');
        password.setAttribute('aria-label', t('admin.newPassword'));
        password.setAttribute('data-i18n-aria-label', 'admin.newPassword');
        passwordControls.className = 'account-user-password-controls';
        passwordControls.appendChild(password);
        passwordControls.appendChild(actionButton('admin.resetPassword', function() {
          authenticatedFetch('/api/admin/users/' + encodeURIComponent(user.username) + '/password', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ password: password.value })
          }).then(function(response) {
            password.value = '';
            if (!response.ok) return showResponseError(response, 'admin');
            showStatus('admin.passwordReset', 'success');
          }).catch(function() { showStatus('admin.error.network', 'error'); });
        }));
        securityActions.appendChild(passwordControls);
        securityActions.appendChild(actionButton('admin.revokeSessions', function() {
          updateUser(user.username, { revoke_sessions: true });
        }, 'danger'));

        detailsBody.appendChild(accountActions);
        detailsBody.appendChild(securityActions);
        details.appendChild(detailsSummary);
        details.appendChild(detailsBody);
        item.appendChild(details);
        list.appendChild(item);
      });
    }

    function renderAiSettings() {
      var form = element('adminAiSettingsForm');
      if (!form || !aiSettings) return;
      var fields = form.elements;
      fields.enabled.checked = Boolean(aiSettings.enabled);
      fields.base_url.value = aiSettings.base_url || '';
      fields.api_key.value = '';
      fields.model.value = aiSettings.model || '';
      fields.timeout_seconds.value = String(aiSettings.timeout_seconds || 60);
      fields.model_context_window.value = String(aiSettings.model_context_window || 32768);
      fields.max_concurrency.value = String(aiSettings.max_concurrency || 2);
      fields.daily_limit.value = String(aiSettings.daily_limit || 0);
      fields.clear_api_key.checked = false;
      fields.api_key.placeholder = aiSettings.api_key_configured
        ? t('admin.ai.apiKeyConfigured') : t('admin.ai.apiKeyPlaceholder');
    }

    function saveAiUserAccess(user, enabled, dailyLimit) {
      return authenticatedFetch('/api/admin/ai/users/' + encodeURIComponent(user.id), {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled: enabled, daily_limit: dailyLimit })
      }).then(function(response) {
        if (!response.ok) return showResponseError(response, 'admin');
        showStatus('admin.ai.accessSaved', 'success');
        return loadAdminData();
      }).catch(function() { showStatus('admin.error.network', 'error'); });
    }

    function renderAiUserAccess() {
      var list = element('adminAiUserList');
      if (!list) return;
      list.textContent = '';
      var members = users.filter(function(user) { return user.role === 'member'; });
      members.forEach(function(user) {
        var item = root.document.createElement('li');
        var name = root.document.createElement('strong');
        var controls = root.document.createElement('div');
        var enabled = root.document.createElement('input');
        var enabledLabel = root.document.createElement('label');
        var limit = root.document.createElement('input');
        var limitLabel = root.document.createElement('label');
        var access = user.ai_access || {};
        item.className = 'account-list-item admin-ai-access-item';
        name.textContent = user.username;
        controls.className = 'admin-ai-access-controls';
        enabled.type = 'checkbox';
        enabled.checked = Boolean(access.enabled);
        enabledLabel.className = 'admin-ai-inline-label';
        enabledLabel.appendChild(enabled);
        enabledLabel.appendChild(root.document.createTextNode(t('admin.ai.allowed')));
        limit.type = 'number';
        limit.min = '0';
        limit.value = access.daily_limit === null || access.daily_limit === undefined ? '' : String(access.daily_limit);
        limit.placeholder = t('admin.ai.defaultLimit');
        limitLabel.className = 'admin-ai-inline-label';
        limitLabel.appendChild(root.document.createTextNode(t('admin.ai.dailyOverride')));
        limitLabel.appendChild(limit);
        controls.appendChild(enabledLabel);
        controls.appendChild(limitLabel);
        controls.appendChild(actionButton('admin.ai.saveAccess', function() {
          var parsed = limit.value === '' ? null : Number(limit.value);
          if (parsed !== null && (!Number.isInteger(parsed) || parsed < 0)) {
            showStatus('admin.error.invalid_ai_access', 'error');
            return;
          }
          saveAiUserAccess(user, enabled.checked, parsed);
        }));
        item.appendChild(name);
        item.appendChild(controls);
        list.appendChild(item);
      });
      if (!members.length) list.appendChild(createTextElement('li', 'account-empty', 'admin.ai.noMembers'));
    }

    function renderAiTags() {
      var list = element('adminAiTagList');
      if (!list) return;
      list.textContent = '';
      aiTags.forEach(function(tag) {
        var item = root.document.createElement('li');
        var input = root.document.createElement('input');
        var actions = root.document.createElement('div');
        item.className = 'account-list-item admin-ai-tag-item';
        input.type = 'text';
        input.maxLength = 80;
        input.value = tag.name;
        input.setAttribute('aria-label', t('admin.ai.tagName'));
        actions.className = 'admin-ai-tag-actions';
        actions.appendChild(actionButton('admin.ai.renameTag', function() {
          authenticatedFetch('/api/admin/ai/tags/' + encodeURIComponent(tag.id), {
            method: 'PUT', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: input.value })
          }).then(function(response) {
            if (!response.ok) return showResponseError(response, 'admin');
            return loadAdminData();
          }).catch(function() { showStatus('admin.error.network', 'error'); });
        }));
        actions.appendChild(actionButton('admin.ai.deleteTag', function() {
          authenticatedFetch('/api/admin/ai/tags/' + encodeURIComponent(tag.id), {
            method: 'DELETE'
          }).then(function(response) {
            if (!response.ok) return showResponseError(response, 'admin');
            return loadAdminData();
          }).catch(function() { showStatus('admin.error.network', 'error'); });
        }, 'danger'));
        item.appendChild(input);
        item.appendChild(actions);
        list.appendChild(item);
      });
      if (!aiTags.length) list.appendChild(createTextElement('li', 'account-empty', 'admin.ai.noTags'));
    }

    function clearAiResults(scope) {
      return authenticatedFetch('/api/admin/ai/results', {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(scope || {})
      }).then(function(response) {
        if (!response.ok) return showResponseError(response, 'admin');
        showStatus('admin.ai.cacheCleared', 'success');
        return loadAdminData();
      }).catch(function() { showStatus('admin.error.network', 'error'); });
    }

    function renderBooks() {
      var list = element('adminBookList');
      if (!list) return;
      list.textContent = '';
      books.forEach(function(book) {
        var item = root.document.createElement('li');
        var header = root.document.createElement('div');
        var settings = root.document.createElement('div');
        item.className = 'account-list-item account-book-item';
        header.className = 'admin-book-header';
        settings.className = 'admin-book-settings-grid';
        var title = root.document.createElement('strong');
        var visibility = root.document.createElement('select');
        var grants = root.document.createElement('fieldset');
        var grantLegend = createTextElement('legend', '', 'admin.grantUsers');
        var grantOptions = root.document.createElement('div');
        var access = root.document.createElement('section');
        var accessTitle = createTextElement('h5', 'admin-book-section-title', 'admin.bookAccessSettings');
        var visibilityField = root.document.createElement('label');
        var visibilityText = root.document.createElement('span');
        var accessActions = root.document.createElement('div');
        var grantableUsers = users.filter(function(user) {
          return user.enabled && user.role === 'member';
        });
        title.textContent = book.title;
        title.className = 'account-book-title';
        var epubTags = root.document.createElement('p');
        epubTags.className = 'admin-book-epub-tags';
        epubTags.textContent = t('admin.ai.epubTags') + ': ' + ((book.epub_tags || []).join(', ') || t('admin.ai.noEpubTags'));
        header.appendChild(title);
        header.appendChild(epubTags);
        item.appendChild(header);
        ['authenticated', 'restricted'].forEach(function(value) {
          var option = root.document.createElement('option');
          option.value = value;
          option.textContent = visibilityLabel(value);
          option.selected = value === book.visibility;
          visibility.appendChild(option);
        });
        visibility.setAttribute('aria-label', t('admin.bookVisibility'));
        visibility.setAttribute('data-i18n-aria-label', 'admin.bookVisibility');
        visibilityField.className = 'admin-book-field';
        visibilityText.textContent = t('admin.bookVisibility');
        visibilityText.setAttribute('data-i18n', 'admin.bookVisibility');
        visibilityField.appendChild(visibilityText);
        visibilityField.appendChild(visibility);
        visibility.addEventListener('change', function() {
          authenticatedFetch('/api/admin/books/' + encodeURIComponent(book.id), {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ visibility: visibility.value })
          }).then(function(response) {
            if (!response.ok) return showResponseError(response, 'admin');
            showStatus('admin.bookUpdated', 'success');
            return loadAdminData();
          }).catch(function() { showStatus('admin.error.network', 'error'); });
        });
        access.className = 'admin-book-section admin-book-access';
        access.appendChild(accessTitle);
        access.appendChild(visibilityField);
        grants.className = 'account-book-grants';
        grantOptions.className = 'account-book-grant-options';
        grants.appendChild(grantLegend);
        grantableUsers.forEach(function(user) {
          var label = root.document.createElement('label');
          var checkbox = root.document.createElement('input');
          var name = root.document.createElement('span');
          label.className = 'account-book-grant-option';
          checkbox.type = 'checkbox';
          checkbox.value = user.id;
          checkbox.checked = (book.grants || []).indexOf(user.id) !== -1;
          name.textContent = user.username;
          label.appendChild(checkbox);
          label.appendChild(name);
          grantOptions.appendChild(label);
        });
        if (!grantableUsers.length) {
          grantOptions.appendChild(createTextElement(
            'p',
            'account-empty',
            'admin.noGrantableUsers'
          ));
        }
        grants.appendChild(grantOptions);
        grants.disabled = book.visibility !== 'restricted';
        access.appendChild(grants);
        var saveGrants = actionButton('admin.saveBookGrants', function() {
          var selected = [];
          Array.prototype.forEach.call(
            grantOptions.querySelectorAll('input[type="checkbox"]'),
            function(checkbox) {
              if (checkbox.checked) selected.push(checkbox.value);
            }
          );
          replaceBookGrants(book.id, selected);
        });
        saveGrants.disabled = book.visibility !== 'restricted';
        accessActions.className = 'admin-book-actions';
        accessActions.appendChild(saveGrants);
        access.appendChild(accessActions);
        var tags = root.document.createElement('fieldset');
        var tagsLegend = createTextElement('legend', '', 'admin.bookTags');
        var ai = root.document.createElement('fieldset');
        var aiLegend = createTextElement('legend', '', 'admin.bookAiReading');
        var profile = root.document.createElement('select');
        var tagOptions = root.document.createElement('div');
        var profileLabel = root.document.createElement('label');
        var profileText = root.document.createElement('span');
        var tagActions = root.document.createElement('div');
        var aiActions = root.document.createElement('div');
        tags.className = 'account-book-grants admin-book-tags-settings';
        ai.className = 'account-book-grants admin-book-ai-settings';
        profile.setAttribute('aria-label', t('admin.ai.readingProfile'));
        profile.setAttribute('data-i18n-aria-label', 'admin.ai.readingProfile');
        ['auto', 'technical', 'fiction', 'general'].forEach(function(value) {
          var option = root.document.createElement('option');
          option.value = value;
          option.textContent = t(aiProfileTranslationKeys[value]);
          option.selected = value === (book.ai_profile || 'auto');
          profile.appendChild(option);
        });
        tagOptions.className = 'account-book-grant-options';
        tags.appendChild(tagsLegend);
        ai.appendChild(aiLegend);
        profileLabel.className = 'admin-book-field';
        profileText.textContent = t('admin.ai.readingProfile');
        profileText.setAttribute('data-i18n', 'admin.ai.readingProfile');
        profileLabel.appendChild(profileText);
        profileLabel.appendChild(profile);
        ai.appendChild(profileLabel);
        aiTags.forEach(function(tag) {
          var label = root.document.createElement('label');
          var checkbox = root.document.createElement('input');
          var name = root.document.createElement('span');
          label.className = 'account-book-grant-option';
          checkbox.type = 'checkbox';
          checkbox.value = tag.id;
          checkbox.checked = (book.ai_tags || []).some(function(assigned) {
            return assigned.id === tag.id;
          });
          name.textContent = tag.name;
          label.appendChild(checkbox);
          label.appendChild(name);
          tagOptions.appendChild(label);
        });
        if (!aiTags.length) tagOptions.appendChild(createTextElement(
          'p', 'account-empty', 'admin.ai.noTags'
        ));
        tags.appendChild(tagOptions);
        tagActions.className = 'admin-book-actions';
        tagActions.appendChild(actionButton('admin.saveBookTags', function() {
          var tagIds = [];
          Array.prototype.forEach.call(tagOptions.querySelectorAll('input[type="checkbox"]'), function(checkbox) {
            if (checkbox.checked) tagIds.push(checkbox.value);
          });
          authenticatedFetch('/api/admin/books/' + encodeURIComponent(book.id) + '/ai', {
            method: 'PUT', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ tag_ids: tagIds })
          }).then(function(response) {
            if (!response.ok) return showResponseError(response, 'admin');
            showStatus('admin.bookTagsSaved', 'success');
            return loadAdminData();
          }).catch(function() { showStatus('admin.error.network', 'error'); });
        }));
        tags.appendChild(tagActions);
        aiActions.className = 'admin-book-actions';
        aiActions.appendChild(actionButton('admin.ai.saveBookProfile', function() {
          authenticatedFetch('/api/admin/books/' + encodeURIComponent(book.id) + '/ai', {
            method: 'PUT', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ profile: profile.value })
          }).then(function(response) {
            if (!response.ok) return showResponseError(response, 'admin');
            showStatus('admin.bookClassificationSaved', 'success');
            return loadAdminData();
          }).catch(function() { showStatus('admin.error.network', 'error'); });
        }));
        ai.appendChild(aiActions);
        var results = root.document.createElement('div');
        var resultsLabel = createTextElement('span', 'admin-book-results-label', 'admin.bookResults');
        results.className = 'admin-book-results';
        results.appendChild(resultsLabel);
        results.appendChild(actionButton('admin.ai.clearBookResults', function() {
          clearAiResults({ book_id: book.id });
        }, 'danger'));
        settings.appendChild(access);
        settings.appendChild(tags);
        settings.appendChild(ai);
        item.appendChild(settings);
        item.appendChild(results);
        list.appendChild(item);
      });
      if (!books.length) list.appendChild(createTextElement('li', 'account-empty', 'admin.noBooks'));
    }

    function renderIdentities() {
      var list = element('adminIdentityList');
      var userSelect = element('adminIdentityUser');
      if (userSelect) {
        var selectedUser = userSelect.value;
        userSelect.textContent = '';
        users.forEach(function(user) {
          var option = root.document.createElement('option');
          option.value = user.id;
          option.textContent = user.username;
          option.selected = user.id === selectedUser;
          userSelect.appendChild(option);
        });
      }
      if (!list) return;
      list.textContent = '';
      identities.forEach(function(identity) {
        var item = root.document.createElement('li');
        item.className = 'account-list-item account-identity-item';
        item.appendChild(createTextElement(
          'span',
          'admin-identity-summary',
          'admin.identitySummary',
          {
            issuer: identity.issuer,
            subject: identity.subject,
            username: identity.username,
            displayName: identity.display_name || identity.username
          }
        ));
        item.appendChild(actionButton('admin.deleteIdentity', function() {
          deleteIdentity(identity.issuer, identity.subject);
        }, 'danger'));
        list.appendChild(item);
      });
      if (!identities.length) {
        list.appendChild(createTextElement('li', 'account-empty', 'admin.noIdentities'));
      }
    }

    function createIdentity(payload, reload) {
      return authenticatedFetch('/api/admin/identities', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload || {})
      }).then(function(response) {
        if (!response.ok) return showResponseError(response, 'admin');
        showStatus('admin.identityCreated', 'success');
        return reload === false ? response : loadAdminData();
      }).catch(function() {
        showStatus('admin.error.network', 'error');
      });
    }

    function deleteIdentity(issuer, subject, reload) {
      return authenticatedFetch('/api/admin/identities', {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ issuer: issuer, subject: subject })
      }).then(function(response) {
        if (!response.ok) return showResponseError(response, 'admin');
        showStatus('admin.identityDeleted', 'success');
        return reload === false ? response : loadAdminData();
      }).catch(function() {
        showStatus('admin.error.network', 'error');
      });
    }

    function replaceBookGrants(bookId, userIds, reload) {
      return authenticatedFetch(
        '/api/admin/books/' + encodeURIComponent(bookId) + '/grants',
        {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ user_ids: userIds || [] })
        }
      ).then(function(response) {
        if (!response.ok) return showResponseError(response, 'admin');
        showStatus('admin.bookGrantsSaved', 'success');
        return reload === false ? response : loadAdminData();
      }).catch(function() { showStatus('admin.error.network', 'error'); });
    }

    function loadAdminData() {
      if (!sessionState || !sessionState.user || sessionState.user.role !== 'admin') {
        return Promise.resolve(null);
      }
      var proxyEnabled = Boolean(
        sessionState.authentication && sessionState.authentication.proxy_enabled
      );
      var requests = [
        authenticatedFetch('/api/admin/users'),
        authenticatedFetch('/api/admin/books'),
        authenticatedFetch('/api/admin/ai/settings'),
        authenticatedFetch('/api/admin/ai/tags')
      ];
      if (proxyEnabled) requests.push(authenticatedFetch('/api/admin/identities'));
      return Promise.all(requests).then(function(responses) {
        if (!responses[0].ok) return showResponseError(responses[0], 'admin');
        if (!responses[1].ok) return showResponseError(responses[1], 'admin');
        if (!responses[2].ok) return showResponseError(responses[2], 'admin');
        if (!responses[3].ok) return showResponseError(responses[3], 'admin');
        if (proxyEnabled && !responses[4].ok) return showResponseError(responses[4], 'admin');
        var payloadRequests = [
          readJson(responses[0]),
          readJson(responses[1]),
          readJson(responses[2]),
          readJson(responses[3])
        ];
        if (proxyEnabled) payloadRequests.push(readJson(responses[4]));
        return Promise.all(payloadRequests).then(function(payloads) {
          users = payloads[0].users || [];
          books = payloads[1].books || [];
          aiSettings = payloads[2].settings || null;
          aiTags = payloads[3].tags || [];
          identities = proxyEnabled ? (payloads[4].identities || []) : [];
          renderUsers();
          renderAiSettings();
          renderAiUserAccess();
          renderAiTags();
          renderBooks();
          renderIdentities();
        });
      }).catch(function() { showStatus('admin.error.network', 'error'); });
    }

    function openPanel() {
      var panel = element('accountPanel');
      if (!panel) return;
      panel.classList.add('active');
      panel.setAttribute('aria-hidden', 'false');
      loadSessions();
    }

    function closePanel() {
      var panel = element('accountPanel');
      if (!panel) return;
      panel.classList.remove('active');
      panel.setAttribute('aria-hidden', 'true');
    }

    function openAdminPanel() {
      if (!sessionState || !sessionState.user || sessionState.user.role !== 'admin') return;
      var panel = element('adminPanel');
      if (!panel) return;
      panel.hidden = false;
      panel.classList.add('active');
      panel.setAttribute('aria-hidden', 'false');
      loadAdminData();
      loadAdminAiJobs();
      startAdminAiJobPolling();
    }

    function closeAdminPanel() {
      var panel = element('adminPanel');
      if (!panel) return;
      panel.classList.remove('active');
      panel.setAttribute('aria-hidden', 'true');
      stopAdminAiJobPolling();
    }

    function bindUi() {
      var menu = element('accountMenu');
      var close = element('accountClose');
      var adminMenu = element('adminMenu');
      var adminClose = element('adminClose');
      var logoutButton = element('accountLogout');
      var passwordForm = element('accountPasswordForm');
      var associationForm = element('associationForm');
      var createUserForm = element('adminUserForm');
      var createIdentityForm = element('adminIdentityForm');
      var aiSettingsForm = element('adminAiSettingsForm');
      var aiTagForm = element('adminAiTagForm');
      var clearAiRevision = element('adminAiClearRevision');
      var clearAiAll = element('adminAiClearAll');
      var aiJobsStatus = element('adminAiJobsStatus');
      var aiJobsPageSize = element('adminAiJobsPageSize');
      var aiJobsRefresh = element('adminAiJobsRefresh');
      var aiHelpButtons = Array.prototype.slice.call(root.document.querySelectorAll('.admin-ai-help'));
      function closeAiHelpTips(except) {
        aiHelpButtons.forEach(function(button) {
          if (button !== except) button.classList.remove('is-open');
        });
      }
      aiHelpButtons.forEach(function(button) {
        button.addEventListener('click', function(event) {
          event.preventDefault();
          event.stopPropagation();
          var willOpen = !button.classList.contains('is-open');
          closeAiHelpTips(button);
          button.classList.toggle('is-open', willOpen);
        });
      });
      if (aiHelpButtons.length) {
        root.document.addEventListener('click', function() { closeAiHelpTips(); });
        root.document.addEventListener('keydown', function(event) {
          if (event.key === 'Escape') closeAiHelpTips();
        });
      }
      if (menu) menu.addEventListener('click', openPanel);
      if (close) close.addEventListener('click', closePanel);
      if (adminMenu) adminMenu.addEventListener('click', openAdminPanel);
      if (adminClose) adminClose.addEventListener('click', closeAdminPanel);
      if (logoutButton) logoutButton.addEventListener('click', function() {
        logout().catch(function() { showStatus('account.error.network', 'error'); });
      });
      if (passwordForm) passwordForm.addEventListener('submit', function(event) {
        event.preventDefault();
        authenticatedFetch('/api/account/password', {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            current_password: formValue(passwordForm, 'current_password'),
            new_password: formValue(passwordForm, 'new_password')
          })
        }).then(function(response) {
          clearPasswordFields(passwordForm);
          if (!response.ok) return showResponseError(response, 'account');
          showStatus('account.passwordChanged', 'success');
          redirectToLogin();
        }).catch(function() { showStatus('account.error.network', 'error'); });
      });
      if (associationForm) associationForm.addEventListener('submit', function(event) {
        event.preventDefault();
        associate({
          username: formValue(associationForm, 'username'),
          password: formValue(associationForm, 'password')
        }).then(function(response) {
          clearPasswordFields(associationForm);
          if (!response.ok) return showResponseError(response, 'account');
          showStatus('account.associationSucceeded', 'success');
          return loadSession(true).then(renderIdentity);
        }).catch(function() { showStatus('account.error.network', 'error'); });
      });
      if (createUserForm) createUserForm.addEventListener('submit', function(event) {
        event.preventDefault();
        authenticatedFetch('/api/admin/users', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            username: formValue(createUserForm, 'username'),
            password: formValue(createUserForm, 'password'),
            role: formValue(createUserForm, 'role')
          })
        }).then(function(response) {
          clearPasswordFields(createUserForm);
          if (!response.ok) return showResponseError(response, 'admin');
          createUserForm.reset();
          showStatus('admin.userCreated', 'success');
          return loadAdminData();
        }).catch(function() { showStatus('admin.error.network', 'error'); });
      });
      if (createIdentityForm) createIdentityForm.addEventListener('submit', function(event) {
        event.preventDefault();
        createIdentity({
          issuer: formValue(createIdentityForm, 'issuer'),
          subject: formValue(createIdentityForm, 'subject'),
          display_name: formValue(createIdentityForm, 'display_name'),
          user_id: formValue(createIdentityForm, 'user_id')
        }).then(function() {
          createIdentityForm.reset();
        });
      });
      if (aiSettingsForm) aiSettingsForm.addEventListener('submit', function(event) {
        event.preventDefault();
        var fields = aiSettingsForm.elements;
        authenticatedFetch('/api/admin/ai/settings', {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            enabled: fields.enabled.checked,
            base_url: fields.base_url.value,
            api_key: fields.api_key.value || undefined,
            model: fields.model.value,
            timeout_seconds: Number(fields.timeout_seconds.value),
            model_context_window: Number(fields.model_context_window.value),
            max_concurrency: Number(fields.max_concurrency.value),
            daily_limit: Number(fields.daily_limit.value),
            clear_api_key: fields.clear_api_key.checked
          })
        }).then(function(response) {
          if (!response.ok) return showResponseError(response, 'admin');
          showStatus('admin.ai.settingsSaved', 'success');
          return loadAdminData();
        }).catch(function() { showStatus('admin.error.network', 'error'); });
      });
      if (aiTagForm) aiTagForm.addEventListener('submit', function(event) {
        event.preventDefault();
        authenticatedFetch('/api/admin/ai/tags', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name: formValue(aiTagForm, 'name') })
        }).then(function(response) {
          if (!response.ok) return showResponseError(response, 'admin');
          aiTagForm.reset();
          showStatus('admin.ai.tagAdded', 'success');
          return loadAdminData();
        }).catch(function() { showStatus('admin.error.network', 'error'); });
      });
      if (clearAiRevision) clearAiRevision.addEventListener('click', function() {
        if (aiSettings) clearAiResults({ config_revision: aiSettings.config_revision });
      });
      if (clearAiAll) clearAiAll.addEventListener('click', function() {
        clearAiResults({});
      });
      if (aiJobsStatus) aiJobsStatus.addEventListener('change', function() {
        aiJobsState.status = String(aiJobsStatus.value || '');
        aiJobsState.page = 1;
        loadAdminAiJobs();
      });
      if (aiJobsPageSize) aiJobsPageSize.addEventListener('change', function() {
        var selected = Number(aiJobsPageSize.value);
        aiJobsState.pageSize = [10, 20, 50, 100].indexOf(selected) !== -1 ? selected : 20;
        aiJobsState.page = 1;
        loadAdminAiJobs();
      });
      if (aiJobsRefresh) aiJobsRefresh.addEventListener('click', function() {
        loadAdminAiJobs();
      });
      if (root.document && typeof root.document.addEventListener === 'function') {
        root.document.addEventListener('visibilitychange', handleAiJobsVisibilityChange);
      }
      if (i18n() && i18n().onLocaleChange) {
        i18n().onLocaleChange(function() {
          renderIdentity();
          renderSessions([]);
          renderUsers();
          renderAiSettings();
          renderAiUserAccess();
          renderAiTags();
          renderBooks();
          renderIdentities();
          renderAdminAiJobs();
          loadSessions();
        });
      }
    }

    function init() {
      if (root.EpubBrowserMode !== 'server') return Promise.resolve(null);
      if (!initialized) {
        initialized = true;
        bindUi();
      }
      return loadSession(false).then(function(payload) {
        if (!payload) return null;
        renderIdentity();
        return payload;
      }).catch(function() {
        showStatus('account.error.network', 'error');
        return null;
      });
    }

    return {
      fetch: authenticatedFetch,
      session: loadSession,
      logout: logout,
      associate: associate,
      createIdentity: createIdentity,
      deleteIdentity: deleteIdentity,
      saveBookGrants: replaceBookGrants,
      loadAiJobs: loadAdminAiJobs,
      retryAiJob: retryAdminAiJob,
      init: init,
      setSession: setSession,
      getSession: function() { return sessionState; }
    };
  }

  return { create: create };
});
