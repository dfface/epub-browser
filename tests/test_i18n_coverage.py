import re
import unittest
from pathlib import Path


FIRST_PARTY = [
    Path('epub_browser/library.py'),
    Path('epub_browser/processor.py'),
    Path('epub_browser/server_chrome.py'),
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
            'book-reviews.js',
            'reading-sessions.js',
            'reading-insights.js',
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
    r"(?P<function>(?<![\w.$])i18n\s*\.\s*t|(?<![\w.$])(?:bookT|tr|t|localized|translate))\s*\(\s*$"
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
    'book-reviews.js': 'bookReviews.',
    'reading-insights.js': 'readingInsights.',
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
    key = literal.group('text')
    if path.name == 'reading-insights.js':
        preceding = value[:literal.start()]
        if (
            key.startswith('readingInsights.')
            and re.search(r"(?:^|[^\w.$])translate\s*\(\s*target\s*,\s*$", preceding)
        ):
            return key in KNOWN_TRANSLATION_KEYS
        reading_call = re.search(
            r"(?:^|[^\w.$])translate\s*\(\s*target\s*,\s*['\"](?P<key>readingInsights\.[A-Za-z0-9.]+)['\"]",
            preceding,
        )
        if reading_call:
            return reading_call.group('key') in KNOWN_TRANSLATION_KEYS
    call = TRANSLATION_KEY_ARGUMENT.search(value[:literal.start()])
    if not call:
        return False
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
            'library.navigation',
            'book.navigation',
            'reader.navigation',
            'account.signIn',
            'account.changePassword',
            'account.passwordChanged',
            'account.sessions',
            'account.pats.title',
            'account.pats.description',
            'account.pats.name',
            'account.pats.scopes',
            'account.pats.expiration',
            'account.pats.never',
            'account.pats.neverExpiresWarning',
            'account.pats.create',
            'account.pats.created',
            'account.pats.copy',
            'account.pats.revoke',
            'account.pats.empty',
            'account.pats.lastUsed',
            'account.pats.expires',
            'account.pats.error.invalid_personal_access_token',
            'account.sessionRevoked',
            'account.sessionTimes',
            'account.logout',
            'account.error.authentication_required',
            'account.error.csrf_required',
            'account.error.invalid_credentials',
            'account.error.unknown',
            'admin.menu',
            'admin.title',
            'admin.close',
            'admin.description',
            'admin.usersDescription',
            'admin.manageUser',
            'admin.accountAccess',
            'admin.security',
            'admin.createUser',
            'admin.resetPassword',
            'admin.revokeSessions',
            'admin.restrictedBook',
            'admin.grantBook',
            'admin.grantUsers',
            'admin.noGrantableUsers',
            'admin.saveBookGrants',
            'admin.bookGrantsSaved',
            'admin.revokeBook',
            'admin.error.last_enabled_admin',
            'admin.error.user_disabled',
            'admin.error.unknown',
            'admin.books.searchLabel',
            'admin.books.searchPlaceholder',
            'admin.books.visibilityFilter',
            'admin.books.tagFilter',
            'admin.books.pageSize',
            'admin.books.refresh',
            'admin.books.tableLabel',
            'admin.books.paginationLabel',
            'admin.books.visibility.all',
            'admin.books.visibility.authenticated',
            'admin.books.visibility.restricted',
            'admin.books.profile.auto',
            'admin.books.profile.technical',
            'admin.books.profile.fiction',
            'admin.books.profile.general',
            'admin.books.tag.all',
            'admin.books.header.book',
            'admin.books.header.access',
            'admin.books.header.profile',
            'admin.books.header.results',
            'admin.books.header.updated',
            'admin.books.header.action',
            'admin.books.manage',
            'admin.books.manageLabel',
            'admin.books.editorTitle',
            'admin.books.editorLabel',
            'admin.books.visibilityLabel',
            'admin.books.memberAccess',
            'admin.books.serverTags',
            'admin.books.aiProfile',
            'admin.books.save',
            'admin.books.cancel',
            'admin.books.cancelLabel',
            'admin.books.clearResults',
            'admin.books.clearResultsLabel',
            'admin.books.loading',
            'admin.books.empty',
            'admin.books.loadError',
            'admin.books.refreshError',
            'admin.books.detailError',
            'admin.books.saveError',
            'admin.books.clearError',
            'admin.books.grantCount',
            'admin.books.resultCount',
            'admin.books.pageSummary',
            'admin.books.pageButton',
            'admin.books.previousPage',
            'admin.books.nextPage',
            'admin.books.clearResultsConfirm',
            'admin.books.deletedCount',
            'admin.books.live.loading',
            'admin.books.live.loaded',
            'admin.books.live.refreshed',
            'admin.books.live.saved',
            'admin.books.live.cleared',
            'admin.books.error.not_found',
            'admin.books.error.invalid_book_settings',
            'admin.books.error.forbidden',
            'admin.books.error.csrf_required',
            'admin.books.error.network',
            'admin.books.error.unknown',
            'admin.ai.jobs.title',
            'admin.ai.jobs.description',
            'admin.ai.jobs.statusFilter',
            'admin.ai.jobs.pageSize',
            'admin.ai.jobs.tableLabel',
            'admin.ai.jobs.paginationLabel',
            'admin.ai.jobs.refresh',
            'admin.ai.jobs.status.all',
            'admin.ai.jobs.status.queued',
            'admin.ai.jobs.status.running',
            'admin.ai.jobs.status.complete',
            'admin.ai.jobs.status.failed',
            'admin.ai.jobs.status.interrupted',
            'admin.ai.jobs.header.status',
            'admin.ai.jobs.header.job',
            'admin.ai.jobs.header.book',
            'admin.ai.jobs.header.requester',
            'admin.ai.jobs.header.scope',
            'admin.ai.jobs.header.progress',
            'admin.ai.jobs.header.timeline',
            'admin.ai.jobs.header.error',
            'admin.ai.jobs.header.created',
            'admin.ai.jobs.header.updated',
            'admin.ai.jobs.header.action',
            'admin.ai.jobs.progress',
            'admin.ai.jobs.progressLabel',
            'admin.ai.jobs.unknownBook',
            'admin.ai.jobs.unknownUser',
            'admin.ai.jobs.unknownValue',
            'admin.ai.jobs.scope.book',
            'admin.ai.jobs.scope.chapter',
            'admin.ai.jobs.language.en',
            'admin.ai.jobs.language.zh-CN',
            'admin.ai.jobs.retry',
            'admin.ai.jobs.retrying',
            'admin.ai.jobs.retryQueued',
            'admin.ai.jobs.retryComplete',
            'admin.ai.jobs.retryConflict',
            'admin.ai.jobs.empty',
            'admin.ai.jobs.loading',
            'admin.ai.jobs.loadError',
            'admin.ai.jobs.refreshError',
            'admin.ai.jobs.pageSummary',
            'admin.ai.jobs.pageButton',
            'admin.ai.jobs.previousPage',
            'admin.ai.jobs.nextPage',
            'admin.ai.jobs.error.invalid_ai_job_query',
            'admin.ai.jobs.error.ai_job_not_found',
            'admin.ai.jobs.error.ai_job_not_retryable',
            'admin.ai.jobs.error.ai_job_retry_conflict',
            'admin.ai.jobs.error.ai_disabled',
            'admin.ai.jobs.error.ai_not_authorized',
            'admin.ai.jobs.error.ai_owner_disabled',
            'admin.ai.jobs.error.book_not_found',
            'admin.ai.jobs.error.chapter_not_found',
            'admin.ai.jobs.error.ai_reading_required',
            'admin.ai.jobs.error.ai_template_unavailable',
            'admin.ai.jobs.error.source_unavailable',
            'admin.ai.jobs.error.no_reading_material',
            'admin.ai.jobs.error.unknown',
        }
        source = Path('epub_browser/assets/i18n.js').read_text(encoding='utf-8')
        keys = set(DICTIONARY_KEY.findall(source))

        self.assertEqual(required - keys, set())

    def test_feynman_learning_copy_exists_in_both_locales(self):
        required = {
            'ai.teachKicker',
            'ai.teachTitle',
            'ai.teachAnalogy',
            'ai.teachCheck',
        }
        source = Path('epub_browser/assets/i18n.js').read_text(encoding='utf-8')
        english = source[source.index('en: {'):source.index("'zh-CN': {")]
        chinese = source[source.index("'zh-CN': {"):]

        self.assertEqual(required - set(DICTIONARY_KEY.findall(english)), set())
        self.assertEqual(required - set(DICTIONARY_KEY.findall(chinese)), set())

    def test_image_notes_vocabulary_and_toc_location_are_localized(self):
        source = Path('epub_browser/assets/i18n.js').read_text(encoding='utf-8')
        for key in (
            'annotations.addImageNote',
            'annotations.imageNote',
            'ai.annotation.vocabulary',
            'reader.locateCurrentChapter',
        ):
            self.assertEqual(source.count("'" + key + "'"), 5, key)

    def test_generation_stage_and_task_limit_copy_exists_in_both_locales(self):
        required = {
            'ai.stage.preparingSource',
            'ai.stage.generatingCore',
            'ai.stage.groundingSource',
            'admin.ai.dailyLimit',
            'admin.ai.dailyLimitHelp',
        }
        source = Path('epub_browser/assets/i18n.js').read_text(encoding='utf-8')
        english = source[source.index('en: {'):source.index("'zh-CN': {")]
        chinese = source[source.index("'zh-CN': {"):]

        self.assertEqual(required - set(DICTIONARY_KEY.findall(english)), set())
        self.assertEqual(required - set(DICTIONARY_KEY.findall(chinese)), set())
        self.assertIn(
            'AI reading tasks each authorized member may start per day', english,
        )
        self.assertIn('several backend model calls', english)

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
