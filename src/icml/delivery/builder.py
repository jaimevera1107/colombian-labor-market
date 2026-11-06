"""Build the two-universe deliverables and their manifest.

Every internal product is read **as text** and written back as text, so
copied columns are identical character by character (no float round trip).
Only the derived columns declared in ``spec`` are computed, and they are
listed in the manifest.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from icml.delivery.spec import (
    SPECS,
    TEXT_COLUMNS,
    UNIVERSES,
    ProductSpec,
)

#: Colombia has no daylight saving time, so the offset is constant (-05:00).
TIMEZONE = ZoneInfo("America/Bogota")
MODES: frozenset[str] = frozenset(
    {"entrega", "anclado", "total", "verificacion"}
)
_REPRESENTED_QUANTITIES = (
    "employed",
    "unemployed",
    "inactive",
    "labor_force",
    "working_age",
    "population",
)


def run_stamp(now: datetime | None = None) -> str:
    """Return ``AAAA-MM-DD_HHMMSS`` in Bogota time for a run folder."""
    moment = (now or datetime.now(TIMEZONE)).astimezone(TIMEZONE)
    return moment.strftime("%Y-%m-%d_%H%M%S")


def sha256_file(path: Path) -> str:
    """Return the SHA-256 of a file."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_text_table(path: Path) -> pd.DataFrame:
    """Read a CSV keeping every cell as the exact text it has on disk."""
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def _numbers(series: pd.Series) -> pd.Series:
    """Parse a text column to floats; empty cells become NaN."""
    return pd.to_numeric(series.replace("", np.nan), errors="raise")


def _format(values: pd.Series) -> pd.Series:
    """Format floats with their shortest exact representation."""
    return values.map(lambda v: "" if pd.isna(v) else repr(float(v)))


