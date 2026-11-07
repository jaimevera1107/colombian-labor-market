"""Orchestration of a recalculation: integral recompute, delivery and audit.

This module holds the logic that used to live in the console module so
the CLI only parses arguments and prints. Nothing here reads ``argv``.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from icml.domain.cutoff import ACTIVE_CUTOFF, FROZEN_CUTOFF
from icml.layout import CONFIGS_DIR, package_root
from icml.recalculation.runner import OUTPUT

#: A recompute may end in either state; the second one is the adopted method
#: (splices of the 2001-01 seam enabled), which differs from the frozen
#: vintage before that month by design.
CLEAN_STATUSES = frozenset({
    "RECOMPUTED_ALL_EIGHT_AUDITED",
    "RECOMPUTED_ALL_EIGHT_CROSS_AUDITED_WITH_SPLICES",
    "RECOMPUTED_ALL_EIGHT_CROSS_AUDITED_WITH_SPLICES_ON_ANOTHER_PLATFORM",
})

#: A month other than the frozen one is a new vintage: it is not expected to
#: match the frozen products, so the internal coherence of the eight (the
#: cross audit) is what decides. It is clean only for a cutoff that differs.
NEW_VINTAGE_STATUS = "RECOMPUTED_ALL_EIGHT_CROSS_AUDITED_NEW_VINTAGE"

#: Name of the integral audit report kept next to each delivery.
INTEGRAL_REPORT_NAME = "INTEGRAL_RECOMPUTE_REPORT.json"


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
    spliced = any(
        report.get(key, {}).get("enabled")
        for key in ("regime_splice", "labor_base_splice", "labor_reconstruction")
    )
    if status.endswith("WITH_SPLICES") and not spliced:
        raise RuntimeError("Recompute reports a spliced state but no splice is enabled")


def splice_notes(report: dict) -> dict[str, str]:
    """Describe the enabled splices for the delivery manifest."""
    notes: dict[str, str] = {}
    for key in ("regime_splice", "labor_base_splice", "labor_reconstruction"):
        section = report.get(key) or {}
        if section.get("enabled") and key == "labor_reconstruction":
            notes[key] = (
                f"enabled; splice_month={section['break_month']}; "
                f"scaling_factor={section['scaling_factor']}"
            )
        elif section.get("enabled"):
            notes[key] = (
                f"enabled; break_month={section['break_month']}; "
                f"window_months={section['window_months']}"
                + (f"; city_break={section['city_break']}" if "city_break" in section else "")
            )
    return notes


def anchor_year(root: Path) -> int:
    """Read the last year of the configured departmental annex."""
    from icml.departmental.annex import DepartmentAnnexReader
    from icml.departmental.pipeline import load_departmental_config
    from icml.recalculation.policy import anchor_year_from_years

    config = load_departmental_config(package_root() / CONFIGS_DIR / "departmental.toml")
    frame = DepartmentAnnexReader(config.annex).read(root / config.sources.annex)
    return anchor_year_from_years(frame["year"])


def products_from_run(run: Path) -> dict[str, Path]:
    """Map every product name to its file inside an integral run folder."""
    from icml.operations.integral import CANDIDATE_FILES

    return {product: run / relative for product, relative in CANDIDATE_FILES.items()}


def products_from_frozen(root: Path) -> dict[str, Path]:
    """Map every product name to its frozen file after a hash audit."""
    from icml.operations.frozen_products import verify_products

    audit = verify_products(root)
    return {item["product"]: root / item["path"] for item in audit["products"]}


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
    """Plan and, if allowed, run a recalculation of the project at ``root``.

    When the active cutoff precedes the frozen vintage, the integral
    recomputation runs on a project root built for that month
    (``build_vintage_root``) in a temporary folder; the delivery is always
    written in ``root``.

    Parameters
    ----------
    root : Path
        Project root (holds ``datos/``).
    mode : str
        One of ``icml.recalculation.policy.MODES``.
    anchor : int, optional
        Last year of the departmental annex (read from it when omitted).
    confirm_total, accept_modified, dry_run, excel : bool
        See ``icml.recalculation.runner.recalculate``.
    upto : str, optional
        Work up to this month and ignore the annexes of later months.

    Returns
    -------
    dict
        ``plan`` and, when something ran, the delivery ``manifest`` and the
        graft reports.
    """
    from icml import __version__
    from icml.operations.integral import run_integral
    from icml.recalculation.runner import recalculate

    root = Path(root).resolve()
    anchor = anchor or anchor_year(root)

    # ``run_integral`` refuses to write inside the project (it protects the
    # frozen vintage), so the heavy recomputation goes to a temporary folder
    # outside it; only its audit report is kept, next to the delivery.
    workdir = Path(tempfile.mkdtemp(prefix="icml_integral_"))
    run = workdir / "integral"
    methodology: dict[str, str] = {}

    def runner(staging: Path) -> dict[str, Path]:
        source_root = root
        if ACTIVE_CUTOFF != FROZEN_CUTOFF:
            from icml.recalculation.vintage_root import build_vintage_root

            source_root = workdir / "vintage_root"
            actions = build_vintage_root(root, ACTIVE_CUTOFF, source_root)
            if actions.get("extended"):
                methodology["frozen_parameters_extension"] = "; ".join(
                    f"{rel.split('/')[-1]}: {info['rule']} (+{info['rows_added']} rows)"
                    for rel, info in actions["extended"].items())
        report = run_integral(source_root, run, mode="recompute")
        require_clean_recompute(report)
        methodology.update(splice_notes(report))
        return products_from_run(run)

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
            shutil.copy2(report_file, folder / INTEGRAL_REPORT_NAME)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
    return result
