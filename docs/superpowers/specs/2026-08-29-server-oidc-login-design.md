# Server OIDC login design

## Purpose and scope

EPUB Browser Server currently authenticates local username/password accounts and
issues its own opaque browser sessions. This change adds one configurable,
standards-based OpenID Connect Provider so deployments can use Authelia,
Authentik, Keycloak, or another conforming Provider without provider-specific
code.

The first release provides:

- one generic, administrator-configured OIDC Provider with a customizable
  display name;
- Authorization Code Flow with discovery, PKCE, state, nonce, and ID Token
  validation;
- explicit binding to existing local accounts and optional just-in-time member
  provisioning;
- local administrator fallback login and an option to disable local password
  login for ordinary members;
- self-service identity management, administrator visibility, and localized
  login, association, account, and configuration interfaces;
- end-to-end validation against a real Authelia container.

This feature is Server-only. SSG output contains no OIDC configuration, routes,
buttons, dependencies, database state, or network calls. The first release does
not support multiple simultaneous Providers, claim-to-administrator mapping,
SCIM lifecycle management, refresh-token storage, access-token API
authorization, or global Provider logout.

## Product decisions

| Area | Decision |
| --- | --- |
| Protocol | EPUB Browser is an OIDC Relying Party and uses the standard Authorization Code Flow with PKCE. |
| Provider support | The implementation is generic. The administrator names and configures one Provider; nothing is hard-coded for Authelia. |
| Account identity | Only the exact `(issuer, subject)` pair identifies an external user. Username, display name, and email are never automatic binding keys. |
| Unknown identity | Binding is the default. An administrator may enable automatic creation of a passwordless `member`. |
| Existing account binding | A signed-in user may start a link flow, or an unknown OIDC identity may prove ownership of an existing account with its local password. |
| Local login | Local administrator login always remains available as a recovery path. Administrators may disable ordinary-member password login. |
| Roles | OIDC claims never grant `admin`. Automatically created users are always `member`; role changes remain explicit administrator actions. |
| Logout | Logout revokes only the EPUB Browser session. It does not terminate the Provider's global SSO session. |
| Provider count | The settings UI manages one Provider. The identity schema includes issuer so future multi-Provider support does not require rewriting bindings. |

## Architecture and component boundaries

### OIDC service

A new focused `OIDCService` owns OIDC protocol work:

1. fetch and validate Provider discovery metadata;
2. create browser-bound, short-lived authorization transactions;
3. build authorization requests with PKCE, state, and nonce;
4. exchange authorization codes and validate ID Tokens;
5. normalize only the claims needed for local account decisions;
6. resolve, link, or provision a local principal transactionally.

`OIDCService` does not authorize books or issue a second class of application
session. After successful OIDC authentication it asks the existing
`AuthService` to issue the same opaque local session cookie used by password
login. All current CSRF, authorization, book visibility, PAT, annotation,
progress, and administration code continues to use `Principal` and `user_id`.

Provider access and refresh tokens are not persisted. The validated identity
claims needed for binding are copied into a short-lived transaction, and token
objects are discarded after callback processing.

### Protocol library

Use Authlib for OAuth/OIDC request construction, token exchange, JOSE/JWK
handling, and standards validation rather than implementing the protocol
primitives locally. The package still supports Python 3.9, while Authlib 1.7 no
longer does, so dependencies are constrained to `Authlib>=1.6.11,<1.7` plus a
compatible `httpx` release. Authlib 1.6.11 includes the relevant Starlette
client CSRF fix.

Application-owned database transactions and cookies store the authorization
transaction instead of introducing Starlette's general-purpose client session
middleware. This keeps OIDC state isolated from EPUB Browser's authenticated
session and makes one-time consumption explicit.

### State store

`StateStore` remains the single owner of SQLite schema and account mutations.
It exposes focused methods for settings replacement, transaction creation and
consumption, identity lookup/link/unlink, and atomic user provisioning. OIDC
code does not execute ad hoc SQL in request handlers.

## Database schema

The next SQLite schema version adds these logical tables.

### `oidc_settings`

A singleton row stores:

- `enabled`;
- `provider_name`;
- `issuer_url`;
- `client_id` and `client_secret`;
- exact `redirect_uri`;
- scopes, defaulting to `openid profile email` and always containing
  `openid`;
