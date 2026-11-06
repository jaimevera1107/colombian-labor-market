"""ICML H19: preflight and protected, non-destructive monthly update staging.

Never rewrites frozen project inputs, canonical labor products or published vintages.
The update candidate must be computed by the existing ICML pipeline separately.
"""
from __future__ import annotations

import hashlib
import json
from importlib import metadata
from pathlib import Path
from typing import Sequence

import numpy as np
import pandas as pd
from icml.domain.cutoff import FIRST_MONTH, FROZEN_CUTOFF, expected_month_count

from icml.pipeline.vintage import (
    STATE_FINAL, VintageError, VintagePolicy, compare_vintages,
    revision_state,
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def json_write(path: Path, obj: dict) -> None:
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def _new_directory(path: Path) -> None:
    if path.exists():
        raise FileExistsError(f"Output already exists: {path}")
    path.mkdir(parents=True, exist_ok=False)


def _file_report(base: Path, file_hashes: dict[str, str]) -> tuple[int, list[dict]]:
    issues = []
    verified = 0
    for rel, expected in file_hashes.items():
        target = base / rel
        if not target.is_file():
            issues.append({"path": str(target), "reason": "missing"})
        elif sha256(target) != expected:
            issues.append({"path": str(target), "reason": "sha256_mismatch"})
        else:
            verified += 1
    return verified, issues


def _audit_labor(root: Path) -> dict:
    """Audit three frozen full-domain labor bases; no re-estimation."""
    base = root / "datos/2_procesamiento/productos_congelados/pruebas_calidad"
    paths = {name: base / (name + ".csv") for name in ("ciudades", "departamentos", "nacionales")}
    if any(not f.is_file() for f in paths.values()):
        return {"status": "UNAVAILABLE", "paths": {k: str(v) for k,v in paths.items()}}
    dfs = {name: pd.read_csv(file, dtype={"dep_code": str, "city_code": str}, low_memory=False)
           for name, file in paths.items()}
    levels = ("population", "working_age", "labor_force", "employed", "unemployed", "inactive")
    problems = []
    for name, df in dfs.items():
        for col in levels:
            if col not in df or not np.isfinite(pd.to_numeric(df[col], errors="coerce")).all():
                problems.append(f"{name}: missing/nonfinite {col}")
        if problems:
            continue
        if (df["labor_force"]-df["employed"]-df["unemployed"]).abs().max() > 1.1:
            problems.append(f"{name}: PEA identity violated")
        if (df["working_age"]-df["labor_force"]-df["inactive"]).abs().max() > 1.1:
            problems.append(f"{name}: PET identity violated")
        if (df[list(levels)] < -1e-5).any().any():
            problems.append(f"{name}: negative levels")
    dep = dfs["departamentos"]
    cit = dfs["ciudades"]
    nat = dfs["nacionales"]
    months = sorted(dep.period.unique())
    n_months = expected_month_count()
    if (len(months) != n_months or months[0] != FIRST_MONTH
            or months[-1] != FROZEN_CUTOFF):
        problems.append("unexpected time window")
    # 33 territories, 33 urban domains and two national series per month.
    if (len(dep), len(cit), len(nat)) != (33 * n_months, 33 * n_months, 2 * n_months):
        problems.append("unexpected row counts")
    if dep.duplicated(["period", "dep_code"]).any() or cit.duplicated(["period", "city_code"]).any():
        problems.append("duplicate territory keys")
    if nat.duplicated(["period", "national_type"]).any():
        problems.append("duplicate national keys")
    national = nat[nat.national_type == "ICML_COMPLETO"].set_index("period")
    dep_sum = dep.groupby("period")[list(levels)].sum()
    if dep_sum.shape != national.shape[:1] + (len(levels),):
        problems.append("national/month shape mismatch")
    elif float(np.max(np.abs(dep_sum.to_numpy() - national.loc[dep_sum.index, list(levels)].to_numpy()))) > 1e-4:
        problems.append("departmental totals != national complete")
    return {"status": "PASS_ACCOUNTING_NOT_STATISTICAL_CERTIFICATION" if not problems else "FAIL",
            "paths_sha256": {k:sha256(v) for k,v in paths.items()},
            "rows": {k:len(v) for k,v in dfs.items()}, "months":len(months),
            "territories": int(dep.dep_code.nunique()), "problems":problems}


def _audit_informality(root: Path) -> dict:
    path = root / "datos/2_procesamiento/parametros_congelados/informalidad_cierre_h9/13_puerta_calidad.csv"
    if not path.is_file():
        return {"status": "UNAVAILABLE"}
    gates = pd.read_csv(path)
    required = gates[gates.criticality.astype(str) == "REQUIRED"]
    count = int(required.passed.astype(str).str.lower().eq("true").sum())
    total = len(required)
    return {"status": "PASS_ACCOUNTING_EXPERIMENTAL_NOT_OFFICIAL" if count == total else "FAIL",
            "required_passed":count, "required_total":total,
            "sha256": sha256(path), "scientific_certification": "NOT_ESTABLISHED"}


def preflight(root: Path, output: Path, golden_dir: Path | None = None) -> dict:
    """Audit frozen H18 products; never assume absent golden data passed."""
    root = root.resolve()
    closure = root / "datos/2_procesamiento/productos_congelados"
    manifest = closure / "MANIFIESTO_CIERRE_SHA256.json"
    if not manifest.is_file():
        raise FileNotFoundError(manifest)
    frozen = json.loads(manifest.read_text(encoding="utf-8"))
    verified, issues = _file_report(closure, frozen["files_sha256"])
    product = closure / "sectorial/sectorial_departamental_1993_2026_EXPERIMENTAL.csv"
    chosen = root / "datos/2_procesamiento/sectorial_h16/outputs/16_matriz_mensual_1993_2026_EXPERIMENTAL.csv"
    panel_ok = chosen.is_file() and product.is_file() and sha256(chosen) == sha256(product)
    if not panel_ok:
        issues.append({"path": str(chosen), "reason": "H16 frozen panel differs from H18 export or is missing"})
    deps = {}
    for package in ("numpy", "pandas", "scipy", "scikit-learn", "xgboost", "statsmodels", "tempdisagg", "xlrd"):
        try:
            deps[package] = metadata.version(package)
        except metadata.PackageNotFoundError:
            deps[package] = None
    golden = {"status": "NOT_EXECUTED_NO_EXTERNAL_REFERENCE", "count": 102}
    if golden_dir is not None:
        from icml.regression.catalog import load_catalog
        from icml.regression.golden import check_integrity
        catalog = load_catalog(root / "configs/golden/rc1_catalog.toml")
        result = check_integrity(golden_dir, catalog)
        golden = {"status": "PASS" if not result else "FAIL", "count": len(catalog.artifacts),
                  "issues": [{"id": i.artifact_id, "problem": i.problem} for i in result]}
    labor = _audit_labor(root)
    informal = _audit_informality(root)
    if labor["status"] != "PASS_ACCOUNTING_NOT_STATISTICAL_CERTIFICATION":
        issues.append({"path": "labor bases", "reason": labor.get("problems", ["missing frozen labor products"])})
    if informal["status"] != "PASS_ACCOUNTING_EXPERIMENTAL_NOT_OFFICIAL":
        issues.append({"path": "informality", "reason": "required gate failed"})
    if golden_dir is not None and golden["status"] == "FAIL":
        issues.append({"path": str(golden_dir), "reason": "golden reference integrity failed"})
    status = "PASS_INTEGRITY_RESEARCH_ONLY" if not issues else "FAIL_INTEGRITY"
    report = {"status": status, "canonical_publication_allowed": False,
              "h18_files_verified": verified, "h18_files_expected": len(frozen["files_sha256"]),
              "h16_export_sha256_match": panel_ok,
              "integrity_issues": issues, "dependencies_installed": deps,
              "golden": golden, "labor": labor, "informality": informal,
              "software": "ICML H19 operational checkpoint",
              "sectoral_status": "FROZEN_EXPERIMENTAL_NON_OFFICIAL"}
    _new_directory(output)
    json_write(output / "19_preflight.json", report)
    return report


def _valid_frame(df: pd.DataFrame, keys: Sequence[str], quantities: Sequence[str], label: str) -> None:
    cols = list(keys) + list(quantities)
    if any(c not in df for c in cols):
        raise VintageError(f"{label}: required columns missing {sorted(set(cols) - set(df))}")
    if df[list(keys)].isna().any().any() or df.duplicated(list(keys)).any():
        raise VintageError(f"{label}: missing/duplicate keys")
    periods = df["period"].astype(str)
    try:
        checked = pd.PeriodIndex(periods, freq="M")
    except (ValueError, TypeError) as exc:
        raise VintageError(f"{label}: invalid monthly calendar") from exc
    if any(str(p) != v for p, v in zip(checked, periods)):
        raise VintageError(f"{label}: period must have format YYYY-MM")
    numbers = df[list(quantities)].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float)
    if not np.isfinite(numbers).all():
        raise VintageError(f"{label}: nonfinite quantities")
    if (numbers < 0).any():
        raise VintageError(f"{label}: negative labor levels")
    months = sorted(periods.unique())
    expected = list(pd.period_range(months[0], months[-1], freq="M").astype(str))
    if months != expected:
        raise VintageError(f"{label}: non-contiguous monthly periods")
    needed = {"employed", "unemployed", "labor_force", "inactive", "working_age"}
    if needed.issubset(df.columns):
        for lhs, a, b in (("labor_force", "employed", "unemployed"),
                          ("working_age", "labor_force", "inactive")):
            diff = (df[lhs] - df[a] - df[b]).abs().max()
            if diff > 1e-4:
                raise VintageError(f"{label}: labor identity violation: {lhs}, max {diff}")


