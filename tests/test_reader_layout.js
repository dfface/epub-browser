const test = require('node:test');
const assert = require('node:assert/strict');

const {
  applyDesktopChapterSidebarAutoHide,
  applyDesktopToolbarAutoHide,
  applyPageWidth,
  allowsReaderNavigationEvent,
  chapterNavigationPresentation,
  bookNavigationEntries,
  createNavigationBehaviorController,
  desktopChapterSidebarWidth,
  getPaginationPageWidth,
  getPaginationScrollLeft,
  paginationWidthChanged,
  initNavigationBehavior,
  normalizeNavigationBehavior,
  normalizePageWidth,
  readingPreferenceEnabled,
  syncChapterTocAvailability,
} = require('../epub_browser/assets/reader-layout.js');

test('PDF chapter navigation uses the same outline title as the book page', () => {
  const translate = (key, params) => key === 'pdf.page' ? `第 ${params.number} 页` : key;
  const presentation = chapterNavigationPresentation({
    title: 'Page 2',
    chapter_index: 1,
    page_label: '2',
    outline_labels: ['Part I', 'Opening'],
  }, true, translate);

  assert.deepEqual(presentation, {
    title: 'Part I · Opening',
    outlineLabels: [],
  });
});

class FakeClassList {
  constructor() {
    this.values = new Set();
  }

  add(value) {
    this.values.add(value);
  }

  remove(...values) {
    values.forEach(value => this.values.delete(value));
  }

  toggle(value, force) {
    if (force === true) {
      this.values.add(value);
      return true;
    }
    if (force === false) {
      this.values.delete(value);
      return false;
    }
    if (this.values.has(value)) {
      this.values.delete(value);
      return false;
    }
    this.values.add(value);
    return true;
  }

  contains(value) {
    return this.values.has(value);
  }
}

test('desktop toolbar auto-hide preference changes only the toolbar presentation state', () => {
  const body = new FakeElement();
  const toolbar = new FakeElement();
  toolbar.setAttribute('aria-hidden', 'false');
  const documentObject = {
    body,
    querySelector(selector) {
      return selector === '.reader-toolbar.top-controls' ? toolbar : null;
    },
  };

  assert.equal(applyDesktopToolbarAutoHide(documentObject, true), true);
  assert.equal(body.classList.contains('desktop-toolbar-auto-hide'), true);
  assert.equal(toolbar.getAttribute('aria-hidden'), 'false');

  assert.equal(applyDesktopToolbarAutoHide(documentObject, false), false);
  assert.equal(body.classList.contains('desktop-toolbar-auto-hide'), false);
  assert.equal(toolbar.getAttribute('aria-hidden'), 'false');
});

test('chapter sidebar auto-hide only activates while the desktop sidebar is shown', () => {
  const body = new FakeElement();
  const toggle = new FakeElement();
  const documentObject = {
    body,
    getElementById(id) {
      return id === 'autoHideDesktopChapterSidebarToggle' ? toggle : null;
    },
  };

  assert.equal(applyDesktopChapterSidebarAutoHide(documentObject, false, true), false);
  assert.equal(body.classList.contains('desktop-chapter-sidebar-auto-hide'), false);
  assert.equal(toggle.disabled, true);
  assert.equal(toggle.getAttribute('aria-disabled'), 'true');

  assert.equal(applyDesktopChapterSidebarAutoHide(documentObject, true, true), true);
  assert.equal(body.classList.contains('desktop-chapter-sidebar-auto-hide'), true);
  assert.equal(toggle.disabled, false);
  assert.equal(toggle.getAttribute('aria-disabled'), 'false');

  assert.equal(applyDesktopChapterSidebarAutoHide(documentObject, true, false), false);
  assert.equal(body.classList.contains('desktop-chapter-sidebar-auto-hide'), false);
});

class FakeElement {
  constructor() {
    this.attributes = new Map();
    this.classList = new FakeClassList();
    this.disabled = false;
    this.hidden = false;
    this.listeners = new Map();
    this.style = {
      values: new Map(),
      setProperty: (name, value) => this.style.values.set(name, value),
    };
  }

