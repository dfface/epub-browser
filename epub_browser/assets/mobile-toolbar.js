(function(root, factory) {
    var api = factory();
    if (typeof module !== 'undefined' && module.exports) module.exports = api;
    else root.EpubMobileToolbar = api;
})(typeof self !== 'undefined' ? self : this, function() {
    var KEY = 'mobileToolbarOrder';
    var DEFAULT_ORDER = [
        'mobileTocBtn', 'mobileBookHomeBtn', 'mobilePdfSearchToggle',
        'mobilePdfZoomOut', 'mobilePdfZoomIn', 'mobilePdfFitWidth',
        'mobilePdfFitPage', 'mobilePdfRotate', 'mobileBookSearchToggle',
        'mobileAIReadingBtn', 'mobileAIChatBtn', 'mobilePrevChapter',
        'mobileHomeBtn', 'mobileNextChapter', 'mobilePageJumpBtn',
        'mobileSettingsBtn', 'mobileBookHomeShortcut', 'mobileTopBtn'
    ];

    function createOrderModel(storage, defaults) {
        var saved;
        try { saved = JSON.parse(storage.getItem(KEY)); } catch (error) {}
        var order = Array.isArray(saved) ? saved.filter(function(id, index) {
            return typeof id === 'string' && defaults.indexOf(id) !== -1 && saved.indexOf(id) === index;
        }) : [];
        defaults.forEach(function(id, index) {
            if (order.indexOf(id) !== -1) return;
            var previous = index > 0 ? order.indexOf(defaults[index - 1]) : -1;
            order.splice(previous + 1, 0, id);
        });
        function save() { storage.setItem(KEY, JSON.stringify(order)); }
        return {
            order: function() { return order.slice(); },
            move: function(id, direction, visible) {
                var index = visible.indexOf(id);
                var other = visible[index + direction];
                if (index < 0 || !other || (direction !== -1 && direction !== 1)) return;
                var from = order.indexOf(id), to = order.indexOf(other);
                order[from] = other;
                order[to] = id;
                save();
            },
            reorder: function(visible) {
                var remaining = visible.filter(function(id, index) {
                    return order.indexOf(id) !== -1 && visible.indexOf(id) === index;
                });
                var ids = remaining.slice();
                order = order.map(function(id) { return ids.indexOf(id) !== -1 ? remaining.shift() : id; });
                save();
            },
            reset: function() { order = defaults.slice(); storage.removeItem(KEY); }
        };
    }

    function init(options) {
        var doc = options.document, toolbar = options.toolbar, i18n = options.i18n;
        var list = doc.getElementById('mobileToolbarOrderList');
        var toggle = doc.getElementById('mobileToolbarOrderToggle');
        var panel = doc.getElementById('mobileToolbarOrderPanel');
        var reset = doc.getElementById('mobileToolbarOrderReset');
        var status = doc.getElementById('mobileToolbarOrderStatus');
        if (!toolbar || !list || !toggle || !panel || !reset) return;
        var controls = Array.prototype.slice.call(toolbar.children).filter(function(node) { return !!node.id; });
        var defaults = DEFAULT_ORDER.slice();
        controls.forEach(function(node) { if (defaults.indexOf(node.id) === -1) defaults.push(node.id); });
        var model = createOrderModel(options.storage, defaults);
        function apply() {
            model.order().forEach(function(id) {
                var node = controls.find(function(item) { return item.id === id; });
                if (node) toolbar.appendChild(node);
            });
        }
        function editable() {
            return Array.prototype.slice.call(toolbar.children).filter(function(node) {
                return !!node.id && !(options.pdf && node.id === 'mobileTocBtn');
            });
        }
        function text(key, params) { return i18n.t(key, params); }
        function announce(node) {
            if (status) status.textContent = text('settings.toolbarMoved', {
                name: label(node), position: editable().indexOf(node) + 1
            });
        }
        function label(node) {
            var span = node.querySelector('[data-i18n]');
            return span ? text(span.getAttribute('data-i18n')) : node.getAttribute('aria-label') || node.id;
        }
        function render(focusId, action) {
            list.textContent = '';
            var nodes = editable();
            nodes.forEach(function(node, index) {
                var row = doc.createElement('li');
                row.className = 'mobile-toolbar-order-row';
                row.dataset.controlId = node.id;
                var handle = doc.createElement('span');
                handle.className = 'mobile-toolbar-drag-handle';
                handle.setAttribute('aria-hidden', 'true');
                handle.textContent = '⠿';
                var name = doc.createElement('span');
                name.className = 'mobile-toolbar-order-name';
                name.textContent = label(node);
                row.appendChild(handle);
                var icon = node.querySelector('i');
                if (icon) {
                    var copy = icon.cloneNode(false);
                    copy.setAttribute('aria-hidden', 'true');
                    row.appendChild(copy);
                }
                row.appendChild(name);
                [-1, 1].forEach(function(direction) {
                    var button = doc.createElement('button');
                    var key = direction === -1 ? 'settings.toolbarMoveUp' : 'settings.toolbarMoveDown';
                    button.type = 'button';
                    button.className = 'mobile-toolbar-move';
                    button.dataset.direction = direction;
                    button.textContent = direction === -1 ? '↑' : '↓';
                    button.setAttribute('aria-label', text(key, { name: label(node) }));
                    button.disabled = direction === -1 ? index === 0 : index === nodes.length - 1;
                    button.addEventListener('click', function() {
                        model.move(node.id, direction, nodes.map(function(item) { return item.id; }));
                        apply();
                        render(node.id, direction);
                        announce(node);
                    });
                    row.appendChild(button);
                });
                list.appendChild(row);
            });
            if (focusId) {
                var row = Array.prototype.find.call(list.children, function(item) { return item.dataset.controlId === focusId; });
                if (row) {
                    var button = row.querySelector('[data-direction="' + action + '"]');
                    // Keep focus on the moved item even at the end of the list.
                    if (button.disabled) button = row.querySelector('button:not(:disabled)');
                    if (button) button.focus();
                }
            }
        }
        toggle.addEventListener('click', function() {
            panel.hidden = !panel.hidden;
            toggle.setAttribute('aria-expanded', panel.hidden ? 'false' : 'true');
            if (!panel.hidden) render();
        });
        reset.addEventListener('click', function() {
            model.reset();
            apply();
            render();
            if (status) status.textContent = text('settings.toolbarResetDone');
        });
        if (options.Sortable) {
            new options.Sortable(list, {
                handle: '.mobile-toolbar-drag-handle', animation: 150,
                onEnd: function(event) {
                    model.reorder(Array.prototype.map.call(list.children, function(row) { return row.dataset.controlId; }));
                    apply();
                    var node = controls.find(function(item) { return item.id === event.item.dataset.controlId; });
                    render();
                    if (node) announce(node);
                }
            });
        }
        if (i18n.onLocaleChange) i18n.onLocaleChange(function() {
            if (!panel.hidden) render();
            if (status) status.textContent = '';
        });
        apply();
    }
    return { createOrderModel: createOrderModel, init: init };
});
