"""The migrated modeling stage reproduces RC1.

Runs the full five-stage chain. Two facts shape the checks:

* XGBoost predictions are float32. RC1 wrote them with the shortest
  float32 decimal; re-serializing the package predictions the same way
  reproduces RC1 bit for bit, which is checked exactly.
* RC1 built the final panels from those decimal predictions. The panels are
  therefore checked by feeding the RC1 predictions to the package panel
  builder (standard tolerance), and the pipeline's own panels, built from
  the exact float32 predictions, are checked to differ by at most a few
  float32 units in the last place.
"""

from pathlib import Path

import numpy as np
import pytest

from icml.domain.territories import territory_codes
from icml.modeling.pipeline import (
    OUTPUTS,
    ModelingPipeline,
    load_modeling_config,
)
from icml.modeling.selection import FinalPanelBuilder
from icml.regression.golden import load_golden_table

from .equivalence import FLOAT32_EPSILON, assert_reports, compare_equivalence
from .modeling_rc1_map import EQUIVALENCES, PREDICTIONS, VALUE_MAPS

pytestmark = pytest.mark.golden

CONFIGS = Path(__file__).resolve().parents[2] / "configs" / "rc1"
PANEL_IDS = (
    "modeling.ward_panel",
    "modeling.hybrid_panel",
    "modeling.panel_sensitivity",
)
RATES = ("to", "td", "tgp", "pet_demog")
MAX_ULPS = 4


@pytest.fixture(scope="module")
def modeling_run(full_chain):
    return full_chain["stores"]["modeling"], full_chain["modeling"]


@pytest.mark.parametrize(
    "golden_id", sorted(set(EQUIVALENCES) - set(PANEL_IDS))
)
def test_modeling_artifact_matches_rc1(
    catalog, golden_dir, modeling_run, golden_id
):
    store, _ = modeling_run
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


def _shortest_float32(values: np.ndarray) -> np.ndarray:
    return np.array(
        [
            float(
                np.format_float_positional(
                    np.float32(v), unique=True, trim="-"
                )
            )
            for v in values
        ]
    )


def test_predictions_serialize_to_rc1_exactly(
    catalog, golden_dir, modeling_run
):
    store, _ = modeling_run
    package = store.read(OUTPUTS["full_predictions"])
    golden = load_golden_table(
        golden_dir, catalog.get("modeling.ward_predictions")
    )
    golden["variant"] = golden["variant"].map(
        {"filtrada": "filtered", "estricta": "strict"}
    )
    merged = package.merge(
        golden.rename(columns={"periodo": "period"}),
        on=["variant", "dep_code", "period"],
        suffixes=("", "_rc1"),
        validate="one_to_one",
    )
    for rate in RATES:
        np.testing.assert_array_equal(
            _shortest_float32(np.array(merged[rate])),
            np.array(merged[f"{rate}_rc1"]),
        )


@pytest.fixture(scope="module")
def panels_from_rc1_predictions(catalog, golden_dir, modeling_run):
    store, _ = modeling_run
    golden = load_golden_table(
        golden_dir, catalog.get("modeling.ward_predictions")
    )
    predictions = golden.rename(columns={v: k for k, v in PREDICTIONS.items()})
    predictions["variant"] = predictions["variant"].map(
        {"filtrada": "filtered", "estricta": "strict"}
    )
    config = load_modeling_config(CONFIGS / "modeling.toml")
    builder = FinalPanelBuilder(
        config.selection, territory_codes(), config.features.synthetic_code
    )
    features = store.read(OUTPUTS["features_filtered"])
    targets = store.read(OUTPUTS["targets"])
    reference = builder.build(
        predictions, features, targets, config.selection.reference_model
    )
    selected = builder.build(
        predictions, features, targets, config.selection.candidate
    )
    sensitivity = ModelingPipeline._sensitivity(selected, reference)
    return {
        "modeling.ward_panel": reference,
        "modeling.hybrid_panel": selected,
        "modeling.panel_sensitivity": sensitivity,
    }


@pytest.mark.parametrize("golden_id", PANEL_IDS)
def test_panels_match_rc1_from_rc1_predictions(
    catalog, golden_dir, panels_from_rc1_predictions, golden_id
):
    reference = load_golden_table(golden_dir, catalog.get(golden_id))
    assert_reports(
        compare_equivalence(
            golden_id,
            reference,
            panels_from_rc1_predictions[golden_id],
            EQUIVALENCES[golden_id],
            VALUE_MAPS.get(golden_id),
        )
    )


@pytest.mark.parametrize(
    ("output", "golden_id"),
    [
        ("panel_reference", "modeling.ward_panel"),
        ("panel_selected", "modeling.hybrid_panel"),
    ],
)
def test_pipeline_panels_within_float32_ulps(
    modeling_run, panels_from_rc1_predictions, output, golden_id
):
    store, _ = modeling_run
    pipeline = store.read(OUTPUTS[output])
    decoupled = panels_from_rc1_predictions[golden_id]
    keys = ["dep_code", "period"]
    merged = pipeline.merge(decoupled, on=keys, suffixes=("", "_rc1"))
    for column in [f"final_{r}" for r in RATES] + [
        "employed",
        "unemployed",
        "labor_force",
        "working_age",
    ]:
        relative = np.abs(merged[column] - merged[f"{column}_rc1"]) / np.abs(
            merged[f"{column}_rc1"]
        ).clip(lower=1e-12)
        assert float(relative.max()) <= MAX_ULPS * FLOAT32_EPSILON, column


def test_selection_matches_rc1_decision(modeling_run):
    _, result = modeling_run
    summary = result.diagnostics["selection"]
    assert result.diagnostics["cv_selected"] == "xgb_ward"
    assert summary["selected_model"] == "hibrido_urbano_to_tgp_xgb_td_pet"
    assert summary["n_configurations"] == 108
    assert summary["hybrid_minus_reference_mean_pp"] == pytest.approx(
        -0.4085381761412679, abs=1e-9
    )
    assert summary["bootstrap_cluster_ci95_pp"] == pytest.approx(
        [-0.7913637532370138, -0.03475427821806793], abs=1e-9
    )
