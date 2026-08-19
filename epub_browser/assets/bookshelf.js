/* Server mode keeps the bookshelf document in the server database, never in localStorage. */
(function(root) {
    var state = { username: '', version: 0, data: null, savedData: null };

    function emptyBookshelf() {
        return { items: [], groups: {}, order: [] };
    }

    function copy(data) {
        return JSON.parse(JSON.stringify(data || emptyBookshelf()));
    }

    function apiUrl() {
        var prefix = root.EpubBrowserBasePath || '/';
        if (prefix.charAt(prefix.length - 1) !== '/') prefix += '/';
        return prefix + 'api/bookshelf';
    }

    function request(method, username, body) {
        var options = { method: method, headers: { 'X-Username': username } };
        if (body) {
            options.headers['Content-Type'] = 'application/json';
            options.body = JSON.stringify(body);
        }
        return Promise.resolve(fetch(apiUrl(), options)).then(function(response) {
            return response.json().catch(function() { return {}; }).then(function(payload) {
                if (!response.ok) return { error: payload || {} };
                return payload;
            });
        }, function() { return { error: { code: 'server_error' } }; });
    }

    root.EpubBookshelfStore = {
        isServerMode: function() { return root.EpubBrowserMode === 'server'; },
        data: function() { return state.data ? copy(state.data) : null; },
        load: function(username) {
            if (root.EpubBrowserMode !== 'server') return Promise.resolve({ data: null, version: 0 });
            return request('GET', username).then(function(result) {
                if (result.error) return result;
                state.username = username;
                state.version = result.version;
                state.data = copy(result.data);
                state.savedData = copy(result.data);
                return { data: copy(state.data), version: state.version };
            });
        },
        save: function(username, data) {
            if (root.EpubBrowserMode !== 'server') return Promise.resolve({ data: data });
            return request('PUT', username, { version: state.version, data: data }).then(function(result) {
                if (result.error) {
                    if (result.error.code === 'bookshelf_conflict' && result.error.data) {
                        state.version = result.error.version;
                        state.data = copy(result.error.data);
                        state.savedData = copy(result.error.data);
                    } else if (state.savedData) {
                        state.data = copy(state.savedData);
                    }
                    return result;
                }
                state.version = result.version;
                state.data = copy(result.data);
                state.savedData = copy(result.data);
                return { data: copy(state.data), version: state.version };
            });
        }
    };
})(typeof window !== 'undefined' ? window : globalThis);

function bookshelfMetadataUrl(basePath) {
    var prefix = basePath || '/';
    if (prefix.charAt(prefix.length - 1) !== '/') prefix += '/';
    return prefix + 'book-metadata.json';
}

function bookshelfCoverUrl(book) {
    return book && book.cover ? book.cover : null;
}

