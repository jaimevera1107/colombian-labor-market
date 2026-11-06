"""Departmental pipeline: anchors, reconstruction, population revision."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, TypeVar

from icml.config import build_dataclass, load_toml, section
from icml.departmental.anchors import (
    AnchorPolicy,
    annual_projections,
    close_annual_anchors,
    compare_population,
)
from icml.departmental.annex import DepartmentAnnexReader, DepartmentAnnexSpec
from icml.departmental.population import (
    DemographicPopulationBackcast,
    PopulationPolicy,
)
from icml.departmental.reconstruction import (
    DepartmentalReconstruction,
    ReconstructionPolicy,
)
from icml.departmental.sensitivity import (
    RhoSensitivityAudit,
    RhoSensitivityPolicy,
)
from icml.domain.territories import territory_codes
from icml.io.artifacts import ArtifactRecord, ArtifactSpec, ArtifactStore
from icml.io.hashing import sha256_file
from icml.national.pipeline import OUTPUTS as NATIONAL_OUTPUTS
from icml.national.reference import reference_national

_Spec = TypeVar("_Spec")


@dataclass(frozen=True)
class DepartmentalSources:
    """Locations of the departmental inputs."""

    annex: str
    population_projections: str


@dataclass(frozen=True)
class DepartmentalConfig:
    """Complete configuration of the departmental stage."""

    sources: DepartmentalSources
    annex: DepartmentAnnexSpec
    anchors: AnchorPolicy
    reconstruction: ReconstructionPolicy
    population: PopulationPolicy
    rho_sensitivity: RhoSensitivityPolicy


def load_departmental_config(path: Path) -> DepartmentalConfig:
    """Load and validate the departmental configuration from TOML."""
    payload = load_toml(path)

    def build(cls: type[_Spec], name: str) -> _Spec:
        return build_dataclass(
            cls,
            section(payload, f"departmental.{name}"),
            context=f"departmental.{name}",
        )

    return DepartmentalConfig(
        sources=build(DepartmentalSources, "sources"),
        annex=build(DepartmentAnnexSpec, "annex"),
        anchors=build(AnchorPolicy, "anchors"),
        reconstruction=build(ReconstructionPolicy, "reconstruction"),
        population=build(PopulationPolicy, "population"),
        rho_sensitivity=build(RhoSensitivityPolicy, "rho_sensitivity"),
    )


def _output(name: str, keys: tuple[str, ...] = ()) -> ArtifactSpec:
    return ArtifactSpec(
        f"departmental.{name}", f"departmental/{name}.csv", keys=keys
    )


OUTPUTS: dict[str, ArtifactSpec] = {
    "official_anchors": _output("official_anchors", ("dep_code", "year")),
    "closed_anchors": _output("closed_anchors", ("dep_code", "year")),
    "anchor_corrections": _output(
        "anchor_corrections", ("dep_code", "year", "quantity")
    ),
    "annual_projections": _output("annual_projections", ("dep_code", "year")),
    "population_vs_projection": _output(
        "population_vs_projection", ("dep_code", "year")
    ),
    "monthly_initial": _output("monthly_initial", ("dep_code", "period")),
    "chow_lin_diagnostics": _output(
        "chow_lin_diagnostics", ("dep_code", "quantity")
    ),
    "monthly_revised": _output("monthly_revised", ("dep_code", "period")),
    "population_calibration": _output("population_calibration", ("dep_code",)),
    "population_backtest": _output(
        "population_backtest", ("dep_code", "method")
    ),
    "link_audit": _output("link_audit", ("dep_code", "quantity")),
    "rho_sensitivity": _output("rho_sensitivity", ("period",)),
    "rho_profile": _output("rho_profile", ("rho",)),
}


@dataclass(frozen=True)
class DepartmentalRunResult:
    """Records of the artifacts written and stage diagnostics."""

    outputs: tuple[ArtifactRecord, ...]
    inputs: tuple[ArtifactRecord, ...]
    diagnostics: dict[str, Any]


class DepartmentalPipeline:
    """Run the departmental stages on top of a national run."""

    def __init__(self, config: DepartmentalConfig) -> None:
        """Compose the stage components."""
        self._config = config
        self._reader = DepartmentAnnexReader(config.annex)
        self._reconstruction = DepartmentalReconstruction(
            config.reconstruction
        )
        self._population = DemographicPopulationBackcast(config.population)
        policy = config.reconstruction
        self._sensitivity = RhoSensitivityAudit(
            config.rho_sensitivity,
            policy.method,
            policy.include_intercept,
            policy.anchor_tolerance_persons,
            policy.anchor_start_period,
            policy.end_period,
        )

    def run(
        self,
        sources_root: Path,
        national: ArtifactStore,
        output: ArtifactStore,
    ) -> DepartmentalRunResult:
        """Execute the departmental stages and write their artifacts."""
        config = self._config
        source_store = ArtifactStore(sources_root)
        annex_path = sources_root.joinpath(
            *PurePosixPath(config.sources.annex).parts
        )
        official = self._reader.read(annex_path)
        projections_raw = source_store.read(
            ArtifactSpec(
                "source.population_projections",
                config.sources.population_projections,
            )
        )
        reference = reference_national(
            national.read(NATIONAL_OUTPUTS["combined_with_provenance"]),
            national.read(NATIONAL_OUTPUTS["reconciled_monthly"]),
            config.reconstruction.end_period,
        )

        closed, corrections = close_annual_anchors(official, config.anchors)
        projections = annual_projections(
            projections_raw, set(territory_codes()), config.anchors
        )
        comparison = compare_population(official, projections)
        initial = self._reconstruction.run(closed, reference)
        revision = self._population.run(
            initial.panel, projections, closed, reference
        )
        sensitivity = self._sensitivity.run(closed, reference)

        tables = {
            "official_anchors": official,
            "closed_anchors": closed,
            "anchor_corrections": corrections,
            "annual_projections": projections,
            "population_vs_projection": comparison,
            "monthly_initial": initial.panel,
            "chow_lin_diagnostics": initial.diagnostics,
            "monthly_revised": revision.panel,
            "population_calibration": revision.calibration,
            "population_backtest": revision.backtest,
            "link_audit": revision.link_audit,
            "rho_sensitivity": sensitivity.series,
            "rho_profile": sensitivity.profile,
        }
        records = tuple(
            output.write(OUTPUTS[name], table)
            for name, table in tables.items()
        )
        diagnostics = {
            "population_revision": revision.quality,
            "rho_sensitivity": sensitivity.summary,
        }
        path = output.root / "departmental" / "diagnostics.json"
        if path.exists():
            raise FileExistsError(path)
        path.write_text(
            json.dumps(diagnostics, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        annex_record = ArtifactRecord(
            artifact_id="source.departmental_annex",
            relative_path=config.sources.annex,
            sha256=sha256_file(annex_path),
            n_rows=int(len(official)),
            n_columns=int(official.shape[1]),
        )
        return DepartmentalRunResult(
            outputs=records,
            inputs=(annex_record, *source_store.records, *national.records),
            diagnostics=diagnostics,
        )
