function showNotification(message, type) {
    var existingNotification = document.querySelector('.custom-css-notification');
    if (existingNotification) {
        existingNotification.remove();
    }
    var notification = document.createElement('div');
    notification.className = "custom-css-notification " + type;
    notification.textContent = message;

    document.body.appendChild(notification);

    setTimeout(function() {
        notification.classList.add('fade-out');
        setTimeout(function() {
            if (notification.parentNode) {
                notification.parentNode.removeChild(notification);
            }
        }, 300);
    }, 3000);
}

// 设置 cookie
function setCookie(key, value) {
    var date = new Date();
    date.setTime(date.getTime() + 3650 * 24 * 60 * 60 * 1000);
    var expires = "expires=" + date.toUTCString();
    document.cookie = key + "=" + value + ";" + expires + "; path=/; SameSite=Lax";
}

// 解析指定 key 的 Cookie —— Kindle 兼容版
function getCookie(key) {
    var cookies = document.cookie.split('; ');
    // 替换 for...of 为传统 for 循环
    for (var i = 0; i < cookies.length; i++) {
        var cookie = cookies[i];
        // 替换解构赋值
        var parts = cookie.split('=');
        var cookieKey = parts[0];
        var cookieValue = parts.slice(1).join('=');
        
        if (cookieKey === key) {
            return decodeURIComponent(cookieValue);
        }
    }
    return null;
}

function deleteCookie(name) {
    document.cookie = name + "=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;";
}

// 检测是否是 Kindle 设备
function isKindleMode() {
    if (window.epubBrowserCache && window.epubBrowserCache.kindle_mode !== undefined) {
        return window.epubBrowserCache.kindle_mode === 'true';
    }
    var ua = navigator.userAgent.toLowerCase();
    var isKindle = ua.indexOf('kindle') !== -1 || ua.indexOf('silk') !== -1;
    if (!window.epubBrowserCache) {
        window.epubBrowserCache = {};
    }
    window.epubBrowserCache.kindle_mode = isKindle ? 'true' : 'false';
    return isKindle;
}

