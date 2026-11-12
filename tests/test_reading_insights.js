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
    removeAttribute(name) { delete this.attributes[name]; },
    getAttribute(name) { return this.attributes[name] || null; },
    addEventListener(type, fn) { (listeners[type] || (listeners[type] = [])).push(fn); },
    click() { (listeners.click || []).forEach(fn => fn()); },
  };
}

function clientFor(payload, translations, fetchPayload) {
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
        const result = fetchPayload ? fetchPayload(url) : url.includes('/sessions?')
          ? { sessions: payload.sessions || [] } : { insights: payload };
        return Promise.resolve({ ok: !!result, json: () => Promise.resolve(result) });
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
    top_book: { book_id: 'book-id', title: 'Book', active_seconds: 1860 },
    days: [{ date: '2026-08-15', active_seconds: 1860 }],
    sessions: [{ started_at: '2026-08-15T08:18:00+00:00', book_id: 'book-id', chapter_index: 5, book_title: 'Book', chapter_label: 'Chapter 6', active_seconds: 1860 }],
  });
  await page.mount();
  assert.equal(page.requests.length, 1);
  await page.setPeriod('week', '2026-08-15');
  await page.selectDay('2026-08-14');
  await page.selectDay('2026-08-15');
  assert.match(page.requests.at(-1), /reading-insights\/sessions\?date=2026-08-15/);
  assert.equal(page.sessionRows[0].getAttribute('aria-label'), '08:18 Book Chapter 6 31 min');
  assert.match(page.sessionRows[0].children.at(-1).className, /is-focused/);
  assert.equal(page.sessionRows[0].children[1].children[0].tagName, 'button');
  assert.equal(page.sessionRows[0].children[1].children[1].getAttribute('href'), '/book/book-id/chapter_5.html');
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
  await page.setPeriod('day', '2026-08-15');
  assert.equal(page.sessionRows[0].getAttribute('aria-label'), '08:18 书 第一章 1 小时 1 分钟');
  assert.match(page.sessionRows[0].children.at(-1).className, /is-deep/);
});

test('the activity calendar opens a day and trend titles describe their period and metric', async () => {
  const page = clientFor({
    total_active_seconds: 3661,
    books_read_count: 2,
    trend: { granularity: 'month', points: [{ bucket: '2026-07', book_count: 2 }, { bucket: '2026-08', book_count: 2 }] },
    days: [{ date: '2026-08-15', active_seconds: 3661 }],
    activity: {
      days: [
        { date: '2026-08-10', active_seconds: 1, book_count: 1 },
        { date: '2026-08-11', active_seconds: 299, book_count: 1 },
        { date: '2026-08-12', active_seconds: 300, book_count: 1 },
        { date: '2026-08-13', active_seconds: 1199, book_count: 1 },
        { date: '2026-08-14', active_seconds: 1200, book_count: 1 },
        { date: '2026-08-15', active_seconds: 3600, book_count: 2 },
      ],
    },
    sessions: [],
  });
  await page.mount();

  assert.match(page.activityCells[0].className, /is-level-1/);
  assert.match(page.activityCells[1].className, /is-level-1/);
  assert.match(page.activityCells[2].className, /is-level-2/);
  assert.match(page.activityCells[3].className, /is-level-2/);
  assert.match(page.activityCells[4].className, /is-level-3/);
  assert.match(page.activityCells[5].className, /is-level-4/);
  assert.equal(page.activityCells[5].getAttribute('aria-label'), 'Sat, Aug 15, 2026: 1 hr. Books read: 2');
  assert.equal(page.activityCells.filter(cell => cell.getAttribute('tabindex') === '0').length, 1);
  const analytics = page.root.children.find(child => child.className === 'reading-insights-analytics');
  const [calendar, trend] = analytics.children[0].children;
  assert.equal(calendar.children.some(child => child.tagName === 'input'), false);
  assert.equal(calendar.children[1].textContent, 'Select a square to view that day’s reading activity.');
  assert.equal(trend.children[0].textContent, 'Monthly reading time');

  page.metricButtons[1].click();
  assert.equal(trend.children[0].textContent, 'Books read per month');
  assert.equal(trend.children.at(-1).textContent, 'Total books read: 2');
  assert.equal(page.metricButtons[0].getAttribute('aria-pressed'), 'false');
  assert.equal(page.metricButtons[1].getAttribute('aria-pressed'), 'true');

  page.activityCells[5].click();
  assert.match(page.requests.at(-1), /period=day&anchor=2026-08-15/);
  await page.setPeriod('week', '2026-08-15');
  page.metricButtons[0].click();
  assert.equal(trend.children[0].textContent, 'Daily reading time');
  page.metricButtons[1].click();
  assert.equal(trend.children[0].textContent, 'Books read per day');
  await page.setPeriod('month', '2026-08-15');
  assert.equal(trend.children[0].textContent, 'Books read per day');
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
  assert.match(page.requests.at(-2), /period=week&anchor=2026-08-08/);
  await page.nextRange();
  assert.match(page.requests.at(-2), /period=week&anchor=2026-08-15/);
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
  const analytics = page.root.children.find(child => child.className === 'reading-insights-analytics');
  const dates = page.root.children.find(child => child.className === 'reading-insights-days');
  assert.equal(analytics.hidden, false);
  assert.equal(dates.hidden, true);

  await page.setPeriod('month', '2026-08-15');
  assert.equal(analytics.hidden, false);
  assert.equal(analytics.children[0].children[0].hidden, true);
});

