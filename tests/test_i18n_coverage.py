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
            'auth.js',
            'library.js',
            'library-progress.js',
            'bookshelf.js',
            'book.js',
            'chapter.js',
            'dialog.js',
            'theme.js',
            'annotation.js',
            'annotation-hub.js',
            'reading-progress.js',
            'version-check.js',
        )
    ],
]

DIRECT_SINKS = [
    re.compile(r"(?:showNotification|confirm|alert|prompt)\s*\(\s*['\"][A-Za-z]", re.DOTALL),
]
PROPERTY_ASSIGNMENT = re.compile(
    r"\.\s*(?:textContent|placeholder|title)\s*=\s*(?P<value>[^;]+);", re.DOTALL
)
SET_ATTRIBUTE_START = re.compile(r"\.\s*setAttribute\s*\(")
VISIBLE_LITERAL = re.compile(r"(?P<quote>['\"])(?P<text>[A-Za-z][^'\"\r\n]*)(?P=quote)")
TRANSLATION_KEY_ARGUMENT = re.compile(
    r"(?P<function>(?<![\w.$])i18n\s*\.\s*t|(?<![\w.$])(?:bookT|tr|t|localized))\s*\(\s*$"
)
DICTIONARY_KEY = re.compile(r"^\s*'(?P<key>[^']+)':", re.MULTILINE)
KNOWN_TRANSLATION_KEYS = {
    match.group('key')
    for match in DICTIONARY_KEY.finditer(
        Path('epub_browser/assets/i18n.js').read_text(encoding='utf-8')
    )
}
TR_NAMESPACES = {
    'bookshelf.js': 'bookshelf.',
    'annotation.js': 'annotations.',
    'annotation-hub.js': 'annotations.',
    'dialog.js': 'dialog.',
}
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


def is_known_translation_key(value, literal, path):
    call = TRANSLATION_KEY_ARGUMENT.search(value[:literal.start()])
    if not call:
        return False
    key = literal.group('text')
    function = call.group('function').replace(' ', '')
    if function in {'tr', 'localized'}:
        namespace = TR_NAMESPACES.get(path.name)
        return namespace is not None and namespace + key in KNOWN_TRANSLATION_KEYS
    return key in KNOWN_TRANSLATION_KEYS


def first_visible_literal(value, path):
    for literal in VISIBLE_LITERAL.finditer(value):
        if not is_known_translation_key(value, literal, path):
            return literal
    return None


def closing_parenthesis(source, opening):
    depth = 0
    quote = None
    escaped = False
    for position in range(opening, len(source)):
        character = source[position]
        if quote:
            if escaped:
                escaped = False
            elif character == '\\':
                escaped = True
            elif character == quote:
                quote = None
            continue
        if character in "'\"`":
            quote = character
        elif character == '(':
            depth += 1
        elif character == ')':
            depth -= 1
            if depth == 0:
                return position
    return None


def split_top_level_arguments(source, start, end):
    arguments = []
    argument_start = start
    depth = 0
    quote = None
    escaped = False
    for position in range(start, end):
        character = source[position]
        if quote:
            if escaped:
                escaped = False
            elif character == '\\':
                escaped = True
            elif character == quote:
                quote = None
            continue
        if character in "'\"`":
            quote = character
        elif character in '([{':
            depth += 1
        elif character in ')]}':
            depth -= 1
        elif character == ',' and depth == 0:
            arguments.append((argument_start, position))
            argument_start = position + 1
    arguments.append((argument_start, end))
    return arguments


def iter_set_attribute_values(source):
    for call in SET_ATTRIBUTE_START.finditer(source):
        opening = call.end() - 1
        closing = closing_parenthesis(source, opening)
        if closing is None:
            continue
        arguments = split_top_level_arguments(source, opening + 1, closing)
        if len(arguments) < 2:
            continue
        attribute_start, attribute_end = arguments[0]
        attribute = source[attribute_start:attribute_end].strip().strip("'\"")
        if attribute not in {'aria-label', 'placeholder', 'title'}:
            continue
        value_start, value_end = arguments[1]
        yield source[value_start:value_end], value_start


