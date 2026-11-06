"""H20 frozen products: immutable staging and accurate failures."""
import csv
from pathlib import Path

import pytest

from icml.operations.frozen_products import EXPECTED_IDS, file_hash, verify_products, freeze_products


def fixture_bundle(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    cat = root / "datos/2_procesamiento/productos_congelados/catalogo_h19/19_catalogo_unificado.csv"
    cat.parent.mkdir(parents=True)
    with cat.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["producto","ruta","sha256","evidencia","estatus","universo"])
        writer.writeheader()
        for name in sorted(EXPECTED_IDS):
            rel = Path("inputs") / (name.replace('.', '_')+".csv")
            (root / rel).parent.mkdir(exist_ok=True)
            (root / rel).write_text(name+"\n", encoding="utf-8")
            writer.writerow({"producto":name,"ruta":str(rel),"sha256":file_hash(root / rel),
                             "evidencia":"historical","estatus":"RESEARCH", "universo":"completo"})
    return root, cat


def test_valid_frozen_catalogue(tmp_path):
    root, _ = fixture_bundle(tmp_path)
    result = verify_products(root)
    assert result["status"] == "PASS_FROZEN_FILE_INTEGRITY"
    assert result["checked_count"] == 8
    assert not result["automatic_publication_authorized"]


def test_hash_mismatch_blocks_delivery(tmp_path):
    root, _ = fixture_bundle(tmp_path)
    (root / "inputs/labor_ciudades.csv").write_text("tampered\n")
    assert any(e["error"] == "sha256_mismatch" for e in verify_products(root)["issues"])
    with pytest.raises(ValueError):
        freeze_products(root, tmp_path / "release")
    assert not (tmp_path / "release").exists()


def test_immutable_snapshot(tmp_path):
    root, _ = fixture_bundle(tmp_path)
    dest = tmp_path / "release"
    result = freeze_products(root, dest)
    assert result["products"] == 8
    assert (dest / "MANIFEST.json").exists()
    assert not result["publication_authorized"]
    with pytest.raises(FileExistsError):
        freeze_products(root, dest)


def test_path_traversal_is_refused(tmp_path):
    root, cat = fixture_bundle(tmp_path)
    text = cat.read_text().replace("inputs/labor_ciudades.csv", "../../file.csv")
    cat.write_text(text)
    assert any(e["error"] == "path_outside_bundle" for e in verify_products(root)["issues"])


def test_catalog_missing_product_fails(tmp_path):
    root, cat = fixture_bundle(tmp_path)
    lines = cat.read_text().splitlines()
    cat.write_text("\n".join(lines[:-1])+"\n")
    assert any(e["error"] == "catalogue_ids_mismatch" for e in verify_products(root)["issues"])
