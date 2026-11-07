"""Expert commands: integrity gates, frozen products, source intake and certification.

Every command here is read-only on the checkpoint or stages its output in a
NEW folder outside it; none of them publishes anything.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from icml.cli._common import EXIT_INTEGRITY_FAILURE, EXIT_OK, Commands, add_path_flags, print_json, write_new_report

INTEGRAL_MODES = ("verify", "recompute-components", "recompute")
#: Integral run states that count as a success for the exit code.
INTEGRAL_SUCCESS = frozenset({
    "VERIFIED_EXISTING_VINTAGE_NOT_REEXECUTED",
    "RECOMPUTED_ALL_EIGHT_AUDITED",
    "RECOMPUTED_ALL_EIGHT_CROSS_AUDITED_WITH_SPLICES",
    "RECOMPUTED_ALL_EIGHT_CROSS_AUDITED_WITH_SPLICES_ON_ANOTHER_PLATFORM",
    "RECOMPUTED_ALL_EIGHT_CROSS_AUDITED_NEW_VINTAGE",
    "RECOMPUTED_H9_H16_WITH_FROZEN_LABOR_AUDITED",
    "RECOMPUTED_H9_H16_FROM_VERIFIED_STAGE_RUNS",
})


def register(commands: Commands) -> None:
    """Register the ``operations`` group on the main parser."""
    ops = commands.add_parser("operations", help="Integrity, product freeze, monthly vintage and certification controls")
    op = ops.add_subparsers(dest="operations_command", required=True)

    pf = op.add_parser("preflight", help="Verify the frozen checksum and golden availability")
    add_path_flags(pf, "root", "output")
    pf.add_argument("--golden-dir", type=Path)
    pf.set_defaults(handler=_preflight)

    upd = op.add_parser("stage-update", help="Check next-month candidate without publishing")
    add_path_flags(upd, "previous", "candidate", "output")
    upd.add_argument("--keys", nargs="+", required=True)
    upd.add_argument("--quantities", nargs="+", required=True)
    upd.add_argument("--old-last-month", required=True)
    upd.add_argument("--new-last-month", required=True)
    upd.add_argument("--old-last-anchored-year", type=int, required=True)
    upd.add_argument("--new-last-anchored-year", type=int, required=True)
    upd.add_argument("--window-length", type=int, default=12)
    upd.set_defaults(handler=_stage_update)

    intake = op.add_parser("intake-geih", help="Stage an official GEIH monthly XLSX without changing frozen products")
    intake.add_argument("--root", type=Path, required=True)
    intake.add_argument("--period", required=True)
    intake.add_argument("--annex", type=Path, help="Locally downloaded original GEIH monthly XLSX")
    intake.add_argument("--previous-annex", type=Path, help="Previous original XLSX to audit revisions")
    intake.add_argument("--output", type=Path, required=True, help="New EMPTY directory")
    intake.set_defaults(handler=_intake_geih)

    pair = op.add_parser("check-monthly-sources",
                         help="Verify declared reference-month synchronization (never authorizes a new vintage)")
    pair.add_argument("--period", required=True, help="ICML month YYYY-MM")
    pair.add_argument("--geih-annex", type=Path, help="Original GEIH monthly XLSX")
    pair.add_argument("--geih-month", help="Month VERIFIED in the GEIH annex, YYYY-MM")
    pair.add_argument("--social-annex", type=Path, help="Original Informal Employment and Social Security moving-3m annex")
    pair.add_argument("--social-start", help="First reference month VERIFIED in social annex, YYYY-MM")
    pair.add_argument("--social-end", help="Last reference month VERIFIED in social annex, YYYY-MM")
    pair.add_argument("--report", type=Path, help="New JSON report; never overwrites")
    pair.set_defaults(handler=_check_monthly_sources)

    social = op.add_parser("audit-social-annex",
                           help="Validate source content, calendar and accounting of the original DANE Social Security XLSX")
    social.add_argument("--annex", type=Path, required=True)
    social.add_argument("--period", required=True)
    social.add_argument("--report", type=Path, help="NEW JSON file; never overwrites")
    social.set_defaults(handler=_audit_social_annex)

    trace = op.add_parser("audit-informality-origin",
                          help="Audit the national informality anchor against the DANE monthly source Excel")
    trace.add_argument("--root", type=Path, required=True)
    trace.add_argument("--report", type=Path, help="NEW JSON file; never overwrites")
    trace.set_defaults(handler=_audit_informality_origin)

    lineage = op.add_parser("audit-historical-lineage",
                            help="Audit the Pareto donor study and archived Excel overlaps without changing inputs")
    lineage.add_argument("--root", type=Path, required=True)
    lineage.add_argument("--report", type=Path, required=True, help="NEW JSON report outside checkpoint")
    lineage.set_defaults(handler=_audit_historical_lineage)

    all_excel = op.add_parser("prepare-all-excel", help="Stage every proven Excel-derived table, without editing canonical data")
    all_excel.add_argument("--root", type=Path, required=True)
    all_excel.add_argument("--output", type=Path, required=True, help="NEW output directory outside frozen checkpoint")
    all_excel.set_defaults(handler=_prepare_all_excel)

    hist_excel = op.add_parser("prepare-historical-excel",
                               help="Reproduce urban 12-month proxies, GEIH annual and monthly economic indicators from frozen XLSX")
    hist_excel.add_argument("--root", type=Path, required=True)
    hist_excel.add_argument("--output", type=Path, required=True, help="NEW staging directory outside checkpoint")
    hist_excel.set_defaults(handler=_prepare_historical_excel)

    excel = op.add_parser("prepare-excel", help="Derive audited population, GDP and sectoral CSVs from original XLSX")
    excel.add_argument("--root", type=Path, required=True)
    excel.add_argument("--output", type=Path, required=True, help="NEW staging directory OUTSIDE the checkpoint")
    excel.set_defaults(handler=_prepare_excel)

    source_audit = op.add_parser("source-audit", help="Audit the central source catalog and stage configurations")
    source_audit.add_argument("--root", type=Path, required=True)
    source_audit.set_defaults(handler=_source_audit)

    source_sync = op.add_parser("source-sync", help="Preview or synchronize nonmonthly stage pointers from the catalog")
    source_sync.add_argument("--root", type=Path, required=True)
    source_sync.add_argument("--apply", action="store_true", help="Use ONLY on a copied new-vintage project")
    source_sync.set_defaults(handler=_source_sync)

    source_stage = op.add_parser("source-stage", help="Stage an updated file for a NEW vintage without activating it")
    source_stage.add_argument("--root", type=Path, required=True)
    source_stage.add_argument("--role", required=True)
    source_stage.add_argument("--file", type=Path, required=True)
    source_stage.add_argument("--period", required=True)
    source_stage.add_argument("--output", type=Path, required=True)
    source_stage.set_defaults(handler=_source_stage)

    integral = op.add_parser("run-integral", help="Unified research validation or source recomputation")
    integral.add_argument("--root", type=Path, required=True, help="Frozen checkpoint root")
    integral.add_argument("--output", type=Path, required=True, help="NEW directory OUTSIDE the frozen checkpoint")
    integral.add_argument("--mode", choices=INTEGRAL_MODES, default="verify",
                          help="verify: audit; recompute-components: informality and sectoral with frozen labor; "
                               "recompute: all stages from sources")
    integral.add_argument("--sources", type=Path, help="Complete historical input tree for the labor stages")
    integral.add_argument("--configs", type=Path, help="Canonical RC1 stage configs (default in checkpoint)")
    integral.add_argument("--informality-root", type=Path, help="Complete immutable informality auxiliary inputs tree")
    integral.add_argument("--resume-informality", type=Path, help="Previously FINISHED and hash-verifiable informality stage output")
    integral.add_argument("--resume-sectoral", type=Path, help="Previously FINISHED and hash-verifiable sectoral predictor output")
    integral.set_defaults(handler=_run_integral)

    pre = op.add_parser("integral-preflight", help="Audit the inputs needed to re-execute the frozen model")
    pre.add_argument("--root", type=Path, required=True)
    pre.add_argument("--mode", choices=INTEGRAL_MODES, default="recompute")
    pre.add_argument("--sources", type=Path)
    pre.add_argument("--configs", type=Path)
    pre.add_argument("--informality-root", type=Path)
    pre.set_defaults(handler=_integral_preflight)

    cycle = op.add_parser("monthly-cycle", help="Immutable monthly source intake and blocked production run plan")
    cycle.add_argument("--root", type=Path, required=True, help="Existing frozen checkpoint root")
    cycle.add_argument("--period", required=True, help="Strictly next YYYY-MM month")
    cycle.add_argument("--geih-annex", type=Path)
    cycle.add_argument("--geih-month", help="GEIH declared reference month, verified against workbook")
    cycle.add_argument("--social-annex", type=Path)
    cycle.add_argument("--social-start", help="Declared first month of the moving quarter")
    cycle.add_argument("--social-end", help="Declared last month of the moving quarter")
    cycle.add_argument("--output", type=Path, required=True, help="New empty staging directory OUTSIDE checkpoint")
    cycle.set_defaults(handler=_monthly_cycle)

    cycle_verify = op.add_parser("verify-monthly-cycle", help="Check immutable intake and frozen product integrity")
    add_path_flags(cycle_verify, "root", "cycle")
    cycle_verify.set_defaults(handler=_verify_monthly_cycle)

    vp = op.add_parser("verify-products", help="Audit SHA-256 of the eight frozen products")
    vp.add_argument("--root", type=Path, required=True)
    vp.add_argument("--report", type=Path)
    vp.set_defaults(handler=_verify_products)

    fr = op.add_parser("freeze-products", help="Stage an immutable NON-OFFICIAL snapshot of the eight frozen products")
    add_path_flags(fr, "root", "destination")
    fr.set_defaults(handler=_freeze_products)

    cert = op.add_parser("certify", help="Read-only frozen-product, Python lock and external RC1 golden readiness audit")
    cert.add_argument("--root", type=Path, required=True)
    cert.add_argument("--report", type=Path, required=True, help="NEW JSON output; refuses overwrites")
    cert.add_argument("--golden-dir", type=Path, help="External ORIGINAL RC1 golden tree only")
    cert.set_defaults(handler=_certify)


def _gate(result: dict, passed: bool) -> int:
    print_json(result)
    return EXIT_OK if passed else EXIT_INTEGRITY_FAILURE


def _preflight(args: argparse.Namespace) -> int:
    from icml.operations.monthly_staging import preflight

    result = preflight(args.root, args.output, args.golden_dir)
    return _gate(result, result["status"].startswith("PASS"))


def _stage_update(args: argparse.Namespace) -> int:
    from icml.operations.monthly_staging import stage_update
    from icml.pipeline.vintage import VintagePolicy

    old_policy = VintagePolicy(args.old_last_month, args.old_last_anchored_year, args.window_length)
    new_policy = VintagePolicy(args.new_last_month, args.new_last_anchored_year, args.window_length)
    result = stage_update(args.previous, args.candidate, args.output, args.keys, args.quantities, old_policy, new_policy)
    return _gate(result, result["status"].startswith("ACCEPTED"))


def _intake_geih(args: argparse.Namespace) -> int:
    from icml.operations.geih_intake import prepare_intake

    result = prepare_intake(args.root, args.output, args.period, args.annex, args.previous_annex)
    return _gate(result, result["status"].startswith("STAGED"))


def _check_monthly_sources(args: argparse.Namespace) -> int:
    from icml.operations.source_pair import check_monthly_sources

    result = check_monthly_sources(args.period, args.geih_annex, args.social_annex,
                                   args.geih_month, args.social_start, args.social_end)
    write_new_report(args.report, result)
    # Metadata coherence never passes the full quality gate.
    return _gate(result, result["status"].startswith("PAIR_CALENDAR_COHERENT"))


def _audit_social_annex(args: argparse.Namespace) -> int:
    from icml.operations.social_annex import inspect_social_annex

    result = inspect_social_annex(args.annex, args.period)
    write_new_report(args.report, result)
    return _gate(result, result["status"].startswith("PASS"))


def _audit_informality_origin(args: argparse.Namespace) -> int:
    from icml.operations.informality_lineage import audit_national_h9_lineage

    result = audit_national_h9_lineage(args.root)
    write_new_report(args.report, result)
    return _gate(result, result["status"].startswith("PASS"))


def _audit_historical_lineage(args: argparse.Namespace) -> int:
    from icml.operations.historical_lineage import audit

    result = audit(args.root)
    write_new_report(args.report, result)
    return _gate(result, result["status"] == "PASS")


def _prepare_all_excel(args: argparse.Namespace) -> int:
    from icml.operations.excel_staging import run

    result = run(args.root, args.output)
    summary = {key: result[key] for key in ("status", "verified_generators", "reference_month")}
    return _gate(summary, result["status"] == "PASS")


def _prepare_historical_excel(args: argparse.Namespace) -> int:
    from icml.operations.excel_historical_sources import run

    result = run(args.root, args.output)
    return _gate(result, result["status"] == "PASS")


def _prepare_excel(args: argparse.Namespace) -> int:
    from icml.operations.excel_sources import run

    result = run(args.root, args.output, verify=True)
    return _gate(result, result["status"] == "PASS")


def _source_audit(args: argparse.Namespace) -> int:
    from icml.operations.source_catalog import audit_catalog

    result = audit_catalog(args.root)
    return _gate(result, result["status"] == "PASS")


def _source_sync(args: argparse.Namespace) -> int:
    from icml.operations.source_catalog import synchronize_stage_configs

    result = synchronize_stage_configs(args.root, apply=args.apply)
    return _gate(result, result["status"] != "BLOCKED")


def _source_stage(args: argparse.Namespace) -> int:
    from icml.operations.source_catalog import stage_new_source

    print_json(stage_new_source(args.root, args.role, args.file, args.output, args.period))
    return EXIT_OK


def _run_integral(args: argparse.Namespace) -> int:
    from icml.operations.integral import run_integral

    result = run_integral(args.root, args.output, mode=args.mode, sources=args.sources, configs=args.configs,
                          informality_root=args.informality_root, resume_informality=args.resume_informality,
                          resume_sectoral=args.resume_sectoral)
    print_json({"status": result["status"],
                "report": str(args.output / "integral_execution_report.json"),
                "recalculated": result["recalculated_from_sources"]})
    return EXIT_OK if result["status"] in INTEGRAL_SUCCESS else EXIT_INTEGRITY_FAILURE


def _integral_preflight(args: argparse.Namespace) -> int:
    from icml.operations.integral import preflight

    result = preflight(args.root, args.mode, sources=args.sources, configs=args.configs,
                       informality_root=args.informality_root)
    return _gate(result, result["status"] == "READY")


def _monthly_cycle(args: argparse.Namespace) -> int:
    from icml.operations.monthly_cycle import prepare_monthly_cycle

    result = prepare_monthly_cycle(args.root, args.period, args.output, args.geih_annex, args.social_annex,
                                   args.geih_month, args.social_start, args.social_end)
    print_json(result)
    # Deliberately 2: a source-only intake never clears the computation gate.
    return EXIT_INTEGRITY_FAILURE


def _verify_monthly_cycle(args: argparse.Namespace) -> int:
    from icml.operations.monthly_cycle import verify_monthly_cycle

    result = verify_monthly_cycle(args.root, args.cycle)
    return _gate(result, not result["issues"])


def _verify_products(args: argparse.Namespace) -> int:
    from icml.operations.frozen_products import verify_products

    result = verify_products(args.root)
    write_new_report(args.report, result)
    return _gate(result, not result["issues"])


def _freeze_products(args: argparse.Namespace) -> int:
    from icml.operations.frozen_products import freeze_products

    print_json(freeze_products(args.root, args.destination))
    return EXIT_OK


def _certify(args: argparse.Namespace) -> int:
    from icml.operations.certification import write_report

    result = write_report(args.root, args.report, args.golden_dir)
    return _gate(result, result["release_gate"].startswith("ELIGIBLE"))
