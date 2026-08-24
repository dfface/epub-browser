(function(root, factory) {
    var api = factory();
    if (typeof module !== 'undefined' && module.exports) {
        module.exports = api;
    } else {
        root.EpubReaderLayout = api;
    }
})(typeof self !== 'undefined' ? self : this, function() {
    var DEFAULT_PAGE_WIDTH = '3';
    var DEFAULT_NAVIGATION_BEHAVIOR = 'normal';
    var NAVIGATION_BEHAVIOR_KEY = 'navigation_bar_behavior';
    var NAVIGATION_BEHAVIORS = ['normal', 'sticky', 'auto-hide'];
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

    function normalizeNavigationBehavior(value) {
        value = String(value || '');
        return NAVIGATION_BEHAVIORS.indexOf(value) !== -1
            ? value
            : DEFAULT_NAVIGATION_BEHAVIOR;
    }

    function createNavigationBehaviorController(options) {
        options = options || {};
        var header = options.header;
        var rootElement = options.rootElement;
        var documentObject = options.documentObject || {};
        var storage = options.storage;
        var previousScrollY = 0;
        var mode = DEFAULT_NAVIGATION_BEHAVIOR;

        try {
            mode = normalizeNavigationBehavior(storage && storage.getItem(NAVIGATION_BEHAVIOR_KEY));
        } catch (error) {
            mode = DEFAULT_NAVIGATION_BEHAVIOR;
        }

        function headerHeight() {
            if (!header || typeof header.getBoundingClientRect !== 'function') return 0;
            return Math.max(0, Math.ceil(header.getBoundingClientRect().height || 0));
        }

        function focusedWithinHeader() {
            return Boolean(
                header && typeof header.contains === 'function' &&
                documentObject.activeElement && header.contains(documentObject.activeElement)
            );
        }

        function showNavigation() {
            if (header) header.classList.remove('is-navigation-hidden');
        }

        function updateOffset() {
            if (!rootElement || !rootElement.style) return;
            var offset = mode === 'normal' ? 0 : headerHeight() + 8;
            rootElement.style.setProperty('--reader-navigation-offset', offset + 'px');
        }

        function applyMode(nextMode) {
            mode = normalizeNavigationBehavior(nextMode);
            if (rootElement) rootElement.setAttribute('data-navigation-behavior', mode);
            if (header) {
                header.classList.remove('is-navigation-sticky', 'is-navigation-auto-hide');
                header.classList.add(mode === 'auto-hide' ? 'is-navigation-auto-hide' : (
                    mode === 'sticky' ? 'is-navigation-sticky' : 'is-navigation-normal'
                ));
            }
            showNavigation();
            updateOffset();
            return mode;
        }

        function setMode(nextMode) {
            var applied = applyMode(nextMode);
            try {
                if (storage) storage.setItem(NAVIGATION_BEHAVIOR_KEY, applied);
            } catch (error) {}
            return applied;
        }

        function handleScroll(nextScrollY) {
            nextScrollY = Math.max(0, Number(nextScrollY) || 0);
            var delta = nextScrollY - previousScrollY;
            if (mode !== 'auto-hide' || focusedWithinHeader()) {
                showNavigation();
            } else if (delta > 4 && nextScrollY > headerHeight()) {
                if (header) header.classList.add('is-navigation-hidden');
            } else if (delta < -4) {
                showNavigation();
            }
            previousScrollY = nextScrollY;
        }

        applyMode(mode);
        return {
            getMode: function() { return mode; },
            handleScroll: handleScroll,
            refreshOffset: updateOffset,
            setMode: setMode,
            show: showNavigation
        };
    }

    function initNavigationBehavior(root) {
        var documentObject = root && root.document;
        if (!documentObject || !documentObject.querySelector) return null;
        var header = documentObject.querySelector('.app-header');
        if (!header || header.getAttribute('data-navigation-behavior-bound') === 'true') return null;
        header.setAttribute('data-navigation-behavior-bound', 'true');
        var storage = null;
        try { storage = root.localStorage; } catch (error) {}
        var controller = createNavigationBehaviorController({
            header: header,
            rootElement: documentObject.documentElement,
            documentObject: documentObject,
            storage: storage
        });
        var radios = documentObject.querySelectorAll('input[name="navigationBehavior"]');

        function syncRadios() {
            Array.prototype.forEach.call(radios, function(radio) {
                radio.checked = radio.value === controller.getMode();
            });
        }

        Array.prototype.forEach.call(radios, function(radio) {
            radio.addEventListener('change', function() {
                if (radio.checked) {
                    controller.setMode(radio.value);
                    syncRadios();
                }
            });
        });
        syncRadios();

        var framePending = false;
        root.addEventListener('scroll', function() {
            if (framePending) return;
            framePending = true;
            root.requestAnimationFrame(function() {
                framePending = false;
                controller.handleScroll(root.pageYOffset || documentObject.documentElement.scrollTop || 0);
            });
        }, { passive: true });
        header.addEventListener('focusin', controller.show);
        root.addEventListener('resize', controller.refreshOffset);
        if (typeof root.ResizeObserver === 'function') {
            new root.ResizeObserver(controller.refreshOffset).observe(header);
        }
        return controller;
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
        createNavigationBehaviorController: createNavigationBehaviorController,
        initNavigationBehavior: initNavigationBehavior,
        normalizeNavigationBehavior: normalizeNavigationBehavior,
        normalizePageWidth: normalizePageWidth,
        syncChapterTocAvailability: syncChapterTocAvailability
    };
});

if (typeof window !== 'undefined' && window.document) {
    if (window.document.readyState === 'loading') {
        window.document.addEventListener('DOMContentLoaded', function() {
            window.EpubReaderLayout.initNavigationBehavior(window);
        });
    } else {
        window.EpubReaderLayout.initNavigationBehavior(window);
    }
}
