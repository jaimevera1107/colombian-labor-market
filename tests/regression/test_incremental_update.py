"""An ordinary monthly update must not rewrite published history.

Two consecutive vintages are produced from the same annex: one cut at
2026-05 (54 windows) and the current one (57 windows). Recomputing the
whole chain rewrites final cells, which is exactly why the graft exists;
after it, only revisable cells change and every row stays internally
consistent.
"""

import shutil

import pandas as pd
import pytest

from icml.integration.pipeline import (
    IntegrationPipeline,
    load_integration_config,
)
from icml.io.artifacts import ArtifactStore
from icml.modeling.pipeline import ModelingPipeline, load_modeling_config
from icml.pipeline.vintage import (
    STATE_FINAL,
    VintagePolicy,
    apply_update,
    assert_accepted,
    compare_vintages,
    with_revision_state,
)
from icml.reconciliation.pipeline import (
    OUTPUTS as RECONCILIATION_OUTPUTS,
)
from icml.reconciliation.pipeline import (
    ReconciliationPipeline,
    load_reconciliation_config,
)

from .conftest import CONFIGS

pytestmark = pytest.mark.golden

KEYS = ["dep_code", "period"]
QUANTITIES = ["employed", "unemployed", "inactive", "population"]
PRODUCT = RECONCILIATION_OUTPUTS["departmental_factors"]
ANCHORED_YEAR = 2025


def _vintage(sources_root, stores, root, last_month, n_windows):
    text = (CONFIGS / "integration.toml").read_text(encoding="utf-8")
    text = text.replace("n_windows = 57", f"n_windows = {n_windows}")
    text = text.replace(
        'last_month = "2026-08"', f'last_month = "{last_month}"'
    )
    config = root / "integration.toml"
    root.mkdir(parents=True, exist_ok=True)
    config.write_text(text, encoding="utf-8")
    IntegrationPipeline(load_integration_config(config)).run(
        sources_root,
        stores["national"],
        stores["urban"],
        stores["departmental"],
        ArtifactStore(root / "integration"),
    )
    national = root / "integration" / "integration" / "national_monthly.csv"
    table = pd.read_csv(national)
    table[table["period"] <= last_month].to_csv(national, index=False)
    ModelingPipeline(load_modeling_config(CONFIGS / "modeling.toml")).run(
        ArtifactStore(root / "integration"),
        stores["departmental"],
        ArtifactStore(root / "modeling"),
    )
    ReconciliationPipeline(
        load_reconciliation_config(CONFIGS / "reconciliation.toml")
    ).run(
        ArtifactStore(root / "modeling"),
        ArtifactStore(root / "integration"),
        stores["departmental"],
        ArtifactStore(root / "reconciliation"),
    )
    return ArtifactStore(root / "reconciliation").read(PRODUCT)


@pytest.fixture(scope="module")
def vintages(sources_root, full_chain, tmp_path_factory):
    root = tmp_path_factory.mktemp("vintages")
    stores = full_chain["stores"]
    shutil.rmtree(root / "old", ignore_errors=True)
    previous = _vintage(sources_root, stores, root / "old", "2026-05", 54)
    current = _vintage(sources_root, stores, root / "new", "2026-08", 57)
    policy = VintagePolicy("2026-05", ANCHORED_YEAR, 12)
    return with_revision_state(previous, policy), current, policy


def test_recomputing_everything_would_rewrite_history(vintages):
    previous, current, policy = vintages
    report = compare_vintages(previous, current, KEYS, QUANTITIES, policy)
    assert not report.accepted
    assert report.summary["protected_cells_changed"] > 1000


def test_update_changes_only_revisable_cells(vintages):
    previous, current, policy = vintages
    merged = apply_update(
        previous, current, KEYS, VintagePolicy("2026-08", ANCHORED_YEAR, 12)
    )
    report = compare_vintages(previous, merged, KEYS, QUANTITIES, policy)
    assert_accepted(report)
    assert report.summary["cells_changed"] > 0
    assert set(report.changes["revision_state"]) == {"provisional"}
    assert report.summary["new_rows"] == 3 * merged["dep_code"].nunique()


def test_updated_rows_stay_internally_consistent(vintages):
    previous, current, policy = vintages
    merged = apply_update(
        previous, current, KEYS, VintagePolicy("2026-08", ANCHORED_YEAR, 12)
    )
    residual = (
        merged["employed"]
        + merged["unemployed"]
        + merged["inactive"]
        - merged["working_age"]
    ).abs()
    assert float(residual.max()) < 1e-6
    frozen = merged[merged["period"] <= "2025-09"]
    assert (frozen["revision_state"] == STATE_FINAL).all()
