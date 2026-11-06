import numpy as np
import pandas as pd
import pytest

from icml.national.disaggregation import (
    AnnualSplicer,
    ChowLinDisaggregator,
    DisaggregationSpec,
    NationalSpecificationError,
    SpliceSpec,
    prepare_annual_source,
    prepare_monthly_indicators,
)

QUANTITIES = (
    "population",
    "working_age",
    "labor_force",
    "employed",
    "unemployed",
    "inactive",
)
TOKENS = {"working_age": "pet", "labor_force": "pea"}
INDICATORS = {q: ["cpi"] for q in QUANTITIES}


def _annual(years, scale, suffix):
    frame = pd.DataFrame({"year": years})
    for position, quantity in enumerate(QUANTITIES):
        token = TOKENS.get(quantity, quantity)
        frame[f"{token}_{suffix}"] = (
            scale * (position + 1) * (1 + 0.02 * np.arange(len(years)))
        )
    return frame


def _indicators(start_year, n_years, seed=7):
    rng = np.random.default_rng(seed)
    n = 12 * n_years
    periods = pd.period_range(f"{start_year}-01", periods=n, freq="M")
    return pd.DataFrame(
        {
            "year": periods.year,
            "month": periods.month,
            "cpi": 100 + np.cumsum(rng.normal(0.5, 0.2, n)),
        }
    )


def test_annual_source_validation():
    good = _annual([2001, 2002], 1e6, "geih")
    assert list(prepare_annual_source(good, "geih").columns) == list(
        QUANTITIES
    )
    with pytest.raises(NationalSpecificationError, match="Missing"):
        prepare_annual_source(good.drop(columns="pet_geih"), "geih")
    negative = good.copy()
    negative.loc[0, "employed_geih"] = -1
    with pytest.raises(NationalSpecificationError, match="Negative"):
        prepare_annual_source(negative, "geih")
    duplicated = pd.concat([good, good])
    with pytest.raises(NationalSpecificationError, match="unique"):
        prepare_annual_source(duplicated, "geih")


def test_indicators_reject_gaps_nan_and_partial_years():
    indicators = _indicators(1995, 2)
    assert len(prepare_monthly_indicators(indicators, ["cpi"])) == 24
    with pytest.raises(NationalSpecificationError, match="gaps"):
        prepare_monthly_indicators(indicators.drop(index=5), ["cpi"])
    with_nan = indicators.copy()
    with_nan.loc[3, "cpi"] = np.nan
    with pytest.raises(NationalSpecificationError, match="finite"):
        prepare_monthly_indicators(with_nan, ["cpi"])
    with pytest.raises(NationalSpecificationError, match="full years"):
        prepare_monthly_indicators(indicators.iloc[:18], ["cpi"])


def test_splice_keeps_observed_values_and_fills_history():
    enh = _annual(list(range(1995, 2003)), 1e6, "enh")
    geih = _annual(list(range(2001, 2005)), 1.05e6, "geih")
    annual, diagnostics = AnnualSplicer(SpliceSpec("ratio", 2)).splice(
        enh, geih
    )
    observed = prepare_annual_source(geih, "geih")
    np.testing.assert_array_equal(
        annual.loc[observed.index].to_numpy(), observed.to_numpy()
    )
    assert str(annual.index[0]) == "1995"
    assert len(diagnostics) == 6
    assert diagnostics[0]["overlap"] == ["2001", "2002"]


def test_disaggregation_preserves_annual_means():
    spec = DisaggregationSpec("chow-lin-maxlog", True, 0.0, INDICATORS)
    indicators = prepare_monthly_indicators(_indicators(1995, 6), ["cpi"])
    years = pd.period_range("1995", periods=6, freq="Y")
    annual = pd.Series(
        1e7 * (1 + 0.03 * np.arange(6)), index=years, name="employed"
    )
    monthly, diagnostics = ChowLinDisaggregator(spec).disaggregate(
        annual, indicators[["cpi"]]
    )
    means = monthly.groupby(monthly.index.asfreq("Y")).mean()
    np.testing.assert_allclose(
        means.to_numpy(), annual.to_numpy(), atol=1e-4, rtol=0
    )
    assert diagnostics["method"] == "chow-lin-maxlog"
    assert diagnostics["nonpositive_months"] == 0


def test_spec_requires_indicators_for_every_quantity():
    with pytest.raises(ValueError, match="six"):
        DisaggregationSpec("chow-lin-maxlog", True, 0.0, {"employed": ["x"]})
    with pytest.raises(ValueError, match="duplicated"):
        DisaggregationSpec(
            "chow-lin-maxlog",
            True,
            0.0,
            {**INDICATORS, "employed": ["a", "a"]},
        )
