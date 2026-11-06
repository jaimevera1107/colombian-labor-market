"""Non-destructive H21 certification gates and failure-mode tests."""
import csv
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from icml.operations.certification import audit, write_report
from icml.operations.frozen_products import EXPECTED_IDS


def _fake_bundle(root: Path, catalog: Path, lock: Path) -> Path:
    code = root
    (code / "configs/golden").mkdir(parents=True)
    (code / "requirements").mkdir(parents=True)
    (code / "configs/golden/rc1_catalog.toml").write_bytes(catalog.read_bytes())
    (code / "requirements/lock-py312.txt").write_bytes(lock.read_bytes())
    # An empty fake package must not pass the eight-product gate.
    (root / "datos/2_procesamiento/productos_congelados/catalogo_h19").mkdir(parents=True)
    with (root / "datos/2_procesamiento/productos_congelados/catalogo_h19/19_catalogo_unificado.csv").open("w") as f:
        writer = csv.DictWriter(f, fieldnames=["producto", "ruta", "sha256", "evidencia", "estatus", "universo"])
        writer.writeheader()
        for item in sorted(EXPECTED_IDS):
            writer.writerow({"producto": item, "ruta": item + ".csv", "sha256": "0"*64,
                             "evidencia": "test", "estatus": "experimental", "universo": "test"})
    return root


def test_h21_missing_products_and_original_rc1_never_certified(tmp_path):
    source = Path(__file__).resolve().parents[2]
    bundle = _fake_bundle(tmp_path, source / "configs/golden/rc1_catalog.toml",
                          source / "requirements/lock-py312.txt")
    result = audit(bundle)
    assert result["release_gate"] == "BLOCKED"
    assert result["golden"]["status"] == "NOT_EXECUTED_EXTERNAL_ARTIFACTS_ABSENT"
    assert result["golden"]["expected"] == 102
    assert result["rc1_catalog"]["unique_paths"] == 101
    assert result["products"]["status"] == "FAIL"


def test_h21_provided_incomplete_golden_fails_closed(tmp_path):
    source = Path(__file__).resolve().parents[2]
    bundle = _fake_bundle(tmp_path, source / "configs/golden/rc1_catalog.toml",
                          source / "requirements/lock-py312.txt")
    golden = tmp_path / "external"; golden.mkdir()
    result = audit(bundle, golden)
    assert result["golden"]["verified"] == 0
    assert result["golden"]["missing"] == 102
    assert result["release_gate"] == "BLOCKED"


def test_h21_refuses_to_overwrite_report(tmp_path):
    source = Path(__file__).resolve().parents[2]
    bundle = _fake_bundle(tmp_path, source / "configs/golden/rc1_catalog.toml",
                          source / "requirements/lock-py312.txt")
    report = tmp_path / "report.json"
    write_report(bundle, report)
    with pytest.raises(FileExistsError):
        write_report(bundle, report)


def test_version_matches_build_metadata():
    import tomllib
    from icml import __version__
    source_root = Path(__file__).resolve().parents[2]
    with (source_root / "pyproject.toml").open("rb") as stream:
        installed_version = tomllib.load(stream)["project"]["version"]
    assert __version__ == installed_version
