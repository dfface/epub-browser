import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawn } from 'node:child_process';

const baseURL = process.env.OIDC_E2E_BASE_URL || 'https://127.0.0.1:18443';
const artifactDir = process.env.OIDC_E2E_ARTIFACT_DIR || path.join(path.dirname(new URL(import.meta.url).pathname), 'artifacts');
const timeoutMs = 30_000;

function chromiumExecutable() {
  const candidates = [
    process.env.EPUB_BROWSER_CHROMIUM,
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    '/Applications/Chromium.app/Contents/MacOS/Chromium',
    '/usr/bin/chromium',
    '/usr/bin/chromium-browser',
    '/usr/bin/google-chrome',
  ].filter(Boolean);
  const cache = path.join(os.homedir(), 'Library', 'Caches', 'ms-playwright');
  if (fs.existsSync(cache)) {
    for (const directory of fs.readdirSync(cache).sort().reverse()) {
      if (!directory.startsWith('chromium_headless_shell-')) continue;
      candidates.push(
        path.join(cache, directory, 'chrome-mac', 'headless_shell'),
        path.join(cache, directory, 'chrome-headless-shell-mac-arm64', 'chrome-headless-shell'),
        path.join(cache, directory, 'chrome-headless-shell-mac-x64', 'chrome-headless-shell'),
      );
    }
  }
  const executable = candidates.find(candidate => fs.existsSync(candidate));
  assert.ok(executable, 'No Chromium executable found; set EPUB_BROWSER_CHROMIUM');
  return executable;
}

class CDPConnection {
  constructor(url) {
    this.url = url;
    this.nextId = 1;
    this.pending = new Map();
    this.listeners = new Map();
  }

  async connect() {
    this.socket = new WebSocket(this.url);
    await new Promise((resolve, reject) => {
      this.socket.addEventListener('open', resolve, { once: true });
      this.socket.addEventListener('error', reject, { once: true });
    });
    this.socket.addEventListener('message', event => {
      const message = JSON.parse(String(event.data));
      if (message.id) {
        const pending = this.pending.get(message.id);
        if (!pending) return;
        this.pending.delete(message.id);
        if (message.error) pending.reject(new Error(message.error.message));
        else pending.resolve(message.result || {});
        return;
      }
      const listeners = this.listeners.get(message.method) || [];
      listeners.forEach(listener => listener(message.params || {}));
    });
  }

  send(method, params = {}) {
    const id = this.nextId++;
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      this.socket.send(JSON.stringify({ id, method, params }));
    });
  }

  on(method, listener) {
    const listeners = this.listeners.get(method) || [];
    listeners.push(listener);
    this.listeners.set(method, listeners);
  }

  close() {
    if (this.socket) this.socket.close();
  }
}

async function launchBrowser() {
  const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'epub-oidc-browser-'));
  const browser = spawn(chromiumExecutable(), [
    '--headless=new',
    '--disable-gpu',
    '--disable-dev-shm-usage',
    '--no-sandbox',
    '--no-proxy-server',
    '--ignore-certificate-errors',
    '--allow-insecure-localhost',
    '--disable-features=UseDnsHttpsSvcbAlpn,DnsOverHttps',
    '--remote-debugging-port=0',
    `--user-data-dir=${profile}`,
    'about:blank',
  ], { stdio: ['ignore', 'ignore', 'pipe'] });
  let stderr = '';
  const websocketURL = await new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error(`Chromium did not start: ${stderr.slice(-1000)}`)), timeoutMs);
    browser.stderr.on('data', chunk => {
      stderr += String(chunk);
      const match = stderr.match(/DevTools listening on (ws:\/\/[^\s]+)/);
      if (match) {
        clearTimeout(timer);
        resolve(match[1]);
      }
    });
    browser.once('exit', code => {
      clearTimeout(timer);
      reject(new Error(`Chromium exited early (${code}): ${stderr.slice(-1000)}`));
    });
  });
  const port = new URL(websocketURL).port;
  const target = await fetch(`http://127.0.0.1:${port}/json/new?about:blank`, { method: 'PUT' }).then(response => response.json());
  const connection = new CDPConnection(target.webSocketDebuggerUrl);
  await connection.connect();
  await Promise.all([
    connection.send('Page.enable'),
    connection.send('Runtime.enable'),
    connection.send('Network.enable'),
  ]);
  await connection.send('Emulation.setDeviceMetricsOverride', {
    width: 1440,
    height: 1000,
    deviceScaleFactor: 1,
    mobile: false,
  });
  connection.lastNetworkError = '';
  connection.on('Network.loadingFailed', event => {
    if (event.type === 'Document') connection.lastNetworkError = event.errorText || 'document load failed';
  });
  return {
    browser,
    profile,
    page: connection,
    async close() {
      connection.close();
      browser.kill('SIGTERM');
      await new Promise(resolve => browser.once('exit', resolve));
      fs.rmSync(profile, { recursive: true, force: true });
    },
  };
}

