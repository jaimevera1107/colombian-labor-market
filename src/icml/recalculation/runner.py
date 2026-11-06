"""Run an anchored or total recalculation and write a timestamped delivery."""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable, Mapping
from datetime import datetime
from pathlib import Path

import pandas as pd

from icml.delivery.builder import TIMEZONE, build_delivery, read_text_table
from icml.delivery.spec import SPECS
from icml.domain.cutoff import ACTIVE_CUTOFF
from icml.ingestion.discovery import INFORMALITY, LABOR, annex_for, annexes_after, detect_cutoff, is_workbook
from icml.recalculation.gates import fingerprint
from icml.recalculation.graft import assert_frozen_unchanged, graft_frozen_years
from icml.recalculation.plan import plan_recalculation
from icml.recalculation.policy import ANCHORED, AnchorPolicy

INGESTA = "datos/1_ingesta"
PARAMETERS = "datos/2_procesamiento/parametros_congelados"
CURRENT = "datos/2_procesamiento/vigente"
OUTPUT = "datos/3_salida"

#: Columns that identify a row of each internal product (besides period).
PRODUCT_KEYS: dict[str, tuple[str, ...]] = {
    "labor.nacionales": ("period", "national_type"),
    "labor.departamentos": ("period", "dep_code"),
    "labor.ciudades": ("period", "city_code"),
    "informalidad.nacionales": ("period", "national_type"),
    "informalidad.departamentos": ("period", "dep_code"),
    "informalidad.ciudades": ("period", "city_code"),
    "sectorial.nacional": ("period", "sector_code"),
    "sectorial.departamental": ("period", "dep_code", "sector_code"),
}

#: Recomputes the internal products and returns ``{product_id: csv path}``.
Runner = Callable[[Path], Mapping[str, Path]]


def _files(folder: Path) -> list[Path]:
    return [p for p in folder.rglob("*") if p.is_file()] if folder.is_dir() else []


def _ingestion_files(folder: Path, cutoff: str | None = None) -> list[Path]:
    """Data workbooks of the ingestion folder: notes and Office lock files do not count.

    With ``cutoff``, the monthly annexes of later months are left out: a run that ends at ``cutoff`` did not use
    them, so adding them afterwards is a new input (the next update), not something the run already consumed.
    """
    later = annexes_after(folder, cutoff) if cutoff else set()
    return [p for p in _files(folder) if is_workbook(p) and p.resolve() not in later]


def _latest_manifest(output: Path) -> dict | None:
    folders = sorted(p for p in output.glob("*") if (p / "MANIFEST.json").is_file())
    if not folders:
        return None
    return json.loads((folders[-1] / "MANIFEST.json").read_text("utf-8"))


