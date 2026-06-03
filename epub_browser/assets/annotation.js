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
        SETTINGS_STORE: 'settings',
        BASE_COLORS: ['#FFEB3B', '#4CAF50', '#2196F3', '#9C27B0', '#F44336', '#FF9800', '#00BCD4', '#795548'],
        DEFAULT_COLOR: '#FFEB3B',
        HEALTH_TIMEOUT: 3000,
        BATCH_SIZE: 100,
        ANNOTATION_CLASS: 'annotation-highlight',
        
        // Get colors based on settings
        getColors: function() {
            var order = Settings.colorOrder || [];
            var custom = Settings.customColors || [];
            
            // If no color order (never dragged/sorted), use base colors + custom colors
            if (order.length === 0) {
                var result = this.BASE_COLORS.slice();
                // Add custom colors that are not in base colors
                for (var j = 0; j < custom.length; j++) {
                    if (result.indexOf(custom[j]) === -1) {
                        result.push(custom[j]);
                    }
                }
                return result;
            }
            
            // Merge: first use color order, then add custom colors not in order
            var allColors = [];
            var seen = {};
            
            // First add colors in order
            for (var i = 0; i < order.length; i++) {
                if (order[i] && !seen[order[i]]) {
                    allColors.push(order[i]);
                    seen[order[i]] = true;
                }
            }
            
            // Then add custom colors not in order
            for (var j = 0; j < custom.length; j++) {
                if (!seen[custom[j]]) {
                    allColors.push(custom[j]);
                    seen[custom[j]] = true;
                }
            }
            
            return allColors;
        }
    };
    
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
                    
                    // 创建设置存储
                    if (!db.objectStoreNames.contains(CONFIG.SETTINGS_STORE)) {
                        db.createObjectStore(CONFIG.SETTINGS_STORE, { keyPath: 'key' });
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
                return store.add(annotation);
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
                        store.add(annotations[i]);
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
        },
        
        // 获取设置
        getSettings: function() {
            var self = this;
            return new Promise(function(resolve, reject) {
                self._transaction(CONFIG.SETTINGS_STORE, 'readonly', function(store) {
                    return store.get('annotation_settings');
                }).then(function(result) {
                    resolve(result ? result.value : null);
                }).catch(reject);
            });
        },
        
        // 保存设置
        saveSettings: function(settings) {
            return this._transaction(CONFIG.SETTINGS_STORE, 'readwrite', function(store) {
                return store.put({ key: 'annotation_settings', value: settings });
            });
        }
    };
    
    // ========== 后端存储适配器 ==========
    var BackendStorage = {
        baseUrl: '/api',
        available: null,
        
        // 检测后端是否可用
        checkHealth: function() {
            var self = this;
            return new Promise(function(resolve) {
                var xhr = new XMLHttpRequest();
                xhr.open('GET', self.baseUrl + '/health', true);
                xhr.timeout = CONFIG.HEALTH_TIMEOUT;
                
                xhr.onload = function() {
                    self.available = xhr.status >= 200 && xhr.status < 300;
                    resolve(self.available);
                };
                
                xhr.onerror = function() {
                    self.available = false;
                    resolve(false);
                };
                
                xhr.ontimeout = function() {
                    self.available = false;
                    resolve(false);
                };
                
                try {
                    xhr.send();
                } catch (e) {
                    self.available = false;
                    resolve(false);
                }
            });
        },
        
        // 发送请求
        _request: function(method, path, data) {
            var self = this;
            return new Promise(function(resolve, reject) {
                var xhr = new XMLHttpRequest();
                xhr.open(method, self.baseUrl + path, true);
                xhr.setRequestHeader('Content-Type', 'application/json');
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
            return this._request('PUT', '/annotations/' + id, data).then(function(res) {
                return res.data || res;
            });
        },
        
        // 删除标注
        delete: function(id) {
            return this._request('DELETE', '/annotations/' + id);
        },
        
        // 获取单个标注
        getById: function(id) {
            return this._request('GET', '/annotations/' + id).then(function(res) {
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
                return IDBStorage.getSettings();
            }).then(function(settings) {
                if (settings) {
                    self.currentType = settings.storage_type || 'idb';
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
                    self.saveSettings().then(resolve).catch(reject);
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
        
        // 保存设置
        saveSettings: function() {
            return IDBStorage.saveSettings({
                enabled: Settings.enabled,
                storage_type: this.currentType,
                default_color: Settings.defaultColor
            });
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
        
        // Load settings
        load: function() {
            var enabled = Utils.getStorage('annotation_enabled');
            var color = Utils.getStorage('annotation_default_color');
            var storageType = Utils.getStorage('annotation_storage_type');
            var colorOrder = Utils.getStorage('annotation_color_order');
            var customColors = Utils.getStorage('annotation_custom_colors');
            
            if (enabled !== null) this.enabled = enabled === 'true';
            if (color) this.defaultColor = color;
            if (storageType) this.storageType = storageType;
            if (colorOrder) {
                try { this.colorOrder = JSON.parse(colorOrder); } catch (e) { this.colorOrder = []; }
            }
            if (customColors) {
                try { this.customColors = JSON.parse(customColors); } catch (e) { this.customColors = []; }
            }
        },
        
        // Save settings
        save: function() {
            Utils.setStorage('annotation_enabled', this.enabled.toString());
            Utils.setStorage('annotation_default_color', this.defaultColor);
            Utils.setStorage('annotation_storage_type', this.storageType);
            Utils.setStorage('annotation_color_order', JSON.stringify(this.colorOrder));
            Utils.setStorage('annotation_custom_colors', JSON.stringify(this.customColors));
        }
    };
    
    // ========== XPath 工具 ==========
    var XPathUtils = {
        // 生成XPath
        generate: function(node) {
            var paths = [];
            var content = document.getElementById('eb-content');
            
            while (node && node !== content && node !== document.body) {
                var index = 0;
                var sibling = node;
                var hasSameSiblings = false;
                
                // 计算同级索引
                while (sibling) {
                    if (sibling.nodeType === node.nodeType && 
                        sibling.nodeName === node.nodeName) {
                        index++;
                        hasSameSiblings = true;
                    }
                    sibling = sibling.previousSibling;
                }
                
                var nodeName = node.nodeType === Node.TEXT_NODE ? 'text()' : node.nodeName.toLowerCase();
                var path = hasSameSiblings ? (nodeName + '[' + index + ']') : nodeName;
                paths.unshift(path);
                node = node.parentNode;
            }
            
            return '/' + paths.join('/');
        },
        
        // 解析XPath
        resolve: function(xpath, root) {
            root = root || document.getElementById('eb-content');
            if (!root || !xpath) return null;
            
            try {
                var result = document.evaluate(
                    xpath,
                    root,
                    null,
                    XPathResult.FIRST_ORDERED_NODE_TYPE,
                    null
                );
                return result.singleNodeValue;
            } catch (e) {
                return null;
            }
        },
        
        // 获取选区信息
        getSelectionInfo: function(selection) {
            if (!selection || selection.rangeCount === 0) return null;
            
            var range = selection.getRangeAt(0);
            var text = selection.toString().trim();
            
            if (!text) return null;
            
            return {
                text: text,
                startContainer: range.startContainer,
                startOffset: range.startOffset,
                endContainer: range.endContainer,
                endOffset: range.endOffset,
                startXPath: this.generate(range.startContainer),
                endXPath: this.generate(range.endContainer)
            };
        }
    };
    
    // ========== 划线交互模块 ==========
    var HighlightInteraction = {
        activeDialog: null,
        annotations: [],
        
        // 初始化
        init: function() {
            var self = this;
            
            // 监听鼠标抬起事件
            document.addEventListener('mouseup', function(e) {
                self.handleMouseUp(e);
            });
            
            // 监听触摸结束事件
            document.addEventListener('touchend', function(e) {
                setTimeout(function() {
                    self.handleMouseUp(e);
                }, 100);
            });
            
            // 点击高亮标注
            document.addEventListener('click', function(e) {
                var target = e.target;
                if (target.classList && target.classList.contains(CONFIG.ANNOTATION_CLASS)) {
                    e.stopPropagation();
                    var id = target.getAttribute('data-annotation-id');
                    if (id) {
                        self.showDetailDialog(id);
                    }
                }
            });
        },
        
        // Handle mouse up
        handleMouseUp: function(e) {
            // Check if annotation feature is enabled
            if (!Settings.enabled) return;
            
            // Check if click is inside a dialog
            if (this.activeDialog && this.activeDialog.contains(e.target)) return;
            
            // Check if click is inside settings modal
            var settingsModal = document.getElementById('settingsModal');
            if (settingsModal && settingsModal.classList.contains('show') && settingsModal.contains(e.target)) return;
            
            // Check if selection is within eb-content-container
            var contentContainer = document.getElementById('eb-content-container');
            if (!contentContainer) return;
            
            var selection = window.getSelection();
            
            // Verify selection is within content container
            if (selection.rangeCount > 0) {
                var range = selection.getRangeAt(0);
                if (!contentContainer.contains(range.commonAncestorContainer)) {
                    return;
                }
            }
            
            var info = XPathUtils.getSelectionInfo(selection);
            
            if (info && info.text.length > 0) {
                this.showCreateDialog(info, e);
            }
        },
        
        // Show create dialog
        showCreateDialog: function(info, event) {
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
            
            // Color picker - only show first 4 colors from settings
            var colorOptions = dialog.querySelector('.color-options-compact');
            var allColors = CONFIG.getColors();
            for (var i = 0; i < Math.min(allColors.length, 4); i++) {
                var color = allColors[i];
                var btn = document.createElement('button');
                btn.className = 'color-option-compact' + (color === Settings.defaultColor ? ' selected' : '');
                btn.style.backgroundColor = color;
                btn.setAttribute('data-color', color);
                btn.addEventListener('click', function(e) {
                    colorOptions.querySelectorAll('.color-option-compact').forEach(function(b) {
                        b.classList.remove('selected');
                    });
                    this.classList.add('selected');
                });
                colorOptions.appendChild(btn);
            }
            
            // Position dialog - more compact positioning
            var x = event.clientX || (event.changedTouches && event.changedTouches[0].clientX) || 100;
            var y = event.clientY || (event.changedTouches && event.changedTouches[0].clientY) || 100;
            
            var dialogWidth = 240; // Smaller width
            var dialogHeight = 140; // Estimated height
            
            // Smart positioning: prefer below selection, but show above if no space below
            var showBelow = (y + 10 + dialogHeight) < window.innerHeight;
            var posX = Math.max(10, Math.min(x - dialogWidth / 2, window.innerWidth - dialogWidth - 10));
            var posY = showBelow ? (y + 10) : Math.max(10, y - dialogHeight - 10);
            
            dialog.style.left = posX + 'px';
            dialog.style.top = posY + 'px';
            
            document.body.appendChild(dialog);
            this.activeDialog = dialog;
            
            // Bind events
            var closeBtn = dialog.querySelector('.annotation-dialog-close');
            var cancelBtn = dialog.querySelector('.annotation-btn-cancel');
            var confirmBtn = dialog.querySelector('.annotation-btn-confirm');
            var noteInput = dialog.querySelector('textarea');
            
            var closeHandler = function() {
                self.closeDialog();
                window.getSelection().removeAllRanges();
            };
            
            closeBtn.addEventListener('click', closeHandler);
            cancelBtn.addEventListener('click', closeHandler);
            
            confirmBtn.addEventListener('click', function() {
                var selectedColor = colorOptions.querySelector('.color-option-compact.selected');
                var color = selectedColor ? selectedColor.getAttribute('data-color') : Settings.defaultColor;
                var note = noteInput.value.trim();
                
                self.createAnnotation(info, color, note);
                self.closeDialog();
                window.getSelection().removeAllRanges();
            });
            
            // Click outside to close
            setTimeout(function() {
                document.addEventListener('click', self.outsideClickHandler = function(e) {
                    if (dialog && !dialog.contains(e.target)) {
                        self.closeDialog();
                    }
                });
            }, 10);
        },
        
        // Show detail dialog
        showDetailDialog: function(id) {
            var self = this;
            this.closeDialog();
            
            StorageManager.getById(id).then(function(annotation) {
                if (!annotation) {
                    Utils.showNotification('Annotation not found', 'warning');
                    return;
                }
                
                var dialog = document.createElement('div');
                dialog.className = 'annotation-dialog';
                dialog.innerHTML = '\
                    <div class="annotation-dialog-header">\
                        <span><i class="fas fa-highlighter"></i> Annotation Details</span>\
                        <button class="annotation-dialog-close"><i class="fas fa-times"></i></button>\
                    </div>\
                    <div class="annotation-dialog-body">\
                        <div class="annotation-dialog-text">' + Utils.escapeHtml(annotation.text.substring(0, 100)) + (annotation.text.length > 100 ? '...' : '') + '</div>\
                        <div class="annotation-color-picker">\
                            <label>Color:</label>\
                            <div class="color-options"></div>\
                        </div>\
                        <div class="annotation-note-input">\
                            <label>Note:</label>\
                            <textarea placeholder="Add description...">' + (annotation.note || '') + '</textarea>\
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
                
                // Show Updated if different from Created
                if (annotation.updated_at && annotation.updated_at !== annotation.created_at) {
                    var updatedSpan = dialog.querySelector('.annotation-updated');
                    updatedSpan.textContent = 'Updated: ' + Utils.formatDateTime(annotation.updated_at);
                }
                
                // Color picker - show first 7 colors from settings
                var colorOptions = dialog.querySelector('.color-options');
                var colors = CONFIG.getColors();
                for (var i = 0; i < Math.min(colors.length, 7); i++) {
                    var color = colors[i];
                    var btn = document.createElement('button');
                    btn.className = 'color-option' + (color === annotation.color ? ' selected' : '');
                    btn.style.backgroundColor = color;
                    btn.setAttribute('data-color', color);
                    btn.addEventListener('click', function(e) {
                        colorOptions.querySelectorAll('.color-option').forEach(function(b) {
                            b.classList.remove('selected');
                        });
                        this.classList.add('selected');
                    });
                    colorOptions.appendChild(btn);
                }
                
                // Position dialog - centered on screen with smart bounds
                var dialogWidth = 300;
                var dialogHeight = 320;
                var posX = Math.max(10, Math.min((window.innerWidth - dialogWidth) / 2, window.innerWidth - dialogWidth - 10));
                var posY = Math.max(10, Math.min((window.innerHeight - dialogHeight) / 2, window.innerHeight - dialogHeight - 10));
                
                dialog.style.left = posX + 'px';
                dialog.style.top = posY + 'px';
                
                document.body.appendChild(dialog);
                self.activeDialog = dialog;
                
                // Bind events
                var closeBtn = dialog.querySelector('.annotation-dialog-close');
                var deleteBtn = dialog.querySelector('.annotation-btn-delete');
                var saveBtn = dialog.querySelector('.annotation-btn-confirm');
                var noteInput = dialog.querySelector('textarea');
                var textEl = dialog.querySelector('.annotation-dialog-text');
                
                // Click to copy text
                if (textEl) {
                    textEl.style.cursor = 'pointer';
                    textEl.title = 'Click to copy';
                    textEl.addEventListener('click', function() {
                        var text = annotation.text;
                        if (navigator.clipboard && navigator.clipboard.writeText) {
                            navigator.clipboard.writeText(text).then(function() {
                                Utils.showNotification('Text copied', 'success');
                            }).catch(function() {
                                // Fallback
                                var textarea = document.createElement('textarea');
                                textarea.value = text;
                                textarea.style.position = 'fixed';
                                textarea.style.opacity = '0';
                                document.body.appendChild(textarea);
                                textarea.select();
                                document.execCommand('copy');
                                document.body.removeChild(textarea);
                                Utils.showNotification('Text copied', 'success');
                            });
                        } else {
                            // Fallback for older browsers
                            var textarea = document.createElement('textarea');
                            textarea.value = text;
                            textarea.style.position = 'fixed';
                            textarea.style.opacity = '0';
                            document.body.appendChild(textarea);
                            textarea.select();
                            document.execCommand('copy');
                            document.body.removeChild(textarea);
                            Utils.showNotification('Text copied', 'success');
                        }
                    });
                }
                
                closeBtn.addEventListener('click', function() {
                    self.closeDialog();
                });
                
                deleteBtn.addEventListener('click', function() {
                    if (confirm('Delete this annotation?')) {
                        self.deleteAnnotation(id);
                        self.closeDialog();
                    }
                });
                
                saveBtn.addEventListener('click', function() {
                    var selectedColor = colorOptions.querySelector('.color-option.selected');
                    var color = selectedColor ? selectedColor.getAttribute('data-color') : annotation.color;
                    var note = noteInput.value.trim();
                    
                    self.updateAnnotation(id, { color: color, note: note });
                    self.closeDialog();
                });
            });
        },
        
        // 关闭弹窗
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
        
        // 创建标注
        createAnnotation: function(info, color, note) {
            var annotation = {
                id: Utils.generateUUID(),
                book_hash: currentBookHash,
                chapter_index: currentChapterIndex,
                text: info.text,
                note: note || '',
                start_xpath: info.startXPath,
                end_xpath: info.endXPath,
                start_offset: info.startOffset,
                end_offset: info.endOffset,
                color: color,
                created_at: Utils.getISOTime(),
                updated_at: Utils.getISOTime()
            };
            
            var self = this;
            StorageManager.create(annotation).then(function() {
                self.annotations.push(annotation);
                // Use simple highlight for immediate rendering
                self.renderSimpleHighlight(annotation);
                Utils.showNotification('Annotation added', 'success');
            }).catch(function(err) {
                Utils.showNotification('Failed to add: ' + err.message, 'error');
            });
        },
        
        // Update annotation
        updateAnnotation: function(id, data) {
            var self = this;
            var now = Utils.getISOTime();
            var updateData = {
                color: data.color,
                note: data.note,
                updated_at: now
            };
            StorageManager.update(id, updateData).then(function(updated) {
                // Update local cache
                for (var i = 0; i < self.annotations.length; i++) {
                    if (self.annotations[i].id === id) {
                        self.annotations[i].color = data.color;
                        self.annotations[i].note = data.note;
                        self.annotations[i].updated_at = now;
                        break;
                    }
                }
                // Update highlight color and note indicator
                var highlights = document.querySelectorAll('.' + CONFIG.ANNOTATION_CLASS + '[data-annotation-id="' + id + '"]');
                highlights.forEach(function(el) {
                    el.style.backgroundColor = Utils.addColorAlpha(data.color, 0.4);
                    if (data.note && data.note.trim()) {
                        el.classList.add('has-note');
                    } else {
                        el.classList.remove('has-note');
                    }
                });
                Utils.showNotification('Annotation updated', 'success');
            }).catch(function(err) {
                Utils.showNotification('Failed to update: ' + err.message, 'error');
            });
        },
        
        // Delete annotation
        deleteAnnotation: function(id) {
            var self = this;
            StorageManager.delete(id).then(function() {
                // Remove from local cache
                self.annotations = self.annotations.filter(function(a) {
                    return a.id !== id;
                });
                // Remove highlight
                var highlights = document.querySelectorAll('.' + CONFIG.ANNOTATION_CLASS + '[data-annotation-id="' + id + '"]');
                highlights.forEach(function(el) {
                    var parent = el.parentNode;
                    while (el.firstChild) {
                        parent.insertBefore(el.firstChild, el);
                    }
                    parent.removeChild(el);
                });
                Utils.showNotification('Annotation deleted', 'info');
            }).catch(function(err) {
                Utils.showNotification('Failed to delete: ' + err.message, 'error');
            });
        },
        
        // 渲染高亮
        renderHighlight: function(annotation) {
            var selection = window.getSelection();
            selection.removeAllRanges();
            
            try {
                var startNode = XPathUtils.resolve(annotation.start_xpath);
                var endNode = XPathUtils.resolve(annotation.end_xpath);
                
                if (startNode && endNode) {
                    var range = document.createRange();
                    range.setStart(startNode, annotation.start_offset);
                    range.setEnd(endNode, annotation.end_offset);
                    
                    var span = document.createElement('span');
                    span.className = CONFIG.ANNOTATION_CLASS;
                    if (annotation.note) span.classList.add('has-note');
                    span.setAttribute('data-annotation-id', annotation.id);
                    span.style.backgroundColor = Utils.addColorAlpha(annotation.color, 0.4);
                    
                    range.surroundContents(span);
                }
            } catch (e) {
                // Cross-element selection, use simplified method
                this.renderSimpleHighlight(annotation);
            }
        },
        
        // Simplified highlight rendering (for cross-element cases)
        renderSimpleHighlight: function(annotation) {
            var content = document.getElementById('eb-content');
            if (!content) return;
            
            // Find element containing annotation text
            var walker = document.createTreeWalker(content, NodeFilter.SHOW_TEXT, null, false);
            var node;
            var found = false;
            
            while (node = walker.nextNode()) {
                if (node.textContent.indexOf(annotation.text) !== -1) {
                    try {
                        var range = document.createRange();
                        var start = node.textContent.indexOf(annotation.text);
                        range.setStart(node, start);
                        range.setEnd(node, start + annotation.text.length);
                        
                        var span = document.createElement('span');
                        span.className = CONFIG.ANNOTATION_CLASS;
                        if (annotation.note) span.classList.add('has-note');
                        span.setAttribute('data-annotation-id', annotation.id);
                        span.style.backgroundColor = Utils.addColorAlpha(annotation.color, 0.4);
                        
                        range.surroundContents(span);
                        found = true;
                        break;
                    } catch (e) {
                        continue;
                    }
                }
            }
        },
        
        // 渲染所有标注
        renderAll: function() {
            var self = this;
            
            // 清除现有高亮
            this.clearHighlights();
            
            // 获取当前章节标注
            StorageManager.getByChapter(currentBookHash, currentChapterIndex).then(function(annotations) {
                self.annotations = annotations || [];
                
                // 逐个渲染
                for (var i = 0; i < self.annotations.length; i++) {
                    try {
                        self.renderSimpleHighlight(self.annotations[i]);
                    } catch (e) {}
                }
            }).catch(function(err) {
                console.error('Failed to load annotations:', err);
            });
        },
        
        // 清除高亮
        clearHighlights: function() {
            var highlights = document.querySelectorAll('.' + CONFIG.ANNOTATION_CLASS);
            highlights.forEach(function(el) {
                var parent = el.parentNode;
                while (el.firstChild) {
                    parent.insertBefore(el.firstChild, el);
                }
                parent.removeChild(el);
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
                            <span class="storage-option-status current">Current</span>\
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
            
            // Remove existing click listeners by cloning nodes
            allTabs.forEach(function(tab) {
                var newTab = tab.cloneNode(true);
                tab.parentNode.replaceChild(newTab, tab);
            });
            
            // Re-query after cloning
            allTabs = document.querySelectorAll('.settings-tab');
            
            // Add new click listeners
            allTabs.forEach(function(tab) {
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
                Utils.showNotification(Settings.enabled ? 'Annotation enabled' : 'Annotation disabled', 'info');
            });
            
            // Storage toggle
            var storageRadios = tabPanel.querySelectorAll('input[name="annotationStorage"]');
            storageRadios.forEach(function(radio) {
                radio.addEventListener('change', function() {
                    if (this.value === 'backend' && !Settings.backendAvailable) {
                        Utils.showNotification('Cloud storage unavailable', 'warning');
                        this.checked = false;
                        return;
                    }
                    
                    if (this.value !== Settings.storageType) {
                        self.showMigrationDialog(Settings.storageType, this.value);
                    }
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
                        
                        // Remove from settings
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
                    Settings.save();
                }
                
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
            
            StorageManager.isBackendAvailable().then(function(available) {
                Settings.backendAvailable = available;
                self.backendChecking = false;
                
                if (available) {
                    statusEl.textContent = 'Connected';
                    statusEl.className = 'storage-option-status connected';
                    backendOption.classList.remove('disabled');
                } else {
                    statusEl.textContent = 'Disconnected';
                    statusEl.className = 'storage-option-status disconnected';
                    backendOption.classList.add('disabled');
                }
            });
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
                var originalRadio = document.querySelector('input[name="annotationStorage"][value="' + fromType + '"]');
                if (originalRadio) {
                    originalRadio.checked = true;
                }
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
                
                // Update UI - clear all current classes first
                var idbOption = document.getElementById('storageOptionIdb');
                var backendOption = document.getElementById('storageOptionBackend');
                
                if (idbOption) {
                    var idbStatus = idbOption.querySelector('.storage-option-status');
                    if (idbStatus) {
                        if (newType === 'idb') {
                            idbStatus.textContent = 'Current';
                            idbStatus.className = 'storage-option-status current';
                        } else {
                            idbStatus.textContent = '';
                            idbStatus.className = 'storage-option-status';
                        }
                    }
                }
                
                if (backendOption) {
                    var backendStatus = backendOption.querySelector('.storage-option-status');
                    if (backendStatus) {
                        if (newType === 'backend') {
                            backendStatus.textContent = 'Current';
                            backendStatus.className = 'storage-option-status current';
                        } else {
                            backendStatus.textContent = '';
                            backendStatus.className = 'storage-option-status';
                        }
                    }
                }
                
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
            if (this.initialized) return;
            
            options = options || {};
            currentBookHash = options.bookHash || '';
            currentChapterIndex = options.chapterIndex || 0;
            
            // Load settings
            Settings.load();
            
            // Initialize storage
            var self = this;
            StorageManager.init().then(function() {
                // Initialize interaction
                HighlightInteraction.init();
                
                // Create settings tab
                SettingsTab.createContent();
                
                // Render existing annotations
                if (Settings.enabled) {
                    HighlightInteraction.renderAll();
                }
                
                self.initialized = true;
            }).catch(function(err) {
                console.error('Annotation module init failed:', err);
            });
        },
        
        // Destroy
        destroy: function() {
            HighlightInteraction.closeDialog();
            HighlightInteraction.clearHighlights();
            this.initialized = false;
        },
        
        // Refresh
        refresh: function() {
            if (Settings.enabled) {
                HighlightInteraction.renderAll();
            }
        },
        
        // Set book info
        setBookInfo: function(bookHash, chapterIndex) {
            currentBookHash = bookHash;
            currentChapterIndex = chapterIndex;
            this.refresh();
        },
        
        // Get annotation count
        getAnnotationCount: function() {
            return HighlightInteraction.annotations.length;
        }
    };
    
    // 导出模块
    global.AnnotationModule = AnnotationModule;
    
})(window);
