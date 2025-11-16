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
        onEnd: function(evt) {
            // 获取所有项目的ID
            var itemIds = Array.from(evt.from.children).map(function(child) {
                return child.dataset.id;
            });
            // 保存到 localStorage
            localStorage.setItem(storageKeySortableTag, JSON.stringify(itemIds));
        }
        });
        var sortableTag = Sortable.create(elContainer, {
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

};

// 如果DOM已经加载完成，立即初始化
window.initScriptLibrary = initScript;