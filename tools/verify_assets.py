"""Check every shipped asset, including embedded DOMPurify sources and wheel contents."""

import argparse
import hashlib
import json
import re
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PINS = json.loads((ROOT / "tools/assets.json").read_text())
MANIFEST = "asset-manifest.json"
FULL_BUNDLES = {
    "swagger-ui-bundle.js": 1,
    "swagger-ui-es-bundle.js": 1,
    "editor/swagger-editor.js": 2,
}
VERSION = re.compile(r"DOMPurify(?:\s+|\.version\s*=\s*['\"])(\d+\.\d+\.\d+)")


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def read_assets(path):
    if path.is_dir():
        return {
            p.relative_to(path).as_posix(): p.read_bytes() for p in path.rglob("*") if p.is_file()
        }
    with zipfile.ZipFile(path) as wheel:
        prefix = "swagger_ui/static/"
        return {n[len(prefix) :]: wheel.read(n) for n in wheel.namelist() if n.startswith(prefix)}


def verify(assets, check_manifest=True):
    expected = PINS["dompurify"]
    if tuple(map(int, expected.split("."))) < (3, 4, 16):
        raise ValueError(
            "DOMPurify must be at least 3.4.16; check current advisories before updating"
        )
    if check_manifest:
        manifest = json.loads(assets[MANIFEST])
        actual = {n: sha256(data) for n, data in assets.items() if n != MANIFEST}
        if manifest["sha256"] != actual or manifest["build"] != PINS:
            raise ValueError(
                "Asset inventory/checksums or build provenance differ from the manifest"
            )

    embedded = {}
    for name, data in assets.items():
        if not name.endswith((".js", ".map", ".LICENSE.txt")):
            continue
        content = data.decode("utf-8")
        versions = set(VERSION.findall(content))
        if versions - {expected}:
            raise ValueError(f"{name}: vulnerable/unexpected DOMPurify {versions}")
        if not name.endswith(".js.map"):
            continue
        source_map = json.loads(content)
        for source, code in zip(source_map["sources"], source_map.get("sourcesContent", [])):
            if code and set(VERSION.findall(code)) - {expected}:
                raise ValueError(f"{name}: unexpected DOMPurify in {source}")
            if "/dompurify/" not in source.lower():
                continue
            if not code or sha256(code.encode()) not in PINS["dompurify_source_sha256"]:
                raise ValueError(f"{name}: unrecognized DOMPurify source {source}")
            embedded.setdefault(name.removesuffix(".map"), []).append(expected)

    for name, copies in FULL_BUNDLES.items():
        if embedded.get(name) != [expected] * copies:
            raise ValueError(f"{name}: expected exactly {copies} verified DOMPurify sources")
        assignments = re.findall(
            r"\.version\s*=\s*([\"'`])" + re.escape(expected) + r"\1", assets[name].decode()
        )
        if len(assignments) != copies:
            raise ValueError(f"{name}: patched DOMPurify version missing from executable bundle")
    return embedded


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", type=Path, default=[ROOT / "swagger_ui/static"])
    args = parser.parse_args()
    for path in args.paths:
        embedded = verify(read_assets(path))
        print(f"{path}: verified all asset hashes; embedded DOMPurify {embedded}")


if __name__ == "__main__":
    main()