- username claim, defaulting to `preferred_username`;
- `auto_create_users`;
- `allow_member_password_login`;
- configuration revision and timestamps.

The client secret is write-only at the API boundary. Reads return only
`client_secret_configured`; logs and error payloads never include the value.
The authoritative database already contains sensitive account, session, PAT,
AI, and WebHook state and retains the same private-file and private-backup
security boundary.

### `user_identities`

Each row stores:

- exact canonical issuer returned by discovery and the validated ID Token;
- non-empty OIDC subject;
- target local `user_id`;
- last observed username claim, display name, and email for administration and
  diagnostics only;
- creation and last-login timestamps.

`(issuer, subject)` is the primary identity key. `(user_id, issuer)` is unique,
so one local account cannot accidentally bind two users from the same Provider.
Changing a displayed username or email never changes the binding.

### `oidc_login_transactions`

Short-lived rows store:

- a digest of high-entropy state and a digest of a separate browser-binding
  cookie;
- nonce and PKCE verifier;
- purpose (`login`, `link`, or `associate`);
- optional expected local user ID;
- validated safe local return path;
- phase, expiry, and one-time-consumption timestamps;
- for the association phase only, validated issuer, subject, and bounded
  profile claims.

Transactions expire after ten minutes, are single-use, and are opportunistically
purged. Raw state and browser-binding tokens are never stored. The PKCE verifier
must remain recoverable for the short authorization window, so it is stored only
in this private, expiring table and deleted on consumption.

Schema creation, migrations, indexes, foreign keys, and rollback tests follow
the existing `StateStore` migration pattern. This is runtime application data,
not EPUB or PDF content cache data, so neither content-cache revision changes.

## Configuration lifecycle

The administrator interface adds a top-level **OIDC** tab. It contains three
progressively disclosed groups:

1. **Provider**: enabled state, display name, issuer, client ID, client secret,
   redirect URI, scopes, and username claim;
2. **Account provisioning**: require binding or automatically create members;
3. **Local fallback**: whether ordinary members may use local passwords, with
   permanent explanatory copy that administrator password login remains
   available.

The redirect URI is explicit because reverse-proxy deployments cannot safely
infer a browser-facing HTTPS origin from the direct application socket. The UI
suggests the current browser origin plus the fixed callback path. It validates
that the configured URI uses HTTPS, except loopback development HTTP, has no
fragment, and uses EPUB Browser's exact callback path.

Saving an enabled configuration performs bounded discovery before committing:

- issuer and discovery issuer must match exactly;
- authorization, token, and JWKS endpoints must be present and use acceptable
  schemes;
- authorization-code response support and a compatible ID Token signing
  algorithm must be advertised when those metadata fields are present;
- scopes and redirect URI must pass local validation.

Failure leaves the previous working row unchanged. A successful save increments
the configuration revision and takes effect on the next login without restart.
Outstanding transactions from older revisions are rejected. Existing EPUB
Browser sessions remain valid, and existing identities remain stored if the
Provider is disabled or replaced.

Changing or clearing the client secret uses explicit replacement semantics like
the existing AI key interface. An enabled configuration cannot clear a required
secret. The page never places the stored secret into the DOM.

Discovery and JWKS responses use bounded timeouts and response sizes. Metadata
is cached by issuer and configuration revision for a short period; validation
errors invalidate the relevant cache without affecting authenticated local
sessions.

## Authentication and account flows

### OIDC login

When enabled, `/login` shows one secondary action labeled with the configured
Provider name. Starting OIDC login:

1. accepts only a validated local `next` path;
2. creates state, nonce, a PKCE verifier/challenge, and a browser-binding token;
3. persists the transaction and sets an `HttpOnly`, `SameSite=Lax`, bounded-path
   cookie;
4. redirects to the discovered authorization endpoint.

The callback requires both the state and browser-binding cookie. It atomically
claims the transaction, exchanges the code using the exact stored redirect URI
and PKCE verifier, and validates signature, issuer, audience/authorized party,
expiry, issued-at bounds, and nonce. Provider and protocol errors return a
localized recovery page without reflecting raw upstream text.

If the identity is already linked and the local account is enabled, EPUB
Browser updates non-authoritative profile snapshots and issues a local session.
Disabled users receive the same generic denial as other unusable identities.

