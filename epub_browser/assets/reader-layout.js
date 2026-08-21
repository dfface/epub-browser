(function(root, factory) {
    var api = factory();
    if (typeof module !== 'undefined' && module.exports) {
        module.exports = api;
    } else {
        root.EpubReaderLayout = api;
    }
})(typeof self !== 'undefined' ? self : this, function() {
    var DEFAULT_PAGE_WIDTH = '3';
    var PAGE_WIDTHS = {
        '1': 680,
        '2': 820,
        '3': 1000,
        '4': 1200
    };

    function normalizePageWidth(value) {
        var key = String(value || '');
        return Object.prototype.hasOwnProperty.call(PAGE_WIDTHS, key)
            ? key
            : DEFAULT_PAGE_WIDTH;
    }

    function applyPageWidth(rootElement, value) {
        var preset = normalizePageWidth(value);
        if (rootElement && rootElement.style) {
            rootElement.style.setProperty('--reader-page-width', PAGE_WIDTHS[preset] + 'px');
            rootElement.setAttribute('data-reader-page-width', preset);
        }
        return preset;
    }

    function setDisabled(control, disabled) {
        if (!control) return;
        control.disabled = disabled;
        control.setAttribute('aria-disabled', disabled ? 'true' : 'false');
        if (disabled) {
            control.setAttribute('aria-expanded', 'false');
            control.classList.remove('active');
        }
    }

    function syncChapterTocAvailability(documentObject, continuous) {
        var disabled = Boolean(continuous);
        setDisabled(documentObject.getElementById('tocToggle'), disabled);
        setDisabled(documentObject.getElementById('mobileTocBtn'), disabled);

        if (disabled) {
            var drawer = documentObject.getElementById('tocFloating');
            if (drawer) {
                drawer.classList.remove('active');
                drawer.setAttribute('aria-hidden', 'true');
            }
        }
    }

    return {
        PAGE_WIDTHS: PAGE_WIDTHS,
        applyPageWidth: applyPageWidth,
        normalizePageWidth: normalizePageWidth,
        syncChapterTocAvailability: syncChapterTocAvailability
    };
});
