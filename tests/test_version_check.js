const test = require('node:test');
const assert = require('node:assert/strict');
const VersionCheck = require('../epub_browser/assets/version-check.js');

function footerFixture(currentVersion) {
  const link = {
    href: '',
    textContent: '',
    setAttribute(name, value) {
      this[name] = value;
    },
  };
  const update = {
    hidden: true,
    querySelector(selector) {
      return selector === 'a' ? link : null;
    },
  };
  const footer = {
    getAttribute(name) {
      if (name === 'data-current-version') return currentVersion;
      if (name === 'data-release-api') {
        return 'https://api.github.com/repos/dfface/epub-browser/releases/latest';
      }
      return null;
    },
    querySelector(selector) {
      return selector === '[data-version-update]' ? update : null;
    },
  };
  return { footer, update, link };
}

function documentFixture(footer) {
  return {
    querySelectorAll(selector) {
      assert.equal(selector, '[data-version-check]');
      return [footer];
    },
  };
}

test('shows a newer stable GitHub release in the footer with localized link text', () => {
  assert.equal(typeof VersionCheck.check, 'function');
  const fixture = footerFixture('1.11.9');
  let requestedUrl = '';

  VersionCheck.check(documentFixture(fixture.footer), (url, done) => {
    requestedUrl = url;
    done({
      tag_name: 'v1.11.10',
      html_url: 'https://github.com/dfface/epub-browser/releases/tag/v1.11.10',
      draft: false,
      prerelease: false,
    });
  }, {
    t(key, params) {
      assert.equal(key, 'version.updateAvailable');
      return '\u53ef\u7528\u66f4\u65b0\uff1av' + params.version;
    },
  });

  assert.equal(requestedUrl, 'https://api.github.com/repos/dfface/epub-browser/releases/latest');
  assert.equal(fixture.update.hidden, false);
  assert.equal(fixture.link.textContent, '\u53ef\u7528\u66f4\u65b0\uff1av1.11.10');
  assert.equal(fixture.link.href, 'https://github.com/dfface/epub-browser/releases/tag/v1.11.10');
});

test('keeps the footer quiet when the GitHub release is not newer', () => {
  const fixture = footerFixture('1.11.0');

  VersionCheck.check(documentFixture(fixture.footer), (url, done) => {
    done({
      tag_name: 'v1.11.0',
      html_url: 'https://github.com/dfface/epub-browser/releases/tag/v1.11.0',
      draft: false,
      prerelease: false,
    });
  });

  assert.equal(fixture.update.hidden, true);
  assert.equal(fixture.link.textContent, '');
  assert.equal(fixture.link.href, '');
});

test('reuses a recent successful GitHub release response across pages', () => {
  const release = {
    tag_name: 'v1.12.0',
    html_url: 'https://github.com/dfface/epub-browser/releases/tag/v1.12.0',
    draft: false,
    prerelease: false,
  };
  const values = new Map();
  const storage = {
    getItem(key) {
      return values.has(key) ? values.get(key) : null;
    },
    setItem(key, value) {
      values.set(key, value);
    },
  };
  let requestCount = 0;

  function FakeXMLHttpRequest() {
    requestCount += 1;
    this.readyState = 0;
    this.status = 0;
    this.responseText = '';
  }
  FakeXMLHttpRequest.prototype.open = function() {};
  FakeXMLHttpRequest.prototype.setRequestHeader = function() {};
  FakeXMLHttpRequest.prototype.send = function() {
    this.readyState = 4;
    this.status = 200;
    this.responseText = JSON.stringify(release);
    this.onreadystatechange();
  };

  const options = {
    storage,
    XMLHttpRequest: FakeXMLHttpRequest,
    now: () => 123456789,
  };
  let firstResult;
  let secondResult;
  const url = 'https://api.github.com/repos/dfface/epub-browser/releases/latest';

  VersionCheck.requestRelease(url, result => { firstResult = result; }, options);
  VersionCheck.requestRelease(url, result => { secondResult = result; }, options);

  assert.deepEqual(firstResult, release);
  assert.deepEqual(secondResult, release);
  assert.equal(requestCount, 1);
});
