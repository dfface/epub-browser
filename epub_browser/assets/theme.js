// 主题切换功能
function initTheme() {
    // 主题列表
    const themes = [
        { id: 'light', name: 'Light', icon: 'fa-sun' },
        { id: 'dark', name: 'Dark', icon: 'fa-moon' },
        { id: 'sepia', name: 'Sepia', icon: 'fa-book' },
        { id: 'forest', name: 'Forest', icon: 'fa-tree' },
        { id: 'ocean', name: 'Ocean', icon: 'fa-water' }
    ];

    // 检查本地存储中的主题设置
    function getCurrentTheme() {
        const isKindle = getCookie("kindle-mode") === "true";
        if (!isKindle) {
            return localStorage.getItem('theme') || 'light';
        } else {
            return getCookie('theme') || 'light';
        }
    }

    // 保存主题设置
    function saveTheme(theme) {
        const isKindle = getCookie("kindle-mode") === "true";
        if (!isKindle) {
            localStorage.setItem('theme', theme);
        } else {
            setCookie('theme', theme);
        }
    }

    // 应用主题
    function applyTheme(theme) {
        // 移除所有主题类
        document.body.classList.remove('light-mode', 'dark-mode', 'sepia-mode', 'forest-mode', 'ocean-mode');
        // 添加当前主题类
        document.body.classList.add(`${theme}-mode`);
        
        // 保存主题设置
        saveTheme(theme);
        
        // 切换代码主题（如果存在）
        if (typeof switchCodeTheme === 'function') {
            switchCodeTheme(theme === 'dark');
        }
    }

    // 创建主题选择菜单
    function createThemeMenu() {
        const menu = document.createElement('div');
        menu.className = 'theme-menu';
        menu.style.position = 'absolute';
        menu.style.top = '100%';
        menu.style.right = '0';
        menu.style.marginTop = '8px';
        menu.style.background = 'white';
        menu.style.border = '1px solid #ddd';
        menu.style.borderRadius = '4px';
        menu.style.boxShadow = '0 2px 10px rgba(0,0,0,0.1)';
        menu.style.zIndex = '1000';
        menu.style.padding = '8px 0';
        menu.style.minWidth = '120px';
        
        themes.forEach(theme => {
            const item = document.createElement('div');
            item.className = 'theme-menu-item';
            item.style.padding = '8px 16px';
            item.style.cursor = 'pointer';
            item.style.display = 'flex';
            item.style.alignItems = 'center';
            item.style.gap = '8px';
            item.style.fontSize = '14px';
            
            item.addEventListener('mouseenter', function() {
                item.style.background = '#f5f5f5';
            });
            
            item.addEventListener('mouseleave', function() {
                item.style.background = 'transparent';
            });
            
            item.addEventListener('click', function() {
                applyTheme(theme.id);
                menu.style.display = 'none';
            });
            
            item.innerHTML = `<i class="fas ${theme.icon}"></i>${theme.name}`;
            menu.appendChild(item);
        });
        
        return menu;
    }

    // 初始化主题
    function init() {
        const themeToggle = document.getElementById('themeToggle');
        if (!themeToggle) return;

        const mobileThemeBtn = document.getElementById('mobileThemeBtn');
        const isKindle = getCookie("kindle-mode") === "true";

        // 应用初始主题
        const currentTheme = getCurrentTheme();
        applyTheme(currentTheme);

        // 初始化主题菜单
        let themeMenu = null;
        function handleThemeToggle(e) {
            e.stopPropagation();
            
            if (isKindle) {
                // Kindle 模式下保持原有切换行为
                const currentTheme = getCurrentTheme();
                const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
                applyTheme(newTheme);
            } else {
                // 非 Kindle 模式下显示主题选择菜单
                if (!themeMenu) {
                    themeMenu = createThemeMenu();
                    themeToggle.parentNode.appendChild(themeMenu);
                    themeMenu.style.display = 'none';
                }
                
                themeMenu.style.display = themeMenu.style.display === 'none' ? 'block' : 'none';
            }
        }

        // 绑定主题切换事件
        themeToggle.addEventListener('click', handleThemeToggle);
        if (mobileThemeBtn) {
            mobileThemeBtn.addEventListener('click', handleThemeToggle);
        }

        // 点击其他地方关闭主题菜单
        document.addEventListener('click', function(e) {
            if (themeMenu && !themeToggle.contains(e.target) && !themeMenu.contains(e.target) && (!mobileThemeBtn || !mobileThemeBtn.contains(e.target))) {
                themeMenu.style.display = 'none';
            }
        });
    }

    // 工具函数：获取 Cookie
    function getCookie(key) {
        const cookies = document.cookie.split('; ');
        for (const cookie of cookies) {
            const [cookieKey, cookieValue] = cookie.split('=');
            if (cookieKey === key) {
                return decodeURIComponent(cookieValue);
            }
        }
        return null;
    }

    // 工具函数：设置 Cookie
    function setCookie(key, value) {
        const date = new Date();
        date.setTime(date.getTime() + 3650 * 24 * 60 * 60 * 1000);
        const expires = "expires=" + date.toUTCString();
        document.cookie = `${key}=${value}; ${expires}; path=/;`;
    }

    // 初始化
    init();
}

// 导出函数
window.initTheme = initTheme;