def recalculate(
    root: Path,
    mode: str,
    *,
    anchor_year: int,
    runner: Runner,
    confirm_total: bool = False,
    accept_modified: bool = False,
    dry_run: bool = False,
    cutoff: str = ACTIVE_CUTOFF,
    now: datetime | None = None,
    check_shapes: bool = True,
    excel: bool = False,
    require_annexes: bool = True,
    verify_content: bool = True,
    upto: str | None = None,
    notes: Callable[[], Mapping[str, str]] | None = None,
    software_version: str = "",
) -> dict:
    """Plan and, if allowed, run a recalculation.

    Parameters
    ----------
    root : Path
        Project root (the folder that holds ``datos``).
    mode : str
        ``anclado`` keeps every year covered by the departmental annex;
        ``total`` rewrites everything and needs ``confirm_total``.
    anchor_year : int
        Last year covered by the departmental annex.
    runner : Runner
        Recomputes the eight internal products into a folder.
    confirm_total, accept_modified : bool
        Explicit confirmations (see ``plan_recalculation``).
    dry_run : bool
        Only return the plan.
    require_annexes : bool
        Require that the annexes in ``datos/1_ingesta`` support exactly the
        cutoff of this run: everything is computed as far as the annexes
        reach, and no further. Disable only in tests.
    notes : callable, optional
        Called after the recomputation; the returned mapping (for example the
        splices that were enabled) is added to the manifest's ``inputs_note``.
    verify_content : bool
        Also read both annexes of the cutoff and require that each declares
        that month inside the workbook (the file name only classifies it).
    upto : str, optional
        ``YYYY-MM``. The user chose to work up to that month: the annexes of later months are ignored instead of
        blocking the run, and they are not counted among the inputs of this run.

    Returns
    -------
    dict
        ``plan`` and, when something ran, the delivery ``manifest`` and the
        graft reports.
    """
    root = Path(root)
    policy = AnchorPolicy(anchor_year)
    previous = _latest_manifest(root / OUTPUT)
    current_fp = {
        "ingesta": fingerprint(_ingestion_files(root / INGESTA, upto), root),
        "parametros": fingerprint(_files(root / PARAMETERS), root),
    }
    # With nothing published yet there is no earlier state to compare with:
    # the current inputs become the baseline instead of counting as changes.
    previous_fp = (previous or {}).get("fingerprints") or current_fp
    plan = plan_recalculation(
        mode,
        policy,
        previous_inputs=previous_fp.get("ingesta", {}),
        current_inputs=current_fp["ingesta"],
        previous_parameters=previous_fp.get("parametros", {}),
        current_parameters=current_fp["parametros"],
        confirm_total=confirm_total,
        accept_modified=accept_modified,
    )
    detected = detect_cutoff(root / INGESTA, upto)
    plan["annexes"] = detected
    if require_annexes:
        reached = detected["cutoff"]
        if reached is None:
            plan["blockers"].append(
                "There is no complete pair of annexes (labor market and informality of "
                f"the same month) in {INGESTA}."
            )
        elif reached > cutoff:
            plan["blockers"].append(
                f"The annexes reach {reached}, but this run computes through {cutoff}. "
                "Processing a month after the frozen vintage requires extending the census "
                "bridge and the MLP priors to new months, and that rule is not defined yet."
            )
        elif reached < cutoff:
            plan["blockers"].append(
                f"The annexes of {cutoff} are missing: the last month with both is {reached}."
            )
        if verify_content and reached == cutoff:
            from icml.ingestion.validation import AnnexPeriodMismatch, verify_annex

            configs = Path(__file__).resolve().parents[3] / "configs" / "rc1"
            for kind in (LABOR, INFORMALITY):
                annex = annex_for(root / INGESTA, kind, cutoff)
                try:
                    verify_annex(annex, configs)
                except AnnexPeriodMismatch as exc:
                    plan["blockers"].append(str(exc))
                except Exception as exc:  # noqa: BLE001 - an unreadable annex blocks
                    plan["blockers"].append(f"No se pudo leer {annex.path.name}: {exc}")
        if plan["blockers"]:
            plan["status"] = "BLOQUEADO"
    if previous is None and mode == ANCHORED and plan["status"] == "SIN_CAMBIOS":
        plan["status"] = "EJECUTAR"  # nothing published yet: first delivery
    result: dict = {"plan": plan}
    if dry_run or plan["status"] != "EJECUTAR":
        return result

    moment = (now or datetime.now(TIMEZONE)).astimezone(TIMEZONE)
    staging = root / "datos/2_procesamiento/_corridas" / moment.strftime("%Y-%m-%d_%H%M%S")
    staging.mkdir(parents=True)
    recomputed = {k: Path(v) for k, v in runner(staging).items()}
    current_dir = root / CURRENT
    graft_reports: dict[str, dict] = {}
    products: dict[str, Path] = {}
    use_graft = mode == ANCHORED and (current_dir / "vigente.json").is_file()
    if use_graft:
        grafted_dir = staging / "injertados"
        grafted_dir.mkdir()
        for spec in SPECS:
            published = read_text_table(current_dir / f"{spec.product_id}.csv")
            fresh = read_text_table(recomputed[spec.product_id])
            keys = PRODUCT_KEYS[spec.product_id]
            grafted, report = graft_frozen_years(published, fresh, policy, keys=keys)
            assert_frozen_unchanged(published, grafted, policy, keys=keys)
            target = grafted_dir / f"{spec.product_id}.csv"
            grafted.to_csv(target, index=False, lineterminator="\n")
            products[spec.product_id] = target
            graft_reports[spec.product_id] = report
    else:
        products = dict(recomputed)

    manifest = build_delivery(
        products,
        root / OUTPUT,
        cutoff=cutoff,
        mode=mode,
        now=moment,
        software_version=software_version,
        excel=excel,
        check_shapes=check_shapes,
        fingerprints=current_fp,
        inputs_note={
            "recalculation_plan": plan["status"],
            "anchor_year": str(anchor_year),
            **(notes() if notes else {}),
        },
    )
    # Promote: the products of this delivery become the published vintage
    # that the next anchored recalculation freezes.
    current_dir.mkdir(parents=True, exist_ok=True)
    for spec in SPECS:
        shutil.copy2(products[spec.product_id], current_dir / f"{spec.product_id}.csv")
    (current_dir / "vigente.json").write_text(
        json.dumps(
            {"run_id": manifest["run_id"], "mode": mode, "anchor_year": anchor_year, "cutoff": cutoff},
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    result.update({"manifest": manifest, "graft": graft_reports})
    return result


def products_frame(path: Path) -> pd.DataFrame:
    """Read a product as text (helper for tests and tools)."""
    return read_text_table(path)
