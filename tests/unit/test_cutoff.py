"""The cutoff helpers reproduce the literals they replace, bit for bit."""

import os
import subprocess
import sys

import pandas as pd
import pytest

from icml.domain.cutoff import (
    FIRST_MONTH,
    FROZEN_CUTOFF,
    INFORMALITY_NEW_FIRST_MONTH,
    SECTORAL_FIRST_MONTH,
    expected_month_count,
    month_labels,
    month_periods,
    month_starts,
    next_month,
    shift_label,
    trailing_window_label,
)


def test_defaults_match_the_frozen_vintage():
    assert FIRST_MONTH == "1993-01"
    assert FROZEN_CUTOFF == "2026-08"
    assert expected_month_count() == 404


def test_period_index_equals_original_literal():
    original = pd.period_range("1993-01", "2026-08", freq="M")
    assert month_periods().equals(original)


def test_labels_equal_original_astype_and_strftime_forms():
    original = pd.period_range("1993-01", "2026-08", freq="M")
    assert month_labels() == original.astype(str).tolist()
    assert month_labels() == list(original.strftime("%Y-%m"))


def test_month_starts_equal_original_date_range():
    original = pd.date_range("1993-01-01", "2026-08-01", freq="MS")
    assert month_starts().equals(original)


def test_informality_window_equals_original_literal():
    original = pd.date_range("2021-01-01", "2026-08-01", freq="MS")
    got = month_starts(INFORMALITY_NEW_FIRST_MONTH)
    assert got.equals(original)
    assert len(got) == 68


def test_explicit_cutoff_moves_the_calendar_without_touching_defaults():
    assert month_labels(last="2026-07")[-1] == "2026-07"
    assert month_labels()[-1] == "2026-08"
    assert expected_month_count(last="2026-09") == 405


@pytest.mark.parametrize("bad", ["2026-8", "202608", "2026-13", "", "agosto"])
def test_malformed_periods_are_rejected(bad):
    with pytest.raises(ValueError):
        month_periods(last=bad)


def test_reversed_range_is_rejected():
    with pytest.raises(ValueError, match="precedes"):
        month_periods("2026-08", "1993-01")


def test_next_month_and_year_rollover():
    assert next_month() == "2026-09"
    assert next_month("2026-12") == "2027-01"
    assert shift_label("2026-01", -1) == "2025-12"


def test_trailing_window_reproduces_the_original_h22_literals():
    # Literals previously written by hand in operations/h22.py.
    assert trailing_window_label("2026-09") == "2026-07/2026-09"
    assert trailing_window_label("2026-08") == "2026-06/2026-08"
    assert trailing_window_label("2026-02") == "2025-12/2026-02"
    assert trailing_window_label("2026-08", 1) == "2026-08/2026-08"
    with pytest.raises(ValueError):
        trailing_window_label("2026-08", 0)


def test_sectoral_window_keeps_its_140_direct_months():
    # ``direct_months: 140`` used to be a literal in sectoral_monthly.py.
    assert expected_month_count(SECTORAL_FIRST_MONTH) == 140
    original = pd.period_range("2015-01", "2026-08", freq="M")
    assert month_periods(SECTORAL_FIRST_MONTH).equals(original)
    assert list(month_periods(SECTORAL_FIRST_MONTH).strftime("%Y-%m")) == list(
        original.strftime("%Y-%m")
    )


def test_panel_shape_constants_equal_the_literals_they_replace():
    from icml.domain.cutoff import N_MONTHS, ROWS_33, ROWS_NATIONAL

    assert N_MONTHS == 404
    assert ROWS_33 == 13332 == 33 * 404
    assert ROWS_NATIONAL == 808 == 2 * 404
    # Sectoral matrix: 33 departments x 15 sectors x months.
    assert ROWS_33 * 15 == 199980


def _in_clean_interpreter(code: str, cutoff: str | None) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k != "ICML_CUTOFF"}
    if cutoff is not None:
        env["ICML_CUTOFF"] = cutoff
    return subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True)


def test_active_cutoff_defaults_to_the_frozen_vintage():
    code = "import icml.domain.cutoff as c; print(c.ACTIVE_CUTOFF, c.N_MONTHS, c.ROWS_33)"
    result = _in_clean_interpreter(code, None)
    assert result.stdout.split() == ["2026-08", "404", "13332"], result.stderr


def test_active_cutoff_moves_calendars_and_shapes_but_not_the_frozen_name():
    code = (
        "import icml.domain.cutoff as c;"
        "print(c.ACTIVE_CUTOFF, c.FROZEN_CUTOFF, c.N_MONTHS, c.ROWS_33, c.ROWS_NATIONAL, len(c.month_starts()))"
    )
    result = _in_clean_interpreter(code, "2026-07")
    assert result.stdout.split() == ["2026-07", "2026-08", "403", "13299", "806", "403"], result.stderr


def test_a_malformed_active_cutoff_stops_the_import():
    result = _in_clean_interpreter("import icml.domain.cutoff", "agosto")
    assert result.returncode != 0
    assert "YYYY-MM" in result.stderr
