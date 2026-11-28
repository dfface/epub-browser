(function(root) {
    'use strict';

    function fitNavigation(links) {
        var more = links.querySelector('.app-nav-more');
        var panel = more.querySelector('.app-nav-more-panel');
        var summary = more.querySelector('summary');
        var narrow = root.matchMedia('(max-width: 768px)');
        var actions = Array.from(links.children).filter(function(node) { return node !== more; });
        var ruler = document.createElement('div');
        ruler.className = 'app-nav-ruler';
        ruler.setAttribute('aria-hidden', 'true');
        ruler.inert = true;
        links.appendChild(ruler);
        var frame;

        function measure(node) {
            var copy = node.cloneNode(true);
            copy.removeAttribute('id');
            ruler.appendChild(copy);
            var width = copy.getBoundingClientRect().width;
            copy.remove();
            return width;
        }

        function layout() {
            frame = null;
            var available = links.clientWidth;
            if (!available) return;
            var scrollable = narrow.matches;
            var gap = parseFloat(getComputedStyle(links).columnGap) || 0;
            var visibleActions = actions.filter(function(action) {
                return !action.hidden && getComputedStyle(action).display !== 'none';
            });
            var widths = scrollable ? [] : actions.map(function(action) {
                return visibleActions.includes(action) ? measure(action) : 0;
            });
            var visible = widths.filter(Boolean);
            var fullWidth = visible.reduce(function(sum, width) { return sum + width; }, 0) +
                Math.max(0, visible.length - 1) * gap;
            var needsOverflow = !scrollable && fullWidth > available + 0.5;
            var budget = available;
            if (needsOverflow) budget -= measure(summary);
            var used = 0;
            var overflowing = false;
            var focus = document.activeElement;
            var focusMoved = false;

            actions.forEach(function(action, index) {
                var width = widths[index];
                if (needsOverflow && width && used + width + gap > budget + 0.5) overflowing = true;
                var destination = overflowing ? panel : links;
                if (action.parentNode !== destination) {
                    if (action === focus) focusMoved = true;
                    if (overflowing) {
                        var nextMember = actions.slice(index + 1).find(function(candidate) {
                            return candidate.parentNode === panel;
                        });
                        panel.insertBefore(action, nextMember || null);
                    } else {
                        links.insertBefore(action, more);
                    }
                }
                if (!overflowing && width) used += width + gap;
            });

            more.hidden = !overflowing;
            if (!overflowing) {
                more.open = false;
                if (focus === summary) {
                    var last = visibleActions[visibleActions.length - 1];
                    if (last) last.focus({ preventScroll: !scrollable });
                }
            }
            if (focusMoved) (panel.contains(focus) && !more.open ? summary : focus).focus({ preventScroll: !scrollable });
        }

        function schedule() {
            if (frame == null) frame = root.requestAnimationFrame(layout);
        }

        more.addEventListener('keydown', function(event) {
            if (event.key !== 'Escape' || !more.open) return;
            event.preventDefault();
            more.open = false;
            summary.focus();
        });

        function dismissOutside(event) {
            if (!more.open || more.contains(event.target)) return;
            // Keep an existing dialog's launcher visible for focus restoration.
            if (event.target.closest('[role="dialog"], [role="alertdialog"]')) return;
            more.open = false;
        }
        document.addEventListener('click', dismissOutside);
        document.addEventListener('focusin', dismissOutside);

        if (root.ResizeObserver) new ResizeObserver(schedule).observe(links);
        if (root.MutationObserver) {
            var observer = new MutationObserver(schedule);
            actions.forEach(function(action) {
                observer.observe(action, { attributes: true, attributeFilter: ['hidden', 'style'] });
            });
        }
        root.addEventListener('resize', schedule);
        if (root.EpubBrowserI18n) root.EpubBrowserI18n.onLocaleChange(schedule);
        if (document.fonts) document.fonts.ready.then(schedule);
        layout();
    }

    function bindInstall() {
        var button = document.getElementById('pwa-install-btn');
        if (!button) return;
        var deferredPrompt;
        if (root.EpubBrowserCacheBoundary && 'serviceWorker' in navigator) {
            root.addEventListener('load', function() {
                root.EpubBrowserCacheBoundary.registerWorker().catch(function() {});
            });
        }
        root.addEventListener('beforeinstallprompt', function(event) {
            event.preventDefault();
            deferredPrompt = event;
            button.hidden = false;
        });
        root.addEventListener('appinstalled', function() { button.hidden = true; });
        button.addEventListener('click', async function() {
            if (!deferredPrompt) return;
            var prompt = deferredPrompt;
            deferredPrompt = null;
            button.hidden = true;
            var t = root.EpubBrowserI18n.t;
            root.showNotification(t('library.installing'), 'info');
            try {
                await prompt.prompt();
                var result = await prompt.userChoice;
                if (result.outcome === 'accepted') root.showNotification(t('library.installSucceeded'), 'success');
                else root.showNotification(t('library.installCancelled'), 'info');
            } catch (_) {
                root.showNotification(t('library.installCancelled'), 'info');
            }
        });
    }

    document.addEventListener('DOMContentLoaded', function() {
        document.querySelectorAll('[data-app-nav-links]').forEach(fitNavigation);
        bindInstall();
    });
})(window);
