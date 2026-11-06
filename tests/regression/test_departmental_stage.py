"""The migrated departmental stage reproduces RC1 within 1e-6 persons.

Runs the national stage first and feeds its artifacts to the departmental
stage, so the chain national -> departmental is checked end to end.
"""

from pathlib import Path

import pytest

from icml.departmental.pipeline import (
    OUTPUTS,
    DepartmentalPipeline,
    load_departmental_config,
)
from icml.domain.contracts import (
    IdentityPolicy,
    check_identities_by_provenance,
)
from icml.domain.quantities import to_canonical_columns
from icml.io.artifacts import ArtifactStore
from icml.national.pipeline import NationalPipeline, load_national_config
from icml.regression.golden import load_golden_table

from .departmental_rc1_map import EQUIVALENCES, VALUE_MAPS
from .equivalence import assert_reports, compare_equivalence

pytestmark = pytest.mark.golden

CONFIGS = Path(__file__).resolve().parents[2] / "configs" / "rc1"


@pytest.fixture(scope="module")
def departmental_run(sources_root, tmp_path_factory):
    root = tmp_path_factory.mktemp("departmental_chain")
    NationalPipeline(load_national_config(CONFIGS / "national.toml")).run(
        sources_root, ArtifactStore(root / "national")
    )
    output = ArtifactStore(root / "departmental")
    result = DepartmentalPipeline(
        load_departmental_config(CONFIGS / "departmental.toml")
    ).run(sources_root, ArtifactStore(root / "national"), output)
    return output, result


@pytest.mark.parametrize("golden_id", sorted(EQUIVALENCES))
def test_departmental_artifact_matches_rc1(
    catalog, golden_dir, departmental_run, golden_id
):
    store, _ = departmental_run
    reference = load_golden_table(golden_dir, catalog.get(golden_id))
    candidate = store.read(OUTPUTS[EQUIVALENCES[golden_id].output])
    reports = compare_equivalence(
        golden_id,
        reference,
        candidate,
        EQUIVALENCES[golden_id],
        VALUE_MAPS.get(golden_id),
    )
    assert_reports(reports)


def test_revised_panel_identities_and_coverage(departmental_run):
    store, _ = departmental_run
    panel = store.read(OUTPUTS["monthly_revised"])
    assert panel["dep_code"].nunique() == 23
    assert panel.groupby("dep_code").size().eq(396).all()
    assert 11 not in set(panel["dep_code"])
    assert set(panel["origin"]) == {
        "INFERIDO_NACIONAL_SIN_ANCLA_DEPARTAMENTAL",
        "CHOW_LIN_063_CON_ANCLA_OFICIAL_ANUAL",
    }


def test_rho_sensitivity_matches_rc1_documentation(departmental_run):
    _, result = departmental_run
    summary = result.diagnostics["rho_sensitivity"]
    assert summary["rho_competing"] == 0.989
    assert (
        summary["log_likelihood_global"] > summary["log_likelihood_competing"]
    )


def test_identity_contract(departmental_run):
    store, _ = departmental_run
    panel = to_canonical_columns(store.read(OUTPUTS["monthly_revised"]))
    reports = check_identities_by_provenance(
        panel.assign(origin="RECONSTRUCCION_CON_ANCLA_ANUAL"),
        provenance_column="origin",
        policy=IdentityPolicy(
            observed_tolerance_persons=2.0, estimated_tolerance_persons=1e-6
        ),
    )
    assert all(report.passed for report in reports.values())


def test_cli_runs_departmental_on_national_run(sources_root, tmp_path):
    import json

    from icml.cli import main

    common = ["--sources", str(sources_root), "--runs-dir", str(tmp_path)]
    assert (
        main(
            [
                "national",
                "run",
                "--config",
                str(CONFIGS / "national.toml"),
                *common,
                "--run-id",
                "n1",
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "departmental",
                "run",
                "--config",
                str(CONFIGS / "departmental.toml"),
                "--national-run",
                str(tmp_path / "n1"),
                *common,
                "--run-id",
                "d1",
            ]
        )
        == 0
    )
    manifest = json.loads(
        (tmp_path / "d1" / "manifest.json").read_text("utf-8")
    )
    assert manifest["stage"] == "departmental"
    assert "source.departmental_annex" in {
        r["artifact_id"] for r in manifest["inputs"]
    }
