(function (root, createAdapter) {
  root.Fancybox = createAdapter(root.GLightbox, root);
})(typeof window !== 'undefined' ? window : globalThis, function (createLightbox, root) {
  'use strict';

  var lightbox = null;
  var bindings = [];

  function safeImageSource(image) {
    var source = image.currentSrc || image.src;
    if (typeof source !== 'string' || !source) return '';
    if (/^data:image\/(?:gif|jpe?g|png|webp);base64,[a-z0-9+/=\s]+$/i.test(source)) {
      return source;
    }
    try {
      var base = new root.URL(root.document.baseURI);
      var bookDirectory = new root.URL('.', base).href;
      var resolved = new root.URL(source, base);
      if ((resolved.protocol === 'http:' || resolved.protocol === 'https:') &&
          resolved.origin === base.origin &&
          resolved.href.indexOf(bookDirectory) === 0) {
        return resolved.href;
      }
      if (resolved.protocol === 'file:' && base.protocol === 'file:' &&
          resolved.href.indexOf(bookDirectory) === 0) {
        return resolved.href;
      }
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
          lightbox.openAt(index);
        };
        entry.image.addEventListener('click', click);
        bindings.push({ image: entry.image, href: entry.slide.href, click: click });
      })(entries[i], i);
    }
  }

  return {
    bind: function (selector, options) {
      var entries = collectImages(selector);
      if (!lightbox) {
        var settings = {};
        var supplied = options || {};
        for (var key in supplied) {
          if (Object.prototype.hasOwnProperty.call(supplied, key)) {
            settings[key] = supplied[key];
          }
        }
        settings.selector = false;
        settings.elements = slidesFor(entries);
        lightbox = createLightbox(settings);
        if (lightbox && typeof lightbox.on === 'function') {
          lightbox.on('open', function () {
            var container = root.document.querySelector('.glightbox-container');
            if (container) container.classList.add('fancybox__container');
          });
        }
        installBindings(entries);
      } else if (!sameEntries(entries)) {
        lightbox.setElements(slidesFor(entries));
        installBindings(entries);
      }
      return lightbox;
    },
    destroy: function () {
      clearBindings();
      if (lightbox && typeof lightbox.destroy === 'function') lightbox.destroy();
      lightbox = null;
    },
  };
});
