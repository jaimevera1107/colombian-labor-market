import numpy as np
import pandas as pd
import pytest

from icml.reconciliation.linearization import (
    LinearizationPolicy,
    WorkingAgeLinearizer,
)
from icml.reconciliation.solvers import (
    SolverError,
    joint_smoother,
    proportional_fit,
    smooth_with_annual_means,
)


def _years(n_years=4, start=2007):
    return np.repeat(np.arange(start, start + n_years), 12)


def test_smoother_keeps_annual_means_and_reduces_curvature():
    rng = np.random.default_rng(1)
    years = _years()
    values = 1000 + 50 * rng.standard_normal(len(years))
    anchors = {int(y): float(values[years == y].mean()) for y in set(years)}
    smooth = smooth_with_annual_means(values, years, anchors, strength=500.0)
    for year, mean in anchors.items():
        assert smooth[years == year].mean() == pytest.approx(mean, abs=1e-6)
    assert np.abs(np.diff(smooth, 2)).sum() < np.abs(np.diff(values, 2)).sum()


def test_smoother_rejects_incomplete_years():
    years = _years()[:-1]
    with pytest.raises(SolverError):
        smooth_with_annual_means(np.ones(len(years)), years, {2010: 1.0}, 10.0)


def test_joint_smoother_matches_national_totals_and_anchors():
    years = _years(2)
    rng = np.random.default_rng(2)
    baseline = np.column_stack(
        [
            100 + rng.standard_normal(24),
            200 + rng.standard_normal(24),
            50 + rng.standard_normal(24),
        ]
    )
    national = baseline.sum(axis=1) + 3.0
    anchors = pd.DataFrame({"dep_code": [1], "year": [2007]})
    target = float(baseline[:12, 0].mean())
    result = joint_smoother(
        baseline, [1, 2, 3], years, national, anchors, 50.0, [target], 1e-6
    )
    np.testing.assert_allclose(result.sum(axis=1), national, atol=1e-6)
    assert result[:12, 0].mean() == pytest.approx(target, abs=1e-6)


def test_proportional_fit_reaches_both_margins():
    seed = np.array([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]])
    rows, columns = np.array([10.0, 20.0]), np.array([8.0, 9.0, 13.0])
    table = proportional_fit(
        seed,
        rows,
        columns,
        max_iterations=500,
        tolerance=1e-12,
        check_every=1,
        floor=1e-8,
    )
    np.testing.assert_allclose(table.sum(axis=1), rows, atol=1e-8)
    np.testing.assert_allclose(table.sum(axis=0), columns, atol=1e-6)


def test_proportional_fit_rejects_incompatible_margins():
    with pytest.raises(SolverError):
        proportional_fit(
            np.ones((2, 2)),
            np.array([1.0, 1.0]),
            np.array([1.0, 3.0]),
            max_iterations=10,
            tolerance=1e-9,
            check_every=1,
            floor=1e-8,
        )


def _national():
    periods = pd.period_range("1999-01", "2002-12", freq="M").astype(str)
    rng = np.random.default_rng(3)
    employed = 1000 + 5 * rng.standard_normal(len(periods))
    unemployed = 100 + rng.standard_normal(len(periods))
    inactive = 600 + 8 * rng.standard_normal(len(periods))
    frame = pd.DataFrame(
        {
            "period": periods,
            "origin": "x",
            "employed": employed,
            "unemployed": unemployed,
            "inactive": inactive,
            "population": 3000.0,
        }
    )
    frame["labor_force"] = frame["employed"] + frame["unemployed"]
    frame["working_age"] = frame["labor_force"] + frame["inactive"]
    return frame


def test_national_linearization_keeps_means_and_later_months():
    policy = LinearizationPolicy("1999-01", "2000-12", 200.0, 200.0, 2)
    national = _national()
    result, stats = WorkingAgeLinearizer(policy).national(national)
    history = national["period"] <= "2000-12"
    pd.testing.assert_frame_equal(result[~history], national[~history])
    for year in ("1999", "2000"):
        rows = national["period"].str.startswith(year)
        assert result.loc[rows, "working_age"].mean() == pytest.approx(
            national.loc[rows, "working_age"].mean(), abs=1e-6
        )
    assert stats["curvature_energy_reduction_pct"] > 0


def test_linearization_policy_rejects_non_positive_strength():
    with pytest.raises(ValueError):
        LinearizationPolicy("1993-01", "2000-12", 0.0, 1.0, 2)
