"""Build deterministic, content-addressed browser assets for generated libraries."""

from __future__ import annotations

import hashlib
import json
import posixpath
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PublishedAssets:
    """The logical-to-public URL map for one generated library release."""

    assets: dict[str, str]

    def url_for(self, logical_name: str) -> str:
        return self.assets[logical_name]


class AssetPublisher:
    """Publish app assets with immutable URLs and render stable update entry points."""

    def __init__(self, source_dir, output_dir):
        self.source_dir = Path(source_dir)
        self.output_dir = Path(output_dir)

    def publish(self) -> PublishedAssets:
        assets = self._copy_immutable_assets()
        published = PublishedAssets(assets)
        self._write_lookup_manifest(published)
        self._write_web_manifest(published)
        self._write_service_worker(published)
        return published

    def _copy_immutable_assets(self) -> dict[str, str]:
        source_contents = {
            path.relative_to(self.source_dir).as_posix(): path.read_bytes()
            for path in sorted(path for path in self.source_dir.rglob('*') if path.is_file())
            if path.relative_to(self.source_dir).as_posix() not in {'sw.js', 'manifest.json'}
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
            target = self.output_dir / assets[logical_path].lstrip('/')
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(contents)
        return assets

    def _immutable_url(self, logical_path: str, contents: bytes) -> str:
        digest = hashlib.sha256(contents).hexdigest()[:12]
        relative = Path(logical_path)
        filename = f'{relative.stem}.{digest}{relative.suffix}'
        return '/assets/immutable/' + (relative.parent / filename).as_posix()

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

    def _write_web_manifest(self, published: PublishedAssets) -> None:
        source = self.source_dir / 'manifest.json'
        if not source.is_file():
            return
        manifest = json.loads(source.read_text(encoding='utf-8'))
        rewritten = self._rewrite_asset_urls(manifest, published)
        target = self.output_dir / 'assets' / 'manifest.json'
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(rewritten, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    def _rewrite_asset_urls(self, value, published: PublishedAssets):
        if isinstance(value, list):
            return [self._rewrite_asset_urls(item, published) for item in value]
        if isinstance(value, dict):
            return {key: self._rewrite_asset_urls(item, published) for key, item in value.items()}
        if isinstance(value, str) and value.startswith('/assets/'):
            logical_name = value.removeprefix('/assets/')
            return published.assets.get(logical_name, value)
        return value

    def _write_service_worker(self, published: PublishedAssets) -> None:
        source = self.source_dir / 'sw.js'
        if not source.is_file():
            return
        release_id = hashlib.sha256(
            json.dumps(published.assets, sort_keys=True, separators=(',', ':')).encode('utf-8')
        ).hexdigest()[:12]
        precache_urls = ['/index.html', *published.assets.values()]
        worker = source.read_text(encoding='utf-8')
        worker = worker.replace('__EPUB_BROWSER_RELEASE_ID__', release_id)
        worker = worker.replace('__EPUB_BROWSER_PRECACHE_URLS__', json.dumps(precache_urls, separators=(',', ':')))
        target = self.output_dir / 'sw.js'
        target.write_text(worker, encoding='utf-8')


def rewrite_asset_urls(html: str, published: PublishedAssets) -> str:
    """Replace generated pages' project-owned asset URLs with immutable URLs."""

    def replace(match):
        logical_name = match.group(1)
        return published.assets.get(logical_name, match.group(0))

    return re.sub(r'/assets/([A-Za-z0-9_.-]+)(?:\?v=\d+)?', replace, html)
