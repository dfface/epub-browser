(function(root, factory) {
  var exported = factory();
  if (typeof module === 'object' && module.exports) module.exports = exported;
  if (root && root.document) root.EpubBrowserI18n = exported.createRuntime(root, exported.dictionaries);
})(typeof window !== 'undefined' ? window : (typeof globalThis !== 'undefined' ? globalThis : this), function() {
  'use strict';

  var STORAGE_KEY = 'epub_browser_locale';
  var dictionaries = {
    en: {
      'common.language': 'Language',
      'common.chinese': 'Chinese',
      'common.english': 'English',
      'common.version': 'Version {version}',
      'theme.light': 'Light',
      'theme.dark': 'Dark',
      'theme.sepia': 'Sepia',
      'theme.forest': 'Forest',
      'theme.ocean': 'Ocean',
      'theme.peach': 'Peach',
      'theme.lavender': 'Lavender',
      'reader.library': 'Library',
      'reader.breadcrumb': 'Breadcrumb',
      'reader.theme': 'Theme',
      'reader.turning': 'Turning',
      'reader.scrolling': 'Scrolling',
      'reader.book': 'Book',
      'reader.home': 'Home',
      'reader.top': 'Top',
      'reader.settings': 'Settings',
      'reader.shelf': 'Shelf',
      'reader.tableOfContents': 'Table of contents',
      'reader.bookChapters': 'Chapters',
      'reader.thisChapterContents': 'This chapter',
      'reader.openBookChapters': 'Open book chapters',
      'reader.skipToContent': 'Skip to reading content',
      'reader.previous': 'Previous chapter',
      'reader.next': 'Next chapter',
      'reader.previousPage': 'Previous page',
      'reader.nextPage': 'Next page',
      'reader.currentPage': 'Current page',
      'reader.totalPages': 'Total pages',
      'reader.jump': 'Jump',
      'reader.clickToTurn': 'Click to turn page',
      'reader.pureReading': 'Pure reading mode',
      'reader.reloadPages': 'Reload pages',
      'reader.setPageHeight': 'Set page height',
      'reader.loadingContent': 'Loading content',
      'reader.openBookHome': 'Open book home',
      'reader.closeBookHome': 'Close book home',
      'reader.closeSettings': 'Close settings',
      'reader.closeTableOfContents': 'Close table of contents',
      'reader.pageHeight': 'Page height',
      'reader.turningModeEnabled': 'Page turning mode enabled',
      'reader.exitTurningConfirm': 'Exit page turning mode?',
      'reader.exitTurning': 'Exit page turning',
      'reader.progressLoadedPage': 'Progress loaded: Page {page}',
      'reader.progressLoadedPercent': 'Progress loaded: {percent}%',
      'reader.pageRange': '1-{total}',
      'reader.validNumber': 'Valid number',
      'reader.firstChapter': 'First chapter',
      'reader.lastChapter': 'Last chapter',
      'reader.first': 'First',
      'reader.last': 'Last',
      'reader.onlyPageMode': 'Only in page mode',
      'reader.pureModeOn': 'Pure mode on',
      'reader.pureModeOff': 'Pure mode off',
      'reader.reloaded': 'Reloaded',
      'reader.clickPageOn': 'Click page on',
      'reader.clickPageOff': 'Click page off',
      'reader.tocLoadFailed': 'Load failed',
      'reader.tocNoTitle': 'No title',
      'reader.annotationNotFound': 'Could not locate this annotation. Opened its chapter instead.',
      'reader.annotationLoadFailed': 'Could not load this annotation. Opened its chapter instead.',
      'reader.loadingNextChapter': 'Loading next chapter',
      'reader.loadingPreviousChapter': 'Loading previous chapter',
      'reader.chapterNumber': 'Chapter {number}',
      'reader.continuousScrollRequiresScrolling': 'Continuous scroll requires Scrolling mode',
      'reader.continuousScrollEnabledReloading': 'Continuous scroll enabled - reloading...',
      'reader.continuousScrollDisabledReloading': 'Continuous scroll disabled - reloading...',
      'settings.appearance': 'Appearance',
      'settings.reading': 'Reading',
      'settings.fontFamily': 'Font family',
      'settings.fontSize': 'Font size',
      'settings.bookDefault': 'Book default',
      'settings.systemDefault': 'System default',
      'settings.customByInput': 'Custom by input',
      'settings.customFontPlaceholder': 'Input font name here',
      'settings.customFontTip': 'Tip: Font family applies globally. Ensure it’s installed in the system.',
      'settings.apply': 'Apply',
      'settings.readingMode': 'Reading mode',
      'settings.showReadingProgressBar': 'Show reading progress bar',
      'settings.desktopChapterSidebar': 'Show chapter sidebar on desktop',
      'settings.continuousScroll': 'Enable continuous scroll',
      'settings.continuousScrollTip': 'Automatically loads the next chapter when scrolling past the end. Note: scroll progress save/restore is disabled. Tip: press Space for a similar seamless reading experience when this is off.',
      'settings.customStyles': 'Custom styles',
      'settings.optional': 'Optional',
      'settings.customStylesDescription': 'Use CSS to fine-tune this book’s typography and layout.',
      'settings.customCssPlaceholder': 'Please input your CSS code... For example: #eb-content-container{background: inherit; box-shadow:inherit;} #eb-content{margin: 50px; width: auto} #eb-content p {margin-bottom: 0.8rem; line-height: 1.7;}',
      'settings.save': 'Save',
      'settings.saveAsDefault': 'Save as default',
      'settings.reset': 'Reset',
      'settings.loadDefault': 'Load default',
      'settings.preview': 'Preview',
      'settings.defaultStyleTip': 'Tip: The default style will be applied to all books unless a custom style is set for specific books.',
      'settings.saved': 'Saved',
      'settings.defaultSaved': 'Default saved',
      'settings.noDefault': 'No default',
      'settings.loaded': 'Loaded',
      'settings.resetDone': 'Reset',
      'settings.applied': 'Applied',
      'settings.saveAsDefaultConfirm': 'Save as default?',
      'settings.loadDefaultConfirm': 'Load default?',
      'settings.resetConfirm': 'Reset?',
      'settings.continuousScrollUnavailable': 'Continuous scroll is only available in Scrolling mode. Switch to Scrolling mode first to enable this feature.',
      'library.title': 'Library',
      'library.pageTitle': 'EPUB Library',
      'library.description': 'EPUB Library - A web-based EPUB reader',
      'library.information': 'Library information',
      'library.bookCount': { one: '{count} book', other: '{count} books' },
      'library.tagCount': { one: '{count} tag', other: '{count} tags' },
      'library.annotations': 'Annotations',
      'library.login': 'Login',
      'library.theme': 'Theme',
      'library.searchPlaceholder': 'Search by book title, author, or tag...',
      'library.all': 'All',
      'library.noTag': 'No tag',
      'library.top': 'Top',
      'library.shelf': 'Shelf',
      'library.cover': 'Cover',
      'library.usernamePrompt': 'Please enter your username:',
      'library.usernameSaved': 'Username saved: {username}',
      'library.usernameCleared': 'Username cleared',
      'library.install': 'Install',
      'library.installing': 'Installing app...',
      'library.installSucceeded': 'App installed successfully!',
      'library.installCancelled': 'Install cancelled',
      'library.loading': 'Loading library',
      'library.empty': 'No books in your library yet.',
      'library.loadError': 'Unable to load your library. Please refresh and try again.',
      'library.progress.scanning': 'Scanning library',
      'library.progress.processing': 'Updating library',
      'library.progress.complete': 'Library updated',
      'library.progress.degraded': 'Library updated with failures',
      'library.progress.reconnecting': 'Reconnecting to library updates…',
      'library.progress.summary': 'Processed {completed} of {total} books',
      'library.progress.removed': { one: 'Removed {count} book', other: 'Removed {count} books' },
      'library.progress.latest': 'Latest: {book}',
      'library.progress.failureDetails': 'Failure details',
      'library.progress.close': 'Close',
      'account.menu': 'Account',
      'account.title': 'Account settings',
      'account.close': 'Close account settings',
      'account.profile': 'Profile',
      'account.signIn': 'Sign in',
      'account.loginPageTitle': 'Sign in · EPUB Browser',
      'account.loginDescription': 'Sign in to continue to your personal library.',
      'account.setupPageTitle': 'Create administrator · EPUB Browser',
      'account.setupTitle': 'Create your administrator account',
      'account.setupDescription': 'When you first access the web interface, you will be prompted to create a superuser account.',
      'account.confirmPassword': 'Confirm password',
      'account.createSuperuser': 'Create superuser',
      'account.signedInAs': 'Signed in as {username} · {role}',
      'account.role.admin': 'Administrator',
      'account.role.member': 'Member',
      'account.username': 'Username',
      'account.password': 'Password',
      'account.logout': 'Sign out',
      'account.changePassword': 'Change password',
      'account.currentPassword': 'Current password',
      'account.newPassword': 'New password',
      'account.savePassword': 'Save password',
      'account.passwordChanged': 'Password changed. Sign in again to continue.',
      'account.sessions': 'Active sessions',
      'account.sessionDescription': 'Created {created}; last used {lastUsed}',
      'account.currentSession': 'Current session',
      'account.revokeSession': 'Revoke session',
      'account.sessionRevoked': 'Session revoked.',
      'account.noSessions': 'No active sessions.',
      'account.associationTitle': 'Associate a proxy identity',
      'account.associationDescription': 'If your trusted proxy identity is not recognized, prove which local account it belongs to.',
      'account.associate': 'Associate identity',
      'account.associationSucceeded': 'Proxy identity associated.',
      'account.error.authentication_required': 'Your session has ended. Sign in again.',
      'account.error.csrf_required': 'The security token expired. Reload and try again.',
      'account.error.forbidden': 'This account is not allowed to perform that action.',
      'account.error.invalid_credentials': 'The username or password is incorrect.',
      'account.error.invalid_password': 'Enter a valid password.',
      'account.error.invalidSetup': 'Enter a username, password, and password confirmation.',
      'account.error.passwordMismatch': 'The passwords do not match.',
      'account.error.username_unavailable': 'That username is unavailable.',
      'account.error.proxy_identity_required': 'No unrecognized trusted proxy identity is available to associate.',
      'account.error.identity_already_linked': 'This proxy identity is already associated.',
      'account.error.not_found': 'The requested account item was not found.',
      'account.error.network': 'Unable to reach the account service.',
      'account.error.unknown': 'The account request could not be completed.',
      'admin.title': 'Administration',
      'admin.users': 'Users',
      'admin.books': 'Book access',
      'admin.role': 'Role',
      'admin.createUser': 'Create user',
      'admin.identities': 'Proxy identities',
      'admin.identityIssuer': 'Issuer',
      'admin.identitySubject': 'Subject',
      'admin.identityDisplayName': 'Display name',
      'admin.identityUser': 'Local user',
      'admin.createIdentity': 'Create identity',
      'admin.deleteIdentity': 'Delete identity',
      'admin.identityCreated': 'Proxy identity created.',
      'admin.identityDeleted': 'Proxy identity deleted.',
      'admin.identitySummary': '{displayName} · {issuer} · {subject} · {username}',
      'admin.noIdentities': 'No proxy identities are linked.',
      'admin.userCreated': 'User created.',
      'admin.userUpdated': 'User updated.',
      'admin.userSummary': '{username} · {role} · {status}',
      'admin.enabled': 'Enabled',
      'admin.disabled': 'Disabled',
      'admin.enableUser': 'Enable',
      'admin.disableUser': 'Disable',
      'admin.makeAdmin': 'Make administrator',
      'admin.makeMember': 'Make member',
      'admin.revokeSessions': 'Revoke all sessions',
      'admin.newPassword': 'New password',
      'admin.resetPassword': 'Reset password',
      'admin.passwordReset': 'Password reset and sessions revoked.',
      'admin.restrictedBook': 'Restricted books are visible only to administrators and explicitly granted users.',
      'admin.visibility.authenticated': 'All signed-in users',
      'admin.visibility.restricted': 'Restricted',
      'admin.bookVisibility': 'Book visibility',
      'admin.bookUpdated': 'Book visibility updated.',
      'admin.grantUser': 'User to grant',
      'admin.grantBook': 'Grant access',
      'admin.revokeBook': 'Revoke access',
      'admin.revokeBookFor': 'Revoke {username} access to {book}',
      'admin.bookGranted': 'Book access granted.',
      'admin.bookRevoked': 'Book access revoked.',
      'admin.noBooks': 'No books are available to administer.',
      'admin.error.invalid_user': 'Enter valid user details.',
      'admin.error.username_unavailable': 'That username is unavailable.',
      'admin.error.invalid_password': 'Enter a valid password.',
      'admin.error.last_enabled_admin': 'The last enabled administrator cannot be disabled or demoted.',
      'admin.error.not_found': 'The requested user or book was not found.',
      'admin.error.invalid_visibility': 'Choose a valid book visibility.',
      'admin.error.invalid_identity': 'Enter valid proxy identity details.',
      'admin.error.identity_already_linked': 'That proxy identity is already linked.',
      'admin.error.user_disabled': 'Enable this user before granting book access.',
      'admin.error.forbidden': 'Administrator access is required.',
      'admin.error.csrf_required': 'The security token expired. Reload and try again.',
      'admin.error.network': 'Unable to reach the administration service.',
      'admin.error.unknown': 'The administration request could not be completed.',
      'book.library': 'Library',
      'book.breadcrumb': 'Breadcrumb',
      'book.theme': 'Theme',
      'book.unknownAuthor': 'Unknown author',
      'book.startReading': 'Start reading',
      'book.continueReading': 'Continue reading',
      'book.moreReadingActions': 'More reading actions',
      'book.clearReadingProgress': 'Clear reading progress',
      'book.clear': 'Clear',
      'book.clearReadingProgressConfirm': 'Clear reading progress for this book?',
      'book.clearReadingProgressSucceeded': 'All reading progress for this book has been deleted!',
      'book.clearReadingProgressFailed': 'Unable to clear reading progress. Please try again.',
      'book.annotations': 'Annotations',
      'book.addToShelf': 'Add to Shelf',
      'book.removeFromShelf': 'Remove from Shelf',
      'book.addedToShelf': 'Book added to shelf!',
      'book.removedFromShelf': 'Book removed from shelf!',
      'book.tableOfContents': 'Table of contents',
      'book.totalChapters': 'Total: {count}',
      'book.top': 'Top',
      'book.shelf': 'Shelf',
      'book.home': 'Home',
      'book.cover': 'Cover',
      'book.cloudSyncUser': 'Cloud sync · {username}',
      'book.cloudSyncUserAria': 'Cloud-synced reading position for {username}',
      'book.sharedUser': 'shared',
      'book.addToShelfTitle': 'Add to Shelf',
      'book.closeGroupChooser': 'Close group chooser',
      'book.shelfHome': 'Shelf Home',
      'book.confirm': 'Confirm',
      'book.error.database_unavailable': 'The reading progress service is temporarily unavailable.',
      'book.error.server_error': 'The reading progress service encountered an error.',
      'book.error.not_found': 'The reading progress service was not found.',
      'bookshelf.addGroup': 'Add Group',
      'bookshelf.sync': 'Sync',
      'bookshelf.export': 'Export',
      'bookshelf.import': 'Import',
      'bookshelf.title': 'Bookshelf',
      'bookshelf.group': 'Group',
      'bookshelf.addBook': 'Add Book',
      'bookshelf.searchBooks': 'Search books',
      'bookshelf.searchPlaceholder': 'Search by title or author',
      'bookshelf.searchNoResults': 'No books match “{query}”.',
      'bookshelf.noBooksToAdd': 'Every available book is already on your bookshelf.',
      'bookshelf.removeBook': 'Remove “{title}”',
      'bookshelf.confirmRemoveBook': 'Remove “{title}” from this location?',
      'bookshelf.bookAdded': 'Added “{title}”.',
      'bookshelf.bookRemoved': 'Removed “{title}”.',
      'bookshelf.bookAlreadyAdded': 'This book is already on your bookshelf.',
      'bookshelf.rename': 'Rename',
      'bookshelf.deleteGroup': 'Delete Group',
      'bookshelf.close': 'Close',
      'bookshelf.home': 'Back to bookshelf',
      'bookshelf.loading': 'Loading bookshelf',
      'bookshelf.all': 'All',
      'bookshelf.noTag': 'No tag',
      'bookshelf.empty': 'Your bookshelf is empty',
      'bookshelf.groupEmpty': 'This group is empty',
      'bookshelf.groupItems': '{books} books, {groups} subgroups',
      'bookshelf.groupBooks': '{books} books',
      'bookshelf.groupSubgroups': '{groups} subgroups',
      'bookshelf.emptyGroup': 'Empty group',
      'bookshelf.currentStats': 'Current: {books} book(s), {groups} group(s) | Total: {totalBooks} book(s), {totalGroups} group(s)',
      'bookshelf.groupNamePrompt': 'Enter group name:',
      'bookshelf.renameGroupPrompt': 'Enter new group name:',
      'bookshelf.confirmDeleteGroup': 'Are you sure you want to delete the group "{name}"?',
      'bookshelf.groupDeleted': 'Deleted group "{name}".',
      'bookshelf.nestedGroupWarning': 'Please delete all nested groups first before deleting this group.',
      'bookshelf.importSucceeded': 'Bookshelf data imported successfully!',
      'bookshelf.importInvalid': 'Invalid bookshelf data format.',
      'bookshelf.importParseFailed': 'Failed to parse the JSON file.',
      'bookshelf.usernamePrompt': 'Please enter your username for sync:',
      'bookshelf.loginRequired': 'Please log in before using your cloud bookshelf.',
      'bookshelf.syncing': 'Syncing...',
      'bookshelf.syncNewUser': 'Sync ({username}): New user created, data uploaded successfully!',
      'bookshelf.syncUpdated': 'Sync ({username}): Data updated from server!',
      'bookshelf.syncCurrent': 'Sync ({username}): No changes, already up to date!',
      'bookshelf.syncUnavailable': 'Sync ({username}): Not allowed to sync, check your configuration!',
      'bookshelf.syncUploaded': 'Sync ({username}): Data uploaded successfully!',
      'bookshelf.syncFailed': 'Sync ({username}) failed. Please try again.',
      'bookshelf.error.username_required': 'A username is required to sync your bookshelf.',
      'bookshelf.error.invalid_json': 'The sync request was invalid.',
      'bookshelf.error.no_sync_data': 'No bookshelf data was provided for sync.',
      'bookshelf.error.not_found': 'The sync endpoint was not found.',
      'bookshelf.error.annotation_not_found': 'The requested item was not found.',
      'bookshelf.error.invalid_chapter_index': 'The requested chapter is invalid.',
      'bookshelf.error.batch_requires_post': 'This request must use POST.',
      'bookshelf.error.database_unavailable': 'The sync service is temporarily unavailable.',
      'bookshelf.error.reading_progress_not_found': 'Reading progress was not found.',
      'bookshelf.error.server_error': 'The sync service encountered an error.',
      'bookshelf.error.unknown': 'The bookshelf could not be synchronized.',
      'dialog.title': 'Confirm',
      'dialog.confirm': 'Confirm',
      'dialog.cancel': 'Cancel',
      'dialog.value': 'Value',
      'annotations.tab': 'Annotations',
      'annotations.enabled': 'Enable annotations',
      'annotations.enabledNotice': 'Annotations enabled',
      'annotations.disabledNotice': 'Annotations disabled',
      'annotations.storageLocation': 'Storage location',
      'annotations.localStorage': 'Local storage',
      'annotations.cloudStorage': 'Cloud storage',
      'annotations.cloudUnavailable': 'Cloud storage is unavailable',
      'annotations.checking': 'Checking…',
      'annotations.connectedUser': 'Connected ({username})',
      'annotations.connectedShared': 'Connected (shared)',
      'annotations.connectedAccount': 'Connected to your account',
      'annotations.disconnected': 'Disconnected',
      'annotations.usernamePrompt': 'You are not logged in.\n\n- Click OK to enter a username (annotations will be isolated by user)\n- Click Cancel to use shared mode (all users share the same annotations)',
      'annotations.login': 'Sign in',
      'annotations.username': 'Username',
      'annotations.usingSharedStorage': 'Using shared cloud storage (no user isolation)',
      'annotations.loggedInAs': 'Logged in as {username} (annotations isolated)',
      'annotations.defaultColor': 'Default color',
      'annotations.defaultColorTip': 'Click a color to set it as the default.',
      'annotations.colors': 'Colors',
      'annotations.colorReorderTip': 'Drag colors to reorder them.',
      'annotations.addColor': 'Add color',
      'annotations.deleteColor': 'Delete color',
      'annotations.hexColor': 'Hex color',
      'annotations.hexPlaceholder': '#RRGGBB',
      'annotations.invalidHex': 'Enter a valid hex color such as #RRGGBB.',
      'annotations.noteOptional': 'Note (optional)…',
      'annotations.note': 'Note:',
      'annotations.addDescription': 'Add description…',
      'annotations.add': 'Add',
      'annotations.save': 'Save',
      'annotations.cancel': 'Cancel',
      'annotations.close': 'Close',
      'annotations.copy': 'Copy',
      'annotations.delete': 'Delete',
      'annotations.details': 'Annotation details',
      'annotations.color': 'Color:',
      'annotations.created': 'Created: {date}',
      'annotations.updated': 'Updated: {date}',
      'annotations.clickToCopy': 'Click to copy',
      'annotations.copied': 'Copied',
      'annotations.textCopied': 'Text copied',
      'annotations.unableToCopy': 'Unable to copy',
      'annotations.notFound': 'Annotation not found',
      'annotations.confirmDelete': 'Delete this annotation?',
      'annotations.loadFailed': 'Failed to load annotation: {error}',
      'annotations.addFailed': 'Failed to add: {error}',
      'annotations.updateFailed': 'Failed to update: {error}',
      'annotations.deleteFailed': 'Failed to delete: {error}',
      'annotations.restoreFailed': 'Some annotations could not be restored. Please reload the chapter.',
      'annotations.loadAllFailed': 'Failed to load annotations: {error}',
      'annotations.dataMigration': 'Data migration',
      'annotations.migrationDescription': 'Switching storage location requires data migration',
      'annotations.countingData': 'Counting data…',
      'annotations.currentData': { one: 'Current data: {count} annotation', other: 'Current data: {count} annotations' },
      'annotations.skip': 'Skip',
      'annotations.migrate': 'Migrate',
      'annotations.migrating': 'Migrating…',
      'annotations.migratingProgress': 'Migrating… {current}/{total}',
      'annotations.storageLocationChanged': 'Storage location changed',
      'annotations.exportData': 'Export data',
      'annotations.exportBook': 'Export book',
      'annotations.exportAll': 'Export all',
      'annotations.exported': { one: 'Exported {count} annotation', other: 'Exported {count} annotations' },
      'annotations.exportFailed': 'Export failed: {error}',
      'annotations.hubTitle': 'Annotations',
      'annotations.allAnnotatedBooks': 'All annotated books',
      'annotations.closeHub': 'Close annotations',
      'annotations.loading': 'Loading annotations…',
      'annotations.retry': 'Retry',
      'annotations.loadHubFailed': 'Unable to load annotations',
      'annotations.loadHubFailedDetail': 'Please try again.',
      'annotations.annotatedBooks': 'Annotated books',
      'annotations.noAnnotationsTitle': 'No annotations yet',
      'annotations.noAnnotationsDescription': 'Select text while reading to save your first annotation.',
      'annotations.noBookAnnotationsTitle': 'No annotations in this book',
      'annotations.noBookAnnotationsDescription': 'This book may have been removed or its annotations were deleted.',
      'annotations.annotationCount': { one: '{count} annotation', other: '{count} annotations' },
      'annotations.bookCount': { one: '{count} book', other: '{count} books' },
      'annotations.updatedAt': 'Updated {date}',
      'annotations.chapterNumber': 'Chapter {number}',
      'annotations.bookFallback': 'Book',
      'annotations.authorSeparator': ' & ',
      'annotations.bylineSeparator': ' · ',
      'annotations.error.not_found': 'The annotation service was not found.',
      'annotations.error.username_required': 'A username is required for this annotation request.',
      'annotations.error.invalid_json': 'The annotation request was invalid.',
      'annotations.error.no_sync_data': 'No annotation data was provided.',
      'annotations.error.annotation_not_found': 'The annotation was not found.',
      'annotations.error.invalid_chapter_index': 'The requested chapter is invalid.',
      'annotations.error.batch_requires_post': 'This batch request must use POST.',
      'annotations.error.database_unavailable': 'The annotation service is temporarily unavailable.',
      'annotations.error.reading_progress_not_found': 'Reading progress was not found.',
      'annotations.error.server_error': 'The annotation service encountered an error.',
      'annotations.error.network': 'A network error occurred while contacting annotations.',
      'annotations.error.timeout': 'The annotation request timed out.',
      'footer.product': 'EPUB Library',
      'footer.poweredBy': 'Powered by',
      'footer.poweredBySuffix': '·',
      'version.updateAvailable': 'Update available: v{version}',
      'errors.generic': 'Something went wrong.',
      'errors.network': 'A network error occurred.'
    },
    'zh-CN': {
      'common.language': '语言',
      'common.chinese': '中文',
      'common.english': 'English',
      'common.version': '版本 {version}',
      'theme.light': '浅色',
      'theme.dark': '深色',
      'theme.sepia': '棕褐色',
      'theme.forest': '森林',
      'theme.ocean': '海洋',
      'theme.peach': '蜜桃',
      'theme.lavender': '薰衣草',
      'reader.library': '书库',
      'reader.breadcrumb': '导航路径',
      'reader.theme': '主题',
      'reader.turning': '翻页',
      'reader.scrolling': '滚动',
      'reader.book': '书籍',
      'reader.home': '主页',
      'reader.top': '顶部',
      'reader.settings': '设置',
      'reader.shelf': '书架',
      'reader.tableOfContents': '目录',
      'reader.bookChapters': '章节',
      'reader.thisChapterContents': '本章目录',
      'reader.openBookChapters': '打开章节目录',
      'reader.skipToContent': '跳到阅读正文',
      'reader.previous': '上一章',
      'reader.next': '下一章',
      'reader.previousPage': '上一页',
      'reader.nextPage': '下一页',
      'reader.currentPage': '当前页',
      'reader.totalPages': '总页数',
      'reader.jump': '跳转',
      'reader.clickToTurn': '点击翻页',
      'reader.pureReading': '纯净阅读模式',
      'reader.reloadPages': '重新加载分页',
      'reader.setPageHeight': '设置页面高度',
      'reader.loadingContent': '正在加载内容',
      'reader.openBookHome': '打开书籍首页',
      'reader.closeBookHome': '关闭书籍首页',
      'reader.closeSettings': '关闭设置',
      'reader.closeTableOfContents': '关闭目录',
      'reader.pageHeight': '页面高度',
      'reader.turningModeEnabled': '已启用翻页模式',
      'reader.exitTurningConfirm': '要退出翻页模式吗？',
      'reader.exitTurning': '退出翻页模式',
      'reader.progressLoadedPage': '已加载阅读进度：第 {page} 页',
      'reader.progressLoadedPercent': '已加载阅读进度：{percent}%',
      'reader.pageRange': '1-{total}',
      'reader.validNumber': '请输入有效数字',
      'reader.firstChapter': '已是第一章',
      'reader.lastChapter': '已是最后一章',
      'reader.first': '已到开头',
      'reader.last': '已到结尾',
      'reader.onlyPageMode': '仅在翻页模式下可用',
      'reader.pureModeOn': '已开启纯净阅读模式',
      'reader.pureModeOff': '已关闭纯净阅读模式',
      'reader.reloaded': '已重新加载',
      'reader.clickPageOn': '已启用点击翻页',
      'reader.clickPageOff': '已关闭点击翻页',
      'reader.tocLoadFailed': '加载失败',
      'reader.tocNoTitle': '无标题',
      'reader.annotationNotFound': '无法定位此标注，已打开其所在章节。',
      'reader.annotationLoadFailed': '无法加载此标注，已打开其所在章节。',
      'reader.loadingNextChapter': '正在加载下一章',
      'reader.loadingPreviousChapter': '正在加载上一章',
      'reader.chapterNumber': '第 {number} 章',
      'reader.continuousScrollRequiresScrolling': '连续滚动需要使用滚动模式',
      'reader.continuousScrollEnabledReloading': '已启用连续滚动，正在重新加载…',
      'reader.continuousScrollDisabledReloading': '已关闭连续滚动，正在重新加载…',
      'settings.appearance': '外观',
      'settings.reading': '阅读',
      'settings.fontFamily': '字体',
      'settings.fontSize': '字号',
      'settings.bookDefault': '书籍默认',
      'settings.systemDefault': '系统默认',
      'settings.customByInput': '手动输入自定义字体',
      'settings.customFontPlaceholder': '请输入字体名称',
      'settings.customFontTip': '提示：字体会全局生效，请确保该字体已安装在系统中。',
      'settings.apply': '应用',
      'settings.readingMode': '阅读模式',
      'settings.showReadingProgressBar': '显示阅读进度条',
      'settings.desktopChapterSidebar': '在桌面端显示章节侧栏',
      'settings.continuousScroll': '启用连续滚动',
      'settings.continuousScrollTip': '滚动到结尾时会自动加载下一章。注意：启用后不会保存或恢复滚动进度。关闭时可按空格键获得类似的连续阅读体验。',
      'settings.customStyles': '自定义样式',
      'settings.optional': '可选',
      'settings.customStylesDescription': '使用 CSS 微调本书的排版与布局。',
      'settings.customCssPlaceholder': '请输入 CSS 代码……例如：#eb-content-container{background: inherit; box-shadow:inherit;} #eb-content{margin: 50px; width: auto} #eb-content p {margin-bottom: 0.8rem; line-height: 1.7;}',
      'settings.save': '保存',
      'settings.saveAsDefault': '另存为默认样式',
      'settings.reset': '重置',
      'settings.loadDefault': '加载默认样式',
      'settings.preview': '预览',
      'settings.defaultStyleTip': '提示：除非为特定书籍设置自定义样式，否则默认样式会应用于所有书籍。',
      'settings.saved': '已保存',
      'settings.defaultSaved': '默认样式已保存',
      'settings.noDefault': '没有默认样式',
      'settings.loaded': '已加载',
      'settings.resetDone': '已重置',
      'settings.applied': '已应用',
      'settings.saveAsDefaultConfirm': '要另存为默认样式吗？',
      'settings.loadDefaultConfirm': '要加载默认样式吗？',
      'settings.resetConfirm': '要重置吗？',
      'settings.continuousScrollUnavailable': '连续滚动仅在滚动模式下可用。请先切换到滚动模式再启用此功能。',
      'library.title': '书库',
      'library.pageTitle': 'EPUB 书库',
      'library.description': 'EPUB 书库 - 基于网页的 EPUB 阅读器',
      'library.information': '书库信息',
      'library.bookCount': '共 {count} 本书',
      'library.tagCount': '共 {count} 个标签',
      'library.annotations': '标注',
      'library.login': '登录',
      'library.theme': '主题',
      'library.searchPlaceholder': '按书名、作者或标签搜索…',
      'library.all': '全部',
      'library.noTag': '无标签',
      'library.top': '顶部',
      'library.shelf': '书架',
      'library.cover': '封面',
      'library.usernamePrompt': '请输入你的用户名：',
      'library.usernameSaved': '用户名已保存：{username}',
      'library.usernameCleared': '用户名已清除',
      'library.install': '安装',
      'library.installing': '正在安装应用…',
      'library.installSucceeded': '应用安装成功！',
      'library.installCancelled': '已取消安装',
      'library.loading': '正在加载书库',
      'library.progress.scanning': '正在扫描书库',
      'library.progress.processing': '正在更新书库',
      'library.progress.complete': '书库已更新',
      'library.progress.degraded': '书库更新时出现失败',
      'library.progress.reconnecting': '正在重新连接书库更新…',
      'library.progress.summary': '已处理 {completed} / {total} 本图书',
      'library.progress.removed': '已移除 {count} 本图书',
      'library.progress.latest': '最新：{book}',
      'library.progress.failureDetails': '失败详情',
      'library.progress.close': '关闭',
      'library.empty': '书库中还没有书籍。',
      'library.loadError': '无法加载书库，请刷新后重试。',
      'account.menu': '账户',
      'account.title': '账户设置',
      'account.close': '关闭账户设置',
      'account.profile': '个人资料',
      'account.signIn': '登录',
      'account.loginPageTitle': '登录 · EPUB Browser',
      'account.loginDescription': '登录后继续进入你的个人书库。',
      'account.setupPageTitle': '创建管理员 · EPUB Browser',
      'account.setupTitle': '创建管理员账户',
      'account.setupDescription': '首次访问 Web 界面时，系统将提示您创建一个超级用户账户。',
      'account.confirmPassword': '确认密码',
      'account.createSuperuser': '创建超级用户',
      'account.signedInAs': '已登录为 {username} · {role}',
      'account.role.admin': '管理员',
      'account.role.member': '成员',
      'account.username': '用户名',
      'account.password': '密码',
      'account.logout': '退出登录',
      'account.changePassword': '修改密码',
      'account.currentPassword': '当前密码',
      'account.newPassword': '新密码',
      'account.savePassword': '保存密码',
      'account.passwordChanged': '密码已修改，请重新登录后继续。',
      'account.sessions': '活跃会话',
      'account.sessionDescription': '创建于 {created}；最近使用于 {lastUsed}',
      'account.currentSession': '当前会话',
      'account.revokeSession': '撤销会话',
      'account.sessionRevoked': '会话已撤销。',
      'account.noSessions': '没有活跃会话。',
      'account.associationTitle': '关联代理身份',
      'account.associationDescription': '如果可信代理身份尚未被识别，请验证它所属的本地账户。',
      'account.associate': '关联身份',
      'account.associationSucceeded': '代理身份已关联。',
      'account.error.authentication_required': '会话已结束，请重新登录。',
      'account.error.csrf_required': '安全令牌已过期，请重新加载后再试。',
      'account.error.forbidden': '此账户无权执行该操作。',
      'account.error.invalid_credentials': '用户名或密码不正确。',
      'account.error.invalid_password': '请输入有效密码。',
      'account.error.invalidSetup': '请输入用户名、密码和确认密码。',
      'account.error.passwordMismatch': '两次输入的密码不一致。',
      'account.error.username_unavailable': '该用户名不可用。',
      'account.error.proxy_identity_required': '当前没有可关联的未识别可信代理身份。',
      'account.error.identity_already_linked': '此代理身份已关联。',
      'account.error.not_found': '未找到账户项目。',
      'account.error.network': '无法连接账户服务。',
      'account.error.unknown': '无法完成账户请求。',
      'admin.title': '管理',
      'admin.users': '用户',
      'admin.books': '书籍访问权限',
      'admin.role': '角色',
      'admin.createUser': '创建用户',
      'admin.identities': '代理身份',
      'admin.identityIssuer': '签发者',
      'admin.identitySubject': '主体',
      'admin.identityDisplayName': '显示名称',
      'admin.identityUser': '本地用户',
      'admin.createIdentity': '创建身份',
      'admin.deleteIdentity': '删除身份',
      'admin.identityCreated': '代理身份已创建。',
      'admin.identityDeleted': '代理身份已删除。',
      'admin.identitySummary': '{displayName} · {issuer} · {subject} · {username}',
      'admin.noIdentities': '尚未关联代理身份。',
      'admin.userCreated': '用户已创建。',
      'admin.userUpdated': '用户已更新。',
      'admin.userSummary': '{username} · {role} · {status}',
      'admin.enabled': '已启用',
      'admin.disabled': '已禁用',
      'admin.enableUser': '启用',
      'admin.disableUser': '禁用',
      'admin.makeAdmin': '设为管理员',
      'admin.makeMember': '设为成员',
      'admin.revokeSessions': '撤销全部会话',
      'admin.newPassword': '新密码',
      'admin.resetPassword': '重置密码',
      'admin.passwordReset': '密码已重置，会话已撤销。',
      'admin.restrictedBook': '受限书籍仅对管理员及明确授权的用户可见。',
      'admin.visibility.authenticated': '所有已登录用户',
      'admin.visibility.restricted': '受限',
      'admin.bookVisibility': '书籍可见范围',
      'admin.bookUpdated': '书籍可见范围已更新。',
      'admin.grantUser': '要授权的用户',
      'admin.grantBook': '授予访问权限',
      'admin.revokeBook': '撤销访问权限',
      'admin.revokeBookFor': '撤销 {username} 对《{book}》的访问权限',
      'admin.bookGranted': '已授予书籍访问权限。',
      'admin.bookRevoked': '已撤销书籍访问权限。',
      'admin.noBooks': '没有可管理的书籍。',
      'admin.error.invalid_user': '请输入有效的用户信息。',
      'admin.error.username_unavailable': '该用户名不可用。',
      'admin.error.invalid_password': '请输入有效密码。',
      'admin.error.last_enabled_admin': '不能禁用最后一个已启用的管理员或将其降级。',
      'admin.error.not_found': '未找到请求的用户或书籍。',
      'admin.error.invalid_visibility': '请选择有效的书籍可见范围。',
      'admin.error.invalid_identity': '请输入有效的代理身份信息。',
      'admin.error.identity_already_linked': '该代理身份已关联。',
      'admin.error.user_disabled': '请先启用此用户，再授予书籍访问权限。',
      'admin.error.forbidden': '需要管理员权限。',
      'admin.error.csrf_required': '安全令牌已过期，请重新加载后再试。',
      'admin.error.network': '无法连接管理服务。',
      'admin.error.unknown': '无法完成管理请求。',
      'book.library': '书库',
      'book.breadcrumb': '导航路径',
      'book.theme': '主题',
      'book.unknownAuthor': '未知作者',
      'book.startReading': '开始阅读',
      'book.continueReading': '继续阅读',
      'book.moreReadingActions': '更多阅读操作',
      'book.clearReadingProgress': '清除阅读进度',
      'book.clear': '清除',
      'book.clearReadingProgressConfirm': '要清除此书的阅读进度吗？',
      'book.clearReadingProgressSucceeded': '已清除此书的全部阅读进度！',
      'book.clearReadingProgressFailed': '无法清除阅读进度，请重试。',
      'book.annotations': '标注',
      'book.addToShelf': '加入书架',
      'book.removeFromShelf': '从书架移除',
      'book.addedToShelf': '书籍已加入书架！',
      'book.removedFromShelf': '书籍已从书架移除！',
      'book.tableOfContents': '目录',
      'book.totalChapters': '共 {count} 章',
      'book.top': '顶部',
      'book.shelf': '书架',
      'book.home': '主页',
      'book.cover': '封面',
      'book.cloudSyncUser': '云端同步 · {username}',
      'book.cloudSyncUserAria': '{username} 的云端同步阅读位置',
      'book.sharedUser': '共享用户',
      'book.addToShelfTitle': '加入书架',
      'book.closeGroupChooser': '关闭分组选择器',
      'book.shelfHome': '书架首页',
      'book.confirm': '确认',
      'book.error.database_unavailable': '阅读进度服务暂时不可用。',
      'book.error.server_error': '阅读进度服务发生错误。',
      'book.error.not_found': '未找到阅读进度服务。',
      'bookshelf.addGroup': '添加分组',
      'bookshelf.sync': '同步',
      'bookshelf.export': '导出',
      'bookshelf.import': '导入',
      'bookshelf.title': '书架',
      'bookshelf.group': '分组',
      'bookshelf.addBook': '添加书籍',
      'bookshelf.searchBooks': '搜索书籍',
      'bookshelf.searchPlaceholder': '按书名或作者搜索',
      'bookshelf.searchNoResults': '没有与“{query}”匹配的书籍。',
      'bookshelf.noBooksToAdd': '可用书籍都已在书架中。',
      'bookshelf.removeBook': '移除“{title}”',
      'bookshelf.confirmRemoveBook': '要从当前位置移除“{title}”吗？',
      'bookshelf.bookAdded': '已添加“{title}”。',
      'bookshelf.bookRemoved': '已移除“{title}”。',
      'bookshelf.bookAlreadyAdded': '这本书已在书架中。',
      'bookshelf.rename': '重命名',
      'bookshelf.deleteGroup': '删除分组',
      'bookshelf.close': '关闭',
      'bookshelf.home': '返回书架',
      'bookshelf.loading': '正在加载书架',
      'bookshelf.all': '全部',
      'bookshelf.noTag': '无标签',
      'bookshelf.empty': '书架中还没有内容',
      'bookshelf.groupEmpty': '此分组中还没有内容',
      'bookshelf.groupItems': '{books} 本书，{groups} 个子分组',
      'bookshelf.groupBooks': '{books} 本书',
      'bookshelf.groupSubgroups': '{groups} 个子分组',
      'bookshelf.emptyGroup': '空分组',
      'bookshelf.currentStats': '当前：{books} 本书、{groups} 个分组｜总计：{totalBooks} 本书、{totalGroups} 个分组',
      'bookshelf.groupNamePrompt': '请输入分组名称：',
      'bookshelf.renameGroupPrompt': '请输入新的分组名称：',
      'bookshelf.confirmDeleteGroup': '确定要删除分组“{name}”吗？',
      'bookshelf.groupDeleted': '已删除分组“{name}”。',
      'bookshelf.nestedGroupWarning': '请先删除此分组中的所有嵌套分组。',
      'bookshelf.importSucceeded': '书架数据导入成功！',
      'bookshelf.importInvalid': '书架数据格式无效。',
      'bookshelf.importParseFailed': '无法解析 JSON 文件。',
      'bookshelf.usernamePrompt': '请输入用于同步的用户名：',
      'bookshelf.loginRequired': '请先登录后再使用云端书架。',
      'bookshelf.syncing': '正在同步…',
      'bookshelf.syncNewUser': '同步（{username}）：已创建用户并上传数据！',
      'bookshelf.syncUpdated': '同步（{username}）：已从服务器更新数据！',
      'bookshelf.syncCurrent': '同步（{username}）：没有变更，已是最新状态！',
      'bookshelf.syncUnavailable': '同步（{username}）：不允许同步，请检查配置！',
      'bookshelf.syncUploaded': '同步（{username}）：数据上传成功！',
      'bookshelf.syncFailed': '同步（{username}）失败，请重试。',
      'bookshelf.error.username_required': '同步书架需要用户名。',
      'bookshelf.error.invalid_json': '同步请求无效。',
      'bookshelf.error.no_sync_data': '同步时未提供书架数据。',
      'bookshelf.error.not_found': '未找到同步服务。',
      'bookshelf.error.annotation_not_found': '未找到请求的项目。',
      'bookshelf.error.invalid_chapter_index': '请求的章节无效。',
      'bookshelf.error.batch_requires_post': '此请求必须使用 POST。',
      'bookshelf.error.database_unavailable': '同步服务暂时不可用。',
      'bookshelf.error.reading_progress_not_found': '未找到阅读进度。',
      'bookshelf.error.server_error': '同步服务发生错误。',
      'bookshelf.error.unknown': '无法同步书架。',
      'dialog.title': '确认操作',
      'dialog.confirm': '确认',
      'dialog.cancel': '取消',
      'dialog.value': '内容',
      'annotations.tab': '标注',
      'annotations.enabled': '启用标注',
      'annotations.enabledNotice': '已启用标注',
      'annotations.disabledNotice': '已禁用标注',
      'annotations.storageLocation': '存储位置',
      'annotations.localStorage': '本地存储',
      'annotations.cloudStorage': '云端存储',
      'annotations.cloudUnavailable': '云端存储不可用',
      'annotations.checking': '正在检查…',
      'annotations.connectedUser': '已连接（{username}）',
      'annotations.connectedShared': '已连接（共享）',
      'annotations.connectedAccount': '已连接到账户',
      'annotations.disconnected': '未连接',
      'annotations.usernamePrompt': '你尚未登录。\n\n- 点击“确定”输入用户名（标注会按用户隔离）\n- 点击“取消”使用共享模式（所有用户共享标注）',
      'annotations.login': '登录',
      'annotations.username': '用户名',
      'annotations.usingSharedStorage': '正在使用共享云端存储（不按用户隔离）',
      'annotations.loggedInAs': '已登录为 {username}（标注按用户隔离）',
      'annotations.defaultColor': '默认颜色',
      'annotations.defaultColorTip': '点击颜色即可设为默认颜色。',
      'annotations.colors': '颜色',
      'annotations.colorReorderTip': '拖动颜色可调整顺序。',
      'annotations.addColor': '添加颜色',
      'annotations.deleteColor': '删除颜色',
      'annotations.hexColor': '十六进制颜色',
      'annotations.hexPlaceholder': '#RRGGBB',
      'annotations.invalidHex': '请输入有效的十六进制颜色，例如 #RRGGBB。',
      'annotations.noteOptional': '笔记（可选）…',
      'annotations.note': '笔记：',
      'annotations.addDescription': '添加说明…',
      'annotations.add': '添加',
      'annotations.save': '保存',
      'annotations.cancel': '取消',
      'annotations.close': '关闭',
      'annotations.copy': '复制',
      'annotations.delete': '删除',
      'annotations.details': '标注详情',
      'annotations.color': '颜色：',
      'annotations.created': '创建时间：{date}',
      'annotations.updated': '更新时间：{date}',
      'annotations.clickToCopy': '点击复制',
      'annotations.copied': '已复制',
      'annotations.textCopied': '文本已复制',
      'annotations.unableToCopy': '无法复制',
      'annotations.notFound': '未找到标注',
      'annotations.confirmDelete': '要删除此标注吗？',
      'annotations.loadFailed': '加载标注失败：{error}',
      'annotations.addFailed': '添加失败：{error}',
      'annotations.updateFailed': '更新失败：{error}',
      'annotations.deleteFailed': '删除失败：{error}',
      'annotations.restoreFailed': '部分标注无法恢复，请重新加载本章。',
      'annotations.loadAllFailed': '加载标注失败：{error}',
      'annotations.dataMigration': '数据迁移',
      'annotations.migrationDescription': '切换存储位置需要迁移数据',
      'annotations.countingData': '正在统计数据…',
      'annotations.currentData': '当前数据：{count} 条标注',
      'annotations.skip': '跳过',
      'annotations.migrate': '迁移',
      'annotations.migrating': '正在迁移…',
      'annotations.migratingProgress': '正在迁移… {current}/{total}',
      'annotations.storageLocationChanged': '存储位置已更改',
      'annotations.exportData': '导出数据',
      'annotations.exportBook': '导出本书',
      'annotations.exportAll': '导出全部',
      'annotations.exported': '已导出 {count} 条标注',
      'annotations.exportFailed': '导出失败：{error}',
      'annotations.hubTitle': '标注',
      'annotations.allAnnotatedBooks': '所有有标注的书籍',
      'annotations.closeHub': '关闭标注',
      'annotations.loading': '正在加载标注…',
      'annotations.retry': '重试',
      'annotations.loadHubFailed': '无法加载标注',
      'annotations.loadHubFailedDetail': '请重试。',
      'annotations.annotatedBooks': '有标注的书籍',
      'annotations.noAnnotationsTitle': '暂无标注',
      'annotations.noAnnotationsDescription': '阅读时选中文本，即可保存你的第一条标注。',
      'annotations.noBookAnnotationsTitle': '本书暂无标注',
      'annotations.noBookAnnotationsDescription': '该书可能已被移除，或其标注已被删除。',
      'annotations.annotationCount': '共 {count} 条标注',
      'annotations.bookCount': '共 {count} 本书',
      'annotations.updatedAt': '更新于 {date}',
      'annotations.chapterNumber': '第 {number} 章',
      'annotations.bookFallback': '书籍',
      'annotations.authorSeparator': '、',
      'annotations.bylineSeparator': ' · ',
      'annotations.error.not_found': '未找到标注服务。',
      'annotations.error.username_required': '此标注请求需要用户名。',
      'annotations.error.invalid_json': '标注请求无效。',
      'annotations.error.no_sync_data': '未提供标注数据。',
      'annotations.error.annotation_not_found': '未找到标注。',
      'annotations.error.invalid_chapter_index': '请求的章节无效。',
      'annotations.error.batch_requires_post': '此批量请求必须使用 POST。',
      'annotations.error.database_unavailable': '标注服务暂时不可用。',
      'annotations.error.reading_progress_not_found': '未找到阅读进度。',
      'annotations.error.server_error': '标注服务发生错误。',
      'annotations.error.network': '连接标注服务时发生网络错误。',
      'annotations.error.timeout': '标注请求超时。',
      'footer.product': 'EPUB 书库',
      'footer.poweredBy': '由',
      'footer.poweredBySuffix': '强力驱动 ·',
      'version.updateAvailable': '有可用更新：v{version}',
      'errors.generic': '发生了错误。',
      'errors.network': '发生网络错误。'
    }
  };

  function normalizeLocale(value) {
    value = String(value || '').replace('_', '-').toLowerCase();
    if (value === 'zh' || value.indexOf('zh-cn') === 0 || value.indexOf('zh-sg') === 0) return 'zh-CN';
    return value === 'en' || value.indexOf('en-') === 0 ? 'en' : '';
  }

  function readCookie(root) {
    var cookie = '';
    var match;
    try { cookie = root.document && root.document.cookie; } catch (error) {}
    if (!cookie) return '';
    match = String(cookie).match(new RegExp('(?:^|;\\s*)' + STORAGE_KEY + '=([^;]*)'));
    if (!match) return '';
    try { return decodeURIComponent(match[1]); } catch (error) { return match[1]; }
  }

  function publicPath(basePath, path) {
    var base = basePath || '/';
    var value = path || '/';
    if (/^(?:[a-z][a-z0-9+.-]*:)?\/\//i.test(value) || /^(?:data|mailto|tel):/i.test(value)) return value;
    if (base.charAt(0) !== '/') base = '/' + base;
    if (base.charAt(base.length - 1) !== '/') base += '/';
    if (base !== '/' && value.indexOf(base) === 0) return value;
    return base + value.replace(/^\/+/, '');
  }

  function createRuntime(root, messages) {
    var locale = '';
    var initialized = false;
    var listeners = [];
    var pageMemoryLocale = '';
    root.EpubBrowserURL = root.EpubBrowserURL || {};
    root.EpubBrowserURL.publicPath = function(path) {
      return publicPath(root.EpubBrowserBasePath || '/', path);
    };

    function readStoredLocale() {
      var stored = '';
      try {
        stored = root.localStorage && root.localStorage.getItem(STORAGE_KEY);
      } catch (error) {}
      stored = normalizeLocale(stored);
      if (stored) return stored;

      try {
        stored = root.epubBrowserCache && root.epubBrowserCache[STORAGE_KEY];
      } catch (error2) {}
      stored = normalizeLocale(stored);
      if (stored) return stored;

      stored = normalizeLocale(readCookie(root));
      if (stored) return stored;
      return normalizeLocale(pageMemoryLocale);
    }

    function persistLocale(value) {
      var localStorageWorked = false;
      pageMemoryLocale = value;
      try {
        if (root.localStorage) {
          root.localStorage.setItem(STORAGE_KEY, value);
          localStorageWorked = true;
        }
      } catch (error) {}

      try {
        if (root.epubBrowserCache) root.epubBrowserCache[STORAGE_KEY] = value;
        if (root.epubBrowserCache) return;
      } catch (error2) {}

      if (localStorageWorked) return;
      try {
        if (root.document) root.document.cookie = STORAGE_KEY + '=' + encodeURIComponent(value) + '; path=/';
      } catch (error3) {}
    }

    function init() {
      var browser;
      if (initialized) return locale;
      initialized = true;
      browser = root.navigator && ((root.navigator.languages || [])[0] || root.navigator.language);
      locale = readStoredLocale() || normalizeLocale(browser) || 'en';
      applyLocaleToDocument();
      if (root.document && root.document.addEventListener) {
        root.document.addEventListener('DOMContentLoaded', function() {
          translateDocument();
        });
      }
      return locale;
    }

    function interpolate(template, params) {
      return String(template).replace(/\{([A-Za-z0-9_]+)\}/g, function(match, key) {
        return params && params[key] !== undefined ? String(params[key]) : match;
      });
    }

    function selectPlural(message, params) {
      var category = 'other';
      var count = params && params.count;
      if (typeof message === 'string') return message;
      if (!message || typeof message !== 'object') return message;
      try {
        if (root.Intl && root.Intl.PluralRules) category = new root.Intl.PluralRules(locale).select(count);
        else category = Number(count) === 1 ? 'one' : 'other';
      } catch (error) {
        category = Number(count) === 1 ? 'one' : 'other';
      }
      return message[category] !== undefined ? message[category] : message.other;
    }

    function t(key, params) {
      var selected;
      var fallback;
      init();
      selected = messages[locale] && messages[locale][key];
      fallback = messages.en && messages.en[key];
      if (selected === undefined) selected = fallback;
      selected = selectPlural(selected, params || {});
      if (selected === undefined) {
        if (root.console && root.console.warn) root.console.warn('Missing i18n key:', key);
        return key;
      }
      return interpolate(selected, params || {});
    }

    function formatDate(value, options) {
      var date = value instanceof Date ? value : new Date(value);
      function pad(number) { return number < 10 ? '0' + number : String(number); }
      init();
      if (isNaN(date.getTime())) return '';
      try {
        if (root.Intl && root.Intl.DateTimeFormat) return new root.Intl.DateTimeFormat(locale, options).format(date);
      } catch (error) {}
      return date.getUTCFullYear() + '-' + pad(date.getUTCMonth() + 1) + '-' + pad(date.getUTCDate());
    }

    function formatNumber(value, options) {
      init();
      try {
        if (root.Intl && root.Intl.NumberFormat) return new root.Intl.NumberFormat(locale, options).format(value);
      } catch (error) {}
      return String(value);
    }

    function translateDocument(scope) {
      var nodes;
      scope = scope || root.document;
      if (!scope || !scope.querySelectorAll) return;
      nodes = scope.querySelectorAll('[data-i18n], [data-i18n-placeholder], [data-i18n-title], [data-i18n-aria-label], [data-i18n-content], [data-i18n-data-tip]');
      Array.prototype.forEach.call(nodes, function(node) {
        var params = {};
        try {
          params = JSON.parse(node.getAttribute('data-i18n-params') || '{}');
        } catch (error) {}
        try {
          if (node.hasAttribute('data-i18n')) node.textContent = t(node.getAttribute('data-i18n'), params);
          ['placeholder', 'title', 'aria-label', 'content', 'data-tip'].forEach(function(attribute) {
            var key = node.getAttribute('data-i18n-' + attribute);
            if (key) node.setAttribute(attribute, t(key, params));
          });
        } catch (error) {
          if (root.console && root.console.warn) root.console.warn('Unable to translate i18n node:', error);
        }
      });
    }

    function updateManifestLink() {
      var link;
      if (root.EpubBrowserDisableManifest) return;
      if (!root.document) return;
      if (root.document.querySelector) link = root.document.querySelector('#epubBrowserManifest');
      if (!link && root.document.createElement && root.document.head) {
        link = root.document.createElement('link');
        link.id = 'epubBrowserManifest';
        link.rel = 'manifest';
        root.document.head.appendChild(link);
      }
      if (link) link.href = root.EpubBrowserURL.publicPath('/assets/manifest.' + locale + '.json');
    }

    function applyLocaleToDocument() {
      var documentRoot = root.document && root.document.documentElement;
      if (documentRoot) documentRoot.lang = locale;
      updateManifestLink();
    }

    function notifyListeners() {
      listeners.slice().forEach(function(listener) {
        try {
          listener(locale);
        } catch (error) {
          if (root.console && root.console.warn) root.console.warn('I18n localechange listener failed:', error);
        }
      });
      try {
        if (root.dispatchEvent && root.CustomEvent) {
          root.dispatchEvent(new root.CustomEvent('localechange', { detail: { locale: locale } }));
        }
      } catch (error2) {}
    }

    function setLocale(value) {
      init();
      locale = normalizeLocale(value) || 'en';
      persistLocale(locale);
      applyLocaleToDocument();
      translateDocument();
      notifyListeners();
      return locale;
    }

    function onLocaleChange(listener) {
      if (typeof listener !== 'function') return function() {};
      listeners.push(listener);
      return function() {
        var index = listeners.indexOf(listener);
        if (index !== -1) listeners.splice(index, 1);
      };
    }

    return {
      init: init,
      t: t,
      getLocale: function() { return init(); },
      setLocale: setLocale,
      translateDocument: translateDocument,
      formatDate: formatDate,
      formatNumber: formatNumber,
      onLocaleChange: onLocaleChange
    };
  }

  return { createRuntime: createRuntime, dictionaries: dictionaries, publicPath: publicPath };
});