async function evaluate(page, expression) {
  const result = await page.send('Runtime.evaluate', {
    expression,
    awaitPromise: true,
    returnByValue: true,
  });
  if (result.exceptionDetails) {
    throw new Error(result.exceptionDetails.exception?.description || result.exceptionDetails.text);
  }
  return result.result?.value;
}

async function waitFor(page, expression, label, timeout = timeoutMs) {
  const deadline = Date.now() + timeout;
  let lastError = '';
  while (Date.now() < deadline) {
    try {
      if (await evaluate(page, `Boolean(${expression})`)) return;
    } catch (error) {
      lastError = error.message;
    }
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  const location = await evaluate(page, 'location.href').catch(() => 'unknown');
  const body = await evaluate(page, 'document.body ? document.body.innerText.slice(0, 500) : ""').catch(() => '');
  const network = page.lastNetworkError ? `; network=${page.lastNetworkError}` : '';
  throw new Error(`Timed out waiting for ${label} at ${location}${network}${lastError ? ` (${lastError})` : ''}${body ? `; body=${body}` : ''}`);
}

async function navigate(page, url) {
  await page.send('Page.navigate', { url });
  await waitFor(page, 'document.readyState === "complete"', `navigation to ${url}`);
}

async function click(page, selector) {
  const encoded = JSON.stringify(selector);
  await waitFor(page, `document.querySelector(${encoded}) && !document.querySelector(${encoded}).disabled && !document.querySelector(${encoded}).hidden`, selector);
  const clicked = await evaluate(page, `(() => { const node = document.querySelector(${encoded}); node.click(); return true; })()`);
  assert.equal(clicked, true);
}

async function fill(page, selector, value) {
  const encodedSelector = JSON.stringify(selector);
  const encodedValue = JSON.stringify(value);
  await waitFor(page, `document.querySelector(${encodedSelector})`, selector);
  await evaluate(page, `(() => {
    const node = document.querySelector(${encodedSelector});
    const setter = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(node), 'value')?.set;
    if (setter) setter.call(node, ${encodedValue}); else node.value = ${encodedValue};
    node.dispatchEvent(new Event('input', { bubbles: true }));
    node.dispatchEvent(new Event('change', { bubbles: true }));
  })()`);
}

async function check(page, selector, checked) {
  const encoded = JSON.stringify(selector);
  await waitFor(page, `document.querySelector(${encoded})`, selector);
  await evaluate(page, `(() => {
    const node = document.querySelector(${encoded});
    node.checked = ${checked ? 'true' : 'false'};
    node.dispatchEvent(new Event('input', { bubbles: true }));
    node.dispatchEvent(new Event('change', { bubbles: true }));
  })()`);
}

async function jsonFetch(page, url, options = {}) {
  const expression = `fetch(${JSON.stringify(url)}, ${JSON.stringify(options)}).then(async response => ({ status: response.status, body: await response.json().catch(() => ({})) }))`;
  return evaluate(page, expression);
}

async function screenshot(page, name) {
  const result = await page.send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false });
  fs.writeFileSync(path.join(artifactDir, name), Buffer.from(result.data, 'base64'));
}

