# Verification · 2026-10-05

Baseline: Nova Django Admin Theme **0.6.0**, source byte-equivalent to the public GitHub import [`b0fd37e528a6ad76bec646a68d02f017cde3c4b9`](https://github.com/mingyueshi/nova-admin/commit/b0fd37e528a6ad76bec646a68d02f017cde3c4b9). Nova source was referenced for integration, not modified or repackaged into this app.

## Executed Python / Django matrix

All seven exact cells passed **31 tests per profile**, with four profiles each: source/native Admin, source/Nova Admin, installed wheel/native Admin, installed wheel/Nova Admin. Total: **28 passing profiles, 868 test executions**, with no skips. Each profile also passed Django system checks and migration-drift checks. Each cell passed `pip check` and source/wheel import-origin assertions. After the final CSS-only compatibility update, both installed-wheel profiles were rerun in all seven cells; those repeat executions are retained in the logs and are not added to the 868 unique-profile total.

| Python | Django | Pillow | Four profiles |
|---|---|---|---|
| 3.11.17 | 5.2.17 | 12.2.0 | Passed |
| 3.12.15 | 5.2.17 | 12.2.0 | Passed |
| 3.12.15 | 6.0.8 | 12.2.0 | Passed |
| 3.12.15 | 6.1.1 | 12.2.0 | Passed |
| 3.13.16 | 6.1.1 | 12.2.0 | Passed |
| 3.14.8 | 5.2.17 | 12.2.0 | Passed |
| 3.14.8 | 6.1.1 | 12.2.0 | Passed |

Platform: Linux x86-64, standard GIL CPython. Exact Python runtimes were installed in isolated task directories using uv 0.12.22; actual runtime/imported Django/Pillow versions were independently asserted. Dependency values were Django as above, Pillow 12.2.0, asgiref 3.12.1 and sqlparse 0.6.0. Build tools were setuptools 84.0.0 / wheel 0.48.0. Concurrency used **file-backed SQLite** and fresh thread-local database connections.

Security tests include anonymous session initialization, PNG-only/public response contract, tolerance boundaries, giant/NaN/infinite/negative coordinates, nested malformed JSON, expiry, cross-session/purpose rejection, one-use proof replay, fifth-attempt lockout, direct-IP/session rate limits, untrusted forwarded-header rejection, same-origin restrictions even with a trusted CSRF origin, real CSRF middleware rejection, protected POST method restrictions, safe pruning, and fail-closed Admin form validation before password authentication. Eight-/twelve-thread races verify single token issuance, single consume winner, exact five-attempt cap and atomic rate claims.

Nova integration asserts its actual `nova-login-layout` renders; the native profile asserts that Nova-specific markup is absent. Successful Admin login and failed-password proof consumption are exercised.

The install boundary matches Nova (`Python>=3.10`, `Django>=5.2.17,<6.2`), but **Python 3.10 was not tested and is not recommended for new deployment**. Metadata is not a claim that every possible combination is tested.

## Executed JavaScript matrix

The final shared widget passed **13 cases per Node version**, 39 executions total:

| Node | bundled npm | jsdom | Widget cases | DOM + Django cases |
|---|---|---|---|---|
| 22.23.3 | 10.9.9 | 26.1.0 | 13 passed | 9 passed |
| 24.21.0 | 11.19.0 | 26.1.0 | 13 passed | 9 passed |
| 26.10.0 | 11.19.1 | 26.1.0 | 13 passed | 9 passed |

Each Node runtime is the official Linux x64 binary, checked against its official HTTPS SHA-256 list. Each version used a separate clean jsdom installation with lifecycle scripts disabled. Runtime provenance is in `verification/node-downloads.json`; outcomes and immutable widget hash are in `verification/node-results.json`.

Shared widget cases cover keyboard submission, duplicate-submit gating, retry/fifth-attempt failure, refresh, late responses, HTML CSRF failures, session-init cache recovery, challenge/proof expiry, pointer cancel, network recovery, reconnects, and multiple widgets. This is a frontend development matrix, not a runtime Node dependency for Django.

An additional **nine DOM-to-real-Django test-client checks per Node version** (27 total) pass against Python 3.12.15 / Django 5.2.17 with actual CSRF enforcement and fresh disposable databases. They cover wrong-answer retry, Enter submission, protected demo consumption/replay, repeated refresh, exactly one populated Admin hidden field, proof expiration, five-error lockout, and a delayed protected submission that must not clear a newly solved replacement proof. Image decoding is stubbed for DOM tests; PNG validity/dimensions are verified independently by Pillow tests.

## Artifacts and reproducibility

- `verification/matrix-results.json`: exact Python cells and profile status
- `verification/python-runtime-versions.json`: observed versions
- `verification/python-*.log`: full final matrix logs
- `verification/node-downloads.json`: official URLs and matching SHA-256 values
- `verification/node-results.json`, `widget-node-*.log`: exact frontend results
- `verification/dom-results.json`, `dom-node-*.log`: real Django / DOM integration results
- `verification/artifact-sha256.json`: tested wheel and asset hashes
- `scripts/test_matrix.py`: isolated source/wheel/native/Nova runner
- `tests/widget.test.mjs`: shared widget regression suite
- `scripts/test_dom.cjs`, `scripts/dom_bridge.py`: test-only stdio bridge; not a deployed HTTP endpoint

All runtime package files and frontend assets inside the built wheel were byte-compared with final source. The wheel has no test solution bridge, demo database, credentials, node_modules, or development server.

## Not executed / limits

- PostgreSQL, MySQL/MariaDB, production load, multi-host/proxy deployment and any real application beyond the supplied test/example sites
- Python 3.10, other Python/Django Cartesian combinations, PyPy, free-threaded builds, Windows, macOS or ARM64
- Real browser layout/pixel, touch-device, keyboard focus appearance or assistive-technology validation of the Django-rendered page: local Chromium was blocked by the execution environment's Unix-socket restrictions. DOM checks do not substitute for these
- Genuine bot resistance, computer-vision resistance or a secure nonvisual verification alternative

Public Site deployment/browser checks are a separate deliverable and are not counted as Django package tests. A production host still needs its own equivalent secure nonvisual route, throttling/MFA, secure deployment settings and manual browser verification.

## Repository export note

The runtime files under `src/` are byte-identical to the tested release snapshot. Documentation/install instructions and historical-log root paths were adjusted for this public source repository. Historical wheel digest refers to that previously tested artifact; rebuilding with updated README metadata can produce a different wheel digest. No wheel or source archive is checked in. There is no GitHub Actions workflow in this export; local historical results are not a remote CI pass. See `SOURCE_PROVENANCE.md`.
