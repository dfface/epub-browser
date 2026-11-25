const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('epub_browser/assets/chapter.js', 'utf8');
function readerFunction(name) {
    const start = source.indexOf('    function ' + name + '(');
    assert.ok(start >= 0, name);
    const end = source.indexOf('\n    function ', start + 5);
    return source.slice(start, end);
}
for (const mode of ['scrolling', 'pagination', 'continuous']) {
    test(`${mode}: same-chapter encoded fragment uses the current chapter target`, () => {
        const calls = [];
        const target = {index: 2, path: '/book/demo/chapter_2.html', hash: '#%E6%B3%A8'};
        const section = {getAttribute: () => ''};
        const context = vm.createContext({
            isPaginationMode: mode === 'pagination', isContinuousScroll: mode === 'continuous',
            chapter_index: '2', chapterTargetFromUrl: () => target,
            closeReaderDrawers: () => {}, updateReaderChapterHistory: () => {},
            scrollToPaginationTarget: t => calls.push(t), scrollToChapterTarget: t => calls.push(t),
            scrollToContinuousChapterTarget: t => calls.push(t),
            content: {querySelector: () => section}, activeReaderChapterRequest: 0, readerChapterXhr: null,
            selectReadingChapter: () => {}, setBookTocActiveChapter: () => {},
            localStorage: {setItem: () => {}}, book_hash: 'demo', hasSearchFragment: () => false,
            announceReadingSessionChapter: () => {},
        });
        vm.runInContext(readerFunction('navigateReaderChapter'), context);
        assert.equal(context.navigateReaderChapter('chapter_2.html#%E6%B3%A8', {history:true}), true);
        assert.equal(calls[0], target);
    });
}
test('an explicit fragment takes precedence over saved reading progress', () => {
    const context = vm.createContext({hasSearchFragment: () => false,
        window: {location: {hash: '#note'}}, isPaginationMode: true, totalPages: 2,
        getStorageKey: () => 'saved', localStorage: {getItem: () => '1'},
        showPage: () => {throw Error('restored progress over fragment');}});
    vm.runInContext(readerFunction('loadReadingProgress'), context);
    context.loadReadingProgress();
});
for (const mode of ['scrolling', 'pagination', 'continuous']) {
    test(`${mode}: encoded fragments locate the authored ID`, () => {
        const calls = [];
        const anchor = {id: '注', offsetLeft: 800, scrollIntoView: () => calls.push('anchor'),
            getBoundingClientRect: () => ({top: 500})};
        const root = {querySelectorAll: () => [anchor], setAttribute: () => {}, focus: () => {}};
        const context = vm.createContext({content: root, pageWidth: 400,
            window: {requestAnimationFrame: f => f(), scrollY: 0, scrollTo: (...args) => calls.push(args)},
            showPage: page => calls.push(page), hasSearchFragment: () => false});
        const name = mode === 'pagination' ? 'scrollToPaginationTarget' :
            mode === 'continuous' ? 'scrollToContinuousChapterTarget' : 'scrollToChapterTarget';
        vm.runInContext(readerFunction('decodeChapterFragment') + readerFunction(name), context);
        context[name]({hash: '#%E6%B3%A8'}, root);
        assert.ok(mode === 'pagination' ? calls.includes(2) :
            mode === 'scrolling' ? calls.includes('anchor') : calls.some(v => v[0]?.top === 420));
    });
}
test('external chapter-shaped URLs are not adopted by the reader', () => {
    const context = vm.createContext({book_hash: 'demo', window: {location: {origin: 'https://reader.test'}},
        document: {createElement: () => new URL('https://reader.test/')}});
    // A browser anchor resolves href assignments into its URL properties.
    context.document.createElement = () => {
        let url;
        return new Proxy({}, {set(_, k, v) { if (k === 'href') url = new URL(v); else url[k] = v; return true; },
            get(_, k) { return url[k]; }});
    };
    vm.runInContext(readerFunction('chapterTargetFromUrl'), context);
    assert.equal(context.chapterTargetFromUrl('https://external.test/book/demo/chapter_2.html#note'), null);
    assert.equal(context.chapterTargetFromUrl('https://reader.test/book/demo/chapter_2.html#note').index, 2);
});
function clickHarness({continuous = false, pdf = false, href = '#note'} = {}) {
    let handler, destination;
    const section = {getAttribute: () => '3'};
    const link = {target: '', hasAttribute: () => false, getAttribute: () => href, closest: () => section};
    const content = {addEventListener: (_, fn) => {handler = fn;}, querySelector: () => pdf ? {} : null};
    const context = vm.createContext({content, isContinuousScroll: continuous,
        getChapterUrl: index => `/book/demo/chapter_${index}.html`,
        navigateReaderChapter: url => {destination = url; return !url.startsWith('https:');}});
    const start = source.indexOf("    content.addEventListener('click', function(event) {");
    const end = source.indexOf('    wireReaderChapterNavigation();', start);
    vm.runInContext(source.slice(start, end), context);
    return {click(extra = {}) {
        let prevented = false;
        handler({button: 0, target: {closest: () => link}, preventDefault: () => {prevented = true;}, ...extra});
        return {prevented, destination};
    }};
}
test('continuous footnote clicks resolve within their own loaded chapter', () => {
    assert.deepEqual(clickHarness({continuous:true}).click(),
        {prevented:true, destination:'/book/demo/chapter_3.html#note'});
});
test('external and modified clicks keep native link behavior', () => {
    assert.equal(clickHarness({href:'https://example.org/'}).click().prevented, false);
    assert.deepEqual(clickHarness().click({ctrlKey:true}), {prevented:false, destination:undefined});
});
test('PDF content clicks remain with the PDF adapter', () => {
    assert.deepEqual(clickHarness({pdf:true}).click(), {prevented:false, destination:undefined});
});