### Automatic member provisioning

If the identity is unknown and automatic creation is enabled, one transaction:

- rechecks that `(issuer, subject)` is still unclaimed;
- creates a passwordless enabled `member`;
- chooses a unique normalized username;
- inserts the identity;
- creates the local application session.

Username generation uses the configured claim, then the verified email local
part, then a provider-name plus subject-digest fallback. Collision suffixes are
deterministic enough for readability but never used as identity evidence.
Concurrent callbacks cannot create duplicate identities or accounts.

### Existing account association

If automatic creation is disabled, a valid unknown callback becomes a second,
short-lived association phase. The page explains that no account has been
created and offers username/password proof for an existing account. Password
verification uses the existing throttling and constant-behavior authentication
path. This proof remains available when ordinary-member password login is
disabled because it establishes account ownership rather than starting a local
password session.

Successful proof atomically verifies that the identity is still unclaimed,
links it, consumes the association transaction, and issues a local session.
Failure does not disclose whether the local username or external identity
exists.

### Link from account settings

A signed-in user can start a `link` transaction from account settings. The
transaction records the expected user ID and asks the Provider for fresh
authentication. The callback links only to that same enabled local user and
rejects an identity already owned by another account. It never changes the
current account based on returned username or email.

### Unlinking and administration

Account settings lists the bound Provider and profile snapshot. Self-service
unlink is rejected if it would leave no usable login method. With one Provider,
that means a passwordless provisioned member cannot remove its sole identity.
Administrators can inspect identities on a user, remove a binding with explicit
confirmation, reset a password, disable an account, and revoke sessions through
the existing user-management surface. Removing a binding does not silently
delete reading data or the local user.

### Local password policy and logout

Local administrator login is always accepted as a recovery route. When member
password login is disabled, password authentication of a `member` at `/login`
returns the same generic failure as invalid credentials. Password proof on the
OIDC association page remains allowed and rate-limited.

Logout revokes only the EPUB Browser session. RP-initiated Provider logout is
deferred because it can unexpectedly sign the reader out of unrelated services
and requires additional Provider-specific policy choices.

## Routes and response semantics

The route contract adds:

- `GET /auth/oidc/start` — begin login;
- `GET /auth/oidc/callback` — validate Provider callback;
- `GET|POST /auth/oidc/associate` — render and complete existing-account proof;
- `POST /api/account/oidc/link` — start self-service linking;
- `DELETE /api/account/oidc/identity` — self-service unlink;
- `GET|PUT /api/admin/oidc/settings` — read masked settings and atomically
  validate/replace them;
- administrator identity inspection/removal through the existing user detail
  API family.

OIDC start, callback, and association are public only after initial server setup
has completed. The callback never accepts an arbitrary post-login URL. API
mutations retain the existing local-session CSRF requirement. HTML protocol
failures show a localized retry path; administrative JSON uses stable error
codes and no upstream secrets.

The authorization callback, association pages, login page, and masked settings
responses use `Cache-Control: no-store`. OIDC tokens, codes, state, nonce, PKCE
material, client secrets, and raw claims never appear in logs, URLs generated by
EPUB Browser beyond required protocol parameters, health endpoints, or error
responses.

## UI and interaction design

The UI follows the existing account/admin visual language. `ui-ux-pro-max`
guidance is applied as constraints rather than introducing a second theme:

- the OIDC configuration is a normal top-level admin tab with a clear selected
  state and deep-linkable section name;
- related inputs use semantic `fieldset`/`legend` groups, persistent helper
  text, visible labels, and a single primary **Validate and save** action;
- the client-secret field is blank on load, uses password-manager-safe
  autocomplete semantics, and explains replacement behavior;
- save, link, associate, and unlink actions disable during requests and expose
  loading, success, and actionable field-level errors through `aria-live`;
- destructive unlink is visually separated and requires confirmation;
- controls have at least 44px touch targets, 8px spacing, visible keyboard focus,
  and no hover-only information;
- layouts are mobile-first, single-column at 375px, reflow without horizontal
  scrolling at 200% zoom, and remain coherent in light and dark themes;
- motion is limited to existing 150–300ms state transitions and respects
  `prefers-reduced-motion`;
