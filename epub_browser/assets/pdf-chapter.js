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

  function translate(key) {
    var i18n = root.EpubBrowserI18n;
    return i18n && typeof i18n.t === 'function' ? i18n.t(key) : key;
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
    return {
      documentUrl: documentURL.href,
      moduleUrl: trustedAssetURL(config.pdfjsModuleUrl, false),
      workerUrl: trustedAssetURL(config.pdfjsWorkerUrl, true),
      zoom: Math.max(0.25, Math.min(4, Number(config.zoom) || 1)),
      rotation: ((Math.round((Number(config.rotation) || 0) / 90) * 90) % 360 + 360) % 360,
      fit: config.fit === 'page' || config.fitMode === 'page' ? 'page' : 'width'
    };
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
        stopAtErrors: true
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
    status.setAttribute('aria-live', role === 'alert' ? 'assertive' : 'polite');
    status.textContent = translate(key);
    node.replaceChildren(status);
    return status;
  }

  function cancelRendering(record) {
    record.generation += 1;
    if (record.renderTask && typeof record.renderTask.cancel === 'function') record.renderTask.cancel();
    if (record.textLayer && typeof record.textLayer.cancel === 'function') record.textLayer.cancel();
    record.renderTask = null;
    record.textLayer = null;
  }

  async function paintNode(node, isRerender) {
    var record = records.get(node);
    if (!record || record.disposed) return;
    if (isRerender) cancelRendering(record);
    var generation = ++record.generation;
    node.setAttribute('data-pdf-rendered', 'pending');
    node.setAttribute('aria-busy', 'true');
    statusNode(node, 'status', 'pdf.loadingPage');
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
      var availableWidth = Math.max(1, bounds.width || node.clientWidth || baseViewport.width);
      var availableHeight = Math.max(1, bounds.height || node.clientHeight || baseViewport.height);
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
      var textLayerNode = node.ownerDocument.createElement('div');
      textLayerNode.className = 'pdf-page-text-layer textLayer';
      textLayerNode.style.setProperty('--total-scale-factor', viewport.scale);
      node.style.minHeight = viewport.height + 'px';
      node.replaceChildren(canvas, textLayerNode);
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
        if (record.textLayer === textLayer) record.textLayer = null;
      } else {
        textLayerNode.setAttribute('aria-label', translate('pdf.textUnavailable'));
      }
      if (record.disposed || generation !== record.generation) return;
      node.setAttribute('data-pdf-rendered', 'complete');
      node.setAttribute('aria-busy', 'false');
    } catch (error) {
      if (record.disposed || generation !== record.generation) return;
      node.setAttribute('data-pdf-rendered', 'error');
      node.setAttribute('aria-busy', 'false');
      statusNode(node, 'alert', 'reader.chapterLoadFailed');
    }
  }

  function prepareNode(node) {
    var record = records.get(node);
    if (record && !record.disposed) return record.promise || Promise.resolve();
    var width = Number(node.getAttribute('data-pdf-page-width'));
    var height = Number(node.getAttribute('data-pdf-page-height'));
    if (width > 0 && height > 0) node.style.aspectRatio = width + ' / ' + height;
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
    if (typeof root.ResizeObserver === 'function') {
      record.resizeObserver = new root.ResizeObserver(function() {
        if (record.disposed || !record.started || record.renderedWidth === null) return;
        var bounds = node.getBoundingClientRect();
        var width = Math.max(1, bounds.width || node.clientWidth || 1);
        var height = Math.max(1, bounds.height || node.clientHeight || 1);
        var widthChanged = Math.abs(width - record.renderedWidth) > 0.5;
        var heightChanged = record.fit === 'page' && Math.abs(height - record.renderedHeight) > 0.5;
        if (widthChanged || heightChanged) record.promise = paintNode(node, true);
      });
      record.resizeObserver.observe(node);
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
  }

  function disposeWithin(rootNode) {
    nodesWithin(rootNode).forEach(disposeNode);
  }

  if (root && typeof root.addEventListener === 'function') {
    root.addEventListener('epub-browser:chapter-content-added', function(event) {
      renderWithin(event.detail && event.detail.root).catch(function() {});
    });
    root.addEventListener('epub-browser:chapter-content-removed', function(event) {
      disposeWithin(event.detail && event.detail.root);
    });
    if (root.document && root.document.readyState === 'loading') {
      root.addEventListener('DOMContentLoaded', function() { renderWithin(root.document); });
    } else if (root.document && root.document.readyState) {
      renderWithin(root.document);
    }
  }

  return { renderWithin: renderWithin, disposeWithin: disposeWithin };
});
