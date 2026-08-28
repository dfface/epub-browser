import json
import re
import tempfile
import unittest
from pathlib import Path

from epub_browser.library import EPUBLibrary
from epub_browser.locales import SUPPORTED_LOCALES


class StaticAssetDeliveryTests(unittest.TestCase):
    def test_generated_library_publishes_nested_vendor_assets(self):
        with tempfile.TemporaryDirectory() as directory:
            library = EPUBLibrary(directory)

            library.create_library_home()

            root = Path(directory)
            html = (root / 'index.html').read_text(encoding='utf-8')
            vendor_urls = re.findall(
                r'/assets/immutable/vendor/[A-Za-z0-9_./-]+\.[0-9a-f]{12}\.[A-Za-z0-9]+',
                html,
            )
            self.assertTrue(vendor_urls)
            for public_url in vendor_urls:
                self.assertTrue((root / public_url.lstrip('/')).is_file(), public_url)

    def test_generated_library_has_complete_versioned_app_shell(self):
        with tempfile.TemporaryDirectory() as directory:
            library = EPUBLibrary(directory)
            library.create_library_home()

            root = Path(directory)
            html = (root / 'index.html').read_text(encoding='utf-8')
            asset_urls = re.findall(
                r'/assets/immutable/[A-Za-z0-9_./-]+\.[0-9a-f]{12}\.[A-Za-z0-9]+',
                html,
            )

            self.assertTrue(asset_urls)
            self.assertNotIn('?v=', html)
            self.assertTrue((root / 'sw.js').is_file())
            self.assertTrue((root / 'assets' / 'manifest.json').is_file())
            for locale in SUPPORTED_LOCALES:
                self.assertTrue((root / 'assets' / f'manifest.{locale}.json').is_file())
            self.assertTrue((root / 'assets' / 'asset-manifest.json').is_file())
            for public_url in asset_urls:
                self.assertTrue((root / public_url.lstrip('/')).is_file(), public_url)
            self.assertFalse((root / 'annotations' / 'index.html').exists())

            manifest = json.loads((root / 'assets' / 'manifest.json').read_text(encoding='utf-8'))
            for icon in manifest['icons']:
                self.assertRegex(icon['src'], r'^/assets/immutable/icon-[0-9]+\.[0-9a-f]{12}\.png$')
            chinese_manifest = json.loads((root / 'assets' / 'manifest.zh-CN.json').read_text(encoding='utf-8'))
            self.assertEqual(chinese_manifest['lang'], 'zh-CN')
            for locale in SUPPORTED_LOCALES:
                localized = json.loads((root / 'assets' / f'manifest.{locale}.json').read_text(encoding='utf-8'))
                self.assertEqual(localized['lang'], locale)
