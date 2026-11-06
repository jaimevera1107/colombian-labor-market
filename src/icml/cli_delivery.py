"""Console commands for two-universe deliveries and recalculation."""

from __future__ import annotations

import argparse
import json
import shutil
import tempfile
from pathlib import Path

from icml.domain.cutoff import ACTIVE_CUTOFF, FROZEN_CUTOFF
from icml.recalculation.policy import MODES
from icml.recalculation.runner import OUTPUT

COMMANDS = ("entrega", "recalcular")


#: A recompute may end in either state; the second one is the adopted method
#: (splices of the 2001-01 seam enabled), which differs from the frozen
#: vintage before that month by design.
CLEAN_STATUSES = frozenset({"RECOMPUTED_ALL_EIGHT_AUDITED", "RECOMPUTED_ALL_EIGHT_CROSS_AUDITED_WITH_SPLICES"})

#: A month other than the frozen one is a new vintage: it is not expected to match the frozen products, so the
#: internal coherence of the eight (the cross audit) is what decides. It is clean only for a cutoff that differs.
NEW_VINTAGE_STATUS = "RECOMPUTED_ALL_EIGHT_CROSS_AUDITED_NEW_VINTAGE"


def require_clean_recompute(report: dict) -> None:
    """Raise unless the integral recompute ended in a clean state.

    The spliced state is only clean when a splice is really enabled in the
    report, so a mislabelled run cannot pass for an audited one.
    """
    status = report.get("status")
    if status == NEW_VINTAGE_STATUS and report.get("cutoff") not in (None, FROZEN_CUTOFF):
        return
    if status not in CLEAN_STATUSES:
        raise RuntimeError(f"Recompute did not finish cleanly: {status}")
    spliced = any(report.get(k, {}).get("enabled") for k in ("regime_splice", "labor_base_splice", "labor_reconstruction"))
    if status.endswith("WITH_SPLICES") and not spliced:
        raise RuntimeError("Recompute reports a spliced state but no splice is enabled")


def splice_notes(report: dict) -> dict[str, str]:
    """Describe the enabled splices for the delivery manifest."""
    notes = {}
    for key in ("regime_splice", "labor_base_splice", "labor_reconstruction"):
        section = report.get(key) or {}
        if section.get("enabled") and key == "labor_reconstruction":
            notes[key] = f"enabled; splice_month={section['break_month']}; scaling_factor={section['scaling_factor']}"
        elif section.get("enabled"):
            notes[key] = (
                f"enabled; break_month={section['break_month']}; window_months={section['window_months']}"
                + (f"; city_break={section['city_break']}" if "city_break" in section else "")
            )
    return notes


def add_commands(commands: argparse._SubParsersAction) -> None:
    """Register ``entrega`` and ``recalcular`` on the main parser."""
    entrega = commands.add_parser(
        "entrega", help="Two-universe deliverables (censo / geih)"
    )
    sub = entrega.add_subparsers(dest="entrega_command", required=True)
    build = sub.add_parser("construir", help="Build a timestamped delivery")
    source = build.add_mutually_exclusive_group(required=True)
    source.add_argument("--desde-corrida", type=Path, help="Folder of a run-integral recompute")
    source.add_argument("--desde-congelados", type=Path, metavar="ROOT", help="Frozen vintage root")
    build.add_argument("--salida", type=Path, required=True, help="Folder that holds the deliveries")
    build.add_argument("--corte", default=ACTIVE_CUTOFF, help="Last month, YYYY-MM")
    build.add_argument("--modo", default="entrega", choices=("entrega", "verificacion"))
    build.add_argument("--excel", action="store_true", help="Also write .xlsx files")
    build.add_argument("--sencillo", action="store_true", help="Also write the simple files (Fecha, DPT, Codigo, ...)")
    simple = sub.add_parser("sencillo", help="Simple files (only the columns of each thing) from a delivery")
    simple.add_argument("--carpeta", type=Path, required=True, help="Delivery folder")
    simple.add_argument("--sin-excel", action="store_true", help="CSV only")
    verify = sub.add_parser("verificar", help="Audit a delivery folder")
    verify.add_argument("--carpeta", type=Path, required=True)

    recalc = commands.add_parser(
        "recalcular",
        help="Recalculate: anclado (default, frozen anchored years) or total",
    )
    recalc.add_argument("--root", type=Path, required=True, help="Project root (holds datos/)")
    recalc.add_argument("--modo", choices=MODES, default="anclado")
    recalc.add_argument("--anio-ancla", type=int, help="Last year of the departmental annex")
    recalc.add_argument("--simulacro", action="store_true", help="Only show the plan")
    recalc.add_argument("--confirmar-total", action="store_true")
    recalc.add_argument("--aceptar-modificados", action="store_true")
    recalc.add_argument("--excel", action="store_true")


def _anchor_year(root: Path) -> int:
    """Read the last year of the configured departmental annex."""
    from icml.departmental.annex import DepartmentAnnexReader
    from icml.departmental.pipeline import load_departmental_config
    from icml.recalculation.policy import anchor_year_from_years

    code = Path(__file__).resolve().parents[2]
    config = load_departmental_config(code / "configs" / "rc1" / "departmental.toml")
    frame = DepartmentAnnexReader(config.annex).read(root / config.sources.annex)
    return anchor_year_from_years(frame["year"])


