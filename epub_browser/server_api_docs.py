"""Render the authenticated Server OpenAPI reference."""

import html
import json
import shlex
from urllib.parse import urlencode

from .i18n_bundles import get_bundle, i18n_core_immutable_url, render_i18n_bootstrap


_GROUPS = (
    ("library", "apiDocs.group.library", "Library"),
    ("bookshelf", "apiDocs.group.bookshelf", "Bookshelf"),
    ("progress", "apiDocs.group.progress", "Reading progress"),
    ("annotations", "apiDocs.group.annotations", "Annotations"),
    ("vocabulary", "vocabulary.navigation", "Vocabulary"),
    ("reviews", "apiDocs.group.reviews", "Reviews"),
    ("kindle-memo", "account.kindle.memo", "Memo"),
    ("admin", "apiDocs.group.admin", "Administrator data"),
)


def _group_for(operation):
    if operation.required_scope == "admin:data:read":
        return "admin"
    return operation.required_scope.split(":", 1)[0]


def _i18n_params(**params):
    return html.escape(json.dumps(params, separators=(",", ":")), quote=True)


_BODY_EXAMPLES = {
    "putMyBookshelf": {"version": 0, "data": {"items": [], "groups": {}, "order": []}},
    "putMyProgress": {"chapter_index": 0},
    "createMyAnnotation": {"book_hash": "BOOK_ID", "chapter_index": 0, "text": "Selected text", "color": "#ffff00"},
    "putMyAnnotation": {"note": "My reading note"},
    "putMyReview": {"rating": 5, "review_text": "My review"},
    "recordMyVocabularyLookup": {"book_id": "BOOK_ID", "chapter_index": 0, "word": "read", "lookup_id": "lookup-001"},
    "patchMyVocabulary": {"mastery": "learning"},
    "putMyKindleMemo": {"memo": "Read a chapter today."},
}

_QUERY_EXAMPLES = {
    "listBooks": {"format": "epub", "limit": 5},
    "getBookChapter": {"format": "text"},
    "listMyAnnotations": {"book_id": "BOOK_ID", "chapter_index": 0, "fields": "id,text,note", "limit": 5},
    "listAdminUserAnnotations": {"book_id": "BOOK_ID", "chapter_index": 0, "fields": "id,text,note", "limit": 5},
    "listMyVocabulary": {"q": "read", "mastery": "learning", "limit": 5},
    "getAdminUserReadingInsights": {"period": "month", "anchor": "2026-01-01", "timezone": "UTC"},
}


def _example_command(operation, contract):
    path = operation.path
    for parameter in contract.get("parameters", ()):
        if parameter["in"] == "path":
            name = parameter["name"]
            value = "0" if name == "chapter_index" else name.upper()
            path = path.replace("{" + name + "}", value)
    query = _QUERY_EXAMPLES.get(operation.operation_id)
    if query is None:
        query_names = {
            parameter["name"] for parameter in contract.get("parameters", ()) if parameter["in"] == "query"
        }
        query = {
            name: value
            for name, value in (("book_id", "BOOK_ID"), ("chapter_index", 0), ("limit", 5))
            if name in query_names
        }
    if query:
        path += "?" + urlencode(query, safe=",")
    lines = [
        "curl --request " + operation.methods[0],
        '--header "Authorization: Bearer $EPUB_BROWSER_PAT"',
    ]
    if operation.operation_id in _BODY_EXAMPLES:
        lines.append('--header "Content-Type: application/json"')
        body = json.dumps(_BODY_EXAMPLES[operation.operation_id], separators=(",", ":"))
        lines.append("--data " + shlex.quote(body))
    lines.append('"$EPUB_BROWSER_URL' + path + '"')
    return (" " + "\\" + "\n  ").join(lines)


def _localized(bundle, key, fallback, **values):
    params = f' data-i18n-params="{_i18n_params(**values)}"' if values else ""
    message = html.escape(bundle.get(key, fallback).format(**values))
    return f'<span data-i18n="{key}"{params}>{message}</span>'


