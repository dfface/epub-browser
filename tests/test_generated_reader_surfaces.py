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

    def test_library_does_not_offer_a_manual_cache_update_button(self):
        script = Path("epub_browser/assets/library.js").read_text(encoding="utf-8")

        self.assertNotIn('update-cache-btn', script)
        self.assertNotIn('Updating cache...', script)

    def test_book_page_offers_a_progress_aware_continue_reading_action(self):
        html = self._book_html()
        script = Path("epub_browser/assets/book.js").read_text(encoding="utf-8")

        self.assertRegex(html, r'id=(?:["\'])?continueReadingBtn')
        self.assertRegex(html, r'id=(?:["\'])?continueReadingBtnText')
        self.assertIn("updateContinueReadingButton(book_hash);", script)
        self.assertIn("document.getElementById(readKey)", script)
        self.assertIn("chapterLinks[i].id.split('#')[0] === readKey", script)
        self.assertIn("Continue reading", script)
        self.assertIn("Start reading", script)

    def test_book_toc_marks_server_synced_reading_progress_with_the_username(self):
        script = Path("epub_browser/assets/book.js").read_text(encoding="utf-8")
        css = Path("epub_browser/assets/book.css").read_text(encoding="utf-8")

        self.assertIn("markReadingChapter(readKey, getProgressUsername())", script)
        self.assertIn("chapter-sync-tag", script)
        self.assertIn("'Cloud sync · ' + username", script)
        self.assertIn(".chapter-sync-tag", css)

    def test_reader_includes_chapter_sync_and_progress_bar_controls(self):
        book_html = self._book_html()
        chapter_html = self._chapter_html()
        css = Path("epub_browser/assets/chapter.css").read_text(encoding="utf-8")

        self.assertRegex(book_html, r'/assets/immutable/reading-progress\.[0-9a-f]{12}\.js')
        self.assertRegex(chapter_html, r'/assets/immutable/reading-progress\.[0-9a-f]{12}\.js')
        self.assertIn('id="showReadingProgressBarToggle"', chapter_html)
        self.assertIn('.reading-progress-container.is-progress-bar-hidden', css)

    def test_book_and_chapter_return_to_the_library_without_redirect_or_unused_fragment(self):
        for html in (self._book_html(), self._chapter_html()):
            self.assertNotIn('/index.html#', html)
            self.assertNotIn('/#AwU__ARVZEOf9_LKuztYxQ', html)
            self.assertRegex(html, r'href=(?:["\'])?/(?:["\' >])')

    def test_pages_link_one_shared_breadcrumb_stylesheet(self):
        for html in (self._library_html(), self._chapter_html()):
            self.assertRegex(html, r'/assets/immutable/breadcrumb\.[0-9a-f]{12}\.css')
        css = Path("epub_browser/assets/breadcrumb.css").read_text(encoding="utf-8")
        self.assertIn("width: min(100%, 1000px)", css)
        self.assertIn("padding-top: 12px", css)
        self.assertIn("margin: 12px 0", css)
        self.assertIn("padding: 15px 20px", css)
        self.assertIn("align-self: center;", css)

    def test_mobile_reader_breadcrumb_uses_the_shared_compact_layout(self):
        css = Path("epub_browser/assets/breadcrumb.css").read_text(encoding="utf-8")
        book_html = self._book_html()
        chapter_html = self._chapter_html()

        self.assertIn(".breadcrumb-library-label", css)
        self.assertIn("@media (max-width: 768px)", css)
        self.assertIn("flex-wrap: nowrap;", css)
        self.assertIn("min-width: 0;", css)
        self.assertIn("text-overflow: ellipsis;", css)
        self.assertIn(".breadcrumb a:not(:first-of-type)", css)
        self.assertIn("max-width: 45%;", css)
        self.assertIn("padding: 0;", css)
        self.assertIn("margin: 0;", css)
        self.assertIn(".library-breadcrumb", css)
        for html in (book_html, chapter_html):
            self.assertRegex(html, r'aria-label=(?:["\'])?Library')
            self.assertRegex(html, r'class=(?:["\'])?breadcrumb-library-label')

    def test_reader_chrome_uses_one_default_font_stack(self):
        for path in ("library.css", "book.css", "chapter.css"):
            css = Path("epub_browser/assets", path).read_text(encoding="utf-8")
            self.assertIn("font-family: var(--font-family, system-ui, -apple-system, sans-serif)", css)
        for path in ("library.js", "book.js"):
            script = Path("epub_browser/assets", path).read_text(encoding="utf-8")
            self.assertIn('fontFamily === "ebook-default"', script)
            self.assertIn("document.body.style.fontFamily = '';", script)

    def test_default_reader_assets_use_immutable_content_addressed_urls(self):
        library_html = self._library_html()
        book_html = self._book_html()
        self.assertRegex(library_html, r'/assets/immutable/library\.[0-9a-f]{12}\.css')
        self.assertRegex(library_html, r'/assets/immutable/library\.[0-9a-f]{12}\.js')
        self.assertRegex(book_html, r'/assets/immutable/book\.[0-9a-f]{12}\.css')
        self.assertRegex(book_html, r'/assets/immutable/book\.[0-9a-f]{12}\.js')
        self.assertNotIn('?v=', library_html + book_html)

    def test_pagination_mode_does_not_access_the_removed_custom_css_panel(self):
        script = Path("epub_browser/assets/chapter.js").read_text(encoding="utf-8")

        self.assertNotIn('document.querySelector(".custom-css-panel").style', script)

    def test_chapter_script_uses_an_immutable_content_addressed_url(self):
        self.assertRegex(self._chapter_html(), r'/assets/immutable/chapter\.[0-9a-f]{12}\.js')

    def test_initial_font_size_update_uses_content_loading_only(self):
        script = Path("epub_browser/assets/chapter.js").read_text(encoding="utf-8")

        self.assertIn('showLoading();\n        requestAnimationFrame(function()', script)
        self.assertIn('updateFontSize(s);', script)
        self.assertNotIn('applyFontSizeWithLoading', script)

    def test_content_loading_uses_the_active_theme_surface(self):
        css = Path("epub_browser/assets/loading.css").read_text(encoding="utf-8")

        self.assertIn('color-mix(in srgb, var(--card-bg) 72%, transparent)', css)
        self.assertNotIn('rgba(15, 23, 42, 0.32)', css)

    def test_content_loading_is_scoped_to_the_reading_content_container(self):
        css = Path("epub_browser/assets/chapter.css").read_text(encoding="utf-8")

        container_rules = css[css.index('.eb-content-container {'):css.index('}', css.index('.eb-content-container {'))]
        self.assertIn('position: relative;', container_rules)
        self.assertRegex(self._chapter_html(), r'/assets/immutable/chapter\.[0-9a-f]{12}\.css')

    def test_pagination_uses_a_chapter_top_bar_not_a_breadcrumb_container(self):
        html = self._chapter_html()

        self.assertIn('class="chapter-top-bar"', html)
        self.assertNotIn('class="breadcrumb-container"', html)

    def test_chapter_breadcrumb_and_reading_container_share_a_width_rule(self):
        css = Path("epub_browser/assets/chapter.css").read_text(encoding="utf-8")

        self.assertIn(".container, .chapter-top-bar", css)
        self.assertIn("width: 80%;", css)
        self.assertIn(".chapter-top-bar { padding-top: 12px; }", css)
        self.assertIn("body:not(.pagination-mode) .chapter-top-bar", css)
        self.assertIn("width: 100%;", css)

    def test_chapter_footer_uses_a_divider_instead_of_a_header_surface(self):
        css = Path("epub_browser/assets/chapter.css").read_text(encoding="utf-8")
        footer_rules = css[css.index(".eb-footer {"):css.index("}", css.index(".eb-footer {"))]

        self.assertIn("border-top: 1px solid var(--footer-border);", footer_rules)
        self.assertNotIn("background: var(--header-bg);", footer_rules)

    def test_chapter_content_has_desktop_breathing_room_below_the_breadcrumb(self):
        css = Path("epub_browser/assets/chapter.css").read_text(encoding="utf-8")
        content_rules = css[css.index(".eb-content-container {"):css.index("}", css.index(".eb-content-container {"))]

        self.assertIn("margin-top: 18px;", content_rules)
        self.assertIn(".navigation, .custom-css-panel, .eb-content-container", css)

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

    def _book_html(self):
        with tempfile.TemporaryDirectory() as directory:
            processor = EPUBProcessor("book.epub", directory)
            processor.book_title = "A Book"
            Path(processor.web_dir).mkdir(parents=True)
            processor.create_index_page()
            return Path(processor.web_dir, "index.html").read_text(encoding="utf-8")

    def test_library_places_its_summary_inside_the_current_location_breadcrumb(self):
        html = self._library_html()

        self.assertRegex(html, r'<nav\b(?=[^>]*\bclass=(?:["\'])?breadcrumb(?:["\'])?)(?=[^>]*\baria-label=(?:["\'])?Breadcrumb(?:["\'])?)[^>]*>')
        self.assertRegex(html, r'<span\b(?=[^>]*\bclass=(?:["\'])?breadcrumb-current(?:["\'])?)(?=[^>]*\baria-current=(?:["\'])?page(?:["\'])?)[^>]*>.*Library.*</span>')
        breadcrumb = html[html.index('<nav'):html.index('</nav>')]
        self.assertRegex(breadcrumb, r'/assets/immutable/logo-mark-color\.[0-9a-f]{12}\.png')
        self.assertIn('breadcrumb-brand-mark', breadcrumb)
        self.assertRegex(breadcrumb, r'\bclass=(?:["\'])?library-meta(?:["\'])?')
        self.assertRegex(breadcrumb, r'\bid=(?:["\'])?loginCard(?:["\'])?')
        self.assertNotIn('library-title', breadcrumb)
        self.assertNotIn('library-info', html)

    def test_chapter_puts_custom_css_in_the_reading_settings_tab(self):
        html = self._chapter_html()

        reading_tab_start = html.index('id="reading-tab"')
        editor_start = html.index('id="customCssInput"')
        self.assertGreater(editor_start, reading_tab_start)
        self.assertIn('Custom styles', html)
        self.assertIn('Optional', html)
        self.assertNotIn('Reading appearance (advanced)', html)
        self.assertNotIn('id="cssPanelToggle"', html)

    def test_library_and_chapter_link_the_shared_loading_stylesheet(self):
        self.assertRegex(self._library_html(), r'/assets/immutable/loading\.[0-9a-f]{12}\.css')
        self.assertRegex(self._chapter_html(), r'/assets/immutable/loading\.[0-9a-f]{12}\.css')
