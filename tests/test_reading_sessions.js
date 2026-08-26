const test = require('node:test');
const assert = require('node:assert/strict');
const Sessions = require('../epub_browser/assets/reading-sessions.js');

test('counts only active, visible, focused reading after a qualifying interaction', () => {
  let clock = 0;
  const sent = [];
  const tracker = Sessions.createTracker({ now: () => clock, send: item => sent.push(item), idleMs: 60000, heartbeatMs: 15000 });
  tracker.setChapter(2, 'Chapter 3');
  tracker.recordInteraction();
  clock += 15000;
  tracker.flush();
  assert.deepEqual(sent[0], { chapter_index: 2, active_seconds: 15, client_sequence: 1 });
  tracker.setVisible(false);
  clock += 15000;
  tracker.flush();
  assert.equal(sent.length, 1);
});

test('idle timeout keeps the failed sequence ahead of later active time', async () => {
  let clock = 0;
  const sent = [];
  const tracker = Sessions.createTracker({ now: () => clock, send: item => { sent.push(item); return Promise.reject(new Error('offline')); }, idleMs: 60000, heartbeatMs: 15000 });
  tracker.setChapter(2, 'Chapter 3'); tracker.recordInteraction(); clock = 15000;
  await tracker.flush();
  clock = 76000; tracker.flush();
  tracker.setChapter(3, 'Chapter 4'); tracker.recordInteraction(); clock = 91000;
  await tracker.flush();
  assert.deepEqual(sent.map(item => item.client_sequence), [1, 1, 1]);
  assert.equal(sent[2].chapter_index, 2);
});

function createFakeChannel() {
  const channels = [];
  return {
    open() {
      const channel = {
        onmessage: null,
        closed: false,
        postMessage(message) {
          channels.forEach(peer => {
            if (!peer.closed && peer.onmessage) peer.onmessage({ data: message });
          });
        },
        close() { this.closed = true; },
      };
      channels.push(channel);
      return channel;
    },
  };
}

test('only the elected focused tab emits a heartbeat', () => {
  const channel = createFakeChannel();
  const first = Sessions.createTracker({ channel, clientId: 'tab-a', now: () => 0, send() {} });
  const second = Sessions.createTracker({ channel, clientId: 'tab-b', now: () => 0, send() {} });
  first.setFocused(true); second.setFocused(true);
  assert.equal(first.isLeader(), false);
  assert.equal(second.isLeader(), true);
  first.destroy();
  second.destroy();
});

test('a client sequence continues after acknowledged payloads and tracker recreation', () => {
  let clock = 0;
  const storage = createStorage();
  const firstSent = [];
  const first = Sessions.createTracker({
    now: () => clock,
    sessionStorage: storage,
    clientId: 'persistent-tab',
    send: item => firstSent.push(item),
  });
  first.setChapter(1, 'One');
  first.recordInteraction();
  clock = 15000;
  first.flush();
  first.destroy();

  const secondSent = [];
  const second = Sessions.createTracker({
    now: () => clock,
    sessionStorage: storage,
    clientId: 'persistent-tab',
    send: item => secondSent.push(item),
  });
  second.setChapter(1, 'One');
  second.recordInteraction();
  clock = 30000;
  second.flush();
  assert.equal(firstSent[0].client_sequence, 1);
  assert.equal(secondSent[0].client_sequence, 2);
  second.destroy();
});

test('a failed heartbeat retries before a later sequence is transmitted', async () => {
  let clock = 0;
  let rejectFirst;
  const sent = [];
  const tracker = Sessions.createTracker({
    now: () => clock,
    send: item => {
      sent.push(item);
      if (sent.length === 1) return new Promise((resolve, reject) => { rejectFirst = reject; });
      return new Promise(() => {});
    },
  });
  tracker.setChapter(1, 'One');
  tracker.recordInteraction();
  clock = 15000;
  const firstRequest = tracker.flush();
  tracker.setChapter(2, 'Two');
  tracker.recordInteraction();
  clock = 30000;
  tracker.flush();
  rejectFirst(new Error('offline'));
  await firstRequest;
  assert.deepEqual(sent.map(item => item.client_sequence), [1, 1]);
  tracker.destroy();
});

