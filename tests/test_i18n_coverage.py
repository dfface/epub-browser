import re
import unittest
from pathlib import Path


FIRST_PARTY = [
    Path('epub_browser/library.py'),
    Path('epub_browser/processor.py'),
    Path('epub_browser/version.py'),
    *[
        Path('epub_browser/assets', name)
        for name in (
            'library.js',
            'bookshelf.js',
            'book.js',
            'chapter.js',
            'theme.js',
            'annotation.js',
            'annotation-hub.js',
            'reading-progress.js',
            'version-check.js',
        )
    ],
]

FORBIDDEN = [
    re.compile(r"(?:showNotification|confirm|alert|prompt)\(\s*['\"][A-Za-z]"),
    re.compile(r"\.(?:textContent|placeholder|title)\s*=\s*['\"][A-Za-z]"),
]
HTML_ATTRIBUTE = re.compile(
    r"(?P<attribute>placeholder|aria-label|title)=(?P<quote>['\"])[A-Za-z][^'{]*?(?P=quote)"
)


def has_localized_attribute_binding(line, attribute, position=None):
    """Allow English fallback HTML only when the same tag has its i18n binding."""
    if position is None:
        position = line.find(attribute + '=')
    tag_start = line.rfind('<', 0, position + 1)
    tag_end = line.find('>', position)
    if tag_start == -1 or tag_end == -1:
        return False
    tag = line[tag_start:tag_end + 1]
    return re.search(r"\bdata-i18n-" + re.escape(attribute) + r"=", tag) is not None


def find_literal_ui_sinks(path):
    failures = []
    for number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
        if 'i18n-allow-literal' in line:
            continue
        if any(pattern.search(line) for pattern in FORBIDDEN):
            failures.append(f'{path}:{number}: {line.strip()}')
            continue
        for match in HTML_ATTRIBUTE.finditer(line):
            if not has_localized_attribute_binding(line, match.group('attribute'), match.start()):
                failures.append(f'{path}:{number}: {line.strip()}')
                break
    return failures


class I18nCoverageTests(unittest.TestCase):
    def test_first_party_ui_sinks_do_not_embed_english_copy(self):
        failures = []
        for path in FIRST_PARTY:
            failures.extend(find_literal_ui_sinks(path))
        self.assertEqual(failures, [], '\n' + '\n'.join(failures))

    def test_html_fallback_requires_a_matching_i18n_attribute_binding(self):
        self.assertTrue(
            has_localized_attribute_binding(
                '<input placeholder="Search" data-i18n-placeholder="library.searchPlaceholder">',
                'placeholder',
            )
        )
        self.assertFalse(has_localized_attribute_binding('<input placeholder="Search">', 'placeholder'))
        self.assertFalse(
            has_localized_attribute_binding(
                '<input placeholder="Search"><span data-i18n-placeholder="library.searchPlaceholder">',
                'placeholder',
            )
        )
