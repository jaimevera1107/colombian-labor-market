"""The migrated urban stage reproduces RC1 within 1e-6 persons.

The urban stage consumes the national artifacts produced by the package
itself, so these tests check the national-to-urban chain end to end.
"""

from pathlib import Path

import pandas as pd
import pytest

from icml.domain.provenance import resolve_legacy_labels
from icml.io.artifacts import ArtifactStore
from icml.national.pipeline import NationalPipeline, load_national_config
from icml.regression.golden import load_golden_table
from icml.urban.pipeline import OUTPUTS, UrbanPipeline, load_urban_config

from .equivalence import assert_reports, compare_equivalence
from .urban_rc1_map import EQUIVALENCES, VALUE_MAPS

pytestmark = pytest.mark.golden

CONFIGS = Path(__file__).resolve().parents[2] / "configs" / "rc1"


@pytest.fixture(scope="module")
def urban_run(sources_root, tmp_path_factory):
    root = tmp_path_factory.mktemp("urban_chain")
    national = ArtifactStore(root / "national_run")
    NationalPipeline(load_national_config(CONFIGS / "national.toml")).run(
        sources_root, national
    )
    output = ArtifactStore(root / "urban_run")
    result = UrbanPipeline(load_urban_config(CONFIGS / "urban.toml")).run(
        sources_root, ArtifactStore(root / "national_run"), output
    )
    return output, result


@pytest.mark.parametrize("golden_id", sorted(EQUIVALENCES))
def test_urban_artifact_matches_rc1(catalog, golden_dir, urban_run, golden_id):
    store, _ = urban_run
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


def test_every_urban_origin_label_is_registered(urban_run):
    store, _ = urban_run
    labels: set[str] = set()
    for name in ("recipient_annual_panel", "signals_33", "synthetic_annual"):
        labels |= set(store.read(OUTPUTS[name])["origin"].astype(str))
    resolve_legacy_labels(labels)


def test_selection_thresholds_match_rc1_documentation(urban_run):
    _, result = urban_run
    # RC1 documents the seam p95 of the 23 pseudo-recipients as 0.08388.
    assert result.diagnostics["thresholds"][
        "seam_error_quantile"
    ] == pytest.approx(0.08388, abs=5e-6)


def test_33_signal_panel_keeps_synthetic_unit_separate(urban_run):
    store, _ = urban_run
    panel = store.read(OUTPUTS["signals_33"])
    synthetic = panel[panel["city_code"] == 25]
    assert set(synthetic["unit_type"]) == {
        "URBANA_SINTETICA_PARA_MODELO_DEPARTAMENTAL"
    }
    assert isinstance(panel, pd.DataFrame)
    assert panel.groupby("city_code").size().eq(336).all()


def test_cli_chains_national_and_urban_runs(sources_root, tmp_path):
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
                "urban",
                "run",
                "--config",
                str(CONFIGS / "urban.toml"),
                "--national-run",
                str(tmp_path / "n1"),
                *common,
                "--run-id",
                "u1",
            ]
        )
        == 0
    )
    manifest = json.loads(
        (tmp_path / "u1" / "manifest.json").read_text("utf-8")
    )
    consumed = {record["artifact_id"] for record in manifest["inputs"]}
    assert {
        "national.combined_with_provenance",
        "national.reconciled_monthly",
    } <= consumed
    with pytest.raises(FileNotFoundError):
        main(
            [
                "urban",
                "run",
                "--config",
                str(CONFIGS / "urban.toml"),
                "--national-run",
                str(tmp_path / "missing"),
                *common,
                "--run-id",
                "u2",
            ]
        )
