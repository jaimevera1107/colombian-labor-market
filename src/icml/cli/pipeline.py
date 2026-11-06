"""Expert commands over the stage pipeline.

* ``icml run`` executes every stage from the DANE sources to the products;
* ``icml <stage> run`` executes one stage on top of completed upstream runs
  (``--national-run``, ``--urban-run``, ...);
* ``icml informality <experiment>`` runs the audited informality
  experiments (none of them is canonical);
* ``icml golden capture|verify`` manages the RC1 reference set.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from icml.cli._common import EXIT_INTEGRITY_FAILURE, EXIT_OK, Commands, add_path_flags
from icml.layout import CONFIGS_DIR, GOLDEN_CATALOG
from icml.pipeline.stage_registry import STAGE_SPECS as STAGES

DEFAULT_CATALOG = Path(GOLDEN_CATALOG)


def register(commands: Commands) -> None:
    """Register ``run``, the stage commands, ``informality`` extras and ``golden``."""
    full = commands.add_parser("run", help="Run every stage, from sources to products.")
    full.add_argument("--configs", type=Path, required=True, help="Folder with the stage TOML files.")
    full.add_argument("--sources", type=Path, required=True)
    full.add_argument("--runs-dir", type=Path, required=True)
    full.add_argument("--run-id", required=True)
    full.add_argument("--census-source", type=Path, default=None,
                      help="Optional CNPV 2018 adjusted nine capitals CSV (post-quality audit stage).")
    full.set_defaults(handler=_run_all)

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
        run.set_defaults(handler=_run_one)
        if name == "informality":
            _register_informality(sub)

    _register_golden(commands)


# ----------------------------------------------------------------------------- stages


def _run_all(args: argparse.Namespace) -> int:
    from icml.pipeline.chain import run_all

    root = run_all(args.configs, args.sources, args.runs_dir, args.run_id, census_source=args.census_source)
    print(f"Full run written to {root} (see run.json).")
    return EXIT_OK


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


# ----------------------------------------------------------------------------- informality experiments


def _register_informality(sub: Commands) -> None:
    extract = sub.add_parser("extract", help="Extract the original DANE informality annexes.")
    add_path_flags(extract, "old", "new", "output")
    extract.set_defaults(handler=_extract)

    history = sub.add_parser("historical", help="Build audited experimental 1993-2026 national history.")
    add_path_flags(history, "sources", "nationals", "recent", "ilo", "output")
    history.set_defaults(handler=_historical)

    urban_history = sub.add_parser("urban-history", help="DANE-only urban-first informality backcast, isolated candidate.")
    add_path_flags(urban_history, "sources", "cities", "nationals", "recent", "anchors13", "anchors-cities", "output")
    urban_history.set_defaults(handler=_urban_history)

    sequential = sub.add_parser("sequential", help="13 areas -> national -> 23 cities -> 33 signals and baseline (experimental).")
    add_path_flags(sequential, "sources", "cities", "departments", "nationals", "recent", "anchors13", "output", "config")
    sequential.set_defaults(handler=_sequential)

    consolidate = sub.add_parser(
        "consolidate-features",
        help="Consolidate original informality feature families with labor-stage fold-safe clusters.",
    )
    add_path_flags(consolidate, "cities", "departments", "nationals", "urban-informality", "population", "modeling-config", "output")
    consolidate.set_defaults(handler=_consolidate_features)

    calibration = sub.add_parser(
        "calibrate-national",
        help="Experimental original-informed calibration of departmental informal shares to national universes.",
    )
    add_path_flags(calibration, "departments", "predictions", "national", "output")
    calibration.add_argument("--rate-column", required=True)
    calibration.add_argument("--label", required=True)
    calibration.add_argument("--allow-missing-months", action="store_true")
    calibration.set_defaults(handler=_calibrate_national)

    post = sub.add_parser("audit-postclosure", help="Read-only comparison of candidate MLP + national calibration.")
    add_path_flags(post, "closures", "departments", "national", "output")
    post.add_argument("--sensitivity-pp", type=float, default=1.0)
    post.set_defaults(handler=_audit_postclosure)

    frontier = sub.add_parser(
        "compare-calibrators",
        help="Experimental five-way constrained national calibration comparison (read-only priors).",
    )
    add_path_flags(frontier, "closures", "departments", "national", "output")
    frontier.set_defaults(handler=_compare_calibrators)

    bridge_stress = sub.add_parser(
        "audit-national-bridge",
        help="Read-only national bridge, two-domain stress and MLP-2020 diagnostic.",
    )
    add_path_flags(bridge_stress, "departments", "nationals", "sources", "recent", "anchors13", "cities13", "closures", "output")
    bridge_stress.set_defaults(handler=_audit_national_bridge)

    transfer = sub.add_parser(
        "census-transfer-mlp",
        help="CNPV-2018 transfer experiment: one residual MLP, full vs GEIH projection, no canonical edits.",
    )
    add_path_flags(transfer, "features-dir", "census-bridge", "census-anchors", "model-dir", "previous-predictions", "national", "output")
    transfer.add_argument("--skip-refit", action="store_true",
                          help="Reuse the frozen model instead of performing an identical-training control fit")
    transfer.set_defaults(handler=_census_transfer_mlp)

    close_block = sub.add_parser(
        "finalize-block",
        help="Complete the three noncanonical informality bases with one MLP and CNPV GEIH transfer.",
    )
    close_block.add_argument("--root", required=True, type=Path, help="Complete checkpoint folder (immutable inputs).")
    close_block.add_argument("--output", required=True, type=Path)
    close_block.add_argument("--gap-method", choices=("interpolated", "seasonal_2019", "urban_shock"), default="interpolated")
    close_block.set_defaults(handler=_finalize_block)

    mlp_gate = sub.add_parser("audit-mlp", help="Read-only quality gate for experimental MLP.")
    add_path_flags(mlp_gate, "experiment", "national")
    mlp_gate.set_defaults(handler=_audit_mlp)

    mlp = sub.add_parser("fit-mlp", help="Audit and fit original residual informality MLP (experimental).")
    add_path_flags(mlp, "features-folder", "output")
    mlp.add_argument("--epochs", type=int, default=120)
    mlp.add_argument("--folds-per-definition", type=int, default=5)
    mlp.set_defaults(handler=_fit_mlp)

    audit = sub.add_parser("audit-historical", help="Audit 13→national→23→ML informality candidate (read-only).")
    add_path_flags(audit, "candidate", "cities-labor", "nationals-labor", "output")
    audit.add_argument("--previous-national", type=Path)
    audit.set_defaults(handler=_audit_historical)


def _extract(args: argparse.Namespace) -> int:
    from icml.informality.extract_annexes import run as extract_annexes

    report = extract_annexes(args.old, args.new, args.output)
    print(f"Informality annex extraction: {report['n_observations']} rolling windows")
    return EXIT_OK


def _historical(args: argparse.Namespace) -> int:
    from icml.informality.historical import run as historical_run

    result = historical_run(args.sources, args.nationals, args.recent, args.ilo, args.output)
    print(f"Historical experiment: {result['months']} months, two national series; not canonical.")
    return EXIT_OK


def _urban_history(args: argparse.Namespace) -> int:
    from icml.informality.urban_backcast import run as urban_history_run

    result = urban_history_run(args.sources, args.cities, args.nationals, args.recent,
                               args.anchors13, args.anchors_cities, args.output)
    print(f"Urban-first DANE candidate: {result['urban_rows']} urban + "
          f"{result['national_rows']} national rows; NOT CANONICAL.")
    return EXIT_OK


def _sequential(args: argparse.Namespace) -> int:
    from icml.informality.sequential import run as sequential_run

    result = sequential_run(args.sources, args.cities, args.departments, args.nationals,
                            args.recent, args.anchors13, args.output, args.config)
    print(f"Sequential experimental informal reconstruction: {result['n_13']} 13-area, "
          f"{result['n_national']} national, {result['n_33']} urban rows; NOT CANONICAL.")
    return EXIT_OK


def _consolidate_features(args: argparse.Namespace) -> int:
    from icml.informality.feature_consolidation import run as consolidate_features

    result = consolidate_features(args.cities, args.departments, args.nationals,
                                  args.urban_informality, args.population, args.modeling_config, args.output)
    print(f"Informality feature checkpoint: {result['cities']} urban, "
          f"{result['departments']} departmental, {result['folds']} folds; "
          "EXPERIMENTAL, NO TRAINING PERFORMED.")
    return EXIT_OK


def _calibrate_national(args: argparse.Namespace) -> int:
    from icml.informality.national_closure import run as calibrate_national

    report = calibrate_national(
        args.departments, args.predictions, args.national, args.output,
        rate_col=args.rate_column, label=args.label, allow_missing_months=args.allow_missing_months,
    )
    print(f"Experimental national closure: {report['processed_months']} months; "
          f"{report['blocked_months']} blocked; NOT CANONICAL.")
    return EXIT_OK


def _audit_postclosure(args: argparse.Namespace) -> int:
    from icml.informality.postclosure_evaluation import run as audit_postclosure

    report = audit_postclosure(args.closures, args.departments, args.national, args.output,
                               sensitivity_pp=args.sensitivity_pp)
    print(f"Postclosure assessment: {report['n_common_months']} matched months; NOT CERTIFIED FOR PUBLICATION.")
    return EXIT_OK


def _compare_calibrators(args: argparse.Namespace) -> int:
    from icml.informality.constrained_frontier import run as compare_calibrators

    report = compare_calibrators(args.closures, args.departments, args.national, args.output)
    print(f"Five-way constrained calibration: {len(report['summary'])} experiments; EXPERIMENTAL, NOT CANONICAL.")
    return EXIT_OK


def _audit_national_bridge(args: argparse.Namespace) -> int:
    from icml.informality.national_bridge_stress import run as audit_bridge

    report = audit_bridge(labor_path=args.departments, national_labor_path=args.nationals,
                          source_path=args.sources, recent_path=args.recent, anchors_path=args.anchors13,
                          cities13_path=args.cities13, closure_root=args.closures, output=args.output)
    print(f"National bridge sensitivity: {report['n_calibrated_rows']} experimental rows; NOT CANONICAL.")
    return EXIT_OK


def _census_transfer_mlp(args: argparse.Namespace) -> int:
    from icml.informality.census_transfer_experiment import run as census_transfer_mlp

    report = census_transfer_mlp(args.features_dir, args.census_bridge, args.census_anchors, args.model_dir,
                                 args.previous_predictions, args.national, args.output, refit=not args.skip_refit)
    print(f"CNPV single MLP transfer: {report['months']} months, {report['rows']} comparison rows; NOT CANONICAL")
    return EXIT_OK


def _finalize_block(args: argparse.Namespace) -> int:
    from icml.informality.finalize_block import run as finalize_informality
    from icml.informality.regime_splice import RegimeSplice

    splice = RegimeSplice.from_toml(Path(args.root) / CONFIGS_DIR / "regime_splice.toml")
    report = finalize_informality(args.root, args.output, gap_method=args.gap_method, splice=splice)
    print(f"Completed reconstructed informality candidate: {report['urban_rows']} cities, "
          f"{report['department_rows']} departments, {report['national_rows']} nationals; "
          "numerical closure passed; independent statistical certification PENDING.")
    return EXIT_OK


def _audit_mlp(args: argparse.Namespace) -> int:
    from icml.informality.mlp_quality import audit as audit_mlp

    result = audit_mlp(args.experiment, args.national)
    print(f"MLP quality gate: {result['status']}, national gap {result['max_abs_national_gap_pp']:.2f} pp. NOT CANONICAL.")
    # The experimental MLP never clears the gate on its own.
    return EXIT_INTEGRITY_FAILURE


def _fit_mlp(args: argparse.Namespace) -> int:
    from icml.informality.mlp_experiment import run as fit_informality_mlp

    result = fit_informality_mlp(args.features_folder, args.output, args.folds_per_definition, args.epochs)
    print(f"Experimental MLP: {result['n_folds']} folds, {result['n_predictions']} departmental candidate rows; NOT CANONICAL.")
    return EXIT_OK


def _audit_historical(args: argparse.Namespace) -> int:
    from icml.informality.quality_gate import audit

    result = audit(args.candidate, args.cities_labor, args.nationals_labor, args.output,
                   previous_national=args.previous_national)
    print(f"Informality gate: {result['status']}; flags={result['n_flags']}; gt200pct={result['n_gt_200pct_equivalent']}")
    return EXIT_OK if not result["status"].startswith("NOT_CERTIFIED") else EXIT_INTEGRITY_FAILURE


# ----------------------------------------------------------------------------- golden


def _register_golden(commands: Commands) -> None:
    golden = commands.add_parser("golden", help="RC1 golden reference set")
    golden_commands = golden.add_subparsers(dest="golden_command", required=True)
    capture = golden_commands.add_parser("capture", help="Copy catalogued RC1 artifacts to a golden folder.")
    capture.add_argument("--legacy-root", type=Path, required=True, help="Root of the legacy RC2 'Proyecto' tree.")
    capture.add_argument("--destination", type=Path, required=True)
    capture.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    capture.set_defaults(handler=_golden)
    verify = golden_commands.add_parser("verify", help="Check hashes of a golden folder or legacy tree.")
    verify.add_argument("--root", type=Path, required=True)
    verify.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    verify.set_defaults(handler=_golden)


def _golden(args: argparse.Namespace) -> int:
    from icml.regression.catalog import load_catalog
    from icml.regression.golden import capture_golden, check_integrity

    catalog = load_catalog(args.catalog)
    if args.golden_command == "capture":
        manifest = capture_golden(args.legacy_root, catalog, args.destination)
        print(f"Captured {len(catalog.artifacts)} artifacts: {manifest}")
        return EXIT_OK
    issues = check_integrity(args.root, catalog)
    for issue in issues:
        print(f"FAIL {issue.artifact_id}: {issue.problem} ({issue.path})", file=sys.stderr)
    print(f"Checked {len(catalog.artifacts)} artifacts, {len(issues)} issues.")
    return EXIT_INTEGRITY_FAILURE if issues else EXIT_OK
