"""National pipeline: wiring of the national stages and their artifacts.

This module is the only place where national statistics meet storage. Each
stage is a pure component; the pipeline reads sources through an artifact
store, runs the components in order and writes every output once.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, TypeVar

import pandas as pd

from icml.config import build_dataclass, load_toml, section
from icml.domain.provenance import ProvenanceCategory
from icml.io.artifacts import ArtifactRecord, ArtifactSpec, ArtifactStore
from icml.io.hashing import sha256_file
from icml.national.combination import combine_history_with_observed
from icml.national.disaggregation import (
    DisaggregationQualityPolicy,
    DisaggregationSpec,
    NationalDisaggregation,
    SpliceSpec,
)
from icml.national.geih_annex import GeihAnnexReader, GeihAnnexSpec
from icml.national.reconciliation import (
    NationalReconciler,
    ReconciliationPolicy,
)
from icml.national.schema import (
    PERIOD_COLUMN,
    PROVENANCE_COLUMN,
    YEAR_COLUMN,
)
from icml.national.seasonality import (
    SeasonalityPolicy,
    SeasonalPatternTransfer,
)

STAGE_NAME = "national"
_Spec = TypeVar("_Spec")


@dataclass(frozen=True)
class NationalSources:
    """Locations of the national inputs, relative to a sources root."""

    enh_annual: str
    geih_annual: str
    monthly_indicators: str
    geih_monthly_annex: str


@dataclass(frozen=True)
class CombinationSpec:
    """Provenance assigned to the reconstructed months."""

    history_provenance: str

    def __post_init__(self) -> None:
        """Validate the provenance category."""
        ProvenanceCategory(self.history_provenance)


@dataclass(frozen=True)
class NationalConfig:
    """Complete configuration of the national stage."""

    sources: NationalSources
    geih_annex: GeihAnnexSpec
    splice: SpliceSpec
    disaggregation: DisaggregationSpec
    disaggregation_quality: DisaggregationQualityPolicy
    combination: CombinationSpec
    reconciliation: ReconciliationPolicy
    seasonality: SeasonalityPolicy


def load_national_config(path: Path) -> NationalConfig:
    """Load and validate the national configuration from TOML."""
    payload = load_toml(path)

    def build(cls: type[_Spec], name: str) -> _Spec:
        return build_dataclass(
            cls,
            section(payload, f"national.{name}"),
            context=f"national.{name}",
        )

    return NationalConfig(
        sources=build(NationalSources, "sources"),
        geih_annex=build(GeihAnnexSpec, "geih_annex"),
        splice=build(SpliceSpec, "splice"),
        disaggregation=build(DisaggregationSpec, "disaggregation"),
        disaggregation_quality=build(
            DisaggregationQualityPolicy, "disaggregation_quality"
        ),
        combination=build(CombinationSpec, "combination"),
        reconciliation=build(ReconciliationPolicy, "reconciliation"),
        seasonality=build(SeasonalityPolicy, "seasonality"),
    )


def _output(
    name: str, keys: tuple[str, ...] = (), description: str = ""
) -> ArtifactSpec:
    return ArtifactSpec(
        f"national.{name}",
        f"national/{name}.csv",
        keys=keys,
        description=description,
    )


OUTPUTS: dict[str, ArtifactSpec] = {
    "disaggregated_annual": _output(
        "disaggregated_annual",
        (YEAR_COLUMN,),
        "Spliced ENH/GEIH annual anchors.",
    ),
    "disaggregated_monthly": _output(
        "disaggregated_monthly",
        (PERIOD_COLUMN,),
        "Chow-Lin monthly series (identities not yet closed).",
    ),
    "geih_observed_monthly": _output(
        "geih_observed_monthly",
        (PERIOD_COLUMN,),
        "National GEIH monthly quantities read from the annex.",
    ),
    "combined_with_provenance": _output(
        "combined_with_provenance",
        (PERIOD_COLUMN,),
        "Reconstructed history followed by observed GEIH.",
    ),
    "reconciled_annual": _output(
        "reconciled_annual", (YEAR_COLUMN,), "Identity-consistent anchors."
    ),
    "reconciled_monthly": _output(
        "reconciled_monthly",
        (PERIOD_COLUMN,),
        "Months rescaled to the reconciled anchors.",
    ),
    "reconciliation_annual_adjustments": _output(
        "reconciliation_annual_adjustments"
    ),
    "reconciliation_monthly_factors": _output(
        "reconciliation_monthly_factors"
    ),
    "reconciliation_seam": _output("reconciliation_seam"),
    "seasonal_monthly": _output(
        "seasonal_monthly",
        (PERIOD_COLUMN,),
        "Reconciled months with the GEIH seasonal pattern transferred.",
    ),
    "seasonal_profiles": _output("seasonal_profiles"),
    "seasonal_seam": _output("seasonal_seam"),
}


@dataclass(frozen=True)
class NationalRunResult:
    """Records of every artifact written and the stage diagnostics."""

    outputs: tuple[ArtifactRecord, ...]
    inputs: tuple[ArtifactRecord, ...]
    diagnostics: dict[str, Any]


class NationalPipeline:
    """Run the national stages from sources to the seasonal series."""

    def __init__(self, config: NationalConfig) -> None:
        """Compose the stage components from the configuration."""
        self._config = config
        self._reader = GeihAnnexReader(config.geih_annex)
        self._disaggregation = NationalDisaggregation(
            config.splice,
            config.disaggregation,
            config.disaggregation_quality,
        )
        self._reconciler = NationalReconciler(config.reconciliation)
        self._seasonality = SeasonalPatternTransfer(config.seasonality)

    def run(
        self, sources_root: Path, output: ArtifactStore
    ) -> NationalRunResult:
        """Execute all national stages and write their artifacts."""
        sources = self._config.sources
        source_store = ArtifactStore(sources_root)
        enh = source_store.read(
            ArtifactSpec("source.enh_annual", sources.enh_annual)
        )
        geih = source_store.read(
            ArtifactSpec("source.geih_annual", sources.geih_annual)
        )
        indicators = source_store.read(
            ArtifactSpec(
                "source.monthly_indicators", sources.monthly_indicators
            )
        )
        annex_path = sources_root.joinpath(
            *PurePosixPath(sources.geih_monthly_annex).parts
        )
        observed = self._reader.read_national_monthly(annex_path)

        disaggregated = self._disaggregation.run(enh, geih, indicators)
        combined = combine_history_with_observed(
            disaggregated.monthly,
            observed,
            history_provenance=ProvenanceCategory(
                self._config.combination.history_provenance
            ),
        )
        annual_input = disaggregated.annual
        reconciled = self._reconciler.run(annual_input, disaggregated.monthly)
        observed_only = combined[
            combined[PROVENANCE_COLUMN] == str(ProvenanceCategory.OBSERVED)
        ]
        seasonal = self._seasonality.adjust(reconciled.monthly, observed_only)

        tables: dict[str, pd.DataFrame] = {
            "disaggregated_annual": disaggregated.annual,
            "disaggregated_monthly": disaggregated.monthly,
            "geih_observed_monthly": observed,
            "combined_with_provenance": combined,
            "reconciled_annual": reconciled.annual,
            "reconciled_monthly": reconciled.monthly,
            "reconciliation_annual_adjustments": reconciled.annual_adjustments,
            "reconciliation_monthly_factors": reconciled.monthly_factors,
            "reconciliation_seam": reconciled.seam_continuity,
            "seasonal_monthly": seasonal.monthly,
            "seasonal_profiles": seasonal.profiles,
            "seasonal_seam": seasonal.seam,
        }
        records = tuple(
            output.write(OUTPUTS[name], table)
            for name, table in tables.items()
        )
        diagnostics = {
            "disaggregation": {
                "gates": dict(disaggregated.gates),
                "splice": list(disaggregated.splice_diagnostics),
                "fit": list(disaggregated.fit_diagnostics),
            },
            "reconciliation": {
                "gates": dict(reconciled.gates),
                "review_flags": dict(reconciled.review_flags),
            },
            "seasonality": {
                "quality": dict(seasonal.quality),
                "diagnostics": dict(seasonal.diagnostics),
            },
        }
        diagnostics_path = output.root / "national" / "diagnostics.json"
        if diagnostics_path.exists():
            raise FileExistsError(diagnostics_path)
        diagnostics_path.write_text(
            json.dumps(diagnostics, indent=2, sort_keys=True, default=str)
            + "\n",
            encoding="utf-8",
        )
        annex_record = ArtifactRecord(
            artifact_id="source.geih_monthly_annex",
            relative_path=sources.geih_monthly_annex,
            sha256=sha256_file(annex_path),
            n_rows=int(observed.shape[0]),
            n_columns=int(observed.shape[1]),
        )
        return NationalRunResult(
            outputs=records,
            inputs=(*source_store.records, annex_record),
            diagnostics=diagnostics,
        )
