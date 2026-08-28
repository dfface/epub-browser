'use strict';

const assert = require('node:assert');
const fs = require('node:fs');
const http = require('node:http');
const os = require('node:os');
const path = require('node:path');
const { spawn } = require('node:child_process');
const { test } = require('node:test');

const projectRoot = path.join(__dirname, '..');
const vendorScript = fs.readFileSync(
  path.join(projectRoot, 'epub_browser', 'assets', 'vendor', 'glightbox', 'glightbox.min.js')
);
const adapterScript = fs.readFileSync(
  path.join(projectRoot, 'epub_browser', 'assets', 'lightbox-adapter.js')
);
const vendorStyles = fs.readFileSync(
  path.join(projectRoot, 'epub_browser', 'assets', 'vendor', 'glightbox', 'glightbox.min.css')
);
const transparentPng = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=',
  'base64'
);

function chromiumCandidates() {
  const candidates = [
    process.env.EPUB_BROWSER_CHROMIUM,
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    '/Applications/Chromium.app/Contents/MacOS/Chromium',
    '/usr/bin/chromium',
    '/usr/bin/chromium-browser',
    '/usr/bin/google-chrome',
  ].filter(Boolean);
  const playwrightCache = path.join(os.homedir(), 'Library', 'Caches', 'ms-playwright');
  if (fs.existsSync(playwrightCache)) {
    for (const directory of fs.readdirSync(playwrightCache).sort().reverse()) {
      if (!directory.startsWith('chromium_headless_shell-')) continue;
      candidates.push(
        path.join(playwrightCache, directory, 'chrome-mac', 'headless_shell'),
        path.join(playwrightCache, directory, 'chrome-headless-shell-mac-arm64', 'chrome-headless-shell'),
        path.join(playwrightCache, directory, 'chrome-headless-shell-mac-x64', 'chrome-headless-shell')
      );
    }
  }
  return candidates.find((candidate) => fs.existsSync(candidate)) || null;
}

