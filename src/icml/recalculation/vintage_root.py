"""Build a project root as it would have been at an earlier monthly cutoff (library form).

Used by ``icml rebuild --through`` and ``icml update --through``; the command line tool
``tools/release/build_vintage_root.py`` is a thin wrapper around ``build_vintage_root``.

The frozen vintage is never touched. The new root shares the
unchanged files by hard link (or copy where links are not available) and
differs in exactly these ways:

* the GEIH labor annex and the informality annex of the cutoff month replace
  the August ones (found by period, whatever the files are called);
* every period-indexed panel of ``datos/2_procesamiento`` is cut at the
  cutoff, so the frozen references describe the same months as the new
  sources (an append-only source then matches them byte for byte);
* the hashes written in the manifests are re-sealed from a single
  ``old hash -> new hash`` map, so integrity gates still mean something;
* the window proxies of the cutoff are extracted from its annex, and the
  configurations point to all of the above.

Usage (run with ``ICML_CUTOFF`` set to the same cutoff)::

    ICML_CUTOFF=AAAA-MM python build_vintage_root.py --root . --cutoff AAAA-MM --workdir ../raiz_de_corte
"""

from __future__ import annotations

import json
import os
import re
import shutil
import tomllib
from pathlib import Path

import pandas as pd

from icml.delivery.builder import sha256_file
from icml.ingestion.discovery import INFORMALITY, LABOR, annex_for
from icml.domain.cutoff import (
    ACTIVE_CUTOFF,
    CITY13_WINDOWS,
    FROZEN_CUTOFF,
    month_labels,
    vintage_suffix,
)
from icml.operations.excel_historical_sources import _write_csv, extract_geih_annual, extract_window_proxies
from icml.operations.urban_annex import extract_urban_historical_annex

LABOR_DIR = "datos/1_ingesta/excel_originales/Mercado Laboral"
PERIOD_COLUMNS = ("period", "period_end", "date")
_MONTH = re.compile(r"^\d{4}-\d{2}")
_HEX = re.compile(r"\b[0-9a-f]{64}\b")


