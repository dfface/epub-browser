const CACHE_NAME = 'epub-browser-v7';

const STATIC_ASSETS = [
    '/',
    '/index.html',
    '/assets/library.css',
    '/assets/library.js',
    '/assets/book.css',
    '/assets/book.js',
    '/assets/chapter.css',
    '/assets/chapter.js',
    '/assets/fa.all.min.css',
    '/assets/sortable.min.js',
    '/assets/medium-zoom.min.js',
    '/assets/manifest.json',
    '/assets/icon-192.png',
    '/assets/icon-512.png',
    '/assets/screenshot-wide.png',
    '/assets/screenshot-narrow.png'
];

// 安装事件 - 预缓存静态资源
self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME)
            .then((cache) => {
                console.log('Caching static assets');
                return cache.addAll(STATIC_ASSETS);
            })
            .catch((error) => {
                console.log('Failed to cache:', error);
            })
    );
    self.skipWaiting();
});

// 激活事件
self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys().then((cacheNames) => {
            return Promise.all(
                cacheNames.map((cacheName) => {
                    if (cacheName !== CACHE_NAME) {
                        console.log('Deleting old cache:', cacheName);
                        return caches.delete(cacheName);
                    }
                })
            );
        })
    );
    self.clients.claim();
});

// 监听消息（清除缓存）
self.addEventListener('message', (event) => {
    if (event.data && event.data.action === 'CLEAR_CACHE') {
        event.waitUntil(
            caches.delete(CACHE_NAME).then(() => {
                console.log('Cache cleared:', CACHE_NAME);
                // 重新预缓存静态资源
                return caches.open(CACHE_NAME).then((cache) => {
                    return cache.addAll(STATIC_ASSETS);
                });
            })
        );
    }
});

// 判断是否应该缓存该请求
function shouldCache(url) {
    const urlObj = new URL(url);
    const pathname = urlObj.pathname;
    
    // 缓存静态资源
    if (pathname.startsWith('/assets/')) {
        return true;
    }
    
    // 缓存书籍页面
    if (pathname.startsWith('/book/')) {
        return true;
    }
    
    // 缓存根页面
    if (pathname === '/' || pathname === '/index.html') {
        return true;
    }
    
    return false;
}

// 请求拦截
self.addEventListener('fetch', (event) => {
    // 只处理 GET 请求
    if (event.request.method !== 'GET') {
        return;
    }

    // 只处理同源请求
    if (!event.request.url.startsWith(self.location.origin)) {
        return;
    }

    // 对于导航请求（页面跳转），使用网络优先策略
    if (event.request.mode === 'navigate') {
        event.respondWith(
            fetch(event.request)
                .then((response) => {
                    // 缓存响应
                    if (response && response.status === 200) {
                        const responseToCache = response.clone();
                        caches.open(CACHE_NAME)
                            .then((cache) => {
                                cache.put(event.request, responseToCache);
                            });
                    }
                    return response;
                })
                .catch(() => {
                    // 网络失败时，返回缓存
                    return caches.match(event.request)
                        .then((cachedResponse) => {
                            return cachedResponse || caches.match('/index.html');
                        });
                })
        );
        return;
    }

    // 其他请求使用缓存优先策略
    event.respondWith(
        caches.match(event.request)
            .then((cachedResponse) => {
                // 如果有缓存，返回缓存
                if (cachedResponse) {
                    return cachedResponse;
                }

                // 否则从网络获取
                return fetch(event.request)
                    .then((response) => {
                        // 检查是否是有效的响应
                        if (!response || response.status !== 200) {
                            return response;
                        }

                        // 如果应该缓存，则缓存响应
                        if (shouldCache(event.request.url)) {
                            const responseToCache = response.clone();
                            caches.open(CACHE_NAME)
                                .then((cache) => {
                                    cache.put(event.request, responseToCache);
                                });
                        }

                        return response;
                    })
                    .catch(() => {
                        // 如果网络请求失败，尝试返回缓存的首页
                        if (event.request.destination === 'document') {
                            return caches.match('/index.html');
                        }
                    });
            })
    );
});
