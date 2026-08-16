from __future__ import annotations

import tomllib
from pathlib import Path

from silverstar_flp.app.version import PRODUCT_NAME, __version__
from silverstar_flp.version import __version__ as compatibility_version


def test_version_has_one_runtime_authority_and_dynamic_packaging_metadata() -> None:
    root = Path(__file__).resolve().parents[1]
    payload = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    assert PRODUCT_NAME == "SilverStar_FLP"
    assert __version__ == compatibility_version == "0.0.2"
    assert "version" not in payload["project"]
    assert "version" in payload["project"]["dynamic"]
    assert payload["tool"]["setuptools"]["dynamic"]["version"]["attr"] == (
        "silverstar_flp.app.version.__version__"
    )
