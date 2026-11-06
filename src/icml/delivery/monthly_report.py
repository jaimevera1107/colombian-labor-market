"""Statistical diagnostics of the newest month of a delivery.

The delivery audit (``verify.py``) checks identities, hashes and coverage. This
module asks a different question: *does the new month look like the series
it extends?* For every monitored series it reports

* the month-over-month change and its z-score against the distribution of
  MoM changes of the previous ten years (a |z| above 3 is flagged);
* the year-over-year change;
* the seasonal-naive residual: the new value minus the same month of the
  previous year adjusted by the last twelve-month drift, as a crude
  out-of-sample check that needs no model;
* where a previous delivery is available, the revisions: how many cells of
  the open years changed and by how much.

Nothing here blocks a run. The report is evidence for the person who
publishes, written next to the delivery as ``MONTHLY_REPORT.json`` and
``MONTHLY_REPORT.md``.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from icml.delivery.builder import read_text_table

#: (product, universe, group column, monitored columns). Rates are compared in
#: percentage points, levels in percent.
MONITORED = (
    ("labor.nacionales", "census", "national_type", ("employed", "unemployed", "labor_force", "unemployment_rate", "employment_rate", "participation_rate")),
    ("labor.departamentos", "census", "dep_code", ("employed", "unemployed", "unemployment_rate", "participation_rate")),
    ("informalidad.nacionales", "census", "national_type", ("informality_rate",)),
    ("informalidad.departamentos", "census", "dep_code", ("informality_rate",)),
)
RATE_HINT = ("rate", "share")
Z_FLAG = 3.0
HISTORY_YEARS = 10


def _load(delivery: Path, manifest: dict, product: str, universe: str) -> pd.DataFrame | None:
    for entry in manifest["outputs"]:
        if entry["source_product"] == product and entry["universe"] == universe:
            frame = read_text_table(delivery / entry["path"])
            return frame
    return None


def _numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def _series_diagnostics(group: pd.DataFrame, column: str) -> dict | None:
    g = group.sort_values("period")
    values = _numeric(g[column]).to_numpy(float)
    periods = g["period"].to_numpy(str)
    if len(values) < 24 or not np.isfinite(values[-1]):
        return None
    is_rate = any(h in column for h in RATE_HINT)
    scale = 100.0 if is_rate else 1.0
    unit = "pp" if is_rate else "%"
    last, prev = values[-1], values[-2]
    mom = (last - prev) * scale if is_rate else (last / prev - 1) * 100 if prev else np.nan
    history = values[-(HISTORY_YEARS * 12 + 1):]
    moms = (np.diff(history) * scale) if is_rate else (history[1:] / history[:-1] - 1) * 100
    moms = moms[np.isfinite(moms)][:-1]
    z = (mom - moms.mean()) / moms.std(ddof=1) if len(moms) > 12 and moms.std(ddof=1) > 0 else np.nan
    yoy = np.nan
    seasonal_residual = np.nan
    if len(values) >= 13 and np.isfinite(values[-13]):
        yoy = (last - values[-13]) * scale if is_rate else (last / values[-13] - 1) * 100 if values[-13] else np.nan
        # Seasonal naive with drift: same month last year plus the mean 12-month change of the last two years.
        if len(values) >= 37:
            drift = np.nanmean(values[-13:-1] - values[-25:-13])
            seasonal_residual = (last - (values[-13] + drift)) * scale if is_rate else (last / (values[-13] + drift) - 1) * 100
    return {
        "period": str(periods[-1]), "value": float(last), "measure_unit": unit,
        "mom_change": None if not np.isfinite(mom) else float(mom),
        "mom_zscore": None if not np.isfinite(z) else float(z),
        "yoy_change": None if not np.isfinite(yoy) else float(yoy),
        "seasonal_naive_residual": None if not np.isfinite(seasonal_residual) else float(seasonal_residual),
        "flag": bool(np.isfinite(z) and abs(z) > Z_FLAG),
    }


def _revisions(current: pd.DataFrame, previous: pd.DataFrame, key: str, columns: tuple[str, ...], frozen_through: int | None) -> dict:
    merged = current.merge(previous, on=["period", key], suffixes=("", "_prev"), how="inner")
    if frozen_through is not None:
        merged = merged[merged["period"].str[:4].astype(int) > frozen_through]
    out = {}
    for column in columns:
        if f"{column}_prev" not in merged:
            continue
        a, b = _numeric(merged[column]), _numeric(merged[f"{column}_prev"])
        diff = (a - b).abs()
        is_rate = any(h in column for h in RATE_HINT)
        rel = diff * 100 if is_rate else (diff / b.abs().replace(0, np.nan)) * 100
        changed = (rel > 1e-6) if is_rate else (rel > 1e-6)
        out[column] = {"cells_compared": int(len(merged)), "cells_changed": int(changed.fillna(False).sum()),
                       "max_change": None if rel.dropna().empty else float(rel.max()), "unit": "pp" if is_rate else "%"}
    return out


def monthly_report(delivery: Path, previous: Path | None = None, frozen_through: int | None = None) -> dict:
    """Build the diagnostics of ``delivery`` (optionally against ``previous``) and write them next to it."""
    delivery = Path(delivery)
    manifest = json.loads((delivery / "MANIFEST.json").read_text(encoding="utf-8"))
    prev_manifest = json.loads((previous / "MANIFEST.json").read_text(encoding="utf-8")) if previous else None
    report: dict = {"run_id": manifest["run_id"], "cutoff": manifest["cutoff"], "series": [], "revisions": {},
                    "flags": 0, "zscore_flag_threshold": Z_FLAG, "history_years": HISTORY_YEARS,
                    "previous_run_id": prev_manifest["run_id"] if prev_manifest else None}
    for product, universe, key, columns in MONITORED:
        frame = _load(delivery, manifest, product, universe)
        if frame is None:
            continue
        for unit_id, group in frame.groupby(key, sort=True):
            for column in columns:
                if column not in group:
                    continue
                diag = _series_diagnostics(group, column)
                if diag is None:
                    continue
                report["series"].append({"product": product, "unit": str(unit_id), "variable": column, **diag})
                report["flags"] += int(diag["flag"])
        if prev_manifest is not None:
            prev = _load(previous, prev_manifest, product, universe)
            if prev is not None:
                report["revisions"][product] = _revisions(frame, prev, key, columns, frozen_through)
    (delivery / "MONTHLY_REPORT.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (delivery / "MONTHLY_REPORT.md").write_text(render_markdown(report), encoding="utf-8")
    return report


def _num(value, digits: int = 2, suffix: str = "") -> str:
    return "" if value is None else f"{value:+.{digits}f}{suffix}"


def render_markdown(report: dict) -> str:
    """A short, readable version of the report."""
    lines = [f"# Monthly diagnostics — {report['run_id']} (cutoff {report['cutoff']})", ""]
    flagged = [s for s in report["series"] if s["flag"]]
    lines.append(f"Series monitored: {len(report['series'])}. Month-over-month changes beyond |z| > {report['zscore_flag_threshold']} "
                 f"(against the last {report['history_years']} years): **{len(flagged)}**. These are not errors; they are where to look first.")
    lines.append("")
    if flagged:
        lines += ["| Product | Unit | Variable | Value | MoM | z | YoY | Seasonal-naive residual |", "|---|---|---|---:|---:|---:|---:|---:|"]
        for s in sorted(flagged, key=lambda x: -abs(x["mom_zscore"] or 0)):
            lines.append("| " + " | ".join([s["product"], s["unit"], s["variable"], f"{s['value']:.4g}",
                                            _num(s["mom_change"], 2, " " + s["measure_unit"]), _num(s["mom_zscore"], 1),
                                            _num(s["yoy_change"]), _num(s["seasonal_naive_residual"])]) + " |")
        lines.append("")
    nat = [s for s in report["series"] if s["product"] == "labor.nacionales" and s["unit"] == "ICML_COMPLETO"]
    if nat:
        lines += ["## National (ICML, census universe)", "", "| Variable | Value | MoM | YoY | Seasonal-naive residual |", "|---|---:|---:|---:|---:|"]
        for s in nat:
            lines.append("| " + " | ".join([s["variable"], f"{s['value']:.6g}", _num(s["mom_change"], 2, " " + s["measure_unit"]),
                                            _num(s["yoy_change"]), _num(s["seasonal_naive_residual"])]) + " |")
        lines.append("")
    if report["revisions"]:
        lines += [f"## Revisions against {report['previous_run_id']} (open years)", "", "| Product | Variable | Cells changed | Max change |", "|---|---|---:|---:|"]
        for product, columns in report["revisions"].items():
            for column, r in columns.items():
                change = "" if r["max_change"] is None else f"{r['max_change']:.3g} {r['unit']}"
                lines.append(f"| {product} | {column} | {r['cells_changed']} / {r['cells_compared']} | {change} |")
        lines.append("")
    return "\n".join(lines)
