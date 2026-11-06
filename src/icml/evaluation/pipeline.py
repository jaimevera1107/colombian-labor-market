"""Transfer evaluation stage (not part of ``icml run``; it is expensive)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from icml.config import build_dataclass, load_toml, section
from icml.departmental.pipeline import OUTPUTS as DEPARTMENTAL_OUTPUTS
from icml.domain.territories import territory_codes
from icml.evaluation.closures import build_closures
from icml.evaluation.transfer import TransferEvaluator, TransferPolicy
from icml.integration.pipeline import OUTPUTS as INTEGRATION_OUTPUTS
from icml.io.artifacts import ArtifactRecord, ArtifactSpec, ArtifactStore
from icml.modeling.clustering import TerritorialClustering
from icml.modeling.features import FeatureBuilder, build_panel
from icml.modeling.pipeline import load_modeling_config
from icml.modeling.selection import FinalPanelBuilder
from icml.modeling.training import (
    RATE_TARGETS,
    DepartmentalTrainer,
    RateModels,
)
from icml.reconciliation.pipeline import load_reconciliation_config


def load_transfer_policy(path: Path) -> TransferPolicy:
    """Load the evaluation configuration from TOML."""
    return build_dataclass(
        TransferPolicy,
        section(load_toml(path), "evaluation.transfer"),
        context="evaluation.transfer",
    )


def _output(name: str, keys: tuple[str, ...]) -> ArtifactSpec:
    return ArtifactSpec(
        f"evaluation.{name}", f"evaluation/{name}.csv", keys=keys
    )


OUTPUTS: dict[str, ArtifactSpec] = {
    "transfer_annual": _output(
        "transfer_annual", ("hidden_code", "candidate", "stage", "year")
    ),
    "transfer_summary": _output("transfer_summary", ("candidate", "stage")),
    "transfer_by_department": _output(
        "transfer_by_department", ("hidden_code", "candidate", "stage")
    ),
}


@dataclass(frozen=True)
class EvaluationRunResult:
    """Records of the artifacts written and stage diagnostics."""

    outputs: tuple[ArtifactRecord, ...]
    inputs: tuple[ArtifactRecord, ...]
    diagnostics: dict[str, Any]


class TransferEvaluationPipeline:
    """Build features and run the leave-one-out transfer evaluation."""

    def __init__(self, config_path: Path) -> None:
        """Load this stage's policy and the reused stage configurations."""
        self._policy = load_transfer_policy(config_path)
        base = config_path.parent
        self._modeling = load_modeling_config(
            base / self._policy.modeling_config
        )
        self._reconciliation = load_reconciliation_config(
            base / self._policy.reconciliation_config
        )

    def run(
        self,
        integration: ArtifactStore,
        departmental: ArtifactStore,
        output: ArtifactStore,
    ) -> EvaluationRunResult:
        """Execute the evaluation and write its artifacts."""
        modeling = self._modeling
        synthetic = modeling.features.synthetic_code
        codes = territory_codes()
        builder = FeatureBuilder(modeling.features)
        national = integration.read(INTEGRATION_OUTPUTS["national_monthly"])
        features = builder.build(
            build_panel(
                integration.read(
                    INTEGRATION_OUTPUTS["predictor_base_filtered"]
                ),
                national,
                codes,
                synthetic,
            )
        )
        strict = builder.build(
            build_panel(
                integration.read(INTEGRATION_OUTPUTS["predictor_base_strict"]),
                national,
                codes,
                synthetic,
            )
        )
        labels = departmental.read(DEPARTMENTAL_OUTPUTS["monthly_revised"])
        anchors = departmental.read(DEPARTMENTAL_OUTPUTS["official_anchors"])
        anchored = sorted(set(labels["dep_code"].astype(int)))
        targets = builder.targets(features, labels, anchored).merge(
            features[
                ["dep_code", "period", "population_demographic_projection"]
            ],
            on=["dep_code", "period"],
            validate="one_to_one",
        )
        targets[RATE_TARGETS["pet_demog"]] = (
            targets["target_working_age"]
            / targets["population_demographic_projection"]
        )
        clustering = TerritorialClustering(
            modeling.clustering, modeling.features.seed, codes, synthetic
        )
        trainer = DepartmentalTrainer(
            modeling.training,
            RateModels(modeling.training, modeling.features.seed),
            clustering,
            modeling.clustering.cluster_columns,
            synthetic,
        )
        evaluator = TransferEvaluator(
            self._policy,
            trainer,
            FinalPanelBuilder(modeling.selection, codes, synthetic),
            build_closures(
                list(self._policy.closures),
                self._reconciliation.hierarchical,
            ),
            modeling.selection.candidate,
            synthetic,
        )
        result = evaluator.run(features, strict, targets, national, anchors)
        tables = {
            "transfer_annual": result.annual,
            "transfer_summary": result.summary,
            "transfer_by_department": result.by_department,
        }
        records = tuple(
            output.write(OUTPUTS[name], table)
            for name, table in tables.items()
        )
        diagnostics = {
            "hidden": evaluator.hidden(anchored),
            "candidates": list(self._policy.candidates),
        }
        (output.root / "evaluation" / "diagnostics.json").write_text(
            json.dumps(diagnostics, indent=2) + "\n", encoding="utf-8"
        )
        return EvaluationRunResult(
            outputs=records,
            inputs=(*integration.records, *departmental.records),
            diagnostics=diagnostics,
        )
