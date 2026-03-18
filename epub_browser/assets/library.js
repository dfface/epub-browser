function initScript() {
    // 设置 cookie
    function setCookie(key, value) {
        const date = new Date();
        date.setTime(date.getTime() + 3650 * 24 * 60 * 60 * 1000); // 3650天的毫秒数
        const expires = "expires=" + date.toUTCString(); // 转换为 UTC 格式
        document.cookie = `${key}=${value}; ${expires}; path=/;`;
    }

    // 解析指定 key 的 Cookie
    function getCookie(key) {
        // 分割所有 Cookie 为数组
        const cookies = document.cookie.split('; ');
        for (const cookie of cookies) {
            // 分割键和值
            const [cookieKey, cookieValue] = cookie.split('=');
            // 解码并返回匹配的值
            if (cookieKey === key) {
            return decodeURIComponent(cookieValue);
            }
        }
        return null; // 未找到
    }

    function deleteCookie(name) {
        // 设置 Cookie 过期时间为过去（例如：1970年1月1日）
        document.cookie = `${name}=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;`;
    }

    // 页面加载时恢复顺序
    function restoreOrder(storageKey, elementClass) {
        var savedOrder = localStorage.getItem(storageKey);
        if (savedOrder) {
            var itemIds = JSON.parse(savedOrder);
            var container = document.querySelector(`.${elementClass}`);
            
            // 按照保存的顺序重新排列元素
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

    let kindleMode = getCookie("kindle-mode") || "false";
    function isKindleMode() {
        return kindleMode == "true";
    }

    const storageKeySortableBook = 'book-grid-sortable-order';
    const storageKeySortableTag = 'tag-cloud-sortable-order';
    const storageKeySortableContainer = 'library-container-sortable-order';

    if (isKindleMode()) {
        document.querySelector("#kindleModeValueNot").style.display = 'none';
        document.querySelector("#kindleModeValueYes").style.display = 'inherit';
        document.body.classList.add("kindle-mode");
    } else {
        document.querySelector("#kindleModeValueNot").style.display = 'inherit';
        document.querySelector("#kindleModeValueYes").style.display = 'none';
        restoreOrder(storageKeySortableBook, 'book-grid');
        restoreOrder(storageKeySortableTag, 'tag-cloud');
        restoreOrder(storageKeySortableContainer, 'container');
    }

    // 拖拽
    var elBook = document.querySelector('.book-grid');
    var elTag = document.querySelector('.tag-cloud');
    var elContainer = document.querySelector('.container');
    if (!isKindleMode()) {
        var sortableBook = Sortable.create(elBook, {
        delay: 300, // 延迟300ms后才开始拖动，避免移动端滑动时误触发
        delayOnTouchOnly: true, // 只在触摸设备上应用延迟
        onEnd: function(evt) {
            // 获取所有项目的ID
            var itemIds = Array.from(evt.from.children).map(function(child) {
                return child.dataset.id;
            });
            // 保存到 localStorage
            localStorage.setItem(storageKeySortableBook, JSON.stringify(itemIds));
        }
        });
        var sortableTag = Sortable.create(elTag, {
        delay: 300, // 延迟300ms后才开始拖动，避免移动端滑动时误触发
        delayOnTouchOnly: true, // 只在触摸设备上应用延迟
        onEnd: function(evt) {
            // 获取所有项目的ID
            var itemIds = Array.from(evt.from.children).map(function(child) {
                return child.dataset.id;
            });
            // 保存到 localStorage
            localStorage.setItem(storageKeySortableTag, JSON.stringify(itemIds));
        }
        });
        var sortableContainer = Sortable.create(elContainer, {
        delay: 300, // 延迟300ms后才开始拖动，给用户选择文字的时间
        delayOnTouchOnly: true, // 只在触摸设备上应用延迟
        filter: '.book-grid, .search-box', // 允许直接选择.content中的文字
        preventOnFilter: false, // 过滤时不阻止默认行为
        onEnd: function(evt) {
            // 获取所有项目的ID
            var itemIds = Array.from(evt.from.children).map(function(child) {
                return child.dataset.id;
            });
            // 保存到 localStorage
            localStorage.setItem(storageKeySortableContainer, JSON.stringify(itemIds));
        }
        });
    }

    // 书籍目录锚点
    const allBookLinks = document.querySelectorAll('.book-card .book-link');
    allBookLinks.forEach(item => {
        let pathParts = item.href.split('/');
        pathParts = pathParts.filter(item => item !== "");
        let book_hash = pathParts[pathParts.length - 2];  // 最后一个是 index.html
        if (!isKindleMode()) {
            let book_anchor = localStorage.getItem(book_hash) || '';
            item.href += book_anchor;
        } else {
            let book_anchor = getCookie(book_hash) || '';
            item.href += book_anchor;
        }
    });

    // 主题切换
    const themeToggle = document.getElementById('themeToggle');
    const themeIcon = themeToggle.querySelector('i');
    let fontFamily = "system-ui, -apple-system, sans-serif";
    let fontFamilyInput = null;

    // 检查本地存储中的主题设置
    let currentTheme = 'light';
    if (!isKindleMode()) {
        currentTheme = localStorage.getItem('theme');
        fontFamily = localStorage.getItem('font_family') || "system-ui, -apple-system, sans-serif";
        fontFamilyInput = localStorage.getItem('font_family_input');
    } else {
        currentTheme = getCookie('theme');
        fontFamily = getCookie('font_family') || "system-ui, -apple-system, sans-serif";
        fontFamilyInput = getCookie('font_family_input');
    }

    // 更新字体
    updateFontFamily(fontFamily, fontFamilyInput);

    // 应用保存的主题
    if (currentTheme === 'dark') {
        document.body.classList.add('dark-mode');
        themeIcon.classList.remove('fa-moon');
        themeIcon.classList.add('fa-sun');
    }

    // 切换主题
    themeToggle.addEventListener('click', function() {
        document.body.classList.toggle('dark-mode');
        
        if (document.body.classList.contains('dark-mode')) {
            themeIcon.classList.remove('fa-moon');
            themeIcon.classList.add('fa-sun');
            if (!isKindleMode()) {
                localStorage.setItem('theme', 'dark');
            } else {
                setCookie('theme', 'dark');
            }
        } else {
            themeIcon.classList.remove('fa-sun');
            themeIcon.classList.add('fa-moon');
            if (!isKindleMode()) {
                localStorage.setItem('theme', 'light');
            } else {
                setCookie('theme', 'light');
            }
        }
    });

    // 搜索功能
    const searchBox = document.querySelector('.search-box');
    const bookCards = document.querySelectorAll('.book-card');
    const tagCloudItems = document.querySelectorAll('.tag-cloud-item');

    // 搜索功能
    searchBox.addEventListener('input', function() {
        const searchTerm = this.value.toLowerCase();
        
        bookCards.forEach(card => {
            const title = card.querySelector('.book-title').textContent.toLowerCase();
            const author = card.querySelector('.book-author').textContent.toLowerCase();
            
            if (title.includes(searchTerm) || author.includes(searchTerm)) {
                card.style.display = 'block';
            } else {
                card.style.display = 'none';
            }
        });
    });

    // 标签云筛选功能
    tagCloudItems.forEach(tag => {
        tag.addEventListener('click', function() {
            // 移除所有标签的active类
            tagCloudItems.forEach(t => t.classList.remove('active'));
            // 为当前点击的标签添加active类
            this.classList.add('active');
            
            const tagText = this.textContent.trim();
            
            if (tagText === 'All') {
                bookCards.forEach(card => {
                    card.style.display = 'block';
                });
            } else if (tagText === 'NoTags') {
                bookCards.forEach(card => {
                    const tags = card.querySelectorAll('.book-tag');
                    let hasTag = tags.length > 0 ? true : false;
                    if (!hasTag) {
                        card.style.display = 'block';
                    } else {
                        card.style.display = 'none';
                    }
                });
            } else {
                bookCards.forEach(card => {
                    const tags = card.querySelectorAll('.book-tag');
                    let hasTag = false;
                    
                    tags.forEach(t => {
                        if (t.textContent === tagText) {
                            hasTag = true;
                        }
                    });
                    
                    if (hasTag) {
                        card.style.display = 'block';
                    } else {
                        card.style.display = 'none';
                    }
                });
            }
        });
    });

    // 书籍标签点击筛选功能
    const bookTags = document.querySelectorAll('.book-tag');
    bookTags.forEach(tag => {
        tag.addEventListener('click', function(e) {
            e.preventDefault();
            e.stopPropagation();
            
            const tagText = this.textContent;
            
            // 移除所有标签云的active类
            tagCloudItems.forEach(t => t.classList.remove('active'));
            
            // 激活对应的标签云项
            tagCloudItems.forEach(t => {
                if (t.textContent === tagText) {
                    t.classList.add('active');
                }
            });
            
            // 筛选书籍
            bookCards.forEach(card => {
                const tags = card.querySelectorAll('.book-tag');
                let hasTag = false;
                
                tags.forEach(t => {
                    if (t.textContent === tagText) {
                        hasTag = true;
                    }
                });
                
                if (hasTag) {
                    card.style.display = 'block';
                } else {
                    card.style.display = 'none';
                }
            });
        });
    });

    // 滚动到顶部功能
    const scrollToTopBtn = document.getElementById('scrollToTopBtn');

    scrollToTopBtn.addEventListener('click', function() {
        window.scrollTo({
            top: 0,
            behavior: 'smooth'
        });
    });

    // 注册 Service Worker
    if ('serviceWorker' in navigator) {
        window.addEventListener('load', function() {
            navigator.serviceWorker.register('/sw.js')
                .then(function(registration) {
                    console.log('ServiceWorker registration successful with scope: ', registration.scope);
                })
                .catch(function(error) {
                    console.log('ServiceWorker registration failed: ', error);
                });
        });
    }

    // 显示通知
    function showNotification(message, type) {
        // 移除现有通知
        const existingNotification = document.querySelector('.custom-css-notification');
        if (existingNotification) {
            existingNotification.remove();
        }
        // 创建新通知
        const notification = document.createElement('div');
        notification.className = `custom-css-notification ${type}`;
        notification.textContent = message;
        
        // 添加到页面
        document.body.appendChild(notification);
        
        // 自动移除
        setTimeout(() => {
            notification.classList.add('fade-out');
            setTimeout(() => {
                if (notification.parentNode) {
                    notification.parentNode.removeChild(notification);
                }
            }, 300);
        }, 3000);
    }
    
    // 将 showNotification 暴露到全局作用域
    window.showNotification = showNotification;

    // PWA 安装提示和更新按钮
    let deferredPrompt;
    const readingControls = document.querySelector('.reading-controls');
    
    // 安装应用按钮
    const installBtn = document.createElement('button');
    installBtn.id = 'pwa-install-btn';
    installBtn.className = 'control-btn';
    installBtn.innerHTML = '<i class="fas fa-download"></i><div class="control-name">Install</div>';
    installBtn.style.display = 'none';
    if (readingControls) {
        readingControls.appendChild(installBtn);
    }

    // 更新缓存按钮
    const updateCacheBtn = document.createElement('button');
    updateCacheBtn.id = 'update-cache-btn';
    updateCacheBtn.className = 'control-btn';
    updateCacheBtn.innerHTML = '<i class="fas fa-sync"></i><div class="control-name">Update</div>';
    if (readingControls) {
        readingControls.appendChild(updateCacheBtn);
    }

    window.addEventListener('beforeinstallprompt', function(e) {
        e.preventDefault();
        deferredPrompt = e;
        if (installBtn) {
            installBtn.style.display = 'block';
        }
        console.log('PWA install prompt captured');
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
                        console.log('User accepted the install prompt');
                    } else {
                        showNotification('Install cancelled', 'info');
                        console.log('User dismissed the install prompt');
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
                // 发送消息给 Service Worker 清除缓存
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
        if (installBtn) {
            installBtn.style.display = 'none';
        }
        console.log('PWA installed successfully');
    });

    // 隐藏加载动画
    function hideLoading() {
        const overlay = document.getElementById('loadingOverlay');
        if (overlay) {
            overlay.style.display = 'none';
        }
    }
    
    // 延迟隐藏加载动画，确保页面完全渲染
    setTimeout(function() {
        hideLoading();
    }, 500);

    // 书架功能（仅非 Kindle 模式）
    if (!isKindleMode()) {
        initBookshelf();
    }

};

// 书架数据结构:
// {
//   "bookshelf": {
//     "items": ["book_hash_1", "book_hash_2", ...],  // 书籍ID数组，支持排序
//     "groups": {
//       "group_id_1": {
//         "id": "group_id_1",
//         "name": "分组名称",
//         "items": ["book_hash_3", ...],  // 分组内的书籍
//         "groups": {}  // 嵌套分组
//       }
//     }
//   }
// }

const BOOKSHELF_KEY = 'bookshelf';

function initBookshelf() {
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
                    if (tag !== 'All' && !groupHasTagInTree(group, tag)) continue;
                
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
                        <div class="bookshelf-item-author">${countGroupItems(group)} items</div>
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
                if (tag !== 'All' && !bookInfo.tags.includes(tag)) continue;
                
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
        
        bookshelfStats.textContent = `${bookCount} books, ${groupCount} groups`;
        
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
    
    // 统计分组内项目数量
    function countGroupItems(group) {
        let count = group.items.length;
        if (group.groups) {
            for (const subGroupId in group.groups) {
                count += countGroupItems(group.groups[subGroupId]);
            }
        }
        return count;
    }
    
    // 打开分组
    function openGroup(groupId, path) {
        currentGroupId = groupId;
        currentGroupPath = path;
        
        const shelfData = getBookshelf();
        let group = shelfData.groups[groupId];
        let fullPath = [group.name];
        
        // 按路径找到嵌套分组并构建完整路径
        let currentParent = shelfData.groups[groupId];
        for (const pathId of path) {
            currentParent = currentParent.groups[pathId];
            fullPath.push(currentParent.name);
            group = currentParent;
        }
        
        // 设置分组标题
        const groupModalTitle = document.getElementById('groupModalTitle');
        if (groupModalTitle) {
            groupModalTitle.innerHTML = `<i class="fas fa-folder"></i> ${fullPath.join(' → ')}`;
        }
        
        const groupTags = getGroupTags(group);
        renderTagFilter(groupTagFilter, groupTags, 'All');
        
        renderGroupContent(group, 'All');
        
        groupModal.classList.add('active');
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
                    if (tag !== 'All' && !groupHasTagInTree(subGroup, tag)) continue;
                    
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
                            <div class="bookshelf-item-author">${countGroupItems(subGroup)} items</div>
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
                    if (tag !== 'All' && !bookInfo.tags.includes(tag)) continue;
                    
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
        
        groupStats.textContent = `${bookCount} books, ${subGroupCount} groups`;
        
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
        
        if (currentGroupPath.length > 0) {
            targetGroup = shelfData.groups[currentGroupId];
            for (let i = 0; i < currentGroupPath.length - 1; i++) {
                targetGroup = targetGroup.groups[currentGroupPath[i]];
            }
            if (currentGroupPath.length > 0) {
                targetId = currentGroupPath[currentGroupPath.length - 1];
                parentGroups = targetGroup.groups;
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
                const shelfData = getBookshelf();
                let parentGroup = shelfData.groups[currentGroupId];
                for (let i = 0; i < currentGroupPath.length - 1; i++) {
                    parentGroup = parentGroup.groups[currentGroupPath[i]];
                }
                if (parentGroup.order) {
                    parentGroup.order = parentGroup.order.filter(id => id !== targetId);
                }
                saveBookshelf(shelfData);
            } else {
                const shelfData = getBookshelf();
                if (shelfData.order) {
                    shelfData.order = shelfData.order.filter(id => id !== targetId);
                }
                saveBookshelf(shelfData);
            }
            
            groupModal.classList.remove('active');
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
    });
    
    // 关闭书架弹窗
    bookshelfCloseBtn.addEventListener('click', function() {
        bookshelfModal.classList.remove('active');
    });
    
    // 关闭分组弹窗
    groupCloseBtn.addEventListener('click', function() {
        groupModal.classList.remove('active');
        currentGroupId = null;
        currentGroupPath = [];
    });
    
    // 点击弹窗外部关闭
    bookshelfModal.addEventListener('click', function(e) {
        if (e.target === bookshelfModal) {
            bookshelfModal.classList.remove('active');
        }
    });
    
    groupModal.addEventListener('click', function(e) {
        if (e.target === groupModal) {
            groupModal.classList.remove('active');
            currentGroupId = null;
            currentGroupPath = [];
        }
    });
    
    // 暴露全局函数供 book.js 使用
    window.bookshelfUtils = {
        getBookshelf,
        saveBookshelf,
        isBookInShelf,
        getBookInfo,
        generateId
    };
}

// 如果DOM已经加载完成，立即初始化
window.initScriptLibrary = initScript;