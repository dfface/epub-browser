(function(root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory;
  else root.EpubPDFChapter = factory(root);
})(typeof window !== 'undefined' ? window : globalThis, function createPDFChapterAdapter(root, dependencies) {
  'use strict';

  dependencies = dependencies || {};
  var records = new WeakMap();
  var documentEntries = new Map();
  var modulePromise = null;
  var runtimeKey = '';
  var activeNodes = new Set();
  var searchGeneration = 0;

  function translate(key, params) {
    var i18n = root.EpubBrowserI18n;
    return i18n && typeof i18n.t === 'function' ? i18n.t(key, params) : key;
  }

  function absoluteURL(value) {
    return new URL(value, root.document.baseURI || root.location.href);
  }

  function trustedAssetURL(value, worker) {
    var url = absoluteURL(value);
    var origin = root.location.origin || absoluteURL(root.location.href).origin;
    var name = worker ? 'pdf\\.worker' : 'pdf';
    var pattern = new RegExp('/assets/immutable/vendor/pdfjs/build/' + name + '\\.[0-9a-f]{12}\\.mjs$');
    if (url.origin !== origin || !pattern.test(url.pathname)) {
      throw new Error('Untrusted PDF.js asset URL');
    }
    return url.pathname + url.search;
  }

  function configForPage() {
    var config = root.EpubPDFConfig || {};
    if (!config.documentUrl || !config.pdfjsModuleUrl || !config.pdfjsWorkerUrl) {
      throw new Error('Incomplete PDF configuration');
    }
    var documentURL = absoluteURL(config.documentUrl);
    var origin = root.location.origin || absoluteURL(root.location.href).origin;
    if (documentURL.origin !== origin) throw new Error('Untrusted PDF document URL');
    var preferences = readPreferences(documentURL.href);
    return {
      documentUrl: documentURL.href,
      moduleUrl: trustedAssetURL(config.pdfjsModuleUrl, false),
      workerUrl: trustedAssetURL(config.pdfjsWorkerUrl, true),
      zoom: Math.max(0.25, Math.min(4, Number(preferences.zoom || config.zoom) || 1)),
      rotation: normalizeRotation(preferences.rotation === undefined ? config.rotation : preferences.rotation),
      fit: preferences.fit === 'page' || preferences.fit === 'width'
        ? preferences.fit
        : (config.fit === 'page' || config.fitMode === 'page' ? 'page' : 'width')
    };
  }

  function normalizeRotation(value) {
    return ((Math.round((Number(value) || 0) / 90) * 90) % 360 + 360) % 360;
  }

  function preferencesKey(url) {
    return 'epub-pdf:' + url + ':preferences';
  }

  function readPreferences(url) {
    if (!root.localStorage) return {};
    try {
      var value = root.localStorage.getItem(preferencesKey(url));
      return value ? JSON.parse(value) : {};
    } catch (error) {
      return {};
    }
  }

  function writePreferences(update) {
    var config = configForPage();
    var preferences = readPreferences(config.documentUrl);
    Object.keys(update).forEach(function(key) { preferences[key] = update[key]; });
    if (root.localStorage) {
      try { root.localStorage.setItem(preferencesKey(config.documentUrl), JSON.stringify(preferences)); }
      catch (error) {}
    }
    return preferences;
  }

  function destroyEntry(entry) {
    if (!entry || entry.destroyed) return;
    entry.destroyed = true;
    documentEntries.delete(entry.url);
    if (entry.task && typeof entry.task.destroy === 'function') entry.task.destroy();
    else if (entry.document && typeof entry.document.destroy === 'function') entry.document.destroy();
  }

  function loadPDFModule(config) {
    var key = config.moduleUrl + '\n' + config.workerUrl;
    if (runtimeKey && runtimeKey !== key) {
      documentEntries.forEach(destroyEntry);
      modulePromise = null;
    }
    runtimeKey = key;
    if (!modulePromise) {
      var importer = dependencies.importModule || function(url) { return import(url); };
      modulePromise = Promise.resolve(importer(config.moduleUrl)).then(function(pdfjs) {
        pdfjs.GlobalWorkerOptions.workerSrc = config.workerUrl;
        return pdfjs;
      });
    }
    return modulePromise;
  }

  function acquireDocument(pdfjs, config, node) {
    documentEntries.forEach(function(entry) {
      if (entry.url !== config.documentUrl) destroyEntry(entry);
    });
    var entry = documentEntries.get(config.documentUrl);
    if (!entry) {
      var task = pdfjs.getDocument({
        url: config.documentUrl,
        cMapUrl: null,
        standardFontDataUrl: null,
        wasmUrl: null,
        iccUrl: null,
        useWorkerFetch: false,
        useWasm: false,
        isImageDecoderSupported: false,
        isOffscreenCanvasSupported: false,
        enableXfa: false,
        // PDFs in the wild frequently contain recoverable operator/resource
        // errors. PDF.js defaults to recovery mode; keep that behavior so one
        // imperfect object cannot turn an otherwise readable page white.
        stopAtErrors: false,
        disableRange: false,
        disableStream: true,
        disableAutoFetch: true,
        rangeChunkSize: 65536
      });
      entry = {
        url: config.documentUrl,
        task: task,
        document: null,
        users: new Set(),
        releaseToken: null,
        destroyed: false
      };
      task.onPassword = function(updatePassword) {
        var password = root.prompt(translate('pdf.passwordRequired'));
        if (password === null) {
          destroyEntry(entry);
          return;
        }
        updatePassword(password);
        password = '';
      };
      entry.promise = Promise.resolve(task.promise).then(function(document) {
        entry.document = document;
        return document;
      });
      documentEntries.set(config.documentUrl, entry);
    }
    entry.releaseToken = null;
    entry.users.add(node);
    return entry;
  }

  function releaseDocument(entry, node) {
    if (!entry) return;
    entry.users.delete(node);
    if (entry.users.size) return;
    var token = {};
    entry.releaseToken = token;
    Promise.resolve().then(function() {
      return Promise.resolve().then(function() {
        if (entry.releaseToken === token && entry.users.size === 0) destroyEntry(entry);
      });
    });
  }

  function nodesWithin(rootNode) {
    var nodes = [];
    if (rootNode && typeof rootNode.hasAttribute === 'function' && rootNode.hasAttribute('data-pdf-page-number')) {
      nodes.push(rootNode);
    }
    if (rootNode && typeof rootNode.querySelectorAll === 'function') {
      var descendants = rootNode.querySelectorAll('[data-pdf-page-number]');
      for (var i = 0; i < descendants.length; i++) {
        if (nodes.indexOf(descendants[i]) === -1) nodes.push(descendants[i]);
      }
    }
    return nodes;
  }

  function statusNode(node, role, key) {
    var status = node.ownerDocument.createElement('p');
    status.className = 'pdf-page-status';
    status.setAttribute('role', role);
    status.setAttribute('data-pdf-status', role === 'status' ? 'loading' : 'error');
    status.setAttribute('aria-live', role === 'alert' ? 'assertive' : 'polite');
    status.textContent = translate(key);
    node.replaceChildren(status);
    return status;
  }

  function chapterRootFor(node) {
    var current = node;
    while (current) {
      if (current.getAttribute && current.getAttribute('id') === 'eb-content') return current;
      current = current.parentNode;
    }
    return null;
  }

  function announceAnnotationContentReady(node, annotationAvailable) {
    var rootNode = chapterRootFor(node);
    var pageNumber = Number(node.getAttribute('data-pdf-page-number'));
    if (!rootNode || !Number.isInteger(pageNumber) || pageNumber < 1 || !root.dispatchEvent) return;
    var detail = {
      root: rootNode,
      chapterIndex: pageNumber - 1,
      chapterUrl: 'chapter_' + (pageNumber - 1) + '.html',
      annotationAvailable: annotationAvailable !== false
    };
    var event = typeof root.CustomEvent === 'function'
      ? new root.CustomEvent('epub-browser:annotation-content-ready', { detail: detail })
      : { type: 'epub-browser:annotation-content-ready', detail: detail };
    root.dispatchEvent(event);
  }

  function cancelRendering(record) {
    record.generation += 1;
    if (record.renderTask && typeof record.renderTask.cancel === 'function') record.renderTask.cancel();
    if (record.textLayer && typeof record.textLayer.cancel === 'function') record.textLayer.cancel();
    record.renderTask = null;
    record.textLayer = null;
  }

  function availablePageHeight(node, bounds) {
    var viewportHeight = Number(root.innerHeight);
    if (!(viewportHeight > 0) && node.ownerDocument && node.ownerDocument.documentElement) {
      viewportHeight = Number(node.ownerDocument.documentElement.clientHeight);
    }
    if (!(viewportHeight > 0)) return Math.max(1, bounds.height || node.clientHeight || 1);
    var measuredTop = Number(bounds.top);
    var topInset = measuredTop >= 0 && measuredTop <= viewportHeight / 2
      ? measuredTop
      : Math.min(92, viewportHeight / 4);
    return Math.max(1, viewportHeight - topInset - 20);
  }

  function pageStageFor(node) {
    var content = chapterRootFor(node);
    var parent = content && content.parentNode;
    if (parent && parent.classList && parent.classList.contains('eb-content-container')) return parent;
    return content || node;
  }

  function availablePageWidth(node, baseViewport) {
    var stage = pageStageFor(node);
    var bounds = stage.getBoundingClientRect ? stage.getBoundingClientRect() : {};
    var width = Number(stage.clientWidth) || Number(bounds.width) || Number(node.clientWidth) || baseViewport.width;
    if (stage !== node && typeof root.getComputedStyle === 'function') {
      var style = root.getComputedStyle(stage);
      width -= (parseFloat(style.paddingLeft) || 0) + (parseFloat(style.paddingRight) || 0);
    }
    return Math.max(1, width);
  }

  function updateContinuousPageGap(viewportWidth) {
    var document = root.document;
    var documentElement = document && document.documentElement;
    if (!documentElement || !documentElement.style || !documentElement.style.setProperty) return;
    var gap = Math.round(Math.max(8, Math.min(20, Number(viewportWidth) * 0.015)));
    documentElement.style.setProperty('--pdf-page-gap', gap + 'px');
  }

  function setPlaceholderGeometry(node) {
    var width = Number(node.getAttribute('data-pdf-page-width'));
    var height = Number(node.getAttribute('data-pdf-page-height'));
    if (!(width > 0) || !(height > 0)) return;
    var config;
    try {
      config = configForPage();
    } catch (error) {
      var fallback = root.EpubPDFConfig || {};
      config = {
        zoom: Math.max(0.25, Math.min(4, Number(fallback.zoom) || 1)),
        rotation: normalizeRotation(fallback.rotation),
        fit: fallback.fit === 'page' || fallback.fitMode === 'page' ? 'page' : 'width'
      };
    }
    var rotated = config.rotation % 180 !== 0;
    var baseViewport = { width: rotated ? height : width, height: rotated ? width : height };
    var availableWidth = availablePageWidth(node, baseViewport);
    var bounds = node.getBoundingClientRect ? node.getBoundingClientRect() : {};
    var scale = config.fit === 'page'
      ? Math.min(availableWidth / baseViewport.width, availablePageHeight(node, bounds) / baseViewport.height)
      : availableWidth / baseViewport.width;
    var renderedWidth = baseViewport.width * scale * config.zoom;
    var renderedHeight = baseViewport.height * scale * config.zoom;
    node.style.aspectRatio = 'auto';
    node.style.width = renderedWidth + 'px';
    node.style.height = renderedHeight + 'px';
    node.style.minHeight = renderedHeight + 'px';
    node.setAttribute('data-pdf-rendered', 'placeholder');
    node.setAttribute('aria-busy', 'false');
  }

  async function paintNode(node, isRerender) {
    var record = records.get(node);
    if (!record || record.disposed) return;
    if (isRerender) cancelRendering(record);
    var generation = ++record.generation;
    node.setAttribute('data-pdf-rendered', 'pending');
    node.setAttribute('aria-busy', 'true');
    var loadingStatus = statusNode(node, 'status', 'pdf.loadingPage');
    try {
      var config = configForPage();
      var pdfjs = await loadPDFModule(config);
      if (record.disposed || generation !== record.generation) return;
      var entry = acquireDocument(pdfjs, config, node);
      record.documentEntry = entry;
      var pdfDocument = await entry.promise;
      if (record.disposed || generation !== record.generation) return;
      var pageNumber = Number(node.getAttribute('data-pdf-page-number'));
      if (!Number.isInteger(pageNumber) || pageNumber < 1 || pageNumber > pdfDocument.numPages) {
        throw new Error('Invalid PDF page number');
      }
      var page = await pdfDocument.getPage(pageNumber);
      if (record.disposed || generation !== record.generation) return;
      var baseViewport = page.getViewport({ scale: 1, rotation: config.rotation });
      var bounds = node.getBoundingClientRect();
      var availableWidth = availablePageWidth(node, baseViewport);
      var availableHeight = config.fit === 'page'
        ? availablePageHeight(node, bounds)
        : Math.max(1, bounds.height || node.clientHeight || baseViewport.height);
      record.renderedWidth = availableWidth;
      record.renderedHeight = availableHeight;
      record.fit = config.fit;
      var fitScale = config.fit === 'page'
        ? Math.min(availableWidth / baseViewport.width, availableHeight / baseViewport.height)
        : availableWidth / baseViewport.width;
      var viewport = page.getViewport({ scale: fitScale * config.zoom, rotation: config.rotation });
      var dpr = Math.max(1, Number(root.devicePixelRatio) || 1);
      var canvas = node.ownerDocument.createElement('canvas');
      canvas.className = 'pdf-page-canvas';
      canvas.width = Math.max(1, Math.floor(viewport.width * dpr));
      canvas.height = Math.max(1, Math.floor(viewport.height * dpr));
      canvas.style.width = viewport.width + 'px';
      canvas.style.height = viewport.height + 'px';
      canvas.style.marginLeft = '0px';
      var textLayerNode = node.ownerDocument.createElement('div');
      textLayerNode.className = 'pdf-page-text-layer textLayer';
      textLayerNode.style.left = '0px';
      textLayerNode.style.setProperty('--total-scale-factor', viewport.scale);
      node.style.aspectRatio = 'auto';
      node.style.width = viewport.width + 'px';
      node.style.height = viewport.height + 'px';
      node.style.minHeight = viewport.height + 'px';
      updateContinuousPageGap(viewport.width);
      node.replaceChildren(canvas, textLayerNode, loadingStatus);
      var renderTask = page.render({
        canvasContext: canvas.getContext('2d'),
        viewport: viewport,
        transform: dpr === 1 ? null : [dpr, 0, 0, dpr, 0, 0]
      });
      record.renderTask = renderTask;
      await renderTask.promise;
      if (record.renderTask === renderTask) record.renderTask = null;
      if (record.disposed || generation !== record.generation) return;
      if (node.getAttribute('data-pdf-has-extractable-text') === 'true') {
        var textContent = await page.getTextContent();
        if (record.disposed || generation !== record.generation) return;
        var textLayer = new pdfjs.TextLayer({
          textContentSource: textContent,
          container: textLayerNode,
          viewport: viewport
        });
        record.textLayer = textLayer;
        await textLayer.render();
        // PDF.js writes a CSS round() expression that depends on viewer-only
        // custom properties. This standalone reader owns exact viewport
        // geometry, so restore concrete dimensions after TextLayer.render().
        textLayerNode.style.width = viewport.width + 'px';
        textLayerNode.style.height = viewport.height + 'px';
        textLayerNode.style.left = '0px';
        if (record.textLayer === textLayer) record.textLayer = null;
        if (record.disposed || generation !== record.generation) return;
      } else {
        textLayerNode.setAttribute('aria-label', translate('pdf.textUnavailable'));
      }
      if (record.disposed || generation !== record.generation) return;
      loadingStatus.remove();
      node.setAttribute('data-pdf-rendered', 'complete');
      node.setAttribute('aria-busy', 'false');
      announceAnnotationContentReady(
        node,
        node.getAttribute('data-pdf-has-extractable-text') === 'true'
      );
    } catch (error) {
      if (record.disposed || generation !== record.generation) return;
      node.setAttribute('data-pdf-rendered', 'error');
      node.setAttribute('aria-busy', 'false');
      statusNode(node, 'alert', 'reader.chapterLoadFailed');
      announceAnnotationContentReady(node, false);
    }
  }

  function prepareNode(node) {
    var record = records.get(node);
    if (record && !record.disposed) return record.promise || Promise.resolve();
    setPlaceholderGeometry(node);
    record = {
      disposed: false,
      generation: 0,
      renderTask: null,
      textLayer: null,
      documentEntry: null,
      resizeObserver: null,
      intersectionObserver: null,
      started: false,
      renderedWidth: null,
      renderedHeight: null,
      fit: 'width',
      promise: null
    };
    records.set(node, record);
    activeNodes.add(node);
    if (typeof root.ResizeObserver === 'function') {
      record.resizeObserver = new root.ResizeObserver(function() {
        if (record.disposed || !record.started || record.renderedWidth === null) return;
        var bounds = node.getBoundingClientRect();
        var width = availablePageWidth(node, { width: 1 });
        var height = record.fit === 'page'
          ? availablePageHeight(node, bounds)
          : Math.max(1, bounds.height || node.clientHeight || 1);
        var widthChanged = Math.abs(width - record.renderedWidth) > 0.5;
        var heightChanged = record.fit === 'page' && Math.abs(height - record.renderedHeight) > 0.5;
        if (widthChanged || heightChanged) record.promise = paintNode(node, true);
      });
      record.resizeObserver.observe(pageStageFor(node));
    }
    if (typeof root.IntersectionObserver === 'function') {
      record.intersectionObserver = new root.IntersectionObserver(function(entries) {
        for (var index = 0; index < entries.length; index++) {
          if (!entries[index].isIntersecting || record.disposed) continue;
          record.intersectionObserver.unobserve(node);
          record.started = true;
          record.promise = paintNode(node, false);
          break;
        }
      }, { rootMargin: '100% 0px' });
      record.intersectionObserver.observe(node);
      record.promise = Promise.resolve();
    } else {
      record.started = true;
      record.promise = paintNode(node, false);
    }
    return record.promise;
  }

  function renderWithin(rootNode) {
    return Promise.all(nodesWithin(rootNode).map(prepareNode));
  }

  function disposeNode(node) {
    var record = records.get(node);
    if (!record || record.disposed) return;
    record.disposed = true;
    cancelRendering(record);
    if (record.resizeObserver) record.resizeObserver.disconnect();
    if (record.intersectionObserver) record.intersectionObserver.disconnect();
    releaseDocument(record.documentEntry, node);
    node.replaceChildren();
    node.removeAttribute('data-pdf-rendered');
    node.setAttribute('aria-busy', 'false');
    records.delete(node);
    activeNodes.delete(node);
  }

  function disposeWithin(rootNode) {
    nodesWithin(rootNode).forEach(disposeNode);
  }

  function refreshActivePages() {
    activeNodes.forEach(function(node) {
      var record = records.get(node);
      if (record && !record.disposed && record.started) record.promise = paintNode(node, true);
    });
    return Promise.all(Array.from(activeNodes).map(function(node) {
      var record = records.get(node);
      return record && record.promise;
    }));
  }

  function rotate() {
    var config = configForPage();
    writePreferences({ rotation: normalizeRotation(config.rotation + 90) });
    return refreshActivePages();
  }

  function syncFitControlState() {
    var document = root.document;
    if (!document || !document.getElementById) return;
    var config = configForPage();
    var fit = Math.abs(config.zoom - 1) < 0.001 ? config.fit : '';
    [['pdfFitWidth', 'width'], ['mobilePdfFitWidth', 'width'],
     ['pdfFitPage', 'page'], ['mobilePdfFitPage', 'page']].forEach(function(pair) {
      var button = document.getElementById(pair[0]);
      if (button) button.setAttribute('aria-pressed', String(fit === pair[1]));
    });
  }

  function setFit(fit) {
    writePreferences({ fit: fit === 'page' ? 'page' : 'width', zoom: 1 });
    syncFitControlState();
    return refreshActivePages();
  }

  function fitWidth() { return setFit('width'); }
  function fitPage() { return setFit('page'); }

  function setZoom(delta) {
    var config = configForPage();
    var zoom = Math.max(0.25, Math.min(4, Math.round((config.zoom + delta) * 100) / 100));
    writePreferences({ zoom: zoom });
    syncFitControlState();
    return refreshActivePages();
  }

  function getZoomPercent() {
    return Math.round(configForPage().zoom * 100);
  }

  function setZoomPercent(percent) {
    var normalized = Math.max(25, Math.min(400, Math.round(Number(percent) || 100)));
    writePreferences({ fit: 'width', zoom: normalized / 100 });
    syncFitControlState();
    return refreshActivePages();
  }

  function setPageWidthPreset(preset) {
    var zoomByPreset = { '1': 0.6, '2': 0.75, '3': 0.88, '4': 1 };
    var zoom = zoomByPreset[String(preset)] || 1;
    writePreferences({ fit: 'width', zoom: zoom });
    syncFitControlState();
    return refreshActivePages();
  }

  async function search(query) {
    var generation = ++searchGeneration;
    var needle = String(query || '').trim().toLocaleLowerCase();
    if (!needle) return [];
    var config = configForPage();
    var pdfjs = await loadPDFModule(config);
    if (generation !== searchGeneration) return [];
    var user = {};
    var entry = acquireDocument(pdfjs, config, user);
    try {
      var pdfDocument = await entry.promise;
      var results = [];
      for (var pageNumber = 1; pageNumber <= pdfDocument.numPages; pageNumber += 1) {
        var page = await pdfDocument.getPage(pageNumber);
        var textContent = await page.getTextContent();
        if (generation !== searchGeneration) return [];
        var text = (textContent.items || []).map(function(item) { return item.str || ''; }).join(' ').replace(/\s+/g, ' ').trim();
        var position = text.toLocaleLowerCase().indexOf(needle);
        if (position !== -1) {
          results.push({
            href: 'chapter_' + (pageNumber - 1) + '.html',
            pageNumber: pageNumber,
            text: text.slice(Math.max(0, position - 48), position + needle.length + 96)
          });
        }
      }
      return results;
    } finally {
      releaseDocument(entry, user);
    }
  }

  function cancelSearch() {
    searchGeneration += 1;
  }

  function bindReaderControls() {
    var document = root.document;
    if (!document || !document.getElementById) return;
    var drawer = document.getElementById('pdfSearchDrawer');
    var toggle = document.getElementById('pdfSearchToggle');
    var mobileToggle = document.getElementById('mobilePdfSearchToggle');
    var drawerController = root.EpubReaderDrawers;
    if (!drawer || !toggle || !drawerController || typeof drawerController.register !== 'function' || drawer.getAttribute('data-pdf-controls-bound') === 'true') return;
    drawer.setAttribute('data-pdf-controls-bound', 'true');
    var displayedSearchGeneration = 0;
    var controller = drawerController.register({
      panel: drawer,
      toggle: toggle,
      mobileToggle: mobileToggle,
      onClose: function() {
        displayedSearchGeneration += 1;
        cancelSearch();
      }
    });
    toggle.addEventListener('click', function() { controller.open(toggle); });
    if (mobileToggle) mobileToggle.addEventListener('click', function() { controller.open(mobileToggle); });
    var close = document.getElementById('pdfSearchClose');
    if (close) close.addEventListener('click', function() { controller.close(true); });
    var form = document.getElementById('pdfSearchForm');
    var input = document.getElementById('pdfSearchInput');
    var resultsNode = document.getElementById('pdfSearchResults');
    function searchError() {
      resultsNode.replaceChildren();
      var error = document.createElement('li');
      error.setAttribute('role', 'alert');
      error.textContent = translate('pdf.searchFailed');
      resultsNode.appendChild(error);
    }
    if (form && input && resultsNode) form.addEventListener('submit', function(event) {
      event.preventDefault();
      var displayedGeneration = ++displayedSearchGeneration;
      resultsNode.replaceChildren();
      search(input.value).then(function(results) {
        if (displayedGeneration !== displayedSearchGeneration || input.value.trim() === '' || !drawer.classList.contains('active')) return;
        if (!results.length) {
          var empty = document.createElement('li');
          empty.textContent = translate('pdf.searchNoResults');
          resultsNode.appendChild(empty);
          return;
        }
        results.forEach(function(result) {
          var item = document.createElement('li');
          var link = document.createElement('a');
          link.href = result.href;
          link.textContent = translate('pdf.page', { number: result.pageNumber }) + ': ' + result.text;
          item.appendChild(link);
          resultsNode.appendChild(item);
        });
      }).catch(function() {
        if (displayedGeneration === displayedSearchGeneration && drawer.classList.contains('active')) searchError();
      });
    });
    if (input && resultsNode) input.addEventListener('input', function() {
      if (input.value.trim() === '') {
        displayedSearchGeneration += 1;
        cancelSearch();
        resultsNode.replaceChildren();
      }
    });
    function bindAction(ids, action) {
      ids.forEach(function(id) {
        var button = document.getElementById(id);
        if (button) button.addEventListener('click', action);
      });
    }
    [['pdfZoomOut', 'mobilePdfZoomOut', -0.25], ['pdfZoomIn', 'mobilePdfZoomIn', 0.25]].forEach(function(pair) {
      bindAction([pair[0], pair[1]], function() { setZoom(pair[2]); });
    });
    bindAction(['pdfFitWidth', 'mobilePdfFitWidth'], fitWidth);
    bindAction(['pdfFitPage', 'mobilePdfFitPage'], fitPage);
    bindAction(['pdfRotate', 'mobilePdfRotate'], rotate);
    syncFitControlState();
  }

  if (root && typeof root.addEventListener === 'function') {
    root.addEventListener('epub-browser:reader-drawers-ready', bindReaderControls);
    root.addEventListener('epub-browser:chapter-content-added', function(event) {
      renderWithin(event.detail && event.detail.root).catch(function() {});
    });
    root.addEventListener('epub-browser:chapter-content-removed', function(event) {
      disposeWithin(event.detail && event.detail.root);
    });
    if (root.document && root.document.readyState === 'loading') {
      root.addEventListener('DOMContentLoaded', function() { renderWithin(root.document); bindReaderControls(); });
    } else if (root.document && root.document.readyState) {
      renderWithin(root.document);
      bindReaderControls();
    }
  }

  return {
    renderWithin: renderWithin, disposeWithin: disposeWithin,
    search: search, rotate: rotate, fitWidth: fitWidth, fitPage: fitPage,
    zoomIn: function() { return setZoom(0.25); }, zoomOut: function() { return setZoom(-0.25); },
    getZoomPercent: getZoomPercent, setZoomPercent: setZoomPercent,
    setPageWidthPreset: setPageWidthPreset,
    cancelSearch: cancelSearch, bindReaderControls: bindReaderControls
  };
});
