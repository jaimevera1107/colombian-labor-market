"""Everyday commands of a project checkout.

``icml status``    what the project holds and what to do next;
``icml rebuild``   recompute every year from 1993 and publish the base;
``icml update``    add the new month only (the anchored years are frozen);
``icml plots``     draw the latest delivery (optional, needs matplotlib);
``icml verify``    audit a delivery.

They are a thin layer over ``icml.recalculation.service``: they decide, print
and never compute anything on their own. A user mistake prints a plain
message and an exit code; it never prints a traceback.
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from icml.cli._common import EXIT_ACTION, EXIT_ERROR, EXIT_OK, Commands
from icml.layout import (
    CURRENT_DIR,
    INGESTION_DIR,
    OUTPUT_DIR,
    PLOTS_SUFFIX,
    SIMPLE_SUFFIX,
    find_project_root,
)

COMMANDS = ("status", "rebuild", "update", "plots", "verify", "checksums")
_MONTH = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
#: Environment variable that fixes the calendar of a process (see ``_relaunch``).
CUTOFF_ENV = "ICML_CUTOFF"


# ----------------------------------------------------------------------------- parser


def register(commands: Commands) -> None:
    """Register the everyday commands on the main parser."""

    def common(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
        parser.add_argument("--root", type=Path, help="Project folder (default: the current one or the closest above it)")
        return parser

    status = common(commands.add_parser("status", help="What the project holds and what to do next"))
    status.set_defaults(handler=run_command)

    rebuild = common(commands.add_parser(
        "rebuild",
        help="Recompute every year from 1993 and publish the base",
        description=(
            "Recomputes ALL years (1993 up to the last month) and publishes the resulting base. "
            "When a base is already published it asks for confirmation; --yes skips the question."
        ),
    ))
    rebuild.add_argument("--through", metavar="YYYY-MM", help="Last month to include; later annexes are ignored (e.g. 2026-07)")
    rebuild.add_argument("--yes", action="store_true", help="Do not ask for confirmation")
    rebuild.add_argument("--dry-run", action="store_true", help="Only show what would be done, without computing")
    rebuild.add_argument("--no-simple", action="store_true", help="Do not create the simple files")
    rebuild.set_defaults(handler=run_command)

    update = common(commands.add_parser(
        "update",
        help="Add the new month only (the anchored years are not touched)",
        description=(
            "Adds the new month to the published base. The years covered by the "
            "departmental annex stay frozen."
        ),
    ))
    update.add_argument(
        "--through", "--month", dest="through", metavar="YYYY-MM",
        help="Month to include (e.g. 2026-07); later annexes are ignored. --month is a synonym",
    )
    update.add_argument("--dry-run", action="store_true", help="Only show what would be done, without computing")
    update.add_argument("--no-simple", action="store_true", help="Do not create the simple files")
    update.set_defaults(handler=run_command)

    plots = common(commands.add_parser("plots", help="Draw the latest delivery (dashboards per territory and comparatives)"))
    plots.add_argument("--folder", type=Path, help="Delivery to draw (default: the published one)")
    plots.add_argument("--only", help="national, departments, comparatives (comma-separated)")
    plots.add_argument("--universe", help="census or geih (default both)")
    plots.add_argument("--departments", help="Comma-separated DANE codes (default all)")
    plots.add_argument("--format", choices=("png", "pdf", "svg"), default="png")
    plots.add_argument("--force", action="store_true", help="Replace existing figures")
    plots.set_defaults(handler=run_command)

    verify = common(commands.add_parser("verify", help="Audit a delivery"))
    verify.add_argument("--folder", type=Path, help="Delivery to audit (default: the published one)")
    verify.set_defaults(handler=run_command)

    checksums = common(commands.add_parser("checksums", help="Verify the checkout against SHA256SUMS, or regenerate it"))
    checksums.add_argument("--write", action="store_true", help="Regenerate SHA256SUMS (before a commit)")
    checksums.add_argument("--strict", action="store_true", help="Also fail on files not in the list")
    checksums.set_defaults(handler=run_command)


# ----------------------------------------------------------------------------- project state


def deliveries(root: Path) -> list[Path]:
    """Delivery folders (the ones with a MANIFEST.json), oldest first."""
    output = root / OUTPUT_DIR
    return sorted(p for p in output.glob("*") if p.is_dir() and (p / "MANIFEST.json").is_file())


def current_vintage(root: Path) -> dict | None:
    """The published vintage: run id, mode and cutoff, or ``None`` when nothing is published."""
    path = root / CURRENT_DIR / "current.json"
    if not path.is_file():
        path = root / CURRENT_DIR / "vigente.json"  # bases published before 2.6.0
    if not path.is_file():
        return None
    info = json.loads(path.read_text("utf-8"))
    if "cutoff" not in info:
        manifest = root / OUTPUT_DIR / info.get("run_id", "") / "MANIFEST.json"
        if manifest.is_file():
            info["cutoff"] = json.loads(manifest.read_text("utf-8")).get("cutoff")
    return info


def _delivery_folder(root: Path, given: Path | None) -> Path:
    if given:
        return Path(given).resolve()
    vintage = current_vintage(root)
    if vintage and (root / OUTPUT_DIR / vintage["run_id"]).is_dir():
        return root / OUTPUT_DIR / vintage["run_id"]
    found = deliveries(root)
    if not found:
        raise FileNotFoundError("There is no delivery yet. First: icml rebuild")
    return found[-1]


def _check_month(value: str | None) -> str | None:
    if value is not None and not _MONTH.match(value):
        raise ValueError(f"--through must be YYYY-MM (for example 2026-07), not {value!r}")
    return value


def command_status(root: Path) -> int:
    """Print the annexes, the published base, the deliveries and the next step."""
    from icml import __version__
    from icml.domain.cutoff import FROZEN_CUTOFF
    from icml.ingestion.discovery import detect_cutoff

    detected = detect_cutoff(root / INGESTION_DIR)
    vintage = current_vintage(root)
    print(f"ICML {__version__} · project: {root}\n")
    print(f"Monthly annexes ({INGESTION_DIR})")
    if detected["cutoff"]:
        print(f"  Last month with both annexes: {detected['cutoff']}")
    else:
        print("  No month has both annexes (labor market and informality).")
    for kind, label in (("only_mercado_laboral", "labor market only"), ("only_informalidad", "informality only")):
        if detected["pending"][kind]:
            print(f"  Incomplete ({label}): {', '.join(detected['pending'][kind])}")
    print("\nPublished base (the one the next update starts from)")
    if vintage:
        print(f"  Cutoff {vintage.get('cutoff') or 'unknown'} · run {vintage['run_id']} · mode {vintage['mode']}")
    else:
        print("  None yet.")
    found = deliveries(root)
    print(f"\nDeliveries: {len(found)}" + (f" (latest: {found[-1].name})" if found else ""))
    latest = found[-1] if found else None
    if latest is not None:
        simple = latest.with_name(latest.name + SIMPLE_SUFFIX)
        figures = latest.with_name(latest.name + PLOTS_SUFFIX)
        print(f"  simple files: {'yes' if simple.is_dir() else 'no'} · plots: {'yes' if figures.is_dir() else 'no'}")

    print("\nNext step")
    reached = detected["cutoff"]
    if reached is None:
        print(f"  Copy both annexes of the same month into {INGESTION_DIR}/ (see {INGESTION_DIR}/LEEME.md).")
    elif vintage is None:
        print(f"  First time: icml rebuild   (through {reached}; use --through YYYY-MM for another month)")
    elif (vintage.get("cutoff") or "") < reached:
        print(f"  There are annexes newer than the base ({vintage.get('cutoff')} → {reached}): icml update")
    else:
        print("  Everything is up to date. To draw the latest delivery: icml plots")
        print("  To start over from scratch: icml rebuild")
    if reached is not None and reached > FROZEN_CUTOFF:
        print(f"  Note: {reached} is later than the frozen vintage ({FROZEN_CUTOFF}); frozen parameters are carried forward.")
    return EXIT_OK


# ----------------------------------------------------------------------------- rebuild / update


def _relaunch(root: Path, command: str, args: argparse.Namespace, target: str) -> int:
    """Run the same command in a new process whose calendar ends at ``target``.

    The cutoff is fixed when the program starts (``ICML_CUTOFF``), so a month
    other than the default needs a fresh process.
    """
    cmd = [sys.executable, "-m", "icml", command, "--root", str(root), "--through", target]
    for flag in ("yes", "dry_run", "no_simple"):
        if getattr(args, flag, False):
            cmd.append("--" + flag.replace("_", "-"))
    print(f"Computing through {target} requires starting with that cutoff; restarting the program...\n")
    return subprocess.run(cmd, env={**os.environ, CUTOFF_ENV: target}).returncode


def _confirm(message: str, assume_yes: bool) -> bool:
    if assume_yes:
        return True
    if not sys.stdin.isatty():
        print(message + "\n\nThere is no terminal to confirm: repeat the command with --yes.")
        return False
    return input(message + "\n\nType YES to continue: ").strip().lower() in {"yes", "y", "si", "sí"}


def _print_plan(plan: dict, ignored: frozenset[str] = frozenset()) -> None:
    inputs = plan.get("inputs", {})
    print(f"Plan: {plan['mode']} · years: {plan['frozen_years']}")
    for key, label in (("added", "new annexes"), ("modified", "modified"), ("removed", "removed")):
        names = [Path(p).name for p in inputs.get(key, [])]
        if key == "removed":
            skipped = [n for n in names if n in ignored]
            names = [n for n in names if n not in ignored]
            if skipped:
                print(f"  ignored by --through (they will be used by the next update): {', '.join(skipped)}")
        if names:
            print(f"  {label}: {', '.join(names)}")
    for blocker in plan.get("blockers", []):
        print(f"  BLOCKED: {blocker}")


def command_run(root: Path, command: str, args: argparse.Namespace) -> int:
    """``rebuild`` and ``update``: both end in a delivery, its simple files and its audit."""
    from icml.domain.cutoff import ACTIVE_CUTOFF, FROZEN_CUTOFF
    from icml.ingestion.discovery import annexes_after, detect_cutoff
    from icml.recalculation import service
    from icml.recalculation.policy import ANCHORED, TOTAL

    through = _check_month(args.through)
    vintage = current_vintage(root)
    detected = detect_cutoff(root / INGESTION_DIR, through)
    target = through or detected["cutoff"]
    if target is None:
        print(f"No month has both annexes (labor market and informality) in {INGESTION_DIR}.")
        return EXIT_ACTION
    if through and through != detected["cutoff"]:
        print(f"Both annexes of {through} are not available. The last complete month up to it is {detected['cutoff']}.")
        return EXIT_ACTION
    if target > FROZEN_CUTOFF:
        print(
            f"{target} is later than the frozen vintage ({FROZEN_CUTOFF}): the frozen parameters "
            "(census bridge, informality priors, national sectoral composition) are carried forward "
            "to the new months and the products say so (docs/production/EXTENSION_BEYOND_FROZEN_CUTOFF.md).\n"
        )

    if command == "rebuild":
        mode = TOTAL
    else:
        mode = ANCHORED
        if vintage is None:
            print("There is no published base to update yet. First: icml rebuild")
            return EXIT_ACTION
        if vintage.get("cutoff") and target < vintage["cutoff"]:
            print(
                f"The base already reaches {vintage['cutoff']}; update does not go back to {target}.\n"
                f"To rebuild it through {target}: icml rebuild --through {target}"
            )
            return EXIT_ACTION

    if target != ACTIVE_CUTOFF:
        return _relaunch(root, command, args, target)

    if command == "rebuild" and vintage and not args.dry_run:
        ok = _confirm(
            f"This recomputes EVERYTHING from scratch through {target}.\n"
            f"It replaces the published base (cutoff {vintage.get('cutoff')}); earlier deliveries are kept.\n"
            "To add a month instead, use: icml update",
            args.yes,
        )
        if not ok:
            print("Nothing was changed.")
            return EXIT_ACTION
    headline = (
        f"REBUILD FROM SCRATCH through {target}: every year is recomputed."
        if mode == TOTAL
        else f"UPDATE ONLY through {target}: the anchored years are kept and only the open ones are recomputed."
    )
    print(headline + "\n")
    result = service.run_recalculation(
        root,
        mode,
        confirm_total=mode == TOTAL,
        dry_run=args.dry_run,
        upto=target if (through or target < FROZEN_CUTOFF) else None,
    )
    plan = result["plan"]
    _print_plan(plan, frozenset(p.name for p in annexes_after(root / INGESTION_DIR, target)))
    if plan["status"] == "BLOCKED":
        return EXIT_ACTION
    if plan["status"] == "NO_CHANGES":
        print("\nAlready up to date: no new annexes since the last update.")
        return EXIT_OK
    if args.dry_run:
        print("\nDry run: nothing was computed or changed.")
        return EXIT_OK
    folder = root / OUTPUT_DIR / result["manifest"]["run_id"]
    return _finish(root, folder, make_simple=not args.no_simple)


def _finish(root: Path, folder: Path, *, make_simple: bool) -> int:
    from icml.delivery.simple import build_simple
    from icml.delivery.verify import verify_delivery

    print(f"\nDelivery: {folder}")
    report = verify_delivery(folder)
    failed = [c["check"] for c in report["checks"] if not c["passed"]]
    print(f"Audit: {report['status']} ({len(report['checks']) - len(failed)} of {len(report['checks'])} checks)")
    for name in failed:
        print(f"  FAILED: {name}")
    if make_simple:
        simple = build_simple(folder)
        print(f"Simple files: {simple['folder']}")
    print("\nNext step: icml plots")
    return EXIT_OK if report["status"] == "PASS" else EXIT_ERROR


# ----------------------------------------------------------------------------- plots / verify


def _csv_list(text: str | None) -> tuple[str, ...]:
    return tuple(part.strip() for part in text.split(",") if part.strip()) if text else ()


def command_plots(root: Path, args: argparse.Namespace) -> int:
    """Draw the per-territory dashboards and comparatives of a delivery."""
    try:
        plots = importlib.import_module("icml.plots.delivery")
    except ImportError as exc:  # matplotlib is an optional dependency
        raise FileNotFoundError(f"The plots need matplotlib: {exc}") from exc

    folder = _delivery_folder(root, args.folder)
    print(f"Drawing {folder.name} ...")
    try:
        output, count = plots.render_delivery(
            folder,
            groups=_csv_list(args.only) or plots.GROUPS,
            universes=_csv_list(args.universe) or plots.UNIVERSES,
            departments=_csv_list(args.departments),
            fmt=args.format,
            force=args.force,
        )
    except plots.PlotsExist as exc:
        print(exc, file=sys.stderr)
        return EXIT_ACTION
    print(f"{count} figures in {output}")
    print(f"\nOpen {output / 'index.html'} in the browser.")
    return EXIT_OK


def command_verify(root: Path, args: argparse.Namespace) -> int:
    """Audit a delivery and list the failed checks."""
    from icml.delivery.verify import verify_delivery

    folder = _delivery_folder(root, args.folder)
    report = verify_delivery(folder)
    failed = [c["check"] for c in report["checks"] if not c["passed"]]
    print(f"{folder.name}: {report['status']} ({len(report['checks']) - len(failed)} of {len(report['checks'])} checks)")
    for name in failed:
        print(f"  FAILED: {name}")
    return EXIT_OK if report["status"] == "PASS" else EXIT_ERROR


def command_checksums(root: Path, args: argparse.Namespace) -> int:
    """Verify the checkout against ``SHA256SUMS`` or regenerate the listing."""
    from icml.operations import checksums

    if args.write:
        print(f"{checksums.LISTING}: {checksums.write_listing(root)} files")
        return EXIT_OK
    result = checksums.verify(root)
    for label, key in (("MISSING", "missing"), ("ALTERED", "altered"), ("NOT LISTED", "extra")):
        for name in result[key][:20]:
            print(f"{label}: {name}")
        if len(result[key]) > 20:
            print(f"  ... and {len(result[key]) - 20} more")
    ok = result["complete"] and not (args.strict and result["extra"])
    print(f"{'COMPLETE AND INTACT' if ok else 'INCOMPLETE OR ALTERED'}: {result['listed']} files listed, "
          f"{len(result['missing'])} missing, {len(result['altered'])} altered, {len(result['extra'])} not listed")
    return EXIT_OK if ok else EXIT_ERROR


def run_command(args: argparse.Namespace) -> int:
    """Dispatch an everyday command; a user mistake prints a plain message, never a traceback."""
    try:
        root = find_project_root(args.root)
        if args.command == "status":
            return command_status(root)
        if args.command in ("rebuild", "update"):
            return command_run(root, args.command, args)
        if args.command == "plots":
            return command_plots(root, args)
        if args.command == "checksums":
            return command_checksums(root, args)
        return command_verify(root, args)
    except (FileNotFoundError, ValueError) as exc:
        print(f"\n{exc}", file=sys.stderr)
        return EXIT_ERROR
