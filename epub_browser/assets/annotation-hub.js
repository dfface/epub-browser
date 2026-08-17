(function(root, factory) {
    var hub = factory(root);
    if (typeof module === 'object' && module.exports) module.exports = hub;
    root.AnnotationHub = hub;
})(typeof window !== 'undefined' ? window : globalThis, function(root) {
    'use strict';

    function annotationTime(annotation) {
        var value = annotation && (annotation.updated_at || annotation.created_at);
        var time = value ? Date.parse(value) : 0;
        return isNaN(time) ? 0 : time;
    }

    function bookMap(metadata) {
        var map = {};
        (metadata || []).forEach(function(book) { map[book.hash] = book; });
        return map;
    }

    function aggregateBooks(annotations, metadata) {
        var metadataByHash = bookMap(metadata);
        var aggregate = {};
        (annotations || []).forEach(function(annotation) {
            if (!annotation || !annotation.book_hash) return;
            var current = aggregate[annotation.book_hash];
            if (!current) {
                var metadataEntry = metadataByHash[annotation.book_hash] || {};
                current = aggregate[annotation.book_hash] = {
                    hash: annotation.book_hash,
                    title: metadataEntry.title || annotation.book_hash,
                    authors: metadataEntry.authors || [],
                    cover: metadataEntry.cover || '',
                    count: 0,
                    latestAt: 0
                };
            }
            current.count++;
            current.latestAt = Math.max(current.latestAt, annotationTime(annotation));
        });
        return Object.keys(aggregate).map(function(hash) { return aggregate[hash]; }).sort(function(a, b) {
            return b.latestAt - a.latestAt || a.title.localeCompare(b.title);
        });
    }

    function tocTitles(toc) {
        var titles = {};
        (toc || []).forEach(function(item) {
            if (item && typeof item.index === 'number') titles[item.index] = item.title;
        });
        return titles;
    }

    function groupByChapter(annotations, toc) {
        var titles = tocTitles(toc);
        var groups = {};
        (annotations || []).forEach(function(annotation) {
            var index = Number(annotation.chapter_index);
            if (isNaN(index)) index = 0;
            if (!groups[index]) groups[index] = { index: index, title: titles[index] || 'Chapter ' + (index + 1), annotations: [] };
            groups[index].annotations.push(annotation);
        });
        return Object.keys(groups).map(function(key) { return groups[key]; }).sort(function(a, b) {
            return a.index - b.index;
        }).map(function(group) {
            group.annotations.sort(function(a, b) { return annotationTime(a) - annotationTime(b); });
            return group;
        });
    }

    function annotationHref(annotation) {
        return '/book/' + encodeURIComponent(annotation.book_hash) + '/chapter_' + Number(annotation.chapter_index) + '.html?annotation=' + encodeURIComponent(annotation.id);
    }

    function queryBook() {
        var match = (root.location.search || '').match(/[?&]book=([^&]*)/);
        return match ? decodeURIComponent(match[1].replace(/\+/g, ' ')) : '';
    }

    function requestJson(url) {
        return new Promise(function(resolve, reject) {
            var request = new XMLHttpRequest();
            request.open('GET', url, true);
            request.onload = function() {
                if (request.status < 200 || request.status >= 300) { reject(new Error('HTTP ' + request.status)); return; }
                try { resolve(JSON.parse(request.responseText)); } catch (error) { reject(error); }
            };
            request.onerror = function() { reject(new Error('Network error')); };
            request.send();
        });
    }

    function setText(element, text) { element.textContent = text; return element; }
    function element(name, className, text) {
        var node = document.createElement(name);
        if (className) node.className = className;
        if (text !== undefined) setText(node, text);
        return node;
    }
    function formatDate(time) { return time ? new Date(time).toLocaleDateString() : ''; }
    function persistPosition() {
        var state = { url: root.location.href, y: root.scrollY || 0 };
        try { root.sessionStorage.setItem('epub-browser-annotation-hub', JSON.stringify(state)); } catch (error) {}
        if (root.history && root.history.replaceState) root.history.replaceState(state, '', root.location.href);
    }
    function restorePosition() {
        try {
            var state = JSON.parse(root.sessionStorage.getItem('epub-browser-annotation-hub') || 'null');
            if (state && state.url === root.location.href && state.y) root.setTimeout(function() { root.scrollTo(0, state.y); }, 0);
        } catch (error) {}
    }
    function makeLink(href, className) {
        var link = element('a', className);
        link.href = href;
        link.addEventListener('click', persistPosition);
        return link;
    }
    function clear(container) { while (container.firstChild) container.removeChild(container.firstChild); }
    function state(container, title, detail, retry) {
        clear(container);
        var box = element('section', 'annotation-hub-state');
        box.appendChild(element('h1', '', title));
        box.appendChild(element('p', '', detail));
        if (retry) { var button = element('button', 'annotation-hub-retry', 'Retry'); button.addEventListener('click', init); box.appendChild(button); }
        container.appendChild(box);
    }
    function renderBookCards(container, books) {
        clear(container);
        var heading = element('header', 'annotation-hub-heading');
        heading.appendChild(element('h1', '', 'Annotated books'));
        heading.appendChild(element('p', '', books.length + ' book' + (books.length === 1 ? '' : 's') + ' with annotations'));
        container.appendChild(heading);
        if (!books.length) { state(container, 'No annotations yet', 'Select text while reading to save your first annotation.'); return; }
        var list = element('div', 'annotation-book-list');
        books.forEach(function(book) {
            var card = makeLink('/annotations/index.html?book=' + encodeURIComponent(book.hash), 'annotation-book-card');
            if (book.cover) { var image = document.createElement('img'); image.src = '/book/' + encodeURIComponent(book.hash) + '/' + book.cover; image.alt = ''; image.className = 'annotation-book-cover'; card.appendChild(image); }
            else card.appendChild(element('div', 'annotation-book-cover annotation-book-cover-fallback', 'Book'));
            var content = element('div', 'annotation-book-card-content');
            content.appendChild(element('h2', '', book.title));
            if (book.authors.length) content.appendChild(element('p', 'annotation-book-author', book.authors.join(' & ')));
            content.appendChild(element('p', 'annotation-book-meta', book.count + ' annotation' + (book.count === 1 ? '' : 's') + (book.latestAt ? ' · updated ' + formatDate(book.latestAt) : '')));
            card.appendChild(content); list.appendChild(card);
        });
        container.appendChild(list);
    }
    function renderBookAnnotations(container, bookHash, annotations, metadata, toc) {
        clear(container);
        var book = bookMap(metadata)[bookHash];
        var heading = element('header', 'annotation-hub-heading');
        var back = makeLink('/annotations/index.html', 'annotation-hub-back'); back.textContent = 'Annotated books'; heading.appendChild(back);
        heading.appendChild(element('h1', '', book ? book.title : bookHash));
        heading.appendChild(element('p', '', annotations.length + ' annotation' + (annotations.length === 1 ? '' : 's')));
        container.appendChild(heading);
        if (!annotations.length) { state(container, 'No annotations in this book', 'This book may have been removed or its annotations were deleted.'); return; }
        groupByChapter(annotations, toc).forEach(function(group) {
            var section = element('section', 'annotation-chapter-group'); section.appendChild(element('h2', '', group.title));
            group.annotations.forEach(function(annotation) {
                var card = makeLink(annotationHref(annotation), 'annotation-card');
                var stripe = element('span', 'annotation-card-color'); stripe.style.backgroundColor = annotation.color || '#FFEB3B'; card.appendChild(stripe);
                var content = element('div', 'annotation-card-content'); content.appendChild(element('blockquote', '', annotation.text || ''));
                if (annotation.note && annotation.note.trim()) content.appendChild(element('p', 'annotation-card-note', annotation.note));
                content.appendChild(element('p', 'annotation-card-meta', formatDate(annotationTime(annotation)))); card.appendChild(content); section.appendChild(card);
            });
            container.appendChild(section);
        });
    }
    function init() {
        var container = document.getElementById('annotationHub');
        if (!container || !root.AnnotationStorage) return;
        state(container, 'Loading annotations', '');
        root.AnnotationStorage.init().then(function() {
            if (root.AnnotationStorage.getStorageType() === 'backend') return root.AnnotationStorage.isBackendAvailable().then(function(result) {
                if (!result.available) throw new Error('Cloud annotations are unavailable on this static site.');
            });
        }).then(function() {
            return Promise.all([root.AnnotationStorage.getAll(), requestJson('/book-metadata.json')]);
        }).then(function(data) {
            var annotations = data[0] || [], metadata = data[1] || [], selectedBook = queryBook();
            if (!selectedBook) { renderBookCards(container, aggregateBooks(annotations, metadata)); restorePosition(); return; }
            requestJson('/book/' + encodeURIComponent(selectedBook) + '/toc.json').catch(function() { return []; }).then(function(toc) {
                renderBookAnnotations(container, selectedBook, annotations.filter(function(annotation) { return annotation.book_hash === selectedBook; }), metadata, toc); restorePosition();
            });
        }).catch(function(error) { state(container, 'Unable to load annotations', error.message || 'Please try again.', true); });
    }
    return { aggregateBooks: aggregateBooks, groupByChapter: groupByChapter, annotationHref: annotationHref, init: init };
});
