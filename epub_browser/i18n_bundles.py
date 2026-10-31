"""Server-side helpers for the split i18n bundles.

Each locale ships as a standalone JSON file under ``assets/i18n/<locale>.json``.
The browser runtime (``i18n-core.js``) registers dictionaries either inline
(Server mode, which ships only the active language) or by fetching them on
demand (SSG and language switches). This module loads the JSON packs once per
process and renders the inline ``<script>`` tags the templates need.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from .locales import SUPPORTED_LOCALES, normalize_locale

_I18N_DIR = Path(__file__).resolve().parent / 'assets' / 'i18n'

_cache: dict[str, dict] = {}


def _immutable_source_url(relative_path: str) -> str | None:
    """Content-addressed URL for a source i18n asset, matching the publisher.

    ``relative_path`` is the full logical path (e.g. ``i18n/i18n-core.js``). The
    asset publisher hashes the raw file bytes and writes the same content under
    ``/assets/immutable/<dir>/<stem>.<hash><suffix>``; computing the hash from
    the identical source bytes yields the same URL, so the manifest is stable
    whether it is generated before or after publishing.
    """
    import hashlib

    source = _I18N_DIR.parent / relative_path
    if not source.is_file():
        return None
    digest = hashlib.sha256(source.read_bytes()).hexdigest()[:12]
    name = Path(relative_path)
    hashed = f'{name.stem}.{digest}{name.suffix}'
    return '/assets/immutable/' + (name.parent / hashed).as_posix()


def build_i18n_manifest() -> dict:
    """Public locale -> hashed-URL manifest built from the source packs.

    The Server exposes this at the stable, unauthenticated
    ``/assets/i18n-manifest.json`` so the browser can fetch only the active
    language at runtime, even before any book has been published.
    """
    locales: dict[str, str] = {}
    for code in SUPPORTED_LOCALES:
        url = _immutable_source_url(f'i18n/{code}.json')
        if url:
            locales[code] = url
    return {'core': _immutable_source_url('i18n/i18n-core.js'), 'locales': locales}


def i18n_core_immutable_url() -> str | None:
    """Content-addressed URL of the i18n runtime loader.

    Derived from the source file so it is stable whether or not the asset
    publisher has run; the published hash matches because identical bytes are
    written under the same immutable path.
    """
    return _immutable_source_url('i18n/i18n-core.js')


def read_i18n_asset(relative_path: str) -> tuple[bytes, str] | None:
    """Serve an i18n asset (logical or content-addressed) from the source tree.

    ``relative_path`` is the public path without a leading slash, e.g.
    ``i18n/de.json`` or ``immutable/i18n/de.013bc0572345.json``. This lets the
    Server resolve locale packs and the runtime loader even before the asset
    publisher has run (e.g. during first-run setup), using the same bytes the
    publisher would hash. Immutable names are verified against the source hash
    so a mismatched digest is rejected rather than served.
    """
    import hashlib
    import mimetypes
    import re

    if relative_path.startswith('assets/'):
        relative_path = relative_path[len('assets/'):]
    if relative_path.startswith('i18n/'):
        source = _I18N_DIR / relative_path[len('i18n/'):]
        if not source.is_file():
            return None
        return source.read_bytes(), mimetypes.guess_type(str(source))[0] or 'application/octet-stream'
    if relative_path.startswith('immutable/i18n/'):
        filename = relative_path.rsplit('/', 1)[-1]
        match = re.match(r'^(.*?)\.[0-9a-f]{12}(\..+)$', filename)
        if not match:
            return None
        source = _I18N_DIR / (match.group(1) + match.group(2))
        if not source.is_file():
            return None
        digest = hashlib.sha256(source.read_bytes()).hexdigest()[:12]
        if digest != filename.split('.')[1]:
            return None
        return source.read_bytes(), mimetypes.guess_type(str(source))[0] or 'application/octet-stream'
    return None

# Namespaces that belong to server-only surfaces (account administration, API
# documentation, AI reading, reading insights, private reviews). SSG pages must
# never ship them: the runtime still fetches the full per-locale pack via the
# i18n manifest, so excluding them from the inline bootstrap only affects the
# very first paint and never the final rendered text.
SSG_EXCLUDED_I18N_NAMESPACES = frozenset(
    ('apiDocs', 'account', 'admin', 'readingInsights', 'bookReviews', 'ai')
)


def _client_safe_bundle(bundle: dict) -> dict:
    return {
        key: value
        for key, value in bundle.items()
        if key.split('.', 1)[0] not in SSG_EXCLUDED_I18N_NAMESPACES
    }


def get_bundle(locale: str) -> dict:
    """Return the dictionary for ``locale``, loading and caching it once."""
    if locale not in _cache:
        path = _I18N_DIR / f'{locale}.json'
        try:
            _cache[locale] = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            _cache[locale] = {}
    return _cache[locale]


def clear_cache() -> None:
    _cache.clear()


def _safe_json(value: dict) -> str:
    # Escape '<' so translated copy can never break out of a <script> block.
    return json.dumps(value, ensure_ascii=False, separators=(',', ':')).replace('<', '\\u003c')


def _register_script(locale: str, bundle: dict | None = None) -> str:
    if bundle is None:
        bundle = get_bundle(locale)
    return (
        '<script>window.EpubBrowserI18n.registerDictionary('
        + json.dumps(locale)
        + ','
        + _safe_json(bundle)
        + ');</script>'
    )


def runtime_script_tag(base_path: str = '/', core_url: str | None = None) -> str:
    if core_url:
        return '<script src="' + core_url + '"></script>'
    prefix = base_path.rstrip('/')
    return '<script src="' + prefix + '/assets/i18n/i18n-core.js"></script>'


def i18n_boot_snippet() -> str:
    """Hide translatable text until the runtime applies the active locale.

    Pages inline only the English pack for the first screen and fetch the real
    locale asynchronously; without this the UI flashes English before switching
    to the user's language. Marking ``<html>`` with ``i18n-boot`` keeps
    ``[data-i18n]`` content invisible (the hide rule lives in ``theme.css``) until
    ``i18n-core.js`` calls ``reveal()`` after translating. A safety timeout
    reveals the page even if the runtime never loads, so a failed fetch degrades
    to English rather than a blank UI.
    """
    return (
        '<script>document.documentElement.classList.add("i18n-boot");'
        'setTimeout(function(){document.documentElement.classList.remove("i18n-boot");},3000);</script>'
    )


def inline_i18n(locale: str | None = None, deployment_mode: str = 'server') -> str:
    """Inline the English fallback and, when given, the active locale pack.

    Server mode passes the resolved locale so only the needed language ships with
    the full key set. SSG ships a client-safe subset: server-only namespaces
    (account, admin, AI reading, reading insights, private reviews, API docs) are
    omitted from the inline bootstrap because the runtime fetches the complete
    pack via the i18n manifest after load.
    """
    client_safe = deployment_mode == 'ssg'
    en = get_bundle('en')
    tags = [_register_script('en', _client_safe_bundle(en) if client_safe else en)]
    if locale and locale != 'en' and locale in SUPPORTED_LOCALES:
        loc = get_bundle(locale)
        tags.append(_register_script(locale, _client_safe_bundle(loc) if client_safe else loc))
    return ''.join(tags)


def init_script_tag(explicit_locale: str | None = None) -> str:
    script = 'window.EpubBrowserI18n.init();'
    if explicit_locale:
        script += 'window.EpubBrowserI18n.setLocale(' + json.dumps(explicit_locale) + ');'
    return '<script>' + script + '</script>'


def render_i18n_bootstrap(
    locale: str | None = None,
    explicit_locale: str | None = None,
    base_path: str = '/',
    core_url: str | None = None,
    deployment_mode: str = 'server',
) -> str:
    """Full i18n bootstrap: load the runtime, register the needed packs, init.

    ``core_url`` is the content-addressed (hashed) runtime URL when the caller
    can resolve it (Server mode); otherwise a logical path is emitted and the
    page's ``rewrite_asset_urls`` pass hashes it. ``deployment_mode`` controls
    whether server-only locale packs are inlined (server) or omitted (ssg).
    """
    return (
        i18n_boot_snippet()
        + runtime_script_tag(base_path, core_url)
        + inline_i18n(locale, deployment_mode)
        + init_script_tag(explicit_locale)
    )


def render_i18n_runtime_and_inline(
    base_path: str = '/',
    core_url: str | None = None,
    deployment_mode: str = 'ssg',
) -> str:
    """Runtime loader plus the English pack, without the init call.

    Used where a later pass sets ``window.EpubBrowserBasePath`` and triggers
    ``init()`` (server chrome and SSG page post-processing), so the active
    locale is fetched with the correct base path. ``deployment_mode`` controls
    whether server-only locale packs are inlined (server) or omitted (ssg).
    """
    return i18n_boot_snippet() + runtime_script_tag(base_path, core_url) + inline_i18n(None, deployment_mode)


def resolve_request_locale(request) -> str:
    """Best-effort locale for a request, matching the browser runtime's fallback."""
    cookie = (getattr(request, 'cookies', None) or {}).get('epub_browser_locale')
    if cookie:
        resolved = normalize_locale(cookie)
        if resolved:
            return resolved
    accept_language = (getattr(request, 'headers', None) or {}).get('accept-language', '')
    if accept_language:
        resolved = normalize_locale(accept_language.split(',')[0].split(';')[0].strip())
        if resolved:
            return resolved
    return 'en'
