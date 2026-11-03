"""H23 immutable monthly-cycle preflight and provenance verification.

This is an *orchestration safety layer*, not an annex converter or an alternative
estimator. There is intentionally no path to execute models or publish a vintage
without a validated social-security source parser and a checked data-adapter.
"""
from __future__ import annotations

import csv
import json
import os
import shutil
import tempfile
from pathlib import Path
from icml.domain.cutoff import FROZEN_CUTOFF  # re-exported: operations.h23.FROZEN_CUTOFF

from icml.operations.h20 import file_hash, verify_products
from icml.operations.h22 import inspect_annex
from icml.operations.h35_social_annex import inspect_social_annex
from icml.operations.source_pair import check_monthly_sources, _month, _shift_month

SCHEMA = "icml.monthly_cycle.h23.v1"
# This reference is inherited from the last published *research* checkpoint,
# not from a user's freely supplied period flag.


def _json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def _file_record(path: Path | None) -> dict | None:
    if path is None or not path.is_file():
        return None
    return {"original_path": str(path.resolve()), "bytes": path.stat().st_size,
            "sha256": file_hash(path), "original_name": path.name}


def _check_cutoff(root: Path, period: str) -> tuple[str, list[str]]:
    """Enforce the *next* contiguous month and the actual frozen CSV cutoff."""
    frozen = root / "datos/2_procesamiento/productos_congelados/pruebas_calidad/nacionales.csv"
    if not frozen.is_file():
        return "UNAVAILABLE", ["FROZEN_NATIONAL_BASE_MISSING"]
    latest = ""
    with frozen.open("r", newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        if "period" not in (reader.fieldnames or []):
            return "UNAVAILABLE", ["FROZEN_NATIONAL_PERIOD_COLUMN_MISSING"]
        for row in reader:
            m = row["period"]
            if not latest or m > latest:
                latest = m
    blockers = []
    if latest != FROZEN_CUTOFF:
        blockers.append("UNEXPECTED_FROZEN_BASE_CUTOFF")
    expected = _shift_month(_month(latest), 1).strftime("%Y-%m") if latest else None
    if expected != period:
        blockers.append("NOT_NEXT_CONTIGUOUS_MONTH")
    return latest, blockers


def prepare_monthly_cycle(root: Path, period: str, output: Path,
                          geih_annex: Path | None = None, social_annex: Path | None = None,
                          geih_month: str | None = None,
                          social_start: str | None = None,
                          social_end: str | None = None) -> dict:
    """Create immutable source-intake evidence and a *non-executable* run plan.

    Copies provided source bytes into a new, unique staging directory and
    verifies copied SHA-256. It never updates any ICML model or data product.
    A matching pair of filenames/declarations is NOT source validation.
    """
    root, output = root.resolve(), output.resolve()
    _month(period)
    if output.exists():
        raise FileExistsError(f"Refusing overwrite of cycle directory: {output}")
    if root == output or root in output.parents or output in root.parents:
        raise ValueError("Cycle output must be outside frozen checkpoint root")
    pair = check_monthly_sources(period, geih_annex, social_annex,
                                 geih_month, social_start, social_end)
    frozen_period, cutoff_blockers = _check_cutoff(root, period)
    frozen = verify_products(root)
    blockers = list(pair["blockers"]) + cutoff_blockers
    if frozen["issues"] or frozen["checked_count"] != 8:
        blockers.append("FROZEN_PRODUCT_INTEGRITY_FAILED")

    # Staging accepts source-only evidence, but an isolated GEIH workbook
    # may be validated before the matching social workbook becomes available.
    geih_values = []
    geih_validation = "NO_SOURCE"
    if geih_annex is not None and geih_annex.is_file():
        if geih_annex.suffix.lower() != ".xlsx":
            blockers.append("GEIH_NOT_XLSX")
            geih_validation = "FAILED_EXTENSION"
        else:
            try:
                geih_values = inspect_annex(geih_annex, [period])
                if len(geih_values) != 2 or {r["domain"] for r in geih_values} != {"DANE_NACIONAL", "DANE_13_CIUDADES"}:
                    raise ValueError("Incorrect required national/13-city domains")
                geih_validation = "PASS_H22_CELL_AND_ACCOUNTING_CHECKS"
            except Exception as exc:
                # Preserve an explicit error instead of manufacturing observations.
                blockers.append("GEIH_WORKBOOK_CONTENT_VALIDATION_FAILED")
                geih_validation = f"FAILED_{type(exc).__name__}: {exc}"
    social_validation = 'NO_SOURCE'
    social_audit = None
    if social_annex is not None and social_annex.is_file():
        if social_annex.suffix.lower() != '.xlsx':
            social_validation = 'FAILED_EXTENSION'
            blockers.append('SOCIAL_SECURITY_NOT_XLSX')
        else:
            try:
                social_audit = inspect_social_annex(social_annex, period)
                social_validation = 'PASS_H35_WORKBOOK_MONTHLY_ROLLING_AND_SECURITY'
                if (social_start is not None and
                    social_start != social_audit['three_month_window_start']):
                    blockers.append('SOCIAL_SECURITY_DECLARED_START_DIFFERS_FROM_WORKBOOK')
                if social_end is not None and social_end != social_audit['period']:
                    blockers.append('SOCIAL_SECURITY_DECLARED_END_DIFFERS_FROM_WORKBOOK')
            except Exception as exc:
                blockers.append('SOCIAL_SECURITY_XLSX_CONTENT_VALIDATION_FAILED')
                social_validation = f'FAILED_{type(exc).__name__}: {exc}'
    else:
        blockers.append('SOCIAL_SECURITY_XLSX_CONTENT_NOT_VERIFIED')
    # Source-content validation is necessary but not sufficient. No production
    # adapters exist for the newly selected month in all three model families.
    blockers.extend(['CANONICAL_SOURCE_ADAPTER_NOT_VERIFIED',
                     'FULL_LABOR_INFORMALITY_SECTORAL_PIPELINE_NOT_EXECUTED'])
    blockers = list(dict.fromkeys(blockers))

    manifest = {
        "schema": SCHEMA,
        "target_month": period,
        "frozen_last_month": frozen_period,
        "status": "BLOCKED_FOR_MONTHLY_COMPUTATION_AND_PUBLICATION",
        "stage": "SOURCE_INTAKE_ONLY",
        "required_sources": pair,
        "geih_content_validation": geih_validation,
        "social_content_validation": social_validation,
        "social_observation_rows": len(social_audit["observations"]) if social_audit else 0,
        "social_workbook_audit": social_audit,
        "geih_observation_rows": len(geih_values),
        "frozen_products": {"status": frozen["status"], "checked_count": frozen["checked_count"],
                            "sha256": {x["product"]: x["sha256"] for x in frozen["products"]},
                            "issues": frozen["issues"]},
        "blockers": blockers,
        "computation_performed": False,
        "new_values_computed": False,
        "canonical_files_modified": False,
        "publication_permitted": False,
        "vintage_promoted": False,
        "execution_plan": [
            {"step": "verify_same_month_source_pair", "status": "CHECKED_DECLARATIONS_ONLY"},
            {"step": "validate_geih_source_cells", "status": geih_validation},
            {"step": "validate_social_security_content_and_origin", "status": social_validation},
            {"step": "adapt_both_annexes_to_pipeline_inputs", "status": "PENDING"},
            {"step": "run_national_urban_departmental", "status": "NOT_RUN"},
            {"step": "run_informality_and_sectoral", "status": "NOT_RUN"},
            {"step": "check_quality_and_compare_against_frozen", "status": "NOT_RUN"},
            {"step": "stage_new_research_vintage", "status": "NOT_RUN"},
        ],
        "sources": {"geih": _file_record(geih_annex), "social_security": _file_record(social_annex)},
        "notes": [
            "Matching files and declared dates never authorize calculation.",
            "New values require content-verified official workbooks, audited source adapters and all quality gates.",
            "Frozen products remain August 2026; Golden RC1 certification remains pending.",
        ],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    # Atomic staging: no incomplete snapshot at output path.
    with tempfile.TemporaryDirectory(prefix=".icml_h23_", dir=output.parent) as temporary:
        staged = Path(temporary) / "cycle"
        staged.mkdir()
        (staged / "sources").mkdir()
        for key, source in (("geih", geih_annex), ("social_security", social_annex)):
            entry = manifest["sources"][key]
            if entry is None:
                continue
            target = staged / "sources" / (key + source.suffix.lower())
            shutil.copy2(source, target)
            if file_hash(target) != entry["sha256"]:
                raise IOError(f"Source mutated during staging: {key}")
            entry["staged_relative_path"] = str(target.relative_to(staged))
        with (staged / "23_geih_observations.csv").open("w", newline="", encoding="utf-8") as stream:
            cols = ["period", "domain", "source_sheet", "participation_rate_pct",
                    "employment_rate_pct", "unemployment_rate_pct", "population_thousands",
                    "working_age_thousands", "labor_force_thousands", "employed_thousands",
                    "unemployed_thousands", "inactive_thousands"]
            writer = csv.DictWriter(stream, fieldnames=cols)
            writer.writeheader()
            writer.writerows(geih_values)
        manifest["staged_artifacts"] = {
            "23_geih_observations.csv": file_hash(staged / "23_geih_observations.csv"),
        }
        _json(staged / "23_monthly_cycle.json", manifest)
        os.replace(staged, output)
    return manifest


def verify_monthly_cycle(root: Path, cycle: Path) -> dict:
    """Verify archived source bytes, frozen-product hashes and blocked state."""
    root, cycle = root.resolve(), cycle.resolve()
    manifest = json.loads((cycle / "23_monthly_cycle.json").read_text(encoding="utf-8"))
    issues: list[str] = []
    if manifest.get("schema") != SCHEMA:
        issues.append("SCHEMA_MISMATCH")
    if manifest.get("status") != "BLOCKED_FOR_MONTHLY_COMPUTATION_AND_PUBLICATION":
        issues.append("UNEXPECTED_MONTHLY_CYCLE_STATUS")
    social_validation = manifest.get('social_content_validation', '')
    if (social_validation != 'NO_SOURCE'
        and social_validation != 'FAILED_EXTENSION'
        and not social_validation.startswith(('FAILED_', 'PASS_H35_'))):
        issues.append('SOCIAL_VALIDATION_NOT_GROUNDED_IN_H35')
    if social_validation.startswith('PASS_H35_'):
        source = manifest.get('sources', {}).get('social_security')
        if not source:
            issues.append('SOCIAL_VERIFIED_WITHOUT_SOURCE')
        else:
            rel = source.get('staged_relative_path', '')
            staging = (cycle / rel).resolve()
            try:
                if cycle not in staging.parents or not staging.is_file():
                    raise ValueError('Missing staged workbook')
                fresh = inspect_social_annex(staging, manifest['target_month'])
                original = manifest.get('social_workbook_audit') or {}
                if (fresh['sha256'] != original.get('sha256') or
                    fresh['observations'] != original.get('observations')):
                    raise ValueError('Social source audit does not match staged source')
            except Exception:
                issues.append('SOCIAL_REVALIDATION_FAILED')
    if "23_geih_observations.csv" not in manifest.get("staged_artifacts", {}):
        issues.append("MISSING_REQUIRED_STAGED_ARTIFACT_DIGEST")
    previous_cutoff, cutoff_issues = _check_cutoff(root, manifest.get("target_month", "2026-09"))
    if cutoff_issues or manifest.get("frozen_last_month") != previous_cutoff:
        issues.append("FROZEN_BASELINE_PERIOD_OR_CYCLE_CHANGED")
    for key in ("geih", "social_security"):
        entry = manifest.get("sources", {}).get(key)
        if not entry:
            continue
        relative = entry.get("staged_relative_path")
        if not relative or Path(relative).is_absolute() or ".." in Path(relative).parts:
            issues.append(f"INVALID_STAGED_RELATIVE_PATH_{key}")
            continue
        staged = (cycle / relative).resolve()
        if cycle not in staged.parents or not staged.is_file():
            issues.append(f"STAGED_SOURCE_MISSING_{key}")
        elif file_hash(staged) != entry.get("sha256") or staged.stat().st_size != entry.get("bytes"):
            issues.append(f"STAGED_SOURCE_HASH_MISMATCH_{key}")
    for rel, expected_hash in manifest.get("staged_artifacts", {}).items():
        if Path(rel).is_absolute() or ".." in Path(rel).parts:
            issues.append("INVALID_STAGED_ARTIFACT_PATH")
            continue
        artifact = (cycle / rel).resolve()
        if cycle not in artifact.parents or not artifact.is_file() or file_hash(artifact) != expected_hash:
            issues.append(f"STAGED_ARTIFACT_HASH_MISMATCH_{rel}")
    frozen = verify_products(root)
    if frozen["issues"]:
        issues.append("FROZEN_PRODUCTS_CHANGED")
    baseline = manifest.get("frozen_products", {}).get("sha256", {})
    for entry in frozen["products"]:
        if baseline.get(entry["product"]) != entry["sha256"]:
            issues.append(f"FROZEN_HASH_CHANGED_{entry['product']}")
    if manifest.get("computation_performed") is not False or manifest.get("publication_permitted") is not False or manifest.get("vintage_promoted") is not False:
        issues.append("CYCLE_CLAIMS_UNAUTHORIZED_EXECUTION")
    return {"status": "PASS_INTAKE_EVIDENCE_ONLY" if not issues else "FAIL_INTAKE_EVIDENCE",
            "target_month": manifest.get("target_month"), "issues": issues,
            "may_compute": False, "may_publish": False,
            "source_content_social_verified": (
                social_validation.startswith('PASS_H35_')
                and not any('SOCIAL_' in issue or 'STAGED_SOURCE_HASH_MISMATCH_social_security' in issue for issue in issues)),
            "frozen_products_checked": frozen["checked_count"]}
