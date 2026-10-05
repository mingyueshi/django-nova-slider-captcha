# Source provenance and export boundary

This is the clean source export of the verified Nova Slider CAPTCHA **0.1.0** snapshot from 2026-10-05. It starts a new repository history; no prior hosting repository history or deployment data is imported.

## Included

- Installable Django package under `src/nova_slider_captcha/`, including migrations, templates, Admin integration and the vanilla `nova-slider` frontend
- Runnable local Django example under `demo/` and its `manage.py`
- Backend, frontend and real-Django DOM tests, compatibility scripts, exact historical matrix results and validation logs
- Optional portable Worker/D1 API logic and schema under `examples/worker-api/`

The Django runtime files and optional Worker API/puzzle/schema files are unchanged from their verified snapshot. `verification/source-runtime-sha256.json` lists every included runtime file's SHA-256. Test assertions in the Worker suite are unchanged; only import/schema paths were adjusted for relocation. The small optional Worker fetch entrypoint is new export glue and is syntax-checked separately.

## Export-only changes

- The original standalone Django package becomes the repository root
- README installs directly from a clone and explicitly explains the public demonstration's different backend
- Historical execution-log root paths are redacted using `<PROJECT_ROOT>`, `<MATRIX_ROOT>`, `<RUNTIMES_ROOT>` and `<PIP_CACHE>`; test outcomes/version evidence remain intact
- The ignore list excludes local secrets, databases, build/cache output and hosting metadata
- The optional Worker example documents platform bindings but carries no real deployment IDs or credentials

## Deliberately excluded

The hosted demonstration's React presentation shell, Sites-specific scaffold and project/database binding are not exported. No `.env` values, user sessions, live database, local Python/Node environments, cache, archive/wheel, private Git history or hosting write credentials are included. The public demonstration remains unchanged by this repository publication.

The package is tested against Nova Admin Theme 0.6.0, whose public source is [mingyueshi/nova-admin at b0fd37e](https://github.com/mingyueshi/nova-admin/commit/b0fd37e528a6ad76bec646a68d02f017cde3c4b9). The theme is not vendored into this repository.

Historical results and untested platform/security boundaries are detailed in `VERIFICATION.md`. The repository currently has no GitHub Actions workflow; do not interpret absent remote checks as a pass. New local relocation checks are summarized in `verification/export-checks.json`.
