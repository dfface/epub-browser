"""Build deterministic, content-addressed browser assets for generated libraries."""

from __future__ import annotations

import hashlib
import json
import posixpath
import re
from dataclasses import dataclass
from pathlib import Path

from .urls import SiteURLs


WEB_MANIFEST_SOURCES = {
    'manifest.json': 'manifest.json',
    'manifest.en.json': 'manifest.json',
    'manifest.zh-CN.json': 'manifest.zh-CN.json',
    'manifest.zh-TW.json': 'manifest.zh-TW.json',
    'manifest.ko.json': 'manifest.ko.json',
    'manifest.ja.json': 'manifest.ja.json',
}

# These files implement authenticated Server-mode experiences. Keeping them out
# of a static export prevents orphaned account/AI controls and API clients from
# crossing the SSG boundary.
SERVER_ONLY_ASSET_PATHS = frozenset({
    'account.css',
    'auth.js',
    # Legacy AI-reading renderer kept for backwards-compatible source trees.
    'ai-reading.css',
    'ai-reading.js',
    'ai-canvas.css',
    'ai-canvas.js',
    'ai-chat.css',
    'ai-chat.js',
    'ai-reading-hub.css',
    'ai-reading-hub.js',
    'ai-rich-text.css',
    'ai-rich-text.js',
    'vendor/katex/katex.min.css',
    'vendor/katex/katex.min.js',
    'vendor/mermaid/mermaid.min.js',
})

# KaTeX ships its glyphs below this directory. A path-level exclusion would
# leave those fonts in static exports even though no SSG surface can use them.
SERVER_ONLY_ASSET_PREFIXES = frozenset({
    'vendor/katex/',
})


@dataclass(frozen=True)
class PublishedAssets:
    """The logical-to-public URL map for one generated library release."""

    assets: dict[str, str]

    def url_for(self, logical_name: str) -> str:
        return self.assets[logical_name]


