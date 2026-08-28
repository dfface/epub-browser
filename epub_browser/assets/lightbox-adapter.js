(function (root, createAdapter) {
  root.Fancybox = createAdapter(root.GLightbox, root);
})(typeof window !== 'undefined' ? window : globalThis, function (createLightbox, root) {
  'use strict';

  var lightbox = null;
  var bindings = [];
  var lightboxOpen = false;
  var pendingEntries = null;
  var pendingDestroy = false;
  var pendingBind = null;
  var galleryUpdatePending = false;
  var pendingOpenImage = null;

  function decodedPathIsSafe(path) {
    var value = path;
    for (var depth = 0; depth < 5; depth++) {
      if (value.indexOf('\\') !== -1 || /%2f|%5c/i.test(value)) return false;
      var segments = value.split('/');
      for (var i = 0; i < segments.length; i++) {
        if (segments[i] === '.' || segments[i] === '..') return false;
      }
      var decoded;
      try {
        decoded = decodeURIComponent(value);
      } catch (error) {
        return false;
      }
      if (decoded === value) return true;
      value = decoded;
    }
    return false;
  }

  function pathSegments(path) {
    var parts = path.split('/');
    var segments = [];
    for (var i = 0; i < parts.length; i++) {
      if (parts[i]) segments.push(parts[i]);
    }
    return segments;
  }

  function safeImageSource(image) {
    var source = image.getAttribute('src');
    if (typeof source !== 'string' || !source) return '';
    source = source.trim();
    if (/^data:image\/(?:gif|jpe?g|png|webp);base64,[a-z0-9+/=\s]+$/i.test(source)) {
      return source;
    }
    var rawPath = source.split(/[?#]/, 1)[0];
    if (!rawPath || !decodedPathIsSafe(rawPath)) return '';
    try {
      var page = new root.URL(root.location.href);
      var resolved = new root.URL(source, page);
      if (resolved.pathname.indexOf('//') !== -1) return '';
      var protocolAllowed = (
        (resolved.protocol === 'http:' || resolved.protocol === 'https:') &&
        resolved.origin === page.origin
      ) || (
        resolved.protocol === 'file:' && page.protocol === 'file:'
      );
      if (!protocolAllowed) return '';

      var pageParts = pathSegments(page.pathname);
      pageParts.pop();
      var resolvedParts = pathSegments(resolved.pathname);
      if (resolvedParts.length <= pageParts.length ||
          resolvedParts[pageParts.length] !== 'resources') {
        return '';
      }
      for (var i = 0; i < pageParts.length; i++) {
        if (resolvedParts[i] !== pageParts[i]) return '';
      }
      return resolved.href;
    } catch (error) {
      return '';
    }
    return '';
  }

  function collectImages(selector) {
    var entries = [];
    var images = root.document.querySelectorAll(selector);
    for (var i = 0; i < images.length; i++) {
      var href = safeImageSource(images[i]);
      if (href) {
        // EPUB attributes are untrusted. Only the displayed image URL crosses
        // the vendor boundary; captions and DOM nodes stay outside GLightbox.
        entries.push({
          image: images[i],
          slide: { href: href, type: 'image' },
        });
      }
    }
    return entries;
  }

  function slidesFor(entries) {
    var slides = [];
    for (var i = 0; i < entries.length; i++) slides.push(entries[i].slide);
    return slides;
  }

  function sameEntries(entries) {
    if (entries.length !== bindings.length) return false;
    for (var i = 0; i < entries.length; i++) {
      if (entries[i].image !== bindings[i].image ||
          entries[i].slide.href !== bindings[i].href) {
        return false;
      }
    }
    return true;
  }

  function clearBindings() {
    for (var i = 0; i < bindings.length; i++) {
      bindings[i].image.removeEventListener('click', bindings[i].click);
    }
    bindings = [];
  }

  function installBindings(entries) {
    clearBindings();
    for (var i = 0; i < entries.length; i++) {
      (function (entry, index) {
        var click = function (event) {
          event.preventDefault();
          if (galleryUpdatePending) {
            pendingOpenImage = entry.image;
            return;
          }
          lightbox.openAt(index);
        };
        entry.image.addEventListener('click', click);
        bindings.push({ image: entry.image, href: entry.slide.href, click: click });
      })(entries[i], i);
    }
  }

  function createInstance(entries, options) {
    var settings = {};
    var supplied = options || {};
    for (var key in supplied) {
      if (Object.prototype.hasOwnProperty.call(supplied, key)) {
        settings[key] = supplied[key];
      }
    }
    settings.selector = false;
    settings.elements = slidesFor(entries);
    var instance = createLightbox(settings);
    lightbox = instance;
    lightboxOpen = false;
    if (instance && typeof instance.on === 'function') {
      instance.on('open', function () {
        if (instance !== lightbox) return;
        lightboxOpen = true;
        var container = root.document.querySelector('.glightbox-container');
        if (container) container.classList.add('fancybox__container');
      });
      instance.on('close', function () {
        if (instance !== lightbox) return;
        lightboxOpen = false;
        if (pendingDestroy) {
          root.setTimeout(function () {
            if (instance === lightbox && pendingDestroy) finalizeDestroy(instance);
          }, 0);
          return;
        }
        if (pendingEntries) {
          var entriesToApply = pendingEntries;
          pendingEntries = null;
          galleryUpdatePending = true;
          root.setTimeout(function () {
            var latestEntries = pendingEntries || entriesToApply;
            pendingEntries = null;
            if (instance === lightbox && !pendingDestroy && sameEntries(latestEntries)) {
              instance.setElements(slidesFor(latestEntries));
            }
            galleryUpdatePending = false;
            var imageToOpen = pendingOpenImage;
            pendingOpenImage = null;
            if (imageToOpen && instance === lightbox && !pendingDestroy) {
              for (var i = 0; i < bindings.length; i++) {
                if (bindings[i].image === imageToOpen) {
                  instance.openAt(i);
                  break;
                }
              }
            }
          }, 0);
        }
      });
    }
    installBindings(entries);
    return instance;
  }

  function finalizeDestroy(instance) {
    var restart = pendingBind;
    pendingBind = null;
    pendingDestroy = false;
    pendingEntries = null;
    galleryUpdatePending = false;
    pendingOpenImage = null;
    lightbox = null;
    lightboxOpen = false;
    if (instance && typeof instance.destroy === 'function') instance.destroy();
    if (restart) createInstance(restart.entries, restart.options);
  }

  return {
    bind: function (selector, options) {
      var entries = collectImages(selector);
      if (pendingDestroy) {
        pendingBind = { entries: entries, options: options || {} };
        return lightbox;
      }
      if (!lightbox) {
        createInstance(entries, options);
      } else if (!sameEntries(entries)) {
        if (lightboxOpen || galleryUpdatePending) pendingEntries = entries;
        else lightbox.setElements(slidesFor(entries));
        installBindings(entries);
      }
      return lightbox;
    },
    destroy: function () {
      clearBindings();
      pendingEntries = null;
      pendingOpenImage = null;
      if (!lightbox || pendingDestroy) return;
      if (lightboxOpen && typeof lightbox.close === 'function') {
        pendingDestroy = true;
        lightbox.close();
        return;
      }
      finalizeDestroy(lightbox);
    },
  };
});