def _ratio(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    """Divide, leaving empty where the denominator is zero or missing."""
    safe = denominator.where(denominator != 0)
    return _format(numerator / safe)


# ---------------------------------------------------------------- splitting


def _split_rows(spec: ProductSpec, frame: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Split by the value of ``spec.row_column``."""
    if spec.row_column not in frame.columns:
        raise ValueError(f"{spec.product_id}: missing {spec.row_column!r}")
    found = set(frame[spec.row_column])
    expected = set(spec.row_values.values())
    if found != expected:
        raise ValueError(
            f"{spec.product_id}: {spec.row_column} values {sorted(found)} "
            f"differ from the specification {sorted(expected)}"
        )
    return {
        universe: frame[frame[spec.row_column] == value].reset_index(drop=True)
        for universe, value in spec.row_values.items()
    }


def _split_columns(spec: ProductSpec, frame: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Split by column groups, renaming to a common schema."""
    assigned = spec.assigned_columns()
    if len(assigned) != len(set(assigned)):
        raise ValueError(f"{spec.product_id}: a column is assigned twice")
    missing = sorted(set(assigned) - set(frame.columns))
    extra = sorted(set(frame.columns) - set(assigned))
    if missing or extra:
        raise ValueError(
            f"{spec.product_id}: columns changed (missing={missing}, "
            f"unassigned={extra}); update icml.delivery.spec"
        )
    out: dict[str, pd.DataFrame] = {}
    for universe, mapping in (("censo", spec.census), ("geih", spec.geih)):
        part = frame[[*spec.keys, *mapping, *spec.both]].copy()
        part.columns = [*spec.keys, *mapping.values(), *spec.both]
        out[universe] = part
    return out


def _split(
    spec: ProductSpec, frame: pd.DataFrame, *, check_shapes: bool
) -> dict[str, pd.DataFrame]:
    if check_shapes and len(frame) != spec.expected_rows:
        raise ValueError(
            f"{spec.product_id}: {len(frame)} rows, expected {spec.expected_rows}"
        )
    if spec.split == "rows":
        return _split_rows(spec, frame)
    if spec.split == "columns":
        return _split_columns(spec, frame)
    return {universe: frame.copy() for universe in UNIVERSES}


# ----------------------------------------------------------------- derived


def _derive_labor_department_rates(
    geih: pd.DataFrame,
) -> tuple[pd.DataFrame, list[str]]:
    """Add unemployment, employment and participation rates (GEIH)."""
    employed = _numbers(geih["employed"])
    unemployed = _numbers(geih["unemployed"])
    labor_force = _numbers(geih["labor_force"])
    working_age = _numbers(geih["working_age"])
    geih["unemployment_rate"] = _ratio(unemployed, labor_force)
    geih["employment_rate"] = _ratio(employed, working_age)
    geih["participation_rate"] = _ratio(labor_force, working_age)
    return geih, ["unemployment_rate", "employment_rate", "participation_rate"]


def _derive_sector_share(geih: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Add the GEIH sector share within each department and month."""
    value = _numbers(geih["employed_sector"])
    total = value.groupby(
        [geih["period"], geih["dep_code"]], sort=False
    ).transform("sum")
    geih["sector_share"] = _ratio(value, total)
    return geih, ["sector_share"]


def _represented_sum_columns(
    national_geih: pd.DataFrame, departments: pd.DataFrame
) -> tuple[pd.DataFrame, list[str]]:
    """Compare the published national with the sum of represented departments."""
    represented = {
        quantity: _numbers(departments[f"{quantity}_represented"])
        for quantity in _REPRESENTED_QUANTITIES
    }
    sums = pd.DataFrame(represented).groupby(
        departments["period"], sort=False
    ).sum()
    added: list[str] = []
    periods = national_geih["period"]
    for quantity in _REPRESENTED_QUANTITIES:
        total = periods.map(sums[quantity])
        published = _numbers(national_geih[quantity])
        national_geih[f"represented_sum_{quantity}"] = _format(total)
        national_geih[f"gap_published_minus_sum_{quantity}"] = _format(
            published - total
        )
        added += [
            f"represented_sum_{quantity}",
            f"gap_published_minus_sum_{quantity}",
        ]
    return national_geih, added


# ---------------------------------------------------------------- coverage

#: Departmental products whose GEIH universe carries the coverage state.
_COVERAGE_PRODUCTS = ("labor.departamentos", "informalidad.departamentos", "sectorial.departamental")
COVERAGE_COLUMN = "cobertura_geih"
NOT_REPRESENTED = "SIN_REPRESENTACION"


def _geih_coverage(departments: pd.DataFrame) -> dict[tuple[str, str], str]:
    """State of the GEIH universe for each department and month.

    ``COMPLETA`` when the GEIH represents the whole territory (factor 1),
    ``PARCIAL`` when it represents part of it, and ``SIN_REPRESENTACION``
    when it represents nobody (population 0): rates and shares are undefined
    there, so they stay empty instead of pretending to be zero.
    """
    population = _numbers(departments["population_represented"])
    factor = _numbers(departments["factor_population"])
    state = np.where(population <= 0, NOT_REPRESENTED, np.where(factor < 1 - 1e-9, "PARCIAL", "COMPLETA"))
    codes = departments["dep_code"].astype(str).str.zfill(2)
    return dict(zip(zip(departments["period"], codes), state, strict=True))


def _with_coverage(part: pd.DataFrame, states: dict[tuple[str, str], str]) -> pd.DataFrame:
    codes = part["dep_code"].astype(str).str.zfill(2)
    part[COVERAGE_COLUMN] = [states[(p, c)] for p, c in zip(part["period"], codes, strict=True)]
    return part


# ------------------------------------------------------------------ output


def _is_numeric_column(column: pd.Series) -> bool:
    filled = column[column != ""]
    if filled.empty:
        return False
    return bool(pd.to_numeric(filled, errors="coerce").notna().all())


def _write_xlsx(
    frame: pd.DataFrame,
    path: Path,
    text_columns: frozenset[str] = TEXT_COLUMNS,
    date_columns: frozenset[str] = frozenset(),
) -> None:
    """Write a frame to Excel: numbers numeric, codes as text, dates as dates."""
    from datetime import date

    from openpyxl import Workbook
    from openpyxl.cell import WriteOnlyCell

    numeric = [
        column
        for column in frame.columns
        if column not in text_columns
        and column not in date_columns
        and _is_numeric_column(frame[column])
    ]
    workbook = Workbook(write_only=True)
    sheet = workbook.create_sheet("datos")
    sheet.append(list(frame.columns))
    flags = [column in numeric for column in frame.columns]
    is_date = [column in date_columns for column in frame.columns]

    def date_cell(text: str) -> object:
        cell = WriteOnlyCell(sheet, value=date.fromisoformat(text))
        cell.number_format = "yyyy-mm-dd"
        return cell

    for row in frame.itertuples(index=False, name=None):
        sheet.append(
            [
                date_cell(cell) if as_date and cell != ""
                else (float(cell) if cell != "" else None) if is_num else cell
                for cell, is_num, as_date in zip(row, flags, is_date, strict=True)
            ]
        )
    workbook.save(path)


def _file_name(spec: ProductSpec, universe: str, cutoff: str, stamp: str) -> str:
    return (
        f"{spec.domain}_{spec.level}_{universe}_corte-{cutoff}_{stamp}"
    )


def build_delivery(
    products: Mapping[str, Path],
    output_root: Path,
    *,
    cutoff: str,
    mode: str,
    now: datetime | None = None,
    software_version: str = "",
    excel: bool = False,
    check_shapes: bool = True,
    fingerprints: Mapping[str, Mapping[str, str]] | None = None,
    inputs_note: Mapping[str, str] | None = None,
) -> dict:
    """Write the two-universe deliverable into a new timestamped folder.

    Parameters
    ----------
    products : Mapping[str, Path]
        Internal product id (``labor.departamentos``...) to its CSV.
    output_root : Path
        Folder that holds every delivery; a new subfolder is created.
    cutoff : str
        Last month of the vintage, ``YYYY-MM``.
    mode : str
        One of ``MODES``; recorded in the folder name and the manifest.
    now : datetime, optional
        Clock override (tests). Defaults to the current Bogota time.
    software_version : str
        Version of the engine that produced the products.
    excel : bool
        Also write an ``.xlsx`` next to each CSV.
    check_shapes : bool
        Require the row counts of the frozen vintage. Disable only in tests.
    fingerprints : Mapping[str, Mapping[str, str]], optional
        ``{group: {path: sha256}}`` of the ingestion workbooks and frozen
        parameters; the next recalculation compares against them.
    inputs_note : Mapping[str, str], optional
        Extra provenance recorded in the manifest (for example the run id).

    Returns
    -------
    dict
        The manifest that was written to ``MANIFEST.json``.

    Raises
    ------
    FileExistsError
        If the folder for this second already exists (never overwrites).
    ValueError
        If a product is missing, has changed columns or has unexpected rows.
    """
    if mode not in MODES:
        raise ValueError(f"mode must be one of {sorted(MODES)}, got {mode!r}")
    missing = sorted({s.product_id for s in SPECS} - set(products))
    if missing:
        raise ValueError(f"Missing products: {missing}")
    moment = (now or datetime.now(TIMEZONE)).astimezone(TIMEZONE)
    stamp = run_stamp(moment)
    run_id = f"{stamp}_corte-{cutoff}_{mode}"
    folder = Path(output_root) / run_id
    if folder.exists():
        raise FileExistsError(f"Refusing to overwrite {folder}")

    frames = {s.product_id: read_text_table(Path(products[s.product_id])) for s in SPECS}
    derived: dict[tuple[str, str], Callable[[pd.DataFrame], tuple[pd.DataFrame, list[str]]]] = {
        ("labor.departamentos", "geih"): _derive_labor_department_rates,
        ("sectorial.departamental", "geih"): _derive_sector_share,
    }

    coverage_states = _geih_coverage(frames["labor.departamentos"])
    outputs: list[dict] = []
    folder.mkdir(parents=True)
    for spec in SPECS:
        parts = _split(spec, frames[spec.product_id], check_shapes=check_shapes)
        for universe in UNIVERSES:
            part = parts[universe]
            added: list[str] = []
            if (spec.product_id, universe) in derived:
                part, added = derived[(spec.product_id, universe)](part.copy())
            if universe == "geih" and spec.product_id in _COVERAGE_PRODUCTS:
                part = _with_coverage(part.copy(), coverage_states)
                added = [*added, COVERAGE_COLUMN]
            if spec.product_id == "labor.nacionales" and universe == "geih":
                part, added = _represented_sum_columns(
                    part.copy(), frames["labor.departamentos"]
                )
            part.insert(0, "universe", universe)
            target_dir = folder / f"universo_{universe}" / spec.domain
            target_dir.mkdir(parents=True, exist_ok=True)
            name = _file_name(spec, universe, cutoff, stamp)
            csv_path = target_dir / f"{name}.csv"
            part.to_csv(csv_path, index=False, lineterminator="\n")
            files = [csv_path]
            if excel:
                xlsx_path = target_dir / f"{name}.xlsx"
                _write_xlsx(part, xlsx_path)
                files.append(xlsx_path)
            if spec.split == "columns":
                mapping = spec.census if universe == "censo" else spec.geih
                column_map = {
                    **{k: k for k in spec.keys},
                    **dict(mapping),
                    **{k: k for k in spec.both},
                }
            else:
                column_map = {c: c for c in frames[spec.product_id].columns}
            for file in files:
                outputs.append(
                    {
                        "path": file.relative_to(folder).as_posix(),
                        "sha256": sha256_file(file),
                        "bytes": file.stat().st_size,
                        "rows": int(len(part)),
                        "columns": list(part.columns),
                        "universe": universe,
                        "domain": spec.domain,
                        "level": spec.level,
                        "split": spec.split,
                        "source_product": spec.product_id,
                        "original_to_delivered_columns": column_map,
                        "derived_columns": added,
                        "note": spec.note,
                    }
                )

    manifest = {
        "schema": "icml.delivery.v1",
        "run_id": run_id,
        "created_at_bogota": moment.isoformat(timespec="seconds"),
        "created_at_utc": moment.astimezone(ZoneInfo("UTC")).isoformat(timespec="seconds"),
        "cutoff": cutoff,
        "mode": mode,
        "software_version": software_version,
        "universes": {
            "censo": "Complete territory (CNPV 2018 population).",
            "geih": "Part of the territory represented by the GEIH.",
        },
        "inputs": {
            product: {
                "path": str(path),
                "sha256": sha256_file(Path(path)),
                "rows": int(len(frames[product])),
            }
            for product, path in sorted(products.items())
            if product in frames
        },
        "inputs_note": dict(inputs_note or {}),
        "fingerprints": {k: dict(v) for k, v in (fingerprints or {}).items()},
        "outputs": outputs,
        "publication_authorized": False,
        "notice": (
            "Research estimates, not official statistics. Sectorial products "
            "are experimental; H9 informality lacks direct departmental "
            "official observations."
        ),
    }
    (folder / "MANIFEST.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return manifest