class AssetPublisher:
    """Publish app assets with immutable URLs and render stable update entry points."""

    def __init__(
        self,
        source_dir,
        output_dir,
        urls=None,
        publish_service_worker=True,
        excluded_paths=(),
        excluded_prefixes=(),
    ):
        self.source_dir = Path(source_dir)
        self.output_dir = Path(output_dir)
        self.urls = urls or SiteURLs()
        self.publish_service_worker = publish_service_worker
        self.excluded_paths = frozenset(excluded_paths)
        self.excluded_prefixes = tuple(excluded_prefixes)

    def publish(self) -> PublishedAssets:
        assets = self._copy_immutable_assets()
        published = PublishedAssets(assets)
        self._write_lookup_manifest(published)
        self._write_web_manifests(published)
        if self.publish_service_worker:
            self._write_service_worker(published)
        return published

    def _copy_immutable_assets(self) -> dict[str, str]:
        source_contents = {
            path.relative_to(self.source_dir).as_posix(): path.read_bytes()
            for path in sorted(path for path in self.source_dir.rglob('*') if path.is_file())
            if not self._is_excluded(path.relative_to(self.source_dir).as_posix())
        }
        preliminary_assets = {
            logical_path: self._immutable_url(logical_path, contents)
            for logical_path, contents in source_contents.items()
        }
        published_contents = {
            logical_path: self._rewrite_css_urls(logical_path, contents, preliminary_assets)
            if logical_path.endswith('.css') else contents
            for logical_path, contents in source_contents.items()
        }
        assets = {
            logical_path: self._immutable_url(logical_path, contents)
            for logical_path, contents in published_contents.items()
        }
        for logical_path, contents in published_contents.items():
            target = self.output_dir / self.urls.filesystem_relative(assets[logical_path])
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(contents)
        return assets

    def _is_excluded(self, logical_path: str) -> bool:
        return (
            logical_path in {
                'sw.js',
                'manifest.json',
                'manifest.zh-CN.json',
                'manifest.zh-TW.json',
                'manifest.ko.json',
                'manifest.ja.json',
            } | self.excluded_paths
            or any(logical_path.startswith(prefix) for prefix in self.excluded_prefixes)
        )

    def _immutable_url(self, logical_path: str, contents: bytes) -> str:
        digest = hashlib.sha256(contents).hexdigest()[:12]
        relative = Path(logical_path)
        filename = f'{relative.stem}.{digest}{relative.suffix}'
        return self.urls.public(
            '/assets/immutable/' + (relative.parent / filename).as_posix()
        )

    def _rewrite_css_urls(self, logical_path: str, contents: bytes, assets: dict[str, str]) -> bytes:
        try:
            stylesheet = contents.decode('utf-8')
        except UnicodeDecodeError:
            return contents

        def replace(match):
            url = match.group(2).strip()
            if url.startswith(('/', '#', 'data:', 'http:', 'https:', '//')):
                return match.group(0)
            target = posixpath.normpath(posixpath.join(posixpath.dirname(logical_path), url))
            if target not in assets:
                return match.group(0)
            return 'url(' + json.dumps(assets[target]) + ')'

        return re.sub(r'url\(\s*([\'\"]?)([^\'\")]+)\1\s*\)', replace, stylesheet).encode('utf-8')

    def _write_lookup_manifest(self, published: PublishedAssets) -> None:
        target = self.output_dir / 'assets' / 'asset-manifest.json'
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(published.assets, ensure_ascii=False, sort_keys=True, separators=(',', ':')),
            encoding='utf-8',
        )

    def _write_web_manifests(self, published: PublishedAssets) -> None:
        for output_name, source_name in WEB_MANIFEST_SOURCES.items():
            source = self.source_dir / source_name
            manifest = self._rewrite_asset_urls(
                json.loads(source.read_text(encoding='utf-8')),
                published,
            )
            target = self.output_dir / 'assets' / output_name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    def _rewrite_asset_urls(self, value, published: PublishedAssets):
        if isinstance(value, list):
            return [self._rewrite_asset_urls(item, published) for item in value]
        if isinstance(value, dict):
            return {key: self._rewrite_asset_urls(item, published) for key, item in value.items()}
        if isinstance(value, str) and value.startswith('/assets/'):
            logical_name = value.removeprefix('/assets/')
            return published.assets.get(logical_name, self.urls.public(value))
        if isinstance(value, str) and value.startswith('/') and not value.startswith('//'):
            return self.urls.public(value)
        return value

    def _write_service_worker(self, published: PublishedAssets) -> None:
        source = self.source_dir / 'sw.js'
        if not source.is_file():
            return
        release_id = hashlib.sha256(
            json.dumps(published.assets, sort_keys=True, separators=(',', ':')).encode('utf-8')
        ).hexdigest()[:12]
        mutable_manifests = [
            self.urls.public(f'/assets/{name}') for name in WEB_MANIFEST_SOURCES
        ]
        index_url = self.urls.public('/index.html')
        precache_urls = [index_url, *published.assets.values(), *mutable_manifests]
        worker = source.read_text(encoding='utf-8')
        worker = worker.replace('__EPUB_BROWSER_RELEASE_ID__', release_id)
        worker = worker.replace('__EPUB_BROWSER_PRECACHE_URLS__', json.dumps(precache_urls, separators=(',', ':')))
        worker = worker.replace('__EPUB_BROWSER_MUTABLE_MANIFEST_URLS__', json.dumps(mutable_manifests, separators=(',', ':')))
        worker = worker.replace('__EPUB_BROWSER_INDEX_URL__', json.dumps(index_url))
        target = self.output_dir / 'sw.js'
        target.write_text(worker, encoding='utf-8')


def rewrite_asset_urls(html: str, published: PublishedAssets) -> str:
    """Replace generated pages' project-owned asset URLs with immutable URLs."""

    def replace(match):
        logical_name = match.group(1)
        return published.assets.get(logical_name, match.group(0))

    return re.sub(r'/assets/([A-Za-z0-9_./-]+)(?:\?v=\d+)?', replace, html)