test('local storage fallback elects one initial leader across separate tabs', () => {
  const localStorage = createStorage();
  const firstTarget = createEventTarget();
  const secondTarget = createEventTarget();
  const first = Sessions.createTracker({
    now: () => 0,
    sessionStorage: createStorage(),
    localStorage,
    eventTarget: firstTarget,
    clientId: 'fallback-a',
    send() {},
  });
  const second = Sessions.createTracker({
    now: () => 0,
    sessionStorage: createStorage(),
    localStorage,
    eventTarget: secondTarget,
    clientId: 'fallback-b',
    send() {},
  });
  assert.equal(first.isLeader(), true);
  assert.equal(second.isLeader(), false);
  second.setFocused(true);
  firstTarget.dispatch('storage', {
    key: 'epub-reading-sessions:active-tab',
    newValue: localStorage.getItem('epub-reading-sessions:active-tab'),
  });
  assert.equal(first.isLeader(), false);
  assert.equal(second.isLeader(), true);
  first.destroy();
  second.destroy();
});

test('a background server reader never flushes a restored queue before election', async () => {
  const sessionStorage = createStorage();
  const localStorage = createStorage();
  const clientId = 'background-tab';
  sessionStorage.setItem('epub-reading-sessions:' + clientId, JSON.stringify([
    { chapter_index: 1, active_seconds: 15, client_sequence: 1 },
  ]));
  const content = {
    getAttribute(name) {
      return { 'data-book-hash': 'book', 'data-chapter-index': '1', 'data-chapter-title': 'One' }[name] || null;
    },
  };
  const target = createEventTarget();
  const sent = [];
  const root = Object.assign(target, {
    EpubBrowserMode: 'server',
    EpubBrowserAuth: { fetch: (url, options) => { sent.push({ url, options }); return Promise.resolve({ ok: true }); } },
    sessionStorage,
    localStorage,
    document: { getElementById: () => content, hasFocus: () => false },
  });
  const tracker = Sessions.start({ root, eventTarget: target, clientId, now: () => 0, schedule() {} });
  await tracker.flush();
  assert.equal(tracker.isLeader(), false);
  assert.equal(sent.length, 0);
  tracker.destroy();
});

test('a focused follower claims a removed local storage lease and flushes its queue', () => {
  let clock = 0;
  const clientId = 'follower-after-removal';
  const sessionStorage = createStorage();
  const localStorage = createStorage();
  const target = createEventTarget();
  const sent = [];
  sessionStorage.setItem('epub-reading-sessions:' + clientId, JSON.stringify([
    { chapter_index: 1, active_seconds: 15, client_sequence: 1 },
  ]));
  localStorage.setItem('epub-reading-sessions:active-tab', JSON.stringify({
    type: 'epub-reading-session-active', clientId: 'other-tab', focused: true, expiresAt: 30000,
  }));
  const tracker = Sessions.createTracker({
    now: () => clock,
    sessionStorage,
    localStorage,
    eventTarget: target,
    clientId,
    send: item => sent.push(item),
  });
  assert.equal(tracker.isLeader(), false);
  localStorage.removeItem('epub-reading-sessions:active-tab');
  target.dispatch('storage', { key: 'epub-reading-sessions:active-tab', newValue: null });
  tracker.flush();
  assert.equal(tracker.isLeader(), true);
  assert.deepEqual(sent, [{ chapter_index: 1, active_seconds: 15, client_sequence: 1 }]);
  tracker.destroy();
});

