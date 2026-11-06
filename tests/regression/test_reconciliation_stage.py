"""The reconciliation stage and the three products reproduce RC1.

The closure and the curvature smoothers solve large KKT systems that
amplify input differences (about 200x for the national linearization).
Checks are therefore layered:

* decoupled: fed with RC1's own inputs (model panels and national series),
  the package reconciler and linearizer reproduce every RC1 table within
  1e-6 persons;
* pipeline: the national product differs from RC1 only by the
  amplification of the 3e-8-person upstream differences (relative 1e-12),
  and the departmental product differs from the decoupled one by a few
  float32 units in the last place inherited from the model predictions.
"""

import numpy as np
import pytest

from icml.departmental.pipeline import OUTPUTS as DEPARTMENTAL_OUTPUTS
from icml.reconciliation.hierarchical import HierarchicalReconciler
from icml.reconciliation.linearization import WorkingAgeLinearizer
from icml.reconciliation.pipeline import (
    OUTPUTS,
    load_reconciliation_config,
)
from icml.regression.compare import Tolerance
from icml.regression.golden import load_golden_table

from .conftest import CONFIGS
from .equivalence import FLOAT32_EPSILON, assert_reports, compare_equivalence
from .integration_rc1_map import EQUIVALENCES as INTEGRATION
from .modeling_rc1_map import PANEL
from .reconciliation_rc1_map import (
    NATIONAL,
    NATIONAL_EQUIVALENCE,
    PANEL_EQUIVALENCES,
    PRODUCT_DEPARTMENTAL_EQUIVALENCE,
)

pytestmark = pytest.mark.golden

AMPLIFIED = Tolerance(absolute=1e-6, relative=1e-12)
MAX_ULPS = 4


@pytest.fixture(scope="module")
def decoupled(catalog, golden_dir, full_chain):
    config = load_reconciliation_config(CONFIGS / "reconciliation.toml")
    names = {
        v: k
        for k, v in INTEGRATION["integration.national_monthly"].columns.items()
    }
    national = load_golden_table(
        golden_dir, catalog.get("integration.national_monthly")
    ).rename(columns=names)
    anchors = full_chain["stores"]["departmental"].read(
        DEPARTMENTAL_OUTPUTS["official_anchors"]
    )
    reconciler = HierarchicalReconciler(config.hierarchical)
    panels = {v: k for k, v in PANEL.items()}
    results = {
        name: reconciler.run(
            load_golden_table(golden_dir, catalog.get(gid)).rename(
                columns=panels
            ),
            national,
            anchors,
        )
        for gid, name in (
            ("modeling.ward_panel", "reference"),
            ("modeling.hybrid_panel", "selected"),
        )
    }
    linearizer = WorkingAgeLinearizer(config.linearization)
    national_product, _ = linearizer.national(national)
    departmental, _ = linearizer.territorial(
        results["reference"].panel, national_product
    )
    return results, national_product, departmental


@pytest.mark.parametrize("golden_id", sorted(PANEL_EQUIVALENCES))
def test_closure_matches_rc1_from_rc1_inputs(
    catalog, golden_dir, decoupled, golden_id
):
    results, _, _ = decoupled
    name, equivalence = PANEL_EQUIVALENCES[golden_id]
    kind = equivalence.output.split("_", 1)[1]
    result = results[name]
    table = {
        "reconciled": result.panel,
        "national_check": result.national_check,
        "anchor_check": result.anchor_check,
        "smoothness": result.smoothness,
    }[kind]
    reference = load_golden_table(golden_dir, catalog.get(golden_id))
    assert_reports(
        compare_equivalence(golden_id, reference, table, equivalence)
    )


def test_products_match_rc1_from_rc1_inputs(catalog, golden_dir, decoupled):
    _, national, departmental = decoupled
    assert_reports(
        compare_equivalence(
            "product.national",
            load_golden_table(golden_dir, catalog.get("product.national")),
            national,
            NATIONAL_EQUIVALENCE,
        )
    )
    assert_reports(
        compare_equivalence(
            "product.departmental",
            load_golden_table(golden_dir, catalog.get("product.departmental")),
            departmental,
            PRODUCT_DEPARTMENTAL_EQUIVALENCE,
        )
    )


