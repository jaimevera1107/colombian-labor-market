"""Fresh fitting of departmental rate models with geographic CV.

Four rates are modeled independently (employment/working age,
unemployment/labor force, participation and working age over the
demographic projection) and projected onto the accounting plane
``TO = TGP x (1 - TD)``. Five methods are compared on 15 folds: the urban
analog, Ridge, XGBoost without clusters and XGBoost with fold-specific
K-Means or Ward memberships. Hyperparameters are fixed before the
comparison; the test fold is never used for tuning or early stopping.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from xgboost import XGBRegressor

from icml.modeling.clustering import TerritorialClustering

RATE_TARGETS: dict[str, str] = {
    "to": "target_ratio_employed_over_working_age",
    "td": "target_ratio_unemployed_over_labor_force",
    "tgp": "target_ratio_labor_force_over_working_age",
    "pet_demog": "working_age_over_demographic_projection",
}
URBAN_ANALOG: dict[str, str] = {
    "to": "urban_employment_rate",
    "td": "urban_unemployment_rate",
    "tgp": "urban_participation_rate",
}
METHODS: tuple[str, ...] = (
    "urban_analog",
    "ridge",
    "xgb_none",
    "xgb_kmeans",
    "xgb_ward",
)
CLUSTERED_METHODS: dict[str, str] = {
    "xgb_kmeans": "kmeans",
    "xgb_ward": "ward",
}
STATUS_HISTORICAL = "EXTRAPOLACION_HISTORICA_FUERA_DEL_ENTRENAMIENTO"
STATUS_PROJECTION = "PROYECCION_2026_NO_VALIDADA"
STATUS_RETROSPECTIVE = "PREDICCION_RETROSPECTIVA_EXPERIMENTAL"
_IDENTITY_TOLERANCE = 1e-5
_NEGATIVE_TOLERANCE = 1e-7


class Regressor(Protocol):
    """Minimal estimator interface used by the trainer."""

    def fit(self, x: np.ndarray, y: np.ndarray) -> object:
        """Fit the estimator."""

    def predict(self, x: np.ndarray) -> np.ndarray:
        """Predict targets."""


class TrainingError(ValueError):
    """Raised when training inputs or outputs break the contract."""


@dataclass(frozen=True)
class TrainingPolicy:
    """Features, model settings and selection weights."""

    base_features: Sequence[str]
    yoy_clip_low: float
    yoy_clip_high: float
    ridge_alpha: float
    selection_mean_weight: float
    selection_worst_weight: float
    selection_reference: str
    xgboost: Mapping[str, Any] = field(default_factory=dict)


def coherent_rates(raw: Mapping[str, Any]) -> dict[str, np.ndarray]:
    """Project four candidate rates onto ``TO = TGP x (1 - TD)``.

    Minimizes ``(g - g0)^2 + (g (1 - d) - o0)^2`` holding ``TD`` and
    working age over population fixed.
    """
    unemployment = np.clip(np.asarray(raw["td"], dtype=float), 0, 1)
    employment = np.clip(np.asarray(raw["to"], dtype=float), 0, 1)
    participation = np.clip(np.asarray(raw["tgp"], dtype=float), 0, 1)
    working_age = np.clip(np.asarray(raw["pet_demog"], dtype=float), 0, 1)
    complement = 1 - unemployment
    corrected = np.clip(
        (participation + complement * employment)
        / (1 + complement * complement),
        0,
        1,
    )
    return {
        "to": corrected * complement,
        "td": unemployment,
        "tgp": corrected,
        "pet_demog": working_age,
    }


class RateModels:
    """Model factory and design-matrix construction."""

    def __init__(self, policy: TrainingPolicy, seed: int) -> None:
        """Store settings."""
        self._policy = policy
        self._seed = seed

    def matrix(
        self, frame: pd.DataFrame, columns: Sequence[str]
    ) -> np.ndarray:
        """Return the predictor matrix with clipped growth rates.

        Raises
        ------
        TrainingError
            If a predictor is missing or not finite.
        """
        data = frame[list(columns)].copy()
        for column in columns:
            if column.endswith("_yoy_pct"):
                data[column] = data[column].clip(
                    self._policy.yoy_clip_low, self._policy.yoy_clip_high
                )
        values = np.array(data, dtype=np.float64)
        if np.isnan(values).any() or not np.isfinite(values).all():
            raise TrainingError("Missing or non-finite predictors")
        return values

    def make(self, method: str) -> Regressor:
        """Return an unfitted estimator for a method."""
        if method == "ridge":
            pipeline: Regressor = make_pipeline(
                StandardScaler(), Ridge(alpha=self._policy.ridge_alpha)
            )
            return pipeline
        if method.startswith("xgb_"):
            return XGBRegressor(
                **dict(self._policy.xgboost), random_state=self._seed
            )
        raise TrainingError(f"Unknown method: {method}")

    def fit_predict(
        self,
        method: str,
        train: pd.DataFrame,
        test: pd.DataFrame,
        rate: str,
        columns: Sequence[str],
    ) -> np.ndarray:
        """Fit on ``train`` and predict ``test`` for one rate."""
        if method == "urban_analog":
            if rate in URBAN_ANALOG:
                return np.clip(
                    np.array(test[URBAN_ANALOG[rate]], dtype=float) / 100, 0, 1
                )
            return np.full(
                len(test), float(np.median(train[RATE_TARGETS[rate]]))
            )
        model = self.make(method)
        model.fit(
            self.matrix(train, columns),
            np.array(train[RATE_TARGETS[rate]], dtype=float),
        )
        return np.asarray(
            np.clip(model.predict(self.matrix(test, columns)), 0, 1)
        )


@dataclass(frozen=True)
class CrossValidationResult:
    """Out-of-fold predictions, metrics and the selected method."""

    oof: pd.DataFrame
    cluster_log: pd.DataFrame
    metrics: pd.DataFrame
    worst: pd.DataFrame
    score: pd.DataFrame
    selected: str


@dataclass(frozen=True)
class FinalFitResult:
    """Full-sample predictions for every territory and month."""

    predictions: pd.DataFrame
    models: dict[str, Any]
    clusters: pd.DataFrame | None
    n_training_rows: int
    columns: list[str]


class DepartmentalTrainer:
    """Cross-validate, select and refit the departmental rate models."""

    def __init__(
        self,
        policy: TrainingPolicy,
        models: RateModels,
        clustering: TerritorialClustering,
        cluster_columns: Sequence[str],
        synthetic_code: int,
    ) -> None:
        """Compose models and clustering."""
        self._policy = policy
        self._models = models
        self._clustering = clustering
        self._cluster_columns = list(cluster_columns)
        self._synthetic = synthetic_code

    def cross_validate(
        self,
        features: pd.DataFrame,
        targets: pd.DataFrame,
        folds: Sequence[Mapping[str, Any]],
        first_year: int,
    ) -> CrossValidationResult:
        """Run every method on every fold and select one XGBoost variant."""
        matched = features.merge(
            targets[["dep_code", "period", *RATE_TARGETS.values()]],
            on=["dep_code", "period"],
            validate="one_to_one",
        )
        base = list(self._policy.base_features)
        rows, logs = [], []
        for fold in folds:
            train_codes, test_codes = (
                fold["training_codes"],
                fold["test_codes"],
            )
            cut = fold["train_year_max"]
            if (
                self._synthetic in train_codes
                or self._synthetic in test_codes
                or not set(train_codes).isdisjoint(test_codes)
            ):
                raise TrainingError(f"Invalid fold {fold['fold_id']}")
            train = matched[
                matched["dep_code"].isin(train_codes)
                & matched["year"].between(first_year, cut)
            ]
            test = matched[
                matched["dep_code"].isin(test_codes)
                & matched["year"].between(
                    fold["test_year_min"], fold["test_year_max"]
                )
            ]
            if (
                len(train) != fold["n_train_rows"]
                or len(test) != fold["n_test_rows"]
            ):
                raise TrainingError("Fold sizes changed")
            designs: dict[str, tuple[pd.DataFrame, pd.DataFrame, list[str]]]
            designs = {
                m: (train, test, base)
                for m in ("urban_analog", "ridge", "xgb_none")
            }
            for method, clustering in CLUSTERED_METHODS.items():
                assignment = self._clustering.fold(
                    features, clustering, train_codes, cut
                )
                logs.append(
                    assignment[
                        ["dep_code", "cluster_id", "k", "fit_member"]
                    ].assign(fold_id=fold["fold_id"], method=clustering)
                )
                membership = assignment[["dep_code", *self._cluster_columns]]
                designs[method] = (
                    train.merge(
                        membership, on="dep_code", validate="many_to_one"
                    ),
                    test.merge(
                        membership, on="dep_code", validate="many_to_one"
                    ),
                    base + self._cluster_columns,
                )
            for method, (fit_rows, eval_rows, columns) in designs.items():
                for rate, target in RATE_TARGETS.items():
                    prediction = self._models.fit_predict(
                        method, fit_rows, eval_rows, rate, columns
                    )
                    rows.append(
                        pd.DataFrame(
                            {
                                "fold_id": fold["fold_id"],
                                "dep_code": eval_rows["dep_code"].to_numpy(),
                                "period": eval_rows["period"].to_numpy(),
                                "model": method,
                                "variable": rate,
                                "actual": eval_rows[target].to_numpy(),
                                "pred": prediction,
                            }
                        )
                    )
        oof = self._evaluate(pd.concat(rows, ignore_index=True))
        metrics, worst = self._metrics(oof)
        selected, score = self._select(metrics)
        return CrossValidationResult(
            oof=oof,
            cluster_log=pd.concat(logs, ignore_index=True),
            metrics=metrics,
            worst=worst,
            score=score,
            selected=selected,
        )

    @staticmethod
    def _evaluate(predictions: pd.DataFrame) -> pd.DataFrame:
        keys = ["fold_id", "dep_code", "period", "model"]
        wide = predictions.pivot_table(
            index=keys, columns="variable", values="pred", aggfunc="first"
        ).reset_index()
        for rate in RATE_TARGETS:
            if wide[rate].isna().any():
                raise TrainingError(f"Missing out-of-fold {rate}")
        coherent = coherent_rates(wide)
        rates = wide[keys].copy()
        for rate in RATE_TARGETS:
            rates[f"coherent_{rate}"] = coherent[rate]
        result = predictions.merge(rates, on=keys, validate="many_to_one")
        result["post_pred"] = np.select(
            [result["variable"].eq(r) for r in RATE_TARGETS],
            [result[f"coherent_{r}"] for r in RATE_TARGETS],
            default=np.nan,
        )
        result["raw_abs_pp"] = 100 * (result["pred"] - result["actual"]).abs()
        result["post_abs_pp"] = (
            100 * (result["post_pred"] - result["actual"]).abs()
        )
        return result

    @staticmethod
    def _metrics(oof: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
        summary = (
            oof.groupby(["model", "variable"])
            .agg(
                mae_pp=("raw_abs_pp", "mean"),
                mae_post_pp=("post_abs_pp", "mean"),
                median_abs_pp=("raw_abs_pp", "median"),
                p90_abs_pp=(
                    "raw_abs_pp",
                    lambda z: float(np.percentile(z, 90)),
                ),
                n=("raw_abs_pp", "size"),
            )
            .reset_index()
        )
        worst = (
            oof.groupby(["model", "variable", "fold_id", "dep_code"])
            .agg(
                raw_abs_pp=("raw_abs_pp", "mean"),
                post_abs_pp=("post_abs_pp", "mean"),
            )
            .reset_index()
        )
        extremes = (
            worst.groupby(["model", "variable"])
            .agg(
                worst_department_fold_mae_pp=("raw_abs_pp", "max"),
                worst_department_fold_mae_post_pp=("post_abs_pp", "max"),
            )
            .reset_index()
        )
        return summary.merge(extremes, on=["model", "variable"]), worst

    def _select(self, metrics: pd.DataFrame) -> tuple[str, pd.DataFrame]:
        """One global XGBoost variant by post-closure mean and worst MAE."""
        policy = self._policy
        score = (
            metrics.groupby("model")
            .agg(
                mae=("mae_post_pp", "mean"),
                worst=("worst_department_fold_mae_post_pp", "max"),
            )
            .reset_index()
        )
        reference = score.set_index("model").loc[policy.selection_reference]
        score["decision_score"] = (
            policy.selection_mean_weight * score["mae"] / reference["mae"]
            + policy.selection_worst_weight
            * score["worst"]
            / reference["worst"]
        )
        chosen = (
            score[score["model"].str.startswith("xgb_")]
            .sort_values(["decision_score", "model"])
            .iloc[0]["model"]
        )
        return str(chosen), score.sort_values("decision_score")

    def final_fit(
        self,
        features: pd.DataFrame,
        strict: pd.DataFrame,
        targets: pd.DataFrame,
        method: str,
        training_codes: Sequence[int],
        years: range,
        anchored_codes: Sequence[int],
    ) -> FinalFitResult:
        """Refit on all labeled years and predict both urban variants.

        Raises
        ------
        TrainingError
            If the training population or the accounting invariants fail.
        """
        codes = sorted(training_codes)
        labels = targets[["dep_code", "period", *RATE_TARGETS.values()]]
        data = features.merge(
            labels, on=["dep_code", "period"], validate="one_to_one"
        )
        train = data[
            data["dep_code"].isin(codes)
            & data["year"].between(years.start, years.stop - 1)
        ]
        if len(train) != len(codes) * len(years) * 12:
            raise TrainingError("Wrong final training population")
        clusters = None
        columns = list(self._policy.base_features)
        if method in CLUSTERED_METHODS:
            assignment = self._clustering.fold(
                features, CLUSTERED_METHODS[method], codes, years.stop - 1
            )
            clusters = assignment[
                ["dep_code", "cluster_id", "k", *self._cluster_columns]
            ].copy()
            columns = columns + self._cluster_columns

        def enrich(frame: pd.DataFrame) -> pd.DataFrame:
            if clusters is None:
                return frame.copy()
            return frame.merge(clusters, on="dep_code", validate="many_to_one")

        training = enrich(train)
        outputs, models = [], {}
        for rate, target in RATE_TARGETS.items():
            model = self._models.make(method)
            model.fit(
                self._models.matrix(training, columns),
                np.array(training[target], dtype=float),
            )
            models[rate] = model
            for variant, panel in (("filtered", features), ("strict", strict)):
                design = enrich(panel)
                frame = design[
                    [
                        "dep_code",
                        "period",
                        "year",
                        "is_synthetic_urban_signal",
                        "population_demographic_projection",
                    ]
                ].copy()
                frame["variable"] = rate
                frame["variant"] = variant
                frame["pred"] = np.clip(
                    model.predict(self._models.matrix(design, columns)), 0, 1
                )
                outputs.append(frame)
        predictions = pd.concat(outputs, ignore_index=True)
        wide = predictions.pivot(
            index=[
                "variant",
                "dep_code",
                "period",
                "year",
                "is_synthetic_urban_signal",
                "population_demographic_projection",
            ],
            columns="variable",
            values="pred",
        ).reset_index()
        wide.columns.name = None
        for rate, values in coherent_rates(wide).items():
            wide[f"{rate}_coherent"] = values
        population = wide["population_demographic_projection"]
        wide["working_age"] = population * wide["pet_demog_coherent"]
        wide["labor_force"] = wide["working_age"] * wide["tgp_coherent"]
        wide["unemployed"] = wide["labor_force"] * wide["td_coherent"]
        wide["employed"] = wide["labor_force"] - wide["unemployed"]
        wide["inactive"] = wide["working_age"] - wide["labor_force"]
        wide["prediction_status"] = np.select(
            [wide["year"] < years.start, wide["year"] > years.stop - 1],
            [STATUS_HISTORICAL, STATUS_PROJECTION],
            default=STATUS_RETROSPECTIVE,
        )
        wide["target_available"] = wide["dep_code"].isin(list(anchored_codes))
        wide["is_synthetic_signal"] = wide["dep_code"] == self._synthetic
        wide["model"] = method
        self._verify(wide)
        return FinalFitResult(
            predictions=wide,
            models=models,
            clusters=clusters,
            n_training_rows=int(len(train)),
            columns=columns,
        )

    @staticmethod
    def _verify(wide: pd.DataFrame) -> None:
        levels = wide[
            [
                "working_age",
                "labor_force",
                "unemployed",
                "employed",
                "inactive",
            ]
        ]
        if (levels < -_NEGATIVE_TOLERANCE).any().any() or (
            wide["working_age"]
            > wide["population_demographic_projection"] + _NEGATIVE_TOLERANCE
        ).any():
            raise TrainingError("Inadmissible predicted levels")
        if (
            max(
                float(
                    (
                        wide["labor_force"]
                        - wide["unemployed"]
                        - wide["employed"]
                    )
                    .abs()
                    .max()
                ),
                float(
                    (
                        wide["working_age"]
                        - wide["labor_force"]
                        - wide["inactive"]
                    )
                    .abs()
                    .max()
                ),
            )
            >= _IDENTITY_TOLERANCE
        ):
            raise TrainingError("Predicted identities not closed")