test('a focused follower claims an expired lease before flushing', () => {
  let clock = 0;
  const clientId = 'follower-after-expiry';
  const sessionStorage = createStorage();
  const localStorage = createStorage();
  const sent = [];
  sessionStorage.setItem('epub-reading-sessions:' + clientId, JSON.stringify([
    { chapter_index: 2, active_seconds: 15, client_sequence: 1 },
  ]));
  localStorage.setItem('epub-reading-sessions:active-tab', JSON.stringify({
    type: 'epub-reading-session-active', clientId: 'other-tab', focused: true, expiresAt: 100,
  }));
  const tracker = Sessions.createTracker({
    now: () => clock,
    sessionStorage,
    localStorage,
    clientId,
    send: item => sent.push(item),
  });
  assert.equal(tracker.isLeader(), false);
  clock = 101;
  tracker.flush();
  assert.equal(tracker.isLeader(), true);
  assert.deepEqual(sent, [{ chapter_index: 2, active_seconds: 15, client_sequence: 1 }]);
  tracker.destroy();
});

test('becoming visible or focused requires a fresh interaction before timing resumes', () => {
  let clock = 0;
  const sent = [];
  const tracker = Sessions.createTracker({ now: () => clock, send: item => sent.push(item) });
  tracker.setChapter(1, 'One');
  tracker.recordInteraction();
  clock = 10000;
  tracker.setVisible(false);
  tracker.setVisible(true);
  clock = 20000;
  tracker.flush();
  assert.deepEqual(sent.map(item => item.active_seconds), [10]);
  tracker.recordInteraction();
  clock = 35000;
  tracker.flush();
  assert.deepEqual(sent.map(item => item.active_seconds), [10, 15]);
  tracker.setFocused(false);
  tracker.setFocused(true);
  clock = 50000;
  tracker.flush();
  assert.equal(sent.length, 2);
});

test('pagehide sends the current bounded increment with keepalive', () => {
  let clock = 0;
  const sent = [];
  const target = createEventTarget();
  const tracker = Sessions.createTracker({
    now: () => clock,
    eventTarget: target,
    send: (item, keepalive) => sent.push({ item, keepalive }),
  });
  tracker.setChapter(4, 'Five');
  tracker.recordInteraction();
  clock = 12000;
  target.dispatch('pagehide');
  assert.deepEqual(sent, [{ item: { chapter_index: 4, active_seconds: 12, client_sequence: 1 }, keepalive: true }]);
});

test('heartbeat payloads cap a long active interval at twenty seconds', () => {
  let clock = 0;
  const sent = [];
  const tracker = Sessions.createTracker({ now: () => clock, send: item => sent.push(item) });
  tracker.setChapter(1, 'One');
  tracker.recordInteraction();
  clock = 55000;
  tracker.flush();
  assert.equal(sent[0].active_seconds, 20);
  tracker.flush();
  assert.equal(sent[1].active_seconds, 20);
  tracker.flush();
  assert.equal(sent[2].active_seconds, 15);
});

test('accrues reading through the idle cutoff before stopping', () => {
  let clock = 0;
  const sent = [];
  const tracker = Sessions.createTracker({ now: () => clock, idleMs: 60000, send: item => sent.push(item) });
  tracker.setChapter(1, 'One');
  tracker.recordInteraction();
  clock = 75000;
  tracker.flush();
  tracker.flush();
  tracker.flush();
  assert.deepEqual(sent.map(item => item.active_seconds), [20, 20, 20]);
  tracker.destroy();
});

test('pagehide repeats an in-flight payload with keepalive without awaiting it', () => {
  let clock = 0;
  const target = createEventTarget();
  const sent = [];
  const tracker = Sessions.createTracker({
    now: () => clock,
    eventTarget: target,
    send: (item, keepalive) => {
      sent.push({ item, keepalive });
      return new Promise(() => {});
    },
  });
  tracker.setChapter(4, 'Five');
  tracker.recordInteraction();
  clock = 12000;
  tracker.flush();
  target.dispatch('pagehide');
  assert.deepEqual(sent, [
    { item: { chapter_index: 4, active_seconds: 12, client_sequence: 1 }, keepalive: false },
    { item: { chapter_index: 4, active_seconds: 12, client_sequence: 1 }, keepalive: true },
  ]);
  tracker.destroy();
});