  setAttribute(name, value) {
    this.attributes.set(name, String(value));
  }

  getAttribute(name) {
    return this.attributes.get(name);
  }

  addEventListener(type, listener) {
    this.listeners.set(type, listener);
  }

  contains(element) {
    return element === this.focusedChild;
  }

  getBoundingClientRect() {
    return { height: 68 };
  }
}

function fakeDocument() {
  const elements = {
    chapterOutlineTab: new FakeElement(),
    tocFloating: new FakeElement(),
  };
  elements.tocFloating.classList.add('active');
  return {
    elements,
    getElementById(id) {
      return elements[id] || null;
    },
  };
}

test('normalizes page-width presets and applies their exact reading width', () => {
  const properties = new Map();
  const root = {
    style: {
      setProperty(name, value) {
        properties.set(name, value);
      },
    },
    setAttribute(name, value) {
      this[name] = value;
    },
  };

  assert.equal(normalizePageWidth('1'), '1');
  assert.equal(normalizePageWidth('4'), '4');
  assert.equal(normalizePageWidth('invalid'), '3');
  assert.equal(applyPageWidth(root, '2'), '2');
  assert.equal(properties.get('--reader-page-width'), '820px');
  assert.equal(root['data-reader-page-width'], '2');
});

test('desktop chapter sidebar only uses width the page leaves over', () => {
  // Page width + outer offset + two gutters + the 220px minimum is the floor.
  assert.equal(desktopChapterSidebarWidth(1287, 1000), 0);
  assert.equal(desktopChapterSidebarWidth(1288, 1000), 220);
  assert.equal(desktopChapterSidebarWidth(1360, 1000), 292);
  // Surplus widens the list, but never past 320px.
  assert.equal(desktopChapterSidebarWidth(1462, 1000), 320);
  assert.equal(desktopChapterSidebarWidth(1920, 1000), 320);
  // A wider reading column needs a wider window before the sidebar fits.
  assert.equal(desktopChapterSidebarWidth(1462, 1200), 0);
  assert.equal(desktopChapterSidebarWidth(1488, 1200), 220);
  // The narrowest preset makes the sidebar available from 968px.
  assert.equal(desktopChapterSidebarWidth(967, 680), 0);
  assert.equal(desktopChapterSidebarWidth(968, 680), 220);
  assert.equal(desktopChapterSidebarWidth(1000, 680), 252);
  assert.equal(desktopChapterSidebarWidth(undefined, 1000), 0);
});

test('pagination keeps the container fractional width as its page stride', () => {
  const container = {
    clientWidth: 786,
    getBoundingClientRect() {
      return { width: 787.1953125 };
    },
  };

  assert.equal(getPaginationPageWidth(container), 787.1953125);
  assert.equal(getPaginationScrollLeft(11, getPaginationPageWidth(container)), 8659);
});

test('pagination refreshes only when the canvas width has materially settled', () => {
  assert.equal(paginationWidthChanged(786.96875, 787.1953125), true);
  assert.equal(paginationWidthChanged(787.1953125, 787.1953125), false);
  assert.equal(paginationWidthChanged(787.1953125, 787.2), false);
});

test('outline tab is available only for ordinary EPUB layouts', () => {
  const document=fakeDocument();
  for(const [continuous,pdf,hidden] of [[false,false,false],[true,false,true],[false,true,true],[false,false,false]]) {
    syncChapterTocAvailability(document,continuous,pdf);
    const tab=document.elements.chapterOutlineTab;
    assert.equal(tab.hidden,hidden);
    assert.equal(tab.disabled,hidden);
    assert.equal(tab.getAttribute('aria-hidden'),String(hidden));
  }
});

test('keyboard navigation preferences default on and only explicit false disables them', () => {
  assert.equal(readingPreferenceEnabled(null), true);
  assert.equal(readingPreferenceEnabled(undefined), true);
  assert.equal(readingPreferenceEnabled('true'), true);
  assert.equal(readingPreferenceEnabled('false'), false);
});

