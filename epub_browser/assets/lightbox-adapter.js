(function (root, createAdapter) {
  root.Fancybox = createAdapter(root.GLightbox, root);
})(typeof window !== 'undefined' ? window : globalThis, function (createLightbox, root) {
  'use strict';

  var lightbox = null;

  return {
    bind: function (selector, options) {
      if (!lightbox) {
        var settings = {};
        var supplied = options || {};
        for (var key in supplied) {
          if (Object.prototype.hasOwnProperty.call(supplied, key)) {
            settings[key] = supplied[key];
          }
        }
        settings.selector = selector;
        lightbox = createLightbox(settings);
        if (lightbox && typeof lightbox.on === 'function') {
          lightbox.on('open', function () {
            var container = root.document.querySelector('.glightbox-container');
            if (container) container.classList.add('fancybox__container');
          });
        }
      } else if (typeof lightbox.reload === 'function') {
        lightbox.reload();
      }
      return lightbox;
    },
  };
});
