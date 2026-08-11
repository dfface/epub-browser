import json
import re
import tempfile
import unittest
from pathlib import Path

from epub_browser.library import EPUBLibrary


class StaticAssetDeliveryTests(unittest.TestCase):
    def test_generated_library_has_complete_versioned_app_shell(self):
        with tempfile.TemporaryDirectory() as directory:
            library = EPUBLibrary(directory)
            library.create_library_home()

            root = Path(directory)
            html = (root / 'index.html').read_text(encoding='utf-8')
            asset_urls = re.findall(r'/assets/immutable/[A-Za-z0-9_.-]+', html)

            self.assertTrue(asset_urls)
            self.assertNotIn('?v=', html)
            self.assertTrue((root / 'sw.js').is_file())
            self.assertTrue((root / 'assets' / 'manifest.json').is_file())
            self.assertTrue((root / 'assets' / 'asset-manifest.json').is_file())
            for public_url in asset_urls:
                self.assertTrue((root / public_url.lstrip('/')).is_file(), public_url)

            manifest = json.loads((root / 'assets' / 'manifest.json').read_text(encoding='utf-8'))
            for icon in manifest['icons']:
                self.assertRegex(icon['src'], r'^/assets/immutable/icon-[0-9]+\.[0-9a-f]{12}\.png$')
