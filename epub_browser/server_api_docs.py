"""Render the authenticated Server OpenAPI reference."""

import html
import json


_GROUPS = (
    ("library", "apiDocs.group.library", "Library"),
    ("bookshelf", "apiDocs.group.bookshelf", "Bookshelf"),
    ("progress", "apiDocs.group.progress", "Reading progress"),
    ("annotations", "apiDocs.group.annotations", "Annotations"),
    ("reviews", "apiDocs.group.reviews", "Reviews"),
    ("admin", "apiDocs.group.admin", "Administrator data"),
)


def _group_for(operation):
    if operation.required_scope == "admin:data:read":
        return "admin"
    return operation.required_scope.split(":", 1)[0]


def _i18n_params(**params):
    return html.escape(json.dumps(params, separators=(",", ":")), quote=True)


def _operation_markup(operation):
    method = operation.methods[0]
    searchable = " ".join((method, operation.path, operation.required_scope, operation.summary))
    return '''<li class="api-endpoint" data-api-endpoint data-api-search="{searchable}">
    <div class="api-endpoint-route"><span class="api-method api-method-{method_class}">{method}</span><code>{path}</code></div>
    <div class="api-endpoint-detail"><span class="api-scope">{scope}</span><p>{summary}</p></div>
</li>'''.format(
        searchable=html.escape(searchable.lower(), quote=True),
        method_class=html.escape(method.lower(), quote=True),
        method=html.escape(method),
        path=html.escape(operation.path),
        scope=html.escape(operation.required_scope),
        summary=html.escape(operation.summary),
    )


