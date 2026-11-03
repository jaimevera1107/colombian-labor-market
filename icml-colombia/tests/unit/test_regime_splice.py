"""Regime splice: estimate a level break and move only the unobserved segment."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from icml.informality.regime_splice import (
    BreakEstimate,
    RegimeSplice,
    estimate_break,
    splice_regime,
)

CUT = "2001-01"
PERIODS = [f"{y}-{m:02d}" for y in range(1993, 2004) for m in range(1, 13)]
ENABLED = RegimeSplice(enabled=True)


def _series(jump: float, slope: float = 0.0, noise: float = 0.002, seed: int = 0) -> pd.Series:
    rng = np.random.default_rng(seed)
    cut = PERIODS.index(CUT)
    values = [
        0.66 + slope * k + (jump if k >= cut else 0.0) + rng.normal(0, noise)
        for k in range(len(PERIODS))
    ]
    return pd.Series(values, index=PERIODS)


def test_the_estimator_recovers_a_known_break():
    estimate = estimate_break(_series(jump=0.025), CUT, 24)
    assert estimate.delta == pytest.approx(0.025, abs=0.004)
    assert 0 < estimate.std_error <= estimate.std_error_autocorrelation_adjusted + 1e-12


def test_no_break_is_estimated_as_none():
    assert abs(estimate_break(_series(jump=0.0, seed=3), CUT, 24).delta) < 0.004


def test_a_trend_is_not_mistaken_for_a_break():
    series = _series(jump=0.0, slope=0.0005)
    estimate = estimate_break(series, CUT, 24)
    assert estimate.diff_of_means > 0.010  # 24 months of trend: the means difference sees a "break"
    assert abs(estimate.delta) < 0.004  # the discontinuity estimate does not
    assert estimate.slope_per_month == pytest.approx(0.0005, abs=0.0002)


def test_a_real_break_over_a_trend_is_recovered_not_inflated():
    estimate = estimate_break(_series(jump=0.025, slope=0.0005), CUT, 24)
    assert estimate.delta == pytest.approx(0.025, abs=0.004)


@pytest.mark.parametrize("window", [60, 200])
def test_a_window_that_does_not_fit_is_refused(window):
    with pytest.raises(ValueError, match="does not fit"):
        estimate_break(_series(0.02), CUT, window)


def test_gaps_and_unknown_months_are_refused():
    broken = _series(0.02)
    broken.iloc[PERIODS.index(CUT) + 3] = np.nan
    with pytest.raises(ValueError, match="missing values"):
        estimate_break(broken, CUT, 24)
    with pytest.raises(ValueError, match="not in the series"):
        estimate_break(_series(0.02), "2030-01", 24)


def test_configuration_defaults_to_off_and_validates(tmp_path):
    assert RegimeSplice.from_toml(tmp_path / "missing.toml") == RegimeSplice(enabled=False)
    path = tmp_path / "splice.toml"
    path.write_text('[regime_splice]\nenabled = true\nbreak_month = "2001-01"\nwindow_months = 18\n')
    assert RegimeSplice.from_toml(path) == RegimeSplice(enabled=True, window_months=18)
    path.write_text("[regime_splice]\nenabled = true\nwindow = 3\n")
    with pytest.raises(ValueError, match="Unknown"):
        RegimeSplice.from_toml(path)
    with pytest.raises(ValueError, match="YYYY-MM"):
        RegimeSplice(break_month="2001")
    with pytest.raises(ValueError, match="at least"):
        RegimeSplice(window_months=3)


# ------------------------------------------------------------------ the splice


def _panel():
    """National (two types), two cities and two departments with different breaks."""
    employed = 1_000_000.0
    national_rows, city_rows, dept_rows, prior_rows = [], [], [], []
    for national_type in ("ICML_COMPLETO", "DANE_REFERENCIA"):
        rate = _series(0.025, seed=1)
        for period in PERIODS:
            national_rows.append(
                {"period": period, "national_type": national_type, "employed_frozen": employed,
                 "informality_rate_estimated": rate[period], "informal_estimated": employed * rate[period],
                 "formal_estimated": employed * (1 - rate[period]), "provenance": "X"}
            )
    for code, jump, seed in (("11", 0.020, 2), ("05", 0.030, 3)):
        rate = _series(jump, seed=seed)
        for period in PERIODS:
            city_rows.append(
                {"period": period, "city_code": code, "employed_frozen": employed,
                 "informality_rate": rate[period], "informal_estimated": employed * rate[period],
                 "formal_estimated": employed * (1 - rate[period])}
            )
    for code, jump, seed in (("11", 0.022, 4), ("05", 0.028, 5)):
        rate = _series(jump, seed=seed)
        for period in PERIODS:
            dept_rows.append({"period": period, "dep_code": code, "informality_rate": rate[period]})
            prior_rows.append({"period": period, "dep_code": code, "prior_rate": rate[period] - 0.001})
    return (pd.DataFrame(national_rows), pd.DataFrame(city_rows),
            pd.DataFrame(prior_rows), pd.DataFrame(dept_rows))


def _step(frame: pd.DataFrame, key: str | None, column: str) -> float:
    """Mean jump of a column between 2000-12 and 2001-01 over the series."""
    rows = frame[frame.period.isin(["2000-12", CUT])]
    wide = rows.pivot(index="period", columns=key, values=column) if key else rows.set_index("period")[[column]]
    return float((wide.loc[CUT] - wide.loc["2000-12"]).abs().mean())


def test_only_the_unobserved_segment_moves_and_the_rest_is_untouched():
    national, cities, priors, departments = _panel()
    snapshot = [x.copy() for x in (national, cities, priors)]
    new_national, new_cities, new_priors, report = splice_regime(
        national=national, cities=cities, priors=priors, departments=departments, config=ENABLED
    )
    for before, after in ((national, new_national), (cities, new_cities), (priors, new_priors)):
        kept = before.period >= CUT
        pd.testing.assert_frame_equal(before[kept].reset_index(drop=True), after[kept].reset_index(drop=True))
        assert (after[~kept].select_dtypes("number").to_numpy() != before[~kept].select_dtypes("number").to_numpy()).any()
    for original, untouched in zip((national, cities, priors), snapshot, strict=True):
        pd.testing.assert_frame_equal(original, untouched)  # the inputs are not modified
    assert report["months_shifted"] == 96  # 1993-01 .. 2000-12


def test_every_series_moves_by_its_own_break_and_the_seam_closes():
    national, cities, priors, departments = _panel()
    new_national, new_cities, new_priors, report = splice_regime(
        national=national, cities=cities, priors=priors, departments=departments, config=ENABLED
    )
    pre = national.period == "1995-06"
    shift = (new_national.informality_rate_estimated - national.informality_rate_estimated)[pre]
    assert shift.nunique() == 1  # a constant, so the retropolated dynamics are kept
    assert float(shift.iloc[0]) == pytest.approx(report["national"]["delta"])
    # the two national types are shifted identically
    by_type = (new_national.informality_rate_estimated - national.informality_rate_estimated)[pre]
    assert by_type.iloc[0] == pytest.approx(by_type.iloc[1])
    # each city and department by its own break
    assert report["cities"]["11"] == pytest.approx(0.020, abs=0.005)
    assert report["cities"]["05"] == pytest.approx(0.030, abs=0.005)
    assert report["departments"]["11"] == pytest.approx(0.022, abs=0.005)
    assert _step(new_national, "national_type", "informality_rate_estimated") < 0.4 * _step(national, "national_type", "informality_rate_estimated")
    assert _step(new_cities, "city_code", "informality_rate") < 0.4 * _step(cities, "city_code", "informality_rate")


def test_counts_follow_the_shifted_rates_only_before_the_break():
    national, cities, priors, departments = _panel()
    new_national, new_cities, *_ = splice_regime(
        national=national, cities=cities, priors=priors, departments=departments, config=ENABLED
    )
    for frame, rate in ((new_national, "informality_rate_estimated"), (new_cities, "informality_rate")):
        pre = frame.period < CUT
        assert np.allclose(frame.loc[pre, "informal_estimated"], frame.loc[pre, "employed_frozen"] * frame.loc[pre, rate])
        assert np.allclose(frame.loc[pre, "informal_estimated"] + frame.loc[pre, "formal_estimated"], frame.loc[pre, "employed_frozen"])


def test_the_splice_refuses_to_leave_the_unit_interval():
    national, cities, priors, departments = _panel()
    cut = PERIODS.index(CUT)
    # A falling unobserved segment that ends well below the anchored level: a
    # positive shift would push its early months above 1.
    values = np.concatenate([np.linspace(0.995, 0.90, cut), np.full(len(PERIODS) - cut, 0.95)])
    for national_type in national.national_type.unique():
        rows = national.national_type == national_type
        national.loc[rows, "informality_rate_estimated"] = values
    with pytest.raises(ValueError, match="outside"):
        splice_regime(national=national, cities=cities, priors=priors, departments=departments, config=ENABLED)


def test_calling_it_while_disabled_is_a_programming_error():
    national, cities, priors, departments = _panel()
    with pytest.raises(ValueError, match="disabled"):
        splice_regime(national=national, cities=cities, priors=priors, departments=departments, config=RegimeSplice())


def test_break_estimate_exposes_plain_floats():
    assert all(isinstance(v, float) for v in estimate_break(_series(0.02), CUT, 24).as_dict().values())
    assert isinstance(estimate_break(_series(0.02), CUT, 24), BreakEstimate)
