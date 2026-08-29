import json
import threading
import time
from urllib.request import Request, urlopen


VERSION = "2.9.2"

REPOSITORY_URL = "https://github.com/dfface/epub-browser"
LATEST_RELEASE_API_URL = "https://api.github.com/repos/dfface/epub-browser/releases/latest"
RELEASE_CACHE_SECONDS = 6 * 60 * 60
_SAFE_RELEASE_FIELDS = ("tag_name", "html_url", "draft", "prerelease")


def _fetch_latest_release(url):
    request = Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "epub-browser-version-check",
        },
    )
    with urlopen(request, timeout=4) as response:
        return json.load(response)


class ReleaseLookup:
    """Fetch and cache the one release document the application exposes."""

    def __init__(self, fetcher=None, now=None):
        self._fetcher = fetcher or _fetch_latest_release
        self._now = now or time.monotonic
        self._lock = threading.Lock()
        self._cached_at = None
        self._cached_release = None

    @staticmethod
    def _safe_release(value):
        if not isinstance(value, dict):
            return None
        tag_name = value.get("tag_name")
        html_url = value.get("html_url")
        if not isinstance(tag_name, str) or not tag_name:
            return None
        if (
            not isinstance(html_url, str)
            or not html_url.startswith("https://github.com/dfface/epub-browser/releases/")
        ):
            return None
        return {
            "tag_name": tag_name,
            "html_url": html_url,
            "draft": bool(value.get("draft")),
            "prerelease": bool(value.get("prerelease")),
        }

    def fetch(self):
        with self._lock:
            now = self._now()
            if (
                self._cached_release is not None
                and self._cached_at is not None
                and now - self._cached_at < RELEASE_CACHE_SECONDS
            ):
                return dict(self._cached_release)
            try:
                release = self._safe_release(self._fetcher(LATEST_RELEASE_API_URL))
            except (OSError, ValueError, json.JSONDecodeError):
                return None
            if release is None:
                return None
            self._cached_at = now
            self._cached_release = release
            return dict(release)


def render_footer(year, release_api_url=LATEST_RELEASE_API_URL):
    """Render the shared application footer for every generated page."""
    return f"""<footer class="eb-footer" data-id="eb-footer" data-version-check data-current-version="{VERSION}" data-release-api="{release_api_url}">
    <p><span data-i18n="footer.product">EPUB Library</span> &copy; {year} | <span data-i18n="footer.poweredBy">Powered by</span> <a href="{REPOSITORY_URL}" target="_blank" rel="noopener noreferrer">epub-browser</a><!-- i18n-allow-literal: product name --> <span data-i18n="footer.poweredBySuffix">&middot;</span> <span class="eb-footer-version" aria-label="Version {VERSION}" data-i18n-aria-label="common.version" data-i18n-params='{{"version":"{VERSION}"}}'>v{VERSION}</span><span class="eb-footer-update" data-version-update hidden><span aria-hidden="true"> &middot; </span><a target="_blank" rel="noopener noreferrer"></a></span></p>
</footer>"""
