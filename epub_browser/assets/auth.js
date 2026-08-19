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

    function associate(credentials) {
      var options = {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(credentials || {})
      };
      var csrfToken = sessionState && sessionState.csrf_token;
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

    function actionButton(key, action) {
      var button = createTextElement('button', 'bookshelf-action-btn', key);
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
      if (adminPanel) adminPanel.hidden = sessionState.user.role !== 'admin';
    }

    function renderSessions(records) {
      var list = element('sessionList');
      if (!list) return;
      list.textContent = '';
      (records || []).forEach(function(record) {
        var item = root.document.createElement('li');
        var label = createTextElement('span', 'account-session-label', 'account.sessionDescription', {
          created: formatDate(record.created_at),
          lastUsed: formatDate(record.last_used_at)
        });
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
          }));
        }
        list.appendChild(item);
      });
      if (!(records || []).length) list.appendChild(createTextElement('li', '', 'account.noSessions'));
    }

    function loadSessions() {
      return authenticatedFetch('/api/account/sessions').then(function(response) {
        if (!response.ok) return showResponseError(response, 'account');
        return readJson(response).then(function(payload) { renderSessions(payload.sessions); });
      }).catch(function() { showStatus('account.error.network', 'error'); });
    }

    function userById(userId) {
      for (var index = 0; index < users.length; index++) {
        if (users[index].id === userId) return users[index];
      }
      return null;
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
        var summary = root.document.createElement('span');
        var password = root.document.createElement('input');
        summary.textContent = t('admin.userSummary', {
          username: user.username,
          role: roleLabel(user.role),
          status: enabledLabel(user.enabled)
        });
        item.appendChild(summary);
        item.appendChild(actionButton(user.enabled ? 'admin.disableUser' : 'admin.enableUser', function() {
          updateUser(user.username, { enabled: !user.enabled });
        }));
        item.appendChild(actionButton(user.role === 'admin' ? 'admin.makeMember' : 'admin.makeAdmin', function() {
          updateUser(user.username, { role: user.role === 'admin' ? 'member' : 'admin' });
        }));
        item.appendChild(actionButton('admin.revokeSessions', function() {
          updateUser(user.username, { revoke_sessions: true });
        }));
        password.type = 'password';
        password.autocomplete = 'new-password';
        password.placeholder = t('admin.newPassword');
        password.setAttribute('data-i18n-placeholder', 'admin.newPassword');
        item.appendChild(password);
        item.appendChild(actionButton('admin.resetPassword', function() {
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
        list.appendChild(item);
      });
    }

    function renderBooks() {
      var list = element('adminBookList');
      if (!list) return;
      list.textContent = '';
      books.forEach(function(book) {
        var item = root.document.createElement('li');
        var title = root.document.createElement('strong');
        var visibility = root.document.createElement('select');
        var grantUser = root.document.createElement('select');
        title.textContent = book.title;
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
        users.filter(function(user) { return user.enabled && user.role !== 'admin'; }).forEach(function(user) {
          var option = root.document.createElement('option');
          option.value = user.id;
          option.textContent = user.username;
          grantUser.appendChild(option);
        });
        grantUser.setAttribute('aria-label', t('admin.grantUser'));
        grantUser.setAttribute('data-i18n-aria-label', 'admin.grantUser');
        item.appendChild(grantUser);
        item.appendChild(actionButton('admin.grantBook', function() {
          if (!grantUser.value) return;
          mutateGrant(book.id, grantUser.value, 'PUT');
        }));
        (book.grants || []).forEach(function(userId) {
          var user = userById(userId);
          var revoke = actionButton('admin.revokeBook', function() {
            mutateGrant(book.id, userId, 'DELETE');
          });
          revoke.setAttribute('aria-label', t('admin.revokeBookFor', {
            username: user ? user.username : userId,
            book: book.title
          }));
          item.appendChild(revoke);
        });
        list.appendChild(item);
      });
      if (!books.length) list.appendChild(createTextElement('li', '', 'admin.noBooks'));
    }

    function mutateGrant(bookId, userId, method) {
      return authenticatedFetch(
        '/api/admin/books/' + encodeURIComponent(bookId) + '/grants/' + encodeURIComponent(userId),
        { method: method }
      ).then(function(response) {
        if (!response.ok) return showResponseError(response, 'admin');
        showStatus(method === 'PUT' ? 'admin.bookGranted' : 'admin.bookRevoked', 'success');
        return loadAdminData();
      }).catch(function() { showStatus('admin.error.network', 'error'); });
    }

    function loadAdminData() {
      if (!sessionState || !sessionState.user || sessionState.user.role !== 'admin') {
        return Promise.resolve(null);
      }
      return Promise.all([
        authenticatedFetch('/api/admin/users'),
        authenticatedFetch('/api/admin/books')
      ]).then(function(responses) {
        if (!responses[0].ok) return showResponseError(responses[0], 'admin');
        if (!responses[1].ok) return showResponseError(responses[1], 'admin');
        return Promise.all([readJson(responses[0]), readJson(responses[1])]).then(function(payloads) {
          users = payloads[0].users || [];
          books = payloads[1].books || [];
          renderUsers();
          renderBooks();
        });
      }).catch(function() { showStatus('admin.error.network', 'error'); });
    }

    function openPanel() {
      var panel = element('accountPanel');
      if (!panel) return;
      panel.classList.add('active');
      panel.setAttribute('aria-hidden', 'false');
      loadSessions();
      loadAdminData();
    }

    function closePanel() {
      var panel = element('accountPanel');
      if (!panel) return;
      panel.classList.remove('active');
      panel.setAttribute('aria-hidden', 'true');
    }

    function bindUi() {
      var menu = element('accountMenu');
      var close = element('accountClose');
      var logoutButton = element('accountLogout');
      var passwordForm = element('accountPasswordForm');
      var associationForm = element('associationForm');
      var createUserForm = element('adminUserForm');
      if (menu) menu.addEventListener('click', openPanel);
      if (close) close.addEventListener('click', closePanel);
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
      if (i18n() && i18n().onLocaleChange) {
        i18n().onLocaleChange(function() {
          renderIdentity();
          renderSessions([]);
          renderUsers();
          renderBooks();
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
      init: init,
      setSession: setSession,
      getSession: function() { return sessionState; }
    };
  }

  return { create: create };
});
