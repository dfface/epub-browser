(function(root) {
    'use strict';

    var cache = root.EpubBrowserBookCache;
    var i18n = root.EpubBrowserI18n;
    var generation = 0;
    var closeButton;

    function element(tag, className) {
        var node = document.createElement(tag);
        if (className) node.className = className;
        return node;
    }

    function message(key, parameters) {
        return i18n.t('bookCache.' + key, parameters);
    }

    function button(key, action, style) {
        var node = element('button', 'app-dialog-button' + (style ? ' ' + style : ''));
        node.type = 'button';
        node.textContent = message(key);
        node.dataset.i18n = 'bookCache.' + key;
        node.addEventListener('click', action);
        return node;
    }

    function bytes(size) {
        var units = ['B', 'kB', 'MB', 'GB', 'TB'];
        var unit = 0;
        while (size >= 1000 && unit < units.length - 1) {
            size /= 1000;
            unit++;
        }
        return new Intl.NumberFormat(document.documentElement.lang || 'en', {
            maximumFractionDigits: unit ? 1 : 0
        }).format(size) + ' ' + units[unit];
    }

    function open(trigger, key, render, bookTitle) {
        var disclosure = trigger.closest('details');
        var returnFocus = trigger;
        if (disclosure) {
            disclosure.open = false;
            returnFocus = disclosure.querySelector('summary');
        }
        var panel = root.EpubDialog.panel({
            fullscreen: key === 'storage',
            title: bookTitle,
            titleKey: bookTitle ? null : 'bookCache.' + key,
            titleDirection: bookTitle ? 'auto' : null,
            closeTextKey: 'bookCache.close',
            returnFocus: returnFocus,
            onClose: function() { generation++; }
        });
        closeButton = panel.closeButton;
        render(panel.body, ++generation);
    }

    function stateText(node, key, params) {
        node.textContent = message(key, params);
        node.dataset.i18n = 'bookCache.' + key;
        if (params) node.dataset.i18nParams = JSON.stringify(params);
        else delete node.dataset.i18nParams;
    }

    function storageError(error) {
        return error && error.name === 'QuotaExceededError' ? 'quota' : 'error';
    }

    function bookDialog(body, view, book) {
        var status = element('p', 'book-cache-status');
        status.setAttribute('role', 'status');
        stateText(status, 'loading');
        var progress = element('progress', 'book-cache-progress');
        progress.hidden = true;
        progress.setAttribute('data-i18n-aria-label', 'bookCache.progress');
        progress.setAttribute('aria-label', message('progress'));
        var actions = element('div', 'book-cache-actions');
        body.append(status, progress, actions);
        var controller;
        var owner;
        var local = false;

        function draw(key, params) {
            if (generation !== view) return;
            stateText(status, key, params);
            progress.hidden = !controller;
            closeButton.disabled = Boolean(controller);
            var focusWasHere = actions.contains(document.activeElement);
            actions.replaceChildren();
            if (controller) {
                actions.appendChild(button('cancel', function() { controller.abort(); }));
            } else {
                if (key !== 'saved') actions.appendChild(button(key === 'error' || key === 'quota' ? 'retry' : 'save', save, 'app-dialog-confirm'));
                if (local) actions.appendChild(button('remove', function() {
                    confirmRemoval(book.title).then(function(confirmed) { if (confirmed) remove(); });
                }, 'app-dialog-danger-action'));
            }
            if (focusWasHere) (actions.firstElementChild || closeButton).focus();
        }

        async function save() {
            controller = new AbortController();
            var signal = controller.signal;
            progress.removeAttribute('value');
            draw('starting');
            try {
                var entry = await cache.save(book, signal, function(done, total, size, fraction) {
                    if (generation !== view) return;
                    progress.max = total;
                    if (fraction === null) progress.removeAttribute('value');
                    else progress.value = done + (fraction || 0);
                    status.removeAttribute('role');
                    stateText(status, 'downloading', { done: done, total: total, size: bytes(size) });
                }, owner);
                controller = null;
                local = true;
                status.setAttribute('role', 'status');
                draw('saved', { size: bytes(entry.size) });
            } catch (error) {
                controller = null;
                status.setAttribute('role', 'status');
                // A failed transfer may have left a previous entry intact.
                local = (await cache.list(owner).catch(function() { return []; })).some(function(item) { return item.id === book.id; });
                draw(signal.aborted ? 'cancelled' : storageError(error));
            }
        }

        async function remove() {
            try {
                actions.querySelectorAll('button').forEach(function(node) { node.disabled = true; });
                await cache.remove(book.id, owner);
                local = false;
                draw('removed');
                if (generation === view) actions.firstElementChild.focus();
            } catch (error) { draw(storageError(error)); }
        }

        cache.activeAccount().then(function(current) {
            owner = current;
            return cache.inspect(book, owner);
        }).then(function(entry) {
            local = Boolean(entry);
            if (!entry) draw('help');
            else if (entry.current) draw('saved', { size: bytes(entry.size) });
            else draw(entry.complete ? 'outdated' : 'partial');
        }).catch(function(error) { draw(storageError(error)); });
    }

    function confirmRemoval(title) {
        return root.EpubDialog.confirm({
            titleKey: 'bookCache.remove',
            messageKey: 'bookCache.confirmRemove',
            messageParams: { title: title },
            confirmTextKey: 'bookCache.remove',
            cancelTextKey: 'bookCache.cancel',
            destructive: true
        });
    }

    function storageDialog(body, view) {
        var status = element('p', 'book-cache-status');
        status.setAttribute('role', 'status');
        stateText(status, 'loading');
        var list = element('ul', 'book-cache-list');
        var actions = element('div', 'book-cache-actions');
        body.append(status, list, actions);
        var owner;

        async function refresh(focus, notice) {
            try {
                if (!owner) owner = await cache.activeAccount();
                var entries = await cache.list(owner);
                if (generation !== view) return;
                entries.sort(function(a, b) { return b.updated - a.updated; });
                list.replaceChildren();
                actions.replaceChildren();
                var total = entries.reduce(function(sum, entry) { return sum + entry.size; }, 0);
                stateText(status, notice || (entries.length ? 'usage' : 'empty'), { size: bytes(total) });
                entries.forEach(function(entry) {
                    var item = element('li');
                    var info = element('div');
                    var name = element('strong', 'book-cache-name');
                    name.textContent = entry.title;
                    name.dir = 'auto';
                    var detail = element('div', 'book-cache-detail');
                    var date = new Intl.DateTimeFormat(document.documentElement.lang || 'en', {
                        dateStyle: 'medium'
                    }).format(entry.updated);
                    detail.textContent = entry.format.toUpperCase() + ' · ' + bytes(entry.size) + ' · ' + date;
                    if (!entry.complete) {
                        var partial = element('span');
                        stateText(partial, 'partial');
                        detail.append(' · ', partial);
                    }
                    info.append(name, detail);
                    var remove = button('remove', function() {
                        confirmRemoval(entry.title).then(function(confirmed) {
                            if (confirmed) change(function() { return cache.remove(entry.id, owner); }, 'removed');
                        });
                    }, 'app-dialog-danger-action');
                    function label() {
                        remove.setAttribute('aria-label', message('removeBook', { title: entry.title }));
                    }
                    label();
                    remove.dataset.i18nAriaLabel = 'bookCache.removeBook';
                    remove.dataset.i18nParams = JSON.stringify({ title: entry.title });
                    item.append(info, remove);
                    list.appendChild(item);
                });
                if (entries.length) actions.appendChild(button('clear', confirmClear, 'app-dialog-danger-action'));
                if (focus) (list.querySelector('button') || closeButton).focus();
            } catch (error) {
                if (generation !== view) return;
                list.replaceChildren();
                actions.replaceChildren();
                stateText(status, storageError(error));
                if (focus) closeButton.focus();
            }
        }

        async function change(operation, notice) {
            list.querySelectorAll('button').forEach(function(node) { node.disabled = true; });
            actions.querySelectorAll('button').forEach(function(node) { node.disabled = true; });
            try {
                await operation();
                await refresh(true, notice);
            } catch (error) {
                await refresh(true, storageError(error));
            }
        }

        function confirmClear() {
            return root.EpubDialog.confirm({
                titleKey: 'bookCache.clear',
                messageKey: 'bookCache.confirmClear',
                confirmTextKey: 'bookCache.clear',
                cancelTextKey: 'bookCache.cancel',
                destructive: true
            }).then(function(confirmed) {
                if (confirmed && generation === view) {
                    return change(function() { return cache.clear(owner); }, 'cleared');
                }
            });
        }

        refresh();
    }

    function bind() {
        if (!cache.supported() || !root.EpubDialog || !root.EpubDialog.panel) return;
        document.querySelectorAll('[data-book-cache-trigger], [data-book-cache-manage]').forEach(function(trigger) {
            var data = trigger.dataset;
            var isBook = trigger.hasAttribute('data-book-cache-trigger');
            var book = isBook ? {
                id: data.bookId, title: data.bookTitle, format: data.bookFormat,
                count: Number(data.chapterCount), version: data.bookVersion
            } : null;
            if (book && ((root.EpubBrowserMode !== 'server' && !book.version) || !book.count)) return;
            trigger.hidden = false;
            trigger.addEventListener('click', function() {
                if (book) open(trigger, 'save', function(body, view) { bookDialog(body, view, book); }, book.title);
                else open(trigger, 'storage', storageDialog);
            });
        });
    }

    document.addEventListener('DOMContentLoaded', bind);
})(window);
