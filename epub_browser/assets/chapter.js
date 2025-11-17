function isFontAvailable(fontName) {
    // 方法1：使用 canvas 测量文本宽度（推荐）
    const canvas = document.createElement('canvas');
    const context = canvas.getContext('2d');
    
    // 基准字体宽度
    const baseText = 'abcdefghijklmnopqrstuvwxyz0123456789';
    context.font = '72px sans-serif';
    const baselineWidth = context.measureText(baseText).width;
    
    // 测试字体宽度
    context.font = `72px ${fontName}, sans-serif`;
    const testWidth = context.measureText(baseText).width;
    
    return testWidth !== baselineWidth;
}

const commonFonts = [
    'Arial', 'Helvetica', 'Times New Roman', 'Helvetica',
    'Courier New','Trebuchet MS', 'Arial Black','Segoe UI', 'Microsoft YaHei', "微软雅黑", 'SimSun',
    'SimHei',"Heiti", "Song Ti", "Kai Ti", 'KaiTi', 'FangSong', "Fang Song", "宋体", "仿宋", "黑体",
    'STHeiti', 'STKaiti', 'STSong', 'STFangsong', 'PingFang SC', 'Heiti SC', 
    'Noto Sans SC', 'WenQuanYi Micro Hei', 'MiSans', 'Alimama ShuHeiTi',
    'LXGW WenKai', 'Amazon Ember',
];

// 获取支持的字体列表
function getAvailableFonts() {
    return commonFonts.filter(font => isFontAvailable(font));
}

function updateFontFamily(fontFamily, fontFamilyInput) {
    let fontFamilySelect = document.getElementById('fontFamilySelect');
    let customFontInput = document.getElementById('customFontInput');
    let customFontFamily = document.getElementById('customFontFamily');
    fontFamilySelect.value = fontFamily;
    if (fontFamily == "custom") {
        document.body.style.fontFamily = fontFamilyInput;
        customFontInput.style.display = 'flex';
        customFontFamily.value = fontFamilyInput;
    } else {
        document.body.style.fontFamily = fontFamily;
        customFontInput.style.display = 'none';
    }
    // 保存选项
    if (fontFamily == "custom") {
        if (!isKindleMode()) {
            localStorage.setItem('font_family_input', fontFamilyInput);
            localStorage.setItem('font_family', "custom");
        } else {
            setCookie('font_family_input', fontFamilyInput);
            setCookie('font_family', "custom");
        }
    } else {
        if (!isKindleMode()) {
            localStorage.setItem('font_family', fontFamily);
        } else {
            setCookie('font_family', fontFamily);
        }
    }
}

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

// 获取元素高度（包括外边距）
function getElementHeight(element) {
    // 创建临时元素测量高度
    const tempElement = element.cloneNode(true);
    tempElement.style.visibility = 'hidden';
    tempElement.style.position = 'absolute';
    content.appendChild(tempElement);
    
    const height = tempElement.getBoundingClientRect().height;
    const styles = window.getComputedStyle(element);
    const marginTop = parseFloat(styles.marginTop) || 0;
    const marginBottom = parseFloat(styles.marginBottom) || 0;
    
    content.removeChild(tempElement);
    
    return height + marginTop + marginBottom;
}