test('all periods keep the same report card order', async () => {
  const page = clientFor({
    total_active_seconds: 90,
    books: [
      { book_id: 'one', title: 'First book', active_seconds: 60 },
      { book_id: 'two', title: 'Second book', active_seconds: 30 },
    ],
  });
  await page.mount();
  const cardNames = ['summary', 'rank', 'analytics', 'days'];
  for (const period of ['overview', 'day', 'week', 'month', 'overview']) {
    await page.setPeriod(period, '2026-08-15');
    const visibleCards = page.root.children
      .filter(card => !card.hidden)
      .map(card => cardNames.find(name => card.className.split(' ').includes('reading-insights-' + name)))
      .filter(Boolean);
    assert.deepEqual(visibleCards, period === 'overview' ? cardNames.slice(0, 3) : cardNames, period);
  }
});

test('week and month use compact visual day labels while preserving full dates for assistive technology', async () => {
  const page = clientFor({ total_active_seconds: 0, days: [{ date: '2026-08-15', active_seconds: 0 }], sessions: [] });
  await page.mount();
  await page.setPeriod('week', '2026-08-15');
  const dayList = page.root.children.find(child => child.className === 'reading-insights-days').children[1];
  const button = dayList.children[0];
  assert.equal(button.children[0].textContent, 'Sat');
  assert.equal(button.children[1].textContent, '15');
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
  let dayList = page.root.children.find(child => child.className === 'reading-insights-days').children[1];
  assert.equal(dayList.children[0].getAttribute('aria-pressed'), 'true');
  assert.equal(dayList.children[1].getAttribute('aria-pressed'), 'false');

  await page.setPeriod('month', todayIso);
  dayList = page.root.children.find(child => child.className === 'reading-insights-days').children[1];
  assert.equal(dayList.children.filter(child => child.className === 'reading-insights-weekday').length, 7);
  const todayButton = dayList.children.find(child => child.getAttribute('data-date') === todayIso);
  assert.equal(todayButton.getAttribute('aria-pressed'), 'true');
});


test('opening a ranked book fetches its report and returning keeps the same time range', async () => {
  const page = clientFor({}, {}, url => ({
    insights: url.startsWith('/api/books/')
      ? { title: 'Book', active_seconds: 15, annotation_count: 2 }
      : { books: [{ book_id: 'book', title: 'Book', active_seconds: 15 }] },
  }));
  await page.mount();
  await page.setPeriod('overview', '2025-08-15');
  const rank = page.root.children.find(child => child.className.includes('reading-insights-rank'));
  const row = rank.children[1].children[0].children[0];
  assert.deepEqual(row.children.slice(0, 3).map(cell => cell.textContent), ['1', 'Book', '15 sec']);
  row.click();
  assert.equal(page.requests.at(-1), '/api/books/book/insights');
  await new Promise(resolve => setImmediate(resolve));
  const heading = page.root.children[0];
  assert.equal(heading.children[0].children[0].textContent, 'Book reading stats');
  assert.equal(heading.children[0].children[1].textContent, 'Book');
  const bookLink = heading.children.find(child => child.tagName === 'a');
  assert.equal(bookLink.textContent, 'Open book home');
  assert.equal(bookLink.getAttribute('href'), '/book/book/index.html');
  assert.equal(bookLink.hidden, false);
  assert.equal(page.root.children[2].children[0].children[1].children[1].textContent, '2');
  const back = heading.children.find(child => child.tagName === 'button');
  assert.equal(back.textContent, 'Back to reading insights');
  back.click();
  assert.equal(page.rangeLabel.textContent, '2025-01-01–2025-12-31');
  assert.equal(page.requests.length, 3);
});

test('overview displays a visible error and retries the same request', async () => {
  let attempts = 0;
  const page = clientFor({}, {}, () => ++attempts === 1 ? null : { insights: { total_active_seconds: 1 } });
  await page.mount();
  const status = page.root.children[2];
  assert.equal(status.children[0].getAttribute('role'), 'status');
  assert.match(status.children[0].textContent, /Unable to load/);
  assert.equal(status.children[1].hidden, false);
  status.children[1].click();
  assert.match(status.children[0].textContent, /Loading/);
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(status.children[1].hidden, true);
  assert.equal(page.requests[0], page.requests[1]);
});
