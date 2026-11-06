"""Monthly diagnostics and experimental forecasts on a synthetic delivery."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from icml.delivery.monthly_report import _series_diagnostics, monthly_report
from icml.forecast import forecast_delivery, forecast_series

pytest.importorskip("statsmodels")


def _group(values, start_year=2010):
    months = pd.period_range(f"{start_year}-01", periods=len(values), freq="M").astype(str)
    return pd.DataFrame({"period": months, "unemployment_rate": values, "employed": 1000 + np.arange(len(values))})


def test_a_normal_month_is_not_flagged_and_a_jump_is():
    rng = np.random.default_rng(0)
    base = 0.10 + 0.01 * np.sin(np.arange(200) * 2 * np.pi / 12) + rng.normal(0, 0.002, 200)
    quiet = _series_diagnostics(_group(base), "unemployment_rate")
    assert quiet is not None and not quiet["flag"] and quiet["measure_unit"] == "pp"
    jump = base.copy(); jump[-1] += 0.05
    loud = _series_diagnostics(_group(jump), "unemployment_rate")
    assert loud["flag"] and abs(loud["mom_zscore"]) > 3 and loud["yoy_change"] is not None


def test_levels_report_percent_changes():
    d = _series_diagnostics(_group(np.linspace(0.1, 0.1, 60)), "employed")
    assert d["measure_unit"] == "%" and d["mom_change"] == pytest.approx(100 / 1058, rel=1e-6)


def test_short_or_non_finite_series_are_skipped():
    assert _series_diagnostics(_group(np.full(12, 0.1)), "unemployment_rate") is None
    bad = np.full(60, 0.1); bad[-1] = np.nan
    assert _series_diagnostics(_group(bad), "unemployment_rate") is None


def _delivery(tmp_path, name, bump=0.0):
    folder = tmp_path / name
    (folder / "universe_census" / "labor").mkdir(parents=True)
    months = pd.period_range("2010-01", periods=200, freq="M").astype(str)
    rows = []
    for nt in ("ICML_COMPLETO", "DANE_REFERENCIA"):
        for i, m in enumerate(months):
            emp = 20e6 + 10000 * i + (bump if m >= "2026-01" else 0)
            rows.append({"period": m, "national_type": nt, "employed": emp, "unemployed": 2e6, "labor_force": emp + 2e6,
                         "unemployment_rate": 2e6 / (emp + 2e6), "employment_rate": 0.57, "participation_rate": 0.63})
    path = "universe_census/labor/labor_national_census.csv"
    pd.DataFrame(rows).to_csv(folder / path, index=False)
    manifest = {"run_id": name, "cutoff": str(months[-1]), "outputs": [{"source_product": "labor.nacionales", "universe": "census", "path": path}]}
    (folder / "MANIFEST.json").write_text(json.dumps(manifest))
    return folder


def test_monthly_report_writes_json_and_markdown_and_counts_revisions(tmp_path):
    previous = _delivery(tmp_path, "2026-01-01_000000_cutoff-2026-07_total")
    current = _delivery(tmp_path, "2026-02-01_000000_cutoff-2026-08_anchored", bump=500.0)
    report = monthly_report(current, previous, frozen_through=2025)
    assert (current / "MONTHLY_REPORT.json").is_file() and (current / "MONTHLY_REPORT.md").is_file()
    assert len(report["series"]) == 12 and report["previous_run_id"] == previous.name
    employed = report["revisions"]["labor.nacionales"]["employed"]
    assert employed["cells_changed"] > 0 and employed["cells_compared"] == 2 * 8  # 2026 months only
    assert "## National (ICML, census universe)" in (current / "MONTHLY_REPORT.md").read_text()


def test_forecast_series_returns_horizon_points_with_intervals_and_skips_flat_series():
    y = 0.1 + 0.01 * np.sin(np.arange(120) * 2 * np.pi / 12)
    out = forecast_series(y, 6)
    assert out is not None and len(out["point"]) == 6 and (out["upper80"] >= out["lower80"]).all()
    assert forecast_series(np.full(120, 0.1), 6) is None


def test_forecast_delivery_writes_experimental_rows_outside_the_delivery(tmp_path):
    folder = _delivery(tmp_path, "2026-02-01_000000_cutoff-2026-08_anchored")
    summary = forecast_delivery(folder, horizon=3, fit_years=5)
    out = folder.parent / (folder.name + "_forecasts")
    table = pd.read_csv(out / "forecasts_EXPERIMENTAL.csv")
    assert summary["series_forecast"] >= 1 and (table.status == "EXPERIMENTAL_UNIVARIATE_HOLT_WINTERS").all()
    assert set(table.period) == {"2026-09", "2026-10", "2026-11"}
    assert ((table.lower80 <= table.forecast) & (table.forecast <= table.upper80)).all()
    with pytest.raises(FileExistsError):
        forecast_delivery(folder, horizon=3)
