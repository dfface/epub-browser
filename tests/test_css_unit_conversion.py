"""Regression tests for normalizing font/length units (px/pt/rem/%) to `em`.

See issue #35: books that size text with fixed or root/percentage-relative
units ignore the reader's font-size control. The conversion lives in
`epub_browser.processor` (`sanitize_css_declarations` / `sanitize_css_text`)
so it is shared by the SSG and Server pipelines and applied once during
conversion, not at request time.
"""

import os
import re
import unittest

from epub_browser import processor
from epub_browser.processor import (
    SERVER_OUTPUT_REVISION,
    _normalize_font_unit_to_em,
    sanitize_css_declarations,
    sanitize_css_text,
)

ASSETS_DIR = os.path.join(os.path.dirname(processor.__file__), "assets")
CHAPTER_CSS = os.path.join(ASSETS_DIR, "chapter.css")


class FixedUnitToEmConversionTests(unittest.TestCase):
    def test_inline_font_size_px_converted_to_em(self):
        out = sanitize_css_declarations("font-size: 12px; color: red")
        self.assertIn("font-size: 0.75em", out)
        self.assertIn("color: red", out)

    def test_inline_pt_converted(self):
        # 12pt == 16px == 1em against the 16px root reference.
        out = sanitize_css_declarations("font-size: 12pt")
        self.assertIn("font-size: 1em", out)

    def test_letter_and_word_spacing_converted(self):
        out = sanitize_css_declarations("letter-spacing: 2px; word-spacing: 4px")
        self.assertIn("letter-spacing: 0.125em", out)
        self.assertIn("word-spacing: 0.25em", out)

    def test_em_and_unitless_untouched(self):
        # `em` and unitless values are already relative and preserved as-is.
        out = sanitize_css_declarations(
            "font-size: 1.2em; line-height: 1.5; letter-spacing: 0.1em"
        )
        self.assertIn("font-size: 1.2em", out)
        self.assertIn("line-height: 1.5", out)
        self.assertIn("letter-spacing: 0.1em", out)

    def test_rem_converted_to_em(self):
        # `rem` is root-relative and does NOT scale with the reader font-size
        # control, so it must be normalized to `em`.
        out = sanitize_css_declarations(
            "font-size: 1.5rem; letter-spacing: 0.5rem; line-height: 2rem"
        )
        self.assertIn("font-size: 1.5em", out)
        self.assertIn("letter-spacing: 0.5em", out)
        self.assertIn("line-height: 2em", out)
        self.assertNotIn("rem", out)

    def test_percent_converted_to_em(self):
        # `%` is normalized to `em` for consistency (150% == 1.5em, etc.).
        out = sanitize_css_declarations(
            "font-size: 150%; line-height: 200%; letter-spacing: 50%"
        )
        self.assertIn("font-size: 1.5em", out)
        self.assertIn("line-height: 2em", out)
        self.assertIn("letter-spacing: 0.5em", out)
        self.assertNotIn("%", out)

    def test_important_preserved(self):
        out = sanitize_css_declarations("font-size: 14pt !important")
        self.assertIn("font-size: 1.1667em !important", out)

    def test_zero_and_negative(self):
        out = sanitize_css_declarations("font-size: 0px; letter-spacing: -1px")
        self.assertIn("font-size: 0", out)
        self.assertIn("letter-spacing: -0.0625em", out)

    def test_layout_critical_properties_untouched(self):
        out = sanitize_css_declarations("border: 1px solid #000; margin: 8px; width: 200px")
        self.assertIn("border: 1px solid #000", out)
        self.assertIn("margin: 8px", out)
        self.assertIn("width: 200px", out)

    def test_calc_and_var_values_untouched(self):
        out = sanitize_css_declarations("font-size: calc(12px + 1px); line-height: var(--lh)")
        self.assertIn("font-size: calc(12px + 1px)", out)
        self.assertIn("line-height: var(--lh)", out)

    def test_line_height_relative_to_block_font_size(self):
        out = sanitize_css_declarations("font-size: 12px; line-height: 18px")
        self.assertIn("line-height: 1.5em", out)

    def test_line_height_without_font_size_uses_root_reference(self):
        out = sanitize_css_declarations("line-height: 18px")
        self.assertIn("line-height: 1.125em", out)

    def test_malformed_css_does_not_break(self):
        out = sanitize_css_declarations("font-size: ; broken: {{ ; font-size: 10px")
        self.assertIn("font-size: 0.625em", out)

    def test_stylesheet_media_query_converted(self):
        css = (
            "p { font-size: 12px; }\n"
            "@media (max-width: 600px) { p { font-size: 10px; } }"
        )
        out = sanitize_css_text(css)
        self.assertIn("font-size: 0.75em", out)
        self.assertIn("font-size: 0.625em", out)

    def test_stylesheet_keeps_relative_and_safe_values(self):
        css = (
            "body { font-family: Georgia, serif; max-width: 40em; }\n"
            "h1 { font-weight: 700; line-height: 1.2; }\n"
            "img { max-width: 100%; height: auto; }"
        )
        out = sanitize_css_text(css)
        self.assertIn("font-family: Georgia", out)
        self.assertIn("max-width: 40em", out)
        self.assertIn("line-height: 1.2", out)

    def test_risky_css_dropped(self):
        out = sanitize_css_text("p { background: url(javascript:alert(1)); }")
        self.assertEqual(out.strip(), "")

    def test_helper_ignores_unrelated_property(self):
        self.assertIsNone(_normalize_font_unit_to_em("border", "1px", None))

    def test_content_revision_bumped_for_semantics_change(self):
        # The stored chapter CSS now differs (px/pt -> em), so the content
        # revision must be bumped; SSG/Server regenerates derived content.
        self.assertEqual(SERVER_OUTPUT_REVISION, "server-content-v11")


