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

function updateFontFamily(fontFamily, fontFamilyInput) {
    if (fontFamily == "custom") {
        document.body.style.fontFamily = fontFamilyInput;
    } else {
        document.body.style.fontFamily = fontFamily;
    }
}

// 显示通知
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

    if (!isKindleMode()) {
        var clearBtn = document.querySelector("#clearReadingProgressBtn");
        clearBtn.addEventListener("click", function() {
            var prefix1 = "scroll_" + book_hash + "_";
            var prefix2 = "turning_" + book_hash + "_";
            deleteKeysByPrefix(prefix1);
            deleteKeysByPrefix(prefix2);
            deleteKeysByPrefix(book_hash);
            showNotification("All reading progress for this book has been deleted!", "success");
        });

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
        var bookshelfBtn = document.getElementById('bookshelfBtn');
        if (bookshelfBtn) bookshelfBtn.style.display = 'inherit';
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
    if (currentChapter !== "") {
        var chapterElement = document.getElementById(currentChapter);

        if (!chapterElement) {
            var chapterLinks = document.querySelectorAll('.chapter-link');
            for (var i = 0; i < chapterLinks.length; i++) {
                var link = chapterLinks[i];
                var linkId = link.id;
                if (linkId) {
                    var cleanId = linkId.split('#')[0];
                    if (cleanId === currentChapter) {
                        chapterElement = link;
                        break;
                    }
                }
            }
        }

        if (chapterElement) {
            chapterElement.classList.add('active');
            var tocContainer = document.querySelector('.chapter-list');
            if (isKindleMode()) {
                tocContainer = document.documentElement;
            }
            if (tocContainer) {
                tocContainer.scrollTop = chapterElement.offsetTop - tocContainer.offsetTop - 50;
            }
        }
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

    var scrollToTopBtn = document.getElementById('scrollToTopBtn');
    scrollToTopBtn.addEventListener('click', function() {
        window.scrollTo({
            top: 0,
            behavior: 'smooth'
        });
    });

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

function initBookShelfButton(bookHash) {
    var BOOKSHELF_KEY = 'bookshelf';
    var BOOKSHELF_VERSION_KEY = 'bookshelf_version';

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
        var data = localStorage.getItem(BOOKSHELF_KEY);
        if (data) {
            return JSON.parse(data);
        }
        return { items: [], groups: {} };
    }

    function saveBookshelf(data) {
        localStorage.setItem(BOOKSHELF_KEY, JSON.stringify(data));
        incrementBookshelfVersion();
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
            toggleShelfBtnText.textContent = 'Remove from Shelf';
            toggleShelfBtn.classList.add('in-shelf');
        } else {
            toggleShelfBtnText.textContent = 'Add to Shelf';
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
            itemEl.className = 'select-group-item';
            itemEl.dataset.id = groupId;
            itemEl.dataset.level = level;
            itemEl.innerHTML =
                '<span class="select-group-item-icon"><i class="fas fa-folder"></i></span>' +
                '<span class="select-group-item-name">' + fullPath + '</span>';
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

    function showSelectGroupModal() {
        var modal = document.getElementById('selectGroupModal');
        if (!modal) {
            modal = document.createElement('div');
            modal.className = 'select-group-modal';
            modal.id = 'selectGroupModal';
            modal.innerHTML =
                '<div class="select-group-content">' +
                    '<div class="select-group-header">' +
                        '<h3>Add to Shelf</h3>' +
                        '<button class="select-group-close-btn" id="selectGroupCloseBtn">' +
                            '<i class="fas fa-times"></i>' +
                        '</button>' +
                    '</div>' +
                    '<div class="select-group-body">' +
                        '<div class="select-group-tree" id="selectGroupTree">' +
                            '<div class="select-group-item selected" data-id="root" data-level="-1">' +
                                '<span class="select-group-item-icon"><i class="fas fa-home"></i></span>' +
                                '<span class="select-group-item-name">Shelf Home</span>' +
                            '</div>' +
                        '</div>' +
                    '</div>' +
                    '<div class="select-group-footer">' +
                        '<button class="select-group-confirm-btn" id="selectGroupConfirmBtn">' +
                            '<i class="fas fa-check"></i> Confirm' +
                        '</button>' +
                    '</div>' +
                '</div>';
            document.body.appendChild(modal);

            modal.querySelector('#selectGroupCloseBtn').addEventListener('click', function() {
                modal.classList.remove('active');
            });

            modal.querySelector('#selectGroupConfirmBtn').addEventListener('click', function() {
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

                    saveBookshelf(shelfData);
                    showNotification('Book added to shelf!', 'success');
                    updateButtonState();
                    modal.classList.remove('active');
                }
            });

            modal.addEventListener('click', function(e) {
                if (e.target === modal) {
                    modal.classList.remove('active');
                }
            });
        }

        var tree = modal.querySelector('#selectGroupTree');
        tree.innerHTML =
            '<div class="select-group-item selected" data-id="root" data-level="-1">' +
                '<span class="select-group-item-icon"><i class="fas fa-home"></i></span>' +
                '<span class="select-group-item-name">Shelf Home</span>' +
            '</div>';

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

    toggleShelfBtn.addEventListener('click', function() {
        var shelfData = getBookshelf();
        var inShelf = isBookInShelf(bookHash, shelfData);

        if (inShelf) {
            removeBookFromShelf(bookHash, shelfData);
            saveBookshelf(shelfData);
            showNotification('Book removed from shelf!', 'success');
            updateButtonState();
        } else {
            showSelectGroupModal();
        }
    });

    updateButtonState();
}

window.initScriptBook = initScript;