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

    function clearTimers() {
        if (hideTimer !== null) root.clearTimeout(hideTimer);
        if (removeTimer !== null) root.clearTimeout(removeTimer);
        hideTimer = null;
        removeTimer = null;
    }

    function dismiss(notification) {
        var target = notification || activeNotification;
        if (!target) return;
        clearTimers();
        target.classList.add('fade-out');
        removeTimer = root.setTimeout(function() {
            if (target.parentNode) target.parentNode.removeChild(target);
            if (activeNotification === target) activeNotification = null;
            removeTimer = null;
        }, 300);
    }

    function show(message, type, options) {
        if (!root.document || !root.document.body) return null;
        clearTimers();
        if (activeNotification && activeNotification.parentNode) {
            activeNotification.parentNode.removeChild(activeNotification);
        }

        var normalizedType = allowedTypes[type] ? type : 'info';
        var notification = root.document.createElement('div');
        notification.className = 'app-notification custom-css-notification ' + normalizedType;
        notification.setAttribute('data-epub-browser-notification', '');
        notification.setAttribute('role', normalizedType === 'error' ? 'alert' : 'status');
        notification.setAttribute('aria-live', normalizedType === 'error' ? 'assertive' : 'polite');
        notification.textContent = String(message == null ? '' : message);
        root.document.body.appendChild(notification);
        activeNotification = notification;

        var settings = options || {};
        if (settings.persistent !== true) {
            var duration = Number(settings.duration);
            if (!isFinite(duration) || duration < 0) duration = normalizedType === 'error' ? 5000 : 3000;
            hideTimer = root.setTimeout(function() {
                hideTimer = null;
                dismiss(notification);
            }, duration);
        }
        return notification;
    }

    return { show: show, dismiss: dismiss };
});
