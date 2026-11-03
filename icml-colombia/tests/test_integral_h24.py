"""Unified H24: historical-vintage verification vs genuine recomputation."""
import json
from pathlib import Path

import pytest

from icml.operations.integral import (
    REQUIRED_INF_FILES,
    audit_products,
    expected_source_files,
    preflight,
    run_integral,
)


@pytest.fixture(scope="module")
def frozen_root():
    # Full-vintage integration tests are skipped in a source-only installation.
    root = Path(__file__).resolve().parents[2]
    if not (root / "datos/2_procesamiento/productos_congelados/catalogo_h19/19_catalogo_unificado.csv").exists():
        pytest.skip("Full ICML research-vintage root not present")
    return root


def test_2026_08_full_vintage_cross_checks(frozen_root):
    import csv
    from icml.operations.h20 import verify_products
    a = verify_products(frozen_root)
    assert not a["issues"]
    p = {x["product"]: frozen_root / x["path"] for x in a["products"]}
    c = audit_products(p)
    assert c["status"] == "PASS", c["issues"]
    assert c["rows"]["sectorial.departamental"] == 199980
    # Represented informality is NOT numerically the same vintage as labor.
    assert c["metrics"]["represented_domain_nonidentical_rows_DIAGNOSTIC"] > 0


def test_verify_is_separate_from_recalculation(frozen_root, tmp_path):
    path = tmp_path / "immutable"
    r = run_integral(frozen_root, path, mode="verify")
    assert r["status"] == "VERIFIED_EXISTING_VINTAGE_NOT_REEXECUTED"
    assert r["recalculated_from_sources"] is False
    assert (path / "integral_execution_report.json").exists()
    with pytest.raises(FileExistsError):
        run_integral(frozen_root, path, mode="verify")


def test_recompute_missing_inputs_blocks_before_compute(frozen_root, tmp_path):
    # A production checkpoint may contain ALL source files. Test the missing-
    # input gate using a deliberately empty independent source tree instead.
    missing_sources = tmp_path / "missing_sources"
    missing_sources.mkdir()
    pre = preflight(frozen_root, "recompute", sources=missing_sources)
    assert pre["status"] == "BLOCKED_MISSING_INPUTS"
    assert any("datos/2_procesamiento/fuentes_preparadas/nacional/" in x for x in pre["missing"])
    assert not any("informalidad_secuencia_h5_h6" in x for x in pre["missing"])
    report = run_integral(
        frozen_root, tmp_path / "blocked", mode="recompute", sources=missing_sources
    )
    assert report["status"] == "BLOCKED"
    assert report["recalculated_from_sources"] is False
    assert not (tmp_path / "blocked" / "runs").exists()


def test_recovered_labor_sources_pass_preflight(frozen_root):
    # No estimator is executed by this test: it only checks all declared paths.
    result = preflight(frozen_root, "recompute")
    assert result["status"] == "READY", result["missing"]
    assert len(result["labor_sources"]["missing"]) == 0


def test_sources_inventory_fails_closed(tmp_path):
    configs, sources = tmp_path / "configs", tmp_path / "sources"
    configs.mkdir()
    sources.mkdir()
    (configs / "national.toml").write_text('[national.sources]\nfile="missing.csv"\n', encoding="utf-8")
    s = expected_source_files(configs, sources)
    assert str(sources / "missing.csv") in s["missing"]
    assert str(configs / "urban.toml") in s["missing"]


def test_mode_validation(frozen_root):
    with pytest.raises(ValueError):
        preflight(frozen_root, "september")


def test_destination_cannot_be_inside_checkpoint(frozen_root):
    with pytest.raises(ValueError):
        run_integral(frozen_root, frozen_root / "bad_output", mode="verify")


def test_resume_previously_completed_stages(frozen_root, tmp_path):
    from icml.operations.integral import run_integral
    completed_h9 = frozen_root / "datos/2_procesamiento/parametros_congelados/informalidad_cierre_h9"
    completed_h16 = frozen_root / "datos/2_procesamiento/sectorial_h16"
    result = run_integral(
        frozen_root, tmp_path / "resumed", mode="recompute-components",
        resume_informality=completed_h9, resume_sectoral=completed_h16,
    )
    assert result["status"] == "RECOMPUTED_H9_H16_FROM_VERIFIED_STAGE_RUNS"
    assert result["recalculated_from_sources"] is False
    assert result["stage_runs_reused_after_cryptographic_validation"]
    assert result["candidate_cross_audit"]["status"] == "PASS"
    assert len(result["comparison_eight_products"]) == 8
    assert all(v["sha256_equal"] for v in result["comparison_eight_products"].values())


def test_resume_rejects_bad_stage_inputs(frozen_root, tmp_path):
    import shutil
    from icml.operations.integral import run_integral
    good = frozen_root / "datos/2_procesamiento/parametros_congelados/informalidad_cierre_h9"
    bad = tmp_path / "altered"
    shutil.copytree(good, bad)
    with (bad / "13_resumen.json").open("a", encoding="utf-8") as stream:
        stream.write("\n")
    result = run_integral(
        frozen_root, tmp_path / "invalid", mode="recompute-components",
        resume_informality=bad,
        resume_sectoral=frozen_root / "datos/2_procesamiento/sectorial_h16",
    )
    assert result["status"] == "RESUME_FAILED_NOT_PUBLISHED"
    assert "manifest" in result["failure"]["message"].lower() or "mutated" in result["failure"]["message"].lower()
