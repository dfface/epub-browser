const test = require('node:test');
const assert = require('node:assert/strict');
const { create } = require('../epub_browser/assets/chapter-prefetch.js');

function harness() {
    const scheduled = [];
    const requests = [];
    const controller = create({
        urlFor: (index) => `/book/demo/chapter_${index}.html`,
        schedule: (task) => {
            const entry = { task, ran: false, cancelled: false };
            scheduled.push(entry);
            return () => { entry.cancelled = true; };
        },
        request: (url, done) => {
            const entry = { url, done, cancelled: false };
            requests.push(entry);
            return () => { entry.cancelled = true; };
        },
    });
    return {
        controller,
        scheduled,
        requests,
        runScheduled() {
            let ran = 0;
            scheduled.forEach((entry) => {
                if (!entry.cancelled && !entry.ran) {
                    entry.ran = true;
                    ran += 1;
                    entry.task();
                }
            });
            return ran;
        },
    };
}

test('prefetches only the next chapter after a chapter has rendered', () => {
    const reader = harness();
    reader.controller.afterChapterRendered(3, 8);

    assert.equal(reader.requests.length, 0, 'prefetch waits for an idle slot');
    reader.runScheduled();
    assert.deepEqual(
        reader.requests.map((entry) => entry.url),
        ['/book/demo/chapter_4.html'],
    );
});

test('does not prefetch past the last chapter', () => {
    const reader = harness();
    reader.controller.afterChapterRendered(7, 8);

    reader.runScheduled();
    assert.deepEqual(reader.requests, []);
});

test('keeps one in-flight prefetch when the same chapter renders twice', () => {
    const reader = harness();
    reader.controller.afterChapterRendered(2, 8);
    reader.controller.afterChapterRendered(2, 8);

    reader.runScheduled();
    assert.deepEqual(
        reader.requests.map((entry) => entry.url),
        ['/book/demo/chapter_3.html'],
    );
});

test('turning to the prefetched chapter reuses its response without another request', () => {
    const reader = harness();
    reader.controller.afterChapterRendered(2, 8);
    reader.runScheduled();
    const html = '<html><article id="eb-content" data-chapter-index="3"></article></html>';
    reader.requests[0].done(html);

    assert.equal(reader.controller.take(3), html);
    assert.equal(reader.controller.take(3), null, 'the cached response is consumed once');
    assert.equal(reader.requests.length, 1);
});

test('a chapter change drops the stale cache and prefetches the new next chapter', () => {
    const reader = harness();
    reader.controller.afterChapterRendered(2, 8);
    reader.runScheduled();
    reader.requests[0].done('<html>chapter 3</html>');

    reader.controller.afterChapterRendered(3, 8);
    reader.runScheduled();

    assert.deepEqual(
        reader.requests.map((entry) => entry.url),
        ['/book/demo/chapter_3.html', '/book/demo/chapter_4.html'],
    );
    assert.equal(reader.controller.take(3), null, 'the stale chapter 3 response is gone');
});

test('a direct chapter navigation cancels an in-flight prefetch so that chapter is fetched once', () => {
    const reader = harness();
    reader.controller.afterChapterRendered(2, 8);
    reader.runScheduled();

    assert.equal(reader.controller.take(3), null);
    assert.equal(reader.requests[0].cancelled, true);

    reader.controller.afterChapterRendered(3, 8);
    reader.runScheduled();
    assert.deepEqual(
        reader.requests.map((entry) => entry.url),
        ['/book/demo/chapter_3.html', '/book/demo/chapter_4.html'],
    );
});

test('a failed prefetch leaves chapter navigation on its normal network path', () => {
    const reader = harness();
    reader.controller.afterChapterRendered(2, 8);
    reader.runScheduled();
    reader.requests[0].done(null);

    assert.equal(reader.controller.take(3), null);
    reader.controller.afterChapterRendered(3, 8);
    reader.runScheduled();
    assert.equal(reader.requests[1].url, '/book/demo/chapter_4.html');
});

test('a late response from a cancelled prefetch cannot replace the current cache', () => {
    const reader = harness();
    reader.controller.afterChapterRendered(2, 8);
    reader.runScheduled();
    reader.controller.afterChapterRendered(4, 8);
    reader.runScheduled();
    reader.requests[0].done('<html>stale chapter 3</html>');
    reader.requests[1].done('<html>chapter 5</html>');

    assert.equal(reader.controller.take(5), '<html>chapter 5</html>');
    assert.equal(reader.controller.take(3), null);
});

test('a chapter change stays safe when the browser lacks cancelIdleCallback', () => {
    const previousWindow = global.window;
    const idleTasks = [];
    const requests = [];
    global.window = {
        requestIdleCallback: (task) => { idleTasks.push(task); return 1; },
    };
    try {
        const controller = create({
            urlFor: (index) => `/book/demo/chapter_${index}.html`,
            request: (url) => { requests.push(url); return () => {}; },
        });
        controller.afterChapterRendered(0, 3);
        assert.doesNotThrow(() => controller.afterChapterRendered(1, 3));
        assert.equal(idleTasks.length, 2);
        idleTasks.forEach((task) => task());
        assert.deepEqual(requests, ['/book/demo/chapter_2.html']);
    } finally {
        if (previousWindow === undefined) delete global.window;
        else global.window = previousWindow;
    }
});

test('browser defaults prefetch during idle time and cache only successful responses', () => {
    const previousWindow = global.window;
    const previousXHR = global.XMLHttpRequest;
    const idleTasks = [];
    const instances = [];
    class FakeXHR {
        constructor() { instances.push(this); }
        open(method, url) { this.method = method; this.url = url; }
        send() {}
        abort() { this.aborted = true; }
        respond(status, text) {
            this.status = status;
            this.responseText = text;
            this.onload();
        }
    }
    global.window = {
        requestIdleCallback: (task) => { idleTasks.push(task); return idleTasks.length; },
        cancelIdleCallback: () => {},
    };
    global.XMLHttpRequest = FakeXHR;
    try {
        const controller = create({
            urlFor: (index) => `/book/demo/chapter_${index}.html`,
        });
        controller.afterChapterRendered(0, 3);

        assert.equal(idleTasks.length, 1);
        idleTasks[0]();
        assert.equal(instances.length, 1);
        assert.equal(instances[0].method, 'GET');
        assert.equal(instances[0].url, '/book/demo/chapter_1.html');

        instances[0].respond(403, '<html>sign in</html>');
        assert.equal(controller.take(1), null, 'a rejected response is not cached');

        controller.afterChapterRendered(1, 3);
        idleTasks[1]();
        instances[1].respond(200, '<html>chapter 2</html>');
        assert.equal(controller.take(2), '<html>chapter 2</html>');
    } finally {
        if (previousWindow === undefined) delete global.window;
        else global.window = previousWindow;
        if (previousXHR === undefined) delete global.XMLHttpRequest;
        else global.XMLHttpRequest = previousXHR;
    }
});
