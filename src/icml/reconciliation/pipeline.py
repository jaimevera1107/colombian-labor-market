"""Reconciliation pipeline and the three published products.

* ``product.national``: national monthly series with the linearized
  1993-2000 working age.
* ``product.departmental``: the operational model's panel (ADR-006: Ward),
  hierarchically reconciled and with linearized 1993-2000 working age.
* ``product.urban_signals``: the quality-filtered urban signals.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar

import pandas as pd

from icml.config import build_dataclass, load_toml, section
from icml.departmental.pipeline import OUTPUTS as DEPARTMENTAL_OUTPUTS
from icml.integration.pipeline import OUTPUTS as INTEGRATION_OUTPUTS
from icml.io.artifacts import ArtifactRecord, ArtifactSpec, ArtifactStore
from icml.modeling.pipeline import OUTPUTS as MODELING_OUTPUTS
from icml.reconciliation.hierarchical import (
    HierarchicalPolicy,
    HierarchicalReconciler,
)
from icml.reconciliation.linearization import (
    LinearizationPolicy,
    WorkingAgeLinearizer,
)
from icml.reconciliation.representativeness import (
    RepresentativenessBuilder,
    RepresentativenessPolicy,
)

_Spec = TypeVar("_Spec")
PANELS = {"reference": "panel_reference", "selected": "panel_selected"}


@dataclass(frozen=True)
class ProductPolicy:
    """Which reconciled panel becomes the departmental product."""

    operational_model: str

    def __post_init__(self) -> None:
        """Validate the panel name."""
        if self.operational_model not in PANELS:
            raise ValueError(
                f"operational_model must be one of {sorted(PANELS)}"
            )


@dataclass(frozen=True)
class ReconciliationConfig:
    """Complete configuration of the reconciliation stage."""

    hierarchical: HierarchicalPolicy
    linearization: LinearizationPolicy
    product: ProductPolicy
    representativeness: RepresentativenessPolicy


def load_reconciliation_config(path: Path) -> ReconciliationConfig:
    """Load and validate the reconciliation configuration from TOML."""
    payload = load_toml(path)

    def build(cls: type[_Spec], name: str) -> _Spec:
        return build_dataclass(
            cls,
            section(payload, f"reconciliation.{name}"),
            context=f"reconciliation.{name}",
        )

    return ReconciliationConfig(
        hierarchical=build(HierarchicalPolicy, "hierarchical"),
        linearization=build(LinearizationPolicy, "linearization"),
        product=build(ProductPolicy, "product"),
        representativeness=build(
            RepresentativenessPolicy, "representativeness"
        ),
    )


def _output(name: str, keys: tuple[str, ...] = ()) -> ArtifactSpec:
    return ArtifactSpec(
        f"reconciliation.{name}", f"reconciliation/{name}.csv", keys=keys
    )


def _product(name: str, keys: tuple[str, ...]) -> ArtifactSpec:
    return ArtifactSpec(f"product.{name}", f"products/{name}.csv", keys=keys)


PANEL_KEYS = ("dep_code", "period")
OUTPUTS: dict[str, ArtifactSpec] = {
    **{
        f"{name}_reconciled": _output(f"{name}_reconciled", PANEL_KEYS)
        for name in PANELS
    },
    **{
        f"{name}_national_check": _output(
            f"{name}_national_check", ("period",)
        )
        for name in PANELS
    },
    **{
        f"{name}_anchor_check": _output(
            f"{name}_anchor_check", ("dep_code", "year")
        )
        for name in PANELS
    },
    **{
        f"{name}_smoothness": _output(
            f"{name}_smoothness", ("dep_code", "quantity")
        )
        for name in PANELS
    },
    "national": _product("national", ("period",)),
    "departmental": _product("departmental", PANEL_KEYS),
    "urban_signals": _product("urban_signals", ("city_code", "period")),
    # Candidate design (whole-territory departments with factors).
    "departmental_factors": _product("departmental_factors", PANEL_KEYS),
    "national_icml": _product("national_icml", ("period",)),
    "rest_ratios": _output("rest_ratios", ("period",)),
    "official_deviation": _product(
        "official_deviation", ("dep_code", "year", "quantity")
    ),
}


@dataclass(frozen=True)
class ReconciliationRunResult:
    """Records of the artifacts written and stage diagnostics."""

    outputs: tuple[ArtifactRecord, ...]
    inputs: tuple[ArtifactRecord, ...]
    diagnostics: dict[str, Any]


class ReconciliationPipeline:
    """Close the panels and build the three products."""

    def __init__(self, config: ReconciliationConfig) -> None:
        """Compose the reconciler and the linearizer."""
        self._config = config
        self._reconciler = HierarchicalReconciler(config.hierarchical)
        self._linearizer = WorkingAgeLinearizer(config.linearization)

    def run(
        self,
        modeling: ArtifactStore,
        integration: ArtifactStore,
        departmental: ArtifactStore,
        output: ArtifactStore,
    ) -> ReconciliationRunResult:
        """Execute the reconciliation stage and write its artifacts."""
        national = integration.read(INTEGRATION_OUTPUTS["national_monthly"])
        anchors = departmental.read(DEPARTMENTAL_OUTPUTS["official_anchors"])
        tables: dict[str, pd.DataFrame] = {}
        summaries: dict[str, Any] = {}
        reconciled: dict[str, pd.DataFrame] = {}
        for name, artifact in PANELS.items():
            result = self._reconciler.run(
                modeling.read(MODELING_OUTPUTS[artifact]), national, anchors
            )
            reconciled[name] = result.panel
            tables[f"{name}_reconciled"] = result.panel
            tables[f"{name}_national_check"] = result.national_check
            tables[f"{name}_anchor_check"] = result.anchor_check
            tables[f"{name}_smoothness"] = result.smoothness
            summaries[name] = result.summary
        national_product, national_stats = self._linearizer.national(national)
        departmental_product, territorial_stats = self._linearizer.territorial(
            reconciled[self._config.product.operational_model],
            national_product,
        )
        tables["national"] = national_product
        tables["departmental"] = departmental_product
        tables["urban_signals"] = integration.read(
            INTEGRATION_OUTPUTS["urban_signals_filtered"]
        )
        factors = RepresentativenessBuilder(
            self._config.representativeness
        ).build(
            modeling.read(
                MODELING_OUTPUTS[
                    PANELS[self._config.product.operational_model]
                ]
            ),
            departmental.read(DEPARTMENTAL_OUTPUTS["monthly_revised"]),
            tables["urban_signals"],
            national,
            anchors,
        )
        tables["departmental_factors"] = factors.departmental
        tables["national_icml"] = factors.national
        tables["rest_ratios"] = factors.rest_ratios
        tables["official_deviation"] = factors.deviation
        records = tuple(
            output.write(OUTPUTS[name], table)
            for name, table in tables.items()
        )
        diagnostics = {
            "closure": summaries,
            "representativeness": factors.summary,
            "linearization": {
                "national": national_stats,
                "territorial": territorial_stats,
            },
            "operational_model": self._config.product.operational_model,
        }
        path = output.root / "reconciliation" / "diagnostics.json"
        path.write_text(
            json.dumps(diagnostics, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return ReconciliationRunResult(
            outputs=records,
            inputs=(
                *modeling.records,
                *integration.records,
                *departmental.records,
            ),
            diagnostics=diagnostics,
        )
