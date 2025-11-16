document.addEventListener('DOMContentLoaded', function() {
    const path = window.location.pathname;  // 获取当前URL路径
    let pathParts = path.split('/');
    pathParts = pathParts.filter(item => item !== "");
    const book_hash = pathParts[pathParts.indexOf('book') + 1];

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

    let kindleMode = getCookie("kindle-mode") || "false";

    function isKindleMode() {
        return kindleMode == "true";
    }

    if (isKindleMode()) {
        document.body.classList.add("kindle-mode");
    }
    
    // 检查当前的基路径
    if (!path.startsWith("/book/")) {
        // 获取基路径
        let basePath = path.split('/book/');
        basePath = basePath[0] + "/";
        // 处理所有资源，都要加上基路径
        addBasePath(basePath);
    }

    function addBasePath(basePath) {
        // 处理所有链接、图片、脚本和样式表
        const resources = document.querySelectorAll('a[href^="/"], img[src^="/"], script[src^="/"], link[rel="stylesheet"][href^="/"]');
        resources.forEach(resource => {
            const src = resource.getAttribute('src');
            const href = resource.getAttribute('href');
            if (src && !src.startsWith('http') && !src.startsWith('//') && !src.startsWith(basePath)) {
                resource.setAttribute('src', basePath.substr(0, basePath.length - 1) + src);
            }
            if (href && !href.startsWith('http') && !href.startsWith('//') && !href.startsWith(basePath)) {
                resource.setAttribute('href', basePath.substr(0, basePath.length - 1) + href);
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
    
    // 检查本地存储中的主题设置
    let currentTheme = 'light';
    if (!isKindleMode()) {
        currentTheme = localStorage.getItem('theme');
    } else {
        currentTheme = getCookie('theme');
    }
    
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
});