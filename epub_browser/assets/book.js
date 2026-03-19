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

function updateFontFamily(fontFamily, fontFamilyInput) {
    if (fontFamily == "custom") {
        document.body.style.fontFamily = fontFamilyInput;
    } else {
        document.body.style.fontFamily = fontFamily;
    }
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

// 删除指定前缀的所有 localStorage 键
function deleteKeysByPrefix(prefix) {
    const keysToDelete = [];
    
    // 遍历 localStorage 中的所有键
    for (let i = 0; i < localStorage.length; i++) {
        const key = localStorage.key(i);
        
        // 检查键是否以指定前缀开头
        if (key.startsWith(prefix)) {
            keysToDelete.push(key);
        }
    }
    
    // 删除匹配的键
    keysToDelete.forEach(key => {
        localStorage.removeItem(key);
        console.log(`Deleted: ${key}`);
    });
    
    return keysToDelete.length;
}

function initScript() {
    const path = window.location.pathname;  // 获取当前URL路径
    let pathParts = path.split('/');
    pathParts = pathParts.filter(item => item !== "");
    const book_hash = pathParts[pathParts.indexOf('book') + 1];

    let kindleMode = getCookie("kindle-mode") || "false";

    function isKindleMode() {
        return kindleMode == "true";
    }

    // 清除阅读进度
    if (!isKindleMode()) {
        const clearBtn = document.querySelector("#clearReadingProgressBtn");
        clearBtn.addEventListener("click", function() {
            let prefix1 = `scroll_${book_hash}_`;
            let prefix2 = `turning_${book_hash}_`;
            deleteKeysByPrefix(prefix1);
            deleteKeysByPrefix(prefix2);
            deleteKeysByPrefix(book_hash);
            showNotification("All reading progress for this book has been deleted!", "success");
        })
        
        // 书架功能（仅非 Kindle 模式）
        initBookShelfButton(book_hash);
    }

    const storageKeySortableContainer = 'book-container-sortable-order';

    if (isKindleMode()) {
        document.body.classList.add("kindle-mode");
    } else {
        restoreOrder(storageKeySortableContainer, 'container');
    }

    // 拖拽
    var el = document.querySelector('.container');
    if (!isKindleMode()) {
        var sortable = Sortable.create(el, {
        delay: 300, // 延迟300ms后才开始拖动，避免移动端滑动时误触发
        delayOnTouchOnly: true, // 只在触摸设备上应用延迟
        filter: '.toc-container', // 允许直接选择文字
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
    
    // 书籍目录锚点删除
    const anchor = window.location.hash;
    if (!isKindleMode()) {
        if (anchor === '' || !anchor.startsWith('#chapter_')) {
            localStorage.removeItem(book_hash);  // 此时 lastPart 就是 book_hash
        }
    } else {
        if (anchor === '' || !anchor.startsWith('#chapter_')) {
            deleteCookie(book_hash);  // 此时 lastPart 就是 book_hash
        }
    }
    
    // 主题切换功能
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

    // 滚动到顶部功能
    const scrollToTopBtn = document.getElementById('scrollToTopBtn');
    
    scrollToTopBtn.addEventListener('click', function() {
        window.scrollTo({
            top: 0,
            behavior: 'smooth'
        });
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
};

function initBookShelfButton(bookHash) {
    // 书架功能
    const BOOKSHELF_KEY = 'bookshelf';

    const toggleShelfBtn = document.getElementById('toggleShelfBtn');
    const toggleShelfBtnText = document.getElementById('toggleShelfBtnText');
    
    if (!toggleShelfBtn) return;
    
    // 获取书架数据
    function getBookshelf() {
        const data = localStorage.getItem(BOOKSHELF_KEY);
        if (data) {
            return JSON.parse(data);
        }
        return { items: [], groups: {} };
    }
    
    // 保存书架数据
    function saveBookshelf(data) {
        localStorage.setItem(BOOKSHELF_KEY, JSON.stringify(data));
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
    
    // 更新按钮状态
    function updateButtonState() {
        const shelfData = getBookshelf();
        const inShelf = isBookInShelf(bookHash, shelfData);
        
        if (inShelf) {
            toggleShelfBtnText.textContent = 'Remove from Shelf';
            toggleShelfBtn.classList.add('in-shelf');
        } else {
            toggleShelfBtnText.textContent = 'Add to Shelf';
            toggleShelfBtn.classList.remove('in-shelf');
        }
    }
    
    // 从书架中移除书籍（递归查找并移除）
    function removeBookFromShelf(bookHash, shelfData) {
        const index = shelfData.items.indexOf(bookHash);
        if (index > -1) {
            shelfData.items.splice(index, 1);
            if (shelfData.order) {
                const orderIndex = shelfData.order.indexOf(bookHash);
                if (orderIndex > -1) {
                    shelfData.order.splice(orderIndex, 1);
                }
            }
            return true;
        }
        
        for (const groupId in shelfData.groups) {
            if (removeBookFromGroup(bookHash, shelfData.groups[groupId])) {
                return true;
            }
        }
        return false;
    }
    
    // 从分组中移除书籍（递归）
    function removeBookFromGroup(bookHash, group) {
        const index = group.items.indexOf(bookHash);
        if (index > -1) {
            group.items.splice(index, 1);
            if (group.order) {
                const orderIndex = group.order.indexOf(bookHash);
                if (orderIndex > -1) {
                    group.order.splice(orderIndex, 1);
                }
            }
            return true;
        }
        
        if (group.groups) {
            for (const subGroupId in group.groups) {
                if (removeBookFromGroup(bookHash, group.groups[subGroupId])) {
                    return true;
                }
            }
        }
        return false;
    }
    
    // 渲染分组树
    function renderGroupTree(container, groups, level = 0, parentPath = '') {
        for (const groupId in groups) {
            const group = groups[groupId];
            const fullPath = parentPath ? `${parentPath} → ${group.name}` : group.name;
            const itemEl = document.createElement('div');
            itemEl.className = 'select-group-item';
            itemEl.dataset.id = groupId;
            itemEl.dataset.level = level;
            itemEl.innerHTML = `
                <span class="select-group-item-icon"><i class="fas fa-folder"></i></span>
                <span class="select-group-item-name">${fullPath}</span>
            `;
            itemEl.addEventListener('click', function() {
                container.querySelectorAll('.select-group-item').forEach(i => i.classList.remove('selected'));
                this.classList.add('selected');
            });
            container.appendChild(itemEl);
            
            if (group.groups && Object.keys(group.groups).length > 0) {
                renderGroupTree(container, group.groups, level + 1, fullPath);
            }
        }
    }
    
    // 显示选择分组弹窗
    function showSelectGroupModal() {
        let modal = document.getElementById('selectGroupModal');
        if (!modal) {
            modal = document.createElement('div');
            modal.className = 'select-group-modal';
            modal.id = 'selectGroupModal';
            modal.innerHTML = `
                <div class="select-group-content">
                    <div class="select-group-header">
                        <h3>Add to Shelf</h3>
                        <button class="select-group-close-btn" id="selectGroupCloseBtn">
                            <i class="fas fa-times"></i>
                        </button>
                    </div>
                    <div class="select-group-body">
                        <div class="select-group-tree" id="selectGroupTree">
                            <div class="select-group-item selected" data-id="root" data-level="-1">
                                <span class="select-group-item-icon"><i class="fas fa-home"></i></span>
                                <span class="select-group-item-name">Shelf Home</span>
                            </div>
                        </div>
                    </div>
                    <div class="select-group-footer">
                        <button class="select-group-confirm-btn" id="selectGroupConfirmBtn">
                            <i class="fas fa-check"></i> Confirm
                        </button>
                    </div>
                </div>
            `;
            document.body.appendChild(modal);
            
            modal.querySelector('#selectGroupCloseBtn').addEventListener('click', function() {
                modal.classList.remove('active');
            });
            
            modal.querySelector('#selectGroupConfirmBtn').addEventListener('click', function() {
                const selected = modal.querySelector('.select-group-item.selected');
                if (selected) {
                    const targetId = selected.dataset.id;
                    const shelfData = getBookshelf();
                    
                    if (targetId === 'root') {
                        shelfData.items.unshift(bookHash);
                        if (!shelfData.order) {
                            shelfData.order = [];
                        }
                        shelfData.order.unshift(bookHash);
                    } else {
                        let targetGroup = findGroupById(shelfData, targetId);
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
        
        const tree = modal.querySelector('#selectGroupTree');
        tree.innerHTML = `
            <div class="select-group-item selected" data-id="root" data-level="-1">
                <span class="select-group-item-icon"><i class="fas fa-home"></i></span>
                <span class="select-group-item-name">Shelf Home</span>
            </div>
        `;
        
        const shelfData = getBookshelf();
        renderGroupTree(tree, shelfData.groups, 0);
        
        tree.querySelector('[data-id="root"]').addEventListener('click', function() {
            tree.querySelectorAll('.select-group-item').forEach(i => i.classList.remove('selected'));
            this.classList.add('selected');
        });
        
        modal.classList.add('active');
    }
    
    // 根据ID查找分组
    function findGroupById(shelfData, groupId) {
        if (shelfData.groups && shelfData.groups[groupId]) {
            return shelfData.groups[groupId];
        }
        
        for (const gId in shelfData.groups) {
            const found = findGroupInGroup(shelfData.groups[gId], groupId);
            if (found) return found;
        }
        return null;
    }
    
    // 在分组中递归查找分组
    function findGroupInGroup(group, groupId) {
        if (group.groups && group.groups[groupId]) {
            return group.groups[groupId];
        }
        
        if (group.groups) {
            for (const gId in group.groups) {
                const found = findGroupInGroup(group.groups[gId], groupId);
                if (found) return found;
            }
        }
        return null;
    }
    
    // 切换书架状态
    toggleShelfBtn.addEventListener('click', function() {
        const shelfData = getBookshelf();
        const inShelf = isBookInShelf(bookHash, shelfData);
        
        if (inShelf) {
            removeBookFromShelf(bookHash, shelfData);
            saveBookshelf(shelfData);
            showNotification('Book removed from shelf!', 'success');
            updateButtonState();
        } else {
            showSelectGroupModal();
        }
    });
    
    // 初始化按钮状态
    updateButtonState();
}

window.initScriptBook = initScript;