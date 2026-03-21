function initScript() {
    // 设置 cookie
    function setCookie(key, value) {
        const date = new Date();
        date.setTime(date.getTime() + 3650 * 24 * 60 * 60 * 1000);
        const expires = "expires=" + date.toUTCString();
        // 重点：加上 SameSite=Lax，和你的按钮完全一致
        document.cookie = key + "=" + value + ";" + expires + "; path=/; SameSite=Lax";
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
        document.cookie = name + "=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;";
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

    let kindleMode = getCookie("kindle-mode") || "false";  // 不能是 true，1 是默认就没设置 2 是点击后也是没设置
    if (window.location.hash == "#kindle") {  // 保底方案
        kindleMode = "true";
    } else if (window.location.hash == "#not-kindle") {
        kindleMode = "false";
    }
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
    function pwaSupport() {
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
    }

    function bookshelfSupport() {
        const bookshelfBtn = document.getElementById('bookshelfBtn');
        if (bookshelfBtn) {
            bookshelfBtn.style.display = 'inherit';
        }
        if (window.initBookshelf) {
            window.initBookshelf();
        } else {
            setTimeout(bookshelfSupport, 100)
        }
    }

    // 书架功能（仅非 Kindle 模式）
    if (!isKindleMode()) {
        pwaSupport();
        bookshelfSupport();
    }

    // 隐藏加载动画
    function hideLoading() {
        const overlay = document.getElementById('loadingOverlay');
        if (overlay) {
            overlay.style.display = 'none';
        }
    }

    setTimeout(hideLoading, 500);
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

// 如果DOM已经加载完成，立即初始化
window.initScriptLibrary = initScript;