test('browser transport starts only for an authenticated server reader and adds its client id', async () => {
  const content = {
    getAttribute(name) {
      return { 'data-book-hash': 'book id', 'data-chapter-index': '6', 'data-chapter-title': 'Seven' }[name] || null;
    },
  };
  const eventTarget = createEventTarget();
  const storage = createStorage();
  let clock = 0;
  const calls = [];
  const root = Object.assign(eventTarget, {
    EpubBrowserMode: 'server',
    EpubBrowserAuth: {
      fetch(url, options) {
        calls.push({ url, options });
        return Promise.resolve({ ok: true });
      },
    },
    sessionStorage: storage,
    document: { getElementById: () => content, hasFocus: () => true },
  });
  assert.equal(Sessions.start({ root: Object.assign({}, root, { EpubBrowserMode: 'ssg' }) }), null);
  const tracker = Sessions.start({ root, eventTarget, now: () => clock, schedule() {} });
  tracker.recordInteraction();
  clock = 15000;
  await tracker.flush(true);
  assert.equal(calls[0].url, '/api/reading-sessions/book%20id/heartbeat');
  assert.equal(calls[0].options.keepalive, true);
  const body = JSON.parse(calls[0].options.body);
  assert.equal(body.chapter_index, 6);
  assert.equal(body.active_seconds, 15);
  assert.match(body.client_id, /^reading-/);
  tracker.destroy();
});

test('offline payload storage retains four unacknowledged heartbeats and retries their sequence', async () => {
  let clock = 0;
  const sent = [];
  const storage = createStorage();
  const tracker = Sessions.createTracker({
    now: () => clock,
    idleMs: 200000,
    sessionStorage: storage,
    clientId: 'offline-tab',
    send: item => { sent.push(item); return Promise.reject(new Error('offline')); },
  });
  tracker.setChapter(1, 'One');
  tracker.recordInteraction();
  for (let index = 0; index < 5; index += 1) {
    clock += 21000;
    await tracker.flush();
  }
  assert.equal(tracker.pendingCount(), 4);
  assert.equal(JSON.parse(storage.getItem('epub-reading-sessions:offline-tab')).length, 4);
  assert.equal(sent[0].client_sequence, 1);
  assert.equal(sent[1].client_sequence, 1);
});

test('destroy clears heartbeat timers, browser listeners, and the coordination channel', () => {
  const channel = createFakeChannel();
  const target = createEventTarget();
  const scheduled = [];
  const tracker = Sessions.createTracker({
    channel,
    eventTarget: target,
    schedule(callback) { scheduled.push(callback); return callback; },
    cancel(callback) { const index = scheduled.indexOf(callback); if (index >= 0) scheduled.splice(index, 1); },
    send() {},
  });
  tracker.setChapter(1, 'One');
  assert.ok(scheduled.length > 0);
  assert.ok(target.listenerCount() > 0);
  tracker.destroy();
  assert.equal(scheduled.length, 0);
  assert.equal(target.listenerCount(), 0);
});

function createStorage() {
  const values = new Map();
  return {
    getItem(key) { return values.has(key) ? values.get(key) : null; },
    setItem(key, value) { values.set(key, String(value)); },
    removeItem(key) { values.delete(key); },
  };
}

function createEventTarget() {
  const listeners = new Map();
  return {
    addEventListener(type, handler) {
      const handlers = listeners.get(type) || [];
      handlers.push(handler);
      listeners.set(type, handlers);
    },
    removeEventListener(type, handler) {
      const handlers = listeners.get(type) || [];
      listeners.set(type, handlers.filter(item => item !== handler));
    },
    listenerCount() {
      let total = 0;
      listeners.forEach(handlers => { total += handlers.length; });
      return total;
    },
    dispatch(type, event) {
      (listeners.get(type) || []).slice().forEach(handler => handler(event || {}));
    },
  };
}
