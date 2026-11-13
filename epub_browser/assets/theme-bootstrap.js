(function(root, factory) {
    var api = factory();
    if (typeof module === 'object' && module.exports) module.exports = api;
    if (root && root.document) {
        root.EpubBrowserThemeBootstrap = api;
        api.apply(root);
    }
})(typeof window !== 'undefined' ? window : (typeof globalThis !== 'undefined' ? globalThis : this), function() {
    'use strict';

    var themes = ['light', 'dark', 'sepia', 'forest', 'ocean', 'peach', 'lavender'];

    function read(root, key) {
        try { return root.localStorage.getItem(key); } catch (error) { return null; }
    }

    function write(root, key, value) {
        try { root.localStorage.setItem(key, value); } catch (error) { /* Keep the in-page preference. */ }
    }

    function preferences(root) {
        var saved = root.EpubBrowserAppearance || {};
        return {
            automatic: saved.automatic === true,
            day: themes.indexOf(saved.day) === -1 ? 'light' : saved.day,
            night: themes.indexOf(saved.night) === -1 ? 'dark' : saved.night,
            manual: themes.indexOf(saved.manual) === -1 ? 'light' : saved.manual
        };
    }

    function saveManualTheme(root, theme) {
        root.epubBrowserCache = root.epubBrowserCache || {};
        root.epubBrowserCache.manualTheme = theme;
        write(root, 'theme', theme);
    }

    function deviceScheme(root) {
        return typeof root.matchMedia === 'function' ? root.matchMedia('(prefers-color-scheme: dark)') : null;
    }

    function storedTheme(root) {
        if (root.EpubBrowserMode === 'server') {
            var saved = preferences(root);
            if (saved.automatic) {
                var scheme = deviceScheme(root);
                return scheme && scheme.matches ? saved.night : saved.day;
            }
            return saved.manual;
        }
        var value = (root.epubBrowserCache && root.epubBrowserCache.manualTheme) || read(root, 'theme');
        return themes.indexOf(value) === -1 ? 'light' : value;
    }

    function apply(root) {
        if (!root || !root.document || !root.document.documentElement) return 'light';
        var theme = storedTheme(root);
        var classList = root.document.documentElement.classList;
        themes.forEach(function(name) { classList.remove(name + '-mode'); });
        classList.add(theme + '-mode');
        if (!root.epubBrowserCache) root.epubBrowserCache = {};
        root.epubBrowserCache.theme = theme;
        return theme;
    }

    return {
        apply: apply,
        storedTheme: storedTheme,
        preferences: preferences,
        saveManualTheme: saveManualTheme,
        deviceScheme: deviceScheme
    };
});