async function setViewport(page, width, height, { dark = false, reducedMotion = false } = {}) {
  await page.send('Emulation.setDeviceMetricsOverride', {
    width,
    height,
    deviceScaleFactor: 1,
    mobile: width <= 480,
  });
  await page.send('Emulation.setEmulatedMedia', {
    features: [
      { name: 'prefers-color-scheme', value: dark ? 'dark' : 'light' },
      { name: 'prefers-reduced-motion', value: reducedMotion ? 'reduce' : 'no-preference' },
    ],
  });
  await evaluate(page, `document.documentElement.setAttribute('data-theme', ${JSON.stringify(dark ? 'dark' : 'light')})`);
  await new Promise(resolve => setTimeout(resolve, 100));
}

async function assertNoPageOverflow(page, label) {
  const dimensions = await evaluate(page, `({
    viewport: document.documentElement.clientWidth,
    content: document.documentElement.scrollWidth,
  })`);
  assert.ok(dimensions.content <= dimensions.viewport + 1, `${label} has horizontal page overflow: ${JSON.stringify(dimensions)}`);
}

async function assertAssociationKeyboardPath(page) {
  await evaluate(page, 'document.activeElement && document.activeElement.blur()');
  const reached = new Set();
  for (let index = 0; index < 8; index += 1) {
    await page.send('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Tab', code: 'Tab', windowsVirtualKeyCode: 9 });
    await page.send('Input.dispatchKeyEvent', { type: 'keyUp', key: 'Tab', code: 'Tab', windowsVirtualKeyCode: 9 });
    reached.add(await evaluate(page, `(() => {
      const node = document.activeElement;
      return node ? [node.tagName, node.getAttribute('name') || '', node.getAttribute('type') || ''].join(':') : '';
    })()`));
  }
  assert.ok(reached.has('INPUT:username:'), `keyboard did not reach username: ${Array.from(reached)}`);
  assert.ok(reached.has('INPUT:password:password'), `keyboard did not reach password: ${Array.from(reached)}`);
  assert.ok(reached.has('BUTTON::submit'), `keyboard did not reach submit: ${Array.from(reached)}`);
}

async function localLogin(page, username, password, expectSuccess = true) {
  await navigate(page, `${baseURL}/login`);
  await fill(page, '#loginForm [name="username"]', username);
  await fill(page, '#loginForm [name="password"]', password);
  await click(page, '#loginForm button[type="submit"]');
  if (expectSuccess) {
    await waitFor(page, 'location.hostname === "127.0.0.1" && location.pathname !== "/login"', `${username} local login`);
  } else {
    await waitFor(page, 'location.pathname === "/login" && !document.querySelector("#loginError").hidden', `${username} login rejection`);
  }
}

async function logout(page) {
  await navigate(page, `${baseURL}/`);
  await click(page, '#accountMenu');
  await waitFor(page, 'document.querySelector("#accountPanel").classList.contains("active")', 'account panel');
  await click(page, '#accountLogout');
  await waitFor(page, 'location.pathname === "/login" && Boolean(document.querySelector("#loginForm"))', 'logout');
}

