"""Compare two releases of the DANE GEIH annex on the figures the system uses.

The comparison goes through the **same readers the labor chain uses**
(``GeihAnnexReader`` and ``read_rolling_windows``), so what is compared is
exactly what enters the calculation. A figure of a frozen year that differs
between consecutive releases is a revision by the source and blocks an
anchored recalculation (see ``gates.check_frozen_observations``).
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pandas as pd

from icml.domain.cutoff import shift_label
from icml.integration.pipeline import load_integration_config
from icml.integration.windows import read_rolling_windows
from icml.national.geih_annex import GeihAnnexReader
from icml.national.pipeline import load_national_config
from icml.recalculation.gates import check_frozen_observations
from icml.recalculation.policy import AnchorPolicy


def national_observations(annex: Path, national_config: Path) -> pd.DataFrame:
    """Return the national monthly series as ``period, quantity, value``."""
    config = load_national_config(national_config)
    wide = GeihAnnexReader(config.geih_annex).read_national_monthly(annex)
    return wide.melt(id_vars="period", var_name="quantity", value_name="value")


def window_observations(
    annex: Path, integration_config: Path, n_windows: int
) -> pd.DataFrame:
    """Return the 32-city 12-month windows as ``period, region, quantity, value``.

    ``period`` is the month in which each window ends.
    """
    config = load_integration_config(integration_config)
    spec = replace(config.windows, n_windows=n_windows)
    windows = read_rolling_windows(annex, spec)
    rows = []
    for region, quantities in windows.items():
        for quantity, values in quantities.items():
            for offset, value in enumerate(values):
                rows.append(
                    {
                        "period": shift_label(spec.first_window_end, offset),
                        "region": region,
                        "quantity": quantity,
                        "value": float(value),
                    }
                )
    return pd.DataFrame(rows)


def _open_year_revisions(
    previous: pd.DataFrame,
    current: pd.DataFrame,
    policy: AnchorPolicy,
    keys: list[str],
    tolerance: float,
) -> int:
    """Count revised figures in the years that are still open (informative)."""
    pre = previous[~previous["period"].map(policy.is_frozen)]
    cur = current[~current["period"].map(policy.is_frozen)]
    merged = pre.merge(cur, on=keys, suffixes=("_prev", "_curr"))
    return int(((merged["value_prev"] - merged["value_curr"]).abs() > tolerance).sum())


def compare_annex_releases(
    previous: Path,
    current: Path,
    *,
    national_config: Path,
    integration_config: Path,
    previous_windows: int,
    current_windows: int,
    policy: AnchorPolicy,
    tolerance: float = 1e-6,
) -> dict:
    """Compare two annex releases on national months and city windows.

    Returns
    -------
    dict
        Per source: the frozen-years gate report and the number of revisions
        found in the open years. ``status`` is ``PASS`` only if no figure of
        a frozen year was revised or removed.
    """
    sources = {
        "national_monthly": (
            national_observations(previous, national_config),
            national_observations(current, national_config),
            ["period", "quantity"],
        ),
        "city_windows": (
            window_observations(previous, integration_config, previous_windows),
            window_observations(current, integration_config, current_windows),
            ["period", "region", "quantity"],
        ),
    }
    report: dict = {"frozen_through_year": policy.last_anchor_year, "sources": {}}
    for name, (old, new, keys) in sources.items():
        gate = check_frozen_observations(
            old, new, policy, keys=keys, value="value", tolerance=tolerance
        )
        gate["observations_compared"] = {"previous": int(len(old)), "current": int(len(new))}
        gate["open_year_revisions"] = _open_year_revisions(old, new, policy, keys, tolerance)
        report["sources"][name] = gate
    report["status"] = (
        "PASS"
        if all(g["status"] == "PASS" for g in report["sources"].values())
        else "BLOCKED"
    )
    return report


def informality_observations(annex: Path) -> pd.DataFrame:
    """Return the informality annex as ``period, domain, concept, measure, value``.

    Reads the rolling three-month windows of the 25 city blocks and the
    three national blocks (total, urban heads, rural) with the same
    extractor the informality models use. ``period`` is the month in which
    each window ends; values are in thousands of persons.
    """
    from icml.informality.extract_annexes import extract_new

    def matrix(sheet: str, rows: int) -> list[list[object]]:
        cells = pd.read_excel(annex, sheet_name=sheet, header=None, nrows=rows)
        return cells.astype(object).where(cells.notna(), None).values.tolist()

    data = extract_new(matrix("Ciudades", 120), matrix("Total nacional", 45))
    wide = data.assign(period=pd.to_datetime(data["period_end"]).dt.strftime("%Y-%m"))
    return wide.melt(
        id_vars=["period", "domain", "concept"],
        value_vars=["occupied_thousands", "formal_thousands", "informal_thousands"],
        var_name="measure",
        value_name="value",
    )


def compare_informality_releases(
    previous: Path,
    current: Path,
    policy: AnchorPolicy,
    *,
    tolerance: float = 1e-6,
) -> dict:
    """Compare two releases of the informality and social-security annex.

    The informality annex is the second source of the two-annex rule: a
    revised window that ends in a frozen year blocks an anchored update.
    """
    keys = ["period", "domain", "concept", "measure"]
    old = informality_observations(previous)
    new = informality_observations(current)
    gate = check_frozen_observations(
        old, new, policy, keys=keys, value="value", tolerance=tolerance
    )
    gate["observations_compared"] = {"previous": int(len(old)), "current": int(len(new))}
    gate["open_year_revisions"] = _open_year_revisions(old, new, policy, keys, tolerance)
    return gate
