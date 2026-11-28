(function(root, factory) {
    if (typeof module !== 'undefined' && module.exports) module.exports = factory();
    else root.EpubTocTree = factory();
})(typeof self !== 'undefined' ? self : this, function() {
    // Native list + disclosure buttons: links keep their navigation semantics.
    function initBookTocTree(list, options) {
        options = options || {};
        function copyState(source) {
            var copy = {};
            Object.keys(source || {}).forEach(function(key) { copy[key] = source[key]; });
            return copy;
        }
        function show(element, visible) {
            element.hidden = !visible;
            if (element.style) element.style.display = visible ? '' : 'none';
        }
        var rows = Array.prototype.slice.call(list.querySelectorAll('[data-toc-level]'));
        var state = copyState(options.state);
        var storageKey;
        if (options.bookId && options.storage) {
            var shape = rows.map(function(row) {
                var link = row.querySelector('a');
                return [row.getAttribute('data-toc-level'), link ? link.getAttribute('data-chapter-index') : null];
            });
            storageKey = 'toc-expansion-v2:' + options.bookId + ':' + JSON.stringify(shape);
            try { state = JSON.parse(options.storage.getItem(storageKey) || '{}') || {}; } catch (error) {}
        }
        var bulkToggle = options.bulkToggle;
        var stack = [];
        var entries = rows.map(function(row, index) {
            var depth = Number(row.getAttribute('data-toc-level')) || 0;
            while (stack.length && stack[stack.length - 1].depth >= depth) stack.pop();
            var entry = {row: row, index: index, depth: depth, parent: stack[stack.length - 1], children: []};
            if (entry.parent) entry.parent.children.push(entry);
            row.id = 'book-toc-entry-' + index;
            stack.push(entry);
            return entry;
        });
        var collapsible = entries.some(function(entry) { return entry.children.length; });
        list.setAttribute('data-toc-collapsible', String(collapsible));
        function save() {
            if (storageKey) {
                try { options.storage.setItem(storageKey, JSON.stringify(state)); } catch (error) {}
            }
            if (options.onChange) options.onChange(copyState(state));
        }
        function allExpanded() {
            return entries.every(function(entry) { return !entry.children.length || state[entry.index] !== false; });
        }
        function render() {
            if (bulkToggle) {
                show(bulkToggle, collapsible);
                var key = allExpanded() ? 'reader.collapseAll' : 'reader.expandAll';
                var label = options.translate ? options.translate(key) : (allExpanded() ? 'Collapse all' : 'Expand all');
                if (options.iconOnly) {
                    bulkToggle.setAttribute('data-toc-action', allExpanded() ? 'collapse' : 'expand');
                    bulkToggle.setAttribute('data-i18n-aria-label', key);
                    bulkToggle.setAttribute('data-i18n-title', key);
                    bulkToggle.setAttribute('aria-label', label);
                    bulkToggle.setAttribute('title', label);
                } else {
                    bulkToggle.setAttribute('data-i18n', key);
                    bulkToggle.textContent = label;
                }
            }
            entries.forEach(function(entry) {
                show(entry.row, !(entry.parent && (entry.parent.row.hidden || state[entry.parent.index] === false)));
                if (entry.button) {
                    var expanded = state[entry.index] !== false;
                    entry.button.setAttribute('aria-expanded', String(expanded));
                    entry.button.textContent = expanded ? '▾' : '▸';
                }
            });
        }
        function expand(entry, value) { state[entry.index] = value; render(); save(); }
        function focus(entry) {
            if (!entry) return;
            var control = entry.row.querySelector('a') || entry.button;
            if (control) control.focus();
        }
        entries.forEach(function(entry) {
            if (!entry.children.length) return;
            var button = list.ownerDocument.createElement('button');
            button.type = 'button';
            button.className = 'toc-branch-toggle';
            button.setAttribute('data-i18n-aria-label', 'reader.toggleTocSection');
            button.setAttribute('aria-label', options.label || 'Expand or collapse section');
            button.setAttribute('aria-controls', entry.children.map(function(child) { return child.row.id; }).join(' '));
            button.onclick = function() { expand(entry, state[entry.index] === false); };
            entry.row.insertBefore(button, entry.row.firstChild);
            entry.button = button;
            if (!entry.row.querySelector('a')) {
                var label = entry.row.querySelector('.chapter-section-title');
                if (label) label.onclick = function() { expand(entry, state[entry.index] === false); };
            }
        });
        list.onkeydown = function(event) {
            if (event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
            var row = event.target;
            while (row && rows.indexOf(row) === -1) row = row.parentNode;
            var entry = entries.filter(function(item) { return item.row === row; })[0];
            if (!entry) return;
            var visible = entries.filter(function(item) { return !item.row.hidden; });
            var position = visible.indexOf(entry);
            switch (event.key) {
            case 'ArrowDown': focus(visible[position + 1]); break;
            case 'ArrowUp': focus(visible[position - 1]); break;
            case 'Home': focus(visible[0]); break;
            case 'End': focus(visible[visible.length - 1]); break;
            case 'ArrowRight':
                if (entry.children.length) {
                    if (state[entry.index] === false) expand(entry, true);
                    else focus(entry.children[0]);
                }
                break;
            case 'ArrowLeft':
                if (entry.children.length && state[entry.index] !== false) expand(entry, false);
                else focus(entry.parent);
                break;
            default: return;
            }
            event.preventDefault();
        };
        if (bulkToggle) bulkToggle.onclick = function() {
            var value = !allExpanded();
            entries.forEach(function(entry) { if (entry.children.length) state[entry.index] = value; });
            render(); save();
        };
        render();
        return {reveal: function(row) {
            var entry = entries.filter(function(item) { return item.row === row; })[0];
            if (!entry) return;
            for (var parent = entry.parent; parent; parent = parent.parent) state[parent.index] = true;
            render(); save();
        }};
    }

    return {initBookTocTree: initBookTocTree};
});
