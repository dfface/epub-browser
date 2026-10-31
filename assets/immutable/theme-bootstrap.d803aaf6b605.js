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

    function storedTheme(root) {
        var value = root.epubBrowserCache && root.epubBrowserCache.theme;
        if (!value) {
            try { value = root.localStorage && root.localStorage.getItem('theme'); } catch (error) { value = null; }
        }
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

    return { apply: apply, storedTheme: storedTheme };
});
