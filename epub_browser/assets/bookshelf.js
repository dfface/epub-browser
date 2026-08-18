function initBookshelf() {
    var BOOKSHELF_KEY = 'bookshelf';
    var BOOKSHELF_VERSION_KEY = 'bookshelf_version';
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
    
    var bookMetadataCache = null;
    
    function loadBookMetadata(callback) {
        if (bookMetadataCache) {
            callback(bookMetadataCache);
            return;
        }
        
        var metadataUrl = "/book-metadata.json";
        
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
    var bookshelfTagFilter = document.getElementById('bookshelfTagFilter');
    var bookshelfStats = document.getElementById('bookshelfStats');
    var bookshelfLoading = document.getElementById('bookshelfLoading');
    var addShelfGroupBtn = document.getElementById('addShelfGroupBtn');
    var exportShelfBtn = document.getElementById('exportShelfBtn');
    var importShelfBtn = document.getElementById('importShelfBtn');
    var importShelfFile = document.getElementById('importShelfFile');
    var syncShelfBtn = document.getElementById('syncShelfBtn');
    
    var groupModal = document.getElementById('groupModal');
    var groupCloseBtn = document.getElementById('groupCloseBtn');
    var groupBody = document.getElementById('groupBody');
    var groupTagFilter = document.getElementById('groupTagFilter');
    var groupStats = document.getElementById('groupStats');
    var groupLoading = document.getElementById('groupLoading');
    var addGroupSubGroupBtn = document.getElementById('addGroupSubGroupBtn');
    var deleteGroupBtn = document.getElementById('deleteGroupBtn');
    var renameGroupBtn = document.getElementById('renameGroupBtn');
    
    var currentGroupId = null;
    var currentGroupPath = [];
    var currentTag = 'All';
    var bookshelfSortableInstance = null;
    var groupSortableInstance = null;
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
        localStorage.setItem(BOOKSHELF_KEY, JSON.stringify(data));
        incrementBookshelfVersion();
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
                var cover = null;
                if (book.cover) {
                    cover = '/book/' + bookHash + '/' + book.cover;
                }
                return {
                    hash: bookHash,
                    title: book.title,
                    author: authors,
                    cover: cover,
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
    
    // 渲染标签过滤器
    function renderTagFilter(container, tags, activeTag) {
        container.innerHTML = '<span class="bookshelf-tag ' + (activeTag === 'All' ? 'active' : '') + '" data-tag="All" data-i18n="bookshelf.all">' + tr('all') + '</span>';
        container.innerHTML += '<span class="bookshelf-tag ' + (activeTag === 'NoTag' ? 'active' : '') + '" data-tag="NoTag" data-i18n="bookshelf.noTag">' + tr('noTag') + '</span>';
        tags.forEach(function(tag) {
            var tagEl = document.createElement('span');
            tagEl.className = 'bookshelf-tag' + (activeTag === tag ? ' active' : '');
            tagEl.dataset.tag = tag;
            tagEl.textContent = tag;
            container.appendChild(tagEl);
        });
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
        var groupElement = document.createElement('div');
        var coverElement = document.createElement('div');
        var infoElement = document.createElement('div');
        var titleElement = document.createElement('div');
        var subtitleElement = document.createElement('div');
        groupElement.className = 'bookshelf-item group';
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
        var coverElement = document.createElement('div');
        var infoElement = document.createElement('div');
        var titleElement = document.createElement('div');
        var authorElement = document.createElement('div');
        bookElement.className = 'bookshelf-item book';
        bookElement.dataset.id = id;
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
        bookElement.appendChild(coverElement);
        bookElement.appendChild(infoElement);
        return bookElement;
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
                var allTags = getShelfTags(shelfData);
                
                renderTagFilter(bookshelfTagFilter, allTags, tag);
                
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
                    
                    (function(bookHash) {
                        bookEl.addEventListener('click', function() {
                            window.location.href = '/book/' + bookHash + '/index.html';
                        });
                    })(id);
                    
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
        
        var groupTags = getGroupTags(group);
        renderTagFilter(groupTagFilter, groupTags, 'All');
        
        renderGroupContent(group, 'All');
        
        groupModal.classList.add('active');
        document.body.style.overflow = 'hidden';
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
                    
                    (function(bookHash) {
                        bookEl.addEventListener('click', function() {
                            window.location.href = '/book/' + bookHash + '/index.html';
                        });
                    })(id);
                    
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
                onEnd: function(evt) {
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
                    saveBookshelf(shelfData);
                    console.log('Saved order:', newOrder);
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
                onEnd: function(evt) {
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
                    saveBookshelf(shelfData);
                    console.log('Saved group order:', newOrder);
                }
            });
        }
    }
    
    // 添加分组
    addShelfGroupBtn.addEventListener('click', function() {
        var groupName = prompt(tr('groupNamePrompt'));
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
            saveBookshelf(shelfData);
            renderBookshelf(currentTag);
        }
    });
    
    // 添加子分组
    addGroupSubGroupBtn.addEventListener('click', function() {
        var groupName = prompt(tr('groupNamePrompt'));
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
            saveBookshelf(shelfData);
            
            var group = shelfData.groups[currentGroupId];
            for (var i = 0; i < currentGroupPath.length; i++) {
                var pathId = currentGroupPath[i];
                group = group.groups[pathId];
            }
            renderGroupContent(group, currentTag);
        }
    });
    
    // 删除分组
    deleteGroupBtn.addEventListener('click', function() {
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
        
        // 检查是否有嵌套分组
        if (targetGroup.groups && Object.keys(targetGroup.groups).length > 0) {
            showNotification(tr('nestedGroupWarning'), 'warning');
            return;
        }
        
        if (confirm(tr('confirmDeleteGroup', { name: targetGroup.name }))) {
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
            
            saveBookshelf(shelfData);
            
            groupModal.classList.remove('active');
            renderBookshelf(currentTag);
        }
    });
    
    // 重命名分组
    renameGroupBtn.addEventListener('click', function() {
        var shelfData = getBookshelf();
        var targetGroup = shelfData.groups[currentGroupId];
        for (var i = 0; i < currentGroupPath.length; i++) {
            var pathId = currentGroupPath[i];
            targetGroup = targetGroup.groups[pathId];
        }
        
        var newName = prompt(tr('renameGroupPrompt'), targetGroup.name);
        if (newName && newName.trim() && newName.trim() !== targetGroup.name) {
            targetGroup.name = newName.trim();
            saveBookshelf(shelfData);
            
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
    
    // 导入书架数据（文件）
    importShelfBtn.addEventListener('click', function() {
        importShelfFile.click();
    });
    
    importShelfFile.addEventListener('change', function(e) {
        var file = e.target.files[0];
        if (file) {
            var reader = new FileReader();
            reader.onload = function(e) {
                try {
                    var data = JSON.parse(e.target.result);
                    if (data.items && data.groups !== undefined) {
                        saveBookshelf(data);
                        renderBookshelf('All');
                        showNotification(tr('importSucceeded'), 'success');
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
    
    // 同步书架数据
    if (syncShelfBtn) {
        syncShelfBtn.addEventListener('click', async function() {
            var username = getUsername();
            
            if (!username) {
                username = prompt(tr('usernamePrompt'));
                if (!username || !username.trim()) {
                    return;
                }
                username = username.trim();
                setUsername(username);
            }
            
            var version = getBookshelfVersion();
            var shelfData = getBookshelf();
            
            try {
                syncShelfBtn.disabled = true;
                syncShelfBtn.innerHTML = '<i class="fas fa-spinner fa-spin" aria-hidden="true"></i> <span data-i18n="bookshelf.syncing">' + tr('syncing') + '</span>';
                
                var response = await fetch('/sync', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        username: username,
                        version: version,
                        data: shelfData
                    })
                });
                
                if (response.status === 404) {
                    var result = await response.json();
                    if (result.code) {
                        console.warn('Bookshelf sync failed:', result.message);
                        showNotification(syncErrorMessage(result.code), 'warning');
                    } else {
                        setBookshelfVersion(result.version || 1);
                        showNotification(tr('syncNewUser', { username: username }), 'success');
                    }
                } else if (response.status === 200) {
                    var result = await response.json();
                    localStorage.setItem(BOOKSHELF_KEY, JSON.stringify(result.data));
                    setBookshelfVersion(result.version);
                    renderBookshelf(currentTag);
                    showNotification(tr('syncUpdated', { username: username }), 'success');
                } else if (response.status === 304) {
                    showNotification(tr('syncCurrent', { username: username }), 'info');
                } else if (response.status === 405) {
                    showNotification(tr('syncUnavailable', { username: username }), 'warning');
                } else if (response.status === 201) {
                    var result = await response.json();
                    setBookshelfVersion(result.version);
                    showNotification(tr('syncUploaded', { username: username }), 'success');
                } else {
                    var result = await response.json();
                    console.warn('Bookshelf sync failed:', result.message);
                    showNotification(syncErrorMessage(result.code), 'warning');
                }
            } catch (err) {
                console.warn('Bookshelf sync failed:', err);
                showNotification(tr('syncFailed', { username: username }), 'warning');
            } finally {
                syncShelfBtn.disabled = false;
                syncShelfBtn.innerHTML = '<i class="fas fa-sync" aria-hidden="true"></i> <span data-i18n="bookshelf.sync">' + tr('sync') + '</span>';
            }
        });
    }
    
    // 标签过滤点击事件
    bookshelfTagFilter.addEventListener('click', function(e) {
        if (e.target.classList.contains('bookshelf-tag')) {
            currentTag = e.target.dataset.tag;
            bookshelfTagFilter.querySelectorAll('.bookshelf-tag').forEach(function(t) { t.classList.remove('active'); });
            e.target.classList.add('active');
            renderBookshelf(currentTag);
        }
    });
    
    groupTagFilter.addEventListener('click', function(e) {
        if (e.target.classList.contains('bookshelf-tag')) {
            currentTag = e.target.dataset.tag;
            groupTagFilter.querySelectorAll('.bookshelf-tag').forEach(function(t) { t.classList.remove('active'); });
            e.target.classList.add('active');
            
            var shelfData = getBookshelf();
            var group = shelfData.groups[currentGroupId];
            for (var i = 0; i < currentGroupPath.length; i++) {
                var pathId = currentGroupPath[i];
                group = group.groups[pathId];
            }
            renderGroupContent(group, currentTag);
        }
    });
    
    // 打开书架弹窗
    bookshelfBtn.addEventListener('click', function() {
        currentTag = 'All';
        renderBookshelf('All');
        bookshelfModal.classList.add('active');
        document.body.style.overflow = 'hidden';
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

window.initBookShelf = initBookshelf;
