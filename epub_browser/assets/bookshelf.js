function initBookshelf() {
    const BOOKSHELF_KEY = 'bookshelf';
    
    const bookshelfBtn = document.getElementById('bookshelfBtn');
    const bookshelfModal = document.getElementById('bookshelfModal');
    const bookshelfCloseBtn = document.getElementById('bookshelfCloseBtn');
    const bookshelfBody = document.getElementById('bookshelfBody');
    const bookshelfTagFilter = document.getElementById('bookshelfTagFilter');
    const bookshelfStats = document.getElementById('bookshelfStats');
    const bookshelfLoading = document.getElementById('bookshelfLoading');
    const addShelfGroupBtn = document.getElementById('addShelfGroupBtn');
    const exportShelfBtn = document.getElementById('exportShelfBtn');
    const importShelfBtn = document.getElementById('importShelfBtn');
    const importShelfFile = document.getElementById('importShelfFile');
    
    const groupModal = document.getElementById('groupModal');
    const groupCloseBtn = document.getElementById('groupCloseBtn');
    const groupBody = document.getElementById('groupBody');
    const groupTagFilter = document.getElementById('groupTagFilter');
    const groupStats = document.getElementById('groupStats');
    const groupLoading = document.getElementById('groupLoading');
    const addGroupSubGroupBtn = document.getElementById('addGroupSubGroupBtn');
    const deleteGroupBtn = document.getElementById('deleteGroupBtn');
    const renameGroupBtn = document.getElementById('renameGroupBtn');
    
    let currentGroupId = null;
    let currentGroupPath = [];
    let currentTag = 'All';
    let bookshelfSortableInstance = null;
    let groupSortableInstance = null;
    
    // 获取书架数据
    function getBookshelf() {
        const data = localStorage.getItem(BOOKSHELF_KEY);
        if (data) {
            const shelfData = JSON.parse(data);
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
    }
    
    // 生成唯一ID
    function generateId() {
        return 'group_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
    }
    
    // 获取书籍信息
    function getBookInfo(bookHash) {
        const bookCard = document.querySelector(`.book-card[data-id="${bookHash}"]`);
        if (bookCard) {
            const title = bookCard.querySelector('.book-title')?.textContent || 'Unknown';
            const author = bookCard.querySelector('.book-author')?.textContent || 'Unknown';
            const coverImg = bookCard.querySelector('img[class="book-cover"]');
            const cover = coverImg ? coverImg.src : null;
            const tags = Array.from(bookCard.querySelectorAll('.book-tag')).map(t => t.textContent);
            return { hash: bookHash, title, author, cover, tags };
        }
        return null;
    }
    
    // 检查书籍是否在书架中（包括所有分组）
    function isBookInShelf(bookHash, shelfData) {
        if (!shelfData) shelfData = getBookshelf();
        if (shelfData.items.includes(bookHash)) return true;
        for (const groupId in shelfData.groups) {
            if (isBookInGroup(bookHash, shelfData.groups[groupId])) return true;
        }
        return false;
    }
    
    // 检查书籍是否在分组中（递归）
    function isBookInGroup(bookHash, group) {
        if (group.items && group.items.includes(bookHash)) return true;
        if (group.groups) {
            for (const subGroupId in group.groups) {
                if (isBookInGroup(bookHash, group.groups[subGroupId])) return true;
            }
        }
        return false;
    }
    
    // 获取书架中所有书籍的标签
    function getShelfTags(shelfData) {
        const tags = new Set();
        shelfData.items.forEach(bookHash => {
            const bookInfo = getBookInfo(bookHash);
            if (bookInfo && bookInfo.tags) {
                bookInfo.tags.forEach(tag => tags.add(tag));
            }
        });
        for (const groupId in shelfData.groups) {
            const groupTags = getGroupTags(shelfData.groups[groupId]);
            groupTags.forEach(tag => tags.add(tag));
        }
        return Array.from(tags);
    }
    
    // 获取分组中所有书籍的标签（递归）
    function getGroupTags(group) {
        const tags = new Set();
        group.items.forEach(bookHash => {
            const bookInfo = getBookInfo(bookHash);
            if (bookInfo && bookInfo.tags) {
                bookInfo.tags.forEach(tag => tags.add(tag));
            }
        });
        if (group.groups) {
            for (const subGroupId in group.groups) {
                const subTags = getGroupTags(group.groups[subGroupId]);
                subTags.forEach(tag => tags.add(tag));
            }
        }
        return Array.from(tags);
    }
    
    // 渲染标签过滤器
    function renderTagFilter(container, tags, activeTag) {
        container.innerHTML = '<span class="bookshelf-tag ' + (activeTag === 'All' ? 'active' : '') + '" data-tag="All">All</span>';
        container.innerHTML += '<span class="bookshelf-tag ' + (activeTag === 'NoTag' ? 'active' : '') + '" data-tag="NoTag">NoTag</span>';
        tags.forEach(tag => {
            const tagEl = document.createElement('span');
            tagEl.className = 'bookshelf-tag' + (activeTag === tag ? ' active' : '');
            tagEl.dataset.tag = tag;
            tagEl.textContent = tag;
            container.appendChild(tagEl);
        });
    }
    
    // 渲染书架内容
    function renderBookshelf(tag = 'All') {
        if (bookshelfLoading) {
            bookshelfLoading.classList.remove('hidden');
        }
        
        setTimeout(() => {
            const shelfData = getBookshelf();
            const allTags = getShelfTags(shelfData);
            
            renderTagFilter(bookshelfTagFilter, allTags, tag);
            
            bookshelfBody.innerHTML = '';
            
            let bookCount = 0;
            let groupCount = 0;
            
            // 按照 order 顺序渲染分组和书籍
            const order = shelfData.order || [...(shelfData.items || []), ...Object.keys(shelfData.groups || {})];
            for (const id of order) {
                // 检查是否是分组
                if (shelfData.groups && shelfData.groups[id]) {
                    const group = shelfData.groups[id];
                    if (tag === 'NoTag') {
                        if (!groupHasNoTagInTree(group)) continue;
                    } else if (tag !== 'All' && !groupHasTagInTree(group, tag)) continue;
                
                const groupEl = document.createElement('div');
                groupEl.className = 'bookshelf-item group';
                groupEl.dataset.id = id;
                
                const coverCoversHtml = renderGroupCovers(group);
                
                groupEl.innerHTML = `
                    <div class="bookshelf-item-cover">
                        ${coverCoversHtml}
                    </div>
                    <div class="bookshelf-item-info">
                        <div class="bookshelf-item-title">${group.name}</div>
                        <div class="bookshelf-item-author">${countGroupItems(group)}</div>
                    </div>
                `;
                groupEl.addEventListener('click', () => openGroup(id, []));
                bookshelfBody.appendChild(groupEl);
                groupCount++;
            } 
            // 检查是否是书籍
            else if (shelfData.items && shelfData.items.includes(id)) {
                const bookInfo = getBookInfo(id);
                if (!bookInfo) continue;
                if (tag === 'NoTag') {
                    if (bookInfo.tags && bookInfo.tags.length > 0) continue;
                } else if (tag !== 'All' && !bookInfo.tags.includes(tag)) continue;
                
                const bookEl = document.createElement('div');
                bookEl.className = 'bookshelf-item book';
                bookEl.dataset.id = id;
                bookEl.innerHTML = `
                    <div class="bookshelf-item-cover">
                        ${bookInfo.cover ? `<img src="${bookInfo.cover}" alt="${bookInfo.title}">` : '<i class="fas fa-book"></i>'}
                    </div>
                    <div class="bookshelf-item-info">
                        <div class="bookshelf-item-title">${bookInfo.title}</div>
                        <div class="bookshelf-item-author">${bookInfo.author}</div>
                    </div>
                `;
                bookEl.addEventListener('click', () => {
                    window.location.href = `/book/${id}/index.html`;
                });
                bookshelfBody.appendChild(bookEl);
                bookCount++;
            }
        }
        
        if (bookCount === 0 && groupCount === 0) {
            bookshelfBody.innerHTML = `
                <div class="bookshelf-empty">
                    <i class="fas fa-bookmark"></i>
                    <p>Your bookshelf is empty</p>
                </div>
            `;
        }
        
        const total = countAllItems(shelfData);
        bookshelfStats.textContent = `Current: ${bookCount} book(s), ${groupCount} group(s) | Total: ${total.books} book(s), ${total.groups} group(s)`;
        
        // 初始化拖拽排序
        initBookshelfSortable();
        
        if (bookshelfLoading) {
            bookshelfLoading.classList.add('hidden');
        }
        }, 100);
    }
    
    // 检查分组树中是否有书籍包含指定标签
    function groupHasTagInTree(group, tag) {
        for (const bookHash of group.items) {
            const bookInfo = getBookInfo(bookHash);
            if (bookInfo && bookInfo.tags.includes(tag)) return true;
        }
        if (group.groups) {
            for (const subGroupId in group.groups) {
                if (groupHasTagInTree(group.groups[subGroupId], tag)) return true;
            }
        }
        return false;
    }
    
    // 检查分组是否包含无标签书籍
    function groupHasNoTagInTree(group) {
        for (const bookHash of group.items) {
            const bookInfo = getBookInfo(bookHash);
            if (bookInfo && (!bookInfo.tags || bookInfo.tags.length === 0)) return true;
        }
        if (group.groups) {
            for (const subGroupId in group.groups) {
                if (groupHasNoTagInTree(group.groups[subGroupId])) return true;
            }
        }
        return false;
    }
    
    // 渲染分组封面（拼接最多4本书的封面）
    function renderGroupCovers(group) {
        const covers = getGroupCovers(group, 4);
        if (covers.length === 0) {
            return '<i class="fas fa-folder"></i>';
        }
        
        let html = '<div class="group-covers">';
        covers.forEach(cover => {
            html += `<div class="group-cover-item"><img src="${cover}" alt=""></div>`;
        });
        // 填充空白
        for (let i = covers.length; i < 4; i++) {
            html += '<div class="group-cover-item"></div>';
        }
        html += '</div>';
        return html;
    }
    
    // 获取分组中的封面（递归获取最多n个）
    function getGroupCovers(group, maxCount) {
        const covers = [];
        
        for (const bookHash of group.items) {
            if (covers.length >= maxCount) break;
            const bookInfo = getBookInfo(bookHash);
            if (bookInfo && bookInfo.cover) {
                covers.push(bookInfo.cover);
            }
        }
        
        if (covers.length < maxCount && group.groups) {
            for (const subGroupId in group.groups) {
                if (covers.length >= maxCount) break;
                const subCovers = getGroupCovers(group.groups[subGroupId], maxCount - covers.length);
                covers.push(...subCovers);
            }
        }
        
        return covers;
    }
    
    // 统计分组内直接子项目数量（只统计下一层）
    function countGroupItems(group) {
        const bookCount = (group.items || []).length;
        const groupCount = group.groups ? Object.keys(group.groups).length : 0;
        
        if (bookCount > 0 && groupCount > 0) {
            return `${bookCount} books, ${groupCount} subgroups`;
        } else if (bookCount > 0) {
            return `${bookCount} books`;
        } else if (groupCount > 0) {
            return `${groupCount} subgroups`;
        } else {
            return 'Empty group';
        }
    }
    
    // 递归统计所有嵌套的书籍和分组数量
    function countAllItems(shelfData) {
        let totalBooks = 0;
        let totalGroups = 0;
        
        function countGroup(group) {
            totalBooks += (group.items || []).length;
            if (group.groups) {
                for (const groupId in group.groups) {
                    totalGroups++;
                    countGroup(group.groups[groupId]);
                }
            }
        }
        
        totalBooks += (shelfData.items || []).length;
        if (shelfData.groups) {
            for (const groupId in shelfData.groups) {
                totalGroups++;
                countGroup(shelfData.groups[groupId]);
            }
        }
        
        return { books: totalBooks, groups: totalGroups };
    }
    
    // 递归统计分组内所有嵌套的书籍和分组数量
    function countAllGroupItems(group) {
        let totalBooks = (group.items || []).length;
        let totalGroups = 0;
        
        if (group.groups) {
            for (const groupId in group.groups) {
                totalGroups++;
                const subResult = countAllGroupItems(group.groups[groupId]);
                totalBooks += subResult.books;
                totalGroups += subResult.groups;
            }
        }
        
        return { books: totalBooks, groups: totalGroups };
    }
    
    // 打开分组
    function openGroup(groupId, path) {
        currentGroupId = groupId;
        currentGroupPath = path || [];
        
        const shelfData = getBookshelf();
        let group = shelfData.groups[groupId];
        let fullPath = [group.name];
        let pathIds = [groupId];
        
        // 按路径找到嵌套分组并构建完整路径
        let currentParent = shelfData.groups[groupId];
        for (const pathId of currentGroupPath) {
            currentParent = currentParent.groups[pathId];
            fullPath.push(currentParent.name);
            pathIds.push(pathId);
            group = currentParent;
        }
        
        // 设置分组标题（可点击的路径）
        const groupModalTitle = document.getElementById('groupModalTitle');
        if (groupModalTitle) {
            let pathHtml = '<i class="fas fa-folder"></i> ';
            fullPath.forEach((name, index) => {
                if (index > 0) {
                    pathHtml += ' <span class="path-separator">→</span> ';
                }
                if (index < fullPath.length - 1) {
                    pathHtml += `<span class="path-item clickable" data-group-id="${pathIds[0]}" data-path="${index === 0 ? '' : pathIds.slice(1, index + 1).join(',')}">${name}</span>`;
                } else {
                    pathHtml += `<span class="path-item">${name}</span>`;
                }
            });
            groupModalTitle.innerHTML = pathHtml;
            
            // 添加点击事件
            groupModalTitle.querySelectorAll('.path-item.clickable').forEach(item => {
                item.addEventListener('click', function() {
                    const groupId = this.dataset.groupId;
                    const pathStr = this.dataset.path;
                    const path = pathStr ? pathStr.split(',') : [];
                    openGroup(groupId, path);
                });
            });
        }
        
        const groupTags = getGroupTags(group);
        renderTagFilter(groupTagFilter, groupTags, 'All');
        
        renderGroupContent(group, 'All');
        
        groupModal.classList.add('active');
        document.body.style.overflow = 'hidden';
    }
    
    // 渲染分组内容
    function renderGroupContent(group, tag = 'All') {
        if (groupLoading) {
            groupLoading.classList.remove('hidden');
        }
        
        setTimeout(() => {
            groupBody.innerHTML = '';
            
            let bookCount = 0;
            let subGroupCount = 0;
            
            // 按照 order 顺序渲染分组和书籍
            const order = group.order || [...(group.items || []), ...Object.keys(group.groups || {})];
            for (const id of order) {
                // 检查是否是子分组
                if (group.groups && group.groups[id]) {
                    const subGroup = group.groups[id];
                    if (tag === 'NoTag') {
                        if (!groupHasNoTagInTree(subGroup)) continue;
                    } else if (tag !== 'All' && !groupHasTagInTree(subGroup, tag)) continue;
                    
                    const groupEl = document.createElement('div');
                    groupEl.className = 'bookshelf-item group';
                    groupEl.dataset.id = id;
                    
                    const coverCoversHtml = renderGroupCovers(subGroup);
                    
                    groupEl.innerHTML = `
                        <div class="bookshelf-item-cover">
                            ${coverCoversHtml}
                        </div>
                        <div class="bookshelf-item-info">
                            <div class="bookshelf-item-title">${subGroup.name}</div>
                            <div class="bookshelf-item-author">${countGroupItems(subGroup)}</div>
                        </div>
                    `;
                    groupEl.addEventListener('click', () => openGroup(currentGroupId, [...currentGroupPath, id]));
                    groupBody.appendChild(groupEl);
                    subGroupCount++;
                }
                // 检查是否是书籍
                else if (group.items && group.items.includes(id)) {
                    const bookInfo = getBookInfo(id);
                    if (!bookInfo) continue;
                    if (tag === 'NoTag') {
                        if (bookInfo.tags && bookInfo.tags.length > 0) continue;
                    } else if (tag !== 'All' && !bookInfo.tags.includes(tag)) continue;
                    
                    const bookEl = document.createElement('div');
                    bookEl.className = 'bookshelf-item book';
                    bookEl.dataset.id = id;
                    bookEl.innerHTML = `
                        <div class="bookshelf-item-cover">
                            ${bookInfo.cover ? `<img src="${bookInfo.cover}" alt="${bookInfo.title}">` : '<i class="fas fa-book"></i>'}
                        </div>
                        <div class="bookshelf-item-info">
                            <div class="bookshelf-item-title">${bookInfo.title}</div>
                            <div class="bookshelf-item-author">${bookInfo.author}</div>
                        </div>
                    `;
                    bookEl.addEventListener('click', () => {
                        window.location.href = `/book/${id}/index.html`;
                    });
                    groupBody.appendChild(bookEl);
                    bookCount++;
            }
        }
        
        if (bookCount === 0 && subGroupCount === 0) {
            groupBody.innerHTML = `
                <div class="bookshelf-empty">
                    <i class="fas fa-folder-open"></i>
                    <p>This group is empty</p>
                </div>
            `;
        }
        
        const total = countAllGroupItems(group);
        groupStats.textContent = `Current: ${bookCount} book(s), ${subGroupCount} group(s) | Total: ${total.books} book(s), ${total.groups} group(s)`;
        
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
                    const shelfData = getBookshelf();
                    const newOrder = [];
                    const newItems = [];
                    const newGroups = {};
                    
                    Array.from(bookshelfBody.children).forEach(child => {
                        const id = child.dataset.id;
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
                    const shelfData = getBookshelf();
                    let targetGroup = shelfData.groups[currentGroupId];
                    for (const pathId of currentGroupPath) {
                        targetGroup = targetGroup.groups[pathId];
                    }
                    
                    const newOrder = [];
                    const newItems = [];
                    const newGroups = {};
                    
                    Array.from(groupBody.children).forEach(child => {
                        const id = child.dataset.id;
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
        const groupName = prompt('Enter group name:');
        if (groupName && groupName.trim()) {
            const shelfData = getBookshelf();
            const groupId = generateId();
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
        const groupName = prompt('Enter group name:');
        if (groupName && groupName.trim()) {
            const shelfData = getBookshelf();
            let targetGroup = shelfData.groups[currentGroupId];
            for (const pathId of currentGroupPath) {
                targetGroup = targetGroup.groups[pathId];
            }
            
            if (!targetGroup.groups) {
                targetGroup.groups = {};
            }
            if (!targetGroup.order) {
                targetGroup.order = [];
            }
            
            const groupId = generateId();
            targetGroup.groups[groupId] = {
                id: groupId,
                name: groupName.trim(),
                items: [],
                groups: {},
                order: []
            };
            targetGroup.order.push(groupId);
            saveBookshelf(shelfData);
            
            let group = shelfData.groups[currentGroupId];
            for (const pathId of currentGroupPath) {
                group = group.groups[pathId];
            }
            renderGroupContent(group, currentTag);
        }
    });
    
    // 删除分组
    deleteGroupBtn.addEventListener('click', function() {
        const shelfData = getBookshelf();
        let targetGroup = shelfData;
        let parentGroups = shelfData.groups;
        let targetId = currentGroupId;
        let parentGroup = null;
        
        if (currentGroupPath.length > 0) {
            targetGroup = shelfData.groups[currentGroupId];
            parentGroup = targetGroup;
            for (let i = 0; i < currentGroupPath.length - 1; i++) {
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
            showNotification('Please delete all nested groups first before deleting this group.', 'error');
            return;
        }
        
        if (confirm(`Are you sure you want to delete the group "${targetGroup.name}"?`)) {
            delete parentGroups[targetId];
            
            if (currentGroupPath.length > 0) {
                if (parentGroup.order) {
                    parentGroup.order = parentGroup.order.filter(id => id !== targetId);
                }
            } else {
                if (shelfData.order) {
                    shelfData.order = shelfData.order.filter(id => id !== targetId);
                }
            }
            
            saveBookshelf(shelfData);
            
            groupModal.classList.remove('active');
            renderBookshelf(currentTag);
        }
    });
    
    // 重命名分组
    renameGroupBtn.addEventListener('click', function() {
        const shelfData = getBookshelf();
        let targetGroup = shelfData.groups[currentGroupId];
        for (const pathId of currentGroupPath) {
            targetGroup = targetGroup.groups[pathId];
        }
        
        const newName = prompt('Enter new group name:', targetGroup.name);
        if (newName && newName.trim() && newName.trim() !== targetGroup.name) {
            targetGroup.name = newName.trim();
            saveBookshelf(shelfData);
            
            const groupModalTitle = document.getElementById('groupModalTitle');
            if (groupModalTitle) {
                let fullPath = [shelfData.groups[currentGroupId].name];
                let currentParent = shelfData.groups[currentGroupId];
                for (const pathId of currentGroupPath) {
                    currentParent = currentParent.groups[pathId];
                    fullPath.push(currentParent.name);
                }
                groupModalTitle.innerHTML = `<i class="fas fa-folder"></i> ${fullPath.join(' → ')}`;
            }
            
            let group = shelfData.groups[currentGroupId];
            for (const pathId of currentGroupPath) {
                group = group.groups[pathId];
            }
            renderGroupContent(group, currentTag);
            renderBookshelf(currentTag);
        }
    });
    
    // 导出书架数据
    exportShelfBtn.addEventListener('click', function() {
        const shelfData = getBookshelf();
        const dataStr = JSON.stringify(shelfData, null, 2);
        const blob = new Blob([dataStr], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
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
        const file = e.target.files[0];
        if (file) {
            const reader = new FileReader();
            reader.onload = function(e) {
                try {
                    const data = JSON.parse(e.target.result);
                    if (data.items && data.groups !== undefined) {
                        saveBookshelf(data);
                        renderBookshelf('All');
                        showNotification('Bookshelf data imported successfully!', 'success');
                    } else {
                        showNotification('Invalid bookshelf data format.', 'error');
                    }
                } catch (err) {
                    showNotification('Failed to parse JSON file: ' + err.message, 'error');
                }
            };
            reader.readAsText(file);
        }
        e.target.value = '';
    });
    
    // 标签过滤点击事件
    bookshelfTagFilter.addEventListener('click', function(e) {
        if (e.target.classList.contains('bookshelf-tag')) {
            currentTag = e.target.dataset.tag;
            bookshelfTagFilter.querySelectorAll('.bookshelf-tag').forEach(t => t.classList.remove('active'));
            e.target.classList.add('active');
            renderBookshelf(currentTag);
        }
    });
    
    groupTagFilter.addEventListener('click', function(e) {
        if (e.target.classList.contains('bookshelf-tag')) {
            currentTag = e.target.dataset.tag;
            groupTagFilter.querySelectorAll('.bookshelf-tag').forEach(t => t.classList.remove('active'));
            e.target.classList.add('active');
            
            const shelfData = getBookshelf();
            let group = shelfData.groups[currentGroupId];
            for (const pathId of currentGroupPath) {
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
    const groupCloseAllBtn = document.getElementById('groupCloseAllBtn');
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
}

if (!window.initBookShelf) {
    window.initBookShelf = initBookshelf;
}