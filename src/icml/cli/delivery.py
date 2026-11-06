"""Expert commands: build, simplify and verify deliveries; plan a recalculation.

``icml delivery build|simple|verify`` work on delivery folders directly;
``icml recalc`` exposes the recalculation planner with every knob
(``rebuild`` and ``update`` are its everyday wrappers).
"""

from __future__ import annotations

import argparse
from pathlib import Path

from icml.cli._common import EXIT_ERROR, EXIT_INTEGRITY_FAILURE, EXIT_OK, Commands, print_json
from icml.domain.cutoff import ACTIVE_CUTOFF
from icml.layout import OUTPUT_DIR
from icml.recalculation.policy import ANCHORED, TOTAL

#: Console names of the recalculation modes, mapped to the persisted values.
MODE_NAMES = {"anchored": ANCHORED, "total": TOTAL}
#: Console names of the delivery modes, mapped to the persisted values.
DELIVERY_MODES = {"delivery": "entrega", "verification": "verificacion"}


def register(commands: Commands) -> None:
    """Register ``delivery`` and ``recalc`` on the main parser."""
    delivery = commands.add_parser("delivery", help="Two-universe deliverables (censo / geih)")
    sub = delivery.add_subparsers(dest="delivery_command", required=True)

    build = sub.add_parser("build", help="Build a timestamped delivery")
    source = build.add_mutually_exclusive_group(required=True)
    source.add_argument("--from-run", type=Path, help="Folder of a run-integral recompute")
    source.add_argument("--from-frozen", type=Path, metavar="ROOT", help="Frozen vintage root")
    build.add_argument("--output", type=Path, required=True, help="Folder that holds the deliveries")
    build.add_argument("--cutoff", default=ACTIVE_CUTOFF, help="Last month, YYYY-MM")
    build.add_argument("--mode", default="delivery", choices=tuple(DELIVERY_MODES))
    build.add_argument("--excel", action="store_true", help="Also write .xlsx files")
    build.add_argument("--simple", action="store_true", help="Also write the simple files (Fecha, DPT, Codigo, ...)")
    build.set_defaults(handler=_build)

    simple = sub.add_parser("simple", help="Simple files (only the columns of each thing) from a delivery")
    simple.add_argument("--folder", type=Path, required=True, help="Delivery folder")
    simple.add_argument("--no-excel", action="store_true", help="CSV only")
    simple.set_defaults(handler=_simple)

    verify = sub.add_parser("verify", help="Audit a delivery folder")
    verify.add_argument("--folder", type=Path, required=True)
    verify.set_defaults(handler=_verify)

    recalc = commands.add_parser("recalc", help="Recalculate: anchored (default, frozen anchored years) or total")
    recalc.add_argument("--root", type=Path, required=True, help="Project root (holds datos/)")
    recalc.add_argument("--mode", choices=tuple(MODE_NAMES), default="anchored")
    recalc.add_argument("--anchor-year", type=int, help="Last year of the departmental annex")
    recalc.add_argument("--dry-run", action="store_true", help="Only show the plan")
    recalc.add_argument("--confirm-total", action="store_true")
    recalc.add_argument("--accept-modified", action="store_true")
    recalc.add_argument("--excel", action="store_true")
    recalc.set_defaults(handler=_recalc)


def _build(args: argparse.Namespace) -> int:
    from icml import __version__
    from icml.delivery.builder import build_delivery
    from icml.recalculation import service

    products = (
        service.products_from_run(args.from_run)
        if args.from_run
        else service.products_from_frozen(args.from_frozen)
    )
    manifest = build_delivery(
        products,
        args.output,
        cutoff=args.cutoff,
        mode=DELIVERY_MODES[args.mode],
        software_version=__version__,
        excel=args.excel,
    )
    print(f"Delivery written: {args.output / manifest['run_id']}")
    if args.simple:
        from icml.delivery.simple import build_simple

        result = build_simple(args.output / manifest["run_id"])
        print(f"Simple files written: {result['folder']}")
    return EXIT_OK


def _simple(args: argparse.Namespace) -> int:
    from icml.delivery.simple import build_simple

    result = build_simple(args.folder, excel=not args.no_excel)
    print(f"Simple files written: {result['folder']} ({len(result['files'])} tables)")
    return EXIT_OK


def _verify(args: argparse.Namespace) -> int:
    from icml.delivery.verify import verify_delivery

    report = verify_delivery(args.folder)
    failed = [c["check"] for c in report["checks"] if not c["passed"]]
    print(f"{report['status']}: {len(report['checks'])} checks, {len(failed)} failed")
    for name in failed:
        print("  FAILED:", name)
    return EXIT_OK if report["status"] == "PASS" else EXIT_ERROR


def _recalc(args: argparse.Namespace) -> int:
    from icml.recalculation import service

    root = args.root.resolve()
    result = service.run_recalculation(
        root,
        MODE_NAMES[args.mode],
        anchor=args.anchor_year,
        confirm_total=args.confirm_total,
        accept_modified=args.accept_modified,
        dry_run=args.dry_run,
        excel=args.excel,
    )
    print_json(result["plan"])
    if "manifest" in result:
        print(f"Delivery written: {root / OUTPUT_DIR / result['manifest']['run_id']}")
    return EXIT_INTEGRITY_FAILURE if result["plan"]["status"] == "BLOQUEADO" else EXIT_OK
