import tempfile
import unittest
from pathlib import Path

from epub_browser.library import EPUBLibrary
from epub_browser.processor import EPUBProcessor


class GeneratedReaderSurfaceTests(unittest.TestCase):
    def test_annotation_menu_includes_a_text_only_copy_action(self):
        script = Path("epub_browser/assets/annotation.js").read_text(encoding="utf-8")

        self.assertIn('annotation-btn-copy', script)
        self.assertIn('copyText(source.text)', script)

    def test_breadcrumb_styles_have_shared_medium_padding(self):
        for path in ("library.css", "book.css", "chapter.css"):
            css = Path("epub_browser/assets", path).read_text(encoding="utf-8")
            self.assertIn("padding: 28px 24px", css)

    def test_generated_pages_do_not_include_fullscreen_loading_overlay(self):
        for html in (self._library_html(), self._chapter_html()):
            self.assertNotIn('id="loadingOverlay"', html)
        self.assertIn('id="contentLoading"', self._chapter_html())

    def _library_html(self):
        with tempfile.TemporaryDirectory() as directory:
            library = EPUBLibrary(directory)
            library.create_library_home()
            return Path(directory, "index.html").read_text(encoding="utf-8")

    def _chapter_html(self):
        with tempfile.TemporaryDirectory() as directory:
            processor = EPUBProcessor("book.epub", directory)
            processor.book_title = "A Book"
            processor.chapters = [{"title": "One"}]
            return processor.create_chapter_template("<p>Text</p>", "", 0, "One")

    def test_library_has_a_current_location_breadcrumb_before_library_info(self):
        html = self._library_html()

        self.assertRegex(html, r'<nav\b(?=[^>]*\bclass=(?:["\'])?breadcrumb(?:["\'])?)(?=[^>]*\baria-label=(?:["\'])?Breadcrumb(?:["\'])?)[^>]*>')
        self.assertRegex(html, r'<span\b(?=[^>]*\bclass=(?:["\'])?breadcrumb-current(?:["\'])?)(?=[^>]*\baria-current=(?:["\'])?page(?:["\'])?)[^>]*>.*Library.*</span>')
        self.assertLess(html.index("aria-label"), html.index("library-info"))
        breadcrumb = html[html.index('<nav'):html.index('</nav>')]
        self.assertIn('fa-home', breadcrumb)

    def test_chapter_puts_custom_css_in_the_reading_settings_tab(self):
        html = self._chapter_html()

        reading_tab_start = html.index('id="reading-tab"')
        editor_start = html.index('id="customCssInput"')
        self.assertGreater(editor_start, reading_tab_start)
        self.assertIn('Reading appearance (advanced)', html)
        self.assertNotIn('id="cssPanelToggle"', html)

    def test_library_and_chapter_link_the_shared_loading_stylesheet(self):
        self.assertIn("/assets/loading.css", self._library_html())
        self.assertIn("/assets/loading.css", self._chapter_html())