def _protected_metadata_check(old: pd.DataFrame, new: pd.DataFrame, keys: Sequence[str]) -> None:
    """Avoid silent edits to frozen labels/factors not listed as quantities."""
    old_final = old.loc[old.revision_state == STATE_FINAL].drop(columns="revision_state")
    indexed_old = old_final.set_index(list(keys)).sort_index()
    indexed_new = new.set_index(list(keys)).reindex(indexed_old.index).sort_index()
    for col in indexed_old.columns:
        a, b = indexed_old[col], indexed_new[col]
        if pd.api.types.is_numeric_dtype(a) and not pd.api.types.is_bool_dtype(a):
            aa = pd.to_numeric(a, errors="coerce").to_numpy(dtype=float)
            bb = pd.to_numeric(b, errors="coerce").to_numpy(dtype=float)
            if not np.isfinite(aa).all() or not np.isfinite(bb).all():
                raise VintageError(f"Frozen column {col}: nonfinite value")
            if (np.abs(aa-bb) > 1e-9 * np.maximum(np.abs(aa), 1.0)).any():
                raise VintageError(f"Frozen column changed: {col}")
        else:
            if not (a.fillna("__NA__").astype(str) == b.fillna("__NA__").astype(str)).all():
                raise VintageError(f"Frozen metadata changed: {col}")


