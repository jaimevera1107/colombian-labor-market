"""Common post-adjustment evaluation and the 33-territory panels (hito 4).

Out-of-fold rate predictions of every model (plus four predeclared hybrid
portfolios that take each rate from a given source) are passed through
twelve label-blind post-processors and evaluated against annual means of
the reconstructed targets. One common post-processor is fixed; among models
that pass declared guards relative to the Ward reference, the lowest
development MAE is selected. The final panel uses the full-sample Ward
predictions (and urban rates for the hybrid), closes the rates, restores
the annually anchored departmental reconstructions and bridges 2026.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

RATES: tuple[str, ...] = ("to", "td", "tgp", "pet_demog")
LEVELS: tuple[str, ...] = (
    "employed",
    "unemployed",
    "labor_force",
    "working_age",
    "inactive",
)
KEYS: list[str] = ["fold_id", "dep_code", "period"]
POST_METHODS: dict[str, dict[str, Any]] = {
    "00_cierre_actual": {"closure": "legacy"},
    "01_proyeccion_equilibrada": {"closure": "balanced"},
    "02_desempleo_prioritario": {"closure": "td_priority"},
    "03_participacion_prioritaria": {"closure": "tgp_priority"},
    "04_regularizacion_causal_suave": {"closure": "balanced", "ema": 0.75},
    "05_regularizacion_causal_moderada": {"closure": "balanced", "ema": 0.50},
    "06_limite_variacion_7pp": {"closure": "balanced", "cap": 0.07},
    "07_mezcla_urbana_10": {"closure": "balanced", "blend": 0.10},
    "08_mezcla_urbana_25": {"closure": "balanced", "blend": 0.25},
    "09_mezcla_urbana_50": {"closure": "balanced", "blend": 0.50},
    "10_mezcla10_y_causal": {
        "closure": "balanced",
        "blend": 0.10,
        "ema": 0.75,
    },
    "11_limite_variacion_4pp": {"closure": "balanced", "cap": 0.04},
}
PORTFOLIOS: dict[str, dict[str, str]] = {
    "hibrido_urbano_to_xgb_resto": {
        "to": "urban_analog",
        "td": "xgb_none",
        "tgp": "xgb_none",
        "pet_demog": "xgb_none",
    },
    "hibrido_urbano_to_tgp_xgb_td_pet": {
        "to": "urban_analog",
        "td": "xgb_ward",
        "tgp": "urban_analog",
        "pet_demog": "xgb_ward",
    },
    "hibrido_xgb_td_urbano_resto": {
        "to": "urban_analog",
        "td": "xgb_none",
        "tgp": "urban_analog",
        "pet_demog": "urban_analog",
    },
    "hibrido_urbano_tgp_ward_resto": {
        "to": "xgb_ward",
        "td": "xgb_ward",
        "tgp": "urban_analog",
        "pet_demog": "xgb_ward",
    },
}
CLOSURE_WEIGHTS: dict[str, tuple[float, float, float]] = {
    "balanced": (1.0, 1.0, 1.0),
    "td_priority": (1.0, 6.0, 1.0),
    "tgp_priority": (1.0, 1.0, 6.0),
}
ORIGIN_MODEL = "PREDICCION_MODELO_EXPERIMENTAL"
ORIGIN_ANCHORED = "RECONSTRUCCION_CON_ANCLA_ANUAL"
ORIGIN_RETROPOLATED = "RECONSTRUCCION_RETROPOLADA_SIN_ANCLA_ANUAL"
ORIGIN_PROVISIONAL = "PREDICCION_PROVISIONAL_2026"
ORIGIN_UNANCHORED = "PREDICCION_TERRITORIO_SIN_ANCLA"
ORIGIN_EXTRAPOLATED = "PREDICCION_EXTRAPOLADA_SIN_ANCLA"
_IDENTITY_TOLERANCE = 1e-5
_EVAL_TOLERANCE = 1e-6
_PARETO_EPSILON = 1e-10


class SelectionError(ValueError):
    """Raised when selection inputs or panels break the contract."""


@dataclass(frozen=True)
class SelectionPolicy:
    """Guards, reference model, bootstrap and bridge settings."""

    candidate: str
    reference_model: str
    common_postprocessing: str
    reserve_group_prefix: str
    max_worst_increase_pp: float
    max_intervention_pp: float
    max_reserve_mae_increase_pp: float
    bootstrap_replicates: int
    bootstrap_seed: int
    bridge_taper_months: int
    anchor_first_year: int
    anchor_last_year: int
    closure_iterations: int
    large_jump: float


class RateCloser:
    """Close four rates onto ``TO = TGP x (1 - TD)``."""

    def __init__(self, iterations: int) -> None:
        """Store the number of alternating iterations."""
        self._iterations = iterations

    def close(self, raw: np.ndarray, variant: str) -> np.ndarray:
        """Return coherent ``[to, td, tgp, pet_demog]`` columns.

        ``legacy`` holds TD fixed; the weighted variants alternate exact
        conditional minimizers of a weighted least-squares objective.

        Raises
        ------
        SelectionError
            On an unknown variant.
        """
        clipped = np.clip(np.asarray(raw, dtype=float), 0, 1)
        employment, unemployment, participation, working_age = clipped.T
        if variant == "legacy":
            corrected = np.clip(
                (participation + (1 - unemployment) * employment)
                / (1 + (1 - unemployment) ** 2),
                0,
                1,
            )
            return np.column_stack(
                (
                    corrected * (1 - unemployment),
                    unemployment,
                    corrected,
                    working_age,
                )
            )
        if variant not in CLOSURE_WEIGHTS:
            raise SelectionError(f"Unknown closure: {variant}")
        w_to, w_td, w_tgp = CLOSURE_WEIGHTS[variant]
        g, d = participation.copy(), unemployment.copy()
        for _ in range(self._iterations):
            g = np.clip(
                (w_tgp * participation + w_to * (1 - d) * employment)
                / (w_tgp + w_to * (1 - d) ** 2),
                0,
                1,
            )
            d = np.clip(
                (w_td * unemployment + w_to * g * (g - employment))
                / (w_td + w_to * g**2),
                0,
                1,
            )
        g = np.clip(
            (w_tgp * participation + w_to * (1 - d) * employment)
            / (w_tgp + w_to * (1 - d) ** 2),
            0,
            1,
        )
        return np.column_stack((g * (1 - d), d, g, working_age))


def causal_transform(
    values: np.ndarray,
    alpha: float | None,
    cap: float | None,
    large_jump: float,
) -> np.ndarray:
    """Causal smoothing / step cap per department and fold.

    Jumps larger than ``large_jump`` are kept (crises are not washed out).
    """
    if alpha is None and cap is None:
        return values.copy()
    result = values.copy()
    for t in range(1, len(values)):
        previous, current = result[t - 1], values[t]
        if alpha is not None:
            weights = np.where(
                np.abs(current - previous) > large_jump, 1.0, alpha
            )
            current = previous + weights * (current - previous)
        if cap is not None:
            current = previous + np.clip(current - previous, -cap, cap)
        result[t] = np.clip(current, 0, 1)
    return result


def oof_wide(oof: pd.DataFrame) -> pd.DataFrame:
    """Wide OOF table of all models plus the hybrid portfolios.

    Raises
    ------
    SelectionError
        On duplicated or missing predictions.
    """
    keys = [*KEYS, "model"]
    if (
        oof.duplicated(subset=[*keys, "variable"]).any()
        or oof["pred"].isna().any()
    ):
        raise SelectionError("Invalid out-of-fold predictions")
    wide = oof.pivot(
        index=keys, columns="variable", values="pred"
    ).reset_index()
    wide.columns.name = None
    wide = wide.sort_values(keys).reset_index(drop=True)
    index = (
        wide[KEYS].drop_duplicates().sort_values(KEYS).reset_index(drop=True)
    )
    hybrids = []
    for portfolio, sources in PORTFOLIOS.items():
        hybrid = index.copy()
        hybrid["model"] = portfolio
        for rate, source in sources.items():
            reference = wide.loc[wide["model"] == source, [*KEYS, rate]]
            hybrid = hybrid.merge(reference, on=KEYS, validate="one_to_one")
        hybrids.append(hybrid)
    return (
        pd.concat([wide, *hybrids], ignore_index=True)
        .sort_values(keys)
        .reset_index(drop=True)
    )


@dataclass(frozen=True)
class SelectionResult:
    """Evaluation tables and the selected model."""

    annual: pd.DataFrame
    comparison: pd.DataFrame
    decision: pd.DataFrame
    paired_errors: pd.DataFrame
    summary: dict[str, Any]


class PostAdjustmentSelector:
    """Evaluate post-processors on OOF rates and select a model."""

    def __init__(self, policy: SelectionPolicy) -> None:
        """Store the policy (including the declared hybrid candidate)."""
        self._policy = policy
        self._candidate = policy.candidate
        self._closer = RateCloser(policy.closure_iterations)

    def _apply(
        self, raw: pd.DataFrame, urban: pd.DataFrame, method: Mapping[str, Any]
    ) -> pd.DataFrame:
        values = np.array(raw[list(RATES)], dtype=float)
        analog = np.array(urban[list(RATES)], dtype=float)
        if method.get("blend"):
            weight = method["blend"]
            values = (1 - weight) * values + weight * analog
        adjusted = values.copy()
        if "ema" in method or "cap" in method:
            groups = raw.groupby(["fold_id", "dep_code"], sort=False).indices
            for index in groups.values():
                index = np.sort(index)
                adjusted[index] = causal_transform(
                    values[index],
                    method.get("ema"),
                    method.get("cap"),
                    self._policy.large_jump,
                )
        closed = self._closer.close(adjusted, method["closure"])
        result = raw[KEYS].copy()
        for position, rate in enumerate(RATES):
            result[rate] = closed[:, position]
        return result

    @staticmethod
    def _evaluate(
        prediction: pd.DataFrame,
        base: pd.DataFrame,
        original: pd.DataFrame,
        name: str,
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        data = prediction.merge(
            base[
                [
                    *KEYS,
                    "model",
                    "population_demographic_projection",
                    *[f"target_{q}" for q in LEVELS],
                ]
            ],
            on=KEYS,
            validate="one_to_one",
        )
        population = data["population_demographic_projection"]
        data["working_age"] = population * data["pet_demog"]
        data["labor_force"] = data["working_age"] * data["tgp"]
        data["unemployed"] = data["labor_force"] * data["td"]
        data["employed"] = data["labor_force"] - data["unemployed"]
        data["inactive"] = data["working_age"] - data["labor_force"]
        if (np.array(data[list(LEVELS)]) < -_EVAL_TOLERANCE).any() or (
            data["working_age"] > population + 1e-7
        ).any():
            raise SelectionError("Inadmissible evaluated levels")
        data["year"] = data["period"].str.slice(0, 4).astype(int)
        data["postprocessing"] = name
        for rate in RATES:
            data[f"delta_{rate}_pp"] = 100 * (
                np.array(data[rate]) - np.array(original[rate])
            )
        aggregations: dict[str, tuple[str, str]] = {
            q: (q, "mean") for q in LEVELS
        }
        aggregations.update(
            {f"target_{q}": (f"target_{q}", "mean") for q in LEVELS}
        )
        aggregations["population_demographic_projection"] = (
            "population_demographic_projection",
            "mean",
        )
        annual = data.groupby(
            ["model", "postprocessing", "fold_id", "dep_code", "year"],
            as_index=False,
        ).agg(**aggregations)
        for rate, numerator, denominator in (
            ("to", "employed", "working_age"),
            ("td", "unemployed", "labor_force"),
            ("tgp", "labor_force", "working_age"),
            ("pet_demog", "working_age", "population_demographic_projection"),
        ):
            target_denominator = (
                f"target_{denominator}"
                if denominator != "population_demographic_projection"
                else denominator
            )
            annual[f"pred_{rate}"] = annual[numerator] / annual[denominator]
            annual[f"ref_{rate}"] = (
                annual[f"target_{numerator}"] / annual[target_denominator]
            )
            annual[f"abs_{rate}_pp"] = 100 * abs(
                annual[f"pred_{rate}"] - annual[f"ref_{rate}"]
            )
        for level in LEVELS:
            annual[f"abs_{level}_pct"] = (
                100
                * abs(annual[level] - annual[f"target_{level}"])
                / annual[f"target_{level}"].clip(lower=1)
            )
        return data, annual

    @staticmethod
    def _summarize(data: pd.DataFrame, annual: pd.DataFrame) -> pd.DataFrame:
        actual = {
            "to": data["target_employed"] / data["target_working_age"],
            "td": data["target_unemployed"] / data["target_labor_force"],
            "tgp": data["target_labor_force"] / data["target_working_age"],
            "pet_demog": data["target_working_age"]
            / data["population_demographic_projection"],
        }
        data = data.copy()
        data["mae_monthly_pp"] = 100 * np.mean(
            [abs(data[r] - actual[r]) for r in RATES], axis=0
        )
        data["intervention_pp"] = np.mean(
            [abs(data[f"delta_{r}_pp"]) for r in RATES], axis=0
        )
        data = data.sort_values(KEYS)
        data["roughness_pp"] = 0.0
        for rate in ("to", "td", "tgp"):
            step = data.groupby(["fold_id", "dep_code"])[rate].diff()
            data["roughness_pp"] += 100 * step.abs().fillna(0) / 3
        monthly = (
            data.groupby(["model", "postprocessing"])
            .agg(
                mae_monthly_pp=("mae_monthly_pp", "mean"),
                intervention_pp=("intervention_pp", "mean"),
                intervention_max_pp=("intervention_pp", "max"),
                roughness_pp=("roughness_pp", "mean"),
            )
            .reset_index()
        )
        yearly = annual.copy()
        yearly["mae_annual_pp"] = yearly[[f"abs_{r}_pp" for r in RATES]].mean(
            axis=1
        )
        yearly["mape_levels_pct"] = yearly[
            [f"abs_{q}_pct" for q in LEVELS]
        ].mean(axis=1)
        summary = (
            yearly.groupby(["model", "postprocessing"])
            .agg(
                mae_annual_pp=("mae_annual_pp", "mean"),
                mape_levels_pct=("mape_levels_pct", "mean"),
            )
            .reset_index()
        )
        worst = (
            yearly.groupby(["model", "postprocessing", "fold_id", "dep_code"])[
                "mae_annual_pp"
            ]
            .mean()
            .groupby(["model", "postprocessing"])
            .max()
            .rename("worst_territory_pp")
            .reset_index()
        )
        summary = summary.merge(worst, on=["model", "postprocessing"]).merge(
            monthly, on=["model", "postprocessing"], validate="one_to_one"
        )
        summary["group"] = np.where(
            summary["model"] == "urban_analog",
            "baseline",
            np.where(summary["model"] == "ridge", "ridge", "xgboost"),
        )
        return summary

    def run(
        self,
        oof: pd.DataFrame,
        labels: pd.DataFrame,
        projections: pd.DataFrame,
    ) -> SelectionResult:
        """Evaluate every model and post-processor, then select."""
        policy = self._policy
        wide = oof_wide(oof)
        analog = wide.loc[wide["model"] == "urban_analog", [*KEYS, *RATES]]
        urban = wide[[*KEYS, "model"]].merge(
            analog, on=KEYS, how="left", validate="many_to_one", sort=False
        )
        full = wide.merge(
            projections, on=["dep_code", "period"], validate="many_to_one"
        ).merge(labels, on=["dep_code", "period"], validate="many_to_one")
        data, annual = [], []
        for name, subset in wide.groupby("model", sort=True):
            subset = subset.reset_index(drop=True)
            analog_rows = urban.loc[wide["model"] == name].reset_index(
                drop=True
            )
            base = full.loc[full["model"] == name].reset_index(drop=True)
            for post, config in POST_METHODS.items():
                evaluated, yearly = self._evaluate(
                    self._apply(subset, analog_rows, config),
                    base,
                    subset,
                    post,
                )
                data.append(evaluated)
                annual.append(yearly)
        monthly_all = pd.concat(data, ignore_index=True)
        annual_all = pd.concat(annual, ignore_index=True)
        reserve = policy.reserve_group_prefix
        summaries = []
        for sample, in_reserve in (("development", False), ("reserve", True)):
            mask = monthly_all["fold_id"].str.startswith(reserve) == in_reserve
            annual_mask = (
                annual_all["fold_id"].str.startswith(reserve) == in_reserve
            )
            summary = self._summarize(
                monthly_all.loc[mask], annual_all.loc[annual_mask]
            )
            summary["sample"] = sample
            summaries.append(summary)
        comparison = pd.concat(summaries, ignore_index=True)
        decision = self._decide(comparison)
        chosen = str(decision.loc[decision["eligible"]].iloc[0]["model"])
        paired, interval, mean_difference = self._paired(annual_all)
        summary_record = {
            "n_configurations": int(len(comparison) // 2),
            "n_folds": int(wide["fold_id"].nunique()),
            "n_unique_oof_rows": int(len(wide[KEYS].drop_duplicates())),
            "selected_model": chosen,
            "common_postprocessing": policy.common_postprocessing,
            "hybrid_minus_reference_mean_pp": mean_difference,
            "bootstrap_cluster_ci95_pp": interval,
            "reserve_is_blind": False,
        }
        return SelectionResult(
            annual=annual_all,
            comparison=comparison,
            decision=decision,
            paired_errors=paired,
            summary=summary_record,
        )

    def _decide(self, comparison: pd.DataFrame) -> pd.DataFrame:
        policy = self._policy
        post = policy.common_postprocessing
        development = comparison[
            (comparison["sample"] == "development")
            & (comparison["postprocessing"] == post)
        ]
        reserve = comparison[
            (comparison["sample"] == "reserve")
            & (comparison["postprocessing"] == post)
        ]
        table = development.merge(
            reserve[["model", "mae_annual_pp", "worst_territory_pp"]].rename(
                columns={
                    "mae_annual_pp": "reserve_mae_pp",
                    "worst_territory_pp": "reserve_worst_pp",
                }
            ),
            on="model",
        )
        reference = table[table["model"] == policy.reference_model].iloc[0]
        table["eligible"] = (
            (
                table["worst_territory_pp"]
                <= reference["worst_territory_pp"]
                + policy.max_worst_increase_pp
            )
            & (table["intervention_pp"] <= policy.max_intervention_pp)
            & (
                table["reserve_mae_pp"]
                <= reference["reserve_mae_pp"]
                + policy.max_reserve_mae_increase_pp
            )
        )
        values = np.array(
            table[
                [
                    "mae_annual_pp",
                    "worst_territory_pp",
                    "mape_levels_pct",
                    "intervention_pp",
                ]
            ]
        )
        table["pareto_frontier"] = [
            not (
                (values <= values[i] + _PARETO_EPSILON).all(axis=1)
                & (values < values[i] - _PARETO_EPSILON).any(axis=1)
            ).any()
            for i in range(len(values))
        ]
        return table.sort_values(
            ["eligible", "mae_annual_pp"], ascending=[False, True]
        )

    def _paired(
        self, annual: pd.DataFrame
    ) -> tuple[pd.DataFrame, list[float], float]:
        policy = self._policy
        reference = policy.reference_model
        key = annual[
            (annual["postprocessing"] == policy.common_postprocessing)
            & annual["model"].isin(
                [self._candidate, reference, "urban_analog", "xgb_none"]
            )
        ]
        key = key.assign(
            mae_annual_pp=key[[f"abs_{r}_pp" for r in RATES]].mean(axis=1)
        )
        grouped = (
            key.groupby(["model", "fold_id", "dep_code"])["mae_annual_pp"]
            .mean()
            .reset_index()
        )
        pivot = grouped.pivot(
            index=["fold_id", "dep_code"],
            columns="model",
            values="mae_annual_pp",
        )
        pivot.columns.name = None
        pivot["hybrid_minus_reference_pp"] = (
            pivot[self._candidate] - pivot[reference]
        )
        development = pivot.reset_index()
        development = development[
            ~development["fold_id"].str.startswith(policy.reserve_group_prefix)
        ]
        by_department = development.groupby("dep_code")[
            "hybrid_minus_reference_pp"
        ].mean()
        rng = np.random.default_rng(policy.bootstrap_seed)
        boots = np.mean(
            rng.choice(
                by_department.to_numpy(),
                size=(policy.bootstrap_replicates, len(by_department)),
                replace=True,
            ),
            axis=1,
        )
        interval = np.quantile(boots, [0.025, 0.975]).tolist()
        return pivot.reset_index(), interval, float(by_department.mean())


class FinalPanelBuilder:
    """Build the complete 33-territory panel for a selected model."""

    def __init__(
        self,
        policy: SelectionPolicy,
        territory_codes: Sequence[int],
        synthetic_code: int,
    ) -> None:
        """Store settings."""
        self._policy = policy
        self._candidate = policy.candidate
        self._codes = set(territory_codes)
        self._synthetic = synthetic_code
        self._closer = RateCloser(policy.closure_iterations)

    def build(
        self,
        predictions: pd.DataFrame,
        features: pd.DataFrame,
        targets: pd.DataFrame,
        model: str,
    ) -> pd.DataFrame:
        """Return the panel for ``model`` (the reference or the hybrid).

        Raises
        ------
        SelectionError
            If coverage, anchors or identities are violated.
        """
        policy = self._policy
        keys = ["dep_code", "period"]
        ward = predictions[predictions["variant"] == "filtered"]
        joined = ward.merge(
            features[
                [
                    *keys,
                    "urban_employment_rate",
                    "urban_participation_rate",
                    "urban_unemployment_rate",
                ]
            ],
            on=keys,
            validate="one_to_one",
            sort=False,
        )
        hybrid = model == self._candidate
        raw = np.column_stack(
            [
                np.array(joined["urban_employment_rate"]) / 100
                if hybrid
                else np.array(joined["to"]),
                np.array(joined["td"]),
                np.array(joined["urban_participation_rate"]) / 100
                if hybrid
                else np.array(joined["tgp"]),
                np.array(joined["pet_demog"]),
            ]
        )
        closed = self._closer.close(raw, "legacy")
        panel = joined[
            [
                *keys,
                "year",
                "population_demographic_projection",
                "is_synthetic_urban_signal",
            ]
        ].copy()
        for position, rate in enumerate(RATES):
            panel[f"raw_{rate}"] = raw[:, position]
            panel[f"final_{rate}"] = closed[:, position]
            panel[f"delta_{rate}_pp"] = 100 * (
                closed[:, position] - raw[:, position]
            )
        self._levels(panel, panel.index, closed)
        panel["origin"] = ORIGIN_MODEL
        references = targets.loc[
            targets["target_employed"].notna(),
            [*keys, *[f"target_{q}" for q in LEVELS]],
        ]
        references = references.rename(
            columns={f"target_{q}": q for q in LEVELS}
        )
        merged = panel.merge(
            references,
            on=keys,
            how="left",
            suffixes=("", "_ref"),
            validate="one_to_one",
        )
        has = merged["employed_ref"].notna()
        unanchored = self._codes - set(references["dep_code"])
        missing = merged["dep_code"].isin(unanchored)
        for level in LEVELS:
            merged[f"predicted_pre_reference_{level}"] = merged[level]
            merged.loc[has, level] = merged.loc[has, f"{level}_ref"]
        first, last = policy.anchor_first_year, policy.anchor_last_year
        merged.loc[has & merged["year"].lt(first), "origin"] = (
            ORIGIN_RETROPOLATED
        )
        merged.loc[has & merged["year"].between(first, last), "origin"] = (
            ORIGIN_ANCHORED
        )
        merged.loc[~has & merged["year"].gt(last), "origin"] = (
            ORIGIN_PROVISIONAL
        )
        merged.loc[missing, "origin"] = ORIGIN_UNANCHORED
        merged.loc[~has & merged["year"].lt(first), "origin"] = (
            ORIGIN_EXTRAPOLATED
        )
        merged["bridge_pp"] = 0.0
        for code in sorted(self._codes - unanchored):
            self._bridge(merged, code, last)
        merged["is_synthetic_signal"] = merged["dep_code"] == self._synthetic
        merged["employment_rate"] = merged["employed"] / merged["working_age"]
        merged["unemployment_rate"] = (
            merged["unemployed"] / merged["labor_force"]
        )
        merged["participation_rate"] = (
            merged["labor_force"] / merged["working_age"]
        )
        merged["working_age_population_rate"] = (
            merged["working_age"] / merged["population_demographic_projection"]
        )
        merged["closure_cost_pp"] = (
            merged[[f"delta_{r}_pp" for r in RATES]].abs().mean(axis=1)
        )
        merged["max_anchor_adjustment_persons"] = np.max(
            [
                abs(merged[q] - merged[f"predicted_pre_reference_{q}"])
                for q in LEVELS
            ],
            axis=0,
        )
        self._verify(merged)
        return merged.drop(columns=[f"{q}_ref" for q in LEVELS])

    @staticmethod
    def _levels(
        frame: pd.DataFrame, index: pd.Index, rates: np.ndarray
    ) -> None:
        population = np.array(
            frame.loc[index, "population_demographic_projection"], dtype=float
        )
        working_age = population * rates[:, 3]
        labor_force = working_age * rates[:, 2]
        unemployed = labor_force * rates[:, 1]
        frame.loc[index, "working_age"] = working_age
        frame.loc[index, "labor_force"] = labor_force
        frame.loc[index, "unemployed"] = unemployed
        frame.loc[index, "employed"] = labor_force - unemployed
        frame.loc[index, "inactive"] = working_age - labor_force

    def _bridge(self, merged: pd.DataFrame, code: int, last: int) -> None:
        """Taper the last anchored rates into the provisional months."""
        last_month = merged.index[
            (merged["dep_code"] == code) & (merged["period"] == f"{last}-12")
        ]
        later = merged.index[
            (merged["dep_code"] == code) & (merged["year"] > last)
        ]
        if len(last_month) != 1:
            raise SelectionError(f"Missing last anchored month for {code}")
        base_row = merged.loc[last_month[0]]
        anchor = np.array(
            [
                base_row["employed"] / base_row["working_age"],
                base_row["unemployed"] / base_row["labor_force"],
                base_row["labor_force"] / base_row["working_age"],
                base_row["working_age"]
                / base_row["population_demographic_projection"],
            ],
            dtype=float,
        )
        base = np.array(base_row[[f"final_{r}" for r in RATES]], dtype=float)
        before = np.array(
            merged.loc[later, [f"final_{r}" for r in RATES]], dtype=float
        )
        months = np.arange(len(later))
        taper = np.maximum(
            0.0, 1.0 - months / self._policy.bridge_taper_months
        )[:, None]
        after = self._closer.close(
            np.clip(before + taper * (anchor - base)[None, :], 0.0, 1.0),
            "legacy",
        )
        merged.loc[later, "bridge_pp"] = np.abs((after - before) * 100).mean(
            axis=1
        )
        for position, rate in enumerate(RATES):
            merged.loc[later, f"final_{rate}"] = after[:, position]
        self._levels(merged, later, after)

    def _verify(self, merged: pd.DataFrame) -> None:
        if (
            max(
                float(
                    abs(
                        merged["labor_force"]
                        - merged["employed"]
                        - merged["unemployed"]
                    ).max()
                ),
                float(
                    abs(
                        merged["working_age"]
                        - merged["labor_force"]
                        - merged["inactive"]
                    ).max()
                ),
            )
            >= _IDENTITY_TOLERANCE
        ):
            raise SelectionError("Panel identities not closed")
        if (np.array(merged[list(LEVELS)]) < -1e-7).any() or (
            merged["working_age"]
            > merged["population_demographic_projection"] + _IDENTITY_TOLERANCE
        ).any():
            raise SelectionError("Inadmissible panel levels")
        sizes = merged.groupby("dep_code").size()
        if set(sizes.index) != self._codes or (sizes != sizes.iloc[0]).any():
            raise SelectionError("Incomplete 33-territory panel")
