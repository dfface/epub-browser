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

SINKS = [
    re.compile(r"(?:showNotification|confirm|alert|prompt)\s*\(\s*['\"][A-Za-z]", re.DOTALL),
    re.compile(r"\.\s*(?:textContent|placeholder|title)\s*=\s*['\"][A-Za-z]", re.DOTALL),
]
HTML_TAG = re.compile(r"<(?P<name>[A-Za-z][\w:-]*)\b(?P<attributes>[^>]*)>", re.DOTALL)
HTML_ATTRIBUTE = re.compile(
    r"\b(?P<attribute>placeholder|aria-label|title)\s*=\s*(?P<quote>['\"])[A-Za-z][^'{]*?(?P=quote)",
    re.DOTALL,
)
VISIBLE_HTML_EXCLUSIONS = {'script', 'style', 'template'}
VALID_LITERAL_EXCEPTION = re.compile(
    r"i18n-allow-literal:\s*(?:product name|URL/protocol value|CSS/HTML syntax|developer log|stable data identifier)\s*(?:-->|$)",
    re.IGNORECASE,
)


def line_number(source, position):
    return source.count('\n', 0, position) + 1


def source_line(source, position):
    return source.splitlines()[line_number(source, position) - 1]


def has_valid_literal_exception(source, position):
    return VALID_LITERAL_EXCEPTION.search(source_line(source, position)) is not None


def has_localized_attribute_binding(attributes, attribute):
    """Allow English fallback HTML only when the same tag has its i18n binding."""
    return re.search(r"\bdata-i18n-" + re.escape(attribute) + r"\s*=", attributes) is not None


def add_failure(failures, source, path, position, reason):
    if not has_valid_literal_exception(source, position):
        number = line_number(source, position)
        failures.append(f'{path}:{number}: {reason}: {source_line(source, position).strip()}')


def find_literal_ui_sinks_text(source, path):
    failures = []
    for number, line in enumerate(source.splitlines(), 1):
        if 'i18n-allow-literal' in line and not VALID_LITERAL_EXCEPTION.search(line):
            failures.append(f'{path}:{number}: invalid i18n literal exception: {line.strip()}')

    for pattern in SINKS:
        for match in pattern.finditer(source):
            add_failure(failures, source, path, match.start(), 'literal UI sink')

    for tag in HTML_TAG.finditer(source):
        attributes = tag.group('attributes')
        for match in HTML_ATTRIBUTE.finditer(attributes):
            if not has_localized_attribute_binding(attributes, match.group('attribute')):
                add_failure(
                    failures,
                    source,
                    path,
                    tag.start('attributes') + match.start(),
                    'unlocalized HTML attribute',
                )

        if tag.group('name').lower() in VISIBLE_HTML_EXCLUSIONS:
            continue
        next_tag = source.find('<', tag.end())
        text = source[tag.end():len(source) if next_tag == -1 else next_tag]
        visible = re.match(r'\s*[A-Za-z]', text)
        if visible and '{' not in text and not re.search(r'\bdata-i18n\s*=', attributes):
            add_failure(
                failures,
                source,
                path,
                tag.end() + visible.start(),
                'unlocalized visible HTML text',
            )
    return failures


def find_literal_ui_sinks(path):
    return find_literal_ui_sinks_text(path.read_text(encoding='utf-8'), path)


class I18nCoverageTests(unittest.TestCase):
    def test_first_party_ui_sinks_do_not_embed_english_copy(self):
        failures = []
        for path in FIRST_PARTY:
            failures.extend(find_literal_ui_sinks(path))
        self.assertEqual(failures, [], '\n' + '\n'.join(failures))

    def test_html_fallback_requires_a_matching_i18n_attribute_binding(self):
        self.assertEqual(
            find_literal_ui_sinks_text(
                '<input\n placeholder="Search"\n data-i18n-placeholder="library.searchPlaceholder">',
                Path('fixture.html'),
            ),
            [],
        )
        self.assertEqual(
            len(find_literal_ui_sinks_text('<input placeholder="Search">', Path('fixture.html'))),
            1,
        )
        self.assertEqual(
            len(
                find_literal_ui_sinks_text(
                    '<input placeholder="Search"><span data-i18n-placeholder="library.searchPlaceholder">',
                    Path('fixture.html'),
                )
            ),
            1,
        )

    def test_catches_multiline_calls_whitespace_properties_and_visible_html(self):
        source = '''
            showNotification(
              'Network failed'
            );
            element . textContent = 'Loading';
            <button>Save</button>
        '''
        failures = find_literal_ui_sinks_text(source, Path('fixture.js'))
        self.assertEqual(len(failures), 3)
        self.assertIn('literal UI sink', failures[0])
        self.assertIn('literal UI sink', failures[1])
        self.assertIn('unlocalized visible HTML text', failures[2])

    def test_exceptions_require_an_approved_reason_on_the_same_line(self):
        valid = '<span>epub-browser</span><!-- i18n-allow-literal: product name -->'
        invalid = "showNotification('Network failed'); // i18n-allow-literal: temporary"

        self.assertEqual(find_literal_ui_sinks_text(valid, Path('fixture.js')), [])
        failures = find_literal_ui_sinks_text(invalid, Path('fixture.js'))
        self.assertEqual(len(failures), 2)
        self.assertIn('invalid i18n literal exception', failures[0])
        self.assertIn('literal UI sink', failures[1])
