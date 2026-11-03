import pandas as pd
import pytest

from icml.pipeline.vintage import (
    STATE_FINAL,
    STATE_PENDING_ANCHOR,
    STATE_PROVISIONAL,
    VintageError,
    VintagePolicy,
    apply_update,
    assert_accepted,
    compare_vintages,
    revision_state,
    with_revision_state,
)

KEYS = ["dep_code", "period"]
QUANTITIES = ["employed"]


def _product(periods, employed=100.0):
    frame = pd.DataFrame({"dep_code": 5, "period": periods})
    frame["employed"] = employed
    return frame


def test_states_follow_window_and_anchor_dates():
    # The next window (ending 2026-09) covers 2025-10 onward, so only
    # those months can still be revised; 2025-09 is already closed.
    policy = VintagePolicy("2026-08", 2025, 12)
    periods = pd.Series(
        ["2024-12", "2025-09", "2025-10", "2026-01", "2026-08"]
    )
    states = revision_state(periods, policy)
    assert list(states) == [
        STATE_FINAL,
        STATE_FINAL,
        STATE_PROVISIONAL,
        STATE_PROVISIONAL,
        STATE_PROVISIONAL,
    ]


def test_pending_anchor_covers_years_without_annex():
    policy = VintagePolicy("2026-08", 2024, 12)
    states = revision_state(pd.Series(["2024-06", "2025-03"]), policy)
    assert list(states) == [STATE_FINAL, STATE_PENDING_ANCHOR]


def test_frozen_window_marks_only_the_last_month():
    policy = VintagePolicy("2026-08", 2025, 12, revise_open_window=False)
    states = revision_state(pd.Series(["2026-07", "2026-08"]), policy)
    assert list(states) == [STATE_PENDING_ANCHOR, STATE_PROVISIONAL]


def test_update_keeps_final_rows_and_adds_new_ones():
    policy_old = VintagePolicy("2026-08", 2025, 12)
    previous = with_revision_state(
        _product(["2024-01", "2026-08"], 100.0), policy_old
    )
    current = _product(["2024-01", "2026-08", "2026-09"], 200.0)
    policy_new = VintagePolicy("2026-09", 2025, 12)
    merged = apply_update(previous, current, KEYS, policy_new)
    values = merged.set_index("period")["employed"]
    assert values["2024-01"] == 100.0
    assert values["2026-08"] == 200.0
    assert values["2026-09"] == 200.0
    report = compare_vintages(previous, merged, KEYS, QUANTITIES, policy_old)
    assert report.accepted
    assert report.summary["new_rows"] == 1
    assert_accepted(report)


def test_comparison_rejects_a_rewritten_final_cell():
    policy = VintagePolicy("2026-08", 2025, 12)
    previous = with_revision_state(_product(["2024-01"], 100.0), policy)
    current = _product(["2024-01"], 150.0)
    report = compare_vintages(previous, current, KEYS, QUANTITIES, policy)
    assert not report.accepted
    assert report.summary["protected_cells_changed"] == 1
    with pytest.raises(VintageError):
        assert_accepted(report)


def test_comparison_requires_published_state_and_rows():
    policy = VintagePolicy("2026-08", 2025, 12)
    with pytest.raises(VintageError):
        compare_vintages(
            _product(["2024-01"]),
            _product(["2024-01"]),
            KEYS,
            QUANTITIES,
            policy,
        )
    previous = with_revision_state(_product(["2024-01", "2024-02"]), policy)
    with pytest.raises(VintageError):
        compare_vintages(
            previous, _product(["2024-01"]), KEYS, QUANTITIES, policy
        )
