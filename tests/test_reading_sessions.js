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

test('idle timeout, chapter change, and retried sequence never double count', async () => {
  let clock = 0;
  const sent = [];
  const tracker = Sessions.createTracker({ now: () => clock, send: item => { sent.push(item); return Promise.reject(new Error('offline')); }, idleMs: 60000, heartbeatMs: 15000 });
  tracker.setChapter(2, 'Chapter 3'); tracker.recordInteraction(); clock = 15000;
  await tracker.flush();
  clock = 76000; tracker.flush();
  tracker.setChapter(3, 'Chapter 4'); tracker.recordInteraction(); clock = 91000;
  await tracker.flush();
  assert.deepEqual(sent.map(item => item.client_sequence), [1, 1, 2]);
  assert.equal(sent[2].chapter_index, 3);
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
