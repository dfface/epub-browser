(function(root) {
    'use strict';

    var database;
    var server = function() { return root.EpubBrowserMode === 'server'; };
    var site = function() { return root.EpubBrowserBasePath || '/'; };
    var open = function() {
        if (!database) {
            database = new Promise(function(resolve, reject) {
                var request = root.indexedDB.open('epub-browser-book-cache', 1);
                request.onupgradeneeded = function() {
                    request.result.createObjectStore('books');
                    request.result.createObjectStore('content');
                };
                request.onsuccess = function() {
                    request.result.onversionchange = function() { request.result.close(); database = null; };
                    resolve(request.result);
                };
                request.onerror = request.onblocked = function() { reject(request.error || Error('storage')); };
            }).catch(function(error) { database = null; throw error; });
        }
        return database;
    };

    function requestResult(request) {
        return new Promise(function(resolve, reject) {
            request.onsuccess = function() { resolve(request.result); };
            request.onerror = function() { reject(request.error); };
        });
    }

    async function transaction(mode, work) {
        var db = await open();
        var tx = db.transaction(['books', 'content'], mode);
        var done = new Promise(function(resolve, reject) {
            tx.oncomplete = resolve;
            tx.onabort = function() { reject(tx.error || Error('storage')); };
        });
        try {
            var result = await work(tx.objectStore('books'), tx.objectStore('content'));
            await done;
            return result;
        } catch (error) {
            try { tx.abort(); } catch (_) {}
            await done.catch(function() {});
            throw error;
        }
    }

    function supported() {
        return Boolean(root.indexedDB && root.AbortController && !root.EpubBrowserAnonymous);
    }

    async function account(fresh) {
        if (!server()) return 'static';
        var session = await root.EpubBrowserAuth.session(fresh);
        if (!session || !session.user) throw Error('session');
        return String(session.user.id);
    }

    async function activeAccount(expected) {
        var owner = await account(true);
        if (expected && owner !== expected) throw Error('session');
        return owner;
    }

    function prefix(owner) {
        return [site(), server() ? 'server' : 'ssg', owner];
    }

    function range(key) {
        return root.IDBKeyRange.bound(key, key.concat([[]]), false, true);
    }

    function publicURL(path) {
        return site().replace(/\/$/, '') + path;
    }

    function bookURL(book, file) {
        return publicURL('/book/' + encodeURIComponent(book.id) + '/' + file);
    }

    function documentURL(book) {
        return server()
            ? publicURL('/api/books/' + encodeURIComponent(book.id) + '/document')
            : bookURL(book, 'document.pdf');
    }

    async function download(url, signal) {
        var result = await root.fetch(url, {
            credentials: 'same-origin', redirect: 'error', cache: 'no-store', signal: signal,
            headers: { 'X-EPUB-Browser-Cache': 'book' }
        });
        if (result.status !== 200) throw Error('download');
        return result;
    }

    async function version(book, owner, signal) {
        if (!server()) return book.version;
        var result = await download(publicURL('/api/books/' + encodeURIComponent(book.id) + '/browser-cache'), signal);
        var stamp = await result.json();
        if (String(stamp.account) !== owner || !stamp.version) throw Error('session');
        return stamp.version;
    }

    function cacheVersion(stamp) {
        // Invalidate a stored fragment when its serialized representation changes.
        return '1:' + stamp;
    }

    function snapshot(html, book, index, stamp) {
        var template = root.document.createElement('template');
        template.innerHTML = html;
        var source = template.content;
        var article = source.querySelector('article#eb-content');
        if (!article || article.dataset.bookHash !== book.id ||
            article.dataset.chapterIndex !== String(index) ||
            (!server() && article.dataset.bookVersion !== stamp)) throw Error('version');

        var output = template.content.ownerDocument.createElement('template');
        output.content.appendChild(article);
        var title = source.querySelector('title');
        if (title) output.content.appendChild(title);
        var mobile = output.content.ownerDocument.createElement('div');
        mobile.className = 'mobile-controls';
        source.querySelectorAll('.prev-chapter, .next-chapter, .mobile-controls > a').forEach(function(link) {
            var clone = mobile.ownerDocument.createElement('a');
            clone.id = link.id;
            clone.className = link.className;
            if (link.hasAttribute('href')) clone.setAttribute('href', link.getAttribute('href'));
            (link.matches('.mobile-controls > a') ? mobile : output.content).appendChild(clone);
        });
        output.content.appendChild(mobile);
        return output.innerHTML;
    }

    async function get(book, part, probe) {
        if (!supported() || (!server() && !book.version)) return null;
        try {
            var owner = await account(false);
            var key = prefix(owner).concat([book.id]);
            var entry = await transaction('readonly', function(books) {
                return requestResult(books.get(key));
            });
            if (!entry || !entry.complete) return null;
            if (probe) return true;
            var stamp = await version(book, owner, AbortSignal.timeout ? AbortSignal.timeout(3500) : undefined);
            if (entry.version !== cacheVersion(stamp)) return null;
            return await transaction('readonly', async function(books, content) {
                var current = await requestResult(books.get(key));
                if (!current || current.token !== entry.token) return null;
                return (await requestResult(content.get(key.concat([part])))) ?? null;
            });
        } catch (_) {
            return null;
        }
    }

    async function removeForOwner(bookId, owner, expectedToken) {
        var key = prefix(owner).concat([bookId]);
        await transaction('readwrite', async function(books, content) {
            if (expectedToken) {
                var current = await requestResult(books.get(key));
                if (!current || current.token !== expectedToken) return;
            }
            books.delete(key);
            content.delete(range(key));
        });
    }

    async function remove(bookId, expected) {
        return removeForOwner(bookId, await activeAccount(expected));
    }

    async function clear(expected) {
        var owner = await activeAccount(expected);
        var keys = range(prefix(owner));
        await transaction('readwrite', function(books, content) {
            books.delete(keys);
            content.delete(keys);
        });
    }

    async function list(expected) {
        var owner = await activeAccount(expected);
        return transaction('readonly', function(books) {
            return requestResult(books.getAll(range(prefix(owner))));
        });
    }

    async function inspect(book, expected) {
        var owner = await activeAccount(expected);
        var entry = await transaction('readonly', function(books) {
            return requestResult(books.get(prefix(owner).concat([book.id])));
        });
        if (!entry) return null;
        var stamp = await version(book, owner);
        return Object.assign(entry, { current: entry.complete && entry.version === cacheVersion(stamp) });
    }

    async function pdfBlob(result, progress) {
        if (!/^application\/pdf(?:;|$)/i.test(result.headers.get('Content-Type') || '')) throw Error('download');
        if (!result.body) return result.blob();
        var reader = result.body.getReader();
        var size = 0;
        var parts = [];
        var total = Number(result.headers.get('Content-Length'));
        var reportedAt = 0;
        try {
            while (true) {
                var chunk = await reader.read();
                if (chunk.done) break;
                size += chunk.value.byteLength;
                parts.push(chunk.value);
                if (Date.now() - reportedAt > 150) {
                    reportedAt = Date.now();
                    progress(size, total ? Math.min(1, size / total) : null);
                }
            }
        } finally {
            reader.releaseLock();
        }
        return new Blob(parts, {type: 'application/pdf'});
    }

    async function save(book, signal, onProgress, expected) {
        var owner = await activeAccount(expected);
        var stamp = await version(book, owner, signal);
        if (!stamp || (book.format !== 'pdf' && !(book.count > 0))) throw Error('version');
        var key = prefix(owner).concat([book.id]);
        var entry = {
            id: book.id, title: book.title, format: book.format, token: String(Date.now()) + ':' + Math.random(),
            version: cacheVersion(stamp), size: 0, complete: false, updated: Date.now()
        };
        if (signal.aborted) throw Error('cancelled');
        await transaction('readwrite', function(books, content) {
            books.put(entry, key);
            content.delete(range(key));
        });

        async function savePart(part, url, decode) {
            if (signal.aborted) throw Error('cancelled');
            var result = await download(url, signal);
            if (server() && result.headers.get('X-Book-Content-Version') !== stamp) throw Error('version');
            var payload = await decode(result);
            var bytes = payload instanceof Blob ? payload.size : new Blob([payload]).size;
            if (signal.aborted) throw Error('cancelled');
            await transaction('readwrite', async function(books, content) {
                var current = await requestResult(books.get(key));
                if (signal.aborted) throw Error('cancelled');
                if (!current || current.token !== entry.token) throw Error('cancelled');
                entry.size += bytes;
                content.put(payload, key.concat([part]));
                books.put(entry, key);
            });
        }

        var count = book.format === 'pdf' ? 2 : book.count + 1;
        var completed = 0;
        try {
            onProgress(completed, count, entry.size);
            var toc = 'toc.json';
            await savePart(toc, bookURL(book, toc), async function(result) {
                var data = await result.json();
                if (!Array.isArray(data)) throw Error('download');
                return JSON.stringify(data);
            });
            onProgress(++completed, count, entry.size);
            if (book.format === 'pdf') {
                await savePart('pdf', documentURL(book), function(result) {
                    return pdfBlob(result, function(size, fraction) {
                        onProgress(completed, count, entry.size + size, fraction);
                    });
                });
                onProgress(++completed, count, entry.size);
            } else {
                // Keep memory and server load bounded even for very long books.
                for (var i = 0; i < book.count; i++) {
                    var file = 'chapter_' + i + '.html';
                    var downloadedIndex = i;
                    await savePart(file, bookURL(book, file), async function(result) {
                        return snapshot(await result.text(), book, downloadedIndex, stamp);
                    });
                    onProgress(++completed, count, entry.size);
                }
            }
            if (await version(book, owner, signal) !== stamp) throw Error('version');
            await transaction('readwrite', async function(books) {
                var current = await requestResult(books.get(key));
                if (signal.aborted) throw Error('cancelled');
                if (!current || current.token !== entry.token) throw Error('cancelled');
                entry.complete = true;
                entry.updated = Date.now();
                books.put(entry, key);
            });
            return entry;
        } catch (error) {
            await removeForOwner(book.id, owner, entry.token).catch(function() {});
            throw error;
        }
    }

    function request(book, url, done, failed, options) {
        var xhr;
        var aborted = false;
        var part = new URL(url, root.location.href).pathname.split('/').pop();
        get(book, part, options && options.prefetch).then(function(cached) {
            if (aborted) return;
            // Prefetch must not hand protected local content to a later read
            // without rechecking access at the point of navigation.
            if (cached !== null && options && options.prefetch) return done(null);
            if (cached !== null && done(cached) !== false) return;
            xhr = new XMLHttpRequest();
            xhr.open('GET', url, true);
            xhr.timeout = 15000;
            xhr.onload = function() {
                if (xhr.status < 200 || xhr.status >= 300 || done(xhr.responseText) === false) failed();
            };
            xhr.onerror = xhr.ontimeout = failed;
            xhr.send();
        });
        return { abort: function() { aborted = true; if (xhr) xhr.abort(); } };
    }

    root.EpubBrowserBookCache = { supported: supported, get: get, save: save, list: list,
        remove: remove, clear: clear, inspect: inspect, activeAccount: activeAccount, request: request, documentURL: documentURL };
})(window);