async function loginAtAuthelia(page, username, password) {
  await waitFor(page, 'location.hostname === "127.0.0.1" && location.port === "18444"', 'Authelia login');
  const usernameSelector = 'input[name="username"], input#username-textfield, input[autocomplete="username"]';
  const passwordSelector = 'input[name="password"], input#password-textfield, input[autocomplete="current-password"]';
  const submitSelector = 'button[type="submit"], button#sign-in-button, form button';
  await fill(page, usernameSelector, username);
  const passwordPresent = await evaluate(page, `Boolean(document.querySelector(${JSON.stringify(passwordSelector)}))`);
  if (!passwordPresent) {
    await click(page, submitSelector);
    await waitFor(page, `document.querySelector(${JSON.stringify(passwordSelector)})`, 'Authelia password field');
  }
  await fill(page, passwordSelector, password);
  await click(page, submitSelector);
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const host = await evaluate(page, 'location.hostname');
    const port = await evaluate(page, 'location.port');
    if (host === '127.0.0.1' && port === '18443') return;
    const accepted = await evaluate(page, `(() => {
      const buttons = Array.from(document.querySelectorAll('button'));
      const button = buttons.find(node => /accept|allow|authorize|continue/i.test(node.textContent || ''));
      if (button) { button.click(); return true; }
      return false;
    })()`);
    await new Promise(resolve => setTimeout(resolve, accepted ? 250 : 100));
  }
  throw new Error(`Authelia did not return to EPUB Browser: ${await evaluate(page, 'location.href')}`);
}

async function configureOidc(page, { autoCreate, allowMemberPassword }) {
  await navigate(page, `${baseURL}/`);
  await click(page, '#adminMenu');
  await waitFor(page, 'document.querySelector("#adminPanel").classList.contains("active") && !document.querySelector("#adminPanel").getAttribute("aria-busy")?.includes("true")', 'administration panel');
  await click(page, '#adminSectionOidcTab');
  await check(page, '#adminOidcForm [name="enabled"]', true);
  await fill(page, '#adminOidcProviderName', 'Company SSO');
  await fill(page, '#adminOidcIssuerUrl', 'https://127.0.0.1:18444');
  await fill(page, '#adminOidcClientId', 'epub-browser-e2e');
  const currentSettings = await jsonFetch(page, '/api/admin/oidc/settings');
  assert.equal(currentSettings.status, 200);
  if (!currentSettings.body.settings.client_secret_configured) {
    await fill(page, '#adminOidcClientSecret', 'insecure_secret');
  }
  await fill(page, '#adminOidcRedirectUri', 'https://127.0.0.1:18443/auth/oidc/callback');
  await fill(page, '#adminOidcScopes', 'openid profile email');
  await fill(page, '#adminOidcUsernameClaim', 'preferred_username');
  await check(page, '#adminOidcForm [name="auto_create_users"]', autoCreate);
  await check(page, '#adminOidcForm [name="allow_member_password_login"]', allowMemberPassword);
  await click(page, '#adminOidcSubmit');
  await waitFor(page, 'document.querySelector("#adminOidcForm").getAttribute("aria-busy") === "false"', 'OIDC settings response');
  const saveResult = await evaluate(page, `(() => {
    const message = document.querySelector('#adminOidcMessage');
    return { className: message.className, text: message.textContent };
  })()`);
  assert.ok(saveResult.className.includes('is-success'), `OIDC settings save failed: ${saveResult.text}`);
  const settings = await jsonFetch(page, '/api/admin/oidc/settings');
  assert.equal(settings.status, 200);
  assert.equal(settings.body.settings.enabled, true);
  assert.equal(settings.body.settings.auto_create_users, autoCreate);
  assert.equal(settings.body.settings.allow_member_password_login, allowMemberPassword);
}

async function createExistingMember(page) {
  await click(page, '#adminSectionUsersTab');
  await fill(page, '#adminUserForm [name="username"]', 'reader');
  await fill(page, '#adminUserForm [name="password"]', 'reader-secret');
  await fill(page, '#adminUserForm [name="role"]', 'member');
  await click(page, '#adminUserSubmit');
  await waitFor(page, 'document.querySelector("#adminUserList").textContent.includes("reader")', 'existing member creation');
}

