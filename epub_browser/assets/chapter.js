// 禁用浏览器自动恢复滚动位置（连续滚动模式自己管理位置）
if ('scrollRestoration' in history) {
    history.scrollRestoration = 'manual';
}

function isFontAvailable(fontName) {
    var canvas = document.createElement('canvas');
    var context = canvas.getContext('2d');
    
    var baseText = 'abcdefghijklmnopqrstuvwxyz0123456789';
    context.font = '72px sans-serif';
    var baselineWidth = context.measureText(baseText).width;
    
    context.font = '72px ' + fontName + ', sans-serif';
    var testWidth = context.measureText(baseText).width;
    
    return testWidth !== baselineWidth;
}

var commonFonts = [
    'Arial', 'Helvetica', 'Times New Roman', 'Helvetica',
    'Courier New','Trebuchet MS', 'Arial Black','Segoe UI', 'Microsoft YaHei', "微软雅黑", 'SimSun',
    'SimHei',"Heiti", "Song Ti", "Kai Ti", 'KaiTi', 'FangSong', "Fang Song", "宋体", "仿宋", "黑体",
    'STHeiti', 'STKaiti', 'STSong', 'STFangsong', 'PingFang SC', 'Heiti SC', 
    'Noto Sans SC', 'WenQuanYi Micro Hei', 'MiSans', 'Alimama ShuHeiTi',
    'LXGW WenKai', 'Amazon Ember',
];

function getAvailableFonts() {
    return commonFonts.filter(function(font) {
        return isFontAvailable(font);
    });
}

function updateFontFamily(fontFamily, fontFamilyInput) {
    var fontFamilySelect = document.getElementById('fontFamilySelect');
    var customFontInput = document.getElementById('customFontInput');
    var customFontFamily = document.getElementById('customFontFamily');
    fontFamilySelect.value = fontFamily;
    
    // 获取 EPUB 内容容器
    var ebContent = document.querySelector('[data-eb-styles]');
    
    if (fontFamily === "ebook-default") {
        // 使用电子书内置字体 - 移除字体覆盖样式
        document.documentElement.style.setProperty('--font-family', '');
        document.body.style.fontFamily = '';
        if (ebContent) {
            ebContent.classList.add('ebook-font-default');
        }
    } else {
        // 使用用户选择的字体 - 添加字体覆盖样式
        var targetFontFamily = fontFamily === "custom" ? fontFamilyInput : fontFamily;
        document.documentElement.style.setProperty('--font-family', targetFontFamily);
        document.body.style.fontFamily = targetFontFamily;
        if (ebContent) {
            ebContent.classList.remove('ebook-font-default');
        }
    }
    
    if (fontFamily == "custom") {
        customFontInput.style.display = 'flex';
        customFontFamily.value = fontFamilyInput;
    } else {
        customFontInput.style.display = 'none';
    }
    if (fontFamily == "custom") {
        if (!isKindleMode()) {
            localStorage.setItem('font_family_input', fontFamilyInput);
            localStorage.setItem('font_family', "custom");
        } else {
            setCookie('font_family_input', fontFamilyInput);
            setCookie('font_family', "custom");
        }
        if (!window.epubBrowserCache) {
            window.epubBrowserCache = {};
        }
        window.epubBrowserCache.font_family_input = fontFamilyInput;
        window.epubBrowserCache.font_family = "custom";
    } else {
        if (!isKindleMode()) {
            localStorage.setItem('font_family', fontFamily);
        } else {
            setCookie('font_family', fontFamily);
        }
        if (!window.epubBrowserCache) {
            window.epubBrowserCache = {};
        }
        window.epubBrowserCache.font_family = fontFamily;
    }
    document.dispatchEvent(new CustomEvent('epub:reader-typography-change'));
}

function setCookie(key, value) {
    var date = new Date();
    date.setTime(date.getTime() + 3650 * 24 * 60 * 60 * 1000);
    var expires = "expires=" + date.toUTCString();
    document.cookie = key + "=" + value + "; " + expires + "; path=/;";
}

// KINDLE 兼容版 getCookie
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

function deleteCookie(name) {
    document.cookie = name + "=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;";
}

function showNotification(message, type) {
    return window.EpubBrowserNotification.show(message, type);
}

function getElementHeight(element) {
    var content = document.getElementById('eb-content');
    var tempElement = element.cloneNode(true);
    tempElement.style.visibility = 'hidden';
    tempElement.style.position = 'absolute';
    content.appendChild(tempElement);
    
    var height = tempElement.getBoundingClientRect().height;
    var styles = window.getComputedStyle(element);
    var marginTop = parseFloat(styles.marginTop) || 0;
    var marginBottom = parseFloat(styles.marginBottom) || 0;
    
    content.removeChild(tempElement);
    
    return height + marginTop + marginBottom;
}

function isKindleMode() {
    if (window.epubBrowserCache && window.epubBrowserCache.kindle_mode !== undefined) {
        return window.epubBrowserCache.kindle_mode === 'true';
    }
    var ua = navigator.userAgent.toLowerCase();
    var isKindle = ua.indexOf('kindle') !== -1 || ua.indexOf('silk') !== -1;
    if (!window.epubBrowserCache) {
        window.epubBrowserCache = {};
    }
    window.epubBrowserCache.kindle_mode = isKindle ? 'true' : 'false';
    return isKindle;
}

