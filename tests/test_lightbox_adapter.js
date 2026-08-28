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
  ],
  'EPUB data attributes must not influence reader lightbox membership'
);

function plain(value) {
  return JSON.parse(JSON.stringify(value));
}

function createImage(currentSrc, src, hostileValues = {}) {
  const listeners = new Map();
  const attributes = {};
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
  'https://reader.example/book/demo/resources/first.png',
  'https://reader.example/book/demo/resources/ignored-fallback.jpg',
  reservedAttributes
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
  '',
  'https://reader.example/book/demo/resources/second.webp',
  reservedAttributes
);
let selectedImages = [first, excludedCrossOrigin, excludedOutsideBook, second];
const compatibilityClasses = [];
const constructorCalls = [];
const instances = [];

const context = {
  URL,
  document: {
    baseURI: 'https://reader.example/book/demo/chapter_0.html',
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
      setElements(elements) {
        this.setElementsCalls.push(elements);
      },
      openAt(index) {
        this.openAtCalls.push(index);
      },
      destroy() {
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

assert.strictEqual(first.listenerCount('click'), 1);
assert.strictEqual(second.listenerCount('click'), 1);
assert.strictEqual(second.click(), true);
assert.deepStrictEqual(firstInstance.openAtCalls, [1]);
firstInstance.trigger('open');
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
assert.deepStrictEqual(plain(firstInstance.setElementsCalls), [
  [
    {
      href: 'https://reader.example/book/demo/resources/first.png',
      type: 'image',
    },
    {
      href: 'https://reader.example/book/demo/resources/appended.avif',
      type: 'image',
    },
  ],
]);
assert.strictEqual(appended.click(), true);
assert.deepStrictEqual(firstInstance.openAtCalls, [1, 1]);

assert.strictEqual(typeof context.Fancybox.destroy, 'function');
context.Fancybox.destroy();
context.Fancybox.destroy();
assert.strictEqual(first.listenerCount('click'), 0);
assert.strictEqual(appended.listenerCount('click'), 0);
assert.strictEqual(firstInstance.destroyCount, 1, 'destroy must be idempotent');

selectedImages = [second];
assert.strictEqual(context.Fancybox.bind('#eb-content img'), instances[1]);
assert.strictEqual(constructorCalls.length, 2, 'binding after destroy must create a fresh instance');
assert.strictEqual(second.listenerCount('click'), 1);

console.log('lightbox adapter tests passed');
