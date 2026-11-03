import numpy as np
import pandas as pd
import pytest

from icml.departmental.anchors import (
    AnchorError,
    AnchorPolicy,
    close_annual_anchors,
    compare_population,
)
from icml.departmental.population import (
    DemographicPopulationBackcast,
    PopulationPolicy,
    PopulationRevisionError,
)

ANCHOR_POLICY = AnchorPolicy(
    max_closure_change_persons=2.01, projection_area_type="Total"
)


def _official(labor_force_shift=0.0):
    return pd.DataFrame(
        {
            "dep_code": [5, 5],
            "department": ["A", "A"],
            "year": [2007, 2008],
            "employed": [90.0, 91.0],
            "unemployed": [10.0, 9.0],
            "inactive": [50.0, 51.0],
            "population": [200.0, 202.0],
            "labor_force": [100.0 + labor_force_shift, 100.0],
            "working_age": [150.0, 151.0],
        }
    )


def test_closure_within_rounding_is_traced():
    closed, trace = close_annual_anchors(_official(1.0), ANCHOR_POLICY)
    assert closed.loc[0, "labor_force"] == 100.0
    assert trace["change_persons"].abs().max() == pytest.approx(1.0)


def test_closure_beyond_rounding_fails():
    with pytest.raises(AnchorError, match="rounding"):
        close_annual_anchors(_official(5.0), ANCHOR_POLICY)


def test_population_comparison_requires_projection():
    projections = pd.DataFrame(
        {
            "dep_code": [5],
            "year": [2007],
            "population_demographic_projection": [210],
        }
    )
    with pytest.raises(AnchorError, match="Missing"):
        compare_population(_official(), projections)


POLICY = PopulationPolicy(
    calibration_year=2007,
    backcast_start_year=2005,
    backcast_end_year=2006,
    holdout_calibration_start=2008,
    holdout_calibration_end=2008,
    holdout_evaluation_start=2007,
    holdout_evaluation_end=2007,
    anchor_tolerance_persons=1e-4,
    demographic_tolerance_persons=1e-5,
    link_quantiles=[0.95, 0.99],
    large_link_change=0.2,
)


def _panel():
    periods = pd.period_range("2005-01", "2008-12", freq="M")
    n = len(periods)
    frame = pd.DataFrame(
        {
            "dep_code": 5,
            "department": "A",
            "period": periods.astype(str),
            "year": periods.year,
            "employed": np.linspace(90, 92, n),
            "unemployed": 10.0,
            "inactive": 50.0,
            "population": np.linspace(190, 205, n),
        }
    )
    frame["labor_force"] = frame["employed"] + frame["unemployed"]
    frame["working_age"] = frame["labor_force"] + frame["inactive"]
    return frame


def _anchors(panel):
    annual = (
        panel[panel["year"] >= 2007]
        .groupby(["dep_code", "department", "year"], as_index=False)[
            [
                "employed",
                "unemployed",
                "inactive",
                "population",
                "labor_force",
                "working_age",
            ]
        ]
        .mean()
    )
    return annual


def test_backcast_replaces_only_early_population():
    panel = _panel()
    projections = pd.DataFrame(
        {
            "dep_code": 5,
            "year": [2005, 2006, 2007, 2008],
            "population_demographic_projection": [180.0, 185.0, 190.0, 195.0],
        }
    )
    anchors = _anchors(panel)
    backcast = DemographicPopulationBackcast(POLICY)
    revised, calibration = backcast.revise(panel, projections, anchors)
    quality = backcast.verify(
        panel, revised, anchors, projections, calibration
    )
    assert quality["max_demographic_target_error_persons"] < 1e-6
    early = revised["year"] < 2007
    pd.testing.assert_series_equal(
        revised.loc[~early, "population"], panel.loc[~early, "population"]
    )
    factor = calibration.loc[0, "scale_factor"]
    means = revised.loc[early].groupby("year")["population"].mean()
    np.testing.assert_allclose(
        means.to_numpy(), np.array([180.0, 185.0]) * factor
    )


def test_backcast_rejects_incomplete_projection():
    panel = _panel()
    projections = pd.DataFrame(
        {
            "dep_code": 5,
            "year": [2006, 2007],
            "population_demographic_projection": [185.0, 190.0],
        }
    )
    with pytest.raises(PopulationRevisionError, match="incomplete"):
        DemographicPopulationBackcast(POLICY).revise(
            panel, projections, _anchors(panel)
        )
