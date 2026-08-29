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
    var aiSettings = null;
    var oidcSettings = null;
    var oidcSaveRequest = null;
    var aiTags = [];
    var aiTagSearchQuery = '';
    var aiTagEditingId = '';
    var dictionaries = [];
    var adminBooksState = {
      books: [],
      query: '',
      visibility: '',
      tagId: '',
      sort: 'title_asc',
      page: 1,
      pageSize: 20,
      requestGeneration: 0,
      expandedBookId: null,
      detailCache: Object.create(null),
      editorGeneration: 0,
      editorBusy: false,
      editorError: false,
      editorSaveError: false,
      editorDraft: null,
      editorDirty: false,
      selectedBookIds: Object.create(null),
      bulkGrantUserIds: Object.create(null),
      bulkBusy: false
    };
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
    var aiJobsRetrying = Object.create(null);
    var aiJobsRetryRequests = Object.create(null);
    var activeAdminSection = 'overview';
    var adminHasUnsavedChanges = false;
    var aiProfileTranslationKeys = {
      auto: 'admin.ai.profile.auto',
      technical: 'admin.ai.profile.technical',
      fiction: 'admin.ai.profile.fiction',
      general: 'admin.ai.profile.general'
    };
    var adminBookVisibilityTranslationKeys = {
      authenticated: 'admin.books.visibility.authenticated',
      restricted: 'admin.books.visibility.restricted'
    };
    var adminBookProfileTranslationKeys = {
      auto: 'admin.books.profile.auto',
      technical: 'admin.books.profile.technical',
      fiction: 'admin.books.profile.fiction',
      general: 'admin.books.profile.general'
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
        invalid_ai_tag: true,
        user_disabled: true,
        forbidden: true,
        csrf_required: true,
        invalid_dictionary_archive: true,
        unsupported_dictionary_format: true,
        invalid_mdict: true,
        empty_dictionary_definition: true,
        invalid_mdict_resource: true,
        mdict_resources_not_found: true,
        unsupported_mdict_resource: true,
        mdict_reader_unavailable: true,
        invalid_stardict: true,
        dictionary_has_no_entries: true,
        invalid_dictionary_update: true,
        invalid_dictionary_name: true,
        invalid_oidc_settings: true,
        oidc_configuration_invalid: true,
        oidc_configuration_unsupported: true,
        oidc_discovery_invalid: true,
        oidc_provider_unavailable: true,
        oidc_identity_conflict: true,
        oidc_identity_not_found: true,
        last_login_method: true,
        network: true
      } : {
        authentication_required: true,
        csrf_required: true,
        forbidden: true,
        invalid_credentials: true,
        login_throttled: true,
        invalid_password: true,
        oidc_identity_not_found: true,
        last_login_method: true,
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

    function showDictionaryMessage(key, type) {
      var message = element('adminDictionaryMessage');
      var live = element('adminDictionaryLive');
      var text = key ? t(key) : '';
      if (live) live.textContent = text;
      if (!message) return;
      message.textContent = text;
      message.hidden = !type;
      message.className = type === 'error' ? 'auth-alert' : 'auth-alert success';
    }

    function showDictionaryResponseError(response) {
      return readJson(response).then(function(payload) {
        var key = messageKey('admin', payload && payload.code);
        showDictionaryMessage(key, 'error');
        showStatus(key, 'error');
        return payload;
      });
    }

    function showAiTagMessage(key, type, params) {
      var message = element('adminAiTagMessage');
      var live = element('adminAiTagLive');
      var value = key ? t(key, params) : '';
      if (live) live.textContent = value;
      if (!message) return;
      message.textContent = value;
      message.hidden = !type;
      message.className = 'auth-alert admin-ai-tag-message' + (type === 'success' ? ' success' : '');
    }

    function showAiTagResponseError(response) {
      return readJson(response).then(function(payload) {
        var key = messageKey('admin', payload && payload.code);
        showAiTagMessage(key, 'error');
        return payload;
      });
    }

    function refreshVisibleLibraryMetadata() {
      if (typeof root.refreshLibraryMetadata !== 'function') return Promise.resolve(null);
      try {
        return Promise.resolve(root.refreshLibraryMetadata()).catch(function() { return null; });
      } catch (error) {
        return Promise.resolve(null);
      }
    }

    function confirmAdminAction(key, params, options) {
      options = options || {};
      if (!root.EpubDialog || typeof root.EpubDialog.confirm !== 'function') {
        return Promise.resolve(false);
      }
      var dialogOptions = {
        title: t(options.titleKey || 'admin.title'),
        message: t(key, params),
        destructive: options.destructive !== false
      };
      if (options.confirmTextKey) dialogOptions.confirmText = t(options.confirmTextKey);
      return Promise.resolve(root.EpubDialog.confirm(dialogOptions));
    }

    function confirmDictionaryAction(actionKey, messageKey, params) {
      if (!root.EpubDialog || typeof root.EpubDialog.confirm !== 'function') {
        return Promise.resolve(false);
      }
      return Promise.resolve(root.EpubDialog.confirm({
        title: t(actionKey),
        message: t(messageKey, params),
        confirmText: t(actionKey),
        destructive: true
      }));
    }

    function confirmAdminDiscardChanges() {
      if (!root.EpubDialog || typeof root.EpubDialog.confirm !== 'function') {
        return Promise.resolve(false);
      }
      return Promise.resolve(root.EpubDialog.confirm({
        title: t('admin.close'),
        message: t('admin.confirmDiscardChanges'),
        confirmText: t('admin.discardChanges'),
        destructive: true
      }));
    }

    function confirmWebhookDeletion(name) {
      if (!root.EpubDialog || typeof root.EpubDialog.confirm !== 'function') return Promise.resolve(false);
      return Promise.resolve(root.EpubDialog.confirm({
        title: t('admin.webhooks.delete'),
        message: t('admin.webhooks.deleteConfirm', { name: name }),
        confirmText: t('admin.webhooks.delete'),
        destructive: true
      }));
    }

    function confirmPatRevocation(name) {
      if (!root.EpubDialog || typeof root.EpubDialog.confirm !== 'function') return Promise.resolve(false);
      return Promise.resolve(root.EpubDialog.confirm({
        title: t('account.pats.revoke'),
        message: t('account.pats.revokeConfirm', { name: name }),
        confirmText: t('account.pats.revoke'),
        destructive: true
      }));
    }

    function copySensitiveText(value) {
      if (!value) return Promise.reject(new Error('empty_copy_value'));
      if (root.navigator && root.navigator.clipboard && typeof root.navigator.clipboard.writeText === 'function') {
        return root.navigator.clipboard.writeText(value);
      }
      return new Promise(function(resolve, reject) {
        var field;
        try {
          field = root.document.createElement('textarea');
          field.value = value;
          field.setAttribute('readonly', '');
          field.style.position = 'fixed';
          field.style.opacity = '0';
          root.document.body.appendChild(field);
          field.select();
          if (!root.document.execCommand || !root.document.execCommand('copy')) throw new Error('copy_failed');
          field.remove();
          resolve();
        } catch (error) {
          if (field && field.remove) field.remove();
          reject(error);
        }
      });
    }

    function confirmAdminBookBulkOperation(operation, params) {
      var actionKey = operation === 'restrict'
        ? 'admin.books.bulk.restrict'
        : 'admin.books.bulk.grant';
      var messageKey = operation === 'restrict'
        ? 'admin.books.bulk.restrictConfirm'
        : 'admin.books.bulk.grantConfirm';
      var options = {
        title: t(actionKey),
        message: t(messageKey, params),
        confirmText: t(actionKey),
        destructive: operation === 'restrict'
      };
      if (!root.EpubDialog || typeof root.EpubDialog.confirm !== 'function') {
        return Promise.resolve(false);
      }
      return Promise.resolve(root.EpubDialog.confirm(options));
    }

    function runButtonOperation(button, pendingKey, operation) {
      if (!button) return Promise.resolve().then(operation);
      if (button.disabled) return Promise.resolve(null);
      var originalText = button.textContent;
      button.disabled = true;
      button.setAttribute('aria-busy', 'true');
      button.textContent = t(pendingKey);
      var result;
      try {
        result = operation();
      } catch (error) {
        button.disabled = false;
        button.setAttribute('aria-busy', 'false');
        button.textContent = originalText;
        throw error;
      }
      return Promise.resolve(result).then(function(value) {
        button.disabled = false;
        button.setAttribute('aria-busy', 'false');
        button.textContent = originalText;
        return value;
      }, function(error) {
        button.disabled = false;
        button.setAttribute('aria-busy', 'false');
        button.textContent = originalText;
        throw error;
      });
    }

    function markAdminDirty() {
      adminHasUnsavedChanges = true;
    }

    function clearAdminDirty() {
      adminHasUnsavedChanges = false;
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
      button.addEventListener('click', function() {
        var request = action();
        if (!request || typeof request.then !== 'function') return request;
        button.disabled = true;
        button.setAttribute('aria-busy', 'true');
        return request.then(function(result) {
          button.disabled = false;
          button.setAttribute('aria-busy', 'false');
          return result;
        }, function(error) {
          button.disabled = false;
          button.setAttribute('aria-busy', 'false');
          throw error;
        });
      });
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
      var normalized = value;
      if (
        typeof value === 'string'
        && /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:\.\d{1,3})?$/.test(value)
      ) {
        normalized = value.replace(' ', 'T') + 'Z';
      }
      var parsed = new Date(normalized);
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
        ai_generation_failed: 'ai.error.ai_generation_failed',
        ai_job_not_retryable: 'admin.ai.jobs.error.ai_job_not_retryable',
        book_not_found: 'admin.ai.jobs.error.book_not_found',
        chapter_not_found: 'admin.ai.jobs.error.chapter_not_found',
        source_unavailable: 'admin.ai.jobs.error.source_unavailable',
        no_reading_material: 'admin.ai.jobs.error.no_reading_material',
        ai_template_unavailable: 'admin.ai.jobs.error.ai_template_unavailable'
      };
      if (!code) return '';
      return hasOwn(known, code)
        ? (known[code] === true ? 'ai.error.' + code : known[code])
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
      cell.colSpan = 6;
      cell.setAttribute('colspan', '6');
      row.appendChild(cell);
      body.appendChild(row);
    }

    function aiJobCell(row, className, labelKey) {
      var cell = root.document.createElement('td');
      if (className) cell.className = className;
      if (labelKey) cell.setAttribute('data-label', t(labelKey));
      row.appendChild(cell);
      return cell;
    }

    function appendAiJobMeta(container, className, label, value) {
      if (!value) return;
      var detail = root.document.createElement('span');
      detail.className = className;
      detail.textContent = label ? label + ': ' + value : value;
      container.appendChild(detail);
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
        'zh-CN': 'admin.ai.jobs.language.zh-CN',
        'zh-TW': 'admin.ai.jobs.language.zh-TW',
        ko: 'admin.ai.jobs.language.ko',
        ja: 'admin.ai.jobs.language.ja'
      };
      var knownScope = hasOwn(scopeKeys, job.scope);
      var details = [knownScope
        ? t(scopeKeys[job.scope])
        : t('admin.ai.jobs.unknownValue')];
      var chapter = safeNonNegativeInteger(job.chapter_index, null);
      if (knownScope && job.scope === 'chapter' && chapter !== null) details.push('#' + chapter);
      var languageKey = languageKeys[job.language] || 'locale.name.' + String(job.language || '');
      var languageLabel = t(languageKey);
      details.push(languageLabel !== languageKey ? languageLabel : t('admin.ai.jobs.unknownValue'));
      return details.join(' · ');
    }

    function renderAiJobProgress(cell, job) {
      var total = Math.max(1, safeNonNegativeInteger(job.progress_total, 1));
      var current = Math.min(total, safeNonNegativeInteger(job.progress_current, 0));
      var label = t('admin.ai.jobs.progress', { current: current, total: total });
      var wrapper = root.document.createElement('div');
      var progress = root.document.createElement('progress');
      var text = root.document.createElement('span');
      wrapper.className = 'admin-ai-job-progress-content';
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
      wrapper.appendChild(progress);
      wrapper.appendChild(text);
      cell.appendChild(wrapper);
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
        var statusCell = aiJobCell(row, 'admin-ai-job-status-cell', 'admin.ai.jobs.header.status');
        var status = root.document.createElement('span');
        var bookTitle = typeof job.book_title === 'string' ? job.book_title : '';
        var ownerUsername = typeof job.owner_username === 'string' ? job.owner_username : '';
        var normalizedStatus = ['queued', 'running', 'complete', 'failed', 'interrupted']
          .indexOf(job.status) !== -1 ? job.status : 'unknown';
        status.className = 'admin-ai-job-status is-' + normalizedStatus;
        status.textContent = t(aiJobStatusKey(job.status));
        statusCell.appendChild(status);

        var taskCell = aiJobCell(row, 'admin-ai-job-task', 'admin.ai.jobs.header.job');
        var taskId = root.document.createElement('strong');
        taskId.textContent = aiJobDisplayId(job);
        taskCell.appendChild(taskId);
        appendAiJobMeta(
          taskCell, 'admin-ai-job-meta', t('admin.ai.jobs.header.requester'),
          ownerUsername || t('admin.ai.jobs.unknownUser')
        );
        var errorKey = aiJobStoredErrorKey(job.error_code);
        appendAiJobMeta(
          taskCell, 'admin-ai-job-error', t('admin.ai.jobs.header.error'),
          errorKey ? t(errorKey) : ''
        );

        var bookCell = aiJobCell(row, 'admin-ai-job-book', 'admin.ai.jobs.header.book');
        var bookName = root.document.createElement('strong');
        bookName.textContent = bookTitle || t('admin.ai.jobs.unknownBook');
        bookCell.appendChild(bookName);
        appendAiJobMeta(
          bookCell, 'admin-ai-job-scope', '', aiJobScopeLabel(job)
        );
        renderAiJobProgress(aiJobCell(row, 'admin-ai-job-progress', 'admin.ai.jobs.header.progress'), job);

        var timeCell = aiJobCell(row, 'admin-ai-job-time', 'admin.ai.jobs.header.timeline');
        appendAiJobMeta(
          timeCell, 'admin-ai-job-meta', t('admin.ai.jobs.header.created'), safeAiJobDate(job.created_at)
        );
        appendAiJobMeta(
          timeCell, 'admin-ai-job-meta', t('admin.ai.jobs.header.updated'), safeAiJobDate(job.updated_at)
        );

        var actionCell = aiJobCell(row, 'admin-ai-job-action', 'admin.ai.jobs.header.action');
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

    function sectionForAdminControl(control) {
      if (!control || typeof control.getAttribute !== 'function') return '';
      var section = control.getAttribute('data-admin-section');
      return ['overview', 'users', 'oidc', 'dictionaries', 'ai-configuration', 'ai-permissions', 'ai-jobs', 'tags', 'webhooks', 'books'].indexOf(section) !== -1
        ? section : '';
    }

    function adminPanelIsAvailable(panel) { return Boolean(panel); }

    function setActiveAdminSection(section) {
      var activeTab = null;
      if (['overview', 'users', 'oidc', 'dictionaries', 'ai-configuration', 'ai-permissions', 'ai-jobs', 'tags', 'webhooks', 'books'].indexOf(section) === -1) return;
      activeAdminSection = section;
      if (!root.document || typeof root.document.querySelectorAll !== 'function') return;
      Array.prototype.slice.call(root.document.querySelectorAll('[data-admin-section]')).forEach(function(control) {
        var selected = sectionForAdminControl(control) === section;
        if (control.getAttribute && control.getAttribute('role') === 'tab') {
          control.setAttribute('aria-selected', String(selected));
          if (control.classList) control.classList.toggle('is-active', selected);
          if (selected) activeTab = control;
        }
      });
      Array.prototype.slice.call(root.document.querySelectorAll('[data-admin-panel]')).forEach(function(panel) {
        panel.hidden = panel.getAttribute('data-admin-panel') !== section || !adminPanelIsAvailable(panel);
      });
      if (activeTab && typeof activeTab.scrollIntoView === 'function') {
        activeTab.scrollIntoView({ block: 'nearest', inline: 'center' });
      }
      if (adminPanelIsActive() && root.history && typeof root.history.replaceState === 'function') {
        root.history.replaceState(null, '', '#admin=' + encodeURIComponent(section));
      }
    }

    function adminSectionFromHash() {
      var match = String(root.location && root.location.hash || '').match(/(?:^#|&)admin=([^&]+)/);
      if (!match) return '';
      try {
        var section = decodeURIComponent(match[1]);
        return ['overview', 'users', 'oidc', 'dictionaries', 'ai-configuration', 'ai-permissions', 'ai-jobs', 'tags', 'webhooks', 'books'].indexOf(section) !== -1
          ? section : '';
      } catch (error) {
        return '';
      }
    }

    function renderAdminOverview() {
      var configured = aiSettings && aiSettings.api_key_configured;
      var aiStateKey = !aiSettings || !aiSettings.enabled
        ? 'admin.overview.aiDisabled'
        : (configured ? 'admin.overview.aiReady' : 'admin.overview.aiNeedsKey');
      var values = {
        adminOverviewUsers: users.length,
        adminOverviewAi: t(aiStateKey),
        adminOverviewTags: aiTags.length,
        adminOverviewBooks: adminBooksState.books.length
      };
      Object.keys(values).forEach(function(id) {
        var target = element(id);
        if (target) target.textContent = String(values[id]);
      });
      var live = element('adminOverviewLive');
      if (live) live.textContent = t('admin.overview.liveLoaded', {
        users: users.length,
        books: adminBooksState.books.length
      });
    }

    function updateDictionary(dictionary, enabled) {
      return authenticatedFetch('/api/admin/dictionaries/' + encodeURIComponent(dictionary.id), {
        method: 'PUT', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({enabled: enabled})
      }).then(function(response) {
        if (!response.ok) return showDictionaryResponseError(response);
        showDictionaryMessage('admin.dictionaryUpdated', 'success');
        showStatus('admin.dictionaryUpdated', 'success');
        return loadDictionaries();
      }).catch(function() {
        showDictionaryMessage('admin.error.network', 'error');
        showStatus('admin.error.network', 'error');
      });
    }

    function updateDictionaryScripts(dictionary, allowScripts) {
      return authenticatedFetch('/api/admin/dictionaries/' + encodeURIComponent(dictionary.id), {
        method: 'PUT', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({allow_scripts: allowScripts})
      }).then(function(response) {
        if (!response.ok) return showDictionaryResponseError(response);
        showDictionaryMessage('admin.dictionaryUpdated', 'success');
        showStatus('admin.dictionaryUpdated', 'success');
        return loadDictionaries();
      }).catch(function() {
        showDictionaryMessage('admin.error.network', 'error');
        showStatus('admin.error.network', 'error');
      });
    }

    function setDefaultDictionary(dictionary) {
      return authenticatedFetch('/api/admin/dictionaries/' + encodeURIComponent(dictionary.id) + '/default', {
        method: 'PUT'
      }).then(function(response) {
        if (!response.ok) return showDictionaryResponseError(response);
        showDictionaryMessage('admin.dictionaryDefaultUpdated', 'success');
        showStatus('admin.dictionaryDefaultUpdated', 'success');
        return loadDictionaries();
      }).catch(function() {
        showDictionaryMessage('admin.error.network', 'error');
        showStatus('admin.error.network', 'error');
      });
    }

    function deleteDictionary(dictionary) {
      return authenticatedFetch('/api/admin/dictionaries/' + encodeURIComponent(dictionary.id), {
        method: 'DELETE'
      }).then(function(response) {
        if (!response.ok) return showDictionaryResponseError(response);
        showDictionaryMessage('admin.dictionaryDeleted', 'success');
        showStatus('admin.dictionaryDeleted', 'success');
        return loadDictionaries();
      }).catch(function() {
        showDictionaryMessage('admin.error.network', 'error');
        showStatus('admin.error.network', 'error');
      });
    }

    function loadDictionaries(options) {
      var silent = options && options.silent;
      return authenticatedFetch('/api/admin/dictionaries').then(function(dictionaryResponse) {
        if (!dictionaryResponse.ok) {
          return silent ? readJson(dictionaryResponse) : showDictionaryResponseError(dictionaryResponse);
        }
        return readJson(dictionaryResponse).then(function(payload) {
          dictionaries = payload.dictionaries || [];
          renderDictionaries();
        });
      }).catch(function() {
        if (!silent) showDictionaryMessage('admin.error.network', 'error');
      });
    }

    function renameDictionary(dictionary) {
      if (!root.EpubDialog || typeof root.EpubDialog.prompt !== 'function') return Promise.resolve(null);
      return Promise.resolve(root.EpubDialog.prompt({
        title: t('admin.renameDictionary'),
        inputLabel: t('admin.dictionaryName'),
        defaultValue: dictionary.display_name,
        selectOnOpen: true,
        confirmText: t('admin.renameDictionary')
      })).then(function(displayName) {
        if (displayName === null) return null;
        return authenticatedFetch('/api/admin/dictionaries/' + encodeURIComponent(dictionary.id), {
          method: 'PUT', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({display_name: displayName})
        }).then(function(response) {
          if (!response.ok) return showDictionaryResponseError(response);
          showDictionaryMessage('admin.dictionaryRenamed', 'success');
          showStatus('admin.dictionaryRenamed', 'success');
          return loadDictionaries();
        }).catch(function() {
          showDictionaryMessage('admin.error.network', 'error');
          showStatus('admin.error.network', 'error');
        });
      });
    }

    function renderDictionaries() {
      var list = element('adminDictionaryList');
      if (!list) return;
      list.textContent = '';
      if (!dictionaries.length) {
        list.appendChild(createTextElement('li', 'account-list-empty', 'admin.noDictionaries'));
        return;
      }
      dictionaries.forEach(function(dictionary) {
        var item = root.document.createElement('li');
        var summary = root.document.createElement('div');
        var name = root.document.createElement('strong');
        var metadata = createTextElement(
          'span', 'dictionary-record-metadata', 'admin.dictionaryEntries',
          {count: dictionary.entry_count}
        );
        var states = root.document.createElement('div');
        var state = root.document.createElement('span');
        var actions = root.document.createElement('div');
        item.className = 'account-list-item';
        summary.className = 'dictionary-record-summary';
        name.className = 'dictionary-record-name';
        state.className = 'dictionary-record-state ' + (dictionary.enabled ? 'is-enabled' : 'is-disabled');
        states.className = 'dictionary-record-states';
        actions.className = 'dictionary-record-actions';
        name.textContent = dictionary.display_name;
        state.textContent = enabledLabel(dictionary.enabled);
        summary.appendChild(name);
        summary.appendChild(metadata);
        item.appendChild(summary);
        if (dictionary.is_default) {
          states.appendChild(createTextElement(
            'span', 'dictionary-record-state is-default', 'admin.defaultDictionary'
          ));
        }
        states.appendChild(state);
        item.appendChild(states);
        if (dictionary.enabled && !dictionary.is_default) {
          actions.appendChild(actionButton('admin.setDefaultDictionary', function() {
            return setDefaultDictionary(dictionary);
          }));
        }
        actions.appendChild(actionButton('admin.renameDictionary', function() {
          return renameDictionary(dictionary);
        }));
        actions.appendChild(actionButton(
          dictionary.allow_scripts ? 'admin.disableDictionaryScripts' : 'admin.enableDictionaryScripts',
          function() {
            var allowScripts = !dictionary.allow_scripts;
            var confirmation = allowScripts
              ? 'admin.confirmEnableDictionaryScripts'
              : 'admin.confirmDisableDictionaryScripts';
            return confirmDictionaryAction(
              dictionary.allow_scripts ? 'admin.disableDictionaryScripts' : 'admin.enableDictionaryScripts',
              confirmation, {name: dictionary.display_name}
            ).then(function(confirmed) {
              return confirmed ? updateDictionaryScripts(dictionary, allowScripts) : null;
            });
          }, dictionary.allow_scripts ? 'danger' : undefined
        ));
        actions.appendChild(actionButton(
          dictionary.enabled ? 'admin.disableDictionary' : 'admin.enableDictionary',
          function() {
            if (dictionary.enabled) {
              return confirmDictionaryAction(
                'admin.disableDictionary', 'admin.confirmDisableDictionary',
                {name: dictionary.display_name}
              ).then(function(confirmed) {
                return confirmed ? updateDictionary(dictionary, false) : null;
              });
            }
            return updateDictionary(dictionary, !dictionary.enabled);
          }, dictionary.enabled ? 'danger' : undefined
        ));
        actions.appendChild(actionButton('admin.deleteDictionary', function() {
          return confirmDictionaryAction(
            'admin.deleteDictionary', 'admin.confirmDeleteDictionary',
            {name: dictionary.display_name}
          ).then(function(confirmed) {
            return confirmed ? deleteDictionary(dictionary) : null;
          });
        }, 'danger'));
        item.appendChild(actions);
        list.appendChild(item);
      });
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
      var patAdminScopeLabel = element('patAdminScopeLabel');
      if (patAdminScopeLabel) patAdminScopeLabel.hidden = sessionState.user.role !== 'admin';
      renderAccountOidc();
    }

    function setTextMessage(target, key, type) {
      if (!target) return;
      target.textContent = key ? t(key) : '';
      target.className = 'account-form-message' + (type ? ' is-' + type : '');
    }

    function oidcCurrentPath() {
      var location = root.location || {};
      var path = String(location.pathname || '/');
      if (path.charAt(0) !== '/' || path.indexOf('//') === 0) path = '/';
      return path + String(location.search || '');
    }

    function renderAccountOidc() {
      var card = element('accountOidcCard');
      if (!card || !sessionState || !sessionState.user) return;
      var identities = Array.isArray(sessionState.user.oidc_identities)
        ? sessionState.user.oidc_identities : [];
      var available = Boolean(sessionState.oidc && sessionState.oidc.enabled);
      var list = element('accountOidcList');
      var link = element('accountOidcLink');
      var unlink = element('accountOidcUnlink');
      card.hidden = !available && identities.length === 0;
      if (list) {
        list.textContent = '';
        if (!identities.length) {
          list.appendChild(createTextElement(
            'li', 'account-list-item account-oidc-empty', 'account.oidc.noIdentity'
          ));
        }
        identities.forEach(function(identity) {
          var item = root.document.createElement('li');
          var details = root.document.createElement('span');
          var provider = root.document.createElement('strong');
          var account = root.document.createElement('span');
          item.className = 'account-list-item account-oidc-identity';
          details.className = 'account-oidc-identity-copy';
          provider.textContent = identity.provider_name || t('admin.oidc.provider');
          account.textContent = identity.display_name || identity.username || identity.email || '';
          details.appendChild(provider);
          details.appendChild(account);
          item.appendChild(details);
          list.appendChild(item);
        });
      }
      if (link) {
        link.hidden = !available || Boolean(sessionState.oidc.linked);
        link.textContent = t('account.oidc.linkWith', {
          provider: sessionState.oidc && sessionState.oidc.provider_name || ''
        });
      }
      if (unlink) {
        unlink.hidden = identities.length === 0;
        unlink.disabled = Boolean(identities.length && !identities[0].can_unlink);
        unlink.setAttribute('aria-disabled', String(unlink.disabled));
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

    function patScopeLabel(scope) {
      var keys = {
        'library:read': 'account.pats.scope.libraryRead',
        'bookshelf:read': 'account.pats.scope.bookshelfRead',
        'bookshelf:write': 'account.pats.scope.bookshelfWrite',
        'progress:read': 'account.pats.scope.progressRead',
        'progress:write': 'account.pats.scope.progressWrite',
        'annotations:read': 'account.pats.scope.annotationsRead',
        'annotations:write': 'account.pats.scope.annotationsWrite',
        'reviews:read': 'account.pats.scope.reviewsRead',
        'reviews:write': 'account.pats.scope.reviewsWrite',
        'admin:data:read': 'account.pats.scope.adminDataRead'
      };
      return t(keys[scope] || 'account.pats.unknownScope', { scope: scope });
    }

    function renderPersonalAccessTokens(records) {
      var list = element('patList');
      if (!list) return;
      list.textContent = '';
      (records || []).forEach(function(record) {
        var item = root.document.createElement('li');
        var details = root.document.createElement('div');
        var name = root.document.createElement('strong');
        var scopes = root.document.createElement('span');
        var dates = root.document.createElement('span');
        item.className = 'account-list-item account-pat-item';
        details.className = 'account-pat-details';
        name.textContent = record.name;
        scopes.className = 'account-pat-scope-summary';
        (record.scopes || []).forEach(function(scope) {
          var chip = root.document.createElement('span');
          chip.className = 'account-pat-scope-chip';
          chip.textContent = patScopeLabel(scope);
          scopes.appendChild(chip);
        });
        dates.className = 'account-pat-dates';
        dates.textContent = record.expires_at
          ? t('account.pats.expires', { date: formatDate(record.expires_at) })
          : t('account.pats.never');
        if (record.last_used_at) {
          dates.textContent += ' · ' + t('account.pats.lastUsed', {
            date: formatDate(record.last_used_at)
          });
        }
        details.appendChild(name);
        details.appendChild(scopes);
        details.appendChild(dates);
        item.appendChild(details);
        item.appendChild(actionButton('account.pats.revoke', function() {
          return confirmPatRevocation(record.name).then(function(confirmed) {
            if (!confirmed) return;
            return authenticatedFetch('/api/account/pats/' + encodeURIComponent(record.id), {
              method: 'DELETE'
            }).then(function(response) {
              if (!response.ok) return showResponseError(response, 'account');
              showStatus('account.pats.revoked', 'success');
              return loadPersonalAccessTokens();
            }).catch(function() { showStatus('account.error.network', 'error'); });
          });
        }, 'danger'));
        list.appendChild(item);
      });
      if (!(records || []).length) {
        list.appendChild(createTextElement('li', 'account-empty', 'account.pats.empty'));
      }
    }

    function loadPersonalAccessTokens() {
      return authenticatedFetch('/api/account/pats').then(function(response) {
        if (!response.ok) return showResponseError(response, 'account');
        return readJson(response).then(function(payload) {
          renderPersonalAccessTokens(payload.personal_access_tokens || []);
        });
      }).catch(function() { showStatus('account.error.network', 'error'); });
    }

    function clearPersonalAccessTokenSecret() {
      var secret = element('patCreatedSecret');
      var region = element('patSecretRegion');
      if (secret) secret.textContent = '';
      if (region) region.hidden = true;
    }

    function showWebhookSecret(value) {
      var secret = element('adminWebhookSecret');
      var region = element('adminWebhookSecretRegion');
      if (secret) secret.textContent = value || '';
      if (region) region.hidden = !value;
      if (value) {
        var copy = element('adminWebhookCopySecret');
        if (copy && copy.focus) copy.focus();
      }
    }

    function webhookEventLabel(eventType) {
      var keys = {
        'review.created': 'admin.webhooks.event.reviewCreated',
        'review.updated': 'admin.webhooks.event.reviewUpdated',
        'review.deleted': 'admin.webhooks.event.reviewDeleted',
        'book.created': 'admin.webhooks.event.bookCreated',
        'book.updated': 'admin.webhooks.event.bookUpdated',
        'book.removed': 'admin.webhooks.event.bookRemoved',
        'book.conversion.succeeded': 'admin.webhooks.event.conversionSucceeded',
        'book.conversion.failed': 'admin.webhooks.event.conversionFailed',
        'webhook.test': 'admin.webhooks.event.test'
      };
      return keys[eventType] ? t(keys[eventType]) : eventType;
    }

    function renderWebhooks(endpoints, deliveries) {
      var list = element('adminWebhookList');
      var history = element('adminWebhookDeliveries');
      if (list) {
        list.textContent = '';
        (endpoints || []).forEach(function(endpoint) {
          var item = root.document.createElement('li');
          var summary = root.document.createElement('div');
          var summaryHeader = root.document.createElement('div');
          var actions = root.document.createElement('div');
          var name = root.document.createElement('strong');
          var url = root.document.createElement('code');
          var events = root.document.createElement('div');
          var stateKey = endpoint.enabled ? 'admin.webhooks.status.enabled' : 'admin.webhooks.status.paused';
          var state = createTextElement('span', '', stateKey);
          item.className = 'account-list-item admin-webhook-item';
          summary.className = 'admin-webhook-summary';
          name.textContent = endpoint.name;
          url.className = 'admin-webhook-url';
          url.textContent = endpoint.url;
          events.className = 'admin-webhook-events-copy';
          state.className = 'account-status-badge ' + (endpoint.enabled ? 'is-success' : 'is-muted');
          summaryHeader.className = 'admin-webhook-summary-header';
          summaryHeader.appendChild(name);
          summaryHeader.appendChild(state);
          summary.appendChild(summaryHeader);
          summary.appendChild(url);
          (endpoint.event_types || []).forEach(function(eventType) {
            var chip = root.document.createElement('span');
            chip.className = 'admin-webhook-event-chip';
            chip.textContent = webhookEventLabel(eventType);
            events.appendChild(chip);
          });
          summary.appendChild(events);
          actions.className = 'account-list-actions';
          actions.appendChild(actionButton('admin.webhooks.edit', function() {
            var form = element('adminWebhookForm');
            if (!form || !form.elements) return;
            form.elements.name.value = endpoint.name;
            form.elements.url.value = endpoint.url;
            form.elements.enabled.checked = endpoint.enabled;
            Array.prototype.forEach.call(form.querySelectorAll('input[name="event_types"]'), function(input) {
              input.checked = (endpoint.event_types || []).indexOf(input.value) !== -1;
            });
            form.setAttribute('data-editing-id', endpoint.id);
            var submit = element('adminWebhookSubmit');
            if (submit) {
              submit.setAttribute('data-i18n', 'admin.webhooks.update');
              if (root.EpubBrowserI18n) root.EpubBrowserI18n.translateDocument(submit.parentNode);
            }
            var cancel = element('adminWebhookCancelEdit');
            if (cancel) cancel.hidden = false;
            if (form.elements.name.focus) form.elements.name.focus();
          }));
          actions.appendChild(actionButton(endpoint.enabled ? 'admin.webhooks.pause' : 'admin.webhooks.resume', function() {
            return authenticatedFetch('/api/admin/webhooks/' + encodeURIComponent(endpoint.id), {
              method: 'PUT', headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ name: endpoint.name, url: endpoint.url, event_types: endpoint.event_types, enabled: !endpoint.enabled })
            }).then(function(response) { if (!response.ok) return showResponseError(response, 'admin'); return loadWebhooks(); });
          }));
          actions.appendChild(actionButton('admin.webhooks.test', function() {
            authenticatedFetch('/api/admin/webhooks/' + encodeURIComponent(endpoint.id) + '/test', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' })
              .then(function(response) { if (!response.ok) return showResponseError(response, 'admin'); return loadWebhooks(); });
          }));
          actions.appendChild(actionButton('admin.webhooks.rotate', function() {
            authenticatedFetch('/api/admin/webhooks/' + encodeURIComponent(endpoint.id) + '/rotate-secret', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' })
              .then(function(response) { if (!response.ok) return showResponseError(response, 'admin'); return readJson(response); })
              .then(function(payload) { if (payload) showWebhookSecret(payload.secret); });
          }));
          actions.appendChild(actionButton('admin.webhooks.delete', function() {
            return confirmWebhookDeletion(endpoint.name).then(function(confirmed) {
              if (!confirmed) return;
              return authenticatedFetch('/api/admin/webhooks/' + encodeURIComponent(endpoint.id), { method: 'DELETE' })
                .then(function(response) { if (!response.ok) return showResponseError(response, 'admin'); return loadWebhooks(); });
            });
          }, 'danger'));
          item.appendChild(summary);
          item.appendChild(actions);
          list.appendChild(item);
        });
        if (!(endpoints || []).length) list.appendChild(createTextElement('li', 'account-empty', 'admin.webhooks.empty'));
      }
      if (history) {
        history.textContent = '';
        (deliveries || []).forEach(function(delivery) {
          var item = root.document.createElement('li');
          item.className = 'account-list-item admin-webhook-delivery';
          item.textContent = delivery.endpoint_name + ' · ' + delivery.event_type + ' · ' + delivery.status + ' · ' + delivery.attempt_count;
          history.appendChild(item);
        });
        if (!(deliveries || []).length) history.appendChild(createTextElement('li', 'account-empty', 'admin.webhooks.noDeliveries'));
      }
    }

    function loadWebhooks() {
      return Promise.all([
        authenticatedFetch('/api/admin/webhooks'),
        authenticatedFetch('/api/admin/webhooks/deliveries')
      ]).then(function(responses) {
        if (!responses[0].ok) return showResponseError(responses[0], 'admin');
        if (!responses[1].ok) return showResponseError(responses[1], 'admin');
        return Promise.all([readJson(responses[0]), readJson(responses[1])]).then(function(payloads) {
          renderWebhooks(payloads[0].items || [], payloads[1].items || []);
        });
      });
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

    function userDeletionDetails(impact) {
      var runtime = i18n();
      var details = [];
      function count(value) {
        return runtime && runtime.formatNumber
          ? runtime.formatNumber(value)
          : String(value);
      }
      (impact.deletions || []).forEach(function(item) {
        details.push(t('admin.userDeleteData.' + item.kind, {
          count: count(item.count)
        }));
      });
      (impact.retained || []).forEach(function(item) {
        details.push(t('admin.userDeleteRetained.' + item.kind, {
          count: count(item.count)
        }));
      });
      return details;
    }

    function requestUserDeletion(user, confirmation) {
      var payload = {};
      if (confirmation !== undefined) payload.confirmation = confirmation;
      return authenticatedFetch('/api/admin/users/' + encodeURIComponent(user.username), {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      }).then(function(response) {
        if (response.ok) {
          showStatus('admin.userDeleted', 'success');
          return loadAdminData();
        }
        return readJson(response).then(function(error) {
          if (
            response.status === 409
            && error
            && error.code === 'user_deletion_confirmation_required'
            && error.impact
          ) {
            return confirmUserDeletion(user, error.impact);
          }
          showStatus(messageKey('admin', error && error.code), 'error');
          return null;
        });
      }).catch(function() {
        showStatus('admin.error.network', 'error');
      });
    }

    function confirmUserDeletion(user, impact) {
      if (!root.EpubDialog) return Promise.resolve(null);
      if (!impact.requires_typed_confirmation) {
        if (typeof root.EpubDialog.confirm !== 'function') return Promise.resolve(null);
        return Promise.resolve(root.EpubDialog.confirm({
          title: t('admin.deleteUser'),
          message: t('admin.deleteUserSimpleConfirm', { username: user.username }),
          confirmText: t('admin.deleteUser'),
          destructive: true
        })).then(function(confirmed) {
          return confirmed ? requestUserDeletion(user) : null;
        });
      }
      if (typeof root.EpubDialog.prompt !== 'function') return Promise.resolve(null);
      return Promise.resolve(root.EpubDialog.prompt({
        title: t('admin.deleteUser'),
        message: t('admin.deleteUserImpactConfirm', { username: user.username }),
        details: userDeletionDetails(impact),
        inputLabel: t('admin.deleteUserConfirmationLabel', {
          username: impact.confirmation_text || user.username
        }),
        expectedValue: impact.confirmation_text || user.username,
        confirmText: t('admin.deleteUser'),
        destructive: true
      })).then(function(value) {
        if (value !== (impact.confirmation_text || user.username)) return null;
        return requestUserDeletion(user, value);
      });
    }

    function beginUserDeletion(user) {
      return authenticatedFetch(
        '/api/admin/users/' + encodeURIComponent(user.username) + '/deletion-impact'
      ).then(function(response) {
        if (!response.ok) return showResponseError(response, 'admin');
        return readJson(response).then(function(payload) {
          return confirmUserDeletion(user, payload.impact || {});
        });
      }).catch(function() {
        showStatus('admin.error.network', 'error');
      });
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
          if (user.enabled) {
            return confirmAdminAction('admin.confirmDisableUser', { username: user.username }, {
              titleKey: 'admin.disableUser', confirmTextKey: 'admin.disableUser'
            }).then(function(confirmed) {
              return confirmed ? updateUser(user.username, { enabled: false }) : null;
            });
          }
          return updateUser(user.username, { enabled: !user.enabled });
        }, user.enabled ? 'danger' : undefined));
        accountActionButtons.appendChild(actionButton(user.role === 'admin' ? 'admin.makeMember' : 'admin.makeAdmin', function() {
          var actionKey = user.role === 'admin' ? 'admin.makeMember' : 'admin.makeAdmin';
          return confirmAdminAction(
            user.role === 'admin' ? 'admin.confirmMakeMember' : 'admin.confirmMakeAdmin',
            { username: user.username },
            { titleKey: actionKey, confirmTextKey: actionKey }
          ).then(function(confirmed) {
            return confirmed
              ? updateUser(user.username, { role: user.role === 'admin' ? 'member' : 'admin' })
              : null;
          });
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
          return authenticatedFetch('/api/admin/users/' + encodeURIComponent(user.username) + '/password', {
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
          return confirmAdminAction('admin.confirmRevokeSessions', { username: user.username }, {
            titleKey: 'admin.revokeSessions', confirmTextKey: 'admin.revokeSessions'
          }).then(function(confirmed) {
            return confirmed ? updateUser(user.username, { revoke_sessions: true }) : null;
          });
        }, 'danger'));

        var oidcIdentities = Array.isArray(user.oidc_identities) ? user.oidc_identities : [];
        if (oidcIdentities.length) {
          var oidcActions = root.document.createElement('section');
          oidcActions.className = 'account-user-action-group account-user-oidc-group';
          oidcActions.appendChild(createTextElement(
            'h5', 'account-user-action-title', 'admin.oidc.connectedIdentity'
          ));
          oidcIdentities.forEach(function(oidcIdentity) {
            var identityRow = root.document.createElement('div');
            var identityCopy = root.document.createElement('span');
            var remove = actionButton('admin.oidc.removeIdentity', function() {
              return confirmAdminAction('admin.oidc.removeIdentityConfirm', {
                username: user.username,
                provider: oidcIdentity.provider_name || ''
              }, {
                titleKey: 'admin.oidc.removeIdentity',
                confirmTextKey: 'admin.oidc.removeIdentity'
              }).then(function(confirmed) {
                if (!confirmed) return null;
                return authenticatedFetch(
                  '/api/admin/users/' + encodeURIComponent(user.username) + '/oidc/identity?issuer=' +
                    encodeURIComponent(oidcIdentity.issuer || ''),
                  { method: 'DELETE' }
                ).then(function(response) {
                  if (!response.ok) return showResponseError(response, 'admin');
                  return loadAdminData();
                });
              });
            }, 'danger');
            identityRow.className = 'account-user-oidc-row';
            identityCopy.textContent = [
              oidcIdentity.provider_name,
              oidcIdentity.display_name || oidcIdentity.username || oidcIdentity.email
            ].filter(Boolean).join(' · ');
            identityRow.appendChild(identityCopy);
            identityRow.appendChild(remove);
            oidcActions.appendChild(identityRow);
          });
          detailsBody.appendChild(oidcActions);
        }

        detailsBody.appendChild(accountActions);
        detailsBody.appendChild(securityActions);
        if (!sessionState.user || user.id !== sessionState.user.id) {
          var dangerActions = root.document.createElement('section');
          var dangerHelp = createTextElement(
            'p', 'account-user-danger-help', 'admin.deleteUserHelp'
          );
          dangerActions.className = 'account-user-action-group account-user-danger-zone';
          dangerActions.appendChild(createTextElement(
            'h5', 'account-user-action-title', 'admin.dangerZone'
          ));
          dangerActions.appendChild(dangerHelp);
          dangerActions.appendChild(actionButton(
            'admin.deleteUser', function() { return beginUserDeletion(user); }, 'danger'
          ));
          detailsBody.appendChild(dangerActions);
        }
        details.appendChild(detailsSummary);
        details.appendChild(detailsBody);
        item.appendChild(details);
        list.appendChild(item);
      });
    }

    function renderOidcSettings() {
      var form = element('adminOidcForm');
      if (!form || !oidcSettings || !form.elements) return;
      var fields = form.elements;
      fields.enabled.checked = Boolean(oidcSettings.enabled);
      fields.provider_name.value = oidcSettings.provider_name || '';
      fields.issuer_url.value = oidcSettings.issuer_url || '';
      fields.client_id.value = oidcSettings.client_id || '';
      fields.client_secret.value = '';
      fields.client_secret.placeholder = oidcSettings.client_secret_configured
        ? t('admin.oidc.secretConfigured') : t('admin.oidc.secretPlaceholder');
      fields.clear_client_secret.checked = false;
      fields.redirect_uri.value = oidcSettings.redirect_uri || '';
      fields.scopes.value = (oidcSettings.scopes || ['openid', 'profile', 'email']).join(' ');
      fields.username_claim.value = oidcSettings.username_claim || 'preferred_username';
      fields.auto_create_users.checked = Boolean(oidcSettings.auto_create_users);
      fields.allow_member_password_login.checked = oidcSettings.allow_member_password_login !== false;
      setTextMessage(
        element('adminOidcMessage'),
        oidcSettings.enabled ? 'admin.oidc.statusConfigured' : 'admin.oidc.statusDisabled',
        oidcSettings.enabled ? 'success' : ''
      );
    }

    function oidcScopes(value) {
      var seen = Object.create(null);
      return String(value || '').split(/[\s,]+/).map(function(scope) {
        return scope.trim();
      }).filter(function(scope) {
        if (!scope || seen[scope]) return false;
        seen[scope] = true;
        return true;
      });
    }

    function oidcUrlIsValid(value, callback) {
      try {
        var parsed = new URL(String(value || ''));
        var loopback = parsed.hostname === 'localhost' || parsed.hostname === '127.0.0.1' || parsed.hostname === '::1';
        if (parsed.protocol !== 'https:' && !(loopback && parsed.protocol === 'http:')) return false;
        if (parsed.username || parsed.password || parsed.hash) return false;
        if (callback) return !parsed.search && parsed.pathname === '/auth/oidc/callback';
        return !parsed.search && (parsed.pathname === '' || parsed.pathname === '/' || parsed.pathname.slice(-1) !== '/');
      } catch (error) {
        return false;
      }
    }

    function validateOidcForm(form) {
      var fields = form.elements;
      var invalid = null;
      Array.prototype.forEach.call(form.querySelectorAll ? form.querySelectorAll('[aria-invalid="true"]') : [], function(field) {
        if (field.removeAttribute) field.removeAttribute('aria-invalid');
      });
      function reject(field) {
        if (!invalid) invalid = field;
        if (field && field.setAttribute) field.setAttribute('aria-invalid', 'true');
      }
      if (!formValue(form, 'username_claim').trim()) reject(fields.username_claim);
      if (fields.enabled.checked) {
        ['provider_name', 'issuer_url', 'client_id', 'redirect_uri'].forEach(function(name) {
          if (!formValue(form, name).trim()) reject(fields[name]);
        });
        if (!(oidcSettings && oidcSettings.client_secret_configured) && !formValue(form, 'client_secret').trim()) {
          reject(fields.client_secret);
        }
        if (fields.clear_client_secret.checked) reject(fields.client_secret);
        if (!oidcUrlIsValid(formValue(form, 'issuer_url'), false)) reject(fields.issuer_url);
        if (!oidcUrlIsValid(formValue(form, 'redirect_uri'), true)) reject(fields.redirect_uri);
        if (oidcScopes(formValue(form, 'scopes')).indexOf('openid') === -1) reject(fields.scopes);
      }
      if (invalid) {
        setTextMessage(element('adminOidcMessage'), 'admin.oidc.validationError', 'error');
        if (typeof invalid.focus === 'function') invalid.focus();
        return false;
      }
      return true;
    }

    function setOidcFormBusy(form, busy) {
      if (!form) return;
      form.setAttribute('aria-busy', String(busy));
      Array.prototype.forEach.call(
        form.querySelectorAll ? form.querySelectorAll('input, button, select') : [],
        function(control) { control.disabled = busy; }
      );
    }

    function saveOidcSettings(form) {
      if (oidcSaveRequest || !validateOidcForm(form)) return oidcSaveRequest || Promise.resolve(null);
      var fields = form.elements;
      var payload = {
        enabled: Boolean(fields.enabled.checked),
        provider_name: formValue(form, 'provider_name').trim(),
        issuer_url: formValue(form, 'issuer_url').trim(),
        client_id: formValue(form, 'client_id').trim(),
        redirect_uri: formValue(form, 'redirect_uri').trim(),
        scopes: oidcScopes(formValue(form, 'scopes')),
        username_claim: formValue(form, 'username_claim').trim(),
        auto_create_users: Boolean(fields.auto_create_users.checked),
        allow_member_password_login: Boolean(fields.allow_member_password_login.checked),
        clear_client_secret: Boolean(fields.clear_client_secret.checked)
      };
      var secret = formValue(form, 'client_secret');
      if (secret) payload.client_secret = secret;
      setOidcFormBusy(form, true);
      setTextMessage(element('adminOidcMessage'), 'admin.oidc.saving', '');
      oidcSaveRequest = authenticatedFetch('/api/admin/oidc/settings', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      }).then(function(response) {
        if (!response.ok) {
          return readJson(response).then(function(errorPayload) {
            var code = errorPayload && errorPayload.code;
            var known = ['invalid_oidc_settings', 'oidc_configuration_invalid', 'oidc_configuration_unsupported', 'oidc_discovery_invalid', 'oidc_provider_unavailable'];
            setTextMessage(
              element('adminOidcMessage'),
              known.indexOf(code) !== -1 ? 'admin.error.' + code : 'admin.oidc.validationError',
              'error'
            );
            return null;
          });
        }
        return readJson(response).then(function(result) {
          oidcSettings = result.settings || oidcSettings;
          renderOidcSettings();
          clearAdminDirty();
          setTextMessage(element('adminOidcMessage'), 'admin.oidc.saved', 'success');
          return oidcSettings;
        });
      }).catch(function() {
        setTextMessage(element('adminOidcMessage'), 'admin.oidc.networkError', 'error');
        return null;
      }).then(function(result) {
        oidcSaveRequest = null;
        setOidcFormBusy(form, false);
        return result;
      }, function(error) {
        oidcSaveRequest = null;
        setOidcFormBusy(form, false);
        throw error;
      });
      return oidcSaveRequest;
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
      var connectionStatus = element('adminAiConnectionStatus');
      if (connectionStatus) {
        var statusKey = !aiSettings.enabled
          ? 'admin.ai.connection.disabled'
          : (aiSettings.api_key_configured
            ? 'admin.ai.connection.ready' : 'admin.ai.connection.needsKey');
        connectionStatus.textContent = t(statusKey);
        connectionStatus.className = 'admin-ai-connection-status ' + (
          aiSettings.enabled && aiSettings.api_key_configured ? 'is-ready' : 'is-muted'
        );
      }
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
        var enabledTrack = root.document.createElement('span');
        var enabledText = root.document.createElement('span');
        var limit = root.document.createElement('input');
        var limitLabel = root.document.createElement('label');
        var limitText = root.document.createElement('span');
        var access = user.ai_access || {};
        item.className = 'account-list-item admin-ai-access-item';
        name.textContent = user.username;
        controls.className = 'admin-ai-access-controls';
        enabled.type = 'checkbox';
        enabled.checked = Boolean(access.enabled);
        enabledLabel.className = 'admin-ai-access-toggle';
        enabledTrack.className = 'admin-ai-access-toggle-track';
        enabledTrack.setAttribute('aria-hidden', 'true');
        enabledText.className = 'admin-ai-access-toggle-text';
        enabledText.textContent = t('admin.ai.allowed');
        enabledLabel.appendChild(enabled);
        enabledLabel.appendChild(enabledTrack);
        enabledLabel.appendChild(enabledText);
        limit.type = 'number';
        limit.min = '0';
        limit.value = access.daily_limit === null || access.daily_limit === undefined ? '' : String(access.daily_limit);
        limit.placeholder = t('admin.ai.defaultLimit');
        limitLabel.className = 'admin-ai-access-quota';
        limitText.className = 'admin-ai-access-quota-label';
        limitText.textContent = t('admin.ai.dailyOverride');
        limitLabel.appendChild(limitText);
        limitLabel.appendChild(limit);
        controls.appendChild(enabledLabel);
        controls.appendChild(limitLabel);
        controls.appendChild(actionButton('admin.ai.saveAccess', function() {
          var parsed = limit.value === '' ? null : Number(limit.value);
          if (parsed !== null && (!Number.isInteger(parsed) || parsed < 0)) {
            showStatus('admin.error.invalid_ai_access', 'error');
            return;
          }
          return saveAiUserAccess(user, enabled.checked, parsed);
        }));
        item.appendChild(name);
        item.appendChild(controls);
        list.appendChild(item);
      });
      if (!members.length) list.appendChild(createTextElement('li', 'account-empty', 'admin.ai.noMembers'));
    }

    function renderAiTags() {
      var list = element('adminAiTagList');
      var search = element('adminAiTagSearch');
      var searchControl = element('adminAiTagSearchControl');
      var query = compactSearchText(aiTagSearchQuery);
      var visibleTags;
      if (!list) return;
      if (searchControl) searchControl.hidden = aiTags.length <= 8;
      if (search && search.value !== aiTagSearchQuery) search.value = aiTagSearchQuery;
      if (aiTags.length <= 8 && aiTagSearchQuery) {
        aiTagSearchQuery = '';
        query = '';
        if (search) search.value = '';
      }
      visibleTags = aiTags.filter(function(tag) {
        return !query || compactSearchText(tag && tag.name).indexOf(query) !== -1;
      });
      list.textContent = '';
      visibleTags.forEach(function(tag) {
        var item = root.document.createElement('li');
        var summary = root.document.createElement('div');
        var name = root.document.createElement('strong');
        var usage = root.document.createElement('span');
        var actions = root.document.createElement('div');
        var count = safeNonNegativeInteger(tag.book_count, 0);
        var editControlId = 'adminAiTagEdit-' + encodeURIComponent(tag.id);
        item.className = 'account-list-item admin-ai-tag-item';
        summary.className = 'admin-ai-tag-summary';
        name.className = 'admin-ai-tag-name';
        name.textContent = tag.name;
        usage.className = 'admin-ai-tag-usage';
        usage.textContent = t('admin.ai.tagUsage', {
          count: count
        });
        summary.appendChild(name);
        summary.appendChild(usage);
        actions.className = 'admin-ai-tag-actions';
        var editButton = actionButton('admin.ai.editTag', function() {
          aiTagEditingId = tag.id;
          showAiTagMessage('', '');
          renderAiTags();
          var editorInput = element('adminAiTagEditorInput');
          if (editorInput && typeof editorInput.focus === 'function') {
            editorInput.focus();
            if (typeof editorInput.select === 'function') editorInput.select();
          }
        });
        editButton.id = editControlId;
        editButton.setAttribute('aria-controls', 'adminAiTagList');
        actions.appendChild(editButton);
        actions.appendChild(actionButton('admin.ai.deleteTag', function() {
          return confirmAdminAction('admin.ai.deleteTagConfirm', {
            name: tag.name,
            count: count
          }, {
            titleKey: 'admin.ai.deleteTag', confirmTextKey: 'admin.ai.deleteTag'
          }).then(function(confirmed) {
            if (!confirmed) return null;
            return authenticatedFetch('/api/admin/ai/tags/' + encodeURIComponent(tag.id), {
              method: 'DELETE'
            }).then(function(response) {
              if (!response.ok) return showAiTagResponseError(response);
              if (aiTagEditingId === tag.id) aiTagEditingId = '';
              showAiTagMessage('admin.ai.tagDeleted', 'success', { name: tag.name });
              refreshVisibleLibraryMetadata();
              return loadAdminData();
            }).catch(function() { showAiTagMessage('admin.error.network', 'error'); });
          });
        }, 'danger'));
        if (aiTagEditingId === tag.id) {
          var editor = root.document.createElement('form');
          var label = root.document.createElement('label');
          var labelText = root.document.createElement('span');
          var input = root.document.createElement('input');
          var editorActions = root.document.createElement('div');
          var cancel = createTextElement('button', 'bookshelf-action-btn account-inline-action', 'admin.ai.cancelTagEdit');
          var save = createTextElement('button', 'bookshelf-action-btn account-primary-action', 'admin.ai.saveTag');
          editor.className = 'admin-ai-tag-editor';
          label.className = 'admin-ai-tag-editor-field';
          labelText.className = 'sr-only visually-hidden';
          labelText.textContent = t('admin.ai.renameTagLabel', { name: tag.name });
          input.id = 'adminAiTagEditorInput';
          input.type = 'text';
          input.maxLength = 80;
          input.required = true;
          input.value = tag.name;
          editorActions.className = 'admin-ai-tag-editor-actions';
          cancel.type = 'button';
          save.type = 'submit';
          label.appendChild(labelText);
          label.appendChild(input);
          editorActions.appendChild(cancel);
          editorActions.appendChild(save);
          editor.appendChild(label);
          editor.appendChild(editorActions);
          function closeEditor() {
            aiTagEditingId = '';
            showAiTagMessage('', '');
            renderAiTags();
            var restoredEdit = element(editControlId);
            if (restoredEdit && typeof restoredEdit.focus === 'function') restoredEdit.focus();
          }
          cancel.addEventListener('click', function() {
            closeEditor();
          });
          editor.addEventListener('keydown', function(event) {
            if (event.key !== 'Escape') return;
            event.preventDefault();
            closeEditor();
          });
          editor.addEventListener('submit', function(event) {
            event.preventDefault();
            var nextName = String(input.value || '').trim();
            if (!nextName) {
              showAiTagMessage('admin.error.invalid_ai_tag', 'error');
              input.focus();
              return;
            }
            runButtonOperation(save, 'admin.ai.renamingTag', function() {
              return authenticatedFetch('/api/admin/ai/tags/' + encodeURIComponent(tag.id), {
                method: 'PUT', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name: nextName })
              }).then(function(response) {
                if (!response.ok) return showAiTagResponseError(response);
                return readJson(response).then(function(payload) {
                  var savedName = payload && payload.tag && payload.tag.name
                    ? payload.tag.name : nextName;
                  aiTagEditingId = '';
                  showAiTagMessage('admin.ai.tagRenamed', 'success', { name: savedName });
                  refreshVisibleLibraryMetadata();
                  return loadAdminData();
                });
              }).catch(function() { showAiTagMessage('admin.error.network', 'error'); });
            });
          });
          item.appendChild(editor);
        } else {
          item.appendChild(summary);
          item.appendChild(actions);
        }
        list.appendChild(item);
      });
      if (!aiTags.length) list.appendChild(createTextElement('li', 'account-empty', 'admin.ai.noTags'));
      else if (!visibleTags.length) list.appendChild(createTextElement('li', 'account-empty', 'admin.ai.noMatchingTags'));
    }

    function clearAiResults(scope, reload) {
      return authenticatedFetch('/api/admin/ai/results', {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(scope || {})
      }).then(function(response) {
        if (!response.ok) {
          return reload === false ? null : showResponseError(response, 'admin');
        }
        return readJson(response).then(function(payload) {
          showStatus('admin.ai.cacheCleared', 'success');
          return reload === false ? payload : loadAdminData();
        });
      }).catch(function() { showStatus('admin.error.network', 'error'); });
    }

    function renderLegacyBooks() {
      var list = element('adminBookLegacyList');
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
        var managedTags = root.document.createElement('p');
        managedTags.className = 'admin-book-tags';
        managedTags.textContent = t('admin.books.tags') + ': ' + (managedBookTags(book).map(function(tag) {
          return tag && tag.name;
        }).filter(Boolean).join(', ') || t('admin.ai.noTags'));
        header.appendChild(title);
        header.appendChild(managedTags);
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
          checkbox.checked = managedBookTags(book).some(function(assigned) {
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
            refreshVisibleLibraryMetadata();
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

    function compactSearchText(value) {
      return String(value || '').toLocaleLowerCase().replace(/\s+/g, '');
    }

    function managedBookTags(book) {
      if (book && Array.isArray(book.tags)) return book.tags;
      if (book && Array.isArray(book.ai_tags) && book.ai_tags.length) return book.ai_tags;
      return book && Array.isArray(book.epub_tags) ? book.epub_tags.map(function(name) {
        return { id: '', name: name };
      }) : [];
    }

    function adminBookSearchText(book) {
      var tags = managedBookTags(book);
      var literal = [book.title].concat(book.authors || [], book.epub_tags || [], tags.map(function(tag) {
        return tag && tag.name;
      })).join(' ');
      var pinyin = '';
      if (root.pinyinPro && typeof root.pinyinPro.pinyin === 'function') {
        try {
          pinyin = root.pinyinPro.pinyin(literal, { toneType: 'none' });
        } catch (error) {
          pinyin = '';
        }
      }
      return compactSearchText(literal) + ' ' + compactSearchText(pinyin);
    }

    function adminBookView(book) {
      return {
        book: book || {},
        searchText: adminBookSearchText(book || {})
      };
    }

    function showAdminBookTable() {
      var surface = element('adminBookTableSurface');
      var legacy = element('adminBookLegacyList');
      if (surface) surface.hidden = false;
      if (legacy) {
        legacy.hidden = true;
        legacy.textContent = '';
      }
    }

    function adminBookSort(left, right) {
      var locale = i18n() && typeof i18n().getLocale === 'function' ? i18n().getLocale() : undefined;
      var title = String(left.book.title || '').localeCompare(
        String(right.book.title || ''), locale, { sensitivity: 'base' }
      );
      if (adminBooksState.sort === 'title_desc' && title) return -title;
      if (adminBooksState.sort === 'created_desc' || adminBooksState.sort === 'updated_desc') {
        var timestampKey = adminBooksState.sort === 'created_desc' ? 'created_at' : 'updated_at';
        var leftTime = Date.parse(String(left.book[timestampKey] || '')) || 0;
        var rightTime = Date.parse(String(right.book[timestampKey] || '')) || 0;
        if (leftTime !== rightTime) return rightTime - leftTime;
      }
      if (title) return title;
      return String(left.book.id || '').localeCompare(String(right.book.id || ''), locale, {
        sensitivity: 'base'
      });
    }

    function filteredAdminBooks() {
      var query = compactSearchText(adminBooksState.query);
      return adminBooksState.books.filter(function(view) {
        var book = view.book;
        if (query && view.searchText.indexOf(query) === -1) return false;
        if (adminBooksState.visibility && book.visibility !== adminBooksState.visibility) return false;
        if (adminBooksState.tagId && !managedBookTags(book).some(function(tag) {
          return tag && tag.id === adminBooksState.tagId;
        })) return false;
        return true;
      }).sort(adminBookSort);
    }

    function createAdminBookCell(row, value, className) {
      var cell = root.document.createElement('td');
      if (className) cell.className = className;
      cell.textContent = value;
      row.appendChild(cell);
      return cell;
    }

    function populateAdminBookTagFilter() {
      var filter = element('adminBookTagFilter');
      if (!filter) return;
      var selected = adminBooksState.tagId;
      var tagsById = Object.create(null);
      adminBooksState.books.forEach(function(view) {
        managedBookTags(view.book).forEach(function(tag) {
          if (tag && tag.id && !tagsById[tag.id]) tagsById[tag.id] = tag;
        });
      });
      filter.textContent = '';
      var all = root.document.createElement('option');
      all.value = '';
      all.textContent = t('admin.books.tag.all');
      all.setAttribute('data-i18n', 'admin.books.tag.all');
      filter.appendChild(all);
      Object.keys(tagsById).sort(function(left, right) {
        return String(tagsById[left].name || '').localeCompare(String(tagsById[right].name || ''));
      }).forEach(function(id) {
        var tag = tagsById[id];
        var option = root.document.createElement('option');
        option.value = id;
        option.textContent = String(tag.name || '');
        option.selected = id === selected;
        filter.appendChild(option);
      });
      if (!tagsById[selected]) adminBooksState.tagId = '';
      filter.value = adminBooksState.tagId;
    }

    function renderAdminBookPagination(total, totalPages) {
      var pagination = element('adminBookPagination');
      if (!pagination) return;
      pagination.textContent = '';
      var summary = root.document.createElement('span');
      summary.className = 'admin-book-page-summary';
      summary.textContent = t('admin.books.pageSummary', {
        page: adminBooksState.page,
        totalPages: totalPages,
        total: total
      });
      pagination.appendChild(summary);
      function pageButton(key, page, disabled) {
        var button = root.document.createElement('button');
        button.type = 'button';
        button.className = 'bookshelf-action-btn account-inline-action admin-book-page';
        button.disabled = disabled;
        button.textContent = t(key, { page: page });
        button.setAttribute('aria-label', t(key, { page: page }));
        if (key === 'admin.books.pageButton' && page === adminBooksState.page) {
          button.setAttribute('aria-current', 'page');
        }
        button.addEventListener('click', function() {
          adminBooksState.page = page;
          renderAdminBooks();
        });
        pagination.appendChild(button);
      }
      pageButton('admin.books.previousPage', Math.max(1, adminBooksState.page - 1), adminBooksState.page <= 1);
      var pages = {};
      [1, adminBooksState.page - 2, adminBooksState.page - 1, adminBooksState.page,
        adminBooksState.page + 1, adminBooksState.page + 2, totalPages].forEach(function(page) {
        if (page >= 1 && page <= totalPages) pages[page] = true;
      });
      Object.keys(pages).map(Number).sort(function(left, right) {
        return left - right;
      }).forEach(function(page) {
        pageButton('admin.books.pageButton', page, page === adminBooksState.page);
      });
      pageButton('admin.books.nextPage', Math.min(totalPages, adminBooksState.page + 1), adminBooksState.page >= totalPages);
    }

    function renderAdminBookMessage(key) {
      var list = element('adminBookList');
      if (!list) return;
      showAdminBookTable();
      list.textContent = '';
      var row = root.document.createElement('tr');
      var cell = createAdminBookCell(row, t(key));
      cell.colSpan = 7;
      cell.setAttribute('data-i18n', key);
      list.appendChild(row);
      var pagination = element('adminBookPagination');
      if (pagination) pagination.textContent = '';
    }

    function selectedAdminBookIds() {
      return Object.keys(adminBooksState.selectedBookIds).filter(function(bookId) {
        return adminBooksState.selectedBookIds[bookId] === true;
      });
    }

    function selectedAdminBookGrantUserIds() {
      return Object.keys(adminBooksState.bulkGrantUserIds).filter(function(userId) {
        return adminBooksState.bulkGrantUserIds[userId] === true;
      });
    }

    function renderAdminBookBulkActions() {
      var surface = element('adminBookBulkActions');
      var count = selectedAdminBookIds().length;
      var summary = element('adminBookSelectionCount');
      var clear = element('adminBookClearSelection');
      var restrict = element('adminBookBulkRestrict');
      var members = element('adminBookBulkMembers');
      var grant = element('adminBookBulkGrant');
      var grantFieldset = element('adminBookBulkGrantFieldset');
      if (surface) surface.hidden = count === 0;
      if (summary) summary.textContent = t('admin.books.bulk.selectionCount', { count: count });
      if (clear) clear.disabled = adminBooksState.bulkBusy;
      if (restrict) restrict.disabled = !count || adminBooksState.bulkBusy;
      if (members) {
        members.textContent = '';
        var grantableUsers = users.filter(function(user) {
          return user && user.enabled && user.role === 'member';
        });
        grantableUsers.forEach(function(user) {
          var option = editorCheckbox(
            user.username,
            user.id,
            adminBooksState.bulkGrantUserIds[user.id] === true
          );
          option.checkbox.setAttribute('aria-label', String(user.username || ''));
          option.checkbox.addEventListener('change', function() {
            adminBooksState.bulkGrantUserIds[user.id] = Boolean(option.checkbox.checked);
            renderAdminBookBulkActions();
          });
          members.appendChild(option.label);
        });
        if (!grantableUsers.length) {
          members.appendChild(createTextElement('p', 'account-empty', 'admin.books.bulk.noMembers'));
        }
      }
      if (grantFieldset) grantFieldset.disabled = adminBooksState.bulkBusy;
      if (grant) {
        grant.disabled = !count || !selectedAdminBookGrantUserIds().length || adminBooksState.bulkBusy;
      }
    }

    function setAdminBookSelection(bookId, selected) {
      if (selected) adminBooksState.selectedBookIds[bookId] = true;
      else delete adminBooksState.selectedBookIds[bookId];
    }

    function setVisibleAdminBookSelection(visible, selected) {
      visible.forEach(function(view) {
        if (view && view.book && view.book.id) setAdminBookSelection(view.book.id, selected);
      });
    }

    function renderAdminBooks() {
      var list = element('adminBookList');
      if (!list) return;
      showAdminBookTable();
      populateAdminBookTagFilter();
      var matching = filteredAdminBooks();
      var totalPages = Math.max(1, Math.ceil(matching.length / adminBooksState.pageSize));
      if (adminBooksState.page > totalPages) adminBooksState.page = totalPages;
      var start = (adminBooksState.page - 1) * adminBooksState.pageSize;
      var visible = matching.slice(start, start + adminBooksState.pageSize);
      list.textContent = '';
      var selectPage = element('adminBookSelectPage');
      if (selectPage) {
        var selectedVisible = visible.filter(function(view) {
          return view && view.book && adminBooksState.selectedBookIds[view.book.id] === true;
        }).length;
        selectPage.checked = Boolean(visible.length && selectedVisible === visible.length);
        selectPage.indeterminate = selectedVisible > 0 && selectedVisible < visible.length;
        selectPage.disabled = !visible.length || adminBooksState.bulkBusy;
      }
      if (!visible.length) {
        var emptyRow = root.document.createElement('tr');
        var emptyCell = createAdminBookCell(emptyRow, t('admin.books.empty'));
        emptyCell.colSpan = 7;
        emptyCell.setAttribute('data-i18n', 'admin.books.empty');
        list.appendChild(emptyRow);
      }
      visible.forEach(function(view) {
        var book = view.book;
        var row = root.document.createElement('tr');
        var selectCell = createAdminBookCell(row, '', 'admin-book-select-column');
        var select = root.document.createElement('input');
        select.type = 'checkbox';
        select.className = 'admin-book-row-select';
        select.checked = adminBooksState.selectedBookIds[book.id] === true;
        select.disabled = adminBooksState.bulkBusy;
        select.setAttribute('aria-label', t('admin.books.bulk.selectBook', {
          title: String(book.title || '')
        }));
        select.addEventListener('change', function() {
          setAdminBookSelection(book.id, Boolean(select.checked));
          renderAdminBooks();
        });
        selectCell.appendChild(select);
        var bookCell = createAdminBookCell(row, '', 'admin-book-summary');
        var title = root.document.createElement('strong');
        title.textContent = String(book.title || '');
        bookCell.appendChild(title);
        if (String(book.format || 'epub').toLowerCase() === 'pdf') {
          var formatBadge = root.document.createElement('span');
          formatBadge.className = 'admin-book-format-badge';
          formatBadge.textContent = t('pdf.formatBadge');
          bookCell.appendChild(formatBadge);
        }
        var authors = Array.isArray(book.authors) ? book.authors.filter(Boolean) : [];
        if (authors.length) {
          var authorLine = root.document.createElement('span');
          authorLine.className = 'admin-book-authors';
          authorLine.textContent = authors.join(', ');
          bookCell.appendChild(authorLine);
        }
        createAdminBookCell(row, t('admin.books.visibility.' + (book.visibility || 'authenticated')) + ' · ' + t('admin.books.grantCount', {
          count: Number(book.grant_count || 0)
        }), 'admin-book-access');
        var profile = String(book.ai_profile || 'auto');
        var serverTags = managedBookTags(book).map(function(tag) { return tag && tag.name; }).filter(Boolean);
        createAdminBookCell(row, t('admin.books.profile.' + profile) + (serverTags.length ? ' · ' + serverTags.join(', ') : ''), 'admin-book-profile');
        createAdminBookCell(row, t('admin.books.resultCount', { count: Number(book.ai_result_count || 0) }), 'admin-book-results-count');
        createAdminBookCell(row, formatDate(book.updated_at), 'admin-book-updated');
        var actions = createAdminBookCell(row, '', 'admin-book-actions');
        var manage = root.document.createElement('button');
        manage.type = 'button';
        manage.className = 'bookshelf-action-btn account-inline-action admin-book-manage';
        manage.textContent = t('admin.books.manage');
        manage.setAttribute('data-book-id', String(book.id || ''));
        manage.setAttribute('aria-label', t('admin.books.manageLabel', { title: String(book.title || '') }));
        manage.setAttribute('aria-controls', adminBookEditorId(book.id));
        manage.setAttribute('aria-expanded', String(adminBooksState.expandedBookId === book.id));
        manage.addEventListener('click', function() { return openAdminBookEditor(book.id); });
        actions.appendChild(manage);
        list.appendChild(row);
      });
      renderAdminBookPagination(matching.length, totalPages);
      renderAdminBookBulkActions();
      renderAdminBookEditorModal();
    }

    function adminBookEditorId() {
      return 'adminBookEditorModal';
    }

    function editorCheckbox(labelText, value, checked) {
      var label = root.document.createElement('label');
      var checkbox = root.document.createElement('input');
      var text = root.document.createElement('span');
      label.className = 'account-book-grant-option';
      checkbox.type = 'checkbox';
      checkbox.value = String(value || '');
      checkbox.checked = Boolean(checked);
      text.textContent = String(labelText || '');
      label.appendChild(checkbox);
      label.appendChild(text);
      return { label: label, checkbox: checkbox };
    }

    function editorSelectedValues(checkboxes) {
      return checkboxes.filter(function(checkbox) { return checkbox.checked; }).map(function(checkbox) {
        return checkbox.value;
      });
    }

    function renderAdminBookEditor(book) {
      var panel = root.document.createElement('section');
      panel.className = 'admin-book-editor';
      panel.setAttribute('aria-label', t('admin.books.editorLabel', { title: String(book.title || '') }));
      panel.setAttribute('aria-busy', String(adminBooksState.editorBusy));
      var heading = root.document.createElement('h5');
      heading.id = 'adminBookEditorModalTitle';
      heading.className = 'admin-book-editor-title';
      heading.textContent = t('admin.books.editorTitle', { title: String(book.title || '') });
      panel.appendChild(heading);
      if (adminBooksState.editorBusy) {
        panel.appendChild(createTextElement(
          'p',
          'account-empty',
          adminBooksState.editorDraft ? 'admin.books.saving' : 'admin.books.loading'
        ));
        if (!adminBooksState.editorDraft) panel.appendChild(adminBookCancelButton(book));
        return panel;
      }
      if (adminBooksState.editorError || !adminBooksState.detailCache[book.id]) {
        panel.appendChild(createTextElement('p', 'account-empty', 'admin.books.detailError'));
        panel.appendChild(adminBookCancelButton(book));
        return panel;
      }
      var detail = adminBooksState.detailCache[book.id];
      var draft = adminBooksState.editorDraft || {
        title: detail.title || '',
        authors: detail.authors || [],
        visibility: detail.visibility || 'authenticated',
        user_ids: detail.grants || [],
        tag_ids: managedBookTags(detail).map(function(tag) { return tag && tag.id; }),
        profile: detail.ai_profile || 'auto'
      };
      var grid = root.document.createElement('div');
      var metadata = root.document.createElement('fieldset');
      var metadataLegend = createTextElement('legend', '', 'admin.books.metadata');
      var titleField = root.document.createElement('label');
      var titleText = root.document.createElement('span');
      var titleInput = root.document.createElement('input');
      var titleError = root.document.createElement('span');
      var authorsField = root.document.createElement('label');
      var authorsText = root.document.createElement('span');
      var authorsInput = root.document.createElement('textarea');
      var authorsHelp = root.document.createElement('span');
      var authorsError = root.document.createElement('span');
      var visibilityField = root.document.createElement('label');
      var visibilityText = root.document.createElement('span');
      var visibility = root.document.createElement('select');
      var grants = root.document.createElement('fieldset');
      var grantLegend = createTextElement('legend', '', 'admin.books.memberAccess');
      var grantOptions = root.document.createElement('div');
      var tags = root.document.createElement('fieldset');
      var tagLegend = createTextElement('legend', '', 'admin.books.tags');
      var tagOptions = root.document.createElement('div');
      var profileField = root.document.createElement('label');
      var profileText = root.document.createElement('span');
      var profile = root.document.createElement('select');
      var grantChecks = [];
      var tagChecks = [];
      var metadataIdSuffix = encodeURIComponent(String(book.id || ''));
      grid.className = 'admin-book-editor-grid';
      metadata.className = 'account-book-grants admin-book-metadata-fields';
      metadata.appendChild(metadataLegend);
      titleField.className = 'admin-book-field admin-book-metadata-field';
      titleText.textContent = t('admin.books.bookTitle') + ' · ' + t('admin.books.required');
      titleInput.type = 'text';
      titleInput.required = true;
      titleInput.maxLength = 500;
      titleInput.value = String(draft.title || '');
      titleInput.setAttribute('aria-describedby', 'adminBookTitleError-' + metadataIdSuffix);
      titleError.id = 'adminBookTitleError-' + metadataIdSuffix;
      titleError.className = 'admin-book-field-error';
      titleError.setAttribute('role', 'alert');
      titleError.hidden = true;
      titleField.appendChild(titleText);
      titleField.appendChild(titleInput);
      titleField.appendChild(titleError);
      authorsField.className = 'admin-book-field admin-book-metadata-field';
      authorsText.textContent = t('admin.books.authors');
      authorsInput.rows = 3;
      authorsInput.value = (draft.authors || []).join('\n');
      authorsInput.setAttribute('aria-describedby', 'adminBookAuthorsHelp-' + metadataIdSuffix + ' adminBookAuthorsError-' + metadataIdSuffix);
      authorsHelp.id = 'adminBookAuthorsHelp-' + metadataIdSuffix;
      authorsHelp.className = 'admin-book-field-help';
      authorsHelp.textContent = t('admin.books.authorsHelp');
      authorsError.id = 'adminBookAuthorsError-' + metadataIdSuffix;
      authorsError.className = 'admin-book-field-error';
      authorsError.setAttribute('role', 'alert');
      authorsError.hidden = true;
      authorsField.appendChild(authorsText);
      authorsField.appendChild(authorsInput);
      authorsField.appendChild(authorsHelp);
      authorsField.appendChild(authorsError);
      metadata.appendChild(titleField);
      metadata.appendChild(authorsField);
      visibilityField.className = 'admin-book-field';
      visibilityText.textContent = t('admin.books.visibilityLabel');
      visibilityField.appendChild(visibilityText);
      ['authenticated', 'restricted'].forEach(function(value) {
        var option = root.document.createElement('option');
        option.value = value;
        option.textContent = t(adminBookVisibilityTranslationKeys[value]);
        option.selected = value === draft.visibility;
        visibility.appendChild(option);
      });
      visibility.value = draft.visibility;
      visibilityField.appendChild(visibility);
      grants.className = 'account-book-grants';
      grantOptions.className = 'account-book-grant-options';
      grants.appendChild(grantLegend);
      users.filter(function(user) { return user.enabled && user.role === 'member'; }).forEach(function(user) {
        var option = editorCheckbox(user.username, user.id, (draft.user_ids || []).indexOf(user.id) !== -1);
        grantChecks.push(option.checkbox);
        grantOptions.appendChild(option.label);
      });
      grants.appendChild(grantOptions);
      grants.disabled = visibility.value !== 'restricted';
      visibility.addEventListener('change', function() {
        grants.disabled = visibility.value !== 'restricted';
        adminBooksState.editorDirty = true;
      });
      tags.className = 'account-book-grants';
      tagOptions.className = 'account-book-grant-options';
      tags.appendChild(tagLegend);
      var editorTagsById = Object.create(null);
      aiTags.concat(managedBookTags(detail)).forEach(function(tag) {
        if (tag && tag.id) editorTagsById[tag.id] = tag;
      });
      Object.keys(editorTagsById).sort(function(left, right) {
        return String(editorTagsById[left].name || '').localeCompare(
          String(editorTagsById[right].name || '')
        );
      }).forEach(function(tagId) {
        var tag = editorTagsById[tagId];
        var option = editorCheckbox(tag.name, tag.id, (draft.tag_ids || []).indexOf(tag.id) !== -1);
        tagChecks.push(option.checkbox);
        tagOptions.appendChild(option.label);
      });
      tags.appendChild(tagOptions);
      profileField.className = 'admin-book-field';
      profileText.textContent = t('admin.books.aiProfile');
      profileField.appendChild(profileText);
      ['auto', 'technical', 'fiction', 'general'].forEach(function(value) {
        var option = root.document.createElement('option');
        option.value = value;
        option.textContent = t(adminBookProfileTranslationKeys[value]);
        option.selected = value === draft.profile;
        profile.appendChild(option);
      });
      profile.value = draft.profile;
      profileField.appendChild(profile);
      [titleInput, authorsInput].forEach(function(control) {
        control.addEventListener('input', function() { adminBooksState.editorDirty = true; });
      });
      [profile].concat(grantChecks, tagChecks).forEach(function(control) {
        control.addEventListener('change', function() { adminBooksState.editorDirty = true; });
      });
      grid.appendChild(metadata);
      grid.appendChild(visibilityField);
      grid.appendChild(grants);
      grid.appendChild(tags);
      grid.appendChild(profileField);
      panel.appendChild(grid);
      if (adminBooksState.editorSaveError) {
        panel.appendChild(createTextElement('p', 'account-empty', 'admin.books.saveError'));
      }
      var actions = root.document.createElement('div');
      actions.className = 'admin-book-editor-actions';
      var save = root.document.createElement('button');
      save.type = 'button';
      save.className = 'bookshelf-action-btn account-inline-action admin-book-save-action';
      save.textContent = t('admin.books.save');
      function authorsValue() {
        return authorsInput.value.split(/\r?\n/).map(function(author) {
          return author.trim();
        }).filter(Boolean);
      }
      function validateMetadata() {
        var normalizedTitle = titleInput.value.trim();
        var authors = authorsValue();
        var titleInvalid = !normalizedTitle;
        var authorsInvalid = authors.length > 100 || authors.some(function(author) {
          return author.length > 500;
        });
        titleError.hidden = !titleInvalid;
        titleError.textContent = titleInvalid ? t('admin.books.titleRequired') : '';
        titleInput.setAttribute('aria-invalid', String(titleInvalid));
        authorsError.hidden = !authorsInvalid;
        authorsError.textContent = authorsInvalid ? t('admin.books.authorsInvalid') : '';
        authorsInput.setAttribute('aria-invalid', String(authorsInvalid));
        return !titleInvalid && !authorsInvalid;
      }
      titleInput.addEventListener('blur', validateMetadata);
      authorsInput.addEventListener('blur', validateMetadata);
      save.addEventListener('click', function() {
        if (!validateMetadata()) {
          if (titleInput.getAttribute('aria-invalid') === 'true') titleInput.focus();
          else authorsInput.focus();
          return;
        }
        saveAdminBookSettings(book.id, {
          title: titleInput.value.trim(),
          authors: authorsValue(),
          visibility: visibility.value,
          user_ids: editorSelectedValues(grantChecks),
          tag_ids: editorSelectedValues(tagChecks),
          profile: profile.value
        });
      });
      var clear = root.document.createElement('button');
      clear.type = 'button';
      clear.className = 'bookshelf-action-btn account-danger-action admin-book-clear-action';
      clear.textContent = t('admin.books.clearResults');
      clear.setAttribute('aria-label', t('admin.books.clearResultsLabel', { title: String(book.title || '') }));
      clear.addEventListener('click', function() { clearAdminBookResults(book.id, book.title); });
      actions.appendChild(clear);
      actions.appendChild(adminBookCancelButton(book));
      actions.appendChild(save);
      panel.appendChild(actions);
      return panel;
    }

    function adminBookSummary(bookId) {
      for (var index = 0; index < adminBooksState.books.length; index += 1) {
        var view = adminBooksState.books[index];
        if (view && view.book && view.book.id === bookId) return view.book;
      }
      return null;
    }

    function setAdminBookModalBackground(active) {
      var consolePanel = element('adminConsole');
      var adminPanel = element('adminPanel');
      if (consolePanel) {
        consolePanel.inert = Boolean(active);
        consolePanel.setAttribute('aria-hidden', String(Boolean(active)));
      }
      if (adminPanel) adminPanel.setAttribute('aria-modal', String(!active));
    }

    function renderAdminBookEditorModal() {
      var modal = element('adminBookEditorModal');
      var content = element('adminBookEditorContent');
      var close = element('adminBookEditorClose');
      if (!modal || !content) return;
      var book = adminBookSummary(adminBooksState.expandedBookId);
      if (!book) {
        content.textContent = '';
        modal.hidden = true;
        modal.setAttribute('aria-hidden', 'true');
        setAdminBookModalBackground(false);
        return;
      }
      content.textContent = '';
      content.appendChild(renderAdminBookEditor(book));
      modal.hidden = false;
      modal.setAttribute('aria-hidden', 'false');
      setAdminBookModalBackground(true);
      if (close) {
        close.disabled = Boolean(adminBooksState.editorDraft && adminBooksState.editorBusy);
        close.setAttribute('aria-label', t('admin.books.cancelLabel', {
          title: String(book.title || '')
        }));
      }
      var firstField = content.querySelector && content.querySelector('input[type="text"]');
      if (!adminBooksState.editorBusy && firstField && typeof firstField.focus === 'function') {
        firstField.focus();
      } else if (close && typeof close.focus === 'function') {
        close.focus();
      }
    }

    function adminBookCancelButton(book) {
      var cancel = root.document.createElement('button');
      cancel.type = 'button';
      cancel.className = 'bookshelf-action-btn account-inline-action';
      cancel.textContent = t('admin.books.cancel');
      cancel.setAttribute('aria-label', t('admin.books.cancelLabel', { title: String(book.title || '') }));
      cancel.addEventListener('click', function() { closeAdminBookEditor(book.id, true); });
      return cancel;
    }

    function focusAdminBookManage(bookId) {
      var list = element('adminBookList');
      if (!list) return;
      var children = list.children || [];
      for (var index = 0; index < children.length; index += 1) {
        var stack = [children[index]];
        while (stack.length) {
          var node = stack.pop();
          if (node && node.getAttribute && node.getAttribute('data-book-id') === String(bookId)) {
            if (typeof node.focus === 'function') node.focus();
            return;
          }
          Array.prototype.forEach.call(node && node.children || [], function(child) { stack.push(child); });
        }
      }
    }

    function closeAdminBookEditor(bookId, restoreFocus) {
      if (adminBooksState.expandedBookId !== bookId) return Promise.resolve(true);
      if (adminBooksState.editorBusy && adminBooksState.editorDraft) return Promise.resolve(false);
      var confirmation = adminBooksState.editorDirty
        ? confirmAdminAction('admin.books.discardChangesConfirm', null, {
          titleKey: 'admin.books.closeEditor', confirmTextKey: 'admin.discardChanges'
        })
        : Promise.resolve(true);
      return confirmation.then(function(confirmed) {
        if (!confirmed) return false;
        adminBooksState.editorGeneration += 1;
        adminBooksState.expandedBookId = null;
        adminBooksState.editorBusy = false;
        adminBooksState.editorError = false;
        adminBooksState.editorSaveError = false;
        adminBooksState.editorDraft = null;
        adminBooksState.editorDirty = false;
        renderAdminBooks();
        if (restoreFocus) focusAdminBookManage(bookId);
        return true;
      });
    }

    async function openAdminBookEditor(bookId) {
      if (!bookId) return null;
      if (adminBooksState.expandedBookId === bookId) {
        await closeAdminBookEditor(bookId, true);
        return null;
      }
      if (
        adminBooksState.expandedBookId
        && !await closeAdminBookEditor(adminBooksState.expandedBookId, false)
      ) return null;
      var generation = ++adminBooksState.editorGeneration;
      adminBooksState.expandedBookId = bookId;
      adminBooksState.editorError = false;
      adminBooksState.editorSaveError = false;
      adminBooksState.editorDraft = null;
      adminBooksState.editorDirty = false;
      adminBooksState.editorBusy = !adminBooksState.detailCache[bookId];
      renderAdminBooks();
      if (adminBooksState.detailCache[bookId]) return adminBooksState.detailCache[bookId];
      return authenticatedFetch('/api/admin/books/' + encodeURIComponent(bookId)).then(function(response) {
        if (!response || !response.ok) return null;
        return readJson(response).then(function(payload) {
          if (generation !== adminBooksState.editorGeneration || adminBooksState.expandedBookId !== bookId) return null;
          adminBooksState.detailCache[bookId] = payload && payload.book;
          adminBooksState.editorBusy = false;
          adminBooksState.editorError = !adminBooksState.detailCache[bookId];
          renderAdminBooks();
          return adminBooksState.detailCache[bookId];
        });
      }).catch(function() { return null; }).then(function(detail) {
        if (!detail && generation === adminBooksState.editorGeneration && adminBooksState.expandedBookId === bookId) {
          adminBooksState.editorBusy = false;
          adminBooksState.editorError = true;
          renderAdminBooks();
        }
        return detail;
      });
    }

    function handleAdminBookEditorKeydown(event) {
      var modal = element('adminBookEditorModal');
      if (!modal || modal.hidden || !adminBooksState.expandedBookId) return;
      if (event.key === 'Escape') {
        event.preventDefault();
        closeAdminBookEditor(adminBooksState.expandedBookId, true);
        return;
      }
      if (event.key !== 'Tab' || typeof modal.querySelectorAll !== 'function') return;
      var focusable = Array.prototype.filter.call(
        modal.querySelectorAll('button, input, select, textarea, [tabindex]'),
        function(control) {
          return !control.disabled && !control.hidden
            && control.getAttribute('aria-hidden') !== 'true'
            && control.getAttribute('tabindex') !== '-1';
        }
      );
      if (!focusable.length) return;
      var first = focusable[0];
      var last = focusable[focusable.length - 1];
      if (event.shiftKey && root.document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && root.document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }

    function patchAdminBookSummary(summary) {
      if (!summary || !summary.id) return;
      adminBooksState.books = adminBooksState.books.map(function(view) {
        return view.book.id === summary.id ? adminBookView(summary) : view;
      });
    }

    function saveAdminBookSettings(bookId, payload) {
      var generation = ++adminBooksState.editorGeneration;
      if (adminBooksState.expandedBookId === bookId) {
        adminBooksState.editorDraft = payload;
        adminBooksState.editorSaveError = false;
        adminBooksState.editorBusy = true;
        setAdminBookLive('admin.books.live.saving');
        renderAdminBooks();
      }
      return authenticatedFetch('/api/admin/books/' + encodeURIComponent(bookId) + '/settings', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      }).then(function(response) {
        if (!response || !response.ok) return null;
        return readJson(response).then(function(result) {
          if (generation !== adminBooksState.editorGeneration) return null;
          patchAdminBookSummary(result && result.summary);
          if (result && result.book) adminBooksState.detailCache[bookId] = result.book;
          adminBooksState.editorBusy = false;
          adminBooksState.editorError = false;
          adminBooksState.editorSaveError = false;
          adminBooksState.editorDraft = null;
          adminBooksState.editorDirty = false;
          adminBooksState.expandedBookId = null;
          renderAdminBooks();
          setAdminBookLive('admin.books.live.saved');
          focusAdminBookManage(bookId);
          refreshVisibleLibraryMetadata();
          return result;
        });
      }).catch(function() { return null; }).then(function(result) {
        if (!result && generation === adminBooksState.editorGeneration && adminBooksState.expandedBookId === bookId) {
          adminBooksState.editorBusy = false;
          adminBooksState.editorSaveError = true;
          renderAdminBooks();
          setAdminBookLive('admin.books.saveError');
        }
        return result;
      });
    }

    function clearAdminBookResults(bookId, title) {
      return confirmAdminAction('admin.books.clearResultsConfirm', {
        title: String(title || '')
      }, {
        titleKey: 'admin.books.clearResults', confirmTextKey: 'admin.books.clearResults'
      }).then(function(confirmed) {
        if (!confirmed) return null;
        var generation = ++adminBooksState.editorGeneration;
        if (adminBooksState.expandedBookId === bookId) {
          adminBooksState.editorBusy = true;
          renderAdminBooks();
        }
        return clearAiResults({ book_id: bookId }, false).then(function(payload) {
        if (generation !== adminBooksState.editorGeneration) return null;
        if (!payload) {
          adminBooksState.editorBusy = false;
          renderAdminBooks();
          setAdminBookLive('admin.books.clearError');
          return null;
        }
        var deleted = Number(payload.deleted || 0);
        var view = adminBooksState.books.filter(function(candidate) { return candidate.book.id === bookId; })[0];
        if (view) {
          var summary = {};
          Object.keys(view.book).forEach(function(key) { summary[key] = view.book[key]; });
          summary.ai_result_count = Math.max(0, Number(summary.ai_result_count || 0) - deleted);
          patchAdminBookSummary(summary);
        }
        if (adminBooksState.detailCache[bookId]) adminBooksState.detailCache[bookId].ai_result_count = 0;
        adminBooksState.editorBusy = false;
        renderAdminBooks();
        setAdminBookLive('admin.books.live.cleared', { count: deleted });
        return payload;
        });
      });
    }

    function setAdminBookIndex(records) {
      adminBooksState.editorGeneration += 1;
      adminBooksState.expandedBookId = null;
      adminBooksState.detailCache = Object.create(null);
      adminBooksState.editorBusy = false;
      adminBooksState.editorError = false;
      adminBooksState.editorSaveError = false;
      adminBooksState.editorDraft = null;
      adminBooksState.books = (Array.isArray(records) ? records : []).map(adminBookView);
      var activeBookIds = Object.create(null);
      adminBooksState.books.forEach(function(view) {
        if (view.book && view.book.id) activeBookIds[view.book.id] = true;
      });
      Object.keys(adminBooksState.selectedBookIds).forEach(function(bookId) {
        if (!activeBookIds[bookId]) delete adminBooksState.selectedBookIds[bookId];
      });
      populateAdminBookTagFilter();
      renderAdminBooks();
    }

    function setAdminBookLive(key, params) {
      var live = element('adminBookLive');
      if (live) live.textContent = t(key, params);
    }

    function beginAdminBookIndexLoad() {
      adminBooksState.requestGeneration += 1;
      renderAdminBookMessage('admin.books.loading');
      setAdminBookLive('admin.books.live.loading');
      return adminBooksState.requestGeneration;
    }

    function applyAdminBookIndex(generation, payload) {
      if (generation !== adminBooksState.requestGeneration) return null;
      setAdminBookIndex(payload && payload.books);
      setAdminBookLive('admin.books.live.loaded', { count: adminBooksState.books.length });
      return payload;
    }

    function loadAdminBookIndex() {
      if (!sessionState || !sessionState.user || sessionState.user.role !== 'admin') {
        return Promise.resolve(null);
      }
      var generation = beginAdminBookIndexLoad();
      return authenticatedFetch('/api/admin/books/index').then(function(response) {
        if (!response || !response.ok) return null;
        return readJson(response);
      }).then(function(payload) {
        if (payload) return applyAdminBookIndex(generation, payload);
        return null;
      }).catch(function() { return null; }).then(function(payload) {
        if (!payload && generation === adminBooksState.requestGeneration) {
          renderAdminBookMessage('admin.books.loadError');
        }
        return payload;
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

    function runAdminBookBulkOperation(operation, userIds) {
      var bookIds = selectedAdminBookIds();
      if (!bookIds.length || adminBooksState.bulkBusy) return Promise.resolve(null);
      var payload = { operation: operation, book_ids: bookIds };
      if (operation === 'grant') payload.user_ids = userIds || [];
      adminBooksState.bulkBusy = true;
      renderAdminBooks();
      return authenticatedFetch('/api/admin/books/bulk', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      }).then(function(response) {
        if (!response || !response.ok) {
          return readJson(response).then(function(error) {
            showStatus('admin.books.error.' + (
              error && error.code === 'invalid_bulk_book_update'
                ? 'invalid_bulk_book_update' : 'unknown'
            ), 'error');
            return null;
          });
        }
        return readJson(response).then(function(result) {
          return loadAdminBookIndex().then(function() {
            setAdminBookLive(
              operation === 'restrict'
                ? 'admin.books.live.bulkRestricted'
                : 'admin.books.live.bulkGranted',
              { count: Number(result && result.updated_count || bookIds.length) }
            );
            return result;
          });
        });
      }).catch(function() {
        showStatus('admin.books.error.network', 'error');
        return null;
      }).then(function(result) {
        adminBooksState.bulkBusy = false;
        renderAdminBooks();
        return result;
      }, function(error) {
        adminBooksState.bulkBusy = false;
        renderAdminBooks();
        throw error;
      });
    }

    function loadAdminData() {
      if (!sessionState || !sessionState.user || sessionState.user.role !== 'admin') {
        return Promise.resolve(null);
      }
      var bookIndexGeneration = beginAdminBookIndexLoad();
      var requests = [
        authenticatedFetch('/api/admin/users'),
        authenticatedFetch('/api/admin/books/index'),
        authenticatedFetch('/api/admin/ai/settings'),
        authenticatedFetch('/api/admin/ai/tags'),
        authenticatedFetch('/api/admin/oidc/settings')
      ];
      return Promise.all(requests).then(function(responses) {
        if (!responses[0].ok) return showResponseError(responses[0], 'admin');
        if (!responses[1].ok) return showResponseError(responses[1], 'admin');
        if (!responses[2].ok) return showResponseError(responses[2], 'admin');
        if (!responses[3].ok) return showResponseError(responses[3], 'admin');
        var payloadRequests = [
          readJson(responses[0]),
          readJson(responses[1]),
          readJson(responses[2]),
          readJson(responses[3]),
          responses[4].ok
            ? readJson(responses[4])
            : showResponseError(responses[4], 'admin').then(function() { return {}; })
        ];
        return Promise.all(payloadRequests).then(function(payloads) {
          users = payloads[0].users || [];
          applyAdminBookIndex(bookIndexGeneration, payloads[1]);
          aiSettings = payloads[2].settings || null;
          aiTags = payloads[3].tags || [];
          oidcSettings = payloads[4].settings || null;
          if (oidcSettings) {
            oidcSettings.redirect_uri_suggestion = payloads[4].suggested_redirect_uri || '';
          }
          renderUsers();
          renderAiSettings();
          renderAiUserAccess();
          renderAiTags();
          renderOidcSettings();
          renderAdminOverview();
          if (element('adminDictionaryList')) return loadDictionaries();
        });
      }).catch(function() { showStatus('admin.error.network', 'error'); });
    }

    function setSurfaceLoading(panelId, loadingId, loading) {
      var panel = element(panelId);
      var indicator = element(loadingId);
      if (panel) panel.setAttribute('aria-busy', loading ? 'true' : 'false');
      if (indicator) indicator.hidden = !loading;
    }

    function openPanel() {
      var panel = element('accountPanel');
      if (!panel) return;
      panel.classList.add('active');
      panel.setAttribute('aria-hidden', 'false');
      setSurfaceLoading('accountPanel', 'accountPanelLoading', true);
      renderAccountOidc();
      Promise.all([loadSessions(), loadPersonalAccessTokens()]).then(function() {
        setSurfaceLoading('accountPanel', 'accountPanelLoading', false);
      }, function() {
        setSurfaceLoading('accountPanel', 'accountPanelLoading', false);
      });
    }

    function closePanel() {
      var panel = element('accountPanel');
      if (!panel) return;
      panel.classList.remove('active');
      panel.setAttribute('aria-hidden', 'true');
      setSurfaceLoading('accountPanel', 'accountPanelLoading', false);
      clearPersonalAccessTokenSecret();
    }

    function openAdminPanel() {
      if (!sessionState || !sessionState.user || sessionState.user.role !== 'admin') return;
      var panel = element('adminPanel');
      if (!panel) return;
      panel.hidden = false;
      panel.classList.add('active');
      panel.setAttribute('aria-hidden', 'false');
      activeAdminSection = adminSectionFromHash() || activeAdminSection;
      setActiveAdminSection(activeAdminSection);
      setSurfaceLoading('adminPanel', 'adminPanelLoading', true);
      loadAdminData().then(function() {
        setSurfaceLoading('adminPanel', 'adminPanelLoading', false);
      }, function() {
        setSurfaceLoading('adminPanel', 'adminPanelLoading', false);
      });
      loadAdminAiJobs();
      loadWebhooks();
      startAdminAiJobPolling();
    }

    async function closeAdminPanel() {
      var panel = element('adminPanel');
      if (!panel) return;
      if (
        adminBooksState.expandedBookId
        && !await closeAdminBookEditor(adminBooksState.expandedBookId, false)
      ) return;
      if (adminHasUnsavedChanges && !await confirmAdminDiscardChanges()) return;
      clearAdminDirty();
      panel.classList.remove('active');
      panel.setAttribute('aria-hidden', 'true');
      setSurfaceLoading('adminPanel', 'adminPanelLoading', false);
      stopAdminAiJobPolling();
      showWebhookSecret('');
    }

    function bindUi() {
      var menu = element('accountMenu');
      var close = element('accountClose');
      var adminMenu = element('adminMenu');
      var adminClose = element('adminClose');
      var adminBookEditorClose = element('adminBookEditorClose');
      var logoutButton = element('accountLogout');
      var oidcLink = element('accountOidcLink');
      var oidcUnlink = element('accountOidcUnlink');
      var passwordForm = element('accountPasswordForm');
      var patCreateForm = element('patCreateForm');
      var patCreateSubmit = element('patCreateSubmit');
      var patCopySecret = element('patCopySecret');
      var webhookForm = element('adminWebhookForm');
      var webhookSubmit = element('adminWebhookSubmit');
      var webhookCopySecret = element('adminWebhookCopySecret');
      var webhookCancelEdit = element('adminWebhookCancelEdit');
      var createUserForm = element('adminUserForm');
      var createUserSubmit = element('adminUserSubmit');
      var oidcForm = element('adminOidcForm');
      var oidcUseSuggestion = element('adminOidcUseSuggestion');
      var aiSettingsForm = element('adminAiSettingsForm');
      var aiSettingsSubmit = element('adminAiSettingsSubmit');
      var aiTagForm = element('adminAiTagForm');
      var aiTagSubmit = element('adminAiTagSubmit');
      var aiTagSearch = element('adminAiTagSearch');
      var dictionaryForm = element('adminDictionaryForm');
      var dictionarySubmit = element('adminDictionarySubmit');
      var dictionaryAutoName = '';
      var setDictionaryFormat = function() {};
      var updateDictionaryFileLabels = function() {};
      var clearAiRevision = element('adminAiClearRevision');
      var clearAiAll = element('adminAiClearAll');
      var aiJobsStatus = element('adminAiJobsStatus');
      var aiJobsPageSize = element('adminAiJobsPageSize');
      var aiJobsRefresh = element('adminAiJobsRefresh');
      var bookSearch = element('adminBookSearch');
      var bookVisibilityFilter = element('adminBookVisibilityFilter');
      var bookTagFilter = element('adminBookTagFilter');
      var bookSort = element('adminBookSort');
      var bookPageSize = element('adminBookPageSize');
      var bookClearFilters = element('adminBookClearFilters');
      var bookRefresh = element('adminBookRefresh');
      var bookSelectPage = element('adminBookSelectPage');
      var bookClearSelection = element('adminBookClearSelection');
      var bookBulkRestrict = element('adminBookBulkRestrict');
      var bookBulkGrant = element('adminBookBulkGrant');
      var adminSectionControls = root.document && typeof root.document.querySelectorAll === 'function'
        ? Array.prototype.slice.call(root.document.querySelectorAll('[data-admin-section]')) : [];
      [createUserForm, oidcForm, aiSettingsForm, aiTagForm, dictionaryForm, webhookForm].forEach(function(form) {
        if (!form) return;
        form.addEventListener('input', markAdminDirty);
        form.addEventListener('change', markAdminDirty);
      });
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
      if (adminBookEditorClose) adminBookEditorClose.addEventListener('click', function() {
        if (adminBooksState.expandedBookId) {
          closeAdminBookEditor(adminBooksState.expandedBookId, true);
        }
      });
      if (root.document && typeof root.document.addEventListener === 'function') {
        root.document.addEventListener('keydown', handleAdminBookEditorKeydown);
      }
      adminSectionControls.forEach(function(control) {
        control.addEventListener('click', function() {
          var section = sectionForAdminControl(control);
          if (section) setActiveAdminSection(section);
        });
      });
      if (logoutButton) logoutButton.addEventListener('click', function() {
        logout().catch(function() { showStatus('account.error.network', 'error'); });
      });
      if (oidcLink) oidcLink.addEventListener('click', function() {
        if (oidcLink.disabled) return;
        oidcLink.disabled = true;
        authenticatedFetch('/api/account/oidc/link', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ next: oidcCurrentPath() })
        }).then(function(response) {
          if (!response.ok) return showResponseError(response, 'account');
          return readJson(response).then(function(payload) {
            if (payload && typeof payload.redirect === 'string' && payload.redirect.charAt(0) === '/') {
              root.location.assign(payload.redirect);
            }
          });
        }).catch(function() {
          setTextMessage(element('accountOidcLive'), 'account.error.network', 'error');
        }).then(function() { oidcLink.disabled = false; });
      });
      if (oidcUnlink) oidcUnlink.addEventListener('click', function() {
        var identities = sessionState && sessionState.user && sessionState.user.oidc_identities || [];
        var identity = identities[0];
        if (!identity || !identity.can_unlink || oidcUnlink.disabled) return;
        confirmAdminAction('account.oidc.unlinkConfirm', {
          provider: identity.provider_name || ''
        }, {
          titleKey: 'account.oidc.unlink',
          confirmTextKey: 'account.oidc.unlink'
        }).then(function(confirmed) {
          if (!confirmed) return null;
          oidcUnlink.disabled = true;
          return authenticatedFetch(
            '/api/account/oidc/identity?issuer=' + encodeURIComponent(identity.issuer || ''),
            { method: 'DELETE' }
          ).then(function(response) {
            if (!response.ok) return showResponseError(response, 'account');
            return loadSession(true).then(function() {
              renderAccountOidc();
              setTextMessage(element('accountOidcLive'), 'account.oidc.unlinked', 'success');
            });
          }).catch(function() {
            setTextMessage(element('accountOidcLive'), 'account.error.network', 'error');
          }).then(function() { oidcUnlink.disabled = false; });
        });
      });
      if (oidcUseSuggestion) oidcUseSuggestion.addEventListener('click', function() {
        if (!oidcForm || !oidcSettings) return;
        oidcForm.elements.redirect_uri.value = oidcSettings.redirect_uri_suggestion || '';
        markAdminDirty();
        if (oidcForm.elements.redirect_uri.focus) oidcForm.elements.redirect_uri.focus();
      });
      if (oidcForm) oidcForm.addEventListener('submit', function(event) {
        event.preventDefault();
        saveOidcSettings(oidcForm);
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
      if (patCreateForm) {
        patCreateForm.addEventListener('change', function(event) {
          var required = {
            'bookshelf:write': 'bookshelf:read',
            'progress:write': 'progress:read',
            'annotations:write': 'annotations:read',
            'reviews:write': 'reviews:read'
          };
          var readScope = event.target && required[event.target.value];
          if (!readScope || !event.target.checked || !patCreateForm.querySelector) return;
          var read = patCreateForm.querySelector('input[name="scopes"][value="' + readScope + '"]');
          if (read) read.checked = true;
        });
        patCreateForm.addEventListener('submit', function(event) {
          event.preventDefault();
          clearPersonalAccessTokenSecret();
          runButtonOperation(patCreateSubmit, 'account.pats.creating', function() {
            var selected = patCreateForm.querySelectorAll
              ? Array.prototype.map.call(
                  patCreateForm.querySelectorAll('input[name="scopes"]:checked'),
                  function(input) { return input.value; }
                ) : [];
            var expiration = formValue(patCreateForm, 'expires_in_days');
            return authenticatedFetch('/api/account/pats', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                name: formValue(patCreateForm, 'name'),
                current_password: formValue(patCreateForm, 'current_password'),
                scopes: selected,
                expires_in_days: expiration === 'never' ? null : Number(expiration)
              })
            }).then(function(response) {
              clearPasswordFields(patCreateForm);
              if (!response.ok) return showResponseError(response, 'account');
              return readJson(response).then(function(payload) {
                var secret = element('patCreatedSecret');
                var region = element('patSecretRegion');
                if (secret) secret.textContent = payload.token || '';
                if (region) region.hidden = false;
                if (patCreateForm.reset) patCreateForm.reset();
                showStatus('account.pats.created', 'success');
                return loadPersonalAccessTokens();
              });
            }).catch(function() { showStatus('account.error.network', 'error'); });
          });
        });
      }
      if (patCopySecret) patCopySecret.addEventListener('click', function() {
        var secret = element('patCreatedSecret');
        var value = secret && secret.textContent;
        copySensitiveText(value).then(function() {
          var live = element('patLive');
          if (live) live.textContent = t('account.pats.copied');
        }).catch(function() { showStatus('account.pats.copyFailed', 'error'); });
      });
      if (webhookCopySecret) webhookCopySecret.addEventListener('click', function() {
        var secret = element('adminWebhookSecret');
        copySensitiveText(secret && secret.textContent).then(function() {
          var live = element('adminWebhookLive');
          if (live) {
            live.setAttribute('data-i18n', 'admin.webhooks.copied');
            if (root.EpubBrowserI18n) root.EpubBrowserI18n.translateDocument(live.parentNode);
          }
        }).catch(function() { showStatus('admin.webhooks.copyFailed', 'error'); });
      });
      if (webhookCancelEdit) webhookCancelEdit.addEventListener('click', function() {
        webhookForm.reset();
        webhookForm.removeAttribute('data-editing-id');
        webhookForm.elements.enabled.checked = true;
        webhookCancelEdit.hidden = true;
        if (webhookSubmit) {
          webhookSubmit.setAttribute('data-i18n', 'admin.webhooks.create');
          if (root.EpubBrowserI18n) root.EpubBrowserI18n.translateDocument(webhookSubmit.parentNode);
        }
        if (webhookForm.elements.name.focus) webhookForm.elements.name.focus();
      });
      if (webhookForm) webhookForm.addEventListener('submit', function(event) {
        event.preventDefault();
        showWebhookSecret('');
        runButtonOperation(webhookSubmit, 'admin.webhooks.creating', function() {
          var events = Array.prototype.map.call(webhookForm.querySelectorAll('input[name="event_types"]:checked'), function(input) { return input.value; });
          var editingId = webhookForm.getAttribute('data-editing-id');
          return authenticatedFetch(editingId ? '/api/admin/webhooks/' + encodeURIComponent(editingId) : '/api/admin/webhooks', {
            method: editingId ? 'PUT' : 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: formValue(webhookForm, 'name'), url: formValue(webhookForm, 'url'), event_types: events, enabled: webhookForm.elements.enabled.checked })
          }).then(function(response) {
            if (!response.ok) return showResponseError(response, 'admin');
            return readJson(response).then(function(payload) {
              showWebhookSecret(payload.secret);
              webhookForm.reset();
              webhookForm.removeAttribute('data-editing-id');
              webhookForm.elements.enabled.checked = true;
              if (webhookCancelEdit) webhookCancelEdit.hidden = true;
              if (webhookSubmit) {
                webhookSubmit.setAttribute('data-i18n', 'admin.webhooks.create');
                if (root.EpubBrowserI18n) root.EpubBrowserI18n.translateDocument(webhookSubmit.parentNode);
              }
              clearAdminDirty();
              return loadWebhooks();
            });
          });
        });
      });
      if (createUserForm) createUserForm.addEventListener('submit', function(event) {
        event.preventDefault();
        runButtonOperation(createUserSubmit, 'admin.creatingUser', function() {
          return authenticatedFetch('/api/admin/users', {
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
            clearAdminDirty();
            showStatus('admin.userCreated', 'success');
            return loadAdminData();
          }).catch(function() { showStatus('admin.error.network', 'error'); });
        });
      });
      if (dictionaryForm) dictionaryForm.addEventListener('submit', function(event) {
        event.preventDefault();
        var format = dictionaryForm.elements.dictionary_format.value;
        var dictionaryFile = format === 'mdict'
          ? dictionaryForm.elements.mdict_archive.files[0]
          : dictionaryForm.elements.stardict_archive.files[0];
        if (!dictionaryFile) return;
        showDictionaryMessage('', '');
        runButtonOperation(dictionarySubmit, 'admin.installingDictionary', function() {
          function upload(file, target) {
            return file.arrayBuffer().then(function(contents) {
              return authenticatedFetch(target, {
                method: 'POST',
                headers: {
                  'Content-Type': file.type || 'application/octet-stream',
                  'X-EPUB-Browser-Dictionary-Filename': encodeURIComponent(file.name),
                  'X-EPUB-Browser-Dictionary-Name': encodeURIComponent(dictionaryForm.elements.display_name.value.trim()),
                  'X-EPUB-Browser-Dictionary-Format': format
                }, body: contents
              });
            });
          }
          return upload(dictionaryFile, '/api/admin/dictionaries').then(function(response) {
            if (!response.ok) return showDictionaryResponseError(response).then(function() { throw new Error('dictionary_upload_failed'); });
            return readJson(response);
          }).then(function(payload) {
            dictionaryForm.reset();
            setDictionaryFormat('mdict');
            updateDictionaryFileLabels();
            dictionaryAutoName = '';
            clearAdminDirty();
            showDictionaryMessage('admin.dictionaryInstalled', 'success');
            showStatus('admin.dictionaryInstalled', 'success');
            if (payload && payload.dictionary) {
              dictionaries = [payload.dictionary].concat(dictionaries);
              renderDictionaries();
            }
            return null;
          }, function(error) {
            if (error && /dictionary_upload_failed/.test(error.message)) return;
            showDictionaryMessage('admin.error.network', 'error');
            showStatus('admin.error.network', 'error');
          });
        });
      });
      if (dictionaryForm) {
        var dictionaryFormatInputs = dictionaryForm.querySelectorAll('input[name="dictionary_format"]');
        var dictionaryFileInputs = [dictionaryForm.elements.mdict_archive, dictionaryForm.elements.stardict_archive];
        var dictionaryNameInput = dictionaryForm.elements.display_name;
        function updateDictionaryFileLabel(input) {
          if (!input) return;
          var output = dictionaryForm.querySelector('[data-dictionary-file-name="' + input.name + '"]');
          var control = input.closest ? input.closest('.dictionary-file-control') : null;
          var file = input.files && input.files[0];
          var label = file && file.name ? file.name : t('admin.noDictionaryFile');
          if (output) output.textContent = label;
          if (control) control.classList.toggle('has-file', Boolean(file));
        }
        updateDictionaryFileLabels = function() {
          dictionaryFileInputs.forEach(updateDictionaryFileLabel);
        };
        setDictionaryFormat = function(format) {
          Array.prototype.forEach.call(dictionaryFormatInputs, function(input) {
            var selected = input.value === format;
            input.checked = selected;
            input.closest('.dictionary-format-option').classList.toggle('is-selected', selected);
          });
          Array.prototype.forEach.call(dictionaryForm.querySelectorAll('[data-dictionary-upload]'), function(group) {
            var selected = group.getAttribute('data-dictionary-upload') === format;
            group.hidden = !selected;
            Array.prototype.forEach.call(group.querySelectorAll('input[type="file"]'), function(input) {
              input.disabled = !selected;
              input.required = selected;
            });
          });
        };
        Array.prototype.forEach.call(dictionaryFormatInputs, function(input) {
          input.addEventListener('change', function() { setDictionaryFormat(input.value); });
        });
        dictionaryFileInputs.forEach(function(dictionaryFileInput) {
          dictionaryFileInput.addEventListener('change', function() {
            updateDictionaryFileLabel(dictionaryFileInput);
            var file = dictionaryFileInput.files && dictionaryFileInput.files[0];
            var fileName = file && file.name ? file.name.replace(/\.(?:mdx|zip|tar(?:\.(?:gz|bz2))?|tgz|tbz2)$/i, '').trim() : '';
            if (!fileName || (dictionaryNameInput.value.trim() && dictionaryNameInput.value !== dictionaryAutoName)) return;
            dictionaryNameInput.value = fileName;
            dictionaryAutoName = fileName;
          });
        });
        dictionaryNameInput.addEventListener('input', function() {
          if (dictionaryNameInput.value !== dictionaryAutoName) dictionaryAutoName = '';
        });
        setDictionaryFormat('mdict');
        updateDictionaryFileLabels();
      }
      if (aiSettingsForm) aiSettingsForm.addEventListener('submit', function(event) {
        event.preventDefault();
        var fields = aiSettingsForm.elements;
        runButtonOperation(aiSettingsSubmit, 'admin.ai.saving', function() {
          return authenticatedFetch('/api/admin/ai/settings', {
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
            clearAdminDirty();
            showStatus('admin.ai.settingsSaved', 'success');
            return loadAdminData();
          }).catch(function() { showStatus('admin.error.network', 'error'); });
        });
      });
      if (aiTagForm) aiTagForm.addEventListener('submit', function(event) {
        event.preventDefault();
        showAiTagMessage('', '');
        runButtonOperation(aiTagSubmit, 'admin.ai.addingTag', function() {
          return authenticatedFetch('/api/admin/ai/tags', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: formValue(aiTagForm, 'name') })
          }).then(function(response) {
            if (!response.ok) return showAiTagResponseError(response);
            aiTagForm.reset();
            clearAdminDirty();
            showAiTagMessage('admin.ai.tagAdded', 'success');
            return loadAdminData();
          }).catch(function() { showAiTagMessage('admin.error.network', 'error'); });
        });
      });
      if (aiTagSearch) aiTagSearch.addEventListener('input', function() {
        aiTagSearchQuery = aiTagSearch.value || '';
        renderAiTags();
      });
      if (clearAiRevision) clearAiRevision.addEventListener('click', function() {
        if (!aiSettings) return;
        confirmAdminAction('admin.ai.clearRevisionConfirm', null, {
          titleKey: 'admin.ai.clearRevision', confirmTextKey: 'admin.ai.clearRevision'
        }).then(function(confirmed) {
          if (confirmed) clearAiResults({ config_revision: aiSettings.config_revision });
        });
      });
      if (clearAiAll) clearAiAll.addEventListener('click', function() {
        confirmAdminAction('admin.ai.clearAllConfirm', null, {
          titleKey: 'admin.ai.clearAll', confirmTextKey: 'admin.ai.clearAll'
        }).then(function(confirmed) {
          if (confirmed) clearAiResults({});
        });
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
      if (bookSearch) bookSearch.addEventListener('input', function() {
        adminBooksState.query = String(bookSearch.value || '');
        adminBooksState.page = 1;
        renderAdminBooks();
      });
      if (bookVisibilityFilter) bookVisibilityFilter.addEventListener('change', function() {
        adminBooksState.visibility = String(bookVisibilityFilter.value || '');
        adminBooksState.page = 1;
        renderAdminBooks();
      });
      if (bookTagFilter) bookTagFilter.addEventListener('change', function() {
        adminBooksState.tagId = String(bookTagFilter.value || '');
        adminBooksState.page = 1;
        renderAdminBooks();
      });
      if (bookSort) bookSort.addEventListener('change', function() {
        var sort = String(bookSort.value || 'title_asc');
        adminBooksState.sort = ['title_asc', 'title_desc', 'created_desc', 'updated_desc']
          .indexOf(sort) !== -1 ? sort : 'title_asc';
        bookSort.value = adminBooksState.sort;
        adminBooksState.page = 1;
        renderAdminBooks();
      });
      if (bookPageSize) bookPageSize.addEventListener('change', function() {
        var selectedBookPageSize = Number(bookPageSize.value);
        adminBooksState.pageSize = [10, 20, 50, 100].indexOf(selectedBookPageSize) !== -1
          ? selectedBookPageSize : 20;
        adminBooksState.page = 1;
        renderAdminBooks();
      });
      if (bookClearFilters) bookClearFilters.addEventListener('click', function() {
        adminBooksState.query = '';
        adminBooksState.visibility = '';
        adminBooksState.tagId = '';
        adminBooksState.page = 1;
        if (bookSearch) bookSearch.value = '';
        if (bookVisibilityFilter) bookVisibilityFilter.value = '';
        if (bookTagFilter) bookTagFilter.value = '';
        renderAdminBooks();
        setAdminBookLive('admin.books.live.filtersCleared');
      });
      if (bookRefresh) bookRefresh.addEventListener('click', function() {
        loadAdminBookIndex();
      });
      if (bookSelectPage) bookSelectPage.addEventListener('change', function() {
        var matching = filteredAdminBooks();
        var start = (adminBooksState.page - 1) * adminBooksState.pageSize;
        setVisibleAdminBookSelection(
          matching.slice(start, start + adminBooksState.pageSize),
          Boolean(bookSelectPage.checked)
        );
        renderAdminBooks();
      });
      if (bookClearSelection) bookClearSelection.addEventListener('click', function() {
        if (adminBooksState.bulkBusy) return;
        adminBooksState.selectedBookIds = Object.create(null);
        renderAdminBooks();
      });
      if (bookBulkRestrict) bookBulkRestrict.addEventListener('click', function() {
        var count = selectedAdminBookIds().length;
        if (!count || adminBooksState.bulkBusy) return;
        confirmAdminBookBulkOperation('restrict', { count: count }).then(function(confirmed) {
          if (!confirmed || adminBooksState.bulkBusy) return null;
          return runButtonOperation(bookBulkRestrict, 'admin.books.bulk.restricting', function() {
            return runAdminBookBulkOperation('restrict');
          });
        });
      });
      if (bookBulkGrant) bookBulkGrant.addEventListener('click', function() {
        var bookIds = selectedAdminBookIds();
        var userIds = selectedAdminBookGrantUserIds();
        if (!bookIds.length || !userIds.length) return;
        var memberNames = users.filter(function(user) {
          return userIds.indexOf(user.id) !== -1;
        }).map(function(user) { return user.username; }).join(', ');
        if (adminBooksState.bulkBusy) return;
        confirmAdminBookBulkOperation('grant', {
          count: bookIds.length,
          members: memberNames
        }).then(function(confirmed) {
          if (!confirmed || adminBooksState.bulkBusy) return null;
          return runButtonOperation(bookBulkGrant, 'admin.books.bulk.granting', function() {
            return runAdminBookBulkOperation('grant', userIds);
          });
        });
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
          renderOidcSettings();
          renderAccountOidc();
          renderAiUserAccess();
          renderAiTags();
          renderAdminBooks();
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
      saveBookGrants: replaceBookGrants,
      loadAiJobs: loadAdminAiJobs,
      retryAiJob: retryAdminAiJob,
      loadBookIndex: loadAdminBookIndex,
      openBookEditor: openAdminBookEditor,
      saveBookSettings: saveAdminBookSettings,
      clearBookResults: clearAdminBookResults,
      normalizeOidcScopes: oidcScopes,
      isOidcUrlValid: oidcUrlIsValid,
      init: init,
      setSession: setSession,
      getSession: function() { return sessionState; }
    };
  }

  return { create: create };
});
