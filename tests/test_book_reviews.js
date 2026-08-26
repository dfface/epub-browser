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
    removeAttribute(name) { delete this.attributes[name]; },
    addEventListener(type, handler) { (listeners[type] || (listeners[type] = [])).push(handler); },
    dispatch(type) { (listeners[type] || []).forEach(handler => handler({ preventDefault() {} })); },
    focus() { this.focused = true; },
  };
}

function loadReviewClient(initial, failSave) {
  const root = makeElement('section');
  const dialog = makeElement('section');
  const requests = [];
  const localeListeners = [];
  const browser = {
    document: {
      createElement: makeElement,
      querySelector(selector) {
        if (selector === '[data-book-reviews]') return root;
        if (selector === '[data-book-review-modal] .book-review-dialog') return dialog;
        return null;
      },
    },
    EpubBrowserI18n: {
      t(key) { return key; },
      onLocaleChange(listener) { localeListeners.push(listener); return () => localeListeners.splice(localeListeners.indexOf(listener), 1); },
    },
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
  client.localeListeners = localeListeners;
  client.dialog = dialog;
  return client;
}

test('review editor loads, saves, and deletes only the current book review', async () => {
  const client = loadReviewClient({ review: { rating: 4, review_text: 'Useful' } });
  await client.mount('book-id');
  assert.equal(client.rating.value, '4');
  assert.equal(client.ratingOptions[3].getAttribute('aria-checked'), 'true');
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

test('a missing rating preserves typed review text and announces the field-specific error without a request', async () => {
  const client = loadReviewClient({ review: { rating: 4, review_text: 'Useful' } });
  await client.mount('book-id');
  client.rating.value = '';
  client.ratingOptions.forEach(option => { option.setAttribute('aria-checked', 'false'); });
  client.reviewText.value = 'Keep this draft';

  await client.save('', client.reviewText.value);

  assert.equal(client.requests.length, 1);
  assert.equal(client.reviewText.value, 'Keep this draft');
  assert.equal(client.ratingError.textContent, 'bookReviews.ratingRequired');
  assert.equal(client.ratingError.hidden, false);
  assert.equal(client.ratingField.getAttribute('aria-invalid'), 'true');
  assert.equal(client.ratingOptions[0].focused, true);
});

test('a review write disables every visible rating choice until the request finishes', async () => {
  const root = makeElement('section');
  let resolveWrite;
  const browser = {
    document: {
      createElement: makeElement,
      querySelector() { return root; },
    },
    EpubBrowserI18n: { t(key) { return key; } },
    EpubBrowserAuth: {
      fetch(_url, options) {
        if (options.method === 'GET') return Promise.resolve({ ok: true, json: () => Promise.resolve({ review: null }) });
        return new Promise(resolve => { resolveWrite = () => resolve({ ok: true, json: () => Promise.resolve({ review: { rating: 5, review_text: 'Done' } }) }); });
      },
    },
  };
  const client = Reviews.create(browser);
  await client.mount('book-id');

  const writing = client.save(5, 'Done');
  assert.equal(client.rating.disabled, true);
  assert.equal(client.reviewText.disabled, true);
  assert.ok(client.ratingOptions.every(option => option.disabled));

  resolveWrite();
  await writing;
  assert.equal(client.rating.disabled, false);
  assert.ok(client.ratingOptions.every(option => !option.disabled));
});

test('rating stars are native buttons and update the selected value on click', async () => {
  const client = loadReviewClient({ review: null });
  await client.mount('book-id');

  assert.ok(client.ratingOptions.every(option => option.tagName === 'button'));
  client.ratingOptions[2].dispatch('click');
  assert.equal(client.rating.value, '3');
  assert.equal(client.ratingOptions[2].getAttribute('aria-checked'), 'true');
  assert.equal(client.ratingOptions[0].className.includes('is-filled'), true);
});

test('delete remains unavailable until a review record has been loaded', async () => {
  const client = loadReviewClient({ review: null });
  await client.mount('book-id');
  assert.equal(client.deleteButton.hidden, true);
});

test('review display and editor copy refresh when the active locale changes', async () => {
  const client = loadReviewClient({ review: { rating: 4, review_text: 'Useful' } });
  const display = makeElement('section');
  await client.mount('book-id', display);

  client.localeListeners[0]();

  assert.equal(display.children[0].children[0].textContent, 'bookReviews.title');
  assert.equal(display.children.length, 3);
  assert.ok(display.children.every(child => child.className !== 'book-review-display-private'));
  assert.equal(client.deleteButton.textContent, 'bookReviews.delete');
  assert.equal(client.ratingOptions[3].getAttribute('aria-label'), 'bookReviews.ratingValue');
  assert.equal(client.dialog.getAttribute('aria-label'), 'bookReviews.write');
});
