# Optional Worker API example

This is the public demonstration's Worker/D1 API implementation exported without its hosting-provider project binding, database ID, deployment history, credentials or React presentation shell. The Django package is the primary integration deliverable; using this example is optional.

## Included

- `captcha.mjs` and `puzzle.mjs`: unchanged server logic from the verified 0.1.0 demonstration
- `schema.sql`: unchanged D1 schema migration; apply once to an empty database under your own deployment tooling
- `worker.mjs`: minimal fetch entrypoint exposing only `/captcha/init`, `/captcha/challenge`, `/captcha/verify` and `/captcha/submit`
- `tests/backend.test.mjs`: same 13 SQLite-backed backend cases, with import paths adjusted for this directory

Configure a D1 binding named `DB` and enable Cloudflare's `nodejs_compat` support for `node:zlib`. No account, database or hosting resource is created by this repository. Do not replay the initial schema on an existing database. No deployment command or live resource identifier is supplied.

Serve the shared `src/nova_slider_captcha/static/nova_slider_captcha/slider.js` and `slider.css` from the same origin as these endpoints. Mount `<nova-slider endpoint="/captcha/" purpose="demo"></nova-slider>`. GET init establishes an HttpOnly session and returns a CSRF token. POST calls require exact Origin and X-CSRFToken. Demo submission consumes a one-use proof but performs no real business operation.

The browser protocol matches Django's dimensions, challenge/proof lifetimes and core request/response fields. Error codes, limit counts and database implementation differ; this is not a byte-identical Django backend. In particular the Worker demo issues only fixed purposes demo/login and uses trusted Cloudflare edge IP headers, while Django uses its configured direct peer address and keyed hashes.

A production host must set HTTPS, suitable security headers, trusted-proxy configuration and abuse controls. In the public Site, the surrounding hosting wrapper adds frame-ancestors / X-Frame-Options protections; that wrapper is excluded here. Neither version guarantees resistance to image matching or provides a universal nonvisual alternative.

Test from the repository root with Node 24:

```sh
npm run test:worker
```

This test uses an in-memory SQLite adapter with actual SQL. It does not claim to deploy Cloudflare or replace tests in your chosen runtime.
