import numpy as np
import pytest

from icml.domain.provenance import ProvenanceCategory
from icml.national.combination import (
    CombinationError,
    combine_history_with_observed,
)
from icml.national.reconciliation import (
    NationalReconciler,
    ReconciliationError,
    ReconciliationPolicy,
)

POLICY = ReconciliationPolicy(
    historical_end=1998,
    anchor_relative_sigma=0.05,
    minimum_anchor_sigma_persons=10000.0,
    max_observed_rounding_persons=1.0,
    max_annual_relative_shift=0.10,
    max_monthly_relative_shift=0.15,
    max_added_bridge_log_shift=0.05,
)
QUANTITIES = [
    "employed",
    "unemployed",
    "inactive",
    "population",
    "labor_force",
    "working_age",
]


def _annual_from(monthly):
    years = monthly["period"].str.slice(0, 4).astype(int)
    annual = monthly.groupby(years)[QUANTITIES].mean()
    return annual.rename_axis("year").reset_index()


def test_consistent_inputs_are_left_unchanged(monthly_levels):
    annual = _annual_from(monthly_levels)
    result = NationalReconciler(POLICY).run(annual, monthly_levels)
    np.testing.assert_allclose(
        result.annual[QUANTITIES], annual[QUANTITIES], rtol=1e-12
    )
    np.testing.assert_allclose(
        result.monthly[QUANTITIES], monthly_levels[QUANTITIES], rtol=1e-12
    )
    assert all(result.gates.values())


def test_inconsistent_historical_anchors_are_closed(monthly_levels):
    annual = _annual_from(monthly_levels)
    annual.loc[annual["year"] <= POLICY.historical_end, "labor_force"] *= 1.01
    distorted = monthly_levels.copy()
    distorted["labor_force"] *= 1.01
    result = NationalReconciler(POLICY).run(annual, distorted)
    monthly = result.monthly
    assert (
        monthly["labor_force"] - monthly["employed"] - monthly["unemployed"]
    ).abs().max() < 1e-6
    years = monthly["period"].str.slice(0, 4).astype(int)
    means = monthly.groupby(years)[QUANTITIES].mean().to_numpy()
    np.testing.assert_allclose(
        means, result.annual[QUANTITIES].to_numpy(), atol=1e-6, rtol=0
    )


def test_observed_years_beyond_rounding_are_rejected(monthly_levels):
    annual = _annual_from(monthly_levels)
    annual.loc[annual["year"] == 2000, "labor_force"] += 5000
    with pytest.raises(ReconciliationError, match="rounding"):
        NationalReconciler(POLICY).reconcile_annual(annual)


def test_incomplete_year_is_rejected(monthly_levels):
    annual = _annual_from(monthly_levels)
    with pytest.raises(ReconciliationError, match="Incomplete"):
        NationalReconciler(POLICY).reconcile_monthly(
            monthly_levels.iloc[1:], annual
        )


def test_combination_uses_observed_values_unchanged(monthly_levels):
    history = monthly_levels
    observed = monthly_levels[monthly_levels["period"] >= "1999-01"].copy()
    observed[QUANTITIES] = observed[QUANTITIES] * 1.5
    combined = combine_history_with_observed(
        history,
        observed,
        history_provenance=ProvenanceCategory.ANCHORED_RECONSTRUCTION,
    )
    assert len(combined) == len(history)
    after = combined[combined["period"] >= "1999-01"]
    assert set(after["provenance"]) == {"observed"}
    np.testing.assert_array_equal(
        after[QUANTITIES].to_numpy(), observed[QUANTITIES].to_numpy()
    )


def test_combination_requires_history_before_observations(monthly_levels):
    with pytest.raises(CombinationError, match="before"):
        combine_history_with_observed(
            monthly_levels,
            monthly_levels,
            history_provenance=ProvenanceCategory.ANCHORED_RECONSTRUCTION,
        )
    gapped = monthly_levels.drop(index=3)
    with pytest.raises(CombinationError, match="gaps"):
        combine_history_with_observed(
            gapped,
            monthly_levels.iloc[-12:],
            history_provenance=ProvenanceCategory.ANCHORED_RECONSTRUCTION,
        )
