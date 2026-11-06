"""Command-line interface: ``icml <command>``.

* ``icml run`` executes the seven stages from the DANE sources to the
  three products;
* ``icml <stage> run`` executes one stage on top of completed upstream
  runs (``--national-run``, ``--urban-run``, ...);
* ``icml golden capture|verify`` manages the RC1 reference set.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING

from icml import __version__
from icml.pipeline.stage_registry import STAGE_SPECS as STAGES
from icml.regression.catalog import load_catalog
from icml.regression.golden import capture_golden, check_integrity

DEFAULT_CATALOG = Path("configs/golden/rc1_catalog.toml")
EXIT_OK = 0
EXIT_INTEGRITY_FAILURE = 2

if TYPE_CHECKING:
    _Commands = argparse._SubParsersAction[argparse.ArgumentParser]


def _add_golden(commands: _Commands) -> None:
    golden = commands.add_parser("golden", help="RC1 golden reference set")
    golden_commands = golden.add_subparsers(
        dest="golden_command", required=True
    )
    capture = golden_commands.add_parser(
        "capture", help="Copy catalogued RC1 artifacts to a golden folder."
    )
    capture.add_argument(
        "--legacy-root",
        type=Path,
        required=True,
        help="Root of the legacy RC2 'Proyecto' tree.",
    )
    capture.add_argument("--destination", type=Path, required=True)
    capture.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    verify = golden_commands.add_parser(
        "verify", help="Check hashes of a golden folder or legacy tree."
    )
    verify.add_argument("--root", type=Path, required=True)
    verify.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)


def _add_stages(commands: _Commands) -> None:
    for name, stage in STAGES.items():
        parser = commands.add_parser(name, help=f"{name.capitalize()} stage")
        sub = parser.add_subparsers(dest=f"{name}_command", required=True)
        run = sub.add_parser("run", help=f"Run the {name} stage.")
        run.add_argument("--config", type=Path, required=True)
        if stage.reads_sources:
            run.add_argument("--sources", type=Path, required=True)
        for upstream in stage.upstream:
            run.add_argument(f"--{upstream}-run", type=Path, required=True)
        run.add_argument("--runs-dir", type=Path, required=True)
        run.add_argument("--run-id", required=True)
        if name == "informality":
            extract = sub.add_parser(
                "extract", help="Extract the original DANE informality annexes."
            )
            extract.add_argument("--old", type=Path, required=True)
            extract.add_argument("--new", type=Path, required=True)
            extract.add_argument("--output", type=Path, required=True)
            history = sub.add_parser(
                "historical", help="Build audited experimental 1993-2026 national history."
            )
            history.add_argument("--sources", type=Path, required=True)
            history.add_argument("--nationals", type=Path, required=True)
            history.add_argument("--recent", type=Path, required=True)
            history.add_argument("--ilo", type=Path, required=True)
            history.add_argument("--output", type=Path, required=True)
            urban_history = sub.add_parser(
                "urban-history", help="DANE-only urban-first informality backcast, isolated candidate."
            )
            sequential = sub.add_parser(
                "sequential", help="13 areas -> national -> 23 cities -> 33 signals and baseline (experimental)."
            )
            for flag in ("sources", "cities", "departments", "nationals", "recent", "anchors13", "output", "config"):
                sequential.add_argument(f"--{flag}", type=Path, required=True)
            consolidate = sub.add_parser(
                "consolidate-features",
                help="Consolidate original informality feature families with labor-stage fold-safe clusters.",
            )
            for flag in ("cities", "departments", "nationals", "urban-informality", "population", "modeling-config", "output"):
                consolidate.add_argument(f"--{flag}", type=Path, required=True)
            calibration = sub.add_parser(
                "calibrate-national",
                help="Experimental original-informed calibration of departmental informal shares to national universes.",
            )
            for flag in ("departments", "predictions", "national", "output"):
                calibration.add_argument(f"--{flag}", type=Path, required=True)
            calibration.add_argument("--rate-column", required=True)
            calibration.add_argument("--label", required=True)
            calibration.add_argument("--allow-missing-months", action="store_true")
            post = sub.add_parser(
                "audit-postclosure",
                help="Read-only comparison of candidate MLP + national calibration.",
            )
            for flag in ("closures", "departments", "national", "output"):
                post.add_argument(f"--{flag}", type=Path, required=True)
            post.add_argument("--sensitivity-pp", type=float, default=1.0)
            frontier = sub.add_parser(
                "compare-calibrators",
                help="Experimental five-way constrained national calibration comparison (read-only priors).",
            )
            for flag in ("closures", "departments", "national", "output"):
                frontier.add_argument(f"--{flag}", type=Path, required=True)
            bridge_stress = sub.add_parser(
                "audit-national-bridge",
                help="Read-only national bridge, two-domain stress and MLP-2020 diagnostic.",
            )
            for flag in ("departments", "nationals", "sources", "recent",
                         "anchors13", "cities13", "closures", "output"):
                bridge_stress.add_argument(f"--{flag}", type=Path, required=True)
            transfer12 = sub.add_parser(
                "census-transfer-mlp",
                help="CNPV-2018 transfer experiment: one residual MLP, full vs GEIH projection, no canonical edits.",
            )
            for flag in ("features-dir", "census-bridge", "census-anchors", "model-dir",
                         "previous-predictions", "national", "output"):
                transfer12.add_argument(f"--{flag}", type=Path, required=True)
            transfer12.add_argument("--skip-refit", action="store_true",
                help="Reuse the frozen model instead of performing an identical-training control fit")
            close_block = sub.add_parser(
                "finalize-block", help="Complete the three noncanonical informality bases with one MLP and CNPV GEIH transfer.")
            close_block.add_argument("--root", required=True, type=Path,
                                     help="Complete 2.2.12+ checkpoint folder (immutable inputs).")
            close_block.add_argument("--output", required=True, type=Path)
            close_block.add_argument("--gap-method", choices=("interpolated","seasonal_2019","urban_shock"),default="interpolated")
            mlp_gate = sub.add_parser("audit-mlp", help="Read-only quality gate for experimental MLP.")
            mlp_gate.add_argument("--experiment", type=Path, required=True)
            mlp_gate.add_argument("--national", type=Path, required=True)
            mlp = sub.add_parser(
                "fit-mlp", help="Audit and fit original residual informality MLP (experimental)."
            )
            mlp.add_argument("--features-folder", type=Path, required=True)
            mlp.add_argument("--output", type=Path, required=True)
            mlp.add_argument("--epochs", type=int, default=120)
            mlp.add_argument("--folds-per-definition", type=int, default=5)
            audit = sub.add_parser(
                "audit-historical", help="Audit 13→national→23→ML informality candidate (read-only)."
            )
            for flag in ("candidate", "cities-labor", "nationals-labor", "output"):
                audit.add_argument(f"--{flag}", type=Path, required=True)
            audit.add_argument("--previous-national", type=Path)
            for flag in ("sources", "cities", "nationals", "recent", "anchors13",
                         "anchors-cities", "output"):
                urban_history.add_argument(f"--{flag}", type=Path, required=True)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="icml", description=__doc__)
    parser.add_argument(
        "--version", action="version", version=f"icml {__version__}"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    from icml.cli_delivery import add_commands as add_delivery_commands

    add_delivery_commands(commands)
    from icml.cli_amigable import add_commands as add_friendly_commands

    add_friendly_commands(commands)
    full = commands.add_parser(
        "run", help="Run every stage, from sources to products."
    )
    full.add_argument(
        "--configs",
        type=Path,
        required=True,
        help="Folder with the seven stage TOML files.",
    )
    full.add_argument("--sources", type=Path, required=True)
    full.add_argument("--runs-dir", type=Path, required=True)
    full.add_argument("--run-id", required=True)
    full.add_argument("--census-source", type=Path, default=None,
                      help="Optional CNPV 2018 adjusted nine capitals CSV (post-quality audit stage).")
    _add_stages(commands)
    sectoral = commands.add_parser("sectoral", help="H10 real-month DANE sectoral source audit")
    sectoral_cmd = sectoral.add_subparsers(dest="sectoral_command", required=True)
    sectoral_monthly = sectoral_cmd.add_parser("audit-monthly", help="Extract observed calendar months; never smooth rolling quarters")
    sectoral_monthly.add_argument("--legacy-checks", type=Path)
    sectoral_monthly.add_argument("--workbook", type=Path,
                        help="Original DANE annex; direct extraction requires artifact_tool; can also verify CSV hash")
    sectoral_monthly.add_argument("--observations-csv", type=Path,
                        help="Frozen 13-group monthly normalized CSV (no Excel runtime needed)")
    sectoral_monthly.add_argument("--totals-csv", type=Path,
                        help="Frozen official monthly totals CSV (no Excel runtime needed)")
    for flag in ("nationals", "output"):
        sectoral_monthly.add_argument(f"--{flag}", type=Path, required=True)
    micro = sectoral_cmd.add_parser("split-microdata", help="DANE monthly 13-to-14 split from actual CIIU4 GEIH microdata; missing months remain unavailable")
    micro.add_argument("--observations-csv",type=Path,required=True)
    micro.add_argument("--totals-csv",type=Path,required=True)
    micro.add_argument("--workbook",type=Path)
    micro.add_argument("--manifest",type=Path,help="Monthly source manifest: period,occupied,classification,characteristics")
    micro.add_argument("--output",type=Path,required=True)
    legacy_annex = sectoral_cmd.add_parser("historical-annexes", help="Inventory 2007-2014 official annexes, validate historic normalized observations; no microdata or smoothing")
    legacy_annex.add_argument("--recent-monthly",type=Path,required=True)
    legacy_annex.add_argument("--annex-csv",type=Path,help="Optional extracted historic annex observations with explicit time domain")
    legacy_annex.add_argument("--source-files",type=Path,help="Directory with original annex XLS files for SHA-256 verification")
    legacy_annex.add_argument("--output",type=Path,required=True)
    vintage = sectoral_cmd.add_parser("bridge-vintages", help="CIIU3 2001-2015 moving quarters -> 2015 CIIU4 overlap, source-aware; NO monthly promotion")
    for flag in ("historic-csv", "recent-monthly-csv", "recent-totals-csv", "nationals-csv", "source-xls", "output"):
        vintage.add_argument(f"--{flag}", type=Path, required=True)
    monthly_b = sectoral_cmd.add_parser("reconstruct-monthly", help="H11 experimental inverse moving 3-month sector shares; never rewrite observed monthly DANE data")
    for flag in ("rolling-csv", "recent-csv", "totals-csv", "nationals-csv", "output"):
        monthly_b.add_argument(f"--{flag}", type=Path, required=True)
    hom = sectoral_cmd.add_parser("homologate-historical", help="H11 1993-2001 experimental DANE 4-group September ENH retropolation into 15 categories; never rewrite H11 observations")
    for flag in ("dane-csv", "link-csv", "totals-csv", "mapping-csv", "output"):
        hom.add_argument(f"--{flag}", type=Path, required=True)
    hom.add_argument("--vintage", default="1958-2011")
    hom.add_argument("--lambda-smooth", dest="lambda_smooth", type=float, default=2.0)
    h12 = sectoral_cmd.add_parser("predict-departments", help="H12 noncanonical department-sector composition priors, rural structural sensitivity and audits")
    for flag in ("departments-csv", "nationals-csv", "population-csv", "historical-csv", "backcast-csv", "observed-csv", "recent-totals-csv", "output"):
        h12.add_argument(f"--{flag}", type=Path, required=True)
    h13 = sectoral_cmd.add_parser("reconcile-department-sectors", help="H13 experimental KL reconciliation of H12 department-sector matrices")
    for flag in ("priors-csv", "national-csv", "covariates-csv", "universe-csv", "output"):
        h13.add_argument(f"--{flag}", type=Path, required=True)
    h16 = sectoral_cmd.add_parser(
        "predict-monthly", help="H16 trained experimental territorial-sectoral predictor and full-universe reconciliation"
    )
    h16.add_argument("--bundle-root", type=Path, required=True, help="Frozen datos/2_procesamiento/sectorial_h16 with inputs/")
    h16.add_argument("--output", type=Path, required=True, help="New EMPTY working directory (no overwrite of frozen sources)")
    h16_audit = sectoral_cmd.add_parser(
        "validate-panel", help="Read-only H16 provenance, accounting and quality gate check"
    )
    h16_audit.add_argument("--bundle-root", type=Path, required=True, help="Directory containing inputs/ and outputs/")
    h17_export = sectoral_cmd.add_parser(
        "export-experimental", help="H17 separate departmental/national sectoral research tables, NEVER canonical"
    )
    h17_export.add_argument("--bundle-root", type=Path, required=True)
    h17_export.add_argument("--output", type=Path, required=True, help="New empty directory for noncanonical outputs")
    census = commands.add_parser("census-bridge", help="CNPV-2018 anchored, reversible GEIH/ICML transfer (experimental).")
    cs = census.add_subparsers(dest="census_command", required=True)
    cr = cs.add_parser("run", help="Build audit and alternative domain bridge without changing frozen labor inputs.")
    for flag in ("departments", "cities", "nationals", "census", "output"):
        cr.add_argument(f"--{flag}", type=Path, required=True)
    # H19 operational gates: read-only audits and staged (never published) updates.
    ops = commands.add_parser("operations", help="H19-H21: integrity, product freeze, monthly vintage and certification controls")
    op = ops.add_subparsers(dest="operations_command", required=True)
    pf = op.add_parser("preflight", help="Verify frozen H18 checksum and golden availability")
    pf.add_argument("--root", type=Path, required=True)
    pf.add_argument("--output", type=Path, required=True)
    pf.add_argument("--golden-dir", type=Path)
    upd = op.add_parser("stage-update", help="Check next-month candidate without publishing")
    for arg in ("previous", "candidate", "output"):
        upd.add_argument(f"--{arg}", type=Path, required=True)
    upd.add_argument("--keys", nargs="+", required=True)
    upd.add_argument("--quantities", nargs="+", required=True)
    upd.add_argument("--old-last-month", required=True)
    upd.add_argument("--new-last-month", required=True)
    upd.add_argument("--old-last-anchored-year", type=int, required=True)
    upd.add_argument("--new-last-anchored-year", type=int, required=True)
    upd.add_argument("--window-length", type=int, default=12)
    intake = op.add_parser("intake-geih", help="H22 stage official GEIH monthly XLSX without changing frozen products")
    intake.add_argument("--root", type=Path, required=True)
    intake.add_argument("--period", required=True)
    intake.add_argument("--annex", type=Path, help="Locally downloaded original GEIH monthly XLSX")
    intake.add_argument("--previous-annex", type=Path, help="Previous original XLSX to audit revisions")
    intake.add_argument("--output", type=Path, required=True, help="New EMPTY directory")
    pair = op.add_parser("check-monthly-sources", help="H22b verify declared reference-month synchronization (never authorizes a new vintage)")
    pair.add_argument("--period", required=True, help="ICML month YYYY-MM")
    pair.add_argument("--geih-annex", type=Path, help="Original GEIH monthly XLSX")
    pair.add_argument("--geih-month", help="Month VERIFIED in the GEIH annex, YYYY-MM")
    pair.add_argument("--social-annex", type=Path, help="Original Informal Employment and Social Security moving-3m annex")
    pair.add_argument("--social-start", help="First reference month VERIFIED in social annex, YYYY-MM")
    pair.add_argument("--social-end", help="Last reference month VERIFIED in social annex, YYYY-MM")
    pair.add_argument("--report", type=Path, help="New JSON report; never overwrites")
    social = op.add_parser('audit-social-annex', help='H35 validate source-content, calendar and accounting in original DANE Social Security XLSX')
    social.add_argument('--annex', type=Path, required=True)
    social.add_argument('--period', required=True)
    social.add_argument('--report', type=Path, help='NEW JSON file; never overwrites')
    trace = op.add_parser('audit-informality-origin', help='H35 audit 68 months of H9 national anchor against DANE monthly source Excel')
    trace.add_argument('--root', type=Path, required=True)
    trace.add_argument('--report', type=Path, help='NEW JSON file; never overwrites')
    h30 = op.add_parser("audit-historical-lineage", help="H30 audit Pareto donor study and archived Excel overlaps without changing inputs")
    h30.add_argument("--root", type=Path, required=True)
    h30.add_argument("--report", type=Path, required=True, help="NEW JSON report outside checkpoint")
    h31all = op.add_parser("prepare-all-excel", help="H31 stage all eight proven Excel-derived tables, without editing canonical data")
    h31all.add_argument("--root", type=Path, required=True)
    h31all.add_argument("--output", type=Path, required=True, help="NEW output directory outside frozen checkpoint")
    h31 = op.add_parser("prepare-historical-excel", help="H31 reproduce urban 12-month proxies, GEIH annual, and 7 monthly economic indicators from frozen XLSX")
    h31.add_argument("--root", type=Path, required=True)
    h31.add_argument("--output", type=Path, required=True, help="NEW staging directory outside checkpoint")
    source_xlsx = op.add_parser("prepare-excel", help="H29 derive audited population, GDP and sectoral CSVs from original XLSX")
    source_xlsx.add_argument("--root", type=Path, required=True)
    source_xlsx.add_argument("--output", type=Path, required=True, help="NEW staging directory OUTSIDE the checkpoint")
    source_check = op.add_parser("source-audit", help="Audit central historical source catalog and stage configurations")
    source_check.add_argument("--root", type=Path, required=True)
    source_sync = op.add_parser("source-sync", help="Preview or synchronize nonmonthly stage pointers from the catalog")
    source_sync.add_argument("--root", type=Path, required=True)
    source_sync.add_argument("--apply", action="store_true", help="Use ONLY on a copied new-vintage project")
    source_stage = op.add_parser("source-stage", help="Stage an updated file for a NEW vintage without activating it")
    source_stage.add_argument("--root", type=Path, required=True)
    source_stage.add_argument("--role", required=True)
    source_stage.add_argument("--file", type=Path, required=True)
    source_stage.add_argument("--period", required=True)
    source_stage.add_argument("--output", type=Path, required=True)
    integral = op.add_parser(
        "run-integral", help="H24 unified 2026-08 research validation or source recomputation"
    )
    integral.add_argument("--root", type=Path, required=True,
                          help="Frozen ICML 2.2.25+ checkpoint root")
    integral.add_argument("--output", type=Path, required=True,
                          help="NEW directory OUTSIDE the frozen checkpoint")
    integral.add_argument("--mode", choices=("verify", "recompute-components", "recompute"), default="verify",
                          help="verify: audit; recompute-components: H9/H16 with frozen labor; recompute: all stages from sources")
    integral.add_argument("--sources", type=Path,
                          help="Complete historical input tree for the seven labor stages")
    integral.add_argument("--configs", type=Path,
                          help="Seven canonical RC1 stage configs (default in checkpoint)")
    integral.add_argument("--informality-root", type=Path,
                          help="Complete immutable H9 auxiliary inputs tree")
    integral.add_argument("--resume-informality", type=Path,
                          help="Previously FINISHED and hash-verifiable H9 stage output")
    integral.add_argument("--resume-sectoral", type=Path,
                          help="Previously FINISHED and hash-verifiable H16 predictor output")
    pre = op.add_parser(
        "integral-preflight", help="H24 audit inputs needed to reexecute the frozen 2026-08 model"
    )
    pre.add_argument("--root", type=Path, required=True)
    pre.add_argument("--mode", choices=("verify", "recompute-components", "recompute"), default="recompute")
    pre.add_argument("--sources", type=Path)
    pre.add_argument("--configs", type=Path)
    pre.add_argument("--informality-root", type=Path)
    cycle = op.add_parser("monthly-cycle", help="H23 immutable monthly source intake and blocked production run plan")
    cycle.add_argument("--root", type=Path, required=True, help="Existing frozen ICML checkpoint root")
    cycle.add_argument("--period", required=True, help="Strictly next YYYY-MM month")
    cycle.add_argument("--geih-annex", type=Path)
    cycle.add_argument("--geih-month", help="GEIH declared reference month, verified against workbook")
    cycle.add_argument("--social-annex", type=Path)
    cycle.add_argument("--social-start", help="Declared first month of the moving quarter")
    cycle.add_argument("--social-end", help="Declared last month of the moving quarter")
    cycle.add_argument("--output", type=Path, required=True, help="New empty staging directory OUTSIDE checkpoint")
    cycle_verify = op.add_parser("verify-monthly-cycle", help="H23 check immutable intake and frozen product integrity")
    cycle_verify.add_argument("--root", type=Path, required=True)
    cycle_verify.add_argument("--cycle", type=Path, required=True)
    # H20 frozen-product delivery (non-official and non-destructive).
    vp = op.add_parser("verify-products", help="Audit SHA-256 for the eight H19 frozen products")
    vp.add_argument("--root", type=Path, required=True)
    vp.add_argument("--report", type=Path)
    fr = op.add_parser("freeze-products", help="Stage an immutable NON-OFFICIAL snapshot of the eight frozen products")
    fr.add_argument("--root", type=Path, required=True)
    fr.add_argument("--destination", type=Path, required=True)
    cert = op.add_parser("certify", help="H21 read-only frozen-product, Python lock and external RC1 golden readiness audit")
    cert.add_argument("--root", type=Path, required=True)
    cert.add_argument("--report", type=Path, required=True, help="NEW JSON output; refuses overwrites")
    cert.add_argument("--golden-dir", type=Path, help="External ORIGINAL RC1 golden tree only")
    _add_golden(commands)
    return parser


def _run_one(args: argparse.Namespace) -> int:
    from icml.pipeline.chain import new_run_root, run_stage
    stage = STAGES[args.command]
    run_root = new_run_root(args.runs_dir, args.run_id)
    upstream = {name: getattr(args, f"{name}_run") for name in stage.upstream}
    run_stage(
        args.command,
        args.config,
        args.sources if stage.reads_sources else None,
        upstream,
        run_root,
        args.run_id,
    )
    print(f"{args.command.capitalize()} stage written to {run_root}.")
    return EXIT_OK


def _golden(args: argparse.Namespace) -> int:
    catalog = load_catalog(args.catalog)
    if args.golden_command == "capture":
        manifest = capture_golden(args.legacy_root, catalog, args.destination)
        print(f"Captured {len(catalog.artifacts)} artifacts: {manifest}")
        return EXIT_OK
    issues = check_integrity(args.root, catalog)
    for issue in issues:
        print(
            f"FAIL {issue.artifact_id}: {issue.problem} ({issue.path})",
            file=sys.stderr,
        )
    print(f"Checked {len(catalog.artifacts)} artifacts, {len(issues)} issues.")
    return EXIT_INTEGRITY_FAILURE if issues else EXIT_OK


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and return the process exit code."""
    args = _build_parser().parse_args(argv)
    from icml.cli_delivery import COMMANDS as DELIVERY_COMMANDS

    if args.command in DELIVERY_COMMANDS:
        from icml.cli_delivery import run_command

        return run_command(args)
    from icml.cli_amigable import COMMANDS as FRIENDLY_COMMANDS

    if args.command in FRIENDLY_COMMANDS:
        from icml.cli_amigable import run_command as run_friendly

        return run_friendly(args)
    if args.command == "operations":
        import json
        if args.operations_command == "audit-historical-lineage":
            from icml.operations.historical_lineage import audit
            result = audit(args.root)
            if args.report.exists():
                raise FileExistsError(f"Audit report already exists: {args.report}")
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return EXIT_OK if result["status"] == "PASS" else EXIT_INTEGRITY_FAILURE
        if args.operations_command in ('audit-social-annex', 'audit-informality-origin'):
            if args.operations_command == 'audit-social-annex':
                from icml.operations.social_annex import inspect_social_annex
                result = inspect_social_annex(args.annex, args.period)
            else:
                from icml.operations.informality_lineage import audit_national_h9_lineage
                result = audit_national_h9_lineage(args.root)
            if args.report is not None:
                if args.report.exists():
                    raise FileExistsError(f'Already exists: {args.report}')
                args.report.parent.mkdir(parents=True, exist_ok=True)
                args.report.write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return EXIT_OK if result['status'].startswith('PASS') else EXIT_INTEGRITY_FAILURE
        if args.operations_command == "prepare-all-excel":
            from icml.operations.excel_staging import run as prepare_all
            result = prepare_all(args.root, args.output)
            print(json.dumps({"status":result["status"], "verified_generators":result["verified_generators"], "reference_month":result["reference_month"]}, indent=2))
            return EXIT_OK if result["status"] == "PASS" else EXIT_INTEGRITY_FAILURE
        if args.operations_command == "prepare-historical-excel":
            from icml.operations.excel_historical_sources import run as prepare_h31
            result = prepare_h31(args.root, args.output)
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return EXIT_OK if result["status"] == "PASS" else EXIT_INTEGRITY_FAILURE
        if args.operations_command == "prepare-excel":
            from icml.operations.excel_sources import run as prepare_excel_sources
            result = prepare_excel_sources(args.root, args.output, verify=True)
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return EXIT_OK if result["status"] == "PASS" else EXIT_INTEGRITY_FAILURE
        if args.operations_command in ("source-audit", "source-stage", "source-sync"):
            from icml.operations.source_catalog import audit_catalog, stage_new_source
            if args.operations_command == "source-audit":
                result = audit_catalog(args.root)
                print(json.dumps(result, indent=2, ensure_ascii=False))
                return EXIT_OK if result["status"] == "PASS" else EXIT_INTEGRITY_FAILURE
            if args.operations_command == "source-sync":
                from icml.operations.source_catalog import synchronize_stage_configs
                result = synchronize_stage_configs(args.root, apply=args.apply)
                print(json.dumps(result, indent=2, ensure_ascii=False))
                return EXIT_OK if result["status"] != "BLOCKED" else EXIT_INTEGRITY_FAILURE
            result = stage_new_source(args.root, args.role, args.file,
                                      args.output, args.period)
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return EXIT_OK
        if args.operations_command in ("run-integral", "integral-preflight"):
            from icml.operations.integral import preflight, run_integral
            if args.operations_command == "integral-preflight":
                result = preflight(args.root, args.mode, sources=args.sources,
                                   configs=args.configs, informality_root=args.informality_root)
                print(json.dumps(result, indent=2, ensure_ascii=False))
                return EXIT_OK if result["status"] == "READY" else EXIT_INTEGRITY_FAILURE
            result = run_integral(args.root, args.output, mode=args.mode,
                                  sources=args.sources, configs=args.configs,
                                  informality_root=args.informality_root,
                                  resume_informality=args.resume_informality,
                                  resume_sectoral=args.resume_sectoral)
            print(json.dumps({"status": result["status"],
                              "report": str(args.output / "integral_execution_report.json"),
                              "recalculated": result["recalculated_from_sources"]},
                             indent=2, ensure_ascii=False))
            return EXIT_OK if result["status"] in (
                "VERIFIED_EXISTING_VINTAGE_NOT_REEXECUTED",
                "RECOMPUTED_ALL_EIGHT_AUDITED",
                "RECOMPUTED_H9_H16_WITH_FROZEN_LABOR_AUDITED",
                "RECOMPUTED_H9_H16_FROM_VERIFIED_STAGE_RUNS",
            ) else EXIT_INTEGRITY_FAILURE
        if args.operations_command == "monthly-cycle":
            from icml.operations.monthly_cycle import prepare_monthly_cycle
            result = prepare_monthly_cycle(args.root, args.period, args.output,
                      args.geih_annex, args.social_annex, args.geih_month,
                      args.social_start, args.social_end)
            print(json.dumps(result, indent=2, ensure_ascii=False))
            # Deliberately return 2: source-only intake never clears computation gate.
            return EXIT_INTEGRITY_FAILURE
        if args.operations_command == "verify-monthly-cycle":
            from icml.operations.monthly_cycle import verify_monthly_cycle
            result = verify_monthly_cycle(args.root, args.cycle)
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return EXIT_OK if not result["issues"] else EXIT_INTEGRITY_FAILURE
        if args.operations_command in ("verify-products", "freeze-products"):
            from icml.operations.frozen_products import verify_products, freeze_products
            if args.operations_command == "verify-products":
                result = verify_products(args.root)
                if args.report:
                    if args.report.exists():
                        raise FileExistsError(f"Report exists: {args.report}")
                    args.report.parent.mkdir(parents=True, exist_ok=True)
                    args.report.write_text(json.dumps(result, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
                print(json.dumps(result, indent=2, ensure_ascii=False))
                return EXIT_OK if not result["issues"] else EXIT_INTEGRITY_FAILURE
            result = freeze_products(args.root, args.destination)
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return EXIT_OK
        if args.operations_command == "intake-geih":
            from icml.operations.geih_intake import prepare_intake
            result = prepare_intake(args.root, args.output, args.period, args.annex, args.previous_annex)
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return EXIT_OK if result["status"].startswith("STAGED") else EXIT_INTEGRITY_FAILURE
        if args.operations_command == "check-monthly-sources":
            from icml.operations.source_pair import check_monthly_sources
            result = check_monthly_sources(args.period, args.geih_annex, args.social_annex,
                    args.geih_month, args.social_start, args.social_end)
            if args.report:
                if args.report.exists():
                    raise FileExistsError(f"Report exists: {args.report}")
                args.report.parent.mkdir(parents=True, exist_ok=True)
                args.report.write_text(json.dumps(result, indent=2, ensure_ascii=False)+"\n",encoding="utf-8")
            print(json.dumps(result, indent=2, ensure_ascii=False))
            # Metadata coherence never passes the full quality gate.
            return EXIT_OK if result["status"].startswith("PAIR_CALENDAR_COHERENT") else EXIT_INTEGRITY_FAILURE
        if args.operations_command == "certify":
            from icml.operations.certification import write_report
            result = write_report(args.root, args.report, args.golden_dir)
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return EXIT_OK if result["release_gate"].startswith("ELIGIBLE") else EXIT_INTEGRITY_FAILURE
        from icml.operations.monthly_staging import preflight, stage_update
        from icml.pipeline.vintage import VintagePolicy
        if args.operations_command == "preflight":
            result = preflight(args.root, args.output, args.golden_dir)
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return EXIT_OK if result["status"].startswith("PASS") else EXIT_INTEGRITY_FAILURE
        old_policy = VintagePolicy(args.old_last_month, args.old_last_anchored_year, args.window_length)
        new_policy = VintagePolicy(args.new_last_month, args.new_last_anchored_year, args.window_length)
        result = stage_update(args.previous, args.candidate, args.output,
                              args.keys, args.quantities, old_policy, new_policy)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return EXIT_OK if result["status"].startswith("ACCEPTED") else EXIT_INTEGRITY_FAILURE
    if args.command == "sectoral" and args.sectoral_command == "audit-monthly":
        from icml.sectoral.monthly import run as sectoral_monthly_run
        r = sectoral_monthly_run(args.workbook, args.nationals, args.output, args.legacy_checks,
                observations_csv=args.observations_csv, totals_csv=args.totals_csv)
        print(f"DANE true monthly sector H10: {r['months']} months, "
              f"{r['monthly_observations']} group-months; 14-branch split NOT observed")
        return EXIT_OK
    if args.command == "sectoral" and args.sectoral_command == "split-microdata":
        from icml.sectoral.microdata import run as split_microdata_run
        r=split_microdata_run(observations_csv=args.observations_csv,totals_csv=args.totals_csv,
              output=args.output,manifest_csv=args.manifest,workbook=args.workbook)
        print(f"DANE monthly H10 microdata split: {r['month_count_validated_14_estimated']} of {r['month_count_official_13']} months supported; no invented observations")
        return EXIT_OK
    if args.command == "sectoral" and args.sectoral_command == "historical-annexes":
        from icml.sectoral.historical_annexes import run as run_historics
        r=run_historics(args.output,args.recent_monthly,args.annex_csv,args.source_files)
        print(f"Historical DANE H10: {r['published_annex_entries_2007_2014']} listings, "
              f"{r['historic_verified_rows']} verified rows; state {r['status']}")
        return EXIT_OK
    if args.command == "sectoral" and args.sectoral_command == "bridge-vintages":
        from icml.sectoral.vintage_bridge import run as run_vintage
        report=run_vintage(historic_csv=args.historic_csv,
            recent_monthly_csv=args.recent_monthly_csv,
            recent_totals_csv=args.recent_totals_csv,nationals_csv=args.nationals_csv,
            source_xls=args.source_xls,output=args.output)
        print(f"Sectorial H10 vintage bridge: {report['source_reference_periods']} official rolling windows, "
              f"{report['historical_14_experimental_rolling_window_rows']} estimated rows; "
              "NO historic directly observed CIIU4 monthly 14-sector observations.")
        return EXIT_OK
    if args.command == "sectoral" and args.sectoral_command == "reconstruct-monthly":
        from icml.sectoral.monthly_backcast import run as backcast_run
        report=backcast_run(rolling_csv=args.rolling_csv, recent_csv=args.recent_csv,
           totals_csv=args.totals_csv, nationals_csv=args.nationals_csv, output=args.output)
        print(f"Sectorial H11: {report['historical_months_estimated']} estimated historic months, "
              f"{report['windows_observed']} official rolling windows; NOT DIRECT DANE MONTHLY OBSERVATIONS")
        return EXIT_OK
    if args.command == "sectoral" and args.sectoral_command == "homologate-historical":
        from icml.sectoral.historical_homologation import run as historical_homologate
        q = historical_homologate(dane_csv=args.dane_csv, link_csv=args.link_csv,
                totals_csv=args.totals_csv, mapping_csv=args.mapping_csv,
                output=args.output, vintage=args.vintage, lam=args.lambda_smooth)
        print(f"H11 historical 1993-2001: {q['months']} estimated months, "
              f"{q['branches']} H11 categories, {q['rows']} exploratory rows across "
              "three scenarios and two universes; NOT OFFICIAL MONTHLY DATA")
        return EXIT_OK
    if args.command == "sectoral" and args.sectoral_command == "predict-departments":
        from icml.sectoral.departmental_prior import run as run_h12
        result = run_h12(args.departments_csv, args.nationals_csv,
            args.population_csv, args.historical_csv, args.backcast_csv,
            args.observed_csv, args.recent_totals_csv, args.output)
        print(f"H12: {result['candidate_rows']} noncanonical prior rows, "
              f"{result['departments']} territories, {result['months']} months; "
              "NO SUBNATIONAL SECTOR LABEL VALIDATION; H13 pending")
        return EXIT_OK
    if args.command == "sectoral" and args.sectoral_command == "reconcile-department-sectors":
        from icml.sectoral.reconciliation import run as run_h13
        result = run_h13(args.priors_csv, args.national_csv, args.covariates_csv,
                         args.universe_csv, args.output)
        print(f"H13: {result['rows']} noncanonical reconciled rows; "
              f"max full-sector margin residual {result['max_full_national_error_persons']:.6g} persons; "
              "DEPARTMENT-SECTOR VALIDATION PENDING")
        return EXIT_OK
    if args.command == "sectoral" and args.sectoral_command == "validate-panel":
        from icml.sectoral.integral import validate_bundle
        import json
        report=validate_bundle(args.bundle_root)
        print(json.dumps(report,ensure_ascii=False,indent=2))
        return EXIT_OK
    if args.command == "sectoral" and args.sectoral_command == "predict-monthly":
        from icml.sectoral.integral import run_predictor
        import json
        report=run_predictor(args.bundle_root,args.output)
        print(json.dumps(report,ensure_ascii=False,indent=2))
        return EXIT_OK
    if args.command == "sectoral" and args.sectoral_command == "export-experimental":
        from icml.sectoral.integral import export_experimental
        import json
        report=export_experimental(args.bundle_root,args.output)
        print(json.dumps(report,ensure_ascii=False,indent=2))
        return EXIT_OK
    if args.command == "census-bridge":
        from icml.census.bridge import run as run_census_bridge
        result = run_census_bridge(args.departments,args.cities,args.nationals,args.census,args.output)
        print(f"CNPV bridge: {result['territorial_rows']} rows, 9 census anchors; labor candidates noncanonical.")
        return EXIT_OK
    if args.command == "run":
        from icml.pipeline.chain import run_all
        root = run_all(args.configs, args.sources, args.runs_dir, args.run_id, census_source=args.census_source)
        print(f"Full run written to {root} (see run.json).")
        return EXIT_OK
    if args.command == "informality" and args.informality_command == "extract":
        from icml.informality.extract_annexes import run as extract_annexes
        report = extract_annexes(args.old, args.new, args.output)
        print(f"Informality annex extraction: {report['n_observations']} rolling windows")
        return EXIT_OK
    if args.command == "informality" and args.informality_command == "historical":
        from icml.informality.historical import run as historical_run
        result = historical_run(args.sources, args.nationals, args.recent, args.ilo, args.output)
        print(f"Historical experiment: {result['months']} months, two national series; not canonical.")
        return EXIT_OK
    if args.command == "informality" and args.informality_command == "audit-historical":
        from icml.informality.quality_gate import audit
        result = audit(args.candidate, args.cities_labor, args.nationals_labor, args.output,
                       previous_national=args.previous_national)
        print(f"Informality gate: {result['status']}; flags={result['n_flags']}; gt200pct={result['n_gt_200pct_equivalent']}")
        return EXIT_OK if not result["status"].startswith("NOT_CERTIFIED") else EXIT_INTEGRITY_FAILURE
    if args.command == "informality" and args.informality_command == "sequential":
        from icml.informality.sequential import run as sequential_run
        result = sequential_run(args.sources, args.cities, args.departments,
                                args.nationals, args.recent, args.anchors13, args.output,
                                args.config)
        print(f"Sequential experimental informal reconstruction: {result['n_13']} 13-area, "
              f"{result['n_national']} national, {result['n_33']} urban rows; NOT CANONICAL.")
        return EXIT_OK
    if args.command == "informality" and args.informality_command == "consolidate-features":
        from icml.informality.feature_consolidation import run as consolidate_features
        result = consolidate_features(args.cities, args.departments, args.nationals,
            args.urban_informality, args.population, args.modeling_config, args.output)
        print(f"Informality feature checkpoint: {result['cities']} urban, "
              f"{result['departments']} departmental, {result['folds']} folds; "
              "EXPERIMENTAL, NO TRAINING PERFORMED.")
        return EXIT_OK
    if args.command == "informality" and args.informality_command == "calibrate-national":
        from icml.informality.national_closure import run as calibrate_national
        report = calibrate_national(
            args.departments, args.predictions, args.national, args.output,
            rate_col=args.rate_column, label=args.label,
            allow_missing_months=args.allow_missing_months,
        )
        print(f"Experimental national closure: {report['processed_months']} months; "
              f"{report['blocked_months']} blocked; NOT CANONICAL.")
        return EXIT_OK
    if args.command == "informality" and args.informality_command == "audit-postclosure":
        from icml.informality.postclosure_evaluation import run as audit_postclosure
        report = audit_postclosure(args.closures, args.departments, args.national,
                                   args.output, sensitivity_pp=args.sensitivity_pp)
        print(f"Postclosure assessment: {report['n_common_months']} matched months; "
              "NOT CERTIFIED FOR PUBLICATION.")
        return EXIT_OK
    if args.command == "informality" and args.informality_command == "compare-calibrators":
        from icml.informality.constrained_frontier import run as compare_calibrators
        report = compare_calibrators(args.closures, args.departments, args.national, args.output)
        print(f"Five-way constrained calibration: {len(report['summary'])} experiments; "
              "EXPERIMENTAL, NOT CANONICAL.")
        return EXIT_OK
    if args.command == "informality" and args.informality_command == "audit-national-bridge":
        from icml.informality.national_bridge_stress import run as audit_bridge
        report = audit_bridge(labor_path=args.departments,
            national_labor_path=args.nationals, source_path=args.sources,
            recent_path=args.recent, anchors_path=args.anchors13,
            cities13_path=args.cities13, closure_root=args.closures,
            output=args.output)
        print(f"National bridge sensitivity: {report['n_calibrated_rows']} "
              "experimental rows; NOT CANONICAL.")
        return EXIT_OK
    if args.command == "informality" and args.informality_command == "census-transfer-mlp":
        from icml.informality.census_transfer_experiment import run as census_transfer_mlp
        report = census_transfer_mlp(args.features_dir, args.census_bridge,
            args.census_anchors, args.model_dir, args.previous_predictions,
            args.national, args.output, refit=not args.skip_refit)
        print(f"CNPV single MLP transfer: {report['months']} months, "
              f"{report['rows']} comparison rows; NOT CANONICAL")
        return EXIT_OK
    if args.command == "informality" and args.informality_command == "finalize-block":
        from icml.informality.finalize_block import run as finalize_informality
        from icml.informality.regime_splice import RegimeSplice
        splice=RegimeSplice.from_toml(Path(args.root)/"configs/rc1/regime_splice.toml")
        report=finalize_informality(args.root,args.output,gap_method=args.gap_method,splice=splice)
        print(f"Completed reconstructed informality candidate: {report['urban_rows']} cities, "
              f"{report['department_rows']} departments, {report['national_rows']} nationals; "
              "numerical closure passed; independent statistical certification PENDING.")
        return EXIT_OK
    if args.command == "informality" and args.informality_command == "audit-mlp":
        from icml.informality.mlp_quality import audit as audit_mlp
        result = audit_mlp(args.experiment, args.national)
        print(f"MLP quality gate: {result['status']}, national gap "
              f"{result['max_abs_national_gap_pp']:.2f} pp. NOT CANONICAL.")
        return EXIT_INTEGRITY_FAILURE
    if args.command == "informality" and args.informality_command == "fit-mlp":
        from icml.informality.mlp_experiment import run as fit_informality_mlp
        result = fit_informality_mlp(args.features_folder, args.output,
                                    args.folds_per_definition, args.epochs)
        print(f"Experimental MLP: {result['n_folds']} folds, "
              f"{result['n_predictions']} departmental candidate rows; NOT CANONICAL.")
        return EXIT_OK
    if args.command == "informality" and args.informality_command == "urban-history":
        from icml.informality.urban_backcast import run as urban_history_run
        result = urban_history_run(args.sources, args.cities, args.nationals,
                                   args.recent, args.anchors13, args.anchors_cities,
                                   args.output)
        print(f"Urban-first DANE candidate: {result['urban_rows']} urban + "
              f"{result['national_rows']} national rows; NOT CANONICAL.")
        return EXIT_OK
    if args.command in STAGES:
        return _run_one(args)
    return _golden(args)


if __name__ == "__main__":
    raise SystemExit(main())