def test_pipeline_national_product_matches_rc1(
    catalog, golden_dir, full_chain
):
    store = full_chain["stores"]["reconciliation"]
    equivalence = NATIONAL_EQUIVALENCE.__class__(
        NATIONAL_EQUIVALENCE.output,
        NATIONAL_EQUIVALENCE.keys,
        NATIONAL,
        tolerances={
            column: AMPLIFIED
            for column in NATIONAL.values()
            if column not in ("periodo", "origin")
        },
    )
    assert_reports(
        compare_equivalence(
            "product.national",
            load_golden_table(golden_dir, catalog.get("product.national")),
            store.read(OUTPUTS["national"]),
            equivalence,
        )
    )


def test_pipeline_departmental_product_within_float32_ulps(
    full_chain, decoupled
):
    _, _, departmental = decoupled
    pipeline = full_chain["stores"]["reconciliation"].read(
        OUTPUTS["departmental"]
    )
    merged = pipeline.merge(
        departmental, on=["dep_code", "period"], suffixes=("", "_decoupled")
    )
    assert len(merged) == len(pipeline) == len(departmental)
    for column in (
        "employed",
        "unemployed",
        "inactive",
        "labor_force",
        "working_age",
        "labor_population_reconciled",
    ):
        relative = (
            np.abs(merged[column] - merged[f"{column}_decoupled"])
            / merged[f"{column}_decoupled"]
        )
        assert float(relative.max()) <= MAX_ULPS * FLOAT32_EPSILON, column


def test_products_close_national_totals(full_chain):
    store = full_chain["stores"]["reconciliation"]
    national = store.read(OUTPUTS["national"]).set_index("period")
    departmental = store.read(OUTPUTS["departmental"])
    totals = departmental.groupby("period")[
        ["employed", "unemployed", "inactive"]
    ].sum()
    for column in totals.columns:
        gap = (totals[column] - national.loc[totals.index, column]).abs()
        assert float(gap.max()) < 1e-4, column


def test_operational_model_is_ward(full_chain):
    assert (
        full_chain["reconciliation"].diagnostics["operational_model"]
        == "reference"
    )


RECONCILIATION_SUMMARY_PRODUCTS = {
    "departmental",
    "departmental_factors",
    "national",
    "national_icml",
    "official_deviation",
    "urban_signals",
}
QUALITY_SUMMARY_PRODUCTS = {"ciudades", "departamentos", "nacionales"}


def test_cli_full_run_is_deterministic(full_chain, sources_root, tmp_path):
    """``icml run`` reproduces the per-stage chain bit for bit."""
    import json

    from icml.cli import main
    from icml.io.hashing import sha256_file

    code = main(
        [
            "run",
            "--configs",
            str(CONFIGS),
            "--sources",
            str(sources_root),
            "--runs-dir",
            str(tmp_path),
            "--run-id",
            "full",
        ]
    )
    assert code == 0
    summary = json.loads((tmp_path / "full" / "run.json").read_text("utf-8"))
    assert summary["stages"] == [
        "national",
        "urban",
        "departmental",
        "integration",
        "modeling",
        "reconciliation",
        "quality",
    ]
    store = full_chain["stores"]["reconciliation"]
    # The run summary registers six reconciliation products; the quality
    # stage adds three bases of its own (not reconciliation outputs).
    compared = set(summary["products"]) & set(OUTPUTS)
    assert compared == RECONCILIATION_SUMMARY_PRODUCTS
    assert set(summary["products"]) - compared == QUALITY_SUMMARY_PRODUCTS
    for product in sorted(compared):
        record = summary["products"][product]
        reference = store.root / OUTPUTS[product].relative_path
        assert record["sha256"] == sha256_file(reference), product
