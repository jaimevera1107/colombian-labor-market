"""H26 source organization and future-vintage isolation."""
import json
from pathlib import Path
import pytest
from icml.operations.source_catalog import audit_catalog, stage_new_source
from icml.departmental.pipeline import load_departmental_config
from icml.departmental.annex import DepartmentAnnexReader

@pytest.fixture(scope="module")
def vintage():
    root = Path(__file__).resolve().parents[2]
    if not (root / "datos/2_procesamiento/catalogos/catalogo_fuentes.json").exists():
        pytest.skip("Full H26 checkpoint not mounted")
    return root

def test_source_catalog_all_active_paths_are_consistent(vintage):
    report = audit_catalog(vintage)
    assert report["status"] == "PASS", report["issues"]
    catalog=json.loads((vintage / "datos/2_procesamiento/catalogos/catalogo_fuentes.json").read_text(encoding="utf-8"))
    assert report["count"] == len(catalog["sources"])
    assert report["unique_paths"] == len({v["path"] for v in catalog["sources"].values()})

def test_xlsx_annual_departments_parsed_without_xlrd(vintage):
    cfg = load_departmental_config(vintage / "icml-colombia/configs/rc1/departmental.toml")
    result = DepartmentAnnexReader(cfg.annex).read(vintage / cfg.sources.annex)
    assert len(result) == 23 * 19
    assert result["dep_code"].nunique() == 23
    assert set(result["year"].unique()) == set(range(2007, 2026))

def test_staging_is_non_destructive(vintage, tmp_path):
    old = (vintage / "datos/2_procesamiento/catalogos/catalogo_fuentes.json").read_bytes()
    source = vintage / "datos/2_procesamiento/fuentes_preparadas/nacional/source_enh_annual.csv"
    dest = tmp_path / "prospective_source"
    manifest = stage_new_source(vintage,"national.enh_annual",source,dest,"2026-08")
    assert manifest["status"] == "STAGED_REQUIRES_SCHEMA_AND_VINTAGE_APPROVAL"
    assert (vintage / "datos/2_procesamiento/catalogos/catalogo_fuentes.json").read_bytes() == old
    assert (dest / "staging.json").exists()
    with pytest.raises(FileExistsError):
        stage_new_source(vintage,"national.enh_annual",source,dest,"2026-08")

def test_staging_does_not_accept_legacy_mismatch(vintage,tmp_path):
    source = vintage / "datos/1_ingesta/geih_departamentos/geih_departamentos_2025.xlsx"
    with pytest.raises(ValueError):
        stage_new_source(vintage,"national.enh_annual",source,tmp_path / "bad","2026-08")

def test_removed_fases_are_not_needed(vintage):
    assert not (vintage / "fases").exists()
    for phase in ("national","urban","departmental","integration"):
        text=(vintage / "icml-colombia/configs/rc1" / (phase+".toml")).read_text()
        assert "fases/" not in text