function fixtureHTML() {
  const hostile = [
    'data-fancybox="&lt;script&gt;legacyXss=true&lt;/script&gt;"',
    'data-gallery="attacker-gallery"',
    'data-glightbox="type: video; href: https://evil.invalid/movie.mp4"',
    'data-href="https://evil.invalid/external.html"',
    'data-content="&lt;script&gt;inlineXss=true&lt;/script&gt;"',
    'data-title="&lt;img src=x onerror=titleXss=true&gt;"',
    'data-description="&lt;img src=x onerror=descriptionXss=true&gt;"',
    'data-type="video"',
    'data-video-provider="youtube"',
    'alt="&lt;img src=x onerror=captionXss=true&gt;"',
  ].join(' ');
  return `<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <base href="/attacker-controlled/">
  <link rel="stylesheet" href="/assets/glightbox.min.css">
  <script src="/assets/glightbox.min.js" defer></script>
  <script src="/assets/lightbox-adapter.js" defer></script>
</head>
<body>
  <main id="eb-content">
    <img id="first" src="resources/one.png" ${hostile}>
    <img id="second" src="resources/two.png" ${hostile}>
  </main>
  <script>
  window.__LIGHTBOX_RESULT__ = null;
  window.addEventListener('load', function () {
    function delay(milliseconds) {
      return new Promise(function (resolve) { setTimeout(resolve, milliseconds); });
    }
    function waitFor(predicate, label) {
      var deadline = Date.now() + 5000;
      return new Promise(function (resolve, reject) {
        function poll() {
          if (predicate()) return resolve();
          if (Date.now() >= deadline) return reject(new Error('Timed out: ' + label));
          setTimeout(poll, 20);
        }
        poll();
      });
    }
    function currentImage() {
      return document.querySelector('.glightbox-container .gslide.current img');
    }
    function close(instance) {
      instance.close();
      return waitFor(function () {
        return !document.querySelector('.glightbox-container');
      }, 'GLightbox close');
    }
    function hostileImage(id, source) {
      var image = document.createElement('img');
      image.id = id;
      image.setAttribute('src', source);
      image.setAttribute('data-type', 'video');
      image.setAttribute('data-href', 'https://evil.invalid/' + id + '.mp4');
      image.setAttribute('data-content', '<script>dynamicInlineXss=true<\\/script>');
      image.setAttribute('data-title', '<img src=x onerror=dynamicTitleXss=true>');
      image.setAttribute('data-description', '<img src=x onerror=descriptionXss=true>');
      image.setAttribute('alt', '<img src=x onerror=dynamicCaptionXss=true>');
      return image;
    }
    (async function () {
      var content = document.getElementById('eb-content');
      var first = document.getElementById('first');
      var second = document.getElementById('second');
      var instance = Fancybox.bind('#eb-content img', {
        openEffect: 'none', closeEffect: 'none', slideEffect: 'none',
        preload: false, touchNavigation: false
      });

      second.click();
      await waitFor(currentImage, 'second image open');
      var initialIndex = instance.getActiveSlideIndex();
      var initialSource = currentImage().src;

      var third = hostileImage('third', 'resources/three.png');
      content.appendChild(third);
      Fancybox.bind('#eb-content img', {});
      await delay(80);
      var openRebindIndex = instance.getActiveSlideIndex();
      var openRebindSource = currentImage().src;

      await close(instance);
      third.click();
      await waitFor(currentImage, 'third image open');
      var appendedIndex = instance.getActiveSlideIndex();
      var appendedSource = currentImage().src;
      await close(instance);

      first.remove();
      Fancybox.bind('#eb-content img', {});
      second.click();
      await waitFor(currentImage, 'pruned second image open');
      var prunedIndex = instance.getActiveSlideIndex();
      var prunedSource = currentImage().src;
      await close(instance);

      third.click();
      await waitFor(currentImage, 'third image reopen');
      Fancybox.destroy();
      Fancybox.bind('#eb-content img', {});
      await waitFor(function () {
        return !document.querySelector('.glightbox-container');
      }, 'destroy close');
      await delay(80);
      var restarted = Fancybox.bind('#eb-content img', {});
      third.click();
      await waitFor(currentImage, 'third image after restart');
      var restartedIndex = restarted.getActiveSlideIndex();
      var restartedSource = currentImage().src;
      var modalCount = document.querySelectorAll('.glightbox-container').length;
      var hostileMarkup = document.querySelector('.glightbox-container').innerHTML;

      window.__LIGHTBOX_RESULT__ = {
        baseURI: document.baseURI,
        initialIndex: initialIndex,
        initialSource: initialSource,
        openRebindIndex: openRebindIndex,
        openRebindSource: openRebindSource,
        appendedIndex: appendedIndex,
        appendedSource: appendedSource,
        prunedIndex: prunedIndex,
        prunedSource: prunedSource,
        restartedIndex: restartedIndex,
        restartedSource: restartedSource,
        modalCount: modalCount,
        hasVideo: !!document.querySelector('.glightbox-container video'),
        hasIframe: !!document.querySelector('.glightbox-container iframe'),
        hasHostileMarkup: /evil\.invalid|onerror|inlineXss|titleXss|captionXss/.test(hostileMarkup),
        xssFlags: !!(
          window.legacyXss || window.inlineXss || window.titleXss ||
          window.captionXss || window.descriptionXss || window.dynamicInlineXss ||
          window.dynamicTitleXss || window.dynamicCaptionXss
        )
      };
    })().catch(function (error) {
      window.__LIGHTBOX_RESULT__ = { error: error.stack || String(error) };
    });
  });
  </script>
</body>
</html>`;
}

function listen(server) {
  return new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(0, '127.0.0.1', () => resolve(server.address().port));
  });
}

function closeServer(server) {
  return new Promise((resolve) => server.close(resolve));
}

