import tempfile
import unittest
import subprocess
import sys
import re
from pathlib import Path

from epub_browser.library import EPUBLibrary
from epub_browser.processor import EPUBProcessor


class GeneratedReaderSurfaceTests(unittest.TestCase):
    def test_generated_footers_show_the_package_version_and_load_the_update_checker(self):
        package_version = subprocess.check_output(
            [sys.executable, "setup.py", "--version"],
            text=True,
        ).strip()

        for html in (self._library_html(), self._book_html(), self._chapter_html()):
            footer = html[html.index('<footer'):html.index('</footer>')]
            self.assertRegex(
                footer,
                rf'data-current-version=(?:["\'])?{package_version}(?:["\' >])',
            )
            self.assertIn(f'v{package_version}', footer)
            self.assertRegex(
                html,
                r'/assets/immutable/version-check\.[0-9a-f]{12}\.js',
            )

    def test_all_generated_pages_bootstrap_shared_i18n_before_ui_scripts(self):
        for html in (self._library_html(), self._book_html(), self._chapter_html()):
            self.assertRegex(html, r'/assets/immutable/i18n\.[0-9a-f]{12}\.js')
            self.assertIn('window.EpubBrowserI18n.init()', html)
            self.assertLess(html.index('window.EpubBrowserI18n.init()'), html.index('/assets/immutable/theme.'))
            self.assertNotIn('/assets/manifest.json', html)
            self.assertRegex(
                html,
                r'<noscript><link\b(?=[^>]*\brel=(?:"manifest"|manifest))(?=[^>]*\bhref=(?:"/assets/manifest\.en\.json"|/assets/manifest\.en\.json))[^>]*>',
            )

    def test_chapter_separates_ui_and_epub_content_languages(self):
        html = self._chapter_html()

        self.assertIn('<html lang="en"', html)
        self.assertRegex(html, r'<article[^>]+id="eb-content"[^>]+lang="en"')

    def test_book_and_chapter_keep_epub_language_off_the_ui_shell(self):
        with tempfile.TemporaryDirectory() as directory:
            processor = EPUBProcessor("book.epub", directory)
            processor.book_title = "A Book"
            processor.description = "Une description"
            processor.lang = "fr"
            processor.chapters = [{"title": "One"}]
            Path(processor.web_dir).mkdir(parents=True)
            processor.create_index_page()
            book_html = Path(processor.web_dir, "index.html").read_text(encoding="utf-8")
            chapter_html = processor.create_chapter_template("<p>Texte</p>", "", 0, "One")

        self.assertRegex(book_html, r'<html\s+lang=(?:"en"|en)(?:\s|>)')
        self.assertRegex(book_html, r'<div\b(?=[^>]*\bclass=(?:"book-info-desc"|book-info-desc))(?=[^>]*\blang=(?:"fr"|fr))[^>]*>')
        self.assertIn('<html lang="en"', chapter_html)
        self.assertRegex(chapter_html, r'<article[^>]+id="eb-content"[^>]+lang="fr"')

    def test_book_page_localizes_shell_but_marks_metadata_as_content(self):
        with tempfile.TemporaryDirectory() as directory:
            processor = EPUBProcessor('book.epub', directory)
            processor.book_title = 'A Book'
            processor.lang = 'fr'
            processor.description = '<p>Texte original</p>'
            Path(processor.web_dir).mkdir(parents=True)
            processor.create_index_page()
            html = Path(processor.web_dir, 'index.html').read_text(encoding='utf-8')

        self.assertRegex(html, r'data-i18n=(?:["\'])?book\.startReading')
        self.assertRegex(html, r'data-i18n=(?:["\'])?book\.tableOfContents')
        self.assertRegex(html, r'class=(?:["\'])?book-info-desc(?=[^>]*\blang=(?:["\'])?fr)')
        self.assertIn('A Book', html)
        self.assertIn('Texte original', html)

    def test_book_script_has_no_literal_user_notifications_or_confirmations(self):
        script = Path('epub_browser/assets/book.js').read_text(encoding='utf-8')

        self.assertNotRegex(script, r"showNotification\(\s*['\"]")
        self.assertNotRegex(script, r"confirm\(\s*['\"]")

    def test_chapter_script_routes_notifications_and_confirmations_through_i18n(self):
        script = Path('epub_browser/assets/chapter.js').read_text(encoding='utf-8')

        self.assertNotRegex(script, r"showNotification\(\s*['\"]")
        self.assertNotRegex(script, r"confirm\(\s*['\"]")
        self.assertIn("i18n.t('reader.loadingNextChapter'", script)
        self.assertIn("i18n.t('settings.saved'", script)
        self.assertIn("i18n.t('reader.chapterNumber'", script)
        self.assertIn("i18n.t('settings.continuousScrollTip'", script)

    def test_annotation_menu_includes_a_text_only_copy_action(self):
        script = Path("epub_browser/assets/annotation.js").read_text(encoding="utf-8")

        self.assertIn('annotation-btn-copy', script)
        self.assertIn('copyText(source.text)', script)

    def test_annotation_storage_exposes_reading_independent_read_apis(self):
        script = Path("epub_browser/assets/annotation.js").read_text(encoding="utf-8")

        self.assertIn('var AnnotationStorage = {', script)
        self.assertIn('init: function() {', script)
        self.assertIn('getAll: function() {', script)
        self.assertIn('getByBook: function(bookHash) {', script)
        self.assertIn('getStorageType: function() {', script)
        self.assertIn('isBackendAvailable: function() {', script)
        self.assertIn('global.AnnotationStorage = AnnotationStorage;', script)

    def test_chapter_can_focus_an_annotation_requested_by_query_parameter(self):
        script = Path("epub_browser/assets/chapter.js").read_text(encoding="utf-8")
        annotation_script = Path("epub_browser/assets/annotation.js").read_text(encoding="utf-8")
        css = Path("epub_browser/assets/annotation.css").read_text(encoding="utf-8")

        self.assertIn("requestedAnnotationId()", script)
        self.assertIn("focusAnnotation(annotationId)", script)
        self.assertIn("focusAnnotation: function(id)", annotation_script)
        self.assertIn("annotation-focus-active", css)

    def test_reader_annotation_edits_are_silent_when_successful(self):
        script = Path("epub_browser/assets/annotation.js").read_text(encoding="utf-8")

        self.assertNotIn("Utils.showNotification('Annotation added', 'success')", script)
        self.assertNotIn("Utils.showNotification('Annotation updated', 'success')", script)
        self.assertNotIn("Utils.showNotification('Annotation deleted', 'info')", script)
        self.assertIn("Utils.showNotification(tr('addFailed', { error: err.message }), 'error')", script)
        self.assertIn("Utils.showNotification(tr('updateFailed', { error: err.message }), 'error')", script)
        self.assertIn("Utils.showNotification(tr('deleteFailed', { error: err.message }), 'error')", script)

    def test_annotation_editor_routes_user_copy_through_i18n(self):
        script = Path('epub_browser/assets/annotation.js').read_text(encoding='utf-8')

        self.assertNotRegex(script, r"Utils\.showNotification\(\s*['\"]")
        self.assertNotRegex(script, r"confirm\(\s*['\"]")
        self.assertIn("i18n.t('annotations.noteOptional'", script)
        self.assertIn("i18n.t('annotations.storageLocationChanged'", script)

    def test_reader_does_not_append_an_emoji_to_noted_highlights(self):
        script = Path("epub_browser/assets/annotation.js").read_text(encoding="utf-8")
        css = Path("epub_browser/assets/annotation.css").read_text(encoding="utf-8")

        self.assertNotIn('has-note', script)
        self.assertNotIn("content: '📝'", css)

    def test_remove_from_shelf_uses_theme_safe_destructive_colors(self):
        css = Path("epub_browser/assets/book.css").read_text(encoding="utf-8")

        rules = css[css.index('#toggleShelfBtn.in-shelf {'):css.index('}', css.index('#toggleShelfBtn.in-shelf {'))]
        hover_rules = css[css.index('#toggleShelfBtn.in-shelf:hover {'):css.index('}', css.index('#toggleShelfBtn.in-shelf:hover {'))]
        self.assertIn('background: #c0392b;', rules)
        self.assertIn('color: #fff;', rules)
        self.assertIn('background: #a93226;', hover_rules)

    def test_cloud_annotations_retry_restoration_without_applying_a_stale_chapter_response(self):
        script = Path("epub_browser/assets/annotation.js").read_text(encoding="utf-8")

        self.assertIn('renderVersion: 0,', script)
        self.assertIn('var renderVersion = ++this.renderVersion;', script)
        self.assertIn('if (renderVersion !== self.renderVersion) return;', script)
        self.assertIn('return false;', script)
        self.assertIn('self.renderAll(true);', script)
        self.assertIn("Utils.showNotification(tr('restoreFailed'), 'error')", script)

    def test_library_does_not_offer_a_manual_cache_update_button(self):
        script = Path("epub_browser/assets/library.js").read_text(encoding="utf-8")

        self.assertNotIn('update-cache-btn', script)
        self.assertNotIn('Updating cache...', script)

    def test_book_page_offers_a_progress_aware_continue_reading_action(self):
        html = self._book_html()
        script = Path("epub_browser/assets/book.js").read_text(encoding="utf-8")
        styles = Path("epub_browser/assets/book.css").read_text(encoding="utf-8")

        self.assertRegex(html, r'id=(?:["\'])?continueReadingBtn')
        self.assertRegex(html, r'id=(?:["\'])?continueReadingBtnText')
        self.assertRegex(html, r'id=(?:["\'])?continueReadingMenuToggle')
        self.assertRegex(html, r'id=(?:["\'])?clearReadingProgressMenu')
        self.assertRegex(html, r'id=(?:["\'])?clearReadingProgressBtn')
        self.assertRegex(html, r'data-i18n-aria-label=(?:["\'])?book\.clearReadingProgress')
        self.assertRegex(html, r'data-i18n=(?:["\'])?book\.clear')
        self.assertIn("updateContinueReadingButton(book_hash);", script)
        self.assertIn("setClearReadingProgressAvailability(!!resumeChapter && !isKindleMode());", script)
        self.assertIn("clearButton.hidden = !available;", script)
        self.assertIn("clearMenuToggle.setAttribute('aria-expanded'", script)
        self.assertIn("window.confirm(bookT('book.clearReadingProgressConfirm'))", script)
        self.assertIn("'DELETE',", script)
        self.assertIn("true,\n                    true", script)
        self.assertIn("if (!result || result.error)", script)
        self.assertIn("book.clearReadingProgressFailed", script)
        clear_handler = script.index("window.confirm(bookT('book.clearReadingProgressConfirm'))")
        self.assertLess(
            script.index("window.EpubReadingProgress.request(", clear_handler),
            script.index("clearLocalProgress();", clear_handler),
        )
        self.assertNotIn("matchMedia", script)
        self.assertIn(".continue-reading-control.has-reading-progress:hover #continueReadingBtn", styles)
        self.assertIn("transform: none;", styles)
        self.assertIn(".continue-reading-control.has-reading-progress:focus-within", styles)
        self.assertIn(".continue-reading-menu-toggle[aria-expanded=\"true\"] i", styles)
        self.assertIn("@media (prefers-reduced-motion: reduce)", styles)
        self.assertIn("overflow: visible;", styles)
        self.assertIn("document.getElementById(readKey)", script)
        self.assertIn("chapterLinks[i].id.split('#')[0] === readKey", script)
        self.assertIn("bookT('book.continueReading')", script)
        self.assertIn("bookT('book.startReading')", script)

    def test_book_toc_marks_server_synced_reading_progress_with_the_reader_identity(self):
        script = Path("epub_browser/assets/book.js").read_text(encoding="utf-8")
        css = Path("epub_browser/assets/book.css").read_text(encoding="utf-8")

        self.assertIn("markReadingChapter(readKey, getProgressIdentity())", script)
        self.assertIn("return window.EpubReadingProgress.getUsername() || 'shared';", script)
        self.assertIn("markReadingChapter(currentChapter);", script)
        self.assertIn("if (username) {", script)
        self.assertIn("chapter-sync-tag", script)
        self.assertIn("chapter-title-with-sync", script)
        self.assertIn("bookT('book.cloudSyncUser'", script)
        self.assertIn("bookT('book.cloudSyncUserAria'", script)
        self.assertIn(".chapter-sync-tag", css)
        self.assertIn(".chapter-title-with-sync", css)
        self.assertIn(".chapter-page", css)
        self.assertIn("flex: 0 0 auto;", css)
        self.assertIn("margin-left: auto;", css)
        self.assertIn("padding-left: 16px;", css)
        self.assertIn("padding-left: 10px;", css)

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

    def test_book_toc_offers_a_direct_book_home_link(self):
        html = self._chapter_html()
        css = Path("epub_browser/assets/chapter.css").read_text(encoding="utf-8")

        self.assertRegex(html, r'<a\b[^>]*\bclass="toc-book-home"[^>]*\bhref="index\.html"')
        self.assertIn('aria-label="Open book home"', html)
        self.assertIn('id="bookHomeClose"', html)
        self.assertIn('.toc-header-actions', css)
        self.assertIn('min-width: 44px;', css)

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

    def test_locale_selector_exists_only_in_library_breadcrumb(self):
        library = self._library_html()
        self.assertEqual(len(re.findall(r'\bid=(?:["\'])?localeSelect(?:["\' >])', library)), 1)
        breadcrumb = library[
            library.index('class="breadcrumb library-breadcrumb"'):library.index('</nav>')
        ]
        self.assertRegex(breadcrumb, r'\bvalue=(?:["\'])?zh-CN(?:["\' >])')
        self.assertRegex(breadcrumb, r'\bvalue=(?:["\'])?en(?:["\' >])')
        self.assertNotRegex(self._book_html(), r'\bid=(?:["\'])?localeSelect(?:["\' >])')
        self.assertNotRegex(self._chapter_html(), r'\bid=(?:["\'])?localeSelect(?:["\' >])')
        self.assertRegex(library, r'localeSelect\.value=i18n\.getLocale\(\)')
        self.assertRegex(library, r'localeSelect\.addEventListener\(["\'`]change')
        self.assertRegex(library, r'i18n\.setLocale\(localeSelect\.value\)')

    def test_library_and_book_open_annotation_center_as_a_modal(self):
        library_html = self._library_html()
        book_html = self._book_html()

        self.assertRegex(library_html, r'\bid=(?:["\'])?annotationsBtn')
        self.assertRegex(library_html, r'\bdata-annotation-hub')
        self.assertIn('aria-haspopup=dialog', library_html)
        self.assertRegex(library_html, r'/assets/immutable/annotation\.[0-9a-f]{12}\.js')
        self.assertRegex(library_html, r'/assets/immutable/annotation-hub\.[0-9a-f]{12}\.js')
        self.assertNotIn('/annotations/index.html', library_html)
        self.assertRegex(book_html, r'\bid=(?:["\'])?bookAnnotationsBtn')
        self.assertRegex(book_html, r'\bdata-book-hash=')
        self.assertIn('aria-haspopup=dialog', book_html)
        self.assertRegex(book_html, r'/assets/immutable/annotation-hub\.[0-9a-f]{12}\.css')

    def test_annotation_modal_assets_are_immutable_and_not_a_separate_page(self):
        with tempfile.TemporaryDirectory() as directory:
            library = EPUBLibrary(directory)
            library.create_library_home()
            html = Path(directory, 'index.html').read_text(encoding='utf-8')
            self.assertFalse(Path(directory, 'annotations', 'index.html').exists())

        self.assertRegex(html, r'/assets/immutable/annotation-hub\.[0-9a-f]{12}\.js')
        self.assertRegex(html, r'/assets/immutable/annotation-hub\.[0-9a-f]{12}\.css')

    def test_annotation_modal_keeps_keyboard_and_scroll_return_paths(self):
        script = Path("epub_browser/assets/annotation-hub.js").read_text(encoding="utf-8")
        css = Path("epub_browser/assets/annotation-hub.css").read_text(encoding="utf-8")

        self.assertIn("modal.setAttribute('role', 'dialog')", script)
        self.assertIn("modal.setAttribute('aria-modal', 'true')", script)
        self.assertIn("if (event.key === 'Escape')", script)
        self.assertIn("document.body.classList.add('annotation-hub-open')", script)
        self.assertIn("modalState.opener.focus()", script)
        self.assertIn('.annotation-hub-header-button[hidden] { display: none; }', css)
        self.assertIn('grid-column: 3;', css)

    def test_annotation_modal_announces_loading_while_data_is_requested(self):
        script = Path("epub_browser/assets/annotation-hub.js").read_text(encoding="utf-8")
        css = Path("epub_browser/assets/annotation-hub.css").read_text(encoding="utf-8")

        self.assertIn('function renderLoading()', script)
        self.assertIn("container.setAttribute('aria-busy', 'true');", script)
        self.assertIn("loading.setAttribute('role', 'status');", script)
        self.assertIn('renderLoading();', script)
        self.assertIn('.annotation-hub-spinner', css)
        self.assertIn('@keyframes annotation-hub-spin', css)
        self.assertIn('.annotation-hub-spinner { animation: none;', css)

    def test_annotation_hub_routes_state_copy_through_i18n(self):
        script = Path("epub_browser/assets/annotation-hub.js").read_text(encoding="utf-8")

        self.assertIn("function tr(key, params)", script)
        self.assertIn("tr('loading')", script)
        self.assertIn("tr('loadHubFailed')", script)
        self.assertIn("tr('noAnnotationsTitle')", script)
        self.assertIn("tr('noBookAnnotationsTitle')", script)
        self.assertIn('function translateChrome()', script)
        self.assertIn('function renderCurrentView()', script)
        self.assertIn('i18n().onLocaleChange(function()', script)
        self.assertNotIn("'Unable to load annotations'", script)
        self.assertNotIn("'Please try again.'", script)
        self.assertNotIn("'No annotations yet'", script)
        self.assertNotIn("'No annotations in this book'", script)

    def test_chapter_puts_custom_css_in_the_reading_settings_tab(self):
        html = self._chapter_html()

        reading_tab_start = html.index('id="reading-tab"')
        editor_start = html.index('id="customCssInput"')
        self.assertGreater(editor_start, reading_tab_start)
        self.assertIn('Custom styles', html)
        self.assertIn('Optional', html)
        self.assertNotIn('Reading appearance (advanced)', html)
        self.assertNotIn('id="cssPanelToggle"', html)

    def test_reader_template_marks_static_ui_and_preserves_chapter_content(self):
        html = self._chapter_html()

        for key in (
            'reader.tableOfContents', 'reader.previous', 'reader.next',
            'settings.appearance', 'settings.readingMode', 'settings.customStyles',
        ):
            self.assertIn('data-i18n="' + key + '"', html)
        article = html[html.index('<article'):html.index('</article>')]
        self.assertIn('<p>Text</p>', article)
        self.assertNotIn('data-i18n', article)

    def test_reader_mobile_controls_use_translatable_accessible_labels(self):
        html = self._chapter_html()

        self.assertIn('data-i18n="reader.theme"', html)
        self.assertIn('data-i18n-aria-label="reader.openBookHome"', html)

    def test_library_and_chapter_link_the_shared_loading_stylesheet(self):
        self.assertRegex(self._library_html(), r'/assets/immutable/loading\.[0-9a-f]{12}\.css')
        self.assertRegex(self._chapter_html(), r'/assets/immutable/loading\.[0-9a-f]{12}\.css')

    def test_bookshelf_templates_localize_labels_without_translating_business_values(self):
        for html in (self._library_html(), self._book_html(), self._chapter_html()):
            self.assertRegex(html, r'data-i18n=(?:["\'])?bookshelf\.addGroup')
            self.assertRegex(html, r'data-i18n=(?:["\'])?bookshelf\.sync')
            self.assertRegex(html, r'data-tag=(?:["\'])?All(?:["\'])?')

    def test_bookshelf_script_routes_user_messages_through_i18n(self):
        script = Path('epub_browser/assets/bookshelf.js').read_text(encoding='utf-8')

        self.assertNotRegex(script, r"showNotification\(\s*['\"]")
        self.assertNotRegex(script, r"confirm\(\s*['\"]")
        self.assertIn("i18n.t('bookshelf.currentStats'", script)

    def test_bookshelf_renders_adversarial_group_and_book_metadata_as_text(self):
        script = Path('epub_browser/assets/bookshelf.js').read_text(encoding='utf-8')

        self.assertIn('titleElement.textContent = group.name;', script)
        self.assertIn('titleElement.textContent = bookInfo.title;', script)
        self.assertIn('authorElement.textContent = bookInfo.author;', script)
        self.assertIn('pathItem.textContent = name;', script)
        self.assertNotRegex(
            script,
            r'innerHTML\s*=\s*[\s\S]{0,300}(?:group\.name|bookInfo\.(?:title|author))',
        )