test('arrow and Space preferences gate their own keys without gating ArrowDown', () => {
  const event = key => ({ key, target: { tagName: 'DIV' } });

  assert.equal(allowsReaderNavigationEvent(event('ArrowLeft'), false, true), false);
  assert.equal(allowsReaderNavigationEvent(event('ArrowRight'), false, true), false);
  assert.equal(allowsReaderNavigationEvent(event(' '), true, false), false);
  assert.equal(allowsReaderNavigationEvent(event('Space'), true, false), false);
  assert.equal(allowsReaderNavigationEvent(event('ArrowRight'), true, false), true);
  assert.equal(allowsReaderNavigationEvent(event(' '), false, true), true);
  assert.equal(allowsReaderNavigationEvent(event('ArrowDown'), false, false), true);
});

test('reader keyboard navigation ignores editing targets, prevented events, and modifiers', () => {
  const editableTargets = [
    { tagName: 'INPUT' },
    { tagName: 'TEXTAREA', className: 'annotation-note-input' },
    { tagName: 'SELECT' },
    { tagName: 'DIV', isContentEditable: true },
    {
      tagName: 'SPAN',
      getAttribute(name) { return name === 'contenteditable' ? 'plaintext-only' : null; },
    },
  ];
  editableTargets.forEach(target => {
    const event = { key: 'ArrowRight', target, composedPath: () => [target] };
    assert.equal(allowsReaderNavigationEvent(event, true, true), false, target.tagName);
  });

  const editableAncestor = { tagName: 'DIV', isContentEditable: true };
  const nestedTarget = { tagName: 'SPAN' };
  assert.equal(allowsReaderNavigationEvent({
    key: ' ',
    target: nestedTarget,
    composedPath: () => [nestedTarget, editableAncestor],
  }, true, true), false);

  for (const property of ['defaultPrevented', 'altKey', 'ctrlKey', 'metaKey', 'shiftKey']) {
    assert.equal(allowsReaderNavigationEvent({
      key: 'ArrowLeft',
      target: { tagName: 'DIV' },
      [property]: true,
    }, true, true), false, property);
  }
});

test('reader keyboard navigation leaves interactive controls and dialogs alone', () => {
  for (const tagName of ['BUTTON', 'A', 'SUMMARY', 'DIALOG']) {
    const target = { tagName };
    assert.equal(allowsReaderNavigationEvent({
      key: ' ',
      target,
      composedPath: () => [target],
    }, true, true), false, tagName);
  }

  const target = { tagName: 'SPAN' };
  const dialog = {
    tagName: 'DIV',
    getAttribute(name) { return name === 'role' ? 'dialog' : null; },
  };
  assert.equal(allowsReaderNavigationEvent({
    key: 'ArrowRight',
    target,
    composedPath: () => [target, dialog],
  }, true, true), false);
});

test('navigation behavior defaults to normal and persists an explicit choice', () => {
  const values = new Map();
  const header = new FakeElement();
  const root = new FakeElement();
  const controller = createNavigationBehaviorController({
    header,
    rootElement: root,
    documentObject: { activeElement: null },
    storage: {
      getItem: key => values.has(key) ? values.get(key) : null,
      setItem: (key, value) => values.set(key, String(value)),
    },
  });

  assert.equal(normalizeNavigationBehavior(null), 'normal');
  assert.equal(normalizeNavigationBehavior('unknown'), 'normal');
  assert.equal(controller.getMode(), 'normal');
  assert.equal(root.getAttribute('data-navigation-behavior'), 'normal');
  assert.deepEqual([...header.classList.values], ['is-navigation-normal']);

  controller.setMode('sticky');
  assert.equal(values.get('navigation_bar_behavior'), 'sticky');
  assert.equal(root.getAttribute('data-navigation-behavior'), 'sticky');
  assert.deepEqual([...header.classList.values], ['is-navigation-sticky']);

  controller.setMode('auto-hide');
  assert.deepEqual([...header.classList.values], ['is-navigation-auto-hide']);

  controller.setMode('normal');
  assert.deepEqual([...header.classList.values], ['is-navigation-normal']);
});

