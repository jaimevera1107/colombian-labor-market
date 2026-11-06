"""Urban pipeline: donors, recipient closure, retropolation, synthetic.

Consumes the national artifacts of a previous national run and the urban
sources; writes every urban artifact once.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, TypeVar

import pandas as pd

from icml.config import build_dataclass, load_toml, section
from icml.domain.territories import UrbanDomainKind, load_urban_domains
from icml.io.artifacts import ArtifactRecord, ArtifactSpec, ArtifactStore
from icml.io.hashing import sha256_file
from icml.national.pipeline import OUTPUTS as NATIONAL_OUTPUTS
from icml.national.reference import reference_national
from icml.urban.accounting import URBAN_SIGNALS
from icml.urban.closure import BridgePolicy, RecipientPanelBuilder
from icml.urban.donors import DonorPolicy, ParetoDonorSelector
from icml.urban.frozen_donors import verify_frozen
from icml.urban.inputs import anchor_column, load_urban_sources
from icml.urban.retropolation import (
    RetropolationPolicy,
    UrbanRetropolation,
    build_annual_anchors,
)
from icml.urban.synthetic import SyntheticSignalBuilder, SyntheticSignalPolicy

_Spec = TypeVar("_Spec")
CITY_UNIT_TYPE = "CIUDAD_O_AREA_METROPOLITANA"


class UrbanPipelineError(ValueError):
    """Raised when urban inputs are inconsistent with the configuration."""


@dataclass(frozen=True)
class UrbanSourcesSpec:
    """Locations of the urban inputs, relative to a sources root."""

    historical_signals: str
    window_proxies: str
    reference_donors: str
    synthetic_donor: str
    frozen_selection: str | None = None


@dataclass(frozen=True)
class UrbanConfig:
    """Complete configuration of the urban stage."""

    sources: UrbanSourcesSpec
    donors: DonorPolicy
    bridge: BridgePolicy
    retropolation: RetropolationPolicy
    synthetic: SyntheticSignalPolicy


def load_urban_config(path: Path) -> UrbanConfig:
    """Load and validate the urban configuration from TOML."""
    payload = load_toml(path)

    def build(cls: type[_Spec], name: str) -> _Spec:
        return build_dataclass(
            cls, section(payload, f"urban.{name}"), context=f"urban.{name}"
        )

    return UrbanConfig(
        sources=build(UrbanSourcesSpec, "sources"),
        donors=build(DonorPolicy, "donors"),
        bridge=build(BridgePolicy, "bridge"),
        retropolation=build(RetropolationPolicy, "retropolation"),
        synthetic=build(SyntheticSignalPolicy, "synthetic"),
    )


def _output(name: str, keys: tuple[str, ...] = ()) -> ArtifactSpec:
    return ArtifactSpec(f"urban.{name}", f"urban/{name}.csv", keys=keys)


OUTPUTS: dict[str, ArtifactSpec] = {
    "donor_alternatives": _output(
        "donor_alternatives", ("recipient_code", "donor_code")
    ),
    "donor_catalog": _output("donor_catalog", ("recipient_code",)),
    "donor_backtest": _output("donor_backtest", ("city_code",)),
    "recipient_annual_panel": _output(
        "recipient_annual_panel", ("recipient_code", "year")
    ),
    "recipient_closure_audit": _output(
        "recipient_closure_audit", ("recipient_code",)
    ),
    "cities_monthly": _output("cities_monthly", ("city_code", "period")),
    "cities_unreconciled": _output(
        "cities_unreconciled", ("city_code", "period")
    ),
    "anchor_audit": _output("anchor_audit", ("city_code", "year", "quantity")),
    "splice_factors": _output("splice_factors", ("city_code", "quantity")),
    "seam_audit": _output("seam_audit", ("city_code", "quantity")),
    "retropolation_backtest": _output(
        "retropolation_backtest", ("city_code", "calibration_year", "quantity")
    ),
    "recent_references": _output("recent_references", ("city_code", "year")),
    "synthetic_monthly": _output("synthetic_monthly", ("period",)),
    "synthetic_annual": _output("synthetic_annual", ("year",)),
    "synthetic_calibration": _output("synthetic_calibration", ("quantity",)),
    "synthetic_links": _output("synthetic_links", ("quantity",)),
    "synthetic_unreconciled": _output("synthetic_unreconciled", ("period",)),
    "synthetic_official_anchors": _output(
        "synthetic_official_anchors", ("year",)
    ),
    "signals_33": _output("signals_33", ("city_code", "period")),
}


@dataclass(frozen=True)
class UrbanRunResult:
    """Records of the artifacts written and stage diagnostics."""

    outputs: tuple[ArtifactRecord, ...]
    inputs: tuple[ArtifactRecord, ...]
    diagnostics: dict[str, Any]


class UrbanPipeline:
    """Run the urban stages."""

    def __init__(self, config: UrbanConfig) -> None:
        """Store the configuration and the territorial catalog."""
        self._config = config
        domains = load_urban_domains()
        self._city_names = {
            d.dane_code: d.name
            for d in domains
            if d.kind is UrbanDomainKind.OBSERVED_CITY
        }

    def run(
        self,
        sources_root: Path,
        national: ArtifactStore,
        output: ArtifactStore,
    ) -> UrbanRunResult:
        """Execute the urban stages and write their artifacts."""
        config = self._config
        source_store = ArtifactStore(sources_root)
        spec = config.sources
        historical = source_store.read(
            ArtifactSpec(
                "source.urban_historical_signals", spec.historical_signals
            )
        )
        proxies = source_store.read(
            ArtifactSpec("source.urban_window_proxies", spec.window_proxies)
        )
        reference = source_store.read(
            ArtifactSpec(
                "source.urban_reference_donors", spec.reference_donors
            )
        )
        frozen_path = sources_root.joinpath(
            *PurePosixPath(spec.synthetic_donor).parts
        )
        frozen = json.loads(frozen_path.read_text(encoding="utf-8"))
        historical_path = source_store.resolve(
            ArtifactSpec(
                "source.urban_historical_signals", spec.historical_signals
            )
        )
        if frozen["source_sha256"] != sha256_file(historical_path):
            raise UrbanPipelineError(
                "Historical signals changed since the synthetic donor was "
                "frozen; a methodological review is required"
            )

        combined = national.read(NATIONAL_OUTPUTS["combined_with_provenance"])
        reconciled = national.read(NATIONAL_OUTPUTS["reconciled_monthly"])

        sources = load_urban_sources(
            historical,
            proxies,
            city_codes=sorted(self._city_names),
            excluded_codes=config.donors.excluded_codes,
            selection_years=config.donors.selection_years,
            published_unit_persons=config.donors.published_unit_persons,
        )
        reference_donors = dict(
            zip(
                reference["dep_code"].astype(int),
                reference["donor_code"].astype(int),
                strict=True,
            )
        )
        selector = ParetoDonorSelector(
            sources, config.donors, self._city_names
        )
        selection = selector.run(reference_donors)
        if spec.frozen_selection is not None:
            selection_path = sources_root.joinpath(*PurePosixPath(spec.frozen_selection).parts)
            selected = dict(zip(
                selection.catalog["recipient_code"].astype(int),
                selection.catalog["selected_donor_code"].astype(int),
                strict=True,
            ))
            verify_frozen(
                selection_path, proxies, config.donors,
                historical_path,
                source_store.resolve(ArtifactSpec(
                    "source.urban_reference_donors", spec.reference_donors)),
                selected,
            )
        closure = RecipientPanelBuilder(
            sources, config.donors, config.bridge
        ).build(
            selection.catalog, selection.thresholds["holdout_error_quantile"]
        )

        years = list(
            range(
                config.retropolation.anchor_start_year,
                config.donors.history_end + 1,
            )
        )
        anchors = build_annual_anchors(
            sources.history,
            closure.panel,
            city_names=self._city_names,
            recipient_codes=config.donors.recipient_codes,
            years=years,
        )
        retropolation = UrbanRetropolation(
            config.retropolation, config.donors.recipient_codes
        ).run(
            anchors,
            reference_national(
                combined, reconciled, config.retropolation.end_period
            ),
        )

        synthetic = SyntheticSignalBuilder(
            config.synthetic, frozen, config.donors.published_unit_persons
        ).build(
            historical,
            reference_national(
                combined, reconciled, f"{config.synthetic.last_year}-12"
            ),
        )

        tables = {
            "donor_alternatives": selection.alternatives,
            "donor_catalog": selection.catalog,
            "donor_backtest": selection.backtest,
            "recipient_annual_panel": closure.panel,
            "recipient_closure_audit": closure.audit,
            "cities_monthly": retropolation.monthly,
            "cities_unreconciled": retropolation.unreconciled,
            "anchor_audit": retropolation.anchor_audit,
            "splice_factors": retropolation.splice_factors,
            "seam_audit": retropolation.seam_audit,
            "retropolation_backtest": retropolation.backtest,
            "recent_references": self._recent_references(proxies),
            "synthetic_monthly": synthetic.monthly,
            "synthetic_annual": synthetic.annual,
            "synthetic_calibration": synthetic.calibration,
            "synthetic_links": synthetic.monthly_links,
            "synthetic_unreconciled": synthetic.unreconciled,
            "synthetic_official_anchors": synthetic.official_anchors,
            "signals_33": self._signals_33(
                retropolation.monthly, synthetic.monthly
            ),
        }
        records = tuple(
            output.write(OUTPUTS[name], table)
            for name, table in tables.items()
        )
        diagnostics = {
            "thresholds": dict(selection.thresholds),
            "normalization": {
                k: dict(v) for k, v in selection.normalization.items()
            },
        }
        path = output.root / "urban" / "diagnostics.json"
        if path.exists():
            raise FileExistsError(path)
        path.write_text(
            json.dumps(diagnostics, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        frozen_record = ArtifactRecord(
            artifact_id="source.urban_synthetic_donor",
            relative_path=spec.synthetic_donor,
            sha256=sha256_file(frozen_path),
            n_rows=1,
            n_columns=len(frozen),
        )
        return UrbanRunResult(
            outputs=records,
            inputs=(*source_store.records, frozen_record, *national.records),
            diagnostics=diagnostics,
        )

    def _recent_references(self, proxies: pd.DataFrame) -> pd.DataFrame:
        columns = {anchor_column(q): q for q in URBAN_SIGNALS}
        table = proxies.rename(
            columns={**columns, "dep_code": "city_code", "city": "city_name"}
        )
        return table[["city_code", "city_name", "year", *URBAN_SIGNALS]]

    def _signals_33(
        self, cities: pd.DataFrame, synthetic: pd.DataFrame
    ) -> pd.DataFrame:
        last = self._config.retropolation.end_period
        observed = cities.assign(unit_type=CITY_UNIT_TYPE)
        signal = synthetic[synthetic["period"] <= last]
        combined = pd.concat([observed, signal], ignore_index=True, sort=False)
        expected_units = len(self._city_names) + 1
        if (
            combined["city_code"].nunique() != expected_units
            or combined.duplicated(subset=["city_code", "period"]).any()
        ):
            raise UrbanPipelineError("33-signal panel coverage is wrong")
        return combined
