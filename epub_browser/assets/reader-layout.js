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
    var NAVIGATION_MOTION_THRESHOLD = 4;
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

    function getPaginationPageWidth(container) {
        if (!container) return 0;
        var rect = typeof container.getBoundingClientRect === 'function'
            ? container.getBoundingClientRect()
            : null;
        var width = rect && Number(rect.width);
        if (Number.isFinite(width) && width > 0) return width;
        return Math.max(0, Number(container.clientWidth) || 0);
    }

    function getPaginationScrollLeft(pageIndex, pageWidth) {
        return Math.round(Math.max(0, Number(pageIndex) || 0) * Math.max(0, Number(pageWidth) || 0));
    }

    function paginationWidthChanged(previousWidth, nextWidth) {
        return Math.abs((Number(nextWidth) || 0) - (Number(previousWidth) || 0)) > 0.01;
    }

    function readingPreferenceEnabled(value) {
        return value !== 'false';
    }

    function chapterNavigationPresentation(item, pdf, translate) {
        item = item || {};
        var outlineLabels = Array.isArray(item.outline_labels)
            ? item.outline_labels.filter(function(label) { return typeof label === 'string' && label; })
            : [];
        var title = typeof item.title === 'string' ? item.title : '';
        if (pdf && item.page_label !== undefined && typeof translate === 'function') {
            title = translate('pdf.page', { number: item.page_label });
        }
        return { title: title, outlineLabels: outlineLabels };
    }

    function continuousChapterPresentation(chapterTitle, chapterIndex, pdf, translate) {
        var index = Number(chapterIndex) || 0;
        if (pdf && typeof translate === 'function') {
            var page = translate('pdf.page', { number: index + 1 });
            return { title: page, index: page };
        }
        return {
            title: chapterTitle || translate('reader.chapterNumber', { number: index }),
            index: translate('reader.chapterNumber', { number: index })
        };
    }

    function isEditableNavigationNode(node) {
        if (!node || typeof node !== 'object') return false;
        var tagName = String(node.tagName || '').toUpperCase();
        if (
            tagName === 'INPUT' || tagName === 'TEXTAREA' || tagName === 'SELECT' ||
            tagName === 'BUTTON' || tagName === 'A' || tagName === 'SUMMARY' ||
            tagName === 'DIALOG' || tagName === 'OPTION'
        ) return true;
        if (node.isContentEditable === true) return true;
        if (typeof node.getAttribute === 'function') {
            var contentEditable = node.getAttribute('contenteditable');
            if (contentEditable !== null && String(contentEditable).toLowerCase() !== 'false') return true;
            var role = String(node.getAttribute('role') || '').toLowerCase();
            if (
                role === 'button' || role === 'link' || role === 'textbox' ||
                role === 'combobox' || role === 'listbox' || role === 'menu' ||
                role === 'dialog' || role === 'alertdialog'
            ) return true;
        }
        return false;
    }

    function navigationEventPath(event) {
        if (event && typeof event.composedPath === 'function') {
            try {
                var composed = event.composedPath();
                if (composed && composed.length) return composed;
            } catch (error) {}
        }
        var path = [];
        var node = event && event.target;
        while (node) {
            path.push(node);
            node = node.parentElement || node.parentNode || node.host || null;
        }
        return path;
    }

    function allowsReaderNavigationEvent(event, arrowEnabled, spaceEnabled) {
        if (!event || event.defaultPrevented || event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) {
            return false;
        }
        var path = navigationEventPath(event);
        for (var i = 0; i < path.length; i++) {
            if (isEditableNavigationNode(path[i])) return false;
        }
        if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') return Boolean(arrowEnabled);
        if (event.key === ' ' || event.key === 'Space' || event.key === 'Spacebar') return Boolean(spaceEnabled);
        return true;
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
        var getScrollY = typeof options.getScrollY === 'function' ? options.getScrollY : null;
        var previousScrollY = Math.max(0, Number(options.initialScrollY) || 0);
        var accumulatedMotion = 0;
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

        function navigationOwnsFocus() {
            var focusedWithinHeader = Boolean(
                header && typeof header.contains === 'function' &&
                documentObject.activeElement && header.contains(documentObject.activeElement)
            );
            var localeToggle = typeof documentObject.getElementById === 'function'
                ? documentObject.getElementById('localeToggle')
                : null;
            return focusedWithinHeader || Boolean(
                localeToggle && localeToggle.getAttribute('aria-expanded') === 'true'
            );
        }

        function revealNavigation() {
            if (header) header.classList.remove('is-navigation-hidden');
        }

        function currentScrollY() {
            if (!getScrollY) return previousScrollY;
            return Math.max(0, Number(getScrollY()) || 0);
        }

        function resetMotion(scrollY) {
            accumulatedMotion = 0;
            previousScrollY = Math.max(0, Number(scrollY) || 0);
        }

        function showNavigation() {
            revealNavigation();
            resetMotion(currentScrollY());
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
                header.classList.remove(
                    'is-navigation-normal',
                    'is-navigation-sticky',
                    'is-navigation-auto-hide'
                );
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
            previousScrollY = nextScrollY;
            if (mode !== 'auto-hide' || navigationOwnsFocus() || nextScrollY <= headerHeight()) {
                revealNavigation();
                accumulatedMotion = 0;
                return;
            }
            if (!delta) return;
            var directionChanged = (
                (accumulatedMotion > 0 && delta < 0) ||
                (accumulatedMotion < 0 && delta > 0)
            );
            if (directionChanged) {
                accumulatedMotion = delta;
            } else {
                accumulatedMotion += delta;
            }
            var hidden = Boolean(header && header.classList.contains('is-navigation-hidden'));
            if (accumulatedMotion > NAVIGATION_MOTION_THRESHOLD && !hidden) {
                if (header) header.classList.add('is-navigation-hidden');
                accumulatedMotion = 0;
            } else if (accumulatedMotion < -NAVIGATION_MOTION_THRESHOLD && hidden) {
                revealNavigation();
                accumulatedMotion = 0;
            }
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
        function readScrollY() {
            return root.pageYOffset || documentObject.documentElement.scrollTop || 0;
        }
        var controller = createNavigationBehaviorController({
            header: header,
            rootElement: documentObject.documentElement,
            documentObject: documentObject,
            storage: storage,
            initialScrollY: readScrollY(),
            getScrollY: readScrollY
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
                controller.handleScroll(readScrollY());
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

    function syncChapterTocAvailability(documentObject, continuous, pdf) {
        var disabled = Boolean(continuous || pdf);
        var controls = [
            documentObject.getElementById('tocToggle'),
            documentObject.getElementById('mobileTocBtn')
        ];
        controls.forEach(function(control) {
            setDisabled(control, disabled);
            if (!control) return;
            control.hidden = disabled;
            control.setAttribute('aria-hidden', disabled ? 'true' : 'false');
        });

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
        allowsReaderNavigationEvent: allowsReaderNavigationEvent,
        applyPageWidth: applyPageWidth,
        chapterNavigationPresentation: chapterNavigationPresentation,
        continuousChapterPresentation: continuousChapterPresentation,
        createNavigationBehaviorController: createNavigationBehaviorController,
        getPaginationPageWidth: getPaginationPageWidth,
        getPaginationScrollLeft: getPaginationScrollLeft,
        initNavigationBehavior: initNavigationBehavior,
        normalizeNavigationBehavior: normalizeNavigationBehavior,
        normalizePageWidth: normalizePageWidth,
        paginationWidthChanged: paginationWidthChanged,
        readingPreferenceEnabled: readingPreferenceEnabled,
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