async function clickUserAction(page, username, key) {
  const clicked = await evaluate(page, `(() => {
    const item = Array.from(document.querySelectorAll('#adminUserList .account-user-item'))
      .find(node => node.querySelector('.account-user-name')?.textContent === ${JSON.stringify(username)});
    if (!item) return false;
    const details = item.querySelector('details');
    if (details) details.open = true;
    const button = item.querySelector('button[data-i18n=${JSON.stringify(key)}]');
    if (!button || button.disabled) return false;
    button.click();
    return true;
  })()`);
  assert.equal(clicked, true, `missing ${key} action for ${username}`);
}

async function waitForUser(page, username, present = true) {
  const expression = `Array.from(document.querySelectorAll('#adminUserList .account-user-name')).some(node => node.textContent === ${JSON.stringify(username)})`;
  await waitFor(page, present ? expression : `!(${expression})`, `${username} user ${present ? 'presence' : 'removal'}`);
}

async function closeAdminAndLogout(page) {
  await click(page, '#adminClose');
  await waitFor(page, '!document.querySelector("#adminPanel").classList.contains("active")', 'administration close');
  await logout(page);
}

fs.mkdirSync(artifactDir, { recursive: true });
const runtime = await launchBrowser();
let callbackURL = '';
runtime.page.on('Network.requestWillBeSent', event => {
  if (event.request?.url?.startsWith(`${baseURL}/auth/oidc/callback?`)) callbackURL = event.request.url;
});

