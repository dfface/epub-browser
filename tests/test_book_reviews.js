const test = require('node:test');
const assert = require('node:assert/strict');
const Reviews = require('../epub_browser/assets/book-reviews.js');

function makeElement(tagName) {
  const listeners = {};
  return {
    tagName,
    children: [],
    attributes: {},
    className: '',
    textContent: '',
    value: '',
    checked: false,
    disabled: false,
    parentNode: null,
    appendChild(node) { node.parentNode = this; this.children.push(node); return node; },
    replaceChildren(...nodes) { this.children = []; nodes.forEach(node => this.appendChild(node)); },
    setAttribute(name, value) { this.attributes[name] = String(value); },
    getAttribute(name) { return this.attributes[name] || null; },
    addEventListener(type, handler) { (listeners[type] || (listeners[type] = [])).push(handler); },
    dispatch(type) { (listeners[type] || []).forEach(handler => handler({ preventDefault() {} })); },
  };
}

function loadReviewClient(initial, failSave) {
  const root = makeElement('section');
  const requests = [];
  const browser = {
    document: {
      createElement: makeElement,
      querySelector(selector) { return selector === '[data-book-reviews]' ? root : null; },
    },
    EpubBrowserI18n: { t(key) { return key; } },
    EpubBrowserAuth: {
      fetch(url, options) {
        requests.push({ url, method: options.method, body: options.body && JSON.parse(options.body) });
        if (failSave && options.method === 'PUT') return Promise.resolve({ ok: false, json: () => Promise.resolve({}) });
        const review = options.method === 'GET' ? initial.review : { rating: 5, review_text: 'Excellent' };
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ review }) });
      },
    },
    confirm() { return true; },
  };
  const client = Reviews.create(browser);
  client.requests = requests;
  return client;
}

test('review editor loads, saves, and deletes only the current book review', async () => {
  const client = loadReviewClient({ review: { rating: 4, review_text: 'Useful' } });
  await client.mount('book-id');
  assert.equal(client.rating.value, '4');
  assert.equal(client.ratingOptions[3].checked, true);
  await client.save(5, 'Excellent');
  assert.deepEqual(client.requests.at(-1).body, { rating: 5, review_text: 'Excellent' });
  assert.equal(client.requests.at(-1).url, '/api/book-reviews/book-id');
  await client.deleteReview();
  assert.equal(client.requests.at(-1).method, 'DELETE');
  assert.equal(client.requests.at(-1).url, '/api/book-reviews/book-id');
});

test('review editor restores saved fields after a failed write', async () => {
  const client = loadReviewClient({ review: { rating: 4, review_text: 'Useful' } }, true);
  await client.mount('book-id');
  await client.save(5, 'Changed');
  assert.equal(client.rating.value, '4');
  assert.equal(client.reviewText.value, 'Useful');
});