function initScript() {
    var i18n = window.EpubBrowserI18n;

    function t(key, params) {
        return i18n ? i18n.t(key, params) : key;
    }

    function loadBookMetadata(callback, failureCallback) {
        var basePath = window.EpubBrowserBasePath || "/";
        var metadataUrl = basePath + "book-metadata.json?" + Date.now();
        
        var xhr = new XMLHttpRequest();
        xhr.open('GET', metadataUrl, true);
        xhr.onreadystatechange = function() {
            if (xhr.readyState === 4) {
                if (xhr.status === 200) {
                    try {
                        var books = JSON.parse(xhr.responseText);
                        if (!Array.isArray(books)) {
                            throw new Error('Book metadata must be an array');
                        }
                        callback(books);
                    } catch (e) {
                        console.error('Failed to parse book metadata:', e);
                        if (failureCallback) failureCallback(e);
                    }
                } else {
                    console.error('Failed to load book metadata:', xhr.status);
                    if (failureCallback) failureCallback(new Error('Failed to load book metadata: ' + xhr.status));
                }
            }
        };
        xhr.send();
    }

    var metadataActiveRevision = null;
    var metadataQueuedRevision = null;
    var metadataCompletedRevision = -1;
    var metadataWaiters = [];
    var lastMetadataBooks = [];

    function settleMetadataWaiters(revision, error, books) {
        var remaining = [];
        metadataWaiters.forEach(function(waiter) {
            if (waiter.revision <= revision) {
                if (error) waiter.reject(error);
                else waiter.resolve(books);
            } else {
                remaining.push(waiter);
            }
        });
        metadataWaiters = remaining;
    }

    function startMetadataRefresh(revision) {
        metadataActiveRevision = revision;
        if (metadataQueuedRevision === revision) metadataQueuedRevision = null;
        loadBookMetadata(function(books) {
            replaceBookCards(books);
            lastMetadataBooks = books;
            metadataCompletedRevision = Math.max(metadataCompletedRevision, revision);
            metadataActiveRevision = null;
            settleMetadataWaiters(revision, null, books);
            if (metadataQueuedRevision !== null && metadataQueuedRevision > metadataCompletedRevision) {
                var nextRevision = metadataQueuedRevision;
                metadataQueuedRevision = null;
                startMetadataRefresh(nextRevision);
            }
        }, function(error) {
            metadataCompletedRevision = Math.max(metadataCompletedRevision, revision);
            metadataActiveRevision = null;
            settleMetadataWaiters(revision, error);
            if (metadataQueuedRevision !== null && metadataQueuedRevision > metadataCompletedRevision) {
                var nextRevision = metadataQueuedRevision;
                metadataQueuedRevision = null;
                startMetadataRefresh(nextRevision);
            }
        });
    }

    function requestMetadataRefresh(revision) {
        var targetRevision = typeof revision === 'number' && isFinite(revision)
            ? revision
            : Math.max(
                metadataCompletedRevision,
                metadataActiveRevision === null ? -1 : metadataActiveRevision,
                metadataQueuedRevision === null ? -1 : metadataQueuedRevision
            ) + 1;

        if (targetRevision <= metadataCompletedRevision) {
            return Promise.resolve(lastMetadataBooks);
        }
        return new Promise(function(resolve, reject) {
            metadataWaiters.push({ revision: targetRevision, resolve: resolve, reject: reject });
            if (metadataActiveRevision === null) {
                startMetadataRefresh(targetRevision);
            } else if (targetRevision > metadataActiveRevision) {
                metadataQueuedRevision = Math.max(metadataQueuedRevision === null ? -1 : metadataQueuedRevision, targetRevision);
            }
        });
    }
    
    function hideBookGridLoading() {
        var loading = document.getElementById('bookGridLoading');
        if (loading) {
            loading.style.display = 'none';
        }
    }

    function showLibraryState(key) {
        var bookGrid = document.querySelector('.book-grid');
        var state;
        if (!bookGrid || bookGrid.querySelector('.library-state')) return;
        state = document.createElement('div');
        state.className = 'empty-state library-state';
        state.setAttribute('data-i18n', key);
        state.textContent = t(key);
        bookGrid.appendChild(state);
    }
    
    function removeLibraryCardsAndStates(bookGrid) {
        var children = Array.prototype.slice.call(bookGrid.children);
        children.forEach(function(child) {
            if (child.classList.contains('book-card') || child.classList.contains('library-state')) {
                bookGrid.removeChild(child);
            }
        });
    }

    function createBookCard(book) {
        var card = document.createElement('div');
        var link = document.createElement('a');
        var cover = document.createElement('img');
        var content = document.createElement('div');
        var title = document.createElement('h3');
        var author = document.createElement('div');
        card.className = 'book-card';
        card.setAttribute('data-id', book.hash);

        link.className = 'book-link';
        link.setAttribute('id', book.hash);
        link.setAttribute('href', book.url);

        cover.className = 'book-cover';
        cover.setAttribute('src', book.cover);
        cover.setAttribute('alt', t('library.cover'));

        content.className = 'book-card-content';
        title.className = 'book-title';
        title.textContent = book.title;
        author.className = 'book-author';
        author.textContent = book.authors && book.authors.length > 0 ? book.authors.join(' & ') : '';

        content.appendChild(title);
        content.appendChild(author);

        if (book.tags && book.tags.length > 0) {
            var tags = document.createElement('div');
            tags.className = 'book-tags';
            book.tags.forEach(function(tag) {
                var tagElement = document.createElement('span');
                tagElement.className = 'book-tag';
                tagElement.textContent = tag;
                tags.appendChild(tagElement);
            });
            content.appendChild(tags);
        }

        link.appendChild(cover);
        link.appendChild(content);
        card.appendChild(link);
        return card;
    }

    function updateLibraryCounts(books, tagCount) {
        var bookCountElement = document.getElementById('libraryBookCount');
        var tagCountElement = document.getElementById('libraryTagCount');
        if (bookCountElement) {
            bookCountElement.textContent = t('library.bookCount', { count: books.length });
            bookCountElement.setAttribute('data-i18n-params', JSON.stringify({ count: books.length }));
        }
        if (tagCountElement) {
            tagCountElement.textContent = t('library.tagCount', { count: tagCount });
            tagCountElement.setAttribute('data-i18n-params', JSON.stringify({ count: tagCount }));
        }
    }

    function collectTagNames(books) {
        var tags = {};
        books.forEach(function(book) {
            (book.tags || []).forEach(function(tag) {
                if (typeof tag === 'string' && tag.trim()) tags[tag.trim()] = true;
            });
        });
        return Object.keys(tags).sort();
    }

    function rebuildTagItems(tagNames, activeTagId) {
        var tagCloud = document.querySelector('.tag-cloud');
        var tagItems;
        if (!tagCloud) return 0;

        tagItems = Array.prototype.slice.call(tagCloud.querySelectorAll('.tag-cloud-item'));
        tagItems.forEach(function(tagItem) {
            var id = tagItem.getAttribute('data-id');
            if (id !== 'All' && id !== 'NoTag') tagCloud.removeChild(tagItem);
        });

        tagNames.forEach(function(tag) {
            var tagItem = document.createElement('div');
            tagItem.className = 'tag-cloud-item';
            tagItem.setAttribute('data-id', tag);
            tagItem.textContent = tag;
            tagCloud.appendChild(tagItem);
        });

        tagItems = tagCloud.querySelectorAll('.tag-cloud-item');
        var selected = false;
        tagItems.forEach(function(tagItem) {
            var isActive = tagItem.getAttribute('data-id') === activeTagId;
            tagItem.classList.remove('active');
            if (isActive) {
                tagItem.classList.add('active');
                selected = true;
            }
        });
        if (!selected) {
            tagItems.forEach(function(tagItem) {
                if (tagItem.getAttribute('data-id') === 'All') tagItem.classList.add('active');
            });
        }
        return tagNames.length;
    }

    function replaceBookCards(books) {
        var bookGrid = document.querySelector('.book-grid');
        var activeTag = document.querySelector('.tag-cloud-item.active');
        var activeTagId = activeTag ? activeTag.getAttribute('data-id') : 'All';
        var cards = books.map(createBookCard);
        var tagNames = collectTagNames(books);
        if (!bookGrid) return;

        hideBookGridLoading();
        removeLibraryCardsAndStates(bookGrid);
        var tagCount = rebuildTagItems(tagNames, activeTagId);
        updateLibraryCounts(books, tagCount);

        if (!books.length) {
            showLibraryState('library.empty');
            restoreOrder(storageKeySortableBook, 'book-grid');
            restoreOrder(storageKeySortableTag, 'tag-cloud');
            applyLibraryFilters();
            return;
        }

        cards.forEach(function(card) {
            bookGrid.appendChild(card);
        });

        restoreOrder(storageKeySortableBook, 'book-grid');
        restoreOrder(storageKeySortableTag, 'tag-cloud');
        applyLibraryFilters();
    }

    // 页面加载时恢复顺序
    function restoreOrder(storageKey, elementClass) {
        var savedOrder = localStorage.getItem(storageKey);
        var itemIds;
        var container;
        var children;
        if (!savedOrder) return;
        try {
            itemIds = JSON.parse(savedOrder);
        } catch (e) {
            return;
        }
        if (!Array.isArray(itemIds)) return;
        container = document.querySelector('.' + elementClass);
        if (!container) return;
        children = Array.prototype.slice.call(container.children);
        itemIds.forEach(function(id) {
            var matchingElement;
            if (typeof id !== 'string') return;
            children.forEach(function(child) {
                if (!matchingElement && child.getAttribute('data-id') === id) matchingElement = child;
            });
            if (matchingElement) container.appendChild(matchingElement);
        });
    }

    function updateFontFamily(fontFamily, fontFamilyInput) {
        if (fontFamily === "ebook-default") {
            document.body.style.fontFamily = '';
        } else if (fontFamily == "custom") {
            document.body.style.fontFamily = fontFamilyInput;
        } else {
            document.body.style.fontFamily = fontFamily;
        }
    }

    var USERNAME_KEY = 'epub_browser_username';

    function getUsername() {
        if (isKindleMode()) {
            return getCookie(USERNAME_KEY);
        }
        return localStorage.getItem(USERNAME_KEY);
    }

    function setUsername(username) {
        if (isKindleMode()) {
            setCookie(USERNAME_KEY, username);
        } else {
            localStorage.setItem(USERNAME_KEY, username);
        }
    }

    function updateLoginDisplay() {
        var loginValue = document.getElementById('loginValue');
        var username = getUsername();
        if (loginValue) {
            if (username) {
                loginValue.textContent = username;
            } else {
                loginValue.textContent = t('library.login');
            }
        }
    }

    // 暴露给全局，供 annotation.js 同步更新 Login 显示
    window.updateLoginDisplay = updateLoginDisplay;

    updateLoginDisplay();

    var loginCard = document.getElementById('loginCard');
    if (loginCard) {
        loginCard.addEventListener('click', async function() {
            var currentUsername = getUsername();
            var username = await window.EpubDialog.prompt({
                title: t('library.login'),
                inputLabel: t('library.usernamePrompt'),
                defaultValue: currentUsername || '',
                selectOnOpen: true,
                confirmText: t('library.login')
            });
            if (username !== null) {
                if (username.trim()) {
                    setUsername(username.trim());
                    updateLoginDisplay();
                    showNotification(t('library.usernameSaved', { username: username.trim() }), 'success');
                } else if (username === '') {
                    setUsername('');
                    updateLoginDisplay();
                    showNotification(t('library.usernameCleared'), 'info');
                }
            }
        });
    }

    if (i18n && document.documentElement.getAttribute('data-library-locale-listener') !== 'true') {
        document.documentElement.setAttribute('data-library-locale-listener', 'true');
        i18n.onLocaleChange(function() {
            var covers = document.querySelectorAll('.book-cover');
            var i;
            updateLoginDisplay();
            for (i = 0; i < covers.length; i++) {
                covers[i].setAttribute('alt', t('library.cover'));
            }
        });
    }

    var storageKeySortableBook = 'book-grid-sortable-order';
    var storageKeySortableTag = 'tag-cloud-sortable-order';
    var storageKeySortableContainer = 'library-container-sortable-order';

    if (isKindleMode()) {
        document.documentElement.classList.remove("kindle-mode");
        document.documentElement.classList.add("kindle-mode");
    }

    function initSortable() {
        if (!isKindleMode()) {
            restoreOrder(storageKeySortableBook, 'book-grid');
            restoreOrder(storageKeySortableTag, 'tag-cloud');
            restoreOrder(storageKeySortableContainer, 'container');
        }
        
        var elBook = document.querySelector('.book-grid');
        var elTag = document.querySelector('.tag-cloud');
        var elContainer = document.querySelector('.container');
        if (!isKindleMode()) {
            var sortableBook = Sortable.create(elBook, {
                delay: 300,
                delayOnTouchOnly: true,
                onEnd: function(evt) {
                    var itemIds = Array.from(evt.from.children).map(function(child) {
                        return child.dataset.id;
                    });
                    localStorage.setItem(storageKeySortableBook, JSON.stringify(itemIds));
                }
            });
            var sortableTag = Sortable.create(elTag, {
                delay: 300,
                delayOnTouchOnly: true,
                onEnd: function(evt) {
                    var itemIds = Array.from(evt.from.children).map(function(child) {
                        return child.dataset.id;
                    });
                    localStorage.setItem(storageKeySortableTag, JSON.stringify(itemIds));
                }
            });
            var sortableContainer = Sortable.create(elContainer, {
                delay: 300,
                delayOnTouchOnly: true,
                filter: '.book-grid, .search-box',
                preventOnFilter: false,
                onEnd: function(evt) {
                    var itemIds = Array.from(evt.from.children).map(function(child) {
                        return child.dataset.id;
                    });
                    localStorage.setItem(storageKeySortableContainer, JSON.stringify(itemIds));
                }
            });
        }
    }
    
    window.onBookCardsLoaded = initSortable;

    if (window.initTheme) {
        window.initTheme();
    }

    var fontFamily = "ebook-default";
    var fontFamilyInput = null;
    if (!isKindleMode()) {
        if (window.epubBrowserCache && window.epubBrowserCache.font_family) {
            fontFamily = window.epubBrowserCache.font_family;
        } else {
            fontFamily = localStorage.getItem('font_family') || "ebook-default";
            if (fontFamily) {
                if (!window.epubBrowserCache) {
                    window.epubBrowserCache = {};
                }
                window.epubBrowserCache.font_family = fontFamily;
            }
        }
        if (window.epubBrowserCache && window.epubBrowserCache.font_family_input) {
            fontFamilyInput = window.epubBrowserCache.font_family_input;
        } else {
            fontFamilyInput = localStorage.getItem('font_family_input');
            if (fontFamilyInput) {
                if (!window.epubBrowserCache) {
                    window.epubBrowserCache = {};
                }
                window.epubBrowserCache.font_family_input = fontFamilyInput;
            }
        }
    } else {
        fontFamily = getCookie('font_family') || "ebook-default";
        fontFamilyInput = getCookie('font_family_input');
    }
    updateFontFamily(fontFamily, fontFamilyInput);

    var searchBox = document.querySelector('.search-box');
    var tagCloud = document.querySelector('.tag-cloud');

    function cardMatchesSearch(card, searchTerm) {
        var title = card.querySelector('.book-title').textContent.toLowerCase();
        var author = card.querySelector('.book-author').textContent.toLowerCase();
        var pinyinMatch = false;
        if (searchTerm === '') return true;
        if (typeof pinyinPro !== 'undefined') {
            try {
                var titlePinyin = pinyinPro.pinyin(title, { toneType: 'none' }).toLowerCase().replace(/ /g, '');
                var authorPinyin = pinyinPro.pinyin(author, { toneType: 'none' }).toLowerCase().replace(/ /g, '');
                var searchPinyin = pinyinPro.pinyin(searchTerm, { toneType: 'none' }).toLowerCase().replace(/ /g, '');
                pinyinMatch = titlePinyin.indexOf(searchPinyin) !== -1 || authorPinyin.indexOf(searchPinyin) !== -1;
            } catch (e) {
                console.log('Pinyin match error:', e);
            }
        }
        return title.includes(searchTerm) || author.includes(searchTerm) || pinyinMatch;
    }

    function cardMatchesTag(card, tagId) {
        var tags = card.querySelectorAll('.book-tag');
        if (tagId === 'All') return true;
        if (tagId === 'NoTag') return tags.length === 0;
        return Array.prototype.some.call(tags, function(tag) {
            return tag.textContent === tagId;
        });
    }

    function applyLibraryFilters() {
        var searchTerm = (searchBox.value || '').toLowerCase().trim();
        var activeTag = document.querySelector('.tag-cloud-item.active');
        var tagId = activeTag ? activeTag.getAttribute('data-id') : 'All';
        document.querySelectorAll('.book-card').forEach(function(card) {
            var textMatches = cardMatchesSearch(card, searchTerm);
            var tagMatches = cardMatchesTag(card, tagId);
            card.style.display = textMatches && tagMatches ? 'block' : 'none';
        });
    }

    function activateTag(tagId) {
        tagCloud.querySelectorAll('.tag-cloud-item').forEach(function(tagItem) {
            tagItem.classList.remove('active');
            if (tagItem.getAttribute('data-id') === tagId) tagItem.classList.add('active');
        });
        applyLibraryFilters();
    }

    if (searchBox && searchBox.getAttribute('data-library-filter-listener') !== 'true') {
        searchBox.setAttribute('data-library-filter-listener', 'true');
        searchBox.addEventListener('input', applyLibraryFilters);
    }
    if (tagCloud && tagCloud.getAttribute('data-library-filter-listener') !== 'true') {
        tagCloud.setAttribute('data-library-filter-listener', 'true');
        tagCloud.addEventListener('click', function(event) {
            var tag = event.target;
            if (tag && tag.classList.contains('tag-cloud-item')) activateTag(tag.getAttribute('data-id'));
        });
    }
    var libraryGrid = document.querySelector('.book-grid');
    if (libraryGrid && libraryGrid.getAttribute('data-library-filter-listener') !== 'true') {
        libraryGrid.setAttribute('data-library-filter-listener', 'true');
        libraryGrid.addEventListener('click', function(event) {
            var tag = event.target;
            if (tag && tag.classList.contains('book-tag')) {
                event.preventDefault();
                event.stopPropagation();
                activateTag(tag.textContent);
            }
        });
    }
    window.initBookCardsEvents = applyLibraryFilters;

    window.refreshLibraryMetadata = function(catalogRevision) {
        return requestMetadataRefresh(catalogRevision);
    };

    requestMetadataRefresh(0).then(function() {
        if (window.onBookCardsLoaded) window.onBookCardsLoaded();
    }, function() {
        hideBookGridLoading();
        showLibraryState('library.loadError');
    });

    var scrollToTopBtn = document.getElementById('scrollToTopBtn');

    scrollToTopBtn.addEventListener('click', function() {
        // 移除 smooth，Kindle 兼容
        window.scrollTo(0, 0);
    });

    function pwaSupport() {
        if (window.EpubBrowserMode === 'server') return;
        if ('serviceWorker' in navigator) {
            window.addEventListener('load', function() {
                window.EpubBrowserCacheBoundary.registerWorker()
                    .then(function(registration) {
                        console.log('ServiceWorker registration successful');
                    })
                    .catch(function(error) {
                        console.log('ServiceWorker registration failed');
                    });
            });
        }
        var deferredPrompt;
        var readingControls = document.querySelector('.reading-controls');
        
        var installBtn = document.createElement('button');
        installBtn.id = 'pwa-install-btn';
        installBtn.className = 'control-btn';
        installBtn.innerHTML = '<i class="fas fa-download"></i><div class="control-name" data-i18n="library.install">' + t('library.install') + '</div>';
        installBtn.style.display = 'none';
        if (readingControls) {
            readingControls.appendChild(installBtn);
        }

        window.addEventListener('beforeinstallprompt', function(e) {
            e.preventDefault();
            deferredPrompt = e;
            if (installBtn) installBtn.style.display = 'block';
        });

        if (installBtn) {
            installBtn.addEventListener('click', function(e) {
                e.preventDefault();
                if (deferredPrompt) {
                    showNotification(t('library.installing'), 'info');
                    installBtn.style.display = 'none';
                    deferredPrompt.prompt();
                    deferredPrompt.userChoice.then(function(choiceResult) {
                        if (choiceResult.outcome === 'accepted') {
                            showNotification(t('library.installSucceeded'), 'success');
                        } else {
                            showNotification(t('library.installCancelled'), 'info');
                        }
                        deferredPrompt = null;
                    });
                }
            });
        }

        window.addEventListener('appinstalled', function() {
            if (installBtn) installBtn.style.display = 'none';
        });
    }

    function bookshelfSupport() {
        var bookshelfBtn = document.getElementById('bookshelfBtn');
        if (bookshelfBtn) bookshelfBtn.style.display = 'inherit';
        if (window.initBookshelf) {
            window.initBookshelf();
        } else {
            setTimeout(bookshelfSupport, 100);
        }
    }

    if (!isKindleMode()) {
        pwaSupport();
        bookshelfSupport();
    }

    function hideLoading() {
        var overlay = document.getElementById('loadingOverlay');
        if (overlay) overlay.style.display = 'none';
    }

    setTimeout(hideLoading, 100);
}

window.initScriptLibrary = initScript;
