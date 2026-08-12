const test = require('node:test');
const assert = require('node:assert/strict');
const Progress = require('../epub_browser/assets/reading-progress.js');

test('continuous reading selects the chapter containing the viewport midpoint', () => {
  assert.equal(Progress.activeChapter([
    { index: 2, top: -300, bottom: 100 },
    { index: 3, top: 100, bottom: 900 },
  ], 400), 3);
});

test('continuous reading falls back to the nearest chapter outside all bounds', () => {
  assert.equal(Progress.activeChapter([
    { index: 2, top: -300, bottom: -100 },
    { index: 3, top: 80, bottom: 400 },
  ], 0), 3);
});

test('chapter reporter debounces changed chapters and retries failed reports', async () => {
  const reports = [];
  let fail = true;
  const reporter = new Progress.ChapterReporter(index => {
    reports.push(index);
    return Promise.resolve(fail ? null : { chapter_index: index });
  }, 1);

  reporter.select(2);
  reporter.select(3);
  reporter.flush();
  await new Promise(resolve => setTimeout(resolve, 0));
  fail = false;
  reporter.select(3);
  reporter.flush();
  await new Promise(resolve => setTimeout(resolve, 0));

  assert.deepEqual(reports, [3, 3]);
});

test('progress-bar preference defaults to visible and hides only its fixed container', () => {
  assert.equal(Progress.showProgressBar(null), true);
  assert.equal(Progress.progressBarClass(false), 'is-progress-bar-hidden');
});

test('reading progress requests persist only a chapter index', async () => {
  const originalFetch = global.fetch;
  let received;
  global.fetch = (url, options) => {
    received = { url, options };
    return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ chapter_index: 5 }) });
  };

  const result = await Progress.request('PUT', '/api/reading-progress/book', 5, true);
  global.fetch = originalFetch;

  assert.deepEqual(result, { chapter_index: 5 });
  assert.equal(received.url, '/api/reading-progress/book');
  assert.equal(received.options.keepalive, true);
  assert.deepEqual(JSON.parse(received.options.body), { chapter_index: 5 });
});
