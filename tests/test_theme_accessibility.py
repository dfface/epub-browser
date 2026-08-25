import re
import unittest
from pathlib import Path


THEME_SELECTORS = {
    "light": ":root",
    "dark": ".dark-mode",
    "sepia": ".sepia-mode",
    "forest": ".forest-mode",
    "ocean": ".ocean-mode",
    "peach": ".peach-mode",
    "lavender": ".lavender-mode",
}


def _relative_luminance(color):
    color = color.lstrip("#")
    if len(color) == 3:
        color = "".join(component * 2 for component in color)
    channels = [int(color[index:index + 2], 16) / 255 for index in range(0, 6, 2)]
    linear = [
        channel / 12.92 if channel <= 0.03928 else ((channel + 0.055) / 1.055) ** 2.4
        for channel in channels
    ]
    return sum(weight * channel for weight, channel in zip((0.2126, 0.7152, 0.0722), linear))


def _contrast(first, second):
    lighter, darker = sorted((_relative_luminance(first), _relative_luminance(second)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def _theme_variables(stylesheet, selector):
    variables = {}
    for match in re.finditer(re.escape(selector) + r"\s*\{([^}]*)\}", stylesheet, re.DOTALL):
        variables.update(dict(re.findall(r"(--[\w-]+)\s*:\s*(#[0-9a-fA-F]{3,6})\s*;", match.group(1))))
    return variables


class ThemeAccessibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.stylesheet = Path("epub_browser/assets/theme.css").read_text(encoding="utf-8")

    def test_every_theme_has_a_reading_palette_with_accessible_text_and_controls(self):
        required = {
            "--reader-page",
            "--reader-ink",
            "--reader-muted",
            "--reader-action",
            "--reader-control-bg",
            "--reader-control-hover",
            "--reader-control-text",
        }
        for name, selector in THEME_SELECTORS.items():
            with self.subTest(theme=name):
                colors = _theme_variables(self.stylesheet, selector)
                self.assertTrue(required.issubset(colors), f"{name} is missing reader palette tokens")
                self.assertGreaterEqual(_contrast(colors["--reader-ink"], colors["--reader-page"]), 7)
                self.assertGreaterEqual(_contrast(colors["--reader-muted"], colors["--reader-page"]), 4.5)
                self.assertGreaterEqual(_contrast(colors["--reader-action"], colors["--reader-page"]), 4.5)
                self.assertGreaterEqual(_contrast(colors["--reader-control-text"], colors["--reader-control-bg"]), 4.5)
                self.assertGreaterEqual(_contrast(colors["--reader-control-text"], colors["--reader-control-hover"]), 4.5)
