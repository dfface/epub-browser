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
  const requests = [];
  const browser = {
    document: { createElement: element, querySelector: () => root },
    EpubBrowserI18n: { t(key) { return key; }, getLocale() { return 'en'; } },
    Intl: {
      DateTimeFormat(_locale, options = {}) {
        return {
          resolvedOptions() { return { timeZone: 'UTC' }; },
          format(value) {
            return options.hour ? '08:18' : new Date(value).toISOString().slice(0, 10);
          },
          formatRange(start, end) {
            return new Date(start).toISOString().slice(0, 10) + '–' + new Date(end).toISOString().slice(0, 10);
          },
        };
      },
      NumberFormat() { return { format(value) { return String(value); } }; },
    },
    EpubBrowserAuth: {
      fetch(url) {
        requests.push(url);
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ insights: payload }) });
      },
    },
  };
  const page = Insights.create(browser);
  page.requests = requests;
  return page;
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

test('activating a period updates its pressed state before requesting the new range', async () => {
  const page = clientFor({ total_active_seconds: 0, days: [], sessions: [] });
  await page.mount();
  const day = page.periodButtons.find(button => button.getAttribute('data-reading-insights-period') === 'day');
  const week = page.periodButtons.find(button => button.getAttribute('data-reading-insights-period') === 'week');

  day.click();

  assert.equal(day.getAttribute('aria-pressed'), 'true');
  assert.equal(week.getAttribute('aria-pressed'), 'false');
  await Promise.resolve();
  assert.match(page.requests.at(-1), /period=day/);
});

test('previous and next range controls preserve period and shift the API anchor', async () => {
  const page = clientFor({ total_active_seconds: 0, days: [], sessions: [] });
  await page.mount();
  await page.setPeriod('week', '2026-08-15');
  await page.previousRange();
  assert.match(page.requests.at(-1), /period=week&anchor=2026-08-08/);
  await page.nextRange();
  assert.match(page.requests.at(-1), /period=week&anchor=2026-08-15/);
  assert.equal(page.rangeButtons.previous.getAttribute('aria-label'), 'Previous range');
  assert.equal(page.rangeButtons.next.getAttribute('aria-label'), 'Next range');
});

test('range label reflects the same day, week, and month bounds as the API', async () => {
  const page = clientFor({ total_active_seconds: 0, days: [], sessions: [] });
  await page.mount();
  await page.setPeriod('day', '2026-08-15');
  assert.equal(page.rangeLabel.textContent, '2026-08-15');
  await page.setPeriod('week', '2026-08-15');
  assert.equal(page.rangeLabel.textContent, '2026-08-10–2026-08-16');
  await page.setPeriod('month', '2026-02-15');
  assert.equal(page.rangeLabel.textContent, '2026-02-01–2026-02-28');
});
