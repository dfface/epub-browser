const CACHE_NAME = 'epub-browser-__EPUB_BROWSER_RELEASE_ID__';
const PRECACHE_URLS = __EPUB_BROWSER_PRECACHE_URLS__;
const MUTABLE_MANIFEST_URLS = new Set([
    '/assets/manifest.json',
    '/assets/manifest.en.json',
    '/assets/manifest.zh-CN.json',
]);

self.addEventListener('install', (event) => {
    event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.addAll(PRECACHE_URLS)));
    self.skipWaiting();
});

self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys().then((names) => Promise.all(
            names.filter((name) => name.startsWith('epub-browser-') && name !== CACHE_NAME)
                .map((name) => caches.delete(name))
        ))
    );
    self.clients.claim();
});

function isPrecachedAsset(request) {
    return PRECACHE_URLS.includes(new URL(request.url).pathname);
}

function isMutableManifest(request) {
    return MUTABLE_MANIFEST_URLS.has(new URL(request.url).pathname);
}

async function networkFirst(request, fallbackUrl) {
    try {
        const response = await fetch(request);
        if (response && response.status === 200) {
            caches.open(CACHE_NAME).then((cache) => cache.put(request, response.clone()));
        }
        return response;
    } catch (error) {
        const cached = await caches.match(request);
        if (cached) return cached;
        if (fallbackUrl) return caches.match(fallbackUrl);
        return Response.error();
    }
}

self.addEventListener('fetch', (event) => {
    if (event.request.method !== 'GET' || !event.request.url.startsWith(self.location.origin)) return;

    if (isMutableManifest(event.request)) {
        event.respondWith(networkFirst(event.request));
        return;
    }

    if (isPrecachedAsset(event.request)) {
        event.respondWith(caches.match(event.request).then((cached) => cached || fetch(event.request)));
        return;
    }

    event.respondWith(networkFirst(event.request, event.request.mode === 'navigate' ? '/index.html' : null));
});
