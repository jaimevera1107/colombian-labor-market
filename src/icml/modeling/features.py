"""Predictor matrix and departmental targets.

Predictors come only from the urban signals, the national series and the
demographic projections; departmental labels live in a separate table and
are never merged into predictor generation. Labels are monthly paths
constrained to annual anchors, not observed monthly values.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import pandas as pd

QUANTITIES: tuple[str, ...] = (
    "employed",
    "unemployed",
    "inactive",
    "labor_force",
    "working_age",
    "population",
)
TARGET_RATIOS: dict[str, tuple[str, str]] = {
    "target_ratio_employed_over_working_age": ("employed", "working_age"),
    "target_ratio_unemployed_over_labor_force": ("unemployed", "labor_force"),
    "target_ratio_labor_force_over_working_age": (
        "labor_force",
        "working_age",
    ),
    "target_ratio_working_age_over_population": ("working_age", "population"),
}
STATUS_ANCHORED = "RECONSTRUIDO_CON_ANCLA_ANUAL"
STATUS_UNANCHORED = "INFERIDO_SIN_ANCLA"
STATUS_MISSING = "SIN_OBJETIVO_DEPARTAMENTAL"
_TARGET_FLOOR = 1e-9


class FeatureError(ValueError):
    """Raised when inputs or features break the modeling contract."""


@dataclass(frozen=True)
class FeaturePolicy:
    """Feature construction settings."""

    seed: int
    training_first_year: int
    training_last_year: int
    synthetic_code: int
    safe_division_floor: float
    lags: Sequence[int]
    log_quantities: Sequence[str]
    growth_quantities: Sequence[str]


def build_panel(
    predictors: pd.DataFrame,
    national: pd.DataFrame,
    territory_codes: Sequence[int],
    synthetic_code: int,
) -> pd.DataFrame:
    """Join the urban predictor base with the national series.

    Raises
    ------
    FeatureError
        On coverage gaps, duplicated keys, negative or missing signals.
    """
    if (
        predictors.duplicated(subset=["city_code", "period"]).any()
        or national.duplicated(subset=["period"]).any()
    ):
        raise FeatureError("Duplicated keys in modeling inputs")
    if sorted(predictors["city_code"].unique()) != sorted(territory_codes):
        raise FeatureError("Predictor territories differ from the catalog")
    months = sorted(national["period"])
    for code, group in predictors.groupby("city_code"):
        if sorted(group["period"]) != months:
            raise FeatureError(f"Missing months in urban signal {code}")
    columns = [*QUANTITIES, "population_demographic_projection"]
    if (
        predictors[columns].isna().any().any()
        or (predictors[list(QUANTITIES)] < 0).any().any()
    ):
        raise FeatureError("Missing or negative urban signals")
    synthetic = predictors[predictors["city_code"] == synthetic_code]
    if not synthetic["is_synthetic_signal"].all():
        raise FeatureError("Synthetic signal is mislabeled")
    panel = predictors.drop(
        columns=["target_with_annual_anchor", "is_synthetic_signal"]
    )
    panel = panel.rename(
        columns={
            "city_code": "dep_code",
            "city_name": "urban_unit_name",
            "origin": "urban_origin",
            "unit_type": "urban_unit_type",
        }
    )
    panel["dep_code"] = panel["dep_code"].astype(int)
    panel["month"] = panel["period"].str.slice(5).astype(int)
    panel["year"] = panel["period"].str.slice(0, 4).astype(int)
    panel["date"] = pd.to_datetime(panel["period"] + "-01")
    panel["is_synthetic_urban_signal"] = panel["dep_code"] == synthetic_code
    # Signals were rebuilt with the latest vintage: never an as-of backtest.
    panel["urban_signal_vintage_asof_available"] = False
    for quantity in QUANTITIES:
        panel[f"urban_{quantity}"] = panel.pop(quantity).astype("float64")
    reference = national[["period", *QUANTITIES]].rename(
        columns={q: f"nat_{q}" for q in QUANTITIES}
    )
    merged = panel.merge(
        reference, how="left", on="period", validate="many_to_one"
    )
    if merged[[f"nat_{q}" for q in QUANTITIES]].isna().any().any():
        raise FeatureError("National coverage gap")
    merged["urban_to_department_mapping"] = (
        "SAME_DEPARTMENT_CODE;URBAN_PROXY_NOT_DEPARTMENT_OBSERVATION"
    )
    return merged


class FeatureBuilder:
    """Derive model features from the joined panel."""

    def __init__(self, policy: FeaturePolicy) -> None:
        """Store the policy."""
        self._policy = policy

    def build(self, panel: pd.DataFrame) -> pd.DataFrame:
        """Return the feature table (one row per territory and month).

        Raises
        ------
        FeatureError
            If a target column leaks in or a feature is not finite.
        """
        floor = self._policy.safe_division_floor
        frame = (
            panel.copy()
            .sort_values(["dep_code", "date"])
            .reset_index(drop=True)
        )

        def ratio(numerator: str, denominator: str) -> pd.Series:
            return frame[numerator] / frame[denominator].clip(lower=floor)

        frame["urban_unemployment_rate"] = 100 * ratio(
            "urban_unemployed", "urban_labor_force"
        )
        frame["urban_employment_rate"] = 100 * ratio(
            "urban_employed", "urban_working_age"
        )
        frame["urban_participation_rate"] = 100 * ratio(
            "urban_labor_force", "urban_working_age"
        )
        frame["urban_inactivity_rate"] = 100 * ratio(
            "urban_inactive", "urban_working_age"
        )
        frame["national_unemployment_rate"] = 100 * ratio(
            "nat_unemployed", "nat_labor_force"
        )
        frame["national_employment_rate"] = 100 * ratio(
            "nat_employed", "nat_working_age"
        )
        frame["national_participation_rate"] = 100 * ratio(
            "nat_labor_force", "nat_working_age"
        )
        frame["urban_minus_national_unemployment_pp"] = (
            frame["urban_unemployment_rate"]
            - frame["national_unemployment_rate"]
        )
        frame["urban_minus_national_employment_pp"] = (
            frame["urban_employment_rate"] - frame["national_employment_rate"]
        )
        frame["urban_population_to_department_projection"] = ratio(
            "urban_population", "population_demographic_projection"
        )
        frame["urban_employed_to_national"] = ratio(
            "urban_employed", "nat_employed"
        )
        frame["urban_working_age_to_national"] = ratio(
            "urban_working_age", "nat_working_age"
        )
        frame["log1p_department_population_projection"] = np.log1p(
            frame["population_demographic_projection"]
        )
        for quantity in self._policy.log_quantities:
            frame[f"log1p_urban_{quantity}"] = np.log1p(
                frame[f"urban_{quantity}"]
            )
        for quantity in self._policy.growth_quantities:
            series = frame.groupby("dep_code")[f"urban_{quantity}"]
            for lag in self._policy.lags:
                lagged = series.shift(lag)
                name = "yoy" if lag == 12 else "mom"
                frame[f"urban_{quantity}_{name}_pct"] = 100 * (
                    frame[f"urban_{quantity}"] / lagged.clip(lower=floor) - 1
                )
                # Warm-up months have no history: explicit flag, neutral fill.
                frame[f"urban_{quantity}_lag{lag}_warmup"] = lagged.isna()
                frame[f"urban_{quantity}_lag{lag}"] = lagged.fillna(
                    frame[f"urban_{quantity}"]
                )
        for column in frame.columns:
            if column.endswith("_pct"):
                frame[column] = (
                    frame[column].replace([np.inf, -np.inf], np.nan).fillna(0)
                )
        frame["month_sin"] = np.sin(2 * np.pi * frame["month"] / 12)
        frame["month_cos"] = np.cos(2 * np.pi * frame["month"] / 12)
        if any(column.startswith("target_") for column in frame.columns):
            raise FeatureError("Target leakage into features")
        numeric = frame.select_dtypes(include=[np.number]).columns
        if not np.isfinite(np.array(frame[numeric], dtype=float)).all():
            raise FeatureError("Non-finite feature values")
        return frame

    def targets(
        self,
        features: pd.DataFrame,
        departmental: pd.DataFrame,
        anchored_codes: Sequence[int],
    ) -> pd.DataFrame:
        """Attach departmental labels and their ratios (never invented).

        Raises
        ------
        FeatureError
            If labels appear for territories without anchors.
        """
        policy = self._policy
        labels = departmental[
            ["dep_code", "period", "origin", *QUANTITIES]
        ].rename(
            columns={
                "origin": "target_origin",
                **{q: f"target_{q}" for q in QUANTITIES},
            }
        )
        result = features[
            [
                "dep_code",
                "period",
                "year",
                "month",
                "is_synthetic_urban_signal",
            ]
        ].merge(
            labels,
            on=["dep_code", "period"],
            how="left",
            validate="one_to_one",
        )
        result["is_target_available"] = result["dep_code"].isin(
            list(anchored_codes)
        )
        result["target_status"] = np.where(
            result["target_employed"].notna(),
            np.where(
                result["year"] >= policy.training_first_year,
                STATUS_ANCHORED,
                STATUS_UNANCHORED,
            ),
            STATUS_MISSING,
        )
        result["eligible_training"] = (
            result["target_status"] == STATUS_ANCHORED
        )
        result["eligible_unbiased_cundinamarca_validation"] = ~result[
            "is_synthetic_urban_signal"
        ]
        for name, (numerator, denominator) in TARGET_RATIOS.items():
            result[name] = result[f"target_{numerator}"] / result[
                f"target_{denominator}"
            ].clip(lower=_TARGET_FLOOR)
        unlabeled = result[~result["is_target_available"]]
        if (
            unlabeled[["target_employed", "target_working_age"]]
            .notna()
            .any()
            .any()
        ):
            raise FeatureError("Invented target values")
        return result
