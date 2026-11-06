"""Experimental forecasts of the delivered series.

For every monitored series of a delivery (national and departmental labor
levels and rates, informality rate) an exponential-smoothing model with
additive trend and additive seasonality (Holt-Winters, ``statsmodels``) is
fitted on the last ``fit_years`` years and projected ``horizon`` months
ahead with an 80 % interval taken from the in-sample residuals.

This is deliberately the simplest defensible univariate forecaster: it
makes no use of the cross-sectional structure the pipeline enforces, so
departmental forecasts do not add to the national one and rates are not
derived from levels. The output is marked ``EXPERIMENTAL`` in every row and
is written next to the delivery (``<delivery>_forecasts/``), never inside it.
"""

from __future__ import annotations

import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

from icml.delivery.builder import read_text_table
from icml.delivery.monthly_report import MONITORED
from icml.domain.cutoff import month_labels

FORECAST_SUFFIX = "_forecasts"
STATUS = "EXPERIMENTAL_UNIVARIATE_HOLT_WINTERS"


def _future_months(last: str, horizon: int) -> list[str]:
    year, month = int(last[:4]), int(last[5:7])
    out = []
    for _ in range(horizon):
        month += 1
        if month > 12:
            month, year = 1, year + 1
        out.append(f"{year}-{month:02d}")
    return out


def forecast_series(values: np.ndarray, horizon: int, fit_years: int = 10) -> dict | None:
    """Holt-Winters forecast of one series; ``None`` when there is not enough clean history."""
    from statsmodels.tsa.holtwinters import ExponentialSmoothing

    y = values[-(fit_years * 12):]
    if len(y) < 36 or not np.isfinite(y).all() or np.allclose(y, y[0]):
        return None
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        model = ExponentialSmoothing(y, trend="add", seasonal="add", seasonal_periods=12, damped_trend=True)
        fit = model.fit(optimized=True)
    point = np.asarray(fit.forecast(horizon), dtype=float)
    resid = np.asarray(fit.resid, dtype=float)
    resid = resid[np.isfinite(resid)]
    spread = 1.2816 * resid.std(ddof=1) * np.sqrt(np.arange(1, horizon + 1)) if len(resid) > 12 else np.full(horizon, np.nan)
    return {"point": point, "lower80": point - spread, "upper80": point + spread,
            "aic": float(fit.aic), "fit_months": int(len(y))}


def forecast_delivery(delivery: Path, horizon: int = 12, fit_years: int = 10, output: Path | None = None) -> dict:
    """Forecast every monitored series of ``delivery``; write CSV and a summary JSON."""
    delivery = Path(delivery)
    manifest = json.loads((delivery / "MANIFEST.json").read_text(encoding="utf-8"))
    output = Path(output) if output else delivery.parent / f"{delivery.name}{FORECAST_SUFFIX}"
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"{output} already exists")
    output.mkdir(parents=True, exist_ok=True)
    rows = []
    skipped = 0
    for product, universe, key, columns in MONITORED:
        frame = None
        for entry in manifest["outputs"]:
            if entry["source_product"] == product and entry["universe"] == universe:
                frame = read_text_table(delivery / entry["path"])
        if frame is None:
            continue
        for unit_id, group in frame.groupby(key, sort=True):
            g = group.sort_values("period")
            months = _future_months(str(g["period"].iloc[-1]), horizon)
            for column in columns:
                if column not in g:
                    continue
                values = pd.to_numeric(g[column], errors="coerce").to_numpy(float)
                result = forecast_series(values, horizon, fit_years)
                if result is None:
                    skipped += 1
                    continue
                is_rate = "rate" in column or "share" in column
                for i, month in enumerate(months):
                    point = result["point"][i]
                    lo, hi = result["lower80"][i], result["upper80"][i]
                    if is_rate:
                        point, lo, hi = (float(np.clip(x, 0, 1)) for x in (point, lo, hi))
                    else:
                        point, lo, hi = (float(max(x, 0.0)) for x in (point, lo, hi))
                    rows.append({"product": product, "universe": universe, "unit": str(unit_id), "variable": column,
                                 "period": month, "horizon": i + 1, "forecast": point, "lower80": lo, "upper80": hi,
                                 "fit_months": result["fit_months"], "status": STATUS})
    table = pd.DataFrame(rows)
    table.to_csv(output / "forecasts_EXPERIMENTAL.csv", index=False, lineterminator="\n")
    summary = {"run_id": manifest["run_id"], "cutoff": manifest["cutoff"], "horizon_months": horizon, "fit_years": fit_years,
               "series_forecast": int(table[["product", "unit", "variable"]].drop_duplicates().shape[0]) if len(table) else 0,
               "series_skipped": skipped, "status": STATUS, "method": "Holt-Winters additive damped trend, additive seasonality (statsmodels); 80 % interval from in-sample residuals",
               "not_claimed": "forecasts are univariate: departments do not add to the national, rates are not derived from levels"}
    (output / "FORECAST_SUMMARY.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary
