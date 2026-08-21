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
      var needsSession = unsafe && isSameOrigin(url) && !(sessionState && sessionState.csrf_token);
      var ready = needsSession ? loadSession(false) : Promise.resolve(sessionState);
      return ready.then(function() {
        var csrfToken = sessionState && sessionState.csrf_token;
        return Promise.resolve(root.fetch(url, requestOptions(options, csrfToken, url)))
          .then(handleUnauthorized);
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

    function renderBooks() {
      var list = element('adminBookList');
      if (!list) return;
      list.textContent = '';
      books.forEach(function(book) {
        var item = root.document.createElement('li');
        item.className = 'account-list-item account-book-item';
        var title = root.document.createElement('strong');
        var visibility = root.document.createElement('select');
        var grants = root.document.createElement('fieldset');
        var grantLegend = createTextElement('legend', '', 'admin.grantUsers');
        var grantOptions = root.document.createElement('div');
        var grantableUsers = users.filter(function(user) {
          return user.enabled && user.role === 'member';
        });
        title.textContent = book.title;
        title.className = 'account-book-title';
        item.appendChild(title);
        ['authenticated', 'restricted'].forEach(function(value) {
          var option = root.document.createElement('option');
          option.value = value;
          option.textContent = visibilityLabel(value);
          option.selected = value === book.visibility;
          visibility.appendChild(option);
        });
        visibility.setAttribute('aria-label', t('admin.bookVisibility'));
        visibility.setAttribute('data-i18n-aria-label', 'admin.bookVisibility');
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
        item.appendChild(visibility);
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
        item.appendChild(grants);
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
        item.appendChild(saveGrants);
        var ai = root.document.createElement('fieldset');
        var aiLegend = createTextElement('legend', '', 'admin.ai.bookSettings');
        var profile = root.document.createElement('select');
        var tagOptions = root.document.createElement('div');
        ai.className = 'account-book-grants admin-book-ai-settings';
        profile.setAttribute('aria-label', t('admin.ai.readingProfile'));
        profile.setAttribute('data-i18n-aria-label', 'admin.ai.readingProfile');
        ['auto', 'technical', 'fiction', 'general'].forEach(function(value) {
          var option = root.document.createElement('option');
          option.value = value;
          option.textContent = t('admin.ai.profile.' + value);
          option.selected = value === (book.ai_profile || 'auto');
          profile.appendChild(option);
        });
        tagOptions.className = 'account-book-grant-options';
        ai.appendChild(aiLegend);
        ai.appendChild(profile);
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
        ai.appendChild(tagOptions);
        item.appendChild(ai);
        item.appendChild(actionButton('admin.ai.saveBookSettings', function() {
          var tagIds = [];
          Array.prototype.forEach.call(tagOptions.querySelectorAll('input[type="checkbox"]'), function(checkbox) {
            if (checkbox.checked) tagIds.push(checkbox.value);
          });
          authenticatedFetch('/api/admin/books/' + encodeURIComponent(book.id) + '/ai', {
            method: 'PUT', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ profile: profile.value, tag_ids: tagIds })
          }).then(function(response) {
            if (!response.ok) return showResponseError(response, 'admin');
            showStatus('admin.ai.bookSaved', 'success');
            return loadAdminData();
          }).catch(function() { showStatus('admin.error.network', 'error'); });
        }));
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
    }

    function closeAdminPanel() {
      var panel = element('adminPanel');
      if (!panel) return;
      panel.classList.remove('active');
      panel.setAttribute('aria-hidden', 'true');
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
      init: init,
      setSession: setSession,
      getSession: function() { return sessionState; }
    };
  }

  return { create: create };
});
