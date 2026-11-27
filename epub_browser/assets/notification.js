(function(root, factory) {
    var api = factory(root);
    api.create = function(target) { return factory(target); };
    if (typeof module === 'object' && module.exports) module.exports = api;
    if (root && root.document) {
        root.EpubBrowserNotification = api;
        root.showNotification = api.show;
    }
})(typeof window !== 'undefined' ? window : (typeof globalThis !== 'undefined' ? globalThis : this), function(root) {
    'use strict';

    var activeNotification = null;
    var hideTimer = null;
    var removeTimer = null;
    var allowedTypes = { success: true, info: true, warning: true, error: true };

    var positionKey = 'epub-notification-position';
    function normalizePosition(value) {
        return ['top','bottom','top-left','top-right','bottom-left','bottom-right'].indexOf(value)>=0 ? value : 'auto';
    }
    function getPosition() {
        var value;
        try { value = root.localStorage.getItem(positionKey); } catch (error) {}
        return normalizePosition(value);
    }
    function setPosition(value) {
        value = normalizePosition(value);
        try { root.localStorage.setItem(positionKey, value); } catch (error) {}
        place();
    }
    function place() {
        var node = activeNotification;
        if (!node || !node.style) return;
        var choice = getPosition(), mobile = root.innerWidth <= 768;
        var placement = choice==='auto' ? (mobile?'bottom':'bottom-left') : choice;
        if(mobile)placement=placement.indexOf('top')===0?'top':'bottom';
        var upper=placement.indexOf('top')===0;
        var viewport = root.visualViewport;
        var top = viewport ? viewport.offsetTop : 0;
        var bottom = viewport ? top + viewport.height : root.innerHeight;
        var offset = root.innerHeight - bottom + 16, topOffset=top+16;
        var bounds=node.getBoundingClientRect ? node.getBoundingClientRect() : {width:320,height:70};
        var left=placement.endsWith('left')?16:placement.endsWith('right')?root.innerWidth-bounds.width-16:(root.innerWidth-bounds.width)/2;
        root.document.querySelectorAll('.mobile-controls,.reader-toolbar,.app-header').forEach(function(toolbar) {
            if(!toolbar.getClientRects().length)return;
            var rect=toolbar.getBoundingClientRect();
            if(rect.right<=left || rect.left>=left+bounds.width)return;
            var toastTop=upper?topOffset:root.innerHeight-offset-bounds.height;
            if(rect.bottom<=toastTop || rect.top>=toastTop+bounds.height)return;
            if(upper)topOffset=Math.max(topOffset,rect.bottom+12);
            else offset=Math.max(offset,root.innerHeight-rect.top+12);
        });
        node.setAttribute('data-notification-placement',placement);
        node.style.setProperty('--notification-top',Math.min(topOffset,Math.max(top+16,bottom-bounds.height-16))+'px');
        node.style.setProperty('--notification-bottom',Math.min(offset,Math.max(root.innerHeight-bottom+16,root.innerHeight-top-bounds.height-16))+'px');
    }
    function initPreferences() {
        var select = root.document && root.document.getElementById('notificationPosition');
        if (select) {
            select.value=getPosition();
            select.addEventListener('change',function(){setPosition(select.value);});
            var preview=root.document.getElementById('notificationPreview');
            if(preview)preview.addEventListener('click',function(){
                show('', 'info', {messageKey:'bookmarks.notificationPreviewMessage'});
            });
        }
    }
    if (root.addEventListener) {
        root.addEventListener('resize',place);
        root.addEventListener('scroll',place,{passive:true});
        root.addEventListener('storage',function(){place();});
        if (root.visualViewport) {
            root.visualViewport.addEventListener('resize',place);
            root.visualViewport.addEventListener('scroll',place);
        }
        if (root.document.readyState==='loading') root.document.addEventListener('DOMContentLoaded',initPreferences);
        else initPreferences();
    }

    function clearTimers() {
        if (hideTimer !== null) root.clearTimeout(hideTimer);
        if (removeTimer !== null) root.clearTimeout(removeTimer);
        hideTimer = null;
        removeTimer = null;
    }

    function dismiss(notification) {
        var target = notification || activeNotification;
        if (!target || target !== activeNotification) return;
        clearTimers();
        target.classList.add('fade-out');
        removeTimer = root.setTimeout(function() {
            restoreFocus(target);
            if (target.parentNode) target.parentNode.removeChild(target);
            if (activeNotification === target) activeNotification = null;
            removeTimer = null;
        }, 300);
    }

    function restoreFocus(node) {
        if (node.contains && node.contains(root.document.activeElement) && node.returnFocus && node.returnFocus.isConnected) {
            node.returnFocus.focus({preventScroll:true});
        }
    }

    function show(message, type, options) {
        if (!root.document || !root.document.body) return null;
        clearTimers();
        if (activeNotification && activeNotification.parentNode) {
            restoreFocus(activeNotification);
            activeNotification.parentNode.removeChild(activeNotification);
        }

        var normalizedType = allowedTypes[type] ? type : 'info';
        var notification = root.document.createElement('div');
        notification.className = 'app-notification custom-css-notification ' + normalizedType;
        notification.setAttribute('data-epub-browser-notification', '');
        notification.setAttribute('role', normalizedType === 'error' ? 'alert' : 'status');
        notification.setAttribute('aria-live', normalizedType === 'error' ? 'assertive' : 'polite');
        var settings = options || {};
        function translated(key, fallback) {
            return key && root.EpubBrowserI18n ? root.EpubBrowserI18n.t(key) : String(fallback || '');
        }
        notification.returnFocus = settings.returnFocus;
        if (settings.messageKey) {
            var label = root.document.createElement('span');
            label.textContent = translated(settings.messageKey, message);
            label.setAttribute('data-i18n', settings.messageKey);
            notification.appendChild(label);
        } else {
            notification.textContent = String(message == null ? '' : message);
        }
        if (settings.action && typeof settings.action.onClick === 'function') {
            var action = root.document.createElement('button');
            action.type = 'button';
            action.className = 'notification-action';
            action.textContent = translated(settings.action.labelKey, settings.action.label);
            if (settings.action.labelKey) action.setAttribute('data-i18n', settings.action.labelKey);
            action.addEventListener('click', function() {
                if (action.disabled) return;
                action.disabled = true;
                Promise.resolve().then(settings.action.onClick).then(function() {
                    if (activeNotification === notification) dismiss(notification);
                }).catch(function() {
                    action.disabled = false;
                });
            });
            notification.appendChild(action);
        }
        root.document.body.appendChild(notification);
        activeNotification = notification;
        place();

        var duration = Number(settings.duration);
        if (!isFinite(duration) || duration < 0) duration = normalizedType === 'error' ? 5000 : 3000;
        function pause() {
            if (hideTimer !== null) root.clearTimeout(hideTimer);
            hideTimer = null;
        }
        function resume() {
            pause();
            if (settings.persistent !== true && activeNotification === notification) {
                hideTimer = root.setTimeout(function() {
                    hideTimer = null;
                    dismiss(notification);
                }, duration);
            }
        }
        if (settings.action) {
            notification.addEventListener('mouseenter', pause);
            notification.addEventListener('focusin', pause);
            notification.addEventListener('mouseleave', function() {
                if (!notification.contains(root.document.activeElement)) resume();
            });
            notification.addEventListener('focusout', function(event) {
                if (!notification.contains(event.relatedTarget) && !notification.matches(':hover')) resume();
            });
        }
        resume();
        return notification;
    }

    return { show: show, dismiss: dismiss, getPosition:getPosition, setPosition:setPosition };
});
