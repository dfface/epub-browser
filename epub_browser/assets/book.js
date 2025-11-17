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
        delay: 10, // 延迟100ms后才开始拖动，给用户选择文字的时间
        delayOnTouchOnly: false, // 在触摸设备上也应用延迟
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
};

window.initScriptBook = initScript;