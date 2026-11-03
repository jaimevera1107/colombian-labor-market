"""Verify the ICML 2.1.2 backup without running model estimation.

Usage: python icml-colombia/tools/release/verify_backup.py --bundle .

Hashes cover both the source tree and frozen release assets, excluding
this tool only insofar as it is listed and hashed like any other file.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

LEVELS = (
    "population",
    "working_age",
    "labor_force",
    "employed",
    "unemployed",
    "inactive",
)
MONTH_START = "1993-01"
MONTH_END = "2026-08"


def _file_hash(path: Path) -> str:
    """Compute a SHA-256 digest of the file in bounded memory."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_manifest(bundle: Path) -> int:
    """Validate every checksum and byte size in the backup manifest."""
    manifest = bundle / "MANIFIESTO_RESPALDO_SHA256.json"
    records = json.loads(manifest.read_text(encoding="utf-8"))["files"]
    if not records:
        raise ValueError("The backup manifest is empty")
    for record in records:
        relative = Path(record["path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"Unsafe manifest path: {relative}")
        path = bundle / relative
        if not path.is_file():
            raise ValueError(f"Missing file: {relative}")
        if path.stat().st_size != record["size_bytes"]:
            raise ValueError(f"Size mismatch: {relative}")
        if _file_hash(path) != record["sha256"]:
            raise ValueError(f"SHA-256 mismatch: {relative}")
    return len(records)


def _check_frame(frame: pd.DataFrame, name: str) -> None:
    """Validate mandatory labor fields and monthly accounting."""
    missing = set(LEVELS).difference(frame.columns)
    if missing:
        raise ValueError(f"{name}: missing quantities {sorted(missing)}")
    x = frame[list(LEVELS)].apply(pd.to_numeric, errors="coerce")
    if not np.isfinite(x.to_numpy(dtype=float)).all():
        raise ValueError(f"{name}: null or infinite labor quantities")
    if x.lt(0).any().any():
        raise ValueError(f"{name}: negative labor quantities")
    tolerance = 1.1 if name == "nacionales" else 1e-5
    if (x.labor_force - x.employed - x.unemployed).abs().max() > tolerance:
        raise ValueError(f"{name}: PEA accounting failed")
    if (x.working_age - x.labor_force - x.inactive).abs().max() > tolerance:
        raise ValueError(f"{name}: PET accounting failed")
    if (x.working_age - x.population).max() > tolerance:
        raise ValueError(f"{name}: PET exceeds population")


def verify_products(bundle: Path) -> None:
    """Check the fixed-vintage three-base public delivery contract."""
    folder = bundle / "productos" / "bases"
    tables = {
        name: pd.read_csv(
            folder / f"{name}.csv",
            dtype={"dep_code": "string", "city_code": "string"},
        )
        for name in ("ciudades", "departamentos", "nacionales")
    }
    months = list(pd.period_range(MONTH_START, MONTH_END, freq="M").astype(str))
    expected = {"ciudades": 33, "departamentos": 33, "nacionales": 2}
    for name, table in tables.items():
        _check_frame(table, name)
        if len(table) != expected[name] * len(months):
            raise ValueError(f"{name}: unexpected number of rows")
        if sorted(table.period.astype(str).unique()) != months:
            raise ValueError(f"{name}: incomplete monthly calendar")
        key = (
            "city_code" if name == "ciudades" else
            "dep_code" if name == "departamentos" else "national_type"
        )
        if table.duplicated([key, "period"]).any():
            raise ValueError(f"{name}: duplicate territory-month")
        if table.groupby("period")[key].nunique().ne(expected[name]).any():
            raise ValueError(f"{name}: incomplete territorial coverage")

    cities = tables["ciudades"]
    deps = tables["departamentos"]
    national = tables["nacionales"]
    if cities.city_code.eq("00").any() or deps.dep_code.eq("00").any():
        raise ValueError("National 00 was included in a territorial table")
    if set(national.national_type) != {"ICML_COMPLETO", "DANE_REFERENCIA"}:
        raise ValueError("Expected both national series")
    if not national.dep_code.eq("00").all():
        raise ValueError("National codes must be 00")
    early = deps.period.lt("2001-01")
    factors = [f"factor_{name}" for name in LEVELS]
    if not deps.loc[early, factors].eq(1.0).all().all():
        raise ValueError("Historical departmental factors are not 1")
    if not national.loc[national.period.lt("2001-01"), factors].eq(1).all().all():
        raise ValueError("Historical national factors are not 1")
    aggregate = deps.groupby("period")[list(LEVELS)].sum().sort_index()
    icml = (national.loc[national.national_type.eq("ICML_COMPLETO")]
            .set_index("period")[list(LEVELS)].sort_index())
    if np.max(np.abs(aggregate.to_numpy() - icml.to_numpy())) > 1e-5:
        raise ValueError("ICML national does not equal sum of departments")


def main() -> int:
    """Print a portable integrity verdict."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, default=Path("."))
    args = parser.parse_args()
    root = args.bundle.resolve()
    files_count = verify_manifest(root)
    verify_products(root)
    print(f"OK: {files_count} SHA-256 files and three labor databases validated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