test('auto-hide seeds direction tracking from a restored scroll position', () => {
  const header = new FakeElement();
  const root = new FakeElement();
  const documentObject = { activeElement: null };
  const controller = createNavigationBehaviorController({
    header,
    rootElement: root,
    documentObject,
    initialScrollY: 500,
    storage: { getItem: () => 'auto-hide', setItem() {} },
  });

  controller.handleScroll(497);
  assert.equal(header.classList.contains('is-navigation-hidden'), false);

  controller.handleScroll(494);
  assert.equal(header.classList.contains('is-navigation-hidden'), false);
});

test('navigation bootstrap seeds restored window scroll before the first event', () => {
  const header = new FakeElement();
  const rootElement = new FakeElement();
  rootElement.scrollTop = 500;
  const documentObject = {
    activeElement: null,
    documentElement: rootElement,
    getElementById() { return null; },
    querySelector(selector) { return selector === '.app-header' ? header : null; },
    querySelectorAll() { return []; },
  };
  const rootListeners = new Map();
  const root = {
    document: documentObject,
    localStorage: { getItem: () => 'auto-hide', setItem() {} },
    pageYOffset: 500,
    addEventListener(type, listener) { rootListeners.set(type, listener); },
    requestAnimationFrame(callback) { callback(); },
  };

  initNavigationBehavior(root);
  root.pageYOffset = 497;
  rootListeners.get('scroll')();

  assert.equal(header.classList.contains('is-navigation-hidden'), false);
});

test('auto-hide accumulates slow motion in both directions', () => {
  const header = new FakeElement();
  const controller = createNavigationBehaviorController({
    header,
    rootElement: new FakeElement(),
    documentObject: { activeElement: null },
    initialScrollY: 100,
    storage: { getItem: () => 'auto-hide', setItem() {} },
  });

  controller.handleScroll(103);
  assert.equal(header.classList.contains('is-navigation-hidden'), false);
  controller.handleScroll(106);
  assert.equal(header.classList.contains('is-navigation-hidden'), true);

  controller.handleScroll(103);
  assert.equal(header.classList.contains('is-navigation-hidden'), true);
  controller.handleScroll(100);
  assert.equal(header.classList.contains('is-navigation-hidden'), false);
});

test('auto-hide resets accumulated motion when scroll direction reverses', () => {
  const header = new FakeElement();
  const controller = createNavigationBehaviorController({
    header,
    rootElement: new FakeElement(),
    documentObject: { activeElement: null },
    initialScrollY: 100,
    storage: { getItem: () => 'auto-hide', setItem() {} },
  });

  controller.handleScroll(103);
  controller.handleScroll(101);
  controller.handleScroll(104);
  assert.equal(header.classList.contains('is-navigation-hidden'), false);
  controller.handleScroll(107);
  assert.equal(header.classList.contains('is-navigation-hidden'), true);
});

test('auto-hide always reveals within the header top zone', () => {
  const header = new FakeElement();
  const controller = createNavigationBehaviorController({
    header,
    rootElement: new FakeElement(),
    documentObject: { activeElement: null },
    initialScrollY: 70,
    storage: { getItem: () => 'auto-hide', setItem() {} },
  });

  controller.handleScroll(76);
  assert.equal(header.classList.contains('is-navigation-hidden'), true);
  controller.handleScroll(72);
  assert.equal(header.classList.contains('is-navigation-hidden'), true);
  controller.handleScroll(68);
  assert.equal(header.classList.contains('is-navigation-hidden'), false);
});