def _link_or_copy(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(source, target)
    except OSError:
        shutil.copy2(source, target)


def _replace_file(path: Path, write) -> None:
    """Write a new version without touching a hard-linked original."""
    temp = path.with_name(path.name + ".tmp")
    write(temp)
    if path.exists():
        path.unlink()
    temp.replace(path)


def _as_text(value: object) -> str:
    """Format a regenerated cell like the frozen files do (ints stay ints)."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int):
        return str(value)
    return repr(float(value))


def _refresh_last_year(path: Path, regenerated: list[dict], keys: tuple[str, ...], last_year: int) -> int:
    """Keep the frozen bytes of every earlier year; replace only the last year.

    The locked donor guards require the *original* serialization of the
    closed years (a regenerated file differs by ~1e-12). Only the partial
    last year depends on the cutoff, so only its rows are rewritten.
    """
    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    fresh = {tuple(str(row[k]) for k in keys): row for row in regenerated if int(row["year"]) == last_year}
    updated = 0
    for index, row in frame.iterrows():
        if int(row["year"]) != last_year:
            continue
        source = fresh.get(tuple(str(row[k]) for k in keys))
        if source is None:
            raise ValueError(f"{path.name}: no regenerated row for {tuple(row[k] for k in keys)}")
        for column in frame.columns:
            if column in source and column not in keys:
                value = source[column]
                frame.at[index, column] = _as_text(value)
        updated += 1
    if updated != len(fresh):
        raise ValueError(f"{path.name}: {len(fresh)} regenerated rows, {updated} replaced")
    _replace_file(path, lambda target: frame.to_csv(target, index=False, lineterminator="\n"))
    return updated


def _truncate(path: Path, cutoff: str) -> tuple[bool, int, int]:
    """Cut a period-indexed CSV at ``cutoff``; return (changed, before, after)."""
    try:
        header = pd.read_csv(path, nrows=0).columns
    except (pd.errors.EmptyDataError, UnicodeDecodeError):
        return False, 0, 0
    column = next((c for c in PERIOD_COLUMNS if c in header), None)
    if column is None:
        return False, 0, 0
    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    values = frame[column].astype(str)
    if not values.map(lambda v: bool(_MONTH.match(v))).all():
        return False, 0, 0
    keep = values.str[:7] <= cutoff
    if keep.all():
        return False, len(frame), len(frame)
    _replace_file(path, lambda t: frame[keep].to_csv(t, index=False, lineterminator="\n"))
    return True, len(frame), int(keep.sum())


def build_vintage_root(root: Path, cutoff: str, workdir: Path) -> dict:
    """Build, in ``workdir``, the project root of an earlier monthly ``cutoff``.

    Parameters
    ----------
    root : Path
        The real project root (it is never modified).
    cutoff : str
        ``YYYY-MM`` of the vintage; it must be the active cutoff of this process (``ICML_CUTOFF``) and precede
        the frozen vintage.
    workdir : Path
        New folder (must not exist).

    Returns
    -------
    dict
        What was done: panels cut, annexes swapped, manifests re-sealed.
    """
    if cutoff != ACTIVE_CUTOFF:
        raise ValueError(f"Run with ICML_CUTOFF={cutoff} (active cutoff is {ACTIVE_CUTOFF}).")
    if cutoff >= FROZEN_CUTOFF:
        raise ValueError(f"{cutoff} must precede the frozen vintage {FROZEN_CUTOFF}.")
    root, work = Path(root).resolve(), Path(workdir).resolve()
    if work.exists():
        raise FileExistsError(f"Refusing to overwrite {work}")
    # The annexes are found by period, whatever the files are called.
    labor_annex = annex_for(root / "datos/1_ingesta", LABOR, cutoff)
    inf_annex = annex_for(root / "datos/1_ingesta", INFORMALITY, cutoff)
    frozen_labor_rel = annex_for(root / "datos/1_ingesta", LABOR, FROZEN_CUTOFF).path.relative_to(root).as_posix()
    actions: dict = {"cutoff": cutoff, "truncated": {}, "swapped": {}}

    # 1. Share the data tree; configs are copied because they are edited.
    for source in (root / "datos").rglob("*"):
        if source.is_file():
            relative = source.relative_to(root)
            if relative.parts[:2] in (("datos", "3_salida"),) or "vigente" in relative.parts \
                    or "_corridas" in relative.parts:
                continue
            _link_or_copy(source, work / relative)
    shutil.copytree(root / "configs", work / "configs")

    # 2. The cutoff annexes are already in the shared tree; only name them.
    labor_rel = labor_annex.path.relative_to(root).as_posix()
    inf_rel = inf_annex.path.relative_to(root).as_posix()
    proxies_rel = f"datos/2_procesamiento/fuentes_preparadas/urbano/proxies_anuales_ventanas_{vintage_suffix()}.csv"
    _write_csv(work / proxies_rel, extract_window_proxies(work / labor_rel, cutoff))

    # 3. Cut the period-indexed panels; remember every hash that changes.
    reseal: dict[str, str] = {}
    for path in sorted((work / "datos" / "2_procesamiento").rglob("*.csv")):
        old_hash = sha256_file(path)
        changed, before, after = _truncate(path, cutoff)
        if changed:
            reseal[old_hash] = sha256_file(path)
            actions["truncated"][path.relative_to(work).as_posix()] = [before, after]

    # 3b. Artifacts whose last year is partial are derived from the annex, so
    #     they are regenerated for the cutoff instead of cut: the annual
    #     national means and the annual medians of the urban rolling windows.
    catalog_source = json.loads((work / "datos/2_procesamiento/catalogos/catalogo_fuentes.json").read_text("utf-8"))
    national_dir = work / "datos/2_procesamiento/fuentes_preparadas/nacional"
    urban_dir = work / "datos/2_procesamiento/fuentes_preparadas/urbano"
    annual_rows = extract_geih_annual(work / labor_rel, work / "configs/rc1/national.toml")
    historical_rows = extract_urban_historical_annex(
        work / labor_rel,
        urban_dir / "donantes_congelados_referencia.csv",
        work / catalog_source["sources"]["departmental.annex"]["path"],
    )
    last_year = int(cutoff[:4])
    for path, rows, keys in (
        (national_dir / "official_geih_annual.csv", annual_rows, ("year",)),
        (urban_dir / "senales_historicas_23_y_donantes.csv", historical_rows, ("dep_code", "year")),
    ):
        old_hash = sha256_file(path)
        replaced = _refresh_last_year(path, rows, keys, last_year)
        reseal[old_hash] = sha256_file(path)
        actions["truncated"][path.relative_to(work).as_posix()] = f"{replaced} rows of {last_year} regenerated; earlier years keep frozen bytes"

    # 4. Roles and catalog: point at the cutoff annexes and proxies.
    registry_path = work / "datos/2_procesamiento/catalogos/REGISTRO_EXCEL_ORIGINALES_H29.json"
    catalog_path = work / "datos/2_procesamiento/catalogos/catalogo_fuentes.json"
    registry = json.loads(registry_path.read_text("utf-8"))
    registry["active_roles"]["informality_current"] = {"path": inf_rel, "sha256": sha256_file(work / inf_rel)}
    registry["vintage"] = cutoff
    catalog = json.loads(catalog_path.read_text("utf-8"))
    for key in ("national.geih_monthly_annex", "integration.geih_monthly_annex"):
        catalog["sources"][key] = {**catalog["sources"][key], "path": labor_rel,
                                   "sha256": sha256_file(work / labor_rel)}
    catalog["sources"]["urban.window_proxies"] = {**catalog["sources"]["urban.window_proxies"],
                                                  "path": proxies_rel, "sha256": sha256_file(work / proxies_rel)}
    catalog["period_through"] = cutoff
    _replace_file(registry_path, lambda t: t.write_text(json.dumps(registry, indent=2, ensure_ascii=False) + "\n", "utf-8"))
    _replace_file(catalog_path, lambda t: t.write_text(json.dumps(catalog, indent=2, ensure_ascii=False) + "\n", "utf-8"))
    actions["swapped"] = {"labor_annex": labor_rel, "informality_annex": inf_rel, "proxies": proxies_rel}

    # 5. Re-seal every manifest from the single old->new hash map.
    resealed: dict[str, int] = {}
    for path in sorted((work / "datos").rglob("*")):
        if not path.is_file() or path.suffix not in {".json", ".csv", ".md"} or path.stat().st_size > 3_000_000:
            continue
        try:
            text = path.read_text("utf-8")
        except UnicodeDecodeError:
            continue
        hits = [h for h in set(_HEX.findall(text)) if h in reseal]
        if hits:
            for old in hits:
                text = text.replace(old, reseal[old])
            _replace_file(path, lambda t, x=text: t.write_text(x, "utf-8"))
            resealed[path.relative_to(work).as_posix()] = len(hits)
    actions["resealed_manifests"] = resealed

    # 6. Configurations of the cutoff.
    cfg = work / "configs/rc1"
    n_windows = len(month_labels("2021-12", cutoff))
    for file, pairs in {
        "national.toml": [(frozen_labor_rel, labor_rel)],
        "integration.toml": [(frozen_labor_rel, labor_rel), ("n_windows = 57", f"n_windows = {n_windows}"),
                             (f'last_month = "{FROZEN_CUTOFF}"', f'last_month = "{cutoff}"')],
        "urban.toml": [(f"proxies_anuales_ventanas_{FROZEN_CUTOFF.replace('-', '_')}.csv", f"proxies_anuales_ventanas_{vintage_suffix()}.csv")],
    }.items():
        text = (cfg / file).read_text("utf-8")
        for old, new in pairs:
            if old not in text:
                raise ValueError(f"{file}: expected {old!r}")
            text = text.replace(old, new)
        (cfg / file).write_text(text, "utf-8")
        tomllib.loads(text)
    # 6b. Counts the H5 model checks against its source are properties of the
    #     cutoff: take them from the cut snapshot instead of assuming them.
    observations = pd.read_csv(
        work / "datos/2_procesamiento/fuentes_preparadas/informalidad/informality_source_observations.csv",
        dtype=str, keep_default_na=False,
    )
    counts = {
        "expected_observations": len(observations),
        "expected_new_national_windows": CITY13_WINDOWS,
        "expected_possible_missing_zeros": int((observations["value_status"] == "ZERO_SENTINEL_POSSIBLE_MISSING").sum()),
    }
    informality = (cfg / "informality.toml").read_text("utf-8")
    for key, value in counts.items():
        informality, hits = re.subn(rf"^{key} = \d+$", f"{key} = {value}", informality, flags=re.M)
        if hits != 1:
            raise ValueError(f"informality.toml: {key} not found")
    (cfg / "informality.toml").write_text(informality, "utf-8")
    actions["informality_counts"] = counts

    # 7. The configurations pin some snapshots by hash as well.
    for path in sorted(cfg.glob("*.toml")):
        text = path.read_text("utf-8")
        hits = [h for h in set(_HEX.findall(text)) if h in reseal]
        for old_hash in hits:
            text = text.replace(old_hash, reseal[old_hash])
        if hits:
            path.write_text(text, "utf-8")
            resealed[f"configs/rc1/{path.name}"] = len(hits)
    actions["resealed_manifests"] = resealed
    (work / "RAIZ_DE_CORTE.json").write_text(json.dumps(actions, indent=2, ensure_ascii=False) + "\n", "utf-8")
    print(f"Vintage root for {cutoff}: {len(actions['truncated'])} panels cut, "
          f"{len(resealed)} manifests resealed -> {work}")
    return actions

