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

function clientFor(payload, translations) {
  const root = element('main');
  const requests = [];
  const browser = {
    document: { createElement: element, querySelector: () => root },
    EpubBrowserI18n: { t(key) { return translations && translations[key] || key; }, getLocale() { return translations && translations.locale || 'en'; } },
    Intl: {
      DateTimeFormat(_locale, options = {}) {
        return {
          resolvedOptions() { return { timeZone: 'UTC' }; },
          format(value) {
            if (options.hour) return '08:18';
            if (options.weekday && !options.day) return 'Sat';
            if (options.weekday) return 'Sat, Aug 15, 2026';
            if (options.day && options.month && !options.year) return '8/15';
            return new Date(value).toISOString().slice(0, 10);
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
  page.root = root;
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
  assert.equal(page.sessionRows[0].getAttribute('aria-label'), '08:18 Book Chapter 6 31 min');
  assert.match(page.sessionRows[0].children.at(-1).className, /is-focused/);
});

test('duration fallback uses the active locale unit copy when DurationFormat is unavailable', async () => {
  const page = clientFor({
    total_active_seconds: 3661,
    top_book: { title: '书', active_seconds: 3661 },
    days: [{ date: '2026-08-15', active_seconds: 3661 }],
    sessions: [{ started_at: '2026-08-15T08:18:00+00:00', book_title: '书', chapter_label: '第一章', active_seconds: 3661 }],
  }, {
    locale: 'zh-CN',
    'readingInsights.duration.second': '秒',
    'readingInsights.duration.minute': '分钟',
    'readingInsights.duration.hour': '小时',
  });
  await page.mount();
  assert.equal(page.sessionRows[0].getAttribute('aria-label'), '08:18 书 第一章 1 小时 1 分钟');
  assert.match(page.sessionRows[0].children.at(-1).className, /is-deep/);
});

test('renders a theme-token-ready activity calendar and switches its daily trend metric', async () => {
  const page = clientFor({
    total_active_seconds: 3661,
    days: [{ date: '2026-08-15', active_seconds: 3661 }],
    activity: {
      days: [
        { date: '2026-08-10', active_seconds: 1, book_count: 1 },
        { date: '2026-08-11', active_seconds: 60, book_count: 1 },
        { date: '2026-08-12', active_seconds: 3600, book_count: 2 },
      ],
    },
    sessions: [],
  });
  await page.mount();

  assert.match(page.activityCells[0].className, /is-level-1/);
  assert.match(page.activityCells[1].className, /is-level-2/);
  assert.match(page.activityCells[2].className, /is-level-4/);
  assert.equal(page.activityCells[2].getAttribute('aria-label'), 'Sat, Aug 15, 2026: 1 hr. Books read: 2');
  page.metricButtons[1].click();
  assert.equal(page.metricButtons[0].getAttribute('aria-pressed'), 'false');
  assert.equal(page.metricButtons[1].getAttribute('aria-pressed'), 'true');
});

test('opens on the annual overview and activating a period updates its pressed state before requesting the new range', async () => {
  const page = clientFor({ total_active_seconds: 0, days: [], sessions: [] });
  await page.mount();
  const overview = page.periodButtons.find(button => button.getAttribute('data-reading-insights-period') === 'overview');
  const day = page.periodButtons.find(button => button.getAttribute('data-reading-insights-period') === 'day');
  const week = page.periodButtons.find(button => button.getAttribute('data-reading-insights-period') === 'week');

  assert.equal(overview.getAttribute('aria-pressed'), 'true');
  assert.equal(day.getAttribute('aria-pressed'), 'false');
  assert.match(page.requests[0], /period=overview/);
  week.click();

  assert.equal(overview.getAttribute('aria-pressed'), 'false');
  assert.equal(week.getAttribute('aria-pressed'), 'true');
  await Promise.resolve();
  assert.match(page.requests.at(-1), /period=week/);
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

test('overview range covers a complete natural year and hides range-specific drills', async () => {
  const page = clientFor({ total_active_seconds: 0, days: [], sessions: [] });
  await page.mount();
  await page.setPeriod('overview', '2026-08-15');
  assert.equal(page.rangeLabel.textContent, '2026-01-01–2026-12-31');
  assert.equal(page.root.children[4].hidden, false);
  assert.equal(page.root.children[5].hidden, true);
  assert.equal(page.root.children[6].hidden, true);

  await page.setPeriod('month', '2026-08-15');
  assert.equal(page.root.children[4].hidden, true);
});

test('week and month use compact visual day labels while preserving full dates for assistive technology', async () => {
  const page = clientFor({ total_active_seconds: 0, days: [{ date: '2026-08-15', active_seconds: 0 }], sessions: [] });
  await page.mount();
  await page.setPeriod('week', '2026-08-15');
  const dayList = page.root.children[5].children[1];
  const button = dayList.children[0];
  assert.equal(button.children[0].textContent, 'Sat');
  assert.equal(button.children[1].textContent, '8/15');
  assert.equal(button.getAttribute('aria-label'), 'Sat, Aug 15, 2026: 0 sec');
});

test('week and month prefer today over the range end when today is visible', async () => {
  const today = new Date();
  const todayIso = [today.getFullYear(), String(today.getMonth() + 1).padStart(2, '0'), String(today.getDate()).padStart(2, '0')].join('-');
  const tomorrow = new Date(today.getFullYear(), today.getMonth(), today.getDate() + 1);
  const tomorrowIso = [tomorrow.getFullYear(), String(tomorrow.getMonth() + 1).padStart(2, '0'), String(tomorrow.getDate()).padStart(2, '0')].join('-');
  const page = clientFor({
    total_active_seconds: 0,
    days: [{ date: todayIso, active_seconds: 0 }, { date: tomorrowIso, active_seconds: 0 }],
    sessions: [],
  });

  await page.mount();
  await page.setPeriod('week', todayIso);
  let dayList = page.root.children[5].children[1];
  assert.equal(dayList.children[0].getAttribute('aria-pressed'), 'true');
  assert.equal(dayList.children[1].getAttribute('aria-pressed'), 'false');

  await page.setPeriod('month', todayIso);
  dayList = page.root.children[5].children[1];
  assert.equal(dayList.children[0].getAttribute('aria-pressed'), 'true');
});