test('focus and an expanded locale popup reset motion and keep navigation visible', () => {
  const header = new FakeElement();
  const localeToggle = new FakeElement();
  const documentObject = {
    activeElement: null,
    getElementById(id) {
      return id === 'localeToggle' ? localeToggle : null;
    },
  };
  const controller = createNavigationBehaviorController({
    header,
    rootElement: new FakeElement(),
    documentObject,
    initialScrollY: 100,
    storage: { getItem: () => 'auto-hide', setItem() {} },
  });

  controller.handleScroll(103);
  header.focusedChild = {};
  documentObject.activeElement = header.focusedChild;
  controller.handleScroll(106);
  assert.equal(header.classList.contains('is-navigation-hidden'), false);

  documentObject.activeElement = null;
  controller.handleScroll(109);
  assert.equal(header.classList.contains('is-navigation-hidden'), false);

  localeToggle.setAttribute('aria-expanded', 'true');
  controller.handleScroll(112);
  controller.handleScroll(115);
  assert.equal(header.classList.contains('is-navigation-hidden'), false);

  localeToggle.setAttribute('aria-expanded', 'false');
  controller.handleScroll(118);
  assert.equal(header.classList.contains('is-navigation-hidden'), false);
  controller.handleScroll(121);
  assert.equal(header.classList.contains('is-navigation-hidden'), true);
});

test('mode changes reset motion at the current non-zero scroll position', () => {
  let scrollY = 200;
  const header = new FakeElement();
  const controller = createNavigationBehaviorController({
    header,
    rootElement: new FakeElement(),
    documentObject: { activeElement: null },
    initialScrollY: scrollY,
    getScrollY: () => scrollY,
    storage: { getItem: () => 'auto-hide', setItem() {} },
  });

  scrollY = 203;
  controller.handleScroll(scrollY);
  controller.setMode('sticky');
  controller.setMode('auto-hide');

  scrollY = 206;
  controller.handleScroll(scrollY);
  assert.equal(header.classList.contains('is-navigation-hidden'), false);
  scrollY = 209;
  controller.handleScroll(scrollY);
  assert.equal(header.classList.contains('is-navigation-hidden'), true);
});

test('reading appearance restores preferences, persists choices and restores book alignment', () => {
  const { initContentPreferences } = require('../epub_browser/assets/reader-layout.js');
  const values = new Map([['reader_text_alignment', 'justify']]);
  const attributes = {};
  function control() {
    return { addEventListener(type, listener) { this.change = listener; } };
  }
  const alignment = control();
  const imageNotes = control();
  let changes = 0;
  const root = {
    localStorage: { getItem: key => values.get(key) || null, setItem: (key, value) => values.set(key, value) },
    document: {
      getElementById: id => ({ textAlignmentSelect: alignment, imageNoteEntrancesToggle: imageNotes })[id],
      documentElement: { setAttribute: (key, value) => { attributes[key] = value; } },
      dispatchEvent() { changes++; },
    },
    CustomEvent: function(type) { this.type = type; },
  };
  initContentPreferences(root);
  assert.equal(alignment.value, 'justify');
  assert.equal(attributes['data-reader-text-alignment'], 'justify');
  assert.equal(imageNotes.checked, false);
  imageNotes.checked = true;
  imageNotes.change();
  assert.equal(values.get('show_image_note_entrances'), 'true');
  assert.equal(attributes['data-image-note-entrances'], 'true');
  alignment.value = 'default';
  alignment.change();
  assert.equal(values.get('reader_text_alignment'), 'default');
  assert.equal(attributes['data-reader-text-alignment'], 'default');
  assert.equal(changes, 1);
  initContentPreferences(root);
  assert.equal(imageNotes.checked, true);
});


test('mobile toolbar can remain visible and resume directional hiding without a scroll jump', () => {
  const { createMobileToolbarController } = require('../epub_browser/assets/reader-layout.js');
  const states = [];
  const controller = createMobileToolbarController({
    scrollTop: 400,
    render: visible => states.push(visible),
  });
  controller.onScroll(420);
  assert.equal(states.at(-1), false);
  controller.setAlwaysVisible(true, 420);
  assert.equal(states.at(-1), true);
  controller.onScroll(600);
  assert.equal(states.at(-1), true);
  controller.setAlwaysVisible(false, 600);
  assert.equal(states.at(-1), true);
  controller.onScroll(620);
  assert.equal(states.at(-1), false);
  controller.onScroll(610);
  assert.equal(states.at(-1), true);
});

