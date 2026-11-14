function showNotification(message, type) {
    return window.EpubBrowserNotification.show(message, type);
}

// 设置 cookie
function setCookie(key, value) {
    var date = new Date();
    date.setTime(date.getTime() + 3650 * 24 * 60 * 60 * 1000);
    var expires = "expires=" + date.toUTCString();
    document.cookie = key + "=" + value + ";" + expires + "; path=/; SameSite=Lax";
}

// 解析指定 key 的 Cookie —— Kindle 兼容版
function getCookie(key) {
    var cookies = document.cookie.split('; ');
    // 替换 for...of 为传统 for 循环
    for (var i = 0; i < cookies.length; i++) {
        var cookie = cookies[i];
        // 替换解构赋值
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

function initScript() {
    var i18n = window.EpubBrowserI18n;

    function t(key, params) {
        return i18n ? i18n.t(key, params) : key;
    }

    var sortControl = document.getElementById('libraryBookSort');
    var bookSort = window.EpubBrowserBookSort;
    var serverMode = window.EpubBrowserMode === 'server';
    var bookDrag;
    var bookDragEnabled = false;
    var manualSave = Promise.resolve();
    var manualOrderKey = 'book-grid-sortable-order';

    function selectedSort() {
        return sortControl ? sortControl.value : 'manual';
    }

    function setBookDragEnabled(enabled) {
        bookDragEnabled = enabled;
        if (bookDrag) bookDrag.option('disabled', !enabled);
    }

    function saveServerOrder(ids, legacy) {
        return window.EpubBrowserAuth.fetch('/api/library-order', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ids: ids, legacy: legacy })
        }).then(function(response) {
            if (!response || !response.ok) throw new Error('library_order_save_failed');
        });
    }

    function importLegacyOrder() {
        if (!serverMode || !bookSort || !window.EpubBrowserAuth) return null;
        var ids = bookSort.manualOrder();
        if (!ids.length) return null;
        return saveServerOrder(ids, true).then(function() {
            try { localStorage.removeItem(manualOrderKey); } catch (error) {}
        }, function() {});
    }

    function loadLibraryFeature(name) {
        var features = window.EpubBrowserLibraryFeatures;
        if (!features || typeof features.load !== 'function') {
            return Promise.reject(new Error('library_feature_loader_unavailable'));
        }
        return features.load(name);
    }

    function loadBookMetadata(sort, callback, failureCallback) {
        var basePath = window.EpubBrowserBasePath || "/";
        var metadataUrl = basePath + "book-metadata.json?" + Date.now();
        if (serverMode && sort !== 'manual') metadataUrl += '&sort=' + encodeURIComponent(sort);
        
        var xhr = new XMLHttpRequest();
        xhr.open('GET', metadataUrl, true);
        xhr.onreadystatechange = function() {
            if (xhr.readyState === 4) {
                if (xhr.status === 200) {
                    try {
                        var books = JSON.parse(xhr.responseText);
                        if (!Array.isArray(books)) {
                            throw new Error('Book metadata must be an array');
                        }
                        callback(books);
                    } catch (e) {
                        console.error('Failed to parse book metadata:', e);
                        if (failureCallback) failureCallback(e);
                    }
                } else {
                    console.error('Failed to load book metadata:', xhr.status);
                    if (failureCallback) failureCallback(new Error('Failed to load book metadata: ' + xhr.status));
                }
            }
        };
        xhr.send();
    }

    var metadataActiveRevision = null;
    var metadataQueuedRevision = null;
    var metadataCompletedRevision = -1;
    var metadataWaiters = [];
    var lastMetadataBooks = [];
    var orderedBooks = null;
    var pageBooks = [];
    var currentPage = 1;
    var libraryPageTarget = 24;
    var libraryPageSize = libraryPageTarget;
    var bookGrid = document.querySelector('.book-grid');
    var pager = document.getElementById('libraryPager');
    var previousPage = document.getElementById('libraryPreviousPage');
    var nextPage = document.getElementById('libraryNextPage');
    var pageStatus = document.getElementById('libraryPageStatus');
    var jumpForm = document.getElementById('libraryJumpForm');
    var jumpInput = document.getElementById('libraryJumpInput');

    function settleMetadataWaiters(revision, error, books) {
        var remaining = [];
        metadataWaiters.forEach(function(waiter) {
            if (waiter.revision <= revision) {
                if (error) waiter.reject(error);
                else waiter.resolve(books);
            } else {
                remaining.push(waiter);
            }
        });
        metadataWaiters = remaining;
    }

    function startMetadataRefresh(revision) {
        metadataActiveRevision = revision;
        if (metadataQueuedRevision === revision) metadataQueuedRevision = null;
        var sort = selectedSort();
        loadBookMetadata(sort, function(books) {
            if (!serverMode || sort === selectedSort()) replaceBookCards(books);
            // The continue-reading rail joins server progress against this same
            // catalogue, so it has to re-render whenever the catalogue changes:
            // a conversion can rename a book, replace its cover, or remove it.
            if (window.EpubRecentReading) window.EpubRecentReading.updateBooks(books);
            lastMetadataBooks = books;
            metadataCompletedRevision = Math.max(metadataCompletedRevision, revision);
            metadataActiveRevision = null;
            settleMetadataWaiters(revision, null, books);
            if (metadataQueuedRevision !== null && metadataQueuedRevision > metadataCompletedRevision) {
                var nextRevision = metadataQueuedRevision;
                metadataQueuedRevision = null;
                startMetadataRefresh(nextRevision);
            }
        }, function(error) {
            metadataCompletedRevision = Math.max(metadataCompletedRevision, revision);
            metadataActiveRevision = null;
            settleMetadataWaiters(revision, error);
            if (metadataQueuedRevision !== null && metadataQueuedRevision > metadataCompletedRevision) {
                var nextRevision = metadataQueuedRevision;
                metadataQueuedRevision = null;
                startMetadataRefresh(nextRevision);
            }
        });
    }

    function requestMetadataRefresh(revision) {
        var targetRevision = typeof revision === 'number' && isFinite(revision)
            ? revision
            : Math.max(
                metadataCompletedRevision,
                metadataActiveRevision === null ? -1 : metadataActiveRevision,
                metadataQueuedRevision === null ? -1 : metadataQueuedRevision
            ) + 1;

        if (targetRevision <= metadataCompletedRevision) {
            return Promise.resolve(lastMetadataBooks);
        }
        return new Promise(function(resolve, reject) {
            metadataWaiters.push({ revision: targetRevision, resolve: resolve, reject: reject });
            if (metadataActiveRevision === null) {
                startMetadataRefresh(targetRevision);
            } else if (targetRevision > metadataActiveRevision) {
                metadataQueuedRevision = Math.max(metadataQueuedRevision === null ? -1 : metadataQueuedRevision, targetRevision);
            }
        });
    }
    
    function hideBookGridLoading() {
        var loading = document.getElementById('bookGridLoading');
        if (loading) {
            loading.style.display = 'none';
        }
    }

    function showLibraryState(titleKey, descriptionKey, variant) {
        var bookGrid = document.querySelector('.book-grid');
        var state;
        var icon;
        var iconGlyph;
        var title;
        var description;
        var stateVariant = variant || 'empty';
        if (!bookGrid || bookGrid.querySelector('.library-state--' + stateVariant)) return;
        state = document.createElement('section');
        state.className = 'empty-state library-state library-state--' + stateVariant;
        state.setAttribute('role', 'status');
        icon = document.createElement('span');
        icon.className = 'library-state-icon';
        icon.setAttribute('aria-hidden', 'true');
        iconGlyph = document.createElement('i');
        iconGlyph.className = stateVariant === 'filtered'
            ? 'fas fa-search'
            : 'fas fa-book-open';
        icon.appendChild(iconGlyph);
        title = document.createElement('h2');
        title.setAttribute('data-i18n', titleKey);
        title.textContent = t(titleKey);
        description = document.createElement('p');
        description.setAttribute('data-i18n', descriptionKey);
        description.textContent = t(descriptionKey);
        state.appendChild(icon);
        state.appendChild(title);
        state.appendChild(description);
        bookGrid.appendChild(state);
    }
    
    function removeLibraryCardsAndStates(bookGrid) {
        var children = Array.prototype.slice.call(bookGrid.children);
        children.forEach(function(child) {
            if (child.classList.contains('book-card') || child.classList.contains('library-state')) {
                bookGrid.removeChild(child);
            }
        });
    }

    function createBookCard(book) {
        var card = document.createElement('div');
        var link = document.createElement('a');
        var coverFrame = document.createElement('div');
        var cover = document.createElement('img');
        var content = document.createElement('div');
        var title = document.createElement('h3');
        var author = document.createElement('div');
        card.className = 'book-card';
        card.setAttribute('data-id', book.hash);

        link.className = 'book-link';
        link.setAttribute('id', book.hash);
        link.setAttribute('href', book.url);

        coverFrame.className = 'book-cover-frame';
        if (book.format === 'pdf') coverFrame.classList.add('pdf-cover-frame');
        cover.className = 'book-cover';
        cover.setAttribute('src', book.cover);
        cover.setAttribute('alt', t('library.cover'));
        cover.setAttribute('loading', 'lazy');
        cover.setAttribute('decoding', 'async');
        coverFrame.appendChild(cover);

        content.className = 'book-card-content';
        title.className = 'book-title';
        title.textContent = book.title;
        author.className = 'book-author';
        author.textContent = book.authors && book.authors.length > 0 ? book.authors.join(' & ') : '';

        content.appendChild(title);
        content.appendChild(author);

        if (Number.isInteger(book.rating) && book.rating >= 1 && book.rating <= 5) {
            var rating = document.createElement('span');
            var icon = document.createElement('i');
            var score = document.createElement('span');
            rating.className = 'book-rating-badge';
            rating.setAttribute('role', 'img');
            rating.setAttribute('aria-label', t('bookReviews.ratingValue', { rating: book.rating }));
            icon.className = 'fas fa-star';
            icon.setAttribute('aria-hidden', 'true');
            score.setAttribute('aria-hidden', 'true');
            score.textContent = String(book.rating);
            rating.appendChild(icon);
            rating.appendChild(score);
            coverFrame.appendChild(rating);
        }

        if (book.format === 'pdf') {
            var formatBadge = document.createElement('span');
            formatBadge.className = 'book-format-badge';
            formatBadge.setAttribute('aria-label', t('pdf.formatBadge'));
            formatBadge.textContent = t('pdf.formatBadge');
            coverFrame.appendChild(formatBadge);
        }

        if (book.tags && book.tags.length > 0) {
            var tags = document.createElement('div');
            tags.className = 'book-tags';
            book.tags.forEach(function(tag) {
                var tagElement = document.createElement('span');
                tagElement.className = 'book-tag';
                tagElement.textContent = tag;
                tags.appendChild(tagElement);
            });
            content.appendChild(tags);
        }

        link.appendChild(coverFrame);
        link.appendChild(content);
        card.appendChild(link);
        return card;
    }

    function updateLibraryCounts(books, tagCount) {
        var bookCountElement = document.getElementById('libraryBookCount');
        var tagCountElement = document.getElementById('libraryTagCount');
        if (bookCountElement) {
            bookCountElement.textContent = t('library.bookCount', { count: books.length });
            bookCountElement.setAttribute('data-i18n-params', JSON.stringify({ count: books.length }));
        }
        if (tagCountElement) {
            tagCountElement.textContent = t('library.tagCount', { count: tagCount });
            tagCountElement.setAttribute('data-i18n-params', JSON.stringify({ count: tagCount }));
        }
    }

    function collectTagNames(books) {
        var tags = {};
        books.forEach(function(book) {
            (book.tags || []).forEach(function(tag) {
                if (typeof tag === 'string' && tag.trim()) tags[tag.trim()] = true;
            });
        });
        return Object.keys(tags).sort();
    }

    function rebuildTagItems(tagNames, activeTagId) {
        var tagCloud = document.querySelector('.tag-cloud');
        var tagItems;
        if (!tagCloud) return 0;

        markTagCloudFixed(tagCloud);
        tagItems = Array.prototype.slice.call(tagCloud.querySelectorAll('.tag-cloud-item'));
        tagItems.forEach(function(tagItem) {
            var id = tagItem.getAttribute('data-id');
            if (id !== 'All' && id !== 'NoTag') tagCloud.removeChild(tagItem);
        });

        tagNames.forEach(function(tag) {
            var tagItem = document.createElement('div');
            tagItem.className = 'tag-cloud-item';
            tagItem.setAttribute('data-id', tag);
            tagItem.textContent = tag;
            tagCloud.appendChild(tagItem);
        });

        tagItems = tagCloud.querySelectorAll('.tag-cloud-item');
        var selected = false;
        tagItems.forEach(function(tagItem) {
            var isActive = tagItem.getAttribute('data-id') === activeTagId;
            tagItem.classList.remove('active');
            if (isActive) {
                tagItem.classList.add('active');
                selected = true;
            }
        });
        if (!selected) {
            tagItems.forEach(function(tagItem) {
                if (tagItem.getAttribute('data-id') === 'All') tagItem.classList.add('active');
            });
        }
        return tagNames.length;
    }

    function tagCloudRowCount(tagCloud) {
        var tagItems = tagCloud.querySelectorAll('.tag-cloud-item');
        var rowTops = [];
        var i;
        var top;
        if (!tagItems.length) return 0;
        for (i = 0; i < tagItems.length; i++) {
            top = tagItems[i].offsetTop;
            if (typeof top !== 'number') return 0;
            if (rowTops.indexOf(top) === -1) rowTops.push(top);
        }
        return rowTops.length;
    }

    function setTagCloudToggleLabel(toggle, expanded) {
        var key = expanded ? 'library.showFewerTags' : 'library.showMoreTags';
        toggle.textContent = t(key);
        toggle.setAttribute('data-i18n', key);
        toggle.setAttribute('aria-expanded', expanded ? 'true' : 'false');
    }

    function updateTagCloudCollapse() {
        var tagCloud = document.querySelector('.tag-cloud');
        var toggle = document.getElementById('tagCloudToggle');
        var expanded;
        var overflows;
        if (!tagCloud || !toggle) return;

        expanded = tagCloud.classList.contains('tag-cloud--expanded');
        overflows = tagCloudRowCount(tagCloud) > 2;
        tagCloud.classList.remove('tag-cloud--overflowing');
        tagCloud.classList.remove('tag-cloud--collapsed');
        tagCloud.classList.remove('tag-cloud--expanded');
        toggle.hidden = !overflows;

        if (!overflows) return;

        tagCloud.classList.add('tag-cloud--overflowing');
        tagCloud.classList.add('tag-cloud--collapsed');
        if (expanded) tagCloud.classList.add('tag-cloud--expanded');
        setTagCloudToggleLabel(toggle, expanded);
    }

    function uniqueBooksById(books) {
        var seenIds = {};
        var seenUrls = {};
        return books.filter(function(book) {
            var id = book && book.hash;
            var url = book && book.url;
            var knownId = typeof id === 'string' && id;
            var knownUrl = typeof url === 'string' && url;
            if ((knownId && seenIds[id]) || (knownUrl && seenUrls[url])) return false;
            if (knownId) seenIds[id] = true;
            if (knownUrl) seenUrls[url] = true;
            return true;
        });
    }

    function replaceBookCards(books) {
        var activeTag = document.querySelector('.tag-cloud-item.active');
        var activeTagId = activeTag ? activeTag.getAttribute('data-id') : 'All';
        orderedBooks = uniqueBooksById(books);
        if (!serverMode && bookSort) {
            orderedBooks = bookSort.sortBooks(orderedBooks, selectedSort(), i18n && i18n.getLocale());
        }
        hideBookGridLoading();
        var tagCount = rebuildTagItems(collectTagNames(orderedBooks), activeTagId);
        updateLibraryCounts(orderedBooks, tagCount);
        restoreTagCloudOrder();
        updateTagCloudCollapse();
        applyLibraryFilters();
    }

    // 页面加载时恢复顺序
    function restoreOrder(storageKey, elementClass) {
        var savedOrder = localStorage.getItem(storageKey);
        var itemIds;
        var container;
        var children;
        if (!savedOrder) return;
        try {
            itemIds = JSON.parse(savedOrder);
        } catch (e) {
            return;
        }
        if (!Array.isArray(itemIds)) return;
        container = document.querySelector('.' + elementClass);
        if (!container) return;
        children = Array.prototype.slice.call(container.children);
        itemIds.forEach(function(id) {
            var matchingElement;
            if (typeof id !== 'string') return;
            children.forEach(function(child) {
                if (!matchingElement && child.getAttribute('data-id') === id) matchingElement = child;
            });
            if (matchingElement) container.appendChild(matchingElement);
        });
    }

    // All/NoTag 是固定项，始终保持在标签云最前且不可拖拽
    function markTagCloudFixed(tagCloud) {
        if (!tagCloud) return;
        var items = tagCloud.querySelectorAll('.tag-cloud-item');
        Array.prototype.forEach.call(items, function(item) {
            var id = item.getAttribute('data-id');
            if (id === 'All' || id === 'NoTag') item.classList.add('tag-cloud-item--fixed');
        });
    }

    function pinTagCloudFixedItems(tagCloud) {
        var fixed = { All: null, NoTag: null };
        var movable = [];
        var items;
        if (!tagCloud) return;
        items = tagCloud.querySelectorAll('.tag-cloud-item');
        Array.prototype.forEach.call(items, function(item) {
            var id = item.getAttribute('data-id');
            if (id === 'All' || id === 'NoTag') fixed[id] = item;
            else movable.push(item);
        });
        // 先重排固定项到最前，再按当前顺序追加其余标签
        if (fixed.All) tagCloud.appendChild(fixed.All);
        if (fixed.NoTag) tagCloud.appendChild(fixed.NoTag);
        movable.forEach(function(item) {
            tagCloud.appendChild(item);
        });
    }

    function restoreTagCloudOrder() {
        restoreOrder(storageKeySortableTag, 'tag-cloud');
        pinTagCloudFixedItems(document.querySelector('.tag-cloud'));
    }

    function suppressTagClick() {
        window.__epubBrowserTagDragSuppressClick = true;
        setTimeout(function() {
            window.__epubBrowserTagDragSuppressClick = false;
        }, 150);
    }

    function updateFontFamily(fontFamily, fontFamilyInput) {
        if (fontFamily === "ebook-default") {
            document.body.style.fontFamily = '';
        } else if (fontFamily == "custom") {
            document.body.style.fontFamily = fontFamilyInput;
        } else {
            document.body.style.fontFamily = fontFamily;
        }
    }

    if (i18n && document.documentElement.getAttribute('data-library-locale-listener') !== 'true') {
        document.documentElement.setAttribute('data-library-locale-listener', 'true');
        i18n.onLocaleChange(function() {
            var covers = document.querySelectorAll('.book-cover');
            var i;
            for (i = 0; i < covers.length; i++) {
                covers[i].setAttribute('alt', t('library.cover'));
            }
        });
    }

    var storageKeySortableTag = 'tag-cloud-sortable-order';

    function initSortable() {
        if (!window.Sortable || window.__epubBrowserLibrarySortable) return;
        window.__epubBrowserLibrarySortable = true;
        var elBook = document.querySelector('.book-grid');
        var elTag = document.querySelector('.tag-cloud');
        bookDrag = Sortable.create(elBook, {
            delay: 300,
            delayOnTouchOnly: true,
            disabled: !bookDragEnabled,
            draggable: '.book-card',
            onEnd: function(evt) {
                if (evt.oldIndex === evt.newIndex) return;
                var booksById = new Map(pageBooks.map(function(book) { return [book.hash, book]; }));
                var reorderedPage = Array.prototype.map.call(evt.from.querySelectorAll('.book-card'), function(card) {
                    return booksById.get(card.getAttribute('data-id'));
                });
                // Replace only the slots occupied by this filtered page.
                var index = 0;
                orderedBooks = orderedBooks.map(function(book) {
                    return booksById.has(book.hash) ? reorderedPage[index++] : book;
                });
                pageBooks = reorderedPage;
                var itemIds = orderedBooks.map(function(book) { return book.hash; });
                if (serverMode) {
                    manualSave = manualSave.then(function() {
                        return saveServerOrder(itemIds, false);
                    }).catch(function() {
                        showNotification(t('library.loadError'), 'error');
                        return requestMetadataRefresh().catch(function() {});
                    });
                } else {
                    try { localStorage.setItem(manualOrderKey, JSON.stringify(itemIds)); } catch (error) {}
                }
            }
        });
        if (elTag) {
            markTagCloudFixed(elTag);
            Sortable.create(elTag, {
                delay: 300,
                delayOnTouchOnly: true,
                filter: '.tag-cloud-item--fixed',
                onEnd: function(evt) {
                    pinTagCloudFixedItems(elTag);
                    var itemIds = Array.from(evt.from.children).map(function(child) {
                        return child.dataset.id;
                    });
                    localStorage.setItem(storageKeySortableTag, JSON.stringify(itemIds));
                    if (evt.oldIndex !== evt.newIndex) suppressTagClick();
                }
            });
        }
    }

    function requestSortable() {
        if (window.Sortable) {
            initSortable();
            return;
        }
        loadLibraryFeature('sortable').then(initSortable, function() {});
    }

    function enableSortableOnInteraction() {
        var grid = document.querySelector('.book-grid');
        [grid, document.querySelector('.tag-cloud')].forEach(function(target) {
            if (!target || target.getAttribute('data-library-sortable-loader') === 'true') return;
            target.setAttribute('data-library-sortable-loader', 'true');
            target.addEventListener('pointerdown', function() {
                if (target !== grid || bookDragEnabled) requestSortable();
            });
        });
    }

    window.onBookCardsLoaded = enableSortableOnInteraction;

    if (window.initTheme) {
        window.initTheme();
    }

    var fontFamily = "ebook-default";
    var fontFamilyInput = null;
    if (window.epubBrowserCache && window.epubBrowserCache.font_family) {
        fontFamily = window.epubBrowserCache.font_family;
    } else {
        fontFamily = localStorage.getItem('font_family') || "ebook-default";
        if (fontFamily) {
            if (!window.epubBrowserCache) {
                window.epubBrowserCache = {};
            }
            window.epubBrowserCache.font_family = fontFamily;
        }
    }
    if (window.epubBrowserCache && window.epubBrowserCache.font_family_input) {
        fontFamilyInput = window.epubBrowserCache.font_family_input;
    } else {
        fontFamilyInput = localStorage.getItem('font_family_input');
        if (fontFamilyInput) {
            if (!window.epubBrowserCache) {
                window.epubBrowserCache = {};
            }
            window.epubBrowserCache.font_family_input = fontFamilyInput;
        }
    }
    updateFontFamily(fontFamily, fontFamilyInput);

    var searchBox = document.querySelector('.search-box');
    var tagCloud = document.querySelector('.tag-cloud');

    function searchablePinyin(text) {
        try {
            return pinyinPro.pinyin(text, { toneType: 'none' }).toLowerCase().replace(/ /g, '');
        } catch (error) {
            return '';
        }
    }

    function libraryGridColumns() {
        var tracks;
        var i;
        if (!bookGrid || !window.getComputedStyle) return 0;
        tracks = window.getComputedStyle(bookGrid).gridTemplateColumns;
        if (!tracks || tracks === 'none') return 0;
        tracks = tracks.trim().split(/\s+/);
        if (!tracks.length) return 0;
        // auto-fill/auto-fit 只有在解析成具体像素轨道时才能确定列数
        for (i = 0; i < tracks.length; i++) {
            if (!/^[0-9.]+px$/.test(tracks[i])) return 0;
        }
        return tracks.length;
    }

    // 每页行数保持接近 libraryPageTarget，但页大小必须是当前列数的整数倍，
    // 否则最后一行会缺卡；窗口宽度改变列数时同步调整。
    function syncLibraryPageSize() {
        var columns = libraryGridColumns();
        var nextSize = columns > 0
            ? columns * Math.max(1, Math.round(libraryPageTarget / columns))
            : libraryPageTarget;
        var firstVisibleIndex;
        if (nextSize === libraryPageSize) return false;
        firstVisibleIndex = (currentPage - 1) * libraryPageSize;
        libraryPageSize = nextSize;
        currentPage = Math.floor(firstVisibleIndex / nextSize) + 1;
        return true;
    }

    function applyLibraryFilters() {
        if (!bookGrid || !orderedBooks) return;
        syncLibraryPageSize();
        var searchTerm = (searchBox.value || '').toLowerCase().trim();
        var searchPinyin = searchTerm && typeof pinyinPro !== 'undefined' ? searchablePinyin(searchTerm) : '';
        var activeTag = document.querySelector('.tag-cloud-item.active');
        var tagId = activeTag ? activeTag.getAttribute('data-id') : 'All';
        var matches = orderedBooks.filter(function(book) {
            var tags = book.tags || [];
            if (tagId === 'NoTag' && tags.length) return false;
            if (tagId !== 'All' && tagId !== 'NoTag' && tags.indexOf(tagId) === -1) return false;
            if (!searchTerm) return true;
            var text = [book.title].concat(book.authors || [], tags).join(' ').toLowerCase();
            return text.includes(searchTerm) || !!(searchPinyin && searchablePinyin(text).includes(searchPinyin));
        });
        var totalPages = Math.max(1, Math.ceil(matches.length / libraryPageSize));
        currentPage = Math.min(currentPage, totalPages);
        var offset = (currentPage - 1) * libraryPageSize;
        pageBooks = matches.slice(offset, offset + libraryPageSize);
        removeLibraryCardsAndStates(bookGrid);

        if (!orderedBooks.length) {
            showLibraryState('library.emptyTitle', serverMode
                ? 'library.emptyServerDescription' : 'library.emptySsgDescription', 'empty');
        } else if (!matches.length) {
            showLibraryState('library.noResultsTitle', 'library.noResultsDescription', 'filtered');
        } else {
            pageBooks.forEach(function(book) {
                bookGrid.appendChild(createBookCard(book));
            });
        }
        setBookDragEnabled(pageBooks.length > 1 && selectedSort() === 'manual');

        if (pager) {
            pager.hidden = totalPages < 2;
            previousPage.disabled = currentPage === 1;
            nextPage.disabled = currentPage === totalPages;
            var params = { number: currentPage, total: totalPages };
            pageStatus.setAttribute('data-i18n-params', JSON.stringify(params));
            pageStatus.textContent = t('pdf.pageOf', params);
            jumpInput.max = totalPages;
            jumpInput.value = currentPage;
        }
    }

    function goToLibraryPage(page) {
        currentPage = page;
        applyLibraryFilters();
        if (bookGrid.focus) bookGrid.focus({ preventScroll: true });
        if (bookGrid.scrollIntoView) bookGrid.scrollIntoView({ block: 'start' });
    }

    if (pager) {
        previousPage.addEventListener('click', function() {
            if (!previousPage.disabled) goToLibraryPage(currentPage - 1);
        });
        nextPage.addEventListener('click', function() {
            if (!nextPage.disabled) goToLibraryPage(currentPage + 1);
        });
        jumpForm.addEventListener('submit', function(event) {
            event.preventDefault();
            var page = Number(jumpInput.value);
            if (Number.isInteger(page) && page >= 1 && page <= Number(jumpInput.max)) {
                goToLibraryPage(page);
            }
        });
    }

    function loadPinyinForSearch() {
        var searchTerm = (searchBox && searchBox.value || '').trim();
        if (!searchTerm || typeof pinyinPro !== 'undefined') return;
        loadLibraryFeature('pinyin').then(applyLibraryFilters, function() {});
    }

    function activateTag(tagId) {
        tagCloud.querySelectorAll('.tag-cloud-item').forEach(function(tagItem) {
            tagItem.classList.remove('active');
            if (tagItem.getAttribute('data-id') === tagId) tagItem.classList.add('active');
        });
        currentPage = 1;
        applyLibraryFilters();
    }

    if (searchBox && searchBox.getAttribute('data-library-filter-listener') !== 'true') {
        searchBox.setAttribute('data-library-filter-listener', 'true');
        searchBox.addEventListener('input', function() {
            currentPage = 1;
            applyLibraryFilters();
            loadPinyinForSearch();
        });
        window.addEventListener('keydown', function(event) {
            if (event.defaultPrevented || event.altKey || event.shiftKey) return;
            if (!(event.ctrlKey || event.metaKey)) return;
            if (String(event.key || '').toLowerCase() !== 'k') return;
            event.preventDefault();
            searchBox.focus();
            searchBox.select();
        });
    }
    if (tagCloud && tagCloud.getAttribute('data-library-filter-listener') !== 'true') {
        tagCloud.setAttribute('data-library-filter-listener', 'true');
        tagCloud.addEventListener('click', function(event) {
            if (window.__epubBrowserTagDragSuppressClick) return;
            var tag = event.target;
            if (tag && tag.classList.contains('tag-cloud-item')) activateTag(tag.getAttribute('data-id'));
        });
    }
    var tagCloudToggle = document.getElementById('tagCloudToggle');
    if (tagCloudToggle && tagCloudToggle.getAttribute('data-tag-cloud-toggle-listener') !== 'true') {
        tagCloudToggle.setAttribute('data-tag-cloud-toggle-listener', 'true');
        tagCloudToggle.addEventListener('click', function() {
            if (!tagCloud) return;
            if (tagCloud.classList.contains('tag-cloud--expanded')) {
                tagCloud.classList.remove('tag-cloud--expanded');
                setTagCloudToggleLabel(tagCloudToggle, false);
            } else {
                tagCloud.classList.add('tag-cloud--expanded');
                setTagCloudToggleLabel(tagCloudToggle, true);
            }
        });
    }
    if (window.addEventListener) {
        window.addEventListener('resize', updateTagCloudCollapse);
        window.addEventListener('resize', function() {
            if (syncLibraryPageSize()) applyLibraryFilters();
        });
    }
    var libraryGrid = document.querySelector('.book-grid');
    if (libraryGrid && libraryGrid.getAttribute('data-library-filter-listener') !== 'true') {
        libraryGrid.setAttribute('data-library-filter-listener', 'true');
        libraryGrid.addEventListener('click', function(event) {
            var tag = event.target;
            if (tag && tag.classList.contains('book-tag')) {
                event.preventDefault();
                event.stopPropagation();
                activateTag(tag.textContent);
            }
        });
    }
    window.initBookCardsEvents = applyLibraryFilters;

    window.refreshLibraryMetadata = function(catalogRevision) {
        return requestMetadataRefresh(catalogRevision);
    };

    if (sortControl) {
        var url = new URL(window.location.href);
        var savedSort = url.searchParams.get('sort');
        if (savedSort) sortControl.value = savedSort;
        if (!sortControl.value) sortControl.value = 'manual';
        sortControl.addEventListener('change', function() {
            currentPage = 1;
            var location = new URL(window.location.href);
            location.searchParams.set('sort', selectedSort());
            window.history.replaceState(window.history.state, '', location.href);
            setBookDragEnabled(false);
            if (serverMode) {
                var choice = selectedSort();
                manualSave.then(function() {
                    if (choice === selectedSort()) return requestMetadataRefresh();
                }).catch(function() {
                    showNotification(t('library.loadError'), 'error');
                });
            } else {
                replaceBookCards(lastMetadataBooks);
            }
        });
        if (i18n && !serverMode) {
            i18n.onLocaleChange(function() {
                if (selectedSort() !== 'manual' && lastMetadataBooks.length) replaceBookCards(lastMetadataBooks);
            });
        }
    }

    function catalogueReady() {
        if (sortControl) sortControl.disabled = false;
        if (window.onBookCardsLoaded) window.onBookCardsLoaded();
    }

    function initialLoadFailed() {
        if (sortControl && serverMode) sortControl.disabled = false;
        hideBookGridLoading();
        showLibraryState('library.loadError');
    }

    var legacyImport = importLegacyOrder();
    var initialLoad = legacyImport
        ? legacyImport.then(function() { return requestMetadataRefresh(0); })
        : requestMetadataRefresh(0);
    initialLoad.then(catalogueReady, initialLoadFailed);

    var scrollToTopBtn = document.getElementById('scrollToTopBtn');

    scrollToTopBtn.addEventListener('click', function() {
        // 移除 smooth，Kindle 兼容
        window.scrollTo(0, 0);
    });

    function updateScrollToTopVisibility() {
        var scrollTop = window.pageYOffset || document.documentElement.scrollTop || 0;
        var threshold = Math.max(320, (window.innerHeight || 0) * 0.75);
        if (scrollTop > threshold) scrollToTopBtn.classList.add('is-visible');
        else scrollToTopBtn.classList.remove('is-visible');
    }
    window.addEventListener('scroll', updateScrollToTopVisibility);
    updateScrollToTopVisibility();

    function pwaSupport() {
        if (window.EpubBrowserMode === 'server') return;
        if ('serviceWorker' in navigator) {
            window.addEventListener('load', function() {
                window.EpubBrowserCacheBoundary.registerWorker()
                    .then(function(registration) {
                        console.log('ServiceWorker registration successful');
                    })
                    .catch(function(error) {
                        console.log('ServiceWorker registration failed');
                    });
            });
        }
        var deferredPrompt;
        var installBtn = document.getElementById('pwa-install-btn');

        window.addEventListener('beforeinstallprompt', function(e) {
            e.preventDefault();
            deferredPrompt = e;
            if (installBtn) installBtn.style.display = '';
        });

        if (installBtn) {
            installBtn.addEventListener('click', function(e) {
                e.preventDefault();
                if (deferredPrompt) {
                    showNotification(t('library.installing'), 'info');
                    installBtn.style.display = 'none';
                    deferredPrompt.prompt();
                    deferredPrompt.userChoice.then(function(choiceResult) {
                        if (choiceResult.outcome === 'accepted') {
                            showNotification(t('library.installSucceeded'), 'success');
                        } else {
                            showNotification(t('library.installCancelled'), 'info');
                        }
                        deferredPrompt = null;
                    });
                }
            });
        }

        window.addEventListener('appinstalled', function() {
            if (installBtn) installBtn.style.display = 'none';
        });
    }

    function setDeferredFeatureLoading(button, loading, loadingKey) {
        var label = button.querySelector('[data-i18n]');
        var icon = button.querySelector('i');
        if (loading) {
            if (label) {
                button.dataset.libraryFeatureLabel = label.textContent;
                label.textContent = t(loadingKey);
            }
            if (icon) {
                button.dataset.libraryFeatureIcon = icon.className;
                icon.className = 'fas fa-spinner fa-spin';
            }
            button.classList.add('is-loading');
            button.setAttribute('aria-busy', 'true');
            button.setAttribute('aria-disabled', 'true');
            button.disabled = true;
            return;
        }
        if (label) label.replaceChildren(document.createTextNode(
            label.getAttribute('data-i18n') ? t(label.getAttribute('data-i18n')) : button.dataset.libraryFeatureLabel
        ));
        if (icon && button.dataset.libraryFeatureIcon) icon.className = button.dataset.libraryFeatureIcon;
        button.classList.remove('is-loading');
        button.removeAttribute('aria-busy');
        button.removeAttribute('aria-disabled');
        button.disabled = false;
        delete button.dataset.libraryFeatureLabel;
        delete button.dataset.libraryFeatureIcon;
    }

    function deferLibraryFeature(buttonId, feature, initialize, loadingKey) {
        var button = document.getElementById(buttonId);
        if (!button || button.getAttribute('data-library-feature-loader') === 'true') return;
        button.setAttribute('data-library-feature-loader', 'true');
        button.addEventListener('click', function(event) {
            if (button.getAttribute('data-library-feature-ready') === 'true') return;
            event.preventDefault();
            setDeferredFeatureLoading(button, true, loadingKey);
            loadLibraryFeature(feature).then(function() {
                if (typeof initialize === 'function') initialize();
                button.setAttribute('data-library-feature-ready', 'true');
                setDeferredFeatureLoading(button, false, loadingKey);
                button.click();
            }, function() { setDeferredFeatureLoading(button, false, loadingKey); });
        });
    }

    pwaSupport();
    deferLibraryFeature('bookshelfBtn', 'bookshelf', function() {
        if (window.initBookShelf) window.initBookShelf();
    }, 'bookshelf.loading');
    deferLibraryFeature('annotationsBtn', 'annotations', null, 'annotations.loading');

    function hideLoading() {
        var overlay = document.getElementById('loadingOverlay');
        if (overlay) overlay.style.display = 'none';
    }

    setTimeout(hideLoading, 100);
}

window.initScriptLibrary = initScript;
