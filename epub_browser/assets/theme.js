// 主题切换功能
function initTheme() {
    // 主题列表
    var themes = [
        { id: 'light', name: 'Light', icon: 'fa-sun' },
        { id: 'dark', name: 'Dark', icon: 'fa-moon' },
        { id: 'sepia', name: 'Sepia', icon: 'fa-book' },
        { id: 'forest', name: 'Forest', icon: 'fa-tree' },
        { id: 'ocean', name: 'Ocean', icon: 'fa-water' },
        { id: 'peach', name: 'Peach', icon: 'fa-heart' },
        { id: 'lavender', name: 'Lavender', icon: 'fa-spa' }
    ];

    // 检测是否是 Kindle 设备
    function isKindleDevice() {
        // 优先从 window 缓存读取
        if (window.epubBrowserCache && window.epubBrowserCache.kindle_mode !== undefined) {
            return window.epubBrowserCache.kindle_mode === 'true';
        }
        // 检测设备
        var ua = navigator.userAgent.toLowerCase();
        // 使用字符串包含检测，更兼容旧浏览器
        var isKindle = ua.indexOf('kindle') !== -1 || ua.indexOf('silk') !== -1;
        // 缓存结果到 window
        if (!window.epubBrowserCache) {
            window.epubBrowserCache = {};
        }
        window.epubBrowserCache.kindle_mode = isKindle ? 'true' : 'false';
        return isKindle;
    }

    // 检查本地存储中的主题设置
    function getCurrentTheme() {
        var isKindle = isKindleDevice();
        if (!isKindle) {
            // 优先从 window 读取
            if (window.epubBrowserCache && window.epubBrowserCache.theme) {
                return window.epubBrowserCache.theme;
            }
            try {
                var theme = localStorage.getItem('theme');
                if (theme) {
                    // 缓存到 window
                    if (!window.epubBrowserCache) {
                        window.epubBrowserCache = {};
                    }
                    window.epubBrowserCache.theme = theme;
                    return theme;
                }
                return 'light';
            } catch (e) {
                return 'light';
            }
        } else {
            return getCookie('theme') || 'light';
        }
    }

    // 保存主题设置
    function saveTheme(theme) {
        var isKindle = isKindleDevice();
        if (!isKindle) {
            try {
                localStorage.setItem('theme', theme);
            } catch (e) {
                // 忽略错误
            }
        } else {
            setCookie('theme', theme);
        }
        // 缓存到 window
        if (!window.epubBrowserCache) {
            window.epubBrowserCache = {};
        }
        window.epubBrowserCache.theme = theme;
    }

    // 应用主题
    function applyTheme(theme) {
        // 移除所有主题类
        document.documentElement.classList.remove('light-mode', 'dark-mode', 'sepia-mode', 'forest-mode', 'ocean-mode', 'peach-mode', 'lavender-mode');
        // 添加当前主题类
        document.documentElement.classList.add(theme + '-mode');
        
        // 更新theme-toggle图标
        var themeToggle = document.getElementById('themeToggle');
        var mobileThemeBtn = document.getElementById('mobileThemeBtn');
        var currentTheme = null;
        for (var i = 0; i < themes.length; i++) {
            if (themes[i].id === theme) {
                currentTheme = themes[i];
                break;
            }
        }
        
        if (themeToggle && currentTheme) {
            var icon = themeToggle.querySelector('i');
            if (icon) {
                icon.className = 'fas ' + currentTheme.icon;
            }
        }
        
        if (mobileThemeBtn && currentTheme) {
            var icon = mobileThemeBtn.querySelector('i');
            if (icon) {
                icon.className = 'fas ' + currentTheme.icon;
            }
        }
        
        // 保存主题设置
        saveTheme(theme);
        
        // 切换代码主题（如果存在）
        if (typeof switchCodeTheme === 'function') {
            switchCodeTheme(theme === 'dark');
        }
    }

    // 创建主题选择菜单
    function createThemeMenu() {
        var menu = document.createElement('div');
        menu.className = 'theme-menu';
        menu.style.display = 'none';
        menu.style.position = 'fixed';
        menu.style.zIndex = '10000';
        
        for (var i = 0; i < themes.length; i++) {
            var theme = themes[i];
            var item = document.createElement('div');
            item.className = 'theme-menu-item';
            item.innerHTML = '<i class="fas ' + theme.icon + '"></i>' + theme.name;
            
            item.addEventListener('click', function(themeId) {
                return function() {
                    applyTheme(themeId);
                    menu.style.display = 'none';
                };
            }(theme.id));
            
            menu.appendChild(item);
        }
        
        return menu;
    }
    
    // 更新主题菜单位置
    function updateThemeMenuPosition(menu, toggleBtn) {
        var mobileControls = document.querySelector('.mobile-controls');
        var isMobile = mobileControls && window.getComputedStyle(mobileControls).display !== 'none';
        
        if (isMobile) {
            // 移动端：固定在右下角，类似于 settings-modal
            menu.style.bottom = '80px';
            menu.style.left = '20px';
            menu.style.top = 'auto';
        } else {
            // 桌面端：相对于按钮定位
            var rect = toggleBtn.getBoundingClientRect();
            menu.style.top = (rect.bottom + 8) + 'px';
            menu.style.right = (window.innerWidth - rect.right) + 'px';
            menu.style.bottom = 'auto';
        }
    }

    // 初始化主题
    function init() {
        var themeToggle = document.getElementById('themeToggle');
        if (!themeToggle) return;

        var mobileThemeBtn = document.getElementById('mobileThemeBtn');
        var isKindle = isKindleDevice();

        // 应用初始主题
        var currentTheme = getCurrentTheme();
        applyTheme(currentTheme);

        // 初始化主题菜单
        var themeMenu = null;
        var currentToggleBtn = null;
        
        function handleThemeToggle(e) {
            e.stopPropagation();
            
            if (isKindle) {
                // Kindle 模式下保持原有切换行为
                var currentTheme = getCurrentTheme();
                var newTheme = currentTheme === 'dark' ? 'light' : 'dark';
                applyTheme(newTheme);
            } else {
                // 非 Kindle 模式下显示主题选择菜单
                if (!themeMenu) {
                    themeMenu = createThemeMenu();
                    document.body.appendChild(themeMenu);
                }
                
                currentToggleBtn = themeToggle;
                
                if (themeMenu.style.display === 'none') {
                    updateThemeMenuPosition(themeMenu, themeToggle);
                    themeMenu.style.display = 'block';
                } else {
                    themeMenu.style.display = 'none';
                }
            }
        }

        // 绑定主题切换事件
        themeToggle.addEventListener('click', handleThemeToggle);
        if (mobileThemeBtn) {
            mobileThemeBtn.addEventListener('click', function(e) {
                e.stopPropagation();
                var isKindle = isKindleDevice();
                if (isKindle) {
                    var currentTheme = getCurrentTheme();
                    var newTheme = currentTheme === 'dark' ? 'light' : 'dark';
                    applyTheme(newTheme);
                } else {
                    if (!themeMenu) {
                        themeMenu = createThemeMenu();
                        document.body.appendChild(themeMenu);
                    }
                    
                    currentToggleBtn = mobileThemeBtn;
                    
                    if (themeMenu.style.display === 'none') {
                        updateThemeMenuPosition(themeMenu, mobileThemeBtn);
                        themeMenu.style.display = 'block';
                    } else {
                        themeMenu.style.display = 'none';
                    }
                }
            });
        }

        // 点击其他地方关闭主题菜单
        document.addEventListener('click', function(e) {
            if (themeMenu && !themeToggle.contains(e.target) && !themeMenu.contains(e.target) && (!mobileThemeBtn || !mobileThemeBtn.contains(e.target))) {
                themeMenu.style.display = 'none';
            }
        });
        
        // 窗口大小改变时更新菜单位置
        window.addEventListener('resize', function() {
            if (themeMenu && themeMenu.style.display !== 'none' && currentToggleBtn) {
                updateThemeMenuPosition(themeMenu, currentToggleBtn);
            }
        });
    }

    // 工具函数：获取 Cookie
    function getCookie(key) {
        var cookies = document.cookie.split('; ');
        for (var i = 0; i < cookies.length; i++) {
            var cookie = cookies[i];
            var parts = cookie.split('=');
            var cookieKey = parts[0];
            var cookieValue = parts.slice(1).join('=');
            if (cookieKey === key) {
                return decodeURIComponent(cookieValue);
            }
        }
        return null;
    }

    // 工具函数：设置 Cookie
    function setCookie(key, value) {
        var date = new Date();
        date.setTime(date.getTime() + 3650 * 24 * 60 * 60 * 1000);
        var expires = "expires=" + date.toUTCString();
        document.cookie = key + "=" + value + "; " + expires + "; path=/;";
    }

    // 初始化
    init();
}

// 导出函数
window.initTheme = initTheme;