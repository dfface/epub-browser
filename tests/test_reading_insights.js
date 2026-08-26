const test = require('node:test');
const assert = require('node:assert/strict');
const Insights = require('../epub_browser/assets/reading-insights.js');

function element(tagName) {
  const listeners = {};
  return {
    tagName, children: [], attributes: {}, className: '', textContent: '', hidden: false,
    appendChild(node) { this.children.push(node); node.parentNode = this; return node; },
    replaceChildren(...nodes) { this.children = []; nodes.forEach(node => this.appendChild(node)); },
    setAttribute(name, value) { this.attributes[name] = String(value); },
    getAttribute(name) { return this.attributes[name] || null; },
    addEventListener(type, fn) { (listeners[type] || (listeners[type] = [])).push(fn); },
    click() { (listeners.click || []).forEach(fn => fn()); },
  };
}

function clientFor(payload) {
  const root = element('main');
  const browser = {
    document: { createElement: element, querySelector: () => root },
    EpubBrowserI18n: { t(key) { return key; }, getLocale() { return 'en'; } },
    Intl: {
      DateTimeFormat() { return { resolvedOptions() { return { timeZone: 'UTC' }; }, format() { return '08:18'; } }; },
      NumberFormat() { return { format(value) { return String(value); } }; },
    },
    EpubBrowserAuth: { fetch() { return Promise.resolve({ ok: true, json: () => Promise.resolve({ insights: payload }) }); } },
  };
  return Insights.create(browser);
}

test('selecting a day fetches and safely renders chronological sessions', async () => {
  const page = clientFor({
    total_active_seconds: 1860,
    top_book: { title: 'Book', active_seconds: 1860 },
    days: [{ date: '2026-08-15', active_seconds: 1860 }],
    sessions: [{ started_at: '2026-08-15T08:18:00+00:00', book_title: 'Book', chapter_label: 'Chapter 6', active_seconds: 1860 }],
  });
  await page.mount();
  await page.selectDay('2026-08-15');
  assert.equal(page.sessionRows[0].textContent, '08:18 Book Chapter 6 31 min');
});
