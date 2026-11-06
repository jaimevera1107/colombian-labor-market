"""Simple files: only the columns of each thing, no traceability.

They are cut from the full delivery, so both sets come from exactly the same
data and universes. Headers are short names (``Date``, ``Year``, ``Month``,
``Department``, ``Code``, ``Employed`` ...), with no audit or provenance columns.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pandas as pd

from icml.delivery.builder import _numbers, _ratio, _write_xlsx, read_text_table
from icml.domain.territories import load_territories

#: Columns kept as text in Excel (codes keep their leading zero).
TEXT = frozenset({"Department", "City", "Code", "Sector"})

#: Columns written as real dates in Excel.
DATES = frozenset({"Date"})

LABOR_COUNTS = (
    ("Employed", "employed"),
    ("Unemployed", "unemployed"),
    ("Inactive", "inactive"),
    ("LaborForce", "labor_force"),
    ("WorkingAge", "working_age"),
    ("Population", "population"),
)
LABOR_RATES = (
    ("UnemploymentRate", "unemployment_rate"),
    ("EmploymentRate", "employment_rate"),
    ("ParticipationRate", "participation_rate"),
)
INFORMALITY = (
    ("Population", "population"),
    ("WorkingAge", "working_age"),
    ("LaborForce", "labor_force"),
    ("Employed", "employed"),
    ("Unemployed", "unemployed"),
    ("Inactive", "inactive"),
    ("Informal", "informal"),
    ("Formal", "formal"),
    ("InformalityRate", "informality_rate"),
)
INFORMALITY_CITIES = (
    ("Employed", "employed_frozen"),
    ("Informal", "informal_estimated"),
    ("Formal", "formal_estimated"),
    ("InformalityRate", "informality_rate"),
)
SECTOR_DEPARTMENTS = (("Sector", "sector_code"), ("Employed", "employed_sector"), ("Share", "sector_share"))
SECTOR_NATIONAL = (("Sector", "sector_code"), ("Employed", "occupied"), ("Share", "share"))


def _department_names() -> dict[str, str]:
    return {f"{t.dane_code:02d}": t.name for t in load_territories()}


def _with_rates(frame: pd.DataFrame) -> pd.DataFrame:
    """Add the rates a labor table lacks, with the same identities as the rest."""
    out = frame.copy()
    labor_force = _numbers(out["labor_force"])
    working_age = _numbers(out["working_age"])
    if "unemployment_rate" not in out.columns:
        out["unemployment_rate"] = _ratio(_numbers(out["unemployed"]), labor_force)
        out["employment_rate"] = _ratio(_numbers(out["employed"]), working_age)
        out["participation_rate"] = _ratio(labor_force, working_age)
    return out


def _columns(source: pd.DataFrame, pairs: tuple[tuple[str, str], ...]) -> dict[str, pd.Series]:
    return {new: source[old] for new, old in pairs}


def simple_frame(domain: str, level: str, source: pd.DataFrame) -> pd.DataFrame:
    """Project a full delivered table onto its simple columns.

    Parameters
    ----------
    domain : str
        ``laboral``, ``informalidad`` or ``sectorial``.
    level : str
        ``nacional``, ``ciudades`` or ``departamentos``.
    source : pandas.DataFrame
        The delivered table, read as text.
    """
    period = source["period"]
    data: dict[str, pd.Series] = {
        "Date": period + "-01",  # first day of the month, ISO date
        "Year": period.str[:4],
        "Month": period.str[5:7].astype(int).astype(str),
    }
    if level == "departments":
        codes = source["dep_code"].astype(str).str.zfill(2)
        names = _department_names()
        data["Department"] = codes.map(names)
        data["Code"] = codes
    elif level == "cities":
        data["City"] = source["city_name"]
        data["Code"] = source["city_code"].astype(str).str.zfill(2)
    if domain == "labor":
        source = _with_rates(source)
        data |= _columns(source, LABOR_COUNTS + LABOR_RATES)
    elif domain == "informality":
        data |= _columns(source, INFORMALITY_CITIES if level == "cities" else INFORMALITY)
    elif domain == "sectoral":
        data |= _columns(source, SECTOR_DEPARTMENTS if level == "departments" else SECTOR_NATIONAL)
    else:
        raise ValueError(f"Unknown domain {domain!r}")
    frame = pd.DataFrame(data)
    if frame.get("Department") is not None and frame["Department"].isna().any():
        raise ValueError("A department code has no name in the territory catalog")
    order = [c for c in ("Code", "Sector", "Date") if c in frame.columns]
    return frame.sort_values(order, kind="stable").reset_index(drop=True)


def build_simple(
    delivery: Path,
    output: Path | None = None,
    *,
    excel: bool = True,
    writer: Callable[[pd.DataFrame, Path], None] | None = None,
) -> dict:
    """Write the simple files of a delivery next to it.

    Parameters
    ----------
    delivery : Path
        A delivery folder (the one that holds ``MANIFEST.json``).
    output : Path, optional
        Destination; defaults to ``<delivery>_simple`` beside it.
    excel : bool
        Also write ``.xlsx``. CSV files use UTF-8 with BOM, so Excel shows the
        accents; the workbooks keep codes as text and ``Date`` as a real date.

    Returns
    -------
    dict
        The files written with their row counts.
    """
    delivery = Path(delivery)
    manifest = json.loads((delivery / "MANIFEST.json").read_text("utf-8"))
    output = Path(output) if output else delivery.parent / f"{delivery.name}_simple"
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite {output}")
    stamp = manifest["run_id"][:17]
    written = []
    for entry in manifest["outputs"]:
        if not entry["path"].endswith(".csv"):
            continue
        frame = simple_frame(entry["domain"], entry["level"], read_text_table(delivery / entry["path"]))
        folder = output / f"universe_{entry['universe']}" / entry["domain"]
        folder.mkdir(parents=True, exist_ok=True)
        name = f"{entry['domain']}_{entry['level']}_{entry['universe']}_cutoff-{manifest['cutoff']}_{stamp}_simple"
        frame.to_csv(folder / f"{name}.csv", index=False, lineterminator="\n", encoding="utf-8-sig")
        files = [folder / f"{name}.csv"]
        if excel:
            (writer or (lambda f, p: _write_xlsx(f, p, text_columns=TEXT, date_columns=DATES)))(frame, folder / f"{name}.xlsx")
            files.append(folder / f"{name}.xlsx")
        written.append(
            {
                "files": [f.relative_to(output).as_posix() for f in files],
                "rows": int(len(frame)),
                "columns": list(frame.columns),
                "universe": entry["universe"],
                "domain": entry["domain"],
                "level": entry["level"],
            }
        )
    return {"folder": str(output), "files": written}