def find_literal_ui_sinks_text(source, path):
    failures = []
    for number, line in enumerate(source.splitlines(), 1):
        if 'i18n-allow-literal' in line and not VALID_LITERAL_EXCEPTION.search(line):
            failures.append(f'{path}:{number}: invalid i18n literal exception: {line.strip()}')

    for pattern in DIRECT_SINKS:
        for match in pattern.finditer(source):
            add_failure(failures, source, path, match.start(), 'literal UI sink')

    for assignment in PROPERTY_ASSIGNMENT.finditer(source):
        literal = first_visible_literal(assignment.group('value'), path)
        if literal:
            add_failure(
                failures,
                source,
                path,
                assignment.start('value') + literal.start(),
                'literal UI sink',
            )

    for value, value_start in iter_set_attribute_values(source):
        literal = first_visible_literal(value, path)
        if literal:
            add_failure(failures, source, path, value_start + literal.start(), 'literal UI sink')

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
    def test_account_and_administration_copy_exists_in_both_locales(self):
        required = {
            'account.menu',
            'account.signIn',
            'account.associationTitle',
            'account.associationSucceeded',
            'account.changePassword',
            'account.passwordChanged',
            'account.sessions',
            'account.sessionRevoked',
            'account.logout',
            'account.error.authentication_required',
            'account.error.csrf_required',
            'account.error.invalid_credentials',
            'account.error.identity_already_linked',
            'account.error.unknown',
            'admin.title',
            'admin.createUser',
            'admin.resetPassword',
            'admin.revokeSessions',
            'admin.restrictedBook',
            'admin.grantBook',
            'admin.revokeBook',
            'admin.error.last_enabled_admin',
            'admin.error.user_disabled',
            'admin.error.unknown',
        }
        source = Path('epub_browser/assets/i18n.js').read_text(encoding='utf-8')
        keys = set(DICTIONARY_KEY.findall(source))

        self.assertEqual(required - keys, set())

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

    def test_catches_multiline_calls_dynamic_attributes_and_visible_html(self):
        source = '''
            showNotification(
              'Network failed'
            );
            element . textContent = isLoading ? 'Loading' : 'Ready';
            element.setAttribute(
              'aria-label',
              isLoading ? i18n.t('reader.loadingContent') : 'Ready'
            );
            element.setAttribute('title', ready ? i18n.t('reader.loadingContent') : 'Loading');
            element.textContent = i18n.t('reader.loadingContent');
            element.setAttribute('aria-label', t('library.login'));
            <button>Save</button>
        '''
        failures = find_literal_ui_sinks_text(source, Path('fixture.js'))
        self.assertEqual(len(failures), 5)
        self.assertIn('literal UI sink', failures[0])
        self.assertIn('literal UI sink', failures[1])
        self.assertIn('literal UI sink', failures[2])
        self.assertIn('literal UI sink', failures[3])
        self.assertIn('unlocalized visible HTML text', failures[4])

    def test_translation_keys_must_be_known_for_the_current_wrapper(self):
        source = "element.textContent = t('Loading');"
        failures = find_literal_ui_sinks_text(source, Path('epub_browser/assets/library.js'))
        self.assertEqual(len(failures), 1)
        self.assertIn('literal UI sink', failures[0])

    def test_only_project_translation_wrappers_are_trusted(self):
        source = '''
            element.textContent = rogue.t('library.login');
            element.textContent = rogue.tr('close');
            element.textContent = rogue.bookT('book.confirm');
        '''
        failures = find_literal_ui_sinks_text(source, Path('epub_browser/assets/annotation.js'))
        self.assertEqual(len(failures), 3)
        self.assertTrue(all('literal UI sink' in failure for failure in failures))

    def test_exceptions_require_an_approved_reason_on_the_same_line(self):
        valid = '<span>epub-browser</span><!-- i18n-allow-literal: product name -->'
        invalid = "showNotification('Network failed'); // i18n-allow-literal: temporary"

        self.assertEqual(find_literal_ui_sinks_text(valid, Path('fixture.js')), [])
        failures = find_literal_ui_sinks_text(invalid, Path('fixture.js'))
        self.assertEqual(len(failures), 2)
        self.assertIn('invalid i18n literal exception', failures[0])
        self.assertIn('literal UI sink', failures[1])
