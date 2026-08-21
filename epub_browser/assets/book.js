// 设置 cookie
function setCookie(key, value) {
    var date = new Date();
    date.setTime(date.getTime() + 3650 * 24 * 60 * 60 * 1000);
    var expires = "expires=" + date.toUTCString();
    document.cookie = key + "=" + value + "; " + expires + "; path=/;";
}

// 解析指定 key 的 Cookie
function getCookie(key) {
    var cookies = document.cookie.split('; ');
    // 替换 for...of 为普通 for 循环
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

function updateFontFamily(fontFamily, fontFamilyInput) {
    if (fontFamily === "ebook-default") {
        document.body.style.fontFamily = '';
    } else if (fontFamily == "custom") {
        document.body.style.fontFamily = fontFamilyInput;
    } else {
        document.body.style.fontFamily = fontFamily;
    }
}

function bookT(key, params) {
    var i18n = window.EpubBrowserI18n;
    return i18n && i18n.t ? i18n.t(key, params) : key;
}

// 显示通知
function showNotification(message, type) {
    return window.EpubBrowserNotification.show(message, type);
}

// 页面加载时恢复顺序
function restoreOrder(storageKey, elementClass) {
    var savedOrder = localStorage.getItem(storageKey);
    if (savedOrder) {
        var itemIds = JSON.parse(savedOrder);
        var container = document.querySelector("." + elementClass);

        itemIds.forEach(function(id) {
            var element = document.querySelector('[data-id="' + id + '"]');
            if (element) {
                container.appendChild(element);
            }
        });
    }
}

// 删除指定前缀的所有 localStorage 键
function deleteKeysByPrefix(prefix) {
    var keysToDelete = [];

    for (var i = 0; i < localStorage.length; i++) {
        var key = localStorage.key(i);
        if (key.indexOf(prefix) === 0) {
            keysToDelete.push(key);
        }
    }

    keysToDelete.forEach(function(key) {
        localStorage.removeItem(key);
        console.log("Deleted: " + key);
    });

    return keysToDelete.length;
}

function initScript() {
    var path = window.location.pathname;
    var pathParts = path.split('/');
    pathParts = pathParts.filter(function(item) { return item !== ""; });
    var book_hash = pathParts[pathParts.indexOf('book') + 1];
    var readingProgressLoadVersion = 0;

    function loadReadingProgress() {
        if (isKindleMode() || !window.EpubReadingProgress || !window.EpubReadingProgress.isServerMode()) return;
        var version = ++readingProgressLoadVersion;
        window.EpubReadingProgress.request('GET', '/api/reading-progress/' + encodeURIComponent(book_hash))
            .then(function(progress) {
                if (version !== readingProgressLoadVersion || !progress || typeof progress.chapter_index !== 'number') return;
                var readKey = 'eb_ci_' + progress.chapter_index;
                localStorage.setItem(book_hash, readKey);
                updateContinueReadingButton(book_hash);
                markReadingChapter(readKey, getProgressIdentity());
            });
    }

    updateContinueReadingButton(book_hash);
    loadReadingProgress();

    if (!isKindleMode()) {
        var clearBtn = document.querySelector("#clearReadingProgressBtn");
        var clearMenu = document.getElementById('clearReadingProgressMenu');
        var clearMenuToggle = document.getElementById('continueReadingMenuToggle');
        var clearControl = document.getElementById('continueReadingControl');
        function closeClearMenu() {
            if (!clearMenu || !clearMenuToggle) return;
            clearMenu.hidden = true;
            clearMenuToggle.setAttribute('aria-expanded', 'false');
        }
        if (clearMenuToggle && clearMenu && clearControl && !clearMenuToggle.dataset.bound) {
            clearMenuToggle.dataset.bound = 'true';
            clearMenuToggle.addEventListener('click', function() {
                var willOpen = clearMenu.hidden;
                clearMenu.hidden = !willOpen;
                clearMenuToggle.setAttribute('aria-expanded', willOpen ? 'true' : 'false');
            });
            document.addEventListener('click', function(event) {
                if (!clearControl.contains(event.target)) closeClearMenu();
            });
            document.addEventListener('keydown', function(event) {
                if (event.key === 'Escape' && !clearMenu.hidden) {
                    closeClearMenu();
                    clearMenuToggle.focus();
                }
            });
        }
        if (clearBtn && !clearBtn.dataset.bound) {
            clearBtn.dataset.bound = 'true';
            clearBtn.addEventListener("click", async function() {
                closeClearMenu();
                if (!await window.EpubDialog.confirm({
                    title: bookT('book.clearReadingProgress'),
                    message: bookT('book.clearReadingProgressConfirm'),
                    confirmText: bookT('book.clearReadingProgress'),
                    destructive: true
                })) return;
                function reportClearFailure(result) {
                    var code = result && result.error && result.error.code;
                    var key = code ? 'book.error.' + code : 'book.clearReadingProgressFailed';
                    var message = bookT(key);
                    showNotification(message === key ? bookT('book.clearReadingProgressFailed') : message, 'error');
                }

                function clearLocalProgress() {
                    var prefix1 = "scroll_" + book_hash + "_";
                    var prefix2 = "turning_" + book_hash + "_";
                    readingProgressLoadVersion++;
                    deleteKeysByPrefix(prefix1);
                    deleteKeysByPrefix(prefix2);
                    deleteKeysByPrefix(book_hash);
                    updateContinueReadingButton(book_hash);
                    showNotification(bookT('book.clearReadingProgressSucceeded'), "success");
                }

                if (!window.EpubReadingProgress) {
                    reportClearFailure(null);
                    return;
                }
                if (!window.EpubReadingProgress.isServerMode()) {
                    clearLocalProgress();
                    return;
                }
                window.EpubReadingProgress.request(
                    'DELETE',
                    '/api/reading-progress/' + encodeURIComponent(book_hash),
                    null,
                    true,
                    true
                ).then(function(result) {
                    if (!result || result.error) {
                        reportClearFailure(result);
                        return;
                    }
                    clearLocalProgress();
                }, function() {
                    reportClearFailure(null);
                });
            });
        }

        initBookShelfButton(book_hash);
    }

    var storageKeySortableContainer = 'book-container-sortable-order';

    if (isKindleMode()) {
        document.documentElement.classList.remove("kindle-mode");
        document.documentElement.classList.add("kindle-mode");
    } else {
        restoreOrder(storageKeySortableContainer, 'container');
    }

    function bookshelfSupport() {
        if (window.initBookshelf) {
            window.initBookshelf();
        } else {
            setTimeout(bookshelfSupport, 100);
        }
    }

    if (!isKindleMode()) {
        bookshelfSupport();
    }

    var el = document.querySelector('.container');
    if (!isKindleMode()) {
        var sortable = Sortable.create(el, {
            delay: 300,
            delayOnTouchOnly: true,
            filter: '.toc-container',
            preventOnFilter: false,
            onEnd: function(evt) {
                // 替换 Array.from
                var children = evt.from.children;
                var itemIds = [];
                for (var i = 0; i < children.length; i++) {
                    itemIds.push(children[i].dataset.id);
                }
                localStorage.setItem(storageKeySortableContainer, JSON.stringify(itemIds));
            }
        });
    }

    var currentChapter = "";
    if (!isKindleMode()) {
        currentChapter = localStorage.getItem(book_hash) || "";
    } else {
        currentChapter = getCookie(book_hash) || "";
    }
    // Browser-local progress restores the active chapter, but is not evidence
    // of a server sync (notably in static Pages builds).
    if (currentChapter !== "") markReadingChapter(currentChapter);

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

    if (window.EpubBrowserI18n && window.EpubBrowserI18n.onLocaleChange && !document.documentElement.dataset.bookI18nBound) {
        document.documentElement.dataset.bookI18nBound = 'true';
        window.EpubBrowserI18n.onLocaleChange(function() {
            var activeChapter = document.querySelector('.chapter-link.active');
            updateContinueReadingButton(book_hash);
            if (activeChapter) {
                markReadingChapter(activeChapter.id, activeChapter.getAttribute('data-sync-username') || '');
            }
            if (window.refreshBookShelfButton) window.refreshBookShelfButton();
        });
    }

    var scrollToTopBtn = document.getElementById('scrollToTopBtn');
    scrollToTopBtn.addEventListener('click', function() {
        window.scrollTo({
            top: 0,
            behavior: 'smooth'
        });
    });

    function updateScrollToTopVisibility() {
        var scrollTop = window.pageYOffset || document.documentElement.scrollTop || 0;
        var threshold = Math.max(320, (window.innerHeight || 0) * 0.75);
        if (scrollTop > threshold) scrollToTopBtn.classList.add('is-visible');
        else scrollToTopBtn.classList.remove('is-visible');
    }
    window.addEventListener('scroll', updateScrollToTopVisibility);
    updateScrollToTopVisibility();

    function hideLoading() {
        var overlay = document.getElementById('loadingOverlay');
        if (overlay) {
            overlay.style.display = 'none';
        }
    }

    setTimeout(function() {
        hideLoading();
    }, 500);
}

function getProgressIdentity() {
    if (window.EpubBrowserMode !== 'server') return '';
    if (!window.EpubReadingProgress || !window.EpubReadingProgress.getUsername) return '';
    return window.EpubReadingProgress.getUsername();
}

function markReadingChapter(readKey, username) {
    var chapterLinks = document.querySelectorAll('.chapter-link');
    var chapterElement = document.getElementById(readKey);
    var i;

    if (!chapterElement) {
        for (i = 0; i < chapterLinks.length; i++) {
            if (chapterLinks[i].id.split('#')[0] === readKey) {
                chapterElement = chapterLinks[i];
                break;
            }
        }
    }

    for (i = 0; i < chapterLinks.length; i++) {
        chapterLinks[i].classList.remove('active');
        var existingTag = chapterLinks[i].querySelector('.chapter-sync-tag');
        if (existingTag) existingTag.remove();
    }

    if (!chapterElement) return;
    chapterElement.classList.add('active');
    chapterElement.setAttribute('data-sync-username', username || '');
    if (username) {
        var displayUsername = username === 'shared' ? bookT('book.sharedUser') : username;
        var syncTag = document.createElement('span');
        syncTag.className = 'chapter-sync-tag';
        syncTag.textContent = bookT('book.cloudSyncUser', { username: displayUsername });
        syncTag.setAttribute('aria-label', bookT('book.cloudSyncUserAria', { username: displayUsername }));
        var title = chapterElement.querySelector('.chapter-title');
        if (title) {
            var titleWithSync = document.createElement('span');
            titleWithSync.className = 'chapter-title-with-sync';
            title.parentNode.insertBefore(titleWithSync, title);
            titleWithSync.appendChild(title);
            titleWithSync.appendChild(syncTag);
        } else {
            chapterElement.appendChild(syncTag);
        }
    }

    var tocContainer = document.querySelector('.chapter-list');
    if (isKindleMode()) tocContainer = document.documentElement;
    if (tocContainer) tocContainer.scrollTop = chapterElement.offsetTop - tocContainer.offsetTop - 50;
}

function updateContinueReadingButton(bookHash) {
    var continueButton = document.getElementById('continueReadingBtn');
    var continueButtonText = document.getElementById('continueReadingBtnText');
    var firstChapter = document.querySelector('.chapter-link');
    if (!continueButton || !continueButtonText || !firstChapter) {
        if (continueButton) continueButton.hidden = true;
        setClearReadingProgressAvailability(false);
        return;
    }

    var readKey = isKindleMode() ? getCookie(bookHash) : localStorage.getItem(bookHash);
    var resumeChapter = readKey ? document.getElementById(readKey) : null;
    if (!resumeChapter && readKey) {
        var chapterLinks = document.querySelectorAll('.chapter-link');
        for (var i = 0; i < chapterLinks.length; i++) {
            if (chapterLinks[i].id.split('#')[0] === readKey) {
                resumeChapter = chapterLinks[i];
                break;
            }
        }
    }
    if (resumeChapter && resumeChapter.href) {
        continueButton.href = resumeChapter.href;
        continueButtonText.textContent = bookT('book.continueReading');
        continueButton.setAttribute('aria-label', bookT('book.continueReading'));
    } else {
        continueButton.href = firstChapter.href;
        continueButtonText.textContent = bookT('book.startReading');
        continueButton.setAttribute('aria-label', bookT('book.startReading'));
    }
    setClearReadingProgressAvailability(!!resumeChapter && !isKindleMode());
}

function setClearReadingProgressAvailability(available) {
    var clearButton = document.getElementById('clearReadingProgressBtn');
    var menu = document.getElementById('clearReadingProgressMenu');
    var toggle = document.getElementById('continueReadingMenuToggle');
    var control = document.getElementById('continueReadingControl');
    if (clearButton) clearButton.hidden = !available;
    if (toggle) {
        toggle.hidden = !available;
        toggle.setAttribute('aria-expanded', 'false');
    }
    if (menu) menu.hidden = true;
    if (control) control.classList.toggle('has-reading-progress', available);
}

function initBookShelfButton(bookHash) {
    var BOOKSHELF_KEY = 'bookshelf';
    var BOOKSHELF_VERSION_KEY = 'bookshelf_version';
    var isServerMode = window.EpubBookshelfStore && window.EpubBookshelfStore.isServerMode();

    var toggleShelfBtn = document.getElementById('toggleShelfBtn');
    var toggleShelfBtnText = document.getElementById('toggleShelfBtnText');

    if (!toggleShelfBtn) return;

    function getBookshelfVersion() {
        var version = localStorage.getItem(BOOKSHELF_VERSION_KEY);
        return version ? parseInt(version, 10) : 1;
    }

    function setBookshelfVersion(version) {
        localStorage.setItem(BOOKSHELF_VERSION_KEY, version.toString());
    }

    function incrementBookshelfVersion() {
        var currentVersion = getBookshelfVersion();
        setBookshelfVersion(currentVersion + 1);
    }

    function getBookshelf() {
        if (isServerMode) {
            return window.EpubBookshelfStore.data() || { items: [], groups: {}, order: [] };
        }
        var data = localStorage.getItem(BOOKSHELF_KEY);
        if (data) {
            return JSON.parse(data);
        }
        return { items: [], groups: {} };
    }

    function saveBookshelf(data) {
        if (isServerMode) {
            return window.EpubBookshelfStore.save(data);
        }
        localStorage.setItem(BOOKSHELF_KEY, JSON.stringify(data));
        incrementBookshelfVersion();
        return Promise.resolve({ data: data });
    }

    function ensureServerBookshelf() {
        if (!isServerMode) return Promise.resolve(true);
        return window.EpubBookshelfStore.load().then(function(result) {
            if (result.error) {
                showNotification(window.EpubBrowserI18n.t('bookshelf.error.' + (result.error.code || 'unknown')), 'warning');
                return false;
            }
            return true;
        });
    }

    function persistBookshelf(data) {
        return saveBookshelf(data).then(function(result) {
            if (result.error) {
                showNotification(window.EpubBrowserI18n.t('bookshelf.error.' + (result.error.code || 'unknown')), 'warning');
                return false;
            }
            return true;
        });
    }

    function isBookInShelf(bookHash, shelfData) {
        if (!shelfData) shelfData = getBookshelf();
        if (shelfData.items.indexOf(bookHash) > -1) return true;
        for (var groupId in shelfData.groups) {
            if (isBookInGroup(bookHash, shelfData.groups[groupId])) return true;
        }
        return false;
    }

    function isBookInGroup(bookHash, group) {
        if (group.items && group.items.indexOf(bookHash) > -1) return true;
        if (group.groups) {
            for (var subGroupId in group.groups) {
                if (isBookInGroup(bookHash, group.groups[subGroupId])) return true;
            }
        }
        return false;
    }

    function updateButtonState() {
        var shelfData = getBookshelf();
        var inShelf = isBookInShelf(bookHash, shelfData);

        if (inShelf) {
            toggleShelfBtnText.textContent = bookT('book.removeFromShelf');
            toggleShelfBtn.setAttribute('aria-label', bookT('book.removeFromShelf'));
            toggleShelfBtn.classList.add('in-shelf');
        } else {
            toggleShelfBtnText.textContent = bookT('book.addToShelf');
            toggleShelfBtn.setAttribute('aria-label', bookT('book.addToShelf'));
            toggleShelfBtn.classList.remove('in-shelf');
        }
    }

    function removeBookFromShelf(bookHash, shelfData) {
        var index = shelfData.items.indexOf(bookHash);
        if (index > -1) {
            shelfData.items.splice(index, 1);
            if (shelfData.order) {
                var orderIndex = shelfData.order.indexOf(bookHash);
                if (orderIndex > -1) {
                    shelfData.order.splice(orderIndex, 1);
                }
            }
            return true;
        }

        for (var groupId in shelfData.groups) {
            if (removeBookFromGroup(bookHash, shelfData.groups[groupId])) {
                return true;
            }
        }
        return false;
    }

    function removeBookFromGroup(bookHash, group) {
        var index = group.items.indexOf(bookHash);
        if (index > -1) {
            group.items.splice(index, 1);
            if (group.order) {
                var orderIndex = group.order.indexOf(bookHash);
                if (orderIndex > -1) {
                    group.order.splice(orderIndex, 1);
                }
            }
            return true;
        }

        if (group.groups) {
            for (var subGroupId in group.groups) {
                if (removeBookFromGroup(bookHash, group.groups[subGroupId])) {
                    return true;
                }
            }
        }
        return false;
    }

    function renderGroupTree(container, groups, level, parentPath) {
        if (level === undefined) level = 0;
        if (parentPath === undefined) parentPath = '';

        for (var groupId in groups) {
            var group = groups[groupId];
            var fullPath = parentPath ? parentPath + " → " + group.name : group.name;
            var itemEl = document.createElement('div');
            var iconEl = document.createElement('span');
            var icon = document.createElement('i');
            var nameEl = document.createElement('span');
            itemEl.className = 'select-group-item';
            itemEl.dataset.id = groupId;
            itemEl.dataset.level = level;
            iconEl.className = 'select-group-item-icon';
            icon.className = 'fas fa-folder';
            nameEl.className = 'select-group-item-name';
            nameEl.textContent = fullPath;
            iconEl.appendChild(icon);
            itemEl.appendChild(iconEl);
            itemEl.appendChild(nameEl);
            itemEl.addEventListener('click', function() {
                container.querySelectorAll('.select-group-item').forEach(function(i) {
                    i.classList.remove('selected');
                });
                this.classList.add('selected');
            });
            container.appendChild(itemEl);

            if (group.groups && Object.keys(group.groups).length > 0) {
                renderGroupTree(container, group.groups, level + 1, fullPath);
            }
        }
    }

    function addRootGroup(tree) {
        var item = document.createElement('div');
        var iconEl = document.createElement('span');
        var icon = document.createElement('i');
        var nameEl = document.createElement('span');
        item.className = 'select-group-item selected';
        item.dataset.id = 'root';
        item.dataset.level = '-1';
        iconEl.className = 'select-group-item-icon';
        icon.className = 'fas fa-home';
        nameEl.className = 'select-group-item-name';
        nameEl.textContent = bookT('book.shelfHome');
        iconEl.appendChild(icon);
        item.appendChild(iconEl);
        item.appendChild(nameEl);
        tree.appendChild(item);
    }

    function updateSelectGroupModalCopy(modal) {
        var title = modal.querySelector('#selectGroupModalTitle');
        var close = modal.querySelector('#selectGroupCloseBtn');
        var confirmButton = modal.querySelector('#selectGroupConfirmBtn');
        if (title) title.textContent = bookT('book.addToShelfTitle');
        if (close) close.setAttribute('aria-label', bookT('book.closeGroupChooser'));
        if (confirmButton) confirmButton.lastChild.textContent = ' ' + bookT('book.confirm');
    }

    function showSelectGroupModal() {
        var modal = document.getElementById('selectGroupModal');
        if (!modal) {
            modal = document.createElement('div');
            modal.className = 'select-group-modal';
            modal.id = 'selectGroupModal';
            modal.innerHTML =
                '<div class="select-group-content">' +
                    '<div class="select-group-header">' +
                        '<h3 id="selectGroupModalTitle"></h3>' +
                        '<button class="select-group-close-btn" id="selectGroupCloseBtn">' +
                            '<i class="fas fa-times"></i>' +
                        '</button>' +
                    '</div>' +
                    '<div class="select-group-body">' +
                        '<div class="select-group-tree" id="selectGroupTree"></div>' +
                    '</div>' +
                    '<div class="select-group-footer">' +
                        '<button class="select-group-confirm-btn" id="selectGroupConfirmBtn">' +
                            '<i class="fas fa-check"></i><span></span>' +
                        '</button>' +
                    '</div>' +
                '</div>';
            document.body.appendChild(modal);
            updateSelectGroupModalCopy(modal);

            modal.querySelector('#selectGroupCloseBtn').addEventListener('click', function() {
                modal.classList.remove('active');
            });

            modal.querySelector('#selectGroupConfirmBtn').addEventListener('click', async function() {
                var selected = modal.querySelector('.select-group-item.selected');
                if (selected) {
                    var targetId = selected.dataset.id;
                    var shelfData = getBookshelf();

                    if (targetId === 'root') {
                        shelfData.items.unshift(bookHash);
                        if (!shelfData.order) {
                            shelfData.order = [];
                        }
                        shelfData.order.unshift(bookHash);
                    } else {
                        var targetGroup = findGroupById(shelfData, targetId);
                        if (targetGroup) {
                            targetGroup.items.unshift(bookHash);
                            if (!targetGroup.order) {
                                targetGroup.order = [];
                            }
                            targetGroup.order.unshift(bookHash);
                        }
                    }

                    if (await persistBookshelf(shelfData)) {
                        showNotification(bookT('book.addedToShelf'), 'success');
                        updateButtonState();
                        modal.classList.remove('active');
                    }
                }
            });

            modal.addEventListener('click', function(e) {
                if (e.target === modal) {
                    modal.classList.remove('active');
                }
            });
        }

        updateSelectGroupModalCopy(modal);
        var tree = modal.querySelector('#selectGroupTree');
        tree.innerHTML = '';
        addRootGroup(tree);

        var shelfData = getBookshelf();
        renderGroupTree(tree, shelfData.groups, 0);

        tree.querySelector('[data-id="root"]').addEventListener('click', function() {
            tree.querySelectorAll('.select-group-item').forEach(function(i) {
                i.classList.remove('selected');
            });
            this.classList.add('selected');
        });

        modal.classList.add('active');
    }

    function findGroupById(shelfData, groupId) {
        if (shelfData.groups && shelfData.groups[groupId]) {
            return shelfData.groups[groupId];
        }

        for (var gId in shelfData.groups) {
            var found = findGroupInGroup(shelfData.groups[gId], groupId);
            if (found) return found;
        }
        return null;
    }

    function findGroupInGroup(group, groupId) {
        if (group.groups && group.groups[groupId]) {
            return group.groups[groupId];
        }

        if (group.groups) {
            for (var gId in group.groups) {
                var found = findGroupInGroup(group.groups[gId], groupId);
                if (found) return found;
            }
        }
        return null;
    }

    if (toggleShelfBtn.dataset.bookShelfBound) {
        window.refreshBookShelfButton = updateButtonState;
        updateButtonState();
        return;
    }
    toggleShelfBtn.dataset.bookShelfBound = 'true';
    toggleShelfBtn.addEventListener('click', async function() {
        if (!await ensureServerBookshelf()) return;
        var shelfData = getBookshelf();
        var inShelf = isBookInShelf(bookHash, shelfData);

        if (inShelf) {
            removeBookFromShelf(bookHash, shelfData);
            if (await persistBookshelf(shelfData)) {
                showNotification(bookT('book.removedFromShelf'), 'success');
                updateButtonState();
            }
        } else {
            showSelectGroupModal();
        }
    });

    window.refreshBookShelfButton = updateButtonState;
    if (isServerMode) {
        ensureServerBookshelf().then(function() { updateButtonState(); });
    } else {
        updateButtonState();
    }
}

window.initScriptBook = initScript;