try {
  const page = runtime.page;

  await localLogin(page, 'owner', 'owner-secret');
  await click(page, '#adminMenu');
  await waitFor(page, 'document.querySelector("#adminPanel").classList.contains("active")', 'administration panel');
  await createExistingMember(page);
  await click(page, '#adminClose');
  await waitFor(page, '!document.querySelector("#adminPanel").classList.contains("active")', 'administration close');

  await configureOidc(page, { autoCreate: false, allowMemberPassword: true });
  await screenshot(page, 'admin-oidc-desktop.png');
  await setViewport(page, 720, 900);
  await assertNoPageOverflow(page, 'OIDC administration at 200% equivalent width');
  await setViewport(page, 375, 812, { dark: true, reducedMotion: true });
  await assertNoPageOverflow(page, 'OIDC administration mobile');
  await screenshot(page, 'admin-oidc-mobile-dark.png');
  await setViewport(page, 1440, 1000);
  await closeAdminAndLogout(page);
  assert.equal(await evaluate(page, 'Boolean(document.querySelector("#oidcLoginAction"))'), true);

  await runtime.page.send('Network.clearBrowserCookies');
  await navigate(page, `${baseURL}/login?lang=zh-CN`);
  await waitFor(page, 'document.querySelector("#oidcLoginAction").textContent.trim() === "使用 Company SSO 继续"', 'localized OIDC action');
  await waitFor(page, 'document.querySelector("#oidcLoginAction strong")?.textContent === "Company SSO"', 'emphasized OIDC provider');
  await screenshot(page, 'login-oidc-zh-CN-desktop.png');
  await click(page, '#oidcLoginAction');
  await loginAtAuthelia(page, 'reader', 'reader-secret');
  await waitFor(page, 'location.pathname === "/auth/oidc/associate"', 'account association');
  await waitFor(page, 'document.querySelector(".auth-card")', 'account association card');
  const associationCardWidth = await evaluate(page, 'document.querySelector(".auth-card").getBoundingClientRect().width');
  assert.ok(associationCardWidth <= 500, `association card is wider than the login measure: ${associationCardWidth}`);
  await screenshot(page, 'oidc-association-desktop.png');
  await assertAssociationKeyboardPath(page);
  await setViewport(page, 375, 812, { dark: true, reducedMotion: true });
  await assertNoPageOverflow(page, 'OIDC association mobile');
  const associationTargets = await evaluate(page, `Array.from(document.querySelectorAll('#associationForm input:not([type="hidden"]), #associationForm button')).map(node => node.getBoundingClientRect().height)`);
  assert.ok(associationTargets.every(height => height >= 44), `association touch target below 44px: ${associationTargets}`);
  await screenshot(page, 'oidc-association-mobile-dark.png');
  await setViewport(page, 1440, 1000);
  await fill(page, '#associationForm [name="username"]', 'reader');
  await fill(page, '#associationForm [name="password"]', 'reader-secret');
  await click(page, '#associationForm button[type="submit"]');
  await waitFor(page, 'location.hostname === "127.0.0.1" && location.port === "18443" && location.pathname !== "/auth/oidc/associate"', 'associated member session');
  const readerSession = await jsonFetch(page, '/api/session');
  assert.equal(readerSession.body.user.username, 'reader');
  assert.equal(readerSession.body.oidc.linked, true);
  assert.ok(callbackURL, 'real callback URL was not observed');

  await navigate(page, callbackURL);
  await waitFor(page, `Boolean(document.querySelector('h1[data-i18n="account.oidc.errorTitle"]'))`, 'safe replay error');
  assert.equal((await evaluate(page, 'document.body.textContent')).includes('insecure_secret'), false);
  await navigate(page, `${baseURL}/`);
  await click(page, '#accountMenu');
  await waitFor(page, 'document.querySelector("#accountOidcList").textContent.includes("Company SSO")', 'linked identity display');
  const oidcCardGeometry = await evaluate(page, `(() => {
    const card = document.querySelector('#accountOidcCard').getBoundingClientRect();
    const button = document.querySelector('#accountOidcUnlink').getBoundingClientRect();
    return { height: card.height, buttonHeight: button.height };
  })()`);
  assert.ok(oidcCardGeometry.height <= 300, `OIDC account card is too sparse: ${JSON.stringify(oidcCardGeometry)}`);
  assert.ok(oidcCardGeometry.buttonHeight >= 44, `OIDC account action is below 44px: ${JSON.stringify(oidcCardGeometry)}`);
  await screenshot(page, 'account-identity-desktop.png');
  await setViewport(page, 375, 812, { dark: true, reducedMotion: true });
  await assertNoPageOverflow(page, 'OIDC account identity mobile');
  await screenshot(page, 'account-identity-mobile-dark.png');
  await setViewport(page, 1440, 1000);
  await click(page, '#accountLogout');
  await waitFor(page, 'location.pathname === "/login" && Boolean(document.querySelector("#loginForm"))', 'reader logout');

  await runtime.page.send('Network.clearBrowserCookies');
  await localLogin(page, 'owner', 'owner-secret');
  await configureOidc(page, { autoCreate: true, allowMemberPassword: false });
  await closeAdminAndLogout(page);

  await runtime.page.send('Network.clearBrowserCookies');
  await navigate(page, `${baseURL}/login`);
  await click(page, '#oidcLoginAction');
  await loginAtAuthelia(page, 'newcomer', 'new-reader-secret');
  await waitFor(page, 'location.hostname === "127.0.0.1" && location.port === "18443" && location.pathname !== "/login"', 'automatic member provisioning');
  const newcomerSession = await jsonFetch(page, '/api/session');
  assert.equal(newcomerSession.body.user.username, 'newcomer');
  assert.equal(newcomerSession.body.user.role, 'member');
  assert.equal(newcomerSession.body.oidc.linked, true);
  const unlink = await jsonFetch(page, '/api/account/oidc/identity', {
    method: 'DELETE',
    headers: { 'X-CSRF-Token': newcomerSession.body.csrf_token },
  });
  assert.equal(unlink.status, 409, 'passwordless member must not unlink its only login method');
  await logout(page);

  await runtime.page.send('Network.clearBrowserCookies');
  await localLogin(page, 'reader', 'reader-secret', false);
  await runtime.page.send('Network.clearBrowserCookies');
  await localLogin(page, 'owner', 'owner-secret');

  const adminSession = await jsonFetch(page, '/api/session');
  const emptyUser = await jsonFetch(page, '/api/admin/users', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': adminSession.body.csrf_token },
    body: JSON.stringify({ username: 'empty-delete', password: 'empty-secret', role: 'member' }),
  });
  assert.equal(emptyUser.status, 201);
  await click(page, '#adminMenu');
  await waitFor(page, 'document.querySelector("#adminPanel").classList.contains("active")', 'administration panel for user deletion');
  await click(page, '#adminSectionUsersTab');
  await waitForUser(page, 'empty-delete');
  await clickUserAction(page, 'empty-delete', 'admin.deleteUser');
  await waitFor(page, 'Boolean(document.querySelector(".app-dialog-confirm"))', 'empty user confirmation');
  assert.equal(await evaluate(page, 'Boolean(document.querySelector(".app-dialog-input"))'), false);
  await click(page, '.app-dialog-confirm');
  await waitForUser(page, 'empty-delete', false);

  await clickUserAction(page, 'reader', 'admin.deleteUser');
  await waitFor(page, 'Boolean(document.querySelector(".app-dialog-input"))', 'associated user typed confirmation');
  const deletionDialog = await evaluate(page, `(() => ({
    detailCount: document.querySelectorAll('.app-dialog-details li').length,
    confirmDisabled: document.querySelector('.app-dialog-confirm').disabled,
    inputHeight: document.querySelector('.app-dialog-input').getBoundingClientRect().height,
    cancelHeight: document.querySelector('.app-dialog-cancel').getBoundingClientRect().height,
    confirmHeight: document.querySelector('.app-dialog-confirm').getBoundingClientRect().height
  }))()`);
  assert.ok(deletionDialog.detailCount >= 1, `associated data was not listed: ${JSON.stringify(deletionDialog)}`);
  assert.equal(deletionDialog.confirmDisabled, true);
  assert.ok(
    deletionDialog.inputHeight >= 44 && deletionDialog.cancelHeight >= 44 && deletionDialog.confirmHeight >= 44,
    `deletion dialog touch targets are too small: ${JSON.stringify(deletionDialog)}`
  );
  await fill(page, '.app-dialog-input', 'Reader');
  assert.equal(await evaluate(page, 'document.querySelector(".app-dialog-confirm").disabled'), true);
  await fill(page, '.app-dialog-input', 'reader');
  assert.equal(await evaluate(page, 'document.querySelector(".app-dialog-confirm").disabled'), false);
  await screenshot(page, 'admin-user-delete-associated.png');
  await click(page, '.app-dialog-confirm');
  await waitForUser(page, 'reader', false);
  assert.equal((await jsonFetch(page, '/api/admin/users')).body.users.some(user => user.username === 'reader'), false);

  const disabled = await jsonFetch(page, '/api/admin/oidc/settings', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': adminSession.body.csrf_token },
    body: JSON.stringify({
      enabled: false,
      provider_name: 'Company SSO',
      issuer_url: 'https://127.0.0.1:18444',
      client_id: 'epub-browser-e2e',
      redirect_uri: `${baseURL}/auth/oidc/callback`,
      scopes: ['openid', 'profile', 'email'],
      username_claim: 'preferred_username',
      auto_create_users: true,
      allow_member_password_login: false,
    }),
  });
  assert.equal(disabled.status, 200);
  await navigate(page, `${baseURL}/auth/oidc/callback?state=tampered&code=redacted-test-code`);
  await waitFor(page, `Boolean(document.querySelector('h1[data-i18n="account.oidc.errorTitle"]'))`, 'disabled callback recovery');
  assert.equal((await evaluate(page, 'document.body.textContent')).includes('redacted-test-code'), false);

  console.log('OIDC browser journey passed');
} finally {
  await runtime.close();
}
