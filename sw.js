const CACHE_NAME = 'epub-browser-e469b3351f55';
const PRECACHE_URLS = ["/index.html","/assets/immutable/account.b50f878e90fc.css","/assets/immutable/annotation-hub.1c2b34b3118c.css","/assets/immutable/annotation-hub.b3aad98b6207.js","/assets/immutable/annotation-position.df7b410bbafb.js","/assets/immutable/annotation.752bf04a87e8.css","/assets/immutable/annotation.6d0efc58939b.js","/assets/immutable/auth.093c456d5fc9.js","/assets/immutable/book.92a860471e04.css","/assets/immutable/book.854989d5db3e.js","/assets/immutable/bookshelf.765c441cdf1c.css","/assets/immutable/bookshelf.9d1bbea30a7a.js","/assets/immutable/breadcrumb.061bc87d8306.css","/assets/immutable/cache-boundary.41fc48a34cbe.js","/assets/immutable/chapter-window.8d2c13e8f216.js","/assets/immutable/chapter.79ce7d06045e.css","/assets/immutable/chapter.acbfdb4ad398.js","/assets/immutable/continuous-buffer.27eaf6de1887.js","/assets/immutable/dialog.e8978fa5eb89.css","/assets/immutable/dialog.80217164cb29.js","/assets/immutable/fa-solid-900.0464086a7d67.woff2","/assets/immutable/fa.all.min.0800fc6965d0.css","/assets/immutable/fancybox.min.b175fce88bfe.css","/assets/immutable/fancybox.min.427255e074f9.js","/assets/immutable/favicon.413482070e46.png","/assets/immutable/github-dark.min.9f208d022102.css","/assets/immutable/github.min.3a9a5def8b9c.css","/assets/immutable/highlight.min.c4a399dd6f48.js","/assets/immutable/i18n.0efdec3fb0df.js","/assets/immutable/icon-192.c6f7d6e5a9b6.png","/assets/immutable/icon-512.2ac1ce7d0c7c.png","/assets/immutable/library-progress.323ed6beec3c.css","/assets/immutable/library-progress.95726bc13f29.js","/assets/immutable/library.e99d7ef11fc1.css","/assets/immutable/library.34c62d129027.js","/assets/immutable/loading.56e36e52fd23.css","/assets/immutable/logo-lockup-color.6e46b73d2019.png","/assets/immutable/logo-mark-color.ef9a3679a944.png","/assets/immutable/logo-mark-outline.4b70e08ef6e0.png","/assets/immutable/notification.6219e1c21c4a.css","/assets/immutable/notification.7492663447d4.js","/assets/immutable/pinyin-pro.min.38a5d585c3af.js","/assets/immutable/reader-layout.6f67c4c1e04c.js","/assets/immutable/reading-progress.653eacfc5c3b.js","/assets/immutable/screenshot-narrow.b18b2c94a054.png","/assets/immutable/screenshot-wide.561f1fb31ff3.png","/assets/immutable/sortable.min.6d0a831fc19b.js","/assets/immutable/theme-bootstrap.d803aaf6b605.js","/assets/immutable/theme.08019b8f3707.css","/assets/immutable/theme.be1f4df08989.js","/assets/immutable/version-check.47351de03846.js","/assets/immutable/viewport-anchor.021abaa5aa16.js","/assets/immutable/web-highlighter.min.7360ce01d835.js","/assets/manifest.json","/assets/manifest.en.json","/assets/manifest.zh-CN.json"];
const MUTABLE_MANIFEST_URLS = new Set(["/assets/manifest.json","/assets/manifest.en.json","/assets/manifest.zh-CN.json"]);
const INDEX_URL = "/index.html";

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

    event.respondWith(networkFirst(event.request, event.request.mode === 'navigate' ? INDEX_URL : null));
});