function initBookshelf() {
    var BOOKSHELF_KEY = 'bookshelf';
    var BOOKSHELF_VERSION_KEY = 'bookshelf_version';
    var USERNAME_KEY = 'epub_browser_username';
    var isServerMode = window.EpubBookshelfStore && window.EpubBookshelfStore.isServerMode();

    function getUsername() {
        if (isKindleMode()) {
            return getCookie(USERNAME_KEY);
        }
        return localStorage.getItem(USERNAME_KEY);
    }

    var bookMetadataCache = null;
    
    function loadBookMetadata(callback) {
        if (bookMetadataCache) {
            callback(bookMetadataCache);
            return;
        }
        
        var metadataUrl = bookshelfMetadataUrl(window.EpubBrowserBasePath);
        
        var xhr = new XMLHttpRequest();
        xhr.open('GET', metadataUrl, true);
        xhr.onreadystatechange = function() {
            if (xhr.readyState === 4) {
                if (xhr.status === 200) {
                    try {
                        bookMetadataCache = JSON.parse(xhr.responseText);
                        callback(bookMetadataCache);
                    } catch (e) {
                        console.error('Failed to parse book metadata:', e);
                        callback([]);
                    }
                } else {
                    console.error('Failed to load book metadata:', xhr.status);
                    callback([]);
                }
            }
        };
        xhr.send();
    }
    
    var bookshelfBtn = document.getElementById('bookshelfBtn');
    var bookshelfModal = document.getElementById('bookshelfModal');
    var bookshelfCloseBtn = document.getElementById('bookshelfCloseBtn');
    var bookshelfBody = document.getElementById('bookshelfBody');
    var bookshelfStats = document.getElementById('bookshelfStats');
    var bookshelfLoading = document.getElementById('bookshelfLoading');
    var addShelfGroupBtn = document.getElementById('addShelfGroupBtn');
    var addShelfBookBtn = document.getElementById('addShelfBookBtn');
    var exportShelfBtn = document.getElementById('exportShelfBtn');
    var importShelfBtn = document.getElementById('importShelfBtn');
    var importShelfFile = document.getElementById('importShelfFile');
    if (isServerMode) {
        if (exportShelfBtn) exportShelfBtn.remove();
        if (importShelfBtn) importShelfBtn.remove();
        if (importShelfFile) importShelfFile.remove();
    }
    
    var groupModal = document.getElementById('groupModal');
    var groupCloseBtn = document.getElementById('groupCloseBtn');
    var groupBody = document.getElementById('groupBody');
    var groupStats = document.getElementById('groupStats');
    var groupLoading = document.getElementById('groupLoading');
    var addGroupSubGroupBtn = document.getElementById('addGroupSubGroupBtn');
    var addGroupBookBtn = document.getElementById('addGroupBookBtn');
    var deleteGroupBtn = document.getElementById('deleteGroupBtn');
    var renameGroupBtn = document.getElementById('renameGroupBtn');
    
    var currentGroupId = null;
    var currentGroupPath = [];
    var currentTag = 'All';
    var bookshelfSortableInstance = null;
    var groupSortableInstance = null;
    var bookSearchModal = null;
    var i18n = window.EpubBrowserI18n;

    function tr(key, params) {
        return i18n ? i18n.t('bookshelf.' + key, params) : key;
    }

    function syncErrorMessage(code) {
        var knownCodes = {
            username_required: true,
            invalid_json: true,
            no_sync_data: true,
            not_found: true,
            annotation_not_found: true,
            invalid_chapter_index: true,
            batch_requires_post: true,
            database_unavailable: true,
            reading_progress_not_found: true,
            bookshelf_conflict: true,
            not_ready: true,
            server_error: true
        };
        return tr('error.' + (knownCodes[code] ? code : 'unknown'));
    }

    function getCurrentGroup() {
        var shelfData = getBookshelf();
        var group = shelfData.groups[currentGroupId];
        for (var i = 0; group && i < currentGroupPath.length; i++) {
            group = group.groups[currentGroupPath[i]];
        }
        return group;
    }
    
    // 获取书架版本号
    function getBookshelfVersion() {
        var version = localStorage.getItem(BOOKSHELF_VERSION_KEY);
        return version ? parseInt(version, 10) : 1;
    }
    
    // 设置书架版本号
    function setBookshelfVersion(version) {
        localStorage.setItem(BOOKSHELF_VERSION_KEY, version.toString());
    }
    
    // 增加书架版本号
    function incrementBookshelfVersion() {
        var currentVersion = getBookshelfVersion();
        setBookshelfVersion(currentVersion + 1);
    }
    
    // 获取书架数据
    function getBookshelf() {
        if (isServerMode) {
            return window.EpubBookshelfStore.data() || { items: [], groups: {}, order: [] };
        }
        var data = localStorage.getItem(BOOKSHELF_KEY);
        if (data) {
            var shelfData = JSON.parse(data);
            // 兼容旧数据：如果没有 order，根据 items 和 groups 生成
            if (!shelfData.order) {
                shelfData.order = [...(shelfData.items || []), ...Object.keys(shelfData.groups || {})];
            }
            return shelfData;
        }
        return { items: [], groups: {}, order: [] };
    }
    
    // 保存书架数据
    function saveBookshelf(data) {
        if (isServerMode) {
            return window.EpubBookshelfStore.save(getUsername(), data);
        }
        localStorage.setItem(BOOKSHELF_KEY, JSON.stringify(data));
        incrementBookshelfVersion();
        return Promise.resolve({ data: data });
    }

    function ensureServerBookshelf() {
        if (!isServerMode) return Promise.resolve(true);
        var username = getUsername();
        if (!username) {
            showNotification(tr('loginRequired'), 'warning');
            return Promise.resolve(false);
        }
        return window.EpubBookshelfStore.load(username).then(function(result) {
            if (result.error) {
                showNotification(syncErrorMessage(result.error.code), 'warning');
                return false;
            }
            return true;
        });
    }

    function persistBookshelf(data) {
        return saveBookshelf(data).then(function(result) {
            if (result.error) {
                showNotification(syncErrorMessage(result.error.code), 'warning');
                return false;
            }
            return true;
        });
    }
    
    // 生成唯一ID
    function generateId() {
        return 'group_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
    }
    
    // 获取书籍信息
    function getBookInfo(bookHash) {
        if (!bookMetadataCache) {
            return null;
        }
        
        for (var i = 0; i < bookMetadataCache.length; i++) {
            if (bookMetadataCache[i].hash === bookHash) {
                var book = bookMetadataCache[i];
                var authors = '';
                if (book.authors && book.authors.length > 0) {
                    authors = book.authors.join(' & ');
                }
                return {
                    hash: bookHash,
                    title: book.title,
                    author: authors,
                    cover: bookshelfCoverUrl(book),
                    tags: book.tags || []
                };
            }
        }
        return null;
    }
    
    // 检查书籍是否在书架中（包括所有分组）
    function isBookInShelf(bookHash, shelfData) {
        if (!shelfData) shelfData = getBookshelf();
        if (shelfData.items.includes(bookHash)) return true;
        for (var groupId in shelfData.groups) {
            if (isBookInGroup(bookHash, shelfData.groups[groupId])) return true;
        }
        return false;
    }
    
    // 检查书籍是否在分组中（递归）
    function isBookInGroup(bookHash, group) {
        if (group.items && group.items.includes(bookHash)) return true;
        if (group.groups) {
            for (var subGroupId in group.groups) {
                if (isBookInGroup(bookHash, group.groups[subGroupId])) return true;
            }
        }
        return false;
    }
    
    // 获取书架中所有书籍的标签
    function getShelfTags(shelfData) {
        var tags = new Set();
        shelfData.items.forEach(function(bookHash) {
            var bookInfo = getBookInfo(bookHash);
            if (bookInfo && bookInfo.tags) {
                bookInfo.tags.forEach(function(tag) { tags.add(tag); });
            }
        });
        for (var groupId in shelfData.groups) {
            var groupTags = getGroupTags(shelfData.groups[groupId]);
            groupTags.forEach(function(tag) { tags.add(tag); });
        }
        return Array.from(tags);
    }
    
    // 获取分组中所有书籍的标签（递归）
    function getGroupTags(group) {
        var tags = new Set();
        group.items.forEach(function(bookHash) {
            var bookInfo = getBookInfo(bookHash);
            if (bookInfo && bookInfo.tags) {
                bookInfo.tags.forEach(function(tag) { tags.add(tag); });
            }
        });
        if (group.groups) {
            for (var subGroupId in group.groups) {
                var subTags = getGroupTags(group.groups[subGroupId]);
                subTags.forEach(function(tag) { tags.add(tag); });
            }
        }
        return Array.from(tags);
    }
    
    function appendIcon(container, className) {
        var icon = document.createElement('i');
        icon.className = className;
        icon.setAttribute('aria-hidden', 'true');
        container.appendChild(icon);
    }

    function renderGroupCovers(container, group) {
        var covers = getGroupCovers(group, 4);
        if (covers.length === 0) {
            appendIcon(container, 'fas fa-folder');
            return;
        }

        var coversElement = document.createElement('div');
        coversElement.className = 'group-covers';
        covers.forEach(function(cover) {
            var coverItem = document.createElement('div');
            var image = document.createElement('img');
            coverItem.className = 'group-cover-item';
            image.src = cover;
            image.alt = '';
            image.loading = 'lazy';
            image.decoding = 'async';
            coverItem.appendChild(image);
            coversElement.appendChild(coverItem);
        });
        for (var i = covers.length; i < 4; i++) {
            var placeholder = document.createElement('div');
            placeholder.className = 'group-cover-item';
            coversElement.appendChild(placeholder);
        }
        container.appendChild(coversElement);
    }

    function createGroupElement(id, group) {
        var groupElement = document.createElement('button');
        var coverElement = document.createElement('div');
        var infoElement = document.createElement('div');
        var titleElement = document.createElement('div');
        var subtitleElement = document.createElement('div');
        groupElement.className = 'bookshelf-item group';
        groupElement.type = 'button';
        groupElement.setAttribute('aria-label', group.name + ': ' + countGroupItems(group));
        groupElement.dataset.id = id;
        coverElement.className = 'bookshelf-item-cover';
        infoElement.className = 'bookshelf-item-info';
        titleElement.className = 'bookshelf-item-title';
        subtitleElement.className = 'bookshelf-item-author';
        titleElement.textContent = group.name;
        subtitleElement.textContent = countGroupItems(group);
        renderGroupCovers(coverElement, group);
        infoElement.appendChild(titleElement);
        infoElement.appendChild(subtitleElement);
        groupElement.appendChild(coverElement);
        groupElement.appendChild(infoElement);
        return groupElement;
    }

    function createBookElement(id, bookInfo) {
        var bookElement = document.createElement('div');
        var openButton = document.createElement('button');
        var removeButton = document.createElement('button');
        var coverElement = document.createElement('div');
        var infoElement = document.createElement('div');
        var titleElement = document.createElement('div');
        var authorElement = document.createElement('div');
        bookElement.className = 'bookshelf-item book';
        bookElement.dataset.id = id;
        openButton.className = 'bookshelf-item-open';
        openButton.type = 'button';
        openButton.setAttribute('aria-label', bookInfo.author ? bookInfo.title + ' — ' + bookInfo.author : bookInfo.title);
        removeButton.className = 'bookshelf-item-remove';
        removeButton.type = 'button';
        removeButton.setAttribute('aria-label', tr('removeBook', { title: bookInfo.title }));
        appendIcon(removeButton, 'fas fa-times');
        coverElement.className = 'bookshelf-item-cover';
        infoElement.className = 'bookshelf-item-info';
        titleElement.className = 'bookshelf-item-title';
        authorElement.className = 'bookshelf-item-author';
        if (bookInfo.cover) {
            var image = document.createElement('img');
            image.src = bookInfo.cover;
            image.alt = bookInfo.title;
            image.loading = 'lazy';
            image.decoding = 'async';
            coverElement.appendChild(image);
        } else {
            appendIcon(coverElement, 'fas fa-book');
        }
        titleElement.textContent = bookInfo.title;
        authorElement.textContent = bookInfo.author;
        infoElement.appendChild(titleElement);
        infoElement.appendChild(authorElement);
        openButton.appendChild(coverElement);
        openButton.appendChild(infoElement);
        bookElement.appendChild(openButton);
        bookElement.appendChild(removeButton);
        return bookElement;
    }

    function bindBookActions(bookElement, bookHash, inGroup) {
        var openButton = bookElement.querySelector('.bookshelf-item-open');
        var removeButton = bookElement.querySelector('.bookshelf-item-remove');
        if (openButton) {
            openButton.addEventListener('click', function() {
                window.location.href = window.EpubBrowserURL.publicPath('/book/' + bookHash + '/index.html');
            });
        }
        if (removeButton) {
            removeButton.addEventListener('click', async function() {
                var bookInfo = getBookInfo(bookHash);
                var title = bookInfo ? bookInfo.title : bookHash;
                if (await window.EpubDialog.confirm({
                    title: tr('removeBook', { title: title }),
                    message: tr('confirmRemoveBook', { title: title }),
                    confirmText: tr('removeBook', { title: title }),
                    destructive: true
                })) {
                    await removeBookFromLocation(bookHash, inGroup);
                }
            });
        }
    }

    function getCurrentGroupFromData(shelfData) {
        var group = shelfData.groups[currentGroupId];
        for (var i = 0; group && i < currentGroupPath.length; i++) {
            group = group.groups[currentGroupPath[i]];
        }
        return group;
    }

    function refreshBookshelfViews() {
        renderBookshelf(currentTag);
        if (groupModal.classList.contains('active') && currentGroupId) {
            var group = getCurrentGroup();
            if (group) renderGroupContent(group, currentTag);
        }
    }

    async function addBookToLocation(bookHash, inGroup) {
        var shelfData = getBookshelf();
        if (isBookInShelf(bookHash, shelfData)) {
            showNotification(tr('bookAlreadyAdded'), 'info');
            return false;
        }
        var target = inGroup ? getCurrentGroupFromData(shelfData) : shelfData;
        if (!target) return false;
        if (!target.items) target.items = [];
        if (!target.order) target.order = [];
        target.items.push(bookHash);
        target.order.push(bookHash);
        if (!await persistBookshelf(shelfData)) return false;
        var bookInfo = getBookInfo(bookHash);
        refreshBookshelfViews();
        showNotification(tr('bookAdded', { title: bookInfo ? bookInfo.title : bookHash }), 'success');
        return true;
    }

    async function removeBookFromLocation(bookHash, inGroup) {
        var shelfData = getBookshelf();
        var target = inGroup ? getCurrentGroupFromData(shelfData) : shelfData;
        if (!target || !target.items) return false;
        var itemIndex = target.items.indexOf(bookHash);
        if (itemIndex === -1) return false;
        target.items.splice(itemIndex, 1);
        if (target.order) {
            target.order = target.order.filter(function(id) { return id !== bookHash; });
        }
        if (!await persistBookshelf(shelfData)) return false;
        var bookInfo = getBookInfo(bookHash);
        refreshBookshelfViews();
        showNotification(tr('bookRemoved', { title: bookInfo ? bookInfo.title : bookHash }), 'success');
        return true;
    }

    function closeBookSearchModal() {
        if (!bookSearchModal) return;
        bookSearchModal.remove();
        bookSearchModal = null;
    }

    function showBookSearch(inGroup) {
        loadBookMetadata(function(metadata) {
            closeBookSearchModal();
            var modal = document.createElement('div');
            var backdrop = document.createElement('div');
            var dialog = document.createElement('section');
            var header = document.createElement('div');
            var title = document.createElement('h3');
            var close = document.createElement('button');
            var label = document.createElement('label');
            var input = document.createElement('input');
            var results = document.createElement('div');

            bookSearchModal = modal;
            modal.className = 'bookshelf-search-modal';
            modal.setAttribute('role', 'dialog');
            modal.setAttribute('aria-modal', 'true');
            modal.setAttribute('aria-labelledby', 'bookshelfSearchTitle');
            backdrop.className = 'bookshelf-search-backdrop';
            dialog.className = 'bookshelf-search-dialog';
            header.className = 'bookshelf-search-header';
            title.id = 'bookshelfSearchTitle';
            title.textContent = tr('searchBooks');
            close.type = 'button';
            close.className = 'bookshelf-close-btn';
            close.setAttribute('aria-label', tr('close'));
            appendIcon(close, 'fas fa-times');
            label.className = 'bookshelf-visually-hidden';
            label.htmlFor = 'bookshelfSearchInput';
            label.textContent = tr('searchBooks');
            input.id = 'bookshelfSearchInput';
            input.className = 'bookshelf-search-input';
            input.type = 'search';
            input.autocomplete = 'off';
            input.placeholder = tr('searchPlaceholder');
            results.className = 'bookshelf-search-results';
            header.appendChild(title);
            header.appendChild(close);
            dialog.appendChild(header);
            dialog.appendChild(label);
            dialog.appendChild(input);
            dialog.appendChild(results);
            modal.appendChild(backdrop);
            modal.appendChild(dialog);
            document.body.appendChild(modal);

            function renderResults() {
                var query = input.value.trim().toLocaleLowerCase();
                var shelfData = getBookshelf();
                var available = metadata.filter(function(book) {
                    return !isBookInShelf(book.hash, shelfData);
                });
                if (query) {
                    available = available.filter(function(book) {
                        return [book.title, (book.authors || []).join(' '), (book.tags || []).join(' ')]
                            .join(' ').toLocaleLowerCase().indexOf(query) !== -1;
                    });
                }
                results.textContent = '';
                if (available.length === 0) {
                    var empty = document.createElement('p');
                    empty.className = 'bookshelf-search-empty';
                    empty.textContent = query ? tr('searchNoResults', { query: input.value.trim() }) : tr('noBooksToAdd');
                    results.appendChild(empty);
                    return;
                }
                available.forEach(function(book) {
                    var result = document.createElement('button');
                    var text = document.createElement('span');
                    var name = document.createElement('strong');
                    var author = document.createElement('small');
                    var action = document.createElement('span');
                    result.className = 'bookshelf-search-result';
                    result.type = 'button';
                    name.textContent = book.title;
                    author.textContent = (book.authors || []).join(' & ');
                    action.textContent = tr('addBook');
                    text.appendChild(name);
                    if (author.textContent) text.appendChild(author);
                    result.appendChild(text);
                    result.appendChild(action);
                    result.addEventListener('click', async function() {
                        if (await addBookToLocation(book.hash, inGroup)) renderResults();
                    });
                    results.appendChild(result);
                });
            }

            close.addEventListener('click', closeBookSearchModal);
            backdrop.addEventListener('click', closeBookSearchModal);
            input.addEventListener('input', renderResults);
            renderResults();
            input.focus();
        });
    }
    
    // 渲染书架内容
    function renderBookshelf(tag) {
        if (!tag) tag = 'All';
        if (bookshelfLoading) {
            bookshelfLoading.classList.remove('hidden');
        }
        
        loadBookMetadata(function(metadata) {
            setTimeout(function() {
                var shelfData = getBookshelf();
                bookshelfBody.innerHTML = '';
                
                var bookCount = 0;
                var groupCount = 0;
                
                // 按照 order 顺序渲染分组和书籍
                var order = shelfData.order || shelfData.items.concat(Object.keys(shelfData.groups || {}));
                for (var i = 0; i < order.length; i++) {
                    var id = order[i];
                    // 检查是否是分组
                    if (shelfData.groups && shelfData.groups[id]) {
                        var group = shelfData.groups[id];
                        if (tag === 'NoTag') {
                            if (!groupHasNoTagInTree(group)) continue;
                        } else if (tag !== 'All' && !groupHasTagInTree(group, tag)) continue;
                    
                    var groupEl = createGroupElement(id, group);
                    
                    (function(groupId) {
                        groupEl.addEventListener('click', function() {
                            openGroup(groupId, []);
                        });
                    })(id);
                    
                    bookshelfBody.appendChild(groupEl);
                    groupCount++;
                } 
                // 检查是否是书籍
                else if (shelfData.items && shelfData.items.indexOf(id) !== -1) {
                    var bookInfo = getBookInfo(id);
                    if (!bookInfo) continue;
                    if (tag === 'NoTag') {
                        if (bookInfo.tags && bookInfo.tags.length > 0) continue;
                    } else if (tag !== 'All' && bookInfo.tags.indexOf(tag) === -1) continue;
                    
                    var bookEl = createBookElement(id, bookInfo);
                    bindBookActions(bookEl, id, false);
                    
                    bookshelfBody.appendChild(bookEl);
                    bookCount++;
                }
            }
            
            if (bookCount === 0 && groupCount === 0) {
                bookshelfBody.innerHTML = 
                    '<div class="bookshelf-empty">' +
                        '<i class="fas fa-bookmark"></i>' +
                        '<p data-i18n="bookshelf.empty">' + tr('empty') + '</p>' +
                    '</div>';
            }
            
            var total = countAllItems(shelfData);
            bookshelfStats.textContent = i18n ? i18n.t('bookshelf.currentStats', {
                books: bookCount,
                groups: groupCount,
                totalBooks: total.books,
                totalGroups: total.groups
            }) : tr('currentStats', {
                books: bookCount,
                groups: groupCount,
                totalBooks: total.books,
                totalGroups: total.groups
            });
            
            // 初始化拖拽排序
            initBookshelfSortable();
            
            if (bookshelfLoading) {
                bookshelfLoading.classList.add('hidden');
            }
            }, 100);
        });
    }
    
    // 检查分组树中是否有书籍包含指定标签
    function groupHasTagInTree(group, tag) {
        for (var i = 0; i < group.items.length; i++) {
            var bookHash = group.items[i];
            var bookInfo = getBookInfo(bookHash);
            if (bookInfo && bookInfo.tags.indexOf(tag) !== -1) return true;
        }
        if (group.groups) {
            for (var subGroupId in group.groups) {
                if (groupHasTagInTree(group.groups[subGroupId], tag)) return true;
            }
        }
        return false;
    }
    
    // 检查分组是否包含无标签书籍
    function groupHasNoTagInTree(group) {
        for (var i = 0; i < group.items.length; i++) {
            var bookHash = group.items[i];
            var bookInfo = getBookInfo(bookHash);
            if (bookInfo && (!bookInfo.tags || bookInfo.tags.length === 0)) return true;
        }
        if (group.groups) {
            for (var subGroupId in group.groups) {
                if (groupHasNoTagInTree(group.groups[subGroupId])) return true;
            }
        }
        return false;
    }
    
    // 获取分组中的封面（递归获取最多n个）
    function getGroupCovers(group, maxCount) {
        var covers = [];
        
        for (var i = 0; i < group.items.length; i++) {
            var bookHash = group.items[i];
            if (covers.length >= maxCount) break;
            var bookInfo = getBookInfo(bookHash);
            if (bookInfo && bookInfo.cover) {
                covers.push(bookInfo.cover);
            }
        }
        
        if (covers.length < maxCount && group.groups) {
            for (var subGroupId in group.groups) {
                if (covers.length >= maxCount) break;
                var subCovers = getGroupCovers(group.groups[subGroupId], maxCount - covers.length);
                covers.push(...subCovers);
            }
        }
        
        return covers;
    }
    
    // 统计分组内直接子项目数量（只统计下一层）
    function countGroupItems(group) {
        var bookCount = (group.items || []).length;
        var groupCount = group.groups ? Object.keys(group.groups).length : 0;
        
        if (bookCount > 0 && groupCount > 0) {
            return tr('groupItems', { books: bookCount, groups: groupCount });
        } else if (bookCount > 0) {
            return tr('groupBooks', { books: bookCount });
        } else if (groupCount > 0) {
            return tr('groupSubgroups', { groups: groupCount });
        } else {
            return tr('emptyGroup');
        }
    }
    
    // 递归统计所有嵌套的书籍和分组数量
    function countAllItems(shelfData) {
        var totalBooks = 0;
        var totalGroups = 0;
        
        function countGroup(group) {
            totalBooks += (group.items || []).length;
            if (group.groups) {
                for (var groupId in group.groups) {
                    totalGroups++;
                    countGroup(group.groups[groupId]);
                }
            }
        }
        
        totalBooks += (shelfData.items || []).length;
        if (shelfData.groups) {
            for (var groupId in shelfData.groups) {
                totalGroups++;
                countGroup(shelfData.groups[groupId]);
            }
        }
        
        return { books: totalBooks, groups: totalGroups };
    }
    
    // 递归统计分组内所有嵌套的书籍和分组数量
    function countAllGroupItems(group) {
        var totalBooks = (group.items || []).length;
        var totalGroups = 0;
        
        if (group.groups) {
            for (var groupId in group.groups) {
                totalGroups++;
                var subResult = countAllGroupItems(group.groups[groupId]);
                totalBooks += subResult.books;
                totalGroups += subResult.groups;
            }
        }
        
        return { books: totalBooks, groups: totalGroups };
    }

    function renderGroupTitle(fullPath, pathIds) {
        var groupModalTitle = document.getElementById('groupModalTitle');
        if (!groupModalTitle) return;

        groupModalTitle.textContent = '';
        // The Home control is moved into this title after the first render, so it
        // may be detached while the title is refreshed for a nested group.
        var homeButton = groupCloseBtn;
        if (homeButton) {
            homeButton.className = 'path-item clickable';
            homeButton.setAttribute('aria-label', tr('title'));
            homeButton.textContent = '';
            appendIcon(homeButton, 'fas fa-home');
            var homeLabel = document.createElement('span');
            homeLabel.textContent = tr('title');
            homeButton.appendChild(homeLabel);
            groupModalTitle.appendChild(homeButton);
            var homeSeparator = document.createElement('span');
            homeSeparator.className = 'path-separator';
            homeSeparator.textContent = '→';
            groupModalTitle.appendChild(homeSeparator);
        }
        appendIcon(groupModalTitle, 'fas fa-folder');
        groupModalTitle.appendChild(document.createTextNode(' '));
        fullPath.forEach(function(name, index) {
            var pathItem;
            if (index > 0) {
                var separator = document.createElement('span');
                separator.className = 'path-separator';
                separator.textContent = '→';
                groupModalTitle.appendChild(document.createTextNode(' '));
                groupModalTitle.appendChild(separator);
                groupModalTitle.appendChild(document.createTextNode(' '));
            }
            pathItem = document.createElement('span');
            pathItem.className = 'path-item' + (index < fullPath.length - 1 ? ' clickable' : '');
            pathItem.textContent = name;
            if (index < fullPath.length - 1) {
                pathItem.dataset.groupId = pathIds[0];
                pathItem.dataset.path = index === 0 ? '' : pathIds.slice(1, index + 1).join(',');
                pathItem.addEventListener('click', function() {
                    var path = this.dataset.path ? this.dataset.path.split(',') : [];
                    openGroup(this.dataset.groupId, path);
                });
            }
            groupModalTitle.appendChild(pathItem);
        });
    }
    
    // 打开分组
    function openGroup(groupId, path) {
        currentGroupId = groupId;
        currentGroupPath = path || [];
        currentTag = 'All';
        
        var shelfData = getBookshelf();
        var group = shelfData.groups[groupId];
        var fullPath = [group.name];
        var pathIds = [groupId];
        
        // 按路径找到嵌套分组并构建完整路径
        var currentParent = shelfData.groups[groupId];
        for (var i = 0; i < currentGroupPath.length; i++) {
            var pathId = currentGroupPath[i];
            currentParent = currentParent.groups[pathId];
            fullPath.push(currentParent.name);
            pathIds.push(pathId);
            group = currentParent;
        }
        
        // 设置分组标题（可点击的路径）
        renderGroupTitle(fullPath, pathIds);
        
        renderGroupContent(group, 'All');
        
        groupModal.classList.add('active');
        document.body.style.overflow = 'hidden';
        var groupContent = groupModal.querySelector('.bookshelf-content');
        if (groupContent) groupContent.focus();
    }
    
    // 渲染分组内容
    function renderGroupContent(group, tag) {
        if (!tag) tag = 'All';
        // 立即清空旧内容，避免闪烁
        groupBody.innerHTML = '';
        if (groupLoading) {
            groupLoading.classList.remove('hidden');
        }
        
        setTimeout(function() {
            
            var bookCount = 0;
            var subGroupCount = 0;
            
            // 按照 order 顺序渲染分组和书籍
            var order = group.order || (group.items || []).concat(Object.keys(group.groups || {}));
            for (var i = 0; i < order.length; i++) {
                var id = order[i];
                // 检查是否是子分组
                if (group.groups && group.groups[id]) {
                    var subGroup = group.groups[id];
                    if (tag === 'NoTag') {
                        if (!groupHasNoTagInTree(subGroup)) continue;
                    } else if (tag !== 'All' && !groupHasTagInTree(subGroup, tag)) continue;
                    
                    var groupEl = createGroupElement(id, subGroup);
                    
                    (function(gId, path) {
                        groupEl.addEventListener('click', function() {
                            openGroup(gId, path);
                        });
                    })(currentGroupId, currentGroupPath.concat([id]));
                    
                    groupBody.appendChild(groupEl);
                    subGroupCount++;
                }
                // 检查是否是书籍
                else if (group.items && group.items.indexOf(id) !== -1) {
                    var bookInfo = getBookInfo(id);
                    if (!bookInfo) continue;
                    if (tag === 'NoTag') {
                        if (bookInfo.tags && bookInfo.tags.length > 0) continue;
                    } else if (tag !== 'All' && bookInfo.tags.indexOf(tag) === -1) continue;
                    
                    var bookEl = createBookElement(id, bookInfo);
                    bindBookActions(bookEl, id, true);
                    
                    groupBody.appendChild(bookEl);
                    bookCount++;
            }
        }
        
        if (bookCount === 0 && subGroupCount === 0) {
            groupBody.innerHTML = 
                '<div class="bookshelf-empty">' +
                    '<i class="fas fa-folder-open"></i>' +
                        '<p data-i18n="bookshelf.groupEmpty">' + tr('groupEmpty') + '</p>' +
                '</div>';
        }
        
        var total = countAllGroupItems(group);
        groupStats.textContent = i18n ? i18n.t('bookshelf.currentStats', {
            books: bookCount,
            groups: subGroupCount,
            totalBooks: total.books,
            totalGroups: total.groups
        }) : tr('currentStats', {
            books: bookCount,
            groups: subGroupCount,
            totalBooks: total.books,
            totalGroups: total.groups
        });
        
        // 初始化拖拽排序
        initGroupSortable();
        
        if (groupLoading) {
            groupLoading.classList.add('hidden');
        }
        }, 100);
    }
    
    // 初始化书架拖拽排序
    function initBookshelfSortable() {
        if (window.Sortable) {
            if (bookshelfSortableInstance) {
                bookshelfSortableInstance.destroy();
            }
            bookshelfSortableInstance = new Sortable(bookshelfBody, {
                animation: 150,
                delay: 300,
                delayOnTouchOnly: true,
                onEnd: async function(evt) {
                    var shelfData = getBookshelf();
                    var newOrder = [];
                    var newItems = [];
                    var newGroups = {};
                    
                    Array.from(bookshelfBody.children).forEach(function(child) {
                        var id = child.dataset.id;
                        newOrder.push(id);
                        if (child.classList.contains('book')) {
                            newItems.push(id);
                        } else if (child.classList.contains('group')) {
                            newGroups[id] = shelfData.groups[id];
                        }
                    });
                    
                    shelfData.order = newOrder;
                    shelfData.items = newItems;
                    shelfData.groups = newGroups;
                    if (!await persistBookshelf(shelfData)) renderBookshelf(currentTag);
                }
            });
        }
    }
    
    // 初始化分组拖拽排序
    function initGroupSortable() {
        if (window.Sortable) {
            if (groupSortableInstance) {
                groupSortableInstance.destroy();
            }
            groupSortableInstance = new Sortable(groupBody, {
                animation: 150,
                delay: 300,
                delayOnTouchOnly: true,
                onEnd: async function(evt) {
                    var shelfData = getBookshelf();
                    var targetGroup = shelfData.groups[currentGroupId];
                    for (var i = 0; i < currentGroupPath.length; i++) {
                        var pathId = currentGroupPath[i];
                        targetGroup = targetGroup.groups[pathId];
                    }
                    
                    var newOrder = [];
                    var newItems = [];
                    var newGroups = {};
                    
                    Array.from(groupBody.children).forEach(function(child) {
                        var id = child.dataset.id;
                        newOrder.push(id);
                        if (child.classList.contains('book')) {
                            newItems.push(id);
                        } else if (child.classList.contains('group')) {
                            newGroups[id] = targetGroup.groups[id];
                        }
                    });
                    
                    targetGroup.order = newOrder;
                    targetGroup.items = newItems;
                    targetGroup.groups = newGroups;
                    if (!await persistBookshelf(shelfData)) {
                        var restoredGroup = getCurrentGroup();
                        if (restoredGroup) renderGroupContent(restoredGroup, currentTag);
                    }
                }
            });
        }
    }
    
    // 添加分组
    addShelfGroupBtn.addEventListener('click', async function() {
        var groupName = await window.EpubDialog.prompt({
            title: tr('addGroup'),
            inputLabel: tr('groupNamePrompt'),
            confirmText: tr('addGroup')
        });
        if (groupName && groupName.trim()) {
            var shelfData = getBookshelf();
            var groupId = generateId();
            shelfData.groups[groupId] = {
                id: groupId,
                name: groupName.trim(),
                items: [],
                groups: {},
                order: []
            };
            if (!shelfData.order) {
                shelfData.order = [];
            }
            shelfData.order.push(groupId);
            if (await persistBookshelf(shelfData)) renderBookshelf(currentTag);
        }
    });

    if (addShelfBookBtn) {
        addShelfBookBtn.addEventListener('click', function() {
            showBookSearch(false);
        });
    }
    
    // 添加子分组
    addGroupSubGroupBtn.addEventListener('click', async function() {
        var groupName = await window.EpubDialog.prompt({
            title: tr('addGroup'),
            inputLabel: tr('groupNamePrompt'),
            confirmText: tr('addGroup')
        });
        if (groupName && groupName.trim()) {
            var shelfData = getBookshelf();
            var targetGroup = shelfData.groups[currentGroupId];
            for (var i = 0; i < currentGroupPath.length; i++) {
                var pathId = currentGroupPath[i];
                targetGroup = targetGroup.groups[pathId];
            }
            
            if (!targetGroup.groups) {
                targetGroup.groups = {};
            }
            if (!targetGroup.order) {
                targetGroup.order = [];
            }
            
            var groupId = generateId();
            targetGroup.groups[groupId] = {
                id: groupId,
                name: groupName.trim(),
                items: [],
                groups: {},
                order: []
            };
            targetGroup.order.push(groupId);
            if (!await persistBookshelf(shelfData)) return;
            
            var group = shelfData.groups[currentGroupId];
            for (var i = 0; i < currentGroupPath.length; i++) {
                var pathId = currentGroupPath[i];
                group = group.groups[pathId];
            }
            renderGroupContent(group, currentTag);
        }
    });

    if (addGroupBookBtn) {
        addGroupBookBtn.addEventListener('click', function() {
            showBookSearch(true);
        });
    }
    
    // 删除分组
    deleteGroupBtn.addEventListener('click', async function() {
        var shelfData = getBookshelf();
        var targetGroup = shelfData;
        var parentGroups = shelfData.groups;
        var targetId = currentGroupId;
        var parentGroup = null;
        
        if (currentGroupPath.length > 0) {
            targetGroup = shelfData.groups[currentGroupId];
            parentGroup = targetGroup;
            for (var i = 0; i < currentGroupPath.length - 1; i++) {
                parentGroup = parentGroup.groups[currentGroupPath[i]];
            }
            if (currentGroupPath.length > 0) {
                targetId = currentGroupPath[currentGroupPath.length - 1];
                parentGroups = parentGroup.groups;
                targetGroup = targetGroup.groups[targetId];
            }
        } else {
            targetGroup = shelfData.groups[currentGroupId];
            parentGroups = shelfData.groups;
        }

        if (!targetGroup) {
            console.warn('Unable to delete bookshelf group: current group was not found.');
            showNotification(tr('error.unknown'), 'error');
            return;
        }
        
        // 检查是否有嵌套分组
        if (targetGroup.groups && Object.keys(targetGroup.groups).length > 0) {
            showNotification(tr('nestedGroupWarning'), 'warning');
            return;
        }
        
        if (await window.EpubDialog.confirm({
            title: tr('deleteGroup'),
            message: tr('confirmDeleteGroup', { name: targetGroup.name }),
            confirmText: tr('deleteGroup'),
            destructive: true
        })) {
            delete parentGroups[targetId];
            
            if (currentGroupPath.length > 0) {
                if (parentGroup.order) {
                    parentGroup.order = parentGroup.order.filter(function(id) { return id !== targetId; });
                }
            } else {
                if (shelfData.order) {
                    shelfData.order = shelfData.order.filter(function(id) { return id !== targetId; });
                }
            }
            
            if (!await persistBookshelf(shelfData)) return;
            
            groupModal.classList.remove('active');
            renderBookshelf(currentTag);
            showNotification(tr('groupDeleted', { name: targetGroup.name }), 'success');
        }
    });
    
    // 重命名分组
    renameGroupBtn.addEventListener('click', async function() {
        var shelfData = getBookshelf();
        var targetGroup = shelfData.groups[currentGroupId];
        for (var i = 0; i < currentGroupPath.length; i++) {
            var pathId = currentGroupPath[i];
            targetGroup = targetGroup.groups[pathId];
        }
        
        var newName = await window.EpubDialog.prompt({
            title: tr('rename'),
            inputLabel: tr('renameGroupPrompt'),
            defaultValue: targetGroup.name,
            selectOnOpen: true,
            confirmText: tr('rename')
        });
        if (newName && newName.trim() && newName.trim() !== targetGroup.name) {
            targetGroup.name = newName.trim();
            if (!await persistBookshelf(shelfData)) return;
            
            var fullPath = [shelfData.groups[currentGroupId].name];
            var pathIds = [currentGroupId];
            var currentParent = shelfData.groups[currentGroupId];
            for (var i = 0; i < currentGroupPath.length; i++) {
                var pathId = currentGroupPath[i];
                currentParent = currentParent.groups[pathId];
                fullPath.push(currentParent.name);
                pathIds.push(pathId);
            }
            renderGroupTitle(fullPath, pathIds);
            
            var group = shelfData.groups[currentGroupId];
            for (var i = 0; i < currentGroupPath.length; i++) {
                var pathId = currentGroupPath[i];
                group = group.groups[pathId];
            }
            renderGroupContent(group, currentTag);
            renderBookshelf(currentTag);
        }
    });
    
    // 导出书架数据
    if (!isServerMode && exportShelfBtn) {
        exportShelfBtn.addEventListener('click', function() {
            var shelfData = getBookshelf();
            var dataStr = JSON.stringify(shelfData, null, 2);
            var blob = new Blob([dataStr], { type: 'application/json' });
            var url = URL.createObjectURL(blob);
            var a = document.createElement('a');
            a.href = url;
            a.download = 'bookshelf_data.json';
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
        });
    }
    
    // 导入书架数据（文件）
    if (!isServerMode && importShelfBtn) {
        importShelfBtn.addEventListener('click', function() {
            importShelfFile.click();
        });
    }
    
    if (!isServerMode && importShelfFile) importShelfFile.addEventListener('change', async function(e) {
        var file = e.target.files[0];
        if (file) {
            var reader = new FileReader();
            reader.onload = async function(e) {
                try {
                    var data = JSON.parse(e.target.result);
                    if (data.items && data.groups !== undefined) {
                        if (await persistBookshelf(data)) {
                            renderBookshelf('All');
                            showNotification(tr('importSucceeded'), 'success');
                        }
                    } else {
                        showNotification(tr('importInvalid'), 'warning');
                    }
                } catch (err) {
                    console.warn('Failed to parse bookshelf import:', err);
                    showNotification(tr('importParseFailed'), 'warning');
                }
            };
            reader.readAsText(file);
        }
        e.target.value = '';
    });
    
    // 打开书架弹窗
    bookshelfBtn.addEventListener('click', async function() {
        if (!await ensureServerBookshelf()) return;
        currentTag = 'All';
        renderBookshelf('All');
        bookshelfModal.classList.add('active');
        document.body.style.overflow = 'hidden';
        var content = bookshelfModal.querySelector('.bookshelf-content');
        if (content) content.focus();
    });
    
    // 关闭书架弹窗
    bookshelfCloseBtn.addEventListener('click', function() {
        bookshelfModal.classList.remove('active');
        document.body.style.overflow = '';
    });
    
    // 关闭分组弹窗
    groupCloseBtn.addEventListener('click', function() {
        groupModal.classList.remove('active');
        currentGroupId = null;
        currentGroupPath = [];
    });
    
    // 关闭所有弹窗（分组和书架）
    var groupCloseAllBtn = document.getElementById('groupCloseAllBtn');
    if (groupCloseAllBtn) {
        groupCloseAllBtn.addEventListener('click', function() {
            groupModal.classList.remove('active');
            bookshelfModal.classList.remove('active');
            document.body.style.overflow = '';
            currentGroupId = null;
            currentGroupPath = [];
        });
    }
    
    // 点击弹窗外部关闭
    bookshelfModal.addEventListener('click', function(e) {
        if (e.target === bookshelfModal) {
            bookshelfModal.classList.remove('active');
            document.body.style.overflow = '';
        }
    });
    
    groupModal.addEventListener('click', function(e) {
        if (e.target === groupModal) {
            groupModal.classList.remove('active');
            currentGroupId = null;
            currentGroupPath = [];
        }
    });

    document.addEventListener('keydown', function(e) {
        if (e.key !== 'Escape') return;
        if (bookSearchModal) {
            closeBookSearchModal();
            return;
        }
        if (groupModal.classList.contains('active')) {
            groupModal.classList.remove('active');
            currentGroupId = null;
            currentGroupPath = [];
            return;
        }
        if (bookshelfModal.classList.contains('active')) {
            bookshelfModal.classList.remove('active');
            document.body.style.overflow = '';
            bookshelfBtn.focus();
        }
    });

    if (i18n && i18n.onLocaleChange) {
        i18n.onLocaleChange(function() {
            if (bookshelfModal && bookshelfModal.classList.contains('active')) {
                renderBookshelf(currentTag);
            }
            if (groupModal && groupModal.classList.contains('active') && currentGroupId) {
                var group = getCurrentGroup();
                if (group) renderGroupContent(group, currentTag);
            }
        });
    }
}

if (typeof window !== 'undefined') window.initBookShelf = initBookshelf;
if (typeof module === 'object' && module.exports) {
    module.exports = {
        metadataUrl: bookshelfMetadataUrl,
        coverUrl: bookshelfCoverUrl
    };
}