def _products_from_run(run: Path) -> dict[str, Path]:
    from icml.operations.integral import CANDIDATE_FILES

    return {product: run / relative for product, relative in CANDIDATE_FILES.items()}


def _products_from_frozen(root: Path) -> dict[str, Path]:
    from icml.operations.frozen_products import verify_products

    audit = verify_products(root)
    return {item["product"]: root / item["path"] for item in audit["products"]}


def run_command(args: argparse.Namespace) -> int:
    """Execute ``entrega`` or ``recalcular``; return the exit code."""
    from icml import __version__

    if args.command == "entrega" and args.entrega_command == "construir":
        from icml.delivery.builder import build_delivery

        products = (
            _products_from_run(args.desde_corrida)
            if args.desde_corrida
            else _products_from_frozen(args.desde_congelados)
        )
        manifest = build_delivery(
            products,
            args.salida,
            cutoff=args.corte,
            mode=args.modo,
            software_version=__version__,
            excel=args.excel,
        )
        print(f"Delivery written: {args.salida / manifest['run_id']}")
        if args.sencillo:
            from icml.delivery.simple import build_simple

            result = build_simple(args.salida / manifest["run_id"])
            print(f"Simple files written: {result['folder']}")
        return 0

    if args.command == "entrega" and args.entrega_command == "sencillo":
        from icml.delivery.simple import build_simple

        result = build_simple(args.carpeta, excel=not args.sin_excel)
        print(f"Simple files written: {result['folder']} ({len(result['files'])} tables)")
        return 0

    if args.command == "entrega" and args.entrega_command == "verificar":
        from icml.delivery.verify import verify_delivery

        report = verify_delivery(args.carpeta)
        failed = [c["check"] for c in report["checks"] if not c["passed"]]
        print(f"{report['status']}: {len(report['checks'])} checks, {len(failed)} failed")
        for name in failed:
            print("  FAILED:", name)
        return 0 if report["status"] == "PASS" else 1

    # recalcular
    root = args.root.resolve()
    result = run_recalculation(
        root,
        args.modo,
        anchor=args.anio_ancla,
        confirm_total=args.confirmar_total,
        accept_modified=args.aceptar_modificados,
        dry_run=args.simulacro,
        excel=args.excel,
    )
    print(json.dumps(result["plan"], indent=2, ensure_ascii=False))
    if "manifest" in result:
        print(f"Delivery written: {root / 'datos/3_salida' / result['manifest']['run_id']}")
    return 2 if result["plan"]["status"] == "BLOQUEADO" else 0


def run_recalculation(
    root: Path,
    mode: str,
    *,
    anchor: int | None = None,
    confirm_total: bool = False,
    accept_modified: bool = False,
    dry_run: bool = False,
    excel: bool = False,
    upto: str | None = None,
) -> dict:
    """Plan and, if allowed, run a recalculation of the project at ``root`` up to the active cutoff.

    When the active cutoff precedes the frozen vintage, the integral recomputation runs on a project root built
    for that month (``build_vintage_root``) in a temporary folder; the delivery is always written in ``root``.

    Parameters
    ----------
    root : Path
        Project root (holds ``datos/``).
    mode : str
        ``anclado`` or ``total``.
    anchor : int, optional
        Last year of the departmental annex (read from it when omitted).
    confirm_total, accept_modified, dry_run, excel : bool
        See ``icml.recalculation.runner.recalculate``.
    upto : str, optional
        Work up to this month and ignore the annexes of later months.

    Returns
    -------
    dict
        ``plan`` and, when something ran, the delivery ``manifest`` and the graft reports.
    """
    from icml import __version__
    from icml.operations.integral import run_integral
    from icml.recalculation.runner import recalculate

    root = Path(root).resolve()
    anchor = anchor or _anchor_year(root)

    # ``run_integral`` refuses to write inside the project (it protects the
    # frozen vintage), so the heavy recomputation goes to a temporary folder
    # outside it; only its audit report is kept, next to the delivery.
    workdir = Path(tempfile.mkdtemp(prefix="icml_integral_"))
    run = workdir / "integral"

    methodology: dict[str, str] = {}

    def runner(staging: Path) -> dict[str, Path]:
        source_root = root
        if ACTIVE_CUTOFF < FROZEN_CUTOFF:
            from icml.recalculation.vintage_root import build_vintage_root

            source_root = workdir / "raiz_de_corte"
            build_vintage_root(root, ACTIVE_CUTOFF, source_root)
        report = run_integral(source_root, run, mode="recompute")
        require_clean_recompute(report)
        methodology.update(splice_notes(report))
        return _products_from_run(run)

    try:
        result = recalculate(
            root,
            mode,
            anchor_year=anchor,
            runner=runner,
            confirm_total=confirm_total,
            accept_modified=accept_modified,
            dry_run=dry_run,
            excel=excel,
            software_version=__version__,
            notes=lambda: methodology,
            upto=upto,
        )
        report_file = run / "integral_execution_report.json"
        if "manifest" in result and report_file.is_file():
            folder = root / OUTPUT / result["manifest"]["run_id"]
            shutil.copy2(report_file, folder / "INFORME_RECALCULO_INTEGRAL.json")
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
    return result
