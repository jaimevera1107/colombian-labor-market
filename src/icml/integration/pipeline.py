"""Integration pipeline: combines the national, urban and departmental runs.

1. Propagate the national seasonal adjustment (1993-2000) to the urban
   and departmental series with their frozen link factors.
2. Extend the urban panel to the last published month with latent months
   that reproduce DANE's rolling windows.
3. Build the strict and quality-filtered urban scenarios and the predictor
   bases used by the departmental model.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, TypeVar

import pandas as pd

from icml.config import build_dataclass, load_toml, section
from icml.departmental.pipeline import OUTPUTS as DEPARTMENTAL_OUTPUTS
from icml.domain.territories import UrbanDomainKind, load_urban_domains
from icml.integration.propagation import PropagationPolicy, SeasonalPropagation
from icml.integration.recent import (
    RecentUrbanPanelBuilder,
    SyntheticExtensionPolicy,
    predictor_base,
)
from icml.integration.regularization import (
    RegularizationPolicy,
    UrbanQualityScenarios,
)
from icml.integration.windows import (
    WindowFitPolicy,
    WindowSheetSpec,
    read_rolling_windows,
)
from icml.io.artifacts import ArtifactRecord, ArtifactSpec, ArtifactStore
from icml.io.hashing import sha256_file
from icml.national.pipeline import OUTPUTS as NATIONAL_OUTPUTS
from icml.urban.pipeline import OUTPUTS as URBAN_OUTPUTS

_Spec = TypeVar("_Spec")


@dataclass(frozen=True)
class IntegrationSources:
    """Locations of the integration source files."""

    geih_monthly_annex: str


@dataclass(frozen=True)
class TargetWindow:
    """Years with departmental annual anchors."""

    anchored_first_year: int
    anchored_last_year: int


@dataclass(frozen=True)
class IntegrationConfig:
    """Complete configuration of the integration stage."""

    sources: IntegrationSources
    propagation: PropagationPolicy
    windows: WindowSheetSpec
    latent_fit: WindowFitPolicy
    synthetic: SyntheticExtensionPolicy
    targets: TargetWindow
    regularization: RegularizationPolicy


def load_integration_config(path: Path) -> IntegrationConfig:
    """Load and validate the integration configuration from TOML."""
    payload = load_toml(path)

    def build(cls: type[_Spec], name: str) -> _Spec:
        return build_dataclass(
            cls,
            section(payload, f"integration.{name}"),
            context=f"integration.{name}",
        )

    return IntegrationConfig(
        sources=build(IntegrationSources, "sources"),
        propagation=build(PropagationPolicy, "propagation"),
        windows=build(WindowSheetSpec, "windows"),
        latent_fit=build(WindowFitPolicy, "latent_fit"),
        synthetic=build(SyntheticExtensionPolicy, "synthetic"),
        targets=build(TargetWindow, "targets"),
        regularization=build(RegularizationPolicy, "regularization"),
    )


def _output(name: str, keys: tuple[str, ...] = ()) -> ArtifactSpec:
    return ArtifactSpec(
        f"integration.{name}", f"integration/{name}.csv", keys=keys
    )


CITY_KEYS = ("city_code", "period")
OUTPUTS: dict[str, ArtifactSpec] = {
    "national_monthly": _output("national_monthly", ("period",)),
    "urban_signals_1993_2020": _output("urban_signals_1993_2020", CITY_KEYS),
    "departmental_monthly": _output(
        "departmental_monthly", ("dep_code", "period")
    ),
    "urban_propagation_changes": _output(
        "urban_propagation_changes", ("city_code",)
    ),
    "departmental_propagation_changes": _output(
        "departmental_propagation_changes", ("dep_code",)
    ),
    "signal_transfer": _output("signal_transfer", ("city_code", "quantity")),
    "urban_signals_full": _output("urban_signals_full", CITY_KEYS),
    "urban_latent_segment": _output("urban_latent_segment", CITY_KEYS),
    "predictor_base": _output("predictor_base", CITY_KEYS),
    "window_control": _output("window_control", ("city_code", "quantity")),
    "window_comparison": _output(
        "window_comparison", ("city_code", "window_end", "quantity")
    ),
    "synthetic_anchor_trace": _output(
        "synthetic_anchor_trace", ("year", "quantity")
    ),
    "urban_signals_strict": _output("urban_signals_strict", CITY_KEYS),
    "predictor_base_strict": _output("predictor_base_strict", CITY_KEYS),
    "urban_signals_filtered": _output("urban_signals_filtered", CITY_KEYS),
    "predictor_base_filtered": _output("predictor_base_filtered", CITY_KEYS),
    "regularization_comparison": _output(
        "regularization_comparison", ("city_code",)
    ),
    "quality_filter_decisions": _output(
        "quality_filter_decisions", ("city_code",)
    ),
    "quality_filter_windows": _output(
        "quality_filter_windows", ("city_code", "window_end")
    ),
}


@dataclass(frozen=True)
class IntegrationRunResult:
    """Records of the artifacts written and stage diagnostics."""

    outputs: tuple[ArtifactRecord, ...]
    inputs: tuple[ArtifactRecord, ...]
    diagnostics: dict[str, Any]


class IntegrationPipeline:
    """Run the integration stage on top of the three territorial runs."""

    def __init__(self, config: IntegrationConfig) -> None:
        """Compose the stage components."""
        self._config = config
        domains = load_urban_domains()
        self._city_names = {
            d.dane_code: d.name
            for d in domains
            if d.kind is UrbanDomainKind.OBSERVED_CITY
        }
        self._propagation = SeasonalPropagation(config.propagation)
        self._recent = RecentUrbanPanelBuilder(
            config.latent_fit, config.synthetic, self._city_names
        )
        self._scenarios = UrbanQualityScenarios(
            config.regularization,
            config.synthetic.recipient_code,
            config.latent_fit.first_month,
        )

    def run(
        self,
        sources_root: Path,
        national: ArtifactStore,
        urban: ArtifactStore,
        departmental: ArtifactStore,
        output: ArtifactStore,
    ) -> IntegrationRunResult:
        """Execute the integration stage and write its artifacts."""
        config = self._config
        nat_full, nat_old, nat_new = self._propagation.national(
            national.read(NATIONAL_OUTPUTS["combined_with_provenance"]),
            national.read(NATIONAL_OUTPUTS["reconciled_monthly"]),
            national.read(NATIONAL_OUTPUTS["seasonal_monthly"]),
        )
        signals, urban_changes, transfer = self._propagation.urban(
            urban.read(URBAN_OUTPUTS["signals_33"]),
            urban.read(URBAN_OUTPUTS["splice_factors"]),
            urban.read(URBAN_OUTPUTS["synthetic_links"]),
            urban.read(URBAN_OUTPUTS["cities_unreconciled"]),
            urban.read(URBAN_OUTPUTS["synthetic_unreconciled"]),
            nat_old,
            nat_new,
            config.synthetic.recipient_code,
        )
        panel, departmental_changes = self._propagation.departmental(
            departmental.read(DEPARTMENTAL_OUTPUTS["monthly_revised"]),
            departmental.read(DEPARTMENTAL_OUTPUTS["chow_lin_diagnostics"]),
            nat_old,
            nat_new,
        )

        annex_path = sources_root.joinpath(
            *PurePosixPath(config.sources.geih_monthly_annex).parts
        )
        windows = read_rolling_windows(annex_path, config.windows)
        recent = self._recent.build(signals, windows, nat_full, panel)
        projections = departmental.read(
            DEPARTMENTAL_OUTPUTS["annual_projections"]
        )
        targets = config.targets
        anchored = sorted(set(panel["dep_code"].astype(int)))
        predictors = predictor_base(
            recent.panel,
            projections,
            anchored,
            range(targets.anchored_first_year, targets.anchored_last_year + 1),
        )
        scenarios = self._scenarios.run(
            recent.panel, predictors, windows, nat_full
        )

        tables: dict[str, pd.DataFrame] = {
            "national_monthly": nat_full,
            "urban_signals_1993_2020": signals,
            "departmental_monthly": panel,
            "urban_propagation_changes": pd.DataFrame(urban_changes),
            "departmental_propagation_changes": pd.DataFrame(
                departmental_changes
            ),
            "signal_transfer": pd.DataFrame(transfer),
            "urban_signals_full": recent.panel,
            "urban_latent_segment": recent.latent,
            "predictor_base": predictors,
            "window_control": recent.window_control,
            "window_comparison": recent.window_comparison,
            "synthetic_anchor_trace": recent.synthetic_anchors,
            "urban_signals_strict": scenarios.strict_panel,
            "predictor_base_strict": scenarios.strict_predictors,
            "urban_signals_filtered": scenarios.filtered_panel,
            "predictor_base_filtered": scenarios.filtered_predictors,
            "regularization_comparison": scenarios.city_comparison,
            "quality_filter_decisions": scenarios.filter_decisions,
            "quality_filter_windows": scenarios.filtered_windows,
        }
        records = tuple(
            output.write(OUTPUTS[name], table)
            for name, table in tables.items()
        )
        decisions = scenarios.filter_decisions
        diagnostics = {
            "filter_rules": {
                str(k): int(v)
                for k, v in decisions["rule"].value_counts().items()
            },
            "max_window_error_persons_latent": float(
                recent.window_comparison["difference_persons"].abs().max()
            ),
            "max_filtered_window_error_pct": float(
                decisions["max_window_error_pct"].max()
            ),
        }
        path = output.root / "integration" / "diagnostics.json"
        if path.exists():
            raise FileExistsError(path)
        path.write_text(
            json.dumps(diagnostics, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        annex = ArtifactRecord(
            artifact_id="source.geih_monthly_annex",
            relative_path=config.sources.geih_monthly_annex,
            sha256=sha256_file(annex_path),
            n_rows=len(windows),
            n_columns=config.windows.n_windows,
        )
        return IntegrationRunResult(
            outputs=records,
            inputs=(
                annex,
                *national.records,
                *urban.records,
                *departmental.records,
            ),
            diagnostics=diagnostics,
        )
