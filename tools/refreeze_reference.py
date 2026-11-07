"""Refreeze the reference vintage from a finished ``icml operations run-integral --mode recompute``.

The frozen products under ``datos/2_procesamiento`` are the reference every
recompute at the frozen cutoff must reproduce. They have to be refrozen,
deliberately and all together, whenever a methodological change or a code
change that alters the numbers is adopted. Doing it by hand is what left
2.4.0 with five of eight products one commit behind the code.

    python -m icml operations run-integral --root . --output /tmp/aug --mode recompute
    python tools/refreeze_reference.py --root . --run /tmp/aug
    icml checksums --write

What it copies, from the run folder into the checkout:

* the three labor products → ``productos_congelados/laboral`` and ``pruebas_calidad``;
* the H9 informality closure (every ``13_*`` file, ``manifest.json``) → ``parametros_congelados/informalidad_cierre_h9``;
* the sectoral exports and ``METADATOS_EXPERIMENTALES.json`` → ``productos_congelados/sectorial``;
* the sectoral predictor bundle (``inputs/`` as used by the run, ``outputs/``) → ``sectorial_h16``.

Then it records the platform in ``productos_congelados/REFERENCE_PLATFORM.json``,
recomputes the hashes in ``catalogo_h19/19_catalogo_unificado.csv``
and ``catalogos/catalogo_fuentes.json`` and checks that the H9 lineage
(``13_resumen.json``) and manifests are consistent. It never runs a model.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

import pandas as pd

PROCESSING = "datos/2_procesamiento"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _copy_tree_files(source: Path, destination: Path) -> list[str]:
    destination.mkdir(parents=True, exist_ok=True)
    copied = []
    for file in sorted(p for p in source.iterdir() if p.is_file()):
        shutil.copy2(file, destination / file.name)
        copied.append(file.name)
    return copied


def refreeze(root: Path, run: Path) -> dict:
    """Copy the products of ``run`` into ``root`` and resync the catalogs."""
    root, run = root.resolve(), run.resolve()
    report = json.loads((run / "integral_execution_report.json").read_text(encoding="utf-8"))
    if not report.get("recalculated_from_sources"):
        raise ValueError("The run must be a full recompute (--mode recompute)")
    if report.get("candidate_cross_audit", {}).get("status") != "PASS":
        raise ValueError("The run's cross audit did not pass; nothing is refrozen")
    proc = root / PROCESSING
    done: dict[str, list[str]] = {}
    labor = run / "labor/quality/products"
    for target in ("productos_congelados/laboral", "productos_congelados/pruebas_calidad"):
        done[target] = _copy_tree_files(labor, proc / target)
    done["parametros_congelados/informalidad_cierre_h9"] = _copy_tree_files(
        run / "informalidad", proc / "parametros_congelados/informalidad_cierre_h9")
    done["productos_congelados/sectorial"] = _copy_tree_files(run / "sectorial", proc / "productos_congelados/sectorial")
    bundle = proc / "sectorial_h16"
    shutil.rmtree(bundle / "outputs", ignore_errors=True)
    done["sectorial_h16/outputs"] = _copy_tree_files(run / "sectorial_calculo/outputs", bundle / "outputs")
    done["sectorial_h16/inputs"] = _copy_tree_files(run / "sectorial_calculo/inputs", bundle / "inputs")

    # Product catalog (CSV with BOM and CRLF, kept as is).
    catalog = proc / "productos_congelados/catalogo_h19/19_catalogo_unificado.csv"
    frame = pd.read_csv(catalog, dtype=str, encoding="utf-8-sig")
    frame["sha256"] = [_sha(root / rel) for rel in frame["ruta"]]
    frame.to_csv(catalog, index=False, encoding="utf-8-sig", lineterminator="\r\n")

    # Source catalog.
    sources = proc / "catalogos/catalogo_fuentes.json"
    data = json.loads(sources.read_text(encoding="utf-8"))
    for entry in list(data["sources"].values()) + data["auxiliary_inputs"]:
        entry["sha256"] = _sha(root / entry["path"])
    sources.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    # The platform the reference was computed on (tree models are not bit-reproducible across platforms).
    from icml.operations.integral import write_reference_platform
    write_reference_platform(root)

    # Lineage checks.
    h9 = proc / "parametros_congelados/informalidad_cierre_h9"
    summary = json.loads((h9 / "13_resumen.json").read_text(encoding="utf-8"))
    lab = proc / "productos_congelados/laboral"
    lineage_ok = all(_sha(lab / name) == digest for name, digest in summary["frozen_sha256"].items())
    manifest = json.loads((h9 / "manifest.json").read_text(encoding="utf-8"))
    manifest_ok = all(_sha(h9 / name) == digest for name, digest in manifest["files_sha256"].items())
    if not (lineage_ok and manifest_ok):
        raise ValueError("The copied H9 closure is not self-consistent; refusing to leave a half-frozen vintage")
    return {"run_status": report["status"], "copied": done, "h9_lineage_consistent": True}


def main(argv: list[str] | None = None) -> int:
    """Command-line entry point."""
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("--root", type=Path, default=Path("."), help="Project root")
    parser.add_argument("--run", type=Path, required=True, help="Output folder of run-integral --mode recompute")
    args = parser.parse_args(argv)
    result = refreeze(args.root, args.run)
    print(json.dumps(result, indent=2))
    print("\nNext: review the diff, update the version and CHANGELOG, then `icml checksums --write`.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
