"""Anchored vs total recalculation: frozen years, gates and planning."""

from __future__ import annotations

import pandas as pd
import pytest

from icml.recalculation.gates import (
    check_frozen_observations,
    check_frozen_parameters,
)
from icml.recalculation.graft import assert_frozen_unchanged, graft_frozen_years
from icml.recalculation.plan import plan_recalculation
from icml.recalculation.policy import (
    AnchorPolicy,
    anchor_year_from_years,
)

POLICY = AnchorPolicy(2025)
KEYS = ["period", "dep_code"]


def _table(values: dict[str, float]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"period": period, "dep_code": "05", "employed": value}
            for period, value in values.items()
        ]
    )


def test_every_month_of_an_anchored_year_is_frozen():
    # October-December 2025 are touched by an open rolling window in the
    # H36 vintage, but their year has an anchor: they are frozen anyway.
    assert POLICY.is_frozen("2025-10")
    assert POLICY.is_frozen("2025-12")
    assert POLICY.is_frozen("1993-01")
    assert not POLICY.is_frozen("2026-01")
    assert not POLICY.is_frozen("2026-08")


def test_split_keeps_order():
    frozen, opened = POLICY.split(["2025-12", "2026-01", "2024-01", "2026-08"])
    assert frozen == ["2025-12", "2024-01"]
    assert opened == ["2026-01", "2026-08"]


def test_anchor_only_advances():
    assert POLICY.advanced_to(2026).last_anchor_year == 2026
    with pytest.raises(ValueError, match="advance"):
        POLICY.advanced_to(2025)
    with pytest.raises(ValueError):
        AnchorPolicy(1900)


def test_anchor_year_comes_from_the_annex_years():
    assert anchor_year_from_years(range(2007, 2026)) == 2025
    with pytest.raises(ValueError):
        anchor_year_from_years([])


def test_graft_keeps_published_frozen_rows_and_takes_open_rows_from_recompute():
    published = _table({"2025-11": 10.0, "2025-12": 11.0, "2026-01": 12.0})
    # The recomputation re-identified late 2025 (a new window) and 2026.
    recomputed = _table(
        {"2025-11": 10.5, "2025-12": 11.5, "2026-01": 12.5, "2026-02": 13.0}
    )
    grafted, report = graft_frozen_years(published, recomputed, POLICY, keys=KEYS)
    by_period = grafted.set_index("period")["employed"]
    assert by_period["2025-11"] == 10.0
    assert by_period["2025-12"] == 11.0
    assert by_period["2026-01"] == 12.5  # open year: recomputed
    assert by_period["2026-02"] == 13.0  # new month
    assert report["rows_frozen_from_published"] == 2
    assert report["rows_open_from_recomputation"] == 2
    assert report["frozen_cells_a_recomputation_would_have_changed"] == 2
    assert report["frozen_cells_changed_in_output"] == 0
    assert_frozen_unchanged(published, grafted, POLICY, keys=KEYS)


def test_graft_detects_a_tampered_frozen_row():
    published = _table({"2025-12": 11.0, "2026-01": 12.0})
    grafted, _ = graft_frozen_years(published, published.copy(), POLICY, keys=KEYS)
    grafted.loc[grafted["period"] == "2025-12", "employed"] = 99.0
    with pytest.raises(AssertionError, match="frozen row"):
        assert_frozen_unchanged(published, grafted, POLICY, keys=KEYS)


def test_graft_refuses_new_rows_inside_a_frozen_year():
    published = _table({"2025-11": 10.0})
    recomputed = _table({"2025-11": 10.0, "2025-12": 11.0})
    with pytest.raises(ValueError, match="total recalculation"):
        graft_frozen_years(published, recomputed, POLICY, keys=KEYS)


def test_graft_rejects_changed_columns_and_duplicate_keys():
    published = _table({"2025-11": 10.0})
    with pytest.raises(ValueError, match="different columns"):
        graft_frozen_years(published, published.assign(extra=1), POLICY, keys=KEYS)
    with pytest.raises(ValueError, match="Duplicated keys"):
        graft_frozen_years(
            pd.concat([published, published]), published, POLICY, keys=KEYS
        )