def stage_update(previous: Path, candidate: Path, output: Path, keys: Sequence[str],
                 quantities: Sequence[str], old_policy: VintagePolicy,
                 new_policy: VintagePolicy) -> dict:
    """Preview/stage a new immutable candidate, refusing frozen edits or gaps.

    Produces no new monthly values: candidate values must come from the
    ICML pipeline and an externally validated new DANE source.
    """
    if "period" not in keys or not keys or not quantities:
        raise VintageError("period must be a key and at least one quantity is needed")
    if new_policy.window_length != old_policy.window_length or new_policy.last_anchored_year < old_policy.last_anchored_year:
        raise VintageError("Window length changed or anchor year moved backward")
    if pd.Period(new_policy.last_month, freq="M") != pd.Period(old_policy.last_month, freq="M") + 1:
        raise VintageError("Ordinary updates must advance exactly one month")
    a = pd.read_csv(previous, dtype={k: str for k in keys}, low_memory=False)
    b = pd.read_csv(candidate, dtype={k: str for k in keys}, low_memory=False)
    _valid_frame(a, keys, quantities, "previous")
    _valid_frame(b, keys, quantities, "candidate")
    if "revision_state" not in a or "revision_state" in b:
        raise VintageError("previous must carry revision_state; candidate must not")
    if set(a.columns) - {"revision_state"} != set(b.columns):
        raise VintageError("Schemas differ between previous and candidate")
    if a.period.max() != old_policy.last_month or b.period.max() != new_policy.last_month:
        raise VintageError("Last month does not match vintage policy")
    # Refuse if a supplied revision state was quietly manipulated after publication.
    original_states = revision_state(a.period, old_policy)
    if not a.revision_state.eq(original_states).all():
        raise VintageError("Previous revision_state does not match old policy")
    previous_keys = pd.MultiIndex.from_frame(a[list(keys)])
    current_keys = pd.MultiIndex.from_frame(b[list(keys)])
    if not previous_keys.isin(current_keys).all():
        raise VintageError("Candidate drops published rows")
    introduced = b.loc[~current_keys.isin(previous_keys)]
    if introduced.empty or not introduced.period.eq(new_policy.last_month).all():
        raise VintageError("New rows must belong exactly to the next month")
    other_keys = [k for k in keys if k != "period"]
    previous_last = a.loc[a.period == old_policy.last_month, other_keys]
    new_last = introduced[other_keys]
    if other_keys:
        last_entities = pd.MultiIndex.from_frame(previous_last)
        next_entities = pd.MultiIndex.from_frame(new_last)
        if len(last_entities) != len(next_entities) or not last_entities.isin(next_entities).all():
            raise VintageError("New month has missing or unexpected entities")
    report = compare_vintages(a, b, keys, quantities, old_policy)
    blocked = None
    if not report.accepted:
        blocked = "Protected numeric quantities differ from published vintage"
    else:
        try:
            _protected_metadata_check(a, b, keys)
        except VintageError as exc:
            blocked = str(exc)
    status = "ACCEPTED_STAGED_NOT_PUBLISHED" if blocked is None else "BLOCKED_FROZEN_HISTORY"
    summary = {**report.summary, "status": status, "reason": blocked,
               "previous_sha256": sha256(previous), "candidate_sha256": sha256(candidate),
               "previous_last_month": old_policy.last_month,
               "candidate_last_month": new_policy.last_month,
               "new_rows": len(introduced), "canonical_published": False,
               "comparability_scope": "full candidate supplied by external pipeline"}
    _new_directory(output)
    report.changes.to_csv(output / "19_cambios_por_celda.csv", index=False,lineterminator='\n')
    json_write(output / "19_actualizacion_auditoria.json", summary)
    if blocked is None:
        staged = b.copy()
        staged["revision_state"] = revision_state(b.period, new_policy)
        staged.sort_values(list(keys)).to_csv(output / "19_candidato_con_estados.csv", index=False,lineterminator='\n')
        summary["staged_sha256"] = sha256(output / "19_candidato_con_estados.csv")
        json_write(output / "19_actualizacion_auditoria.json", summary)
    return summary