def _parameter_markup(parameter, bundle):
    name = parameter["name"]
    schema = parameter["schema"]
    location = parameter["in"]
    key = name
    if name == "format":
        key = "chapterFormat" if "text" in schema["enum"] else "bookFormat"
    values = {}
    if name == "fields":
        values["fields"] = ", ".join(parameter["x-allowed-fields"])
    if name == "chapter_index" and "maximum" in schema:
        # The upper bound is the storage integer limit, not the book length.
        schema = {k: v for k, v in schema.items() if k != "maximum"}
    metadata = [
        _localized(bundle, f"apiDocs.paramLocation.{location}", {"path": "Path", "query": "Query", "body": "JSON body"}[location]),
    ]
    if parameter.get("required"):
        metadata.append(_localized(bundle, "apiDocs.paramRequired", "Required"))
    if parameter.get("deprecated"):
        metadata.append(_localized(bundle, "apiDocs.paramLegacy", "Legacy"))
    kind = schema.get("type")
    if kind:
        metadata.append("<code dir=\"ltr\">" + html.escape(" | ".join(kind) if isinstance(kind, list) else kind) + "</code>")
    if "enum" in schema:
        metadata.append('<code dir="ltr">' + html.escape(", ".join(map(str, schema["enum"]))) + "</code>")
    if "minimum" in schema:
        bounds = str(schema["minimum"])
        bounds = bounds + "–" + str(schema["maximum"]) if "maximum" in schema else "≥ " + bounds
        metadata.append(f'<code dir="ltr">{bounds}</code>')
    if "default" in schema:
        metadata.append(_localized(bundle, "apiDocs.paramDefault", "Default {value}", value=schema["default"]))
    if "maxLength" in schema:
        metadata.append(_localized(bundle, "apiDocs.paramLength", "Up to {value} characters", value=schema["maxLength"]))
    description = parameter.get("description", "")
    help_key = "apiDocs.param." + key
    help_text = _localized(bundle, help_key, description, **values) if description or help_key in bundle else ""
    return (
        f'<div class="api-param"><dt><code dir="ltr">{html.escape(name)}</code></dt>'
        f'<dd><div class="api-param-meta">{"".join(metadata)}</div>{help_text}</dd></div>'
    )


def _operation_details(operation, contract, schemas, bundle):
    parameters = list(contract.get("parameters", ()))
    if "requestBody" in contract:
        body = contract["requestBody"]["content"]["application/json"]["schema"]
        if "$ref" in body:
            body = schemas[body["$ref"].rsplit("/", 1)[-1]]
        parameters.extend(
            {"name": name, "in": "body", "schema": schema, "required": name in body.get("required", ())}
            for name, schema in body["properties"].items()
        )
    rows = "".join(_parameter_markup(parameter, bundle) for parameter in parameters)
    code_id = "api-example-" + operation.operation_id
    return f'''<details class="api-endpoint-details" data-api-endpoint-details id="{operation.operation_id}">
        <summary>{_localized(bundle, "apiDocs.requestDetails", "Parameters and example")}</summary>
        <div class="api-endpoint-content">
            {f'<dl class="api-params">{rows}</dl>' if rows else ''}
            <div class="api-code-card api-endpoint-example">
                <div class="api-code-header">
                    <strong>{_localized(bundle, "apiDocs.example", "Example request")}</strong>
                    <button type="button" data-api-copy="{code_id}">{_localized(bundle, "apiDocs.copy", "Copy")}</button>
                </div>
                <pre dir="ltr"><code id="{code_id}">{html.escape(_example_command(operation, contract))}</code></pre>
                <p class="api-copy-status" role="status" data-api-copy-status></p>
            </div>
        </div>
    </details>'''


def _operation_markup(operation, contract, schemas, bundle):
    method = operation.methods[0]
    searchable = " ".join((method, operation.path, operation.required_scope, operation.summary))
    summary_key = "apiDocs.operation.{0}".format(operation.operation_id)
    return '''<li class="api-endpoint" data-api-endpoint data-api-search="{searchable}">
    <div class="api-endpoint-route"><span class="api-method api-method-{method_class}" dir="ltr">{method}</span><code dir="ltr">{path}</code></div>
    <div class="api-endpoint-detail"><span class="api-scope" dir="ltr">{scope}</span><p data-i18n="{summary_key}">{summary}</p></div>
    {details}
</li>'''.format(
        searchable=html.escape(searchable.lower(), quote=True),
        method_class=html.escape(method.lower(), quote=True),
        method=html.escape(method),
        path=html.escape(operation.path),
        scope=html.escape(operation.required_scope),
        summary_key=html.escape(summary_key, quote=True),
        summary=html.escape(operation.summary),
        details=_operation_details(operation, contract, schemas, bundle),
    )


