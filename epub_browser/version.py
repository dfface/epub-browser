VERSION = "2.3.8"

REPOSITORY_URL = "https://github.com/dfface/epub-browser"
LATEST_RELEASE_API_URL = "https://api.github.com/repos/dfface/epub-browser/releases/latest"


def render_footer(year):
    """Render the shared application footer for every generated page."""
    return f"""<footer class="eb-footer" data-id="eb-footer" data-version-check data-current-version="{VERSION}" data-release-api="{LATEST_RELEASE_API_URL}">
    <p><span data-i18n="footer.product">EPUB Library</span> &copy; {year} | <span data-i18n="footer.poweredBy">Powered by</span> <a href="{REPOSITORY_URL}" target="_blank" rel="noopener noreferrer">epub-browser</a><!-- i18n-allow-literal: product name --> <span data-i18n="footer.poweredBySuffix">&middot;</span> <span class="eb-footer-version" aria-label="Version {VERSION}" data-i18n-aria-label="common.version" data-i18n-params='{{"version":"{VERSION}"}}'>v{VERSION}</span><span class="eb-footer-update" data-version-update hidden><span aria-hidden="true"> &middot; </span><a target="_blank" rel="noopener noreferrer"></a></span></p>
</footer>"""