class ReaderContentCssUsesEmTests(unittest.TestCase):
    """The reader's own content typography must use `em` (not `rem`) so it scales
    with the reader font-size control, matching the book-body behavior fixed in
    #35. Only the live rules are asserted here: `#eb-content pre` / `pre code`.
    The legacy `#eb-content h2/h3/h4/p` block was dead (commented-out) CSS and has
    been intentionally removed, so headings fall back to browser defaults.
    Chrome (toolbar/settings) stays `rem` on purpose and is not asserted here.
    """

    @classmethod
    def setUpClass(cls):
        with open(CHAPTER_CSS, "r", encoding="utf-8") as fh:
            # Strip `/* ... */` comments so the simple regex parser below only
            # sees live rules.
            cls.css = re.sub(r"/\*.*?\*/", "", fh.read(), flags=re.DOTALL)

    @staticmethod
    def _rule_font_size(css, selector):
        match = re.search(
            re.escape(selector) + r"\s*\{([^}]*)\}", css, re.IGNORECASE
        )
        if not match:
            return None
        fm = re.search(r"font-size:\s*([^;]+);", match.group(1), re.IGNORECASE)
        return fm.group(1).strip() if fm else None

    def test_content_headings_not_styled(self):
        # The `#eb-content h2/h3/h4` rules were dead (commented-out) CSS and have
        # been intentionally removed; headings must not define a live font-size
        # rule (browser defaults apply). Guards against re-introducing them.
        for selector in ("#eb-content h2", "#eb-content h3", "#eb-content h4"):
            self.assertIsNone(
                self._rule_font_size(self.css, selector),
                f"{selector} should not define a live font-size rule",
            )

    def test_content_code_uses_em(self):
        fs = self._rule_font_size(self.css, "#eb-content pre")
        self.assertIsNotNone(fs)
        self.assertIn("em", fs)
        self.assertNotIn("rem", fs)
        # `pre code` is `1em` relative to `pre` so the block is not double-scaled.
        code_fs = self._rule_font_size(self.css, "#eb-content pre code")
        self.assertIsNotNone(code_fs)
        self.assertIn("em", code_fs)


if __name__ == "__main__":
    unittest.main()
