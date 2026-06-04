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
        
        // 与首页 Login 保持一致的用户名管理
        USERNAME_KEY: 'epub_browser_username',
        
        getAnnotationUsername: function() {
            if (this.isKindleMode()) {
                return this.getCookie(this.USERNAME_KEY) || '';
            }
            try {
                return localStorage.getItem(this.USERNAME_KEY) || '';
            } catch (e) {
                return '';
            }
        },
        
        setAnnotationUsername: function(username) {
            if (this.isKindleMode()) {
                this.setCookie(this.USERNAME_KEY, username);
            } else {
                try {
                    localStorage.setItem(this.USERNAME_KEY, username);
                } catch (e) {}
            }
            // 同步更新首页 Login 显示
            if (typeof window.updateLoginDisplay === 'function') {
                window.updateLoginDisplay();
            }
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
            return new Promise(function(resolve) {
                var xhr = new XMLHttpRequest();
                xhr.open('GET', self.baseUrl + '/health', true);
                xhr.timeout = CONFIG.HEALTH_TIMEOUT;
                
                xhr.onload = function() {
                    if (xhr.status >= 200 && xhr.status < 300) {
                        try {
                            var resp = JSON.parse(xhr.responseText);
                            self.available = resp.status === 'ok';
                        } catch (e) {
                            self.available = false;
                        }
                    } else {
                        self.available = false;
                    }
                    resolve({ available: self.available });
                };
                
                xhr.onerror = function() {
                    self.available = false;
                    resolve({ available: false });
                };
                
                xhr.ontimeout = function() {
                    self.available = false;
                    resolve({ available: false });
                };
                
                try {
                    xhr.send();
                } catch (e) {
                    self.available = false;
                    resolve({ available: false });
                }
            });
        },
        
        // 发送请求
        _request: function(method, path, data) {
            var self = this;
            var username = Utils.getAnnotationUsername();
            return new Promise(function(resolve, reject) {
                var xhr = new XMLHttpRequest();
                xhr.open(method, self.baseUrl + path, true);
                xhr.setRequestHeader('Content-Type', 'application/json');
                xhr.setRequestHeader('X-Username', username);
                xhr.timeout = 10000;
                
                xhr.onload = function() {
                    if (xhr.status >= 200 && xhr.status < 300) {
                        try {
                            resolve(JSON.parse(xhr.responseText));
                        } catch (e) {
                            resolve(xhr.responseText);
                        }
                    } else {
                        reject(new Error('HTTP ' + xhr.status));
                    }
                };
                
                xhr.onerror = function() {
                    reject(new Error('Network error'));
                };
                
                xhr.ontimeout = function() {
                    reject(new Error('Request timeout'));
                };
                
                try {
                    xhr.send(data ? JSON.stringify(data) : null);
                } catch (e) {
                    reject(e);
                }
            });
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
            return IDBStorage.init().then(function() {
                // 从 localStorage 加载 storageType
                var storageType = Utils.getStorage('annotation_storage_type');
                if (storageType) {
                    self.currentType = storageType;
                }
            });
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
            var storageType = Utils.getStorage('annotation_storage_type');
            var colorOrder = Utils.getStorage('annotation_color_order');
            var customColors = Utils.getStorage('annotation_custom_colors');
            var deletedColors = Utils.getStorage('annotation_deleted_colors');
            
            if (enabled !== null) this.enabled = enabled === 'true';
            if (color) this.defaultColor = color;
            if (storageType) this.storageType = storageType;
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
            Utils.setStorage('annotation_storage_type', this.storageType);
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
        pendingDraft: null,

        init: function() {
            var hl = initHighlighter();
            if (!hl) return;
            if (!this.isBound) {
                this.bindHighlighterEvents(hl);
                this.isBound = true;
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
                if (annotationId) {
                    self.showDetailDialog(annotationId);
                }
            });
        },

        syncEnabledState: function() {
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
            this.renderAll();
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
            return {
                id: source.id || Utils.generateUUID(),
                book_hash: currentBookHash,
                chapter_index: currentChapterIndex,
                text: source.text || '',
                note: note || '',
                startMeta: Utils.deepClone(source.startMeta),
                endMeta: Utils.deepClone(source.endMeta),
                color: color,
                created_at: Utils.getISOTime(),
                updated_at: Utils.getISOTime()
            };
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
            var hasNote = !!(annotation.note && annotation.note.trim());
            var bgColor = Utils.addColorAlpha(annotation.color, 0.4);
            var hoverColor = Utils.addColorAlpha(annotation.color, 0.6);
            var borderColor = Utils.addColorAlpha(annotation.color, 0.8);
            var self = this;
            (nodes || []).forEach(function(node, index) {
                node.style.backgroundColor = bgColor;
                node.style.setProperty('--annotation-color', bgColor);
                node.style.setProperty('--annotation-hover-color', hoverColor);
                node.style.setProperty('--annotation-border-color', borderColor);
                if (hasNote && index === nodes.length - 1) {
                    node.classList.add('has-note');
                } else {
                    node.classList.remove('has-note');
                }
                self.bindHighlightHoverState(node, annotation.id);
            });
        },

        closeDialog: function() {
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
            this.closeDialog();

            var dialog = document.createElement('div');
            dialog.className = 'annotation-dialog annotation-dialog-compact';
            dialog.innerHTML = '\
                <div class="annotation-compact-header">\
                    <div class="color-options-compact"></div>\
                    <button class="annotation-dialog-close"><i class="fas fa-times"></i></button>\
                </div>\
                <div class="annotation-compact-body">\
                    <textarea class="annotation-compact-note" placeholder="Note (optional)..."></textarea>\
                </div>\
                <div class="annotation-compact-footer">\
                    <button class="annotation-btn annotation-btn-cancel">Cancel</button>\
                    <button class="annotation-btn annotation-btn-confirm">Add</button>\
                </div>';

            var colorOptions = dialog.querySelector('.color-options-compact');
            var noteInput = dialog.querySelector('textarea');
            var colors = CONFIG.getColors();

            colors.slice(0, 4).forEach(function(color) {
                var btn = document.createElement('button');
                btn.className = 'color-option-compact' + (color === Settings.defaultColor ? ' selected' : '');
                btn.style.backgroundColor = color;
                btn.setAttribute('data-color', color);
                btn.addEventListener('click', function() {
                    var newColor = this.getAttribute('data-color');
                    colorOptions.querySelectorAll('.color-option-compact').forEach(function(option) {
                        option.classList.remove('selected');
                    });
                    this.classList.add('selected');
                    self.applyHighlightStyles({
                        id: source.id,
                        color: newColor,
                        note: ''
                    }, self.getHighlightNodesByAnnotationId(source.id));
                });
                colorOptions.appendChild(btn);
            });

            // Position near the highlighted text
            var nodes = self.getHighlightNodesByAnnotationId(source.id);
            if (nodes.length > 0) {
                var rect = nodes[0].getBoundingClientRect();
                var dialogW = 240;
                var dialogH = 140;
                var left = rect.left + (rect.width - dialogW) / 2;
                var top = rect.bottom + 8;
                // Keep within viewport
                left = Math.max(10, Math.min(left, window.innerWidth - dialogW - 10));
                if (top + dialogH > window.innerHeight - 10) {
                    top = rect.top - dialogH - 8;
                }
                if (top < 10) top = 10;
                dialog.style.left = left + 'px';
                dialog.style.top = top + 'px';
            } else {
                dialog.style.left = Math.max(10, (window.innerWidth - 240) / 2) + 'px';
                dialog.style.top = Math.max(10, (window.innerHeight - 140) / 2) + 'px';
            }

            document.body.appendChild(dialog);
            this.activeDialog = dialog;

            dialog.querySelector('.annotation-dialog-close').addEventListener('click', function() {
                self.cancelPendingDraft();
            });
            dialog.querySelector('.annotation-btn-cancel').addEventListener('click', function() {
                self.cancelPendingDraft();
            });
            dialog.querySelector('.annotation-btn-confirm').addEventListener('click', function() {
                var selectedColor = colorOptions.querySelector('.color-option-compact.selected');
                var color = selectedColor ? selectedColor.getAttribute('data-color') : Settings.defaultColor;
                self.createAnnotationFromSource(source, color, noteInput.value.trim());
            });

            setTimeout(function() {
                self.outsideClickHandler = function(e) {
                    if (dialog && !dialog.contains(e.target)) {
                        self.cancelPendingDraft();
                    }
                };
                document.addEventListener('click', self.outsideClickHandler);
            }, 10);
        },

        showDetailDialog: function(id) {
            var self = this;
            this.closeDialog();
            StorageManager.getById(id).then(function(annotation) {
                annotation = self.normalizeAnnotation(annotation);
                if (!annotation) {
                    Utils.showNotification('Annotation not found', 'warning');
                    return;
                }

                var textPreview = annotation.text.substring(0, 100) + (annotation.text.length > 100 ? '...' : '');
                var dialog = document.createElement('div');
                dialog.className = 'annotation-dialog';
                dialog.innerHTML = '\
                    <div class="annotation-dialog-header">\
                        <span><i class="fas fa-highlighter"></i> Annotation Details</span>\
                        <button class="annotation-dialog-close"><i class="fas fa-times"></i></button>\
                    </div>\
                    <div class="annotation-dialog-body">\
                        <div class="annotation-dialog-text">' + Utils.escapeHtml(textPreview) + '</div>\
                        <div class="annotation-color-picker">\
                            <label>Color:</label>\
                            <div class="color-options"></div>\
                        </div>\
                        <div class="annotation-note-input">\
                            <label>Note:</label>\
                            <textarea placeholder="Add description...">' + Utils.escapeHtml(annotation.note) + '</textarea>\
                        </div>\
                        <div class="annotation-meta">\
                            <span>Created: ' + Utils.formatDateTime(annotation.created_at) + '</span>\
                            <span class="annotation-updated"></span>\
                        </div>\
                    </div>\
                    <div class="annotation-dialog-footer">\
                        <button class="annotation-btn annotation-btn-delete"><i class="fas fa-trash"></i> Delete</button>\
                        <button class="annotation-btn annotation-btn-confirm">Save</button>\
                    </div>';

                if (annotation.updated_at && annotation.updated_at !== annotation.created_at) {
                    dialog.querySelector('.annotation-updated').textContent = 'Updated: ' + Utils.formatDateTime(annotation.updated_at);
                }

                var colorOptions = dialog.querySelector('.color-options');
                CONFIG.getColors().slice(0, 7).forEach(function(color) {
                    var btn = document.createElement('button');
                    btn.className = 'color-option' + (color === annotation.color ? ' selected' : '');
                    btn.style.backgroundColor = color;
                    btn.setAttribute('data-color', color);
                    btn.addEventListener('click', function() {
                        colorOptions.querySelectorAll('.color-option').forEach(function(option) {
                            option.classList.remove('selected');
                        });
                        this.classList.add('selected');
                    });
                    colorOptions.appendChild(btn);
                });

                dialog.style.left = Math.max(10, Math.min((window.innerWidth - 300) / 2, window.innerWidth - 310)) + 'px';
                dialog.style.top = Math.max(10, Math.min((window.innerHeight - 320) / 2, window.innerHeight - 330)) + 'px';

                document.body.appendChild(dialog);
                self.activeDialog = dialog;

                var noteInput = dialog.querySelector('textarea');
                var textEl = dialog.querySelector('.annotation-dialog-text');

                textEl.style.cursor = 'pointer';
                textEl.title = 'Click to copy';
                textEl.addEventListener('click', function() {
                    var textarea = document.createElement('textarea');
                    textarea.value = annotation.text;
                    textarea.style.position = 'fixed';
                    textarea.style.opacity = '0';
                    document.body.appendChild(textarea);
                    textarea.select();
                    document.execCommand('copy');
                    document.body.removeChild(textarea);
                    Utils.showNotification('Text copied', 'success');
                });

                dialog.querySelector('.annotation-dialog-close').addEventListener('click', function() {
                    self.closeDialog();
                });
                dialog.querySelector('.annotation-btn-delete').addEventListener('click', function() {
                    if (confirm('Delete this annotation?')) {
                        self.deleteAnnotation(annotation.id);
                        self.closeDialog();
                    }
                });
                dialog.querySelector('.annotation-btn-confirm').addEventListener('click', function() {
                    var selectedColor = colorOptions.querySelector('.color-option.selected');
                    var color = selectedColor ? selectedColor.getAttribute('data-color') : annotation.color;
                    self.updateAnnotation(annotation.id, {
                        color: color,
                        note: noteInput.value.trim()
                    });
                    self.closeDialog();
                });
            }).catch(function(err) {
                Utils.showNotification('Failed to load annotation: ' + err.message, 'error');
            });
        },

        createAnnotationFromSource: function(source, color, note) {
            var self = this;
            var annotation = this.buildAnnotationFromSource(source, color, note);
            StorageManager.create(annotation).then(function() {
                self.annotations.push(annotation);
                self.applyHighlightStyles(annotation, self.getHighlightNodesByAnnotationId(annotation.id));
                self.clearPendingDraftState();
                self.closeDialog();
                Utils.showNotification('Annotation added', 'success');
            }).catch(function(err) {
                self.cancelPendingDraft();
                Utils.showNotification('Failed to add: ' + err.message, 'error');
            });
        },

        updateAnnotation: function(id, data) {
            var self = this;
            var updateData = {
                color: data.color,
                note: data.note,
                updated_at: Utils.getISOTime()
            };
            StorageManager.update(id, updateData).then(function() {
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
                Utils.showNotification('Annotation updated', 'success');
            }).catch(function(err) {
                Utils.showNotification('Failed to update: ' + err.message, 'error');
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
                Utils.showNotification('Annotation deleted', 'info');
            }).catch(function(err) {
                Utils.showNotification('Failed to delete: ' + err.message, 'error');
            });
        },

        renderHighlight: function(annotation) {
            if (!highlighter || !annotation) return;
            try {
                var source = highlighter.fromStore(
                    annotation.startMeta,
                    annotation.endMeta,
                    annotation.text,
                    annotation.id
                );
                if (!source) return;
                this.applyHighlightStyles(annotation, this.getHighlightNodesByAnnotationId(annotation.id));
            } catch (e) {
                console.error('Failed to render highlight:', e);
            }
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

        renderAll: function() {
            var self = this;
            if (!highlighter) return Promise.resolve();
            this.isRendering = true;
            this.cancelPendingDraft();
            this.clearHighlights();
            return StorageManager.getByChapter(currentBookHash, currentChapterIndex).then(function(annotations) {
                self.annotations = (annotations || []).map(function(annotation) {
                    return self.normalizeAnnotation(annotation);
                }).filter(Boolean).sort(function(a, b) {
                    return (b.text || '').length - (a.text || '').length;
                });
                self.annotations.forEach(function(annotation) {
                    self.renderHighlight(annotation);
                });
            }).catch(function(err) {
                console.error('Failed to load annotations:', err);
            }).finally(function() {
                self.isRendering = false;
            });
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
            tabBtn.innerHTML = '<i class="fas fa-highlighter"></i><span>Annotation</span>';
            
            // Create tab panel
            var tabPanel = document.createElement('div');
            tabPanel.className = 'settings-tab-panel';
            tabPanel.id = 'annotation-tab';
            tabPanel.innerHTML = '\
                <div class="settings-group">\
                    <label class="settings-switch">\
                        <input type="checkbox" id="annotationEnabled" ' + (Settings.enabled ? 'checked' : '') + '>\
                        <span class="switch-slider"></span>\
                        <span class="switch-text">Enable Annotation</span>\
                    </label>\
                </div>\
                <div class="settings-group">\
                    <label class="settings-label">Storage Location</label>\
                    <div class="storage-options">\
                        <label class="storage-option" id="storageOptionIdb">\
                            <input type="radio" name="annotationStorage" value="idb" ' + (Settings.storageType === 'idb' ? 'checked' : '') + '>\
                            <span class="storage-option-text">Local Storage</span>\
                        </label>\
                        <label class="storage-option" id="storageOptionBackend">\
                            <input type="radio" name="annotationStorage" value="backend" ' + (Settings.storageType === 'backend' ? 'checked' : '') + '>\
                            <span class="storage-option-text">Cloud Storage</span>\
                            <span class="storage-option-status" id="backendStatus">Checking...</span>\
                        </label>\
                    </div>\
                </div>\
                <div class="settings-group">\
                    <label class="settings-label">\
                        Default Color\
                        <span class="color-tip-default"><i class="fas fa-info-circle"></i></span>\
                    </label>\
                    <div class="color-picker-default"></div>\
                </div>\
                <div class="settings-group">\
                    <label class="settings-label">Export Data</label>\
                    <div class="export-buttons">\
                        <button class="annotation-btn annotation-btn-secondary" id="exportBookBtn">\
                            <i class="fas fa-download"></i> Export Book\
                        </button>\
                        <button class="annotation-btn annotation-btn-secondary" id="exportAllBtn">\
                            <i class="fas fa-download"></i> Export All\
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
                this.checkBackendStatus();
                
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
                Utils.showNotification(Settings.enabled ? 'Annotation enabled' : 'Annotation disabled', 'info');
            });
            
            // Storage toggle
            var storageRadios = tabPanel.querySelectorAll('input[name="annotationStorage"]');
            storageRadios.forEach(function(radio) {
                radio.addEventListener('change', function() {
                    var targetType = this.value;
                    
                    // 如果选择的是当前存储类型，不处理
                    if (targetType === Settings.storageType) return;
                    
                    // 切换到云端存储
                    if (targetType === 'backend') {
                        if (!Settings.backendAvailable) {
                            Utils.showNotification('Cloud storage unavailable', 'warning');
                            self.revertStorageRadio(Settings.storageType);
                            return;
                        }
                        
                        // 检查是否已登录，提示用户
                        var currentUsername = Utils.getAnnotationUsername();
                        if (!currentUsername) {
                            var msg = 'You are not logged in.\n\n' +
                                '- Click OK to enter a username (annotations will be isolated by user)\n' +
                                '- Click Cancel to use shared mode (all users share the same annotations)';
                            var username = prompt(msg, '');
                            if (username === null) {
                                // 用户取消 → 使用共享模式
                                Utils.showNotification('Using shared cloud storage (no user isolation)', 'info');
                            } else {
                                username = username.trim();
                                if (username) {
                                    Utils.setAnnotationUsername(username);
                                    Utils.showNotification('Logged in as: ' + username + ' (annotations isolated)', 'success');
                                    self.checkBackendStatus();
                                } else {
                                    Utils.showNotification('Using shared cloud storage (no user isolation)', 'info');
                                }
                            }
                        }
                        
                        // 继续迁移流程
                        self.showMigrationDialog(Settings.storageType, targetType);
                        return;
                    }
                    
                    // 切换到本地存储
                    self.showMigrationDialog(Settings.storageType, targetType);
                });
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
            header.innerHTML = '\
                <span class="color-header-label">\
                    Colors\
                    <span class="color-tip-reorder"><i class="fas fa-info-circle"></i></span>\
                </span>\
                <button class="color-add-btn" title="Add color"><i class="fas fa-plus"></i></button>';
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
                    btn.innerHTML = '\
                        <button class="color-option' + (color === Settings.defaultColor ? ' selected' : '') + '" style="background-color: ' + color + '"></button>\
                        <button class="color-delete-btn" title="Delete"><i class="fas fa-times"></i></button>';
                    
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
                    <span><i class="fas fa-palette"></i> Add Color</span>\
                    <button class="annotation-dialog-close"><i class="fas fa-times"></i></button>\
                </div>\
                <div class="annotation-dialog-body">\
                    <div class="color-input-row">\
                        <input type="color" id="colorPickerInput" value="#FF5722">\
                        <input type="text" id="colorHexInput" value="#FF5722" maxlength="7" placeholder="#RRGGBB">\
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
                    <button class="annotation-btn annotation-btn-cancel">Cancel</button>\
                    <button class="annotation-btn annotation-btn-confirm">Add</button>\
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
                var color = colorInput.value.toUpperCase();
                
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
            statusEl.textContent = 'Checking...';
            
            StorageManager.isBackendAvailable().then(function(result) {
                var available = result.available;
                Settings.backendAvailable = available;
                self.backendChecking = false;
                
                if (available) {
                    var username = Utils.getAnnotationUsername();
                    if (username) {
                        statusEl.textContent = 'Connected (' + username + ')';
                    } else {
                        statusEl.textContent = 'Connected (shared)';
                    }
                    statusEl.className = 'storage-option-status connected';
                    backendOption.classList.remove('disabled');
                } else {
                    statusEl.textContent = 'Disconnected';
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
                    <span><i class="fas fa-exchange-alt"></i> Data Migration</span>\
                </div>\
                <div class="annotation-dialog-body">\
                    <p>Switching storage location requires data migration</p>\
                    <p id="migrationStatus">Counting data...</p>\
                </div>\
                <div class="annotation-dialog-footer">\
                    <button class="annotation-btn annotation-btn-secondary" id="migrationCancel">Cancel</button>\
                    <button class="annotation-btn annotation-btn-secondary" id="migrationSkip">Skip</button>\
                    <button class="annotation-btn annotation-btn-confirm" id="migrationConfirm">Migrate</button>\
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
                statusEl.textContent = 'Current data: ' + count + ' annotations';
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
                statusEl.innerHTML = '<div class="migration-progress"><div class="migration-progress-bar"><div class="migration-progress-fill" style="width:0%"></div></div><span>Migrating...</span></div>';
                
                self.finishStorageChange(toType, true, function(current, total) {
                    var fill = dialog.querySelector('.migration-progress-fill');
                    var text = dialog.querySelector('.migration-progress span');
                    if (fill) fill.style.width = Math.round(current / total * 100) + '%';
                    if (text) text.textContent = 'Migrating... ' + current + '/' + total;
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
                
                Utils.showNotification('Storage location changed', 'success');
                
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
                Utils.showNotification('Exported ' + (annotations ? annotations.length : 0) + ' annotations', 'success');
            }).catch(function(err) {
                Utils.showNotification('Export failed: ' + err.message, 'error');
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
                Utils.showNotification('Exported ' + (annotations ? annotations.length : 0) + ' annotations', 'success');
            }).catch(function(err) {
                Utils.showNotification('Export failed: ' + err.message, 'error');
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
        
        // Initialize
        init: function(options) {
            options = options || {};
            currentBookHash = options.bookHash || '';
            currentChapterIndex = options.chapterIndex || 0;

            if (this.initialized) {
                HighlightInteraction.setContext(currentBookHash, currentChapterIndex);
                HighlightInteraction.syncEnabledState();
                return;
            }
            
            // Load settings
            Settings.load();
            
            // Initialize storage
            var self = this;
            StorageManager.init().then(function() {
                // Initialize interaction
                HighlightInteraction.init();
                
                // Create settings tab
                SettingsTab.createContent();
                
                HighlightInteraction.setContext(currentBookHash, currentChapterIndex);
                
                self.initialized = true;
            }).catch(function(err) {
                console.error('Annotation module init failed:', err);
            });
        },
        
        // Destroy
        destroy: function() {
            HighlightInteraction.cancelPendingDraft();
            HighlightInteraction.closeDialog();
            HighlightInteraction.clearHighlights();
            if (highlighter && HighlightInteraction.isListening) {
                highlighter.stop();
                HighlightInteraction.isListening = false;
            }
            this.initialized = false;
        },
        
        // Refresh
        refresh: function() {
            HighlightInteraction.renderAll();
        },
        
        // Set book info
        setBookInfo: function(bookHash, chapterIndex) {
            HighlightInteraction.setContext(bookHash, chapterIndex);
        },
        
        // Get annotation count
        getAnnotationCount: function() {
            return HighlightInteraction.annotations.length;
        }
    };
    
    // 导出模块
    global.AnnotationModule = AnnotationModule;
    
})(window);
