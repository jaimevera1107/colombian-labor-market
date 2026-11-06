"""H20 immutable, non-official frozen-product delivery.

Integrity is a technical gate, never scientific or DANE certification.
No model fit, historical revision, source mutation or publication occurs here.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path

from icml.domain.cutoff import FROZEN_CUTOFF

# Product IDs are intentionally explicit: a missing product cannot silently
# disappear from the catalogue just because the catalogue was edited.
EXPECTED_IDS = frozenset({
    "labor.ciudades", "labor.departamentos", "labor.nacionales",
    "informalidad.ciudades", "informalidad.departamentos",
    "informalidad.nacionales", "sectorial.departamental", "sectorial.nacional",
})


def file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def verify_products(root: Path, catalog: Path | None = None) -> dict:
    """Validate the eight frozen products against signed-off H19 digests.

    A successful return does not establish golden equivalence, external DANE
    validation, statistical certainty or official publication permission.
    """
    root = root.resolve()
    catalog = catalog or root / "datos/2_procesamiento/productos_congelados/catalogo_h19/19_catalogo_unificado.csv"
    with catalog.open("r", encoding="utf-8-sig", newline="") as f:
        entries = list(csv.DictReader(f))
    issues: list[dict] = []
    ids = [e["producto"] for e in entries]
    if len(ids) != len(set(ids)):
        issues.append({"error": "duplicate_product_ids"})
    if set(ids) != EXPECTED_IDS:
        issues.append({"error": "catalogue_ids_mismatch", "missing": sorted(EXPECTED_IDS-set(ids)),
                       "unexpected": sorted(set(ids)-EXPECTED_IDS)})
    checked = []
    seen_paths = set()
    for e in entries:
        rel = Path(e["ruta"])
        target = (root / rel).resolve()
        if target != root and root not in target.parents:
            issues.append({"product": e["producto"], "error": "path_outside_bundle"})
            continue
        if str(target) in seen_paths:
            issues.append({"product": e["producto"], "error": "duplicate_file_path"})
        seen_paths.add(str(target))
        expected = e["sha256"].strip().lower()
        if len(expected) != 64 or not all(c in '0123456789abcdef' for c in expected):
            issues.append({"product": e["producto"], "error": "invalid_hash"})
            continue
        if not target.is_file():
            issues.append({"product": e["producto"], "error": "file_missing", "path": e["ruta"]})
            continue
        digest = file_hash(target)
        if digest != expected:
            issues.append({"product": e["producto"], "error": "sha256_mismatch", "path": e["ruta"]})
        checked.append({"product": e["producto"], "path": e["ruta"], "bytes": target.stat().st_size,
                        "sha256": digest, "evidence": e["evidencia"], "status": e["estatus"],
                        "universe": e["universo"]})
    return {"status": "PASS_FROZEN_FILE_INTEGRITY" if not issues else "FAIL_FROZEN_FILE_INTEGRITY",
            "software_version": "2.2.21.dev0", "period_through": FROZEN_CUTOFF,
            "checked_count": len(checked), "expected_count": len(EXPECTED_IDS),
            "issues": issues, "products": checked,
            "golden_102": "NOT_CERTIFIED", "new_real_month": "NOT_TESTED",
            "scientific_certification": "NOT_ESTABLISHED",
            "official_DANE_statistics": False, "automatic_publication_authorized": False}


def freeze_products(root: Path, destination: Path, catalog: Path | None = None) -> dict:
    """Stage an immutable, clearly experimental product delivery atomically.

    Refuses existing paths and never overwrites any prior vintage.
    """
    root = root.resolve()
    destination = destination.resolve()
    report = verify_products(root, catalog)
    if report["issues"]:
        raise ValueError("Frozen product integrity failed; no snapshot was produced")
    if destination.exists():
        raise FileExistsError(f"Immutable delivery already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    # All copied files are verified again before the temporary dir is promoted.
    with tempfile.TemporaryDirectory(prefix=".icml_h20_staging_", dir=destination.parent) as tmp:
        staged = Path(tmp) / "snapshot"
        staged.mkdir()
        records = []
        for item in report["products"]:
            rel = Path(item["path"])
            target = staged / "productos" / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(root / rel, target)
            if file_hash(target) != item["sha256"]:
                raise IOError(f"Transferred bytes differ for {item['product']}")
            records.append({**item, "delivery_path": str(Path("productos") / rel)})
        manifest = {"status": "RESEARCH_SNAPSHOT_FROZEN_NON_OFFICIAL",
                    "software_version": report["software_version"],
                    "period_through": report["period_through"],
                    "publication_authorized": False,
                    "golden_102": "NOT_CERTIFIED", "real_month_update": "NOT_TESTED",
                    "products": records}
        (staged / "MANIFEST.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True)+"\n", encoding="utf-8")
        os.replace(staged, destination)
    return {"status": "FROZEN_RESEARCH_DELIVERY", "destination": str(destination),
            "products": len(records), "publication_authorized": False}
