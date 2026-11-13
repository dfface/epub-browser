import re
import unittest
from pathlib import Path


class ReadmeDocumentationTests(unittest.TestCase):
    def test_primary_readmes_document_secure_generic_oidc_and_authelia_setup(self):
        required = (
            "OIDC",
            "/auth/oidc/callback",
            "Authorization Code",
            "S256",
            "(issuer, sub)",
            "Authelia",
        )
        localized = {
            Path("README.md"): (
                "local administrator",
                "passwordless member",
                "duplicate local accounts",
            ),
            Path("docs/readme/README.zh-CN.md"): (
                "本地管理员",
                "无密码成员",
                "本地账户",
            ),
        }
        for path, language_specific in localized.items():
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=path):
                for phrase in required + language_specific:
                    self.assertIn(phrase, text)

    def test_why_epub_browser_highlights_ai_native_reading_and_insights(self):
        assets = (
            Path("docs/readme/assets/ai-native-reading.png"),
            Path("docs/readme/assets/reading-insights.png"),
        )
        for asset in assets:
            with self.subTest(asset=asset):
                self.assertTrue(asset.is_file())
                self.assertGreater(asset.stat().st_size, 0)

        readmes = {
            Path("README.md"): (
                "evidence-linked explanations",
                "activity calendars",
                "docs/readme/assets/ai-native-reading.png",
                "docs/readme/assets/reading-insights.png",
            ),
            Path("docs/readme/README.zh-CN.md"): (
                "Ask AI",
                "活动日历",
                "assets/ai-native-reading.png",
                "assets/reading-insights.png",
            ),
        }
        for path, required in readmes.items():
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=path):
                for phrase in required:
                    self.assertIn(phrase, text)

        for path in sorted(Path("docs/readme").glob("README.*.md")):
            text = path.read_text(encoding="utf-8")
            with self.subTest(localized_assets=path):
                self.assertIn("assets/ai-native-reading.png", text)
                self.assertIn("assets/reading-insights.png", text)

    def test_readmes_document_the_technology_stack(self):
        for path in (Path("README.md"), Path("docs/readme/README.zh-CN.md")):
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=path):
                for technology in (
                    "VanillaJS",
                    "Starlette",
                    "Uvicorn",
                    "SQLite",
                    "PDF.js",
                    "pypdf",
                    "pypdfium2",
                    "Service Worker",
                ):
                    self.assertIn(technology, text)

        for path in sorted(Path("docs/readme").glob("README.*.md")):
            with self.subTest(path=path):
                self.assertIn(
                    "VanillaJS",
                    path.read_text(encoding="utf-8"),
                )

    def test_readme_information_architecture_stays_reader_focused(self):
        expected_top_level = {
            Path("README.md"): (
                "Contents",
                "Project overview",
                "Get started",
                "Formats and reading",
                "Deployment",
                "Reference and operations",
                "Development and license",
            ),
            Path("docs/readme/README.zh-CN.md"): (
                "目录",
                "项目概览",
                "开始使用",
                "格式与阅读体验",
                "部署",
                "参考与运维",
                "开发与许可证",
            ),
        }
        for path, expected in expected_top_level.items():
            headings = tuple(
                line[3:].strip()
                for line in path.read_text(encoding="utf-8").splitlines()
                if line.startswith("## ")
            )
            with self.subTest(path=path):
                self.assertEqual(expected, headings)

        reference_lines = Path("README.md").read_text(encoding="utf-8").splitlines()
        reference_headings = tuple(
            line[: len(line) - len(line.lstrip("#"))]
            for line in reference_lines
            if re.match(r"^#{1,6} ", line)
        )
        reference_fences = tuple(
            line for line in reference_lines if line.startswith("```")
        )
        reference_table_rows = sum(
            line.startswith("|") for line in reference_lines
        )
        reference_links = len(
            re.findall(r"\[[^]]*\]\([^)]+\)", "\n".join(reference_lines))
        )
        for path in sorted(Path("docs/readme").glob("README.*.md")):
            text = path.read_text(encoding="utf-8")
            lines = text.splitlines()
            headings = tuple(
                line[: len(line) - len(line.lstrip("#"))]
                for line in lines
                if re.match(r"^#{1,6} ", line)
            )
            with self.subTest(path=path):
                self.assertEqual(reference_headings, headings)
                self.assertEqual(
                    reference_fences,
                    tuple(line for line in lines if line.startswith("```")),
                )
                self.assertEqual(
                    reference_table_rows,
                    sum(line.startswith("|") for line in lines),
                )
                self.assertEqual(
                    reference_links,
                    len(re.findall(r"\[[^]]*\]\([^)]+\)", text)),
                )

    def test_documentation_hub_links_the_stable_entry_points(self):
        hub = Path("docs/README.md").read_text(encoding="utf-8")
        for target in (
            "../README.md",
            "readme/README.zh-CN.md",
            "ai-native-reading.md",
            "third-party-ai-renderers.md",
            "migration-v2.md",
            "releases/v2.9.4.md",
            "../AGENTS.md",
            "../CONTEXT.md",
        ):
            with self.subTest(target=target):
                self.assertIn(target, hub)

    def test_every_localized_readme_presents_pdf_as_a_first_class_format(self):
        localized_readmes = sorted(Path("docs/readme").glob("README.*.md"))
        self.assertEqual(16, len(localized_readmes))

        required = (
            "PDF",
            ".pdf",
            "chapter_0.html",
            "PDF.js",
            "`ssg`",
            "`server`",
            "v2.8.0-pdf-reader.png",
        )
        for path in localized_readmes:
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=path):
                for phrase in required:
                    self.assertIn(phrase, text)

    def test_every_readme_presents_oidc_as_a_server_capability(self):
        readmes = [Path("README.md")]
        readmes.extend(sorted(Path("docs/readme").glob("README.*.md")))
        self.assertEqual(17, len(readmes))

        for path in readmes:
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=path):
                self.assertIn("OIDC", text)

    def test_readmes_document_pdf_chapter_mapping(self):
        contracts = {
            Path("README.md"): (
                "| PDF concept | SSG | Server |",
                "Page N URL",
                "chapter_{N-1}.html",
                "chapter_0.html",
                "normalized TOC",
                "outline markers",
                "--book-id-storage embedded",
                "saves the same ID in an adjacent sidecar",
                "no usable text layer exists",
                "selection spanning pages",
                "complete, byte-identical source",
                "Session-only",
                "bounded single-range responses",
                "not available to PAT authentication",
                "not listed in the PAT/OpenAPI",
                "hydrate and verify the locked third-party assets",
                "local hashed PDF.js module",
                "never fetches them from a CDN",
                "GLightbox dependency",
                "Fancyapps/Fancybox is not a runtime",
            ),
            Path("docs/readme/README.zh-CN.md"): (
                "| PDF 概念 | SSG | Server |",
                "第 N 页 URL",
                "chapter_{N-1}.html",
                "chapter_0.html",
                "规范化目录",
                "大纲标记",
                "--book-id-storage embedded",
                "PDF 文档信息字典",
                "相邻的 sidecar",
                "没有可用文本层时",
                "跨页",
                "逐字节一致的源文件",
                "只接受 Session",
                "单区间 Range 响应",
                "不接受 PAT 认证",
                "也不列入 PAT/OpenAPI",
                "sync_vendor_assets.py",
                "PDF.js",
                "绝不从 CDN",
                "GLightbox",
                "Fancyapps/Fancybox 不是运行时依赖",
            ),
        }
        for path, required in contracts.items():
            text = re.sub(r"\s+", " ", path.read_text(encoding="utf-8"))
            with self.subTest(path=path):
                for phrase in required:
                    self.assertIn(phrase, text)


if __name__ == "__main__":
    unittest.main()
