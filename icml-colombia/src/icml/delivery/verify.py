"""Audit a finished delivery: integrity, shapes and cross-universe identities.

The checks do not depend on how the split was coded; they re-derive
relations that must hold between the two universes in the real data
(complete = represented x factor, complete = represented + outside, the
sectoral totals equal the labor totals, ...). A wrong column assignment in
``spec`` therefore fails here even though the mechanical split is correct.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from icml.delivery.builder import COVERAGE_COLUMN, NOT_REPRESENTED, read_text_table, sha256_file
from icml.domain.cutoff import month_labels
from icml.delivery.spec import SPECS, UNIVERSES

#: Absolute tolerance, in persons, for identities between delivered files.
TOLERANCE_PERSONS = 1e-3
#: First month in which the GEIH national equals the sum of represented
#: departments (before it, the nine partially represented capitals are not
#: in the national total).
SUM_EQUALS_NATIONAL_FROM = "2014-01"


def coverage_report(frame: pd.DataFrame, *, level: str, months: list[str], sectors: int = 0) -> dict:
    """Check that a delivered table covers every territory and month.

    Parameters
    ----------
    frame : pandas.DataFrame
        The delivered table, read as text.
    level : str
        ``nacional``, ``ciudades`` or ``departamentos``.
    months : list[str]
        Every month the table must have (``1993-01`` up to the cutoff).
    sectors : int
        Number of sectors for sectoral tables, 0 otherwise.

    Returns
    -------
    dict
        Missing and duplicated keys, and empty cells. An empty cell is only
        legitimate where ``cobertura_geih`` says ``SIN_REPRESENTACION`` or ``PARCIAL``
        (partially-covered territories whose informality is not yet estimated).
    """
    territory = {"ciudades": "city_code", "departamentos": "dep_code"}.get(level)
    units = 33 if territory else 1
    keys = [c for c in (territory, "sector_code" if sectors else None, "period") if c]
    expected = units * len(months) * (sectors or 1)
    present = frame[keys].drop_duplicates()
    missing = expected - len(present)
    bad_months = sorted(set(frame["period"]) ^ set(months))
    units_found = frame[territory].nunique() if territory else 1
    blank = frame.eq("").any(axis=1)
    if COVERAGE_COLUMN in frame.columns:
        explained = frame[COVERAGE_COLUMN].isin((NOT_REPRESENTED, "PARCIAL"))
        unexplained = int((blank & ~explained).sum())
        explained_blank = int((blank & explained).sum())
    else:
        unexplained, explained_blank = int(blank.sum()), 0
    return {
        "rows": int(len(frame)),
        "expected_rows": expected,
        "territories": int(units_found),
        "missing_keys": int(max(missing, 0)),
        "duplicated_keys": int(frame.duplicated(keys).sum()),
        "months_not_matching": bad_months[:5],
        "blank_rows_explained_by_no_representation": explained_blank,
        "blank_rows_unexplained": unexplained,
        "complete": bool(
            len(frame) == expected and missing == 0 and not bad_months
            and units_found == units and unexplained == 0
            and not frame.duplicated(keys).any()
        ),
    }


def _load(folder: Path, manifest: dict, product: str, universe: str) -> pd.DataFrame:
    entry = next(
        e
        for e in manifest["outputs"]
        if e["source_product"] == product
        and e["universe"] == universe
        and e["path"].endswith(".csv")
    )
    return read_text_table(folder / entry["path"])


def _num(frame: pd.DataFrame, column: str) -> pd.Series:
    return pd.to_numeric(frame[column].replace("", np.nan))


def _check(name: str, value: float, tolerance: float, **extra: object) -> dict:
    return {
        "check": name,
        "max_abs_difference": float(value),
        "tolerance": tolerance,
        "passed": bool(value <= tolerance),
        **extra,
    }


def verify_delivery(folder: Path) -> dict:
    """Verify a delivery folder and return a report.

    Parameters
    ----------
    folder : Path
        Folder that contains ``MANIFEST.json``.

    Returns
    -------
    dict
        ``status`` is ``PASS`` only if every check passed.
    """
    folder = Path(folder)
    manifest = json.loads((folder / "MANIFEST.json").read_text("utf-8"))
    checks: list[dict] = []

    # 1. Integrity: every listed file exists and keeps its hash.
    bad = [
        e["path"]
        for e in manifest["outputs"]
        if not (folder / e["path"]).is_file()
        or sha256_file(folder / e["path"]) != e["sha256"]
    ]
    checks.append(
        {"check": "files_exist_and_hash_matches", "passed": not bad, "bad": bad}
    )

    # 2. Structure: every product exists in both universes.
    seen = {(e["source_product"], e["universe"]) for e in manifest["outputs"]}
    absent = sorted(
        f"{s.product_id}/{u}" for s in SPECS for u in UNIVERSES if (s.product_id, u) not in seen
    )
    checks.append(
        {"check": "every_product_in_both_universes", "passed": not absent, "absent": absent}
    )

    def both(product: str) -> tuple[pd.DataFrame, pd.DataFrame]:
        return (
            _load(folder, manifest, product, "censo"),
            _load(folder, manifest, product, "geih"),
        )

    # 3. Labor departments: complete x factor = represented; identities.
    census, geih = both("labor.departamentos")
    for quantity in ("employed", "unemployed", "inactive", "population"):
        diff = (_num(census, quantity) * _num(geih, f"factor_{quantity}") - _num(geih, quantity)).abs().max()
        checks.append(_check(f"labor_dept_{quantity}_complete_x_factor_equals_represented", diff, TOLERANCE_PERSONS))
    checks.append(
        _check(
            "labor_dept_geih_labor_force_equals_employed_plus_unemployed",
            (_num(geih, "employed") + _num(geih, "unemployed") - _num(geih, "labor_force")).abs().max(),
            TOLERANCE_PERSONS,
        )
    )

    # 4. Informality departments: complete = GEIH + outside GEIH.
    census_i, geih_i = both("informalidad.departamentos")
    for quantity in ("population", "working_age", "labor_force", "employed", "unemployed", "inactive", "informal"):
        diff = (
            _num(census_i, quantity)
            - _num(geih_i, quantity)
            - _num(census_i, f"outside_geih_{quantity}")
        ).abs().max()
        checks.append(_check(f"informality_dept_{quantity}_complete_equals_geih_plus_outside", diff, TOLERANCE_PERSONS))
    for label, frame in (("census", census_i), ("geih", geih_i)):
        rate = _num(frame, "informal") / _num(frame, "employed").where(_num(frame, "employed") != 0)
        diff = (rate - _num(frame, "informality_rate")).abs().max()
        checks.append(_check(f"informality_dept_{label}_rate_equals_informal_over_employed", diff, 1e-9))

    # 5. Sectors agree with labor in each universe.
    for universe, labor_frame, sector in (
        ("censo", census, both("sectorial.departamental")[0]),
        ("geih", geih, both("sectorial.departamental")[1]),
    ):
        total = _num(sector, "employed_sector").groupby([sector["period"], sector["dep_code"]]).sum()
        labor_employed = _num(labor_frame, "employed")
        labor_employed.index = pd.MultiIndex.from_arrays([labor_frame["period"], labor_frame["dep_code"]])
        aligned = labor_employed.reindex(total.index)
        checks.append(
            _check(f"sector_dept_total_equals_labor_employed_{universe}", (total - aligned).abs().max(), TOLERANCE_PERSONS)
        )

    # 6. National GEIH vs the sum of represented departments.
    national_geih = both("labor.nacionales")[1]
    gaps = pd.DataFrame(
        {
            q: _num(national_geih, f"gap_published_minus_sum_{q}").abs()
            for q in ("employed", "unemployed", "population")
        }
    )
    late = national_geih["period"] >= SUM_EQUALS_NATIONAL_FROM
    checks.append(
        _check(
            f"national_geih_equals_sum_of_represented_from_{SUM_EQUALS_NATIONAL_FROM}",
            gaps[late].max().max(),
            TOLERANCE_PERSONS,
        )
    )
    checks.append(
        {
            "check": "national_geih_gap_before_cutoff_informational",
            "max_abs_gap_persons": float(gaps[~late].max().max()),
            "passed": True,
            "note": "Informational: reconstruction and nine-capitals entry.",
        }
    )

    # 7. Coverage: every territory, every month, every sector, in both universes.
    months = month_labels(last=manifest["cutoff"])
    for entry in manifest["outputs"]:
        if not entry["path"].endswith(".csv"):
            continue
        sectors = 15 if entry["domain"] == "sectorial" else 0
        coverage = coverage_report(
            read_text_table(folder / entry["path"]), level=entry["level"], months=months, sectors=sectors
        )
        checks.append(
            {
                "check": f"coverage_{entry['universe']}_{entry['domain']}_{entry['level']}",
                "passed": coverage["complete"],
                **coverage,
            }
        )

    report = {
        "run_id": manifest["run_id"],
        "status": "PASS" if all(c["passed"] for c in checks) else "FAIL",
        "checks": checks,
    }
    (folder / "VERIFICACION.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return report
