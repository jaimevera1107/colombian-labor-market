"""Canonical source inventory for the frozen ICML August 2026 vintage.

Auditing and staging never mutate a checkpoint, active TOMLs, or frozen data.
New monthly vintages require paired DANE annexes and the H22b approval gate.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import tomllib
from pathlib import Path


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _safe(root: Path, rel: str) -> Path:
    path = (root / rel).resolve()
    if path == root or root not in path.parents:
        raise ValueError(f"Unsafe source path: {rel}")
    return path


def audit_catalog(root: Path) -> dict:
    root = Path(root).resolve()
    catalog = json.loads((root / "datos/2_procesamiento/catalogos/catalogo_fuentes.json").read_text(encoding="utf-8"))
    checked = []
    issues = []
    for role, record in catalog["sources"].items():
        try:
            path = _safe(root, record["path"])
        except ValueError as exc:
            issues.append({"role": role, "issue": str(exc)})
            continue
        actual = digest(path) if path.is_file() else None
        if actual != record["sha256"]:
            issues.append({"role": role, "issue": "missing_or_hash_mismatch", "path": record["path"]})
        section, name = role.split(".", 1)
        configuration = root / "configs/rc1" / f"{section}.toml"
        try:
            configured = tomllib.loads(configuration.read_text(encoding="utf-8"))[section]["sources"][name]
        except (KeyError, FileNotFoundError) as exc:
            issues.append({"role": role, "issue": f"missing_config: {exc}"})
            configured = None
        if configured != record["path"]:
            issues.append({"role": role, "issue": "config_catalog_mismatch", "configured": configured})
        checked.append({"role": role, "path": record["path"], "sha256": actual, "active": True})
    for aux in catalog.get("auxiliary_inputs", []):
        try:
            path = _safe(root, aux["path"])
        except ValueError as exc:
            issues.append({"role": "auxiliary", "issue": str(exc)})
            continue
        if not path.is_file() or digest(path) != aux["sha256"]:
            issues.append({"role": "auxiliary", "issue": "missing_or_hash_mismatch", "path": aux["path"]})
    # All relevant stage inputs have to be catalogued; fail closed on untracked config.
    for section in ("national", "urban", "departmental", "integration"):
        config = tomllib.loads((root / "configs/rc1" / f"{section}.toml").read_text(encoding="utf-8"))
        for name in config[section]["sources"]:
            if f"{section}.{name}" not in catalog["sources"]:
                issues.append({"role": f"{section}.{name}", "issue": "uncatalogued_source"})
    return {"status": "PASS" if not issues else "BLOCKED", "sources": checked,
            "count": len(checked), "unique_paths": len({x["path"] for x in checked}),
            "issues": issues, "period_through": catalog["period_through"],
            "auxiliary_count": len(catalog.get("auxiliary_inputs", []))}


def stage_new_source(root: Path, role: str, incoming: Path, output: Path,
                     reference_period: str) -> dict:
    """Copy a prospective replacement OUTSIDE a checkpoint, without activation."""
    root, incoming, output = Path(root).resolve(), Path(incoming).resolve(), Path(output).resolve()
    if output == root or root in output.parents:
        raise ValueError("Staging must be OUTSIDE immutable ICML checkpoint")
    if output.exists():
        raise FileExistsError(output)
    audit = audit_catalog(root)
    if audit["status"] != "PASS":
        raise ValueError("Cannot stage source against an invalid catalog")
    catalog = json.loads((root / "datos/2_procesamiento/catalogos/catalogo_fuentes.json").read_text(encoding="utf-8"))
    if role not in catalog["sources"]:
        raise KeyError(role)
    if not incoming.is_file() or incoming.suffix.lower() not in (".csv", ".xlsx", ".xls", ".json"):
        raise ValueError("Expected an existing CSV/Excel/JSON source file")
    record = catalog["sources"][role]
    if Path(record["path"]).suffix.lower() != incoming.suffix.lower():
        raise ValueError("Different format from the active input: requires a reader-compatibility review")
    output.mkdir(parents=True)
    stored = output / incoming.name
    shutil.copy2(incoming, stored)
    manifest = {"role": role, "reference_period": reference_period,
                "new_file": stored.name, "new_sha256": digest(stored),
                "existing_sha256": record["sha256"], "active_checkpoint_unchanged": True,
                "status": "STAGED_REQUIRES_SCHEMA_AND_VINTAGE_APPROVAL",
                "note": "Monthly updates require both DANE annexes with the same ending month."}
    (output / "staging.json").write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    return manifest


def synchronize_stage_configs(root: Path, *, apply: bool = False) -> dict:
    """Synchronize only source pointers from catalog into stage TOMLs.

    Never copy/alter sources or model parameters. Monthly pointers are not
    activated by this command: they require the paired-annex vintage gate.
    Operate on a fresh working COPY when applying annual or historical updates.
    """
    import re
    root = Path(root).resolve()
    catalog = json.loads((root / "datos/2_procesamiento/catalogos/catalogo_fuentes.json").read_text(encoding="utf-8"))
    pending = []
    blocked = []
    edits = {}
    for role, record in catalog["sources"].items():
        path = _safe(root, record["path"])
        if not path.is_file() or digest(path) != record["sha256"]:
            blocked.append({"role": role, "reason": "file_missing_or_digest_mismatch"})
            continue
        section, key = role.split(".", 1)
        cfg = root / "configs/rc1" / f"{section}.toml"
        original = edits.get(cfg, cfg.read_text(encoding="utf-8"))
        current = tomllib.loads(original)[section]["sources"][key]
        if current == record["path"]:
            continue
        change = {"role": role, "old": current, "new": record["path"]}
        pending.append(change)
        if record["type"] == "publicacion_mensual":
            blocked.append({"role": role, "reason": "requires_two_synchronized_DANE_annexes"})
            continue
        expression = re.compile(r'(?m)^(\s*'+re.escape(key)+r'\s*=\s*)"'+re.escape(current)+r'"\s*$')
        updated, count = expression.subn(lambda m: m.group(1)+'"'+record["path"]+'"', original)
        if count != 1:
            blocked.append({"role": role, "reason": "cannot_patch_unique_config_field"})
        else:
            edits[cfg] = updated
    if apply and blocked:
        raise ValueError("Source pointer activation blocked: " + json.dumps(blocked))
    if apply:
        for path, data in edits.items():
            path.write_text(data, encoding="utf-8")
    return {"status": "BLOCKED" if blocked else ("APPLIED" if apply else "READY"),
            "pending": pending, "blocked": blocked, "changed_config_files":len(edits),
            "requires_working_copy_for_apply": True}