function isKindleMode() {
    let kindleMode = getCookie("kindle-mode") || "false";
    return kindleMode == "true";
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


function initScript() {
    const path = window.location.pathname;  // 获取当前URL路径
    let pathParts = path.split('/');
    pathParts = pathParts.filter(item => item !== "");
    const book_hash = pathParts[pathParts.indexOf('book') + 1];
    let chapter_index = pathParts[pathParts.indexOf('book') + 2];
    chapter_index = chapter_index.replace("chapter_","");
    chapter_index = chapter_index.replace(".html", "");

    // 翻页功能
    const togglePaginationBtn = document.getElementById('togglePagination');
    const mobileTogglePaginationBtn  = document.getElementById('mobileTogglePagination');
    const navigationHomeBtn = document.getElementById('navigationHomeBtn');
    const paginationInfo = document.getElementById('paginationInfo');
    const currentPageEl = document.getElementById('currentPage');
    const totalPagesEl = document.getElementById('totalPages');
    const prevPageBtn = document.getElementById('prevPage');
    const nextPageBtn = document.getElementById('nextPage');
    const contentContainer = document.querySelector('.content-container');
    const content = document.getElementById('content');
    const pageJumpInput = document.getElementById('pageJumpInput');
    const goToPageBtn = document.getElementById('goToPage');
    const progressFill = document.getElementById('progressBar');
    const pageHeightSetBtn = document.querySelector("#setPageHeight");
    const pageHeightInput = document.querySelector("#pageHeightInput");

    // 生成存储键名
    function getStorageKey(mode) {
        // 书籍ID和章节ID
        const bookId = book_hash;
        const chapterId = chapter_index;
        return `${mode}_${bookId}_${chapterId}`;
    }
    
    // 翻页状态变量
    let isPaginationMode = false;
    let currentPage = 0;
    let totalPages = 0;
    let pages = [];

    let fontSize = "small";
    let fontFamily = "system-ui, -apple-system, sans-serif";
    let fontFamilyInput = null;
    const supportedFonts = getAvailableFonts();
    supportedFonts.forEach(item => {
        let newOption = document.createElement('option');
        newOption.value = item;
        newOption.textContent = item;
        let fontFamilySelect = document.getElementById('fontFamilySelect');
        fontFamilySelect.appendChild(newOption);
    })

    const storageKeySortableContainer = 'chapter-container-sortable-order';

    // 检查本地存储中的主题设置
    if (!isKindleMode()) {
        let currentPaginationMode = localStorage.getItem('turning') || "false";
        isPaginationMode = currentPaginationMode == "true"
        fontSize = localStorage.getItem('font_size') || "small";
        fontFamily = localStorage.getItem('font_family') || "system-ui, -apple-system, sans-serif";
        fontFamilyInput = localStorage.getItem('font_family_input');
        restoreOrder(storageKeySortableContainer, 'container');
    } else {
        let currentPaginationMode =  getCookie('turning') || "false";
        isPaginationMode = currentPaginationMode == "true";
        fontSize = getCookie('font_size') || "small";
        fontFamily = getCookie('font_family') || "system-ui, -apple-system, sans-serif";
        fontFamilyInput = getCookie('font_family_input');
    }
    updateFontSize(fontSize);
    updateFontFamily(fontFamily, fontFamilyInput);

    // 添加键盘事件监听
    document.addEventListener('keydown', handleKeyDown);

    var el = document.querySelector('.container');
    if (!isKindleMode()) {
        var sortable = Sortable.create(el, {
        delay: 10, // 延迟100ms后才开始拖动，给用户选择文字的时间
        delayOnTouchOnly: false, // 在触摸设备上也应用延迟
        filter: '.content, #pageJumpInput, .page-height-adjustment', // 允许直接选择.content中的文字
        preventOnFilter: false, // 过滤时不阻止默认行为
        onStart: function(evt) {
            // 拖拽开始时检查是否有文字被选中
            const selection = window.getSelection();
            if (selection.toString().length > 0) {
                // 如果有文字被选中，取消拖拽
                evt.oldIndex; // 访问一下属性，确保事件被处理
                return false;
            }
        },
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
    // 添加双击选择文字的功能
    document.querySelectorAll('.content').forEach(item => {
        item.addEventListener('dblclick', function(e) {
            // 阻止双击触发拖拽
            e.stopPropagation();
        });
    });

    if (isKindleMode() || isPaginationMode) {
        document.querySelector(".custom-css-panel").style.display = "none";

        // 获取目标元素
        let mobileControls = document.querySelector('.mobile-controls');
        let bottomNav = document.querySelector('.navigation');
        bottomNav.style.marginBottom = `${getElementHeight(mobileControls)}px`;
    }

    if (isKindleMode()) {
        document.body.classList.add("kindle-mode");
    }

    if (isPaginationMode) {
        // 一开始就是翻页
        enablePaginationMode();
        // 禁止翻页模式 点击页面链接
        document.querySelectorAll('.content a').forEach(item => {
            item.removeAttribute('href');
        });
        togglePaginationBtn.innerHTML = '<i class="fas fa-scroll"></i><span class="control-name">Scrolling</span>';
        mobileTogglePaginationBtn.innerHTML = '<i class="fas fa-scroll"></i><span class="control-name">Scrolling</span>';
        // 隐藏 tocFloatingBtn
        let tocToggleBtn = document.getElementById('tocToggle');
        if (tocToggleBtn) {
            tocToggleBtn.style.display = 'none';
        }
        // 隐藏 mobileTocBtn
        let mobileTocBtn = document.getElementById('mobileTocBtn');
        if (mobileTocBtn) {
            mobileTocBtn.style.display = 'none';
        }
    } else {
        loadReadingProgress();  // 刚进去是 scroll，也需要恢复下进度
    }
    
    function savePaginationModeAndReload() {
        isPaginationMode = !isPaginationMode;
        
        if (isPaginationMode) {
            if (!isKindleMode()) {
                localStorage.setItem('turning', 'true');
            } else {
                setCookie('turning', 'true');
            }
        } else {
            if (!isKindleMode()) {
                localStorage.removeItem('turning');
            } else {
                deleteCookie('turning');
            }
        }

        location.reload();
    }
    
    // 切换翻页模式
    togglePaginationBtn.addEventListener('click', savePaginationModeAndReload);
    mobileTogglePaginationBtn.addEventListener('click', savePaginationModeAndReload);
    
    // 启用翻页模式
    function enablePaginationMode() {
        if (!isKindleMode()) {
            localStorage.setItem('turning', 'true');
        } else {
            setCookie('turning', 'true');
        }
        
        // 添加翻页模式类
        document.body.classList.add('pagination-mode');
        contentContainer.classList.add('pagination-mode');  

        // 获取目标元素
        let mobileControls = document.querySelector('.mobile-controls');
        let bottomNav = document.querySelector('.navigation');
        bottomNav.style.marginBottom = `${getElementHeight(mobileControls)}px`;
        
        // 关闭页面的不必要元素
        toggleHideUnnecessary(true);
        
        // 显示翻页信息
        paginationInfo.style.display = 'flex';
        navigationHomeBtn.style.display = 'none';
        
        // 分割内容为页面
        createPages();

        // 尝试加载保存的阅读进度
        loadReadingProgress();
        
        // 更新导航按钮状态
        updateNavButtons();

        if (isKindleMode()) {
            showNotification(`Page turning mode enabled`, 'info');
        }
    }

    // 关闭页面的不必要元素
    function toggleHideUnnecessary(hide) {
        let customCssPanel = document.querySelector(".custom-css-panel");
        let breadcrumb = document.querySelector(".breadcrumb");
        let footer = document.querySelector("footer");
        if (hide) {
            customCssPanel.style.display = 'none';
            breadcrumb.style.display = 'none';
            footer.style.display = 'none';
        } else {
            customCssPanel.style.display = 'inherit';
            breadcrumb.style.display = 'inherit';
            footer.style.display = 'inherit';
        }
    }
    
    // 禁用翻页模式
    function disablePaginationMode() {
        if (!isKindleMode()) {
            localStorage.removeItem('turning');
        } else {
            deleteCookie('turning');
        }
        // 恢复原始内容
        restoreOriginalContent();
        
    }

    function preprocessContent(content) {
        if (content.children && Array.from(content.children).length == 1) {
            if (content.children[0].tagName == "DIV") {
                return preprocessContent(content.children[0]);
            }
        }
        return content.innerHTML;
    }
    
    // 创建页面
    function createPages() {
        // 保存原始内容
        // 预处理
        const originalContent = preprocessContent(content);
        let newContent = document.createElement("article");
        newContent.innerHTML = originalContent;
        
        // 获取容器高度
        const bottomNav = document.querySelector('.navigation');
        const bottomNavHeight = getElementHeight(bottomNav);
        const viewportHeight = window.innerHeight;

        let contentHeight = viewportHeight - bottomNavHeight; // 减去边距
        contentContainer.style.height = contentHeight;
        contentHeight -= 60; // 减去大的内边距
        if (fontSize == "large") {
            contentHeight -= 280;
        } else if (fontSize == "small") {
            contentHeight += 40;
        }
        if (!isKindleMode()) {
            let customContentHeight = localStorage.getItem("page_height");
            if (customContentHeight) {
                contentHeight = parseFloat(customContentHeight);
            }
        } else {
            let customContentHeight = getCookie("page_height");
            if (customContentHeight) {
                contentHeight = parseFloat(customContentHeight);
            }
        }

        pageHeightInput.value = contentHeight
        
        // 分割内容为页面
        let currentPageContent = '';
        let currentHeight = 0;
        const elements = Array.from(newContent.children || []);
        
        // 如果没有子元素，直接使用文本内容
        if (elements.length === 0) {
            pages = [originalContent];
            totalPages = 1;
        } else {
            // 遍历所有子元素
            elements.forEach(element => {
                let elementHeight = getElementHeight(element);
                // 如果当前页面高度加上新元素高度超过容器高度，创建新页面
                if (currentHeight + elementHeight > contentHeight && currentHeight > 0) {
                    pages.push(currentPageContent);
                    currentPageContent = '';
                    currentHeight = 0;
                }        
                // 添加元素到当前页面
                currentPageContent += element.outerHTML;
                currentHeight += elementHeight;
            });
            
            // 添加最后一页
            if (currentPageContent) {
                pages.push(currentPageContent);
            }
            
            totalPages = pages.length;
        }

        pageJumpInput.setAttribute('max', totalPages);

        // 清空内容容器
        content.innerHTML = '';
        
        // 创建页面元素
        pages.forEach((pageContent, index) => {
            const pageElement = document.createElement('div');
            pageElement.className = 'pagination-page';
            pageElement.innerHTML = pageContent;
            content.appendChild(pageElement);
        });
    }
    
    // 显示指定页面
    function showPage(pageIndex) {
        // 隐藏所有页面
        document.querySelectorAll('.pagination-page').forEach(page => {
            page.classList.remove('active', 'prev');
        });
        
        // 显示当前页面
        const currentPageElement = document.querySelectorAll('.pagination-page')[pageIndex];
        if (currentPageElement) {
            currentPageElement.classList.add('active');
        }
        
        // 更新当前页面索引
        currentPage = pageIndex;
        currentPageEl.textContent = currentPage + 1;
        totalPagesEl.textContent = totalPages;
        
        // 更新跳转输入框
        pageJumpInput.value = currentPage + 1;
        
        // 更新进度指示器
        updateProgressIndicator();

        // 更新导航按钮状态
        updateNavButtons();

        // 保存阅读进度
        saveReadingProgress();

        // 更新目录锚点
        updateTocHighlight();
    }
    
    // 更新导航按钮状态
    function updateNavButtons() {
        prevPageBtn.disabled = currentPage === 0;
        nextPageBtn.disabled = currentPage === totalPages - 1;
    }

    // 更新进度指示器
    function updateProgressIndicator() {
        const progress = ((currentPage + 1) / totalPages) * 100;
        progressFill.style.width = `${progress}%`;
    }
    
    // 恢复原始内容
    function restoreOriginalContent() {
        // 这里需要重新加载原始内容
        // 在实际应用中，您可能需要保存原始内容或重新获取
        // 这里我们简单重新加载页面
        if (isKindleMode() || confirm('Are you sure you want to exit the page-turning mode?')) {
            location.reload();
        } else {
            // 如果用户取消，重新启用翻页模式
            // 什么也不干
        }
    }

    // 保存阅读进度
    function saveReadingProgress() {
        if (isPaginationMode && !isKindleMode()) {
            // 翻页模式
            let storageKey = getStorageKey("turning");
            localStorage.setItem(storageKey, currentPage.toString());
        }
    }

    // 加载阅读进度
    function loadReadingProgress() {
        if (isKindleMode()) {
            if (isPaginationMode) {
                showPage(0);
            }
            return
        }

        if (isPaginationMode) {
            // 翻页模式
            let storageKey = getStorageKey("turning");
            let savedPage = localStorage.getItem(storageKey);
        
            if (savedPage && savedPage > 0) {
                const pageIndex = parseInt(savedPage, 10);
                if (pageIndex >= 0 && pageIndex < totalPages) {
                    showPage(pageIndex);
                    
                    // 显示加载进度提示
                    showNotification(`Reading progress loaded: Page ${pageIndex + 1}`, 'info');
                }
            } else {
                showPage(0);
            }
        } else {
            // 滚动模式
            let storageKey = getStorageKey("scroll");
            let savedPos = localStorage.getItem(storageKey);
            let windowHeight = window.innerHeight;
            if (savedPos && savedPos > 0) {
                    window.scrollTo({
                    top: parseInt(savedPos),
                    behavior: 'smooth'
                });
                // 显示加载进度提示
                showNotification(`Reading progress loaded: Scroll position ${Math.round( savedPos / (document.documentElement.scrollHeight - windowHeight) * 100 )}%`, 'info');
            }
        }
    }

    // 跳转到指定页面
    goToPageBtn.addEventListener('click', function() {
        const pageNum = parseInt(pageJumpInput.value, 10);
        if (pageNum >= 1 && pageNum <= totalPages) {
            showPage(pageNum - 1);
        } else {
            showNotification(`Please enter a valid page number (1-${totalPages})`, 'warning');
            pageJumpInput.value = currentPage + 1;
        }
    });
    
    // 跳转输入框回车事件
    pageJumpInput.addEventListener('keypress', function(e) {
        if (e.key === 'Enter') {
            goToPageBtn.click();
        }
    });

    pageHeightInput.addEventListener('keypress', function(e) {
        if (e.key === 'Enter') {
            pageHeightSetBtn.click();
        }
    });

    // 设置页面高度
    pageHeightSetBtn.addEventListener('click', function(e) {
        const pageHeight = parseFloat(pageHeightInput.value);
        if (pageHeight > 0) {
            if (isKindleMode()) {
                setCookie('page_height', pageHeight);
            } else {
                localStorage.setItem('page_height', pageHeight);
            }
            location.reload();
        } else {
            showNotification(`Please enter a valid page height`, 'warning');
        }
    });
    // 键盘事件处理
    function handleKeyDown(e) {
        if (isKindleMode()) return;
        if (isPaginationMode) {
            // 翻页模式
            switch(e.key) {
            case 'ArrowLeft':
                if (currentPage > 0) {
                    showPage(currentPage - 1);
                } else {
                    let prev_href = document.querySelector(".prev-chapter").href;
                    if (prev_href == location.href) {
                        showNotification("It's already the first chapter!", 'warning')
                        break;
                    }
                    location.href = prev_href;
                }
                break;
            case ' ':
            case 'Space':
            case 'ArrowRight':
                if (currentPage < totalPages - 1) {
                    showPage(currentPage + 1);
                } else {
                    let next_href = document.querySelector(".next-chapter").href;
                    if (next_href == location.href) {
                        showNotification("It's already the last chapter!", 'warning')
                        break;
                    }
                    location.href = next_href;
                }
                break;
            }
        } else {
            // 滚动模式
            switch(e.key) {
            case 'ArrowLeft':
                let prev_href = document.querySelector(".prev-chapter").href;
                if (prev_href == location.href) {
                    showNotification("It's already the first chapter!", 'warning')
                    break;
                }
                location.href = prev_href;
                break;
            case ' ':
            case 'ArrowDown':
            case 'Space':
                // 获取页面总高度
                const scrollHeight = document.documentElement.scrollHeight;
                // 获取可视区域高度
                const clientHeight = document.documentElement.clientHeight;
                // 获取当前滚动位置
                const scrollTop = document.documentElement.scrollTop || document.body.scrollTop;
                // 判断是否滚动到底部
                if (scrollTop + clientHeight < scrollHeight) {
                    break;
                }
            case 'ArrowRight':
                let next_href = document.querySelector(".next-chapter").href;
                if (next_href == location.href) {
                    showNotification("It's already the last chapter!", 'warning')
                    break;
                }
                location.href = next_href;
                break;
            }
        }
        
    }

    // 上一页按钮事件
    prevPageBtn.addEventListener('click', function() {
        if (currentPage > 0) {
            showPage(currentPage - 1);
        } else {
            let prev_href = document.querySelector(".prev-chapter").href;
            if (prev_href == location.href) {
                showNotification("It's already the first chapter!", 'warning')
            } else {
                location.href = prev_href;
            }
        }
    });
    
    // 下一页按钮事件
    nextPageBtn.addEventListener('click', function() {
        if (currentPage < totalPages - 1) {
            showPage(currentPage + 1);
        } else {
            let next_href = document.querySelector(".next-chapter").href;
            if (next_href == location.href) {
                showNotification("It's already the last chapter!", 'warning')
            } else {
                location.href = next_href;
            }
        }
    });

    // 监听点击事件
    if (isKindleMode()) {
        content.addEventListener('click', function(e) {
            const screenWidth = window.innerWidth;
            const targetArea = screenWidth * 0.2;
            
            // 左侧40px内点击
            if (e.clientX < targetArea) {
                prevPageBtn.click();
            }
            // 右侧40px内点击
            else if (e.clientX > screenWidth - targetArea) {
                nextPageBtn.click();
            }
        });
    }

    // 自定义 css
    customCssFunc();

    function customCssFunc() {
        if (isKindleMode()) {
            return;
        }
        // 自定义CSS功能
        const cssPanelToggle = document.getElementById('cssPanelToggle');
        const cssPanelContent = document.getElementById('cssPanelContent');
        const customCssInput = document.getElementById('customCssInput');
        const saveCssBtn = document.getElementById('saveCssBtn');
        const saveAsDefaultBtn = document.getElementById('saveAsDefaultBtn');
        const resetCssBtn = document.getElementById('resetCssBtn');
        const previewCssBtn = document.getElementById('previewCssBtn');
        const loadDefaultBtn = document.getElementById('loadDefaultBtn');
        const storageKey = `custom_css_${book_hash}`;
        const defaultStorageKey = `custom_css_default`;
        // 切换面板展开/收起
        cssPanelToggle.addEventListener('click', function() {
            cssPanelContent.classList.toggle('expanded');
            const icon = cssPanelToggle.querySelector('i');
            if (cssPanelContent.classList.contains('expanded')) {
                icon.classList.remove('fa-chevron-down');
                icon.classList.add('fa-chevron-up');
            } else {
                icon.classList.remove('fa-chevron-up');
                icon.classList.add('fa-chevron-down');
            }
        });
        // 加载保存的自定义CSS
        function loadCustomCss() {
            // 首先尝试加载特定书籍的CSS
            const savedCss = localStorage.getItem(storageKey);
            if (savedCss) {
                customCssInput.value = savedCss;
                applyCustomCss(savedCss);
                return;
            }
            
            // 如果没有特定书籍的CSS，尝试加载默认CSS
            const defaultCss = localStorage.getItem(defaultStorageKey);
            if (defaultCss) {
                customCssInput.value = defaultCss;
                applyCustomCss(defaultCss);
            }
        }
        // 应用自定义CSS到页面
        function applyCustomCss(css) {
            // 移除之前添加的自定义样式
            const existingStyle = document.getElementById('custom-user-css');
            if (existingStyle) {
                existingStyle.remove();
            }
            
            if (css.trim()) {
                // 创建新的style元素并添加到head
                const styleElement = document.createElement('style');
                styleElement.id = 'custom-user-css';
                styleElement.textContent = css;
                document.head.appendChild(styleElement);
            }
        }
        // 保存自定义CSS
        saveCssBtn.addEventListener('click', function() {
            const css = customCssInput.value;
            localStorage.setItem(storageKey, css);
            applyCustomCss(css);
            
            // 显示保存成功提示
            showNotification('Saved for current book!', 'success');
        });
        // 保存为默认样式
        saveAsDefaultBtn.addEventListener('click', function() {
            const css = customCssInput.value;
            if (confirm('Are you sure to save as the default style? This will affect all books that do not have a custom style.')) {
                localStorage.setItem(defaultStorageKey, css);
                showNotification('Saved as a default style!', 'success');
            }
        });
        // 加载默认样式
        loadDefaultBtn.addEventListener('click', function() {
            const defaultCss = localStorage.getItem(defaultStorageKey);
            if (!defaultCss) {
                showNotification('Default style not found!', 'warning');
                return;
            }
            
            if (confirm('Are you sure to load the default style? This will replace the current CSS code.')) {
                customCssInput.value = defaultCss;
                applyCustomCss(defaultCss);
                showNotification('The default style has been loaded!', 'success');
            }
        });
        // 重置自定义CSS
        resetCssBtn.addEventListener('click', function() {
            if (confirm('Are you sure to reset? This will clear the custom CSS code for this book.')) {
                customCssInput.value = '';
                localStorage.removeItem(storageKey);
                applyCustomCss('');
                
                // 重置后尝试加载默认样式
                const defaultCss = localStorage.getItem(defaultStorageKey);
                if (defaultCss) {
                    customCssInput.value = defaultCss;
                    applyCustomCss(defaultCss);
                }
                
                showNotification('The custom style for this book has been reset!', 'info');
            }
        });
        // 预览自定义CSS
        previewCssBtn.addEventListener('click', function() {
            const css = customCssInput.value;
            applyCustomCss(css);
            showNotification('Applied!', 'info');
        });

        // 初始化 - 加载保存的CSS
        loadCustomCss();
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
    
    
    // iframe 处理
    let iframe = document.getElementById('bookHomeIframe');
    iframe.addEventListener('load', function() {
        loadBookHomeToc();
        iframeAddEvent();
    });
    function loadBookHomeToc() {
        try {
            const iframeDoc = iframe.contentDocument || iframe.contentWindow.document;
            // 使用 iframeDoc 进行操作
            let bookHomeToc = iframeDoc.querySelector('.chapter-list');
            let iframeBody = iframeDoc.querySelector('body');
            let iframeFooter = iframeDoc.querySelector('footer');
            let iframeContainer = iframeDoc.querySelector('.container');
            let topControls = iframeDoc.querySelector('.top-controls');
            let readingControls = iframeDoc.querySelector('.reading-controls');
            let breadcrumb = iframeDoc.querySelector('.breadcrumb');
            let bookInfoCard = iframeDoc.querySelector('.book-info-card');
            let tocHeader = iframeDoc.querySelector('.toc-header'); 
            let tocContainer = iframeDoc.querySelector('.toc-container');

            topControls.style.display = 'none';
            breadcrumb.style.display = 'none';
            bookInfoCard.style.display = 'none';
            iframeFooter.style.display = 'none';
            tocHeader.style.display = 'none';
            readingControls.style.display = 'none';
            bookHomeToc.style.width = "100%";
            bookHomeToc.style.maxHeight = "100%";
            iframeBody.style.padding = 0;
            iframeContainer.style.padding = 0;
            iframeContainer.style.margin = 0; 
            tocContainer.style.margin = 0;
        } catch (e) {
            console.log('Can not reach iframe:', e.message);
        }
    }

    function iframeAddEvent() {
        try {
            const iframeDoc = iframe.contentDocument || iframe.contentWindow.document;
            // 使用 iframeDoc 进行操作
            let allLinks = iframeDoc.querySelectorAll('a');
            allLinks.forEach( link => {
                link.addEventListener('click', function(event) {
                // 阻止默认行为（在iframe中打开） 
                event.preventDefault(); 
                // 获取链接URL 
                var href = this.getAttribute('href'); 
                // 在父页面中打开链接 
                window.location.href = href; 
                return false; 
                });
            });

            // 书籍目录锚点滚动
            mobileBookHomeBtn.addEventListener('click', function(){
                scrollBookHomeToc();
            });
            bookHomeToggle.addEventListener('click', function(){
                scrollBookHomeToc();
            });

            function scrollBookHomeToc() {
                if (anchor != '') { // 后面有 var anchor 的声明和取值
                    targetEl =  iframeDoc.getElementById(anchor.substr(1));
                    if (targetEl) {
                        var rect = targetEl.getBoundingClientRect();
                        // 滚动到元素位置
                        iframe.contentWindow.scrollTo({
                            top: rect.top + iframe.contentWindow.pageYOffset,
                        });
                    }
                }
            }
        } catch (e) {
            console.log('Can not reach iframe:', e.message);
        }
    }
    
    // 代码高亮
    if (!isKindleMode()) {
        // highlight 之前的处理 pre 里面有无 code
        let allPres = document.querySelectorAll("pre");
        allPres.forEach(pre => {
            if (pre.children.length == 0) {
                // 需要用 code 包裹
                oldValue = pre.innerHTML;
                code = document.createElement('code');
                code.innerHTML = oldValue;
                pre.replaceChildren(code);
            }
        })
        // 高亮
        hljs.highlightAll();
    }
    
    function switchCodeTheme(isDark) {
        const lightTheme = document.querySelector('link[href*="highlight.js"][id*="light"]');
        const darkTheme = document.querySelector('link[href*="highlight.js"][id*="dark"]');
        
        if (lightTheme && darkTheme) {
            if (isDark) {
            lightTheme.disabled = true;
            darkTheme.disabled = false;
            } else {
            lightTheme.disabled = false;
            darkTheme.disabled = true;
            }
        }
    }
    

    // 包裹所有表格
    function wrapAllElements(name, wrapperElementName) {
        wrapperName = `${name}-wrapper`
        // 获取页面中所有元素
        const elements = document.querySelectorAll(name);
        let wrappedCount = 0;
        
        // 遍历每个表格
        elements.forEach((el, index) => {
            // 如果表格已经被包裹，跳过
            if (el.parentElement && el.parentElement.classList.contains(wrapperName)) {
                return;
            }
            
            // 创建包裹div
            const wrapper = document.createElement(wrapperElementName);
            wrapper.className = wrapperName;
            
            // 将表格插入到包裹div中
            el.parentNode.insertBefore(wrapper, el);
            wrapper.appendChild(el);
            
            wrappedCount++;
        });
        
        return wrappedCount;
    }
    wrapAllElements('table', 'div');
    wrapAllElements('img', 'div');

    // 书籍目录锚点更新
    const lastPart = pathParts[pathParts.length - 1];
    var anchor = '';
    if (lastPart.startsWith('chapter_') && lastPart.endsWith('.html')) {
        anchor = "#" + lastPart.replace('.html', '');
    }
    if (anchor !== '') {
        let bookHomes = document.querySelectorAll('.a-book-home');
        bookHomes.forEach(item => {
            item.href += anchor;
        });
        if (!isKindleMode()) {
            localStorage.setItem(book_hash, anchor);
        } else {
            setCookie(book_hash, anchor);
        }   
        
        let bookHomeIframe = document.querySelector('#bookHomeIframe');
        bookHomeIframe.src += anchor;
    }

    // 主题切换功能
    const themeToggle = document.getElementById('themeToggle');
    const mobileThemeBtn = document.getElementById('mobileThemeBtn');
    const themeIcon = themeToggle.querySelector('i');
    
    // 检查本地存储中的主题设置
    let currentTheme =  'light';
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
        mobileThemeBtn.querySelector('i').classList.remove('fa-moon');
        mobileThemeBtn.querySelector('i').classList.add('fa-sun');
        switchCodeTheme(true);
    }
    
    // 切换主题
    function toggleTheme() {
        document.body.classList.toggle('dark-mode');
        
        if (document.body.classList.contains('dark-mode')) {
            themeIcon.classList.remove('fa-moon');
            themeIcon.classList.add('fa-sun');
            mobileThemeBtn.querySelector('i').classList.remove('fa-moon');
            mobileThemeBtn.querySelector('i').classList.add('fa-sun');
            if (!isKindleMode()) {
                localStorage.setItem('theme', 'dark');
            } else {
                setCookie('theme', 'dark');
            }
            switchCodeTheme(true);
        } else {
            themeIcon.classList.remove('fa-sun');
            themeIcon.classList.add('fa-moon');
            mobileThemeBtn.querySelector('i').classList.remove('fa-sun');
            mobileThemeBtn.querySelector('i').classList.add('fa-moon');
            if (!isKindleMode()) {
                localStorage.setItem('theme', 'light');
            } else {
                setCookie('theme', 'light');
            }
            switchCodeTheme(false);
        }
    }

    // 切换主题 - 桌面端
    themeToggle.addEventListener('click', function() {
        toggleTheme();
    });

    // 切换主题 - 移动端
    mobileThemeBtn.addEventListener('click', function() {
        toggleTheme();
    });
    
    // 阅读进度功能
    const progressBar = document.getElementById('progressBar');
    
    window.addEventListener('scroll', function() {
        const windowHeight = window.innerHeight;
        const documentHeight = document.documentElement.scrollHeight - windowHeight;
        const scrollTop = window.pageYOffset || document.documentElement.scrollTop;
        const progress = (scrollTop / documentHeight) * 100;
        
        if (!document.body.classList.contains('pagination-mode')) {
            // 滚动模式进度条
            progressBar.style.width = progress + '%';
        }

        if (!isKindleMode()) {
            if (!document.body.classList.contains('pagination-mode')) {
                // 保存阅读进度
                let curStorageKey = getStorageKey("scroll");
                localStorage.setItem(curStorageKey, window.scrollY);  // 不加偏移
            }
        }
        
        // 更新目录高亮
        updateTocHighlight();
    });
    
    // 目录功能
    const tocToggle = document.getElementById('tocToggle');
    const bookHomeToggle = document.getElementById('bookHomeToggle');
    const tocFloating = document.getElementById('tocFloating');
    const bookHomeFloating = document.getElementById('bookHomeFloating');
    const mobileTocBtn = document.getElementById('mobileTocBtn');
    const mobileBookHomeBtn = document.getElementById('mobileBookHomeBtn');
    const tocClose = document.getElementById('tocClose');
    const bookHomeClose = document.getElementById('bookHomeClose');
    const tocList = document.getElementById('tocList');
    
    // 生成目录
    generateToc();
    
    // 切换目录显示 - 桌面端
    function tocFloatingScrolling() {
        // 滚动到正确的位置
        const activeLi = document.querySelector('.toc-list li.active');
        const tocList = document.getElementById('tocList');
        if (activeLi) {
            // 计算 activeLi 相对于 ul 的顶部偏移量
            const offsetTop = activeLi.offsetTop;
            tocList.scrollTop = offsetTop - 150;  // 加点偏移
        }
    }
    tocToggle.addEventListener('click', function() {
        tocFloating.classList.toggle('active');
        tocFloatingScrolling();
    });
    bookHomeToggle.addEventListener('click', function() {
        bookHomeFloating.classList.toggle('active');
        loadBookHomeToc();
    });
    
    // 切换目录显示 - 移动端
    mobileTocBtn.addEventListener('click', function() {
        tocFloating.classList.toggle('active');
        tocFloatingScrolling();
        // 移动端点击后高亮按钮
        mobileTocBtn.classList.toggle('active');
    });
    mobileBookHomeBtn.addEventListener('click', function() {
        bookHomeFloating.classList.toggle('active');
        // 移动端点击后高亮按钮
        mobileBookHomeBtn.classList.toggle('active');
        loadBookHomeToc();
    });
    
    // 关闭目录
    tocClose.addEventListener('click', function() {
        tocFloating.classList.remove('active');
        mobileTocBtn.classList.remove('active');
    });
    bookHomeClose.addEventListener('click', function() {
        bookHomeFloating.classList.remove('active');
        mobileBookHomeBtn.classList.remove('active');
    });
    
    // 生成目录函数
    function generateToc() {
        const content = document.getElementById('content');
        const headings = content.querySelectorAll('h2, h3, h4');
        
        if (headings.length === 0) {
            tocList.innerHTML = '<li class="toc-item">no title found</li>';
            return;
        }
        
        headings.forEach((heading, index) => {
            // 为每个标题添加ID
            if (!heading.id) {
                heading.id = `heading-${index}`;
            }
            
            // 创建目录项
            const listItem = document.createElement('li');
            const level = heading.tagName.charAt(1); // h2 -> 2, h3 -> 3, h4 -> 4
            listItem.className = `toc-item toc-level-${level - 1}`;
            
            const link = document.createElement('a');
            link.href = `#${heading.id}`;
            link.textContent = heading.textContent;
            
            link.addEventListener('click', function(e) {
                e.preventDefault();
                
                // 平滑滚动到标题位置
                const targetElement = document.getElementById(heading.id);
                if (targetElement) {
                    const offsetTop = targetElement.offsetTop - 100;
                    window.scrollTo({
                        top: offsetTop,
                        behavior: 'smooth'
                    });
                    
                    // 关闭目录浮窗
                    tocFloating.classList.remove('active');
                    mobileTocBtn.classList.remove('active');
                }
            });
            
            listItem.appendChild(link);
            tocList.appendChild(listItem);
        });
    }
    
    // 更新目录高亮
    function updateTocHighlight() {
        const content = document.getElementById('content');
        const headings = content.querySelectorAll('h2, h3, h4');
        const tocItems = document.querySelectorAll('.toc-item');
        
        // 找到当前可见的标题
        let currentHeadingId = '';
        const scrollPosition = window.scrollY + 150; // 偏移量
        
        for (let i = headings.length - 1; i >= 0; i--) {
            const heading = headings[i];
            if (heading.offsetTop <= scrollPosition) {
                currentHeadingId = heading.id;
                break;
            }
        }
        
        // 更新目录高亮
        tocItems.forEach(item => {
            item.classList.remove('active');
            const link = item.querySelector('a');
            if (link && link.getAttribute('href') === `#${currentHeadingId}`) {
                item.classList.add('active');
            }
        });

        // 滚动到对应位置
        tocFloatingScrolling();
    }
    
    // 滚动到顶部功能
    const scrollToTopBtn = document.getElementById('scrollToTopBtn');
    
    scrollToTopBtn.addEventListener('click', function() {
        window.scrollTo({
            top: 0,
            behavior: 'smooth'
        });
    });

    // 滚动到顶部功能 - 移动端
    const mobileTopBtn = document.getElementById('mobileTopBtn');
    
    mobileTopBtn.addEventListener('click', function() {
        window.scrollTo({
            top: 0,
            behavior: 'smooth'
        });
    });

    
    let lastScrollTop = 0; // 移动端滚动时显示/隐藏底部控件
    const scrollThreshold = 1; // 滚动阈值，避免轻微滚动触
    const mobileControls = document.querySelector('.mobile-controls');
    if(!isKindleMode() && !document.body.classList.contains('pagination-mode')) {
        window.addEventListener('scroll', function() {
            const scrollTop = window.pageYOffset || document.documentElement.scrollTop;

            if (scrollTop > lastScrollTop && scrollTop - lastScrollTop > scrollThreshold) {
                mobileControls.style.transform = 'translateY(100%)';
            } 
            // 向上滚动超过阈值时显示控件
            else if (scrollTop < lastScrollTop && lastScrollTop - scrollTop > scrollThreshold) {
                mobileControls.style.transform = 'translateY(0)';
            }

            // 更新上一次滚动位置
            lastScrollTop = scrollTop;
        });
    } else {
        mobileControls.style.transform = 'translateY(0)';
    }
    

    // 图片点击放大功能
    const contentImages = document.querySelectorAll('img');

    for (let i = 0; i < contentImages.length; i++) {
        let contentImage = contentImages[i];
        contentImage.addEventListener('click', function() {
            if (this.classList.contains('zoomed')) {
                this.classList.remove('zoomed');
                this.style.cursor = 'zoom-in';
            } else {
                this.classList.add('zoomed');
                this.style.cursor = 'zoom-out';
            }
        });
    }
    
    // 字体控制功能
    const fontControlBtn = document.getElementById('fontControlBtn');
    const mobileFontBtn = document.getElementById('mobileFontBtn');
    const fontControls = document.getElementById('fontControls');
    const fontSizeBtns = document.querySelectorAll('.font-size-btn');
    const fontFamilySelect = document.getElementById('fontFamilySelect');
    const customFontInput = document.getElementById('customFontInput');
    const applyFontSettings = document.getElementById('applyFontSettings');

    fontFamilySelect.addEventListener('change', function() {
        if (this.value === 'custom') {
            customFontInput.style.display = 'flex';
        } else {
            customFontInput.style.display = 'none';
            updateFontFamily(this.value, null);
            location.reload();
        }
    });

    applyFontSettings.addEventListener('click', function() {
        let customFontFamily = document.getElementById('customFontFamily');
        currentFont = customFontFamily.value ? `'${customFontFamily.value}', sans-serif` : 'system-ui, -apple-system, sans-serif';
        if (currentFont == "system-ui, -apple-system, sans-serif") {
            updateFontFamily(currentFont, null);
        } else {
            updateFontFamily("custom", currentFont);
        }
        location.reload();
    });

    
    fontControlBtn.addEventListener('click', function() {
        fontControls.classList.toggle('show');
    });

    mobileFontBtn.addEventListener('click', function() {
        fontControls.classList.toggle('show');
    });

    function updateFontSize(size) {
        // 移除所有按钮的active类
        const fontSizeBtns = document.querySelectorAll('.font-size-btn');
        fontSizeBtns.forEach(b => b.classList.remove('active'));
        fontSizeBtns.forEach(btn => {
            // 点亮那个字体按钮
            let btnSize = btn.getAttribute('data-size');
            if (btnSize == size) {
                btn.classList.add('active');
            }
        })

        // 移除所有字体大小类
        content.classList.remove('font-small', 'font-medium', 'font-large');
        
        // 添加选中的字体大小类
        if (size === 'small') {
            content.classList.add('font-small');
        } else if (size === 'medium') {
            content.classList.add('font-medium');
        } else if (size === 'large') {
            content.classList.add('font-large');
        }
    }
    
    fontSizeBtns.forEach(btn => {
        btn.addEventListener('click', function() {
            let size = this.getAttribute('data-size');

            // 保存选项
            if (!isKindleMode()) {
                localStorage.setItem('font_size', size);
            } else {
                setCookie('font_size', size);
            }

            location.reload();
        });
    });
    
    // 添加字体大小样式
    const style = document.createElement('style');
    style.textContent = `
        .font-small { font-size: 1rem; }
        .font-medium { font-size: 1.5rem; }
        .font-large { font-size: 2rem; }

        img.zoomed {
            width: 90vw; 
            max-height: 100vh; 
            cursor: zoom-out;
        }
    `;
    document.head.appendChild(style);

    // 聚焦
    content.focus();
};

window.initScriptChapter = initScript;