(function(root, factory) {
  var exported = factory(root);
  if (typeof module === 'object' && module.exports) module.exports = exported;
  root.EpubReadingSessions = exported;
})(typeof window !== 'undefined' ? window : globalThis, function(root) {
  'use strict';

  var STORAGE_PREFIX = 'epub-reading-sessions:';
  var CLIENT_ID_KEY = STORAGE_PREFIX + 'client-id';
  var COORDINATION_KEY = STORAGE_PREFIX + 'active-tab';
  var MAX_PENDING = 4;
  var MAX_SECONDS = 20;
  var PENDING_TTL_MS = 5 * 60 * 1000;

  function randomClientId() {
    return 'reading-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2);
  }

  function storedClientId(storage) {
    if (!storage) return randomClientId();
    try {
      var existing = storage.getItem(CLIENT_ID_KEY);
      if (existing) return existing;
      var created = randomClientId();
      storage.setItem(CLIENT_ID_KEY, created);
      return created;
    } catch (error) {
      return randomClientId();
    }
  }

  function heartbeatPayload(state, seconds) {
    return {
      client_id: state.clientId,
      client_sequence: state.nextSequence,
      chapter_index: state.chapterIndex,
      active_seconds: Math.min(MAX_SECONDS, seconds)
    };
  }

  function isActive(state, now) {
    return state.visible && state.focused && state.leader && state.chapterIndex !== null &&
      state.lastInteraction !== null && now - state.lastInteraction < state.idleMs;
  }

  function asSendPayload(payload) {
    return {
      chapter_index: payload.chapter_index,
      active_seconds: payload.active_seconds,
      client_sequence: payload.client_sequence
    };
  }

  function validPayload(value) {
    return value && Number.isInteger(value.chapter_index) && value.chapter_index >= 0 &&
      Number.isInteger(value.active_seconds) && value.active_seconds >= 1 && value.active_seconds <= MAX_SECONDS &&
      Number.isInteger(value.client_sequence) && value.client_sequence >= 1 &&
      Number.isFinite(value.queued_at) && value.queued_at >= 0;
  }

  function openChannel(channel) {
    if (!channel) return null;
    return typeof channel.open === 'function' ? channel.open() : channel;
  }

  function createTracker(options) {
    options = options || {};
    var storage = options.sessionStorage;
    var localStorage = options.localStorage || null;
    var clientId = options.clientId || storedClientId(storage);
    var now = options.now || function() { return Date.now(); };
    var schedule = options.schedule || function(callback, delay) {
      var timer = setTimeout(callback, delay);
      if (timer && typeof timer.unref === 'function') timer.unref();
      return timer;
    };
    var cancel = options.cancel || function(timer) { clearTimeout(timer); };
    var eventTarget = options.eventTarget || null;
    var documentTarget = options.document || null;
    var state = {
      clientId: clientId,
      chapterIndex: null,
      chapterLabel: '',
      visible: options.visible !== false,
      focused: options.focused !== false,
      leader: options.focused !== false,
      leaderId: clientId,
      lastInteraction: null,
      idleMs: options.idleMs || 60000,
      heartbeatMs: options.heartbeatMs || 15000,
      lastTick: now(),
      unaccountedMs: 0,
      buckets: [],
      pending: [],
      nextSequence: 1,
      inFlight: null,
      inFlightPayload: null,
      requestedFlush: false,
      requestedKeepalive: false,
      consecutiveFailures: 0,
      retryAnnounced: false,
      failureAnnounced: false,
      timer: null,
      destroyed: false
    };
    var queueKey = STORAGE_PREFIX + clientId;
    var sequenceKey = queueKey + ':next-sequence';
    var listeners = [];
    var channel = openChannel(options.channel);
    var leaseMs = options.leaderLeaseMs || Math.max(state.heartbeatMs * 2, 30000);

    function restorePending() {
      if (!storage) return;
      try {
        var saved = JSON.parse(storage.getItem(queueKey) || '[]');
        if (!Array.isArray(saved)) return;
        state.pending = saved.map(function(payload) {
          if (payload && !Number.isFinite(payload.queued_at)) payload.queued_at = now();
          return payload;
        }).filter(validPayload).filter(function(payload) {
          return now() - payload.queued_at <= PENDING_TTL_MS;
        }).slice(0, MAX_PENDING);
        state.pending.forEach(function(payload) {
          state.nextSequence = Math.max(state.nextSequence, payload.client_sequence + 1);
        });
      } catch (error) {}
    }

    function restoreNextSequence() {
      if (!storage) return;
      try {
        var saved = parseInt(storage.getItem(sequenceKey), 10);
        if (Number.isInteger(saved) && saved >= 1) state.nextSequence = saved;
      } catch (error) {}
    }

    function saveNextSequence() {
      if (!storage) return;
      try { storage.setItem(sequenceKey, String(state.nextSequence)); } catch (error) {}
    }

    function savePending() {
      if (!storage) return;
      try {
        if (state.pending.length) storage.setItem(queueKey, JSON.stringify(state.pending));
        else storage.removeItem(queueKey);
      } catch (error) {}
    }

    function accrue(current) {
      if (state.visible && state.focused && state.leader && state.chapterIndex !== null && state.lastInteraction !== null) {
        var activeUntil = Math.min(current, state.lastInteraction + state.idleMs);
        state.unaccountedMs += Math.max(0, activeUntil - state.lastTick);
        var seconds = Math.floor(state.unaccountedMs / 1000);
        if (seconds) {
          state.unaccountedMs -= seconds * 1000;
          var latest = state.buckets[state.buckets.length - 1];
          if (latest && latest.chapter_index === state.chapterIndex) latest.seconds += seconds;
          else state.buckets.push({ chapter_index: state.chapterIndex, seconds: seconds });
        }
      }
      state.lastTick = current;
    }

    function queueBuckets() {
      if (!state.buckets.length || state.pending.length >= MAX_PENDING) return;
      var bucket = state.buckets[0];
      if (!bucket.seconds) {
        state.buckets.shift();
        return queueBuckets();
      }
      var seconds = Math.min(MAX_SECONDS, bucket.seconds);
      var payload = heartbeatPayload({
        clientId: state.clientId,
        nextSequence: state.nextSequence,
        chapterIndex: bucket.chapter_index
      }, seconds);
      payload.queued_at = now();
      state.nextSequence += 1;
      saveNextSequence();
      bucket.seconds -= seconds;
      state.pending.push(payload);
      if (!bucket.seconds) state.buckets.shift();
      savePending();
    }

    function removePending(payload) {
      var index = state.pending.indexOf(payload);
      if (index >= 0) state.pending.splice(index, 1);
      savePending();
    }

    function retryLater(payload) {
      savePending();
      state.consecutiveFailures += 1;
      if (!state.retryAnnounced) {
        state.retryAnnounced = true;
        if (typeof options.onStatus === 'function') options.onStatus('pending');
      }
      if (state.consecutiveFailures >= 3 && !state.failureAnnounced) {
        state.failureAnnounced = true;
        if (typeof options.onStatus === 'function') options.onStatus('error');
      }
    }

    function retryable(error) {
      var status = error && error.status;
      return !Number.isInteger(status) || status === 429 || status >= 500;
    }

    function discardPending(payload) {
      removePending(payload);
      state.consecutiveFailures = 0;
      state.retryAnnounced = false;
      state.failureAnnounced = false;
      if (typeof options.onStatus === 'function') options.onStatus('discarded');
    }

    function settle(payload, successful, error) {
      state.inFlight = null;
      state.inFlightPayload = null;
      if (successful) {
        removePending(payload);
        state.consecutiveFailures = 0;
        if (!state.pending.length) {
          state.retryAnnounced = false;
          state.failureAnnounced = false;
        }
      } else if (retryable(error)) retryLater(payload);
      else discardPending(payload);
      if (state.requestedFlush && !state.destroyed) {
        var keepalive = state.requestedKeepalive;
        state.requestedFlush = false;
        state.requestedKeepalive = false;
        flush(keepalive);
      } else if (!successful && !retryable(error) && state.pending.length && !state.destroyed) {
        flush(false);
      }
    }

    function flush(keepalive) {
      if (state.destroyed) return Promise.resolve(null);
      refreshLeaseLeadership();
      accrue(now());
      queueBuckets();
      if (!state.leader || !state.pending.length) return Promise.resolve(null);
      if (state.inFlight) {
        if (keepalive && state.inFlightPayload) sendKeepalive(state.inFlightPayload);
        state.requestedFlush = true;
        state.requestedKeepalive = state.requestedKeepalive || !!keepalive;
        return state.inFlight;
      }
      var payload = state.pending[0];
      var result;
      try {
        result = (options.send || function() {})(asSendPayload(payload), !!keepalive);
      } catch (error) {
        settle(payload, false, error);
        return Promise.resolve(null);
      }
      if (!result || typeof result.then !== 'function') {
        settle(payload, true);
        return Promise.resolve(result || null);
      }
      state.inFlightPayload = payload;
      state.inFlight = Promise.resolve(result).then(function(response) {
        settle(payload, true);
        return response;
      }, function(error) {
        settle(payload, false, error);
        return null;
      });
      return state.inFlight;
    }

    function sendKeepalive(payload) {
      var result;
      try {
        result = (options.send || function() {})(asSendPayload(payload), true);
      } catch (error) {
        return;
      }
      if (result && typeof result.then === 'function') {
        Promise.resolve(result).then(function() { removePending(payload); }, function() {});
      } else {
        removePending(payload);
      }
    }

    function scheduleHeartbeat() {
      if (state.destroyed || !state.heartbeatMs) return;
      state.timer = schedule(function() {
        state.timer = null;
        refreshLeaseLeadership();
        if (!channel && localStorage && state.leader && state.focused) announce(true);
        flush(false);
        scheduleHeartbeat();
      }, state.heartbeatMs);
    }

    function leaseMessage(focused) {
      return {
        type: 'epub-reading-session-active',
        clientId: state.clientId,
        focused: focused,
        expiresAt: focused ? now() + leaseMs : 0
      };
    }

    function currentLease() {
      if (!localStorage) return null;
      try {
        var saved = JSON.parse(localStorage.getItem(COORDINATION_KEY) || 'null');
        if (!saved || saved.type !== 'epub-reading-session-active' || !saved.focused || !saved.clientId ||
          !Number.isFinite(saved.expiresAt) || saved.expiresAt <= now()) return null;
        return saved;
      } catch (error) {
        return null;
      }
    }

    function announce(focused) {
      var message = leaseMessage(focused);
      if (channel && typeof channel.postMessage === 'function') channel.postMessage(message);
      else if (localStorage) {
        try {
          if (focused) localStorage.setItem(COORDINATION_KEY, JSON.stringify(message));
          else {
            var lease = currentLease();
            if (lease && lease.clientId === state.clientId) localStorage.removeItem(COORDINATION_KEY);
          }
        } catch (error) {}
      }
    }

    function receiveAnnouncement(message) {
      if (!message || message.type !== 'epub-reading-session-active' || message.clientId === state.clientId) return;
      if (message.focused) {
        if (message.expiresAt !== undefined && message.expiresAt <= now()) return;
        accrue(now());
        state.leaderId = message.clientId;
        state.leader = false;
        state.lastInteraction = null;
      }
    }

    function refreshLeaseLeadership() {
      if (channel || !localStorage) return state.leader;
      var lease = currentLease();
      if (lease && lease.clientId !== state.clientId) {
        state.leader = false;
        state.leaderId = lease.clientId;
        return false;
      }
      if (!state.focused) {
        state.leader = false;
        state.leaderId = lease ? lease.clientId : null;
        return false;
      }
      if (!lease || lease.clientId !== state.clientId) {
        state.leader = true;
        state.leaderId = state.clientId;
        announce(true);
      }
      return state.leader;
    }

    function electInitialLeader() {
      refreshLeaseLeadership();
    }

    function setChapter(chapterIndex, chapterLabel) {
      if (!Number.isInteger(chapterIndex) || chapterIndex < 0) return;
      var current = now();
      accrue(current);
      queueBuckets();
      state.chapterIndex = chapterIndex;
      state.chapterLabel = typeof chapterLabel === 'string' ? chapterLabel : '';
      state.lastTick = current;
    }

    function recordInteraction() {
      var current = now();
      accrue(current);
      state.lastInteraction = current;
      state.lastTick = current;
    }

    function setVisible(visible) {
      var current = now();
      accrue(current);
      state.visible = !!visible;
      state.lastInteraction = null;
      state.lastTick = current;
    }

    function setFocused(focused) {
      var current = now();
      accrue(current);
      state.focused = !!focused;
      state.lastInteraction = null;
      state.lastTick = current;
      if (state.focused) {
        state.leader = true;
        state.leaderId = state.clientId;
        announce(true);
      } else if (state.leader) {
        state.leader = false;
        announce(false);
      }
    }

    function addListener(target, type, handler) {
      if (!target || typeof target.addEventListener !== 'function') return;
      target.addEventListener(type, handler);
      listeners.push({ target: target, type: type, handler: handler });
    }

    function bindBrowserEvents() {
      addListener(eventTarget, 'scroll', recordInteraction);
      addListener(eventTarget, 'keydown', function(event) {
        var key = event && event.key;
        var target = event && event.target;
        var tag = target && target.tagName && target.tagName.toLowerCase();
        if (target && (target.isContentEditable || tag === 'input' || tag === 'textarea' || tag === 'select')) return;
        if (['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown', 'PageUp', 'PageDown', 'Home', 'End', ' ', 'Spacebar'].indexOf(key) >= 0) recordInteraction();
      });
      addListener(eventTarget, 'epub:reader-page-turn', recordInteraction);
      addListener(eventTarget, 'focus', function() { setFocused(true); });
      addListener(eventTarget, 'blur', function() { setFocused(false); });
      addListener(eventTarget, 'pagehide', function() { flush(true); });
      addListener(eventTarget, 'epub-browser:chapter-change', function(event) {
        var detail = event && event.detail || {};
        setChapter(detail.chapterIndex === undefined ? detail.index : detail.chapterIndex, detail.chapterLabel || detail.title);
        recordInteraction();
      });
      addListener(documentTarget, 'visibilitychange', function() {
        if (documentTarget.hidden) {
          flush(true);
          setVisible(false);
        } else setVisible(true);
      });
      addListener(eventTarget, 'storage', function(event) {
        if (event && event.key === COORDINATION_KEY) refreshLeaseLeadership();
      });
      if (channel) channel.onmessage = function(event) { receiveAnnouncement(event && event.data); };
    }

    function destroy() {
      if (state.destroyed) return;
      state.destroyed = true;
      if (state.timer !== null) cancel(state.timer);
      state.timer = null;
      listeners.forEach(function(listener) {
        listener.target.removeEventListener(listener.type, listener.handler);
      });
      listeners = [];
      if (channel) {
        channel.onmessage = null;
        if (typeof channel.close === 'function') channel.close();
      }
    }

    restoreNextSequence();
    restorePending();
    saveNextSequence();
    electInitialLeader();
    bindBrowserEvents();
    scheduleHeartbeat();
    return {
      recordInteraction: recordInteraction,
      setChapter: setChapter,
      setVisible: setVisible,
      setFocused: setFocused,
      flush: flush,
      destroy: destroy,
      isLeader: function() { return state.leader; },
      pendingCount: function() { return state.pending.length; },
      clientId: state.clientId
    };
  }

  function start(options) {
    options = options || {};
    var browser = options.root || root;
    if (!browser || browser.EpubBrowserMode !== 'server' || !browser.EpubBrowserAuth ||
      typeof browser.EpubBrowserAuth.fetch !== 'function') return null;
    var documentTarget = browser.document;
    var content = options.content || (documentTarget && documentTarget.getElementById('eb-content'));
    if (!content) return null;
    var bookId = options.bookId || content.getAttribute('data-book-hash');
    var chapterIndex = options.chapterIndex;
    if (chapterIndex === undefined) chapterIndex = parseInt(content.getAttribute('data-chapter-index'), 10);
    if (!bookId || !Number.isInteger(chapterIndex)) return null;
    var publicPath = browser.EpubBrowserURL && browser.EpubBrowserURL.publicPath;
    var endpoint = (publicPath ? publicPath('/api/reading-sessions/' + encodeURIComponent(bookId) + '/heartbeat') :
      '/api/reading-sessions/' + encodeURIComponent(bookId) + '/heartbeat');
    var storage = options.sessionStorage || browser.sessionStorage;
    var channel = options.channel;
    if (!channel && browser.BroadcastChannel) {
      try { channel = new browser.BroadcastChannel('epub-reading-sessions'); } catch (error) {}
    }
    var clientId = options.clientId || storedClientId(storage);
    function notifyStatus(status) {
      var i18n = browser.EpubBrowserI18n;
      var key = status === 'error' ? 'readingSessions.error' : status === 'discarded' ? 'readingSessions.discarded' : 'readingSessions.pending';
      var message = i18n && typeof i18n.t === 'function' ? i18n.t(key) : key;
      var notification = browser.EpubBrowserNotification;
      if (notification && typeof notification.show === 'function') {
        notification.show(message, status === 'error' || status === 'discarded' ? 'error' : 'warning');
      }
    }
    var tracker = createTracker({
      now: options.now,
      schedule: options.schedule,
      cancel: options.cancel,
      idleMs: options.idleMs,
      heartbeatMs: options.heartbeatMs,
      sessionStorage: storage,
      localStorage: options.localStorage || browser.localStorage,
      clientId: clientId,
      channel: channel,
      eventTarget: options.eventTarget || browser,
      document: options.document || documentTarget,
      visible: !documentTarget || !documentTarget.hidden,
      focused: !documentTarget || !documentTarget.hasFocus || documentTarget.hasFocus(),
      onStatus: notifyStatus,
      send: function(payload, keepalive) {
        var request = {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            client_id: clientId,
            client_sequence: payload.client_sequence,
            chapter_index: payload.chapter_index,
            active_seconds: payload.active_seconds
          })
        };
        if (keepalive) request.keepalive = true;
        return Promise.resolve(browser.EpubBrowserAuth.fetch(endpoint, request)).then(function(response) {
          if (!response || !response.ok) {
            var error = new Error('reading_session_heartbeat_failed');
            error.status = response && response.status;
            throw error;
          }
          return response;
        });
      }
    });
    tracker.setChapter(chapterIndex, options.chapterLabel || content.getAttribute('data-chapter-title') || '');
    return tracker;
  }

  return {
    createTracker: createTracker,
    start: start,
    heartbeatPayload: heartbeatPayload,
    isActive: isActive
  };
});