function reservePort() {
  const server = http.createServer();
  return listen(server).then((port) => closeServer(server).then(() => port));
}

function fetchJSON(url) {
  return new Promise((resolve, reject) => {
    const request = http.get(url, (response) => {
      let body = '';
      response.setEncoding('utf8');
      response.on('data', (chunk) => { body += chunk; });
      response.on('end', () => {
        try {
          resolve(JSON.parse(body));
        } catch (error) {
          reject(error);
        }
      });
    });
    request.on('error', reject);
  });
}

async function waitForDebugger(port) {
  const deadline = Date.now() + 5000;
  while (Date.now() < deadline) {
    try {
      const targets = await fetchJSON(`http://127.0.0.1:${port}/json/list`);
      const page = targets.find((target) => target.type === 'page');
      if (page) return page.webSocketDebuggerUrl;
    } catch (error) {
      // Chromium has not opened its debugging socket yet.
    }
    await new Promise((resolve) => setTimeout(resolve, 50));
  }
  throw new Error('Chromium debugging endpoint did not start');
}

function connectCDP(webSocketURL) {
  return new Promise((resolve, reject) => {
    const socket = new WebSocket(webSocketURL);
    const pending = new Map();
    const listeners = [];
    let nextID = 1;
    socket.addEventListener('error', reject, { once: true });
    socket.addEventListener('open', () => {
      resolve({
        onEvent(callback) {
          listeners.push(callback);
        },
        send(method, params = {}) {
          const id = nextID++;
          socket.send(JSON.stringify({ id, method, params }));
          return new Promise((resolveCommand, rejectCommand) => {
            pending.set(id, { resolve: resolveCommand, reject: rejectCommand });
          });
        },
        close() {
          socket.close();
        },
      });
    }, { once: true });
    socket.addEventListener('message', (event) => {
      const message = JSON.parse(event.data);
      if (message.id) {
        const command = pending.get(message.id);
        if (!command) return;
        pending.delete(message.id);
        if (message.error) command.reject(new Error(message.error.message));
        else command.resolve(message.result);
        return;
      }
      for (const listener of listeners) listener(message);
    });
  });
}

async function evaluate(client, expression) {
  const response = await client.send('Runtime.evaluate', {
    expression,
    awaitPromise: true,
    returnByValue: true,
  });
  if (response.exceptionDetails) {
    throw new Error(response.exceptionDetails.text || 'Browser evaluation failed');
  }
  return response.result.value;
}

async function waitForResult(client) {
  const deadline = Date.now() + 12000;
  while (Date.now() < deadline) {
    const result = await evaluate(client, 'window.__LIGHTBOX_RESULT__ || null');
    if (result) return result;
    await new Promise((resolve) => setTimeout(resolve, 50));
  }
  throw new Error('Browser lightbox scenario timed out');
}

const chromium = chromiumCandidates();