def render_api_docs(operations):
    operations = tuple(operations)
    grouped = {key: [] for key, _translation, _fallback in _GROUPS}
    for operation in operations:
        grouped.setdefault(_group_for(operation), []).append(operation)

    navigation = []
    sections = []
    for key, translation, fallback in _GROUPS:
        group_operations = grouped.get(key, ())
        if not group_operations:
            continue
        count = len(group_operations)
        navigation.append(
            '<a href="#api-group-{key}" data-api-group-link="{key}"><span data-i18n="{translation}">{fallback}</span>'
            '<strong aria-hidden="true">{count}</strong></a>'.format(
                key=key, translation=translation, fallback=fallback, count=count,
            )
        )
        sections.append('''<section class="api-group" id="api-group-{key}" data-api-group="{key}" aria-labelledby="api-group-{key}-title">
    <header class="api-group-header"><div><p data-i18n="apiDocs.endpointGroup">Endpoint group</p><h2 id="api-group-{key}-title" data-i18n="{translation}">{fallback}</h2></div><span data-api-group-count data-i18n="apiDocs.endpointCount" data-i18n-params="{params}">{count} endpoints</span></header>
    <ul class="api-endpoint-list">{rows}</ul>
</section>'''.format(
            key=key,
            translation=translation,
            fallback=fallback,
            params=_i18n_params(count=count),
            count=count,
            rows="".join(_operation_markup(operation) for operation in group_operations),
        ))

    count = len(operations)
    return '''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light dark">
<title data-i18n="apiDocs.pageTitle">API reference · EPUB Browser</title>
<link rel="stylesheet" href="/assets/theme.css">
<link rel="stylesheet" href="/assets/api-docs.css">
<script src="/assets/theme-bootstrap.js"></script>
<script src="/assets/i18n.js" defer></script>
<script src="/assets/api-docs.js" defer></script>
</head>
<body class="api-docs-page" id="apiDocsTop">
<a class="api-skip-link" href="#apiEndpointExplorer" data-i18n="apiDocs.skip">Skip to endpoints</a>
<header class="api-topbar">
    <a class="api-brand" href="/" aria-label="EPUB Browser"><img class="api-brand-mark" src="/assets/logo-mark-color.png" width="32" height="32" alt="" aria-hidden="true"><span>EPUB Browser</span><span class="api-brand-divider" aria-hidden="true">/</span><strong>API</strong></a>
    <a class="api-back-link" href="/" aria-label="Back to library" data-i18n-aria-label="apiDocs.back"><svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="m15 18-6-6 6-6"/></svg><span data-i18n="apiDocs.back">Back to library</span></a>
</header>
<main class="api-shell">
    <section class="api-hero" aria-labelledby="apiDocsTitle">
        <div class="api-hero-copy"><p class="api-eyebrow"><span>OpenAPI 3.1</span><span data-i18n="apiDocs.authBadge">Bearer PAT authentication</span></p><h1 id="apiDocsTitle" data-i18n="apiDocs.title">Build with your EPUB library</h1><p data-i18n="apiDocs.intro">Read books and chapters, sync personal reading data, or inspect account data with an administrator token.</p><div class="api-hero-actions"><a class="api-primary-action" href="/openapi.json" download><svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M12 3v12m0 0 4-4m-4 4-4-4M5 20h14"/></svg><span data-i18n="apiDocs.download">Download OpenAPI JSON</span></a><a class="api-secondary-action" href="#apiEndpointExplorer" data-i18n="apiDocs.browse">Browse endpoints</a></div></div>
        <aside class="api-hero-facts" aria-label="API details" data-i18n-aria-label="apiDocs.details"><div><span data-i18n="apiDocs.basePath">Base path</span><code>/api/v1</code></div><div><span data-i18n="apiDocs.format">Format</span><strong>JSON</strong></div><div><span data-i18n="apiDocs.operations">Operations</span><strong>{count}</strong></div></aside>
    </section>
    <section class="api-quickstart" aria-labelledby="apiQuickstartTitle">
        <div class="api-steps"><p class="api-section-kicker" data-i18n="apiDocs.getStarted">Get started</p><h2 id="apiQuickstartTitle" data-i18n="apiDocs.quickstart">Authenticate your first request</h2><ol><li><span>1</span><div><strong data-i18n="apiDocs.step1Title">Create a token</strong><p data-i18n="apiDocs.step1Body">Open Account settings, create a PAT, and choose only the scopes your integration needs.</p></div></li><li><span>2</span><div><strong data-i18n="apiDocs.step2Title">Add the Bearer header</strong><p data-i18n="apiDocs.step2Body">Send the token in the Authorization header. This documentation page never reads or stores it.</p></div></li><li><span>3</span><div><strong data-i18n="apiDocs.step3Title">Call a versioned endpoint</strong><p data-i18n="apiDocs.step3Body">All public endpoints live under /api/v1 and return JSON unless documented otherwise.</p></div></li></ol></div>
        <div class="api-code-card"><div class="api-code-header"><div><p data-i18n="apiDocs.example">Example request</p><strong>List books</strong></div><button type="button" id="apiCopyExample" data-i18n="apiDocs.copy">Copy</button></div><pre><code id="apiExampleCode">curl --request GET \\
  --header "Authorization: Bearer $EPUB_BROWSER_PAT" \\
  "$EPUB_BROWSER_URL/api/v1/books"</code></pre><p class="api-code-note" data-i18n="apiDocs.envHint">Keep the token in an environment variable instead of placing it in source code.</p><p class="api-copy-status" id="apiCopyStatus" role="status" aria-live="polite"></p></div>
    </section>
    <section class="api-explorer" id="apiEndpointExplorer" aria-labelledby="apiExplorerTitle">
        <header class="api-explorer-header"><div><p class="api-section-kicker" data-i18n="apiDocs.reference">Reference</p><h2 id="apiExplorerTitle" data-i18n="apiDocs.explorer">Endpoint explorer</h2><p data-i18n="apiDocs.explorerBody">Search by method, path, permission scope, or description.</p></div><label class="api-search"><span data-i18n="apiDocs.searchLabel">Search endpoints</span><input id="apiEndpointSearch" type="search" autocomplete="off" placeholder="Search path, scope, or description" data-i18n-placeholder="apiDocs.searchPlaceholder" aria-describedby="apiSearchHint"><small id="apiSearchHint" data-i18n="apiDocs.searchHint">Press / to focus search.</small></label></header>
        <div class="api-results-bar"><p id="apiResultCount" role="status" aria-live="polite" data-i18n="apiDocs.results" data-i18n-params="{result_params}">{count} endpoints shown</p><a href="/openapi.json" data-i18n="apiDocs.machineReadable">Machine-readable schema</a></div>
        <div class="api-explorer-layout"><nav class="api-toc" aria-label="On this page" data-i18n-aria-label="apiDocs.onThisPage"><p data-i18n="apiDocs.onThisPage">On this page</p>{navigation}</nav><div class="api-groups">{sections}<div class="api-empty-state" id="apiEmptyState" hidden><strong data-i18n="apiDocs.emptyTitle">No matching endpoints</strong><p data-i18n="apiDocs.emptyBody">Try a method such as GET, a scope such as reviews:read, or part of a path.</p></div></div></div>
    </section>
    <footer class="api-footer"><span>EPUB Browser API · OpenAPI 3.1</span><a href="#apiDocsTop" data-i18n="apiDocs.backToTop">Back to top</a></footer>
</main>
</body>
</html>'''.format(
        count=count,
        result_params=_i18n_params(count=count),
        navigation="".join(navigation),
        sections="".join(sections),
    )
