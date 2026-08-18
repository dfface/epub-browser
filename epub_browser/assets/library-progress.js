(function(root, factory) {
  var exported = factory();
  if (typeof module === 'object' && module.exports) module.exports = exported;
  if (root && root.document) root.EpubLibraryProgress = exported;
})(typeof window !== 'undefined' ? window : (typeof globalThis !== 'undefined' ? globalThis : this), function() {
  'use strict';

  function isNewer(previous, incoming) {
    return !previous || incoming.generation > previous.generation ||
      (incoming.generation === previous.generation && incoming.revision > previous.revision);
  }

  function initialState() {
    return {
      snapshot: null,
      visible: false,
      connected: true,
      hiddenGeneration: null,
      catalogRevision: 0,
      announceDegraded: false
    };
  }

  function stateWith(state, updates) {
    var next = {};
    var key;
    for (key in state) {
      if (Object.prototype.hasOwnProperty.call(state, key)) next[key] = state[key];
    }
    for (key in updates) {
      if (Object.prototype.hasOwnProperty.call(updates, key)) next[key] = updates[key];
    }
    return next;
  }

  function reduce(state, snapshot) {
    state = state || initialState();
    if (!snapshot || !isNewer(state.snapshot, snapshot)) return state;

    var previous = state.snapshot;
    var firstSnapshot = !previous;
    var visible = snapshot.phase !== 'idle' &&
      !(firstSnapshot && snapshot.phase === 'complete') &&
      state.hiddenGeneration !== snapshot.generation;

    return {
      snapshot: snapshot,
      visible: visible,
      connected: true,
      hiddenGeneration: state.hiddenGeneration,
      catalogRevision: Math.max(state.catalogRevision, snapshot.catalog_revision || 0),
      announceDegraded: snapshot.phase === 'degraded' && (!previous || previous.phase !== 'degraded' || previous.generation !== snapshot.generation)
    };
  }

  function createController(options) {
    options = options || {};
    var refreshActive = false;
    var requestedRefreshRevision = 0;
    var completedRefreshRevision = 0;
    var controller = {
      state: initialState(),
      accept: accept,
      dismiss: dismiss,
      disconnected: disconnected,
      render: render
    };

    function requestMetadataRefresh(revision) {
      requestedRefreshRevision = Math.max(requestedRefreshRevision, revision);
      if (refreshActive || requestedRefreshRevision <= completedRefreshRevision || !options.refreshMetadata) return;

      var targetRevision = requestedRefreshRevision;
      refreshActive = true;
      Promise.resolve().then(function() {
        return options.refreshMetadata(targetRevision);
      }).then(refreshSettled, refreshSettled);

      function refreshSettled() {
        completedRefreshRevision = Math.max(completedRefreshRevision, targetRevision);
        refreshActive = false;
        if (requestedRefreshRevision > completedRefreshRevision) {
          requestMetadataRefresh(requestedRefreshRevision);
        }
      }
    }

    function render() {
      if (options.render) options.render(controller.state);
    }

    function accept(snapshot) {
      var previous = controller.state;
      if (!isNewer(previous.snapshot, snapshot)) {
        if (!previous.connected) {
          controller.state = stateWith(previous, { connected: true, announceDegraded: false });
          render();
        }
        return false;
      }
      controller.state = reduce(previous, snapshot);
      render();

      if ((snapshot.catalog_revision || 0) > previous.catalogRevision && options.refreshMetadata) {
        requestMetadataRefresh(snapshot.catalog_revision || 0);
      }
      return true;
    }

    function dismiss() {
      if (!controller.state.snapshot ||
          (controller.state.snapshot.phase !== 'complete' && controller.state.snapshot.phase !== 'degraded')) return;
      controller.state = stateWith(controller.state, {
        hiddenGeneration: controller.state.snapshot.generation,
        visible: false,
        announceDegraded: false
      });
      render();
    }

    function disconnected() {
      if (!controller.state.connected) return;
      controller.state = stateWith(controller.state, { connected: false, announceDegraded: false });
      render();
    }

    return controller;
  }

  function translate(root, key, params) {
    var i18n = root.EpubBrowserI18n;
    if (i18n && i18n.t) return i18n.t(key, params || {});
    var fallback = {
      'library.progress.scanning': 'Scanning library',
      'library.progress.processing': 'Updating library',
      'library.progress.complete': 'Library updated',
      'library.progress.degraded': 'Library updated with failures',
      'library.progress.reconnecting': 'Reconnecting to library updates…',
      'library.progress.summary': 'Processed {completed} of {total} books',
      'library.progress.removed': 'Removed {count} books',
      'library.progress.latest': 'Latest: {book}'
    }[key] || key;
    return fallback.replace(/\{([^}]+)\}/g, function(_, name) { return params && params[name] !== undefined ? params[name] : ''; });
  }

  function phaseTitleKey(phase) {
    if (phase === 'discovering') return 'library.progress.scanning';
    if (phase === 'processing') return 'library.progress.processing';
    if (phase === 'complete') return 'library.progress.complete';
    return 'library.progress.degraded';
  }

  function summaryText(root, snapshot) {
    var parts = [];
    if (snapshot.total) {
      parts.push(translate(root, 'library.progress.summary', {
        completed: snapshot.completed,
        total: snapshot.total
      }));
    }
    if (snapshot.removed) {
      parts.push(translate(root, 'library.progress.removed', { count: snapshot.removed }));
    }
    return parts.join(' · ');
  }

  function createDomOptions(root, mount) {
    var title = mount.querySelector('[data-progress-title]');
    var summary = mount.querySelector('[data-progress-summary]');
    var track = mount.querySelector('[data-progress-track]');
    var bar = mount.querySelector('[data-progress-bar]');
    var latest = mount.querySelector('[data-progress-latest]');
    var failures = mount.querySelector('[data-progress-failures]');
    var failureList = mount.querySelector('[data-progress-failure-list]');
    var close = mount.querySelector('[data-progress-close]');

    function t(key, params) {
      return translate(root, key, params);
    }

    function setPhase(phase) {
      var phases = ['discovering', 'processing', 'complete', 'degraded'];
      phases.forEach(function(name) { mount.classList.remove('library-progress--' + name); });
      mount.classList.add('library-progress--' + phase);
    }

    function render(state) {
      var snapshot = state.snapshot;
      mount.hidden = !snapshot || !state.visible;
      if (!snapshot) return;

      setPhase(snapshot.phase);
      close.hidden = snapshot.phase !== 'complete' && snapshot.phase !== 'degraded';
      close.disabled = snapshot.phase !== 'complete' && snapshot.phase !== 'degraded';
      title.textContent = t(phaseTitleKey(snapshot.phase));
      summary.removeAttribute('role');
      summary.setAttribute('aria-live', 'polite');
      if (state.announceDegraded) {
        summary.removeAttribute('aria-live');
        summary.setAttribute('role', 'alert');
      }
      if (!state.connected) {
        summary.textContent = t('library.progress.reconnecting');
      } else if (state.announceDegraded) {
        summary.textContent = t('library.progress.degraded') + ' ' +
          summaryText(root, snapshot);
      } else {
        summary.textContent = summaryText(root, snapshot);
      }

      if (snapshot.phase === 'discovering') {
        track.classList.add('library-progress-track--indeterminate');
        track.setAttribute('role', 'progressbar');
        track.setAttribute('aria-labelledby', 'libraryProgressTitle');
        track.setAttribute('aria-valuemin', '0');
        track.removeAttribute('aria-valuemax');
        track.removeAttribute('aria-valuenow');
        bar.style.width = '';
      } else {
        track.classList.remove('library-progress-track--indeterminate');
        track.setAttribute('role', 'progressbar');
        track.setAttribute('aria-labelledby', 'libraryProgressTitle');
        track.setAttribute('aria-valuemin', '0');
        track.setAttribute('aria-valuemax', String(snapshot.total));
        track.setAttribute('aria-valuenow', String(snapshot.completed));
        bar.style.width = snapshot.total ? Math.min(100, Math.round((snapshot.completed / snapshot.total) * 100)) + '%' : '100%';
      }

      latest.textContent = snapshot.latest_book ? t('library.progress.latest', { book: snapshot.latest_book }) : '';
      failures.hidden = !snapshot.failures || snapshot.failures.length === 0;
      while (failureList.children.length) failureList.removeChild(failureList.children[0]);
      (snapshot.failures || []).forEach(function(failure) {
        var item = root.document.createElement('li');
        item.textContent = failure.filename + ': ' + failure.message;
        failureList.appendChild(item);
      });
    }

    return {
      render: render,
      refreshMetadata: function() {
        return root.refreshLibraryMetadata ? root.refreshLibraryMetadata.apply(root, arguments) : Promise.resolve();
      }
    };
  }

  function eventUrl(root) {
    return (root.EpubBrowserBasePath || '/') + 'api/library-events';
  }

  function start(root) {
    var mount = root.document.getElementById('libraryProgress');
    if (root.EpubBrowserMode !== 'server' || !mount || !root.EventSource) return null;
    var controller = createController(createDomOptions(root, mount));
    if (root.EpubBrowserI18n && root.EpubBrowserI18n.onLocaleChange) {
      root.EpubBrowserI18n.onLocaleChange(function() { controller.render(); });
    }
    var source = new root.EventSource(eventUrl(root));
    source.addEventListener('progress', function(event) {
      try { controller.accept(JSON.parse(event.data)); } catch (error) {}
    });
    source.onerror = function() { controller.disconnected(); };
    mount.querySelector('[data-progress-close]').addEventListener('click', function() { controller.dismiss(); });
    return { controller: controller, source: source };
  }

  return {
    isNewer: isNewer,
    reduce: reduce,
    createController: createController,
    createDomOptions: createDomOptions,
    summaryText: summaryText,
    start: start
  };
});