test('actual GLightbox bundle keeps hostile EPUB DOM inert across reader rebinding', {
  skip: chromium ? false : 'set EPUB_BROWSER_CHROMIUM to run the real-browser lightbox smoke test',
  timeout: 20000,
}, async () => {
  const localRequests = [];
  const server = http.createServer((request, response) => {
    localRequests.push(request.url);
    if (request.url === '/book/demo/chapter_0.html') {
      response.writeHead(200, { 'content-type': 'text/html; charset=utf-8' });
      response.end(fixtureHTML());
      return;
    }
    if (request.url === '/assets/glightbox.min.js') {
      response.writeHead(200, { 'content-type': 'text/javascript' });
      response.end(vendorScript);
      return;
    }
    if (request.url === '/assets/lightbox-adapter.js') {
      response.writeHead(200, { 'content-type': 'text/javascript' });
      response.end(adapterScript);
      return;
    }
    if (request.url === '/assets/glightbox.min.css') {
      response.writeHead(200, { 'content-type': 'text/css' });
      response.end(vendorStyles);
      return;
    }
    if (request.url.endsWith('.png')) {
      response.writeHead(200, { 'content-type': 'image/png' });
      response.end(transparentPng);
      return;
    }
    response.writeHead(404);
    response.end('not found');
  });

  const port = await listen(server);
  const debugPort = await reservePort();
  const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'epub-browser-lightbox-'));
  const browser = spawn(chromium, [
    '--headless',
    '--no-sandbox',
    '--disable-gpu',
    '--disable-background-networking',
    '--disable-component-update',
    '--disable-default-apps',
    '--no-first-run',
    `--remote-debugging-port=${debugPort}`,
    '--remote-allow-origins=*',
    `--user-data-dir=${profile}`,
    'about:blank',
  ], { stdio: ['ignore', 'ignore', 'pipe'] });
  let browserStderr = '';
  browser.stderr.setEncoding('utf8');
  browser.stderr.on('data', (chunk) => { browserStderr += chunk; });

  let client;
  try {
    let webSocketURL;
    try {
      webSocketURL = await waitForDebugger(debugPort);
    } catch (error) {
      throw new Error(`${error.message}\n${browserStderr}`);
    }
    client = await connectCDP(webSocketURL);
    const networkRequests = [];
    const browserErrors = [];
    client.onEvent((message) => {
      if (message.method === 'Network.requestWillBeSent') {
        networkRequests.push(message.params.request.url);
      }
      if (message.method === 'Runtime.exceptionThrown') {
        browserErrors.push(message.params.exceptionDetails.text);
      }
    });
    await client.send('Network.enable');
    await client.send('Runtime.enable');
    await client.send('Page.enable');
    await client.send('Page.navigate', {
      url: `http://127.0.0.1:${port}/book/demo/chapter_0.html`,
    });

    const result = await waitForResult(client);
    assert.ok(!result.error, result.error);
    assert.strictEqual(result.baseURI, `http://127.0.0.1:${port}/attacker-controlled/`);
    assert.strictEqual(result.initialIndex, 1);
    assert.strictEqual(result.openRebindIndex, 1);
    assert.strictEqual(result.initialSource, `http://127.0.0.1:${port}/book/demo/resources/two.png`);
    assert.strictEqual(result.openRebindSource, result.initialSource);
    assert.strictEqual(result.appendedIndex, 2);
    assert.strictEqual(result.appendedSource, `http://127.0.0.1:${port}/book/demo/resources/three.png`);
    assert.strictEqual(result.prunedIndex, 0);
    assert.strictEqual(result.prunedSource, result.initialSource);
    assert.strictEqual(result.restartedIndex, 1);
    assert.strictEqual(result.restartedSource, result.appendedSource);
    assert.strictEqual(result.modalCount, 1);
    assert.strictEqual(result.hasVideo, false);
    assert.strictEqual(result.hasIframe, false);
    assert.strictEqual(result.hasHostileMarkup, false);
    assert.strictEqual(result.xssFlags, false);
    assert.deepStrictEqual(browserErrors, []);

    const externalRequests = networkRequests.filter((url) => {
      return /^https?:/.test(url) && !url.startsWith(`http://127.0.0.1:${port}/`);
    });
    assert.deepStrictEqual(externalRequests, []);
    assert.ok(!networkRequests.some((url) => /cdn\.plyr\.io|evil\.invalid/.test(url)));
    assert.ok(localRequests.includes('/book/demo/resources/two.png'));
    assert.ok(localRequests.includes('/book/demo/resources/three.png'));
  } finally {
    if (client) client.close();
    if (browser.exitCode === null) {
      const exited = new Promise((resolve) => browser.once('exit', resolve));
      browser.kill('SIGTERM');
      await Promise.race([
        exited,
        new Promise((resolve) => setTimeout(resolve, 2000)),
      ]);
    }
    await closeServer(server);
    fs.rmSync(profile, { recursive: true, force: true, maxRetries: 5, retryDelay: 100 });
  }
});
