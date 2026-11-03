import numpy as np
import pandas as pd
import pytest

from icml.evaluation.transfer import (
    TransferEvaluator,
    TransferPolicy,
    annual_comparison,
    summarize,
)


def _policy(**changes):
    values = dict(
        modeling_config="m.toml",
        reconciliation_config="r.toml",
        excluded_codes=[25],
        hidden_codes=[],
        first_year=2007,
        last_year=2008,
        candidates=["xgb_ward", "urban_analog"],
        closures=["rc1"],
    )
    values.update(changes)
    return TransferPolicy(**values)


def test_policy_rejects_unknown_candidates():
    with pytest.raises(ValueError):
        _policy(candidates=["magic"])


def test_hidden_excludes_synthetic_and_validates_requests():
    evaluator = TransferEvaluator(_policy(), None, None, {}, "h", 25)
    assert evaluator.hidden([5, 25, 68]) == [5, 68]
    strict = TransferEvaluator(
        _policy(hidden_codes=[25]), None, None, None, "h", 25
    )
    with pytest.raises(ValueError):
        strict.hidden([5, 25, 68])


def _panel(scale=1.0):
    periods = [f"{y}-{m:02d}" for y in (2007, 2008) for m in range(1, 13)]
    frame = pd.DataFrame(
        {
            "dep_code": 5,
            "period": periods,
            "year": [int(p[:4]) for p in periods],
        }
    )
    frame["employed"] = 90.0 * scale
    frame["unemployed"] = 10.0
    frame["inactive"] = 50.0
    frame["labor_force"] = frame["employed"] + frame["unemployed"]
    frame["working_age"] = frame["labor_force"] + frame["inactive"]
    frame["labor_population_reconciled"] = 200.0
    return frame


def _anchors():
    return pd.DataFrame(
        {
            "dep_code": [5, 5],
            "year": [2007, 2008],
            "employed": 90.0,
            "unemployed": 10.0,
            "inactive": 50.0,
            "labor_force": 100.0,
            "working_age": 150.0,
            "population": 200.0,
        }
    )


def test_annual_comparison_is_zero_for_exact_reconstruction():
    result = annual_comparison(
        _panel(),
        _anchors(),
        5,
        range(2007, 2009),
        "labor_population_reconciled",
    )
    errors = result.drop(columns="year").to_numpy()
    np.testing.assert_allclose(errors, 0, atol=1e-12)


def test_annual_comparison_measures_rate_errors_in_points():
    result = annual_comparison(
        _panel(scale=1.1),
        _anchors(),
        5,
        range(2007, 2009),
        "labor_population_reconciled",
    )
    expected = 100 * (10 / 109 - 10 / 100)
    assert result["unemployment_rate_pp_error"].iloc[0] == pytest.approx(
        expected
    )
    assert result["employed_pct_error"].iloc[0] == pytest.approx(10.0)


def test_summary_reports_worst_department():
    annual = pd.DataFrame(
        {
            "hidden_code": [5, 5, 8, 8],
            "candidate": "a",
            "stage": "closed",
            "year": [2007, 2008, 2007, 2008],
            **{
                c: [1.0, -1.0, 3.0, 3.0]
                for c in (
                    "unemployment_rate_pp_error",
                    "employment_rate_pp_error",
                    "participation_rate_pp_error",
                    "employed_pct_error",
                    "unemployed_pct_error",
                    "inactive_pct_error",
                    "labor_force_pct_error",
                    "working_age_pct_error",
                    "population_pct_error",
                )
            },
        }
    )
    summary = summarize(annual)
    row = summary.iloc[0]
    assert row["mae_unemployment_rate_pp_error"] == pytest.approx(2.0)
    assert row["worst_department_unemployment_rate_pp_error"] == pytest.approx(
        3.0
    )
