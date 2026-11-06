"""H21 read-only technical certification gate for the H20 frozen checkpoint.

Never creates RC1 golden artifacts. Never equates checkpoint integrity to
regression equivalence or DANE validation. No frozen model is modified.
"""
from __future__ import annotations

from collections import Counter
from importlib import metadata
import json
import platform
import re
from pathlib import Path, PurePosixPath
from icml.domain.cutoff import FROZEN_CUTOFF

from icml.operations.h20 import verify_products
from icml.regression.catalog import load_catalog
from icml.regression.golden import check_integrity

NUMERICAL_PACKAGES = ("numpy", "scipy", "pandas", "statsmodels",
                      "tempdisagg", "scikit-learn", "xgboost")
REQUIRED_PYTHON = (3, 12)


def audit(root: Path, golden_dir: Path | None = None) -> dict:
    """Check frozen-product integrity, historical RC1 and locked runtime.

    The output is evidence for a release review, not a release authorization.
    Missing external references are counted as NOT_EXECUTED, never PASS.
    """
    root = root.resolve()
    code = root
    lock = code / "requirements/lock-py312.txt"
    catalog_path = code / "configs/golden/rc1_catalog.toml"
    if not lock.is_file() or not catalog_path.is_file():
        raise FileNotFoundError("Missing H20 lock or RC1 catalog")
    locked = {}
    for line in lock.read_text(encoding="utf-8").splitlines():
        match = re.fullmatch(r"([A-Za-z0-9_.-]+)==([^\s#]+)", line.strip())
        if match:
            locked[match.group(1).lower()] = match.group(2)
    runtime = {}
    mismatch = []
    for package in NUMERICAL_PACKAGES:
        try:
            installed = metadata.version(package)
        except metadata.PackageNotFoundError:
            installed = None
        expected = locked.get(package)
        runtime[package] = {"locked": expected, "installed": installed,
                            "match": installed is not None and installed == expected}
        if installed != expected:
            mismatch.append(package)
    py = platform.python_version()
    py_ok = tuple(map(int, py.split(".")[:2])) == REQUIRED_PYTHON
    products = verify_products(root)
    catalog = load_catalog(catalog_path)
    # A duplicated file path is legitimate when two IDs reference identical bytes,
    # but conflicting digest declarations are never allowed.
    seen = {}
    catalog_problems = []
    for a in catalog.artifacts:
        path = PurePosixPath(a.legacy_path)
        if path.is_absolute() or ".." in path.parts:
            catalog_problems.append({"id": a.artifact_id, "problem": "unsafe_path"})
        elif path.as_posix() in seen and seen[path.as_posix()] != a.sha256:
            catalog_problems.append({"id": a.artifact_id, "problem": "contradictory_sha256"})
        seen[path.as_posix()] = a.sha256
    counts = dict(sorted(Counter(a.role.value for a in catalog.artifacts).items()))
    if golden_dir is None:
        golden = {"status": "NOT_EXECUTED_EXTERNAL_ARTIFACTS_ABSENT", "expected": len(catalog.artifacts),
                  "verified": 0, "missing": len(catalog.artifacts), "mismatched": 0,
                  "source": None}
    else:
        issues = check_integrity(golden_dir.resolve(), catalog)
        missing = sum(issue.problem == "missing" for issue in issues)
        wrong = sum(issue.problem != "missing" for issue in issues)
        golden = {"status": "PASS_REFERENCE_INTEGRITY_ONLY" if not issues else "FAIL_REFERENCE_INTEGRITY",
                  "expected": len(catalog.artifacts), "verified": len(catalog.artifacts)-len(issues),
                  "missing": missing, "mismatched": wrong, "source": str(golden_dir.resolve()),
                  "issues": [{"id": i.artifact_id, "problem": i.problem} for i in issues]}
    products_ok = not products["issues"] and products["checked_count"] == 8
    reference_ok = golden["status"] == "PASS_REFERENCE_INTEGRITY_ONLY"
    env_ok = py_ok and not mismatch
    from icml import __version__
    return {
        "hito": 21, "baseline": "RC1 original / H20 frozen products", "candidate": __version__,
        "cutoff": FROZEN_CUTOFF, "products": {"status": "PASS" if products_ok else "FAIL",
                                      "count": products["checked_count"], "issues": products["issues"]},
        "python": {"installed": py, "required_minor": "3.12", "match": py_ok},
        "numerical_environment": {"status": "PASS" if env_ok else "UNMATCHED_LOCK",
                                  "mismatched": mismatch, "packages": runtime},
        "rc1_catalog": {"reference": catalog.reference, "artifacts": len(catalog.artifacts),
                        "unique_paths": len(seen), "by_role": counts,
                        "status": "PASS" if not catalog_problems else "FAIL",
                        "issues": catalog_problems},
        "golden": golden,
        "operational_integrity": "PASS_FROZEN_PRODUCTS" if products_ok else "FAIL",
        "rc1_equivalence": "NOT_TESTED" if not reference_ok else "REFERENCE_HASHES_OK_TEST_SUITE_REQUIRED",
        "release_gate": "BLOCKED" if not (products_ok and reference_ok and env_ok and not catalog_problems)
                                      else "ELIGIBLE_FOR_FULL_RC1_TEST_SUITE_NOT_YET_CERTIFIED",
        "published_official": False,
        "notes": ["Product hashes are not independent statistical validation.",
                  "RC1 golden hash integrity alone does not execute the six-stage RC1 chain.",
                  "No new DANE month has been processed by this gate."],
    }


def write_report(root: Path, output: Path, golden_dir: Path | None = None) -> dict:
    """Write into a NEW report file, never overwrite evidence."""
    if output.exists():
        raise FileExistsError(output)
    report = audit(root, golden_dir)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    return report
