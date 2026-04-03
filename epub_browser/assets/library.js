function initScript() {
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

    // 页面加载时恢复顺序
    function restoreOrder(storageKey, elementClass) {
        var savedOrder = localStorage.getItem(storageKey);
        if (savedOrder) {
            var itemIds = JSON.parse(savedOrder);
            var container = document.querySelector('.' + elementClass);
            
            itemIds.forEach(function(id) {
                var element = document.querySelector('[data-id="' + id + '"]');
                if (element) {
                    container.appendChild(element);
                }
            });
        }
    }

    function updateFontFamily(fontFamily, fontFamilyInput) {
        if (fontFamily == "custom") {
            document.body.style.fontFamily = fontFamilyInput;
        } else {
            document.body.style.fontFamily = fontFamily;
        }
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
                loginValue.textContent = 'Login';
            }
        }
    }

    window.getUsername = getUsername;
    window.setUsername = setUsername;
    updateLoginDisplay();

    var loginCard = document.getElementById('loginCard');
    if (loginCard) {
        loginCard.addEventListener('click', function() {
            var currentUsername = getUsername();
            var username = prompt('Please enter your username:', currentUsername || '');
            if (username !== null) {
                if (username.trim()) {
                    setUsername(username.trim());
                    updateLoginDisplay();
                    showNotification('Username saved: ' + username.trim(), 'success');
                } else if (username === '') {
                    setUsername('');
                    updateLoginDisplay();
                    showNotification('Username cleared', 'info');
                }
            }
        });
    }

    var storageKeySortableBook = 'book-grid-sortable-order';
    var storageKeySortableTag = 'tag-cloud-sortable-order';
    var storageKeySortableContainer = 'library-container-sortable-order';

    if (isKindleMode()) {
        document.documentElement.classList.remove("kindle-mode");
        document.documentElement.classList.add("kindle-mode");
    } else {
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

    if (window.initTheme) {
        window.initTheme();
    }

    var fontFamily = "system-ui, -apple-system, sans-serif";
    var fontFamilyInput = null;
    if (!isKindleMode()) {
        if (window.epubBrowserCache && window.epubBrowserCache.font_family) {
            fontFamily = window.epubBrowserCache.font_family;
        } else {
            fontFamily = localStorage.getItem('font_family') || "system-ui, -apple-system, sans-serif";
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
        fontFamily = getCookie('font_family') || "system-ui, -apple-system, sans-serif";
        fontFamilyInput = getCookie('font_family_input');
    }
    updateFontFamily(fontFamily, fontFamilyInput);

    var searchBox = document.querySelector('.search-box');
    var bookCards = document.querySelectorAll('.book-card');
    var tagCloudItems = document.querySelectorAll('.tag-cloud-item');

    searchBox.addEventListener('input', function() {
        var searchTerm = this.value.toLowerCase().trim();
        
        bookCards.forEach(function(card) {
            var title = card.querySelector('.book-title').textContent.toLowerCase();
            var author = card.querySelector('.book-author').textContent.toLowerCase();
            
            var match = false;
            
            if (searchTerm === '') {
                match = true;
            } else {
                var titleMatch = title.includes(searchTerm);
                var authorMatch = author.includes(searchTerm);
                
                var pinyinMatch = false;
                if (typeof pinyinPro !== 'undefined') {
                    try {
                        var titlePinyin = pinyinPro.pinyin(title, { toneType: 'none', type: 'all' }).toLowerCase();
                        var authorPinyin = pinyinPro.pinyin(author, { toneType: 'none', type: 'all' }).toLowerCase();
                        var searchPinyin = pinyinPro.pinyin(searchTerm, { toneType: 'none', type: 'all' }).toLowerCase();
                        
                        if (titlePinyin.includes(searchPinyin) || authorPinyin.includes(searchPinyin)) {
                            pinyinMatch = true;
                        }
                    } catch (e) {
                        console.log('Pinyin match error:', e);
                    }
                }
                
                match = titleMatch || authorMatch || pinyinMatch;
            }
            
            card.style.display = match ? 'block' : 'none';
        });
    });

    tagCloudItems.forEach(function(tag) {
        tag.addEventListener('click', function() {
            tagCloudItems.forEach(function(t) { t.classList.remove('active'); });
            this.classList.add('active');
            
            var tagText = this.textContent.trim();
            
            if (tagText === 'All') {
                bookCards.forEach(function(card) { card.style.display = 'block'; });
            } else if (tagText === 'NoTag') {
                bookCards.forEach(function(card) {
                    var tags = card.querySelectorAll('.book-tag');
                    var hasTag = tags.length > 0;
                    card.style.display = hasTag ? 'none' : 'block';
                });
            } else {
                bookCards.forEach(function(card) {
                    var tags = card.querySelectorAll('.book-tag');
                    var hasTag = false;
                    
                    tags.forEach(function(t) {
                        if (t.textContent === tagText) hasTag = true;
                    });
                    
                    card.style.display = hasTag ? 'block' : 'none';
                });
            }
        });
    });

    var bookTags = document.querySelectorAll('.book-tag');
    bookTags.forEach(function(tag) {
        tag.addEventListener('click', function(e) {
            e.preventDefault();
            e.stopPropagation();
            
            var tagText = this.textContent;
            
            tagCloudItems.forEach(function(t) { t.classList.remove('active'); });
            tagCloudItems.forEach(function(t) {
                if (t.textContent === tagText) t.classList.add('active');
            });
            
            bookCards.forEach(function(card) {
                var tags = card.querySelectorAll('.book-tag');
                var hasTag = false;
                
                tags.forEach(function(t) {
                    if (t.textContent === tagText) hasTag = true;
                });
                
                card.style.display = hasTag ? 'block' : 'none';
            });
        });
    });

    var scrollToTopBtn = document.getElementById('scrollToTopBtn');

    scrollToTopBtn.addEventListener('click', function() {
        // 移除 smooth，Kindle 兼容
        window.scrollTo(0, 0);
    });

    function showNotification(message, type) {
        var existingNotification = document.querySelector('.custom-css-notification');
        if (existingNotification) {
            existingNotification.remove();
        }
        var notification = document.createElement('div');
        notification.className = 'custom-css-notification ' + type;
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
    
    window.showNotification = showNotification;

    function pwaSupport() {
        if ('serviceWorker' in navigator) {
            window.addEventListener('load', function() {
                navigator.serviceWorker.register('/sw.js')
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
        installBtn.innerHTML = '<i class="fas fa-download"></i><div class="control-name">Install</div>';
        installBtn.style.display = 'none';
        if (readingControls) {
            readingControls.appendChild(installBtn);
        }

        var updateCacheBtn = document.createElement('button');
        updateCacheBtn.id = 'update-cache-btn';
        updateCacheBtn.className = 'control-btn';
        updateCacheBtn.innerHTML = '<i class="fas fa-sync"></i><div class="control-name">Update</div>';
        if (readingControls) {
            readingControls.appendChild(updateCacheBtn);
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
                    showNotification('Installing app...', 'info');
                    installBtn.style.display = 'none';
                    deferredPrompt.prompt();
                    deferredPrompt.userChoice.then(function(choiceResult) {
                        if (choiceResult.outcome === 'accepted') {
                            showNotification('App installed successfully!', 'success');
                        } else {
                            showNotification('Install cancelled', 'info');
                        }
                        deferredPrompt = null;
                    });
                }
            });
        }

        if (updateCacheBtn) {
            updateCacheBtn.addEventListener('click', function(e) {
                e.preventDefault();
                showNotification('Updating cache...', 'info');
                
                if ('serviceWorker' in navigator && navigator.serviceWorker.controller) {
                    navigator.serviceWorker.controller.postMessage({ action: 'CLEAR_CACHE' });
                    showNotification('Cache cleared, page will reload...', 'info');
                    setTimeout(function() {
                        location.reload();
                    }, 1000);
                } else {
                    showNotification('Page will reload...', 'info');
                    setTimeout(function() {
                        location.reload();
                    }, 500);
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

    setTimeout(hideLoading, 500);
}

window.initScriptLibrary = initScript;