- the login page uses a textual divider between local and OIDC actions, avoiding
  a false hierarchy that makes the recovery method look disabled;
- protocol failures preserve a safe retry or local-login escape route.

All visible copy and dynamically inserted DOM use the existing i18n mechanism
and are added to every supported locale. Locale changes update an open OIDC
admin panel or identity area without reload.

No Provider logo is fetched remotely. The button uses the Provider's configured
text name and the project's existing neutral identity icon treatment, avoiding
unverified brand assets and runtime third-party dependencies.

## Error handling and observability

- Discovery, JWKS, and token endpoint timeouts produce stable localized errors
  with retry guidance.
- Unknown state, missing browser cookie, reused callback, revision mismatch,
  nonce mismatch, invalid signature, issuer/audience mismatch, and expired
  transactions fail closed.
- Duplicate identity linking and provisioning races are resolved by SQLite
  uniqueness and translated into generic user-facing conflicts.
- OIDC outages never invalidate existing local sessions or the local
  administrator fallback.
- Configuration diagnostics may log a sanitized stage and Provider host only
  when logging is enabled. They never log query strings, tokens, claims,
  credentials, or client secrets.
- Disabling an external account at the Provider prevents future OIDC login but
  cannot revoke an already-issued EPUB Browser session without a logout
  protocol. Administrators retain local session revocation controls; back/front
  channel logout are future work.

## Compatibility and deployment

This is a SQLite runtime schema migration and does not touch the EPUB/PDF
content cache revisions. Server UI, routes, i18n, and asset updates take effect
after deployment/restart without reconverting books.

Authelia deployment documentation includes:

- registering EPUB Browser as a confidential OIDC client;
- the exact callback URI;
- Authorization Code Flow, `openid profile email`, and S256 PKCE;
- an example client-secret hash/configuration;
- the requirement that browser-facing issuer and redirect URI normally use
  HTTPS;
- keeping a local administrator credential as recovery.

Existing installations remain local-login-only after migration because the
OIDC singleton defaults to disabled. No bootstrap or setup behavior changes.

## Test strategy

### Unit and state tests

Tests cover:

1. schema migration, constraints, transaction expiry/one-time use, and settings
   rollback on validation failure;
2. exact issuer/subject identity semantics, duplicate races, account disablement,
   profile snapshot updates, unlink safeguards, and atomic provisioning;
3. username claim fallback and collision handling without implicit matching;
4. member local-login policy while preserving administrator and association
   password proof;
5. state, browser binding, nonce, PKCE, safe-next, configuration revision, and
   sanitized error handling;
6. ID Token signature, issuer, audience, authorized-party, time, and nonce
   validation with rotating JWKS fixtures;
7. discovery cache behavior, bounded HTTP failures, and no token/secret logging.

### Server integration tests

Starlette tests cover login-button visibility, callback success and every
failure class, linked login, required association, automatic provisioning,
account linking/unlinking, administrator settings and identity APIs, CSRF,
cache headers, role protection, session issuance, disabled users, and SSG
absence.

UI tests cover tab navigation, locale updates, loading/disabled states,
field-level errors, secret masking, confirmation, keyboard operation, and
responsive markup. Existing generated-surface and i18n completeness tests are
extended rather than introducing a separate UI framework.

### Real Authelia end-to-end test

A Docker Compose test fixture starts:

- Authelia with a file user backend and a confidential OIDC client requiring
  S256 PKCE;
- EPUB Browser Server with a temporary persistent data directory and a small
  test library;
- an isolated test network and browser-reachable test hostnames.

The automated browser flow verifies local administrator setup, OIDC settings
configuration, real Authelia sign-in, association with an existing account,
logout/relogin, automatic member creation, local-member-login disablement, and
an authenticated library page. The test also verifies that bad redirect/state
and disabled OIDC paths fail safely. Test-only credentials and signing keys are
clearly marked and never reused as production examples.

Final verification includes the focused Python and JavaScript suites, the
Docker Authelia E2E run, `git diff --check`, UI screenshots at desktop and
375px widths in light/dark themes, keyboard traversal, and a final review using
the `UI/UX Design Review` WCAG 2.1/2.2 AA checklist. Review findings rated
critical, high, or medium are fixed and re-verified before completion.
