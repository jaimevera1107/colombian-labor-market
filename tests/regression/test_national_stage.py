"""The migrated national stage reproduces RC1 within 1e-6 persons."""

from pathlib import Path

import pandas as pd
import pytest

from icml.io.artifacts import ArtifactStore
from icml.national.pipeline import (
    OUTPUTS,
    NationalPipeline,
    load_national_config,
)
from icml.national.schema import RC1_COLUMN_MAP
from icml.regression.compare import compare_tables
from icml.regression.golden import load_golden_table

pytestmark = pytest.mark.golden

CONFIG = Path(__file__).resolve().parents[2] / "configs/rc1/national.toml"
# Golden id -> (package output, RC1 key column).
EQUIVALENCES = {
    "national.disaggregated_annual": "disaggregated_annual",
    "national.disaggregated_monthly": "disaggregated_monthly",
    "national.combined_with_provenance": "combined_with_provenance",
    "national.reconciled_annual": "reconciled_annual",
    "national.reconciled_monthly": "reconciled_monthly",
    "national.seasonal_monthly": "seasonal_monthly",
}
RC1_PROVENANCE_LABELS = {
    "observed": "geih_observado",
    "anchored_reconstruction": "reconstruido",
}


@pytest.fixture(scope="module")
def national_run(sources_root, tmp_path_factory):
    output = ArtifactStore(tmp_path_factory.mktemp("national_run"))
    result = NationalPipeline(load_national_config(CONFIG)).run(
        sources_root, output
    )
    return output, result


def _to_rc1_schema(frame: pd.DataFrame) -> pd.DataFrame:
    converted = frame.rename(
        columns={**RC1_COLUMN_MAP, "year": "periodo", "provenance": "origen"}
    )
    if "origen" in converted:
        converted["origen"] = converted["origen"].map(RC1_PROVENANCE_LABELS)
    return converted


@pytest.mark.parametrize("golden_id", sorted(EQUIVALENCES))
def test_national_artifact_matches_rc1(
    catalog, golden_dir, national_run, golden_id
):
    store, _ = national_run
    candidate = store.read(OUTPUTS[EQUIVALENCES[golden_id]])
    reference = load_golden_table(golden_dir, catalog.get(golden_id))
    report = compare_tables(
        reference,
        _to_rc1_schema(candidate),
        artifact_id=golden_id,
        keys=("periodo",),
    )
    assert report.passed, report.to_dict()


def test_national_gates_match_rc1_status(national_run):
    _, result = national_run
    disaggregation = result.diagnostics["disaggregation"]["gates"]
    assert disaggregation["annual_identities_close"] is False
    assert all(result.diagnostics["reconciliation"]["gates"].values())
    assert all(result.diagnostics["seasonality"]["quality"].values())


def test_outputs_are_immutable(sources_root, national_run):
    store, _ = national_run
    with pytest.raises(FileExistsError):
        NationalPipeline(load_national_config(CONFIG)).run(sources_root, store)


def test_cli_writes_manifest(sources_root, tmp_path):
    import json

    from icml.cli import main

    code = main(
        [
            "national",
            "run",
            "--config",
            str(CONFIG),
            "--sources",
            str(sources_root),
            "--runs-dir",
            str(tmp_path),
            "--run-id",
            "cli_check",
        ]
    )
    assert code == 0
    manifest = json.loads(
        (tmp_path / "cli_check" / "manifest.json").read_text("utf-8")
    )
    assert manifest["stage"] == "national"
    assert len(manifest["outputs"]) == len(OUTPUTS)
    assert {r["artifact_id"] for r in manifest["inputs"]} >= {
        "source.geih_monthly_annex",
        "source.enh_annual",
    }
