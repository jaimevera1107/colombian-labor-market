"""The migrated integration stage reproduces RC1.

Runs national, urban and departmental stages first; integration consumes
their artifacts, so this checks the four-stage chain end to end. The three
flexible cities of the quality filter use a documented relaxed tolerance
(one part per million) because their optimum is ill-conditioned.
"""

from pathlib import Path

import pytest

from icml.departmental.pipeline import (
    DepartmentalPipeline,
    load_departmental_config,
)
from icml.integration.pipeline import (
    OUTPUTS,
    IntegrationPipeline,
    load_integration_config,
)
from icml.io.artifacts import ArtifactStore
from icml.national.pipeline import NationalPipeline, load_national_config
from icml.regression.golden import load_golden_table
from icml.urban.pipeline import UrbanPipeline, load_urban_config

from .equivalence import assert_reports, compare_equivalence
from .integration_rc1_map import EQUIVALENCES, VALUE_MAPS

pytestmark = pytest.mark.golden

CONFIGS = Path(__file__).resolve().parents[2] / "configs" / "rc1"


@pytest.fixture(scope="module")
def integration_run(sources_root, tmp_path_factory):
    root = tmp_path_factory.mktemp("integration_chain")
    stores = {
        name: ArtifactStore(root / name)
        for name in ("national", "urban", "departmental", "integration")
    }
    NationalPipeline(load_national_config(CONFIGS / "national.toml")).run(
        sources_root, stores["national"]
    )
    UrbanPipeline(load_urban_config(CONFIGS / "urban.toml")).run(
        sources_root, ArtifactStore(root / "national"), stores["urban"]
    )
    DepartmentalPipeline(
        load_departmental_config(CONFIGS / "departmental.toml")
    ).run(
        sources_root, ArtifactStore(root / "national"), stores["departmental"]
    )
    result = IntegrationPipeline(
        load_integration_config(CONFIGS / "integration.toml")
    ).run(
        sources_root,
        ArtifactStore(root / "national"),
        ArtifactStore(root / "urban"),
        ArtifactStore(root / "departmental"),
        stores["integration"],
    )
    return stores["integration"], result, root


@pytest.mark.parametrize("golden_id", sorted(EQUIVALENCES))
def test_integration_artifact_matches_rc1(
    catalog, golden_dir, integration_run, golden_id
):
    store, _, _ = integration_run
    reference = load_golden_table(golden_dir, catalog.get(golden_id))
    candidate = store.read(OUTPUTS[EQUIVALENCES[golden_id].output])
    assert_reports(
        compare_equivalence(
            golden_id,
            reference,
            candidate,
            EQUIVALENCES[golden_id],
            VALUE_MAPS.get(golden_id),
        )
    )


def test_filter_rules_match_rc1(integration_run):
    _, result, _ = integration_run
    assert result.diagnostics["filter_rules"] == {
        "unchanged": 22,
        "strict_exact_windows": 7,
        "flexible_bounded_tolerance": 3,
        "synthetic_unchanged": 1,
    }
    # RC1 documents a maximum window deviation of 2.1 % (Leticia).
    assert result.diagnostics[
        "max_filtered_window_error_pct"
    ] == pytest.approx(2.1, abs=1e-6)


def test_cli_chains_all_stages(sources_root, tmp_path):
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
    for stage, run_id in (("urban", "u1"), ("departmental", "d1")):
        assert (
            main(
                [
                    stage,
                    "run",
                    "--config",
                    str(CONFIGS / f"{stage}.toml"),
                    "--national-run",
                    str(tmp_path / "n1"),
                    *common,
                    "--run-id",
                    run_id,
                ]
            )
            == 0
        )
    assert (
        main(
            [
                "integration",
                "run",
                "--config",
                str(CONFIGS / "integration.toml"),
                *common,
                "--national-run",
                str(tmp_path / "n1"),
                "--urban-run",
                str(tmp_path / "u1"),
                "--departmental-run",
                str(tmp_path / "d1"),
                "--run-id",
                "i1",
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "modeling",
                "run",
                "--config",
                str(CONFIGS / "modeling.toml"),
                "--integration-run",
                str(tmp_path / "i1"),
                "--departmental-run",
                str(tmp_path / "d1"),
                "--runs-dir",
                str(tmp_path),
                "--run-id",
                "m1",
            ]
        )
        == 0
    )
    modeling_manifest = json.loads(
        (tmp_path / "m1" / "manifest.json").read_text("utf-8")
    )
    assert "modeling.model_td" in {
        r["artifact_id"] for r in modeling_manifest["outputs"]
    }
    manifest = json.loads(
        (tmp_path / "i1" / "manifest.json").read_text("utf-8")
    )
    consumed = {r["artifact_id"] for r in manifest["inputs"]}
    assert {
        "urban.signals_33",
        "departmental.monthly_revised",
        "national.seasonal_monthly",
    } <= consumed
