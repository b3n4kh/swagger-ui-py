"""Rebuild pinned Swagger assets without rewriting this fork's templates or Python API."""

import argparse
import json
import os
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request
from pathlib import Path

from verify_assets import MANIFEST
from verify_assets import PINS
from verify_assets import ROOT
from verify_assets import read_assets
from verify_assets import sha256
from verify_assets import verify


def run(args, cwd, env):
    subprocess.run(args, cwd=cwd, env=env, check=True)


def build(product, work, refresh_lock):
    pin = PINS[product]
    archive = work / f"{product}.tar.gz"
    url = f"https://codeload.github.com/{pin['repo']}/tar.gz/refs/tags/v{pin['version']}"
    with urllib.request.urlopen(url, timeout=120) as response:
        archive.write_bytes(response.read())
    if sha256(archive.read_bytes()) != pin["archive_sha256"]:
        raise ValueError(f"{product}: upstream source archive checksum mismatch")
    with tarfile.open(archive) as source:
        source.extractall(work, filter="data")
    repo = work / f"swagger-{product}-{pin['version']}"
    package_path = repo / "package.json"
    package = json.loads(package_path.read_text())
    if "dompurify" in package["dependencies"]:
        package["dependencies"]["dompurify"] = PINS["dompurify"]
    package.setdefault("overrides", {})["dompurify"] = PINS["dompurify"]
    package_path.write_text(json.dumps(package, indent=2) + "\n")

    env = dict(os.environ, TZ="UTC", LANG="C", CI="true")
    env.pop("NODE_ENV", None)
    env.pop("BABEL_ENV", None)
    lock = ROOT / f"tools/{product}-package-lock.json"
    npm_flags = ["--ignore-scripts", "--legacy-peer-deps", "--no-audit", "--no-fund"]
    if refresh_lock:
        run(["npm", "install", "--package-lock-only", *npm_flags], repo, env)
        shutil.copyfile(repo / "package-lock.json", lock)
    else:
        shutil.copyfile(lock, repo / "package-lock.json")
    locked = json.loads(lock.read_text())["packages"]
    purifier = [v for k, v in locked.items() if k.endswith("/dompurify")]
    if not purifier or any(v["version"] != PINS["dompurify"] for v in purifier):
        raise ValueError(f"{product}: lockfile contains missing/unpatched DOMPurify")
    run(["npm", "ci", *npm_flags], repo, env)
    if product == "editor":
        run(["npm", "run", "prepare"], repo, env)
        # Its Node-only fallback otherwise gets a random polyfill module ID and
        # embeds the temporary build path. This fallback is unused in browsers.
        tree_sitter = repo / "node_modules/web-tree-sitter/tree-sitter.js"
        source = tree_sitter.read_text()
        if source.count("__dirname") != 1:
            raise ValueError("web-tree-sitter Node fallback changed upstream")
        tree_sitter.write_text(source.replace("__dirname", json.dumps("/")))
        for filename in ("vite.config.umd.js", "vite/configs/worker-configs.umd.js"):
            config = repo / filename
            config.write_text(config.read_text().replace("sourcemap: false", "sourcemap: true"))
        shutil.copyfile(ROOT / "tools/editor-entry.jsx", repo / "python-entry.jsx")
        config = repo / "vite.config.umd.js"
        config.write_text(
            config.read_text()
            .replace("src/App.tsx", "python-entry.jsx")
            .replace("external: ['react', 'react-dom']", "external: []")
        )
        defines = {
            "PACKAGE_VERSION": json.dumps(pin["version"]),
            "GIT_COMMIT": json.dumps(pin["commit"]),
            "GIT_DIRTY": "false",
            "BUILD_TIME": json.dumps(PINS["build_time"]),
            "process.env.NODE_ENV": json.dumps("production"),
        }
        config.write_text(
            config.read_text().replace(
                "  configFile: false,",
                "  configFile: false,\n  define: " + json.dumps(defines) + ",",
            )
        )
        workers = repo / "vite/configs/worker-configs.umd.js"
        workers.write_text(
            workers.read_text().replace(
                "  configFile: false,",
                '  configFile: false,\n  define: { "process.env.NODE_ENV": JSON.stringify("production") },',
            )
        )
        for filename in ("vite.config.umd.js", "vite/configs/worker-configs.umd.js"):
            config = repo / filename
            config.write_text(
                config.read_text().replace(
                    "nodePolyfills()",
                    "nodePolyfills({ exclude: ['**/react/**', '**/react-dom/**', '**/scheduler/**'] })",
                )
            )
        # Resolve Node built-ins before Vite externalizes them; AsyncAPI's Avro
        # parser imports util.debuglog even when rendering a JSON-schema message.
        polyfills = (
            "nodePolyfills({ exclude: ['**/react/**', '**/react-dom/**', '**/scheduler/**'] })"
        )
        early_polyfills = "{ ..." + polyfills + ", enforce: 'pre' }"
        for filename, plugins in (
            ("vite.config.umd.js", "rewriteEditorWorkerImport(), react()"),
            ("vite/configs/worker-configs.umd.js", "inlineAllWasms()"),
        ):
            config = repo / filename
            config.write_text(
                config.read_text()
                .replace(
                    f"plugins: [{plugins}]", f"plugins: [fsShim(), {early_polyfills}, {plugins}]"
                )
                .replace(f"      plugins: [{polyfills}],", "")
            )
        config = repo / "vite.config.umd.js"
        config.write_text(
            "import { fsShim } from './vite/plugins/fs-shim.js';\n" + config.read_text()
        )
        # Upstream's UMD worker URLs walk up two directories. Honor the configured
        # static prefix instead, so workers also work on nested Flask blueprints.
        worker = repo / "vite/plugins/rewrite-editor-worker-import.js"
        original = """    const _meta = new URL('../../${filename}', import.meta.url);
    const _url = _meta.protocol === 'file:'
      ? new URL('./${filename}', globalThis.MonacoEnvironment?.baseUrl ?? location.origin)
      : _meta;"""
        content = worker.read_text()
        if content.count(original) != 1:
            raise ValueError("Editor worker URL construction changed upstream")
        worker.write_text(
            content.replace(
                original,
                "    const _url = new URL('./${filename}', globalThis.MonacoEnvironment.baseUrl);",
            )
        )
        run(["npm", "run", "build:bundle:umd"], repo, env)
        return repo

    builder = repo / "webpack/_config-builder.js"
    config = builder.read_text()
    replacements = {
        "const gitInfo = getRepoInfo()": 'const gitInfo = { hash: "pinned-source", dirty: false }',
        "new Date().toUTCString()": json.dumps(PINS["build_time"]),
        "return completeConfig": 'completeConfig.devtool = "source-map"\n  return completeConfig',
    }
    for old, new in replacements.items():
        if config.count(old) != 1:
            raise ValueError(f"{product}: upstream webpack configuration changed: {old}")
        config = config.replace(old, new)
    builder.write_text(config)
    dist = repo / "dist"
    # Never leave a prebuilt bundle or stale source map in the build output.
    for path in dist.iterdir():
        if path.suffix in (".js", ".map") or path.name.endswith(".LICENSE.txt"):
            path.unlink()
    run(["npm", "run", "build"], repo, env)
    return repo


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ui", action="store_true")
    parser.add_argument("--editor", action="store_true")
    parser.add_argument("--refresh-lock", action="store_true", help="Regenerate selected npm locks")
    parser.add_argument("--no-clean", action="store_true", help="Keep temporary build files")
    args = parser.parse_args()
    if not args.ui and not args.editor:
        parser.error("Select --ui and/or --editor (versions are pinned in tools/assets.json)")
    for command in ("node", "npm"):
        actual = subprocess.check_output([command, "--version"], text=True).strip().lstrip("v")
        if actual != PINS[command]:
            parser.error(f"Use {command} {PINS[command]}, found {actual}")
    work = Path(tempfile.mkdtemp(prefix="swagger-assets-"))
    print(f"Build directory: {work}", flush=True)
    try:
        static = ROOT / "swagger_ui/static"
        staged = work / "static"
        shutil.copytree(static, staged)
        for product in ("ui", "editor"):
            if not getattr(args, product):
                continue
            repo = build(product, work, args.refresh_lock)
            for old in staged.glob(f"swagger-{product}*"):
                old.unlink()
            if product == "editor":
                shutil.rmtree(staged / "editor", ignore_errors=True)
                (staged / "validator.worker.js.LICENSE.txt").unlink(missing_ok=True)
                (staged / "LICENSE-swagger-editor").unlink(missing_ok=True)
                shutil.copytree(repo / "dist/umd", staged / "editor")
                shutil.copyfile(
                    repo / "dist/swagger-editor.css", staged / "editor/swagger-editor.css"
                )
                for react in ("react", "react-dom"):
                    shutil.copyfile(
                        repo / f"node_modules/{react}/LICENSE", staged / f"editor/LICENSE-{react}"
                    )
                for license_file in (repo / "LICENSES").iterdir():
                    shutil.copyfile(license_file, staged / f"editor/LICENSE-{license_file.name}")
                shutil.copyfile(repo / "NOTICE", staged / "editor/NOTICE")
            else:
                for path in (repo / "dist").iterdir():
                    if path.is_file() and (
                        path.name.startswith("swagger-ui")
                        or path.name.endswith(".LICENSE.txt")
                        or path.name
                        in (
                            "oauth2-redirect.html",
                            "oauth2-redirect.js",
                            "index.css",
                            "favicon-16x16.png",
                            "favicon-32x32.png",
                        )
                    ):
                        shutil.copyfile(path, staged / path.name)
                shutil.copyfile(repo / "LICENSE", staged / "LICENSE-swagger-ui")
                shutil.copyfile(repo / "LICENSE", staged / "LICENSE")
            shutil.copyfile(repo / "node_modules/dompurify/LICENSE", staged / "LICENSE-DOMPurify")
        assets = read_assets(staged)
        verify(assets, check_manifest=False)
        manifest = {
            "build": PINS,
            "sha256": {n: sha256(b) for n, b in sorted(assets.items()) if n != MANIFEST},
        }
        (staged / MANIFEST).write_text(json.dumps(manifest, indent=2) + "\n")
        verify(read_assets(staged))
        for old in static.rglob("*"):
            if old.is_file() and not (staged / old.relative_to(static)).exists():
                old.unlink()
        shutil.copytree(staged, static, dirs_exist_ok=True)
        print("Verified assets installed. Review README versions and release metadata.")
    finally:
        if not args.no_clean:
            shutil.rmtree(work)


if __name__ == "__main__":
    main()
