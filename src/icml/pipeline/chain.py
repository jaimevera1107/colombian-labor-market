"""Stage registry and the end-to-end run.

Every stage is declared once: its configuration file, the upstream runs
it consumes and whether it reads the source tree. The CLI and the full
run use the same registry, so a stage is always invoked the same way.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from icml.config import config_sha256
from icml.integration.pipeline import (
    IntegrationPipeline,
    load_integration_config,
)
from icml.io.artifacts import ArtifactStore
from icml.io.hashing import sha256_file
from icml.modeling.pipeline import ModelingPipeline, load_modeling_config
from icml.national.pipeline import NationalPipeline, load_national_config
from icml.pipeline.manifest import RunManifest, validate_run_id
from icml.pipeline.stage import StageResult
from icml.reconciliation.pipeline import (
    OUTPUTS as PRODUCT_OUTPUTS,
)
from icml.quality.pipeline import OUTPUTS as QUALITY_OUTPUTS
from icml.reconciliation.pipeline import (
    ReconciliationPipeline,
    load_reconciliation_config,
)
from icml.urban.pipeline import UrbanPipeline, load_urban_config

MANIFEST = "manifest.json"
PRODUCTS = (
    "national",
    "departmental",
    "urban_signals",
    "departmental_factors",
    "national_icml",
    "official_deviation",
    "ciudades",
    "departamentos",
    "nacionales",
)


@dataclass(frozen=True)
class StageDefinition:
    """How to configure and invoke one stage."""

    name: str
    config_file: str
    upstream: tuple[str, ...]
    reads_sources: bool
    execute: Callable[
        [Path, Path | None, dict[str, ArtifactStore], ArtifactStore],
        StageResult,
    ]
    in_full_run: bool = True


def _national(
    config: Path,
    sources: Path | None,
    upstream: dict[str, ArtifactStore],
    output: ArtifactStore,
) -> StageResult:
    return NationalPipeline(load_national_config(config)).run(
        _required(sources), output
    )


def _urban(
    config: Path,
    sources: Path | None,
    upstream: dict[str, ArtifactStore],
    output: ArtifactStore,
) -> StageResult:
    return UrbanPipeline(load_urban_config(config)).run(
        _required(sources), upstream["national"], output
    )


def _departmental(
    config: Path,
    sources: Path | None,
    upstream: dict[str, ArtifactStore],
    output: ArtifactStore,
) -> StageResult:
    from icml.departmental.pipeline import DepartmentalPipeline, load_departmental_config
    return DepartmentalPipeline(load_departmental_config(config)).run(
        _required(sources), upstream["national"], output
    )


def _integration(
    config: Path,
    sources: Path | None,
    upstream: dict[str, ArtifactStore],
    output: ArtifactStore,
) -> StageResult:
    return IntegrationPipeline(load_integration_config(config)).run(
        _required(sources),
        upstream["national"],
        upstream["urban"],
        upstream["departmental"],
        output,
    )


def _modeling(
    config: Path,
    sources: Path | None,
    upstream: dict[str, ArtifactStore],
    output: ArtifactStore,
) -> StageResult:
    return ModelingPipeline(load_modeling_config(config)).run(
        upstream["integration"], upstream["departmental"], output
    )


def _reconciliation(
    config: Path,
    sources: Path | None,
    upstream: dict[str, ArtifactStore],
    output: ArtifactStore,
) -> StageResult:
    return ReconciliationPipeline(load_reconciliation_config(config)).run(
        upstream["modeling"],
        upstream["integration"],
        upstream["departmental"],
        output,
    )


def _quality(
    config: Path,
    sources: Path | None,
    upstream: dict[str, ArtifactStore],
    output: ArtifactStore,
) -> StageResult:
    from icml.quality.pipeline import QualityPipeline, load_quality_config

    return QualityPipeline(load_quality_config(config)).run(
        upstream["reconciliation"], output
    )


def _evaluation(
    config: Path,
    sources: Path | None,
    upstream: dict[str, ArtifactStore],
    output: ArtifactStore,
) -> StageResult:
    from icml.evaluation.pipeline import TransferEvaluationPipeline

    return TransferEvaluationPipeline(config).run(
        upstream["integration"], upstream["departmental"], output
    )


def _informality(
    config: Path,
    sources: Path | None,
    upstream: dict[str, ArtifactStore],
    output: ArtifactStore,
) -> StageResult:
    """Hito 5, explicitly optional: original sources and frozen quality run."""
    from icml.informality.national import (
        InformalityNationalPipeline, load_informality_config,
    )
    return InformalityNationalPipeline(load_informality_config(config)).run(
        _required(sources), upstream["quality"], output,
    )




def _census_bridge(
    config: Path,
    sources: Path | None,
    upstream: dict[str, ArtifactStore],
    output: ArtifactStore,
) -> StageResult:
    """Optional post-quality census anchor; never rewrite canonical products."""
    import tomllib
    from icml.census_bridge import run as run_census
    from icml.io.artifacts import ArtifactRecord
    from types import SimpleNamespace
    from icml.quality.pipeline import OUTPUTS as QUALITY

    options = tomllib.loads(config.read_text(encoding="utf-8"))["census_bridge"]
    if options != {
        "anchor_file": "cnpv_2018_capitales_ajustado.csv",
        "mode": "full_primary_geih_component_transfer",
        "census_anchor_year": 2018,
        "status": "experimental_read_only",
    }:
        raise ValueError("Unsupported census-bridge configuration; check vintage")
    source = _required(sources)
    census = source if source.is_file() else source / options["anchor_file"]
    if not census.is_file():
        raise FileNotFoundError(census)
    qualified = upstream["quality"]
    input_paths = [qualified.resolve(QUALITY[q]) for q in ("departamentos", "ciudades", "nacionales")]
    report = run_census(*input_paths, census, output.root / "products")
    # Records are based on the materialized artifacts for immutable stage manifests.
    from icml.io.hashing import sha256_file as _hash
    def make_record(name: str, path: Path, input_record: bool = False) -> ArtifactRecord:
        import pandas as pd
        frame = pd.read_csv(path, encoding="utf-8-sig")
        return ArtifactRecord(name, path.as_posix() if input_record else path.relative_to(output.root).as_posix(),
                              _hash(path),len(frame),len(frame.columns))
    outputs = tuple(make_record(f"census_bridge.product_{i}", output.root / "products" / x)
         for i,x in enumerate(("01_ancla_cnpv_2018_nueve.csv",
            "02_puente_dos_universos_33_territorios.csv",
            "03_nacionales_censo_y_geih.csv", "04_comparacion_direccion_transferencia.csv",
            "05_puertas_calidad.csv"),start=1))
    inputs=tuple(make_record(f"census_bridge.input_{i}", p, input_record=True)
        for i,p in enumerate([*input_paths,census],start=1))
    return SimpleNamespace(outputs=outputs, inputs=inputs, diagnostics=report)

def _required(sources: Path | None) -> Path:
    if sources is None:
        raise ValueError("This stage needs --sources")
    return sources


# Stage names and their dependency metadata are defined once in stage_registry.
# The execution table below only binds the appropriate stage function.
from icml.pipeline.stage_registry import STAGE_SPECS
_EXECUTORS = {
    "census_bridge": _census_bridge,
    "national": _national,
    "urban": _urban,
    "departmental": _departmental,
    "integration": _integration,
    "modeling": _modeling,
    "reconciliation": _reconciliation,
    "quality": _quality,
    "informality": _informality,
    "evaluation": _evaluation,
}
STAGES: dict[str, StageDefinition] = {
    key: StageDefinition(
        name=spec.name,
        config_file=spec.config_file,
        upstream=spec.upstream,
        reads_sources=spec.reads_sources,
        execute=_EXECUTORS[key],
        in_full_run=spec.in_full_run,
    )
    for key, spec in STAGE_SPECS.items()
}


def completed_run(path: Path) -> ArtifactStore:
    """Open a finished stage run (it must have a manifest).

    Raises
    ------
    FileNotFoundError
        If the folder is not a completed run.
    """
    if not (path / MANIFEST).is_file():
        raise FileNotFoundError(f"Not a completed run: {path}")
    return ArtifactStore(path)


def new_run_root(runs_dir: Path, run_id: str) -> Path:
    """Return a fresh run folder path (runs are immutable).

    Raises
    ------
    FileExistsError
        If the run folder already exists.
    """
    root = runs_dir / validate_run_id(run_id)
    if root.exists():
        raise FileExistsError(f"Run folder already exists: {root}")
    return root


def run_stage(
    name: str,
    config: Path,
    sources: Path | None,
    upstream: Mapping[str, Path],
    run_root: Path,
    run_id: str,
) -> RunManifest:
    """Run one stage into ``run_root`` and write its manifest.

    Raises
    ------
    ValueError
        If an upstream run is missing.
    """
    stage = STAGES[name]
    missing = set(stage.upstream) - set(upstream)
    if missing:
        raise ValueError(f"{name} needs upstream runs: {sorted(missing)}")
    stores = {key: completed_run(upstream[key]) for key in stage.upstream}
    result = stage.execute(config, sources, stores, ArtifactStore(run_root))
    manifest = RunManifest(
        run_id=run_id,
        stage=name,
        config_sha256=config_sha256(config),
        inputs=result.inputs,
        outputs=result.outputs,
    )
    manifest.write(run_root / MANIFEST)
    return manifest


def run_all(configs: Path, sources: Path, runs_dir: Path, run_id: str,
            census_source: Path | None = None) -> Path:
    """Run every stage in order under ``runs_dir/run_id/<stage>``.

    Writes ``run.json`` with the stage folders and the SHA-256 of the
    three products, and returns the run folder.
    """
    root = new_run_root(runs_dir, run_id)
    folders: dict[str, Path] = {}
    stages = {n: s for n, s in STAGES.items() if s.in_full_run}
    for name, stage in stages.items():
        folders[name] = root / name
        run_stage(
            name,
            configs / stage.config_file,
            sources if stage.reads_sources else None,
            {key: folders[key] for key in stage.upstream},
            folders[name],
            f"{run_id}-{name}",
        )
    if census_source is not None:
        folders["census_bridge"] = root / "census_bridge"
        run_stage("census_bridge", configs / "census_bridge.toml", census_source,
                  {"quality":folders["quality"]},folders["census_bridge"],
                  f"{run_id}-census_bridge")
    products = {}
    for product in PRODUCTS:
        stage_name = "quality" if product in ("ciudades", "departamentos", "nacionales") else "reconciliation"
        spec = QUALITY_OUTPUTS[product] if stage_name == "quality" else PRODUCT_OUTPUTS[product]
        path = folders[stage_name] / spec.relative_path
        products[product] = {
            "path": path.relative_to(root).as_posix(),
            "sha256": sha256_file(path),
        }
    gate_summary = json.loads((folders["quality"] / "audit/summary.json").read_text(encoding="utf-8"))
    summary = {
        "run_id": run_id,
        "quality_gate": {
            "status": gate_summary["status"],
            "certified_for_publication": gate_summary["status"] == "APTO",
            "report_path": "quality/audit/summary.json",
            "report_sha256": sha256_file(folders["quality"] / "audit/summary.json"),
        },
        "stages": list(stages) + (["census_bridge"] if census_source is not None else []),
        "configs": {
            name: config_sha256(configs / s.config_file)
            for name, s in stages.items()
        },
        "products": products,
    }
    if census_source is not None:
        summary["configs"]["census_bridge"] = config_sha256(configs / "census_bridge.toml")
        summary["census_bridge"] = {
           "status": "EXPERIMENTAL_NOT_CANONICAL",
           "input_census_sha256": sha256_file(census_source if census_source.is_file() else census_source / "cnpv_2018_capitales_ajustado.csv"),
           "manifest_path": "census_bridge/manifest.json",
        }
    (root / "run.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    return root
