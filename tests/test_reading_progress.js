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

test('a failed older report does not replace a newer chapter selection', async () => {
  const reports = [];
  let finishFirst;
  const reporter = new Progress.ChapterReporter(index => {
    reports.push(index);
    if (index === 2) return new Promise(resolve => { finishFirst = resolve; });
    return Promise.resolve({ chapter_index: index });
  }, 1);

  reporter.select(2);
  const first = reporter.flush();
  reporter.select(3);
  finishFirst(null);
  await first;
  await reporter.flush();

  assert.deepEqual(reports, [2, 3]);
  assert.equal(reporter.reported, 3);
});

test('reselecting an already reported chapter is not overwritten by an older failure', async () => {
  const reports = [];
  let finishOld;
  const reporter = new Progress.ChapterReporter(index => {
    reports.push(index);
    if (index === 2) return new Promise(resolve => { finishOld = resolve; });
    return Promise.resolve({ chapter_index: index });
  }, 1);
  reporter.reported = 3;

  reporter.select(2);
  const oldRequest = reporter.flush();
  reporter.select(3);
  finishOld(null);
  await oldRequest;
  await reporter.flush();

  assert.equal(reporter.pending, undefined);
  assert.equal(reporter.reported, 3);
  assert.deepEqual(reports, [2, 3]);
});

test('a stale successful report is followed by the latest selected chapter', async () => {
  const reports = [];
  let finishOld;
  const reporter = new Progress.ChapterReporter(index => {
    reports.push(index);
    if (index === 2) return new Promise(resolve => { finishOld = resolve; });
    return Promise.resolve({ chapter_index: index });
  }, 1);
  reporter.reported = 3;

  reporter.select(2);
  const oldRequest = reporter.flush();
  reporter.select(3);
  finishOld({ chapter_index: 2 });
  await oldRequest;
  await reporter.flush();

  assert.deepEqual(reports, [2, 3]);
  assert.equal(reporter.reported, 3);
});

test('pagehide keeps the pending latest chapter unload-safe after an in-flight request', async () => {
  const reports = [];
  let finishOld;
  const reporter = new Progress.ChapterReporter((index, keepalive) => {
    reports.push({ index, keepalive });
    if (index === 2) return new Promise(resolve => { finishOld = resolve; });
    return Promise.resolve({ chapter_index: index });
  }, 1);

  reporter.select(2);
  const oldRequest = reporter.flush();
  reporter.select(3);
  reporter.flush(true);
  finishOld({ chapter_index: 2 });
  await oldRequest;
  await new Promise(resolve => setTimeout(resolve, 0));

  assert.deepEqual(reports, [{ index: 2, keepalive: undefined }, { index: 3, keepalive: true }]);
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
