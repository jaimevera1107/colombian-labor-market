import numpy as np
import pandas as pd
import pytest

from icml.evaluation.closures import UniformRakingClosure, build_closures


def _panel():
    rows = []
    for period in ("2010-01", "2010-02"):
        for code, scale in ((1, 1.0), (2, 2.0)):
            rows.append(
                {
                    "dep_code": code,
                    "period": period,
                    "year": 2010,
                    "employed": 90.0 * scale,
                    "unemployed": 10.0 * scale,
                    "inactive": 50.0 * scale,
                    "population_demographic_projection": 200.0 * scale,
                }
            )
    frame = pd.DataFrame(rows)
    frame["labor_force"] = frame["employed"] + frame["unemployed"]
    frame["working_age"] = frame["labor_force"] + frame["inactive"]
    return frame


def _national():
    return pd.DataFrame(
        {
            "period": ["2010-01", "2010-02"],
            "employed": [300.0, 270.0],
            "unemployed": [30.0, 33.0],
            "inactive": [150.0, 140.0],
            "population": [580.0, 600.0],
        }
    )


def test_uniform_raking_adds_to_national_and_keeps_identities():
    result = UniformRakingClosure().apply(_panel(), _national(), None)
    totals = result.groupby("period")[
        ["employed", "unemployed", "inactive", "labor_population_reconciled"]
    ].sum()
    national = _national().set_index("period")
    for column in ("employed", "unemployed", "inactive"):
        np.testing.assert_allclose(totals[column], national[column])
    np.testing.assert_allclose(
        totals["labor_population_reconciled"], national["population"]
    )
    np.testing.assert_allclose(
        result["working_age"],
        result["employed"] + result["unemployed"] + result["inactive"],
    )


def test_uniform_raking_scales_every_territory_by_the_same_factor():
    result = UniformRakingClosure().apply(_panel(), _national(), None)
    january = result[result["period"] == "2010-01"].set_index("dep_code")
    assert january.loc[2, "employed"] == pytest.approx(
        2 * january.loc[1, "employed"]
    )


def test_unknown_closure_variant_is_rejected():
    with pytest.raises(ValueError):
        build_closures(["mystery"], None)
