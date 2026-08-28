'use strict';

const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const adapterPath = path.join(
  __dirname,
  '..',
  'epub_browser',
  'assets',
  'lightbox-adapter.js'
);

assert.ok(fs.existsSync(adapterPath), 'the project-owned lightbox adapter must exist');

const source = fs.readFileSync(adapterPath, 'utf8');
const chapterSource = fs.readFileSync(
  path.join(__dirname, '..', 'epub_browser', 'assets', 'chapter.js'),
  'utf8'
);

const readerSelectors = [...chapterSource.matchAll(/Fancybox\.bind\((['"])(.*?)\1/g)]
  .map((match) => match[2]);
assert.deepStrictEqual(
  readerSelectors,
  [
    '#eb-content img',
    '#eb-content img',
    '#eb-content img',
    '#eb-content img',
    '#eb-content img',
    '#eb-content img',
  ],
  'EPUB data attributes must not influence reader lightbox membership'
);
const continuousReplacement = chapterSource.slice(
  chapterSource.indexOf('function replaceContinuousChapterWindow('),
  chapterSource.indexOf('function ensureContinuousScrollBuffer(')
);
assert.match(
  continuousReplacement,
  /content\.appendChild\(chapterSection\);[\s\S]*Fancybox\.bind\('#eb-content img'/,
  'direct continuous chapter replacement must bind its new image nodes'
);
const backwardLoad = chapterSource.slice(
  chapterSource.indexOf('function loadPrevChapter('),
  chapterSource.indexOf('function saveContinuousScrollProgress(')
);
assert.match(
  backwardLoad,
  /pruneContinuousWindow\('previous', prevIdx\);[\s\S]*Fancybox\.bind\('#eb-content img'/,
  'backward prepend and prune must refresh image indexes and stale listeners'
);

function plain(value) {
  return JSON.parse(JSON.stringify(value));
}

function createImage(currentSrc, src, hostileValues = {}, rawSrc = src) {
  const listeners = new Map();
  const attributes = { src: rawSrc };
  for (const [name, value] of Object.entries(hostileValues)) {
    attributes[name] = value;
  }
  return {
    nodeName: 'IMG',
    currentSrc,
    src,
    alt: hostileValues.alt || '',
    dataset: Object.fromEntries(
      Object.entries(hostileValues)
        .filter(([name]) => name.startsWith('data-'))
        .map(([name, value]) => [
          name.slice(5).replace(/-([a-z])/g, (_, letter) => letter.toUpperCase()),
          value,
        ])
    ),
    getAttribute(name) {
      return Object.prototype.hasOwnProperty.call(attributes, name)
        ? attributes[name]
        : null;
    },
    addEventListener(name, callback) {
      const callbacks = listeners.get(name) || [];
      callbacks.push(callback);
      listeners.set(name, callbacks);
    },
    removeEventListener(name, callback) {
      const callbacks = listeners.get(name) || [];
      listeners.set(name, callbacks.filter((candidate) => candidate !== callback));
    },
    listenerCount(name) {
      return (listeners.get(name) || []).length;
    },
    click() {
      let prevented = false;
      const event = {
        preventDefault() {
          prevented = true;
        },
      };
      for (const callback of [...(listeners.get('click') || [])]) callback(event);
      return prevented;
    },
  };
}

const reservedAttributes = {
  alt: '<img src=x onerror=globalThis.captionXss=true>',
  'data-fancybox': '<script>globalThis.legacyConfigXss=true</script>',
  'data-gallery': 'attacker-controlled-gallery',
  'data-glightbox': 'type: video; href: https://evil.example/movie.mp4',
  'data-href': 'https://evil.example/external.html',
  'data-sizes': '100vw',
  'data-srcset': 'https://evil.example/tracker.png 1x',
  'data-title': '<svg onload=globalThis.titleXss=true>',
  'data-type': 'video',
  'data-video-provider': 'youtube',
  'data-description': '.attacker-controlled-description',
  'data-alt': '<img src=x onerror=globalThis.altXss=true>',
  'data-desc-position': 'left',
  'data-effect': 'evil-effect',
  'data-width': 'javascript:globalThis.widthXss=true',
  'data-height': '999999px',
  'data-content': '<script>globalThis.inlineXss=true</script>',
  'data-zoomable': 'false',
  'data-draggable': 'false',
};

const first = createImage(
  'https://evil.example/attacker/first.png',
  'https://evil.example/attacker/first.png',
  reservedAttributes,
  'resources/first.png'
);
const excludedCrossOrigin = createImage(
  'https://evil.example/youtube.com/movie.mp4#inline?goajax=true',
  'https://evil.example/fallback.png',
  reservedAttributes
);
const excludedOutsideBook = createImage(
  'https://reader.example/attacker-controlled/tracker.png',
  'https://reader.example/attacker-controlled/fallback.png',
  reservedAttributes
);
const second = createImage(
  'https://evil.example/attacker/second.webp',
  'https://evil.example/attacker/second.webp',
  reservedAttributes,
  'resources/second.webp'
);
const encodedAliases = [
  'resources%2Fslash.png',
  'resources%5Cbackslash.png',
  'resources/%2E%2E/dot-segment.png',
  'resources/%252E%252E%252Fdouble-encoded.png',
  'resources/%252Fdouble-slash.png',
  'resources//duplicate-separator.png',
].map((rawSrc) => createImage(
  'https://reader.example/book/demo/resources/apparently-safe.png',
  'https://reader.example/book/demo/resources/apparently-safe.png',
  reservedAttributes,
  rawSrc
));
let selectedImages = [
  first,
  excludedCrossOrigin,
  excludedOutsideBook,
  ...encodedAliases,
  second,
];
const compatibilityClasses = [];
const constructorCalls = [];
const instances = [];
const timers = [];

function flushTimers() {
  while (timers.length) timers.shift()();
}

const context = {
  URL,
  setTimeout(callback) {
    timers.push(callback);
  },
  location: {
    href: 'https://reader.example/book/demo/chapter_0.html',
  },
  document: {
    baseURI: 'https://evil.example/attacker/',
    querySelectorAll(selector) {
      assert.strictEqual(selector, '#eb-content img');
      return selectedImages;
    },
    querySelector(selector) {
      assert.strictEqual(selector, '.glightbox-container');
      return {
        classList: {
          add(name) {
            compatibilityClasses.push(name);
          },
        },
      };
    },
  },
  GLightbox(options) {
    constructorCalls.push(options);
    const events = {};
    const instance = {
      setElementsCalls: [],
      openAtCalls: [],
      destroyCount: 0,
      closeCount: 0,
      activeIndex: null,
      lightboxOpen: false,
      destroyedWhileOpen: false,
      setElements(elements) {
        this.setElementsCalls.push(elements);
        if (this.lightboxOpen) this.activeIndex = 0;
      },
      openAt(index) {
        this.openAtCalls.push(index);
        this.activeIndex = index;
        this.lightboxOpen = true;
        if (events.open) events.open();
      },
      close() {
        this.closeCount += 1;
      },
      finishClose() {
        this.lightboxOpen = false;
        if (events.close) events.close();
      },
      destroy() {
        if (this.lightboxOpen) this.destroyedWhileOpen = true;
        this.destroyCount += 1;
      },
      on(name, callback) {
        events[name] = callback;
      },
      trigger(name) {
        events[name]();
      },
    };
    instances.push(instance);
    return instance;
  },
};
context.globalThis = context;
vm.createContext(context);
vm.runInContext(source, context, { filename: adapterPath });

assert.strictEqual(typeof context.Fancybox.bind, 'function');

const firstInstance = context.Fancybox.bind('#eb-content img', {
  touchNavigation: false,
});
assert.strictEqual(firstInstance, instances[0]);
assert.strictEqual(constructorCalls.length, 1);
assert.deepStrictEqual(plain(constructorCalls[0]), {
  touchNavigation: false,
  selector: false,
  elements: [
    {
      href: 'https://reader.example/book/demo/resources/first.png',
      type: 'image',
    },
    {
      href: 'https://reader.example/book/demo/resources/second.webp',
      type: 'image',
    },
  ],
});
const serializedOptions = JSON.stringify(constructorCalls[0]);
const serializedSlides = JSON.stringify(constructorCalls[0].elements);
for (const value of Object.values(reservedAttributes)) {
  assert.ok(
    !serializedSlides.includes(value),
    `GLightbox slides must not contain EPUB-controlled value: ${value}`
  );
}
assert.ok(!serializedOptions.includes('cdn.plyr.io'));
assert.strictEqual(excludedCrossOrigin.listenerCount('click'), 0);
assert.strictEqual(excludedOutsideBook.listenerCount('click'), 0);
for (const encodedAlias of encodedAliases) {
  assert.strictEqual(encodedAlias.listenerCount('click'), 0);
}

assert.strictEqual(first.listenerCount('click'), 1);
assert.strictEqual(second.listenerCount('click'), 1);
assert.strictEqual(second.click(), true);
assert.deepStrictEqual(firstInstance.openAtCalls, [1]);
assert.strictEqual(firstInstance.activeIndex, 1);
assert.deepStrictEqual(compatibilityClasses, ['fancybox__container']);

assert.strictEqual(
  context.Fancybox.bind('#eb-content img'),
  firstInstance,
  'later binds must reuse the reader lightbox'
);
assert.strictEqual(constructorCalls.length, 1);
assert.strictEqual(first.listenerCount('click'), 1, 'duplicate binds must not stack listeners');
assert.strictEqual(second.listenerCount('click'), 1, 'duplicate binds must not stack listeners');

const appended = createImage(
  'https://reader.example/book/demo/resources/appended.avif',
  'https://reader.example/book/demo/resources/appended-fallback.png',
  reservedAttributes
);
selectedImages = [first, appended];
context.Fancybox.bind('#eb-content img');
assert.strictEqual(second.listenerCount('click'), 0, 'AJAX replacement must unbind removed images');
assert.strictEqual(first.listenerCount('click'), 1);
assert.strictEqual(appended.listenerCount('click'), 1);
assert.strictEqual(firstInstance.activeIndex, 1, 'open rebinding must not jump to slide zero');
assert.deepStrictEqual(
  firstInstance.setElementsCalls,
  [],
  'GLightbox gallery replacement must wait for the close event'
);
firstInstance.finishClose();
assert.deepStrictEqual(
  firstInstance.setElementsCalls,
  [],
  'gallery replacement must wait until GLightbox finishes its close callback'
);
assert.strictEqual(appended.click(), true);
assert.deepStrictEqual(
  firstInstance.openAtCalls,
  [1],
  'clicks during close-time gallery replacement must wait for current indexes'
);
flushTimers();
assert.deepStrictEqual(plain(firstInstance.setElementsCalls), [
  [
    {
      href: 'https://reader.example/book/demo/resources/first.png',
      type: 'image',
    },
    {
      href: 'https://reader.example/book/demo/resources/appended-fallback.png',
      type: 'image',
    },
  ],
]);
assert.deepStrictEqual(firstInstance.openAtCalls, [1, 1]);

assert.strictEqual(typeof context.Fancybox.destroy, 'function');
context.Fancybox.destroy();
context.Fancybox.destroy();
assert.strictEqual(first.listenerCount('click'), 0);
assert.strictEqual(appended.listenerCount('click'), 0);
assert.strictEqual(firstInstance.closeCount, 1, 'destroy must request one asynchronous close');
assert.strictEqual(firstInstance.destroyCount, 0, 'open GLightbox must not be destroyed before close');
assert.strictEqual(firstInstance.destroyedWhileOpen, false);

selectedImages = [second];
assert.strictEqual(context.Fancybox.bind('#eb-content img'), firstInstance);
assert.strictEqual(constructorCalls.length, 1, 'reinitialization must wait for the closing instance');
assert.strictEqual(second.listenerCount('click'), 0);
firstInstance.finishClose();
assert.strictEqual(firstInstance.destroyCount, 0, 'close handlers must finish before destruction');
assert.strictEqual(constructorCalls.length, 1);
flushTimers();
assert.strictEqual(firstInstance.destroyCount, 1, 'destroy must finalize after close');
assert.strictEqual(firstInstance.destroyedWhileOpen, false);
assert.strictEqual(constructorCalls.length, 2, 'binding after destroy must create a fresh instance');
assert.strictEqual(second.listenerCount('click'), 1);

console.log('lightbox adapter tests passed');
