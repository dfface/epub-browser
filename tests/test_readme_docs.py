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
                "重复的本地账户",
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
                "AI-native reading, grounded in the text",
                "Private reading insights",
                "docs/readme/assets/ai-native-reading.png",
                "docs/readme/assets/reading-insights.png",
            ),
            Path("docs/readme/README.zh-CN.md"): (
                "贴着原文的 AI 原生阅读",
                "只属于你的阅读洞察",
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
                    "Vanilla JavaScript",
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
                    "Vanilla JavaScript",
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

        compact_readmes = [
            path
            for path in sorted(Path("docs/readme").glob("README.*.md"))
            if path.name not in {"README.zh-CN.md"}
        ]
        for path in compact_readmes:
            lines = path.read_text(encoding="utf-8").splitlines()
            with self.subTest(path=path):
                self.assertEqual(4, sum(line.startswith("## ") for line in lines))
                self.assertGreaterEqual(
                    sum(line.startswith("### ") for line in lines),
                    7,
                )

    def test_documentation_hub_links_the_stable_entry_points(self):
        hub = Path("docs/README.md").read_text(encoding="utf-8")
        for target in (
            "../README.md",
            "readme/README.zh-CN.md",
            "ai-native-reading.md",
            "third-party-ai-renderers.md",
            "migration-v2.md",
            "releases/v2.9.0.md",
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
                "cannot write an ID into its bytes",
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
                "outline 标题作为 marker",
                "--book-id-storage embedded",
                "必须回退到相邻的 sidecar",
                "不能把 ID 写进 PDF 字节",
                "没有可用文本层时",
                "跨页选择可以继续",
                "完整且 逐字节一致的源文件",
                "只接受 Session",
                "有界的单一 Range 响应",
                "不接受 PAT，也不出现在",
                "hydrate 并验证锁定的第三方资源",
                "本地带 hash 的 PDF.js module",
                "绝不从 CDN 获取",
                "使用锁定的 GLightbox",
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
