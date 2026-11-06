"""Expert commands of the sectoral block and the census bridge.

All of them are research tools: they never rewrite observed DANE data and
none of their outputs is canonical.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from icml.cli._common import EXIT_OK, Commands, add_path_flags, print_json


def register(commands: Commands) -> None:
    """Register ``sectoral`` and ``census-bridge`` on the main parser."""
    sectoral = commands.add_parser("sectoral", help="Real-month DANE sectoral sources, bridges and experimental priors")
    sub = sectoral.add_subparsers(dest="sectoral_command", required=True)

    monthly = sub.add_parser("audit-monthly", help="Extract observed calendar months; never smooth rolling quarters")
    monthly.add_argument("--legacy-checks", type=Path)
    monthly.add_argument("--workbook", type=Path,
                         help="Original DANE annex; direct extraction requires artifact_tool; can also verify CSV hash")
    monthly.add_argument("--observations-csv", type=Path, help="Frozen 13-group monthly normalized CSV (no Excel runtime needed)")
    monthly.add_argument("--totals-csv", type=Path, help="Frozen official monthly totals CSV (no Excel runtime needed)")
    add_path_flags(monthly, "nationals", "output")
    monthly.set_defaults(handler=_audit_monthly)

    micro = sub.add_parser("split-microdata",
                           help="DANE monthly 13-to-14 split from actual CIIU4 GEIH microdata; missing months remain unavailable")
    add_path_flags(micro, "observations-csv", "totals-csv", "output")
    micro.add_argument("--workbook", type=Path)
    micro.add_argument("--manifest", type=Path, help="Monthly source manifest: period,occupied,classification,characteristics")
    micro.set_defaults(handler=_split_microdata)

    annexes = sub.add_parser("historical-annexes",
                             help="Inventory 2007-2014 official annexes, validate historic normalized observations; no microdata or smoothing")
    add_path_flags(annexes, "recent-monthly", "output")
    annexes.add_argument("--annex-csv", type=Path, help="Optional extracted historic annex observations with explicit time domain")
    annexes.add_argument("--source-files", type=Path, help="Directory with original annex XLS files for SHA-256 verification")
    annexes.set_defaults(handler=_historical_annexes)

    vintage = sub.add_parser("bridge-vintages",
                             help="CIIU3 2001-2015 moving quarters -> 2015 CIIU4 overlap, source-aware; NO monthly promotion")
    add_path_flags(vintage, "historic-csv", "recent-monthly-csv", "recent-totals-csv", "nationals-csv", "source-xls", "output")
    vintage.set_defaults(handler=_bridge_vintages)

    backcast = sub.add_parser("reconstruct-monthly",
                              help="Experimental inverse of moving 3-month sector shares; never rewrite observed monthly DANE data")
    add_path_flags(backcast, "rolling-csv", "recent-csv", "totals-csv", "nationals-csv", "output")
    backcast.set_defaults(handler=_reconstruct_monthly)

    homologation = sub.add_parser("homologate-historical",
                                  help="1993-2001 experimental DANE 4-group September ENH retropolation into 15 categories")
    add_path_flags(homologation, "dane-csv", "link-csv", "totals-csv", "mapping-csv", "output")
    homologation.add_argument("--vintage", default="1958-2011")
    homologation.add_argument("--lambda-smooth", dest="lambda_smooth", type=float, default=2.0)
    homologation.set_defaults(handler=_homologate_historical)

    priors = sub.add_parser("predict-departments",
                            help="Noncanonical department-sector composition priors, rural structural sensitivity and audits")
    add_path_flags(priors, "departments-csv", "nationals-csv", "population-csv", "historical-csv", "backcast-csv",
                   "observed-csv", "recent-totals-csv", "output")
    priors.set_defaults(handler=_predict_departments)

    reconcile = sub.add_parser("reconcile-department-sectors",
                               help="Experimental KL reconciliation of department-sector prior matrices")
    add_path_flags(reconcile, "priors-csv", "national-csv", "covariates-csv", "universe-csv", "output")
    reconcile.set_defaults(handler=_reconcile_department_sectors)

    predict = sub.add_parser("predict-monthly",
                             help="Trained experimental territorial-sectoral predictor and full-universe reconciliation")
    predict.add_argument("--bundle-root", type=Path, required=True, help="Frozen sectoral bundle with inputs/")
    predict.add_argument("--output", type=Path, required=True, help="New EMPTY working directory (no overwrite of frozen sources)")
    predict.set_defaults(handler=_predict_monthly)

    validate = sub.add_parser("validate-panel", help="Read-only provenance, accounting and quality gate check of a sectoral bundle")
    validate.add_argument("--bundle-root", type=Path, required=True, help="Directory containing inputs/ and outputs/")
    validate.set_defaults(handler=_validate_panel)

    export = sub.add_parser("export-experimental",
                            help="Separate departmental/national sectoral research tables, NEVER canonical")
    export.add_argument("--bundle-root", type=Path, required=True)
    export.add_argument("--output", type=Path, required=True, help="New empty directory for noncanonical outputs")
    export.set_defaults(handler=_export_experimental)

    census = commands.add_parser("census-bridge", help="CNPV-2018 anchored, reversible GEIH/ICML transfer (experimental).")
    census_sub = census.add_subparsers(dest="census_command", required=True)
    run = census_sub.add_parser("run", help="Build audit and alternative domain bridge without changing frozen labor inputs.")
    add_path_flags(run, "departments", "cities", "nationals", "census", "output")
    run.set_defaults(handler=_census_bridge)


def _audit_monthly(args: argparse.Namespace) -> int:
    from icml.sectoral.monthly import run

    r = run(args.workbook, args.nationals, args.output, args.legacy_checks,
            observations_csv=args.observations_csv, totals_csv=args.totals_csv)
    print(f"DANE true monthly sectors: {r['months']} months, "
          f"{r['monthly_observations']} group-months; 14-branch split NOT observed")
    return EXIT_OK


def _split_microdata(args: argparse.Namespace) -> int:
    from icml.sectoral.microdata import run

    r = run(observations_csv=args.observations_csv, totals_csv=args.totals_csv,
            output=args.output, manifest_csv=args.manifest, workbook=args.workbook)
    print(f"DANE monthly microdata split: {r['month_count_validated_14_estimated']} of "
          f"{r['month_count_official_13']} months supported; no invented observations")
    return EXIT_OK


def _historical_annexes(args: argparse.Namespace) -> int:
    from icml.sectoral.historical_annexes import run

    r = run(args.output, args.recent_monthly, args.annex_csv, args.source_files)
    print(f"Historical DANE annexes: {r['published_annex_entries_2007_2014']} listings, "
          f"{r['historic_verified_rows']} verified rows; state {r['status']}")
    return EXIT_OK


def _bridge_vintages(args: argparse.Namespace) -> int:
    from icml.sectoral.vintage_bridge import run

    report = run(historic_csv=args.historic_csv, recent_monthly_csv=args.recent_monthly_csv,
                 recent_totals_csv=args.recent_totals_csv, nationals_csv=args.nationals_csv,
                 source_xls=args.source_xls, output=args.output)
    print(f"Sectoral vintage bridge: {report['source_reference_periods']} official rolling windows, "
          f"{report['historical_14_experimental_rolling_window_rows']} estimated rows; "
          "NO historic directly observed CIIU4 monthly 14-sector observations.")
    return EXIT_OK


def _reconstruct_monthly(args: argparse.Namespace) -> int:
    from icml.sectoral.monthly_backcast import run

    report = run(rolling_csv=args.rolling_csv, recent_csv=args.recent_csv, totals_csv=args.totals_csv,
                 nationals_csv=args.nationals_csv, output=args.output)
    print(f"Sectoral monthly backcast: {report['historical_months_estimated']} estimated historic months, "
          f"{report['windows_observed']} official rolling windows; NOT DIRECT DANE MONTHLY OBSERVATIONS")
    return EXIT_OK


def _homologate_historical(args: argparse.Namespace) -> int:
    from icml.sectoral.historical_homologation import run

    q = run(dane_csv=args.dane_csv, link_csv=args.link_csv, totals_csv=args.totals_csv,
            mapping_csv=args.mapping_csv, output=args.output, vintage=args.vintage, lam=args.lambda_smooth)
    print(f"Historical homologation 1993-2001: {q['months']} estimated months, "
          f"{q['branches']} categories, {q['rows']} exploratory rows across "
          "three scenarios and two universes; NOT OFFICIAL MONTHLY DATA")
    return EXIT_OK


def _predict_departments(args: argparse.Namespace) -> int:
    from icml.sectoral.departmental_prior import run

    result = run(args.departments_csv, args.nationals_csv, args.population_csv, args.historical_csv,
                 args.backcast_csv, args.observed_csv, args.recent_totals_csv, args.output)
    print(f"Departmental priors: {result['candidate_rows']} noncanonical prior rows, "
          f"{result['departments']} territories, {result['months']} months; "
          "NO SUBNATIONAL SECTOR LABEL VALIDATION; reconciliation pending")
    return EXIT_OK


def _reconcile_department_sectors(args: argparse.Namespace) -> int:
    from icml.sectoral.reconciliation import run

    result = run(args.priors_csv, args.national_csv, args.covariates_csv, args.universe_csv, args.output)
    print(f"Department-sector reconciliation: {result['rows']} noncanonical reconciled rows; "
          f"max full-sector margin residual {result['max_full_national_error_persons']:.6g} persons; "
          "DEPARTMENT-SECTOR VALIDATION PENDING")
    return EXIT_OK


def _validate_panel(args: argparse.Namespace) -> int:
    from icml.sectoral.integral import validate_bundle

    print_json(validate_bundle(args.bundle_root))
    return EXIT_OK


def _predict_monthly(args: argparse.Namespace) -> int:
    from icml.sectoral.integral import run_predictor

    print_json(run_predictor(args.bundle_root, args.output))
    return EXIT_OK


def _export_experimental(args: argparse.Namespace) -> int:
    from icml.sectoral.integral import export_experimental

    print_json(export_experimental(args.bundle_root, args.output))
    return EXIT_OK


def _census_bridge(args: argparse.Namespace) -> int:
    from icml.census.bridge import run

    result = run(args.departments, args.cities, args.nationals, args.census, args.output)
    print(f"CNPV bridge: {result['territorial_rows']} rows, 9 census anchors; labor candidates noncanonical.")
    return EXIT_OK
