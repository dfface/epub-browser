import re
import unittest
from pathlib import Path


class ReadmeDocumentationTests(unittest.TestCase):
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
