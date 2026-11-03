"""Simple files: only the columns of each thing, no traceability.

They are cut from the full delivery, so both sets come from exactly the same
data and universes. Headers are short Spanish names (``Fecha``, ``Año``,
``Mes``, ``DPT``, ``Codigo``, ``Ocupados`` ...), with no audit or provenance columns.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pandas as pd

from icml.delivery.builder import _numbers, _ratio, _write_xlsx, read_text_table
from icml.domain.territories import load_territories

#: Columns kept as text in Excel (codes keep their leading zero).
TEXT = frozenset({"DPT", "CIUDAD", "Codigo", "Sector"})

#: Columns written as real dates in Excel.
DATES = frozenset({"Fecha"})

LABOR_COUNTS = (
    ("Ocupados", "employed"),
    ("Desocupados", "unemployed"),
    ("Inactivos", "inactive"),
    ("PEA", "labor_force"),
    ("PET", "working_age"),
    ("Poblacion", "population"),
)
LABOR_RATES = (
    ("TD", "unemployment_rate"),
    ("TO", "employment_rate"),
    ("TGP", "participation_rate"),
)
INFORMALITY = (
    ("Poblacion", "population"),
    ("PET", "working_age"),
    ("PEA", "labor_force"),
    ("Ocupados", "employed"),
    ("Desocupados", "unemployed"),
    ("Inactivos", "inactive"),
    ("Informales", "informal"),
    ("Formales", "formal"),
    ("TI", "informality_rate"),
)
INFORMALITY_CITIES = (
    ("Ocupados", "employed_frozen"),
    ("Informales", "informal_estimated"),
    ("Formales", "formal_estimated"),
    ("TI", "informality_rate"),
)
SECTOR_DEPARTMENTS = (("Sector", "sector_code"), ("Ocupados", "employed_sector"), ("Participacion", "sector_share"))
SECTOR_NATIONAL = (("Sector", "sector_code"), ("Ocupados", "occupied"), ("Participacion", "share"))


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
        "Fecha": period + "-01",  # first day of the month, ISO date
        "Año": period.str[:4],
        "Mes": period.str[5:7].astype(int).astype(str),
    }
    if level == "departamentos":
        codes = source["dep_code"].astype(str).str.zfill(2)
        names = _department_names()
        data["DPT"] = codes.map(names)
        data["Codigo"] = codes
    elif level == "ciudades":
        data["CIUDAD"] = source["city_name"]
        data["Codigo"] = source["city_code"].astype(str).str.zfill(2)
    if domain == "laboral":
        source = _with_rates(source)
        data |= _columns(source, LABOR_COUNTS + LABOR_RATES)
    elif domain == "informalidad":
        data |= _columns(source, INFORMALITY_CITIES if level == "ciudades" else INFORMALITY)
    elif domain == "sectorial":
        data |= _columns(source, SECTOR_DEPARTMENTS if level == "departamentos" else SECTOR_NATIONAL)
    else:
        raise ValueError(f"Unknown domain {domain!r}")
    frame = pd.DataFrame(data)
    if frame.get("DPT") is not None and frame["DPT"].isna().any():
        raise ValueError("A department code has no name in the territory catalog")
    order = [c for c in ("Codigo", "Sector", "Fecha") if c in frame.columns]
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
        Destination; defaults to ``<delivery>_sencillo`` beside it.
    excel : bool
        Also write ``.xlsx``. CSV files use UTF-8 with BOM, so Excel shows the
        accents; the workbooks keep codes as text and ``Fecha`` as a real date.

    Returns
    -------
    dict
        The files written with their row counts.
    """
    delivery = Path(delivery)
    manifest = json.loads((delivery / "MANIFEST.json").read_text("utf-8"))
    output = Path(output) if output else delivery.parent / f"{delivery.name}_sencillo"
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite {output}")
    stamp = manifest["run_id"][:17]
    written = []
    for entry in manifest["outputs"]:
        if not entry["path"].endswith(".csv"):
            continue
        frame = simple_frame(entry["domain"], entry["level"], read_text_table(delivery / entry["path"]))
        folder = output / f"universo_{entry['universe']}" / entry["domain"]
        folder.mkdir(parents=True, exist_ok=True)
        name = f"{entry['domain']}_{entry['level']}_{entry['universe']}_corte-{manifest['cutoff']}_{stamp}_sencillo"
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
