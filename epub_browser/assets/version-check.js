(function(root, factory) {
    var api = factory(root);
    if (typeof module === 'object' && module.exports) {
        module.exports = api;
    } else {
        root.EpubVersionCheck = api;
        api.start(root.document);
    }
}(typeof self !== 'undefined' ? self : this, function(root) {
    'use strict';

    function parseVersion(value) {
        var match = /^v?(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?$/.exec(String(value || '').trim());
        if (!match) return null;
        return {
            major: parseInt(match[1], 10),
            minor: parseInt(match[2], 10),
            patch: parseInt(match[3], 10),
            prerelease: match[4] || ''
        };
    }

    function compareVersions(left, right) {
        var a = parseVersion(left);
        var b = parseVersion(right);
        var keys = ['major', 'minor', 'patch'];
        var i;
        if (!a || !b) return 0;
        for (i = 0; i < keys.length; i += 1) {
            if (a[keys[i]] > b[keys[i]]) return 1;
            if (a[keys[i]] < b[keys[i]]) return -1;
        }
        if (!a.prerelease && b.prerelease) return 1;
        if (a.prerelease && !b.prerelease) return -1;
        if (a.prerelease > b.prerelease) return 1;
        if (a.prerelease < b.prerelease) return -1;
        return 0;
    }

    function updateFor(currentVersion, release) {
        var parsed;
        if (!release || release.draft || release.prerelease) return null;
        parsed = parseVersion(release.tag_name);
        if (!parsed || parsed.prerelease || compareVersions(release.tag_name, currentVersion) <= 0) return null;
        if (typeof release.html_url !== 'string' || release.html_url.indexOf('https://github.com/') !== 0) return null;
        return {
            version: parsed.major + '.' + parsed.minor + '.' + parsed.patch,
            url: release.html_url
        };
    }

    function render(footer, update, i18n) {
        var container;
        var link;
        if (!update) return;
        container = footer.querySelector('[data-version-update]');
        if (!container) return;
        link = container.querySelector('a');
        if (!link) return;
        link.setAttribute('data-i18n', 'version.updateAvailable');
        link.setAttribute('data-i18n-params', JSON.stringify({ version: update.version }));
        link.textContent = i18n && i18n.t ? i18n.t('version.updateAvailable', { version: update.version }) : 'Update available: v' + update.version;
        link.setAttribute('href', update.url);
        container.hidden = false;
    }

    var CACHE_DURATION = 6 * 60 * 60 * 1000;

    function requestRelease(url, done, options) {
        var xhr;
        var settings = options || {};
        var storage = settings.storage || (root && root.localStorage);
        var XMLHttpRequestClass = settings.XMLHttpRequest || (root && root.XMLHttpRequest);
        var now = settings.now ? settings.now() : Date.now();
        var cacheKey = 'epub-browser:latest-release:' + url;
        var cached;
        var release;
        if (storage) {
            try {
                cached = JSON.parse(storage.getItem(cacheKey) || 'null');
                if (cached && cached.release && now >= cached.checkedAt && now - cached.checkedAt < CACHE_DURATION) {
                    done(cached.release);
                    return;
                }
            } catch (error) {
                cached = null;
            }
        }
        if (!XMLHttpRequestClass) return;
        xhr = new XMLHttpRequestClass();
        xhr.open('GET', url, true);
        xhr.timeout = 4000;
        xhr.setRequestHeader('Accept', 'application/vnd.github+json');
        xhr.onreadystatechange = function() {
            if (xhr.readyState !== 4) return;
            if (xhr.status !== 200) return;
            try {
                release = JSON.parse(xhr.responseText);
                if (storage) {
                    try {
                        storage.setItem(cacheKey, JSON.stringify({
                            checkedAt: now,
                            release: release
                        }));
                    } catch (storageError) {
                        cached = null;
                    }
                }
                done(release);
            } catch (error) {
                return;
            }
        };
        xhr.send();
    }

    function check(doc, requester, i18n) {
        var footers;
        var apiUrl;
        var request = requester || requestRelease;
        var i;
        var runtime = i18n || (root && root.EpubBrowserI18n);
        if (!doc || !doc.querySelectorAll) return;
        footers = doc.querySelectorAll('[data-version-check]');
        if (!footers.length) return;
        apiUrl = footers[0].getAttribute('data-release-api');
        if (!apiUrl) return;
        request(apiUrl, function(release) {
            for (i = 0; i < footers.length; i += 1) {
                render(footers[i], updateFor(
                    footers[i].getAttribute('data-current-version'),
                    release
                ), runtime);
            }
        });
    }

    function start(doc) {
        if (!doc) return;
        if (doc.readyState === 'loading') {
            doc.addEventListener('DOMContentLoaded', function() { check(doc); });
        } else {
            check(doc);
        }
    }

    return {
        check: check,
        compareVersions: compareVersions,
        updateFor: updateFor,
        requestRelease: requestRelease,
        start: start
    };
}));
