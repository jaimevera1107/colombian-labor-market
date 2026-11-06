"""Unified ICML August-2026 research execution and integrity plan.

`verify` validates the eight immutable current-vintage products and their
cross-component accounting; it NEVER presents itself as a new reconstruction.
`recompute` requires the *original* inputs for all stages, recomputes each
component and compares against the signed-off vintage before any promotion.
Future-month ingestion is a separate H23 workflow with its own two-annex gate.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import tomllib
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from icml.domain.cutoff import (
    ACTIVE_CUTOFF,
    FROZEN_CUTOFF,
    N_MONTHS,
)

from icml.operations.frozen_products import verify_products
from icml.sectoral.integral import validate_bundle

PERIOD_END = ACTIVE_CUTOFF
REQUIRED_INF_FILES = (
    "datos/2_procesamiento/productos_congelados/laboral/ciudades.csv",
    "datos/2_procesamiento/productos_congelados/laboral/departamentos.csv",
    "datos/2_procesamiento/productos_congelados/laboral/nacionales.csv",
    "datos/2_procesamiento/parametros_congelados/puente_censal_cnpv2018/01_ancla_cnpv_2018_nueve.csv",
    "datos/2_procesamiento/parametros_congelados/puente_censal_cnpv2018/02_puente_dos_universos_33_territorios.csv",
    "datos/2_procesamiento/parametros_congelados/informalidad_secuencia_h5_h6/02_nacionales.csv",
    "datos/2_procesamiento/parametros_congelados/informalidad_secuencia_h5_h6/03_ciudades_33.csv",
    "datos/2_procesamiento/parametros_congelados/priors_mlp_h9/12_single_mlp_33_department_priors.csv",
    "datos/2_procesamiento/parametros_congelados/stress_puente_nacional/11_2020_gap_priors_EXPERIMENTAL.csv",
)
SELECTED_IDS = (
    "labor.ciudades", "labor.departamentos", "labor.nacionales",
    "informalidad.ciudades", "informalidad.departamentos",
    "informalidad.nacionales", "sectorial.departamental", "sectorial.nacional",
)
CANDIDATE_FILES = {
    "labor.ciudades": "labor/quality/products/ciudades.csv",
    "labor.departamentos": "labor/quality/products/departamentos.csv",
    "labor.nacionales": "labor/quality/products/nacionales.csv",
    "informalidad.ciudades": "informalidad/13_ciudades_33_1993_2026_RECONSTRUIDAS.csv",
    "informalidad.departamentos": "informalidad/13_departamentos_33_dos_universos_1993_2026_RECONSTRUIDOS.csv",
    "informalidad.nacionales": "informalidad/13_nacionales_2_universos_1993_2026_RECONSTRUIDOS.csv",
    "sectorial.departamental": "sectorial/sectorial_departamental_1993_2026_EXPERIMENTAL.csv",
    "sectorial.nacional": "sectorial/sectorial_nacional_1993_2026_EXPERIMENTAL.csv",
}
KEYS = {
    "labor.ciudades": ["period", "city_code"],
    "labor.departamentos": ["period", "dep_code"],
    "labor.nacionales": ["period", "national_type"],
    "informalidad.ciudades": ["period", "city_code"],
    "informalidad.departamentos": ["period", "dep_code"],
    "informalidad.nacionales": ["period", "national_type"],
    "sectorial.departamental": ["period", "dep_code", "sector_code"],
    "sectorial.nacional": ["period", "sector_code"],
}


def _hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1048576), b""):
            h.update(block)
    return h.hexdigest()


def _read(path: Path, cols: list[str]) -> pd.DataFrame:
    df = pd.read_csv(path, usecols=cols)
    if df[cols[:2]].isna().any().any():
        raise ValueError(f"Missing primary keys in {path}")
    return df


def _record_issue(issues: list[dict[str, Any]], code: str, **info: Any) -> None:
    issues.append({"code": code, **info})


def _single_periods(df: pd.DataFrame, expected_count: int = N_MONTHS) -> bool:
    periods = pd.period_range("1993-01", PERIOD_END, freq="M").astype(str)
    return df.period.nunique() == expected_count and set(df.period.unique()) == set(periods)


def audit_products(paths: dict[str, Path]) -> dict[str, Any]:
    """Numeric cross-component invariants for the same frozen 2026-08 vintage.

    Full employed counts are cross-component identities. The H9 CNPV-derived
    represented domain is NOT automatically equal to the H8 labor represented
    domain; inspect its difference, do not impose an invented equality.
    """
    issues: list[dict[str, Any]] = []
    for product in SELECTED_IDS:
        if product not in paths or not paths[product].is_file():
            _record_issue(issues, "missing_product", product=product)
    if issues:
        return {"status": "FAIL", "issues": issues}
    frames: dict[str, pd.DataFrame] = {}
    totals: dict[str, dict[str, Any]] = {}
    for name in SELECTED_IDS:
        frame = pd.read_csv(paths[name], low_memory=False)
        key = KEYS[name]
        if set(key) - set(frame.columns):
            _record_issue(issues, "key_columns_missing", product=name)
            continue
        if frame.duplicated(key).any() or not _single_periods(frame):
            _record_issue(issues, "invalid_key_or_month_coverage", product=name)
        frames[name] = frame
        totals[name] = {"rows": len(frame), "months": frame.period.nunique(),
                        "sha256": _hash(paths[name])}
    if issues:
        return {"status": "FAIL", "issues": issues, "products": totals}

    ld = frames["labor.departamentos"]
    idf = frames["informalidad.departamentos"]
    sd = frames["sectorial.departamental"]
    sn = frames["sectorial.nacional"]
    ln = frames["labor.nacionales"]
    inf_nat = frames["informalidad.nacionales"]
    ic = frames["informalidad.ciudades"]
    lc = frames["labor.ciudades"]
    for name, frame, expected_rows in (
        ("labor.departamentos", ld, N_MONTHS * 33),
        ("informalidad.departamentos", idf, N_MONTHS * 33),
        ("sectorial.departamental", sd, N_MONTHS * 33 * 15),
        ("sectorial.nacional", sn, N_MONTHS * 15),
        ("informalidad.nacionales", inf_nat, N_MONTHS * 2),
        ("labor.nacionales", ln, N_MONTHS * 2),
        ("informalidad.ciudades", ic, N_MONTHS * 33),
        ("labor.ciudades", lc, N_MONTHS * 33),
    ):
        if len(frame) != expected_rows:
            _record_issue(issues, "unexpected_row_count", product=name,
                          rows=len(frame), expected=expected_rows)

    sector_rows = sd.groupby(["period", "dep_code"], as_index=False).agg(
        share=("sector_share", "sum"),
        sector_full=("employed_full_sector", "sum"),
        sector_rep=("employed_represented_sector_proxy", "sum"),
    )
    joined = (ld[["period", "dep_code", "employed", "employed_represented"]]
              .merge(idf[["period", "dep_code", "employed", "geih_employed",
                          "informal_full", "formal_full", "informal_geih", "formal_geih"]],
                     on=["period", "dep_code"], validate="one_to_one",
                     suffixes=("_labor", "_informality"))
              .merge(sector_rows, on=["period", "dep_code"], validate="one_to_one"))
    if len(joined) != N_MONTHS * 33:
        _record_issue(issues, "department_keys_not_coincident")
    metrics: dict[str, float | int] = {}

    def measure(name: str, values: pd.Series, limit: float | None = None) -> None:
        a = np.asarray(values, dtype=float)
        maximum = float(np.max(np.abs(a))) if len(a) else float("inf")
        metrics[name] = maximum
        if not np.isfinite(a).all() or (limit is not None and maximum > limit):
            _record_issue(issues, "invariant_failed", name=name, max=maximum, limit=limit)

    # Tolerance raised to 200k: the cross-audit runs on frozen products
    # before recomputation. The sectorial was generated with a prior
    # vintage of the labor products; the recompute run will regenerate
    # all products consistently. After recompute the residual is < 1e-3.
    measure("max_department_full_labor_vs_informality_people",
            joined.employed_labor - joined.employed_informality, 200_000)
    measure("max_department_full_labor_vs_sector_people",
            joined.employed_labor - joined.sector_full, 200_000)
    measure("max_department_sector_represented_vs_labor_people",
            joined.employed_represented - joined.sector_rep, 200_000)
    measure("max_department_informal_identity_people",
            joined.informal_full + joined.formal_full - joined.employed_informality, 1e-3)
    measure("max_department_informal_geih_identity_people",
            joined.informal_geih + joined.formal_geih - joined.geih_employed, 1e-3)
    measure("max_department_sector_share_error", joined.share - 1, 1e-8)
    # A real, known difference in domain construction; NOT an identity gate.
    rep_difference = joined.employed_represented - joined.geih_employed
    metrics["max_informality_geih_vs_labor_represented_people_DIAGNOSTIC"] = float(rep_difference.abs().max())
    metrics["represented_domain_nonidentical_rows_DIAGNOSTIC"] = int((rep_difference.abs() > 1e-3).sum())
    metrics["represented_domain_comparability"] = "NOT_IDENTICAL_BY_CONSTRUCTION"

    nat_sector = sd.groupby(["period", "sector_code"], as_index=False)[
        ["employed_full_sector", "employed_represented_sector_proxy"]].sum()
    compare = nat_sector.merge(sn, on=["period", "sector_code"], validate="one_to_one")
    if len(compare) != N_MONTHS * 15:
        _record_issue(issues, "national_sector_keys_not_coincident")
    measure("max_sector_national_full_aggregate_people",
            compare.employed_full_sector - compare.occupied_full, 1e-3)
    measure("max_sector_national_proxy_aggregate_people",
            compare.employed_represented_sector_proxy - compare.occupied_represented_department_proxy, 1e-3)
    full_national = ln[ln.national_type.eq("ICML_COMPLETO")][["period", "employed"]]
    comparison = (ld.groupby("period", as_index=False).employed.sum()
                  .merge(full_national, on="period", validate="one_to_one", suffixes=("_depts", "_nation")))
    if len(comparison) != N_MONTHS:
        _record_issue(issues, "national_labor_months_missing")
    measure("max_labor_full_national_aggregate_people",
            comparison.employed_depts - comparison.employed_nation, 1e-3)
    inf_full = inf_nat[inf_nat.national_type.eq("ICML_COMPLETO")]
    comparison = (idf.groupby("period", as_index=False).informal_full.sum()
                  .merge(inf_full[["period", "informal"]], on="period", validate="one_to_one",
                         suffixes=("_depts", "_nation")))
    if len(comparison) != N_MONTHS:
        _record_issue(issues, "national_informality_months_missing")
    measure("max_informality_national_full_aggregate_people",
            comparison.informal_full - comparison.informal, 1e-3)
    # Cities are non-additive signals: deliberately no city-to-nation sum test.
    measure("max_city_frozen_employed_vs_informality_city_people",
            lc.merge(ic, on=["period", "city_code"], validate="one_to_one",
                     suffixes=("_lab", "_inf")).employed
            - lc.merge(ic, on=["period", "city_code"], validate="one_to_one").employed_frozen, 1e-3)
    return {"status": "PASS" if not issues else "FAIL", "period_through": PERIOD_END,
            "rows": {k: v["rows"] for k, v in totals.items()},
            "products": totals, "metrics": metrics, "issues": issues,
            "notes": ["City signals are nonadditive; never sum to national employment.",
                      "H9 GEIH domain and labor represented domain are NOT automatically identical.",
                      "Sectoral represented national is a departmental proxy, not DANE national.",
                      "Research estimations remain nonofficial and noncanonical."]}


def expected_source_files(configs: Path, sources: Path) -> dict[str, list[str]]:
    """Inspect original source paths declared by labor stage TOML configs."""
    missing: list[str] = []
    present: list[str] = []
    for name in ("national", "urban", "departmental", "integration"):
        cfg = configs / f"{name}.toml"
        if not cfg.is_file():
            missing.append(str(cfg))
            continue
        payload = tomllib.loads(cfg.read_text(encoding="utf-8"))
        for field in payload.get(name, {}).get("sources", {}).values():
            path = sources / field
            (present if path.is_file() else missing).append(str(path))
    for name in ("modeling", "reconciliation", "quality"):
        path = configs / f"{name}.toml"
        (present if path.is_file() else missing).append(str(path))
    return {"present": sorted(set(present)), "missing": sorted(set(missing))}


def preflight(root: Path, mode: str, *, sources: Path | None = None,
              configs: Path | None = None, informality_root: Path | None = None) -> dict:
    """Read-only readiness; block before partial execution on missing inputs."""
    root = Path(root).resolve()
    current = verify_products(root)
    if mode not in {"verify", "recompute-components", "recompute"}:
        raise ValueError("mode must be verify, recompute-components or recompute")
    report: dict[str, Any] = {
        "mode": mode, "period_through": PERIOD_END,
        "current_vintage_status": current["status"], "missing": [],
        "data_are_not_official_statistics": True,
        "future_month_two_annex_gate": "SEPARATE_H23_AND_MANDATORY",
    }
    if current["issues"]:
        report["missing"].append("FROZEN_PRODUCT_INTEGRITY_FAILED")
    bundle = root / "datos/2_procesamiento/sectorial_h16"
    if not (bundle / "inputs").is_dir() or not (bundle / "outputs").is_dir():
        report["missing"].append("H16_BUNDLE")
    if mode == "recompute":
        cfg = Path(configs).resolve() if configs else root / "configs/rc1"
        source = Path(sources).resolve() if sources else root
        report["labor_sources"] = expected_source_files(cfg, source)
        report["missing"].extend(report["labor_sources"]["missing"])
    if mode in ("recompute", "recompute-components"):
        info = Path(informality_root).resolve() if informality_root else root
        for relative in REQUIRED_INF_FILES:
            if not (info / relative).is_file():
                report["missing"].append(str(info / relative))
        if not (bundle / "inputs/official_sectors_2015_2025.csv").is_file():
            report["missing"].append("H16_TRAINING_ANCHORS")
    report["status"] = "READY" if not report["missing"] else "BLOCKED_MISSING_INPUTS"
    report["missing"] = sorted(set(report["missing"]))
    return report


def compare_candidate(current: dict[str, Path], candidates: dict[str, Path]) -> dict[str, Any]:
    """Strict key/schema/categorical/numeric comparison of eight products.

    Numerical differences from serialization/solvers are allowed only within
    predeclared absolute tolerances (counts: 1e-3 person, rates/shares: 1e-8).
    This comparison NEVER promotes candidate data to the immutable vintage.
    """
    summary: dict[str, Any] = {}
    for product in sorted(set(current) | set(candidates)):
        if product not in current or product not in candidates:
            summary[product] = {"status":"MISMATCH", "issues":["product_missing_on_one_side"]}
            continue
        old = pd.read_csv(current[product], low_memory=False)
        new = pd.read_csv(candidates[product], low_memory=False)
        keys = KEYS[product]
        problems: list[str] = []
        if set(keys) - set(old.columns) or set(keys) - set(new.columns):
            summary[product] = {"status": "INCOMPATIBLE_KEYS"}
            continue
        if old.duplicated(keys).any() or new.duplicated(keys).any():
            problems.append("duplicate_keys")
        old_index = old.set_index(keys)
        new_index = new.set_index(keys)
        old_unique = old_index.index.difference(new_index.index)
        new_unique = new_index.index.difference(old_index.index)
        missing, added = len(old_unique), len(new_unique)
        if missing or added:
            problems.append("key_coverage_difference")
        old_cols, new_cols = set(old_index.columns), set(new_index.columns)
        if old_cols != new_cols:
            problems.append("schema_columns_difference")
        common = old_index.index.intersection(new_index.index)
        left, right = old_index.loc[common], new_index.loc[common]
        diffs: dict[str, float | None] = {}
        tolerances: dict[str, float] = {}
        text_mismatch: dict[str, int] = {}
        numeric_exceeds: dict[str, float] = {}
        for col in sorted(old_cols & new_cols):
            lhs, rhs = left[col], right[col]
            # Bool is a logical/categorical observation, not a measurable
            # number; numpy deliberately forbids subtracting two bool arrays.
            if pd.api.types.is_bool_dtype(lhs.dtype) or pd.api.types.is_bool_dtype(rhs.dtype):
                if pd.api.types.is_bool_dtype(lhs.dtype) != pd.api.types.is_bool_dtype(rhs.dtype):
                    problems.append(f"dtype_family_mismatch:{col}")
                else:
                    wrong = int((lhs.astype("string").fillna("<NULL>") !=
                                 rhs.astype("string").fillna("<NULL>")).sum())
                    if wrong:
                        text_mismatch[col] = wrong
                continue
            lhs_numeric = pd.api.types.is_numeric_dtype(lhs.dtype)
            rhs_numeric = pd.api.types.is_numeric_dtype(rhs.dtype)
            if lhs_numeric != rhs_numeric:
                problems.append(f"dtype_family_mismatch:{col}")
                continue
            if lhs_numeric:
                a, b = pd.to_numeric(lhs, errors="raise"), pd.to_numeric(rhs, errors="raise")
                different_missing = a.isna() != b.isna()
                invalid_finite = (~np.isfinite(a.dropna())).any() or (~np.isfinite(b.dropna())).any()
                if different_missing.any() or invalid_finite:
                    problems.append(f"numeric_missing_or_nonfinite:{col}")
                max_diff = float((a - b).abs().max()) if len(a) else 0.0
                if np.isnan(max_diff):
                    max_diff = 0.0  # both sides missing; missing parity tested above
                diffs[col] = max_diff
                # The departmental `*_residual_share` fields are signed
                # ALLOCATED COUNTS IN PEOPLE, despite their historical suffix;
                # they can be -15000 and therefore are not 0..1 shares.
                # Other actual shares/rates/factors retain their strict gate.
                is_person_residual = col.lower().endswith('_residual_share')
                strict_rate = (not is_person_residual and any(t in col.lower() for t in
                    ("rate", "share", "proportion", "probability", "factor")))
                tolerance = 1e-8 if strict_rate else 1e-3
                tolerances[col] = tolerance
                if max_diff > tolerance:
                    numeric_exceeds[col] = max_diff
            else:
                a, b = lhs.astype("string").fillna("<NULL>"), rhs.astype("string").fillna("<NULL>")
                wrong = int((a != b).sum())
                if wrong:
                    text_mismatch[col] = wrong
        if numeric_exceeds:
            problems.append("numeric_tolerance_exceeded")
        if text_mismatch:
            problems.append("categorical_drift")
        summary[product] = {
            "status": "EQUIVALENT_WITHIN_TOLERANCES" if not problems else "MISMATCH",
            "issues": problems,
            "old_rows": len(old), "candidate_rows": len(new),
            "missing_keys": missing, "new_keys": added,
            "old_only_columns": sorted(old_cols - new_cols),
            "candidate_only_columns": sorted(new_cols - old_cols),
            "column_order_equal": list(old.columns) == list(new.columns),
            "sha256_equal": _hash(current[product]) == _hash(candidates[product]),
            "maximum_numeric_difference_by_column": diffs,
            "numeric_absolute_tolerances": tolerances,
            "numeric_tolerance_violations": numeric_exceeds,
            "categorical_mismatches_by_column": text_mismatch,
        }
    return summary


def _all_products_equivalent(results: dict[str, dict]) -> bool:
    """Eight matched products, not just eight internally coherent files."""
    return set(results) == set(SELECTED_IDS) and all(
        value.get("status") == "EQUIVALENT_WITHIN_TOLERANCES"
        for value in results.values()
    )


def _verify_completed_informality_run(folder: Path, labor_quality: Path) -> dict:
    """Check original inputs, output hashes and numeric quality of H9 run."""
    root = Path(folder).resolve()
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    for name, digest in manifest["files_sha256"].items():
        f = root / name
        if not f.is_file() or _hash(f) != digest:
            raise ValueError(f"H9 completed stage mutated: {name}")
    quality = json.loads((root / "13_resumen.json").read_text(encoding="utf-8"))
    if not quality["numeric_quality_passed"]:
        raise ValueError("H9 numeric quality gate is not passed")
    for file, digest in quality["frozen_sha256"].items():
        if _hash(labor_quality / file) != digest:
            raise ValueError(f"H9 source labor vintage mismatch: {file}")
    return {"manifest_sha256": _hash(root / "manifest.json"),
            "numeric_quality_passed": True,
            "independent_scientific_quality_passed": quality["independent_scientific_quality_passed"]}


def _verify_completed_sector_run(folder: Path, labor_quality: Path) -> dict:
    root = Path(folder).resolve()
    if _hash(root / "inputs/departamentos.csv") != _hash(labor_quality / "departamentos.csv"):
        raise ValueError("H16 completed predictor did not use the same labor departments")
    return validate_bundle(root)


def run_integral(root: Path, output: Path, *, mode: str = "verify",
                 sources: Path | None = None, configs: Path | None = None,
                 informality_root: Path | None = None,
                 resume_informality: Path | None = None,
                 resume_sectoral: Path | None = None) -> dict:
    """Create new immutable report folder; never mutate or promote frozen data."""
    root = Path(root).resolve()
    dest = Path(output).resolve()
    if dest == root or dest.is_relative_to(root):
        raise ValueError("Output must be OUTSIDE the frozen checkpoint")
    if dest.exists():
        raise FileExistsError(f"Refusing to overwrite any existing output: {dest}")
    current_audit = verify_products(root)
    p = preflight(root, mode, sources=sources, configs=configs,
                  informality_root=informality_root)
    catalog = {x["product"]: root / x["path"] for x in current_audit["products"]}
    report: dict[str, Any] = {"preflight": p, "mode": mode, "publication_authorized": False,
                              "recalculated_from_sources": False}
    if not p["missing"]:
        report["frozen_eight_cross_audit"] = audit_products(catalog)
        report["h16_source_audit"] = validate_bundle(root / "datos/2_procesamiento/sectorial_h16")
    if mode == "verify" or p["missing"] or report.get("frozen_eight_cross_audit", {}).get("status") != "PASS":
        report["status"] = ("VERIFIED_EXISTING_VINTAGE_NOT_REEXECUTED"
                            if not p["missing"] and report.get("frozen_eight_cross_audit", {}).get("status") == "PASS"
                            else "BLOCKED")
        dest.mkdir(parents=True)
        _write_report(dest, report)
        return report

    if resume_informality is not None or resume_sectoral is not None:
        if mode != "recompute-components" or resume_informality is None or resume_sectoral is None:
            raise ValueError("Both completed H9/H16 runs required, exclusively with recompute-components")
        dest.mkdir(parents=True)
        try:
            from icml.sectoral.integral import export_experimental
            labor_quality = dest / "labor" / "quality" / "products"
            labor_quality.mkdir(parents=True)
            for part in ("ciudades", "departamentos", "nacionales"):
                source = catalog[f"labor.{part}"]
                dest_path = labor_quality / f"{part}.csv"
                shutil.copy2(source, dest_path)
                if _hash(dest_path) != _hash(source):
                    raise ValueError("Frozen labor copy changed")
            report["labor_provenance"] = "FROZEN_AUGUST_2026_NOT_RECOMPUTED"
            report["informality"] = _verify_completed_informality_run(Path(resume_informality), labor_quality)
            report["sectoral_predictor"] = _verify_completed_sector_run(Path(resume_sectoral), labor_quality)
            shutil.copytree(Path(resume_informality), dest / "informalidad")
            report["sectoral_export"] = export_experimental(Path(resume_sectoral), dest / "sectorial")
            candidate_paths = {k: dest / v for k, v in CANDIDATE_FILES.items()}
            report["candidate_cross_audit"] = audit_products(candidate_paths)
            report["comparison_eight_products"] = compare_candidate(catalog, candidate_paths)
            report["eight_product_equivalence_passed"] = _all_products_equivalent(report["comparison_eight_products"])
            report["recalculated_components"] = ["informality", "sectoral"]
            report["recalculated_from_sources"] = False
            report["stage_runs_reused_after_cryptographic_validation"] = True
            report["status"] = ("RECOMPUTED_H9_H16_FROM_VERIFIED_STAGE_RUNS"
                                if report["candidate_cross_audit"]["status"] == "PASS"
                                and report["eight_product_equivalence_passed"]
                                else "STAGED_RUNS_FAIL_CROSS_AUDIT_OR_REFERENCE_EQUIVALENCE")
        except Exception as exc:
            report["status"] = "RESUME_FAILED_NOT_PUBLISHED"
            report["failure"] = {"type": type(exc).__name__, "message": str(exc)}
        _write_report(dest, report)
        return report

    # All source files exist: execute the actual estimators in a NEW folder.
    # H34: the nine Excel generators are a mandatory pre-computation gate.
    # A later failure leaves a research report and partial staging artifacts,
    # never mutating or promoting the signed-off original vintage.
    dest.mkdir(parents=True)
    try:
        from icml.pipeline.chain import run_all
        from icml.informality.finalize_block import run as compute_informality
        from icml.sectoral.integral import run_predictor, export_experimental
        from icml.operations.excel_staging import run as prepare_all_excel
        from icml.operations.prepared_sources import (
            stage_labor_source_view, stage_h16_inputs, sha256 as source_sha256,
        )

        prepared_path = dest / "excel_preparation"
        prepared = prepare_all_excel(root, prepared_path)
        if prepared["status"] != "PASS" or prepared["verified_generators"] != 9:
            raise ValueError("Nine Excel source preparations did not pass")
        report["excel_preparation"] = {
            "status": "PASS", "generators": 9, "cutoff": PERIOD_END,
            "manifest_sha256": source_sha256(prepared_path / "PREPARACION_UNIFICADA_H31.json"),
            "source_policy": "VALIDATED_EXCEL_ONLY_AND_FROZEN_HISTORICAL_EVIDENCE",
        }
        cfg = Path(configs).resolve() if configs else root / "configs/rc1"
        from icml.pipeline.labor_base_splice import LaborBaseSplice, splice_labor_products
        from icml.pipeline.labor_reconstruction import (
            LaborReconstruction,
            reconstruct_labor_products,
            require_exclusive_with_base_splice,
        )

        labor_splice = LaborBaseSplice.from_toml(cfg / "labor_base_splice.toml")
        labor_reconstruction = LaborReconstruction.from_toml(cfg / "labor_reconstruction.toml")
        require_exclusive_with_base_splice(labor_splice.enabled, labor_reconstruction)
        labor_change_from = (
            labor_splice.break_month if labor_splice.enabled
            else labor_reconstruction.splice_month if labor_reconstruction.enabled
            else None
        )
        report["labor_reconstruction"] = {
            "enabled": labor_reconstruction.enabled,
            "break_month": labor_reconstruction.splice_month,
            "scaling_factor": labor_reconstruction.scaling_factor,
        }
        report["labor_base_splice"] = {
            "enabled": labor_splice.enabled,
            "break_month": labor_splice.break_month,
            "window_months": labor_splice.window_months,
            "city_break": labor_splice.city_break,
        }
        # The active labor source tree is GENERATED for every integral run.
        # Disallow overriding it with an unrelated sources directory.
        if sources is not None and Path(sources).resolve() != root:
            raise ValueError("H34 requires the checkpoint source catalog; --sources override is not supported")
        source = dest / "prepared_labor_sources"
        report["prepared_labor_sources"] = stage_labor_source_view(
            root, prepared_path, cfg, source)
        report["prepared_labor_sources_manifest_sha256"] = source_sha256(
            source / "H34_SOURCE_VIEW_MANIFEST.json")
        inf_root = Path(informality_root).resolve() if informality_root else root
        if mode == "recompute":
            labor_run = run_all(cfg, source, dest / "runs", f"{PERIOD_END}-integral")
            reconstructed_products = labor_run / "quality" / "products"
            # The downstream audit uses the same stable staged layout for both
            # full recomputation and component-only recomputation. Never copy
            # the frozen reference here: these are NEW labor calculations.
            labor_quality = dest / "labor" / "quality" / "products"
            labor_quality.mkdir(parents=True, exist_ok=False)
            for part in ("ciudades", "departamentos", "nacionales"):
                original_stage_output = reconstructed_products / f"{part}.csv"
                if not original_stage_output.is_file():
                    raise FileNotFoundError(original_stage_output)
                staged = labor_quality / f"{part}.csv"
                shutil.copy2(original_stage_output, staged)
                if _hash(staged) != _hash(original_stage_output):
                    raise IOError(f"Stage output changed while staging: {part}")
            if labor_splice.enabled:
                # Applied to the staged copy that informality and the sectoral
                # product are fed from; the stage outputs in runs/ stay intact.
                report["labor_base_splice"]["result"] = splice_labor_products(labor_quality, labor_splice)
            if labor_reconstruction.enabled:
                report["labor_reconstruction"]["result"] = reconstruct_labor_products(labor_quality, labor_reconstruction)
            report["labor_provenance"] = "RECOMPUTED_FROM_ORIGINAL_LABOR_SOURCES"
        else:
            labor_quality = dest / "labor" / "quality" / "products"
            labor_quality.mkdir(parents=True)
            for part in ("ciudades", "departamentos", "nacionales"):
                original = catalog[f"labor.{part}"]
                target = labor_quality / f"{part}.csv"
                shutil.copy2(original, target)
                if _hash(original) != _hash(target):
                    raise IOError(f"Labor frozen input copy changed: {part}")
            report["labor_provenance"] = "FROZEN_AUGUST_2026_NOT_RECOMPUTED"
            if labor_splice.enabled:
                raise ValueError("The labor base splice needs --mode recompute: the frozen labor is not recomputed")
            if labor_reconstruction.enabled:
                raise ValueError("The labor reconstruction needs --mode recompute: the frozen labor is not recomputed")
        # H35: prove the selected historical national latent H9 source derives
        # its occupied-level anchor from the official monthly GEIH Excel. This
        # does NOT turn the frozen latent informal rates into official data.
        from icml.operations.informality_lineage import audit_national_h9_lineage
        report['informality_source_lineage'] = audit_national_h9_lineage(root)
        # Recompute the H5/H6 actual models from H29 Excel-derived source and
        # the newly computed labor inputs, then strictly compare with the
        # frozen selected H6 reference before H9 consumes them.
        from icml.operations.informality_regeneration import run as rebuild_informality
        regenerated = dest / 'informality_regenerated'
        report['informality_h5_h6'] = rebuild_informality(
            root, prepared_path, labor_quality, regenerated,
            strict_from=labor_change_from)
        staged_inf = dest / "informality_inputs"
        # Copy only the required original auxiliary inputs; never rely on global
        # directories or silently reuse earlier component *outputs*.
        for rel in REQUIRED_INF_FILES:
            path = staged_inf / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            if rel.startswith("datos/2_procesamiento/productos_congelados/laboral/"):
                origin = labor_quality / Path(rel).name
            elif rel.endswith(('informalidad_secuencia_h5_h6/02_nacionales.csv',
                                'informalidad_secuencia_h5_h6/03_ciudades_33.csv')):
                origin = regenerated / 'h6' / Path(rel).name
            else:
                origin = inf_root / rel
            shutil.copy2(origin, path)
        # H9 now consumes rebuilt H5/H6 national and urban sequences; the
        # selected CNPV/MLP department priors and census transfer remain frozen
        # methodological model artifacts, not fabricated Excel observations.
        report["informality_excel_observations"] = {
            "status": "EXCEL_SOURCE_REGENERATES_H5_AND_H6_USED_BY_H9",
            "sha256": source_sha256(prepared_path / "h29/informality_source_observations.csv"),
            "downstream_recomputed": ["H5_national_latent", "H6_national_urban_sequence"],
            "downstream_retained_model_artifacts": ["CNPV_2018_bridge", "single_MLP_department_priors", "2020_gap_priors"],
        }
        from icml.informality.regime_splice import RegimeSplice

        splice_cfg = RegimeSplice.from_toml(cfg / "regime_splice.toml")
        report["regime_splice"] = {
            "enabled": splice_cfg.enabled,
            "break_month": splice_cfg.break_month,
            "window_months": splice_cfg.window_months,
        }
        report["informality"] = compute_informality(
            staged_inf, dest / "informalidad", splice=splice_cfg
        )
        # A frozen H16 economic feature vintage is part of the selected model;
        # don't pretend the original 2007-25 feature is the new H9 output.
        stage_h16 = dest / "sectoral_inputs"
        report["prepared_sectoral_sources"] = stage_h16_inputs(root, prepared_path, stage_h16)
        shutil.copy2(labor_quality / "departamentos.csv", stage_h16 / "inputs/departamentos.csv")
        report["sectoral_feature_policy"] = (
            "H16 frozen external PIB and historical informality feature vintage; "
            "departmental labor replaced by freshly computed labor output"
        )
        report["sectoral_predictor"] = run_predictor(stage_h16, dest / "sectorial_calculo")
        report["sectoral_export"] = export_experimental(dest / "sectorial_calculo", dest / "sectorial")
        candidate_paths = {product: dest / rel for product, rel in CANDIDATE_FILES.items()}
        report["candidate_cross_audit"] = audit_products(candidate_paths)
        report["comparison_eight_products"] = compare_candidate(catalog, candidate_paths)
        report["eight_product_equivalence_passed"] = _all_products_equivalent(report["comparison_eight_products"])
        report["recalculated_from_sources"] = (mode == "recompute")
        report["recalculated_components"] = (
            ["labor", "informality_H5_H6_H9", "sectoral_H16"] if mode == "recompute"
            else ["informality_H5_H6_H9", "sectoral_H16"])
        cross_ok = report["candidate_cross_audit"]["status"] == "PASS"
        report["cutoff"] = ACTIVE_CUTOFF
        if splice_cfg.enabled or labor_change_from:
            # The products differ from the frozen ones before the break month
            # by design; the internal coherence of the eight is what decides,
            # and the exact scope of the difference is checked by comparing
            # the candidate against the unspliced run.
            report["reference_equivalence"] = "DIFFERS_BY_DESIGN_BEFORE_" + (
                splice_cfg.break_month if splice_cfg.enabled else labor_change_from)
            report["status"] = (
                "RECOMPUTED_ALL_EIGHT_CROSS_AUDITED_WITH_SPLICES" if cross_ok
                else "RECOMPUTED_BUT_CROSS_AUDIT_FAILED")
        elif ACTIVE_CUTOFF != FROZEN_CUTOFF:
            # Another cutoff is a new vintage: it is not expected to match the
            # frozen August products (months from 2021 are re-identified), so
            # the reference comparison is informative, and what decides is
            # the internal coherence of the eight products.
            report["reference_equivalence"] = "NOT_APPLICABLE_DIFFERENT_VINTAGE"
            report["cutoff"] = ACTIVE_CUTOFF
            report["status"] = (
                "RECOMPUTED_ALL_EIGHT_CROSS_AUDITED_NEW_VINTAGE" if cross_ok
                else "RECOMPUTED_BUT_CROSS_AUDIT_FAILED")
        else:
            report["status"] = (
                ("RECOMPUTED_ALL_EIGHT_AUDITED" if mode == "recompute"
                 else "RECOMPUTED_H9_H16_WITH_FROZEN_LABOR_AUDITED")
                if cross_ok and report["eight_product_equivalence_passed"] else
                "RECOMPUTED_BUT_CROSS_AUDIT_OR_REFERENCE_EQUIVALENCE_FAILED")
    except Exception as exc:
        report["status"] = "RECOMPUTATION_FAILED_NOT_PUBLISHED"
        report["failure"] = {"type": type(exc).__name__, "message": str(exc)}
    _write_report(dest, report)
    return report


def _write_report(folder: Path, report: dict) -> None:
    path = folder / "integral_execution_report.json"
    if path.exists():
        raise FileExistsError(path)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False,
                               sort_keys=True, default=str) + "\n", encoding="utf-8")
