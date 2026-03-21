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
    const content = document.getElementById('eb-content');
    
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

// CSS 作用域化函数
/**
 * 优化后的CSS作用域化函数
 * 处理复杂的CSS选择器，包括嵌套规则和特殊选择器
 */
function scopeCSS(cssText, scopeSelector = '[data-eb-styles]') {
  // 临时存储处理过的关键帧动画名称映射
  const keyframesMap = new Map();
  let keyframeCounter = 0;
  
  // 第一步：处理关键帧动画，避免它们被作用域化
  const processedKeyframes = cssText.replace(
    /(@keyframes\s+)([\w-]+)(\s*\{[\s\S]*?\})/g,
    (match, prefix, name, content) => {
      const scopedName = `eb-${keyframeCounter++}-${name}`;
      keyframesMap.set(name, scopedName);
      return `${prefix}${scopedName}${content}`;
    }
  );
  
  // 第二步：处理媒体查询和规则
  const processRules = (css, inMediaQuery = false) => {
    return css.replace(
      /((?:@media[^{]+\{[^{]*)?)([^{]+)\{([^}]+)\}/g,
      (match, mediaPart, selectors, rules) => {
        if (mediaPart) {
          // 这是媒体查询内的规则
          const processedSelectors = selectors.split(',')
            .map(selector => {
              const trimmed = selector.trim();
              if (trimmed === '' || 
                  trimmed.startsWith('@') || 
                  trimmed.includes(scopeSelector)) {
                return trimmed;
              }
              
              // 处理复杂选择器（伪类、伪元素、属性选择器等）
              return scopeComplexSelector(trimmed, scopeSelector);
            })
            .filter(s => s !== '')
            .join(', ');
          
          return `${mediaPart}${processedSelectors}{${rules}}`;
        } else {
          // 普通规则
          const processedSelectors = selectors.split(',')
            .map(selector => {
              const trimmed = selector.trim();
              if (trimmed === '' || trimmed.startsWith('@') || trimmed.includes(scopeSelector)) {
                return trimmed;
              }
              
              return scopeComplexSelector(trimmed, scopeSelector);
            })
            .filter(s => s !== '')
            .join(', ');
          
          return `${processedSelectors}{${rules}}`;
        }
      }
    );
  };
  
  // 第三步：处理复杂选择器
  const scopeComplexSelector = (selector, scope) => {
    // 检查是否已经包含作用域
    if (selector.includes(scope)) {
      return selector;
    }
    
    // 处理:root和:host选择器
    if (selector === ':root' || selector === ':host') {
      return `${scope}:root`;
    }
    
    // 处理:not()、:is()、:where()等伪类函数
    if (selector.includes(':not(') || selector.includes(':is(') || selector.includes(':where(')) {
      // 这些伪类函数内部的选择器也需要作用域化
      return selector.replace(/(:not\(|:is\(|:where\()([^)]+)\)/g, (match, pseudo, innerSelectors) => {
        const scopedInner = innerSelectors.split(',')
          .map(s => scopeComplexSelector(s.trim(), scope))
          .join(', ');
        return `${pseudo}${scopedInner})`;
      });
    }
    
    // 处理普通伪类和伪元素
    const pseudoMatch = selector.match(/(.*?)(::?[a-zA-Z-]+(?:\([^)]+\))?)$/);
    if (pseudoMatch) {
      const [_, base, pseudo] = pseudoMatch;
      if (base.trim() === '') {
        return `${scope}${pseudo}`;
      }
      return `${scope} ${base.trim()}${pseudo}`;
    }
    
    // 默认情况：在开头添加作用域
    return `${scope} ${selector}`;
  };
  
  // 第四步：应用关键帧名称的替换
  let result = processRules(processedKeyframes);
  keyframesMap.forEach((scopedName, originalName) => {
    const regex = new RegExp(`\\b${originalName}\\b`, 'g');
    result = result.replace(regex, scopedName);
  });
  
  return result;
}

/**
 * 优化后的作用域化主函数
 * 支持并行加载和错误处理
 */
async function scopeEBStyles(scopeSelector = '[data-eb-styles]') {
  const ebLinks = Array.from(document.querySelectorAll('link.eb'));
  const ebStyles = Array.from(document.querySelectorAll('style.eb'));
  
  // 处理外部样式表 - 并行加载
  const linkPromises = ebLinks.map(async link => {
    try {
      const response = await fetch(link.href);
      if (!response.ok) {
        throw new Error(`Failed to fetch ${link.href}: ${response.status}`);
      }
      const cssText = await response.text();
      const scopedCSS = scopeCSS(cssText, scopeSelector);
      
      // 创建新的style标签
      const style = document.createElement('style');
      style.setAttribute('data-eb-scoped', 'true');
      style.textContent = scopedCSS;
      
      // 移除原link
      link.remove();
      
      return style;
    } catch (error) {
      console.error('Error loading external CSS:', error);
      // 保持原link作为fallback
      return null;
    }
  });
  
  // 处理内联样式
  const inlinePromises = ebStyles.map(style => {
    const originalCSS = style.textContent;
    const scopedCSS = scopeCSS(originalCSS, scopeSelector);
    
    // 创建新的style标签
    const scopedStyle = document.createElement('style');
    scopedStyle.setAttribute('data-eb-scoped', 'true');
    scopedStyle.textContent = scopedCSS;
    
    // 移除原style
    style.remove();
    
    return Promise.resolve(scopedStyle);
  });
  
  // 等待所有样式处理完成
  const allPromises = [...linkPromises, ...inlinePromises];
  const results = await Promise.allSettled(allPromises);
  
  // 将处理好的样式添加到head
  results.forEach(result => {
    if (result.status === 'fulfilled' && result.value) {
      document.head.appendChild(result.value);
    }
  });
  
}


function initScript() {
    // 显示加载动画
    function showLoading() {
        const overlay = document.getElementById('loadingOverlay');
        if (overlay) {
            overlay.style.display = 'flex';
        }
    }
    
    // 隐藏加载动画
    function hideLoading() {
        const overlay = document.getElementById('loadingOverlay');
        if (overlay) {
            overlay.style.display = 'none';
        }
    }

    // 样式重写，增加区域限定
    scopeEBStyles();

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
    const content = document.getElementById('eb-content');
    const pageJumpInput = document.getElementById('pageJumpInput');
    const goToPageBtn = document.getElementById('goToPage');
    const progressFill = document.getElementById('progressBar');
    const pageHeightSetBtn = document.querySelector("#setPageHeight");
    const pageHeightInput = document.querySelector("#pageHeightInput");
    const toggleClickPageBtn = document.getElementById('toggleClickPage');

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
    let contentWidth = 0;
    let pageWidth = 0;
    let isClickPageEnabled = false; // 点击翻页功能状态

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
        delay: 300, // 延迟300ms后才开始拖动，避免移动端滑动时误触发
        delayOnTouchOnly: true, // 只在触摸设备上应用延迟
        filter: '#eb-content, #pageJumpInput, .page-height-adjustment, #customCssInput', // 允许直接选择#eb-content中的文字
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
    document.querySelectorAll('.eb-content').forEach(item => {
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
        document.querySelectorAll('.eb-content a').forEach(item => {
            const originalHref = item.getAttribute('href');
            if (originalHref) {
                item.setAttribute('data-original-href', originalHref);
                item.removeAttribute('href');
            }
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
        
        // 添加滚动事件监听，更新当前页码
        content.addEventListener('scroll', function() {
            const scrollLeft = content.scrollLeft;
            const newPage = Math.round(scrollLeft / pageWidth);
            
            if (newPage !== currentPage && newPage >= 0 && newPage < totalPages) {
                currentPage = newPage;
                currentPageEl.textContent = currentPage + 1;
                pageJumpInput.value = currentPage + 1;
                updateNavButtons();
                updateProgressIndicator();
                saveReadingProgress();
            }
        });
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
        
        // 保存链接的原始 href 属性，然后移除 href
        document.querySelectorAll('.eb-content a').forEach(item => {
            const originalHref = item.getAttribute('href');
            if (originalHref) {
                item.setAttribute('data-original-href', originalHref);
                item.removeAttribute('href');
            }
        });
        
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
    
    // 创建页面 - 使用 CSS Column 实现
    function createPages() {
        showLoading();
        
        // 保存原始内容
        const originalContent = preprocessContent(content);
        
        // 获取容器高度
        const bottomNav = document.querySelector('.navigation');
        const bottomNavMobile = document.querySelector('.mobile-controls');
        const bottomNavHeight = getElementHeight(bottomNav);
        const bottomNavMobileHeight = getElementHeight(bottomNavMobile);

        const viewportHeight = window.innerHeight;

        let contentHeight = viewportHeight - bottomNavHeight - bottomNavMobileHeight - 40; // 减去边距和安全余量，安全余量就是 margin-top: 20px，然后上下不就都是 20 了
        contentContainer.style.height = `${viewportHeight - bottomNavHeight - bottomNavMobileHeight}px`;
        
        // 直接设置内容容器的高度
        content.style.height = `${contentHeight}px`;
        
        // 先恢复原始内容，以便计算内容高度
        content.innerHTML = originalContent;
        
        // 等待内容渲染完成后计算需要的列数
        setTimeout(() => {
            // 计算内容总高度
            const contentScrollHeight = content.scrollHeight;
            
            // 计算需要的列数
            const columnCount = Math.ceil(contentScrollHeight / contentHeight);
            
            console.log(`Content scroll height: ${contentScrollHeight}, Content height: ${contentHeight}, Column count: ${columnCount}`);
            
            // 应用 CSS Column 样式
            content.style.columnCount = columnCount;
            content.style.columnWidth = 'auto';
            content.style.columnFill = 'auto';
            content.style.columnGap = '0';
            content.style.overflowX = 'auto';
            content.style.overflowY = 'hidden';
            content.style.scrollSnapType = 'x mandatory';
            content.style.scrollBehavior = 'smooth';
            
            // 确保内容能够正确分割
            content.style.breakInside = 'auto';
            content.style.pageBreakInside = 'auto';
            content.style.orphans = 1;
            content.style.widows = 1;
            
            // 等待内容重新渲染完成后计算总页数
            setTimeout(() => {
                calculateTotalPages();
                pageJumpInput.setAttribute('max', totalPages);
                // 延迟隐藏加载动画，确保页面完全渲染
                setTimeout(function() {
                    hideLoading();
                }, 500);
            }, 200);
        }, 200);
    }
    
    // 计算总页数
    function calculateTotalPages() {
        // 获取父容器宽度并计算统一的整数宽度
        const parentContainer = document.querySelector('.container');
        const parentWidth = parentContainer.clientWidth;
        // 设置统一的整数宽度（父容器宽度取整）
        const unifiedWidth = Math.floor(parentWidth);
        
        // 设置 content-container 宽度和高度
        const contentContainer = document.querySelector('.content-container');
        contentContainer.style.width = `${unifiedWidth}px`;
        // 高度由 flex 布局自动计算，确保填满剩余空间
        contentContainer.style.flex = '1';
        
        // 设置 navigation 宽度
        const navigation = document.querySelector('.pagination-mode .navigation');
        if (navigation) {
            navigation.style.width = `${unifiedWidth}px`;
            navigation.style.padding = '20px';
            navigation.style.boxSizing = 'border-box';
        }
        
        // 设置列宽为统一宽度（整数）
        pageWidth = unifiedWidth;
        content.style.columnWidth = `${pageWidth}px`;
        content.style.boxSizing = 'border-box';
        
        // 获取内容总宽度
        const scrollWidth = content.scrollWidth;
        
        // 计算总页数 - 如果最后一页的内容很少，可能需要减去一页
        // 使用 Math.ceil 计算，但如果最后一页的内容少于一半，则减去一页
        const rawTotalPages = scrollWidth / pageWidth;
        totalPages = Math.max(1, Math.ceil(rawTotalPages - 0.1)); // 减去 0.1 避免浮点数精度问题导致的额外一页
        
        // 更新总页数显示
        totalPagesEl.textContent = totalPages;
        
        // 确保当前页码显示正确
        currentPageEl.textContent = currentPage + 1;
        pageJumpInput.value = currentPage + 1;
        
        console.log(`Total pages: ${totalPages}, contentWidth: ${contentWidth}, unifiedWidth: ${unifiedWidth}, pageWidth: ${pageWidth}`);
    }
    
    // 显示指定页面
    function showPage(pageIndex) {
        // 确保页面索引在有效范围内
        if (pageIndex < 0) pageIndex = 0;
        if (pageIndex >= totalPages) pageIndex = totalPages - 1;
        
        // 计算滚动位置 - 使用实际的列宽（页面宽度）作为偏移量，确保为整数
        const scrollPosition = Math.floor(pageIndex * pageWidth);
        
        // 滚动到指定位置 - 使用 smooth 滚动
        content.scrollTo({
            left: scrollPosition,
            behavior: 'instant'  // 立即滚动
        });
        
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
        // 移除分页模式类
        document.body.classList.remove('pagination-mode');
        contentContainer.classList.remove('pagination-mode');
        
        // 恢复内容样式
        content.style.height = '';
        content.style.columnCount = '';
        content.style.columnFill = '';
        content.style.columnGap = '';
        
        // 显示页面的必要元素
        toggleHideUnnecessary(false);
        
        // 隐藏翻页信息
        paginationInfo.style.display = 'none';
        navigationHomeBtn.style.display = 'flex';
        
        // 重新启用链接
        document.querySelectorAll('.eb-content a').forEach(item => {
            const originalHref = item.getAttribute('data-original-href');
            if (originalHref) {
                item.setAttribute('href', originalHref);
                item.removeAttribute('data-original-href');
            }
        });
        
        // 显示目录按钮
        let tocToggleBtn = document.getElementById('tocToggle');
        if (tocToggleBtn) {
            tocToggleBtn.style.display = 'flex';
        }
        let mobileTocBtn = document.getElementById('mobileTocBtn');
        if (mobileTocBtn) {
            mobileTocBtn.style.display = 'flex';
        }
        
        // 重新加载页面以确保所有样式和功能恢复正常
        if (isKindleMode() || confirm('Are you sure you want to exit the page-turning mode?')) {
            location.reload();
        } else {
            // 如果用户取消，重新启用翻页模式
            enablePaginationMode();
        }
    }

    // 保存阅读进度
    function saveReadingProgress() {
        if (isPaginationMode) {
            // 翻页模式
            let storageKey = getStorageKey("turning");
            if (isKindleMode()) {
                setCookie(storageKey, currentPage.toString());
            } else {
                localStorage.setItem(storageKey, currentPage.toString());
            }
        }
    }

    // 加载阅读进度
    function loadReadingProgress() {
        if (isPaginationMode) {
            // 翻页模式需要等待 totalPages 计算完成
            if (totalPages === 0) {
                setTimeout(() => {
                    loadReadingProgress();
                }, 100);
                return
            }

            // 翻页模式
            let storageKey = getStorageKey("turning");
            let savedPage;
            if (isKindleMode()) {
                savedPage = getCookie(storageKey);
            } else {
                savedPage = localStorage.getItem(storageKey);
            }

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
            // 滚动模式不需要等待 totalPages
            let storageKey = getStorageKey("scroll");
            let savedPos = localStorage.getItem(storageKey);
            let windowHeight = window.innerHeight;
            setTimeout(function(){
                if (savedPos && savedPos > 0) {
                    window.scrollTo({
                    top: parseInt(savedPos),
                    behavior: 'smooth'
                    });
                // 显示加载进度提示
                showNotification(`Reading progress loaded: Scroll position ${Math.round( savedPos / (document.documentElement.scrollHeight - windowHeight) * 100 )}%`, 'info');
                }
            }, 1000);
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
            e.preventDefault(); // 禁用默认跳转列行为
            goToPageBtn.click();
        }
    });

    pageHeightInput.addEventListener('keypress', function(e) {
        if (e.key === 'Enter') {
            e.preventDefault(); // 禁用默认跳转列行为
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
                e.preventDefault(); // 禁用默认跳转列行为
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
                e.preventDefault(); // 禁用默认跳转列行为
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
            const customCssInput = document.getElementById('customCssInput');
            const customFontFamilyInput = document.getElementById('customFontFamily');
            if (customCssInput === document.activeElement || customFontFamilyInput === document.activeElement) {
                // 正在进行输入，输入框被聚焦了
                return
            }
            switch(e.key) {
            case 'ArrowLeft':
                e.preventDefault(); // 禁用默认跳转列行为
                let prev_href = document.querySelector(".prev-chapter").href;
                if (prev_href === location.href) {
                    showNotification("It's already the first chapter!", 'warning')
                    break;
                }
                location.href = prev_href;
                break;
            case ' ':
            case 'ArrowDown':
            case 'Space':
                e.preventDefault(); // 禁用默认跳转列行为
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
                e.preventDefault(); // 禁用默认跳转列行为
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

    // 点击翻页功能
    function handleClickPage(e) {
        if (!isClickPageEnabled || !isPaginationMode) return;
        
        // 排除一些特殊元素，避免误触发
        const target = e.target;
        const tagName = target.tagName.toLowerCase();
        const isInteractiveElement = 
            tagName === 'a' || 
            tagName === 'button' || 
            tagName === 'input' || 
            tagName === 'textarea' || 
            tagName === 'select' ||
            tagName === 'img' ||
            target.closest('a') || 
            target.closest('button') || 
            target.closest('input') || 
            target.closest('textarea') || 
            target.closest('select') ||
            target.closest('.navigation') ||
            target.closest('.font-controls') ||
            target.closest('.reading-controls') ||
            target.closest('.toc-container') ||
            target.closest('.medium-zoom-container') ||
            target.closest('.top-controls') ||
            target.closest('.mobile-controls');
        
        if (isInteractiveElement) return;
        
        const screenWidth = window.innerWidth;
        const leftArea = screenWidth * 0.3;  // 左侧30%区域
        const rightArea = screenWidth * 0.7; // 右侧30%区域（从70%开始）
        
        // 左侧30%区域点击 - 上一页
        if (e.clientX < leftArea) {
            e.preventDefault();
            prevPageBtn.click();
        }
        // 右侧30%区域点击 - 下一页
        else if (e.clientX > rightArea) {
            e.preventDefault();
            nextPageBtn.click();
        }
        // 中间40%区域不触发翻页
    }
    
    // 初始化点击翻页功能状态
    function initClickPageState() {
        if (!isKindleMode()) {
            isClickPageEnabled = localStorage.getItem('clickPageEnabled') === 'true';
        } else {
            isClickPageEnabled = getCookie('clickPageEnabled') === 'true';
        }
        updateClickPageButton();
        
        // 如果是 Kindle 模式，默认开启点击翻页
        if (isKindleMode() && getCookie('clickPageEnabled') === null) {
            isClickPageEnabled = true;
            saveClickPageState();
            updateClickPageButton();
        }
        
        // 如果是移动端，默认开启点击翻页
        if (isMobile() && localStorage.getItem('clickPageEnabled') === null) {
            isClickPageEnabled = true;
            saveClickPageState();
            updateClickPageButton();
        }
    }
    
    // 保存点击翻页功能状态
    function saveClickPageState() {
        if (!isKindleMode()) {
            localStorage.setItem('clickPageEnabled', isClickPageEnabled.toString());
        } else {
            setCookie('clickPageEnabled', isClickPageEnabled.toString());
        }
    }
    
    // 更新点击翻页按钮状态
    function updateClickPageButton() {
        if (isClickPageEnabled) {
            toggleClickPageBtn.classList.add('active');
            toggleClickPageBtn.style.background = 'var(--primary)';
            toggleClickPageBtn.style.color = 'white';
        } else {
            toggleClickPageBtn.classList.remove('active');
            toggleClickPageBtn.style.background = '';
            toggleClickPageBtn.style.color = '';
        }
    }
    
    // 初始化点击翻页功能状态
    initClickPageState();
    
    // 监听整个 body 的点击事件
    document.body.addEventListener('click', handleClickPage);
    
    // 纯净阅读模式
    let isPureModeEnabled = false;
    const togglePureModeBtn = document.getElementById('togglePureMode');
    
    // 初始化纯净阅读模式状态
    function initPureModeState() {
        if (!isKindleMode()) {
            isPureModeEnabled = localStorage.getItem('pureModeEnabled') === 'true';
        } else {
            isPureModeEnabled = getCookie('pureModeEnabled') === 'true';
        }
        updatePureModeButton();
        
        const navigation = document.querySelector('.navigation');
        const contentContainer = document.querySelector('.content-container');
        const ebContent = document.getElementById('eb-content');
        
        // 应用保存的状态 - 只在翻页模式下生效
        if (isPureModeEnabled && isPaginationMode) {
            // 隐藏工具栏
            navigation.style.display = 'none';
            
            // 根据设备类型隐藏不同的控件
            if (isMobile()) {
                // 移动端：隐藏 mobile-controls
                const mobileControls = document.querySelector('.mobile-controls');
                if (mobileControls) {
                    mobileControls.style.display = 'none';
                }
            } else {
                // 桌面端：隐藏 top-controls 和 reading-controls
                const topControls = document.querySelector('.top-controls');
                const readingControls = document.querySelector('.reading-controls');
                if (topControls) {
                    topControls.style.display = 'none';
                }
                if (readingControls) {
                    readingControls.style.display = 'none';
                }
            }
            
            // 调整内容容器高度，填充导航栏的空间
            contentContainer.style.marginTop = '0';
            contentContainer.style.marginBottom = '0';
            ebContent.style.minHeight = 'calc(100vh - 80px)'; // 减去页面顶部和底部的 padding
        } else {
            // 显示工具栏
            navigation.style.display = 'flex';
            
            // 根据设备类型显示不同的控件
            if (isMobile()) {
                // 移动端：只显示 mobile-controls，不操作 top-controls 和 reading-controls
                const mobileControls = document.querySelector('.mobile-controls');
                if (mobileControls) {
                    mobileControls.style.display = 'flex';
                }
            } else {
                // 桌面端：显示 top-controls 和 reading-controls
                const topControls = document.querySelector('.top-controls');
                const readingControls = document.querySelector('.reading-controls');
                if (topControls) {
                    topControls.style.display = 'flex';
                }
                if (readingControls) {
                    readingControls.style.display = 'flex';
                }
            }
            
            // 恢复默认高度
            contentContainer.style.marginTop = '';
            contentContainer.style.marginBottom = '';
            ebContent.style.minHeight = '';
        }
    }
    
    // 保存纯净阅读模式状态
    function savePureModeState() {
        if (!isKindleMode()) {
            localStorage.setItem('pureModeEnabled', isPureModeEnabled.toString());
        } else {
            setCookie('pureModeEnabled', isPureModeEnabled.toString());
        }
    }
    
    // 切换纯净阅读模式
    function togglePureMode() {
        // 只在翻页模式下才能切换纯净阅读模式
        if (!isPaginationMode) {
            showNotification('Pure reading mode is only available in page-turning mode', 'info');
            return;
        }
        
        isPureModeEnabled = !isPureModeEnabled;
        savePureModeState();
        updatePureModeButton();
        
        const navigation = document.querySelector('.navigation');
        const contentContainer = document.querySelector('.content-container');
        const ebContent = document.getElementById('eb-content');
        
        if (isPureModeEnabled) {
            // 隐藏工具栏
            navigation.style.display = 'none';
            
            // 根据设备类型隐藏不同的控件
            if (isMobile()) {
                // 移动端：隐藏 mobile-controls
                const mobileControls = document.querySelector('.mobile-controls');
                if (mobileControls) {
                    mobileControls.style.display = 'none';
                }
            } else {
                // 桌面端：隐藏 top-controls 和 reading-controls
                const topControls = document.querySelector('.top-controls');
                const readingControls = document.querySelector('.reading-controls');
                if (topControls) {
                    topControls.style.display = 'none';
                }
                if (readingControls) {
                    readingControls.style.display = 'none';
                }
            }
            
            // 调整内容容器高度，填充导航栏的空间
            contentContainer.style.marginTop = '0';
            contentContainer.style.marginBottom = '0';
            ebContent.style.minHeight = 'calc(100vh - 80px)'; // 减去页面顶部和底部的 padding
            
            showNotification('Pure reading mode enabled. You can click the "Click" button to enable edge-click page turning, or use Spacebar and arrow keys for page navigation.', 'info');
        } else {
            // 显示工具栏
            navigation.style.display = 'flex';
            
            // 根据设备类型显示不同的控件
            if (isMobile()) {
                // 移动端：只显示 mobile-controls，不操作 top-controls 和 reading-controls
                const mobileControls = document.querySelector('.mobile-controls');
                if (mobileControls) {
                    mobileControls.style.display = 'flex';
                }
            } else {
                // 桌面端：显示 top-controls 和 reading-controls
                const topControls = document.querySelector('.top-controls');
                const readingControls = document.querySelector('.reading-controls');
                if (topControls) {
                    topControls.style.display = 'flex';
                }
                if (readingControls) {
                    readingControls.style.display = 'flex';
                }
            }
            
            // 恢复默认高度
            contentContainer.style.marginTop = '';
            contentContainer.style.marginBottom = '';
            ebContent.style.minHeight = '';
            
            showNotification('Pure reading mode disabled', 'info');
        }
    }
    
    // 更新纯净模式按钮状态
    function updatePureModeButton() {
        if (togglePureModeBtn) {
            if (isPureModeEnabled) {
                togglePureModeBtn.classList.add('active');
                togglePureModeBtn.style.background = 'var(--primary)';
                togglePureModeBtn.style.color = 'white';
            } else {
                togglePureModeBtn.classList.remove('active');
                togglePureModeBtn.style.background = '';
                togglePureModeBtn.style.color = '';
            }
        }
    }
    
    // 检查是否为移动端（通过 mobile-controls 是否显示）
    function isMobile() {
        // 更可靠的移动端检测方法
        return window.innerWidth <= 768 || /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent);
    }
    
    // 点击屏幕中间部分切换纯净阅读模式
    document.getElementById('eb-content').addEventListener('click', function(e) {
        // 排除图片元素，避免影响图片缩放
        const target = e.target;
        const tagName = target.tagName.toLowerCase();
        const isImageElement = 
            tagName === 'img' ||
            target.closest('img') ||
            target.closest('.medium-zoom-container');
        
        if (isImageElement) return;
        
        // 计算点击位置是否在文档中心
        const rect = e.currentTarget.getBoundingClientRect();
        const centerX = rect.left + rect.width / 2;
        const centerY = rect.top + rect.height / 2;
        const centerAreaWidth = rect.width * 0.3; // 中心30%区域
        const centerAreaHeight = rect.height * 0.3;
        
        if (Math.abs(e.clientX - centerX) < centerAreaWidth && Math.abs(e.clientY - centerY) < centerAreaHeight) {
            // 点击中间部分，只有在翻页模式下才切换纯净模式
            if (isPaginationMode) {
                // 区分桌面端和移动端的行为
                if (isMobile()) {
                    // 移动端：点击中间部分切换纯净模式
                    togglePureMode();
                } else {
                    // 桌面端：只有在纯净阅读模式已开启时，点击中间部分才关闭纯净模式
                    if (isPureModeEnabled) {
                        togglePureMode();
                    }
                }
            }
        }
    });
    
    // 纯净模式按钮点击事件（仅桌面端）
    if (togglePureModeBtn) {
        togglePureModeBtn.addEventListener('click', function() {
            togglePureMode();
        });
    }

    // Reload按钮点击事件（仅桌面端翻页模式）
    const reloadPagesBtn = document.getElementById('reloadPages');
    if (reloadPagesBtn) {
        reloadPagesBtn.addEventListener('click', function() {
            if (isPaginationMode) {
                showLoading();
                // 保存当前页码
                const savedPage = currentPage;
                // 延迟执行createPages，确保loading动画显示
                setTimeout(() => {
                    createPages();
                    // 恢复页码位置
                    setTimeout(() => {
                        showPage(savedPage);
                        hideLoading();
                        showNotification('Pages reloaded', 'info');
                    }, 500);
                }, 200);
            } else {
                showNotification('Reload is only available in page-turning mode', 'info');
            }
        });
    }

    // 初始化纯净阅读模式状态
    initPureModeState();
    
    // 点击翻页按钮点击事件
    toggleClickPageBtn.addEventListener('click', function() {
        isClickPageEnabled = !isClickPageEnabled;
        saveClickPageState();
        updateClickPageButton();
        
        if (isClickPageEnabled) {
            showNotification('Click edge to turn page enabled', 'info');
        } else {
            showNotification('Click edge to turn page disabled', 'info');
        }
    });
    
    // 自定义 css
    customCssFunc();
    
    // 根据模式决定何时隐藏加载动画
    if (isPaginationMode) {
        // 翻页模式：在 createPages 完成后隐藏 loading
        // createPages 内部已经处理了 hideLoading
    } else {
        // 滚动模式：在 loadReadingProgress 完成后隐藏 loading
        // 延迟隐藏加载动画，确保页面完全渲染
        setTimeout(function() {
            hideLoading();
        }, 500); // 等待 loadReadingProgress 中的 setTimeout 完成
    }

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
    
    
    // 加载书籍目录
    loadBookHomeToc();
    
    async function loadBookHomeToc() {
        try {
            const bookHomeTocList = document.getElementById('bookHomeTocList');
            const currentPath = window.location.pathname;
            const bookHash = currentPath.split('/book/')[1].split('/')[0];
            const tocJsonPath = `/book/${bookHash}/toc.json`;
            
            const response = await fetch(tocJsonPath);
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            const tocData = await response.json();
            
            bookHomeTocList.innerHTML = '';
            
            tocData.forEach(item => {
                const listItem = document.createElement('li');
                listItem.className = `toc-item toc-level-${Math.min(item.level, 3)}`;
                
                const link = document.createElement('a');
                let href = `/book/${bookHash}/${item.chapter_file}`;
                if (item.anchor) {
                    href += `#${item.anchor}`;
                }
                link.href = href;
                link.textContent = item.title;
                
                link.addEventListener('click', function(e) {
                    e.preventDefault();
                    window.location.href = href;
                });
                
                listItem.appendChild(link);
                bookHomeTocList.appendChild(listItem);
            });
            
            // 滚动到当前章节
            const currentChapter = currentPath.split('/').pop();
            const activeLi = bookHomeTocList.querySelector(`a[href*="${currentChapter}"]`);
            if (activeLi) {
                const listItem = activeLi.parentElement;
                listItem.classList.add('active');
                bookHomeTocList.scrollTop = listItem.offsetTop - 150;
            }
            
        } catch (e) {
            console.log('Failed to load book home toc:', e.message);
            const bookHomeTocList = document.getElementById('bookHomeTocList');
            if (bookHomeTocList) {
                bookHomeTocList.innerHTML = '<li class="toc-item">Failed to load table of contents</li>';
            }
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
        const lightTheme = document.querySelector('link[href*="github"][id*="light"]');
        const darkTheme = document.querySelector('link[href*="github"][id*="dark"]');
        
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
        const content = document.getElementById('eb-content');
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
                    // tocFloating.classList.remove('active');
                    mobileTocBtn.classList.remove('active');
                }
            });
            
            listItem.appendChild(link);
            tocList.appendChild(listItem);
        });
    }
    
    // 更新目录高亮
    function updateTocHighlight() {
        const content = document.getElementById('eb-content');
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
    

    // 图片缩放功能 - 使用 medium-zoom
    mediumZoom('#eb-content img', {
        margin: 24,
        background: '#000',
        scrollOffset: 0
    });
    
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

    // 页面加载完成后自动聚焦
    window.addEventListener('load', () => {
        document.body.focus(); // 主动让页面body获得焦点
    });

};

window.initScriptChapter = initScript;