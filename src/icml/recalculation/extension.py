"""Extend the frozen monthly parameters past the frozen cutoff.

Four parameter panels are frozen model artifacts that end at the frozen
cutoff and that a recompute requires for every month of its calendar. A
cutoff later than the frozen one therefore needs rows for the new months.
The rules below are deliberately simple and explicit; every extended row is
tagged so the products can show where a frozen parameter was carried
forward instead of estimated.

* ``EXTENDED_SEASONAL_PERSISTENCE``: the row of the same calendar month of
  the previous year (departmental informality priors, national sectoral
  composition). The level of the informality priors is irrelevant: they are
  calibrated to the national target of the new annex; what is carried
  forward is the departmental pattern. The sectoral composition is carried
  forward until the H10 monthly extraction of the new annex is wired in.
* ``EXTENDED_LAST_MONTH_PERSISTENCE``: the last frozen row (the census
  bridge). Its full levels are refreshed from the labor product at closure
  time, and the nine partial territories take the labor product's GEIH
  factors; the factors of the 24 fully covered territories are carried
  forward.

None of these rules re-estimates anything; the functions are pure and work
on data frames so the vintage root can apply them to the copied files.
"""

from __future__ import annotations

import pandas as pd

from typing import TYPE_CHECKING

from icml.domain.cutoff import month_labels

if TYPE_CHECKING:
    from pathlib import Path

SEASONAL = "EXTENDED_SEASONAL_PERSISTENCE"
PERSISTENCE = "EXTENDED_LAST_MONTH_PERSISTENCE"


def _months_after(last_frozen: str, cutoff: str) -> list[str]:
    labels = month_labels(last_frozen, cutoff)
    return labels[1:]


def _previous_year(month: str) -> str:
    return f"{int(month[:4]) - 1}{month[4:]}"


def _stamp(rows: pd.DataFrame, month: str, provenance: str | None, tag: str) -> pd.DataFrame:
    rows = rows.copy()
    rows["period"] = month
    if "year" in rows.columns:
        rows["year"] = type(rows["year"].iloc[0])(int(month[:4])) if len(rows) else rows["year"]
    if "month" in rows.columns:
        rows["month"] = type(rows["month"].iloc[0])(int(month[5:7])) if len(rows) else rows["month"]
    if provenance:
        rows[provenance] = tag
    return rows


def extend_seasonal(frame: pd.DataFrame, last_frozen: str, cutoff: str,
                    provenance: str | None = None) -> tuple[pd.DataFrame, int]:
    """Append, for every month after ``last_frozen`` through ``cutoff``, the rows of the same month one year earlier.

    Returns the extended frame and the number of rows added. Raises when a
    source month is missing or has no rows, so a gap is never filled by
    accident.
    """
    if "period" not in frame.columns:
        raise ValueError("The panel has no 'period' column")
    present = set(frame["period"].astype(str))
    added = []
    for month in _months_after(last_frozen, cutoff):
        source = _previous_year(month)
        rows = frame[frame["period"].astype(str) == source]
        if rows.empty:
            raise ValueError(f"Cannot extend to {month}: no rows for {source}")
        if month in present:
            raise ValueError(f"{month} is already present; refusing to duplicate it")
        added.append(_stamp(rows, month, provenance, SEASONAL))
    if not added:
        return frame, 0
    out = pd.concat([frame, *added], ignore_index=True)
    return out, sum(len(a) for a in added)


def extend_persistence(frame: pd.DataFrame, last_frozen: str, cutoff: str,
                       provenance: str | None = None) -> tuple[pd.DataFrame, int]:
    """Append, for every month after ``last_frozen`` through ``cutoff``, a copy of the ``last_frozen`` rows."""
    if "period" not in frame.columns:
        raise ValueError("The panel has no 'period' column")
    last = frame[frame["period"].astype(str) == last_frozen]
    if last.empty:
        raise ValueError(f"No rows for the last frozen month {last_frozen}")
    present = set(frame["period"].astype(str))
    added = []
    for month in _months_after(last_frozen, cutoff):
        if month in present:
            raise ValueError(f"{month} is already present; refusing to duplicate it")
        added.append(_stamp(last, month, provenance, PERSISTENCE))
    if not added:
        return frame, 0
    return pd.concat([frame, *added], ignore_index=True), sum(len(a) for a in added)


#: Which rule each frozen panel gets, relative to ``datos/2_procesamiento``.
#: (rule, provenance column that receives the tag, or None when the file
#: has no free-text status column to carry it).
EXTENSION_RULES: dict[str, tuple[str, str | None]] = {
    "parametros_congelados/priors_mlp_h9/12_single_mlp_33_department_priors.csv": ("seasonal", "extension_status"),
    "parametros_congelados/puente_censal_cnpv2018/02_puente_dos_universos_33_territorios.csv": ("persistence", "factor_reference_status"),
    "sectorial_h16/inputs/12_composicion_nacional_unificada_1993_2026.csv": ("annex_or_seasonal", "source_status"),
}

ANNEX_EXTENDED = "DANE_13_PUBLISHED_PLUS_NO_INFO_REMAINDER_EXTENDED"


def extend_composition_from_annex(frame: pd.DataFrame, last_frozen: str, cutoff: str,
                                  workbooks: dict[str, "Path"]) -> tuple[pd.DataFrame, int, dict[str, str]]:
    """Extend the national sectoral composition from the labor annexes of the new months.

    ``workbooks`` maps each new month to the DANE labor annex that contains
    it (the annex of month M publishes every month from 2015-01 through M,
    so the latest annex normally covers all of them). Months the annexes do
    not publish fall back to seasonal persistence. Returns the frame, the
    rows added and, per month, which rule produced it.
    """
    from icml.sectoral.monthly import extract_monthly_composition

    base = frame[frame["period"].astype(str) == "2015-03"].set_index("sector_code")["sector_share"].astype(float)
    ratio = float(base["B"] / (base["B"] + base["D_E"]))
    rules: dict[str, str] = {}
    out = frame
    added = 0
    for month in _months_after(last_frozen, cutoff):
        workbook = workbooks.get(month)
        rows = None
        if workbook is not None:
            try:
                rows = extract_monthly_composition(workbook, [month], ratio)
            except ValueError:
                rows = None
        if rows:
            new = pd.DataFrame(rows)
            for column in out.columns:
                if column not in new:
                    new[column] = ""
            out = pd.concat([out, new[list(out.columns)].astype(str)], ignore_index=True)
            added += len(new)
            rules[month] = "annex"
        else:
            out, n = extend_seasonal(out, _previous_month(month), month, "source_status")
            added += n
            rules[month] = "seasonal"
    return out, added, rules


def _previous_month(month: str) -> str:
    year, m = int(month[:4]), int(month[5:7]) - 1
    if m == 0:
        year, m = year - 1, 12
    return f"{year}-{m:02d}"


def extend_panel(frame: pd.DataFrame, rule: str, last_frozen: str, cutoff: str,
                 provenance: str | None, workbooks: dict[str, "Path"] | None = None) -> tuple[pd.DataFrame, int]:
    """Dispatch on the rule name (``annex_or_seasonal`` needs ``workbooks``)."""
    if rule == "annex_or_seasonal":
        out, added, _ = extend_composition_from_annex(frame, last_frozen, cutoff, workbooks or {})
        return out, added
    if rule == "seasonal":
        return extend_seasonal(frame, last_frozen, cutoff, provenance)
    if rule == "persistence":
        return extend_persistence(frame, last_frozen, cutoff, provenance)
    raise ValueError(f"Unknown extension rule {rule!r}")