function scopeCSS(cssText, scopeSelector) {
  if (!scopeSelector) scopeSelector = '[data-eb-styles]';
  var keyframesMap = {};
  var keyframeCounter = 0;
  
  var processedKeyframes = cssText.replace(
    /(@keyframes\s+)([\w-]+)(\s*\{[\s\S]*?\})/g,
    function(match, prefix, name, content) {
      var scopedName = 'eb-' + keyframeCounter++ + '-' + name;
      keyframesMap[name] = scopedName;
      return prefix + scopedName + content;
    }
  );
  
  var processRules = function(css, inMediaQuery) {
    return css.replace(
      /((?:@media[^{]+\{[^{]*)?)([^{]+)\{([^}]+)\}/g,
      function(match, mediaPart, selectors, rules) {
        if (mediaPart) {
          var selArr = selectors.split(',');
          var processed = [];
          for (var i = 0; i < selArr.length; i++) {
            var s = selArr[i].trim();
            if (s === '' || s.startsWith('@') || s.indexOf(scopeSelector) !== -1) {
              processed.push(s);
            } else {
              processed.push(scopeComplexSelector(s, scopeSelector));
            }
          }
          return mediaPart + processed.join(', ') + '{' + rules + '}';
        } else {
          var selArr2 = selectors.split(',');
          var processed2 = [];
          for (var i = 0; i < selArr2.length; i++) {
            var s = selArr2[i].trim();
            if (s === '' || s.startsWith('@') || s.indexOf(scopeSelector) !== -1) {
              processed2.push(s);
            } else {
              processed2.push(scopeComplexSelector(s, scopeSelector));
            }
          }
          return processed2.join(', ') + '{' + rules + '}';
        }
      }
    );
  };
  
  var scopeComplexSelector = function(selector, scope) {
    if (selector.indexOf(scope) !== -1) return selector;
    if (selector === ':root' || selector === ':host') return scope + ':root';
    if (selector.indexOf(':not(') !== -1 || selector.indexOf(':is(') !== -1 || selector.indexOf(':where(') !== -1) {
      return selector.replace(/(:not\(|:is\(|:where\()([^)]+)\)/g, function(m, p, inner) {
        var scopedInner = inner.split(',').map(function(s) {
          return scopeComplexSelector(s.trim(), scope);
        }).join(', ');
        return p + scopedInner + ')';
      });
    }
    var pseudoMatch = selector.match(/(.*?)(::?[a-zA-Z-]+(?:\([^)]+\))?)$/);
    if (pseudoMatch) {
      var base = pseudoMatch[1].trim();
      var pseudo = pseudoMatch[2];
      if (base === '') return scope + pseudo;
      return scope + ' ' + base + pseudo;
    }
    return scope + ' ' + selector;
  };
  
  var result = processRules(processedKeyframes);
  for (var orig in keyframesMap) {
    if (keyframesMap.hasOwnProperty(orig)) {
      var reg = new RegExp('\\b' + orig + '\\b', 'g');
      result = result.replace(reg, keyframesMap[orig]);
    }
  }
  return result;
}

// 移除 async，Kindle 兼容
function scopeEBStyles(scopeSelector) {
  if (!scopeSelector) scopeSelector = '[data-eb-styles]';
  var ebLinks = Array.prototype.slice.call(document.querySelectorAll('link.eb'));
  var ebStyles = Array.prototype.slice.call(document.querySelectorAll('style.eb'));
  
  var processLink = function(link) {
    var xhr = new XMLHttpRequest();
    xhr.open('GET', link.href, true);
    xhr.onload = function() {
      if (xhr.status >= 200 && xhr.status < 300) {
        var scoped = scopeCSS(xhr.responseText, scopeSelector);
        var style = document.createElement('style');
        style.setAttribute('data-eb-scoped', 'true');
        style.textContent = scoped;
        link.parentNode.removeChild(link);
        document.head.appendChild(style);
      }
    };
    xhr.send();
  };
  
  for (var i = 0; i < ebLinks.length; i++) {
    processLink(ebLinks[i]);
  }
  
  for (var j = 0; j < ebStyles.length; j++) {
    var s = ebStyles[j];
    var scoped = scopeCSS(s.textContent, scopeSelector);
    var style = document.createElement('style');
    style.setAttribute('data-eb-scoped', 'true');
    style.textContent = scoped;
    s.parentNode.removeChild(s);
    document.head.appendChild(style);
  }
}

function initializeChapterBookshelf() {
    if (!window.initBookShelf) return false;
    window.initBookShelf();
    return true;
}

function initScript() {
    var i18n = window.EpubBrowserI18n;
    function showLoading() {
        var overlay = document.getElementById('contentLoading');
        if (overlay) overlay.classList.add('is-visible');
    }
    
    function hideLoading() {
        var overlay = document.getElementById('contentLoading');
        if (overlay) overlay.classList.remove('is-visible');
    }

    scopeEBStyles();

    var path = window.location.pathname;
    var pathParts = path.split('/').filter(function(item) { return item !== ''; });
    var book_hash = pathParts[pathParts.indexOf('book') + 1];
    var chapter_index = pathParts[pathParts.indexOf('book') + 2];
    chapter_index = chapter_index.replace("chapter_", "").replace(".html", "");

    var paginationModeToggle = document.getElementById('paginationModeToggle');
    var exitPaginationModeBtn = document.getElementById('exitPaginationMode');
    var navigationHomeBtn = document.getElementById('navigationHomeBtn');
    var paginationInfo = document.getElementById('paginationInfo');
    var currentPageEl = document.getElementById('currentPage');
    var totalPagesEl = document.getElementById('totalPages');
    var prevPageBtn = document.getElementById('prevPage');
    var nextPageBtn = document.getElementById('nextPage');
    var contentContainer = document.querySelector('.eb-content-container');
    var content = document.getElementById('eb-content');
    var pageJumpInput = document.getElementById('pageJumpInput');
    var goToPageBtn = document.getElementById('goToPage');
    var progressFill = document.getElementById('progressBar');
    var readingProgressContainer = document.querySelector('.reading-progress-container');
    var pageHeightSetBtn = document.querySelector("#setPageHeight");
    var pageHeightInput = document.querySelector("#pageHeightInput");
    var toggleClickPageBtn = document.getElementById('toggleClickPage');

    function getStorageKey(mode) {
        return mode + '_' + book_hash + '_' + chapter_index;
    }
    
    var isPaginationMode = false;
    var isContinuousScroll = false;
    var currentPage = 0;
    var totalPages = 0;
    var contentWidth = 0;
    var pageWidth = 0;
    var paginationResizeObserver = null;
    var paginationWidthSyncPending = false;
    var isClickPageEnabled = false;
    var loadedChapters = {};  // 记录已加载的章节 {chapterIndex: true}
    var isLoadingChapter = false;  // 防止重复加载
    var maxScrollTopSoFar = 0;  // 连续滚动模式下，跟踪用户向下滚过的最远位置
    var continuousChapterWindow = null;
    var visibleChapterIndex = parseInt(chapter_index, 10);
    var activeReaderChapterRequest = 0;
    var readerChapterXhr = null;
    var continuousChapterXhr = null;
    var activeContinuousChapterRequest = 0;

    function dispatchChapterContentLifecycle(type, rootNode) {
        if (!rootNode || typeof window.CustomEvent !== 'function') return;
        window.dispatchEvent(new CustomEvent('epub-browser:chapter-content-' + type, {
            detail: { root: rootNode }
        }));
    }

    function getReadingPreference(key) {
        return isKindleMode() ? getCookie(key) : localStorage.getItem(key);
    }

    function setReadingPreference(key, value) {
        if (isKindleMode()) setCookie(key, value);
        else localStorage.setItem(key, value);
    }

    function applyReadingProgressBarVisibility(visible) {
        if (!readingProgressContainer) return;
        var className = window.EpubReadingProgress
            ? window.EpubReadingProgress.progressBarClass(visible)
            : (visible ? '' : 'is-progress-bar-hidden');
        readingProgressContainer.classList.toggle('is-progress-bar-hidden', className !== '');
    }

    var showReadingProgressBar = window.EpubReadingProgress
        ? window.EpubReadingProgress.showProgressBar(getReadingPreference('showReadingProgressBar'))
        : getReadingPreference('showReadingProgressBar') !== 'false';
    var showDesktopChapterSidebar = getReadingPreference('desktopChapterSidebar') === 'true';
    var arrowKeyNavigationEnabled = window.EpubReaderLayout
        ? window.EpubReaderLayout.readingPreferenceEnabled(getReadingPreference('arrowKeyNavigation'))
        : getReadingPreference('arrowKeyNavigation') !== 'false';
    var spaceKeyNavigationEnabled = window.EpubReaderLayout
        ? window.EpubReaderLayout.readingPreferenceEnabled(getReadingPreference('spaceKeyNavigation'))
        : getReadingPreference('spaceKeyNavigation') !== 'false';
    applyReadingProgressBarVisibility(showReadingProgressBar);

    function applyDesktopChapterSidebar() {
        var isVisible = showDesktopChapterSidebar && !isPaginationMode && !isKindleMode();
        document.body.classList.toggle('desktop-chapter-sidebar', isVisible);
        var persistentDrawer = document.getElementById('bookHomeFloating');
        if (persistentDrawer && !persistentDrawer.classList.contains('active')) {
            persistentDrawer.setAttribute('aria-hidden', isVisible ? 'false' : 'true');
        }
    }

    var fontSize = "3";
    var pageWidthPreset = "3";
    var fontFamily = "ebook-default";
    var fontFamilyInput = null;
    var supportedFonts = getAvailableFonts();
    
    // 替换箭头函数
    supportedFonts.forEach(function(item) {
        var opt = document.createElement('option');
        opt.value = item;
        opt.textContent = item;
        document.getElementById('fontFamilySelect').appendChild(opt);
    });

    if (!isKindleMode()) {
        var currentPaginationMode = "false";
        if (window.epubBrowserCache && window.epubBrowserCache.turning) {
            currentPaginationMode = window.epubBrowserCache.turning;
        } else {
            currentPaginationMode = localStorage.getItem('turning') || "false";
            if (currentPaginationMode) {
                if (!window.epubBrowserCache) window.epubBrowserCache = {};
                window.epubBrowserCache.turning = currentPaginationMode;
            }
        }
        isPaginationMode = currentPaginationMode == "true";
        
        // 连续滚动模式状态（仅在非翻页模式下生效）
        if (!isPaginationMode) {
            if (window.epubBrowserCache && window.epubBrowserCache.continuousScroll !== undefined) {
                isContinuousScroll = window.epubBrowserCache.continuousScroll === 'true';
            } else {
                isContinuousScroll = localStorage.getItem('continuousScroll') === 'true';
                if (localStorage.getItem('continuousScroll') !== null) {
                    if (!window.epubBrowserCache) window.epubBrowserCache = {};
                    window.epubBrowserCache.continuousScroll = isContinuousScroll ? 'true' : 'false';
                }
            }
        }
        
        if (window.epubBrowserCache && window.epubBrowserCache.font_size) {
            fontSize = window.epubBrowserCache.font_size;
        } else {
            fontSize = localStorage.getItem('font_size') || "3";
            if (fontSize) {
                if (!window.epubBrowserCache) window.epubBrowserCache = {};
                window.epubBrowserCache.font_size = fontSize;
            }
        }

        if (window.epubBrowserCache && window.epubBrowserCache.page_width) {
            pageWidthPreset = window.epubBrowserCache.page_width;
        } else {
            pageWidthPreset = localStorage.getItem('page_width') || "3";
            if (!window.epubBrowserCache) window.epubBrowserCache = {};
            window.epubBrowserCache.page_width = pageWidthPreset;
        }
        
        if (window.epubBrowserCache && window.epubBrowserCache.font_family) {
            fontFamily = window.epubBrowserCache.font_family;
        } else {
            fontFamily = localStorage.getItem('font_family') || "ebook-default";
            if (fontFamily) {
                if (!window.epubBrowserCache) window.epubBrowserCache = {};
                window.epubBrowserCache.font_family = fontFamily;
            }
        }
        
        if (window.epubBrowserCache && window.epubBrowserCache.font_family_input) {
            fontFamilyInput = window.epubBrowserCache.font_family_input;
        } else {
            fontFamilyInput = localStorage.getItem('font_family_input');
            if (fontFamilyInput) {
                if (!window.epubBrowserCache) window.epubBrowserCache = {};
                window.epubBrowserCache.font_family_input = fontFamilyInput;
            }
        }
        
    } else {
        var currentPaginationMode = getCookie('turning') || "false";
        isPaginationMode = currentPaginationMode == "true";
        fontSize = getCookie('font_size') || "3";
        pageWidthPreset = getCookie('page_width') || "3";
        fontFamily = getCookie('font_family') || "ebook-default";
        fontFamilyInput = getCookie('font_family_input');
    }
    updatePageWidth(pageWidthPreset, false);
    applyDesktopChapterSidebar();
    if (isPaginationMode) {
        updateFontSize(fontSize);
    } else {
        showLoading();
        requestAnimationFrame(function() {
            requestAnimationFrame(function() {
                updateFontSize(fontSize);
            });
        });
    }
    updateFontFamily(fontFamily, fontFamilyInput);

    document.addEventListener('keydown', handleKeyDown);

    document.querySelectorAll('.eb-content').forEach(function(item) {
        item.addEventListener('dblclick', function(e) {
            e.stopPropagation();
        });
    });

    if (isKindleMode() || isPaginationMode) {
        var mobileControls = document.querySelector('.mobile-controls');
        var bottomNav = document.querySelector('.navigation');
        bottomNav.style.marginBottom = getElementHeight(mobileControls) + 'px';
    }

    if (isKindleMode()) {
        document.documentElement.classList.remove("kindle-mode");
        document.documentElement.classList.add("kindle-mode");
    }

    if (isPaginationMode) {
        enablePaginationMode();
        document.querySelectorAll('.eb-content a').forEach(function(item) {
            var href = item.getAttribute('href');
            if (href) {
                item.setAttribute('data-original-href', href);
                item.removeAttribute('href');
            }
        });
        content.addEventListener('scroll', function() {
            var sl = content.scrollLeft;
            var np = Math.round(sl / pageWidth);
            if (np !== currentPage && np >=0 && np < totalPages) {
                currentPage = np;
                currentPageEl.textContent = currentPage+1;
                pageJumpInput.value = currentPage+1;
                updateNavButtons();
                updateProgressIndicator();
                saveReadingProgress();
            }
        });
    } else {
        loadReadingProgress();
        if (isContinuousScroll) {
            initContinuousScroll();
        }
    }
    
    function savePaginationModeAndReload(nextMode) {
        isPaginationMode = typeof nextMode === 'boolean' ? nextMode : !isPaginationMode;
        if (isPaginationMode) {
            if (!isKindleMode()) localStorage.setItem('turning', 'true');
            else setCookie('turning', 'true');
        } else {
            if (!isKindleMode()) localStorage.removeItem('turning');
            else deleteCookie('turning');
        }
        if (!window.epubBrowserCache) window.epubBrowserCache = {};
        window.epubBrowserCache.turning = isPaginationMode ? 'true' : 'false';
        location.reload();
    }
    
    if (paginationModeToggle) {
        paginationModeToggle.checked = isPaginationMode;
        paginationModeToggle.addEventListener('change', function() {
            savePaginationModeAndReload(this.checked);
        });
    }
    if (exitPaginationModeBtn) {
        exitPaginationModeBtn.addEventListener('click', function() {
            savePaginationModeAndReload(false);
        });
    }
    
    function enablePaginationMode() {
        if (!isKindleMode()) localStorage.setItem('turning', 'true');
        else setCookie('turning', 'true');
        if (!window.epubBrowserCache) window.epubBrowserCache = {};
        window.epubBrowserCache.turning = 'true';
        
        document.body.classList.add('pagination-mode');
        contentContainer.classList.add('pagination-mode');
        
        var mobileControls = document.querySelector('.mobile-controls');
        var bottomNav = document.querySelector('.navigation');
        bottomNav.style.marginBottom = getElementHeight(mobileControls) + 'px';
        
        toggleHideUnnecessary(true);
        paginationInfo.style.display = 'flex';
        navigationHomeBtn.style.display = 'none';
        
        document.querySelectorAll('.eb-content a').forEach(function(item) {
            var href = item.getAttribute('href');
            if (href) {
                item.setAttribute('data-original-href', href);
                item.removeAttribute('href');
            }
        });
        
        createPages();
        loadReadingProgress();
        updateNavButtons();
        
        if (isKindleMode()) {
            showNotification(i18n.t('reader.turningModeEnabled'), 'info');
        }
    }

    function toggleHideUnnecessary(hide) {
        var chapterTopBar = document.querySelector(".chapter-top-bar");
        var footer = document.querySelector("footer");
        if (hide) {
            chapterTopBar.style.display = 'none';
            footer.style.display = 'none';
        } else {
            chapterTopBar.style.display = '';
            footer.style.display = 'inherit';
        }
    }
    
    function disablePaginationMode() {
        if (!isKindleMode()) localStorage.removeItem('turning');
        else deleteCookie('turning');
        restoreOriginalContent();
    }

    function preprocessContent(c) {
        if (c.children && c.children.length === 1) {
            if (c.children[0].tagName === "DIV") {
                return preprocessContent(c.children[0]);
            }
        }
        return c.innerHTML;
    }

    function afterPaginationLayout(callback) {
        var schedule = window.requestAnimationFrame || function(fn) { return setTimeout(fn, 0); };
        schedule(function() {
            schedule(callback);
        });
    }

    function getPaginationCanvasWidth() {
        if (window.EpubReaderLayout && typeof window.EpubReaderLayout.getPaginationPageWidth === 'function') {
            return window.EpubReaderLayout.getPaginationPageWidth(contentContainer);
        }
        var rect = contentContainer.getBoundingClientRect();
        return rect.width || contentContainer.clientWidth;
    }

    function getPaginationScrollPosition(pageIndex) {
        if (window.EpubReaderLayout && typeof window.EpubReaderLayout.getPaginationScrollLeft === 'function') {
            return window.EpubReaderLayout.getPaginationScrollLeft(pageIndex, pageWidth);
        }
        return Math.round(pageIndex * pageWidth);
    }

    function paginationCanvasWidthChanged(nextWidth) {
        if (window.EpubReaderLayout && typeof window.EpubReaderLayout.paginationWidthChanged === 'function') {
            return window.EpubReaderLayout.paginationWidthChanged(pageWidth, nextWidth);
        }
        return Math.abs(pageWidth - nextWidth) > 0.01;
    }

    function syncPaginationCanvasWidth() {
        paginationWidthSyncPending = false;
        if (!isPaginationMode || !pageWidth) return;
        var nextWidth = getPaginationCanvasWidth();
        if (!paginationCanvasWidthChanged(nextWidth)) return;
        var savedPage = currentPage;
        calculateTotalPages();
        showPage(Math.min(savedPage, totalPages - 1));
    }

    function watchPaginationCanvas() {
        if (paginationResizeObserver || typeof window.ResizeObserver !== 'function') return;
        paginationResizeObserver = new window.ResizeObserver(function() {
            if (paginationWidthSyncPending) return;
            paginationWidthSyncPending = true;
            afterPaginationLayout(syncPaginationCanvasWidth);
        });
        paginationResizeObserver.observe(contentContainer);
    }
    
    function createPages(target) {
        showLoading();
        var hasPDFPage = !!content.querySelector('[data-pdf-page-number]');
        if (hasPDFPage) dispatchChapterContentLifecycle('removed', content);
        var original = hasPDFPage ? content.innerHTML : preprocessContent(content);
        if (!hasPDFPage) dispatchChapterContentLifecycle('removed', content);
        content.innerHTML = original;
        dispatchChapterContentLifecycle('added', content);
        
        setTimeout(function() {
            content.style.columnCount = 'auto';
            content.style.columnWidth = 'auto';
            content.style.columnFill = 'auto';
            content.style.columnGap = '0';
            content.style.overflowX = 'hidden';
            content.style.overflowY = 'hidden';
            content.style.scrollSnapType = 'none';
            content.style.scrollBehavior = 'auto';
            content.style.breakInside = 'auto';
            content.style.pageBreakInside = 'auto';
            content.style.orphans = 1;
            content.style.widows = 1;
            
            afterPaginationLayout(function() {
                calculateTotalPages();
                watchPaginationCanvas();
                pageJumpInput.setAttribute('max', totalPages);
                if (target) scrollToPaginationTarget(target);
                setTimeout(function() {
                    hideLoading();
                    Fancybox.bind('#eb-content img', {
                        // Your custom options
                    });
                }, 500);
            });
        }, 200);
    }

    function scrollToPaginationTarget(target) {
        var anchor = null;
        if (target.hash) {
            var anchorId = decodeURIComponent(target.hash.substring(1));
            var anchors = content.querySelectorAll('[id]');
            for (var i = 0; i < anchors.length; i++) {
                if (anchors[i].id === anchorId) {
                    anchor = anchors[i];
                    break;
                }
            }
        }
        var page = anchor && pageWidth ? Math.floor(anchor.offsetLeft / pageWidth) : 0;
        showPage(page);
    }

    function refreshPaginationChapter(target) {
        wrapAllElements('table', 'div', content);
        wrapAllElements('img', 'div', content);
        prepareChapterCodeBlocks(content);
        document.querySelectorAll('.eb-content a').forEach(function(item) {
            var href = item.getAttribute('href');
            if (!href) return;
            item.setAttribute('data-original-href', href);
            item.removeAttribute('href');
        });
        currentPage = 0;
        totalPages = 0;
        setBookTocActiveChapter(target.index, true);
        selectReadingChapter(target.index);
        refreshChapterAnnotations(target, false);
        createPages(target);
    }
    
    function calculateTotalPages() {
        var w = getPaginationCanvasWidth();
        var nav = document.querySelector('.pagination-mode .navigation');
        if (nav) {
            nav.style.width = w + 'px';
            nav.style.padding = '20px';
            nav.style.boxSizing = 'border-box';
        }
        pageWidth = w;
        content.style.columnCount = 'auto';
        content.style.columnWidth = pageWidth + 'px';
        content.style.boxSizing = 'border-box';
        var sw = content.scrollWidth;
        var raw = sw / pageWidth;
        totalPages = Math.max(1, Math.ceil(raw - 0.1));
        totalPagesEl.textContent = totalPages;
        currentPageEl.textContent = currentPage+1;
        pageJumpInput.value = currentPage+1;
    }
    
    function announceReadingSessionPageTurn() {
        window.dispatchEvent(new CustomEvent('epub:reader-page-turn'));
    }

    function showPage(idx, fromReaderNavigation) {
        if (idx < 0) idx = 0;
        if (idx >= totalPages) idx = totalPages-1;
        var pageChanged = idx !== currentPage;
        var pos = getPaginationScrollPosition(idx);
        content.scrollTo(pos, 0);
        currentPage = idx;
        currentPageEl.textContent = idx+1;
        totalPagesEl.textContent = totalPages;
        pageJumpInput.value = idx+1;
        updateProgressIndicator();
        updateNavButtons();
        saveReadingProgress();
        updateTocHighlight();
        if (fromReaderNavigation && pageChanged) announceReadingSessionPageTurn();
    }
    
    function updateNavButtons() {
        prevPageBtn.disabled = currentPage === 0;
        nextPageBtn.disabled = currentPage === totalPages-1;
    }

    function updateProgressIndicator() {
        var p = ((currentPage+1)/totalPages)*100;
        progressFill.style.width = p+'%';
    }
    
    async function restoreOriginalContent() {
        document.body.classList.remove('pagination-mode');
        contentContainer.classList.remove('pagination-mode');
        content.style.height = '';
        content.style.columnCount = '';
        content.style.columnFill = '';
        content.style.columnGap = '';
        toggleHideUnnecessary(false);
        paginationInfo.style.display = 'none';
        navigationHomeBtn.style.display = 'flex';
        
        document.querySelectorAll('.eb-content a').forEach(function(item) {
            var href = item.getAttribute('data-original-href');
            if (href) {
                item.setAttribute('href', href);
                item.removeAttribute('data-original-href');
            }
        });
        
        var toc = document.getElementById('tocToggle');
        if (toc) toc.style.display = 'flex';
        var mtoc = document.getElementById('mobileTocBtn');
        if (mtoc) mtoc.style.display = 'flex';
        
        if (isKindleMode() || await window.EpubDialog.confirm({
            title: i18n.t('reader.exitTurning'),
            message: i18n.t('reader.exitTurningConfirm'),
            confirmText: i18n.t('reader.exitTurning')
        })) {
            location.reload();
        } else {
            enablePaginationMode();
        }
    }

    function saveReadingProgress() {
        if (isPaginationMode) {
            var key = getStorageKey("turning");
            if (isKindleMode()) setCookie(key, currentPage.toString());
            else localStorage.setItem(key, currentPage.toString());
        }
    }

    function loadReadingProgress() {
        if (isPaginationMode) {
            if (totalPages === 0) {
                setTimeout(loadReadingProgress, 100);
                return;
            }
            var key = getStorageKey("turning");
            var sp = isKindleMode() ? getCookie(key) : localStorage.getItem(key);
            if (sp && parseInt(sp) > 0) {
                var pi = parseInt(sp,10);
                if (pi >=0 && pi < totalPages) {
                    showPage(pi);
                    showNotification(i18n.t('reader.progressLoadedPage', { page: pi + 1 }), 'info');
                }
            } else {
                showPage(0);
            }
        } else {
            // 连续滚动模式下不恢复滚动进度（章节位置通过 URL 记录）
            if (!isContinuousScroll) {
                var key = getStorageKey("scroll");
                var pos = localStorage.getItem(key);
                var wh = window.innerHeight;
                var scrollRestoreTimer = setTimeout(function() {
                    if (pos && parseInt(pos) > 0) {
                        window.scrollTo(0, parseInt(pos));
                        var total = document.documentElement.scrollHeight - wh;
                        var pct = Math.round((parseInt(pos)/total)*100);
                        showNotification(i18n.t('reader.progressLoadedPercent', { percent: pct }), 'info');
                    }
                }, 1000);
                // 用户在恢复前手动滚动则取消自动恢复
                var cancelScrollRestore = function() {
                    if (scrollRestoreTimer) {
                        clearTimeout(scrollRestoreTimer);
                        scrollRestoreTimer = null;
                    }
                    window.removeEventListener('scroll', cancelScrollRestore);
                    window.removeEventListener('wheel', cancelScrollRestore);
                    window.removeEventListener('touchstart', cancelScrollRestore);
                    window.removeEventListener('keydown', cancelScrollRestore);
                };
                window.addEventListener('scroll', cancelScrollRestore, { once: true });
                window.addEventListener('wheel', cancelScrollRestore, { once: true });
                window.addEventListener('touchstart', cancelScrollRestore, { once: true });
                window.addEventListener('keydown', cancelScrollRestore, { once: true });
            }
        }
    }

    goToPageBtn.addEventListener('click', function() {
        var n = parseInt(pageJumpInput.value,10);
        if (n >=1 && n <= totalPages) {
            showPage(n-1, true);
        } else {
            showNotification(i18n.t('reader.pageRange', { total: totalPages }), 'warning');
            pageJumpInput.value = currentPage+1;
        }
    });
    
    pageJumpInput.addEventListener('keypress', function(e) {
        if (e.key === 'Enter') {
            e.preventDefault();
            goToPageBtn.click();
        }
    });

    pageHeightInput.addEventListener('keypress', function(e) {
        if (e.key === 'Enter') {
            e.preventDefault();
            pageHeightSetBtn.click();
        }
    });

    pageHeightSetBtn.addEventListener('click', function() {
        var h = parseFloat(pageHeightInput.value);
        if (h>0) {
            if (isKindleMode()) setCookie('page_height', h);
            else localStorage.setItem('page_height', h);
            location.reload();
        } else {
            showNotification(i18n.t('reader.validNumber'), 'warning');
        }
    });

    function chapterTargetFromUrl(url) {
        var link = document.createElement('a');
        link.href = url;
        var match = link.pathname.match(/\/chapter_(\d+)\.html$/);
        if (!match) return null;
        var bookPath = '/book/' + book_hash + '/';
        if (link.pathname.indexOf(bookPath) === -1) return null;
        // Chapter-local state such as `annotation` and `ai_result` must never
        // follow the reader into another chapter.  A hash is retained only
        // because a TOC entry can deliberately point at a section anchor.
        link.search = '';
        return {
            index: parseInt(match[1], 10),
            url: link.href,
            path: link.pathname,
            hash: link.hash
        };
    }

    function isDifferentScrollingChapter(url) {
        var target = chapterTargetFromUrl(url);
        return target && target.path !== window.location.pathname;
    }

    function copyChapterNavigationHref(current, incoming) {
        if (!current || !incoming) return;
        var href = incoming.getAttribute('href');
        if (href) current.setAttribute('href', href);
        else current.removeAttribute('href');
    }

    function syncChapterNavigationLinks(source) {
        copyChapterNavigationHref(
            document.querySelector('.prev-chapter'),
            source.querySelector('.prev-chapter')
        );
        copyChapterNavigationHref(
            document.querySelector('.next-chapter'),
            source.querySelector('.next-chapter')
        );
        var currentMobileLinks = document.querySelectorAll('.mobile-controls > a');
        var incomingMobileLinks = source.querySelectorAll('.mobile-controls > a');
        for (var i = 0; i < currentMobileLinks.length && i < incomingMobileLinks.length; i++) {
            copyChapterNavigationHref(currentMobileLinks[i], incomingMobileLinks[i]);
        }
    }

    function syncChapterScopedControls(chapterIndex) {
        var controls = document.querySelectorAll(
            '[data-ai-learning-canvas], [data-ai-followup-drawer]'
        );
        for (var i = 0; i < controls.length; i++) {
            controls[i].setAttribute('data-chapter-index', chapterIndex);
        }
    }

    function refreshPartialChapterCanvas(chapterIndex) {
        if (
            window.EpubBrowserAICanvas &&
            typeof window.EpubBrowserAICanvas.refresh === 'function'
        ) {
            window.EpubBrowserAICanvas.refresh(chapterIndex);
        }
    }

    function syncChapterContentAttributes(source) {
        var attributes = [
            'lang', 'data-eb-styles', 'data-chapter-index', 'data-chapter-title',
            'data-book-hash', 'data-total-chapters'
        ];
        for (var i = 0; i < attributes.length; i++) {
            var name = attributes[i];
            if (source.hasAttribute(name)) content.setAttribute(name, source.getAttribute(name));
            else content.removeAttribute(name);
        }
    }

    function scrollToChapterTarget(target) {
        window.requestAnimationFrame(function() {
            var anchor = null;
            if (target.hash) {
                var anchorId = decodeURIComponent(target.hash.substring(1));
                var anchors = content.querySelectorAll('[id]');
                for (var i = 0; i < anchors.length; i++) {
                    if (anchors[i].id === anchorId) {
                        anchor = anchors[i];
                        break;
                    }
                }
            }
            content.setAttribute('tabindex', '-1');
            content.focus({ preventScroll: true });
            if (anchor) anchor.scrollIntoView({ behavior: 'auto', block: 'start' });
            else window.scrollTo(0, 0);
        });
    }

    function refreshChapterAnnotations(target, continuous) {
        if (!window.AnnotationModule) return;
        window.AnnotationModule.init({
            bookHash: book_hash,
            chapterIndex: target.index
        }).then(function() {
            if (continuous) return refreshContinuousAnnotations();
            return focusRequestedAnnotation(true);
        }).catch(function() {
            showNotification(i18n.t('reader.annotationLoadFailed'), 'warning');
        });
    }

    function refreshNormalScrollChapter(target) {
        wrapAllElements('table', 'div', content);
        wrapAllElements('img', 'div', content);
        prepareChapterCodeBlocks(content);
        if (!isKindleMode() && typeof hljs !== 'undefined') hljs.highlightAll();
        if (typeof Fancybox !== 'undefined') Fancybox.bind('#eb-content img', {});
        generateToc();
        updateTocHighlight();
        setBookTocActiveChapter(target.index, true);
        selectReadingChapter(target.index);
        var readKey = 'eb_ci_' + target.index + (target.hash || '');
        if (!isKindleMode()) localStorage.setItem(book_hash, readKey);
        else setCookie(book_hash, readKey);
        refreshChapterAnnotations(target, false);
        scrollToChapterTarget(target);
    }

    function announceReadingSessionChapter(chapterIndex, chapterLabel) {
        if (!window.CustomEvent || !window.dispatchEvent) return;
        window.dispatchEvent(new CustomEvent('epub-browser:chapter-change', {
            detail: { chapterIndex: chapterIndex, chapterLabel: chapterLabel || '' }
        }));
    }

    function replaceReaderChapterContent(chapterContent, source, target) {
        if (window.AnnotationModule && typeof window.AnnotationModule.closeTransient === 'function') {
            window.AnnotationModule.closeTransient();
        }
        dispatchChapterContentLifecycle('removed', content);
        while (content.firstChild) content.removeChild(content.firstChild);
        var childNodes = chapterContent.childNodes;
        for (var i = 0; i < childNodes.length; i++) {
            content.appendChild(childNodes[i].cloneNode(true));
        }
        syncChapterContentAttributes(chapterContent);
        dispatchChapterContentLifecycle('added', content);
        syncChapterNavigationLinks(source);
        var pageTitle = source.querySelector('title');
        if (pageTitle) document.title = pageTitle.textContent;
        chapter_index = String(target.index);
        visibleChapterIndex = target.index;
        pendingAnnotationId = requestedAnnotationId();
        syncChapterScopedControls(target.index);
        refreshPartialChapterCanvas(target.index);
        announceReadingSessionChapter(
            target.index,
            content.getAttribute('data-chapter-title') || ''
        );
    }

    function updateReaderChapterHistory(target, options) {
        if (options.history !== false) {
            window.history.pushState({chapterIndex: target.index}, '', target.url);
        } else {
            window.history.replaceState({chapterIndex: target.index}, '', target.url);
        }
    }

    function navigateReaderChapter(url, options) {
        options = options || {};
        var target = chapterTargetFromUrl(url);
        if (!target || (!isContinuousScroll && target.index === parseInt(chapter_index, 10))) return false;
        closeReaderDrawers(false);
        if (isContinuousScroll) {
            var loadedChapter = content.querySelector(
                '.continuous-chapter[data-chapter-index="' + target.index + '"]'
            );
            if (loadedChapter) {
                activeReaderChapterRequest += 1;
                if (readerChapterXhr) readerChapterXhr.abort();
                readerChapterXhr = null;
                updateReaderChapterHistory(target, options);
                visibleChapterIndex = target.index;
                selectReadingChapter(target.index);
                setBookTocActiveChapter(target.index, true);
                if (!isKindleMode()) localStorage.setItem(book_hash, 'eb_ci_' + target.index + (target.hash || ''));
                else setCookie(book_hash, 'eb_ci_' + target.index + (target.hash || ''));
                announceReadingSessionChapter(
                    target.index,
                    loadedChapter.getAttribute('data-chapter-title') || ''
                );
                scrollToContinuousChapterTarget(target, loadedChapter);
                return true;
            }
        }
        activeReaderChapterRequest += 1;
        var requestId = activeReaderChapterRequest;
        if (readerChapterXhr) readerChapterXhr.abort();
        var xhr = new XMLHttpRequest();
        readerChapterXhr = xhr;
        xhr.open('GET', url, true);
        xhr.onload = function() {
            if (requestId !== activeReaderChapterRequest) return;
            readerChapterXhr = null;
            if (xhr.status < 200 || xhr.status >= 300) {
                showNotification(i18n.t('reader.chapterLoadFailed'), 'warning');
                return;
            }
            var tempDiv = document.createElement('div');
            tempDiv.innerHTML = xhr.responseText;
            var chapterContent = tempDiv.querySelector('#eb-content');
            if (
                !chapterContent ||
                parseInt(chapterContent.getAttribute('data-chapter-index'), 10) !== target.index ||
                chapterContent.getAttribute('data-book-hash') !== content.getAttribute('data-book-hash')
            ) {
                showNotification(i18n.t('reader.chapterLoadFailed'), 'warning');
                return;
            }
            updateReaderChapterHistory(target, options);
            if (isContinuousScroll) {
                replaceContinuousChapterWindow(target, chapterContent, tempDiv);
            } else {
                replaceReaderChapterContent(chapterContent, tempDiv, target);
                if (isPaginationMode) refreshPaginationChapter(target);
                else refreshNormalScrollChapter(target);
            }
        };
        xhr.onerror = function() {
            if (requestId !== activeReaderChapterRequest) return;
            readerChapterXhr = null;
            showNotification(i18n.t('reader.chapterLoadFailed'), 'warning');
        };
        xhr.send();
        return true;
    }

    function wireReaderChapterNavigation() {
        var links = document.querySelectorAll(
            '.prev-chapter, .next-chapter, .mobile-controls > a'
        );
        for (var i = 0; i < links.length; i++) {
            links[i].addEventListener('click', function(event) {
                if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
                if (!isDifferentScrollingChapter(this.href)) return;
                event.preventDefault();
                navigateReaderChapter(this.href, { history: true });
            });
        }
    }

    window.addEventListener('popstate', function() {
        navigateReaderChapter(window.location.href, { history: false });
    });
    wireReaderChapterNavigation();
    
    function handleKeyDown(e) {
        if (isKindleMode()) return;
        if (
            !window.EpubReaderLayout ||
            !window.EpubReaderLayout.allowsReaderNavigationEvent(
                e,
                arrowKeyNavigationEnabled,
                spaceKeyNavigationEnabled
            )
        ) return;
        if (isPaginationMode) {
            switch(e.key) {
                case 'ArrowLeft':
                    e.preventDefault();
                    if (currentPage>0) showPage(currentPage-1, true);
                    else {
                        var prev = document.querySelector(".prev-chapter").href;
                        if (prev === location.href) showNotification(i18n.t('reader.firstChapter'), 'warning');
                        else navigateReaderChapter(prev, { history: true });
                    }
                    break;
                case ' ':
                case 'Space':
                case 'ArrowRight':
                    e.preventDefault();
                    if (currentPage < totalPages-1) showPage(currentPage+1, true);
                    else {
                        var next = document.querySelector(".next-chapter").href;
                        if (next === location.href) showNotification(i18n.t('reader.lastChapter'), 'warning');
                        else navigateReaderChapter(next, { history: true });
                    }
                    break;
            }
        } else {
            switch(e.key) {
                case 'ArrowLeft':
                    e.preventDefault();
                    // 连续滚动模式下，用浏览器前进/后退替代跳转
                    if (isContinuousScroll) {
                        window.history.back();
                    } else {
                        var prev = document.querySelector(".prev-chapter").href;
                        if (prev === location.href) showNotification(i18n.t('reader.first'), 'warning');
                        else navigateReaderChapter(prev, { history: true });
                    }
                    break;
                case ' ':
                case 'ArrowDown':
                case 'Space':
                    var sh = document.documentElement.scrollHeight;
                    var ch = document.documentElement.clientHeight;
                    var st = document.documentElement.scrollTop || document.body.scrollTop;
                    if (st+ch < sh) break;
                case 'ArrowRight':
                    e.preventDefault();
                    // 连续滚动模式下，滚动到底部时用浏览器前进替代跳转
                    if (isContinuousScroll) {
                        window.history.forward();
                    } else {
                        var next = document.querySelector(".next-chapter").href;
                        if (next === location.href) showNotification(i18n.t('reader.last'), 'warning');
                        else navigateReaderChapter(next, { history: true });
                    }
                    break;
            }
        }
    }

    prevPageBtn.addEventListener('click', function() {
        if (currentPage>0) showPage(currentPage-1, true);
        else {
            var prev = document.querySelector(".prev-chapter").href;
            if (prev === location.href) showNotification(i18n.t('reader.first'), 'warning');
            else navigateReaderChapter(prev, { history: true });
        }
    });
    
    nextPageBtn.addEventListener('click', function() {
        if (currentPage < totalPages-1) showPage(currentPage+1, true);
        else {
            var next = document.querySelector(".next-chapter").href;
            if (next === location.href) showNotification(i18n.t('reader.last'), 'warning');
            else navigateReaderChapter(next, { history: true });
        }
    });

    function handleClickPage(e) {
        if (!isClickPageEnabled || !isPaginationMode) return;
        var t = e.target;
        var interactive = false;
        var tn = t.tagName.toLowerCase();
        if (tn === 'a' || tn === 'button' || tn === 'input' || tn === 'textarea' || tn === 'select' || tn === 'img') interactive = true;
        else if (t.closest('a') || t.closest('button') || t.closest('input') || t.closest('textarea') || t.closest('select')) interactive = true;
        else if (t.closest('.navigation') || t.closest('.settings-modal') || t.closest('.reading-controls') || t.closest('.toc-container') || t.closest('.fancybox__container') || t.closest('.top-controls') || t.closest('.mobile-controls')) interactive = true;
        if (interactive) return;
        
        var w = window.innerWidth;
        var l = w*0.3;
        var r = w*0.7;
        if (e.clientX < l) {
            e.preventDefault();
            prevPageBtn.click();
        } else if (e.clientX > r) {
            e.preventDefault();
            nextPageBtn.click();
        }
    }
    
    function initClickPageState() {
        if (!isKindleMode()) {
            if (window.epubBrowserCache && window.epubBrowserCache.clickPageEnabled) {
                isClickPageEnabled = window.epubBrowserCache.clickPageEnabled === 'true';
            } else {
                isClickPageEnabled = localStorage.getItem('clickPageEnabled') === 'true';
                if (localStorage.getItem('clickPageEnabled')) {
                    if (!window.epubBrowserCache) window.epubBrowserCache = {};
                    window.epubBrowserCache.clickPageEnabled = localStorage.getItem('clickPageEnabled');
                }
            }
        } else {
            isClickPageEnabled = getCookie('clickPageEnabled') === 'true';
        }
        updateClickPageButton();
        if (isKindleMode() && getCookie('clickPageEnabled') === null) {
            isClickPageEnabled = true;
            saveClickPageState();
            updateClickPageButton();
        }
        if (isMobile() && localStorage.getItem('clickPageEnabled') === null) {
            isClickPageEnabled = true;
            saveClickPageState();
            updateClickPageButton();
        }
    }
    
    function saveClickPageState() {
        if (!isKindleMode()) localStorage.setItem('clickPageEnabled', isClickPageEnabled.toString());
        else setCookie('clickPageEnabled', isClickPageEnabled.toString());
        if (!window.epubBrowserCache) window.epubBrowserCache = {};
        window.epubBrowserCache.clickPageEnabled = isClickPageEnabled.toString();
    }
    
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
    
    initClickPageState();
    document.body.addEventListener('click', handleClickPage);
    
    var isPureModeEnabled = false;
    var togglePureModeBtn = document.getElementById('togglePureMode');
    
    function initPureModeState() {
        if (!isKindleMode()) {
            if (window.epubBrowserCache && window.epubBrowserCache.pureModeEnabled) {
                isPureModeEnabled = window.epubBrowserCache.pureModeEnabled === 'true';
            } else {
                isPureModeEnabled = localStorage.getItem('pureModeEnabled') === 'true';
                if (localStorage.getItem('pureModeEnabled')) {
                    if (!window.epubBrowserCache) window.epubBrowserCache = {};
                    window.epubBrowserCache.pureModeEnabled = localStorage.getItem('pureModeEnabled');
                }
            }
        } else {
            isPureModeEnabled = getCookie('pureModeEnabled') === 'true';
        }
        updatePureModeButton();
        var nav = document.querySelector('.navigation');
        var cc = document.querySelector('.eb-content-container');
        var eb = document.getElementById('eb-content');
        if (isPureModeEnabled && isPaginationMode) {
            nav.style.display = 'none';
            if (isMobile()) {
                var mc = document.querySelector('.mobile-controls');
                if (mc) mc.style.display = 'none';
            } else {
                var topc = document.querySelector('.top-controls');
                var rc = document.querySelector('.reading-controls');
                if (topc) topc.style.display = 'none';
                if (rc) rc.style.display = 'none';
            }
            cc.style.marginTop = '0';
            cc.style.marginBottom = '0';
            eb.style.minHeight = 'calc(100vh - 80px)';
        } else {
            nav.style.display = 'flex';
            if (isMobile()) {
                var mc = document.querySelector('.mobile-controls');
                if (mc) mc.style.display = '';
            } else {
                var topc = document.querySelector('.top-controls');
                var rc = document.querySelector('.reading-controls');
                if (topc) topc.style.display = '';
                if (rc) rc.style.display = '';
            }
            cc.style.marginTop = '';
            cc.style.marginBottom = '';
            eb.style.minHeight = '';
        }
    }
    
    function savePureModeState() {
        if (!isKindleMode()) localStorage.setItem('pureModeEnabled', isPureModeEnabled.toString());
        else setCookie('pureModeEnabled', isPureModeEnabled.toString());
        if (!window.epubBrowserCache) window.epubBrowserCache = {};
        window.epubBrowserCache.pureModeEnabled = isPureModeEnabled.toString();
    }
    
    function togglePureMode() {
        if (!isPaginationMode) {
            showNotification(i18n.t('reader.onlyPageMode'), 'info');
            return;
        }
        isPureModeEnabled = !isPureModeEnabled;
        savePureModeState();
        updatePureModeButton();
        var nav = document.querySelector('.navigation');
        var cc = document.querySelector('.eb-content-container');
        var eb = document.getElementById('eb-content');
        if (isPureModeEnabled) {
            nav.style.display = 'none';
            if (isMobile()) {
                var mc = document.querySelector('.mobile-controls');
                if (mc) mc.style.display = 'none';
            } else {
                var topc = document.querySelector('.top-controls');
                var rc = document.querySelector('.reading-controls');
                if (topc) topc.style.display = 'none';
                if (rc) rc.style.display = 'none';
            }
            cc.style.marginTop = '0';
            cc.style.marginBottom = '0';
            eb.style.minHeight = 'calc(100vh - 80px)';
            showNotification(i18n.t('reader.pureModeOn'), 'info');
        } else {
            nav.style.display = 'flex';
            if (isMobile()) {
                var mc = document.querySelector('.mobile-controls');
                if (mc) mc.style.display = '';
            } else {
                var topc = document.querySelector('.top-controls');
                var rc = document.querySelector('.reading-controls');
                if (topc) topc.style.display = '';
                if (rc) rc.style.display = '';
            }
            cc.style.marginTop = '';
            cc.style.marginBottom = '';
            eb.style.minHeight = '';
            showNotification(i18n.t('reader.pureModeOff'), 'info');
        }
    }
    
    function updatePureModeButton() {
        if (!togglePureModeBtn) return;
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
    
    function isMobile() {
        return window.innerWidth <= 768 || /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent);
    }
    
    document.getElementById('eb-content').addEventListener('click', function(e) {
        var t = e.target;
        var img = t.tagName.toLowerCase() === 'img' || t.closest('img') || t.closest('.fancybox__container');
        if (img) return;
        var rect = e.currentTarget.getBoundingClientRect();
        var cx = rect.left + rect.width/2;
        var cy = rect.top + rect.height/2;
        var w = rect.width*0.3;
        var h = rect.height*0.3;
        if (Math.abs(e.clientX - cx) < w && Math.abs(e.clientY - cy) < h) {
            if (isPaginationMode) {
                if (isMobile()) togglePureMode();
                else if (isPureModeEnabled) togglePureMode();
            }
        }
    });
    
    if (togglePureModeBtn) {
        togglePureModeBtn.addEventListener('click', togglePureMode);
    }

    var reloadPagesBtn = document.getElementById('reloadPages');
    if (reloadPagesBtn) {
        reloadPagesBtn.addEventListener('click', function() {
            if (isPaginationMode) {
                showLoading();
                var save = currentPage;
                setTimeout(function() {
                    createPages();
                    setTimeout(function() {
                        showPage(save);
                        hideLoading();
                        showNotification(i18n.t('reader.reloaded'), 'info');
                    }, 500);
                }, 200);
            } else {
                showNotification(i18n.t('reader.onlyPageMode'), 'info');
            }
        });
    }

    initPureModeState();
    
    toggleClickPageBtn.addEventListener('click', function() {
        isClickPageEnabled = !isClickPageEnabled;
        saveClickPageState();
        updateClickPageButton();
        showNotification(i18n.t(isClickPageEnabled ? 'reader.clickPageOn' : 'reader.clickPageOff'), 'info');
    });
    
    function customCssFunc() {
        if (isKindleMode()) return;
        var cssInput = document.getElementById('customCssInput');
        var saveBtn = document.getElementById('saveCssBtn');
        var saveDefaultBtn = document.getElementById('saveAsDefaultBtn');
        var resetBtn = document.getElementById('resetCssBtn');
        var previewBtn = document.getElementById('previewCssBtn');
        var loadDefaultBtn = document.getElementById('loadDefaultBtn');
        var key = 'custom_css_' + book_hash;
        var defKey = 'custom_css_default';
        
        function load() {
            var saved = localStorage.getItem(key);
            if (saved) {
                cssInput.value = saved;
                apply(saved);
                return;
            }
            var def = localStorage.getItem(defKey);
            if (def) {
                cssInput.value = def;
                apply(def);
            }
        }
        
        function apply(css) {
            var old = document.getElementById('custom-user-css');
            if (old) old.remove();
            if (css.trim()) {
                var s = document.createElement('style');
                s.id = 'custom-user-css';
                s.textContent = css;
                document.head.appendChild(s);
            }
        }
        
        saveBtn.addEventListener('click', function() {
            var v = cssInput.value;
            localStorage.setItem(key, v);
            apply(v);
            showNotification(i18n.t('settings.saved'), 'success');
        });
        
        saveDefaultBtn.addEventListener('click', async function() {
            if (await window.EpubDialog.confirm({
                title: i18n.t('settings.saveAsDefault'),
                message: i18n.t('settings.saveAsDefaultConfirm'),
                confirmText: i18n.t('settings.saveAsDefault')
            })) {
                localStorage.setItem(defKey, cssInput.value);
                showNotification(i18n.t('settings.defaultSaved'), 'success');
            }
        });
        
        loadDefaultBtn.addEventListener('click', async function() {
            var d = localStorage.getItem(defKey);
            if (!d) {
                showNotification(i18n.t('settings.noDefault'), 'warning');
                return;
            }
            if (await window.EpubDialog.confirm({
                title: i18n.t('settings.loadDefault'),
                message: i18n.t('settings.loadDefaultConfirm'),
                confirmText: i18n.t('settings.loadDefault')
            })) {
                cssInput.value = d;
                apply(d);
                showNotification(i18n.t('settings.loaded'), 'success');
            }
        });
        
        resetBtn.addEventListener('click', async function() {
            if (await window.EpubDialog.confirm({
                title: i18n.t('settings.reset'),
                message: i18n.t('settings.resetConfirm'),
                confirmText: i18n.t('settings.reset'),
                destructive: true
            })) {
                cssInput.value = '';
                localStorage.removeItem(key);
                apply('');
                var d = localStorage.getItem(defKey);
                if (d) {
                    cssInput.value = d;
                    apply(d);
                }
                showNotification(i18n.t('settings.resetDone'), 'info');
            }
        });
        
        previewBtn.addEventListener('click', function() {
            apply(cssInput.value);
            showNotification(i18n.t('settings.applied'), 'info');
        });
        
        load();
    }
    
    customCssFunc();
    
    if (!isPaginationMode) {
        setTimeout(function() {
            hideLoading();
        }, 500);
    }
    
    loadBookHomeToc();
    
    function loadBookHomeToc() {
        var list = document.getElementById('bookHomeTocList');
        var path = window.location.pathname;
        var hash = path.split('/book/')[1].split('/')[0];
        var url = window.EpubBrowserURL.publicPath('/book/' + hash + '/toc.json');
        
        var xhr = new XMLHttpRequest();
        xhr.open('GET', url, true);
        xhr.onload = function() {
            if (xhr.status >= 200 && xhr.status < 300) {
                var data = JSON.parse(xhr.responseText);
                list.innerHTML = '';
                for (var i = 0; i < data.length; i++) {
                    var item = data[i];
                    var li = document.createElement('li');
                    li.className = 'toc-item toc-level-' + Math.min(item.level, 3);
                    if (item.kind === 'section') {
                        li.classList.add('toc-section');
                        var sectionTitle = document.createElement('span');
                        sectionTitle.className = 'chapter-section-title';
                        sectionTitle.textContent = item.title;
                        li.appendChild(sectionTitle);
                        list.appendChild(li);
                        continue;
                    }
                    li.setAttribute('data-chapter-index', item.chapter_index);
                    var a = document.createElement('a');
                    var href = window.EpubBrowserURL.publicPath('/book/' + hash + '/' + item.chapter_file);
                    if (item.anchor) href += '#' + item.anchor;
                    a.href = href;
                    a.setAttribute('data-chapter-index', item.chapter_index);
                    var title = document.createElement('span');
                    title.className = 'chapter-title';
                    title.textContent = item.title;
                    a.appendChild(title);
                    a.addEventListener('click', function(e) {
                        if (!isContinuousScroll && isDifferentScrollingChapter(this.href)) {
                            e.preventDefault();
                            navigateReaderChapter(this.href, { history: true });
                            return;
                        }
                        if (isContinuousScroll) {
                            e.preventDefault();
                            navigateReaderChapter(this.href, { history: true });
                            return;
                        }
                        if (!isDifferentScrollingChapter(this.href)) return;
                        e.preventDefault();
                        navigateReaderChapter(this.href, { history: true });
                    });
                    li.appendChild(a);
                    list.appendChild(li);
                }
                // ai-reading-hub may have loaded before this asynchronous TOC.
                // Notify it explicitly as well as allowing its observer fallback.
                if (window.EpubBrowserAIReadingHub && window.EpubBrowserAIReadingHub.refreshChapterIndicators) {
                    window.EpubBrowserAIReadingHub.refreshChapterIndicators(list);
                }
                document.dispatchEvent(new CustomEvent('epub-browser:chapter-toc-loaded', { detail: { container: list } }));
                setBookTocActiveChapter(visibleChapterIndex, true);
            } else {
                list.innerHTML = '<li class="toc-item"></li>';
                list.firstChild.textContent = i18n.t('reader.tocLoadFailed');
            }
        };
        xhr.onerror = function() {
            list.innerHTML = '<li class="toc-item"></li>';
            list.firstChild.textContent = i18n.t('reader.tocLoadFailed');
        };
        xhr.send();
    }

    function setBookTocActiveChapter(index, keepVisible, focusLink) {
        var list = document.getElementById('bookHomeTocList');
        if (!list) return;
        var active = list.querySelector('.toc-item[data-chapter-index="' + index + '"]');
        if (!active) return;
        list.querySelectorAll('.toc-item.active').forEach(function(item) {
            item.classList.remove('active');
            var link = item.querySelector('a');
            if (link) link.removeAttribute('aria-current');
        });
        active.classList.add('active');
        var activeLink = active.querySelector('a');
        if (activeLink) {
            activeLink.setAttribute('aria-current', 'location');
        }
        if (keepVisible !== false) {
            var itemTop = active.offsetTop;
            var itemBottom = itemTop + active.offsetHeight;
            if (itemTop < list.scrollTop || itemBottom > list.scrollTop + list.clientHeight) {
                list.scrollTop = Math.max(0, itemTop - list.clientHeight / 2);
            }
        }
        if (focusLink && activeLink && typeof activeLink.focus === 'function') {
            try {
                activeLink.focus({ preventScroll: true });
            } catch (error) {
                activeLink.focus();
            }
        }
    }
    
    function prepareChapterCodeBlocks(root) {
        var pres = (root || document).querySelectorAll('pre');
        for (var i = 0; i < pres.length; i++) {
            var p = pres[i];
            if (p.children.length === 0) {
                var c = document.createElement('code');
                c.innerHTML = p.innerHTML;
                p.innerHTML = '';
                p.appendChild(c);
            }
        }
    }

    if (!isKindleMode()) {
        prepareChapterCodeBlocks(content);
        hljs.highlightAll();
    }
    
    function switchCodeTheme(dark) {
        var light = document.querySelector('link[href*="github"][id*="light"]');
        var darkLink = document.querySelector('link[href*="github"][id*="dark"]');
        if (light && darkLink) {
            light.disabled = dark;
            darkLink.disabled = !dark;
        }
    }

    function wrapAllElements(name, wrapper, root) {
        var list = (root || document).querySelectorAll(name);
        var wrapName = name + '-wrapper';
        var count = 0;
        for (var i = 0; i < list.length; i++) {
            var el = list[i];
            if (el.parentElement && el.parentElement.classList.contains(wrapName)) continue;
            var w = document.createElement(wrapper);
            w.className = wrapName;
            el.parentNode.insertBefore(w, el);
            w.appendChild(el);
            count++;
        }
        return count;
    }
    wrapAllElements('table', 'div');
    wrapAllElements('img', 'div');

    var readingProgressReporter = null;
    if (!isKindleMode() && window.EpubReadingProgress && window.EpubReadingProgress.isServerMode()) {
        readingProgressReporter = new window.EpubReadingProgress.ChapterReporter(function(index, keepalive) {
            return window.EpubReadingProgress.request(
                'PUT', '/api/reading-progress/' + encodeURIComponent(book_hash), index, keepalive
            );
        });
    }

    function selectReadingChapter(index) {
        if (readingProgressReporter && !isNaN(index)) readingProgressReporter.select(index);
    }

    var readKey = "eb_ci_" + chapter_index;
    if (window.location.hash !== '') readKey += window.location.hash;
    if (!isKindleMode()) localStorage.setItem(book_hash, readKey);
    else setCookie(book_hash, readKey);
    selectReadingChapter(parseInt(chapter_index, 10));

    if (window.initTheme) window.initTheme();
    
    var progressBar = document.getElementById('progressBar');
    
    var progressScrollPending = false;
    function scheduleProgressUpdate() {
        if (progressScrollPending) return;
        progressScrollPending = true;
        window.requestAnimationFrame(function() {
            progressScrollPending = false;
        var wh = window.innerHeight;
        var dh = document.documentElement.scrollHeight - wh;
        var st = window.pageYOffset || document.documentElement.scrollTop;
        var pct = (st/dh)*100;
        if (!document.body.classList.contains('pagination-mode')) {
            progressBar.style.width = pct + '%';
        }
        if (!isKindleMode() && !document.body.classList.contains('pagination-mode')) {
            // 连续滚动模式下不保存滚动进度（章节位置通过 URL 记录）
            if (!isContinuousScroll) {
                var k = getStorageKey("scroll");
                localStorage.setItem(k, window.scrollY);
            }
        }
        updateTocHighlight();
        if (isContinuousScroll) updateContinuousReadingChapter();
        
        // 连续滚动模式：检测是否滚动到底部或顶部
        if (isContinuousScroll && !isLoadingChapter && !isPaginationMode) {
            var contentBottom = content.getBoundingClientRect().bottom + window.scrollY;
            var scrollBottom = contentBottom - (st + wh);
            // 距离底部 300px 时预加载下一章
            if (scrollBottom < 300) {
                loadNextChapter();
            }
            // 跟踪用户向下滚过的最远位置
            if (st > maxScrollTopSoFar) {
                maxScrollTopSoFar = st;
            }
            // 只有用户已经向下滚过至少 300px 后再回滚到顶部附近，才加载上一章
            // 避免刚进入页面时轻微滚动就触发 loadPrevChapter 导致位置跳变
            if (st < 100 && maxScrollTopSoFar >= 300) {
                loadPrevChapter();
            }
        }
        });
    }
    window.addEventListener('scroll', scheduleProgressUpdate, { passive: true });

    window.addEventListener('pagehide', function() {
        if (readingProgressReporter) readingProgressReporter.flush(true);
    });
    
    var tocToggle = document.getElementById('tocToggle');
    var bookHomeToggle = document.getElementById('bookHomeToggle');
    var tocFloating = document.getElementById('tocFloating');
    var bookHomeFloating = document.getElementById('bookHomeFloating');
    var mobileTocBtn = document.getElementById('mobileTocBtn');
    var mobileBookHomeBtn = document.getElementById('mobileBookHomeBtn');
    var tocClose = document.getElementById('tocClose');
    var bookHomeClose = document.getElementById('bookHomeClose');
    var bookHomeLocateCurrent = document.getElementById('bookHomeLocateCurrent');
    var tocList = document.getElementById('tocList');
    var readerDrawerBackdrop = document.getElementById('readerDrawerBackdrop');
    var readerDrawerOpener = null;
    var readerDrawerEntries = [];
    
    generateToc();
    
    function tocFloatingScrolling() {
        var active = document.querySelector('.toc-list li.active');
        var list = document.getElementById('tocList');
        if (active) list.scrollTop = active.offsetTop - 150;
    }

    function bookHomeFloatingScrolling() {
        setBookTocActiveChapter(visibleChapterIndex, true);
    }

    function isPersistentBookDrawer(panel) {
        return panel === bookHomeFloating &&
            document.body.classList.contains('desktop-chapter-sidebar') &&
            window.innerWidth >= 1360;
    }

    function registerReaderDrawer(options) {
        options = options || {};
        if (!options.panel || !options.toggle) return null;
        var entry = {
            panel: options.panel,
            toggle: options.toggle,
            mobileToggle: options.mobileToggle || null,
            afterOpen: options.afterOpen || function() {},
            onClose: options.onClose || function() {}
        };
        readerDrawerEntries.push(entry);
        return {
            open: function(opener) {
                openReaderDrawer(entry.panel, entry.toggle, entry.mobileToggle, entry.afterOpen, opener || entry.toggle);
            },
            close: function(restoreFocus) {
                closeReaderDrawers(restoreFocus);
            }
        };
    }

    registerReaderDrawer({
        panel: tocFloating,
        toggle: tocToggle,
        mobileToggle: mobileTocBtn,
        afterOpen: tocFloatingScrolling
    });
    registerReaderDrawer({
        panel: bookHomeFloating,
        toggle: bookHomeToggle,
        mobileToggle: mobileBookHomeBtn,
        afterOpen: bookHomeFloatingScrolling
    });

    function closeReaderDrawers(restoreFocus) {
        readerDrawerEntries.forEach(function(entry) {
            var wasActive = entry.panel.classList.contains('active');
            entry.panel.classList.remove('active');
            entry.panel.setAttribute('aria-hidden', isPersistentBookDrawer(entry.panel) ? 'false' : 'true');
            if (wasActive) entry.onClose();
        });
        readerDrawerEntries.forEach(function(entry) {
            entry.toggle.setAttribute('aria-expanded', 'false');
        });
        readerDrawerEntries.forEach(function(entry) {
            if (entry.mobileToggle) entry.mobileToggle.classList.remove('active');
        });
        document.body.classList.remove('reader-drawer-open');
        readerDrawerBackdrop.classList.remove('is-active');
        readerDrawerBackdrop.setAttribute('aria-hidden', 'true');
        if (restoreFocus && readerDrawerOpener) readerDrawerOpener.focus();
        readerDrawerOpener = null;
    }

    function openReaderDrawer(panel, toggle, mobileToggle, afterOpen, opener) {
        if ((toggle && toggle.disabled) || (opener && opener.disabled)) return;
        if (isPersistentBookDrawer(panel)) {
            afterOpen();
            return;
        }
        if (panel.classList.contains('active')) {
            closeReaderDrawers(true);
            return;
        }
        closeReaderDrawers(false);
        readerDrawerOpener = opener || toggle;
        panel.classList.add('active');
        panel.setAttribute('aria-hidden', 'false');
        toggle.setAttribute('aria-expanded', 'true');
        if (mobileToggle) mobileToggle.classList.add('active');
        document.body.classList.add('reader-drawer-open');
        readerDrawerBackdrop.classList.add('is-active');
        readerDrawerBackdrop.setAttribute('aria-hidden', 'false');
        afterOpen();
        window.requestAnimationFrame(function() {
            var closeButton = panel.querySelector('.toc-close');
            if (closeButton) closeButton.focus();
        });
    }

    if (window.EpubReaderLayout) {
        window.EpubReaderLayout.syncChapterTocAvailability(document, isContinuousScroll);
    }

    tocToggle.addEventListener('click', function() {
        openReaderDrawer(tocFloating, tocToggle, mobileTocBtn, tocFloatingScrolling, tocToggle);
    });
    bookHomeToggle.addEventListener('click', function() {
        openReaderDrawer(bookHomeFloating, bookHomeToggle, mobileBookHomeBtn, bookHomeFloatingScrolling, bookHomeToggle);
    });
    mobileTocBtn.addEventListener('click', function() {
        openReaderDrawer(tocFloating, tocToggle, mobileTocBtn, tocFloatingScrolling, mobileTocBtn);
    });
    mobileBookHomeBtn.addEventListener('click', function() {
        openReaderDrawer(bookHomeFloating, bookHomeToggle, mobileBookHomeBtn, bookHomeFloatingScrolling, mobileBookHomeBtn);
    });
    tocClose.addEventListener('click', function() {
        closeReaderDrawers(true);
    });
    bookHomeClose.addEventListener('click', function() {
        closeReaderDrawers(true);
    });
    if (bookHomeLocateCurrent) {
        bookHomeLocateCurrent.addEventListener('click', function() {
            setBookTocActiveChapter(visibleChapterIndex, true, true);
        });
    }
    readerDrawerBackdrop.addEventListener('click', function() {
        closeReaderDrawers(true);
    });
    document.addEventListener('keydown', function(event) {
        if (event.key === 'Escape' && document.body.classList.contains('reader-drawer-open')) {
            closeReaderDrawers(true);
        }
    });
    window.EpubReaderDrawers = {
        register: registerReaderDrawer,
        close: closeReaderDrawers
    };
    if (typeof window.CustomEvent === 'function') {
        window.dispatchEvent(new CustomEvent('epub-browser:reader-drawers-ready'));
    }
    
    function generateToc() {
        var c = document.getElementById('eb-content');
        var heads = c.querySelectorAll('h2, h3, h4');
        tocList.innerHTML = '';
        if (heads.length === 0) {
            tocList.innerHTML = '<li class="toc-item"></li>';
            tocList.firstChild.textContent = i18n.t('reader.tocNoTitle');
            return;
        }
        for (var i = 0; i < heads.length; i++) {
            var h = heads[i];
            if (!h.id) h.id = 'heading-' + i;
            var li = document.createElement('li');
            var level = h.tagName.charAt(1);
            li.className = 'toc-item toc-level-' + (level-1);
            var a = document.createElement('a');
            a.href = '#' + h.id;
            a.textContent = h.textContent;
            a.addEventListener('click', function(e) {
                e.preventDefault();
                var t = document.getElementById(this.hash.substring(1));
                if (!t) return;
                if (isPaginationMode) {
                    var page = Math.floor(t.offsetLeft / pageWidth);
                    showPage(page, true);
                } else {
                    window.scrollTo({top: t.offsetTop-100, behavior:'smooth'});
                }
                closeReaderDrawers(false);
            });
            li.appendChild(a);
            tocList.appendChild(li);
        }
    }
    
    function updateTocHighlight() {
        if (isPaginationMode) return;
        var c = document.getElementById('eb-content');
        var heads = c.querySelectorAll('h2, h3, h4');
        var items = document.querySelectorAll('#tocFloating .toc-item');
        var pos = window.scrollY + 150;
        var id = '';
        for (var i = heads.length-1; i >=0; i--) {
            var h = heads[i];
            if (h.offsetTop <= pos) {
                id = h.id;
                break;
            }
        }
        items.forEach(function(it) { it.classList.remove('active'); });
        items.forEach(function(it) {
            var a = it.querySelector('a');
            if (a && a.getAttribute('href') === '#' + id) it.classList.add('active');
        });
        tocFloatingScrolling();
    }
    
    var scrollTopBtn = document.getElementById('scrollToTopBtn');
    var mobileTopBtn = document.getElementById('mobileTopBtn');
    if (scrollTopBtn) {
        scrollTopBtn.addEventListener('click', function() {
            window.scrollTo(0,0);
        });
    }
    function updateScrollToTopVisibility() {
        // Continuous-scroll setup runs before this block is reached. Resolve
        // lazily so its first visibility update cannot abort reader startup.
        if (!scrollTopBtn) scrollTopBtn = document.getElementById('scrollToTopBtn');
        if (!mobileTopBtn) mobileTopBtn = document.getElementById('mobileTopBtn');
        var scrollTop = window.pageYOffset || document.documentElement.scrollTop || 0;
        var threshold = Math.max(320, (window.innerHeight || 0) * 0.75);
        if (scrollTop > threshold && !document.body.classList.contains('pagination-mode') && !isContinuousScroll) {
            if (scrollTopBtn) scrollTopBtn.classList.add('is-visible');
            if (mobileTopBtn) mobileTopBtn.classList.add('is-visible');
        } else {
            if (scrollTopBtn) scrollTopBtn.classList.remove('is-visible');
            if (mobileTopBtn) mobileTopBtn.classList.remove('is-visible');
        }
    }
    var scrollToTopVisibilityPending = false;
    function scheduleScrollToTopVisibility() {
        if (scrollToTopVisibilityPending) return;
        scrollToTopVisibilityPending = true;
        window.requestAnimationFrame(function() {
            scrollToTopVisibilityPending = false;
            updateScrollToTopVisibility();
        });
    }
    window.addEventListener('scroll', scheduleScrollToTopVisibility, { passive: true });
    updateScrollToTopVisibility();
    if (mobileTopBtn) {
        mobileTopBtn.addEventListener('click', function() {
            window.scrollTo(0,0);
        });
    }
    
    var lastScrollTop = 0;
    var mobileControls = document.querySelector('.mobile-controls');
    if (!isKindleMode() && !document.body.classList.contains('pagination-mode')) {
        var mobileControlsScrollPending = false;
        function scheduleMobileControlsVisibility() {
            if (mobileControlsScrollPending) return;
            mobileControlsScrollPending = true;
            window.requestAnimationFrame(function() {
                mobileControlsScrollPending = false;
            var st = window.pageYOffset || document.documentElement.scrollTop;
            if (st > lastScrollTop && st - lastScrollTop > 1) {
                mobileControls.style.transform = 'translateY(100%)';
            } else if (st < lastScrollTop && lastScrollTop - st > 1) {
                mobileControls.style.transform = 'translateY(0)';
            }
            lastScrollTop = st;
            });
        }
        window.addEventListener('scroll', scheduleMobileControlsVisibility, { passive: true });
    } else {
        mobileControls.style.transform = 'translateY(0)';
    }

    Fancybox.bind('#eb-content img', {
        // Your custom options
    });

    var settingsControlBtn = document.getElementById('settingsControlBtn');
    var mobileSettingsBtn = document.getElementById('mobileSettingsBtn');
    var settingsModal = document.getElementById('settingsModal');
    var settingsOverlay = document.getElementById('settingsOverlay');
    var settingsCloseBtn = document.getElementById('settingsCloseBtn');
    var fontSizeBtns = document.querySelectorAll('.font-size-btn');
    var fontFamilySelect = document.getElementById('fontFamilySelect');
    var customFontInput = document.getElementById('customFontInput');
    var applyFontSettings = document.getElementById('applyFontSettings');
    var settingsTabs = document.querySelectorAll('.settings-tab');
    var settingsOpener = null;

    fontFamilySelect.addEventListener('change', function() {
        if (this.value === 'custom') {
            customFontInput.style.display = 'flex';
        } else {
            customFontInput.style.display = 'none';
            updateFontFamily(this.value, null);
            if (!isKindleMode()) localStorage.setItem('font_family', this.value);
            else setCookie('font_family', this.value);
        }
    });

    applyFontSettings.addEventListener('click', function() {
        var custom = document.getElementById('customFontFamily');
        var f = custom.value ? "'" + custom.value + "', sans-serif" : "system-ui, -apple-system, sans-serif";
        if (f === "system-ui, -apple-system, sans-serif") {
            updateFontFamily(f, null);
            if (!isKindleMode()) {
                localStorage.setItem('font_family', f);
                localStorage.removeItem('font_family_input');
            } else {
                setCookie('font_family', f);
                setCookie('font_family_input', '');
            }
        } else {
            updateFontFamily("custom", f);
            if (!isKindleMode()) {
                localStorage.setItem('font_family', "custom");
                localStorage.setItem('font_family_input', f);
            } else {
                setCookie('font_family', "custom");
                setCookie('font_family_input', f);
            }
        }
    });
    
    function showSettingsModal(opener) {
        closeReaderDrawers(false);
        settingsOpener = opener;
        settingsModal.classList.add('show');
        settingsModal.setAttribute('aria-hidden', 'false');
        settingsOverlay.classList.add('show');
        settingsOverlay.setAttribute('aria-hidden', 'false');
        settingsControlBtn.setAttribute('aria-expanded', 'true');
        mobileSettingsBtn.setAttribute('aria-expanded', 'true');
        document.body.classList.add('reader-drawer-open');
        window.requestAnimationFrame(function() {
            settingsCloseBtn.focus();
        });
    }

    function hideSettingsModal(restoreFocus) {
        settingsModal.classList.remove('show');
        settingsModal.setAttribute('aria-hidden', 'true');
        settingsOverlay.classList.remove('show');
        settingsOverlay.setAttribute('aria-hidden', 'true');
        settingsControlBtn.setAttribute('aria-expanded', 'false');
        mobileSettingsBtn.setAttribute('aria-expanded', 'false');
        document.body.classList.remove('reader-drawer-open');
        if (restoreFocus && settingsOpener) settingsOpener.focus();
        settingsOpener = null;
    }

    settingsControlBtn.addEventListener('click', function() {
        showSettingsModal(settingsControlBtn);
    });
    mobileSettingsBtn.addEventListener('click', function() {
        showSettingsModal(mobileSettingsBtn);
    });

    settingsOverlay.addEventListener('click', function() {
        hideSettingsModal(true);
    });

    settingsCloseBtn.addEventListener('click', function() {
        hideSettingsModal(true);
    });

    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape' && settingsModal.classList.contains('show')) {
            hideSettingsModal(true);
        }
    });

    settingsTabs.forEach(function(tab) {
        tab.addEventListener('click', function() {
            var tabId = this.getAttribute('data-tab');
            
            settingsTabs.forEach(function(t) {
                t.classList.remove('active');
            });
            this.classList.add('active');
            
            document.querySelectorAll('.settings-tab-panel').forEach(function(panel) {
                panel.classList.remove('active');
            });
            document.getElementById(tabId + '-tab').classList.add('active');
        });
    });

    function updateFontSize(size) {
        var slider = document.getElementById('fontSizeSlider');
        if (slider) {
            slider.value = size;
        }
        content.classList.remove('font-size-1', 'font-size-2', 'font-size-3', 'font-size-4', 'font-size-5', 'font-size-6', 'font-size-7');
        content.classList.add('font-size-' + size);
        document.dispatchEvent(new CustomEvent('epub:reader-typography-change'));
    }

    function updatePageWidth(preset, reflowPagination) {
        if (!window.EpubReaderLayout) return;
        pageWidthPreset = window.EpubReaderLayout.applyPageWidth(
            document.documentElement,
            preset
        );
        var labels = {
            '1': 'settings.pageWidthNarrow',
            '2': 'settings.pageWidthComfortable',
            '3': 'settings.pageWidthWide',
            '4': 'settings.pageWidthExtraWide'
        };
        var translatedLabel = i18n.t(labels[pageWidthPreset]);
        var slider = document.getElementById('pageWidthSlider');
        if (slider) {
            slider.value = pageWidthPreset;
            slider.setAttribute('aria-valuetext', translatedLabel);
        }
        if (reflowPagination && isPaginationMode) {
            window.requestAnimationFrame(function() {
                calculateTotalPages();
                showPage(Math.min(currentPage, totalPages - 1));
            });
        }
    }

    var fontSizeSlider = document.getElementById('fontSizeSlider');
    if (fontSizeSlider) {
        fontSizeSlider.addEventListener('input', function() {
            var s = this.value;
            if (!isKindleMode()) localStorage.setItem('font_size', s);
            else setCookie('font_size', s);
            updateFontSize(s);
        });
    }

    var pageWidthSlider = document.getElementById('pageWidthSlider');
    if (pageWidthSlider) {
        pageWidthSlider.addEventListener('input', function() {
            pageWidthPreset = window.EpubReaderLayout.normalizePageWidth(this.value);
            setReadingPreference('page_width', pageWidthPreset);
            if (!window.epubBrowserCache) window.epubBrowserCache = {};
            window.epubBrowserCache.page_width = pageWidthPreset;
            updatePageWidth(pageWidthPreset, true);
        });
    }
    
    var style = document.createElement('style');
    style.textContent = `
        .font-size-1 { font-size: 0.9rem; }
        .font-size-2 { font-size: 1.1rem; }
        .font-size-3 { font-size: 1.3rem; }
        .font-size-4 { font-size: 1.5rem; }
        .font-size-5 { font-size: 1.7rem; }
        .font-size-6 { font-size: 1.9rem; }
        .font-size-7 { font-size: 2.2rem; }
    `;
    document.head.appendChild(style);

    window.addEventListener('load', function() {
        document.body.focus();
    });

    function bookshelfSupport() {
        if (!initializeChapterBookshelf()) {
            setTimeout(bookshelfSupport, 100);
        }
    }

    if (!isKindleMode()) {
        bookshelfSupport();
    }
    
    // Initialize annotation module
    function requestedAnnotationId() {
        var match = window.location.search.match(/[?&]annotation=([^&]*)/);
        return match ? decodeURIComponent(match[1].replace(/\+/g, ' ')) : '';
    }
    var pendingAnnotationId = requestedAnnotationId();
    function focusRequestedAnnotation(showWarning) {
        if (!pendingAnnotationId || !window.AnnotationModule) return Promise.resolve(false);
        var annotationId = pendingAnnotationId;
        return window.AnnotationModule.focusAnnotation(annotationId).then(function(found) {
            if (found) {
                pendingAnnotationId = '';
            } else if (showWarning) {
                showNotification(i18n.t('reader.annotationNotFound'), 'warning');
            }
            return found;
        });
    }
    function refreshContinuousAnnotations() {
        if (!window.AnnotationModule || !window.AnnotationModule.initialized) return Promise.resolve();
        return window.AnnotationModule.refresh().then(function() {
            return focusRequestedAnnotation(false);
        });
    }
    function initAnnotationModule() {
        if (window.AnnotationModule) {
            window.AnnotationModule.init({
                bookHash: book_hash,
                chapterIndex: parseInt(chapter_index, 10)
            }).then(function() {
                return focusRequestedAnnotation(!isContinuousScroll);
            }).catch(function() {
                if (pendingAnnotationId && !isContinuousScroll) {
                    showNotification(i18n.t('reader.annotationLoadFailed'), 'warning');
                }
            });
        } else {
            // Wait for annotation.js to load
            setTimeout(initAnnotationModule, 100);
        }
    }
    initAnnotationModule();

    // ==================== 连续滚动模式 ====================

    function initContinuousScroll() {
        document.body.classList.add('continuous-scroll-mode');
        updateScrollToTopVisibility();
        // 标记当前章节已加载
        var currentIdx = parseInt(chapter_index, 10);
        var initialSection = document.createElement('section');
        initialSection.className = 'continuous-chapter';
        initialSection.setAttribute('data-chapter-index', currentIdx);
        initialSection.setAttribute('data-chapter-title', content.getAttribute('data-chapter-title') || '');
        while (content.firstChild) initialSection.appendChild(content.firstChild);
        content.appendChild(initialSection);
        loadedChapters[currentIdx] = true;
        continuousChapterWindow = new EpubChapterWindow(currentIdx, 5);
        loadNextChapter();
        setTimeout(function() {
            if (!isLoadingChapter && Object.keys(loadedChapters).length === 1) loadNextChapter();
        }, 2000);
    }

    function abortContinuousChapterLoad() {
        activeContinuousChapterRequest += 1;
        if (continuousChapterXhr) continuousChapterXhr.abort();
        continuousChapterXhr = null;
        isLoadingChapter = false;
        var loaders = content.querySelectorAll('.continuous-scroll-loader');
        for (var i = 0; i < loaders.length; i++) loaders[i].remove();
    }

    function scrollToContinuousChapterTarget(target, chapterSection) {
        window.scrollTo(0, 0);
        window.requestAnimationFrame(function() {
            var destination = chapterSection;
            if (target.hash) {
                var anchorId = decodeURIComponent(target.hash.substring(1));
                var anchors = chapterSection.querySelectorAll('[id]');
                for (var i = 0; i < anchors.length; i++) {
                    if (anchors[i].id === anchorId) {
                        destination = anchors[i];
                        break;
                    }
                }
            }
            var top = destination.getBoundingClientRect().top + window.scrollY - 80;
            window.scrollTo({top: Math.max(0, top), behavior: 'auto'});
        });
    }

    function replaceContinuousChapterWindow(target, chapterContent, source) {
        abortContinuousChapterLoad();
        if (window.AnnotationModule && typeof window.AnnotationModule.closeTransient === 'function') {
            window.AnnotationModule.closeTransient();
        }
        dispatchChapterContentLifecycle('removed', content);
        while (content.firstChild) content.removeChild(content.firstChild);
        syncChapterContentAttributes(chapterContent);
        syncChapterNavigationLinks(source);
        var pageTitle = source.querySelector('title');
        if (pageTitle) document.title = pageTitle.textContent;
        chapter_index = String(target.index);
        visibleChapterIndex = target.index;
        pendingAnnotationId = requestedAnnotationId();
        syncChapterScopedControls(target.index);
        refreshPartialChapterCanvas(target.index);

        announceReadingSessionChapter(
            target.index,
            content.getAttribute('data-chapter-title') || ''
        );

        var chapterSection = document.createElement('section');
        chapterSection.className = 'continuous-chapter';
        chapterSection.setAttribute('data-chapter-index', target.index);
        chapterSection.setAttribute('data-chapter-title', content.getAttribute('data-chapter-title') || '');
        var childNodes = chapterContent.childNodes;
        for (var i = 0; i < childNodes.length; i++) {
            chapterSection.appendChild(childNodes[i].cloneNode(true));
        }
        content.appendChild(chapterSection);
        dispatchChapterContentLifecycle('added', chapterSection);
        if (typeof Fancybox !== 'undefined') {
            Fancybox.bind('#eb-content img', {});
        }
        loadedChapters = {};
        loadedChapters[target.index] = true;
        continuousChapterWindow = new EpubChapterWindow(target.index, 5);
        maxScrollTopSoFar = 0;
        setBookTocActiveChapter(target.index, true);
        selectReadingChapter(target.index);
        if (!isKindleMode()) localStorage.setItem(book_hash, 'eb_ci_' + target.index + (target.hash || ''));
        else setCookie(book_hash, 'eb_ci_' + target.index + (target.hash || ''));
        refreshChapterAnnotations(target, true);
        scrollToContinuousChapterTarget(target, chapterSection);
        loadNextChapter();
    }

    function ensureContinuousScrollBuffer() {
        if (!isContinuousScroll || isLoadingChapter) return;
        var contentBottom = content.getBoundingClientRect().bottom + window.scrollY;
        var needsMore = typeof EpubContinuousBuffer !== 'undefined'
            ? EpubContinuousBuffer.needsMoreContinuousContent(contentBottom, window.scrollY, window.innerHeight)
            : contentBottom - (window.scrollY + window.innerHeight) < window.innerHeight * 2;
        if (needsMore) {
            loadNextChapter();
        }
    }

    function pruneContinuousWindow(direction, index) {
        var change = continuousChapterWindow.add(index, direction);
        change.evicted.forEach(function(index) {
            var chapter = content.querySelector('.continuous-chapter[data-chapter-index="' + index + '"]');
            if (!chapter) return;
            dispatchChapterContentLifecycle('removed', chapter);
            chapter.remove();
            delete loadedChapters[index];
        });
    }
    
    function updateContinuousScrollUrl(chapterIdx) {
        var newUrl = window.EpubBrowserURL.publicPath('/book/' + book_hash + '/chapter_' + chapterIdx + '.html');
        if (window.location.pathname !== newUrl) {
            try {
                window.history.replaceState({chapterIndex: chapterIdx}, '', newUrl);
            } catch(e) {}
        }
    }

    function updateContinuousReadingChapter() {
        var elements = content.querySelectorAll('.continuous-chapter');
        var sections = [];
        for (var i = 0; i < elements.length; i++) {
            var bounds = elements[i].getBoundingClientRect();
            sections.push({
                index: parseInt(elements[i].getAttribute('data-chapter-index'), 10),
                top: bounds.top,
                bottom: bounds.bottom
            });
        }
        var currentIdx = window.EpubReadingProgress
            ? window.EpubReadingProgress.activeChapter(sections, window.innerHeight / 2)
            : NaN;
        if (isNaN(currentIdx)) return;
        if (currentIdx === visibleChapterIndex) return;
        visibleChapterIndex = currentIdx;
        var currentSection = content.querySelector(
            '.continuous-chapter[data-chapter-index="' + currentIdx + '"]'
        );
        announceReadingSessionChapter(
            currentIdx,
            currentSection && currentSection.getAttribute('data-chapter-title') || ''
        );
        localStorage.setItem(book_hash, 'eb_ci_' + currentIdx);
        updateContinuousScrollUrl(currentIdx);
        selectReadingChapter(currentIdx);
        setBookTocActiveChapter(currentIdx, true);
    }
    
    function getChapterUrl(idx) {
        return window.EpubBrowserURL.publicPath('/book/' + book_hash + '/chapter_' + idx + '.html');
    }
    
    function loadNextChapter() {
        var currentIdx = parseInt(chapter_index, 10);
        var totalChapters = parseInt(content.getAttribute('data-total-chapters'), 10) || 999;
        var nextIdx = currentIdx + 1;
        
        // 找到最后已加载章节的下一章
        var maxLoaded = currentIdx;
        for (var key in loadedChapters) {
            if (loadedChapters.hasOwnProperty(key)) {
                var k = parseInt(key, 10);
                if (k > maxLoaded) maxLoaded = k;
            }
        }
        nextIdx = maxLoaded + 1;
        
        if (nextIdx >= totalChapters || loadedChapters[nextIdx]) return;
        
        isLoadingChapter = true;
        
        // 在内容末尾插入加载指示器
        var loader = document.createElement('div');
        loader.className = 'continuous-scroll-loader';
        loader.id = 'scrollLoader';
        loader.innerHTML = '<span class="chapter-loading-label"></span><span class="loading-dot"></span><span class="loading-dot"></span><span class="loading-dot"></span>';
        loader.querySelector('.chapter-loading-label').textContent = i18n.t('reader.loadingNextChapter');
        content.appendChild(loader);
        
        var xhr = new XMLHttpRequest();
        activeContinuousChapterRequest += 1;
        var requestId = activeContinuousChapterRequest;
        continuousChapterXhr = xhr;
        xhr.open('GET', getChapterUrl(nextIdx), true);
        xhr.onload = function() {
            if (requestId !== activeContinuousChapterRequest) return;
            continuousChapterXhr = null;
            var appendedChapter = false;
            if (xhr.status >= 200 && xhr.status < 300) {
                // 从返回的 HTML 中提取正文内容
                var html = xhr.responseText;
                var tempDiv = document.createElement('div');
                tempDiv.innerHTML = html;
                var chapterContent = tempDiv.querySelector('#eb-content');
                
                // 移除加载指示器
                var loaderEl = document.getElementById('scrollLoader');
                if (loaderEl) loaderEl.remove();
                
                if (chapterContent) {
                    // 提取章节标题
                    var chapterTitle = chapterContent.getAttribute('data-chapter-title') || '';
                    if (!chapterTitle) {
                        var pageTitle = tempDiv.querySelector('title');
                        if (pageTitle) {
                            chapterTitle = pageTitle.textContent.split(' - ')[0].trim();
                        }
                    }
                    
                    // 添加章节分隔符和可淘汰的章节容器
                    var chapterSection = document.createElement('section');
                    chapterSection.className = 'continuous-chapter';
                    chapterSection.setAttribute('data-chapter-index', nextIdx);
                    chapterSection.setAttribute('data-chapter-title', chapterTitle || '');
                    var separator = document.createElement('div');
                    separator.className = 'chapter-separator';
                    separator.innerHTML = '<div class="chapter-sep-title"></div><div class="chapter-sep-index"></div>';
                    separator.querySelector('.chapter-sep-title').textContent = chapterTitle || i18n.t('reader.chapterNumber', { number: nextIdx });
                    separator.querySelector('.chapter-sep-index').textContent = i18n.t('reader.chapterNumber', { number: nextIdx });
                    chapterSection.appendChild(separator);
                    
                    // 追加章节内容
                    var childNodes = chapterContent.childNodes;
                    for (var i = 0; i < childNodes.length; i++) {
                        chapterSection.appendChild(childNodes[i].cloneNode(true));
                    }
                    var viewportAnchor = EpubViewportAnchor.capture(content);
                    content.appendChild(chapterSection);
                    dispatchChapterContentLifecycle('added', chapterSection);
                    
                    loadedChapters[nextIdx] = true;
                    pruneContinuousWindow('next', nextIdx);
                    EpubViewportAnchor.restoreAfterLayout(viewportAnchor);
                    EpubViewportAnchor.restoreOnImageLoad(viewportAnchor, chapterSection);
                    appendedChapter = true;
                    
                    // 对新增内容重新绑定 Fancybox
                    if (typeof Fancybox !== 'undefined') {
                        Fancybox.bind('#eb-content img', {});
                    }
                }
            }
            isLoadingChapter = false;
            if (appendedChapter) {
                refreshContinuousAnnotations();
                ensureContinuousScrollBuffer();
            }
        };
        xhr.onerror = function() {
            if (requestId !== activeContinuousChapterRequest) return;
            continuousChapterXhr = null;
            var loaderEl = document.getElementById('scrollLoader');
            if (loaderEl) loaderEl.remove();
            isLoadingChapter = false;
        };
        xhr.send();
    }
    
    function loadPrevChapter() {
        var currentIdx = parseInt(chapter_index, 10);
        
        // 找到最先已加载章节的前一章
        var minLoaded = currentIdx;
        for (var key in loadedChapters) {
            if (loadedChapters.hasOwnProperty(key)) {
                var k = parseInt(key, 10);
                if (k < minLoaded) minLoaded = k;
            }
        }
        var prevIdx = minLoaded - 1;
        
        if (prevIdx < 0 || loadedChapters[prevIdx]) return;
        
        isLoadingChapter = true;
        
        // 在内容顶部插入加载指示器
        var loader = document.createElement('div');
        loader.className = 'continuous-scroll-loader';
        loader.id = 'scrollLoaderTop';
        loader.innerHTML = '<span class="chapter-loading-label"></span><span class="loading-dot"></span><span class="loading-dot"></span><span class="loading-dot"></span>';
        loader.querySelector('.chapter-loading-label').textContent = i18n.t('reader.loadingPreviousChapter');
        if (content.firstChild) {
            content.insertBefore(loader, content.firstChild);
        } else {
            content.appendChild(loader);
        }
        
        var xhr = new XMLHttpRequest();
        activeContinuousChapterRequest += 1;
        var requestId = activeContinuousChapterRequest;
        continuousChapterXhr = xhr;
        xhr.open('GET', getChapterUrl(prevIdx), true);
        xhr.onload = function() {
            if (requestId !== activeContinuousChapterRequest) return;
            continuousChapterXhr = null;
            var appendedChapter = false;
            if (xhr.status >= 200 && xhr.status < 300) {
                var html = xhr.responseText;
                var tempDiv = document.createElement('div');
                tempDiv.innerHTML = html;
                var chapterContent = tempDiv.querySelector('#eb-content');
                
                var loaderEl = document.getElementById('scrollLoaderTop');
                if (loaderEl) loaderEl.remove();
                
                if (chapterContent) {
                    var chapterTitle = chapterContent.getAttribute('data-chapter-title') || '';
                    if (!chapterTitle) {
                        var pageTitle = tempDiv.querySelector('title');
                        if (pageTitle) {
                            chapterTitle = pageTitle.textContent.split(' - ')[0].trim();
                        }
                    }
                    
                    // 创建可淘汰的章节容器
                    var chapterSection = document.createElement('section');
                    chapterSection.className = 'continuous-chapter';
                    chapterSection.setAttribute('data-chapter-index', prevIdx);
                    chapterSection.setAttribute('data-chapter-title', chapterTitle || '');
                    
                    // 章节分隔符放在新内容的末尾
                    var separator = document.createElement('div');
                    separator.className = 'chapter-separator';
                    separator.innerHTML = '<div class="chapter-sep-title"></div><div class="chapter-sep-index"></div>';
                    separator.querySelector('.chapter-sep-title').textContent = chapterTitle || i18n.t('reader.chapterNumber', { number: prevIdx });
                    separator.querySelector('.chapter-sep-index').textContent = i18n.t('reader.chapterNumber', { number: prevIdx });
                    
                    var childNodes = chapterContent.childNodes;
                    for (var i = 0; i < childNodes.length; i++) {
                        chapterSection.appendChild(childNodes[i].cloneNode(true));
                    }
                    chapterSection.appendChild(separator);
                    
                    var viewportAnchor = EpubViewportAnchor.capture(content);
                    // 插入到内容最前面
                    if (content.firstChild) {
                        content.insertBefore(chapterSection, content.firstChild);
                    } else {
                        content.appendChild(chapterSection);
                    }
                    dispatchChapterContentLifecycle('added', chapterSection);
                    
                    loadedChapters[prevIdx] = true;
                    pruneContinuousWindow('previous', prevIdx);
                    if (typeof Fancybox !== 'undefined') {
                        Fancybox.bind('#eb-content img', {});
                    }
                    EpubViewportAnchor.restoreAfterLayout(viewportAnchor);
                    EpubViewportAnchor.restoreOnImageLoad(viewportAnchor, chapterSection);
                    appendedChapter = true;
                }
            }
            isLoadingChapter = false;
            if (appendedChapter) refreshContinuousAnnotations();
        };
        xhr.onerror = function() {
            if (requestId !== activeContinuousChapterRequest) return;
            continuousChapterXhr = null;
            var loaderEl = document.getElementById('scrollLoaderTop');
            if (loaderEl) loaderEl.remove();
            isLoadingChapter = false;
        };
        xhr.send();
    }
    
    function saveContinuousScrollProgress() {
        // 保存全局阅读进度：基于已加载的所有章节计算当前阅读百分比
        var totalChapters = parseInt(content.getAttribute('data-total-chapters'), 10);
        if (!totalChapters) return;

        // The OPF spine index is encoded on each loaded chapter.  Never infer
        // it from separator position: continuous reading can prepend chapters
        // and prune the window, so separator order is not chapter_N order.
        updateContinuousReadingChapter();
        var currentVisibleChapter = visibleChapterIndex;
        if (isNaN(currentVisibleChapter)) {
            currentVisibleChapter = parseInt(chapter_index, 10);
        }
        
        var key = 'continuous_' + book_hash;
        localStorage.setItem(key, JSON.stringify({
            scrollY: window.scrollY,
            chapterIndex: currentVisibleChapter,
            timestamp: Date.now()
        }));
    }
    
    function loadContinuousScrollProgress() {
        var key = 'continuous_' + book_hash;
        var saved = localStorage.getItem(key);
        if (saved) {
            try {
                var data = JSON.parse(saved);
                if (data.scrollY > 0) {
                    setTimeout(function() {
                        window.scrollTo(0, data.scrollY);
                        var total = document.documentElement.scrollHeight - window.innerHeight;
                        var pct = Math.round((data.scrollY / total) * 100);
                        showNotification(i18n.t('reader.progressLoadedPercent', { percent: pct }), 'info');
                    }, 1000);
                }
            } catch(e) {}
        }
    }
    
    function escapeHtml(text) {
        var div = document.createElement('div');
        div.appendChild(document.createTextNode(text));
        return div.innerHTML;
    }
    
    // 绑定 continuous scroll toggle 开关
    var continuousScrollToggle = document.getElementById('continuousScrollToggle');
    var continuousScrollTip = document.getElementById('continuousScrollTip');
    var showReadingProgressBarToggle = document.getElementById('showReadingProgressBarToggle');
    var desktopChapterSidebarToggle = document.getElementById('desktopChapterSidebarToggle');
    var arrowKeyNavigationToggle = document.getElementById('arrowKeyNavigationToggle');
    var spaceKeyNavigationToggle = document.getElementById('spaceKeyNavigationToggle');
    if (arrowKeyNavigationToggle) {
        arrowKeyNavigationToggle.checked = arrowKeyNavigationEnabled;
        arrowKeyNavigationToggle.addEventListener('change', function() {
            arrowKeyNavigationEnabled = this.checked;
            setReadingPreference('arrowKeyNavigation', arrowKeyNavigationEnabled ? 'true' : 'false');
        });
    }
    if (spaceKeyNavigationToggle) {
        spaceKeyNavigationToggle.checked = spaceKeyNavigationEnabled;
        spaceKeyNavigationToggle.addEventListener('change', function() {
            spaceKeyNavigationEnabled = this.checked;
            setReadingPreference('spaceKeyNavigation', spaceKeyNavigationEnabled ? 'true' : 'false');
        });
    }
    if (showReadingProgressBarToggle) {
        showReadingProgressBarToggle.checked = showReadingProgressBar;
        showReadingProgressBarToggle.addEventListener('change', function() {
            showReadingProgressBar = this.checked;
            setReadingPreference('showReadingProgressBar', showReadingProgressBar ? 'true' : 'false');
            applyReadingProgressBarVisibility(showReadingProgressBar);
        });
    }
    if (desktopChapterSidebarToggle) {
        desktopChapterSidebarToggle.checked = showDesktopChapterSidebar;
        desktopChapterSidebarToggle.addEventListener('change', function() {
            showDesktopChapterSidebar = this.checked;
            setReadingPreference(
                'desktopChapterSidebar',
                showDesktopChapterSidebar ? 'true' : 'false'
            );
            applyDesktopChapterSidebar();
            if (showDesktopChapterSidebar) setBookTocActiveChapter(visibleChapterIndex, true);
        });
    }
    if (continuousScrollToggle) {
        // 翻页模式下禁用该开关
        if (isPaginationMode) {
            continuousScrollToggle.disabled = true;
            continuousScrollToggle.checked = false;
            if (continuousScrollTip) {
                continuousScrollTip.setAttribute('data-tip', i18n.t('settings.continuousScrollUnavailable'));
            }
        } else {
            continuousScrollToggle.disabled = false;
            continuousScrollToggle.checked = isContinuousScroll;
            if (continuousScrollTip) {
                continuousScrollTip.setAttribute('data-tip', i18n.t('settings.continuousScrollTip'));
            }
        }
        
        continuousScrollToggle.addEventListener('change', function() {
            // 翻页模式下不允许切换
            if (isPaginationMode) {
                this.checked = false;
                showNotification(i18n.t('reader.continuousScrollRequiresScrolling'), 'warning');
                return;
            }
            
            isContinuousScroll = this.checked;
            if (window.EpubReaderLayout) {
                window.EpubReaderLayout.syncChapterTocAvailability(document, isContinuousScroll);
            }
            if (!isKindleMode()) {
                localStorage.setItem('continuousScroll', isContinuousScroll ? 'true' : 'false');
            } else {
                setCookie('continuousScroll', isContinuousScroll ? 'true' : 'false');
            }
            if (!window.epubBrowserCache) window.epubBrowserCache = {};
            window.epubBrowserCache.continuousScroll = isContinuousScroll ? 'true' : 'false';
            
            if (isContinuousScroll) {
                showNotification(i18n.t('reader.continuousScrollEnabledReloading'), 'info');
            } else {
                showNotification(i18n.t('reader.continuousScrollDisabledReloading'), 'info');
            }
            // 重新加载以应用/取消连续滚动模式
            setTimeout(function() { location.reload(); }, 500);
        });
    }
    
    // 连续滚动开关的 hint tooltip（JS 动态创建 append 到 body，避免被 settings-content 的 overflow 裁剪）
    if (continuousScrollTip) {
        var tipTooltip = null;
        continuousScrollTip.addEventListener('mouseenter', function() {
            var tipText = continuousScrollTip.getAttribute('data-tip');
            if (!tipText) return;
            
            tipTooltip = document.createElement('div');
            tipTooltip.className = 'continuous-scroll-tooltip';
            tipTooltip.textContent = tipText;
            document.body.appendChild(tipTooltip);
            
            var iconRect = continuousScrollTip.getBoundingClientRect();
            tipTooltip.style.left = (iconRect.left + iconRect.width / 2) + 'px';
            tipTooltip.style.transform = 'translateX(-50%)';
            tipTooltip.style.bottom = (window.innerHeight - iconRect.top + 8) + 'px';
        });
        continuousScrollTip.addEventListener('mouseleave', function() {
            if (tipTooltip) {
                tipTooltip.remove();
                tipTooltip = null;
            }
        });
    }
}

window.initScriptChapter = initScript;
