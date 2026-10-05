# Nova Slider CAPTCHA 0.1.0

An independent, installable Django app for self-hosted puzzle verification. It does not alter `nova-django-admin-theme`, patch Django globally, or add third-party CAPTCHA services. Designed for the Nova 0.6.0 Admin baseline and ordinary Django templates / same-origin SPAs.

## 仓库范围 / Repository scope

[公开交互演示](https://nova-slider-captcha.mingyueshi.chatgpt.site)运行在 Cloudflare Worker + D1。仓库根目录是可安装的 **Django 组件**，包含同一个原生前端组件、Django 本地演示、Admin 接入、测试和精确兼容矩阵。

`examples/worker-api/` 保留在线演示的服务端出题、校验、限流、单次凭证实现和数据库 schema，并提供最小 Worker 入口。它不是 Django 服务。在线演示的 React 展示页面与 Sites 托管脚手架、项目绑定、数据库实例及部署历史不在此仓库。克隆本仓库不会复制线上服务或其运行数据。

The repository root is the installable Django package. The public demo uses a separate Worker/D1 backend whose portable API source is included under `examples/worker-api/`; the hosted presentation shell and platform-specific deployment scaffold are intentionally excluded. See `SOURCE_PROVENANCE.md` for the export boundary and unchanged runtime hashes.

## Quick start

From a clone of this repository:

```sh
python -m pip install .
```

No wheel or source ZIP is required. If you later build a wheel, install that locally generated file instead.

Add `nova_slider_captcha` to `INSTALLED_APPS`; keep Django's sessions, authentication and CSRF middleware enabled. Include the routes and run migrations:

```python
# urls.py
path("captcha/", include("nova_slider_captcha.urls")),
```

```sh
python manage.py migrate
python manage.py collectstatic
```

For the included local example (development configuration only):

```sh
python -m pip install -e .
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Open `/captcha/` or `/admin/login/`. The example Admin explicitly enables this CAPTCHA. Use your own production settings, secret, hosts, HTTPS and secure cookies; do not deploy the example's development secret.

## Templates and SPAs

Load `nova_slider_captcha/slider.css` and `nova_slider_captcha/slider.js`, then render:

```html
<nova-slider endpoint="/captcha/" purpose="demo"></nova-slider>
```

The custom element initializes CSRF using `GET /captcha/init`, sends same-origin requests, and emits `verified` with `event.detail = {token, expiresIn}`. Keep the token only in the relevant form/component; clear it on reset, expiration or challenge replacement. Never put tokens in URLs or logs. The component owns its hidden `nova_slider_token` field; do not render a duplicate. It emits `captcha-reset` when proof becomes invalid and `captcha-state` for state changes.

For a business endpoint, require CSRF and consume the proof server-side before the protected operation:

```python
from nova_slider_captcha.services import consume

# Purpose is fixed in trusted application code, never taken from the client.
if not consume(request.POST.get("nova_slider_token"), request, purpose="login"):
    return HttpResponseForbidden("Verification required")
# Continue with the separately authorized business operation.
```

`consume` is one-use: failed downstream work may need a fresh challenge. If you place proof consumption inside a larger database transaction, rollback also rolls back consumption. Decide transaction boundaries deliberately, and use separate idempotency controls for payments or other important operations. CAPTCHA does not replace authentication or authorization.

Use a rendered `{% csrf_token %}` value or `/captcha/init`'s `csrfToken` for `X-CSRFToken`; cookie reading is unnecessary, so `CSRF_COOKIE_HTTPONLY=True` is compatible. Pass `credentials: 'same-origin'`. No cross-origin CORS mode is supplied. With `CSRF_USE_SESSIONS=True`, keep the normal SessionMiddleware ordering.

## Explicit Django Admin integration

For a new custom site:

```python
from nova_slider_captcha.admin import SliderCaptchaAdminSite
admin_site = SliderCaptchaAdminSite(name="admin")
# Register your actual models and ModelAdmin classes on this site.
```

For an existing site, set both attributes explicitly during application setup:

```python
from nova_slider_captcha.forms import SliderAdminAuthenticationForm
admin_site.login_form = SliderAdminAuthenticationForm
admin_site.login_template = "nova_slider_captcha/admin_login.html"
```

Both are required: the form enforces verification; the template renders the widget and media. Native Django's login template does not render arbitrary extra fields. The supplied login template extends the selected `admin/login.html`; when Nova 0.6.0 is active it retains Nova's brand panel and extra-field rendering. Keep `nova_admin` before `django.contrib.admin` in `INSTALLED_APPS` and retain Nova's documented context processor. Configure every separately mounted AdminSite: protecting one does not protect another. Authentication/API routes outside that site need their own explicit `consume` call.

Do not silently replace a project's custom authentication form; review its validation and MRO, then compose its checks with the CAPTCHA form. Missing, expired, cross-purpose and consumed tokens all fail closed before password authentication. A wrong password consumes the proof, requiring a new puzzle.

## HTTP contract

All CAPTCHA responses have `Cache-Control: no-store`; all mutating endpoints require JSON, same origin and Django CSRF validation. Initialize the browser session first.

- `GET /captcha/init` → `{csrfToken}`; establishes the anonymous session binding and CSRF cookie/token
- `POST /captcha/challenge` `{purpose: "demo" | "login"}` → `{challengeId, background, piece, width:320, height:160, pieceWidth:44, pieceY, expiresIn:120, maxAttempts:5}`
- `POST /captcha/verify` `{challengeId, x}` → `{ok:true, token, expiresIn:60}` or `{ok:false, code, attemptsRemaining}`
- `POST /captcha/submit` `{token, purpose:"demo"}` → consumes a demo proof and returns `{ok:true, message}`; `/captcha/demo` is an alias

The background and piece are flattened PNG data URLs; no correct X coordinate, image seed, vector geometry, target metadata or verification token is embedded in them. The correct location can naturally be inferred from image pixels: this is a visual puzzle, not a secret-proof system.

`x` is the piece's left edge in natural 320×160 coordinates, range 0–276, tolerance ±4 px; scale pointer coordinates back to natural units. `pieceY` is public and both images use a 44×44 piece box. Wrong valid guesses consume one of five attempts. Malformed values do not consume puzzle attempts but count against verification rate limits. Challenge expiry is 120 seconds; proof expiry is 60 seconds from successful verification.

Errors include `init_required` (409), `rate_limited` (429, `Retry-After: 60`), `invalid_position`, `invalid_challenge`, `expired`, `already_verified`, `incorrect`, `attempts_exhausted`, and `invalid_token` (403 on protected submit). A middleware CSRF rejection may be Django's HTML 403, so clients must handle non-JSON failures. Codes intentionally avoid revealing other sessions' challenge state.

## Security and operations

- State, rate counters and token hashes live in Django's database. No Redis/cache atomicity assumptions; no process-local lock is a security boundary.
- Attempt claims, token issuance and token consumption use conditional SQL updates. Concurrent successes yield one proof; concurrent consumers yield one winner. Never read-then-delete a token in downstream code.
- Session binding uses a random secret stored inside the Django session, hashed with a server-side keyed HMAC. It survives session-key rotation but is cleared by session flush/logout. GET init runs before issuance. Concurrent first-ever tabs can leave an orphan challenge requiring refresh; that is a fail-closed outcome.
- Fixed-window limits default to challenge issuance 20/session/minute and 60/direct-IP/minute; verification 60/session/minute and 120/direct-IP/minute. Customize positive integer values using `NOVA_SLIDER_RATE_LIMITS` keys `issue_session`, `issue_ip`, `verify_session`, `verify_ip`. Two adjacent windows can allow a boundary burst. Limits are supplementary; add edge request/body limits, login/account throttling and operational monitoring.
- IP keys are HMACed. `X-Forwarded-For` and similar arbitrary headers are ignored. Set trusted proxy handling explicitly and ensure Django receives the intended `REMOTE_ADDR`; otherwise all users may share a proxy bucket. Never trust a public client-supplied IP header.
- Run `python manage.py prune_slider_captcha` regularly using your scheduler. It removes rate buckets and challenges safely past their challenge/proof lifetime. Keep tables unregistered from ordinary Admin interfaces; avoid logging raw tokens, session secrets or solution positions.
- HTTPS, secure session/CSRF cookies, a strong rotating deployment secret, correct host/proxy settings and CSP remain the host project's responsibility. For the supplied frontend, allow same-origin script/style/connect resources and `img-src 'self' data:`. Never disable CSRF or accept a client-side success flag.
- This is a minimal self-hosted friction mechanism. Computer vision, image matching, solver farms and replay of browser interactions can solve it. It does not claim commercial risk scoring, fraud prevention or production abuse resistance. Protect credential endpoints with independent account/IP controls and appropriate MFA.
- Database unavailability raises an error and does not grant access. High traffic needs a production database and load testing; the automated concurrency suite uses file-backed SQLite. PostgreSQL/MySQL behavior is not claimed as executed unless recorded in the verification report.

## Accessibility

The frontend supports keyboard positioning and status announcements, but a spatial image puzzle is not independently accessible to blind users and may be unsuitable for motor/cognitive needs. Before production use, provide an equivalent secure nonvisual verification route (for example an authenticated recovery/support flow designed for your threat model). Do not disable verification based on screen-reader detection, query parameters or an “accessible bypass” button. Offer that alternative visibly and test it with actual users. The package cannot choose a safe universal alternative for your application.

## Verification and compatibility

Install metadata matches the theme: Python >=3.10 and Django >=5.2.17,<6.2. Python 3.10 is only an installation boundary, is untested in this package, and is not recommended for new deployments; actual verification targets the seven maintained-version cells below. No result is implied for 3.10 or every possible version combination. Raster generation pins Pillow 12.2.0. See `VERIFICATION.md` and `verification/matrix-results.json` for exact executed combinations, rather than treating install metadata as a test promise.

```sh
python manage.py test tests --settings=tests.settings --noinput
python manage.py makemigrations --check --dry-run
python -m pip install build
python -m build
```

Frontend and real-Django DOM checks (Node is development-only):

```sh
npm ci --ignore-scripts
npm test
# Use the same Python environment where this package is installed.
NOVA_PYTHON=python npm run test:dom
npm run test:worker
```

The repository currently contains no GitHub Actions workflow. The checked-in reports describe executed local validation, not a remote CI run.

Tests cover PNG/public-field contracts, CSRF, strict origin, malformed and extreme coordinates, expiry, tolerance, cross-session/purpose rejection, five-attempt limits, replay, atomic concurrent verification/consumption/rate limiting, cleanup, fail-closed Admin login, and explicit Nova integration.
