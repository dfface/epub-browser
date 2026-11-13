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

    var bootstrap = window.EpubBrowserThemeBootstrap;
    var serverMode = window.EpubBrowserMode === 'server';

    function getCurrentTheme() {
        return bootstrap.storedTheme(window);
    }

    var saving = false;
    var syncAppearance = function() {};
    var refreshTheme = applyTheme;

    function saveAppearance(changes, fromPanel) {
        if (saving) return;
        var status = document.getElementById('accountAppearanceStatus');
        function showStatus(key) {
            if (status) {
                if (key) status.setAttribute('data-i18n', key);
                else status.removeAttribute('data-i18n');
                status.textContent = key ? window.EpubBrowserI18n.t(key) : '';
            }
        }

        saving = true;
        syncAppearance();
        showStatus('');
        window.EpubBrowserAuth.fetch('/api/account/appearance', {
            method: 'PUT',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(changes)
        }).then(function(response) {
            if (!response.ok) throw new Error('Appearance update failed');
            return response.json();
        }).then(function(preferences) {
            window.EpubBrowserAppearance = preferences;
            refreshTheme();
            if (fromPanel) showStatus('settings.saved');
        }).catch(function() {
            showStatus('theme.saveFailed');
            if (!fromPanel && window.showNotification) {
                window.showNotification(window.EpubBrowserI18n.t('theme.saveFailed'), 'error');
            }
        }).then(function() {
            saving = false;
            syncAppearance();
        });
    }

    function chooseTheme(theme) {
        if (!serverMode) {
            bootstrap.saveManualTheme(window, theme);
            applyTheme();
            return;
        }

        var preferences = bootstrap.preferences(window);
        var key = 'manual';
        if (preferences.automatic) {
            var scheme = bootstrap.deviceScheme(window);
            key = scheme && scheme.matches ? 'night' : 'day';
        }
        var changes = {};
        changes[key] = theme;
        saveAppearance(changes, false);
    }

    function applyTheme() {
        var theme = bootstrap.apply(window);

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
        
        var lightCode = document.getElementById('code-light');
        var darkCode = document.getElementById('code-dark');
        if (lightCode && darkCode) {
            lightCode.disabled = theme === 'dark';
            darkCode.disabled = theme !== 'dark';
        }
        return theme;
    }

    function bindAppearance() {
        var day = document.getElementById('accountDayTheme');
        var night = document.getElementById('accountNightTheme');
        var automatic = document.getElementById('accountAutoTheme');
        if (!automatic) return;

        [day, night].forEach(function(select) {
            themes.forEach(function(theme) {
                var option = document.createElement('option');
                option.value = theme.id;
                option.setAttribute('data-i18n', theme.nameKey);
                option.textContent = window.EpubBrowserI18n.t(theme.nameKey);
                select.appendChild(option);
            });
        });

        syncAppearance = function() {
            var preferences = bootstrap.preferences(window);
            day.disabled = night.disabled = automatic.disabled = saving;
            day.value = preferences.day;
            night.value = preferences.night;
            automatic.checked = preferences.automatic;
        };

        day.addEventListener('change', function() { saveAppearance({day: day.value}, true); });
        night.addEventListener('change', function() { saveAppearance({night: night.value}, true); });
        automatic.addEventListener('change', function() {
            saveAppearance({automatic: automatic.checked}, true);
        });
        syncAppearance();
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
                    chooseTheme(themeId);
                    menu.style.display = 'none';
                    themeToggle.setAttribute('aria-expanded', 'false');
                    themeToggle.focus({ preventScroll: true });
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
        var currentTheme = applyTheme();

        // 初始化主题菜单
        var themeMenu = null;
        var currentToggleBtn = null;
        var themeMenuFocusIndex = themeIndex(currentTheme);

        refreshTheme = function() {
            var activeTheme = applyTheme();
            if (themeMenu) {
                // Keep the focused menu item in place during a device change.
                themes.forEach(function(theme, index) {
                    themeMenu.children[index].setAttribute('aria-checked', String(theme.id === activeTheme));
                });
            }
        };

        if (serverMode) {
            bindAppearance();
            var scheme = bootstrap.deviceScheme(window);
            if (scheme && scheme.addEventListener) scheme.addEventListener('change', refreshTheme);
            else if (scheme && scheme.addListener) scheme.addListener(refreshTheme);
        }

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
                themeToggle.focus({ preventScroll: true });
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
