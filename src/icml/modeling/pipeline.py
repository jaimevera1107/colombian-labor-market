"""Modeling pipeline: features, folds, training, selection, final panels."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar

import numpy as np
import pandas as pd

from icml.config import build_dataclass, load_toml, section
from icml.departmental.pipeline import OUTPUTS as DEPARTMENTAL_OUTPUTS
from icml.domain.territories import territory_codes
from icml.integration.pipeline import OUTPUTS as INTEGRATION_OUTPUTS
from icml.io.artifacts import ArtifactRecord, ArtifactSpec, ArtifactStore
from icml.io.hashing import sha256_file
from icml.modeling.clustering import ClusteringPolicy, TerritorialClustering
from icml.modeling.features import (
    FeatureBuilder,
    FeaturePolicy,
    build_panel,
)
from icml.modeling.folds import FoldPolicy, make_folds
from icml.modeling.selection import (
    FinalPanelBuilder,
    PostAdjustmentSelector,
    SelectionPolicy,
)
from icml.modeling.training import (
    RATE_TARGETS,
    DepartmentalTrainer,
    RateModels,
    TrainingPolicy,
)

_Spec = TypeVar("_Spec")
PANEL_LEVELS = (
    "employed",
    "unemployed",
    "labor_force",
    "working_age",
    "inactive",
)


@dataclass(frozen=True)
class ModelingConfig:
    """Complete configuration of the modeling stage."""

    features: FeaturePolicy
    clustering: ClusteringPolicy
    folds: FoldPolicy
    training: TrainingPolicy
    selection: SelectionPolicy


def load_modeling_config(path: Path) -> ModelingConfig:
    """Load and validate the modeling configuration from TOML."""
    payload = load_toml(path)

    def build(cls: type[_Spec], name: str) -> _Spec:
        return build_dataclass(
            cls,
            section(payload, f"modeling.{name}"),
            context=f"modeling.{name}",
        )

    return ModelingConfig(
        features=build(FeaturePolicy, "features"),
        clustering=build(ClusteringPolicy, "clustering"),
        folds=build(FoldPolicy, "folds"),
        training=build(TrainingPolicy, "training"),
        selection=build(SelectionPolicy, "selection"),
    )


def _output(name: str, keys: tuple[str, ...] = ()) -> ArtifactSpec:
    return ArtifactSpec(f"modeling.{name}", f"modeling/{name}.csv", keys=keys)


PANEL_KEYS = ("dep_code", "period")
OUTPUTS: dict[str, ArtifactSpec] = {
    "features_filtered": _output("features_filtered", PANEL_KEYS),
    "features_strict": _output("features_strict", PANEL_KEYS),
    "targets": _output("targets", PANEL_KEYS),
    "reference_clusters": _output("reference_clusters", ("dep_code",)),
    "reference_k_candidates": _output("reference_k_candidates", ("k",)),
    "folds": _output("folds", ("fold_id",)),
    "strict_vs_filtered": _output("strict_vs_filtered", ("dep_code",)),
    "oof_predictions": _output("oof_predictions"),
    "cv_metrics": _output("cv_metrics", ("model", "variable")),
    "cv_worst": _output("cv_worst"),
    "model_scores": _output("model_scores", ("model",)),
    "fold_clusters": _output("fold_clusters"),
    "full_predictions": _output(
        "full_predictions", ("variant", "dep_code", "period")
    ),
    "final_clusters": _output("final_clusters", ("dep_code",)),
    "selection_annual": _output("selection_annual"),
    "selection_comparison": _output("selection_comparison"),
    "selection_decision": _output("selection_decision", ("model",)),
    "selection_paired_errors": _output(
        "selection_paired_errors", ("fold_id", "dep_code")
    ),
    "panel_selected": _output("panel_selected", PANEL_KEYS),
    "panel_reference": _output("panel_reference", PANEL_KEYS),
    "panel_sensitivity": _output("panel_sensitivity", PANEL_KEYS),
}


@dataclass(frozen=True)
class ModelingRunResult:
    """Records of the artifacts written and stage diagnostics."""

    outputs: tuple[ArtifactRecord, ...]
    inputs: tuple[ArtifactRecord, ...]
    diagnostics: dict[str, Any]


class ModelingPipeline:
    """Run hitos 2-4 on top of the integration and departmental runs."""

    def __init__(self, config: ModelingConfig) -> None:
        """Compose the modeling components."""
        self._config = config
        codes = territory_codes()
        synthetic = config.features.synthetic_code
        self._codes = codes
        self._builder = FeatureBuilder(config.features)
        self._clustering = TerritorialClustering(
            config.clustering, config.features.seed, codes, synthetic
        )
        self._trainer = DepartmentalTrainer(
            config.training,
            RateModels(config.training, config.features.seed),
            self._clustering,
            config.clustering.cluster_columns,
            synthetic,
        )
        self._selector = PostAdjustmentSelector(config.selection)
        self._panels = FinalPanelBuilder(config.selection, codes, synthetic)

    def run(
        self,
        integration: ArtifactStore,
        departmental: ArtifactStore,
        output: ArtifactStore,
    ) -> ModelingRunResult:
        """Execute the modeling stage and write its artifacts."""
        config = self._config
        policy = config.features
        synthetic = policy.synthetic_code
        national = integration.read(INTEGRATION_OUTPUTS["national_monthly"])
        labels = departmental.read(DEPARTMENTAL_OUTPUTS["monthly_revised"])
        anchored = sorted(set(labels["dep_code"].astype(int)))
        features = self._builder.build(
            build_panel(
                integration.read(
                    INTEGRATION_OUTPUTS["predictor_base_filtered"]
                ),
                national,
                self._codes,
                synthetic,
            )
        )
        strict = self._builder.build(
            build_panel(
                integration.read(INTEGRATION_OUTPUTS["predictor_base_strict"]),
                national,
                self._codes,
                synthetic,
            )
        )
        if list(strict.columns) != list(features.columns) or not strict[
            list(PANEL_KEYS)
        ].equals(features[list(PANEL_KEYS)]):
            raise ValueError("Strict and filtered features are incompatible")
        targets = self._builder.targets(features, labels, anchored)
        training_codes = [c for c in anchored if c != synthetic]
        reference, candidates, _ = self._clustering.reference(
            features, training_codes
        )
        folds = make_folds(
            targets,
            config.folds,
            policy.seed,
            policy.training_first_year,
            synthetic,
        )

        targets_model = targets.merge(
            features[
                ["dep_code", "period", "population_demographic_projection"]
            ],
            on=["dep_code", "period"],
            validate="one_to_one",
        )
        targets_model[RATE_TARGETS["pet_demog"]] = (
            targets_model["target_working_age"]
            / targets_model["population_demographic_projection"]
        )
        cv = self._trainer.cross_validate(
            features, targets_model, folds, policy.training_first_year
        )
        years = range(
            policy.training_first_year, policy.training_last_year + 1
        )
        final = self._trainer.final_fit(
            features,
            strict,
            targets_model,
            cv.selected,
            training_codes,
            years,
            anchored,
        )
        selection = self._selector.run(
            cv.oof.rename(columns={"period": "period"}),
            targets[
                ["dep_code", "period", *[f"target_{q}" for q in PANEL_LEVELS]]
            ],
            features[
                ["dep_code", "period", "population_demographic_projection"]
            ],
        )
        selected = selection.summary["selected_model"]
        reference_panel = self._panels.build(
            final.predictions,
            features,
            targets,
            config.selection.reference_model,
        )
        selected_panel = self._panels.build(
            final.predictions, features, targets, selected
        )
        sensitivity = self._sensitivity(selected_panel, reference_panel)

        tables = {
            "features_filtered": features,
            "features_strict": strict,
            "targets": targets,
            "reference_clusters": reference,
            "reference_k_candidates": candidates,
            "folds": pd.DataFrame(
                [
                    {
                        **f,
                        "training_codes": " ".join(
                            map(str, f["training_codes"])
                        ),
                        "test_codes": " ".join(map(str, f["test_codes"])),
                    }
                    for f in folds
                ]
            ),
            "strict_vs_filtered": self._variant_comparison(features, strict),
            "oof_predictions": cv.oof,
            "cv_metrics": cv.metrics,
            "cv_worst": cv.worst,
            "model_scores": cv.score,
            "fold_clusters": cv.cluster_log,
            "full_predictions": final.predictions,
            "final_clusters": final.clusters
            if final.clusters is not None
            else pd.DataFrame(columns=["dep_code"]),
            "selection_annual": selection.annual,
            "selection_comparison": selection.comparison,
            "selection_decision": selection.decision,
            "selection_paired_errors": selection.paired_errors,
            "panel_selected": selected_panel,
            "panel_reference": reference_panel,
            "panel_sensitivity": sensitivity,
        }
        records = [
            output.write(OUTPUTS[name], table)
            for name, table in tables.items()
        ]
        model_folder = output.root / "modeling" / "models"
        model_folder.mkdir(parents=True, exist_ok=False)
        for rate, model in final.models.items():
            path = model_folder / f"{cv.selected}_{rate}.json"
            model.save_model(path)
            records.append(
                ArtifactRecord(
                    artifact_id=f"modeling.model_{rate}",
                    relative_path=path.relative_to(output.root).as_posix(),
                    sha256=sha256_file(path),
                    n_rows=0,
                    n_columns=0,
                )
            )
        diagnostics = {
            "cv_selected": cv.selected,
            "selection": selection.summary,
            "training_rows_final": final.n_training_rows,
            "features": final.columns,
        }
        path = output.root / "modeling" / "diagnostics.json"
        path.write_text(
            json.dumps(diagnostics, indent=2, sort_keys=True, default=str)
            + "\n",
            encoding="utf-8",
        )
        return ModelingRunResult(
            outputs=tuple(records),
            inputs=(*integration.records, *departmental.records),
            diagnostics=diagnostics,
        )

    @staticmethod
    def _variant_comparison(
        features: pd.DataFrame, strict: pd.DataFrame
    ) -> pd.DataFrame:
        delta = pd.DataFrame(
            {
                "dep_code": features["dep_code"],
                "unemployed": features["urban_unemployed"]
                - strict["urban_unemployed"],
                "employed": features["urban_employed"]
                - strict["urban_employed"],
            }
        )
        return (
            delta.groupby("dep_code")
            .agg(
                n_months_changed_unemployment=(
                    "unemployed",
                    lambda s: int(np.sum(abs(s) > 1e-5)),
                ),
                max_abs_difference_unemployed=(
                    "unemployed",
                    lambda s: float(abs(s).max()),
                ),
                max_abs_difference_employed=(
                    "employed",
                    lambda s: float(abs(s).max()),
                ),
            )
            .reset_index()
        )

    @staticmethod
    def _sensitivity(
        selected: pd.DataFrame, reference: pd.DataFrame
    ) -> pd.DataFrame:
        keys = list(PANEL_KEYS)
        merged = selected[[*keys, *PANEL_LEVELS]].merge(
            reference[[*keys, *PANEL_LEVELS]],
            on=keys,
            suffixes=("_selected", "_reference"),
            validate="one_to_one",
        )
        for level in PANEL_LEVELS:
            merged[f"difference_{level}_pct"] = (
                100
                * (merged[f"{level}_selected"] - merged[f"{level}_reference"])
                / merged[f"{level}_reference"].clip(lower=1)
            )
        return merged