def test_source_revision_of_a_frozen_year_blocks():
    previous = _table({"2024-05": 100.0, "2025-12": 200.0, "2026-01": 300.0})
    current = _table({"2024-05": 101.0, "2025-12": 200.0, "2026-01": 999.0})
    report = check_frozen_observations(
        previous, current, POLICY, keys=KEYS, value="employed"
    )
    assert report["status"] == "BLOCKED"
    assert report["n_revisions"] == 1  # 2026 is open: its change is allowed
    assert report["revisions"][0]["period"] == "2024-05"


def test_a_new_month_in_an_open_year_does_not_block():
    previous = _table({"2025-12": 200.0})
    current = _table({"2025-12": 200.0, "2026-09": 5.0})
    report = check_frozen_observations(
        previous, current, POLICY, keys=KEYS, value="employed"
    )
    assert report["status"] == "PASS"


def test_an_observation_added_inside_a_frozen_year_blocks():
    # DANE filled a window an earlier release left empty (real case: the
    # national window Dec 2022 - Feb 2023 of the informality annex).
    previous = _table({"2023-01": 1.0, "2023-03": 3.0})
    current = _table({"2023-01": 1.0, "2023-02": 2.0, "2023-03": 3.0})
    report = check_frozen_observations(
        previous, current, POLICY, keys=KEYS, value="employed"
    )
    assert report["status"] == "BLOCKED"
    assert report["n_added_in_frozen_years"] == 1
    assert report["n_revisions"] == 0
    assert report["n_changes"] == 1
    assert report["revisions"][0]["period"] == "2023-02"


def test_a_removed_frozen_observation_blocks():
    previous = _table({"2024-05": 100.0})
    current = _table({"2025-12": 1.0})
    report = check_frozen_observations(
        previous, current, POLICY, keys=KEYS, value="employed"
    )
    assert report["status"] == "BLOCKED"
    assert report["n_frozen_observations_removed"] == 1


def test_frozen_parameter_change_is_reported():
    report = check_frozen_parameters({"a.csv": "1", "b.csv": "2"}, {"a.csv": "1", "b.csv": "9"})
    assert report["status"] == "BLOCKED"
    assert report["changed"] == ["b.csv"]


def _plan(mode="anclado", **kwargs):
    base = {
        "previous_inputs": {"geih.xlsx": "a", "dept.xlsx": "b"},
        "current_inputs": {"geih.xlsx": "a", "dept.xlsx": "b"},
        "previous_parameters": {"priors.csv": "p"},
        "current_parameters": {"priors.csv": "p"},
    }
    base.update(kwargs)
    return plan_recalculation(mode, POLICY, **base)


def test_nothing_changed_means_nothing_to_do_in_anchored_mode():
    plan = _plan()
    assert plan["status"] == "SIN_CAMBIOS"
    assert plan["inputs"]["unchanged"] == 2
    assert "2025" in plan["frozen_years"]


def test_new_annex_means_run_in_anchored_mode():
    plan = _plan(current_inputs={"geih.xlsx": "a", "dept.xlsx": "b", "dept2026.xlsx": "c"})
    assert plan["status"] == "EJECUTAR"
    assert plan["inputs"]["added"] == ["dept2026.xlsx"]


def test_changed_parameter_blocks_anchored_mode_but_not_total():
    changed = {"current_parameters": {"priors.csv": "other"}}
    assert _plan(**changed)["status"] == "BLOQUEADO"
    total = _plan("total", confirm_total=True, **changed)
    assert total["status"] == "EJECUTAR"


def test_revision_of_frozen_years_blocks_with_a_clear_message():
    blocked = {"status": "BLOCKED", "n_revisions": 3}
    plan = _plan(observation_checks=(blocked,))
    assert plan["status"] == "BLOQUEADO"
    assert "3 cifras oficiales" in plan["blockers"][0]
    assert "recálculo total" in plan["blockers"][0]


def test_total_mode_needs_explicit_confirmation():
    unconfirmed = _plan("total")
    assert unconfirmed["status"] == "BLOQUEADO"
    assert "--confirmar-total" in unconfirmed["blockers"][0]
    assert _plan("total", confirm_total=True)["status"] == "EJECUTAR"


def test_unknown_mode_is_rejected():
    with pytest.raises(ValueError, match="mode"):
        _plan("parcial")
