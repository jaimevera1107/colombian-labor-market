import pandas as pd
import pytest

from icml.domain.periods import (
    MonthlyPeriod,
    month_range,
    period_years,
    validate_periods,
)


def test_parse_and_format_round_trip():
    assert str(MonthlyPeriod.parse("1993-01")) == "1993-01"


@pytest.mark.parametrize("text", ["1993-13", "93-01", "1993/01", "", "x"])
def test_parse_rejects_malformed(text):
    with pytest.raises(ValueError):
        MonthlyPeriod.parse(text)


def test_shift_crosses_year_boundaries():
    assert str(MonthlyPeriod(2000, 12).shift(1)) == "2001-01"
    assert str(MonthlyPeriod(2001, 1).shift(-1)) == "2000-12"


def test_month_range_inclusive_and_rc1_length():
    periods = month_range("1993-01", "2026-08")
    assert periods[0] == "1993-01"
    assert periods[-1] == "2026-08"
    assert len(periods) == 404


def test_month_range_rejects_reversed_bounds():
    with pytest.raises(ValueError):
        month_range("2001-01", "2000-12")


def test_validate_detects_gaps_and_duplicates():
    with pytest.raises(ValueError, match="contiguous"):
        validate_periods(["2000-01", "2000-03"])
    with pytest.raises(ValueError, match="contiguous"):
        validate_periods(["2000-01", "2000-01"])
    assert validate_periods(["2000-03", "2000-01"], require_contiguous=False)


def test_validate_rejects_empty():
    with pytest.raises(ValueError, match="empty"):
        validate_periods([])


def test_period_years():
    years = period_years(pd.Series(["1993-01", "2026-08"]))
    assert years.tolist() == [1993, 2026]
