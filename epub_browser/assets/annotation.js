/**
 * Text Highlight and Annotation Module
 * Supports IndexedDB and backend storage, compatible with a wide range of devices
 */
(function(global) {
    'use strict';
    
    // ========== Configuration & Constants ==========
    var CONFIG = {
        DB_NAME: 'epub-browser-annotations',
        DB_VERSION: 1,
        STORE_NAME: 'annotations',
        BASE_COLORS: ['#FFEB3B', '#4CAF50', '#2196F3', '#9C27B0', '#F44336', '#FF9800', '#00BCD4', '#795548'],
        DEFAULT_COLOR: '#FFEB3B',
        HEALTH_TIMEOUT: 3000,
        BATCH_SIZE: 100,
        ANNOTATION_CLASS: 'annotation-highlight',
        
        // Get colors based on settings
        getColors: function() {
            var order = Settings.colorOrder || [];
            var custom = Settings.customColors || [];
            var deleted = Settings.deletedColors || [];
            
            // If no color order (never dragged/sorted), use base colors + custom colors
            if (order.length === 0) {
                var result = this.BASE_COLORS.slice();
                // Add custom colors that are not in base colors
                for (var j = 0; j < custom.length; j++) {
                    if (result.indexOf(custom[j]) === -1) {
                        result.push(custom[j]);
                    }
                }
                // Filter out deleted colors
                return result.filter(function(c) { return deleted.indexOf(c) === -1; });
            }
            
            // Merge: first use color order, then add custom colors not in order
            var allColors = [];
            var seen = {};
            
            // First add colors in order
            for (var i = 0; i < order.length; i++) {
                if (order[i] && !seen[order[i]] && deleted.indexOf(order[i]) === -1) {
                    allColors.push(order[i]);
                    seen[order[i]] = true;
                }
            }
            
            // Then add custom colors not in order
            for (var j = 0; j < custom.length; j++) {
                if (!seen[custom[j]] && deleted.indexOf(custom[j]) === -1) {
                    allColors.push(custom[j]);
                    seen[custom[j]] = true;
                }
            }
            
            return allColors;
        }
    };
    
    // ========== Web Highlighter Integration ==========
    var highlighter = null;
    
    function initHighlighter() {
        if (highlighter) return highlighter;
        
        // Wait for web-highlighter to be available
        if (typeof Highlighter === 'undefined') {
            console.error('web-highlighter not loaded');
            return null;
        }
        
        highlighter = new Highlighter({
            $root: document.getElementById('eb-content') || document.documentElement,
            exceptSelectors: ['pre', 'code', 'a', 'br'],
            wrapTag: 'span',
            style: {
                className: CONFIG.ANNOTATION_CLASS,
                backgroundColor: Utils.addColorAlpha(Settings.defaultColor, 0.4)
            }
        });
        
        return highlighter;
    }
    
    // Current book and chapter info (set by external code)
    var currentBookHash = '';
    var currentChapterIndex = -1;
    var pendingContentRefreshDetails = [];
    var contentReadyListenerBound = false;
    var contentReadyRefreshGeneration = 0;
    var contentReadyRefreshes = Object.create(null);

    function contentReadyRefreshKey(chapterIndex) {
        var normalized = Number(chapterIndex);
        return Number.isInteger(normalized) ? String(normalized) : '*';
    }

    function rememberContentReadyRefresh(detail, promise) {
        var record = {
            generation: ++contentReadyRefreshGeneration,
            detail: detail || {},
            promise: Promise.resolve(promise)
        };
        contentReadyRefreshes[contentReadyRefreshKey(detail && detail.chapterIndex)] = record;
        return record;
    }

    function contentReadyRefreshFor(chapterIndex) {
        return contentReadyRefreshes[contentReadyRefreshKey(chapterIndex)] ||
            contentReadyRefreshes['*'] || null;
    }

    function tr(key, params) {
        var i18n = window.EpubBrowserI18n;
        return i18n && i18n.t ? i18n.t('annotations.' + key, params) : key;
    }

    function createAnnotationDetailLifecycle() {
        var revision = 0;
        return {
            begin: function() {
                revision += 1;
                return revision;
            },
            invalidate: function() {
                revision += 1;
            },
            isCurrent: function(token) {
                return token === revision;
            },
            run: function(token, operation, onSuccess, onFailure) {
                var self = this;
                return Promise.resolve().then(operation).then(function(result) {
                    if (self.isCurrent(token) && onSuccess) onSuccess(result);
                    return result;
                }).catch(function(error) {
                    if (self.isCurrent(token) && onFailure) onFailure(error);
                    throw error;
                });
            },
            runSave: function(token, operation, onSuccess, onFailure) {
                return this.run(token, function() {
                    return operation({ notifyFailure: false });
                }, onSuccess, onFailure);
            }
        };
    }

    var BACKEND_ERROR_CODES = {
        not_found: true,
        username_required: true,
        invalid_json: true,
        no_sync_data: true,
        annotation_not_found: true,
        invalid_chapter_index: true,
        batch_requires_post: true,
        database_unavailable: true,
        reading_progress_not_found: true,
        server_error: true,
        network: true,
        timeout: true
    };

    function backendErrorMessage(code) {
        var key = BACKEND_ERROR_CODES[code] ? code : 'server_error';
        return tr('error.' + key);
    }

    function backendRequestError(code) {
        var normalizedCode = BACKEND_ERROR_CODES[code] ? code : 'server_error';
        var error = new Error(backendErrorMessage(normalizedCode));
        error.code = normalizedCode;
        return error;
    }

    function errorCodeFromPayload(responseText) {
        var payload;
        try {
            payload = JSON.parse(responseText);
        } catch (e) {
            return '';
        }
        return payload && typeof payload.code === 'string' ? payload.code : '';
    }

    function formatAnnotationDate(value) {
        var i18n = window.EpubBrowserI18n;
        if (i18n && i18n.formatDate) {
            return i18n.formatDate(value, {
                year: 'numeric', month: '2-digit', day: '2-digit',
                hour: '2-digit', minute: '2-digit', second: '2-digit'
            });
        }
        return Utils.formatDateTime(value);
    }

    var COLLAPSED_COLOR_COUNT = 7;

    function compactAnnotationColors(colors, selectedColor) {
        var visible = colors.slice(0, COLLAPSED_COLOR_COUNT);
        if (
            colors.indexOf(selectedColor) !== -1 &&
            visible.indexOf(selectedColor) === -1 &&
            visible.length
        ) {
            visible[visible.length - 1] = selectedColor;
        }
        return visible;
    }

    function createExpandableColorPicker(container, selectedColor, onSelect) {
        var allColors = CONFIG.getColors();
        var currentColor = selectedColor;
        var expanded = false;

        var render = function() {
            container.innerHTML = '';
            var visibleColors = expanded
                ? allColors
                : compactAnnotationColors(allColors, currentColor);

            visibleColors.forEach(function(color) {
                var choice = document.createElement('button');
                choice.type = 'button';
                choice.className = 'color-option' + (color === currentColor ? ' selected' : '');
                choice.style.backgroundColor = color;
                choice.setAttribute('data-color', color);
                choice.setAttribute('aria-label', tr('color') + ' ' + color);
                choice.setAttribute('aria-pressed', (color === currentColor).toString());
                choice.addEventListener('click', function() {
                    currentColor = color;
                    container.querySelectorAll('.color-option').forEach(function(option) {
                        option.classList.toggle('selected', option === choice);
                        option.setAttribute('aria-pressed', (option === choice).toString());
                    });
                    if (onSelect) onSelect(color);
                });
                container.appendChild(choice);
            });

            if (allColors.length > COLLAPSED_COLOR_COUNT) {
                var hiddenCount = allColors.length - visibleColors.length;
                var toggle = document.createElement('button');
                var toggleLabel = expanded
                    ? tr('showFewerColors')
                    : tr('showMoreColors', { count: hiddenCount });
                toggle.type = 'button';
                toggle.className = 'color-options-toggle';
                toggle.textContent = expanded ? '−' : '+' + hiddenCount;
                toggle.title = toggleLabel;
                toggle.setAttribute('aria-label', toggleLabel);
                toggle.setAttribute('aria-expanded', expanded.toString());
                toggle.addEventListener('click', function(event) {
                    event.stopPropagation();
                    expanded = !expanded;
                    render();
                });
                container.appendChild(toggle);
            }
        };

        render();
    }
    
    // ========== Utility Functions ==========
    var Utils = {
        // Generate UUID
        generateUUID: function() {
            var d = new Date().getTime();
            var uuid = 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
                var r = (d + Math.random() * 16) % 16 | 0;
                d = Math.floor(d / 16);
                return (c === 'x' ? r : (r & 0x3 | 0x8)).toString(16);
            });
            return uuid;
        },
        
        // Get current time in ISO format
        getISOTime: function() {
            return new Date().toISOString();
        },
        
        // Deep clone
        deepClone: function(obj) {
            if (obj === null || typeof obj !== 'object') return obj;
            if (obj instanceof Array) {
                var arr = [];
                for (var i = 0; i < obj.length; i++) {
                    arr[i] = this.deepClone(obj[i]);
                }
                return arr;
            }
            var copy = {};
            for (var key in obj) {
                if (obj.hasOwnProperty(key)) {
                    copy[key] = this.deepClone(obj[key]);
                }
            }
            return copy;
        },
        
        // Escape HTML
        escapeHtml: function(text) {
            var div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        },

        copyText: function(text) {
            if (navigator.clipboard && navigator.clipboard.writeText) {
                return navigator.clipboard.writeText(text);
            }
            return new Promise(function(resolve, reject) {
                var input = document.createElement('textarea');
                input.value = text;
                input.setAttribute('readonly', '');
                input.style.position = 'fixed';
                input.style.opacity = '0';
                document.body.appendChild(input);
                input.select();
                var copied = document.execCommand('copy');
                input.remove();
                copied ? resolve() : reject(new Error('Clipboard unavailable'));
            });
        },
        
        // Format date as YYYY-MM-DD HH:MM:SS
        formatDateTime: function(dateStr) {
            var d = new Date(dateStr);
            var yyyy = d.getFullYear();
            var MM = String(d.getMonth() + 1).padStart(2, '0');
            var dd = String(d.getDate()).padStart(2, '0');
            var HH = String(d.getHours()).padStart(2, '0');
            var mm = String(d.getMinutes()).padStart(2, '0');
            var ss = String(d.getSeconds()).padStart(2, '0');
            return yyyy + '-' + MM + '-' + dd + ' ' + HH + ':' + mm + ':' + ss;
        },
        
        // Show notification (reuse chapter.js notification function)
        showNotification: function(message, type) {
            if (typeof window.showNotification === 'function') {
                window.showNotification(message, type);
            } else {
                // Simple notification implementation
                var existing = document.querySelector('.annotation-notification');
                if (existing) existing.remove();
                
                var notification = document.createElement('div');
                notification.className = 'annotation-notification custom-css-notification ' + (type || 'info');
                notification.textContent = message;
                document.body.appendChild(notification);
                
                setTimeout(function() {
                    notification.classList.add('fade-out');
                    setTimeout(function() {
                        if (notification.parentNode) notification.remove();
                    }, 300);
                }, 3000);
            }
        },
        
        // Detect if Kindle device
        isKindleMode: function() {
            if (window.epubBrowserCache && window.epubBrowserCache.kindle_mode !== undefined) {
                return window.epubBrowserCache.kindle_mode === 'true';
            }
            var ua = navigator.userAgent.toLowerCase();
            var isKindle = ua.indexOf('kindle') !== -1 || ua.indexOf('silk') !== -1;
            if (!window.epubBrowserCache) window.epubBrowserCache = {};
            window.epubBrowserCache.kindle_mode = isKindle ? 'true' : 'false';
            return isKindle;
        },
        
        // Get storage
        getStorage: function(key) {
            if (this.isKindleMode()) {
                return this.getCookie(key);
            }
            try {
                return localStorage.getItem(key);
            } catch (e) {
                return null;
            }
        },
        
        // Set storage
        setStorage: function(key, value) {
            if (this.isKindleMode()) {
                this.setCookie(key, value);
            } else {
                try {
                    localStorage.setItem(key, value);
                } catch (e) {}
            }
        },
        
        // Cookie operations
        getCookie: function(key) {
            var cookies = document.cookie.split('; ');
            for (var i = 0; i < cookies.length; i++) {
                var parts = cookies[i].split('=');
                if (parts[0] === key) {
                    return decodeURIComponent(parts.slice(1).join('='));
                }
            }
            return null;
        },
        
        setCookie: function(key, value) {
            var date = new Date();
            date.setTime(date.getTime() + 3650 * 24 * 60 * 60 * 1000);
            document.cookie = key + '=' + value + '; expires=' + date.toUTCString() + '; path=/;';
        },
        
        // Add alpha to hex color
        addColorAlpha: function(hex, alpha) {
            // Convert hex to rgba
            var r = parseInt(hex.slice(1, 3), 16);
            var g = parseInt(hex.slice(3, 5), 16);
            var b = parseInt(hex.slice(5, 7), 16);
            return 'rgba(' + r + ', ' + g + ', ' + b + ', ' + alpha + ')';
        }
    };
    
    // ========== IndexedDB 存储适配器 ==========
    var IDBStorage = {
        db: null,
        
        // 初始化数据库
        init: function() {
            var self = this;
            return new Promise(function(resolve, reject) {
                if (self.db) {
                    resolve();
                    return;
                }
                
                var request;
                try {
                    request = indexedDB.open(CONFIG.DB_NAME, CONFIG.DB_VERSION);
                } catch (e) {
                    reject(e);
                    return;
                }
                
                request.onerror = function(event) {
                    reject(request.error);
                };
                
                request.onsuccess = function(event) {
                    self.db = request.result;
                    resolve();
                };
                
                request.onupgradeneeded = function(event) {
                    var db = event.target.result;
                    
                    // 创建标注存储
                    if (!db.objectStoreNames.contains(CONFIG.STORE_NAME)) {
                        var store = db.createObjectStore(CONFIG.STORE_NAME, { keyPath: 'id' });
                        store.createIndex('book_hash', 'book_hash', { unique: false });
                        store.createIndex('chapter', ['book_hash', 'chapter_index'], { unique: false });
                        store.createIndex('created_at', 'created_at', { unique: false });
                    }
                };
            });
        },
        
        // 通用事务操作
        _transaction: function(storeName, mode, callback) {
            var self = this;
            return new Promise(function(resolve, reject) {
                if (!self.db) {
                    reject(new Error('Database not initialized'));
                    return;
                }
                
                var transaction = self.db.transaction(storeName, mode);
                var store = transaction.objectStore(storeName);
                
                transaction.onerror = function() {
                    reject(transaction.error);
                };
                
                var request = callback(store);
                if (request) {
                    request.onsuccess = function() {
                        resolve(request.result);
                    };
                    request.onerror = function() {
                        reject(request.error);
                    };
                } else {
                    transaction.oncomplete = function() {
                        resolve();
                    };
                }
            });
        },
        
        // 创建标注
        create: function(annotation) {
            return this._transaction(CONFIG.STORE_NAME, 'readwrite', function(store) {
                return store.put(annotation);
            });
        },
        
        // 更新标注
        update: function(id, data) {
            var self = this;
            return new Promise(function(resolve, reject) {
                self._transaction(CONFIG.STORE_NAME, 'readonly', function(store) {
                    return store.get(id);
                }).then(function(existing) {
                    if (!existing) {
                        reject(new Error('Annotation not found'));
                        return;
                    }
                    for (var key in data) {
                        if (data.hasOwnProperty(key)) {
                            existing[key] = data[key];
                        }
                    }
                    existing.updated_at = Utils.getISOTime();
                    self._transaction(CONFIG.STORE_NAME, 'readwrite', function(store) {
                        return store.put(existing);
                    }).then(resolve).catch(reject);
                }).catch(reject);
            });
        },
        
        // 删除标注
        delete: function(id) {
            return this._transaction(CONFIG.STORE_NAME, 'readwrite', function(store) {
                return store.delete(id);
            });
        },
        
        // 获取单个标注
        getById: function(id) {
            return this._transaction(CONFIG.STORE_NAME, 'readonly', function(store) {
                return store.get(id);
            });
        },
        
        // 获取书籍所有标注
        getByBook: function(bookHash) {
            var self = this;
            return new Promise(function(resolve, reject) {
                if (!self.db) {
                    reject(new Error('Database not initialized'));
                    return;
                }
                
                var transaction = self.db.transaction(CONFIG.STORE_NAME, 'readonly');
                var store = transaction.objectStore(CONFIG.STORE_NAME);
                var index = store.index('book_hash');
                var request = index.getAll(bookHash);
                
                request.onsuccess = function() {
                    resolve(request.result || []);
                };
                request.onerror = function() {
                    reject(request.error);
                };
            });
        },
        
        // 获取章节标注
        getByChapter: function(bookHash, chapterIndex) {
            var self = this;
            return new Promise(function(resolve, reject) {
                if (!self.db) {
                    reject(new Error('Database not initialized'));
                    return;
                }
                
                var transaction = self.db.transaction(CONFIG.STORE_NAME, 'readonly');
                var store = transaction.objectStore(CONFIG.STORE_NAME);
                var index = store.index('chapter');
                var request = index.getAll([bookHash, chapterIndex]);
                
                request.onsuccess = function() {
                    resolve(request.result || []);
                };
                request.onerror = function() {
                    reject(request.error);
                };
            });
        },
        
        // 获取所有标注
        getAll: function() {
            return this._transaction(CONFIG.STORE_NAME, 'readonly', function(store) {
                return store.getAll();
            }).then(function(result) {
                return result || [];
            });
        },
        
        // 批量创建
        batchCreate: function(annotations) {
            var self = this;
            return new Promise(function(resolve, reject) {
                if (!self.db) {
                    reject(new Error('Database not initialized'));
                    return;
                }
                
                var transaction = self.db.transaction(CONFIG.STORE_NAME, 'readwrite');
                var store = transaction.objectStore(CONFIG.STORE_NAME);
                var created = 0;
                var failed = 0;
                
                for (var i = 0; i < annotations.length; i++) {
                    try {
                        store.put(annotations[i]);
                        created++;
                    } catch (e) {
                        failed++;
                    }
                }
                
                transaction.oncomplete = function() {
                    resolve({ created: created, failed: failed });
                };
                transaction.onerror = function() {
                    reject(transaction.error);
                };
            });
        },
        
        // 清空所有数据
        clear: function() {
            return this._transaction(CONFIG.STORE_NAME, 'readwrite', function(store) {
                return store.clear();
            });
        }
    };
    
    // ========== 后端存储适配器 ==========
    var BackendStorage = {
        baseUrl: '/api',
        available: null,
        
        // 检测后端是否可用（纯健康检查，不耦合登录）
        checkHealth: function() {
            var self = this;
            if (window.EpubBrowserMode !== 'server') {
                self.available = false;
                return Promise.resolve({ available: false });
            }
            if (!window.EpubBrowserAuth || typeof window.EpubBrowserAuth.fetch !== 'function') {
                self.available = false;
                return Promise.resolve({ available: false });
            }
            try {
                return Promise.resolve(window.EpubBrowserAuth.fetch(self.baseUrl + '/health')).then(function(response) {
                    if (!response.ok) return null;
                    return response.text().then(function(responseText) {
                        try {
                            return JSON.parse(responseText);
                        } catch (e) {
                            return null;
                        }
                    });
                }).then(function(payload) {
                    self.available = !!payload && payload.status === 'ok';
                    return { available: self.available };
                }, function() {
                    self.available = false;
                    return { available: false };
                });
            } catch (e) {
                self.available = false;
                return Promise.resolve({ available: false });
            }
        },
        
        // 发送请求
        _request: function(method, path, data) {
            var self = this;
            if (!window.EpubBrowserAuth || typeof window.EpubBrowserAuth.fetch !== 'function') {
                return Promise.reject(backendRequestError('network'));
            }
            var options = {
                method: method,
                headers: { 'Content-Type': 'application/json' }
            };
            if (data !== undefined && data !== null) {
                options.body = JSON.stringify(data);
            }
            try {
                return Promise.resolve(window.EpubBrowserAuth.fetch(self.baseUrl + path, options)).then(function(response) {
                    return response.text().then(function(responseText) {
                        if (!response.ok) {
                            throw backendRequestError(errorCodeFromPayload(responseText));
                        }
                        try {
                            return JSON.parse(responseText);
                        } catch (e) {
                            return responseText;
                        }
                    });
                }, function() {
                    throw backendRequestError('network');
                });
            } catch (e) {
                return Promise.reject(backendRequestError('network'));
            }
        },
        
        // 创建标注
        create: function(annotation) {
            return this._request('POST', '/annotations', annotation).then(function(res) {
                return res.data || res;
            });
        },
        
        // 更新标注
        update: function(id, data) {
            return this._request('PUT', '/annotations/item/' + id, data).then(function(res) {
                return res.data || res;
            });
        },
        
        // 删除标注
        delete: function(id) {
            return this._request('DELETE', '/annotations/item/' + id);
        },
        
        // 获取单个标注
        getById: function(id) {
            return this._request('GET', '/annotations/item/' + id).then(function(res) {
                return res.data || res;
            });
        },
        
        // 获取书籍所有标注
        getByBook: function(bookHash) {
            return this._request('GET', '/annotations/' + bookHash).then(function(res) {
                return res.data || [];
            });
        },
        
        // 获取章节标注
        getByChapter: function(bookHash, chapterIndex) {
            return this._request('GET', '/annotations/' + bookHash + '/' + chapterIndex).then(function(res) {
                return res.data || [];
            });
        },
        
        // 获取所有标注
        getAll: function() {
            return this._request('GET', '/annotations').then(function(res) {
                return res.data || [];
            });
        },

        // 获取汇总页所需的按书统计，不下载标注正文和定位数据
        getSummary: function() {
            return this._request('GET', '/annotations?view=summary').then(function(res) {
                return res.data || [];
            });
        },
        
        // 批量创建
        batchCreate: function(annotations) {
            return this._request('POST', '/annotations/batch', { annotations: annotations });
        }
    };
    
    // ========== 数据迁移器 ==========
    var Migrator = {
        // 从源存储迁移到目标存储
        migrate: function(fromAdapter, toAdapter, onProgress) {
            return new Promise(function(resolve, reject) {
                // 获取源数据
                fromAdapter.getAll().then(function(data) {
                    if (!data || data.length === 0) {
                        resolve(0);
                        return;
                    }
                    
                    var total = data.length;
                    var migrated = 0;
                    var batches = [];
                    
                    // 分批
                    for (var i = 0; i < data.length; i += CONFIG.BATCH_SIZE) {
                        batches.push(data.slice(i, i + CONFIG.BATCH_SIZE));
                    }
                    
                    // 逐批迁移
                    var migrateBatch = function(batchIndex) {
                        if (batchIndex >= batches.length) {
                            resolve(migrated);
                            return;
                        }
                        
                        var batch = batches[batchIndex];
                        toAdapter.batchCreate(batch).then(function() {
                            migrated += batch.length;
                            if (onProgress) onProgress(migrated, total);
                            migrateBatch(batchIndex + 1);
                        }).catch(function(err) {
                            // 继续下一批
                            migrateBatch(batchIndex + 1);
                        });
                    };
                    
                    migrateBatch(0);
                }).catch(reject);
            });
        }
    };
    
    // ========== 存储管理器 ==========
    var StorageManager = {
        currentType: 'idb',
        adapters: {
            idb: IDBStorage,
            backend: BackendStorage
        },
        
        // 初始化
        init: function() {
            var self = this;
            if (window.EpubBrowserMode === 'server') {
                self.currentType = 'backend';
                Settings.storageType = 'backend';
                return Promise.resolve();
            }
            self.currentType = 'idb';
            Settings.storageType = 'idb';
            return IDBStorage.init();
        },
        
        // 获取当前适配器
        getAdapter: function() {
            return this.adapters[this.currentType];
        },
        
        // 切换存储类型
        setStorageType: function(type, shouldMigrate, onProgress) {
            var self = this;
            return new Promise(function(resolve, reject) {
                if (type === self.currentType) {
                    resolve();
                    return;
                }
                
                var fromAdapter = self.adapters[self.currentType];
                var toAdapter = self.adapters[type];
                
                var finish = function() {
                    self.currentType = type;
                    // 保存到 localStorage
                    Settings.storageType = type;
                    Settings.save();
                    resolve();
                };
                
                if (shouldMigrate) {
                    Migrator.migrate(fromAdapter, toAdapter, onProgress).then(function(count) {
                        finish();
                    }).catch(function(err) {
                        finish(); // 即使迁移失败也切换
                    });
                } else {
                    finish();
                }
            });
        },
        
        // 检测后端是否可用
        isBackendAvailable: function() {
            if (window.EpubBrowserMode !== 'server') {
                return Promise.resolve({ available: false });
            }
            return BackendStorage.checkHealth();
        },
        
        // CRUD 操作
        create: function(data) {
            return this.getAdapter().create(data);
        },
        
        update: function(id, data) {
            return this.getAdapter().update(id, data);
        },
        
        delete: function(id) {
            return this.getAdapter().delete(id);
        },
        
        getById: function(id) {
            return this.getAdapter().getById(id);
        },
        
        getByBook: function(bookHash) {
            return this.getAdapter().getByBook(bookHash);
        },
        
        getByChapter: function(bookHash, chapterIndex) {
            return this.getAdapter().getByChapter(bookHash, chapterIndex);
        },
        
        getAll: function() {
            return this.getAdapter().getAll();
        },

        getSummary: function() {
            var adapter = this.getAdapter();
            return typeof adapter.getSummary === 'function'
                ? adapter.getSummary()
                : adapter.getAll();
        }
    };
    
    // ========== Settings Manager ==========
    var Settings = {
        enabled: true,
        defaultColor: CONFIG.DEFAULT_COLOR,
        storageType: 'idb',
        backendAvailable: false,
        colorOrder: [],
        customColors: [],
        deletedColors: [],
        
        // Load settings
        load: function() {
            var enabled = Utils.getStorage('annotation_enabled');
            var color = Utils.getStorage('annotation_default_color');
            var colorOrder = Utils.getStorage('annotation_color_order');
            var customColors = Utils.getStorage('annotation_custom_colors');
            var deletedColors = Utils.getStorage('annotation_deleted_colors');
            
            if (enabled !== null) this.enabled = enabled === 'true';
            if (color) this.defaultColor = color;
            this.storageType = window.EpubBrowserMode === 'server' ? 'backend' : 'idb';
            if (colorOrder) {
                try { this.colorOrder = JSON.parse(colorOrder); } catch (e) { this.colorOrder = []; }
            }
            if (customColors) {
                try { this.customColors = JSON.parse(customColors); } catch (e) { this.customColors = []; }
            }
            if (deletedColors) {
                try { this.deletedColors = JSON.parse(deletedColors); } catch (e) { this.deletedColors = []; }
            }
        },
        
        // Save settings
        save: function() {
            Utils.setStorage('annotation_enabled', this.enabled.toString());
            Utils.setStorage('annotation_default_color', this.defaultColor);
            Utils.setStorage('annotation_color_order', JSON.stringify(this.colorOrder));
            Utils.setStorage('annotation_custom_colors', JSON.stringify(this.customColors));
            Utils.setStorage('annotation_deleted_colors', JSON.stringify(this.deletedColors));
        }
    };
    
    // ========== 划线交互模块 ==========
    var HighlightInteraction = {
        activeDialog: null,
        outsideClickHandler: null,
        annotations: [],
        isRendering: false,
        isListening: false,
        isBound: false,
        keyboardBound: false,
        pendingDraft: null,
        imageNoteButtons: [],
        renderVersion: 0,
        detailLifecycle: createAnnotationDetailLifecycle(),

        init: function() {
            var hl = initHighlighter();
            if (hl && !this.isBound) {
                this.bindHighlighterEvents(hl);
                this.isBound = true;
            }
            if (!this.keyboardBound && typeof document.addEventListener === 'function') {
                var self = this;
                document.addEventListener('keydown', function(event) {
                    if (event.key === 'Escape' && self.activeDialog) self.cancelPendingDraft();
                });
                this.keyboardBound = true;
            }
            this.syncEnabledState();
        },

        bindHighlighterEvents: function(hl) {
            var self = this;
            hl.on(Highlighter.event.CREATE, function(data) {
                self.handleHighlightCreate(data);
            });
            hl.on(Highlighter.event.CLICK, function(data) {
                var annotationId = (data && data.id) || self.getAnnotationIdFromNode(data && data.target);
                if (!annotationId) return;
                var draft = self.pendingDraft;
                if (draft && draft.id === annotationId && draft.source) {
                    self.showCreateDialogFromSource(draft.source);
                    return;
                }
                self.showDetailDialog(annotationId);
            });
        },

        syncEnabledState: function() {
            this.imageNoteButtons.forEach(function(button) {
                button.disabled = !Settings.enabled;
                button.setAttribute('aria-disabled', Settings.enabled ? 'false' : 'true');
            });
            if (!highlighter) return;
            if (Settings.enabled) {
                if (!this.isListening) {
                    highlighter.run();
                    this.isListening = true;
                }
                return;
            }
            if (this.isListening) {
                highlighter.stop();
                this.isListening = false;
            }
            this.cancelPendingDraft();
        },

        setContext: function(bookHash, chapterIndex) {
            currentBookHash = bookHash || '';
            currentChapterIndex = typeof chapterIndex === 'number' ? chapterIndex : 0;
            return this.renderAll();
        },

        getContentRoot: function() {
            return document.getElementById('eb-content') || document.documentElement;
        },

        getContinuousChapterSections: function() {
            return Array.prototype.slice.call(this.getContentRoot().querySelectorAll('.continuous-chapter'));
        },

        getChapterSection: function(chapterIndex) {
            var sections = this.getContinuousChapterSections();
            for (var i = 0; i < sections.length; i++) {
                if (parseInt(sections[i].getAttribute('data-chapter-index'), 10) === chapterIndex) {
                    return sections[i];
                }
            }
            return null;
        },

        hasPendingPdfAnnotationContent: function() {
            if (!global.EpubPDFConfig) return false;
            var pages = this.getContentRoot().querySelectorAll('[data-pdf-page-number]');
            for (var i = 0; i < pages.length; i++) {
                var state = pages[i].getAttribute('data-pdf-rendered');
                if (state !== 'complete' && state !== 'error') return true;
            }
            return false;
        },

        pdfPageForNode: function(node) {
            var current = node;
            while (current) {
                if (current.getAttribute && current.getAttribute('data-pdf-page-number') !== null) return current;
                current = current.parentNode;
            }
            return null;
        },

        pdfPagesForSource: function(source, sources) {
            var pages = [];
            var add = function(node) {
                var page = this.pdfPageForNode(node);
                if (page && pages.indexOf(page) === -1) pages.push(page);
            }.bind(this);
            var allSources = Array.isArray(sources) && sources.length ? sources : [source];
            allSources.forEach(function(item) {
                this.getHighlightNodesByAnnotationId(item && item.id).forEach(add);
            }, this);
            if (pages.length || !global.getSelection) return pages;
            var selection = global.getSelection();
            if (!selection || !selection.rangeCount) return pages;
            var range = selection.getRangeAt(0);
            add(range.startContainer);
            add(range.endContainer);
            return pages;
        },

        selectionCapabilityMessage: function(source, sources) {
            var pages = this.pdfPagesForSource(source, sources);
            if (!pages.length) return '';
            if (pages.some(function(page) {
                return page.getAttribute('data-pdf-has-extractable-text') !== 'true';
            })) return 'pdf.textUnavailable';
            return pages.length === 1 ? '' : 'pdf.selectionWithinPageRequired';
        },

        rejectUnsupportedSource: function(source, sources) {
            var key = this.selectionCapabilityMessage(source, sources);
            if (!key) return false;
            var i18n = window.EpubBrowserI18n;
            Utils.showNotification(i18n && i18n.t ? i18n.t(key) : key, 'warning');
            if (highlighter) {
                (Array.isArray(sources) && sources.length ? sources : [source]).forEach(function(item) {
                    if (!item || !item.id) return;
                    try { highlighter.remove(item.id); } catch (e) {}
                });
            }
            if (window.getSelection) window.getSelection().removeAllRanges();
            return true;
        },

        getChapterIndexFromSource: function(source) {
            var pages = this.pdfPagesForSource(source);
            if (pages.length === 1) {
                var pageNumber = parseInt(pages[0].getAttribute('data-pdf-page-number'), 10);
                if (Number.isInteger(pageNumber) && pageNumber > 0) return pageNumber - 1;
            }
            var nodes = this.getHighlightNodesByAnnotationId(source && source.id);
            if (global.EpubAnnotationPosition) {
                return global.EpubAnnotationPosition.chapterIndexForNodes(nodes, currentChapterIndex);
            }
            return currentChapterIndex;
        },

        getChapterIndexForImage: function(image) {
            var section = image && image.closest && image.closest('.continuous-chapter');
            var index = section && parseInt(section.getAttribute('data-chapter-index'), 10);
            return Number.isInteger(index) ? index : currentChapterIndex;
        },

        getCanonicalSourceMetas: function(source, chapterIndex) {
            var startMeta = Utils.deepClone(source.startMeta);
            var endMeta = Utils.deepClone(source.endMeta);
            var section = this.getChapterSection(chapterIndex);
            var positioning = global.EpubAnnotationPosition;
            if (!section || !positioning) return { startMeta: startMeta, endMeta: endMeta };

            var root = this.getContentRoot();
            return {
                startMeta: positioning.toChapterMeta(startMeta, root, section) || startMeta,
                endMeta: positioning.toChapterMeta(endMeta, root, section) || endMeta
            };
        },

        normalizeAnnotation: function(raw) {
            if (!raw || !raw.id || !raw.startMeta || !raw.endMeta) return null;
            return {
                id: raw.id,
                book_hash: raw.book_hash,
                chapter_index: raw.chapter_index,
                text: raw.text || '',
                note: raw.note || '',
                startMeta: raw.startMeta,
                endMeta: raw.endMeta,
                color: raw.color || Settings.defaultColor,
                created_at: raw.created_at || Utils.getISOTime(),
                updated_at: raw.updated_at || raw.created_at || Utils.getISOTime()
            };
        },

        buildAnnotationFromSource: function(source, color, note) {
            if (source && source.imageNote && source.imageMeta) {
                return {
                    id: source.id || Utils.generateUUID(),
                    book_hash: currentBookHash,
                    chapter_index: typeof source.chapterIndex === 'number' ? source.chapterIndex : currentChapterIndex,
                    text: source.text || tr('imageNote'),
                    note: note || '',
                    startMeta: { image: source.imageMeta },
                    endMeta: { image: source.imageMeta },
                    color: color,
                    created_at: Utils.getISOTime(),
                    updated_at: Utils.getISOTime()
                };
            }
            var chapterIndex = this.getChapterIndexFromSource(source);
            var metas = this.getCanonicalSourceMetas(source, chapterIndex);
            return {
                id: source.id || Utils.generateUUID(),
                book_hash: currentBookHash,
                chapter_index: chapterIndex,
                text: source.text || '',
                note: note || '',
                startMeta: metas.startMeta,
                endMeta: metas.endMeta,
                color: color,
                created_at: Utils.getISOTime(),
                updated_at: Utils.getISOTime()
            };
        },

        isImageAnnotation: function(annotation) {
            return Boolean(annotation && annotation.startMeta && annotation.startMeta.image);
        },

        imageSource: function(image) {
            return String(image && (image.getAttribute('src') || image.currentSrc || image.src) || '');
        },

        imageMetaFor: function(image, chapterIndex) {
            var section = this.getChapterSection(chapterIndex);
            var root = section || this.getContentRoot();
            var source = this.imageSource(image);
            var images = Array.prototype.slice.call(root.querySelectorAll('img'));
            var ordinal = 0;
            for (var index = 0; index < images.length; index++) {
                if (images[index] === image) break;
                if (this.imageSource(images[index]) === source) ordinal += 1;
            }
            return {
                src: source,
                ordinal: ordinal,
                alt: String(image.getAttribute('alt') || image.getAttribute('title') || '')
            };
        },

        imageForMeta: function(meta, chapterIndex) {
            if (!meta || !meta.src) return null;
            var section = this.getChapterSection(chapterIndex);
            var root = section || this.getContentRoot();
            var matches = Array.prototype.slice.call(root.querySelectorAll('img')).filter(function(image) {
                return this.imageSource(image) === meta.src;
            }, this);
            return matches[Number(meta.ordinal) || 0] || null;
        },

        imageForAnnotationId: function(id) {
            for (var index = 0; index < this.annotations.length; index++) {
                var annotation = this.annotations[index];
                if (annotation.id !== id || !this.isImageAnnotation(annotation)) continue;
                return this.imageForMeta(annotation.startMeta.image, annotation.chapter_index);
            }
            return null;
        },

        imageNoteLabel: function(key) {
            var i18n = window.EpubBrowserI18n;
            return i18n && i18n.t ? i18n.t('annotations.' + key) : tr(key);
        },

        imageNoteContainer: function(image) {
            var subject = image;
            if (image.parentElement && image.parentElement.tagName === 'A') subject = image.parentElement;
            if (subject.parentElement && subject.parentElement.tagName === 'PICTURE') subject = subject.parentElement;
            if (subject.parentElement && subject.parentElement.classList.contains('image-annotation-anchor')) {
                return subject.parentElement;
            }
            var wrapper = document.createElement('span');
            wrapper.className = 'image-annotation-anchor';
            subject.parentNode.insertBefore(wrapper, subject);
            wrapper.appendChild(subject);
            return wrapper;
        },

        clearImageNotes: function() {
            this.imageNoteButtons.forEach(function(button) { button.remove(); });
            this.imageNoteButtons = [];
            this.getContentRoot().querySelectorAll('img.annotation-image-noted').forEach(function(image) {
                image.classList.remove('annotation-image-noted');
                image.removeAttribute('data-image-annotation-id');
            });
        },

        decorateImageNote: function(image, annotation) {
            if (!image) return;
            var self = this;
            var wrapper = this.imageNoteContainer(image);
            var button = document.createElement('button');
            button.className = 'image-annotation-button';
            button.type = 'button';
            button.disabled = !Settings.enabled;
            button.setAttribute('aria-disabled', Settings.enabled ? 'false' : 'true');
            var i18n = window.EpubBrowserI18n;
            var labelKey = annotation ? 'annotations.imageNote' : 'annotations.addImageNote';
            var buttonLabel = i18n && i18n.t ? i18n.t(labelKey) : this.imageNoteLabel(annotation ? 'imageNote' : 'addImageNote');
            button.setAttribute('aria-label', buttonLabel);
            button.title = buttonLabel;
            button.setAttribute('aria-pressed', annotation ? 'true' : 'false');
            button.appendChild(document.createElement('i')).className = annotation ? 'fas fa-sticky-note' : 'fas fa-plus';
            if (annotation) {
                image.classList.add('annotation-image-noted');
                image.setAttribute('data-image-annotation-id', annotation.id);
                wrapper.classList.add('has-image-note');
            } else {
                wrapper.classList.remove('has-image-note');
            }
            button.addEventListener('click', function(event) {
                event.preventDefault();
                event.stopPropagation();
                if (!Settings.enabled) return;
                if (annotation) {
                    self.showDetailDialog(annotation.id);
                    return;
                }
                var chapterIndex = self.getChapterIndexForImage(image);
                var meta = self.imageMetaFor(image, chapterIndex);
                var source = {
                    id: Utils.generateUUID(),
                    imageNote: true,
                    imageMeta: meta,
                    imageElement: image,
                    chapterIndex: chapterIndex,
                    text: meta.alt || self.imageNoteLabel('imageNote')
                };
                self.setPendingDraft(source);
                self.showCreateDialogFromSource(source);
            });
            wrapper.appendChild(button);
            this.imageNoteButtons.push(button);
        },

        renderImageNotes: function() {
            var self = this;
            this.clearImageNotes();
            var images = Array.prototype.slice.call(this.getContentRoot().querySelectorAll('img'));
            images.forEach(function(image) {
                var match = null;
                for (var index = 0; index < self.annotations.length; index++) {
                    var annotation = self.annotations[index];
                    if (!self.isImageAnnotation(annotation)) continue;
                    var meta = annotation.startMeta.image;
                    var candidate = self.imageForMeta(meta, annotation.chapter_index);
                    if (candidate === image) {
                        match = annotation;
                        break;
                    }
                }
                self.decorateImageNote(image, match);
            });
        },

        getAnnotationIdFromNode: function(node) {
            if (!node || !highlighter) return null;
            try {
                return highlighter.getIdByDom(node) || null;
            } catch (e) {
                return null;
            }
        },

        getHighlightNodesByAnnotationId: function(id) {
            if (!id || !highlighter) return [];
            try {
                return highlighter.getDoms(id) || [];
            } catch (e) {
                return [];
            }
        },

        bindHighlightHoverState: function(node, annotationId) {
            var self = this;
            if (!node || !annotationId || node.dataset.annotationHoverBound === annotationId) return;
            node.dataset.annotationHoverBound = annotationId;
            node.addEventListener('mouseenter', function() {
                self.getHighlightNodesByAnnotationId(annotationId).forEach(function(sib) {
                    sib.classList.add('annotation-hover-active');
                });
            });
            node.addEventListener('mouseleave', function() {
                self.getHighlightNodesByAnnotationId(annotationId).forEach(function(sib) {
                    sib.classList.remove('annotation-hover-active');
                });
            });
        },

        applyHighlightStyles: function(annotation, nodes) {
            var bgColor = Utils.addColorAlpha(annotation.color, 0.4);
            var hoverColor = Utils.addColorAlpha(annotation.color, 0.6);
            var borderColor = Utils.addColorAlpha(annotation.color, 0.8);
            var self = this;
            (nodes || []).forEach(function(node) {
                node.style.backgroundColor = bgColor;
                node.style.setProperty('--annotation-color', bgColor);
                node.style.setProperty('--annotation-hover-color', hoverColor);
                node.style.setProperty('--annotation-border-color', borderColor);
                self.bindHighlightHoverState(node, annotation.id);
            });
        },

        closeDialog: function() {
            this.detailLifecycle.invalidate();
            if (this.activeDialog) {
                this.activeDialog.remove();
                this.activeDialog = null;
            }
            if (this.outsideClickHandler) {
                document.removeEventListener('click', this.outsideClickHandler);
                this.outsideClickHandler = null;
            }
        },

        setPendingDraft: function(source) {
            if (!source || !source.id) return;
            this.pendingDraft = {
                id: source.id,
                source: source
            };
        },

        clearPendingDraftState: function() {
            this.pendingDraft = null;
        },

        cancelPendingDraft: function() {
            var draftId = this.pendingDraft && this.pendingDraft.id;
            this.closeDialog();
            this.clearPendingDraftState();
            if (draftId && highlighter) {
                try {
                    highlighter.remove(draftId);
                } catch (e) {}
            }
            if (window.getSelection) {
                window.getSelection().removeAllRanges();
            }
        },

        handleHighlightCreate: function(data) {
            var source = data && data.sources && data.sources[0];
            if (!source || !source.text) return;
            if (this.isRendering) return;
            if (this.rejectUnsupportedSource(source, data.sources)) return;
            if (!Settings.enabled) {
                if (source.id && highlighter) {
                    highlighter.remove(source.id);
                }
                return;
            }
            // Cancel previous pending draft before starting a new one
            if (this.pendingDraft) {
                var oldId = this.pendingDraft.id;
                this.closeDialog();
                this.clearPendingDraftState();
                if (oldId && highlighter) {
                    try {
                        highlighter.remove(oldId);
                    } catch (e) {}
                }
            }
            this.setPendingDraft(source);
            this.applyHighlightStyles({
                id: source.id,
                color: Settings.defaultColor,
                note: ''
            }, this.getHighlightNodesByAnnotationId(source.id));
            this.showCreateDialogFromSource(source);
        },

        showCreateDialogFromSource: function(source) {
            var self = this;
            if (this.rejectUnsupportedSource(source)) return;
            this.closeDialog();
            var dialog = document.createElement('div');
            dialog.className = 'annotation-selection-menu';
            dialog.setAttribute('role', 'toolbar');
            dialog.setAttribute('aria-label', tr('selectionActions'));
            var actionButton = function(key, handler, legacyClass) {
                var btn = document.createElement('button');
                btn.type = 'button';
                btn.className = 'annotation-selection-action' + (legacyClass ? ' ' + legacyClass : '');
                btn.textContent = tr(key);
                btn.setAttribute('aria-label', tr(key));
                btn.addEventListener('click', handler);
                dialog.appendChild(btn);
            };
            actionButton('copy', function() {
                Utils.copyText(source.text).catch(function() {
                    Utils.showNotification(tr('unableToCopy'), 'error');
                });
                self.cancelPendingDraft();
            }, 'annotation-btn-copy');
            actionButton('highlight', function() {
                if (self.rejectUnsupportedSource(source)) return;
                self.createAnnotationFromSource(source, Settings.defaultColor, '');
            });
            actionButton('noteAction', function() {
                if (self.rejectUnsupportedSource(source)) return;
                self.showNoteDialog(source);
            });
            if (global.EpubBrowserMode === 'server' && global.EpubBrowserDictionary) {
                actionButton('dictionary', function() {
                    if (self.rejectUnsupportedSource(source)) return;
                    var anchor = self.getSourceAnchorRect(source);
                    self.cancelPendingDraft();
                    global.EpubBrowserDictionary.open('dictionary', source.text, anchor);
                });
                actionButton('encyclopedia', function() {
                    if (self.rejectUnsupportedSource(source)) return;
                    var anchor = self.getSourceAnchorRect(source);
                    self.cancelPendingDraft();
                    global.EpubBrowserDictionary.open('encyclopedia', source.text, anchor);
                });
            }

            document.body.appendChild(dialog);
            self.positionFloatingDialog(dialog, self.getSourceAnchorRect(source));
            this.activeDialog = dialog;
            this.bindDialogOutsideClick(dialog, function() { self.cancelPendingDraft(); });
        },

        bindDialogOutsideClick: function(dialog, dismiss) {
            var self = this;
            setTimeout(function() {
                if (self.activeDialog !== dialog) return;
                self.outsideClickHandler = function(event) {
                    if (!dialog.contains(event.target)) dismiss();
                };
                document.addEventListener('click', self.outsideClickHandler);
            }, 10);
        },

        getSourceAnchorRect: function(source) {
            var nodes = source && source.id ? this.getHighlightNodesByAnnotationId(source.id) : [];
            var node = nodes[0] || (source && source.imageElement);
            if (!node || !node.getBoundingClientRect) return null;
            var rect = node.getBoundingClientRect();
            return {
                left: rect.left, top: rect.top, right: rect.right, bottom: rect.bottom,
                width: rect.width, height: rect.height
            };
        },

        getAnnotationAnchorRect: function(annotation) {
            var rect = this.getSourceAnchorRect(annotation);
            if (rect) return rect;
            var image = annotation && this.imageForAnnotationId(annotation.id);
            if (!image || !image.getBoundingClientRect) return null;
            rect = image.getBoundingClientRect();
            return {
                left: rect.left, top: rect.top, right: rect.right, bottom: rect.bottom,
                width: rect.width, height: rect.height
            };
        },

        positionFloatingDialog: function(dialog, anchorRect) {
            var margin = 12;
            var width = dialog.offsetWidth || 280;
            var height = dialog.offsetHeight || 160;
            var rect = anchorRect;
            var left = rect ? rect.left + (rect.width - width) / 2 : (window.innerWidth - width) / 2;
            var top = rect ? rect.bottom + margin : (window.innerHeight - height) / 2;
            left = Math.max(margin, Math.min(left, window.innerWidth - width - margin));
            if (rect && top + height > window.innerHeight - margin) top = rect.top - height - margin;
            top = Math.max(margin, Math.min(top, window.innerHeight - height - margin));
            dialog.style.left = Math.round(left) + 'px';
            dialog.style.top = Math.round(top) + 'px';
        },

        showNoteDialog: function(source) {
            var self = this;
            if (this.rejectUnsupportedSource(source)) return;
            this.closeDialog();
            var dialog = document.createElement('div');
            dialog.className = 'annotation-dialog annotation-note-dialog';
            dialog.setAttribute('role', 'dialog');
            dialog.setAttribute('aria-label', tr('noteAction'));
            var header = document.createElement('div');
            header.className = 'annotation-dialog-header';
            var title = document.createElement('span');
            title.textContent = tr('noteAction');
            header.appendChild(title);
            var close = document.createElement('button');
            close.type = 'button';
            close.className = 'annotation-dialog-close';
            close.textContent = '×';
            close.setAttribute('aria-label', tr('close'));
            header.appendChild(close);
            var body = document.createElement('div');
            body.className = 'annotation-dialog-body';
            var preview = document.createElement('div');
            preview.className = 'annotation-dialog-text';
            preview.textContent = String(source.text || '').slice(0, 160);
            body.appendChild(preview);
            var colorPicker = document.createElement('div');
            colorPicker.className = 'annotation-color-picker';
            var colorLabel = document.createElement('label');
            colorLabel.textContent = tr('color');
            var input = document.createElement('textarea');
            input.setAttribute('aria-label', tr('note'));
            var i18n = window.EpubBrowserI18n;
            input.placeholder = i18n && i18n.t ? i18n.t('annotations.noteOptional') : tr('noteOptional');
            var colors = document.createElement('div');
            colors.className = 'color-options';
            var selectedColor = Settings.defaultColor;
            createExpandableColorPicker(colors, selectedColor, function(color) {
                selectedColor = color;
            });
            colorPicker.appendChild(colorLabel);
            colorPicker.appendChild(colors);
            var noteInput = document.createElement('div');
            noteInput.className = 'annotation-note-input';
            var noteLabel = document.createElement('label');
            noteLabel.textContent = tr('note');
            noteInput.appendChild(noteLabel);
            noteInput.appendChild(input);
            body.appendChild(colorPicker);
            body.appendChild(noteInput);
            var footer = document.createElement('div');
            footer.className = 'annotation-dialog-footer';
            var cancel = document.createElement('button');
            cancel.type = 'button'; cancel.className = 'annotation-btn annotation-btn-cancel'; cancel.textContent = tr('cancel');
            var save = document.createElement('button');
            save.type = 'button'; save.className = 'annotation-btn annotation-btn-confirm'; save.textContent = tr('save');
            footer.appendChild(cancel); footer.appendChild(save);
            dialog.appendChild(header); dialog.appendChild(body); dialog.appendChild(footer);
            document.body.appendChild(dialog);
            this.positionFloatingDialog(dialog, this.getSourceAnchorRect(source));
            this.activeDialog = dialog;
            this.bindDialogOutsideClick(dialog, function() { self.cancelPendingDraft(); });
            input.focus();
            close.addEventListener('click', function() { self.cancelPendingDraft(); });
            cancel.addEventListener('click', function() { self.cancelPendingDraft(); });
            save.addEventListener('click', function() {
                if (self.rejectUnsupportedSource(source)) return;
                self.createAnnotationFromSource(source, selectedColor, input.value.trim());
            });
        },

        showDetailDialog: function(id) {
            var self = this;
            this.closeDialog();
            var dialogToken = this.detailLifecycle.begin();
            this.detailLifecycle.run(
                dialogToken,
                function() { return StorageManager.getById(id); },
                function(annotation) {
                annotation = self.normalizeAnnotation(annotation);
                if (!annotation) {
                    Utils.showNotification(tr('notFound'), 'warning');
                    return;
                }

                var textPreview = annotation.text.substring(0, 100) + (annotation.text.length > 100 ? '...' : '');
                var dialog = document.createElement('div');
                dialog.className = 'annotation-dialog annotation-detail-dialog';
                dialog.setAttribute('role', 'dialog');
                dialog.setAttribute('aria-label', tr('details'));
                dialog.innerHTML = '\
                    <div class="annotation-dialog-header">\
                        <strong>' + tr('details') + '</strong>\
                        <button class="annotation-dialog-close" title="' + tr('close') + '" aria-label="' + tr('close') + '">×</button>\
                    </div>\
                    <div class="annotation-dialog-body">\
                        <div class="annotation-dialog-text">' + Utils.escapeHtml(textPreview) + '</div>\
                        <div class="annotation-color-picker">\
                            <label>' + tr('color') + '</label>\
                            <div class="color-options"></div>\
                        </div>\
                        <div class="annotation-note-input">\
                            <label>' + tr('note') + '</label>\
                            <textarea placeholder="' + tr('addDescription') + '">' + Utils.escapeHtml(annotation.note) + '</textarea>\
                        </div>\
                        <div class="annotation-meta">\
                            <span>' + tr('created', { date: formatAnnotationDate(annotation.created_at) }) + '</span>\
                            <span class="annotation-updated"></span>\
                        </div>\
                    </div>\
                    <div class="annotation-dialog-footer">\
                        <button class="annotation-btn annotation-btn-delete"><i class="fas fa-trash"></i> ' + tr('delete') + '</button>\
                        <button class="annotation-btn annotation-btn-confirm">' + tr('save') + '</button>\
                    </div>';

                if (annotation.updated_at && annotation.updated_at !== annotation.created_at) {
                    dialog.querySelector('.annotation-updated').textContent = tr('updated', { date: formatAnnotationDate(annotation.updated_at) });
                }

                var colorOptions = dialog.querySelector('.color-options');
                createExpandableColorPicker(colorOptions, annotation.color);

                document.body.appendChild(dialog);
                dialog._epubAnchor = self.getAnnotationAnchorRect(annotation);
                self.positionFloatingDialog(dialog, dialog._epubAnchor);
                self.activeDialog = dialog;
                self.bindDialogOutsideClick(dialog, function() { self.closeDialog(); });

                var noteInput = dialog.querySelector('textarea');
                var textEl = dialog.querySelector('.annotation-dialog-text');

                textEl.style.cursor = 'pointer';
                textEl.title = tr('clickToCopy');
                textEl.addEventListener('click', function() {
                    var textarea = document.createElement('textarea');
                    textarea.value = annotation.text;
                    textarea.style.position = 'fixed';
                    textarea.style.opacity = '0';
                    document.body.appendChild(textarea);
                    textarea.select();
                    document.execCommand('copy');
                    document.body.removeChild(textarea);
                    Utils.showNotification(tr('textCopied'), 'success');
                });

                dialog.querySelector('.annotation-dialog-close').addEventListener('click', function() {
                    self.closeDialog();
                });
                dialog.querySelector('.annotation-btn-delete').addEventListener('click', async function() {
                    if (await window.EpubDialog.confirm({
                        title: tr('confirmDelete'),
                        message: tr('confirmDelete'),
                        confirmText: tr('delete'),
                        destructive: true
                    })) {
                        self.deleteAnnotation(annotation.id);
                        self.closeDialog();
                    }
                });
                var saveButton = dialog.querySelector('.annotation-btn-confirm');
                saveButton.addEventListener('click', function() {
                    var selectedColor = colorOptions.querySelector('.color-option.selected');
                    var color = selectedColor ? selectedColor.getAttribute('data-color') : annotation.color;
                    saveButton.disabled = true;
                    saveButton.setAttribute('aria-disabled', 'true');
                    self.detailLifecycle.runSave(
                        dialogToken,
                        function(updateOptions) {
                            return self.updateAnnotation(annotation.id, {
                                color: color,
                                note: noteInput.value.trim()
                            }, updateOptions);
                        },
                        function() {
                            if (self.activeDialog === dialog) self.closeDialog();
                        },
                        function(err) {
                            if (self.activeDialog !== dialog) return;
                            Utils.showNotification(tr('updateFailed', { error: err.message }), 'error');
                            saveButton.disabled = false;
                            saveButton.setAttribute('aria-disabled', 'false');
                        }
                    ).catch(function() {});
                });
            }, function(err) {
                Utils.showNotification(tr('loadFailed', { error: err.message }), 'error');
            }).catch(function() {});
        },

        createAnnotationFromSource: function(source, color, note) {
            var self = this;
            if (this.rejectUnsupportedSource(source)) return;
            var annotation = this.buildAnnotationFromSource(source, color, note);
            StorageManager.create(annotation).then(function() {
                self.annotations.push(annotation);
                self.applyHighlightStyles(annotation, self.getHighlightNodesByAnnotationId(annotation.id));
                if (self.isImageAnnotation(annotation)) self.renderImageNotes();
                self.clearPendingDraftState();
                self.closeDialog();
            }).catch(function(err) {
                self.cancelPendingDraft();
                Utils.showNotification(tr('addFailed', { error: err.message }), 'error');
            });
        },

        updateAnnotation: function(id, data, options) {
            var self = this;
            var updateData = {
                color: data.color,
                note: data.note,
                updated_at: Utils.getISOTime()
            };
            return StorageManager.update(id, updateData).then(function() {
                var updatedAnnotation = null;
                self.annotations = self.annotations.map(function(annotation) {
                    if (annotation.id !== id) return annotation;
                    annotation.color = data.color;
                    annotation.note = data.note;
                    annotation.updated_at = updateData.updated_at;
                    updatedAnnotation = annotation;
                    return annotation;
                });
                if (updatedAnnotation) {
                    self.applyHighlightStyles(updatedAnnotation, self.getHighlightNodesByAnnotationId(id));
                }
            }).catch(function(err) {
                if (!options || options.notifyFailure !== false) {
                    Utils.showNotification(tr('updateFailed', { error: err.message }), 'error');
                }
                throw err;
            });
        },

        deleteAnnotation: function(id) {
            var self = this;
            StorageManager.delete(id).then(function() {
                self.annotations = self.annotations.filter(function(annotation) {
                    return annotation.id !== id;
                });
                if (highlighter) {
                    highlighter.remove(id);
                }
                self.renderImageNotes();
            }).catch(function(err) {
                Utils.showNotification(tr('deleteFailed', { error: err.message }), 'error');
            });
        },

        normalizedHighlightText: function(text) {
            return (text || '').replace(/\s+/g, ' ').trim();
        },

        renderWithMetas: function(annotation, startMeta, endMeta, expectedSection) {
            if (!startMeta || !endMeta) return null;
            try {
                var source = highlighter.fromStore(startMeta, endMeta, annotation.text, annotation.id);
                var nodes = source ? this.getHighlightNodesByAnnotationId(annotation.id) : [];
                var renderedText = nodes.map(function(node) { return node.textContent || ''; }).join('');
                var isExpectedText = this.normalizedHighlightText(renderedText) === this.normalizedHighlightText(annotation.text);
                var isExpectedSection = !expectedSection || nodes.every(function(node) {
                    return expectedSection.contains(node);
                });
                if (!nodes.length || !isExpectedText || !isExpectedSection) {
                    if (highlighter) highlighter.remove(annotation.id);
                    return null;
                }
                this.applyHighlightStyles(annotation, nodes);
                return nodes;
            } catch (e) {
                if (highlighter) {
                    try { highlighter.remove(annotation.id); } catch (removeError) {}
                }
                return null;
            }
        },

        getTextPointMeta: function(node, offset, chapterRoot) {
            var parent = node && node.parentElement;
            if (!parent || !chapterRoot.contains(parent)) return null;
            while (parent !== chapterRoot && parent.classList && parent.classList.contains(CONFIG.ANNOTATION_CLASS)) {
                parent = parent.parentElement;
            }

            var parentIndex = -2;
            if (parent !== chapterRoot) {
                parentIndex = Array.prototype.indexOf.call(
                    chapterRoot.getElementsByTagName(parent.tagName),
                    parent
                );
                if (parentIndex === -1) return null;
            }

            var textOffset = 0;
            var walker = document.createTreeWalker(parent, 4, null, false);
            var current;
            while ((current = walker.nextNode())) {
                if (current === node) {
                    textOffset += offset;
                    return {
                        parentTagName: parent.tagName,
                        parentIndex: parentIndex,
                        textOffset: textOffset
                    };
                }
                textOffset += (current.nodeValue || '').length;
            }
            return null;
        },

        resolveLegacyPointMeta: function(meta, chapterRoot) {
            if (!meta || !meta.legacyXPath || !chapterRoot || !document.evaluate) return null;
            try {
                var expression = meta.legacyXPath.charAt(0) === '/'
                    ? '.' + meta.legacyXPath
                    : meta.legacyXPath;
                var result = document.evaluate(
                    expression,
                    chapterRoot,
                    null,
                    global.XPathResult ? global.XPathResult.FIRST_ORDERED_NODE_TYPE : 9,
                    null
                );
                var node = result && result.singleNodeValue;
                if (!node) return null;
                return this.getTextPointMeta(
                    node,
                    Math.max(0, Number(meta.legacyOffset) || 0),
                    chapterRoot
                );
            } catch (error) {
                return null;
            }
        },

        findTextAnchor: function(annotation, chapterRoot) {
            if (!annotation.text || !chapterRoot) return null;
            var walker = document.createTreeWalker(chapterRoot, 4, null, false);
            var segments = [];
            var fullText = '';
            var node;
            while ((node = walker.nextNode())) {
                var parent = node.parentElement;
                if (!parent) continue;
                var excluded = parent.closest && parent.closest('pre, code, a, .chapter-separator, script, style');
                if (excluded) continue;
                var value = node.nodeValue || '';
                if (!value) continue;
                segments.push({ node: node, start: fullText.length, end: fullText.length + value.length });
                fullText += value;
            }

            var matches = [];
            var from = 0;
            while (matches.length < 100) {
                var match = fullText.indexOf(annotation.text, from);
                if (match === -1) break;
                matches.push(match);
                from = match + Math.max(annotation.text.length, 1);
            }
            if (!matches.length) return null;

            var pointAt = function(position, isEnd) {
                for (var i = 0; i < segments.length; i++) {
                    var segment = segments[i];
                    if ((!isEnd && position >= segment.start && position < segment.end) ||
                        (isEnd && position > segment.start && position <= segment.end)) {
                        return { node: segment.node, offset: position - segment.start };
                    }
                }
                return null;
            };
            var candidates = [];
            for (var i = 0; i < matches.length; i++) {
                var startPoint = pointAt(matches[i], false);
                var endPoint = pointAt(matches[i] + annotation.text.length, true);
                if (!startPoint || !endPoint) continue;
                var startMeta = this.getTextPointMeta(startPoint.node, startPoint.offset, chapterRoot);
                var endMeta = this.getTextPointMeta(endPoint.node, endPoint.offset, chapterRoot);
                if (!startMeta || !endMeta) continue;
                var score = 0;
                if (annotation.startMeta && annotation.startMeta.parentTagName === startMeta.parentTagName) {
                    score += Math.abs(annotation.startMeta.parentIndex - startMeta.parentIndex);
                } else {
                    score += 10000;
                }
                if (annotation.endMeta && annotation.endMeta.parentTagName === endMeta.parentTagName) {
                    score += Math.abs(annotation.endMeta.parentIndex - endMeta.parentIndex);
                } else {
                    score += 10000;
                }
                candidates.push({ startMeta: startMeta, endMeta: endMeta, score: score });
            }
            candidates.sort(function(a, b) { return a.score - b.score; });
            if (!candidates.length || (candidates[1] && candidates[1].score === candidates[0].score)) return null;
            return candidates[0];
        },

        getChapterIndexFromSection: function(section) {
            if (!section || !section.getAttribute) return currentChapterIndex;
            var index = parseInt(section.getAttribute('data-chapter-index'), 10);
            return isNaN(index) ? currentChapterIndex : index;
        },

        repairAnnotationPosition: function(annotation, chapterIndex, startMeta, endMeta) {
            annotation.chapter_index = chapterIndex;
            annotation.startMeta = Utils.deepClone(startMeta);
            annotation.endMeta = Utils.deepClone(endMeta);
            StorageManager.update(annotation.id, {
                chapter_index: chapterIndex,
                startMeta: startMeta,
                endMeta: endMeta
            }).catch(function(err) {
                console.warn('Could not persist repaired annotation position:', err);
            });
        },

        renderHighlight: function(annotation) {
            if (this.isImageAnnotation(annotation)) return true;
            if (!highlighter || !annotation) return false;
            var root = this.getContentRoot();
            var sections = this.getContinuousChapterSections();
            var isContinuous = sections.length > 0;
            var preferredSection = isContinuous ? this.getChapterSection(annotation.chapter_index) : root;
            if (!preferredSection) return null;

            var positioning = global.EpubAnnotationPosition;
            var startMeta = annotation.startMeta;
            var endMeta = annotation.endMeta;
            var migratedLegacyPosition = false;
            var legacyStartMeta = this.resolveLegacyPointMeta(startMeta, preferredSection);
            var legacyEndMeta = this.resolveLegacyPointMeta(endMeta, preferredSection);
            if (legacyStartMeta && legacyEndMeta) {
                startMeta = annotation.startMeta = legacyStartMeta;
                endMeta = annotation.endMeta = legacyEndMeta;
                migratedLegacyPosition = true;
            }
            if (isContinuous && positioning) {
                startMeta = positioning.toRootMeta(annotation.startMeta, root, preferredSection);
                endMeta = positioning.toRootMeta(annotation.endMeta, root, preferredSection);
            }
            if (this.renderWithMetas(annotation, startMeta, endMeta, preferredSection)) {
                if (migratedLegacyPosition) {
                    this.repairAnnotationPosition(
                        annotation,
                        isContinuous ? this.getChapterIndexFromSection(preferredSection) : currentChapterIndex,
                        annotation.startMeta,
                        annotation.endMeta
                    );
                }
                return true;
            }

            // Older continuous-reading annotations used full-root indices. Try
            // those once before falling back to text-based re-anchoring.
            if (isContinuous && positioning) {
                var legacyNodes = this.renderWithMetas(annotation, annotation.startMeta, annotation.endMeta, null);
                if (legacyNodes) {
                    var actualSection = legacyNodes[0].closest && legacyNodes[0].closest('.continuous-chapter');
                    var repairedStart = actualSection && positioning.toChapterMeta(annotation.startMeta, root, actualSection);
                    var repairedEnd = actualSection && positioning.toChapterMeta(annotation.endMeta, root, actualSection);
                    if (actualSection && repairedStart && repairedEnd) {
                        this.repairAnnotationPosition(
                            annotation,
                            this.getChapterIndexFromSection(actualSection),
                            repairedStart,
                            repairedEnd
                        );
                    }
                    return true;
                }
            }

            var candidateSections = [preferredSection];
            if (isContinuous) {
                sections.forEach(function(section) {
                    if (section !== preferredSection) candidateSections.push(section);
                });
            }
            for (var i = 0; i < candidateSections.length; i++) {
                var section = candidateSections[i];
                var anchor = this.findTextAnchor(annotation, section);
                if (!anchor) continue;
                var renderStart = anchor.startMeta;
                var renderEnd = anchor.endMeta;
                if (isContinuous && positioning) {
                    renderStart = positioning.toRootMeta(anchor.startMeta, root, section);
                    renderEnd = positioning.toRootMeta(anchor.endMeta, root, section);
                }
                if (!this.renderWithMetas(annotation, renderStart, renderEnd, section)) continue;
                this.repairAnnotationPosition(
                    annotation,
                    isContinuous ? this.getChapterIndexFromSection(section) : currentChapterIndex,
                    anchor.startMeta,
                    anchor.endMeta
                );
                return true;
            }
            return false;
        },

        clearHighlights: function() {
            if (highlighter) {
                highlighter.removeAll();
            }
            document.querySelectorAll('.' + CONFIG.ANNOTATION_CLASS).forEach(function(el) {
                var parent = el.parentNode;
                if (!parent) return;
                while (el.firstChild) {
                    parent.insertBefore(el.firstChild, el);
                }
                parent.removeChild(el);
            });
        },

        renderAll: function(isRetry) {
            var self = this;
            var renderVersion = ++this.renderVersion;
            var isContinuous = this.getContinuousChapterSections().length > 0;
            this.isRendering = true;
            this.cancelPendingDraft();
            this.clearHighlights();
            this.clearImageNotes();
            var loadAnnotations = isContinuous
                ? StorageManager.getByBook(currentBookHash)
                : StorageManager.getByChapter(currentBookHash, currentChapterIndex);
            return loadAnnotations.then(function(annotations) {
                if (renderVersion !== self.renderVersion) return;
                self.annotations = (annotations || []).map(function(annotation) {
                    return self.normalizeAnnotation(annotation);
                }).filter(Boolean).sort(function(a, b) {
                    return (b.text || '').length - (a.text || '').length;
                });
                self.renderImageNotes();
                var failedToRestore = false;
                self.annotations.forEach(function(annotation) {
                    if (!self.isImageAnnotation(annotation) && highlighter && self.renderHighlight(annotation) === false) {
                        failedToRestore = true;
                    }
                });
                if (!failedToRestore) return;
                if (self.hasPendingPdfAnnotationContent()) return;
                if (!isRetry) {
                    requestAnimationFrame(function() {
                        requestAnimationFrame(function() {
                            if (renderVersion === self.renderVersion) self.renderAll(true);
                        });
                    });
                    return;
                }
                if (!isContinuous) {
                    Utils.showNotification(tr('restoreFailed'), 'error');
                }
            }).catch(function(err) {
                console.error('Failed to load annotations:', err);
                if (renderVersion === self.renderVersion) {
                    Utils.showNotification(tr('loadAllFailed', { error: err.message }), 'error');
                }
            }).finally(function() {
                if (renderVersion === self.renderVersion) self.isRendering = false;
            });
        }
    };
    
    var AnnotationSettingsMarkup = {
        colorHeader: function() {
            return '\
                <span class="color-header-label">\
                    <span data-i18n="annotations.colors">' + tr('colors') + '</span>\
                    <span class="color-tip-reorder" data-tooltip="' + tr('colorReorderTip') + '" aria-label="' + tr('colorReorderTip') + '" data-i18n-data-tip="annotations.colorReorderTip" data-i18n-aria-label="annotations.colorReorderTip"><i class="fas fa-info-circle"></i></span>\
                </span>\
                <button class="color-add-btn" title="' + tr('addColor') + '" aria-label="' + tr('addColor') + '" data-i18n-title="annotations.addColor" data-i18n-aria-label="annotations.addColor"><i class="fas fa-plus"></i></button>';
        },
        colorDeleteButton: function(color, selected) {
            return '\
                <button class="color-option' + (selected ? ' selected' : '') + '" style="background-color: ' + color + '"></button>\
                <button class="color-delete-btn" title="' + tr('deleteColor') + '" aria-label="' + tr('deleteColor') + '" data-i18n-title="annotations.deleteColor" data-i18n-aria-label="annotations.deleteColor"><i class="fas fa-times"></i></button>';
        }
    };

    // ========== Settings Tab Module ==========
    var SettingsTab = {
        initialized: false,
        backendChecking: false,
        
        // Create tab content
        createContent: function() {
            var self = this;
            
            // Create tab button
            var tabBtn = document.createElement('button');
            tabBtn.className = 'settings-tab';
            tabBtn.setAttribute('data-tab', 'annotation');
            tabBtn.innerHTML = '<i class="fas fa-highlighter"></i><span data-i18n="annotations.tab">' + tr('tab') + '</span>';
            
            // Create tab panel
            var tabPanel = document.createElement('div');
            tabPanel.className = 'settings-tab-panel';
            tabPanel.id = 'annotation-tab';
            tabPanel.innerHTML = '\
                <div class="settings-group">\
                    <label class="settings-switch">\
                        <input type="checkbox" id="annotationEnabled" ' + (Settings.enabled ? 'checked' : '') + '>\
                        <span class="switch-slider"></span>\
                        <span class="switch-text" data-i18n="annotations.enabled">' + tr('enabled') + '</span>\
                    </label>\
                </div>\
                <div class="settings-group">\
                    <label class="settings-label">\
                        <span data-i18n="annotations.defaultColor">' + tr('defaultColor') + '</span>\
                        <span class="color-tip-default" data-tooltip="' + tr('defaultColorTip') + '" aria-label="' + tr('defaultColorTip') + '" data-i18n-data-tip="annotations.defaultColorTip" data-i18n-aria-label="annotations.defaultColorTip"><i class="fas fa-info-circle"></i></span>\
                    </label>\
                    <div class="color-picker-default"></div>\
                </div>\
                <div class="settings-group">\
                    <label class="settings-label" data-i18n="annotations.exportData">' + tr('exportData') + '</label>\
                    <div class="export-buttons">\
                        <button class="annotation-btn annotation-btn-secondary" id="exportBookBtn">\
                            <i class="fas fa-download"></i> <span data-i18n="annotations.exportBook">' + tr('exportBook') + '</span>\
                        </button>\
                        <button class="annotation-btn annotation-btn-secondary" id="exportAllBtn">\
                            <i class="fas fa-download"></i> <span data-i18n="annotations.exportAll">' + tr('exportAll') + '</span>\
                        </button>\
                    </div>\
                </div>';
            
            // 插入Tab
            var tabsContainer = document.querySelector('.settings-tabs');
            var panelsContainer = document.querySelector('.settings-content');
            
            if (tabsContainer && panelsContainer) {
                tabsContainer.appendChild(tabBtn);
                panelsContainer.appendChild(tabPanel);
                
                this.bindEvents(tabBtn, tabPanel);
                this.initColorPicker(tabPanel);
                
                // Re-bind tab switch events for all tabs (including the new one)
                this.rebindTabEvents();
            }
        },
        
        // Re-bind tab switch events for all tabs
        rebindTabEvents: function() {
            var allTabs = document.querySelectorAll('.settings-tab');
            
            // Add new click listeners (use once flag to avoid duplicates)
            allTabs.forEach(function(tab) {
                if (tab.dataset.tabBound) return;
                tab.dataset.tabBound = '1';
                tab.addEventListener('click', function() {
                    var tabId = this.getAttribute('data-tab');
                    
                    // Remove active from all tabs and panels
                    document.querySelectorAll('.settings-tab').forEach(function(t) {
                        t.classList.remove('active');
                    });
                    document.querySelectorAll('.settings-tab-panel').forEach(function(p) {
                        p.classList.remove('active');
                    });
                    
                    // Add active to current tab and panel
                    this.classList.add('active');
                    var panel = document.getElementById(tabId + '-tab');
                    if (panel) {
                        panel.classList.add('active');
                    }
                });
            });
        },
        
        // Bind events
        bindEvents: function(tabBtn, tabPanel) {
            var self = this;
            
            // Listen for settings modal close to close migration dialog
            var settingsModal = document.getElementById('settingsModal');
            if (settingsModal) {
                var observer = new MutationObserver(function(mutations) {
                    mutations.forEach(function(mutation) {
                        if (mutation.attributeName === 'class' && 
                            !settingsModal.classList.contains('show')) {
                            // Settings modal closed, close migration dialog if open
                            var migrationDialog = document.querySelector('.annotation-migration-dialog');
                            if (migrationDialog) {
                                migrationDialog.remove();
                            }
                        }
                    });
                });
                observer.observe(settingsModal, { attributes: true });
            }
            
            // Enable toggle
            var enabledCheckbox = tabPanel.querySelector('#annotationEnabled');
            enabledCheckbox.addEventListener('change', function() {
                Settings.enabled = this.checked;
                Settings.save();
                HighlightInteraction.syncEnabledState();
                if (Settings.enabled) {
                    HighlightInteraction.renderAll();
                } else {
                    HighlightInteraction.clearHighlights();
                }
                Utils.showNotification(tr(Settings.enabled ? 'enabledNotice' : 'disabledNotice'), 'info');
            });
            
            // 导出按钮
            var exportBookBtn = tabPanel.querySelector('#exportBookBtn');
            var exportAllBtn = tabPanel.querySelector('#exportAllBtn');
            
            exportBookBtn.addEventListener('click', function() {
                Exporter.exportBook(currentBookHash);
            });
            
            exportAllBtn.addEventListener('click', function() {
                Exporter.exportAll();
            });
        },
        
        // Initialize color picker with drag-sort and add color
        initColorPicker: function(tabPanel) {
            var picker = tabPanel.querySelector('.color-picker-default');
            var self = this;
            if (!picker) return;
            
            // Clear existing
            picker.innerHTML = '';
            
            // Create header with info and add button
            var header = document.createElement('div');
            header.className = 'color-picker-header';
            header.innerHTML = AnnotationSettingsMarkup.colorHeader();
            picker.appendChild(header);
            
            // Create colors container
            var colorsContainer = document.createElement('div');
            colorsContainer.className = 'color-picker-colors';
            picker.appendChild(colorsContainer);
            
            // Render colors
            var colors = CONFIG.getColors();
            var renderColors = function() {
                colorsContainer.innerHTML = '';
                var currentColors = CONFIG.getColors();
                
                for (var i = 0; i < currentColors.length; i++) {
                    var color = currentColors[i];
                    var btn = document.createElement('div');
                    btn.className = 'color-option-wrapper';
                    btn.setAttribute('draggable', 'true');
                    btn.setAttribute('data-color', color);
                    btn.innerHTML = AnnotationSettingsMarkup.colorDeleteButton(
                        color,
                        color === Settings.defaultColor
                    );
                    
                    var colorBtn = btn.querySelector('.color-option');
                    colorBtn.addEventListener('click', function(e) {
                        var wrapper = this.closest('.color-option-wrapper');
                        var c = wrapper.getAttribute('data-color');
                        colorsContainer.querySelectorAll('.color-option').forEach(function(b) {
                            b.classList.remove('selected');
                        });
                        this.classList.add('selected');
                        Settings.defaultColor = c;
                        Settings.save();
                    });
                    
                    var deleteBtn = btn.querySelector('.color-delete-btn');
                    deleteBtn.addEventListener('click', function(e) {
                        e.stopPropagation();
                        var wrapper = this.closest('.color-option-wrapper');
                        var c = wrapper.getAttribute('data-color');
                        
                        // Add to deleted colors (tracks both base and custom colors)
                        if (!Settings.deletedColors) Settings.deletedColors = [];
                        if (Settings.deletedColors.indexOf(c) === -1) {
                            Settings.deletedColors.push(c);
                        }
                        // Remove from custom colors and color order
                        var idx = Settings.customColors.indexOf(c);
                        if (idx !== -1) Settings.customColors.splice(idx, 1);
                        idx = Settings.colorOrder.indexOf(c);
                        if (idx !== -1) Settings.colorOrder.splice(idx, 1);
                        Settings.save();
                        renderColors();
                    });
                    
                    // Drag events
                    btn.addEventListener('dragstart', function(e) {
                        e.dataTransfer.setData('text/plain', this.getAttribute('data-color'));
                        this.classList.add('dragging');
                    });
                    
                    btn.addEventListener('dragend', function() {
                        this.classList.remove('dragging');
                    });
                    
                    btn.addEventListener('dragover', function(e) {
                        e.preventDefault();
                        this.classList.add('drag-over');
                    });
                    
                    btn.addEventListener('dragleave', function() {
                        this.classList.remove('drag-over');
                    });
                    
                    btn.addEventListener('drop', function(e) {
                        e.preventDefault();
                        this.classList.remove('drag-over');
                        var draggedColor = e.dataTransfer.getData('text/plain');
                        var targetColor = this.getAttribute('data-color');
                        
                        if (draggedColor === targetColor) return;
                        
                        // Reorder
                        var colors = CONFIG.getColors();
                        var fromIdx = colors.indexOf(draggedColor);
                        var toIdx = colors.indexOf(targetColor);
                        
                        if (fromIdx !== -1 && toIdx !== -1) {
                            colors.splice(fromIdx, 1);
                            colors.splice(toIdx, 0, draggedColor);
                            Settings.colorOrder = colors;
                            Settings.save();
                            renderColors();
                        }
                    });
                    
                    colorsContainer.appendChild(btn);
                }
            };
            
            renderColors();
            
            // Add color button
            var addBtn = header.querySelector('.color-add-btn');
            addBtn.addEventListener('click', function() {
                self.showAddColorDialog(tabPanel, renderColors);
            });
        },
        
        // Show add color dialog
        showAddColorDialog: function(tabPanel, onComplete) {
            var self = this;
            var existing = document.querySelector('.annotation-add-color-dialog');
            if (existing) existing.remove();
            
            var dialog = document.createElement('div');
            dialog.className = 'annotation-dialog annotation-add-color-dialog';
            dialog.innerHTML = '\
                <div class="annotation-dialog-header">\
                    <span><i class="fas fa-palette"></i> ' + tr('addColor') + '</span>\
                    <button class="annotation-dialog-close" title="' + tr('close') + '" aria-label="' + tr('close') + '"><i class="fas fa-times"></i></button>\
                </div>\
                <div class="annotation-dialog-body">\
                    <div class="color-input-row">\
                        <input type="color" id="colorPickerInput" value="#FF5722">\
                        <input type="text" id="colorHexInput" value="#FF5722" maxlength="7" placeholder="' + tr('hexPlaceholder') + '" aria-label="' + tr('hexColor') + '">\
                    </div>\
                    <div class="preset-colors">\
                        <button class="preset-color" style="background:#FF5722"></button>\
                        <button class="preset-color" style="background:#E91E63"></button>\
                        <button class="preset-color" style="background:#673AB7"></button>\
                        <button class="preset-color" style="background:#3F51B5"></button>\
                        <button class="preset-color" style="background:#009688"></button>\
                        <button class="preset-color" style="background:#8BC34A"></button>\
                        <button class="preset-color" style="background:#CDDC39"></button>\
                        <button class="preset-color" style="background:#607D8B"></button>\
                    </div>\
                </div>\
                <div class="annotation-dialog-footer">\
                    <button class="annotation-btn annotation-btn-cancel">' + tr('cancel') + '</button>\
                    <button class="annotation-btn annotation-btn-confirm">' + tr('add') + '</button>\
                </div>';
            
            document.body.appendChild(dialog);
            
            // Position dialog near the settings modal
            var settingsModal = document.getElementById('settingsModal');
            if (settingsModal) {
                var modalRect = settingsModal.getBoundingClientRect();
                dialog.style.left = Math.min(modalRect.left + 20, window.innerWidth - 320) + 'px';
                dialog.style.top = Math.min(modalRect.top + 50, window.innerHeight - 400) + 'px';
            } else {
                dialog.style.left = '50%';
                dialog.style.top = '50%';
                dialog.style.transform = 'translate(-50%, -50%)';
            }
            
            var colorInput = dialog.querySelector('#colorPickerInput');
            var hexInput = dialog.querySelector('#colorHexInput');
            var presetColors = dialog.querySelectorAll('.preset-color');
            var closeBtn = dialog.querySelector('.annotation-dialog-close');
            var cancelBtn = dialog.querySelector('.annotation-btn-cancel');
            var confirmBtn = dialog.querySelector('.annotation-btn-confirm');
            
            var closeDialog = function() {
                dialog.remove();
                if (onComplete) onComplete();
            };
            
            colorInput.addEventListener('input', function() {
                hexInput.value = this.value;
            });
            
            hexInput.addEventListener('input', function() {
                if (/^#[0-9A-Fa-f]{6}$/.test(this.value)) {
                    colorInput.value = this.value;
                }
            });
            
            presetColors.forEach(function(btn) {
                btn.addEventListener('click', function() {
                    var color = this.style.backgroundColor;
                    // Convert rgb to hex
                    var match = color.match(/rgb\((\d+),\s*(\d+),\s*(\d+)\)/);
                    if (match) {
                        var hex = '#' + [match[1], match[2], match[3]].map(function(x) {
                            return parseInt(x).toString(16).padStart(2, '0');
                        }).join('');
                        colorInput.value = hex;
                        hexInput.value = hex;
                    }
                });
            });
            
            closeBtn.addEventListener('click', closeDialog);
            cancelBtn.addEventListener('click', closeDialog);
            confirmBtn.addEventListener('click', function() {
                var color = hexInput.value.toUpperCase();
                if (!/^#[0-9A-F]{6}$/.test(color)) {
                    Utils.showNotification(tr('invalidHex'), 'warning');
                    return;
                }
                colorInput.value = color;
                
                // Add to custom colors
                if (Settings.customColors.indexOf(color) === -1) {
                    Settings.customColors.push(color);
                }
                var deletedIdx = Settings.deletedColors.indexOf(color);
                if (deletedIdx !== -1) Settings.deletedColors.splice(deletedIdx, 1);
                Settings.save();
                
                closeDialog();
            });
            
            // Click outside to close
            setTimeout(function() {
                var handler = function(e) {
                    if (!dialog.contains(e.target)) {
                        document.removeEventListener('click', handler);
                        closeDialog();
                    }
                };
                document.addEventListener('click', handler);
            }, 10);
        },
        
        // Check backend status
        checkBackendStatus: function() {
            var self = this;
            var statusEl = document.getElementById('backendStatus');
            var backendOption = document.getElementById('storageOptionBackend');
            
            if (!statusEl || !backendOption) return;
            
            this.backendChecking = true;
            statusEl.textContent = tr('checking');
            
            StorageManager.isBackendAvailable().then(function(result) {
                var available = result.available;
                Settings.backendAvailable = available;
                self.backendChecking = false;
                
                if (available) {
                    var session = window.EpubBrowserAuth && window.EpubBrowserAuth.getSession
                        ? window.EpubBrowserAuth.getSession()
                        : null;
                    statusEl.textContent = session && session.user
                        ? tr('connectedUser', { username: session.user.username })
                        : tr('connectedAccount');
                    statusEl.className = 'storage-option-status connected';
                    backendOption.classList.remove('disabled');
                } else {
                    statusEl.textContent = tr('disconnected');
                    statusEl.className = 'storage-option-status disconnected';
                    backendOption.classList.add('disabled');
                }
            });
        },
        
        // Revert radio button back to current storage type
        revertStorageRadio: function(targetType) {
            var radio = document.querySelector('input[name="annotationStorage"][value="' + targetType + '"]');
            if (radio) {
                radio.checked = true;
            }
        },
        
        // Show migration dialog
        showMigrationDialog: function(fromType, toType) {
            var self = this;
            
            // Create migration dialog
            var dialog = document.createElement('div');
            dialog.className = 'annotation-dialog annotation-migration-dialog';
            dialog.innerHTML = '\
                <div class="annotation-dialog-header">\
                    <span><i class="fas fa-exchange-alt"></i> ' + tr('dataMigration') + '</span>\
                </div>\
                <div class="annotation-dialog-body">\
                    <p>' + tr('migrationDescription') + '</p>\
                    <p id="migrationStatus">' + tr('countingData') + '</p>\
                </div>\
                <div class="annotation-dialog-footer">\
                    <button class="annotation-btn annotation-btn-secondary" id="migrationCancel">' + tr('cancel') + '</button>\
                    <button class="annotation-btn annotation-btn-secondary" id="migrationSkip">' + tr('skip') + '</button>\
                    <button class="annotation-btn annotation-btn-confirm" id="migrationConfirm">' + tr('migrate') + '</button>\
                </div>';
            
            document.body.appendChild(dialog);
            
            // Position
            dialog.style.left = '50%';
            dialog.style.top = '50%';
            dialog.style.transform = 'translate(-50%, -50%)';
            
            // Count data
            StorageManager.getAll().then(function(data) {
                var count = data ? data.length : 0;
                var statusEl = dialog.querySelector('#migrationStatus');
                statusEl.textContent = tr('currentData', { count: count });
            });
            
            // Bind events
            var cancelBtn = dialog.querySelector('#migrationCancel');
            var skipBtn = dialog.querySelector('#migrationSkip');
            var confirmBtn = dialog.querySelector('#migrationConfirm');
            
            cancelBtn.addEventListener('click', function() {
                // Cancel switch, restore original selection
                self.revertStorageRadio(fromType);
                dialog.remove();
            });
            
            skipBtn.addEventListener('click', function() {
                self.finishStorageChange(toType, false);
                dialog.remove();
            });
            
            confirmBtn.addEventListener('click', function() {
                var statusEl = dialog.querySelector('#migrationStatus');
                statusEl.innerHTML = '<div class="migration-progress"><div class="migration-progress-bar"><div class="migration-progress-fill" style="width:0%"></div></div><span>' + tr('migrating') + '</span></div>';
                
                self.finishStorageChange(toType, true, function(current, total) {
                    var fill = dialog.querySelector('.migration-progress-fill');
                    var text = dialog.querySelector('.migration-progress span');
                    if (fill) fill.style.width = Math.round(current / total * 100) + '%';
                    if (text) text.textContent = tr('migratingProgress', { current: current, total: total });
                }).then(function() {
                    dialog.remove();
                });
            });
        },
        
        // Finish storage change
        finishStorageChange: function(newType, shouldMigrate, onProgress) {
            var self = this;
            
            return StorageManager.setStorageType(newType, shouldMigrate, onProgress).then(function() {
                Settings.storageType = newType;
                Settings.save();
                
                // Refresh backend status display
                self.checkBackendStatus();
                
                var i18n = window.EpubBrowserI18n;
                Utils.showNotification(i18n && i18n.t ? i18n.t('annotations.storageLocationChanged') : tr('storageLocationChanged'), 'success');
                
                // Re-render annotations
                HighlightInteraction.renderAll();
            });
        }
    };
    
    // ========== Export Module ==========
    var Exporter = {
        // Export book data
        exportBook: function(bookHash) {
            var self = this;
            
            StorageManager.getByBook(bookHash).then(function(annotations) {
                var data = {
                    version: '1.0',
                    exported_at: Utils.getISOTime(),
                    type: 'book',
                    book_hash: bookHash,
                    count: annotations ? annotations.length : 0,
                    annotations: annotations || []
                };
                
                self.downloadJSON(data, 'annotations_' + bookHash + '_' + Date.now() + '.json');
                Utils.showNotification(tr('exported', { count: annotations ? annotations.length : 0 }), 'success');
            }).catch(function(err) {
                Utils.showNotification(tr('exportFailed', { error: err.message }), 'error');
            });
        },
        
        // Export all data
        exportAll: function() {
            var self = this;
            
            StorageManager.getAll().then(function(annotations) {
                var data = {
                    version: '1.0',
                    exported_at: Utils.getISOTime(),
                    type: 'all',
                    count: annotations ? annotations.length : 0,
                    annotations: annotations || []
                };
                
                self.downloadJSON(data, 'annotations_all_' + Date.now() + '.json');
                Utils.showNotification(tr('exported', { count: annotations ? annotations.length : 0 }), 'success');
            }).catch(function(err) {
                Utils.showNotification(tr('exportFailed', { error: err.message }), 'error');
            });
        },
        
        // Download JSON file
        downloadJSON: function(data, filename) {
            var json = JSON.stringify(data, null, 2);
            var blob = new Blob([json], { type: 'application/json' });
            var url = URL.createObjectURL(blob);
            
            var a = document.createElement('a');
            a.href = url;
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
        }
    };
    
    // ========== Main Module ==========
    var AnnotationModule = {
        initialized: false,

        bindContentReadyRefresh: function() {
            if (contentReadyListenerBound || typeof global.addEventListener !== 'function') return;
            contentReadyListenerBound = true;
            var self = this;
            global.addEventListener('epub-browser:annotation-content-ready', function(event) {
                var detail = event && event.detail;
                if (!detail || !detail.root) return;
                if (!self.initialized) {
                    pendingContentRefreshDetails.push(detail);
                    return;
                }
                rememberContentReadyRefresh(detail, self.refresh());
            });
        },
        
        // Initialize
        init: function(options) {
            options = options || {};
            currentBookHash = options.bookHash || '';
            currentChapterIndex = options.chapterIndex || 0;
            this.bindContentReadyRefresh();

            if (this.initialized) {
                var refresh = HighlightInteraction.setContext(currentBookHash, currentChapterIndex);
                HighlightInteraction.syncEnabledState();
                return refresh;
            }
            
            // Load settings
            Settings.load();
            
            // Initialize storage
            var self = this;
            return StorageManager.init().then(function() {
                // Initialize interaction
                HighlightInteraction.init();
                
                // Create settings tab
                SettingsTab.createContent();
                
                return HighlightInteraction.setContext(currentBookHash, currentChapterIndex);
            }).then(function() {
                self.initialized = true;
                if (pendingContentRefreshDetails.length) {
                    var details = pendingContentRefreshDetails.slice();
                    pendingContentRefreshDetails = [];
                    var refreshPromise = Promise.resolve(self.refresh());
                    details.forEach(function(detail) {
                        rememberContentReadyRefresh(detail, refreshPromise);
                    });
                    return refreshPromise;
                }
            }).catch(function(err) {
                console.error('Annotation module init failed:', err);
                throw err;
            });
        },
        
        // Destroy
        destroy: function() {
            HighlightInteraction.cancelPendingDraft();
            HighlightInteraction.closeDialog();
            HighlightInteraction.clearHighlights();
            HighlightInteraction.clearImageNotes();
            if (highlighter && HighlightInteraction.isListening) {
                highlighter.stop();
                HighlightInteraction.isListening = false;
            }
            this.initialized = false;
        },
        
        // Refresh
        refresh: function() {
            return HighlightInteraction.renderAll();
        },
        
        // Set book info
        setBookInfo: function(bookHash, chapterIndex) {
            return HighlightInteraction.setContext(bookHash, chapterIndex);
        },

        closeTransient: function() {
            if (HighlightInteraction.pendingDraft) HighlightInteraction.cancelPendingDraft();
            else HighlightInteraction.closeDialog();
        },
        
        // Get annotation count
        getAnnotationCount: function() {
            return HighlightInteraction.annotations.length;
        },
        focusAnnotation: function(id, options) {
            options = options || {};
            return new Promise(function(resolve) {
                var attempts = 0;
                var settled = false;
                var contentReadyListener = null;
                var lastAttemptedGeneration = 0;
                var waitForContentReady = options.waitForContentReady === true;
                var requestedChapterIndex = Number(options.chapterIndex);

                var cleanup = function() {
                    if (contentReadyListener && typeof global.removeEventListener === 'function') {
                        global.removeEventListener('epub-browser:annotation-content-ready', contentReadyListener);
                    }
                    contentReadyListener = null;
                };
                var finish = function(found) {
                    if (settled) return;
                    settled = true;
                    cleanup();
                    resolve(found);
                };
                var matchesRequestedChapter = function(detail) {
                    if (!Number.isInteger(requestedChapterIndex)) return true;
                    var readyChapterIndex = Number(detail && detail.chapterIndex);
                    return !Number.isInteger(readyChapterIndex) || readyChapterIndex === requestedChapterIndex;
                };
                var contentIsPending = function(detail) {
                    var root = detail && detail.root;
                    if (!root || typeof root.querySelectorAll !== 'function' || !Number.isInteger(requestedChapterIndex)) {
                        return false;
                    }
                    var pages = root.querySelectorAll('[data-pdf-page-number]');
                    for (var i = 0; i < pages.length; i++) {
                        var pageNumber = Number(pages[i].getAttribute('data-pdf-page-number'));
                        if (pageNumber - 1 !== requestedChapterIndex) continue;
                        var state = pages[i].getAttribute('data-pdf-rendered');
                        return state !== 'complete' && state !== 'error';
                    }
                    return false;
                };
                var focusNow = function() {
                    var nodes = HighlightInteraction.getHighlightNodesByAnnotationId(id);
                    if (nodes.length) {
                        nodes.forEach(function(node) { node.classList.add('annotation-focus-active'); });
                        nodes[0].scrollIntoView({ behavior: 'auto', block: 'center' });
                        setTimeout(function() { nodes.forEach(function(node) { node.classList.remove('annotation-focus-active'); }); }, 1800);
                        return true;
                    }
                    var image = HighlightInteraction.imageForAnnotationId(id);
                    if (image) {
                        image.classList.add('annotation-focus-active');
                        image.scrollIntoView({ behavior: 'auto', block: 'center' });
                        setTimeout(function() {
                            image.classList.remove('annotation-focus-active');
                        }, 1800);
                        return true;
                    }
                    return false;
                };
                var focusWithRetries = function(onMissing) {
                    if (settled) return;
                    if (focusNow()) {
                        finish(true);
                        return;
                    }
                    attempts++;
                    if (attempts < 6) {
                        requestAnimationFrame(function() { focusWithRetries(onMissing); });
                        return;
                    }
                    onMissing();
                };
                var focusAfterContentRefresh = function(record) {
                    if (
                        settled || !record || record.generation <= lastAttemptedGeneration ||
                        !matchesRequestedChapter(record.detail) || contentIsPending(record.detail)
                    ) return;
                    lastAttemptedGeneration = record.generation;
                    Promise.resolve(record.promise).then(function() {
                        if (settled) return;
                        var latest = contentReadyRefreshFor(requestedChapterIndex);
                        if (latest && latest.generation > record.generation) {
                            focusAfterContentRefresh(latest);
                            return;
                        }
                        if (contentIsPending(record.detail)) return;
                        attempts = 0;
                        focusWithRetries(function() {
                            var current = contentReadyRefreshFor(requestedChapterIndex);
                            if (current && current.generation > record.generation) {
                                focusAfterContentRefresh(current);
                                return;
                            }
                            if (!contentIsPending(record.detail)) finish(false);
                        });
                    }).catch(function() {
                        finish(false);
                    });
                };

                if (!waitForContentReady) {
                    focusWithRetries(function() { finish(false); });
                    return;
                }

                contentReadyListener = function(event) {
                    var detail = event && event.detail;
                    if (!matchesRequestedChapter(detail)) return;
                    // The module's content-ready listener is registered first and
                    // records the refresh promise synchronously. Read it in the
                    // following microtask, then focus only after restoration ends.
                    Promise.resolve().then(function() {
                        focusAfterContentRefresh(contentReadyRefreshFor(requestedChapterIndex));
                    });
                };
                if (typeof global.addEventListener === 'function') {
                    global.addEventListener('epub-browser:annotation-content-ready', contentReadyListener);
                }

                if (focusNow()) {
                    finish(true);
                    return;
                }
                focusAfterContentRefresh(contentReadyRefreshFor(requestedChapterIndex));
            });
        }
    };

    // Storage facade for pages that must share annotation data without starting
    // the reader's highlighter, selection handlers, or settings panel.
    var AnnotationStorage = {
        init: function() {
            return StorageManager.init();
        },
        getAll: function() {
            return StorageManager.getAll();
        },
        getSummary: function() {
            return StorageManager.getSummary();
        },
        getByBook: function(bookHash) {
            return StorageManager.getByBook(bookHash);
        },
        delete: function(id) {
            return StorageManager.delete(id);
        },
        getStorageType: function() {
            return StorageManager.currentType;
        },
        isBackendAvailable: function() {
            return StorageManager.isBackendAvailable();
        }
    };
    
    // 导出模块
    AnnotationModule.bindContentReadyRefresh();
    global.AnnotationModule = AnnotationModule;
    global.AnnotationStorage = AnnotationStorage;
    if (global.__EPUB_BROWSER_TESTING__) {
        global.AnnotationBackendStorage = BackendStorage;
        global.AnnotationDetailLifecycle = {
            create: createAnnotationDetailLifecycle
        };
        global.AnnotationLegacyPosition = {
            resolve: function(meta, chapterRoot) {
                return HighlightInteraction.resolveLegacyPointMeta(meta, chapterRoot);
            }
        };
        global.__testAnnotationSettingsMarkup = AnnotationSettingsMarkup;
    }
    
})(window);
