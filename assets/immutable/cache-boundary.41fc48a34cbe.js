(function(root) {
    function workerPath() {
        if (root.EpubBrowserURL && root.EpubBrowserURL.publicPath) {
            return root.EpubBrowserURL.publicPath('/sw.js');
        }
        return (root.EpubBrowserBasePath || '/') + 'sw.js';
    }

    function workerURL() {
        return new URL(workerPath(), root.location.href).href;
    }

    function appScope() {
        return new URL(root.EpubBrowserBasePath || '/', root.location.href).href;
    }

    function workerReference(registration) {
        return registration.active || registration.waiting || registration.installing;
    }

    function isLibraryWorker(reference) {
        return Boolean(reference && reference.scriptURL === workerURL());
    }

    function isLibraryRegistration(registration) {
        var reference = workerReference(registration);
        return isLibraryWorker(reference) || registration.scope === appScope();
    }

    function registrations(serviceWorker) {
        if (!serviceWorker) return Promise.resolve([]);
        if (typeof serviceWorker.getRegistrations === 'function') {
            return Promise.resolve(serviceWorker.getRegistrations());
        }
        if (typeof serviceWorker.getRegistration === 'function') {
            return Promise.resolve(serviceWorker.getRegistration(appScope()))
                .then(function(registration) {
                    return registration ? [registration] : [];
                });
        }
        return Promise.reject(new Error('Service worker registrations cannot be inspected'));
    }

    function unregisterLibraryWorkers(serviceWorker) {
        return registrations(serviceWorker).then(function(items) {
            return Promise.all(items.filter(isLibraryRegistration).map(function(registration) {
                return Promise.resolve(registration.unregister()).then(function(removed) {
                    if (removed === false) {
                        throw new Error('Service worker registration could not be removed');
                    }
                });
            }));
        });
    }

    function clearLibraryCaches() {
        if (!root.caches) return Promise.resolve();
        return Promise.resolve(root.caches.keys()).then(function(names) {
            return Promise.all(names.filter(function(name) {
                return name.indexOf('epub-browser-') === 0;
            }).map(function(name) {
                return Promise.resolve(root.caches.delete(name)).then(function(removed) {
                    if (removed === false) {
                        throw new Error('EPUB Browser cache could not be removed');
                    }
                });
            }));
        });
    }

    function prepare() {
        if (root.EpubBrowserMode !== 'server') return Promise.resolve(true);
        var serviceWorker = root.navigator && root.navigator.serviceWorker;
        var controller = serviceWorker && serviceWorker.controller;
        var controlledByLibraryWorker = isLibraryWorker(controller);
        if (controller && !controlledByLibraryWorker) return Promise.resolve(false);
        if (controlledByLibraryWorker && !root.caches) return Promise.resolve(false);

        return Promise.all([
            unregisterLibraryWorkers(serviceWorker),
            clearLibraryCaches(),
        ]).then(function() {
            if (!controlledByLibraryWorker) return true;
            if (root.location && typeof root.location.reload === 'function') {
                root.location.reload();
            }
            return false;
        }, function() {
            return false;
        });
    }

    function start(callback) {
        return prepare().then(function(ready) {
            return ready ? callback() : null;
        });
    }

    function registerWorker() {
        var serviceWorker = root.navigator && root.navigator.serviceWorker;
        if (
            root.EpubBrowserMode === 'server'
            || !serviceWorker
            || typeof serviceWorker.register !== 'function'
        ) {
            return Promise.resolve(null);
        }
        return Promise.resolve(serviceWorker.register(workerPath()));
    }

    root.EpubBrowserCacheBoundary = {
        prepare: prepare,
        start: start,
        registerWorker: registerWorker,
    };
})(window);
