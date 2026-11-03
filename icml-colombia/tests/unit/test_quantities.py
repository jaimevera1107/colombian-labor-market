import numpy as np
import pandas as pd
import pytest

from icml.domain.quantities import (
    LaborQuantity,
    RateScale,
    check_labor_identities,
    compute_labor_rates,
    to_canonical_columns,
)


def _levels(**overrides: float) -> pd.DataFrame:
    row = {
        "population": 100.0,
        "working_age": 80.0,
        "labor_force": 50.0,
        "employed": 45.0,
        "unemployed": 5.0,
        "inactive": 30.0,
    }
    row.update(overrides)
    return pd.DataFrame([row])


def test_identities_pass_on_consistent_levels():
    report = check_labor_identities(_levels(), tolerance_persons=1e-6)
    assert report.passed
    assert report.max_labor_force_residual == 0.0


def test_labor_force_residual_detected():
    report = check_labor_identities(
        _levels(labor_force=51.0), tolerance_persons=1e-6
    )
    assert not report.passed
    assert report.max_labor_force_residual == pytest.approx(1.0)


def test_working_age_above_population_detected():
    report = check_labor_identities(
        _levels(population=79.0), tolerance_persons=1e-6
    )
    assert report.working_age_above_population_rows == 1
    assert not report.passed


def test_population_check_can_be_disabled():
    frame = _levels().drop(columns="population")
    report = check_labor_identities(
        frame, tolerance_persons=0.0, check_population=False
    )
    assert report.passed


def test_negative_levels_detected():
    report = check_labor_identities(
        _levels(unemployed=-1.0, labor_force=44.0, working_age=74.0),
        tolerance_persons=1e-6,
    )
    assert report.negative_level_rows == 1


@pytest.mark.parametrize(
    ("kwargs", "error"),
    [
        ({"tolerance_persons": -1.0}, ValueError),
    ],
)
def test_invalid_arguments(kwargs, error):
    with pytest.raises(error):
        check_labor_identities(_levels(), **kwargs)


def test_empty_frame_rejected():
    with pytest.raises(ValueError, match="empty"):
        check_labor_identities(_levels().iloc[0:0], tolerance_persons=0.0)


def test_missing_column_rejected():
    with pytest.raises(KeyError, match="employed"):
        check_labor_identities(
            _levels().drop(columns="employed"), tolerance_persons=0.0
        )


def test_rates_in_both_scales():
    fraction = compute_labor_rates(_levels(), scale=RateScale.FRACTION)
    percent = compute_labor_rates(_levels(), scale=RateScale.PERCENT)
    assert fraction.loc[0, "unemployment_rate"] == pytest.approx(0.1)
    assert percent.loc[0, "participation_rate"] == pytest.approx(62.5)


def test_rates_are_nan_for_zero_denominators():
    rates = compute_labor_rates(
        _levels(labor_force=0.0, working_age=0.0), scale=RateScale.FRACTION
    )
    assert np.isnan(rates.loc[0, "unemployment_rate"])
    assert np.isnan(rates.loc[0, "employment_rate"])


def test_rates_do_not_mutate_input():
    frame = _levels()
    snapshot = frame.copy()
    compute_labor_rates(frame, scale=RateScale.PERCENT)
    pd.testing.assert_frame_equal(frame, snapshot)


def test_legacy_departmental_columns_are_renamed():
    legacy = pd.DataFrame(
        [
            {
                "ocupados": 1,
                "desocupados": 2,
                "inactivos": 3,
                "pet": 6,
                "pea": 3,
                "poblacion_laboral_conciliada": 9,
            }
        ]
    )
    canonical = to_canonical_columns(legacy)
    assert set(canonical.columns) == {str(q) for q in LaborQuantity}


def test_ambiguous_legacy_columns_rejected():
    legacy = pd.DataFrame([{"employed": 1, "ocupados": 1}])
    with pytest.raises(ValueError, match="Ambiguous"):
        to_canonical_columns(legacy)
