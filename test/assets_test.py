"""Guard the actual vendored bytes, including copies hidden in Editor/source maps."""

import json
import zipfile

import pytest

from tools.verify_assets import FULL_BUNDLES
from tools.verify_assets import ROOT
from tools.verify_assets import read_assets
from tools.verify_assets import verify


def test_shipped_assets_and_wheel_reader(tmp_path):
    assets = read_assets(ROOT / "swagger_ui/static")
    assert set(verify(assets)) == set(FULL_BUNDLES)
    wheel = tmp_path / "assets.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        for name, data in assets.items():
            archive.writestr(f"swagger_ui/static/{name}", data)
    assert verify(read_assets(wheel)) == verify(assets)
    assets["obsolete-bundle.js"] = b"/* DOMPurify 2.3.3 */"
    with pytest.raises(ValueError, match="inventory"):
        verify(assets)


@pytest.mark.parametrize("bundle", FULL_BUNDLES)
def test_reject_unpatched_or_missing_embedded_source(bundle):
    assets = read_assets(ROOT / "swagger_ui/static")
    source_map = bundle + ".map"
    assets[source_map] = assets[source_map].replace(b"DOMPurify 3.4.16", b"DOMPurify 3.4.15")
    with pytest.raises(ValueError, match="DOMPurify"):
        verify(assets, check_manifest=False)
    assets = read_assets(ROOT / "swagger_ui/static")
    content = json.loads(assets[source_map])
    content.pop("sourcesContent")
    assets[source_map] = json.dumps(content).encode()
    with pytest.raises(ValueError, match="expected exactly"):
        verify(assets, check_manifest=False)
