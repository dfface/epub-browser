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
    if (fontFamily == "custom") {
        document.body.style.fontFamily = fontFamilyInput;
        customFontInput.style.display = 'flex';
        customFontFamily.value = fontFamilyInput;
    } else {
        document.body.style.fontFamily = fontFamily;
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

function restoreOrder(storageKey, elementClass) {
    var savedOrder = localStorage.getItem(storageKey);
    if (savedOrder) {
        var itemIds = JSON.parse(savedOrder);
        var container = document.querySelector('.' + elementClass);
        
        itemIds.forEach(function(id) {
            var element = document.querySelector('[data-id="' + id + '"]');
            if (element) {
                container.appendChild(element);
            }
        });
    }
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

function initScript() {
    function showLoading() {
        var overlay = document.getElementById('loadingOverlay');
        if (overlay) overlay.style.display = 'flex';
    }
    
    function hideLoading() {
        var overlay = document.getElementById('loadingOverlay');
        if (overlay) overlay.style.display = 'none';
    }

    scopeEBStyles();

    var path = window.location.pathname;
    var pathParts = path.split('/').filter(function(item) { return item !== ''; });
    var book_hash = pathParts[pathParts.indexOf('book') + 1];
    var chapter_index = pathParts[pathParts.indexOf('book') + 2];
    chapter_index = chapter_index.replace("chapter_", "").replace(".html", "");

    var togglePaginationBtn = document.getElementById('togglePagination');
    var mobileTogglePaginationBtn = document.getElementById('mobileTogglePagination');
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
    var pageHeightSetBtn = document.querySelector("#setPageHeight");
    var pageHeightInput = document.querySelector("#pageHeightInput");
    var toggleClickPageBtn = document.getElementById('toggleClickPage');

    function getStorageKey(mode) {
        return mode + '_' + book_hash + '_' + chapter_index;
    }
    
    var isPaginationMode = false;
    var currentPage = 0;
    var totalPages = 0;
    var contentWidth = 0;
    var pageWidth = 0;
    var isClickPageEnabled = false;

    var fontSize = "small";
    var fontFamily = "system-ui, -apple-system, sans-serif";
    var fontFamilyInput = null;
    var supportedFonts = getAvailableFonts();
    
    // 替换箭头函数
    supportedFonts.forEach(function(item) {
        var opt = document.createElement('option');
        opt.value = item;
        opt.textContent = item;
        document.getElementById('fontFamilySelect').appendChild(opt);
    });

    var storageKeySortableContainer = 'chapter-container-sortable-order';

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
        
        if (window.epubBrowserCache && window.epubBrowserCache.font_size) {
            fontSize = window.epubBrowserCache.font_size;
        } else {
            fontSize = localStorage.getItem('font_size') || "small";
            if (fontSize) {
                if (!window.epubBrowserCache) window.epubBrowserCache = {};
                window.epubBrowserCache.font_size = fontSize;
            }
        }
        
        if (window.epubBrowserCache && window.epubBrowserCache.font_family) {
            fontFamily = window.epubBrowserCache.font_family;
        } else {
            fontFamily = localStorage.getItem('font_family') || "system-ui, -apple-system, sans-serif";
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
        
        restoreOrder(storageKeySortableContainer, 'container');
    } else {
        var currentPaginationMode = getCookie('turning') || "false";
        isPaginationMode = currentPaginationMode == "true";
        fontSize = getCookie('font_size') || "small";
        fontFamily = getCookie('font_family') || "system-ui, -apple-system, sans-serif";
        fontFamilyInput = getCookie('font_family_input');
    }
    updateFontSize(fontSize);
    updateFontFamily(fontFamily, fontFamilyInput);

    document.addEventListener('keydown', handleKeyDown);

    var el = document.querySelector('.container');
    if (!isKindleMode()) {
        var sortable = Sortable.create(el, {
            delay: 300,
            delayOnTouchOnly: true,
            filter: '#eb-content, #pageJumpInput, .page-height-adjustment, #customCssInput',
            preventOnFilter: false,
            onStart: function(evt) {
                var sel = window.getSelection();
                if (sel.toString().length > 0) return false;
            },
            onEnd: function(evt) {
                var ids = Array.prototype.map.call(evt.from.children, function(c) {
                    return c.dataset.id;
                });
                localStorage.setItem(storageKeySortableContainer, JSON.stringify(ids));
            }
        });
    }

    document.querySelectorAll('.eb-content').forEach(function(item) {
        item.addEventListener('dblclick', function(e) {
            e.stopPropagation();
        });
    });

    if (isKindleMode() || isPaginationMode) {
        document.querySelector(".custom-css-panel").style.display = "none";
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
        togglePaginationBtn.innerHTML = '<i class="fas fa-scroll"></i><span class="control-name">Scrolling</span>';
        mobileTogglePaginationBtn.innerHTML = '<i class="fas fa-scroll"></i><span class="control-name">Scrolling</span>';
        
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
    }
    
    function savePaginationModeAndReload() {
        isPaginationMode = !isPaginationMode;
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
    
    togglePaginationBtn.addEventListener('click', savePaginationModeAndReload);
    mobileTogglePaginationBtn.addEventListener('click', savePaginationModeAndReload);
    
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
            showNotification('Page turning mode enabled', 'info');
        }
    }

    function toggleHideUnnecessary(hide) {
        var panel = document.querySelector(".custom-css-panel");
        var bread = document.querySelector(".breadcrumb");
        var footer = document.querySelector("footer");
        if (hide) {
            panel.style.display = 'none';
            bread.style.display = 'none';
            footer.style.display = 'none';
        } else {
            panel.style.display = 'inherit';
            bread.style.display = 'inherit';
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
    
    function createPages() {
        showLoading();
        var original = preprocessContent(content);
        var bottomNav = document.querySelector('.navigation');
        var mobileNav = document.querySelector('.mobile-controls');
        var navH = getElementHeight(bottomNav);
        var mobileH = getElementHeight(mobileNav);
        var vh = window.innerHeight;
        var contentH = vh - navH - mobileH - 40;
        contentContainer.style.height = (vh - navH - mobileH) + 'px';
        content.style.height = contentH + 'px';
        content.innerHTML = original;
        
        setTimeout(function() {
            var sh = content.scrollHeight;
            var cols = Math.ceil(sh / contentH);
            content.style.columnCount = cols;
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
            
            setTimeout(function() {
                calculateTotalPages();
                pageJumpInput.setAttribute('max', totalPages);
                setTimeout(function() {
                    hideLoading();
                    if (document.documentElement.mediumZoomInstance) {
                        document.documentElement.mediumZoomInstance.detach();
                    }
                    document.documentElement.mediumZoomInstance = mediumZoom('#eb-content img', {
                        margin: 24,
                        background: '#000',
                        scrollOffset: 0
                    });
                }, 500);
            }, 200);
        }, 200);
    }
    
    function calculateTotalPages() {
        var parent = document.querySelector('.container');
        var w = Math.floor(parent.clientWidth);
        contentContainer.style.width = w + 'px';
        contentContainer.style.flex = '1';
        var nav = document.querySelector('.pagination-mode .navigation');
        if (nav) {
            nav.style.width = w + 'px';
            nav.style.padding = '20px';
            nav.style.boxSizing = 'border-box';
        }
        pageWidth = w;
        content.style.columnWidth = pageWidth + 'px';
        content.style.boxSizing = 'border-box';
        var sw = content.scrollWidth;
        var raw = sw / pageWidth;
        totalPages = Math.max(1, Math.ceil(raw - 0.1));
        totalPagesEl.textContent = totalPages;
        currentPageEl.textContent = currentPage+1;
        pageJumpInput.value = currentPage+1;
    }
    
    function showPage(idx) {
        if (idx < 0) idx = 0;
        if (idx >= totalPages) idx = totalPages-1;
        var pos = Math.floor(idx * pageWidth);
        content.scrollTo(pos, 0);
        currentPage = idx;
        currentPageEl.textContent = idx+1;
        totalPagesEl.textContent = totalPages;
        pageJumpInput.value = idx+1;
        updateProgressIndicator();
        updateNavButtons();
        saveReadingProgress();
        updateTocHighlight();
    }
    
    function updateNavButtons() {
        prevPageBtn.disabled = currentPage === 0;
        nextPageBtn.disabled = currentPage === totalPages-1;
    }

    function updateProgressIndicator() {
        var p = ((currentPage+1)/totalPages)*100;
        progressFill.style.width = p+'%';
    }
    
    function restoreOriginalContent() {
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
        
        if (isKindleMode() || confirm('Exit page turning mode?')) {
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
                    showNotification('Progress loaded: Page '+(pi+1), 'info');
                }
            } else {
                showPage(0);
            }
        } else {
            var key = getStorageKey("scroll");
            var pos = localStorage.getItem(key);
            var wh = window.innerHeight;
            setTimeout(function() {
                if (pos && parseInt(pos) > 0) {
                    window.scrollTo(0, parseInt(pos));
                    var total = document.documentElement.scrollHeight - wh;
                    var pct = Math.round((parseInt(pos)/total)*100);
                    showNotification('Progress loaded: '+pct+'%', 'info');
                }
            }, 1000);
        }
    }

    goToPageBtn.addEventListener('click', function() {
        var n = parseInt(pageJumpInput.value,10);
        if (n >=1 && n <= totalPages) {
            showPage(n-1);
        } else {
            showNotification('1-'+totalPages, 'warning');
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
            showNotification('Valid number', 'warning');
        }
    });
    
    function handleKeyDown(e) {
        if (isKindleMode()) return;
        if (isPaginationMode) {
            switch(e.key) {
                case 'ArrowLeft':
                    e.preventDefault();
                    if (currentPage>0) showPage(currentPage-1);
                    else {
                        var prev = document.querySelector(".prev-chapter").href;
                        if (prev === location.href) showNotification('First chapter', 'warning');
                        else location.href=prev;
                    }
                    break;
                case ' ':
                case 'Space':
                case 'ArrowRight':
                    e.preventDefault();
                    if (currentPage < totalPages-1) showPage(currentPage+1);
                    else {
                        var next = document.querySelector(".next-chapter").href;
                        if (next === location.href) showNotification('Last chapter', 'warning');
                        else location.href=next;
                    }
                    break;
            }
        } else {
            var cssInput = document.getElementById('customCssInput');
            var fontInput = document.getElementById('customFontFamily');
            if (document.activeElement === cssInput || document.activeElement === fontInput) return;
            
            switch(e.key) {
                case 'ArrowLeft':
                    e.preventDefault();
                    var prev = document.querySelector(".prev-chapter").href;
                    if (prev === location.href) showNotification('First', 'warning');
                    else location.href=prev;
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
                    var next = document.querySelector(".next-chapter").href;
                    if (next === location.href) showNotification('Last', 'warning');
                    else location.href=next;
                    break;
            }
        }
    }

    prevPageBtn.addEventListener('click', function() {
        if (currentPage>0) showPage(currentPage-1);
        else {
            var prev = document.querySelector(".prev-chapter").href;
            if (prev === location.href) showNotification('First', 'warning');
            else location.href=prev;
        }
    });
    
    nextPageBtn.addEventListener('click', function() {
        if (currentPage < totalPages-1) showPage(currentPage+1);
        else {
            var next = document.querySelector(".next-chapter").href;
            if (next === location.href) showNotification('Last', 'warning');
            else location.href=next;
        }
    });

    function handleClickPage(e) {
        if (!isClickPageEnabled || !isPaginationMode) return;
        var t = e.target;
        var interactive = false;
        var tn = t.tagName.toLowerCase();
        if (tn === 'a' || tn === 'button' || tn === 'input' || tn === 'textarea' || tn === 'select' || tn === 'img') interactive = true;
        else if (t.closest('a') || t.closest('button') || t.closest('input') || t.closest('textarea') || t.closest('select')) interactive = true;
        else if (t.closest('.navigation') || t.closest('.font-controls') || t.closest('.reading-controls') || t.closest('.toc-container') || t.closest('.medium-zoom-container') || t.closest('.top-controls') || t.closest('.mobile-controls')) interactive = true;
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
                if (mc) mc.style.display = 'flex';
            } else {
                var topc = document.querySelector('.top-controls');
                var rc = document.querySelector('.reading-controls');
                if (topc) topc.style.display = 'flex';
                if (rc) rc.style.display = 'flex';
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
            showNotification('Only in page mode', 'info');
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
            showNotification('Pure mode on', 'info');
        } else {
            nav.style.display = 'flex';
            if (isMobile()) {
                var mc = document.querySelector('.mobile-controls');
                if (mc) mc.style.display = 'flex';
            } else {
                var topc = document.querySelector('.top-controls');
                var rc = document.querySelector('.reading-controls');
                if (topc) topc.style.display = 'flex';
                if (rc) rc.style.display = 'flex';
            }
            cc.style.marginTop = '';
            cc.style.marginBottom = '';
            eb.style.minHeight = '';
            showNotification('Pure mode off', 'info');
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
        var img = t.tagName.toLowerCase() === 'img' || t.closest('img') || t.closest('.medium-zoom-container');
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
                        showNotification('Reloaded', 'info');
                    }, 500);
                }, 200);
            } else {
                showNotification('Only page mode', 'info');
            }
        });
    }

    initPureModeState();
    
    toggleClickPageBtn.addEventListener('click', function() {
        isClickPageEnabled = !isClickPageEnabled;
        saveClickPageState();
        updateClickPageButton();
        showNotification(isClickPageEnabled ? 'Click page on' : 'Click page off', 'info');
    });
    
    function customCssFunc() {
        if (isKindleMode()) return;
        var cssToggle = document.getElementById('cssPanelToggle');
        var cssContent = document.getElementById('cssPanelContent');
        var cssInput = document.getElementById('customCssInput');
        var saveBtn = document.getElementById('saveCssBtn');
        var saveDefaultBtn = document.getElementById('saveAsDefaultBtn');
        var resetBtn = document.getElementById('resetCssBtn');
        var previewBtn = document.getElementById('previewCssBtn');
        var loadDefaultBtn = document.getElementById('loadDefaultBtn');
        var key = 'custom_css_' + book_hash;
        var defKey = 'custom_css_default';
        
        cssToggle.addEventListener('click', function() {
            cssContent.classList.toggle('expanded');
            var icon = cssToggle.querySelector('i');
            if (cssContent.classList.contains('expanded')) {
                icon.classList.remove('fa-chevron-down');
                icon.classList.add('fa-chevron-up');
            } else {
                icon.classList.remove('fa-chevron-up');
                icon.classList.add('fa-chevron-down');
            }
        });
        
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
            showNotification('Saved', 'success');
        });
        
        saveDefaultBtn.addEventListener('click', function() {
            if (confirm('Save as default?')) {
                localStorage.setItem(defKey, cssInput.value);
                showNotification('Default saved', 'success');
            }
        });
        
        loadDefaultBtn.addEventListener('click', function() {
            var d = localStorage.getItem(defKey);
            if (!d) {
                showNotification('No default', 'warning');
                return;
            }
            if (confirm('Load default?')) {
                cssInput.value = d;
                apply(d);
                showNotification('Loaded', 'success');
            }
        });
        
        resetBtn.addEventListener('click', function() {
            if (confirm('Reset?')) {
                cssInput.value = '';
                localStorage.removeItem(key);
                apply('');
                var d = localStorage.getItem(defKey);
                if (d) {
                    cssInput.value = d;
                    apply(d);
                }
                showNotification('Reset', 'info');
            }
        });
        
        previewBtn.addEventListener('click', function() {
            apply(cssInput.value);
            showNotification('Applied', 'info');
        });
        
        load();
    }
    
    customCssFunc();
    
    if (!isPaginationMode) {
        setTimeout(function() {
            hideLoading();
        }, 500);
    }

    function showNotification(msg, type) {
        var old = document.querySelector('.custom-css-notification');
        if (old) old.remove();
        var n = document.createElement('div');
        n.className = 'custom-css-notification ' + type;
        n.textContent = msg;
        document.body.appendChild(n);
        setTimeout(function() {
            n.classList.add('fade-out');
            setTimeout(function() {
                if (n.parentNode) n.parentNode.removeChild(n);
            }, 300);
        }, 3000);
    }
    
    loadBookHomeToc();
    
    function loadBookHomeToc() {
        var list = document.getElementById('bookHomeTocList');
        var path = window.location.pathname;
        var hash = path.split('/book/')[1].split('/')[0];
        var url = '/book/' + hash + '/toc.json';
        
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
                    var a = document.createElement('a');
                    var href = '/book/' + hash + '/' + item.chapter_file;
                    if (item.anchor) href += '#' + item.anchor;
                    a.href = href;
                    a.textContent = item.title;
                    a.addEventListener('click', function(e) {
                        e.preventDefault();
                        window.location.href = this.href;
                    });
                    li.appendChild(a);
                    list.appendChild(li);
                }
                var cur = path.split('/').pop();
                var active = list.querySelector('a[href*="' + cur + '"]');
                if (active) {
                    var p = active.parentElement;
                    p.classList.add('active');
                    list.scrollTop = p.offsetTop - 150;
                }
            } else {
                list.innerHTML = '<li class="toc-item">Load failed</li>';
            }
        };
        xhr.onerror = function() {
            list.innerHTML = '<li class="toc-item">Load failed</li>';
        };
        xhr.send();
    }
    
    if (!isKindleMode()) {
        var pres = document.querySelectorAll('pre');
        for (var i = 0; i < pres.length; i++) {
            var p = pres[i];
            if (p.children.length === 0) {
                var c = document.createElement('code');
                c.innerHTML = p.innerHTML;
                p.innerHTML = '';
                p.appendChild(c);
            }
        }
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

    function wrapAllElements(name, wrapper) {
        var list = document.querySelectorAll(name);
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

    var readKey = "eb_ci_" + chapter_index;
    if (window.location.hash !== '') readKey += window.location.hash;
    if (!isKindleMode()) localStorage.setItem(book_hash, readKey);
    else setCookie(book_hash, readKey);

    if (window.initTheme) window.initTheme();
    
    var progressBar = document.getElementById('progressBar');
    
    window.addEventListener('scroll', function() {
        var wh = window.innerHeight;
        var dh = document.documentElement.scrollHeight - wh;
        var st = window.pageYOffset || document.documentElement.scrollTop;
        var pct = (st/dh)*100;
        if (!document.body.classList.contains('pagination-mode')) {
            progressBar.style.width = pct + '%';
        }
        if (!isKindleMode() && !document.body.classList.contains('pagination-mode')) {
            var k = getStorageKey("scroll");
            localStorage.setItem(k, window.scrollY);
        }
        updateTocHighlight();
    });
    
    var tocToggle = document.getElementById('tocToggle');
    var bookHomeToggle = document.getElementById('bookHomeToggle');
    var tocFloating = document.getElementById('tocFloating');
    var bookHomeFloating = document.getElementById('bookHomeFloating');
    var mobileTocBtn = document.getElementById('mobileTocBtn');
    var mobileBookHomeBtn = document.getElementById('mobileBookHomeBtn');
    var tocClose = document.getElementById('tocClose');
    var bookHomeClose = document.getElementById('bookHomeClose');
    var tocList = document.getElementById('tocList');
    
    generateToc();
    
    function tocFloatingScrolling() {
        var active = document.querySelector('.toc-list li.active');
        var list = document.getElementById('tocList');
        if (active) list.scrollTop = active.offsetTop - 150;
    }

    function bookHomeFloatingScrolling() {
        var list = document.getElementById('bookHomeTocList');
        var cur = window.location.pathname.split('/').pop();
        var a = list.querySelector('a[href*="' + cur + '"]');
        if (a) {
            var li = a.parentElement;
            list.querySelectorAll('.toc-item').forEach(function(i) { i.classList.remove('active'); });
            li.classList.add('active');
            list.scrollTop = li.offsetTop - 150;
        }
    }
    
    tocToggle.addEventListener('click', function() {
        tocFloating.classList.toggle('active');
        tocFloatingScrolling();
    });
    bookHomeToggle.addEventListener('click', function() {
        bookHomeFloating.classList.toggle('active');
        if (bookHomeFloating.classList.contains('active')) bookHomeFloatingScrolling();
    });
    mobileTocBtn.addEventListener('click', function() {
        tocFloating.classList.toggle('active');
        tocFloatingScrolling();
        mobileTocBtn.classList.toggle('active');
    });
    mobileBookHomeBtn.addEventListener('click', function() {
        bookHomeFloating.classList.toggle('active');
        mobileBookHomeBtn.classList.toggle('active');
        if (bookHomeFloating.classList.contains('active')) bookHomeFloatingScrolling();
    });
    tocClose.addEventListener('click', function() {
        tocFloating.classList.remove('active');
        mobileTocBtn.classList.remove('active');
    });
    bookHomeClose.addEventListener('click', function() {
        bookHomeFloating.classList.remove('active');
        mobileBookHomeBtn.classList.remove('active');
    });
    
    function generateToc() {
        var c = document.getElementById('eb-content');
        var heads = c.querySelectorAll('h2, h3, h4');
        if (heads.length === 0) {
            tocList.innerHTML = '<li class="toc-item">no title</li>';
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
                    t.scrollIntoView({behavior:'auto', block:'start'});
                    setTimeout(function() {
                        var sl = content.scrollLeft;
                        var pg = Math.round(sl / pageWidth);
                        currentPage = Math.max(0, Math.min(pg, totalPages-1));
                        currentPageEl.textContent = currentPage+1;
                        pageJumpInput.value = currentPage+1;
                        updateNavButtons();
                        updateProgressIndicator();
                        saveReadingProgress();
                        updateTocHighlight();
                    }, 500);
                } else {
                    window.scrollTo({top: t.offsetTop-100, behavior:'smooth'});
                }
                tocFloating.classList.remove('active');
                if (mobileTocBtn) mobileTocBtn.classList.remove('active');
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
    scrollTopBtn.addEventListener('click', function() {
        window.scrollTo(0,0);
    });
    var mobileTopBtn = document.getElementById('mobileTopBtn');
    mobileTopBtn.addEventListener('click', function() {
        window.scrollTo(0,0);
    });
    
    var lastScrollTop = 0;
    var mobileControls = document.querySelector('.mobile-controls');
    if (!isKindleMode() && !document.body.classList.contains('pagination-mode')) {
        window.addEventListener('scroll', function() {
            var st = window.pageYOffset || document.documentElement.scrollTop;
            if (st > lastScrollTop && st - lastScrollTop > 1) {
                mobileControls.style.transform = 'translateY(100%)';
            } else if (st < lastScrollTop && lastScrollTop - st > 1) {
                mobileControls.style.transform = 'translateY(0)';
            }
            lastScrollTop = st;
        });
    } else {
        mobileControls.style.transform = 'translateY(0)';
    }
    
    if (document.documentElement.mediumZoomInstance) {
        document.documentElement.mediumZoomInstance.detach();
    }
    document.documentElement.mediumZoomInstance = mediumZoom('#eb-content img', {
        margin:24, background:'#000', scrollOffset:0
    });
    
    var fontControlBtn = document.getElementById('fontControlBtn');
    var mobileFontBtn = document.getElementById('mobileFontBtn');
    var fontControls = document.getElementById('fontControls');
    var fontSizeBtns = document.querySelectorAll('.font-size-btn');
    var fontFamilySelect = document.getElementById('fontFamilySelect');
    var customFontInput = document.getElementById('customFontInput');
    var applyFontSettings = document.getElementById('applyFontSettings');

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
        var custom = document.getElementById('customFontFamily');
        var f = custom.value ? "'" + custom.value + "', sans-serif" : "system-ui, -apple-system, sans-serif";
        if (f === "system-ui, -apple-system, sans-serif") {
            updateFontFamily(f, null);
        } else {
            updateFontFamily("custom", f);
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
        var btns = document.querySelectorAll('.font-size-btn');
        btns.forEach(function(b) { b.classList.remove('active'); });
        btns.forEach(function(b) {
            if (b.getAttribute('data-size') === size) b.classList.add('active');
        });
        content.classList.remove('font-small', 'font-medium', 'font-large');
        if (size === 'small') content.classList.add('font-small');
        else if (size === 'medium') content.classList.add('font-medium');
        else if (size === 'large') content.classList.add('font-large');
    }
    
    fontSizeBtns.forEach(function(btn) {
        btn.addEventListener('click', function() {
            var s = this.getAttribute('data-size');
            if (!isKindleMode()) localStorage.setItem('font_size', s);
            else setCookie('font_size', s);
            location.reload();
        });
    });
    
    var style = document.createElement('style');
    style.textContent = `
        .font-small { font-size: 1rem; }
        .font-medium { font-size: 1.5rem; }
        .font-large { font-size: 2rem; }
        img.zoomed { width: 90vw; max-height: 100vh; cursor: zoom-out; }
    `;
    document.head.appendChild(style);

    window.addEventListener('load', function() {
        document.body.focus();
    });
}

window.initScriptChapter = initScript;