test('fixed mobile shortcuts keep their slots and disable Top only at the top', () => {
  const { mobileToolbarShortcutState } = require('../epub_browser/assets/reader-layout.js');
  assert.deepEqual(mobileToolbarShortcutState(true, 0, 600, false, false),
    { visible: true, topDisabled: true });
  assert.deepEqual(mobileToolbarShortcutState(true, 20, 600, false, true),
    { visible: true, topDisabled: false });
  assert.deepEqual(mobileToolbarShortcutState(true, 0, 600, true, false),
    { visible: true, topDisabled: true });
  assert.deepEqual(mobileToolbarShortcutState(false, 20, 600, false, false),
    { visible: false, topDisabled: false });
  assert.deepEqual(mobileToolbarShortcutState(false, 700, 600, false, false),
    { visible: true, topDisabled: false });
  assert.deepEqual(mobileToolbarShortcutState(false, 700, 600, false, true),
    { visible: false, topDisabled: false });
  assert.deepEqual(mobileToolbarShortcutState(false, 700, 600, true, false),
    { visible: false, topDisabled: false });
});

test('reader source TOC preserves groups, deep levels and distinct chapter fragments', () => {
  const fs = require('node:fs');
  const vm = require('node:vm');
  const source = fs.readFileSync(require.resolve('../epub_browser/assets/chapter.js'), 'utf8');
  const start = source.indexOf('    function loadBookHomeToc()');
  const end = source.indexOf('    function setBookTocActiveChapter', start);
  function element(tag) {
    return {
      tag, children: [], attributes: {}, style: { setProperty(k, v) { this[k] = String(v); } },
      classList: { add() {} },
      appendChild(child) { this.children.push(child); },
      setAttribute(k, v) { this.attributes[k] = String(v); },
      addEventListener() {},
    };
  }
  const list = element('ul');
  const data = [
    { title: 'Part', kind: 'section', level: 0 },
    { title: 'Child', kind: 'section', level: 1 },
    { title: 'Deep target', kind: 'chapter', level: 5, chapter_index: 0, chapter_file: 'chapter_0.html', anchor: 'one' },
    { title: 'Second target', kind: 'chapter', level: 1, chapter_index: 0, chapter_file: 'chapter_0.html', anchor: 'two' },
  ];
  const context = {
    window: { location: { pathname: '/book/id/chapter_0.html' }, EpubBrowserURL: { publicPath: x => x },
      EpubReaderLayout: { chapterNavigationPresentation, bookNavigationEntries, initBookTocTree: () => ({reveal() {}}) } },
    document: { getElementById: () => list, createElement: element, dispatchEvent() {} },
    requestBookContent(url, onSuccess) {
      assert.equal(url, '/book/id/toc.json');
      onSuccess(JSON.stringify(data));
    },
    localStorage: {getItem: () => null, setItem() {}},
    i18n: { t: x => x }, CustomEvent: function() {},
    setBookTocActiveChapter() {}, visibleChapterIndex: 0,
  };
  vm.runInNewContext(source.slice(start, end) + '\nloadBookHomeToc();', context);
  assert.deepEqual(list.children.map(x => x.attributes['data-toc-level']), ['0', '1', '5', '1']);
  assert.deepEqual(list.children.map(x => x.style['--toc-depth']), ['0', '1', '5', '1']);
  assert.equal(list.children[0].children[0].tag, 'span');
  assert.equal(list.children[0].children[0].textContent, 'Part');
  assert.equal(list.children[2].children[0].href, '/book/id/chapter_0.html#one');
  assert.equal(list.children[3].children[0].href, '/book/id/chapter_0.html#two');
});

test('PDF book navigation lists only outline entries while EPUB keeps all entries',()=>{
  const entries=[
    {chapter_index:0,page_label:'1',outline_labels:[]},
    {chapter_index:2,page_label:'3',outline_labels:['Opening']},
    {chapter_index:3,page_label:'4',outline_labels:['  ']},
  ];
  assert.deepEqual(bookNavigationEntries(entries,true),[entries[1]]);
  assert.deepEqual(bookNavigationEntries(entries,false),entries);
  assert.deepEqual(bookNavigationEntries([entries[0]],true),[]);
});
