import json
import re
import subprocess
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
    def test_every_generated_vendor_file_is_locked_and_untracked(self):
        lock = json.loads(
            Path("third_party/assets.lock.json").read_text(encoding="utf-8")
        )
        locked = {
            item["target"]
            for package in lock["packages"]
            for item in (
                package["files"] + package.get("supplemental_license_files", [])
            )
        }
        generated = {
            path.relative_to("epub_browser/assets/vendor").as_posix()
            for path in Path("epub_browser/assets/vendor").rglob("*")
            if path.is_file()
        }
        tracked = subprocess.check_output(
            ["git", "ls-files", "epub_browser/assets/vendor"], text=True
        ).splitlines()

        self.assertEqual(generated, locked)
        self.assertEqual(tracked, [])
        self.assertIn("pdfjs/build/pdf.mjs", locked)

    def test_production_lock_is_release_auditable_and_uses_mit_lightbox(self):
        lock = json.loads(
            Path("third_party/assets.lock.json").read_text(encoding="utf-8")
        )

        self.assertEqual(lock["schema"], 2)
        identities = {
            (package["name"], package["version"])
            for package in lock["packages"]
        }
        self.assertIn(("glightbox", "3.3.1"), identities)
        self.assertNotIn(("@fancyapps/ui", "6.1.14"), identities)
        locked_targets = {
            item["target"]
            for package in lock["packages"]
            for item in (
                package["files"] + package.get("supplemental_license_files", [])
            )
        }
        for package in lock["packages"]:
            self.assertRegex(package["upstream"], r"^https://")
            self.assertTrue(package["copyright"])
            self.assertTrue(package["runtime_files"])
            self.assertLessEqual(set(package["runtime_files"]), locked_targets)

    def test_pdfjs_main_and_worker_are_modern_and_version_matched(self):
        lock = json.loads(
            Path("third_party/assets.lock.json").read_text(encoding="utf-8")
        )
        pdfjs = next(
            package for package in lock["packages"] if package["name"] == "pdfjs-dist"
        )
        sources = {item["source"] for item in pdfjs["files"]}

        self.assertIn("package/build/pdf.mjs", sources)
        self.assertIn("package/build/pdf.worker.mjs", sources)
        self.assertFalse(any("/legacy/" in source for source in sources))
        main = Path("epub_browser/assets/vendor/pdfjs/build/pdf.mjs").read_text(
            encoding="utf-8"
        )
        worker = Path(
            "epub_browser/assets/vendor/pdfjs/build/pdf.worker.mjs"
        ).read_text(encoding="utf-8")
        version_pattern = re.compile(r"pdfjsVersion\s*=\s*([0-9.]+)")
        self.assertEqual(version_pattern.search(main).group(1), pdfjs["version"])
        self.assertEqual(version_pattern.search(worker).group(1), pdfjs["version"])
        self.assertNotIn("core-js", main)
        self.assertNotIn("core-js", worker)

    def test_bundled_component_inventory_is_exact_and_not_top_level_only(self):
        lock = json.loads(
            Path("third_party/assets.lock.json").read_text(encoding="utf-8")
        )
        mermaid_components = {
            (package["name"], package["version"])
            for package in lock["packages"]
            if "mermaid/mermaid.min.js" in package["runtime_files"]
        }
        expected_mermaid = {
            ("@braintree/sanitize-url", "7.1.1"),
            ("@chevrotain/cst-dts-gen", "11.0.3"),
            ("@chevrotain/gast", "11.0.3"),
            ("@chevrotain/regexp-to-ast", "11.0.3"),
            ("@chevrotain/utils", "11.0.3"),
            ("@iconify/utils", "3.0.2"),
            ("@mermaid-js/parser", "0.6.2"),
            ("chevrotain", "11.0.3"),
            ("chevrotain-allstar", "0.3.1"),
            ("cose-base", "1.0.3"),
            ("cose-base", "2.2.0"),
            ("cytoscape", "3.33.1"),
            ("cytoscape-cose-bilkent", "4.1.0"),
            ("cytoscape-fcose", "2.2.0"),
            ("d3", "7.9.0"),
            ("d3-array", "2.12.1"),
            ("d3-array", "3.2.4"),
            ("d3-axis", "3.0.0"),
            ("d3-brush", "3.0.0"),
            ("d3-chord", "3.0.1"),
            ("d3-color", "3.1.0"),
            ("d3-contour", "4.0.2"),
            ("d3-delaunay", "6.0.4"),
            ("d3-dispatch", "3.0.1"),
            ("d3-drag", "3.0.0"),
            ("d3-dsv", "3.0.1"),
            ("d3-ease", "3.0.1"),
            ("d3-fetch", "3.0.1"),
            ("d3-force", "3.0.0"),
            ("d3-format", "3.1.0"),
            ("d3-geo", "3.1.1"),
            ("d3-hierarchy", "3.1.2"),
            ("d3-interpolate", "3.0.1"),
            ("d3-path", "1.0.9"),
            ("d3-path", "3.1.0"),
            ("d3-polygon", "3.0.1"),
            ("d3-quadtree", "3.0.1"),
            ("d3-random", "3.0.1"),
            ("d3-sankey", "0.12.3"),
            ("d3-scale", "4.0.2"),
            ("d3-scale-chromatic", "3.1.0"),
            ("d3-selection", "3.0.0"),
            ("d3-shape", "1.3.7"),
            ("d3-shape", "3.2.0"),
            ("d3-time", "3.1.0"),
            ("d3-time-format", "4.1.0"),
            ("d3-timer", "3.0.1"),
            ("d3-transition", "3.0.1"),
            ("d3-zoom", "3.0.0"),
            ("dagre-d3-es", "7.0.11"),
            ("dayjs", "1.11.18"),
            ("dompurify", "3.2.6"),
            ("esbuild", "0.25.9"),
            ("internmap", "2.0.3"),
            ("js-yaml", "4.1.0"),
            ("katex", "0.16.22"),
            ("khroma", "2.1.0"),
            ("langium", "3.3.1"),
            ("layout-base", "1.0.2"),
            ("layout-base", "2.0.1"),
            ("lodash-es", "4.17.21"),
            ("marked", "16.3.0"),
            ("mermaid", "11.12.0"),
            ("path-browserify", "1.0.1"),
            ("roughjs", "4.6.6"),
            ("stylis", "4.3.6"),
            ("ts-dedent", "2.2.0"),
            ("uuid", "11.1.0"),
            ("vscode-jsonrpc", "8.2.0"),
            ("vscode-languageserver-textdocument", "1.0.12"),
            ("vscode-languageserver-types", "3.17.5"),
            ("vscode-uri", "3.0.8"),
            ("webpack", "5.88.2"),
        }
        self.assertEqual(mermaid_components, expected_mermaid)

        pdf_components = {
            (package["name"], package["version"])
            for package in lock["packages"]
            if "pdfjs/build/pdf.worker.mjs" in package["runtime_files"]
        }
        self.assertEqual(
            pdf_components,
            {
                ("emscripten", "5.0.6"),
                ("google-brotli", "1.2.0"),
                (
                    "mozilla-pdfjs-jbig2-wrapper",
                    "1e945e7552561c9b45e6d2c7d1a359ea82afc5b7",
                ),
                (
                    "mozilla-pdfjs-openjpeg-wrapper",
                    "8bb19dc1aeecb104ce2ed3493d41fe131fc681e0",
                ),
                (
                    "mozilla-pdfjs-qcms-wrapper",
                    "2ae4ee72334782928210ba4050e3e77d9b2d35be",
                ),
                ("openjpeg", "2.5.4"),
                ("pdfium-jbig2", "0455e822ded1a5537d826703988e986a33d2d4a1"),
                ("pdfjs-dist", "6.2.108"),
                ("qcms", "0.3.0"),
                ("wasm-bindgen", "0.2.100"),
                ("webpack", "5.109.0"),
            },
        )

    def test_third_party_notices_cover_every_locked_package_and_component(self):
        lock = json.loads(
            Path("third_party/assets.lock.json").read_text(encoding="utf-8")
        )
        notices = Path("THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")

        for package in lock["packages"]:
            source_to_target = {
                item["source"]: item["target"] for item in package["files"]
            }
            installed_licenses = [
                source_to_target[source] for source in package["license"]["files"]
            ] + [
                item["target"]
                for item in package.get("supplemental_license_files", [])
            ]
            row_prefix = "| `{}` | `{}` | `{}` | `{}` | `{}` |".format(
                package["name"],
                package["version"],
                package["upstream"],
                package["source"]["url"],
                package["license"]["spdx"],
            )
            with self.subTest(package=(package["name"], package["version"])):
                matching_rows = [
                    row for row in notices.splitlines() if row.startswith(row_prefix)
                ]
                self.assertEqual(len(matching_rows), 1)
                row = matching_rows[0]
                for value in (
                    *package["copyright"],
                    *package["runtime_files"],
                    *installed_licenses,
                ):
                    self.assertIn(value, row)

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
