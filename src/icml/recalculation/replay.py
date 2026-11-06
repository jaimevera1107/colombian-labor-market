"""Compare two published vintages of the labor products under the anchor policy."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

import pandas as pd

from icml.delivery.builder import read_text_table
from icml.recalculation.graft import assert_frozen_unchanged, graft_frozen_years
from icml.recalculation.policy import AnchorPolicy

#: Labor products and the columns that identify a row.
LABOR_KEYS: Mapping[str, Sequence[str]] = {
    "ciudades": ("period", "city_code"),
    "departamentos": ("period", "dep_code"),
    "nacionales": ("period", "national_type"),
}


def compare_labor_vintages(
    previous_dir: Path,
    current_dir: Path,
    policy: AnchorPolicy,
    *,
    tolerance: float = 1e-6,
) -> dict:
    """Measure what a naive recomputation changes and apply the graft.

    Parameters
    ----------
    previous_dir, current_dir : Path
        Folders that hold ``ciudades.csv``, ``departamentos.csv`` and
        ``nacionales.csv`` of the earlier and the later vintage.
    policy : AnchorPolicy
        Frozen years.
    tolerance : float
        Absolute tolerance for a cell to count as changed.

    Returns
    -------
    dict
        Per product: rows, how many frozen cells a recomputation would have
        changed (by year), and the graft result (always 0 frozen changes).
    """
    report: dict = {"frozen_through_year": policy.last_anchor_year, "products": {}}
    for name, keys in LABOR_KEYS.items():
        old = read_text_table(Path(previous_dir) / f"{name}.csv")
        new = read_text_table(Path(current_dir) / f"{name}.csv")
        grafted, graft = graft_frozen_years(old, new, policy, keys=keys, tolerance=tolerance)
        assert_frozen_unchanged(old, grafted, policy, keys=keys)
        merged = old.merge(new, on=list(keys), suffixes=("_prev", "_curr"))
        merged["year"] = merged["period"].str[:4].astype(int)
        frozen = merged[merged["year"] <= policy.last_anchor_year]
        by_year: dict[int, int] = {}
        for column in (c for c in old.columns if c not in keys):
            before = pd.to_numeric(frozen[f"{column}_prev"], errors="coerce")
            after = pd.to_numeric(frozen[f"{column}_curr"], errors="coerce")
            both = before.notna() & after.notna()
            changed = (before - after).abs() > tolerance
            hits = frozen.loc[both & changed, "year"].value_counts()
            for year, count in hits.items():
                by_year[int(year)] = by_year.get(int(year), 0) + int(count)
        report["products"][name] = {
            "rows_previous": int(len(old)),
            "rows_current": int(len(new)),
            "new_rows": int(len(new) - len(old)),
            "frozen_cells_a_naive_recomputation_would_change": int(sum(by_year.values())),
            "by_year": dict(sorted(by_year.items())),
            "frozen_rows_kept_from_previous": graft["rows_frozen_from_published"],
            "open_rows_taken_from_current": graft["rows_open_from_recomputation"],
            "frozen_cells_changed_after_graft": graft["frozen_cells_changed_in_output"],
        }
    return report


#: Identifying columns of the eight products, with ``period`` first.
PRODUCT_KEYS: Mapping[str, Sequence[str]] = {
    "labor.nacionales": ("period", "national_type"),
    "labor.departamentos": ("period", "dep_code"),
    "labor.ciudades": ("period", "city_code"),
    "informalidad.nacionales": ("period", "national_type"),
    "informalidad.departamentos": ("period", "dep_code"),
    "informalidad.ciudades": ("period", "city_code"),
    "sectorial.nacional": ("period", "sector_code"),
    "sectorial.departamental": ("period", "dep_code", "sector_code"),
}


def compare_products(
    previous: Mapping[str, Path],
    current: Mapping[str, Path],
    policy: AnchorPolicy,
    *,
    tolerance: float = 1e-6,
) -> dict:
    """Compare two vintages of the eight products under the anchor policy.

    Same measurements as ``compare_labor_vintages`` but for every product,
    reading each from its own path (``previous`` / ``current`` map a product
    id to its CSV).
    """
    report: dict = {"frozen_through_year": policy.last_anchor_year, "products": {}}
    for name, keys in PRODUCT_KEYS.items():
        old = read_text_table(Path(previous[name]))
        new = read_text_table(Path(current[name]))
        grafted, graft = graft_frozen_years(old, new, policy, keys=keys, tolerance=tolerance)
        assert_frozen_unchanged(old, grafted, policy, keys=keys)
        merged = old.merge(new, on=list(keys), suffixes=("_prev", "_curr"))
        merged["year"] = merged["period"].str[:4].astype(int)
        frozen = merged[merged["year"] <= policy.last_anchor_year]
        by_year: dict[int, int] = {}
        for column in (c for c in old.columns if c not in keys):
            before = pd.to_numeric(frozen[f"{column}_prev"], errors="coerce")
            after = pd.to_numeric(frozen[f"{column}_curr"], errors="coerce")
            both = before.notna() & after.notna()
            changed = (before - after).abs() > tolerance
            for year, count in frozen.loc[both & changed, "year"].value_counts().items():
                by_year[int(year)] = by_year.get(int(year), 0) + int(count)
        report["products"][name] = {
            "rows_previous": int(len(old)),
            "rows_current": int(len(new)),
            "new_rows": int(len(new) - len(old)),
            "frozen_cells_a_naive_recomputation_would_change": int(sum(by_year.values())),
            "by_year": dict(sorted(by_year.items())),
            "first_year_changed": min(by_year) if by_year else None,
            "frozen_rows_kept_from_previous": graft["rows_frozen_from_published"],
            "open_rows_taken_from_current": graft["rows_open_from_recomputation"],
            "frozen_cells_changed_after_graft": graft["frozen_cells_changed_in_output"],
        }
    return report
