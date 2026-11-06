"""Two closure controls that used to be exercised only by full runs (traceability gap 2)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from icml.informality.finalize_block import _BRIDGE_LEVELS, _refresh_bridge_levels
from icml.operations.informality_regeneration import strict_window_gate

LEVELS = dict(population=1000.0, working_age=800.0, labor_force=500.0, employed=450.0, unemployed=50.0, inactive=300.0)


def _bridge(rows):
    frame = pd.DataFrame(rows)
    for name in ("employed", "unemployed", "inactive", "labor_force", "working_age", "population"):
        frame[f"factor_geih_{name}"] = 0.5
        frame[f"geih_{name}"] = frame[name] * 0.5
        frame[f"outside_geih_{name}"] = frame[name] * 0.5
    return frame


def test_refresh_is_a_no_op_when_the_bridge_matches_the_labor_product():
    bridge = _bridge([{"dep_code": "05", "period": "2026-07", **LEVELS}, {"dep_code": "05", "period": "2026-08", **LEVELS}])
    labor = bridge[["period", "dep_code", *_BRIDGE_LEVELS]].copy()
    out, report = _refresh_bridge_levels(bridge, labor)
    assert report["rows_refreshed"] == 0 and report["months_refreshed"] == 0
    pd.testing.assert_frame_equal(out, bridge)


def test_stale_rows_take_the_labor_levels_and_the_geih_identities_are_rebuilt():
    bridge = _bridge([{"dep_code": "05", "period": "2026-07", **LEVELS}, {"dep_code": "05", "period": "2026-08", **LEVELS}])
    labor = bridge[["period", "dep_code", *_BRIDGE_LEVELS]].copy()
    # August re-identified: more employed, fewer inactive, same aggregates.
    labor.loc[labor.period == "2026-08", "employed"] = 480.0
    labor.loc[labor.period == "2026-08", "unemployed"] = 40.0
    labor.loc[labor.period == "2026-08", "labor_force"] = 520.0
    labor.loc[labor.period == "2026-08", "inactive"] = 280.0
    out, report = _refresh_bridge_levels(bridge, labor)
    assert report["rows_refreshed"] == 1 and report["first_month"] == report["last_month"] == "2026-08"
    assert report["max_level_change_people"] == pytest.approx(30.0)
    august = out[out.period == "2026-08"].iloc[0]
    july = out[out.period == "2026-07"].iloc[0]
    assert august["employed"] == 480.0 and july["employed"] == 450.0  # July untouched
    # GEIH components follow the frozen factors; aggregates are sums, so identities hold.
    assert august["geih_employed"] == pytest.approx(240.0)
    assert august["geih_labor_force"] == pytest.approx(august["geih_employed"] + august["geih_unemployed"])
    assert august["geih_working_age"] == pytest.approx(august["geih_labor_force"] + august["geih_inactive"])


def test_a_labor_product_that_does_not_cover_the_bridge_is_refused():
    bridge = _bridge([{"dep_code": "05", "period": "2026-08", **LEVELS}])
    labor = bridge[["period", "dep_code", *_BRIDGE_LEVELS]].copy()
    labor["period"] = "2026-07"
    with pytest.raises(ValueError, match="does not cover"):
        _refresh_bridge_levels(bridge, labor)


def _series(tmp_path, name, values):
    frame = pd.DataFrame({"period": [f"2000-{m:02d}" for m in range(1, 7)] + [f"2001-{m:02d}" for m in range(1, 7)],
                          "national_type": "ICML_COMPLETO", "informality_rate_estimated": values})
    path = tmp_path / name
    frame.to_csv(path, index=False)
    return path


def test_the_strict_window_ignores_differences_before_the_window_and_catches_them_inside(tmp_path):
    base = np.linspace(0.50, 0.55, 12)
    frozen = _series(tmp_path, "frozen.csv", base)
    rebuilt_before = _series(tmp_path, "rebuilt_before.csv", np.r_[base[:6] + 0.02, base[6:]])
    gate = strict_window_gate({"informalidad.nacionales": frozen}, {"informalidad.nacionales": rebuilt_before}, "2001-01", tmp_path / "w1")
    assert gate["informalidad.nacionales"]["status"] == "EQUIVALENT_WITHIN_TOLERANCES"
    assert (tmp_path / "w1" / "frozen_frozen.csv").is_file()
    rebuilt_inside = _series(tmp_path, "rebuilt_inside.csv", np.r_[base[:6], base[6:] + 0.02])
    gate = strict_window_gate({"informalidad.nacionales": frozen}, {"informalidad.nacionales": rebuilt_inside}, "2001-01", tmp_path / "w2")
    assert gate["informalidad.nacionales"]["status"] == "MISMATCH"