def render_api_docs(operations, document, locale=None):
    bundle = {**get_bundle("en"), **get_bundle(locale or "en")}
    paths = document["paths"]
    schemas = document["components"]["schemas"]
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
            rows="".join(
                _operation_markup(operation, paths[operation.path][operation.methods[0].lower()], schemas, bundle)
                for operation in group_operations
            ),
        ))

    count = len(operations)
    api_docs_html = '''<!doctype html>
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
        <aside class="api-hero-facts" aria-label="API details" data-i18n-aria-label="apiDocs.details"><div><span data-i18n="apiDocs.basePath">Base path</span><code dir="ltr">/api/v1</code></div><div><span data-i18n="apiDocs.format">Format</span><strong>JSON</strong></div><div><span data-i18n="apiDocs.operations">Operations</span><strong>{count}</strong></div></aside>
    </section>
    <section class="api-quickstart" aria-labelledby="apiQuickstartTitle">
        <div class="api-steps"><p class="api-section-kicker" data-i18n="apiDocs.getStarted">Get started</p><h2 id="apiQuickstartTitle" data-i18n="apiDocs.quickstart">Authenticate your first request</h2><ol><li><span>1</span><div><strong data-i18n="apiDocs.step1Title">Create a token</strong><p data-i18n="apiDocs.step1Body">Open Account settings, create a PAT, and choose only the scopes your integration needs.</p></div></li><li><span>2</span><div><strong data-i18n="apiDocs.step2Title">Add the Bearer header</strong><p data-i18n="apiDocs.step2Body">Send the token in the Authorization header. This documentation page never reads or stores it.</p></div></li><li><span>3</span><div><strong data-i18n="apiDocs.step3Title">Call a versioned endpoint</strong><p data-i18n="apiDocs.step3Body">All public endpoints live under /api/v1 and return JSON unless documented otherwise.</p></div></li></ol></div>
        <div class="api-code-card"><div class="api-code-header"><div><p data-i18n="apiDocs.example">Example request</p><strong data-i18n="apiDocs.exampleListBooks">List books</strong></div><button type="button" data-api-copy="apiExampleCode" data-i18n="apiDocs.copy">Copy</button></div><pre dir="ltr"><code id="apiExampleCode">curl --request GET \\
  --header "Authorization: Bearer $EPUB_BROWSER_PAT" \\
  "$EPUB_BROWSER_URL/api/v1/books"</code></pre><p class="api-code-note">{example_setup}</p><p class="api-copy-status" data-api-copy-status role="status" aria-live="polite"></p></div>
    </section>
    <section class="api-explorer" id="apiEndpointExplorer" aria-labelledby="apiExplorerTitle">
        <header class="api-explorer-header"><div><p class="api-section-kicker" data-i18n="apiDocs.reference">Reference</p><h2 id="apiExplorerTitle" data-i18n="apiDocs.explorer">Endpoint explorer</h2><p data-i18n="apiDocs.explorerBody">Search by method, path, permission scope, or description.</p></div><label class="api-search"><span data-i18n="apiDocs.searchLabel">Search endpoints</span><input id="apiEndpointSearch" type="search" autocomplete="off" placeholder="Search path, scope, or description" data-i18n-placeholder="apiDocs.searchPlaceholder" aria-describedby="apiSearchHint"><small id="apiSearchHint" data-i18n="apiDocs.searchHint">Press / to focus search.</small></label></header>
        <div class="api-results-bar"><p id="apiResultCount" role="status" aria-live="polite" data-i18n="apiDocs.results" data-i18n-params="{result_params}">{count} endpoints shown</p><a href="/openapi.json" data-i18n="apiDocs.machineReadable">Machine-readable schema</a></div>
        <div class="api-explorer-layout"><nav class="api-toc" aria-label="On this page" data-i18n-aria-label="apiDocs.onThisPage"><p data-i18n="apiDocs.onThisPage">On this page</p>{navigation}</nav><div class="api-groups">{sections}<div class="api-empty-state" id="apiEmptyState" hidden><strong data-i18n="apiDocs.emptyTitle">No matching endpoints</strong><p data-i18n="apiDocs.emptyBody">Try a method such as GET, a scope such as reviews:read, or part of a path.</p></div></div></div>
    </section>
    <footer class="api-footer"><span>EPUB Browser API · OpenAPI 3.1</span><a href="#apiDocsTop" data-i18n="apiDocs.backToTop">Back to top</a></footer>
</main>
</body>
</html>'''

    api_docs_html = api_docs_html.format(
        count=count,
        example_setup=_localized(bundle, "apiDocs.exampleSetup",
            "Set EPUB_BROWSER_URL to your server address and EPUB_BROWSER_PAT to your token. Replace placeholders such as BOOK_ID with real IDs."),
        result_params=_i18n_params(count=count),
        navigation="".join(navigation),
        sections="".join(sections),
    )
    return api_docs_html.replace(
        '<script src="/assets/i18n.js" defer></script>',
        render_i18n_bootstrap(
            locale,
            None,
            core_url=i18n_core_immutable_url(),
            deployment_mode='server',
        ),
    )
