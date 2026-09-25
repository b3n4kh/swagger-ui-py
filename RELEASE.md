# Release 26.9.25: bundled DOMPurify security update

Prepared for `swagger-ui-py-x`; do not tag or publish without maintainer approval.
The tag workflow publishes to GitHub Releases and PyPI automatically.

## Versions and scope

Checked upstream GitHub releases, npm metadata, and DOMPurify advisories on
2026-09-25:

- [Swagger UI 5.33.0](https://github.com/swagger-api/swagger-ui/releases/tag/v5.33.0)
  is current, but its prebuilt bundle contains DOMPurify 3.4.13.
- [DOMPurify 3.4.16](https://github.com/cure53/DOMPurify/releases/tag/3.4.16)
  is current and fixes
  [GHSA-6688-9rhm-gjv2](https://github.com/cure53/DOMPurify/security/advisories/GHSA-6688-9rhm-gjv2)
  (affected through 3.4.15) and
  [GHSA-p98j-92pf-mc4p](https://github.com/cure53/DOMPurify/security/advisories/GHSA-p98j-92pf-mc4p)
  (3.4.13–3.4.15). Earlier advisories also affect the copies previously shipped.
- [Swagger Editor 5.8.8](https://github.com/swagger-api/swagger-editor/releases/tag/v5.8.8)
  is current and is included, with its Swagger UI React **5.33.0** dependency.
  Its OpenAPI and AsyncAPI renderers both use patched DOMPurify **3.4.16**.

Both full Swagger UI UMD/ES bundles embed one verified DOMPurify 3.4.16 copy.
The Editor UMD bundle includes two verified copies (ESM and CommonJS, for its
OpenAPI and AsyncAPI renderers), both 3.4.16. UI core bundles externalize
dependencies. Generated maps, Editor workers, bundled React runtime, and license
notices are shipped alongside the bundles. The old Editor maps contained
DOMPurify 2.2.0/2.3.3; the old UI in this checkout contained 3.1.6 (the published
26.2.18 release contained 3.2.6). All are replaced, including stale source maps.

No Python API, Flask blueprint override, documentation template, or OAuth
initialization changes. The Editor template mounts the v5 React component, loads
the configured spec, and sets the worker base URL under the configured prefix.
UI 5.33.0's OAuth callback now uses its companion `oauth2-redirect.js`; both files
are shipped. This release verifies DOMPurify remediation; it is not a
comprehensive audit of every transitive JavaScript dependency.

## Reproduce or update assets

Use Python 3.12+, Node **22.22.0**, npm **10.9.4**. Node/npm are required only for
asset maintenance; the Python package serves committed assets without JavaScript
build tooling. npm is used because these upstream projects build with npm/webpack.

```bash
uv sync --frozen --all-extras --python 3.12
uv run python tools/update.py --ui --editor
uv run python tools/verify_assets.py
```

`tools/assets.json` pins upstream tags, commits, archive SHA-256 values, DOMPurify,
its source hash, toolchain, and deterministic build time. The updater verifies
archives, uses the checked-in `*-package-lock.json` files with `npm ci`, disables
install scripts, and explicitly applies Editor's checked-in AsyncAPI parser
patch. It normalizes upstream build metadata and enables full source maps for inspection.
Editor uses upstream's UMD build with a small `tools/editor-entry.jsx` mount
entry, bundling React and its renderer together, plus upstream's worker bundles.
The unused Node path fallback in web-tree-sitter is fixed to `/` to prevent
randomized build paths in the output. React uses production mode without a Node
process shim. Browser polyfills (including upstream's filesystem shim) resolve
before Vite's Node externalization so the AsyncAPI renderer can load. The worker
resolver honors `MonacoEnvironment.baseUrl` on nested routes. The updater stages
and verifies all outputs before copying them into the package, and never
regenerates templates. Use `--no-clean` to retain build output.
If an existing npm cache has permission problems, set `npm_config_cache` to a new
writable directory; no global npm installation is needed.

For future upgrades, first recheck current upstream releases and
[all DOMPurify advisories](https://github.com/cure53/DOMPurify/security/advisories).
Edit `tools/assets.json`, including independently verified archive/source hashes,
then use `--refresh-lock` with the selected `--ui`/`--editor` flags. Review both
npm locks; every DOMPurify resolution must match the pin. Rebuild **both** products
when changing DOMPurify. Commit the locks, generated assets/manifest, updated
README/release notes, and matching `pyproject.toml`/`uv.lock` release versions.
Neither installing a Python dependency nor adding a second sanitizer script
updates the embedded code.

`tools/verify_assets.py` checks the complete static file inventory and SHA-256
manifest, scans JavaScript/license/source-map content, requires exact pinned
ESM/CommonJS DOMPurify source bytes in each full bundle, and checks the executable version
assignment. It accepts a static directory or wheel paths. CI now fails on test
failures and inspects built wheels before release.

## Pre-release validation

```bash
uv sync --frozen --all-extras --python 3.12
uv run ruff check .
uv run isort --line-width=100 --check-only --force-single-line-imports .
uv run pytest -q test/
uv run python tools/verify_assets.py
uv build --out-dir dist/26.9.25
uv run python tools/verify_assets.py dist/26.9.25/*.whl
uvx --from twine==6.2.0 twine check dist/26.9.25/*
```

Repeat tests with Python 3.13; Python 3.12 is the minimum supported version. Install the wheel in
a clean environment outside the checkout and smoke-test in a browser using a
Flask app with a non-default URL prefix, custom `blueprint_name`, local OpenAPI
configuration, Editor enabled, and OAuth client/PKCE configuration. A local fixture
is provided (all credentials/tokens are synthetic):

```bash
uv venv --python 3.12 /tmp/swagger-wheel-smoke
uv pip install --python /tmp/swagger-wheel-smoke/bin/python dist/26.9.25/*.whl flask
cd /tmp
/tmp/swagger-wheel-smoke/bin/python /absolute/path/to/swagger-ui-py/tools/smoke_app.py
```

Open `http://127.0.0.1:8765/private/docs` and `/private/docs/editor`; both load the
configured local spec. Confirm:

- UI and Editor render; spec operations and sanitized Markdown appear.
- Monaco editing and validation workers load beneath the custom static prefix.
- Raw HTML/event-handler payloads do not execute in either renderer.
- Custom parameters and `initOAuth` settings reach the live UI.
- Authorization opens, and the local OAuth callback returns valid code/state;
  mismatched state and OAuth errors follow the upstream error paths.
- UI CSS, full bundles, presets, callback HTML/JS, and config load successfully.

## Validation recorded on 2026-09-25

- Python 3.12 and 3.13: 55 tests passed on each; only dependency deprecation warnings.
- Ruff, isort, Deno lint/format, and `git diff --check` passed.
- Clean source rebuilds produced byte-identical UI/Editor assets and maps.
- Built wheel and sdist; Twine metadata checks passed. The actual wheel's entire
  static inventory and embedded DOMPurify ESM/CommonJS sources passed verification.
- Chromium against a clean installed wheel: custom Flask prefix/blueprint and custom CSS,
  configured OpenAPI spec, UI and Editor Markdown sanitization, Monaco workers,
  AsyncAPI preview, and local OAuth authorization-code/PKCE flow passed.
  Callback state-mismatch warnings and access-denied errors were also exercised.
  Final Editor OpenAPI/AsyncAPI runs had no browser console errors or warnings.

## Publish only after explicit approval

From the reviewed commit, with a clean working tree, run the validation above.
Then, only with approval to tag and publish:

```bash
git push origin master
git tag -a v26.9.25 -m '26.9.25: rebuild Swagger UI and Editor with DOMPurify 3.4.16'
git push origin v26.9.25
```

The `Releases` workflow checks that the tag matches package metadata, runs tests,
verifies assets, builds wheel/sdist, inspects the actual wheel, creates the GitHub
release, and publishes via PyPI trusted publishing. Do not also run a manual
upload. Verify the workflow succeeded, PyPI reports 26.9.25, and a freshly
downloaded wheel passes `tools/verify_assets.py`.

For deployment, pin `swagger-ui-py-x==26.9.25`, restart the consuming application,
and repeat its docs/Editor/OAuth smoke checks. PyPI versions cannot be overwritten;
if a release regression occurs, prepare a new patch release. Rolling back to
26.2.18 restores vulnerable assets and is not a security fix.
