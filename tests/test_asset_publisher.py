import json
import re
import tempfile
import unittest
from pathlib import Path

from epub_browser.asset_publisher import (
    AssetPublisher,
    SERVER_ONLY_ASSET_PATHS,
    SERVER_ONLY_ASSET_PREFIXES,
    WEB_MANIFEST_LOCALIZATIONS,
)
from epub_browser.asset_publisher import rewrite_asset_urls
from epub_browser.locales import SUPPORTED_LOCALES
from epub_browser.urls import SiteURLs


class AssetPublisherTests(unittest.TestCase):
    def test_publish_uses_base_path_without_writing_the_prefix_to_disk(self):
        with tempfile.TemporaryDirectory() as source, tempfile.TemporaryDirectory() as output:
            self._write_source_assets(source)

            published = AssetPublisher(
                source,
                output,
                SiteURLs("/reader/"),
            ).publish()

            public_url = published.url_for("app.js")
            self.assertRegex(
                public_url,
                r"^/reader/assets/immutable/app\.[0-9a-f]{12}\.js$",
            )
            filename = public_url.rsplit("/", 1)[1]
            self.assertTrue(Path(output, "assets", "immutable", filename).is_file())
            self.assertFalse(Path(output, "reader").exists())

    def test_non_root_manifests_and_worker_use_the_base_path(self):
        with tempfile.TemporaryDirectory() as source, tempfile.TemporaryDirectory() as output:
            self._write_source_assets(source)
            manifest_path = Path(source, "manifest.json")
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest.update({"start_url": "/index.html", "scope": "/"})
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            AssetPublisher(source, output, SiteURLs("/reader/")).publish()

            published_manifest = json.loads(
                Path(output, "assets", "manifest.json").read_text(encoding="utf-8")
            )
            worker = Path(output, "sw.js").read_text(encoding="utf-8")
            self.assertEqual(published_manifest["start_url"], "/reader/index.html")
            self.assertEqual(published_manifest["scope"], "/reader/")
            self.assertRegex(
                published_manifest["icons"][0]["src"],
                r"^/reader/assets/immutable/icon-192\.[0-9a-f]{12}\.png$",
            )
            self.assertIn(json.dumps("/reader/index.html"), worker)
            self.assertIn(json.dumps("/reader/assets/manifest.json"), worker)

    def test_publish_writes_content_addressed_assets_and_a_lookup_manifest(self):
        with tempfile.TemporaryDirectory() as source, tempfile.TemporaryDirectory() as output:
            self._write_source_assets(source)

            published = AssetPublisher(source, output).publish()

            public_url = published.url_for("app.js")
            self.assertRegex(public_url, r"^/assets/immutable/app\.[0-9a-f]{12}\.js$")
            self.assertTrue(Path(output, public_url.lstrip("/")).is_file())
            manifest = json.loads(Path(output, "assets", "asset-manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest, published.assets)
            self.assertEqual(manifest["app.js"], public_url)

    def test_publish_changes_only_the_url_for_changed_content(self):
        with tempfile.TemporaryDirectory() as source, tempfile.TemporaryDirectory() as output:
            self._write_source_assets(source)
            first = AssetPublisher(source, output).publish()

            Path(source, "app.js").write_text("console.log('v2')", encoding="utf-8")
            second = AssetPublisher(source, output).publish()

            self.assertNotEqual(first.url_for("app.js"), second.url_for("app.js"))
            self.assertEqual(first.url_for("icon-192.png"), second.url_for("icon-192.png"))

    def test_publish_renders_stable_service_worker_with_release_precache(self):
        with tempfile.TemporaryDirectory() as source, tempfile.TemporaryDirectory() as output:
            self._write_source_assets(source)

            published = AssetPublisher(source, output).publish()

            worker = Path(output, "sw.js").read_text(encoding="utf-8")
            self.assertNotIn("__EPUB_BROWSER_RELEASE_ID__", worker)
            self.assertNotIn("__EPUB_BROWSER_PRECACHE_URLS__", worker)
            self.assertRegex(worker, r"epub-browser-[0-9a-f]{12}")
            self.assertIn(json.dumps(published.url_for("app.js")), worker)
            self.assertNotIn("/assets/app.js", worker)
            for manifest_path in (
                "/assets/manifest.json",
                *(f"/assets/manifest.{locale}.json" for locale in SUPPORTED_LOCALES),
            ):
                self.assertIn(json.dumps(manifest_path), worker)

    def test_publish_writes_localized_stable_web_manifests(self):
        with tempfile.TemporaryDirectory() as source, tempfile.TemporaryDirectory() as output:
            self._write_source_assets(source)

            AssetPublisher(source, output).publish()

            english = json.loads(Path(output, "assets", "manifest.en.json").read_text(encoding="utf-8"))
            chinese = json.loads(Path(output, "assets", "manifest.zh-CN.json").read_text(encoding="utf-8"))
            traditional = json.loads(Path(output, "assets", "manifest.zh-TW.json").read_text(encoding="utf-8"))
            korean = json.loads(Path(output, "assets", "manifest.ko.json").read_text(encoding="utf-8"))
            japanese = json.loads(Path(output, "assets", "manifest.ja.json").read_text(encoding="utf-8"))
            self.assertEqual(english["lang"], "en")
            self.assertEqual(chinese["lang"], "zh-CN")
            self.assertEqual(chinese["description"], "私人 EPUB 阅读器与静态站点生成器")
            self.assertEqual(traditional["lang"], "zh-TW")
            self.assertEqual(traditional["description"], "私人 EPUB 閱讀器與靜態網站產生器")
            self.assertEqual(korean["lang"], "ko")
            self.assertEqual(korean["description"], "개인용 EPUB 리더 및 정적 사이트 생성기")
            self.assertEqual(japanese["lang"], "ja")
            self.assertEqual(japanese["description"], "個人用 EPUB リーダー兼静的サイトジェネレーター")
            for locale in SUPPORTED_LOCALES:
                localized = json.loads(Path(output, "assets", f"manifest.{locale}.json").read_text(encoding="utf-8"))
                self.assertEqual(localized["lang"], locale)
                if locale in WEB_MANIFEST_LOCALIZATIONS:
                    self.assertTrue(localized["description"])
            self.assertRegex(english["icons"][0]["src"], r"^/assets/immutable/icon-192\.[0-9a-f]{12}\.png$")

    def test_real_worker_only_uses_cache_first_for_content_addressed_assets(self):
        with tempfile.TemporaryDirectory() as output:
            source = Path("epub_browser/assets")
            worker = Path(output, "sw.js")
            AssetPublisher(source, output).publish()
            contents = worker.read_text(encoding="utf-8")

            self.assertIn('function isPrecachedAsset(request)', contents)
            self.assertIn('async function networkFirst(request, fallbackUrl)', contents)
            self.assertNotIn('function shouldCache(', contents)
            self.assertNotIn('STATIC_ASSETS', contents)

    def test_publish_rewrites_css_local_asset_urls_to_their_immutable_urls(self):
        with tempfile.TemporaryDirectory() as source, tempfile.TemporaryDirectory() as output:
            self._write_source_assets(source)
            Path(source, 'font.woff2').write_bytes(b'font')
            Path(source, 'app.css').write_text("@font-face { src: url(./font.woff2); }", encoding='utf-8')

            published = AssetPublisher(source, output).publish()
            stylesheet = Path(output, published.url_for('app.css').lstrip('/')).read_text(encoding='utf-8')

            self.assertIn('url(' + json.dumps(published.url_for('font.woff2')) + ')', stylesheet)

    def test_rewrite_html_supports_nested_local_vendor_assets(self):
        with tempfile.TemporaryDirectory() as source, tempfile.TemporaryDirectory() as output:
            self._write_source_assets(source)
            vendor = Path(source, "vendor", "example")
            vendor.mkdir(parents=True)
            (vendor / "renderer.js").write_text("window.renderer=true", encoding="utf-8")
            published = AssetPublisher(source, output).publish()

            rewritten = rewrite_asset_urls(
                '<script src="/assets/vendor/example/renderer.js"></script>', published
            )

            self.assertIn(published.url_for("vendor/example/renderer.js"), rewritten)

    def test_excluded_assets_are_not_written_or_listed(self):
        self.assertIn('account.css', SERVER_ONLY_ASSET_PATHS)
        self.assertIn('api-docs.css', SERVER_ONLY_ASSET_PATHS)
        self.assertIn('api-docs.js', SERVER_ONLY_ASSET_PATHS)
        self.assertIn('auth.js', SERVER_ONLY_ASSET_PATHS)
        self.assertIn('book-reviews.css', SERVER_ONLY_ASSET_PATHS)
        self.assertIn('book-reviews.js', SERVER_ONLY_ASSET_PATHS)
        self.assertIn('reading-sessions.js', SERVER_ONLY_ASSET_PATHS)
        self.assertIn('reading-insights.css', SERVER_ONLY_ASSET_PATHS)
        self.assertIn('reading-insights.js', SERVER_ONLY_ASSET_PATHS)
        with tempfile.TemporaryDirectory() as output:
            published = AssetPublisher(
                Path("epub_browser/assets"),
                output,
                excluded_paths=SERVER_ONLY_ASSET_PATHS,
                excluded_prefixes=SERVER_ONLY_ASSET_PREFIXES,
            ).publish()

            for logical_path in SERVER_ONLY_ASSET_PATHS:
                self.assertNotIn(logical_path, published.assets)
                self.assertFalse((Path(output) / "assets" / "immutable" / logical_path).exists())
            self.assertFalse(any(
                logical_path.startswith(prefix)
                for logical_path in published.assets
                for prefix in SERVER_ONLY_ASSET_PREFIXES
            ))

    def _write_source_assets(self, source):
        root = Path(source)
        (root / "app.js").write_text("console.log('v1')", encoding="utf-8")
        (root / "icon-192.png").write_bytes(b"icon")
        (root / "manifest.json").write_text(
            json.dumps({"lang": "en", "icons": [{"src": "/assets/icon-192.png"}]}), encoding="utf-8"
        )
        (root / "manifest.zh-CN.json").write_text(
            json.dumps(
                {
                    "lang": "zh-CN",
                    "description": "私人 EPUB 阅读器与静态站点生成器",
                    "icons": [{"src": "/assets/icon-192.png"}],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        for locale, description in (
            ("zh-TW", "私人 EPUB 閱讀器與靜態網站產生器"),
            ("ko", "개인용 EPUB 리더 및 정적 사이트 생성기"),
            ("ja", "個人用 EPUB リーダー兼静的サイトジェネレーター"),
        ):
            (root / f"manifest.{locale}.json").write_text(
                json.dumps({
                    "lang": locale,
                    "description": description,
                    "icons": [{"src": "/assets/icon-192.png"}],
                }, ensure_ascii=False),
                encoding="utf-8",
            )
        (root / "sw.js").write_text(
            "const CACHE_NAME = 'epub-browser-__EPUB_BROWSER_RELEASE_ID__';\n"
            "const PRECACHE_URLS = __EPUB_BROWSER_PRECACHE_URLS__;\n",
            encoding="utf-8",
        )
