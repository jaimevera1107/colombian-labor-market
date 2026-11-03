"""Post-closure territorial transfer evaluation (leave one out).

For every anchored department H (except excluded ones), H is treated as if
it had no departmental survey data: models and clusters are refitted
without it, the 33-territory panel is built with H as an unanchored
territory, the hierarchical closure runs without H's anchors, and H's
annual means for the anchored years are compared with its official
anchors. The comparison is made before the closure (the model panel) and
after it (what would be published), for every candidate and for two
baselines that use no departmental model at all.

What this measures is the error of reconstructing an unanchored territory
with the published method. It does not measure the error of the ten real
unanchored territories, whose structure (size, remoteness) differs from
the anchored ones; it is evidence of transferability, not of accuracy.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from icml.evaluation.closures import Closure
from icml.modeling.selection import FinalPanelBuilder
from icml.modeling.training import RATE_TARGETS, DepartmentalTrainer

LEVELS: tuple[str, ...] = (
    "employed",
    "unemployed",
    "inactive",
    "labor_force",
    "working_age",
)
RATES: dict[str, tuple[str, str]] = {
    "unemployment_rate": ("unemployed", "labor_force"),
    "employment_rate": ("employed", "working_age"),
    "participation_rate": ("labor_force", "working_age"),
}
STAGE_MODEL = "model"
BASELINES = ("urban_analog", "national_rates")
TRAINED = ("xgb_ward", "xgb_none")
HYBRID = "hybrid"


class TransferError(ValueError):
    """Raised when the evaluation design is invalid."""


@dataclass(frozen=True)
class TransferPolicy:
    """Hidden territories, evaluation years and candidates."""

    modeling_config: str
    reconciliation_config: str
    excluded_codes: Sequence[int]
    hidden_codes: Sequence[int]
    first_year: int
    last_year: int
    candidates: Sequence[str]
    closures: Sequence[str]

    def __post_init__(self) -> None:
        """Validate candidates and years."""
        known = {*TRAINED, HYBRID, *BASELINES}
        unknown = set(self.candidates) - known
        if unknown:
            raise ValueError(f"Unknown candidates: {sorted(unknown)}")
        if self.first_year > self.last_year:
            raise ValueError("first_year must not exceed last_year")


@dataclass(frozen=True)
class TransferResult:
    """Annual comparisons and summaries."""

    annual: pd.DataFrame
    summary: pd.DataFrame
    by_department: pd.DataFrame


def annual_comparison(
    panel: pd.DataFrame,
    anchors: pd.DataFrame,
    code: int,
    years: range,
    population_column: str,
) -> pd.DataFrame:
    """Annual means of one territory against its official anchors."""
    rows = panel[
        (panel["dep_code"] == code)
        & panel["year"].between(years.start, years.stop - 1)
    ]
    means = rows.groupby("year")[[*LEVELS, population_column]].mean()
    official = anchors[anchors["dep_code"] == code].set_index("year")
    result = pd.DataFrame({"year": means.index.astype(int)})
    for level in LEVELS:
        estimate = np.array(means[level], dtype=float)
        truth = np.array(official.loc[means.index, level], dtype=float)
        result[f"{level}_pct_error"] = 100 * (estimate / truth - 1)
    for rate, (numerator, denominator) in RATES.items():
        estimate = np.array(means[numerator] / means[denominator])
        truth = np.array(
            official.loc[means.index, numerator]
            / official.loc[means.index, denominator]
        )
        result[f"{rate}_pp_error"] = 100 * (estimate - truth)
    population = np.array(means[population_column], dtype=float)
    result["population_pct_error"] = 100 * (
        population
        / np.array(official.loc[means.index, "population"], dtype=float)
        - 1
    )
    return result


class TransferEvaluator:
    """Leave-one-out transfer evaluation through the full closure."""

    def __init__(
        self,
        policy: TransferPolicy,
        trainer: DepartmentalTrainer,
        panels: FinalPanelBuilder,
        closures: dict[str, Closure],
        hybrid_name: str,
        synthetic_code: int,
    ) -> None:
        """Compose the components reused from modeling and closure."""
        self._policy = policy
        self._trainer = trainer
        self._panels = panels
        self._closures = closures
        self._hybrid_name = hybrid_name
        self._synthetic = synthetic_code

    def hidden(self, anchored: Sequence[int]) -> list[int]:
        """Return the departments to hide, one per fold.

        Raises
        ------
        TransferError
            If a requested department is not anchored or is excluded.
        """
        policy = self._policy
        eligible = sorted(set(anchored) - set(policy.excluded_codes))
        if not policy.hidden_codes:
            return eligible
        invalid = set(policy.hidden_codes) - set(eligible)
        if invalid:
            raise TransferError(f"Cannot hide {sorted(invalid)}")
        return sorted(policy.hidden_codes)

    def run(
        self,
        features: pd.DataFrame,
        strict: pd.DataFrame,
        targets: pd.DataFrame,
        national: pd.DataFrame,
        anchors: pd.DataFrame,
    ) -> TransferResult:
        """Evaluate every fold and candidate."""
        policy = self._policy
        years = range(policy.first_year, policy.last_year + 1)
        anchored = sorted(set(anchors["dep_code"].astype(int)))
        rows = []
        for code in self.hidden(anchored):
            rows.extend(
                self._fold(
                    code,
                    features,
                    strict,
                    targets,
                    national,
                    anchors,
                    anchored,
                    years,
                )
            )
        annual = pd.concat(rows, ignore_index=True)
        return TransferResult(
            annual=annual,
            summary=summarize(annual),
            by_department=by_department(annual),
        )

    def _fold(
        self,
        code: int,
        features: pd.DataFrame,
        strict: pd.DataFrame,
        targets: pd.DataFrame,
        national: pd.DataFrame,
        anchors: pd.DataFrame,
        anchored: Sequence[int],
        years: range,
    ) -> list[pd.DataFrame]:
        masked = targets.copy()
        hidden_rows = masked["dep_code"] == code
        label_columns = [
            c
            for c in masked.columns
            if c.startswith("target_") and c not in ("target_origin",)
        ]
        masked.loc[hidden_rows, label_columns] = np.nan
        masked.loc[hidden_rows, list(RATE_TARGETS.values())] = np.nan
        remaining = [c for c in anchored if c != code]
        training = [c for c in remaining if c != self._synthetic]
        fold_anchors = anchors[anchors["dep_code"] != code]
        predictions: dict[str, pd.DataFrame] = {}
        for method in TRAINED:
            if method in self._policy.candidates or (
                method == "xgb_ward" and HYBRID in self._policy.candidates
            ):
                predictions[method] = self._trainer.final_fit(
                    features,
                    strict,
                    masked,
                    method,
                    training,
                    years,
                    remaining,
                ).predictions
        median_ratio = float(
            np.nanmedian(
                masked.loc[
                    masked["dep_code"].isin(training)
                    & masked["year"].between(years.start, years.stop - 1),
                    RATE_TARGETS["pet_demog"],
                ]
            )
        )
        if "urban_analog" in self._policy.candidates:
            predictions["urban_analog"] = _baseline(
                features,
                "urban_employment_rate",
                "urban_unemployment_rate",
                "urban_participation_rate",
                median_ratio,
            )
        if "national_rates" in self._policy.candidates:
            predictions["national_rates"] = _baseline(
                features,
                "national_employment_rate",
                "national_unemployment_rate",
                "national_participation_rate",
                median_ratio,
            )
        frames = []
        for candidate in self._policy.candidates:
            source = (
                predictions["xgb_ward"]
                if candidate == HYBRID
                else predictions[candidate]
            )
            model_name = self._hybrid_name if candidate == HYBRID else "seed"
            panel = self._panels.build(source, features, masked, model_name)
            stages = [
                (STAGE_MODEL, panel, "population_demographic_projection")
            ]
            for name, closure in self._closures.items():
                stages.append(
                    (
                        name,
                        closure.apply(panel, national, fold_anchors),
                        "labor_population_reconciled",
                    )
                )
            for stage, table, population in stages:
                result = annual_comparison(
                    table, anchors, code, years, population
                )
                result.insert(0, "stage", stage)
                result.insert(0, "candidate", candidate)
                result.insert(0, "hidden_code", code)
                frames.append(result)
        return frames


def _baseline(
    features: pd.DataFrame,
    employment: str,
    unemployment: str,
    participation: str,
    working_age_ratio: float,
) -> pd.DataFrame:
    """Rates taken directly from a signal, as model-free seeds."""
    frame = features[
        [
            "dep_code",
            "period",
            "year",
            "is_synthetic_urban_signal",
            "population_demographic_projection",
        ]
    ].copy()
    frame["variant"] = "filtered"
    frame["to"] = np.clip(np.array(features[employment]) / 100, 0, 1)
    frame["td"] = np.clip(np.array(features[unemployment]) / 100, 0, 1)
    frame["tgp"] = np.clip(np.array(features[participation]) / 100, 0, 1)
    frame["pet_demog"] = min(1.0, working_age_ratio)
    return frame


ERROR_COLUMNS: dict[str, str] = {
    **{f"{rate}_pp_error": "pp" for rate in RATES},
    **{f"{level}_pct_error": "pct" for level in LEVELS},
    "population_pct_error": "pct",
}


def summarize(annual: pd.DataFrame) -> pd.DataFrame:
    """Mean absolute errors per candidate and stage (department-years).

    ``worst_department_*`` is the largest department-level mean error.
    """
    rows = []
    for (candidate, stage), group in annual.groupby(["candidate", "stage"]):
        record: dict[str, Any] = {
            "candidate": candidate,
            "stage": stage,
            "n_department_years": len(group),
        }
        for column in ERROR_COLUMNS:
            absolute = group[column].abs()
            record[f"mae_{column}"] = float(absolute.mean())
            record[f"worst_department_{column}"] = float(
                absolute.groupby(group["hidden_code"]).mean().max()
            )
        record["mean_abs_rate_error_pp"] = float(
            np.mean([group[f"{r}_pp_error"].abs().mean() for r in RATES])
        )
        rows.append(record)
    return pd.DataFrame(rows)


def by_department(annual: pd.DataFrame) -> pd.DataFrame:
    """Mean absolute rate error per hidden department, candidate, stage."""
    columns = [f"{rate}_pp_error" for rate in RATES]
    table = annual.assign(
        mean_abs_rate_error_pp=annual[columns].abs().mean(axis=1)
    )
    return (
        table.groupby(["hidden_code", "candidate", "stage"])
        .agg(
            mean_abs_rate_error_pp=("mean_abs_rate_error_pp", "mean"),
            unemployed_mape=(
                "unemployed_pct_error",
                lambda s: float(s.abs().mean()),
            ),
            working_age_mape=(
                "working_age_pct_error",
                lambda s: float(s.abs().mean()),
            ),
        )
        .reset_index()
    )
