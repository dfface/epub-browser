(function(root, factory) {
    var hub = factory(root);
    if (typeof module === 'object' && module.exports) module.exports = hub;
    root.AnnotationHub = hub;
})(typeof window !== 'undefined' ? window : globalThis, function(root) {
    'use strict';

    var modalState = { modal: null, opener: null, scrollY: 0, bookHash: '', data: null, loadVersion: 0 };

    function i18n() { return root.EpubBrowserI18n; }
    function tr(key, params) {
        var runtime = i18n();
        return runtime && runtime.t ? runtime.t('annotations.' + key, params) : 'annotations.' + key;
    }

    function publicPath(path) {
        return root.EpubBrowserURL ? root.EpubBrowserURL.publicPath(path) : path;
    }

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
                    cover: metadataEntry.cover || '', count: 0, latestAt: 0
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
            if (!item || !item.title) return;
            var index = Number(item.chapter_index);
            if (isNaN(index)) index = Number(item.index);
            if (!isNaN(index)) titles[index] = item.title;
        });
        return titles;
    }

    function groupByChapter(annotations, toc) {
        var titles = tocTitles(toc), groups = {};
        (annotations || []).forEach(function(annotation) {
            var index = Number(annotation.chapter_index);
            if (isNaN(index)) index = 0;
            // chapter_index is the canonical, user-visible chapter number across
            // annotations, AI reading, jobs, and chat. Do not turn it into a
            // one-based ordinal here.
            if (!groups[index]) groups[index] = { index: index, title: titles[index] || tr('chapterNumber', { number: index }), annotations: [] };
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
        return publicPath('/book/' + encodeURIComponent(annotation.book_hash) + '/chapter_' + Number(annotation.chapter_index) + '.html?annotation=' + encodeURIComponent(annotation.id));
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

    function element(name, className, text) {
        var node = document.createElement(name);
        if (className) node.className = className;
        if (text !== undefined) node.textContent = text;
        return node;
    }
    function clear(node) { while (node.firstChild) node.removeChild(node.firstChild); }
    function formatTimestamp(time) {
        if (!time) return '';
        var date = new Date(time);
        if (isNaN(date.getTime())) return '';
        var runtime = i18n();
        return runtime && runtime.formatDate ? runtime.formatDate(date, { dateStyle: 'short', timeStyle: 'medium' }) : '';
    }
    function labelCount(count) { return tr('annotationCount', { count: count }); }

    function notify(key, type, params) {
        if (root.EpubBrowserNotification && typeof root.EpubBrowserNotification.show === 'function') {
            root.EpubBrowserNotification.show(tr(key, params), type);
        }
    }

    function deleteAnnotation(annotation, onDeleted) {
        if (!annotation || !annotation.id || !root.EpubDialog || typeof root.EpubDialog.confirm !== 'function' ||
                !root.AnnotationStorage || typeof root.AnnotationStorage.delete !== 'function') {
            return Promise.resolve(false);
        }
        return Promise.resolve().then(function() {
            return root.EpubDialog.confirm({
                title: tr('deleteAnnotation'),
                message: tr('confirmDelete'),
                confirmText: tr('delete'),
                destructive: true
            });
        }).then(function(confirmed) {
            if (!confirmed) return false;
            return Promise.resolve(root.AnnotationStorage.delete(annotation.id)).then(function() {
                if (typeof onDeleted === 'function') onDeleted(annotation);
                notify('deleted', 'success');
                return true;
            });
        }).catch(function(error) {
            notify('deleteFailed', 'error', { error: error && error.message ? error.message : String(error) });
            return false;
        });
    }

    function translateChrome() {
        if (!modalState.modal) return;
        modalState.back.querySelector('span').textContent = tr('allAnnotatedBooks');
        modalState.modal.querySelector('.annotation-hub-header-label span').textContent = tr('hubTitle');
        modalState.closeButton.setAttribute('aria-label', tr('closeHub'));
    }

    function renderCurrentView() {
        if (!modalState.data) return;
        if (!modalState.bookHash) {
            renderBookCards(aggregateBooks(modalState.data.annotations, modalState.data.metadata));
            return;
        }
        renderBookAnnotations(
            modalState.bookHash,
            modalState.data.annotations.filter(function(annotation) { return annotation.book_hash === modalState.bookHash; }),
            modalState.data.metadata,
            modalState.data.toc || []
        );
    }

    function ensureModal() {
        if (modalState.modal || !root.document || !document.body) return modalState.modal;
        var modal = element('div', 'annotation-hub-modal');
        modal.id = 'annotationHubModal';
        modal.hidden = true;
        modal.setAttribute('role', 'dialog');
        modal.setAttribute('aria-modal', 'true');
        modal.setAttribute('aria-labelledby', 'annotationHubTitle');
        modal.innerHTML = '<div class="annotation-hub-backdrop" data-annotation-hub-close></div>' +
            '<section class="annotation-hub-dialog"><header class="annotation-hub-modal-header">' +
            '<button type="button" class="annotation-hub-header-button" id="annotationHubBack" hidden><i class="fas fa-arrow-left" aria-hidden="true"></i><span></span></button>' +
            '<span class="annotation-hub-header-label"><i class="fas fa-highlighter" aria-hidden="true"></i><span></span></span>' +
            '<button type="button" class="annotation-hub-icon-button" id="annotationHubClose"><i class="fas fa-times" aria-hidden="true"></i></button>' +
            '</header><main class="annotation-hub-container" id="annotationHub" tabindex="-1" aria-live="polite"></main></section>';
        document.body.appendChild(modal);
        modalState.modal = modal;
        modalState.back = document.getElementById('annotationHubBack');
        modalState.closeButton = document.getElementById('annotationHubClose');
        modalState.container = document.getElementById('annotationHub');
        modalState.back.addEventListener('click', function() { load(''); });
        modalState.closeButton.addEventListener('click', close);
        modal.querySelector('[data-annotation-hub-close]').addEventListener('click', close);
        modal.addEventListener('keydown', trapFocus);
        translateChrome();
        return modal;
    }

    function trapFocus(event) {
        if (event.key === 'Escape') { event.preventDefault(); close(); return; }
        if (event.key !== 'Tab') return;
        var focusable = modalState.modal.querySelectorAll('button:not([hidden]):not([disabled]), a[href], [tabindex]:not([tabindex="-1"])');
        if (!focusable.length) return;
        var first = focusable[0], last = focusable[focusable.length - 1];
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    }

    function renderState(title, detail, retry) {
        var container = modalState.container;
        clear(container);
        container.removeAttribute('aria-busy');
        var box = element('section', 'annotation-hub-state');
        var heading = element('h1', 'annotation-hub-title', title);
        heading.id = 'annotationHubTitle';
        box.appendChild(heading);
        box.appendChild(element('p', '', detail));
        if (retry) {
            var button = element('button', 'annotation-hub-retry', tr('retry'));
            button.type = 'button'; button.addEventListener('click', retry); box.appendChild(button);
        }
        container.appendChild(box);
    }

    function renderLoading() {
        var container = modalState.container;
        clear(container);
        container.setAttribute('aria-busy', 'true');
        var loading = element('section', 'annotation-hub-loading');
        loading.setAttribute('role', 'status');
        loading.appendChild(element('span', 'annotation-hub-spinner'));
        loading.appendChild(element('p', '', tr('loading')));
        container.appendChild(loading);
    }

    function renderBookCards(books) {
        var container = modalState.container;
        clear(container);
        container.removeAttribute('aria-busy');
        var heading = element('header', 'annotation-hub-heading');
        var title = element('h1', 'annotation-hub-title', tr('annotatedBooks'));
        title.id = 'annotationHubTitle';
        heading.appendChild(title);
        heading.appendChild(element('p', '', labelCount(books.reduce(function(sum, book) { return sum + book.count; }, 0)) + tr('bylineSeparator') + tr('bookCount', { count: books.length })));
        container.appendChild(heading);
        if (!books.length) { renderState(tr('noAnnotationsTitle'), tr('noAnnotationsDescription')); return; }
        var list = element('div', 'annotation-book-list');
        books.forEach(function(book) {
            var card = element('button', 'annotation-book-card');
            card.type = 'button'; card.addEventListener('click', function() { load(book.hash); });
            if (book.cover) {
                var image = document.createElement('img');
                image.src = book.cover;
                image.alt = ''; image.className = 'annotation-book-cover'; card.appendChild(image);
            } else card.appendChild(element('div', 'annotation-book-cover annotation-book-cover-fallback', tr('bookFallback')));
            var content = element('div', 'annotation-book-card-content');
            content.appendChild(element('h2', '', book.title));
            if (book.authors.length) content.appendChild(element('p', 'annotation-book-author', book.authors.join(tr('authorSeparator'))));
            content.appendChild(element('p', 'annotation-book-meta', labelCount(book.count) + (book.latestAt ? tr('bylineSeparator') + tr('updatedAt', { date: formatTimestamp(book.latestAt) }) : '')));
            card.appendChild(content); list.appendChild(card);
        });
        container.appendChild(list);
    }

    function renderBookAnnotations(bookHash, annotations, metadata, toc) {
        var container = modalState.container, book = bookMap(metadata)[bookHash];
        clear(container);
        container.removeAttribute('aria-busy');
        var heading = element('header', 'annotation-hub-heading');
        var title = element('h1', 'annotation-hub-title', book ? book.title : bookHash);
        title.id = 'annotationHubTitle';
        heading.appendChild(title);
        heading.appendChild(element('p', '', labelCount(annotations.length)));
        container.appendChild(heading);
        if (!annotations.length) { renderState(tr('noBookAnnotationsTitle'), tr('noBookAnnotationsDescription')); return; }
        groupByChapter(annotations, toc).forEach(function(group) {
            var section = element('section', 'annotation-chapter-group');
            section.appendChild(element('h2', '', group.title));
            group.annotations.forEach(function(annotation) {
                section.appendChild(annotationCard(annotation));
            });
            container.appendChild(section);
        });
    }

    function annotationCard(annotation) {
        var row = element('article', 'annotation-card-row');
        var card = element('a', 'annotation-card');
        card.href = annotationHref(annotation); card.addEventListener('click', close);
        var stripe = element('span', 'annotation-card-color');
        stripe.style.backgroundColor = annotation.color || '#FFEB3B'; card.appendChild(stripe);
        var content = element('div', 'annotation-card-content');
        content.appendChild(element('blockquote', '', annotation.text || ''));
        if (annotation.note && annotation.note.trim()) content.appendChild(element('p', 'annotation-card-note', annotation.note));
        content.appendChild(element('p', 'annotation-card-meta', formatTimestamp(annotationTime(annotation))));
        card.appendChild(content); row.appendChild(card);

        var deleteButton = element('button', 'annotation-card-delete');
        deleteButton.type = 'button';
        deleteButton.setAttribute('aria-label', tr('deleteAnnotation'));
        deleteButton.setAttribute('title', tr('deleteAnnotation'));
        var deleteIcon = element('i', 'fas fa-trash-alt');
        deleteIcon.setAttribute('aria-hidden', 'true');
        deleteButton.appendChild(deleteIcon);
        deleteButton.addEventListener('click', function(event) {
            event.preventDefault(); event.stopPropagation();
            if (deleteButton.disabled) return;
            deleteButton.disabled = true;
            deleteButton.setAttribute('aria-busy', 'true');
            deleteAnnotation(annotation, function() {
                modalState.data.annotations = modalState.data.annotations.filter(function(item) { return item.id !== annotation.id; });
                renderCurrentView();
            }).then(function(deleted) {
                if (!deleted) {
                    deleteButton.disabled = false;
                    deleteButton.removeAttribute('aria-busy');
                }
            });
        });
        row.appendChild(deleteButton);
        return row;
    }

    function load(bookHash) {
        if (!ensureModal() || !root.AnnotationStorage) return;
        var loadVersion = ++modalState.loadVersion;
        modalState.bookHash = bookHash || '';
        modalState.data = null;
        modalState.back.hidden = !modalState.bookHash;
        renderLoading();
        Promise.resolve(root.AnnotationStorage.init()).then(function() {
            if (loadVersion !== modalState.loadVersion) return null;
            if (root.AnnotationStorage.getStorageType() === 'backend') return root.AnnotationStorage.isBackendAvailable().then(function(result) {
                if (!result.available) throw new Error('annotation_hub_cloud_unavailable');
            });
        }).then(function() {
            if (loadVersion !== modalState.loadVersion) return null;
            return Promise.all([root.AnnotationStorage.getAll(), requestJson(publicPath('/book-metadata.json'))]);
        }).then(function(data) {
            if (!data || loadVersion !== modalState.loadVersion || modalState.bookHash !== (bookHash || '')) return;
            modalState.data = { annotations: data[0] || [], metadata: data[1] || [], toc: [] };
            if (!modalState.bookHash) { renderBookCards(aggregateBooks(modalState.data.annotations, modalState.data.metadata)); return; }
            requestJson(publicPath('/book/' + encodeURIComponent(modalState.bookHash) + '/toc.json')).catch(function() { return []; }).then(function(toc) {
                if (loadVersion === modalState.loadVersion && modalState.bookHash === bookHash) {
                    modalState.data.toc = toc || [];
                    renderCurrentView();
                }
            });
        }).catch(function(error) {
            if (loadVersion !== modalState.loadVersion) return;
            renderState(tr('loadHubFailed'), tr('loadHubFailedDetail'), function() { load(modalState.bookHash); });
        });
    }

    function open(options) {
        options = options || {};
        var modal = ensureModal();
        if (!modal) return;
        if (modal.hidden) {
            modalState.opener = options.opener || document.activeElement;
            modalState.scrollY = root.scrollY || 0;
            document.body.classList.add('annotation-hub-open');
            document.body.style.top = '-' + modalState.scrollY + 'px';
            modal.hidden = false;
        }
        load(options.bookHash || '');
        root.setTimeout(function() { modalState.closeButton.focus(); }, 0);
    }

    function close() {
        if (!modalState.modal || modalState.modal.hidden) return;
        modalState.modal.hidden = true;
        document.body.classList.remove('annotation-hub-open'); document.body.style.top = '';
        root.scrollTo(0, modalState.scrollY);
        if (modalState.opener && typeof modalState.opener.focus === 'function') modalState.opener.focus();
    }

    function bind() {
        if (!root.document) return;
        if (!modalState.localeBound && i18n() && typeof i18n().onLocaleChange === 'function') {
            modalState.localeBound = true;
            i18n().onLocaleChange(function() {
                if (!modalState.modal) return;
                translateChrome();
                if (!modalState.modal.hidden && modalState.data) renderCurrentView();
            });
        }
        var triggers = document.querySelectorAll('[data-annotation-hub]');
        Array.prototype.forEach.call(triggers, function(trigger) {
            if (trigger.getAttribute('data-annotation-hub-bound')) return;
            trigger.setAttribute('data-annotation-hub-bound', 'true');
            trigger.addEventListener('click', function(event) {
                event.preventDefault(); open({ bookHash: trigger.getAttribute('data-book-hash') || '', opener: trigger });
            });
        });
    }

    if (root.document) {
        if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', bind);
        else bind();
    }

    return { aggregateBooks: aggregateBooks, groupByChapter: groupByChapter, annotationHref: annotationHref, formatTimestamp: formatTimestamp, annotationCard: annotationCard, deleteAnnotation: deleteAnnotation, open: open, close: close, bind: bind };
});
