import unittest
from pathlib import Path


class ReadmeDocumentationTests(unittest.TestCase):
    def test_readmes_document_pdf_chapter_mapping(self):
        for path in (Path("README.md"), Path("README.zh-CN.md")):
            text = path.read_text(encoding="utf-8")
            self.assertIn("chapter_0.html", text)
            self.assertIn("PDF", text)


if __name__ == "__main__":
    unittest.main()
