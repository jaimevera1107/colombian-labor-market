"""Replay the July 2026 vintage and update it to August (labor chain).

Uses only the DANE annexes already in ``datos/1_ingesta`` (the July and the
August GEIH annexes). It builds a July vintage with the same code and
procedure as August, then checks, on real figures:

* that no official figure of an anchored year was revised between the two
  annexes (national months and 32-city windows);
* what a naive recomputation would change in the anchored years, and that
  the graft leaves them untouched.

Nothing inside the project is modified: sources are copied to ``--workdir``.

Usage (project root = folder that holds ``datos``)::

    python icml-colombia/tools/release/simulate_july_august.py --root . --workdir ../sim_julio_agosto
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

from icml.delivery.builder import TIMEZONE
from icml.ingestion.discovery import LABOR, annex_for
from icml.operations.h31_sources import _write_csv, extract_window_proxies
from icml.pipeline.chain import run_all
from icml.recalculation.annex_checks import compare_annex_releases
from icml.recalculation.policy import AnchorPolicy
from icml.recalculation.replay import compare_labor_vintages

AUGUST_PROXIES = "datos/2_procesamiento/fuentes_preparadas/urbano/proxies_anuales_ventanas_2026_08.csv"
JULY_PROXIES = "datos/2_procesamiento/fuentes_preparadas/urbano/proxies_anuales_ventanas_2026_07.csv"


def _substitute(path: Path, pairs: list[tuple[str, str]]) -> None:
    text = path.read_text(encoding="utf-8")
    for old, new in pairs:
        if old not in text:
            raise ValueError(f"{path.name}: expected {old!r}")
        text = text.replace(old, new)
    path.write_text(text, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    """Run the simulation; return 0 on success, 3 if July does not close."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--workdir", type=Path, required=True, help="New folder")
    parser.add_argument(
        "--tolerancia-ancla",
        type=float,
        default=None,
        help="Replace the anchor gate threshold (persons) in the JULY run only.",
    )
    args = parser.parse_args(argv)
    root, work = args.root.resolve(), args.workdir.resolve()
    if work.exists():
        raise FileExistsError(f"Refusing to overwrite {work}")
    configs = root / "icml-colombia" / "configs" / "rc1"
    sources = work / "fuentes"
    # The annexes are found by period, whatever the files are called.
    AUGUST_ANNEX = annex_for(root / "datos/1_ingesta", LABOR, "2026-08").path.relative_to(root).as_posix()
    JULY_ANNEX = annex_for(root / "datos/1_ingesta", LABOR, "2026-07").path.relative_to(root).as_posix()
    # 1. Copy only the files the configurations name, plus the July annex.
    toml_text = "\n".join(p.read_text(encoding="utf-8") for p in configs.glob("*.toml"))
    needed = sorted(set(re.findall(r'"(datos/[^"]+)"', toml_text)))
    for relative in needed:
        origin = root / relative
        if origin.is_file():
            (sources / relative).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(origin, sources / relative)
    (sources / JULY_ANNEX).parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(root / JULY_ANNEX, sources / JULY_ANNEX)
    _write_csv(sources / JULY_PROXIES, extract_window_proxies(sources / JULY_ANNEX, "2026-07"))
    # 2. July configuration: annex, 56 windows, last month 2026-07, July proxies.
    july_configs = work / "configuracion_julio"
    shutil.copytree(configs, july_configs)
    _substitute(july_configs / "national.toml", [(AUGUST_ANNEX, JULY_ANNEX)])
    _substitute(
        july_configs / "integration.toml",
        [(AUGUST_ANNEX, JULY_ANNEX), ("n_windows = 57", "n_windows = 56"),
         ('last_month = "2026-08"', 'last_month = "2026-07"')],
    )
    _substitute(july_configs / "urban.toml", [(AUGUST_PROXIES, JULY_PROXIES)])
    if args.tolerancia_ancla is not None:
        _substitute(
            july_configs / "reconciliation.toml",
            [("anchor_tolerance_persons = 1e-4", f"anchor_tolerance_persons = {args.tolerancia_ancla}")],
        )
    # 3. Both vintages with the same procedure.
    runs = work / "corridas"
    print("Corriendo agosto ...", flush=True)
    august = run_all(configs, sources, runs, "agosto")
    print("Corriendo julio ...", flush=True)
    try:
        july = run_all(july_configs, sources, runs, "julio")
    except Exception as exc:  # noqa: BLE001 - report the gate that stopped it
        print(f"JULIO NO CIERRA: {type(exc).__name__}: {exc}")
        print("Si es 'Annual anchor not kept' por unos 1e-4 personas, use --tolerancia-ancla 1e-3.")
        return 3
    # 4. Checks on real figures.
    from icml.cli_delivery import _anchor_year

    policy = AnchorPolicy(_anchor_year(root))
    annexes = compare_annex_releases(
        sources / JULY_ANNEX,
        sources / AUGUST_ANNEX,
        national_config=configs / "national.toml",
        integration_config=configs / "integration.toml",
        previous_windows=56,
        current_windows=57,
        policy=policy,
    )
    vintages = compare_labor_vintages(
        july / "quality" / "products", august / "quality" / "products", policy
    )
    report = {
        "created_at_bogota": datetime.now(TIMEZONE).isoformat(timespec="seconds"),
        "anchor_year": policy.last_anchor_year,
        "july_anchor_tolerance_override": args.tolerancia_ancla,
        "annex_revisions": annexes,
        "vintages": vintages,
    }
    (work / "INFORME_SIMULACION_JULIO_AGOSTO.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8"
    )
    print(f"\nRevisiones entre anexos (años congelados hasta {policy.last_anchor_year}): {annexes['status']}")
    for name, item in annexes["sources"].items():
        print(f"  {name}: {item['n_revisions']} revisiones; {item['observations_compared']}")
    for name, item in vintages["products"].items():
        print(
            f"  {name}: un recálculo ingenuo cambiaría "
            f"{item['frozen_cells_a_naive_recomputation_would_change']} celdas congeladas "
            f"{item['by_year']}; tras el injerto: {item['frozen_cells_changed_after_graft']}"
        )
    print(f"Informe: {work / 'INFORME_SIMULACION_JULIO_AGOSTO.json'}")
    return 0 if annexes["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
