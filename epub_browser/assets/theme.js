// 主题切换功能
function initTheme() {
    // 主题列表
    var themes = [
        { id: 'light', nameKey: 'theme.light', icon: 'fa-sun' },
        { id: 'dark', nameKey: 'theme.dark', icon: 'fa-moon' },
        { id: 'sepia', nameKey: 'theme.sepia', icon: 'fa-book' },
        { id: 'forest', nameKey: 'theme.forest', icon: 'fa-tree' },
        { id: 'ocean', nameKey: 'theme.ocean', icon: 'fa-water' },
        { id: 'peach', nameKey: 'theme.peach', icon: 'fa-heart' },
        { id: 'lavender', nameKey: 'theme.lavender', icon: 'fa-spa' }
    ];

    // 检查本地存储中的主题设置
    function getCurrentTheme() {
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
    }

    // 保存主题设置
    function saveTheme(theme) {
        try {
            localStorage.setItem('theme', theme);
        } catch (e) {
            // 忽略错误
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
        
        // 保存主题设置
        saveTheme(theme);
        
        // 切换代码主题（如果存在）
        if (typeof switchCodeTheme === 'function') {
            switchCodeTheme(theme === 'dark');
        }
    }

    function renderThemeMenu(menu, currentTheme, themeToggle) {
        menu.innerHTML = '';
        for (var i = 0; i < themes.length; i++) {
            var theme = themes[i];
            var item = document.createElement('button');
            item.type = 'button';
            item.className = 'theme-menu-item';
            item.setAttribute('role', 'menuitemradio');
            item.setAttribute('aria-checked', theme.id === currentTheme ? 'true' : 'false');
            item.innerHTML = '<i class="fas ' + theme.icon + '"></i>';
            item.appendChild(document.createTextNode(window.EpubBrowserI18n.t(theme.nameKey)));
            
            item.addEventListener('click', function(themeId) {
                return function() {
                    applyTheme(themeId);
                    renderThemeMenu(menu, themeId, themeToggle);
                    menu.style.display = 'none';
                    themeToggle.setAttribute('aria-expanded', 'false');
                    themeToggle.focus();
                };
            }(theme.id));
            
            menu.appendChild(item);
        }
    }

    function themeIndex(themeId) {
        for (var i = 0; i < themes.length; i++) {
            if (themes[i].id === themeId) return i;
        }
        return 0;
    }

    function focusThemeChoice(menu, index) {
        var choices = Array.prototype.slice.call(menu.children || []);
        if (!choices.length) return 0;
        var normalizedIndex = (index + choices.length) % choices.length;
        choices[normalizedIndex].focus();
        return normalizedIndex;
    }

    // 创建主题选择菜单
    function createThemeMenu() {
        var menu = document.createElement('div');
        menu.className = 'theme-menu';
        menu.setAttribute('role', 'menu');
        menu.setAttribute('aria-labelledby', 'themeToggle');
        menu.style.display = 'none';
        menu.style.position = 'fixed';
        menu.style.zIndex = '10000';
        renderThemeMenu(menu);
        
        return menu;
    }
    
    // 更新主题菜单位置
    function updateThemeMenuPosition(menu, toggleBtn) {
        // Theme selection belongs to the persistent top-right action on every
        // viewport.  Do not detach it into the reader's bottom action bar.
        var rect = toggleBtn.getBoundingClientRect();
        menu.style.top = (rect.bottom + 8) + 'px';
        menu.style.right = (window.innerWidth - rect.right) + 'px';
        menu.style.bottom = 'auto';
        menu.style.left = 'auto';
    }

    // 初始化主题
    function init() {
        var themeToggle = document.getElementById('themeToggle');
        if (!themeToggle) return;

        themeToggle.setAttribute('aria-haspopup', 'menu');
        themeToggle.setAttribute('aria-expanded', 'false');

        // 应用初始主题
        var currentTheme = getCurrentTheme();
        applyTheme(currentTheme);

        // 初始化主题菜单
        var themeMenu = null;
        var currentToggleBtn = null;
        var themeMenuFocusIndex = themeIndex(currentTheme);

        if (window.EpubBrowserI18n && window.EpubBrowserI18n.onLocaleChange) {
            window.EpubBrowserI18n.onLocaleChange(function() {
                if (themeMenu) {
                    renderThemeMenu(themeMenu, getCurrentTheme(), themeToggle);
                }
            });
        }
        
        function handleThemeToggle(e) {
            e.stopPropagation();
            
            // 显示主题选择菜单
            if (!themeMenu) {
                themeMenu = createThemeMenu();
                document.body.appendChild(themeMenu);
            }

            currentToggleBtn = themeToggle;

            if (themeMenu.style.display === 'none') {
                updateThemeMenuPosition(themeMenu, themeToggle);
                var activeTheme = getCurrentTheme();
                renderThemeMenu(themeMenu, activeTheme, themeToggle);
                themeMenu.style.display = 'block';
                themeToggle.setAttribute('aria-expanded', 'true');
                themeMenuFocusIndex = focusThemeChoice(themeMenu, themeIndex(activeTheme));
            } else {
                themeMenu.style.display = 'none';
                themeToggle.setAttribute('aria-expanded', 'false');
            }
        }

        // 绑定主题切换事件
        themeToggle.addEventListener('click', handleThemeToggle);
        // 点击其他地方关闭主题菜单
        document.addEventListener('click', function(e) {
            if (themeMenu && !themeToggle.contains(e.target) && !themeMenu.contains(e.target)) {
                themeMenu.style.display = 'none';
                themeToggle.setAttribute('aria-expanded', 'false');
            }
        }, true);

        document.addEventListener('keydown', function(e) {
            if (e.key === 'Escape' && themeMenu && themeMenu.style.display !== 'none') {
                themeMenu.style.display = 'none';
                themeToggle.setAttribute('aria-expanded', 'false');
                themeToggle.focus();
                return;
            }
            if (!themeMenu || themeMenu.style.display === 'none') return;

            if (e.key === 'ArrowDown' || e.key === 'ArrowRight') {
                e.preventDefault();
                themeMenuFocusIndex = focusThemeChoice(themeMenu, themeMenuFocusIndex + 1);
            } else if (e.key === 'ArrowUp' || e.key === 'ArrowLeft') {
                e.preventDefault();
                themeMenuFocusIndex = focusThemeChoice(themeMenu, themeMenuFocusIndex - 1);
            } else if (e.key === 'Home') {
                e.preventDefault();
                themeMenuFocusIndex = focusThemeChoice(themeMenu, 0);
            } else if (e.key === 'End') {
                e.preventDefault();
                themeMenuFocusIndex = focusThemeChoice(themeMenu, themes.length - 1);
            }
        });
        
        // 窗口大小改变时更新菜单位置
        window.addEventListener('resize', function() {
            if (themeMenu && themeMenu.style.display !== 'none' && currentToggleBtn) {
                updateThemeMenuPosition(themeMenu, currentToggleBtn);
            }
        });
    }

    // 初始化
    init();
}

// 导出函数
window.initTheme = initTheme;
